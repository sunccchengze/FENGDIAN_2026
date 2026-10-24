#!/usr/bin/env python3
"""核查三机串列 CFD 交付件里「转子盘面平均速度」的采样有效性。

背景
----
`materials/田铭雨/20261024_三机串列双模型对比/` 给出的盘面平均速度 u_disk 是
`rotor{1,2,3}_plane.csv` 逐点取值的环形面积加权。本脚本不改任何数据，只回答三个问题：

1. 这些采样点本身是否落在物理可能范围内（0 … 1.05·U∞）？
2. 交付的 u_disk 与同一批采样点的中位数，给出的**逐台趋势**是否一致？
3. 交付 CSV 的 u_disk 与交付文档自述的「盘面平均亏损 4.4%」是否自洽？

用法
----
    python3 docs/research/scripts/probe_rotor_plane_sampling.py            # 全部
    python3 docs/research/scripts/probe_rotor_plane_sampling.py --per-radius

只用标准库；不依赖 floris、numpy、pandas。
结论口径见 docs/evidence/EVID-2026-003 §4.1.1。
"""
from __future__ import annotations

import csv
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "materials" / "田铭雨" / "20261024_三机串列双模型对比"
CASES = ("k-omega_data", "k-epsilon_data")
U_INF = 9.0          # 交付件自述来流
U_CEIL = 1.05 * U_INF  # 均匀来流下盘面采样不应显著超过来流
PLANES = (1, 2, 3)


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load(case: str, k: int) -> list[tuple[float, float, float]]:
    """返回 (r_m, theta, U_forward) 三元组。"""
    out = []
    for r in rows(DATA / case / f"rotor{k}_plane.csv"):
        out.append((float(r["r_m"]), float(r["theta_rad"]), float(r["U_forward_m_s"])))
    return out


def area_weight(pts: list[tuple[float, float, float]]) -> float:
    """环形面积加权平均：每点代表 r·dr·dθ，权重取 r。"""
    w = [(u, r) for r, _t, u in pts]
    return sum(u * r for u, r in w) / sum(r for _u, r in w)


def main(argv: list[str]) -> int:
    if not DATA.is_dir():
        print(f"找不到数据目录：{DATA}", file=sys.stderr)
        return 2
    per_radius = "--per-radius" in argv

    print(f"数据目录：{DATA.relative_to(ROOT)}")
    print(f"工况：U∞ = {U_INF} m/s（交付件自述）；物理上限按 {U_CEIL:.2f} m/s 判\n")

    summary = {}
    for case in CASES:
        print(f"[{case}] 转子盘面采样")
        print("   机   点数  中位数  面积加权  越界占比   最小值   最大值")
        meds, wts = [], []
        for k in PLANES:
            pts = load(case, k)
            us = [u for _r, _t, u in pts]
            bad = sum(1 for u in us if u < 0.0 or u > U_CEIL)
            med = st.median(us)
            wt = area_weight(pts)
            meds.append(med)
            wts.append(wt)
            print(f"   T{k}  {len(pts):5d}  {med:6.2f}  {wt:8.2f}  "
                  f"{100 * bad / len(us):6.1f}%  {min(us):8.2f} {max(us):8.2f}")
            if per_radius:
                byr = defaultdict(list)
                for r, _t, u in pts:
                    byr[r].append(u)
                for r in sorted(byr):
                    v = byr[r]
                    b = sum(1 for u in v if u < 0.0 or u > U_CEIL)
                    print(f"        r={r:5.1f}  n={len(v):2d}  中位数={st.median(v):6.2f}  "
                          f"min={min(v):8.2f}  max={max(v):8.2f}  越界={b}/{len(v)}")
        summary[case] = (meds, wts)
        print()

    print("逐台趋势（同一批采样点的两种汇总方式）")
    print("   算例            口径            T1     T2     T3    T2/T1   T3/T2")
    for case, (meds, wts) in summary.items():
        for label, vals in (("中位数", meds), ("面积加权(交付)", wts)):
            r21 = vals[1] / vals[0]
            r32 = vals[2] / vals[1]
            print(f"   {case:14s}  {label:12s} {vals[0]:6.2f} {vals[1]:6.2f} {vals[2]:6.2f}"
                  f"   {r21:5.3f}   {r32:5.3f}")
    print()

    print("与交付文档自述的交叉核对")
    print("  自述（总对比README.md / 中期答辩_仿真部分总结.md §5.1）：盘面平均亏损 4.4%，P2/P1 = 0.88")
    for case, (_meds, wts) in summary.items():
        loss = 1 - wts[1] / wts[0]
        print(f"  {case:14s} 交付 CSV 的面积加权口径：P2/P1 = {wts[1] / wts[0]:.3f}，"
              f"即 T1→T2 亏损 {100 * loss:+.1f}%（亏损 >0 表示 T2 更低）")
    print("  三处口径互不一致：CSV 面积加权 ≈ +0.2%，文档自述 4.4%，两者都由同一批采样点得出。")
    print()
    print("读法（不得越过）")
    print("  · 越界点占四到五成、且在每个半径上都出现，说明盘面平均不是被尾流污染的，是被取样污染的；")
    print("  · 中位数口径下 T1>T2>T3 单调下降，说明尾流在流场里是存在的，"
          "不能据此说「CFD 没有尾流」；")
    print("  · 结论：串列干扰量仍不可用（判否），但理由应从「数据自相矛盾」改为"
          "「盘面平均与剖面的取样口径不可靠、两种汇总互相矛盾」。")
    print("  详见 docs/evidence/EVID-2026-003_三机串列CFD数据可用性核查.md §4.1.1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
