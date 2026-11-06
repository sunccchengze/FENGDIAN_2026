# 桨距Critic回报目标单因素协议（2026-10-28，运行前冻结）

主对话已批准d6b0a9b中的唯一候选及固定预算；不再检验趋势信息，不引入第二项干预。
独立worktree `.`、分支codex/pitch-cross-wind；原项目、父状态、旧实验和共享状态只读，不合并master、不推送。

## 文件职责与保留

`nstep_algorithm.py`仅提供时序回放/多步目标和带恢复元数据的独立算法；原algorithm.py只读。
`pitch_nstep_trial.py`负责冻结来源、生成训练/验证、两臂配对续训、分片恢复及冻结后独立测试。
`pitch_nstep_review.py`负责全量复算、分风况配对、验收和Python科学图；结果写PITCH_NSTEP_RESULTS.md。
实验沿用experiments/YYYYMMDD_简短描述/config.yaml、metrics.csv、summary.txt；本轮目录20261028_pitch_nstep和20261028_pitch_nstep_smoke。
新增文本UTF-8 LF。逐回合128步保存恢复点，每个文件新建不覆盖；权重、轨迹、图像不入Git，不自动清理。
中断最多重算未提交的128步，记录恢复源、已保存步数和未提交尝试；完整分片校验后复用。

## 唯一干预与时序契约

对照n=1与候选n=8；Actor目标、15维观测/64宽网络、reward、采样锚点及RNG、lr、更新数、gamma=.99、tau=.01均相同。
父策略来自20261023_progressive_random_control的三份验证选中pitch状态：流0 step16384、流1 step12288、流2 step8192。
完整继承online/target Actor/Critic、Adam、回放与RNG；固定模型wind12-synthetic-7506554ac981。实际SHA256写入运行config。
只学pitch，mask=[0,1,0]；yaw跟踪风向，speed沿用统一运行曲线；P/PI沿用原冻结参数。

y_i=sum(k=0..m-1,gamma^k*r_(t+k,i))+gamma^m*(1-done)*Q'_i(s_(t+m),pi'(s_(t+m)))。
m=min(n,真正终止前步数,真实连续可用步数)。不跨episode、不从最新槽跳回最旧槽；容量回卷用单调序号识别。
每一相邻对校验next_obs==下一obs及剩余时间递减；所有agents共享环境done，拒绝不同agent的done语义。
最新尾部尚未写入不算终止，以实际m bootstrap；真正终止不bootstrap。奖励使用已存scale100后的值，不重复缩放。
目标动作在s_(t+m)用原policy映射（包括yaw/speed规则）；不使用未来风或功率作为Actor输入。
n=1调用原update/td_target并须精确等价；n=8只通过同一update中的回放目标字段/折扣替换。
保存n、tail_rule、单调序号、实际m直方图；恢复严格核对。行为策略后续奖励带来off-policy偏差，本候选有偏，不称真实Q修复。

## 冻结训练与选模

主seed42；新命名空间SeedSequence([42,20261028,purpose,run_id,...])，purpose=1训练设计、2初态、3探索；回放RNG完整继承。
风生成仍原generate_inflow(seed42,split,episode)；train从31000000+run*1000+episode，validation从32000000，test从33000000，压力33009000。
配置冻结时核查历史已维护协议中的命名空间碰撞；不读取三通道新测试。
训练每9回合三风况stationary/ramp/gust×目标2.6/3.2/3.8MW随机排列，初始pitch均匀[.025,.055]，沿用原采样结构。
两臂各1024步smoke（流0）；通过后正式重新加载三父，不沿用smoke学习结果。
正式2臂×3流×16384=98304新增环境步。warmup512，之后每2步update，batch64/capacity32768，actor_lr1e-4/critic_lr.001。
pitch白噪声std.03线性衰减至.2倍；同一流两臂天气、目标、初态、探索及采样锚点随机状态一致。
验证2.9/3.5MW×三风况×初态.025/.04/.055=18完整128步回合；每4096步验证，以全部回合RMSE均值严格改善选模，initial也参与。
保留initial、selected、final及验证历史/源摘要/种子状态/更新数/m分布；不得因失败追加预算或候选。

## 冻结后的独立测试与验收

六作业完整后冻结selection及全部检查点摘要，才生成/释放一次新test。
常规2.65/3.25/3.95MW×三风况×初态.025/.055×两条轨迹=36场。
压力固定7.6/7.8m/s×4.35/4.55MW×初态.025/.055=8场，单列不计常规总体。
所有initial/selected/final/P/PI共享风况、目标、初态、执行器；不再整定P/PI。
报告完整回合RMSE、bias/std及RMSE²=bias²+variance、配对P/PI/父/同预算差、跨流样本标准差、selected→final退化。
原44场诊断中的已知薄弱与反证保留回归评估，明确是已知训练/验证样本，不称新独立样本，不用于选模。
慢变候选selected相对同预算n1的跨流均值改善≥5%且至少2/3流改善；平稳/阵风逐流回归≤5%；各臂final/selected≤1.25。
同时单列相对父策略慢变改善和initial保留情况；只保留initial不称学习成功，终点未保持不称稳定改进。
区分改善原策略、平均优于PI、所有case稳定优于PI。Q指标不能替代控制验收。
低风可达性仅引用冻结模型内数值路径，不称物理/全局最优证明；全部困难样本保留。

## 必须先通过的验证

原一步update同输入/随机状态参数、Adam、target、损失精确一致；8步奖励/gamma幂/末状态/终止/动作映射显式算例；
ring满/回卷/新写入/缺失尾部/episode隔离；错误连续性或多agent done拒绝；保存恢复下一update精确一致；
真实父恢复及smoke中断恢复精确分叉，验证继承未改变权限和父文件；完整训练/测试轨迹指标与reward/执行器复算。
