"""One frozen, budgeted independent evaluation of the Y/S yaw pilot."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from . import forecast_speed_training as old
from . import yaw_pilot as pilot

ROOT = old.EXPS/"20261105_yaw_independent"
PROTOCOL = Path(__file__).with_name("YAW_INDEPENDENT_TEST_PROTOCOL.md")
BASE = "eec78180f2679d65ab4a71ee074d9f57a98375e5"
FAMILIES = ("stationary", "ramp", "gust")
NS = tuple(range(74000000, 74000018))
STARTS = (71000000, 72000000, 73000000, 74000000)
PART_CAPS = (19104, 19104, 16792)
MIB = 1024**2


def shared():
    return old.Store(ROOT, 36*MIB, shared=True)


def namespace_scan():
    ids = {base: set(range(base, base+18)) for base in STARTS}
    all_ids = set.union(*ids.values())
    found, count = {str(base): [] for base in STARTS}, 0
    def entries(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("episode", "source_episode") and type(item) is int and item in all_ids:
                    yield item
                yield from entries(item)
        elif isinstance(value, list):
            for item in value:
                yield from entries(item)
    for repo in (old.REPO, old.ORIGIN, old.PITCH):
        names = subprocess.check_output(["rg", "--files", "--hidden", "--no-ignore", "-g", "*.json",
            str(repo/"optimization_control")], encoding="utf-8")
        for name in names.splitlines():
            path = Path(name)
            if path.is_relative_to(ROOT):
                continue
            raw = path.read_bytes()
            count += 1
            if re.search(rb"(?<!\d)7[1234]0000(?:0\d|1[0-7])(?!\d)", raw):
                for episode in entries(json.loads(raw.decode("utf-8-sig"))):
                    for base, group in ids.items():
                        if episode in group:
                            found[str(base)].append(dict(path=name, episode=episode))
    return dict(scanned_json=count, occupied=found, chosen=list(NS), original=list(range(71000000, 71000018)))


def prior_waves():
    """Hash saved physical disturbances, independent of their original float dtype."""
    import numpy as np
    inventory, hashes = [], set()
    for repo in (old.REPO, old.ORIGIN, old.PITCH):
        names = subprocess.check_output(["rg", "--files", "--hidden", "--no-ignore", "-g", "*.npz", "-g", "*.csv",
            str(repo/"optimization_control/experiments")], encoding="utf-8")
        for name in names.splitlines():
            path = Path(name)
            if path.is_relative_to(ROOT):
                continue
            waves = []
            if path.suffix == ".npz":
                with np.load(path, allow_pickle=False) as data:
                    if "wind" in data.files:
                        values = data["wind"]
                        if values.ndim == 2 and values.shape[-1] == 3:
                            waves = [values]
                        elif values.ndim == 3 and values.shape[-1] == 3:
                            waves = values
            else:
                with path.open(encoding="utf-8-sig", newline="") as stream:
                    reader = csv.DictReader(stream)
                    columns = ("speed_m_s", "direction_rad", "background_ti")
                    if set(columns).issubset(reader.fieldnames or ()):
                        waves = [np.asarray([[float(row[key]) for key in columns] for row in reader])]
            if len(waves):
                digests = []
                for values in waves:
                    physical = np.asarray(values, np.float32)
                    if physical.ndim != 2 or physical.shape[1] != 3 or not np.isfinite(physical).all():
                        raise ValueError("invalid prior disturbance source " + name)
                    digests.append(hashlib.sha256(physical.tobytes()).hexdigest())
                hashes.update(digests)
                inventory.append(dict(path=name, sha256=old.sha(path), waveforms=len(digests), hashes=digests))
    return inventory, hashes


def context():
    lock = old.read(ROOT/"lock.json")
    for path, sha in lock["hashes"].items():
        old.verify(dict(path=path, sha256=sha))
    assert pilot.lock_digest(pilot.context()) == lock["source_run_sha"]
    return lock


def prepare():
    import yaml
    assert old.git("rev-parse", "HEAD").decode().strip() == BASE
    source = pilot.context()
    proposal = old.read(pilot.ROOT/"future_test_proposal.json")
    selection = old.read(pilot.ROOT/"selection.json")
    assert not proposal["released"] and proposal["planned_rows"] == 53406 and proposal["roles_count"] == 23
    assert proposal["selection_sha"] == old.sha(pilot.ROOT/"selection.json")
    assert proposal["run_lock_sha"] == pilot.lock_digest(source)
    assert tuple(proposal["namespace"]) == tuple(range(71000000, 71000018))
    roles = []
    for item in proposal["selected_roles_frozen"]:
        job = next(j for j in selection["jobs"] if j["arm"] == item["arm"] and j["run"] == item["run"])
        point = job[item["role"]]
        assert point["step"] == item["step"] and point["snapshot"] == item["snapshot"]
        roles.append(dict(**item, kind="policy", id=f"{item['arm']}{item['run']}_{item['role']}"))
    roles.extend(dict(kind="fixed", run=r, id=f"fixed{r}") for r in range(3))
    roles.extend(dict(kind="baseline", mode=mode, id=mode) for mode in ("p", "pi"))
    roles.extend(r | dict(kind="yaw_disabled", id=r["id"]+"_zero") for r in list(roles) if r.get("arm") == "Y")
    assert len(roles) == len({r["id"] for r in roles}) == 23
    scan = namespace_scan()
    assert all(scan["occupied"][str(n)] for n in STARTS[:-1]) and not scan["occupied"]["74000000"]
    ROOT.mkdir(exist_ok=False)
    s = shared()
    scan_ref = s.json("namespace_correction.json", scan)
    review = pilot.REVIEW.with_name("YAW_PILOT_INDEPENDENT_REVIEW_20261105.md")
    review_ref = s.write("review_at_prepare.md", review.read_bytes()) if review.exists() else None
    config = dict(seed=42, base=BASE, source_run_sha=pilot.lock_digest(source), primary="Y_selected", comparator="shared_PI",
        families=list(FAMILIES), targets_w=[2750000, 3350000, 3850000], pitch_rad=[.025, .055],
        original_namespace=list(range(71000000, 71000018)), actual_namespace=list(NS), namespace_corrected_before_generation=True,
        horizon=128, dt_s=1, split="test", roles=23, rollouts=414, planned_rows=53406, row_hard_cap=55000,
        part_caps=list(PART_CAPS), disk_cap_MiB=128, role_cap_MiB=4, shared_cap_MiB=36,
        roles_aliased=False, bootstrap_seed=42, bootstrap_samples=2000, plot_case=17, plot_stream=2,
        criterion="each_family_equal_case_and_stream_mean_Y_selected_strictly_below_PI",
        new_training_steps=0, optimizer_updates=0, new_pressure_queries=0, pressure_source=str(pilot.ROOT/"pressure.csv"))
    cfg_ref = s.write("config.yaml", yaml.safe_dump(config, allow_unicode=True, sort_keys=False).encode())
    paths = [Path(__file__), PROTOCOL, Path(__file__).with_name("yaw_independent_report.py"),
        Path(__file__).with_name("forecast_speed_user_test_report.py"),
        Path(__file__).with_name("forecast_speed_report.py"),
        Path(__file__).with_name("yaw_pilot_saved_report.py"),
        pilot.ROOT/"selection.json", pilot.ROOT/"future_test_proposal.json", pilot.ROOT/"pressure.csv",
        pilot.ROOT/"verification.json", pilot.ROOT/"final_saved_audit.json", pilot.ROOT/"git_delivery.json",
        pilot.ROOT/"lock.json", pilot.ROOT/"repair_001/amendment.json", pilot.ROOT/"output_manifest.csv",
        Path(cfg_ref["path"]), Path(scan_ref["path"])]
    if review_ref:
        paths.append(Path(review_ref["path"]))
    hashes = dict(source["hashes"])
    hashes.update({str(p): old.sha(p) for p in paths})
    for role in roles:
        ref = role.get("snapshot")
        if ref and not ref.get("initial"):
            hashes[ref["path"]] = old.sha(old.verify(ref))
    s.json("lock.json", dict(hashes=hashes, source=source, source_run_sha=pilot.lock_digest(source),
        roles=roles, config=config, selection_sha=proposal["selection_sha"], original_proposal=proposal,
        namespace_correction=scan_ref, review_at_prepare=review_ref))
    print("Frozen 23 roles. Namespace corrected to 74000000..17 before any wind generation.", flush=True)


def release():
    import numpy as np
    from ..environments.farm_inflow import generate_inflow
    lock, s = context(), shared()
    scan = namespace_scan()
    if scan["occupied"]["74000000"]:
        raise ValueError("corrected namespace occupied since prepare")
    s.json("release_attempt.json", dict(lock_sha=old.sha(ROOT/"lock.json"), namespace=scan, model_rows=0))
    inventory, prior = prior_waves()
    inventory_ref = s.json("prior_waveforms.json", dict(files=inventory, unique_float32_hashes=len(prior)))
    cases, winds, seen = [], [], set()
    for family in FAMILIES:
        for target in lock["config"]["targets_w"]:
            for pitch in lock["config"]["pitch_rad"]:
                number = NS[len(cases)]
                cfg = deepcopy(lock["source"]["source"]["base_config"]["environment"]["inflow"])
                cfg["speed"]["scenario"] = family
                wind = generate_inflow(cfg, dt_s=1, horizon=128, seed=42, split="test", episode=number).values.astype(np.float32)
                sha = hashlib.sha256(wind.tobytes()).hexdigest()
                assert sha not in prior and sha not in seen and wind.shape == (129, 3)
                seen.add(sha)
                cases.append(dict(id=f"test_{len(cases):02d}_{family}_{target}_pitch{round(1000*pitch):03d}",
                    family=family, split="test", target_w=target, pitch_rad=pitch, episode=number, wind_sha=sha))
                winds.append(wind)
    bank = s.arrays("bank/test.npz", wind=np.stack(winds), meta=np.array(json.dumps(cases)))
    manifest = s.json("bank/manifest.json", dict(cases=cases, bank=bank, distinct_float32_waveforms=18,
        prior_inventory=inventory_ref, old_waves_disjoint=True, namespace_changed_for_occupancy=True))
    review_path = pilot.REVIEW.with_name("YAW_PILOT_INDEPENDENT_REVIEW_20261105.md")
    review = s.write("review_at_release.md", review_path.read_bytes()) if review_path.exists() else None
    s.json("release.json", dict(lock_sha=old.sha(ROOT/"lock.json"), selection_sha=lock["selection_sha"],
        bank_manifest=manifest, banks={"test": bank}, prior_inventory=inventory_ref, review=review,
        winds=18, model_rows=0, namespace=list(NS), release_once=True))
    print(f"Released 18 unique independent waves, disjoint from {len(prior)} saved float32 waves. 0 model rows.", flush=True)


def evaluation_context():
    lock = context()
    release = old.read(ROOT/"release.json")
    assert release["lock_sha"] == old.sha(ROOT/"lock.json") and release["selection_sha"] == lock["selection_sha"]
    old.verify(release["bank_manifest"])
    old.verify(release["prior_inventory"])
    cases = old.bank(release, "test")
    assert tuple(case["episode"] for case, _ in cases) == NS
    return lock, cases


def policy(lock, role):
    if role["kind"] == "baseline":
        return None
    if role["kind"] == "fixed":
        identity = lock["source"]["identities"][role["run"]]
        return old.inference(lock["source"]["source"], identity["snapshot"], "C", role["run"], identity["step"])
    return pilot.inference(lock["source"], role["snapshot"], role["arm"], role["run"], role["step"])


def policy_digest(agent):
    from .forecast_decision_contract import model_digest
    h = hashlib.sha256(model_digest(agent.parent).encode())
    for name in ("heads", "critics", "target_heads", "target_critics", "speed_heads"):
        if hasattr(agent, name):
            for key, value in getattr(agent, name).state_dict().items():
                h.update(name.encode()); h.update(key.encode()); h.update(value.detach().numpy().tobytes())
    return h.hexdigest()


def counters(agent):
    return [getattr(agent, k) for k in ("steps", "episodes", "updates", "draws")]+[agent.replay.insertions]


class CaseScope(old.QueryScope):
    def __init__(self, s, tag, ledger, **meta):
        self.ledger = ledger
        ledger.start(f"{meta['role']['id']}/{tag}", 129)
        super().__init__(s, tag, 129, **meta)

    def take(self, rows, kind):
        self.ledger.take(rows, kind)
        super().take(rows, kind)

    def finish(self, **data):
        account = self.ledger.finish()
        assert account["actual"] == account["reserve"] == 129
        return super().finish(partition_accounting=account, **data)


def worker(part):
    import numpy as np
    import torch
    from .causal_speed_search import Budget
    lock, cases = evaluation_context()
    world = pilot.World(lock["source"]["source"])
    ledger = Budget(ROOT/f"part{part}_budget.json", PART_CAPS[part])
    for role in lock["roles"][part::3]:
        start = time.perf_counter()
        a = policy(lock, role)
        before = policy_digest(a) if a is not None else None
        counts = counters(a) if a is not None else None
        rng = torch.get_rng_state().clone()
        s = old.Store(ROOT/"jobs"/role["id"], 4*MIB)
        results = []
        for index, item in enumerate(cases):
            tag = f"cases/{index:02d}"
            scope = CaseScope(s, tag, ledger, role=role, case=item[0], release_sha=old.sha(ROOT/"release.json"))
            if a is None:
                metrics, trace = old.evaluate(world, scope, [item], None, mode=role["mode"])
                trace = np.concatenate((trace, np.zeros((*trace.shape[:2], 3))), axis=2)
                metrics[0].update(yaw_z_abs_mean=0., yaw_z_saturation=0.,
                    yaw_actual_abs_mean=float(np.abs(trace[0, 1:, 19:28].reshape(128, 3, 3)[:, :, 0]).mean()))
            else:
                arm = role.get("arm", "S")
                metrics, trace = pilot.evaluate(world, scope, [item], a, arm, zero=role["kind"] == "yaw_disabled")
            ev = pilot.save_eval(s, tag, metrics, trace)
            results.append(scope.finish(eval=ev))
        assert torch.equal(rng, torch.get_rng_state())
        if a is not None:
            assert before == policy_digest(a) and counts == counters(a)
        s.json("complete.json", dict(role=role, cases=results, rows=2322, rollouts=18, pid=os.getpid(),
            parameter_digest=before, optimizer_updates_during_test=0, counters_before=counts,
            counters_after=counters(a) if a is not None else None, elapsed_s=time.perf_counter()-start))
        print(role["id"], "18 cases, 2322 rows", f"{time.perf_counter()-start:.1f}s", flush=True)


def run():
    lock, _ = evaluation_context()
    s = shared()
    s.json("run_attempt.json", dict(lock_sha=old.sha(ROOT/"lock.json"), release_sha=old.sha(ROOT/"release.json"),
        rows=53406, cap=55000, workers=3, optimizer_updates=0))
    def launch(part):
        command = [sys.executable, "-B", "-X", "utf8", "-m", "optimization_control.maddpg_wind_farm.yaw_independent_test",
                   "worker", "--part", str(part)]
        proc = subprocess.Popen(command, cwd=old.REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
        log = []
        for line in proc.stdout:
            log.append(line); print(f"part{part} {line.rstrip()}", flush=True)
        return dict(part=part, pid=proc.pid, status=proc.wait(), log="".join(log))
    with ThreadPoolExecutor(max_workers=3) as pool:
        processes = list(pool.map(launch, range(3)))
    for process in processes:
        s.write(f"processes/part{process['part']}.log", process.pop("log").encode())
    s.json("processes.json", processes)
    if any(p["status"] for p in processes):
        raise RuntimeError("Independent test failed; inspect reserved cases and charged budget before recovery")
    results = []
    for role in lock["roles"]:
        path = ROOT/"jobs"/role["id"]/"complete.json"
        entry = old.read(path)
        assert entry["role"] == role and entry["rows"] == 2322
        results.append(dict(path=str(path), sha256=old.sha(path)))
    budgets = [old.read(ROOT/f"part{part}_budget.json") for part in range(3)]
    assert sum(sum(r["actual"] for r in b["scopes"]) for b in budgets) == 53406
    assert all(r["status"] == "complete" for b in budgets for r in b["scopes"])
    context()
    s.json("complete.json", dict(results=results, roles=23, rollouts=414, unique_winds=18, rows=53406,
        charged_rows=53406, hard_cap=55000, optimizer_updates=0, training_steps=0, roles_aliased=False,
        selection_sha=lock["selection_sha"], release_sha=old.sha(ROOT/"release.json")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "release", "run", "worker"))
    parser.add_argument("--part", type=int, choices=(0, 1, 2))
    args = parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(old.ORIGIN/".venv/pinn_tf216")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True); torch.manual_seed(42)
    if args.phase == "worker":
        if args.part is None:
            parser.error("worker requires part")
        worker(args.part)
    else:
        dict(prepare=prepare, release=release, run=run)[args.phase]()


if __name__ == "__main__":
    main()
