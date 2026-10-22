"""Writes a NEW replay directory from a portable handoff; never trains or overwrites."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys


def resolve_recorded(root, value):
    value = str(value).replace("\\", "/")
    for marker in ("optimization_control/", "pinn/"):
        if marker in value:
            p = root / value[value.index(marker):]
            break
    else:
        p = root / value
    from .fixed_pinn_demo import resolve_team_path
    p = resolve_team_path(p).resolve()
    if not p.is_relative_to(root) or not p.exists():
        raise ValueError(f"missing/out-of-root handoff dependency: {value}")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--experiment", default="20261007_fixed_pinn_curriculum")
    ap.add_argument("--stage", default="multi_pitch")
    ap.add_argument("--run-id", type=int, default=1)
    ap.add_argument("--checkpoint", choices=("initial", "selected", "final"), default="selected")
    ap.add_argument("--target-w", type=float)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    root = Path(a.root).resolve()
    sys.path.insert(0, str(root))
    from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
    activate_runtime(root / ".venv/pinn_tf216")
    import numpy as np
    import torch
    import yaml
    from optimization_control.maddpg_wind_farm.algorithm import MADDPG
    from optimization_control.maddpg_wind_farm.fixed_curriculum import evaluate, attach_settings
    from optimization_control.maddpg_wind_farm.workflow import build_env, write_csv, fresh_output
    torch.set_num_threads(1)
    exp = root / "optimization_control/experiments" / a.experiment
    selection = json.loads((exp / "selection.json").read_text(encoding="utf-8-sig"))
    matches = [r for r in selection["results"] if r["stage"] == a.stage and r["run_id"] == a.run_id
               and (a.target_w is None or r["target_w"] == a.target_w)]
    if len(matches) != 1:
        raise ValueError("selection must identify one strategy; use --target-w for single_pitch")
    record = matches[0]
    cfg = deepcopy(record["config"])
    for key in ("run_dir", "script"):
        cfg["plant"]["backend"][key] = str(resolve_recorded(root, cfg["plant"]["backend"][key]))
    checkpoint = resolve_recorded(root, record["best"]["checkpoint"] if a.checkpoint == "selected" else record[a.checkpoint])
    actual_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    expected = {resolve_recorded(root, p): h for p, h in record["hashes"].items()}
    if expected[checkpoint] != actual_hash:
        raise ValueError("checkpoint differs from frozen experiment")
    protocol = yaml.safe_load((exp / "config.yaml").read_text(encoding="utf-8-sig"))["protocol"]
    targets = [record["target_w"]] if record["target_w"] is not None else protocol["test_targets_w"]
    pitches = protocol["test_initial_pitch_rad"]
    output = fresh_output(a.output, dict(seed=42, source_experiment=a.experiment, stage=a.stage,
        run_id=a.run_id, checkpoint=a.checkpoint, checkpoint_sha256=actual_hash, targets_w=targets,
        initial_pitch_rad=pitches, purpose="frozen_strategy_replay_not_new_training"))
    env = build_env(cfg)
    attach_settings(env, cfg)
    agent, _ = MADDPG.load(checkpoint)
    rows, traces = [], []
    for method in (a.checkpoint, "P", "PI"):
        part, trajectory = evaluate(env, agent if method == a.checkpoint else None, targets,
            split="test", pitches=pitches, mode=None if method == a.checkpoint else method.lower(), capture=True)
        rows.extend(dict(method=method, **r) for r in part)
        traces.extend(dict(method=method, **r) for r in trajectory)
    write_csv(output / "metrics.csv", rows)
    write_csv(output / "trajectories.csv", traces)
    summary = {method: float(np.mean([r["rmse_w"] for r in rows if r["method"] == method])) / 1000
               for method in (a.checkpoint, "P", "PI")}
    (output / "summary.txt").write_text(json.dumps(dict(rmse_kw=summary, scope="synthetic_fixed_condition_only"),
        ensure_ascii=False, indent=2), encoding="utf-8")
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == actual_hash
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
