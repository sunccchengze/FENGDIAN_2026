import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from surrogate_model import predict_power
from utils import DARK_CSS, PLOT_THEME, GRID_STYLE, AXIS_COLOR, download_plotly

st.set_page_config(page_title="尾流分析", page_icon="📊", layout="wide")
st.markdown(DARK_CSS, unsafe_allow_html=True)

st.markdown("## 📊 尾流分析")
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

@st.cache_data
def load_result():
    import json
    with open(os.path.join(BASE, "optimizer_result.json")) as f:
        return json.load(f)

with st.spinner("加载数据..."):
    df = load_cases()
    df["power_total"] = df["power_1"] + df["power_2"]
    baseline = df[df["yaw_1"] == 0]["power_total"].values[0]
    result   = load_result()

with st.sidebar:
    st.markdown("## ⚙️ 参数控制台")
    st.divider()
    yaw_input = st.slider(
        "上游风机偏航角 γ₁ (°)",
        min_value=int(df["yaw_1"].min()),
        max_value=int(df["yaw_1"].max()),
        value=0, step=1
    )
    st.divider()
    st.markdown("**📋 数据集信息**")
    st.markdown(f"""
- 工况数量：**{len(df)}** 个
- 代理模型：**三次样条插值**
- 风机型号：**NREL 5MW**
- 来流风速：**8.0 m/s**
- 湍流强度：**6%**
- 机组间距：**630 m（5D）**
- 尾流模型：**GCH**
    """)

with st.spinner("计算代理模型预测值..."):
    p1_pred, p2_pred = predict_power(yaw_input)
    p_total_pred = p1_pred + p2_pred
    gain_pred    = (p_total_pred - baseline) / baseline * 100

idx     = (df["yaw_1"] - yaw_input).abs().idxmin()
row     = df.loc[idx]
case_id = row["case_id"]

c1, c2, c3, c4 = st.columns(4)
with c1:
    p1_base = df[df["yaw_1"] == 0]["power_1"].values[0]
    st.metric("⬆️ 上游风机 P₁",
              f"{p1_pred:.0f} kW",
              delta=f"{p1_pred - p1_base:+.0f} kW")
with c2:
    p2_base = df[df["yaw_1"] == 0]["power_2"].values[0]
    st.metric("⬇️ 下游风机 P₂",
              f"{p2_pred:.0f} kW",
              delta=f"{p2_pred - p2_base:+.0f} kW")
with c3:
    st.metric("⚡ 总功率",
              f"{p_total_pred:.0f} kW",
              delta=f"{p_total_pred - baseline:+.0f} kW vs 无偏航")
with c4:
    st.metric("📈 相对基准增益", f"{gain_pred:+.1f}%")

st.markdown("<br>", unsafe_allow_html=True)

col_map, col_curves = st.columns([3, 2])

with col_map:
    st.markdown(f"#### 🗺️ 尾流速度场（最近工况：{row['yaw_1']:+.0f}°）")
    with st.spinner("加载流场数据..."):
        x, y, u = load_field(case_id)

    if u is not None:
        fig_map = go.Figure()
        fig_map.add_trace(go.Heatmap(
            z=u, x=x, y=y,
            colorscale="RdBu_r", zmin=4, zmax=9,
            colorbar=dict(
                title=dict(text="风速 (m/s)", side="right"),
                thickness=15, len=0.8, x=1.02
            )
        ))
        fig_map.add_trace(go.Scatter(
            x=[0, 630], y=[0, 0],
            mode="markers+text",
            marker=dict(size=16, color="#e8edf5", symbol="triangle-up",
                        line=dict(color="#1a3a6e", width=1.5)),
            text=["  风机1（可调偏航）", "  风机2（固定0°）"],
            textposition="middle right",
            textfont=dict(size=12, color="#e8edf5"),
            showlegend=True, name="风机位置"
        ))
        fig_map.add_trace(go.Scatter(
            x=[0, 900], y=[0, 0],
            mode="lines",
            line=dict(color="white", width=1, dash="dot"),
            name="中心线", opacity=0.4, showlegend=True
        ))
        fig_map.update_layout(
            xaxis=dict(title="顺风方向 x (m)", showgrid=False, **AXIS_COLOR),
            yaxis=dict(title="横向 y (m)",     showgrid=False, **AXIS_COLOR),
            height=420,
            margin=dict(l=10, r=70, t=20, b=50),
            **PLOT_THEME,
            legend=dict(orientation="h", y=-0.18, x=0,
                        font=dict(size=11), bgcolor="rgba(0,0,0,0)")
        )
        st.plotly_chart(fig_map, use_container_width=True)
        download_plotly(fig_map, f"wake_field_yaw{row['yaw_1']:+.0f}.html",
                        "📥 下载尾流云图")

with col_curves:
    st.markdown("#### 📈 总功率 vs 偏航角 (°)")
    with st.spinner("生成功率曲线..."):
        yaw_fine = np.linspace(-30, 30, 200)
        p_fine   = [predict_power(y)[0] + predict_power(y)[1]
                    for y in yaw_fine]

    fig_total = go.Figure()
    fig_total.add_trace(go.Scatter(
        x=yaw_fine, y=p_fine,
        mode="lines", name="代理模型曲线",
        line=dict(color="#4a9eff", width=2),
        fill="tozeroy", fillcolor="rgba(74,158,255,0.08)"
    ))
    fig_total.add_trace(go.Scatter(
        x=df["yaw_1"], y=df["power_total"],
        mode="markers", name="FLORIS计算点",
        marker=dict(size=7, color="#a8bcdf")
    ))
    fig_total.add_trace(go.Scatter(
        x=[yaw_input], y=[p_total_pred],
        mode="markers", name=f"当前 {yaw_input}°",
        marker=dict(size=14, color="#e74c3c",
                    line=dict(color="white", width=2))
    ))
    fig_total.add_vline(
        x=result["recommended_yaw"],
        line_dash="dash", line_color="#27ae60", line_width=1.5,
        annotation_text=f"最优 {result['recommended_yaw']}°",
        annotation_font=dict(color="#27ae60", size=11)
    )
    fig_total.update_layout(
        xaxis=dict(title="偏航角 (°)", **GRID_STYLE, **AXIS_COLOR),
        yaxis=dict(title="总功率 (kW)", **GRID_STYLE, **AXIS_COLOR),
        height=190,
        margin=dict(l=10, r=10, t=15, b=40),
        **PLOT_THEME,
        legend=dict(orientation="h", y=-0.38, x=0,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)")
    )
    st.plotly_chart(fig_total, use_container_width=True)
    download_plotly(fig_total, "wake_power_curve.html", "📥 下载功率曲线")

    st.markdown("#### ⚡ 上下游功率分解 (kW)")
    p1_fine = [predict_power(y)[0] for y in yaw_fine]
    p2_fine = [predict_power(y)[1] for y in yaw_fine]

    fig_split = go.Figure()
    fig_split.add_trace(go.Scatter(
        x=yaw_fine, y=p1_fine,
        name="上游 P₁", mode="lines",
        line=dict(color="#e67e22", width=2)
    ))
    fig_split.add_trace(go.Scatter(
        x=yaw_fine, y=p2_fine,
        name="下游 P₂", mode="lines",
        line=dict(color="#2980b9", width=2)
    ))
    fig_split.add_vline(x=yaw_input, line_dash="dot",
                        line_color="#e74c3c", line_width=1.5)
    fig_split.update_layout(
        xaxis=dict(title="偏航角 (°)", **GRID_STYLE, **AXIS_COLOR),
        yaxis=dict(title="功率 (kW)",  **GRID_STYLE, **AXIS_COLOR),
        height=190,
        margin=dict(l=10, r=10, t=15, b=40),
        **PLOT_THEME,
        legend=dict(orientation="h", y=-0.42, x=0,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)")
    )
    st.plotly_chart(fig_split, use_container_width=True)
    download_plotly(fig_split, "wake_power_split.html", "📥 下载分解曲线")