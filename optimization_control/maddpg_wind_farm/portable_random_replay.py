"""Replay frozen random-wind policies from a relocated bundle; only new output is written."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import json
from pathlib import Path
import sys

from .fixed_pinn_demo import activate_runtime, digest


def recorded_path(root, value):
    normalized = str(value).replace("\\", "/")
    matches = [normalized.index(marker) for marker in ("optimization_control/", "pinn/") if marker in normalized]
    if not matches:
        raise ValueError("Not a recorded project dependency: " + str(value))
    path = (root / normalized[min(matches):]).resolve()
    if not path.is_relative_to(root) or not path.exists():
        raise ValueError("Missing or out-of-root portable dependency: " + str(value))
    return path


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--runtime", type=Path, default=Path(".venv/pinn_tf216"))
    parser.add_argument("--run-id", type=int, choices=(0, 1, 2), default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("A new replay output directory is required")
    activate_runtime(args.runtime)
    import torch
    import yaml
    from .algorithm import MADDPG
    from .random_wind_training import cases, rollout, write_csv, write_json
    torch.set_num_threads(1)
    source = root / "optimization_control/experiments/20261022_random_wind_training"
    config = yaml.safe_load((source / "config.yaml").read_text(encoding="utf-8"))
    selection = json.loads((source / "selection.json").read_text(encoding="utf-8"))
    records = [r for r in selection["results"] if r["stage"] == "pitch" and r["run_id"] == args.run_id]
    if len(records) != 1:
        raise ValueError("Exactly one frozen pitch policy required")
    record = records[0]
    protected = {recorded_path(root, k): h for k, h in {**config["source_hashes"], **record["hashes"]}.items()}
    if any(digest(k) != h for k, h in protected.items()) or digest(source / "bank/manifest.json") != selection["bank_sha256"]:
        raise ValueError("Frozen model, source, bank or checkpoint identity changed")
    cfg = deepcopy(record["config"])
    for key in ("run_dir", "script"):
        cfg["plant"]["backend"][key] = str(recorded_path(root, cfg["plant"]["backend"][key]))
    checkpoint = recorded_path(root, record["best"]["checkpoint"])
    agent, _ = MADDPG.load(checkpoint)
    bank = cases(source, "test", allow_test=True)
    actual, metrics = [], []
    for method in ("selected", "fixed", "p", "pi"):
        rows, traces = rollout(cfg, bank, agent=agent if method == "selected" else None,
                               mode=None if method == "selected" else method, capture=True)
        tags = dict(stage="pitch", run_id=args.run_id if method == "selected" else -1, controller=method)
        metrics.extend(dict(**tags, **r) for r in rows)
        actual.extend(dict(**tags, **r) for r in traces)
    text_fields = {"case_id", "split", "family", "stage", "controller"}
    with (source / "test/trajectories.csv").open(encoding="utf-8", newline="") as f:
        expected = [{k: v if k in text_fields else float(v) for k, v in row.items()} for row in csv.DictReader(f)
                    if row["stage"] == "pitch" and ((row["controller"] == "selected" and int(row["run_id"]) == args.run_id)
                    or (row["controller"] in ("fixed", "p", "pi") and int(row["run_id"]) == -1))]
    if actual != expected:
        raise AssertionError("Relocated replay differs from frozen trajectories")
    if any(digest(k) != h for k, h in protected.items()):
        raise ValueError("Portable replay changed a protected input")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "config.yaml", dict(seed=42, run_id=args.run_id, root=str(root),
        checkpoint=str(checkpoint), model_dir=cfg["plant"]["backend"]["run_dir"], new_training=False))
    write_csv(output / "metrics.csv", metrics)
    write_csv(output / "trajectories.csv", actual)
    result = dict(seed=42, run_id=args.run_id, rows=len(actual), metric_rows=len(metrics), full_trace_equal=True,
                  protected_inputs_unchanged=True, relocated_model=True, new_training=False, physical_validation=False)
    write_json(output / "summary.txt", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
