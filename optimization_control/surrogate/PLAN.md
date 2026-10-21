# 代理模型机器学习优化 — 生产方案

> 制定日期：2026-08-07 | 负责人：优化控制模块（Codex）
> 背景：袁夫达提出「在 CFD 高保真数据产出前，通过优化函数提高数据精度作为训练素材」。
> 当前数据：FLORIS v4.6.6 生成，GCH/CC 两套各 1224 组（风速 4~12 m/s × 风向 0~345° × 湍流强度 3 档），
> 输出 3 台 NREL 5MW 风机功率 + 全场功率。厉今飞已训练 MLP 基线（R²≈0.999）。

## 问题本质

1224 组 × 2 套，3 维输入 → 4 维输出，**低维、网格化、确定性回归**（FLORIS 稳态模型，无噪声）。
这是插值/函数逼近问题，不是统计学习问题 → GPR、树模型、物理约束 MLP 是正确方向；
大数据深度学习、时序模型、生成模型均不适用。

## 路线

| 路线 | 方法 | 定位 |
|------|------|------|
| 树模型基线 | XGBoost / LightGBM | 表格数据强基线，成本最低 |
| 高斯过程回归 | GPR（RBF + 白噪声核） | 数据高效、带不确定性输出、可做数据质量诊断 |
| 改进 MLP | 物理约束 / 多任务 / 残差 | 保留深度路线，物理先验内建 |

配套：Optuna 贝叶斯超参搜索 + 分层 5-fold CV + 统一评估协议。

## 生产阶段

### 阶段 0：评估协议与基线复现
- 复现厉今飞 `.keras` 模型指标（加载、推理一致）
- 评估协议：分层 5-fold CV（按风速层分组）+ 独立测试集 15%
- 指标：R²、MAE(kW)、RMSE、分段相对误差（风速区间 [4-6,6-9,9-12] / 功率区间）、守恒校验（farm≈Σturbine）
- 产出：`eval_protocol.md` + `baseline_metrics.csv`

### 阶段 1：候选模型实现
- 统一接口 `fit/predict/save`，输入统一 6 特征编码
- 候选：`xgb_model.py`、`gpr_model.py`、`mlp_v2.py`（U³ 与高阶谐波特征 + 多任务损失）、`two_stage.py`（零功率分类+回归）
- 产出：模型模块 + 每模型验证脚本（10 分钟跑通）

### 阶段 2：超参优化
- Optuna TPE，seed=42，目标 = farm RMSE（5-fold 均值）
- 搜索空间：树模型（n_estimators/depth/lr/L2）、GPR（核参数）、MLP（宽度/深度/dropout/lr）
- 产出：`optuna_results.csv` + 最优超参 `config.yaml`

### 阶段 3：模型对比与选优
- 全模型统一协议评估 → `model_comparison.csv`（GCH/CC 各一张）
- 残差分析（误差 vs 风速/风向/功率）→ 定位误差热点
- 物理一致性：单调性、守恒、边界（0≤P≤5MW）
- 产出：`model_comparison.md` + 残差图

### 阶段 4：生产化交付
- 最优模型导出 **xgboost 原生 .json**（替代 ONNX：零额外依赖、无损、RL 环境加载快）
- 存放：`optimization_control/surrogate/models/final/`（gch/cc 各 3 台机 + metadata）
- 验证：加载前后预测差 0 W

## 执行状态（2026-08-07）

- ✅ 阶段 0：基线复现（numpy 前向与 Keras 一致，差 2W）
- ✅ 阶段 1：候选模型 CV 对比（XGB/GPR/two-stage 超越基线 ~6 倍；mlp_v2 打不过树模型）
- ✅ 阶段 2：Optuna 调参（XGB farm RMSE 14→8.95 kW；GPR 20.17；mlp_v2 115）
- ✅ 阶段 3：残差分析 + 物理一致性（守恒 1W；cc 边界最高约 +108kW 需 clip；gch 额定区 kW 级非单调）
- ✅ 阶段 4：最终 XGB 导出（原生 json + metadata）

### 最终模型（XGBoost，调参后）

| 数据 | farm R² | farm MAE(kW) | farm RMSE(kW) |
|------|---------|--------------|---------------|
| GCH | 0.999978 | 7.79 | 22.43 |
| CC | 0.999961 | 10.49 | 29.97 |

推理时需 clip 到 [0, 5e6]（物理边界）。

### 阶段 5：与 RL 流程衔接（⛔ 等含控制参数数据）
- 代理模型接入 RL 环境动力学（任务 7）
- 注意：**当前数据无偏航维度**，本次优化提升的是数据/预测精度；
  RL 偏航控制需等含偏航数据（袁夫达任务 6），同一 pipeline 届时重训

## 交付物清单

- `eval_protocol.md` / `baseline_metrics.csv`（阶段 0）
- 4 个候选模型模块（阶段 1）
- `optuna_results.txt`（阶段 2；历史实验未单独生成 `config.yaml`）
- `model_comparison_cv.csv` / 两张残差图 / `summary_stage2_4.txt`（阶段 3）
- `{gch,cc}_turbine_{1,2,3}.json` + `*_metadata.json`（阶段 4）

> 早期方案中的 ONNX、`model_comparison.md` 和 `optuna_results.csv` 未作为最终产物生成；以上清单按 2026-08-23 实际文件修正。

## 验证与 git

- 每阶段改完跑验证（脚本输出指标表）
- 每阶段一个 commit，实验记录进 `optimization_control/experiments/YYYYMMDD_描述/`
- 随机种子统一 seed=42

## 2026-08-23 复核补充

- 当前四个主执行脚本仍硬编码本机绝对路径，阶段 5 前必须参数化。
- `stage3_analysis.py` 的风向反推 `atan2` 参数顺序需复核，现有残差图的风向横坐标不能直接用于论文。
- 当前模型没有偏航/桨距/转速输入；阶段 5 的第一步是数据需求，不是直接包装 Gym 环境。