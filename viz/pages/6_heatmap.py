import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import DARK_CSS, PLOT_THEME, GRID_STYLE, AXIS_COLOR, download_plotly, download_csv

st.set_page_config(page_title="热力矩阵", page_icon="🔥", layout="wide")
st.markdown(DARK_CSS, unsafe_allow_html=True)

st.markdown("## 🔥 多风速偏航优化热力矩阵")
st.divider()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@st.cache_data
def load_multi():
    df = pd.read_csv(os.path.join(BASE, "cases_multi.csv"))
    df["power_total"] = df["power_1"] + df["power_2"]
    return df

with st.spinner("加载多风速数据..."):
    df = load_multi()

wind_speeds = sorted(df["U_inf"].unique())
yaw_angles  = sorted(df["yaw_1"].unique())

with st.sidebar:
    st.markdown("## ⚙️ 显示设置")
    st.divider()
    metric = st.radio(
        "显示指标",
        ["总功率 (kW)", "功率增益 (%)", "下游风机 P₂ (kW)"],
        index=1
    )
    st.divider()
    st.markdown("**数据说明**")
    st.markdown(f"""
- 风速范围：**{min(wind_speeds):.0f} ~ {max(wind_speeds):.0f} m/s**
- 偏航角范围：**-30° 到 +30°**
- 工况总数：**{len(df)}** 个
- 风机型号：**NREL 5MW**
- 额定功率：**5000 kW**
    """)

# ===== 构建矩阵 =====
with st.spinner("构建热力矩阵..."):
    matrix      = np.zeros((len(wind_speeds), len(yaw_angles)))
    text_matrix = []

    for i, U in enumerate(wind_speeds):
        row_text = []
        baseline = df[(df["U_inf"] == U) & (df["yaw_1"] == 0)]["power_total"].values[0]
        for j, yaw in enumerate(yaw_angles):
            row    = df[(df["U_inf"] == U) & (df["yaw_1"] == yaw)].iloc[0]
            p_total = row["power_total"]
            gain    = (p_total - baseline) / baseline * 100
            if metric == "总功率 (kW)":
                val  = p_total
                text = f"{p_total:.0f} kW"
            elif metric == "功率增益 (%)":
                val  = gain
                text = f"{gain:+.1f}%"
            else:
                val  = row["power_2"]
                text = f"{row['power_2']:.0f} kW"
            matrix[i, j] = val
            row_text.append(text)
        text_matrix.append(row_text)

colorscale = "RdYlGn" if metric == "功率增益 (%)" else "Viridis"
zmid       = 0         if metric == "功率增益 (%)" else None

# ===== 热力矩阵 =====
st.markdown("#### 🔥 偏航角 × 风速 热力矩阵")
fig_hm = go.Figure(go.Heatmap(
    z=matrix,
    x=[f"{y:+.0f}°" for y in yaw_angles],
    y=[f"{U:.0f} m/s" for U in wind_speeds],
    text=text_matrix,
    texttemplate="%{text}",
    textfont=dict(size=12, color="white"),
    colorscale=colorscale,
    zmid=zmid,
    colorbar=dict(title=dict(text=metric, side="right"), thickness=15)
))
fig_hm.update_layout(
    title=dict(
        text=f"偏航角 × 风速 热力矩阵  |  指标：{metric}",
        font=dict(color="#e8edf5", size=15), x=0.5),
    xaxis=dict(title="上游风机偏航角 (°)", **AXIS_COLOR,
               tickfont=dict(size=12)),
    yaxis=dict(title="来流风速 (m/s)",     **AXIS_COLOR,
               tickfont=dict(size=12)),
    height=380,
    margin=dict(l=10, r=10, t=60, b=50),
    **PLOT_THEME
)
st.plotly_chart(fig_hm, use_container_width=True)
download_plotly(fig_hm, "heatmap_matrix.html", "📥 下载热力矩阵")

st.divider()

# ===== 各风速功率曲线 =====
st.markdown("#### 📈 各风速下总功率 vs 偏航角 (kW)")
fig_curves = go.Figure()
colors_map = ["#4a9eff", "#27ae60", "#e67e22", "#e74c3c"]

for U, color in zip(wind_speeds, colors_map):
    df_U     = df[df["U_inf"] == U].sort_values("yaw_1")
    best_yaw = df_U.loc[df_U["power_total"].idxmax(), "yaw_1"]
    fig_curves.add_trace(go.Scatter(
        x=df_U["yaw_1"], y=df_U["power_total"],
        mode="lines+markers",
        name=f"{U:.0f} m/s（最优 {best_yaw:+.0f}°）",
        line=dict(color=color, width=2),
        marker=dict(size=6)
    ))

fig_curves.update_layout(
    xaxis=dict(title="偏航角 (°)", **GRID_STYLE, **AXIS_COLOR),
    yaxis=dict(title="总功率 (kW)", **GRID_STYLE, **AXIS_COLOR),
    height=320,
    margin=dict(l=10, r=10, t=20, b=50),
    **PLOT_THEME,
    legend=dict(orientation="h", y=-0.25, x=0,
                font=dict(size=11), bgcolor="rgba(0,0,0,0)")
)
st.plotly_chart(fig_curves, use_container_width=True)
download_plotly(fig_curves, "heatmap_power_curves.html", "📥 下载功率曲线")

st.divider()

# ===== 最优偏航角汇总 =====
st.markdown("#### 🎯 各风速最优偏航角汇总")
cols = st.columns(len(wind_speeds))
for col, U in zip(cols, wind_speeds):
    df_U     = df[df["U_inf"] == U]
    best     = df_U.loc[df_U["power_total"].idxmax()]
    baseline = df_U[df_U["yaw_1"] == 0]["power_total"].values[0]
    gain     = (best["power_total"] - baseline) / baseline * 100
    col.metric(
        label=f"风速 {U:.0f} m/s",
        value=f"偏航 {best['yaw_1']:+.0f}°",
        delta=f"+{gain:.1f}%"
    )

st.divider()
download_csv(
    df[["U_inf", "yaw_1", "power_1", "power_2", "power_total"]],
    "heatmap_data.csv", "📥 下载全部工况数据 (CSV)"
)