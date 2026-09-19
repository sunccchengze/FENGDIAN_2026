import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import DARK_CSS, PLOT_THEME, GRID_STYLE, AXIS_COLOR, download_plotly, download_csv

st.set_page_config(page_title="阵列优化", page_icon="⚡", layout="wide")
st.markdown(DARK_CSS, unsafe_allow_html=True)

st.markdown("## ⚡ 3×3 风机阵列协同优化")
st.caption("统一偏航 vs 逐排独立优化 · 协同控制效果对比")
st.divider()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@st.cache_data
def load_data():
    df = pd.read_csv(os.path.join(BASE, "cases_array.csv"))
    with open(os.path.join(BASE, "array_independent_result.json")) as f:
        result = json.load(f)
    df2 = pd.read_csv(os.path.join(BASE, "cases.csv"))
    df2["power_total"] = df2["power_1"] + df2["power_2"]
    return df, result, df2

with st.spinner("加载阵列数据..."):
    df, result, df2 = load_data()

baseline = df[df["yaw_upstream"] == 0]["power_total"].values[0]
best_row  = df.loc[df["power_total"].idxmax()]

# ===== 侧边栏 =====
with st.sidebar:
    st.markdown("## ⚙️ 参数设置")
    st.divider()

    strategy = st.radio(
        "控制策略",
        ["统一偏航（可调）", "逐排独立优化（最优）"],
        index=0
    )

    if strategy == "统一偏航（可调）":
        yaw_select = st.select_slider(
            "上游统一偏航角 (°)",
            options=sorted(df["yaw_upstream"].astype(int).tolist()),
            value=0
        )

    st.divider()
    st.markdown("**📐 阵列参数**")
    st.markdown("""
- 布局：**3×3 九台风机**
- 顺风间距：**5D = 630 m**
- 横向间距：**3D = 378 m**
    """)
    st.divider()
    st.markdown("**🏆 各策略最优结果**")
    st.markdown(f"""
- 无偏航基准：**{result['power_none']:.0f} kW**
- 统一偏航最优：**{result['power_unified']:.0f} kW**（+{result['gain_unified_pct']:.1f}%）
- 逐排独立最优：**{result['power_independent']:.0f} kW**（+{result['gain_independent_pct']:.1f}%）
    """)

# ===== 确定当前工况 =====
if strategy == "统一偏航（可调）":
    row      = df[df["yaw_upstream"] == yaw_select].iloc[0]
    p_total  = row["power_total"]
    gain_pct = row["gain_pct"]
    powers   = [row[f"power_{i+1}"] for i in range(9)]
    yaw_list = [yaw_select] * 3 + [0] * 6
else:
    p_total  = result["power_independent"]
    gain_pct = result["gain_independent_pct"]
    powers   = result["turbine_powers_independent"]
    yaw_list = result["greedy_yaws"]

# ===== 顶部指标 =====
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("控制策略",
          "统一偏航" if strategy == "统一偏航（可调）" else "逐排独立")
c2.metric("总功率",
          f"{p_total:.0f} kW",
          delta=f"{p_total - baseline:+.0f} kW vs 无偏航")
c3.metric("功率增益", f"{gain_pct:+.1f}%")
c4.metric("统一偏航增益", f"+{result['gain_unified_pct']:.1f}%")
c5.metric("独立优化增益", f"+{result['gain_independent_pct']:.1f}%")

st.markdown("<br>", unsafe_allow_html=True)

# ===== 策略说明 =====
if strategy == "逐排独立优化（最优）":
    st.markdown(f"""
    <div style="
        background: rgba(39,174,96,0.08);
        border: 1px solid rgba(39,174,96,0.25);
        border-radius: 12px;
        padding: 14px 20px;
        margin-bottom: 16px;
    ">
        <div style="color:#27ae60; font-size:12px; font-weight:700;
                    letter-spacing:1px; margin-bottom:8px;">
            🏆 逐排独立优化策略说明
        </div>
        <div style="color:rgba(168,188,223,0.85); font-size:12px; line-height:1.7;">
            各排最优偏航角：
            第1排 <b style="color:#e8edf5">{result['greedy_row_yaws'][0]:+.0f}°</b> →
            第2排 <b style="color:#e8edf5">{result['greedy_row_yaws'][1]:+.0f}°</b> →
            第3排 <b style="color:#e8edf5">{result['greedy_row_yaws'][2]:+.0f}°</b><br>
            第2排偏航将尾流进一步推离第3排；第3排偏航0°因其下游无风机，偏航只会损失自身功率。
            这正是<b style="color:#27ae60">协同控制</b>优于统一偏航的根本原因。
        </div>
    </div>
    """, unsafe_allow_html=True)

# ===== 主图区 =====
col_layout, col_curves = st.columns([3, 2])

with col_layout:
    st.markdown("#### 🗺️ 风机阵列功率分布图")

    D = 126.0
    layout_x = [row_i * 5 * D for row_i in range(3) for col_i in range(3)]
    layout_y  = [(col_i - 1) * 3 * D for row_i in range(3) for col_i in range(3)]

    p_max = max(powers)
    p_min = min(powers)

    fig_layout = go.Figure()

    # 尾流方向示意
    for i in range(9):
        yaw_rad = np.radians(yaw_list[i])
        tx, ty  = layout_x[i], layout_y[i]
        dx = 350 * np.cos(yaw_rad)
        dy = 350 * np.sin(yaw_rad)
        fig_layout.add_trace(go.Scatter(
            x=[tx, tx + dx], y=[ty, ty + dy],
            mode="lines",
            line=dict(color="rgba(74,158,255,0.25)", width=25),
            showlegend=False, hoverinfo="skip"
        ))

    # 风机圆圈
    for i, (tx, ty, p) in enumerate(zip(layout_x, layout_y, powers)):
        row_i  = i // 3 + 1
        col_i  = i % 3 + 1
        norm   = (p - p_min) / (p_max - p_min + 1e-6)
        r = int(74  + (230 - 74)  * (1 - norm))
        g = int(158 + (126 - 158) * (1 - norm))
        b = int(255 + (34  - 255) * (1 - norm))

        yaw_show = yaw_list[i]
        fig_layout.add_trace(go.Scatter(
            x=[tx], y=[ty],
            mode="markers+text",
            marker=dict(
                size=42,
                color=f"rgb({r},{g},{b})",
                symbol="circle",
                line=dict(color="white", width=2)
            ),
            text=[f"T{i+1}<br>{p:.0f}"],
            textposition="middle center",
            textfont=dict(size=10, color="white"),
            showlegend=False,
            hovertemplate=(
                f"<b>风机 {i+1}</b>（排{row_i}列{col_i}）<br>"
                f"偏航角：{yaw_show:+.0f}°<br>"
                f"功率：{p:.0f} kW<br>"
                "<extra></extra>"
            )
        ))

    fig_layout.add_annotation(
        x=630, y=-560, text="风向 →  来流 8 m/s",
        showarrow=False,
        font=dict(color="#8899bb", size=12)
    )
    fig_layout.update_layout(
        xaxis=dict(title="顺风方向 x (m)",
                   **GRID_STYLE, **AXIS_COLOR,
                   range=[-200, 1500]),
        yaxis=dict(title="横向 y (m)",
                   **GRID_STYLE, **AXIS_COLOR,
                   range=[-600, 600],
                   scaleanchor="x", scaleratio=1),
        height=460,
        margin=dict(l=10, r=10, t=20, b=50),
        **PLOT_THEME, showlegend=False
    )
    st.plotly_chart(fig_layout, use_container_width=True)
    st.caption("圆圈颜色：蓝=高功率 橙=低功率 | 蓝色光晕=尾流偏转方向 | 悬停查看详情")
    download_plotly(fig_layout, "array_layout.html", "📥 下载布局图")

with col_curves:
    st.markdown("#### 📊 三种策略功率对比")
    strategies = ["无偏航\n（基准）",
                  f"统一偏航\n（{result['unified_yaw']:+.0f}°）",
                  "逐排独立\n优化"]
    s_powers   = [result["power_none"],
                  result["power_unified"],
                  result["power_independent"]]
    s_gains    = [0,
                  result["gain_unified_pct"],
                  result["gain_independent_pct"]]
    s_colors   = ["#4a5568", "#4a9eff", "#27ae60"]

    fig_cmp = go.Figure()
    fig_cmp.add_trace(go.Bar(
        x=strategies, y=s_powers,
        marker_color=s_colors,
        text=[f"{p:.0f} kW\n({g:+.1f}%)"
              for p, g in zip(s_powers, s_gains)],
        textposition="outside",
        textfont=dict(color="#e8edf5", size=11)
    ))
    fig_cmp.update_layout(
        xaxis=dict(color="#8899bb", showgrid=False),
        yaxis=dict(title="总功率 (kW)",
                   **GRID_STYLE, **AXIS_COLOR,
                   range=[0, max(s_powers) * 1.18]),
        height=230,
        margin=dict(l=10, r=10, t=20, b=50),
        **PLOT_THEME, showlegend=False
    )
    st.plotly_chart(fig_cmp, use_container_width=True)
    download_plotly(fig_cmp, "array_strategy_comparison.html", "📥 下载对比图")

    st.markdown("#### 🏭 各排平均功率 (kW)")
    row1_avg = np.mean(powers[:3])
    row2_avg = np.mean(powers[3:6])
    row3_avg = np.mean(powers[6:])

    fig_rows = go.Figure()
    fig_rows.add_trace(go.Bar(
        x=["第1排（上游）", "第2排（中游）", "第3排（下游）"],
        y=[row1_avg, row2_avg, row3_avg],
        marker_color=["#4a9eff", "#27ae60", "#e67e22"],
        text=[f"{v:.0f} kW" for v in [row1_avg, row2_avg, row3_avg]],
        textposition="outside",
        textfont=dict(color="#e8edf5", size=11)
    ))
    fig_rows.update_layout(
        xaxis=dict(color="#8899bb", showgrid=False),
        yaxis=dict(title="平均功率 (kW)",
                   **GRID_STYLE, **AXIS_COLOR,
                   range=[0, max(row1_avg, row2_avg, row3_avg) * 1.2]),
        height=200,
        margin=dict(l=10, r=10, t=15, b=40),
        **PLOT_THEME, showlegend=False
    )
    st.plotly_chart(fig_rows, use_container_width=True)

st.divider()

if strategy == "统一偏航（可调）":
    st.markdown("#### 📈 总功率 vs 上游偏航角（统一偏航模式）")
    fig_total = go.Figure()
    fig_total.add_trace(go.Scatter(
        x=df["yaw_upstream"], y=df["power_total"],
        mode="lines+markers", name="总功率 (kW)",
        line=dict(color="#4a9eff", width=2.5),
        marker=dict(size=6),
        fill="tozeroy", fillcolor="rgba(74,158,255,0.06)"
    ))
    row_sel = df[df["yaw_upstream"] == yaw_select].iloc[0]
    fig_total.add_trace(go.Scatter(
        x=[yaw_select], y=[row_sel["power_total"]],
        mode="markers", name="当前",
        marker=dict(size=14, color="#e74c3c",
                    line=dict(color="white", width=2))
    ))
    fig_total.add_vline(
        x=best_row["yaw_upstream"],
        line_dash="dash", line_color="#27ae60",
        annotation_text=f"最优 {best_row['yaw_upstream']:+.0f}°",
        annotation_font=dict(color="#27ae60", size=11)
    )
    fig_total.update_layout(
        xaxis=dict(title="上游偏航角 (°)", **GRID_STYLE, **AXIS_COLOR),
        yaxis=dict(title="总功率 (kW)",    **GRID_STYLE, **AXIS_COLOR),
        height=260,
        margin=dict(l=10, r=10, t=20, b=50),
        **PLOT_THEME,
        legend=dict(orientation="h", y=-0.25, x=0,
                    font=dict(size=11), bgcolor="rgba(0,0,0,0)")
    )
    st.plotly_chart(fig_total, use_container_width=True)
    download_plotly(fig_total, "array_power_curve.html", "📥 下载功率曲线")

st.divider()

st.markdown("#### 🔥 全场功率分布热力图（偏航角 × 风机编号）")

power_matrix = np.zeros((len(df), 9))
for i, r in df.iterrows():
    for j in range(9):
        power_matrix[i, j] = r[f"power_{j+1}"]

fig_hm = go.Figure(go.Heatmap(
    z=power_matrix,
    x=[f"T{i+1}（排{i//3+1}列{i%3+1}）" for i in range(9)],
    y=[f"{y:+.0f}°" for y in df["yaw_upstream"]],
    colorscale="Viridis",
    colorbar=dict(title=dict(text="功率 (kW)", side="right"), thickness=15),
    text=[[f"{v:.0f}" for v in row] for row in power_matrix],
    texttemplate="%{text}",
    textfont=dict(size=10, color="white")
))
fig_hm.update_layout(
    xaxis=dict(title="风机编号", **AXIS_COLOR),
    yaxis=dict(title="上游统一偏航角 (°)", **AXIS_COLOR),
    height=380,
    margin=dict(l=10, r=10, t=20, b=50),
    **PLOT_THEME
)
st.plotly_chart(fig_hm, use_container_width=True)
download_plotly(fig_hm, "array_heatmap.html", "📥 下载热力图")

st.divider()

st.markdown("#### 📊 两台串列 vs 3×3 阵列：偏航控制增益对比")

base2 = df2[df2["yaw_1"] == 0]["power_total"].values[0]
df2["gain_pct"] = (df2["power_total"] - base2) / base2 * 100

fig_vs = go.Figure()
fig_vs.add_trace(go.Scatter(
    x=df2["yaw_1"], y=df2["gain_pct"],
    mode="lines+markers", name="两台串列",
    line=dict(color="#4a9eff", width=2), marker=dict(size=6)
))
fig_vs.add_trace(go.Scatter(
    x=df["yaw_upstream"], y=df["gain_pct"],
    mode="lines+markers", name="3×3 统一偏航",
    line=dict(color="#e67e22", width=2), marker=dict(size=6)
))
fig_vs.add_hline(
    y=result["gain_independent_pct"],
    line_dash="dash", line_color="#27ae60", line_width=2,
    annotation_text=f"逐排独立优化 +{result['gain_independent_pct']:.1f}%",
    annotation_position="right",
    annotation_font=dict(color="#27ae60", size=11)
)
fig_vs.add_hline(y=0, line_dash="dot",
                 line_color="#4a5568", line_width=1)
fig_vs.update_layout(
    xaxis=dict(title="上游偏航角 (°)", **GRID_STYLE, **AXIS_COLOR),
    yaxis=dict(title="功率增益 (%)",   **GRID_STYLE, **AXIS_COLOR),
    height=280,
    margin=dict(l=10, r=80, t=20, b=50),
    **PLOT_THEME,
    legend=dict(orientation="h", y=-0.25, x=0,
                font=dict(size=11), bgcolor="rgba(0,0,0,0)")
)
st.plotly_chart(fig_vs, use_container_width=True)
download_plotly(fig_vs, "array_vs_two_turbines.html", "📥 下载对比图")

st.divider()
st.markdown("#### 📥 数据导出")
col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    download_csv(df[["case_id", "yaw_upstream", "power_total", "gain_pct"]],
                 "array_unified_yaw.csv", "📥 下载统一偏航数据")
with col_dl2:
    df_indep = pd.DataFrame({
        "策略":       ["无偏航", "统一偏航", "逐排独立优化"],
        "总功率(kW)": [result["power_none"],
                       result["power_unified"],
                       result["power_independent"]],
        "增益(%)":    [0, result["gain_unified_pct"],
                       result["gain_independent_pct"]],
    })
    download_csv(df_indep, "array_strategy_comparison.csv",
                 "📥 下载策略对比数据")

# ===== 动画对比 =====
st.divider()
st.markdown("#### 🎬 统一偏航 vs 逐排独立优化 · 流场对比动画")

col_gif, col_desc = st.columns([3, 1])

with col_gif:
    gif_path = os.path.join(BASE, "array_animation.gif")
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
        st.warning("未找到 array_animation.gif，请先运行 export_array_gif.py")

with col_desc:
    st.markdown(f"""
**动画说明**

**左侧：** 上游统一偏航从 -30° 扫描至 +30° 再返回

**右侧：** 逐排独立优化三步渐进过程
1. 无偏航基准
2. 第1排 +30°
3. 完整独立优化

**关键结论：**
- 统一偏航最优：**+{result['gain_unified_pct']:.1f}%**
- 逐排独立最优：**+{result['gain_independent_pct']:.1f}%**
- 独立优化额外提升：**+{result['gain_independent_pct'] - result['gain_unified_pct']:.1f}%**
    """)