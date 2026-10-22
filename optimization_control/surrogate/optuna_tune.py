"""阶段2：Optuna 贝叶斯超参搜索（单分层 split 评估，目标 farm RMSE）"""

import os
import sys

import numpy as np
import optuna
import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"))

from data_loader import clean_data, load_raw, make_features
from models.xgb_model import XGBSurrogate
from models.gpr_model import GPRSurrogate
from models.mlp_v2 import MLPv2Surrogate


from _paths import repo_path, yuan_training_csv

DATA_CSV = yuan_training_csv("gch")
EXP_DIR = repo_path("optimization_control", "experiments", "20260807_surrogate_baseline")
SEED = 42


def load_data():
    raw = load_raw(DATA_CSV)
    clean = clean_data(raw)
    X = make_features(clean)
    y = clean[["turbine_1_power", "turbine_2_power", "turbine_3_power", "farm_power"]].to_numpy(float)
    labels = (X[:, 0] * 2).astype(int)
    return train_test_split(X, y, test_size=0.2, random_state=SEED, stratify=labels)


def farm_rmse_kw(model, X_val, y_val):
    pred = model.predict(X_val)
    err = y_val[:, 3] - pred[:, 3]
    return float(np.sqrt((err**2).mean()) / 1e3)


def main():
    X_tr, X_va, y_tr, y_va = load_data()

    def obj_xgb(trial):
        params = dict(
            n_estimators=trial.suggest_int("n_estimators", 200, 800),
            max_depth=trial.suggest_int("max_depth", 3, 8),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            subsample=trial.suggest_float("subsample", 0.7, 1.0),
            reg_lambda=trial.suggest_float("reg_lambda", 0.1, 10.0, log=True),
        )
        model = XGBSurrogate(seed=SEED, params=params).fit(X_tr, y_tr)
        return farm_rmse_kw(model, X_va, y_va)

    def obj_gpr(trial):
        length_scale = trial.suggest_float("length_scale", 0.3, 10.0, log=True)
        noise = trial.suggest_float("noise_level", 1e-8, 1e-4, log=True)
        model = GPRSurrogate(seed=SEED, length_scale=length_scale, alpha=noise).fit(X_tr, y_tr)
        return farm_rmse_kw(model, X_va, y_va)

    def obj_mlp(trial):
        lr = trial.suggest_float("lr", 1e-4, 3e-3, log=True)
        l2 = trial.suggest_float("l2", 1e-6, 1e-2, log=True)
        hidden = trial.suggest_categorical("hidden", [(64, 128, 64), (128, 128), (128, 256, 128), (64, 64, 64)])
        model = MLPv2Surrogate(seed=SEED, epochs=150, lr=lr, l2=l2, hidden=hidden).fit(X_tr, y_tr)
        return farm_rmse_kw(model, X_va, y_va)

    results = {}
    for name, obj, n_trials in [("xgb", obj_xgb, 30), ("gpr", obj_gpr, 20), ("mlp_v2", obj_mlp, 25)]:
        study = optuna.create_study(direction="minimize", study_name=name, sampler=optuna.samplers.TPESampler(seed=SEED))
        study.optimize(obj, n_trials=n_trials, show_progress_bar=False)
        results[name] = {"best_value": study.best_value, "best_params": study.best_params}
        print(f"{name}: 最优 farm RMSE = {study.best_value:.2f} kW")
        print(f"  参数: {study.best_params}")

    with open(os.path.join(EXP_DIR, "optuna_results.txt"), "w", encoding="utf-8") as f:
        for name, r in results.items():
            f.write(f"{name}: best_farm_RMSE_kW={r['best_value']:.4f} params={r['best_params']}\n")
    print(f"\n已保存: {os.path.join(EXP_DIR, 'optuna_results.txt')}")


if __name__ == "__main__":
    main()
