"""Draw inherited-control evidence from frozen CSV files with Matplotlib."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def plot(root):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    root = Path(root)
    selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    for result in selection["results"]:
        history = read(Path(result["final"]).parent / "metrics.csv")
        x = [int(r["steps"]) for r in history]
        label = f"{result['stage']} / 训练流{result['run_id']}"
        axes[0].plot(x, [float(r["validation_rmse_w"]) / 1000 for r in history], "o-", label=label)
        axes[1].plot(x, [float(r["worst_validation_rmse_w"]) / 1000 for r in history], "o-", label=label)
    for ax, threshold, ylabel in zip(axes, (400, 500), ("平均验证 RMSE / kW", "最差场景验证 RMSE / kW")):
        ax.axhline(threshold, color="black", linestyle="--", label=f"门槛 {threshold} kW")
        ax.set(xlabel="本层新增训练步数", ylabel=ylabel)
        ax.grid(alpha=.25); ax.legend(fontsize=8)
    fig.suptitle("继承桨距策略后继续训练：平均误差与最差场景必须同时达标\n冻结合成 PINN；验证选模；不代表真实风场精度", fontsize=12)
    fig.tight_layout(); fig.savefig(root / "progressive_validation.png", dpi=160); plt.close(fig)
    metrics = read(root / "test/metrics.csv")
    stages = list(dict.fromkeys(r["stage"] for r in selection["results"]))
    fig, axes = plt.subplots(len(stages), 1, figsize=(12, 4.8 * len(stages)), squeeze=False)
    families = ("stationary", "ramp", "gust", "low_wind_stress")
    names = ("平稳湍流", "慢变", "阵风", "低风高目标压力场")
    labels = {"parent": "继承前策略", "selected": "验证选中 MADDPG", "p": "P 组合基线", "pi": "PI 组合基线"}
    for stage, ax in zip(stages, axes[:, 0]):
        for index, (controller, label) in enumerate(labels.items()):
            means, sds = [], []
            for family in families:
                part = [r for r in metrics if r["stage"] == stage and r["controller"] == controller and r["family"] == family]
                per_run = [np.mean([float(r["rmse_w"]) for r in part if r["run_id"] == run]) / 1000
                           for run in sorted({r["run_id"] for r in part})]
                means.append(float(np.mean(per_run)))
                sds.append(float(np.std(per_run, ddof=1)) if len(per_run) > 1 else 0.)
            ax.bar(np.arange(4) + (index - 1.5) * .19, means, .19, yerr=sds, capsize=3, label=label)
        ax.set(xticks=np.arange(4), xticklabels=names, ylabel="全回合 RMSE / kW", title=stage + "：同入口、同目标、同初始状态及执行器")
        ax.grid(axis="y", alpha=.25); ax.legend(fontsize=9)
    fig.suptitle("独立测试：按风况分组；误差棒为三条训练流的样本标准差\n压力场单列，不计入常规均值；P/PI为共享的确定性组合基线", fontsize=12)
    fig.tight_layout(); fig.savefig(root / "progressive_test_families.png", dpi=160); plt.close(fig)
    (root / "figure_notes.md").write_text(
        "# 本轮图表解释\n\n"
        "1. `progressive_validation.png`：左图展示各训练流的平均验证误差，右图展示最差验证场景误差。"
        "两条门槛必须同时满足；平均分变好不能掩盖某类风况失败，曲线反弹说明终点与最优检查点需要区分。"
        "横轴从继承已有策略后重新计数，不代表从零训练。\n\n"
        "2. `progressive_test_families.png`：在策略冻结后，以新的风况与功率目标比较继承前策略、选中MADDPG及P/PI。"
        "同组控制器共享风轨迹、目标、初始运行点及执行器。误差棒只表示三次训练之间的差异，"
        "不是置信区间；P/PI未随机训练，不绘制虚构训练方差。压力场与常规三类分开解释。\n\n"
        "本轮全部图表由Python/Matplotlib从CSV绘制，未使用AI图像生成；结果仅适用于冻结的合成联调网络。\n",
        encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument("--output", required=True)
    plot(ap.parse_args().output)


if __name__ == "__main__":
    main()
