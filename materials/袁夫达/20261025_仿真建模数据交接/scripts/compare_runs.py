# -*- coding: utf-8 -*-
"""横向比较同一份数据在不同坐标口径下的训练结果。

三次训练用的是同一份 cases_wind.csv、同一个 seed，
而 split_groups 只按 12 维输入分组、与坐标无关，
因此三组的训练/验证/测试行完全相同，可以直接横比。

不需要 TF，只读 training_report.json：

    .\\.venv\\Scripts\\python.exe pinn_wind_data\\compare_runs.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = (HERE.parent / "PINNs_multi_turbine_wake_simulation-outputchange"
          / "OutputChange" / "wind_iochanged_9ms")
OUT = HERE / "out"

LABEL = {
    "scaled": "D 无量纲化 (s=0.239)",
    "spacing7D": "7D 间距匹配 (s=0.558)",
    "physical": "真实米制 (s=1.0)",
}


def collect(min_epochs: int = 50) -> list[dict]:
    rows = []
    for run in sorted(p for p in BUNDLE.glob("training_*") if p.is_dir()):
        rep_f, cfg_f = run / "training_report.json", run / "config_used.json"
        if not (rep_f.is_file() and cfg_f.is_file()):
            continue
        rep = json.loads(rep_f.read_text(encoding="utf-8"))
        cfg = json.loads(cfg_f.read_text(encoding="utf-8"))
        if rep.get("epochs_completed", 0) < min_epochs:
            continue            # 跳过冒烟训练
        m = rep["test_metrics"]
        n_rows = sum(len(rep.get(k, [])) for k in
                     ("train_rows_zero_based", "validation_rows_zero_based", "test_rows_zero_based"))
        rows.append({
            "run": run.name,
            "mode": cfg.get("coordinate_mode", "?"),
            "scale": cfg.get("coordinate_scale", 1.0),
            "positions": cfg["turbine_positions_m"],
            "epochs": rep["epochs_completed"],
            "n_rows": n_rows,
            "P_MAE_kW": sum(m[f"P{i}"]["MAE"] for i in (1, 2, 3)) / 3 / 1e3,
            "P_RMSE_kW": sum(m[f"P{i}"]["RMSE"] for i in (1, 2, 3)) / 3 / 1e3,
            "Ueff_MAE": sum(m[f"Ueff{i}"]["MAE"] for i in (1, 2, 3)) / 3,
            "neg": rep.get("negative_test_output_count", -1),
            "csv_sha": rep.get("csv_sha256", "")[:12],
        })
    return rows


def main() -> int:
    rows = collect()
    if not rows:
        print("还没有完成的训练（>=50 轮）")
        return 1

    print(f"{'口径':22s} {'样本':>6s} {'轮次':>5s} {'P_MAE(kW)':>10s} "
          f"{'P_RMSE(kW)':>11s} {'Ueff_MAE':>9s} {'负输出':>6s}  训练目录")
    print("-" * 110)
    for r in sorted(rows, key=lambda r: r["P_MAE_kW"]):
        print(f"{LABEL.get(r['mode'], r['mode']):22s} {r['n_rows']:6d} {r['epochs']:5d} "
              f"{r['P_MAE_kW']:10.2f} {r['P_RMSE_kW']:11.2f} {r['Ueff_MAE']:9.4f} "
              f"{r['neg']:6d}  {r['run']}")

    (OUT / "run_comparison.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] 写出 {OUT / 'run_comparison.json'}")
    print("提示：更细的分档误差用 analyze_training.py --run <训练目录>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
