"""Validation-only closed-loop channel swaps; never reads the old test split."""
from __future__ import annotations

import argparse
from copy import deepcopy
import itertools
import json
from pathlib import Path

from .fixed_pinn_demo import activate_runtime, digest
from .progressive_random_control import verify_hashes
from . import random_wind_training as shared

DEFAULT = Path(__file__).parent / "configs/residual_stability_diagnostic.yaml"


class MixedPolicy:
    """Recompute BOTH endpoint policies at each current closed-loop observation."""
    def __init__(self, selected, final, cfg, mixture="FFF", ablation=None):
        import numpy as np
        if mixture not in ("".join(p) for p in itertools.product("SF", repeat=3)):
            raise ValueError("yaw/pitch/speed mixture must contain three S/F letters")
        if ablation not in (None, "zero_yaw", "zero_speed", "zero_both"):
            raise ValueError("unknown residual ablation")
        self.selected, self.final = selected, final
        self.choose_final = np.array([v == "F" for v in mixture])
        self.ablation = ablation
        self.width = np.asarray(cfg["environment"]["action_high"]) - cfg["environment"]["action_low"]
        self.corrections, self.raw, self.drift = [], [], []

    def act(self, obs):
        import numpy as np
        import torch
        selected = self.selected.act(obs)
        final = self.final.act(obs)
        total = np.where(self.choose_final, final, selected).astype(np.float32)
        with torch.no_grad():
            x = torch.as_tensor(obs, device=self.final.device)
            baseline = self.final.compose(torch.zeros((3, 3), device=self.final.device), x).cpu().numpy()
            selected_raw = torch.stack([actor(x[i]) for i, actor in enumerate(self.selected.actors)]).cpu().numpy()
            final_raw = torch.stack([actor(x[i]) for i, actor in enumerate(self.final.actors)]).cpu().numpy()
        raw = np.where(self.choose_final, final_raw, selected_raw)
        if self.ablation in ("zero_yaw", "zero_both"):
            total[:, 0] = baseline[:, 0]
            raw[:, 0] = 0.
        if self.ablation in ("zero_speed", "zero_both"):
            total[:, 2] = baseline[:, 2]
            raw[:, 2] = 0.
        correction = (total - baseline) * self.width / 2
        correction[:, 1] = 0.
        self.corrections.append(correction)
        self.raw.append(raw * np.asarray(self.final.config.action_mask))
        self.drift.append((final - selected) * self.width / 2)
        return total

    def summary(self):
        import numpy as np
        correction, raw, drift = map(np.asarray, (self.corrections, self.raw, self.drift))
        return dict(speed_correction_rms_rad_s=float(np.sqrt(np.mean(correction[..., 2] ** 2))),
            speed_correction_max_rad_s=float(np.abs(correction[..., 2]).max()),
            yaw_correction_rms_rad=float(np.sqrt(np.mean(correction[..., 0] ** 2))),
            yaw_correction_max_rad=float(np.abs(correction[..., 0]).max()),
            speed_raw_saturation=float(np.mean(np.abs(raw[..., 2]) >= .99)),
            yaw_raw_saturation=float(np.mean(np.abs(raw[..., 0]) >= .99)),
            yaw_selected_final_drift_rms_rad=float(np.sqrt(np.mean(drift[..., 0] ** 2))),
            pitch_selected_final_drift_rms_rad=float(np.sqrt(np.mean(drift[..., 1] ** 2))),
            speed_selected_final_drift_rms_rad_s=float(np.sqrt(np.mean(drift[..., 2] ** 2))))


def prepare(p, output):
    import yaml
    if p["seed"] != 42 or p["version"] != "residual_stability_diagnostic_v1" or p["split"] != "validation":
        raise ValueError("fixed seed42 validation-only diagnostic required")
    source = Path(p["source_experiment"]).resolve()
    saved = yaml.safe_load((source / "config.yaml").read_text(encoding="utf-8"))
    selection = json.loads((source / "selection.json").read_text(encoding="utf-8"))
    verify_hashes(saved["source_hashes"])
    verify_hashes(selection["hashes"])
    if digest(source / "config.yaml") != selection["root_config_sha256"] or digest(source / "bank/manifest.json") != selection["bank_sha256"]:
        raise ValueError("old validation bank or config identity changed")
    jobs = []
    for run in p["run_ids"]:
        for stage in ("all", "all_control"):
            r = next(r for r in selection["results"] if r["stage"] == stage and r["run_id"] == run)
            jobs.append(dict(stage=stage, run_id=run, config=r["config"], selected=r["best"]["checkpoint"], final=r["final"]))
    hashes = deepcopy(saved["source_hashes"])
    files = [source / n for n in ("config.yaml", "metrics.csv", "summary.txt", "selection.json", "bank/manifest.json")]
    files += [Path(__file__), DEFAULT, Path(__file__).with_name("RESIDUAL_STABILITY_DIAGNOSTIC.md")]
    files += [Path(job[label]) for job in jobs for label in ("selected", "final")]
    hashes.update({str(path.resolve()): digest(path) for path in files})
    return shared.fresh(output, dict(seed=42, protocol=p, jobs=jobs, source_hashes=hashes)).resolve()


def execute(root):
    import numpy as np
    import torch
    import yaml
    from .residual_algorithm import ResidualMADDPG
    root = Path(root)
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    p = saved["protocol"]
    verify_hashes(saved["source_hashes"])
    if (root / "summary.txt").exists():
        raise ValueError("completed diagnostic is immutable; do not append candidates")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    bank = shared.cases(p["source_experiment"], "validation")
    if len(bank) != 6:
        raise ValueError("frozen six-case validation bank required")
    aggregates, case_metrics, steps = [], [], 0
    for job in saved["jobs"]:
        selected, _ = ResidualMADDPG.load(job["selected"])
        final, _ = ResidualMADDPG.load(job["final"])
        variants = [(mix, mix, None) for mix in p["mixtures"]] + [(name, "FFF", name) for name in p["ablations"]]
        if job["stage"] == "all_control":
            variants = [("selected", "SSS", None), ("final", "FFF", None)]
        for name, mixture, ablation in variants:
            policy = MixedPolicy(selected, final, job["config"], mixture, ablation)
            rows, _ = shared.rollout(job["config"], bank, agent=policy)
            tags = dict(stage=job["stage"], run_id=job["run_id"], variant=name)
            case_metrics.extend(dict(**tags, **row) for row in rows)
            steps += sum(len(wind.values) - 1 for _, wind in bank)
            aggregate = dict(**tags, mean_rmse_w=float(np.mean([r["rmse_w"] for r in rows])),
                worst_rmse_w=max(r["rmse_w"] for r in rows), tail_rmse_w=float(np.mean([r["tail_rmse_w"] for r in rows])),
                **policy.summary())
            aggregates.append(aggregate)
            print(json.dumps({k: aggregate[k] for k in ("stage", "run_id", "variant", "mean_rmse_w", "worst_rmse_w")}), flush=True)
    for row in aggregates:
        label = "FFF" if row["stage"] == "all" else "final"
        reference = next(r for r in aggregates if r["stage"] == row["stage"] and r["run_id"] == row["run_id"] and r["variant"] == label)
        row["improvement_over_final_w"] = reference["mean_rmse_w"] - row["mean_rmse_w"]
    assert steps <= p["max_environment_steps"] and len(case_metrics) <= p["max_policy_case_rollouts"]
    verify_hashes(saved["source_hashes"])
    shared.write_csv(root / "metrics.csv", aggregates)
    shared.write_csv(root / "case_metrics.csv", case_metrics)
    summary = dict(seed=42, completed=True, new_training_steps=0, diagnostic_environment_steps=steps,
        policy_variants=len(aggregates), case_rollouts=len(case_metrics), test_split_read=False,
        source_files_unchanged=True, protected_files=len(saved["source_hashes"]), aggregate=aggregates,
        attribution="Closed-loop interactions are non-additive; channel interventions do not prove a unique cause")
    shared.write_json(root / "summary.txt", summary)
    plot(root, aggregates)


def plot(root, rows):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    variants = ["SSS", "SSF", "SFS", "SFF", "FSS", "FSF", "FFS", "FFF", "zero_yaw", "zero_speed", "zero_both"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True, layout="constrained")
    for run, ax in enumerate(axes):
        data = [next(r for r in rows if r["stage"] == "all" and r["run_id"] == run and r["variant"] == variant) for variant in variants]
        ax.barh(np.arange(len(data)), [r["mean_rmse_w"] / 1000 for r in data], color=["#ca694d" if r["variant"] == "FFF" else "#3f81a9" for r in data])
        ax.set_yticks(np.arange(len(data)), variants)
        ax.invert_yaxis()
        ax.set_title(f"stream {run}")
        ax.set_xlabel("Validation mean RMSE [kW]")
        ax.grid(axis="x", alpha=.2)
    fig.suptitle("Current-observation closed-loop swaps: yaw / pitch / speed | S=selected, F=final")
    fig.savefig(Path(root) / "channel_swaps.png", dpi=180)
    fig.savefig(Path(root) / "channel_swaps.pdf")
    plt.close(fig)


def main():
    import yaml
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--protocol", default=str(DEFAULT))
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    p = yaml.safe_load(Path(args.protocol).read_text(encoding="utf-8"))
    activate_runtime(p["runtime_site_packages"])
    root = prepare(p, args.output)
    execute(root)


if __name__ == "__main__":
    main()
