# 单项Actor学习率稳定化：实际结果

实验按[冻结协议](RESIDUAL_STABILITY_PROTOCOL.md)执行；唯一干预为Actor lr从1e-4降至3e-5。其余模型、动作语义、奖励、探索和预算相同，基于[已有验证集闭环诊断](RESIDUAL_STABILITY_DIAGNOSTIC_RESULTS.md)提出，不读取旧独立测试调参。

本轮实验完成，但降低Actor学习率未通过稳定化验收，不替换现有默认。父模型为上一轮各流all初始handover，三通道网络结构不变；两臂统一清空Actor moments，Critic优化器、网络/target、回放和RNG继承。各臂3流×8192步，总49152步；完整权限验证与选模包含initial。三个流由主种子42派生，不称为三个不同的全局seed。

六次训练的selected_step全部为0：本轮选模保留了父策略，没有学到验证集上更好的策略。两臂final/selected均3/3不超过1.25，但相对父策略的mean/worst共同5%门槛均0/3通过；low_lr相对同预算baseline的共同5%门槛2/3通过。完整稳定化验收失败。

## 验证集配对结果

单位kW，越低越好；每个训练流按六个验证场景的RMSE取均值。只有validation用于选模。

| 派生流 | 初始／选中 | baseline终点 | low_lr终点 | low_lr减baseline | low_lr终点／选中 |
|---|---:|---:|---:|---:|---:|
| 0 | 329.11 | 372.86 | 385.17 | +12.31（+3.30%） | 1.1703 |
| 1 | 285.04 | 305.86 | 327.87 | +22.01（+7.20%） | 1.1503 |
| 2 | 299.09 | 338.33 | 317.53 | -20.79（-6.15%） | 1.0617 |

low_lr终点仅1/3配对改善。原400/500 kW选中策略精度检查两臂各2/3通过，且均来自初始策略；这一字段只检查mean/worst精度，与本轮稳定性门槛分开。流0最差场景初始523.53 kW，超过500 kW。

## 冻结后的新独立测试

新routine测试由stationary/ramp/gust新轨迹组成，目标2.75/3.35/3.85 MW。表中先对每个训练流的18个routine case取平均，再报告三流均值±样本标准差。P/PI使用完全相同的测试case、后台参考与执行器；其桨距为P/PI功率反馈，yaw/speed按统一调度，不是三个通道各装一个P或PI。这里属于完整控制方案比较。

| 控制方案 | 常规独立测试RMSE（kW） |
|---|---:|
| 初始＝选中＝父策略（两臂完全相同） | 405.35 ± 21.33 |
| baseline终点 | 419.38 ± 28.10 |
| low_lr终点 | 429.57 ± 23.66 |
| P组合方案 | 571.34 |
| PI组合方案 | 506.05 |

low_lr终点相对baseline三流分别增加7.16、17.49、5.92 kW，0/3改善；总体增加10.19 kW（2.43%）。两臂终点在三流常规测试中均差于自身初始策略。虽然常规平均仍低于本次P/PI，但这是继承策略已有能力，不能归功于本轮训练或学习率干预，也不能证明所有case均领先。

已知低风压力回归为固定7.6 m/s、4.4 MW目标和两种初始桨距；不是新独立样本。初始／选中1684.61 kW，baseline终点1682.67 kW，low_lr终点1598.38 kW，P/PI均1383.30 kW。low_lr在该回归中三流终点均优于baseline，但仍弱于P/PI，不足以推翻常规独立测试和冻结验收的失败结论。

## 诊断、验证和图表

前置诊断共39个策略变体、234个闭环case，29952个环境步但没有RL更新。选中与最终策略的通道在混合策略自身当前观测上组合，表明pitch漂移及yaw/speed补偿同时存在。关掉yaw或speed只改善部分流，不能将yaw饱和或某一个通道断言为唯一根因。详见[诊断结果](RESIDUAL_STABILITY_DIAGNOSTIC_RESULTS.md)。

- 7项不同受影响测试通过：4项Actor学习率／恢复契约和3项通道诊断测试。
- 正式实验50个受保护源／父模型摘要不变；诊断阶段57个保护项不变，两个计数有重叠，不能相加成不同文件数。
- 六份最终回放共196608条保留转移通过总动作、奖励、执行器速率检查；其中包含重复继承历史，实际新增训练49152步。新增转移全部符合动态残差范围。
- baseline流0在2048步真实暂停再恢复；该检查点两个128步分叉的动作、奖励、loss、噪声和网络完全相同，并与真实恢复后下一回合的保存动作一致。审计分叉没有写回实验模型、没有追加训练预算。
- 600条测试指标、76800行轨迹复算RMSE差为0；其中540条routine指标为新独立测试，60条为已知压力回归。
- 补充原始检查点审计：三组两臂初始的四套网络、全部Critic优化器、回放及随机状态完全相同；Actor moments均空，唯一算法差异为学习率。全部30个检查点的配置与Actor优化器学习率一致。记录见实验目录`paired_initial_audit.json`。

[训练与测试图PNG](../experiments/20261024_residual_stability/actor_lr_validation_test.png)／[PDF（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)由Python/Matplotlib生成，已视觉检查。左图实线baseline、虚线low_lr，各检查点统一完整控制权限；曲线显示六次训练均未低于各自起点，降低学习率仅流2较平缓。右图为routine测试均值及跨训练流SD；initial、selected、parent及传统控制的两臂结果相同，点会重叠。误差条不是置信区间，P/PI没有训练随机流SD。该图没有包含低风压力回归，不能用它宣称低风高目标表现好。

[通道组合诊断图](../experiments/20261024_residual_stability_diagnostic/channel_swaps.png)中S/F依次代表yaw/pitch/speed来自selected/final，FFF为红色。它说明通道相互补偿，柱差不能相加；三个面板横轴不同，应比较数值而非跨面板柱长。

下一步可单独检验相对父策略的动作偏离约束，让Actor保留改进空间但限制联合漂移；应先冻结惩罚形式、系数和同预算对照，再重新训练及使用新的测试。这个建议尚未实施、未获性能验证。本轮没有追加第二个候选，也没有把低学习率改为默认。

5%工程不劣容差不等于性能改善；selected=initial不证明学到了新策略。7.6m/s、4.4MW场景为已知低风压力回归，不能称为新独立样本。模型为合成入口和合成标签PINN联调，不据此主张真实风机收益或统计显著性。

复现（NEW_DIRECTORY必须不存在；已有目录只用run恢复）：

```powershell
.venv/Scripts/python.exe -B -m unittest optimization_control.tests.test_residual_stability optimization_control.tests.test_residual_stability_diagnostic -v
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.residual_stability prepare --output optimization_control/experiments/NEW_DIRECTORY
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.residual_stability worker --output optimization_control/experiments/NEW_DIRECTORY --arm baseline --run-id 0 --stop-after 2048
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.residual_stability run --output optimization_control/experiments/NEW_DIRECTORY
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.verify_residual_stability --output optimization_control/experiments/NEW_DIRECTORY
```

产物：[config.yaml](../experiments/20261024_residual_stability/config.yaml)、[metrics.csv](../experiments/20261024_residual_stability/metrics.csv)、[summary.txt](../experiments/20261024_residual_stability/summary.txt)。检查点、lineage、选择锁、测试冻结锁与审计保存在同目录；训练只支持已保存的eval回合边界恢复。
