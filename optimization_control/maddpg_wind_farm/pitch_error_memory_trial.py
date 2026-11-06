"""Frozen paired pitch-memory trial. Training and sealed evaluation share one ledger."""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .fixed_pinn_demo import activate_runtime, digest
from .pitch_cross_wind_diagnostic import ORIGINAL, read_csv
from .pitch_error_memory_engineering import EXPERIMENTS, INTEGRAL, PARENTS, PROJECT
from .pitch_gamma_trial import episode_metrics, fingerprint, json_state, row_step
from .pitch_nstep_trial import read_json, verify, wind

HERE = Path(__file__).resolve().parent
ENGINEERING = EXPERIMENTS / "20261104_pitch_error_memory_engineering"
ARMS = ("zero", "memory")
FAMILIES = ("stationary", "ramp", "gust")
NAMESPACE = dict(train=71000000, validation=72000000, test=73000000, pressure=73009000)
ROWS = dict(train=99072, validation=74304, known=55728, test=92880, pressure=20640)
CAP = 2756 * 1024**2
STATE_CAP = 22 * 1024**2
TRACE_CAP = 128 * 1024
STEPS = 16384
SELECTION_STEPS = tuple(range(0, STEPS + 1, 4096))
MODULE = "optimization_control.maddpg_wind_farm.pitch_error_memory_trial"


def size(root):
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


class Store:
    def __init__(self, root):
        self.root = root
        self.used = size(root)
        self.existing_engineering = size(ENGINEERING)
        if self.existing_engineering > 256 * 1024**2:
            raise RuntimeError("engineering storage cap exceeded")

    def check(self, extra):
        if self.used + extra > CAP or self.used + extra + self.existing_engineering >= 3 * 1024**3:
            raise RuntimeError("trial storage limit")

    def put(self, path, data, limit=CAP):
        path = self.root / path
        if len(data) > limit:
            raise RuntimeError(f"artifact exceeds its allocation: {path}")
        self.check(len(data))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)
        self.used += len(data)

    def json(self, path, value):
        self.put(path, (json.dumps(json_state(value), ensure_ascii=False, indent=2) + "\n").encode("utf8"))

    def table(self, path, rows, *, compressed=False, limit=CAP):
        rows = list(rows)
        fields = list(dict.fromkeys(k for row in rows for k in row))
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        data = buffer.getvalue().encode("utf8")
        self.put(path, gzip.compress(data, mtime=0) if compressed else data, limit)

    def wind(self, path, trace):
        path = self.root / path
        self.check(128 * 1024)
        path.parent.mkdir(parents=True, exist_ok=True)
        trace.save(path)
        paths = (path, path.with_suffix(".json"))
        written = sum(p.stat().st_size for p in paths)
        if written > 128 * 1024:
            raise RuntimeError("wind artifact allocation exceeded")
        self.used += written
        return {str(p): digest(p) for p in paths}


class Meter:
    def __init__(self, store):
        self.store = store
        self.counts = {}
        self.active = None
        self.file = None
        for name in ROWS:
            path = store.root / f"rows_{name}.bin"
            ticks = path.read_bytes() if path.exists() else b""
            if ticks != b"1" * len(ticks) or len(ticks) > ROWS[name]:
                raise ValueError("invalid predictor ledger")
            self.counts[name] = len(ticks)

    def begin(self, kind):
        if self.active is not None or self.counts[kind] + 129 > ROWS[kind]:
            raise RuntimeError(f"episode would exceed {kind} row allowance")
        self.file = (self.store.root / f"rows_{kind}.bin").open("ab", buffering=0)
        self.active = kind
        self.start = self.counts[kind]

    def end(self):
        self.file.close()
        count = self.counts[self.active] - self.start
        self.active = None
        return count

    def wrap(self, predictor):
        def measured(values):
            kind = self.active
            if kind is None or len(values) != 1:
                raise ValueError("one predictor row requires an active episode")
            if self.counts[kind] >= ROWS[kind] or sum(self.counts.values()) + 297 >= 346720:
                raise RuntimeError("predictor row cap")
            self.store.check(1)
            self.file.write(b"1")
            self.store.used += 1
            self.counts[kind] += 1
            return predictor(values)
        return measured


def context(root):
    seal = read_json(root / "input_lock.json")
    verify(seal["hashes"])
    cfg = read_json(root / "config.yaml")
    verify(cfg["protected_hashes"])
    return cfg


def seed(purpose, run, *extra):
    import numpy as np
    return np.random.SeedSequence([42, 20261104, purpose, run, *extra])


def exploration(run):
    from .stable_workflow import Exploration
    number = int(seed(7103, run).generate_state(1)[0])
    return number, Exploration(number, [0., .03, 0.], [10., 3., 5.], 1., "white", .2)


def bank_spec(split):
    targets, pitches, repeats = ((2.9e6, 3.5e6), (.025, .04, .055), 1) if split == "validation" else (
        (2.75e6, 3.35e6, 3.95e6), (.03, .05), 2)
    cases = []
    for i, family in enumerate(FAMILIES):
        for j, target in enumerate(targets):
            for repeat in range(repeats):
                episode = NAMESPACE[split] + i * 100 + j * 10 + repeat
                for pitch in pitches:
                    cases.append(dict(id=f"{split}_{family}_t{target:g}_r{repeat}_p{pitch}", split=split,
                                      family=family, target_w=target, initial_pitch_rad=pitch, episode=episode))
    if split == "test":
        for i, speed in enumerate((7.6, 7.8)):
            for target in (4.35e6, 4.55e6):
                for pitch in pitches:
                    cases.append(dict(id=f"pressure_w{speed}_t{target:g}_p{pitch}", split="stress",
                                      family="low_wind_stress", target_w=target, initial_pitch_rad=pitch,
                                      episode=NAMESPACE["pressure"]+i, constant_wind=[speed, 0., .08]))
    return cases


def make_bank(store, cfg, split, specs):
    if split == "test":
        lock = read_json(store.root / "pretest_lock.json")
        verify(lock["hashes"])
    paths = {}
    cases, hashes = [], {}
    for spec in specs:
        episode = spec["episode"]
        if episode not in paths:
            family = spec["family"] if spec["split"] != "stress" else "stationary"
            trace = wind(cfg, family, split, episode)
            if "constant_wind" in spec:
                trace.values[:] = spec["constant_wind"]
                trace.components[:] = [spec["constant_wind"][0], 0., 0.]
                trace.metadata["override_family"] = "known_low_wind_pressure"
            path = Path(f"{split}_bank/{episode}.csv")
            hashes.update(store.wind(path, trace))
            paths[episode] = str(store.root / path)
        cases.append(dict(spec, path=paths[episode]))
    manifest = store.root / f"{split}_bank/manifest.json"
    store.json(manifest, dict(seed=42, cases=cases, hashes=hashes))
    return dict(hashes, **{str(manifest): digest(manifest)})


def namespace_audit():
    scan = {}
    ranges = ((71000000, 71002127), (72000000, 72000210), (73000000, 73000221), (73009000, 73009001))
    import re
    for tree in (ORIGINAL, PROJECT, Path(".")):
        top = tree / "optimization_control"
        paths = list((top / "maddpg_wind_farm/configs").glob("*.yaml"))
        paths += list((top / "experiments").glob("*/config.yaml"))
        paths += list((top / "experiments").glob("*/*_bank/manifest.json"))
        paths += list((top / "experiments").glob("*/training_manifest.csv"))
        for path in paths:
            # Registered IDs and configured namespaces are metadata. Old test wind
            # values and evaluation metrics are outside this scan.
            values = map(int, re.findall(r"(?<![\d.])7[123]\d{6}(?![\d.])", path.read_text(encoding="utf-8-sig")))
            occupied = sorted({n for n in values if any(lo <= n <= hi for lo, hi in ranges)})
            scan[str(path)] = dict(sha256=digest(path), occupied=occupied)
    if any(row["occupied"] for row in scan.values()):
        raise ValueError("reserved namespace already occupied")
    return scan


def prepare(root):
    import numpy as np
    import yaml
    from .pitch_error_memory import RULE
    from .pitch_error_memory_engineering import state
    from .nstep_algorithm import NStepMADDPG
    from . import pitch_error_memory_review  # Resolve the analysis imports before sealing.
    from . import workflow, controllers, stable_workflow, pitch_action_diagnostic
    from ..environments import wind_pinn_backend

    old = yaml.safe_load((INTEGRAL / "config.yaml").read_text(encoding="utf8"))
    base = old["base_config"]
    source = read_json(PARENTS)
    prior = read_json(ENGINEERING / "verification.json")
    assert prior["status"] == "passed" and prior["real_rows"] == 297 and prior["mock_rows"] == 0
    assert (ENGINEERING / "plant_rows.log").read_bytes().splitlines() == [b"real"] * 297
    source_config = EXPERIMENTS / "20261028_pitch_nstep/config.yaml"
    assert digest(source_config) == source["trial_config_sha256"]
    assert base == yaml.safe_load(source_config.read_text(encoding="utf8"))["base_config"]
    protected = {source["source_selection"]: source["source_selection_sha256"],
                 str(source_config): source["trial_config_sha256"]}
    parents = {}
    for p in source["candidates"]:
        assert p["selected_by_test"] is False
        verify({p["checkpoint"]: p["sha256"]})
        agent, _ = NStepMADDPG.load(p["checkpoint"], expected_n=8)
        assert agent.config.gamma == .99 and tuple(agent.config.action_mask) == (0, 1, 0)
        parents[str(p["run"])] = dict(path=p["checkpoint"], sha256=p["sha256"], step=p["selected_step"],
                                      updates=agent.updates, insertions=agent.replay.insertions,
                                      fingerprint=fingerprint(state(agent)), replay_rng=agent.replay.rng.bit_generator.state,
                                      actor_rng=agent.rng.bit_generator.state)
        protected[p["checkpoint"]] = p["sha256"]
    assert [p["step"] for p in parents.values()] == [16384, 12288, 4096]
    references = [r for r in read_json(INTEGRAL / "reference_reuse.json")["references"] if r["collection"] == "known"]
    known = [c for c in read_json(INTEGRAL / "case_manifest.json")["cases"] if c["collection"] == "known"]
    assert len(known) == 36 and len(references) == 5
    wind_lock = read_json(INTEGRAL / "input_lock.json")["hashes"]
    for c in known:
        for path in (c["path"], str(Path(c["path"]).with_suffix(".json"))):
            protected[path] = wind_lock[path]
    for reference in references:
        for key in ("metrics", "traces"):
            protected[reference[key]] = reference[f"{key}_sha256"]
    model = Path(base["plant"]["backend"]["run_dir"])
    paths = [PARENTS, INTEGRAL / "config.yaml", INTEGRAL / "reference_reuse.json", INTEGRAL / "case_manifest.json",
             INTEGRAL / "input_lock.json", ENGINEERING / "verification.json", ENGINEERING / "budget_audit.json",
             ENGINEERING / "plant_rows.log", HERE / "PITCH_ERROR_MEMORY_FORMAL_PROTOCOL.md",
             Path(base["plant"]["backend"]["script"]), *(model / n for n in ("trained.keras", "config_used.json", "training_report.json"))]
    for module in tuple(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and Path(path).resolve().is_relative_to(PROJECT / "optimization_control"):
            paths.append(Path(path).resolve())
    protected.update({str(p): digest(p) for p in paths})
    verify(protected)
    scan = namespace_audit()
    root.mkdir(parents=True, exist_ok=False)
    store = Store(root)
    store.json("config.yaml", dict(seed=42, experiment="pitch_error_memory_formal_v1", memory_rule=RULE,
               source_commit="698537ce9ade3cb515e41b87fea1322cbad6865b", parents=parents, base_config=base,
               steps_per_job=STEPS, total_steps=6*STEPS, update_calls_per_job=7937, warmup=512, update_every=2,
               arms=ARMS, selection_steps=SELECTION_STEPS, selection_rule="strict minimum validation case RMSE then earliest step",
               namespace=NAMESPACE, purpose_ids=[7101,7102,7103], row_caps=ROWS, prior_engineering_rows=297,
               storage_limit_bytes=CAP, full_checkpoint_every=1024, light_every=128, protected_hashes=protected))
    store.json("namespace_audit.json", scan)
    store.json("test_spec.json", dict(seed=42, cases=bank_spec("test"), release="pretest_lock"))
    store.json("known_sources.json", dict(cases=known, references=references))
    hashes = make_bank(store, base, "validation", bank_spec("validation"))
    design = []
    random_states = []
    cells = [(f, t) for f in FAMILIES for t in (2.6e6, 3.2e6, 3.8e6)]
    for run in range(3):
        number, noise = exploration(run)
        state_log = dict(run=run, entropy=[42,20261104,7103,run], integer_seed=number, initial=json_state(noise.state_dict()), episodes=[])
        samples = []
        for ep in range(128):
            block, index = divmod(ep, 9)
            order = np.random.default_rng(seed(7101, run, block)).permutation(9)
            family, target = cells[order[index]]
            pitch = float(np.random.default_rng(seed(7102, run, ep)).uniform(.025, .055))
            episode = NAMESPACE["train"] + run*1000 + ep
            path = Path(f"train_bank/{episode}.csv")
            trace = wind(base, family, "train", episode)
            hashes.update(store.wind(path, trace))
            design.append(dict(id=f"run{run}_ep{ep:03d}", run=run, episode_index=ep, episode=episode,
                               split="train", family=family, target_w=target, initial_pitch_rad=pitch,
                               path=str(root/path), values_sha256=fingerprint(trace.values)))
            noise.reset()
            values = np.stack([noise.sample((ep*128+t)/STEPS) for t in range(128)])
            samples.append(values)
            state_log["episodes"].append(dict(after=json_state(noise.state_dict()), sha256=fingerprint(values)))
        buffer = io.BytesIO()
        np.savez_compressed(buffer, noise=np.stack(samples))
        name = f"noise_run{run}.npz"
        store.put(name, buffer.getbuffer())
        hashes[str(root/name)] = digest(root/name)
        random_states.append(state_log)
    store.table("training_manifest.csv", design)
    store.json("random_states.json", random_states)
    for name in ("config.yaml", "training_manifest.csv", "test_spec.json", "known_sources.json", "random_states.json", "namespace_audit.json"):
        hashes[str(root/name)] = digest(root/name)
    store.json("input_lock.json", dict(hashes=hashes, new_test_generated=False, model_rows=0))
    print(f"Frozen {len(design)} training episodes and 18 validation cases", flush=True)


def environment(cfg, meter):
    from .workflow import build_env
    env = build_env(cfg["base_config"])
    env.plant.predictor = meter.wrap(env.plant.predictor)
    return env


def rollout(env, meter, kind, case, agent=None, baseline=None, training=None):
    import numpy as np
    from ..environments.farm_inflow import InflowTrace
    from .controllers import PitchController
    from .pitch_action_diagnostic import reset_case
    from .pitch_error_memory import advance_integral
    meter.begin(kind)
    try:
        obs, info = reset_case(env, case, InflowTrace.load(case["path"]))
        controller = PitchController(env, baseline[0], baseline[1]) if baseline else None
        integral = 0.
        rows, transitions, losses = [], [], []
        for t in range(128):
            action = agent.act(obs, integral=integral) if agent else controller.act(obs)
            if training is not None:
                step, noise, expected = training
                exploration = noise.sample((step+t)/STEPS)
                np.testing.assert_array_equal(exploration, expected[t])
                action = env.project_action(np.clip(action + exploration, -1, 1)).astype(np.float32)
            following, reward, done, truncated, after = env.step(action)
            assert not truncated and done == (t == 127)
            issued = after["executed_action"]
            next_integral = advance_integral(integral, obs, issued) if agent else 0.
            row = row_step(env, obs, action, reward, info, after, case)
            rows.append(dict(row, integral_rad=integral, next_integral_rad=next_integral))
            if training is not None:
                assert agent.replay.add(obs, issued, reward, following, done, integral=integral) == next_integral
                transitions.append(dict(obs=obs, next_obs=following, actions=issued, rewards=reward, terminated=done,
                                        exploration=exploration, integral=integral, next_integral=next_integral))
                current = step+t+1
                if current >= 512 and current % 2 == 0:
                    stats = agent.update()
                    losses.append(dict(step=current, **stats, indices_sha256=fingerprint(agent.replay.last_indices),
                                       lengths_sha256=fingerprint(agent.replay.last_lengths)))
            obs, info, integral = following, after, next_integral
    finally:
        count = meter.end()
    assert count == 129
    return rows, transitions, losses


def evaluate(store, env, meter, cases, folder, split, agent=None, baseline=None):
    result = []
    traces = {}
    for index, case in enumerate(cases):
        kind = "pressure" if case["split"] == "stress" else split
        trace, _, _ = rollout(env, meter, kind, case, agent, baseline)
        path = store.root / folder / f"case_{index:02d}.csv.gz"
        store.table(path, trace, compressed=True, limit=TRACE_CAP)
        traces[case["id"]] = dict(path=str(path), sha256=digest(path))
        result.append(episode_metrics(trace))
    path = store.root / folder / "metrics.csv"
    store.table(path, result)
    store.json(folder / "cases.json", dict(metrics=str(path), metrics_sha256=digest(path), traces=traces))
    return result


def worker(root, arm, run, stop):
    import numpy as np
    import torch
    from .pitch_error_memory import PitchErrorMemory, NETWORKS
    from .pitch_error_memory_engineering import legacy
    cfg = context(root)
    config_sha = digest(root/"config.yaml")
    store = Store(root)
    meter = Meter(store)
    env = environment(cfg, meter)
    parent = cfg["parents"][str(run)]
    job = root / f"{arm}_run{run}"
    _, noise = exploration(run)
    states = read_json(root/"random_states.json")[run]
    designs = [r for r in read_csv(root/"training_manifest.csv") if int(r["run"]) == run]
    expected = np.load(root/f"noise_run{run}.npz")["noise"]
    validation = read_json(root/"validation_bank/manifest.json")["cases"]
    recovered = job.exists()
    if recovered:
        assert run == 0 and stop == STEPS and not (job/"result.json").exists()
        assert len(list(job.glob("step_*/complete.json"))) == 9
        point = job/"step_00001024"
        committed = read_json(point/"complete.json")
        verify(committed["hashes"])
        agent, meta = PitchErrorMemory.load(point/"state.pth", expected_arm=arm, purpose="formal")
        assert (meta["step"], meta["run"], meta["config_sha"], meta["parent_sha"]) == (1024, run, config_sha, parent["sha256"])
        assert meta["pid"] != os.getpid() and agent.updates-parent["updates"] == 257
        assert agent.replay.insertions == parent["insertions"] + 1024
        noise.load_state_dict(meta["noise"])
        assert json_state(noise.state_dict()) == states["episodes"][7]["after"]
        start, history = 1024, meta["history"]
        store.json(job/"recovery.json", dict(source=str(point/"state.pth"), sha256=digest(point/"state.pth"), step=start,
                   previous_pid=meta["pid"], current_pid=os.getpid(), replayed_steps=0, resume_rng=meta["noise"]))
    else:
        agent, _, episodes = PitchErrorMemory.from_parent(parent["path"], arm, purpose="formal")
        assert fingerprint(legacy(agent)) == parent["fingerprint"]
        assert episodes == (256,256,224)[run]
        start, history = 0, []

    def checkpoint(step, rows=None, transitions=None, losses=None):
        folder = job / f"step_{step:08d}"
        if rows is not None:
            store.table(folder/"trace.csv.gz", rows, compressed=True, limit=TRACE_CAP)
            buffer = io.BytesIO()
            np.savez_compressed(buffer, **{k:np.stack([r[k] for r in transitions]) for k in transitions[0]})
            store.put(folder/"transitions.npz", buffer.getbuffer(), TRACE_CAP)
            store.table(folder/"losses.csv", losses or [dict(no_updates=True)], limit=32*1024)
        if step in SELECTION_STEPS:
            result = evaluate(store, env, meter, validation, folder/"validation", "validation", agent=agent)
            history.append(dict(step=step, rmse_w=float(np.mean([r["rmse_w"] for r in result]))))
        full = step % 1024 == 0
        if full:
            buffer = io.BytesIO()
            meta = dict(step=step, run=run, pid=os.getpid(), config_sha=config_sha, parent_sha=parent["sha256"],
                        noise=noise.state_dict(), history=history, next_integral=0.)
            torch.save(agent.checkpoint(meta), buffer)
            store.put(folder/"state.pth", buffer.getbuffer(), STATE_CAP)
        hashes = {str(p):digest(p) for p in folder.rglob("*") if p.is_file()}
        store.json(folder/"complete.json", dict(step=step, full=full, updates=agent.updates,
                   insertions=agent.replay.insertions, hashes=hashes, rows=meter.counts))
        if full:
            print(dict(arm=arm, run=run, step=step, rows=meter.counts, storage=store.used), flush=True)

    if not recovered:
        checkpoint(0)
    for step in range(start, stop, 128):
        ep = step//128
        design = dict(designs[ep], target_w=float(designs[ep]["target_w"]), initial_pitch_rad=float(designs[ep]["initial_pitch_rad"]))
        noise.reset()
        try:
            rows, transitions, losses = rollout(env, meter, "train", design, agent, training=(step, noise, expected[ep]))
            assert json_state(noise.state_dict()) == states["episodes"][ep]["after"]
            checkpoint(step+128, rows, transitions, losses)
        except Exception as error:
            store.json(job/f"failed_{step:08d}.json", dict(start_step=step, error=repr(error), rows=meter.counts))
            raise
    if stop == 1024:
        norms = [float(m.memory_weight.detach().norm()) for name in NETWORKS for m in getattr(agent,name)]
        assert all(v>0 for v in norms) if arm == "memory" else all(v==0 for v in norms)
        store.json(job/"entry.json", dict(step=stop, added_updates=agent.updates-parent["updates"], memory_weight_norms=norms))
    else:
        assert [h["step"] for h in history] == list(SELECTION_STEPS)
        best = min(history, key=lambda h:(h["rmse_w"], h["step"]))["step"]
        paths = {role:str(job/f"step_{step:08d}/state.pth") for role, step in
                 (("initial",0),("selected",best),("final",STEPS))}
        store.json(job/"result.json", dict(arm=arm, run=run, steps=stop, selected_step=best, history=history,
                   roles=paths, hashes={p:digest(p) for p in paths.values()},
                   added_updates=agent.updates-parent["updates"], added_insertions=agent.replay.insertions-parent["insertions"],
                   m_histogram=agent.replay.m_histogram.tolist()))


def entry_audit(root):
    import numpy as np
    cfg = context(root)
    zero, memory = (root/f"{arm}_run0" for arm in ARMS)
    for step in (128,256,384,512,640,768,896,1024):
        paths = [job/f"step_{step:08d}" for job in (zero,memory)]
        with np.load(paths[0]/"transitions.npz") as a, np.load(paths[1]/"transitions.npz") as b:
            assert np.array_equal(a["exploration"],b["exploration"])
            if step<=512:
                assert all(np.array_equal(a[k],b[k]) for k in a.files)
        x,y = [read_csv(p/"losses.csv") for p in paths]
        assert len(x)==len(y)
        for l,r in zip(x,y):
            assert all(l.get(k)==r.get(k) for k in ("step","indices_sha256","lengths_sha256"))
    assert all(read_json(job/"entry.json")["added_updates"]==257 for job in (zero,memory))
    Store(root).json("entry_audit.json", dict(status="passed", equivalent_first_512=True, paired_indices_and_m=True,
                     planned_budget_steps=2048, extra_model_rows=0, config_sha=digest(root/"config.yaml")))


def evaluate_stage(root, split):
    from .pitch_error_memory import PitchErrorMemory
    cfg = context(root)
    store = Store(root)
    if split == "test":
        specs = read_json(root/"test_spec.json")["cases"]
        make_bank(store, cfg["base_config"], "test", specs)
    cases = (read_json(root/"known_sources.json")["cases"] if split == "known" else
             read_json(root/f"{split}_bank/manifest.json")["cases"])
    meter = Meter(store)
    env = environment(cfg,meter)
    index = []
    cache = {}
    if split == "known":
        for ref in read_json(root/"known_sources.json")["references"]:
            arm = "zero" if ref["arm"]=="parent" else ref["arm"]
            role = "initial" if arm=="zero" else arm
            index.append(dict(arm=arm, role=role, run=ref["run"], legacy_reference=ref))
    if split != "validation":
        selection = read_json(root/"selection.json")
        for result in selection["jobs"]:
            arm,run = result["arm"],result["run"]
            for role in (("selected","final") if split=="known" else ("initial","selected","final")):
                path = result["roles"][role]
                key = arm,path
                if key not in cache:
                    folder = Path(f"evaluations/{split}/{arm}_{run}_{role}")
                    agent,_ = PitchErrorMemory.load(path,expected_arm=arm,purpose="formal")
                    evaluate(store,env,meter,cases,folder,split,agent=agent)
                    cache[key] = str(root/folder/"cases.json")
                index.append(dict(arm=arm,run=run,role=role,cases=cache[key],state_sha256=result["hashes"][path]))
    if split != "known":
        for mode in ("p","pi"):
            folder = Path(f"evaluations/{split}/{mode}")
            evaluate(store,env,meter,cases,folder,split,baseline=(cfg["base_config"]["baselines"],mode))
            index.append(dict(arm=mode,run=-1,role=mode,cases=str(root/folder/"cases.json")))
    store.json(f"{split}_index.json", index)


def pipeline(root):
    context(root)
    Store(root).json("pipeline_started.json", dict(pid=os.getpid(), start=time.time()))
    schedule = [(arm,0,1024) for arm in ARMS]+[(arm,0,STEPS) for arm in ARMS]
    schedule += [(arm,run,STEPS) for run in (1,2) for arm in ARMS]
    stages = [("worker",["--arm",a,"--run",str(r),"--stop",str(s)]) for a,r,s in schedule]
    stages.insert(2,("entry",[]))
    stages += [(mode,[]) for mode in ("select","validation","known","pretest","test","report")]
    env = os.environ.copy()
    env.update(TF_NUM_INTRAOP_THREADS="1",TF_NUM_INTEROP_THREADS="1",PYTHONHASHSEED="42")
    for i,(mode,extra) in enumerate(stages):
        start = time.time()
        command = [sys.executable,"-B","-X","utf8","-m",MODULE,mode,"--output",str(root),*extra]
        done = subprocess.run(command,env=env,cwd=PROJECT,check=False)
        Store(root).json(f"stages/{i:02d}_{mode}.json", dict(command=command, seconds=time.time()-start, returncode=done.returncode))
        done.check_returncode()
    Store(root).json("pipeline_complete.json", dict(stages=len(stages), status="complete", extra_steps=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","pipeline","worker","entry","select","validation","known","pretest","test","report"))
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--arm",choices=ARMS)
    parser.add_argument("--run",type=int,choices=range(3))
    parser.add_argument("--stop",type=int,choices=(1024,STEPS))
    args = parser.parse_args()
    root = args.output.resolve()
    if args.mode == "pipeline":
        pipeline(root)
        return
    activate_runtime(ORIGINAL/".venv/pinn_tf216")
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    if args.mode == "prepare":
        prepare(root)
    elif args.mode == "worker":
        worker(root,args.arm,args.run,args.stop)
    elif args.mode == "entry":
        entry_audit(root)
    elif args.mode in ("validation","known","test"):
        evaluate_stage(root,args.mode)
    else:
        from . import pitch_error_memory_review as review
        getattr(review,args.mode)(root)


if __name__ == "__main__":
    main()
