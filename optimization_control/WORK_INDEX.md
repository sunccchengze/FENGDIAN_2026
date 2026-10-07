# 优化控制工作总索引

更新日期 2026-10-07。主责为优化控制；包括代理模型优化、PPO、随机入口、统一执行器与传统对照、三机 MADDPG、PINN 接口适配、评估与失败诊断。队友原始仿真数据和 PINN 主体不属于本人独立成果。

## 按工作阶段查找

| 阶段 | 实现与证据入口 | 当前判断 |
|---|---|---|
| FLORIS 功率代理模型复现与优化 | [工作记录](surrogate/WORKLOG.md)、[评估协议](surrogate/eval_protocol.md)、`surrogate/models/final/` | 已完成基线复现、候选比较和 XGBoost 优化；适用原数据域，不含完整控制自由度 |
| 单机 PPO 预研与工程复核 | `ppo_single_turbine/`、[准静态闭环指南](OPTIMIZATION_SHELL_GUIDE.md) | 保留旧策略和修复记录；旧未约束动作结论已撤回，不混用策略版本 |
| 动作映射与执行器 | `utils/`、`environments/`、[接口说明](PINN_OPTIMIZATION_INTERFACE.md) | 统一目标值、执行器运行点、观测与奖励；Mock 仅用于联调 |
| 随机风况与单机回放 | [随机风况指南](ppo_single_turbine/随机风况使用指南.md)、`environments/wind_generator.py` | 平稳湍流、慢变、阵风和统计验证；不是完整 TurbSim 全场风 |
| 三机 MADDPG 与传统基线 | [模块入口](maddpg_wind_farm/README.md)、[逐通道诊断](maddpg_wind_farm/DIAGNOSTIC_REPORT.md) | 三个通道共用执行器，机舱朝向与偏航失配分离 |
| 稳定训练与固定评估 | [训练流程](maddpg_wind_farm/STABLE_TRAINING.md)、[混合风况对照](maddpg_wind_farm/MIXED_STABILITY.md) | 多种子、验证选模、冻结测试已建立；未全部通过精度与稳定性门槛 |
| 可达性与误差分解 | [诊断及干预](maddpg_wind_farm/REACHABILITY_TRACKING.md)、[价值学习审计](maddpg_wind_farm/VALUE_BASELINE_DIAGNOSTIC.md) | 区分物理不可达与策略剩余损失；保留未通过的采样干预 |
| 队友 PINN 接收与九输入联调 | [交付检查](maddpg_wind_farm/PINN_HANDOVER_REVIEW.md)、[联调报告](maddpg_wind_farm/FIXED_PINN_DEMO.md) | 使用队友主体和合成标签训练副本；没有真实精度验证 |
| 固定九输入结果异常排查 | [异常诊断](maddpg_wind_farm/FIXED_PINN_DIAGNOSTIC.md) | 识别目标响应弱、价值失配和近自然功率低误差；未断言唯一根因 |
| 本轮逐级能力验证 | [完整报告](maddpg_wind_farm/FIXED_CURRICULUM.md) | 12 次训练、245760 步；单目标可学习，多目标可靠性与后期退化未解决 |

## 接手顺序

先读本索引和 `TASKFLOW.md`，再读相关模块报告及实验的 `config.yaml / metrics.csv / summary.txt`。当前九输入迁移模型只在 9 m/s、方向 0、TI 0.1 下用于合成联调；随机风况能力属于外层环境，不能直接施加给这一固定工况网络。

本轮 ZIP 配有 `任务说明.docx`、`readme.md`、`manifest.json` 和可移动回放入口。全部历史产物按原实验目录保留在分卷中，不只保留成功结果。GitHub 分支只用于交付和审阅，没有合并到团队 main。
