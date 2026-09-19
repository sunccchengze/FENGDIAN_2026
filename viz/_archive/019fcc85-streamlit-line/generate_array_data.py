from floris import FlorisModel
from pathlib import Path
import floris
import numpy as np
import pandas as pd
import os

print("=" * 40)
print("开始生成 3×3 风机阵列数据")
print("=" * 40)

floris_dir = Path(floris.__file__).parent
config_path = floris_dir / "default_inputs.yaml"
fmodel = FlorisModel(str(config_path))

# ===== 3×3 阵列布局 =====
# 行间距：5D = 630m（顺风方向）
# 列间距：3D = 378m（横向）
D = 126.0   # NREL 5MW 转子直径

layout_x = []
layout_y = []
for row in range(3):       # 顺风方向3排
    for col in range(3):   # 横向3列
        layout_x.append(row * 5 * D)    # 0, 630, 1260 m
        layout_y.append((col - 1) * 3 * D)  # -378, 0, 378 m

layout_x = np.array(layout_x)
layout_y = np.array(layout_y)

print("风机布局（9台）：")
for i, (x, y) in enumerate(zip(layout_x, layout_y)):
    row = i // 3 + 1
    col = i % 3 + 1
    print(f"  风机{i+1}（第{row}排第{col}列）：x={x:.0f}m  y={y:.0f}m")

fmodel.set(
    layout_x=layout_x.tolist(),
    layout_y=layout_y.tolist(),
    wind_directions=[270.0],
    wind_speeds=[8.0],
    turbulence_intensities=[0.06],
)

# ===== 扫描偏航角 =====
# 只让第一排（上游3台）偏航，下游固定0°
yaw_angles = np.arange(-30, 31, 5)
print(f"\n共 {len(yaw_angles)} 个工况（上游偏航角 -30° 到 +30°）")

os.makedirs("fields_array", exist_ok=True)
records = []

for i, yaw in enumerate(yaw_angles):
    case_id = f"array_yaw_{yaw:+03d}"

    # 第一排3台偏航，其余6台固定0°
    yaw_matrix = np.array([[
        float(yaw), float(yaw), float(yaw),  # 第一排
        0.0, 0.0, 0.0,                        # 第二排
        0.0, 0.0, 0.0                          # 第三排
    ]])

    fmodel.set(yaw_angles=yaw_matrix)
    fmodel.run()

    powers = fmodel.get_turbine_powers()[0] / 1000  # shape: (9,), kW
    total  = powers.sum()

    records.append({
        "case_id":    case_id,
        "yaw_upstream": yaw,
        **{f"power_{i+1}": round(float(p), 2) for i, p in enumerate(powers)},
        "power_total": round(float(total), 2),
    })

    print(f"  {case_id}：总功率={total:.0f}kW  "
          f"[{', '.join(f'{p:.0f}' for p in powers)}] kW  ✅")

df = pd.DataFrame(records)

# 计算功率增益
baseline = df[df["yaw_upstream"] == 0]["power_total"].values[0]
df["gain_pct"] = (df["power_total"] - baseline) / baseline * 100

df.to_csv("cases_array.csv", index=False)

best = df.loc[df["power_total"].idxmax()]
print(f"\n✅ cases_array.csv 已保存（{len(df)} 条工况）")
print(f"基准总功率（0°）：{baseline:.0f} kW")
print(f"最优偏航角：{best['yaw_upstream']:+.0f}°")
print(f"最优总功率：{best['power_total']:.0f} kW")
print(f"最大功率提升：{best['gain_pct']:.1f}%")
