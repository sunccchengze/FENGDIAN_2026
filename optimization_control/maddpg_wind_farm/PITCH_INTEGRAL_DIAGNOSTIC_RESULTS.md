# 冻结n8＋积分修正：开发筛查通过，仍不是学习或泛化验收

2026-10-30。按[事前冻结协议](PITCH_INTEGRAL_DIAGNOSTIC_PROTOCOL.md)完成唯一±.02rad共同积分修正诊断。**主薄弱组RMSE相对冻结n8降低6.13%，三父流均改善；能力保留、PI失败数量、实际运动和硬边界全部通过开发筛查。** 这证明当前模型和权限内存在可利用的因果闭环修正空间，支持提出误差记忆学习方案；不证明现有Actor已经学会记忆、不证明记忆必要或独立测试通过，不升级默认策略。

正式训练0、优化器更新0、新独立测试0。没有换增益/幅值、追加候选或打开压力/test回放。完整实验位于[20261030_pitch_integral_feasibility（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。前轮5d34e61的Actor队友条件干预失败结论保留，未把它的新selected/final作为起点。

## 固定对象、真实单位和因果时序

固定[原n8候选清单](../experiments/20261028_pitch_nstep_mechanism/candidate_manifest.json)三份validation-selected16384/12288/4096，父SHA依次为`1f91cdba…678a`、`cc0b37eb…a957`、`0e19dd05…3b5b`，完整值/路径见[config.yaml](../experiments/20261030_pitch_integral_feasibility/config.yaml)。模型`wind12-synthetic-7506554ac981`及原执行器冻结，MADDPG仅控制pitch，yaw跟踪风向，speed使用同一运行曲线。三父完整状态在各自闭环前后指纹相同，无回放采样或网络/Adam/RNG更新。

PI代码实际读取float32的`obs[0,9]=(全场功率−目标)/15MW`，正为过发。积分单位为rad，dt=1s、ki=.08 rad/(s·归一化误差)，SI系数为5.333333333333333e-9 rad/(W·s)；100kW欠发对应下一拍积分约-.000533333rad。不是把.08直接乘W。

每回合I_0=0，本时刻输出`clip(父当前pitch目标+I_t,0,.22)`，随后仅用已知当前误差计算下一拍I；范围±.02rad，修正量或任一总目标同向饱和时停止继续累积，反向可退饱和。没有加入P/bias/预测，也没有复制PI的tracking反算项；这是授权的条件积分规则。代码见[pitch_integral_controller.py](pitch_integral_controller.py)。父每步读取**混合闭环自己的当前观测**，并非平移旧功率或重放父世界的未来动作。

4项单元测试覆盖PI单位和一拍延迟、零修正、复位、修正/总目标抗饱和与反向退出；测试不调用Plant。另三父各一个真实完整零修正回合，原轨迹全部字段最大差0，387输入行含reset。独立保存数据核验又逐步检查20736个混合动作的误差float32转换、积分递推、复位、来流及同一yaw heading。

## 54槽位对应21条波形，引用基线不是新增回放

只使用已登记36开发回归case（9训练波形×2初态、6旧validation波形×3初态）和Actor条件实验18场validation（6波形×3初态）。共54槽位/父，21条不同完整129×3入口波形。三父、初态和同波形下各控制器高度相关，162个父流×case不能当162个独立风况样本或训练重复，不作显著性/置信区间结论。

270条父/P/PI指标从原Actor条件实验的**initial和公共基线**完整轨迹引用，核对原n8 Actor身份、完整配置、模型/代码、来流、目标、初态和SHA并复算；不引用该实验新selected/final。旧登记清单含压力身份元数据，筛选时显式排除；未读取压力风轨迹/性能或旧独立test指标，未复评压力。21条已登记波形仅按既有规则再生并锁定SHA，没有抽新波形。见[reference_reuse.json](../experiments/20261030_pitch_integral_feasibility/reference_reuse.json)与[wave_identity.csv](../experiments/20261030_pitch_integral_feasibility/wave_identity.csv)。

P/PI沿用kp1.5、ki.08、bias.04rad、antiwindup.2、integral_limit.3，未重新整定。现有模型是准静态合成联调代理，统一执行器属于优化侧；本轮没有可达性搜索，不证明真实风机性能或全局最优。

## 主薄弱组：偏差下降带来可重复的局部收益

事前指定train_episode_8、平稳3.8MW、两初态.025/.055，始终使用完整128秒。单位kW；bias=e均值，负为欠发；std为各完整回合误差标准差再平均。

| 父流 | 冻结父RMSE / bias / std | 冻结父＋积分RMSE / bias / std | RMSE变化 |
|---|---:|---:|---:|
| 0 | 471.37 / -244.16 / 402.99 | 445.69 / -174.06 / 410.16 | -5.45% |
| 1 | 560.39 / -374.70 / 416.50 | 511.80 / -305.84 / 410.24 | -8.67% |
| 2 | 507.49 / -296.72 / 411.29 | 487.36 / -261.45 / 410.91 | -3.97% |

三流均值由513.09降至481.62kW，降低6.13%，达到总体≥5%及≥2/3流改善门槛；不要求每流都达到5%。同两case的PI仍为423.01kW、bias=-37.68kW、std=420.71kW，混合控制在主组6/6槽位仍弱于PI。

逐case使用RMSE²=bias²+variance，ddof=0，先分解再平均。流0平均bias²由.05969降至.03036MW²，variance由.16252升至.16832，偏差下降超过波动增加；流1由.14045/.17360变.09356/.16841，流2由.08819/.16938变.06851/.16904。不能以平均RMSE平方代替平均MSE，也不把平均bias平方冒充平均bias²。

这些变化是在同父、同风、同目标/初态/执行器，只改变修正器的在线闭环下观察到的，故支持此固定修正的因果收益。它不能分离“额外历史信息”和“手工控制律”的独立贡献；没有做恒定偏置、打乱记忆或增益扫描。因此后续需要学习器自身的记忆输入对照，不能直接宣布新增信息必然有效或Critic根因已解决。

## 全部开发场景：平均改善，47个逐场退化保留

下表为完整case-RMSE均值，单位kW。±为三父各自均值的样本SD，包含父策略历史预算差异，不是置信区间。每风况在两集合共18槽位/父。

| 全54槽位中的风况 | 冻结父 ± SD | 冻结父＋积分 ± SD | P | PI |
|---|---:|---:|---:|---:|
| 平稳 | 347.47 ± 4.27 | 337.64 ± 2.30 | 515.94 | 411.77 |
| 慢变 | 338.91 ± 10.17 | 329.52 ± 6.03 | 500.58 | 411.56 |
| 阵风 | 416.61 ± 4.64 | 414.07 ± 5.27 | 599.45 | 502.42 |
| 全部 | 367.66 ± 2.65 | 360.41 ± .74 | 538.66 | 441.92 |

全部case均值改善1.97%，慢变改善2.77%；pooled RMSE由385.87降至379.65kW，PI为462.19。均为开发描述，不称新独立泛化结果。分集合全部36已知开发case由356.21降至347.65kW（-2.40%）；另18validation由390.57降至385.92（-1.19%），后者慢变244.05→235.15kW（-3.64%）。

| 集合/风况 | 冻结父 | 冻结父＋积分 |
|---|---:|---:|
| 已知开发：平稳 | 339.62 | 325.69 |
| 已知开发：慢变 | 386.35 | 376.70 |
| 已知开发：阵风 | 342.65 | 340.56 |
| 18validation：平稳 | 363.17 | 361.53 |
| 18validation：慢变 | 244.05 | 235.15 |
| 18validation：阵风 | 564.51 | 561.08 |

162个父流×case中115改善、47退化，全部保留在[paired_cases.csv](../experiments/20261030_pitch_integral_feasibility/paired_cases.csv)，另列相对P/PI差、bias²/variance变化；[target_initial.csv](../experiments/20261030_pitch_integral_feasibility/target_initial.csv)覆盖每流×集合×风况×目标×初态，不能用总体代替逐组。

最大绝对退化是流0、train_episode_2阵风3.2MW、初态.025：483.72→492.74kW，+9.02kW；bias²反而减少.000752MW²，variance增加.009560MW²，说明积分可降低偏差同时加重波动。另流0旧validation_gust_0、2.85MW、初态.025为354.06→361.25kW，bias²和variance均增。最大逐case相对退化约2.06%（流2该阵风初态.04），不是完全无损。

冻结门槛中的其他34开发case及18validation按集合/流/风况核查：mean比最大1.00164、worst比最大1.01865，均≤1.05；worst比是两组各自最大值之比，完整逐case另列。18组实际TV比最大1.02656、RMS速率比最大1.01186，均≤1.10；硬pitch幅值[0,.22]rad、最大速率.00872664626rad/s（tol1e-9）全部通过，实际速率饱和不等于违反硬约束。

弱于PI的总槽位从11/162降至6/162：流0/1/2分别2→2、4→2、5→2；18validation两方法均0/54弱于PI。逐组不增门槛通过，但主要6槽位仍全部弱PI。可以说“该开发集合平均优PI、原策略得到改善”，不能说“各场各流稳定优PI”，更不能替代原纯MADDPG及压力目标。

## 交付核验与预算

新增真实Plant输入21285行=混合3×54×129的20898行＋工程3×129的387行，全部含reset；mock输入0，低于共同60000上限。调用前追加字节计数，失败尝试也会计入；本轮无失败重跑。没有.pth输出，没有权重/回放目录副本，没有清理旧文件。

独立[delivery_check.json](../experiments/20261030_pitch_integral_feasibility/delivery_check.json)用标准库math.fsum复算432条完整回合指标及实际TV/RMS，RMSE最大差0W，逐步核对全部20736个混合动作的因果积分和当前误差单位；[independent_screening.json](../experiments/20261030_pitch_integral_feasibility/independent_screening.json)独立重算18组门槛与主组判定一致。122项冻结来源及输入风文件SHA保持。

图均由Python从保存数据绘制并已逐张查看：[主组误差分解](../experiments/20261030_pitch_integral_feasibility/primary_decomposition.png)、[全部54槽位×三父差值](../experiments/20261030_pitch_integral_feasibility/all_case_paired_differences.png)、[三流完整128秒时序](../experiments/20261030_pitch_integral_feasibility/full_integral_timeseries.png)。最后一图的代表事前固定为主组.025；误差/风速、实际/命令/积分state各用对应单位，三机均值仅展示，运动统计取逐机数据。[response_windows.csv](../experiments/20261030_pitch_integral_feasibility/response_windows.csv)保留全部648个32秒描述窗口，不用于重新选择或改门槛。

当前实验精确最终空间与分类见[storage_stats.json](../experiments/20261030_pitch_integral_feasibility/storage_stats.json)，低于512MiB。指标、来源、代码、配置和摘要进入本地原子提交；gzip/PNG/风数据留本地实验目录。原共享PROJECT_STATUS/TASKFLOW/README、PINN和speed实现未修改，不合并master、不push。

## 一项下一学习提案，尚未实施

见[PITCH_ERROR_MEMORY_CANDIDATE.md](PITCH_ERROR_MEMORY_CANDIDATE.md)：只比较同一零初始化记忆支路读取恒0或因果积分标量，不再向桨距直接叠加积分。环境仍15维，Actor/Critic新增私有标量支路和回放context属于网络/数据格式变更，**必须审阅确认后才实施**。本轮没有新网络、私有回放格式或训练。

为使提案具体可审阅，只读核查了原三父回放的时间顺序/回合边界：32768/32768/28672条分别构成256/256/224个完整128步回合，内部next_obs→obs连续，能从已存当前误差与已执行目标定义因果记忆。见[memory_replay_readiness.json](../experiments/20261030_pitch_integral_feasibility/memory_replay_readiness.json)。未构造新特征、未改写回放，若下一实施工程检查不通过则停止，不能用假零记忆或清空回放绕过。

## 可复现命令

使用现有本地环境与不存在的新目录。同数据复现不是新独立测试；不在当前完成目录重复写入。

```powershell
Set-Location -LiteralPath .
$py='./.venv/Scripts/python.exe'
$out='optimization_control/experiments/20261030_pitch_integral_feasibility_reproduction'
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_integral_diagnostic prepare --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_integral_diagnostic engineering --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_integral_diagnostic run --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_integral_diagnostic report --output $out
```

本轮只执行一次上述诊断，没有第二轮复现。交付核验脚本在当前实验verify_delivery.py中，若用于新目录需复制此小脚本并在查看三图后运行；它不调用模型。图、补充只读门槛/回放核验和最终空间记录不增加模型输入。下一学习提案的任何预算均不包含在本轮执行授权中。
