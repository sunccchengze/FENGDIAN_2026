# 单机 PPO 功率跟踪 — 组会汇报与演示指南

> 汇报人：优化控制模块 | 日期：2026-08-09
> 本文档 = 汇报讲稿 + 现场演示流程 + 脚本/指标速查，照着讲即可
> **T1-R 复核提示（2026-08-24）**：第三、第五、第六节中的旧数值和旧图片只保留历史语境；当前可执行命令、输出名和结论边界以第八、九节为准。

---

## 一、背景：为什么做这件事

**项目目标**：电网说"我要 X MW"，风电场精准输出 X MW，同时风机之间不互相"坑"（尾流）。

**我的职责**：优化控制模块——RL 环境构建、PPO 单机控制、MADDPG 多机协同。

**团队数据流**：
```
袁夫达（FLORIS 数据）→ 厉今飞（神经网络代理模型）→ 我（RL 控制器）
```

**本次工作（T1）**：真正控制风机需要"偏航/桨距"维度的数据，目前还在等。为了不让进度卡死，
先用**解析公式（NREL 5MW 物理模型）搭建单机环境**，把"输入目标功率 → 输出控制参数 → 功率稳定跟踪"
这条 RL 完整链路跑通。这不是最终控制器，但验证了算法路线和工具链，是后续 MADDPG 的基础。

---

## 二、原理（从头到尾）

### 2.1 风机功率的物理模型

单台风机的功率由气动公式决定：

```
P = 0.5 × ρ × A × Cp(λ, β) × U³
```

| 符号 | 含义 | 值/范围 |
|------|------|---------|
| ρ | 空气密度 | 1.225 kg/m³ |
| A | 扫风面积 πR² | NREL 5MW：R=63m |
| U | 来流风速 | 8 / 9.5 m/s（本演示） |
| β | 桨距角 | 0~25°（**控制量之一**） |
| ω | 叶轮转速 | 0~1.27 rad/s（**控制量之二**） |
| λ | 叶尖速比 = ωR/U | — |
| Cp | 功率系数（经验公式） | 最优 ~0.48 |

**关键物理规律**：功率 ∝ U³（风速影响巨大）；Cp 曲线决定了"什么转速/桨距下效率最高"。

**为什么控制桨距角和转速，而不是偏航角**：
- 桨距角、转速：**秒级**调节，直接改变功率 → 适合单机快速功率跟踪
- 偏航角：**分钟级**调节，主要改变尾流方向 → 留给多机协同（MADDPG，下一步）

### 2.2 一阶转速动力学（秒级响应）

```
J × dω/dt = Ta − Tg
```

气动转矩 Ta 由风提供，发电机转矩 Tg 由控制决定。我们简化为：转速设定值（控制输出）经过
一阶惯性环节（时间常数 τ=5s）逼近——模拟真实风机的秒级动态响应。

### 2.3 强化学习公式化

把功率跟踪建模为 RL 问题：

```
状态 s  = [P, ω, β, U, P_target]          # 当前功率、转速、桨距、风速、目标功率
动作 a  = [Δβ, Δω]                        # 桨距角变化量、转速设定变化量
奖励 r  = -((P_target − P)/1MW)² − λ·mean[(Δβ/0.5°)², (Δω/0.1rad/s)²]
          ↑ 功率误差归一化                 ↑ 各动作按自身上限归一化，避免单位混合
目标    = 最大化累积奖励 Σ γᵗ r
```

**为什么奖励要两项**：只惩罚误差会导致控制器疯狂抖动（功率贴着目标来回跳，风机受不了）；
加上动作平滑惩罚，才学出"既准确又稳定"的控制。

### 2.4 PPO 算法（一句话 + 类比）

**PPO = 近端策略优化**，当前最主流的连续控制 RL 算法：

> 教练（策略）每次根据表现改进运动员（控制参数），但**每次改进步子不能太大**
> （clip 限制新旧策略差异），防止一次更新过头导致崩盘。

核心公式（Clipped Surrogate Objective）：
```
L = E[ min( r_t(θ)·A_t,  clip(r_t(θ), 1−ε, 1+ε)·A_t ) ]
```
- r_t(θ) = 新旧策略概率比
- A_t = 优势函数（GAE 估计，这个动作比平均好多少）
- ε = 0.2（更新幅度上限）

网络结构：**Actor-Critic**（64×64 Tanh MLP）——Actor 输出动作（桨距/转速变化），
Critic 评价状态好坏（学价值函数），二者共享特征。

### 2.5 训练配置

| 项目 | 值 |
|------|-----|
| 环境 | NREL 5MW 解析公式 + 一阶转速动力学 |
| 任务 | 目标 = 最大可发功率 × (80%→65%) 阶跃；风速 8→9.5 m/s 阶跃 |
| episode | 200 步（1 步 = 1 秒） |
| PPO | 200,000 步，4 个并行环境，lr=3e-4（退火），clip=0.2，GAE λ=0.95 |
| 种子 | seed=42（全局统一） |
| 观测 | 归一化到 ~[0,1]（环境内建，训练/评估一致） |

### 2.6 过程中踩的两个坑（值得在组会讲，体现工程判断）

1. **目标必须物理可达**：初版设目标 2.5/3.5 MW，但 8 m/s 风速下最大只能发 ~1.9 MW——
   任务本身不可能完成，PPO 永远学不好。**修正**：目标改为"当前风况最大可发功率的 80%/65%"。
2. **训练/评估观测必须一致**：初版训练用 NormalizeObservation wrapper、评估用原始观测，
   输入尺度差 100 万倍，策略输出乱动作。**修正**：归一化内建到环境，训练评估天然一致。

---

## 三、现场演示（demo.py）

### 3.1 演示前检查（提前 10 分钟）

```powershell
# 1. 模型文件存在
Test-Path .\models\ppo\ppo_tracking_v3_seed42.pt   # 应为 True
# 2. venv 存在
Test-Path .\.venv\Scripts\python.exe               # 应为 True
```

### 3.2 演示命令（一条命令跑完，约 10 秒）

```powershell
.\.venv\Scripts\python.exe .\optimization_control\ppo_single_turbine\demo.py --target-fraction 0.8 --step
```

### 3.3 预期输出 + 讲解词

**终端会显示**：
```
目标设定: 0.8 (比例) + 阶跃
跟踪 RMSE = 38.13 kW | MAE = 26.88 kW（目标 ~1.74 MW，相对误差 1.54%）
桨距角范围: 3.7~7.2° | 转速范围: 1.17~1.27 rad/s
动作平滑度（桨距变化 std）: 0.146°
效果图已保存: ...\runs\demo_0.8_step.png
```

**口头讲解**（照着说）：
> "这里我输入的目标功率是'当前风况最大可发功率的 80%'（约 1.5 MW），
> 模拟电网下发降载指令。PPO 控制器实时输出桨距角和转速的调节量，
> 让实际功率稳定贴住目标，误差只有 1.5% 左右。
> 第 100 秒目标阶跃到 65%，可以看到控制器在几秒内重新跟上，这就是动态响应能力。"

**打开效果图**：
```powershell
Invoke-Item .\runs\demo_0.8_step.png
```

图有 3 个面板（边指边说）：
1. **功率跟踪**：黑虚线 = 目标功率（电网指令），蓝实线 = PPO 实际功率，蓝色阴影 = 误差带
   → 实线紧贴虚线，阶跃后快速收敛
2. **桨距角**：PPO 自动把桨距从 ~7° 调到 ~4°（降载需要增大桨距、减少捕风）
3. **转速**：在 1.17~1.27 rad/s 之间小幅调节

### 3.4 现场可变演示（加分项）

```powershell
# 换一个目标（70% 固定降载）
... demo.py --target-fraction 0.7

# 演示物理约束：目标 2.5 MW 超过当前可发 1.84 MW → 自动 clamp 并警告
... demo.py --target-power 2.5
```

讲解词：
> "如果我下发的目标超过风机物理能发的上限（风速 8 m/s 时最大约 1.84 MW），
> 系统会识别并提示，不会硬追一个不可能的目标——这是工程上必须处理的约束。"

---

## 四、其他脚本

| 脚本 | 作用 | 运行方式 | 产出 |
|------|------|---------|------|
| `demo.py` | **演示**：输入目标功率 → 效果图 | 见上 | `runs/demo_*.png` + 终端指标 |
| `train.py` | **训练** PPO | `python train.py --total-timesteps 196608 --num-envs 4` | `models/ppo/*.pt` + `runs/<run>/metrics.csv` + `training_curve.png` |
| `eval.py` | **评估**：PPO vs P 控制 对比 | `python eval.py --model <模型路径> --policy-format <tanh_squashed或legacy_unsquashed> --episodes 1` | `runs/ppo_vs_p_controller.png` + 终端指标 |
| `simplified_turbine_env.py` | 环境本体（物理模型+RL 接口） | 被以上脚本调用 | — |

**train.py 常用参数**：`--total-timesteps`（训练步数）、`--num-envs`（并行环境数）、
`--seed`（随机种子）、`--run-tag`（实验名）。

**P 控制基准是什么**：传统比例控制器。当前工作点有限差分得到 `dP/dβ < 0`，因此按
`Δβ = -kP × (P_target - P)` 调桨距。它用于检验 PPO 是否确有收益，本身不预设谁更优。

---

## 五、指标速查（含义 + 在哪里看）

### 5.1 终端指标（demo.py / eval.py 打印）

| 指标 | 含义 | 怎么看 | 历史记录（旧协议） |
|------|------|--------|---------|
| 跟踪 RMSE | 功率误差的均方根（kW） | 越小越好 | PPO 28.5 / P 控制 959.7 |
| 跟踪 MAE | 功率误差的平均绝对值（kW） | 越小越好 | PPO 20.0 / P 控制 900.7 |
| 相对误差 | MAE ÷ 目标功率 | <2% 即优秀 | 1.54% |
| 动作平滑度 | 桨距角逐帧变化的 std（°） | 越小越稳 | 0.146° |
| 桨距/转速范围 | 控制器使用的参数区间 | 应在物理边界内 | β 3.7~7.2°、ω 1.17~1.27 |

### 5.2 训练曲线（`runs/<run_name>/training_curve.png` + `metrics.csv`）

| 曲线 | 含义 | 健康形态 |
|------|------|---------|
| episodic_return | 本轮完成 episode 的平均累计奖励 | 历史 CSV 全为 0 且不可用；T1-R 后的新训练应为有限非零值 |
| explained_variance | 价值函数对回报的解释度 | 0.7~0.9 说明 Critic 学得不错 |
| policy_loss | 策略更新损失 | 波动但总体稳定 |
| value_loss | 价值函数损失 | 下降并稳定 |

### 5.3 对比图

`runs/ppo_vs_pid.png` 是旧协议历史图，其中的差距不能作为当前结论。T1-R 的 `eval.py`
按完整 episode 评估并输出 `runs/ppo_vs_p_controller.png`。

### 5.4 文件位置总览

```
runs/                            # 演示/训练输出（不入 git）
  demo_0.8_step.png              #   演示效果图
  ppo_vs_pid.png                 #   旧协议历史图，不作为当前结论
  ppo_vs_p_controller.png        #   T1-R 当前 episode 评估输出
  <run_name>/metrics.csv         #   训练指标
  <run_name>/training_curve.png  #   训练曲线
models/ppo/ppo_tracking_v3_seed42.pt   # 训练好的策略（不入 git）
optimization_control/experiments/20260808_ppo_single_turbine/   # 实验记录（指标/图/summary）
optimization_control/TASKFLOW.md        # 任务流程与状态看板
```

---

## 六、总结与展望（收尾话术）

> "历史实验只证明环境、训练、模型加载和绘图链路能够运行。复核发现旧评估跨越 episode、
> 比例控制方向写反，且策略概率对应的未压缩动作与环境裁剪后的动作不一致，所以 34 倍差距不能作为结论。
> 当前已修复日志、目标/终点语义、动作尺度和有界策略；下一步需重新训练，并在多种子、同 episode 的条件下形成
> PPO 与比例控制、静态优化等基线的正式比较。"

**下一步**：
- T2：向袁夫达提出含偏航数据需求（已写好格式建议）
- T3-T6：重训含参数代理模型 → 准静态 RL 环境 → MADDPG 训练 → 结题素材

---

## 七、组会前检查清单

- [ ] 模型文件存在（`Test-Path ...\ppo_tracking_v3_seed42.pt` = True）
- [ ] venv 存在
- [ ] 演示命令跑一遍，确认输出正常（提前跑，不要现场装依赖）
- [ ] 效果图提前打开一版备着（万一现场渲染慢）
- [ ] 备好 2-3 个演示参数（0.8+step / 0.7 / 2.5MW clamp）

## 八、2026-08-24 复核与收尾注记

- 本汇报是 2026-08-09 的历史讲稿，不是当前实时状态；后续任务以 `../TASKFLOW.md` 和项目根目录 `PROJECT_STATUS.md` 为准。
- `eval.py` 已将误称的 `PIDController` 改为 `PController`，并用有限差分确认 `dP/d_beta < 0` 后修正控制符号。
- 旧“34 倍”数值还存在未压缩高斯动作与环境裁剪后动作不一致的问题，只保留追溯，不能作为正式结论。
- 历史 `metrics.csv` 的 `episodic_return=0` 保持原样；当前训练脚本已兼容 Gymnasium vector info，并记录每轮完成 episode 的平均回报。
- 当前合成任务在 200 步返回 `terminated=True`；向量训练使用 SAME_STEP 自动重置，独立评估每 episode 显式 `reset`。
- 动作惩罚已按各动作上限归一化；奖励定义改变后必须重新训练，才能形成新的正式性能结论。
- 回归测试使用 Python 标准库 `unittest`，不需要安装 `pytest`。
- 新训练策略使用 tanh 压缩高斯并映射到物理动作边界；历史模型评估必须显式选择 `legacy_unsquashed`。
- 修正旧模型单场景回归：PPO RMSE 49.83 kW，PController RMSE 35.99 kW；不是统计性能结论。

## 九、T1-R 当前用法

以下命令均在项目根目录执行。

回归测试（标准库 `unittest`，无需 `pytest`）：

```powershell
& .\.venv\Scripts\python.exe optimization_control\ppo_single_turbine\test_baseline.py
```

512 步训练 smoke test（不保存模型，只验证有界动作、训练与回报日志链路）：

```powershell
& .\.venv\Scripts\python.exe optimization_control\ppo_single_turbine\train.py --total-timesteps 512 --num-envs 2 --num-steps 256 --num-minibatches 4 --update-epochs 1 --no-save-model --run-tag smoke_tanh_policy
```

按完整 episode 评估现有模型：

```powershell
& .\.venv\Scripts\python.exe optimization_control\ppo_single_turbine\eval.py --model models\ppo\ppo_tracking_v3_seed42.pt --policy-format legacy_unsquashed --episodes 1
```

新评估图输出为 `runs/ppo_vs_p_controller.png`；`runs/ppo_vs_pid.png` 是旧协议生成的历史图，不应覆盖或当作当前评估结果。
