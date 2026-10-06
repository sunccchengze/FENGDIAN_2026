#!/usr/bin/env python3
"""软著说明文档（用户手册）markdown → docx 生成器。

口径（中国版权保护中心）：说明文档不足 60 页交全部；A4；封面 + 每页页眉
（软件全称 + 版本号）+ 页脚（权利人）+ 页码。本生成器不自动分页正文，
由 markdown 内的 `<!-- page -->` 显式控制分页（保证每节不超一页，
排版可预期；生成后请在 Word/WPS 里翻一遍核对）。

支持的 markdown 子集（手写约定，见 docs/research/softcopy/用户手册_v1.md 头部注释）：
  # 章节（自动另起一页）  ## / ### 小节  段落（首行缩进 2 字符）
  **粗体**  `行内代码`   - 列表   | 表格 |   <!-- page --> 强制分页
  ![图注](相对路径.png)  → 居中插图（16cm 宽）+ 居中图注
依赖：python3 + python-docx
用法：
  python3 tools/mk_softcopy_doc.py \
    --md docs/research/softcopy/用户手册_v1.md \
    --title "多机协同智能功率控制与数字孪生演示平台" \
    --version "V1.0（待定）" --doc-name "用户手册" \
    --rights-holder "（待定）" --date "（待定）" \
    --out docs/research/softcopy/output/用户手册_V1.0_草稿.docx
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
except ImportError:
    sys.exit("缺少 python-docx：pip3 install --user python-docx")


def set_cjk(run, size: float, bold: bool = False, font_cn: str = "宋体", font_en: str = "Times New Roman") -> None:
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = font_en
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font_cn)


def add_page_field(par) -> None:
    r1 = OxmlElement("w:r")
    f1 = OxmlElement("w:fldChar")
    f1.set(qn("w:fldCharType"), "begin")
    r1.append(f1)
    r2 = OxmlElement("w:r")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = " PAGE "
    r2.append(it)
    r3 = OxmlElement("w:r")
    f3 = OxmlElement("w:fldChar")
    f3.set(qn("w:fldCharType"), "end")
    r3.append(f3)
    for el in (r1, r2, r3):
        par._p.append(el)


def add_runs_with_inline(par, text: str, size: float, bold_base: bool = False) -> None:
    """**粗体** 与 `代码` 行内标记。"""
    for tok in re.split(r"(\*\*.+?\*\*|`[^`]+`)", text):
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**"):
            r = par.add_run(tok[2:-2])
            set_cjk(r, size, bold=True)
        elif tok.startswith("`") and tok.endswith("`"):
            r = par.add_run(tok[1:-1])
            r.font.size = Pt(size - 0.5)
            r.font.name = "Consolas"
            r._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        else:
            r = par.add_run(tok)
            set_cjk(r, size, bold=bold_base)


def build(md_path: Path, out: Path, title: str, version: str, doc_name: str,
          rights: str, date: str) -> None:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(2.2)
    sec.left_margin = sec.right_margin = Cm(2.0)

    # 页眉：软件全称 + 版本号（左）… 第 [PAGE] 页（右）
    hpara = sec.header.paragraphs[0]
    hpara.text = ""
    r1 = hpara.add_run(f"{title} {version}")
    r1.font.size = Pt(9)
    r1.font.name = "Times New Roman"
    r1._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    pPr = hpara._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "right")
    tab.set(qn("w:pos"), "9600")
    tabs.append(tab)
    pPr.append(tabs)
    hpara.add_run("\t第 ")
    add_page_field(hpara)
    hpara.add_run(" 页")

    # 页脚：权利人（居中）
    fpara = sec.footer.paragraphs[0]
    fpara.text = ""
    fpara.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rf = fpara.add_run(f"著作权人：{rights}")
    rf.font.size = Pt(9)
    rf.font.name = "Times New Roman"
    rf._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    # ── 封面 ──
    for _ in range(4):
        doc.add_paragraph()
    for text, size, bold in ((title, 22, True), (version, 16, False)):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text)
        set_cjk(r, size, bold, font_cn="黑体")
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(doc_name)
    set_cjk(r, 26, True, font_cn="黑体")
    for _ in range(6):
        doc.add_paragraph()
    for text in (f"开发完成日期：{date}", f"著作权人：{rights}"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text)
        set_cjk(r, 14, False)
    doc.add_page_break()

    # ── 正文 ──
    lines = md_path.read_text(encoding="utf-8").splitlines()
    i = 0
    table_buf: list[str] = []

    def flush_table() -> None:
        nonlocal table_buf
        if not table_buf:
            return
        rows = []
        for ln in table_buf:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c or "---") for c in cells):
                continue
            rows.append(cells)
        table_buf = []
        if not rows:
            return
        ncols = max(len(r) for r in rows)
        tbl = doc.add_table(rows=len(rows), cols=ncols)
        tbl.style = "Table Grid"
        for ri, row in enumerate(rows):
            for ci in range(ncols):
                cell = tbl.cell(ri, ci)
                cell.text = ""
                par = cell.paragraphs[0]
                txt = row[ci] if ci < len(row) else ""
                add_runs_with_inline(par, txt, 9.5, bold_base=(ri == 0))
        doc.add_paragraph()

    while i < len(lines):
        ln = lines[i].rstrip()
        if ln.lstrip().startswith("|"):
            table_buf.append(ln)
            i += 1
            continue
        flush_table()

        if not ln.strip():
            i += 1
            continue
        if ln.strip() == "<!-- page -->":
            doc.add_page_break()
            i += 1
            continue
        if ln.strip() == "---":
            i += 1
            continue
        if ln.startswith("# "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(8)
            r = p.add_run(ln[2:].strip())
            set_cjk(r, 16, True, font_cn="黑体")
        elif ln.startswith("## "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(6)
            r = p.add_run(ln[3:].strip())
            set_cjk(r, 13.5, True, font_cn="黑体")
        elif ln.startswith("### "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(4)
            r = p.add_run(ln[4:].strip())
            set_cjk(r, 12, True, font_cn="黑体")
        elif m := re.match(r"^!\[(.*?)\]\((.*?)\)\s*$", ln.strip()):
            cap, src = m.group(1), m.group(2)
            img = (md_path.parent / src).resolve()
            if not img.is_file():
                sys.exit(f"插图不存在: {img}")
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(str(img), width=Cm(16.0))
            if cap:
                cp = doc.add_paragraph()
                cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cr = cp.add_run(f"图 {cap}")
                cr.font.size = Pt(9)
                cr.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
                set_cjk(cr, 9)
        elif ln.lstrip().startswith("- "):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run("• ")
            set_cjk(r, 11)
            add_runs_with_inline(p, ln.lstrip()[2:], 11)
        elif re.match(r"^\d+\.\s", ln.strip()):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            add_runs_with_inline(p, ln.strip(), 11)
        else:
            p = doc.add_paragraph()
            p.paragraph_format.first_line_indent = Pt(22)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.25
            add_runs_with_inline(p, ln.strip(), 11)
        i += 1
    flush_table()

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(f"docx: {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--title", required=True, help="软件全称（待定占位可）")
    ap.add_argument("--version", required=True)
    ap.add_argument("--doc-name", default="用户手册")
    ap.add_argument("--rights-holder", default="（待定）")
    ap.add_argument("--date", default="（待定）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    build(Path(args.md), Path(args.out), args.title, args.version,
          args.doc_name, args.rights_holder, args.date)


if __name__ == "__main__":
    main()
