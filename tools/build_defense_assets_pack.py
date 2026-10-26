#!/usr/bin/env python3
"""答辩 PPT 素材包（2026-10-26 第二版，只收「图表版式」的图）。

用户口径（2026-10-26 修正，覆盖上一版）
------------------------------------
> 「我喜欢的图就是 02_论文插图 的那种版式。其他的文件夹如果图片风格和这个不一样就不要放进来。
>   g01–g37 我完全没有用，整页的版式根本加不进我们的 PPT。我要的从来都不是整页。」

所以本版只收三类：

1. **`01_论文插图`**：`tools/paper_figures.py` 产出的 `fig01`–`fig19`
   （单/双栏、四边脊线、宋体、400 dpi，无页眉页脚角标）+ 同名矢量 PDF；
2. **`02_数字孪生截图`**：可视化页面的**实拍**（这是截图不是排版图，风格不冲突），
   只挑 9 张能上屏的，重命名为中文，转 JPEG 瘦身；
3. **`03_Fluent导出`**：Fluent 软件直接导出的云图/网格/求解器截图（同样是「原图」而非排版页）。

**不再收录**：`g01`–`g37` 整页图、`figures_nature` 里带大标题的旧图、
`assets/extracted` 里带 PPT 版式的示意图、科普插图。它们仍在仓库原位，只是不进这个包。

用法
----
    python3 tools/build_defense_assets_pack.py            # 打包
    python3 tools/build_defense_assets_pack.py --list     # 只打印清单

输出：`docs/defense/defense_ppt_assets_20261026.zip`
索引：`docs/defense/2026-10-26_素材总索引.md`（同时写进包的 `00_索引/`）
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "defense" / "defense_ppt_assets_20261026.zip"
PAPER = ROOT / "docs" / "defense" / "assets" / "paper"
EXTRACTED = ROOT / "docs" / "defense" / "assets" / "extracted"
SHOTS = ROOT / "docs" / "research" / "shots"
INDEX_MD = ROOT / "docs" / "defense" / "2026-10-26_素材总索引.md"
INDEX_CSV = ROOT / "docs" / "defense" / "2026-10-26_素材总索引.csv"

# (图号, 中文图名, 讲什么, 建议页, 口径提醒)
FIGS = [
    ("fig01", "设计空间覆盖", "风速×风向、风速×TI 两维覆盖；合成数据", "p7", "B 级：合成数据，绝对功率不与 5.80 MW 混比"),
    ("fig02", "五种偏航策略功率曲线", "偏航一律低于对齐，仅作余弦损失旁证", "p2", "不能当「偏航增功」证据"),
    ("fig03", "湍流强度敏感性", "TI 6%→10%，8 m/s 处 2194→2305 kW", "p7", "不能说「TI 越高越好」"),
    ("fig04", "尾流中心线与两模型偏差", "近场重合、远场差 3%–4%", "p5", "单条取样线不是流场重建"),
    ("fig05", "三台机盘面速度极坐标", "逐单元波动大，呈棋盘状", "p5", "不要按等值线读流场结构；云图不当精度证据"),
    ("fig06", "盘面湍流强度径向分布", "k-ω 明显高于 k-ε，差 32%–45%", "p5", "不能据此判哪个模型更准"),
    ("fig07", "四控制器 RMSE 箱线", "平稳 516、阵风 406 最好；慢变 465 输给 PI 441", "p8", "不能说「全面优于 PI」"),
    ("fig08", "跟踪误差累积分布", "小误差段左移，中段与 PI 交叉", "p9", "不能把位移换算成百分比提升"),
    ("fig09", "逐场配对散点", "12 胜 6 负；均值 449.7 vs 477.5 kW", "p9", "不能说「17/20 场更优」"),
    ("fig10", "训练收敛与参数冻结", "3.09 M 冻结 / 0.027 M 可训练", "p7", "收敛不是精度证据"),
    ("fig11", "预测-真值一致性与残差", "R²=0.999、RMSE 142.8 kW（合成标签）", "p13", "不能说现场精度 99.9%"),
    ("fig12", "执行器步进分布与上限", "偏航/转速受控；桨距中位数已达上限 3.3 倍、最大 11.8 倍", "追问", "不能说「约束已全部落实」"),
    ("fig13", "来流方向极坐标功率", "串列正对 2249/2230 kW，侧向 3634 kW", "p7", "不能说「侧吹几乎没有损失」"),
    ("fig14", "反算 Cp 与桨距", "三台机塌缩同一带（自洽性）", "追问", "自洽 ≠ 效率实测"),
    ("fig15", "两机串列偏航优化", "最优 +25°：上游 1462 kW、下游 909 kW、合计 2368 kW（+8.1%）", "p2", "两机历史工作，不是三机结论"),
    ("fig16", "3×3 阵列统一偏航与贪心", "对齐 8.1 MW → 统一 30° 9.3 MW（+14.9%）→ 逐台贪心 10.0 MW（+24.0%）", "p2 备选", "阵列规模与本次三机不同，不能直接搬结论"),
    ("fig17", "尾流模态分解", "前两阶占 97.97%：一阶偶极、二阶自恢复", "p3 备选", "两机数据；模态不等于物理机理证明"),
    ("fig18", "尾流水平切片（对齐 vs +25°）", "偏航把尾流推离下游机，下游来风回升", "p2", "16 点横向采样的插值云图，不当流场重建"),
    ("fig19", "六工况功率跟踪过程", "阵风 2.7 MW 目标下训练后更贴身；慢变差距小", "p9", "单条曲线不能替代 18 场统计"),
]

# 数字孪生：只收实拍截图（非排版页）
SHOT_LIST = [
    ("after_hero_1920.png", "数字孪生主界面", "1920×1080 默认视角；三栏面板 + 3D 风场"),
    ("after_optimize.png", "一键寻优闭环", "5 路滑杆 −1.5…−33°，功率 4.82→6.00 MW（+24.3%），尾流损失 40.9%→26.5%"),
    ("after_curtail_12mw.png", "限功率指令 12 MW", "指令 12 MW → 全场 12.00 MW，9 机降容、DERATE 告警"),
    ("after_wake_veil_on.png", "尾流纱开启", "与下一张同 t 同相位的真 A/B"),
    ("after_wake_veil_off.png", "尾流纱关闭", "关纱对照；差异集中在轮毂高走廊与尾流羽带"),
    ("after_az272_west.png", "西侧视角", "方位巡检，展示机位与尾流走向"),
    ("r29_ocean_night.png", "夜间海洋场景", "夜间光照与海面反射"),
    ("r21-night.png", "夜间主界面（另一机位）", "夜间光照下的整体画面，适合做封面底图"),
    ("r40_yaw_slew.png", "偏航执行过程", "偏航角随时间变化的上屏截图"),
]

FLUENT_LIST = [
    ("fluent_velocity_contour.png", "Fluent 速度云图", "单机尾流速度场"),
    ("fluent_contour_scene.png", "Fluent 流场场景", "整场视角云图"),
    ("fluent_mesh_issue.png", "Fluent 网格问题", "尾流区网格偏粗、盘面取样越界——主动交代的卡点"),
    ("fluent_solver_settings.png", "Fluent 求解器设置", "求解器与湍流模型设置"),
]


def _safe(name: str) -> str:
    for a, b in (("/", "·"), ("\\", "·"), (":", "·"), ("*", ""), ("?", ""),
                 ('"', ""), ("<", ""), (">", ""), ("|", "")):
        name = name.replace(a, b)
    return name.strip()


def _prepare_jpeg(src: Path, dst: Path, maxw: int = 1700, quality: int = 88) -> None:
    from PIL import Image

    im = Image.open(src).convert("RGB")
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=quality, optimize=True)


def collect():
    items = []
    for fid, title, desc, page, note in FIGS:
        pngs = sorted(PAPER.glob(f"{fid}_*.png"))
        pdfs = sorted(PAPER.glob(f"{fid}_*.pdf"))
        if not pngs:
            continue
        items.append(dict(cat="01_论文插图", src=pngs[0], pdf=pdfs[0] if pdfs else None,
                          name=_safe(f"{fid}_{title}.png"), title=title, desc=desc,
                          page=page, note=note))
    for i, (fn, title, desc) in enumerate(SHOT_LIST, 1):
        src = SHOTS / fn
        if src.exists():
            items.append(dict(cat="02_数字孪生截图", src=src, pdf=None,
                              name=_safe(f"{i:02d}_{title}.jpg"), title=title, desc=desc,
                              page="p9", note="界面演示值，不是实验结论；个别数字处缺字是软渲染伪影"))
    for src_name, title, desc in FLUENT_LIST:
        src = EXTRACTED / src_name
        if src.exists():
            items.append(dict(cat="03_Fluent导出", src=src, pdf=None,
                              name=_safe(f"{title}.png"), title=title, desc=desc,
                              page="p5", note="软件导出原图；云图不当精度证据"))
    return items


def main(argv):
    items = collect()
    if "--list" in argv:
        for it in items:
            print(f"{it['cat']}/{it['name']}")
        return 0

    md = io.StringIO()
    cs = io.StringIO()
    w = csv.writer(cs)
    w.writerow(["分类", "包内文件名", "图名", "讲什么", "建议页", "口径提醒"])

    md.write("# 答辩 PPT 素材总索引（2026-10-26 · 只收图表版式的图）\n\n")
    md.write("> 只收三种：**论文插图**（`fig01`–`fig19`，单/双栏、无页眉角标）、"
             "**数字孪生实拍截图**、**Fluent 软件导出原图**。\n>\n"
             "> 上一版里的 `g01`–`g37` 整页图、带大标题的旧科研图、PPT 版式示意图、科普插图**全部移出**——"
             "它们加不进我们的版式。原文件仍在仓库原位，只是不进这个包。\n\n")
    md.write("| 分类 | 文件数 | 说明 |\n|---|---:|---|\n")
    notes = {
        "01_论文插图": "`fig01`–`fig19`，PNG 400 dpi + 同名矢量 PDF（PDF 在 `01_论文插图/PDF矢量/`）",
        "02_数字孪生截图": "可视化页面实拍，JPEG（长边 ≤1700 px）",
        "03_Fluent导出": "Fluent 直接导出的云图 / 网格 / 求解器截图",
    }
    for c in ("01_论文插图", "02_数字孪生截图", "03_Fluent导出"):
        n = sum(1 for it in items if it["cat"] == c)
        md.write(f"| {c} | {n} | {notes[c]} |\n")
    md.write("\n")

    for c in ("01_论文插图", "02_数字孪生截图", "03_Fluent导出"):
        lst = [it for it in items if it["cat"] == c]
        md.write(f"\n## {c}\n\n| 文件 | 图名 | 讲什么 | 建议页 | 口径提醒 |\n|---|---|---|---|---|\n")
        for it in lst:
            md.write(f"| `{it['name']}` | {it['title']} | {it['desc']} | {it['page']} | {it['note']} |\n")
            w.writerow([c, it["name"], it["title"], it["desc"], it["page"], it["note"]])
        md.write("\n")

    md.write("""## 配页建议（14 页里挑 7 张就够）

| 页 | 图 |
|---|---|
| p2 研究背景 | `fig02`（偏航只降不升 → 说明收益要从布局/控制里找）+ `fig18`（偏航把尾流推开的物理） |
| p5 Fluent | `fig04`（中心线）+ `fig06`（盘面 TI）；云图只用「Fluent 导出」里的两张做观感 |
| p7 数据与代理 | `fig01`（覆盖）+ `fig03`（TI 影响）+ `fig10`（参数冻结） |
| p8 优化控制 | `fig07`（四控制器箱线） |
| p9 结果 | `fig09`（逐场配对，12 胜 6 负）+ `fig19`（跟踪过程） |
| p9 追问 | `fig12`（执行器超限）、`fig15`/`fig16`（两机与阵列历史工作） |
| p13 结论 | `fig11`（预测一致性，注合成标签） |

> 讲稿里所有数字仍以 `docs/defense/2026-10-24_口播稿_照念_v3.txt` 为准；
> 图上没有的结论不要口播补，图上有的口径提醒不要跳过。
""")

    INDEX_MD.write_text(md.getvalue(), encoding="utf-8")
    INDEX_CSV.write_text("\ufeff" + cs.getvalue(), encoding="utf-8")

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("00_索引/INDEX.md", md.getvalue())
        z.writestr("00_索引/INDEX.csv", "\ufeff" + cs.getvalue())
        tmp = Path("/tmp/_pack.jpg")
        for it in items:
            if it["name"].endswith(".jpg"):
                _prepare_jpeg(it["src"], tmp)
                z.write(tmp, f"{it['cat']}/{it['name']}")
            else:
                z.write(it["src"], f"{it['cat']}/{it['name']}")
            if it["pdf"]:
                z.write(it["pdf"], f"{it['cat']}/PDF矢量/{it['pdf'].name}")

    print(f"写出 {OUT.relative_to(ROOT)}：{OUT.stat().st_size / 1e6:.1f} MB，"
          f"{len(items)} 张图 + {sum(1 for i in items if i['pdf'])} 个 PDF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
