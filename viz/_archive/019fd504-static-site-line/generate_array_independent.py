from floris import FlorisModel
from pathlib import Path
import floris
import numpy as np
import pandas as pd
import os

print("=" * 40)
print("3×3 阵列独立偏航优化")
print("=" * 40)

floris_dir = Path(floris.__file__).parent
config_path = floris_dir / "default_inputs.yaml"
fmodel = FlorisModel(str(config_path))

D = 126.0
layout_x = [row * 5 * D for row in range(3) for col in range(3)]
layout_y  = [(col - 1) * 3 * D for row in range(3) for col in range(3)]

fmodel.set(
    layout_x=layout_x,
    layout_y=layout_y,
    wind_directions=[270.0],
    wind_speeds=[8.0],
    turbulence_intensities=[0.06],
)

yaw_candidates = np.arange(-30, 31, 5)

# ===== 贪心逐排优化 =====
# 原理：从上游到下游逐排优化，每排固定后优化下一排
# 这比"全部统一偏航"更接近真实协同控制

print("\n开始贪心逐排优化...")
best_yaws = [0.0] * 9   # 初始全部0°

for target_row in range(3):
    print(f"\n优化第 {target_row+1} 排...")
    best_power = -1
    best_yaw_for_row = 0.0

    for yaw in yaw_candidates:
        # 当前排设置候选偏航，其他排保持已优化的值
        trial_yaws = best_yaws.copy()
        for col in range(3):
            trial_yaws[target_row * 3 + col] = float(yaw)

        fmodel.set(yaw_angles=np.array([trial_yaws]))
        fmodel.run()
        powers = fmodel.get_turbine_powers()[0] / 1000
        total  = powers.sum()

        if total > best_power:
            best_power = total
            best_yaw_for_row = float(yaw)

    # 固定当前排的最优偏航
    for col in range(3):
        best_yaws[target_row * 3 + col] = best_yaw_for_row

    print(f"  第 {target_row+1} 排最优偏航：{best_yaw_for_row:+.0f}°  "
          f"当前总功率：{best_power:.0f} kW")

# ===== 计算最终结果 =====
fmodel.set(yaw_angles=np.array([best_yaws]))
fmodel.run()
final_powers = fmodel.get_turbine_powers()[0] / 1000

# 基准（全部0°）
fmodel.set(yaw_angles=np.array([[0.0]*9]))
fmodel.run()
baseline_powers = fmodel.get_turbine_powers()[0] / 1000
baseline_total  = baseline_powers.sum()
final_total     = final_powers.sum()
gain            = (final_total - baseline_total) / baseline_total * 100

print(f"\n===== 贪心优化结果 =====")
print(f"各排最优偏航角：")
for row in range(3):
    yaw = best_yaws[row * 3]
    print(f"  第 {row+1} 排：{yaw:+.0f}°")
print(f"基准总功率（全0°）：{baseline_total:.0f} kW")
print(f"独立优化总功率：{final_total:.0f} kW")
print(f"功率提升：{gain:.1f}%")

# ===== 对比三种策略 =====
print("\n===== 三种策略对比 =====")

# 策略1：无偏航
fmodel.set(yaw_angles=np.array([[0.0]*9]))
fmodel.run()
p_none = fmodel.get_turbine_powers()[0].sum() / 1000

# 策略2：统一偏航（从cases_array.csv读取最优）
df_array = pd.read_csv("cases_array.csv")
best_unified = df_array.loc[df_array["power_total"].idxmax()]
unified_yaw  = float(best_unified["yaw_upstream"])
unified_yaws = [unified_yaw]*3 + [0.0]*6
fmodel.set(yaw_angles=np.array([unified_yaws]))
fmodel.run()
p_unified = fmodel.get_turbine_powers()[0].sum() / 1000

# 策略3：独立优化
p_independent = final_total

strategies = {
    "无偏航（基准）":   p_none,
    f"统一偏航（{unified_yaw:+.0f}°）": p_unified,
    "逐排独立优化":     p_independent,
}

for name, power in strategies.items():
    gain_vs_base = (power - p_none) / p_none * 100
    print(f"  {name}：{power:.0f} kW  ({gain_vs_base:+.1f}%)")

# ===== 保存结果 =====
result = {
    "greedy_yaws":        best_yaws,
    "greedy_row_yaws":    [best_yaws[i*3] for i in range(3)],
    "power_none":         round(float(p_none), 2),
    "power_unified":      round(float(p_unified), 2),
    "power_independent":  round(float(p_independent), 2),
    "unified_yaw":        float(unified_yaw),
    "gain_unified_pct":   round((p_unified - p_none) / p_none * 100, 2),
    "gain_independent_pct": round((p_independent - p_none) / p_none * 100, 2),
    "turbine_powers_none":        [round(float(p), 2) for p in baseline_powers],
    "turbine_powers_independent": [round(float(p), 2) for p in final_powers],
}

import json
with open("array_independent_result.json", "w") as f:
    json.dump(result, f, indent=2)

print(f"\n✅ array_independent_result.json 已保存")
