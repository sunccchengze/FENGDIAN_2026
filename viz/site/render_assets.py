#!/usr/bin/env python3
# 渲染 npz 流场 -> PNG，供纯静态站点使用（无 Python 后端）。
# 浅色莫兰迪主题，与 site/css/style.css 保持一致。
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET = os.path.join(ROOT, "site", "assets", "img")
for d in ["fields", "opt", "d3", "array", "pod"]:
    os.makedirs(os.path.join(ASSET, d), exist_ok=True)

# ---- 莫兰迪风电配色（与 CSS / plotly-theme.js 同步）----
BG      = "#f6f3ec"   # 图表区底
PANEL   = "#fbfaf6"   # 画布底
TXT     = "#3b3f46"
SUB     = "#73787f"
GRID    = "#e2dccf"
BLUE    = "#6b8cae"
BLUE_D  = "#547394"
SAGE    = "#8aa17a"
LAV     = "#8e88a6"
GOLD    = "#c2a86b"

# 中文字体（若系统没有则回退默认）
for fp in ["/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
           "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]:
    if os.path.exists(fp):
        font_manager.fontManager.addfont(fp)
plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 速度场色：暖米 -> 雾蓝
FIELD_CMAP = matplotlib.colors.LinearSegmentedColormap.from_list(
    "morandi_field",
    ["#e8dfd0", "#cfc6b4", "#a9bdcf", "#7d9ebb", "#547394"]
)


def style_ax(ax):
    ax.set_facecolor(BG)
    ax.tick_params(colors=SUB, labelsize=7)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.xaxis.label.set_color(SUB)
    ax.yaxis.label.set_color(SUB)
    ax.title.set_color(TXT)


def field_png(npz, out, title, cmap=FIELD_CMAP):
    d = np.load(npz); u = d["u"]; x = d["x"]; y = d["y"]
    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=110)
    im = ax.imshow(u, origin="lower", extent=[x.min(), x.max(), y.min(), y.max()],
                   cmap=cmap, aspect="auto")
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("x (m)", fontsize=8); ax.set_ylabel("y (m)", fontsize=8)
    style_ax(ax)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("u (m/s)", color=SUB, fontsize=8)
    cb.ax.tick_params(colors=SUB, labelsize=7)
    cb.outline.set_edgecolor(GRID)
    fig.patch.set_facecolor(PANEL)
    plt.tight_layout(); plt.savefig(out, facecolor=PANEL); plt.close(fig)


def case_for_yaw(yaw):
    n = int(round((yaw + 30) / 5)) + 1
    return os.path.join(ROOT, "fields", f"case_{n:04d}.npz")


for yaw in [-30, -15, 0, 15, 30]:
    field_png(case_for_yaw(yaw), os.path.join(ASSET, "fields", f"yaw_{yaw:+03d}.png"),
              f"Wake velocity field  yaw={yaw}°")
field_png(case_for_yaw(0), os.path.join(ASSET, "opt", "before.png"), "Before optimization  yaw=0°")
field_png(case_for_yaw(25), os.path.join(ASSET, "opt", "after.png"), "After optimization  yaw=25°")

# ---- 3D 曲面（静态预览）----
d3 = np.load(os.path.join(ROOT, "fields_3d", "yaw_+00.npz"))
u3 = d3["u"]; xs = d3["x"]; ys = d3["y"]; zs = d3["z"]
X, Y = np.meshgrid(xs, ys)
zz = zs[len(zs)//2]
fig = plt.figure(figsize=(6.4, 4.6), dpi=110); ax = fig.add_subplot(111, projection="3d")
ax.plot_surface(X, Y, u3[list(zs).index(zz)], cmap=FIELD_CMAP, linewidth=0, antialiased=True)
ax.set_title("3D wake surface (mid-height)", fontsize=11)
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("u")
ax.tick_params(colors=SUB, labelsize=7)
fig.patch.set_facecolor(PANEL)
ax.set_facecolor(PANEL)
plt.tight_layout(); plt.savefig(os.path.join(ASSET, "d3", "surface.png"), facecolor=PANEL); plt.close(fig)

fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.0), dpi=110)
for ax, zi in zip(axes, [0, len(zs)//2, len(zs)-1]):
    ax.imshow(u3[zi], origin="lower", extent=[xs.min(), xs.max(), ys.min(), ys.max()],
              cmap=FIELD_CMAP, aspect="auto")
    ax.set_title(f"z={zs[zi]:.0f} m", fontsize=9, color=TXT)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_facecolor(BG)
fig.suptitle("3D volume slices (multiple heights)", fontsize=11, color=TXT)
fig.patch.set_facecolor(PANEL)
plt.tight_layout(); plt.savefig(os.path.join(ASSET, "d3", "volume.png"), facecolor=PANEL); plt.close(fig)

# ---- 3x3 阵列基准 ----
field_png(os.path.join(ROOT, "fields_array", "baseline.npz"),
          os.path.join(ASSET, "array", "baseline.png"), "3x3 array flow field (baseline)")

# ---- POD ----
pod = np.load(os.path.join(ROOT, "pod_results", "pod_data.npz"))
ef = pod["energy_frac"]; ec = pod["energy_cum"]
modes = pod["modes"]; xm = pod["x_mean"]; coeff = pod["coefficients"]; yaw = pod["yaw_angles"]

fig, ax = plt.subplots(figsize=(6.0, 3.0), dpi=110)
ax.plot(range(1, len(ec)+1), ec*100, "o-", color=BLUE, lw=2)
ax.axhline(98, color=SAGE, ls="--", lw=1, label="98%")
ax.set_title("POD cumulative energy", fontsize=11)
ax.set_xlabel("Mode number"); ax.set_ylabel("Cumulative energy %")
ax.legend(fontsize=8, labelcolor=SUB)
style_ax(ax)
fig.patch.set_facecolor(PANEL)
plt.tight_layout(); plt.savefig(os.path.join(ASSET, "pod", "energy_cum.png"), facecolor=PANEL); plt.close(fig)

for k in range(3):
    fig, ax = plt.subplots(figsize=(6.0, 3.0), dpi=110)
    ax.imshow(modes[k], origin="lower", cmap="RdBu_r", aspect="auto")
    ax.set_title(f"POD mode {k+1} (energy {ef[k]*100:.1f}%)", fontsize=10)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_facecolor(BG)
    fig.patch.set_facecolor(PANEL)
    plt.tight_layout(); plt.savefig(os.path.join(ASSET, "pod", f"mode_{k}.png"), facecolor=PANEL); plt.close(fig)

ci = int(np.argmin(np.abs(yaw))); nm = modes.shape[0]
c = coeff[:, ci] if coeff.shape[0] == nm else coeff[ci, :nm]
c = np.asarray(c)[:nm]
orig = np.load(case_for_yaw(0))["u"]
recon = xm.copy()
for k in range(nm):
    recon += c[k] * modes[k]
fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.0), dpi=110)
vmax = max(abs(orig.min()), abs(orig.max()))
for ax, im, t in zip(axes, [orig, recon, orig - recon], ["Original", "POD recon", "Error"]):
    cm = FIELD_CMAP if t != "误差" else "RdBu_r"
    ax.imshow(im, origin="lower", cmap=cm, aspect="auto",
              vmin=-vmax if t == "误差" else None, vmax=vmax if t == "误差" else None)
    ax.set_title(t, fontsize=9, color=TXT); ax.set_xticks([]); ax.set_yticks([])
    ax.set_facecolor(BG)
fig.suptitle("POD reconstruction (all modes)", fontsize=11, color=TXT)
fig.patch.set_facecolor(PANEL)
plt.tight_layout(); plt.savefig(os.path.join(ASSET, "pod", "recon.png"), facecolor=PANEL); plt.close(fig)
print("render done (light morandi theme)")
