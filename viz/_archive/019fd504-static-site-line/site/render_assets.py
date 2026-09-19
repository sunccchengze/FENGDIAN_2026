#!/usr/bin/env python3
# 渲染 npz 流场 -> PNG，供纯静态站点使用（无 Python 后端）。
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET = os.path.join(ROOT, "site", "assets", "img")
for d in ["fields", "opt", "d3", "array", "pod"]:
    os.makedirs(os.path.join(ASSET, d), exist_ok=True)

def field_png(npz, out, title, cmap="viridis"):
    d = np.load(npz); u = d["u"]; x = d["x"]; y = d["y"]
    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=110)
    im = ax.imshow(u, origin="lower", extent=[x.min(), x.max(), y.min(), y.max()],
                   cmap=cmap, aspect="auto")
    ax.set_title(title, fontsize=11, color="#e8edf5")
    ax.set_xlabel("x (m)", fontsize=8, color="#9fb3d4")
    ax.set_ylabel("y (m)", fontsize=8, color="#9fb3d4")
    ax.tick_params(colors="#9fb3d4", labelsize=7)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="u (m/s)")
    fig.patch.set_facecolor("#0a1020"); ax.set_facecolor("#0a1020")
    plt.tight_layout(); plt.savefig(out, facecolor="#0a1020"); plt.close(fig)

def case_for_yaw(yaw):
    n = int(round((yaw + 30) / 5)) + 1
    return os.path.join(ROOT, "fields", f"case_{n:04d}.npz")

for yaw in [-30, -15, 0, 15, 30]:
    field_png(case_for_yaw(yaw), os.path.join(ASSET, "fields", f"yaw_{yaw:+03d}.png"),
              f"尾流速度场  yaw={yaw}°")
field_png(case_for_yaw(0), os.path.join(ASSET, "opt", "before.png"), "优化前 yaw=0°")
field_png(case_for_yaw(25), os.path.join(ASSET, "opt", "after.png"), "优化后 yaw=25°")

d3 = np.load(os.path.join(ROOT, "fields_3d", "yaw_+00.npz"))
u3 = d3["u"]; xs = d3["x"]; ys = d3["y"]; zs = d3["z"]
X, Y = np.meshgrid(xs, ys)
zz = zs[len(zs)//2]
fig = plt.figure(figsize=(6.4, 4.6), dpi=110); ax = fig.add_subplot(111, projection="3d")
ax.plot_surface(X, Y, u3[list(zs).index(zz)], cmap="viridis", linewidth=0, antialiased=True)
ax.set_title("3D 尾流曲面 (mid-height)", fontsize=11, color="#e8edf5")
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("u")
ax.tick_params(colors="#9fb3d4", labelsize=7)
fig.patch.set_facecolor("#0a1020")
plt.tight_layout(); plt.savefig(os.path.join(ASSET, "d3", "surface.png"), facecolor="#0a1020"); plt.close(fig)

fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.0), dpi=110)
for ax, zi in zip(axes, [0, len(zs)//2, len(zs)-1]):
    ax.imshow(u3[zi], origin="lower", extent=[xs.min(), xs.max(), ys.min(), ys.max()],
              cmap="viridis", aspect="auto")
    ax.set_title(f"z={zs[zi]:.0f} m", fontsize=9, color="#e8edf5")
    ax.set_xticks([]); ax.set_yticks([])
fig.suptitle("3D 体渲染（多高度层切片）", fontsize=11, color="#e8edf5")
fig.patch.set_facecolor("#0a1020")
plt.tight_layout(); plt.savefig(os.path.join(ASSET, "d3", "volume.png"), facecolor="#0a1020"); plt.close(fig)

field_png(os.path.join(ROOT, "fields_array", "baseline.npz"),
          os.path.join(ASSET, "array", "baseline.png"), "3×3 阵列流场（基准）")

pod = np.load(os.path.join(ROOT, "pod_results", "pod_data.npz"))
sv = pod["singular_values"]; ef = pod["energy_frac"]; ec = pod["energy_cum"]
modes = pod["modes"]; xm = pod["x_mean"]; coeff = pod["coefficients"]; yaw = pod["yaw_angles"]
fig, ax = plt.subplots(figsize=(6.0, 3.0), dpi=110)
ax.plot(range(1, len(ec)+1), ec*100, "o-", color="#4a9eff")
ax.axhline(98, color="#27ae60", ls="--", lw=1, label="98%")
ax.set_title("POD 模态累计能量", fontsize=11, color="#e8edf5")
ax.set_xlabel("模态数"); ax.set_ylabel("累计能量 %")
ax.tick_params(colors="#9fb3d4"); ax.legend(fontsize=8, labelcolor="#9fb3d4")
fig.patch.set_facecolor("#0a1020"); ax.set_facecolor("#0a1020")
plt.tight_layout(); plt.savefig(os.path.join(ASSET, "pod", "energy_cum.png"), facecolor="#0a1020"); plt.close(fig)
for k in range(3):
    fig, ax = plt.subplots(figsize=(6.0, 3.0), dpi=110)
    ax.imshow(modes[k], origin="lower", cmap="RdBu_r", aspect="auto")
    ax.set_title(f"POD 模态 {k+1} (能量 {ef[k]*100:.1f}%)", fontsize=10, color="#e8edf5")
    ax.set_xticks([]); ax.set_yticks([])
    fig.patch.set_facecolor("#0a1020")
    plt.tight_layout(); plt.savefig(os.path.join(ASSET, "pod", f"mode_{k}.png"), facecolor="#0a1020"); plt.close(fig)
ci = int(np.argmin(np.abs(yaw))); nm = modes.shape[0]
c = coeff[:, ci] if coeff.shape[0] == nm else coeff[ci, :nm]
c = np.asarray(c)[:nm]
orig = np.load(case_for_yaw(0))["u"]
recon = xm.copy()
for k in range(nm):
    recon += c[k] * modes[k]
fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.0), dpi=110)
for ax, im, t in zip(axes, [orig, recon, orig - recon], ["原始", "POD 重构", "误差"]):
    ax.imshow(im, origin="lower", cmap="viridis", aspect="auto")
    ax.set_title(t, fontsize=9, color="#e8edf5"); ax.set_xticks([]); ax.set_yticks([])
fig.suptitle("POD 流场重构对比（全模态）", fontsize=11, color="#e8edf5")
fig.patch.set_facecolor("#0a1020")
plt.tight_layout(); plt.savefig(os.path.join(ASSET, "pod", "recon.png"), facecolor="#0a1020"); plt.close(fig)
print("render done")
