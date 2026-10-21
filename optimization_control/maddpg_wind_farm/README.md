# 三台风机 MADDPG

稳定训练、验证集选模、独立重复与固定测试流程见 [STABLE_TRAINING.md](STABLE_TRAINING.md)。
后续混合风况的退化定位、逐因素对照与验证选参 P/PI 基线见 [MIXED_STABILITY.md](MIXED_STABILITY.md)。
功率可达性证明、误差分解和联合风速/目标采样实验见 [REACHABILITY_TRACKING.md](REACHABILITY_TRACKING.md)。
2026-10-07 当前优先固定风况下的队友九输入迁移网络联调，见 [FIXED_PINN_DEMO.md](FIXED_PINN_DEMO.md)；
合成标签训练副本与正式物理模型验收分别处理，原 Mock/随机风况默认入口保留。
原表高目标退化与 P/PI 个位数 kW 的核查见 [FIXED_PINN_DIAGNOSTIC.md](FIXED_PINN_DIAGNOSTIC.md)。
固定九输入的单目标、多目标及通道逐级能力验证见 [FIXED_CURRICULUM.md](FIXED_CURRICULUM.md)：已完成实验，完整可靠性门槛仍未通过。
不可达任务的奖励/价值失配与终止步骤离线审计见 [VALUE_BASELINE_DIAGNOSTIC.md](VALUE_BASELINE_DIAGNOSTIC.md)。

固定三台风机、直线等间距；每台独立 Actor 和集中式 Critic，联合回放、目标网络、
确定性策略梯度与高斯探索。实现参考 [MADDPG 原论文](https://arxiv.org/abs/1706.02275)，
不含论文中的策略集成扩展。当前默认对象是未标定的联调模型，不是 PINN、CFD 或真实风机。

## 文件与边界

- `algorithm.py`：Actor/Critic、联合回放、更新、完整检查点。
- `controllers.py`：固定参考、三通道 P/PI 组合；偏航跟踪/预设失配角、风速到转速参考曲线、桨距反馈。
- `workflow.py`：训练、恢复、评估、CSV 和绘图入口。
- `verify_workflow.py`：连续训练与断点恢复、两次磁盘回放的端到端一致性验证。
- `configs/default.yaml`：seed=42；算法、执行器、对象接口、工况和基准参数。
- `configs/stochastic_inflow.yaml`：三类随机入口、慢变风向、背景 TI 与统一评估场景。
- `diagnostics.py`：固定可达目标、三种控制权限、初始/训练策略/P/PI、奖励尺度诊断。
- `diagnose_fixed_pinn.py`：已保存固定九输入实验的指标复算、目标响应、稳态可行点及 Critic 首步反事实回放；不训练、不覆盖原实验。报告放同目录，CSV/图表放日期命名实验目录。
- `fixed_curriculum.py`：固定九输入模型的单目标桨距、多目标桨距、转速与偏航逐级训练；协议放 `configs/`，运行/恢复/验收记录沿用日期实验目录，不覆盖旧策略。
- `inflow_workflow.py`：风况统计、CSV/JSON 回放、同权限及完整方案对照。
- `../environments/farm_inflow.py`：复用旧 Kaimal 速度生成器，增加入口方向与 TI。
- `../environments/pinn_adapter.py`：变化的 PINN 输入与固定六维输出之间的适配。
- `../environments/maddpg_farm_env.py`：三智能体数组接口；复用项目动作映射和执行器。
- `../tests/test_maddpg.py`：接口、环境、学习更新和恢复一致性测试。

模块新增文件沿用英文小写下划线；配置放 `configs/`；运行产物放现有
`../experiments/YYYYMMDD_简短描述/`。目录存在即拒绝覆盖，不自动删除旧模型或实验。

## 接口与控制时序

默认 PINN 输入 `[B,12]`：

```text
U_inf, direction, TI,
gamma_1, gamma_2, gamma_3,
beta_1, beta_2, beta_3,
omega_1, omega_2, omega_3
```

配置中的完整具名字段见 `plant.features`。九个控制量必需且只能由执行器提供。
方向编码可使用 `wind_direction_sin` 和 `wind_direction_cos`；额外固定量使用
`plant.constants`，变化的额外量可在 Python 中通过 `PINNAdapter(extra_provider=...)`
提供，该函数接收当前 `DisturbanceBatch, AppliedOperatingPoint`，返回 scalar 或 `[B]` 的具名字段。
不得覆盖已有控制或风况。变化的附加物理因素是否还需进入策略观测，应另行检查。

输出 `[B,6]` 始终为 `[P1,P2,P3,Ueff1,Ueff2,Ueff3]`，单位 W、m/s；功率非负且不得
超过配置额定值（允许 0.1% 数值容差），不裁剪错误预测。输入控制角单位 rad，转速 rad/s。
`plant.bounds` 必须覆盖全部输入特征，越界在调用网络前报错。这是声明域检查，不是误差或
不确定度估计；六维输出本身无法证明模型可信度。旧 `SteadyPlantOutput.floris_*` 字段仅作
内部兼容容器，CSV/summary 中的 `source` 和 `power_semantics` 标识实际来源。

每步顺序：当前观测和已公布的固定目标 → 三机动作 → 动作映射 → 执行器限速/跟踪 →
当前步结束时风况 → PINN 六维预测 → 全场共享奖励 → 下一观测。每回合目标保持不变。
缺额直接记录，目标不会随本策略降载而降低。目标不超过额定和不等于物理上可达；
`reachability.py` 可检查当前特定 Mock 的稳态可达性，不提供真实 PINN 或瞬态可达性认证。

每机动作 `[yaw_reference, pitch_reference, rotor_speed_reference]` 位于 `[-1,1]`，
映射为绝对设定值；动作零表示物理区间中点，不表示保持。实际转速运行点由执行器生成。
默认 `yaw_frame: nacelle_heading`：偏航动作给出期望失配角 gamma_ref，环境利用当前风向
转换为最短转动路径的机舱朝向参考。执行器推进连续机舱角 psi，随后使用新风向计算
`gamma=wrap(psi-theta)` 送 PINN。限制的是 dpsi/dt，不能把风向导致的 gamma 突变裁剪掉。
默认机舱角数值边界 +/-100pi 只是联调防护，不是已标定的电缆扭转模型；本版本不模拟解缆。
旧配置未设置 yaw_frame 时保留 legacy_misalignment 语义，以便复查历史权重；新风向任务必须用新模式。
第一版三通道均每步采样、零命令延迟，带不同时间常数和速率限制。增加多速率或延迟时必须
同时扩展观测中的保持参考/队列信息，不能只改执行器而隐去相关状态。

每机 15 维观测按 `OBSERVATIONS` 固定顺序：

1. 本机功率/额定功率、有效风速/风速尺度；
2. 本机已施加偏航、桨距、转速，分别线性映射到 `[-1,1]`；
3. 上一步本机三个归一化命令；
4. 全场目标/额定和、全场误差/额定和；
5. 公共入口风速/风速尺度、风向 sin/cos、TI；
6. 剩余回合比例。

全场目标、误差和入口风况是允许广播的信息。Actor 不读取其他机组原始观测；Critic 拼接
全部三机观测与动作。上述观测不声称重建完整气象/尾流 Markov 状态。归一化使用固定物理尺度，
没有依赖训练批次的运行统计；随检查点保存并另存 `normalization.json`。

共享奖励：`-((P_farm-target)/rated_farm)^2 - action_change_weight*mean((a-a_prev)^2)`。
可用正数 `environment.reward_scale` 统一乘整项奖励（默认 1），保持跟踪与动作惩罚的比例；
诊断配置中的 100 仅检验数值敏感性，未据单次实验替换默认值。
执行器硬约束负责位置/速率限制，并在指标中记录触发比例；超出对象有效域直接停止。
不添加无载荷输出支撑的载荷奖励。有限回合的剩余时间可见，终点 `terminated=True`，
Bellman 目标不再 bootstrap；不要把它改成自动重置后的下一回合观测。

## 运行

在项目根目录使用现有 `.venv`。当前工作流在 CPU 上运行，设置一个 PyTorch 线程并启用确定性算法。

```powershell
& .\.venv\Scripts\python.exe -m optimization_control.maddpg_wind_farm.workflow train --output optimization_control/experiments/20260922_maddpg_smoke
& .\.venv\Scripts\python.exe -m optimization_control.maddpg_wind_farm.workflow evaluate --checkpoint optimization_control/experiments/20260922_maddpg_smoke/checkpoint.pth --output optimization_control/experiments/20260922_maddpg_eval
```

以上目录已存在时换一个日期/后缀。训练默认 2048 步，仅验证流程，不是收敛预算。
训练在回合间轮换配置的目标比例，回合内固定；初始状态固定、风况按 `seed + episode_index`
生成。评估使用 `seed + evaluation.seed_offset + scenario_index`，不同控制器复用相同场景种子。

恢复训练：复制配置至新的实验目录或任务配置，将 `training.total_steps` 改为更大的回合长度
整数倍，再执行 `train --config <配置> --checkpoint <旧检查点> --output <新目录>`。
`total_steps` 表示累计目标步数。恢复只允许这个字段变化，以防模型、归一化或学习参数静默切换。
检查点保存完整回放池、所有网络/优化器和随机状态，默认在训练正常结束的回合边界保存；
不提供中途崩溃的逐步恢复保证。只加载可信本地检查点，完整恢复使用 PyTorch pickle 加载。

单步决策：

```python
from optimization_control.maddpg_wind_farm.algorithm import MADDPG
agent, metadata = MADDPG.load("path/to/checkpoint.pth")
actions = agent.act(observation)  # observation [3,15], actions [3,3]; no exploration
```

训练输出 `config.yaml / metrics.csv / summary.txt / checkpoint.pth / normalization.json`。
评估输出 `config.yaml / metrics.csv / summary.txt / trajectories.csv` 和每场景 PNG。
轨迹包含三机功率、有效风速、全部九个命令和已施加状态；PNG 显示全场对照、三机功率和 T1 命令。

## 接入 PINN 组模型

将 `plant.kind` 改为 `pinn`，设置来源、功率口径、`model_version`、布局间距、额定值、
字段列表、有效域及需要的归一化参数；`factory` 使用 `your_package.bridge:create_predictor`。
此工厂在初始化时接收 `plant.backend` 字典并加载模型一次，返回一个 NumPy 批量预测函数：

```python
def create_predictor(backend_config):
    model = load_your_model(backend_config["weights"])
    def predict(normalized_inputs):
        # Use eval/inference mode for your framework; return NumPy [B,6].
        return run_your_model(model, normalized_inputs)
    return predict
```

上面是后端接入示意，`load_your_model/run_your_model` 由模型交付方提供。如果模型已内置预处理，
适配器对应均值/尺度使用恒等值，防止双重归一化。
适配器公式为 `x_model=(x_physical-input_mean)/input_scale`，
`y_physical=y_model*output_scale+output_mean`。缺省均值 0、尺度 1，顺序分别与输入字段和六维输出一致。
后端加载失败、配置不足、越界或预测形状不符均报错，绝不自动改用 Mock。

## 对照解释和验收

固定/P/PI 与 MADDPG 共享对象、风况、初始点、目标与执行器。默认 P/PI 的偏航跟踪来流
（可配置 yaw_offset_rad），转速参考为 `clip(speed_per_wind_rad_m * Ueff_i)`，桨距用全场误差反馈。
转速曲线系数是联调假设；真实机型需提供运行曲线。固定参考组的 gamma_ref 固定，因此变风向时机舱仍会跟风转动。
`control_mask` 按 yaw/pitch/speed 排列：[0,1,0]、[0,1,1]、[1,1,1] 分别是三种诊断权限。
禁用通道固定为初始参考；网络推理/探索、目标网络、Actor 梯度、回放和环境均使用相同屏蔽。
逐通道比较使用相同启用通道，完整方案比较允许 MADDPG 学习联合动作、传统方案使用显式调度，
但均受相同执行器约束。控制权限相同不代表结构、信息利用或调参预算相同，不能据单次分数宣称算法优势。
P 的误差符号采用正功率误差增加桨距；真实模型须验证这个方向在启用域成立。
PI 用实际桨距与未限幅命令的差进行跟踪抗饱和，积分量另有上限。

```powershell
& .\.venv\Scripts\python.exe -m unittest optimization_control.tests.test_maddpg -v
& .\.venv\Scripts\python.exe -m unittest discover -s optimization_control/tests -p 'test_*.py' -v
& .\.venv\Scripts\python.exe -m unittest optimization_control.ppo_single_turbine.test_baseline -v
& .\.venv\Scripts\python.exe -m optimization_control.maddpg_wind_farm.verify_workflow --output optimization_control/experiments/20260922_maddpg_verification
```

关键证据：输入顺序/扩展/归一化正确，六维输出不混淆，控制影响下游，执行器限速，目标固定，
回合重置可复现，终点掩码正确，三套网络更新，软更新正确，保存加载后动作/噪声/下一更新一致。
联调对象固定机组索引为上下游顺序，忽略风向、TI 和实际间距；它仅检验软件链路。
真实 PINN 未交付前，不报告物理收益、真实动态响应或算法性能优势。

## 随机入口与复现

方法参考 [TurbSim v2 Kaimal 谱](https://openfast.readthedocs.io/en/main/_downloads/cb14d3e2d3533d76e405d730fea19846/TurbSim_v2.00.pdf)。
复用 `wind_generator.py` 的背景+带限 Kaimal 湍流+事件，不另造三条独立风速。
入口输出 `[U_inf(t),theta_inf(t),TI_background]`，仍映射到原 12 维 PINN 输入。
不含空间相干性、尾流或机位传播延迟，Ueff 仍完全由 PINN 输出。

默认训练回合 600 s、dt=1 s，均风 7.5–9 m/s，TI 从 0.06/0.08/0.10 抽取；
平稳、慢变和阵风三类场景混合。背景 TI 是标定谱的参数，回合内固定，不把阵风或趋势计为 TI。
慢变化时湍流残差仍采用回合初始均风标定。方向采用随机初相位的低频正弦，慢变场景可加平滑趋势，
属于训练设计，不宣称符合 IEC 方向湍流谱。所有方向与机舱角必须使用 PINN 约定的同一坐标/符号。
未来风况及隐藏生成参数不提供给策略；瞬时输入与真实 PINN 的统计窗口仍需交接确认。

默认随机任务把 yaw_ref 范围缩至 +/-0.45 rad，保留风向变化余量，PINN 的 gamma 域仍为 +/-0.524 rad。
余量不是任意风向变化下的安全保证；实际失配角越域直接报错。风速/方向/TI 全轨迹先检查声明域，
控制状态每步再检查；拒绝采样次数保留，不裁剪风速来强行进入有效域。

主种子仍为 42，速度复用 SeedSequence 的 train/validation/test 分流及 episode 编号；方向使用
独立派生流。随机训练使用固定主种子和累计回合编号，恢复时不重复前半程风况。
训练、验证、测试流隔离；所有控制器使用同一条预生成轨迹，目标在回合内固定。
CSV 七列为时间、风速、方向、背景 TI、背景风、湍流、事件，同名 JSON 保存参数、版本和 SHA-256。
`env.reset(options={"wind_trace_path": "...csv"})` 可回放，校验失败拒绝运行。

```powershell
& .\.venv\Scripts\python.exe -m optimization_control.maddpg_wind_farm.workflow train --config optimization_control/maddpg_wind_farm/configs/stochastic_inflow.yaml --output optimization_control/experiments/20260922_maddpg_stochastic_train
& .\.venv\Scripts\python.exe -m optimization_control.maddpg_wind_farm.diagnostics --output optimization_control/experiments/20260922_maddpg_channel_diagnosis --steps 8192 --reward-scales 1
& .\.venv\Scripts\python.exe -m optimization_control.maddpg_wind_farm.diagnostics --output optimization_control/experiments/20260922_maddpg_reward_diagnosis --steps 8192 --reward-scales 100 --modes pitch all
& .\.venv\Scripts\python.exe -m optimization_control.maddpg_wind_farm.inflow_workflow --output optimization_control/experiments/20260922_farm_inflow_validation --checkpoint optimization_control/experiments/20260922_maddpg_stochastic_train/checkpoint.pth
& .\.venv\Scripts\python.exe -m optimization_control.maddpg_wind_farm.verify_workflow --config optimization_control/maddpg_wind_farm/configs/stochastic_inflow.yaml --output optimization_control/experiments/20260922_maddpg_stochastic_resume
```

以上目录是已运行记录，复跑使用新后缀。统计验收对每类 64 条独立验证风况计算集合 PSD/理论谱
（0.03–0.35 Hz，接受 0.8–1.2）及残差均方/离散带限理论方差（接受 0.75–1.25）；
不逐条强制均值或方差。1 s 步长以上的高频能量被舍弃，不能据此报告高频载荷精度。
评估三类测试轨迹共 39 个控制器/权限组合，另做全部组合的磁盘/内存精确一致验收。
具体结果与原因判断见 [本轮诊断报告](DIAGNOSTIC_REPORT.md)。
