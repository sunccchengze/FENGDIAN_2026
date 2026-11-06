# 冻结父策略动作约束：运行前协议

用户2026-10-24确认执行。唯一干预：Actor损失为负Q均值加lambda乘当前采样状态下自身总动作与冻结父Actor总动作的标准化均方差。baseline lambda=0，anchor lambda=1；两臂Actor lr固定1e-4，Critic、奖励、探索、执行器及网络结构不变。系数为工程假设，不称最优。

1. 每个Actor三通道平均，再对batch平均。动作是compose后的归一化总目标；分母固定为完整权限尺度yaw=2*radians(5)/0.5、pitch=1、speed=2*0.1/0.667，相当于5度、0.11rad桨距和0.1rad/s转速。分母不随yaw ramp改变；父策略使用冻结full尺度，在当前obs上求值，无梯度且无探索噪声。惩罚不写进环境reward或Critic TD目标。
2. 同上一轮的三份20261023_residual_random_control/all初始交接检查点起步；两臂同父、同网络/target/Critic优化器/回放/RNG，统一清空Actor Adam moments。teacher为交接Actor固定副本，不用训练终点或测试挑父策略。version3完整保存teacher权重、teacher配置、lambda、固定尺度及原训练状态，独立加载器拒绝混淆v2/v3。
3. 主种子42及run0/1/2派生流。两臂各三流8192步，共49152步；eval2048，warmup512，每2步更新，无全随机warmup。speed修正固定±0.10rad/s，yaw前4096步从1度到5度。与原对照一样在验证/选模/测试中统一full权限。
4. 训练namespace1600000，验证1710000，routine测试1820000，探索namespace1214；目标和风况族沿用上一轮。1839000固定7.6m/s、4.4MW仅为已知压力回归，不计新独立样本。不得用已读取的旧test挑系数。
5. 工程稳定性：final/selected<=1.25；final mean/worst均<=父策略1.05；anchor final mean/worst均<=配对baseline1.05。三流全过才称本轮稳定性通过，5%只是工程容差。另报原400/500kW精度、真实配对差值、selected_step及动作偏离；selected=initial不能称学习收益。
6. 先验证lambda0更新与旧算法精确一致、teacher冻结、三通道惩罚梯度和完整恢复，再冻结源与配置启动训练。baseline0在2048步真实暂停恢复；审计两个128步恢复分叉不计新增实验训练。
7. 六次训练和选模全部冻结后一次释放新测试，initial/selected/final/parent与固定/P/PI统一case和执行器。P/PI的yaw/speed由原调度给定，属于完整方案比较。保留所有失败，无第二系数或额外预算。标准差不是显著性证明。
8. 保留config.yaml、metrics.csv、summary.txt、各检查点和lineage、动作偏离曲线、Python图及独立结果报告。新源码UTF-8 LF后冻结，不改旧保护源，不修改PINN，不推送、不删除、不安装全局依赖。
