# 风电场偏航优化可视化系统

> **📦 迁入说明（2026-09-19）**：本目录是原独立仓库 `sunccchengze/wind_farm_viz` 的**整树迁入**（含全部 182 个提交历史），
> 现属 `Dachuang-SZLS` 仓库的 `viz/` 子目录，与数字孪生 `twin/` 平级；原仓库由用户删除。
> - 下文所有命令的当前目录都是**本目录**（先 `cd viz`）；
> - 下文提到的分支名（如 `arena/01a012f1-wind-farm-viz`）与 8 位 SHA 属原仓库，对照表见 `../docs/12_附件_wind_farm_viz_commit_map.tsv`；
> - 原仓 `技能库&准则/`（-SKILL- 仓库整份拷贝，410 MB）**未迁入**，其中 7 份项目相关 md 保留在 `skills-notes/`；精选技能在 `../skills/`；
> - Cloudflare Pages 项目需重新连接到本仓（Root directory `viz`，输出 `site`），见 `../docs/12` §4.2；
> - 封板状态（v1.3-final）、FREEZE 边界与数据口径**原样有效**，本段之外未改动任何原文。

西安交通大学 · 能源与动力工程学院 · 大学生创新训练项目
可视化与交互系统模块负责人：孙承泽 ｜ 指导教师：李良星 副教授
团队成员：田铭雨（CFD 仿真）· 袁夫达（降阶与代理模型）· 厉今飞（基线数据）· 洪祖名（优化与 PPO）

> **最终封板**：网页于 2026-08-19 完成 `v1.3-final` 验收。现役 15 页不再继续视觉改版；最终维护边界见 `HANDOFF_NEXT_AGENT.md` 与 `FREEZE.md`。

---

## 两个形态

| 形态 | 状态 | 入口 |
|---|---|---|
| 纯静态演示系统（`site/`，15 页） | **最终封板产品**，Cloudflare Pages 部署 | https://wind-farm-viz.pages.dev/ |
| Streamlit 应用（`app.py` + `pages/`，10 页） | 留档本地工具，离线探索与答辩断网备胎 | 本地 `streamlit run app.py` |

静态站零后端：数据经构建脚本注入 `assets/data*.js`，浏览器内双线性插值（`assets/js/interp.js`），Plotly.js / three.js 出图。

## 静态站页面（15 页）

| 页面 | 文件 | 一句话 |
|---|---|---|
| 主页 | `index.html` | 鼠标耦合 3×3 数字风洞、项目入口与审计 KPI |
| 尾流分析 | `wake.html` | 偏航角滑块联动尾流云图与功率 |
| 优化结果 | `optimization.html` | 0° vs +25° 对比，含速度场与功率分解 |
| 优化求解器 | `solver.html` | 任意风速实时搜索最优偏航角，算法开销对比表（实测） |
| Dashboard | `dashboard.html` | 数据-物理-控制一屏总控 |
| 3D 风电场 | `3d_farm.html` | 九机 three.js 场景，转子旋转与尾流偏转 |
| 3D 尾流曲面 | `3d_surface.html` | 三维速度曲面 |
| 3D 体渲染 | `3d_volume.html` | 尾流低速泡等值面 |
| 热力矩阵 | `heatmap.html` | 偏航角 × 风速增益矩阵 |
| 数据总览 | `overview.html` | 全工况表与分解曲线 |
| POD 降阶 | `pod.html` | 模态能量 76.4% / 21.6%，前 2 阶累计 98.0%（97.97%） |
| 3×3 阵列优化 | `array.html` | 统一 +14.87% / 逐排贪心 +24.04% |
| 功率需求跟踪 | `power_tracking.html` | 目标功率反求偏航角 |
| 模型精度 | `model.html` | XGBoost 图源级佐证（仓内复现资产待补） |
| 统一数据接口 | `interface.html` | 三组数据契约与接入状态 |

> 风向扫描 CSV、生成脚本与 Nature 风玫瑰图继续作为科研留档保留，但不再进入现役网页导航。

## 快速开始

```bash
# 静态站本地预览（零依赖）
python3 -m http.server 8000 --bind 0.0.0.0 --directory site

# 最终部署门禁（任一失败均禁止部署）
python3 site/check_contract.py
python3 site/verify_all_pages.py

# Streamlit 留档工具
pip install -r requirements.txt
streamlit run app.py
```

## 数据管道

```bash
python generate_data.py             # 两台串列 8 m/s × 13 偏航 → cases.csv + fields/
python generate_multiwind_data.py   # 4 风速 × 13 偏航 → cases_multi.csv
python generate_3d_data.py          # 5 偏航 × 9 高度层 → fields_3d/
python generate_array_data.py       # 3×3 阵列统一偏航 → cases_array.csv
python generate_array_independent.py# 阵列逐排贪心优化 → array_independent_result.json
python generate_windrose_data.py    # 12 风向 × 4 风速 × 13 偏航 → cases_windrose*.csv
python pod_analysis.py              # POD/SVD 分解 → pod_results/
python site/build_data.py           # csv/json → site/assets/data.js(纯标准库)
python site/build_3d_data.py        # npz → site/assets/data_3d.js
python site/check_contract.py       # 契约自检(部署前必跑,退出码非 0 禁部署)
python site/benchmark_solver.py     # solver 页算法对比表复跑口径
```

## 数据契约（三组接口，字段形状不可变更）

### 仿真组：`cases.csv` / `fields/case_XXXX.npz` / `fields_3d/yaw_±XX.npz`

| 变量 | 形状 | 单位 | 说明 |
|---|---|---|---|
| x / y | (128,) / (64,) | m | 顺风 / 横向坐标 |
| u | (64, 128) | m/s | 轮毂高度水平截面风速（绝对风速，不归一化） |
| 3D 版 | x(64,) y(32,) z(9,)，u(9,32,64) | m/s | 20~180 m 九层 |

### 控制组：`optimizer_result.json` 与功率跟踪函数

`find_yaw_for_target(target_power, U_inf) -> (best_yaw, actual_power, error_pct)`，放入 `surrogate_model.py` 覆盖同名函数即可被留档页自动调用；静态站等价契约见下。

### AI 组：`predict_power`

- Python（留档）：`predict_power(yaw_angle, U_inf) -> (p1, p2)` kW
- JS（静态站 `assets/js/interp.js`）：`predict_power(yaw, U) -> {p1, p2, ptot, outOfRange, reasons}`，可信域 6~12 m/s、±30°，越界自动提示

## 当前数据口径（2026-08-19 最终封板复核）

| 项 | 口径 |
|---|---|
| 仿真来源 | FLORIS 4.6.6 默认配置：GCH（gauss 速度/偏转 + 二次转向 + 偏航附加恢复 + 横向速度） |
| 风机 | NREL 5MW（额定 5 MW @ 11.4 m/s，轮毂 90 m，转子标称 126 m） |
| 两台串列 | 间距 5D，8 m/s，TI 6%：最优 +25°，全场 +8.13%（本地复现偏差 < 0.01 kW） |
| 3×3 阵列 | 第一排偏航 +14.87%、前两排接力 +22.73% (9935 kW)、逐排贪心 [30/20/0]° +24.04%（Row 均速 7.97 / 5.10 / 5.31 m/s） |
| POD | 前 2 阶累计 97.97%（模态 0 偶极子 76.4%，模态 1 恢复 21.6%） |
| 风玫瑰（两台串列） | 仅 270° 正对扇区有收益；等权 ΔAEP +0.51%，西风 30% 示例 +1.97% |
| 风玫瑰（3×3 阵列） | 12 风向双通道贪心（7536 次求解）：8 扇区非零——轴向 90°/270° +24.0% 级、列轴 0°/180° +21.6%、晶格对角 60°/120°/240°/300° +10.7~11.3%；等权 ΔAEP +8.86%，西风 30% 示例 +11.37%（8 m/s 口径） |
| PPO 闭环 | 200 独立测试回合实测稳态 MAE = 0.523% (< 1.2%)、平均调节时间 = 0.944 s (~0.8 s)、稳态零抖动（4 维契约权重 55 KB） |
| 模型精度证据边界 | XGBoost 交付图源已纳入网页；原始训练压缩包未纳入仓库，因此不承诺仓内完整重训 |

数据来源、可信域和假设直接写入对应页面的图注与边界说明；全部数字的复算口径见 `.learnings/AUDIT_20260810.md`（审计台账）。

## 依赖

`requirements.txt` 已锁定验证区间：Python 3.11（审计复核环境）与 3.13（开发机），FLORIS 钉死 4.6.6（API 敏感），其余给出已验证上下限。静态站 `site/` 不依赖任何 Python 包。

## 仓库治理

- 当前固定工作分支：`arena/01a012f1-wind-farm-viz`；历史会话分支只作追溯；**永不 merge 到 `main`**。Cloudflare Pages 的生产分支需在控制台单独核对，不以旧文档中的分支名为准。
- 网页已最终冻结；当前交接以 `HANDOFF_NEXT_AGENT.md` 和 `FREEZE.md` 为准，`HANDOFF.md` 与 `.learnings/SESSION_ARCHIVE_20260810.md` 仅作历史索引。
- 后续只允许修复明确运行错误、死链、数据错误、安全问题或文字溢出；任何数字改动必须附复算路径并重跑两道门禁。
