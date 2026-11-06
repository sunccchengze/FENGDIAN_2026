# 联合蒸馏实测与接管结果

本轮遵守[运行前协议](JOINT_DISTILLATION.md)，从 `20261023_progressive_random_control` 的三个仅桨距选中策略出发。旧实验及其精度失败保持不变。新协议的相对工程门槛与旧400/500 kW绝对精度门槛分别报告。

三个派生流的两候选均未满足蒸馏接管标准，speed接管通过0/3；按冻结协议停止，新增环境训练为0步，未启动yaw、配对续训或独立测试。实际完成143400次蒸馏mini-batch更新（36个网络候选，其中一个网络提前600次停止）。这不是三通道训练完成，也没有新的性能收益结论。

| 派生流 | 候选 | 旧动作最大漂移（限.02） | 新speed最大误差（限.05） | 六网络优化器更新数 |
|---|---|---|---|---|
| 0 | 1 | 0.02978 | 0.18209 | 18000 |
| 0 | 2 | 0.02551 | 0.18685 | 30000 |
| 1 | 1 | 0.02318 | 0.11706 | 17400 |
| 1 | 2 | 0.01729 | 0.11118 | 30000 |
| 2 | 1 | 0.02483 | 0.12739 | 18000 |
| 2 | 2 | 0.03567 | 0.12191 | 30000 |

三个父策略在新验证风况的RMSE只用于新实验交接基准，没有重新评判旧实验通过与否。内部验证的转速误差明显低于上一轮固定隐藏层单行拟合的.395/.304/.339最大误差，但两种拟合方式及误差分布不同，不能把数字下降当作闭环收益。

30个受保护文件（含队友源文件、冻结网络、旧选择记录和父策略）摘要核对一致。34项不同测试通过（5项联合蒸馏、7项原晋级流程、8项随机参考调度、14项MADDPG/接口/环境）。审计另外对三个真实父检查点做保存—加载—带噪动作—下一步联合更新一致性验证；原检查点字节摘要保持不变。

实现保持原MLP和绝对参考，不增加残差或分支。在线Actor与target Actor分别使用各自父policy作为教师，包含后台转速参考；新权限只在全部六网络内部蒸馏验证均通过时授予。联合拟合允许隐藏层变化，旧通道loss权重10。候选从父状态分别重新初始化，最多3000/5000次mini-batch更新，每100次使用内部蒸馏验证早停；因此该验证集参与了选择，不是独立测试。

Actor参数坐标已变化，旧Adam moments不能被视作无影响。本方案统一重置全部Actor优化器，父权限配对对照也执行同样重置；Critic与target Critic、Critic优化器、回放和训练RNG继承。旧回放的物理动作语义保留，但不保证行为分布相同。target拟合时临时开启梯度，拟合后重新冻结。

图 `../experiments/20261023_joint_distillation/distillation_errors.png` 使用Python/Matplotlib从保存的诊断数值绘制。左图比较旧已学动作的最大漂移与.02门槛，右图比较新转速参考误差与.05门槛。每组取online/target各三网络中的最大值；柱越过虚线表示该训练流接管失败，不能用较小的平均误差替代协议中的max。

候选末态权重和逐行误差未持久化，仅保留fit max、内部验证max/p95/RMS。fit max为启用通道合并最大值，p95/RMS也合并旧/新通道，不能据此定位新转速的最差输入Ueff或断言仅clip边界稀有点导致失败。没有为补此诊断重新启动拟合。后续若研究误差来源，需要新的预声明诊断；本轮不以此说明MADDPG或三通道控制本身不可行。

复现入口（从仓库根目录运行，输出目录必须不存在）：

```powershell
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.joint_distillation all --output optimization_control/experiments/NEW_DIRECTORY
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.verify_joint_distillation --output optimization_control/experiments/NEW_DIRECTORY
.venv/Scripts/python.exe -B -m unittest optimization_control.tests.test_joint_distillation optimization_control.tests.test_progressive_random_control optimization_control.tests.test_random_wind_training optimization_control.tests.test_maddpg -v
```

`prepare`会冻结配置、父检查点摘要和新的验证/测试风况；`run`只执行未冻结的新实验，`all`组合两步。选模后拒绝追加训练。训练检查点保存网络、优化器、回放及随机状态；本入口没有自动中断续训命令，不能将底层检查点恢复正确性说成命令级恢复已完成。

产物保留于 `../experiments/20261023_joint_distillation/`：`config.yaml`含父策略lineage与源摘要，`metrics.csv`含36条网络候选诊断，`summary.txt`含完整证据和复现；`pitch_speed_run_*/distillation.json`保留原诊断，`selection.json`冻结本轮停止状态，`verification.json`记录加载与下一步更新一致性。实验运行产物沿用默认忽略约定，提交三类必要小文件。没有写入队友PINN、旧策略或旧实验；没有安装依赖、推送或公开发布。

本轮对象仍为十二输入合成标签联调网络，转速参考 `clip((1.267/11.4)*Ueff,.6,1.267)` 仅为联调假设，不是经物理证明的最优转速曲线。
