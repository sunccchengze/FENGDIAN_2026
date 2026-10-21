# -*- coding: utf-8 -*-
"""答辩 PPT · 七页证据骨架渲染（round43 的渲染，round43 文档仍为证据权威来源）

沿用 8.23 组会汇报的瑞士国际主义网格皮肤（materials/孙承泽/2026-08-23_组会汇报/generate_823_pptx.py）：
莫兰迪工科配色、发丝线、Nature 三线表、零 Emoji、1.3 倍行距、16:9 宽屏。

9.19 §十一 图表纪律在本文件中的落实：
  - 每个数字带口径标签：【申请书原文】【会议决议】【真值=FLORIS 4.6.6 模拟真值】
    【代理=浏览器内核/场景仿真】【实测=本沙箱实测】【讨论目标=9.19 验收门槛】；
  - 收集不到的证据以【待收集】条带如实呈现（9.19 §八：不补写为完成）；
  - 色标为常量，不自动改变色标夸大变化（本页面无数据图件，图件为整屏截图）。

依赖：python3 + python-pptx（pip3 install --user python-pptx）
用法：python3 docs/defense/generate_defense_pptx.py
"""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

ROOT = Path(__file__).resolve().parent          # docs/defense/
REPO_ROOT = ROOT.parents[1]                      # 仓库根
IMG = REPO_ROOT / "docs" / "research" / "img"
OUT_PPTX = ROOT / "答辩_证据骨架_v1_20261005.pptx"

TOTAL = 9
FOOTER_TEXT = "多机协同智能功率控制与数字孪生演示 · 答辩证据骨架 | 汇报人：孙承泽 (指导教师：李良星 副教授) | 瑞士网格排版规范"

# 莫兰迪工科色调体系（与 823 皮肤一致）
BG_COLOR = RGBColor(248, 249, 250)
TXT_COLOR = RGBColor(29, 32, 36)
SUB_COLOR = RGBColor(73, 80, 87)
LINE_COLOR = RGBColor(222, 226, 230)
LINE_DARK = RGBColor(43, 47, 51)
BLUE_DEEP = RGBColor(77, 104, 132)
SAGE_DEEP = RGBColor(81, 100, 71)
ROSE_COLOR = RGBColor(185, 132, 132)
ROSE_DEEP = RGBColor(140, 93, 93)
WHITE_COLOR = RGBColor(255, 255, 255)


def set_slide_background(slide):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = BG_COLOR


def add_header(slide, title_text, subtitle_text, slide_num):
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(0.45), Inches(11.73), Inches(0.02))
    line.fill.solid(); line.fill.fore_color.rgb = LINE_DARK; line.line.color.rgb = LINE_DARK
    tx = slide.shapes.add_textbox(Inches(0.8), Inches(0.55), Inches(9.7), Inches(0.95))
    tf = tx.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title_text
    p.font.size = Pt(18); p.font.bold = True; p.font.color.rgb = TXT_COLOR; p.font.name = "Arial"
    p2 = tf.add_paragraph()
    p2.text = subtitle_text
    p2.font.size = Pt(13); p2.font.bold = True; p2.font.color.rgb = BLUE_DEEP; p2.font.name = "Songti SC"
    txN = slide.shapes.add_textbox(Inches(10.5), Inches(0.55), Inches(2.0), Inches(0.5))
    pN = txN.text_frame.paragraphs[0]
    pN.text = f"{slide_num:02d} / {TOTAL}"
    pN.alignment = PP_ALIGN.RIGHT; pN.font.size = Pt(12); pN.font.bold = True; pN.font.color.rgb = SUB_COLOR; pN.font.name = "Arial"


def add_footer(slide):
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(6.9), Inches(11.73), Inches(0.01))
    line.fill.solid(); line.fill.fore_color.rgb = LINE_COLOR; line.line.color.rgb = LINE_COLOR
    tx = slide.shapes.add_textbox(Inches(0.8), Inches(6.95), Inches(11.73), Inches(0.4))
    p = tx.text_frame.paragraphs[0]
    p.text = FOOTER_TEXT
    p.font.size = Pt(9); p.font.color.rgb = SUB_COLOR; p.font.name = "Arial"


def add_q_line(slide, text, y=1.62):
    """每页顶部「要回答」一行（骨架问题，灰色斜体感）。"""
    tx = slide.shapes.add_textbox(Inches(0.8), Inches(y), Inches(11.7), Inches(0.4))
    p = tx.text_frame.paragraphs[0]
    p.text = text
    p.font.size = Pt(11.5); p.font.italic = True; p.font.color.rgb = SUB_COLOR; p.font.name = "Songti SC"


def add_strip(slide, text, y=6.32):
    """页底【待收集】条带：rose 发丝框 + rose 文字（如实呈现缺口）。"""
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(y), Inches(11.73), Inches(0.5))
    box.fill.solid(); box.fill.fore_color.rgb = WHITE_COLOR; box.line.color.rgb = ROSE_COLOR
    tf = box.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    r.font.size = Pt(10.5); r.font.color.rgb = ROSE_DEEP; r.font.name = "Songti SC"
    p.space_before = Pt(4); p.space_after = Pt(0)


def add_bullets(slide, x, y, w, h, items, size=12.5, color=None, gap=8, bold_lead=True):
    """项目符号列表；item 以 '• ' 开头；'｜' 前段加粗（如「内核对拍｜41 工况…」）。"""
    tx = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tx.text_frame; tf.word_wrap = True
    first = True
    for it in items:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_before = Pt(gap)
        if bold_lead and "｜" in it:
            lead, rest = it.split("｜", 1)
            r1 = p.add_run(); r1.text = lead
            r1.font.size = Pt(size); r1.font.bold = True; r1.font.color.rgb = color or TXT_COLOR; r1.font.name = "Songti SC"
            r2 = p.add_run(); r2.text = rest
            r2.font.size = Pt(size); r2.font.color.rgb = color or SUB_COLOR; r2.font.name = "Songti SC"
        else:
            r = p.add_run(); r.text = it
            r.font.size = Pt(size); r.font.color.rgb = color or SUB_COLOR; r.font.name = "Songti SC"
    return tx


def format_nature_table(table, size=10.5, first_col_bold=False):
    for ri, row in enumerate(table.rows):
        for cell in row.cells:
            cell.fill.solid(); cell.fill.fore_color.rgb = WHITE_COLOR
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.CENTER if ri > 0 else PP_ALIGN.LEFT
                for r in p.runs:
                    r.font.size = Pt(size)
                    r.font.color.rgb = TXT_COLOR
                    r.font.name = "Arial"
                    if ri == 0 or (first_col_bold and cell is row.cells[0]):
                        r.font.bold = True


def fill_table(slide, x, y, w, h, headers, rows, col_w=None, size=10.5):
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(x), Inches(y), Inches(w), Inches(h))
    t = shape.table
    if col_w:
        for i, cw in enumerate(col_w):
            t.columns[i].width = Inches(cw)
    for i, htxt in enumerate(headers):
        t.cell(0, i).text = htxt
    for ri, r in enumerate(rows):
        for ci, v in enumerate(r):
            t.cell(ri + 1, ci).text = v
    format_nature_table(t, size=size, first_col_bold=True)
    return t


def add_caption(slide, text, x, y, w):
    tx = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.35))
    p = tx.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = text
    p.font.size = Pt(9.5); p.font.color.rgb = SUB_COLOR; p.font.name = "Songti SC"


def new_slide(prs, title, subtitle, num):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(s)
    add_header(s, title, subtitle, num)
    add_footer(s)
    return s


def create_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # ==================== S1 封面 ====================
    s = prs.slides.add_slide(blank)
    set_slide_background(s)
    line1 = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(1.2), Inches(10.9), Inches(0.04))
    line1.fill.solid(); line1.fill.fore_color.rgb = LINE_DARK; line1.line.color.rgb = LINE_DARK
    tx = s.shapes.add_textbox(Inches(1.2), Inches(1.5), Inches(10.9), Inches(2.4))
    tf = tx.text_frame
    p1 = tf.paragraphs[0]
    p1.text = "多机协同智能功率控制与数字孪生演示平台"
    p1.font.size = Pt(34); p1.font.bold = True; p1.font.color.rgb = TXT_COLOR; p1.font.name = "Songti SC"
    p2 = tf.add_paragraph()
    p2.text = "结题答辩 · 七页证据骨架（v1 渲染）"
    p2.font.size = Pt(22); p2.font.bold = True; p2.font.color.rgb = BLUE_DEEP; p2.font.name = "Songti SC"
    txm = s.shapes.add_textbox(Inches(1.2), Inches(3.9), Inches(10.9), Inches(2.4))
    tfm = txm.text_frame
    pm = tfm.paragraphs[0]
    pm.text = ("• 汇报人：孙承泽（可视化与数字孪生 · 项目集成 · 仓库治理）\n"
               "• 指导教师：李良星 副教授\n"
               "• 依据：9.19《风电场项目结题目标与倒排实施方案》§十一（可视化同学先行建立答辩骨架，每页证据列为收集任务）\n"
               "• 渲染日期：2026-10-05（答辩对象/时长/截止日未定——骨架先立，题目来了填肉）")
    pm.font.size = Pt(13.5); pm.font.color.rgb = SUB_COLOR; pm.font.name = "Songti SC"
    add_footer(s)

    # ==================== S2 页1 · 背景与目标 ====================
    s = new_slide(prs, "01 / BACKGROUND, WAKE IMPACT & GOALS", "尾流为什么值得预测与优化——1×3 串列零偏航基线已给出量级", 2)
    add_q_line(s, "要回答：尾流影响什么？为什么需要预测与优化？最终验证哪一个问题？")
    add_bullets(s, 0.8, 2.05, 6.1, 4.1, [
        "申请书结题承诺｜研究报告 1 项 + 有望专利或软著 1 项；阶段五成果 =「多机协同智能功率控制与数字孪生演示平台 1 套」【申请书原文】",
        "9.19 决议｜第一版固定三台 NREL 5 MW；输入范围界面明确显示、超范围提示【会议决议】",
        "尾流损失量级（1×3 串列 · 零偏航）｜无尾流 5261.9 → 有尾流 2702.2 kW，损失 48.6%【FLORIS 4.6.6 · GCH 模拟真值】",
        "结论｜串列布置下尾流是主导损失项；预测 + 航向角优化是第一版范围内唯一的主动减损手段",
    ], size=12.5)
    img1 = IMG / "r41_3x3_look_20261005.png"
    if img1.exists():
        s.shapes.add_picture(str(img1), Inches(7.2), Inches(2.05), Inches(5.33), Inches(3.0))
        add_caption(s, "3×3 九机留档视图（R41 重拍 · 2026-10-05 · ?freeze=1）", 7.2, 5.1, 5.33)
    add_strip(s, "【待收集】实测场站尾流损失量级图——待真实 SCADA / 阶段五物理平台；上图与数字为模拟真值，非实测。")

    # ==================== S3 页2 · 任务边界 ====================
    s = new_slide(prs, "02 / TASK BOUNDARIES & PHYSICAL ASSUMPTIONS", "固定三机几何、唯一验证工况与两条红线", 3)
    add_q_line(s, "要回答：什么布局、风况、物理假设？哪些能力未覆盖？")
    fill_table(s, 0.8, 2.05, 11.73, 1.7,
               ["布局", "机位 (x, y) / m", "行距", "用途"],
               [
                   ["3×3 留档", "9 台 · 3 行×3 列", "632 m = 5.02 D", "阶段一/二可视化（tag 留档不删）"],
                   ["1×3 演示", "T01(−100,0) T02(100,0) T03(300,0)", "200 m = 1.59 D", "航向角优化演示固定工况"],
               ], col_w=[1.8, 4.7, 2.2, 3.03], size=10.5)
    add_bullets(s, 0.8, 4.0, 11.73, 2.2, [
        "机组｜NREL 5 MW 级：D = 125.88 m · 轮毂高度 90 m · 额定 5000 kW",
        "来流｜8 m/s / 0°（正北）/ 湍流强度 6% —— 唯一已验证范围；界面明确显示、超范围提示（R44 已实现）",
        "红线 ①｜轮毂高度截面是工程近似，不宣称二维物理",
        "红线 ②｜不宣称在线控制 / 电网跟踪 / 并网稳定",
    ], size=12)
    add_strip(s, "【待收集】输入范围完整验证表（风速/风向/湍流强度已验证区间）——依赖字段与单位冻结（组会催办项，WORKLIST §2.5）。")

    # ==================== S4 页3 · 技术路线 ====================
    s = new_slide(prs, "03 / TECHNICAL ROUTE: DATA → MODEL → OPTIMIZE → REVIEW → DISPLAY", "零后端孪生链路：离线真值打包进前端，浏览器内核推理，41 工况对拍", 4)
    add_q_line(s, "要回答：数据怎样进模型、模型怎样服务优化、结果怎样复核？")
    boxes = [
        ("FLORIS 4.6.6", "Python 离线生成\n41 工况真值"),
        ("oracle JSON", "构建期打包\n零运行时依赖"),
        ("GCH 内核", "浏览器内推理\n逐式移植 · ms 级"),
        ("贪心航向优化", "±30° / 5° 步\n上游→下游三阶段"),
        ("对拍 + 七步演示", "41 工况核对\nJSON / SVG 导出"),
    ]
    bw, bh, y0 = 2.06, 1.5, 2.35
    x0 = 0.8
    for i, (t, d) in enumerate(boxes):
        x = x0 + i * 2.4
        box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y0), Inches(bw), Inches(bh))
        box.fill.solid(); box.fill.fore_color.rgb = WHITE_COLOR; box.line.color.rgb = LINE_DARK
        tf = box.text_frame; tf.word_wrap = True
        p0 = tf.paragraphs[0]
        r = p0.add_run(); r.text = t
        r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = BLUE_DEEP; r.font.name = "Songti SC"
        p1 = tf.add_paragraph()
        r2 = p1.add_run(); r2.text = d
        r2.font.size = Pt(10.5); r2.font.color.rgb = SUB_COLOR; r2.font.name = "Songti SC"
        r2.space_before = Pt(6)
        if i < len(boxes) - 1:
            ar = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + bw + 0.05), Inches(y0 + bh / 2 - 0.09), Inches(0.28), Inches(0.18))
            ar.fill.solid(); ar.fill.fore_color.rgb = LINE_DARK; ar.line.color.rgb = LINE_DARK
    add_bullets(s, 0.8, 4.35, 11.73, 1.8, [
        "两条路线｜快速路线（上排全链路，本 PPT 全部数字出自此链）；PINN 路线（洪祖名接口：≥9 控制量 → P1–P3 + Ueff1–3，待数据训练）",
        "模块关系图为本次装配新绘｜round43 骨架「现在不存在」的待收集项 → 已补齐（渲染即证据，口径见 legend）",
    ], size=12)
    add_strip(s, "【待收集】PINN 路线端到端图（待训练完成后补；当前接口定义见 9/20 群聊记录）。")

    # ==================== S5 页4 · 数据质量 ====================
    s = new_slide(prs, "04 / DATA QUALITY & CASE INVENTORY", "41 个独立工况入库，每一条数据的来源与质量结论可点到", 5)
    add_q_line(s, "要回答：样本哪来？多少独立工况？如何排除无效算例？")
    fill_table(s, 0.8, 2.1, 11.73, 3.3,
               ["来源", "体量", "状态 / 质量结论"],
               [
                   ["袁夫达 · FLORIS GCH/CC（20260808）", "各 1224 条", "已交付；自评「数据品质不高，还是得最后靠仿真」"],
                   ["FLORIS 4.6.6 · tandem3 oracle（R42）", "41 个独立工况", "入库 · sha256 可核验 · G3t 对拍断言全绿"],
                   ["厉今飞 · 三机 PINN 交接（10-03）", "3,090,200 参数（新增可训 0.79%）", "待数据训练（阶段三检查点）"],
                   ["田铭雨 · CFD 最小复现包", "—", "⚠ 至今零痕迹，按 9.19 §十 催办"],
               ], col_w=[4.6, 2.6, 4.53], size=10.5)
    add_bullets(s, 0.8, 5.5, 11.73, 0.7, [
        "口径｜case_id 统一编号；无效算例排除 = 41 工况全部通过内核-基准对拍（R42 G3t，161 项断言常绿）",
    ], size=12)
    add_strip(s, "【待收集】工况清单表（case_id × 来源 × 质量结论）全量版；CFD 网格质量证据（MRF/滑移网格、网格无关性）。")

    # ==================== S6 页5 · 模型方法 ====================
    s = new_slide(prs, "05 / MODEL METHODS: BASELINE / SURROGATE / PINN", "三类模型的分工与各自的验证状态", 6)
    add_q_line(s, "要回答：基准 / 降阶 / 物理信息各解决什么问题？")
    fill_table(s, 0.8, 2.1, 11.73, 3.3,
               ["模型", "角色", "状态"],
               [
                   ["FLORIS 4.6.6 · GCH", "基准真值（离线生成）", "41 工况 oracle 入库【基准】"],
                   ["浏览器 GCH 内核", "快速代理（实时推理）", "FLORIS 逐式移植；对拍最大差 1.25×10⁻¹² kW【代理】"],
                   ["三机 PINN（Keras）", "物理信息代理", "冻结 3,087,200 / 新增 24,306 · 9 入 6 出 · 待训练"],
                   ["MLP 功率基线（厉今飞）", "回归基线", "20260808 交付；对李良星正式答复已完成"],
               ], col_w=[3.4, 3.4, 4.93], size=10.5)
    add_bullets(s, 0.8, 5.5, 11.73, 0.7, [
        "参照｜尾流 PINN 论文 2 篇（9/14，materials/集体）；9.19 §四/§五（POD 基 + PINN 结构约定）",
    ], size=12)
    add_strip(s, "【待收集】PINN 训练结果或完整阻塞记录（9/25 检查点未达，按 9.19 §八 如实留痕）；POD 基重建结论。")

    # ==================== S7 页6 · 预测与优化结果 ====================
    s = new_slide(prs, "06 / PREDICTION & OPTIMIZATION RESULTS (1×3 TANDEM)", "贪心 [30,25,0] 净增 +597.5 kW / +22.11%；内核对拍 1.25×10⁻¹² kW", 7)
    add_q_line(s, "要回答：误差、成本、收益是多少？有哪些失败条件？")
    fill_table(s, 0.8, 2.05, 6.3, 1.9,
               ["工况（1×3 · 8 m/s · 北来风）", "T01 / T02 / T03 · kW", "全场"],
               [
                   ["零偏航【真值】", "1754.0 / 439.0 / 509.2", "2702.2 kW"],
                   ["贪心 [30,25,0]【真值】", "1339.9 / 847.2 / 1112.7", "3299.8 kW (+22.11%)"],
               ], col_w=[2.3, 2.5, 1.5], size=10)
    add_bullets(s, 0.8, 4.15, 6.3, 2.1, [
        "内核 vs 基准对拍｜41 工况 · 最大单台差 1.25×10⁻¹² kW · NMAE 3.8×10⁻¹⁴ %",
        "耗时（SwiftShader 沙箱）｜推理 27–37 ms / 优化 5–23 ms / 41 工况复核 ≈229 ms【实测 · 代理环境】",
        "归因｜「下游 > 中游」非单调 = FLORIS 真值行为（R42 已修正归因，非缺陷）",
    ], size=11.5)
    img5 = IMG / "r44_demo_step5.png"
    if img5.exists():
        s.shapes.add_picture(str(img5), Inches(7.4), Inches(2.05), Inches(5.13), Inches(2.89))
        add_caption(s, "演示第⑤步 · 复核效果：前后流场对比 + 逐台功率（R44 演示截图）", 7.4, 4.98, 5.13)
    add_strip(s, "【待收集】PINN 路线逐工况指标表与失败案例集（待训练）；9.19 §七验收口径（流场 5% / NMAE≤3% / P95<1 s）均为【讨论目标，非成绩】。")

    # ==================== S8 页7 · 系统展示与贡献 ====================
    s = new_slide(prs, "07 / SYSTEM DEMONSTRATION & TEAM CONTRIBUTIONS", "三闸全绿、基线 145→161；五人分工与本周（R41–R46）收口", 8)
    add_q_line(s, "要回答：系统是否可用？每位成员实际交付了什么？")
    add_bullets(s, 0.8, 2.05, 5.9, 4.2, [
        "系统可用性【实测】｜三道质量闸：lint 0/0 · selftest 3×3 161/0、1×3 158/0 · 构建 ✓（R44）",
        "可复现基线演进｜EVID-2026-001 145/0（9/20）→ 150/0（R41）→ 161/0（R44）",
        "viz 15 页科研平台｜v1.3-final 封板（法定边界，本轮零改动）",
        "本周 R41–R46｜布局真值源 / 冻结取证 / 三机串列 oracle / 七步演示 / 软著材料——6 轮 · 12 张新证据截图",
        "演示入口｜?demo=1&layout=1x3（七步流程，3299.8 kW 可现场复现）",
    ], size=11.5)
    fill_table(s, 7.0, 2.05, 5.53, 3.6,
               ["成员", "方向", "现状"],
               [
                   ["厉今飞（负责人）", "三机 PINN", "已交接 · 待训练"],
                   ["洪祖名", "代理模型 + PPO", "8/8 交付 · 优化接口已定义"],
                   ["袁夫达", "建模 + 数据", "FLORIS 2448 条 + GCH/CC 各 1224"],
                   ["田铭雨", "CFD 高保真", "⚠ 最小复现包零痕迹"],
                   ["孙承泽（汇报人）", "可视化 + 材料", "本周 6 轮：演示 + 软著 + PPT"],
               ], col_w=[1.9, 1.6, 2.03], size=10)
    add_strip(s, "【待收集】3–5 分钟演示视频（9.19 成果包指定 · 可视化同学责任 · 下一工作项）；成员贡献表初稿（按提交 + 材料台账可自动生成）。")

    # ==================== S9 Q&A ====================
    s = new_slide(prs, "THANKS FOR YOUR ATTENTION / Q & A", "西安交通大学 · 能源与动力工程学院 · 大学生创新训练项目团队", 9)
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.5), Inches(2.0), Inches(10.33), Inches(4.3))
    box.fill.solid(); box.fill.fore_color.rgb = WHITE_COLOR; box.line.color.rgb = LINE_COLOR
    tf = box.text_frame; tf.word_wrap = True
    p0 = tf.paragraphs[0]
    p0.text = "感谢指导！请李良星老师及全体组员批评指正"
    p0.font.size = Pt(24); p0.font.bold = True; p0.font.color.rgb = TXT_COLOR; p0.alignment = PP_ALIGN.CENTER; p0.font.name = "Songti SC"
    p1 = tf.add_paragraph()
    p1.text = "多机协同智能功率控制与数字孪生演示平台 · 答辩证据骨架 v1（2026-10-05）"
    p1.font.size = Pt(14); p1.font.color.rgb = SUB_COLOR; p1.alignment = PP_ALIGN.CENTER; p1.font.name = "Songti SC"
    p1.space_before = Pt(14)
    p2 = tf.add_paragraph()
    p2.text = "证据清单权威来源：docs/research/round43_答辩骨架.md —— 本 PPT 是它的渲染；收集不到的证据以【待收集】如实留痕（9.19 §八）。"
    p2.font.size = Pt(11); p2.font.color.rgb = SUB_COLOR; p2.alignment = PP_ALIGN.CENTER; p2.font.name = "Songti SC"
    p2.space_before = Pt(12)
    p3 = tf.add_paragraph()
    p3.text = "数字口径图例：【申请书原文】｜【会议决议】｜【真值 = FLORIS 4.6.6 模拟真值】｜【代理 = 浏览器内核 / 场景仿真】｜【实测 = 本沙箱实测】｜【讨论目标 = 9.19 验收门槛】"
    p3.font.size = Pt(10.5); p3.font.color.rgb = ROSE_DEEP; p3.alignment = PP_ALIGN.CENTER; p3.font.name = "Songti SC"
    p3.space_before = Pt(10)

    prs.save(str(OUT_PPTX))
    print(f"✅ 生成：{OUT_PPTX}（{OUT_PPTX.stat().st_size/1024:.0f} KB · {TOTAL} 页 16:9 · 证据骨架 v1）")


if __name__ == "__main__":
    create_deck()
