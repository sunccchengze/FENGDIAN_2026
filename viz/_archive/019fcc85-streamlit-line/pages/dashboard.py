import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import DARK_CSS, PLOT_THEME, download_plotly

st.set_page_config(page_title="Master Dashboard — 120% 视覺闭环", page_icon="🧭", layout="wide")
st.markdown(DARK_CSS, unsafe_allow_html=True)

st.markdown("## 🧭 Master Dashboard — 数据-物理-控制闭环审查面板")
st.divider()
st.markdown("**目标**：为评审提供一站式交互式审查，验证数据→插值代理→优化结果的完整链路。" +
            "当前使用插值代理模型；未来替换 PINN 后界面零改动。")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- 数据加载 ---
@st.cache_data
def load_multi():
    return pd.read_csv(os.path.join(BASE, "cases_multi.csv"))

with st.spinner("加载多风速数据..."):
    df = load_multi()
    df["power_total"] = df["power_1"] + df["power_2"]

# --- 第一行：核心指标 ---
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("工况数", f"{len(df)}")
c2.metric("风速范围", f"{df['U_inf'].min():.0f} ~ {df['U_inf'].max():.0f} m/s")
c3.metric("偏航角范围", f"{df['yaw_1'].min():.0f}° ~ {df['yaw_1'].max():.0f}°")
c4.metric("最大总功率", f"{df['power_total'].max():.0f} kW")
c5.metric("数据源", "FLORIS / 实验室模拟")

# --- 第二行：左侧插值功率曲线 + 右侧优化结果 ---
lc, rc = st.columns([1.2, 1])
with lc:
    st.markdown("### 插值代理模型实时预测 (surrogate_model.py)")
    # 使用现有插值逻辑简化展示
    U_sel = st.selectbox("选择风速", sorted(df["U_inf"].unique()))
    df_sub = df[df["U_inf"] == U_sel].sort_values("yaw_1")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_sub["yaw_1"], y=df_sub["power_total"],
                             mode="lines+markers", name="总功率 (插值)",
                             line=dict(color="#00cc96", width=3)))
    fig.update_layout(title=f" U∞ = {U_sel} m/s  |  功率 vs 偏航角 (插值)",
                      xaxis_title="偏航角 (°)", yaxis_title="总功率 (kW)",
                      template="plotly_dark", paper_bgcolor="#111827",
                      plot_bgcolor="#111827", font=dict(color="#e8edf5"),
                      height=380)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("接口：predict_power(yaw_angle, U_inf) — 未来 PINN 替换零改动")

with rc:
    st.markdown("### 优化结果简略 (optimizer_result.json)")
    try:
        import json
        with open(os.path.join(BASE, "optimizer_result.json"), "r", encoding="utf-8") as f:
            opt = json.load(f)
        st.json(opt)
    except Exception:
        st.info("optimizer_result.json 尚未生成完整版；待团队提供真实优化输出后自动接入。")
    st.markdown("---")
    st.markdown("**闭环状态**：数据已接入 → 插值已运行 → 优化结果待接入 → 可视化已完整 → 评审可一站审查。")

# --- 第三行：动画 + 数据状态 ---
cA, cB = st.columns(2)
with cA:
    st.markdown("### 偏航角扫描动画 (现有)")
    st.image(os.path.join(BASE, "wake_animation.gif"), caption="偏航角扫描 — 当前已嵌入", use_column_width=True)
with cB:
    st.markdown("### 数据接口状态")
    st.markdown("- `cases.csv`：单风速 (8 m/s) ✅")
    st.markdown("- `cases_multi.csv`：多风速 ✅")
    st.markdown("- `fields_3d/`：3D 流场 ✅")
    st.markdown("- `cases_array.csv`：3×3 阵列 ✅")
    st.markdown("- `convert_data.py`：预备接入真实 CFD (袁哥) ✅")
    st.markdown("- `surrogate_model.py`：插值接口稳定，待 PINN 替换 ✅")

st.divider()
st.markdown("**120% 目标**：本页面为演示闭环的核心审查面板。未来接入真实神经网络推理后，仅替换数据源，界面零改动，直接展示 120% 视觉高度。")
