# HANDOFF · 交接给下一任 Agent

> 🗄️ **已被取代**｜这是**第 2 任 Agent** 的交接，历史价值为主。现行交接：[`HANDOFF_NEXT.md`](HANDOFF_NEXT.md)（2026-10-24 刷新，含「不要完全相信这份文件」声明）。


> **本文件是「Agent 交接」分区明细的历史部分**（第 2 任 → 第 3 任）。全项目时间线主干见 [`docs/project/TIMELINE.md`](docs/project/TIMELINE.md)；现行交接与开放项见 [`HANDOFF_NEXT.md`](HANDOFF_NEXT.md)。
>
> **⚠️ 本文件是「第 2 任 → 第 3 任」的历史交接（写于 2026-08-28），正文中的分支名/数字/工具体检均已过期。**
> 保留价值：§0 三句忠告、§2 用户偏好、§8 红线——这四节仍是现行口径。
> **当前进度与开放项一律看** [`HANDOFF_NEXT.md`](HANDOFF_NEXT.md)；
> 场景层权威记录看 `docs/research/round36_海岸真实化与远岸森林.md`（含 R36b/R36c/R37）
> 与 `docs/research/round38_残项收口与裁决.md`。
>
> 过期数字速查（以 2026-09-13 复测为准）：selftest `34/34` → **84/84**；lint `23 warnings` → **0/0**；
> 仓库 `sunccchengze/0824-2026` → **`sunccchengze/Dachuang-SZLS`**；
> §3 的手搓 NSS 编译配方 → **`bash twin/scripts/bootstrap.sh`**（桩库，2 秒）；
> §3「调试参数记得最终清掉」→ **已收口**：生产构建 `?debug=1` 才解锁（docs/08 D10）。

> 写于 2026-08-28，由本仓第 2 任维护者（评审者）留下。你是第 3 任。
> **你的任务：复核我的评审 → 独立再评一遍 → 合并两版为最全清单 → 按优先级把问题全部修好。**

---

## 0 · 给你的三句忠告（用户原话精神）

1. **不要过于依赖我留给你的东西。** 我的评审结论（docs/07）本身也要被你质疑——我已把自认站不住脚的 7 处写进 docs/07 §7"复审提示"，那是起点，不是终点。
2. **不要照抄，要在我的基础上发散性思考、继续发扬。** 你比前一任更强，标准应该更高，而不是把我的清单当考卷逐题打钩。
3. **独立、批判性地思考。** 每个结论先自己验证（截图/测量/查文献），再决定采纳、推翻或升级。

---

## 1 · 仓库与项目坐标

| 项 | 值 |
|---|---|
| **主仓库** | https://github.com/sunccchengze/Dachuang-SZLS （本仓，main 分支；历史名 `0824-2026` 已弃用） |
| 项目目录 | `twin/`（Vite 8 + React 19 + TS + three 0.185 + R3F 9 + drei + @react-three/postprocessing + zustand） |
| 历任分支 | 第 1 任 `arena/01a03669-0824-2026`（视觉搭建期）· 第 2 任 `arena/01a03e22-0824-2026`（本文件作者，全量评审 docs/07） |
| 技能库来源 | https://github.com/sunccchengze/-SKILL- （26 个技能包，已装在 `skills/`，索引见 `skills/README.md`） |
| 大创申请书 | 据 docs/03：终版在用户的 `wind_farm_viz` 分支（不在本仓），关键承诺已摘录进 docs/03 |
| 原始参考图（视觉真值） | `docs/research/mockups/user_original_微信图片_174_2.png`（用户原图，一切视觉口径的最终裁判）；已认可的白线稿效果样本 `docs/research/shots/r7_white_no_turbine_bloom.png` |

**项目性质**（读 docs/01-06）：这是大学生创新训练项目（西安交大，负责人厉今飞，本项目成员孙承泽）的**结题法定交付物**——"多机协同智能功率控制与数字孪生演示平台"。申请书研究内容③原文："构建一个风电场的线上运维系统，通过输入目前所需求的功率，系统能够实时输出并调整各个风机的偏航角"。这不是普通炫酷大屏，**闭环控制叙事是验收点**。

## 2 · 用户是谁（沟通规范）

- **中文回复**，永远。
- 审美极挑剔：要**克制、高级、科幻**——不要霓虹灯管、不要过曝、不要粗亮发光；线条要纤细优雅。
- 风机必须是**纯白线稿全息**，任何角度都不得变暗变灰；粒子/电缆亮度必须**视角无关**。
- **信息准确性、建模精准度**要求极高（本次评审的 A/B 类就是按这个标准打的）。
- 每个问题要**理解到根因再修**，不要贴参数创可贴；**要拿实拍截图/测量数据证明修好了**，不要空谈。
- 用户会亲自盯预览，糊弄会被当场指出。

## 3 · 环境 & 工具（沙箱重置后必读）

```bash
bash twin/scripts/bootstrap.sh          # ★ 一键恢复：npm install + /tmp/nsslibs 桩库 + 解压 chromium
cd twin && npm run dev -- --host 0.0.0.0 # 端口 5173；node_modules 每次沙箱重置都会被清空
npm run build && npx tsc -b --noEmit     # 构建与类型检查（2026-09-13 复测：✓ 1.36s / 0 错误）
npm run lint                             # oxlint：0 warnings 0 errors（52 files）
npm run selftest                         # 84 断言（数据契约 + 渲染口径回归锁）
npm run perftier                         # 三档画质单帧计数 + 帧时长（需先 build+preview）
```

- **无头截图**：`node scripts/shot.mjs <url> <out.png> [waitMs] [w] [h]`（puppeteer + @sparticuz/chromium + SwiftShader 软渲染）。
  ⚠️ 依赖 `/tmp/nsslibs`（NSS/NSPR 共享库，沙箱重置即丢）——**用上面的 `bootstrap.sh` 即可**（`gcc` 编桩库，约 2 秒）。
  旧配方（源码编译整套 NSS，30 分钟起、且 signtool 会因缺 zlib.h 报错）已被 `scripts/nss_stub.c` + `nss_version.map`
  的 47 符号桩库取代（2026-08-31 起为权威方式，见 Round-10 记录）。
- **A/B 帧差分析**：`python3 scripts/abdiff.py <on.png> <off.png> <label>`（需 `pip install --break-system-packages pillow numpy`）。
  另有 `framestats.py`（全局亮度/饱和）、`horizoncheck.py`（地平线台阶剖面）、`moontrack.py`（月轨连续性）。
- **调试参数**（生产构建默认关闭，需 `?debug=1` 解锁；dev 常开——docs/08 D10 已收口，不再是待清项）：
  - `?cam=方位角,俯仰角,距离[,目标x,y,z]`——任意摆机位截图（CameraRig.tsx）；`?t=10.2` 锁时刻并暂停（A/B 可复现）；
  - `?noveil=1` 关风纱层（归属定位）· `?q=low|medium|high` **锁**画质（R36 起才是真锁）· `?intro0=1` 跳过开场。
- 开场运镜 34s **已可跳过**（Esc/空格/点击/书签键/`?intro0=1`/debug 机位自动跳过）；但截图仍建议带 `?cam=` 锁机位以对齐历轮口径。
- ⚠️ **帧率数字不要用沙箱值**：SwiftShader 软件渲染（且沙箱常为 2 核）与实机 GPU 差一个量级；只用于档间相对比较。

## 4 · 场景代码地图（`twin/src/`）

> ⚠️ **本表写于 2026-08-28，"现状要点"列是当时的缺陷清单**：其中 B7/A4/A6/A8/C1/C5/D3/D7 已在
> `docs/08`（P0/P1 收口）与 R29–R37 场景重构中解决，别再照着它找问题；**"职责"列仍然有效**。
> R29 之后的新增/重写：`scene/WorldTerrain.tsx`（地形+海洋双层自定义着色器，R36 岸距场/碎浪/swash，R37 色温消费）、
> `scene/SkyAurora.tsx`（程序星野+极光+白昼卷云+日月视差修正）、`scene/treeField.tsx`（实例化远岸森林，新建）、
> `scene/hotkeys.ts`（9 机位取景真值源 + 约束 + 诊断，新建）、`scene/grassField.tsx`（草地，**R40 校正 2026-09-17：已挂载**，见 docs/research/round40）、
> `data/farmSim.ts`（唯一真值源 + `dayNight`/`sunWarmth`）、`data/turbinePhysics.ts`（FLORIS nrel_5MW 表 + Jensen）、
> `data/telemetry.ts`（接入契约 Demo/Ws）、`data/debug.ts`（`?debug` 门控）。

| 文件 | 职责 | 现状要点 |
|---|---|---|
| `App.tsx` | Canvas 装配、4 灯+半球光、FogExp2、dpr[1,2.5] | 灯光只照亮地形 PBR（C7） |
| `scene/terrainUtil.ts` | **世界真值源**：terrainHeight、FARM 3×3、SUBSTATION、CAM、ANCHOR | 间距已改 632m = 5.02D（B7 已消解）；R36 起含 `shoreSigned` 岸距场与 `treeAccept` 落位真值 |
| `scene/HoloTurbine.tsx` | 纯白线稿风机：fresnel 壳 + EdgesGeometry + 手工肋线 + halo | depthTest:false 全家桶（C1） |
| `scene/turbine/geometry.ts` | NREL 5MW 参数化几何（18 站位/塔筒放样/机舱） | B1-B6 硬伤在站位表与翼型公式 |
| `scene/TurbineField.tsx` | 9 机布置 + 舵机联动 | `yawDeg+8` 魔法数、转子朝向（A4） |
| `scene/CableNetwork.tsx` | Line2 屏幕空间等宽电缆 + 脉冲 + 晶粒 | 9 条放射拓扑（A8）、CPU getPointAt（D3） |
| `scene/WindVeil.tsx` | 风况粒子：11 条列向来流 + 6 条远脊来流（北→南） | 与风机朝向的矛盾见 A4 |
| `scene/SparkleGround.tsx` | 地面星芒点云 4600 | depthTest:true（与其它全息层不一致） |
| `scene/Substation.tsx` | 玻璃升压站 | 76m 巨盒比例失真（A8） |
| `scene/WorldTerrain.tsx` / `SkyAurora.tsx` / `Callouts.tsx` / `Effects.tsx` / `EnvSetup.tsx` / `CameraRig.tsx` | 地形 PBR+程序细节 / 天空球 / DOM 引线标注 / SMAA+CA+Noise+Vignette / PMREM / 34s 运镜 | CA 撕白线（C 类测量）、标注悬空（A6）、运镜不可跳（C5） |
| `state/simStore.ts` | 舵机/时间轴/报警/矩阵（全静态假数据） | SERVO_TID 死代码（D7） |
| `hud/Hud.tsx` + `styles/theme.css` | 1920×1080 大屏 HUD | A1/A2/A3 术语与数值硬伤聚集地 |

## 5 · 已完成工作（第 1-2 任累计）

1. **第 1 任**：项目搭建、NREL 5MW 参数化几何、地形/天空/升压站/HUD 像素级还原、34s 开场运镜。
2. **第 2 任（我）**：
   - HoloTurbine 全面重写（修复"填充白色"事故，改 EdgesGeometry+肋线纯白线稿）；
   - 基座能量环视角无关化；
   - CableNetwork 从 TubeGeometry 改 Line2（修复视角相关亮度），剥离霓虹灯管感；
   - WindVeil 修正风语义（删除横贯第二排的 3 条"银河弧带"，统一为北→南列向来流+远脊来流，材质 depthTest/fog/toneMapped 全关）；
   - 删除孤儿 torus 标注、修英文错字；
   - 建立无头截图+A/B 差分验证链路（含沙箱内源码编译 NSS）；
   - **全量评审 → `docs/07_全面评审报告_问题清单与优先级.md`（A/B/C/D/E 五类 + P0/P1/P2 + §7 自我质疑）**。

## 6 · 你的工作流（建议）

1. **读** docs/07（含 §7）+ 本文件 + docs/01-06（尤其 03 的一致性审计）。
2. **复核**：对 docs/07 每条结论亲自验证（截图/测量/查 NREL 与电网规程原文）；§7 列的 7 处存疑点逐条裁决。
3. **独立盲评**：忘掉我的清单，自己从零再评一遍——你会找到我漏掉的东西（我已知自己没查的：暗色主题下的 HUD 对比度量化、字体渲染层叠、多帧时间序列稳定性、`skills/testing-data-visualizations` 里的差分测试范式、性能基线profiling……）。
4. **合并**：两版评审去重合并成唯一权威清单（建议 `docs/08_合并评审_最终清单.md`），标注每条的验证证据。
5. **修复**：P0（9 项）→ P1（14 项）→ P2。修一项销一项，每项附前后对比截图。**先跟用户确认 A1 术语订正清单与 A4 风向语义二选一，再动 HUD 和机舱朝向**（这两处涉及"忠实还原用户原图"的边界，别自作主张）。
6. **提交**：小步提交到你的工作分支，说清楚为什么；不要把 node_modules/dist 提进去（.gitignore 已建）。

## 7 · 技能包使用指引（`skills/`，索引在 `skills/README.md`）

修复期最可能用上的：
- `game-playtest` —— 浏览器端截图 QA/自动化巡检范式（配合我的 shot.mjs）；
- `testing-data-visualizations` —— 可视化差分/契约测试（把 A/B 差分升级成回归测试，治 D2）；
- `react-three-fiber-game` / `three-webgl-game` —— 场景组织、合批、GPU 粒子化（治 D3/D4）；
- `visualization-strategy-and-critique` —— 设计评审框架（你的独立盲评可套用）；
- `scientific-visualization` —— **科研可视化诚信规范**（治 A7 虚假宣称、E7 V&V 时必读）；
- `dashboards-and-real-time-visualization` —— 大屏版式与流式数据联动（治 A5、E1-E3）；
- `performance-optimization` / `web-perf` / `react-performance` —— 治 D3-D5。

用法规：目录即技能包，先读该包 `SKILL.md`，再按需展开 `references/`；它们是弹药库不是圣旨——**与你自己的判断冲突时，以实测为准**。

## 8 · 红线（沿袭项目既定边界，docs/03）

- 全息线稿美学不回退：不再引入写实 PBR 机身、不再开 Bloom 糊白线；
- 不虚构数据来源：接不了真 FLORIS 就明写"演示数据"，meta/README 与实现必须一致（A7 的教训）；
- 大改前给用户看对比图，获认可再铺开。

祝顺利。这个项目的底子配得上更高的标准，别辜负它。
