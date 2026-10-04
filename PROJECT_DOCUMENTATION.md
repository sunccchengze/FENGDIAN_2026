# PINNs 多风机尾流模拟 —— 项目说明文档

## 1. 项目概述

本项目名为 **PINNs_multi_turbine_wake**，是一个基于**物理信息神经网络（Physics-Informed Neural Networks，简称 PINN）**的多风力涡轮机尾流场仿真与功率预测研究项目。其核心目标是利用深度学习方法替代传统计算流体力学（CFD）的高成本数值模拟，实现对多风机阵列在湍流风场中尾流效应的快速、高精度预测，并在此基础上进一步预测各机组的发电功率与有效风速。

风力发电场的效率高度依赖于风机之间的尾流干扰效应：上游风机产生的低速尾流会降低下游风机的来流风速，从而显著减少其发电功率，同时增加结构载荷。传统的 CFD 仿真虽然精度高，但每次模拟需要数小时甚至数天的计算时间，难以满足风电场布局优化、实时控制等需要大量迭代的场景。本项目试图通过 PINN 方法，在保持物理一致性的前提下，将模拟速度提升数个数量级，并在预训练模型的基础上实现向不同入流工况的迁移学习。

---

## 2. 项目目录结构

```
PINNs_multi_turbine_wake-outputchange/
├── README.md                    # 项目简要说明
├── LICENSE                      # 开源协议
├── requirements.txt             # Python 依赖清单
├── gitignore.txt                # Git 忽略规则
├── modify_pinn_io.py            # 修改原模型输入输出接口的核心脚本
├── prepare_pinn_outputchange.py # 冻结并准备原始预训练模型的脚本
├── Rectangular_grid/            # 矩形网格布置场景
│   ├── Rectangular_grid_config.py
│   ├── Run_multiturbine_model.py
│   ├── Post_Processing.ipynb
│   ├── Pre_trained/             # 预训练模型存放目录
│   └── Plots/                   # 可视化数据与结果
├── Diamond_grid/                # 菱形网格布置场景
│   ├── Diamond_grid_config.py
│   ├── Run_multiturbine_model.py
│   ├── Post_Processing.ipynb
│   ├── Pre_trained/
│   └── Plots/
└── Transfer_learning/           # 迁移学习模块
    ├── Grid_config.py
    └── Run_multiturbine_model.py
```

---

## 3. 科学背景

### 3.1 物理信息神经网络（PINN）

PINN 是由 Raissi 等人于 2019 年提出的一种将物理定律嵌入神经网络训练过程的方法。与传统数据驱动的深度学习方法不同，PINN 的损失函数不仅包含观测数据拟合项，还包含由偏微分方程（PDE）约束构建的物理残差项。这种设计使得模型即使在训练数据稀疏的情况下，也能保证解满足守恒律、动量方程等物理约束，从而具备更强的外推能力和泛化性。

### 3.2 尾流模拟的数学模型

本项目采用 **RANS（Reynolds-Averaged Navier-Stokes）方程** 配合 **k-ε 湍流模型** 对湍流风场进行建模。控制方程包括：

- **连续性方程**：$\nabla \cdot \mathbf{u} = 0$（不可压缩流体的质量守恒）
- **动量方程**：$\mathbf{u} \cdot \nabla \mathbf{u} = -\nabla p / \rho + \nabla \cdot ((\nu + \nu_\tau) \nabla \mathbf{u})$
- **湍流动能方程**：$\mathbf{u} \cdot \nabla k = \nabla \cdot ((\nu + \nu_\tau/\sigma_k)\nabla k) + P_k - \varepsilon$
- **耗散率方程**：$\mathbf{u} \cdot \nabla \varepsilon = \nabla \cdot ((\nu + \nu_\tau/\sigma_\varepsilon)\nabla \varepsilon) + (C_{\varepsilon1}P_k - C_{\varepsilon2}\varepsilon)\varepsilon/(k + 0.01)$

其中 $\nu_\tau = C_\mu k^2/\varepsilon$ 为涡粘系数，$P_k$ 为湍流动能生成项，六个模型常数为：
$\sigma_k = 1.0$，$\sigma_\varepsilon = 1.3$，$C_{\varepsilon1} = 1.176$，$C_{\varepsilon2} = 1.92$，$C_{\varepsilon4} = 0.37$，$C_\mu = 0.033$。

### 3.3 执行盘模型（Actuator Disc Model）

风机在流场中通过"执行盘"（Actuator Disc）近似表示。在盘面上的动量源项为高斯分布形式：

$$f_x = \frac{0.5 \, C_T \, U_{cl}^2}{\sqrt{2\pi}\,s_d} \exp\left(-0.5 \frac{(x - x_c)^2}{s_d^2}\right)$$

其中 $C_T$ 为推力系数（根据实验数据插值获得），$U_{cl}$ 为盘面中心处的本地来流速度，$s_d = R/6 \approx 2.51\,\text{m}$ 为高斯分布的标准差，$R = 15.05\,\text{m}$ 为转子半径。这一近似避免了直接解析风机叶片的几何细节，同时保留了主要的动量提取效应。

---

## 4. 神经网络架构

### 4.1 原始预训练模型

原始 PINN 模型的输入为三维空间坐标 $(x, y, z)$，输出为六个物理量的场分布：

| 输出头 | 物理量 | 含义 |
|--------|--------|------|
| `output_u` | 流向速度分量 | 沿主风向的速度 |
| `output_v` | 横向速度分量 | 垂直于来流方向的速度 |
| `output_w` | 竖直速度分量 | 高度方向的速度 |
| `output_p` | 压力场 | 流体压力 |
| `output_k` | 湍流动能 | 单位质量流体的湍流动能 |
| `output_eps` | 耗散率 | 湍流动能的耗散率 |

**网络结构**：

1. **输入缩放层**：将三个坐标分别除以所在方向的最大范围再乘以 100，使输入归一化到 $[0, 100]$ 量级。
2. **共享隐藏层**：三个全连接层，每层 700 个神经元，激活函数为 Swish（$x \cdot \text{sigmoid}(x)$），权重初始化使用 Glorot 均匀分布（种子 1234）。
3. **六个分支**：从共享层输出各自接一个 500 单元的全连接层（Swish 激活），再各接一个线性输出层（无偏置）。
4. **总参数量**：3,090,200 个参数，其中前三个隐藏层共 3,087,200 个参数，六个输出头各 500 个参数（无偏置）。

该模型在四个不同参考风速（7、8、9、10、11 m/s）下分别训练，每个训练场景运行 5000 个 epoch。

### 4.2 改进后的迁移模型（OutputChange 版本）

`modify_pinn_io.py` 脚本的核心任务是在保留原始预训练骨干网络（3,087,200 个冻结参数）的基础上，构建一个新的输入/输出接口，使其能够：

- 接受 **9 个控制变量** 作为额外输入（三台风机各自的偏航角、俯仰角、转速）
- 输出 **6 个标量物理量**（三台风机的功率 P1/P2/P3 和有效风速 Ueff1/Ueff2/Ueff3）

**架构细节**：

1. **`ExtendedInputDense` 层**：复用原始的 3→700 权重矩阵和偏置（冻结），但新增 9×700 的可训练权重矩阵（从零初始化），将控制变量投影到与坐标相同的 700 维隐空间。公式为：

   $$h = \text{Swish}\left(W_\text{coord} \cdot \mathbf{x}_\text{coord} + W_\text{control} \cdot \mathbf{x}_\text{control} + b_\text{original}\right)$$

   其中 $W_\text{control}$ 是唯一新增的可训练输入层参数（6,300 个）。

2. **原始隐藏网络**：完全冻结，保持原样，将 700 维隐状态映射到六个 500 维的特征分支。

3. **新的输出头**：六个 500→1 的线性层（各 3,000+1 个参数，共 18,006 个），用 Glorot 均匀分布初始化（种子 1234+索引），带 L2 正则化（系数 1e-4）。

4. **标准化层**：
   - `control_normalization`：对 9 个控制变量做 Z-score 标准化，统计量从训练集计算，不参与优化。
   - `output_units`：对 6 个输出做反向 Z-score 标准化，将归一化预测还原为物理单位。

5. **总可训练参数**：24,306 个（仅 0.79% 的原始参数），极大降低了迁移训练的数据和计算需求。

---

## 5. 训练流程详解

### 5.1 第一步：准备预训练骨干网络

运行命令：

```bash
python prepare_pinn_outputchange.py --velocity 9
```

该脚本执行以下操作：

1. 从 `Rectangular_grid/Pre_trained/9ms/` 加载作者提供的预训练模型（需验证参数总数恰好为 3,090,200）。
2. 将模型所有权重设为不可训练（`trainable=False`）。
3. 在四个检查点（`[-120.4, -105.35, 35.0]`、`[0, 0, 35]`、`[210.7, 105.35, 35]`、`[300, 0, 35]`）执行前向推理，确保输出有限且与冻结前完全一致。
4. 提取六个 500 维特征分支作为 `original_frozen_features.keras` 供后续使用。
5. 将冻结的完整模型保存为 `original_frozen.keras`。
6. 生成 `preparation_report.json`，记录 SHA-256 哈希值用于完整性校验。

### 5.2 第二步：构建并验证修改后的模型

运行命令：

```bash
python modify_pinn_io.py build
```

该步骤执行严格的结构性检查：

1. **权重完整性验证**：确认原始模型的 SHA-256 哈希在构建过程中未发生任何变化。
2. **梯度连通性检查**：在新内核权重为零的初始状态下，验证从九个控制输入到六个输出之间存在有效的反向传播路径。
3. **数值更新测试**：施加随机目标值，执行一步 SGD 更新，确认新权重确实发生变化，同时原始权重严格保持不变。
4. **非零连接测试**：临时给新权重赋予小扰动值，验证雅可比矩阵中所有控制输入方向的偏导数均不为零。
5. **保存/重载一致性**：将模型保存到 `.keras` 格式后重新加载，确认参数和预测结果完全一致。

通过所有检查后，脚本保存 `untrained.keras` 模型文件，并生成 `training_data_template.csv`（仅含列名的空模板）和 `model_summary.txt`。

### 5.3 第三步：监督式迁移训练

运行命令：

```bash
python modify_pinn_io.py train --csv cases.csv
```

训练数据的 CSV 文件需包含 9 列控制量和 6 列标签：

**控制量顺序**：`yaw1, pitch1, rotor_speed1, yaw2, pitch2, rotor_speed2, yaw3, pitch3, rotor_speed3`

**标签顺序**：`P1, P2, P3, Ueff1, Ueff2, Ueff3`（单位分别为 W, W, W, m/s, m/s, m/s）

**数据预处理**：
- 按控制量组合进行分组，相同设置的不同样本归入同一组，避免数据泄漏。
- 按 60/20/20 比例划分训练/验证/测试集（每组至少 2 个训练组）。
- 使用训练集的均值和标准差分别对输入和输出做 Z-score 标准化。
- 若存在恒定的控制量列，会在日志中警告（这些变量的影响无法被验证）。

**训练配置**：
- 优化器：Adam，初始学习率 1e-4，梯度裁剪范数 1.0
- 损失函数：均方误差（MSE）
- Early Stopping：监控验证损失，耐心值 30 个 epoch，恢复最优权重
- 默认最多 200 个 epoch，批次大小 16

**重要安全约束**：训练过程中持续检查原始权重的哈希值，一旦发现任何变化即中止训练并拒绝导出模型。

### 5.4 第四步：预测

运行命令：

```bash
python modify_pinn_io.py predict --controls 0.0 0.0 5.0 0.0 0.0 5.0 0.0 0.0 5.0
```

或从 CSV 文件批量预测：

```bash
python modify_pinn_io.py predict --csv predictions.csv --output results.csv
```

预测时自动检查控制量是否在训练范围内；超出范围时输出警告（表示正在外推）。输出结果包含六个物理量及其单位说明。

---

## 6. 配置文件

### 6.1 project_config.json

位于 `OutputChange/project_config.json`，是迁移模型的关键配置：

```json
{
  "turbine_positions_m": [[x1, y1, z1], [x2, y2, z2], [x3, y3, z3]],
  "control_units": {"yaw": "deg", "pitch": "deg", "rotor_speed": "rpm"},
  "fixed_inlet_wind_speed_m_s": 9.0,
  "notes": [...]
}
```

- `turbine_positions_m`：三台风机的三维坐标（单位：米），z 为轮毂高度，坐标系定义与原始模型一致（x 沿来流方向，y 横向，z 竖直）。
- `control_units`：角度单位可选 `deg` 或 `rad`，转速单位可选 `rpm` 或 `rad/s`。修改单位后必须确保训练数据和预测输入一致。
- `fixed_inlet_wind_speed_m_s`：固定入口风速（本版本为 9 m/s），CSV 中的环境条件列必须与此一致或为恒定值。

---

## 7. 原始模型训练（Rectangular / Diamond 网格）

### 7.1 空间离散与采样

以菱形网格为例（`Diamond_grid_config.py`），计算域定义为：

- x 方向：$[-150.6, 632.1]$ m（-10R 到 42R）
- y 方向：$[-255.7, 255.7]$ m（-17R 到 17R）
- z 方向：$[0.301, 225.75]$ m（0.02R 到 15R）

采用 **Hammersley 低差异序列采样**（来自 IDAES PSE 库）在域内生成 30,000 个训练点，并在每台风机周围生成 3,000 个细化点和 4,000 个盘面点。风机布置为四台：`(0,0,35)`、`(18R,0,35)`、`(9R,7R,35)`、`(9R,-7R,35)`。

### 7.2 边界条件

| 边界 | 条件 |
|------|------|
| 入口（inlet） | 对数风剖面：$u = u_*/\kappa \cdot \ln((z+z_0)/z_0)$，$v=w=0$，$k$ 和 $\varepsilon$ 按均匀值设定 |
| 出口（outlet） | 压力为零，法向梯度为零 |
| 地面（bottom） | 无滑移：$u=v=w=0$，$k$ 和 $\varepsilon$ 按壁面公式 |
| 顶部、前侧、后侧 | 对称/滑移边界，法向速度梯度为零 |

摩擦速度 $u_*$ 由参考高度的湍流强度计算：$u_* = \sqrt{k_\text{ref}} \cdot c_\mu^{1/4}$，其中 $k_\text{ref} = 1.5 \cdot (u_\text{ref} \cdot TI_\text{ref})^2$。

### 7.3 损失函数构成

总损失由多个分项加权组成：

$$\mathcal{L} = 10\mathcal{L}_\text{std} + \mathcal{L}_\text{residual} + \mathcal{L}_\text{residual_act} + 10\mathcal{L}_\text{da}$$

其中：
- $\mathcal{L}_\text{std}$：边界条件拟合损失（入口、底部、顶部、侧面速度/压力/湍流量）
- $\mathcal{L}_\text{residual}$：内部区域的 PDE 残差（动量方程×10 + 连续性×100 + k 方程 + ε 方程）
- $\mathcal{L}_\text{residual_act}$：执行盘区域的 PDE 残差（同样加权）
- $\mathcal{L}_\text{da}$：离散数据点（来自 `4wt_XY.csv`）的速度拟合损失

### 7.4 训练执行

运行 `Run_multiturbine_model.py` 启动训练，默认 5000 个 epoch，每 1000 个 epoch 打印一次损失日志并保存图片。训练完成后模型保存至 `out_hSaved_models/` 目录，按风速命名（如 `10ms/`）。

---

## 8. 后处理与可视化

每个网格场景均配备 `Post_Processing.ipynb` Jupyter Notebook，用于：

1. 加载训练好的模型和保存的数据。
2. 绘制速度剖面线图（保存在 `Plots/line_plots/`）。
3. 生成等值面数据（CSV 格式，保存在 `Plots/csv_data/`），用于后续渲染三维尾流云图。
4. 对比不同风机位置（0D、3D、6D、9D、12D、15D 下游距离）的速度恢复情况。

数据文件命名约定：
- `XY_ND.csv`：第 N 个转子下游 N 倍直径处的横截面速度数据
- `ZXN_ND.csv`：不同纵向截面的速度数据
- `stag_N_xy/zx*.csv`：交错布置的风机数据

---

## 9. 迁移学习（Transfer Learning）

`Transfer_learning/` 目录实现了从一个预训练风速向另一个目标风速的迁移。核心思路：

1. 加载在参考风速（如 9 m/s）下训练好的预训练模型。
2. 保持原始权重完全冻结。
3. 仅微调少量参数以适应新的入口风速条件。

配置要点（`Grid_config.py` 第 23 行和第 28 行）：
```python
u_ref = 11.                    # 目标风速
Pre_trained_model_velocity = 9 # 预训练模型的风速
```

迁移学习的价值在于：避免从零开始训练昂贵的 PINN 模型，利用已有知识加速新工况下的收敛。

---

## 10. 技术栈与依赖

| 包名 | 版本 | 用途 |
|------|------|------|
| tensorflow | 2.16.1 | 深度学习框架 |
| tf-keras | 2.16.0 | TensorFlow 官方的 Keras 实现 |
| keras | 3.1.1 | Keras API（作为前端） |
| numpy | 1.23.5 | 数值计算 |
| pandas | 2.0.0 | 数据读写 |
| matplotlib | 3.7.1 | 可视化 |
| pyDOE | 0.3.8 | 实验设计采样 |
| idaes_pse | 2.4.0 | Hammersley 低差异序列采样 |

安装方式：`pip install -r requirements.txt`（需在指定的 conda 环境 `pinn-multi` 中运行）。

---

## 11. 关键注意事项与使用警告

### 11.1 版本锁定要求

本项目对 TensorFlow 和 tf-keras 的版本有严格要求（均为 2.16.x），混用其他版本可能导致模型加载失败或训练异常。建议始终在 `pinn-multi` conda 环境中运行。

### 11.2 固定环境条件

当前 OutputChange 版本的模型**仅接受固定入口风速**（默认 9 m/s）。如果 CSV 数据中包含变化的风速、风向或湍流强度列，脚本将报错并要求筛选为恒定工况的数据。这一限制源于当前仅设计了 9 个控制输入，未将环境条件接入网络。

### 11.3 有效风速（Ueff）的定义

`Ueff` 并非简单地取风机中心点的流速，而是按照项目约定的**转子盘有效风速**定义计算。直接使用中心点速度作为标签会导致训练偏差。

### 11.4 预训练布置与迁移目标的不匹配

原始模型在**四台风机**布置下训练，而 OutputChange 版本适配为**三台风机**。迁移到三台布置的准确性需要通过实际数据验证，不建议直接用于工程决策。

### 11.5 监督训练而非物理训练

OutputChange 版本的训练采用纯监督学习（MSE 损失），**不使用原始的 RANS/k-ε PDE 损失**。这意味着新模型拟合的是数据标签，而非物理方程——其泛化能力受训练数据覆盖范围的限制。

### 11.6 结构检查不等同于准确性验证

`modify_pinn_io.py build` 通过的所有数值检查仅验证了模型结构的正确性（权重冻结、梯度连通、保存一致性），**并不代表任何物理准确性或迁移加速效果**。迁移性能必须通过实际测试数据的误差指标来评估。

### 11.7 功率输出的物理约束

六个线性输出头不强制非负约束，预测结果可能出现负值（尤其是功率 P1/P2/P3）。在用于优化或决策前，需审查输出的物理合理性。

---

## 12. 工作流程总结

完整的使用流程如下：

```
1. 准备预训练骨干网络
   python prepare_pinn_outputchange.py --velocity 9
   ↓
   生成 OutputChange/prepared_9ms/original_frozen.keras

2. 构建并验证修改后的模型
   python modify_pinn_io.py build
   ↓
   生成 OutputChange/iochanged_9ms/untrained.keras
   生成 OutputChange/project_config.json（需手动填写风机坐标）

3. 准备训练数据 CSV
   列顺序：yaw1 pitch1 rotor_speed1 yaw2 pitch2 rotor_speed2
           yaw3 pitch3 rotor_speed3 P1 P2 P3 Ueff1 Ueff2 Ueff3

4. 执行迁移训练
   python modify_pinn_io.py train --csv cases.csv
   ↓
   生成 OutputChange/iochanged_9ms/training_<timestamp>/trained.keras

5. 预测新工况
   python modify_pinn_io.py predict --csv new_cases.csv --output results.csv
```

---

## 13. 项目意义与展望

本项目展示了 PINN 方法在风力发电领域的一个典型应用范式：**先通过高保真物理仿真训练一个通用尾流场预测器，再通过少量控制参数扩展其功能，最后利用迁移学习快速适应新工况**。这种"物理先验 + 数据微调"的两阶段策略，既保留了 CFD 仿真的物理一致性，又大幅降低了在线预测的计算成本。

未来的改进方向包括：
- 将入口风速、风向、湍流强度等环境条件纳入控制输入，消除固定风速的限制。
- 引入物理损失项作为正则化，增强模型在外推区域的一般性。
- 适配更多风机数量配置（当前为三台，原始为四台），扩大工程适用性。
- 探索非对称布置和复杂地形下的迁移性能。



因原文件太大，无法上传至github，暂时仅以此文档作为介绍。有任何具体文件需要可以再找我。