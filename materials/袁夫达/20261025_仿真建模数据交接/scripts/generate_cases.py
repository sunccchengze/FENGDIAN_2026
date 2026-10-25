# -*- coding: utf-8 -*-
"""生成 PINN 新版接口所需的 18 列训练数据 cases_wind.csv。

本版相比首版的三处升级
----------------------
1. **Cp 已标定**：build_table.py 把 demo 曲面的 Cp 整体乘 1.0347，
   使孤立单机功率曲线与 FLORIS 官方 nrel_5MW 表完全对齐（残差 0.00%）。
2. **逐机控制**：每台机可以有自己的 (桨距, 叶尖速比)，因此 pitch1/2/3、
   rotor_speed1/2/3 都是逐机不同的真实运行点，不再是"三台机同一个桨距"。
   实现方式：按 (风向, 三机块组合) 分组，每组用 f.set(turbine_type=[...]) 挂三张表。
3. **正对来流加密**：在 15° 网格之外额外插入 85/95/265/275°，因为深尾流误差最大。

输入（12 维，顺序严格固定）
    ambient_wind_speed_m_s, ambient_wind_direction_rad, turbulence_intensity,
    yaw1, pitch1, rotor_speed1, yaw2, pitch2, rotor_speed2, yaw3, pitch3, rotor_speed3
输出（6 维）
    P1, P2, P3, Ueff1, Ueff2, Ueff3

用法
----
    .\\.venv\\Scripts\\python.exe generate_cases.py
    .\\.venv\\Scripts\\python.exe generate_cases.py --quick     # 小样本冒烟
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from floris import FlorisModel

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out"
BASE_CONFIG = HERE / "config" / "gch_base.yaml"
TURBINE_DIR = HERE / "turbine"
TABLE_MANIFEST = OUT_DIR / "table_manifest.json"

INPUT_NAMES = [
    "ambient_wind_speed_m_s", "ambient_wind_direction_rad", "turbulence_intensity",
    "yaw1", "pitch1", "rotor_speed1",
    "yaw2", "pitch2", "rotor_speed2",
    "yaw3", "pitch3", "rotor_speed3",
]
OUTPUT_NAMES = ["P1", "P2", "P3", "Ueff1", "Ueff2", "Ueff3"]

LAYOUT_X = [0.0, 377.64, 755.28]   # 3D 间距，D = 125.88 m
LAYOUT_Y = [0.0, 0.0, 0.0]
ROTOR_DIAMETER = 125.88
RADIUS = ROTOR_DIAMETER / 2.0
HUB_HEIGHT = 90.0
AIR_DENSITY = 1.225
ETA_GEN = 0.944
RATED_POWER_W = 5.0e6
RATED_OMEGA = 12.1 * 2 * math.pi / 60.0      # 12.1 rpm -> 1.267 rad/s
COS_EXP = 1.88
WS_MIN_AXIS, WS_MAX_AXIS, WS_STEP_AXIS = 0.5, 26.0, 0.5

# 偏航策略（度，逆时针为正，相对来流）。三台机按顺序给出。
# 覆盖 0 / ±10 / +20 以及错列；不做 ±30，因为那已超出本次采样范围，
# 优化器应限制在 ±20 内（见 response_check 的结论）。
YAW_STRATEGIES = [
    ("aligned", (0.0, 0.0, 0.0)),
    ("plus10", (10.0, 10.0, 10.0)),
    ("minus10", (-10.0, -10.0, -10.0)),
    ("plus20", (20.0, 20.0, 20.0)),
    ("staggered", (20.0, -20.0, 20.0)),
]

# 桨距阶梯与速比偏好。
# 关键设计：每个风速下把所有"物理可行"的桨距档都取进来，
# 使桨距与风速**解耦**——否则模型无法把桨距效应从风速效应里分离（v2 的教训）。
PITCH_LADDER = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]
TSR_PREFERENCE = [8.0, 7.0, 6.0]        # 优先取最优速比，超转速时依次降档

# 盘面面积平均：等面积极坐标网格
DISK_RADII = 8
DISK_ANGLES = 16


def log(msg: str) -> None:
    print(msg, flush=True)


def base_wind_directions(step: float) -> np.ndarray:
    """15° 网格 + 正对来流附近的加密点（85/95/265/275）。"""
    grid = set(np.round(np.arange(0.0, 360.0, step), 3).tolist())
    for extra in (85.0, 95.0, 265.0, 275.0):
        grid.add(extra)
    return np.array(sorted(grid))


def turbine_dict(beta_deg: float, tsr: float, cp: float, ct: float, slot: int = 0) -> dict:
    """把某个 (桨距, 速比) 块做成一张完整的涡轮机定义。

    slot 用来给 turbine_type 加唯一后缀：FLORIS 会往缓存里的定义字典补一个键，
    因此即使两台机的定义完全相同，同名也会被判成"两个不同定义"而报错。
    """
    axis = np.arange(WS_MIN_AXIS, WS_MAX_AXIS + 1e-9, WS_STEP_AXIS)
    area = math.pi * RADIUS**2
    power_kw = 0.5 * AIR_DENSITY * area * axis**3 * cp * ETA_GEN / 1000.0
    return {
        "turbine_type": f"blk_tsr{int(round(tsr*10))}_pit{int(round(beta_deg))}_t{slot}",
        "hub_height": HUB_HEIGHT,
        "rotor_diameter": ROTOR_DIAMETER,
        "TSR": float(tsr),
        "operation_model": "cosine-loss",
        "power_thrust_table": {
            "wind_speed": axis.tolist(),
            "power": power_kw.tolist(),
            "thrust_coefficient": [float(ct)] * len(axis),
            "ref_air_density": AIR_DENSITY,
            "ref_tilt": 5.0,
            "cosine_loss_exponent_tilt": COS_EXP,
            "cosine_loss_exponent_yaw": COS_EXP,
        },
    }


def build_farm_config(tsr_list) -> dict:
    cfg = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    cfg["farm"]["layout_x"] = list(LAYOUT_X)
    cfg["farm"]["layout_y"] = list(LAYOUT_Y)
    cfg["farm"]["turbine_type"] = [f"placeholder{abs(hash(t)) % 10**8}" for t in tsr_list]
    cfg["solver"]["turbine_grid_points"] = 3
    return cfg


def disk_offsets() -> np.ndarray:
    frac = (np.arange(DISK_RADII) + 0.5) / DISK_RADII
    radii = RADIUS * np.sqrt(frac)
    angles = np.arange(DISK_ANGLES) * (2 * np.pi / DISK_ANGLES)
    rr, tt = np.meshgrid(radii, angles, indexing="ij")
    return np.column_stack([rr.ravel() * np.cos(tt.ravel()), rr.ravel() * np.sin(tt.ravel())])


def disk_points_global(wd_deg: float, offsets: np.ndarray):
    th = np.deg2rad(wd_deg)
    lateral = np.array([-np.cos(th), np.sin(th)])
    pts = []
    for i in range(3):
        pts.append((LAYOUT_X[i] + offsets[:, 0] * lateral[0],
                    LAYOUT_Y[i] + offsets[:, 0] * lateral[1],
                    HUB_HEIGHT + offsets[:, 1]))
    return pts


def block_power(cp: float, ws: float) -> float:
    area = math.pi * RADIUS**2
    return 0.5 * AIR_DENSITY * area * ws**3 * cp * ETA_GEN


def best_lambda(blocks: dict, ws: float, beta: float):
    """给定桨距，找最高的可行叶尖速比（转速不超额定、功率不超额定）。"""
    for lam in TSR_PREFERENCE:
        b = blocks.get((round(lam, 3), round(float(beta), 1)))
        if b is None:
            continue
        if lam * ws / RADIUS > RATED_OMEGA + 1e-9:
            continue
        if block_power(b["cp"], ws) > RATED_POWER_W:
            continue
        return b
    return None


def control_settings(blocks: dict, ws: float, max_uniform: int) -> list[dict]:
    """列出当前风速下的全部控制设置。

    与 v2 的区别：v2 是"每个风速手工挑 3 个模式"，导致 β>0 只出现在高风速、
    β=0 只出现在低风速，桨距与风速共线，模型学不到桨距效应。
    本版对每个风速把**所有物理可行的桨距档**都纳入，桨距与风速因此解耦。
    """
    avail = {}
    for beta in PITCH_LADDER:
        b = best_lambda(blocks, ws, beta)
        if b is not None:
            avail[float(beta)] = b
    if not avail:
        return []

    betas = sorted(avail)
    if len(betas) > max_uniform:                    # 均匀取 4 档，保留首尾
        idx = np.linspace(0, len(betas) - 1, max_uniform).round().astype(int)
        betas = sorted({betas[i] for i in idx})

    out = [{"name": f"uniform_b{b:g}", "blocks": [avail[b]] * 3} for b in betas]
    if len(betas) >= 3:                             # 两个逐机错列
        lo, mid, hi = betas[0], betas[len(betas) // 2], betas[-1]
        out.append({"name": "stagger_hi_low_mid",
                    "blocks": [avail[hi], avail[lo], avail[mid]]})
        out.append({"name": "stagger_lo_mid_hi",
                    "blocks": [avail[lo], avail[mid], avail[hi]]})
    elif len(betas) == 2:
        lo, hi = betas
        out.append({"name": "stagger_hi_lo_lo",
                    "blocks": [avail[hi], avail[lo], avail[lo]]})
    return out


def build_cases(args) -> list[dict]:
    blocks = {(round(b["tsr"], 3), round(float(b["pitch"]), 1)): b
              for b in json.loads(TABLE_MANIFEST.read_text(encoding="utf-8"))["blocks"]}
    cases = []
    wind_speeds = np.arange(args.ws_min, args.ws_max + 1e-9, args.ws_step)
    wind_dirs = base_wind_directions(args.wd_step)
    tis = [0.06, 0.08, 0.10]
    for ws in wind_speeds:
        settings = control_settings(blocks, float(ws), args.max_uniform)
        if not settings:
            log(f"[warn] ws={ws:.1f} 无可行控制设置，跳过")
            continue
        for wd in wind_dirs:
            for ti in tis:
                for sname, yaws in YAW_STRATEGIES:
                    for s in settings:
                        cases.append({
                            "ws": float(ws), "wd": float(wd), "ti": float(ti),
                            "yaw_strategy": sname, "yaws_deg": yaws,
                            "pattern": s["name"],
                            "blocks": [(b["pitch"], b["tsr"], b["cp"], b["ct"]) for b in s["blocks"]],
                        })
    return cases


def run_cases(args) -> dict:
    cases = build_cases(args)
    if args.quick:
        cases = cases[:: max(1, len(cases) // 240)][:240]
    log(f"共 {len(cases)} 个工况")

    # 按 (风向, 三机块组合) 分组：组内 turbine_type 相同，可一次批量求解 + 一次批量盘面采样
    groups: dict[tuple, list[int]] = {}
    for k, c in enumerate(cases):
        key = (c["wd"], tuple((round(b[1], 3), round(b[0], 1)) for b in c["blocks"]))
        groups.setdefault(key, []).append(k)

    n = len(cases)
    powers = np.zeros((n, 3))
    power_floris = np.zeros((n, 3))
    ueff = np.zeros((n, 3))
    offsets = disk_offsets()
    t_all = time.time()

    for gi, ((wd_deg, tri), idx) in enumerate(sorted(groups.items())):
        sub = [cases[k] for k in idx]
        # 组内三机的块组合固定
        turbs = [turbine_dict(beta, tsr, cp, ct, slot=i)
                 for i, (beta, tsr, cp, ct) in enumerate(sub[0]["blocks"])]
        cfg = build_farm_config([t["TSR"] for t in turbs])
        cfg["farm"]["turbine_type"] = turbs
        fmodel = FlorisModel(cfg)

        ws = np.array([c["ws"] for c in sub])
        ti = np.array([c["ti"] for c in sub])
        yaw = np.array([c["yaws_deg"] for c in sub])
        fmodel.set(wind_speeds=ws, wind_directions=np.full(len(sub), wd_deg),
                   turbulence_intensities=ti, yaw_angles=yaw)
        fmodel.run()
        power_floris[idx] = fmodel.get_turbine_powers()

        pts = disk_points_global(wd_deg, offsets)
        xs = np.concatenate([p[0] for p in pts])
        ys = np.concatenate([p[1] for p in pts])
        zs = np.concatenate([p[2] for p in pts])
        u = fmodel.sample_flow_at_points(xs, ys, zs)
        per = offsets.shape[0]
        ueff[idx] = np.column_stack(
            [np.cbrt(np.mean(u[:, i * per:(i + 1) * per] ** 3, axis=1)) for i in range(3)])
        if (gi + 1) % 40 == 0:
            log(f"  分组 {gi + 1}/{len(groups)}  已用 {time.time() - t_all:.0f}s")

    log(f"  全部求解+采样总耗时 {time.time() - t_all:.1f} s")

    cp = np.array([[b[2] for b in c["blocks"]] for c in cases])
    tsr = np.array([[b[1] for b in c["blocks"]] for c in cases])
    yaw_rad = np.deg2rad(np.array([c["yaws_deg"] for c in cases]))
    area = math.pi * RADIUS**2
    powers = 0.5 * AIR_DENSITY * area * ueff**3 * cp * ETA_GEN * np.cos(yaw_rad) ** COS_EXP
    omega = tsr * ueff / RADIUS

    gap = np.abs(powers - power_floris) / np.maximum(power_floris, 1.0)
    log(f"  与 FLORIS 自身 9 点功率的差异：中位 {np.median(gap)*100:.2f}%，"
        f"95 分位 {np.percentile(gap,95)*100:.2f}%")
    return {"cases": cases, "powers": powers, "power_floris": power_floris,
            "ueff": ueff, "omega": omega}


def validate_rows(rows: list[dict]) -> list[str]:
    problems = []
    for i, r in enumerate(rows):
        for key in ("P1", "P2", "P3"):
            if r[key] < 0 or r[key] > RATED_POWER_W * 1.0005:
                problems.append(f"第 {i} 行 {key}={r[key]:.0f} W 越界")
        for key in ("Ueff1", "Ueff2", "Ueff3"):
            if not r[key] > 0:
                problems.append(f"第 {i} 行 {key}={r[key]} 非正")
        for key in ("rotor_speed1", "rotor_speed2", "rotor_speed3"):
            if r[key] < 0:
                problems.append(f"第 {i} 行 {key} 为负")
    return problems


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(",".join(INPUT_NAMES + OUTPUT_NAMES) + "\n")
        for r in rows:
            fh.write(
                f"{r['ambient_wind_speed_m_s']:.6f},"
                f"{r['ambient_wind_direction_rad']:.10f},"
                f"{r['turbulence_intensity']:.6f},"
                f"{r['yaw1']:.8f},{r['pitch1']:.8f},{r['rotor_speed1']:.8f},"
                f"{r['yaw2']:.8f},{r['pitch2']:.8f},{r['rotor_speed2']:.8f},"
                f"{r['yaw3']:.8f},{r['pitch3']:.8f},{r['rotor_speed3']:.8f},"
                f"{r['P1']:.6f},{r['P2']:.6f},{r['P3']:.6f},"
                f"{r['Ueff1']:.6f},{r['Ueff2']:.6f},{r['Ueff3']:.6f}\n"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ws-min", type=float, default=5.0)
    ap.add_argument("--ws-max", type=float, default=12.0)
    ap.add_argument("--ws-step", type=float, default=0.5)
    ap.add_argument("--wd-step", type=float, default=15.0)
    ap.add_argument("--max-uniform", type=int, default=4,
                    help="每个风速取几个统一桨距档（0 与最高档必留）")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT_DIR / "cases_wind.csv")
    args = ap.parse_args()
    args.out = args.out if args.out.is_absolute() else (Path.cwd() / args.out).resolve()

    if not TABLE_MANIFEST.is_file():
        raise SystemExit("请先运行 build_table.py")

    result = run_cases(args)
    cases, powers, ueff, omega = result["cases"], result["powers"], result["ueff"], result["omega"]

    rows = []
    for k, c in enumerate(cases):
        th_flow = np.deg2rad((270.0 - c["wd"]) % 360.0)
        yaws = np.deg2rad(np.array(c["yaws_deg"]))
        pits = np.deg2rad(np.array([b[0] for b in c["blocks"]]))
        rows.append({
            "ambient_wind_speed_m_s": c["ws"],
            "ambient_wind_direction_rad": float(th_flow),
            "turbulence_intensity": c["ti"],
            "yaw1": float(yaws[0]), "pitch1": float(pits[0]), "rotor_speed1": float(omega[k, 0]),
            "yaw2": float(yaws[1]), "pitch2": float(pits[1]), "rotor_speed2": float(omega[k, 1]),
            "yaw3": float(yaws[2]), "pitch3": float(pits[2]), "rotor_speed3": float(omega[k, 2]),
            "P1": float(powers[k, 0]), "P2": float(powers[k, 1]), "P3": float(powers[k, 2]),
            "Ueff1": float(ueff[k, 0]), "Ueff2": float(ueff[k, 1]), "Ueff3": float(ueff[k, 2]),
        })

    problems = validate_rows(rows)
    if problems:
        for p in problems[:15]:
            log("[FAIL] " + p)
        raise SystemExit(f"共 {len(problems)} 条不通过校验，未写出。")

    write_csv(rows, args.out)

    payload = args.out.read_bytes()
    table_manifest = json.loads(TABLE_MANIFEST.read_text(encoding="utf-8"))
    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "rows": len(rows),
        "csv": str(args.out.relative_to(HERE)),
        "csv_sha256": hashlib.sha256(payload).hexdigest(),
        "columns": INPUT_NAMES + OUTPUT_NAMES,
        "layout": {"x": LAYOUT_X, "y": LAYOUT_Y, "rotor_diameter": ROTOR_DIAMETER,
                   "hub_height": HUB_HEIGHT, "spacing_D": 3.0},
        "scan": {
            "ws": [args.ws_min, args.ws_max, args.ws_step],
            "wd": base_wind_directions(args.wd_step).tolist(),
            "ti": [0.06, 0.08, 0.10],
            "yaw_strategies": {name: list(y) for name, y in YAW_STRATEGIES},
            "control_patterns_note": "每个风速下所有物理可行的桨距档都入选（解耦桨距与风速），另加逐机错列",
            "pitch_ladder_deg": PITCH_LADDER,
            "tsr_preference": TSR_PREFERENCE,
            "max_uniform_per_ws": args.max_uniform,
        },
        "units": {"wind_speed": "m/s", "direction": "rad (flow-to)", "yaw": "rad",
                  "pitch": "rad", "rotor_speed": "rad/s", "power": "W (electrical)", "ueff": "m/s"},
        "ueff_sampling": {"radii": DISK_RADII, "angles": DISK_ANGLES,
                          "points_per_rotor": DISK_RADII * DISK_ANGLES,
                          "method": "cubic-mean (cbrt of mean u^3), equal-area polar grid"},
        "power_method": (
            "每台机用自己 (桨距, 速比) 块的表；FLORIS 提供流场，功率由 128 点盘面积分"
            "P = 0.5*rho*A*Ueff^3*Cp_i*eta*cos^1.88(yaw_i) 计算"
        ),
        "cp_calibration": table_manifest.get("cp_calibration"),
        "per_turbine_control": True,
        "floris_version": __import__("floris").__version__,
        "quick": bool(args.quick),
    }
    (OUT_DIR / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    log(f"[OK] 写出 {len(rows)} 行 -> {args.out}")
    log("[OK] 校验通过：P∈[0,5MW]、Ueff>0、转速≥0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
