# n-step机制核查与实验候选交接（2026-10-28）

**完成。本轮支持“selected在部分公共锚点的有限回报方向更一致”，不支持“真实Q已修复”或“终点稳定性已解决”。**
仅将原已锁定三份n8 selected交接为实验候选；不修改默认、不挑选训练流、不替换三通道父。
可审阅决定：支持另一侧继续单独TD目标的工程适配/一步等价性检查；现有证据不足以自动迁移为speed默认或启动正式RL。

## 预算、来源与测量隔离

协议先冻结：[PITCH_NSTEP_MECHANISM_PROTOCOL.md](PITCH_NSTEP_MECHANISM_PROTOCOL.md)。来源为740d040的已冻结训练和选择，不重选checkpoint、不重抽test。
仅使用原validation的六场：三风况×2.9/3.5MW，初始pitch=.04，三流全保留；t32/96锚点，实际8/32步窗口。
公共状态由同流父策略n1 initial产生，九动作是零与共同/各机±.005rad参考修正，经原执行器。
本流n1/n8各initial/selected/final六组Critic都对相同状态和完整联合动作评分；每动作固定首步后，分别以父策略和n8 selected延续。
每种延续内的状态、动作、未来风和后续策略完全相同，Q差异来自函数本身，避免混入各Actor闭环状态差异。
另有各策略自身状态、共同±.005rad/零动作及自身延续结果，单列不能作相同状态的因果比较。
三机Q及均值都保留；逐机动作使用本机ΔQ、共同动作使用均值ΔQ。完整九动作排序另外分别对Q1/Q2/Q3/均值计算，不混用各Critic的绝对值。

实际新增评估 **44928步**：机制38016、新进程候选统一验证回放6912；正式训练0、新test执行0。
最坏58752步以内，通过精确策略/锚点/首动作/延续缓存复用13824步；另只读复用108条完整回合验证指标及其13824行既有轨迹。
18分片完成，无中断保守占用差额；低于65000硬上限。逐片账本evaluation_budget.jsonl包含所有前缀/分支/交接占用。
31104行新分叉时序、6912条公共方向对照、864条自身方向对照全部保留；指标复算最大差0，reward分项和最大差2.94e-8。
141个保护文件摘要未变，online/target网络参数未变；原n1/n8 initial的全部公共Q评分差0。
216个自身策略零扰动窗口与旧轨迹误差差0W；两种固定延续的324对公共首动作、首步reward和功率响应完全一致。

## 公共锚点：方向变化存在，但不是普遍修复

“反向”指|ΔQ|与|ΔG|均>1e-5且符号相反。表中先取两个Critic版本都非平局的相同槽位；所有平局/支持范围外数据仍保留。
一个槽位是流×case×锚点×非零动作，初态/风轨迹/动作高度相关，不把这些计数当独立显著性证据。

| 固定延续/32步 | 比较 | 配对非平局 | n1反向 | n8反向 | 由反向变一致 | 新增反向 |
|---|---|---:|---:|---:|---:|---:|
| 父策略 | selected | 285 | 140 | 127 | 66 | 53 |
| n8 selected | selected | 285 | 131 | 117 | 66 | 52 |
| 父策略 | final | 285 | 117 | 121 | 65 | 69 |
| n8 selected | final | 285 | 116 | 112 | 69 | 65 |

selected有所减少，但大量改善与新增错误同时存在；同预算final的方向结果随延续改变，不能称稳定修复。
selected比较使用validation选出的不同训练时刻（n1流0/1仍initial），不代表两个Critic经历相同更新数；final才都是16384步终点。
普通n1续训本身也有方向变化：父延续32步下，initial原155/285反向，n1 selected为140/285、final117/285；不能把所有相对initial变化归因于n-step。

父延续、32步、selected的逐流匹配反向计数：

| 流 | 槽位 | n1 selected | n8 selected |
|---|---:|---:|---:|
| 0 | 95 | 47 | 35 |
| 1 | 96 | 55 | 47 |
| 2 | 94 | 38 | 45 |

流2反证保留；换n8 selected延续时，流2同样由30/95变37/95。两种延续都没有三流一致改善。
双边均在32近邻动作范围内的父延续selected配对238槽位，反向116→112；n8 selected延续为111→104。
局部范围内的减少更小，不能用支持标签筛掉反证后宣布修复。

## 九动作排序、短长窗口与奖励

完整九动作使用同一个Q头逐对排序，不将不同Critic绝对值拼接成一条排名。均值Q头的32步概要：

| 固定延续 | Q版本 | 反序动作对/可比较对 | Q首选等于实现G首选/36网格 | 平均有限G regret |
|---|---|---:|---:|---:|
| 父策略 | n1 selected | 670/1292 | 5 | .007374 |
| 父策略 | n8 selected | 570/1293 | 12 | .005538 |
| n8 selected | n1 selected | 609/1292 | 8 | .008302 |
| n8 selected | n8 selected | 495/1293 | 12 | .006295 |

这里有局部排序改善，但大多数网格Q首选仍不等于该实现有限G首选；Q1/Q2/Q3和initial/final全表见grid_ranking_summary.csv。
九动作最优只是在这条固定风实现和局部网格中的有限窗口最好，不是长期期望Q、真实价值梯度或全局动态最优。
32/576个去重的“同起点×动作×固定延续”比较在8与32步间发生符号改变，不能以8步短时收益认定长期改善。
G8/G32没有添加bootstrap，不能当作训练中的8步TD target；本审计也没有证明真实长期期望Q的偏差已消失。

父固定延续32步有14/288个非零动作槽位tracking回报改善却总回报变差；n8 selected固定延续有12/288。
它们是实际G的去重计数，不乘六组Critic。原reward的动作变化惩罚会抵消部分跟踪改善，不把全部方向差异称为Q错误。
各策略自身状态/自身延续的共同扰动32步反向计数，n1 initial/selected/final为38/72、35/72、36/72；
n8 initial/selected/final为38/72、32/72、32/71。自身状态不同，这只能说明各策略局部闭环特征，不能替代公共参考对照。

## 有效m、回放支持与解释界限

n8公共锚点32近邻回放的m均值：initial7.9939、selected7.9974、final7.9974；n1均为1。
这些锚点远离真实终止，附近多用满8步，不代表训练中所有样本；原训练全局m均值约7.78，直方图随role分别保留。
n8 initial虽配置8步但尚未新更新，Q与n1 initial精确相同，不能把其m值当已学习效果。
实际m、旧行为策略后续奖励和bootstrap终止规则均按原实现；多步目标仍带off-policy偏差，没有添加重要性校正。

全部公共动作都在各回放的全局动作坐标范围内，公共obs逐坐标也未越界；这不是密度支持证明。
288个非零动作槽位中，initial局部范围外41、n1 selected33、n8 selected42、n1 final19、n8 final44。
n8没有普遍扩大这一近邻动作范围，方向变化不能简单解释为覆盖改善。全量obs距离、坐标范围、局部标记和m在metrics.csv保留。
Critic针对各自训练策略，而交叉评分采用固定公共延续；该离策略测量限制、单条未来风、有限窗口和相关样本共同限制机制结论。

## 已保存结果的能力保留核对

只读取上一轮保存结果，没有新的独立test运行或选模。原selected门槛通过事实保留：慢变case均值相对n1改善5.39%，2/3流改善。
同一批保存结果中final慢变优势仅1.57%；pooled慢变selected相对n1改善3.93%，不能换口径称达到5%。
含压力全44场，selected case均值615.75kW优于PI657.03，但pooled752.15差于PI738.72；压力24/24差于P/PI。

流2的父能力保留反证（case均值，kW）：

| 范围 | 父 | n8 selected | n8 final | final相对父 |
|---|---:|---:|---:|---:|
| 慢变 | 397.79 | 401.14 | 421.72 | +6.02% |
| 阵风 | 386.17 | 398.13 | 417.73 | +8.17% |
| 常规总体 | 410.31 | 420.54 | 432.21 | +5.34% |

相对selected的宽松1.25倍门槛通过，不等于相对父策略能力保留通过，也不证明所有流稳定。
retention_audit.csv逐流逐风况保存case均值/pooled的parent、selected、final和三种比值，包含压力及全部44场。

## 三份实验候选交接

正式清单：[candidate_manifest.json](../experiments/20261028_pitch_nstep_mechanism/candidate_manifest.json)。
归一化：[candidate_normalization.json](../experiments/20261028_pitch_nstep_mechanism/candidate_normalization.json)。
模型和环境配置、完整模型SHA保护表、[3,15]观测/[3,3]总命令语义、mask=[0,1,0]、统一yaw/speed调度、n=8和tail_rule均在清单。
归一化来自原环境的固定物理缩放，无另拟合running mean/std。恢复保留online/target、Adam、回放、时序和全部原RNG元数据。

| 流 | 已锁定selected（绝对路径） | SHA256 |
|---|---|---|
| 0 | [16384步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) | 1f91cdba7676f1c32434e7e1e130cac6df155e4c41798ef6b88c6c58b032678a |
| 1 | [12288步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) | cc0b37ebd7da662ce435658891d660c2699bca438280d0ae51da992557a3a957 |
| 2 | [4096步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) | 0e19dd05fcdd58701aa1fd17e87739f05e60fe71a2a9bc60c162918607733b5b |

清单加载会核对原selection.json，不允许把final改称selected、按test挑流或开放speed。普通MADDPG.load不加载此格式；
使用NStepMADDPG.load(path, expected_n=8)，或有完整身份校验的pitch_nstep_handoff.load_candidate(manifest_path,run)。
新进程三候选×原18场验证共54回合，所有完整时序及指标与原保存值最大差0，网络参数/策略SHA未变。
这是加载/统一验证回放，不是新的独立性能证据。交接身份是experimental_candidates_not_default。

## 下一决策及跨任务边界

支持另一侧继续**只做工程适配**：独立可选TD目标、n1与原update精确等价、ring/episode/尾部、目标动作映射及恢复核查。
保留原speed父状态和全部原控制权限；本清单只供实验比较，不自动接管三通道父。
现阶段不支持把n8当已验证speed改进直接迁移或启动正式RL，原因是：

1. 公共锚点selected的额外方向改善较小、流2反向增多；同预算final对比依赖固定延续，未证明稳定机制改善。
2. 流2父能力保留失败，终点慢变收益减弱；n8存在off-policy偏差，pitch证据无法验证新speed动作分布。
3. speed自己的等价性/状态接管尚须由另一侧验证，本轮没有speed控制效果或稳定性实验。

若以后审阅单独TD目标的speed对照，应保留其原父和n1基线、重新预声明预算/门槛/独立测试；这是下一轮需审阅事项，本轮不执行。
不自动增加新的桨距改进候选，不把该建议解释为正式训练授权。

## 复现与证据

实际根目录./optimization_control/experiments/20261028_pitch_nstep_mechanism/。
原12图和旧实验没有改写，本轮不重复生成它们。后处理pitch_nstep_mechanism_review.py只读评分/旧结果，输出方向转移、九动作排名和保留表，不创建环境。

```powershell
Set-Location -LiteralPath .
$env:TF_NUM_INTRAOP_THREADS='1'
$env:TF_NUM_INTEROP_THREADS='1'
$py='./.venv/Scripts/python.exe'
& $py -B -X utf8 -m unittest optimization_control.tests.test_pitch_nstep_mechanism -v
# 全部重做须用新目录，现有完成目录只允许后处理；0正式训练、无test rollout。
$out='optimization_control/experiments/20261028_pitch_nstep_mechanism_repro'
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_mechanism prepare --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_mechanism run --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_handoff create --output $out
# 独立新进程同时完成三份加载和原18场统一验证回放
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_handoff replay --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_mechanism_review --output $out
```

- [匹配方向转移](../experiments/20261028_pitch_nstep_mechanism/critic_transition_summary.csv)
- [九动作排名](../experiments/20261028_pitch_nstep_mechanism/grid_ranking_summary.csv)
- [各策略自身闭环方向](../experiments/20261028_pitch_nstep_mechanism/own_policy.csv)
- [case/pooled能力保留](../experiments/20261028_pitch_nstep_mechanism/retention_audit.csv)
- [新进程加载与回放核验（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [最终预算/身份/源保护核验](../experiments/20261028_pitch_nstep_mechanism/final_verification.json)
