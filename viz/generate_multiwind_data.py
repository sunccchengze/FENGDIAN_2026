from floris import FlorisModel
from pathlib import Path
from scipy.interpolate import griddata
import floris
import numpy as np
import pandas as pd
import json
import os

print("=" * 40)
print("开始生成多风速数据集")
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

# 四个风速，13个偏航角
wind_speeds  = [6.0, 8.0, 10.0, 12.0]
yaw_angles   = np.arange(-30, 31, 5)

os.makedirs("fields_multi", exist_ok=True)
records = []

for U_inf in wind_speeds:
    print(f"\n风速 = {U_inf} m/s")
    fmodel.set(wind_speeds=[U_inf])

    for i, yaw in enumerate(yaw_angles):
        case_id = f"U{U_inf:.0f}_yaw_{yaw:+03d}"

        fmodel.set(yaw_angles=np.array([[float(yaw), 0.0]]))
        fmodel.run()

        powers = fmodel.get_turbine_powers()
        p1 = powers[0, 0] / 1000
        p2 = powers[0, 1] / 1000

        records.append({
            "case_id":  case_id,
            "U_inf":    U_inf,
            "yaw_1":    yaw,
            "yaw_2":    0.0,
            "power_1":  round(p1, 2),
            "power_2":  round(p2, 2),
        })

        print(f"  {case_id}：P1={p1:.1f}kW  P2={p2:.1f}kW  总={p1+p2:.1f}kW  ✅")

df = pd.DataFrame(records)
df["power_total"] = df["power_1"] + df["power_2"]

# 计算每个风速下相对基准（偏航0°）的功率增益
baselines = df[df["yaw_1"] == 0].set_index("U_inf")["power_total"]
df["gain_pct"] = df.apply(
    lambda r: (r["power_total"] - baselines[r["U_inf"]]) / baselines[r["U_inf"]] * 100,
    axis=1
)

df.to_csv("cases_multi.csv", index=False)
print("\n✅ cases_multi.csv 已保存")
print(f"共 {len(df)} 条记录（{len(wind_speeds)} 个风速 × {len(yaw_angles)} 个偏航角）")