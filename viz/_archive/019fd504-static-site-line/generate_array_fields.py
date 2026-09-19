from floris import FlorisModel
from pathlib import Path
from scipy.interpolate import griddata
import floris
import numpy as np
import pandas as pd
import os

print("生成 3×3 阵列流场数据...")

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

yaw_angles = np.arange(-30, 31, 5)
os.makedirs("fields_array", exist_ok=True)

for yaw in yaw_angles:
    fmodel.set(yaw_angles=np.array(
        [[float(yaw)]*3 + [0.0]*6]
    ))
    fmodel.run()

    plane = fmodel.calculate_horizontal_plane(
        height=90.0,
        x_resolution=128,
        y_resolution=64,
        x_bounds=(-200, 1500),
        y_bounds=(-600, 600),
    )

    x_vals = plane.df["x1"].values
    y_vals = plane.df["x2"].values
    u_vals = plane.df["u"].values

    x_unique = np.unique(x_vals)
    y_unique = np.unique(y_vals)
    X_grid, Y_grid = np.meshgrid(x_unique, y_unique)

    U_grid = griddata(
        points=(x_vals, y_vals),
        values=u_vals,
        xi=(X_grid, Y_grid),
        method="linear"
    )
    nan_mask = np.isnan(U_grid)
    if nan_mask.any():
        U_nearest = griddata(
            points=(x_vals, y_vals),
            values=u_vals,
            xi=(X_grid, Y_grid),
            method="nearest"
        )
        U_grid[nan_mask] = U_nearest[nan_mask]

    np.savez(f"fields_array/yaw_{yaw:+03d}.npz",
             x=x_unique, y=y_unique, u=U_grid)
    print(f"  偏航 {yaw:+.0f}° 完成 ✅")

print("✅ 全部流场数据生成完毕")