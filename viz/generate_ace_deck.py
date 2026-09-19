#!/usr/bin/env python3
"""
制作单页超级王牌大图演示文稿: 王牌PPT.pptx (完全去 AI 化 · 顶尖学术/工科竞赛挑战杯级排版)
规范: 瑞士国际主义工科排版 (Swiss Style / Vignelli / Tufte)
特点:
1. 彻底剔除浮动大圆角卡片、毛玻璃灰框、Emoji 图标等 AI 模板痕迹
2. 采用真实 FLORIS 2D 阵列流场云图 (包含真实偏航角倾斜叶轮面与物理流线)
3. 采用 Nature/IEEE 规范的三线表与阶梯能量瀑布柱状图
4. 严格 1.3 倍行距，精细无衬线与工程排版
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from pathlib import Path
import numpy as np
import matplotlib
import matplotlib.pyplot as plt

BASE_DIR = Path("/home/user/wind_farm_viz")
OUT_PATH = BASE_DIR / "王牌PPT.pptx"

def generate_figures():
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Liberation Sans']
    plt.rcParams['axes.unicode_minus'] = False

    base = np.load(BASE_DIR / 'fields_array/baseline.npz')
    ind = np.load(BASE_DIR / 'fields_array/independent.npz')

    x = base['x']
    y = base['y']
    u_base = base['u']
    u_ind = ind['u']

    D = 126.0
    rows_x = [0.0, 5.0 * D, 10.0 * D]
    cols_y = [-3.0 * D, 0.0, 3.0 * D]

    # 图 1: 上下对比流场 (IEEE/Nature 严谨学术英标)
    fig, axes = plt.subplots(2, 1, figsize=(9.2, 5.4), dpi=300, sharex=True, sharey=True)
    levels = np.linspace(2.5, 8.2, 58)
    cmap = 'cividis'

    cs0 = axes[0].contourf(x / D, y / D, u_base, levels=levels, cmap=cmap, extend='both')
    axes[0].set_title('(a) Baseline Configuration (All Turbines Yaw = 0°, Total Power = 8095.15 kW)', fontsize=10, fontweight='bold', pad=6, loc='left', color='#0F172A')
    axes[0].set_ylabel('Lateral y / D', fontsize=9, color='#334155', fontweight='bold')

    cs1 = axes[1].contourf(x / D, y / D, u_ind, levels=levels, cmap=cmap, extend='both')
    axes[1].set_title('(b) Optimal Multi-Turbine Steering (γ = [+30°, +20°, 0°], Total = 10041.46 kW, +24.04%)', fontsize=10, fontweight='bold', pad=6, loc='left', color='#0F172A')
    axes[1].set_xlabel('Streamwise Distance x / D', fontsize=9, color='#334155', fontweight='bold')
    axes[1].set_ylabel('Lateral y / D', fontsize=9, color='#334155', fontweight='bold')

    yaws_base = [0, 0, 0]
    yaws_ind = [30, 20, 0]

    for ax_idx, (ax, yaws) in enumerate(zip(axes, [yaws_base, yaws_ind])):
        ax.set_facecolor('#0F172A')
        for r_i, rx in enumerate(rows_x):
            yaw = yaws[r_i]
            yaw_rad = np.radians(yaw)
            R = 0.5
            dx = - R * np.sin(yaw_rad)
            dy =   R * np.cos(yaw_rad)
            
            for c_i, cy in enumerate(cols_y):
                cx_D = rx / D
                cy_D = cy / D
                ax.plot([cx_D - dx, cx_D + dx], [cy_D - dy, cy_D + dy], color='#FFFFFF', lw=2.8, solid_capstyle='round', zorder=5)
                ax.plot(cx_D, cy_D, marker='o', markersize=3.5, color='#38BDF8', zorder=6)
                t_id = r_i * 3 + c_i + 1
                ax.text(cx_D - 0.38, cy_D + 0.52, f'T{t_id}', color='#F8FAFC', fontsize=7.5, fontweight='bold', zorder=7)
                    
        ax.set_xlim(-1.5, 12.0)
        ax.set_ylim(-4.5, 4.5)
        ax.grid(True, linestyle=':', alpha=0.35, color='#94A3B8')

    # 物理标注
    axes[0].annotate('Full-Wake Superposition\nVelocity Deficit > 55%', xy=(5.0, 0.0), xytext=(3.5, 2.2),
                     arrowprops=dict(arrowstyle='->', color='#F87171', lw=1.2),
                     fontsize=8, fontweight='bold', color='#FEE2E2',
                     bbox=dict(boxstyle='square,pad=0.25', facecolor='#0F172A', edgecolor='#F87171', alpha=0.85))

    axes[1].annotate('Upstream +30° Deflection\nWakes Shifted Upward', xy=(1.5, 1.2), xytext=(1.5, 2.4),
                     arrowprops=dict(arrowstyle='->', color='#38BDF8', lw=1.2),
                     fontsize=8, fontweight='bold', color='#E0F2FE',
                     bbox=dict(boxstyle='square,pad=0.25', facecolor='#0F172A', edgecolor='#38BDF8', alpha=0.85))

    axes[1].annotate('Secondary Deflection +20°\nCorridor Cleared', xy=(6.5, 1.0), xytext=(6.2, 2.4),
                     arrowprops=dict(arrowstyle='->', color='#38BDF8', lw=1.2),
                     fontsize=8, fontweight='bold', color='#E0F2FE',
                     bbox=dict(boxstyle='square,pad=0.25', facecolor='#0F172A', edgecolor='#38BDF8', alpha=0.85))

    axes[1].annotate('Row 3 Clean Inflow\nPower +112.5%', xy=(10.0, 0.0), xytext=(8.8, -2.6),
                     arrowprops=dict(arrowstyle='->', color='#4ADE80', lw=1.2),
                     fontsize=8, fontweight='bold', color='#DCFCE7',
                     bbox=dict(boxstyle='square,pad=0.25', facecolor='#0F172A', edgecolor='#4ADE80', alpha=0.85))

    cbar_ax = fig.add_axes([0.915, 0.15, 0.016, 0.7])
    cbar = fig.colorbar(cs1, cax=cbar_ax)
    cbar.set_label('Hub-Height Velocity u (m/s)', fontsize=8.5, color='#334155', labelpad=6)
    cbar.ax.tick_params(labelsize=8)

    plt.subplots_adjust(left=0.07, right=0.895, top=0.92, bottom=0.11, hspace=0.32)
    fig_cfd_path = BASE_DIR / 'scientific_cfd_fig.png'
    plt.savefig(fig_cfd_path, dpi=300)
    plt.close()

    # 图 2: 逐排能量账本柱状图
    fig, ax = plt.subplots(figsize=(5.0, 2.5), dpi=300)
    rows = ['Row 1\n(Upstream)', 'Row 2\n(Midstream)', 'Row 3\n(Downstream)', 'Total Farm\n(3×3 Array)']
    b_pwr = [5262, 1309, 1522, 8095]
    o_pwr = [4020, 2787, 3234, 10041]
    deltas = [-1242, 1478, 1712, 1946]
    pcts = ['-23.6%', '+112.9%', '+112.5%', '+24.04%']

    x_idx = np.arange(len(rows))
    w = 0.35
    ax.bar(x_idx - w/2, b_pwr, w, label='Baseline (0° Yaw)', color='#CBD5E1', edgecolor='#94A3B8', lw=0.8)
    rects = ax.bar(x_idx + w/2, o_pwr, w, label='Collaborative Yaw', color=['#FCA5A5', '#7DD3FC', '#86EFAC', '#FDE047'], edgecolor='#475569', lw=0.8)

    for i, rect in enumerate(rects):
        h = rect.get_height()
        sign = '+' if deltas[i] > 0 else ''
        ax.annotate(f'{sign}{deltas[i]} kW\n({pcts[i]})',
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords='offset points',
                    ha='center', va='bottom', fontsize=6.8, fontweight='bold',
                    color='#991B1B' if deltas[i] < 0 else ('#166534' if i < 3 else '#854D0E'))

    ax.set_ylabel('Power Output (kW)', fontsize=8, fontweight='bold', color='#1E293B')
    ax.set_xticks(x_idx)
    ax.set_xticklabels(rows, fontsize=7.5, fontweight='bold', color='#334155')
    ax.legend(frameon=False, fontsize=7.2, loc='upper left')
    ax.grid(axis='y', linestyle=':', alpha=0.4, color='#94A3B8')
    ax.set_ylim(0, 11900)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    fig_bar_path = BASE_DIR / 'scientific_bar_fig.png'
    plt.savefig(fig_bar_path, dpi=300)
    plt.close()

    return fig_cfd_path, fig_bar_path

def build_ace_presentation():
    fig_cfd, fig_bar = generate_figures()

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # 1. 干净极简浅灰白学术背景 (消除刺眼白与模板质感)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
    bg.fill.solid(); bg.fill.fore_color.rgb = RGBColor(248, 249, 250); bg.line.fill.background()

    # 顶部工科深蓝 2px 结构顶线
    top_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(0.4), Inches(12.133), Inches(0.025))
    top_line.fill.solid(); top_line.fill.fore_color.rgb = RGBColor(30, 58, 138); top_line.line.fill.background()

    # 2. 页面导航与核心标题区 (严格无 Emoji, 无圆角泡泡)
    tb_tag = slide.shapes.add_textbox(Inches(0.6), Inches(0.48), Inches(6.0), Inches(0.3))
    p = tb_tag.text_frame.paragraphs[0]
    p.text = "08 / ARRAY TOPOLOGY · MULTI-TURBINE COLLABORATIVE WAKE STEERING"
    p.font.size = Pt(9.5); p.font.bold = True; p.font.color.rgb = RGBColor(30, 58, 138); p.font.name = "Arial"
    p.line_spacing = 1.3

    # 右上角关键指标大字报 (学术角标)
    tb_badge = slide.shapes.add_textbox(Inches(9.2), Inches(0.44), Inches(3.533), Inches(0.4))
    p = tb_badge.text_frame.paragraphs[0]
    p.text = "全场净增益: +24.04% (+1946.3 kW)"
    p.font.size = Pt(13); p.font.bold = True; p.font.color.rgb = RGBColor(21, 128, 61); p.font.name = "Microsoft YaHei"
    p.alignment = PP_ALIGN.RIGHT; p.line_spacing = 1.3

    # 主标题
    tb_title = slide.shapes.add_textbox(Inches(0.6), Inches(0.78), Inches(11.0), Inches(0.45))
    p = tb_title.text_frame.paragraphs[0]
    p.text = "3×3 九机阵列阶梯协同偏航全景拓扑与能量倍增解析"
    p.font.size = Pt(20); p.font.bold = True; p.font.color.rgb = RGBColor(15, 23, 42); p.font.name = "Microsoft YaHei"
    p.line_spacing = 1.3

    # 副标题（物理机理解释链条）
    tb_sub = slide.shapes.add_textbox(Inches(0.6), Inches(1.24), Inches(12.133), Inches(0.35))
    p = tb_sub.text_frame.paragraphs[0]
    p.text = "物理机理：前排偏航 +30° 开启主通道 → 中排偏航 +20° 二次导流借道穿行 → 后排 0° 迎风满发，打通全场气动流动瓶颈"
    p.font.size = Pt(11); p.font.color.rgb = RGBColor(71, 85, 105); p.font.name = "Microsoft YaHei"
    p.line_spacing = 1.3

    # 3. 左右非对称工科栅格分割 (左 7.0 英寸: 流场真实仿真图; 右 4.9 英寸: 科学数据与优化求解)
    pic_cfd = slide.shapes.add_picture(str(fig_cfd), Inches(0.6), Inches(1.65), width=Inches(7.1))

    # 左栏下方学术说明条 (纯结构，无圆角卡片)
    tb_cfd_note = slide.shapes.add_textbox(Inches(0.6), Inches(5.95), Inches(7.1), Inches(1.0))
    tf = tb_cfd_note.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "【阵列几何与流场特征】顺风间距 5D (630 m)，横向间距 3D (378 m)。基准状态下中下游机组遭受强尾流双重叠加，轮毂风速由 8.0 m/s 衰减至 3.6 m/s；阶梯偏航 [30°, 20°, 0°] 将前中排高亏损尾流核心精准偏转至列间空隙，实现后排机组迎风风速恢复至 7.2 m/s。"
    p.font.size = Pt(9.5); p.font.color.rgb = RGBColor(51, 65, 85); p.font.name = "Microsoft YaHei"; p.line_spacing = 1.3

    # -----------------------------------------------------------------
    # 右栏：学术三线表 + 能量阶梯柱状图 + 优化器参数
    # -----------------------------------------------------------------
    # 右栏 1: 3×3 机组出力三线表 (Nature/IEEE 规范学术表格)
    tb_tbl_title = slide.shapes.add_textbox(Inches(7.9), Inches(1.60), Inches(4.8), Inches(0.28))
    p = tb_tbl_title.text_frame.paragraphs[0]
    p.text = "表 1. 3×3 九机阵列单机功率分布与排级出力汇总 (kW)"
    p.font.size = Pt(9.5); p.font.bold = True; p.font.color.rgb = RGBColor(15, 23, 42); p.font.name = "Microsoft YaHei"

    tbl_shape = slide.shapes.add_table(4, 5, Inches(7.9), Inches(1.92), Inches(4.83), Inches(1.4))
    tbl = tbl_shape.table
    tbl.columns[0].width = Inches(1.23)
    tbl.columns[1].width = Inches(0.9)
    tbl.columns[2].width = Inches(0.9)
    tbl.columns[3].width = Inches(0.9)
    tbl.columns[4].width = Inches(0.9)

    headers = ["机组阵列", "Col 1", "Col 2", "Col 3", "排级合计"]
    data = [
        ["Row 1 (30°)", "1340 kW", "1340 kW", "1340 kW", "4020 kW"],
        ["Row 2 (20°)", " 909 kW", " 935 kW", " 943 kW", "2787 kW"],
        ["Row 3 ( 0°)", "1060 kW", "1088 kW", "1086 kW", "3234 kW"],
    ]

    for c_i, h in enumerate(headers):
        cell = tbl.cell(0, c_i)
        cell.text = h
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(8.5); p.font.bold = True; p.font.color.rgb = RGBColor(15, 23, 42); p.alignment = PP_ALIGN.CENTER

    for r_i, row in enumerate(data):
        for c_i, val in enumerate(row):
            cell = tbl.cell(r_i + 1, c_i)
            cell.text = val
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(8); p.alignment = PP_ALIGN.CENTER
            if c_i == 0 or c_i == 4:
                p.font.bold = True
                p.font.color.rgb = RGBColor(15, 23, 42)
            else:
                p.font.color.rgb = RGBColor(51, 65, 85)

    # 右栏 2: 逐排能量阶梯柱状图
    pic_bar = slide.shapes.add_picture(str(fig_bar), Inches(7.9), Inches(3.40), width=Inches(4.83))

    # 右栏 3: 优化求解数学公式与工程收敛特性
    tb_solver = slide.shapes.add_textbox(Inches(7.9), Inches(5.60), Inches(4.83), Inches(1.35))
    tf = tb_solver.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "【优化模型与求解收敛】"
    p.font.size = Pt(9.5); p.font.bold = True; p.font.color.rgb = RGBColor(30, 58, 138); p.font.name = "Microsoft YaHei"; p.line_spacing = 1.3
    
    p2 = tf.add_paragraph()
    p2.text = "• 目标函数：max_γ ∑ P_i(γ_1, γ_2, γ_3)，γ_i ∈ [-30°, +30°]\n• 寻优结果：最优偏航向量 γ* = [30.0°, 20.0°, 0.0°]\n• 算法特性：FLORIS GCH + 逐排贪心搜索，单次评估耗时 < 1.5 ms\n• 能量重构：后排出力占比由基准的 18.8% 跃升至 32.2%，实现全场最优功率跃迁。"
    p2.font.size = Pt(8.5); p2.font.color.rgb = RGBColor(51, 65, 85); p2.font.name = "Microsoft YaHei"; p2.line_spacing = 1.3

    prs.save(str(OUT_PATH))
    print(f"✅ 成功生成全新学术级无 AI 味王牌文稿: {OUT_PATH} ({OUT_PATH.stat().st_size} 字节)")

if __name__ == "__main__":
    build_ace_presentation()
