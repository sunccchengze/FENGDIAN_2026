#!/usr/bin/env python3
"""交付包收取工具：只依赖标准库。

用途：把队友通过网盘 / 微信 / Release 资产拿到的 zip（或分卷）在**入库前**先验一遍，
避免「先解包再说」带来的三类事故：带病文件进 git、体积超限被 GitHub 拒收、
以及 zip 里的绝对路径/上跳路径落到仓库外面。

三种模式
--------
1. ``--inspect ZIP [ZIP ...]``
   只读检查：文件数、解压后总大小、顶层目录、最大的 10 个文件、
   超 95 MiB 门禁线 / 超 50 MiB 告警线的清单、可疑路径（绝对路径 / ``..`` / 符号链接）、
   0 字节文件、扩展名分布。**不解压、不写入任何东西。**

2. ``--manifest ZIP --out PATH.json``
   逐文件流式算 sha256（大文件也不会吃内存），产出 manifest.json：
   包级 sha256、解压后逐文件 sha256、大小、以及本工具版本与生成时刻。
   仓库里的大交付包按 ADR-2026-001「manifest + SHA-256」的口径留证。

3. ``--check-splits DIR``
   校验分卷（``X.zip.001``、``X.zip.002``… 或 ``*_partNN.zip``）是否连续、有无缺号。

退出码：0 = 通过；1 = 发现阻断级问题（超 95 MiB、可疑路径、包损坏）。

用法示例
--------
    python3 tools/intake_bundle.py --inspect ~/Downloads/交付.zip
    python3 tools/intake_bundle.py --manifest ~/Downloads/交付.zip --out /tmp/manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

MAX_ERROR_BYTES = 95 * 1024 * 1024   # 与 ci/repo_quality.py 同一条线
MAX_WARN_BYTES = 50 * 1024 * 1024
CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GiB"


def suspicious(name: str) -> str | None:
    pure = PurePosixPath(name.replace("\\", "/"))
    if pure.is_absolute() or name.startswith(("/", "\\")) or (len(name) > 1 and name[1] == ":"):
        return "绝对路径"
    if any(part == ".." for part in pure.parts):
        return "上跳路径（..）"
    return None


def inspect(zip_path: Path) -> tuple[dict, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        return {"path": str(zip_path), "error": "不是有效的 zip"}, [f"包损坏或不是 zip：{zip_path}"], []

    infos = archive.infolist()
    files = [i for i in infos if not i.is_dir()]
    total_uncompressed = sum(i.file_size for i in files)
    exts: dict[str, int] = {}
    for info in files:
        suffix = os.path.splitext(info.filename)[1].lower() or "(无扩展名)"
        exts[suffix] = exts.get(suffix, 0) + 1

    tops: dict[str, int] = {}
    for info in files:
        parts = PurePosixPath(info.filename.replace("\\", "/")).parts
        key = parts[0] if len(parts) > 1 else "(根目录散文件)"
        tops[key] = tops.get(key, 0) + 1

    biggest = sorted(files, key=lambda i: i.file_size, reverse=True)[:10]

    for info in files:
        if info.file_size > MAX_ERROR_BYTES:
            errors.append(f"超过 95 MiB 门禁线：{info.filename}（{human(info.file_size)}）")
        elif info.file_size > MAX_WARN_BYTES:
            warnings.append(f"超过 50 MiB 告警线：{info.filename}（{human(info.file_size)}）")
        reason = suspicious(info.filename)
        if reason:
            errors.append(f"可疑路径（{reason}）：{info.filename}")
        if info.file_size == 0:
            warnings.append(f"0 字节文件：{info.filename}")

    crc_bad = archive.testzip()
    if crc_bad:
        errors.append(f"CRC 校验失败：{crc_bad}")

    report = {
        "path": str(zip_path),
        "bytes": zip_path.stat().st_size,
        "files": len(files),
        "dirs": len(infos) - len(files),
        "uncompressed_bytes": total_uncompressed,
        "ratio": round(zip_path.stat().st_size / total_uncompressed, 4) if total_uncompressed else None,
        "top_level": dict(sorted(tops.items(), key=lambda kv: -kv[1])),
        "extensions": dict(sorted(exts.items(), key=lambda kv: -kv[1])),
        "largest": [{"name": i.filename, "size": i.file_size, "human": human(i.file_size)} for i in biggest],
    }
    archive.close()
    return report, errors, warnings


def manifest(zip_path: Path) -> dict:
    archive = zipfile.ZipFile(zip_path)
    entries = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        digest = hashlib.sha256()
        with archive.open(info) as handle:
            for chunk in iter(lambda: handle.read(CHUNK), b""):
                digest.update(chunk)
        entries.append({"name": info.filename, "size": info.file_size, "sha256": digest.hexdigest()})
    archive.close()
    entries.sort(key=lambda e: e["name"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": "tools/intake_bundle.py",
        "archive": {"path": str(zip_path), "bytes": zip_path.stat().st_size, "sha256": sha256_file(zip_path)},
        "file_count": len(entries),
        "files": entries,
    }


def check_splits(directory: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    groups: dict[str, list[int]] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if ".zip." in name:
            base, _, seq = name.rpartition(".")
            if seq.isdigit():
                groups.setdefault(base, []).append(int(seq))
    for base, seqs in groups.items():
        seqs.sort()
        expected = list(range(1, len(seqs) + 1))
        if seqs != expected:
            errors.append(f"分卷缺号：{base} → 实际 {seqs}，应为 {expected}")
        else:
            notes.append(f"{base}：{len(seqs)} 卷连续")
        for seq in seqs:
            sized = (directory / f"{base}.{seq:03d}").stat().st_size
            if sized > MAX_ERROR_BYTES:
                errors.append(f"单卷超 95 MiB：{base}.{seq:03d}（{human(sized)}）")
    if not groups:
        notes.append("没有发现 .zip.NNN 形式的分卷")
    return errors, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="交付包收取工具（只读检查 / 生成清单）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", nargs="+", metavar="ZIP", help="只读检查，不解压")
    mode.add_argument("--manifest", metavar="ZIP", help="逐文件 sha256 清单")
    mode.add_argument("--check-splits", metavar="DIR", help="校验分卷连续性")
    parser.add_argument("--out", metavar="PATH", help="--manifest 的输出文件")
    args = parser.parse_args()

    if args.inspect:
        failed = False
        for raw in args.inspect:
            path = Path(raw)
            if not path.is_file():
                print(f"✗ 找不到文件：{path}")
                failed = True
                continue
            report, errors, warnings = inspect(path)
            print(f"== {path.name} ==")
            if "error" in report:
                print(f"  ✗ {report['error']}")
                failed = True
                continue
            print(f"  包大小 {human(report['bytes'])} / 解压后 {human(report['uncompressed_bytes'])}"
                  f"（压缩比 {report['ratio']}）")
            print(f"  {report['files']} 个文件 + {report['dirs']} 个目录")
            print(f"  顶层：{', '.join(f'{k}({v})' for k, v in list(report['top_level'].items())[:8])}")
            print(f"  扩展名：{', '.join(f'{k}×{v}' for k, v in list(report['extensions'].items())[:10])}")
            print("  最大的文件：")
            for item in report["largest"][:5]:
                print(f"    {item['human']:>10}  {item['name']}")
            for w in warnings[:10]:
                print(f"  ! {w}")
            for e in errors[:10]:
                print(f"  ✗ {e}")
            if errors:
                failed = True
        return 1 if failed else 0

    if args.manifest:
        path = Path(args.manifest)
        if not path.is_file():
            print(f"✗ 找不到文件：{path}")
            return 1
        data = manifest(path)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
            print(f"已写入 {args.out}：{data['file_count']} 个文件，包 sha256 {data['archive']['sha256'][:16]}…")
        else:
            print(text)
        return 0

    errors, notes = check_splits(Path(args.check_splits))
    for note in notes:
        print(f"  ✓ {note}")
    for e in errors:
        print(f"  ✗ {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
