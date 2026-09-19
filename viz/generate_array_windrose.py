#!/usr/bin/env python3
"""3×3 阵列全风向偏航贪心扫描。

12 风向 × 4 风速，每个条件下从上游到下游逐机贪心选偏航角（±30°，13 候选）。
输出 cases_array_windrose.csv：
    wind_direction, U_inf, power_base, power_greedy, gain_pct, yaw_1..yaw_9

口径：FLORIS 4.6.6 默认配置（GCH），NREL 5MW，行距 5D、列距 3D，TI=6%。
内置自检：270°/8 m/s 的 base 应复现 8095.15 kW，贪心总功率应不低于
逐排贪心交付值 10041.46 kW（逐机自由度 ⊃ 逐排自由度）。
"""
import time
from pathlib import Path

import floris
import numpy as np
import pandas as pd
from floris import FlorisModel

D = 126.0
LAYOUT_X = np.array([r * 5 * D for r in range(3) for c in range(3)])
LAYOUT_Y = np.array([(c - 1) * 3 * D for r in range(3) for c in range(3)])
DIRECTIONS = np.arange(0, 360, 30)
SPEEDS = [6.0, 8.0, 10.0, 12.0]
CANDS = np.arange(-30, 31, 5, dtype=float)

fm = FlorisModel(str(Path(floris.__file__).parent / "default_inputs.yaml"))
fm.set(
    layout_x=LAYOUT_X.tolist(),
    layout_y=LAYOUT_Y.tolist(),
    wind_directions=[270.0],
    wind_speeds=[8.0],
    turbulence_intensities=[0.06],
)


def streamwise_key(wd):
    """上游→下游排序键：迎向来流方向的投影（FLORIS 风自 wd 吹向 wd+180）。"""
    return -(LAYOUT_X * np.sin(np.radians(wd)) + LAYOUT_Y * np.cos(np.radians(wd)))


def total_power_kw():
    return float(fm.get_turbine_powers()[0].sum()) / 1000.0


def greedy_per_turbine(order):
    """通道 1：逐机贪心（上游→下游，单机 13 候选）。"""
    best_yaws = np.zeros(9)
    best_total = -1.0
    for t in order:
        loc_best_p, loc_best_y = -1.0, 0.0
        for cand in CANDS:
            trial = best_yaws.copy()
            trial[t] = cand
            fm.set(yaw_angles=trial.reshape(1, -1))
            fm.run()
            p = total_power_kw()
            if p > loc_best_p:
                loc_best_p, loc_best_y = p, cand
        best_yaws[t] = loc_best_y
        best_total = loc_best_p
    return best_total, best_yaws


def greedy_row_rank(order):
    """通道 2：按风位秩次 3 台一组、组内共用偏航角的行贪心。

    wd=270° 时秩次分组即物理三排，本通道与 generate_array_independent.py
    等价（应复现其 10041.46 kW）。两个通道是路径互异的局部搜索，互不支配，
    故最终取二者之优（2026-08-10 审计找到的教训：贪心不满足自由度单调性）。
    """
    groups = [order[0:3], order[3:6], order[6:9]]
    best_yaws = np.zeros(9)
    best_total = -1.0
    for grp in groups:
        loc_best_p, loc_best_y = -1.0, 0.0
        for cand in CANDS:
            trial = best_yaws.copy()
            trial[grp] = cand
            fm.set(yaw_angles=trial.reshape(1, -1))
            fm.run()
            p = total_power_kw()
            if p > loc_best_p:
                loc_best_p, loc_best_y = p, cand
        best_yaws[grp] = loc_best_y
        best_total = loc_best_p
    return best_total, best_yaws


def run():
    rows = []
    t0 = time.time()
    n_run = 0
    for wd in DIRECTIONS:
        order = np.argsort(streamwise_key(wd))  # 上游在前
        for U in SPEEDS:
            fm.set(wind_directions=[float(wd)], wind_speeds=[float(U)])
            yaws = np.zeros(9)
            fm.set(yaw_angles=yaws.reshape(1, -1))
            fm.run()
            base = total_power_kw()
            n_run += 1

            p_t, y_t = greedy_per_turbine(order)
            p_r, y_r = greedy_row_rank(order)
            if p_r > p_t + 1e-9:
                best_total, best_yaws, method = p_r, y_r, "row_rank"
            else:
                best_total, best_yaws, method = p_t, y_t, "per_turbine"

            row = {
                "wind_direction": int(wd),
                "U_inf": U,
                "power_base": round(base, 2),
                "power_greedy": round(best_total, 2),
                "gain_pct": round((best_total - base) / base * 100, 2),
                "greedy_method": method,
            }
            for i in range(9):
                row[f"yaw_{i+1}"] = float(best_yaws[i])
            rows.append(row)
            print(f"wd={wd:3d} U={U:4.1f}: base={base:8.1f} greedy={best_total:8.1f} "
                  f"gain={row['gain_pct']:+6.2f}%  [{method}]")

    df = pd.DataFrame(rows)
    df.to_csv("cases_array_windrose.csv", index=False)

    # ===== 内置自检 =====
    chk = df[(df.wind_direction == 270) & (df.U_inf == 8.0)].iloc[0]
    print(f"\n[自检] 270°/8 m/s: base={chk.power_base:.2f}（应≈8095.15）; "
          f"greedy={chk.power_greedy:.2f}（应≥10041.46）")
    assert abs(chk.power_base - 8095.15) < 1.0, "基准复现失败，布局/配置有误"
    assert chk.power_greedy >= 10041.46 - 1e-6, "逐机贪心不应差于逐排贪心"
    print(f"[自检] 通过。共 {n_run} 次 FLORIS 求解，耗时 {time.time()-t0:.1f}s")
    nz = df.groupby("wind_direction").gain_pct.mean()
    print("\n各风向平均增益(%):")
    print(nz.round(2).to_string())


if __name__ == "__main__":
    run()
