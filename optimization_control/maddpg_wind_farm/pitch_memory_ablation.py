"""Audit frozen memory policies and evaluate the same weights with a zero context."""
from __future__ import annotations

import argparse
from collections import defaultdict
from functools import partial
import os
from pathlib import Path
import sys

from .fixed_pinn_demo import activate_runtime
from .pitch_error_memory_review import audit_case, resolve, role_sources
from .pitch_error_memory_trial import (
    EXPERIMENTS, ORIGINAL, Store, context, digest, environment, episode_metrics,
    read_csv, read_json, rollout, size, verify,
)


FORMAL = EXPERIMENTS / "20261104_pitch_error_memory_formal"
OUTPUT = EXPERIMENTS / "20261105_pitch_memory_ablation"
PROTOCOL = Path(__file__).with_name("PITCH_ERROR_MEMORY_ABLATION_PROTOCOL.md")
SPLITS = ("known", "validation")
ROLES = ("initial", "selected", "final")
ARMS = ("memory", "zero")
NETWORKS = ("actors", "critics", "target_actors", "target_critics")
ROW_CAP = 50_000
PLANNED = 3 * 2 * 54 * 129
STORAGE_CAP = 128 * 1024**2


class AblationStore(Store):
    def __init__(self, root):
        self.root = root
        self.used = size(root)
        self.check(0)

    def check(self, extra):
        if self.used + extra > STORAGE_CAP:
            raise RuntimeError("ablation storage cap exceeded")


class Ledger:
    def __init__(self, store):
        self.store = store
        self.path = store.root / "predictor_rows.bin"
        self.count = 0
        self.active = None

    def __enter__(self):
        self.handle = self.path.open("xb", buffering=0)
        return self

    def __exit__(self, *exc):
        self.handle.close()

    def begin(self, kind):
        if kind not in SPLITS or self.active is not None or self.count + 129 > min(ROW_CAP, PLANNED):
            raise RuntimeError("unregistered episode or exhausted predictor allocation")
        self.active = kind
        self.start = self.count

    def end(self):
        self.active = None
        return self.count - self.start

    def wrap(self, predictor):
        def measured(values):
            if self.active is None or len(values) != 1 or self.count - self.start >= 129:
                raise RuntimeError("predictor row outside a registered episode")
            self.store.check(1)
            self.handle.write(b"K" if self.active == "known" else b"V")
            self.store.used += 1
            self.count += 1
            return predictor(values)
        return measured


def freeze():
    OUTPUT.mkdir(exist_ok=False)
    cfg = context(FORMAL)
    selection = read_json(FORMAL / "selection.json")
    assert selection["validation_only"] and selection["config_sha"] == digest(FORMAL / "config.yaml")
    references = {
        "known": read_json(FORMAL / "known_sources.json"),
        "validation": read_json(FORMAL / "validation_bank/manifest.json"),
    }
    verify(references["validation"]["hashes"])
    cases = {split: references[split]["cases"] for split in SPLITS}
    assert [len(cases[k]) for k in SPLITS] == [36, 18]
    assert all(c["split"] != "stress" for group in cases.values() for c in group)
    checks = [PROTOCOL, Path(__file__), Path(__file__).with_name("pitch_memory_ablation_report.py"),
              *(FORMAL / name for name in ("config.yaml", "input_lock.json", "selection.json", "known_sources.json",
                "known_index.json", "validation_index.json", "validation_bank/manifest.json", "light_manifest.csv",
                "training_manifest.csv"))]
    hashes = {str(p): digest(p) for p in checks}
    hashes.update({c["path"]: digest(c["path"]) for group in cases.values() for c in group})
    states = []
    for job in selection["jobs"]:
        arm, run = job["arm"], job["run"]
        for role in ROLES:
            path = job["roles"][role]
            sha = job["hashes"][path]
            hashes[path] = sha
            states.append(dict(arm=arm, run=run, role=role, path=path, sha256=sha))
    for run, parent in cfg["parents"].items():
        hashes[parent["path"]] = parent["sha256"]
        states.append(dict(arm="parent", run=int(run), role="initial", path=parent["path"], sha256=parent["sha256"]))

    sources = {}
    for split in SPLITS:
        entries = role_sources(FORMAL, split)
        if split == "validation":
            for run in range(3):
                initial = next(e for e in entries if (e["arm"], e["run"], e["role"]) == ("memory", run, "initial"))
                entries.append(dict(initial, arm="parent"))
        else:
            entries = [dict(e, arm="parent") if e["arm"] == "zero" and e["role"] == "initial" else e for e in entries]
        sources[split] = []
        for entry in entries:
            arm, role, run = entry["arm"], entry["role"], entry["run"]
            if arm in ARMS and role == "initial":
                continue
            if "cases" in entry:
                path = entry["cases"]
                hashes[path] = digest(path)
                if "state_sha256" in entry:
                    assert entry["state_sha256"] == next(s["sha256"] for s in states
                        if (s["arm"], s["run"], s["role"]) == (arm, run, role))
            sources[split].append(entry)
        assert len(sources[split]) == 17
    verify(hashes)
    AblationStore(OUTPUT).json("config.yaml", dict(seed=42, row_cap=ROW_CAP, planned_rows=PLANNED,
        training_steps=0, optimizer_updates=0, new_test_cases=0, storage_cap_bytes=STORAGE_CAP,
        cases=cases, sources=sources, states=states, hashes=hashes, anchor_steps=list(range(0, 128, 8))))


def frozen():
    cfg = read_json(OUTPUT / "config.yaml")
    verify(cfg["hashes"])
    assert cfg["planned_rows"] == PLANNED and cfg["row_cap"] == ROW_CAP
    return cfg


def load_state(entry):
    import torch
    path = entry["path"]
    assert digest(path) == entry["sha256"]
    state = torch.load(path, map_location="cpu", weights_only=False)
    assert state["n"] == 8 and tuple(state["config"]["action_mask"]) == (0, 1, 0)
    if entry["arm"] != "parent":
        from .pitch_error_memory import VERSION
        assert (state["version"], state["arm"], state["purpose"], state["metadata"]["run"]) == (
            VERSION, entry["arm"], "formal", entry["run"])
    return state


def inference(state, arm):
    from .algorithm import AlgorithmConfig
    from .nstep_algorithm import NStepMADDPG
    from .pitch_error_memory import PitchErrorMemory
    agent = PitchErrorMemory(AlgorithmConfig(**state["config"])) if arm != "parent" else NStepMADDPG(AlgorithmConfig(**state["config"]))
    if arm != "parent":
        agent.n = 8
        agent._attach(arm, "formal")
    for name in ("actors", "critics"):
        getattr(agent, name).load_state_dict(state[name])
        getattr(agent, name).requires_grad_(False)
    return agent


def weight_stats(entry, state, initial, selected, parent):
    import torch
    for name in NETWORKS:
        current = state[name]
        for i in range(3):
            weight = current[f"{i}.memory_weight"]
            keys = [k for k in current if k.startswith(f"{i}.") and not k.endswith("memory_weight")]
            flatten = lambda params: torch.cat([params[key].flatten().double() for key in keys])
            old = flatten(current)
            start = flatten(initial[name])
            assert torch.equal(start, flatten(parent[name]))
            if entry["role"] == "initial" or entry["arm"] == "zero":
                assert torch.count_nonzero(weight) == 0
            norm = float(torch.linalg.vector_norm(start))
            yield dict(arm=entry["arm"], run=entry["run"], role=entry["role"], net=name, turbine=i+1,
                memory_l2=float(torch.linalg.vector_norm(weight.double())), memory_max=float(weight.abs().max()),
                memory_drift_selected_l2=float(torch.linalg.vector_norm((weight-selected[name][f"{i}.memory_weight"]).double())),
                old_l2=norm, old_drift_l2=float(torch.linalg.vector_norm(old-start)),
                old_drift_relative=float(torch.linalg.vector_norm(old-start))/norm,
                old_drift_selected_l2=float(torch.linalg.vector_norm(old-flatten(selected[name]))))


def integral_stats(records):
    import numpy as np
    values = np.concatenate([row[0] for row in records])
    errors = np.concatenate([row[1] for row in records])
    quantiles = np.quantile(values, [.05, .5, .95])
    return dict(n=len(values), mean_i_rad=float(values.mean()), std_i_rad=float(values.std()),
        p05_i_rad=quantiles[0], median_i_rad=quantiles[1], p95_i_rad=quantiles[2],
        positive_edge=float(np.mean(values == .02)), negative_edge=float(np.mean(values == -.02)),
        mean_error_w=float(errors.mean()), underproduction=float(np.mean(errors < 0)),
        corr_i_error=float(np.corrcoef(values, errors)[0, 1]) if values.std() > 0 and errors.std() > 0 else None)


def add_integrals(groups, *, split, entry, case, integral, error):
    prefix = (split, entry["arm"], entry["run"], entry["role"])
    f, target, pitch = case["family"], float(case["target_w"]), case.get("initial_pitch_rad")
    for group in (("all", None, None), (f, None, None), (f, target, None), (f, target, pitch)):
        groups[prefix + group].append((integral, error))


def replay_integrals(groups, entry, state, offset, designs):
    import numpy as np
    replay = state["replay"]
    raw = replay["data"]
    sequence = replay["sequence"][:replay["size"]]
    assert np.array_equal(np.sort(sequence), np.arange(replay["insertions"]-replay["size"], replay["insertions"]))
    episodes = (sequence-offset)//128
    for ep in np.unique(episodes):
        take = episodes == ep
        target = int(round(float(raw["obs"][take, 0, 8][0]) * 15e6))
        case = designs[entry["run"], int(ep)] if ep >= 0 else dict(family="inherited_unlabelled", target_w=target)
        add_integrals(groups, split="checkpoint_replay", entry=entry, case=case, integral=raw["integral"][take, 0],
                      error=raw["obs"][take, 0, 9].astype(float)*15e6)


def probe(agent, arm, obs, executed, integral):
    import torch
    z = torch.as_tensor(integral / .02, dtype=obs.dtype)[:, None].requires_grad_(True)
    zero = torch.zeros_like(z)
    memory = arm == "memory"
    modes = (("real", z), ("zero", zero)) if memory else (("zero", None),)
    out = {}
    for mode, ctx in modes:
        policy = torch.stack([agent.policy(partial(actor, context=ctx) if memory else actor, obs[:, i])[:, 1]
                              for i, actor in enumerate(agent.actors)], dim=1)
        if mode == "real":
            out["d_pitch_d_i"] = torch.cat([torch.autograd.grad(policy[:, i].sum(), z, retain_graph=True)[0]
                                          for i in range(3)], dim=1).detach().numpy() * .11 / .02
        inputs = torch.cat((obs.flatten(1), executed.flatten(1)), dim=1).requires_grad_(True)
        values, gradients = [], []
        for i, critic in enumerate(agent.critics):
            q = critic(inputs, context=ctx) if memory else critic(inputs)
            gradient = torch.autograd.grad(q.sum(), inputs)[0][:, 45+3*i+1]
            values.append(q.detach())
            gradients.append(gradient.detach())
        out[f"pitch_{mode}"] = (policy.detach().numpy() + 1) * .11
        out[f"q_{mode}"] = torch.cat(values, dim=1).numpy()
        out[f"dq_da_{mode}"] = torch.stack(gradients, dim=1).numpy()
    return out


def offline(cfg, store):
    import numpy as np
    import torch
    from ..environments.farm_inflow import InflowTrace

    lookup = {(s["arm"], s["run"], s["role"]): s for s in cfg["states"]}
    base = read_json(FORMAL / "config.yaml")
    designs = {(int(r["run"]), int(r["episode_index"])): r for r in read_csv(FORMAL / "training_manifest.csv")}
    fragments = {(r["arm"], int(r["run"]), int(r["step"])): r for r in read_csv(FORMAL / "light_manifest.csv")}
    weights, integral_groups, probe_rows = [], defaultdict(list), []
    for run in range(3):
        parent_entry = lookup["parent", run, "initial"]
        parent = load_state(parent_entry)
        anchors, obs, act, integrals = [], [], [], []
        for arm in ARMS:
            for ep in range(128):
                source = fragments[arm, run, (ep+1)*128]
                manifest = Path(source["manifest"])
                assert digest(manifest) == source["sha256"]
                path = manifest.parent / "transitions.npz"
                assert digest(path) == read_json(manifest)["hashes"][str(path)]
                case = designs[run, ep]
                with np.load(path) as d:
                    add_integrals(integral_groups, split="formal_training", entry=dict(arm=arm, run=run, role="all"),
                        case=case, integral=d["integral"], error=d["obs"][:, 0, 9].astype(float)*15e6)
                    if arm == "memory":
                        steps = cfg["anchor_steps"]
                        obs.append(d["obs"][steps]); act.append(d["actions"][steps]); integrals.append(d["integral"][steps])
                        anchors.extend(dict(case_id=case["id"], family=case["family"], target_w=case["target_w"],
                                            initial_pitch_rad=case["initial_pitch_rad"], step=t) for t in steps)
        x, a = map(torch.from_numpy, (np.concatenate(obs), np.concatenate(act)))
        z = np.concatenate(integrals)
        common = probe(inference(parent, "parent"), "parent", x, a, z)
        for arm in ARMS:
            initial, selected, final = (load_state(lookup[arm, run, role]) for role in ROLES)
            for role, state in zip(ROLES, (initial, selected, final), strict=True):
                entry = lookup[arm, run, role]
                weights.extend(weight_stats(entry, state, initial, selected, parent))
                replay_integrals(integral_groups, entry, state, base["parents"][str(run)]["insertions"], designs)
                if role == "initial":
                    continue
                values = probe(inference(state, arm), arm, x, a, z)
                for i, anchor in enumerate(anchors):
                    for unit in range(3):
                        row = dict(arm=arm, run=run, role=role, turbine=unit+1, **anchor,
                            integral_rad=z[i], error_w=float(x[i, 0, 9])*15e6,
                            **{k: v[i, unit] for k, v in values.items()},
                            **{f"parent_{k}": v[i, unit] for k, v in common.items()})
                        probe_rows.append(row)
        print(f"Offline replay, weights and 2,048 shared decision states verified for stream {run}", flush=True)

    saved, indexes = [], {}
    for split in SPLITS:
        designs_by_id = {c["id"]: c for c in cfg["cases"][split]}
        winds = {key: InflowTrace.load(c["path"]).values.astype(np.float32) for key, c in designs_by_id.items()}
        heading = {}
        for entry in cfg["sources"][split]:
            metrics, traces = resolve(entry)
            assert set(traces) == set(winds) == {r["case_id"] for r in metrics}
            arm, run, role = (entry[k] for k in ("arm", "run", "role"))
            for row in metrics:
                case_id = row["case_id"]
                case, trace = designs_by_id[case_id], traces[case_id]
                checked = audit_case(row, trace, case, winds[case_id], arm in ARMS)
                yaw = np.array([[float(t[f"heading_{j}"]) for j in range(3)] for t in trace])
                np.testing.assert_allclose(yaw, heading.setdefault(case_id, yaw), rtol=0, atol=1e-9)
                saved.append(dict(collection=split, arm=arm, run=run, role=role, **checked))
                if arm == "memory":
                    indexes[split, run, role, case_id] = [float(trace[0][f"pitch_command_{j}"]) for j in range(3)]
                if split == "validation" and arm in ARMS:
                    add_integrals(integral_groups, split=split, entry=entry, case=case,
                        integral=np.array([float(t["integral_rad"]) for t in trace]),
                        error=np.array([float(t["decision_error_w"]) for t in trace]))
    for run in range(3):
        entry = lookup["memory", run, "initial"]
        state = load_state(entry)
        source = dict(cases=str(Path(entry["path"]).parent / "validation/cases.json"))
        assert all(not state[net][f"{i}.memory_weight"].count_nonzero() for net in NETWORKS for i in range(3))
        _, traces = resolve(source)
        for case in cfg["cases"]["validation"]:
            trace = traces[case["id"]]
            add_integrals(integral_groups, split="validation", entry=entry, case=case,
                integral=np.array([float(t["integral_rad"]) for t in trace]),
                error=np.array([float(t["decision_error_w"]) for t in trace]))
    labels = ("collection", "arm", "run", "role", "family", "target_w", "initial_pitch_rad")
    store.table("weights.csv", weights)
    store.table("integrals.csv", [dict(zip(labels, key), **integral_stats(records)) for key, records in integral_groups.items()])
    store.table("probes.csv.gz", probe_rows, compressed=True)
    store.table("saved_metrics.csv", saved)
    store.json("initial_commands.json", [{"collection": s, "run": run, "role": role, "case_id": case, "pitch": v}
               for (s, run, role, case), v in indexes.items()])
    store.json("offline.json", dict(status="passed", predictor_rows=0, anchor_states=6144, probe_rows=len(probe_rows),
        saved_cases=len(saved), weight_rows=len(weights), validated_parent_initial_weights=True,
        config_sha=digest(OUTPUT / "config.yaml"), hashes={str(OUTPUT / name): digest(OUTPUT / name) for name in
            ("weights.csv", "integrals.csv", "probes.csv.gz", "saved_metrics.csv", "initial_commands.json")}))


class ZeroContext:
    def __init__(self, policy):
        self.policy = policy

    def act(self, obs, *, integral):
        return self.policy.act(obs, integral=0.)


def closed_loop(cfg, store):
    import numpy as np
    from ..environments.farm_inflow import InflowTrace

    check = read_json(OUTPUT / "offline.json")
    assert check["status"] == "passed" and check["config_sha"] == digest(OUTPUT / "config.yaml")
    verify(check["hashes"])
    first = {(r["collection"], r["run"], r["role"], r["case_id"]): r["pitch"]
             for r in read_json(OUTPUT / "initial_commands.json")}
    runs, rows = [], []
    meter = Ledger(store)
    source = context(FORMAL)
    with meter:
        try:
            env = environment(source, meter)
            for entry in cfg["states"]:
                if entry["arm"] != "memory" or entry["role"] == "initial":
                    continue
                policy = ZeroContext(inference(load_state(entry), "memory"))
                run, role = entry["run"], entry["role"]
                for split in SPLITS:
                    for i, case in enumerate(cfg["cases"][split]):
                        trace, _, _ = rollout(env, meter, split, case, agent=policy)
                        key = (split, run, role, case["id"])
                        np.testing.assert_array_equal([trace[0][f"pitch_command_{j}"] for j in range(3)], first[key])
                        metrics = episode_metrics(trace)
                        wind = InflowTrace.load(case["path"]).values.astype(np.float32)
                        audit_case(metrics, trace, case, wind, True)
                        path = Path(f"traces/run{run}_{role}/{split}_{i:02d}.csv.gz")
                        store.table(path, [dict(r, context_input_rad=0.) for r in trace], compressed=True, limit=128*1024)
                        runs.append(dict(collection=split, run=run, role=role, case_id=case["id"],
                                         path=str(path), sha256=digest(OUTPUT / path), state_sha256=entry["sha256"]))
                        rows.append(dict(collection=split, arm="ablated", run=run, role=role, **metrics))
                    print(f"Closed-loop stream {run} {role} {split} complete, {meter.count:,} predictor rows", flush=True)
        except Exception as exc:
            store.json("failure.json", dict(error=repr(exc), predictor_rows=meter.count, completed=runs))
            raise
    assert len(runs) == 324 and meter.count == PLANNED
    ledger = meter.path.read_bytes()
    assert ledger.count(b"K") == 27864 and ledger.count(b"V") == 13932
    store.table("ablation_metrics.csv", rows)
    store.json("trajectory_manifest.json", runs)
    store.json("execution.json", dict(status="passed", episodes=len(runs), model_rows=meter.count,
        rows_known=ledger.count(b"K"), rows_validation=ledger.count(b"V"), optimizer_updates=0, new_test_cases=0,
        config_sha=digest(OUTPUT / "config.yaml"), hashes={str(OUTPUT / name): digest(OUTPUT / name) for name in
            ("predictor_rows.bin", "ablation_metrics.csv", "trajectory_manifest.json", "offline.json")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "offline", "closed", "report"))
    mode = parser.parse_args().mode
    if mode == "freeze":
        freeze()
        return
    cfg = frozen()
    store = AblationStore(OUTPUT)
    if mode == "report":
        from .pitch_memory_ablation_report import report
        report(cfg, store)
        return
    for name in ("OMP_NUM_THREADS", "TF_NUM_INTRAOP_THREADS", "TF_NUM_INTEROP_THREADS"):
        os.environ[name] = "1"
    activate_runtime(ORIGINAL / ".venv/pinn_tf216")
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    if mode == "offline":
        offline(cfg, store)
    else:
        closed_loop(cfg, store)


if __name__ == "__main__":
    main()
