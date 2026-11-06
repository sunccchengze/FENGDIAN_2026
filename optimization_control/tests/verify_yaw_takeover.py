"""Opt-in bounded engineering acceptance. No formal training or new test release."""
import argparse
from copy import deepcopy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from optimization_control.maddpg_wind_farm import forecast_speed_training as formal

REPO = formal.REPO
ROOT = formal.EXPS/"20261105_yaw_engineering"
MODULE = REPO/"optimization_control/maddpg_wind_farm"
PROTOCOL = MODULE/"YAW_ENGINEERING_PROTOCOL.md"
BASE = "c6a27774ec7cd34113ed7e37b47947b279fef86a"
CAP = 128*1024**2


def equal(actual, expected):
    from optimization_control.tests.verify_forecast_speed_macro import arrays
    from optimization_control.maddpg_wind_farm.forecast_decision_contract import exact_tree
    exact_tree(arrays(actual), arrays(expected))


def reject(call, text):
    try:
        call()
    except ValueError as error:
        assert text in str(error), str(error)
    else:
        raise AssertionError("expected rejection " + text)


def context():
    lock = formal.read(ROOT/"lock.json")
    for path, digest in lock["hashes"].items():
        formal.verify(dict(path=path, sha256=digest))
    return lock


def prepare():
    import yaml
    from optimization_control.maddpg_wind_farm.yaw_macro import SCHEMA
    assert formal.git("rev-parse", "HEAD").decode().strip() == BASE
    source = formal.context()
    selected = formal.read(formal.ROOT/"selection.json")
    jobs = [next(j for j in selected["jobs"] if j["arm"] == "C" and j["run"] == run)
            for run in range(3)]
    assert [j["selected"]["step"] for j in jobs] == [0, 0, 4096]
    identities = [dict(schema=SCHEMA, parent=source["parents"][j["run"]], forecast=source["forecast"],
        run=j["run"], step=j["selected"]["step"], snapshot=j["selected"]["snapshot"],
        source_lock_sha=formal.sha(formal.ROOT/"lock.json")) for j in jobs]
    hashes = deepcopy(source["hashes"])
    files = [PROTOCOL, Path(__file__), MODULE/"yaw_macro.py", MODULE/"forecast_speed_macro.py",
             MODULE/"forecast_speed_training.py", MODULE/"YAW_SOFTWARE_PILOT_PROPOSAL.md",
             formal.ROOT/"selection.json", MODULE/"FORECAST_SPEED_USER_TEST_RESULTS.md",
             formal.EXPS/"20261105_forecast_speed_independent/metrics.csv"]
    for identity in identities:
        files.append(formal.verify(identity["snapshot"]))
    for bank in source["banks"].values():
        files.append(formal.verify(bank))
    hashes.update({str(p): formal.sha(p) for p in files})
    # Also protect current state documents of the separate pitch worktree.
    for tree in (REPO, formal.ORIGIN, formal.PITCH):
        for name in ("PROJECT_STATUS.md", "optimization_control/TASKFLOW.md", "README.md"):
            path = tree/name
            hashes[str(path)] = formal.sha(path)
    ROOT.mkdir(exist_ok=False)
    store = formal.Store(ROOT, CAP)
    plan = dict(seed=42, source_commit=BASE, stage="engineering_only", formal_RL_steps=0,
        new_independent_winds=0, row_hard_cap=4096, disk_cap_bytes=CAP, update_hard_cap=12,
        real_zero_rows=2322, real_nonzero_rows=258, mock_boundary_rows=774, mock_short_rows=45,
        planned_rows=3399, planned_updates=3, old_validation_indices=[0, 2, 4],
        nonzero_validation_index=0, identities=identities,
        action_atol=2e-6, applied_atol=1e-6, power_atol_w=1., rmse_atol_w=1.,
        yaw_radius_rad=math.pi/180, yaw_interval_s=8, parent_speed_interval_s=8,
        parent_pitch_interval_s=1, actual_m_gamma=.99,
        mock_formula="U=9+.0015*t+.06*sin(t/3+episode/5), direction=.0003*t, TI=.08",
        short_resume_steps=[5, 8], short_horizon=19, full_resume_step=512)
    ref = store.write("config.yaml", yaml.safe_dump(plan, allow_unicode=True, sort_keys=False).encode())
    hashes[ref["path"]] = ref["sha256"]
    store.json("lock.json", dict(seed=42, hashes=hashes, identities=identities, source=source, plan=plan))
    print("Locked yaw engineering, 3399 planned rows, no forwards.", flush=True)


class RecordingMeter:
    def __init__(self, predictor, budget, kind):
        self.predictor, self.budget, self.kind = predictor, budget, kind
        self.inputs = []

    def __call__(self, x):
        self.budget.take(len(x), self.kind)
        self.inputs.append(x.copy())
        return self.predictor(x)


class Gate:
    def __init__(self):
        self.lock = context()
        self.store = formal.Store(ROOT, CAP)
        self.world = None

    def agent(self, run=2):
        from optimization_control.maddpg_wind_farm.yaw_macro import FrozenCYaw
        return FrozenCYaw(self.lock["identities"][run])

    def scope(self, label, rows, updates=0):
        from optimization_control.maddpg_wind_farm.causal_speed_search import Budget
        self.rows = Budget(ROOT/"model_budget.json", 4096)
        self.updates = Budget(ROOT/"update_budget.json", 12)
        self.rows.start(label, rows)
        self.updates.start(label, updates)

    def finish(self):
        rows, updates = self.rows.finish(), self.updates.finish()
        assert rows["actual"] == rows["reserve"] and updates["actual"] == updates["reserve"]
        return dict(rows=rows, updates=updates)

    def env(self, *, real, horizon=128, direct=False):
        from optimization_control.maddpg_wind_farm.workflow import build_env, load_config, DEFAULT_CONFIG
        from optimization_control.environments.maddpg_farm_env import MADDPGFarmEnv
        cfg = deepcopy(self.lock["source"]["base_config"])
        cfg["environment"]["control_mask"] = [int(not direct), 1, 1]
        cfg["environment"]["horizon"] = horizon
        if real:
            if self.world is None:
                self.world = formal.World(self.lock["source"])
            plant, predictor = self.world.plant, self.world.predictor
        else:
            cfg["plant"] = load_config(DEFAULT_CONFIG)["plant"]
            plant = build_env(cfg).plant
            predictor = plant.predictor
        plant.predictor = RecordingMeter(predictor, getattr(self, "rows", None), "PINN" if real else "mock")
        return MADDPGFarmEnv(plant, cfg["environment"])

    def save(self, name, value, limit=8*1024**2):
        return self.store.torch(name, value, limit)

    def update(self, agent):
        return agent.update(lambda: self.updates.take(1, "yaw_joint_engineering"))


def frozen_digest(agent):
    from optimization_control.maddpg_wind_farm.forecast_decision_contract import model_digest
    h = hashlib.sha256(model_digest(agent.parent).encode())
    for value in agent.speed_heads.state_dict().values():
        h.update(value.numpy().tobytes())
    return h.hexdigest()


def mock_case(index=0, horizon=128):
    import numpy as np
    t = np.arange(horizon+1)
    wind = np.column_stack((9+.0015*t+.06*np.sin(t/3+index/5), .0003*t, np.full(t.shape, .08)))
    return dict(id=f"mock_{index}", family="mock", split="engineering", target_w=3.2e6,
                pitch_rad=.04), wind.astype(np.float32)


def rollout(agent, env, case, wind, *, direct=False, collect=False, fixed_z=None, zero_check=False):
    import numpy as np
    from optimization_control.maddpg_wind_farm.forecast_speed_macro import Episode
    from optimization_control.maddpg_wind_farm.yaw_macro import YawEpisode
    obs, info = formal.reset(env, case, wind)
    episode = (Episode(agent, env, obs, info) if direct else
               YawEpisode(agent, env, obs, info, collect=collect, explore=collect))
    rows = [formal.trace_row(info, info["executed_action"], np.zeros(3), 0)]
    observations, rewards, speed, yaw, macros = [obs.copy()], [], [], [], []
    for _ in range(env.horizon):
        if direct:
            parent, action, z, reward, terminal, info = episode.step()
            sy, yz = z, np.zeros(3, np.float32)
        else:
            if zero_check:
                for target in (False, True):
                    np.testing.assert_array_equal(agent.z(episode.obs, episode.features, target=target),
                                                  np.zeros(3, np.float32))
            item = episode.step(override_z=fixed_z)
            action, parent, sy, yz, reward, terminal, info = [item[k] for k in (
                "action", "pitch_parent", "speed_z", "yaw_z", "reward", "terminal", "info")]
            if zero_check:
                np.testing.assert_array_equal(action, item["fixed_C"])
            # Independent total-command reward oracle, evaluated before float32 storage.
            error = (np.sum(info["power_w"], dtype=np.float32)-info["target_w"])/env.rated.sum()
            expected = env.config.get("reward_scale", 1.)*(-float(error**2)
                       -env.config["action_change_weight"]*info["action_change"])
            np.testing.assert_array_equal(reward, np.full(3, expected, np.float32))
            if episode.pending is None:
                m = int(episode.last_closed["m"])
                row = deepcopy(episode.last_closed)
                oracle = np.array([math.fsum(float(r[i])*.99**k for k, r in enumerate(row["raw_reward"][:m]))
                                   for i in range(3)])
                np.testing.assert_allclose(row["return"], oracle, atol=1e-12, rtol=0)
                macros.append(row)
        assert terminal == (env.t == env.horizon)
        rows.append(formal.trace_row(info, parent, sy, reward[0]))
        observations.append(env._observe())
        rewards.append(reward)
        speed.append(sy.copy())
        yaw.append(yz.copy())
    assert len(episode.observed) == env.horizon+1
    result = dict(trace=np.asarray(rows, np.float64), obs=np.stack(observations),
        rewards=np.stack(rewards), speed=np.stack(speed), yaw=np.stack(yaw),
        inputs=np.concatenate(env.plant.predictor.inputs), decisions=episode.decisions,
        prefix_sha=hashlib.sha256(np.asarray(episode.observed, np.float32).tobytes()).hexdigest(), macros=macros)
    if not direct:
        result["controller"] = episode.snapshot()
    return result


def pure_checks(gate):
    import numpy as np
    import torch
    from optimization_control.environments.wind_pinn_backend import team_inputs
    from optimization_control.environments.maddpg_farm_env import wrap_angle
    from optimization_control.maddpg_wind_farm.yaw_macro import FrozenCYaw, RADIUS, YawReplay
    from optimization_control.maddpg_wind_farm.forecast_speed_macro import MacroSpeed
    physical = np.array([[9., .1, .08, -.03, .02, .01, .04, .07, .09, .8, .9, 1.1]])
    expected = np.array([[9., .1, .08, -.03, .04, .8, .02, .07, .9, .01, .09, 1.1]])
    np.testing.assert_allclose(team_inputs(physical), expected, atol=5e-16, rtol=0)
    cases = []
    # Pure actuator arithmetic, deliberately no model forward for wrapped angles.
    env = gate.env(real=False, horizon=19)
    names = env.actuator_commands
    for heading, direction, z in ((2*np.pi-.001, .001, 1), (.001, 2*np.pi-.001, -1),
                                   (0., 0., 1), (0., 0., -1)):
        initial = dict(zip(env.actuator_applied, (np.full(3, heading), np.full(3, .04), np.full(3, .9))))
        env.actuator.reset(initial)
        delta = float(wrap_angle(direction+z*RADIUS-heading))
        result = env.actuator.step(dict(zip(names, (np.full(3, heading+delta), np.full(3, .04), np.full(3, .9)))))
        actual = result.applied_control[env.actuator_applied[0]]-heading
        expected_delta = np.clip((1-np.exp(-1/5))*delta, -.005, .005)
        np.testing.assert_allclose(actual, expected_delta, atol=1e-15, rtol=0)
        assert np.all(np.abs(actual) <= .005+1e-15) and np.all(np.sign(actual) == np.sign(delta))
        cases.append(dict(heading=heading, direction=direction, yaw_rad=z*RADIUS,
                          shortest_delta=delta, actual_delta=float(actual[0])))
    # Force the actual .005 limiter to bind in the pure actuator domain.
    env.actuator.reset(initial)
    old = env.actuator.applied_control[env.actuator_applied[0]].copy()
    limits = env.actuator.step(dict(zip(names, (old+.1, np.full(3, .04), np.full(3, .9)))))
    np.testing.assert_allclose(limits.applied_control[env.actuator_applied[0]]-old, .005, atol=1e-15, rtol=0)
    agent = gate.agent()
    reject(lambda: FrozenCYaw.load(agent.identity["snapshot"]["path"], agent.identity,
                                   agent.identity["snapshot"]["sha256"]), "private yaw")
    with torch.no_grad():
        for net in agent.target_critics:
            for p in net.parameters():
                p.fill_(float("nan"))
    terminal = dict(terminal=torch.tensor([True]), **{"return": torch.tensor([[1., 2., 3.]])})
    torch.testing.assert_close(agent.targets(terminal), terminal["return"], rtol=0, atol=0)
    reject(lambda: YawReplay(42).restore(dict(schema="forecast_speed_macro_replay_v1"), 1), "private yaw")
    zero = np.zeros((3, 15), np.float32)
    zero[:, 14] = 1
    feat = np.zeros(36, np.float32)
    prefixes = np.tile(np.array([9., .1, .08], np.float32), (20, 1))
    other = prefixes.copy(); other[9:, 0] += 1
    np.testing.assert_array_equal(agent.features(prefixes[:9]), agent.features(other[:9]))
    for run in range(3):
        a = gate.agent(run)
        assert a.replay.size == 0 and a.steps == a.updates == a.draws == 0
        assert all(not opt.state for opt in (*a.head_adam, *a.critic_adam))
        for target in (False, True):
            np.testing.assert_array_equal(a.z(zero, feat, target=target), np.zeros(3, np.float32))
    gate.store.json("pure.json", dict(SI_three_markers=True, angle_cases=cases, rate_limit_bound=True,
        private_schema_rejection=True, terminal_bootstrap_skipped=True, prefix_causal=True,
        all_three_empty_zero=True, rows=0, updates=0))


def real_zero(gate):
    import numpy as np
    from optimization_control.maddpg_wind_farm.forecast_decision_contract import model_digest
    gate.scope("real_zero", 2322)
    cases = formal.bank(gate.lock["source"], "validation")
    results = []
    for run in range(3):
        agent = gate.agent(run)
        frozen = frozen_digest(agent)
        for index in (0, 2, 4):
            case, wind = cases[index]
            identity = agent.identity
            direct = formal.inference(gate.lock["source"], identity["snapshot"], "C", run, identity["step"])
            before = model_digest(direct.parent)
            reference = rollout(direct, gate.env(real=True, direct=True), case, wind, direct=True)
            actual = rollout(agent, gate.env(real=True), case, wind, zero_check=True)
            diffs = {}
            for key in ("trace", "obs", "rewards", "speed", "inputs"):
                diffs[key] = float(np.max(np.abs(actual[key]-reference[key])))
                np.testing.assert_array_equal(actual[key], reference[key])
            assert actual["decisions"] == reference["decisions"] == 16
            assert actual["prefix_sha"] == reference["prefix_sha"]
            assert frozen_digest(agent) == frozen and model_digest(direct.parent) == before
            metrics = formal.metric(actual["trace"], case)
            ref = gate.save(f"real_zero/run{run}_case{index}.pt", dict(reference=reference, actual=actual))
            results.append(dict(run=run, case=case["id"], original_step=identity["step"],
                max_differences=diffs, rmse_w=metrics["rmse_w"], artifact=ref,
                online_target_zero=True, full_trajectory_exact=True))
            print(f"zero C{run} {case['family']} exact", flush=True)
    gate.store.json("real_zero.json", dict(cases=results, accounting=gate.finish()))


def real_nonzero(gate):
    import numpy as np
    from optimization_control.maddpg_wind_farm.yaw_macro import RADIUS
    gate.scope("real_nonzero", 258)
    case, wind = formal.bank(gate.lock["source"], "validation")[0]
    original = torch_load(formal.read(ROOT/"real_zero.json")["cases"][6]["artifact"])["actual"]
    results = []
    for sign in (1, -1):
        agent = gate.agent()
        frozen = frozen_digest(agent)
        env = gate.env(real=True)
        result = rollout(agent, env, case, wind, fixed_z=np.full(3, sign, np.float32))
        trace = result["trace"]
        heading_delta = trace[:, 16:19]-original["trace"][:, 16:19]
        gamma_delta = result["inputs"][:, 3:6]-original["inputs"][:, 3:6]
        assert np.max(np.abs(heading_delta)) > 1e-4 and np.max(np.abs(gamma_delta)) > 1e-4
        assert np.all(np.sign(heading_delta[1]) == sign)
        # Physical feature order is [wind, direction, TI, gamma1..3, pitch1..3, speed1..3].
        np.testing.assert_allclose(result["inputs"][:, 3:6], trace[:, 19:28].reshape(129, 3, 3)[:, :, 0],
                                   atol=1e-7, rtol=0)
        yaw_change = (trace[1:, 28:37].reshape(128, 3, 3)[:, :, 0]
                      -original["trace"][1:, 28:37].reshape(128, 3, 3)[:, :, 0])
        np.testing.assert_allclose(yaw_change*(env.high[0]-env.low[0])/2,
                                   sign*RADIUS, atol=2e-9, rtol=0)
        metric = formal.metric(trace, case)
        assert frozen_digest(agent) == frozen and agent.updates == 0
        artifact = gate.save(f"real_nonzero/sign{sign}.pt", result)
        results.append(dict(sign=sign, artifact=artifact, max_heading_delta_rad=float(np.max(np.abs(heading_delta))),
            max_PINN_gamma_delta_rad=float(np.max(np.abs(gamma_delta))), metrics=metric,
            RMSE_delta_w=metric["rmse_w"]-formal.metric(original["trace"], case)["rmse_w"]))
    gate.store.json("real_nonzero.json", dict(cases=results, accounting=gate.finish(), selected_using_this=False))


def torch_load(ref):
    import torch
    return torch.load(formal.verify(ref), map_location="cpu", weights_only=False)


def mock_boundary(gate):
    import numpy as np
    import torch
    from optimization_control.maddpg_wind_farm.forecast_speed_macro import MacroSpeed
    from optimization_control.maddpg_wind_farm.yaw_macro import FrozenCYaw
    agent = gate.agent()
    frozen = frozen_digest(agent)
    gate.scope("mock_first_four", 516, 1)
    for index in range(4):
        case, wind = mock_case(index)
        result = rollout(agent, gate.env(real=False), case, wind, collect=True)
        assert np.max(np.abs(result["speed"])) > 0 and np.max(np.abs(result["yaw"])) > 0
    first_update = gate.update(agent)
    assert any(torch.count_nonzero(head[2].weight) for head in agent.heads)
    boundary = gate.save("mock_boundary/state.pt", agent.state())
    gate.store.json("mock_boundary/ref.json", boundary)
    gate.store.json("mock_boundary/first.json", dict(update=first_update, accounting=gate.finish()))
    identity = agent.identity
    old_identity = dict(parent=identity["parent"], forecast=identity["forecast"], run=2, arm="C")
    reject(lambda: MacroSpeed.load(boundary["path"], old_identity, boundary["sha256"]), "private macro")
    # Strict restored fields before the next episode, no model query.
    restored = FrozenCYaw.load(boundary["path"], identity, boundary["sha256"])
    equal(restored.state(), torch_load(boundary))
    gate.scope("mock_continuous", 129, 1)
    case, wind = mock_case(4)
    continuous = rollout(agent, gate.env(real=False), case, wind, collect=True)
    next_update = gate.update(agent)
    continuous_state = gate.save("mock_continuous/state.pt", agent.state())
    gate.finish()
    process = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m",
        "optimization_control.tests.verify_yaw_takeover", "resume"], cwd=REPO,
        capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
    gate.store.write("mock_boundary/child.log", (process.stdout+process.stderr).encode())
    process.check_returncode()
    child = formal.read(ROOT/"mock_disk/result.json")
    assert child["pid"] != os.getpid()
    equal(torch_load(child["trajectory"]), continuous)
    equal(child["update"], next_update)
    equal(torch_load(child["state"]), torch_load(continuous_state))
    assert frozen_digest(agent) == frozen
    assert all(p.grad is None for p in agent.speed_heads.parameters())
    gate.store.json("mock_boundary/verification.json", dict(exact_disk_restore=True,
        next_trajectory_exact=True, next_update_exact=True, next_state_exact=True, frozen_parent=True,
        two_clocks=True, private_state_rejected_by_speed=True, parent_pid=os.getpid(), child_pid=child["pid"],
        first_update=first_update, next_update=next_update))


def disk_resume(gate):
    from optimization_control.maddpg_wind_farm.yaw_macro import FrozenCYaw
    boundary = formal.read(ROOT/"mock_boundary/ref.json")
    agent = FrozenCYaw.load(boundary["path"], gate.lock["identities"][2], boundary["sha256"])
    equal(agent.state(), torch_load(boundary))
    assert (agent.steps, agent.episodes, agent.draws, agent.updates) == (512, 4, 64, 1)
    gate.scope("mock_disk_resume", 129, 1)
    case, wind = mock_case(4)
    result = rollout(agent, gate.env(real=False), case, wind, collect=True)
    update = gate.update(agent)
    trajectory = gate.save("mock_disk/trajectory.pt", result)
    state = gate.save("mock_disk/state.pt", agent.state())
    gate.store.json("mock_disk/result.json", dict(pid=os.getpid(), trajectory=trajectory, state=state,
        update=update, accounting=gate.finish()))


def mock_short(gate):
    import numpy as np
    from optimization_control.maddpg_wind_farm.causal_speed_search import capture, fork
    from optimization_control.maddpg_wind_farm.yaw_macro import YawEpisode
    gate.scope("mock_short", 20)
    agent, env = gate.agent(), gate.env(real=False, horizon=19)
    case, wind = mock_case(0, 19)
    obs, info = formal.reset(env, case, wind)
    episode = YawEpisode(agent, env, obs, info)
    snapshots, records, closed = {}, [], []
    for t in range(19):
        item = episode.step(override_z=np.array([1, -1, .5], np.float32))
        records.append(item)
        if episode.pending is None:
            closed.append(deepcopy(episode.last_closed))
        if env.t in (5, 8):
            saved = dict(physical=capture(env), controller=episode.snapshot(), noise=deepcopy(agent.noise.bit_generator.state))
            snapshots[env.t] = gate.save(f"short/t{env.t}.pt", saved)
    assert [int(x["m"]) for x in closed] == [8, 8, 3]
    assert [bool(x["terminal"]) for x in closed] == [False, False, True]
    assert closed[-1]["discount"] == .99**3 and not closed[-1]["next_forecast_valid"]
    assert not np.any(closed[-1]["next_forecast"]) and not np.any(closed[-1]["raw_reward"][3:])
    for row in closed:
        oracle = [math.fsum(float(r[i])*.99**k for k, r in enumerate(row["raw_reward"][:int(row["m"])]))
                  for i in range(3)]
        np.testing.assert_allclose(row["return"], oracle, atol=1e-12, rtol=0)
    original_final = episode.snapshot()
    gate.save("short/reference.pt", dict(records=records, final=original_final, closed=closed))
    gate.finish()
    for t, ref in snapshots.items():
        gate.scope(f"mock_short_resume_t{t}", 19-t)
        saved = torch_load(ref)
        fresh = gate.agent()
        fresh.noise.bit_generator.state = saved["noise"]
        template = gate.env(real=False, horizon=19)
        child_env = fork(saved["physical"], template.plant, type(template))
        child_env.trajectory = wind.copy()
        recovered = YawEpisode.restore(fresh, child_env, saved["controller"])
        continuation = []
        while not child_env._done:
            continuation.append(recovered.step(override_z=np.array([1, -1, .5], np.float32)))
        equal(continuation, records[t:])
        equal(recovered.snapshot(), original_final)
        equal(fresh.noise.bit_generator.state, agent.noise.bit_generator.state)
        bad = deepcopy(saved["controller"]); bad["parent_clock"] += 1
        reject(lambda: YawEpisode.restore(gate.agent(), child_env, bad), "restored yaw clock")
        gate.store.json(f"short/resume_t{t}.json", dict(pending=t == 5, exact=True,
            parent_speed_nonzero=bool(np.any(saved["controller"]["speed_z"])),
            snapshot=ref, accounting=gate.finish()))


def finish(gate):
    import csv
    context()
    scopes = {name: formal.read(ROOT/f"{name}_budget.json")["scopes"] for name in ("model", "update")}
    totals = {name: sum(s["actual"] if s["status"] == "complete" else s["reserve"] for s in rows)
              for name, rows in scopes.items()}
    assert totals == dict(model=3399, update=3)
    checks = [("SI_and_angles", 0, 0, 1), ("real_zero_full_trajectory", 2322, 0, 9),
              ("real_nonzero_yaw", 258, 0, 2), ("mock_update_disk_resume", 774, 3, 1),
              ("short_terminal_and_pending_resume", 45, 0, 3)]
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["check", "model_rows", "joint_updates", "cases", "passed"])
    writer.writerows([(*row, True) for row in checks])
    gate.store.write("metrics.csv", text.getvalue().encode())
    gate.store.json("complete.json", dict(passed=True, rows=totals["model"], updates=totals["update"],
        model_rows_cap=4096, update_cap=12, formal_RL_steps=0, new_test_winds=0,
        C_selected_steps=[0, 0, 4096], pure_SI=True, zero_full_cases=9,
        real_nonzero_cases=2, disk_resume=True, pending_resume_steps=[5, 8],
        yaw_learning_benefit_evaluated=False, protected_files=len(gate.lock["hashes"])))
    gate.store.write("summary.txt", (
        "Yaw software engineering acceptance passed. seed=42, original C selected=0/0/4096.\n"
        "3399 total model rows (2580 PINN, 819 mock), 3 isolated engineering joint updates.\n"
        "9 full zero-takeover pairs exact, +1/-1 degree physical yaw connected, disk next update exact.\n"
        "No formal learning experiment or new independent test. Yaw weak/sign model limitation retained.\n"
        "See YAW_ENGINEERING_RESULTS.md and YAW_ENGINEERING_PROTOCOL.md for references and reproduction.\n").encode())
    print("Yaw engineering passed: 3399 rows, 3 engineering updates.", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("prepare", "run", "resume"))
    args = p.parse_args()
    from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
    activate_runtime(formal.ORIGIN/".venv/pinn_tf216")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(42)
    if args.phase == "prepare":
        prepare()
    elif args.phase == "resume":
        disk_resume(Gate())
    else:
        gate = Gate()
        pure_checks(gate)
        real_zero(gate)
        real_nonzero(gate)
        mock_boundary(gate)
        mock_short(gate)
        finish(gate)


if __name__ == "__main__":
    main()
