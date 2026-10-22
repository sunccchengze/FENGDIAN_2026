"""阶段1：候选模型 5-fold 交叉验证对比（GCH/CC 各一套）"""

import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"))

from data_loader import clean_data, load_raw, make_features
from models.xgb_model import XGBSurrogate
from models.gpr_model import GPRSurrogate
from models.mlp_v2 import MLPv2Surrogate
from models.two_stage import TwoStageSurrogate


DATA_DIR = r"D:\VSCODE\大创项目风电\data\teammates\yuan_fuda_floris\raw"
EXP_DIR = r"D:\VSCODE\大创项目风电\optimization_control\experiments\20260807_surrogate_baseline"
TARGETS = ["turbine_1_power", "turbine_2_power", "turbine_3_power", "farm_power"]
SEED = 42


def metrics(true: np.ndarray, pred: np.ndarray) -> dict:
    """逐目标指标: R2/MAE_kW/RMSE_kW"""
    out = {}
    for i, name in enumerate(TARGETS):
        err = true[:, i] - pred[:, i]
        r2 = 1 - (err**2).sum() / ((true[:, i] - true[:, i].mean()) ** 2).sum()
        out[f"{name}_R2"] = r2
        out[f"{name}_MAE_kW"] = np.abs(err).mean() / 1e3
        out[f"{name}_RMSE_kW"] = np.sqrt((err**2).mean()) / 1e3
    return out


def run_cv_clean(model_factory, X, y, n_splits=5):
    """清洗后数据上的分层 5-fold CV（按风速分层），返回 out-of-fold 拼接指标"""
    wind_labels = (X[:, 0] * 2).astype(int)  # 风速档位整数标签（4.0->8, 12.0->24）
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=SEED)
    pred_all = np.zeros_like(y)
    t0 = time.time()
    for tr_idx, te_idx in skf.split(X, wind_labels):
        model = model_factory()
        model.fit(X[tr_idx], y[tr_idx])
        pred_all[te_idx] = model.predict(X[te_idx])
    dt = time.time() - t0
    return metrics(y, pred_all), dt


def run_cv_full_two_stage(model_factory, X_full, y_full, X_clean, y_clean):
    """two_stage 在全量数据（含零功率行）上的 5-fold CV"""
    wind_labels = (X_full[:, 0] * 2).astype(int)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    pred_full = np.zeros_like(y_full)
    t0 = time.time()
    for tr_idx, te_idx in skf.split(X_full, wind_labels):
        model = model_factory()
        model.fit(X_full[tr_idx], y_full[tr_idx])
        pred_full[te_idx] = model.predict(X_full[te_idx])
    dt = time.time() - t0
    m = metrics(y_full, pred_full)
    # 零功率分类准确率（3 台机）
    cls_acc = []
    for i in range(3):
        cls_acc.append(float(((pred_full[:, i] > 0) == (y_full[:, i] > 0)).mean()))
    m["zero_class_acc_mean"] = float(np.mean(cls_acc))
    return m, dt


def main():
    os.makedirs(EXP_DIR, exist_ok=True)
    all_rows = []
    for model_key in ["gch", "cc"]:
        csv_path = os.path.join(DATA_DIR, model_key, f"training_data_{model_key}.csv")
        raw = load_raw(csv_path)
        clean = clean_data(raw)
        X = make_features(clean)
        y = clean[["turbine_1_power", "turbine_2_power", "turbine_3_power", "farm_power"]].to_numpy(float)
        X_full = make_features(raw)
        y_full = raw[["turbine_1_power", "turbine_2_power", "turbine_3_power", "farm_power"]].to_numpy(float)

        factories = {
            "xgb": lambda: XGBSurrogate(seed=SEED),
            "gpr": lambda: GPRSurrogate(seed=SEED, length_scale=1.0),
            "mlp_v2": lambda: MLPv2Surrogate(seed=SEED),
            "two_stage": lambda: TwoStageSurrogate(seed=SEED),
        }
        for name, factory in factories.items():
            if name == "two_stage":
                m, dt = run_cv_full_two_stage(factory, X_full, y_full, X, y)
                row = {"data": model_key, "model": name, "subset": "full_with_zeros", "time_s": round(dt, 1), **m}
            else:
                m, dt = run_cv_clean(factory, X, y)
                row = {"data": model_key, "model": name, "subset": "clean", "time_s": round(dt, 1), **m}
            all_rows.append(row)
            print(f"{model_key} / {name}: 完成 ({dt:.1f}s) farm_R2={m.get('farm_power_R2', float('nan')):.5f}")

    df = pd.DataFrame(all_rows)
    out_csv = os.path.join(EXP_DIR, "model_comparison_cv.csv")
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\n已保存: {out_csv}")
    print(df[["data", "model", "subset", "turbine_1_power_MAE_kW", "farm_power_MAE_kW", "farm_power_R2", "time_s"]].to_string(index=False))


if __name__ == "__main__":
    main()
