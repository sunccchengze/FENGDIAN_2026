import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import time

st.set_page_config(page_title="尾流动画", layout="wide")
st.title("🌬️ 偏航角扫描动画")

@st.cache_data
def load_all_fields():
    df = pd.read_csv("cases.csv")
    frames = []
    for _, row in df.iterrows():
        data = np.load(f"fields/{row['case_id']}.npz")
        frames.append({
            "yaw": float(row["yaw_1"]),
            "x":   data["x"],
            "y":   data["y"],
            "u":   data["u"],
            "p1":  float(row["power_1"]),
            "p2":  float(row["power_2"]),
        })
    return frames

frames = load_all_fields()

# ===== 控制栏 =====
col1, col2 = st.columns([1, 2])
with col1:
    play = st.button("▶ 播放完整扫描")
with col2:
    speed = st.slider("播放速度（秒/帧）", 0.1, 1.2, 0.4, 0.1)

st.divider()

# ===== 占位符 =====
chart_slot  = st.empty()
metric_slot = st.empty()

# ===== 画单帧 =====
def draw_frame(f, key):
    fig = go.Figure()

    fig.add_trace(go.Heatmap(
        z=f["u"], x=f["x"], y=f["y"],
        colorscale="RdBu_r",
        zmin=4, zmax=9,
        colorbar=dict(title="风速 (m/s)", thickness=15)
    ))

    fig.add_trace(go.Scatter(
        x=[0, 630], y=[0, 0],
        mode="markers+text",
        marker=dict(size=15, color="#1a2340", symbol="triangle-up",
                    line=dict(color="white", width=1.5)),
        text=["风机1", "风机2"],
        textposition="top center",
        textfont=dict(size=12, color="#1a2340"),
        showlegend=False
    ))

    fig.update_layout(
        xaxis=dict(title="顺风方向 x (m)", showgrid=False),
        yaxis=dict(title="横向 y (m)",     showgrid=False),
        height=460,
        margin=dict(l=10, r=70, t=20, b=50),
        paper_bgcolor="white",
        plot_bgcolor="white",
    )

    chart_slot.plotly_chart(fig, use_container_width=True,
                            key=f"chart_{key}")

    total    = f["p1"] + f["p2"]
    baseline = 2190.4
    gain     = (total - baseline) / baseline * 100

    with metric_slot.container():
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("偏航角",  f"{f['yaw']:+.0f}°")
        m2.metric("上游 P₁", f"{f['p1']:.0f} kW")
        m3.metric("下游 P₂", f"{f['p2']:.0f} kW")
        m4.metric("总功率",  f"{total:.0f} kW",
                  delta=f"{gain:+.1f}% vs 0°")

# ===== 默认显示偏航0° =====
draw_frame(frames[6], key="init")

# ===== 播放 =====
if play:
    for i, f in enumerate(frames):
        draw_frame(f, key=f"fwd_{i}")
        time.sleep(speed)
    for i, f in enumerate(reversed(frames)):
        draw_frame(f, key=f"bwd_{i}")
        time.sleep(speed)
    draw_frame(frames[6], key="final")