"""Private engineering yaw branch above the frozen C-selected speed mapping."""
from copy import deepcopy

import numpy as np
import torch

from . import forecast_speed_training as source
from .benchmark import seed_for
from .causal_speed_search import command
from .forecast_decision_contract import discounted, forecast_features, sha_history
from .forecast_speed_macro import (
    BATCH, GAMMA, HORIZON, INTERVAL, MacroReplay, MacroSpeed, REPLAY_SCHEMA,
    digest_array, restore_adam,
)

SCHEMA = "frozen_C_yaw_engineering_v1"
YAW_REPLAY = "frozen_C_yaw_macro_replay_v1"
RADIUS = np.pi/180
GROUPS = ("heads", "critics", "target_heads", "target_critics")


class YawReplay(MacroReplay):
    def state(self):
        return super().state() | dict(schema=YAW_REPLAY)

    def restore(self, saved, episodes, arm="C"):
        if saved.get("schema") != YAW_REPLAY:
            raise ValueError("private yaw replay required")
        super().restore(saved | dict(schema=REPLAY_SCHEMA), episodes, arm)


class FrozenCYaw(MacroSpeed):
    PURPOSE = "yaw_engineering_only"

    def __init__(self, identity):
        if identity.get("schema") != SCHEMA or identity.get("step") != (0, 0, 4096)[identity["run"]]:
            raise ValueError("original C selected identity required")
        super().__init__(identity["parent"], identity["forecast"], identity["run"], "C")
        self.speed_heads = deepcopy(self.heads)
        weights = torch.load(source.verify(identity["snapshot"]), map_location="cpu", weights_only=True)
        if (weights["purpose"], weights["arm"], weights["run"], weights["step"], weights["lock_sha"]) != (
                source.PURPOSE, "C", identity["run"], identity["step"], identity["source_lock_sha"]):
            raise ValueError("frozen speed snapshot provenance mismatch")
        self.speed_heads.load_state_dict(weights["weights"], strict=True)
        self.speed_heads.requires_grad_(False)
        for name in ("actors", "target_actors", "critics", "target_critics"):
            getattr(self.parent, name).requires_grad_(False)
        with torch.random.fork_rng(devices=[]):
            for group, stream in ((self.heads, 9031), (self.critics, 9032)):
                torch.manual_seed(seed_for(42, stream, identity["run"]))
                for layer in group.modules():
                    if isinstance(layer, torch.nn.Linear):
                        layer.reset_parameters()
            with torch.no_grad():
                for head in self.heads:
                    head[2].weight.zero_()
                    head[2].bias.zero_()
        self.target_heads = deepcopy(self.heads).requires_grad_(False)
        self.target_critics = deepcopy(self.critics).requires_grad_(False)
        self.replay = YawReplay(seed_for(42, 9033, identity["run"]))
        self.noise = np.random.default_rng(np.random.SeedSequence([42, 20261105, 9034, identity["run"]]))
        self.identity = deepcopy(identity)

    def features(self, observed):
        return forecast_features(self.forecaster, observed, True)

    @torch.no_grad()
    def speed_z(self, obs, forecast):
        x = torch.from_numpy(obs[None])
        f = torch.from_numpy(forecast[None])
        return torch.cat([head(torch.cat((x[:, i], f), dim=1))
                          for i, head in enumerate(self.speed_heads)], dim=1)[0].numpy()

    def compose(self, obs, speed_z, yaw_z, bounds):
        action, pitch_parent = command(self.parent, obs, .1*speed_z.astype(np.float64))
        fixed_C = action.copy()
        lo, hi = bounds
        action[:, 0] = np.clip(action[:, 0] + 2*RADIUS*yaw_z.astype(np.float64)/(hi-lo), -1, 1)
        return action, fixed_C, pitch_parent

    def state(self):
        if (self.active or self.episodes < 1 or self.steps != HORIZON*self.episodes
                or self.replay.insertions != self.episodes*16 or self.boundary is None):
            raise ValueError("yaw checkpoint requires a complete 128-step boundary")
        return dict(schema=SCHEMA, purpose=self.PURPOSE, identity=deepcopy(self.identity),
            **{k: getattr(self, k) for k in ("steps", "episodes", "updates", "draws")},
            boundary=deepcopy(self.boundary), replay=self.replay.state(),
            torch_rng=torch.get_rng_state(), noise_rng=deepcopy(self.noise.bit_generator.state),
            networks={name: getattr(self, name).state_dict() for name in GROUPS},
            adam={name: [opt.state_dict() for opt in getattr(self, name)]
                  for name in ("head_adam", "critic_adam")})

    @classmethod
    def load(cls, path, expected_identity, expected_sha):
        if source.sha(path) != expected_sha:
            raise ValueError("yaw checkpoint SHA mismatch")
        saved = torch.load(path, map_location="cpu", weights_only=False)
        if (saved.get("schema"), saved.get("purpose"), saved.get("identity")) != (
                SCHEMA, cls.PURPOSE, expected_identity):
            raise ValueError("private yaw checkpoint identity required")
        agent = cls(expected_identity)
        for name in ("steps", "episodes", "updates", "draws"):
            if type(saved[name]) is not int or saved[name] < 0:
                raise ValueError("invalid yaw counter")
            setattr(agent, name, saved[name])
        if agent.episodes < 1 or agent.steps != agent.episodes*128 or agent.draws > agent.episodes*16:
            raise ValueError("invalid yaw checkpoint clock")
        agent.replay.restore(saved["replay"], agent.episodes)
        agent.boundary = deepcopy(saved["boundary"])
        b = agent.boundary
        last = (agent.replay.position-1) % agent.replay.capacity
        if (b["t"] != 128 or b["pending"] is not None or b["parent_clock"] != 128
                or b["yaw_clock"] != 128 or b["parent_decisions"] != 16 or b["decisions"] != 16
                or len(b["observed"]) != 129 or b["speed_z"].shape != (3,)
                or digest_array(b["observed"]).tobytes() != agent.replay.data["next_history"][last].tobytes()
                or not np.array_equal(b["obs"], agent.replay.data["next_obs"][last])):
            raise ValueError("yaw checkpoint boundary or history mismatch")
        for name in GROUPS:
            weights = saved["networks"][name]
            for key, value in getattr(agent, name).state_dict().items():
                if weights[key].dtype != value.dtype or not torch.isfinite(weights[key]).all():
                    raise ValueError("invalid yaw network tensor")
            getattr(agent, name).load_state_dict(weights, strict=True)
        for name in ("head_adam", "critic_adam"):
            if len(saved["adam"][name]) != 3:
                raise ValueError("three yaw Adam states required")
            for opt, state in zip(getattr(agent, name), saved["adam"][name], strict=True):
                restore_adam(opt, state, agent.updates)
        agent.noise.bit_generator.state = deepcopy(saved["noise_rng"])
        torch.set_rng_state(saved["torch_rng"])
        return agent


class YawEpisode:
    """One physical collector, with separate frozen-speed and yaw decision clocks."""
    def __init__(self, agent, env, obs, info, *, collect=False, explore=False):
        if (agent.active or env.t != 0 or info["step"] != 0 or env.horizon > HORIZON
                or (collect and env.horizon != HORIZON) or (explore and not collect)
                or not np.all(env.control_mask)):
            raise ValueError("invalid yaw episode entry")
        self.agent, self.env = agent, env
        self.collect, self.explore = collect, explore
        self.obs = obs.copy()
        self.observed = [info["wind"].copy()]
        self.features = agent.features(self.observed)
        self.t = self.parent_clock = self.yaw_clock = 0
        self.decisions = self.parent_decisions = 0
        self.pending = self.last_closed = None
        self.speed_z = np.zeros(3, np.float32)
        agent.active = True

    def step(self, override_z=None):
        a, env = self.agent, self.env
        if not a.active or env.t != self.t or self.parent_clock != self.t or self.yaw_clock != self.t:
            raise ValueError("yaw/parent/physical clock mismatch")
        if self.pending is None:
            if self.t % INTERVAL:
                raise ValueError("lost held yaw interval")
            # Both branches use precisely the same t observation and prefix.
            self.speed_z = a.speed_z(self.obs, self.features)
            z = a.z(self.obs, self.features)
            if self.explore:
                decay = 1-.8*min(1., a.steps/2048)
                z = np.clip(z+a.noise.normal(0, .15*decay, 3), -1, 1).astype(np.float32)
                a.draws += 1
            if override_z is not None:
                z = np.asarray(override_z, np.float32)
                if z.shape != (3,) or not np.isfinite(z).all() or np.any(np.abs(z) > 1):
                    raise ValueError("bounded engineering yaw vector required")
            self.pending = dict(obs=self.obs.copy(), forecast=self.features.copy(), z=z.copy(),
                history=digest_array(self.observed), raw_reward=np.zeros((8, 3), np.float32),
                episode=np.int64(a.episodes), t=np.uint8(self.t))
            self.decisions += 1
            self.parent_decisions += 1
        row = self.pending
        z = row["z"]
        action, fixed_C, pitch = a.compose(self.obs, self.speed_z, z, (env.low[0], env.high[0]))
        nxt, reward, terminal, truncated, info = env.step(action)
        if truncated or info["step"] != self.t+1:
            raise ValueError("unexpected yaw physical truncation")
        np.testing.assert_array_equal(action, info["executed_action"])
        np.testing.assert_array_equal(nxt[:, 5:8], action)
        row["raw_reward"][self.t-int(row["t"])] = reward
        self.observed.append(info["wind"].copy())
        self.obs = nxt.copy()
        self.t += 1
        self.parent_clock += 1
        self.yaw_clock += 1
        if self.collect:
            a.steps += 1
        if terminal or self.t % INTERVAL == 0:
            m = self.t-int(row["t"])
            self.features = np.zeros(36, np.float32) if terminal else a.features(self.observed)
            row.update(next_obs=self.obs.copy(), next_forecast=self.features.copy(), m=np.uint8(m),
                terminal=np.bool_(terminal), next_forecast_valid=np.bool_(not terminal),
                next_history=digest_array(self.observed))
            row["return"], row["discount"] = discounted(row["raw_reward"][:m], GAMMA)
            if self.collect:
                a.replay.add(row)
            self.last_closed = deepcopy(row)
            self.pending = None
        if terminal:
            a.active = False
            if self.collect:
                a.boundary = self.snapshot()
                a.episodes += 1
        return dict(action=action, fixed_C=fixed_C, pitch_parent=pitch, speed_z=self.speed_z.copy(),
                    yaw_z=z.copy(), reward=reward, terminal=terminal, info=info)

    def snapshot(self):
        fields = ("collect", "explore", "obs", "observed", "features", "t", "parent_clock", "yaw_clock",
                  "decisions", "parent_decisions", "pending", "last_closed", "speed_z")
        return deepcopy({key: getattr(self, key) for key in fields})

    @classmethod
    def restore(cls, agent, env, saved):
        t, pending = saved["t"], saved["pending"]
        if (agent.active or t != env.t or len(saved["observed"]) != t+1
                or saved["parent_clock"] != t or saved["yaw_clock"] != t
                or not np.array_equal(saved["obs"], env._observe())
                or not np.array_equal(saved["observed"][-1], env.wind)
                or (pending is None and t % INTERVAL and not env._done)):
            raise ValueError("invalid restored yaw clock or physical observation")
        if pending is not None and (int(pending["t"]) != t-t % INTERVAL
                or not np.array_equal(pending["history"], digest_array(saved["observed"][:int(pending["t"])+1]))
                or np.any(pending["raw_reward"][t-int(pending["t"]):])):
            raise ValueError("invalid restored yaw pending prefix")
        expected = np.zeros(36, np.float32) if env._done else agent.features(
            saved["observed"][:(int(pending["t"])+1) if pending is not None else t+1])
        if not np.array_equal(saved["features"], expected):
            raise ValueError("restored forecast is not the decision prefix")
        episode = object.__new__(cls)
        episode.__dict__ = deepcopy(saved)
        episode.agent, episode.env = agent, env
        agent.active = not env._done
        return episode
