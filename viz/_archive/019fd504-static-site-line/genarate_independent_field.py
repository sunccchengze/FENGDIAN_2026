from floris import FlorisModel
from pathlib import Path
from scipy.interpolate import griddata
import floris
import numpy as np
import os

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

os.makedirs("fields_array", exist_ok=True)

# 两种配置：基准（全0°）和独立优化（排1:+30°，排2:+20°，排3:0°）
configs = {
    "baseline":     [0.0]*9,
    "independent":  [30.0, 30.0, 30.0, 20.0, 20.0, 20.0, 0.0, 0.0, 0.0],
}

for name, yaws in configs.items():
    fmodel.set(yaw_angles=np.array([yaws]))
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

    np.savez(f"fields_array/{name}.npz",
             x=x_unique, y=y_unique, u=U_grid)
    print(f"✅ {name} 流场已保存")