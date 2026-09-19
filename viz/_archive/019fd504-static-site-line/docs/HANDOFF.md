# HANDOFF · 风电场偏航优化可视化（孙承泽 · 可视化模块）

> 本文档供**下一个接手 agent** 阅读，目标是无需追问即可继续推进。
> 最后更新：2026-08-08，分支 `arena/019fd504-wind-farm-viz`，远端 HEAD = `9df0e7c`。

---

## 0. 一句话定位

这是**孙承泽（本科生）的可视化模块**，不是组长，不负责向全组交付。当前交付物是一个**纯静态、零依赖、可部署 Cloudflare Pages 的网页**（`site/`），把原来卡顿的 Streamlit 演示重写了。数据目前是 FLORIS 工程尾流模型占位，等袁夫达/厉今飞/洪祖名/田铭雨给真实模型后按**契约**替换，界面零改动。

---

## 1. 分支与环境

- **工作分支**：`arena/019fd504-wind-farm-viz`（你应该在它上面工作）。远程同名，已推送至 `9df0e7c`。
- **不要碰** `arena/019fcc85-wind-farm-viz`（老分支，仅作来源归档）。
- 仓库根还有旧的 `app.py` / `pages/dashboard.py`（Streamlit 版本）——**用户明确说"别急着删"**，暂留。
- Python 环境：沙箱默认**无 numpy/matplotlib**，需用 `pip install --break-system-packages numpy matplotlib` 安装（系统包受 PEP 668 保护）。

---

## 2. 站点结构（`site/`）

```
site/
├── index.html              # 着陆页：4 个 KPI + 14 张功能卡片 + 技术栈
├── wake.html               # 尾流分析（速度场切片 + 功率曲线）
├── optimization.html       # 优化结果（前后对比 + 扫描动画）
├── overview.html           # 数据总览（柱状 + P1/P2 分解 + 原始表格）
├── 3d_surface.html         # 3D 尾流曲面（numpy 渲染 PNG）
├── 3d_volume.html          # 3D 体渲染（多高度层切片）
├── heatmap.html            # 偏航角×风速 增益热力矩阵
├── solver.html             # 优化求解器（网格搜索最优偏航）
├── pod.html                # POD 降阶分析（能量/模态/重构）
├── array.html              # 3×3 阵列优化（柱图 + 布局 + 功率热力图）
├── power_tracking.html     # 功率需求跟踪（目标→最优偏航）
├── dashboard.html          # Master Dashboard（5 KPI + 曲线 + JSON + 状态）
├── windrose.html           # 风玫瑰（额外页）
├── model.html              # 模型精度（额外页）
├── interface.html          # 统一数据接口（额外页）
├── css/style.css           # 全部样式（含 landing/page 样式）
├── assets/
│   ├── data.js             # 所有图表数据（window.WIND_DATA）
│   ├── js/
│   │   ├── interp.js       # 浏览器内插值：predict_power / find_yaw_for_target
│   │   ├── charts.js       # 零依赖 SVG 图表（line/bar/rose/gauge/layout/heatmap/powerGrid）
│   │   └── app.js          # 旧 Streamlit 版遗留，未使用，可删
│   └── img/                # 原始图 + render_assets.py 生成的 PNG
│       ├── fields/  opt/  d3/  array/  pod/   # 由 npz 渲染
│       └── *.png/*.gif                    # 仓库根拷来的原图
├── build_data.py           # CSV/JSON → data.js（纯 Python，无需 numpy）
├── render_assets.py        # npz 流场 → PNG（需 numpy/matplotlib）
├── README.md               # Cloudflare Pages 部署步骤
└── wrangler.toml           # Cloudflare Pages 配置
```

共 **14 个页面**（着陆页 + 13 子页），导航在各页 `<nav>` 内硬编码，已统一含全部 14 个链接。

---

## 3. 数据流向

1. **表格数据**：根目录 `cases_multi.csv` / `cases.csv` / `cases_array.csv` / `cases_windrose_opt.csv` / `optimizer_result.json` / `array_independent_result.json`
   → `python3 site/build_data.py` → 导出 `site/assets/data.js`（`window.WIND_DATA`）。
2. **流场图**：`fields/*.npz`、`fields_3d/*.npz`、`fields_array/*.npz`、`pod_results/pod_data.npz`
   → `python3 site/render_assets.py` → 渲染到 `site/assets/img/{fields,opt,d3,array,pod}/`。
3. 前端 `interp.js` 用 `data.js` 做双线性插值（`predict_power(yaw, U)→(P1,P2)`、`find_yaw_for_target(target,U)→(yaw,power,err%)`），**无任何后端**。

> ⚠️ 沙箱重启后 numpy 会被清掉，`site/assets/img/{fields,opt,d3,array,pod}/` 的 PNG 也会丢；重新跑 `pip install --break-system-packages numpy matplotlib` 再 `python3 site/render_assets.py` 即可恢复。

---

## 4. 统一数据接口契约（各组替换时只改函数体/文件，界面 0 改动）

- `predict_power(yaw_angle, U_inf) -> (P1, P2) kW`（`site/assets/js/interp.js`）
- `find_yaw_for_target(target_power, U_inf) -> (best_yaw, actual_power, error_pct)`
- `optimizer_result.json` 字段已对齐假期前 PPT：`wind_speed, original_yaw, recommended_yaw, power_before, power_after, wake_field`（前 5 项已落地，`wake_field` 待田铭雨 CFD 提供后仅换图）
- `cases.csv` 最小字段（PPT）：`case_id, U_inf, yaw_1, yaw_2, pitch, rpm, power_1, power_2`（第一版 pitch/rpm 固定，暂未含）

---

## 5. 本地预览 / 部署

- **预览**：`python3 -m http.server 8000 --bind 0.0.0.0 --directory site`，浏览器开 `http://localhost:8000`。
  - 当前沙箱实时预览：`https://8000-incy4nxt6uh37zu3h5o12.e2b.app`
- **部署 Cloudflare Pages**：
  - Dashboard 方式：连 GitHub 仓库 `sunccchengze/wind_farm_viz`，构建命令留空，输出目录 `site`，分支 `arena/019fd504-wind-farm-viz`。
  - CLI：`npx wrangler pages deploy site --project-name wind-farm-viz`。
  - 详见 `site/README.md`。

---

## 6. 已完成 vs 待办（next agent 起点）

**已完成**
- 14 页纯静态站点，还原了原 Streamlit 版的几乎全部可视化（尾流/优化/总览/3D曲面/3D体/热力矩阵/求解器/POD/阵列/功率跟踪/Dashboard），并加了风玫瑰/模型精度/接口 3 个额外页。
- 用 numpy 真实渲染 npz 流场（不再是占位图）。
- 统一接口契约固化，对齐假期前 PPT。
- 文档 `docs/` 已重构为孙承泽个人视角（`孙承泽个人待办.md` 是核心可执行清单）。

**建议下一步（按"先能跑→再准确→再高级"）**
1. **部署 Cloudflare Pages**（用户想要正式 `*.pages.dev` 网址；wrangler.toml 已就绪）。
2. **升级动画**：`wake_animation.gif` / `array_animation.gif` 是 GIF，换成 MP4/Canvas 更丝滑（用户明确不喜欢卡顿）。
3. **交互联动**：拖拽偏航角 → 全场功率与流场图实时联动（"再高级"阶段）。
4. **实时仪表盘**：借鉴 `20260808/本科生答辩材料可供参考.md` §3.9（半圆三色仪表、滚动曲线、阈值告警）。
5. **替换真实数据**（等各组给）：
   - 洪祖名 XGBoost 模型（`20260808/代理模型优化交付_20260808.zip → final_models/*.json`）接入 `predict_power`；
   - 洪真实优化器 JSON 覆盖 `optimizer_result.json` / `array_independent_result.json`；
   - 田铭雨 CFD 流场 npz 接 `wake_field`。
6. **POD 页**目前是静态图，若需要可做成交互模态查看。
7. 旧 Streamlit 文件（`app.py`/`pages/`）在用户许可后再删。

---

## 7. 已知坑（务必注意）

- **沙箱不稳定**：本地分支曾被多次重置回基线 `efdb50d`，但远端始终是最新。遇到本地 HEAD 不对，先 `git fetch` 再 `git reset --hard origin/arena/019fd504-wind-farm-viz`。
- **提交要频繁**：沙箱崩溃会丢未提交文件（曾丢过整批页面，已重建）。
- **numpy 非持久**：重装 + 重渲。
- **AGENT 宪法级文件**（`20260808/最高优先级AGENT必须遵守的宪法级文件.md`）：先想后写、最简、外科手术式改动、目标驱动、不确定就问。

---

## 8. 关键文档导航（在 `docs/`）

- `孙承泽个人待办.md` —— **最该先看**，仅针对孙的可执行清单（对齐 PPT）。
- `README.md` —— 文档中心索引（已声明本分支是孙的可视化工作台）。
- `research_overview.md` / `question.md` / `communication_log.md` / `delivery_plan.md` / `team_inventory.md` —— 项目背景/集成参考（非孙需交付）。
- `chat_20260808_digest.md` —— 20260808 文件夹（袁/厉/洪材料 + PPT + 答辩材料）的完整消化。
- `20260808/` —— 组共享原始材料（`README.md`、`floris(1).zip`、`代理模型优化交付_20260808.zip`、`本科生答辩材料可供参考.md`、`假期前PPT.md`、`最高优先级AGENT必须遵守的宪法级文件.md`）。
