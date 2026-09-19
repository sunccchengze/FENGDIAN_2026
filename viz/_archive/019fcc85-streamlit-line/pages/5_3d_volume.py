import streamlit as st
import numpy as np
import plotly.graph_objects as go
import os

st.set_page_config(page_title="3D体渲染", page_icon="🫧", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #080d1a; }
[data-testid="stSidebar"] { background-color: #0d1526; }
[data-testid="stSidebar"] * { color: #e8edf5 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("## 🫧 三维尾流体渲染")
st.divider()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@st.cache_data
def load_3d(yaw):
    filename = f"yaw_{yaw:+03d}.npz"
    path = os.path.join(BASE, "fields_3d", filename)
    if os.path.exists(path):
        d = np.load(path)
        return d["x"], d["y"], d["z"], d["u"]
    return None, None, None, None

# ===== 侧边栏 =====
with st.sidebar:
    st.markdown("## ⚙️ 渲染设置")
    st.divider()

    yaw_select = st.select_slider(
        "偏航角 (°)",
        options=[-30, -15, 0, 15, 30],
        value=0
    )

    st.divider()
    st.markdown("**尾流显示阈值**")
    st.markdown("低于此风速的区域显示为尾流泡")
    threshold = st.slider(
        "风速阈值 (m/s)",
        min_value=5.0, max_value=8.0,
        value=6.5, step=0.1
    )

    st.divider()
    opacity = st.slider(
        "尾流透明度",
        min_value=0.1, max_value=1.0,
        value=0.4, step=0.05
    )

    show_turbines = st.checkbox("显示风机", value=True)
    show_slices   = st.checkbox("显示截面", value=True)

# ===== 读取数据 =====
x, y, z, U = load_3d(yaw_select)

if U is None:
    st.error("找不到三维数据，请先运行 generate_3d_data.py")
    st.stop()

# U 的形状是 (n_z, n_y, n_x) = (9, 32, 64)
# Plotly Isosurface 需要展开成一维
X_grid, Y_grid, Z_grid = np.meshgrid(x, y, z, indexing="ij")
# 转置U让维度对应 (n_x, n_y, n_z)
U_plot = U.transpose(2, 1, 0)

x_flat = X_grid.flatten()
y_flat = Y_grid.flatten()
z_flat = Z_grid.flatten()
u_flat = U_plot.flatten()

fig = go.Figure()

# ===== 尾流泡：Isosurface =====
fig.add_trace(go.Isosurface(
    x=x_flat,
    y=y_flat,
    z=z_flat,
    value=u_flat,
    isomin=4.0,
    isomax=threshold,
    surface_count=3,        # 3个等值面，形成层次感
    colorscale="Blues_r",
    showscale=True,
    colorbar=dict(
        title="风速 (m/s)",
        thickness=15,
        len=0.6,
        x=1.02
    ),
    opacity=opacity,
    caps=dict(x_show=False, y_show=False, z_show=False),
    name="尾流区"
))

# ===== 截面：轮毂高度水平切面 =====
if show_slices:
    hub_z_idx = np.argmin(np.abs(z - 90))
    U_hub = U[hub_z_idx, :, :]   # shape (32, 64)
    X2d, Y2d = np.meshgrid(x, y)

    fig.add_trace(go.Surface(
        x=X2d, y=Y2d,
        z=np.full_like(X2d, float(z[hub_z_idx])),
        surfacecolor=U_hub,
        colorscale="RdBu_r",
        cmin=4, cmax=9,
        showscale=False,
        opacity=0.6,
        name=f"轮毂高度截面 ({z[hub_z_idx]:.0f}m)"
    ))

# ===== 风机几何 =====
if show_turbines:
    for tx, label in zip([0, 630], ["风机1", "风机2"]):
        # 塔筒（垂直线）
        fig.add_trace(go.Scatter3d(
            x=[tx, tx], y=[0, 0], z=[0, 90],
            mode="lines",
            line=dict(color="white", width=4),
            showlegend=False
        ))
        # 转子扫掠面（圆形近似，用散点画圆）
        theta = np.linspace(0, 2 * np.pi, 60)
        rotor_y = 63 * np.sin(theta)
        rotor_z = 90 + 63 * np.cos(theta)
        fig.add_trace(go.Scatter3d(
            x=np.full(60, float(tx)),
            y=rotor_y,
            z=rotor_z,
            mode="lines",
            line=dict(color="white", width=2),
            showlegend=False
        ))
        # 标签
        fig.add_trace(go.Scatter3d(
            x=[tx], y=[0], z=[170],
            mode="text",
            text=[label],
            textfont=dict(color="white", size=12),
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
            title="高度 z (m)",
            backgroundcolor="#080d1a",
            gridcolor="#1e2d4a",
            showbackground=True,
            color="#8899bb",
            range=[0, 200]
        ),
        bgcolor="#080d1a",
        aspectmode="manual",
        aspectratio=dict(x=3, y=3, z=1),
        camera=dict(
            eye=dict(x=-1.8, y=-1.5, z=0.8)
        )
    ),
    title=dict(
        text=f"三维尾流体渲染  |  偏航角 = {yaw_select:+.0f}°  "
             f"|  显示风速 < {threshold} m/s 的尾流区域",
        font=dict(color="#e8edf5", size=14),
        x=0.5
    ),
    height=650,
    margin=dict(l=0, r=0, t=60, b=0),
    paper_bgcolor="#080d1a",
    font=dict(color="#e8edf5")
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("""
<div style="color:#8899bb; font-size:13px; text-align:center;">
    💡 蓝色半透明区域为尾流低速泡，白色圆圈为风机转子扫掠面
    &nbsp;｜&nbsp; 鼠标拖拽旋转，滚轮缩放，双击重置
</div>
""", unsafe_allow_html=True)
