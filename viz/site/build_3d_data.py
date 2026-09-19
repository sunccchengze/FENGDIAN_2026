#!/usr/bin/env python3
"""导出3D流场数据为JS，供Plotly.js前端交互渲染使用。
运行：python3 site/build_3d_data.py
输出：site/assets/data_3d.js  (window.WIND_3D_DATA)
"""
import numpy as np
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ===== 2D 流场数据 (fields/) =====
fields_2d = {}
cases_csv = os.path.join(BASE, "cases.csv")
if os.path.exists(cases_csv):
    import pandas as pd
    df = pd.read_csv(cases_csv)
    for _, row in df.iterrows():
        cid = row["case_id"]
        yaw = int(row["yaw_1"])
        path = os.path.join(BASE, "fields", f"{cid}.npz")
        if os.path.exists(path):
            d = np.load(path)
            # 降采样到 64x32 以控制 JS 文件体积
            x = d["x"]
            y = d["y"]
            u = d["u"]
            # 取每隔2个点
            x_ds = x[::2].tolist()
            y_ds = y[::2].tolist()
            u_ds = u[::2, ::2].tolist()
            fields_2d[str(yaw)] = {"x": x_ds, "y": y_ds, "u": u_ds}

# ===== 3D 流场数据 (fields_3d/) =====
fields_3d = {}
for fname in sorted(os.listdir(os.path.join(BASE, "fields_3d"))):
    if not fname.endswith(".npz"):
        continue
    path = os.path.join(BASE, "fields_3d", fname)
    d = np.load(path)
    x = d["x"]
    y = d["y"]
    z = d["z"]
    u = d["u"]  # shape: (n_z, n_y, n_x)
    # 从文件名解析偏航角
    yaw_str = fname.replace("yaw_", "").replace(".npz", "")
    # 降采样: x取每隔2, y取每隔2, z全保留(只有9层)
    x_ds = x[::2].tolist()
    y_ds = y[::2].tolist()
    z_ds = z.tolist()
    u_ds = u[:, ::2, ::2].tolist()
    fields_3d[yaw_str] = {"x": x_ds, "y": y_ds, "z": z_ds, "u": u_ds}

# ===== 热力矩阵数据 =====
# 从 cases_multi.csv 构建偏航角×风速的功率增益矩阵
heatmap_data = {}
cases_multi = os.path.join(BASE, "cases_multi.csv")
if os.path.exists(cases_multi):
    import pandas as pd
    dfm = pd.read_csv(cases_multi)
    wind_speeds = sorted(dfm["U_inf"].unique())
    yaw_angles = sorted(dfm["yaw_1"].unique())
    # 计算每个(U, yaw)的总功率
    ptot_map = {}
    for _, row in dfm.iterrows():
        u_key = float(row["U_inf"])
        y_key = float(row["yaw_1"])
        ptot = float(row["power_1"] + row["power_2"])
        ptot_map[(u_key, y_key)] = ptot
    # 计算增益(%)
    gain_matrix = []
    for u in wind_speeds:
        row_gains = []
        base_ptot = ptot_map.get((u, 0.0), 0)
        for y in yaw_angles:
            ptot = ptot_map.get((u, y), 0)
            gain = ((ptot - base_ptot) / base_ptot * 100) if base_ptot > 0 else 0
            row_gains.append(round(gain, 2))
        gain_matrix.append(row_gains)
    heatmap_data = {
        "wind_speeds": [float(u) for u in wind_speeds],
        "yaw_angles": [float(y) for y in yaw_angles],
        "gain_pct": gain_matrix
    }

result = {
    "fields_2d": fields_2d,
    "fields_3d": fields_3d,
    "heatmap": heatmap_data
}

js_content = f"window.WIND_3D_DATA = {json.dumps(result)};"
out_path = os.path.join(BASE, "site", "assets", "data_3d.js")
with open(out_path, "w") as f:
    f.write(js_content)

# ---- 精简的真实三维流场（供 three.js 点云尾流使用）：只导出 fields_3d，降采样 ----
real = {}
d3dir = os.path.join(BASE, "fields_3d")
if os.path.isdir(d3dir):
    for fname in sorted(os.listdir(d3dir)):
        if not fname.endswith(".npz"):
            continue
        d = np.load(os.path.join(d3dir, fname))
        u = d["u"][:, ::2, ::2]  # 9 x 16 x 32
        yaw = fname.replace("yaw_", "").replace(".npz", "")

        def clean(v):
            return None if not np.isfinite(v) else round(float(v), 3)
        real[yaw] = {
            "x": d["x"][::2].tolist(), "y": d["y"][::2].tolist(), "z": d["z"].tolist(),
            "u": [[[clean(v) for v in row] for row in layer] for layer in u],
        }
    real_path = os.path.join(BASE, "site", "assets", "data_3d_real.js")
    with open(real_path, "w") as f:
        f.write("window.WIND_3D_REAL = " + json.dumps(real, separators=(",", ":")) + ";")
    print(f"✅ 真实三维流场: {real_path} ({os.path.getsize(real_path)/1024:.0f} KB, {len(real)} 偏航角)")

print(f"✅ 导出完成: {out_path}")
print(f"   2D 流场工况: {len(fields_2d)}")
print(f"   3D 流场工况: {len(fields_3d)}")
print(f"   热力矩阵: {len(heatmap_data)} 风速×偏航角")
print(f"   文件大小: {os.path.getsize(out_path)/1024:.0f} KB")
