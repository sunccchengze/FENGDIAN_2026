# -*- coding: utf-8 -*-
"""中期答辩 v3 渲染器（13 页 / 7 分钟版，16:9，含暗底封面/谢幕）

内容一律来自 `deck_v3_content.py`，本文件只管版式。改文案请改内容模块，
**不要改 pptx**——重跑会覆盖。版式复用 v2（`generate_midterm_pptx_v2.py`）的皮肤与
十六个版式，仅新增 `two_value`（国际/国家双栏）与 `three_value_band`（三卡 + 结论带）。

皮肤：8.23 瑞士网格（浅色内容页）+ 深色转折页（封面 / 谢幕）。
零 Emoji。数字全部带【真值/代理/实测/外部/约定】标签。

依赖：python-pptx
用法：
  python3 docs/defense/generate_midterm_pptx_v3.py           # 生成 pptx
  python3 docs/defense/generate_midterm_pptx_v3.py --md      # 另出讲稿 md
输出：docs/defense/中期答辩_v3_7min_20261022.pptx
      docs/defense/2026-10-22_中期答辩讲稿_7min.md
"""
from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_v3_content as C   # noqa: E402

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
MEDIA = ROOT / "media"
OUT = ROOT / "中期答辩_v3_7min_20261022.pptx"
OUT_MD = ROOT / "2026-10-22_中期答辩讲稿_7min.md"

# ------------------------------------------------------------------ 色板
BG = RGBColor(0xF7, 0xF8, 0xF9)
INK = RGBColor(0x12, 0x16, 0x1A)
SUB = RGBColor(0x56, 0x5F, 0x67)
HAIR = RGBColor(0xD9, 0xDD, 0xE1)
RULE = RGBColor(0x23, 0x29, 0x2E)
BLUE = RGBColor(0x3D, 0x5A, 0x73)
SAGE = RGBColor(0x4E, 0x62, 0x42)
ROSE = RGBColor(0x8B, 0x5C, 0x5C)
GOLD = RGBColor(0xA0, 0x83, 0x55)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x0B, 0x10, 0x13)
DARK_TXT = RGBColor(0xF2, 0xF4, 0xF6)
DARK_SUB = RGBColor(0xB4, 0xBC, 0xC2)

SERIF = "Songti SC"
SANS = "Arial"

M = 0.72                 # 左右页边距
CW = 13.333 - 2 * M      # 内容宽 11.893


# ------------------------------------------------------------------ 基础件
def _alpha(shape, pct: int) -> None:
    fill = shape.fill._xPr.find(qn("a:solidFill"))
    clr = fill.find(qn("a:srgbClr"))
    node = etree.SubElement(clr, qn("a:alpha"))
    node.set("val", str(int(pct * 1000)))


def rect(slide, x, y, w, h, color=None, line=None, alpha=None, lw=0.75):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    if color is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = color
        if alpha is not None:
            _alpha(sh, alpha)
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(lw)
    sh.shadow.inherit = False
    sh.text_frame.word_wrap = True
    return sh


def text(slide, x, y, w, h, s, size=11, bold=False, color=SUB, font=SERIF,
         align=PP_ALIGN.LEFT, italic=False, gap=0, lspace=1.3, anchor=None):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    if anchor is not None:
        tf.vertical_anchor = anchor
    for i, line in enumerate(s.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.alignment = align
        p.space_before = Pt(gap)
        p.line_spacing = lspace
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.italic = italic
        p.font.color.rgb = color
        p.font.name = font
    return tb


def lead_bullets(slide, x, y, w, h, items, size=11, gap=9, lead_color=INK, body_color=SUB,
                 sep="｜"):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(gap)
        p.line_spacing = 1.3
        if sep and sep in it:
            head, rest = it.split(sep, 1)
            r1 = p.add_run(); r1.text = head
            r1.font.size = Pt(size); r1.font.bold = True
            r1.font.color.rgb = lead_color; r1.font.name = SERIF
            r2 = p.add_run(); r2.text = "  " + rest
            r2.font.size = Pt(size); r2.font.color.rgb = body_color; r2.font.name = SERIF
        else:
            r = p.add_run(); r.text = it
            r.font.size = Pt(size); r.font.color.rgb = body_color; r.font.name = SERIF
    return tb


def table(slide, x, y, w, h, headers, rows, col_w=None, size=11, highlight=(), head_color=BLUE,
          row_h=None):
    shp = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(x), Inches(y), Inches(w), Inches(h))
    t = shp.table
    if col_w:
        for i, cw in enumerate(col_w):
            t.columns[i].width = Inches(cw)
    if row_h:
        for r in t.rows:
            r.height = Inches(row_h)
    for i, hd in enumerate(headers):
        t.cell(0, i).text = hd
    for ri, row in enumerate(rows):
        for ci, v in enumerate(row):
            t.cell(ri + 1, ci).text = str(v)
    for ri, row in enumerate(t.rows):
        first = row.cells[0].text if ri > 0 else ""
        hot = first in highlight
        for ci, cell in enumerate(row.cells):
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE
            cell.margin_left = Inches(0.10)
            cell.margin_right = Inches(0.08)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = 3  # middle
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.CENTER
                p.line_spacing = 1.15
                for r in p.runs:
                    r.font.size = Pt(size)
                    r.font.name = SERIF
                    r.font.color.rgb = INK
                    if ri == 0:
                        r.font.bold = True
                        r.font.color.rgb = head_color
                    elif hot:
                        r.font.bold = True
                        r.font.color.rgb = SAGE
    return t


def img_size(path):
    from PIL import Image
    im = Image.open(MEDIA / path)
    return im.size


def picture_fit(slide, path, x, y, w, h, cap_h=0.30, cap=""):
    """等比装进 (w, h) 盒子并居中，标题写在盒子下方固定位置——避免压到图。"""
    pw, ph = img_size(path)
    box_h = h - (cap_h if cap else 0)
    scale = min(w / pw, box_h / ph)
    iw, ih = pw * scale, ph * scale
    px = x + (w - iw) / 2
    py = y + (box_h - ih) / 2
    rect(slide, x, y, w, box_h, WHITE, HAIR)
    pic = picture(slide, path, px, py, w=iw)
    if pic is not None:
        pic.line.color.rgb = HAIR
        pic.line.width = Pt(0.75)
    if cap:
        text(slide, x, y + box_h + 0.08, w, cap_h - 0.08, cap, size=8.5, color=SUB, gap=0)
    return pic


def picture(slide, path, x, y, w=None, h=None):
    p = MEDIA / path
    if not p.exists():
        rect(slide, x, y, w or 4, h or 2.4, WHITE, ROSE)
        text(slide, x + 0.15, y + 0.15, (w or 4) - 0.3, 0.4, f"【缺图】{path}", size=10, color=ROSE)
        return None
    kw = {}
    if w:
        kw["width"] = Inches(w)
    if h:
        kw["height"] = Inches(h)
    return slide.shapes.add_picture(str(p), Inches(x), Inches(y), **kw)


def strip(slide, s, y=6.36, dark=False, color=None):
    c = color or (HAIR if not dark else RGBColor(0x2A, 0x32, 0x38))
    rect(slide, M, y, CW, 0.44, c if not dark else c, alpha=None if not dark else 60)
    text(slide, M + 0.18, y + 0.09, CW - 0.36, 0.3, s, size=9.5,
         color=ROSE if not dark else DARK_SUB, gap=0)


def footer(slide, dark=False):
    col = DARK_SUB if dark else SUB
    text(slide, M, 7.03, CW - 1.2, 0.28, C.FOOTER, size=8.5, color=col, gap=0)
    if not dark:
        rect(slide, M, 6.95, CW, 0.008, HAIR)


def page_no(slide, n, total, dark=False):
    text(slide, 13.333 - M - 1.2, 0.42, 1.2, 0.3, f"{n:02d} / {total:02d}", size=10.5,
         bold=True, color=DARK_SUB if dark else SUB, font=SANS, align=PP_ALIGN.RIGHT, gap=0)


def light(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    rect(s, M, 0.40, CW, 0.018, RULE)
    return s


def header(s, p):
    page_no(s, p["no"], C.TOTAL)
    if p["sec"]:
        text(s, M, 0.55, 3.2, 0.26, p["sec"], size=9.5, bold=True, color=GOLD, gap=0, font=SANS)
    text(s, M, 0.82, CW - 1.3, 0.52, p["title"], size=25, bold=True, color=INK, gap=0, lspace=1.1)
    if p["kicker"]:
        text(s, M, 1.34, CW - 0.2, 0.34, p["kicker"], size=12.5, bold=True, color=BLUE, gap=0)
    if p["lead"]:
        text(s, M, 1.68, CW - 0.2, 0.3, p["lead"], size=10, italic=True, color=SUB, gap=0)


def notes(slide, p):
    tf = slide.notes_slide.notes_text_frame
    tf.text = f"【第 {p['no']} 页 · 目标 {p['secs']} 秒 · 口播 {len(p['note'])} 字】\n\n{p['note']}"


# ------------------------------------------------------------------ 版式
def lay_cover(prs, p):
    d = p["data"]
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = DARK
    picture(s, d["bg"], 0, 0, w=13.333)
    rect(s, 0, 0, 13.333, 7.5, DARK, alpha=72)
    rect(s, 0, 0, 8.6, 7.5, DARK, alpha=45)
    rect(s, M, 1.30, 0.06, 3.05, GOLD)
    text(s, M + 0.28, 1.26, 9.6, 0.3, d["badge"], size=10.5, bold=True, color=GOLD, gap=0)
    y = 1.72
    for line in d["lines"]:
        text(s, M + 0.28, y, 11.6, 0.86, line, size=40, bold=True, color=WHITE, lspace=1.05)
        y += 0.86
    text(s, M + 0.28, 3.62, 10.6, 0.4, d["sub"], size=14, color=DARK_SUB, gap=0)
    rect(s, M + 0.28, 4.32, 5.0, 0.01, GOLD)
    text(s, M + 0.28, 4.55, 11.0, 0.9, "\n".join(d["meta"]), size=10.5, color=DARK_SUB, gap=6)
    text(s, M + 0.28, 6.55, 6.0, 0.3, d["corner"], size=9.5, color=DARK_SUB, gap=0)
    return s


def lay_closing(prs, p):
    d = p["data"]
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = DARK
    picture(s, d["bg"], 0, 0, w=13.333)
    rect(s, 0, 0, 13.333, 7.5, DARK, alpha=78)
    rect(s, 0, 3.0, 13.333, 4.5, DARK, alpha=55)
    page_no(s, p["no"], C.TOTAL, dark=True)
    y = 1.42
    for line in d["lines"]:
        text(s, M, y, CW, 0.68, line, size=29, bold=True, color=WHITE, lspace=1.15)
        y += 0.62
    rect(s, M, 3.02, 2.6, 0.012, GOLD)
    y = 3.26
    for line in d["gold"]:
        text(s, M, y, CW, 0.66, line, size=27, bold=True, color=GOLD, lspace=1.15)
        y += 0.60
    text(s, M, 5.12, CW, 0.4, d["thanks"], size=13, color=DARK_TXT, gap=0)
    rect(s, M, 6.02, CW, 0.012, RGBColor(0x3A, 0x42, 0x48))
    text(s, M, 6.18, CW, 0.3, d["meta"], size=9.5, color=DARK_SUB, gap=0)
    text(s, M, 6.52, CW, 0.3, d["names"], size=9.5, color=DARK_SUB, gap=0)
    return s


def lay_quad(prs, p):
    s = light(prs)
    header(s, p)
    cells = p["data"]["cells"]
    w, h, gx, gy = 5.86, 2.16, 0.18, 0.18
    y0 = 2.20
    for i, (num, cap, tag, kind) in enumerate(cells):
        x = M + (i % 2) * (w + gx)
        y = y0 + (i // 2) * (h + gy)
        rect(s, x, y, w, h, WHITE, HAIR)
        rect(s, x, y, 0.05, h, SAGE if i in (2, 3) else BLUE)
        text(s, x + 0.34, y + 0.20, w - 0.6, 0.72, num, size=40, bold=True,
             color=SAGE if i in (2, 3) else BLUE, font=SANS, lspace=1.0)
        text(s, x + 0.34, y + 1.02, w - 0.55, 0.5, cap, size=10.5, color=SUB, lspace=1.25)
        text(s, x + 0.34, y + 1.60, w - 0.55, 0.28, f"【{kind}】{tag}", size=9.5, bold=True, color=ROSE)
    strip(s, "说明：前两格是模型结果，后两格是工程事实。所有页面沿用它——模型结果不说成实测，工程事实不吹成效果。")
    footer(s)
    return s


def lay_hero_facts(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    # 左：大数字
    rect(s, M, 1.98, 4.55, 3.55, WHITE, HAIR)
    rect(s, M, 1.98, 0.05, 3.55, ROSE)
    text(s, M + 0.34, 2.14, 3.9, 1.05, d["num"], size=54, bold=True, color=ROSE, font=SANS, lspace=1.0)
    text(s, M + 0.34, 3.24, 3.9, 0.62, d["num_cap"], size=10.5, color=SUB, lspace=1.3)
    text(s, M + 0.34, 3.98, 3.9, 0.28, d["num_tag"], size=9.5, bold=True, color=ROSE)
    rect(s, M + 0.34, 4.42, 3.85, 0.008, HAIR)
    text(s, M + 0.34, 4.56, 3.9, 0.3, "真实风场远低于此值——这一条我们自己先说", size=9.5, color=SUB)
    # 右：三条外部事实
    for i, (lead, body, src) in enumerate(d["facts"]):
        y = 1.98 + i * 1.06
        rect(s, 5.5, y, CW - 4.78, 0.94, WHITE, HAIR)
        text(s, 5.70, y + 0.10, 4.6, 0.28, lead, size=10.5, bold=True, color=BLUE)
        text(s, 5.70, y + 0.40, 5.50, 0.32, body, size=10.5, color=INK, lspace=1.25)
        text(s, 11.35, y + 0.10, 1.9, 0.26, f"【{src}】", size=8.5, bold=True, color=ROSE, align=PP_ALIGN.RIGHT)
    # 底部判断带
    rect(s, M, 5.72, CW, 0.5, BLUE)
    text(s, M + 0.2, 5.83, CW - 0.4, 0.3, d["band"], size=11, bold=True, color=WHITE)
    strip(s, "口径：48.6% 是三机串列场景的模拟真值，不得当作实测尾流损失，也不得与外场实测数据并列比较。")
    footer(s)
    return s


def lay_gif_focus(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    box_w = d["img_w"]
    box_h = 4.35
    picture_fit(s, d["img"], M, 1.96, box_w, box_h, cap_h=0.30, cap=d["img_cap"])
    xr = M + box_w + 0.30
    wr = 13.333 - M - xr
    yy = 1.96
    for lead, body, note in d["rows"]:
        rect(s, xr, yy, wr, 0.92, WHITE, HAIR)
        rect(s, xr, yy, 0.045, 0.92, BLUE)
        text(s, xr + 0.20, yy + 0.10, wr - 0.36, 0.26, lead, size=9.5, bold=True, color=BLUE)
        text(s, xr + 0.20, yy + 0.36, wr - 0.36, 0.32, body, size=13, bold=True, color=INK, font=SANS)
        text(s, xr + 0.20, yy + 0.66, wr - 0.36, 0.22, note, size=8.5, color=SUB)
        yy += 1.00
    strip(s, d["foot"])
    footer(s)
    return s


def lay_steps_up(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    n = len(d["steps"])
    w = (CW - 0.5 * (n - 1)) / n
    base_y, max_h = 5.35, 2.55
    lo, hi = 2500.0, 3450.0
    for i, (name, val, gain, ratio) in enumerate(d["steps"]):
        x = M + i * (w + 0.5)
        h = max_h * (float(val.replace(",", "")) - lo) / (hi - lo)
        col = [HAIR, RGBColor(0x9A, 0xAB, 0xB8), BLUE][i]
        rect(s, x, base_y - h, w, h, col)
        text(s, x + 0.16, base_y - h + 0.12, w - 0.3, 0.62, val, size=24, bold=True,
             color=WHITE if i else INK, font=SANS, lspace=1.0)
        text(s, x + 0.16, base_y + 0.12, w - 0.3, 0.28, name, size=10.5, bold=True, color=INK)
        if i:
            text(s, x + 0.16, base_y + 0.44, w - 0.3, 0.32, gain, size=15, bold=True, color=SAGE, font=SANS)
        if i < n - 1:
            text(s, x + w, base_y - 0.6, 0.5, 0.5, "→", size=20, bold=True, color=SUB, align=PP_ALIGN.CENTER)
    rect(s, M, base_y, CW, 0.01, RULE)
    text(s, M, 1.98, 5.0, 0.3, "三机总功率 / kW　　零偏航基准线 2702.2", size=9.5, color=SUB)
    strip(s, d["foot"])
    footer(s)
    return s


def lay_chain(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    n = len(d["nodes"])
    gap = 0.36
    w = (CW - gap * (n - 1)) / n
    for i, (name, desc, state, note) in enumerate(d["nodes"]):
        x = M + i * (w + gap)
        ok = state == "已通"
        c = SAGE if ok else ROSE
        rect(s, x, 1.92, w, 2.02, WHITE, HAIR)
        rect(s, x, 1.92, 0.05, 2.02, c)
        text(s, x + 0.22, 2.04, w - 0.36, 0.32, name, size=13, bold=True, color=INK)
        text(s, x + 0.22, 2.40, w - 0.36, 0.62, desc, size=9.5, color=SUB, lspace=1.3)
        text(s, x + 0.22, 3.08, w - 0.36, 0.26, state, size=9.5, bold=True, color=c)
        text(s, x + 0.22, 3.36, w - 0.36, 0.26, note, size=9, color=SUB)
        if i < n - 1:
            rect(s, x + w + 0.06, 2.92, gap - 0.12, 0.012, RULE)
    for i, (k, v) in enumerate(d["proofs"]):
        x = M + i * (w * 1.0 + gap + (w - w) / 2 + (CW - 3 * (w + gap)) / 2)
        x = M + i * ((CW - 2 * 0.36) / 3 + 0.36)
        ww = (CW - 2 * 0.36) / 3
        rect(s, x, 4.16, ww, 1.30, WHITE, HAIR)
        rect(s, x, 4.16, ww, 0.045, BLUE)
        text(s, x + 0.2, 4.30, ww - 0.36, 0.28, k, size=11, bold=True, color=BLUE)
        text(s, x + 0.2, 4.62, ww - 0.36, 0.72, v, size=9.5, color=SUB, lspace=1.3)
    text(s, M, 5.68, CW, 0.3, d["foot"], size=9.5, color=SUB)
    strip(s, "两处褐色是本轮的真实短板：代理模型仍是合成标签，控制只开了桨距。我们不把褐色画成绿色。")
    footer(s)
    return s


def lay_table_side(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    tw = 6.05
    table(s, M, 1.94, tw, 0.40 * (len(d["rows"]) + 1), d["headers"], d["rows"],
          col_w=d["col_w"], size=10.5, highlight=d.get("highlight", ()))
    xr = M + tw + 0.3
    wr = 13.333 - M - xr
    yy = 1.94
    for big, cap in d["side"]:
        rect(s, xr, yy, wr, 0.98, WHITE, HAIR)
        text(s, xr + 0.18, yy + 0.12, wr - 0.34, 0.42, big, size=18, bold=True, color=BLUE, font=SANS)
        text(s, xr + 0.18, yy + 0.56, wr - 0.34, 0.3, cap, size=9.5, color=SUB)
        yy += 1.08
    text(s, xr, yy - 0.02, wr, 0.26, d["side_tag"], size=9, bold=True, color=ROSE)
    # 改动面条
    if d.get("bar"):
        label, note, keep = d["bar"]
        by = 4.72
        text(s, M, by - 0.28, CW, 0.26, f"{label}：{note}，其余冻结", size=10, bold=True, color=INK)
        rect(s, M, by, CW, 0.26, RGBColor(0xE4, 0xE7, 0xEA), HAIR)
        w_keep = CW * (1 - keep)
        rect(s, M + CW - w_keep, by, w_keep, 0.26, ROSE)
        text(s, M + 0.12, by + 0.03, 6.0, 0.22, "冻结主干　3,087,200 参数", size=8.5, color=SUB)
        text(s, M, by + 0.30, CW, 0.24, "赭红色块为可训练部分（示意放大，真实占比 0.79%）", size=8.5, color=ROSE)
    lead_bullets(s, M, 5.38, CW, 0.85, d["below"], size=9.5, gap=4)
    if d.get("strip"):
        strip(s, d["strip"])
    footer(s)
    return s


def lay_two_col(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    w = (CW - 0.12) / 2
    for i, (title, items, c) in enumerate(((d["left_title"], d["left"], BLUE),
                                           (d["right_title"], d["right"], ROSE))):
        x = M + i * (w + 0.12)
        rect(s, x, 1.98, w, 2.95, WHITE, HAIR)
        rect(s, x, 1.98, w, 0.05, c)
        text(s, x + 0.24, 2.12, w - 0.4, 0.3, title, size=11.5, bold=True, color=c)
        yy = 2.56
        for it in items:
            rect(s, x + 0.26, yy + 0.10, 0.06, 0.06, c)
            text(s, x + 0.44, yy, w - 0.7, 0.3, it, size=11.5, color=INK)
            yy += 0.62
    rect(s, M, 5.14, CW, 0.52, BLUE)
    text(s, M + 0.2, 5.26, CW - 0.4, 0.3, d["band"], size=11.5, bold=True, color=WHITE)
    strip(s, d["foot"])
    footer(s)
    return s


def lay_result_pair(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    tw = 4.75
    table(s, M, 1.98, tw, 0.40 * (len(d["rows"]) + 1), d["headers"], d["rows"],
          col_w=d["col_w"], size=10.5, highlight=d.get("highlight", ()))
    xr = M + tw + 0.26
    wr = 13.333 - M - xr
    wb = (wr - 0.22) / 2
    for i, (num, cap, tag, tone) in enumerate(d["big"]):
        x = xr + i * (wb + 0.22)
        c = SAGE if tone == "sage" else ROSE
        rect(s, x, 1.98, wb, 1.75, WHITE, HAIR)
        rect(s, x, 1.98, 0.05, 1.75, c)
        text(s, x + 0.24, 2.14, wb - 0.4, 0.66, num, size=32, bold=True, color=c, font=SANS, lspace=1.0)
        text(s, x + 0.24, 2.86, wb - 0.4, 0.34, cap, size=10, color=SUB, lspace=1.25)
        text(s, x + 0.24, 3.38, wb - 0.4, 0.28, tag, size=8.5, bold=True, color=c)
    lead_bullets(s, xr, 3.96, wr, 1.0, ["对评委的一句话｜我们赢在均值、输在边界，所以没把这一页写成结论",
                                        "口径纪律｜误差棒是三条流的样本标准差，不是置信区间"],
                 size=9.5, gap=8)
    lead_bullets(s, M, 5.10, CW, 0.9, d["below"], size=10, gap=6)
    strip(s, "措辞纪律：本页不得表述为「MADDPG 优于传统控制」。正确说法是「均值略低、未达统计显著、跨流可靠性不足」。")
    footer(s)
    return s


def lay_cards3(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    n = 3
    gap = 0.24
    w = (CW - gap * (n - 1)) / n
    for i, (name, ours, pi, why, delta) in enumerate(d["cards"]):
        x = M + i * (w + gap)
        rect(s, x, 1.98, w, 2.72, WHITE, HAIR)
        rect(s, x, 1.98, w, 0.05, ROSE)
        text(s, x + 0.24, 2.14, w - 0.44, 0.62, name, size=12.5, bold=True, color=INK, lspace=1.2)
        text(s, x + 0.24, 2.86, w - 0.44, 0.26, "MADDPG / kW", size=8.5, color=SUB)
        text(s, x + 0.24, 3.10, w - 0.44, 0.56, ours, size=26, bold=True, color=ROSE, font=SANS, lspace=1.0)
        text(s, x + 0.24, 3.70, w - 0.44, 0.28, pi, size=10.5, color=SUB)
        text(s, x + 0.24, 4.06, w - 0.44, 0.28, f"假设：{why}", size=9.5, color=BLUE)
        text(s, x + 0.24, 4.34, w - 0.44, 0.26, f"差距：{delta}", size=9.5, bold=True, color=ROSE)
    strip(s, d["foot"])
    footer(s)
    return s


def lay_metrics4(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    gap = 0.22
    w = (CW - gap * 3) / 4
    for i, (num, cap, note) in enumerate(d["metrics"]):
        x = M + i * (w + gap)
        rect(s, x, 2.02, w, 2.16, WHITE, HAIR)
        rect(s, x, 2.02, w, 0.05, SAGE)
        text(s, x + 0.2, 2.18, w - 0.36, 0.7, num, size=26 if len(num) < 8 else 22, bold=True,
             color=SAGE, font=SANS, lspace=1.0)
        text(s, x + 0.2, 2.94, w - 0.36, 0.6, cap, size=9.5, color=SUB, lspace=1.3)
        text(s, x + 0.2, 3.66, w - 0.36, 0.3, note, size=10, bold=True, color=INK)
    rect(s, M, 4.42, CW, 0.56, BLUE)
    text(s, M + 0.2, 4.55, CW - 0.4, 0.3, d["band"], size=11, bold=True, color=WHITE)
    lead_bullets(s, M, 5.30, CW, 0.8, ["怎么证明｜评委指定任意一个数字，我们当场重跑，不给截图式的证明",
                                       "代价｜为此多写了二十余份审计与证据卡，交付节奏比「先做再说」慢——这是主动选择"],
                 size=10, gap=8)
    strip(s, d["foot"])
    footer(s)
    return s


def lay_limits(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    table(s, M, 1.98, CW, 0.66 * (len(d["rows"]) + 1), d["headers"], d["rows"],
          col_w=d["col_w"], size=11)
    text(s, M, 5.62, CW, 0.3, "对应到人：厉今飞（模型与数据）· 洪祖名（控制与诊断）· 田铭雨（CFD）· 袁夫达（建模口径）· 孙承泽（集成与复现）",
         size=9.5, color=SUB)
    strip(s, "这一页不是自我批评，是路线图：四条线对应四个可以交付的下一步，每条都写清了验收标准。")
    footer(s)
    return s


def lay_value(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    yy = 2.00
    for i, (fact, src) in enumerate(d["facts"]):
        text(s, M, yy, CW - 2.4, 0.32, fact, size=12, color=INK)
        text(s, 11.2, yy, 2.1, 0.3, f"【{src}】", size=8.5, bold=True, color=ROSE, align=PP_ALIGN.RIGHT)
        rect(s, M, yy + 0.42, CW, 0.008, HAIR)
        yy += 0.62
    rect(s, M, 4.02, CW, 1.28, WHITE, HAIR)
    rect(s, M, 4.02, 0.05, 1.28, SAGE)
    text(s, M + 0.26, 4.14, CW - 0.5, 0.28, d["pos_title"], size=10.5, bold=True, color=SAGE)
    text(s, M + 0.26, 4.44, CW - 0.55, 0.8, "\n".join(d["pos"]), size=12, color=INK, lspace=1.35)
    text(s, M, 5.50, CW, 0.34, d["verdict"], size=11.5, bold=True, color=BLUE)
    strip(s, "措辞纪律：不说「达到国际水平」，只说「把国际主流链路做到可复现」。前者无法证明，后者每一项都有文件。")
    footer(s)
    return s


def lay_value_stats(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    for i, (num, desc, src) in enumerate(d["stats"]):
        y = 1.98 + i * 1.02
        rect(s, M, y, 6.5, 0.92, WHITE, HAIR)
        rect(s, M, y, 0.05, 0.92, BLUE)
        text(s, M + 0.24, y + 0.16, 2.5, 0.4, num, size=19, bold=True, color=BLUE, font=SANS)
        text(s, M + 2.85, y + 0.16, 3.5, 0.40, desc, size=9.5, color=SUB, lspace=1.2)
        text(s, M + 2.85, y + 0.64, 3.5, 0.22, f"【{src}】", size=8, bold=True, color=ROSE)
    xr = 7.42
    wr = 13.333 - M - xr
    rect(s, xr, 1.98, wr, 3.02, WHITE, HAIR)
    text(s, xr + 0.24, 2.10, wr - 0.44, 0.28, d["pos_title"], size=10.5, bold=True, color=SAGE)
    yy = 2.46
    for it in d["pos"]:
        rect(s, xr + 0.26, yy + 0.10, 0.055, 0.055, SAGE)
        text(s, xr + 0.42, yy, wr - 0.7, 0.7, it, size=9.5, color=SUB, lspace=1.3)
        yy += 0.82
    rect(s, M, 5.16, CW, 0.5, BLUE)
    text(s, M + 0.2, 5.27, CW - 0.4, 0.3, d["band"], size=11, bold=True, color=WHITE)
    strip(s, "措辞纪律：不说「替代国外商业软件」，只说「不依赖商业许可的验证环境」。说替代，一定会被追问到崩。")
    footer(s)
    return s


def lay_three_value(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    gap = 0.25
    w = (CW - gap * 2) / 3
    for i, (k, body, why, tag) in enumerate(d["cards"]):
        x = M + i * (w + gap)
        rect(s, x, 2.02, w, 2.95, WHITE, HAIR)
        rect(s, x, 2.02, w, 0.05, BLUE)
        text(s, x + 0.24, 2.18, w - 0.44, 0.32, k, size=12.5, bold=True, color=BLUE)
        text(s, x + 0.24, 2.60, w - 0.44, 0.88, body, size=10.5, color=INK, lspace=1.35)
        rect(s, x + 0.24, 3.56, w - 0.48, 0.008, HAIR)
        text(s, x + 0.24, 3.68, w - 0.44, 0.62, why, size=9.5, color=SUB, lspace=1.3)
        text(s, x + 0.24, 4.52, w - 0.44, 0.26, f"【{tag}】", size=8.5, bold=True, color=ROSE)
    text(s, M, 5.24, CW, 0.34, "同样的风，更少的弃风；同样的课，更可复用的模板。", size=13, bold=True, color=INK)
    strip(s, "这一页不放新数字：所有数据都在前面出现过，或者标了外部来源。升华靠结论，不靠加码。")
    footer(s)
    return s


def lay_roadmap(prs, p):
    s = light(prs)
    header(s, p)
    d = p["data"]
    gap = 0.24
    w = (CW - gap * 2) / 3
    for i, (idx, title, how, goal) in enumerate(d["steps"]):
        x = M + i * (w + gap)
        rect(s, x, 1.98, w, 3.05, WHITE, HAIR)
        rect(s, x, 1.98, w, 0.05, GOLD)
        text(s, x + 0.24, 2.14, w - 0.44, 0.5, idx, size=24, bold=True, color=GOLD, font=SANS, lspace=1.0)
        text(s, x + 0.24, 2.66, w - 0.44, 0.5, title, size=13, bold=True, color=INK, lspace=1.2)
        text(s, x + 0.24, 3.22, w - 0.44, 0.7, how, size=9.5, color=SUB, lspace=1.3)
        rect(s, x + 0.24, 4.02, w - 0.48, 0.008, HAIR)
        text(s, x + 0.24, 4.16, w - 0.44, 0.7, goal, size=9.5, bold=True, color=SAGE, lspace=1.3)
        if i < 2:
            text(s, x + w - 0.1, 3.3, 0.4, 0.4, "→", size=18, bold=True, color=SUB, align=PP_ALIGN.CENTER)
    rect(s, M, 5.30, CW, 0.52, GOLD)
    text(s, M + 0.2, 5.42, CW - 0.4, 0.3, d["band"], size=11, bold=True, color=WHITE)
    strip(s, "这三件事都写进了下一轮的验收：不做完，不宣称。", color=RGBColor(0xEE, 0xE2, 0xCB))
    footer(s)
    return s




def lay_two_value(prs, p):
    """国际 / 国家 双栏：每栏三条「数字 + 说明 + 出处」。"""
    s = light(prs)
    header(s, p)
    d = p["data"]
    gap = 0.30
    w = (CW - gap) / 2
    for i, (title, items, c) in enumerate(((d["left_title"], d["left"], BLUE),
                                           (d["right_title"], d["right"], ROSE))):
        x = M + i * (w + gap)
        rect(s, x, 1.96, w, 2.96, WHITE, HAIR)
        rect(s, x, 1.96, w, 0.05, c)
        text(s, x + 0.26, 2.10, w - 0.44, 0.30, title, size=12, bold=True, color=c)
        yy = 2.48
        for j, (num, desc, src) in enumerate(items):
            text(s, x + 0.26, yy, 2.14, 0.44, num, size=16.5, bold=True, color=c, font=SANS,
                 lspace=1.0, gap=0)
            text(s, x + 2.52, yy - 0.02, w - 2.76, 0.46, desc, size=9.5, color=INK, lspace=1.25, gap=0)
            text(s, x + 2.52, yy + 0.44, w - 2.76, 0.22, f"【{src}】", size=8, bold=True, color=ROSE, gap=0)
            if j < len(items) - 1:
                rect(s, x + 0.26, yy + 0.74, w - 0.52, 0.008, HAIR)
            yy += 0.82
    rect(s, M, 5.10, CW, 0.52, BLUE)
    text(s, M + 0.2, 5.22, CW - 0.4, 0.30, d["band"], size=11, bold=True, color=WHITE)
    strip(s, "措辞纪律：不说「领先国际」，只说「把国际主流链路在本科团队里跑到可复算」。前者无法证明，后者每一项都有文件。")
    footer(s)
    return s


def lay_three_value_band(prs, p):
    """三张价值卡 + 底部结论带（v2 的同名版式只有一句硬编码结语）。"""
    s = light(prs)
    header(s, p)
    d = p["data"]
    gap = 0.24
    w = (CW - gap * 2) / 3
    for i, (k, body, why, tag) in enumerate(d["cards"]):
        x = M + i * (w + gap)
        rect(s, x, 1.96, w, 2.52, WHITE, HAIR)
        rect(s, x, 1.96, w, 0.05, BLUE)
        text(s, x + 0.24, 2.10, w - 0.44, 0.30, k, size=12.5, bold=True, color=BLUE)
        text(s, x + 0.24, 2.46, w - 0.44, 0.74, body, size=10, color=INK, lspace=1.32)
        rect(s, x + 0.24, 3.24, w - 0.48, 0.008, HAIR)
        text(s, x + 0.24, 3.36, w - 0.44, 0.58, why, size=9.5, color=SUB, lspace=1.28)
        text(s, x + 0.24, 4.04, w - 0.44, 0.24, f"【{tag}】", size=8.5, bold=True, color=ROSE)
    rect(s, M, 4.74, CW, 0.60, GOLD)
    text(s, M + 0.2, 4.86, CW - 0.4, 0.34, d["band"], size=10.5, bold=True, color=WHITE)
    strip(s, "这一页不放新数字：所有数据都在前面出现过，或者标了外部来源。升华靠结论，不靠加码。")
    footer(s)
    return s


LAYOUTS = {
    "two_value": lay_two_value, "three_value_band": lay_three_value_band,
    "cover": lay_cover, "closing": lay_closing, "quad": lay_quad,
    "hero_facts": lay_hero_facts, "gif_focus": lay_gif_focus, "steps_up": lay_steps_up,
    "chain": lay_chain, "table_side": lay_table_side, "two_col": lay_two_col,
    "result_pair": lay_result_pair, "cards3": lay_cards3, "metrics4": lay_metrics4,
    "limits": lay_limits, "value": lay_value, "value_stats": lay_value_stats,
    "three_value": lay_three_value, "roadmap": lay_roadmap,
}


# ------------------------------------------------------------------ 讲稿
def write_speech_md() -> None:
    total_chars = sum(len(p["note"]) for p in C.SPEC)
    total_secs = sum(p["secs"] for p in C.SPEC)
    lines = ["# 中期答辩讲稿 · 7 分钟版（2026-10-22）", "",
             "> 由 `docs/defense/deck_v3_content.py` 自动生成：改稿请改内容模块后重跑，不要手改本文件。",
             f"> 共 {len(C.SPEC)} 页 · 口播 {total_chars} 字 · 按 {C.RATE} 字/秒 ≈ {total_chars / C.RATE / 60:.1f} 分钟"
             f" · 预算 {total_secs // 60} 分 {total_secs % 60:02d} 秒（含停顿、翻页、指屏）。",
             "> **7 分钟是硬上限**：本版预算 6′46″，留给现场 14 秒余量。",
             "> **全片不出现 GitHub / 仓库 / 提交 / 克隆**；一律说「共享资料空间」「迭代轮次」。",
             "> 每页备注页里也写了同一段口播，放映时按 `⌘⇧N` / `Alt+F5` 打开演示者视图即可看提词。", ""]
    clock = 0
    for p in C.SPEC:
        start_t = f"{clock // 60:02d}:{clock % 60:02d}"
        clock += p["secs"]
        end_t = f"{clock // 60:02d}:{clock % 60:02d}"
        name = p["title"] or ("（封面）" if p["layout"] == "cover" else "（谢幕）")
        lines += [f"## P{p['no']:02d} · {name}　`{start_t} – {end_t}`", ""]
        if p["kicker"]:
            lines += [f"**屏上**：{p['kicker']}", ""]
        lines += [f"**口播（{p['secs']}s / {len(p['note'])} 字）**", "", f"> {p['note']}", ""]
    lines += ["---", "",
              "## 附一 · 时间控制（现场用）", "",
              "| 检查点 | 应到时间 | 该页 |", "|---|---|---|",
              "| 开场 + 四个数字讲完 | 00:46 | P02 |",
              "| 尾流量级讲完 | 01:24 | P03 |",
              "| 偏航扫掠讲完 | 02:10 | P04 |",
              "| 系统链路讲完 | 02:38 | P05 |",
              "| 七步闭环讲完 | 03:08 | P06 |",
              "| 迁移学习讲完 | 03:36 | P07 |",
              "| 同权对照讲完 | 04:08 | P08 |",
              "| 失败场景讲完 | 04:36 | P09 |",
              "| 可复现讲完 | 05:08 | P10 |",
              "| 国际与国家讲完 | 05:46 | P11 |",
              "| 社会与下一步讲完 | 06:20 | P12 |",
              "| 谢幕讲完 | 06:46 | P13 |", "",
              "**任意检查点晚 20 秒以上，就直接砍 P09（失败场景）的后两句，跳到「下一步三件事」。**", "",
              "## 附二 · 全程禁语（说了就会被追问到崩）", "",
              "1. 「仿真降损 22.11%」→ 那是 FLORIS 真值，不是本项目 CFD",
              "2. 「PINN 精度 18 kW」不加标签 → 必须说「合成标签下」",
              "3. 「MADDPG 优于传统控制」→ 均值低 5.8%，且有一条流输了",
              "4. 「三通道协同已实现」→ 只开了桨距",
              "5. 「替代国外商业软件」→ 改「不依赖商业许可的验证环境」",
              "6. 「工业级」「实时控制」「已收敛」——一个都不要说",
              "7. **「GitHub / 仓库 / 提交记录」——全场不提**，改「共享资料空间」「迭代轮次」", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    for p in C.SPEC:
        fn = LAYOUTS.get(p["layout"])
        if fn is None:
            raise SystemExit(f"未知版式 {p['layout']!r}（P{p['no']:02d}）")
        s = fn(prs, p)
        notes(s, p)
    prs.save(OUT)
    print(f"WROTE {OUT.name}  ({len(prs.slides._sldIdLst)} slides)")
    if "--md" in sys.argv:
        write_speech_md()
        print(f"WROTE {OUT_MD.name}")


if __name__ == "__main__":
    main()
