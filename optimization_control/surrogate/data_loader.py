"""加载 FLORIS 数据：读取 CSV、清洗（去零功率/非有限）、6 特征工程"""

import numpy as np
import pandas as pd


RAW_COLS = [
    "wind_speed",
    "wind_direction",
    "turbulence_intensity",
    "turbine_1_power",
    "turbine_2_power",
    "turbine_3_power",
    "farm_power",
]
TARGET_COLS = RAW_COLS[3:]


def load_raw(csv_path: str) -> pd.DataFrame:
    """读取原始 CSV 并做基本列检查"""
    raw = pd.read_csv(csv_path)
    missing = [c for c in RAW_COLS if c not in raw.columns]
    if missing:
        raise ValueError(f"CSV 缺少必要列: {missing}")
    return raw


def clean_data(raw: pd.DataFrame) -> pd.DataFrame:
    """清洗：去除非有限值与任一风机功率为 0 的行（与厉今飞训练脚本一致）"""
    data = raw[RAW_COLS].copy()
    non_finite = ~np.isfinite(data[TARGET_COLS].to_numpy(dtype=float)).all(axis=1)
    zero_target = (data[TARGET_COLS] == 0).any(axis=1)
    valid = ~(non_finite | zero_target)
    n_drop = int((~valid).sum())
    clean = data[valid].reset_index(drop=True)
    print(f"清洗: {len(data)} -> {len(clean)} 行（剔除 {n_drop} 行: 非有限 {int(non_finite.sum())} + 零功率 {int(zero_target.sum())}）")
    return clean


def make_features(frame: pd.DataFrame) -> np.ndarray:
    """6 特征编码: [U, TI, sin(theta), cos(theta), sin(2*theta), cos(2*theta)]，theta=风向(弧度)"""
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


def make_one_feature_row(wind_speed: float, wind_direction: float, turbulence_intensity: float) -> np.ndarray:
    """单条推理用 6 特征编码（风向自动映射 [0,360)）"""
    theta = np.deg2rad(np.float32(wind_direction % 360.0))
    return np.array(
        [
            np.float32(wind_speed),
            np.float32(turbulence_intensity),
            np.sin(theta),
            np.cos(theta),
            np.sin(2.0 * theta),
            np.cos(2.0 * theta),
        ],
        dtype=np.float32,
    )
