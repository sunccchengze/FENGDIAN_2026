from floris import FlorisModel
from pathlib import Path
import floris
import numpy as np
import pandas as pd
import json
import os

print("=" * 40)
print("开始生成多风向数据集")
print("=" * 40)

floris_dir = Path(floris.__file__).parent
config_path = floris_dir / "default_inputs.yaml"
fmodel = FlorisModel(str(config_path))

fmodel.set(
    layout_x=[0.0, 630.0],
    layout_y=[0.0, 0.0],
    wind_directions=[270.0],
    wind_speeds=[8.0],
    turbulence_intensities=[0.06],
)

# 12个风向（0°到330°，步长30°）
# 4个风速（6/8/10/12 m/s）
# 每个风向下扫描偏航角（-30°到30°，步长5°）
wind_directions = np.arange(0, 360, 30)
wind_speeds     = [6.0, 8.0, 10.0, 12.0]
yaw_angles      = np.arange(-30, 31, 5)

print(f"风向：{list(wind_directions)} °")
print(f"风速：{wind_speeds} m/s")
print(f"偏航角：{list(yaw_angles)} °")
print(f"总工况数：{len(wind_directions) * len(wind_speeds) * len(yaw_angles)}")

records = []

for wd in wind_directions:
    for U in wind_speeds:
        fmodel.set(
            wind_directions=[float(wd)],
            wind_speeds=[float(U)],
        )

        for yaw in yaw_angles:
            fmodel.set(yaw_angles=np.array([[float(yaw), 0.0]]))
            fmodel.run()

            powers = fmodel.get_turbine_powers()
            p1 = powers[0, 0] / 1000
            p2 = powers[0, 1] / 1000

            records.append({
                "wind_direction": wd,
                "U_inf":         U,
                "yaw_1":         yaw,
                "yaw_2":         0.0,
                "power_1":       round(p1, 2),
                "power_2":       round(p2, 2),
                "power_total":   round(p1 + p2, 2),
            })

        print(f"  风向={wd:3.0f}°  风速={U:.0f}m/s  完成 ✅")

df = pd.DataFrame(records)

# 计算每个风向+风速组合下的最优偏航角
opt_records = []
for wd in wind_directions:
    for U in wind_speeds:
        subset = df[(df["wind_direction"] == wd) & (df["U_inf"] == U)]
        best   = subset.loc[subset["power_total"].idxmax()]
        base   = subset[subset["yaw_1"] == 0]["power_total"].values[0]
        gain   = (best["power_total"] - base) / base * 100
        opt_records.append({
            "wind_direction": wd,
            "U_inf":          U,
            "best_yaw":       best["yaw_1"],
            "power_base":     round(base, 2),
            "power_opt":      round(best["power_total"], 2),
            "gain_pct":       round(gain, 2),
        })

df_opt = pd.DataFrame(opt_records)

df.to_csv("cases_windrose.csv",     index=False)
df_opt.to_csv("cases_windrose_opt.csv", index=False)

print(f"\n✅ cases_windrose.csv 已保存（{len(df)} 条）")
print(f"✅ cases_windrose_opt.csv 已保存（{len(df_opt)} 条）")
print("\n各风向下平均最优偏航角：")
for wd in wind_directions:
    avg_yaw  = df_opt[df_opt["wind_direction"] == wd]["best_yaw"].mean()
    avg_gain = df_opt[df_opt["wind_direction"] == wd]["gain_pct"].mean()
    print(f"  风向={wd:3.0f}°  平均最优偏航={avg_yaw:+.1f}°  "
          f"平均增益={avg_gain:+.1f}%")