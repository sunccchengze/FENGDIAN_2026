# 预测辅助 MADDPG 决策/回放契约核查结果（2026-10-30）

**推荐只在8秒决策边界学习speed修正，父pitch继续每秒反馈。** 不直接套用现有逐秒update/n8回放；输入提案从53/94维改为51维speed head、84维宏动作Critic。6项契约测试通过，三原父的零修正接管与短闭环逐位一致；保持、真实短终止、回报和t5/t8内存恢复通过。本轮正式RL步0、参数更新0、真实PINN查询0、新独立测试0；这只是实施前的软件契约证据，不是新增MADDPG学习收益。

## 选择及其必要性

[运行前协议与完整下一阶段方案](FORECAST_DECISION_CONTRACT.md)固定了短case、查询/文件上限、停止边界和预期333行mock。现有 `speed_nstep_training.py` 每秒选动作并存转移，n1/n8算法的区别是回报展开长度；n8并不意味着speed保持8秒。现有实现并未被本轮发现为“历史训练时序错误”。错误风险发生在未来加hold而仍沿用逐秒新head输出/target的组合时。

本次选择只在t0/8/16…调用head、抽噪声和封装一个宏动作；期间每秒从当前观测调用冻结父，固定δ加到当秒父speed参考上，经原动作映射/执行器运行。保持δ不等于保持总命令，pitch、背景speed参考、yaw机舱跟踪仍按当前观测变化。保持步没有新的speed策略输出，因此没有对未执行动作求Actor梯度的入口。

| 对象 | 推荐输入/动作 | 原提案调整理由 |
|---|---|---|
| 父Actor | 原15维观测，三原父映射冻结 | 不加入forecast，不替换pitch父 |
| speed head | 15观测+36预测=51维；输出z，δ=.1z rad/s | 决策边界phase恒0，旧held无条件被替换，删除held_i/phase |
| 集中Critic | 联合观测45+共享预测36+实际联合z 3=84维 | 9维当秒总动作可能因clip混淆不同heldδ，不能代表整个宏动作 |
| 逐秒审计 | 父动作、组合命令、实际执行总动作[3,3]、δ、物理量 | 总动作仍须保存并和执行器对齐；不是丢弃执行语义 |

裁剪反例是确定的：当秒父speed归一化值.95，δ=.05/.10rad/s经组合都clip成1；父参考随后降至.4，两个总speed分别约.549925/.699850，后续闭环不同。仅用当秒9维总动作训练宏Q会丢失这一区别。新Critic以实际z为动作；Actor更新只替换本agent z，其余用回放z并detach；target只在下一个真实决策边界选择新z。

对照的逐秒增强状态方案也能实现正确，但必须把held/phase加入所有current/next、target、动作组合、恢复状态，且phase>0不得提前重选speed。相较之下，决策边界方案需要核查的入口更少。持续时间折扣依据[Sutton、Precup、Singh的原论文](https://people.cs.umass.edu/~barto/courses/cs687/Sutton-Precup-Singh-AIJ99.pdf)，集中式Critic/本agent动作梯度形式参考[MADDPG原论文](https://papers.neurips.cc/paper_files/paper/2017/file/68a9750337a418a86fe06c1991a1d64c-Paper.pdf)；51/84、具体保持周期及迁移选择是本项目的设计判断，不是论文保证。

## 已验证内容、失败记录及查询

| 核查 | 实际证据 | 结论 |
|---|---|---|
| 回报/实际m/终止 | m=1/3/5/8，与独立math.fsum核对；terminal无bootstrap | 通过；不能固定用gamma或gamma^8替代实际gamma^m |
| 保持步策略梯度 | 标量autograd反例；保持7步梯度为0，错误重选输出梯度非0 | 通过；没有建立新网络或执行optimizer.step |
| 宏动作裁剪别名 | 同当秒总命令、不同后续命令 | 确认必须保存实际held修正 |
| forecast因果 | 同观测前缀、不同未来后缀，F逐位相同；推理签名只接history；代码无trajectory/episode/隐状态入口 | 通过；h1..12由已观测历史生成 |
| 历史/next特征 | 不足32左填首样本；只用最近32；next用新增真实观测重算，与start F不同 | 通过；B的零F是显式信息消融 |
| 三原父零接管 | direct、zero-B、zero-C；观测、命令、next_obs、实际量、功率逐位相同 | 三流通过；本轮最大差0，比原容差更严格 |
| 保持/短终止/reset | 19步探索只决策3次，宏长度[8,8,3]；另5步新回合，独立历史/时钟 | 通过；不跨回合；末尾true terminal不是行政暂停 |
| 恢复 | 三父分别t5/t8内存快照，继续到19；状态、数组类型/形状、回报、动作、预测及RNG逐项相同 | 六条恢复通过，错误时钟拒绝 |
| 父来源保护 | 三父online/target Actor/Critic张量摘要、RNG、update计数前后核对 | 未改变；旧模型只按路径+SHA引用 |

forecast仅接收已观测wind前缀，没有未来真实轨迹访问。F由预测器输出相对当前的ΔU/3、Δsin、Δcos形成；不重新拟合、改normalizer或使用family/seed信息。B的current/next F共同置零并显式标记消融；terminal next F采用valid=false的占位零，不当成真实观测。没有证明这些压缩输入足够Markov，仍有部分观测风险。

首轮失败保留在实验根目录：[verification.json](../experiments/20261030_forecast_decision_contract/verification.json)、[tests.txt](../experiments/20261030_forecast_decision_contract/tests.txt)、[budget.json](../experiments/20261030_forecast_decision_contract/budget.json)。其错误是把pickle整段字节相等当作状态相等，run0第一次恢复完成后断言失败，消耗94行。已按原SHA恢复保存[首轮执行源（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，未删记录或把失败改成成功。

修正为状态值/类型逐项精确比较，新attempt_001重新锁源再验证，6项测试全部通过、333行。六条恢复均字段精确相同，但pickle字节均不同，支持“序列化表示差异导致错误判定”，不支持“恢复算法确实发生漂移”的判断。证据见[通过审计（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、[逐scope计费（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、[原父回放审查（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。

累计mock输入94+333=**427/4096行**，真实PINN输入0，参数更新0。首轮中断scope的14行预占全部计入，没有通过标记complete抹去失败。通过后只对新增的重复运行/祖先提交/预算保护代码做无plant核查，未再跑333行序列；通过时的执行源另保存[executed_review_source.py（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，其余契约函数与最终提交AST一致，差异仅prepare/audit中的运行保护。见[后续保护核查](../experiments/20261030_forecast_decision_contract/post_run_guard_review.json)。

测试入口随后明确区分普通发现与有预算的集成核查：普通unittest只运行四项无plant断言，已全部通过；audit注入冻结父/预测器/预算后运行完整六项。六个原测试方法AST未变、无skip或吞掉失败；通过时的[测试源（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)按原SHA保留。新增load_tests只控制集成fixture的明确入口，不增加查询；见[普通发现日志](../experiments/20261030_forecast_decision_contract/standalone_tests.txt)。

所有原执行模块、三原父、预测器、旧test释放/完成记录、旧863.95秒异常保护文件及两个工作区状态入口的SHA前后核对；未重跑旧198回合、未新增test、未覆盖共享PROJECT_STATUS/TASKFLOW/README。磁盘上限256MiB，最终新文件大小和逐文件SHA见[交付清单](../experiments/20261030_forecast_decision_contract/output_manifest.csv)及[交付审计](../experiments/20261030_forecast_decision_contract/delivery_verification.json)。未复制模型/旧回放、未删除任何文件。

## 回放与恢复仍须正式实施的部分

三父保留回放分别32768/28672/24576条，三者最早保留obs剩余时钟均为1；本轮没有发现实际环首丢失回合前缀，不能把“可能缺前缀”说成已观察到的事实。字段只有obs/actions/rewards/next_obs/terminated，没有逐条episode身份、原始wind历史/F/heldδ。部分历史可能从外部原始manifest重建，但本轮未证明完整逐条来源映射与float32方向无损恢复。

即便能补齐forecast，旧回放仍来自逐秒策略和训练中变化的父Actor，不是当前固定父下保持δ八秒的宏动作转移，不能直接拼8条伪装相同数据。B/C共同新建空宏回放，字段、容量、初始化和采样完全配对；这不叫旧训练无损恢复。A继续原父完整状态/旧逐秒回放，用作同交互预算完整方案对照。

旧一秒Critic的54维权重和Adam不迁入新84维宏Critic；Q的未来策略/动作持续时间语义也变化，补零输入列不能保持正确宏Q。B/C各agent拟议head为51→32→1（1697参数）、Critic84→64→64→1（9665参数），三个agent新增在线可训练参数34086，target另34086；B/C分配结构和参数量相同。head末层全零、target精确复制；新Critic同种子逐参数配对，新Adam空状态。B的forecast列无输入变化、对应权重缺乏信息梯度是消融本身，不伪称两臂有效信息维数相同。

正式target宏动作也必须使用同一个冻结父在线映射；继承父target的初始滞后不能替代实际闭环父。原父target仍原样保留且不更新，只有新head/新Critic target做Polyak。上述是待审阅设计，**本轮没有创建正式51/84结构，没有验证其target/优化器/磁盘checkpoint恢复**。内存mock恢复通过不能升级为完整训练恢复已通过。

正式首版只允许128步回合边界持久恢复；必须保存全局物理步、episode索引、采样/探索/回放RNG、宏replay、网络/Adam/update数、选模历史与父/forecast SHA。若以后支持t5恢复，必须再纳入pending区间、部分回报/折扣、held/phase、观测前缀、环境/执行器和previous_action，按本轮契约逐项验证；行政暂停不得冒充真terminal或新决策。

## 唯一正式候选、预算和验收提案

唯一候选C为“冻结原父+每8秒bounded speed+冻结forecast”，B是完全相同结构/时序的零forecast消融，A是原父同预算pitch续训。B/C固定半径.1rad/s、奖励/执行器不变、无额外n-step累积；head_lr1e-4、critic_lr.001、gamma.99、tau.01、batch64、clip1、宏replay容量4096。只选择这个候选，不继续比较53/94结构或另一种逐秒方案，不开放yaw。

为消除种子描述歧义，后续正式实施固定：`seed_for(42,8601,run)`初始化B/C各自同种子的head，8602用于Critic，8603用于macro replay；noise用`SeedSequence([42,20261030,8604,run])`，A的pitch噪声用8605替换8604。`seed_for`沿用现有benchmark的SeedSequence定义；B/C seed均不加arm标签。目标/族排列每9回合覆盖三族×三目标，用`SeedSequence([42,20261030,8601,1,run,block])`打乱；64回合为7整轮+最后1场。pitch用`SeedSequence([42,20261030,8601,2,run,episode])`在[.025,.055]取样。风按原生成器seed42、split及新episode身份生成，同一run的A/B/C共用相同风/目标/初始pitch。

B/C探索为z坐标白噪声std.15，按决策前已完成物理步k乘`1-.8*k/8192`，只在决策边界抽一次3向量；初始化接管/评估完全无噪声。父pitch不加探索。A原pitch噪声std.03按相同物理进度衰减，每秒取样。B/C从第64个闭合宏样本起，每新增2个宏样本更新一次，共481次联合update/流；A沿用512物理步后偶数步update，共3841次/流。A与B/C的可训练范围、回放和更新时序不同，A比较不能把全部差异归因新增speed；预测增量主要由配对B/C判断，speed贡献还需同策略关闭speed诊断。

| 预算 | 精确值 |
|---|---:|
| 三臂×三流×8192物理训练步 | 73728 |
| B/C宏转移总数；联合update总数 | 6144；2886 |
| A联合update总数 | 11523 |
| 训练查询含576reset | 74304 |
| 五个评估点×九job×六validation×129 | 34830 |
| 冻结三父+公共P/PI验证 | 3870 |
| B/C selected/final关闭speed诊断 | 9288 |
| 已知压力独立报告 | 2967 |
| 正式查询小计+新结构工程预留 | 125259+4096=129355 |
| 提议查询硬上限；文件硬上限 | 130000行；256MiB |

这里的联合update每次含三个Critic和三个对应Actor/head的optimizer step，不能和物理步混为一谈。新结构工程预留包括mock和真实PINN行，未来独立test不在该预算内。本轮未执行其中任何训练/工程参数更新。不得把本轮mock427行算成未来额外训练额度，也不得用角色去重节省的查询追加候选。

train只预留67000000+run×1000+[0..63]，validation预留68000000..68000005，未来test预留69000000起；均未生成、尚须正式释放前查实际冲突。原66000000..66000017完全封存。新validation仍三族×2.85/3.45MW、pitch.04；原训练目标2.6/3.2/3.8MW与来流分布不变。旧7.6m/s、4.4MW只作已知压力回归，不并入普通场景均值或称新测试。

工程与收益分别冻结：

- 接管：零头/无探索，动作≤2e-6、实际量≤1e-6、功率/回合RMSE≤1W；真实时钟、因果前缀、动作字段、折扣/终止与恢复须一致。正式current/target、回放和Adam持久恢复仍需新工程验收。
- 选模与新增学习：只用新validation；0/2048/4096/6144/8192评估，严格改善才替换selected，平手保留更早，保存initial/selected/final。三流selected_step均>0、各流selected严格改善本臂initial且总体≥1%，才有重复学习改善；selected=initial直接记为无新增学习收益。
- 稳定性：每流final/selected≤1.25，selected和final相对冻结父的mean及worst≤1.05；final对A final的1.05不劣另列。工程容差不是性能改善。
- 性能：C selected对A selected、C final对A final分开，均要求三流严格改善、总体≥1%；C对B对应角色同样要求，完整通过才称此配置重复改善。B对A及P/PI均属完整方案比较，附固定父和关闭speed诊断。预测误差下降不替代功率闭环收益。
- 原精度与代价：400kW mean/500kW worst逐流独立报告；运动TV、命令变化MSE、饱和/限速频率与压力单列；不因某通道饱和认定唯一原因。正式后期退化曲线/实际控制轨迹仍须交付，本轮不绘制不存在的训练曲线。

## 复核与实施边界

[私有入口](forecast_decision_contract.py)、[六项测试](../tests/test_forecast_decision_contract.py)、[固定配置](configs/forecast_decision_contract.yaml)、[汇总metrics](../experiments/20261030_forecast_decision_contract/metrics.csv)、[summary](../experiments/20261030_forecast_decision_contract/summary.txt)。根config是首轮原锁，保留其旧源SHA；通过attempt的config/run_lock和两份执行源分别保存，避免把失败和修复后的执行混成一次成功。

只读复核读取verification/budget/source_guard及清单即可，不触发PINN或RL；逐区间动作/回报/forecast存在attempt_001的run0/1/2_intervals.json。需要完整重现短mock时必须获得独立查询额度、使用新目录并按相同配置执行，不能对现有attempt重新audit：

```powershell
# 在本隔离工作树或包含本提交的独立副本，输出必须是尚不存在的新实验目录。
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.forecast_decision_contract prepare --output optimization_control/experiments/YYYYMMDD_contract_reproduction
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.forecast_decision_contract audit --output optimization_control/experiments/YYYYMMDD_contract_reproduction
```

本轮完成了实施前核查和可执行设计；正式51/84网络、宏回放/checkpoint版本、Adam初始化及新训练方案均等协调方审阅后再实施。没有替换父、引入队友pitch新候选、修改队友代理或启动yaw。既有搜索器均值收益和本轮契约通过都不构成MADDPG学习成功；仍以当前代理模型内逐通道、多流、同预算学习证据为后续目标。
