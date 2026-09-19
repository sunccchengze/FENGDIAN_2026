import numpy as np
import matplotlib.pyplot as plt

# ===== 第一步：造一个假的速度场 =====
x = np.linspace(0, 1000, 128)
y = np.linspace(-300, 300, 64)
X, Y = np.meshgrid(x, y)

# 来流风速 8 m/s，全场初始化为8
U = np.full_like(X, 8.0)

# 在风机（x=100m）后方制造速度亏缺（尾流）
for i in range(128):
    if x[i] > 100:
        deficit = 0.4 * np.exp(-Y[:, i]**2 / (2 * 40**2))
        U[:, i] = 8.0 * (1 - deficit)

# ===== 第二步：画图 =====
fig, ax = plt.subplots(figsize=(12, 5))

contour = ax.contourf(X, Y, U, levels=20, cmap="RdBu_r")
plt.colorbar(contour, ax=ax, label="风速 (m/s)")

ax.plot(100, 0, "k^", markersize=12, label="风机1")
ax.set_xlabel("顺风方向 x (m)")
ax.set_ylabel("横向 y (m)")
ax.set_title("Wind Turbine Wake")
ax.legend()

plt.tight_layout()
plt.savefig("my_first_wake.png", dpi=150)
plt.show()
print("图片已保存为 my_first_wake.png")