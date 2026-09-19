import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import DARK_CSS, PLOT_THEME, GRID_STYLE, AXIS_COLOR, download_plotly, download_csv

st.set_page_config(page_title="数据总览", page_icon="📋", layout="wide")
st.markdown(DARK_CSS, unsafe_allow_html=True)

st.markdown("## 📋 数据总览")
st.divider()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@st.cache_data
def load_cases():
    return pd.read_csv(os.path.join(BASE, "cases.csv"))

with st.spinner("加载数据..."):
    df = load_cases()
    df["power_total"] = df["power_1"] + df["power_2"]
    baseline = df[df["yaw_1"] == 0]["power_total"].values[0]
    df["gain_pct"] = (df["power_total"] - baseline) / baseline * 100

c1, c2, c3, c4 = st.columns(4)
c1.metric("工况总数", f"{len(df)} 个")
c2.metric("最大总功率",
          f"{df['power_total'].max():.0f} kW",
          delta=f"偏航 {df.loc[df['power_total'].idxmax(), 'yaw_1']:+.0f}°")
c3.metric("最小总功率",
          f"{df['power_total'].min():.0f} kW",
          delta=f"偏航 {df.loc[df['power_total'].idxmin(), 'yaw_1']:+.0f}°")
c4.metric("最大功率提升",
          f"{df['gain_pct'].max():.1f}%",
          delta=f"偏航 {df.loc[df['gain_pct'].idxmax(), 'yaw_1']:+.0f}°")

st.markdown("<br>", unsafe_allow_html=True)

# ===== 柱状图 =====
st.markdown("#### ⚡ 各工况总功率对比 (kW)")
colors = ["#27ae60" if g > 0 else "#e74c3c" for g in df["gain_pct"]]

fig_bar = go.Figure()
fig_bar.add_trace(go.Bar(
    x=df["yaw_1"],
    y=df["power_total"],
    marker_color=colors,
    text=[f"{p:.0f}" for p in df["power_total"]],
    textposition="outside",
    textfont=dict(color="#e8edf5", size=11),
    name="总功率 (kW)"
))
fig_bar.add_hline(
    y=baseline,
    line_dash="dash", line_color="#a8bcdf", line_width=1.5,
    annotation_text="基准（0°）",
    annotation_font=dict(color="#a8bcdf", size=11)
)
fig_bar.update_layout(
    xaxis=dict(title="偏航角 (°)", showgrid=False, **AXIS_COLOR,
               tickmode="array", tickvals=df["yaw_1"].tolist()),
    yaxis=dict(title="总功率 (kW)", **GRID_STYLE, **AXIS_COLOR,
               range=[df["power_total"].min() * 0.95,
                      df["power_total"].max() * 1.06]),
    height=350,
    margin=dict(l=10, r=10, t=20, b=50),
    **PLOT_THEME, showlegend=False
)
st.plotly_chart(fig_bar, use_container_width=True)
download_plotly(fig_bar, "overview_power_bar.html", "📥 下载柱状图")

st.markdown("<br>", unsafe_allow_html=True)

# ===== 折线图 =====
st.markdown("#### 📈 功率分布详情 (kW)")
fig_line = go.Figure()
fig_line.add_trace(go.Scatter(
    x=df["yaw_1"], y=df["power_1"],
    name="上游 P₁ (kW)", mode="lines+markers",
    line=dict(color="#e67e22", width=2), marker=dict(size=7)
))
fig_line.add_trace(go.Scatter(
    x=df["yaw_1"], y=df["power_2"],
    name="下游 P₂ (kW)", mode="lines+markers",
    line=dict(color="#2980b9", width=2), marker=dict(size=7)
))
fig_line.add_trace(go.Scatter(
    x=df["yaw_1"], y=df["power_total"],
    name="总功率 (kW)", mode="lines+markers",
    line=dict(color="#4a9eff", width=2.5, dash="dot"),
    marker=dict(size=7)
))
fig_line.update_layout(
    xaxis=dict(title="偏航角 (°)", **GRID_STYLE, **AXIS_COLOR),
    yaxis=dict(title="功率 (kW)",  **GRID_STYLE, **AXIS_COLOR),
    height=320,
    margin=dict(l=10, r=10, t=20, b=50),
    **PLOT_THEME,
    legend=dict(orientation="h", y=-0.2, x=0,
                font=dict(size=11), bgcolor="rgba(0,0,0,0)")
)
st.plotly_chart(fig_line, use_container_width=True)
download_plotly(fig_line, "overview_power_lines.html", "📥 下载折线图")

st.divider()

# ===== 数据表格 =====
st.markdown("#### 📄 全部工况原始数据")
st.dataframe(
    df[["case_id", "yaw_1", "power_1",
        "power_2", "power_total", "gain_pct"]].rename(columns={
        "case_id":     "工况编号",
        "yaw_1":       "偏航角 (°)",
        "power_1":     "P₁ (kW)",
        "power_2":     "P₂ (kW)",
        "power_total": "总功率 (kW)",
        "gain_pct":    "相对基准增益 (%)"
    }).style.format({
        "P₁ (kW)":         "{:.1f}",
        "P₂ (kW)":         "{:.1f}",
        "总功率 (kW)":      "{:.1f}",
        "相对基准增益 (%)": "{:+.2f}"
    }),
    use_container_width=True,
    hide_index=True
)
download_csv(
    df[["case_id", "yaw_1", "power_1", "power_2",
        "power_total", "gain_pct"]],
    "overview_data.csv", "📥 下载数据表格 (CSV)"
)