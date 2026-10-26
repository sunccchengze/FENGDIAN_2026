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
