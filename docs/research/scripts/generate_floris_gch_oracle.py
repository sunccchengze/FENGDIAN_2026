# ================================================================
# FLORIS GCH oracle 生成器（P0-1 · L4 物理内核 V&V 数据源）
# ----------------------------------------------------------------
# 作用：用 FLORIS 4.6.6 `FlorisModel("defaults")`（即 GCH 默认配置，
#       与 docs/research/scripts/floris_probe.py 完全同源）对拍生成
#       本项目 TS 物理内核（twin/src/core/physics）的验证数据。
#
# 配置（default_inputs.yaml 原文，勿改）：
#   velocity_model=gauss  deflection_model=gauss
#   turbulence_model=crespo_hernandez  combination_model=sosfs
#   enable_secondary_steering=True  enable_yaw_added_recovery=True
#   enable_transverse_velocities=True
#   gauss 参数 alpha=0.58 beta=0.077 ka=0.38 kb=0.004
#   crespo_hernandez initial=0.1 constant=0.5 ai=0.8 downstream=-0.32
#   solver=turbine_grid(3×3 转子网格, ±D/4, cubic-mean)
#   风场 shear=0.12（轮毂高 90m 为参考）, veer=0, rho=1.225, TI=0.06
#
# 输出：
#   docs/research/oracle/floris_gch_oracle_v1.json   （第三方可复现存档）
#   twin/src/data/oracle/florisGchOracle.ts          （selftest 内嵌数据件）
#
# R42（2026-10-05）新增 tandem3 块：三机串列（= 3×3 中列，docs/13 决议 1×3 几何），
# 8 m/s 北来风 × {none / 统一偏航 13 档 / 上游扫 13 档 / 中游扫 13 档 / 逐机贪心}，
# 外加与 3×3 中列切片的交叉校验（纯北来风三列互不干扰，两者应逐机相等）。
#
# 复现：pip install floris==4.6.6 && python3 generate_floris_gch_oracle.py
# 注意：每工况的 `sec` 是生成机墙钟，重跑必然变化，整文件哈希不可比；
# 复现校验用同目录 check_oracle_physics.py 比对剔除 sec 后的物理哈希（AUD-17）。
# 红线：本脚本不拟合、不调参 —— 所有数字均为 FLORIS 原样输出。
# ================================================================
import json
import math
import os

import numpy as np

from floris import FlorisModel

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT_JSON = os.path.join(REPO, "docs", "research", "oracle", "floris_gch_oracle_v1.json")
OUT_TS = os.path.join(REPO, "twin", "src", "data", "oracle", "florisGchOracle.ts")

TI = 0.06
WS = 8.0

# ---- 场景 FARM（与 twin/src/scene/terrainUtil.ts FARM 逐位一致）----
# 场景系：+x=东, +z=南；FLORIS 系：x=东, y=北 → y = -z
ROWS_Z = [-1272, -640, -8]
COLS_X = [-732, -100, 532]
SCENE = []
_k = 0
for r in range(3):
    for c in range(3):
        jx = (((_k * 53) % 5) - 2) * 10
        jz = (((_k * 37) % 5) - 2) * 8
        SCENE.append((COLS_X[c] + jx, ROWS_Z[r] + jz))  # (x_east, z_south)
        _k += 1
FLORIS_LAY = [(p[0], -p[1]) for p in SCENE]  # (x_east, y_north)
CLEAN_LAY = [(COLS_X[c], -ROWS_Z[r]) for r in range(3) for c in range(3)]


def run_fm(lay, wd, ws, yaw):
    fm = FlorisModel("defaults")
    fm.set(
        layout_x=[p[0] for p in lay],
        layout_y=[p[1] for p in lay],
        wind_speeds=[ws],
        wind_directions=[wd],
        turbulence_intensities=[TI],
    )
    if yaw is not None:
        fm.set_operation(yaw_angles=np.array([[float(v) for v in yaw]]))
    fm.run()
    core = fm.core
    u = np.asarray(core.flow_field.u)[0]  # (n_turb, 3, 3)
    tis = np.asarray(core.flow_field.turbulence_intensity_field)[0]  # (n_turb,) 已按转子网格平均
    u_eff = np.cbrt(np.mean(u ** 3, axis=(1, 2)))  # (n_turb,)
    powers = np.asarray(fm.get_turbine_powers())[0] / 1e3  # kW
    try:
        cts = np.asarray(fm.get_turbine_thrust_coefficients())[0]
    except Exception:
        cts = np.full(len(u_eff), math.nan)
    return powers, u_eff, cts, tis


def run_fm6(lay, wd, ws, yaw):
    """R44 演示用（C3 参考值/C4 耗时对照）：run_fm 口径 + 轮毂高度平均风速
    (fm.turbine_average_velocities, m/s, 布局序) + fm.run() 墙钟耗时 (s)。
    独立实现，不改 run_fm，保证旧区块逐位一致。红线同前：不拟合、不调参。"""
    import time
    fm = FlorisModel("defaults")
    fm.set(
        layout_x=[p[0] for p in lay],
        layout_y=[p[1] for p in lay],
        wind_speeds=[ws],
        wind_directions=[wd],
        turbulence_intensities=[TI],
    )
    if yaw is not None:
        fm.set_operation(yaw_angles=np.array([[float(v) for v in yaw]]))
    t0 = time.perf_counter()
    fm.run()
    sec = time.perf_counter() - t0
    p = np.asarray(fm.get_turbine_powers())[0] / 1e3  # kW
    vel = np.asarray(fm.turbine_average_velocities)[0]  # m/s, 布局序
    u = np.asarray(fm.core.flow_field.u)[0]  # (n_turb, 3, 3)
    uEff = np.cbrt(np.mean(u ** 3, axis=(1, 2)))  # (n_turb,) 与 run_fm 同口径
    return p, [float(v) for v in uEff], [float(v) for v in vel], float(sec)


def cross_plane_u(yaw_up, x_down, ys, zs):
    """双机 [0,0]→[632,0]（上风向偏航 yaw_up，下风向 0），下游 x_down 处 y-z 网格的 u。
    与 floris3dData.mjs 数据件同工况（涡轮在 x=0 / x=632，wd=270 即流向 +x）。
    注：资产实测坐标原点在上风向机（x=0 处即其尾流起点），无 200m 偏移。"""
    fm = FlorisModel("defaults")
    fm.set(
        layout_x=[0.0, 632.0],
        layout_y=[0.0, 0.0],
        wind_speeds=[WS],
        wind_directions=[270.0],
        turbulence_intensities=[TI],
    )
    fm.set_operation(yaw_angles=np.array([[float(yaw_up), 0.0]]))
    cs = fm.calculate_cross_plane(
        downstream_dist=x_down, y_resolution=len(ys), z_resolution=len(zs),
        y_bounds=[min(ys), max(ys)], z_bounds=[min(zs), max(zs)],
    )
    df = cs.df
    u = df.u.values
    return u.tolist()


def centroid_deflection(yaw_up, x_down):
    """复刻 floris_probe.py 口径（涡轮在原点）：逐高度局地自由流归一 → 亏损质心。"""
    fm = FlorisModel("defaults")
    fm.set(
        layout_x=[0.0],
        layout_y=[0.0],
        wind_speeds=[WS],
        wind_directions=[270.0],
        turbulence_intensities=[TI],
    )
    fm.set_operation(yaw_angles=np.array([[float(yaw_up)]]))
    cs = fm.calculate_cross_plane(downstream_dist=x_down, y_resolution=60, z_resolution=45)
    df = cs.df
    y, z, u = df.x1.values, df.x2.values, df.u.values
    dfc = np.zeros_like(u)
    for zz in np.unique(z):
        m = z == zz
        u0 = u[m].max()
        dfc[m] = np.clip((u0 - u[m]) / max(u0, 1e-6), 0, 1)
    yc = (y * dfc).sum() / dfc.sum()
    return float(yc)


def main():
    meta = {
        "generator": "generate_floris_gch_oracle.py",
        "floris_version": __import__("floris").__version__,
        "config": "FlorisModel('defaults') == GCH",
        "model_strings": {
            "velocity_model": "gauss",
            "deflection_model": "gauss",
            "turbulence_model": "crespo_hernandez",
            "combination_model": "sosfs",
        },
        "flags": {
            "enable_secondary_steering": True,
            "enable_yaw_added_recovery": True,
            "enable_transverse_velocities": True,
        },
        "params": {
            "gauss": {"alpha": 0.58, "beta": 0.077, "ka": 0.38, "kb": 0.004},
            "crespo_hernandez": {"initial": 0.1, "constant": 0.5, "ai": 0.8, "downstream": -0.32},
            "shear": 0.12,
            "veer": 0.0,
            "rho": 1.225,
            "TI": TI,
            "grid": "turbine_grid 3x3 (±D/4), cubic-mean",
        },
        "scene_layout_floris_xy": FLORIS_LAY,
        "scene_coord_note": "FLORIS(x=东,y=北)；场景系 +x=东,+z=南 → y=-z",
    }

    out = {"meta": meta}

    # ---- 1) 机组表（v4.6.6 nrel_5MW.yaml 原样 54 点）----
    import yaml as _yaml
    import floris as _fl

    _yaml_path = os.path.join(os.path.dirname(_fl.__file__), "turbine_library", "nrel_5MW.yaml")
    with open(_yaml_path) as f:
        _y = _yaml.safe_load(f)
    _pt = _y["power_thrust_table"]
    out["turbine"] = {
        "D": _y["rotor_diameter"],
        "HH": _y["hub_height"],
        "TSR": _y["TSR"],
        "ref_rho": _pt["ref_air_density"],
        "ref_tilt": _pt["ref_tilt"],
        "exp_yaw": _pt["cosine_loss_exponent_yaw"],
        "exp_tilt": _pt["cosine_loss_exponent_tilt"],
        "table": [
            {"u": float(u), "kW": float(p), "Ct": float(ct)}
            for u, p, ct in zip(_pt["wind_speed"], _pt["power"], _pt["thrust_coefficient"])
        ],
    }

    # ---- 2) 功率曲线（单机, yaw=0）----
    curve = []
    for i in range(5, 52):
        u = i / 2.0
        p, ue, ct, _ = run_fm([(0.0, 0.0)], 270.0, u, None)
        curve.append({"u": u, "kW": float(p[0]), "uEff": float(ue[0]), "Ct": float(ct[0])})
    out["powerCurve"] = curve

    # ---- 3) 双机 5D（对齐 florisData.ts FLORIS_PAIR_8MS）----
    pair = []
    for y in range(-30, 31, 5):
        p, ue, ct, ti = run_fm([(0.0, 0.0), (632.0, 0.0)], 270.0, WS, [y, 0.0])
        pair.append({
            "yaw": y,
            "pUp_kW": float(p[0]), "pDn_kW": float(p[1]),
            "uEffUp": float(ue[0]), "uEffDn": float(ue[1]),
            "ctUp": float(ct[0]), "ctDn": float(ct[1]),
            "tiDn": float(ti[1]),
        })
    out["pair8ms"] = pair

    # ---- 4) 九机阵列（规范几何 3×3@632m，北来风 wd=0）----
    # 注：场景 FARM 抖动已在本提交移除（terrainUtil.ts），场景几何 == 规范 FLORIS 布局。
    D = out["turbine"]["D"]
    arr = {}
    p, ue, ct, ti = run_fm(CLEAN_LAY, 0.0, WS, [0.0] * 9)
    arr["none"] = {"total_kW": float(p.sum()), "p_kW": [float(v) for v in p],
                   "uEff": [float(v) for v in ue], "ti": [float(v) for v in ti]}
    arr["unified_total"] = []
    for y in range(-30, 31, 5):
        p, ue, ct, ti = run_fm(CLEAN_LAY, 0.0, WS, [float(y)] * 9)
        arr["unified_total"].append({"yaw": y, "total_kW": float(p.sum())})
    arr["unified_detail"] = {}
    for y in (-30, 0, 30):
        p, ue, ct, ti = run_fm(CLEAN_LAY, 0.0, WS, [float(y)] * 9)
        arr["unified_detail"][str(y)] = {
            "total_kW": float(p.sum()), "p_kW": [float(v) for v in p],
            "uEff": [float(v) for v in ue],
        }
    arr["row0_scan"] = []
    for a in range(-30, 31, 5):
        yaw = [float(a)] * 3 + [0.0] * 6
        p, ue, ct, ti = run_fm(CLEAN_LAY, 0.0, WS, yaw)
        arr["row0_scan"].append({"yaw": a, "total_kW": float(p.sum())})
    cfgs = {"row_30_20_0": [30] * 3 + [20] * 3 + [0] * 3,
            "row_-30_-20_0": [-30] * 3 + [-20] * 3 + [0] * 3,
            "row_30_-20_0": [30] * 3 + [-20] * 3 + [0] * 3,
            "row_-30_20_0": [-30] * 3 + [20] * 3 + [0] * 3,
            "mixed1": [25, 30, 20, 10, 15, 0, -5, 0, 5]}
    arr["configs"] = {}
    for name, yaw in cfgs.items():
        p, ue, ct, ti = run_fm(CLEAN_LAY, 0.0, WS, yaw)
        arr["configs"][name] = {"yaw": yaw, "total_kW": float(p.sum()),
                                "p_kW": [float(v) for v in p]}
    # 与 round18 记录值（8108.08 / 9060.03）的同源对照
    p0, *_ = run_fm(CLEAN_LAY, 0.0, WS, [0.0] * 9)
    p30, *_ = run_fm(CLEAN_LAY, 0.0, WS, [30.0] * 9)
    arr["round18_ref"] = {"none_kW": float(p0.sum()), "unified+30_kW": float(p30.sum())}
    out["array"] = arr

    # ---- 4b) 三机串列 tandem3（R42 · 1×3 真值组；= 3×3 中列，docs/13 §4.4）----
    # 场景系 (-100, z) 北→南: T01 z=-1272 / T02 z=-640 / T03 z=-8
    # FLORIS 系 y=-z: (x=-100, y=1272/640/8)；wd=0 北来风 → 上游=最大 y（T01，index 0）
    TAND3 = [(-100.0, 1272.0), (-100.0, 640.0), (-100.0, 8.0)]
    td = {}
    p, ue, ct, ti = run_fm(TAND3, 0.0, WS, [0.0, 0.0, 0.0])
    p6, uEff0, vel0, sec0 = run_fm6(TAND3, 0.0, WS, [0.0, 0.0, 0.0])
    td["none"] = {"total_kW": float(p.sum()), "p_kW": [float(v) for v in p],
                  "uEff": [float(v) for v in ue], "ti": [float(v) for v in ti],
                  "vel": vel0, "sec": sec0}
    td["unified"] = []
    for y in range(-30, 31, 5):
        p, uEff, vel, sec = run_fm6(TAND3, 0.0, WS, [float(y)] * 3)
        td["unified"].append({"yaw": y, "total_kW": float(p.sum()),
                               "p_kW": [float(v) for v in p], "uEff": [float(v) for v in uEff],
                               "vel": vel, "sec": sec})
    td["upstreamScan"] = []
    for a in range(-30, 31, 5):
        p, uEff, vel, sec = run_fm6(TAND3, 0.0, WS, [float(a), 0.0, 0.0])
        td["upstreamScan"].append({"yaw": a, "total_kW": float(p.sum()),
                                    "p_kW": [float(v) for v in p], "uEff": [float(v) for v in uEff],
                                    "vel": vel, "sec": sec})
    td["midstreamScan"] = []
    for b in range(-30, 31, 5):
        p, uEff, vel, sec = run_fm6(TAND3, 0.0, WS, [0.0, float(b), 0.0])
        td["midstreamScan"].append({"yaw": b, "total_kW": float(p.sum()),
                                     "p_kW": [float(v) for v in p], "uEff": [float(v) for v in uEff],
                                     "vel": vel, "sec": sec})
    # 逐机贪心（与 twin farmSim.optimizeYaw 同逻辑：上游→下游逐行推进，
    # 每步在 CAND 上取全场总功率最大；此处作为 TS 贪心的真值参照）
    CAND = [-30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30]
    def tsum(yaw3):
        pp, *_ = run_fm(TAND3, 0.0, WS, [float(v) for v in yaw3])
        return float(pp.sum())
    greedy = {"path": []}
    base = tsum([0, 0, 0])
    greedy["none_kW"] = base
    best1 = max(CAND, key=lambda a: tsum([a, 0, 0]))
    greedy["path"].append({"stage": "upstream", "yaw": best1, "total_kW": tsum([best1, 0, 0])})
    best2 = max(CAND, key=lambda b: tsum([best1, b, 0]))
    greedy["path"].append({"stage": "midstream", "yaw": best2, "total_kW": tsum([best1, best2, 0])})
    best3 = max(CAND, key=lambda c: tsum([best1, best2, c]))
    greedy["path"].append({"stage": "downstream", "yaw": best3, "total_kW": tsum([best1, best2, best3])})
    greedy["yaw"] = [best1, best2, best3]
    greedy["total_kW"] = tsum([best1, best2, best3])
    greedy["gain_pct"] = (greedy["total_kW"] / base - 1) * 100
    # R44：逐阶段 + 终态补 pKw/uEff/vel/sec（tsum 搜索路径本身不记，仅定稿复算）
    for entry, yaw3 in ((greedy["path"][0], [best1, 0.0, 0.0]),
                        (greedy["path"][1], [best1, best2, 0.0]),
                        (greedy["path"][2], [best1, best2, best3])):
        p, uEff, vel, sec = run_fm6(TAND3, 0.0, WS, yaw3)
        entry["p_kW"] = [float(v) for v in p]
        entry["uEff"] = [float(v) for v in uEff]
        entry["vel"] = vel
        entry["sec"] = sec
    p, uEff, greedy["vel"], greedy["sec"] = run_fm6(TAND3, 0.0, WS, [best1, best2, best3])
    greedy["p_kW"] = [float(v) for v in p]
    greedy["uEff"] = [float(v) for v in uEff]
    td["greedy"] = greedy
    td["velNote"] = ("vel = FLORIS turbine_average_velocities（轮毂高度平均风速, m/s, 布局序 index0=上游 T01）；"
                     "uEff = 转子网格立方平均风速（与 run_fm 同口径）；"
                     "sec = fm.run() 墙钟 (s, 本机实测, 仅稳态求解, 不含模型构建)")
    # 交叉校验：纯北来风下 3×3 各列互不干扰 → 1×3 逐机功率 == 3×3 中列切片
    # 3×3 row-major: 中列 = 索引 1/4/7（T02 北 / T05 中 / T08 南，与 TAND3 同序）
    def midcol(total_p):
        return [total_p[1], total_p[4], total_p[7]]
    p3_none, *_ = run_fm(CLEAN_LAY, 0.0, WS, [0.0] * 9)
    p3_30, *_ = run_fm(CLEAN_LAY, 0.0, WS, [30.0] * 9)
    td["crossCheck3x3"] = {
        "none": {
            "pKw1x3": td["none"]["p_kW"],
            "pKw3x3MidCol": [float(v) for v in midcol(p3_none)],
            "maxDiffKw": float(max(abs(a - b) for a, b in zip(td["none"]["p_kW"], midcol(p3_none)))),
        },
        "unified+30": {
            "pKw1x3": None,  # 下面补
            "pKw3x3MidCol": [float(v) for v in midcol(p3_30)],
            "maxDiffKw": None,
        },
    }
    p1_30, *_ = run_fm(TAND3, 0.0, WS, [30.0, 30.0, 30.0])
    cc = td["crossCheck3x3"]["unified+30"]
    cc["pKw1x3"] = [float(v) for v in p1_30]
    cc["maxDiffKw"] = float(max(abs(a - b) for a, b in zip(p1_30, midcol(p3_30))))
    td["layout"] = TAND3
    td["coordNote"] = "FLORIS(x=东,y=北)；TAND3 = 3×3 中列 (x=-100, y=1272/640/8)，index0=上游"
    out["tandem3"] = td
    print("tandem3 none:", td["none"]["total_kW"], "kW; 交叉校验 maxDiff:",
          td["crossCheck3x3"]["none"]["maxDiffKw"], "/", cc["maxDiffKw"], "kW")

    # ---- 5) 尾流横偏质心（对齐 round17 §3.2 口径，涡轮在原点）----
    defl = []
    for y in (10, 20, 30):
        for dD in (3, 5, 8):
            c = centroid_deflection(y, dD * D)
            defl.append({"yaw": y, "xD": dD, "centroid_y_m": round(c, 3)})
    out["deflection"] = defl

    # ---- 6) 下游横截面 u（双机, 涡轮在原点, 节点=floris3dData.mjs 资产网格）----
    # 资产系 x 以"涡轮上游 200m"为 0（T07 在资产 x=200, T04 在 x=832）
    # → floris 下游距离 = 资产节点 x - 200
    import re as _re

    with open(os.path.join(REPO, "twin", "src", "data", "floris3dData.mjs")) as f:
        _mjs = f.read()
    _m = _re.search(r"export default (\{.*\})\s*$", _mjs, _re.S)
    _asset = json.loads(_m.group(1))
    _ay = [round(v, 3) for v in _asset["+00"]["y"]]
    _az = [round(v, 3) for v in _asset["+00"]["z"]]
    _ax_nodes = [round(v, 3) for v in _asset["+00"]["x"]]
    # 资产系 x 原点在上风向机（x=0），downstream_dist 即节点坐标本身。
    # 走廊内 6 个节点（463~813 m：跨上游机尾流 → 下风向机 → 其下游）
    _pick = [19, 21, 23, 25, 27, 29]
    _x_fl = [round(_ax_nodes[i], 3) for i in _pick]
    secs = {
        "frame_note": ("资产系 x 原点=上风向机(x=0)，下风向机 x=632，流向 +x(wd=270)。"
                       "另：florisData.ts sampleWorldU 的 fx=200+(z+640) 映射与资产帧不符"
                       "（资产实测 x=0 即尾流起点），P0-3 将以 TS 内核现场采样取代 mjs 映射。"),
        "xsFloris": _x_fl, "ys": _ay, "zs": _az, "u": {}, "uOld": {},
    }
    for y in (-30, -15, 0, 15, 30):
        key = "%+03d" % y
        vals = {}
        for xf in _x_fl:
            vals[str(xf)] = [round(v, 4) for v in cross_plane_u(y, xf, _ay, _az)]
        secs["u"][key] = vals
        old = []
        for i in _pick:
            for iz in range(len(_az)):
                for iy in range(len(_ay)):
                    v = _asset[key]["u"][iz][iy][i]
                    old.append(round(v, 4) if v is not None else None)
        secs["uOld"][key] = old
    out["crossSection"] = secs

    # ---- 写 JSON ----
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", OUT_JSON, os.path.getsize(OUT_JSON), "bytes")

    # ---- 写 TS 内嵌件 ----
    os.makedirs(os.path.dirname(OUT_TS), exist_ok=True)
    ts = []
    ts.append("/* ================================================================")
    ts.append(" * florisGchOracle.ts — FLORIS 4.6.6 GCH 实算 oracle（生成件，勿手改）")
    ts.append(" * ----------------------------------------------------------------")
    ts.append(" * 生成：docs/research/scripts/generate_floris_gch_oracle.py")
    ts.append(" *       （FlorisModel('defaults')，与 floris_probe.py 同源同参）")
    ts.append(" * 存档：docs/research/oracle/floris_gch_oracle_v1.json（逐位一致）")
    ts.append(" * 用途：core/physics 的 V&V oracle —— 本仓 TS 内核 vs FLORIS 实算。")
    ts.append(" * ================================================================ */")
    ts.append("")
    ts.append("export interface TurbineTablePoint { u: number; kW: number; Ct: number }")
    ts.append("export interface Oracle {")
    ts.append("  turbine: {")
    ts.append("    D: number; HH: number; TSR: number; refRho: number; refTilt: number")
    ts.append("    expYaw: number; expTilt: number; table: TurbineTablePoint[]")
    ts.append("  }")
    ts.append("  powerCurve: { u: number; kW: number; uEff: number; Ct: number }[]")
    ts.append("  pair8ms: { yaw: number; pUpKw: number; pDnKw: number; uEffUp: number; uEffDn: number; ctUp: number; ctDn: number; tiDn: number }[]")
    ts.append("  array: {")
    ts.append("    none: { totalKw: number; pKw: number[]; uEff: number[]; ti: number[] }")
    ts.append("    unifiedTotal: { yaw: number; totalKw: number }[]")
    ts.append("    unifiedDetail: Record<string, { totalKw: number; pKw: number[]; uEff: number[] }>")
    ts.append("    row0Scan: { yaw: number; totalKw: number }[]")
    ts.append("    configs: Record<string, { yaw: number[]; totalKw: number; pKw: number[] }>")
    ts.append("    round18Ref: { noneKw: number; unified30Kw: number }")
    ts.append("  }")
    ts.append("  tandem3: {")
    ts.append("    layout: [number, number][]")
    ts.append("    coordNote: string")
    ts.append("    none: { totalKw: number; pKw: number[]; uEff: number[]; ti: number[]; vel: number[]; sec: number }")
    ts.append("    unified: { yaw: number; totalKw: number; pKw: number[]; uEff: number[]; vel: number[]; sec: number }[]")
    ts.append("    upstreamScan: { yaw: number; totalKw: number; pKw: number[]; uEff: number[]; vel: number[]; sec: number }[]")
    ts.append("    midstreamScan: { yaw: number; totalKw: number; pKw: number[]; uEff: number[]; vel: number[]; sec: number }[]")
    ts.append("    greedy: { path: { stage: string; yaw: number; totalKw: number; pKw: number[]; uEff: number[]; vel: number[]; sec: number }[]; yaw: number[]; totalKw: number; noneKw: number; gainPct: number; pKw: number[]; uEff: number[]; vel: number[]; sec: number }")
    ts.append("    velNote: string")
    ts.append("    crossCheck3x3: { none: { pKw1x3: number[]; pKw3x3MidCol: number[]; maxDiffKw: number }; unifiedPlus30: { pKw1x3: number[]; pKw3x3MidCol: number[]; maxDiffKw: number } }")
    ts.append("  }")
    ts.append("  deflection: { yaw: number; xD: number; centroidYm: number }[]")
    ts.append("  crossSection: {")
    ts.append("    frameNote: string")
    ts.append("    xsFloris: number[]")
    ts.append("    ys: number[]")
    ts.append("    zs: number[]")
    ts.append("    /** 4.6.6 实算 u，case(+00..+30) → florisX(m) → u 展平(iz 外层, iy 内层, len=zs*ys) */")
    ts.append("    u: Record<string, Record<string, number[]>>")
    ts.append("    /** 旧资产 floris3dData.mjs 同节点 u（展平 iz 外层 iy 内层），旧版 FLORIS 值；null=资产空洞 */")
    ts.append("    uOld: Record<string, (number | null)[]>")
    ts.append("  }")
    ts.append("}")
    ts.append("")

    def tsv(key, obj, renames=None):
        renames = renames or {}

        def conv(o):
            if isinstance(o, dict):
                return {renames.get(k, k): conv(v) for k, v in o.items()}
            if isinstance(o, list):
                return [conv(v) for v in o]
            return o

        js = json.dumps(conv(obj), ensure_ascii=False)
        return js

    ts.append("export const ORACLE: Oracle = " + tsv(None, {
        "turbine": {
            "D": out["turbine"]["D"], "HH": out["turbine"]["HH"], "TSR": out["turbine"]["TSR"],
            "refRho": out["turbine"]["ref_rho"], "refTilt": out["turbine"]["ref_tilt"],
            "expYaw": out["turbine"]["exp_yaw"], "expTilt": out["turbine"]["exp_tilt"],
            "table": out["turbine"]["table"],
        },
        "powerCurve": [
            {"u": c["u"], "kW": c["kW"], "uEff": c["uEff"], "Ct": c["Ct"]} for c in out["powerCurve"]
        ],
        "pair8ms": [
            {"yaw": c["yaw"], "pUpKw": c["pUp_kW"], "pDnKw": c["pDn_kW"],
             "uEffUp": c["uEffUp"], "uEffDn": c["uEffDn"],
             "ctUp": c["ctUp"], "ctDn": c["ctDn"], "tiDn": c["tiDn"]} for c in out["pair8ms"]
        ],
        "array": {
            "none": {"totalKw": out["array"]["none"]["total_kW"], "pKw": out["array"]["none"]["p_kW"],
                     "uEff": out["array"]["none"]["uEff"], "ti": out["array"]["none"]["ti"]},
            "unifiedTotal": [
                {"yaw": c["yaw"], "totalKw": c["total_kW"]} for c in out["array"]["unified_total"]
            ],
            "unifiedDetail": {
                k: {"totalKw": v["total_kW"], "pKw": v["p_kW"], "uEff": v["uEff"]}
                for k, v in out["array"]["unified_detail"].items()
            },
            "row0Scan": [
                {"yaw": c["yaw"], "totalKw": c["total_kW"]} for c in out["array"]["row0_scan"]
            ],
            "configs": {
                k: {"yaw": v["yaw"], "totalKw": v["total_kW"], "pKw": v["p_kW"]}
                for k, v in out["array"]["configs"].items()
            },
            "round18Ref": {"noneKw": out["array"]["round18_ref"]["none_kW"],
                           "unified30Kw": out["array"]["round18_ref"]["unified+30_kW"]},
        },
        "tandem3": {
            "layout": out["tandem3"]["layout"],
            "coordNote": out["tandem3"]["coordNote"],
            "none": {"totalKw": out["tandem3"]["none"]["total_kW"], "pKw": out["tandem3"]["none"]["p_kW"],
                     "uEff": out["tandem3"]["none"]["uEff"], "ti": out["tandem3"]["none"]["ti"],
                     "vel": out["tandem3"]["none"]["vel"], "sec": out["tandem3"]["none"]["sec"]},
            "unified": [{"yaw": c["yaw"], "totalKw": c["total_kW"], "pKw": c["p_kW"], "uEff": c["uEff"], "vel": c["vel"], "sec": c["sec"]}
                        for c in out["tandem3"]["unified"]],
            "upstreamScan": [{"yaw": c["yaw"], "totalKw": c["total_kW"], "pKw": c["p_kW"], "uEff": c["uEff"], "vel": c["vel"], "sec": c["sec"]}
                             for c in out["tandem3"]["upstreamScan"]],
            "midstreamScan": [{"yaw": c["yaw"], "totalKw": c["total_kW"], "pKw": c["p_kW"], "uEff": c["uEff"], "vel": c["vel"], "sec": c["sec"]}
                              for c in out["tandem3"]["midstreamScan"]],
            "greedy": {
                "path": [{"stage": s["stage"], "yaw": s["yaw"], "totalKw": s["total_kW"], "pKw": s["p_kW"], "uEff": s["uEff"], "vel": s["vel"], "sec": s["sec"]}
                         for s in out["tandem3"]["greedy"]["path"]],
                "yaw": out["tandem3"]["greedy"]["yaw"],
                "totalKw": out["tandem3"]["greedy"]["total_kW"],
                "noneKw": out["tandem3"]["greedy"]["none_kW"],
                "gainPct": out["tandem3"]["greedy"]["gain_pct"],
                "pKw": out["tandem3"]["greedy"]["p_kW"],
                "uEff": out["tandem3"]["greedy"]["uEff"],
                "vel": out["tandem3"]["greedy"]["vel"],
                "sec": out["tandem3"]["greedy"]["sec"],
            },
            "velNote": out["tandem3"]["velNote"],
            "crossCheck3x3": {
                "none": out["tandem3"]["crossCheck3x3"]["none"],
                "unifiedPlus30": {
                    "pKw1x3": out["tandem3"]["crossCheck3x3"]["unified+30"]["pKw1x3"],
                    "pKw3x3MidCol": out["tandem3"]["crossCheck3x3"]["unified+30"]["pKw3x3MidCol"],
                    "maxDiffKw": out["tandem3"]["crossCheck3x3"]["unified+30"]["maxDiffKw"],
                },
            },
        },
        "deflection": [
            {"yaw": d["yaw"], "xD": d["xD"], "centroidYm": d["centroid_y_m"]} for d in out["deflection"]
        ],
        "crossSection": {
            "frameNote": out["crossSection"]["frame_note"],
            "xsFloris": out["crossSection"]["xsFloris"],
            "ys": out["crossSection"]["ys"],
            "zs": out["crossSection"]["zs"],
            "u": {
                k: {str(xf): rows for xf, rows in u_per_x.items()}
                for k, u_per_x in out["crossSection"]["u"].items()
            },
            "uOld": out["crossSection"]["uOld"],
        },
    }) + " as const\n")
    with open(OUT_TS, "w") as f:
        f.write("\n".join(ts))
    print("wrote", OUT_TS, os.path.getsize(OUT_TS), "bytes")


if __name__ == "__main__":
    main()
