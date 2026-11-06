# 基线参考加MADDPG修正量：运行前协议

2026-10-23冻结。仅合成十二输入网络的软件联调；保留旧绝对动作、联合蒸馏失败及原400/500 kW精度门槛。

1. 从 `20261023_progressive_random_control` 三个pitch选中策略出发。pitch保持原绝对参考；speed采用 `clip(k*Ueff,.6,1.267)` 加有界MADDPG修正，再新增yaw基线失配角0加修正。总绝对目标交原统一执行器，机舱朝向与风向差产生gamma，不修改PINN、奖励、P/PI或执行器。
2. 原MLP/Actor/Critic继承。新通道online/target输出行均置零，hidden和旧输出行逐位不变；检查父训练回放总动作及新闭环validation，允许浮点误差2e-6，总功率RMSE均值和worst须<=父1.05。所有Actor Adam moments重置，父权限配对对照同样重置；Critic/优化器/回放/RNG继承。version2检查点明确残差语义，旧version1拒绝误读。
3. 物理修正范围speed .02到.10 rad/s、yaw 1到5度，前4096环境步线性扩大。这是人为联调范围，并非硬件额定或最优控制结论。speed阶段yaw仍后台跟踪，yaw阶段speed固定此前最终范围。噪声先在raw修正坐标加入并clip[-1,1]，再乘范围、加基线并按全域动作边界clip；pitch噪声保持绝对归一化坐标。Actor更新和target Critic都使用合成后的总动作，回放也记录总动作，不能存raw修正。
4. 每层三流child和三流父权限配对对照，各8192步，eval2048，warmup512后每2步更新，actor lr1e-4，主seed42派生0/1/2，无全随机warmup。每层49152步，全两层最多98304步；失败不追加预算。父子使用同一父检查点、风况顺序和探索随机流，公共Actor重置匹配。
5. 全部验证、选模和独立测试固定最终完整修正范围，所有checkpoint含step0均可选，不能用小权限评估结果充当完整策略。检查点分别记录训练时幅度、评估完整幅度和步数；训练恢复按step恢复训练幅度。selected=initial只能证明保留，不能称新通道学习收益。
6. 新工程晋级：selected validation均值和worst分别<=父1.05，final/selected<=1.25，三流全部通过才加yaw。旧绝对精度400/500 kW另报；性能收益另与同预算对照配对比较。报告实际修正RMS/max、clip/范围饱和和新通道有效性，接管/稳定/收益分别判断。
7. 新风况namespace train1040000（yaw层+10000）、validation1150000、test1260000、stress1269000；目标train2.6/3.2/3.8MW、validation2.85/3.45MW、test2.75/3.35/3.85MW。test在全部已有阶段选择及配置冻结后仅释放一次，失败策略也评估selected/final/initial/parent及统一P/PI。测试不用于调参。
8. 支持eval检查点处的回合边界恢复，恢复进度包括回放、网络、优化器、RNG、探索和训练幅度；从最近已保存检查点继续，未保存步数不计入已持久化成果。第0流计划在2048步暂停后恢复。另以同一检查点分叉验证短rollout/update的一致性，不为此增加实验训练预算。
9. 先运行受影响测试，再冻结代码/协议/父模型摘要并实际训练；新文件UTF-8 LF。保存config.yaml、metrics.csv、summary.txt、lineage、动作/执行器审计、恢复证据和Python图表。协议不后加结果，实际结果另放RESIDUAL_RANDOM_RESULTS.md。旧文件不覆盖，不删除、不上传。
