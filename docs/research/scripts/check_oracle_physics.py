#!/usr/bin/env python3
"""FLORIS GCH oracle 复现校验：只比对物理量，忽略易变的 `sec`（AUD-17）。

背景：`floris_gch_oracle_v1.json` 每个工况都烘焙了生成机器的墙钟 `sec`，
重跑生成脚本后物理量逐位相同、文件哈希却必然不同，「复现＝比整文件哈希」
在设计上永远红。本脚本计算**剔除所有 `sec` 键后**的规范化 SHA-256；
第三方复现时重跑生成脚本后对新旧两份文件各算一次，物理哈希相等即复现成功。

用法：
    python3 docs/research/scripts/check_oracle_physics.py            # 打印存档文件的物理哈希
    python3 docs/research/scripts/check_oracle_physics.py A.json B.json  # 比较两份

存档文件（2026-10-22 审计重跑核验：物理哈希一致，仅 sec 不同）：
    docs/research/oracle/floris_gch_oracle_v1.json
"""
import hashlib
import json
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "oracle" / "floris_gch_oracle_v1.json"


def strip_sec(obj):
    if isinstance(obj, dict):
        return {k: strip_sec(v) for k, v in obj.items() if k != "sec"}
    if isinstance(obj, list):
        return [strip_sec(v) for v in obj]
    return obj


def physics_hash(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(strip_sec(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main(argv) -> int:
    paths = [Path(a) for a in argv[1:]] or [DEFAULT]
    hashes = {str(p): physics_hash(p) for p in paths}
    for p, h in hashes.items():
        print(f"{h}  {p}  (sec 已剔除)")
    if len(set(hashes.values())) > 1:
        print("MISMATCH: 物理量不一致（不只是 sec 不同）", file=sys.stderr)
        return 1
    if len(paths) > 1:
        print("OK: 物理量逐位一致（sec 差异已忽略）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
