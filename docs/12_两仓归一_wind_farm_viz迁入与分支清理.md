# 12 · 两仓归一：wind_farm_viz 迁入记录与分支清理（2026-09-19）

> 决议来源：2026-09-19 组会后，用户决定风电大创项目**只保留本仓**（Dachuang-SZLS），
> 前身仓库 `sunccchengze/wind_farm_viz`（科研可视化平台线）整体迁入本仓后由用户删除。
> 本文是这次迁入的**完整台账**：迁了什么、没迁什么、怎么迁的、旧引用怎么查、删了哪些分支。
> 执行分支：`arena/01a0b9f8-dachuang-szls`。

## 〇、一句话

**wind_farm_viz 的 183 个提交（main + 2 条未并分支）经 `git filter-repo` 重写后，以
`--allow-unrelated-histories` 合并进本仓，文件树整体落在 `viz/`；剔除了 410 MB 的通用技能库拷贝；
本仓 3 条多余远端分支删除，只留 `main` 与工作分支。**

## 一、两条线的关系（为什么是"合并"不是"覆盖"）

| | `viz/`（原 wind_farm_viz） | `twin/`（本仓原有） |
|---|---|---|
| 时间 | 2026-07 底 → 2026-09-14 | 2026-08-24 → 今 |
| 产品 | 15 页科研可视化平台（Cloudflare Pages，**v1.3-final 封板**） | AEOLUS TWIN 数字孪生演示平台（持续迭代） |
| 角色 | 「已验证了什么」——科研证据中心 | 「将被如何验收」——结题法定交付形态 |
| 状态 | 封板，只修 bug / 死链 / 数据错 | 活跃开发 |

两条线是同一条证据链的前后两段（见 `materials/孙承泽——9月工作阶段总结.docx` §五），
所以在 Git 图谱里表现为**两个根节点在 `3c9603d` 汇合**，而不是把一方的提交改写到另一方之后
（改写会让 `main` 上全部 SHA、PR #5/#7/#9/#10 的引用全部失效）。

```
*   3c9603d merge(repo): 并入 wind_farm_viz 全部历史与文件树 → viz/
|\
| *   7da5e87 merge(union): 并入 arena/01a0a074 —— pocket-orbit          ┐
| * | 9f50a17 merge(union): 并入 arena/01a083c6 —— 自学白皮书             │ 原 wind_farm_viz
| * aab36f3 archive(union): 孤立线A/B 全量文件树归档至 _archive/          │ 182 个提交
| * ... （179 个提交，含 8/19 封板 v1.3-final）                            ┘
* 96efb95 docs(summary): 9 月工作阶段总结（来自 arena/01a0b993，已并）
* b96bf3e Merge PR #10（R40 声场/草地/执行器）                            ← 本仓原 main
```

## 二、来源清单（wind_farm_viz 侧，全部并入，零遗漏）

| 原分支 | tip | 相对 main | 处理 |
|---|---|---|---|
| `main` | `617b179a` | 179 提交 | 基线 |
| `arena/01a06516-wind-farm-viz` | `617b179a` | = main | 无独有提交，无需处理 |
| `arena/01a083c6-wind-farm-viz` | `b3f5cc78` | +1 | 合并：`风电场偏航优化与智能可视化自学白皮书.md`（138 KB）+ `images/` 19 张教学图 + `pdf/` 8 册 + `whitepaper_src/` + DeepTutor 练习册 |
| `arena/01a0a074-wind-farm-viz` | `992f6665` | +1 | 合并：`pocket-orbit/` 袖珍轨道站（3×3 软体风场交互演示）+ `给承泽·请先打开这个.md` |

两条分支的独有提交与 main **没有任何路径重叠**，`ort` 策略直接合并，无冲突。
更早的 10 条历史分支已在 2026-09-03 被归档到 `viz/_archive/`（见 `viz/_archive/MANIFEST.md`），本次不再重复处理。

## 三、迁入方式：三步 `git filter-repo` 重写

在 wind_farm_viz 的本地克隆上建 `union` 分支合并上表两条分支后，`--no-local` 复制一份做重写：

| 步 | 命令要点 | 目的 |
|---|---|---|
| 1 | `--path-rename '技能库&准则/<7 份 md>' → 'skills-notes/<同名>'` | 先把技能库目录里**项目相关的 7 份 md** 挪出来保住 |
| 2 | `--path '技能库&准则/' --invert-paths` | 从**全部历史**里剔除技能库目录 |
| 3 | `--to-subdirectory-filter viz` | 整树加 `viz/` 前缀，与 `twin/` 平级 |

- 步骤 2 的后果：只有 1 个只改动技能库的提交（`5b02260f feat(harness)…`）因变为空提交被剪除；其余 182 个全部保留。
- filter-repo 会同步改写提交信息里内嵌的旧 SHA（例如 `256a7490` 的标题里 `01759b13` → `010c76c1`），这是预期行为。
- 校验：重写后 `viz/` 下 567 个文件与原 union 树逐目录 **tree-hash 一致**（`site/ _archive/ fields/ figures_nature/ pocket-orbit/ pdf/` 抽查全同）；另加 `skills-notes/` 7 份。
- 体积：wind_farm_viz `.git` 322 MB → 重写后 86 MB；工作树 563 MB → 166 MB。

### 3.1 为什么剔除 `技能库&准则/`

- 它是用户通用技能仓 [`sunccchengze/-SKILL-`](https://github.com/sunccchengze/-SKILL-) 的**整份拷贝**：410 MB / 16,470 个文件，占原仓 75%，含 11 个 zip 与一个 28 MB 的测试 fixture；
- 本仓 `skills/` 已是按项目需要精选安装的 27 项（见 `skills/README.md`），装载来源与协议都写明；
- 原仓自己的装载纪要（现 `viz/skills-notes/019ff854技能装载纪要.md`）也写着"上游 community 1,556 + variants 697 不复制进本仓库"——整份拷贝是后来的操作，与其原则相悖；
- 用户 2026-09-19 拍板：**不迁，以 -SKILL- 仓库链接代替**。需要时 `git clone https://github.com/sunccchengze/-SKILL-`。

### 3.2 旧 SHA 怎么查

wind_farm_viz 的 `FREEZE.md` / `HANDOFF*.md` / `_archive/MANIFEST.md` / `.learnings/*` 里引用的 8 位短 SHA（如 `21a385e1`、`5dbd23ea`、`61313850`），在原仓删除后无法直接 `git show`。
对照表：[`docs/12_附件_wind_farm_viz_commit_map.tsv`](12_附件_wind_farm_viz_commit_map.tsv)（`old_sha → new_sha → subject`，183 行）。

```bash
grep '^21a385e1' docs/12_附件_wind_farm_viz_commit_map.tsv   # 查封板基线的新 SHA
git show <new_sha> --stat
git log --oneline -- viz/site/index.html                      # 单文件全程追溯（含迁入前历史）
```

## 四、迁入后的目录约定

```
Dachuang-SZLS/
├── README.md / HANDOFF.md / HANDOFF_NEXT.md   仓级门面与交接（HANDOFF_NEXT 已记 9/19 决议）
├── docs/            数字孪生线文档 01–13 + research/ 历轮记录 + 本文附件（commit map）
├── materials/       ★ 新：对外材料（阶段总结 / 答辩 PPT / 申报材料）索引与成品
├── skills/          精选 27 项技能（不变）
├── twin/            AEOLUS TWIN 数字孪生（当前 3×3；留档 tag 见 §六）
└── viz/             ★ 新：原 wind_farm_viz 整树（科研可视化平台，封板 v1.3-final）
    ├── site/            15 页纯静态站（Cloudflare Pages 产物目录）
    ├── app.py pages/    Streamlit 留档工具
    ├── generate_*.py    FLORIS 数据管道 · cases*.csv fields*/ pod_results/ figures_nature/
    ├── _archive/        2026-09-03 归档的孤立线 A/B（MANIFEST.md 身份卡）
    ├── pocket-orbit/    袖珍轨道站（arena/01a0a074）
    ├── images/ pdf/ whitepaper_src/ + 自学白皮书 .md（arena/01a083c6）
    ├── skills-notes/    自技能库目录保留的 7 份项目 md
    ├── 8.23组会*.md/.pptx · 王牌PPT.pptx · 建模与数据生成.docx · 大创申请书终版.docx
    └── FREEZE.md HANDOFF_NEXT_AGENT.md README.md .learnings/   原仓治理文档（原样，未改口径）
```

**原则**：`viz/` 内部结构**原样保留**（封板线，改路径会破坏其文档、脚本与 FREEZE 边界的引用），
只在 `viz/README.md` 顶部加了一段迁入说明；对外材料的"统一入口"由 `materials/README.md` 做索引，不搬文件。

### 4.1 在 `viz/` 里执行命令的口径

原仓文档里所有命令都以原仓根为当前目录，现在要先 `cd viz`：

```bash
cd viz
python3 -m http.server 8000 --bind 0.0.0.0 --directory site   # 静态站本地预览
python3 site/check_contract.py && python3 site/verify_all_pages.py   # 两道门禁
```

### 4.2 Cloudflare Pages（wind-farm-viz.pages.dev）——删原仓前必须处理

现役科研台是用 wind_farm_viz 仓库的 Git 集成部署的（产物目录 `site`，无构建命令）。
**删除原仓后，已上线版本不会下线，但 Pages 项目会失去源仓库，无法再发布任何修复。** 二选一：

1. 控制台把 Pages 项目 `wind-farm-viz` 重新连接到 `sunccchengze/Dachuang-SZLS`，生产分支 `main`，
   Root directory 设为 `viz`、Build output directory 设为 `site`（无构建命令）；
2. 或改为直传：`npx wrangler pages deploy viz/site --project-name wind-farm-viz`（本仓 `skills/cloudflare-deploy` 有流程）。

另一个更稳的选项：GitHub 上对 wind_farm_viz 点 **Archive**（只读）而不是 Delete——原 SHA 仍可解析、Pages 链接不断。
这是用户的决定，本文只把后果写清楚。

## 五、本仓分支清理（Dachuang-SZLS 侧）

清理前远端 4 条分支，逐条核对：

| 分支 | tip | 与 main 关系 | 处理 |
|---|---|---|---|
| `main` | `b96bf3e` | — | 保留 |
| `arena/01a0ad8e-dachuang-szls` | `81266de` | 已由 PR #9（`a86af8c`）并入 | **删除** |
| `arena/01a0adbd-dachuang-szls` | `eb6c662` | 是 PR #10 合入分支的祖先，已在 main | **删除** |
| `arena/01a0b993-dachuang-szls` | `96efb95` | +1：《孙承泽——9月工作阶段总结.docx》 | **先 ff 并入本分支再删除**；文件已归位到 `materials/` |
| `arena/01a0b9f8-dachuang-szls` | 本轮 | 当前工作分支 | 保留（合入 main 后按惯例可删） |

删除命令与结果记录在本文 §七。

## 六、数字孪生 3×3 状态留档（组会决议：改单列三风机，但 3×3 不删）

- **留档 tag**：`twin-3x3-archive-20260919`（附注 tag，指向 09-19 收尾提交 `70ed46e`——`twin/` 仍是 3×3、`selftest` 145/0、lint 0/0、build ✓ 的最后状态；其后的 `c2905fe` 与 PR #11 合并提交只改文档，`twin/` 一字未动）。
- 只要 tag 在，3×3 的每一个文件都随时可取；改造方案本身也要求**布局可切换**而不是删代码（见 [`docs/13`](13_0919组会决议_三风机改造方案与3x3留档.md)）。

```bash
git fetch --tags
git show twin-3x3-archive-20260919 --stat                      # 看留档点
git show twin-3x3-archive-20260919:twin/src/scene/terrainUtil.ts | less   # 看某个文件
git diff twin-3x3-archive-20260919 -- twin/                    # 改造后与 3×3 的全部差异
git worktree add ../twin-3x3 twin-3x3-archive-20260919         # 整套 3×3 另开目录跑起来
git checkout twin-3x3-archive-20260919 -- twin/src/scene/terrainUtil.ts   # 只拿回某个文件
```

## 七、执行记录

| 时间（Asia/Shanghai） | 动作 | 结果 |
|---|---|---|
| 09-19 | clone wind_farm_viz，核对 4 条分支 | main 179 提交；2 条 +1；1 条 = main |
| 09-19 | 本地 `union` = main + 01a083c6 + 01a0a074 | 2 个合并提交，无冲突；4 个 tip 全为 union 祖先 |
| 09-19 | filter-repo 三步重写 | 182 提交；567 文件 tree-hash 一致；.git 322→86 MB |
| 09-19 | 本仓：ff 并入 `arena/01a0b993`（9 月总结 docx） | `96efb95` |
| 09-19 | 本仓：`--allow-unrelated-histories` 合并 | `3c9603d` |
| 09-19 | 整理：`materials/` 建立、README/HANDOFF_NEXT/docs 12·13 落盘、`viz/README.md` 迁入说明 | 见本分支后续提交 |
| 09-19 | `cd twin && npm run selftest` | **145 通过 / 0 失败**（迁入不触碰 twin/） |
| 09-19 | 打 tag `twin-3x3-archive-20260919` 并推送 | 见 §六 |
| 09-19 | 删除远端 `arena/01a0ad8e` `arena/01a0adbd` `arena/01a0b993` | 远端只剩 `main` + `arena/01a0b9f8` |
| 09-19 | wind_farm_viz 远端 | **未做任何写操作**（由用户决定 Archive 或 Delete；见 §4.2） |
| 09-20 | 沙箱重置为空白克隆 → 自远端 `origin/arena/01a0b9f8` 恢复 | 分支 `70ed46e`、tag、PR #11 均在 GitHub，本地零丢失 |
| 09-20 | **独立复核**（重新 bare-clone 原仓，与 `viz/` 逐文件比 blob 哈希） | 见 §八 |
| 09-20 | 收工：PR #11（`arena/01a0b9f8` → `main`，merge commit，不 squash 以保留 182 个迁入提交的图谱） | 合入后远端 = `main` + 会话分支 + 留档 tag |

## 八、09-20 独立复核（回答"确定都转过来了吗"）

用一份**全新拉取**的 wind_farm_viz bare clone，与本仓 `HEAD:viz/` 逐文件比对（脚本即席执行，结果如下）：

| 检查 | 结果 |
|---|---|
| 原仓 4 条分支 tip 文件**并集** | 17,037 个文件，其中技能库 16,470 个（按用户决定不迁，另 7 份 md 归位 `skills-notes/`） |
| 本仓 `viz/` 文件数 | 574 = 567 项目文件 + 7 份 skills-notes |
| **缺失**（原仓有、`viz/` 没有） | **0** |
| **blob 哈希不同** | 2：`.gitignore`（= 白皮书分支加的 `pdf/v*.md` 忽略行，两分支合并后的自然结果）、`README.md`（只在顶部**加**了 8 行迁入说明，unified diff 无删除行；合并提交 `3c9603d` 处的 `viz/README.md` 与原仓 `main:README.md` **逐字节相同**） |
| `viz/` 多出的文件 | 0 |
| **全历史路径覆盖**（原仓任何提交里出现过、含后来被删的文件） | 原仓 604 条（剔除技能库）→ 本仓 `viz/` 历史 611 条，**原仓有而本仓没有的：0** |
| 提交数 | 原仓 181 + 本地 2 个 union 合并 = 183 → 迁入 182；差 1 = `5b02260f`（只改技能库，剔除后为空提交） |
| 4 条分支 tip 的等价提交 | `617b179a`→`aab36f3`、`b3f5cc78`→`2b89338`、`992f6665`→`0faeb18`（01a06516 = main） |
| GitHub 侧非 git 内容 | Issues 0 · PR 0 · Release 0 · Wiki 无页面 · 无 description/topics/homepage · 无 LFS · 无 submodule → **没有需要另外搬的东西** |

结论：**除用户明确决定不迁的 `技能库&准则/`（410 MB，-SKILL- 仓库拷贝）外，wind_farm_viz 的每一个文件、每一条历史路径、每一个提交都在本仓里。**
