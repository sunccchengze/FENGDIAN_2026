# -*- coding: utf-8 -*-
"""
风电场多输出神经网络回归
原始输入:
    wind_speed, wind_direction, turbulence_intensity
模型输出:
    turbine_1_power, turbine_2_power, turbine_3_power, farm_power

设计要点:
1. 任意一个 y 标签等于 0 的样本都删除。
2. 风向是周期变量，用 sin/cos 及二阶谐波编码，避免 0° 与 360° 被视为相距很远。
3. 网络只自由预测三台风机的功率比例。
4. farm_power 由三台风机功率相加得到，强制满足物理一致性。
"""

import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")

from pathlib import Path
import json
import random

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from tensorflow import keras
from tensorflow.keras import layers, regularizers


# =========================
# 1. 参数设置
# =========================
SEED = 42
BATCH_SIZE = 32
MAX_EPOCHS = 1000

BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DATA_PATH = BASE_DIR / "training_data_gch.csv"
RESULT_DIR = BASE_DIR / "wind_farm_results"
MODEL_PATH = RESULT_DIR / "wind_farm_power_model.keras"

INPUT_COLS = [
    "wind_speed",
    "wind_direction",
    "turbulence_intensity",
]
TARGET_COLS = [
    "turbine_1_power",
    "turbine_2_power",
    "turbine_3_power",
    "farm_power",
]

# 数据显示三台风机额定功率均为 5 MW，风场总额定功率为 15 MW。
# 训练时把输出缩放到 0~1，训练更稳定。
OUTPUT_SCALES_W = np.array(
    [5_000_000.0, 5_000_000.0, 5_000_000.0, 15_000_000.0],
    dtype=np.float32,
)

RESULT_DIR.mkdir(parents=True, exist_ok=True)

random.seed(SEED)
np.random.seed(SEED)
tf.keras.utils.set_random_seed(SEED)
try:
    tf.config.experimental.enable_op_determinism()
except Exception:
    pass


# =========================
# 2. 读取与清洗数据
# =========================
def load_and_clean_data(csv_path: Path) -> pd.DataFrame:
    raw = pd.read_csv(csv_path)

    required_cols = INPUT_COLS + TARGET_COLS
    missing_cols = [col for col in required_cols if col not in raw.columns]
    if missing_cols:
        raise ValueError(f"CSV 缺少必要列: {missing_cols}")

    # 强制转为数值；无法转换、正负无穷都会作为无效数据删除。
    data = raw[required_cols].apply(pd.to_numeric, errors="coerce")
    non_finite_mask = ~np.isfinite(data.to_numpy()).all(axis=1)

    # 用户给定规则：任意一个 y 标签为 0，该行无效。
    zero_target_mask = (data[TARGET_COLS] == 0).any(axis=1)

    valid_mask = ~(non_finite_mask | zero_target_mask)
    clean = data.loc[valid_mask].copy()

    # 保留原 CSV 行号，方便回查。CSV 第一行为表头，因此数据行号从 2 开始。
    clean.insert(0, "source_csv_line", clean.index.to_numpy() + 2)
    clean.reset_index(drop=True, inplace=True)

    print("=" * 65)
    print("数据清洗结果")
    print(f"原始样本数:            {len(raw)}")
    print(f"非数值/缺失/无穷样本: {int(non_finite_mask.sum())}")
    print(f"任一 y 为 0 的样本:   {int(zero_target_mask.sum())}")
    print(f"最终有效样本数:        {len(clean)}")
    print("=" * 65)

    if len(clean) < 100:
        raise ValueError("有效样本过少，不建议继续训练神经网络。")

    # 检查 farm_power 是否等于三台风机功率之和。
    turbine_sum = clean[TARGET_COLS[:3]].sum(axis=1)
    consistency_error = np.abs(clean["farm_power"] - turbine_sum)
    max_error = float(consistency_error.max())
    print(f"farm_power 与三台风机功率和的最大误差: {max_error:.6g} W")

    # 这个模型强制总功率等于三台风机功率和，因此数据必须满足该关系。
    if max_error > 1.0:
        raise ValueError(
            "数据中的 farm_power 与三台风机功率和不一致，"
            "不适合直接使用当前的物理约束输出层。"
        )

    return clean


# =========================
# 3. 特征工程
# =========================
def make_features(frame: pd.DataFrame) -> np.ndarray:
    """
    将 3 个原始输入转换成 6 个网络特征:
    wind_speed
    turbulence_intensity
    sin(theta), cos(theta)
    sin(2*theta), cos(2*theta)

    二阶谐波用于帮助网络表达风向造成的多峰尾流影响。
    """
    theta = np.deg2rad(frame["wind_direction"].to_numpy(dtype=np.float32))

    features = np.column_stack(
        [
            frame["wind_speed"].to_numpy(dtype=np.float32),
            frame["turbulence_intensity"].to_numpy(dtype=np.float32),
            np.sin(theta),
            np.cos(theta),
            np.sin(2.0 * theta),
            np.cos(2.0 * theta),
        ]
    )
    return features.astype(np.float32)


def make_one_feature_row(
    wind_speed: float,
    wind_direction: float,
    turbulence_intensity: float,
) -> np.ndarray:
    theta = np.deg2rad(np.float32(wind_direction % 360.0))
    return np.array(
        [[
            wind_speed,
            turbulence_intensity,
            np.sin(theta),
            np.cos(theta),
            np.sin(2.0 * theta),
            np.cos(2.0 * theta),
        ]],
        dtype=np.float32,
    )


# =========================
# 4. 建立物理约束神经网络
# =========================
def build_model(x_train: np.ndarray) -> keras.Model:
    normalizer = layers.Normalization(axis=-1, name="feature_normalization")
    normalizer.adapt(x_train)

    inputs = keras.Input(shape=(x_train.shape[1],), name="engineered_inputs")
    x = normalizer(inputs)

    x = layers.Dense(
        64,
        activation="swish",
        kernel_regularizer=regularizers.l2(1e-5),
        name="dense_1",
    )(x)
    x = layers.Dense(
        128,
        activation="swish",
        kernel_regularizer=regularizers.l2(1e-5),
        name="dense_2",
    )(x)
    x = layers.Dense(
        64,
        activation="swish",
        kernel_regularizer=regularizers.l2(1e-5),
        name="dense_3",
    )(x)

    # 三个输出均为各自额定功率的比例，sigmoid 将其限制在 0~1。
    turbine_fraction = layers.Dense(
        3,
        activation="sigmoid",
        name="turbine_power_fraction",
    )(x)

    # farm_fraction = (t1_fraction + t2_fraction + t3_fraction) / 3
    # 因为 farm_power 的缩放基准是 15 MW，而单机缩放基准是 5 MW。
    farm_layer = layers.Dense(
        1,
        use_bias=False,
        trainable=False,
        name="farm_power_fraction",
    )
    farm_fraction = farm_layer(turbine_fraction)

    outputs = layers.Concatenate(name="all_power_fraction")(
        [turbine_fraction, farm_fraction]
    )

    model = keras.Model(inputs=inputs, outputs=outputs, name="wind_farm_power_model")

    # 固定总功率层的权重为 [1/3, 1/3, 1/3]。
    farm_layer.set_weights(
        [np.full((3, 1), 1.0 / 3.0, dtype=np.float32)]
    )

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss=keras.losses.MeanSquaredError(),
        metrics=[keras.metrics.MeanAbsoluteError(name="mae")],
    )
    return model


# =========================
# 5. 评估与保存结果
# =========================
def calculate_metrics(
    y_true_w: np.ndarray,
    y_pred_w: np.ndarray,
) -> pd.DataFrame:
    rows = []
    for i, target in enumerate(TARGET_COLS):
        mae_w = mean_absolute_error(y_true_w[:, i], y_pred_w[:, i])
        rmse_w = np.sqrt(mean_squared_error(y_true_w[:, i], y_pred_w[:, i]))
        r2 = r2_score(y_true_w[:, i], y_pred_w[:, i])

        rows.append(
            {
                "target": target,
                "MAE_W": mae_w,
                "MAE_kW": mae_w / 1_000.0,
                "MAE_percent_of_rated": 100.0 * mae_w / OUTPUT_SCALES_W[i],
                "RMSE_W": rmse_w,
                "RMSE_kW": rmse_w / 1_000.0,
                "R2": r2,
            }
        )
    return pd.DataFrame(rows)


def save_training_plots(
    history: keras.callbacks.History,
    y_true_w: np.ndarray,
    y_pred_w: np.ndarray,
) -> None:
    history_df = pd.DataFrame(history.history)
    history_df.to_csv(RESULT_DIR / "training_history.csv", index=False)

    plt.figure(figsize=(8, 5))
    plt.plot(history_df.index + 1, history_df["loss"], label="train_loss")
    plt.plot(history_df.index + 1, history_df["val_loss"], label="val_loss")
    plt.xlabel("Epoch")
    plt.ylabel("MSE on normalized power")
    plt.title("Training history")
    plt.legend()
    plt.tight_layout()
    plt.savefig(RESULT_DIR / "training_curve.png", dpi=180)
    plt.close()

    for i, target in enumerate(TARGET_COLS):
        plt.figure(figsize=(6, 6))
        plt.scatter(
            y_true_w[:, i] / 1e6,
            y_pred_w[:, i] / 1e6,
            s=18,
            alpha=0.7,
        )
        lower = min(y_true_w[:, i].min(), y_pred_w[:, i].min()) / 1e6
        upper = max(y_true_w[:, i].max(), y_pred_w[:, i].max()) / 1e6
        plt.plot([lower, upper], [lower, upper], linestyle="--")
        plt.xlabel("True power (MW)")
        plt.ylabel("Predicted power (MW)")
        plt.title(f"True vs predicted: {target}")
        plt.tight_layout()
        plt.savefig(RESULT_DIR / f"true_vs_pred_{target}.png", dpi=180)
        plt.close()


def predict_power(
    model: keras.Model,
    wind_speed: float,
    wind_direction: float,
    turbulence_intensity: float,
) -> dict:
    """
    输入一组原始工况，返回四个功率预测值。
    wind_direction 可以是任意角度，会自动映射到 [0, 360)。
    """
    x = make_one_feature_row(
        wind_speed=wind_speed,
        wind_direction=wind_direction,
        turbulence_intensity=turbulence_intensity,
    )
    pred_fraction = model.predict(x, verbose=0)[0]
    pred_w = pred_fraction * OUTPUT_SCALES_W

    return {
        "turbine_1_power_W": float(pred_w[0]),
        "turbine_2_power_W": float(pred_w[1]),
        "turbine_3_power_W": float(pred_w[2]),
        "farm_power_W": float(pred_w[3]),
        "turbine_1_power_MW": float(pred_w[0] / 1e6),
        "turbine_2_power_MW": float(pred_w[1] / 1e6),
        "turbine_3_power_MW": float(pred_w[2] / 1e6),
        "farm_power_MW": float(pred_w[3] / 1e6),
    }


def main() -> None:
    data = load_and_clean_data(DATA_PATH)

    x = make_features(data)
    y_w = data[TARGET_COLS].to_numpy(dtype=np.float32)
    y_fraction = y_w / OUTPUT_SCALES_W

    # 70% 训练、15% 验证、15% 测试。
    all_indices = np.arange(len(data))
    train_val_idx, test_idx = train_test_split(
        all_indices,
        test_size=0.15,
        random_state=SEED,
        shuffle=True,
    )
    train_idx, val_idx = train_test_split(
        train_val_idx,
        test_size=0.15 / 0.85,
        random_state=SEED,
        shuffle=True,
    )

    x_train, y_train = x[train_idx], y_fraction[train_idx]
    x_val, y_val = x[val_idx], y_fraction[val_idx]
    x_test, y_test = x[test_idx], y_fraction[test_idx]

    print(f"训练集: {len(train_idx)}")
    print(f"验证集: {len(val_idx)}")
    print(f"测试集: {len(test_idx)}")

    model = build_model(x_train)
    model.summary()

    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=80,
            min_delta=1e-7,
            restore_best_weights=True,
            verbose=1,
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=20,
            min_lr=1e-6,
            verbose=1,
        ),
    ]

    history = model.fit(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=MAX_EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=callbacks,
        verbose=1,
    )

    # 保存已恢复到最佳验证轮次的模型。
    model.save(MODEL_PATH)

    pred_fraction = model.predict(x_test, verbose=0)
    pred_w = pred_fraction * OUTPUT_SCALES_W
    true_w = y_test * OUTPUT_SCALES_W

    metrics_df = calculate_metrics(true_w, pred_w)
    metrics_df.to_csv(RESULT_DIR / "test_metrics.csv", index=False)

    print("\n测试集评估:")
    print(metrics_df.to_string(index=False))

    # 检查预测结果中的物理一致性。
    predicted_consistency_error = np.abs(
        pred_w[:, 3] - pred_w[:, :3].sum(axis=1)
    )
    print(
        "\n预测 farm_power 与三台风机预测和的最大误差: "
        f"{predicted_consistency_error.max():.6g} W"
    )

    # 保存测试集逐行预测。
    test_output = data.iloc[test_idx][
        ["source_csv_line"] + INPUT_COLS + TARGET_COLS
    ].reset_index(drop=True)

    for i, target in enumerate(TARGET_COLS):
        test_output[f"pred_{target}"] = pred_w[:, i]
        test_output[f"error_{target}"] = pred_w[:, i] - true_w[:, i]

    test_output.to_csv(
        RESULT_DIR / "test_predictions.csv",
        index=False,
        encoding="utf-8-sig",
    )

    save_training_plots(history, true_w, pred_w)

    metadata = {
        "raw_input_columns": INPUT_COLS,
        "engineered_features": [
            "wind_speed",
            "turbulence_intensity",
            "sin(direction)",
            "cos(direction)",
            "sin(2*direction)",
            "cos(2*direction)",
        ],
        "target_columns": TARGET_COLS,
        "output_scales_W": OUTPUT_SCALES_W.tolist(),
        "split": {
            "train_samples": int(len(train_idx)),
            "validation_samples": int(len(val_idx)),
            "test_samples": int(len(test_idx)),
            "random_seed": SEED,
        },
        "data_ranges": {
            col: {
                "min": float(data[col].min()),
                "max": float(data[col].max()),
            }
            for col in INPUT_COLS + TARGET_COLS
        },
    }
    with open(RESULT_DIR / "model_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # 给出一组调用示例。
    loaded_model = keras.models.load_model(MODEL_PATH)
    example = predict_power(
        loaded_model,
        wind_speed=8.0,
        wind_direction=270.0,
        turbulence_intensity=0.08,
    )
    print("\n示例预测: wind_speed=8.0, wind_direction=270°, TI=0.08")
    print(json.dumps(example, ensure_ascii=False, indent=2))

    print(f"\n模型已保存到: {MODEL_PATH}")
    print(f"评估结果已保存到: {RESULT_DIR}")


if __name__ == "__main__":
    main()
