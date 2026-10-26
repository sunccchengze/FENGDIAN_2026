# 答辩素材目录

三层，都是**图**，不是成品 PPT。

| 目录 | 内容 | 数量 | 产生方式 |
|---|---|---:|---|
| [`generated/`](generated/) | 16:9 整页图（PNG 300 dpi + PDF）——**已确认不用于 PPT，仅存档** | **37** | `tools/make_defense_figures.py`、`tools/make_defense_figures_batch2.py` |
| [`animated/`](animated/) | 两个 GIF（七步演示、偏航扫描） | 2 | `python3 tools/make_defense_figures.py gif` |
| [`extracted/`](extracted/) | 从 .docx / .pptx 里解出来的原图 | 12 | `python3 tools/extract_defense_assets.py` |
| [`paper/`](paper/) | **论文插图**（论文版式，PNG 400 dpi + PDF）——**这是唯一要进 PPT 的版式** | **22**（`fig01`–`fig23`，`fig12` 已撤） | `python3 tools/paper_figures.py` |

**每张图配哪一页、能支持什么结论、不能说什么** → [`../2026-10-23_答辩素材清单.md`](../2026-10-23_答辩素材清单.md)。

两条纪律：

1. **不要手改 PNG。** 数字要改就改脚本里的常量再重画，否则图与数据脱钩。
2. **图上的角标要与口播一致。** 「模拟真值 · FLORIS」不能说成实测；「合成标签 · 非物理精度」不能省掉这半句。

## 论文插图（2026-10-26，`fig01`–`fig23`，22 张）

给论文正文用的 figure，不是整页答辩图：**没有页眉、大标题、读法行、角标横幅**，
只保留坐标轴、轴标签、图例、(a)(b)(c) 面板字母和必要注解；图注另见
[`../paper_captions.md`](../paper_captions.md)。

| 项 | 规格 |
|---|---|
| 版面 | 单栏 3.35 in、双栏 6.90 in（多面板）；按最终排版宽度等比缩放 |
| 字体 | 中文**宋体**（思源宋体 Noto Serif SC 400/700）+ 拉丁/数字 DejaVu Serif；字号 7–9 pt |
| 线型 | 四边闭合脊线 0.8 pt、刻度朝内、图例无边框、`mathtext.fontset=dejavuserif` |
| 导出 | PNG **400 dpi** + 矢量 PDF（`pdf.fonttype=42`，文字可编辑/可搜） |

22 张清单（`fig12` 已撤、编号留空档）：`fig01` 设计空间、`fig02` 偏航策略、`fig03` TI 敏感性、`fig04` 尾流中心线＋两模型偏差、
`fig05` 盘面速度极坐标、`fig06` 盘面 TI 径向、`fig07` 四控制器箱线、`fig08` 误差 CDF、
`fig09` 逐场配对、`fig10` 训练收敛＋参数冻结、`fig11` 预测一致性／残差、
`fig13` 来流方向极坐标、`fig14` 反算 Cp–桨距、**`fig15` 两机串列偏航优化**、**`fig16` 3×3 阵列偏航**、
**`fig17` 尾流模态分解**、**`fig18` 尾流水平切片**、**`fig19` 六工况功率跟踪**、
**`fig20` 偏航策略选择地图**、**`fig21` 四指标逐场热图**、**`fig22` 执行器速率余量**、**`fig23` 盘面速度逐点对比**。
（`fig12` 已撤下：按 `case_id` 合并 3 次重复会造成假尖峰，同一内容改由 `fig22` 呈现。）

一览图：`paper/_contact_sheet.png`（22 张缩略拼版，只用于快速过目，不进论文）。

整包下载（只有 PNG，4.92 MB / 23 文件）：[`../paper_figures_20261026.zip`](../paper_figures_20261026.zip)。

重画：`/home/user/.venvs/fig/bin/python tools/paper_figures.py [figXX …]`（`--list` 看图号）。
**存量 37 张（`generated/`）不重画、不覆盖**；两批图结论口径一致。

## 素材总包（2026-10-26 第二版）：只收「图表版式」的图

用户口径：**只保留和论文插图同一种版式的图**，整页版式（`g01`–`g37`）不进 PPT。
所以现在的包只有三类——

[`../defense_ppt_assets_20261026.zip`](../defense_ppt_assets_20261026.zip)（**6.6 MB / 35 张图 + 22 个 PDF**）：

| 文件夹 | 内容 | 数量 |
|---|---|---:|
| `01_论文插图` | `fig01`–`fig23`（单/双栏、四边脊线、宋体、400 dpi，无页眉角标读法行）；`PDF矢量/` 下是同名矢量 PDF | 22 + 22 |
| `02_数字孪生截图` | 主界面、一键寻优、限功率 12 MW、尾流纱 A/B、方位巡检、夜间场景、偏航执行 | 9 |
| `03_Fluent导出` | 速度云图、流场场景、网格问题、求解器设置 | 4 |

不打开 zip 也能查：[`../2026-10-26_素材总索引.md`](../2026-10-26_素材总索引.md)（同 `INDEX.csv`），
逐条写「图名 / 讲什么 / 建议第几页 / 口径提醒」。
重打：`python3 tools/build_defense_assets_pack.py`（`--list` 只打印清单）。

**已移出本包**（原文件仍在仓库原位）：`generated/` 的 37 张整页图、`viz/figures_nature` 带大标题的旧科研图、
`extracted/` 里带 PPT 版式的示意图、白皮书科普插图。需要历史素材时按路径直接取，不再进答辩包。

## 整包下载

全部素材打成一个 zip，随仓库一起推：`../defense_full_pack_20261024.zip`（8.9 MiB / 56 文件，2026-10-24 晚重打）。
包里除这 37 张图，还带 7 份文档（逐页制作规格 / 问答备忘 / 照念稿 / 替换表 / 素材清单 / 项目记忆 / 证据卡）+ 第 9 页源数据 + 3 个脚本，是做 PPT 用的整包。
重打用 `python3 tools/build_defense_pack.py`；它除了完整性、清单、格式与尺寸，还会逐字节比对「包内 vs 仓库」，防止把旧图打进新包。

## 第二批（2026-10-26，`g26`–`g37`，12 张数据图）

补「多曲线 / 多子图」的实验图：CFD 中心线与剖面、盘面对照、来流方向扫描、数据集口径自检、
TI 敏感性、逐场配对、六工况小倍数、执行器约束核对、三机分解、PINN 训练诊断、四项指标并排。

**2026-10-26 全库重绘**：37 张主图统一按 [figures4papers](https://github.com/ChenLiu-1996/figures4papers) 的规范出图
（思源黑体 400/700 真粗体、语义配色、去上/右脊线、300 dpi + PDF），见 [`../../figures-style-guide.md`](../../figures-style-guide.md)。

- 逐条说明（放哪页、能说什么、**不能说什么**）→ [`../2026-10-26_第二批数据图_使用说明.md`](../2026-10-26_第二批数据图_使用说明.md)
- 单独打包 → [`../figures_batch2_20261026.zip`](../figures_batch2_20261026.zip)
- 重画 → `python3 tools/make_defense_figures_batch2.py`（只需 matplotlib + numpy）
