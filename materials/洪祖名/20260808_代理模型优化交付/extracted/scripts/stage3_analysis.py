"""阶段3+4：最终 XGB 模型的残差分析、物理一致性检查与导出"""

import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"))

from data_loader import clean_data, load_raw, make_features
from models.xgb_model import XGBSurrogate


DATA_DIR = r"D:\VSCODE\大创项目风电\data\teammates\yuan_fuda_floris\raw"
EXP_DIR = r"D:\VSCODE\大创项目风电\optimization_control\experiments\20260807_surrogate_baseline"
MODEL_DIR = r"D:\VSCODE\大创项目风电\optimization_control\surrogate\models\final"
SEED = 42
BEST_PARAMS = dict(
    n_estimators=529, max_depth=5, learning_rate=0.19716139842591673,
    subsample=0.7382962469610985, reg_lambda=5.239619507609589,
)
TARGETS = ["turbine_1_power", "turbine_2_power", "turbine_3_power", "farm_power"]


def run_cv(model_key):
    """分层 5-fold CV，返回 out-of-fold 预测"""
    raw = load_raw(os.path.join(DATA_DIR, model_key, f"training_data_{model_key}.csv"))
    clean = clean_data(raw)
    X = make_features(clean)
    y = clean[TARGETS].to_numpy(float)
    labels = (X[:, 0] * 2).astype(int)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    pred = np.zeros_like(y)
    for tr, te in skf.split(X, labels):
        m = XGBSurrogate(seed=SEED, params=BEST_PARAMS).fit(X[tr], y[tr])
        pred[te] = m.predict(X[te])
    return clean, X, y, pred


def plot_residuals(clean, X, y, pred, model_key, tag):
    """残差 vs 风速/风向/真实功率，三张图合成一张"""
    ws = X[:, 0]
    wd = np.degrees(np.arctan2(X[:, 3], X[:, 2])) % 360  # 由 sin/cos 反推风向
    farm_err = (y[:, 3] - pred[:, 3]) / 1e3  # kW
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    axes[0].scatter(ws, farm_err, s=6, alpha=0.4)
    axes[0].set_xlabel("wind speed (m/s)")
    axes[0].set_ylabel("farm error (kW)")
    axes[0].set_title("error vs wind speed")
    axes[1].scatter(wd, farm_err, s=6, alpha=0.4)
    axes[1].set_xlabel("wind direction (deg)")
    axes[1].set_ylabel("farm error (kW)")
    axes[1].set_title("error vs wind direction")
    axes[2].scatter(y[:, 3] / 1e6, farm_err, s=6, alpha=0.4)
    axes[2].set_xlabel("true farm power (MW)")
    axes[2].set_ylabel("farm error (kW)")
    axes[2].set_title("error vs true power")
    fig.suptitle(f"XGB residual analysis - {model_key} ({tag})")
    fig.tight_layout()
    out = os.path.join(EXP_DIR, f"residual_{model_key}_{tag}.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"残差图: {out}")
    # 分风速段误差
    segs = [(4, 6), (6, 9), (9, 12.1)]
    for lo, hi in segs:
        mask = (ws >= lo) & (ws < hi)
        if mask.sum():
            print(f"  风速 {lo}-{hi} m/s: n={mask.sum()}, farm MAE={np.abs(farm_err[mask]).mean():.2f} kW")


def export_final(model_key):
    """全量清洗数据训练最终模型，导出 xgboost 原生 json + 元数据"""
    raw = load_raw(os.path.join(DATA_DIR, model_key, f"training_data_{model_key}.csv"))
    clean = clean_data(raw)
    X = make_features(clean)
    y = clean[TARGETS].to_numpy(float)
    model = XGBSurrogate(seed=SEED, params=BEST_PARAMS).fit(X, y)
    os.makedirs(MODEL_DIR, exist_ok=True)
    # xgboost 原生格式（替代 ONNX：零额外依赖、无损、RL 环境加载快）
    for i, name in enumerate(["turbine_1", "turbine_2", "turbine_3"]):
        model.models[i].save_model(os.path.join(MODEL_DIR, f"{model_key}_{name}.json"))
    meta = {
        "model": "xgboost",
        "params": BEST_PARAMS,
        "features": ["wind_speed", "turbulence_intensity", "sin(dir)", "cos(dir)", "sin(2dir)", "cos(2dir)"],
        "targets": TARGETS,
        "farm": "sum of turbine powers (conservation)",
        "trained_samples": len(clean),
        "data_source": f"floris_{model_key}",
        "seed": SEED,
        "export_format": "xgboost native json (per turbine)",
    }
    with open(os.path.join(MODEL_DIR, f"{model_key}_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    # 验证：加载后与训练时预测一致
    from xgboost import XGBRegressor
    loaded = [XGBRegressor() for _ in range(3)]
    for i, name in enumerate(["turbine_1", "turbine_2", "turbine_3"]):
        loaded[i].load_model(os.path.join(MODEL_DIR, f"{model_key}_{name}.json"))
    pred_orig = model.predict(X)
    pred_load = np.column_stack([m.predict(X) for m in loaded])
    pred_load = np.concatenate([pred_load, pred_load.sum(axis=1, keepdims=True)], axis=1)
    print(f"  导出验证: 加载前后最大差 = {np.abs(pred_orig - pred_load).max():.6g} W")
    return model


def main():
    for key in ["gch", "cc"]:
        print("=" * 60)
        print(f"{key}:")
        clean, X, y, pred = run_cv(key)
        print("CV 指标:")
        for i, name in enumerate(TARGETS):
            err = y[:, i] - pred[:, i]
            r2 = 1 - (err**2).sum() / ((y[:, i] - y[:, i].mean()) ** 2).sum()
            print(f"  {name}: R2={r2:.6f} MAE={np.abs(err).mean()/1e3:.2f} kW RMSE={np.sqrt((err**2).mean())/1e3:.2f} kW")
        plot_residuals(clean, X, y, pred, key, "xgb_tuned")
        # 物理一致性
        t = pred[:, :3]
        print(f"  单机功率边界: [{t.min():.1f}, {t.max():.1f}] W")
        print(f"  守恒误差 max|farm-sum| = {np.abs(pred[:,3]-t.sum(axis=1)).max():.6g} W")
        # 单调性抽查（重新训练一次用于序列预测）
        wd, ti = 180.0, 0.08
        ws_seq = np.arange(4.0, 12.1, 0.5)
        d = pd.DataFrame({"wind_speed": ws_seq, "wind_direction": wd, "turbulence_intensity": ti})
        m = XGBSurrogate(seed=SEED, params=BEST_PARAMS).fit(X, y)
        farm_seq = m.predict(make_features(d))[:, 3]
        mono = np.all(np.diff(farm_seq) >= -1e-3)
        print(f"  单调性(风向180°, TI=0.08, 风速4->12): {'OK' if mono else 'FAIL'}")
        print(f"    序列: {['%.1f' % (v/1e6) for v in farm_seq]}")
        print("导出最终模型:")
        export_final(key)
    # 汇总最终指标表
    print("\n完成。最终模型目录:", MODEL_DIR)


if __name__ == "__main__":
    main()
