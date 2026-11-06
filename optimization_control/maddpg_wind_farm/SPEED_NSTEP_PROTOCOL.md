# speed n1/n8 固定预算协议（2026-10-29）

## 新启动决定与边界

主对话在读取 c3e9cc0 工程交付及桨距 dd6f400 机制报告后，明确接受现有性能反证，授权一次可证伪的 speed n1/n8 单因素对照。此决定是新的前瞻实验授权，不表示旧“价值方向与稳定性同时改善”条件通过。2026-10-28 的草案、停止结论和失败结果保持原文。桨距 selected 的局部正面证据、speed 自身可改善却被 Q 反排的动作及已通过工程等价性，支持直接检验；不能预先认定迁移有效或无效。

保持现有独立工作树和分支，不合并 master、不推送、不改原模型/历史实验/共享状态。目录沿用现行职责：speed_nstep_training.py 负责冻结、接管、逐回合保存/新进程恢复、选模和测试；speed_nstep_audit.py 负责保存产物复算、有限 validation 方向核查和少量 Python 图；configs/speed_nstep.yaml 保存固定协议参数；tests/test_speed_nstep_training.py 保存入口契约测试。新实验为 experiments/20261029_speed_nstep_control，config.yaml、metrics.csv、summary.txt 入 Git，其余检查点/轨迹/锁/清单/图按现行忽略规则本地保留，不删除失败或中断产物。

## 唯一变量、父状态与预算

两臂均为原三父 Actor 完整冻结＋独立 speed 头：n1 对 n8，仅 Critic TD 目标不同。原父仍是 20261023_progressive_random_control 三流 segment_000 的 16384/12288/8192 步检查点，SHA 和累计插入数 32768/28672/24576 与 c3e9cc0 草案一致；不使用新 n8 桨距父或旧 speed 权重。保留原 Critic/target/Adam/回放和 RNG，新头 seed_for(42,8405,run)、末层零、head Adam 空；父 target 继承滞后并按 tau=.01 跟随冻结父，不新增父约束或目标。

正式新增环境步唯一预算为 2×3×8192=49152；每 job 64×128 步，warmup512 包含预算内，第512步起每2步更新，共3841次。Actor/head lr1e-4、Critic lr1e-3、gamma=.99、tau=.01、batch64、capacity32768、grad_clip1、reward_scale100、动作变化权重.001不变。speed raw 白噪声std=.15、尾比.2；pitch/yaw 无新探索或训练，统一原执行器及限制。没有额外环境学习 smoke；已有39次丢弃工程更新不计入正式策略或预算。每回合保存完整状态；run0两臂在2048退出后由新进程恢复，包含8192内。未保存重算由持久 attempt 台账记录，不能冒称零重算。

## 连续窗口与 radius

复用 c3e9cc0 已验证的严格序列适配，缺独立迁移证据拒绝。所有存储起点同资格、同一次无放回 RNG 抽样，不过滤不足8步窗口；真实 done 不 bootstrap，最新缺尾以实际 m 和 gamma^m bootstrap，不跨 episode。共同 reward 已含scale，只累计一次。回放动作是三机执行总指令，未来 Critic 联合动作是末状态 target 父 reference＋target speed 头。rho(k)=.02+.08min(1,k/4096) rad/s，k为本 transition 执行前新增步数；本次 update 整批使用该当前 rho，不按历史窗口重算。eval 固定.10。多步回报仍有行为策略 off-policy 偏差，无 IS 或其他更改。

## 冻结、独立审查与接管

先固定本协议/config、实际执行源码与模型/父 SHA，检查新 namespace，再做零头一致性 gate；复用原工程证据，不重跑全部39次。正式学习前必须读取另一工作树 SPEED_NSTEP_INDEPENDENT_REVIEW.md 并记录确切内容/SHA及审查覆盖的代码身份。没有阻断性实现/公平性问题即可按这次授权启动；审查不证明性能有效，不再将此误作性能门槛。有实质问题先普通修复、针对验证、保存旧冻结记录并重新冻结。若报告尚缺，完成准备和最小 gate 后报告等待点，不无限轮询。

初始化门槛：原父/v4零头/n1/n8的online/target动作差<=2e-6；新 validation 六场闭环实际状态差<=1e-6，功率最大差与RMSE差<=1 W，执行器无违例。 gate 是评估，不更新网络；评估步数单列，不代替学习验收。

## 数据、选模和分层验收

沿用草案新 namespace：train41000000+run*1000+episode、validation42000000+family*100+target_index、test43000000+family*100+target_index、已知压力43009000。设计/探索为SeedSequence([42,20261028,8405001,purpose,run,block])；purpose分别1=九组合排列、2=初始pitch、3=探索。每九回合覆盖stationary/ramp/gust×2.6/3.2/3.8 MW，初始pitch均匀[.025,.055]；两臂同流完整天气、目标、初态和探索抽样一致。准备时检查当前两工作树维护协议/配置的命名空间记录并保留检索清单。

新validation六场：三风况×2.85/3.45 MW，初始pitch=.04；2048/4096/6144/8192评估，initial参与，严格按六场RMSE均值改善选模。保存initial/selected/final和所有回合检查点，选模不读test。冻结父、fixed/P/PI在相同新validation和test共同评估，无新整定。

1. 稳定性：final/selected均值<=1.25；final mean/worst相对固定父和配对n1均<=1.05，逐流及三流全过分别报告。5%是工程不劣，不是改善。
2. n8相对同预算n1：三流selected_step>0，selected与final各自三流严格改善、总体至少1%；1%不是显著性证明。selected=initial不算新学习。
3. 相对冻结父：selected/final的mean/worst比值及逐流改善独立列出，不把固定父当同预算续训控制臂。没有同预算pitch续训，不能称新增speed权限因果收益已证明。
4. 精度：initial/selected/final分别列mean<=400、worst<=500 kW及通过流数，不替代接管、稳定和收益条件。不挑流、不删失败。

六job完成、选模/检查点锁及核心审计冻结后，一次生成并释放新独立test：三风况×2.75/3.35/3.85 MW×初始pitch.025/.055，共18常规case；另2个已知7.6 m/s、4.4 MW压力回归单列。两臂initial/selected/final、各流固定父与zero-speed selected/final、统一fixed/P/PI同场比较；零修正是部署消融，不是续训。完整控制方案比较不能代替逐通道因果判断。已读旧测试不选新配置或阈值，测试失败不追加预算。

## 有限方向核查与交付

主要结论来自完整回合配对表现和能力保留。仅追加预声明validation方向检查：每流固定父在ramp高目标case的t64公共锚点，首步speed共同±.05 rad/s或0，经原执行器，之后固定父延续32步。n1/n8 initial/selected/final六组Critic评价同一状态和完整联合动作；实际G单独列tracking和动作惩罚，三机Q及均值保留。最多3×(64+3×32)=480评估步，缓存同流公共分支，不扩网格/锚点/风况，不据此再选模或改候选。

交付逐流表、接管记录、selected→final退化曲线、实际控制轨迹、有限Q方向表、模型/源/运行/检查点SHA和复现说明；少量图用Python绘制并查看。所有结论仅限当前合成代理模型的软件实验。候选无收益则形成否定结论，不自动下一算法。
