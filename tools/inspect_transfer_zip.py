#!/usr/bin/env python3
"""看一眼别人发来的 zip 里到底是什么——只做清点，不做结论。

为什么需要它：队友发来的交付件经常是「一个 zip + 一段口头说明」，
里面可能有 CSV、有图、有 Word，命名还常常是中文或拼音。人工翻容易漏，
也容易在没看清字段的情况下就开始算数。这个脚本先只回答四个问题：

  1. 里面有哪些文件、多大、什么格式？
  2. 每个 CSV/XLSX-mirror 的列名是什么、多少行？
  3. 有没有像「功率」「风速」「偏航」的列？单位看起来是 W 还是 kW？
  4. 有没有能和现有 oracle（8 m/s、零偏航、1×3）直接对照的单点？

它**不会**替你做换算，也不会把任何数写进结论——只把观察到的事实摆出来，
判断留给看的人。这一点是刻意的：之前有过「照着一个数就往下推」的教训。

用法：
    python3 tools/inspect_transfer_zip.py <文件或目录>
    python3 tools/inspect_transfer_zip.py 三机串列_双模型对比数据及说明.zip
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

TEXT_EXT = {".csv", ".txt", ".json", ".md", ".yaml", ".yml", ".tsv"}
KNOWN = {
    "power": ("power", "p_", "_p", "kw", "功率", "p1", "p2", "p3", "farm"),
    "wind": ("wind", "u_", "uinf", "风速", "speed", "velocity"),
    "yaw": ("yaw", "gamma", "偏航"),
    "pitch": ("pitch", "beta", "桨距"),
    "ti": ("ti", "turbulence", "湍流"),
    "dir": ("direction", "theta", "风向", "wd"),
}
MAX_PREVIEW_ROWS = 5


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n / 1:.1f} {unit}" if False else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def classify(col: str) -> str | None:
    low = col.lower()
    for kind, keys in KNOWN.items():
        if any(k in low for k in keys):
            return kind
    return None


def guess_unit(values: list[float], kind: str) -> str:
    if kind != "power" or not values:
        return ""
    peak = max(abs(v) for v in values)
    if peak > 1e5:
        return "（量级像 W）"
    if peak > 1e2:
        return "（量级像 kW）"
    return "（量级像 MW 或已归一）"


def describe_text(name: str, raw: bytes) -> None:
    """非表格文本（说明文档）只摘前几行，不假装它是 CSV。"""
    lines = [ln for ln in raw.decode("utf-8-sig", errors="replace").splitlines() if ln.strip()]
    print(f"    {name}")
    print(f"      文本，{len(lines)} 行；前 4 行：")
    for ln in lines[:4]:
        print(f"        {ln[:90]}")


def describe_csv(name: str, raw: bytes) -> None:
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        print(f"    {name}：空文件")
        return
    header = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    print(f"    {name}")
    print(f"      行数 {len(body):,}｜列数 {len(header)}｜分隔符 {delim!r}")
    print(f"      列名：{', '.join(header[:14])}{' …' if len(header) > 14 else ''}")
    hits = {}
    for idx, col in enumerate(header):
        kind = classify(col)
        if not kind:
            continue
        vals = []
        for r in body[:400]:
            if idx < len(r):
                try:
                    vals.append(float(r[idx]))
                except ValueError:
                    pass
        if vals:
            hits.setdefault(kind, []).append(
                f"{col} [{min(vals):.4g}, {max(vals):.4g}]{guess_unit(vals, kind)}")
    if hits:
        for kind, items in hits.items():
            print(f"      {kind:5s}: " + "；".join(items[:4]))
    else:
        print("      未识别出功率/风速/偏航等字段（可能列名是拼音或代号）")
    if body:
        print("      前两行样例：")
        for r in body[:2]:
            print("        " + ", ".join(r[:8]))


def walk(root: Path, label: str) -> None:
    print(f"\n【{label}】")
    if root.is_dir():
        entries = sorted(p for p in root.rglob("*") if p.is_file())
        for p in entries:
            print(f"  {human(p.stat().st_size):>10s}  {p.relative_to(root)}")
            if p.suffix.lower() in TEXT_EXT and p.stat().st_size < 20_000_000:
                if p.suffix.lower() in (".csv", ".tsv"):
                    describe_csv(p.name, p.read_bytes())
                else:
                    describe_text(p.name, p.read_bytes())
        return
    ext = root.suffix.lower()
    if ext == ".zip":
        with zipfile.ZipFile(root) as zf:
            infos = sorted(zf.infolist(), key=lambda i: i.filename)
            print(f"  共 {len(infos)} 项")
            for info in infos:
                if info.is_dir():
                    continue
                print(f"  {human(info.file_size):>10s}  {info.filename}")
            for info in infos:
                if info.is_dir():
                    continue
                p = Path(info.filename)
                if p.suffix.lower() in TEXT_EXT and info.file_size < 20_000_000:
                    if p.suffix.lower() in (".csv", ".tsv"):
                        describe_csv(p.name, zf.read(info))
                    else:
                        describe_text(p.name, zf.read(info))
        return
    if ext in (".csv", ".tsv"):
        describe_csv(root.name, root.read_bytes())
        return
    if ext in TEXT_EXT:
        describe_text(root.name, root.read_bytes())
        return
    print(f"  {human(root.stat().st_size)}  {root.name}（不是 zip，也无法按文本读）")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for arg in argv:
        path = Path(arg)
        if not path.exists():
            print(f"找不到：{arg}")
            continue
        walk(path, str(path))
    print("\n下一步：字段与单位确认后，再决定能不能和 oracle 对照；"
          "未确认前不要写任何结论。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
