# 风电场偏航优化可视化项目 · 文档中心

> 分支：`arena/019fd504-wind-farm-viz` ｜ 模块维护人：孙承泽（可视化）｜ 指导老师：李良星
> **定位说明**：本分支是**孙承泽的可视化工作台**。下面的团队级文档（research_overview / question / communication_log / delivery_plan / team_inventory）是**项目背景与集成参考**，并非孙承泽需向全组交付的内容。孙承泽自身的**可执行清单见 [`孙承泽个人待办.md`](孙承泽个人待办.md)**；可视化交付物是 **`site/`**（纯静态，可一键部署 Cloudflare Pages）。

---

## 0. 怎么用这个 docs 文件夹

| 文件 | 作用 |
| --- | --- |
| `README.md`（本文件） | 总览 + 当前进度 + 阶段性交付说明 |
| `team_inventory.md` | 谁做了什么：文件 → 负责人 → 状态 → 下一步 |
| `delivery_plan.md` | 阶段性交付方案：里程碑 M0–M5、交付物、集成点、时间线 |
| `research_overview.md` | 研究目标拆解 + 方法合理性（回应李良星建议 3、4，含 20260808 更新） |
| `question.md` | **李良星老师对孙承泽的 20 问 + 20260808 后新增 4 问**（含已答复状态） |
| `communication_log.md` | 群内关键沟通（厉 / 袁 / 洪 / 李） |
| `chat_20260808_digest.md` | 2026-08-08 群聊与洪祖名交付的完整消化 |

> 群聊原始材料在仓库根目录 `20260808/` 文件夹（来自 `arena/019fcc85` 分支，已拉取到本分支）。

---

## 1. 当前进度（一句话）

**数据底座（袁/厉）→ 代理模型（厉 MLP 基线 → 洪选定 XGBoost，farm MAE 降 ~11 倍）→ 可视化（孙）→ 阵列偏航优化（洪，双机 +8.1%、9 机独立 +24.0%）** 已形成可演示闭环；**最大短板是当前数据无偏航维度**，PINN 与智能调控闭环为下一阶段。

---

## 2. 给组内的"阶段性交付"是什么

详见 `delivery_plan.md`。阶段一交付包（5 份）：
1. 可视化演示系统（孙）；
2. 数据底座说明（袁，含补偏航数据计划）；
3. **代理模型报告（厉基线 + 洪 XGBoost 优化）**；
4. 阵列优化结果（洪）；
5. 仿真流场（田）。

用本 docs 串联即为一份完整阶段一交付包，组会/中期检查可直接汇报。

---

## 3. 如何本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

数据 / 模型入口：
- 双机插值代理：`surrogate_model.py`（读 `cases_multi.csv`）
- **最终代理模型（XGBoost）**：`20260808/代理模型优化交付_20260808.zip` → `final_models/*.json`（见 `chat_20260808_digest.md` 用法示例）
- FLORIS 原始 NN：`floris(1).zip` → `wind_farm_results/*.keras`
- 流场 / 优化：`generate_*.py`、`pod_analysis.py`、`optimizer_result.json`

---

## 4. 已知缺口 / 待办

- ⚠️ **数据无偏航维度**（洪指出）：PPO 偏航控制无法训练，最高优先级待补（Q22）。
- PINN 物理融合未启动（M4）；真·高保真 CFD（Fluent）待田推进。
- 可视化未接洪的 XGBoost（Q1）；优化结果 JSON 未做成可调（Q14）。
- 零功率：剔除 vs 两阶段保留，待定正式方案（Q23）。
