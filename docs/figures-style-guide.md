# 出图规范（2026-10-26 起）：照 figures4papers 的科研制图规范执行

> 来源：[ChenLiu-1996/figures4papers](https://github.com/ChenLiu-1996/figures4papers) 仓库里的
> `scientific-figure-making` 技能（`SKILL.md` + `references/{design-theory,api,common-patterns,tutorials,demos}.md`）。
> 该仓库是顶会/期刊投稿图的实践合集（约 8.9k star），规范可直接落到 matplotlib。
>
> 本文件只记录**我们采用了哪些、改了哪些、为什么**，不复制原文。

## 1. 落点：`tools/figstyle.py`

所有答辩图脚本（`make_defense_figures.py`、`make_defense_figures_batch2.py`）统一 import 它，
不再各自维护配色与版式。改一处，37 张图同时生效。

```python
import figstyle as F
F.use_cjk(ROOT)                       # 字体：Noto Sans SC 400/700（真粗体）
fig = plt.figure(figsize=F.FS)        # 16:9
F.frame(fig, 标题, 副标题, 来源, kicker, F.TAG_CFD, reading="读法：…")
F.clean(ax, "y")                      # 去掉上/右脊线，线宽 2.2
F.save(fig, OUT, "g26_cfd_centerline")  # PNG 300 dpi + 矢量 PDF
```

## 2. 照做的八条

| # | 规则 | 具体做法 |
|---|---|---|
| 1 | **语义配色** | 主方法/我方 = 蓝 `#0F4D92`；对照（PI、固定桨距）= 中性灰；改进 = 绿 `#3F7A4B`；落后/超限 = 砖红 `#B64342`；高亮黄全篇只用一次。图里写「角色」（`ROLE["ours"]`）不写色号 |
| 2 | **脊线纪律** | 只留左/下；线宽 2.2（大柱图 3）；刻度朝外 |
| 3 | **图例去框** | `legend.frameon=False`；曲线多于 4 条时给**独立图例子图**（`F.legend_panel`），绝不压数据 |
| 4 | **数值上墙** | 柱顶/关键点直接标数（`F.annotate`），不靠网格线读数 |
| 5 | **柱状描边** | `edgecolor=#4D4D4D, linewidth=1.2`，灰度打印仍可分辨；需要时加 hatch |
| 6 | **纵轴诚实** | 比较绝对量级时一律 `ylim` 从 0 起；只有画「相对变化」才用 0 中心轴（如 `g37` 第四格）。**不用收紧的轴制造差别** |
| 7 | **双格式导出** | PNG **300 dpi**（给 PPT）+ **矢量 PDF**（给放大幅/截图，文字可选中） |
| 8 | **headless** | 先 `matplotlib.use("Agg")`，沙箱里不出窗 |

**没有照搬**的两条：`text.usetex=True`（中文进不了 TeX，沙箱也没 TeX）、`figsize=(45,12)` 这类超宽画布
（那是论文横排多指标用的，答辩是 16:9 固定版式，照搬会把中文挤死）。

## 3. 字体：从宋体黑体换成思源黑体

之前用的 `Songti SC` 单字重 900 有三个毛病：粗体无法区分（只能描边伪造）、缺 `⁻¹` 上标、
观感像印刷品而不像论文图。现在：

| 位置 | 字体 | 说明 |
|---|---|---|
| 中文 | **Noto Sans SC** 400 / 700 | `~/.fonts/NotoSansSC-cn-{400,700}.ttf`，两档真字重 |
| 拉丁 / 数字 / ± µ 上标 | DejaVu Sans | tabular 数字，小数点对齐 |

这两份 TTF 由 npm 包 `@fontsource/noto-sans-sc` 的 `chinese-simplified-{400,700}-normal.woff`
用 `fontTools` 转出（已重写 name 表，使 700 正确注册为 Bold），命令见 §5。
换机器没有这两份时自动回退到仓库自带的 `viz/site/assets/fonts/songti-sc-black.ttf`——仍能出图，只是没有真粗体。

## 4. 答辩纪律仍优先于制图美学

规范只解决「好看」，不解决「能不能说」。以下约束**没有**因为换风格而放宽：

- 每张图右下角必须有证据等级角标（`TAG_SIM` / `TAG_SYN` / `TAG_CFD` / `TAG_UI`），且与口播同词；本仓库目前**没有任何图**能挂 `TAG_OBS`（实测）。
- 图脚「读法」是**给评委看的一句话**，不是结论，也不是免责声明堆砌。
- 多指标不一致时（见 `g37`）必须并排展示，不许只挑赢的指标。

## 5. 复现

```bash
python3 -m venv .venvs/fig && .venvs/fig/bin/pip install matplotlib numpy fonttools

# 字体（只需一次）
npm pack @fontsource/noto-sans-sc
tar xzf fontsource-noto-sans-sc-*.tgz
.venvs/fig/bin/python - <<'EOF'
from fontTools.ttLib import TTFont
for w in (400, 700):
    f = TTFont(f"package/files/noto-sans-sc-chinese-simplified-{w}-normal.woff")
    f.flavor = None
    f.save(f"{__import__('os').path.expanduser('~')}/.fonts/NotoSansSC-cn-{w}.ttf")
EOF
# 再用 fontTools 改 name 表（见 git 记录 tools/figstyle.py 的注释）

# 出图
.venvs/fig/bin/python tools/make_defense_figures.py            # 第一批 g01–g25 + GIF
.venvs/fig/bin/python tools/make_defense_figures_batch2.py     # 第二批 g26–g37
```

## 6. 与旧图的差异（重画后）

- 37 张主图全部按新规范重画：真粗体标题、去掉上/右脊线、语义配色、300 dpi、附 PDF。
- 第一批图的版式（题注/角标/页脚）保持不变，只有字体、配色与线宽变了，**内容与数字一字未改**。
- `docs/defense/defense_full_pack_20261024.zip` 仍是 2026-10-24 的旧版图，**不要直接用**；
  需要整包时按 §5 重跑脚本后重新打包（`tools/build_defense_pack.py`）。

## 7. 论文插图模式（2026-10-26 新增，与上面 37 张答辩图并存）

上面 §1–§6 讲的是**答辩整页**：16:9、带页眉题注、读法行、右下角证据角标。这一节讲另一套：

> 论文正文里的 figure 只应该有一个坐标系和它的说明文字。页眉、大标题、副标题、读法行、
> 来源条、角标横幅**一律不出现**——这些内容属于 caption，不属于图。

### 7.1 落点

`tools/figstyle.py` 里追加的「论文插图模式」段（原有 `PALETTE`/`frame()`/`card()`/`save()` 全部保留）：

| 常量 / 函数 | 作用 |
|---|---|
| `PAPER_SINGLE = (3.35, 2.55)` | 单栏图宽 3.35 in（≈ 85 mm，双栏期刊单栏宽度） |
| `PAPER_WIDE = (6.90, 2.45)` | 双栏图宽 6.90 in（≈ 175 mm） |
| `PAPER_SQUARE` | 极坐标 / 方形图 |
| `use_serif(root)` | 装载宋体字族，设定字号、线宽、刻度、`pdf.fonttype=42` |
| `paper_axes(fig, rect)` | 四边闭合脊线 0.8 pt、刻度朝内、无网格 |
| `panel_label(ax, "(a)")` | 左上角面板字母，8 pt 粗体 |
| `paper_save(fig, out, name)` | 400 dpi PNG + 矢量 PDF，`bbox_inches="tight"` |

出图脚本：`tools/paper_figures.py`（`fig01`–`fig14`），只读既有 CSV/JSON。
图注与「不能说什么」见 `docs/defense/paper_captions.md`。

### 7.2 字体：**宋体**（思源宋体 Noto Serif SC）

用户明确要求用宋体。仓库自带 `viz/site/assets/fonts/songti-sc-black.ttf` **不能直接用于论文插图**：

- 它是**单字重 900**，matplotlib 找不到常规字重，日志会刷
  `findfont: Failed to find font weight normal for Songti SC, now using 900`；
- 它的字符集**缺 `⁻`（U+207B）**，`m·s⁻¹` 这类写法会掉字。

因此改用**思源宋体**（Noto Serif SC，同为宋体族，SIL OFL），400/700 双字重：

```bash
npm pack @fontsource/noto-serif-sc
tar xzf fontsource-noto-serif-sc-*.tgz
.venvs/fig/bin/python - <<'PY'
from fontTools.ttLib import TTFont
import os
for w in (400, 700):
    f = TTFont(f"package/files/noto-serif-sc-chinese-simplified-{w}-normal.woff")
    f.flavor = None                      # 去掉 WOFF 容器
    for rec in f["name"].names:          # 重写 family，避免与系统已装字重混淆
        f["name"].setName(f"Noto Serif SC CN", rec.nameID, rec.platformID,
                          rec.platEncID, rec.langID) if rec.nameID in (1, 4, 16) else None
        if rec.nameID == 2:
            f["name"].setName("Regular" if w == 400 else "Bold", 2, rec.platformID,
                              rec.platEncID, rec.langID)
    f.save(os.path.expanduser(f"~/.fonts/NotoSerifSC-cn-{w}.ttf"))
PY
```

- 字族名：`Noto Serif SC CN`（各 7,946 字形）。
- `font.family = ["DejaVu Serif", "Noto Serif SC CN"]`：拉丁字母与数字走衬线体，中文回落宋体。
- `mathtext.fontset = "dejavuserif"`：公式与正文衬线风格一致。
- 仓库内的 `songti-sc-black.ttf` 仅作**回退**（找不到上面两份时仍能出图，只是没有常规字重）。

### 7.3 一条硬约束：**`$...$` 里不能夹中文**

matplotlib 的 mathtext 一旦介入整个字符串，CJK 就交给 DejaVu，结果是豆腐块（日志为
`Font 'default' does not have a glyph for '\u901f'…`）。所以论文插图的轴标签一律写成纯文本：

| 不要写 | 改写成 |
|---|---|
| `速度 / m s$^{-1}$` | `速度 / (m/s)` |
| `$C_p$ / 桨距` | 中文标签 + 图例里用 `Cp`，或把符号单独放进图内注释 |
| `来流方向 $\\theta$` | `来流方向 / (°)` |

函数名、变量名照常（`figstyle.py` 内部用 `r"k-$\omega$ SST"` 这类纯数学标签是安全的，
因为字符串里没有中文）。

### 7.4 与 §4「答辩纪律」的关系

论文插图**不上图面**、但**必须在 caption 里**保留同样的边界：证据等级（A/B/C）、
「不能说什么」。位置从图的右下角挪到 `docs/defense/paper_captions.md` 的对应条目，
口头答辩仍按 §4 的口径讲。
