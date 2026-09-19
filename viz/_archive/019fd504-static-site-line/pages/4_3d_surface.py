import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import os

st.set_page_config(page_title="3D尾流", page_icon="🌐", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #080d1a; }
[data-testid="stSidebar"] { background-color: #0d1526; }
[data-testid="stSidebar"] * { color: #e8edf5 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("## 🌐 三维尾流速度场")
st.divider()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@st.cache_data
def load_cases():
    return pd.read_csv(os.path.join(BASE, "cases.csv"))

@st.cache_data
def load_field(case_id):
    path = os.path.join(BASE, "fields", f"{case_id}.npz")
    if os.path.exists(path):
        d = np.load(path)
        return d["x"], d["y"], d["u"]
    return None, None, None

df = load_cases()

# ===== 侧边栏 =====
with st.sidebar:
    st.markdown("## ⚙️ 显示设置")
    st.divider()

    yaw_select = st.select_slider(
        "选择偏航角 (°)",
        options=sorted(df["yaw_1"].astype(int).tolist()),
        value=0
    )

    st.divider()
    show_surface = st.checkbox("显示速度曲面", value=True)
    show_contour = st.checkbox("显示底部投影", value=True)
    show_turbines = st.checkbox("显示风机位置", value=True)

    st.divider()
    colorscale = st.selectbox(
        "配色方案",
        ["RdBu_r", "Viridis", "Plasma", "Turbo"],
        index=0
    )

# ===== 找工况 =====
idx = (df["yaw_1"] - yaw_select).abs().idxmin()
row = df.loc[idx]
case_id = row["case_id"]
x, y, u = load_field(case_id)

if u is None:
    st.error("找不到流场数据")
    st.stop()

# ===== 构建3D图 =====
X, Y = np.meshgrid(x, y)

fig = go.Figure()

# 三维速度曲面
if show_surface:
    fig.add_trace(go.Surface(
        x=X, y=Y, z=u,
        colorscale=colorscale,
        cmin=4, cmax=9,
        colorbar=dict(
            title="风速 (m/s)",
            thickness=15,
            len=0.6,
            x=1.02
        ),
        opacity=0.9,
        contours=dict(
            z=dict(show=True, usecolormap=True,
                   highlightcolor="white", project_z=False)
        ),
        name="速度场"
    ))

# 底部投影（等值线）
if show_contour:
    fig.add_trace(go.Surface(
        x=X, y=Y, z=u,
        colorscale=colorscale,
        cmin=4, cmax=9,
        showscale=False,
        opacity=0.3,
        contours=dict(
            z=dict(show=True, usecolormap=True,
                   project=dict(z=True),
                   start=4, end=9, size=0.5)
        ),
        name="底部投影"
    ))

# 风机位置（垂直线段）
if show_turbines:
    for tx, label in zip([0, 630], ["风机1", "风机2"]):
        # 找风机处的风速值
        x_idx = np.argmin(np.abs(x - tx))
        y_idx = np.argmin(np.abs(y - 0))
        u_at_turbine = float(u[y_idx, x_idx])

        # 垂直线段（从底部到速度曲面）
        fig.add_trace(go.Scatter3d(
            x=[tx, tx],
            y=[0, 0],
            z=[3.5, u_at_turbine],
            mode="lines+text",
            line=dict(color="white", width=4),
            text=["", label],
            textposition="top center",
            textfont=dict(color="white", size=12),
            showlegend=False
        ))

        # 顶部圆点
        fig.add_trace(go.Scatter3d(
            x=[tx], y=[0], z=[u_at_turbine],
            mode="markers",
            marker=dict(size=6, color="white",
                        symbol="diamond"),
            showlegend=False
        ))

fig.update_layout(
    scene=dict(
        xaxis=dict(
            title="顺风方向 x (m)",
            backgroundcolor="#0d1526",
            gridcolor="#1e2d4a",
            showbackground=True,
            color="#8899bb"
        ),
        yaxis=dict(
            title="横向 y (m)",
            backgroundcolor="#0d1526",
            gridcolor="#1e2d4a",
            showbackground=True,
            color="#8899bb"
        ),
        zaxis=dict(
            title="风速 (m/s)",
            backgroundcolor="#080d1a",
            gridcolor="#1e2d4a",
            showbackground=True,
            color="#8899bb",
            range=[3.5, 9.5]
        ),
        bgcolor="#080d1a",
        camera=dict(
            eye=dict(x=-1.5, y=-1.8, z=1.2)
        )
    ),
    title=dict(
        text=f"三维尾流速度场  |  偏航角 = {yaw_select:+.0f}°  "
             f"|  P₁={row['power_1']:.0f} kW  "
             f"P₂={row['power_2']:.0f} kW  "
             f"总={row['power_1']+row['power_2']:.0f} kW",
        font=dict(color="#e8edf5", size=14),
        x=0.5
    ),
    height=620,
    margin=dict(l=0, r=0, t=60, b=0),
    paper_bgcolor="#080d1a",
    font=dict(color="#e8edf5")
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("""
<div style="color:#8899bb; font-size:13px; text-align:center;">
💡 用鼠标拖拽旋转视角，滚轮缩放，双击重置视角
</div>
""", unsafe_allow_html=True)