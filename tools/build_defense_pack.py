#!/usr/bin/env python3
"""把答辩素材打成一个可下载的 zip（进仓库，随分支一起推送）。

为什么是脚本而不是手工压缩：
- 包内目录结构、附录文件、校验和都由脚本决定，换机器重跑结果一致；
- 素材更新后重跑一次即可，不会出现「包里的图和仓库里的图不是同一版」；
- 打完之后立即自检（文件数、尺寸、格式、sha256），不合格就不落盘。

用法：
    python3 tools/build_defense_pack.py            # 生成 zip
    python3 tools/build_defense_pack.py --check    # 只校验已有 zip

输出：docs/defense/defense_assets_<日期>.zip（当前 20261024）

文件名用 ASCII：中文名在命令行与 URL 里要百分号转义，容易传错。
包内的目录名仍是中文。
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
PACK_DATE = "20261024"
OUT_ZIP = ROOT / "docs/defense" / f"defense_assets_{PACK_DATE}.zip"
TOP = f"中期答辩素材_{PACK_DATE}"

README = """中期答辩素材包 · 2026-10-24
================================

这是给评审/自查用的压缩包，不是成品 PPT。
解压后 40 余个文件，按下面顺序看，20 分钟能看完。

目录
----
  00_先读我.txt                    ← 本文件
  01_中期答辩大纲_14页7分钟.md     ← 现行大纲：开篇 1 + 中间 12 + 结尾 1
  02_答辩素材清单.md               ← 逐张图的来源、口径、不能说什么
  03_项目记忆与现存问题.md         ← 真问题在哪、哪些数字说出去会出事
  figures/   22 张 PNG            ← 答辩图，1920×1080，可直接插 PPT
  animated/   2 个 GIF            ← 七步界面、偏航扫描
  extracted/ 12 张图片            ← 从 .docx/.pptx 里解出来的原始截图
  scripts/    3 个 .py            ← 图的生成脚本与打包脚本（只读仓库数据）
  MANIFEST.sha256                 ← 校验和，确认没传坏


一、20 分钟怎么看完
----
第 1 步（4 分钟）先看这 5 张：
  figures/g01_wake_loss.png        尾流吃掉 48.6%，第 2 页主图
  figures/g19_fluent_status.png    Fluent 现状（2026-10-24 已按三机数据重画）
  figures/g07_pinn_migration.png   PINN 接口改造与可训练占比
  figures/g11_independent_test.png 独立测试：−58.5% / −5.8%，含「第 0 条高于 PI」
  figures/g22_problems_actions.png 第 10 页：四个卡点与下一步

第 2 步（5 分钟）看 01_ 的 §1 排片表
  14 行，一眼看完。重点确认：每页时长你认不认。

第 3 步（6 分钟）看 01_ 的第 5、7、10 三页
  这三页是评委会认真看的地方，也是风险最高的三页。
  讲稿可直接念，口径和禁语都写在旁边。

第 4 步（5 分钟）抽查三张容易出问题的：
  figures/g13_failure_cases.png     三处没达标（主动交代那页）
  figures/g15_positioning.png       证据等级对照，故意不写外部数值
  figures/g21_two_control_lines.png 偏航线与桨距线不能混


二、这批图的口径纪律（看图时请一起核）
----
每张图右下角有一个角标，四种颜色四种话术，说的时候不能改：

  蓝「模拟真值 · FLORIS」    =  FLORIS 算出来的，口播说「模拟真值」
  橙「合成标签 · 非物理精度」=  标签是合成公式生成的，口播必须带后半句
  紫「CFD 后处理 · 非实测」  =  Fluent 算完导出的，不是实测，也不是精度证据
  绿「实测记录」             =  本仓库目前没有任何一张图该挂这个角标

已经守住的几条：
  · 没有把代理说成实测
  · 没有把 449.72 的均值说成「优于传统控制」（第 0 条流 492.28 高于 PI 477.54）
  · 没有把 +22.11% 说成年发电量增益
  · 没有把 0.4%–1.7% 那类外部数值写成「上限」，也没有画进任何一张图
  · 没有用「实时控制」，界面计时只说「界面内单次求解」，不代表全链路
  · 三机串列 CFD 的阵列总功率与 P2/P1 没有画进任何一张图（自身不自洽，见 EVID-2026-003）

禁用素材（这批里没有，但仓库里有）：
  viz/figures_nature/ 那 18 张是 3×3 旧口径（+24.04% / +67.26%），
  本轮是 1×3，不能当结果上屏；只能当方法示意并标注。


三、这一版相较 2026-10-23 改了什么
----
1) 大纲换成 14 页（用户 2026-10-24 给定结构），旧的 13 页版已作废；
2) g19 按三机串列真实数据重画——原图是 2026-09 的双机、11.4 m/s、12.1 rpm，
   与新工况（三机、9 m/s、TI 10%、105 万单元）不是一回事；
3) 新增 03_项目记忆与现存问题.md；
4) 打包脚本的 --check 现在会逐字节比对「包内 vs 仓库」，
   以前只数文件个数，图换了它也不知道。


四、图上数字怎么核
----
所有图都是脚本从仓库数据现算的，没有手填。改数字就改脚本里的常量再重画，
不要手改 PNG（改了图就和数据脱钩了）。

  python3 scripts/make_defense_figures.py          # 重画 22 张
  python3 scripts/make_defense_figures.py g01 g11  # 只画指定几张
  python3 scripts/make_defense_figures.py gif      # 重画 2 个动图
  python3 scripts/extract_defense_assets.py        # 重新解出 12 张原图
  python3 scripts/build_defense_pack.py --check    # 校验包是否与仓库一致

依赖：matplotlib + numpy + pillow，中文字体 NotoSansCJKsc-Regular.otf。
脚本只读仓库既有文件，不重跑实验、不改任何实验目录。


五、这包里没有的东西
----
· 没有 .pptx / PDF / 渲染脚本 —— 版式和成稿由组内自己做
· 没有视频 —— 两个 GIF 是逐帧图，不是录屏
· 没有外部文献原文 —— 所以那 9 个外部数值一个都没画进图

—— 生成于 2026-10-24
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def img_size(path: Path):
    data = path.read_bytes()[:32]
    if data[:4] == b"\x89PNG":
        return struct.unpack(">II", data[16:24]), "png"
    if data[:2] == b"\xff\xd8":
        return None, "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10]), "gif"
    return None, "?"


def build() -> int:
    if not ASSETS.exists():
        print(f"素材目录不存在：{ASSETS}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / TOP
        for sub in ("figures", "animated", "extracted", "scripts"):
            (stage / sub).mkdir(parents=True)

        copies = [
            (ASSETS / "generated", "figures", ".png"),
            (ASSETS / "animated", "animated", ".gif"),
            (ASSETS / "extracted", "extracted", None),
        ]
        for src_dir, dst, ext in copies:
            for f in sorted(src_dir.iterdir()):
                if not f.is_file() or (ext and f.suffix.lower() != ext):
                    continue
                shutil.copy2(f, stage / dst / f.name)

        for f in ("make_defense_figures.py", "extract_defense_assets.py",
                  "build_defense_pack.py"):
            src = ROOT / "tools" / f
            if src.exists():
                shutil.copy2(src, stage / "scripts" / f)

        shutil.copy2(ROOT / "docs/defense/2026-10-24_中期答辩大纲_按建议结构.md",
                     stage / "01_中期答辩大纲_14页7分钟.md")
        shutil.copy2(ROOT / "docs/defense/2026-10-23_答辩素材清单.md",
                     stage / "02_答辩素材清单.md")
        shutil.copy2(ROOT / "docs/defense/2026-10-24_项目记忆与现存问题.md",
                     stage / "03_项目记忆与现存问题.md")
        (stage / "00_先读我.txt").write_text(README, encoding="utf-8")

        manifest = []
        for f in sorted(p for p in stage.rglob("*") if p.is_file()):
            rel = f.relative_to(stage).as_posix()
            manifest.append(f"{sha256(f)}  {rel}")
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
        missing = sorted(set(listed) - {n[len(TOP) + 1:] for n in payload})
        extra = sorted({n[len(TOP) + 1:] for n in payload} - set(listed))
        if missing:
            print(f"ERROR 清单里有、包里没有：{missing}")
            ok = False
        if extra:
            print(f"ERROR 包里有、清单没有：{extra}")
            ok = False
        for n in payload:
            rel = n[len(TOP) + 1:]
            digest = hashlib.sha256(zf.read(n)).hexdigest()
            if listed.get(rel) != digest:
                print(f"ERROR 校验和不符：{rel}")
                ok = False
        # 图片格式与扩展名、答辩图尺寸
        counts = {"figures": 0, "animated": 0, "extracted": 0}
        for n in payload:
            rel = n[len(TOP) + 1:]
            if "/" not in rel:
                continue
            top = rel.split("/")[0]
            if top in counts:
                counts[top] += 1
            data = zf.read(n)[:32]
            ext = Path(n).suffix.lower().lstrip(".")
            real = ("png" if data[:4] == b"\x89PNG" else
                    "jpg" if data[:2] == b"\xff\xd8" else
                    "gif" if data[:6] in (b"GIF87a", b"GIF89a") else "?")
            if real not in ("?", ext) and not (real == "jpg" and ext in ("jpg", "jpeg")):
                print(f"ERROR 格式与扩展名不符：{rel}（实际 {real}）")
                ok = False
            if top == "figures" and real == "png":
                w, h = struct.unpack(">II", data[16:24])
                if (w, h) != (1920, 1080):
                    print(f"WARN 尺寸不是 1920×1080：{rel} = {w}×{h}")
    # ── 新鲜度：包里的每一份，必须和仓库里的当前版本逐字节相同 ──────────
    # 早先的 check 只比对「清单 vs 包内」，只能证明包没传坏，**证明不了包是新的**。
    # 2026-10-24 发现 g19 已按三机数据重画，但包内仍是 10-23 的旧图而 --check 报通过，
    # 因此补上这一层：包内容 vs 仓库源文件。
    fresh = [
        (ASSETS / "generated", "figures", ".png"),
        (ASSETS / "animated", "animated", ".gif"),
        (ASSETS / "extracted", "extracted", None),
    ]
    stale: list[str] = []
    expected: dict[str, Path] = {}
    for src_dir, prefix, ext in fresh:
        if not src_dir.is_dir():
            continue
        for f in sorted(src_dir.iterdir()):
            if not f.is_file():
                continue
            if ext and f.suffix.lower() != ext:
                continue
            expected[f"{prefix}/{f.name}"] = f

    # 只打包这三个脚本，别把整个 tools/ 都算进去（否则永远报"缺失"）
    for name in ("make_defense_figures.py", "extract_defense_assets.py",
                 "build_defense_pack.py"):
        src = ROOT / "tools" / name
        if src.exists():
            expected[f"scripts/{name}"] = src

    doc_map = {
        "01_中期答辩大纲_14页7分钟.md": ROOT / "docs/defense/2026-10-24_中期答辩大纲_按建议结构.md",
        "02_答辩素材清单.md": ROOT / "docs/defense/2026-10-23_答辩素材清单.md",
        "03_项目记忆与现存问题.md": ROOT / "docs/defense/2026-10-24_项目记忆与现存问题.md",
    }
    for name, src in doc_map.items():
        if src.exists():
            expected[name] = src

    with zipfile.ZipFile(OUT_ZIP) as zf:
        inpack = {n[len(TOP) + 1:]: n for n in zf.namelist() if not n.endswith("/")}
        for rel, src in expected.items():
            if rel not in inpack:
                stale.append(f"{rel}（包内缺失，仓库里有）")
                continue
            if hashlib.sha256(zf.read(inpack[rel])).hexdigest() != sha256(src):
                stale.append(f"{rel}（包内是旧版）")
        for rel in inpack:
            if rel != "00_先读我.txt" and rel != "MANIFEST.sha256" and rel not in expected:
                stale.append(f"{rel}（仓库里已不存在，包内仍留着）")

    if stale:
        ok = False
        print("ERROR 包内容与仓库当前文件不一致，请重跑打包：")
        for item in stale:
            print(f"  · {item}")
    else:
        print(f"  新鲜度：{len(expected)} 个文件与仓库逐字节一致")

    print(f"  自检：{len(payload)} 个文件，"
          f"figures {counts['figures']} / animated {counts['animated']} / "
          f"extracted {counts['extracted']} —— {'通过' if ok else '未通过'}")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    return check() if "--check" in argv else build()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
