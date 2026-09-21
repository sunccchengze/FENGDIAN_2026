#!/usr/bin/env python3
"""为 materials/ 下的 docx / pptx / xlsx / pdf 生成同名 Markdown 镜像（microsoft/markitdown）。

用途：让 Agent 与队友不必打开 Office / PDF 阅读器就能读到文档正文；镜像是只读副本，以原文件为准。

规则
- 输出与原文件同目录、同主名、扩展名 .md（如 `原理简概.docx` → `原理简概.md`）。
- 每个镜像首行带标记注释，记录来源文件名、来源 sha256 前 12 位与生成日期；
  再次运行时 sha256 未变则跳过，变了则重新生成（--force 强制全部重生成）。
- 同名 .md 已存在但没有标记注释 → 视为人工文件，跳过并告警，绝不覆盖。
- 跳过 `materials/孙承泽/自学白皮书/pdf/`（这些 PDF 由同目录 Markdown 源生成，镜像无意义）。
- 图片不转换（markitdown 对图片只能给出 EXIF 元数据）。
- 后处理（镜像里不留死链）：
  * pptx 导出的 `![alt](PictureN.jpg)` 与 docx 导出的 `![alt](data:image/...base64...)` 都指向不存在的文件，
    统一改写为文字占位 `*(图片：alt · 见原文件 xxx.pptx)*`；
  * pptx 文本框里的软换行（U+000B）改成换行（表格行内改成 `<br>`）；
  * 连续 4 个以上空行压成 2 个。

用法
    python3 tools/markitdown_sync.py            # 处理 materials/
    python3 tools/markitdown_sync.py --force    # 全部重生成
    python3 tools/markitdown_sync.py --root docs/  # 指定其他目录
    python3 tools/markitdown_sync.py --check    # 只校验镜像是否齐全且与原文件 sha256 一致（不需要 markitdown）

依赖（--check 之外）：pip install 'markitdown[docx,pptx,pdf,xlsx]'
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import re
import sys
from pathlib import Path
from typing import Iterator

REPO = Path(__file__).resolve().parents[1]
EXTS = {".docx", ".pptx", ".xlsx", ".pdf"}
SKIP_DIRS = {REPO / "materials" / "孙承泽" / "自学白皮书" / "pdf"}
MARK_RE = re.compile(r"<!-- markitdown-mirror: source=\"(?P<src>[^\"]+)\" sha256=\"(?P<sha>[0-9a-f]{12})\"")

# markitdown 产物里的两类"假图片"：pptx 的 PictureN.ext（文件并不存在）、docx 的 data-URI 截断占位
_IMG_PPTX_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<ref>Picture\d+\.[A-Za-z0-9]+)\)")
_IMG_DATA_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\(data:[^)]*\)")


def sha12(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def header(src: Path, sha: str) -> str:
    today = _dt.date.today().isoformat()
    return (
        f'<!-- markitdown-mirror: source="{src.name}" sha256="{sha}" generated="{today}" '
        f"| 只读镜像，正文由 microsoft/markitdown 自动转换，以同目录原文件为准；"
        f"重新生成：python3 tools/markitdown_sync.py -->\n\n"
    )


def read_marker(md_path: Path) -> re.Match | None:
    """镜像文件的标记必须在文件开头（人工 md 正文里提到这串字不算）。"""
    try:
        head = md_path.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return None
    return MARK_RE.match(head)


def postprocess(text: str, src: Path) -> str:
    """去掉 markitdown 产物里的死链与控制字符，其余正文原样保留。"""

    def _placeholder(m: re.Match) -> str:
        alt = (m.group("alt") or "").strip()
        ref = m.groupdict().get("ref")
        where = f"见原文件 {src.name}"
        if ref:
            where = f"原文件 {src.name} 内 {ref}"
        return f"*(图片：{alt} · {where})*" if alt else f"*(图片 · {where})*"

    text = _IMG_PPTX_RE.sub(_placeholder, text)
    text = _IMG_DATA_RE.sub(_placeholder, text)

    if "\x0b" in text:
        lines = []
        for line in text.split("\n"):
            if "\x0b" in line:
                line = line.replace("\x0b", "<br>") if line.lstrip().startswith("|") else line.replace("\x0b", "\n")
            lines.append(line)
        text = "\n".join(lines)

    text = re.sub(r"[ \t]+\n", "\n", text)  # 行尾空白
    text = re.sub(r"\n{4,}", "\n\n\n", text)  # 连续空行
    return text


def iter_sources(root: Path) -> Iterator[Path]:
    for src in sorted(root.rglob("*")):
        if not src.is_file() or src.suffix.lower() not in EXTS or src.name.startswith("~$"):
            continue
        if any(sd in src.parents for sd in SKIP_DIRS):
            continue
        yield src


def check(root: Path) -> int:
    """校验模式：每个来源都有镜像、镜像 sha 与来源一致、没有失去来源的孤儿镜像。返回问题数。"""
    problems = 0
    seen_mirrors: set[Path] = set()
    for src in iter_sources(root):
        out = src.with_suffix(".md")
        rel = out.relative_to(REPO)
        if not out.exists():
            print(f"MISSING  无镜像: {src.relative_to(REPO)}")
            problems += 1
            continue
        m = read_marker(out)
        if not m:
            print(f"MANUAL   同名 md 是人工文件，未镜像: {rel}")
            continue
        seen_mirrors.add(out)
        if m.group("sha") != sha12(src):
            print(f"STALE    镜像落后于原文件: {rel}")
            problems += 1
    for md in sorted(root.rglob("*.md")):
        if md in seen_mirrors or not md.is_file():
            continue
        m = read_marker(md)
        if m and not (md.parent / m.group("src")).exists():
            print(f"ORPHAN   镜像的原文件已不存在: {md.relative_to(REPO)} (source={m.group('src')})")
            problems += 1
    print(f"markitdown_sync --check: {len(seen_mirrors)} mirrors ok, {problems} problems")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="materials", help="要扫描的目录（相对仓库根）")
    ap.add_argument("--force", action="store_true", help="忽略 sha256 缓存，全部重生成")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="只校验，不生成；有缺失/过期/孤儿镜像时返回 1")
    args = ap.parse_args()
    root = (REPO / args.root).resolve()

    if args.check:
        return 1 if check(root) else 0

    try:
        from markitdown import MarkItDown  # noqa: WPS433
    except ImportError:
        print("缺少 markitdown：pip install 'markitdown[docx,pptx,pdf,xlsx]'", file=sys.stderr)
        return 2

    md = MarkItDown()
    made = skipped = unchanged = 0
    for src in iter_sources(root):
        out = src.with_suffix(".md")
        sha = sha12(src)
        if out.exists():
            m = read_marker(out)
            if not m:
                print(f"SKIP  人工 md 已存在，不覆盖: {out.relative_to(REPO)}")
                skipped += 1
                continue
            if m.group("sha") == sha and not args.force:
                unchanged += 1
                continue
        if args.dry_run:
            print(f"WOULD {out.relative_to(REPO)}")
            made += 1
            continue
        try:
            text = md.convert(str(src)).text_content
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {src.relative_to(REPO)}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        text = postprocess(text, src)
        out.write_text(header(src, sha) + text.strip() + "\n", encoding="utf-8")
        print(f"WROTE {out.relative_to(REPO)}  ({len(text):,} chars)")
        made += 1
    print(f"markitdown_sync: {made} written, {unchanged} unchanged, {skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
