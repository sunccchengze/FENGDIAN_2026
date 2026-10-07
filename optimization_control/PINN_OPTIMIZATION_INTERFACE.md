# PINN—优化控制交接接口规范（组会决策稿 v0.3）

## 2026-10-07 固定风况九输入交付联调

用户确认当前跟随队友网络：内部九个控制输入，辅助输入为固定三机坐标，风速、风向、TI 固定。
外层十二维物理字段保持不变，前三个来流量仅用于一致性检查；适配器转换控制顺序和单位，
不宣称该九输入模型支持随机来流。机舱朝向执行器与 gamma 关系沿用下文已确认语义。
当前允许现有 Mock 合成标签训练副本，仅用于流程演示；正式物理验收要求仍独立保留。
交付检查见 [PINN_HANDOVER_REVIEW.md](maddpg_wind_farm/PINN_HANDOVER_REVIEW.md)，
本轮协议和运行入口见 [FIXED_PINN_DEMO.md](maddpg_wind_farm/FIXED_PINN_DEMO.md)。

## 2026-09-22 三机 MADDPG 增量（优先于下文旧任务默认值）

本轮补充：随机入口维持 12 维，U 为控制采样时刻入口风速，TI 为生成该背景湍流谱的
统计参数，不是逐时刻计算的 TI；真实 PINN 必须确认这一时间尺度。随机来流不含尾流。
风向和机舱朝向使用同一角度约定，gamma=wrap(机舱朝向-来流方向)。统一执行器推进
机舱朝向 psi，限制 dpsi/dt；下一时刻结合新风向计算 gamma 送 PINN，不能限制 dgamma/dt
来代替物理偏航速率。指令仍为期望失配角，由当前可观测风向转换为最短路径机舱朝向目标。
风向变化导致 gamma 越出 PINN 有效域时明确报错，不能裁剪真实失配角伪造状态。
传统控制使用偏航跟踪/预设失配角、有效风速到转速参考曲线、P/PI 桨距反馈，全部共用执行器。
逐通道诊断禁用的通道采用相同固定参考，独立报告同权限对比与三通道完整方案对比。

用户已确认：固定三台风机直线等间距；每台控制偏航、集体桨距、转速参考。
布局数值由对象模型配置固定，不作为优化变量。第一版为准静态对象加优化侧执行器。
参考采用外部给定、回合内固定的全场目标，不使用下文旧版平滑参考默认模式。

PINN 输出固定为 `[P1,P2,P3,Ueff1,Ueff2,Ueff3]`，批量形状 `[B,6]`，单位 W、m/s。
默认输入为 `[ambient_wind_speed_m_s,ambient_wind_direction_rad,turbulence_intensity,
gamma_1,gamma_2,gamma_3,beta_1,beta_2,beta_3,omega_1,omega_2,omega_3]`。
九个控制字段始终必需，单位 rad、rad、rad/s，取自执行器已施加运行点而非策略原始动作。
其余输入及顺序通过适配配置定义，支持风向 sin/cos 和额外具名工况，缺失字段拒绝运行。
输入输出归一化由适配器显式配置；网络后端统一为接收 `[B,D]`、返回 `[B,6]` 的可调用对象。

真实 PINN 必须说明功率口径、机组顺序、机型/布局和输入有效域；不将六个预测值中的任何一个
视为有效域证明。现有内部 `floris_*` 字段名仅为兼容容器，真实来源以适配器元数据为准。
不重复预测执行器状态；总功率由三个功率求和。原有单机/PPO 接口维持兼容。
模拟对象只用于接口、梯度更新、回放及训练流程验证，不能形成物理控制或算法优势结论。

> 日期：2026-08-24
>
> 面向任务：PINN 代理模型 → PPO/MADDPG 环境 → 风电场功率波动控制
>
> 状态：已记录第一轮组会决策；带 `[TBD]` 的数值必须由仿真、PINN、优化三方确认后冻结

## 0. 先给结论

正式动态功率波动控制最终需要的不是“输入风况后只输出一次流场或功率”的 PINN，而是一个**受控制量约束、可连续推进、可批量调用的风机/风场对象模型**：

```text
当前状态 state_t
  + 外部风况 disturbance_t
  + 已施加控制 applied_control_t
  + 时间步 dt_s
        ↓
PINN / 代理模型
        ↓
下一状态 state_t+1
  + 各机/全场功率
  + 载荷或安全量
  + 有效域/不确定度信息
```

完整训练闭环应为：

```text
state_t + disturbance_t + power_reference_t
        ↓
PPO 输出归一化动作
        ↓
优化侧动作映射、限幅、限速、延迟
        ↓
applied_control_t
        ↓
PINN: (state_t, disturbance_t, applied_control_t, dt_s)
        ↓
state_t+1 + power_t+1 + safety_t+1
        ↓
优化侧计算 reward_t，反馈 PPO
```

因此：

1. 凡是 PPO 当前启用的控制量，都必须进入 PINN/对象模型，并在训练数据中有真实变化；不支持的动作必须显式禁用。
2. 若 PINN 只有稳态快照映射，它只能支撑静态参数优化或准静态预研，不能据此声称完成了动态功率波动控制。
3. `rotor_speed_rad_s` 在真实风机中是动态状态，不是可瞬时设置的执行器；当前 v0 因仿真侧难以交付转矩数据，采用带独立执行器模型的转速参考值抽象。
4. PINN 与优化之间只交换具名物理量；PINN 归一化和 PPO 观测归一化分别封装，禁止双重归一化。

### 0.1 当前项目落地决策（2026-08-23）

已冻结的第一阶段方案为：

1. PINN v0 定位为 `quasi_static`：`current_wind_condition + current/applied_control_operating_point → steady_turbine_state/power`。
2. 当前仿真数据若只包含相互独立的当前风况、当前控制参数和对应输出，就不具备训练 `dynamic_transition` 的信息。
3. v0 计划支持 yaw、pitch 和 rotor-speed operating point/reference；暂不要求 generator torque。任一字段只有在仿真中真实扫描且通过控制敏感性验证后才能标记为“已支持”。
4. “调转速”在 PPO 层表示为转速参考命令，由优化组维护的独立 `ActuatorModel` 执行限幅、限速、延迟和跟踪，不表示真实转子可以瞬时跳到指定转速。
5. `model_dt_s` 对 `quasi_static` 模型为 `not_applicable`；`control_interval_s` 与 `yaw_update_period_s` 暂为 `[TBD]`，按第 6.3 节的证据流程确定。
6. 最终控制目标的功率口径冻结为电有功功率；当前数据在仿真组确认原始生成脚本和风机功率配置前，严谨命名为 `floris_turbine_power_w` / `floris_farm_power_sum_w`。
7. FLORIS 准静态功率不是天然的时间区间平均值。v0 环境将准静态功率在 `[t, t + control_interval_s)` 内零阶保持，由此定义环境的区间平均功率；这是环境假设，不是 PINN 学到的动态平均。
8. `farm_power_reference_w` 由优化侧的因果参考生成器从可利用功率生成，同时施加爬坡限制和降载裕度。
9. 角度、风向和偏航按第 2.2 节冻结；布局、风机数量和 `turbine_ids` 顺序在第一版固定。
10. 顶层 `plant_model` 向优化组返回完整的结构化风机状态；PINN、`ActuatorModel` 和环境对每个字段遵循“单一权威更新者”原则。

上述 v0 可以用于准静态参考跟踪与控制逻辑验证，但不包含真实转子惯性、尾流传播和瞬态功率响应，结题表述中必须明确这一限制。

## 1. 三方职责边界

| 参与方 | 负责内容 | 不应转交给下游猜测的内容 |
|---|---|---|
| 仿真组 | v0 生成风况+控制运行点的稳态扫描；未来动态版再生成连续轨迹 | 坐标系、单位、控制实际值、采样/工况语义、初边值条件 |
| PINN 组 | v0 准静态代理；未来动态状态转移；归一化、有效域、推理接口和模型验证 | 网络结构、字段顺序、隐藏状态、流场到功率的算子 |
| 优化组 | PPO 观测、动作归一化、独立 `ActuatorModel`、奖励、训练和策略评估 | 不把工程假设伪装成 PINN 学到的物理动力学 |
| 三方共同 | 字段、单位、时间语义、执行器边界、目标定义和验收阈值 | 所有 `[TBD]` 项必须形成书面决定 |

`farm_power_reference_w` 等控制目标由优化侧持有，不应作为 PINN 物理预测的条件。PINN 应预测“系统在该动作下会发生什么”，而不是根据目标功率反推优化结果。

### 1.1 v0 状态更新唯一责任方

| 字段/过程 | 唯一更新者 | 说明 |
|---|---|---|
| `action_normalized` | PPO | 只提出无量纲动作，不直接改物理状态 |
| yaw/pitch/speed reference | `ActionMapper` | 完成动作缩放和命令级边界检查 |
| 实际 yaw、pitch、rotor speed operating point | 独立 `ActuatorModel` | 唯一负责限速、延迟、饱和和跟踪 |
| 有效风速、单机稳态功率及可交付载荷量 | quasi-static PINN/代理模型 | 使用已施加控制运行点进行预测 |
| 全场功率 | `StateAssembler` | v0 对有效风机功率做确定性求和 |
| 完整结构化状态 | `StateAssembler` | 只拼装和透传，不重复推进任何状态 |
| 参考功率、PPO 观测、奖励和终止条件 | 优化环境 | 不修改 PINN 或执行器物理状态 |

每个 `next_*` 或实际状态字段只能有一个权威生产者。如果 PINN 包内部已更新某个执行器状态，外部 `ActuatorModel` 必须停用对应更新；v0 当前选择由独立 `ActuatorModel` 更新执行器状态。

## 2. 统一命名、单位和张量约定

### 2.1 基本约定

- `B`：批量大小。
- `N`：风机数量；单机时仍保留 `N=1`。
- `H`：rollout 时间步数。
- `S/A/K`：状态、动作、流场隐变量维数。
- 在线风机标量统一为 `[B, N]`，风场标量统一为 `[B, 1]`。
- 风机位置统一为 `[N, 2]`，顺序由 `turbine_ids` 固定。
- 浮点张量统一为 `float32`；掩码用 `bool`。
- 跨组接口采用物理量；字段名必须带单位后缀。
- 角度接口统一用弧度：`*_rad`、`*_rad_s`。
- 原始 FLORIS/当前 PPO 中的角度可以是度，但必须在适配器内显式转换，不得仅写 `yaw`、`pitch`。
- `turbulence_intensity` 使用 0–1 的无量纲小数，例如 `0.08`，不能传整数百分数 `8`。
- 不使用 `power_1`、`power_2` 等固定台数命名。

### 2.2 风向和偏航约定

必须在 `metadata.json` 中冻结：

1. 风向是“来向”还是“去向”；
2. 0 rad 对应的全局轴；
3. 正方向为顺时针还是逆时针；
4. 周期归一化范围；
5. `yaw_misalignment_rad` 的正负定义。

本项目当前冻结为：

```text
ambient_wind_direction_rad:
    气象来向，0 指北，顺时针为正，范围 [0, 2π)

yaw_misalignment_rad:
    nacelle_heading_rad - ambient_wind_direction_rad
    结果 wrap 到 [-π, π)
```

如果 PINN 内部使用周期编码，由 PINN 包内部固定执行：

```text
wind_direction_sin = sin(ambient_wind_direction_rad)
wind_direction_cos = cos(ambient_wind_direction_rad)
```

禁止同时把角度和未经校验的 sin/cos 当作独立输入。

接口验收必须包含方向黄金测试：同向时偏航误差为 0；跨越 `0/2π` 时取最短角度差；正偏航动作的符号与定义一致；一个已知风向下的上下游风机识别正确。FLORIS、OpenFOAM 和 PINN 的原生方向约定统一由各自适配器转换。

## 3. 当前解析 PPO 参数与正式接口的对应关系

当前 `SimplifiedTurbineEnv` 是算法链路原型，不是正式 PINN 环境。现有字段映射如下：

| 当前符号/变量 | 当前含义与单位 | 当前范围/尺度 | 正式建议名称 | 说明 |
|---|---|---|---|---|
| `P` / `self.P` | 单机功率，W | `0–5e6` | `active_power_w` | 最终目标为电有功；当前解析量仍只是简化功率 |
| `omega` / `self.omega` | 实际转速，rad/s | `0.1–1.267` | `rotor_speed_rad_s` | 状态，不是直接动作 |
| `omega_set` | 转速设定值，rad/s | `0.1–1.267` | `rotor_speed_reference_rad_s` | 必须与实际转速分字段 |
| `beta` / `self.beta` | 集体桨距角，deg | `0–25` | `collective_pitch_rad` | 进入正式接口前转换为 rad |
| `U` / `self.U` | 来流风速，m/s | 原型约 `4–12` | `ambient_wind_speed_m_s` | 正式多机还需区分环境风和盘面有效风 |
| `P_target` | 功率目标，W | 当前风况 `P_max(U)` 的 `65%–80%` | `farm_power_reference_w` | 属于优化目标，不是 PINN 物理输入 |
| `d_beta` | 每步桨距增量，deg/step | `±0.5`，`dt=1 s` | `collective_pitch_rate_command_rad_s` | 由动作适配器换算并限速 |
| `d_omega` | 每步转速参考增量，rad/s/step | `±0.1` | `delta_rotor_speed_reference_rad_s` | v0 继续采用高层转速参考，但改由独立 `ActuatorModel` 处理 |
| `dt` | 原型状态推进步长，s | `1` | `control_interval_s` | v0 的 `model_dt_s` 为 N/A；正式控制周期仍待确认 |
| `tau` | 转速一阶惯性常数，s | `5` | `rotor_speed_time_constant_s` | 解析假设，不得直接复制到 PINN |
| `ep_len` | 回合步数 | `200` | `episode_horizon_steps` | 优化内部参数 |

当前观测顺序为：

```text
[P, omega, beta, U, P_target]
```

当前归一化尺度为：

```text
[5e6 W, 1.267 rad/s, 25 deg, 12 m/s, 5e6 W]
```

当前奖励为：

```text
- (P_target - P)^2 / 1e12
- 0.1 * (d_beta^2 + d_omega^2)
```

这里把 `deg²` 与 `(rad/s)²` 直接相加，量纲和动作尺度不一致。正式奖励必须先用各自动作范围归一化，再计算动作惩罚。

接入 yaw、风向、湍流、多机尾流或新动作后，旧 PPO 权重的观测/动作维度会改变，必须重新训练。

## 4. PINN 模型静态元数据

以下字段放在 `metadata.json` 或 `interface_schema.json`，无需每次 `step()` 重传。

| 字段名 | 类型/单位 | Shape | 要求 | 说明 |
|---|---:|---:|---|---|
| `schema_version` | string | scalar | 必选 | 接口版本，如 `0.1.0` |
| `model_version` | string | scalar | 必选 | PINN 模型版本 |
| `training_data_version` | string | scalar | 必选 | 对应仿真数据版本 |
| `model_type` | enum | scalar | 必选 | v0 固定 `quasi_static`；未来动态版另发版本 |
| `dtype` | string | scalar | 必选 | 固定 `float32` |
| `model_dt_s` | s/null | scalar | 条件必选 | v0 为 `null`/`not_applicable`；动态版才是推进步长 |
| `control_interval_s` | s | scalar | 必选 | PPO 与 `ActuatorModel` 的控制更新间隔，当前 `[TBD]` |
| `yaw_update_period_s` | s | scalar | 使用 yaw 时必选 | 偏航更新周期，必须是控制周期整数倍，当前 `[TBD]` |
| `turbine_count` | int | scalar | 必选 | v0 固定支持的风机数量 |
| `turbine_ids` | string/int | `[N]` | 必选 | 固定输入输出顺序 |
| `turbine_positions_m` | m | `[N,2]` | 必选 | 固定全局坐标位置 |
| `layout_id` | string | scalar | 必选 | 固定布局标识 |
| `layout_version` | string | scalar | 必选 | 布局或 ID 顺序变化时升级 |
| `layout_sha256` | string | scalar | 推荐 | 布局文件校验值 |
| `hub_height_m` | m | `[N]` | 必选 | 轮毂高度 |
| `rotor_radius_m` | m | `[N]` | 必选 | 风轮半径 |
| `rated_power_w` | W | `[N]` | 必选 | 各机额定功率 |
| `rated_rotor_speed_rad_s` | rad/s | `[N]` | 必选 | 各机额定转速 |
| `coordinate_frame` | object | scalar | 必选 | 原点、轴和正方向 |
| `wind_direction_convention` | object | scalar | 必选 | 本文第 2.2 节内容 |
| `validity_domain` | object | scalar | 必选 | 每个输入的训练/验证范围 |
| `control_limits` | object | scalar | 必选 | 执行器位置、速率、延迟和饱和 |
| `normalization_version` | string | scalar | 必选 | 归一化文件版本 |
| `git_commit` | string | scalar | 推荐 | PINN 训练代码 commit |
| `model_sha256` | string | scalar | 推荐 | 模型文件校验值 |

### 4.1 执行器和安全边界

以下边界由优化组的 `ActuatorModel` 执行，但数值必须来自仿真配置、风机资料或三方书面认可的工程假设；当前解析原型参数不得直接复制成正式值：

```text
yaw_min_rad
yaw_max_rad
yaw_rate_limit_rad_s
yaw_command_delay_s

collective_pitch_min_rad
collective_pitch_max_rad
collective_pitch_rate_limit_rad_s
collective_pitch_command_delay_s

rotor_speed_min_rad_s
rotor_speed_max_rad_s
rotor_acceleration_limit_rad_s2

generator_torque_min_n_m
generator_torque_max_n_m
generator_torque_rate_limit_n_m_s

maximum_thrust_n
maximum_tower_base_moment_n_m
```

如果不同风机边界不同，上述字段使用 `[N]`。

## 5. PINN 单步输入字段

### 5.1 当前物理状态 `state_t`

对 v0 `quasi_static`，以下结构由顶层 `plant_model` 组装；PINN 核心接收的是当前风况和已施加的绝对运行点。`rotor_speed_rad_s` 在该版本中是 `ActuatorModel` 生成的运行点近似，不代表 PINN 学得了真实转子惯性。

| 字段名 | 单位 | Shape | 要求 | 说明 |
|---|---:|---:|---|---|
| `active_power_w` | W | `[B,N]` | 必选 | 最终目标口径为电有功；当前 FLORIS 数据确认前使用临时来源字段名 |
| `rotor_speed_rad_s` | rad/s | `[B,N]` | 必选 | 转子实际转速 |
| `collective_pitch_rad` | rad | `[B,N]` | 必选 | 实际集体桨距角 |
| `nacelle_heading_rad` | rad | `[B,N]` | 使用偏航时必选 | 机舱实际朝向 |
| `yaw_misalignment_rad` | rad | `[B,N]` | 推荐 | 可由方向与朝向派生，但只能有一个权威计算位置 |
| `effective_wind_speed_m_s` | m/s | `[B,N]` | 推荐 | 各风机转子盘等效来流 |
| `generator_torque_n_m` | N·m | `[B,N]` | 转矩控制时必选 | 当前实际转矩 |
| `previous_active_power_w` | W | `[B,N]` | 推荐 | 计算动态与爬坡率 |
| `previous_applied_control` | 见动作字段 | `[B,N,A]` | 推荐 | 执行器滞后和动作平滑 |
| `flow_state` | model-defined | `[B,N,K]` 或 `[B,K]` | 条件必选 | PINN/POD/循环模型的显式隐状态 |

若模型需要历史序列，必须显式改为：

```text
state_history: [B, H_history, N, S]
history_time_s: [B, H_history]
history_mask: [B, H_history, N]
```

禁止在模型内部保留不能由 `reset()` 清理的隐式全局状态，否则多个 PPO episode/并行环境会相互污染。

### 5.2 外部风况 `disturbance_t`

| 字段名 | 单位 | Shape | 要求 | 说明 |
|---|---:|---:|---|---|
| `time_s` | s | `[B,1]` | 推荐 | 当前轨迹相对时间 |
| `ambient_wind_speed_m_s` | m/s | `[B,1]` | 必选 | 上游自由来流，不等于盘面有效风 |
| `ambient_wind_direction_rad` | rad | `[B,1]` | 必选 | 遵循元数据方向约定 |
| `turbulence_intensity` | 1 | `[B,1]` | 必选 | 0–1 小数 |
| `air_density_kg_m3` | kg/m³ | `[B,1]` | 条件必选 | 若固定则写入元数据，不必每步传 |
| `wind_shear_exponent` | 1 | `[B,1]` | 可选 | 数据包含风切变时使用 |
| `ambient_temperature_k` | K | `[B,1]` | 可选 | 模型依赖温度时使用 |
| `turbine_mask` | bool | `[B,N]` | 变台数时必选 | 区分有效风机和 padding |

如果仿真直接交付风矢量，可以用：

```text
ambient_wind_u_m_s
ambient_wind_v_m_s
ambient_wind_w_m_s
```

风速/风向与风矢量二选一作为权威输入，不得两套数值不一致。

### 5.3 不属于 PINN 物理输入的优化目标

这些字段进入 Gym/PettingZoo 环境和 PPO 观测/奖励，不进入 PINN 状态转移：

| 字段名 | 单位 | 说明 |
|---|---:|---|
| `reference_mode` | enum | v0 固定 `available_power_smoothing`；预留 `dispatch_tracking` |
| `farm_power_reference_w` | W | 因果参考生成器给出的可达跟踪目标 |
| `farm_available_power_w` | W | 当前风况和基准控制下的可利用功率估计 |
| `previous_farm_power_w` | W | 计算全场爬坡率 |
| `farm_power_ramp_limit_w_s` | W/s | 允许的功率变化率 |
| `headroom_fraction` | 1 | 预留降载裕度；具体数值 `[TBD]` |
| `reserve_requirement_w` | W | 当前要求保留的上调裕度 |
| `operating_mode` | enum | 正常、低风速、停机、故障等模式 |
| `is_controllable` | bool | 当前工况是否进入正常跟踪评价 |
| `episode_horizon_steps` | step | PPO 回合长度 |

v0 任务冻结为：从 `farm_available_power_w` 生成因果、限爬坡且预留裕度的 `farm_power_reference_w`，再由 PPO 跟踪该参考。参考生成器只能使用当前和历史信息，不能使用未来真实风况。

```text
P_headroom = (1 - headroom_fraction) * farm_available_power_w
P_filtered = causal_filter(P_headroom_history)
P_reference = ramp_limit(P_filtered, previous_reference, control_interval_s)
P_reference = clip(P_reference, 0, P_headroom)
```

滤波器类型、时间常数、上下行爬坡率和 `headroom_fraction` 均为 `[TBD]`，写入实验配置，不埋入代码。奖励必须同时约束参考跟踪、能量捕获/不必要弃风、动作平滑和安全边界，避免“零功率最平滑”的平凡策略。

## 6. PPO 动作与 PINN 控制输入

### 6.1 推荐动作

PPO 网络内部输出：

```text
action_normalized ∈ [-1, 1]^[B,N,A]
```

优化侧动作适配器把它变成物理命令并施加约束：

| 物理动作名称 | 单位 | Shape | 推荐程度 | 说明 |
|---|---:|---:|---|---|
| `yaw_rate_command_rad_s` | rad/s | `[B,N]` | 多机尾流控制推荐 | 偏航为慢动作，应单独设置更新周期 |
| `collective_pitch_rate_command_rad_s` | rad/s | `[B,N]` | 功率快调推荐 | 也可用带执行器模型的桨距设定值 |
| `generator_torque_command_n_m` | N·m | `[B,N]` | v0 不启用 | 保留为未来动态模型扩展 |
| `rotor_speed_reference_rad_s` | rad/s | `[B,N]` | v0 选用 | 高层参考命令；由独立 `ActuatorModel` 生成受限运行点 |

动作映射器必须输出并记录：

```text
commanded_control
applied_control
action_saturation_mask
```

PINN 接收的是 `applied_control`，不能直接接收 PPO 的归一化动作。

当前 v0 中，`ActionMapper + ActuatorModel` 均由优化组维护：前者把归一化动作转换成物理参考，后者唯一负责 yaw、pitch、rotor-speed reference 的限幅、限速、延迟、饱和和跟踪。其参数来源和适用范围必须写入配置；没有可靠依据的参数标记为工程假设并做敏感性分析。

### 6.2 两种合法控制语义

#### 速率命令

```text
yaw_rate_command_rad_s
collective_pitch_rate_command_rad_s
generator_torque_rate_command_n_m_s
```

动作在 `[t, t+dt)` 内零阶保持，PINN/执行器模型推进到下一状态。

#### 绝对设定值

```text
nacelle_heading_setpoint_rad
collective_pitch_setpoint_rad
generator_torque_setpoint_n_m
```

使用绝对设定值时，必须明确由谁负责限速、延迟和一阶/高阶执行器动态。

不得同时让 PINN 和优化侧各更新一次同一个执行器状态。

### 6.3 多时间尺度

偏航、桨距和转速参考不能默认同频、瞬时执行。接口需要共同冻结：

```text
model_dt_s
control_interval_s
yaw_update_period_s
action_hold_steps
```

v0 是准静态模型，因此 `model_dt_s = not_applicable`，不能把“每隔若干秒查询一次稳态模型”称为模型动态步长。环境时间满足：

```text
control_interval_s = k_control * actuator_internal_dt_s
yaw_update_period_s = k_yaw * control_interval_s
```

其中 `k_control`、`k_yaw` 为正整数。数值按以下顺序确定：仿真/外部风况时间序列的可用采样间隔 → yaw/pitch/speed-reference 的响应时间和速率边界 → 候选控制周期下的零阶保持误差与控制效果 → PPO 推理成本。当前解析原型的 `dt=1 s` 只作为候选，不作为正式依据。若没有任何带时间戳的风况/参考序列，就只能做稳态优化，不能定义有物理意义的功率波动回合。

## 7. PINN 单步输出字段

### 7.1 v0 准静态输出语义

当前 FLORIS/PINN 核心输出的是给定运行点下的稳态机组功率模型值，不包含时间积分。项目最终目标口径为电有功功率，但在仿真组补齐生成脚本、风机配置和效率/损耗说明前，v0 原始字段使用：

```text
floris_turbine_power_w       [B,N]
floris_farm_power_sum_w      [B,1]
power_semantics = steady_state_model_output
```

FLORIS v4 的公开规范要求功率曲线表示包含损耗的风机电功率，但当前仓库尚不能证明这批 CSV 使用的具体功率配置和测量边界。确认后再把原始字段映射为 `turbine_active_power_w`；不能直接称为并网点净有功功率。

v0 环境将该稳态功率在一个控制区间内零阶保持，因此：

```text
interval_mean_farm_active_power_w = held_steady_farm_power_w
interval_energy_j = interval_mean_farm_active_power_w * control_interval_s
```

这只是一项准静态环境约定，不代表 PINN 学到了区间内瞬态或平均过程。

### 7.2 未来动态模型输出字段

| 字段名 | 单位 | Shape | 要求 | 说明 |
|---|---:|---:|---|---|
| `next_active_power_w` | W | `[B,N]` | 必选 | `t+dt` 各机电有功功率 |
| `farm_active_power_w` | W | `[B,1]` | 必选 | 应与有效风机功率求和一致 |
| `interval_mean_farm_active_power_w` | W | `[B,1]` | 动态模型推荐 | 奖励优先使用区间平均电有功功率 |
| `interval_energy_j` | J | `[B,1]` | 推荐 | 检查功率积分和能量捕获 |
| `next_rotor_speed_rad_s` | rad/s | `[B,N]` | 动态模型必选 | 下一时刻实际转速 |
| `next_collective_pitch_rad` | rad | `[B,N]` | 动态模型必选 | 下一时刻实际桨距 |
| `next_nacelle_heading_rad` | rad | `[B,N]` | 偏航动态时必选 | 下一时刻机舱朝向 |
| `next_yaw_misalignment_rad` | rad | `[B,N]` | 推荐 | 下一时刻偏航误差 |
| `next_effective_wind_speed_m_s` | m/s | `[B,N]` | 推荐 | 下一时刻盘面等效风 |
| `next_generator_torque_n_m` | N·m | `[B,N]` | 转矩动态时必选 | 下一时刻实际转矩 |
| `rotor_thrust_n` | N | `[B,N]` | 推荐 | 载荷/安全约束 |
| `tower_base_moment_n_m` | N·m | `[B,N]` | 可选 | 疲劳代理 |
| `flow_state_next` | model-defined | `[B,N,K]` 或 `[B,K]` | 条件必选 | 下一时刻显式隐状态 |
| `prediction_std` | 对应物理单位 | 与预测量一致 | 推荐 | 不确定度 |
| `in_domain` | bool | `[B,N]` 或 `[B,1]` | 必选 | 是否处于训练有效域 |
| `ood_score` | 1 | `[B,N]` 或 `[B,1]` | 推荐 | 距离/置信度 |
| `violation_code` | int/string | `[B,N]` | 推荐 | 失败或越界原因 |

输出不得静默产生 NaN、Inf、负电功率或超额定功率。若某些物理情形确实允许负功率，必须另行定义状态和含义，不能沿用正常发电状态的功率边界。

顶层 `plant_model` 必须返回完整、结构化的风机级状态。v0 中的实际 yaw、pitch 和 rotor-speed operating point 来自 `ActuatorModel`，PINN 只允许原样透传；稳态功率、有效风速和可交付载荷量来自 PINN/代理模型，最后由 `StateAssembler` 合并。

如果 PINN 核心只输出完整流场，PINN 组还必须把固定、可测试的 `observation_operator` 与模型同包交付，将流场转换为上述风机级功率、盘面有效风和载荷量。仿真组负责物理校验，优化组不自行猜测积分方式，也不把 `observation_operator` 与 PPO 的 `ObservationBuilder` 混为一谈。

## 8. 时序和 API

### 8.1 v0 准静态查询接口

```python
steady_output = plant_model.predict_steady(
    disturbance=disturbance_t,
    applied_operating_point=applied_control_t,
)
```

顶层环境的一个伪时间步按以下顺序执行：PPO 产生参考命令 → `ActuatorModel` 推进实际运行点 → 查询准静态 PINN → `StateAssembler` 拼装完整状态 → 计算区间平均功率、奖励和下一观测。PINN 查询本身没有 `dt` 动力学；时间只存在于环境、执行器和外部风况/参考序列。

### 8.2 未来动态单步接口

```python
transition = plant_model.step(
    state_t=state_t,
    disturbance_t=disturbance_t,
    applied_control_t=applied_control_t,
    dt_s=dt_s,
)
```

唯一时序语义：

```text
state_t 在时刻 t 观测；
applied_control_t 在 [t, t+dt_s) 内保持；
输出对应 t+dt_s；
奖励使用区间平均输出或明确指定的末端输出。
```

### 8.3 重置和批量接口

```python
initial_state = plant_model.reset(
    scenario=initial_condition,
    batch_size=B,
    seed=42,
)

transition = plant_model.batch_step(...)
```

建议提供：

```python
trajectory = plant_model.rollout(
    initial_state=initial_state,          # [B,N,S]
    control_sequence=control_sequence,    # [B,H,N,A]
    disturbance_sequence=disturbance_seq, # [B,H,...]
    dt_sequence_s=dt_sequence_s,          # [B,H,1]
)
```

PINN/PPO 耦合要求：

- 模型加载一次后可重复调用，`step()` 内不得读文件或重新加载权重；
- 必须支持批量推理；
- 相同输入与 seed 的结果可复现；
- CPU 必须可运行，GPU 可选；
- PINN 不必为 PPO 保留梯度，但不得强迫调用端逐样本循环；
- 随机性、隐状态和 reset 规则必须显式；
- `reset_mask` 必须支持并行环境中单个 episode 的独立重置；
- 推理吞吐量需要在指定硬件、batch 和版本上实测报告。

## 9. 两阶段交接方案

### 9.1 v0.3 准静态控制环境

当前已冻结为：

```text
wind condition + fixed layout
        + applied yaw/pitch/rotor-speed operating point
        ↓
quasi-static PINN / surrogate
        ↓
steady turbine power + effective wind + other available states
        ↓
StateAssembler merges ActuatorModel states
        ↓
complete structured turbine state
```

v0 数据可以是独立稳态控制扫描，不要求伪造 `state_t → state_t+1`。但是 yaw、pitch、rotor-speed operating point 必须在仿真中真实变化，并通过单变量与联合控制敏感性检查；始终保持默认值的字段不得进入 PPO 动作空间。

它可以用于：

- 接口联调和批量推理；
- 稳态控制参数扫描；
- 带独立 `ActuatorModel` 的准静态参考跟踪环境；
- PPO/MADDPG 算法预研和消融实验。

它不能用于：

- 声称 PINN 学到了真实瞬态功率波动；
- 研究真实转子惯性、尾流传播时间或动态相位；
- 替代未来 `dynamic_transition` 模型的高保真闭环验证。

### 9.2 v1.0 动态正式闭环

正式 PPO 功率波动控制需要：

```text
(state_t, disturbance_t, applied_control_t, dt)
→ (state_t+1, interval_power, loads, flow_state_next)
```

仿真数据必须保留：

```text
scenario_id
episode_id
time_s
step_index
state_t
commanded_control_t
applied_control_t
state_t+1
```

训练/验证/测试必须按完整场景或轨迹划分，不能随机拆分相邻时间行。

## 10. PPO 观测、奖励和内部超参数

### 10.1 建议 PPO 观测

PINN 输出结构化物理量，优化侧再构建固定观测：

```text
power_tracking_error_pu
farm_power_ramp_pu_s
ambient_wind_speed_pu
wind_direction_sin
wind_direction_cos
turbulence_intensity
turbine_power_pu[N]
rotor_speed_pu[N]
collective_pitch_pu[N]
yaw_misalignment_pu[N]
previous_action_normalized[N,A]
prediction_uncertainty_pu[N,U]  # 可选
```

### 10.2 建议奖励

```text
reward =
    - reward_tracking_weight
      * normalized_tracking_error^2
    - reward_ramp_weight
      * ramp_limit_violation^2
    - reward_action_rate_weight
      * normalized_action_change^2
    - reward_load_weight
      * normalized_load_penalty
    - reward_constraint_weight
      * hard_constraint_violation
    - reward_ood_weight
      * ood_penalty
    + reward_energy_weight
      * normalized_energy_capture
```

动作变化量必须先除以各自幅值/速率上限再惩罚。超速、超载和执行器硬边界由环境强制，不只依靠奖励。
当前 v0 配置把 `reward_energy_weight` 设为 `0`。非零功率参考本身已经排除
“零功率最优”；线性能量奖励若与平方跟踪项同时启用，会把数学最优点推到参考值之上，
只能在明确接受该偏置并完成权重消融后开启。


### 10.3 PPO 内部配置

下表属于优化组内部配置，不要求 PINN 组提供；接入正式模型后需要重新调参。

| 参数名 | 当前原型值 | 含义 |
|---|---:|---|
| `seed` | `42` | 随机种子 |
| `total_timesteps` | `196608` | T1 回归默认总环境步；接入正式 Plant 后重定 |
| `num_envs` | `4` | 并行环境数 |
| `rollout_steps`（当前代码 `num_steps`） | `2048` | 每次更新的单环境 rollout 长度 |
| `num_minibatches` | `32` | 每轮 minibatch 数 |
| `update_epochs` | `10` | 每批数据更新轮数 |
| `learning_rate` | `3e-4` | 学习率 |
| `discount_factor`（`gamma`） | `0.99` | 折扣因子 |
| `gae_lambda` | `0.95` | GAE 参数 |
| `clip_coefficient`（`clip_coef`） | `0.2` | PPO 裁剪系数 |
| `entropy_coefficient`（`ent_coef`） | `0.0` | 熵奖励权重 |
| `value_loss_coefficient`（`vf_coef`） | `0.5` | 价值损失权重 |
| `max_gradient_norm` | `0.5` | 梯度裁剪 |
| `anneal_learning_rate` | `true` | 学习率线性衰减 |

这些超参数不属于跨组接口；跨组只冻结物理状态、动作、时序、约束、输出和归一化协议。

## 11. PINN 交付包

建议每次交付使用：

```text
pinn_package_vX.Y.Z/
├── README.md
├── interface_schema.json
├── metadata.json
├── normalization.json
├── model_card.md
├── layout.json
├── observation_operator.py       # PINN 核心只输出流场时必选
├── model.ts / model.onnx
├── model_native.pth              # 可选，不能只给裸 state_dict
├── infer.py
├── example_input.npz
├── example_output.npz
├── interface_test.py
├── metrics.csv
├── validation_report.md
├── requirements.txt
└── checksums.sha256
```

要求：

- `infer.py` 在新进程中能直接完成加载、单步和批量推理；
- 不能只交 `.pth` 而不交网络定义和推理代码；
- 禁止硬编码本机绝对路径；
- `normalization.json` 明确字段顺序、均值、标准差、上下界和数据版本；
- 示例覆盖 `B=1,N=1` 和正式风场规模；
- 修改字段、单位、shape、顺序或归一化属于破坏性接口变更；
- 模型、代码、仿真数据、接口和验证报告可以通过版本号与 checksum 追溯。

## 12. 验收要求

### 12.1 接口验收

- schema、字段、dtype、shape、单位全部一致；
- v0 的 `model_dt_s` 为 N/A，稳态功率零阶保持与区间能量计算一致；
- 每个实际状态字段只更新一次，`reset()` 后无上一回合执行器状态残留；
- 固定布局、`turbine_ids` 顺序或 layout checksum 不匹配时拒绝加载；
- 风向/偏航通过第 2.2 节黄金测试；
- `B=1` 和批量调用均能运行；
- 批量结果与逐样本结果在容差内一致；
- 相同输入和 seed 可复现；
- `reset()` 能独立清理每个并行 episode；
- 无 NaN/Inf 和未说明的静默裁剪；
- `farm_active_power_w` 与有效风机功率求和一致；
- OOD 输入必须返回 `in_domain=false` 或明确 `ood_score`；
- 每个控制变量扫描后，模型输出必须对动作有合理敏感性。

### 12.2 精度与动力学验收

v0 `quasi_static` 必须报告稳态功率误差、分工况误差、控制敏感性、边界行为和批量性能；下列 `one_step`、相位和多步 rollout 指标只对未来 `dynamic_transition` 模型强制，不能拿准静态模型的重复查询冒充动态验收。

动态模型必须报告：

```text
one_step_mae
one_step_rmse
multi_step_rmse
p95_absolute_error
maximum_absolute_error
power_phase_lag_error_s
control_response_error
long_rollout_stability
```

并按风速、风向、湍流强度、控制量和边界工况分箱。数值门槛暂记 `[TBD]`，应依据仿真数值误差、基线模型和控制需求共同冻结，不能在没有数据时随意指定。

必须包含：

- 零动作稳态测试；
- yaw/pitch/torque 单变量扫描；
- 联合动作和边界动作；
- 阶跃与斜坡响应；
- 连续长时 rollout；
- 超域输入；
- 独立完整场景测试。

只验证 PDE 残差不够，必须验证功率误差、动态相位/延迟和控制敏感性。

### 12.3 性能验收

- 报告指定 CPU/GPU、batch size、软件版本下的 transitions/s；
- `step()` 内不得加载模型或读写磁盘；
- 正式 PPO 训练通常需要十万到百万级环境步，若 PINN 过慢，应交付轻量代理或蒸馏模型。

## 13. 组会问题决策状态

| 原问题编号 | 议题 | 当前决策 | 状态 |
|---:|---|---|---|
| 13 | PINN 第一版模型类型 | v0 采用 `quasi_static`；动态版未来另立版本 | 已冻结 |
| 14 | 控制输入 | v0 预留 yaw、pitch、rotor-speed reference；torque 不启用 | 范围已冻结，字段启用待仿真敏感性确认 |
| 15 | “调转速”语义 | PPO 输出高层转速参考，实际运行点由 `ActuatorModel` 生成 | 已冻结 |
| 16 | 执行器动态 | 独立 `ActuatorModel` 由优化组实现，参数需有仿真/资料依据 | 责任已冻结，数值 `[TBD]` |
| 17 | 时间尺度 | v0 `model_dt_s = N/A`；控制周期和 yaw 周期按第 6.3 节确定 | 方法已冻结，数值 `[TBD]` |
| 18 | 功率口径 | 最终目标为电有功；当前 FLORIS 数据先按稳态机组功率模型输出命名；环境零阶保持后形成区间平均 | 目标已冻结，原始数据测量边界待仿真组确认 |
| 19 | 参考功率 | 因果、限爬坡、预留 headroom 的可利用功率平滑参考 | 方法已冻结，参数 `[TBD]` |
| 20 | headroom 与零功率陷阱 | 主要依靠可达的非零参考和 `headroom_fraction`；线性能量奖励默认关闭 | 原则已冻结，比例 `[TBD]` |
| 21 | 风向和偏航 | 按第 2.2 节：气象来向、北为 0、顺时针、rad、误差 wrap | 已冻结，需黄金测试 |
| 22 | 风场组织 | 第一版固定风机数、布局和 `turbine_ids` 顺序 | 结构已冻结，具体 ID/checksum 待交付 |
| 23 | PINN/plant 输出 | 顶层接口输出完整结构化风机状态；裸流场不是 PPO 正式接口 | 已冻结 |
| 24 | 状态更新责任 | 使用第 1.1 节单一权威更新者表，禁止重复推进 | 已冻结 |
| 25 | 有效域、OOD、不确定度 | 仍按第 7/12 节建议讨论 | 待后续组会确认 |
| 26 | 数据轨迹 | v0 接受含控制扫描的独立稳态样本；动态版才要求连续状态转移轨迹 | v0 已冻结，动态版待规划 |
| 27 | 验收门槛 | 先冻结指标和测试方法，代表性数据/基线到位后再冻结数值 | 待三方确认冻结日期 |

“已冻结”表示 v0 接口按此实施；“数值 `[TBD]`”表示不得在代码中静默写死默认值。

## 14. 最小可落地交接

v0 最小接口冻结如下：

```text
输入：
    ambient_wind_speed_m_s                 [B,1]
    ambient_wind_direction_rad             [B,1]
    turbulence_intensity                   [B,1]
    applied_yaw_misalignment_rad           [B,N]
    applied_collective_pitch_rad           [B,N]
    applied_rotor_speed_operating_point_rad_s [B,N]

PINN/代理模型原始输出：
    floris_turbine_power_w                 [B,N]
    floris_farm_power_sum_w                [B,1]
    effective_wind_speed_m_s               [B,N]
    other_available_turbine_states         [B,N,*]
    in_domain                              [B,1]

顶层 plant_model 输出：
    complete_turbine_state                 structured [B,N,*]
    interval_mean_farm_active_power_w      [B,1]
    action_saturation_mask                 [B,N,A]
```

`complete_turbine_state` 中的 yaw、pitch 和 rotor-speed operating point 来自 `ActuatorModel`，PINN 只透传；功率和有效风来自准静态模型。功率来源口径确认后，再把 `floris_*` 字段稳定映射到正式 `*_active_power_w` 字段。

该最小版必须标注为 `quasi_static`。它可验证接口、控制敏感性、批量推理和准静态控制逻辑，但不能替代正式动态闭环。

动态数据到位后升级为：

```text
(state_t, disturbance_t, applied_control_t, dt_s)
→ (state_t+1, interval_mean_power, loads, flow_state_next)
```

## 15. 参考依据

- [NREL 5-MW 基准风机规范](https://www.nrel.gov/docs/fy09osti/38060.pdf)：基准控制主要由发电机转矩控制和集体变桨控制组成。
- [OpenFAST ServoDyn Extended Bladed Interface](https://openfast.readthedocs.io/en/v4.0.5/source/user/servodyn/ExtendedBladedInterface.html)：区分实测转速、转矩、桨距、偏航误差与对应命令。
- [FLORIS v3 → v4 接口说明](https://github.com/NatLabRockies/floris/blob/main/docs/v3_to_v4.md)：风况与 yaw 控制量的批量 shape 为风况数 × 风机数；FLORIS v4 的功率曲线应表示包含损耗的风机电功率。当前项目仍需用原始生成脚本和 turbine 配置确认本批 CSV 的具体测量边界。
