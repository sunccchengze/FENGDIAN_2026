"""Private CPU implementation of decision-boundary forecast-assisted MADDPG."""
from copy import deepcopy
import io
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .algorithm import MADDPG, mlp
from .benchmark import seed_for
from .causal_speed_search import command
from .forecast_decision_contract import discounted, forecast_features, sha, sha_history
from .history_wind_forecast import RidgeForecast

SCHEMA = "forecast_speed_macro_boundary_v1"
REPLAY_SCHEMA = "forecast_speed_macro_replay_v1"
INTERVAL = 8
HORIZON = 128
GAMMA = .99
TAU = .01
BATCH = 64
CAPACITY = 4096
SPECS = {
    "obs": ((3, 15), np.float32), "next_obs": ((3, 15), np.float32),
    "forecast": ((36,), np.float32), "next_forecast": ((36,), np.float32),
    "z": ((3,), np.float32), "raw_reward": ((8, 3), np.float32),
    "return": ((3,), np.float64), "discount": ((), np.float64),
    "m": ((), np.uint8), "terminal": ((), np.bool_), "next_forecast_valid": ((), np.bool_),
    "episode": ((), np.int64), "t": ((), np.uint8),
    "history": ((32,), np.uint8), "next_history": ((32,), np.uint8),
}


class MacroReplay:
    def __init__(self, seed, capacity=CAPACITY):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("positive macro capacity required")
        self.capacity = capacity
        self.insertions = 0
        self.rng = np.random.default_rng(seed)
        self.data = {key: np.zeros((capacity, *shape), dtype=dtype)
                     for key, (shape, dtype) in SPECS.items()}

    @property
    def size(self):
        return min(self.insertions, self.capacity)

    @property
    def position(self):
        return self.insertions % self.capacity

    def order(self):
        return np.arange(self.insertions-self.size, self.insertions) % self.capacity

    def add(self, row):
        if set(row) != SPECS.keys():
            raise ValueError("incorrect macro fields")
        for key, (shape, dtype) in SPECS.items():
            value = np.asarray(row[key])
            if value.shape != shape or value.dtype != dtype or not np.isfinite(value).all():
                raise ValueError("invalid macro field " + key)
        m, t, terminal = int(row["m"]), int(row["t"]), bool(row["terminal"])
        if (not 1 <= m <= INTERVAL or t % INTERVAL or t+m > HORIZON
                or (m != INTERVAL and not terminal) or np.any(np.abs(row["z"]) > 1)
                or terminal == bool(row["next_forecast_valid"])
                or (terminal and np.any(row["next_forecast"])) or np.any(row["raw_reward"][m:])
                or row["episode"] < 0):
            raise ValueError("invalid macro action, phase or terminal")
        reward, discount = discounted(row["raw_reward"][:m], GAMMA)
        if not np.array_equal(row["return"], reward) or row["discount"] != discount:
            raise ValueError("invalid actual-m return")
        if self.size:
            last = (self.position-1) % self.capacity
            if self.data["terminal"][last]:
                if row["episode"] != self.data["episode"][last]+1 or t != 0:
                    raise ValueError("new episode must start after terminal")
            elif (row["episode"] != self.data["episode"][last] or t != self.data["t"][last]+INTERVAL
                  or any(not np.array_equal(row[k], self.data["next_"+k][last])
                         for k in ("obs", "forecast", "history"))):
                raise ValueError("nonterminal macro boundary is discontinuous")
        for key, value in row.items():
            self.data[key][self.position] = value
        self.insertions += 1

    def sample(self):
        slots = self.rng.choice(self.size, BATCH, replace=False)
        keys = ("obs", "next_obs", "forecast", "next_forecast", "z", "return", "discount", "terminal")
        batch = {key: torch.from_numpy(self.data[key][slots]) for key in keys}
        return slots, batch

    def state(self):
        return dict(schema=REPLAY_SCHEMA, capacity=self.capacity, insertions=self.insertions,
                    rng=deepcopy(self.rng.bit_generator.state),
                    data={key: value[:self.size].copy() for key, value in self.data.items()})

    def restore(self, saved, episodes, arm):
        if (saved["schema"], saved["capacity"], saved["insertions"]) != (
                REPLAY_SCHEMA, self.capacity, episodes*(HORIZON//INTERVAL)):
            raise ValueError("macro replay schema or boundary counter mismatch")
        data = saved["data"]
        size = min(self.capacity, saved["insertions"])
        if set(data) != SPECS.keys() or any(
                data[k].shape != (size, *shape) or data[k].dtype != dtype
                for k, (shape, dtype) in SPECS.items()):
            raise ValueError("macro replay shape or dtype mismatch")
        # Validate every retained row in chronological order, including the wrap edge.
        self.insertions = saved["insertions"]-size
        for sequence in range(self.insertions, saved["insertions"]):
            slot = sequence % self.capacity
            row = {key: value[slot] for key, value in data.items()}
            episode, block = divmod(sequence, HORIZON//INTERVAL)
            t = block*INTERVAL
            if (row["episode"] != episode or row["t"] != t or row["m"] != INTERVAL
                    or row["terminal"] != (t+INTERVAL == HORIZON)
                    or not np.all(row["obs"][:, 14] == 1-t/HORIZON)
                    or not np.all(row["next_obs"][:, 14] == 1-(t+INTERVAL)/HORIZON)
                    or (arm == "B" and (np.any(row["forecast"]) or np.any(row["next_forecast"])))):
                raise ValueError("macro replay clock or information mode mismatch")
            if sequence == saved["insertions"]-size:
                # Its predecessor may have been overwritten.
                self._first_retained(row, sequence)
            else:
                self.add(row)
        self.rng.bit_generator.state = deepcopy(saved["rng"])

    def _first_retained(self, row, sequence):
        self.insertions = 0
        self.add(row)
        if sequence:
            for key, value in row.items():
                self.data[key][sequence % self.capacity] = value
        self.insertions = sequence+1


def joint_input(obs, forecast, z):
    return torch.cat((obs.flatten(1), forecast, z), dim=1)


class MacroSpeed:
    PURPOSE = "engineering_only"

    def __init__(self, parent_ref, forecast_ref, run, arm):
        if arm not in ("B", "C") or run not in (0, 1, 2):
            raise ValueError("known arm and original parent stream required")
        self.identity = dict(parent=deepcopy(parent_ref), forecast=deepcopy(forecast_ref), run=run, arm=arm)
        for ref in (parent_ref, forecast_ref):
            if sha(ref["path"]) != ref["sha256"]:
                raise ValueError("frozen source SHA mismatch")
        with torch.random.fork_rng(devices=[]):
            self.parent, _ = MADDPG.load(parent_ref["path"])
            if (tuple(self.parent.config.action_mask) != (0, 1, 0)
                    or self.parent.config.speed_reference_schedule is None):
                raise ValueError("a scheduled-speed pitch parent is required")
            self.parent.actors.requires_grad_(False)
            self.parent.target_actors.requires_grad_(False)
            torch.manual_seed(seed_for(42, 8601, run))
            self.heads = nn.ModuleList(
                nn.Sequential(nn.Linear(51, 32), nn.ReLU(), nn.Linear(32, 1), nn.Tanh())
                for _ in range(3))
            with torch.no_grad():
                for head in self.heads:
                    head[2].weight.zero_()
                    head[2].bias.zero_()
            torch.manual_seed(seed_for(42, 8602, run))
            self.critics = nn.ModuleList(mlp(84, 64, 1) for _ in range(3))
        self.target_heads = deepcopy(self.heads).requires_grad_(False)
        self.target_critics = deepcopy(self.critics).requires_grad_(False)
        self.head_adam = [torch.optim.Adam(head.parameters(), lr=1e-4) for head in self.heads]
        self.critic_adam = [torch.optim.Adam(critic.parameters(), lr=.001) for critic in self.critics]
        self.replay = MacroReplay(seed_for(42, 8603, run))
        self.noise = np.random.default_rng(np.random.SeedSequence([42, 20261030, 8604, run]))
        self.forecaster = RidgeForecast.load(forecast_ref["path"]) if arm == "C" else None
        self.steps = self.episodes = self.updates = self.draws = 0
        self.active = False
        self.boundary = None

    def features(self, observed):
        return forecast_features(self.forecaster, observed, self.identity["arm"] == "C")

    def offsets(self, obs, forecast, *, target=False):
        models = self.target_heads if target else self.heads
        return torch.cat([model(torch.cat((obs[:, i], forecast), dim=1))
                          for i, model in enumerate(models)], dim=1)

    def z(self, obs, forecast, *, target=False):
        with torch.no_grad():
            return self.offsets(torch.from_numpy(obs[None]), torch.from_numpy(forecast[None]),
                                target=target)[0].numpy()

    @torch.no_grad()
    def targets(self, batch):
        answer = batch["return"].float().clone()
        live = ~batch["terminal"]
        if live.any():
            obs, forecast = batch["next_obs"][live], batch["next_forecast"][live]
            z = self.offsets(obs, forecast, target=True)
            x = joint_input(obs, forecast, z)
            q = torch.cat([net(x) for net in self.target_critics], dim=1)
            answer[live] += batch["discount"][live, None].float()*q
        return answer

    def update(self, before_update):
        if self.replay.size < BATCH:
            raise ValueError("need 64 closed macro samples")
        before_update()
        slots, batch = self.replay.sample()
        target = self.targets(batch)
        obs, forecast, actual = (batch[k] for k in ("obs", "forecast", "z"))
        inputs = joint_input(obs, forecast, actual)
        losses, norms = [], []
        for i, critic in enumerate(self.critics):
            loss = nn.functional.mse_loss(critic(inputs)[:, 0], target[:, i])
            losses.append(float(loss.detach()))
            norms.append(self._optimize(loss, critic, self.critic_adam[i]))
            critic.requires_grad_(False)
            try:
                own = self.heads[i](torch.cat((obs[:, i], forecast), dim=1))
                proposed = torch.cat((actual[:, :i], own, actual[:, i+1:]), dim=1)
                loss = -critic(joint_input(obs, forecast, proposed)).mean()
                losses.append(float(loss.detach()))
                norms.append(self._optimize(loss, self.heads[i], self.head_adam[i]))
            finally:
                critic.requires_grad_(True)
        with torch.no_grad():
            for online, delayed in ((self.heads, self.target_heads), (self.critics, self.target_critics)):
                for parameter, target_parameter in zip(online.parameters(), delayed.parameters()):
                    target_parameter.lerp_(parameter, TAU)
        self.updates += 1
        return dict(slots=slots.tolist(), losses=losses, gradient_norms=norms, update=self.updates)

    @staticmethod
    def _optimize(loss, network, adam):
        if not torch.isfinite(loss):
            raise FloatingPointError("nonfinite macro loss")
        adam.zero_grad(set_to_none=True)
        loss.backward()
        norm = nn.utils.clip_grad_norm_(network.parameters(), 1., error_if_nonfinite=True)
        adam.step()
        return float(norm)

    def state(self):
        if (self.active or self.episodes < 1 or self.steps != HORIZON*self.episodes
                or self.replay.insertions != self.episodes*16 or self.boundary is None):
            raise ValueError("only a complete 128-step episode boundary can be saved")
        return dict(schema=SCHEMA, purpose=self.PURPOSE, identity=self.identity,
                    steps=self.steps, episodes=self.episodes, updates=self.updates, draws=self.draws,
                    boundary=self.boundary, replay=self.replay.state(),
                    torch_rng=torch.get_rng_state(), noise_rng=deepcopy(self.noise.bit_generator.state),
                    networks={name: getattr(self, name).state_dict() for name in (
                        "heads", "critics", "target_heads", "target_critics")},
                    adam={name: [opt.state_dict() for opt in getattr(self, name)]
                          for name in ("head_adam", "critic_adam")})

    def save(self, path, reserve_bytes):
        path = Path(path)
        with io.BytesIO() as buffer:
            torch.save(self.state(), buffer)
            reserve_bytes(len(buffer.getbuffer()))
            with path.open("xb") as stream:
                stream.write(buffer.getbuffer())
                stream.flush()
                import os
                os.fsync(stream.fileno())

    @classmethod
    def load(cls, path, expected_identity, expected_sha):
        if sha(path) != expected_sha:
            raise ValueError("private checkpoint SHA mismatch")
        saved = torch.load(path, map_location="cpu", weights_only=False)
        if (saved.get("schema") != SCHEMA or saved.get("purpose") != cls.PURPOSE
                or saved.get("identity") != expected_identity):
            raise ValueError("private macro checkpoint identity required")
        instance = cls(expected_identity["parent"], expected_identity["forecast"],
                       expected_identity["run"], expected_identity["arm"])
        for name in ("steps", "episodes", "updates", "draws"):
            if type(saved[name]) is not int or saved[name] < 0:
                raise ValueError("invalid checkpoint counter")
            setattr(instance, name, saved[name])
        if (instance.episodes < 1 or instance.steps != instance.episodes*HORIZON
                or instance.draws > instance.episodes*16):
            raise ValueError("checkpoint is not a 128-step boundary")
        instance.replay.restore(saved["replay"], instance.episodes, expected_identity["arm"])
        instance.boundary = saved["boundary"]
        history = instance.boundary["history_tail"]
        last = (instance.replay.position-1) % instance.replay.capacity
        if (instance.boundary["episode"] != instance.episodes-1
                or history.shape != (32, 3) or history.dtype != np.float32
                or not np.isfinite(history).all()
                or instance.boundary["history_sha256"] != instance.replay.data["next_history"][last].tobytes().hex()
                or sha_history(history) != instance.boundary["tail_sha256"]):
            raise ValueError("terminal forecast history mismatch")
        for name in ("heads", "critics", "target_heads", "target_critics"):
            network = getattr(instance, name)
            weights = saved["networks"][name]
            for key, parameter in network.state_dict().items():
                if weights[key].dtype != parameter.dtype or not torch.isfinite(weights[key]).all():
                    raise ValueError("invalid macro network tensor")
            network.load_state_dict(weights, strict=True)
        for name in ("head_adam", "critic_adam"):
            states = saved["adam"][name]
            if len(states) != 3:
                raise ValueError("three Adam states required")
            for opt, state in zip(getattr(instance, name), states):
                restore_adam(opt, state, instance.updates)
        instance.noise.bit_generator.state = deepcopy(saved["noise_rng"])
        torch.set_rng_state(saved["torch_rng"])
        return instance


def restore_adam(adam, saved, updates):
    initial = adam.state_dict()["param_groups"]
    if saved["param_groups"] != initial:
        raise ValueError("Adam group contract mismatch")
    params = adam.param_groups[0]["params"]
    ids = initial[0]["params"]
    if set(saved["state"]) != (set(ids) if updates else set()):
        raise ValueError("Adam state count mismatch")
    for index, parameter in zip(ids, params):
        if not updates:
            break
        state = saved["state"][index]
        if (set(state) != {"step", "exp_avg", "exp_avg_sq"}
                or state["step"].ndim != 0 or state["step"].item() != updates
                or any(state[k].shape != parameter.shape or state[k].dtype != parameter.dtype
                       or not torch.isfinite(state[k]).all() for k in ("exp_avg", "exp_avg_sq"))):
            raise ValueError("Adam moment shape, dtype or clock mismatch")
    adam.load_state_dict(saved)


class Episode:
    """Own one observed-prefix collector and its held correction."""
    def __init__(self, agent, env, obs, info, *, collect=False, explore=False):
        if (agent.active or env.horizon > HORIZON or (collect and env.horizon != HORIZON)
                or (explore and not collect) or env.t != 0 or info["step"] != 0):
            raise ValueError("invalid macro episode start")
        self.agent, self.env = agent, env
        self.collect, self.explore = collect, explore
        self.obs = obs.copy()
        self.observed = [info["wind"].copy()]
        self.features = agent.features(self.observed)
        self.pending = None
        self.last_closed = None
        self.decisions = 0
        self.t = 0
        agent.active = True

    def step(self):
        a = self.agent
        if not a.active or self.env.t != self.t:
            raise ValueError("episode and physical clock disagree")
        if self.pending is None:
            z = a.z(self.obs, self.features)
            if self.explore:
                decay = 1-.8*min(1., a.steps/8192)
                z = np.clip(z + a.noise.normal(0, .15*decay, 3), -1, 1).astype(np.float32)
                a.draws += 1
            self.pending = dict(obs=self.obs, forecast=self.features, z=z,
                history=digest_array(self.observed), raw_reward=np.zeros((8, 3), np.float32),
                episode=np.int64(a.episodes), t=np.uint8(self.t))
            self.decisions += 1
        row = self.pending
        z = row["z"]
        action, parent = command(a.parent, self.obs, .1*z.astype(np.float64))
        nxt, reward, terminal, truncated, info = self.env.step(action)
        if truncated or info["step"] != self.t+1:
            raise ValueError("unexpected physical truncation or clock")
        np.testing.assert_array_equal(info["executed_action"], action)
        np.testing.assert_array_equal(nxt[:, 5:8], action)
        row["raw_reward"][self.t-int(row["t"])] = reward
        self.observed.append(info["wind"].copy())
        self.obs = nxt.copy()
        self.t += 1
        if self.collect:
            a.steps += 1
        if terminal or self.t % INTERVAL == 0:
            m = self.t-int(row["t"])
            self.features = np.zeros(36, np.float32) if terminal else a.features(self.observed)
            row.update(next_obs=self.obs, next_forecast=self.features, m=np.uint8(m),
                       terminal=np.bool_(terminal), next_forecast_valid=np.bool_(not terminal),
                       next_history=digest_array(self.observed))
            row["return"], row["discount"] = discounted(row["raw_reward"][:m], GAMMA)
            if self.collect:
                a.replay.add(row)
            self.last_closed = row
            self.pending = None
        if terminal:
            if self.collect:
                tail = np.asarray(self.observed[-32:], np.float32)
                a.boundary = dict(episode=a.episodes, history_tail=tail,
                                  history_sha256=sha_history(self.observed), tail_sha256=sha_history(tail))
                a.episodes += 1
            a.active = False
        return parent, action, z.copy(), reward, terminal, info


def digest_array(history):
    return np.frombuffer(bytes.fromhex(sha_history(history)), dtype=np.uint8).copy()
