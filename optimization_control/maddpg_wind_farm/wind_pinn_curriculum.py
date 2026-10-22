"""Bounded wind12 curriculum reusing the verified fixed-condition trainer.

Each worker is a fresh Python process, not a model/agent delegation. Source
PINN, sampling, gates and baseline parameters freeze before learning/test.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

from .fixed_pinn_demo import activate_runtime, digest
from .wind_pinn_demo import save_json

DEFAULT = Path(__file__).parent / "configs/wind_pinn_curriculum.yaml"


def read_protocol(path):
    import yaml
    p = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    if p.get("version") != "wind_pinn_curriculum_v1" or p.get("seed") != 42:
        raise ValueError("wind curriculum version and seed 42 required")
    if p.get("selection_rule") != "lowest_validation_mean_rmse_including_initial" or p.get("test_rule") != "freeze_completed_stages_and_baselines_before_test":
        raise ValueError("validation-only selection and locked test required")
    for key in ("single_steps", "multi_steps", "expansion_steps", "eval_every"):
        if p[key] <= 0 or p[key] % p["horizon"]:
            raise ValueError("positive complete-episode budgets required")
    families = [set(p[k]) for k in ("training_fractions", "validation_fractions", "test_fractions")]
    if any(families[a] & families[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("multi-target splits must be disjoint")
    if any(not 0 < f < 1 for key in ("single_fractions", "training_fractions", "validation_fractions", "test_fractions") for f in p[key]):
        raise ValueError("targets must lie strictly inside the measured feasible path")
    return p


def execute(p, output, *, resume=False):
    import numpy as np
    import yaml
    from .fixed_curriculum import STAGES, locked_test, plot_results, audit_replay
    from .workflow import fresh_output, write_csv
    source = Path(p["source_experiment"]).resolve()
    base = yaml.safe_load((source / "training/config.yaml").read_text(encoding="utf-8"))
    if base["plant"]["source"] != "teammate_20261021_synthetic_test":
        raise ValueError("pinned wind12 synthetic integration required")
    base["environment"].pop("inflow", None)
    base["environment"].update(wind_base_m_s=9., wind_direction_rad=0., turbulence_intensity=.1,
                               wind_amplitude_m_s=0., wind_noise_std_m_s=0.)
    checks = json.loads((source / "model_checks/summary.txt").read_text(encoding="utf-8"))
    if not checks["monotone_common_pitch"]:
        raise ValueError("common-pitch path needs diagnosis before curriculum")
    low, high = checks["common_pitch_power_range_w"]
    protocol = deepcopy(p)
    for name, key in (("single_targets_w", "single_fractions"), ("multi_training_targets_w", "training_fractions"),
                      ("validation_targets_w", "validation_fractions"), ("test_targets_w", "test_fractions")):
        protocol[name] = [low + f * (high - low) for f in p[key]]
    protected = json.loads((source / "data/source_manifest.json").read_text(encoding="utf-8"))["source_hashes"]
    protected[str(source / "model/trained.keras")] = digest(source / "model/trained.keras")
    saved = dict(seed=42, protocol=protocol, base_config=base, source_hashes=protected)
    root = Path(output).resolve()
    if resume:
        if yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8")) != saved or (root / "test").exists():
            raise ValueError("resume identity changed or test already released")
    else:
        fresh_output(root, saved)
    if not all(digest(path) == h for path, h in protected.items()):
        raise ValueError("source hashes changed")
    save_json(root / "summary.txt", dict(status="running", seed=42, test_locked=True))
    results, gates = [], []
    for stage, mask in STAGES:
        targets = protocol["single_targets_w"] if stage == "single_pitch" else [None]
        current = []
        for index, target in enumerate(targets):
            directory = root / (stage + (f"_target_{index}" if target is not None else "_run_0"))
            request = root / (directory.name + "_request.json")
            value = dict(protocol=protocol, base=base, stage=stage, mask=mask, target=target, directory=str(directory))
            if request.exists():
                if json.loads(request.read_text(encoding="utf-8")) != value:
                    raise ValueError("worker request identity changed")
            else:
                save_json(request, value)
            print("Training", directory.name, flush=True)
            subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "optimization_control.maddpg_wind_farm.wind_pinn_curriculum", "worker", "--request", str(request)], check=True)
            result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
            current.append(result)
            print(json.dumps(dict(stage=stage, target_w=target, gate=result["gate"], final_over_best=result["final_over_best"])), flush=True)
        results.extend(current)
        passed = all(r["gate"]["passed"] for r in current)
        gates.append(dict(stage=stage, passed=passed, jobs=len(current)))
        write_csv(root / "metrics.csv", [dict(stage=r["stage"], run_id=r["run_id"], target_w=r["target_w"],
            selected_step=r["best"]["step"], selected_rmse_w=r["best"]["score_w"], final_rmse_w=r["final_rmse_w"],
            final_over_best=r["final_over_best"], gate_passed=r["gate"]["passed"],
            worst_tail_rmse_w=r["gate"]["worst_tail_rmse_w"], response_fraction=r["gate"]["response_fraction"]) for r in results])
        save_json(root / "stage_gates.json", gates)
        print(json.dumps(dict(stage_gate=stage, passed=passed)), flush=True)
        if not passed:
            break
    groups = locked_test(root, protocol, results)
    if not all(digest(path) == h for path, h in protected.items()):
        raise RuntimeError("source changed during curriculum")
    summary = dict(seed=42, gates=gates, jobs=len(results), physical_validation=False,
        planned_stages=[stage for stage, _ in STAGES], all_stages_passed=len(gates) == len(STAGES) and all(g["passed"] for g in gates),
        source_files_unchanged=True, test_used_for_selection=False, aggregate=groups,
        final_stable_runs=sum(r["final_over_best"] <= p["gate"]["max_final_over_best_validation_ratio"] for r in results),
        steps=sum((p["single_steps"] if r["stage"] == "single_pitch" else p["multi_steps"] if r["stage"] == "multi_pitch" else p["expansion_steps"]) for r in results),
        scope="one derived training stream per task; capability diagnostic, not multi-seed reliability")
    save_json(root / "summary.txt", summary)
    audit_replay(root)
    plot_results(root)
    print(json.dumps(summary, indent=2), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("run", "worker"))
    ap.add_argument("--protocol", default=str(DEFAULT)); ap.add_argument("--output")
    ap.add_argument("--request"); ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    sys.dont_write_bytecode = True
    if args.command == "worker":
        from .fixed_curriculum import train_job
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        train_job(request["protocol"], request["base"], request["stage"], request["mask"], request["target"], 0, request["directory"])
    else:
        p = read_protocol(args.protocol)
        activate_runtime(p["runtime_site_packages"])
        if not args.output:
            ap.error("run requires --output")
        execute(p, args.output, resume=args.resume)


if __name__ == "__main__":
    main()
