#!/usr/bin/env python3
"""契约自检：在替换真实数据后运行，校验 site/assets/data*.js 的结构与一致性。

用法：
    python3 site/check_contract.py

纯标准库，无需 numpy/pandas。校验内容：
  - data.js: multi 网格形状、功率非负、ptot==p1+p2、gain 与公式一致；
             single/array/opt/array_opt 字段齐全且数值合理。
  - data_3d.js: fields_2d/fields_3d 的坐标与速度场形状一致、速度非负；
                heatmap 网格形状与增益范围合理。

退出码 0 表示全部通过，非 0 表示有错误（适合接入 CI / 部署前检查）。
"""
import csv
import json
import os
import re
import sys

SITE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SITE)
ASSETS = os.path.join(SITE, "assets")
ERRORS = []
WARNINGS = []


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def load_window_js(fname, varname):
    """读取 `window.VAR = {...};` 形式的 JS，返回解析后的对象。"""
    path = os.path.join(ASSETS, fname)
    if not os.path.exists(path):
        err(f"缺少文件: {fname}")
        return None
    text = open(path, encoding="utf-8").read()
    m = re.search(r"window\." + varname + r"\s*=\s*", text)
    if not m:
        err(f"{fname} 中未找到 window.{varname}")
        return None
    start = m.end()
    # 找到对应的顶层分号（用括号配平，避免对象内分号干扰）
    depth = 0
    in_str = None
    i = start
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        else:
            if c in "\"'":
                in_str = c
            elif c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
            elif c == ";" and depth == 0:
                break
        i += 1
    blob = text[start:i]
    try:
        return json.loads(blob)
    except json.JSONDecodeError as e:
        err(f"{fname} 不是合法 JSON: {e}")
        return None


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check_multi(d):
    m = d.get("multi")
    if not m:
        err("data.multi 缺失")
        return
    us, ys = m.get("wind_speeds"), m.get("yaw_angles")
    if not (us and ys):
        err("data.multi.wind_speeds/yaw_angles 缺失")
        return
    nu, ny = len(us), len(ys)
    for key in ("p1", "p2", "ptot", "gain"):
        mat = m.get(key)
        if not isinstance(mat, list) or len(mat) != nu:
            err(f"multi.{key} 形状应为 {nu}x{ny}")
            continue
        for i, row in enumerate(mat):
            if not isinstance(row, list) or len(row) != ny:
                err(f"multi.{key}[{i}] 长度应为 {ny}")
                continue
            for j, v in enumerate(row):
                if not is_num(v):
                    err(f"multi.{key}[{i}][{j}] 非数值: {v!r}")
    # 数值一致性
    if all(k in m for k in ("p1", "p2", "ptot")):
        for i in range(nu):
            for j in range(ny):
                p1, p2, ptot = m["p1"][i][j], m["p2"][i][j], m["ptot"][i][j]
                if is_num(p1) and is_num(p2) and is_num(ptot):
                    if min(p1, p2, ptot) < 0:
                        err(f"功率出现负值 @ U={us[i]},yaw={ys[j]}: p1={p1},p2={p2},ptot={ptot}")
                    if abs((p1 + p2) - ptot) > max(1.0, 0.01 * ptot):
                        warn(f"ptot≠p1+p2 @ U={us[i]},yaw={ys[j]}: {ptot} vs {p1+p2}")
    if "gain" in m and "ptot" in m:
        for i in range(nu):
            j0 = ys.index(0) if 0 in ys else None
            if j0 is None:
                continue
            base = m["ptot"][i][j0]
            if base > 0:
                for j in range(ny):
                    expect = round((m["ptot"][i][j] - base) / base * 100, 3)
                    got = m["gain"][i][j]
                    if abs(expect - got) > 0.6:  # 容差 0.6 个百分点
                        warn(f"gain 不一致 @ U={us[i]},yaw={ys[j]}: 文件 {got}% vs 公式 {expect}%")


def check_scalars(d):
    s = d.get("single")
    if s:
        n = len(s.get("yaw_angles", []))
        for k in ("p1", "p2", "ptot"):
            if not isinstance(s.get(k), list) or len(s[k]) != n:
                err(f"single.{k} 长度应为 {n}")
    a = d.get("array")
    if a:
        n = len(a.get("yaw_upstream", []))
        if not isinstance(a.get("powers"), list) or len(a["powers"]) != n:
            err("array.powers 行数与 yaw_upstream 不一致")
        else:
            for i, row in enumerate(a["powers"]):
                if len(row) != 9:
                    err(f"array.powers[{i}] 应有 9 台风机功率")
    opt = d.get("opt")
    if opt:
        for k in ("wind_speed", "recommended_yaw", "power_before", "power_after", "power_gain_pct"):
            if k not in opt:
                err(f"opt 缺字段 {k}")
    ao = d.get("array_opt")
    if ao:
        for k in ("power_none", "power_unified", "power_row2_30", "power_independent", "greedy_yaws",
                  "turbine_powers_none", "turbine_powers_unified", "turbine_powers_row2_30", "turbine_powers_independent"):
            if k not in ao:
                err(f"array_opt 缺字段 {k}")
        if "greedy_yaws" in ao and len(ao["greedy_yaws"]) != 9:
            err("array_opt.greedy_yaws 应为 9 个偏航角")
        for pk in ("turbine_powers_none", "turbine_powers_unified", "turbine_powers_row2_30", "turbine_powers_independent"):
            arr = ao.get(pk)
            if isinstance(arr, list):
                if len(arr) != 9:
                    err(f"array_opt.{pk} 应为 9 台风机功率")
                elif any((not is_num(v)) or v < 0 for v in arr):
                    err(f"array_opt.{pk} 存在非法功率: {arr!r}")


def check_3d(d3):
    if not d3:
        return
    for label, group in (("fields_2d", d3.get("fields_2d")), ("fields_3d", d3.get("fields_3d"))):
        if not group:
            warn(f"{label} 为空")
            continue
        for key, fd in group.items():
            x, y = fd.get("x"), fd.get("y")
            u = fd.get("u")
            if not (x and y and u):
                err(f"{label}[{key}] 缺 x/y/u")
                continue
            if label == "fields_2d":
                if len(u) != len(y) or any((not isinstance(row, list)) or len(row) != len(x) for row in u):
                    err(f"{label}[{key}] u 形状应为 (len(y)={len(y)}, len(x)={len(x)})")
            else:
                z = fd.get("z")
                if not z:
                    err(f"{label}[{key}] 缺 z")
                else:
                    bad = (len(u) != len(z) or
                           any((not isinstance(row, list)) or len(row) != len(y) for row in u) or
                           any((not isinstance(cell, list)) or len(cell) != len(x)
                               for row in u for cell in row))
                    if bad:
                        err(f"{label}[{key}] u 形状应为 (len(z)={len(z)}, len(y)={len(y)}, len(x)={len(x)})")
            # 速度非负且物理上界合理（NREL 5MW 切入~额定区间，留宽松上界）
            flat = []
            def collect(node):
                if isinstance(node, list):
                    for q in node:
                        collect(q)
                else:
                    flat.append(node)
            collect(u)
            if any(not is_num(v) for v in flat):
                err(f"{label}[{key}] 存在非数值速度")
            # FLORIS 在远场/边界可能出现极小负值（数值噪声），容忍 -1 m/s 以内
            elif min(flat) < -1.0:
                err(f"{label}[{key}] 出现明显负速度 {min(flat)} m/s（<-1）")
            if flat and max(flat) > 30:
                warn(f"{label}[{key}] 最大速度 {max(flat)} m/s 偏高，请确认单位")
    hm = d3.get("heatmap")
    if hm:
        nu, ny = len(hm.get("wind_speeds", [])), len(hm.get("yaw_angles", []))
        g = hm.get("gain_pct", [])
        if len(g) != nu or any(len(r) != ny for r in g):
            err("heatmap.gain_pct 形状与风速/偏航网格不一致")
        else:
            lo, hi = min(min(r) for r in g), max(max(r) for r in g)
            if lo < -50 or hi > 100:
                warn(f"heatmap 增益范围异常: {lo:.1f}% ~ {hi:.1f}%")


def _csv_rows(name):
    with open(os.path.join(ROOT, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _close(a, b, tol=0.005):
    return is_num(a) and abs(float(a) - float(b)) <= tol


def check_source_sync(d):
    """确认前端 data.js 与根目录 CSV/JSON 源文件逐工况同源。"""
    multi = d.get("multi", {})
    speeds, yaws = multi.get("wind_speeds", []), multi.get("yaw_angles", [])
    for row in _csv_rows("cases_multi.csv"):
        u, yaw = float(row["U_inf"]), float(row["yaw_1"])
        if u not in speeds or yaw not in yaws:
            err(f"data.js 缺 cases_multi 工况 U={u}, yaw={yaw}")
            continue
        i, j = speeds.index(u), yaws.index(yaw)
        for key, column in (("p1", "power_1"), ("p2", "power_2"),
                            ("ptot", "power_total"), ("gain", "gain_pct")):
            if not _close(multi[key][i][j], float(row[column])):
                err(f"data.js multi.{key} 未同步 {column} @ U={u},yaw={yaw}")

    single = d.get("single", {})
    syaws = single.get("yaw_angles", [])
    for row in _csv_rows("cases.csv"):
        yaw = float(row["yaw_1"])
        if yaw not in syaws:
            err(f"data.js single 缺 yaw={yaw}")
            continue
        j = syaws.index(yaw)
        for key, column in (("p1", "power_1"), ("p2", "power_2"), ("ptot", "power_total")):
            if not _close(single[key][j], float(row[column])):
                err(f"data.js single.{key} 未同步 {column} @ yaw={yaw}")

    array = d.get("array", {})
    ayaws = array.get("yaw_upstream", [])
    for row in _csv_rows("cases_array.csv"):
        yaw = float(row["yaw_upstream"])
        if yaw not in ayaws:
            err(f"data.js array 缺 yaw={yaw}")
            continue
        i = ayaws.index(yaw)
        source_powers = [float(row[f"power_{k}"]) for k in range(1, 10)]
        if any(not _close(a, b) for a, b in zip(array["powers"][i], source_powers)):
            err(f"data.js array.powers 未同步 cases_array.csv @ yaw={yaw}")
        if not _close(array["total"][i], float(row["power_total"])):
            err(f"data.js array.total 未同步 cases_array.csv @ yaw={yaw}")
        if not _close(array["gain"][i], float(row["gain_pct"])):
            err(f"data.js array.gain 未同步 cases_array.csv @ yaw={yaw}")

    for source, key in (("optimizer_result.json", "opt"),
                        ("array_independent_result.json", "array_opt")):
        with open(os.path.join(ROOT, source), encoding="utf-8") as fh:
            expected = json.load(fh)
        if d.get(key) != expected:
            err(f"data.js {key} 与 {source} 不同源，请重跑 site/build_data.py")


def check_real_3d(real, d3):
    """检查 Three.js 使用的精简三维数据结构，并与 data_3d.js 工况集合对齐。"""
    if not isinstance(real, dict) or not real:
        err("data_3d_real.js 为空或不是对象")
        return
    standard = d3.get("fields_3d", {}) if d3 else {}
    if set(real) != set(standard):
        err(f"data_3d_real.js 工况键与 data_3d.js 不一致：{sorted(real)} vs {sorted(standard)}")
    for key, fd in real.items():
        x, y, z, u = fd.get("x"), fd.get("y"), fd.get("z"), fd.get("u")
        if not (x and y and z and u):
            err(f"data_3d_real[{key}] 缺 x/y/z/u")
            continue
        bad = (len(u) != len(z) or
               any(not isinstance(layer, list) or len(layer) != len(y) for layer in u) or
               any(not isinstance(row, list) or len(row) != len(x)
                   for layer in u for row in layer))
        if bad:
            err(f"data_3d_real[{key}] u 形状应为 ({len(z)},{len(y)},{len(x)})")
            continue
        flat = [value for layer in u for row in layer for value in row]
        if any(value is not None and not is_num(value) for value in flat):
            err(f"data_3d_real[{key}] 含非法速度值")
        finite = [value for value in flat if value is not None]
        if finite and min(finite) < -1.0:
            err(f"data_3d_real[{key}] 出现明显负速度 {min(finite)} m/s")


def main():
    d = load_window_js("data.js", "WIND_DATA")
    if d is not None:
        check_multi(d)
        check_scalars(d)
        check_source_sync(d)
    d3 = load_window_js("data_3d.js", "WIND_3D_DATA")
    if d3 is not None:
        check_3d(d3)
    real = load_window_js("data_3d_real.js", "WIND_3D_REAL")
    if real is not None:
        check_real_3d(real, d3)

    print("=" * 60)
    if WARNINGS:
        print(f"⚠️  警告 {len(WARNINGS)} 项：")
        for w in WARNINGS:
            print("  - " + w)
    if ERRORS:
        print(f"❌ 错误 {len(ERRORS)} 项：")
        for e in ERRORS:
            print("  - " + e)
        print("=" * 60)
        print("契约校验失败，请修正后再部署/展示。")
        sys.exit(1)
    print("✅ 契约校验通过：源 CSV/JSON、data.js、data_3d.js 与 data_3d_real.js 同源一致。")
    if WARNINGS:
        print(f"   （有 {len(WARNINGS)} 条警告，建议人工确认）")
    print("=" * 60)


if __name__ == "__main__":
    main()
