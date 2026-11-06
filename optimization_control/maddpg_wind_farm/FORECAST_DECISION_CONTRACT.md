# 预测辅助 MADDPG 的决策与回放方案（2026-10-30，待结构实施审阅）

推荐只在 speed 决策边界训练有界修正，父 pitch 仍每秒反馈。每次 speed 决策保持 8 个物理步，回放记录实际经历的 m 步区间；这是一个宏动作转移，不是把原逐秒 n8 回放直接换个名字。当前只实施私有契约审查，不创建正式网络、优化器或检查点版本。

## 本轮边界、目录与固定核查

沿用当前模块/测试/日期实验目录职责；不新增持续维护目录。私有审查入口 `forecast_decision_contract.py`、测试 `../tests/test_forecast_decision_contract.py`、配置 `configs/forecast_decision_contract.yaml`；本协议和结果文档分开。输出放 `../experiments/20261030_forecast_decision_contract/`，保留 config.yaml、metrics.csv、summary.txt 和小型 JSON 证据。只写新输出，不覆盖旧结果，不自动清理。

三原父与冻结 ridge 预测器只按旧 config 路径及 SHA 引用；不换 pitch 新候选，不复制权重/旧回放。旧 test episode66000000..66000017 封存，不读其逐场结果作结构整定、不重跑198回合、不生成新独立测试。本轮真实 PINN 查询0、正式 RL 步0、参数更新0、forecast 拟合0。所有 mock 输入逐 forward 收费，总上限4096行；新文件总上限256MiB。超过上限在 forward/写入前拒绝，不靠删旧结果腾空间。

运行前固定软件序列：horizon19，t=0..19，U=9+.02t+.06sin(t/3)，direction=.002t，TI=.08，target3.2MW，初始pitch.04；三原父各执行 direct、zero-B、zero-C、随机 speed 四条短回合，各20查询行。随机路径在 t5 和 t8 保存内存快照并各恢复到终点，额外14、11行；另运行 horizon5 的新回合验证reset，6行。因此预计每父111、合计333 mock行。短序列是确定性联调输入，无风况生成器 episode 身份，不是训练/验证/独立测试样本。其他算术、信息、梯度检查不调用 plant。若失败保留证据，不隐性重跑整个套件；修复后新 attempt 单独计费。

## 现有代码与两种选择

`speed_nstep_training.py` 每秒 `act`/step/add，在物理步>=512且偶数步 update；`FrozenSpeedMADDPG.update` 对每条回放 obs 重新生成 speed，`SequenceReplay(n=8)` 只累积最多8条逐秒转移。它们当前没有8秒保持，现有 n8 结果不因这次审查而被重新解释为时序错误。

| 方案 | 必须处理的内容 | 选择 |
|---|---|---|
| 决策边界训练 | 仅t=0,8,16…调用speed；m步回报；下一决策状态 | 推荐，消除保持步Actor梯度入口 |
| 逐秒增强状态 | 每步包含held/phase；phase>0不调用新head；target须执行hold；Actor仅phase0有梯度；Q须与总动作及held一致 | 可以正确实现，但本轮不选，契约和恢复面更大 |

在保持步用 `head(obs_t)` 替换实际 held offset 再求策略梯度，会优化没有执行的动作。即使把 loss 乘零，target若仍提前重选speed也不正确；需要同时约束动作、target和回放。参考 temporal abstraction 的回报框架仅支持持续时间折扣这一原则，本项目的具体时序/维度是工程设计：[Sutton、Precup、Singh 1999](https://people.cs.umass.edu/~barto/courses/cs687/Sutton-Precup-Singh-AIJ99.pdf)。集中Critic、仅替换本agent动作的梯度形式参考[MADDPG原论文](https://papers.neurips.cc/paper_files/paper/2017/file/68a9750337a418a86fe06c1991a1d64c-Paper.pdf)。不据论文保证本模型学习收敛。

## 推荐时序与输入：51维 head、84维 Critic

在观察到 s_t 后，先把这一时刻 wind 加入本回合已观测历史；冻结预测器只接收该前缀，取最近32样本，不足左填首样本。预测h1..12；输入F为相对当前的 `[ΔU/3, Δsin(direction), Δcos(direction)]` 按h排列，共36维，使用预测器已经裁剪/圆周化后的输出。3m/s是固定速度全范围，不拟合新归一化；方向正余弦不再缩放，TI只携带当前观测，不宣称TI预测增益。

每agent speed head 输入 `[o_i(15), F(36)]` 共51维，51→32→1，ReLU/Tanh；输出z_i∈[-1,1]，物理修正δ_i=.1z_i rad/s。在线/目标使用相同输入契约。父Actor保持原15维，固定三原父在线映射在采样与target对应的宏动作执行语义中均相同，不使用有初始滞后的父target映射代表闭环父反馈；原父target原样冻结、仅作来源留档，不做Polyak靠拢。只有新speed target与新Critic target做tau=.01更新。

每秒重新算父动作a_parent(o_s)，仅speed列加2δ/.667后clip[-1,1]。held的是δ，不是总转速命令、实际转速或pitch。机舱朝向由原yaw执行器处理，gamma=wrap(heading-direction)，继续共用原执行器/物理限制。t+1..t+7不调用head、不抽探索噪声、不新增Actor样本；父pitch反馈每秒更新。t+8收齐真实观测与回报后才产生下一预测/决策。

在完整决策边界，phase恒0，旧held会被新δ无条件替换；过去命令已在o的previous_action、执行器状态中体现，因此删除53维提案中的held_i/phase。集中Critic状态 `[flatten(o)(45), F(36)]` 共81维，动作是实际选择并持有的联合z=δ/.1，共3维，合计84。三agent分别84→64→64→1。

**94维提案不直接沿用。** 即使保留9维当前总动作，当前speed clip可能使不同δ在这一秒执行命令完全相同，但随父speed参考变化，后续命令不同；这9维无法唯一描述宏动作。推荐以3维实际held修正作为Critic的动作变量；逐秒9维执行总动作、父总动作与δ同时留在审计轨迹。Critic batch和Actor替换/target均使用联合z，不能拿9维总动作代替它。总动作映射/执行器继续是唯一原实现。这里没有证明 `[o,F]` 是充分Markov状态：forecast是32历史的压缩，学习仍是有限历史/部分观测近似，若后续表现差须保留这一限制。

## 回放、回报、target和终止

一条宏转移的逻辑字段：run/episode身份、decision_t、m、o_start[3,15]、F_start[36]、history_start_SHA、实际z[3]/δ[3]、discounted_return[3]、raw_rewards[m,3]、o_next[3,15]、F_next[36]、history_next_SHA、terminated、bootstrap_discount=gamma^m。审计旁表记录m个逐秒parent_action/command/executed_action、reward_terms、物理轨迹，不用旁表的未来信息作为start输入。B的F_start和F_next明确为“信息消融零”，不标成真实预测；C为当时已观测历史的冻结预测。B/C独立缓冲区、相同字段/容量/抽样算法/初始化种子，不共享随后由不同策略产生的经验。

`R_t = sum(k=0..m-1, gamma^k * r_(t+k))`，其中r_(t+k)是执行第k个物理动作后获得的原环境reward；`y_i = R_i + (1-terminated)*gamma^m*Qtarget_i(S_next, z_target_next)`。正常m=8；真终止发生在不足8步时立即封口，m取实际步数，禁止跨episode，terminal不计算/使用target head，F_next约定为显式terminal占位零、valid=false（不是伪装真实信息）。非terminal边界使用已经观察到的完整前缀重算next F，不能复用start F或直接把start预测后8行当真实next预测。

next target选择的是下一次将真正执行的宏动作。Actor loss仅对宏样本：替换本agent z为当前head输出，其余agent用回放实际z并detach；pitch父反馈不是待优化动作。宏replay的一次TD即“一次决策转移”，不另拼8个宏动作，正式候选的额外n-step horizon=1。控制保持周期8、物理折扣gamma=.99、额外TD展开1是三个不同参数。

行政暂停不等于terminal/truncation。t5暂停必须保留t0未封口区间、累计5步回报/折扣、heldδ、相位5、wind已观测前缀、环境/执行器/previous_action、物理t/全局采样步、pending start特征、RNG/噪声状态；恢复继续3步，到t8才插入回放。不得在t5bootstrap一次后再把t5当新speed决策。正式首版只允许128步回合边界持久恢复；任意中途恢复需工程测试通过并明确版本后才能启用，本轮mock内存恢复不等于完整训练恢复已通过。

## 旧回放与权重/Adam边界

三父旧replay只有obs、actions、rewards、next_obs、terminated；没有原wind前缀、逐条episode身份、F或决策保持δ。时钟/obs中sin/cos和U不能证明从原始float32风序列无损复原32步历史，保留环首还可能缺episode起点。更关键的是旧策略每秒动作，不是固定δ持有8秒的宏动作，不能把它强行拼成此宏回放。

推荐B/C共同采用**新的空宏回放**，只复用冻结父Actor映射与预测器；不导入旧一秒Q/target Q或Adam。一秒Q与本方案8秒后重新决策的Q语义不同，不能仅扩展输入列为零就宣称初始Q保持正确。新B/C Critic和speed heads逐参数配对初始化，head末层全零，targets精确复制；所有新Adam从空状态开始。父四组online/target Actor/Critic及旧优化器只读来源，不迁移。A保留原父的Actor/Critic/target/Adam和旧逐秒回放继续训练，此差异必须披露。

正式实现需独立命名的宏replay/checkpoint schema、显式loader拒绝旧格式、独立Adam shape校验、来源SHA/决策时钟/预测器版本/特征尺度/回放字段/随机状态锁，且须协调方审阅本方案后实施。本轮私有ledger不是正式schema，不写新.pth/.pt，不静默迁移任何状态。

## 唯一下一候选及对照（提案，尚未执行）

| 臂 | 权限与信息 | 初始化/采样/更新 |
|---|---|---|
| A | 原父pitch按同预算续训，yaw/speed原调度 | 原父完整恢复；pitch噪声.03每秒；512物理步后偶数步update，8192步时3841次联合update |
| B | 冻结父pitch + bounded speed，无forecast | 51/84结构，F_start/next均消融零；每8秒决策；新空宏回放 |
| C，唯一候选 | 与B相同，有冻结真实forecast | 与B逐参数初始配对，唯一处理差异是F信息；共同3条42派生流 |

B/C固定半径.1rad/s，无权限ramp；白噪声在z坐标std=.15，按全局物理步k以`1-.8*k/8192`衰减，每个决策只抽一次3向量；执行z=clip(head+noise,-1,1)。初始化接管/评估禁止探索，zero head必须父动作一致；探索产生非零speed是训练采样，不拿来判接管失败。B/C head_lr=1e-4、critic_lr=.001、gamma=.99、tau=.01、clip=1、batch64、macro容量4096，共同empty replay；从64条已闭合宏样本/512物理步开始，每新增2条宏样本update一次，64,66,…1024，共481次联合update/流。A的更新频率/可训练父/replay不同，A比较是同环境交互预算的完整方案比较；不能把B/C对A全部差异归因speed权限。B/C两臂时序/结构/参数量/初始化/RNG派生/抽样/预算完全相同，才用于预测信息增量判断。后续若改变半径/学习率/奖励/额外n-step则另立单因素实验，不在本轮同时调。

三流run0/1/2固定原父，不换父；每臂8192物理步=64个128步回合，9个job总73728训练步，B/C共6144宏样本、2886联合update，A共11523联合update；一次联合update含3个Critic和3个各自Actor/head优化器step，物理步与参数更新分别计数。全局seed42；design entropy[42,20261030,8601]，wind/target/pitch/noise/head/critic/replay按语义namespace+run派生，B/C不把arm标签加入共同随机数种子。

训练只预留episode67000000+run*1000+[0..63]（split=train），stationary/ramp/gust×2.6/3.2/3.8MW平衡打乱，pitch在[.025,.055]逐episode派生；原模型/来流分布/执行器/目标规则不变。验证预留68000000..68000005（split=validation），三族×2.85/3.45MW、pitch.04，共6条，首次正式实施时扫描实际namespace再一次锁定；本轮不生成。未来测试仅预留69000000起的独立空间，候选完全冻结后另定预算/释放，不能复用66000000试验。已知7.6m/s、4.4MW为固定压力回归，不能当新独立样本。

## 正式预算与验收（全部运行前冻结，待实施批准）

训练8192/流，不因结果不好加预算。评估点0/2048/4096/6144/8192，initial/selected/final独立身份，selected按验证case RMSE均值严格改善选取，平手保留更早，包含initial。相对本臂initial的学习改善：三流selected_step均>0且各流均值严格降低、总体至少1%；selected=initial必须记为无新增学习收益。

稳定性与收益分开：每流final/selected≤1.25、selected和final相对冻结父的均值及worst均≤1.05，三流全部满足才称完整工程稳定；final对A同预算final也单列1.05不劣。性能主判断以C selected对A selected、C final对A final分别报告：三流各严格改善、总体≥1%；C对B同样角色作预测信息增量判据，全部通过才称此配置重复改善，不能挑一个角色。三流不当独立物理风数量；以后新test按整条风cluster区间单列。B对A也是完整方案比较，新增speed的贡献还要看同一B/C策略关闭speed后诊断，不用一处饱和单因归因。

接管容差沿用原动作2e-6、实际量1e-6、功率/回合RMSE1W；当前/target head零与组合、无噪声短闭环及保存加载必须分别通过；目前只验证组合/短闭环，正式网络/target/优化器持久恢复尚未实施。物理时钟和forecast因果检查要求精确一致，reward/discount用float64算术核对，再报告float32误差。final-selected退化曲线与实际控制必交；速度命令/实际速度TV、pitch/heading TV、命令变化MSE、边界/限速频率独立报告，不将运动量下降等同跟踪收益。原400kW mean/500kW worst逐流原样报告，不作为新增学习的替代判据。冻结父及统一P/PI是完整控制方案基准，不能称所有差异来自预测或speed。

| 正式阶段查询（reset也计行） | 预定行数 |
|---|---:|
| 9job训练：73728步+576reset | 74304 |
| 9job×5点×6验证case×129 | 34830 |
| 冻结父3×6×129；公共P/PI2×6×129 | 3870 |
| B/C selected/final各关闭speed：6job×2×6×129 | 9288 |
| 压力：9job×2角色+3父+2P/PI，各129 | 2967 |
| 正式小计 | 125259 |
| 新结构工程mock/真实等价验证共同预留 | 4096 |
| 合计预留／硬上限 | 129355／130000 |

以上正式预算不属于本轮授权，不含未来独立test、不额外重跑旧198回合；重复角色/完全相同零策略可按冻结SHA去重并如实少计，不把结余变成新候选预算。正式新增产物提议硬上限256MiB：推理快照只存权重和元数据；每job仅一份可恢复训练state/回放，后续journal按增量，不每评估点重复全回放；所有旧来源路径+SHA引用，无旧模型副本，不删除旧state。正式实施前需测量新state大小、写前预占，不足则停留方案审查，不能隐性增限。

当前可交付的是契约正确性证据和上述单一候选设计；不据短mock或既有搜索器结果宣布MADDPG产生收益，更不开放yaw。当前代理仅为软件实验对象，不外推真实风机表现。
