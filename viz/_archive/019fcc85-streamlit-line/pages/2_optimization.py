import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import DARK_CSS, PLOT_THEME, GRID_STYLE, AXIS_COLOR, download_plotly

st.set_page_config(page_title="优化结果", page_icon="🎯", layout="wide")
st.markdown(DARK_CSS, unsafe_allow_html=True)

st.markdown("## 🎯 优化结果")
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
    with open(os.path.join(BASE, "optimizer_result.json")) as f:
        return json.load(f)

with st.spinner("加载数据..."):
    df     = load_cases()
    df["power_total"] = df["power_1"] + df["power_2"]
    result = load_result()

with st.sidebar:
    st.markdown("## ⚙️ 对比设置")
    st.divider()
    yaw_compare = st.slider(
        "对比偏航角 (°)",
        min_value=int(df["yaw_1"].min()),
        max_value=int(df["yaw_1"].max()),
        value=int(result["recommended_yaw"]),
        step=5
    )

idx_compare    = (df["yaw_1"] - yaw_compare).abs().idxmin()
row_compare    = df.loc[idx_compare]
case_id_compare = row_compare["case_id"]
case_id_base   = df[df["yaw_1"] == 0]["case_id"].values[0]

r1, r2, r3, r4 = st.columns(4)
r1.metric("原偏航角",     f"{result['original_yaw']}°")
r2.metric("推荐偏航角",   f"{result['recommended_yaw']}°")
r3.metric("优化前总功率", f"{result['power_before']:.0f} kW")
r4.metric("优化后总功率", f"{result['power_after']:.0f} kW",
          delta=f"+{result['power_gain_pct']}%")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("#### 🔄 偏航前后尾流对比")

with st.spinner("加载流场数据..."):
    x0, y0, u0 = load_field(case_id_base)
    x1, y1, u1 = load_field(case_id_compare)

col_b, col_a, col_d = st.columns(3)

def make_heatmap(x, y, u, title, colorscale="RdBu_r",
                 zmin=4, zmax=9, zmid=None, cbar_title="风速 (m/s)"):
    fig = go.Figure(go.Heatmap(
        z=u, x=x, y=y,
        colorscale=colorscale,
        zmin=zmin, zmax=zmax, zmid=zmid,
        colorbar=dict(thickness=12, len=0.85,
                      title=dict(text=cbar_title, side="right"))
    ))
    fig.add_trace(go.Scatter(
        x=[0, 630], y=[0, 0], mode="markers",
        marker=dict(size=12, color="#e8edf5", symbol="triangle-up"),
        showlegend=False
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#e8edf5"), x=0.5),
        xaxis=dict(title="顺风方向 x (m)", showgrid=False, **AXIS_COLOR),
        yaxis=dict(title="横向 y (m)",     showgrid=False, **AXIS_COLOR),
        height=300,
        margin=dict(l=10, r=60, t=40, b=45),
        **PLOT_THEME
    )
    return fig

with col_b:
    if u0 is not None:
        fig_b = make_heatmap(x0, y0, u0, "优化前（偏航 0°）")
        st.plotly_chart(fig_b, use_container_width=True)
        download_plotly(fig_b, "opt_before_field.html", "📥 下载优化前场")

with col_a:
    if u1 is not None:
        fig_a = make_heatmap(x1, y1, u1,
                             f"优化后（偏航 {row_compare['yaw_1']:+.0f}°）")
        st.plotly_chart(fig_a, use_container_width=True)
        download_plotly(fig_a, "opt_after_field.html", "📥 下载优化后场")

with col_d:
    if u0 is not None and u1 is not None:
        delta_u  = u1 - u0
        abs_max  = max(np.abs(delta_u).max(), 1e-6)
        fig_diff = make_heatmap(
            x1, y1, delta_u,
            "速度变化量（红=增加 蓝=减少）",
            colorscale="RdBu",
            zmin=-abs_max, zmax=abs_max,
            zmid=0, cbar_title="Δm/s"
        )
        st.plotly_chart(fig_diff, use_container_width=True)
        download_plotly(fig_diff, "opt_delta_field.html", "📥 下载差值场")

st.divider()

# ===== 动画 =====
st.markdown("#### 🎬 偏航角扫描动画")
col_gif, col_desc = st.columns([3, 1])

with col_gif:
    gif_path = os.path.join(BASE, "wake_animation.gif")
    if os.path.exists(gif_path):
        import base64
        with open(gif_path, "rb") as f:
            gif_b64 = base64.b64encode(f.read()).decode("utf-8")
        st.markdown(
            f'<img src="data:image/gif;base64,{gif_b64}" '
            f'style="width:100%; border-radius:12px;">',
            unsafe_allow_html=True
        )
    else:
        st.warning("未找到 wake_animation.gif，请先运行 export_gif.py")

with col_desc:
    st.markdown(f"""
**动画说明**

偏航角从 **-30°** 扫描至 **+30°** 再返回。

**关键现象：**
- 偏航角 = 0° 时，下游风机完全处于尾流遮挡区
- 偏航角 ≠ 0° 时，尾流向侧方偏转，下游入流风速回升
- 最优偏航角约为 **+{result['recommended_yaw']}°**
- 总功率提升 **{result['power_gain_pct']}%**
    """)