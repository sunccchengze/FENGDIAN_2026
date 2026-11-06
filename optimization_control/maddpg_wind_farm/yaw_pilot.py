"""Frozen two-arm, three-stream yaw/speed software pilot with bounded accounting."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from . import forecast_speed_training as old

ROOT = old.EXPS/"20261105_yaw_pilot"
ENGINEERING = old.EXPS/"20261105_yaw_engineering"
REVIEW = old.PITCH/"optimization_control/maddpg_wind_farm/YAW_IMPLEMENTATION_REVIEW_20261105.md"
INTERFACE = REVIEW.with_name("YAW_PARENT_INTERFACE_REVIEW_20261105.md")
PROTOCOL = Path(__file__).with_name("YAW_PILOT_PROTOCOL.md")
BASE = "a12288fd1dfdd2b299e4d949288d8a5908bcbe3f"
SCHEMA = "yaw_speed_pilot_state_v1"
PURPOSE = "formal_yaw_speed_software_pilot_v1"
POINTS = (0, 1024, 2048)
ARMS = ("Y", "S")
MIB = 1024**2
TRACE = old.TRACE+("yaw_z_0", "yaw_z_1", "yaw_z_2")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def store():
    return old.Store(ROOT, 48*MIB, shared=True)


def context():
    lock = old.read(ROOT/"lock.json")
    amendment = ROOT/"repair_001/amendment.json"
    if amendment.exists():
        change = old.read(amendment)
        assert change["old_lock_sha"] == old.sha(ROOT/"lock.json")
        original = change["original_source"]
        assert old.sha(old.verify(original)) == lock["hashes"][str(Path(__file__))]
        for path, sha in change["new_hashes"].items():
            old.verify(dict(path=path, sha256=sha))
            lock["hashes"][path] = sha
        lock["banks"].update(change["bank_overrides"])
        for ref in change["bank_overrides"].values():
            old.verify(ref)
        lock["_revision"] = old.sha(amendment)
    for path, sha in lock["hashes"].items():
        old.verify(dict(path=path, sha256=sha))
    return lock


def lock_digest(lock):
    return digest(dict(original=old.sha(ROOT/"lock.json"), revision=lock.get("_revision")))


def preflight_path(lock):
    return "preflight_001.json" if "_revision" in lock else "preflight.json"


def namespace():
    ids = {70000000+1000*r+e for r in range(3) for e in range(16)}
    matches, count = [], 0
    def entries(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("episode", "source_episode") and type(item) is int and item in ids:
                    yield item
                yield from entries(item)
        elif isinstance(value, list):
            for item in value:
                yield from entries(item)
    for repo in (old.REPO, old.ORIGIN, old.PITCH):
        names = subprocess.check_output(["rg", "--files", "--hidden", "--no-ignore", "-g", "*.json",
            str(repo/"optimization_control")], encoding="utf-8")
        for name in names.splitlines():
            p = Path(name)
            if p.is_relative_to(ROOT):
                continue
            count += 1
            raw = p.read_bytes()
            if re.search(rb"(?<!\d)7000[012]0(?:0\d|1[0-5])(?!\d)", raw):
                matches.extend(dict(path=name, episode=e) for e in entries(json.loads(raw.decode("utf-8-sig"))))
    return dict(scanned_json=count, actual_episode_collisions=matches, planned_episode_count=48)


def binding(lock, arm, run):
    return lock["contracts"][f"{arm}{run}"]


def new_agent(lock, arm, run):
    from .yaw_macro import FrozenCYaw
    if arm == "Y":
        class FormalYaw(FrozenCYaw):
            PURPOSE = "formal_yaw_pilot_inner_v1"
        return FormalYaw(lock["identities"][run])
    job = next(j for j in lock["selection"]["jobs"] if j["arm"] == "C" and j["run"] == run)
    if run == 2:
        next_case = old.bank(lock["source"], "train2")[32][0]["id"]
        return old.resume(lock["source"], "C", run, job["selected"], 4096, next_case)[0]
    return old.fresh(lock["source"], "C", run)[0]


def envelope_check(saved, lock, arm, run):
    expected = binding(lock, arm, run)
    if (saved.get("schema"), saved.get("purpose"), saved.get("lock_sha"), saved.get("arm"), saved.get("run"),
            saved.get("contract"), saved.get("contract_sha")) != (
            SCHEMA, PURPOSE, lock_digest(lock), arm, run, expected, digest(expected)):
        raise ValueError("formal pilot purpose, source, scale or permission mismatch")


class Pilot:
    def __init__(self, lock, arm, run):
        import numpy as np
        self.lock, self.arm, self.run = lock, arm, run
        self.agent = new_agent(lock, arm, run)
        self.origin = {k: getattr(self.agent, k) for k in ("steps", "episodes", "updates", "draws")}
        self.noise = np.random.default_rng(np.random.SeedSequence([42, 20261105, 9042, run]))
        self.new_steps = self.new_updates = self.new_draws = 0

    def state(self):
        import torch
        if self.new_steps not in (1024, 2048):
            raise ValueError("only planned pilot boundaries may be saved")
        contract = binding(self.lock, self.arm, self.run)
        return dict(schema=SCHEMA, purpose=PURPOSE, lock_sha=lock_digest(self.lock),
            arm=self.arm, run=self.run, contract=contract, contract_sha=digest(contract),
            origin=self.origin, new_steps=self.new_steps, new_updates=self.new_updates, new_draws=self.new_draws,
            exploration_rng=deepcopy(self.noise.bit_generator.state), payload=self.agent.state(),
            torch_rng=torch.get_rng_state())

    @classmethod
    def load(cls, ref, lock, arm, run):
        import numpy as np
        import torch
        from .forecast_speed_macro import restore_adam, digest_array
        from .forecast_decision_contract import sha_history
        saved = torch.load(old.verify(ref), map_location="cpu", weights_only=False)
        envelope_check(saved, lock, arm, run)
        obj = cls(lock, arm, run)
        if saved["origin"] != obj.origin:
            raise ValueError("inherited pilot origin mismatch")
        for name in ("new_steps", "new_updates", "new_draws"):
            value = saved[name]
            if type(value) is not int or value < 0:
                raise ValueError("invalid pilot delta counter")
            setattr(obj, name, value)
        if (obj.new_steps not in (1024, 2048) or obj.new_updates != (obj.new_steps-512)//16+1
                or obj.new_draws != obj.new_steps//8):
            raise ValueError("pilot delta schedule mismatch")
        a, state = obj.agent, saved["payload"]
        initial_identity = deepcopy(a.identity)
        if state["identity"] != initial_identity or state["purpose"] != a.PURPOSE:
            raise ValueError("pilot inner source or purpose mismatch")
        for k, delta in (("steps", obj.new_steps), ("episodes", obj.new_steps//128),
                         ("updates", obj.new_updates), ("draws", obj.new_draws)):
            if state[k] != obj.origin[k]+delta:
                raise ValueError("pilot cumulative counter mismatch")
            setattr(a, k, state[k])
        a.replay.restore(state["replay"], a.episodes, "C")
        a.boundary = deepcopy(state["boundary"])
        last = (a.replay.position-1) % a.replay.capacity
        b = a.boundary
        if arm == "Y":
            if (b["t"] != 128 or b["parent_clock"] != 128 or b["yaw_clock"] != 128
                    or b["pending"] is not None or b["decisions"] != 16 or b["parent_decisions"] != 16
                    or len(b["observed"]) != 129
                    or not np.array_equal(b["obs"], a.replay.data["next_obs"][last])
                    or not np.array_equal(digest_array(b["observed"]), a.replay.data["next_history"][last])
                    or not np.array_equal(b["speed_z"], a.speed_z(a.replay.data["obs"][last],
                                                               a.replay.data["forecast"][last]))):
                raise ValueError("pilot yaw clocks, held speed or prefix mismatch")
        elif (b["episode"] != a.episodes-1 or b["history_tail"].shape != (32, 3)
                or sha_history(b["history_tail"]) != b["tail_sha256"]
                or b["history_sha256"] != a.replay.data["next_history"][last].tobytes().hex()):
            raise ValueError("pilot speed history mismatch")
        for name in ("heads", "critics", "target_heads", "target_critics"):
            network, weights = getattr(a, name), state["networks"][name]
            for key, expected in network.state_dict().items():
                if weights[key].dtype != expected.dtype or not torch.isfinite(weights[key]).all():
                    raise ValueError("invalid pilot network")
            network.load_state_dict(weights, strict=True)
        for name in ("head_adam", "critic_adam"):
            if len(state["adam"][name]) != 3:
                raise ValueError("three pilot Adam states required")
            for opt, value in zip(getattr(a, name), state["adam"][name], strict=True):
                restore_adam(opt, value, a.updates)
        a.noise.bit_generator.state = deepcopy(state["noise_rng"])
        obj.noise.bit_generator.state = deepcopy(saved["exploration_rng"])
        torch.set_rng_state(saved["torch_rng"])
        return obj


def prepare():
    import numpy as np
    import torch
    import yaml
    from ..environments.farm_inflow import generate_inflow
    from .speed_nstep_training import design
    assert old.git("rev-parse", "HEAD").decode().strip() == BASE
    engineering = old.read(ENGINEERING/"complete.json")
    assert engineering["passed"] and (engineering["rows"], engineering["updates"]) == (3399, 3)
    e = old.read(ENGINEERING/"lock.json")
    for p, sha in e["hashes"].items():
        old.verify(dict(path=p, sha256=sha))
    review = REVIEW.read_bytes()
    assert "未发现当前已证实的代码阻断项" in review.decode("utf-8") and "a12288f" in review.decode("utf-8")
    scan = namespace()
    assert not scan["actual_episode_collisions"]
    prior = old.context()
    selected = old.read(old.ROOT/"selection.json")
    cfg = prior["base_config"]
    contract = dict(dt=1, horizon=128, gamma=.99, interval=8, physical_low=cfg["environment"]["action_low"],
        physical_high=cfg["environment"]["action_high"], normalization="fixed_physical_scales_no_running_statistics",
        reference=cfg["environment"]["reference_schedule"], reference_mode=cfg["environment"]["speed_reference_mode"],
        parent_speed_source="deployment_online", synchronized=True, plant=cfg["plant"])
    contracts = {}
    for arm in ARMS:
        for run in range(3):
            contracts[f"{arm}{run}"] = dict(**contract, arm=arm, run=run, frozen_C=e["identities"][run],
                permission=[1, 1, 1] if arm == "Y" else [0, 1, 1],
                correction_channel="yaw" if arm == "Y" else "speed", radius=math_radius(arm),
                parent_C_state=(old.read(old.ROOT/"jobs/C2/s4096/state_ref.json") if arm == "S" and run == 2 else None))
    ROOT.mkdir(exist_ok=False)
    s = store()
    s.json("namespace.json", scan)
    review_ref = s.write("review_snapshot.md", review)
    interface_ref = s.write("interface_review_snapshot.md", INTERFACE.read_bytes())
    banks = {k: prior["banks"][k] for k in ("validation", "stress")}
    old_hashes = set()
    for k in ("train0", "train1", "train2", "validation"):
        for case, wind in old.bank(prior, k):
            old_hashes.add(case["wind_sha"])
            old_hashes.add(hashlib.sha256(wind.astype(np.float32).tobytes()).hexdigest())
    for path, groups, key in (
        (old.EXPS/"20261029_history_forecast/bank_manifest.json", ("fit", "score"), "values_sha256"),
        (old.EXPS/"20261029_history_independent_test/bank/manifest.json", ("cases",), "values_sha256"),
        (old.EXPS/"20261105_forecast_speed_independent/bank/manifest.json", ("cases",), "wind_sha")):
        d = old.read(path)
        old_hashes.update(row[key] for group in groups for row in d[group])
    seen = set()
    ep_design = dict(design_entropy=[42, 20261105, 9041], training_targets_w=[2.6e6, 3.2e6, 3.8e6],
                     training_initial_pitch_rad=[.025, .055])
    for run in range(3):
        cases, winds = [], []
        for episode in range(16):
            family, target, pitch = design(ep_design, run, episode)
            number = 70000000+1000*run+episode
            inflow = deepcopy(cfg["environment"]["inflow"])
            inflow["speed"]["scenario"] = family
            wind = generate_inflow(inflow, dt_s=1, horizon=128, seed=42, split="train", episode=number).values.astype(np.float32)
            sha = hashlib.sha256(wind.astype(np.float32).tobytes()).hexdigest()
            assert sha not in old_hashes and sha not in seen
            seen.add(sha)
            cases.append(dict(id=f"yawpilot_{run}_{episode:02d}", episode=number, family=family,
                split="train", target_w=target, pitch_rad=pitch, wind_sha=sha))
            winds.append(wind)
        banks[f"train{run}"] = s.arrays(f"bank/train{run}.npz", wind=np.stack(winds), meta=np.array(json.dumps(cases)))
    plan = dict(seed=42, base=BASE, arms=list(ARMS), runs=[0, 1, 2], points=list(POINTS),
        formal_steps=12288, expected_updates_per_job=97, rows=37023, engineering_rows=3399,
        cumulative_rows=40422, cumulative_cap=42000, row_retry_margin=1578,
        pilot_disk_MiB=120, jobs_disk_MiB=12, shared_disk_MiB=48, combined_disk_MiB=128,
        engineering_bytes=sum(p.stat().st_size for p in ENGINEERING.rglob("*") if p.is_file()),
        prior_waveform_hashes=len(old_hashes), new_train_waveforms=48, training_design=ep_design,
        test_release=False, main_criterion="each_family_equal_parent_case_mean_RMSE_strictly_below_shared_PI",
        ratios_are_diagnostics=True, selection="strict_validation_mean_then_earliest", new_budget_schedule=True,
        noise_std=.15, noise_entropy=[42, 20261105, 9042], no_auxiliary_heads=True)
    assert plan["engineering_bytes"]+120*MIB < 128*MIB
    ref = s.write("config.yaml", yaml.safe_dump(plan, allow_unicode=True, sort_keys=False).encode())
    hashes = deepcopy(e["hashes"])
    hashes.update({str(p): old.sha(p) for p in (Path(__file__), PROTOCOL,
        Path(__file__).with_name("yaw_pilot_report.py"), ENGINEERING/"complete.json", ENGINEERING/"git_delivery.json",
        old.ROOT/"selection.json", old.ROOT/"jobs/C2/s4096/state_ref.json", old.ROOT/"jobs/C2/s4096/state.pth")})
    hashes.update({r["path"]: r["sha256"] for r in (review_ref, interface_ref, ref, *banks.values())})
    s.json("lock.json", dict(hashes=hashes, source=prior, selection=selected, identities=e["identities"],
        contracts=contracts, banks=banks, plan=plan, review_at_release_sha=review_ref["sha256"]))
    preflight(context())
    print("Pilot locked: 48 paired training winds, 0 model rows, 0 optimizer updates.", flush=True)


def math_radius(arm):
    import math
    return math.pi/180 if arm == "Y" else .1


def preflight(lock):
    import numpy as np
    import torch
    from .yaw_macro import RADIUS
    from ..tests.verify_yaw_takeover import equal, reject, torch_load
    from ..environments.maddpg_farm_env import MADDPGFarmEnv
    from .workflow import build_env, DEFAULT_CONFIG, load_config
    results = []
    for run in range(3):
        cases = old.bank(lock, f"train{run}")
        assert len(cases) == 16 and all(w.dtype == np.float32 for _, w in cases)
    for run in range(3):
        y, speed = Pilot(lock, "Y", run), Pilot(lock, "S", run)
        origin = speed.origin
        assert origin == dict(steps=4096, episodes=32, updates=225, draws=512) if run == 2 else origin == dict(steps=0, episodes=0, updates=0, draws=0)
        assert y.agent.replay.size == 0 and all(not opt.state for opt in (*y.agent.head_adam, *y.agent.critic_adam))
        ref = old.read(ENGINEERING/"real_zero.json")["cases"][run*3]["artifact"]
        saved = torch_load(ref)["actual"]
        obs, feat = saved["obs"][0], saved["macros"][0]["forecast"]
        sy = y.agent.speed_z(obs, feat)
        mixed = np.array([1, 0, -1], np.float32)
        cfg = deepcopy(lock["source"]["base_config"])
        cfg["plant"] = load_config(DEFAULT_CONFIG)["plant"]
        cfg["environment"]["control_mask"] = [1, 1, 1]
        env = build_env(cfg)
        # No reset, advance or predictor invocation. Supply only observed physical fields needed by projection.
        env.wind = saved["inputs"][0, :3].copy()
        env.effective_wind = saved["trace"][0, 10:13].copy()
        env.applied = saved["trace"][0, 19:28].reshape(3, 3).copy()
        env.previous_action = saved["obs"][0, :, 5:8].copy()
        env.target = 2.85e6; env.power = saved["trace"][0, 13:16].astype(np.float32); env.t = 0
        a, fixed, _ = y.agent.compose(obs, sy, mixed, (env.low[0], env.high[0]))
        projected = env.project_action(a)
        mapped = env.mapper.map(projected).commanded_control["yaw_misalignment_reference_rad"]
        baseline = env.mapper.map(fixed).commanded_control["yaw_misalignment_reference_rad"]
        np.testing.assert_allclose(mapped-baseline, RADIUS*mixed, atol=2e-9, rtol=0)
        np.testing.assert_array_equal(projected[:, 1:], fixed[:, 1:])
        np.testing.assert_array_equal(sy, speed.agent.z(obs, feat))
        np.testing.assert_array_equal(y.noise.normal(size=3), speed.noise.normal(size=3))
        for target in (False, True):
            np.testing.assert_array_equal(y.agent.z(obs, feat, target=target), np.zeros(3, np.float32))
        # Upper bounds include all 256 new samples, with room for inherited C2 speed samples.
        measured = {}
        for arm, agent in (("Y", y.agent), ("S", speed.agent)):
            raw = sum(v[:agent.replay.size+256].nbytes for v in agent.replay.data.values())
            parameter_bytes = sum(v.numel()*v.element_size() for group in
                (agent.heads, agent.critics, agent.target_heads, agent.target_critics) for v in group.parameters())
            upper = raw+3*parameter_bytes+256*1024
            assert upper < 4*MIB
            measured[arm] = upper
        results.append(dict(run=run, S_origin=origin, S_inherited_replay=speed.agent.replay.size,
            mixed_yaw_rad=mapped.tolist(), state_upper_bytes=measured))
    # Contract-only mutation checks reject before any state restoration or model forward.
    header = dict(schema=SCHEMA, purpose=PURPOSE, lock_sha=lock_digest(lock), arm="Y", run=2,
        contract=binding(lock, "Y", 2), contract_sha=digest(binding(lock, "Y", 2)))
    envelope_check(header, lock, "Y", 2)
    for field, value in (("schema", "frozen_C_yaw_engineering_v1"), ("purpose", "yaw_engineering_only"),
                         ("run", 1), ("contract_sha", "wrong")):
        reject(lambda f=field, v=value: envelope_check(header | {f: v}, lock, "Y", 2), "formal pilot")
    for field, value in (("radius", .1), ("permission", [0, 1, 1]), ("parent_speed_source", "target")):
        altered = deepcopy(header); altered["contract"][field] = value
        altered["contract_sha"] = digest(altered["contract"])
        reject(lambda v=altered: envelope_check(v, lock, "Y", 2), "formal pilot")
    old_state = torch.load(old.ROOT/"jobs/C2/s4096/state.pth", map_location="cpu", weights_only=False)
    difference = sum(not torch.equal(x, old_state["networks"]["target_heads"][k])
                     for k, x in old_state["networks"]["heads"].items())
    assert difference > 0
    store().json(preflight_path(lock), dict(passed=True, G1_mixed_mapping=True, G2_reused_exact_pairs=9,
        G3_deployment_online_only=True, C2_online_target_different_tensors=difference,
        G4_contract_mutations_rejected=True, runs=results, new_model_rows=0, new_updates=0,
        inherited_C2_full_state=True, no_engineering_state_loaded=True, checkpoint_cap_bytes=4*MIB,
        independence_review_sha=lock["review_at_release_sha"]))


class World(old.World):
    def env(self, scope, arm):
        if isinstance(arm, bool):
            return super().env(scope, arm)
        env = super().env(scope, True)
        env.control_mask[:] = [arm == "Y", True, True]
        env.config["control_mask"] = [int(arm == "Y"), 1, 1]
        return env


def evaluate(world, scope, cases, agent, arm, *, zero=False):
    import numpy as np
    from .forecast_speed_macro import Episode
    from .yaw_macro import YawEpisode
    env = world.env(scope, arm)
    metrics, traces = [], []
    for case, wind in cases:
        obs, info = old.reset(env, case, wind)
        episode = YawEpisode(agent, env, obs, info) if arm == "Y" else Episode(agent, env, obs, info)
        rows = [old.trace_row(info, info["executed_action"], np.zeros(3), 0)+[0., 0., 0.]]
        for t in range(128):
            if arm == "Y":
                item = episode.step(override_z=np.zeros(3, np.float32) if zero else None)
                parent, sy, yz, reward, done, info = [item[k] for k in
                    ("pitch_parent", "speed_z", "yaw_z", "reward", "terminal", "info")]
            else:
                parent, _, sy, reward, done, info = episode.step()
                yz = np.zeros(3, np.float32)
            assert done == (t == 127)
            rows.append(old.trace_row(info, parent, sy, reward[0])+yz.tolist())
        trace = np.asarray(rows, np.float64)
        metric = old.metric(trace[:, :len(old.TRACE)], case)
        metric.update(yaw_z_abs_mean=float(np.abs(trace[1:, -3:]).mean()),
            yaw_z_saturation=float(np.mean(np.abs(trace[1:, -3:]) >= .98)),
            yaw_actual_abs_mean=float(np.abs(trace[1:, 19:28].reshape(128, 3, 3)[:, :, 0]).mean()))
        metrics.append(metric); traces.append(trace)
    return metrics, np.stack(traces)


def save_eval(s, tag, metrics, trace):
    import numpy as np
    return dict(metrics=s.json(f"{tag}/metrics.json", metrics),
        trace=s.arrays(f"{tag}/trace.npz", trace=trace, fields=np.array(TRACE)))


def snapshot(s, tag, pilot):
    if not pilot.new_steps:
        return dict(initial=True, arm=pilot.arm, run=pilot.run, step=0,
                    contract_sha=digest(binding(pilot.lock, pilot.arm, pilot.run)))
    return s.torch(f"{tag}/inference.pt", dict(schema="yaw_speed_pilot_inference_v1", purpose=PURPOSE,
        lock_sha=lock_digest(pilot.lock), arm=pilot.arm, run=pilot.run, step=pilot.new_steps,
        contract_sha=digest(binding(pilot.lock, pilot.arm, pilot.run)), weights=pilot.agent.heads.state_dict()), MIB//4)


def inference(lock, ref, arm, run, step):
    import torch
    a = new_agent(lock, arm, run)
    if ref.get("initial"):
        assert step == 0 and ref == dict(initial=True, arm=arm, run=run, step=0,
            contract_sha=digest(binding(lock, arm, run)))
        return a
    saved = torch.load(old.verify(ref), map_location="cpu", weights_only=True)
    assert (saved["schema"], saved["purpose"], saved["lock_sha"], saved["arm"], saved["run"], saved["step"],
            saved["contract_sha"]) == ("yaw_speed_pilot_inference_v1", PURPOSE, lock_digest(lock),
                                    arm, run, step, digest(binding(lock, arm, run)))
    a.heads.load_state_dict(saved["weights"], strict=True)
    return a


def train(world, scope, pilot, target, cases):
    import numpy as np
    from unittest.mock import patch
    from .forecast_speed_macro import Episode
    from .yaw_macro import YawEpisode
    env = world.env(scope, pilot.arm)
    rows = []
    for ordinal in range(pilot.new_steps//128, target//128):
        case, wind = cases[ordinal]
        obs, info = old.reset(env, case, wind)
        ep = (YawEpisode(pilot.agent, env, obs, info, collect=True) if pilot.arm == "Y" else
              Episode(pilot.agent, env, obs, info, collect=True))
        errors, motion, updates = [], [], []
        for t in range(128):
            proposed = None
            if ep.pending is None:
                proposed = pilot.agent.z(ep.obs, ep.features)
                scale = 1-.8*min(1., pilot.new_steps/2048)
                proposed = np.clip(proposed+pilot.noise.normal(0, .15*scale, 3), -1, 1).astype(np.float32)
                pilot.new_draws += 1
                pilot.agent.draws += 1
            if pilot.arm == "Y":
                item = ep.step(override_z=proposed)
                done, info = item["terminal"], item["info"]
            elif proposed is not None:
                with patch.object(pilot.agent, "z", return_value=proposed):
                    *_, done, info = ep.step()
            else:
                *_, done, info = ep.step()
            pilot.new_steps += 1
            if ep.pending is None and pilot.new_steps >= 512 and pilot.new_steps % 16 == 0:
                update = pilot.agent.update(lambda: None)
                pilot.new_updates += 1
                updates.append(update)
            assert done == (t == 127)
            errors.append(info["error_w"]); motion.append(info["action_change"])
        assert pilot.agent.steps == pilot.origin["steps"]+pilot.new_steps
        rows.append(dict(case=case, new_step=pilot.new_steps, new_updates=pilot.new_updates,
            rmse_w=float(np.sqrt(np.mean(np.square(errors)))), command_mse=float(np.mean(motion)), updates=updates))
    assert pilot.new_updates == (target-512)//16+1
    return rows


def worker(arm, run):
    import torch
    from .forecast_decision_contract import model_digest
    from ..tests.verify_yaw_takeover import equal, frozen_digest
    lock = context()
    assert old.read(ROOT/preflight_path(lock))["passed"]
    s = old.Store(ROOT/"jobs"/f"{arm}{run}", 12*MIB)
    pilot = Pilot(lock, arm, run)
    world = World(lock["source"])
    cases, validation = old.bank(lock, f"train{run}"), old.bank(lock, "validation")
    frozen = frozen_digest(pilot.agent) if arm == "Y" else model_digest(pilot.agent.parent)
    for step in POINTS:
        start = time.perf_counter()
        tag = f"s{step:04d}"
        scope = old.QueryScope(s, tag, 774 if step == 0 else 1806, arm=arm, run=run, new_step=step)
        logs = train(world, scope, pilot, step, cases) if step else []
        state_ref = None
        if step:
            state_ref = s.torch(f"{tag}/state.pt", pilot.state(), 4*MIB)
            restored = Pilot.load(state_ref, lock, arm, run)
            equal(restored.state(), pilot.state())
            # Continue from the disk-restored object at 1024, exercising the normal resume entry.
            pilot = restored
        snap = snapshot(s, tag, pilot)
        rng = torch.get_rng_state().clone()
        metrics, trace = evaluate(world, scope, validation, pilot.agent, arm)
        assert torch.equal(rng, torch.get_rng_state())
        assert frozen == (frozen_digest(pilot.agent) if arm == "Y" else model_digest(pilot.agent.parent))
        result = save_eval(s, tag, metrics, trace)
        scope.finish(arm=arm, run=run, step=step, eval=result, state=state_ref, snapshot=snap,
            logs=s.json(f"{tag}/episodes.json", logs), origin=pilot.origin,
            new_updates=pilot.new_updates, new_draws=pilot.new_draws,
            mean_w=sum(r["rmse_w"] for r in metrics)/6, worst_w=max(r["rmse_w"] for r in metrics),
            restored_exact=bool(step), elapsed_s=time.perf_counter()-start)
        print(f"{arm}{run} new_step={step} mean={sum(r['rmse_w'] for r in metrics)/6000:.3f} kW", flush=True)


def run():
    lock = context()
    s = store()
    assert old.read(ROOT/preflight_path(lock))["passed"]
    attempt = "001" if "_revision" in lock else "000"
    s.json(f"run_attempt_{attempt}.json", dict(seed=42, jobs=6, lock_sha=lock_digest(lock), formal_rows=26316,
        no_new_test=True, independence_review_sha=lock["review_at_release_sha"]))
    def launch(part):
        log = []
        statuses = []
        for arm, run in [(a, r) for a in ARMS for r in range(3)][part::3]:
            command = [sys.executable, "-B", "-X", "utf8", "-m", "optimization_control.maddpg_wind_farm.yaw_pilot",
                       "worker", "--arm", arm, "--run", str(run)]
            p = subprocess.Popen(command, cwd=old.REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
            for line in p.stdout:
                print(line.rstrip(), flush=True); log.append(line)
            statuses.append(dict(arm=arm, run=run, pid=p.pid, status=p.wait()))
            if statuses[-1]["status"]:
                break
        return dict(part=part, jobs=statuses, log="".join(log))
    with ThreadPoolExecutor(max_workers=3) as pool:
        processes = list(pool.map(launch, range(3)))
    for p in processes:
        s.write(f"processes/attempt_{attempt}_part{p['part']}.log", p.pop("log").encode())
    s.json(f"processes_{attempt}.json", processes)
    assert sum(len(p["jobs"]) for p in processes) == 6 and all(
        j["status"] == 0 for p in processes for j in p["jobs"])
    jobs = []
    for arm in ARMS:
        for run in range(3):
            points = [old.read(ROOT/"jobs"/f"{arm}{run}"/f"s{x:04d}/complete.json") for x in POINTS]
            assert [r["rows"] for r in points] == [774, 1806, 1806]
            assert [r["new_updates"] for r in points] == [0, 33, 97]
            chosen = min(points, key=lambda row: (row["mean_w"], row["step"]))
            jobs.append(dict(arm=arm, run=run, initial=points[0], selected=chosen, final=points[-1], points=points))
    context()
    s.json("selection.json", dict(jobs=jobs, selection="strict_validation_mean_then_earliest",
        lock_sha=lock_digest(lock), steps=12288, rows=26316, no_new_test=True))


def diagnostics():
    lock = context()
    selection = old.read(ROOT/"selection.json")
    assert selection["lock_sha"] == lock_digest(lock)
    world, s = World(lock["source"]), store()
    validation, stress = old.bank(lock, "validation"), old.bank(lock, "stress")
    groups = []
    def one(label, agent, arm, cases, *, zero=False, mode=None):
        scope = old.QueryScope(s, label, len(cases)*129, selection_sha=old.sha(ROOT/"selection.json"))
        if mode:
            metrics, tr = old.evaluate(world, scope, cases, None, mode=mode)
            import numpy as np
            trace = np.concatenate((tr, np.zeros((*tr.shape[:2], 3))), axis=2)
            for m in metrics:
                m.update(yaw_z_abs_mean=0., yaw_z_saturation=0.,
                         yaw_actual_abs_mean=float(np.abs(tr[metrics.index(m), 1:, 19:28].reshape(128, 3, 3)[:, :, 0]).mean()))
        else:
            metrics, trace = evaluate(world, scope, cases, agent, arm, zero=zero)
        ev = save_eval(s, label, metrics, trace)
        groups.append(dict(label=label, eval=ev, receipt=scope.finish(eval=ev)))
        print(label, scope.actual, flush=True)
    for run in range(3):
        identity = lock["identities"][run]
        fixed = old.inference(lock["source"], identity["snapshot"], "C", run, identity["step"])
        one(f"diagnostics/fixed{run}/validation", fixed, "S", validation)
        one(f"diagnostics/fixed{run}/stress", fixed, "S", stress)
    for mode in ("p", "pi"):
        one(f"diagnostics/{mode}/validation", None, "S", validation, mode=mode)
        one(f"diagnostics/{mode}/stress", None, "S", stress, mode=mode)
    for job in selection["jobs"]:
        for role in ("selected", "final"):
            point = job[role]
            a = inference(lock, point["snapshot"], job["arm"], job["run"], point["step"])
            label = f"diagnostics/{job['arm']}{job['run']}/{role}"
            if job["arm"] == "Y":
                one(label+"/zero", a, "Y", validation, zero=True)
            one(label+"/stress", a, job["arm"], stress)
    context()
    assert sum(old.read(old.verify(r["receipt"]))["rows"] for r in groups) == 10707
    s.json("complete.json", dict(passed=True, groups=groups, diagnostics_rows=10707, formal_rows=37023,
        engineering_rows=3399, cumulative_rows=40422, hard_cap=42000, steps=12288, updates=582,
        new_test_winds=0, selection_sha=old.sha(ROOT/"selection.json")))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("prepare", "run", "worker", "diagnostics"))
    p.add_argument("--arm", choices=ARMS); p.add_argument("--run", type=int, choices=(0, 1, 2))
    args = p.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(old.ORIGIN/".venv/pinn_tf216")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1"); os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True); torch.manual_seed(42)
    if args.phase == "worker":
        if args.arm is None or args.run is None:
            p.error("worker requires arm and run")
        worker(args.arm, args.run)
    else:
        dict(prepare=prepare, run=run, diagnostics=diagnostics)[args.phase]()


if __name__ == "__main__":
    main()
