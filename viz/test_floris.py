from floris import FlorisModel
from pathlib import Path
import floris
import numpy as np

print("正在启动FLORIS...")

# 自动找到配置文件的位置
floris_dir = Path(floris.__file__).parent
config_path = floris_dir / "default_inputs.yaml"
print("配置文件路径：", config_path)

# 初始化模型
fmodel = FlorisModel(str(config_path))

# 设置两台风机
fmodel.set(
    layout_x=[0.0, 630.0],
    layout_y=[0.0, 0.0],
    wind_directions=[270.0],
    wind_speeds=[8.0],
    turbulence_intensities=[0.06],
)

# 运行计算
fmodel.run()

# 获取功率
powers = fmodel.get_turbine_powers()
p1 = powers[0, 0] / 1000
p2 = powers[0, 1] / 1000

print(f"风机1功率：{p1:.1f} kW")
print(f"风机2功率：{p2:.1f} kW")
print(f"总功率：{p1+p2:.1f} kW")
print("✅ FLORIS运行成功！")