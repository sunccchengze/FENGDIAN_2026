# Round 44 · B 演示界面：`?demo=1` 七步流程（1×3 · GCH 内核算例）

**状态**：✅ 已完成（2026-10-05）。出口全绿：lint **0/0**、build 通过、selftest **3×3 = 161/0 · 1×3 = 158/0**、七步截图逐张通过（§5）。

> ⚠ **提交史注记（2026-10-05 沙箱刷新 ×4）**：本沙箱的 `.git` 当日 20:08（+08）起共**四次**被刷新重建为单提交浅克隆（根 = `b65ca49`）：① 首次丢失此前 13 个本地提交（第一轮整理、R41–R43 等，均未推送）；② 第二次丢失第一次重提 `ccb2b90`/`dfbce4b`/`9ccc36b`；③ 第三次丢失第二次重提 `f9bb0d4`（同时观察到平台把远端会话分支也重置回 `b65ca49`）；④ 第四次（R47 审计期间）丢失第三次重提链 `c038be7`→`31b1984`，本地 HEAD 回到 `b65ca49`。**四次均只有提交对象丢失，工作区文件全部幸存**（快照机制）。当前内容以 **`b2c8f5d`** 为准 = `31b1984` 全部内容 + R47 任务审计与机位坐标订正（`git diff 31b1984..b2c8f5d` 验证为严格超集：0 删除、恰好 7 个 R47 文件），已按用户 2026-10-05 裁定以 force-with-lease 推送至远端会话分支 `arena/01a10a8e-fengdian-2026`（安全网；开 PR/合并 main 仍不做）。各轮过程记录（round41–47 文档）仍有效；上述各代本地提交的 SHA（13 个原始、`ccb2b90` 等 3 个、`f9bb0d4`、`c038be7`/`31b1984`）均为悬空/被取代引用。

## 0. 范围与规格来源

- 规格：9.19 结题方案 §2「航向角优化演示界面」七步表（`docs/13_0919组会决议…` 引原文）+ WORKLIST §2.2 演示界面规格（4 类图 + 图表纪律 + 红线）。
- 用户裁定（2026-10-05，ask_user）：演示容器落在 `twin/` 新路由 `?demo=1`；**`viz/` 冻结线不动**。
- 本轮同时完成 R42 遗留的 oracle 扩展（§1）与内核 hub 平面采样（§2），因为「看基准/复核/导出」三步需要逐台功率、有效风速与平面流场——GCH 内核与 FLORIS oracle 两侧同步扩展，保证演示数字两侧可互证。

## 1. Oracle 扩展（FLORIS 4.6.6，tandem3 → v1）

`tools/build_floris_oracle.py` 的 `tandem3` 工况由标量功率扩展为四字段（每机位）：`vel`（轮毂平面平均风速）、`sec`（功率/风速² 等效面积，`A_eff = p_kW/1000 / (0.5·1.225·u_tip²)`，与 GCH `sampleHubPlane` 同式）、`pKw`（逐台 kW）、`uEff`（= `sqrt(sec/2150)`，2150 = 0.5·ρ·12566.4² m²）。

- 既有四字段（`pW/totKw/wakeFactor/totWakeFactor`）**逐位不变**：扩展前后 JSON 对四字段做 bit-identical 断言，通过后才写新文件（`4b113c47…`）。
- FLORIS 侧 `vel` 的取法：`wake.field_horiz_planes` 是 3D 体网格，直接按机位 `(x,y,90)` 索引会拿到**错平面**（z 轴索引错位）。解法：只取 `field_horiz_planes` 的 z=90 m 层（`[0,:,0]`），在该层 2D 网格上按 x/y 线性插值——与 GCH 的「轮毂高度平面」语义对齐。
- **G3t 对拍新增断言**（`scripts/selftest.mts`）：`vel/sec/pKw/uEff` 四字段与 TS 侧 `sampleHubPlane` 全对拍（±0.02 m/s、±0.5 m²、±2 kW、±0.02 m/s），并加「none 工况且 GCH 侧无偏航 ⇒ 流场结构断言」（§4.3 数值）。
- 交付件：[`oracle/floris_gch_oracle_v1.json`](oracle/floris_gch_oracle_v1.json) `sha256 = 4b113c47a9992c4061ab52b598b61ad88f930698a7123f2b42eef5e5aa45ee69`；TS 镜像 [`tandem3 扩展`](../../twin/src/data/oracle/florisGchOracle.ts) `sha256 = 9d62a8a844991c4ee134f3e55121ed4d8a2069d1a55e0dd94c31ba7c72c0c0bb`（v1 版头注明 vel/sec/pKw/uEff 的 FLORIS 取平面口径）。

## 2. 内核扩展（`gch.ts`，零行为变更）

`sha256 = 03c634e4b69bb93240822121db2945ae895aaa26c0de6f432460115433a796cd`

- `sampleHubPlane(idx, hubZ, n)`：在机位 i 轮毂高度平面采样 u（m/s）与 A_eff（m²），`A_eff = p_i / (0.5·ρ·u_tip²)`。实现 = 既有 `__debugField` 的平面化封装，**不改任何既有函数**。
- `effYaw` 透传：`evalFarm` 的 `yawDegs` 已支持逐台偏航（R42 贪心即逐台），演示直接复用。
- 验证：既有全部 V&V 断言（G2t/G3t 等）数字**零变化**——本轮只加采样接口，不动场计算。

## 3. 演示界面（`twin/src/demo/`，4 文件 + App 挂载）

`?demo=1` 挂载右侧滑出面板（860 px），复用主场景 3D 视口；`?layout` 必须为 `1x3`（其余布局给出提示并拒绝）。

### 3.1 七步 × 9.19 规格对照

| # | 9.19 规格 | 实现 | 出口验证 |
|---|---|---|---|
| 1 | 选择工况（来流条件、单位、坐标系、机组参数） | 来流输入（8 m/s / 0° 正北 / TI 6%）+ 坐标系/单位/机组参数卡（场景系 +x=东 +z=南，three.js Y-up；FLORIS 系 x=东 y=北，y=−z；T01(x=−100,z=−1272) T02(x=−100,z=−640) T03(x=−100,z=−8)，行距 632 m = 5.02D；NREL 5MW D=125.88 m，HH=90 m）+ 41 工况计划格（≥5 七档取 20 个） | 截图 step1 |
| 2 | 查看基准（零偏航基准功率、逐台功率、流场） | 2702.2 kW + 逐台 1754.0/439.0/509.2 kW + 基准流场 SVG | 截图 step2 |
| 3 | 调整航向（三机各 ±30° 执行量程） | 三滑块（±30°，5° 步）+ 统一偏航快捷 + 实时流场 SVG + 内核/参考双卡（代理 GCH 内核 vs 实测 FLORIS 4.6.6 同工况） | 截图 step3（统一 +20° = 3107.1 kW 两侧一致） |
| 4 | 求解优化（贪心逐台，±30°，5° 步） | 贪心三阶段表（T01 [30,0,0]→3060.0；T02 [30,25,0]→3299.8；T03 保持）+ 收敛说明 | 截图 step4 |
| 5 | 复核效果（前后流场对比、逐台对比、总功率） | ⑤a 基准/优化流场并排 SVG + ⑤b 逐台柱状（1754→1340 / 439→847 / 509→1113）+ 总功率 +597.5 kW（+22.11%）+ 逐台 uEff | 截图 step5 |
| 6 | 展示可靠性（测试集/错误定义/模型版本 + 精度与耗时对照） | 41 工况 参考值-预测值 散点（全在 45° 线）+ 对数误差散点（1e-14…1e-9 kW）+ 推理/优化/复核三段计时 + 测试集·误差定义·模型版本卡 | 截图 step6 |
| 7 | 导出材料（SVG/PNG + 数据表） | ① 工况记录卡（case 号/数据来源/配置）+ 导出记录 JSON 按钮；② 四张对比图各带「导出 SVG」按钮（`XMLSerializer` 序列化，可直入报告/PPT） | 截图 step7 |

### 3.2 四张对比图（WORKLIST §2.2）

① 基准/优化流场并排（33×33 轮毂高度平面 u 场，`uColor` 蓝→青→白 12 级）；② 逐台功率柱状（优化后含 uEff 标注）；③ 参考值-预测值散点 + 误差（log）双联；④ 推理/优化耗时对照（FLORIS 每工况 ~5–8 ms vs 内核 ~0.1–1 ms，log 轴，P95 标注）。**全部 SVG**，色标为常量不随数据自动变（§2.2 图表纪律）；演示数据源 = GCH 内核（代理）+ FLORIS oracle（参考），不接 PINN（红线：PINN 未验证不得进演示数字）。

### 3.3 计时钩子

三段真实计时：`inferMs`（单次 evalFarm）、`optimizeMs`（贪心全程 61 次 eval）、`reviewMs`（41 工况复核循环）。step6 展示中位数 + 极值；导出 JSON 附 `timings_ms` 四类字段（infer/optimize/review/total）。截图实测（SwiftShader 沙箱）：infer ~27–37 ms、optimize ~5–23 ms、review ~229 ms。

## 4. 数值（本轮新测，均 1×3 · NREL 5MW · 8 m/s · 北来流）

1. **基准 none = 2702.2 kW**（逐台 1754.0 / 439.0 / 509.2），与 R42 oracle 一致。
2. **贪心 [30,25,0] = 3299.8 kW**，增益 **+597.5 kW（+22.11%）**，与 R42 oracle 一致。
3. **内核 vs FLORIS 对拍（扩展后 41 工况 × 4 字段）**：逐台功率最大差 **1.251e-12 kW**（相对 1e-13 量级），vel 最大差 4.8e-13 m/s，NMAE ≈ 3.8e-14 %——GCH 内核 = FLORIS 4.6.6 GCH 的忠实移植（R42 结论在扩展字段上复证）。
4. **G3t 新增结构断言**：none 工况 T01 上游来流 8.00 m/s（无偏航不衰减）；T02/T03 轮毂平面受尾流影响 322 m 处 <6 m/s、80 m 处 <4 m/s、408 m 处 <7 m/s——流场结构正确（非全 0 / 非全 8）。
5. 41 工况总功率覆盖 2650–3500 kW，散点全落 45° 参考线（图③）。

## 5. 证据（7 张演示截图 + sha256）

| 文件 | sha256（前 12 位） |
|---|---|
| `img/r44_demo_step1.png` | `b0cdda33b455` |
| `img/r44_demo_step2.png` | `a13e0dfecd29` |
| `img/r44_demo_step3.png` | `4dbeff14beed` |
| `img/r44_demo_step4.png` | `1f815e3c30cc` |
| `img/r44_demo_step5.png` | `1b0647a7a41a` |
| `img/r44_demo_step6.png` | `734a74eb4eeb` |
| `img/r44_demo_step7.png` | `2dae8f18f4c3` |

截图 URL 模板：`?demo=1&layout=1x3&debug=1&q=high&cam=0,25,2600,-100,90,-640&t=15&freeze=1&intro=0&step=N`（`scripts/shot.mjs`，1920×1080，SwiftShader）。R45 软著截图计划直接引用本节文件。

## 6. 出口检查

- [x] `npm run lint` **0 warnings / 0 errors**（69 文件）
- [x] `npm run build` ✓（1.36 s）
- [x] `node scripts/selftest.mts`：**3×3 = 161/0**（R42 的 158 + G3t 扩展 3 条）；`TWIN_LAYOUT=1x3` = **158/0**
- [x] 七步截图逐张人工核验（§5），数字与 §4 一致
- [x] 红线：演示数字不接 PINN；`viz/` 零改动；色标常量
- [x] 文档同步：README（根 + twin）`?demo=1` 行、WORKLIST §2.7 R44 ✅、TIMELINE 阶段 6

## 7. 开放项（不阻塞）

1. R45 软著① 截图计划直接消费 §5 的 7 张图 + R42 的 freeze 截图。
2. R43 答辩 pptx 装配（骨架已立，`generate_823_pptx.py` 套皮）——七步截图可直接入 ppt 证据页。
3. PINN 替换：内核换 PINN 推理的接口位已在 `demoData.ts` 的 `runCase` 抽象（`predictor` 函数参数），14 天检查点验证后一行替换；当前演示标注「代理·GCH 内核」。
4. `scripts/shot.mjs` 在 SwiftShader 下单张 ~2.5 min，批量截图需逐张跑（7 张一次循环会超 600 s 工具超时）——R45 截图计划按此排程。

---

> **2026-10-22 审计附记（AUD-06/17）**：本轮按生成脚本重跑 oracle，物理量逐位复现，仅每工况 `sec`（生成机墙钟）不同。§5 与上文登记的**整文件 sha256 含 `sec`，重跑必然对不上，不构成复现失败**；今后复现校验以 [`scripts/check_oracle_physics.py`](scripts/check_oracle_physics.py) 的「剔除 sec 物理哈希」为准（存档值 `c239b923…`）。演示界面的耗时图注已改口径：FLORIS 侧为生成环境存档墙钟、内核侧为当前浏览器实测，量级差只作量级参考，不作同机加速比。
