#!/usr/bin/env python3
"""solver.html 算法对比表的可复现基准。

口径：Python 3.11 · FLORIS 4.6.6 · SciPy（SLSQP ftol=1e-3；差分进化 popsize=10 /
maxiter=12 / seed=1）。两台串列 NREL 5MW，间距 5D，U=8 m/s，TI=6%。
单目标：max P_total(yaw1)，yaw2 固定 0°。代理模型为 cases_multi.csv 双线性插值。

用法：
    python3 site/benchmark_solver.py
"""
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution, minimize

import floris
from floris import FlorisModel

ROOT = Path(__file__).resolve().parent.parent

# ---- 代理模型: cases_multi.csv 双线性插值(与 site/assets/js/interp.js 同算法) ----
df = pd.read_csv(ROOT / "cases_multi.csv")
df["pt"] = df.power_1 + df.power_2
WS = sorted(df.U_inf.unique())
YS = sorted(df.yaw_1.unique())
P = np.zeros((len(WS), len(YS)))
for i, U in enumerate(WS):
    for j, y in enumerate(YS):
        P[i, j] = df[(df.U_inf == U) & (df.yaw_1 == y)].pt.iloc[0]


def bl(U, y):
    U = max(WS[0], min(WS[-1], U))
    y = max(YS[0], min(YS[-1], y))
    i = max(0, min(int(np.searchsorted(WS, U)) - 1, len(WS) - 2))
    j = max(0, min(int(np.searchsorted(YS, y)) - 1, len(YS) - 2))
    tx = (U - WS[i]) / (WS[i + 1] - WS[i])
    ty = (y - YS[j]) / (YS[j + 1] - YS[j])
    return (P[i, j] * (1 - tx) + P[i, j + 1] * tx) * (1 - ty) + (
        P[i + 1, j] * (1 - tx) + P[i + 1, j + 1] * tx
    ) * ty


def bench_surrogate(reps=1000):
    t0 = time.perf_counter()
    for _ in range(reps):
        cand = np.linspace(-30, 30, 61)
        vals = [bl(8.0, y) for y in cand]
        k = int(np.argmax(vals))
    dt = (time.perf_counter() - t0) / reps
    return dt, cand[k], vals[k]


# ---- FLORIS 全保真目标 ----
fm = FlorisModel(str(Path(floris.__file__).parent / "default_inputs.yaml"))
fm.set(
    layout_x=[0.0, 630.0],
    layout_y=[0.0, 0.0],
    wind_directions=[270.0],
    wind_speeds=[8.0],
    turbulence_intensities=[0.06],
)


def neg_total(x):
    fm.set(yaw_angles=np.array([[float(x[0]), 0.0]]))
    fm.run()
    return -float(fm.get_turbine_powers()[0].sum()) / 1000.0


if __name__ == "__main__":
    dt, ybest, vbest = bench_surrogate()
    print(f"代理模型 61 点穷举: {dt*1000:.3f} ms/次 -> {ybest:+.2f}°, {vbest:.1f} kW")

    t0 = time.perf_counter()
    r1 = minimize(neg_total, [0.0], method="SLSQP",
                  bounds=[(-30, 30)], options={"maxiter": 30, "ftol": 1e-3})
    t1 = time.perf_counter() - t0
    print(f"FLORIS+SLSQP: nfev={r1.nfev}  耗时={t1:.2f} s  -> "
          f"{r1.x[0]:+.1f}°, {-r1.fun:.1f} kW")

    t0 = time.perf_counter()
    r2 = differential_evolution(neg_total, [(-30, 30)], popsize=10,
                                maxiter=12, tol=1e-4, seed=1, polish=True)
    t2 = time.perf_counter() - t0
    print(f"FLORIS+差分进化: nfev={r2.nfev}  耗时={t2:.2f} s  -> "
          f"{r2.x[0]:+.1f}°, {-r2.fun:.1f} kW")

    print(f"提速比: vs SLSQP ≈ {t1/dt:.0f}× | vs 差分进化 ≈ {t2/dt:.0f}×")
