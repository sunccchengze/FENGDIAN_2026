# -*- coding: utf-8 -*-
"""中期答辩 PPT 渲染（2026-10-22 v1）

严格按 docs/defense/2026-10-22_中期答辩PPT大纲.md 的 15 页（含封面）生成。
沿用 8.23 组会汇报 / 答辩证据骨架 v1 的瑞士网格皮肤：莫兰迪工科色、发丝线、零 Emoji、1.3 行距、16:9。

口径纪律（写死在代码里，改文案前先读大纲 §4）：
  - 每个数字带标签：【真值=FLORIS 4.6.6】【代理】【实测】【外部】【约定】
  - 限定语最小 11pt，不允许藏起来；
  - 外部数据统一加角标（GWEC 2026 / 国家能源局 2026 / WES 2024）。

依赖：python-pptx
用法：python3 docs/defense/generate_midterm_pptx.py
输出：docs/defense/中期答辩_v1_20261022.pptx
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
MIDTERM_IMG = REPO / "optimization_control" / "experiments" / "20261022_midterm_figures"
DEMO_IMG = REPO / "docs" / "research" / "img"
OUT = ROOT / "中期答辩_v1_20261022.pptx"

TOTAL = 15
FOOTER = "多机协同智能功率控制与数字孪生演示 · 中期检查 2026-10 | 汇报人：孙承泽 | 指导教师：李良星 副教授"

BG = RGBColor(248, 249, 250)
TXT = RGBColor(29, 32, 36)
SUB = RGBColor(73, 80, 87)
LINE = RGBColor(222, 226, 230)
LINE_DARK = RGBColor(43, 47, 51)
BLUE = RGBColor(77, 104, 132)
SAGE = RGBColor(81, 100, 71)
ROSE = RGBColor(185, 132, 132)
ROSE_DEEP = RGBColor(140, 93, 93)
WHITE = RGBColor(255, 255, 255)

SERIF = "Songti SC"
SANS = "Arial"


# ---------------------------------------------------------------- 基础件
def blank(prs, num):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = BG
    rule(slide, 0.8, 0.42, 11.73, 0.02, LINE_DARK)
    num_box = slide.shapes.add_textbox(Inches(10.9), Inches(0.5), Inches(1.63), Inches(0.3))
    p = num_box.text_frame.paragraphs[0]
    p.text = f"{num:02d} / {TOTAL - 1:02d}"
    p.alignment = PP_ALIGN.RIGHT
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = SUB
    p.font.name = SANS
    rule(slide, 0.8, 6.9, 11.73, 0.01, LINE)
    foot = slide.shapes.add_textbox(Inches(0.8), Inches(6.95), Inches(11.73), Inches(0.3))
    fp = foot.text_frame.paragraphs[0]
    fp.text = FOOTER
    fp.font.size = Pt(9)
    fp.font.color.rgb = SUB
    fp.font.name = SANS
    return slide


def rule(slide, x, y, w, h, color):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.color.rgb = color
    return shape


def box(slide, x, y, w, h, line_color=LINE, fill_color=WHITE):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.color.rgb = line_color
    return shape


def text(slide, x, y, w, h, s, size=12, bold=False, color=None, font=SERIF,
         align=PP_ALIGN.LEFT, italic=False, space=6, lspace=1.3):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(s.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.alignment = align
        p.space_before = Pt(space)
        p.line_spacing = lspace
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.italic = italic
        p.font.color.rgb = color or SUB
        p.font.name = font
    return tb


def head(slide, title, sub, lead=None):
    text(slide, 0.8, 0.52, 9.9, 0.5, title, size=20, bold=True, color=TXT, space=0)
    text(slide, 0.8, 0.95, 10.0, 0.32, sub, size=12, bold=True, color=BLUE, space=0)
    if lead:
        text(slide, 0.8, 1.3, 11.6, 0.32, lead, size=11, italic=True, color=SUB, space=0)


def bullets(slide, x, y, w, h, items, size=12, gap=7):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(gap)
        if "｜" in it:
            lead, rest = it.split("｜", 1)
            r1 = p.add_run()
            r1.text = lead
            r1.font.size = Pt(size)
            r1.font.bold = True
            r1.font.color.rgb = TXT
            r1.font.name = SERIF
            r3 = p.add_run()
            r3.text = "｜"
            r3.font.size = Pt(size)
            r3.font.color.rgb = LINE
            r3.font.name = SERIF
            r2 = p.add_run()
            r2.text = rest
            r2.font.size = Pt(size)
            r2.font.color.rgb = SUB
            r2.font.name = SERIF
        else:
            r = p.add_run()
            r.text = it
            r.font.size = Pt(size)
            r.font.color.rgb = SUB
            r.font.name = SERIF
    return tb


def big_number(slide, x, y, w, number, caption, color=BLUE, num_size=34, cap_size=10.5):
    # 数字用 0.95 行距，框高按字号推，避免 40pt 以上顶掉说明行
    h = num_size * 1.2 * 0.95 / 72
    text(slide, x, y, w, h + 0.04, number, size=num_size, bold=True, color=color,
         font=SANS, space=0, lspace=0.95)
    text(slide, x, y + h + 0.08, w, 0.5, caption, size=cap_size, color=SUB, space=2)


def table(slide, x, y, w, h, headers, rows, col_w=None, size=10.5, highlight=None):
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(x), Inches(y), Inches(w), Inches(h))
    t = shape.table
    if col_w:
        for i, cw in enumerate(col_w):
            t.columns[i].width = Inches(cw)
    for i, h in enumerate(headers):
        t.cell(0, i).text = h
    for ri, row in enumerate(rows):
        for ci, v in enumerate(row):
            t.cell(ri + 1, ci).text = str(v)
    for ri, row in enumerate(t.rows):
        for cell in row.cells:
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER
                for r in p.runs:
                    r.font.size = Pt(size)
                    r.font.name = SERIF
                    r.font.color.rgb = TXT
                    if ri == 0:
                        r.font.bold = True
                    if ri > 0 and highlight and row.cells[0].text in highlight:
                        r.font.bold = True
                        r.font.color.rgb = SAGE
    return t


def picture(slide, path, x, y, w=None, h=None):
    if not Path(path).exists():
        box(slide, x, y, w or 4, h or 3, ROSE)
        text(slide, x + 0.15, y + 0.15, (w or 4) - 0.3, 0.4, f"【缺图】{Path(path).name}", size=10, color=ROSE_DEEP)
        return
    kw = {}
    if w:
        kw["width"] = Inches(w)
    if h:
        kw["height"] = Inches(h)
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), **kw)


def strip(slide, s, y=6.28, color=ROSE, deep=ROSE_DEEP):
    b = box(slide, 0.8, y, 11.73, 0.46, color)
    tf = b.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = s
    r.font.size = Pt(10.5)
    r.font.color.rgb = deep
    r.font.name = SERIF


# ---------------------------------------------------------------- 各页
def cover(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = BG
    rule(slide, 0.9, 1.5, 0.06, 2.6, BLUE)
    text(slide, 1.2, 1.45, 10.5, 0.5, "国家级大学生创新创业训练计划 · 中期检查", size=12, bold=True, color=BLUE, space=0)
    text(slide, 1.2, 1.86, 11.0, 0.72, "多机协同智能功率控制", size=38, bold=True, color=TXT, space=0, lspace=1.0)
    text(slide, 1.2, 2.6, 11.0, 0.72, "与数字孪生演示平台", size=38, bold=True, color=TXT, space=0, lspace=1.0)
    text(slide, 1.2, 3.55, 10.8, 0.6, "从代理模型到协同控制，从数字孪生到可复现验证", size=14, color=SUB, space=0)
    rule(slide, 1.2, 4.35, 5.2, 0.01, LINE)
    text(slide, 1.2, 4.55, 11.0, 1.2,
         "汇报人：孙承泽　｜　指导教师：李良星 副教授\n"
         "团队：厉今飞（项目负责人 / AI）· 袁夫达（建模）· 田铭雨（仿真）· 洪祖名（优化控制）",
         size=11.5, color=SUB, space=5)
    text(slide, 1.2, 6.2, 6.0, 0.4, "2026 年 10 月 · 西安交通大学", size=10.5, color=SUB, space=0)
    return slide


def p1_numbers(prs):
    s = blank(prs, 1)
    head(s, "一页看懂", "四个数字，四个问题",
         "接口通没通 · 学习有没有效 · 系统稳不稳 · 结果能不能被检查")
    cards = [
        ("12 → 6", "十二维来流与控制输入 → 六维功率与有效风速输出", BLUE, "【代理】接口已通"),
        ("−58.5%", "三机功率跟踪误差 1083.62 → 449.72 kW", SAGE, "【代理】合成入口与标签"),
        ("161 / 0", "数字孪生自检 通过 / 失败", BLUE, "【实测】本仓库"),
        ("0 W", "30,720 行轨迹复算与原始记录的差值", SAGE, "【实测】可复现"),
    ]
    for i, (num, cap, color, tag) in enumerate(cards):
        x = 0.8 + (i % 2) * 5.95
        y = 1.95 + (i // 2) * 2.2
        box(s, x, y, 5.7, 1.95)
        big_number(s, x + 0.35, y + 0.28, 5.0, num, cap, color=color, num_size=40)
        text(s, x + 0.35, y + 1.55, 5.0, 0.3, tag, size=10, color=ROSE_DEEP, space=0)
    strip(s, "说明：本页四个数字分属两类口径——「代理」指合成入口与合成标签下的代理模型结果，「实测」指本仓库可当场复跑的门禁与复算。两类不得混写。")
    return s


def p2_wake(prs):
    s = blank(prs, 2)
    head(s, "尾流的代价", "我们到底在省什么",
         "先给行业上限，再谈我们的位置——这是本场唯一一次「先自曝」")
    # 左：本项目模拟真值
    box(s, 0.8, 1.8, 4.35, 3.05)
    rule(s, 0.8, 1.8, 0.055, 3.05, ROSE_DEEP)
    big_number(s, 1.1, 1.98, 3.75, "48.6%", "1×3 串列：无尾流 5261.9 kW\n→ 有尾流 2702.2 kW", color=ROSE_DEEP, num_size=46)
    text(s, 1.1, 3.62, 3.75, 0.62, "本项目模拟值\n【真值 = FLORIS 4.6.6 · GCH · R42 oracle】", size=10, color=ROSE_DEEP, space=2)
    text(s, 1.1, 4.34, 3.75, 0.35, "真实风场远低于此值", size=10, color=SUB, space=0)
    # 右：国际坐标
    facts = [
        ("国际实测区间", "真实风场未控制尾流损失约 4%–20%", "WES 2024"),
        ("国际提升上限", "wake steering 年发电量增益 0.4%–1.7%，60 场站平均 0.8%", "Bensason 2021"),
        ("现场实测", "只能拿到静态最优的约一半（损失降低 6.4%–6.6%）", "WES 2020/2021"),
    ]
    for i, (lead, body, src) in enumerate(facts):
        y = 1.8 + i * 1.02
        box(s, 5.35, y, 7.18, 0.88)
        text(s, 5.55, y + 0.1, 4.35, 0.3, lead, size=11, bold=True, color=BLUE, space=0)
        text(s, 5.55, y + 0.42, 6.6, 0.34, body, size=10, color=SUB, space=0)
        text(s, 10.1, y + 0.1, 2.25, 0.3, f"【外部 · {src}】", size=9, bold=True, color=ROSE_DEEP, space=0)
    # 结论带
    box(s, 0.8, 5.05, 11.73, 0.95, BLUE, BLUE)
    text(s, 1.05, 5.16, 11.2, 0.34, "我们的判断", size=10, bold=True, color=WHITE, space=0)
    text(s, 1.05, 5.45, 11.2, 0.4, "不追百分比，先追「链路通、口径清、能复现」——把国际上的方法在这套系统里跑通，比多报一个点更重要。",
         size=12.5, bold=True, color=WHITE, space=0)
    strip(s, "口径提醒：48.6% 是本项目三机串列场景的模拟真值，真实风场远低于此。答辩中不得把该值当作实测尾流损失，也不得与外场实测数据并列比较。")
    return s


def p3_arch(prs):
    s = blank(prs, 3)
    head(s, "三线一体", "一条数据流串起五个人、四种角色、一套字段",
         "同一张图上同时画出已通的和没通的，是「系统」与「拼盘」的区别")
    nodes = [
        ("来流", "Kaimal 谱\nTI / 风向", "已通", "合成入口"),
        ("代理模型", "12 输入 / 6 输出\nPINN（冻结主干）", "部分通", "合成标签"),
        ("协同控制", "MADDPG / P / PI\n同权对照", "部分通", "仅桨距通道"),
        ("统一执行器", "偏航 / 桨距 / 转速\n速率与量程约束", "已通", "统一施加"),
        ("数字孪生", "twin 1×3 实时渲染\n七步演示", "已通", "FLORIS 真值"),
    ]
    w, gap = 2.05, 0.42
    for i, (name, desc, state, note) in enumerate(nodes):
        x = 0.8 + i * (w + gap)
        c = SAGE if state == "已通" else ROSE_DEEP
        box(s, x, 1.78, w, 1.86, LINE)
        rule(s, x, 1.78, 0.055, 1.86, c)
        text(s, x + 0.2, 1.9, w - 0.34, 0.35, name, size=13, bold=True, color=TXT, space=0)
        text(s, x + 0.2, 2.3, w - 0.34, 0.62, desc, size=9.5, color=SUB, space=3)
        text(s, x + 0.2, 2.99, w - 0.34, 0.26, state, size=9, bold=True, color=c, space=0)
        text(s, x + 0.2, 3.27, w - 0.34, 0.26, note, size=9.5, color=SUB, space=0)
        if i < len(nodes) - 1:
            rule(s, x + w, 2.7, gap, 0.012, LINE_DARK)
    text(s, 0.8, 3.9, 11.6, 0.35, "↓ 评价与复现层：统一场景库 · 冻结独立测试 · metrics / trajectory / validation.json",
         size=10.5, color=BLUE, space=0)
    # 三张「这是系统不是拼盘」的证据条
    proofs = [
        ("一套字段", "十二维输入、六维输出两侧共同冻结，\n字段与单位写进接口文档"),
        ("一套场景", "同一随机入口、同一执行器、同一评价口径\nP / PI / MADDPG 完全同权"),
        ("一套证据", "轨迹、指标、校验和三件套同时落盘，\n任何一个数字都能当场复算"),
    ]
    for i, (k, v) in enumerate(proofs):
        x = 0.8 + i * 3.95
        box(s, x, 4.45, 3.75, 1.35, LINE)
        text(s, x + 0.2, 4.55, 3.35, 0.28, k, size=11, bold=True, color=BLUE, space=0)
        text(s, x + 0.2, 4.9, 3.35, 0.8, v, size=9.5, color=SUB, space=0)
    text(s, 0.8, 5.92, 11.6, 0.28, "分工：厉今飞（模型与接口）· 洪祖名（控制与对照）· 田铭雨（仿真）· 袁夫达（建模口径）· 孙承泽（集成与复现）",
         size=9.5, color=SUB, space=0)
    strip(s, "两处褐色是本轮的真实短板：代理模型仍以合成标签训练，协同控制只开放了桨距通道。我们不把褐色画成绿色。")
    return s


def p4_demo(prs):
    s = blank(prs, 4)
    head(s, "现场演示", "三机数字孪生 · 七步优化闭环（现场运行，不放视频）",
         "选工况 → 看基准 → 调航向 → 求解优化 → 复核 → 可靠性 → 导出")
    picture(s, DEMO_IMG / "r44_demo_step5.png", 0.8, 1.85, w=7.3)
    box(s, 8.35, 1.85, 4.18, 1.55)
    big_number(s, 8.6, 1.95, 3.7, "2702.2 → 3299.8", "kW · 逐机贪心 [30°, 25°, 0°]", color=SAGE, num_size=22)
    text(s, 8.6, 3.05, 3.7, 0.3, "【真值 = FLORIS 4.6.6 · tandem3 oracle】", size=9.5, color=ROSE_DEEP, space=0)
    bullets(s, 8.35, 3.6, 4.2, 2.4, [
        "全场增益｜+22.11%，来自三机串列 oracle，不是 CFD",
        "逐式对拍｜浏览器内核与 FLORIS 参考值差 1.25×10⁻¹² kW",
        "兜底方案｜断网或卡顿切七步截图，话术不变",
    ], size=10.5, gap=9)
    strip(s, "口径：+22.11% 属 1×3 串列 FLORIS 真值，不得挪用到 3×3 场景（24.04%）或 PINN / 优化模块。", color=LINE, deep=SUB)
    return s


def p5_pinn(prs):
    s = blank(prs, 5)
    head(s, "十二输入 PINN", "把队友的模型接进来：只训新增的 0.79% 参数",
         "冻结主干 → 只训新增输入连接与输出层 → 合成样本短训练")
    table(s, 0.8, 1.85, 6.4, 2.4,
          ["层", "参数", "状态"],
          [["原模型总量", "3,090,200", "—"],
           ["保留的隐藏层", "3,087,200", "冻结"],
           ["新增控制输入连接", "6,300", "可训练"],
           ["新六输出层", "18,006", "可训练"],
           ["合计可训练", "24,306（≈0.79%）", "本轮训练"]],
          col_w=[2.7, 2.2, 1.5], size=10, highlight={"合计可训练"})
    box(s, 7.5, 1.85, 5.03, 3.15)
    bullets(s, 7.7, 1.95, 4.65, 2.95, [
        "输入 12 维｜风速 / 风向 / TI + 三机 × 偏航失配角·桨距角·转速",
        "输出 6 维｜三机功率 + 三机有效风速",
        "低 / 中目标｜验证误差 18.14 / 1.69 kW　【代理 · 合成标签】",
        "高目标｜最终/选中误差比 2.306，按冻结门槛停止晋级",
        "可迁移｜换成别的队友模型同样适用：冻结主干 + 新增输入连接 + 新输出头",
    ], size=10.5, gap=10)
    # 改动面：冻结 vs 可训练
    rule(s, 0.8, 5.2, 11.73, 0.01, LINE)
    text(s, 0.8, 5.3, 6.2, 0.3, "改动面：99.21% 参数冻结，只训 24,306 个（≈0.79%）",
         size=10.5, bold=True, color=TXT, space=0)
    bar_y, bar_h = 5.72, 0.34
    box(s, 0.8, bar_y, 11.73, bar_h, LINE, RGBColor(222, 226, 230))
    rule(s, 11.55, bar_y, 0.98, bar_h, ROSE_DEEP)      # 0.79% 放大显示
    text(s, 0.95, bar_y + 0.04, 8.0, 0.28, "冻结主干　3,087,200 参数", size=9.5, color=SUB, space=0)
    text(s, 9.05, 5.4, 2.75, 0.26, "可训练 24,306（示意放大）", size=8.5, bold=True, color=ROSE_DEEP, space=0)
    strip(s, "边界：训练标签为合成样本，不是 CFD 或实测；「接口已通 + 结构正确」不等于「物理精度已验证」。高目标停在前，是协议要求，不是调参失败。")
    return s


def p6_fair(prs):
    s = blank(prs, 6)
    head(s, "公平对比", "随机入口 + 统一执行器：把「同权」做成代码",
         "P / PI / MADDPG 使用同一套场景、同一套执行器、同一套评价口径")
    picture(s, MIDTERM_IMG / "02_random_inflow.png", 0.8, 1.78, w=4.7)
    picture(s, MIDTERM_IMG / "07_actuator_replay.png", 6.75, 1.78, w=4.7)
    text(s, 0.8, 4.9, 4.7, 0.3, "图02 · 三类入口：平稳湍流 / 慢变 / 阵风", size=9.5, color=SUB, space=0)
    text(s, 6.75, 4.9, 4.7, 0.3, "图07 · 统一执行器的实际运行点（同一阵风场 T1）", size=9.5, color=SUB, space=0)
    bullets(s, 0.8, 5.35, 11.6, 0.85, [
        "为什么要抽执行器｜算法只给目标值，速率 / 时间常数 / 量程由执行器施加——避免「学的方法能瞬移、传统方法被限速」的伪对比",
    ], size=11, gap=6)
    strip(s, "边界：Kaimal 单点入口不含完整空间相干结构；执行器参数为联调假设，非实际机型标定值。", color=LINE, deep=SUB)
    return s


def p7_result1(prs):
    s = blank(prs, 7)
    head(s, "结果一 · 学习有效性", "三条独立训练流，误差确实在降，但都没过门槛",
         "主种子 42 派生三条流，各 16,384 步，共 49,152 步")
    picture(s, MIDTERM_IMG / "03_validation_learning.png", 0.8, 1.8, w=7.4)
    box(s, 8.45, 1.85, 4.05, 2.6)
    text(s, 8.7, 1.98, 3.6, 0.3, "平均验证误差 / kW", size=10, bold=True, color=TXT, space=0)
    for i, (k, v, c) in enumerate([("流 1", "471.79", BLUE), ("流 2", "444.14", BLUE), ("流 3", "433.65", BLUE), ("门槛", "400 / 500", ROSE_DEEP)]):
        text(s, 8.7, 2.35 + i * 0.5, 0.95, 0.3, k, size=9.5, color=SUB, space=0)
        text(s, 9.75, 2.3 + i * 0.5, 2.5, 0.35, v, size=14, bold=True, color=c, font=SANS, space=0)
    bullets(s, 8.45, 4.65, 4.1, 1.4, [
        "从约 1290 kW 起步，三条流都下降",
        "三条均未达 400 / 500 kW 门槛 → 按协议不开放转速与偏航学习",
    ], size=10.5, gap=8)
    strip(s, "这一页只下一句结论：学习有效，验收未通过。不写成「已收敛」——最终检查点恰为验证最佳，不证明更长训练仍稳定。")
    return s


def p8_result2(prs):
    s = blank(prs, 8)
    head(s, "结果二 · 同权对照", "误差相对初始策略降 58.5%；相对 PI 再低 5.8%",
         "18 场常规测试的场景 RMSE 均值；± 为三条训练流均值的样本标准差，不是置信区间")
    table(s, 0.8, 1.85, 6.4, 2.55,
          ["控制方法", "常规平均 RMSE / kW"],
          [["初始 MADDPG", "1083.62"],
           ["固定桨距", "1100.34"],
           ["P 控制", "552.37"],
           ["PI 控制", "477.54"],
           ["训练后 MADDPG", "449.72 ± 40.11"]],
          col_w=[3.6, 2.8], size=10.5, highlight={"训练后 MADDPG"})
    box(s, 7.5, 1.9, 5.0, 1.3)
    big_number(s, 7.75, 2.0, 4.6, "−58.5%", "相对初始策略（硬结论）", color=SAGE, num_size=30)
    box(s, 7.5, 3.35, 5.0, 1.3)
    big_number(s, 7.75, 3.45, 4.6, "−5.8%", "误差均值低于 PI，仅均值层面（软结论）", color=ROSE_DEEP, num_size=30)
    bullets(s, 0.8, 4.9, 11.6, 1.25, [
        "跨流一致性｜三条训练流中有一条弱于 PI，均值优势不等于普适优势",
        "场景短板｜慢变与低风高目标均劣于 PI（见下一页展开）",
        "对评委的一句话｜我们赢在均值、输在边界，所以没有把这一页写成结论",
    ], size=10.5, gap=7)
    strip(s, "措辞纪律：本页不得表述为「MADDPG 优于传统控制」。正确说法是「均值略低、未达统计显著、跨流可靠性不足」。")
    return s


def p9_fail(prs):
    s = blank(prs, 9)
    head(s, "三个失败场景", "负结果怎么用：把它当下一轮的靶子，而不是藏起来",
         "很多项目只报均值。我们偏要把失败场景放上来")
    cards = [
        ("慢变风向", "432.08", "417.19", "目标条件响应不足"),
        ("低风高目标 7.6 m/s / 4.4 MW", "1727.89", "1383.30", "欠功率 + 可达性边界"),
        ("单条训练流", "高于 PI", "—", "跨流可靠性未达"),
    ]
    for i, (name, ours, pi, why) in enumerate(cards):
        x = 0.8 + i * 3.95
        box(s, x, 1.85, 3.75, 2.15)
        text(s, x + 0.2, 1.95, 3.35, 0.35, name, size=11, bold=True, color=TXT, space=0)
        text(s, x + 0.2, 2.35, 3.35, 0.3, "MADDPG / kW", size=9, color=SUB, space=0)
        text(s, x + 0.2, 2.6, 3.35, 0.45, ours, size=20, bold=True, color=ROSE_DEEP, font=SANS, space=0)
        text(s, x + 0.2, 3.1, 3.35, 0.3, f"PI / kW　{pi}", size=10, color=SUB, space=0)
        text(s, x + 0.2, 3.45, 3.35, 0.4, f"假设：{why}", size=9.5, color=BLUE, space=0)
    picture(s, MIDTERM_IMG / "05_scenario_breakdown.png", 0.8, 4.12, w=3.55)
    bullets(s, 6.8, 4.25, 5.7, 1.8, [
        "总体均值会掩盖失效场景｜慢变与低风高目标都输给 PI",
        "下一轮的打法｜先诊断欠功率与目标响应，再开放转速 / 偏航学习",
        "不做的选择｜不靠增加控制通道去刷平均值",
    ], size=10.5, gap=8)
    strip(s, "边界：压力场是固定风，不能称为湍流测试；没有全局功率上界证书，不能把全部跟踪损失解释为物理不可达。")
    return s


def p10_repro(prs):
    s = blank(prs, 10)
    head(s, "可复现", "我们的护城河：每个数字都能当场点开",
         "评委现在问任意一个数怎么来的，都可以打开文件核对")
    rows = [
        ["仓库门禁", "0 error / 0 warning", "python3 ci/repo_quality.py"],
        ["数字孪生自检", "161 通过 / 0 失败", "cd twin && npm run selftest"],
        ["轨迹复算", "30,720 行，差值 0 W", "metrics.csv + validation.json"],
        ["记录留痕", "3,367 文件 / 193 条链接 / 22 份镜像 / 5 份校验和", "docs/ · materials/"],
    ]
    table(s, 0.8, 1.9, 11.7, 2.6, ["项", "数字", "现场怎么证"], rows, col_w=[2.4, 4.4, 4.9], size=11,
          highlight={"轨迹复算", "数字孪生自检"})
    bullets(s, 0.8, 4.75, 11.6, 1.3, [
        "四条硬规矩｜一轮一提交一记录；出口不绿不合并；失败实验保留；数字只有一个权威来源",
        "代价我们也认｜为此多写了 20 余份审计与证据卡，交付节奏比「先做再说」慢",
    ], size=11, gap=9)
    strip(s, "这一页是「顶天」与「吹牛」的分界线：可验证性本身就是最强的说服力。", color=LINE, deep=SUB)
    return s


def p11_limits(prs):
    s = blank(prs, 11)
    head(s, "局限与下一步", "我们自己划的线，和下一轮要打的靶",
         "答辩不是终点，是下一轮的开始")
    table(s, 0.8, 1.9, 11.7, 3.3,
          ["现在不宣称", "为什么", "下一步（可交付）"],
          [["真实风场精度 / 发电收益", "入口与标签均为合成", "接 CFD 或实测 SCADA 数据"],
           ["三通道协同已学会", "本轮只开放桨距", "先诊断慢变与欠功率，再放开转速 / 偏航"],
           ["全局可达性证书", "只做了有限稳态候选扫描", "补齐候选扫描与功率上界证明"],
           ["CFD 算例", "几何非流形，网格内存吃满", "修复几何 → 最小复现包 → 单工况可信算例"]],
          col_w=[3.6, 3.6, 4.5], size=10.5)
    text(s, 0.8, 5.45, 11.6, 0.5, "对应到人：厉今飞（模型与数据）· 洪祖名（控制与诊断）· 田铭雨（CFD）· 袁夫达（建模口径）· 孙承泽（集成与复现）",
         size=10.5, color=BLUE, space=0)
    strip(s, "这四条是我们主动写下的，不是被问出来的。9.19 方案 §八：已过去的里程碑应记录偏差与原因，不补写为完成。", color=LINE, deep=SUB)
    return s


def p12_intl(prs):
    s = blank(prs, 12)
    head(s, "国际价值", "把前沿能力接进「可复现」的边界内",
         "一个外部事实 → 一个我们的位置 → 一句结论")
    bullets(s, 0.8, 1.9, 11.6, 2.1, [
        "全球规模｜2025 年新增 164.6 GW（+40%），累计 1,299 GW　【外部 · GWEC《2026 全球风能报告》】",
        "技术前沿｜风场级控制被公认为下一站，wake steering 年发电量增益 0.4%–1.7%　【外部 · WES 2024】",
        "实测落差｜现场只能拿到静态最优的约一半（损失降低 6.4%–6.6%）　【外部 · WES 2020/2021】",
        "国际现实｜上述成果由国家级实验室与大型场站完成，工具链与数据均闭环在少数机构手里",
    ], size=11.5, gap=14)
    # 上方事实列表实际占位 ≈1.9–4.05 in；卡片从 4.15 in 起
    box(s, 0.8, 4.15, 11.7, 1.55)
    text(s, 1.05, 4.3, 11.2, 0.3, "我们的位置", size=11, bold=True, color=SAGE, space=0)
    text(s, 1.05, 4.66, 11.2, 0.95,
         "不做新的物理模型，而是把「代理模型 → 协同控制 → 数字孪生 → 可复现验证」这条国际主流技术链路，\n"
         "在本科团队里完整跑通、逐式对拍、并留下全部证据——这条链路的每一步都能被第三方复算。",
         size=12, color=TXT, space=4)
    strip(s, "措辞纪律：不说「达到国际水平」，只说「把国际主流链路做到可复现」。前者无法证明，后者每一项都有文件。", color=LINE, deep=SUB)
    return s


def p13_nation(prs):
    s = blank(prs, 13)
    head(s, "国家价值", "装机全球第一之后，验证工具要能自己看见",
         "能源安全 · 大基地尾流 · 工业软件自主")
    stats = [
        ("6.4 亿千瓦", "我国风电累计装机（+22.9%），连续十余年全球第一", "国家能源局 2026-02"),
        ("1.2 亿千瓦", "2025 年新增装机（+51%），其中「三北」占 79%", "国家能源局 2026-02"),
        ("73% / 49.6%", "中国占全球新增 / 累计装机比重；海上 48.4 GW 占全球 52%", "GWEC 2026"),
    ]
    for i, (num, desc, src) in enumerate(stats):
        y = 1.8 + i * 1.05
        box(s, 0.8, y, 6.55, 0.95)
        rule(s, 0.8, y, 0.05, 0.95, BLUE)
        text(s, 1.02, y + 0.12, 2.35, 0.4, num, size=17, bold=True, color=BLUE, font=SANS, space=0)
        text(s, 3.45, y + 0.11, 3.75, 0.5, desc, size=9.5, color=SUB, space=0)
        text(s, 3.45, y + 0.65, 3.75, 0.24, f"【外部 · {src}】", size=8.5, bold=True, color=ROSE_DEEP, space=0)

    box(s, 7.6, 1.8, 4.93, 3.05)
    text(s, 7.85, 1.94, 4.45, 0.3, "我们的位置", size=11, bold=True, color=SAGE, space=0)
    bullets(s, 7.85, 2.3, 4.45, 2.45, [
        "行业真问题｜大基地集中连片布置放大尾流，而风场级控制的设计与验证长期依赖国外商业软件",
        "技术栈｜FLORIS 4.6.6 开源内核 + 自研 GCH 逐式对拍 + 浏览器端孪生",
        "可迁移｜不依赖任何商业许可，高校与中小整机厂可直接复用",
    ], size=9.5, gap=9)

    box(s, 0.8, 5.05, 11.73, 0.95, BLUE, BLUE)
    text(s, 1.05, 5.16, 11.2, 0.34, "对应国家需求", size=10, bold=True, color=WHITE, space=0)
    text(s, 1.05, 5.45, 11.2, 0.4,
         "双碳目标下的存量场站提效（不新增硬件）· 大基地尾流治理 · 工业软件自主可控的验证能力 · 本科生科研训练",
         size=11.5, bold=True, color=WHITE, space=0)
    strip(s, "措辞纪律：不说「替代国外商业软件」，只说「不依赖商业许可的验证环境」。说替代，一定会被追问到崩。", color=LINE, deep=SUB)
    return s


def p14_social(prs):
    s = blank(prs, 14)
    head(s, "社会价值", "同样的风，更少的弃风；同样的课，更可复用的模板",
         "电价 · 教育 · 科研诚信")
    cards = [
        ("电价", "国际研究显示 wake steering 的收益增益比能量增益还高约 4%（高价时段多发）", "【外部 · WES 2024】"),
        ("教育", "数据—模型—控制—可视化—复现全链路留档：3,367 个文件，每步可回溯，可直接作为本科生科研训练模板", "【实测 · 本仓库】"),
        ("诚信", "主动报告失败场景与未过门槛——这是我们在这次答辩里最想留下的示范", "【自述 · 本项目做法】"),
    ]
    for i, (k, v, tag) in enumerate(cards):
        x = 0.8 + i * 3.95
        box(s, x, 1.9, 3.75, 1.95)
        rule(s, x, 1.9, 3.75, 0.045, BLUE)
        text(s, x + 0.22, 2.06, 3.3, 0.3, k, size=12, bold=True, color=BLUE, space=0)
        text(s, x + 0.22, 2.44, 3.3, 1.0, v, size=10, color=SUB, space=3)
        text(s, x + 0.22, 3.5, 3.3, 0.25, tag, size=9, color=ROSE_DEEP, space=0)
    rule(s, 0.8, 4.15, 11.73, 0.02, LINE_DARK)
    text(s, 0.8, 4.35, 11.6, 1.4, "「我们没做出一个漂亮的数字，\n我们做出了一件可以被检查的东西。」",
         size=24, bold=True, color=TXT, space=4, lspace=1.15)
    text(s, 0.8, 6.05, 11.6, 0.5,
         "感谢各位老师。全部代码、数据、审计与失败记录见仓库 sunccchengze/FENGDIAN_2026（门禁 0 error / 0 warning）。",
         size=10.5, color=SUB, space=0)
    return s


def main():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    cover(prs)
    p1_numbers(prs)
    p2_wake(prs)
    p3_arch(prs)
    p4_demo(prs)
    p5_pinn(prs)
    p6_fair(prs)
    p7_result1(prs)
    p8_result2(prs)
    p9_fail(prs)
    p10_repro(prs)
    p11_limits(prs)
    p12_intl(prs)
    p13_nation(prs)
    p14_social(prs)
    prs.save(str(OUT))
    print(f"WROTE {OUT.relative_to(REPO)}  ({len(prs.slides._sldIdLst)} slides)")


if __name__ == "__main__":
    main()
