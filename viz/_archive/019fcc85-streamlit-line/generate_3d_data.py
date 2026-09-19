from floris import FlorisModel
from pathlib import Path
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter
import floris
import numpy as np
import os

print("=" * 40)
print("开始生成三维流场数据")
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

heights    = np.linspace(20, 180, 9)
yaw_angles = [-30, -15, 0, 15, 30]

os.makedirs("fields_3d", exist_ok=True)

for yaw in yaw_angles:
    print(f"\n偏航角 = {yaw:+.0f}°")
    fmodel.set(yaw_angles=np.array([[float(yaw), 0.0]]))
    fmodel.run()

    U_3d = []

    for h in heights:
        plane = fmodel.calculate_horizontal_plane(
            height=float(h),
            x_resolution=64,
            y_resolution=32,
            x_bounds=(-200, 900),
            y_bounds=(-300, 300),
        )

        x_vals = plane.df["x1"].values
        y_vals = plane.df["x2"].values
        u_vals = plane.df["u"].values

        x_unique = np.unique(x_vals)
        y_unique = np.unique(y_vals)
        X_grid, Y_grid = np.meshgrid(x_unique, y_unique)

        # linear 插值
        U_grid = griddata(
            points=(x_vals, y_vals),
            values=u_vals,
            xi=(X_grid, Y_grid),
            method="linear"
        )

        # nearest 补全 NaN
        nan_mask = np.isnan(U_grid)
        if nan_mask.any():
            U_nearest = griddata(
                points=(x_vals, y_vals),
                values=u_vals,
                xi=(X_grid, Y_grid),
                method="nearest"
            )
            U_grid[nan_mask] = U_nearest[nan_mask]

        # ===== 新增：边界区域强制恢复来流风速 =====
        # 在计算域边界（x<0 或 x>850 或 |y|>250）不应有尾流
        # 强制赋值为来流风速 8.0 m/s，消除边界插值伪影
        X_abs = np.abs(X_grid)
        Y_abs = np.abs(Y_grid)
        boundary_mask = (X_grid < -100) | (X_grid > 850) | (Y_abs > 260)
        U_grid[boundary_mask] = 8.0

        # ===== 新增：轻度高斯平滑，消除孤立伪影点 =====
        U_grid = gaussian_filter(U_grid, sigma=0.8)

        U_3d.append(U_grid)
        print(f"  高度 {h:.0f}m 完成  "
              f"min={U_grid.min():.2f}  max={U_grid.max():.2f}")

    U_3d = np.array(U_3d)

    filename = f"fields_3d/yaw_{yaw:+03d}.npz"
    np.savez(filename, x=x_unique, y=y_unique, z=heights, u=U_3d)
    print(f"  已保存：{filename}  形状：{U_3d.shape}")

print("\n✅ 全部三维数据生成完毕")