#!/usr/bin/env python3
"""三机串列 CFD 数据可用性核查（EVID-2026-003 的复现脚本）。

被核查的数据：`materials/田铭雨/20261024_三机串列双模型对比/`
（田铭雨 2026-10-24 交付，k-omega SST 与 k-epsilon 两套算例，同一套 1,055,511 单元网格）。

本脚本只做三件事，不修改任何交付物：
  1. 内部自洽性检查：同列三台机，下游机盘面速度是否应低于上游机；
  2. 尾流剖面质量检查：剖面里是否出现超过来流 1.2 倍或负的速度、左右是否对称、
     相邻探针是否读到同一个网格单元（网格尺度不足以解析剖面）；
  3. 外部对照：用项目自己的 FLORIS GCH 配置（`FlorisModel("defaults")`，与
     `docs/research/oracle/floris_gch_oracle_v1.json` 同源同参），在**同一布局、同一来流、
     同一湍流度**下重算功率，给出 P2/P1 的参考值。

用法：
    python3 docs/research/scripts/verify_tandem_cfd.py            # 跑全部检查
    python3 docs/research/scripts/verify_tandem_cfd.py --no-floris  # 只跑 1、2（无需装 FLORIS）

依赖：标准库即可跑 1、2；第 3 部分需要 `pip install floris`（本项目验证于 4.7，默认配置即 GCH）。

结论见 docs/evidence/EVID-2026-003_三机串列CFD数据可用性核查.md。
"""
from __future__ import annotations

import argparse
import collections
import csv
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "materials" / "田铭雨" / "20261024_三机串列双模型对比"
CASES = ("k-omega_data", "k-epsilon_data")

# 交付物自述的工况（case_meta.json / 总对比README.md）
U_INF = 9.0        # m/s
D_ROTOR = 126.0    # m
R_ROTOR = 63.5     # m
TI_INF = 0.10      # 入流湍流度 10%
SPACING_D = 3.0    # 机间距 378 m
RHO = 1.225        # kg/m^3（由交付物自述 Ct≈0.62 反推的空气密度）
OMEGA = 1.070      # rad/s（定速运行，= 10.2 rpm）


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def check_power(case: str) -> list[dict[str, float]]:
    """第 1 部分：盘面速度与功率比的自洽性。"""
    rows = read_csv(DATA / case / "power_thrust.csv")
    out = []
    for r in rows:
        out.append(
            {
                "t": int(float(r["turbine"])),
                "z": float(r["z_rotor_m"]),
                "u": float(r["u_disk_forward_m_s"]),
                "T": float(r["thrust_N"]),
                "P": float(r["power_MW"]),
                "TI": float(r["TI_mean"]),
            }
        )
    p1 = out[0]["P"]
    print(f"\n[{case}] 盘面速度 / 推力 / 功率")
    print(f"  {'机':>2} {'z(m)':>10} {'u_disk':>7} {'T(kN)':>8} {'P(MW)':>7} {'TI%':>6} {'P/P1':>6}")
    for r in out:
        print(
            f"  {r['t']:>2} {r['z']:>10.1f} {r['u']:>7.3f} {r['T'] / 1e3:>8.1f} "
            f"{r['P']:>7.3f} {100 * r['TI']:>6.2f} {r['P'] / p1:>6.3f}"
        )
    print(f"  合计 {sum(r['P'] for r in out):.3f} MW")

    # 首台机近似自由来流：核对 Cp / Ct / 叶尖速比，判断单机标定是否可信。
    area = math.pi * R_ROTOR**2
    p_avail = 0.5 * RHO * area * U_INF**3
    t1 = out[0]
    print(
        f"  T1 标定：Cp={t1['P'] * 1e6 / p_avail:.3f}"
        f"  Ct={t1['T'] / (0.5 * RHO * area * U_INF**2):.3f}"
        f"  λ={OMEGA * R_ROTOR / U_INF:.2f}"
    )

    # 自洽性判据：与上游机相距 3D 的下游机，盘面平均速度必须明显低于上游机
    # （同一套来流、同一机型、同一转速）。门槛取 1%：低于 1% 视为「尾流未体现」。
    flags = []
    for a, b in ((out[0], out[1]), (out[1], out[2])):
        drop = 100 * (1 - b["u"] / a["u"])
        tag = "OK" if drop > 1.0 else "!! 尾流未体现"
        print(f"  T{a['t']}→T{b['t']} 盘面速度降幅 {drop:+5.1f}%  {tag}")
        if drop <= 1.0:
            flags.append(f"T{b['t']} 仅比 T{a['t']} 低 {drop:.1f}%")
    if flags:
        print("  !! 自洽性失败：" + "；".join(flags))
    else:
        print("  自洽性：通过")
    return out


def check_profiles(case: str) -> None:
    """第 2 部分：wake_profiles.csv 的剖面质量。"""
    rows = read_csv(DATA / case / "wake_profiles.csv")
    pts = [
        (
            int(float(r["turbine"])),
            round(float(r["dist_D"]), 3),
            float(r["dy_m"]),
            float(r["U_forward_m_s"]),
        )
        for r in rows
    ]
    u = [p[3] for p in pts]
    n = len(pts)
    neg = sum(1 for x in u if x < 0)
    acc = sum(1 for x in u if x > 1.2 * U_INF)

    groups: dict[tuple[int, float], list[tuple[float, float]]] = collections.defaultdict(list)
    for t, dD, dy, uu in pts:
        if abs(dy) <= R_ROTOR:
            groups[(t, dD)].append((dy, uu))

    dup = tot = 0
    runs = []
    for v in groups.values():
        v.sort()
        run = 1
        for i in range(1, len(v)):
            tot += 1
            if v[i][1] == v[i - 1][1]:
                dup += 1
                run += 1
            else:
                runs.append(run)
                run = 1
        runs.append(run)

    sym = cmp = 0
    for v in groups.values():
        d = dict(v)
        for dy, uu in v:
            if dy > 0 and -dy in d:
                cmp += 1
                if abs(uu - d[-dy]) < 0.5:
                    sym += 1

    print(f"\n[{case}] 尾流剖面质量（{n} 点，U∞={U_INF} m/s）")
    print(f"  速度区间              {min(u):+.2f} … {max(u):+.2f} m/s")
    print(f"  负速度                {neg} 点（{100 * neg / n:.1f}%）  物理上只应出现在转子后紧邻区")
    print(f"  > 1.2·U∞              {acc} 点（{100 * acc / n:.1f}%）  均匀来流不可能出现")
    print(f"  相邻 2 m 探针同值      {dup}/{tot}（{100 * dup / tot:.0f}%），平均连续同值 {sum(runs) / len(runs):.1f} 点")
    print(f"  左右对称（差<0.5 m/s） {sym}/{cmp}（{100 * sym / cmp:.0f}%）  轴对称转子应接近 100%")


def check_floris(cfd_power: dict[str, list[dict[str, float]]]) -> None:
    """第 3 部分：同配置 FLORIS GCH 参考值。"""
    try:
        import numpy as np
        from floris import FlorisModel
    except ImportError:
        print("\n[FLORIS] 未安装，跳过（pip install floris 后可复现）")
        return

    print("\n[FLORIS] FlorisModel('defaults') == 项目 GCH oracle 配置，同一布局/来流/TI")
    print(f"  {'布局':>8} {'TI':>5} {'P1':>8} {'P2':>8} {'P3':>8} {'合计':>9} {'P2/P1':>6} {'P3/P1':>6}")
    ref = {}
    for label, xs in (
        ("3D", [0.0, SPACING_D * D_ROTOR, 2 * SPACING_D * D_ROTOR]),
        ("5.02D", [0.0, 5.015 * D_ROTOR, 2 * 5.015 * D_ROTOR]),
    ):
        for ti in (0.06, 0.08, 0.10, 0.12):
            fm = FlorisModel("defaults")
            fm.set(
                layout_x=xs,
                layout_y=[0.0] * 3,
                wind_speeds=[U_INF],
                wind_directions=[270.0],
                turbulence_intensities=[ti],
            )
            fm.run()
            p = fm.get_turbine_powers()[0] / 1e3
            print(
                f"  {label:>8} {ti:>5.2f} {p[0]:>8.1f} {p[1]:>8.1f} {p[2]:>8.1f} "
                f"{p.sum():>9.1f} {p[1] / p[0]:>6.3f} {p[2] / p[0]:>6.3f}"
            )
            if label == "3D" and abs(ti - TI_INF) < 1e-9:
                ref = {"P1": p[0], "P2": p[1], "P3": p[2], "sum": p.sum()}

    # 盘面平均亏损参考值
    print("\n  同布局下游 3D 处的盘面平均亏损（FLORIS 横截面，r<=R）：")
    fm = FlorisModel("defaults")
    fm.set(
        layout_x=[0.0],
        layout_y=[0.0],
        wind_speeds=[U_INF],
        wind_directions=[270.0],
        turbulence_intensities=[TI_INF],
    )
    for dD in (1, 2, 3, 4, 6, 8):
        cs = fm.calculate_cross_plane(
            downstream_dist=dD * D_ROTOR, y_resolution=161, z_resolution=161
        )
        df = cs.df
        y, z, uu = df.x1.values, df.x2.values, df.u.values
        r = np.hypot(y, z)
        m = r <= R_ROTOR
        avg = uu[m].mean()
        cen = uu[int(np.argmin(r))]
        print(
            f"    {dD:>2}D  盘面均速 {avg:5.2f} m/s（亏损 {100 * (1 - avg / U_INF):4.1f}%）"
            f"  中心 {cen:5.2f} m/s（亏损 {100 * (1 - cen / U_INF):4.1f}%）"
        )

    if not ref:
        return
    print("\n  CFD vs FLORIS（TI=10%，3D 间距）")
    for case, rows in cfd_power.items():
        p1 = rows[0]["P"]
        tot = sum(r["P"] for r in rows) * 1e3
        print(
            f"    {case:>14}: P1 {p1 * 1e3:7.1f} kW (参考 {ref['P1']:.1f}, 差 {100 * (p1 * 1e3 / ref['P1'] - 1):+.1f}%)"
            f" | 合计 {tot:7.1f} kW (参考 {ref['sum']:.1f}, 差 {100 * (tot / ref['sum'] - 1):+.1f}%)"
            f" | P2/P1 {rows[1]['P'] / p1:.3f} vs {ref['P2'] / ref['P1']:.3f}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-floris", action="store_true", help="只跑内部检查")
    args = ap.parse_args()

    if not DATA.is_dir():
        print(f"找不到数据目录：{DATA}", file=sys.stderr)
        return 2

    print(f"数据目录：{DATA.relative_to(REPO)}")
    print(f"工况：U∞={U_INF} m/s，TI={TI_INF:.0%}，转子 D={D_ROTOR} m，间距 {SPACING_D}D")

    powers = {case: check_power(case) for case in CASES}
    for case in CASES:
        check_profiles(case)
    if not args.no_floris:
        check_floris(powers)
    print("\n结论口径见 docs/evidence/EVID-2026-003_三机串列CFD数据可用性核查.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
