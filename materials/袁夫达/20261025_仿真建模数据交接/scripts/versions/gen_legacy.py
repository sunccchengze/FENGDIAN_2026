# -*- coding: utf-8 -*-
"""重建 v1 / v2 两个历史版本的数据集（用于可复现性与探索过程留档）。

为什么单独写这个文件
--------------------
v1 与 v2 的 generate_cases.py 在迭代中已被覆盖。本文件按当时的设计重建两版，
并用训练报告里记录的 csv_sha256 验证是否**逐字节复现**。

  v1 = 15,264 行，统一控制（三机同桨距/同速比），Cp 未标定
  v2 = 13,440 行，逐机控制（5 个控制模式，每风速取前 3），Cp 已标定
  v3 = 20,160 行，见同级 generate_cases.py（桨距与风速解耦）

用法
----
    .\\.venv\\Scripts\\python.exe versions\\gen_legacy.py v1
    .\\.venv\\Scripts\\python.exe versions\\gen_legacy.py v2
输出写到 versions/out/cases_wind_v1.csv / _v2.csv，并打印 SHA256 与期望值对比。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT))          # 复用上级目录的 generate_cases 工具函数
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = HERE / "out"
TURBINE_MANIFEST = HERE / "table_manifest_pinned.json"

# ---- 与主脚本一致的常量
INPUT_NAMES = [
    "ambient_wind_speed_m_s", "ambient_wind_direction_rad", "turbulence_intensity",
    "yaw1", "pitch1", "rotor_speed1", "yaw2", "pitch2", "rotor_speed2",
    "yaw3", "pitch3", "rotor_speed3",
]
OUTPUT_NAMES = ["P1", "P2", "P3", "Ueff1", "Ueff2", "Ueff3"]
LAYOUT_X = [0.0, 377.64, 755.28]
LAYOUT_Y = [0.0, 0.0, 0.0]
R = 125.88 / 2
D = 125.88
HUB = 90.0
RHO = 1.225
ETA = 0.944
RATED_W = 5.0e6
RATED_OMEGA = 12.1 * 2 * math.pi / 60.0
COS_EXP = 1.88
WS_MIN_AXIS, WS_MAX_AXIS, WS_STEP_AXIS = 0.5, 26.0, 0.5
DISK_RADII, DISK_ANGLES = 8, 16

TSR_GRID = [6.0, 7.0, 8.0, 9.0]
PITCH_GRID = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]
CP_MIN, CT_MIN = 0.02, 0.02

# ---- v1 / v2 的偏航策略（当时是 4 种，含 all_minus20）
YAW_V12 = [
    ("aligned", (0.0, 0.0, 0.0)),
    ("all_plus20", (20.0, 20.0, 20.0)),
    ("all_minus20", (-20.0, -20.0, -20.0)),
    ("staggered", (20.0, -20.0, 20.0)),
]

# ---- v2 的 5 个控制模式与优先级
V2_PATTERNS = [
    ("optimal_l8", [(0.0, 8.0), (0.0, 8.0), (0.0, 8.0)]),
    ("derate_l8", [(6.0, 8.0), (6.0, 8.0), (6.0, 8.0)]),
    ("stagger_mix", [(10.0, 8.0), (0.0, 7.0), (4.0, 8.0)]),
    ("high_l6", [(8.0, 6.0), (8.0, 6.0), (8.0, 6.0)]),
    ("stagger_l6", [(12.0, 6.0), (4.0, 6.0), (8.0, 6.0)]),
]
V2_PRIORITY = ["optimal_l8", "stagger_mix", "derate_l8", "high_l6", "stagger_l6"]

EXPECTED_SHA = {
    "v1": "cf2dfeae34a015a45b5fd545332968f3c16f43db598dff3c28491e9c75931df1",
    "v2": "a22b833e4fcfa57e",
}


def log(m):
    print(m, flush=True)


def surface():
    import floris
    p = (Path(floris.__file__).resolve().parent / "turbine_library"
         / "demo_cp_ct_surfaces" / "nrel_5MW_demo_cp_ct_surface.npz")
    d = np.load(p)
    return d["tsr_lut"], d["pitch_lut"], d["cp_lut"], d["ct_lut"]


def bilinear(arr, tsr, pitch, lam, beta):
    i = int(np.clip(np.searchsorted(tsr, lam) - 1, 0, len(tsr) - 2))
    j = int(np.clip(np.searchsorted(pitch, beta) - 1, 0, len(pitch) - 2))
    tx = (lam - tsr[i]) / (tsr[i + 1] - tsr[i])
    ty = (beta - pitch[j]) / (pitch[j + 1] - pitch[j])
    return float((1 - tx) * (1 - ty) * arr[i, j] + tx * (1 - ty) * arr[i + 1, j]
                 + (1 - tx) * ty * arr[i, j + 1] + tx * ty * arr[i + 1, j + 1])


def blocks_for(version: str) -> list[dict]:
    """按版本返回 (tsr, pitch, cp, ct) 列表。

    v1：从曲面直接取（未标定，k=1）。
    v2：直接读 manifest 里记录的块——注意 manifest 里的标定因子写成了 6 位小数，
        而当时乘的是未取整的 k，所以不能拿 npz*factor 重算，必须用存档值。
    """
    if version == "v2":
        man = json.loads(TURBINE_MANIFEST.read_text(encoding="utf-8"))
        return [{"tsr": float(b["tsr"]), "pitch": float(b["pitch"]),
                 "cp": float(b["cp"]), "ct": float(b["ct"])} for b in man["blocks"]]

    tsr_lut, pitch_lut, cp_lut, ct_lut = surface()
    out = []
    for lam in TSR_GRID:
        for beta in PITCH_GRID:
            cp = bilinear(cp_lut, tsr_lut, pitch_lut, lam, beta)
            ct = bilinear(ct_lut, tsr_lut, pitch_lut, lam, beta)
            if cp < CP_MIN or ct < CT_MIN:
                continue
            out.append({"tsr": lam, "pitch": beta, "cp": cp, "ct": ct})
    return out


def block_power(cp: float, ws: float) -> float:
    return 0.5 * RHO * math.pi * R**2 * ws**3 * cp * ETA


def feasible_ops_v1(blocks: list[dict], ws: float, n_points: int) -> list[dict]:
    """v1 的运行点选择：λ=8/7/6 各自最小桨距，再加一个中等偏深的降载点。"""
    feas = [b for b in blocks
            if b["tsr"] * ws / R <= RATED_OMEGA + 1e-9
            and block_power(b["cp"], ws) <= RATED_W]

    def best_at(lam):
        cand = [b for b in feas if abs(b["tsr"] - lam) < 1e-9]
        return min(cand, key=lambda b: b["pitch"]) if cand else None

    picks = [x for x in (best_at(8.0), best_at(7.0), best_at(6.0)) if x is not None]
    if not picks:
        return []
    base = picks[0]
    deeper = sorted((b for b in feas if abs(b["tsr"] - base["tsr"]) < 1e-9
                     and b["pitch"] > base["pitch"]), key=lambda b: b["pitch"])
    if deeper:
        picks.append(deeper[max(0, len(deeper) // 2)])
    seen, out = set(), []
    for b in picks:
        key = (b["tsr"], b["pitch"])
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return out[:n_points]


def feasible_patterns_v2(blocks: list[dict], ws: float, max_patterns: int) -> list[dict]:
    """v2 的控制模式选择：5 个模式按优先级，最多取前 3 个。"""
    index = {(round(b["tsr"], 3), round(float(b["pitch"]), 1)): b for b in blocks}
    ok = []
    for name, triple in V2_PATTERNS:
        entries, good = [], True
        for (beta, tsr) in triple:
            b = index.get((round(tsr, 3), round(float(beta), 1)))
            if b is None or tsr * ws / R > RATED_OMEGA + 1e-9 or block_power(b["cp"], ws) > RATED_W:
                good = False
                break
            entries.append(b)
        if good:
            ok.append({"name": name, "blocks": entries})
    ok.sort(key=lambda p: V2_PRIORITY.index(p["name"]))
    return ok[:max_patterns]


def base_wind_directions_v2(step=15.0):
    grid = set(np.round(np.arange(0.0, 360.0, step), 3).tolist())
    for extra in (85.0, 95.0, 265.0, 275.0):
        grid.add(extra)
    return np.array(sorted(grid))


def turbine_dict(beta, tsr, cp, ct, slot, yaml_tsr, round6):
    """构造涡轮机定义。

    yaml_tsr 是写进 yaml 的 TSR 标量，它只参与 GCH 的尾流旋转涡量项
    （Gamma ∝ 1/TSR），不参与功率查表。
    v1 用的是统一的多维表 yaml，其 TSR 固定为 8.0；
    v2 起改为逐机表，TSR 取该块的叶尖速比。这个差别会改变 Ueff，必须区分。

    round6：v1 的功率/推力是经 CSV 中转的（写文件时按 %.6f 取整），
    v2 起改为内存里直接传全精度数组。要逐字节复现 v1 必须同样取整。
    """
    axis = np.arange(WS_MIN_AXIS, WS_MAX_AXIS + 1e-9, WS_STEP_AXIS)
    area = math.pi * R**2
    power_kw = 0.5 * RHO * area * axis**3 * cp * ETA / 1000.0
    if round6:
        power_kw = np.array([float(f"{v:.6f}") for v in power_kw])
        ct = float(f"{ct:.6f}")
    return {
        "turbine_type": f"blk_tsr{int(round(tsr*10))}_pit{int(round(beta))}_t{slot}",
        "hub_height": HUB,
        "rotor_diameter": D,
        "TSR": float(yaml_tsr),
        "operation_model": "cosine-loss",
        "power_thrust_table": {
            "wind_speed": axis.tolist(),
            "power": power_kw.tolist(),
            "thrust_coefficient": [float(ct)] * len(axis),
            "ref_air_density": RHO,
            "ref_tilt": 5.0,
            "cosine_loss_exponent_tilt": COS_EXP,
            "cosine_loss_exponent_yaw": COS_EXP,
        },
    }


def disk_points_global(wd_deg, offsets):
    import generate_cases as gc
    return gc.disk_points_global(wd_deg, offsets)


def build_cases(version: str, blocks: list[dict]) -> list[dict]:
    cases = []
    wss = np.arange(5.0, 12.0 + 1e-9, 0.5)
    wds = np.arange(0.0, 360.0, 15.0) if version == "v1" else base_wind_directions_v2()
    tis = [0.06, 0.08, 0.10]
    for ws in wss:
        settings = (feasible_ops_v1(blocks, float(ws), 4) if version == "v1"
                    else feasible_patterns_v2(blocks, float(ws), 3))
        if not settings:
            continue
        for wd in wds:
            for ti in tis:
                for sname, yaws in YAW_V12:
                    for s in settings:
                        tri = [s] * 3 if version == "v1" else s["blocks"]
                        cases.append({
                            "ws": float(ws), "wd": float(wd), "ti": float(ti),
                            "yaws_deg": yaws,
                            "blocks": [(b["pitch"], b["tsr"], b["cp"], b["ct"]) for b in tri],
                        })
    return cases


def run(cases: list[dict], version: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import generate_cases as gc
    from floris import FlorisModel

    groups = {}
    for k, c in enumerate(cases):
        key = (c["wd"], tuple((round(b[1], 3), round(b[0], 1)) for b in c["blocks"]))
        groups.setdefault(key, []).append(k)

    n = len(cases)
    ueff = np.zeros((n, 3))
    offsets = gc.disk_offsets()
    t0 = time.time()
    for gi, ((wd, tri), idx) in enumerate(sorted(groups.items())):
        sub = [cases[k] for k in idx]
        turbs = [turbine_dict(beta, tsr, cp, ct, slot=i,
                              yaml_tsr=(8.0 if version == "v1" else tsr),
                              round6=(version == "v1"))
                 for i, (beta, tsr, cp, ct) in enumerate(sub[0]["blocks"])]
        cfg = gc.build_farm_config([t["TSR"] for t in turbs])
        cfg["farm"]["turbine_type"] = turbs
        f = FlorisModel(cfg)
        f.set(wind_speeds=np.array([c["ws"] for c in sub]),
              wind_directions=np.full(len(sub), wd),
              turbulence_intensities=np.array([c["ti"] for c in sub]),
              yaw_angles=np.array([c["yaws_deg"] for c in sub]))
        f.run()
        pts = disk_points_global(wd, offsets)
        xs = np.concatenate([p[0] for p in pts])
        ys = np.concatenate([p[1] for p in pts])
        zs = np.concatenate([p[2] for p in pts])
        u = f.sample_flow_at_points(xs, ys, zs)
        per = offsets.shape[0]
        ueff[idx] = np.column_stack(
            [np.cbrt(np.mean(u[:, i * per:(i + 1) * per] ** 3, axis=1)) for i in range(3)])
        if (gi + 1) % 60 == 0:
            log(f"  分组 {gi + 1}/{len(groups)}  已用 {time.time()-t0:.0f}s")

    cp = np.array([[b[2] for b in c["blocks"]] for c in cases])
    tsr = np.array([[b[1] for b in c["blocks"]] for c in cases])
    yaw = np.deg2rad(np.array([c["yaws_deg"] for c in cases]))
    area = math.pi * R**2
    P = 0.5 * RHO * area * ueff**3 * cp * ETA * np.cos(yaw) ** COS_EXP
    omega = tsr * ueff / R
    return P, ueff, omega


def write_csv(cases, P, ueff, omega, path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(INPUT_NAMES + OUTPUT_NAMES)]
    for k, c in enumerate(cases):
        th = np.deg2rad((270.0 - c["wd"]) % 360.0)
        yaw = np.deg2rad(np.array(c["yaws_deg"]))
        pit = np.deg2rad(np.array([b[0] for b in c["blocks"]]))
        lines.append(
            f"{c['ws']:.6f},{th:.10f},{c['ti']:.6f},"
            f"{yaw[0]:.8f},{pit[0]:.8f},{omega[k,0]:.8f},"
            f"{yaw[1]:.8f},{pit[1]:.8f},{omega[k,1]:.8f},"
            f"{yaw[2]:.8f},{pit[2]:.8f},{omega[k,2]:.8f},"
            f"{P[k,0]:.6f},{P[k,1]:.6f},{P[k,2]:.6f},"
            f"{ueff[k,0]:.6f},{ueff[k,1]:.6f},{ueff[k,2]:.6f}")
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", choices=("v1", "v2"))
    args = ap.parse_args()

    blocks = blocks_for(args.version)
    cases = build_cases(args.version, blocks)
    log(f"[{args.version}] 工况数 {len(cases)}（涉及 {len(blocks)} 个控制块）")
    P, ueff, omega = run(cases, args.version)
    payload = write_csv(cases, P, ueff, omega, OUT / f"cases_wind_{args.version}.csv")
    sha = hashlib.sha256(payload).hexdigest()
    exp = EXPECTED_SHA[args.version]
    log(f"  写出 {OUT / f'cases_wind_{args.version}.csv'}")
    log(f"  SHA256    = {sha}")
    log(f"  期望(前缀)= {exp}")
    log(f"  复现判定  = {'逐字节一致 ✓' if sha.startswith(exp) else '不一致 ✗'}")
    return 0 if sha.startswith(exp) else 1


if __name__ == "__main__":
    raise SystemExit(main())
