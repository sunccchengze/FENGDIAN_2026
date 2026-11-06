# MADDPG两任务阶段交接索引（2026-10-29）

**2026-10-30更新：Actor队友条件98304步对照完整验收失败；后续冻结n8＋积分的RL0开发诊断通过筛查，下一误差记忆学习方案仅待审阅。原n8候选保留，纯MADDPG三流终点稳定性与各场优PI目标仍未解决。yaw继续等待模型响应复核。**
speed n1/n8单因素49152步对照已在`7ad33692591ec458e8995e1dbfb75b11522e57d7`完成，预声明可重复收益未通过，validation完整稳定性仍2/3；后续9/17点网格诊断`1a7221a3bcbceb351b5555111c1a58a687bdf1f6`亦未通过可重复收益。协调侧另提供speed历史17点方案的正向开发证据及继续独立测试的状态，这不是MADDPG新增学习收益。本侧gamma单因素98304步对照在`eef2a131e66e23b051bd1d148867d5402caec5a4`完整验收失败；剩余失败RL0核查在`99a48037ff0a39322fbb3df1117088b2b810e63e`形成后续获批方案，现按新报告完成而非仍待实施。不合并两边代码、不改变默认策略或父来源，也不替代原PROJECT_STATUS/TASKFLOW实时看板。

## 模型、环境和结论边界

冻结三机模型为`wind12-synthetic-7506554ac981`：

- 模型绝对路径：[trained.keras（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。
- SHA256：`7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`。
- 来源：[2026-10-22联调报告](WIND_PINN_INTEGRATION.md)。沿用队友`pinn/2026_1021`结构，在只读来源上建立合成标签联调副本，冻结原主干，仅拟合新增连接参数；不是团队交付了经过物理验收的可控动力学模型。
- 外部SI输入顺序`[U,theta,TI,gamma1..3,beta1..3,omega1..3]`，桥接到队友逐机交错顺序；输出`[P1..3,Ueff1..3]`，单位W、m/s。风向是flow-to，从+x逆时针；机舱执行器产生heading，实际失配角`gamma=wrap(heading-theta)`。
- 演示布局`[[0,0,90],[378,0,90],[756,0,90]] m`，各机5MW；均非队友物理标定。域为U 7.5–10.5m/s、theta ±.15rad圆周等价、TI .02–.15、gamma ±.4rad、pitch 0–.22rad、speed .6–1.267rad/s。
- Plant为准静态合成代理，时间响应含优化侧统一执行器；没有真实风机、高保真流场或全局可达性证书。有限扰动和数值扫描仅说明当前模型内响应，不证明全局最优或物理可信度。

各实验均用三机[3,15]观测和[3,3]归一化**总目标指令**，执行器实际量与命令分开。旧pitch使用`legacy_physical`参考模式；新speed显式用`observation_float32_v1`统一策略/环境/P/PI的参考运算，旧模式仍保留。
speed模式修复了严格零头接管中的2W级数值投影差，没有用它解释几十kW学习退化，也没有放宽1W门槛。统一集成须绑定各自清单的环境/参考模式，不能只凭模型SHA相同就混用配置或横比不同测试均值。

## 固定父来源和加载契约

两任务原父均是原项目`optimization_control/experiments/20261023_progressive_random_control/pitch_run_N/segment_000/`的validation选中状态，不来自旧test挑选：

| 流 | 父文件 | 累计采样/插入数 | SHA256 |
|---|---|---:|---|
| 0 | step_00016384.pth | 32768 | 28e221e6f6e74096ef74e9a9375c638823a055c38232ef4d3b5e16a5026996ea |
| 1 | step_00012288.pth | 28672 | 0fcb0b9d474db0d04b3ac2d86c91d2f39d66bb3c025e30d911ce79b2ba445821 |
| 2 | step_00008192.pth | 24576 | e2897be535e5c9bae27acbecc5edd57460a8a038ba28719e366ab4c904309a05 |

主seed42，三条明确派生流；起点累计预算不同，不能把三流差异全归因于本轮随机性。新实验在各流内同起点/预算配对。
P/PI沿用kp1.5、ki.08、pitch_bias.04rad、antiwindup.2、integral_limit.3，不借test重新整定。

| 保存格式 | 正确加载入口 | 权限/用途 |
|---|---|---|
| version=1 | algorithm.MADDPG.load | 原pitch父；mask[0,1,0]、yaw/speed后台调度 |
| pitch_nstep_v1 | nstep_algorithm.NStepMADDPG.load(expected_n=8)，优先用清单校验loader | pitch n8实验候选，仍不开放speed/yaw学习 |
| pitch_actor_context_v1 | pitch_actor_context_algorithm.PitchActorContextMADDPG.load(path, expected_arm='replay'或'current_pitch') | Actor队友pitch条件对照的新私有格式；完整验收失败，不升级默认 |
| version=4 | frozen_speed_algorithm.FrozenSpeedMADDPG.load | 原冻结父映射+独立speed头 |
| frozen_speed_nstep_v1 | speed_nstep_algorithm.FrozenSpeedNStepMADDPG.load(expected_n=1或8) | 当前speed单因素实验显式新格式 |
| version=3 anchor | anchor_algorithm.load_policy | 已收尾的动作约束历史，不是本轮speed起点 |

不得用权重文件名猜版本，不把普通MADDPG/v4通用分派当新格式兼容器。完整恢复须带online/target、对应Adam、回放时序、RNG、外部探索状态和环境归一化；retained size不等于累计训练步数。回放动作仍是执行总指令，不可误当raw head输出或实际转速。

## pitch：候选可交接，终点和机制限制保留

最新完整学习实验提交`740d04044e6b046dfe6256bfa3c2d4ef88925783`：唯一改变Critic一步/最多8步目标，2×3×16384=98304正式新增步。
机制/交接提交`dd6f40072a19005c630f106944e540a5cfe6c2a9`：正式训练0，评估44928步，未重抽test。

新独立测试的case RMSE均值，单位kW；下面同一行/列只在本pitch实验的共同测试中比较：

| 范围 | 父/initial | n1 selected | n1 final | n8 selected | n8 final |
|---|---:|---:|---:|---:|---:|
| 常规36场 | 433.40 | 431.52 | 435.86 | 419.92 | 422.47 |
| 慢变 | 424.56 | 420.54 | 411.49 | 397.86 | 405.03 |

n8 selected慢变相对n1改善5.39%、相对父6.29%，两项2/3流改善，原selected验收通过；三流selected均非initial，步数16384/12288/4096。
final慢变相对n1只剩1.57%。流2final相对父常规+5.34%、慢变+6.02%、阵风+8.17%，不能宣称全流稳定或保住全部能力。
case均值与pooled都保留：慢变pooled相对n1改善3.93%；含压力全44场的selected case均值615.75优于PI657.03，但pooled752.15差于PI738.72。压力24/24槽位差于P/PI。

公共锚点、相同动作与延续下，selected的32步反向计数n1→n8为140→127（父延续）或131→117（n8 selected延续）；流2反而增加，同预算final又有混合结果。
有限G不是长期期望Q，行为策略多步奖励仍有off-policy偏差。没有认定真实Q修复。本轮[奖励一致性审计](PITCH_REWARD_ALIGNMENT_RESULTS.md)已完成：复用既存train/validation完整轨迹，补齐6912评估步（上限10000）、正式RL0；常规验证固定修正725对奖励/RMSE反向，254对动作引入、471对折扣反向保留，另有74对被动作修复。不能认定动作惩罚唯一根因。
[3b4acc9的gamma=.99/1方案](PITCH_REWARD_ALIGNMENT_CANDIDATE.md)随后获得明确批准，现已按[PITCH_GAMMA_PROTOCOL.md](PITCH_GAMMA_PROTOCOL.md)完成，[完整结果](PITCH_GAMMA_RESULTS.md)：两臂n8、原reward/.001动作项/三父不变，98304学习步、47622新增update、774检查点；验证及测试评估152576步（低于186368上限），其中一次新test78848。8次工程核验update不进入正式训练，10个worker正常退出，流0首128/4096恢复均在预算内，无重算。

gamma1 selected为8192/4096/0，新增选中点2/3。慢变validation selected比.99差1.43%、0/3流改善，final好1.21%、2/3；新test对应差2.45%、0/3及好1.03%、2/3，均未达到5%门槛。validation终点稳定性子条件3/3、新test2/3，但其他风况能力保留和实际运动代价均失败，不能将子条件称完整通过。新test流0 selected慢变实际行程/RMS速率对照比1.2301/1.1368。

新test case-RMSE均值kW：父常规418.12；.99 selected/final399.54/411.02，gamma1 402.71/411.40，PI479.34。含已知压力全44场为父624.67、.99 590.28/593.64、gamma1 591.72/594.18、PI632.39；压力gamma1 1442.28/1416.71仍差于P/PI1321.09。全44场selected case均值gamma1比.99差，pooled725.48却略好于726.87，两口径并列，未借test翻案。平均优PI不证明gamma新增收益，压力24/24槽位失败，不能称各场稳定优PI。

图、三流SD、相对父/对照/P/PI的配对差、实际控制/完整时序、目标初态分组和复现命令见新报告。没有升级默认、追加候选、改PINN或yaw/speed权限；原已交接n8候选与旧报告保持历史口径。

2026-10-29追加[固定n8剩余失败核查](PITCH_REMAINING_FAILURE_RESULTS.md)：正式RL/优化器/模型推进均0，新test0；只复用原n8的训练/常规validation，不按test拼父，不采用gamma实验的.99 selected。固定原n8 selected16384/12288/4096，36开发case×三流108槽位中11处弱于冻结PI；3.8MW、均值8.597m/s平稳同波形两初态共6槽位三流全部失败，10/11失败由更大bias²而更小variance伴随，另有启动方差反例。低风压力即使split写validation也按family排除候选选择，仅保留原已发表结论。

流2开发回归selected/final在29/36和32/36场弱于自身initial；另一18场选模validation final相对selected+10.02kW，不能以总体或选中点遮盖遗忘。离线回放/实际参数梯度当时支持一个[待审阅单因素方案](PITCH_REMAINING_FAILURE_CANDIDATE.md)：Actor损失只把队友pitch由回放动作改成同update入口缓存的当前动作且detach，其他通道保持回放；网络/15维观测、n8、gamma=.99、reward、LR及采样不变。原MADDPG设计允许回放队友动作，故不是已认定bug或真实Q修复。该RL0核查当时未实现/训练候选，提出98304学习步和278528评估推进预算；之后获批执行，结果如下，原各风况/多流稳定优PI目标不降低。

### 2026-10-30：Actor条件单因素完成，新增收益未通过

见[PITCH_ACTOR_CONTEXT_RESULTS.md](PITCH_ACTOR_CONTEXT_RESULTS.md)与[批准协议及存储修订](PITCH_ACTOR_CONTEXT_PROTOCOL.md)。两臂都继承原n8 validation-selected16384/12288/4096，不用gamma对照的.99 selected；唯一改变Actor队友pitch条件，网络/观测/奖励/n8/gamma=.99/LR/采样不变。98304正式步、47622新增update全部完成，工程8次内存更新单列；217088评估推进（含一次新test78848）、实际Plant输入317856（含reset），无恢复重算。

候选selected步4096/0/8192，流1保留initial。已知3.8MW平稳两初态selected对同预算原更新差2.18%、对父好1.37%，final分别好0.55%/2.81%，均未达5%；selected改善流0/3或1/3。新validation流0final慢变比原更新差13.24%，流1final实际慢变行程比1.1254，流2终点能力保留失败。

新test case-RMSE均值kW：父常规446.78，原更新selected/final444.07/454.58，候选447.74/451.33，PI525.90；慢变对应父518.90、原更新514.93/525.65、候选520.03/519.10、PI608.88。候选selected慢变差0.99%，final好1.25%但仍略差于父。常规selected/final优PI槽位78/108、81/108，压力两角色均0/24；全44场case均值640.96/641.16优于PI670.48，但pooled770.60/766.29差于PI750.74。不能把平均优PI或相对退化对照的final收益说成干预成功、各场稳定优PI。

已知回归/新validation/新test的能力保留、PI失败数、完整final稳定性均失败；实际硬幅值/速率均通过，新test运动代价通过也不覆盖validation失败。104正式全状态+1工程状态，774轻量commit不冒充恢复权重；initial/selected/final只引用，不复制。全实验约2.04GiB，严格低于3GiB，最终精确字节及分类见实验storage_stats.json。85项冻结来源与11项分析源码不变，1696完整回合独立复算RMSE差0W，图已查看。失败不换候选或预算、不默认升级、不删除历史，不把speed历史预测开发收益计入MADDPG。

新[实验清单](../experiments/20261029_pitch_actor_context/policy_manifest.json)和[归一化契约](../experiments/20261029_pitch_actor_context/normalization.json)仅作研究复现。原n8 selected曾通过原慢变门槛及流2final失败继续保留，未被此新试验替换。

### 2026-10-30：冻结n8＋积分的因果可行性诊断通过开发筛查

协调方核对`5d34e612580e64092a96b40f5b8509926baf771c`失败后授权本轮[协议](PITCH_INTEGRAL_DIAGNOSTIC_PROTOCOL.md)，[完整结果](PITCH_INTEGRAL_DIAGNOSTIC_RESULTS.md)。固定原n8三份selected，不使用Actor/gamma新selected/final；只在父当前pitch目标上共同叠加±.02rad积分，ki/误差单位及一拍时序从原PI代码核对，条件积分抗饱和。正式训练/优化器更新/新test均0，不称纯MADDPG学习。

54个已登记开发槽位对应21条波形（36旧开发＋18Actor validation）；270父/P/PI指标引用原initial/公共基线并复算，新跑162个混合回合与3个零修正核验。实际新增输入21285（含reset），mock0，低于60000上限；没有权重/回放副本，无失败重跑，输出低于512MiB。

主3.8MW平稳两初态均值513.09→481.62kW（-6.13%），三流分别-5.45%/-8.67%/-3.97%，3/3改善。其他开发/validation逐流逐风况能力保留、弱PI数、实际TV/RMS和硬约束均通过；全54槽位均值367.66→360.41kW，慢变338.91→329.52。弱PI11/162→6/162，但主组6/6仍弱PI423.01kW；115场改善、47场退化，最大逐场约+2.06%，不称完全无损或各场稳定优PI。未复评压力/旧test，原纯策略与压力失败历史保持。

4项单元测试、三父零修正完整时序差0、432个回合独立指标/运动复算、20736步积分时序核验通过，122冻结来源不变。混合诊断提供因果修正空间，不能独立分离手工控制律与记忆信息的贡献；不据此认定Critic根因解决。

唯一下一[PITCH_ERROR_MEMORY_CANDIDATE.md](PITCH_ERROR_MEMORY_CANDIDATE.md)提案：同一零初始化私有Actor/Critic记忆支路，恒0对照因果积分标量，不向桨距直接加积分；保留原15维公共环境/原n8参数和旧Adam/回放。只读证明三父回放256/256/224个完整128步回合可供因果历史构造，未构造新特征或网络。因涉及网络/私有数据格式，等审阅确认，未开展下一训练；不默认切换混合控制。

可靠交接直接引用以下已锁定材料，不重复打包或重跑54场：

- [三份候选清单：绝对路径/SHA/来源/恢复契约](../experiments/20261028_pitch_nstep_mechanism/candidate_manifest.json)
- [固定物理归一化](../experiments/20261028_pitch_nstep_mechanism/candidate_normalization.json)
- [三候选×18场新进程验证回放证明（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)：完整时序及指标最大差0。
- [学习结果/可复现命令](PITCH_NSTEP_RESULTS.md)、[机制与交接限制](PITCH_NSTEP_MECHANISM_RESULTS.md)。

候选身份是experimental_candidates_not_default。当前speed新实验继续使用原三父，**没有换成这三份pitch n8候选**。

## speed：严格接管已过，稳定和学习收益未全过

`eaacdef`的原冻结父+speed实验：online/target全回放及6场零头闭环动作差0、状态差0、功率max/RMSE差0，三流严格接管通过。
同预算对照是“可训练pitch续训”，候选是“冻结父完整映射+独立speed头”；两者不仅权限不同，所以相对对照的全部收益不能归为新增speed维度。
新routine18场及已知压力2场的case RMSE均值，单位kW，来自该speed实验，不能直接和上面的pitch36场横比：

| 方案 | 父/initial | selected | final |
|---|---:|---:|---:|
| 冻结父参照 | 365.60 | — | — |
| 原同预算pitch续训 | 365.60 | 366.01 | 409.72 |
| 冻结父+speed | 365.60 | 355.08 | 367.43 |

候选validation完整稳定性2/3，通过接管但整体稳定/可重复学习收益未通过；流0 selected仍initial。
speed final相对同预算pitch续训好，但相对父365.60变367.43，约+0.50%，不能据此认定新增收益。已知压力final1712.00，差于父1607.95和P/PI1383.30。
selected/final zero-speed消融共15360行完整时序逐位回到冻结父；冻结的是映射权重，不是pitch闭环轨迹，speed改变观测仍会经父pitch映射反馈。

`6b7314a`的零训练诊断保留：终点有有益动作被Q反排，但反序不单调，缩radius对流1有损，离线父世界未来pitch重放不可部署，不能据此归为一个根因或用未来信息控制。
`c3e9cc0`已完成n1/n8严格工程适配：n1与原更新精确等价、实际m/终止/总动作/当前radius及恢复通过；39次内存工程更新全丢弃，不是正式学习。

- [冻结父+speed完整报告](FROZEN_SPEED_RESULTS.md)
- [价值方向/反馈/边界诊断](SPEED_VALUE_RESULTS.md)
- [c3e9cc0工程核查](SPEED_NSTEP_ENGINEERING_RESULTS.md)
- [本侧独立审查，核心范围无阻断项](SPEED_NSTEP_INDEPENDENT_REVIEW.md)：明确SHA、最小复现、非阻断风险及新入口未覆盖范围。

## yaw：响应问题待PINN复核

`a49eb90d942fc50f68cedb3d00b2b53a3a80da02`完成旧三通道anchor收尾；动作约束减少漂移，但原完整验收失败、流0损失和压力失败保留，本阶段没有追加yaw学习。
validation局部诊断中，yaw共同扰动代理响应绝对值中位数.73kW，而合成标签源7.29kW；标签响应≥1kW记录的38.65%方向不一致，逐机约44.04%。这是相关/重复点的模型内描述，标签本身也不是物理真值。
非零yaw响应不等于通过可控代理验收，不能仅凭闭环失败认定yaw本身无效。原模型不改，待PINN组核对输入映射、拟合/尺度、响应符号和有效域；本轮没有联系队友。

- [优化侧yaw复核问题与交付格式](PINN_YAW_RESPONSE_QUESTIONS.md)
- [anchor收尾与局部响应来源](ANCHOR_CLOSEOUT_RESULTS.md)
- [局部响应原始表（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

## 已完成单因素实验：speed n1/n8 49152步

2026-10-29主对话已明确接受现有反证，授权**一次可证伪对照**；这不是旧“机制与稳定性均改善”条件已通过，也不是认定pitch机制可泛化。
原草案和历史停止报告保留，新授权由[SPEED_NSTEP_PROTOCOL.md](SPEED_NSTEP_PROTOCOL.md)和[新配置](configs/speed_nstep.yaml)记录。

| 项目 | 本次固定范围 |
|---|---|
| 两臂 | 两者都是原冻结父+speed头，n1 vs n8；只改Critic TD目标 |
| 起点 | 原三份pitch父；不使用新pitch n8或旧speed selected/final |
| 正式预算 | 2×3×8192=49152步；每job3841次update；无额外环境学习smoke |
| radius | .02→.10rad/s，前4096步；整批目标用当前transition锁存radius，eval=.10 |
| 数据命名空间 | train41000000、validation42000000、test43000000、已知压力43009000；seed42派生流 |
| 验证/保存 | 6场validation，每2048步选模含initial；每128步保存；run0两臂2048处退出后新进程恢复，包含预算内 |
| 稳定与收益 | final/selected≤1.25，final mean/worst对固定父及n1≤1.05；n8三流selected非initial，selected和final对n1三流严格改善且总体≥1%；精度400/500另列 |
| 测试隔离 | 六job/选择/核心审计冻结后一次新18场test；2个已知压力另列；P/PI不重整定，不因失败加预算 |

实验根：[20261029_speed_nstep_control（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。
完成提交`7ad33692591ec458e8995e1dbfb75b11522e57d7`，以[SPEED_NSTEP_RESULTS.md](SPEED_NSTEP_RESULTS.md)和[summary.txt](../experiments/20261029_speed_nstep_control/summary.txt)为准。六job各8192步/3841次update，共49152步/23046次update；390份检查点、8个正常退出子进程，run0两臂2048处新进程恢复。9项严格接管gate差0，入口3项测试通过；无未保存重算或额外学习smoke。

| validation | n1 selected / final kW | n8 selected / final kW | n8 selected步 | n8完整稳定 |
|---|---:|---:|---:|---|
| 流0 | 362.27 / 375.89 | 364.34 / 379.45 | 0 | False |
| 流1 | 342.88 / 348.01 | 338.91 / 342.19 | 4096 | True |
| 流2 | 307.96 / 321.84 | 306.75 / 315.31 | 2048 | True |

n8相对n1的validation selected/final均值仅改善0.31%/0.84%；预声明要求两角色三流严格改善且总体至少1%、三流selected均非initial，结果未通过。完整稳定n8为2/3、n1为1/3；精度mean400/worst500kW另列，不能用5%不劣容差称为学习收益。

冻结后新常规18场test中，父378.33kW；n1 selected/final为358.96/374.29，n8为360.60/369.56，P527.47、PI434.99。n8 selected比n1差0.46%，final改善1.26%；这些不能反向改变validation失败或用来改选。已知压力2场另列：父1607.95，n1 selected/final1668.78/1717.61，n8 1653.41/1711.76，P/PI1383.30kW。n8 test工程稳定3/3只作冻结后描述，不覆盖validation 2/3。

720条指标/92160行test时序复算差0；selected/final zero-speed共30720行回到冻结父。预声明480步方向核查中的n1/n8 selected反向数1/6与2/6、final2/6与3/6，不能认定普遍Q修复。没有用test追加调参，也没有默认换父或新候选。

后续已完成[9点/17点单因素网格诊断](SPEED_MIDGRID_RESULTS.md)，提交`1a7221a3bcbceb351b5555111c1a58a687bdf1f6`，正式RL0：仅追加±.05rad/s八个中幅候选，旧9项前缀不变。validation case均值352.67→350.92kW，但相对固定父仅改善.733%，流1仍退化2.16%，未达三流可重复收益；同状态预测较低成本未保证闭环收益。没有启动示范/RL、新独立test或默认升级。speed侧历史风预测后续工作由该侧独立推进，本pitch核查未读取/复制其预测器。

本侧先前独立审查只做4次丢弃内存更新，不是本正式预算的一部分；未替speed侧执行、修改代码或清理产物。

## 工作树、提交和产物地图

| 工作树绝对路径 | 分支/已完成来源提交 | 主要产物 |
|---|---|---|
| . | master；999a3792cca1d66ac3fcfec3b54cfeffacc8a27a | 原模型、20261022/23父链、共享状态；本轮只读 |
| . | codex/pitch-cross-wind；48d4dd4→d6b0a9b→740d040→dd6f400→63db394→3b4acc9→eef2a13→99a4803→5d34e61；积分可行性收尾提交见Git记录 | 原n8候选、reward/gamma/Actor失败历史、20261030_pitch_integral_feasibility的RL0正向开发筛查及待审阅误差记忆方案 |
| . | codex/maddpg-anchor-closeout-20261027；a49eb90 | experiments/20261027_anchor_closeout，旧anchor补齐审计/模型响应证据 |
| . | codex/speed-nstep-engineering-20261028；eaacdef→6b7314a→c3e9cc0→7ad3369→2273d0a→1a7221a | speed n1/n8及9/17点网格均保留未通过收益结论；后续预测研究归该侧 |

本侧独立审查/索引和后续奖励审计分别在pitch分支形成原子提交；确切提交号见该分支Git记录及最终交接消息。
仅以明确文件列表整合已验证提交，不直接切换同一工作区分支、不自动合并master、不推送、不清理其他改动。原共享状态由协调方单一维护。
不改写2026-10-22 PPT和历史报告的当时口径；10月28/29的新结果作为带日期、模型/数据身份的新阶段证据引用。没有新ZIP或大模型副本。
