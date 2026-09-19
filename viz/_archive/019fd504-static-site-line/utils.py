# utils.py
# 全局共享工具函数：导出、加载状态、单位规范

import plotly.graph_objects as go
import streamlit as st
import pandas as pd
import io

# ===== 单位规范字典 =====
UNITS = {
    "wind_speed":   "m/s",
    "power":        "kW",
    "yaw":          "°",
    "distance":     "m",
    "velocity":     "m/s",
    "delta_v":      "Δm/s",
    "energy_frac":  "%",
    "gain":         "%",
}

def unit_label(quantity: str, name: str) -> str:
    """生成带单位的坐标轴标签"""
    u = UNITS.get(quantity, "")
    return f"{name} ({u})" if u else name

# ===== 导出 Plotly 图表为 HTML =====
def download_plotly(fig: go.Figure, filename: str, label: str = "📥 下载图表"):
    """在图表下方添加下载按钮（HTML格式，可在浏览器独立打开）"""
    html_bytes = fig.to_html(include_plotlyjs="cdn").encode("utf-8")
    st.download_button(
        label=label,
        data=html_bytes,
        file_name=filename,
        mime="text/html",
        use_container_width=False
    )

# ===== 导出 DataFrame 为 CSV =====
def download_csv(df: pd.DataFrame, filename: str, label: str = "📥 下载数据"):
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=label,
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
        use_container_width=False
    )

# ===== 全局深色主题 CSS =====
DARK_CSS = """
<style>
.stApp { background-color: #080d1a; }
[data-testid="stMetric"] {
    background-color: #111827;
    border: 1px solid #1e2d4a;
    border-radius: 12px;
    padding: 16px 20px;
}
[data-testid="stMetricLabel"] {
    font-size: 13px !important;
    color: #8899bb !important;
    font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    font-size: 22px !important;
    color: #e8edf5 !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] { background-color: #0d1526; }
[data-testid="stSidebar"] * { color: #e8edf5 !important; }
</style>
"""

PLOT_THEME = dict(
    paper_bgcolor="#111827",
    plot_bgcolor="#111827",
    font=dict(color="#e8edf5"),
)

GRID_STYLE = dict(showgrid=True, gridcolor="#1e2d4a")
AXIS_COLOR = dict(color="#8899bb")