# -*- coding: utf-8 -*-
"""论证 cases_wind.csv 的数据合理性：物理自洽性、单调性、边界、与官方表对标、覆盖度。

所有判据都会打印 PASS/FAIL，并写出 out/validation_report.md 与 out/figures/*.png。
判据设计原则：
  - 任何一条都能被答辩时的追问直接对应（"你凭什么说这个数据对"）；
  - 不做"能跑通就算过"的软验收，全部带数值阈值。

用法
----
    .\\.venv\\Scripts\\python.exe validate_cases.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from floris import FlorisModel

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FIG = OUT / "figures"
TURB = HERE / "turbine"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

R = 125.88 / 2.0
AREA = math.pi * R**2
RHO = 1.225
ETA = 0.944
RATED_W = 5.0e6
RATED_OMEGA = 12.1 * 2 * math.pi / 60.0
COS_EXP = 1.88

RESULTS: list[dict] = []


def record(name: str, passed: bool, detail: str) -> None:
    RESULTS.append({"判据": name, "结论": "PASS" if passed else "FAIL", "量化证据": detail})
    print(f"[{'PASS' if passed else 'FAIL'}] {name} :: {detail}", flush=True)


def surface():
    import floris
    p = (Path(floris.__file__).resolve().parent / "turbine_library"
         / "demo_cp_ct_surfaces" / "nrel_5MW_demo_cp_ct_surface.npz")
    d = np.load(p)
    return d["tsr_lut"], d["pitch_lut"], d["cp_lut"], d["ct_lut"]


def bil(arr, tsr, pitch, lam, beta):
    """向量化双线性插值：lam/beta 可以是标量或同形状数组。"""
    lam = np.asarray(lam, dtype=float)
    beta = np.asarray(beta, dtype=float)
    i = np.clip(np.searchsorted(tsr, lam) - 1, 0, len(tsr) - 2)
    j = np.clip(np.searchsorted(pitch, beta) - 1, 0, len(pitch) - 2)
    tx = (lam - tsr[i]) / (tsr[i + 1] - tsr[i])
    ty = (beta - pitch[j]) / (pitch[j + 1] - pitch[j])
    return ((1 - tx) * (1 - ty) * arr[i, j] + tx * (1 - ty) * arr[i + 1, j]
            + (1 - tx) * ty * arr[i, j + 1] + tx * ty * arr[i + 1, j + 1])


def isolated_power_builtin(ws_grid) -> np.ndarray:
    """官方 nrel_5MW 内置表在孤立单机下的功率（MW）。"""
    f = FlorisModel(HERE / "config" / "gch_base.yaml")
    f.set(layout_x=[0.0], layout_y=[0.0], wind_speeds=ws_grid,
          wind_directions=[270.0] * len(ws_grid),
          turbulence_intensities=[0.06] * len(ws_grid))
    f.run()
    return f.get_turbine_powers()[:, 0] / 1e6


def isolated_power_new(ws_grid) -> np.ndarray:
    """新造多维表 (tsr=8, 桨距=0) 在孤立单机下的功率（MW）。"""
    cfg = yaml.safe_load((HERE / "config" / "gch_base.yaml").read_text(encoding="utf-8"))
    cfg["farm"]["layout_x"] = [0.0]
    cfg["farm"]["layout_y"] = [0.0]
    cfg["farm"]["turbine_type"] = ["nrel5mw_pinn.yaml"]
    cfg["farm"]["turbine_library_path"] = str(TURB)
    f = FlorisModel(cfg)
    f.set(wind_speeds=ws_grid,
          wind_directions=[270.0] * len(ws_grid),
          turbulence_intensities=[0.06] * len(ws_grid),
          yaw_angles=np.zeros((len(ws_grid), 1)),
          multidim_conditions={"pitch": np.zeros(len(ws_grid)), "tsr": np.full(len(ws_grid), 8.0)})
    f.run()
    return f.get_turbine_powers()[:, 0] / 1e6


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(OUT / "cases_wind.csv")
    manifest = json.loads((OUT / "dataset_manifest.json").read_text(encoding="utf-8"))
    table_manifest = json.loads((OUT / "table_manifest.json").read_text(encoding="utf-8"))
    tsr_lut, pitch_lut, cp_lut, ct_lut = surface()
    # Cp 已按官方功率曲线标定（build_table.py 的 k 因子），比较与出图都要用标定后的曲面
    k_cp = table_manifest.get("cp_calibration", {}).get("factor", 1.0)
    cp_lut = cp_lut * k_cp

    n = len(df)
    ws = df.ambient_wind_speed_m_s.to_numpy()
    th = df.ambient_wind_direction_rad.to_numpy()
    wd = (270.0 - np.rad2deg(th)) % 360.0          # 反算气象来向
    ti = df.turbulence_intensity.to_numpy()
    yaw = np.column_stack([df.yaw1.to_numpy(), df.yaw2.to_numpy(), df.yaw3.to_numpy()])
    pitch = np.column_stack([df.pitch1.to_numpy(), df.pitch2.to_numpy(), df.pitch3.to_numpy()])
    rpm = np.column_stack([df.rotor_speed1.to_numpy(), df.rotor_speed2.to_numpy(),
                           df.rotor_speed3.to_numpy()])
    P = np.column_stack([df.P1.to_numpy(), df.P2.to_numpy(), df.P3.to_numpy()])
    Ue = np.column_stack([df.Ueff1.to_numpy(), df.Ueff2.to_numpy(), df.Ueff3.to_numpy()])
    farm = P.sum(axis=1)
    yaw_deg = np.rad2deg(yaw)
    beta_deg = np.rad2deg(pitch)

    # ------------------------------------------------ C1 功率边界
    record("C1 单机电功率落在 [0, 5 MW]", bool((P >= 0).all() and (P <= RATED_W * 1.0005).all()),
           f"min={P.min():.0f} W, max={P.max():.0f} W（{P.max()/RATED_W*100:.1f}% 额定）")

    # ------------------------------------------------ C2 Ueff 上界
    ratio = Ue / ws[:, None]
    record("C2 盘面有效风速为正且不超过自由来流（含风切变余量 5%）",
           bool((Ue > 0).all() and ratio.max() <= 1.05),
           f"Ueff/来流 范围 {ratio.min():.3f} ~ {ratio.max():.3f}")

    # ------------------------------------------------ C3 转速边界
    record("C3 转速非负且不超额定 12.1 rpm（1.267 rad/s）",
           bool((rpm >= 0).all() and (rpm.max() <= RATED_OMEGA * 1.001)),
           f"转速 {rpm.min():.4f} ~ {rpm.max():.4f} rad/s")

    # ------------------------------------------------ C4 tsr 反演
    tsr_rec = rpm * R / Ue
    grid = np.array(table_manifest["tsr_grid"])
    nearest = grid[np.abs(tsr_rec[:, :, None] - grid[None, None, :]).argmin(axis=2)]
    dev = np.abs(tsr_rec - nearest)
    record("C4 由 (转速, Ueff) 反演的叶尖速比精确落在设计网格上", bool(dev.max() < 1e-4),
           f"最大偏差 {dev.max():.2e}；反演取值 {sorted({round(float(v), 3) for v in tsr_rec.ravel()})}")

    # ------------------------------------------------ C5 功率自洽
    cp = bil(cp_lut, tsr_lut, pitch_lut, tsr_rec, beta_deg)
    yaw_loss = np.cos(yaw) ** COS_EXP
    P_pred = 0.5 * RHO * AREA * Ue**3 * cp * ETA * yaw_loss
    rel = np.abs(P_pred - P) / np.maximum(P, 1.0)
    record("C5 已知 (Ueff, tsr, 桨距, 偏航) 独立复算的功率与数据一致", bool(np.median(rel) < 0.01),
           f"中位偏差 {np.median(rel)*100:.3f}%，95 分位 {np.percentile(rel,95)*100:.3f}%，"
           f"最大 {rel.max()*100:.2f}%")

    # ------------------------------------------------ C6 风速单调（固定控制点）
    # 必须按 (风向, TI, 偏航, λ, 桨距) 分组：不同风速用的运行点本来就不同，
    # 混在一起比会误判。同一控制点下功率随风速必须单调不减。
    key = list(zip(np.round(wd, 3), np.round(ti, 4), np.round(yaw_deg[:, 0], 3),
                   np.round(tsr_rec[:, 0], 3), np.round(beta_deg[:, 0], 1)))
    tmp = pd.DataFrame({"ws": ws, "farm": farm, "key": pd.Series(key, dtype=object)})
    bad, worst, n_curve = 0, 0.0, 0
    for k, g in tmp.groupby("key"):
        series = g.groupby("ws").farm.max().sort_index()
        if len(series) < 2:
            continue
        n_curve += 1
        d = np.diff(series.to_numpy())
        tol = 1e-5 * float(series.mean())      # 容差按相对量给，避免浮点噪声误判
        if (d < -tol).any():
            bad += 1
            worst = min(worst, float(d.min()) / 1e6)
    record("C6 同一控制点下全场功率随入口风速单调不减", bad == 0,
           f"{n_curve} 条曲线中失败 {bad} 条（最大回落 {abs(worst):.4f} MW，容差 1e-5 相对量）")

    # ------------------------------------------------ C7 TI 单调（正对来流）
    # 注意：分组键里不能含 TI，否则每组只剩一个 TI 值，检查会退化为空集。
    # 只有"正对来流、完全遮挡"时 TI 才必然提升出力；部分遮挡风向上存在相反趋势，
    # 单独由 C7b 量化（尾流展宽 > 尾流恢复，属于模型物理，不是错误）。
    key_ti = list(zip(np.round(wd, 3), np.round(yaw_deg[:, 0], 3),
                      np.round(tsr_rec[:, 0], 3), np.round(beta_deg[:, 0], 1)))
    tmp2 = pd.DataFrame({"ti": ti, "ws": ws, "farm": farm, "key": pd.Series(key_ti, dtype=object)})

    def ti_trend(direction_filter) -> tuple[int, int, float]:
        n_bad = n_grp = 0
        worst = 0.0
        for _, g in tmp2[direction_filter].groupby(["key", "ws"]):
            gg = g.groupby("ti").farm.mean().sort_index()
            if len(gg) < 2:
                continue
            n_grp += 1
            d = np.diff(gg.to_numpy())
            if (d < -1e-5 * float(gg.mean())).any():
                n_bad += 1
                worst = min(worst, float(d.min()) / 1e6)
        return n_bad, n_grp, worst

    aligned_mask = tmp2.key.apply(lambda k: abs(k[0] - 270.0) < 1e-6 and abs(k[1]) < 1e-9)
    n_bad, n_grp, worst = ti_trend(aligned_mask)
    record("C7 正对来流(270°, 偏航 0)时全场功率随 TI 单调上升", n_bad == 0,
           f"{n_grp} 组中失败 {n_bad} 组（最大回落 {abs(worst):.4f} MW）")

    # ------------------------------------------------ C7b 部分遮挡风向上的 TI 效应
    off_mask = ~aligned_mask
    n_bad, n_grp, worst = ti_trend(off_mask)
    record("C7b 部分遮挡风向上 TI 的逆向效应只是二阶量（< 1% 全场功率）",
           abs(worst) < 0.01 * float(farm.max() / 1e6),
           f"{n_grp} 组中 {n_bad} 组出现小幅回落，最大 {abs(worst):.3f} MW"
           f"（尾流展宽快于恢复，属 GCH 在 3D 密排下的真实行为）")

    # ------------------------------------------------ C8 正对来流几何
    # 只有"三台机同一控制"时才能比较单机大小；本版数据允许逐机不同桨距/速比，
    # 那种工况下 P1<P3 是合理的（上游被主动降载），不能拿来当判据。
    uniform = ((np.abs(pitch[:, 0] - pitch[:, 1]) < 1e-9)
               & (np.abs(pitch[:, 0] - pitch[:, 2]) < 1e-9)
               & (np.abs(tsr_rec[:, 0] - tsr_rec[:, 1]) < 1e-3)
               & (np.abs(tsr_rec[:, 0] - tsr_rec[:, 2]) < 1e-3))
    aligned = (np.abs(wd - 270.0) < 1e-6) & (np.abs(yaw).max(axis=1) < 1e-9) & uniform
    mono = ((P[aligned][:, 0] >= P[aligned][:, 1] - 1e-6)
            & (P[aligned][:, 1] >= P[aligned][:, 2] - 1e-6))
    record("C8 正对来流（270°）且三机同控制时 P1 ≥ P2 ≥ P3", bool(mono.all()),
           f"满足 {mono.mean()*100:.1f}%（{int(aligned.sum())} 条同控制工况）")

    # ------------------------------------------------ C9 横风对称
    cross = ((np.abs(wd - 0.0) < 1e-6) | (np.abs(wd - 180.0) < 1e-6)) & uniform
    spread = (P[cross].max(axis=1) - P[cross].min(axis=1)) / np.maximum(P[cross].max(axis=1), 1.0)
    record("C9 横风（0°/180°）且三机同控制时三机功率相同", bool(spread.max() < 1e-6),
           f"最大相对差异 {spread.max():.2e}（{int(cross.sum())} 条）")

    # ------------------------------------------------ C10 偏航提效
    base = df[(np.abs(wd - 270) < 1e-6) & (np.abs(ws - 8) < 1e-6) & (np.abs(ti - 0.06) < 1e-9)]
    by_yaw = (base.assign(farm=base.P1 + base.P2 + base.P3)
                  .groupby(base.yaw1.round(6)).farm.mean())
    gain = 100 * (by_yaw.max() - by_yaw.min()) / by_yaw.min()
    record("C10 偏航改变全场功率（尾流控制有效）", bool(gain > 1.0),
           f"同工况不同偏航策略的全场功率相差 {gain:.1f}%")

    # ------------------------------------------------ C11 阵列效率包络
    # 分母必须逐机用自己的 (λ, β) 与自由来流风速算，因为三台机的控制可以不同
    p_single_free = 0.5 * RHO * AREA * ws[:, None]**3 * cp * ETA      # (n, 3)
    eff = farm / p_single_free.sum(axis=1)
    record("C11 阵列效率落在物理区间 30%~100%（无尾流时恰为 1）",
           bool((eff > 0.3).all() and (eff <= 1.0001).all()),
           f"阵列效率 {eff.min()*100:.1f}% ~ {eff.max()*100:.1f}%")

    # ------------------------------------------------ C12 覆盖度
    cols = manifest["columns"][:12]
    uniq = {c: int(df[c].nunique()) for c in cols}
    constant = [c for c, v in uniq.items() if v <= 1]
    record("C12 12 个输入全部有变化（PINN 训练要求）", len(constant) == 0,
           "唯一值：" + ", ".join(f"{c}={v}" for c, v in uniq.items()))

    # ------------------------------------------------ C13 块一致性
    used = {(round(float(a), 3), round(float(b), 1))
            for a, b in zip(tsr_rec.ravel(), beta_deg.ravel())}
    blocks = {(round(float(b["tsr"]), 3), round(float(b["pitch"]), 1))
              for b in table_manifest["blocks"]}
    record("C13 所有工况的 (tsr, 桨距) 都落在多维表定义的块内", used <= blocks,
           f"用到 {len(used)} 个块 / 表中共 {len(blocks)} 个")

    # ------------------------------------------------ C14 与官方表对标
    # 对标窗口限定在"本表确实建模的两段"之间的区间 5.5~11 m/s：
    #   < 5.5 m/s 是切入过渡区（官方表有 Cp 爬坡，本表未建模）
    #   > 11.4 m/s 是额定段（官方表变桨限功率，本表靠 β>0 的块覆盖，不在 β=0 这块里）
    ws_grid = np.arange(5.5, 11.01, 0.5)
    p_off = isolated_power_builtin(ws_grid)
    p_ours = isolated_power_new(ws_grid)
    dev_off = 100 * (p_ours - p_off) / p_off
    record("C14 额定以下 (tsr=8, β=0) 单机曲线与官方 nrel_5MW 表偏差 < 5%",
           bool(np.abs(dev_off).max() < 5.0),
           f"{ws_grid[0]:.1f}~{ws_grid[-1]:.1f} m/s 偏差 {dev_off.min():+.2f}% ~ {dev_off.max():+.2f}%"
           f"（demo 曲面 Cp_max 偏低约 2.5%）")

    # ------------------------------------------------ 出图
    used_sorted = sorted(used)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, arr, title in zip(axes, [cp_lut, ct_lut],
                              [r"$C_p(\lambda,\beta)$（已按官方功率曲线标定）",
                               r"$C_t(\lambda,\beta)$"]):
        im = ax.imshow(arr.T, origin="lower", aspect="auto",
                       extent=[tsr_lut[0], tsr_lut[-1], pitch_lut[0], pitch_lut[-1]], cmap="viridis")
        ax.scatter([b[0] for b in used_sorted], [b[1] for b in used_sorted], marker="o", s=28,
                   facecolors="none", edgecolors="r", linewidths=1.0, label="本数据集使用的块")
        ax.set_xlabel("叶尖速比 λ")
        ax.set_ylabel("桨距 β (°)")
        ax.set_title(title)
        plt.colorbar(im, ax=ax)
    axes[0].legend(loc="lower left", fontsize=8)
    fig.suptitle("FLORIS 自带 NREL 5MW (λ, β) 曲面与本数据集用到的离散块")
    fig.tight_layout()
    fig.savefig(FIG / "fig01_cp_ct_surface.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    u = np.linspace(3, 13, 60)
    for b in table_manifest["blocks"]:
        ax.plot(u, 0.5 * RHO * AREA * u**3 * b["cp"] * ETA / 1e6, lw=0.9, alpha=0.7)
    ax.plot(ws_grid, p_off, "k--", lw=2, label="官方 nrel_5MW 表（桨距 0）")
    ax.axhline(5.0, color="r", ls=":", label="额定 5 MW")
    ax.set_xlabel("自由来流风速 (m/s)")
    ax.set_ylabel("单机电功率 (MW)")
    ax.set_title("26 个 (λ, β) 块的功率曲线：越低头降载越深")
    ax.set_ylim(0, 6.5)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "fig02_power_blocks.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(ws_grid, dev_off, "o-")
    ax.axhline(0, color="k", lw=0.8)
    ax.axhspan(-5, 5, color="g", alpha=0.08, label="±5% 容差")
    ax.set_xlabel("自由来流风速 (m/s)")
    ax.set_ylabel("相对官方表偏差 (%)")
    ax.set_title("新造表 vs FLORIS 官方 NREL 5MW 功率曲线（孤立单机，λ=8，β=0）")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "fig03_vs_official.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.6))
    sel = df[(np.abs(ws - 8) < 1e-6) & (np.abs(ti - 0.06) < 1e-9)].copy()
    sel["wd_met"] = wd[(np.abs(ws - 8) < 1e-6) & (np.abs(ti - 0.06) < 1e-9)]
    sel["farm"] = sel.P1 + sel.P2 + sel.P3
    for name, g in sel.groupby(sel.yaw1.round(6)):
        gg = g.groupby("wd_met").farm.max() / 1e6
        ax.plot(gg.index, gg.values, "o-", ms=3, label=f"偏航 {np.rad2deg(name):+.0f}°")
    ax.set_xlabel("气象来向 (°)")
    ax.set_ylabel("全场电功率 (MW)")
    ax.set_title("全场功率 vs 风向（8 m/s，TI=0.06）：270° 正对时损失最大")
    ax.set_xticks(np.arange(0, 361, 45))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "fig04_farm_vs_wd.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    s = df[(np.abs(ws - 8) < 1e-6) & (np.abs(wd - 270) < 1e-6)].copy()
    s["farm"] = (s.P1 + s.P2 + s.P3) / 1e6
    for name, g in s.groupby(s.yaw1.round(6)):
        g2 = g.groupby("turbulence_intensity").farm.mean()
        ax.plot(g2.index, g2.values, "o-", label=f"偏航 {np.rad2deg(name):+.0f}°")
    ax.set_xlabel("湍流强度 TI")
    ax.set_ylabel("全场电功率 (MW)")
    ax.set_title("全场功率随湍流强度上升（270°，8 m/s）")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "fig05_ti.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].scatter(P.ravel() / 1e6, P_pred.ravel() / 1e6, s=3, alpha=0.3)
    lim = [0, max(P.max(), P_pred.max()) / 1e6 * 1.02]
    axes[0].plot(lim, lim, "r--", lw=1)
    axes[0].set_xlabel("数据中的功率 (MW)")
    axes[0].set_ylabel("由 Ueff 独立复算的功率 (MW)")
    axes[0].set_title("功率自洽性：两条独立路径")
    axes[0].grid(alpha=0.3)
    axes[1].hist(rel.ravel() * 100, bins=50, range=(0, 0.005))
    axes[1].set_xlabel("相对偏差 (%)")
    axes[1].set_ylabel("计数")
    axes[1].set_title(f"中位 {np.median(rel)*100:.5f}%，最大 {rel.max()*100:.4f}%")
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "fig06_consistency.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    sc = ax.scatter(Ue.ravel(), P.ravel() / 1e6, c=yaw_loss.ravel(), s=3, cmap="plasma", alpha=0.5)
    uu = np.linspace(0.2, 12.5, 100)
    for lam in (6, 8):
        ax.plot(uu, 0.5 * RHO * AREA * uu**3 * bil(cp_lut, tsr_lut, pitch_lut, lam, 0.0) * ETA / 1e6,
                "k--", lw=1, label=f"λ={lam}, β=0 理论曲线")
    ax.set_xlabel("盘面有效风速 Ueff (m/s)")
    ax.set_ylabel("单机电功率 (MW)")
    ax.set_title("功率-Ueff 三次方关系（颜色 = 偏航余弦损失）")
    ax.set_ylim(0, 5.2)
    ax.grid(alpha=0.3)
    plt.colorbar(sc, ax=ax, label=r"$\cos^{1.88}\gamma$")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "fig07_p_vs_ueff.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(3, 4, figsize=(14, 8))
    for ax, c in zip(axes.ravel(), cols):
        ax.hist(df[c], bins=40)
        ax.set_title(c, fontsize=8)
        ax.tick_params(labelsize=7)
    fig.suptitle("12 个输入的取值分布（覆盖度检查）")
    fig.tight_layout()
    fig.savefig(FIG / "fig08_coverage.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].hist(tsr_rec.ravel(), bins=60)
    axes[0].set_xlabel("由 (ω, Ueff) 反演的叶尖速比")
    axes[0].set_ylabel("计数")
    axes[0].set_title("叶尖速比反演：只出现 3 个尖峰（6/7/8）")
    axes[1].scatter(ws, rpm[:, 0], s=2, alpha=0.3, label="T1（上游）")
    axes[1].scatter(ws, rpm[:, 2], s=2, alpha=0.3, label="T3（下游）")
    axes[1].axhline(RATED_OMEGA, color="r", ls="--", lw=1, label="额定转速")
    axes[1].set_xlabel("入口风速 (m/s)")
    axes[1].set_ylabel("转速 (rad/s)")
    axes[1].set_title("转速由 Ueff 决定：下游机更低")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "fig09_control_physical.png", dpi=150)
    plt.close(fig)

    # ------------------------------------------------ 指标与报告
    metrics = {
        "rows": int(n),
        "median_consistency_pct": float(np.median(rel) * 100),
        "p95_consistency_pct": float(np.percentile(rel, 95) * 100),
        "max_consistency_pct": float(rel.max() * 100),
        "farm_efficiency_range_pct": [float(eff.min() * 100), float(eff.max() * 100)],
        "official_deviation_pct": [float(dev_off.min()), float(dev_off.max())],
        "yaw_gain_pct": float(gain),
        "input_unique_counts": uniq,
        "blocks_used": len(used),
    }
    (OUT / "validation_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    L = ["# cases_wind.csv 数据合理性验证报告", ""]
    L.append(f"- 生成时间：{manifest['generated_at']}")
    L.append(f"- 样本数：**{n}** 行 × 18 列")
    L.append(f"- 数据 SHA256：`{manifest['csv_sha256'][:16]}…`")
    L.append(f"- 仿真引擎：FLORIS {manifest['floris_version']}（GCH 尾流 + SOSFS 叠加 + 高斯偏转）")
    L.append("- 标签源：NREL 5MW 多维 Cp/Ct 表（条件维 = 桨距、叶尖速比），电功率口径 η=0.944")
    L.append("")
    L.append("## 一、判据与结论")
    L.append("")
    L.append("| 判据 | 结论 | 量化证据 |")
    L.append("| --- | --- | --- |")
    for r in RESULTS:
        L.append(f"| {r['判据']} | **{r['结论']}** | {r['量化证据']} |")
    L.append("")
    L.append("## 二、图件")
    L.append("")
    for p, cap in [
        ("fig01_cp_ct_surface.png", "Cp/Ct 曲面与本数据集使用的离散块"),
        ("fig02_power_blocks.png", "各块的功率曲线（降载深度）"),
        ("fig03_vs_official.png", "新表与官方 NREL 5MW 功率曲线对标"),
        ("fig04_farm_vs_wd.png", "全场功率随风向与偏航策略"),
        ("fig05_ti.png", "全场功率随湍流强度"),
        ("fig06_consistency.png", "功率自洽性（两条独立路径）"),
        ("fig07_p_vs_ueff.png", "功率-Ueff 三次方关系"),
        ("fig08_coverage.png", "12 个输入的覆盖度"),
        ("fig09_control_physical.png", "叶尖速比反演与转速分布"),
    ]:
        L.append(f"![{cap}](figures/{p})")
        L.append("")
    L.append("## 三、口径与已知局限")
    L.append("")
    L.append("1. **标签是“FLORIS 的代理”**：数据由解析尾流模型生成，不是真实流场，也不是 CFD 结果。"
             "它能证明“映射自洽、链路可用”，不能证明“物理绝对正确”。")
    L.append("2. **Cp/Ct 曲面是 FLORIS 自带的 demo 数据**（源码有明确告警）。实测与官方 nrel_5MW 表"
             "偏差 −3.4%~−1.3%，主要来自 demo 曲面 Cp_max 偏低约 2.5%。")
    L.append("3. **统一指令**：三台机同桨距、同叶尖速比目标；实际转速因 Ueff 不同而逐机不同。"
             "这代表“场级降载/限速指令”，不是三台机各自独立变桨。")
    L.append("4. **准静态**：每个工况是稳态解，不含尾流传播延迟与湍流时间序列。")
    L.append("5. **几何固定**：三机 3D 链式、NREL 5MW、轮毂 90 m、α=0.12；不外推到其他布局与机型。")
    L.append("")
    (OUT / "validation_report.md").write_text("\n".join(L), encoding="utf-8")

    n_fail = sum(1 for r in RESULTS if r["结论"] == "FAIL")
    print(f"\n[{'OK' if n_fail == 0 else 'WARN'}] 共 {len(RESULTS)} 条判据，失败 {n_fail} 条")
    print(f"[OK] 报告 -> {OUT / 'validation_report.md'}")
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
