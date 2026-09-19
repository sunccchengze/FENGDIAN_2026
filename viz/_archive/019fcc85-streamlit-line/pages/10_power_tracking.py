import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from surrogate_model import (predict_power, predict_power_2d,
                              find_yaw_for_target, U_min, U_max)
from utils import DARK_CSS, PLOT_THEME, GRID_STYLE, AXIS_COLOR, \
    download_plotly, download_csv

st.set_page_config(page_title="功率需求跟踪", page_icon="🎛️", layout="wide")
st.markdown(DARK_CSS, unsafe_allow_html=True)

st.markdown("## 🎛️ 电网功率需求跟踪")
st.caption("双偏航角协同控制 · 在约束条件下精确跟踪电网目标功率")
st.divider()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

P_RATED = 5000.0

@st.cache_data
def load_cases():
    df = pd.read_csv(os.path.join(BASE, "cases_multi.csv"))
    df["power_total"] = df["power_1"] + df["power_2"]
    return df

df = load_cases()

# ===== 侧边栏 =====
with st.sidebar:
    st.markdown("## ⚙️ 输入参数")
    st.divider()

    U_input = st.slider(
        "当前来流风速 (m/s)",
        min_value=float(U_min), max_value=float(U_max),
        value=8.0, step=0.1
    )

    st.divider()
    st.markdown("**⚙️ 风机功率约束**")

    p1_min = st.slider("风机1 最小功率 (kW)", 0,   1000, 200,  50)
    p1_max = st.slider("风机1 最大功率 (kW)", 1000, int(P_RATED),
                       int(P_RATED), 100)
    p2_min = st.slider("风机2 最小功率 (kW)", 0,   1000, 200,  50)
    p2_max = st.slider("风机2 最大功率 (kW)", 1000, int(P_RATED),
                       int(P_RATED), 100)

    st.divider()
    st.markdown("**🔍 搜索精度**")
    n_search = st.select_slider(
        "2D搜索网格密度",
        options=[30, 40, 60, 80, 100],
        value=60
    )
    st.caption(f"搜索候选点：{n_search}² = {n_search**2} 个")

# ===== 计算可达范围 =====
with st.spinner("计算约束下的可达功率范围..."):
    yaw_scan = np.linspace(-30, 30, 120)
    feasible_powers_all = []
    for y1 in yaw_scan:
        for y2 in [0]:   # 快速估算用单变量
            p1, p2 = predict_power_2d(y1, y2, U_input)
            if p1_min <= p1 <= p1_max and p2_min <= p2 <= p2_max:
                feasible_powers_all.append(p1 + p2)

    if not feasible_powers_all:
        st.error("⚠️ 当前约束下无可行解，请放宽约束。")
        st.stop()

    p_min = min(feasible_powers_all)
    p_max = max(feasible_powers_all)
    st.info(f"ℹ️ 当前风速 **{U_input:.1f} m/s** 下最大可输出功率为 **{p_max:.0f} kW**。"
            f"如需更高功率，请在左侧提高来流风速。")

with st.sidebar:
    st.divider()
    st.markdown("**⚡ 当前可达功率范围**")
    st.markdown(f"**{p_min:.0f} ~ {p_max:.0f} kW**")
    target_power = st.slider(
        "电网目标功率需求 (kW)",
        min_value=int(p_min * 0.9),
        max_value=int(p_max * 1.1),
        value=int((p_min + p_max) / 2),
        step=10
    )

# ===== 2D搜索求解 =====
with st.spinner(f"2D搜索中（{n_search}² = {n_search**2}个候选点）..."):
    best_y1, best_y2, actual_power, err_pct, feasible = find_yaw_for_target(
        target_power, U_input,
        p1_min, p1_max, p2_min, p2_max,
        n_search=n_search
    )
    best_p1, best_p2 = predict_power_2d(best_y1, best_y2, U_input)

# ===== 状态提示 =====
if not feasible:
    st.error(f"⚠️ 目标功率 {target_power:.0f} kW 在当前约束下无可行方案")
elif err_pct < 1.0:
    st.success(f"✅ 2D搜索找到最优方案，跟踪误差 {err_pct:.2f}%")
elif err_pct < 3.0:
    st.warning(f"⚠️ 最接近方案误差 {err_pct:.2f}%，可增大搜索密度")
else:
    st.error(f"❌ 误差 {err_pct:.2f}%，建议调整目标功率或放宽约束")

st.markdown("<br>", unsafe_allow_html=True)

# ===== 约束满足情况 =====
p1_ok = p1_min <= best_p1 <= p1_max
p2_ok = p2_min <= best_p2 <= p2_max

st.markdown("#### 🔒 约束满足情况")
cc1, cc2, cc3, cc4 = st.columns(4)
cc1.metric("风机1 实际功率",
           f"{best_p1:.0f} kW",
           delta=f"[{p1_min}, {p1_max}] kW")
cc2.metric("风机2 实际功率",
           f"{best_p2:.0f} kW",
           delta=f"[{p2_min}, {p2_max}] kW")
cc3.metric("约束状态",
           "✅ 全部满足" if (p1_ok and p2_ok) else "❌ 存在违反")
cc4.metric("搜索候选点", f"{n_search**2} 个")

st.divider()

# ===== 顶部指标 =====
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("目标功率",    f"{target_power:.0f} kW")
c2.metric("风机1偏航角", f"{best_y1:+.1f}°")
c3.metric("风机2偏航角", f"{best_y2:+.1f}°")
c4.metric("实际总功率",
          f"{actual_power:.0f} kW",
          delta=f"{actual_power - target_power:+.0f} kW")
c5.metric("跟踪误差",    f"{err_pct:.2f}%")
c6.metric("P₁ / P₂",    f"{best_p1:.0f} / {best_p2:.0f} kW")

st.markdown("<br>", unsafe_allow_html=True)

# ===== 主图区 =====
col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown("#### 📈 2D功率曲面（yaw1 × yaw2）")
    st.caption("颜色深浅表示总功率大小，绿星为当前推荐方案，红线为目标功率等值线")

    with st.spinner("生成功率曲面..."):
        yaw1_grid = np.linspace(-30, 30, 40)
        yaw2_grid = np.linspace(-30, 30, 40)
        Z = np.zeros((len(yaw2_grid), len(yaw1_grid)))
        feasible_mask_2d = np.zeros_like(Z, dtype=bool)

        for i, y2 in enumerate(yaw2_grid):
            for j, y1 in enumerate(yaw1_grid):
                p1, p2 = predict_power_2d(y1, y2, U_input)
                Z[i, j] = p1 + p2
                feasible_mask_2d[i, j] = (
                    p1_min <= p1 <= p1_max and
                    p2_min <= p2 <= p2_max
                )
        # 不可行区域设为NaN（显示为空白）
        Z_show = Z.copy().astype(float)
        Z_show[~feasible_mask_2d] = np.nan

    fig_surf = go.Figure()
    fig_surf.add_trace(go.Heatmap(
        z=Z_show,
        x=yaw1_grid, y=yaw2_grid,
        colorscale="Viridis",
        colorbar=dict(title=dict(text="总功率 (kW)", side="right"),
                      thickness=15),
        hovertemplate="yaw1=%{x:.1f}°<br>yaw2=%{y:.1f}°<br>"
                      "总功率=%{z:.0f}kW<extra></extra>"
    ))

    # 目标功率等值线
    fig_surf.add_trace(go.Contour(
        z=Z, x=yaw1_grid, y=yaw2_grid,
        contours=dict(
            type="constraint",
            value=target_power,
            operation="=",
            showlabels=True,
            labelfont=dict(color="#e74c3c", size=11)
        ),
        line=dict(color="#e74c3c", width=2, dash="dash"),
        showscale=False, name=f"目标 {target_power:.0f} kW"
    ))

    # 最优点
    fig_surf.add_trace(go.Scatter(
        x=[best_y1], y=[best_y2],
        mode="markers",
        marker=dict(size=16, color="#27ae60",
                    symbol="star",
                    line=dict(color="white", width=2)),
        name=f"推荐方案 ({best_y1:+.1f}°, {best_y2:+.1f}°)"
    ))

    fig_surf.update_layout(
        xaxis=dict(title="上游风机偏航角 γ₁ (°)",
                   **GRID_STYLE, **AXIS_COLOR),
        yaxis=dict(title="下游风机偏航角 γ₂ (°)",
                   **GRID_STYLE, **AXIS_COLOR),
        height=420,
        margin=dict(l=10, r=70, t=20, b=50),
        **PLOT_THEME,
        legend=dict(orientation="h", y=-0.18, x=0,
                    font=dict(size=11), bgcolor="rgba(0,0,0,0)")
    )
    st.plotly_chart(fig_surf, use_container_width=True)
    download_plotly(fig_surf, "power_surface_2d.html", "📥 下载功率曲面图")

with col_right:
    # 仪表盘
    st.markdown("#### 🎯 功率跟踪仪表")
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=actual_power,
        delta=dict(reference=target_power,
                   valueformat=".0f", suffix=" kW",
                   increasing=dict(color="#27ae60"),
                   decreasing=dict(color="#e74c3c")),
        gauge=dict(
            axis=dict(range=[0, p_max * 1.1],
                      tickcolor="#8899bb",
                      tickfont=dict(color="#8899bb", size=10)),
            bar=dict(color="#4a9eff"),
            bgcolor="#1e2d4a",
            bordercolor="#1e2d4a",
            steps=[
                dict(range=[0, p_min],
                     color="rgba(230,126,34,0.15)"),
                dict(range=[p_min, p_max],
                     color="rgba(39,174,96,0.08)"),
            ],
            threshold=dict(
                line=dict(color="#e74c3c", width=3),
                thickness=0.85, value=target_power
            )
        ),
        number=dict(suffix=" kW",
                    font=dict(color="#e8edf5", size=26)),
        title=dict(
            text=f"实际输出功率<br>"
                 f"<span style='font-size:12px;color:#8899bb'>"
                 f"目标：{target_power:.0f} kW  误差：{err_pct:.2f}%</span>",
            font=dict(color="#e8edf5", size=13)
        )
    ))
    fig_gauge.update_layout(
        height=250, margin=dict(l=20, r=20, t=20, b=10),
        **PLOT_THEME
    )
    st.plotly_chart(fig_gauge, use_container_width=True)

    # 单机约束状态
    st.markdown("#### 🔒 单机功率约束状态")
    fig_bar = go.Figure()
    for turbine, p_val, p_lo, p_hi, color in [
        ("风机1 P₁", best_p1, p1_min, p1_max, "#4a9eff"),
        ("风机2 P₂", best_p2, p2_min, p2_max, "#27ae60"),
    ]:
        ok = p_lo <= p_val <= p_hi
        r, g, b = int(color[1:3],16), int(color[3:5],16), int(color[5:7],16)
        fig_bar.add_trace(go.Bar(
            x=[turbine], y=[p_hi - p_lo], base=[p_lo],
            marker_color=f"rgba({r},{g},{b},0.15)",
            marker_line=dict(color=color, width=1.5),
            showlegend=False
        ))
        fig_bar.add_trace(go.Bar(
            x=[turbine], y=[p_val],
            marker_color=color if ok else "#e74c3c",
            text=[f"{p_val:.0f} kW {'✅' if ok else '❌'}"],
            textposition="outside",
            textfont=dict(color="#e8edf5", size=11),
            showlegend=False
        ))
    fig_bar.update_layout(
        barmode="overlay",
        xaxis=dict(color="#8899bb", showgrid=False),
        yaxis=dict(title="功率 (kW)", **GRID_STYLE, **AXIS_COLOR,
                   range=[0, P_RATED * 1.15]),
        height=200,
        margin=dict(l=10, r=10, t=15, b=40),
        **PLOT_THEME
    )
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ===== 多风速可行域 =====
st.markdown("#### 🌐 多风速下的约束可行域")
with st.spinner("计算多风速可行域..."):
    U_levels = [6.0, 8.0, 10.0, 12.0]
    p_ranges = []
    for U in U_levels:
        feas = []
        for y in np.linspace(-30, 30, 60):
            p1, p2 = predict_power_2d(y, 0, U)
            if p1_min <= p1 <= p1_max and p2_min <= p2 <= p2_max:
                feas.append(p1 + p2)
        p_ranges.append((min(feas) if feas else None,
                         max(feas) if feas else None))

fig_range = go.Figure()
for U, (p_lo, p_hi) in zip(U_levels, p_ranges):
    if p_lo is None:
        continue
    fig_range.add_trace(go.Bar(
        x=[f"{U:.0f} m/s"], y=[p_hi - p_lo], base=[p_lo],
        marker_color="rgba(74,158,255,0.5)",
        marker_line=dict(color="#4a9eff", width=1.5),
        text=[f"{p_lo:.0f}~{p_hi:.0f} kW"],
        textposition="inside",
        textfont=dict(color="white", size=11),
        showlegend=False
    ))
fig_range.add_hline(
    y=target_power, line_dash="dash",
    line_color="#e74c3c", line_width=1.5,
    annotation_text=f"目标 {target_power:.0f} kW",
    annotation_font=dict(color="#e74c3c", size=11)
)
fig_range.update_layout(
    xaxis=dict(title="来流风速", color="#8899bb", showgrid=False),
    yaxis=dict(title="功率 (kW)", **GRID_STYLE, **AXIS_COLOR),
    height=250,
    margin=dict(l=10, r=10, t=20, b=50),
    **PLOT_THEME
)
st.plotly_chart(fig_range, use_container_width=True)
download_plotly(fig_range, "power_feasible_range.html", "📥 下载可行域图")

st.divider()

# ===== 接口预留 =====
with st.expander("🔗 控制组接口预留说明"):
    st.markdown("**控制组需要提供的接口格式：**")
    st.code("""
def find_yaw_for_target(target_power, U_inf,
                         p1_min, p1_max,
                         p2_min, p2_max,
                         n_search=60):
    # 输入：目标功率(kW)，风速(m/s)，各风机功率约束(kW)
    # 输出：yaw1(°), yaw2(°), actual_power(kW),
    #        error_pct(%), feasible(bool)
    ...
    return yaw1, yaw2, actual_power, error_pct, feasible
""", language="python")
    st.markdown("将此函数放入 `surrogate_model.py` 覆盖同名函数，本页面无需修改。")

# ===== 数据导出 =====
st.divider()
st.markdown("#### 📥 数据导出")
df_export = pd.DataFrame({
    "yaw1(°)":    [best_y1],
    "yaw2(°)":    [best_y2],
    "目标功率(kW)": [target_power],
    "实际功率(kW)": [actual_power],
    "误差(%)":     [err_pct],
    "风机1(kW)":   [best_p1],
    "风机2(kW)":   [best_p2],
    "风速(m/s)":   [U_input],
})
download_csv(df_export, "power_tracking_result.csv", "📥 下载跟踪结果")