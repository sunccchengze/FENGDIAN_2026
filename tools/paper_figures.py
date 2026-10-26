#!/usr/bin/env python3
"""论文插图（2026-10-26）：期刊/学位论文用的 figure，不是 slide。

与 `make_defense_figures*.py` 的分工
------------------------------------
那两个脚本产出**答辩整页**：16:9、带页眉题注、右下角证据角标、页脚来源条。
本脚本产出**可插进论文正文的插图**：

  · 无标题、无页眉、无页脚、无角标 —— 论文里 figure 的说明文字在 caption（见
    `docs/defense/paper_captions.md`），不烧在图上；
  · 尺寸按版面：单栏 3.35 in、双栏 6.90 in，多面板用 (a)(b)(c) 标号；
  · 中文宋体 + 拉丁/数字衬线（DejaVu Serif），字号 7–9 pt，线宽 0.8，四边闭合、刻度朝内；
  · 导出 400 dpi PNG + 矢量 PDF。

数据全部只读仓库既有 CSV/JSON，不重跑实验。

用法
----
    python3 tools/paper_figures.py            # 全部
    python3 tools/paper_figures.py fig04 fig09
    python3 tools/paper_figures.py --list
输出：docs/defense/assets/paper/
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figstyle as F

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "defense" / "assets" / "paper"

# 论文插图用色：低饱和、可灰度打印（蓝 / 橙 / 绿 / 红 / 灰，色盲友好）
C = {
    "ours": "#1f4e79",      # 我们的方法
    "base": "#7f7f7f",      # 基线（PI）
    "alt": "#c87e2c",       # 第二个湍流模型 / 第二组
    "acc": "#4a7d3f",       # 改进
    "warn": "#b23b32",      # 落后 / 超限
    "light": "#c9d6e3",
    "grid": "#dcdcdc",
}

# ── 数据源 ──────────────────────────────────────────────────────────────
DATASET = ROOT / "materials" / "袁夫达" / "20261025_仿真建模数据交接"
CASES = DATASET / "data" / "cases_wind.csv"
PINN_REPORT = DATASET / "model" / "training_report.json"
CFD = ROOT / "materials" / "田铭雨" / "20261024_三机串列双模型对比"
RANDOM = ROOT / "optimization_control" / "experiments" / "20261022_random_wind_training"
BASELINE_NN = ROOT / "materials" / "厉今飞" / "20260808_功率预测神经网络基线"
VIZ = ROOT / "viz"   # 两机串列 / 3×3 阵列 / POD 的 FLORIS 数据（8 月历史工作）

D_ROTOR = 125.88
A_ROTOR = math.pi * (D_ROTOR / 2) ** 2
RHO = 1.225
MODELS = (("k-omega_data", "k-$\\omega$ SST", C["ours"]), ("k-epsilon_data", "k-$\\varepsilon$", C["alt"]))
TURB_X = (8.0, -370.0, -748.0)


def rows(p) -> list[dict]:
    with Path(p).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def f(v) -> float:
    return float(str(v).replace("\r", "").strip())


# ══════════════════════════════════════════════════════════════════════
def fig01():
    """设计空间：来流风速 × 风向，以及来流风速 × 湍流强度。"""
    data = rows(CASES)
    aligned = [r for r in data if abs(f(r["yaw1"])) < 1e-6 and abs(f(r["pitch1"])) < 1e-6]

    ws_list = sorted({f(r["ambient_wind_speed_m_s"]) for r in aligned})
    wd_list = sorted({round(math.degrees(f(r["ambient_wind_direction_rad"])), 1) for r in aligned})
    P = np.full((len(ws_list), len(wd_list)), np.nan)
    for r in aligned:
        i = ws_list.index(f(r["ambient_wind_speed_m_s"]))
        j = wd_list.index(round(math.degrees(f(r["ambient_wind_direction_rad"])), 1))
        P[i, j] = (f(r["P1"]) + f(r["P2"]) + f(r["P3"])) / 1e3
    # 每个风速只保留一次（同一格有 3 档 TI，取均值）
    P2 = np.full_like(P, np.nan)
    for i, ws in enumerate(ws_list):
        for j, wd in enumerate(wd_list):
            v = [f(r["P1"]) + f(r["P2"]) + f(r["P3"]) for r in aligned
                 if abs(f(r["ambient_wind_speed_m_s"]) - ws) < 1e-6
                 and abs(math.degrees(f(r["ambient_wind_direction_rad"])) - wd) < 0.06]
            if v:
                P2[i, j] = st.mean(v) / 1e3

    # (b) 风速 × 湍流强度：这两维在设计网格上完全正交（每格样本数相同），
    # 而桨距只在个别工况点取值，画成“桨距—功率”图会读出错误的趋势。
    ti_list = sorted({round(f(r["turbulence_intensity"]), 2) for r in aligned})
    R = np.full((len(ws_list), len(ti_list)), np.nan)
    for i, ws in enumerate(ws_list):
        for j, ti in enumerate(ti_list):
            v = [f(r["P1"]) + f(r["P2"]) + f(r["P3"]) for r in aligned
                 if abs(f(r["ambient_wind_speed_m_s"]) - ws) < 1e-6
                 and abs(f(r["turbulence_intensity"]) - ti) < 1e-6]
            if v:
                R[i, j] = st.mean(v) / 1e3

    fig = plt.figure(figsize=(6.9, 2.55))
    ax1 = F.paper_axes(fig, [0.075, 0.19, 0.36, 0.68])
    im1 = ax1.pcolormesh(wd_list, ws_list, P2, cmap="viridis", shading="nearest")
    ax1.set_xlabel("来流方向 / (°)")
    ax1.set_ylabel("来流风速 / (m/s)")
    ax1.set_xticks([0, 90, 180, 270, 360])
    ax1.set_yticks([5, 7, 9, 11])
    cb1 = fig.colorbar(im1, ax=ax1, pad=0.02, fraction=0.05)
    cb1.set_label("三机总功率 / kW", fontsize=7.5)
    cb1.ax.tick_params(labelsize=6.5)
    F.panel_label(ax1, "(a)")

    ax2 = F.paper_axes(fig, [0.585, 0.19, 0.28, 0.68])
    im2 = ax2.pcolormesh(ti_list, ws_list, R, cmap="viridis", shading="nearest")
    ax2.set_xlabel("湍流强度")
    ax2.set_ylabel("来流风速 / (m/s)")
    ax2.set_xticks(ti_list)
    ax2.set_xticklabels([f"{v:.0%}" for v in ti_list])
    ax2.set_yticks([5, 7, 9, 11])
    cb2 = fig.colorbar(im2, ax=ax2, pad=0.02, fraction=0.05)
    cb2.set_label("三机总功率 / kW", fontsize=7.5)
    cb2.ax.tick_params(labelsize=6.5)
    F.panel_label(ax2, "(b)")
    F.paper_save(fig, OUT, "fig01_design_space")


def fig02():
    """五种偏航策略在各风速下的总功率（均值 ± 标准差）。"""
    data = rows(CASES)
    strat = {0: "对齐", 10: "统一 +10°", -10: "统一 −10°", 20: "统一 +20°"}
    ws_list = sorted({f(r["ambient_wind_speed_m_s"]) for r in data})
    fig = plt.figure(figsize=(3.35, 2.65))
    ax = F.paper_axes(fig, [0.155, 0.175, 0.80, 0.75])

    series = []
    for key, label in strat.items():
        mu, sd = [], []
        for ws in ws_list:
            v = [(f(r["P1"]) + f(r["P2"]) + f(r["P3"])) / 1e3 for r in data
                 if abs(f(r["ambient_wind_speed_m_s"]) - ws) < 1e-6
                 and abs(round(math.degrees(f(r["yaw1"])), 0) - key) < 0.1
                 and abs(round(math.degrees(f(r["yaw2"])), 0) - key) < 0.1]
            mu.append(st.mean(v) if v else np.nan)
            sd.append(st.pstdev(v) if len(v) > 1 else 0.0)
        series.append((label, np.array(mu)))
    # 错列策略单独一条
    mu, sd = [], []
    for ws in ws_list:
        v = [(f(r["P1"]) + f(r["P2"]) + f(r["P3"])) / 1e3 for r in data
             if abs(f(r["ambient_wind_speed_m_s"]) - ws) < 1e-6
             and abs(round(math.degrees(f(r["yaw1"])), 0) - 20) < 0.1
             and abs(round(math.degrees(f(r["yaw2"])), 0) + 20) < 0.1]
        mu.append(st.mean(v) if v else np.nan)
        sd.append(st.pstdev(v) if len(v) > 1 else 0.0)
    series.append(("错列 +20/−20°", np.array(mu)))

    styles = [("-", "o", "#111111"), ("--", "s", C["ours"]), ("-.", "^", C["alt"]),
              (":", "v", C["warn"]), ("-", "D", C["acc"])]
    for (label, y), (ls, mk, col) in zip(series, styles):
        ax.plot(ws_list, y, ls=ls, marker=mk, color=col, lw=1.1, ms=3.0, label=label,
                markerfacecolor="white", markeredgewidth=0.8)
    ax.set_xlabel("来流风速 / (m/s)")
    ax.set_ylabel("三机总功率 / kW")
    ax.set_xlim(4.5, 12.5)
    ax.legend(loc="upper left", ncol=1, fontsize=6.5, handletextpad=0.5)
    F.paper_save(fig, OUT, "fig02_yaw_strategies")


def fig03():
    """湍流强度对总功率的影响（带局部放大）。"""
    data = rows(CASES)
    aligned = [r for r in data if abs(f(r["yaw1"])) < 1e-6 and abs(f(r["pitch1"])) < 1e-6
               and abs(math.degrees(f(r["ambient_wind_direction_rad"]))) < 0.6]
    ws_list = sorted({f(r["ambient_wind_speed_m_s"]) for r in aligned})
    fig = plt.figure(figsize=(3.35, 2.65))
    ax = F.paper_axes(fig, [0.155, 0.175, 0.80, 0.75])
    cols = {0.06: C["ours"], 0.08: C["acc"], 0.10: C["alt"]}
    for ti in (0.06, 0.08, 0.10):
        y = [st.mean([(f(r["P1"]) + f(r["P2"]) + f(r["P3"])) / 1e3 for r in aligned
                      if abs(f(r["ambient_wind_speed_m_s"]) - ws) < 1e-6
                      and abs(f(r["turbulence_intensity"]) - ti) < 1e-9]) for ws in ws_list]
        ax.plot(ws_list, y, marker="o", ms=3.0, color=cols[ti], label=f"TI = {int(ti * 100)} %",
                markerfacecolor="white", markeredgewidth=0.9)
    ax.set_xlabel("来流风速 / (m/s)")
    ax.set_ylabel("三机总功率 / kW")
    ax.legend(loc="upper left", fontsize=6.8)

    # 放大：6–8 m/s
    axi = ax.inset_axes([0.50, 0.10, 0.46, 0.38])
    for ti in (0.06, 0.08, 0.10):
        y = [st.mean([(f(r["P1"]) + f(r["P2"]) + f(r["P3"])) / 1e3 for r in aligned
                      if abs(f(r["ambient_wind_speed_m_s"]) - ws) < 1e-6
                      and abs(f(r["turbulence_intensity"]) - ti) < 1e-9]) for ws in ws_list]
        axi.plot(ws_list, y, marker="o", ms=2.0, color=cols[ti], lw=1.0)
    axi.set_xlim(6.7, 8.45)
    axi.set_ylim(1400, 2400)
    axi.set_xticks([7, 8])
    axi.set_yticks([1500, 2000])
    axi.tick_params(labelsize=6, direction="in", top=True, right=True)
    for s in axi.spines.values():
        s.set_linewidth(0.6)
    F.paper_save(fig, OUT, "fig03_ti_sensitivity")


def fig04():
    """尾流：中心线速度分布，以及 k-ε 相对 k-ω 的相对偏差。"""
    fig = plt.figure(figsize=(6.9, 2.6))

    def centerline(folder):
        r = rows(CFD / folder / "wake_centerline.csv")
        x = np.array([(TURB_X[0] - f(t["z_m"])) / D_ROTOR for t in r])
        y = np.array([f(t["U_forward_smooth_m_s"]) for t in r])
        o = np.argsort(x)
        return x[o], y[o]

    def binned(x, y, width=0.25):
        edges = np.arange(0, 10 + width, width)
        cx, med, p10, p90 = [], [], [], []
        for i in range(len(edges) - 1):
            m = (x >= edges[i]) & (x < edges[i + 1])
            if m.sum() < 3:
                continue
            cx.append((edges[i] + edges[i + 1]) / 2)
            med.append(np.median(y[m]))
            p10.append(np.percentile(y[m], 10))
            p90.append(np.percentile(y[m], 90))
        return map(np.array, (cx, med, p10, p90))

    ax1 = F.paper_axes(fig, [0.075, 0.20, 0.40, 0.70])
    curves = {}
    for folder, label, col in MODELS:
        x, y = centerline(folder)
        cx, med, p10, p90 = binned(x, y)
        curves[label] = (cx, med)
        ax1.fill_between(cx, p10, p90, color=col, alpha=0.15, lw=0)
        ax1.plot(cx, med, color=col, marker="o", ms=2.2, label=label)
    ax1.axhline(9.0, color="#888888", lw=0.7, ls=":")
    for xd, tag in (((TURB_X[0] - TURB_X[1]) / D_ROTOR, "T2"), ((TURB_X[0] - TURB_X[2]) / D_ROTOR, "T3")):
        ax1.axvline(xd, color="#bbbbbb", lw=0.7, ls="--")
        ax1.text(xd + 0.12, 2.35, tag, fontsize=7, color="#555555")
    ax1.text(0.15, 2.35, "T1", fontsize=7, color="#555555")
    ax1.set_xlim(0, 10)
    ax1.set_ylim(2, 9.8)
    ax1.set_xlabel("下游距离 x/D")
    ax1.set_ylabel("轴向速度 / (m/s)")
    ax1.legend(loc="lower right", fontsize=7)
    F.panel_label(ax1, "(a)")

    ax2 = F.paper_axes(fig, [0.585, 0.20, 0.28, 0.70])
    a = curves["k-$\\omega$ SST"]
    b = curves["k-$\\varepsilon$"]
    dev = (b[1] - a[1]) / a[1] * 100
    ax2.axhline(0, color="#555555", lw=0.7)
    ax2.axvspan(0, 7, color="#f0f0f0", zorder=0)
    ax2.plot(a[0], dev, color="#7a5aa0", lw=1.0, marker="o", ms=2.0, markerfacecolor="white")
    ax2.set_xlim(0, 10)
    ax2.set_xlabel("下游距离 x/D")
    ax2.set_ylabel("k-ε 相对 k-ω 的偏差 / %")
    ax2.text(6.6, ax2.get_ylim()[1] * 0.82, "近场 < 7D", fontsize=6.6, color="#777777", ha="right")
    F.panel_label(ax2, "(b)")

    # 横向剖面未纳入本图：wake_profiles.csv 的横向取样在盘面附近成片跳变
    # （相邻 8 m 点从 9.6 m/s 跳到 4.9 m/s、甚至出现 -7.7 m/s），
    # 属提取口径问题，平滑只会掩盖而不解决，故本图只保留中心线与模型偏差。
    F.paper_save(fig, OUT, "fig04_wake_centerline_profiles")


def _clean_profile(y: np.ndarray) -> np.ndarray:
    """剖面清洗：剔除非物理值 → 线性补齐 → 5 点中位数去毛刺 → 5 点均值平滑。

    原始提取里存在少量单点离群（盘内近零点、个别 >15 m/s 的取样），
    直接连线会在剖面中造出假尖峰，因此在绘图前做统一处理（图注已声明）。
    """
    y = np.array(y, dtype=float)
    y[y < 0.5] = np.nan
    idx = np.arange(len(y))
    good = np.isfinite(y)
    if good.sum() < 5:
        return y
    y = np.interp(idx, idx[good], y[good])
    if len(y) >= 5:
        ypad = np.pad(y, 2, mode="edge")
        y = np.median(np.lib.stride_tricks.sliding_window_view(ypad, 5), axis=1)
    y = np.convolve(np.pad(y, 2, mode="edge"), np.ones(5) / 5, mode="valid")
    return y


def _smooth(Z: np.ndarray, k: int = 1) -> np.ndarray:
    """对极坐标矩阵做环形-aware 的盒式平滑（方位向首尾相接，径向不接）。"""
    A = np.array(Z, dtype=float)
    A = np.where(np.isfinite(A), A, np.nanmean(A))
    for _ in range(k):
        P = np.pad(A, ((1, 1), (0, 0)), mode="edge")
        Q = np.pad(A, ((0, 0), (1, 1)), mode="wrap")
        A = (P[:-2, :] + P[1:-1, :] + P[2:, :] + Q[:, :-2] + Q[:, 1:-1] + Q[:, 2:]) / 6.0
    return A


def _disk(folder, turbine, field):
    r = rows(CFD / folder / f"rotor{turbine}_plane.csv")
    rs = sorted({round(f(t["r_m"]), 3) for t in r})
    th = sorted({round(f(t["theta_rad"]), 5) for t in r})
    Z = np.full((len(rs), len(th)), np.nan)
    for t in r:
        Z[rs.index(round(f(t["r_m"]), 3)), th.index(round(f(t["theta_rad"]), 5))] = f(t[field])
    return np.array(rs), np.array(th), Z


def fig05():
    """三台机盘面速度分布（极坐标），两模型同色标。"""
    fig = plt.figure(figsize=(6.9, 4.3))
    vmin, vmax = 2.0, 9.0
    for i, (folder, label, _c) in enumerate(MODELS):
        for j in range(3):
            ax = fig.add_axes([0.075 + j * 0.245, 0.50 - i * 0.44, 0.20, 0.38], projection="polar")
            rs, th, Z = _disk(folder, j + 1, "U_forward_m_s")
            # 不做平滑、不做插值：648 个取样点的单点值本来就是离散的，
            # 平滑后出现的「螺旋花纹」是插值伪影，不是流场结构（图注已声明）。
            # 周向首尾需要闭合，否则 0°/360° 处会留一条白色楔形缝
            dth = th[1] - th[0]
            th_c = np.append(th, th[-1] + dth)
            Z_c = np.hstack([Z, Z[:, :1]])
            TE, RE = np.meshgrid(th_c, rs)
            mesh = ax.pcolormesh(TE, RE, np.clip(Z_c, vmin, vmax), cmap="viridis",
                                 vmin=vmin, vmax=vmax, shading="nearest")
            ax.set_theta_zero_location("N")
            ax.set_theta_direction(-1)
            ax.grid(False)
            ax.set_yticks([])
            ax.set_xticks(np.radians([0, 90, 180, 270]))
            ax.set_xticklabels(["", "", "", ""])
            ax.tick_params(pad=-6)
            ax.spines["polar"].set_linewidth(0.7)
            ax.set_title(f"{label} · T{j + 1}", fontsize=8, pad=2)
            if i == 0 and j == 0:
                F.panel_label(ax, "(a)", x=-0.16, y=1.06)
            if i == 1 and j == 0:
                F.panel_label(ax, "(b)", x=-0.16, y=1.06)
    cax = fig.add_axes([0.815, 0.12, 0.014, 0.76])
    cb = fig.colorbar(mesh, cax=cax)
    cb.set_label("盘面轴向速度 / (m/s)", fontsize=7.5)
    cb.ax.tick_params(labelsize=6.5)
    F.paper_save(fig, OUT, "fig05_rotor_planes")


def fig06():
    """盘面湍流强度的径向分布。"""
    fig = plt.figure(figsize=(6.9, 2.5))
    for k in range(3):
        ax = F.paper_axes(fig, [0.075 + k * 0.315, 0.185, 0.265, 0.72])
        for folder, label, col in MODELS:
            rs, _th, Z = _disk(folder, k + 1, "TI")
            med = np.nanmedian(Z * 100, axis=1)
            q1 = np.clip(np.nanpercentile(Z * 100, 25, axis=1), 0, None)
            q3 = np.nanpercentile(Z * 100, 75, axis=1)
            ax.fill_between(rs, q1, q3, color=col, alpha=0.14, lw=0)
            ax.plot(rs, med, color=col, marker="o", ms=2.4, label=label)
        ax.set_xlabel("盘面半径 / m")
        ax.set_ylim(0, 18)          # 三幅共用纵轴，便于横向比较
        ax.set_yticks([0, 5, 10, 15])
        if k == 0:
            ax.set_ylabel("湍流强度 / %")
            ax.legend(loc="upper center", fontsize=6.6, ncol=2, columnspacing=0.8,
                      handlelength=1.4, borderaxespad=0.2)
        ax.set_title(f"T{k + 1}", fontsize=8.5, pad=3)
        F.panel_label(ax, "(" + "abc"[k] + ")")
    F.paper_save(fig, OUT, "fig06_disk_ti_radial")


def _case_avg(ctrl, key="rmse_w", routine_only=True):
    by = {}
    for r in rows(RANDOM / "test" / "metrics.csv"):
        if r["controller"] != ctrl:
            continue
        if routine_only and r["family"] == "low_wind_stress":
            continue
        by.setdefault(r["case_id"], []).append(f(r[key]) / 1e3)
    return {k: st.mean(v) for k, v in by.items()}


def fig07():
    """四控制器 × 三来流族的 RMSE 分布（箱线 + 散点）。"""
    data = rows(RANDOM / "test" / "metrics.csv")
    fams = [("stationary", "平稳"), ("ramp", "慢变"), ("gust", "阵风")]
    ctrls = [("initial", "初始策略", "#c8c8c8"), ("p", "P 控制", "#a8a8a8"),
             ("pi", "PI 控制", C["base"]), ("selected", "训练后", C["ours"])]
    fig = plt.figure(figsize=(3.35, 2.9))
    ax = F.paper_axes(fig, [0.165, 0.175, 0.79, 0.70])
    width = 0.19
    for i, (fam, flabel) in enumerate(fams):
        for j, (ctrl, clabel, col) in enumerate(ctrls):
            v = [f(r["rmse_w"]) / 1e3 for r in data if r["family"] == fam and r["controller"] == ctrl]
            pos = i + (j - 1.5) * width
            bp = ax.boxplot([v], positions=[pos], widths=width * 0.85, patch_artist=True,
                            showfliers=False, medianprops=dict(color="white", lw=1.0),
                            boxprops=dict(facecolor=col, edgecolor="#333333", lw=0.6),
                            whiskerprops=dict(lw=0.6, color="#333333"),
                            capprops=dict(lw=0.6, color="#333333"))
            rng = np.random.default_rng(0)
            ax.scatter(pos + rng.uniform(-0.035, 0.035, len(v)), v, s=3.5,
                       color="#222222", alpha=0.55, linewidths=0, zorder=3)
    ax.set_xticks(range(len(fams)))
    ax.set_xticklabels([l for _f, l in fams])
    ax.set_xlabel("来流族")
    ax.set_ylabel("跟踪 RMSE / kW")
    ax.set_ylim(150, 1900)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=c, edgecolor="#333333", lw=0.6)
               for _k, _l, c in ctrls]
    ax.legend(handles, [l for _k, l, _c in ctrls], loc="lower center", fontsize=6.6, ncol=4,
              columnspacing=0.7, handlelength=1.2, bbox_to_anchor=(0.5, 1.005))
    F.paper_save(fig, OUT, "fig07_rmse_boxes")


def fig08():
    """误差累积分布（CDF）：训练后在小误差段的占比更高。"""
    fig = plt.figure(figsize=(3.35, 2.65))
    ax = F.paper_axes(fig, [0.165, 0.185, 0.79, 0.74])
    ctrls = [("initial", "初始策略", "#b9b9b9"), ("p", "P 控制", "#8f8f8f"),
             ("pi", "PI 控制", C["base"]), ("selected", "训练后", C["ours"])]
    for ctrl, label, col in ctrls:
        v = np.sort(np.array([f(r["rmse_w"]) / 1e3 for r in rows(RANDOM / "test" / "metrics.csv")
                              if r["controller"] == ctrl and r["family"] != "low_wind_stress"]))
        ax.plot(v, np.arange(1, len(v) + 1) / len(v), color=col, lw=1.2,
                ls="-" if ctrl == "selected" else "--", label=label)
    ax.set_xlabel("跟踪 RMSE / kW")
    ax.set_ylabel("累积概率")
    ax.set_xlim(250, 720)
    ax.set_ylim(0, 1.02)
    ax.legend(loc="upper left", fontsize=6.6, handlelength=1.8, borderaxespad=0.35,
              labelspacing=0.3)
    F.paper_save(fig, OUT, "fig08_error_cdf")


def fig09():
    """逐场配对：训练后 vs PI（1:1 线 + 边缘分布）。"""
    sel, pi = _case_avg("selected"), _case_avg("pi")
    cases = sorted(sel)
    x = np.array([pi[c] for c in cases])
    y = np.array([sel[c] for c in cases])
    fam = {r["case_id"]: r["family"] for r in rows(RANDOM / "test" / "metrics.csv")}
    style = {"gust": ("o", C["alt"], "阵风"), "ramp": ("s", C["ours"], "慢变"),
             "stationary": ("^", C["acc"], "平稳")}

    fig = plt.figure(figsize=(3.35, 3.15))
    ax = F.paper_axes(fig, [0.165, 0.225, 0.655, 0.715])
    lim = (270, 710)
    ax.plot(lim, lim, color="#555555", lw=0.8, ls="--")
    ax.fill_between(lim, [v - 50 for v in lim], [v + 50 for v in lim], color="#eeeeee", zorder=0, lw=0)
    for famname, (mk, col, lab) in style.items():
        idx = [i for i, c in enumerate(cases) if fam[c] == famname]
        ax.scatter(x[idx], y[idx], marker=mk, s=18, facecolor=col, edgecolor="white",
                   linewidth=0.5, label=lab, zorder=3)
    ax.set_xlim(*lim)
    ax.set_ylim(*lim)
    ax.set_xlabel("PI 控制 RMSE / kW")
    ax.set_ylabel("训练后 RMSE / kW")
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=6.4, handletextpad=0.3)
    ax.text(0.97, 0.05, f"均值 {y.mean():.0f} vs {x.mean():.0f} kW", transform=ax.transAxes,
            ha="right", fontsize=6.6, color="#333333")

    # 右侧边缘：差值分布
    axr = F.paper_axes(fig, [0.865, 0.235, 0.115, 0.70])
    d = np.sort(y - x)
    axr.axvline(0, color="#555555", lw=0.8)
    for yi, di in zip(np.arange(len(d)), d):
        axr.plot([0, di], [yi, yi], color="#cccccc", lw=0.7, zorder=1)
    axr.scatter(d, np.arange(len(d)), s=8,
                color=[C["acc"] if di < 0 else C["warn"] for di in d], zorder=3,
                linewidths=0)
    axr.set_ylim(-0.5, len(d) - 0.5)
    axr.set_xlim(-230, 230)
    axr.set_xticks([-200, 0, 200])
    axr.set_xticklabels(["-200", "0", "200"], fontsize=6)
    axr.set_xlabel("差值 / kW", fontsize=7)
    axr.set_yticks([])
    F.paper_save(fig, OUT, "fig09_paired_scatter")


def fig10():
    """训练收敛：PINN（200 轮）与功率预测基线（1000 轮）。"""
    fig = plt.figure(figsize=(6.9, 2.6))
    ax1 = F.paper_axes(fig, [0.075, 0.185, 0.30, 0.72])
    rep = json.loads(PINN_REPORT.read_text(encoding="utf-8"))
    lo = np.array(rep["history"]["loss"], dtype=float)
    va = np.array(rep["history"]["val_loss"], dtype=float)
    ax1.semilogy(np.arange(1, len(lo) + 1), lo, color=C["ours"], lw=1.1, label="训练")
    ax1.semilogy(np.arange(1, len(va) + 1), va, color=C["alt"], lw=1.1, ls="--", label="验证")
    ax1.set_xlabel("训练轮次 (epoch)")
    ax1.set_ylabel("损失（对数坐标）")
    ax1.legend(loc="upper right", fontsize=6.8)
    ax1.set_title("(a) PINN 迁移训练", fontsize=8.5, pad=4)

    ax2 = F.paper_axes(fig, [0.425, 0.185, 0.285, 0.72])
    for out, label, col, ls in (("output_cc", "算例 CC", C["ours"], "-"), ("output_gch", "算例 GCH", C["alt"], "--")):
        h = rows(BASELINE_NN / out / "wind_farm_results" / "training_history.csv")
        loss = np.array([f(r["loss"]) for r in h])
        val = np.array([f(r["val_loss"]) for r in h])
        ax2.semilogy(np.arange(1, len(loss) + 1), loss, color=col, ls=ls, lw=1.0, label=f"{label} 训练")
        ax2.semilogy(np.arange(1, len(val) + 1), val, color=col, ls=":", lw=0.9, label=f"{label} 验证")
    ax2.set_xlabel("训练轮次 (epoch)")
    ax2.set_ylabel("损失（对数坐标）")
    ax2.legend(loc="upper right", fontsize=6.2, ncol=2, columnspacing=0.6)
    ax2.set_title("(b) 功率预测基线（两组算例）", fontsize=8.5, pad=4)

    # 右：两套模型结构规模对比（柱）
    ax3 = F.paper_axes(fig, [0.805, 0.185, 0.155, 0.72])
    names = ["原主干\n(冻结)", "新增\n可训练"]
    vals = [3087200 / 1e6, 27106 / 1e6]
    ax3.bar([0, 1], vals, color=[C["light"], C["ours"]], edgecolor="#333333", lw=0.6, width=0.6)
    ax3.set_yscale("log")
    ax3.set_xticks([0, 1])
    ax3.set_xticklabels(names, fontsize=6.8)
    ax3.set_ylabel("参数量 / 百万", labelpad=1.5, fontsize=8)
    for i, v in enumerate(vals):
        ax3.text(i, v * 1.8, ("0.027" if v < 1 else "3.09"), ha="center", fontsize=6.5)
    ax3.set_ylim(1e-3, 60)
    ax3.set_title("(c) 参数冻结", fontsize=8.5, pad=4)
    F.paper_save(fig, OUT, "fig10_learning_curves")


def fig11():
    """预测-真值一致性 + 残差分布（功率预测基线测试集）。"""
    r = rows(BASELINE_NN / "output_gch" / "wind_farm_results" / "test_predictions.csv")
    true = np.array([f(x["farm_power"]) for x in r]) / 1e3
    pred = np.array([f(x["pred_farm_power"]) for x in r]) / 1e3
    err = pred - true

    fig = plt.figure(figsize=(6.9, 2.8))
    ax1 = F.paper_axes(fig, [0.075, 0.19, 0.275, 0.72])
    hb = ax1.hexbin(true, pred, gridsize=22, cmap="Blues", mincnt=1, linewidths=0.2)
    lim = [0, max(true.max(), pred.max()) * 1.06]
    ax1.plot(lim, lim, color="#b23b32", lw=0.8, ls="--")
    ax1.set_xlim(*lim)
    ax1.set_ylim(*lim)
    ax1.set_xlabel("真值 / kW")
    ax1.set_ylabel("预测 / kW")
    cb = fig.colorbar(hb, ax=ax1, pad=0.10, fraction=0.05)
    cb.set_label("样本数", fontsize=7)
    cb.ax.tick_params(labelsize=6.2)
    F.panel_label(ax1, "(a)")

    ax2 = F.paper_axes(fig, [0.505, 0.19, 0.215, 0.72])
    ax2.axhline(0, color="#555555", lw=0.8)
    ax2.scatter(true, err, s=7, facecolor=C["ours"], edgecolor="white", linewidth=0.3)
    ax2.set_xlabel("真值 / kW")
    ax2.set_ylabel("残差 / kW")
    F.panel_label(ax2, "(b)")

    ax3 = F.paper_axes(fig, [0.795, 0.19, 0.175, 0.72])
    ax3.hist(err / true.mean() * 100, bins=22, color=C["ours"], edgecolor="white", lw=0.5)
    ax3.axvline(0, color="#b23b32", lw=0.8, ls="--")
    ax3.set_xlabel("相对残差 / %")
    ax3.set_ylabel("频数")
    F.panel_label(ax3, "(c)")
    F.paper_save(fig, OUT, "fig11_parity_residual")


def fig12():
    """已撤下：按 case_id 合并 3 次重复会把不同 run 的同 step 行相邻差分，产生假尖峰。
    同一内容改由 fig22 呈现（按 (case_id, run_id) 分组）。保留占位以免图号错位。"""
    raise SystemExit("fig12 已撤下，请用 fig22（执行器速率余量）")


def fig13():
    """来流方向的极坐标功率图（风玫瑰式）。"""
    data = rows(CASES)
    sel = [r for r in data if abs(f(r["yaw1"])) < 1e-6 and abs(f(r["pitch1"])) < 1e-6
           and abs(f(r["ambient_wind_speed_m_s"]) - 8.0) < 1e-6]
    agg = {}
    for r in sel:
        key = round(math.degrees(f(r["ambient_wind_direction_rad"])), 0)
        agg.setdefault(key, []).append((f(r["P1"]) + f(r["P2"]) + f(r["P3"])) / 1e3)
    th = np.radians(sorted(agg))
    val = np.array([st.mean(agg[k]) for k in sorted(agg)])
    th_c = np.append(th, th[0])
    val_c = np.append(val, val[0])

    fig = plt.figure(figsize=(2.9, 2.8))
    ax = fig.add_axes([0.17, 0.10, 0.74, 0.84], projection="polar")
    ax.plot(th_c, val_c, color=C["ours"], lw=1.2)
    ax.fill(th_c, val_c, color=C["ours"], alpha=0.18, lw=0)
    ax.set_theta_zero_location("E")
    ax.set_theta_direction(1)
    ax.set_xticks(np.radians([0, 90, 180, 270]))
    ax.set_xticklabels(["0°", "90°", "180°", "270°"], fontsize=7.5)
    # 径向轴从 0 起：否则 0°/180° 附近的低谷会被夸大成“掉到圆心”
    ax.set_ylim(0, 4000)
    ax.set_yticks([1000, 2000, 3000])
    ax.set_yticklabels(["1", "2", "3 MW"], fontsize=6.2)
    ax.tick_params(pad=1.5)
    ax.grid(color=C["grid"], lw=0.6)
    ax.spines["polar"].set_linewidth(0.8)
    F.paper_save(fig, OUT, "fig13_windrose")


def fig14():
    """口径自洽：三台机的反算 Cp 全部塌缩到同一条「桨距—Cp」曲线上。"""
    r = rows(CASES)[::2]
    pit, cp, ueff, tno = [], [], [], []
    for row in r:
        for i in (1, 2, 3):
            u = f(row[f"Ueff{i}"])
            if u < 0.6:
                continue
            pit.append(round(math.degrees(f(row[f"pitch{i}"]))))
            cp.append(f(row[f"P{i}"]) / (0.5 * RHO * A_ROTOR * u ** 3))
            ueff.append(u)
            tno.append(i)
    pit = np.array(pit, dtype=float)
    cp = np.array(cp)
    tno_col = np.array(tno)

    fig = plt.figure(figsize=(3.35, 2.85))
    ax = F.paper_axes(fig, [0.165, 0.175, 0.795, 0.755])
    # 三台机分别着色：若三色点落在同一条带上，说明反算口径在三台机间自洽
    for i, (col, mk) in enumerate(zip([C["ours"], C["alt"], C["acc"]], ["o", "s", "^"])):
        m = tno_col == i + 1
        ax.plot(pit[m], cp[m], mk, ms=3.4, color=col, mec="white", mew=0.4,
                alpha=0.85, ls="none", label=f"T{i + 1}")
    bx, med = [], []
    for b in sorted(set(pit)):
        v = cp[pit == b]
        if len(v) > 10:
            bx.append(b)
            med.append(np.median(v))
    ax.plot(bx, med, color="#222222", lw=0.9, zorder=1)
    ax.plot(bx, med, "o", ms=3.6, mfc="white", mec="#222222", mew=0.9, zorder=4,
            ls="none", label="分箱中位数")
    ax.axhline(0.457, color=C["warn"], lw=0.9, ls="--")
    ax.text(5.6, 0.474, "Cp,max = 0.457", color=C["warn"], fontsize=6.8, ha="left")
    ax.set_xlabel("集体桨距 / (°)")
    ax.set_ylabel("反算功率系数")
    ax.set_xlim(-0.8, 14.8)
    ax.set_ylim(0, 0.52)
    ax.legend(loc="lower left", fontsize=6.4, handletextpad=0.4, labelspacing=0.28,
              borderaxespad=0.3, ncol=2)
    F.paper_save(fig, OUT, "fig14_cp_pitch")


def fig15():
    """两机串列偏航优化（8 月历史工作，FLORIS 合成数据）。"""
    one = rows(VIZ / "cases.csv")
    yaw = np.array([f(r["yaw_1"]) for r in one])
    o = np.argsort(yaw)
    yaw = yaw[o]
    # viz/cases*.csv 里的功率已是 kW，不用再除 1e3
    p1 = np.array([f(r["power_1"]) for r in one])[o]
    p2 = np.array([f(r["power_2"]) for r in one])[o]
    pt = np.array([f(r["power_total"]) for r in one])[o]

    fig = plt.figure(figsize=(6.9, 2.5))
    ax1 = F.paper_axes(fig, [0.075, 0.20, 0.365, 0.70])
    ax1.plot(yaw, p1, color=C["ours"], marker="o", ms=2.6, lw=1.1, label="上游 P1")
    ax1.plot(yaw, p2, color=C["alt"], marker="s", ms=2.6, lw=1.1, label="下游 P2")
    ax1.plot(yaw, pt, color="#222222", marker="^", ms=2.6, lw=1.3, label="合计")
    i_best = int(np.argmax(pt))
    ax1.plot(yaw[i_best], pt[i_best], "o", ms=6.5, mfc="white", mec=C["warn"], mew=1.1, zorder=5)
    ax1.annotate(f"最优 {yaw[i_best]:.0f}°", (yaw[i_best], pt[i_best]),
                 textcoords="offset points", xytext=(0, -16), fontsize=6.8, ha="center",
                 color=C["warn"])
    ax1.set_xlabel("统一偏航角 / (°)")
    ax1.set_ylabel("机组功率 / kW")
    ax1.set_xlim(-33, 33)
    ax1.set_ylim(300, 3000)
    ax1.legend(loc="upper left", fontsize=6.4, ncol=3, columnspacing=0.7,
               handlelength=1.5, borderaxespad=0.25)

    multi = rows(VIZ / "cases_multi.csv")
    us = sorted({f(r["U_inf"]) for r in multi})
    ys = sorted({f(r["yaw_1"]) for r in multi})
    G = np.full((len(us), len(ys)), np.nan)
    for r in multi:
        G[us.index(f(r["U_inf"])), ys.index(f(r["yaw_1"]))] = f(r["gain_pct"])
    ax2 = F.paper_axes(fig, [0.575, 0.20, 0.26, 0.70])
    im = ax2.pcolormesh(ys, us, G, cmap="YlGnBu", shading="nearest")
    cb = fig.colorbar(im, ax=ax2, pad=0.02, fraction=0.05)
    cb.set_label("相对对齐的总增益 / %", fontsize=7)
    cb.ax.tick_params(labelsize=6.2)
    ax2.set_xlabel("统一偏航角 / (°)")
    ax2.set_ylabel("来流风速 / (m/s)")
    ax2.set_yticks(us)
    ax2.set_xticks([-30, -15, 0, 15, 30])
    F.panel_label(ax1, "(a)")
    F.panel_label(ax2, "(b)")
    F.paper_save(fig, OUT, "fig15_tandem_yaw")


def fig16():
    """3×3 阵列：统一偏航 vs 逐台贪心（FLORIS 合成数据）。"""
    one = rows(VIZ / "cases_array.csv")
    yaw = np.array([f(r["yaw_upstream"]) for r in one])
    o = np.argsort(yaw)
    yaw, tot = yaw[o], np.array([f(r["power_total"]) for r in one])[o]   # 已是 kW
    base = float(tot[yaw == 0][0]) if (yaw == 0).any() else tot.min()
    greedy = json.loads((VIZ / "array_independent_result.json").read_text(encoding="utf-8"))

    fig = plt.figure(figsize=(6.9, 2.6))
    ax1 = F.paper_axes(fig, [0.075, 0.20, 0.33, 0.70])
    ax1.plot(yaw, tot, color=C["ours"], marker="o", ms=2.8, lw=1.1)
    ax1.axhline(base, color=C["base"], lw=0.9, ls="--")
    ax1.text(-29, base + 90, f"对齐 {base:.0f} kW", fontsize=6.4, color=C["base"])
    i = int(np.argmax(tot))
    ax1.plot(yaw[i], tot[i], "o", ms=6.0, mfc="white", mec=C["warn"], mew=1.1, zorder=5)
    ax1.set_xlabel("统一偏航角 / (°)")
    ax1.set_ylabel("全场总功率 / kW")
    ax1.set_xlim(-33, 33)
    ax1.set_ylim(7800, 10600)

    ax2 = F.paper_axes(fig, [0.575, 0.20, 0.40, 0.70])
    names = ["对齐", "统一 30°", "前两排 30°", "逐台贪心"]
    vals = [greedy["power_none"], greedy["power_unified"],
            greedy["power_row2_30"], greedy["power_independent"]]
    cols = [C["base"], C["light"], C["acc"], C["ours"]]
    bars = ax2.bar(range(4), np.array(vals), color=cols, edgecolor="#333333",
                   lw=0.6, width=0.62)
    for b, v in zip(bars, vals):
        ax2.text(b.get_x() + b.get_width() / 2, v + 90,
                 f"{v / 1e3:.1f} MW", ha="center", fontsize=6.4)
        if v != vals[0]:
            ax2.text(b.get_x() + b.get_width() / 2, v + 330,
                     f"+{(v / vals[0] - 1) * 100:.1f}%", ha="center", fontsize=6.2,
                     color=C["warn"])
    ax2.set_xticks(range(4))
    ax2.set_xticklabels(names, fontsize=6.6)
    ax2.set_ylabel("全场总功率 / kW")
    ax2.set_ylim(7500, 11200)
    F.panel_label(ax1, "(a)")
    F.panel_label(ax2, "(b)")
    F.paper_save(fig, OUT, "fig16_array_yaw")


def fig17():
    """尾流模态分解：能量占比与前两阶模态。"""
    d = np.load(VIZ / "pod_results" / "pod_data.npz")
    frac = d["energy_frac"][:6] * 100
    cum = d["energy_cum"][:6] * 100
    x, y = d["x"], d["y"]
    modes = d["modes"]

    fig = plt.figure(figsize=(6.9, 2.4))
    ax1 = F.paper_axes(fig, [0.065, 0.20, 0.19, 0.68])
    idx = np.arange(1, 7)
    ax1.bar(idx, frac, color=C["ours"], edgecolor="white", lw=0.5, width=0.62)
    ax1.set_xlabel("模态阶次")
    ax1.set_ylabel("能量占比 / %")
    ax1.set_xticks(idx)
    ax1.set_ylim(0, 88)
    ax1.text(3, 80, "前两阶 97.97 %", fontsize=6.4, ha="left")
    F.panel_label(ax1, "(a)")

    for k in range(2):
        ax = F.paper_axes(fig, [0.325 + k * 0.335, 0.20, 0.26, 0.68])
        lim = float(np.percentile(np.abs(modes[k]), 99))
        im = ax.pcolormesh(x, y, modes[k], cmap="RdBu_r", vmin=-lim, vmax=lim,
                           shading="nearest")
        ax.set_xlabel("下游距离 x / m")
        ax.set_yticks([-200, 0, 200])
        if k == 0:
            ax.set_ylabel("横向距离 y / m")
        ax.set_title(f"模态 {k + 1}（{frac[k]:.1f} %）", fontsize=8, pad=3)
        cb = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.05)
        cb.ax.tick_params(labelsize=6)
        F.panel_label(ax, "(" + "bc"[k] + ")")
    F.paper_save(fig, OUT, "fig17_pod_modes")


def fig18():
    """尾流水平切片：对齐 vs 统一偏航 +25°。"""
    def field(name):
        d = np.load(VIZ / "fields" / name)
        return d["x"], d["y"], d["u"]

    fig = plt.figure(figsize=(6.9, 2.45))
    cases = (("case_0007.npz", "对齐 0°"), ("case_0012.npz", "统一偏航 +25°"))
    vmin, vmax = 4.6, 8.0
    levels = np.linspace(vmin, vmax, 15)
    xs, ys, us = [], [], []
    for _fn, _label in cases:
        _x, _y, _u = field(_fn)
        xs.append(_x)
        ys.append(_y)
        us.append(np.clip(_u, vmin, vmax))
    for k, (fn, label) in enumerate(cases):
        x, y, u = xs[k], ys[k], us[k]
        ax = F.paper_axes(fig, [0.07 + k * 0.44, 0.20, 0.345, 0.70])
        im = ax.contourf(x, y, u, levels=levels, cmap="viridis", extend="both")
        for tx, tag in ((0.0, "T1"), (630.0, "T2")):
            ax.plot(tx, 0, "^", ms=4.6, mfc="white", mec="#222222", mew=0.7)
            ax.text(tx, 42, tag, fontsize=6.4, ha="center", color="#222222")
        ax.set_xlabel("下游距离 x / m")
        if k == 0:
            ax.set_ylabel("横向距离 y / m")
        ax.set_xlim(-200, 900)
        ax.set_ylim(-300, 300)
        ax.set_title(label, fontsize=8, pad=3)
        F.panel_label(ax, "(" + "ab"[k] + ")")
    cb = fig.colorbar(im, ax=fig.axes[-2:], pad=0.012, fraction=0.022)
    cb.set_label("轴向速度 / (m/s)", fontsize=7)
    cb.ax.tick_params(labelsize=6.2)
    cb.set_ticks([5, 6, 7, 8])
    cb.ax.set_yticklabels(["5", "6", "7", "8"])
    F.paper_save(fig, OUT, "fig18_wake_slices")


def fig19():
    """六工况的功率跟踪过程（四种控制器）。"""
    tr = rows(RANDOM / "test" / "trajectories.csv")
    ctrls = [("initial", "初始策略", "#d0d0d0", ":"), ("p", "P 控制", "#a0a0a0", "-."),
             ("pi", "PI 控制", "#4d4d4d", "--"), ("selected", "训练后", C["ours"], "-")]
    fams = [("gust", "阵风"), ("stationary", "平稳"), ("ramp", "慢变")]

    fig = plt.figure(figsize=(6.9, 2.65))
    for k, (fam, flabel) in enumerate(fams):
        ax = F.paper_axes(fig, [0.07 + k * 0.325, 0.255, 0.265, 0.625])
        case = f"test_{fam}_0_pitch0.025"
        tgt = None
        for key, label, col, ls in ctrls:
            rs = [r for r in tr if r["controller"] == key and r["case_id"] == case]
            if not rs:
                continue
            rs.sort(key=lambda r: int(r["step"]))
            tgt = tgt or f(rs[0]["target_w"]) / 1e6      # 目标单位是 MW
            ax.plot([int(r["step"]) for r in rs], [f(r["farm_power_w"]) / 1e3 for r in rs],
                    color=col, ls=ls, lw=1.1 if ls == "-" else 0.8,
                    zorder=4 if ls == "-" else 2, label=label)
        ax.axhline(tgt * 1e3, color=C["warn"], lw=0.8, ls=":")
        ax.set_xlabel("控制步")
        if k == 0:
            ax.set_ylabel("全场功率 / kW")
        ax.set_title(f"{flabel}　目标 {tgt:.1f} MW", fontsize=7.6, pad=3)
        ax.set_ylim(1200, 5200)
        ax.set_yticks([2000, 3000, 4000, 5000])
        F.panel_label(ax, "(" + "abc"[k] + ")")
    handles, labels_ = fig.axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_, loc="lower center", ncol=4, fontsize=6.6,
               frameon=False, bbox_to_anchor=(0.5, -0.01), handlelength=1.9,
               columnspacing=1.4)
    F.paper_save(fig, OUT, "fig19_tracking_cases")


def _strategy_of(r):
    """把一行工况归到四种偏航策略之一（只取零桨距行）。"""
    y1, y2 = round(math.degrees(f(r["yaw1"]))), round(math.degrees(f(r["yaw2"])))
    if y1 == 0 and y2 == 0:
        return "align"
    if y1 == 20 and y2 == -20:
        return "stag"
    if y1 == y2:
        return f"u{y1:+d}"
    return None


def fig20():
    """偏航策略的选择地图：只有来流接近串列轴时，偏航才真的换来增益。"""
    data = [r for r in rows(CASES) if abs(f(r["pitch1"])) < 1e-9]
    by: dict[tuple, list[float]] = {}
    for r in data:
        s = _strategy_of(r)
        if s is None:
            continue
        d = round(math.degrees(f(r["ambient_wind_direction_rad"])))
        by.setdefault((d, round(f(r["ambient_wind_speed_m_s"])), s), []).append(
            f(r["P1"]) + f(r["P2"]) + f(r["P3"]))

    dirs = sorted({k[0] for k in by})
    spds = sorted({k[1] for k in by})
    # 先在「每个方向」上各算各的增益，再折叠成 δ（同一 δ 可能对应左右两侧的对称方向，
    # 取其中更高的一侧；不能先平均功率，否则两边最优策略不同会被抹平）
    per_dir: dict[tuple[int, float], tuple[str, float]] = {}
    for d in dirs:
        for ws in spds:
            vals = {s: st.mean(v) for (dd, ww, s), v in by.items() if dd == d and ww == ws}
            if "align" not in vals or len(vals) < 2:
                continue
            b = max(vals, key=vals.get)
            per_dir[(d, ws)] = (b, (vals[b] / vals["align"] - 1) * 100)
    deltas = sorted({min(abs(d), abs(d - 180), abs(d - 360)) for d in dirs})
    G = np.full((len(spds), len(deltas)), np.nan)
    best = {}
    for i, ws in enumerate(spds):
        for j, dl in enumerate(deltas):
            cand = [(g, s) for (d, w) in per_dir if w == ws
                    and min(abs(d), abs(d - 180), abs(d - 360)) == dl
                    for s, g in [per_dir[(d, w)]][0:1]]
            if not cand:
                continue
            g, s = max(cand)
            G[i, j] = g
            best[(dl, ws)] = s

    fig = plt.figure(figsize=(6.9, 2.7))
    ax1 = F.paper_axes(fig, [0.075, 0.215, 0.30, 0.68])
    im = ax1.pcolormesh(deltas, spds, G, cmap="YlGnBu", vmin=0, vmax=10, shading="nearest")
    for i, ws in enumerate(spds):
        for j, dl in enumerate(deltas):
            v = G[i, j]
            if np.isfinite(v):
                ax1.text(dl, ws, f"{v:.0f}", ha="center", va="center", fontsize=5.6,
                         color="white" if v > 6 else "#333333")
    ax1.set_xlabel("与串列轴的夹角 δ / (°)")
    ax1.set_ylabel("来流风速 / (m/s)")
    ax1.set_xticks(deltas)
    ax1.set_yticks(spds)
    cb = fig.colorbar(im, ax=ax1, pad=0.03, fraction=0.05)
    cb.set_label("最优策略增益 / %", fontsize=7)
    cb.ax.tick_params(labelsize=6.2)
    F.panel_label(ax1, "(a)")

    ax2 = F.paper_axes(fig, [0.60, 0.215, 0.29, 0.68])
    labels = {"align": "对齐（偏航无益）", "u+10": "统一 +10°", "u-10": "统一 −10°",
              "u+20": "统一 +20°", "stag": "错列 ±20°"}
    cols = {"align": C["base"], "u+10": "#9ec5e0", "u-10": C["alt"],
            "u+20": "#d8b4a0", "stag": C["acc"]}
    ws0 = 8.0 if 8.0 in spds else spds[len(spds) // 2]
    xs = np.arange(len(deltas))
    vals = [G[spds.index(ws0), j] for j in range(len(deltas))]
    bars = ax2.bar(xs, vals, color=[cols[best[(dl, ws0)]] for dl in deltas],
                   edgecolor="#333333", lw=0.6, width=0.68)
    for x, v, dl in zip(xs, vals, deltas):
        if v > 0.5:
            ax2.text(x, v + 0.25, f"{v:.0f}", ha="center", fontsize=6.0)
    ax2.set_xticks(xs)
    ax2.set_xticklabels([f"{d:.0f}" for d in deltas], fontsize=7)
    ax2.set_xlabel("与串列轴的夹角 δ / (°)")
    ax2.set_ylabel(f"最优增益 / %（{ws0:.0f} m/s）")
    ax2.set_ylim(0, 12)
    ax2.set_xlim(-0.65, len(deltas) - 0.35)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=cols[k], edgecolor="#333333", lw=0.6)
               for k in ("u+10", "u-10", "u+20", "stag", "align")]
    ax2.legend(handles, [labels[k] for k in ("u+10", "u-10", "u+20", "stag", "align")],
               loc="upper right", fontsize=6.0, handlelength=1.1, labelspacing=0.25)
    F.panel_label(ax2, "(b)")
    F.paper_save(fig, OUT, "fig20_yaw_strategy_map")
    print("    δ 档位：", deltas)
    for ws in spds:
        row = " ".join(f"δ{dl:.0f}:{G[spds.index(ws), deltas.index(dl)]:.0f}%"
                       for dl in deltas if np.isfinite(G[spds.index(ws), deltas.index(dl)]))
        print(f"    {ws:.0f} m/s → {row}")


def fig21():
    """四个指标逐场对比：赢什么、输什么，一场一格。"""
    def avg(ctrl):
        acc: dict[str, list[dict]] = {}
        for r in rows(RANDOM / "test" / "metrics.csv"):
            if r["controller"] != ctrl or r["family"] == "low_wind_stress":
                continue
            acc.setdefault(r["case_id"], []).append(r)
        out = {}
        for cid, rs in acc.items():
            row = dict(rs[0])
            for k in ("rmse_w", "mae_w", "tail_rmse_w", "mean_shortfall_w"):
                row[k] = str(st.mean(f(x[k]) for x in rs))
            out[cid] = row
        return out

    data = avg("pi")
    sel = avg("selected")
    cases = sorted(data)
    keys = [("rmse_w", "RMSE"), ("mae_w", "MAE"),
            ("tail_rmse_w", "尾段 RMSE"), ("mean_shortfall_w", "平均缺额")]
    M = np.full((len(keys), len(cases)), np.nan)
    for i, (k, _lab) in enumerate(keys):
        for j, c in enumerate(cases):
            M[i, j] = (f(sel[c][k]) / f(data[c][k]) - 1) * 100
    order = np.argsort(M[0])
    M = M[:, order]
    cases = [cases[i] for i in order]
    fam = [data[c]["family"] for c in cases]

    fig = plt.figure(figsize=(6.9, 2.9))
    ax = F.paper_axes(fig, [0.085, 0.36, 0.82, 0.56])
    lim = 40
    im = ax.pcolormesh(np.arange(len(cases) + 1) - 0.5, np.arange(len(keys) + 1) - 0.5,
                       np.clip(M, -lim, lim), cmap="RdBu_r", vmin=-lim, vmax=lim,
                       shading="flat")
    for j, c in enumerate(cases):
        for i in range(len(keys)):
            v = M[i, j]
            if abs(v) > 8:
                ax.text(j, i, f"{v:+.0f}", ha="center", va="center", fontsize=5.4,
                        color="white" if abs(v) > 25 else "#222222")
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([lab for _k, lab in keys], fontsize=7)
    ax.set_xticks(range(len(cases)))
    short = [("阵" if fm == "gust" else "慢" if fm == "ramp" else "稳")
             + c.split("_")[-2] for c, fm in zip(cases, fam)]
    ax.set_xticklabels(short, fontsize=6.4)
    ax.set_xlabel("测试场（族 + 序号，按 RMSE 变化排序）", fontsize=7.5)
    cb = fig.colorbar(im, ax=ax, pad=0.012, fraction=0.025)
    cb.set_label("训练后相对 PI 的变化 / %（负 = 更好）", fontsize=6.6)
    cb.ax.tick_params(labelsize=6)
    F.paper_save(fig, OUT, "fig21_metric_heatmap")
    print(f"    RMSE 更好 {int((M[0] < 0).sum())}/{len(cases)}；MAE 更好 {int((M[1] < 0).sum())}；"
          f"尾段更好 {int((M[2] < 0).sum())}；缺额更好 {int((M[3] < 0).sum())}")


def fig22():
    """执行器速率余量：三个通道离配置上限还有多远（按 run 逐步差分，不与限幅比较错位）。"""
    traj = [r for r in rows(RANDOM / "test" / "trajectories.csv")
            if r["controller"] == "selected"]
    chans = [("heading_1_rad", "偏航", 0.005, C["ours"]),
             ("pitch_1", "桨距", 0.00872664626, C["alt"]),
             ("speed_1", "转速", 0.1, C["acc"])]
    by: dict[tuple, list[dict]] = {}
    for r in traj:
        by.setdefault((r["case_id"], r["run_id"]), []).append(r)

    fig = plt.figure(figsize=(6.9, 2.5))
    ax1 = F.paper_axes(fig, [0.075, 0.20, 0.30, 0.70])
    for i, (col, name, lim, color) in enumerate(chans):
        vals = []
        for _k, rs in by.items():
            rs.sort(key=lambda r: int(r["step"]))
            vals.extend(np.abs(np.diff([f(r[col]) for r in rs])) / lim)
        vals = np.array(vals)
        parts = ax1.violinplot([vals], positions=[i], widths=0.62, showextrema=False)
        for pc in parts["bodies"]:
            pc.set_facecolor(color)
            pc.set_alpha(0.5)
            pc.set_edgecolor("#333333")
            pc.set_linewidth(0.6)
        ax1.hlines(np.median(vals), i - 0.2, i + 0.2, color="#111111", lw=1.0)
        ax1.text(i, np.percentile(vals, 99.5) * 1.25, f"最大 {vals.max():.2f}",
                 ha="center", fontsize=6.2)
    ax1.axhline(1.0, color=C["warn"], lw=1.0, ls="--")
    ax1.text(2.45, 1.08, "上限", color=C["warn"], fontsize=6.8, ha="right")
    ax1.set_xticks(range(3))
    ax1.set_xticklabels([c[1] for c in chans])
    ax1.set_ylim(0, 1.35)
    ax1.set_ylabel("实际步进 ÷ 配置上限")
    F.panel_label(ax1, "(a)")

    ax2 = F.paper_axes(fig, [0.485, 0.20, 0.47, 0.70])
    for col, name, lim, color in chans:
        vals = []
        for _k, rs in by.items():
            rs.sort(key=lambda r: int(r["step"]))
            vals.extend(np.abs(np.diff([f(r[col]) for r in rs])) / lim)
        vals = np.sort(np.array(vals))
        ax2.plot(vals, np.arange(1, len(vals) + 1) / len(vals), color=color, lw=1.2, label=name)
    ax2.axvline(1.0, color=C["warn"], lw=1.0, ls="--")
    ax2.set_xlim(0, 1.15)
    ax2.set_ylim(0, 1.02)
    ax2.set_xlabel("实际步进 ÷ 配置上限")
    ax2.set_ylabel("累积概率")
    ax2.legend(loc="upper left", fontsize=6.8, handlelength=1.8)
    ax2.text(1.0, 0.12, " 上限", color=C["warn"], fontsize=6.6, rotation=90, va="bottom", ha="right")
    F.panel_label(ax2, "(b)")
    F.paper_save(fig, OUT, "fig22_actuator_margin")


def fig23():
    """盘面速度逐点对比：k-ω vs k-ε（替代极坐标云图）。"""
    fig = plt.figure(figsize=(6.9, 2.55))
    names = ["T1", "T2", "T3"]
    for k in range(3):
        _, _t, a = _disk("k-omega_data", k + 1, "U_forward_m_s")
        _, _t2, b = _disk("k-epsilon_data", k + 1, "U_forward_m_s")
        x, y = a.ravel(), b.ravel()
        ok = np.isfinite(x) & np.isfinite(y)
        x, y = np.clip(x[ok], 0, 12), np.clip(y[ok], 0, 12)
        ax = F.paper_axes(fig, [0.07 + k * 0.245, 0.20, 0.21, 0.70])
        ax.plot([0, 12], [0, 12], color="#888888", lw=0.8, ls="--")
        ax.scatter(x, y, s=3.2, color=C["ours"], alpha=0.45, linewidths=0)
        mae = np.mean(np.abs(y - x))
        ax.text(0.05, 0.95, f"MAE {mae:.2f} m/s\n偏差 {(y.mean() / x.mean() - 1) * 100:+.1f} %",
                transform=ax.transAxes, va="top", fontsize=6.2)
        ax.set_xlim(0, 12)
        ax.set_ylim(0, 12)
        ax.set_xticks([0, 4, 8, 12])
        ax.set_yticks([0, 4, 8, 12])
        ax.set_xlabel("k-ω SST 盘面速度 / (m/s)", fontsize=7.2)
        if k == 0:
            ax.set_ylabel("k-ε 盘面速度 / (m/s)")
        ax.set_title(names[k], fontsize=8, pad=3)
        F.panel_label(ax, "(" + "abc"[k] + ")")
    F.paper_save(fig, OUT, "fig23_disk_scatter")


FIGURES = {
    "fig01": ("设计空间热图（风速×风向 / 风速×湍流强度）", fig01),
    "fig02": ("五种偏航策略的功率曲线", fig02),
    "fig03": ("湍流强度敏感性（含放大）", fig03),
    "fig04": ("尾流中心线速度与两模型偏差", fig04),
    "fig05": ("三台机盘面速度（极坐标）", fig05),
    "fig06": ("盘面湍流强度径向分布", fig06),
    "fig07": ("四控制器 × 三来流族 RMSE 箱线", fig07),
    "fig08": ("跟踪误差累积分布", fig08),
    "fig09": ("逐场配对散点（含差值边缘分布）", fig09),
    "fig10": ("训练收敛与参数冻结", fig10),
    "fig11": ("预测-真值一致性 / 残差分布", fig11),
    "fig13": ("来流方向极坐标功率图", fig13),
    "fig14": ("反算 Cp 与桨距的关系", fig14),
    "fig15": ("两机串列偏航优化（功率与增益矩阵）", fig15),
    "fig16": ("3×3 阵列统一偏航与逐台贪心", fig16),
    "fig17": ("尾流模态分解（能量与前两阶模态）", fig17),
    "fig18": ("尾流水平切片：对齐 vs 偏航 25°", fig18),
    "fig19": ("六工况功率跟踪过程", fig19),
    "fig20": ("偏航策略选择地图（方向×风速）", fig20),
    "fig21": ("四指标逐场对比热图", fig21),
    "fig22": ("执行器速率余量（三通道）", fig22),
    "fig23": ("盘面速度逐点对比（两模型）", fig23),
}


def main(argv):
    if "--list" in argv:
        for k, (desc, _fn) in FIGURES.items():
            print(f"  {k}  {desc}")
        return 0
    todo = [a for a in argv if not a.startswith("-")] or list(FIGURES)
    fam = F.use_serif(ROOT)
    print(f"字体: {plt.rcParams['font.family']}  (中文族: {fam})")
    for key in todo:
        if key not in FIGURES:
            print(f"  ?? 未知图号 {key}")
            continue
        print(f"[{key}] {FIGURES[key][0]}")
        FIGURES[key][1]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
