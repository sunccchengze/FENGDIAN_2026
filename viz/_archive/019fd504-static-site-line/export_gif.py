import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

# ===== 读取所有工况数据 =====
df = pd.read_csv("cases.csv")
frames = []
for _, row in df.iterrows():
    data = np.load(f"fields/{row['case_id']}.npz")
    frames.append({
        "yaw": float(row["yaw_1"]),
        "x":   data["x"],
        "y":   data["y"],
        "u":   data["u"],
        "p1":  float(row["power_1"]),
        "p2":  float(row["power_2"]),
    })

# 正向 + 反向，共26帧，形成来回循环
all_frames = frames + list(reversed(frames))

# ===== 建画布 =====
fig, ax = plt.subplots(figsize=(12, 5))
plt.tight_layout(pad=2)

f0 = all_frames[0]
mesh = ax.contourf(f0["x"], f0["y"], f0["u"],
                   levels=50, cmap="RdBu_r", vmin=4, vmax=9)
cbar = plt.colorbar(mesh, ax=ax, label="风速 (m/s)")

turbines, = ax.plot([0, 630], [0, 0], "k^", markersize=10, label="风机")
title = ax.set_title("")
ax.set_xlabel("顺风方向 x (m)")
ax.set_ylabel("横向 y (m)")
ax.legend(loc="upper right")

# ===== 逐帧更新函数 =====
def update(i):
    global mesh
    f = all_frames[i]

    # 清除上一帧的等值线
    for c in ax.collections:
        c.remove()

    mesh = ax.contourf(f["x"], f["y"], f["u"],
                       levels=50, cmap="RdBu_r", vmin=4, vmax=9)

    # 重新画风机标注
    ax.plot([0, 630], [0, 0], "k^", markersize=10)

    total = f["p1"] + f["p2"]
    baseline = 2190.4
    gain = (total - baseline) / baseline * 100
    title.set_text(
        f"偏航角 = {f['yaw']:+.0f}°  |  "
        f"P₁={f['p1']:.0f} kW  "
        f"P₂={f['p2']:.0f} kW  "
        f"总={total:.0f} kW  ({gain:+.1f}%)"
    )
    return []

# ===== 生成动画并保存 =====
ani = animation.FuncAnimation(
    fig,
    update,
    frames=len(all_frames),
    interval=400,       # 每帧间隔400毫秒
    blit=False
)

print("正在导出 wake_animation.gif，请稍候（约10-20秒）...")
ani.save("wake_animation.gif", writer="pillow", fps=3, dpi=120)
print("✅ 导出完成：wake_animation.gif")
plt.close()