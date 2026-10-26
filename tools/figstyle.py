#!/usr/bin/env python3
"""科研出图公共样式（2026-10-26，按 figures4papers / scientific-figure-making 规范落到本项目）。

来源与取舍
----------
参照 [ChenLiu-1996/figures4papers](https://github.com/ChenLiu-1996/figures4papers) 的
`scientific-figure-making` 技能（`references/design-theory.md`、`api.md`、`common-patterns.md`），
取其**可移植的规范**，不搬它的演讲风格（那套 45×12 超宽画布是给论文横排多指标用的，
答辩 PPT 是 16:9 固定版式，照搬会挤死中文）。

**照做**的：
  1. 语义配色：主方法=蓝（`#0F4D92`）、基线/对照=中性灰、改进=绿、反向/落后=砖红、高亮只用一次；
  2. 脊线只留左/下，线宽 2.2；图例一律去框（`legend.frameon=False`）；
  3. y 轴**动态收紧**到数据范围（不再从 0 拉满），差异才看得见；
  4. 柱状图带描边（`edgecolor` + `linewidth`），灰度打印可分辨；必要时加 hatch；
  5. 数值直接标在图上（in-place annotation），不靠网格线读数；
  6. 图例太大就单独给一个空白子图（dedicated legend panel），不许压数据；
  7. 导出 **PNG 300 dpi + 矢量 PDF**（`svg.fonttype='none'` 等价：PDF 里文字可编辑）；
  8. 先 `matplotlib.use("Agg")`，headless 环境不弹窗。

**不照搬**的：
  · 不用 LaTeX（`text.usetex`）—— 中文无法进 TeX，且沙箱无 TeX；
  · 不用 45×12 超宽画布 —— 答辩版式固定 16:9；
  · 不把 x 轴刻度全藏掉 —— 中文读者看「第 1 台 / 第 2 台」比看图例快。

字体（关键，之前踩过坑）
------------------------
原来的宋体（Songti SC，单字重 900）会：① 粗体无法区分（只能描边伪造）；② 缺 `⁻¹` 上标；
③ 观感偏「印刷品」而非「论文图」。现在优先用 **Noto Sans SC**（思源黑体，400/700 两档真字重）：

    ~/.fonts/NotoSansSC-cn-400.ttf
    ~/.fonts/NotoSansSC-cn-700.ttf

这两份从 npm 包 `@fontsource/noto-sans-sc` 的 `chinese-simplified-{400,700}-normal.woff`
转成 TTF 得来（`fontTools`，已改 name 表使 400/700 分别注册为 Regular/Bold）。
换机器没有这两份时，自动回退到仓库自带的 Songti（仍能出图，只是没有真粗体）。
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# ── 配色：figures4papers 语义色 + 本项目补充 ──────────────────────────────
PALETTE = {
    # 主方法 / 关键结果（蓝）
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "blue_light": "#9FC3E0",
    # 改进 / 正向（绿）
    "green_1": "#DDF3DE",
    "green_2": "#AADCA9",
    "green_3": "#8BCF8B",
    "green_deep": "#3F7A4B",
    # 对照 / 反向（红）
    "red_1": "#F6CFCB",
    "red_2": "#E9A6A1",
    "red_strong": "#B64342",
    # 中性（基线、网格、文字）
    "neutral": "#CFCECE",
    "gray_mid": "#767676",
    "muted": "#8C8C8C",
    "gray_dark": "#4D4D4D",
    "ink": "#1F1F1F",
    "line": "#E3E3E3",
    "panel": "#F5F7FA",
    "bg": "#FFFFFF",
    # 单一高亮（全篇只用一次）
    "highlight": "#FFD700",
    # 本项目补充：第三条曲线 / 第二台机
    "teal": "#42949E",
    "violet": "#9A4D8E",
    "amber": "#D9862A",
}

# 语义别名：图里一律用「角色」而不是色号，换配色只改这一张表
ROLE = {
    "ours": PALETTE["blue_main"],      # 我们 / 训练后 / 主方法
    "ours_light": PALETTE["blue_secondary"],
    "baseline": PALETTE["gray_mid"],   # PI、固定桨距等对照
    "baseline_light": PALETTE["neutral"],
    "alt": PALETTE["teal"],            # 另一条同等重要的曲线
    "alt2": PALETTE["amber"],
    "alt3": PALETTE["violet"],
    "better": PALETTE["green_deep"],   # 更好 / 改进
    "worse": PALETTE["red_strong"],    # 更差 / 落后 / 超限
    "ink": PALETTE["ink"],
    "gray": PALETTE["gray_mid"],
    "muted": "#8C8C8C",
    "line": PALETTE["line"],
    "panel": PALETTE["panel"],
}

# 证据等级角标（答辩纪律：角标与口播必须同词）
TAG_SIM = ("模拟真值 · FLORIS", PALETTE["blue_main"])
TAG_SYN = ("合成标签 · 非物理精度", PALETTE["amber"])
TAG_CFD = ("CFD 后处理 · 非实测", PALETTE["violet"])
TAG_OBS = ("实测记录", PALETTE["green_deep"])
TAG_UI = ("界面演示 · 非实时控制", PALETTE["blue_main"])

DPI = 300
FS = (16, 9)

_FONT_PREFERENCE = [
    (Path.home() / ".fonts" / "NotoSansSC-cn-400.ttf",
     Path.home() / ".fonts" / "NotoSansSC-cn-700.ttf"),
]


def use_cjk(root: Path | None = None) -> str:
    """装配字体。返回实际使用的字体族名，供脚本打印以便排查。"""
    from matplotlib import font_manager as fm

    family = None
    for regular, bold in _FONT_PREFERENCE:
        if regular.exists():
            fm.fontManager.addfont(str(regular))
            family = fm.FontProperties(fname=str(regular)).get_name()
            if bold.exists():
                fm.fontManager.addfont(str(bold))
            break
    if family is None and root is not None:
        fallback = root / "viz" / "site" / "assets" / "fonts" / "songti-sc-black.ttf"
        if fallback.exists():
            fm.fontManager.addfont(str(fallback))
            family = fm.FontProperties(fname=str(fallback)).get_name()

    # 拉丁与数字交给 DejaVu Sans（tabular 数字、±、µ、上标齐全），中文回退到 CJK 字体
    stack = ["DejaVu Sans"] + ([family] if family else ["sans-serif"])
    plt.rcParams.update({
        "font.family": stack,
        "font.sans-serif": stack,
        "font.size": 15,
        "axes.unicode_minus": False,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 2.2,
        "axes.edgecolor": PALETTE["gray_dark"],
        "axes.labelcolor": PALETTE["gray_mid"],
        "xtick.color": PALETTE["gray_mid"],
        "ytick.color": PALETTE["gray_mid"],
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.width": 1.6,
        "ytick.major.width": 1.6,
        "legend.frameon": False,
        "legend.fontsize": 12,
        "savefig.facecolor": PALETTE["bg"],
        "figure.facecolor": PALETTE["bg"],
        "pdf.fonttype": 42,      # 文字嵌入为 TrueType，PDF 里可选中/可编辑
        "ps.fonttype": 42,
    })
    return family or "(fallback)"


# ── 排版 ────────────────────────────────────────────────────────────────
def bold(t, lw: float = 0.0):
    """真粗体现在由 fontweight 提供；只有回退到单字重字体时才用描边补。"""
    if lw:
        t.set_path_effects([pe.withStroke(linewidth=lw, foreground=t.get_color())])
    return t


def _wrap(text: str, limit: int = 150) -> list[str]:
    """按显示宽度折行（中文一个字算两个半角）。"""
    lines, cur, cur_w = [], "", 0
    for ch in str(text).replace("**", ""):
        w = 1 if ord(ch) < 128 else 2
        if cur_w + w > limit and cur:
            lines.append(cur)
            cur, cur_w = "", 0
        cur += ch
        cur_w += w
    if cur:
        lines.append(cur)
    return lines


def frame(fig, title, subtitle="", footer="", kicker="", tag=None, reading=""):
    """16:9 版式：题注在上、角标在右下、读法与来源合并在页脚。

    reading（一句话「怎么读」）与 footer（数据来源 + 口径）会合成一个自底部向上的文本块，
    避免两段字互相压 —— 第一批图踩过这个坑。
    """
    fig.patch.set_facecolor(PALETTE["bg"])
    if kicker:
        fig.text(0.045, 0.958, kicker, color=PALETTE["muted"], fontsize=13, va="top")
    bold(fig.text(0.045, 0.920, title, color=PALETTE["ink"], fontsize=29, va="top",
                  fontweight="bold"))
    fig.add_artist(Rectangle((0.045, 0.906), 0.052, 0.0032, transform=fig.transFigure,
                             facecolor=PALETTE["blue_main"], edgecolor="none"))
    if subtitle:
        fig.text(0.045, 0.856, subtitle.replace("**", ""), color=PALETTE["gray_mid"],
                 fontsize=15, va="top")

    block = "\n".join(x for x in (reading, footer) if x)
    if block:
        lines = _wrap(block)
        fig.text(0.045, 0.030, "\n".join(lines), color=PALETTE["muted"], fontsize=11,
                 va="bottom", linespacing=1.5)
        if len(lines) > 4:
            print(f"    ! 页脚 {len(lines)} 行，可能与坐标轴标签相压：{title[:16]}")
    fig.add_artist(Rectangle((0.045, 0.086), 0.760, 0.0012, transform=fig.transFigure,
                             facecolor=PALETTE["line"], edgecolor="none"))

    if tag:
        text, color = tag
        fig.add_artist(Rectangle((0.80, 0.026), 0.155, 0.040, transform=fig.transFigure,
                                 facecolor=color, alpha=0.10, edgecolor="none"))
        fig.text(0.877, 0.046, text, color=color, fontsize=11, ha="center", va="center")


def clean(ax, grid_axis=None, linewidth: float = 2.2):
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_linewidth(linewidth)
        ax.spines[s].set_color(PALETTE["gray_dark"])
    if grid_axis:
        ax.grid(axis=grid_axis, color=PALETTE["line"], lw=0.8)
        ax.set_axisbelow(True)
    ax.tick_params(labelsize=12)


def tight_ylim(ax, values, margin: float = 0.08, floor_zero: bool = False):
    """动态收紧 y 轴（figures4papers 的 dynamic y-axis scaling）：差异才看得见。"""
    import numpy as np

    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return
    lo, hi = float(v.min()), float(v.max())
    pad = (hi - lo) * margin or max(abs(hi) * 0.02, 1e-9)
    ax.set_ylim(0 if floor_zero else lo - pad, hi + pad)


def annotate(ax, x, y, text, color=None, fontsize=11, dx=0, dy=8, ha="center", **kw):
    """把数值直接标在图上（in-place annotation），不让读者去数网格线。"""
    ax.annotate(text, (x, y), textcoords="offset points", xytext=(dx, dy),
                ha=ha, color=color or PALETTE["ink"], fontsize=fontsize,
                fontweight="bold", **kw)


def legend_panel(fig, rect, handles, labels, ncol=1, fontsize=12, title=""):
    """独立图例子图：多曲线时图例不许压数据。"""
    ax = fig.add_axes(rect)
    ax.set_axis_off()
    if title:
        ax.text(0, 1.02, title, fontsize=fontsize, color=PALETTE["gray_mid"],
                va="bottom", fontweight="bold")
    ax.legend(handles, labels, ncol=ncol, frameon=False, fontsize=fontsize,
              loc="upper left", borderaxespad=0.0, handlelength=2.2,
              labelspacing=0.9 if ncol == 1 else 1.2,
              bbox_to_anchor=(0, 0.88))


# ── 导出 ────────────────────────────────────────────────────────────────
def save(fig, out_dir: Path, name: str, pdf: bool = True, dpi: int = DPI) -> list[Path]:
    """PNG（300 dpi）+ 矢量 PDF。PDF 给投稿/放大用，PNG 给 PPT。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    png = out_dir / f"{name}.png"
    fig.savefig(png, dpi=dpi, facecolor=PALETTE["bg"])
    paths.append(png)
    if pdf:
        p = out_dir / f"{name}.pdf"
        fig.savefig(p, facecolor=PALETTE["bg"])
        paths.append(p)
    plt.close(fig)
    kb = png.stat().st_size / 1024
    print(f"  {name}.png  {kb:.0f} KB" + (f"  + .pdf" if pdf else ""))
    return paths


def rows(path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def export_zip(zip_path: Path, members: list[tuple[Path, str]], note: str = "") -> Path:
    """把一组文件打成 zip（组内路径可重命名）。"""
    import zipfile

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in members:
            z.write(src, arc)
        if note:
            z.writestr("README.txt", note)
    return zip_path


def have_pdf_support() -> bool:
    return shutil.which("pdflatex") is not None


# ══════════════════════════════════════════════════════════════════════
# 论文插图模式（2026-10-26 增补）
# ----------------------------------------------------------------------
# 与上面的「答辩整页」不同：期刊/学位论文里的插图是 figure，不是 slide
#   · 没有页眉 kic​ker、没有大标题、没有页脚条、没有右下角证据角标；
#   · 画面比例按单栏 / 双栏（3.3 in、6.8 in），不是 16:9；
#   · 字号 7–9 pt，线宽 0.8，四边脊线闭合（full box），刻度朝内 —— 这是期刊排版惯例；
#   · 中文用宋体（Songti SC），拉丁与数字用衬线体（DejaVu Serif），接近中文期刊的正文/图中字体；
#   · 面板标号 (a)(b)(c) 用轴坐标写，不占标题位；
#   · 导出 400 dpi PNG + 矢量 PDF。
# 证据等级与「不能说什么」不写在图上，统一写在 docs/defense/paper_captions.md（caption 就是论文学术规范的位置）。
# ══════════════════════════════════════════════════════════════════════

PAPER_SINGLE = (3.35, 2.55)   # 单栏（约 85 mm）
PAPER_WIDE = (6.90, 2.45)     # 双栏（约 175 mm）
PAPER_SQUARE = (4.30, 3.60)

# 拉丁/数字：DejaVu Serif（衬线、上标齐全）；中文：思源宋体 400/700
_SERIF_STACK = ["DejaVu Serif"]
_SERIF_CJK = [
    (Path.home() / ".fonts" / "NotoSerifSC-cn-400.ttf",
     Path.home() / ".fonts" / "NotoSerifSC-cn-700.ttf"),
]


def use_serif(root: Path | None = None) -> str:
    """论文插图字体：中文宋体 + 拉丁/数字衬线。"""
    from matplotlib import font_manager as fm

    family = None
    for regular, bold in _SERIF_CJK:
        if regular.exists():
            fm.fontManager.addfont(str(regular))
            if bold.exists():
                fm.fontManager.addfont(str(bold))
            family = fm.FontProperties(fname=str(regular)).get_name()
            break
    if family is None and root is not None:
        fallback = root / "viz" / "site" / "assets" / "fonts" / "songti-sc-black.ttf"
        if fallback.exists():
            fm.fontManager.addfont(str(fallback))
            family = fm.FontProperties(fname=str(fallback)).get_name()
    stack = _SERIF_STACK + ([family] if family else ["sans-serif"])
    plt.rcParams.update({
        "font.family": stack,
        "font.serif": stack,
        "font.size": 8,
        "mathtext.fontset": "dejavuserif",
        "axes.unicode_minus": False,
        "axes.linewidth": 0.8,
        "axes.spines.right": True,
        "axes.spines.top": True,
        "axes.edgecolor": "#222222",
        "axes.labelcolor": "#222222",
        "axes.labelsize": 8.5,
        "axes.titlesize": 9,
        "axes.titlepad": 4,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "xtick.minor.width": 0.6,
        "ytick.minor.width": 0.6,
        "xtick.top": True,
        "ytick.right": True,
        "xtick.major.size": 3.0,
        "ytick.major.size": 3.0,
        "legend.frameon": False,
        "legend.fontsize": 7,
        "legend.handlelength": 1.8,
        "legend.labelspacing": 0.35,
        "legend.borderaxespad": 0.3,
        "lines.linewidth": 1.1,
        "lines.markersize": 3.4,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    return family or "(fallback)"


def paper_axes(fig, rect):
    """论文风格子图：四边闭合 + 刻度朝内。"""
    ax = fig.add_axes(rect)
    for side in ("left", "bottom", "right", "top"):
        ax.spines[side].set_linewidth(0.8)
        ax.spines[side].set_color("#222222")
    ax.tick_params(which="both", direction="in", top=True, right=True)
    return ax


def panel_label(ax, text, x=-0.005, y=1.02, fontsize=9):
    """(a) (b) (c) 面板标号 —— 论文里写在数据区左上角，不占标题。"""
    ax.text(x, y, text, transform=ax.transAxes, fontsize=fontsize, fontweight="bold",
            ha="left", va="bottom", color="#111111")


def paper_save(fig, out_dir: Path, name: str, dpi: int = 400) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"{name}.png", out_dir / f"{name}.pdf"]
    fig.savefig(paths[0], dpi=dpi, facecolor="white")
    fig.savefig(paths[1], facecolor="white")
    plt.close(fig)
    print(f"  {name}  ({paths[0].stat().st_size / 1024:.0f} KB, {paths[1].stat().st_size / 1024:.0f} KB pdf)")
    return paths
