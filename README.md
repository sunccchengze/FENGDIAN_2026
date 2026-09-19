# Dachuang-SZLS · 风电场偏航优化大创项目 · 可视化与数字孪生（唯一仓库）

> 西安交通大学 · 国家重点领域大学生创新训练项目《融合数据-物理驱动的风电流场智能感知与智能调控研究》（2026.04–2027.06）
> 可视化与数字孪生模块负责人：孙承泽 ｜ 导师：李良星 副教授
>
> **2026-09-19 起本仓是项目可视化线的唯一仓库**：前身仓库 `wind_farm_viz`（科研可视化平台，2026-07 底 → 09-14）
> 已连同全部提交历史迁入 `viz/`，原仓库由用户删除。迁入台账见 [docs/12](docs/12_两仓归一_wind_farm_viz迁入与分支清理.md)。

## 🗂 仓库结构：一条证据链、两套平台

| 目录 | 平台 | 状态 | 入口 |
|---|---|---|---|
| [`viz/`](viz/README.md) | **科研可视化平台**（15 页浅色瑞士网格科研台，FLORIS/POD/PPO 真值全量呈现） | **封板 v1.3-final**（2026-08-19），只修 bug/死链/数据错 | `cd viz && python3 -m http.server 8000 --directory site`；线上 [wind-farm-viz.pages.dev](https://wind-farm-viz.pages.dev/)（Pages 需重连本仓，见 docs/12 §4.2） |
| [`twin/`](twin/README.md) | **AEOLUS TWIN 数字孪生**（影院级深色 3D Web 大屏，申请书阶段五法定交付形态） | 持续迭代（R40）；**当前 3×3，组会决议改单列三机**，3×3 留档 tag `twin-3x3-archive-20260919` | `cd twin && npm install && npm run dev`；改造方案 [docs/13](docs/13_0919组会决议_三风机改造方案与3x3留档.md) |
| [`materials/`](materials/README.md) | 对外材料（阶段总结 / 答辩 PPT / 申报） | 9 月阶段总结已入库 | — |
| [`docs/`](docs/) | 数字孪生线文档 01–13 + `research/` 历轮记录与截图证据 | — | — |
| [`skills/`](skills/README.md) | 精选 27 项技能（来源 `-SKILL-` 仓库） | — | — |

> 科研平台负责"已验证"，孪生平台负责"将被验收"：数据同源、口径全局唯一、钦定数字只有一份出处。
> 两平台关系的完整表述见 `materials/孙承泽——9月工作阶段总结.docx` §五。

## 🧭 2026-09-19 组会后的三件事

1. **仓库归一**（已完成）：wind_farm_viz 183 提交 → `viz/`；本仓多余分支清理，只留 `main` + 工作分支；
2. **数字孪生 3×3 → 单列三风机**（方案已出，下一轮动工）：布局可切换、3×3 不删，见 docs/13；
3. **材料与答辩 PPT**（新增职责）：入口 `materials/`。

---

# 以下为数字孪生线（`twin/`）门面 · 0824-2026 起

> 目标：为西安交大风电场偏航优化项目打造**影院级、深色系、3D Web 数字孪生**（对标 51World/数字冰雹/Omniverse 的观感），部署至 Cloudflare Pages。
> 科研台 `viz/`（原 [wind-farm-viz.pages.dev](https://wind-farm-viz.pages.dev/)）保持封板不动；`twin/` 是它的**暗色旗舰姊妹篇**。

## 📚 文档导航
| 文件 | 内容 |
|---|---|
| [docs/01_调研报告_顶级数字孪生界面.md](docs/01_调研报告_顶级数字孪生界面.md) | 18 组深搜 + 视觉拆解：顶级数字孪生 UI 三大流派、平台格局、风电专项、参考图录 |
| [docs/02_实操方案_风电场3A数字孪生.md](docs/02_实操方案_风电场3A数字孪生.md) | **主交付**：已验证的技术选型（+版本核验）、3A 画质规格清单、架构、数据接入、8 阶段路线图、Cloudflare Pages 部署手册、性能预算、风险册 |
| [skills/README.md](skills/README.md) | 从用户技能库装载的 26 项技能及用途 |
| [docs/03_申请书一致性审计报告.md](docs/03_申请书一致性审计报告.md) | **已按申请书终版原文逐字对表**：数字孪生=研究内容③+阶段五的法定交付物；里程碑 v0→v3 对齐 2027.06 结题；含原文勘误 3 处与 5 项裁决 |
| [docs/04_视觉设计系统_冰青.md](docs/04_视觉设计系统_冰青.md) | **已定稿·冰青版**（用户 08-24 上传原图钦定，取代金翡版）：单青令牌、场景特征清单（极光/星光/冰河集电）、3D 与 HUD 实现口径 |
| docs/research/img/ | 顶级大屏参考图 5 张 |
| docs/research/mockups/ | **预期效果概念图**（AI 生图并经两轮导演修图）：`styleA_deepblue_v2.png` 深蓝全息风、`styleB_amber_v2.png` 琥珀金工业风 |

## ✅ 已验证基线（2026-08-24 沙箱实测 · 技术选型 PoC）
> 本节是**选型期**的 PoC 数据（当时尚未有地形/海洋/森林等场景层），不要与下方「当前状态」表混读。
- Vite 8.2.2 + React 19.2.8 + TS 6.0.3 + three 0.185.1 + R3F 9.7.0 + drei 10.7.8 + @react-three/postprocessing 3.1.0 + zustand 5.0.15：**构建通过（1.18s，gzip 382KB）**，含 9 机阵列/物理天空/Bloom/SMAA/晕影 PoC
- wrangler 4.125.0 可用；npm 核验：n8ao 2.0.1、@takram/three-atmosphere 0.19.1、@gltf-transform/cli 4.4.2、camera-controls 3.1.2、echarts 6.1.0、uplot 1.6.32、maath 0.10.8、gsap 3.15.0
- Cloudflare Pages 硬约束登记：单文件 ≤25MiB、20,000 文件、带宽免费；Workers Static Assets 为官方新推荐（迁移零成本预留）

## 🚦 当前状态（2026-09-17 实测，R40 声场/草地/执行器轮）
**v3 演示平台已交付并持续细化**：`twin/`（AEOLUS TWIN）。docs/07 评审 + docs/08 合并清单全部 P0/P1 修复并实测验收，
场景自 R29 起已推进到 R40（海洋/海岸/天空/色温/声场/草地/偏航执行器）。本轮（2026-09-17）在 `arena/01a0ae5c-dachuang-szls` 复测的**权威数字**
（过程与根因见 `docs/research/round40_声场真实化_草地挂载_偏航执行器.md`）：

| 指标 | 实测值 | 测法 |
|---|---|---|
| `npm run selftest` | **145 通过 / 0 失败** | Node 22 原生类型剥离，无浏览器依赖（R40 新增声场/草地/执行器 36 断言 + R40b 修正 3） |
| `npx tsc -b --noEmit` | **0 错误** | — |
| `npm run lint` | **0 warnings / 0 errors**（52 files） | oxlint 1.79 |
| `npm run build` | **✓ 1.36s** | Vite 8 + rolldown |
| 渲染计数（`?q=high&t=15&cam=60,22,990`） | **267 draw calls / 642,556 tris / 48,880 lines** | `npm run perftier`（`window.__aeolus_stats()` 单帧手动计数） |
| 画质分档 | high 267c/642,556t · medium 264c/567,064t · low 231c/440,060t（与 R39 基线同探针实测**完全一致**：草地 low 档零绘制） | 同上，三档同参 |
| 产物体积 | JS gzip 合计 **468 kB**（three 单包 384 kB + 业务 58 kB + floris3d 26 kB）· CSS 162 kB | `vite build` reporter |

> 旧文档里反复出现的「22 断言 / 35 draw calls / 84 断言 / 250 draw calls」是 2026-08-28 v3 交付轮与 R38 轮的口径，**已作废**，以本表为准。
> **一条命令跑齐四条闸门**：`cd twin && npm run verify`（lint + selftest + tsc/build）。
> CI：`ci/qa-gates.yml` 已备好但**尚未生效**——本仓 GitHub App 无 `workflows` 权限，需人执行
> `mkdir -p .github/workflows && git mv ci/qa-gates.yml .github/workflows/ && git push` 启用（见该文件头注释）。
> 沙箱为 SwiftShader 软渲染（本沙箱仅 2 核），**帧率绝对值不可用作结论**，只作档间相对比较；实机 GPU 需另行验收。

数据口径三分法（真实/演示/示意）已上界面角标与 README。文档索引补充：

| 文件 | 内容 |
|---|---|
| [docs/07_全面评审报告_问题清单与优先级.md](docs/07_全面评审报告_问题清单与优先级.md) | 第二轮全面评审（A-E 五类 63 项） |
| [docs/08_合并评审_最终清单.md](docs/08_合并评审_最终清单.md) | **权威清单（终版）**：复核裁决 + 逐项修复证据 + 验收门槛对照 |
| [docs/09_R34_海洋真实化.md](docs/09_R34_海洋真实化.md) | R34 海洋真实化（深度/配色/波光口径定型） |
| [docs/10_R28-R32_地形海洋重做.md](docs/10_R28-R32_地形海洋重做.md) | R28–R32 地形海洋重做全过程 |
| [docs/research/round36_海岸真实化与远岸森林.md](docs/research/round36_海岸真实化与远岸森林.md) | R36/R36b/R36c/R37 权威记录：岸距场/拍岸碎浪/地平线收边/白昼卷云/远岸森林/夜陆去灰白/日照金山 |
| [docs/research/round38_残项收口与裁决.md](docs/research/round38_残项收口与裁决.md) | **R38 本轮**：残项清单逐项收口 + `arena/01a074a3` 孤儿分支裁决 |
| [docs/research/](docs/research/) | 历轮 round*.md（11–38）+ [shots/](docs/research/shots/) 截图证据链 |
| [HANDOFF_NEXT.md](HANDOFF_NEXT.md) | 当前阶段交接（开放项与红线）；[HANDOFF.md](HANDOFF.md) 为第 2 任历史交接 |
| [twin/README.md](twin/README.md) | 演示平台运行/自检/调试键/口径说明 |
| [docs/12_两仓归一_wind_farm_viz迁入与分支清理.md](docs/12_两仓归一_wind_farm_viz迁入与分支清理.md) | **2026-09-19 两仓归一台账**：来源分支、filter-repo 三步、旧 SHA 对照表（附件 tsv）、Cloudflare Pages 重连、分支清理、3×3 留档 tag 用法 |
| [docs/13_0919组会决议_三风机改造方案与3x3留档.md](docs/13_0919组会决议_三风机改造方案与3x3留档.md) | **9/19 组会决议** + 「3×3 → 单列三风机」逐文件改造清单（布局可切换设计、1×3 oracle、验收门槛） |
| [materials/README.md](materials/README.md) | 对外材料入口：9 月阶段总结 docx、历史 PPT/讲稿索引、写材料数字口径 |
