import streamlit as st
import numpy as np
import plotly.graph_objects as go
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import DARK_CSS, PLOT_THEME, GRID_STYLE, AXIS_COLOR, download_plotly, download_csv
import pandas as pd

st.set_page_config(page_title="POD分析", page_icon="🔬", layout="wide")
st.markdown(DARK_CSS, unsafe_allow_html=True)

st.markdown("## 🔬 POD 本征正交分解分析")
st.caption("Principal Orthogonal Decomposition · 流场降阶核心技术")
st.divider()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@st.cache_data
def load_pod():
    path = os.path.join(BASE, "pod_results", "pod_data.npz")
    raw  = np.load(path)
    return {k: raw[k] for k in raw.files}

@st.cache_data
def load_cases():
    df = pd.read_csv(os.path.join(BASE, "cases.csv"))
    return df.sort_values("yaw_1").reset_index(drop=True)

with st.spinner("加载POD数据..."):
    pod = load_pod()
    df_cases = load_cases()

x            = pod["x"]
y            = pod["y"]
x_mean       = pod["x_mean"]
modes        = pod["modes"]
energy_frac  = pod["energy_frac"]
energy_cum   = pod["energy_cum"]
coefficients = pod["coefficients"]
yaw_angles   = pod["yaw_angles"]
n_snapshots  = int(pod["n_snapshots"])

# ===== 侧边栏 =====
with st.sidebar:
    st.markdown("## ⚙️ 分析设置")
    st.divider()
    k_recon = st.slider("重构使用模态数 k",
                        min_value=1, max_value=int(n_snapshots),
                        value=3, step=1)
    st.divider()
    mode_view = st.selectbox(
        "查看第几阶模态",
        options=list(range(1, min(11, n_snapshots + 1))),
        index=0
    )
    st.divider()
    snap_idx = st.selectbox(
        "对比工况",
        options=list(range(n_snapshots)),
        format_func=lambda i: f"偏航 {yaw_angles[i]:+.0f}°",
        index=6
    )

# ===== 顶部指标 =====
k_95 = int(np.searchsorted(energy_cum, 0.95)) + 1
k_99 = int(np.searchsorted(energy_cum, 0.99)) + 1

c1, c2, c3, c4 = st.columns(4)
c1.metric("快照数量",       f"{n_snapshots} 个")
c2.metric("95% 能量模态数", f"{k_95} 个")
c3.metric("99% 能量模态数", f"{k_99} 个")
c4.metric(f"前 {k_recon} 模态能量",
          f"{energy_cum[k_recon-1]*100:.2f}%")

st.markdown("<br>", unsafe_allow_html=True)

# ===== 物理解释面板 =====
st.markdown("#### 💡 POD 物理含义解读")

with st.expander("📖 POD 物理含义解读（点击展开）", expanded=True):
    st.markdown(f"""
    <style>
    .pod-grid {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 14px;
        margin: 12px 0 20px 0;
    }}
    .pod-card {{
        background: rgba(255,255,255,0.04);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 20px 18px;
        position: relative;
        overflow: hidden;
    }}
    .pod-card::before {{
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0; height: 1px;
        background: linear-gradient(90deg,
            transparent, rgba(255,255,255,0.15), transparent);
    }}
    .pod-card-icon {{
        font-size: 28px;
        margin-bottom: 10px;
    }}
    .pod-card-title {{
        font-size: 13px;
        font-weight: 700;
        color: #e8edf5;
        margin-bottom: 6px;
    }}
    .pod-card-sub {{
        font-size: 11px;
        color: #4a9eff;
        font-weight: 600;
        margin-bottom: 8px;
        letter-spacing: 0.5px;
    }}
    .pod-card-desc {{
        font-size: 12px;
        color: rgba(136,153,187,0.9);
        line-height: 1.6;
        margin: 0;
    }}
    .pod-card-stat {{
        margin-top: 12px;
        background: rgba(74,158,255,0.08);
        border: 1px solid rgba(74,158,255,0.2);
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
        font-weight: 700;
        color: #4a9eff;
        text-align: center;
    }}
    .pod-insight {{
        background: rgba(39,174,96,0.06);
        border: 1px solid rgba(39,174,96,0.2);
        border-radius: 12px;
        padding: 16px 20px;
        margin-top: 4px;
    }}
    .pod-insight-title {{
        font-size: 12px;
        font-weight: 700;
        color: #27ae60;
        letter-spacing: 1px;
        text-transform: uppercase;
        margin-bottom: 8px;
    }}
    .pod-insight-text {{
        font-size: 12px;
        color: rgba(168,188,223,0.85);
        line-height: 1.7;
        margin: 0;
    }}
    .pod-insight-text b {{
        color: #e8edf5;
    }}
    </style>

    <div class="pod-grid">
        <div class="pod-card">
            <div class="pod-card-icon">🌊</div>
            <div class="pod-card-title">模态 1</div>
            <div class="pod-card-sub">主导尾流结构</div>
            <p class="pod-card-desc">
                代表所有工况的平均尾流形态——风机后方对称的速度亏缺区。
                无论偏航角如何变化，尾流主体形状始终存在，因此能量最大。
            </p>
            <div class="pod-card-stat">能量占比 {energy_frac[0]*100:.1f}%</div>
        </div>
        <div class="pod-card">
            <div class="pod-card-icon">↔️</div>
            <div class="pod-card-title">模态 2</div>
            <div class="pod-card-sub">偏航偏转效应</div>
            <p class="pod-card-desc">
                代表偏航引起的尾流横向偏移——左右不对称的速度分布。
                这是偏航控制能提升下游功率的根本原因，也是本项目的核心物理机制。
            </p>
            <div class="pod-card-stat">能量占比 {energy_frac[1]*100:.1f}%</div>
        </div>
        <div class="pod-card">
            <div class="pod-card-icon">🌀</div>
            <div class="pod-card-title">模态 3+</div>
            <div class="pod-card-sub">高阶非线性扰动</div>
            <p class="pod-card-desc">
                代表尾流蜿蜒、湍流混合等细节效应。
                能量贡献极小，可在降阶模型中安全忽略，这正是POD高压缩比的基础。
            </p>
            <div class="pod-card-stat">累计仅占 {(energy_cum[-1] - energy_cum[1])*100:.2f}%</div>
        </div>
    </div>

    <div class="pod-insight">
        <div class="pod-insight-title">🔑 工程意义</div>
        <p class="pod-insight-text">
            仅需前 <b>2 个模态</b> 即可重构 <b>{energy_cum[1]*100:.2f}%</b> 的流场能量，
            将 <b>8192 维</b>速度场压缩为 <b>2 个 POD 系数</b>，压缩比达 <b>4096:1</b>。
            这直接证明了 POD 降阶代替高成本 CFD 的可行性，
            为申报书中"数据-物理融合驱动"技术路线提供了定量支撑。
        </p>
    </div>
    """, unsafe_allow_html=True)