# 优化侧准静态可替换闭环使用指南

> 版本：v0.1（2026-08-23）
>
> 对应任务：T2.5 优化核心组件、T4a 准静态软件闭环、T1-R 历史基线修复
>
> 入口配置：[ppo_single_turbine/configs/quasi_static_v0.yaml](ppo_single_turbine/configs/quasi_static_v0.yaml)
>
> 跨组物理语义以 [PINN_OPTIMIZATION_INTERFACE.md](PINN_OPTIMIZATION_INTERFACE.md) 为准；本文说明已经落地的优化侧代码怎样使用。

## 1. 这套闭环解决什么

当前仿真组还没有交付含控制参数的数据，PINN 组也没有可供强化学习调用的真实代理模型。优化组仍然可以先完成与具体 PINN 无关的部分：

- 把 PPO 的无量纲动作转换为具名物理参考值；
- 模拟 yaw、pitch、转速参考的限幅、限速、延迟、一阶跟踪和不同更新周期；
- 从独立的可利用功率估计生成因果、预留裕度且限爬坡的参考功率；
- 组装完整状态、构造 PPO 观测、分项计算奖励；
- 固定 PINN 替换接口、shape、单位、风机顺序和 OOD 诊断；
- 在 Mock 模型上验证软件链路、重置规则、异常检查和可复现性。

这套代码的直接用途是让未来接入真实准静态 PINN 时，只替换 Plant，而不重写 PPO 环境。

## 2. 它不能证明什么

默认的 `MockQuasiStaticPlant`、合成风况和配置数值都只用于软件联调，不能用于证明：

- PPO 在真实风机或真实风场上的控制性能；
- PINN 已经学到转子惯性、尾流传播、功率相位或其他动态过程；
- 当前 `control_interval_s=1.0`、headroom、执行器速率和时间常数是正式工程参数；
- PPO 优于工业 PID、MPC、静态优化或其他传统方法；
- 当前输出已经是并网点净电有功功率。

任何基于 Mock 的 RMSE、奖励或发电量只能写成“软件集成测试结果”，不能进入物理效果结论。

## 3. 什么是 quasi-static 伪时间

### 3.1 准静态 Plant 没有时间记忆

当前 Plant 接口是：

```text
当前风况 + 当前已施加运行点
    → 该运行点下的稳态功率、有效风速和有效域信息
```

`PlantModel.predict_steady()` 不接收上一状态和 `dt`，也不保存隐藏动力学。因此，连续查询准静态模型不等于动态 PINN。

### 3.2 时间存在于 Plant 外部

一个环境步中的“时间变化”来自：

1. `DisturbanceProvider` 提供下一时刻风况；
2. `ActuatorModel` 按控制周期推进实际 yaw、pitch 和转速运行点；
3. `ReferencePowerGenerator` 更新滤波和爬坡记忆；
4. 环境更新上一动作、上一功率和 episode 步数；
5. 准静态 Plant 只回答新风况和新运行点对应的稳态结果。

因此，当前环境是“带外部时序约束的准静态伪时间闭环”，不是 `dynamic_transition` 模型。

### 3.3 功率和能量的时间语义

准静态功率在一个控制区间内按零阶保持解释：

```text
interval_mean_farm_active_power_w = held_steady_farm_power_w
interval_energy_j = interval_mean_farm_active_power_w × control_interval_s
```

这是环境约定，不是 PINN 学到的区间瞬态平均。v0 的 `model_dt_s = null / not_applicable`；`control_interval_s` 属于环境和执行器配置。

### 3.4 动作、风况和参考的一步对齐

在状态 `observation_t` 上选出 `action_t` 后，环境先推进执行器和步号，再读取
`disturbance_t+1`，随后计算 `power_t+1`、因果 `reference_t+1` 和本步奖励。
因此当前任务是“对未知下一步风况的鲁棒/期望跟踪”，不是让策略提前知道下一步调度指令。

如果未来接入已知的调度计划，必须把可用的未来参考窗口作为独立输入，在动作产生前放入
观测，并在接口文档中冻结预测窗口和时间戳；不能只把现有参考生成器向前平移，否则会产生
信息泄漏或一拍错位。


## 4. 闭环架构

```text
PPO normalized action [-1, 1]
        │
        ▼
ActionMapper
  无量纲动作 → yaw/pitch/rotor-speed 绝对参考值
        │ commanded_control
        ▼
ActuatorModel
  延迟、多速率保持、一阶跟踪、位置/速率边界
        │ applied_control
        ├──────────────────────────────┐
        ▼                              │
PlantModel.predict_steady()            │
  Mock 或未来 PINN Adapter             │
        │ steady output                │
        ▼                              │
StateAssembler ◄───────────────────────┘
  合并控制状态与 Plant 输出，权威计算全场功率/区间能量
        │
        ├── ObservationBuilder → PPO 下一观测
        └── RewardCalculator    → 分项奖励

独立支路：
基准控制反事实 Plant 查询 → farm_available_power_w
    → ReferencePowerGenerator → farm_power_reference_w
```

每个环境步会查询 Plant 两次：

- 一次使用当前实际控制，得到受控功率；
- 一次使用固定基准控制，估计可利用功率。

第二次查询与当前受控动作解耦，避免出现“主动降功率 → 可利用功率估计下降 → 参考继续下降 → 收缩到零”的反馈。

## 5. 单一权威更新者

| 字段或过程 | 唯一写入者 | 其他组件的职责 |
|---|---|---|
| PPO 无量纲动作 | PPO 策略 | 环境只读取 |
| yaw/pitch/转速物理参考 | `ActionMapper` | PPO 不直接写物理状态 |
| 实际 yaw/pitch/转速运行点 | `ActuatorModel` | Plant 只读取，不再次推进 |
| 稳态逐机功率、有效风速、OOD | `PlantModel` 实现 | StateAssembler 校验并透传 |
| 全场功率、区间平均功率、区间能量 | `StateAssembler` | Plant 提供逐机功率及一致的原始和 |
| 可利用功率 | 固定基准控制下的反事实 Plant 查询 | 不使用当前受控功率替代 |
| 参考功率 | `ReferencePowerGenerator` | Plant 不接收控制目标 |
| PPO 观测 | `ObservationBuilder` | PINN 归一化与 PPO 归一化分离 |
| 奖励、终止和截断 | Gym 环境 | Plant 不决定优化目标 |

如果未来 PINN 内部开始推进某个执行器状态，必须先修改接口责任表并停用外部对应更新，不能两边各更新一次。

## 6. 新增文件及职责

### 6.1 Plant 与环境

| 文件 | 用途 |
|---|---|
| [environments/plant_model.py](environments/plant_model.py) | 定义 `DisturbanceBatch`、`AppliedOperatingPoint`、`SteadyPlantOutput` 和可替换 `PlantModel` 协议；集中校验 shape、dtype、风机顺序、功率求和和非有限值 |
| [environments/mock_quasi_static_plant.py](environments/mock_quasi_static_plant.py) | 平滑、确定性的联调替身；响应风速、yaw、pitch 和转速运行点，但没有经过物理标定 |
| [environments/quasi_static_wind_farm_env.py](environments/quasi_static_wind_farm_env.py) | 组合全部组件的 Gymnasium 环境；提供 YAML 加载、合成风况、可利用功率反事实查询、reset/step 和审计信息 |
| [environments/__init__.py](environments/__init__.py) | 对外导出 Plant 类型和 `load_quasi_static_env` 入口 |
| [environments/simplified_turbine_env.py](environments/simplified_turbine_env.py) | T1 历史解析单机环境；用于 PPO 工具链回归，不是新闭环的 Plant |

### 6.2 优化核心组件

| 文件 | 用途 |
|---|---|
| [utils/action_mapper.py](utils/action_mapper.py) | `[-1,1]` 与三通道物理绝对参考之间的正逆映射；返回裁剪掩码；定义 `ParameterSource` |
| [utils/actuator_model.py](utils/actuator_model.py) | 优化组拥有的执行器状态机；处理位置、速率、延迟、一阶滞后、多更新频率和 episode reset |
| [utils/reference_power.py](utils/reference_power.py) | 因果执行“可利用功率 → headroom → 一阶低通 → 上下行爬坡限制 → 可达性裁剪” |
| [utils/state_pipeline.py](utils/state_pipeline.py) | `StateAssembler` 合并状态并权威计算全场功率/能量；`ObservationBuilder` 按显式顺序和尺度构造观测 |
| [utils/reward.py](utils/reward.py) | 计算可审计的 tracking、ramp、action-rate、load、constraint、OOD 和 energy 分项 |
| [utils/__init__.py](utils/__init__.py) | 对外导出优化核心组件 |

### 6.3 配置与测试

| 文件 | 用途 |
|---|---|
| [ppo_single_turbine/configs/quasi_static_v0.yaml](ppo_single_turbine/configs/quasi_static_v0.yaml) | 当前单机软件联调配置；每个参数值带来源 |
| [tests/test_plant_contract.py](tests/test_plant_contract.py) | Plant shape、批量/逐样本等价、ID 顺序和异常输入契约 |
| [tests/test_action_mapper.py](tests/test_action_mapper.py) | 动作正逆映射、保持动作、裁剪和来源校验 |
| [tests/test_actuator_model.py](tests/test_actuator_model.py) | 延迟、限速、一阶跟踪、多速率保持和 reset 隔离 |
| [tests/test_reference_power.py](tests/test_reference_power.py) | 因果滤波、headroom、上下爬坡和可达性 |
| [tests/test_state_reward.py](tests/test_state_reward.py) | 状态所有权、观测顺序、功率求和和奖励分项 |
| [tests/test_quasi_static_env.py](tests/test_quasi_static_env.py) | Gym 契约、固定 seed、长时 rollout、风况替换、可利用功率语义和 Plant 热替换 |
| [ppo_single_turbine/test_baseline.py](ppo_single_turbine/test_baseline.py) | T1-R 的 episode 日志、P 控制方向、动作尺度和评估生命周期回归 |

## 7. Plant 接口和 shape

### 7.1 输入

`DisturbanceBatch`：

| 字段 | Shape | 单位 |
|---|---:|---:|
| `ambient_wind_speed_m_s` | `[B,1]` | m/s |
| `ambient_wind_direction_rad` | `[B,1]` | rad |
| `turbulence_intensity` | `[B,1]` | 0–1 |

`AppliedOperatingPoint`：

| 字段 | Shape | 单位 |
|---|---:|---:|
| `turbine_ids` | 长度 `N` 的有序 tuple | — |
| `applied_yaw_misalignment_rad` | `[B,N]` | rad |
| `applied_collective_pitch_rad` | `[B,N]` | rad |
| `applied_rotor_speed_operating_point_rad_s` | `[B,N]` | rad/s |

### 7.2 输出

`SteadyPlantOutput`：

| 字段 | Shape | 要求 |
|---|---:|---|
| `floris_turbine_power_w` | `[B,N]` | 非负；当前保留来源语义名称 |
| `floris_farm_power_sum_w` | `[B,1]` | 必须等于有序逐机功率之和 |
| `effective_wind_speed_m_s` | `[B,N]` | 逐机有效来流 |
| `in_domain` | `[B,1]` bool | 当前输入是否处于有效域 |
| `ood_score` | `[B,1]` | 非负 OOD 诊断 |
| `other_available_turbine_states` | 每项 `[B,N]` | 可选的载荷或其他已交付状态 |
| `model_kind` | string | 必须区分 Mock、准静态 PINN 等 |

所有跨 Plant 浮点数组使用 `float32`。固定布局下 `turbine_ids` 的内容和顺序必须完全一致，不能只保证集合相同。

### 7.3 Python 协议

```python
class PlantModel(Protocol):
    @property
    def turbine_ids(self) -> tuple[str, ...]: ...

    @property
    def rated_power_w(self) -> np.ndarray: ...  # [N]

    def predict_steady(
        self,
        disturbance: DisturbanceBatch,
        applied_operating_point: AppliedOperatingPoint,
    ) -> SteadyPlantOutput: ...
```

代码中的 `PlantModel` 是窄的“稳态预测器”接口。跨组文档所说的“顶层 plant 输出完整状态”，由 `PlantModel + ActuatorModel + StateAssembler + QuasiStaticWindFarmEnv` 共同实现；不能把窄协议返回的原始稳态结果误写成完整控制状态。

## 8. 动作、观测和保持动作

### 8.1 动作

当前软件壳采用 `absolute_reference`，每台风机三个固定顺序通道：

```text
yaw_misalignment_reference_rad
collective_pitch_reference_rad
rotor_speed_reference_rad_s
```

Gym 动作是展平后的 `[N×3]` float32 数组，范围 `[-1,1]`。`ActionMapper` 将其恢复为 `[N,3]` 并映射到配置中的物理上下界。

关键陷阱：绝对参考模式下，数值 `action=0` 表示每个物理范围的中点，不是“不动作”。

请求保持当前已施加运行点的动作是：

```python
hold_action = env.hold_action_normalized.copy()
# 或从 reset/step 的 info 中读取：
hold_action = info["hold_action_normalized"].copy()
```

执行器推进后保持动作也会变化，因此需要使用最新值，不能在整个 episode 固定保存 reset 时的数组。
若某通道配置了非零命令延迟，已经进入延迟队列的旧命令不会被该动作撤销；需要在 reset 后等待
队列清空，或由未来执行器接口显式实现“取消待执行命令”。

### 8.2 默认观测顺序

YAML 加载器当前按以下顺序拼接并归一化：

1. 全场功率跟踪误差；
2. 全场区间平均有功功率；
3. 环境风速、风向、湍流强度；
4. 各机稳态功率；
5. 各机实际转速运行点；
6. 各机实际集体桨距；
7. 各机实际偏航误差；
8. 上一步归一化动作。

观测是展平 float32 数组。当前单机配置的 shape 由加载后的 `env.observation_space.shape` 给出；布局或特征改变后不得继续假定旧维数，旧 PPO 权重也必须重新训练。

## 9. YAML 参数来源：为什么必须写 source

配置中的物理或实验参数统一使用：

```yaml
control_interval_s:
  value: 1.0
  source: assumed
  note: "Candidate used for integration tests; not a frozen physical control period."
```

`source: assumed` 表示“为了让软件闭环可运行而暂定”，不是“已经冻结”。当前配置中的控制周期、执行器边界/速率/时间常数、合成风况、Mock 参数、headroom、爬坡限制和奖励权重均不能自动升级为工程事实。

常用来源含义：

| source | 含义 |
|---|---|
| `assumed` | 临时软件联调假设；必须做敏感性分析并等待替换 |
| `project_interface_decision` | 已冻结的接口结构或语义，例如 `quasi_static` 和 `model_dt_s=null` |
| `project_convention` | 项目工程约定，例如 `seed=42` |
| 仿真/资料的具体标识 | 正式值到位后应指向可追溯配置、文档版本或数据版本 |

规则：

- 每个包含 `value` 的节点必须同时包含 `source`；
- 正式值到位时先更新接口/配置说明，再更新 YAML；
- 不在 Python 中静默增加“看起来合理”的物理默认值；
- 替换假设后运行全部契约测试和参数敏感性验证；
- 报告中必须区分 `assumed`、已冻结结构和有证据的物理数值。

## 10. 快速开始

以下命令均从项目根目录执行。

### 10.1 加载默认 Mock 环境

```python
import numpy as np

from optimization_control.environments import load_quasi_static_env

config_path = (
    "optimization_control/ppo_single_turbine/configs/quasi_static_v0.yaml"
)
env = load_quasi_static_env(config_path)

observation, info = env.reset(seed=42)
print(observation.shape)
print(info["model_kind"])
print(info["farm_power_w"], info["farm_power_reference_w"])

for _ in range(32):
    action = env.hold_action_normalized.copy()
    observation, reward, terminated, truncated, info = env.step(action)
    assert np.isfinite(reward)
    if terminated or truncated:
        observation, info = env.reset(seed=42)

env.close()
```

此入口默认创建 `MockQuasiStaticPlant` 和 `SyntheticDisturbanceProvider`。二者都只用于联调。

### 10.2 命令行 smoke test

```powershell
& .\.venv\Scripts\python.exe -c "import numpy as np; from optimization_control.environments import load_quasi_static_env; e=load_quasi_static_env('optimization_control/ppo_single_turbine/configs/quasi_static_v0.yaml'); o,i=e.reset(seed=42); o,r,t,tr,i=e.step(e.hold_action_normalized.copy()); print(o.shape, r, i['model_kind']); e.close()"
```

## 11. 测试

优化闭环测试只使用 Python 标准库 `unittest` 和项目已有依赖，不需要安装 `pytest`。

运行 Plant、核心组件和新环境的完整测试：

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s optimization_control\tests -p 'test_*.py' -v
```

运行 T1-R 历史基线回归：

```powershell
& .\.venv\Scripts\python.exe optimization_control\ppo_single_turbine\test_baseline.py
```

测试覆盖：

- Gymnasium `check_env`；
- batch 与逐样本预测等价；
- 固定 seed 的观测、奖励和标志可复现；
- 长时随机 rollout 无 NaN/Inf；
- episode reset 后无执行器或参考记忆泄漏；
- `turbine_ids` 重排、错误 shape 和非有限值会拒绝；
- 替换 Plant 和替换风况源不需要改环境代码；
- 可利用功率不随当前降载动作自收缩。

代码修改后必须运行相关测试；正式 PINN 接入时还必须运行 PINN 交付包自己的接口和精度测试。

## 12. T1-R 历史 PPO 基线

2026-08-24 收尾验证结果：优化框架 36 项测试、T1 7 项回归测试全部通过。


T1-R 修复的是旧解析单机 PPO 的工程可信度，不等于已经训练了新准静态 Plant 策略。

### 12.1 回归测试

```powershell
& .\.venv\Scripts\python.exe optimization_control\ppo_single_turbine\test_baseline.py
```

### 12.2 轻量训练 smoke

```powershell
& .\.venv\Scripts\python.exe optimization_control\ppo_single_turbine\train.py --total-timesteps 512 --num-envs 2 --num-steps 256 --num-minibatches 4 --update-epochs 1 --no-save-model --run-tag smoke_tanh_policy
```

它只验证训练循环和 `episodic_return` 日志能工作，不生成正式模型结论。

### 12.3 按完整 episode 评估历史模型

```powershell
& .\.venv\Scripts\python.exe optimization_control\ppo_single_turbine\eval.py --model models\ppo\ppo_tracking_v3_seed42.pt --policy-format legacy_unsquashed --episodes 1
```

旧结果同时存在跨越 episode 边界、P 控制方向错误、未压缩高斯动作与环境裁剪后的实际动作不一致三项问题。显式旧格式回归得到 PPO RMSE 49.83 kW、PController RMSE 35.99 kW；它仍是单一确定性场景，只用于证明旧模型在修正协议下不优于基准。正式比较必须用当前 tanh 有界策略重新训练并进行多种子评估。

## 13. 用真实 PINN 替换 Mock

### 13.1 编写窄适配器

真实 PINN 不应直接耦合 Gym 环境。先写一个实现 `PlantModel` 的适配器：

```python
import numpy as np

from optimization_control.environments import (
    AppliedOperatingPoint,
    DisturbanceBatch,
    SteadyPlantOutput,
)


class PinnQuasiStaticPlant:
    def __init__(self, model_package):
        self._model = model_package.load_once()
        self._turbine_ids = tuple(model_package.turbine_ids)
        self._rated_power_w = np.asarray(
            model_package.rated_power_w, dtype=np.float32
        )

    @property
    def turbine_ids(self):
        return self._turbine_ids

    @property
    def rated_power_w(self):
        return self._rated_power_w.copy()

    def predict_steady(self, disturbance, applied_operating_point):
        # 1. 在适配器内部完成 PINN 自身的字段排序、归一化和单位转换。
        # 2. 一次完成整个 batch 推理；不要在这里重复加载权重或逐样本读文件。
        prediction = self._model.predict(
            wind_speed=disturbance.ambient_wind_speed_m_s,
            wind_direction=disturbance.ambient_wind_direction_rad,
            turbulence=disturbance.turbulence_intensity,
            yaw=applied_operating_point.applied_yaw_misalignment_rad,
            pitch=applied_operating_point.applied_collective_pitch_rad,
            rotor_speed=(
                applied_operating_point
                .applied_rotor_speed_operating_point_rad_s
            ),
        )
        turbine_power = np.asarray(
            prediction.turbine_power_w, dtype=np.float32
        )
        return SteadyPlantOutput(
            turbine_ids=self.turbine_ids,
            floris_turbine_power_w=turbine_power,
            floris_farm_power_sum_w=turbine_power.sum(
                axis=1, keepdims=True, dtype=np.float32
            ),
            effective_wind_speed_m_s=np.asarray(
                prediction.effective_wind_speed_m_s, dtype=np.float32
            ),
            in_domain=np.asarray(prediction.in_domain, dtype=np.bool_),
            ood_score=np.asarray(prediction.ood_score, dtype=np.float32),
            other_available_turbine_states={},
            model_kind="pinn_quasi_static_vX.Y.Z",
        )
```

### 13.2 注入现有环境

```python
from optimization_control.environments import load_quasi_static_env

plant = PinnQuasiStaticPlant(model_package)
env = load_quasi_static_env(
    "optimization_control/ppo_single_turbine/configs/quasi_static_v0.yaml",
    plant=plant,
)
```

环境会在加载时检查：

- `turbine_ids` 与 YAML 固定顺序完全一致；
- `rated_power_w` 为有限正数且 shape 为 `[N]`；
- 输出字段 shape、dtype、功率非负和全场求和一致；
- 每步 Plant 输出不能改变风机顺序。

如果真实布局、额定功率或观测尺度与单机 Mock 不同，先复制并版本化新 YAML，再加载新配置；不要为了让模型通过而伪装成 `T01` 或沿用 5 MW 假设。

## 14. env.reset/step 的 info

顶层字段：

| 字段 | 用途 |
|---|---|
| `step_index` | 当前伪时间步 |
| `turbine_ids` | 固定有序风机 ID |
| `model_kind` | 当前 Plant 类型和版本 |
| `farm_power_w` | 当前受控运行点的稳态全场功率 |
| `farm_available_power_w` | 固定基准控制下的反事实可利用功率估计 |
| `farm_available_power_semantics` | 固定为 `baseline_control_counterfactual_estimate` |
| `hold_action_normalized` | 当前物理运行点对应的保持请求；不能撤销已排队的延迟命令 |
| `farm_power_reference_w` | 当前因果参考功率 |
| `reward_components` | 分项奖励；reset 时为空字典 |
| `constraint_flags` | 动作与执行器约束诊断 |
| `domain_flags` | 受控查询及可利用功率查询的 OOD 诊断 |
| `reference_flags` | 参考功率限爬坡/可达性诊断 |

子字段：

```text
reward_components:
    tracking, ramp, action_rate, load,
    constraint, ood, energy

constraint_flags:
    normalized_action_clipped
    position_saturated
    rate_saturated
    held_for_multirate_update

domain_flags:
    in_domain
    ood_score
    available_power_query_in_domain

reference_flags:
    ramp_up_limited
    ramp_down_limited
    availability_clipped
```

训练日志至少应保存总奖励、所有 `reward_components`、功率/参考/可利用功率和三组 flags。只保存总奖励会掩盖策略利用约束或 OOD 的问题。

## 15. 奖励分项怎样理解

```text
total =
    tracking
  + ramp
  + action_rate
  + load
  + constraint
  + ood
  + energy
```

| 分项 | 符号与意义 |
|---|---|
| `tracking` | 非正；归一化参考跟踪误差平方 |
| `ramp` | 非正；超过全场爬坡限制的部分 |
| `action_rate` | 非正；历史字段名，实际是相邻控制步的归一化动作变化，不是除以秒后的物理速率 |
| `load` | 非正；有载荷信号且权重大于零时启用；当前 v0 权重为 0 |
| `constraint` | 非正；动作裁剪、执行器位置/速率边界等违反 |
| `ood` | 非正；Plant 超出有效域 |
| `energy` | 非负；可选区间能量项；v0 默认权重为 0，避免把跟踪最优点推高 |

所有动作代价都在无量纲归一化空间中计算，不直接相加 `deg²` 与 `(rad/s)²`。非零奖励权重缺少对应输入或 shape 与 `[N,A]`/`[B,N,A]` 契约不符时，`RewardCalculator` 会直接报错，不会静默广播或忽略。

奖励权重仍是 `source: assumed`。在形成正式结论前需要做权重消融，并检查策略是否通过 OOD、饱和、过度降载或参考生成漏洞获取虚假高奖励。

## 16. 真实 PINN 接入清单

### 16.1 接口与元数据

- [ ] 明确模型为 `quasi_static`，`model_dt_s=null`；
- [ ] 固定 `turbine_ids`、布局版本、位置和 checksum；
- [ ] 确认各机额定功率、功率测量边界和 `floris_*` 到电有功字段的映射；
- [ ] 冻结角度单位、风向来向/去向、零点、正方向和 yaw 符号；
- [ ] 提供输入/输出字段顺序、shape、dtype 和归一化版本；
- [ ] 所有 yaw、pitch、转速输入在训练数据中真实扫描且有可验证敏感性；
- [ ] 提供有效域、`in_domain`、`ood_score` 和越界策略；
- [ ] PINN 只输出流场时，同包交付并验证 `observation_operator`。

### 16.2 适配器实现

- [ ] 模型在适配器构造时加载一次，`predict_steady()` 内不读磁盘；
- [ ] 支持 `B=1` 和批量推理；
- [ ] 保持固定风机顺序，输出 `float32`；
- [ ] 适配器内部完成 PINN 归一化、反归一化、单位和方向转换；
- [ ] 不在 PINN 与 `ActuatorModel` 中重复推进 yaw/pitch/转速；
- [ ] 每个环境步的受控查询与基准反事实查询都可运行；
- [ ] 相同输入和 seed 可复现，不保留无法 reset 的隐式 episode 状态；
- [ ] 无 NaN/Inf、未说明负功率或静默超额定裁剪。

### 16.3 配置替换与验收

- [ ] 用真实布局和模型范围创建版本化 YAML；
- [ ] 把有证据的 `source: assumed` 替换为可追溯来源；
- [ ] 冻结 `control_interval_s`、yaw 更新周期和执行器参数；
- [ ] 运行 Plant 契约、完整环境测试和 PINN 自带接口测试；
- [ ] 验证 batch 与逐样本一致、固定 seed、长 rollout 和 OOD；
- [ ] 做 yaw/pitch/转速单变量及联合扫描；
- [ ] 记录两次 Plant 查询带来的推理吞吐量；
- [ ] 与 P 控制、保持动作、受约束静态优化等公平基线比较；
- [ ] 只有高保真仿真或物理实验验证后，才形成真实控制效果结论。

## 17. 常见错误

| 错误 | 正确处理 |
|---|---|
| 在绝对参考模式下用全零动作表示保持 | 使用最新 `env.hold_action_normalized` |
| 把 PPO 无量纲动作直接传给 PINN | 先经过 `ActionMapper + ActuatorModel`，PINN 只接收实际物理运行点 |
| 用当前受控功率生成可利用功率 | 使用固定基准控制的独立反事实查询 |
| 把连续稳态查询称为动态 PINN | 明确写“准静态伪时间闭环” |
| 把 `source: assumed` 参数写入正式风机结论 | 先获得来源、更新配置并做敏感性分析 |
| 只返回总奖励 | 同时记录所有奖励分项和约束/OOD flags |
| 改了风机顺序但继续加载旧策略 | 升级布局和配置版本，重新训练策略 |
| 只替换模型文件、不交推理定义和归一化 | 按 PINN 交付包规范提供完整可执行适配器 |
| episode 结束后继续 step | 遇到 `terminated/truncated` 后 reset |
| 用 Mock 结果比较算法优劣 | Mock 只验证软件链路，不做性能结论 |
