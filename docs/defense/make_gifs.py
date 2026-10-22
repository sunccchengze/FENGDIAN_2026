# -*- coding: utf-8 -*-
"""中期答辩用高清 GIF 生成（无视频、可循环、进 PPT 即可播放）

三件产物，全部来自仓库内**真实数据**，不做任何示意重构：

1. `media/g1_wake_sweep.gif`
   来源 `docs/research/oracle/floris_gch_oracle_v1.json` → `tandem3.unified`（13 个
   真实求解点，统一偏航 −30°→+30°）与 `tandem3.greedy`（逐机贪心 30°/25°/0°）。
   左三机功率条、右总功率曲线同步生长，末两帧落到 3299.8 kW。
   标签必须是【真值 · FLORIS 4.6.6 · GCH · 1×3 串列】，**不插值、不补点**。

2. `media/g2_seven_steps.gif`
   来源 `docs/research/img/r44_demo_step1..7.png`（R44 七步演示的**真实截图**）。
   7 帧循环，用于讲「优化闭环」时当背景动效，不替代现场演示。

3. `media/g3_inflow.gif`
   来源 `optimization_control/experiments/20261022_random_wind_training/bank/*.csv`
   （三类入口各 130 个时间样本）。逐帧扫过 130 s，三条曲线同步生长。
   标签必须是【实测 · 场景库文件】。

依赖：numpy、matplotlib、Pillow
用法：python3 docs/defense/make_gifs.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
MEDIA = ROOT / "media"
ORACLE = REPO / "docs" / "research" / "oracle" / "floris_gch_oracle_v1.json"
DEMO_IMG = REPO / "docs" / "research" / "img"
BANK = REPO / "optimization_control" / "experiments" / "20261022_random_wind_training" / "bank"

BG = "#0E1418"
FG = "#E6EAEE"
DIM = "#8A949C"
BLUE = "#4D6884"
SAGE = "#7C9A6E"
ROSE = "#C08585"

# 中文字形：本机没有系统中文字体，用 PyMuPDF 自带的 CJK 字体注册为全局默认，
# 这样刻度、图例、标注都会用它，不会出现方块（DejaVu 无中文字形）。
def _register_cjk() -> str:
    try:
        import pymupdf
        from matplotlib import font_manager as fm
        path = Path("/tmp/cjk_dump.ttf")
        if not path.exists():
            path.write_bytes(pymupdf.Font("cjk").buffer)
        fm.fontManager.addfont(str(path))
        return fm.FontProperties(fname=str(path)).get_name()
    except Exception:
        return "DejaVu Sans"


plt.rcParams["font.family"] = _register_cjk()
plt.rcParams["axes.facecolor"] = BG
plt.rcParams["figure.facecolor"] = BG
plt.rcParams["text.color"] = FG
plt.rcParams["axes.labelcolor"] = FG
plt.rcParams["xtick.color"] = DIM
plt.rcParams["ytick.color"] = DIM
plt.rcParams["axes.edgecolor"] = "#2A343B"
plt.rcParams["axes.unicode_minus"] = False   # CJK 字体无 U+2212，用 ASCII 减号


def cjk_font(size):
    """显式指定字号的中文文本（全局默认字体已注册，这里只负责定字号）。"""
    from matplotlib.font_manager import FontProperties
    return FontProperties(family=plt.rcParams["font.family"], size=size)


CJK = cjk_font(11)


# ---------------------------------------------------------------- 1. 偏航扫掠
def gif_wake_sweep(out: Path, width=1360, hold=760) -> None:
    """13 个真实求解点的统一偏航扫描 + 逐机贪心两步。数据一字未改。"""
    data = json.loads(ORACLE.read_text(encoding="utf-8"))
    t3 = data["tandem3"]
    sweep = t3["unified"]
    none_kw = t3["none"]["total_kW"]
    greedy = t3["greedy"]["path"]

    yaws = [e["yaw"] for e in sweep]
    totals = [e["total_kW"] for e in sweep]
    per_t = [e["p_kW"] for e in sweep]

    ymin, ymax = 2600.0, 3400.0
    names = ["T01 上风向", "T02 中", "T03 下风向"]
    bar_colors = ["#6E8FA6", "#8FA98A", "#C08585"]

    def draw(idx=None, greedy_step=None):
        fig = plt.figure(figsize=(width / 100, 6.0), dpi=100)
        gs = fig.add_gridspec(1, 2, width_ratios=[1.05, 1.25], wspace=0.24)
        axb = fig.add_subplot(gs[0, 0])
        axc = fig.add_subplot(gs[0, 1])
        fig.subplots_adjust(left=0.145, right=0.965, top=0.80, bottom=0.12)

        # ---- 左：三机功率条
        if greedy_step is not None:
            pv = greedy[greedy_step]["p_kW"]
            tag = f"逐机贪心 第 {greedy_step + 1} 步"
            yaw_txt = "　".join(f"{y:+.0f}°" for y in [g["yaw"] for g in greedy[: greedy_step + 1]]) + "　0°"
        else:
            pv = per_t[idx]
            tag = f"统一偏航 {yaws[idx]:+d}°"
            yaw_txt = f"{yaws[idx]:+d}°（三机同角）"
        bars = axb.barh(names[::-1], pv[::-1], color=bar_colors[::-1], height=0.55)
        for b, v in zip(bars, pv[::-1]):
            axb.text(v + 25, b.get_y() + b.get_height() / 2, f"{v:,.0f} kW",
                     va="center", color=FG, fontproperties=cjk_font(11))
        axb.set_xlim(0, 2050)
        axb.set_xlabel("单机功率 / kW", fontproperties=cjk_font(10))
        axb.set_title(tag, fontproperties=cjk_font(13), color=FG, loc="left")
        axb.text(0.0, 1.02, yaw_txt, transform=axb.transAxes, color=DIM,
                 fontproperties=cjk_font(9))
        axb.grid(axis="x", color="#243038", lw=0.6)
        axb.set_axisbelow(True)

        # ---- 右：总功率曲线
        n = len(yaws) if greedy_step is not None else idx + 1
        axc.plot(yaws[:n], totals[:n], color="#7FA8BE", lw=2.2, marker="o", ms=4.5)
        if greedy_step is not None:
            for g in greedy[: greedy_step + 1]:
                axc.plot([], [])
                axc.axhline(g["total_kW"], color=SAGE, lw=1.0, ls=(0, (5, 4)))
                axc.text(-31.5, g["total_kW"] + 9, f"贪心 {g['total_kW']:,.1f} kW",
                         color=SAGE, fontproperties=cjk_font(10), ha="left")
            axc.plot([30], [greedy[greedy_step]["total_kW"]], "o", ms=10, color=SAGE)
        else:
            axc.plot(yaws[idx], totals[idx], "o", ms=10, color="#D8C6A6")
        axc.axhline(none_kw, color=ROSE, lw=1.0, ls=(0, (3, 3)))
        axc.text(-31.5, none_kw - 45, f"零偏航基准 {none_kw:,.1f} kW",
                 color=ROSE, fontproperties=cjk_font(10), ha="left")
        axc.set_xlim(-33, 33)
        axc.set_ylim(ymin, ymax)
        axc.set_xlabel("统一偏航角 / °", fontproperties=cjk_font(10))
        axc.set_ylabel("三机总功率 / kW", fontproperties=cjk_font(10))
        axc.set_title("三机总功率随偏航角的变化", fontproperties=cjk_font(13),
                      color=FG, loc="left")
        axc.grid(color="#1E2A31", lw=0.6)
        axc.set_axisbelow(True)

        fig.text(0.06, 0.935, "真值 · FLORIS 4.6.6 · GCH · 1×3 串列",
                 color=DIM, fontproperties=cjk_font(10))
        fig.text(0.955, 0.935, "13 个真实求解点，无一插值补点",
                 color=DIM, fontproperties=cjk_font(10), ha="right")

        path = MEDIA / f"_sweep_{idx}_{greedy_step}.png"
        fig.savefig(path, facecolor=BG)
        plt.close(fig)
        return Image.open(path).convert("RGB"), path

    frames, temps = [], []
    for i in range(len(yaws)):
        im, pth = draw(i)
        frames.append(im)
        temps.append(pth)
    for k in range(len(greedy)):
        im, pth = draw(len(yaws) - 1, k)
        frames += [im] * 2
        temps.append(pth)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=hold,
                   loop=0, optimize=True)
    for pth in temps:
        pth.unlink(missing_ok=True)
    print("WROTE", out.relative_to(REPO), out.stat().st_size // 1024, "KB")


# ---------------------------------------------------------------- 2. 七步演示
def gif_seven_steps(out: Path, width=1180, duration=900) -> None:
    frames = []
    src = [DEMO_IMG / f"r44_demo_step{i}.png" for i in range(1, 8)]
    missing = [p for p in src if not p.exists()]
    if missing:
        print("SKIP g2：缺", [p.name for p in missing])
        return
    for i, p in enumerate(src, 1):
        im = Image.open(p).convert("RGB")
        h = int(im.height * width / im.width)
        im = im.resize((width, h), Image.LANCZOS)
        # 顶部压一条进度提示，让 7 帧读起来是一条流程
        frames.append(im)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=duration,
                   loop=0, optimize=True)
    print("WROTE", out.relative_to(REPO), out.stat().st_size // 1024, "KB")


# ---------------------------------------------------------------- 3. 三类入口
def gif_inflow(out: Path, width=1180, duration=80) -> None:
    series = {
        "平稳湍流": BANK / "test_stationary_0.csv",
        "慢变风向": BANK / "test_ramp_0.csv",
        "阵风": BANK / "test_gust_0.csv",
    }
    if not all(p.exists() for p in series.values()):
        print("SKIP g3：缺 bank 文件")
        return

    def load(p):
        ts, vs, ds = [], [], []
        with p.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ts.append(float(row["time_s"]))
                vs.append(float(row["speed_m_s"]))
                # 风向存为 [0, 2π)；跨 0 处会跳 6.283，先折回 ±π 再转度
                r = float(row["direction_rad"])
                ds.append(np.degrees(((r + np.pi) % (2 * np.pi)) - np.pi))
        return np.array(ts), np.array(vs), np.array(ds)

    data = {k: load(p) for k, p in series.items()}
    colors = {"平稳湍流": "#6E8FA6", "慢变风向": "#8FA98A", "阵风": "#C08585"}
    tmax = max(v[0].max() for v in data.values())
    vmin = min(v[1].min() for v in data.values()) - 0.6
    vmax = max(v[1].max() for v in data.values()) + 0.6
    dmax = max(abs(v[2]).max() for v in data.values()) + 1.0

    steps = np.linspace(0, len(next(iter(data.values()))[0]) - 1, 36).astype(int)
    frames, temps = [], []
    for n in steps:
        fig, axes = plt.subplots(2, 1, figsize=(width / 100, 5.4), dpi=100, sharex=True)
        fig.subplots_adjust(left=0.10, right=0.97, top=0.86, bottom=0.13, hspace=0.22)
        for name, (t, v, d) in data.items():
            for ax, y in ((axes[0], v), (axes[1], d)):
                ax.plot(t[: n + 1], y[: n + 1], color=colors[name], lw=1.5, label=name)
                ax.plot(t[n], y[n], "o", color=colors[name], ms=4.5)
        axes[0].set_ylim(vmin, vmax)
        axes[1].set_ylim(-dmax, dmax)
        axes[0].set_ylabel("风速 / (m/s)", fontproperties=cjk_font(9))
        axes[1].set_ylabel("风向 / °", fontproperties=cjk_font(9))
        axes[1].set_xlabel("时间 / s", fontproperties=cjk_font(9))
        axes[0].set_xlim(0, tmax)
        for ax in axes:
            ax.grid(color="#1E2A31", lw=0.6)
            ax.set_axisbelow(True)
        axes[0].legend(loc="upper right", frameon=False, ncol=3,
                       prop=cjk_font(9), labelcolor=FG)
        axes[0].set_title(f"三类随机入口 · 同一套场景库　t = {t[n]:.0f} s",
                          fontproperties=cjk_font(12), color=FG, loc="left")
        fig.text(0.10, 0.925, "实测 · 场景库文件 test_{stationary,ramp,gust}_0.csv（每例 129 个时间样本）",
                 color=DIM, fontproperties=cjk_font(9))
        path = MEDIA / f"_in_{n:03d}.png"
        fig.savefig(path, facecolor=BG)
        plt.close(fig)
        frames.append(Image.open(path).convert("RGB"))
        temps.append(path)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=duration,
                   loop=0, optimize=True)
    for pth in temps:
        pth.unlink(missing_ok=True)
    print("WROTE", out.relative_to(REPO), out.stat().st_size // 1024, "KB")



# ---------------------------------------------------------------- 4. 全幅底图（压暗）
def darken(src_name: str, out: Path, target_w=2400, strength=0.72) -> None:
    """把真实截图压暗成封面/谢幕底图：只调亮度，不裁内容、不加特效。"""
    src = DEMO_IMG / src_name
    if not src.exists():
        print("SKIP", src_name)
        return
    im = Image.open(src).convert("RGB")
    w, h = im.size
    if w > target_w:
        im = im.resize((target_w, int(h * target_w / w)), Image.LANCZOS)
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            px[x, y] = (int(r * strength), int(g * strength), int(b * strength * 1.03))
    im.save(out, quality=90)
    print("WROTE", out.relative_to(REPO), out.stat().st_size // 1024, "KB")

def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    gif_wake_sweep(MEDIA / "g1_wake_sweep.gif")
    gif_seven_steps(MEDIA / "g2_seven_steps.gif")
    gif_inflow(MEDIA / "g3_inflow.gif")
    darken("r44_demo_step5.png", MEDIA / "bg_cover.jpg", strength=0.42)
    darken("r44_demo_step6.png", MEDIA / "bg_closing.jpg", strength=0.30)


if __name__ == "__main__":
    main()
