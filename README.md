# Dachuang-SZLS · 风电场偏航优化大创项目 · 可视化与数字孪生（唯一仓库）

> 西安交通大学 · 国家重点领域大学生创新训练项目《融合数据-物理驱动的风电流场智能感知与智能调控研究》（2026.04–2027.06）
>
> 可视化与数字孪生模块负责人：孙承泽 ｜ 导师：李良星 副教授
>
> **2026-09-19 起本仓是项目可视化线的唯一仓库**：前身仓库 `wind_farm_viz`（科研可视化平台，2026-07 底 → 09-14）已经按 [`docs/12`](docs/12_两仓归一_wind_farm_viz迁入与分支清理.md) 的台账迁入 `viz/`，原仓库由用户删除。
>
> 迁移审计证明的是：除用户明确决定不迁的通用技能库拷贝外，前身仓库的文件、历史路径和提交已进入 `viz/`；它**不等于**外部技能仓、聊天记录、外部数据或其他项目生态内容自动进入本仓。迁移边界和未迁内容以 `docs/12` 为准。

## 🚪 新接手？先花 30 分钟，按这个顺序读

本仓文档多（根 README、两份 HANDOFF、`docs/` 14 篇编号文档、`materials/` 六个台账），**不要从任意一篇开始**。按 [`HANDOFF_NEXT.md`](HANDOFF_NEXT.md) §0 的路径读，30 分钟能掌握全貌：

1. 本 README §项目入口 + §五人分工 + §PINN 线（5 分钟）
2. [`docs/project/TIMELINE.md`](docs/project/TIMELINE.md) §0–§2 —— **什么时候发生了什么**（10 分钟）
3. [`docs/project/WORKLIST.md`](docs/project/WORKLIST.md) §0–§2 —— **接下来谁干什么、卡在哪、过期几天**（10 分钟）
4. [`HANDOFF_NEXT.md`](HANDOFF_NEXT.md) §1 现状快照 + 红线 + 九条门槛（5 分钟）

三条导航原则：**时间 → TIMELINE；待办 → WORKLIST；本模块技术与红线 → HANDOFF_NEXT。** 其余文档都是这三者的分区明细或原始记录，不要把它们当入口。

## 项目入口

| 入口 | 你会找到什么 |
|---|---|
| [`docs/project/TIMELINE.md`](docs/project/TIMELINE.md) | **唯一时间线主干**：六个阶段、按事件日期的主表、事件↔入库滞后对照、十一项已知缺口 |
| [`docs/project/WORKLIST.md`](docs/project/WORKLIST.md) | **唯一待办来源**：按角色的待办/阻塞/过期天数/倒排节点；可视化四条工作流 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 五人分工、Issue/PR、审阅和提交规则 |
| [`docs/14`](docs/14_协作治理与可复现研究工作台方案.md) | **当前治理基线**：技术取舍、证据链、MVP 和执行顺序 |
| [`docs/`](docs/README.md) | 研究、决策、会议、证据、审计和模板导航 |
| [`docs/evidence/`](docs/evidence/README.md) | 权威数字和可复现证据索引 |
| [`materials/`](materials/README.md) | **按人归档**的材料与交付件（五个个人目录 + `集体/`）、答辩 / 申报材料和审核口径 |
| [`optimization_control/`](optimization_control/WORK_INDEX.md) | **优化控制代码与实验**（洪祖名 2026-10-07 交付）：代理模型、PPO、随机入口、三机 MADDPG、统一传统基线、诊断与回放工具 |
| [`HANDOFF_NEXT.md`](HANDOFF_NEXT.md) | 当前阶段开放项、红线和下一轮交接 |

## 五人分工

| 成员 | 主责 |
|---|---|
| **厉今飞** | **项目负责人**；AI 模块：功率 / 流场预测神经网络、PINN、降阶与代理模型路线、各模块目标与接口对接 |
| **袁夫达** | 建模：风机选型（NREL 5MW）、FLORIS 风场数据生成、数据字典与工况口径、FLORIS / Fluent 原理梳理 |
| **田铭雨** | 仿真：Fluent CFD（MRF）算例、网格与湍流模型、高保真流场数据 |
| **洪祖名** | 优化控制：代理模型优化、PPO 与控制闭环验证 |
| **孙承泽** | 可视化与数字孪生：`viz/` 科研平台、`twin/` 数字孪生；项目集成、仓库治理、材料与答辩 |

主责人负责事实和审阅。代码与数据目录（`viz/`、`twin/`、`docs/`）不按人划分，共享文件必须通过 PR 协作；个人制作的材料、报告与交付件按内容主责人归档在 `materials/<姓名>/`（2026-09-21 起，见 [`materials/README.md`](materials/README.md)）；跨领域结论由主责人和至少一名其他成员共同审阅。

> 分工口径以申请书封面（项目负责人厉今飞）与各成员工作总结自述为准，2026-09-21 经 [`ADR-2026-002`](docs/decisions/ADR-2026-002-五人分工表以申请书与成员自述为准.md) 修订（此前版本把厉今飞写成「基线数据」、袁夫达写成「降阶模型和代理模型」，已 supersede）。

## 仓库结构：一条证据链、两套平台

| 目录 | 平台 | 状态 | 入口 |
|---|---|---|---|
| [`viz/`](viz/README.md) | **科研可视化平台**（15 页浅色瑞士网格科研台，FLORIS/POD/PPO 真值全量呈现） | **封板 v1.3-final**（2026-08-19），只修 bug/死链/数据错 | `cd viz && python3 -m http.server 8000 --directory site`；线上 [wind-farm-viz.pages.dev](https://wind-farm-viz.pages.dev/)（Pages 需重连本仓，见 `docs/12` §4.2） |
| [`twin/`](twin/README.md) | **AEOLUS TWIN 数字孪生**（影院级深色 3D Web 大屏，申请书阶段五法定交付形态） | 持续迭代（R44）；**单列三机（1×3）改造 + 九一九 §2 演示界面已完成**：布局可切换（`?layout=1x3` / `?layout=3x3`，默认 3×3）、3×3 不删（留档 tag `twin-3x3-archive-20260919`）、1×3 真值来自 FLORIS 三机串列 oracle（tandem3）、`?demo=1` 七步演示（调航向/求解优化/复核/导出，GCH 内核 + FLORIS 实测对拍 1e-12 kW），见 [`docs/13`](docs/13_0919组会决议_三风机改造方案与3x3留档.md) 与 [`round41`](docs/research/round41_单列三机改造.md)/[`round42`](docs/research/round42_单列三机改造_视觉与真值.md)/[`round44`](docs/research/round44_演示界面_七步流程.md) | `cd twin && npm install && npm run dev` |
| [`optimization_control/`](optimization_control/WORK_INDEX.md) | **优化控制模块**（准静态风场环境 / MADDPG / PPO / 代理模型，纯 Python + `unittest`） | 2026-10-21 随分支吸收并入 `main`；**固定 9 输入网络的结果仅为合成联调，可靠性门槛未全部通过** | 入口 [`WORK_INDEX.md`](optimization_control/WORK_INDEX.md)；交付包 [`materials/洪祖名/20261007_optimization_handoff/`](materials/洪祖名/20261007_optimization_handoff/README.md) |
| [`materials/`](materials/README.md) | 按人归档的材料与交付件（阶段总结 / PPT / 讲稿 / 申报 / 队友交付包） | 2026-09-21 已把 `viz/` 及其归档中的个人材料与队友交付件按人迁入（不含目录 README 与 Markdown 镜像：孙承泽 76 · 洪祖名 101 · 厉今飞 27 · 袁夫达 13 · 集体 28 · 田铭雨 2；2026-09-21 的基线为 76 / 36 / 25 / 13 / 20 / 2，10 月新增部分见 `materials/README.md` §1）；所有 docx / pptx / pdf 附 markitdown 生成的同名 `.md` 镜像（`tools/markitdown_sync.py`），材料治理已建立 | 各人目录 `README.md` |
| [`docs/`](docs/README.md) | 研究、决策、会议、证据、审计和交接记录 | 持续维护 | — |
| [`skills/`](skills/README.md) | 精选技能和参考资料 | 辅助知识，不是事实来源 | — |
| [`ci/`](ci/repo_quality.py) | 仓库契约门禁（链接、镜像、`SHA256SUMS`、白皮书装配、体积/命名）与 workflow 草案 | `.github/workflows/` 待有权限后激活（见 `docs/audits/2026-09-20_治理实现自审.md`） | `python3 ci/repo_quality.py` |
| [`tools/`](tools/README.md) | 仓库维护脚本（目前：`markitdown_sync.py` 生成/校验 Office·PDF 的 Markdown 镜像） | 持续维护 | `python3 tools/markitdown_sync.py --check` |

> 科研平台负责“已验证”，孪生平台负责“将被验收”：数据同源、口径全局唯一、重要数字必须有证据入口。两平台关系的完整表述见 `materials/孙承泽/孙承泽——9月工作阶段总结.docx` §五。

## 2026-09-19 组会后的三件事

1. **仓库归一**（已完成）：`wind_farm_viz` 的项目文件和历史迁入 `viz/`；本仓多余分支清理，迁移范围与例外见 `docs/12`；
2. **数字孪生 3×3 → 单列三风机**（✅ 已完成 R41–R42 · 2026-10-05）：布局可切换、3×3 不删、1×3 真值来自新 tandem3 oracle，见 `docs/13` + `docs/research/round41·round42`；
3. **材料与答辩 PPT**（新增职责）：统一入口为 `materials/`；历史 PPT / 讲稿 / 白皮书等已从 `viz/` 按人迁入 `materials/<姓名>/`（2026-09-21）。

## PINN 线（2026-10-03 交接）· 两份文档 + 一个未入库的交付包

9.19 方案定的「两条并行工作线」中，物理线（CFD / PINN）的第一份实质交付已在 2026-10-04 入库**说明文档**：

| 文件 | 日期 | 性质 | 内容 |
|---|---|---|---|
| [`materials/厉今飞/三台风机PINN模型交接与训练指南.docx`](materials/厉今飞/三台风机PINN模型交接与训练指南.docx) | 交接日期 **2026-10-03**（docx 自述）；**2026-10-04 00:06 由厉今飞发到微信群**（截图坐实，见下） | 交接指南 · 生成文件 | 厉今飞打包。已完成：原预训练模型加载、隐藏层冻结、**9 个控制输入 + 6 个目标输出**的结构改造、项目运行检查。参数账：原模型 3,090,200；保留的原有隐藏层 3,087,200（**冻结**）；新增控制输入连接 6,300；新六个输出层 18,006；**合计可训练 24,306（约占原模型 0.79%）**。三台机组共用原网络权重，各自输出层读取所在位置特征。46,329 B（微信显示 45.2K，吻合）；sha256 `5d8bdce36636…`；附 markitdown 镜像（20 份之一） |
| [`materials/厉今飞/PROJECT_DOCUMENTATION.md`](materials/厉今飞/PROJECT_DOCUMENTATION.md) | 2026-10-04 入库 | 项目说明 · 源文件 | 同一交付的 13 章说明版：`PINNs_multi_turbine_wake-outputchange/` 的目录结构、PINN 与尾流数学模型、执行盘模型、原始预训练架构与 OutputChange 迁移架构、四步训练流程、`project_config.json`、Rectangular/Diamond 网格原始训练、后处理与可视化、迁移学习、技术栈、11 条使用警告 |

**当前交付阶段 = 待数据训练。** 新增部分尚未学习真实工况与功率/有效风速的关系，**预测准确性尚未验证**；结构检查通过 ≠ 准确性验证（`PROJECT_DOCUMENTATION.md` §11.6 自己写明）。本版面向**固定三台机组布置、固定机型、固定来流**；入口风速、风向、湍流强度**尚未作为可变输入接入**。原预训练模型对应 **9 m/s、四台风机**的源工况，迁移到三机布局的准确性需验证。后续训练采用**有标签的迁移学习**，不运行原仓库的 RANS 与 k-ε 方程残差训练流程；可训练参数减少 **不等于** 计算时间按同比例减少（原隐藏层仍参与前向计算与新增连接的反向传播）。

**2026-10-04 00:06 群聊证据**（用户 2026-10-05 提供截图转录，见 [`materials/集体/聊天记录/群聊记录_2026-07-26至09-20.md`](materials/集体/聊天记录/群聊记录_2026-07-26至09-20.md) §2026-10-04）：厉今飞在群里**同时**发了这份 docx 和交付 zip。按 materials/README 规则 8「文件归属以截图里的发送人为准」，两份文档于 **2026-10-05 第二轮归位到 `materials/厉今飞/`**（`git mv`，保留原文件名），docx 同时补上 markitdown 镜像。

> ⚠ **交付包本体没有入库，且 603.8 MB 装不进普通 git。** 截图显示 zip 名为 `PINNs_multi_turbine_wake_simul…ange.zip`（即 `PINNs_multi_turbine_wake_simulation-outputchange.zip`）、**603.8 MB**，与 docx 同一条消息发出。这个体积**超过 GitHub 单文件 100 MB 硬限**（push 会被拒），也超过 Cloudflare Pages 单文件 25 MiB 约束；Git LFS 免费额度（1 GB 存储 / 1 GB 月流量）装得下但流量吃紧。docx §2 列明的包内内容（`prepare_pinn_outputchange.py`、`modify_pinn_io.py`、`OutputChange/prepared_9ms/original_frozen.keras`、`OutputChange/iochanged_9ms/untrained.keras` + `build_report.json` + 训练数据模板、`project_config.json`、原仓库代码与 LICENSE/README）**全部不在仓库**，因此当前无法复现、无法审阅。补交待办与存储方式裁定见 [`materials/README.md`](materials/README.md) §7 与 [`materials/厉今飞/README.md`](materials/厉今飞/README.md)。
>
> ✅ 2026-10-05 第二轮已解决原缺口 #2：两份文档从根目录归位 `materials/厉今飞/`，docx 补上镜像（镜像总数 19 → 20），[`docs/audits/2026-10-05_仓库整理与时间线主干.md`](docs/audits/2026-10-05_仓库整理与时间线主干.md) §5 缺口 #2 状态已更新为「已解决」。

---

# 数字孪生线（`twin/`）门面

> 目标：为西安交大风电场偏航优化项目打造**影院级、深色系、3D Web 数字孪生**（对标 51World/数字冰雹/Omniverse 的观感），部署至 Cloudflare Pages。
> 科研台 `viz/`（原 [wind-farm-viz.pages.dev](https://wind-farm-viz.pages.dev/)）保持封板不动；`twin/` 是它的**暗色旗舰姊妹篇**。

## 文档导航

| 文件 | 内容 |
|---|---|
| [`docs/01_调研报告_顶级数字孪生界面.md`](docs/01_调研报告_顶级数字孪生界面.md) | 18 组深搜 + 视觉拆解：顶级数字孪生 UI 三大流派、平台格局、风电专项、参考图录 |
| [`docs/02_实操方案_风电场3A数字孪生.md`](docs/02_实操方案_风电场3A数字孪生.md) | **主交付**：已验证的技术选型、3A 画质规格、架构、数据接入、8 阶段路线图、Cloudflare Pages 部署手册、性能预算、风险册 |
| [`docs/03_申请书一致性审计报告.md`](docs/03_申请书一致性审计报告.md) | **申请书边界**：数字孪生=研究内容③+阶段五法定交付物；里程碑 v0→v3 对齐 2027.06 结题；含原文勘误和裁决 |
| [`docs/04_视觉设计系统_冰青.md`](docs/04_视觉设计系统_冰青.md) | **冰青版视觉设计系统**：单青令牌、场景特征清单、3D 与 HUD 实现口径 |
| [`docs/05_还原度核对表.md`](docs/05_还原度核对表.md) | 视觉还原和交付核对 |
| [`docs/06_风机模型资产调研与自研决策.md`](docs/06_风机模型资产调研与自研决策.md) | 风机模型资产调研和自研决策 |
| [`docs/07_全面评审报告_问题清单与优先级.md`](docs/07_全面评审报告_问题清单与优先级.md) | 第二轮全面评审（A–E 五类问题） |
| [`docs/08_合并评审_最终清单.md`](docs/08_合并评审_最终清单.md) | **权威验收清单**：复核裁决、修复证据和验收门槛 |
| [`docs/09_R34_海洋真实化.md`](docs/09_R34_海洋真实化.md) | R34 海洋真实化：深度、配色、波光口径定型 |
| [`docs/10_R28-R32_地形海洋重做.md`](docs/10_R28-R32_地形海洋重做.md) | R28–R32 地形海洋重做全过程 |
| [`docs/11_R36_场景细化_海洋天空v2借鉴.md`](docs/11_R36_场景细化_海洋天空v2借鉴.md) | R36 场景细化和海洋/天空借鉴 |
| [`docs/research/`](docs/research/README.md) | 历轮研究记录、失败尝试、外部资料和截图证据 |
| [`skills/README.md`](skills/README.md) | 项目采用的精选技能及用途 |

截图参考资料位于 `docs/research/img/`，预期效果概念图位于 `docs/research/mockups/`；它们是设计和研究记录，不是工程测量证据。

## 历史选型期基线（2026-08-24）

> 本节是**选型期**的 PoC 数据（当时尚未有地形、海洋、森林等场景层），不要与最新验证或材料口径混读。

- Vite 8.2.2 + React 19.2.8 + TS 6.0.3 + three 0.185.1 + R3F 9.7.0 + drei 10.7.8 + `@react-three/postprocessing` 3.1.0 + zustand 5.0.15：**构建通过（1.18s，gzip 382KB）**，含 9 机阵列、物理天空、Bloom/SMAA/晕影 PoC；
- wrangler 4.125.0 可用；当时核验过 n8ao 2.0.1、`@takram/three-atmosphere` 0.19.1、`@gltf-transform/cli` 4.4.2、camera-controls 3.1.2、echarts 6.1.0、uplot 1.6.32、maath 0.10.8、gsap 3.15.0；
- Cloudflare Pages 硬约束登记：单文件 ≤25 MiB、20,000 文件、带宽免费；Workers Static Assets 为官方新推荐，迁移零成本预留。

## 当前验证状态

本轮在 2026-09-20 沙箱、当前分支执行：

```bash
cd twin
npm run verify
```

结果：**lint 0 warnings / 0 errors；selftest 145 通过 / 0 失败；TypeScript 检查通过；Vite production build 通过。** 该结果只证明当前代码在本次环境下通过对应门禁，不替代真实硬件、现场数据或领域审阅。

### R42 视觉取证基线（2026-10-05，当前有效）

单列三机改造后的重测（1280×720、SwiftShader、固定机位 `?q=…&t=15&cam=60,22,990`；计数=确定值，帧时长只作档间相对）。
**上节 R40 的 267/642,556 等旧数自此作废，只作历史留档。**

| 布局 | 档 | draw calls | tris | lines |
|---|---|---|---|---|
| 3×3 | high | 267 | 586,756 | 48,880 |
| 3×3 | medium | 264 | 567,064 | 48,180 |
| 3×3 | low | 231 | 440,060 | 47,730 |
| **1×3** | high | 267 | **549,556**（−6.3%） | 48,880 |
| **1×3** | medium | 264 | 529,864 | 48,180 |
| **1×3** | low | 231 | 440,060 | 47,730 |

取证新增 `?freeze=1`（渲染相位冻结，同参数两次渲染逐像素可比，见 `docs/research/round42` §2）。

### R40 视觉取证基线（2026-09-17，历史留档，数字已作废）

以下数字来自固定机位和 `npm run perftier` 的历史取证，不是本轮 `npm run verify` 重新测得的硬件性能：

| 指标 | 实测值 | 测法 |
|---|---|---|
| `npm run selftest` | **145 通过 / 0 失败** | Node 22 原生类型剥离，无浏览器依赖；R40/R40b 声场、草地、执行器断言已纳入 |
| `npx tsc -b --noEmit` | **0 错误** | TypeScript 检查 |
| `npm run lint` | **0 warnings / 0 errors**（当时 52 files） | oxlint 1.79 |
| `npm run build` | **通过（当时 1.36s）** | Vite + rolldown |
| 渲染计数（`?q=high&t=15&cam=60,22,990`） | **267 draw calls / 642,556 tris / 48,880 lines** | `npm run perftier`（`window.__aeolus_stats()` 单帧手动计数） |
| 画质分档 | high 267c/642,556t · medium 264c/567,064t · low 231c/440,060t | 同一探针；草地 low 档零绘制 |
| 产物体积 | JS gzip 合计 **468 kB** · CSS 162 kB | `vite build` reporter |

> 旧文档里反复出现的“22 断言 / 35 draw calls / 84 断言 / 250 draw calls”是 2026-08-28 v3 交付轮与 R38 轮的历史口径，**已作废**，以 R40 取证和当前命令输出为准。
> 沙箱为 SwiftShader 软件渲染（本沙箱仅 2 核），**帧率绝对值不可用作真实硬件结论**，只作档间相对比较；实机 GPU 需另行验收。

## 研究与验收索引

| 文件 | 内容 |
|---|---|
| [`docs/07_全面评审报告_问题清单与优先级.md`](docs/07_全面评审报告_问题清单与优先级.md) | 第二轮全面评审（A–E 五类问题） |
| [`docs/08_合并评审_最终清单.md`](docs/08_合并评审_最终清单.md) | **权威清单**：复核裁决、逐项修复证据和验收门槛 |
| [`docs/09_R34_海洋真实化.md`](docs/09_R34_海洋真实化.md) | R34 海洋真实化 |
| [`docs/10_R28-R32_地形海洋重做.md`](docs/10_R28-R32_地形海洋重做.md) | R28–R32 地形海洋重做 |
| [`docs/research/round36_海岸真实化与远岸森林.md`](docs/research/round36_海岸真实化与远岸森林.md) | R36/R36b/R36c/R37 权威记录：岸距场、碎浪、地平线、卷云、远岸森林、夜陆和日照金山 |
| [`docs/research/round38_残项收口与裁决.md`](docs/research/round38_残项收口与裁决.md) | R38 残项收口、孤儿分支裁决 |
| [`docs/research/round40_声场真实化_草地挂载_偏航执行器.md`](docs/research/round40_声场真实化_草地挂载_偏航执行器.md) | R40 声场、草地和偏航执行器验证 |
| [`HANDOFF_NEXT.md`](HANDOFF_NEXT.md) | 当前阶段交接、开放项与红线；[`HANDOFF.md`](HANDOFF.md) 为历史交接 |
| [`twin/README.md`](twin/README.md) | 数字孪生运行、自检、调试键和口径说明 |
| [`docs/12_两仓归一_wind_farm_viz迁入与分支清理.md`](docs/12_两仓归一_wind_farm_viz迁入与分支清理.md) | 两仓归一台账、来源分支、历史映射、Pages 重连、分支清理和 3×3 留档 |
| [`docs/13_0919组会决议_三风机改造方案与3x3留档.md`](docs/13_0919组会决议_三风机改造方案与3x3留档.md) | 9/19 组会决议和“3×3 → 单列三风机”逐文件改造清单 |
| [`materials/README.md`](materials/README.md) | 对外材料入口、历史材料索引和写材料数字口径 |

## 当前协作原则

1. 实质工作先建 Issue；
2. 从独立分支提交 PR，不直接修改 `main`；
3. 关键数字、物理结论、数据口径和对外材料至少双人审阅；
4. 实验记录必须包含输入、代码 commit、环境、命令、结果和限制；
5. 源文件、生成产物和提交快照分开管理；
6. Git + manifest + SHA-256 是当前数据管理基线，DVC/Kedro 只有在真实需求证明必要后才引入。

## 数据口径

所有平台和材料统一使用：

- **真实**：有明确离线计算、来源或实验记录的结果；
- **代理**：浏览器端或简化模型推算；
- **演示**：用于界面展示的确定性数据，不代表实时场站值；
- **示意**：几何、构图或概念表达，不代表工程测量。

科研可视化和数字孪生的当前数字、限制与复现入口见 [`docs/evidence/README.md`](docs/evidence/README.md)、[`viz/README.md`](viz/README.md) 和 [`twin/README.md`](twin/README.md)。

## 远端自动化状态

两份只读工作流草案已提交到 [`ci/workflow-drafts/`](ci/workflow-drafts/)，本地 `.github/workflows/` 也已准备好对应文件；但本次推送被 GitHub App 以缺少 `workflows` 权限拒绝，因此远端当前**尚未**有可执行的 `.github/workflows/` 文件。重新连接具备该权限的 GitHub 后，才能把草案移入 `.github/workflows/` 并验证运行。当前远端 labels 已建立，Project 和 `main` branch protection 仍因 GitHub App 权限限制未配置；工作流文件入库也不等于状态检查已成为合并门禁，这些状态都需分别实际验证。配置蓝图见 [`docs/project/`](docs/project/README.md)。

## 当前阶段

- 两仓归一已经完成，但迁移边界仍按 `docs/12` 区分，不把外部技能仓、聊天、外部数据或原仓库生态默认视为已迁入；
- `viz/` 继续封板维护；
- `twin/` 已完成单列三机（1×3）改造（布局可切换、3×3 留档 tag `twin-3x3-archive-20260919`）；1×3 数字以 tandem3 oracle 为准（`docs/research/round42`）；
- 五人协作、实验记录、证据卡、材料审阅和仓库质量门禁已经进入实施阶段；
- 已用 Issue `#13` → PR `#12` → `EVID-2026-001` → `materials/README.md` 试跑一条真实验证闭环（Issue 随 2026-09-21 的 PR 关闭；队友复核改在证据卡 §6 打勾跟踪）；
- 后续继续处理 GitHub 权限、Project、分支保护和其他领域的真实研究任务。

详细研究历史、阶段数据和验收记录请从 [`docs/`](docs/README.md) 进入，不在根 README 复制所有轮次细节。

## 优化控制完整交付（2026-10-07，2026-10-21 并入 main）

[优化工作总索引](optimization_control/WORK_INDEX.md) 与 [洪祖名完整交付](materials/洪祖名/20261007_optimization_handoff/README.md) 原在独立分支 `codex/optimization-handoff-20261007`（`84d6f4b` + `782368a3`），**2026-10-21 随分支吸收并入主线**（PR #17）。内容包括代理模型、PPO、随机入口、MADDPG、统一传统基线及诊断；**当前固定九输入网络的结果仅为合成联调，可靠性门槛未全部通过**，不能当作 `main` 的结论引用。交付包本体 **≈1.01 GiB**（58 个分卷，单卷 ≤95 MiB），入库理由、体积代价与待裁定项见 [`docs/audits/2026-10-21_分支吸收与合并审计.md`](docs/audits/2026-10-21_分支吸收与合并审计.md) 与 [`materials/README.md`](materials/README.md) §7。
