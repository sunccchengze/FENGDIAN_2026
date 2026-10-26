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
    """执行器通道：实际步进的分布与配置上限。"""
    traj = [r for r in rows(RANDOM / "test" / "trajectories.csv") if r["controller"] == "selected"]
    by = {}
    for r in traj:
        by.setdefault(r["case_id"], []).append(r)
    chans = [("heading_1_rad", "偏航", 0.005, C["ours"]),
             ("pitch_1", "桨距", 0.00872664626, C["alt"]),
             ("speed_1", "转速", 0.1, C["acc"])]

    fig = plt.figure(figsize=(3.35, 2.7))
    ax = F.paper_axes(fig, [0.17, 0.19, 0.78, 0.73])
    data, ticks, labels = [], [], []
    for i, (col, name, lim, color) in enumerate(chans):
        vals = []
        for _cid, rs in by.items():
            rs.sort(key=lambda r: int(r["step"]))
            v = np.abs(np.diff([f(r[col]) for r in rs]))
            vals.extend(v / lim)
        vals = np.array(vals)
        parts = ax.violinplot([vals], positions=[i], widths=0.62, showextrema=False)
        for pc in parts["bodies"]:
            pc.set_facecolor(color)
            pc.set_alpha(0.55)
            pc.set_edgecolor("#333333")
            pc.set_linewidth(0.6)
        ax.hlines(np.median(vals), i - 0.22, i + 0.22, color="#111111", lw=1.0)
        ax.hlines(1.0, i - 0.3, i + 0.3, color=C["warn"], lw=1.2, ls="--")
        data.append(vals)
        ticks.append(i)
        labels.append(name)
    ax.set_yscale("log")
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)
    ax.set_ylabel("实际步进 ÷ 配置上限")
    ax.text(2.42, 1.15, "上限", color=C["warn"], fontsize=6.8, ha="right")
    F.paper_save(fig, OUT, "fig12_actuator_violin")


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
    "fig12": ("执行器步进分布与上限", fig12),
    "fig13": ("来流方向极坐标功率图", fig13),
    "fig14": ("反算 Cp 与桨距的关系", fig14),
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
