# -*- coding: utf-8 -*-
"""从 FLORIS 自带的 (叶尖速比, 桨距) -> Cp/Ct 曲面，构造多维功率/推力表。

为什么需要这一步
----------------
FLORIS 的涡轮机模型本身只认「风速 -> 功率/推力系数」这条一维曲线（nrel_5MW.yaml），
没有桨距 beta 与转速 omega 这两个输入。而 PINN 新版接口要求
  yaw_i, pitch_i, rotor_speed_i   （i = 1,2,3）
作为 9 个控制量中的 6 个。

本脚本把 Cp/Ct 曲面折叠进 FLORIS 自己的表里：
  对每个 (桨距 beta, 叶尖速比 lam) 组合，
      功率 P(U) = 0.5 * rho * A * U^3 * Cp(lam, beta) * eta
      推力 Ct   = Ct(lam, beta)                                （常数）
写成一个「条件维 + 风速」的多维表（FLORIS v4.6 的 multi_dimensional_cp_ct 机制）。
运行时用 fmodel.set(multidim_conditions={"pitch": ..., "tsr": ...}) 逐工况选表。

为什么这样就自洽
----------------
表里 (lam, beta) 固定，意味着"控制器把叶尖速比稳定在 lam"。
于是每台机自己的实际转速 omega_i = lam * U_eff_i / R 由当地盘面风速决定，
而它查到的 Cp/Ct 恰好就是 (lam, beta) 那一格的常数 —— 功率与推力来自同一个点，
不会出现"功率按 A 算、推力按 B 算"的矛盾。

数据来源
--------
floris/turbine_library/demo_cp_ct_surfaces/nrel_5MW_demo_cp_ct_surface.npz
  tsr_lut   3.00 ~ 10.00  (29 点)
  pitch_lut -5 ~ 30 deg   (36 点)
  cp_lut / ct_lut        (29 x 36)
FLORIS 源码自带告警：该曲面为示范用途。实测与官方 nrel_5MW 表一致到 2.5% 以内
（见 validate_cases.py 的对标图）。

用法
----
    .\\.venv\\Scripts\\python.exe build_table.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

import floris

HERE = Path(__file__).resolve().parent
TURBINE_DIR = HERE / "turbine"
OUT_DIR = HERE / "out"
SURFACE = (
    Path(floris.__file__).resolve().parent
    / "turbine_library"
    / "demo_cp_ct_surfaces"
    / "nrel_5MW_demo_cp_ct_surface.npz"
)

# ---------------------------------------------------------------- 机型常量
# 全部取自 FLORIS 内置 nrel_5MW.yaml，逐项核对过
ROTOR_DIAMETER = 125.88
HUB_HEIGHT = 90.0
AIR_DENSITY = 1.225
ETA_GEN = 0.944          # nrel_5MW.yaml 注释："generator efficiency of 94.4% is assumed"
REF_TILT = 5.0
COS_EXP = 1.88

# ---------------------------------------------------------------- 离散网格
# 叶尖速比档位：覆盖"最优跟踪(8)"、"偏速运行(7)"、"高风速降速(6)"、"轻度过速(9)"
TSR_GRID = [6.0, 7.0, 8.0, 9.0]
# 桨距档位：0 = 最优效率；越大越"深降载"
PITCH_GRID = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]
# 表内风速轴
WS_MIN, WS_MAX, WS_STEP = 0.5, 26.0, 0.5
# 物理有效性下限：Cp、Ct 为负代表"风轮在耗电/风车态"，不是发电运行点
CP_MIN, CT_MIN = 0.02, 0.02


def bilinear(arr: np.ndarray, tsr: np.ndarray, pitch: np.ndarray, lam: float, beta: float) -> float:
    """在 (tsr, pitch) 网格上做双线性插值，越界直接报错（绝不外推）。"""
    if not (tsr[0] <= lam <= tsr[-1]):
        raise ValueError(f"叶尖速比 {lam} 超出曲面范围 [{tsr[0]}, {tsr[-1]}]")
    if not (pitch[0] <= beta <= pitch[-1]):
        raise ValueError(f"桨距 {beta} 超出曲面范围 [{pitch[0]}, {pitch[-1]}]")
    i = int(np.clip(np.searchsorted(tsr, lam) - 1, 0, len(tsr) - 2))
    j = int(np.clip(np.searchsorted(pitch, beta) - 1, 0, len(pitch) - 2))
    tx = (lam - tsr[i]) / (tsr[i + 1] - tsr[i])
    ty = (beta - pitch[j]) / (pitch[j + 1] - pitch[j])
    return float(
        (1 - tx) * (1 - ty) * arr[i, j]
        + tx * (1 - ty) * arr[i + 1, j]
        + (1 - tx) * ty * arr[i, j + 1]
        + tx * ty * arr[i + 1, j + 1]
    )


def load_surface():
    if not SURFACE.is_file():
        raise FileNotFoundError(f"找不到 Cp/Ct 曲面：{SURFACE}")
    data = np.load(SURFACE)
    return (
        data["tsr_lut"].astype(float),
        data["pitch_lut"].astype(float),
        data["cp_lut"].astype(float),
        data["ct_lut"].astype(float),
    )


def build_blocks():
    """枚举所有物理有效的 (桨距, 叶尖速比) 组合，返回块定义与诊断。"""
    tsr_lut, pitch_lut, cp_lut, ct_lut = load_surface()
    radius = ROTOR_DIAMETER / 2.0
    area = np.pi * radius**2

    blocks, rows, skipped = [], [], []
    for lam in TSR_GRID:
        for beta in PITCH_GRID:
            cp = bilinear(cp_lut, tsr_lut, pitch_lut, lam, beta)
            ct = bilinear(ct_lut, tsr_lut, pitch_lut, lam, beta)
            if cp < CP_MIN or ct < CT_MIN:
                skipped.append(
                    {"tsr": lam, "pitch": beta, "cp": round(cp, 4), "ct": round(ct, 4),
                     "reason": "Cp 或 Ct 低于发电运行下限（风轮不产功/负推力）"}
                )
                continue
            blocks.append({"tsr": lam, "pitch": beta, "cp": cp, "ct": ct})
            for ws in np.arange(WS_MIN, WS_MAX + 1e-9, WS_STEP):
                p_w = 0.5 * AIR_DENSITY * area * ws**3 * cp * ETA_GEN
                rows.append((beta, lam, float(ws), p_w / 1000.0, ct))

    return blocks, rows, skipped, area


def write_table(rows, path: Path) -> None:
    """列序必须严格是：条件维..., ws, power, thrust_coefficient（后三列固定）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "pitch,tsr,ws,power,thrust_coefficient"
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(header + "\n")
        for beta, lam, ws, p_kw, ct in rows:
            fh.write(f"{beta:.1f},{lam:.2f},{ws:.2f},{p_kw:.6f},{ct:.6f}\n")


def write_yaml(path: Path, csv_name: str) -> None:
    doc = {
        "turbine_type": "nrel_5MW_pinn_pitch_tsr",
        "hub_height": HUB_HEIGHT,
        "rotor_diameter": ROTOR_DIAMETER,
        # TSR 只在 GCH 的尾流旋转涡量项里作为标量使用，不参与功率查表
        "TSR": 8.0,
        "operation_model": "cosine-loss",
        "multi_dimensional_cp_ct": True,
        "power_thrust_table": {
            "ref_air_density": AIR_DENSITY,
            "ref_tilt": REF_TILT,
            "cosine_loss_exponent_tilt": COS_EXP,
            "cosine_loss_exponent_yaw": COS_EXP,
            "power_thrust_data_file": csv_name,
        },
    }
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False)


def calibrate_cp(blocks: list[dict], k: float) -> list[dict]:
    """把 Cp 整体乘 k，使孤立单机功率曲线对齐 FLORIS 官方 nrel_5MW 表。

    Ct 不标定：实测 λ=8/β=0 处 demo Ct=0.7878，官方表 8 m/s 处 0.7871，差 0.09%。
    """
    return [{**b, "cp": b["cp"] * k} for b in blocks]


def measure_isolated_power(blocks: list[dict], ws_probe: float = 8.0) -> float:
    """用当前 blocks 造一张临时单块涡轮机，算孤立单机功率（MW），用于标定/校验。"""
    from floris import FlorisModel

    def one(beta, lam, cp, ct):
        axis = np.arange(WS_MIN, WS_MAX + 1e-9, WS_STEP)
        return {
            "turbine_type": "tmp", "hub_height": HUB_HEIGHT, "rotor_diameter": ROTOR_DIAMETER,
            "TSR": lam, "operation_model": "cosine-loss",
            "power_thrust_table": {
                "wind_speed": axis.tolist(),
                "power": (0.5 * AIR_DENSITY * np.pi * (ROTOR_DIAMETER / 2) ** 2
                          * axis**3 * cp * ETA_GEN / 1000.0).tolist(),
                "thrust_coefficient": [ct] * len(axis),
                "ref_air_density": AIR_DENSITY, "ref_tilt": REF_TILT,
                "cosine_loss_exponent_tilt": COS_EXP, "cosine_loss_exponent_yaw": COS_EXP,
            },
        }

    b = next(x for x in blocks if abs(x["tsr"] - 8.0) < 1e-9 and abs(x["pitch"]) < 1e-9)
    cfg = yaml.safe_load((HERE / "config" / "gch_base.yaml").read_text(encoding="utf-8"))
    cfg["farm"]["layout_x"], cfg["farm"]["layout_y"] = [0.0], [0.0]
    cfg["farm"]["turbine_type"] = [one(b["pitch"], b["tsr"], b["cp"], b["ct"])]
    f = FlorisModel(cfg)
    f.set(wind_speeds=[ws_probe], wind_directions=[270.0], turbulence_intensities=[0.06])
    f.run()
    return float(f.get_turbine_powers()[0, 0] / 1e6)


def official_isolated_power(ws_probe: float = 8.0) -> float:
    from floris import FlorisModel
    f = FlorisModel(HERE / "config" / "gch_base.yaml")
    f.set(layout_x=[0.0], layout_y=[0.0], wind_speeds=[ws_probe],
          wind_directions=[270.0], turbulence_intensities=[0.06])
    f.run()
    return float(f.get_turbine_powers()[0, 0] / 1e6)


def main() -> int:
    blocks, _, skipped, area = build_blocks()

    # ---- Cp 标定：让孤立单机 8 m/s 功率对齐官方 nrel_5MW 表
    p_before = measure_isolated_power(blocks)
    p_official = official_isolated_power()
    k = p_official / p_before
    blocks = calibrate_cp(blocks, k)
    p_after = measure_isolated_power(blocks)

    # 用标定后的 blocks 重建表
    rows = []
    for b in blocks:
        for ws in np.arange(WS_MIN, WS_MAX + 1e-9, WS_STEP):
            p_w = 0.5 * AIR_DENSITY * area * ws**3 * b["cp"] * ETA_GEN
            rows.append((b["pitch"], b["tsr"], float(ws), p_w / 1000.0, b["ct"]))

    csv_path = TURBINE_DIR / "nrel5mw_pitch_tsr.csv"
    yaml_path = TURBINE_DIR / "nrel5mw_pinn.yaml"
    write_table(rows, csv_path)
    write_yaml(yaml_path, csv_path.name)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_surface": str(SURFACE),
        "turbine_model": "NREL 5MW (FLORIS 内置 nrel_5MW)",
        "rotor_diameter_m": ROTOR_DIAMETER,
        "hub_height_m": HUB_HEIGHT,
        "air_density_kg_m3": AIR_DENSITY,
        "rotor_area_m2": round(area, 2),
        "generator_efficiency": ETA_GEN,
        "power_definition": "electrical: P = 0.5*rho*A*U^3*Cp(tsr,pitch)*eta_gen",
        "cp_calibration": {
            "factor": round(k, 6),
            "isolated_8ms_before_MW": round(p_before, 4),
            "isolated_8ms_after_MW": round(p_after, 4),
            "official_isolated_8ms_MW": round(p_official, 4),
            "residual_pct": round(100 * (p_after - p_official) / p_official, 4),
            "reason": "demo Cp 曲面峰值比官方表低约 2.5%，整体乘因子对齐官方功率曲线；Ct 未动（差 0.09%）",
        },
        "tsr_grid": TSR_GRID,
        "pitch_grid_deg": PITCH_GRID,
        "ws_axis": {"min": WS_MIN, "max": WS_MAX, "step": WS_STEP},
        "validity_rule": f"Cp >= {CP_MIN} 且 Ct >= {CT_MIN}",
        "blocks": blocks,
        "skipped_blocks": skipped,
        "table_rows": len(rows),
        "table_csv": str(csv_path.relative_to(HERE)),
        "turbine_yaml": str(yaml_path.relative_to(HERE)),
    }
    (OUT_DIR / "table_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"[OK] Cp 标定因子 k = {k:.4f}（{p_before:.4f} -> {p_after:.4f} MW，官方 {p_official:.4f}）")
    print(f"[OK] 标定残差 {100*(p_after-p_official)/p_official:+.3f}%")
    print(f"[OK] 有效块 {len(blocks)} 个（跳过 {len(skipped)} 个非发电运行点）")
    print(f"[OK] 多维表 {len(rows)} 行 -> {csv_path}")
    print(f"[OK] 涡轮机定义 -> {yaml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
