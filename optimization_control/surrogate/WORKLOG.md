# 代理模型机器学习优化 — 工作记录

> 记录范围：2026-08-06 ~ 2026-08-07 全部工作（队友成果接收 → 框架建立 → 生产方案执行）
> 状态：✅ 阶段 0-4 已完成 | ⏳ 阶段 5（RL 衔接）等待含偏航数据

---

## 1. 背景与目标

项目团队分工：袁夫达提供 FLORIS 数据 → 厉今飞训练 NN 代理模型 → 优化控制模块（我）用代理模型构建 RL 环境。
当前阶段目标：**先跑通一个简单但完整的流程**，并按照袁夫达提议「在 CFD 高保真数据产出前，通过优化函数提高数据精度作为训练素材」，
对现有 FLORIS 数据执行机器学习优化，产出高质量功率代理模型。

---

## 2. 队友成果接收（2026-08-06）

来源：`external_teammate_delivery\floris.zip`（含 31 个文件 + 说明.docx）

### 数据（袁夫达）

- FLORIS **v4.6.6**（NatLabRockies/floris），尾流模型 **GCH**（Gauss-Curl-Hybrid）与 **CC**（Cumulative-Curl）各一套
- 布局：NREL 5MW × 3 台，间距 378m（3D），沿 X 轴排列
- 样本：**1224 组/套** = 风速 4~12 m/s（17 档）× 风向 0~345°（24 档）× 湍流强度 [0.06, 0.08, 0.10]
- 字段（CSV 实际英文列名）：`wind_speed, wind_direction, turbulence_intensity, turbine_1/2/3_power(W), farm_power(W)`
- 数据质量：GCH 含 **22 行零功率**、CC 含 **4 行**（低风速+尾流遮挡），训练时已剔除

### 模型（厉今飞）

- Keras3 Functional MLP：`Normalization → Dense(64,Swish) → Dense(128,Swish) → Dense(64,Swish) → Dense(3,Sigmoid) → Dense(3→1,权重[1/3,1/3,1/3])`
- 输入 6 特征：`[U, TI, sinθ, cosθ, sin2θ, cos2θ]`（风向周期编码 + 二阶谐波）
- 输出：3 台机功率分数（×5MW）+ farm（三机求和，功率守恒）
- 训练：70/15/15、seed=42、Adam lr=1e-3、MSE、Swish、L2、EarlyStopping、ReduceLROnPlateau
- 基线指标：gch farm R²=0.99906 MAE=86.5kW | cc R²=0.99871 MAE=103.1kW

### 归档位置

```
data/teammates/yuan_fuda_floris/   # raw/gch + raw/cc（数据+图）、说明.docx、processed/、scripts/
data/teammates/li_jinfei_nn/       # models/gch+cc（.keras+metadata）、scripts/gch+cc、results/gch+cc
```

---

## 3. 框架建立

- `AGENTS.md`（Codex 协作规则）、`README.md`（文件框架总览+队友接收指南）、`.gitignore`
- 更新 `CLAUDE.md` 第五节（目录树含 teammates 交付区）与第六节（数据格式约定：FLORIS 数据 / .keras 模型）
- 队友目录 README 入 git、数据文件不入 git（大文件约定）
- git 初始化（注意：沙箱下操作需 `-c safe.directory=...`）

---

## 4. 生产方案执行（2026-08-07）

方案文档：`optimization_control/surrogate/PLAN.md`（含阶段 0-5 与执行状态）
评估协议：`optimization_control/surrogate/eval_protocol.md`

### 阶段 0：基线复现 ✅

- 实现 `keras_model.py`：**numpy 前向加载 .keras**（不依赖 TensorFlow，仅 numpy+h5py）
- 关键坑：**Keras3 Normalization 在 count=0 时推理 epsilon=0**（非文档默认 1e-3），修正后与 Keras 官方加载预测最大差 **2W**
- 复现验证：与 `test_metrics.csv` MAE 差 <0.1W、R² 差 <3e-8 → 基线可信，队友交付自洽
- 环境：项目 venv（`.venv`，Python 3.12，依赖见 `optimization_control/requirements.txt`）

### 阶段 1：候选模型实现与 CV 对比 ✅

统一接口（6 特征输入 → 4 维功率输出，farm=sum 守恒），分层 5-fold CV（按风速档，seed=42）：

| 模型 | gch farm R² | gch farm MAE(kW) | cc farm R² | cc farm MAE(kW) |
|------|------------|------------------|-----------|-----------------|
| 基线 MLP（厉今飞） | 0.99906 | 86.5 | 0.99871 | 103.1 |
| XGBoost | 0.99994 | 13.8 | 0.99996 | 15.0 |
| GPR | 0.99993 | 14.9 | 0.99934 | 22.3 |
| two-stage（含零行） | 0.99994 | 13.7 | 0.99996 | 12.8 |
| mlp_v2（扩展特征） | 0.99757 | 157 | 0.99765 | 154 |

结论：**树模型/GPR 全面超越基线 MLP（~6 倍）**；mlp_v2 待调参。

### 阶段 2：Optuna 超参优化 ✅

| 模型 | 最优 farm RMSE(kW) | 关键参数 |
|------|-------------------|----------|
| XGBoost | **8.95** | n_estimators=529, depth=5, lr=0.197, subsample=0.738, reg_lambda=5.24 |
| GPR | 20.17 | length_scale=0.37, noise=2.9e-5（超参敏感） |
| mlp_v2 | 115.42 | lr=2.6e-3, l2=1e-6, hidden=(128,256,128) |

结论：mlp_v2 调参后优于基线（142.8kW）但仍远逊树模型 → **1200 样本确定性映射场景深度模型不占优**，选定 XGB 为最终模型。

### 阶段 3：残差分析与物理一致性 ✅

调参后 XGB 的 5-fold CV：

| 数据 | farm R² | farm MAE(kW) | farm RMSE(kW) |
|------|---------|--------------|---------------|
| GCH | 0.999978 | **7.79** | 22.43 |
| CC | 0.999961 | **10.49** | 29.97 |

- 分风速段 farm MAE（gch）：4-6m/s=2.87kW，6-9=5.56kW，9-12=**12.29kW**（高风速段是主要误差来源）
- 守恒：farm−Σturbine = 1W（设计保证）✅
- 边界：gch 在 [0,5MW] 内；cc 轻微越界（−0.66kW/约 +108kW）→ 推理需 clip [0,5e6]
- 单调性：cc 严格 OK；gch 额定饱和区有 <kW 级非单调抖动（无实际影响）

### 阶段 4：生产化交付 ✅

- 最终模型：**XGBoost 原生 .json**（替代 ONNX：零额外依赖、无损、加载快）
- 位置：`optimization_control/surrogate/models/final/`（`{gch,cc}_turbine_{1,2,3}.json` + `*_metadata.json`）
- 验证：加载前后预测差 **0 W**

---

## 5. 最终成果与结论

### 成果对比（farm 功率）

| 指标 | 厉今飞 MLP（基线） | 最终 XGB（本工作） | 提升 |
|------|-------------------|-------------------|------|
| gch farm MAE | 86.5 kW | **7.79 kW** | ~11 倍 |
| cc farm MAE | 103.1 kW | **10.49 kW** | ~10 倍 |
| gch farm R² | 0.99906 | **0.999978** | — |

### 关键结论

1. **树模型路线正确**：XGB/GPR 在低维、网格化、确定性数据上远超 MLP；深度路线留给后续 PINN 组
2. **误差热点**：高风速段（9-12 m/s，额定饱和平台区）是优化函数/数据精度的主攻方向（接袁夫达提议）
3. **GCH vs CC**：GCH 数据更平滑易拟合；CC 物理更准但更难——RL 环境两套都保留对比
4. **当前模型定位**：功率预测器（无偏航维度）。PPO 偏航控制需等袁夫达生成**含偏航数据**后重训
   （同一 pipeline，输入 6 特征 + yaw = 7 特征即可复用）

---

## 6. git 提交记录

```
2acc617 阶段2-4：Optuna调参+残差分析+最终XGB导出（farm MAE 86.5->7.8kW）
b839400 阶段1：候选模型实现与CV对比（XGB/GPR/two-stage 超越基线6倍）
17de9a5 阶段0：基线复现（numpy前向，指标与厉今飞完全一致）+评估协议+环境
b377d7b docs：补充厉今飞模型设计说明
537249a 修正 .gitignore（队友 README 入 git）
b22d0eb 接收队友成果并归档
d576c49 初始化项目框架
```

## 7. 下一步（阶段 5：RL 衔接）

1. 向袁夫达提出数据扩展需求：现有 1224 组 × 偏航角扫描（yaw ∈ [−30°, 30°]，步长 5~10°）→ 数据量 ~2 万组
2. 厉今飞/我方用同一 pipeline 重训含偏航代理模型（7 特征）
3. 代理模型接入 Gymnasium 环境 → PPO 训练 → 对比贪婪策略（任务 7-9）

相关文件索引：
- 方案：`optimization_control/surrogate/PLAN.md`
- 评估协议：`optimization_control/surrogate/eval_protocol.md`
- 实验记录：`optimization_control/experiments/20260807_surrogate_baseline/`
- 最终模型：`optimization_control/surrogate/models/final/`

## 8. 2026-08-23 恢复审计

- 结论和指标与 CSV、模型 metadata、XGBoost JSON 结构一致；六个最终模型均为 XGBoost 3.4.0、6 特征、529 棵树。
- 历史复现入口不可移植：`eval_baseline.py`、`train_and_eval.py`、`optuna_tune.py`、`stage3_analysis.py` 均含绝对路径。
- 历史实验目录缺 `config.yaml`，与当前项目规范不一致；后续实验必须补齐，不回填伪造的历史配置。
- `stage3_analysis.py` 的风向残差横坐标算法待复核；不影响已记录的整体 R²/MAE/RMSE，但影响按风向解释残差。
- 阶段 5 继续阻塞于含控制参数数据，下一动作见 `../TASKFLOW.md` 与项目根目录 `PROJECT_STATUS.md`。