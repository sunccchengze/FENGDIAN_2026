import numpy as np

# ===== 保存数据到文件 =====
x = np.linspace(0, 1000, 128)
y = np.linspace(-300, 300, 64)
U = np.ones((64, 128)) * 8.0    # 随便造个数据

# 把三个数组打包存成一个文件
np.savez("test_field.npz", x=x, y=y, u=U)
print("已保存 test_field.npz")

# ===== 读取文件 =====
data = np.load("test_field.npz")

print("文件里有：", list(data.keys()))   # ['x', 'y', 'u']
print("x的形状：", data["x"].shape)      # (128,)
print("y的形状：", data["y"].shape)      # (64,)
print("u的形状：", data["u"].shape)      # (64, 128)
print("u里第一个数：", data["u"][0, 0])  # 8.0