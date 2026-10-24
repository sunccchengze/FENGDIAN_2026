#!/usr/bin/env python3
"""把中期答辩所需的**全部素材**打成一个 zip（进仓库，随分支一起推送）。

与上一版（`defense_assets_20261024.zip`，只有图 + 3 份文档）的区别：
本包是「做 PPT 的人打开就能干活」的整包 —— 多了**逐页制作规格**、**问答备忘**、
**照念口播稿**、**证据卡**、**第 9 页源数据**、**出图与解包脚本**。

为什么是脚本而不是手工压缩：
- 包内目录结构、校验和都由脚本决定，换机器重跑结果一致；
- 素材更新后重跑一次即可，不会出现「包里的图和仓库里的图不是同一版」；
- 打完之后立即自检（清单、sha256、图片格式与尺寸、逐字节新鲜度），不合格就不落盘。

用法：
    python3 tools/build_defense_pack.py            # 生成 zip
    python3 tools/build_defense_pack.py --check    # 只校验已有 zip

输出：docs/defense/defense_full_pack_20261024.zip
      包内顶层目录「中期答辩_全素材_20261024/」

zip 文件名用 ASCII（中文名在命令行与 URL 里要百分号转义，容易传错）；包内目录名仍是中文。
"""
from __future__ import annotations

import hashlib
import shutil
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/defense/assets"
DEF = ROOT / "docs/defense"
PACK_DATE = "20261024"
OUT_ZIP = DEF / f"defense_full_pack_{PACK_DATE}.zip"
TOP = f"中期答辩_全素材_{PACK_DATE}"

README = """中期答辩 · 全素材包（2026-10-24）
============================================

这是给「做 PPT 的人」用的整包，不是成品 PPT（成品由组内自己做）。
解压后按下面的顺序看，半小时能上手。

目录
----
  00_先读我.txt                ← 本文件
  01_逐页制作规格_14页.md      ★ 主文件：每页「屏上放什么 / 用哪张图 / 口播念什么 / 不要说 / 时间」
  02_问答备忘.md               ★ Q1–Q10 高频问 + 每页 2–3 条追问的标准答法，每条 ≤3 句
  03_口播稿_照念.txt           ★ 提词器版：全篇 1,394 字，分页并标「应到时间」
  04_初版大纲内容替换表.md      ← 你初版 14 页大纲逐页「哪句要改、改成什么、出处」
  05_答辩素材清单.md           ← 23 张图逐张的作用、关键数、出处、不能说什么
  06_项目记忆与现存问题.md      ← 真问题在哪、哪些数说出去会出事
  07_证据卡_EVID-2026-003.md    ← CFD 数据可用性判定（含 2026-10-24 的取样复核）
  figures/     23 张 PNG       ← 1920×1080，16:9，可直接拖进 PPT
  animated/     2 个 GIF       ← 七步演示逐帧、偏航扫描逐帧
  extracted/   12 张原图       ← 从 .docx / .pptx 里解出来的队友原始截图
  raw/          3 份源数据     ← 第 9 页那张图的 metrics.csv（240 行）+ summary + aggregate
  scripts/      3 个 .py       ← 出图、解包、打包脚本（只读仓库数据，不重跑实验）
  MANIFEST.sha256              ← 逐文件校验和


一、半小时怎么用
----
1.（5 分钟）读 01_ 开头两张表：「排片总表」和「时间检查点」。
   先认三件事：14 页定死、口播 1,394 字 ≈ 5 分 24 秒、含停顿计划 6 分 27 秒、硬上限 7 分。

2.（10 分钟）把 01_ 里 14 页的「屏上」代码块整块复制进 PPT。
   每块都已按最新口径改好，包括要加的小字和要删的旧数字。

3.（8 分钟）按 01_ 每页的「图」一行，插 figures/ 里的图。
   图右下角的口径角标（模拟真值 / 合成标签 / CFD 后处理 / 界面演示）不要裁掉——
   它和口播是配套的，裁掉就成了没有依据的声明。

4.（5 分钟）把 03_ 打印出来实念一遍，掐表记总长。
   超 7 分：按 01_ 末尾的「兜底砍句顺序」删括号里的句子，不要加速念。

5.（2 分钟）看 02_ 的 Q1–Q10，覆盖八成提问。


二、这批图的口径纪律（看图时请一起核）
----
每张图右下角有一个角标，四种说法，说的时候不能改：

  蓝「模拟真值 · FLORIS」      = FLORIS 算出来的，口播说「模拟真值」
  橙「合成标签 · 非物理精度」  = 标签由合成公式生成，口播必须带后半句
  紫「CFD 后处理 · 非实测」    = Fluent 算完导出的，不是实测，也不是精度证据
  蓝「界面演示 · 非实时控制」  = 浏览器截图，口播必须补「不是实时控制系统」

已经守住的几条（改稿时不要破）：
  · 没有把代理结果说成实测；
  · 没有把 449.72 说成「优于传统控制」——第 0 条流 492.28 仍高于 PI 的 477.54；
  · 58.5% 一律是**功率跟踪误差**下降，不是发电量增益；
  · 没有用「实时控制 / 毫秒级」，界面里的计时只说「界面内单次寻优」；
  · 三机串列 CFD 的阵列总功率、P2/P1 没有画进任何一张图，
    判否理由是「盘面平均与剖面的取样口径不可靠」（详见 07_ §4.1.1）；
  · 界面截图里「1.2 MW / 30.1 / 6.0 / 25%」四个数已逐条注正，
    不再当作发电量、风速、增量或运行状态引用。


三、23 张图的用途分工
----
进主线的 16 张（按 14 页顺序）：
  p2  g01 尾流损失曲线        p3  g04 技术路线
  p4  g05 模型选型（备 g06）   p5  g19 Fluent 现状
  p6  g18 PINN 结构            p7  g07 PINN 训练进展
  p8  g02 偏航扫描（或 g21 两条控制线）
  p9  g11 独立测试（配 g13 三处未达标）
  p10 g23 界面演示            p11 g22 五个卡点与动作
  p12 g16 下一阶段计划        p13 g14 证据链（或 g15 定位）

没进主线、被问到时才拿出来的 7 张：
  g03  偏航把尾流推开（横向 16 点，示意级，不当数据）
  g08  五段数据流架构（p3 的备选）
  g09  七步流程条（p10 的备选）
  g10  三条流验证误差均未过 400 kW 门槛（p7 追问时用）
  g12  按来流族拆开：阵风赢、慢变输
  g17  数据集覆盖 1,224 条（17 风速 × 24 风向 × 3 湍流度）
  g20  偏航的收益账：上游少发、下游多发

> 07_ 是内部核查记录，里面有组内人名与数据路径；会上**不要点名**，
> 一律说「仿真组交付的这批数据」。


四、不能用的素材
----
viz/figures_nature/ 那 18 张是 3×3 的旧口径（+24.04% / +67.26%），
本轮是 1×3，不能当结果上屏。本包已刻意不放。


五、图上数字怎么核
----
所有图都是脚本从仓库数据现算，没有手填。要改数字就改脚本常量再重画，
不要手改 PNG（改了图就和数据脱钩）。

  python3 scripts/make_defense_figures.py            # 重画全部 23 张
  python3 scripts/make_defense_figures.py g07 g19    # 只画指定几张
  python3 scripts/make_defense_figures.py gif        # 重画 2 个动图
  python3 scripts/extract_defense_assets.py          # 重新解出 12 张原图
  python3 scripts/build_defense_pack.py --check      # 校验包与仓库逐字节一致

依赖：matplotlib + numpy + pillow，中文用 NotoSansCJKsc-Regular.otf。
脚本只读仓库里已有的数据文件，不重跑实验、不改任何实验目录。
raw/metrics.csv 是第 9 页那张图的原始逐工况记录，可以直接复算 RMSE 与均值。


六、包里没有的东西
----
· 没有 .pptx / PDF —— 版式和成稿由组内自己做（当前只到大纲、讲稿、图）
· 没有视频 —— 两个 GIF 是逐帧拼接，不是录屏
· 没有外部文献原文 —— 所以外部数字只用文字写，没有画进图

—— 生成于 2026-10-24
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# 只打包这几个脚本，别把整个 tools/ 都算进去
SCRIPT_MAP = {
    "make_defense_figures.py": ROOT / "tools/make_defense_figures.py",
    "extract_defense_assets.py": ROOT / "tools/extract_defense_assets.py",
    "build_defense_pack.py": ROOT / "tools/build_defense_pack.py",
}

# 包内文档 → 仓库源文件
DOC_MAP = {
    "01_逐页制作规格_14页.md": DEF / "2026-10-24_逐页制作规格_14页.md",
    "02_问答备忘.md": DEF / "2026-10-24_问答备忘.md",
    "03_口播稿_照念.txt": DEF / "2026-10-24_口播稿_照念.txt",
    "04_初版大纲内容替换表.md": DEF / "2026-10-24_初版大纲内容替换表.md",
    "05_答辩素材清单.md": DEF / "2026-10-23_答辩素材清单.md",
    "06_项目记忆与现存问题.md": DEF / "2026-10-24_项目记忆与现存问题.md",
    "07_证据卡_EVID-2026-003.md": ROOT / "docs/evidence/EVID-2026-003_三机串列CFD数据可用性核查.md",
}

TEST_DIR = ROOT / "optimization_control/experiments/20261022_random_wind_training/test"
RAW_MAP = {
    "g11_independent_test_source.csv": TEST_DIR / "metrics.csv",
    "g11_test_summary.txt": TEST_DIR / "summary.txt",
    "g11_test_aggregate.csv": TEST_DIR / "aggregate.csv",
}

DIR_MAP = (
    (ASSETS / "generated", "figures", ".png"),
    (ASSETS / "animated", "animated", ".gif"),
    (ASSETS / "extracted", "extracted", None),
)


def build() -> int:
    if not ASSETS.exists():
        print(f"素材目录不存在：{ASSETS}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / TOP
        for sub in ("figures", "animated", "extracted", "raw", "scripts"):
            (stage / sub).mkdir(parents=True)

        for src_dir, dst, ext in DIR_MAP:
            if not src_dir.is_dir():
                print(f"ERROR 素材目录不存在：{src_dir.relative_to(ROOT)}")
                return 1
            for f in sorted(src_dir.iterdir()):
                if not f.is_file() or (ext and f.suffix.lower() != ext):
                    continue
                shutil.copy2(f, stage / dst / f.name)

        for name, src in SCRIPT_MAP.items():
            if not src.exists():
                print(f"ERROR 缺脚本：{src.relative_to(ROOT)}")
                return 1
            shutil.copy2(src, stage / "scripts" / name)

        for name, src in DOC_MAP.items():
            if not src.exists():
                print(f"ERROR 缺文档：{src.relative_to(ROOT)}")
                return 1
            shutil.copy2(src, stage / name)

        for name, src in RAW_MAP.items():
            if not src.exists():
                print(f"ERROR 缺原始数据：{src.relative_to(ROOT)}")
                return 1
            shutil.copy2(src, stage / "raw" / name)

        (stage / "00_先读我.txt").write_text(README, encoding="utf-8")

        manifest = [f"{sha256(f)}  {f.relative_to(stage).as_posix()}"
                    for f in sorted(p for p in stage.rglob("*") if p.is_file())]
        (stage / "MANIFEST.sha256").write_text("\n".join(manifest) + "\n",
                                               encoding="utf-8")

        OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
        if OUT_ZIP.exists():
            OUT_ZIP.unlink()
        with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for f in sorted(stage.rglob("*")):
                if f.is_file():
                    zf.write(f, f"{TOP}/{f.relative_to(stage).as_posix()}")

    print(f"打包完成：{OUT_ZIP.relative_to(ROOT)}")
    print(f"  大小 {OUT_ZIP.stat().st_size / 1024 / 1024:.1f} MiB")
    print(f"  sha256 {sha256(OUT_ZIP)}")
    return check()


def expected_sources() -> dict[str, Path]:
    """包内相对路径 → 仓库源文件。生成的 README / MANIFEST 不在此列。"""
    exp: dict[str, Path] = {}
    for src_dir, prefix, ext in DIR_MAP:
        if not src_dir.is_dir():
            continue
        for f in sorted(src_dir.iterdir()):
            if not f.is_file() or (ext and f.suffix.lower() != ext):
                continue
            exp[f"{prefix}/{f.name}"] = f
    for name, src in SCRIPT_MAP.items():
        if src.exists():
            exp[f"scripts/{name}"] = src
    for name, src in DOC_MAP.items():
        if src.exists():
            exp[name] = src
    for name, src in RAW_MAP.items():
        if src.exists():
            exp[f"raw/{name}"] = src
    return exp


def check() -> int:
    if not OUT_ZIP.exists():
        print(f"找不到 {OUT_ZIP}，先跑一次不带参数的打包")
        return 1
    ok = True
    with zipfile.ZipFile(OUT_ZIP) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        bad_crc = zf.testzip()
        if bad_crc:
            print(f"ERROR 压缩包内文件损坏：{bad_crc}")
            ok = False
        manifest = zf.read(f"{TOP}/MANIFEST.sha256").decode("utf-8").splitlines()
        listed = {line.split("  ", 1)[1]: line.split("  ", 1)[0]
                  for line in manifest if "  " in line}
        payload = [n for n in names if n != f"{TOP}/MANIFEST.sha256"]
        inside = {n[len(TOP) + 1:] for n in payload}
        missing = sorted(set(listed) - inside)
        extra = sorted(inside - set(listed))
        if missing:
            print(f"ERROR 清单里有、包里没有：{missing}")
            ok = False
        if extra:
            print(f"ERROR 包里有、清单没有：{extra}")
            ok = False
        for n in payload:
            rel = n[len(TOP) + 1:]
            if hashlib.sha256(zf.read(n)).hexdigest() != listed.get(rel):
                print(f"ERROR 校验和不符：{rel}")
                ok = False
            data = zf.read(n)[:32]
            ext = Path(n).suffix.lower().lstrip(".")
            real = ("png" if data[:4] == b"\x89PNG" else
                    "jpg" if data[:2] == b"\xff\xd8" else
                    "gif" if data[:6] in (b"GIF87a", b"GIF89a") else "?")
            if real not in ("?", ext) and not (real == "jpg" and ext in ("jpg", "jpeg")):
                print(f"ERROR 格式与扩展名不符：{rel}（实际 {real}）")
                ok = False
            if rel.startswith("figures/") and real == "png":
                w, h = struct.unpack(">II", data[16:24])
                if (w, h) != (1920, 1080):
                    print(f"WARN 尺寸不是 1920×1080：{rel} = {w}×{h}")

        # ── 新鲜度：包里的每一份，必须和仓库里的当前版本逐字节相同 ──────────
        # 只比对「清单 vs 包内」只能证明包没传坏，证明不了包是新的。
        for rel, src in sorted(expected_sources().items()):
            if rel not in listed:
                print(f"ERROR 包内缺少：{rel}")
                ok = False
                continue
            if hashlib.sha256(zf.read(f"{TOP}/{rel}")).hexdigest() != sha256(src):
                print(f"ERROR 包内容与仓库不一致（旧版）：{rel}")
                ok = False
        # 反向：包里是否有仓库已不存在的文件
        for rel in sorted(listed):
            if rel in ("00_先读我.txt", "MANIFEST.sha256"):
                continue
            if rel not in expected_sources():
                print(f"ERROR 包内有仓库已不存在的文件：{rel}")
                ok = False

        n_fig = len([r for r in listed if r.startswith("figures/")])
        n_gif = len([r for r in listed if r.startswith("animated/")])
        n_ext = len([r for r in listed if r.startswith("extracted/")])
    print(f"  自检：{len(listed)} 个文件，figures {n_fig} / animated {n_gif} / "
          f"extracted {n_ext} / raw {len(RAW_MAP)} / scripts {len(SCRIPT_MAP)} "
          f"—— {'通过' if ok else '未通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else build())
