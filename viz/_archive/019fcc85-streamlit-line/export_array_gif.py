import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

print("生成双面板对比动画...")

df = pd.read_csv("cases_array.csv")
df = df.sort_values("yaw_upstream").reset_index(drop=True)

D = 126.0
layout_x = [row * 5 * D for row in range(3) for col in range(3)]
layout_y  = [(col - 1) * 3 * D for row in range(3) for col in range(3)]

# ===== 左面板：统一偏航扫描帧 =====
unified_frames = []
for yaw in list(df["yaw_upstream"]) + list(reversed(list(df["yaw_upstream"]))):
    data = np.load(f"fields_array/yaw_{yaw:+03d}.npz")
    row  = df[df["yaw_upstream"] == yaw].iloc[0]
    unified_frames.append({
        "u":     data["u"],
        "yaw":   yaw,
        "power": row["power_total"],
        "gain":  row["gain_pct"],
        "label": f"统一偏航  γ = {yaw:+.0f}°\n"
                 f"总功率 {row['power_total']:.0f} kW  ({row['gain_pct']:+.1f}%)"
    })

# ===== 右面板：逐排优化渐进过程（3步循环）=====
# 步骤1：全0°基准
# 步骤2：第1排+30°，其余0°
# 步骤3：第1排+30°，第2排+20°，第3排0°（完整独立优化）
import json
with open("array_independent_result.json") as f:
    res = json.load(f)

right_data = [
    {
        "npz":   "fields_array/baseline.npz",
        "label": "步骤1：无偏航基准\n"
                 f"总功率 {res['power_none']:.0f} kW  (+0.0%)"
    },
    {
        "npz":   "fields_array/yaw_+30.npz",   # 只有第1排+30°
        "label": f"步骤2：第1排 +30°，其余 0°\n"
                 f"总功率 {res['power_unified']:.0f} kW  "
                 f"(+{res['gain_unified_pct']:.1f}%)"
    },
    {
        "npz":   "fields_array/independent.npz",
        "label": f"步骤3：逐排独立优化\n"
                 f"排1: +30°  排2: +20°  排3: 0°\n"
                 f"总功率 {res['power_independent']:.0f} kW  "
                 f"(+{res['gain_independent_pct']:.1f}%)"
    },
]

# 每个右侧步骤重复几帧，和左侧帧数对齐
total_frames = len(unified_frames)
repeat_each  = total_frames // 3
right_frames = []
for i, rd in enumerate(right_data):
    count = repeat_each if i < 2 else total_frames - repeat_each * 2
    data  = np.load(rd["npz"])
    for _ in range(count):
        right_frames.append({
            "u":     data["u"],
            "label": rd["label"]
        })

x_ref = np.load("fields_array/baseline.npz")["x"]
y_ref = np.load("fields_array/baseline.npz")["y"]
vmin, vmax = 4.0, 9.0

# ===== 建画布：1行2列 =====
fig, (ax_l, ax_r) = plt.subplots(
    1, 2, figsize=(16, 5),
    facecolor="#080d1a"
)
for ax in (ax_l, ax_r):
    ax.set_facecolor("#111827")
    ax.tick_params(colors="#8899bb")
    for spine in ax.spines.values():
        spine.set_edgecolor("#1e2d4a")

# 初始轮廓
contour_l = ax_l.contourf(x_ref, y_ref,
                           unified_frames[0]["u"],
                           levels=50, cmap="RdBu_r",
                           vmin=vmin, vmax=vmax)
contour_r = ax_r.contourf(x_ref, y_ref,
                           right_frames[0]["u"],
                           levels=50, cmap="RdBu_r",
                           vmin=vmin, vmax=vmax)

for ax in (ax_l, ax_r):
    plt.colorbar(
        plt.cm.ScalarMappable(
            cmap="RdBu_r",
            norm=plt.Normalize(vmin=vmin, vmax=vmax)
        ),
        ax=ax, label="风速 (m/s)", fraction=0.025
    ).ax.yaxis.label.set_color("#8899bb")

title_l = ax_l.set_title("", color="#e8edf5", fontsize=11)
title_r = ax_r.set_title("", color="#e8edf5", fontsize=11)

for ax in (ax_l, ax_r):
    ax.set_xlabel("顺风方向 x (m)", color="#8899bb", fontsize=9)
    ax.set_ylabel("横向 y (m)",    color="#8899bb", fontsize=9)

fig.suptitle("统一偏航  vs  逐排独立优化",
             color="#e8edf5", fontsize=13, y=1.02)
plt.tight_layout()

def update(i):
    global contour_l, contour_r

    # 清除
    for c in ax_l.collections: c.remove()
    for c in ax_r.collections: c.remove()

    # 左面板
    lf = unified_frames[i]
    contour_l = ax_l.contourf(x_ref, y_ref, lf["u"],
                               levels=50, cmap="RdBu_r",
                               vmin=vmin, vmax=vmax)
    # 右面板
    rf = right_frames[i]
    contour_r = ax_r.contourf(x_ref, y_ref, rf["u"],
                               levels=50, cmap="RdBu_r",
                               vmin=vmin, vmax=vmax)

    # 重绘风机
    for ax in (ax_l, ax_r):
        for j, (tx, ty) in enumerate(zip(layout_x, layout_y)):
            row_j = j // 3 + 1
            ax.plot(tx, ty, "^",
                    markersize=9 if row_j == 1 else 6,
                    markeredgecolor="white", markeredgewidth=1.5,
                    markerfacecolor="white" if row_j == 1 else "gray",
                    zorder=5)

    title_l.set_text(lf["label"])
    title_r.set_text(rf["label"])
    return []

ani = animation.FuncAnimation(
    fig, update,
    frames=total_frames,
    interval=400, blit=False
)

print("正在导出 array_animation.gif，请稍候...")
ani.save("array_animation.gif", writer="pillow", fps=3, dpi=110)
print("✅ 导出完成：array_animation.gif")
plt.close()