# speed Critic n1/n8 同预算实验草案——尚未获准启动

日期2026-10-28。本文冻结待审阅设计，不启动正式训练、环境smoke或独立测试。工程正确性见SPEED_NSTEP_ENGINEERING_RESULTS.md；通过工程审计不构成性能支持。

## 当前依据与启动条件

已有speed诊断发现三流终点有限收益被Q反向排序，且存在闭环pitch反馈与奖励补偿；反序不单调，固定final动作时流0旧Critic也有反例，不能认定单一根因。旧speed完整稳定性和可重复收益失败不变。

主对话已核查桨距740d040：n8 selected新慢变397.86 kW、n1为420.54（改善5.39%），但final优势仅1.57%、流2 final相对父回归5.34%，尚无同锚点Q方向复核。该结果不能证明“价值方向与稳定性同时改善”，也不能推定speed迁移成功。

正式启动仍须主对话核对桨距固定预算机制审计及交接清单，并明确决定是否接受当前性能反证继续单项迁移。至少须交付同锚点/同执行动作的有限回报方向、完整稳定性与tracking/动作惩罚分项，不以selected单项通过或本工程loss精确相等替代。若证据不支持，不启动本草案；本轮不无限轮询、也不复制桨距训练。

## 唯一干预与固定起点

两臂都使用完整冻结父Actor＋每机15→32→1独立speed头：控制臂n1，候选n8。只改变Critic TD目标；父target继承并按tau=.01跟随冻结线上父，新目标头正常Polyak。Actor目标仍固定其他机同批回放总动作，网络、Adam、reward、采样、输入15维、所有执行器与物理限制均不变，yaw后台调度且停止新增学习。

三份起点仍为原20261023_progressive_random_control的pitch_run_i/segment_000：

| 流 | 检查点 | SHA256 | 累计插入数 |
|---|---|---|---:|
| 0 | step_00016384.pth | 28e221e6f6e74096ef74e9a9375c638823a055c38232ef4d3b5e16a5026996ea | 32768 |
| 1 | step_00012288.pth | 0fcb0b9d474db0d04b3ac2d86c91d2f39d66bb3c025e30d911ce79b2ba445821 | 28672 |
| 2 | step_00008192.pth | e2897be535e5c9bae27acbecc5edd57460a8a038ba28719e366ab4c904309a05 | 24576 |

不同时换用桨距新n8父策略，不用旧speed selected/final作新起点。两臂从同一父构建完全相同初始网络、target、Critic/Adam、回放、RNG和新头隐藏初始化（沿用head_namespace8405、末层零）；head Adam均空。原Actor优化器不用，Critic优化器完整继承。父回放迁移必须有source SHA、独立lineage/steps计数和全环连续审计，不能默认以size充当全局计数。

## 时序、目标与权限契约

所有已存transition均为同一采样资格，不因n重筛起点、不拒绝短尾、不额外抽样；n1/n8均从同一继承Replay RNG作一次无放回batch64抽样。窗口以单调插入序号识别回卷，true done停止，禁止跨episode；最新缺尾以实际m<=8、gamma^m bootstrap，不冒充terminal。已存共同reward已含scale100，累计一次；未来观测s_t+m只用于Critic训练目标，部署Actor仍只读当前观测。

目标为sum(k=0..m-1,gamma^k*r_t+k)+gamma^m*(1-done)*Q_target(s_t+m,a_target(s_t+m))。目标动作是未来状态的父reference＋目标speed头，总动作送集中Critic，不能使用原始head或历史动作替代。行为策略后续奖励带来off-policy偏差，本方案不加IS/其他修正，不称真实长期Q修复。

沿用observation_float32_v1，使环境、父reference和P/PI统一；所有渠道仍使用原heading执行器，gamma=wrap(heading-direction)。speed范围rho(k)=.02+.08*min(1,k/4096) rad/s；k是当前执行transition前的新增步数，更新沿用刚执行transition时锁存的同一rho(k)，整批所有目标统一使用该当前范围，不按所采样历史窗口重新取范围。验证/测试固定rho=.10。

## 拟预算与数据设计

- 正式拟2臂×3流×8192=49152新增环境步，主seed42；每流64回合、每回合128步。warmup512包含在8192内，收集第512步起每2步更新，共每job3841次update。Actor/head lr1e-4、Critic lr1e-3、gamma=.99、tau=.01、batch64、capacity32768、grad_clip1。
- 不默认增加2048步smoke。本轮有限内存工程副本不继承到正式策略；若另需环境学习smoke，预算须单列获准。正式前初始化一致性评估不是训练，可用新validation逐步核对，并报告评估步数。
- 原训练结构不变：stationary/ramp/gust×2.6/3.2/3.8 MW每九回合共同排列，初始pitch均匀[.025,.055]；同一流两臂天气、目标、初态与完整探索抽样一致。只给speed raw白噪声std=.15，8192步内衰减至.2倍；pitch无新增探索，yaw不学。
- 草案新风况namespace：train41000000+run*1000+episode、validation42000000、test43000000、已知压力43009000；设计/探索派生SeedSequence([42,20261028,8405001,purpose,run,block])。正式冻结前须与当时所有已维护协议再次核对碰撞；本轮不生成或占用这些数据。
- 新validation保持六场：三风况×2.85/3.45 MW，初始pitch=.04。每2048步评估，严格按case RMSE均值选模，initial参与；保存initial/selected/final和全部中间点。run0两臂2048处退出后新进程恢复，包含在预算内，不能为恢复额外续训。

## 分层验收与新独立测试

1. 初始化接管：原v4、n1、n8初始线上/目标总动作差<=2e-6；短闭环实际状态差<=1e-6，功率max/RMSE差<=1 W，无执行器违例。不能用低跟踪误差代替接管。
2. 稳定：final/selected均值<=1.25；final mean/worst相对各自固定父及配对n1均<=1.05，三流全过。工程5%不劣不等于性能改善；固定父必须从新共同比较场景评价。
3. 学习收益：n8三流selected_step>0，selected及final相对同预算n1分别三流严格改善、总体至少1%。1%是效应尺度，不是显著性证明；selected=initial不算学习收益。
4. 精度：initial/selected/final各列mean<=400、worst<=500 kW及通过流数；不替代上述条件。分风况、目标、动作分项、Q方向和selected→final退化保留，不挑最优流。

正式六job完成、全部候选与选择锁冻结后才释放新的test：三风况×2.75/3.35/3.85 MW×初始pitch.025/.055共18常规case；另2个已知7.6 m/s、4.4 MW回归单列，不称新独立样本。所有策略、固定父、统一固定/P/PI方案使用相同来流、目标、初态、参考模式及执行器，不整定P/PI，不用已读旧test选参数或阈值。

旧仅pitch续训和固定父可作历史参照，或在新场景共同评估；不能把旧pitch续训臂替代本次冻结父＋speed的n1控制臂。完整MADDPG与pitch反馈＋yaw/speed调度的P/PI比较仍是完整方案比较；n-step收益主要由本次n1/n8配对判断。未经主对话启动决定，不执行本文任何正式训练或测试释放。
