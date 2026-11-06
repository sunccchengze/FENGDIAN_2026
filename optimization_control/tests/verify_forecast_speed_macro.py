"""Bounded, opt-in engineering gate. Run as a module, never through discovery."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime

RUNTIME = Path("./.venv/pinn_tf216")
REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "optimization_control/experiments/20261029_history_independent_test"
REVIEW = REPO / "optimization_control/experiments/20261030_forecast_decision_contract"
ROOT = REPO / "optimization_control/experiments/20261104_forecast_speed_engineering"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def arrays(value):
    import torch
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy()
    if isinstance(value, dict):
        return {k: arrays(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return type(value)(arrays(v) for v in value)
    return value


def equal(a, b):
    from optimization_control.maddpg_wind_farm.forecast_decision_contract import exact_tree
    exact_tree(arrays(a), arrays(b))


def reject(call, reason):
    try:
        call()
    except ValueError as error:
        assert reason in str(error), str(error)
    else:
        raise AssertionError("expected rejection: " + reason)


class Gate:
    def __init__(self, root, attempt):
        from optimization_control.maddpg_wind_farm.forecast_decision_contract import Output
        self.root, self.attempt = root, attempt
        self.output = Output(root)
        self.folder = root / attempt
        self.cfg = read(self.folder / "lock.json")
        self.verify_sources()

    def verify_sources(self):
        from optimization_control.maddpg_wind_farm.anchor_closeout import verify_hashes
        verify_hashes(self.cfg["hashes"])

    def path(self, name):
        return self.folder / name

    def json(self, name, value):
        self.output.json(f"{self.attempt}/{name}", value)

    def scope(self, label, rows, updates):
        from optimization_control.maddpg_wind_farm.causal_speed_search import Budget
        self.rows = Budget(self.root/"model_budget.json", limit=4096)
        self.updates = Budget(self.root/"update_budget.json", limit=24)
        name = f"{self.attempt}/{label}"
        self.rows.start(name, rows)
        self.updates.start(name, updates)

    def finish(self):
        rows, updates = self.rows.finish(), self.updates.finish()
        assert rows["actual"] == rows["reserve"] and updates["actual"] == updates["reserve"]
        return dict(rows=rows, updates=updates)

    def agent(self, arm, run=0):
        from optimization_control.maddpg_wind_farm.forecast_speed_macro import MacroSpeed
        return MacroSpeed(self.cfg["parents"][run], self.cfg["forecast"], run, arm)

    def env(self, kind, horizon):
        from optimization_control.maddpg_wind_farm.causal_speed_search import Meter
        from optimization_control.maddpg_wind_farm.workflow import DEFAULT_CONFIG, build_env, load_config
        cfg = deepcopy(self.cfg["base_config"])
        if kind == "mock":
            cfg["plant"] = load_config(DEFAULT_CONFIG)["plant"]
        cfg["environment"]["horizon"] = horizon
        env = build_env(cfg)
        env.plant.predictor = Meter(env.plant.predictor, self.rows)
        env.plant.predictor.kind = kind
        return env

    def update(self, agent):
        return agent.update(lambda: self.updates.take(1, "joint_engineering_update"))

    def save(self, agent, name):
        from optimization_control.maddpg_wind_farm.forecast_decision_contract import sha
        path = self.path(name)
        agent.save(path, self.reserve)
        return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size, identity=agent.identity)

    def reserve(self, extra):
        used = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
        if used+extra > 256*1024**2:
            raise ValueError("engineering disk cap exceeded")


def prepare(root, attempt):
    import yaml
    from optimization_control.maddpg_wind_farm.forecast_decision_contract import Output, sha
    origin = Path(".")
    prior = yaml.safe_load((SOURCE/"config.yaml").read_text(encoding="utf-8"))
    evidence = read(REVIEW/"attempt_001/verification.json")
    assert evidence["passed"] and evidence["cumulative_mock_rows"] == 427
    cfg = yaml.safe_load((REVIEW/"config.yaml").read_text(encoding="utf-8"))
    parents = [dict(path=x["checkpoint"], sha256=x["sha256"]) for x in prior["parents"]]
    forecast = dict(path=prior["model"], sha256=cfg["protocol"]["forecast_sha256"])
    protected = {x["path"]: x["sha256"] for x in [*parents, forecast]}
    backend = prior["base_config"]["plant"]["backend"]
    protected[str(Path(backend["run_dir"])/"trained.keras")] = backend["model_sha256"]
    protected[backend["script"]] = backend["script_sha256"]
    for tree in (REPO, origin):
        for name in ("PROJECT_STATUS.md", "optimization_control/TASKFLOW.md", "README.md"):
            path = tree/name
            protected[str(path)] = sha(path)
    module = REPO/"optimization_control/maddpg_wind_farm"
    files = [SOURCE/"config.yaml", SOURCE/"complete.json", SOURCE/"release.json",
             REVIEW/"attempt_001/verification.json", Path(__file__)]
    files.extend(module/name for name in (
        "FORECAST_SPEED_ENGINEERING.md", "forecast_speed_macro.py", "forecast_decision_contract.py",
        "algorithm.py", "benchmark.py", "history_wind_forecast.py", "causal_speed_search.py", "workflow.py",
        "configs/default.yaml"))
    files.extend(REPO/"optimization_control"/name for name in (
        "environments/maddpg_farm_env.py", "environments/wind_pinn_backend.py",
        "utils/actuator_model.py", "utils/action_mapper.py", "utils/reference_schedule.py"))
    protected.update({str(path): sha(path) for path in files})
    if (root/"complete.json").exists():
        raise ValueError("engineering gate already complete")
    (root/attempt).mkdir(parents=True, exist_ok=False)
    store = Output(root)
    store.json(f"{attempt}/lock.json", dict(seed=42, parents=parents, forecast=forecast, hashes=protected,
               base_config={key: prior["base_config"][key] for key in ("plant", "environment")}))
    if not (root/"config.yaml").exists():
        store.write("config.yaml", yaml.safe_dump(dict(seed=42, stage="engineering_only", formal_RL_steps=0,
            new_independent_winds=0, mock_rows_planned=1548, real_PINN_rows_planned=180,
            joint_updates_planned=6, model_row_hard_cap=4096, joint_update_hard_cap=24,
            disk_cap_bytes=256*1024**2, first_attempt=attempt, parent_refs=parents, forecast_ref=forecast,
            resume_at_step=512, full_episode_steps=128, short_episode_steps=19,
            wind_formula="U=9+.0015*t+.06*sin(t/3+e/5), direction=.0003*t, TI=.08",
            engineering_target_w=3200000, pitch_rad=.04), sort_keys=False, allow_unicode=True).encode())


def reset(env, index):
    import numpy as np
    t = np.arange(env.horizon+1)
    wind = np.column_stack((9+.0015*t+.06*np.sin(t/3+index/5), .0003*t, np.full(t.shape, .08)))
    assert env.initial[1] == .04
    return env.reset(seed=42, options=dict(wind_trajectory=wind.astype(np.float32), target_w=3.2e6))


def rollout(agent, env, index, *, collect=False):
    import numpy as np
    from optimization_control.maddpg_wind_farm.forecast_speed_macro import Episode, GAMMA, digest_array
    obs, info = reset(env, index)
    episode = Episode(agent, env, obs, info, collect=collect, explore=collect)
    before_draws = agent.draws
    prefix, trace, raw_rewards = [info["wind"].copy()], [], []
    before_action = obs[:, 5:8].copy()
    costs = []
    calls = 0
    with patch.object(agent, "z", wraps=agent.z) as head_calls:
        for t in range(env.horizon):
            forecast = agent.features(prefix) if t % 8 == 0 else None
            if t == 0 and collect:
                reject(agent.state, "128-step episode boundary")
            baseline, action, z, reward, terminal, info = episode.step()
            if t % 8 == 0:
                held = z.copy()
                raw_rewards = []
                first_forecast = forecast
                history = digest_array(prefix)
                calls += 1
            np.testing.assert_array_equal(z, held)
            assert head_calls.call_count == calls
            assert agent.draws == before_draws+(calls if collect else 0)
            action_mse = float(np.mean((action-before_action)**2))
            assert action_mse == info["action_change"]
            previous_error = info["error_w"]/env.rated.sum()
            expected = env.config["reward_scale"]*(-previous_error**2-env.config["action_change_weight"]*action_mse)
            np.testing.assert_array_equal(reward, np.full(3, expected, np.float32))
            before_action = action.copy()
            prefix.append(info["wind"].copy())
            raw_rewards.append(reward.copy())
            costs.append(action_mse)
            trace.append(dict(parent=baseline.tolist(), action=action.tolist(), z=z.tolist(), reward=reward.tolist(),
                              wind=info["wind"].tolist(), obs=episode.obs.tolist(),
                              applied=info["applied"].tolist(), heading=info["heading_rad"].tolist(),
                              power=info["power_w"].tolist(), mse=action_mse))
            if terminal or (t+1) % 8 == 0:
                row = episode.last_closed
                m = len(raw_rewards)
                np.testing.assert_array_equal(row["raw_reward"][:m], raw_rewards)
                np.testing.assert_array_equal(row["forecast"], first_forecast)
                np.testing.assert_array_equal(row["history"], history)
                np.testing.assert_array_equal(row["next_history"], digest_array(prefix))
                np.testing.assert_array_equal(row["next_forecast"],
                    np.zeros(36, np.float32) if terminal else agent.features(prefix))
                result = sum((GAMMA**k)*r.astype(np.float64) for k, r in enumerate(raw_rewards))
                np.testing.assert_allclose(row["return"], result, rtol=0, atol=1e-12)
                assert row["m"] == m and row["discount"] == GAMMA**m
                assert row["terminal"] == terminal and row["next_forecast_valid"] != terminal
    assert not agent.active and len(episode.observed) == env.horizon+1
    return dict(trace=trace, decisions=calls, sum_motion_mse=sum(costs), last_m=int(episode.last_closed["m"]))


def paired(b, c):
    from optimization_control.maddpg_wind_farm.forecast_decision_contract import model_digest
    for name in ("heads", "critics", "target_heads", "target_critics"):
        equal(getattr(b, name).state_dict(), getattr(c, name).state_dict())
    assert model_digest(b.parent) == model_digest(c.parent)
    equal(b.replay.state(), c.replay.state())
    equal(b.noise.bit_generator.state, c.noise.bit_generator.state)
    assert b.replay.size == c.replay.size == 0
    for agent in (b, c):
        assert all(not opt.state for opt in [*agent.head_adam, *agent.critic_adam])


def pure_checks(agent):
    import numpy as np
    import torch
    from optimization_control.maddpg_wind_farm.forecast_speed_macro import MacroReplay, restore_adam
    from optimization_control.maddpg_wind_farm.history_speed_search import Persistence
    # Current clipped commands can alias while held actions remain different.
    z = np.array([.5, 1.])
    assert np.all(np.clip(.95+2*.1*z/.667, -1, 1) == 1)
    assert np.diff(np.clip(.4+2*.1*z/.667, -1, 1))[0] > .14
    assert abs((1+.99)*(-.001*100*(3*.3**2/9))+.00597) < 1e-12
    replay = MacroReplay(42, capacity=19)
    for slot in agent.replay.order():
        replay.add({k: v[slot] for k, v in agent.replay.data.items()})
    state = replay.state()
    restored = MacroReplay(43, capacity=19)
    restored.restore(state, agent.episodes, agent.identity["arm"])
    equal(restored.state(), state)
    np.testing.assert_array_equal(restored.data["t"][restored.order()], replay.data["t"][replay.order()])
    old = replay.data["t"][replay.order()].tolist()
    assert old[0] == 104 and old[-1] == 120 and replay.position == 7
    with patch.object(agent, "offsets", side_effect=AssertionError("terminal evaluated a target")):
        result = agent.targets(dict(terminal=torch.tensor([True]), return_=None,
                                   **{"return": torch.tensor([[1., 2., 3.]])}))
    torch.testing.assert_close(result, torch.tensor([[1., 2., 3.]]), rtol=0, atol=0)
    opt = agent.head_adam[0]
    bad = deepcopy(opt.state_dict())
    bad["state"][0]["exp_avg"] = torch.zeros(1)
    reject(lambda: restore_adam(opt, bad, agent.updates), "Adam moment shape")
    if agent.identity["arm"] == "C":
        # Forecast receives only the observed slice, even if hidden suffix changes.
        one = np.tile(np.array([9., .01, .08], np.float32), (20, 1))
        other = one.copy()
        other[9:, 0] += 1.
        np.testing.assert_array_equal(agent.features(one[:9]), agent.features(other[:9]))
        assert np.any(agent.features(one[:9]))
        assert Persistence().predict(one[:9])[0].shape == (12, 3)
    return dict(ring_capacity=19, retained=19, insertions=replay.insertions, wrap_position=replay.position,
                first_retained_t=old[0], last_retained_t=old[-1], terminal_skip=True, invalid_Adam_rejected=True)


def resume(gate, arm):
    import torch
    from optimization_control.maddpg_wind_farm.forecast_speed_macro import MacroSpeed
    gate.scope(f"{arm}_disk_resume", 129, 1)
    entry = read(gate.path(f"{arm}_boundary.json"))
    torch.manual_seed(98765)
    agent = MacroSpeed.load(entry["path"], entry["identity"], entry["sha256"])
    saved = torch.load(entry["path"], map_location="cpu", weights_only=False)
    equal(agent.state(), saved)
    assert agent.episodes == 4 and agent.steps == 512 and agent.draws == 64
    result = rollout(agent, gate.env("mock", 128), agent.episodes, collect=True)
    update = gate.update(agent)
    state = gate.save(agent, f"{arm}_disk_after.pth")
    gate.json(f"{arm}_disk.json", dict(pid=os.getpid(), starting_state_exact=True, result=result,
              update=update, state=state, accounting=gate.finish()))


def mock_gate(gate):
    import torch
    from optimization_control.maddpg_wind_farm.forecast_decision_contract import model_digest
    from optimization_control.maddpg_wind_farm.forecast_speed_macro import MacroSpeed
    b, c = gate.agent("B"), gate.agent("C")
    paired(b, c)
    outputs = []
    for arm, agent in (("B", b), ("C", c)):
        parent_digest = model_digest(agent.parent)
        entry = agent.identity["parent"]
        reject(lambda: MacroSpeed.load(entry["path"], agent.identity, entry["sha256"]),
               "private macro checkpoint identity")
        gate.scope(f"{arm}_first_boundary", 516, 1)
        env = gate.env("mock", 128)
        for index in range(4):
            result = rollout(agent, env, index, collect=True)
            assert result["decisions"] == 16 and result["last_m"] == 8
        first = gate.update(agent)
        assert any(parameter.abs().max() > 0 for head in agent.heads for parameter in head[2].parameters())
        pure = pure_checks(agent)
        state = gate.save(agent, f"{arm}_boundary.pth")
        gate.json(f"{arm}_boundary.json", state)
        gate.finish()
        gate.scope(f"{arm}_continuous", 129, 1)
        continuous = rollout(agent, gate.env("mock", 128), agent.episodes, collect=True)
        next_update = gate.update(agent)
        gate.finish()
        child = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m",
            "optimization_control.tests.verify_forecast_speed_macro", "resume",
            "--attempt", gate.attempt, "--arm", arm], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
        gate.output.write(f"{gate.attempt}/{arm}_child.log", (child.stdout+child.stderr).encode())
        child.check_returncode()
        disk = read(gate.path(f"{arm}_disk.json"))
        assert disk["pid"] != os.getpid()
        equal(disk["result"], continuous)
        equal(disk["update"], next_update)
        restored = torch.load(disk["state"]["path"], map_location="cpu", weights_only=False)
        equal(restored, agent.state())
        assert model_digest(agent.parent) == parent_digest and agent.parent.actors[0][0].weight.grad is None
        outputs.append(dict(arm=arm, boundary=state, first_update=first, next_update=next_update,
                            child_pid=disk["pid"], parent_pid=os.getpid(), disk_state_exact=True,
                            next_trajectory_exact=True, parent_weights_frozen=True, pure_checks=pure))
    gate.json("mock_verification.json", outputs)


def real_gate(gate):
    import numpy as np
    from optimization_control.maddpg_wind_farm.causal_speed_search import command
    gate.scope("real_takeover", 180, 0)
    env = gate.env("pinn", 19)
    results = []
    for run in range(3):
        b, c = gate.agent("B", run), gate.agent("C", run)
        paired(b, c)
        obs, info = reset(env, 0)
        prefix, reference = [info["wind"].copy()], []
        for t in range(19):
            direct = b.parent.act(obs)
            for agent in (b, c):
                forecast = agent.features(prefix)
                for target in (False, True):
                    z = agent.z(obs, forecast, target=target)
                    np.testing.assert_array_equal(z, np.zeros(3, np.float32))
                    np.testing.assert_array_equal(command(agent.parent, obs, .1*z)[0], direct)
            obs, _, _, _, info = env.step(direct)
            prefix.append(info["wind"].copy())
            reference.append(dict(action=direct, obs=obs, applied=info["applied"], power=info["power_w"]))
        for arm, agent in (("B", b), ("C", c)):
            result = rollout(agent, env, 0)
            assert result["decisions"] == 3 and result["last_m"] == 3
            values = {}
            for key in ("action", "obs", "applied", "power"):
                values[key] = max(float(np.max(np.abs(x[key]-np.asarray(y[key]))))
                                  for x, y in zip(reference, result["trace"]))
            target = 3.2e6
            rmse = [np.sqrt(np.mean([(np.sum(x["power"], dtype=np.float32)-target)**2 for x in trace]))
                    for trace in (reference, result["trace"])]
            assert values["action"] <= 2e-6 and values["applied"] <= 1e-6 and values["power"] <= 1
            assert abs(rmse[0]-rmse[1]) <= 1
            results.append(dict(run=run, arm=arm, max_differences=values, rmse_diff_w=float(abs(rmse[0]-rmse[1])),
                                rmse_w=float(rmse[1]), short_m=3, zero_online_target=True))
            gate.json(f"real_run{run}_{arm}.json", result)
    gate.json("real_verification.json", dict(cases=results, accounting=gate.finish()))


def finish(gate):
    from optimization_control.maddpg_wind_farm.forecast_speed_macro import SPECS
    import numpy as np
    gate.verify_sources()
    budgets = {k: read(gate.root/f"{k}_budget.json")["scopes"] for k in ("model", "update")}
    totals = {k: sum(s["actual"] if s["status"] == "complete" else s["reserve"] for s in scopes)
              for k, scopes in budgets.items()}
    mock = read(gate.path("mock_verification.json"))
    real = read(gate.path("real_verification.json"))
    row_bytes = sum(int(np.prod(shape))*np.dtype(dtype).itemsize for shape, dtype in SPECS.values())
    size = dict(macro_bytes_per_row=row_bytes, old_A_replay_raw_max=32768*103*4,
                parent_checkpoint_bytes=[Path(x["path"]).stat().st_size for x in gate.cfg["parents"]],
                old_speed_final_checkpoint_bytes=sorted(p.stat().st_size for p in
                    (REPO/"optimization_control/experiments/20261029_speed_nstep_control/formal").rglob("step_00008192.pth")),
                actual_B_C_512_state_bytes=[x["boundary"]["bytes"] for x in mock],
                macro_1024_replay_raw_bytes=1024*row_bytes,
                formal_training_steps=73728, formal_query_reserve=129355,
                formal_disk_MiB=dict(A_full=168, B_C_full=36, inference=11.25, eval_trace=26, other=12))
    assert row_bytes == 864 and sum(size["formal_disk_MiB"].values()) == 253.25
    gate.json("storage.json", size)
    gate.output.csv("metrics.csv", [
        dict(check="mock_boundary_resume", cases=2, rows=1548, updates=6, passed=True),
        dict(check="real_zero_takeover", cases=len(real["cases"]), rows=180, updates=0, passed=True),
        dict(check="cumulative_charged", cases=0, rows=totals["model"], updates=totals["update"], passed=True),
    ])
    gate.output.write("summary.txt", (
        f"Engineering gate passed, seed=42, {gate.attempt}. Current 1548 mock + 180 real rows, 6 engineering updates.\n"
        f"Cumulative conservative charge: {totals['model']}/4096 rows, {totals['update']}/24 joint updates.\n"
        "Formal RL steps=0, independent tests=0, yaw=0. Disk resume exact for B and C.\n"
    ).encode())
    gate.output.json("complete.json", dict(attempt=gate.attempt, passed=True, totals=totals,
        formal_RL_steps=0, new_independent_winds=0, source_hashes_verified=True, engineering_states_only=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "resume"))
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--arm", choices=("B", "C"))
    args = parser.parse_args()
    if len(args.attempt) != 11 or not args.attempt.startswith("attempt_") or not args.attempt[-3:].isdigit():
        raise ValueError("attempt_NNN required")
    activate_runtime(RUNTIME)
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(42)
    if args.mode == "resume":
        resume(Gate(ROOT, args.attempt), args.arm)
    else:
        prepare(ROOT, args.attempt)
        gate = Gate(ROOT, args.attempt)
        mock_gate(gate)
        real_gate(gate)
        finish(gate)


if __name__ == "__main__":
    main()
