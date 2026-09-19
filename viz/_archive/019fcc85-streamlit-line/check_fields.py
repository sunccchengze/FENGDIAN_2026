import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False
import numpy as np
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 3, figsize=(15, 4))

# 画三个有代表性的工况
cases = [
    ("case_0001.npz", "偏航 -30°"),
    ("case_0007.npz", "偏航 0°（基准）"),
    ("case_0013.npz", "偏航 +30°"),
]

for ax, (filename, title) in zip(axes, cases):
    data = np.load(f"fields/{filename}")
    x = data["x"]
    y = data["y"]
    u = data["u"]

    im = ax.contourf(x, y, u, levels=20, cmap="RdBu_r", vmin=4, vmax=9)
    plt.colorbar(im, ax=ax, label="风速 (m/s)")

    # 标注风机位置
    ax.plot(0, 0, "k^", markersize=10)
    ax.plot(630, 0, "k^", markersize=10)
    ax.text(0, 50, "风机1", ha="center")
    ax.text(630, 50, "风机2", ha="center")

    ax.set_title(title)
    ax.set_xlabel("顺风方向 x (m)")
    ax.set_ylabel("横向 y (m)")

plt.suptitle("FLORIS尾流数据验证", fontsize=14)
plt.tight_layout()
plt.savefig("check_fields.png", dpi=150)
plt.show()
print("✅ 图片已保存为 check_fields.png")
