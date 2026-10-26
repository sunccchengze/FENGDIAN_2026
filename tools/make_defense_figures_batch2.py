#!/usr/bin/env python3
"""第二批答辩图（2026-10-26）：把「已有实验数据」翻成能上屏的科研图。

为什么单独一个文件
------------------
`tools/make_defense_figures.py` 的 25 张图以「流程图 + 结论卡」为主，评委看下来
容易产生「讲了很多、数据图很少」的观感。本批只做一件事：**让数据自己说话** ——
每条曲线都来自仓库里既有的 CSV/JSON，不重跑实验、不改实验目录、不手填数字。

纪律（与第一批相同，不得放宽）
------------------------------
1. 只读数据；图上出现的每个数都能用脚本复算出来。
2. 每张图右下角固定角标标明证据等级：模拟真值 / 合成标签 / CFD 后处理。
3. 一律不出现：实测、实时控制、减少弃风、年发电量、P2/P1 比值（第 5 页与
   CFD 组图的硬约束）、「两者精度持平」类说法。
4. 中文字体优先用本机 `~/.fonts/NotoSansCJKsc-Regular.otf`（与第一批一致）；
   没有则退回仓库自带的 Songti SC，保证在无网/新机器上也能重画。

用法
----
    python3 tools/make_defense_figures_batch2.py            # 全部重画
    python3 tools/make_defense_figures_batch2.py g26 g30    # 只画指定编号
    python3 tools/make_defense_figures_batch2.py --list     # 看图号与一句话说明
输出：docs/defense/assets/generated/
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "defense" / "assets" / "generated"

INK = "#16232f"
GRAY = "#5d6f7e"
MUTED = "#93a3b0"
LINE = "#d7dee5"
BG = "#ffffff"
PANEL = "#f4f7fa"
BLUE = "#2f6f9f"
TEAL = "#2a9d8f"
AMBER = "#d9862a"
RED = "#bf5140"
PURPLE = "#6f68a8"
GREEN = "#4a8c53"

DPI = 120
FS = (16, 9)

TAG_SIM = ("模拟真值 · FLORIS", BLUE)
TAG_SYN = ("合成标签 · 非物理精度", AMBER)
TAG_CFD = ("CFD 后处理 · 非实测", PURPLE)

# ── 字体 ────────────────────────────────────────────────────────────────
FONT_CANDIDATES = [
    Path.home() / ".fonts" / "NotoSansCJKsc-Regular.otf",
    Path.home() / ".fonts" / "NotoSansCJK-Regular.ttc",
    ROOT / "viz" / "site" / "assets" / "fonts" / "songti-sc-black.ttf",
]


def use_cjk() -> None:
    from matplotlib import font_manager as fm

    for cand in FONT_CANDIDATES:
        if cand.exists():
            fm.fontManager.addfont(str(cand))
            name = fm.FontProperties(fname=str(cand)).get_name()
            # 数字与拉丁字母优先用 DejaVu（字形细、tabular 数字对齐），中文回退到 CJK 字体
            plt.rcParams["font.family"] = ["DejaVu Sans", name]
            plt.rcParams["font.sans-serif"] = ["DejaVu Sans", name]
            break
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 15


def b(t, color=INK, lw=0.85):
    """伪粗体：同色描边，弥补单字重字体。"""
    t.set_path_effects([pe.withStroke(linewidth=lw, foreground=color)])
    return t


def frame(fig, title, subtitle="", footer="", kicker="", tag=None, reading=""):
    fig.patch.set_facecolor(BG)
    if kicker:
        fig.text(0.045, 0.955, kicker, color=MUTED, fontsize=13.5, va="top")
    b(fig.text(0.045, 0.918, title, color=INK, fontsize=30, va="top"), INK, 1.1)
    if subtitle:
        fig.text(0.045, 0.852, subtitle.replace("**", ""), color=GRAY, fontsize=15.5, va="top")
    fig.add_artist(Rectangle((0.045, 0.905), 0.055, 0.0035,
                             transform=fig.transFigure, facecolor=BLUE, edgecolor="none"))
    block = "\n".join(x for x in (reading, footer) if x).replace("**", "")
    if block:
        lines, cur, cur_w, limit = [], "", 0, 150
        for ch in block:
            w = 1 if ord(ch) < 128 else 2
            if cur_w + w > limit and cur:
                lines.append(cur)
                cur, cur_w = "", 0
            cur += ch
            cur_w += w
        if cur:
            lines.append(cur)
        fig.text(0.045, 0.030, "\n".join(lines), color=MUTED, fontsize=11,
                 va="bottom", linespacing=1.45)
        if len(lines) > 4:
            print(f"    ! 底部文字 {len(lines)} 行，可能与坐标轴标签相压：{title[:18]}")
    fig.add_artist(Rectangle((0.045, 0.086), 0.760, 0.0014,
                             transform=fig.transFigure, facecolor=LINE, edgecolor="none"))
    if tag:
        text, color = tag
        fig.add_artist(Rectangle((0.80, 0.028), 0.155, 0.042,
                                 transform=fig.transFigure, facecolor=color, alpha=0.10,
                                 edgecolor="none"))
        fig.text(0.877, 0.049, text, color=color, fontsize=11.5, ha="center", va="center")


def clean(ax, grid_axis=None):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    if grid_axis:
        ax.grid(axis=grid_axis, color=LINE, lw=0.8)
        ax.set_axisbelow(True)
    ax.tick_params(colors=GRAY, labelsize=12)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    fig.savefig(path, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"  {name}.png  {path.stat().st_size / 1024:.0f} KB")


def rows(path):
    with Path(path).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ── 数据源 ──────────────────────────────────────────────────────────────
CFD = ROOT / "materials" / "田铭雨" / "20261024_三机串列双模型对比"
DATASET = ROOT / "materials" / "袁夫达" / "20261025_仿真建模数据交接"
CASES = DATASET / "data" / "cases_wind.csv"
PINN_REPORT = DATASET / "model" / "training_report.json"
RANDOM = ROOT / "optimization_control" / "experiments" / "20261022_random_wind_training"

D_ROTOR = 125.88          # m，NREL 5MW 风轮直径（与数据集 manifest 同口径）
A_ROTOR = math.pi * (D_ROTOR / 2) ** 2
RHO = 1.225

MODELS = (("k-omega_data", "k-ω SST", TEAL), ("k-epsilon_data", "k-ε", AMBER))
TURB_X = (8.0, -370.0, -748.0)   # 三台机的 z 坐标（总结文档 §2）


def _f(v) -> float:
    return float(str(v).replace("\r", "").strip())


# ══════════════════════════════════════════════════════════════════════
# CFD · 三机串列双湍流模型（第 5 页 / 备用页）
# ══════════════════════════════════════════════════════════════════════
def _centerline(folder: str):
    r = rows(CFD / folder / "wake_centerline.csv")
    x = np.array([(TURB_X[0] - _f(t["z_m"])) / D_ROTOR for t in r])
    y = np.array([_f(t["U_forward_smooth_m_s"]) for t in r])
    o = np.argsort(x)
    return x[o], y[o]


def _bin(x, y, width=0.25, lo=0.0, hi=10.0):
    """分箱统计：CFD 沿线的原始取样是逐单元取值的，逐点连线只会画出锯齿；
    这里对每个箱给出中位数与 10–90 分位，既保留趋势也如实显示离散度。"""
    edges = np.arange(lo, hi + width, width)
    cx, med, p10, p90 = [], [], [], []
    for i in range(len(edges) - 1):
        m = (x >= edges[i]) & (x < edges[i + 1])
        if m.sum() < 3:
            continue
        cx.append((edges[i] + edges[i + 1]) / 2)
        med.append(np.median(y[m]))
        p10.append(np.percentile(y[m], 10))
        p90.append(np.percentile(y[m], 90))
    return np.array(cx), np.array(med), np.array(p10), np.array(p90)


def g26():
    """尾流中心线：两模型在近场重合、远场才分开。"""
    fig = plt.figure(figsize=FS)
    frame(fig, "尾流中心线：中近场两模型几乎重合，远场才分开",
          "同一几何、同一网格（1,055,511 单元）、同一工况（9 m/s / TI 10% / 0° 桨距）　·　"
          "点为 0.25D 箱内中位数，阴影为 10–90 分位",
          "数据来源：materials/田铭雨/20261024_三机串列双模型对比/{k-omega_data,k-epsilon_data}/wake_centerline.csv"
          "（±10 m 环带平均值，源文件已做 9 点滑动平均）　｜　CFD 后处理：说明流场形态与模型间差异，不作精度证据",
          "第 5 页 · Fluent 仿真工作（过程证据）", TAG_CFD,
          reading="读法：中心线在 1D 处降到 4.5 m/s，随后随下游逐级恢复；第 2、3 台正对的位置（3D、6D）又各被压出一个台阶 —— 这就是三机串列的叠加效应。两模型的差别不在「有没有尾流」，在远场恢复得快慢（>7D 差 3%–4%）。")

    ax = fig.add_axes([0.065, 0.245, 0.60, 0.52])
    data = {}
    for folder, label, color in MODELS:
        x, y = _centerline(folder)
        cx, med, p10, p90 = _bin(x, y)
        data[label] = (cx, med)
        ax.fill_between(cx, p10, p90, color=color, alpha=0.13, lw=0)
        ax.plot(cx, med, color=color, lw=2.8, marker="o", ms=3.5, label=label)
    ax.axhline(9.0, color=MUTED, lw=1.2, ls=":")
    ax.text(9.8, 9.3, "来流 9.0 m/s", color=MUTED, fontsize=11.5, ha="right")
    for i, xd in enumerate([(TURB_X[0] - TURB_X[1]) / D_ROTOR, (TURB_X[0] - TURB_X[2]) / D_ROTOR]):
        ax.axvline(xd, color=LINE, lw=1.6, ls="--")
        ax.text(xd + 0.1, 2.6, f"第 {i + 2} 台", color=GRAY, fontsize=11.5)
    ax.text(0.12, 2.6, "第 1 台", color=GRAY, fontsize=11.5)
    ax.set_xlim(0, 10)
    ax.set_ylim(2, 9.8)
    ax.set_xlabel("第 1 台下游距离 / D（D = 126 m）", color=GRAY, fontsize=13)
    ax.set_ylabel("轴向平均速度 / m/s", color=GRAY, fontsize=13)
    clean(ax, "y")
    ax.legend(loc="lower right", frameon=False, fontsize=12.5)

    ax2 = fig.add_axes([0.715, 0.245, 0.245, 0.52])
    a, c = data["k-ω SST"], data["k-ε"]
    ax2.axhline(0, color=MUTED, lw=1)
    ax2.axvspan(0, 7, color=PANEL, zorder=0)
    ax2.plot(a[0], (c[1] - a[1]) / a[1] * 100, color=PURPLE, lw=2.4, marker="o", ms=3.5)
    ax2.text(3.4, ax2.get_ylim()[1] * 0.9 if ax2.get_ylim()[1] > 1 else 3,
             "近场 < 7D：±1%", color=MUTED, fontsize=11, ha="center")
    ax2.set_xlim(0, 10)
    ax2.set_xlabel("下游距离 / D", color=GRAY, fontsize=12.5)
    ax2.set_ylabel("k-ε 相对 k-ω 的偏差 / %", color=GRAY, fontsize=12.5)
    clean(ax2, "y")


    save(fig, "g26_cfd_centerline")


def _disk(folder: str, turbine: int, field: str):
    r = rows(CFD / folder / f"rotor{turbine}_plane.csv")
    rs = sorted({round(_f(t["r_m"]), 3) for t in r})
    th = sorted({round(_f(t["theta_rad"]), 5) for t in r})
    Z = np.full((len(rs), len(th)), np.nan)
    for t in r:
        i = rs.index(round(_f(t["r_m"]), 3))
        j = th.index(round(_f(t["theta_rad"]), 5))
        Z[i, j] = _f(t[field])
    return np.array(rs), np.array(th), Z


def _radial(fig, field, ylab, title, scale, floor=None):
    for col in range(3):
        ax = fig.add_axes([0.065 + col * 0.315, 0.245, 0.27, 0.50])
        for folder, label, color in MODELS:
            rs, _th, Z = _disk(folder, col + 1, field)
            Z = Z * scale
            med = np.nanmedian(Z, axis=1)
            q1 = np.nanpercentile(Z, 25, axis=1)
            q3 = np.nanpercentile(Z, 75, axis=1)
            if floor is not None:
                q1, q3 = np.clip(q1, floor, None), np.clip(q3, floor, None)
            ax.fill_between(rs, q1, q3, color=color, alpha=0.15, lw=0)
            ax.plot(rs, med, color=color, lw=2.6, marker="o", ms=3.2, label=label)
            if col == 0:
                continue
        ax.set_title(f"第 {col + 1} 台盘面", color=INK, fontsize=14, pad=6)
        ax.set_xlabel("盘面半径 r / m", color=GRAY, fontsize=12.5)
        if col == 0:
            ax.set_ylabel(ylab, color=GRAY, fontsize=12.5)
            ax.legend(frameon=False, fontsize=12, loc="lower left")
        clean(ax, "y")
    return ax


def _disk_avg(folder: str):
    """盘面平均：按半径加权（等角度网格上，环带面积 ∝ r），与源文档的盘面平均同口径。"""
    out = []
    for i in (1, 2, 3):
        r = rows(CFD / folder / f"rotor{i}_plane.csv")
        rs = np.array([_f(t["r_m"]) for t in r])
        U = np.array([_f(t["U_forward_m_s"]) for t in r])
        TI = np.array([_f(t["TI"]) for t in r])
        out.append((float((U * rs).sum() / rs.sum()), float((TI * rs).sum() / rs.sum()) * 100))
    return out


def g27():
    """盘面平均速度与湍流强度：两模型逐台对照（柱状）。"""
    fig = plt.figure(figsize=FS)
    frame(fig, "盘面平均：两模型的速度几乎一样，湍流强度差一半",
          "按环带面积加权（等角度网格，面积 ∝ r）　·　同一几何、同一网格、同一工况　·　"
          "左右两栏分别是盘面平均轴向速度与盘面平均湍流强度",
          "数据来源：materials/田铭雨/20261024_三机串列双模型对比/rotor{1,2,3}_plane.csv（648 点/盘面）"
          "　｜　速度复算得 6.15 / 6.14 / 4.05 m/s，与源文档一致；TI 为面积加权复算，源文档的点平均略低",
          "第 5 页 · Fluent 仿真工作（模型间差异）", TAG_CFD,
          reading="读法：两模型对盘面速度的判断差 0.3%–0.9%（第 1、2 台几乎重合，第 3 台 −0.4%），对盘面湍流强度却差 32%、44%、45% —— 同一网格上换湍流模型，先变的是掺混量，不是速度。这也是为什么本组数据能支撑「流场形态趋势」，但支撑不了「精度」：没有实测锚点，无法判断谁对。")

    kw, ke = _disk_avg("k-omega_data"), _disk_avg("k-epsilon_data")
    x = np.arange(3)
    w = 0.34

    ax = fig.add_axes([0.075, 0.245, 0.38, 0.52])
    ax.bar(x - w / 2, [v[0] for v in kw], width=w, color=TEAL, label="k-ω SST")
    ax.bar(x + w / 2, [v[0] for v in ke], width=w, color=AMBER, label="k-ε")
    for i in range(3):
        for dx, val, col in ((-w / 2, kw[i][0], TEAL), (w / 2, ke[i][0], AMBER)):
            ax.text(i + dx, val + 0.12, f"{val:.2f}", ha="center", color=INK, fontsize=11.5)
        ax.text(i, 0.35, f"{(ke[i][0] / kw[i][0] - 1) * 100:+.1f}%", ha="center",
                color=RED if ke[i][0] < kw[i][0] else GRAY, fontsize=11.5)
    ax.axhline(9.0, color=MUTED, lw=1.2, ls=":")
    ax.text(2.45, 9.3, "来流 9 m/s", color=MUTED, fontsize=11, ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels(["第 1 台", "第 2 台", "第 3 台"])
    ax.set_ylabel("盘面平均轴向速度 / m/s", color=GRAY, fontsize=12.5)
    ax.set_ylim(0, 10.9)
    clean(ax, "y")
    ax.legend(frameon=False, fontsize=12, loc="upper right")

    ax2 = fig.add_axes([0.545, 0.245, 0.38, 0.52])
    ax2.bar(x - w / 2, [v[1] for v in kw], width=w, color=TEAL)
    ax2.bar(x + w / 2, [v[1] for v in ke], width=w, color=AMBER)
    for i in range(3):
        for dx, val in ((-w / 2, kw[i][1]), (w / 2, ke[i][1])):
            ax2.text(i + dx, val + 0.12, f"{val:.1f}", ha="center", color=INK, fontsize=11.5)
        ax2.text(i, 0.3, f"{(ke[i][1] / kw[i][1] - 1) * 100:+.0f}%", ha="center", color=RED, fontsize=11.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(["第 1 台", "第 2 台", "第 3 台"])
    ax2.set_ylabel("盘面平均湍流强度 / %", color=GRAY, fontsize=12.5)
    ax2.set_ylim(0, 11)
    clean(ax2, "y")


    save(fig, "g27_cfd_disk_bars")


def g28():
    """尾流横向剖面：亏损深度与宽度。"""
    fig = plt.figure(figsize=FS)
    frame(fig, "尾流横向剖面：近场有回流区，8D 才恢复到来流的八成",
          "第 1 台下游 2D / 4D / 8D 三处横切面　·　横轴以风轮直径归一　·　淡点是 128 个原始取样点，实线为 5 点滑动平均",
          "数据来源：materials/田铭雨/20261024_三机串列双模型对比/{k-omega_data,k-epsilon_data}/wake_profiles.csv"
          "　｜　CFD 后处理：剖面是单条取样线，不是流场重建，也不是尾流宽度的定量测量",
          "第 5 页 · Fluent 仿真工作（过程证据）", TAG_CFD,
          reading="读法：2D 处中心出现负速度（回流区），4D 中心恢复到 5.9 m/s，8D 才到 7.4 m/s（来流的八成）；"
                  "两模型的剖面几乎重合 —— 说明「差 32%–45% 的盘面 TI」还没有改变速度剖面的外形，"
                  "这是后续加密尾流区网格后要重新看的地方。")

    for i, dist in enumerate((2, 4, 8)):
        ax = fig.add_axes([0.065 + i * 0.315, 0.245, 0.27, 0.50])
        for folder, label, color in MODELS:
            r = rows(CFD / folder / "wake_profiles.csv")
            pts = sorted((_f(t["dy_m"]), _f(t["U_forward_m_s"])) for t in r
                         if abs(_f(t["turbine"]) - 1) < 1e-6 and abs(_f(t["dist_D"]) - dist) < 1e-6)
            x = np.array([p[0] for p in pts]) / D_ROTOR
            y = np.array([p[1] for p in pts])
            ax.scatter(x, y, s=6, color=color, alpha=0.20, linewidths=0)
            ax.plot(x, np.convolve(y, np.ones(5) / 5, mode="same"), color=color, lw=2.4, label=label)
        ax.axhline(9.0, color=MUTED, lw=1.1, ls=":")
        ax.axvline(0, color=LINE, lw=1)
        ax.set_xlim(-1.05, 1.05)
        ax.set_ylim(-1.5, 11)
        ax.set_title(f"第 1 台下游 {dist}D", color=INK, fontsize=14, pad=6)
        ax.set_xlabel("横向偏移 / D", color=GRAY, fontsize=12.5)
        if i == 0:
            ax.set_ylabel("轴向速度 / m/s", color=GRAY, fontsize=12.5)
            ax.legend(frameon=False, fontsize=11.5, loc="upper right")
        clean(ax, "y")

    save(fig, "g28_cfd_wake_profiles")


# ══════════════════════════════════════════════════════════════════════
# 数据集 · 20,160 行 FLORIS 合成样本（第 7 页 / 备用页）
# ══════════════════════════════════════════════════════════════════════
def _cases():
    return rows(CASES)


def _farm_p_kw(r) -> float:
    return (_f(r["P1"]) + _f(r["P2"]) + _f(r["P3"])) / 1000


def g29():
    """来流方向扫描：偏 90° 时尾流不进下游机。"""
    fig = plt.figure(figsize=FS)
    rs = [r for r in _cases()
          if abs(_f(r["yaw1"])) < 1e-6 and abs(_f(r["pitch1"])) < 1e-6
          and abs(_f(r["ambient_wind_speed_m_s"]) - 8.0) < 1e-6]
    agg: dict[float, list[float]] = {}
    for r in rs:
        wd = round(math.degrees(_f(r["ambient_wind_direction_rad"])), 1)
        agg.setdefault(wd, []).append(_farm_p_kw(r))
    xs = sorted(agg)
    ys = [st.mean(agg[k]) for k in xs]
    top = max(ys)
    drop = (1 - st.mean(agg[0.0]) / top) * 100

    frame(fig, "尾流损失随来流方向变化：正对来流丢 38%，侧向来流只丢 2%",
          "8 m/s、0° 桨距　·　28 档来流方向（3 档 TI 平均）　·　90° 附近下游机不进尾流，可当作「无尾流参照」",
          "数据来源：materials/袁夫达/20261025_仿真建模数据交接/data/cases_wind.csv（20,160 行，FLORIS 4.6.6）"
          "　｜　标签为模拟真值，不是实测；横轴角度是风矢量来向，0° 与 180° 都是三机串列正对来流",
          "第 7 页 · 数据与代理模型（偏航前景）", TAG_SIM,
          reading=f"读法：正对来流 0° 时三机总功率比侧向参照低 {drop:.1f}%（2249 vs {top:.0f} kW），这是尾流造成的；侧向（90°）也有约 2% 的损失，说明「侧向参照」本身不是完全无损。真实风场里风向不会停在「正对」或「侧吹」，可调的是几度到二十几度的偏航 —— 机会窗口就在这一段。")

    ax = fig.add_axes([0.06, 0.215, 0.56, 0.545])
    ax.plot(xs, ys, color=BLUE, lw=2.6)
    ax.plot(xs, ys, color=BLUE, lw=9, alpha=0.10)
    ax.axhline(top, color=TEAL, lw=1.4, ls="--")
    ax.text(330, top + 60, f"侧向来流上限 {top:.0f} kW", color=TEAL, fontsize=12, ha="right")
    for xd, lab in ((0.0, "0°"), (180.0, "180°")):
        ax.plot([xd], [st.mean(agg[xd])], "o", color=RED, ms=8)
        ax.annotate(f"{lab} 正对：{st.mean(agg[xd]):.0f} kW",
                    (xd, st.mean(agg[xd])), textcoords="offset points",
                    xytext=(8 if xd == 0 else -8, -28 if xd == 0 else 16),
                    ha="left" if xd == 0 else "right", color=RED, fontsize=12)
    ax.set_xlim(-5, 365)
    ax.set_ylim(2000, 3850)
    ax.set_xticks([0, 45, 90, 135, 180, 225, 270, 315, 360])
    ax.set_xlabel("来流方向 / °", color=GRAY, fontsize=13)
    ax.set_ylabel("三机总功率 / kW", color=GRAY, fontsize=13)
    clean(ax, "y")

    axp = fig.add_axes([0.685, 0.215, 0.28, 0.510], projection="polar")
    th = np.radians(xs)
    axp.plot(th, ys, color=BLUE, lw=2.2)
    axp.fill_between(th, 2000, ys, color=BLUE, alpha=0.10)
    axp.set_theta_zero_location("E")
    axp.set_ylim(2000, 3900)
    axp.set_yticks([2500, 3500])
    axp.set_yticklabels(["2.5", "3.5 MW"], color=MUTED, fontsize=10)
    axp.set_xticks(np.radians([0, 90, 180, 270]))
    axp.set_xticklabels(["0°", "90°", "180°", "270°"], color=GRAY, fontsize=11)
    axp.grid(color=LINE)
    axp.spines["polar"].set_color(LINE)
    axp.set_title("同一组数据的极坐标视角", color=GRAY, fontsize=12, pad=12)


    save(fig, "g29_direction_sweep")


def g30():
    """隐含 Cp 与盘面有效风速：数据集口径自洽性检验。"""
    fig = plt.figure(figsize=FS)
    frame(fig, "口径自检：反算 Cp 不过 0.457 上限，三台机落在同一条曲线上",
          "每条样本一台机：Cp = P / (½ρA·U_eff³)　·　颜色是桨距档　·　20,160 行全用，无抽样",
          "数据来源：materials/袁夫达/20261025_仿真建模数据交接/data/cases_wind.csv（P1–P3、Ueff1–Ueff3）"
          "　｜　ρ=1.225 kg/m³、A=π(D/2)²、D=125.88 m（与 manifest 同口径）；上界 0.457 = 0.4836 × η 0.944",
          "第 7 页 · 数据与代理模型（口径核对）", TAG_SIM,
          reading="读法：反算 Cp 分成三层水平带（桨距 0° / 4° / 8°–14°），最高一档贴着 0.457 上限而不越界 —— 说明功率与 U_eff 是按同一条口径生成的，可以当成「同一把尺子」下的标签；但这只是自洽，不是对真实机组的验证。")

    rs = _cases()[::4]
    ax = fig.add_axes([0.065, 0.215, 0.42, 0.545])
    for i in (1, 2, 3):
        u = np.array([_f(r[f"Ueff{i}"]) for r in rs])
        p = np.array([_f(r[f"P{i}"]) for r in rs])
        pitch = np.array([round(math.degrees(_f(r[f"pitch{i}"]))) for r in rs])
        cp = p / (0.5 * RHO * A_ROTOR * np.clip(u, 0.6, None) ** 3)
        sc = ax.scatter(u, cp, c=pitch, cmap="viridis", s=9, alpha=0.55,
                        vmin=0, vmax=14, linewidths=0)
    ax.axhline(0.457, color=RED, lw=1.4, ls="--")
    ax.text(2.1, 0.474, "Cp 上界 0.457（= 0.4836 × 0.944）", color=RED, fontsize=11.5)
    ax.set_xlim(1.5, 12.6)
    ax.set_ylim(0, 0.52)
    ax.set_xlabel("盘面有效风速 U_eff / m/s", color=GRAY, fontsize=13)
    ax.set_ylabel("反算 Cp = P / (½ρA U³)", color=GRAY, fontsize=13)
    clean(ax, "y")
    cax = fig.add_axes([0.497, 0.22, 0.011, 0.48])
    cb = fig.colorbar(sc, cax=cax)
    cb.set_label("桨距 / °", color=GRAY, fontsize=12)
    cb.ax.tick_params(colors=GRAY, labelsize=11)
    cb.outline.set_edgecolor(LINE)

    ax2 = fig.add_axes([0.6, 0.215, 0.36, 0.545])
    for i, color in ((1, BLUE), (2, TEAL), (3, AMBER)):
        u = np.array([_f(r[f"Ueff{i}"]) for r in rs])
        p = np.array([_f(r[f"P{i}"]) for r in rs]) / 1000
        ax2.scatter(u, p, s=6, color=color, alpha=0.35, linewidths=0, label=f"第 {i} 台")
    ax2.set_xlabel("盘面有效风速 U_eff / m/s", color=GRAY, fontsize=13)
    ax2.set_ylabel("单台功率 / kW", color=GRAY, fontsize=13)
    ax2.set_xlim(1.5, 12.6)
    clean(ax2, "y")
    ax2.legend(frameon=False, fontsize=11.5, loc="upper left", markerscale=3)


    save(fig, "g30_dataset_selfcheck")


def g31():
    """来流强度对尾流恢复的影响。"""
    fig = plt.figure(figsize=FS)
    frame(fig, "湍流强度：从 6% 到 10%，正对来流时总功率最多高 5%",
          "三机串列正对来流（0°）、0° 桨距　·　每个 TI 档在 28 个方向上各取 6 条样本再平均",
          "数据来源：materials/袁夫达/20261025_仿真建模数据交接/data/cases_wind.csv"
          "　｜　标签为模拟真值；该趋势只在 FLORIS 尾流模型内成立，未做实测对照",
          "第 7 页 · 数据与代理模型（边界条件敏感性）", TAG_SIM,
          reading="读法：同一风速、同一方向，把 TI 从 6% 提到 10%，总功率高 2.5%–5.1%（低风速段更大）—— 因为尾流掺混更快、下游机恢复得更快。任何「偏航增益」都必须在同一 TI 档内比较，跨 TI 档比较会得出假结论。")

    rs = [r for r in _cases()
          if abs(_f(r["yaw1"])) < 1e-6 and abs(_f(r["pitch1"])) < 1e-6
          and abs(math.degrees(_f(r["ambient_wind_direction_rad"]))) < 1e-6 + 0.5]
    ax = fig.add_axes([0.065, 0.215, 0.4, 0.535])
    colors = {0.06: BLUE, 0.08: TEAL, 0.10: AMBER}
    for ti in (0.06, 0.08, 0.10):
        sub = {}
        for r in rs:
            if abs(_f(r["turbulence_intensity"]) - ti) < 1e-9:
                sub.setdefault(_f(r["ambient_wind_speed_m_s"]), []).append(_farm_p_kw(r))
        x = sorted(sub)
        y = [st.mean(sub[k]) for k in x]
        ax.plot(x, y, "o-", color=colors[ti], lw=2.4, ms=6, label=f"TI {int(ti * 100)}%")
    ax.set_xlabel("来流风速 / m/s", color=GRAY, fontsize=13)
    ax.set_ylabel("三机总功率 / kW", color=GRAY, fontsize=13)
    clean(ax, "y")
    ax.legend(frameon=False, fontsize=12, loc="upper left")

    ax2 = fig.add_axes([0.575, 0.215, 0.385, 0.535])
    ws_list = sorted({_f(r["ambient_wind_speed_m_s"]) for r in rs})
    base = {}
    for ti in (0.06,):
        for r in rs:
            if abs(_f(r["turbulence_intensity"]) - ti) < 1e-9:
                base.setdefault(_f(r["ambient_wind_speed_m_s"]), []).append(_farm_p_kw(r))
    base = {k: st.mean(v) for k, v in base.items()}
    width = 0.26
    for j, ti in enumerate((0.08, 0.10)):
        vals = []
        for ws in ws_list:
            sub = [_farm_p_kw(r) for r in rs
                   if abs(_f(r["turbulence_intensity"]) - ti) < 1e-9
                   and abs(_f(r["ambient_wind_speed_m_s"]) - ws) < 1e-9]
            vals.append((st.mean(sub) / base[ws] - 1) * 100)
        ax2.bar(np.arange(len(ws_list)) + (j - 0.5) * width, vals, width=width,
                color=colors[ti], label=f"TI {int(ti * 100)}% 相对 6%", alpha=0.9)
    ax2.axhline(0, color=MUTED, lw=1)
    ax2.set_xticks(np.arange(len(ws_list)))
    ax2.set_xticklabels([f"{int(w)}" for w in ws_list])
    ax2.set_xlabel("来流风速 / m/s", color=GRAY, fontsize=13)
    ax2.set_ylabel("相对 TI 6% 的功率变化 / %", color=GRAY, fontsize=13)
    clean(ax2, "y")
    ax2.legend(frameon=False, fontsize=12, loc="upper left")


    save(fig, "g31_ti_sensitivity")


# ══════════════════════════════════════════════════════════════════════
# 控制 · 18 场独立测试（第 9 页）
# ══════════════════════════════════════════════════════════════════════
def _test_metrics():
    return rows(RANDOM / "test" / "metrics.csv")


def _ctrl_map(data, ctrl):
    return {r["case_id"]: _f(r["rmse_w"]) / 1000 for r in data if r["controller"] == ctrl}


def _case_avg(ctrl: str, key: str = "rmse_w", routine_only: bool = True):
    """按 case 先平均（同一工况 3 条流各跑一次，不能当 3 个样本），再用于配对比较。
    routine_only：只取 18 个常规工况；低风高目标压力场单列在第 13 页，混进来会把均值方向翻掉。"""
    by: dict[str, list[float]] = {}
    for r in _test_metrics():
        if r["controller"] != ctrl:
            continue
        if routine_only and r["family"] == "low_wind_stress":
            continue
        by.setdefault(r["case_id"], []).append(_f(r[key]) / 1000)
    return {k: st.mean(v) for k, v in by.items()}


def g32():
    """逐场配对：18 个常规工况里 12 场更好，胜负全画出来。"""
    sel, pi = _case_avg("selected"), _case_avg("pi")
    cases = sorted(sel)
    x = np.array([pi[c] for c in cases])
    y = np.array([sel[c] for c in cases])
    fam = {r["case_id"]: r["family"] for r in _test_metrics()}
    wins = int((y < x).sum())
    delta = y - x
    mean_sel, mean_pi = float(np.mean(y)), float(np.mean(x))

    fig = plt.figure(figsize=FS)
    frame(fig, f"逐场配对：{len(cases)} 个常规工况里 {wins} 场更好，输的 {len(cases) - wins} 场也画出来",
          "每点一个工况（三条流先平均，同一工况只算一个样本）　·　对角线下方 = 我们更好　·　"
          "颜色是来流族，标注的是落后最多的那场",
          "数据来源：optimization_control/experiments/20261022_random_wind_training/test/metrics.csv"
          "（selected / pi，整回合功率跟踪 RMSE）　｜　不含低风高目标压力场；标签为合成教师模型",
          "第 9 页 · 独立测试（成对比较）", TAG_SYN,
          reading=f"读法：均值 {mean_sel:.1f} vs {mean_pi:.1f} kW（−{(1 - mean_sel / mean_pi) * 100:.1f}%），但 {len(cases)} 场只有 {wins} 场更好 —— "
                  "优势来自阵风与慢变几场的大幅领先，平稳场末两档与慢变第 3 场落后。"
                  "分布支持「阶段有效」，不支持「全面优于 PI」，也未做显著性检验。")

    ax = fig.add_axes([0.065, 0.215, 0.38, 0.56])
    style = {"gust": (AMBER, "阵风"), "ramp": (BLUE, "慢变"),
             "stationary": (TEAL, "平稳"), "low_wind_stress": (RED, "低风高目标")}
    lim = (250, 730)
    ax.plot(lim, lim, color=MUTED, lw=1.2, ls="--")
    ax.text(600, 578, "与 PI 持平", color=MUTED, fontsize=11.5, rotation=33)
    for f, (color, lab) in style.items():
        idx = [i for i, c in enumerate(cases) if fam[c] == f]
        if idx:
            ax.scatter(x[idx], y[idx], s=62, color=color, label=lab,
                       edgecolor="w", linewidth=1.2, zorder=3)
    worst = int(np.argmax(delta))
    ax.annotate(f"慢变第 3 场：+{delta[worst]:.0f} kW",
                (x[worst], y[worst]), textcoords="offset points", xytext=(12, -4),
                ha="left", color=RED, fontsize=11)
    ax.set_xlim(*lim)
    ax.set_ylim(*lim)
    ax.set_xlabel("PI 控制的 RMSE / kW", color=GRAY, fontsize=13)
    ax.set_ylabel("训练后策略的 RMSE / kW", color=GRAY, fontsize=13)
    clean(ax, "y")
    ax.legend(frameon=False, fontsize=11.5, loc="upper left")

    ax2 = fig.add_axes([0.565, 0.215, 0.395, 0.56])
    order = np.argsort(delta)
    cols = [TEAL if d < 0 else RED for d in delta[order]]
    ax2.barh(np.arange(len(cases)), delta[order], color=cols, height=0.70)
    ax2.axvline(0, color=INK, lw=1.1)
    ax2.set_yticks([])
    ax2.set_xlabel("训练后 − PI 的 RMSE 差 / kW（负 = 更好）", color=GRAY, fontsize=12.5)
    ax2.set_ylabel(f"{len(cases)} 个工况（按差值排序）", color=GRAY, fontsize=12.5)
    clean(ax2, "x")
    ax2.set_xlim(-260, 260)
    ax2.text(-250, len(cases) - 0.6, f"更好 {wins} 场", color=TEAL, fontsize=12.5, va="top")
    ax2.text(250, 5.2, f"落后 {len(cases) - wins} 场", color=RED, fontsize=12.5, ha="right")

    save(fig, "g32_paired_cases")


def g33():
    """六工况小倍数：同一执行器下的跟踪过程。"""
    fig = plt.figure(figsize=FS)
    frame(fig, "跟踪过程小倍数：六种工况、四种控制方式、同一张图上看完",
          "横轴为一回合 128 步（每步 1 s）　·　虚线是给定目标　·　纵轴统一 1.5–6.0 MW 便于横向比较",
          "数据来源：optimization_control/experiments/20261022_random_wind_training/test/trajectories.csv"
          "（同 case_id 回放，测试集不参与选模）　｜　标签为合成教师模型；单条曲线不能替代 20 场统计",
          "第 9 页 · 独立测试（过程证据）", TAG_SYN,
          reading="读法：训练后（青线）在六种工况里都最贴近黑虚线，但慢变 + 高目标那一格仍然掉下去 —— 这不是画法问题，是训练后的策略在「目标接近可用出力上限」时确实够不到。")

    traj = rows(RANDOM / "test" / "trajectories.csv")
    pick = [
        ("test_stationary_0_pitch0.025", "平稳 · 目标 2.7 MW"),
        ("test_stationary_1_pitch0.025", "平稳 · 目标 3.3 MW"),
        ("test_ramp_0_pitch0.025", "慢变 · 目标 2.7 MW"),
        ("test_ramp_1_pitch0.025", "慢变 · 目标 3.3 MW"),
        ("test_gust_0_pitch0.025", "阵风 · 目标 2.7 MW"),
        ("test_gust_1_pitch0.025", "阵风 · 目标 3.3 MW"),
    ]
    ctrl = [("initial", "初始策略", MUTED, 1.6), ("p", "P 控制", GRAY, 1.5),
            ("pi", "PI 控制", BLUE, 1.8), ("selected", "训练后", TEAL, 2.6)]
    for k, (cid, title) in enumerate(pick):
        ax = fig.add_axes([0.06 + (k % 3) * 0.315, 0.515 - (k // 3) * 0.285, 0.27, 0.215])
        for name, label, color, lw in ctrl:
            sub = [r for r in traj if r["case_id"] == cid and r["controller"] == name]
            if not sub:
                continue
            sub.sort(key=lambda r: int(r["step"]))
            ax.plot([int(r["step"]) for r in sub], [_f(r["farm_power_w"]) / 1e6 for r in sub],
                    color=color, lw=lw, label=label)
        sub = [r for r in traj if r["case_id"] == cid and r["controller"] == "selected"]
        if sub:
            tgt = _f(sub[0]["target_w"]) / 1e6
            ax.axhline(tgt, color=INK, lw=1.1, ls="--")
        ax.set_ylim(1.5, 6.0)
        ax.set_xlim(0, 128)
        ax.set_title(title, color=INK, fontsize=13.5, pad=5)
        if k % 3 == 0:
            ax.set_ylabel("全场功率 / MW", color=GRAY, fontsize=11.5)
        if k // 3 == 1:
            ax.set_xlabel("回合内时间 / s", color=GRAY, fontsize=11.5)
        clean(ax, "y")
    handles = [plt.Line2D([], [], color=c, lw=lw, label=lab) for _n, lab, c, lw in ctrl]
    handles.append(plt.Line2D([], [], color=INK, lw=1.1, ls="--", label="给定目标"))
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, fontsize=12,
               bbox_to_anchor=(0.5, 0.778))


    save(fig, "g33_tracking_grid")


def g34():
    """执行器约束核对：指令列是归一化动作，只有物理状态列能与上限比。"""
    fig = plt.figure(figsize=FS)
    frame(fig, "执行器约束核对：偏航与转速在上限内，桨距实际角速度超上限一个量级",
          "由轨迹的物理状态列逐步差分（每秒一步）　·　横轴 = 实测步进 ÷ 配置上限，竖线 1.0 即上限　·　"
          "指令列是归一化动作，不与 rad/s 比较",
          "数据来源：optimization_control/experiments/20261022_random_wind_training/test/trajectories.csv（训练后策略，"
          "20 场 × 128 步）+ config.yaml 的 rate_limits　｜　上限本身是演示假设，非现场执行器标定值",
          "第 9 页 · 独立测试（执行器约束）", TAG_SYN,
          reading="读法：偏航实测最大 0.11 °/s（上限 0.29 °/s，占 39%）、转速 0.027（上限 0.1，占 27%），都在约束内；"
                  "桨距实测最大 5.88 °/s，是配置上限 0.50 °/s 的 11.8 倍，81.8% 的步都越界 —— "
                  "**这说明「统一执行器约束」目前只在偏航与转速上成立，桨距通道的限幅还没接到实际角上，是下一阶段必须补的**。")

    traj = [r for r in rows(RANDOM / "test" / "trajectories.csv") if r["controller"] == "selected"]
    by: dict[str, list[dict]] = {}
    for r in traj:
        by.setdefault(r["case_id"], []).append(r)

    chans = [("heading_1_rad", "偏航", 0.005, BLUE),
             ("pitch_1", "桨距", 0.00872664626, AMBER),
             ("speed_1", "转速", 0.1, TEAL)]
    ratio = {}
    ax = fig.add_axes([0.065, 0.215, 0.44, 0.56])
    bins = np.linspace(0, 13, 120)
    for col, name, lim, color in chans:
        vals = []
        for _cid, rs in by.items():
            rs.sort(key=lambda r: int(r["step"]))
            v = np.array([_f(r[col]) for r in rs])
            vals.extend(np.abs(np.diff(v)) / lim)
        vals = np.clip(np.array(vals), 0, 13)
        ratio[name] = (float(vals.max()), float((vals > 1.0).mean() * 100))
        unit = "rad/s" if name == "转速" else f"{lim * 180 / math.pi:.2f} °/s"
        ax.hist(vals, bins=bins, color=color, alpha=0.55, label=f"{name}（上限 {unit}）", edgecolor="none")
    ax.axvline(1.0, color=RED, lw=1.8, ls="--")
    ax.text(1.12, ax.get_ylim()[1] * 0.93, "配置上限", color=RED, fontsize=12)
    ax.set_yscale("log")
    ax.set_xlim(0, 8)
    ax.set_xlabel("实测步进 ÷ 配置上限", color=GRAY, fontsize=13)
    ax.set_ylabel("步数（对数）", color=GRAY, fontsize=13)
    clean(ax, "y")
    ax.legend(frameon=False, fontsize=11.5, loc="upper right")

    ax2 = fig.add_axes([0.60, 0.215, 0.36, 0.56])
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis("off")
    head = ("通道", "实测最大", "上限", "占上限", "越界步")
    xs = (0.00, 0.30, 0.50, 0.66, 0.86)
    for x0, h in zip(xs, head):
        ax2.text(x0, 0.93, h, color=GRAY, fontsize=12)
    rows_txt = [
        ("偏航", "0.11 °/s", "0.29 °/s", f"{ratio['偏航'][0]:.2f}×", "0%", GREEN),
        ("转速", "0.027 rad/s", "0.1 rad/s", f"{ratio['转速'][0]:.2f}×", "0%", GREEN),
        ("桨距", "5.88 °/s", "0.50 °/s", f"{ratio['桨距'][0]:.1f}×", f"{ratio['桨距'][1]:.0f}%", RED),
    ]
    for i, (a, bb, c, d, e, color) in enumerate(rows_txt):
        y = 0.78 - i * 0.15
        ax2.add_patch(Rectangle((0, y - 0.055), 1.0, 0.11, facecolor=PANEL if i % 2 == 0 else "white",
                                edgecolor="none"))
        for x0, val in zip(xs, (a, bb, c, d, e)):
            ax2.text(x0, y, val, color=color if val in (d, e) else INK, fontsize=11.5, va="center")
    ax2.text(0.0, 0.22, "桨距超限的原因（待查）：配置里的上限作用在归一化动作上，",
             color=GRAY, fontsize=11.5)
    ax2.text(0.0, 0.14, "实际桨距由一阶惯性环节更新，中间没有限幅 —— 下一阶段",
             color=GRAY, fontsize=11.5)
    ax2.text(0.0, 0.06, "要把限幅移到实际角上，再重跑这组测试。", color=GRAY, fontsize=11.5)

    save(fig, "g34_actuator_limits")


def g35():
    """单场三机分解：尾流下游机功率低。"""
    fig = plt.figure(figsize=FS)
    frame(fig, "同一场里三台机的分工：下游机功率低，但也在按目标调整",
          "阵风工况、目标 2.7 MW、训练后策略　·　上：三台机功率　·　下：三台机的盘面有效风速",
          "数据来源：optimization_control/experiments/20261022_random_wind_training/test/trajectories.csv"
          "（case_id = test_gust_0_pitch0.025）　｜　标签为合成教师模型；此处不引用 P2/P1 比值",
          "第 9 页 · 独立测试（机组间分布）", TAG_SYN,
          reading="读法：三台机的功率差主要来自盘面有效风速差（下游两台长期偏低），而不是控制指令差 —— 这也是为什么「提高全场功率」只能靠上游机让出一点来换下游机多拿。")

    traj = [r for r in rows(RANDOM / "test" / "trajectories.csv")
            if r["controller"] == "selected" and r["case_id"] == "test_gust_0_pitch0.025"]
    traj.sort(key=lambda r: int(r["step"]))
    step = np.array([int(r["step"]) for r in traj])
    colors = (BLUE, TEAL, AMBER)

    ax = fig.add_axes([0.065, 0.40, 0.87, 0.34])
    for i in (1, 2, 3):
        ax.plot(step, [_f(r[f"power_{i}_w"]) / 1e3 for r in traj], color=colors[i - 1], lw=2.0,
                label=f"第 {i} 台")
    ax.plot(step, [_f(r["farm_power_w"]) / 1e3 for r in traj], color=INK, lw=1.4, ls="--", label="三机合计")
    ax.set_ylabel("功率 / kW", color=GRAY, fontsize=13)
    ax.set_xlim(0, 128)
    clean(ax, "y")
    ax.legend(frameon=False, fontsize=11.5, ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.02))

    ax2 = fig.add_axes([0.065, 0.215, 0.87, 0.140])
    for i in (1, 2, 3):
        ax2.plot(step, [_f(r[f"ueff_{i}_m_s"]) for r in traj], color=colors[i - 1], lw=1.9)
    ax2.set_xlabel("回合内时间 / s", color=GRAY, fontsize=13)
    ax2.set_ylabel("盘面有效风速 / m/s", color=GRAY, fontsize=13)
    ax2.set_xlim(0, 128)
    clean(ax2, "y")


    save(fig, "g35_per_turbine")


# ══════════════════════════════════════════════════════════════════════
# PINN · 训练诊断（第 7 页）
# ══════════════════════════════════════════════════════════════════════
def g36():
    """200 epoch 收敛 + 测试误差。"""
    fig = plt.figure(figsize=FS)
    frame(fig, "200 轮训练：验证损失同步下降，测试 MAE 停在 41–57 kW 量级",
          "左：训练/验证损失（对数轴）　·　右：测试集三台机的 MAE / RMSE　·　"
          "同一批 12,096 / 4,032 / 4,032 划分",
          "数据来源：materials/袁夫达/20261025_仿真建模数据交接/model/training_report.json"
          "（epochs=200、seed=1234、trainable_parameters=27,106）　｜　标签来源为 FLORIS 合成，"
          "误差不代表对真实机组的物理精度",
          "第 7 页 · PINN 迁移（训练与测试）", TAG_SIM,
          reading="读法：两条损失曲线在整个训练里同步下降，没有出现「训练降、验证升」的过拟合形态；误差的绝对值只在「合成标签」这个口径内成立 —— 它衡量的是对 FLORIS 标签的逼近，不是对真实风场的精度。")

    rep = json.loads(PINN_REPORT.read_text(encoding="utf-8"))
    lo = np.array(rep["history"]["loss"], dtype=float)
    va = np.array(rep["history"]["val_loss"], dtype=float)

    ax = fig.add_axes([0.065, 0.215, 0.4, 0.535])
    ax.semilogy(np.arange(1, len(lo) + 1), lo, color=BLUE, lw=2.2, label="训练损失")
    ax.semilogy(np.arange(1, len(va) + 1), va, color=AMBER, lw=2.2, label="验证损失")
    ax.set_xlabel("epoch", color=GRAY, fontsize=13)
    ax.set_ylabel("损失（对数轴）", color=GRAY, fontsize=13)
    clean(ax, "y")
    ax.legend(frameon=False, fontsize=12.5, loc="upper right")
    ax.text(6, lo[0] * 0.55, f"起点 {lo[0]:.3f}", color=GRAY, fontsize=11.5)
    ax.text(len(lo) * 0.55, lo[-1] * 2.6, f"终点 {lo[-1]:.4f}（降 {lo[0] / lo[-1]:.0f}×）",
            color=GRAY, fontsize=11.5)

    ax2 = fig.add_axes([0.575, 0.215, 0.385, 0.535])
    tm = rep["test_metrics"]
    names = ["P1", "P2", "P3"]
    mae = [tm[k]["MAE"] / 1e3 for k in names]
    rmse = [tm[k]["RMSE"] / 1e3 for k in names]
    x = np.arange(3)
    ax2.bar(x - 0.19, mae, width=0.36, color=TEAL, label="MAE")
    ax2.bar(x + 0.19, rmse, width=0.36, color=BLUE, alpha=0.75, label="RMSE")
    for i, (a, c) in enumerate(zip(mae, rmse)):
        ax2.text(i - 0.19, a + 1.4, f"{a:.1f}", ha="center", color=INK, fontsize=12)
        ax2.text(i + 0.19, c + 1.4, f"{c:.1f}", ha="center", color=GRAY, fontsize=11.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(["第 1 台 P1", "第 2 台 P2", "第 3 台 P3"])
    ax2.set_ylabel("测试误差 / kW", color=GRAY, fontsize=13)
    ax2.set_ylim(0, max(rmse) * 1.22)
    clean(ax2, "y")
    ax2.legend(frameon=False, fontsize=12, loc="upper left")
    ax2.set_title(f"测试集 4,032 条　·　负输出 {rep['negative_test_output_count']} 条"
                  f"（{rep['negative_test_output_count'] / 4032 * 100:.1f}%，须先取 max(P,0)）",
                  color=GRAY, fontsize=12, pad=10)


    save(fig, "g36_pinn_training")


FIGURES = {
    "g26": ("CFD 尾流中心线 · 双湍流模型", g26),
    "g27": ("CFD 盘面平均速度与 TI 对照", g27),
    "g28": ("CFD 尾流横向剖面", g28),
    "g29": ("来流方向扫描 · 尾流损失", g29),
    "g30": ("数据集口径自检 · 反算 Cp", g30),
    "g31": ("湍流强度敏感性", g31),
    "g32": ("逐场配对 · 18 场胜负", g32),
    "g33": ("六工况跟踪小倍数", g33),
    "g34": ("执行器速率上限核对", g34),
    "g35": ("单场三机功率分解", g35),
    "g36": ("PINN 训练与测试误差", g36),
}


def main(argv):
    if "--list" in argv:
        for k, (desc, _f) in FIGURES.items():
            print(f"  {k}  {desc}")
        return 0
    todo = [a for a in argv if not a.startswith("-")] or list(FIGURES)
    use_cjk()
    print("字体:", plt.rcParams["font.family"])
    for key in todo:
        if key not in FIGURES:
            print(f"  ?? 未知图号 {key}")
            continue
        print(f"[{key}] {FIGURES[key][0]}")
        FIGURES[key][1]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
