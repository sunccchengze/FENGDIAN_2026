"""阶段0：复现厉今飞 MLP 基线指标（GCH/CC），与 test_metrics.csv 对比"""

import os

import numpy as np
import pandas as pd

from data_loader import make_features
from keras_model import KerasMLPForward


TEAMMATES = r"D:\VSCODE\大创项目风电\data\teammates\li_jinfei_nn"


def eval_one(model_key: str):
    """对单个模型（gch/cc）：用 test_predictions.csv 的输入行复现预测，输出指标对比"""
    print("=" * 60)
    print(f"模型: {model_key}")
    model_path = os.path.join(TEAMMATES, "models", model_key, "wind_farm_power_model.keras")
    pred_csv = os.path.join(TEAMMATES, "results", model_key, "test_predictions.csv")
    metrics_csv = os.path.join(TEAMMATES, "results", model_key, "test_metrics.csv")

    model = KerasMLPForward(model_path)
    test = pd.read_csv(pred_csv)
    x = make_features(test)
    pred_w = model.predict_w(x)  # (N,4)

    # 与 test_predictions.csv 中已存预测对比（确认前向复现正确）
    ref_pred = np.column_stack(
        [
            test["pred_turbine_1_power"],
            test["pred_turbine_2_power"],
            test["pred_turbine_3_power"],
            test["pred_farm_power"],
        ]
    ).astype(np.float64)
    max_diff = float(np.abs(pred_w - ref_pred).max())
    print(f"与 test_predictions.csv 预测最大绝对差: {max_diff:.6g} W")

    # 真实值
    true_w = np.column_stack(
        [test["turbine_1_power"], test["turbine_2_power"], test["turbine_3_power"], test["farm_power"]]
    ).astype(np.float64)
    names = ["turbine_1_power", "turbine_2_power", "turbine_3_power", "farm_power"]
    rows = []
    for i, name in enumerate(names):
        err = true_w[:, i] - pred_w[:, i]
        mae = np.abs(err).mean()
        rmse = np.sqrt((err**2).mean())
        r2 = 1 - (err**2).sum() / ((true_w[:, i] - true_w[:, i].mean()) ** 2).sum()
        rows.append({"target": name, "MAE_W": mae, "RMSE_W": rmse, "R2": r2})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    # 与厉今飞 test_metrics.csv 对比
    ref = pd.read_csv(metrics_csv)
    ref = ref[ref["target"].isin(names)][["target", "MAE_W", "RMSE_W", "R2"]].reset_index(drop=True)
    merged = df.merge(ref, on="target", suffixes=("_repro", "_ref"))
    mae_diff = float(np.abs(merged["MAE_W_repro"] - merged["MAE_W_ref"]).max())
    r2_diff = float(np.abs(merged["R2_repro"] - merged["R2_ref"]).max())
    print(f"与 test_metrics.csv 对比: MAE 最大差 {mae_diff:.6g} W, R2 最大差 {r2_diff:.6g}")
    return df


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    out = []
    for key in ["gch", "cc"]:
        out.append(eval_one(key))
    # 汇总表（供实验记录）
    summary = pd.concat(out, keys=["gch", "cc"], names=["model"])
    summary = summary.reset_index()
    exp_dir = r"D:\VSCODE\大创项目风电\optimization_control\experiments\20260807_surrogate_baseline"
    os.makedirs(exp_dir, exist_ok=True)
    summary.to_csv(os.path.join(exp_dir, "baseline_metrics.csv"), index=False)
    print(f"\n已保存: {exp_dir}\\baseline_metrics.csv")
