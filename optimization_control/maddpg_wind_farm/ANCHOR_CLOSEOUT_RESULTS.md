# 父策略动作约束收尾、接管与局部模型诊断（2026-10-27）

审计、validation诊断及原锁定测试已完成。动作约束减少联合漂移，但流0损失保留，原完整稳定性验收仍失败；常规测试终点相对baseline仅2/3改善，相对父策略也仅2/3改善，不能宣布可重复的三通道学习收益。正式新增训练0步，没有新候选训练，没有改写原实验。图表视觉检查与最终产物校验见下文。

## 范围、来源与隔离

本轮只收尾20261024父策略动作约束实验，并完成validation接管、通道组合和局部模型诊断。原lambda=0/1、三条主种子42派生流、每臂每流8192步（原新增49152步）、选模与精度/稳定性门槛保持冻结。[原协议](ANCHOR_PROTOCOL.md)及[本轮收尾协议](ANCHOR_CLOSEOUT_PROTOCOL.md)分别保存历史和新增审计约定。

- 原工作区：`.`，分支master保持原状。原PROJECT_STATUS.md、TASKFLOW.md、README.md未修改。
- 隔离工作树：`.`，分支`codex/maddpg-anchor-closeout-20261027`，基点`999a3792cca1d66ac3fcfec3b54cfeffacc8a27a`。本轮不合并master、不推送。
- 原实验：`./optimization_control/experiments/20261024_parent_action_anchor`；原模型、30份检查点、日志、选择锁、test/config.yaml及其目录文件清单只读。
- 本轮输出：[20261027_anchor_closeout](../experiments/20261027_anchor_closeout/config.yaml)。原summary仍为prepared、原ANCHOR_RESULTS仍是暂停时占位说明；本报告及新目录是收尾结果，不能把未写回旧summary解释成未完成。

独立工作树逐字节复制7个未提交文件：ANCHOR_PROTOCOL.md、ANCHOR_RESULTS.md、anchor_algorithm.py、anchor_training.py、verify_anchor.py、configs/anchor_training.yaml、tests/test_anchor_control.py。来源与SHA256在本轮config.yaml的copied_uncommitted中，原件没有暂存、提交或清理。原51个保护项全部匹配；本轮进一步固定197个源/旧产物摘要及63个执行文件摘要，计数有重叠，不能相加为不同文件数。补充精度定位和标签源复算各自在audit中保存额外脚本SHA256。

## 验证集：动作约束减少漂移，但完整验收失败

下表单位kW，为原六场validation的case RMSE平均。父策略来自上一轮all初始交接，已包含前一阶段学成的speed能力；本实验不重新授予权限，不能直接证明新增通道收益。

| 流 | 父策略 | baseline selected步/均值 | baseline final | anchor selected步/均值 | anchor final | anchor final减baseline |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 423.99 | 8192 / 385.65 | 385.65 | 6144 / 405.73 | 408.62 | +22.96（+5.95%） |
| 1 | 343.33 | 0 / 343.33 | 371.23 | 6144 / 340.21 | 344.20 | -27.04（-7.28%） |
| 2 | 345.96 | 0 / 345.96 | 409.08 | 6144 / 342.74 | 343.44 | -65.64（-16.04%） |

anchor三流selected均不是initial，相对父策略的验证均值改善4.31%/0.91%/0.93%。baseline流1/2 selected仍为initial，不记作新增学习。anchor流1 final仍略差于父策略（344.20 vs343.33），所以5%工程不劣也不能当成严格改善。

| 冻结判据 | baseline | anchor |
|---|---:|---:|
| final/selected<=1.25 | 3/3 | 3/3 |
| final mean/worst相对父策略<=1.05 | 1/3 | 3/3 |
| final mean/worst相对配对baseline<=1.05 | 3/3（自身参照） | 2/3 |
| 完整稳定性 | 失败 | 失败 |
| selected精度mean<=400、worst<=500 kW | 3/3 | 2/3 |
| final精度mean<=400、worst<=500 kW | 1/3 | 2/3 |

anchor流0最差case从baseline final的446.99增至531.99 kW，恶化19.02%，不能被三流终点平均388.65→365.42 kW（降低5.98%）掩盖。两臂selected平均分别358.31与362.90 kW，anchor也没有选中均值优势。原门槛失败与所有检查点均保留，不换系数、不追加预算。

终点/选中比：baseline为1.0000/1.0813/1.1824，anchor为1.0071/1.0117/1.0020。验证当前状态上的父动作偏离RMS如下；每个策略访问的状态分布可能不同，不能据此证明唯一因果。

| 流 | yaw偏离deg，baseline→anchor | pitch偏离deg，baseline→anchor | speed偏离rad/s，baseline→anchor |
|---|---:|---:|---:|
| 0 | 4.993→0.313 | 3.173→0.482 | 0.09542→0.01233 |
| 1 | 4.819→0.466 | 5.487→0.461 | 0.08618→0.00419 |
| 2 | 4.151→0.567 | 4.219→0.210 | 0.09198→0.00320 |

## 原锁定测试

本轮固定测试600条指标、76800行轨迹已完成，逐case由保存轨迹复算RMSE，最大差0 W。测试已在2026-10-24进入释放流程，原目录只有绑定选择SHA256的config.yaml；不能断言此前从未进行过内存评估。本轮沿用原20 case和选择锁，没有重新抽风况。18个routine case为本轮锁定常规测试，2个7.6m/s、4.4MW压力case为已知回归；60条压力指标不记新独立样本。

先对每流18个routine case的RMSE取平均，再汇总三流均值±样本SD；不是将全体误差重新合并成单一RMSE，也不是置信区间。initial=parent，两臂相同。

| 控制方案 | routine RMSE kW |
|---|---:|
| initial=parent | 389.83 ± 27.31 |
| baseline selected | 381.39 ± 13.02 |
| baseline final | 407.86 ± 29.03 |
| anchor selected | 384.87 ± 25.42 |
| anchor final | 386.41 ± 25.09 |
| 固定设定 | 1138.71 |
| P组合 | 584.57 |
| PI组合 | 493.07 |

| 流 | 父策略 | baseline selected | baseline final | anchor selected | anchor final | anchor final减baseline |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 421.04 | 395.72 | 395.72 | 413.28 | 413.83 | +18.11 |
| 1 | 378.16 | 378.16 | 386.86 | 377.06 | 380.79 | -6.07 |
| 2 | 370.29 | 370.29 | 440.99 | 364.26 | 364.61 | -76.38 |

anchor final总体相对baseline降低5.26%，但仅2/3配对改善；相对自身父策略总体只降低3.42 kW（0.88%），流1反而恶化2.63 kW。anchor selected相对baseline总体增加0.91%，三流差为+17.56/-1.09/-6.02 kW。因此不是所有流或所有选模方式都获益，终点总体优势主要来自流2避免较大退化。测试不改变原validation流0失败，不用测试重选selected。

已知低风压力：initial=parent为1684.61±154.84 kW，baseline selected/final为1722.57±154.45 /1692.33±127.02，anchor selected/final为1691.54±167.98 /1698.72±175.80；P/PI均1383.30。两臂终点均未改善初始总体压力表现，anchor final也比baseline final高6.38 kW，失败保留。

P/PI使用共同桨距功率反馈和统一yaw/speed后台调度，与MADDPG同风况、目标、初态、执行器和限制。这是完整控制方案比较，不是三个通道各自安装P/PI，也不是新增权限的单因素消融。父策略在本次routine已低于P/PI，大部分优势来自继承能力，不能全归功于动作约束或本轮训练；压力场仍明显较差。新增权限的收益须另靠逐通道及同预算父权限对照证明。

## 接管：同状态动作相同，speed严格闭环容差未过

旧协议的回放动作接管检查与本次新增的严格闭环复核分别报告，不追溯改判历史工程通过结果。本次预先固定总动作<=2e-6、实际heading/pitch/speed差<=1e-6、最大功率及RMSE差<=1 W。使用原父训练回放的obs/next_obs、online/target及新validation六场128步闭环。

| 接管对象 | 同状态online/target最大动作差 | 闭环最大功率差W | 最大实际状态差 | RMSE差W | 本次严格检查 |
|---|---:|---:|---:|---:|---|
| speed流0 | 0 | 2.25 | 2.68e-7 | 0.084 | 未过 |
| speed流1 | 0 | 2.25 | 1.66e-7 | 0.086 | 未过 |
| speed流2 | 0 | 2.50 | 2.89e-7 | 0.129 | 未过 |
| yaw三流 | 全0 | 全0 | 全0 | 全0 | 3/3 |
| anchor初始对父三流 | 全0 | 全0 | 全0 | 全0 | 3/3 |

speed闭环最大总命令差约3.96e-6至6.59e-6，也超过本次2e-6容差。补充定位三流各一个validation case、384环境步：同观测父/零头子策略请求动作始终完全相同；旧父环境后台speed从物理有效风速重新计算，子策略从float32观测重建。有效风速量化差最大4.768e-7 m/s，环境投影最大差2.682e-7，1152个逐机记录中1108个非零。闭环累计后出现上述差异。

这是数值投影路径差异，量级不能解释后期数十kW的退化。保留严格失败，不改旧环境或放宽容差。未来的新协议应先统一参考生成的输入与运算，再复核。详见[audit精度定位（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)及[补充约定](ANCHOR_TAKEOVER_PRECISION.md)。

偏航执行器仍更新机舱heading；实际gamma=wrap(heading-wind_direction)，回放速率审计据gamma和风向恢复heading增量。online/target共用compose，Critic与回放使用投影后的归一化总命令，实际执行器状态另存。三通道没有绕过共同执行器与物理限制。

## validation通道组合：漂移与补偿同时存在

两臂三流各15变体：8种S/F组合、3种关闭修正、4种parent替换，共90变体/540 case/69120环境步，无更新。S/F顺序为yaw/pitch/speed；每步在混合策略自己的当前obs上重算各策略，再组合，不拼接旧轨迹。完整每case指标及轨迹保存在diagnostic各job目录，未删除失败组合。

| 臂/流 | SSS | FFF | 关闭yaw | 关闭speed | 恢复parent pitch | 恢复parent speed |
|---|---:|---:|---:|---:|---:|---:|
| baseline 0 | 385.65 | 385.65 | 425.93 | 415.76 | 422.12 | 415.76 |
| baseline 1 | 343.33 | 371.23 | 649.49 | 405.66 | 383.00 | 350.94 |
| baseline 2 | 345.96 | 409.08 | 410.67 | 422.14 | 376.34 | 405.65 |
| anchor 0 | 405.73 | 408.62 | 409.68 | 410.26 | 420.41 | 410.26 |
| anchor 1 | 340.21 | 344.20 | 346.12 | 394.21 | 340.96 | 344.72 |
| anchor 2 | 342.74 | 343.44 | 343.51 | 385.29 | 346.65 | 342.53 |

单位kW。baseline流1仅把pitch换成final（SFS）会从343.33恶化至541.27，但从FFF恢复parent pitch却得到383.00，比371.23还差；pitch漂移和yaw/speed补偿同时存在。关闭speed与恢复parent speed也不是同一干预：parent已含学到的speed，归零会抹去这一继承能力。不能从某一饱和通道或单一替换断言唯一根因。

冻结父映射的新候选因此只是可检验的保留能力方案，不是已证明的修复。固定权重也不保证新控制改变状态后旧pitch轨迹不变；应该约束/核对同一当前obs上的父映射。

## 新通道的局部作用与代理限制

只在validation的parent/selected/final实际运行点，于步16/64/112进行逐机及共同扰动，speed为0、±0.02/0.05/0.10 rad/s，gamma为0、±1/3/5度，形成18144条响应。包含两臂父状态等重复点，不作为18144个独立样本。全部使用原模型及有效域；响应不是高保真或真实物理证据。

共同±0.10 rad/s扰动时，父状态的全场功率绝对变化中位数约164.14 kW；共同±5度时约1.58 kW。响应强度不能直接当跟踪收益。进一步通过同一执行器对冻结父策略叠加预声明固定偏置，共39变体/234 case/29952步。

| 固定speed偏置rad/s | 流0 mean RMSE kW | 流1 | 流2 |
|---|---:|---:|---:|
| -0.10 | 385.10 | 336.89 | 349.06 |
| -0.05 | 394.73 | 327.50 | 333.77 |
| -0.02 | 411.70 | 335.07 | 339.34 |
| 0 | 423.99 | 343.33 | 345.96 |
| +0.02 | 436.57 | 352.70 | 354.59 |
| +0.05 | 455.50 | 368.08 | 370.22 |
| +0.10 | 484.86 | 396.26 | 400.31 |

完整yaw正负网格同样保留在fixed_offset_cases.csv，不按最好点挑策略。该扫描说明speed有可利用的模型内作用，且方向重要；不能把某个诊断网格点当成经独立测试选出的调度，更不能记作MADDPG学到收益。

由于yaw的直接响应较小，额外复算**同一批点**在原合成标签公式中的控制响应；没有新增探针、PINN调用、环境步或训练，也未读取test。它只比较当前代理与其合成标签源，标签公式不是物理真值。

| 扰动 | 模型响应绝对值中位数kW | 合成标签源对应值kW | 方向不一致比例（标签响应>=1kW） |
|---|---:|---:|---:|
| speed共同扰动 | 63.58 | 70.63 | 4.18%（1936条） |
| speed逐机扰动 | 22.13 | 23.80 | 3.74%（5754条） |
| yaw共同扰动 | 0.73 | 7.29 | 38.65%（1581条） |
| yaw逐机扰动 | 0.68 | 2.59 | 44.04%（4212条） |

这里汇总所有非零预声明幅度，不能与只取±最大幅度的164.14/1.58 kW直接比较。标签响应>=1kW只是说明符号统计排除近零值的描述阈值，不是后设性能通过门槛。主NumPy与原TF216运行时复算的CSV逐字节一致，两份派生结果保留；正式引用runtime216版本。

当前yaw响应存在相对标签源的幅度压缩和方向失配，不能仅以“非零敏感性”宣布模型足以支撑yaw收益学习。关闭yaw引起很大闭环误差也不等于yaw直接功率作用强，因为pitch/speed网络输出会随状态变化。建议优先完成speed，yaw训练前交由模型组复核局部响应；本轮没有擅自改模型。

## 审计、测试与计数

- 6项新收尾契约测试、5项原anchor测试，以及2项角度显示测试，共13项不同测试通过。覆盖隔离输出、三重冻结身份、轨迹缺失/重复/乱序/NaN拒绝、指标复算、parent通道替换与物理偏置单位，以及lambda0精确旧更新、teacher冻结与三通道梯度、v3恢复、环绕展开与gamma关系保持。
- 30份检查点teacher、lambda、学习率和固定尺度核验；三组配对初始网络/全部优化器/回放/RNG/探索一致，Actor moments均空，所有Critic优化器继承。每次8192步新增3841次联合更新。
- initial/selected/final共18次内存保存加载核对，带噪动作、下一update、网络、优化器、回放一致；两副本共36次诊断update不写回。
- 六份终点回放共196608条保留转移，通过总命令/next command、奖励、heading速率、终止掩码、目标不变和动态残差包络检查。包含重复继承历史，实际原新增训练仅49152步，本轮新增正式训练0。
- 192条训练风况预检按原种子/episode逐条重生成，家族、目标、初始pitch及SHA256一致。
- baseline流0真实2048暂停点，两个128步内存分叉的动作、回报、loss、噪声与网络精确一致，并与真实恢复后下一回合的保存回放动作逐位相同。256环境步/128次update只用于丢弃的内存副本。
- 新缓存plant的rollout与原冻结rollout在一个完整validation case的指标和128行轨迹逐列精确一致；两次回放256步计入诊断，不计正式训练。
- 600条锁定测试指标由76800行轨迹复算，差0 W；540 routine、60已知压力。原选择锁和释放标记不变，没有新test抽样；诊断及候选建议先于测试指标冻结。
- 全轨迹风况逐值对齐原CSV的环境float32表示（环境本身在_read_wind中显式转换）。初版交叉核验误将float64 CSV与float32记录直接比较，失败代码和示例保存在audit/final_check_failure.json及副本；修正审计预期表示后仍要求精确相等，没有改数据或放宽容差。
- 功率求和交叉核验同样复现环境float32求和，误差0；对序列化单机功率用float64重加可出现0.5 W舍入差。误用双精度断言的第二份失败记录及代码副本也保留，未改评估数据或稳定性门槛。

计数：通道69120＋固定偏置29952＋接管13824＋rollout等价256＋精度补充384＋恢复256＋锁定测试76800＝190592个评估/诊断环境步；另有18144个静态模型输入。它们不等于新增RL训练，不生成新策略检查点。后续结构建议只写文档。

## 图表与复现

图均由Python/Matplotlib从冻结CSV绘制，9组主图的PNG/PDF共18份；不是AI绘图。另保留3组原始显示图，共有24份PNG/PDF文件。逐张检查主图后确认文字/坐标未裁切、图例与数据对应。控制图预先指定test_gust_1_pitch0.025，三个训练流全部展示，不能按表现挑图。

初始控制图将环绕在0/2pi的风向直接连线，视觉检查发现虚假的整圈跳变。没有修改数据或冻结绘图源码；独立`anchor_heading_figures.py`将heading和wind展开后统一减去该case初始风向，另存unwrapped版本，下面只链接修正版。两项显示测试通过，原始图保留但不作为主图使用。

显示原点的“初始风向”指图中第一个保存点step1，三种策略与PI共用同一原点；准确弧度值存heading_display_fix.json。执行器t0初始化及原始绝对角度数据没有改变。

- [三流验证退化曲线（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)：包括2048步突增、选中星号和终点，400线仅为均值精度参考。
- [锁定测试与已知压力（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)：误差条是三派生流样本SD，不是置信区间；P/PI无训练流SD。
- [父动作漂移（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)：在各策略自身当前validation状态上计算。
- [通道干预（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)：共享坐标，差值不可相加。
- [局部模型响应（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)与[固定偏置闭环（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)：局部敏感性、闭环可利用性与训练收益分别报告。
- 实际控制：[流0（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、[流1（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、[流2（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，包含全场功率、机舱/来流朝向、实际gamma、pitch、speed。完整P/PI及所有case轨迹在test/trajectories.csv。

从独立工作树根目录运行，原工作区模型与checkpoint需保持可读。输出必须是当前工作树内不存在的新目录，不能指向旧实验。已有分阶段完成目录只能运行尚未完成阶段；完成job有hash锁，未完成job保留并报错，不删除后重跑。

```powershell
$py = './.venv/Scripts/python.exe'
$out = './optimization_control/experiments/NEW_ANCHOR_CLOSEOUT'
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_closeout prepare --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_closeout audit --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_closeout diagnose --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_takeover_precision --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_response_reference --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_closeout test --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_closeout figures --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_heading_figures --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_closeout finish --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.anchor_closeout_final_checks --output $out
& $py -B -X utf8 -m unittest optimization_control.tests.test_anchor_closeout optimization_control.tests.test_anchor_control.AnchorTests -v
& $py -B -X utf8 -m unittest optimization_control.tests.test_anchor_heading_figures -v
```

候选建议在[ANCHOR_NEXT_CANDIDATE.md](ANCHOR_NEXT_CANDIDATE.md)，其SHA256及诊断冻结SHA256在audit/pre_test_recommendation.json中记录，形成时本轮test/metrics.csv不存在。该建议只依据训练/validation，未实现、未启动新训练；未来涉及结构与数据格式的方案仍须确认。

## 检查点与供统一整合的状态

原30份checkpoint没有改写。baseline流0 selected=final=`baseline_run_0/segment_001/step_00008192.pth`；baseline流1/2 selected为各自segment_000的step_00000000；anchor三流selected均为segment_000/step_00006144。六个final均为step_00008192，initial均为segment_000/step_00000000。绝对路径/SHA256、父链和配置见[checkpoint_manifest.csv（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、原selection.json及本轮config.yaml.source_snapshot；30份metadata的归一化一致，另导出[normalization.json（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。加载使用anchor_algorithm.load_policy，旧v2加载器不接受v3。

供统一整合：20261024动作约束实验已在独立工作树完成收尾，原49152训练步不重复，新增正式训练0。30checkpoint/197保护项、18恢复检查、196608保留回放、192训练入口与真实2048恢复分叉通过；600指标/76800轨迹复算差0。anchor验证final相对父3/3工程不劣、相对baseline2/3，原完整验收失败；selected均6144。routine anchor final386.41±25.09 vs baseline407.86±29.03 kW，仅2/3配对改善，流0损失与低风压力失败保留。speed零头同状态动作0差，但严格闭环1W/2e-6要求因数值投影差未过；yaw及anchor初始精确接管3/3。yaw模型相对合成标签源的局部响应存在压缩/方向失配，建议先完成speed并在yaw立项前复核模型。未来冻结完整父映射+独立speed头仅提交方案，未实施。

原状态文件由协调方单一写入，本工作树只保留验证后的原子提交，不自动合并master。整合时7个原未提交anchor文件在本分支按来源原样纳入，不能顺带提交、覆盖或清理原工作区其他改动。
