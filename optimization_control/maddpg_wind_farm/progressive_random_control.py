"""Inherited pitch -> speed -> yaw training, with validation-only permission gates."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

from .fixed_pinn_demo import activate_runtime, digest
from . import random_wind_training as shared

DEFAULT = Path(__file__).parent / "configs/progressive_random_control.yaml"
VERSION = "wind12_progressive_random_v1"


def read_protocol(path):
    import yaml
    p = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    if p.get("version") != VERSION or p.get("seed") != 42:
        raise ValueError("progressive protocol and master seed 42 required")
    groups = [set(p[k]) for k in ("training_targets_w", "validation_targets_w", "test_targets_w")]
    if any(groups[a] & groups[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("training/validation/test targets must be disjoint")
    if p["run_ids"] != [0, 1, 2]:
        raise ValueError("three paired streams 0, 1, 2 required")
    if any(p[k] <= 0 or p[k] % p["horizon"] for k in ("steps_per_run", "eval_every")):
        raise ValueError("positive complete-episode budgets required")
    if p["steps_per_run"] > 16384 or p["warmup_steps"] < 0 or p["update_every"] < 1:
        raise ValueError("bounded continuation schedule required")
    if not 1 <= p["max_handover_ratio"] <= 1.05 or not 0 < p["head_max_action_error"] <= .05:
        raise ValueError("handover tolerance exceeds declared protocol")
    if p["gate"] != dict(mean_validation_rmse_w=400000., worst_validation_rmse_w=500000., max_final_over_selected=1.25):
        raise ValueError("original gates must not be relaxed")
    if set(p["stage_noise_std"]) != {s for s, _ in shared.STAGES}:
        raise ValueError("each permission stage needs an exploration schedule")
    windows = [(p["training_episode_offset"], p["training_episode_offset"] + 23000),
               (p["validation_episode_offset"], p["validation_episode_offset"] + 300),
               (p["test_episode_offset"], p["test_episode_offset"] + 300),
               (p["stress_episode"], p["stress_episode"] + 1)]
    if any(a <= 330064 or a >= b for a, b in windows) or any(max(a, c) < min(b, d)
            for i, (a, b) in enumerate(windows) for c, d in windows[i + 1:]):
        raise ValueError("fresh non-overlapping episode namespaces required")
    return p


def passes(result, p):
    """Recompute the gate rather than trusting a saved Boolean alone."""
    best = result["best"]
    return bool(result["passed"] and not result.get("handover_failed", False)
                and result["steps"] == p["steps_per_run"] and best["step"] > 0
                and best["score_w"] < result["initial_rmse_w"]
                and best["score_w"] <= p["gate"]["mean_validation_rmse_w"]
                and max(r["rmse_w"] for r in best["validation"]) <= p["gate"]["worst_validation_rmse_w"]
                and result["final_over_best"] <= p["gate"]["max_final_over_selected"])


def verify_hashes(hashes):
    if not all(digest(f) == h for f, h in hashes.items()):
        raise ValueError("pinned source or checkpoint changed")


def prepare(p, output):
    import yaml
    source = Path(p["bootstrap_experiment"]).resolve()
    selection = json.loads((source / "selection.json").read_text(encoding="utf-8"))
    bootstrap = {}
    for run in p["run_ids"]:
        matches = [r for r in selection["results"] if r["stage"] == "pitch" and r["run_id"] == run]
        if len(matches) != 1:
            raise ValueError("one pitch checkpoint per bootstrap stream required")
        r = matches[0]; verify_hashes(r["hashes"])
        checkpoint = r["best"]["checkpoint"]
        bootstrap[str(run)] = dict(checkpoint=checkpoint, sha256=digest(checkpoint), stage="pitch", run_id=run,
                                   cumulative_steps=r["best"]["step"])
    root = shared.prepare(p, output)
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    saved["bootstrap"] = bootstrap
    protected = [str(source / "selection.json")] + [v["checkpoint"] for v in bootstrap.values()]
    protected += [str(Path(__file__).parent / f) for f in
                  ("progressive_random_control.py", "random_wind_training.py", "algorithm.py", "controllers.py", "workflow.py")]
    saved["source_hashes"].update({str(Path(f).resolve()): digest(f) for f in protected})
    (root / "config.yaml").write_text(yaml.safe_dump(saved, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
    # Preflight all possible phases before any training; this does not open their gates.
    for phase, (stage, _) in enumerate(shared.STAGES):
        phase_p = deepcopy(p); phase_p["training_episode_offset"] += phase * 10000
        rows = shared.preflight_training_winds(phase_p, root)
        shared.write_csv(root / f"{stage}_wind_preflight.csv", rows)
    shared.write_json(root / "summary.txt", dict(seed=42, status="prepared", test_locked=True,
                                               bootstrap=bootstrap, permission_order=[s for s, _ in shared.STAGES]))
    return root


def parent_for_worker(root, stage, run_id):
    import yaml
    root = Path(root)
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8")); p = saved["protocol"]
    if p["version"] != VERSION or run_id not in p["run_ids"] or stage not in dict(shared.STAGES):
        raise ValueError("unknown progressive training job")
    if (root / "test").exists() or (root / "selection.json").exists():
        raise ValueError("selection frozen; further training is prohibited")
    verify_hashes(saved["source_hashes"])
    phase = [s for s, _ in shared.STAGES].index(stage)
    if phase == 0:
        return saved["bootstrap"][str(run_id)]
    previous = shared.STAGES[phase - 1][0]
    results = []
    for run in p["run_ids"]:
        path = root / f"{previous}_run_{run}/result.json"
        if not path.exists():
            raise ValueError("all parent streams must complete and pass before adding one channel")
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["stage"] != previous or result["run_id"] != run or not passes(result, p):
            raise ValueError("all parent streams must pass; manual worker cannot bypass the gate")
        verify_hashes(result["hashes"]); results.append(result)
    r = next(r for r in results if r["run_id"] == run_id)
    checkpoint = r["best"]["checkpoint"]
    return dict(checkpoint=checkpoint, sha256=digest(checkpoint), stage=previous, run_id=run_id,
                parent_result_sha256=digest(root / f"{previous}_run_{run_id}/result.json"),
                cumulative_steps=r["lineage"]["cumulative_parent_steps"] + r["best"]["step"])


def initialize_heads(agent, mask, *, max_action_error=.05, strict=True):
    """Fit only the newly enabled output row on training replay, never hidden layers.

    The held-out subset checks transfer approximation, not control performance.
    Adam/critic/replay state is retained. Disabled output rows had zero policy
    gradients in the parent. No new layers or checkpoint formats are introduced.
    """
    import numpy as np
    import torch
    old = tuple(agent.config.action_mask); new = tuple(mask)
    allowed = {(0, 1, 0): (0, 1, 1), (0, 1, 1): (1, 1, 1)}
    if new == old:
        if old != (0, 1, 0):
            raise ValueError("only pitch bootstrap may retain the same permissions")
        return []
    if allowed.get(old) != new:
        raise ValueError("exactly one channel must open, in speed then yaw order")
    channel = next(i for i in range(3) if not old[i] and new[i])
    if agent.replay.size < 128:
        raise ValueError("training replay required for inherited head validation")
    # Deterministic capped sample; no replay RNG is consumed by initialization.
    indices = np.linspace(0, agent.replay.size - 1, min(5120, agent.replay.size), dtype=int)
    held = np.arange(len(indices)) % 5 == 0
    reports = []
    for kind in ("actors", "target_actors"):
        for i, actor in enumerate(getattr(agent, kind)):
            states = torch.as_tensor(agent.replay.data["obs"][indices, i], device=agent.device)
            before = {k: v.detach().clone() for k, v in actor.state_dict().items()}
            with torch.no_grad():
                teacher = agent.policy(actor, states)[:, channel]
                head = actor[-2]
                if channel == 0:
                    head.weight[channel].zero_()
                    head.bias[channel].copy_(torch.atanh(teacher[0].clamp(-.999999, .999999)))
                else:
                    features = actor[:-2](states).double()
                    design = torch.cat((features, torch.ones((len(states), 1), device=agent.device, dtype=torch.float64)), dim=1)
                    fit = torch.as_tensor(~held, device=agent.device)
                    ridge = 1e-6 * torch.eye(design.shape[1], dtype=torch.float64, device=agent.device)
                    solution = torch.linalg.solve(design[fit].T @ design[fit] + ridge,
                        design[fit].T @ torch.atanh(teacher[fit].clamp(-.999999, .999999)).double())
                    head.weight[channel].copy_(solution[:-1].float()); head.bias[channel].copy_(solution[-1].float())
                predicted = actor(states)[:, channel]
                error = (predicted - teacher).abs().cpu().numpy()
            # Verify all hidden parameters and all previously learned output rows.
            for key, value in actor.state_dict().items():
                expected = before[key]
                if key in ("4.weight", "4.bias"):
                    keep = [j for j in range(3) if j != channel]
                    if not torch.equal(value[keep], expected[keep]):
                        raise AssertionError("handover changed an existing output row")
                elif not torch.equal(value, expected):
                    raise AssertionError("handover changed a hidden layer")
            reports.append(dict(network=kind, agent=i, new_channel=channel,
                fit_rows=int((~held).sum()), held_out_rows=int(held.sum()),
                fit_max_action_error=float(error[~held].max()), held_out_max_action_error=float(error[held].max()),
                hidden_and_existing_rows_unchanged=True))
    if strict and max(r["held_out_max_action_error"] for r in reports) > max_action_error:
        raise ValueError("new head cannot match scheduled parent within held-out tolerance; no permission granted")
    agent.config = replace(agent.config, action_mask=new,
                           speed_reference_schedule=None if new[2] else agent.config.speed_reference_schedule)
    return reports


def initialize_stage(root, stage, run_id, cfg, env, parent):
    import numpy as np
    from .algorithm import MADDPG
    agent, meta = MADDPG.load(parent["checkpoint"])
    if digest(parent["checkpoint"]) != parent["sha256"]:
        raise ValueError("parent checkpoint identity changed")
    # Environment dynamics and scales must stay identical; only permission changes.
    old_env, new_env = deepcopy(meta["config"]["environment"]), deepcopy(cfg["environment"])
    old_env.pop("control_mask"); new_env.pop("control_mask")
    if old_env != new_env or meta["config"]["plant"] != cfg["plant"]:
        raise ValueError("inheritance requires identical plant, dynamics, references and observation scales")
    parent_rows, _ = shared.rollout(meta["config"], shared.cases(root, "validation"), agent=agent)
    p = __import__("yaml").safe_load((Path(root) / "config.yaml").read_text(encoding="utf-8"))["protocol"]
    before_mask = list(agent.config.action_mask)
    reports = initialize_heads(agent, env.control_mask.astype(int).tolist(), max_action_error=p["head_max_action_error"], strict=False)
    lineage = dict(parent_checkpoint=parent["checkpoint"], parent_sha256=parent["sha256"], parent_stage=parent["stage"],
                   run_id=run_id, previous_mask=before_mask, new_mask=list(map(int, env.control_mask)),
                   parent_validation_rmse_w=float(np.mean([r["rmse_w"] for r in parent_rows])),
                   inherited_replay_size=agent.replay.size, inherited_updates=agent.updates,
                   cumulative_parent_steps=parent["cumulative_steps"], head_initialization=reports,
                   head_fit_passed=all(r["held_out_max_action_error"] <= p["head_max_action_error"] for r in reports),
                   critics_optimizers_replay_inherited=True, fit_source="parent_training_replay_only")
    return agent, lineage


def execute(root):
    import yaml
    root = Path(root).resolve()
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8")); p = saved["protocol"]
    if (root / "test").exists() or (root / "selection.json").exists():
        raise ValueError("experiment frozen; use replay, never append training")
    verify_hashes(saved["source_hashes"])
    shared.sampled_ranges(saved["base_config"], shared.cases(root, "validation"), root / "validation_sampled_ranges.csv")
    results, gates = [], []
    for stage, _ in shared.STAGES:
        current = []
        for run in p["run_ids"]:
            subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", __spec__.name,
                            "worker", "--output", str(root), "--stage", stage, "--run-id", str(run)], check=True)
            r = json.loads((root / f"{stage}_run_{run}/result.json").read_text(encoding="utf-8"))
            current.append(r)
        results.extend(current)
        gate = dict(stage=stage, passed=all(passes(r, p) for r in current), passed_runs=sum(passes(r, p) for r in current), runs=len(current))
        gates.append(gate)
        shared.write_csv(root / "metrics.csv", [dict(stage=r["stage"], run_id=r["run_id"],
            initial_validation_rmse_w=r["initial_rmse_w"], selected_step=r["best"]["step"],
            selected_validation_rmse_w=r["best"]["score_w"], worst_validation_rmse_w=max(v["rmse_w"] for v in r["best"]["validation"]),
            final_over_selected=r["final_over_best"], additional_steps=r["steps"], cumulative_steps=r["cumulative_steps"],
            passed=passes(r, p)) for r in results])
        shared.write_json(root / "stage_gates.json", gates)
        print("Permission gate", json.dumps(gate), flush=True)
        if not gate["passed"]:
            break
    hashes = {f: h for r in results for f, h in r["hashes"].items()}
    hashes.update({r["lineage"]["parent_checkpoint"]: r["lineage"]["parent_sha256"] for r in results})
    shared.write_json(root / "selection.json", dict(seed=42, results=results, gates=gates,
        bank_sha256=digest(root / "bank/manifest.json"), hashes=hashes, root_config_sha256=digest(root / "config.yaml")))
    shared.test_locked(root)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("prepare", "run", "all", "worker", "replay", "plot"))
    ap.add_argument("--protocol", default=str(DEFAULT)); ap.add_argument("--output", required=True)
    ap.add_argument("--stage", choices=[s for s, _ in shared.STAGES], default="pitch")
    ap.add_argument("--run-id", type=int, default=0); ap.add_argument("--replay-output")
    args = ap.parse_args(); p = read_protocol(args.protocol)
    activate_runtime(p["runtime_site_packages"]); sys.dont_write_bytecode = True
    root = Path(args.output)
    if args.command in ("prepare", "all"):
        root = prepare(p, root)
    if args.command in ("run", "all"):
        execute(root)
    if args.command == "worker":
        shared.train_job(root, args.stage, dict(shared.STAGES)[args.stage], args.run_id)
    if args.command == "plot":
        shared.plot(root)
    if args.command == "replay":
        if not args.replay_output:
            ap.error("replay requires a new --replay-output directory")
        shared.replay(root, args.replay_output, args.stage, args.run_id)


if __name__ == "__main__":
    main()
