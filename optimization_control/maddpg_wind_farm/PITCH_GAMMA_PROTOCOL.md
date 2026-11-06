# 桨距gamma单因素正式对照（2026-10-29，训练前冻结）

主对话已读取并批准3b4acc9的PITCH_REWARD_ALIGNMENT_CANDIDATE全文。本协议将该方案落到一次可执行对照；不改变历史失败结论，不修改原共享状态/别树，不合并master或push。

## 固定因素与文件职责

两臂均n8，只改gamma=.99/1。逐步reward=100[-((P(t+1)-target)/15MW)^2-.001 mean((exec_reference(t)-exec_reference(t-1))²)]；obs[3,15]、remaining、网络、Actor/Critic LR、采样、三机pitch权限和后台yaw/speed不改。模型SHA7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451，原20261023三父SHA及绝对路径沿用已批准方案，写入config并在prepare核对。

新pitch_gamma_trial.py负责冻结数据/工程检查/预算内worker/选择锁/test；pitch_gamma_review.py只从保存数据审计、汇总、绘图。复用nstep_algorithm.py，不改任何公共训练/环境代码。tests/test_pitch_gamma.py沿用optimization_control/tests职责。配置与结果在experiments/20261029_pitch_gamma_control（config.yaml/metrics.csv/summary.txt）；权重/完整时序/图本地保留，元数据与源码原子提交。失败attempt保留，不覆盖旧实验。

同步AlgorithmConfig.gamma、SequenceReplay.gamma、effective base_config和metadata，清除派生采样缓存；原始reward不变，全部新旧回放按当前gamma即时重算m步。初始四网络、六Adam、回放、RNG均同源，不校准/重置旧Critic。旧gamma=.99的Critic对gamma1语义不匹配作为限制保留。128步true done停止bootstrap；非终止短尾用实际m及gamma^m。gamma1不引入未来输入，也不保证多步off-policy更新稳定。

## 预算、派生流和顺序

正式2×3×16384=98304步，每job128回合/7937次新增update；warmup512/update_every2，std[0,.03,0]白噪声、末比例.2，其他继承。每128保存、每4096验证含initial，完整18场case-RMSE均值严格改善选selected。initial/selected/final全部保留。

主seed42，SeedSequence([42,20261029,purpose,run,...])，purpose5101九格排列、5102初态uniform(.025,.055)、5103探索；train51000000+run1000+ep，validation52000000，test53000000，已知压力53009000。prepare再次扫描原/本/速度树维护config和实验顶层config，排除本候选预留文件，发现占用则停止。先冻结384条训练设计/风数组、全部探索序列及逐回合实际RNG；两臂逐步核对，恢复沿用实际状态。

先通过gamma专项工程（无环境步）：三流.99对既有n8逐batch、loss、四网络/Adam/回放/RNG精确一致；gamma1手算短序列/ring/terminal/缺尾；新进程恢复后的下一update与单进程一致。共8次内存工程update全丢弃，单列不算正式预算。

真实最小运行为run0两臂各前128步，0次新增update，计入各自16384预算。两臂都通过字段/reward/remaining/done/物理检查并保存后，才推进；各到4096再退出并由新进程恢复。其余run1/2完整执行。预计10个正常worker进程；不增加环境学习smoke。每128步预留预算，失败保留保守预留与actual，不自动重算未提交片段。

验证评估最多30快照×18×128=69120步，P/PI验证4608；新test最多20角色×44×128=112640，重复Actor映射可复用但语义角色保留且不可充当独立样本。总评估上限186368（不含学习），每段先预留，恢复已完成评估不重复。没有额外Q网格/机制环境搜索。总学习预算和候选到此为止。

## 选择、验收和测试隔离

原已批准门槛完整保留：

- gamma1三流selected_step>0；有initial被选则不得称三流新增学习。
- selected、final慢变case-RMSE均值各较同预算.99减少≥5%，各至少2/3流改善；相对原父另列，不用退化对照掩盖父损失。
- 平稳/阵风selected、final逐流mean/worst对原父及对照≤1.05。
- 各流final/selected≤1.25；全常规final mean/worst对父及对照≤1.05。
- 各风况/流selected和final平均实际pitch总行程及RMS速率各≤对照1.10倍，分母下限均1e-4（各自SI单位）；worst也报。
- pitch实际[0,.22]rad、每秒速率≤.00872664626，tol1e-9。用info实际float64执行器量/相邻实际状态核对，包含首步；不从float32观测反算后放宽门槛。若失败先定位，不放宽。

先判validation，不因test翻案。六job、选择锁及训练/来源审计完成后才一次生成新test：stationary/ramp/gust×2.70/3.30/3.90MW×两条轨迹×初态.03/.05=36常规；另7.6/7.8m/s×4.35/4.55MW×.03/.05=8已知压力回归。新validation18场为三风况×2.9/3.5MW×.025/.04/.055。所有控制器同天气/目标/初态/模型/执行器，P/PI冻结不整定。

报告case-RMSE均值与pooled、偏差/标准差分解、各case、三流SD、相对父/同预算对照/P/PI配对差、selected到final、实际/参考控制和饱和。压力单列，保留困难场。只限合成准静态模型数值实验，不是真实风机收益或全局可达性证明。结论区分改善原策略、平均优于PI、各场优于PI。失败也结题，不继续改gamma/去惩罚/换reward，不降门槛或增预算。
