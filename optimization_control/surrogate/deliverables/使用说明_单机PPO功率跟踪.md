# 单机 PPO 功率跟踪 — 使用说明

> 交付日期：2026-08-08 | 提供：优化控制模块（Codex）
> 这是什么：一个**强化学习演示**——输入目标功率（电网指令），PPO 控制器自动输出桨距角/转速，
> 让单台风机的实际功率稳定跟踪目标。基于 NREL 5MW 解析公式环境（Cp 经验公式 + 一阶转速动力学）。
> **2026-08-24 复核警告**：本文是 2026-08-08 历史交付说明。旧评估跨越 episode、
> P 控制方向错误，且未压缩策略动作与环境裁剪后的动作不一致；文中的 28.5/959.7 kW
> 和“显著优于”结论已作废。当前状态与正式命令以 `PROJECT_STATUS.md` 和
> `optimization_control/OPTIMIZATION_SHELL_GUIDE.md` 为准。


---

## 一、效果先看这里（3 分钟出结果）

```bash
# 1. 安装依赖（Python 3.12）
pip install -r requirements.txt

# 2. 运行演示（目标功率 = 当前风况最大可发功率 × 0.8，中途阶跃到 0.65）
python demo.py --target-fraction 0.8 --step
```

终端会打印跟踪指标，并生成效果图 **`runs/demo_0.8_step.png`**：

```
目标设定: 0.8 (比例) + 阶跃
跟踪 RMSE = 38.13 kW | MAE = 26.88 kW（目标 ~1.74 MW，相对误差 1.54%）
桨距角范围: 3.7~7.2° | 转速范围: 1.17~1.27 rad/s
效果图已保存: runs/demo_0.8_step.png
```

效果图共 3 个面板（从上到下）：
1. **功率跟踪**：黑色虚线 = 目标功率（电网指令），蓝色实线 = PPO 实际功率，蓝色阴影 = 误差带
2. **桨距角**：PPO 输出的桨距角随时间变化（控制动作之一）
3. **转速**：PPO 输出的转速变化（控制动作之二）

---

## 二、在哪里输入目标功率

**方式 1：按比例（推荐，始终物理可达）**

```bash
python demo.py --target-fraction 0.7          # 目标 = 最大可发功率 × 70%
python demo.py --target-fraction 0.8 --step   # 80% → 65% 阶跃（第 100 步），演示动态响应
python demo.py --target-fraction 0.5          # 50%（深度降载）
```

> 取值范围 0.05~0.95。比例越小，要求降载越多，跟踪越难。

**方式 2：绝对功率（MW）**

```bash
python demo.py --target-power 2.0             # 目标 2.0 MW
```

> 注意：如果目标超过当前风况的最大可发功率，程序会自动 clamp 并提示，例如：
> `⚠ 目标 2.50 MW 超过当前风况最大可发 1.84 MW，已 clamp`

**训练代码里改目标**（进阶）：`simplified_turbine_env.py` 的 `_target_power()` 函数中修改目标逻辑。

---

## 三、在哪里显示效果

1. **终端**：跟踪 RMSE / MAE / 相对误差 / 桨距角与转速范围 / 动作平滑度
2. **效果图**：`runs/demo_*.png`（默认在项目 `runs/` 目录，可用 `--out` 指定路径）
3. **训练曲线**（复现训练时）：`runs/<run_name>/training_curve.png` + `metrics.csv`
4. **评估对比**：`runs/ppo_vs_pid.png` 是历史失效图；当前脚本默认输出 `runs/ppo_vs_p_controller.png`

---

## 四、复现训练

```bash
python train.py --total-timesteps 196608 --num-envs 4 --run-tag ppo_tracking
# 训练完成后模型保存到 models/ppo/ppo_tracking_seed42.pt
```

评估新训练模型（PPO vs `PController`）：

```bash
python eval.py --model models/ppo/ppo_tracking_seed42.pt --policy-format tanh_squashed
```

**当前 T1 回归配置**（seed=42，196608 步）：PPO clip=0.2、GAE λ=0.95、lr=3e-4（退火）、
64×64 Tanh Actor-Critic；环境：目标 = 最大可发功率 ×（80%→65%），风速 8→9.5 m/s 阶跃，episode 200 步。

---

## 五、历史结果摘要（2026-08-08，结论已作废）

| 控制器 | 跟踪 RMSE (kW) | 跟踪 MAE (kW) | 相对误差 |
|--------|---------------|---------------|----------|
| **PPO（本交付）** | **28.5** | **20.0** | **<2%** |
| P 控制基准（仅比例项，kP=2e-6） | 959.7 | 900.7 | ~35% |

这些数值只用于追溯旧交付，不得用于组会或结题性能结论。旧 v3 模型按修正协议单场景回归为 PPO RMSE 49.83 kW、PController RMSE 35.99 kW；仍需用当前 tanh 策略重新训练并做多种子比较。

---

## 六、文件清单

```
├── 使用说明.md                # 本文件
├── demo.py                    # ★ 演示入口：输入目标功率 → 出效果图
├── train.py                   # PPO 训练（cleanrl 单文件风格）
├── eval.py                    # PPO vs P 控制评估对比
├── simplified_turbine_env.py  # 环境（Cp 解析公式 + 一阶转速动力学）
├── model/
│   └── ppo_tracking_v3_seed42.pt   # 训练好的 PPO 模型
├── results/                   # 训练指标、曲线、对比图、示例效果图
└── requirements.txt           # 依赖清单
```

## 七、注意事项

1. **目标必须物理可达**：8 m/s 风速最大约可发 1.84 MW、9.5 m/s 约 3.1 MW；超过会自动 clamp（提示见上）
2. 模型在"最大可发 × 0.65~0.8"的目标分布内训练，**强烈建议演示用该区间**（比例模式 0.65~0.8 效果最好）；
   0.5 以下或绝对功率超出训练分布时，跟踪误差会增大（模型外推）
3. 这是**单机功率跟踪**（控制量=桨距角/转速），偏航协同（多机）是下一步，等含偏航数据

## 八、2026-08-23 使用前复核

1. `metrics.csv` 的 `episodic_return` 全为 0，是日志采集缺陷；训练效果以独立评估和功率跟踪图为准。
2. `demo_*.png` 的中文标题/坐标出现缺字方框，正式展示前需配置中文字体后重新生成。
3. 结果只覆盖解析公式环境及 65%–80% 目标比例附近，不能表述为真实风机、FLORIS 可控环境或代理 PINN 上已验证。
4. 当前传统基准只有比例项，不能用于“PPO 全面优于工业 PID”的结论。