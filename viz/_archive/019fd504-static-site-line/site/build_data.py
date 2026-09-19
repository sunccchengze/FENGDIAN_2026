#!/usr/bin/env python3
# 纯 Python（无 numpy/pandas 依赖）把仓库里的 CSV/JSON 导出为 site/assets/data.js
# 供纯静态网页（Cloudflare Pages）使用，浏览器内做插值，无需 Python 后端。
import csv, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "assets", "data.js")

def read_csv(name):
    with open(os.path.join(ROOT, name), newline="") as f:
        return list(csv.DictReader(f))

def f(x):
    try:
        return round(float(x), 3)
    except Exception:
        return x

data = {}

# ---- cases_multi.csv: 双机 (U_inf, yaw_1) -> P1/P2/Ptot ----
rows = read_csv("cases_multi.csv")
wind_speeds = sorted({float(r["U_inf"]) for r in rows})
yaw_angles = sorted({float(r["yaw_1"]) for r in rows})
def mat(col):
    m = [[None]*len(yaw_angles) for _ in wind_speeds]
    for r in rows:
        i = wind_speeds.index(float(r["U_inf"]))
        j = yaw_angles.index(float(r["yaw_1"]))
        m[i][j] = f(r[col])
    return m
data["multi"] = {
    "wind_speeds": [f(u) for u in wind_speeds],
    "yaw_angles": [f(y) for y in yaw_angles],
    "p1": mat("power_1"),
    "p2": mat("power_2"),
    "ptot": mat("power_total"),
    "gain": mat("gain_pct"),
}

# ---- cases.csv: 单风速(8m/s)双机 yaw 扫掠 ----
rows = read_csv("cases.csv")
u0 = sorted({float(r["U_inf"]) for r in rows})[0]
ya = sorted({float(r["yaw_1"]) for r in rows})
def arr(col):
    return [next(f(r[col]) for r in rows if float(r["U_inf"])==u0 and float(r["yaw_1"])==y) for y in ya]
data["single"] = {
    "U_inf": f(u0),
    "yaw_angles": [f(y) for y in ya],
    "p1": arr("power_1"),
    "p2": arr("power_2"),
    "ptot": arr("power_total"),
}

# ---- cases_array.csv: 3x3 阵列 (yaw_upstream) -> 9机功率 ----
rows = read_csv("cases_array.csv")
yu = sorted({float(r["yaw_upstream"]) for r in rows})
turb = [f"power_{k}" for k in range(1,10)]
def arr_powers():
    out = []
    for y in yu:
        r = next(r for r in rows if float(r["yaw_upstream"])==y)
        out.append([f(r[t]) for t in turb])
    return out
data["array"] = {
    "yaw_upstream": [f(y) for y in yu],
    "powers": arr_powers(),
    "total": [next(f(r["power_total"]) for r in rows if float(r["yaw_upstream"])==y) for y in yu],
    "gain": [next(f(r["gain_pct"]) for r in rows if float(r["yaw_upstream"])==y) for y in yu],
}

# ---- cases_windrose_opt.csv: 风玫瑰(优化后) ----
rows = read_csv("cases_windrose_opt.csv")
data["windrose_opt"] = [
    {"wind_direction": f(r["wind_direction"]), "U_inf": f(r["U_inf"]),
     "best_yaw": f(r["best_yaw"]), "power_base": f(r["power_base"]),
     "power_opt": f(r["power_opt"]), "gain_pct": f(r["gain_pct"])}
    for r in rows
]

# ---- optimizer_result.json / array_independent_result.json ----
with open(os.path.join(ROOT, "optimizer_result.json")) as fh:
    data["opt"] = json.load(fh)
with open(os.path.join(ROOT, "array_independent_result.json")) as fh:
    data["array_opt"] = json.load(fh)

js = "window.WIND_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n"
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(js)
print("wrote", OUT, "bytes=", len(js))
print("multi grid:", len(data["multi"]["wind_speeds"]), "x", len(data["multi"]["yaw_angles"]))
print("array yaw_upstream n=", len(data["array"]["yaw_upstream"]))
print("windrose_opt n=", len(data["windrose_opt"]))
