#!/usr/bin/env python3
"""装配自学白皮书：把本目录 8 个分章片段按文件名顺序拼成上一级的整册 Markdown。

    python3 build.py           # 重新装配，覆盖 ../风电场偏航优化与智能可视化自学白皮书.md
    python3 build.py --check   # 只比对：片段拼装结果与整册是否一致（CI 用，不写文件）

路径约定
- 片段就地可读：片段里的图片一律写 `](../images/xxx.png)`，在 GitHub 上打开单个片段也能显示图。
- 整册与 `images/` 同级，装配时把 `](../images/` 改写为 `](./images/`，其余字节原样拼接（无分隔符）。
- 修改讲稿只改片段，改完运行本脚本；`pdf/` 下的 PDF 另按 `pdf/README.md` 重出。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "风电场偏航优化与智能可视化自学白皮书.md"


def assemble() -> str:
    parts = sorted(p for p in HERE.glob("*.md") if p.name[:2].isdigit())
    text = "".join(p.read_text(encoding="utf-8") for p in parts)
    return text.replace("](../images/", "](./images/")


def main(argv: list[str]) -> int:
    text = assemble()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else None
        if current == text:
            print(f"whitepaper build --check: OK ({len(text):,} chars, {OUT.name})")
            return 0
        print(f"whitepaper build --check: 整册与片段不一致，请运行 python3 {HERE.name}/build.py 重新装配", file=sys.stderr)
        return 1
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE.parent.parent.parent.parent)} ({len(text):,} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
