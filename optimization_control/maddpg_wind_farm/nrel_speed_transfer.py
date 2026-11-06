"""Bounded engineering and six-wind frozen-policy speed-rule transfer evaluation."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path

from . import forecast_speed_training as old
from . import yaw_pilot as pilot
from . import yaw_independent_test as frozen

ROOT = old.EXPS/"20261106_nrel_speed_transfer"
PROTOCOL = Path(__file__).with_name("NREL_SPEED_TRANSFER_PROTOCOL.md")
REVIEW = old.PITCH/"optimization_control/maddpg_wind_farm/NREL_SPEED_REVIEW_20261106.md"
BASE = "11ba03d18be653fe0f10b2d020ede55ce4561984"
MIB = 1024**2
EXTRA = tuple(f"{name}_{i}" for name in ("reference_u", "base_omega", "command_omega", "actual_tsr", "base_tsr", "command_tsr") for i in range(3))
TRACE = pilot.TRACE+EXTRA


def store():
    return old.Store(ROOT, 128*MIB)


def context():
    lock = old.read(ROOT/"lock.json")
    for path, sha in lock["hashes"].items():
        old.verify(dict(path=path, sha256=sha))
    return lock


def cases(lock):
    return old.bank(dict(banks={"validation": lock["bank"]}), "validation")


def prepare():
    import numpy as np
    import yaml
    from . import nrel_speed_adapter as a
    assert old.git("rev-parse", "HEAD").decode().strip() == BASE
    source = frozen.context()
    roles = [r for r in source["roles"] if r["kind"] == "policy" and r["arm"] == "Y" and r["role"] == "selected"]
    assert [r["step"] for r in roles] == [2048, 0, 2048]
    selection = old.read(pilot.ROOT/"selection.json")
    legacy = {}
    for role in roles:
        j = next(j for j in selection["jobs"] if j["arm"] == "Y" and j["run"] == role["run"])
        assert role["snapshot"] == j["selected"]["snapshot"]
        legacy[role["id"]] = j["selected"]["eval"]
    for mode in ("p", "pi"):
        legacy[mode] = old.read(pilot.ROOT/f"diagnostics/{mode}/validation/complete.json")["eval"]
    validation = old.bank(source["source"], "validation")
    meta, winds = [], []
    for case, wind in validation:
        physical = wind.astype(np.float32)
        meta.append(case | dict(source_array_sha=case["wind_sha"],
            wind_sha=old.hashlib.sha256(physical.tobytes()).hexdigest()))
        winds.append(physical)
    ROOT.mkdir(exist_ok=False)
    s = store()
    bank = s.arrays("validation.npz", wind=np.stack(winds), meta=np.array(json.dumps(meta)))
    cfg = dict(seed=42, base_commit=BASE, task_start_commit="a98ef917f7826c553065163b26c81201655e495f",
        initial_worktree_status=[], purpose="frozen_old_policy_new_speed_rule_transfer",
        radius_m=a.RADIUS_M, lambda_ref=a.LAMBDA_REF, new_slope=a.SLOPE,
        new_speed_low=a.LOW, speed_high=a.HIGH, legacy_speed_low=a.OLD_LOW, legacy_slope=a.OLD_SLOPE,
        schema=a.SCHEMA, network_and_reward_speed_coordinates=[a.OLD_LOW, a.HIGH],
        final_execution_speed_bounds=[a.LOW, a.HIGH], old_rollouts_referenced=30, old_original_rows=3870,
        new_performance_rollouts=30, new_performance_rows=3870, engineering_PINN_rows=120,
        engineering_mock_rows=40, planned_new_rows=4030, row_hard_cap=10000, disk_cap_MiB=128,
        training_steps=0, optimizer_updates=0, new_wind_generation=0, pressure_rollouts=0,
        source_url="https://www.nlr.gov/docs/fy09osti/38060.pdf",
        source_sections=["Table 1-1", "Section 7.2", "Table 7-2"], plot_case=4, plot_stream=2)
    config_ref = s.write("config.yaml", yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False).encode())
    paths = [Path(__file__), PROTOCOL, Path(__file__).with_name("nrel_speed_adapter.py"),
             Path(__file__).with_name("nrel_speed_transfer_report.py"), Path(config_ref["path"])]
    saved_engineering = old.EXPS/"20261105_yaw_engineering/real_zero.json"
    paths.append(saved_engineering)
    paths.extend(old.verify(old.read(saved_engineering)["cases"][role["run"]*3]["artifact"]) for role in roles)
    hashes = dict(source["hashes"])
    hashes.update({str(p): old.sha(p) for p in paths})
    hashes[bank["path"]] = bank["sha256"]
    for ev in legacy.values():
        hashes.update({ref["path"]: old.sha(old.verify(ref)) for ref in ev.values()})
    s.json("lock.json", dict(hashes=hashes, source=source, base_config=source["source"]["source"]["base_config"],
        roles=roles, old_evaluations=legacy, bank=bank, config=cfg))
    print("Frozen transfer plan: 160 engineering + 3870 new performance rows, 30 old rollouts referenced.", flush=True)


class Recorder:
    def __init__(self, predictor, budget, kind):
        self.predictor, self.budget, self.kind = predictor, budget, kind
        self.inputs = []

    def __call__(self, x):
        self.budget.take(len(x), self.kind)
        self.inputs.append(x.copy())
        return self.predictor(x)


class World:
    def __init__(self, lock):
        self.lock, self.real = lock, None

    def env(self, budget, rule, controller, *, mock=False, horizon=128):
        from .nrel_speed_adapter import SpeedTransferEnv
        from .workflow import build_env, load_config, DEFAULT_CONFIG
        if mock:
            cfg = deepcopy(self.lock["base_config"])
            cfg["plant"] = load_config(DEFAULT_CONFIG)["plant"]
            plant = build_env(cfg).plant
            predictor = plant.predictor
        else:
            if self.real is None:
                self.real = old.World(dict(base_config=self.lock["base_config"]))
            plant, predictor = self.real.plant, self.real.predictor
        cfg = deepcopy(self.lock["base_config"]["environment"])
        cfg["horizon"] = horizon
        cfg["control_mask"] = [1, 1, 1] if controller.startswith("Y") else [0, 1, int(rule == "nrel")]
        plant.predictor = Recorder(predictor, budget, "mock" if mock else "PINN")
        return SpeedTransferEnv(plant, cfg, rule)


def legacy_base(wind):
    import numpy as np
    from ..utils.reference_schedule import speed_numpy
    from .nrel_speed_adapter import physical_speed, OLD_SLOPE, OLD_LOW, HIGH
    obs = np.zeros((3, 15), np.float32)
    obs[:, 1] = np.asarray(wind, np.float32)/np.float32(25.)
    return physical_speed(speed_numpy(obs, (25., OLD_SLOPE, OLD_LOW, HIGH)))


def extend(trace, rule):
    import numpy as np
    from .nrel_speed_adapter import base_reference, physical_speed, RADIUS_M
    effective = trace[:, 10:13]
    reference_u = np.concatenate((effective[:1], effective[:-1]))
    base = np.stack([base_reference(w) if rule == "nrel" else legacy_base(w) for w in reference_u])
    command = physical_speed(trace[:, 28:37].reshape(-1, 3, 3)[:, :, 2])
    actual = trace[:, 19:28].reshape(-1, 3, 3)[:, :, 2]
    return np.concatenate((trace, reference_u, base, command, actual*RADIUS_M/effective,
                           base*RADIUS_M/reference_u, command*RADIUS_M/reference_u), axis=1)


def metric(trace, case, rule):
    import numpy as np
    from .nrel_speed_adapter import LOW, OLD_LOW, HIGH
    result = old.metric(trace[:, :len(old.TRACE)], case)
    base, command = trace[1:, 55:58], trace[1:, 58:61]
    actual = trace[1:, 19:28].reshape(128, 3, 3)[:, :, 2]
    low = LOW if rule == "nrel" else OLD_LOW
    assert np.all(command >= low-1e-12) and np.all(command <= HIGH+1e-12)
    assert np.all(actual >= low-1e-12) and np.all(actual <= HIGH+1e-12)
    result.update(rule=rule, physical_low=low, speed_min=float(actual.min()), speed_max=float(actual.max()),
        base_mean=float(base.mean()), command_mean=float(command.mean()), speed_mean=float(actual.mean()),
        command_floor_fraction=float(np.mean(command <= low+1e-7)), command_ceiling_fraction=float(np.mean(command >= HIGH-1e-7)),
        actual_floor_fraction=float(np.mean(actual <= low+1e-7)), actual_ceiling_fraction=float(np.mean(actual >= HIGH-1e-7)),
        actual_TSR_mean=float(trace[1:, 61:64].mean()), actual_TSR_min=float(trace[1:, 61:64].min()),
        actual_TSR_max=float(trace[1:, 61:64].max()), base_TSR_mean=float(trace[1:, 64:67].mean()),
        command_TSR_mean=float(trace[1:, 67:70].mean()))
    return result


def rollout(world, budget, lock, controller, rule, case, wind, *, steps=128, mock=False, horizon=128):
    import numpy as np
    from .nrel_speed_adapter import FrozenTransfer, TransferPPI, LOW, HIGH
    from .yaw_macro import YawEpisode
    env = world.env(budget, rule, controller, mock=mock, horizon=horizon)
    obs, info = old.reset(env, case, wind if horizon == 128 else wind[:horizon+1])
    raw = None
    if controller.startswith("Y"):
        role = next(r for r in lock["roles"] if r["id"] == controller)
        raw = frozen.policy(lock["source"], role)
        digest = frozen.policy_digest(raw)
        counts = frozen.counters(raw)
        adapter = FrozenTransfer(raw, env)
        episode = YawEpisode(adapter, env, obs, info)
    else:
        feedback = TransferPPI(env, lock["base_config"]["baselines"], controller)
    rows = [old.trace_row(info, info["executed_action"], np.zeros(3), 0)+[0., 0., 0.]]
    observations = [obs.copy()]
    for t in range(steps):
        if raw is not None:
            item = episode.step()
            parent, sy, yz, reward, done, info = [item[k] for k in
                ("pitch_parent", "speed_z", "yaw_z", "reward", "terminal", "info")]
        else:
            parent = feedback.act(obs)
            obs, reward, done, trunc, info = env.step(parent)
            assert not trunc
            sy = yz = np.zeros(3, np.float32)
        assert done == (t+1 == horizon)
        rows.append(old.trace_row(info, parent, sy, reward[0])+yz.tolist())
        current = env._observe()
        expected_speed_obs = (2*(env.applied[:, 2]-env.low[2])/(env.high[2]-env.low[2])-1).astype(np.float32)
        np.testing.assert_array_equal(current[:, 4], expected_speed_obs)
        np.testing.assert_array_equal(current[:, 7], info["executed_action"][:, 2])
        observations.append(current)
    if raw is not None:
        assert digest == frozen.policy_digest(raw) and counts == frozen.counters(raw)
    trace = extend(np.asarray(rows, np.float64), rule)
    inputs = np.concatenate(env.plant.predictor.inputs)
    np.testing.assert_allclose(inputs[:, 9:12], trace[:, 19:28].reshape(-1, 3, 3)[:, :, 2], atol=1e-7, rtol=0)
    if rule == "nrel":
        assert np.all(trace[:, 19:28].reshape(-1, 3, 3)[:, :, 2] >= LOW-1e-12)
        assert np.all(inputs[:, 9:12] >= LOW-1e-7) and np.all(inputs[:, 9:12] <= HIGH+1e-7)
    return dict(trace=trace, obs=np.stack(observations), inputs=inputs, normalization=env.normalization(),
        parameters_frozen=True, counters_unchanged=True, reference_wind="previous_response_effective_wind")


def pure(lock):
    import numpy as np
    import torch
    from . import nrel_speed_adapter as a
    from ..tests.verify_yaw_takeover import reject
    assert a.SLOPE == 7.55/63 and a.LOW == 6.9*2*np.pi/60
    lo_u, hi_u = a.LOW/a.SLOPE, a.HIGH/a.SLOPE
    u = np.array([lo_u-1, lo_u, 8., hi_u, hi_u+1])
    base = a.base_reference(u)
    np.testing.assert_allclose(base, np.clip(u*a.SLOPE, a.LOW, a.HIGH), atol=0, rtol=0)
    assert abs(a.base_reference(np.array([8.]))[0]*63/8-7.55) < 1e-14
    marks = np.array([a.LOW, .9, a.HIGH])
    decoded = a.physical_speed(a.speed_action(marks))
    assert np.all(decoded >= a.LOW) and np.all(decoded <= a.HIGH)
    np.testing.assert_allclose(decoded, marks, atol=3e-8, rtol=0)
    for sign in (-1, 1):
        values = a.physical_speed(a.speed_action(a.base_reference(np.array([4., 8., 15.]))+.1*sign))
        assert np.all(values >= a.LOW) and np.all(values <= a.HIGH)
    identity_checks = []
    for role in lock["roles"]:
        agent = frozen.policy(lock["source"], role)
        # Use already saved engineering observations and forecast values, never query the plant.
        entry = old.read(old.EXPS/"20261105_yaw_engineering/real_zero.json")["cases"][role["run"]*3]["artifact"]
        saved = torch.load(old.verify(entry), map_location="cpu", weights_only=False)["actual"]
        obs, features = saved["obs"][0], saved["macros"][0]["forecast"]
        cfg = deepcopy(lock["base_config"]["environment"]); cfg["control_mask"] = [1, 1, 1]
        from .workflow import build_env, DEFAULT_CONFIG, load_config
        mock_cfg = deepcopy(lock["base_config"]); mock_cfg["plant"] = load_config(DEFAULT_CONFIG)["plant"]
        plant = build_env(mock_cfg).plant
        env = a.SpeedTransferEnv(plant, cfg, "legacy")
        adapter = a.FrozenTransfer(agent, env)
        for target in (False, True):
            np.testing.assert_array_equal(agent.z(obs, features, target=target), adapter.z(obs, features, target=target))
        sy, yz = agent.speed_z(obs, features), agent.z(obs, features)
        for x, y in zip(agent.compose(obs, sy, yz, (-.25, .25)), adapter.compose(obs, sy, yz, (-.25, .25)), strict=True):
            np.testing.assert_array_equal(x, y)
        reject(lambda: adapter.update(), "inference only")
        assert agent.parent.config.speed_reference_schedule == (25., a.OLD_SLOPE, .6, 1.267)
        new_env = a.SpeedTransferEnv(plant, cfg, "nrel")
        new_env.effective_wind = np.array([8., 9., 10.5])
        adapted = a.FrozenTransfer(agent, new_env)
        for sign in (-1, 0, 1):
            speed_z = np.full(3, sign, np.float32)
            original = agent.compose(obs, speed_z, yz, (-.25, .25))
            changed = adapted.compose(obs, speed_z, yz, (-.25, .25))
            for x, y in zip(original[:2], changed[:2], strict=True):
                np.testing.assert_array_equal(x[:, :2], y[:, :2])
            np.testing.assert_array_equal(original[2], changed[2])
            expected = np.clip(a.base_reference(new_env.effective_wind)+.1*sign, a.LOW, a.HIGH)
            np.testing.assert_allclose(a.physical_speed(changed[0][:, 2]), expected, atol=3e-8, rtol=0)
            np.testing.assert_array_equal(changed[0][:, 2], changed[1][:, 2])
        # All frozen heads see the original coordinate for three distinct physical markers.
        marked_obs = obs.copy()
        marked_obs[:, 4] = 2*(marks-a.OLD_LOW)/(a.HIGH-a.OLD_LOW)-1
        marked_obs[:, 7] = a.speed_action(marks)
        for target in (False, True):
            np.testing.assert_array_equal(agent.z(marked_obs, features, target=target),
                                          adapted.z(marked_obs, features, target=target))
        np.testing.assert_array_equal(agent.speed_z(marked_obs, features), adapted.speed_z(marked_obs, features))
        for actors in (agent.parent.actors, agent.parent.target_actors):
            x = torch.as_tensor(marked_obs)
            output = torch.stack([agent.parent.policy(actor, x[i]) for i, actor in enumerate(actors)])
            assert output.shape == (3, 3) and torch.isfinite(output).all()
        identity_checks.append(dict(run=role["run"], old_current_target_coordinates=True,
            old_command_exact=True, new_speed_physical_radius_and_clamp=True,
            pitch_yaw_same_input_commands_exact=True, three_physical_markers_old_coordinates=True))
    store().json("pure.json", dict(passed=True, rows=0, updates=0, lower_intersection_m_s=lo_u,
        upper_intersection_m_s=hi_u, old_coordinate_lower_for_new_min=float(a.LOW_ACTION),
        marked_physical_speeds=decoded.tolist(), old_identity_checks=identity_checks,
        error_normalization_unchanged=True, no_new_target_training_path=True))


def engineering():
    import numpy as np
    from .causal_speed_search import Budget
    from .yaw_pilot_saved_report import frozen as report
    lock, s = context(), store()
    pure(lock)
    validation = cases(lock)
    reused = {}
    for name, ev in lock["old_evaluations"].items():
        metrics, trace = report.read_eval(ev, validation, "Y" if name.startswith("Y") else "baseline")
        reused[name] = trace
    s.json("legacy_reuse.json", dict(verified=True, roles=lock["old_evaluations"], physical_rollouts_referenced=30,
        original_input_rows=3870, new_model_rows=0, all_same_frozen_identity_wind_targets_initials=True))
    world, budget = World(lock), Budget(ROOT/"model_budget.json", 10000)
    outcomes = []
    for role in lock["roles"]:
        for rule in ("legacy", "nrel"):
            label = f"engineering/{role['id']}_{rule}"
            budget.start(label, 20)
            result = rollout(world, budget, lock, role["id"], rule, *validation[0], steps=19)
            if rule == "legacy":
                np.testing.assert_array_equal(result["trace"][:, :52], reused[role["id"]][0, :20])
            actual = result["trace"][:, 19:28].reshape(20, 3, 3)
            heading = result["trace"][:, 16:19]
            assert np.abs(np.diff(heading, axis=0)).max() <= .005+1e-12
            assert np.abs(np.diff(actual[:, :, 1:], axis=0)).max(axis=(0, 1))[0] <= .00872664626+1e-12
            assert np.abs(np.diff(actual[:, :, 2], axis=0)).max() <= .1+1e-12
            ref = s.torch(label+".pt", result, MIB)
            account = budget.finish(); assert account["actual"] == 20
            outcomes.append(dict(controller=role["id"], rule=rule, artifact=ref, budget=account, old_path_exact=rule == "legacy"))
    from ..tests.verify_yaw_takeover import equal
    reference = None
    for repeat in range(2):
        budget.start(f"engineering/mock_reset{repeat}", 20)
        data = rollout(world, budget, lock, "Y2_selected", "nrel", *validation[0], steps=19, horizon=19, mock=True)
        if reference is None:
            reference = data
        else:
            equal(reference, data)
        s.torch(f"engineering/mock_reset{repeat}.pt", data, MIB)
        assert budget.finish()["actual"] == 20
    context()
    s.json("engineering.json", dict(passed=True, rows=160, PINN_rows=120, mock_rows=40, outcomes=outcomes,
        old_prefix_pairs_exact=3, old_observation_speed_previous_action_checked=True, actual_bounds_and_rates_passed=True,
        same_mock_reset_trajectory_exact=True, training_steps=0, optimizer_updates=0))
    print("Engineering passed: old prefixes exact, new physical bounds, reset exact. 160 rows.", flush=True)


def performance():
    import numpy as np
    from .causal_speed_search import Budget
    lock, s = context(), store()
    assert old.read(ROOT/"engineering.json")["passed"] and old.read(ROOT/"legacy_reuse.json")["verified"]
    if not REVIEW.exists():
        raise ValueError("current implementation review required before performance")
    review = REVIEW.read_text(encoding="utf-8")
    # Admission is recorded after reading the substantive implementation review.
    admission = old.read(ROOT/"review_admission.json")
    assert admission["performance_allowed"] and admission["review_sha256"] == old.sha(REVIEW)
    s.write("review_at_performance.md", review.encode())
    world, budget = World(lock), Budget(ROOT/"model_budget.json", 10000)
    results = []
    for controller in [r["id"] for r in lock["roles"]]+["p", "pi"]:
        metrics, traces = [], []
        for index, item in enumerate(cases(lock)):
            budget.start(f"performance/{controller}/{index}", 129)
            data = rollout(world, budget, lock, controller, "nrel", *item)
            metrics.append(metric(data["trace"], item[0], "nrel")); traces.append(data["trace"])
            assert budget.finish()["actual"] == 129
        ev = dict(metrics=s.json(f"new/{controller}/metrics.json", metrics),
            trace=s.arrays(f"new/{controller}/trace.npz", trace=np.stack(traces), fields=np.array(TRACE)))
        results.append(dict(controller=controller, eval=ev, actual_rollouts=6, input_rows=774))
        print(controller, "new rule mean kW", sum(m["rmse_w"] for m in metrics)/6000, flush=True)
    totals = sum(x["actual"] if x["status"] == "complete" else x["reserve"] for x in budget.data["scopes"])
    assert totals == 4030 and all(x["status"] == "complete" for x in budget.data["scopes"])
    context()
    s.json("complete.json", dict(results=results, new_rows=4030, performance_rows=3870, engineering_rows=160,
        old_rollouts_referenced=30, new_performance_rollouts=30, training_steps=0, optimizer_updates=0,
        pressure_cases=0, new_wind_generation=0, row_hard_cap=10000, migration_only=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "engineering", "performance"))
    args = parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(old.ORIGIN/".venv/pinn_tf216")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1"); os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True); torch.manual_seed(42)
    dict(prepare=prepare, engineering=engineering, performance=performance)[args.phase]()


if __name__ == "__main__":
    main()
