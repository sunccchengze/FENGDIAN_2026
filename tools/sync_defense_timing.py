#!/usr/bin/env python3
"""把 14 页口播的字数、秒数、累计时间「一处改、处处同步」。

为什么要有这个脚本：
- 同一个数字（1,433 字 / 6′32″）在 v3 大纲里有 5 个地方出现（文首摘要、排片表、
  表下三条说明、时间检查点表、文末修订记录），另外还写在提词器、README、打包脚本里；
- 手工改必定漏一处，而漏掉的两处数字会互相打架——这是本仓库出现过的问题；
- 所以：**只改 `# 第 N 页` 段落里的口播正文**，其余全部由本脚本重算重写。

用法：
    python3 tools/sync_defense_timing.py          # 重算并写回全部文件
    python3 tools/sync_defense_timing.py --check  # 只校验，不写文件（不一致则退出码 1）

规则：
- 字数 = 口播正文去掉〔可略句〕与所有空白后的字符数；
- 秒数 = round(字数 / 4.3)；每页停顿秒数来自 PAUSE 表（人工设定，脚本不改）；
- 计划 = 口播秒 + 停顿秒；累计逐页相加。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/defense"
OUTLINE = DOCS / "2026-10-24_制作大纲v3_主线版.md"
PROMPTER = DOCS / "2026-10-24_口播稿_照念_v3.txt"
README = DOCS / "README.md"
PACK = ROOT / "tools/build_defense_pack.py"

RATE = 4.3
HARD_LIMIT = 7 * 60
PAUSE = {1: 2, 2: 4, 3: 4, 4: 3, 5: 7, 6: 3, 7: 6,
         8: 4, 9: 7, 10: 4, 11: 5, 12: 3, 13: 5, 14: 2}
TITLES = {1: "封面", 2: "研究背景与意义", 3: "研究目标与技术路线", 4: "文献与方法取舍",
          5: "流场与网格", 6: "接口适配", 7: "主干承旧，接口纳新",
          8: "偏航移尾迹，桨距抑偏离", 9: "优化控制结果", 10: "可视化与系统集成",
          11: "正视短板，逐项解难", 12: "排定节点，逐项查验",
          13: "已有成果可述，未竟之功待续", 14: "致谢"}


def mmss(sec: int) -> str:
    return f"{sec // 60:02d}:{sec % 60:02d}"


def count(text: str) -> int:
    """字数 = 去掉引用符 `>`、可略句〔　〕与所有空白后的字符数。"""
    plain = re.sub(r"〔[^〕]*〕", "", text.replace(">", ""))
    return len(re.sub(r"\s", "", plain))


def parse(outline: str) -> dict[int, str]:
    body = outline.split("\n## 修订记录")[0]
    parts = re.split(r"\n# 第 (\d+) 页", body)
    talks: dict[int, str] = {}
    for i in range(1, len(parts), 2):
        page = int(parts[i])
        m = re.search(r"\*\*口播（\d+ 字）\*\*\n((?:>.*\n)+)", parts[i + 1])
        if not m:
            raise SystemExit(f"第 {page} 页找不到口播块")
        talks[page] = m.group(1)
    if sorted(talks) != list(range(1, 15)):
        raise SystemExit(f"页数不对：{sorted(talks)}")
    return talks


def schedule(talks: dict[int, str]):
    rows, cum = [], 0
    for p in range(1, 15):
        chars = count(talks[p])
        speak = round(chars / RATE)
        pause = PAUSE[p]
        plan = speak + pause
        cum += plan
        rows.append(dict(page=p, chars=chars, speak=speak, pause=pause, plan=plan, cum=cum))
    return rows


def rewrite(outline: str, talks: dict[int, str], rows) -> str:
    total_chars = sum(r["chars"] for r in rows)
    speak_total = sum(r["speak"] for r in rows)
    pause_total = sum(r["pause"] for r in rows)
    total = rows[-1]["cum"]
    slack = HARD_LIMIT - total
    pure = round(total_chars / RATE)
    secs = (pure // 60, pure % 60)

    # 1) 每页口播块前的字数标注
    for p, text in talks.items():
        outline = re.sub(rf"(\n# 第 {p} 页[^\n]*\n(?:.*\n)*?)\*\*口播（\d+ 字）\*\*",
                         rf"\g<1>**口播（{count(text)} 字）**", outline, count=1)

    # 2) 表头摘要
    outline = re.sub(r"口播总量 \*\*[\d,]+ 字 ≈ \d+′\d+″\*\*",
                     f"口播总量 **{total_chars:,} 字 ≈ {secs[0]}′{secs[1]:02d}″**",
                     outline)
    outline = re.sub(r"计划总时长 \*\*\d+′\d+″\*\*，硬上限 \*\*7′00″\*\*，余量 \*\*\d+ 秒\*\*",
                     f"计划总时长 **{total // 60}′{total % 60:02d}″**，硬上限 **7′00″**，余量 **{slack} 秒**",
                     outline)

    # 3) 排片总表逐行
    def fix_row(m):
        p = int(m.group(1))
        r = next(x for x in rows if x["page"] == p)
        return (f"| {p} |{m.group(2)}| {r['chars']} | {r['speak']}s | {r['pause']}s | "
                f"{r['plan']}s | {mmss(r['cum'])} |")
    outline = re.sub(r"^\| (\d+) \|([^\n]*)\| \d+ \| \d+s \| \d+s \| \d+s \| \d+:\d+ \|$",
                     fix_row, outline, flags=re.M)
    outline = re.sub(r"^\| — \| \*\*合计\*\* \| \| \| \*\*[\d,]+\*\* \| \*\*\d+s\*\* \| \*\*\d+s\*\* \| "
                     r"\*\*\d+s（\d+′\d+″）\*\* \| 余量 \*\*\d+s\*\* \|$",
                     f"| — | **合计** | | | **{total_chars:,}** | **{speak_total}s** | **{pause_total}s** | "
                     f"**{total}s（{total // 60}′{total % 60:02d}″）** | 余量 **{slack}s** |",
                     outline, flags=re.M)

    # 4) 表下三条说明
    outline = re.sub(r"- 硬上限 \*\*7′00″\*\*，计划 \*\*\d+′\d+″\*\*，留 \*\*\d+ 秒\*\*",
                     f"- 硬上限 **7′00″**，计划 **{total // 60}′{total % 60:02d}″**，留 **{slack} 秒**", outline)
    top = sorted(rows, key=lambda r: (-r["chars"], r["page"]))[:3]
    outline = re.sub(r"- 最重的三页：\*\*.*?\*\*。",
                     "- 最重的三页：" + " · ".join(
                         f"**第 {r['page']} 页（{r['chars']} 字）**" for r in top) + "。", outline)

    # 5) 时间检查点表
    marks = [3, 5, 7, 9, 11, 13, 14]
    lines = []
    for p in marks:
        r = next(x for x in rows if x["page"] == p)
        label = "结束" if p == 14 else f"第 {p} 页结束"
        lines.append(f"| {label} | **{mmss(r['cum'])}** |")
    for line in lines:
        outline = re.sub(r"^\| (?:第 \d+ 页结束|结束) \| \*\*\d+:\d+\*\*" + re.escape(line.split("|")[2].rstrip()),
                         line.rstrip(), outline, flags=re.M)
    outline = re.sub(r"\| 结束 \| \*\*\d+:\d+\*\*（上限 07:00）\| 余量 \d+ 秒 \|",
                     f"| 结束 | **{mmss(total)}**（上限 07:00） | 余量 {slack} 秒 |", outline)

    # 6) 文末修订记录
    outline = re.sub(r"> 改后口播总量 \*\*[\d,]+ 字 ≈ \d+′\d+″\*\*，计划 \*\*\d+′\d+″\*\*，余量 \*\*\d+ 秒\*\*。",
                     f"> 改后口播总量 **{total_chars:,} 字 ≈ {secs[0]}′{secs[1]:02d}″**，计划 **{total // 60}′{total % 60:02d}″**，"
                     f"余量 **{slack} 秒**。", outline)
    return outline


def prompter_text(talks: dict[int, str], rows) -> str:
    total_chars = sum(r["chars"] for r in rows)
    total = rows[-1]["cum"]
    pure = round(total_chars / RATE)
    head = [f"口播稿 · 照念版 v3（主线版）",
            "=" * 46,
            "用法：打印这一份，只念正文；〔　〕里是可略句，超时先删。",
            f"合计 {total_chars:,} 字 ≈ {pure // 60}′{pure % 60:02d}″；"
            f"含停顿计划 {total // 60}′{total % 60:02d}″；硬上限 7′00″（余量 {HARD_LIMIT - total} 秒）。",
            "每页抬头给了「应到时间」——念完这页看一眼秒表；超了就按 v3 大纲的砍句顺序删。",
            ""]
    body = []
    for r in rows:
        p = r["page"]
        body += ["-" * 46,
                 f"第 {p} 页 · {TITLES[p]}    〔本页 {r['chars']} 字 · 念完应到 {mmss(r['cum'])}〕",
                 "-" * 46,
                 " ".join(l[1:].strip() for l in talks[p].strip("\n").splitlines()).replace("  ", " "),
                 ""]
    return "\n".join(head + body)


def main() -> int:
    check_only = "--check" in sys.argv
    outline = OUTLINE.read_text(encoding="utf-8")
    talks = parse(outline)
    rows = schedule(talks)
    new_outline = rewrite(outline, talks, rows)
    new_prompter = prompter_text(talks, rows)
    total_chars = sum(r["chars"] for r in rows)
    total = rows[-1]["cum"]

    expected = [("v3 提词器：1,433 字 / 6′32″", "v3 提词器"),
                ("1,433 字 / 6′32″", "打包脚本")]
    print(f"总字数 {total_chars:,}；纯念 {sum(r['speak'] for r in rows)}s；"
          f"含停顿 {total}s（{total // 60}′{total % 60:02d}″）；余量 {HARD_LIMIT - total}s")
    for r in rows:
        print(f"  p{r['page']:>2} {r['chars']:>4} 字 {r['speak']:>3}s +{r['pause']}s → {mmss(r['cum'])}")

    if check_only:
        bad = []
        if new_outline != outline:
            bad.append("v3 大纲与脚本重算结果不一致")
        if new_prompter != PROMPTER.read_text(encoding="utf-8"):
            bad.append("提词器与大纲不一致")
        print("校验：" + ("通过" if not bad else "；".join(bad)))
        return 0 if not bad else 1

    if new_outline != outline:
        OUTLINE.write_text(new_outline, encoding="utf-8")
        print("已写回 v3 大纲")
    PROMPTER.write_text(new_prompter, encoding="utf-8")
    print("已重生成提词器")

    for path in (README, PACK):
        t = path.read_text(encoding="utf-8")
        t2 = re.sub(r"\d,\d{3} 字 / \d+′\d+″", f"{total_chars:,} 字 / {total // 60}′{total % 60:02d}″", t)
        if t2 != t:
            path.write_text(t2, encoding="utf-8")
            print(f"已同步 {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
