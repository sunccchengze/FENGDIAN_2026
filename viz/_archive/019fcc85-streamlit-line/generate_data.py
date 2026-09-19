from floris import FlorisModel
from pathlib import Path
from scipy.interpolate import griddata
import floris
import numpy as np
import pandas as pd
import json
import os

print("=" * 40)
print("开始生成数据集")
print("=" * 40)

# 初始化FLORIS
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

yaw_angles = np.arange(-30, 31, 5)
print(f"共 {len(yaw_angles)} 个工况")

os.makedirs("fields", exist_ok=True)
records = []

for i, yaw in enumerate(yaw_angles):
    case_id = f"case_{i+1:04d}"

    # 设置偏航角
    fmodel.set(yaw_angles=np.array([[float(yaw), 0.0]]))
    fmodel.run()

    # 获取功率
    powers = fmodel.get_turbine_powers()
    p1 = powers[0, 0] / 1000
    p2 = powers[0, 1] / 1000

    # 记录功率数据
    records.append({
        "case_id": case_id,
        "U_inf": 8.0,
        "yaw_1": yaw,
        "yaw_2": 0.0,
        "power_1": round(p1, 2),
        "power_2": round(p2, 2),
    })

    # 计算水平截面流场
    horizontal_plane = fmodel.calculate_horizontal_plane(
        height=90.0,
        x_resolution=128,
        y_resolution=64,
        x_bounds=(-200, 900),
        y_bounds=(-300, 300),
    )

    # 取出坐标和速度
    x_vals = horizontal_plane.df["x1"].values
    y_vals = horizontal_plane.df["x2"].values
    u_vals = horizontal_plane.df["u"].values

    # 整理成二维网格
    x_unique = np.unique(x_vals)
    y_unique = np.unique(y_vals)
    X_grid, Y_grid = np.meshgrid(x_unique, y_unique)

    # linear插值
    U_grid = griddata(
        points=(x_vals, y_vals),
        values=u_vals,
        xi=(X_grid, Y_grid),
        method="linear"
    )

    # 修复NaN：用nearest填充linear插值凸包外的空白区域
    nan_mask = np.isnan(U_grid)
    if nan_mask.any():
        U_grid_nearest = griddata(
            points=(x_vals, y_vals),
            values=u_vals,
            xi=(X_grid, Y_grid),
            method="nearest"
        )
        U_grid[nan_mask] = U_grid_nearest[nan_mask]

    # 保存流场文件
    np.savez(
        f"fields/{case_id}.npz",
        x=x_unique,
        y=y_unique,
        u=U_grid,
    )

    print(f"{case_id}：偏航={yaw:+3.0f}°，"
          f"P1={p1:.1f}kW，P2={p2:.1f}kW，"
          f"总={p1+p2:.1f}kW  ✅")

# 保存cases.csv
df = pd.DataFrame(records)
df["power_total"] = df["power_1"] + df["power_2"]
df.to_csv("cases.csv", index=False)

# 保存optimizer_result.json
best_idx = df["power_total"].idxmax()
best_yaw = df["yaw_1"].iloc[best_idx]
best_power = df["power_total"].iloc[best_idx]
baseline = df[df["yaw_1"] == 0]["power_total"].values[0]
gain = (best_power - baseline) / baseline * 100

result = {
    "wind_speed": 8.0,
    "original_yaw": 0,
    "recommended_yaw": int(best_yaw),
    "power_before": round(float(baseline), 2),
    "power_after": round(float(best_power), 2),
    "power_gain_pct": round(gain, 2)
}
with open("optimizer_result.json", "w") as f:
    json.dump(result, f, indent=2)

print("\n✅ cases.csv 已保存")
print("✅ optimizer_result.json 已保存")
print("✅ fields/ 文件夹里有13个.npz文件")
print(f"\n最优偏航角：{best_yaw}°，功率提升：{gain:.1f}%")