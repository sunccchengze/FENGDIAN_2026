# -*- coding: utf-8 -*-
"""分析一次训练结果：loss 曲线、留出集误差、按工况分档的误差归因、出图。

需要 TF 环境，请用 pinn_wind_data\\.venv-tf 的 python 运行：

    pinn_wind_data\\.venv-tf\\Scripts\\python.exe pinn_wind_data\\analyze_training.py

默认取 bundle 下最新的 training_* 目录。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
PINN_DIR = PROJECT / "PINNs_multi_turbine_wake_simulation-outputchange"
OUT = HERE / "out"
FIG = OUT / "figures"
TURBINE = HERE / "turbine"
CSV = OUT / "cases_wind.csv"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

R = 125.88 / 2.0
OUTPUT_NAMES = ["P1", "P2", "P3", "Ueff1", "Ueff2", "Ueff3"]


def latest_run(bundle: Path) -> Path:
    # 注意：glob("training_*") 也会命中 training_data_template.csv，必须过滤成目录
    runs = [p for p in bundle.glob("training_*")
            if p.is_dir() and (p / "training_report.json").is_file()]
    if not runs:
        raise SystemExit(f"{bundle} 下没有已完成的训练目录")
    runs.sort(key=lambda p: (p / "training_report.json").stat().st_mtime)
    return runs[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, help="指定 training_时间戳 目录")
    ap.add_argument("--bundle", type=Path, default=None)
    args = ap.parse_args()

    sys.path.insert(0, str(PINN_DIR))
    import modify_pinn_wind_io as io

    bundle = args.bundle or (PINN_DIR / "OutputChange" / "wind_iochanged_9ms")
    run = args.run.resolve() if args.run else latest_run(bundle)
    print(f"分析目录: {run}")

    tf, keras, *_ = io.tensorflow_components()
    report = json.loads((run / "training_report.json").read_text(encoding="utf-8"))
    config, positions = io.validate_config(run / "config_used.json")

    raw, targets = io.read_cases(CSV, require_targets=True)
    model = keras.models.load_model(str(run / "trained.keras"), compile=False)
    pred = io.predict_batches(model, raw, positions)

    test_idx = np.array(report["test_rows_zero_based"])
    tr_idx = np.array(report["train_rows_zero_based"])
    metrics = io.error_metrics(pred[test_idx], targets[test_idx])

    # ---------------- 误差归因：按工况分档
    df = pd.DataFrame({
        "ws": raw[:, 0],
        "wd_met": (270.0 - np.rad2deg(raw[:, 1])) % 360.0,
        "ti": raw[:, 2],
        "yaw1": np.rad2deg(raw[:, 3]),
        "pitch1": np.rad2deg(raw[:, 4]),
    })
    tsr = raw[:, 5] * R / np.maximum(targets[:, 3], 1e-6)
    df["tsr"] = np.round(tsr, 1)          # 反演值有浮点噪声，取整到 0.1 才能分组
    for i, name in enumerate(OUTPUT_NAMES):
        df[f"err_{name}"] = pred[:, i] - targets[:, i]
        df[f"tgt_{name}"] = targets[:, i]
    df["is_test"] = False
    df.loc[test_idx, "is_test"] = True
    test = df[df.is_test].copy()

    # 相对误差用"该机在该行的功率/风速"做分母，避免把大功率机组主导总体指标
    for i in range(3):
        test[f"rel_P{i+1}"] = np.abs(test[f"err_P{i+1}"]) / np.maximum(test[f"tgt_P{i+1}"], 1e3)
        test[f"rel_U{i+1}"] = np.abs(test[f"err_Ueff{i+1}"]) / np.maximum(test[f"tgt_Ueff{i+1}"], 0.1)

    def breakdown(col, bins=None, labels=None, frame=None):
        frame = test if frame is None else frame
        rows = []
        s = pd.cut(frame[col], bins=bins, labels=labels) if bins is not None else frame[col]
        for key, g in frame.groupby(s, observed=True):
            rows.append({
                col: str(key), "n": len(g),
                "P_MAE_kW": float(np.mean([np.abs(g[f"err_P{i+1}"]).mean() for i in range(3)]) / 1e3),
                "P_MAPE_%": float(100 * np.mean([g[f"rel_P{i+1}"].mean() for i in range(3)])),
                "Ueff_MAE": float(np.mean([np.abs(g[f"err_Ueff{i+1}"]).mean() for i in range(3)])),
            })
        return pd.DataFrame(rows)

    by_ws = breakdown("ws", bins=[4.75, 6, 7.5, 9, 10.5, 12.25],
                      labels=["5-6", "6-7.5", "7.5-9", "9-10.5", "10.5-12"])
    by_alignment = test.assign(
        align=np.where(np.abs(test.wd_met - 270) < 1e-6, "正对来流 270°",
                       np.where(np.abs(test.wd_met - 90) < 1e-6, "正对来流 90°", "其它风向")))
    by_align = breakdown("align", frame=by_alignment)
    by_yaw = breakdown("yaw1")
    by_tsr = breakdown("tsr")

    # ---------------- 出图
    FIG.mkdir(parents=True, exist_ok=True)
    hist = report["history"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(hist["loss"], label="训练损失")
    ax.plot(hist["val_loss"], label="验证损失")
    ax.set_yscale("log")
    ax.set_xlabel("轮次")
    ax.set_ylabel("归一化 MSE（对数）")
    ax.set_title(f"训练曲线：{report['epochs_completed']} 轮，27,106 个可训练参数")
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "fig10_training_curve.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    for k, ax in enumerate(axes.ravel()):
        name = OUTPUT_NAMES[k]
        y, p = targets[test_idx, k], pred[test_idx, k]
        unit = "MW" if k < 3 else "m/s"
        scale = 1e6 if k < 3 else 1.0
        ax.scatter(y / scale, p / scale, s=4, alpha=0.25)
        lo, hi = 0, max(y.max(), p.max()) / scale * 1.03
        ax.plot([lo, hi], [lo, hi], "r--", lw=1)
        mae = np.mean(np.abs(p - y)) / (1e3 if k < 3 else 1)
        label = f"{mae:.1f} kW" if k < 3 else f"{mae:.4f} m/s"
        ax.set_title(f"{name}  MAE={label}")
        ax.set_xlabel(f"真值 ({unit})")
        ax.set_ylabel(f"预测 ({unit})")
        ax.grid(alpha=0.3)
    fig.suptitle("留出工况上的预测-真值对比（红线为理想对角线）")
    fig.tight_layout()
    fig.savefig(FIG / "fig11_parity.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for ax, table, key, title in [
        (axes[0, 0], by_ws, "ws", "按入口风速分档"),
        (axes[0, 1], by_align, "align", "按是否正对来流"),
        (axes[1, 0], by_yaw, "yaw1", "按偏航指令"),
        (axes[1, 1], by_tsr, "tsr", "按叶尖速比"),
    ]:
        labels = []
        for v in table[key]:
            if key == "yaw1":
                labels.append(f"{float(v):+.0f}°")
            elif key == "tsr":
                labels.append(f"λ={float(v):.1f}")
            else:
                labels.append(str(v))
        ax.bar(labels, table["P_MAPE_%"])
        for i, v in enumerate(table["P_MAPE_%"]):
            ax.text(i, v, f"{v:.1f}%", ha="center", va="bottom", fontsize=8)
        ax.set_title(title)
        ax.set_ylabel("功率平均相对误差 (%)")
        ax.grid(alpha=0.3, axis="y")
    fig.suptitle("误差归因：哪一类工况学得差")
    fig.tight_layout()
    fig.savefig(FIG / "fig12_error_breakdown.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.scatter(test["wd_met"], test["rel_P1"] * 100, s=4, alpha=0.2, label="T1")
    ax.scatter(test["wd_met"], test["rel_P3"] * 100, s=4, alpha=0.2, label="T3（下游）")
    ax.set_xlabel("气象来向 (°)")
    ax.set_ylabel("功率相对误差 (%)")
    ax.set_title("误差 vs 风向：下游机在深尾流下更难学")
    ax.set_xticks(np.arange(0, 361, 45))
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "fig13_error_vs_direction.png", dpi=150)
    plt.close(fig)

    # ---------------- 报告
    n_test = len(test_idx)
    p_mean = float(targets[test_idx][:, :3].mean())
    summary = {
        "run": run.name,
        "epochs": report["epochs_completed"],
        "test_rows": int(n_test),
        "test_metrics": metrics,
        "P_MAE_kW_avg": float(np.mean([metrics[f"P{i}"]["MAE"] for i in (1, 2, 3)]) / 1e3),
        "P_MAPE_%_avg": float(100 * np.mean([test[f"rel_P{i}"].mean() for i in (1, 2, 3)])),
        # MAPE 在跨三个数量级的功率分布上会被近停机工况主导，这组归一化更可比
        "P_MAE_pct_of_rated": float(100 * np.mean([metrics[f"P{i}"]["MAE"] for i in (1, 2, 3)]) / 5e6),
        "P_MAE_pct_of_mean": float(100 * np.mean([metrics[f"P{i}"]["MAE"] for i in (1, 2, 3)]) / p_mean),
        "mean_power_test_W": p_mean,
        "Ueff_MAE_avg": float(np.mean([metrics[f"Ueff{i}"]["MAE"] for i in (1, 2, 3)])),
        "negative_outputs": int(report["negative_test_output_count"]),
        "constant_inputs_in_training": report["constant_inputs_in_training"],
        "original_parameters_unchanged": report["original_parameters_unchanged"],
    }
    (OUT / "training_analysis.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    L = ["# 训练结果分析", ""]
    L.append(f"- 训练目录：`{run.name}`")
    L.append(f"- 轮次：{report['epochs_completed']}；可训练参数 {report['trainable_parameters']}；原权重未变：{report['original_parameters_unchanged']}")
    L.append(f"- 留出集：{n_test} 行；恒定输入：{report['constant_inputs_in_training'] or '无'}")
    L.append(f"- 负输出个数：{report['negative_test_output_count']}（线性读出层无物理约束，优化侧必须先做非负钳制）")
    L.append("")
    L.append("## 一、留出集误差")
    L.append("")
    L.append("| 输出 | MAE | RMSE | 单位 |")
    L.append("| --- | --- | --- | --- |")
    for name in OUTPUT_NAMES:
        m = metrics[name]
        # 功率是 kW 量级、Ueff 是 0.0x 量级，用同一套小数位会把 Ueff 显示成 0
        if m["unit"] == "W":
            L.append(f"| {name} | {m['MAE']/1e3:.1f} kW | {m['RMSE']/1e3:.1f} kW | {m['unit']} |")
        else:
            L.append(f"| {name} | {m['MAE']:.4f} | {m['RMSE']:.4f} | {m['unit']} |")
    L.append("")
    L.append(f"平均功率误差 **{summary['P_MAE_kW_avg']:.1f} kW**"
             f"（相对 **{summary['P_MAPE_%_avg']:.2f}%**，"
             f"= 额定功率的 **{summary['P_MAE_pct_of_rated']:.2f}%**、"
             f"测试集平均功率的 **{summary['P_MAE_pct_of_mean']:.1f}%**），"
             f"空调速误差 **{summary['Ueff_MAE_avg']:.3f} m/s**。")
    L.append("")
    L.append("> MAPE 在跨三个数量级的功率分布（9 kW ~ 4.76 MW）上会被近停机工况主导，"
             "所以另给两个归一化口径：相对额定功率、相对测试集平均功率。")
    L.append("")
    for title, table in [("按风速分档", by_ws), ("按是否正对来流", by_align),
                         ("按偏航指令", by_yaw), ("按叶尖速比", by_tsr)]:
        L.append(f"### {title}")
        L.append("")
        L.append(table.to_markdown(index=False, floatfmt=".2f"))
        L.append("")
    L.append("## 二、图件")
    L.append("")
    for p, cap in [("fig10_training_curve.png", "训练曲线"),
                   ("fig11_parity.png", "预测-真值对比"),
                   ("fig12_error_breakdown.png", "误差归因"),
                   ("fig13_error_vs_direction.png", "误差随风向")]:
        L.append(f"![{cap}](figures/{p})")
        L.append("")
    L.append("## 三、结论与边界")
    L.append("")
    L.append("1. 随机留出误差不等于外推到全新风况的误差；风向覆盖 345°、风速 5–12 m/s，"
             "超出该范围不做任何保证。")
    L.append("2. 标签源是 FLORIS 解析模型 + demo Cp/Ct 曲面，本模型学到的是它的代理，"
             "不是真实流场。独立校验仍需 Fluent 锚点或实测数据。")
    L.append("3. 负输出必须由下游优化程序钳制，或改为输出侧加非负变换。")
    L.append("")
    (OUT / "training_analysis.md").write_text("\n".join(L), encoding="utf-8")

    print(f"[OK] 平均功率 MAE {summary['P_MAE_kW_avg']:.1f} kW ({summary['P_MAPE_%_avg']:.2f}%)")
    print(f"[OK] 空调速 MAE {summary['Ueff_MAE_avg']:.3f} m/s；负输出 {summary['negative_outputs']} 个")
    print(f"[OK] 报告 -> {OUT / 'training_analysis.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
