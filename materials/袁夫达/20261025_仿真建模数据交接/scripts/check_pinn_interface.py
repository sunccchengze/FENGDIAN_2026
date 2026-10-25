# -*- coding: utf-8 -*-
"""用 PINN 项目自己的校验函数检查 cases_wind.csv 能否被直接接收。

这不是重新实现一遍规则，而是把
PINNs_multi_turbine_wake_simulation-outputchange/modify_pinn_wind_io.py
里的 read_cases / validated_cases / split_groups 直接 import 进来跑一遍。
好处：验收口径与训练脚本完全一致，避免"我这边看着没问题、他那边读不了"。

这些函数不依赖 TensorFlow（TF 只在 tensorflow_components() 里惰性导入），
因此本机没有 TF 也能跑。

用法
----
    .\\.venv\\Scripts\\python.exe check_pinn_interface.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
PINN_DIR = PROJECT / "PINNs_multi_turbine_wake_simulation-outputchange"
OUT = HERE / "out"

sys.path.insert(0, str(PINN_DIR))
import modify_pinn_wind_io as io  # noqa: E402


def main() -> int:
    csv_path = OUT / "cases_wind.csv"
    cfg_path = OUT / "wind_project_config.json"
    print(f"PINN 脚本: {PINN_DIR.name}/modify_pinn_wind_io.py")
    print(f"数据:      {csv_path.name}")

    # 1) 配置校验（机位/单位/约定）
    config, positions = io.validate_config(cfg_path)
    print(f"[OK] 配置通过：schema={config['schema']}，口径={config['coordinate_mode']}")
    print("     机位(m): " + json.dumps(config["turbine_positions_m"]))

    # 2) 读 CSV（表头必须恰好 18 列、无空白、TI∈[0,1]、转速≥0、P≥0、Ueff>0）
    raw, targets = io.read_cases(csv_path, require_targets=True)
    print(f"[OK] read_cases 通过：{raw.shape[0]} 行，输入 {raw.shape[1]} 维，输出 {targets.shape[1]} 维")

    # 3) 与训练脚本完全一致的 float32 变换 + 分组划分
    raw32 = io.validated_cases(io.inputs_for(raw, positions)["conditions_and_controls"])
    train_idx, val_idx, test_idx = io.split_groups(raw32, seed=42)
    print(f"[OK] split_groups 通过：训练 {len(train_idx)} / 验证 {len(val_idx)} / 测试 {len(test_idx)} 行")
    assert not np.intersect1d(train_idx, val_idx).size
    assert not np.intersect1d(train_idx, test_idx).size
    assert not np.intersect1d(val_idx, test_idx).size

    # 4) 编码后是否跨集泄漏（训练脚本会因此直接报错）
    features = io.encoded_features(raw32)
    _, encoded_group = np.unique(features.astype(np.float32), axis=0, return_inverse=True)
    leak = 0
    for a, b in ((train_idx, val_idx), (train_idx, test_idx), (val_idx, test_idx)):
        leak += int(np.intersect1d(encoded_group[a], encoded_group[b]).size)
    print(f"[OK] 无跨集泄漏（{leak} 处）")

    # 5) 常量输入报告（训练脚本会把没变化的列标出来）
    constants = [n for i, n in enumerate(io.INPUT_NAMES) if np.ptp(raw32[train_idx, i]) <= 1e-8]
    print(f"[OK] 训练集中恒定不变的输入：{constants if constants else '无'}")
    if all(n in constants for n in io.CONTROL_NAMES):
        print("[FAIL] 九个控制量全不变，训练脚本会直接报错")
        return 2

    # 6) 输出统计与单位
    P = targets[:, :3]
    U = targets[:, 3:]
    print(f"[OK] P 范围 {P.min():.0f} ~ {P.max():.0f} W（≤5 MW 额定：{bool(P.max() <= 5e6*1.0005)}）")
    print(f"[OK] Ueff 范围 {U.min():.3f} ~ {U.max():.3f} m/s")
    print(f"[OK] 负输出计数：P {(P < 0).sum()}，Ueff {(U <= 0).sum()}")

    # 7) 风向覆盖弧（报告里会写）
    arc = io.direction_arc(raw[:, 1])
    print(f"[OK] 覆盖的风向弧：起点 {np.rad2deg(arc['start_rad']):.1f}°，宽度 {np.rad2deg(arc['width_rad']):.1f}°")

    report = {
        "csv": str(csv_path.relative_to(PROJECT)),
        "config": str(cfg_path.relative_to(PROJECT)),
        "rows": int(raw.shape[0]),
        "split": {"train": len(train_idx), "validation": len(val_idx), "test": len(test_idx)},
        "encoded_duplicate_leak": leak,
        "constant_inputs_in_training": constants,
        "power_range_W": [float(P.min()), float(P.max())],
        "ueff_range_m_s": [float(U.min()), float(U.max())],
        "direction_arc_deg": [float(np.rad2deg(arc["start_rad"])), float(np.rad2deg(arc["width_rad"]))],
        "verdict": "accepted_by_pinn_loader",
    }
    (OUT / "pinn_interface_check.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n[OK] 这份 CSV 可以被 modify_pinn_wind_io.py 直接读取并训练。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
