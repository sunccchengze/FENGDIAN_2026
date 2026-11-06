"""Readable paired figures from frozen residual CSV, without policy evaluation."""
import argparse
import csv
import json
from pathlib import Path

from .fixed_pinn_demo import digest


def read_csv(path):
    with Path(path).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def plot(root):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    root = Path(root)
    selection_path = root / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    histories = {r["stage"] + str(r["run_id"]): Path(r["final"]).parent / "metrics.csv" for r in selection["results"]}
    inputs = [selection_path, root / "test/metrics.csv", *histories.values()]
    hashes = {str(path): digest(path) for path in inputs}
    result = {(r["stage"], r["run_id"]): r for r in selection["results"]}
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True, sharey=True, layout="constrained")
    for row, stage in enumerate(("pitch_speed", "all")):
        for run in (0, 1, 2):
            ax = axes[row, run]
            for label, color, style in ((stage, "#236aa0", "-"), (stage + "_control", "#d88122", "--")):
                r = result[label, run]
                history = read_csv(histories[label + str(run)])
                ax.plot([int(v["steps"]) for v in history], [float(v["validation_rmse_w"]) / 1000 for v in history],
                    color=color, linestyle=style, label="Residual" if label == stage else "Same-budget control")
                ax.scatter([r["best"]["step"]], [r["best"]["score_w"] / 1000], color=color, s=35, zorder=4)
            ax.set_title(f"{'Add speed' if stage == 'pitch_speed' else 'Add yaw'} | stream {run}")
            ax.grid(alpha=.2)
            if row == 1:
                ax.set_xlabel("Additional environment steps")
            if run == 0:
                ax.set_ylabel("Validation RMSE [kW]")
    fig.suptitle("Full-authority validation | dots mark frozen selected checkpoints | synthetic PINN")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(.5, -.04), ncol=2)
    for suffix in ("png", "pdf"):
        fig.savefig(root / f"residual_paired_validation.{suffix}", dpi=180, bbox_inches="tight")
    plt.close(fig)

    rows = read_csv(root / "test/metrics.csv")

    def mean(stage, controller, run=None):
        values = [float(v["rmse_w"]) / 1000 for v in rows if v["stage"] == stage and v["controller"] == controller
                  and v["family"] != "low_wind_stress" and (run is None or int(v["run_id"]) == run)]
        return float(np.mean(values))

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharey=True, layout="constrained")
    x = np.arange(3)
    for row, stage in enumerate(("pitch_speed", "all")):
        for col, label in enumerate(("selected", "final")):
            ax = axes[row, col]
            child = [mean(stage, label, run) for run in (0, 1, 2)]
            control = [mean(stage + "_control", label, run) for run in (0, 1, 2)]
            left = ax.bar(x - .18, child, .36, color="#236aa0", label="Residual")
            right = ax.bar(x + .18, control, .36, color="#d88122", label="Same-budget control")
            ax.bar_label(left, fmt="%.1f", fontsize=8, padding=2)
            ax.bar_label(right, fmt="%.1f", fontsize=8, padding=2)
            ax.axhline(mean(stage, "pi"), color="#549750", ls="--", label="PI")
            ax.axhline(mean(stage, "p"), color="#9a5a90", ls=":", label="P")
            ax.set_title(f"{'Add speed' if stage == 'pitch_speed' else 'Add yaw'} | {label}")
            ax.set_xticks(x, ["stream 0", "stream 1", "stream 2"])
            ax.set_ylim(0, max(650, max(child + control) * 1.14))
            ax.grid(axis="y", alpha=.2)
            ax.legend(fontsize=8, loc="upper left", ncol=2)
            if col == 0:
                ax.set_ylabel("Routine independent-test RMSE [kW]")
    fig.suptitle("Paired, equal-budget frozen test | lower is better | synthetic model only")
    for suffix in ("png", "pdf"):
        fig.savefig(root / f"residual_paired_test.{suffix}", dpi=180)
    plt.close(fig)
    assert all(digest(path) == expected for path, expected in hashes.items())
    (root / "figure_inputs.json").write_text(json.dumps(dict(seed=42, input_hashes=hashes,
        source_unchanged=True, new_policy_evaluations=0, new_training_steps=0), indent=2, ensure_ascii=False),
        encoding="utf-8", newline="\n")
    print("Four paired PNG/PDF figures; frozen CSV unchanged; no policy evaluations")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True)
    plot(ap.parse_args().output)


if __name__ == "__main__":
    main()
