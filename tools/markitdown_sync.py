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

用法
    python3 tools/markitdown_sync.py            # 处理 materials/
    python3 tools/markitdown_sync.py --force    # 全部重生成
    python3 tools/markitdown_sync.py --root docs/  # 指定其他目录

依赖：pip install 'markitdown[docx,pptx,pdf,xlsx]'
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXTS = {".docx", ".pptx", ".xlsx", ".pdf"}
SKIP_DIRS = {REPO / "materials" / "孙承泽" / "自学白皮书" / "pdf"}
MARK_RE = re.compile(r"<!-- markitdown-mirror: source=\"(?P<src>[^\"]+)\" sha256=\"(?P<sha>[0-9a-f]{12})\"")


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="materials", help="要扫描的目录（相对仓库根）")
    ap.add_argument("--force", action="store_true", help="忽略 sha256 缓存，全部重生成")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        from markitdown import MarkItDown  # noqa: WPS433
    except ImportError:
        print("缺少 markitdown：pip install 'markitdown[docx,pptx,pdf,xlsx]'", file=sys.stderr)
        return 2

    md = MarkItDown()
    root = (REPO / args.root).resolve()
    made = skipped = unchanged = 0
    for src in sorted(root.rglob("*")):
        if not src.is_file() or src.suffix.lower() not in EXTS or src.name.startswith("~$"):
            continue
        if any(sd in src.parents for sd in SKIP_DIRS):
            continue
        out = src.with_suffix(".md")
        sha = sha12(src)
        if out.exists():
            head = out.read_text(encoding="utf-8", errors="replace")[:400]
            m = MARK_RE.search(head)
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
        out.write_text(header(src, sha) + text.strip() + "\n", encoding="utf-8")
        print(f"WROTE {out.relative_to(REPO)}  ({len(text):,} chars)")
        made += 1
    print(f"markitdown_sync: {made} written, {unchanged} unchanged, {skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
