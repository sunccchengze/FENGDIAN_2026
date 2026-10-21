# Round 41 · 单列三风机改造（工作流 A 第一轮）· 过程记录

> **状态**：2026-10-05 开工。方案依据 [`../13_0919组会决议_三风机改造方案与3x3留档.md`](../13_0919组会决议_三风机改造方案与3x3留档.md) §四–§五（2026-09-19 出，**拖了 16 天才动工**，见 [`../project/WORKLIST.md`](../project/WORKLIST.md) §2.1）。
> **本轮范围（R41-A）**：布局真值源 `layouts.ts` + 全部「字面量 9 / 3×3」派生化 + selftest 守卫。**不改视觉、不改物理公式**。
> **下一轮（R42 = A-2）**：1×3 机位/开场/锚点/电缆/HUD 竖排 + 三机串列 oracle + V&V 断言 + 三档基线重测。
> **纪律**（docs/13 §4.4 原文，不许讨价还价）：
> 1. 1×3 的全场增益数字必须来自**新 oracle**；在此之前界面只许挂【代理】；
> 2. `+24.04% / 8095.15 kW / 97.97%` 是 3×3 / 双机口径，不许混写给 1×3；
> 3. 渲染计数三档基线**重新实测**，不许沿用 267 draw calls / 642,556 tris。

---

## 1. 基线（2026-10-05，本沙箱实测）

| 项 | 值 | 备注 |
|---|---|---|
| 环境恢复 | `bash twin/scripts/bootstrap.sh`，11 s | npm 141 包 + NSS 桩库 + `/tmp/chromium` |
| `npm run selftest` | **145 通过 / 0 失败** | 首次跑是 **144/1**，见 §1.1 |
| `npm run lint` | 0 warnings / 0 errors | oxlint，64 文件 116 规则 |
| `npm run build` | ✓ 1.52 s | vite/rolldown，chunk 体积警告为既有项 |
| 仓库门禁 `ci/repo_quality.py` | 0 error / 1 warning | 1833 跟踪文件、127 md 链接、20 镜像 |

### 1.1 前置基线修复（动工前必须先做的事，已做）

首跑 selftest 得 **144/1**，失败项是 R38 证据链守卫：`docs/project/TIMELINE.md` 三行按名引用了
聊天截图，而守卫的证据树只有 `docs/` + `image-search/`——**守卫写于 2026-09-21 归档之前**，
不认识 `materials/集体/聊天记录/` 这棵新证据树。这不是 twin 的回归，是仓库治理领先于 twin 守卫。

修复（只增严不放宽）：

1. `scripts/selftest.mts`：证据树扩为 `docs + image-search + materials`；0 字节检查一并覆盖
   `materials/`（纳管当天实测 56 张图、零空文件）。守卫内留有注释说明来由；
2. `TIMELINE.md` 三处裸文件名改为**可点相对链接**；其中 8/7 那处原本写成省略号截断的假名字
   （`20260807-0815_群聊_…` 加 png 后缀，永远解析不到；本文不 reproduce 该字符串，
   因为 R38 守卫会按文件名抓它），补全为真文件名
   `20260807-0815_群聊_厉今飞网络选型说明·洪祖名发代理模型交付·袁夫达发建模与数据生成.png`。

修复后 145/0。**教训记入 WORKLIST §5**：跨分区引用（docs → materials）第一次出现时，
所有按名解析的守卫都要重新审一遍；门禁（ci/repo_quality.py）解析相对链接所以没报，
twin 守卫按 basename 解析所以报了——两套解析器，两套盲區。

---

## 2. R41-A 改动清单（待填：动工后逐文件记 before/after）

| 文件 | 现状 | 改法 | 状态 |
|---|---|---|---|
| `src/scene/layouts.ts` | 不存在 | 新建：`LAYOUTS = { '3x3': …, '1x3': … }`，`FARM/SERVOS/ROW_COUNT/ANCHOR` 全部由它派生 | ☑ |
| `src/scene/terrainUtil.ts` | `FARM` 内联双循环 9 台；`ANCHOR` 写死 `FARM[4]/[6]/[7]/[8]` | 改派生 + 语义选择器 `upstream()/middle()/downstream()` | ☑ |
| `src/data/farmSim.ts` | `FARM_RATED_MW = 45` 写死；贪心 `for r<3` | `N_UNITS * 5`；上界改 `ROW_COUNT` | ☑ |
| `src/state/simStore.ts` | `ZERO_YAW` 长度、`SERVO_UNIT`、HUD 上限 45 | 全部派生 | ☑ |
| `src/data/telemetry.ts` | `p.unitYaw.length === 9` 硬校验 | `=== N_UNITS` | ☑ |
| `scripts/selftest.mts` | 无布局守卫 | 新增**五条**守卫（三条来自 docs/13 §4.5 + 两条回归锁，见下） | ☑ |
| `src/hud/Hud.tsx` | 滑杆 `Array.from({length: 9})`；矩阵 aria/标题写死 3×3 | 滑杆数 = `N_UNITS`；矩阵口径 = `LAYOUT.label`（列样式变体留 R42） | ☑ |

**新增守卫（docs/13 §4.5 原文落地 + 两条回归锁，selftest 145 → 150）**：
① `src/` 内不得出现字面量 `length: 9` / `Array(9)` / `=== 9`；
② `LAYOUTS` 两套都能生成合法 `FARM`（间距 632、id 连续、贴地 ≤12 m）；
③ 1×3 下 `FARM` 是 3×3 中列的严格子集（几何回归）；
④ 回归锁：3×3 派生几何与留档 tag 的写死九机坐标逐位一致；
⑤ 同源锁：`FARM/SERVOS/ROW_COUNT/FARM_RATED_MW` 与 `ACTIVE_LAYOUT` 一致。

## 3. 出口证据（2026-10-05 实测）

- **数值等价（本次采用的判据）**：重构前（`git worktree` 取 `174f8b6`，其 `twin/src` 与留档 tag
  同源——`gh api …/commits?path=twin/src` 证实 `twin/src` 最后改动是 09-17 的 R40b，早于 tag）
  与重构后，对同一组纯函数输入输出 **1720 字节 JSON 逐位一致**：FARM 九机坐标/排/列/转速、
  SERVOS、ROW_COUNT、ANCHOR 五锚点、t=15 与 t=9.5（u=9 北来风）零偏航与九元偏航向量下的
  逐机功率与全场总功率、`optimizeYaw` 的逐排偏移与增益。存证：
  [`r41_equiv_3x3.json`](r41_equiv_3x3.json)。
- `npm run verify` 全绿，断言数**只增不减**：145 → **150**（+5 条 R41 布局守卫）；lint 0/0；build ✓。
- 本文件 §2 全部 ☐ 变 ☑（见 §2 表）。
- 外观存证（**非判据**，见 §3.1）：[`img/r41_3x3_look_20261005.png`](img/r41_3x3_look_20261005.png)。

### 3.1 判据事故：像素 abdiff 在本环境不是有效等价判据（docs/13 的出口被修正）

docs/13 §五 与 HANDOFF_NEXT 把 R41-A 的出口写成「`?layout=3x3` 与留档 tag 同机位 abdiff = 0」。
实测**做不到，且不该做**：

| 比对 | 差>0 像素 | 显著差(>60) |
|---|---|---|
| 同构建自差（now vs now2，同 URL 同脚本同等待） | 742,873（35.83%） | 32,437 |
| 跨构建（now vs prev） | 585,429（28.23%） | 11,450 |

**自差大于跨差** ⇒ 场景里的波/粒子/云按挂钟时间动画，`t=15` 只冻结了模拟小时、没冻结渲染相位；
任何两张截图都不可比。于是像素差既证不了「没变」也证不了「变了」。

处置：① 本轮改用**确定性数值等价**（§3 第一条）作判据——纯函数同输入同输出，比像素更强；
② docs/13 的 abdiff 出口**修正为**「数值等价 + 冻结渲染相位后的像素差」；后者需要给场景加
`?freeze=1`（把波/粒子/云的相位源从挂钟换成模拟时间），**列为 R42 开放项**；
③ 教训：写出口之前先验证判据本身有没有噪声底（自差），否则「abdiff=0」只是运气。

## 4. 三档基线重测（R42 已填，2026-10-05 实测）

口径：1280×720、SwiftShader、`perftier`（`window.__aeolus_stats()` 单帧手动计数=确定值；
帧时长绝对 ms 无参考意义）。旧 3×3 基线 267 / 642,556 **作废，不许沿用**。

| 布局 | 档 | calls | tris |
|---|---|---|---|
| 3×3 | high | 267 | 586,756 |
| 3×3 | medium | 264 | 567,064 |
| 3×3 | low | 231 | 440,060 |
| **1×3** | high | 267 | **549,556**（−6.3%） |
| **1×3** | medium | 264 | 529,864 |
| **1×3** | low | 231 | 440,060（同 3×3，低档细节层裁剪吸收差异） |

完整表（含 lines/geom/tex/帧时长）见 [`round42`](round42_单列三机改造_视觉与真值.md) §6.3。
