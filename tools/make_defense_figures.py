#!/usr/bin/env python3
"""生成中期答辩用的图与动图（16:9，1920x1080）。

设计原则
--------
1. **只读**仓库既有数据，不重跑实验、不改实验目录。
2. 每张图右下角固定写「数据来源 + 口径」，任何上屏数字都能倒查。
3. 合成标签 / 模拟真值 / 实测 三类来源用不同颜色角标区分，避免答辩时口误。
4. 中文标题不加粗（字重只有一档），用「加大字号 + 收紧行距」制造层级。

用法：
    python3 tools/make_defense_figures.py             # 全部重画
    python3 tools/make_defense_figures.py g07 g11     # 只画指定编号
    python3 tools/make_defense_figures.py gif         # 只重画动图
输出：docs/defense/assets/generated/
"""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "defense" / "assets" / "generated"
GIF = ROOT / "docs" / "defense" / "assets" / "animated"
FONT = Path.home() / ".fonts" / "NotoSansCJKsc-Regular.otf"

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

# 数据来源角标：三类证据用三种颜色，答辩时口头也必须说同一个词
TAG_SIM = ("模拟真值 · FLORIS", BLUE)
TAG_SYN = ("合成标签 · 非物理精度", AMBER)
TAG_OBS = ("实测记录", GREEN)
TAG_CFD = ("CFD 后处理 · 非实测", PURPLE)
TAG_UI = ("界面演示 · 非实时控制", BLUE)


def use_cjk() -> None:
    from matplotlib import font_manager as fm

    if FONT.exists():
        fm.fontManager.addfont(str(FONT))
        plt.rcParams["font.family"] = fm.FontProperties(fname=str(FONT)).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 15


def b(t, color=INK, lw=0.85):
    """伪粗体：同色描边，弥补单字重字体。"""
    t.set_path_effects([pe.withStroke(linewidth=lw, foreground=color)])
    return t


def frame(fig, title, subtitle="", footer="", kicker="", tag=None):
    fig.patch.set_facecolor(BG)
    if kicker:
        fig.text(0.045, 0.955, kicker, color=MUTED, fontsize=13.5, va="top")
    b(fig.text(0.045, 0.918, title, color=INK, fontsize=30, va="top"), INK, 1.1)
    if subtitle:
        fig.text(0.045, 0.848, subtitle, color=GRAY, fontsize=15.5, va="top")
    fig.add_artist(Rectangle((0.045, 0.905), 0.055, 0.0035,
                             transform=fig.transFigure, facecolor=BLUE, edgecolor="none"))
    if footer:
        # 右下角有口径角标（从 x=0.80 起），脚注必须在此之前折行，否则两段字会叠在一起。
        # 注意：textwrap 数的是「字符数」，中文一个字占两个字宽，必须按显示宽度折。
        lines, cur, cur_w, limit = [], "", 0, 132   # 132 半角单位 ≈ 66 个汉字
        for ch in str(footer):
            w = 1 if ord(ch) < 128 else 2
            if cur_w + w > limit and cur:
                lines.append(cur)
                cur, cur_w = "", 0
            cur += ch
            cur_w += w
        if cur:
            lines.append(cur)
        fig.text(0.045, 0.038, "\n".join(lines), color=MUTED, fontsize=11.5,
                 va="bottom", linespacing=1.45)
    fig.add_artist(Rectangle((0.045, 0.088), 0.760, 0.0014,
                             transform=fig.transFigure, facecolor=LINE, edgecolor="none"))
    if tag:
        text, color = tag
        fig.add_artist(Rectangle((0.80, 0.030), 0.155, 0.042,
                                 transform=fig.transFigure, facecolor=color, alpha=0.10,
                                 edgecolor="none"))
        fig.text(0.877, 0.051, text, color=color, fontsize=11.5, ha="center", va="center")


def clean(ax, grid_axis=None):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    if grid_axis:
        ax.grid(axis=grid_axis, color=LINE, lw=0.8)
        ax.set_axisbelow(True)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    fig.savefig(path, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"  {name}.png  {path.stat().st_size / 1024:.0f} KB")


def card(ax, x, y, w, h, title, value, note="", color=INK, fill=PANEL):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012",
                                facecolor=fill, edgecolor=LINE, lw=1.2))
    ax.text(x + 0.03 * w, y + h * 0.80, title, fontsize=13, color=GRAY)
    b(ax.text(x + 0.03 * w, y + h * 0.50, value, fontsize=26, color=color), color)
    if note:
        ax.text(x + 0.03 * w, y + h * 0.16, note, fontsize=11.5, color=GRAY)


# ── 数据 ────────────────────────────────────────────────────────────────
ORACLE = ROOT / "docs/research/oracle/floris_gch_oracle_v1.json"
RANDOM = ROOT / "optimization_control/experiments/20261022_random_wind_training"
CURRIC = ROOT / "optimization_control/experiments/20261022_wind_pinn_curriculum"
INTEG = ROOT / "optimization_control/experiments/20261022_wind_pinn_integration"
SURROGATE = ROOT / "optimization_control/experiments/20260807_surrogate_baseline"
FLORIS_DIR = ROOT / "materials/袁夫达/20260808_FLORIS数据生成/extracted"
FLORIS_TRAIN = FLORIS_DIR / "output_gch/training_data_gch.csv"
BUILD_REPORT = (
    ROOT / "materials/厉今飞/20261021_PINN十二输入交付/2026_1021"
    / "PINNs_multi_turbine_wake_simulation-outputchange/OutputChange/iochanged_9ms/build_report.json"
)
SHOT = ROOT / "docs/research/img"


def oracle():
    return json.loads(ORACLE.read_text(encoding="utf-8"))


def rows(path):
    with Path(path).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_metrics():
    return rows(RANDOM / "test/metrics.csv")


def fam_mean(data, family, controller):
    vals = [float(r["rmse_w"]) / 1000 for r in data
            if r["family"] == family and r["controller"] == controller]
    return st.mean(vals) if vals else float("nan")


# ── g01 尾流损失 ────────────────────────────────────────────────────────
def g01():
    d = oracle()["tandem3"]["none"]
    p = d["p_kW"]
    solo, total = p[0], sum(p)
    ideal = solo * 3
    loss = 1 - total / ideal

    fig = plt.figure(figsize=FS)
    frame(fig, "串列布局的尾流损失：三台机合计只有单机功率的 51%",
          "1×3 串列，间距 632 m（5.02D），来流 8 m/s、均匀入口、零偏航"
          "　｜　同期外场：未控制尾流损失约 4%–20%（Simley et al., WES 9, 219–234, 2024）",
          "数据来源：floris_gch_oracle_v1.json（tandem3.none，FLORIS 4.6.6 GCH）"
          "　｜　首台机功率作「无尾流单机功率」代理　｜　左图为本场景模拟值，不与其他场站年值直接比较",
          "第 2 页 · 研究背景", TAG_SIM)

    ax = fig.add_axes([0.065, 0.175, 0.40, 0.56])
    x = np.arange(3)
    ax.bar(x - 0.19, [ideal / 3] * 3, 0.36, color=LINE, label="无尾流单机功率")
    ax.bar(x + 0.19, p, 0.36, color=BLUE, label="本布局实际功率")
    for i, (a, v) in enumerate(zip([ideal / 3] * 3, p)):
        ax.text(i - 0.19, a + 45, f"{a:.0f}", ha="center", fontsize=12.5, color=GRAY)
        b(ax.text(i + 0.19, v + 45, f"{v:.0f}", ha="center", fontsize=15, color=INK))
        if i:
            ax.text(i + 0.19, v / 2, f"−{100 * (1 - v / a):.0f}%", ha="center",
                    color="white", fontsize=15)
    ax.set_xticks(x, ["T01 上游", "T02 中游", "T03 下游"])
    ax.set_ylim(0, 2350)
    ax.set_ylabel("单机功率 / kW")
    b(ax.set_title("逐台功率", loc="left", fontsize=16.5, color=INK), INK, 0.7)
    ax.legend(frameon=False, loc="upper center", ncol=2, fontsize=12.5,
              bbox_to_anchor=(0.5, 1.02), handlelength=1.4, columnspacing=1.6)
    clean(ax, "y")

    bx = fig.add_axes([0.52, 0.175, 0.44, 0.56])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    bx.add_patch(FancyBboxPatch((0.02, 0.62), 0.96, 0.30, boxstyle="round,pad=0.02",
                                facecolor=PANEL, edgecolor=LINE, lw=1.3))
    bx.text(0.5, 0.845, f"全场  {ideal:.0f} kW  →  {total:.0f} kW",
            ha="center", va="center", fontsize=21, color=GRAY)
    b(bx.text(0.5, 0.705, f"本场景模拟损失 −{loss * 100:.1f}%", ha="center", va="center",
              fontsize=27, color=RED), RED, 1.0)
    bx.add_patch(FancyArrowPatch((0.10, 0.52), (0.90, 0.52), arrowstyle="-|>",
                                 mutation_scale=26, color=MUTED, lw=2))
    bx.text(0.5, 0.42, "机位固定、来流均匀时，这个差额全部来自尾流",
            ha="center", fontsize=14.5, color=GRAY)
    bx.text(0.5, 0.22,
            "口径提醒：这是单一场景的 FLORIS 模拟真值，不是现场实测；\n"
            "换风向、换间距、换湍流强度，数值都会变；\n"
            "外场的年尺度量级是 4%–20%，与本图的单场景值不同口径。",
            ha="center", va="center", fontsize=13, color=GRAY, linespacing=1.9)
    save(fig, "g01_wake_loss")


# ── g02 偏航扫描 ────────────────────────────────────────────────────────
def g02():
    t = oracle()["tandem3"]
    scan = {r["yaw"]: r["total_kW"] for r in t["unified"]}
    base = t["none"]["total_kW"]
    g = t["greedy"]

    fig = plt.figure(figsize=FS)
    frame(fig, "统一偏航能把功率拉起来，但增益随角度非线性变化",
          "三机同角度偏航扫描（±30°，5° 步长），同一来流与同一零偏航基准",
          "数据来源：同 oracle（tandem3.unified / tandem3.greedy）　｜　"
          "增益 = 单场景、单风向的模拟真值，不可外推为年发电量",
          "第 8 页 · 优化控制（偏航线）", TAG_SIM)

    ax = fig.add_axes([0.065, 0.165, 0.55, 0.585])
    ys = sorted(scan)
    vals = [scan[y] for y in ys]
    ax.plot(ys, vals, "-o", color=BLUE, lw=2.6, ms=7, mfc="white", mew=2)
    ax.axhline(base, color=MUTED, ls="--", lw=1.5)
    ax.text(-29.4, base + 45, f"零偏航 {base:.0f} kW", color=GRAY, fontsize=12.5)

    best = max(scan, key=scan.get)
    ax.scatter([best], [scan[best]], s=200, zorder=5, color=AMBER,
               edgecolor="white", lw=2)
    ax.annotate(f"统一 +{best}°：{scan[best]:.0f} kW（+{100 * (scan[best] / base - 1):.1f}%）",
                (best, scan[best]), xytext=(-46, 74), textcoords="offset points",
                fontsize=13.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=1.3))
    ax.scatter([0], [g["total_kW"]], s=210, marker="D", zorder=6, color=TEAL,
               edgecolor="white", lw=2)
    ax.annotate(f"逐台贪心 [{g['yaw'][0]}, {g['yaw'][1]}, {g['yaw'][2]}]："
                f"{g['total_kW']:.0f} kW（+{g['gain_pct']:.2f}%）",
                (0, g["total_kW"]), xytext=(14, -34), textcoords="offset points",
                fontsize=13.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=1.3))
    ax.set_xlabel("三机统一偏航角 / °")
    ax.set_ylabel("全场功率 / kW")
    ax.set_xlim(-33, 33)
    ax.set_ylim(base - 170, g["total_kW"] + 240)
    clean(ax, "y")

    bx = fig.add_axes([0.655, 0.165, 0.30, 0.585])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    bx.text(0.0, 0.99, "两个层次的结果", fontsize=14, color=MUTED)
    b(bx.text(0.0, 0.855, "① 统一偏航", fontsize=15, color=INK), INK, 0.6)
    bx.text(0.0, 0.775, f"+{best}° 时 +{100 * (scan[best] / base - 1):.1f}%；\n"
                        f"±30° 反而只有 +11% ~ +15%",
            fontsize=12.5, color=GRAY, linespacing=1.9)
    b(bx.text(0.0, 0.60, "② 逐台偏航", fontsize=15, color=INK), INK, 0.6)
    bx.text(0.0, 0.515, f"三台机角度各不相同，合计 +{g['gain_pct']:.2f}%，\n"
                        f"比最优统一角再高 {100 * (g['total_kW'] / scan[best] - 1):.1f}%",
            fontsize=12.5, color=GRAY, linespacing=1.9)
    bx.add_patch(FancyBboxPatch((0.0, 0.10), 1.0, 0.30, boxstyle="round,pad=0.02",
                                facecolor="#fdf3e7", edgecolor=AMBER, lw=1.2))
    bx.text(0.5, 0.28, "答辩口径", ha="center", fontsize=13.5, color=AMBER)
    bx.text(0.5, 0.19, "这两个百分数是同一场景的\n模拟真值，不是实测，也不是上限",
            ha="center", va="center", fontsize=12.5, color=GRAY, linespacing=1.8)
    save(fig, "g02_yaw_scan")


# ── g03 尾流偏移 ────────────────────────────────────────────────────────
def g03():
    d = oracle()["crossSection"]
    ys = np.array(d["ys"])
    xs = d["xsFloris"]
    zi = d["zs"].index(100.0)

    def prof(yaw, x):
        return np.array(d["u"][yaw][str(x)]).reshape(len(d["zs"]), len(ys))[zi]

    fig = plt.figure(figsize=FS)
    frame(fig, "偏航把尾流推开半个机位，下游来风从 4.1 涨到 5.4 m/s",
          "取轮毂高度附近 z = 100 m 的水平剖面，比较 0° 与三机 +30° 时 T01 下游三处",
          "数据来源：同 oracle（crossSection.u；x 为自 T01 起算的顺风距离）　｜　"
          "剖面相隔约 70 m，用于示意，不作逐点定量结论",
          "第 8 页 · 偏航示意（备用）", TAG_SIM)

    ax = fig.add_axes([0.065, 0.165, 0.46, 0.585])
    colors = [BLUE, TEAL, AMBER]
    for color, x in zip(colors, xs[:3]):
        ax.plot(ys, prof("+00", x), color=color, lw=2.4, label=f"0°    x={x:.0f} m")
        ax.plot(ys, prof("+30", x), color=color, lw=2.4, ls="--",
                label=f"+30°  x={x:.0f} m")
    ax.axhline(8.0, color=MUTED, ls=":", lw=1.3)
    ax.text(-292, 8.12, "自由来流 8.0 m/s", color=GRAY, fontsize=12)
    ax.set_xlabel("横向位置 y / m")
    ax.set_ylabel("风速 / (m·s$^{-1}$)")
    ax.set_xlim(-300, 300)
    ax.set_ylim(3.2, 9.0)
    ax.legend(fontsize=11, ncol=2, frameon=False, loc="lower right")
    clean(ax, "y")

    bx = fig.add_axes([0.575, 0.165, 0.39, 0.585])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    bx.text(0.0, 0.95, "尾流中心与最低风速", fontsize=15, color=GRAY)
    head = ["x / m", "0° 中心", "+30° 中心", "最低风速"]
    xx = [0.0, 0.22, 0.50, 0.76]
    for x0, h in zip(xx, head):
        bx.text(x0, 0.86, h, fontsize=12, color=MUTED)
    bx.add_patch(Rectangle((0, 0.82), 1.0, 0.004, facecolor=LINE, edgecolor="none"))
    for row, x in enumerate(xs[:3]):
        y0 = 0.70 - row * 0.135
        u0, u30 = prof("+00", x), prof("+30", x)

        def centroid(u):
            w = np.maximum(8.0 - u, 0)
            return (w * ys).sum() / w.sum()

        cells = [f"{x:.0f}", f"{centroid(u0):.0f} m", f"{centroid(u30):.0f} m",
                 f"{u0.min():.1f} → {u30.min():.1f}"]
        for x0, c in zip(xx, cells):
            bx.text(x0, y0, c, fontsize=14.5, color=INK)
    bx.text(0.0, 0.20,
            "T02 的来风从 4.1 m/s 回到 5.4 m/s，下游机多发的电\n"
            "抵消了上游机偏航的损失——这就是 +22% 的物理来源。",
            fontsize=12.5, color=INK, linespacing=1.95)
    bx.text(0.0, 0.05,
            "中心位置按 8 m/s 亏损加权，仅用于比较偏移趋势；\n"
            "横向仅 16 个采样点，曲线为线性连接。",
            fontsize=10.5, color=MUTED, linespacing=1.7)
    save(fig, "g03_wake_deflect")


# ── g04 技术路线 ────────────────────────────────────────────────────────
def g04():
    fig = plt.figure(figsize=FS)
    frame(fig, "技术路线：仿真 → 代理模型 → 优化控制 → 可视化闭环",
          "四个模块完成度不同，按「已跑通 / 部分完成 / 未达标」分别标注",
          "依据：docs/project/WORKLIST.md 与各模块交付记录　｜　"
          "「跑通」指软件链路可运行，不等于物理精度验收",
          "第 3 页 · 研究目标与技术路线")

    ax = fig.add_axes([0.04, 0.11, 0.92, 0.66])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    boxes = [
        (3, 48, "Fluent 仿真", "NREL-5MW · MRF · 双湍流模型\n三机串列，间距 3D（378 m）",
         "流程跑通；网格与取样待修", AMBER),
        (28, 48, "PINN 代理模型", "冻结主干 308.7 万参数\n新增 12 输入 / 6 输出",
         "结构就绪，精度待真实数据", AMBER),
        (53, 48, "优化控制", "MADDPG + P/PI 同权对照\n逐台贪心偏航寻优",
         "闭环已完成，未达精度门槛", TEAL),
        (78, 48, "可视化与集成", "1×3 数字孪生 · 七步演示\n三段计时 · 可导出",
         "已集成，可逐行回放", TEAL),
    ]
    for x, y, name, detail, status, color in boxes:
        ax.add_patch(FancyBboxPatch((x, y), 19, 35, boxstyle="round,pad=1.0",
                                    facecolor=PANEL, edgecolor=color, lw=2))
        b(ax.text(x + 9.5, y + 28, name, ha="center", fontsize=17.5, color=INK), INK, 0.8)
        ax.text(x + 9.5, y + 18, detail, ha="center", va="center", fontsize=12,
                color=GRAY, linespacing=1.9)
        ax.add_patch(FancyBboxPatch((x + 1.5, y + 3.5), 16, 6.5,
                                    boxstyle="round,pad=0.5", facecolor=color,
                                    edgecolor="none", alpha=0.14))
        ax.text(x + 9.5, y + 6.7, status, ha="center", va="center", fontsize=11.5,
                color=color)
        if x < 78:
            ax.add_patch(FancyArrowPatch((x + 20.2, y + 18), (x + 23.8, y + 18),
                                         arrowstyle="-|>", mutation_scale=20,
                                         color=MUTED, lw=1.8))
    ax.add_patch(FancyArrowPatch((87.5, 46), (87.5, 24), arrowstyle="-|>",
                                 mutation_scale=20, color=MUTED, lw=1.8))
    ax.add_patch(FancyArrowPatch((87.5, 24), (12.5, 24), arrowstyle="-|>",
                                 mutation_scale=20, color=MUTED, lw=1.8))
    ax.add_patch(FancyArrowPatch((12.5, 24), (12.5, 46), arrowstyle="-|>",
                                 mutation_scale=20, color=MUTED, lw=1.8))
    ax.text(50, 20.5, "控制指令回到模型，形成可回放的闭环", ha="center",
            fontsize=13.5, color=GRAY)
    ax.text(50, 9, "本页要说清的一件事：四个框的完成度不同，不能用一个框代表整条链路",
            ha="center", fontsize=13.5, color=RED)
    save(fig, "g04_roadmap")


# ── g05 代理模型选型 ────────────────────────────────────────────────────
def g05():
    data = rows(SURROGATE / "model_comparison_cv.csv")
    models = ["xgb", "gpr", "mlp_v2", "two_stage"]
    label = {"xgb": "XGBoost", "gpr": "GPR", "mlp_v2": "MLP（基线）",
             "two_stage": "两阶段"}
    fig = plt.figure(figsize=FS)
    frame(fig, "代理模型选型：四种候选在两组数据上的全场功率误差",
          "输入风速 / 风向 / 湍流强度；1224 条 FLORIS 样本，8:1:1 划分，交叉验证",
          "数据来源：optimization_control/experiments/20260807_surrogate_baseline/model_comparison_cv.csv"
          "　｜　这是交叉验证误差，不是独立测试集精度",
          "第 4 页 · 前期研究", TAG_SIM)

    ax = fig.add_axes([0.065, 0.175, 0.48, 0.56])
    width = 0.19
    x = np.arange(2)
    colors = [BLUE, TEAL, MUTED, AMBER]
    for i, m in enumerate(models):
        vals = []
        for ds in ("cc", "gch"):
            hit = [r for r in data if r["data"] == ds and r["model"] == m]
            vals.append(float(hit[0]["farm_power_RMSE_kW"]))
        ax.bar(x + (i - 1.5) * width, vals, width, color=colors[i], label=label[m])
        for xi, v in zip(x + (i - 1.5) * width, vals):
            ax.text(xi, v * 1.09, f"{v:.0f}", ha="center", fontsize=11.5, color=INK)
    ax.set_xticks(x, ["CC 数据集", "GCH 数据集"])
    ax.set_yscale("log")
    ax.set_ylabel("全场功率 RMSE / kW（对数轴）")
    ax.set_ylim(8, 1200)
    ax.legend(frameon=False, fontsize=12, ncol=4, loc="upper center")
    clean(ax, "y")

    bx = fig.add_axes([0.585, 0.175, 0.37, 0.56])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    items = [
        ("R² 全部 > 0.996", "四种模型都能拟合，差别主要在全场 RMSE"),
        ("MLP 基线 232 / 236 kW", "约为树模型的 7 倍，所以没有选它"),
        ("两阶段 29 / 36 kW", "与 XGB 相当，且能给出逐台约束"),
        ("标签来自 FLORIS", "代理的是 GCH 模型，不是实测——这一句要主动说"),
    ]
    for i, (t1, t2) in enumerate(items):
        y0 = 0.80 - i * 0.215
        bx.add_patch(FancyBboxPatch((0.0, y0 - 0.02), 1.0, 0.165,
                                    boxstyle="round,pad=0.02", facecolor=PANEL,
                                    edgecolor=LINE, lw=1.1))
        b(bx.text(0.04, y0 + 0.10, t1, fontsize=13.5, color=INK), INK, 0.6)
        bx.text(0.04, y0 + 0.035, t2, fontsize=11.5, color=GRAY)
    save(fig, "g05_model_selection")


# ── g06 方法谱系 ────────────────────────────────────────────────────────
def g06():
    fig = plt.figure(figsize=FS)
    frame(fig, "文献里的四类做法，以及本项目落在哪里",
          "不在此页做数值对比——外部增益数字必须带研究范围，留给口头补充",
          "说明：本页刻意不含外部研究的具体增益数值；若要引用，须注明场站与条件（见大纲 §4.2）",
          "第 4 页 · 前期研究")

    ax = fig.add_axes([0.04, 0.13, 0.92, 0.66])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    cols = [
        ("几何尾流模型", "Jensen、GCH 等解析式\n秒级求解、可批量扫描\n精度取决于标定", MUTED, False),
        ("CFD 数值仿真", "RANS / LES\n物理最完整\n单算例成本高", MUTED, False),
        ("数据驱动代理", "从仿真或实测学映射\n推理快、可嵌进优化\n外推能力是主要风险", BLUE, True),
        ("场级控制优化", "逐台偏航 / 桨距寻优\nRL、贪心、梯度法\n收益依赖风况分布", BLUE, True),
    ]
    for i, (name, desc, color, ours) in enumerate(cols):
        x = 3 + i * 24
        ax.add_patch(FancyBboxPatch((x, 44), 20, 37, boxstyle="round,pad=1.0",
                                    facecolor="#eef5f9" if ours else PANEL,
                                    edgecolor=color, lw=2.2 if ours else 1.3))
        b(ax.text(x + 10, 74, name, ha="center", fontsize=16, color=INK), INK, 0.8)
        ax.text(x + 10, 57, desc, ha="center", va="center", fontsize=12,
                color=GRAY, linespacing=1.9)
        if ours:
            ax.text(x + 10, 47.5, "本项目在此", ha="center", fontsize=12.5,
                    color=BLUE)
        if i < 3:
            ax.add_patch(FancyArrowPatch((x + 20.4, 62), (x + 23.6, 62),
                                         arrowstyle="-|>", mutation_scale=18,
                                         color=MUTED, lw=1.6))
    ax.text(50, 34,
            "本项目链路：FLORIS 造标签 → PINN 改造为 12 输入 → MADDPG / 贪心做场级偏航",
            ha="center", fontsize=14.5, color=INK)
    ax.text(50, 23, "Fluent 这条线目前卡在网格质量，尚未进入标签供应链",
            ha="center", fontsize=13, color=AMBER)
    ax.text(50, 10,
            "文献调研的结论：单机尾流控制已有现场验证，场级闭环控制仍以仿真为主",
            ha="center", fontsize=13, color=GRAY)
    save(fig, "g06_method_lineage")


# ── g07 PINN 改造 ───────────────────────────────────────────────────────
def g07():
    """第 7 页主图：结构改造（左）+ 训练与测试（右）。

    左栏取结构包 `build_report.json`（9 输入版，可训练 24,306）；
    右栏取真正训过的 12 输入版 `20261022_wind_pinn_integration/model/summary.txt`
    （可训练 27,106、120 epoch、MAE 51.0/48.3/44.5 kW）。
    **两个数不是同一版本，图上必须分开写**——这是 2026-10-24 复核发现的坑。
    """
    rep = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    total = rep["original_parameters"]
    frozen = rep["retained_original_hidden_parameters"]
    add_in = rep["new_input_trainable_parameters"]
    add_out = rep["new_output_trainable_parameters"]
    structure = rep["total_trainable_parameters"]

    trained = json.loads((INTEG / "model/summary.txt").read_text(encoding="utf-8"))
    n_epoch = trained["epochs_completed"]
    trainable = trained["trainable_parameters"]
    tm = trained["test_metrics"]
    mae = [tm[k]["MAE"] / 1000 for k in ("P1", "P2", "P3")]

    hist = [(int(r["epoch"]), float(r["loss"]), float(r["val_loss"]))
            for r in rows(INTEG / "model/metrics.csv")]

    fig = plt.figure(figsize=FS)
    frame(fig, "PINN：冻结 309 万主干，只训新增接口；已训完 120 epoch",
          "左＝结构改造（9 输入版，可训练 24,306）　右＝实际训练版本（12 输入版，可训练 27,106）"
          "　—— 两个数是两个版本，不能混写",
          "来源：PINN十二输入交付/…/build_report.json；experiments/20261022_wind_pinn_integration/model/"
          "{summary.txt,metrics.csv}　｜　标签为合成教师模型，physical_validation = false",
          "第 7 页 · PINN 开发进展", TAG_SYN)

    # 左：结构改造
    ax = fig.add_axes([0.045, 0.15, 0.40, 0.60])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((4, 60), 92, 24, boxstyle="round,pad=1.0",
                                facecolor="#eef5f9", edgecolor=BLUE, lw=2))
    b(ax.text(50, 79, "原 PINN 主干（冻结）", ha="center", fontsize=15, color=INK), INK, 0.8)
    ax.text(50, 68, f"{frozen:,} 个参数 · 权重不变 · 摘要前后一致",
            ha="center", fontsize=12, color=GRAY)
    ax.add_patch(FancyBboxPatch((4, 33), 92, 17, boxstyle="round,pad=1.0",
                                facecolor="#fdf3e7", edgecolor=AMBER, lw=2))
    b(ax.text(50, 45, f"新增输入连接 {add_in:,}", ha="center", fontsize=14, color=INK), INK, 0.7)
    ax.text(50, 37, "12 维：风速/风向/TI + 三机 γ、β、ω", ha="center",
            fontsize=11.5, color=GRAY)
    ax.add_patch(FancyBboxPatch((4, 8), 92, 17, boxstyle="round,pad=1.0",
                                facecolor="#fdf3e7", edgecolor=AMBER, lw=2))
    b(ax.text(50, 20, f"新增输出头 {add_out:,}", ha="center", fontsize=14, color=INK), INK, 0.7)
    ax.text(50, 12, "6 维：P1–P3（W）、Ueff1–3（m/s）", ha="center",
            fontsize=11.5, color=GRAY)
    for y0, y1 in ((60, 50), (33, 25)):
        ax.add_patch(FancyArrowPatch((50, y0), (50, y1), arrowstyle="-|>",
                                     mutation_scale=16, color=MUTED, lw=1.6))
    ax.text(50, 3, f"原模型总量 {total:,}　可训练 {structure:,}（{100 * structure / total:.2f}%）",
            ha="center", fontsize=12, color=GRAY)

    # 右：训练曲线
    bx = fig.add_axes([0.50, 0.455, 0.44, 0.295])
    ep = [h[0] for h in hist]
    bx.plot(ep, [h[1] for h in hist], color=BLUE, lw=2.2, label="训练 loss")
    bx.plot(ep, [h[2] for h in hist], color=AMBER, lw=2.2, ls="--", label="验证 loss")
    bx.set_yscale("log")
    bx.set_ylabel("loss（对数）", fontsize=12)
    b(bx.set_title(f"训练过程：{n_epoch} epoch，loss {hist[0][1]:.2f} → {hist[-1][1]:.3f}",
                   loc="left", fontsize=14, color=INK), INK, 0.6)
    bx.legend(frameon=False, fontsize=11.5)
    bx.tick_params(labelsize=11)
    clean(bx, "y")

    # 右：测试指标卡
    cx = fig.add_axes([0.50, 0.115, 0.44, 0.26])
    cx.set_xlim(0, 1)
    cx.set_ylim(0, 1)
    cx.axis("off")
    card(cx, 0.0, 0.48, 0.30, 0.50, "可训练（12 输入版）", f"{trainable:,}",
         f"结构版为 {structure:,}", INK)
    card(cx, 0.35, 0.48, 0.30, 0.50, "测试集 P1 MAE", f"{mae[0]:.1f} kW",
         "相对 4.09%", AMBER)
    card(cx, 0.70, 0.48, 0.30, 0.50, "P2 / P3 MAE", f"{mae[1]:.1f} / {mae[2]:.1f}",
         "4.76% / 5.11%", AMBER)
    cx.text(0.0, 0.30, "标签来源 synthetic_test　·　physical_validation = false　·　监督迁移（无 PDE 残差）",
            fontsize=11.5, color=RED)
    cx.text(0.0, 0.10, "所以：这是「拟合合成标签」的精度，不是对 CFD 或实测的精度。",
            fontsize=12, color=GRAY)
    save(fig, "g07_pinn_migration")


# ── g08 五段架构 ────────────────────────────────────────────────────────
def g08():
    fig = plt.figure(figsize=FS)
    frame(fig, "系统架构：五段数据流，一段接一段跑通",
          "随机入口 → 冻结代理模型 → 反馈与评估 → 控制器 → 统一执行器",
          "依据：optimization_control/experiments/20261022_midterm_figures/01_closed_loop（同一张图的重新排版）",
          "第 3 页 · 技术路线（备用）")

    ax = fig.add_axes([0.04, 0.11, 0.92, 0.66])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    stages = [
        ("① 随机入口", "风速 / 风向 / 湍流强度\n随时间变化；平稳、慢变、阵风\n三类入口按同一协议生成",
         "输入侧", BLUE),
        ("② 冻结代理模型", "12 输入 → 6 输出\nP1–P3 与 Ueff1–Ueff3\n合成标签，非物理精度",
         "模型侧", AMBER),
        ("③ 反馈与评估", "全场功率与跟踪误差\n验证选模 → 独立测试\n阈值：均值 400 kW / 最差 500 kW",
         "评估侧", TEAL),
        ("④ 控制器", "MADDPG / P / PI / 固定桨距\n共享同一初态与动作映射\n同权对照，不额外调参",
         "控制侧", TEAL),
        ("⑤ 统一执行器", "接收偏航 / 桨距 / 转速目标\n施加限速、时间常数与边界\nγ = wrap(ψ − θ∞)",
         "执行侧", PURPLE),
    ]
    w = 17.5
    for i, (name, detail, side, color) in enumerate(stages):
        x = 2 + i * 19.4
        ax.add_patch(FancyBboxPatch((x, 30), w, 52, boxstyle="round,pad=1.0",
                                    facecolor=PANEL, edgecolor=color, lw=2))
        ax.text(x + w / 2, 77, side, ha="center", fontsize=11.5, color=MUTED)
        b(ax.text(x + w / 2, 69, name, ha="center", fontsize=15, color=INK), INK, 0.8)
        ax.text(x + w / 2, 46, detail, ha="center", va="center", fontsize=11,
                color=GRAY, linespacing=1.85)
        if i < 4:
            ax.add_patch(FancyArrowPatch((x + w + 0.4, 56), (x + 19.0, 56),
                                         arrowstyle="-|>", mutation_scale=19,
                                         color=MUTED, lw=1.8))
    ax.add_patch(FancyBboxPatch((2, 14), 96, 9, boxstyle="round,pad=0.5",
                                facecolor="#eef5f9", edgecolor=BLUE, lw=1.2))
    ax.text(50, 18.5, "⑤ 的输出成为下一时间步的入口，每步 1 s、128 步一个回合",
            ha="center", va="center", fontsize=13, color=BLUE)
    ax.text(50, 6, "答辩提醒：这条链路证明「能跑通、能复算」，不证明「物理精度更准」",
            ha="center", fontsize=13, color=RED)
    save(fig, "g08_pipeline")


# ── g09 七步演示 ────────────────────────────────────────────────────────
def g09():
    steps = [
        ("① 选工况", "来流、坐标、机组参数"),
        ("② 看基准", "2702 kW 与逐台功率"),
        ("③ 调航向", "三机各 ±30°"),
        ("④ 求解优化", "贪心逐台寻优"),
        ("⑤ 复核效果", "并排流场与逐台柱"),
        ("⑥ 展示可靠性", "散点、误差、三段计时"),
        ("⑦ 导出材料", "SVG / PNG / JSON"),
    ]
    fig = plt.figure(figsize=FS)
    frame(fig, "七步闭环：从选工况到导出材料，全程在同一界面完成",
          "每一步都有对应截图与可导出数据；界面内置三段计时，现场以显示为准",
          "截图来源：docs/research/img/r44_demo_step1–7.png（1×3 布局，2026-10-05）",
          "第 10 页 · 可视化与集成")

    ax = fig.add_axes([0.045, 0.700, 0.91, 0.135])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    for i, (name, note) in enumerate(steps):
        x = 0.5 + i * 14.2
        ax.add_patch(FancyBboxPatch((x, 26), 12.6, 62, boxstyle="round,pad=0.4",
                                    facecolor=PANEL, edgecolor=BLUE if i < 5 else TEAL,
                                    lw=1.6))
        b(ax.text(x + 6.3, 70, name, ha="center", fontsize=13, color=INK), INK, 0.6)
        ax.text(x + 6.3, 44, note, ha="center", va="center", fontsize=10.5,
                color=GRAY, wrap=True)
        if i < 6:
            ax.add_patch(FancyArrowPatch((x + 13.0, 57), (x + 14.6, 57),
                                         arrowstyle="-|>", mutation_scale=14,
                                         color=MUTED, lw=1.4))

    picks = [(0, "① 选工况"), (3, "③ 调航向"), (4, "④ 求解优化"), (6, "⑦ 导出")]
    for k, (idx, label) in enumerate(picks):
        sub = fig.add_axes([0.048 + k * 0.238, 0.145, 0.222, 0.435])
        img = Image.open(SHOT / f"r44_demo_step{idx + 1}.png").convert("RGB")
        sub.imshow(img)
        sub.set_xticks([])
        sub.set_yticks([])
        for s in sub.spines.values():
            s.set_color(LINE)
        sub.set_title(label, fontsize=11.5, color=GRAY, loc="left", pad=4)
    fig.text(0.048, 0.112, "四张为关键帧；完整七步动图见 assets/animated/gif_demo_seven_steps.gif",
             fontsize=11, color=MUTED)
    save(fig, "g09_seven_steps")


# ── g10 三流训练收敛 ────────────────────────────────────────────────────
def g10():
    fig = plt.figure(figsize=FS)
    frame(fig, "三条训练流的验证误差同步下降，但都没有过 400 kW 门槛",
          "验证 RMSE 随训练步数变化；三条流各 16,384 步，每 4,096 步验证一次",
          "数据来源：optimization_control/experiments/20261022_random_wind_training/pitch_run_{0,1,2}"
          "/segment_000/metrics.csv　｜　合成入口 + 合成标签",
          "第 9 页 · 优化控制（训练收敛）", TAG_SYN)

    ax = fig.add_axes([0.07, 0.175, 0.53, 0.56])
    colors = [BLUE, TEAL, AMBER]
    finals = []
    for i, color in enumerate(colors):
        data = rows(RANDOM / f"pitch_run_{i}/segment_000/metrics.csv")
        xs = [int(r["steps"]) for r in data]
        ys = [float(r["validation_rmse_w"]) / 1000 for r in data]
        finals.append(ys[-1])
        ax.plot(xs, ys, "-o", color=color, lw=2.4, ms=7, mfc="white", mew=2,
                label=f"第 {i} 条流")
        ax.annotate(f"{ys[-1]:.0f}", (xs[-1], ys[-1]), xytext=(8, -4),
                    textcoords="offset points", fontsize=12.5, color=color)
    ax.axhline(400, color=RED, ls="--", lw=1.5)
    ax.text(200, 425, "晋级门槛：验证均值 ≤ 400 kW", color=RED, fontsize=12)
    ax.set_xlabel("训练步数")
    ax.set_ylabel("验证 RMSE / kW")
    ax.set_xlim(-400, 17800)
    ax.set_ylim(380, 1360)
    ax.legend(frameon=False, fontsize=12.5, loc="upper right")
    clean(ax, "y")

    bx = fig.add_axes([0.635, 0.175, 0.33, 0.56])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    bx.text(0.0, 0.95, "训练末段验证误差", fontsize=15, color=GRAY)
    for i, v in enumerate(finals):
        y0 = 0.72 - i * 0.16
        bx.text(0.0, y0, f"第 {i} 条流", fontsize=14, color=INK)
        b(bx.text(0.62, y0, f"{v:.2f} kW", fontsize=16, color=INK), INK, 0.7)
        bx.add_patch(Rectangle((0.0, y0 - 0.055), 1.0, 0.004, facecolor=LINE,
                               edgecolor="none"))
    bx.text(0.0, 0.20, "三条流都在下降，但\n都停在门槛上方——\n所以没有宣称收敛。",
            fontsize=13, color=GRAY, linespacing=1.9)
    bx.text(0.0, 0.02, "注：验证集与测试集独立，测试只在参数冻结后开启。",
            fontsize=11, color=MUTED)
    save(fig, "g10_training_curves")


# ── g11 独立测试 ────────────────────────────────────────────────────────
def g11():
    data = test_metrics()
    names = [("initial", "初始 MADDPG"), ("fixed", "固定桨距"),
             ("p", "P 控制"), ("pi", "PI 控制"), ("final", "训练后 MADDPG")]
    means = []
    for key, label in names:
        vals = [float(r["rmse_w"]) / 1000 for r in data
                if r["controller"] == key and r["family"] != "low_wind_stress"]
        means.append(st.mean(vals))
    streams = []
    for i in range(3):
        vals = [float(r["rmse_w"]) / 1000 for r in data
                if r["controller"] == "final" and r["run_id"] == str(i)
                and r["family"] != "low_wind_stress"]
        streams.append(st.mean(vals))

    fig = plt.figure(figsize=FS)
    frame(fig, "独立测试：跟踪误差比初始策略降 58.5%，比 PI 只低 5.8%",
          "20 个工况中的 18 个常规工况（平稳 / 慢变 / 阵风各 6）　·　指标是功率跟踪 RMSE，越低越好"
          "　·　五种方法同一执行器、同一量程",
          "数据来源：optimization_control/experiments/20261022_random_wind_training/test/metrics.csv"
          "　｜　± 为三条训练流均值的样本标准差，不是置信区间",
          "第 9 页 · 优化控制结果", TAG_SYN)

    ax = fig.add_axes([0.07, 0.175, 0.46, 0.56])
    cols = [LINE, MUTED, BLUE, TEAL, AMBER]
    bars = ax.bar(range(5), means, 0.62, color=cols)
    for i, (bar, v) in enumerate(zip(bars, means)):
        b(ax.text(bar.get_x() + bar.get_width() / 2, v + 22, f"{v:.1f}",
                  ha="center", fontsize=14, color=INK), INK, 0.6)
    ax.set_xticks(range(5), [n for _, n in names], fontsize=11.5)
    ax.set_ylabel("常规 18 工况平均 RMSE / kW（越低越好）")
    ax.set_ylim(0, 1280)
    ax.text(4, means[4] + 120, "± 40.1", ha="center", fontsize=12, color=AMBER)
    clean(ax, "y")

    bx = fig.add_axes([0.575, 0.175, 0.39, 0.56])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    bx.text(0.0, 0.97, "两条结论要分开说", fontsize=14.5, color=GRAY)
    bx.add_patch(FancyBboxPatch((0.0, 0.62), 1.0, 0.28, boxstyle="round,pad=0.02",
                                facecolor="#eef7f5", edgecolor=TEAL, lw=1.2))
    bx.text(0.04, 0.84, "相对初始：−58.5%", fontsize=15, color=TEAL)
    bx.text(0.04, 0.71, "三条训练流方向一致，这一条站得住", fontsize=12, color=GRAY)
    bx.add_patch(FancyBboxPatch((0.0, 0.28), 1.0, 0.28, boxstyle="round,pad=0.02",
                                facecolor="#fdf3e7", edgecolor=AMBER, lw=1.2))
    bx.text(0.04, 0.50, "相对 PI：−5.8%", fontsize=15, color=AMBER)
    bx.text(0.04, 0.37, "均值略低，但不显著，且跨流不稳定", fontsize=12, color=GRAY)
    bx.text(0.0, 0.19, "三条流分别：", fontsize=12.5, color=GRAY)
    for i, v in enumerate(streams):
        w = 0.09 + 0.25 * (v / max(streams))
        bx.add_patch(Rectangle((0.24, 0.145 - i * 0.055), w, 0.028,
                               facecolor=AMBER if v > means[3] else TEAL,
                               edgecolor="none"))
        bx.text(0.24 + w + 0.02, 0.145 - i * 0.055, f"{v:.1f} kW", fontsize=11.5,
                color=INK, va="bottom")
    bx.text(0.0, 0.0, "第 0 条高于 PI 3.1% —— 这是必须主动说的失败面。",
            fontsize=12, color=RED)
    save(fig, "g11_independent_test")


# ── g12 场景拆解 ────────────────────────────────────────────────────────
def g12():
    data = test_metrics()
    fams = [("stationary", "平稳"), ("ramp", "慢变"), ("gust", "阵风")]
    ctrls = [("pi", "PI", TEAL), ("final", "训练后", AMBER), ("initial", "初始", MUTED)]
    fig = plt.figure(figsize=FS)
    frame(fig, "按场景拆开看：阵风和平稳场有改善，慢变场仍落后于 PI",
          "同一个指标在不同来流族上的表现并不一致，均值会掩盖这一点",
          "数据来源：同 metrics.csv（family 字段；每族 6 个工况 × 对应控制器）",
          "控制效果 · 第 8 页", TAG_SYN)

    ax = fig.add_axes([0.07, 0.175, 0.55, 0.56])
    x = np.arange(3)
    for i, (key, label, color) in enumerate(ctrls):
        vals = [fam_mean(data, f, key) for f, _ in fams]
        ax.bar(x + (i - 1) * 0.26, vals, 0.24, color=color, label=label)
        for xi, v in zip(x + (i - 1) * 0.26, vals):
            ax.text(xi, v + 18, f"{v:.0f}", ha="center", fontsize=11.5, color=INK)
    ax.set_xticks(x, [n for _, n in fams])
    ax.set_ylabel("平均 RMSE / kW")
    ax.set_ylim(0, 1350)
    ax.legend(frameon=False, fontsize=12.5, ncol=3, loc="upper left")
    clean(ax, "y")
    ax.annotate("慢变：432 vs 417，仍高 3.6%", xy=(1.26, 440), xytext=(0.55, 780),
                fontsize=12.5, color=RED,
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.4))

    bx = fig.add_axes([0.655, 0.175, 0.31, 0.56])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    bx.text(0.0, 0.95, "读图方法", fontsize=14.5, color=GRAY)
    bx.text(0.0, 0.80,
            "① 同一族内比三根柱的高度；\n"
            "② 只比较同族，不跨族比较；\n"
            "③ 均值有意义，但不能替代分族结论。",
            fontsize=13, color=GRAY, linespacing=2.0)
    bx.add_patch(FancyBboxPatch((0.0, 0.20), 1.0, 0.34, boxstyle="round,pad=0.02",
                                facecolor="#fdf3e7", edgecolor=AMBER, lw=1.2))
    bx.text(0.06, 0.44, "诚实边界", fontsize=13, color=AMBER)
    bx.text(0.06, 0.33, "阵风改善最大，但阵风\n也是最难做现场验证的一类；\n这一条只能算软件链路的证据。",
            fontsize=11.5, color=GRAY, linespacing=1.9)
    bx.text(0.0, 0.05, "低风压力场见下一页。", fontsize=11.5, color=MUTED)
    save(fig, "g12_scenario_breakdown")


# ── g13 未达标场景 ──────────────────────────────────────────────────────
def g13():
    data = test_metrics()
    fig = plt.figure(figsize=FS)
    frame(fig, "三处没达标：低风压力场、慢变场、高目标桨距",
          "这些不改口径、不挑数据，原样报告",
          "数据来源：test/metrics.csv（low_wind_stress 族）+ 20261022_wind_pinn_curriculum/metrics.csv"
          "　｜　三条结论都是合成标签下的结果",
          "第 9 页 · 结果（负结果）", TAG_SYN)

    ax = fig.add_axes([0.05, 0.14, 0.90, 0.62])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    blocks = [
        ("低风压力场", fam_mean(data, "low_wind_stress", "final"),
         fam_mean(data, "low_wind_stress", "pi"), "训练后 vs PI", "kW",
         "两条低风工况，固定风而非湍流测试"),
        ("慢变来流", fam_mean(data, "ramp", "final"),
         fam_mean(data, "ramp", "pi"), "训练后 vs PI", "kW",
         "6 个慢变工况，跟踪滞后暴露"),
        ("高目标桨距", 23.96, 10.39, "训练终点 vs 初始", "kW",
         "选中策略即初始策略，判为未学会"),
    ]
    for i, (name, ours, ref, label, unit, note) in enumerate(blocks):
        x = 2 + i * 32.5
        ax.add_patch(FancyBboxPatch((x, 40), 29, 52, boxstyle="round,pad=1.0",
                                    facecolor=PANEL, edgecolor=RED, lw=1.6))
        b(ax.text(x + 14.5, 84, name, ha="center", fontsize=16, color=INK), INK, 0.8)
        ax.text(x + 14.5, 74, label, ha="center", fontsize=11.5, color=MUTED)
        b(ax.text(x + 7.5, 60, f"{ours:.1f}", ha="center", fontsize=24, color=RED), RED, 0.8)
        ax.text(x + 7.5, 52, unit, ha="center", fontsize=11.5, color=GRAY)
        ax.text(x + 14.5, 60, "vs", ha="center", fontsize=13, color=MUTED)
        b(ax.text(x + 21.5, 60, f"{ref:.1f}", ha="center", fontsize=24, color=TEAL), TEAL, 0.8)
        ax.text(x + 21.5, 52, unit, ha="center", fontsize=11.5, color=GRAY)
        ax.text(x + 14.5, 45, note, ha="center", fontsize=11, color=GRAY)
    ax.text(50, 28, "红 = 我们的结果　绿 = 对照或初始策略", ha="center",
            fontsize=12, color=MUTED)
    ax.text(50, 12,
            "答辩口径：这三处不适合说「优化后全面优于传统控制」，只能说「部分场景改善、部分场景不及对照」",
            ha="center", fontsize=13, color=RED)
    save(fig, "g13_failure_cases")


# ── g14 证据链 ──────────────────────────────────────────────────────────
def g14():
    fig = plt.figure(figsize=FS)
    frame(fig, "证据链：每个数字都能回到一份可复算的文件",
          "左侧是四条可复算证据，右侧是它们各自回答的那个质疑",
          "来源：docs/evidence/、ci/repo_quality.py 输出、30,720 行轨迹复算记录",
          "第 13 页 · 总结（可复算）")

    ax = fig.add_axes([0.05, 0.14, 0.44, 0.62])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    card(ax, 0.0, 0.63, 0.47, 0.32, "布局自检 3×3 / 1×3", "161 / 158",
         "失败 0 项", INK)
    card(ax, 0.51, 0.63, 0.47, 0.32, "轨迹复算", "0 W",
         "30,720 行逐行差异（去重 23,040）", INK)
    card(ax, 0.0, 0.22, 0.47, 0.32, "内核与参考对拍", "1.25e-12",
         "浏览器内核 vs FLORIS 4.6.6，kW", INK)
    card(ax, 0.51, 0.22, 0.47, 0.32, "轮次记录", "28 份",
         "R11–R47，改动与理由可回溯", INK)
    ax.text(0.0, 0.08, "以上四项可在会议室当场重跑，不是只存在于报告里的数字。",
            fontsize=12.5, color=GRAY)

    bx = fig.add_axes([0.545, 0.14, 0.42, 0.62])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    pairs = [
        ("「你怎么知道结果不是编的？」", "30,720 行轨迹 → 240 条指标差值 0 W"),
        ("「界面显示和别人算的不一样怎么办？」", "内核与 FLORIS 参考逐式对拍，差 1.25e-12 kW"),
        ("「改动会不会把好结果弄坏？」", "161 / 158 项自检 + 回放逐行一致"),
        ("「出了问题谁负责、怎么追？」", "28 份轮次记录 + 审计文档"),
    ]
    for i, (q, a) in enumerate(pairs):
        y0 = 0.80 - i * 0.235
        bx.add_patch(FancyBboxPatch((0.0, y0 - 0.02), 1.0, 0.185,
                                    boxstyle="round,pad=0.02", facecolor=PANEL,
                                    edgecolor=LINE, lw=1.1))
        bx.text(0.035, y0 + 0.115, q, fontsize=12.5, color=INK)
        bx.text(0.035, y0 + 0.045, "→ " + a, fontsize=11.5, color=GRAY)
    save(fig, "g14_evidence_chain")


# ── g15 定位 ────────────────────────────────────────────────────────────
def g15():
    fig = plt.figure(figsize=FS)
    frame(fig, "研究定位：国际上已走到场站验证，我们的强项是闭环与可复算",
          "两张对照卡：左边是公开研究的证据等级，右边是我们目前的证据等级",
          "文献事实：Fleming et al., WES 9 (2024)；Howland et al., WES 5 (2020) / 6 (2021)；"
          "Bensason et al., JRSE 13 (2021)　｜　本页不写外部增益数值，引用时须带研究范围",
          "第 13 页 · 总结（备用）")

    ax = fig.add_axes([0.045, 0.145, 0.665, 0.615])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    rows_ = [
        ("现场实测", "风洞 + 现场单机 / 场站", "公开研究已有：用现场数据证明年发电量增益", MUTED, "已达成"),
        ("高保真仿真", "LES / RANS + 尾流模型", "公开研究常见；也用于给代理模型造标签", MUTED, "已达成"),
        ("几何代理模型", "GCH / Jensen 等解析式", "本项目用它造全部标签（FLORIS 4.6.6）", BLUE, "本项目在此"),
        ("软件闭环", "接口 + 控制 + 界面 + 回放", "本项目已完成：可跑通、可复算、可当场重跑", BLUE, "本项目在此"),
        ("跨场站泛化", "多风场、多机型验证", "本项目没有做，也不宣称", RED, "未达成"),
    ]
    for i, (name, how, note, color, status) in enumerate(rows_):
        y0 = 88 - i * 18
        ax.add_patch(FancyBboxPatch((0, y0 - 12), 100, 15.5, boxstyle="round,pad=0.5",
                                    facecolor="#eef5f9" if color == BLUE else PANEL,
                                    edgecolor=LINE, lw=1))
        ax.add_patch(Rectangle((0, y0 - 12), 0.8, 15.5, facecolor=color, edgecolor="none"))
        b(ax.text(3, y0 - 2, name, fontsize=13.5, color=INK), INK, 0.6)
        ax.text(24, y0 - 2, how, fontsize=11.5, color=GRAY)
        ax.text(24, y0 - 8.5, note, fontsize=11, color=GRAY)
        ax.text(90, y0 - 5, status, fontsize=11.5, color=color, ha="center")

    bx = fig.add_axes([0.735, 0.145, 0.225, 0.615])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    bx.add_patch(FancyBboxPatch((0, 0.42), 1.0, 0.52, boxstyle="round,pad=0.02",
                                facecolor="#eef7f5", edgecolor=TEAL, lw=1.2))
    bx.text(0.08, 0.86, "我们的强项", fontsize=13, color=TEAL)
    bx.text(0.08, 0.60, "同一套字段贯穿四个模块；\n每一步都能回放、能对拍、\n能当场重跑。",
            fontsize=12, color=GRAY, linespacing=1.9)
    bx.add_patch(FancyBboxPatch((0, 0.02), 1.0, 0.34, boxstyle="round,pad=0.02",
                                facecolor="#fdf1ef", edgecolor=RED, lw=1.2))
    bx.text(0.08, 0.29, "我们不宣称的", fontsize=13, color=RED)
    bx.text(0.08, 0.13, "真实风场精度\n年发电量增益\n跨场站泛化", fontsize=11.5,
            color=GRAY, linespacing=1.85)
    save(fig, "g15_positioning")


# ── g16 路线图 ──────────────────────────────────────────────────────────
def g16():
    fig = plt.figure(figsize=FS)
    frame(fig, "下一步：先把真实数据接进来，再谈策略与规模",
          "三段时间预算，每一段都有可验收的产出物",
          "依据：docs/project/WORKLIST.md §2.6 节点表（2026-10-31 / 11-30 / 12-31 / 2027-06）",
          "第 12 页 · 后续研究计划")

    ax = fig.add_axes([0.05, 0.16, 0.90, 0.60])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.add_patch(FancyArrowPatch((3, 62), (97, 62), arrowstyle="-|>",
                                 mutation_scale=22, color=MUTED, lw=2))
    nodes = [
        (8, "2026-10-31", "主路线确定", "字段表冻结\n真实数据接口就位", BLUE),
        (33, "2026-11-30", "模块联通", "同一份字段跑通\n界面展示真实结果", BLUE),
        (58, "2026-12-31", "原型 V1", "固定测试工况\n初版指标 + 录屏", TEAL),
        (85, "2027-06", "正式提交", "结题报告 / 答辩\n代码与数据归档", TEAL),
    ]
    for x, date, name, detail, color in nodes:
        ax.scatter([x], [62], s=200, color=color, zorder=5, edgecolor="white", lw=2)
        ax.text(x, 68, date, ha="center", fontsize=12, color=MUTED)
        b(ax.text(x, 76, name, ha="center", fontsize=14.5, color=INK), INK, 0.7)
        ax.text(x, 45, detail, ha="center", va="top", fontsize=11.5, color=GRAY,
                linespacing=1.8)
    ax.text(50, 20, "第一优先级：用实测或 CFD 数据替换合成标签——这是所有精度声明的前提",
            ha="center", fontsize=13, color=RED)
    ax.text(50, 8, "第二优先：把三条未达标场景（低风、慢变、高目标）逐个定性",
            ha="center", fontsize=12.5, color=GRAY)
    save(fig, "g16_roadmap")


# ── 动图 ────────────────────────────────────────────────────────────────
def gif_demo():
    GIF.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(1, 8):
        im = Image.open(SHOT / f"r44_demo_step{i}.png").convert("RGB")
        im = im.resize((1180, 664), Image.LANCZOS)
        frames.append(im.quantize(colors=128, method=Image.MEDIANCUT))
    path = GIF / "gif_demo_seven_steps.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=1300,
                   loop=0, optimize=True)
    print(f"  gif_demo_seven_steps.gif  {path.stat().st_size / 1024:.0f} KB")


def gif_scan():
    """逐台贪心的 13 帧扫描：真实 oracle 数据，不是示意动画。"""
    t = oracle()["tandem3"]
    scan = sorted(t["unified"], key=lambda r: r["yaw"])
    base = t["none"]
    GIF.mkdir(parents=True, exist_ok=True)
    frames = []
    for rec in scan:
        fig = plt.figure(figsize=(10, 5.6))
        ax = fig.add_axes([0.10, 0.16, 0.86, 0.66])
        yaw = rec["yaw"]
        names = ["T01", "T02", "T03"]
        cols = [MUTED, BLUE, TEAL]
        ax.bar([0, 1, 2], base["p_kW"], 0.55, color="#e8ecf0", label="零偏航")
        ax.bar([0.42, 1.42, 2.42], rec["p_kW"], 0.55, color=cols, label=f"统一 {yaw:+d}°")
        for i, v in enumerate(rec["p_kW"]):
            ax.text(0.42 + i, v + 40, f"{v:.0f}", ha="center", fontsize=13, color=INK)
        for i, v in enumerate(base["p_kW"]):
            ax.text(i, v + 40, f"{v:.0f}", ha="center", fontsize=12, color=GRAY)
        ax.set_xticks([0.21, 1.21, 2.21], names)
        ax.set_ylim(0, 2100)
        ax.set_ylabel("单机功率 / kW")
        total = rec["total_kW"]
        gain = 100 * (total / base["total_kW"] - 1)
        ax.set_title(f"三机统一偏航 {yaw:+d}°　全场 {total:.0f} kW　"
                     f"（{gain:+.1f}% vs 零偏航 {base['total_kW']:.0f} kW）",
                     fontsize=15, color=INK, loc="left")
        ax.legend(frameon=False, loc="upper right", fontsize=12)
        clean(ax, "y")
        fig.text(0.10, 0.045,
                 "FLORIS 4.6.6 GCH · 1×3 串列 · 8 m/s 均匀来流 · 模拟真值，非实测",
                 fontsize=11, color=MUTED)
        path = Path("/tmp/_scan_frame.png")
        fig.savefig(path, dpi=110, facecolor=BG)
        plt.close(fig)
        frames.append(Image.open(path).convert("RGB").quantize(colors=128))
    out = GIF / "gif_yaw_scan.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=320,
                   loop=0, optimize=True)
    print(f"  gif_yaw_scan.gif  {out.stat().st_size / 1024:.0f} KB")


# ── g24 功率跟踪时序（有效 / 不足） ─────────────────────────────────────
TRAJ = RANDOM / "test/trajectories.csv"

# 选例规则（写死在脚本里，改例要连口径一起改）：
#   有效场景 = 阵风、目标 2.7 MW、第 1 条训练流 —— 训练后 376 kW vs PI 512 kW
#   不足场景 = 慢变、目标 3.9 MW、第 1 条训练流 —— 训练后 517 kW vs P 278 / PI 303 kW
G24_CASES = (
    ("test_gust_0_pitch0.055", "1", "有效场景｜阵风 · 目标 2.7 MW", TEAL),
    ("test_ramp_2_pitch0.025", "1", "不足场景｜慢变 · 目标 3.9 MW（高目标）", RED),
)


def _series(case, ctrl, run):
    pts = [(int(r["step"]), float(r["farm_power_w"]) / 1e6, float(r["target_w"]) / 1e6)
           for r in rows(TRAJ)
           if r["case_id"] == case and r["controller"] == ctrl and r["run_id"] == run]
    pts.sort()
    return pts


def _rmse(case, ctrl, run):
    vals = [float(r["error_w"]) for r in rows(TRAJ)
            if r["case_id"] == case and r["controller"] == ctrl and r["run_id"] == run]
    return (sum(v * v for v in vals) / len(vals)) ** 0.5 / 1000


def g24():
    fig = plt.figure(figsize=FS)
    frame(fig, "同一工况、同一执行器：跟踪过程看得见，强弱点也看得见",
          "左＝有效场景，训练后贴近目标、明显优于 PI　·　右＝不足场景，慢变加高目标下落后于 P / PI"
          "　·　横轴为一回合 128 步（每步 1 s）",
          "数据来源：…/20261022_random_wind_training/test/trajectories.csv（同 case_id 回放，测试集不参与选模）"
          "　｜　标签为合成教师模型",
          "第 9 页 · 优化控制结果（过程证据）", TAG_SYN)

    for i, (case, run, label, color) in enumerate(G24_CASES):
        ax = fig.add_axes([0.055 + i * 0.485, 0.335, 0.415, 0.395])
        ours = _series(case, "final", run)
        pi = _series(case, "pi", "-1")
        p_ = _series(case, "p", "-1")
        ini = _series(case, "initial", run)
        t = [s for s, _, _ in ours]
        tgt = ours[0][2]

        ax.plot([s for s, _, _ in ini], [v for _, v, _ in ini], color=MUTED, lw=1.4,
                alpha=0.75, label=f"初始策略　{_rmse(case, 'initial', run):.0f} kW")
        ax.plot([s for s, _, _ in pi], [v for _, v, _ in pi], color=BLUE, lw=1.9,
                label=f"PI 控制　{_rmse(case, 'pi', '-1'):.0f} kW")
        ax.plot([s for s, _, _ in p_], [v for _, v, _ in p_], color=GRAY, lw=1.4,
                ls=(0, (4, 2)), label=f"P 控制　{_rmse(case, 'p', '-1'):.0f} kW")
        ax.plot(t, [v for _, v, _ in ours], color=color, lw=2.8,
                label=f"训练后 MADDPG　{_rmse(case, 'final', run):.0f} kW")
        ax.axhline(tgt, color=INK, lw=1.6, ls=(0, (6, 3)))
        ax.text(3, tgt + 0.11, f"给定目标 {tgt:.1f} MW", ha="left", fontsize=11.5, color=INK,
                bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor="none", alpha=0.9))

        ax.set_xlim(0, 128)
        ax.set_ylim(1.9, 5.55)
        ax.set_xlabel("回合内时间 / s", fontsize=12)
        ax.set_ylabel("全场功率 / MW", fontsize=12)
        b(ax.set_title(label, fontsize=14.5, color=color, pad=9), color, 0.5)
        leg = ax.legend(fontsize=10, loc="upper left", ncol=2, handlelength=1.5,
                        columnspacing=1.1, labelspacing=0.3, borderpad=0.35,
                        facecolor="white", edgecolor=LINE, framealpha=0.95)
        for txt in leg.get_texts():
            txt.set_color(GRAY)
        clean(ax, "y")

    fig.text(0.055, 0.205,
             "读法：黑虚线是给定目标，四条线是四种方式（同一执行器、同一量程、同一回合）。\n"
             "左图各方法都向目标收敛、训练后最贴近；右图目标接近可用出力上限，训练后反而落后于 P / PI。",
             fontsize=11.5, color=GRAY)
    fig.text(0.055, 0.122,
             "能证明：合成标签环境下训练后的策略确实把功率拉向目标；不能证明：真实风场同样成立。",
             fontsize=11.5, color=RED)
    save(fig, "g24_power_tracking")


# ── g25 三项阶段技术贡献 ────────────────────────────────────────────────
def g25():
    fig = plt.figure(figsize=FS)
    frame(fig, "我们具体解决了什么：三项阶段技术贡献，各对应一个难点",
          "都不是算法原创；是把「已有模型 + 已有算法」接成一条能复算、能对照、能追责的评估链",
          "对应页：第 6 页（贡献 01）· 第 8 页（贡献 02）· 第 9 页（贡献 03）"
          "　｜　每一项的检验依据都在本仓库可复算",
          "第 7 页备选 · 贡献提炼", None)

    items = [
        ("01", "面向三机任务的模型接口适配与检查", BLUE,
         "难点", "风况、实际运行点、列序、风向周期、单位怎么统一",
         "做法的检验依据",
         ["外部 12 维 = 风况 3 + 三机运行点 9；桥接层转逐机交错列序",
          "风向内部编为 sin/cos，外部 12 维 / 内部 13 特征不混称",
          "列序、单位、机位、有效域逐项自检：输入越界显式拒绝",
          "输入取执行器实际运行点，不把参考值当已施加状态"]),
        ("02", "带统一执行器约束的多机控制评估", TEAL,
         "难点", "RL 与 P / PI 权限、限速、后台规则不同，比较就不公平",
         "做法的检验依据",
         ["所有方法共享同一 ActionMapper 与 ActuatorModel",
          "偏航 0.005 rad/s、桨距 0.5°/s、转速 0.1 rad/s²，全体一致",
          "正式实验 RL 仅学桨距，偏航与转速由共同调度补齐",
          "奖励 = 归一化跟踪误差平方 + 目标动作平滑惩罚"]),
        ("03", "训练到冻结测试的评估流程", AMBER,
         "难点", "避免只展示最好的一条流、一个工况或一根均值柱",
         "做法的检验依据",
         ["三流 × 每流 128 回合，验证集先定门槛再开测试",
          "门槛预先固定：验证均值 ≤400 kW、最差 ≤500 kW，未过不晋级",
          "冻结测试 18 场 + 压力 2 场，测试集不参与选模与调参",
          "240 条指标 / 30,720 行轨迹全留档，可逐回合复算"]),
    ]
    for i, (num, title, color, k1, v1, k2, rows_) in enumerate(items):
        x = 0.045 + i * 0.318
        ax = fig.add_axes([x, 0.175, 0.30, 0.62])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0.012",
                                    facecolor=PANEL, edgecolor=color, lw=1.6))
        b(ax.text(0.05, 0.945, num, fontsize=15, color=color), color, 0.5)
        b(ax.text(0.05, 0.845, title, fontsize=14.5, color=INK), INK, 0.5)
        ax.plot([0.05, 0.95], [0.70, 0.70], color=LINE, lw=1.0)
        b(ax.text(0.05, 0.645, k1, fontsize=12, color=color), color, 0.4)
        ax.text(0.05, 0.585, v1, fontsize=11, color=GRAY, wrap=True)
        ax.plot([0.05, 0.95], [0.505, 0.505], color=LINE, lw=1.0)
        b(ax.text(0.05, 0.455, k2, fontsize=12, color=color), color, 0.4)
        for j, r in enumerate(rows_):
            ax.text(0.055, 0.375 - j * 0.115, "· " + r, fontsize=10.3, color=INK,
                    wrap=True)
    save(fig, "g25_contributions")


def main(argv):
    use_cjk()
    wanted = set(argv)
    funcs = {n: o for n, o in sorted(globals().items())
             if len(n) == 3 and n[0] == "g" and n[1:].isdigit() and callable(o)}
    if "gif" in wanted:
        gif_demo()
        gif_scan()
        return 0
    if "all" not in wanted and wanted:
        for n in sorted(funcs):
            if n in wanted:
                funcs[n]()
    else:
        for n in sorted(funcs):
            funcs[n]()
    total = sum(f.stat().st_size for f in OUT.glob("*.png"))
    print(f"\n{len(list(OUT.glob('*.png')))} 张图，合计 {total / 1024 / 1024:.1f} MiB")
    return 0




# ── g17 数据集覆盖 ──────────────────────────────────────────────────────
def g17():
    cc = rows(FLORIS_DIR / "output_cc/training_data_cc.csv")
    gch = rows(FLORIS_TRAIN)
    us = sorted({float(r["wind_speed"]) for r in gch})
    ds = sorted({float(r["wind_direction"]) for r in gch})
    ts = sorted({float(r["turbulence_intensity"]) for r in gch})

    fig = plt.figure(figsize=FS)
    frame(fig, "CFD 数据集的覆盖范围：17 档风速 × 24 个风向 × 3 档湍流强度",
          "每个组合一条样本，共 1,224 条；同一套参数分别用 CC 与 GCH 两套尾流模型各算一遍",
          "数据来源：materials/袁夫达/20260808_FLORIS数据生成/extracted/output_{cc,gch}/training_data_*.csv"
          "　｜　标签来自 FLORIS，不是 Fluent",
          "第 7 页 · PINN 数据集（备用）", TAG_SIM)

    ax = fig.add_axes([0.065, 0.175, 0.36, 0.56])
    sub = [r for r in gch if abs(float(r["turbulence_intensity"]) - 0.06) < 1e-9]
    ax.scatter([float(r["wind_direction"]) for r in sub],
               [float(r["wind_speed"]) for r in sub],
               s=9, color=BLUE, alpha=0.75)
    ax.set_xlabel("风向 / °")
    ax.set_ylabel("风速 / (m·s$^{-1}$)")
    b(ax.set_title("参数空间取样（TI = 6%）", loc="left", fontsize=14, color=INK), INK, 0.6)
    ax.set_xlim(-10, 355)
    clean(ax, "both")

    bx = fig.add_axes([0.455, 0.175, 0.36, 0.56])
    for data, color, label in ((cc, TEAL, "CC 模型"), (gch, AMBER, "GCH 模型")):
        pts = sorted((float(r["wind_speed"]), float(r["farm_power"]) / 1000) for r in data)
        bx.scatter([p[0] for p in pts], [p[1] for p in pts], s=9, alpha=0.55,
                   color=color, label=label)
    bx.set_xlabel("风速 / (m·s$^{-1}$)")
    bx.set_ylabel("全场功率 / kW")
    b(bx.set_title("两套模型的功率散布", loc="left", fontsize=14, color=INK), INK, 0.6)
    bx.legend(frameon=False, fontsize=12, markerscale=2.4)
    clean(bx, "both")

    cx = fig.add_axes([0.855, 0.175, 0.11, 0.56])
    cx.set_xlim(0, 1)
    cx.set_ylim(0, 1)
    cx.axis("off")
    for i, (k, v) in enumerate([("样本", "1,224"), ("风速", f"{len(us)} 档"),
                                ("风向", f"{len(ds)} 个"), ("TI", "6/8/10%")]):
        y0 = 0.88 - i * 0.23
        cx.text(0.0, y0, k, fontsize=12, color=MUTED)
        b(cx.text(0.0, y0 - 0.09, v, fontsize=17, color=INK), INK, 0.7)
    save(fig, "g17_dataset_coverage")


# ── g18 PINN 网络结构 ───────────────────────────────────────────────────
def g18():
    fig = plt.figure(figsize=FS)
    frame(fig, "PINN 的结构改造：坐标输入旁接上 9 个控制量，输出接三个头",
          "不新增隐藏层，复用原网络的共享主干与六个特征分支；三台机共用同一套权重",
          "依据：materials/厉今飞/三台风机PINN模型交接与训练指南.docx（2026-10-03）",
          "第 6 页 · PINN 模型构建", TAG_SYN)

    ax = fig.add_axes([0.045, 0.13, 0.92, 0.64])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    def box(x, y, w, h, text, color, fs=12.5, fill=PANEL):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.8",
                                    facecolor=fill, edgecolor=color, lw=1.8))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, color=INK, linespacing=1.8)

    box(2, 46, 20, 34, "坐标输入\nx, y, z\n（每台机各自的位置）", MUTED)
    box(2, 8, 20, 30, "控制输入 ×9\nyaw / pitch / 转速\n（三台机各一套）", AMBER)
    box(30, 26, 26, 54, "原 PINN 主干\n共享隐藏层\n3,087,200 参数\n（冻结）", BLUE, 13.5, "#eef5f9")
    box(63, 26, 15, 54, "六个特征\n分支\nu v w p\nk ε", MUTED)
    for i, t in enumerate(["T01 输出头", "T02 输出头", "T03 输出头"]):
        box(82, 66 - i * 22, 16, 16, f"{t}\nP / Ueff", AMBER, 10.5, "#fdf3e7")
    ax.add_patch(FancyArrowPatch((22.5, 63), (29.5, 60), arrowstyle="-|>",
                                 mutation_scale=16, color=MUTED, lw=1.6))
    ax.add_patch(FancyArrowPatch((22.5, 23), (29.5, 33), arrowstyle="-|>",
                                 mutation_scale=16, color=AMBER, lw=1.8))
    ax.add_patch(FancyArrowPatch((56.5, 53), (62.5, 53), arrowstyle="-|>",
                                 mutation_scale=16, color=MUTED, lw=1.6))
    for y in (74, 52, 30):
        ax.add_patch(FancyArrowPatch((78.5, 53), (81.5, y), arrowstyle="-|>",
                                     mutation_scale=14, color=MUTED, lw=1.3,
                                     connectionstyle="arc3,rad=0.12"))
    ax.text(50, 5,
            "口播口径：这叫「接口扩展」，不是「重新训练一个新模型」；新增连接初始为零，真实控制作用靠后续数据学",
            ha="center", fontsize=12.5, color=RED)
    save(fig, "g18_pinn_architecture")


# ── g19 Fluent 现状（2026-10-24 按三机串列双模型数据重做）──────────────
def g19():
    """第 5 页主图：左「已完成工况」、右「已知不足」。

    口径来源 materials/田铭雨/20261024_三机串列双模型对比/（k-omega_data、
    k-epsilon_data 的 power_thrust.csv 与 case_meta.json），可用性判定见
    docs/evidence/EVID-2026-003。**三台总功率与逐台功率比一律不上这张图**。
    """
    fig = plt.figure(figsize=FS)
    frame(fig, "Fluent 仿真：流程跑通了，网格还解析不了串列尾流",
          "NREL-5MW · 三机串列 3D（378 m）· 稳态 MRF · 9 m/s、TI 10% · 同一套网格跑 SST k-ω 与标准 k-ε",
          "依据：materials/田铭雨/20261024_三机串列双模型对比/　｜　"
          "判定见 docs/evidence/EVID-2026-003　｜　单机才可信，串列干扰量不上屏",
          "第 5 页 · Fluent 仿真工作", TAG_CFD)

    # 左栏：已完成
    ax = fig.add_axes([0.05, 0.13, 0.44, 0.63])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    b(ax.text(0.0, 0.95, "已完成", fontsize=16, color=TEAL), TEAL, 0.7)
    done = [
        ("布置", "三机串列，间距 378 m（3.0D）"),
        ("网格", "Poly-Hexcore，1,055,511 单元"),
        ("湍流模型", "SST k-ω 与标准 k-ε，各一套"),
        ("工况", "9 m/s、TI 10%、Ω = 1.070 rad/s"),
        ("单机功率", "2.39 MW（k-ω）/ 2.32 MW（k-ε）"),
        ("两模型差", "2.7%；对 FLORIS 单机差 4.4% / 7.0%"),
    ]
    for i, (k, v) in enumerate(done):
        y0 = 0.82 - i * 0.135
        ax.add_patch(Rectangle((0.0, y0 - 0.012), 0.012, 0.012, color=TEAL))
        ax.text(0.03, y0, k, fontsize=13, color=INK)
        ax.text(0.30, y0, v, fontsize=11.5, color=GRAY)

    # 右栏：已知不足
    bx = fig.add_axes([0.53, 0.13, 0.42, 0.63])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    b(bx.text(0.0, 0.95, "已知不足", fontsize=16, color=RED), RED, 0.7)
    todo = [
        ("尾流区网格 13 m", "127 m 直径上只有十来个单元，解析不出盘面平均亏损"),
        ("3D 处尾流未体现", "T2 盘面均速只比 T1 低 0.2%（k-ε 反而高 0.3%）"),
        ("同一 3D 却掉 34%", "T3 相对 T2 掉 34%，与上一条自相矛盾"),
        ("零速度区", "3 个 zone 共 285,579 单元，占 27%"),
    ]
    for i, (k, v) in enumerate(todo):
        y0 = 0.80 - i * 0.205
        bx.add_patch(FancyBboxPatch((0.0, y0 - 0.040), 1.0, 0.150,
                                    boxstyle="round,pad=0.02", facecolor="#fdf1ef",
                                    edgecolor=RED, lw=1, alpha=0.7))
        bx.text(0.035, y0 + 0.062, k, fontsize=12.5, color=INK)
        bx.text(0.035, y0 - 0.005, v, fontsize=10.5, color=GRAY)
    bx.text(0.0, 0.015, "所以：单机数据可用作交叉核对，串列干扰量不进入对外材料。",
            fontsize=11.5, color=RED)
    save(fig, "g19_fluent_status")


# ── g20 偏航的收益账 ────────────────────────────────────────────────────
def g20():
    d = oracle()
    pair = sorted(d["pair8ms"], key=lambda r: r["yaw"])
    fig = plt.figure(figsize=FS)
    frame(fig, "偏航不是白拿：上游机少发、下游机多发，净值才决定值不值得",
          "同一 8 m/s 来流下，上游机偏航后自身功率下降，但把尾流推开让下游机回升",
          "数据来源：同 oracle（pair8ms，上游/下游两台机随偏航角变化的功率）",
          "第 2 页 · 研究背景（备用）", TAG_SIM)

    ax = fig.add_axes([0.07, 0.175, 0.52, 0.56])
    ys = [r["yaw"] for r in pair]
    ax.plot(ys, [r["pUp_kW"] for r in pair], "-o", color=BLUE, lw=2.4, ms=6,
            label="上游机功率")
    ax.plot(ys, [r["pDn_kW"] for r in pair], "-o", color=AMBER, lw=2.4, ms=6,
            label="下游机功率")
    ax.plot(ys, [r["pUp_kW"] + r["pDn_kW"] for r in pair], "-o", color=TEAL,
            lw=2.8, ms=6, label="两台合计")
    zero = [r for r in pair if r["yaw"] == 0][0]
    ax.axvline(0, color=MUTED, ls=":", lw=1.2)
    best = max(pair, key=lambda r: r["pUp_kW"] + r["pDn_kW"])
    ax.scatter([best["yaw"]], [best["pUp_kW"] + best["pDn_kW"]], s=180,
               color=TEAL, edgecolor="white", lw=2, zorder=5)
    ax.annotate(f"合计最高：{best['yaw']:+d}°\n{best['pUp_kW'] + best['pDn_kW']:.0f} kW"
                f"（{(best['pUp_kW'] + best['pDn_kW']) / (zero['pUp_kW'] + zero['pDn_kW']) - 1:+.1%}）",
                (best["yaw"], best["pUp_kW"] + best["pDn_kW"]),
                xytext=(-150, -70), textcoords="offset points", fontsize=12.5,
                color=INK, arrowprops=dict(arrowstyle="-", color=MUTED, lw=1.2))
    ax.set_xlabel("上游机偏航角 / °")
    ax.set_ylabel("功率 / kW")
    ax.legend(frameon=False, fontsize=12, loc="lower left")
    ax.set_ylim(300, 2550)
    clean(ax, "y")

    bx = fig.add_axes([0.62, 0.175, 0.34, 0.56])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")
    bx.text(0.0, 0.95, "同一个动作，两台机方向相反", fontsize=14.5, color=GRAY)
    for i, (label, value, color) in enumerate([
        ("上游机", f"{best['pUp_kW'] - zero['pUp_kW']:+.0f} kW", BLUE),
        ("下游机", f"{best['pDn_kW'] - zero['pDn_kW']:+.0f} kW", AMBER),
        ("合计", f"{(best['pUp_kW'] + best['pDn_kW']) - (zero['pUp_kW'] + zero['pDn_kW']):+.0f} kW", TEAL),
    ]):
        y0 = 0.76 - i * 0.17
        bx.text(0.0, y0, label, fontsize=13.5, color=INK)
        b(bx.text(0.42, y0, value, fontsize=17, color=color), color, 0.7)
    bx.text(0.0, 0.20,
            "这就是「场级」的含义：\n不是让每台机都发得更多，\n而是让全场加总更多。",
            fontsize=13, color=GRAY, linespacing=1.95)
    save(fig, "g20_yaw_tradeoff")


# ── g21 两个控制任务不能混 ──────────────────────────────────────────────
def g21():
    fig = plt.figure(figsize=FS)
    frame(fig, "两条控制线要分开讲：一条管偏航、一条管桨距",
          "两条线用的后端、评价指标、证据强度都不一样，混在一起就会被追问",
          "依据：optimization_control/maddpg_wind_farm/{WIND_PINN_INTEGRATION,REACHABILITY_TRACKING}.md"
          " 与 docs/research/oracle/",
          "第 8 页 · 优化控制")

    ax = fig.add_axes([0.045, 0.13, 0.92, 0.64])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    cols = [
        (3, "① 场级偏航优化", BLUE,
         ["后端：FLORIS 4.6.6 GCH 真值",
          "方法：逐台贪心（±30°，5° 步）",
          "指标：全场功率 / kW",
          "结果：2702 → 3300 kW（+22.11%）",
          "证据：模拟真值，界面可现场复算"]),
        (51, "② 单机桨距跟踪（RL）", TEAL,
         ["后端：12 输入 PINN + 合成标签",
          "方法：MADDPG，三流各 16,384 步",
          "指标：跟踪 RMSE / kW",
          "结果：1083.6 → 449.7（−58.5%）",
          "证据：合成标签，未过 400 kW 门槛"]),
    ]
    for x, name, color, lines in cols:
        ax.add_patch(FancyBboxPatch((x, 26), 46, 60, boxstyle="round,pad=1.0",
                                    facecolor=PANEL, edgecolor=color, lw=2))
        b(ax.text(x + 3, 78, name, fontsize=16, color=INK), INK, 0.8)
        for i, line in enumerate(lines):
            ax.text(x + 3, 68 - i * 9.5, line, fontsize=12.5, color=GRAY)
    ax.add_patch(Rectangle((49.4, 30), 0.7, 52, facecolor=LINE, edgecolor="none"))
    ax.text(50, 18, "两条线的数字不能互换：偏航的 +22% 不能加到桨距的 −58.5% 上，反之亦然",
            ha="center", fontsize=13, color=RED)
    ax.text(50, 8, "答辩时被问到「那到底提升了多少」，先问一句「您指哪条线」。",
            ha="center", fontsize=12.5, color=GRAY)
    save(fig, "g21_two_control_lines")


# ── g22 当前问题与解决方案 ──────────────────────────────────────────────
def g22():
    """第 11 页主图。五条卡点，按「卡住整条链路的程度」排序。

    2026-10-24 复核后重写：原第 2 条「力矩失真」是 2026-08 的旧结论，本轮真正的
    卡点是「尾流区 13 m 网格 + 盘面平均取样」；并新增第 5 条「验收带未对齐」。
    """
    fig = plt.figure(figsize=FS)
    frame(fig, "当前问题与应对：五条卡点，每条都有下一步动作",
          "问题按「卡住整条链路的程度」排序；写的是下一步做什么，不是愿望",
          "依据：EVID-2026-003 §4.1.1（取样复核）　｜　田铭雨《中期答辩_仿真部分总结》§5.2（加密方案）"
          "　｜　20261022_random_wind_training（训练门槛）",
          "第 11 页 · 当前问题与解决方案")

    ax = fig.add_axes([0.045, 0.105, 0.92, 0.70])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    items = [
        ("① 标签全是代理或合成",
         "训练标签来自 FLORIS 与自建合成教师模型；没有任何 CFD 或实测标签",
         "修 Fluent 小算例，形成可追溯校验集", RED),
        ("② 网格与取样口径",
         "尾流区单元 13 m，解析不出盘面亏损；盘面 648 点中四成越界",
         "尾流区加密到 2.0–2.5 m + 取样口径重写", RED),
        ("③ 训练成本与泛化",
         "三条训练流均未过 400 kW 门槛，慢变场仍落后 PI",
         "先补样本再扩预算；分场景重跑对照", AMBER),
        ("④ 输入语义未冻结",
         "坐标口径（g18）与来流口径（g07）的映射未核对；rad/rpm 未统一",
         "冻结字段表与单位，补单元测试", AMBER),
        ("⑤ 验收带未对齐",
         "P2/P1 合格带：仿真侧 0.50–0.65，本项目 FLORIS 基准 0.222，差一个量级",
         "加密前先谈拢判据，否则是 450–600 万网格返工", BLUE),
    ]
    for i, (name, problem, plan, color) in enumerate(items):
        y0 = 92 - i * 17.6
        ax.add_patch(FancyBboxPatch((0, y0 - 13), 100, 15.2, boxstyle="round,pad=0.5",
                                    facecolor=PANEL, edgecolor=LINE, lw=1.1))
        ax.add_patch(Rectangle((0.4, y0 - 13), 0.9, 15.2, facecolor=color,
                               edgecolor="none"))
        b(ax.text(3.2, y0 - 3.2, name, fontsize=13.5, color=INK), INK, 0.7)
        ax.text(3.2, y0 - 10.2, problem, fontsize=11, color=GRAY)
        ax.text(58, y0 - 7.5, "→  " + plan, fontsize=11, color=color)
    ax.text(50, 0.5, "排序原则：先解决「没有真实标签」与「网格/取样」，其余问题在它们之后才有意义",
            ha="center", fontsize=12, color=GRAY)
    save(fig, "g22_problems_actions")


# ── g23 演示界面（重新裁切 + 数值口径图例）──────────────────────────────
def g23():
    """第 10 页主图：界面实拍（重新裁切）+ 面板数值的正确含义。

    2026-10-24 用户要求重做。原 PPT 把左栏面板读成「全场发电量 1.2 MW /
    当前风速 30.1 / 增量 6.0 / 运行状态 25%」，实际分别是
    演示占位功率 / 发电机温度 30.1 ℃ / 等效满发小时 6.0 h / 机组状态矩阵载荷。
    本图把「可引用的结果值」与「面板占位值」分成两块，避免再次误读。
    """
    src = SHOT / "r44_demo_step4.png"
    shot = Image.open(src).convert("RGB")
    # 只保留右侧「七步流程 + 模型建议 / 参考复核」面板。
    # 左边界按像素实测：x≈1245 是面板与 3D 场景的分界（1200–1240 列均亮度 258→274，
    # 1245 起降到 54），早先裁 1440 会把「模型建议」那一栏和总功率列切掉。
    crop = shot.crop((1245, 0, 1915, 720))

    fig = plt.figure(figsize=FS)
    frame(fig, "界面演示：七步流程走通，模型建议与参考复核并列",
          "第 4 步「求解优化」实拍　·　1×3 串列（T01→T02→T03，北→南）、8 m/s 北风、TI 6%",
          "截图来源：docs/research/img/r44_demo_step4.png（twin/?demo=1 第 4 步浏览器实拍）"
          "　｜　界面为演示工具，非 SCADA、非实时控制",
          "第 10 页 · 可视化与系统集成", TAG_UI)

    # 左：界面裁切
    ax = fig.add_axes([0.045, 0.115, 0.44, 0.66])
    ax.axis("off")
    ax.imshow(np.asarray(crop))
    ax.add_patch(Rectangle((-0.004, -0.004), 1.008, 1.008, transform=ax.transAxes,
                           facecolor="none", edgecolor=LINE, lw=2))
    ax.text(0.5, -0.055, "界面右侧面板原样截取（未改字）", transform=ax.transAxes,
            ha="center", fontsize=11.5, color=MUTED)

    # 右：两栏口径说明
    bx = fig.add_axes([0.505, 0.115, 0.45, 0.66])
    bx.set_xlim(0, 1)
    bx.set_ylim(0, 1)
    bx.axis("off")

    bx.add_patch(FancyBboxPatch((0.0, 0.585), 1.0, 0.395, boxstyle="round,pad=0.012",
                                facecolor=PANEL, edgecolor=TEAL, lw=1.6))
    b(bx.text(0.035, 0.935, "可引用的结果值", fontsize=15, color=TEAL), TEAL, 0.7)
    rows_ok = [
        ("模型建议（代理 · GCH 内核）", "3,299.8 kW"),
        ("参考复核（FLORIS 4.6.6 独立算）", "3,299.8 kW"),
        ("逐台：T01 / T02 / T03", "1339.9 / 847.2 / 1112.7 kW"),
        ("本步优化计时（界面内单次）", "5.5 ms"),
    ]
    for i, (k, v) in enumerate(rows_ok):
        y = 0.855 - i * 0.078
        bx.text(0.035, y, k, fontsize=11.5, color=GRAY)
        b(bx.text(0.66, y, v, fontsize=13, color=INK), INK, 0.5)

    bx.add_patch(FancyBboxPatch((0.0, 0.245), 1.0, 0.305, boxstyle="round,pad=0.012",
                                facecolor="#f7f8fa", edgecolor=MUTED, lw=1.3))
    bx.text(0.035, 0.505, "左侧 HUD 面板值是演示占位，不作结论", fontsize=13, color=GRAY)
    rows_demo = [
        ("1.2 MW　→ 全场功率总览（面板带「演示」角标）", ),
        ("30.1 ℃　→ 发电机温度峰值，不是风速", ),
        ("6.0 h　→ 等效满发小时，不是增量百分比", ),
        ("3 / 3 台　→ 运行机组数（25% 是载荷矩阵值）", ),
    ]
    for i, (k,) in enumerate(rows_demo):
        bx.text(0.05, 0.425 - i * 0.055, k, fontsize=11, color=GRAY)

    bx.text(0.0, 0.16, "界面是演示工具，不是实时控制系统：", fontsize=13.5, color=RED)
    bx.text(0.0, 0.075,
            "5.5 ms 只代表界面内单次寻优，数据接口、执行器速率与闭环时延\n"
            "都没有做过实时性验证。全片不使用「实时控制」「毫秒级控制」。",
            fontsize=11.5, color=GRAY, linespacing=1.7)
    save(fig, "g23_ui_demo")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
