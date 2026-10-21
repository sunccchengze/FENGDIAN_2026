# 固定风况九输入迁移网络与三机控制联调

2026-10-07 用户确认范围：跟随队友九输入网络，在单一固定风况下训练联调副本，
跑通 MADDPG、P、PI 与统一执行器，不等待仿真标签、不要求真实精度或算法优势。

## 配置与数据

协议：[configs/fixed_pinn_demo.yaml](configs/fixed_pinn_demo.yaml)。风速 9 m/s、来流沿 +x、TI=0.1。
演示坐标 `(0,0,90)`、`(378,0,90)`、`(756,0,90)` m；间距、轮毂高度、TI 和执行器参数为
明确记录的演示假设，不是 PINN 组确认的实际三机布局或机型标定。
九输入范围：每机偏航失配角 ±0.35 rad，桨距 0–0.25 rad，转速 0.6–1.267 rad/s。

2048 个训练样本、256 个验证样本、256 个独立合成测试样本，master seed=42。
标签来自现有 `CoupledIntegrationPredictor`，仅有固定机组顺序的简化耦合：
不解析布局、TI、变风向或真实尾流偏转。合成数据的拟合误差只衡量对这个标签源的复现。
上游 Ueff 固定为 9 m/s，归一化采用常量输出 std=1，不要求每个输出都随每个控制变化。

训练加载队友 `untrained.keras`，保留原坐标缩放、第一层坐标权重、隐藏层和所有分支；
只更新 6300 个新增控制连接与 18006 个新读出参数。新读出初始化为标准化零输出即训练集均值；
控制和输出统计由训练集计算，验证集选早停权重，测试集不选参。训练前后及保存/重载核对冻结主体摘要。

## 运行

安装兼容依赖到项目内部独立目录（不会替换原 `.venv/Lib/site-packages`）：

```powershell
.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --target .venv\pinn_tf216 -r optimization_control\maddpg_wind_farm\requirements_pinn_demo.txt
```

从项目根目录完整运行，必须使用尚不存在的输出目录：

```powershell
.venv\Scripts\python.exe -X utf8 -m optimization_control.maddpg_wind_farm.fixed_pinn_demo all --output optimization_control/experiments/20261007_fixed_pinn_demo_reproduce
```

入口在导入数值库前启用协议指定的兼容目录。可分别使用 `prepare`、`fit`、`control`，
后三者使用同一实验根目录和相同配置；已有阶段目录不会覆盖。`control` 会重新训练一份短策略，
所以复现实验使用新目录。全流程运行输出位于 `data/`、`model/`、`model_checks/`、
`initial_evaluation/`、`training/`、`evaluation/`，三类小文件记录各阶段配置、指标和摘要。

## 接入与验收

外层十二维保持原字段，固定来流三个量只作上下文检查；模型收到九控制量和固定位置。
适配器转换 rad/rad/s 为 deg/rpm，归一化在模型内部完成。改变风况或控制越出训练域会明确报错；
不自动切回 Mock，不裁剪预测功率掩盖异常。合成演示工厂必须显式启用，无法通过正式物理模型准入。

九通道分别检查响应、桨距反馈符号，检查端点及联合样本输出；之后运行 MADDPG 短训练与
相同初始条件/固定风况/目标/执行器下的固定、P、PI。功率目标每回合固定，训练与评估覆盖 2.5/3.5/4.5 MW。
传统 yaw 跟踪固定风向，转速参考使用已有演示运行曲线，pitch 由 P/PI 功率误差修正。

验收包括实际模型推理、九通道响应、非零 MADDPG 更新、策略保存/重载动作一致和整个回合重复回放一致。
短训练与有限样本检查不证明稳定收敛、模型全域物理有效或 MADDPG 优于 PI。

## 本次运行结果

完整实验：`optimization_control/experiments/20261007_fixed_pinn_demo_checked/`。
此前 `20261007_fixed_pinn_demo/` 仅完成数据准备，保留为准备记录；正式结果以 checked 目录为准。

- 迁移训练 80 轮，验证最优为第 80 轮，标准化验证损失从 0.8362 降至 0.05078。
- 原冻结主体 SHA256 与队友构建报告一致，九个新增控制矩阵行均已非零；队友七个源文件/权重摘要未变。
- 独立合成测试单机功率 RMSE 为 47.25 / 101.70 / 101.49 kW，Ueff RMSE 为 0 / 0.04163 / 0.05912 m/s。
  这是合成标签拟合误差，不是真实流场误差。
- 149 个运行点/响应探针通过有限输出、九通道响应与桨距反馈符号检查；功率范围 0.3283–2.2933 MW/机。
  响应检查不等于物理方向全面正确：例如 yaw2 探针单机功率增量约 +1.82 kW，未复现标签源的自身偏航损失。
  当前不针对这些精度问题追加研究，保留敏感性指标供后续模型改进。
- MADDPG 共 2048 步、16 回合、897 次联合更新；保存/重载动作一致、重复 reset 与完整回合回放逐值一致。
- 23 项不同相关单元/回归测试通过。实际评估 1536 行轨迹符合固定来流、运行点边界、机舱朝向与 gamma 关系。
  实际每步最大 yaw/pitch/speed 变化为 0.005 / 0.00872665 / 0.04329264，未超过设定限速。
- 初始策略评估与训练后评估中的 fixed/P/PI 轨迹完全一致，避免基线条件改变。

全回合跟踪 RMSE，单位 kW；单一 seed 的短训练，仅用于展示流程结果：

| 固定目标 | 初始 MADDPG | 训练后 MADDPG | 固定控制 | P | PI |
|---|---:|---:|---:|---:|---:|
| 2.5 MW | 1932.54 | 997.28 | 1932.77 | 878.30 | 579.75 |
| 3.5 MW | 932.51 | 112.61 | 932.77 | 420.68 | 242.72 |
| 4.5 MW | 67.51 | 940.90 | 67.23 | 3.53 | 2.89 |

流程验收通过；策略没有跨目标稳定学习，4.5 MW 训练后明显退化，不能宣称收敛或算法整体优势。
2026-10-07 后续核查见 [FIXED_PINN_DIAGNOSTIC.md](FIXED_PINN_DIAGNOSTIC.md)：指标复算正确，
初始约 4.433 MW、训练后三目标均约 3.5 MW；目标可达但响应弱、Critic 判断失配。
P/PI 个位数 kW 仅是固定无噪声网络内跟踪误差，同运行点合成标签源检查约 288–290 kW，不能当作真实功率精度。
原联调及后续目标响应诊断均已完成；未在这组评估结果上继续调参。小规模训练改进尚未启动，
需要另立新验证/测试；真实精度仍待真实标签。

本地主要产物：

- 联调模型：`model/trained.keras`；归一化保存在模型内部，`training_report.json` 和 `config_used.json` 记录来源与范围。
- MADDPG：`training/checkpoint.pth`；观测/动作缩放：`training/normalization.json`。
- 表格：根目录 `metrics.csv`（初始/训练对照），`model_checks/metrics.csv`（九通道响应）。
- 轨迹与功率图：`evaluation/trajectories.csv`、`evaluation/fixed9_target_3500000w.png` 等。
- 训练曲线：`training_curves.png`；三机执行器运行点：`applied_controls.png`。

原数据、权重与图像不进入 Git；各阶段顶层三类小文件和报告纳入 Git。兼容环境实测
TensorFlow 2.16.1、tf_keras 2.16.0、NumPy 1.26.4、SciPy 1.12.0；原 RL 环境保留。
