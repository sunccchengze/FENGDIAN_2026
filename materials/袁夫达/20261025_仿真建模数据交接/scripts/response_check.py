# -*- coding: utf-8 -*-
"""响应校验：扫单变量，看 PINN 是否复现 FLORIS 的物理响应方向与幅度。

这是「训练是否有效果」最直接的证据——留出集误差只说明它拟合得好，
响应曲线才说明它学到的是物理规律而不是插值。

两种模式（因为两个虚拟环境各有依赖）：
  truth   用 .venv（装了 floris）算真值
  predict 用 .venv-tf（装了 TF）加载模型预测并出图

    .\\.venv\\Scripts\\python.exe           pinn_wind_data\\response_check.py truth
    pinn_wind_data\\.venv-tf\\Scripts\\python.exe pinn_wind_data\\response_check.py predict
"""
from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
OUT = HERE / "out"
FIG = OUT / "figures"
TRUTH = OUT / "sweep_truth.json"

R = 125.88 / 2
ETA = 0.944
RHO = 1.225
COS_EXP = 1.88


# ---------------------------------------------------------------- 扫描设计
def sweeps() -> dict[str, list[dict]]:
    """四组单变量扫描；除被扫的量外，其余条件固定。"""
    base = {"ws": 8.0, "wd": 270.0, "ti": 0.06,
            "yaws": (0.0, 0.0, 0.0), "block": (0.0, 8.0)}   # (桨距°, 速率)

    def case(**kw):
        c = dict(base)
        c.update(kw)
        return c

    out = {}
    # 偏航只扫到 ±20°：这是本轮数据的采样包络，超出即外推，不作保证
    out["偏航角 γ1 (T1 单独偏航)"] = [
        case(yaws=(float(y), 0.0, 0.0)) for y in np.arange(-20, 20.1, 5.0)]
    # 桨距 0~10°：v3 在每个风速都采了 0/4/10，这里检验它能否插值出 2/6/8
    out["集体桨距 β (三机同桨距)"] = [
        case(block=(float(b), 8.0)) for b in (0, 2, 4, 6, 8, 10)]
    out["入口风速 U∞"] = [
        case(ws=float(u)) for u in np.arange(5, 12.01, 0.5)]
    out["风向 θ∞"] = [
        case(wd=float(d)) for d in list(np.arange(0, 360, 15.0)) + [85.0, 95.0, 265.0, 275.0]]
    return out


# ---------------------------------------------------------------- truth 模式
def run_truth() -> int:
    import generate_cases as gc
    from floris import FlorisModel

    blocks = {(round(b["tsr"], 3), round(float(b["pitch"]), 1)): b
              for b in json.loads((OUT / "table_manifest.json").read_text(encoding="utf-8"))["blocks"]}
    offsets = gc.disk_offsets()
    payload = {}

    for name, cases in sweeps().items():
        rows = []
        for c in cases:
            b = blocks[(round(c["block"][1], 3), round(float(c["block"][0]), 1))]
            turbs = [gc.turbine_dict(c["block"][0], c["block"][1], b["cp"], b["ct"], slot=i)
                     for i in range(3)]
            cfg = gc.build_farm_config([c["block"][1]] * 3)
            cfg["farm"]["turbine_type"] = turbs
            f = FlorisModel(cfg)
            f.set(wind_speeds=[c["ws"]], wind_directions=[c["wd"]],
                  turbulence_intensities=[c["ti"]], yaw_angles=np.array([c["yaws"]]))
            f.run()
            pts = gc.disk_points_global(c["wd"], offsets)
            u = f.sample_flow_at_points(np.concatenate([p[0] for p in pts]),
                                        np.concatenate([p[1] for p in pts]),
                                        np.concatenate([p[2] for p in pts]))[0]
            per = offsets.shape[0]
            ueff = np.array([np.cbrt(np.mean(u[i * per:(i + 1) * per] ** 3)) for i in range(3)])
            area = math.pi * R**2
            yaw = np.deg2rad(c["yaws"])
            p = 0.5 * RHO * area * ueff**3 * b["cp"] * ETA * np.cos(yaw) ** COS_EXP
            omega = c["block"][1] * ueff / R
            rows.append({"case": c, "ueff": ueff.tolist(), "omega": omega.tolist(),
                         "P": p.tolist()})
        payload[name] = rows
        print(f"  {name}: {len(rows)} 点", flush=True)

    TRUTH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] 真值写入 {TRUTH}")
    return 0


# ---------------------------------------------------------------- predict 模式
def run_predict() -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    PINN = PROJECT / "PINNs_multi_turbine_wake_simulation-outputchange"
    sys.path.insert(0, str(PINN))
    import modify_pinn_wind_io as io

    # 自动选最新一次完成的训练
    runs = [p for p in (PINN / "OutputChange" / "wind_iochanged_9ms").glob("training_*")
            if p.is_dir() and (p / "trained.keras").is_file()
            and (p / "training_report.json").is_file()]
    if not runs:
        raise SystemExit("找不到已完成的训练目录")
    runs.sort(key=lambda p: (p / "training_report.json").stat().st_mtime)
    run_path = runs[-1]
    print(f"  使用训练目录: {run_path.name}")
    tf, keras, *_ = io.tensorflow_components()
    cfg, pos = io.validate_config(run_path / "config_used.json")
    model = keras.models.load_model(str(run_path / "trained.keras"), compile=False)

    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    summary = {}

    for ax, (name, rows) in zip(axes.ravel(), truth.items()):
        raw, p_true = [], []
        for r in rows:
            c = r["case"]
            th_flow = math.radians((270.0 - c["wd"]) % 360.0)
            yaw = np.deg2rad(c["yaws"])
            pit = np.deg2rad(c["block"][0])
            raw.append([c["ws"], th_flow, c["ti"],
                        yaw[0], pit, r["omega"][0],
                        yaw[1], pit, r["omega"][1],
                        yaw[2], pit, r["omega"][2]])
            p_true.append(r["P"])
        raw = np.array(raw)
        pred = io.predict_batches(model, raw, pos)
        p_true = np.array(p_true)

        x = np.arange(len(rows))
        labels = {"偏航角 γ1 (T1 单独偏航)": [f"{c['case']['yaws'][0]:.0f}" for c in rows],
                  "集体桨距 β (三机同桨距)": [f"{c['case']['block'][0]:.0f}" for c in rows],
                  "入口风速 U∞": [f"{c['case']['ws']:.1f}" for c in rows],
                  "风向 θ∞": [f"{c['case']['wd']:.0f}" for c in rows]}[name]
        step = max(1, len(x) // 12)
        ax.plot(x, p_true.sum(axis=1) / 1e6, "k-o", ms=3, lw=1.2, label="FLORIS 真值")
        ax.plot(x, pred[:, :3].sum(axis=1) / 1e6, "r--s", ms=3, lw=1.2, label="PINN 预测")
        ax.set_xticks(x[::step])
        ax.set_xticklabels(labels[::step], fontsize=8)
        ax.set_ylabel("全场功率 (MW)")
        ax.set_title(name)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        rel = np.abs(pred[:, :3].sum(axis=1) - p_true.sum(axis=1)) / np.maximum(p_true.sum(axis=1), 1.0)
        summary[name] = {"max_rel_pct": float(rel.max() * 100),
                         "mean_rel_pct": float(rel.mean() * 100),
                         "trend_true": [float(v) for v in p_true.sum(axis=1) / 1e6],
                         "trend_pred": [float(v) for v in pred[:, :3].sum(axis=1) / 1e6]}

    fig.suptitle("响应校验：单变量扫描下 PINN 与 FLORIS 的全场功率响应")
    fig.tight_layout()
    fig.savefig(FIG / "fig14_response_check.png", dpi=150)
    plt.close(fig)

    (OUT / "response_check.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, v in summary.items():
        print(f"  {name:26s} 平均偏差 {v['mean_rel_pct']:5.2f}%  最大 {v['max_rel_pct']:5.2f}%")
    print(f"[OK] 图 -> {FIG / 'fig14_response_check.png'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("truth", "predict"))
    args = ap.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)
    return run_truth() if args.mode == "truth" else run_predict()


if __name__ == "__main__":
    raise SystemExit(main())
