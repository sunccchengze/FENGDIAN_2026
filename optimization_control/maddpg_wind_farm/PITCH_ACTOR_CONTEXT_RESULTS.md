# Actor队友桨距条件单因素：完成对照，完整验收失败

2026-10-30。已完成获批的两臂三流配对续训、冻结选模和一次新独立测试。**仅把Actor损失中的队友桨距改为本次update入口缓存的当前策略值，没有带来足够、可重复的收益，不升级默认策略。** 已知3.8MW平稳薄弱组未达到5%改善，候选只有2/3流选中新增状态；慢变新测试selected比原更新差0.99%，final好1.25%，仍有其他风况退化。不能把平均优于PI解释成本项干预成功。

协议及先验门槛见[PITCH_ACTOR_CONTEXT_PROTOCOL.md](PITCH_ACTOR_CONTEXT_PROTOCOL.md)，动机和反证见[PITCH_REMAINING_FAILURE_RESULTS.md](PITCH_REMAINING_FAILURE_RESULTS.md)及[获批候选方案](PITCH_REMAINING_FAILURE_CANDIDATE.md)。本轮固定一个候选、98304学习步，未追加调参或重抽测试。实验根目录为[20261029_pitch_actor_context（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。

## 诊断依据及本轮能检验的问题

10月22/23日起点与最初慢变诊断见[PITCH_CROSS_WIND_RESULTS.md](PITCH_CROSS_WIND_RESULTS.md)。原策略并非所有慢变场都差于PI；当时流0、3.45MW慢变三初态存在持续欠发。4秒趋势筛查未通过，不能据此直接增加趋势输入。之后[n8对照](PITCH_NSTEP_RESULTS.md)的selected慢变收益通过原门槛，但流2final退化；[奖励审计](PITCH_REWARD_ALIGNMENT_RESULTS.md)和[gamma单因素](PITCH_GAMMA_RESULTS.md)也保留失败，未把动作惩罚认定为唯一原因。

本轮接在原n8验证选中的三份状态之后，使用训练/验证诊断，不从旧独立测试选父。前轮剩余失败核查在36开发case×三流的108槽位发现11处弱于PI，其中6处集中于同一3.8MW平稳波形的两种初态；10/11失败伴随更大的bias²和更小的variance，另1处是启动波动反例。当前15维观测已有误差、执行器状态及当前来流，不能把持续偏差直接归成缺少误差信息。

同一离线回放上，Actor参数梯度对“回放队友桨距/当前队友桨距”敏感，部分批次方向相反，因而提出一次有界条件替换实验。原MADDPG允许回放队友动作，本轮属于研究变体；梯度敏感性不证明哪种方向正确。本轮结果不支持将这一条件认定为足以解决持续欠发或遗忘的根因。

## 唯一干预、固定来源和执行契约

对照`replay`直接调用原n8更新；候选`current_pitch`在update入口、任何Actor更新之前，在no_grad下缓存所有当前投影策略。Actor i求梯度时，本机当前动作保留梯度，队友仅pitch坐标替换为缓存值并detach，队友yaw/speed逐位保留回放。Critic目标、原奖励及.001动作项、n8尾部/终止规则、gamma=.99、学习率、tau、采样、15维观测和两层64网络均相同。私有保存格式`pitch_actor_context_v1`使用[专用加载器](pitch_actor_context_algorithm.py)，不修改公共算法分派。

模型固定为`wind12-synthetic-7506554ac981`，SHA256 `7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`，引用原项目[trained.keras（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。它是准静态合成联调代理；不改PINN。MADDPG只学习pitch，mask=[0,1,0]；yaw跟踪风向，speed按统一曲线，各方法共用执行器和原`legacy_physical`参考模式。

三父来自[已验证n8候选清单](../experiments/20261028_pitch_nstep_mechanism/candidate_manifest.json)，不是gamma实验的.99 selected：

| 流 | 20261028_pitch_nstep下的完整父状态 | 父SHA256 |
|---|---|---|
| 0 | n8_run0/step_00016384/attempt_000/state.pth | 1f91cdba7676f1c32434e7e1e130cac6df155e4c41798ef6b88c6c58b032678a |
| 1 | n8_run1/step_00012288/attempt_000/state.pth | cc0b37ebd7da662ce435658891d660c2699bca438280d0ae51da992557a3a957 |
| 2 | n8_run2/step_00004096/attempt_000/state.pth | 0e19dd05fcdd58701aa1fd17e87739f05e60fe71a2a9bc60c162918607733b5b |

online/target四组网络、六Adam、完整回放时序和m统计、全部算法/回放/Torch随机状态均继承，不重置。初态核心指纹与父一致。父累计插入数49152/40960/28672不同，跨流SD同时包含已有策略差异，不能视为同一起点的三个独立seed估计。

主seed42；SeedSequence([42,20261029,purpose,run,...])，6101设计、6102初态、6103探索。探索三整数种子2400279337/594427830/4274659687；实际PCG64状态、逐回合前后状态与噪声SHA保存在[random_states.json](../experiments/20261029_pitch_actor_context/random_states.json)。两臂逐流同128回合来流/目标/初态/探索，配对回放采样索引及实际m一致。实际参数见[resolved_execution.json](../experiments/20261029_pitch_actor_context/resolved_execution.json)：每job16384步，warmup512，每2步update，共7937次；actor_lr=.0001、critic_lr=.001、tau=.01、batch64、回放32768，pitch白噪声std=.03衰减到.2倍。旧base_config.training模板的2048/256/.15不代表本轮实际执行。

两臂新增m=8采样占比分别逐流相同，为94.463%/94.534%/94.507%；每job507968个采样项，其余为终止附近m=1..7。统计扣除了继承前缀，见[actual_m_statistics.json](../experiments/20261029_pitch_actor_context/actual_m_statistics.json)。

## 选模、测试隔离及工程验证

新validation为三风况×2.9/3.5MW×.025/.04/.055，共18格；每4096步及initial评估完整128秒，严格按case-RMSE均值最小选择。已知36开发case全部保留，但只作回归，不参与本轮选择。低风压力即使历史split标validation也不参与选择。

| 流 | 父validation kW | 原更新selected步 / kW | 候选selected步 / kW | 原更新final kW | 候选final kW | 候选final较selected |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 392.51 | 16384 / 387.43 | 4096 / 388.00 | 387.43 | 401.45 | +3.47% |
| 1 | 387.92 | 0 / 387.92 | 0 / 387.92 | 413.97 | 395.67 | +2.00% |
| 2 | 391.29 | 8192 / 390.26 | 8192 / 391.09 | 419.19 | 412.08 | +5.37% |

候选流1仍保留初始策略，流2新增selected仅比父好0.20kW，不能称为三流学习收益。initial/selected/final均保留，仅manifest引用已有文件，无权重副本。

全部六job、选择、已知回归及[pretest_audit.json](../experiments/20261029_pitch_actor_context/pretest_audit.json)锁定后，才一次生成新test：三风况×2.725/3.325/3.925MW×两条新波形×.03/.05，共36常规case，外加8个已知压力case。命名空间61000000/62000000/63000000及63009000扫描无碰撞；压力是既知规格，不称全新压力发现。P/PI冻结kp1.5、ki.08、bias.04、antiwindup.2、integral_limit.3，未重新整定。

6项针对性单元测试通过。另8次内存工程更新全部丢弃、0环境/Plant输入：原臂在三真实父上下一更新与原n8精确一致；初始动作差0，队友参数梯度全None、本机非零；后续Actor读取同一入口快照，未被前序更新污染；新进程恢复后下一更新精确一致。run0两臂在128及4096处各恢复一次，共4次，均计入正式预算、无重算。全部10个worker及7个后处理阶段正常退出。

## 预先冻结的主薄弱组未改善到门槛

已知train_episode_8为平稳3.8MW，两初态.025/.055，完整回合平均，不裁启动段。门槛要求selected及final对原更新和固定父均改善≥5%，各比较至少2/3流改善，并且三流selected非initial。

| 角色 | 相对原更新RMSE变化 | 改善流 | 相对固定父RMSE变化 | 改善流 |
|---|---:|---:|---:|---:|
| selected | +2.18% | 0/3 | -1.37% | 1/3 |
| final | -0.55% | 1/3 | -2.81% | 2/3 |

均未达到5%。持续欠发没有消失，下面平均两初态，误差定义e=P-target，负为欠发；RMSE/平均误差/回合std单位kW：

| 流 | 固定父RMSE / bias / std | 原更新selected | 候选selected | 候选final |
|---|---:|---:|---:|---:|
| 0 | 471.37 / -244.16 / 402.99 | 454.29 / -213.77 / 400.63 | 480.29 / -255.48 / 406.49 | 467.77 / -209.75 / 418.02 |
| 1 | 560.39 / -374.70 / 416.50 | 560.39 / -374.70 / 416.50 | 560.39 / -374.70 / 416.50 | 505.95 / -246.54 / 441.68 |
| 2 | 507.49 / -296.72 / 411.29 | 471.14 / -203.72 / 424.73 | 477.54 / -201.91 / 432.72 | 522.32 / -335.24 / 400.32 |

同两case的PI为423.01 / -37.68 / 420.71kW。流2候选final的平均bias²=.11245MW²、variance=.16038MW²；原更新final为.09970/.16933MW²，PI为.00192/.17705MW²。较小波动可同时伴随较大持续欠发。逐case严格满足RMSE²=bias²+variance，方差ddof=0；上表是各case的统计量再平均，不能将上表平均RMSE平方硬等同于平均bias的平方加平均std的平方。

## 冻结后新测试：平均优PI，新增干预未通过

下表为完整case-RMSE均值，单位kW。候选±为三流各自均值的样本SD（ddof=1），不是置信区间；P/PI仅共同评估一次。同Actor角色复用时序并明确引用，不伪装成重复实验。

| 新测试范围 | 固定父 | 原更新selected | 原更新final | 候选selected ± SD | 候选final ± SD | P | PI |
|---|---:|---:|---:|---:|---:|---:|---:|
| 平稳12场 | 448.13 | 446.69 | 455.14 | 449.13 ± 7.15 | 454.77 ± 3.80 | 585.29 | 517.72 |
| 慢变12场 | 518.90 | 514.93 | 525.65 | 520.03 ± 9.35 | 519.10 ± 9.98 | 653.15 | 608.88 |
| 阵风12场 | 373.30 | 370.59 | 382.94 | 374.05 ± 9.55 | 380.11 ± 2.79 | 531.71 | 451.09 |
| 常规36场 | 446.78 | 444.07 | 454.58 | 447.74 ± 8.58 | 451.33 ± 4.95 | 590.05 | 525.90 |
| 已知压力8场 | 1496.59 | 1522.86 | 1532.83 | 1510.46 ± 71.20 | 1495.39 ± 74.50 | 1321.09 | 1321.09 |
| 全44场含压力 | 637.65 | 640.22 | 650.62 | 640.96 ± 19.96 | 641.16 ± 17.54 | 722.97 | 670.48 |

配对差Δ=候选-参考，负为更好，单位kW；每列同case/同训练流配对。全套差值与差值跨流SD在[test_comparisons.csv](../experiments/20261029_pitch_actor_context/test_comparisons.csv)，逐case在[test_paired_cases.csv](../experiments/20261029_pitch_actor_context/test_paired_cases.csv)。

| 范围 | selected Δ原更新 / ΔP / ΔPI | final Δ原更新 / ΔP / ΔPI |
|---|---:|---:|
| 平稳 | +2.44 / -136.16 / -68.59 | -0.37 / -130.52 / -62.95 |
| 慢变 | +5.10 / -133.12 / -88.85 | -6.55 / -134.05 / -89.78 |
| 阵风 | +3.46 / -157.66 / -77.04 | -2.82 / -151.60 / -70.98 |
| 常规 | +3.67 / -142.31 / -78.16 | -3.25 / -138.72 / -74.57 |
| 压力 | -12.41 / +189.36 / +189.36 | -37.44 / +174.30 / +174.30 |
| 全部含压力 | +0.74 / -82.01 / -29.52 | -9.47 / -81.81 / -29.32 |

selected慢变比原更新差0.99%、比固定父差0.22%；final比原更新好1.25%，比固定父仍差0.04%。常规总体selected也比原更新差0.83%、比父差0.22%；final比原更新好0.71%，却比父差1.02%。因此不能用final相对已退化的对照较好来认定超过已有能力。

| 流 | 常规父 | 原更新selected / final | 候选selected / final | 候选final较selected |
|---|---:|---:|---:|---:|
| 0 | 442.43 | 433.45 / 433.45 | 443.00 / 446.17 | +0.72% |
| 1 | 457.64 | 457.64 / 475.79 | 457.64 / 451.77 | -1.28% |
| 2 | 440.26 | 441.13 / 454.49 | 442.57 / 456.04 | +3.04% |

case均值与pooled RMSE含义不同，后者为先汇总全部平方误差再开方。候选selected常规pooled462.46kW优于PI544.09；但**全44场pooled770.60kW差于PI750.74**，即使case均值640.96优于670.48。final全44场pooled766.29也差于PI750.74。困难样本未删除，两种口径并列在[test_cross_stream.csv](../experiments/20261029_pitch_actor_context/test_cross_stream.csv)。

候选selected在常规108槽位中78处严格优于PI，final为81处；加压力后分别仍为78/132、81/132。压力selected/final均0/24优于PI。可以描述“本测试常规case平均优PI”，不能描述“各测试场景及训练流稳定优PI”，也不能把这一继承能力归因于本次更新条件。

## 能力保留、实际执行器与压力边界

主组外其余34个开发case、18个新validation、36个新test全部保留。门槛逐流逐风况检查case均值和最坏case≤参考1.05、弱于PI数不增；最坏比值是两组各自最大值之比，并非保证每一case都≤1.05。完整配对case仍交付。

| 检查 | 已知开发回归 | 新validation | 新test |
|---|---|---|---|
| 实际pitch幅值/速率硬边界 | 通过 | 通过 | 通过 |
| 风况能力保留 | 失败 | 失败 | 失败 |
| 弱于PI数量不增加 | 失败 | 失败 | 失败 |
| 实际行程/RMS速率≤对照1.10 | 通过 | 失败 | 通过 |
| 完整final稳定性 | 失败 | 失败 | 失败 |

具体反例：validation流0 final慢变均值较对照+13.24%、最坏+22.95%，相对父均值+16.10%；流2final平稳均值较父+9.23%。validation流1final慢变实际行程比1.1254、RMS速率比1.0766，行程超门槛。test流1final平稳均值虽较对照改善，但最坏比1.0632失败；流2final平稳最坏较父1.0563失败。test流0selected慢变弱PI数4，对照2；不能用总体均值遮盖。

三流final/selected常规均值比均≤1.25，但完整稳定性还要求final均值/最坏对父和同预算原更新≤1.05，故该子条件通过不代表整体通过。实际pitch均在[0,.22]rad，最大速率.00872664626rad/s（容差1e-9）；命令、实际量、速率饱和占比、幅值边界占比、实际行程及RMS速率全保留在各split的metrics/aggregate。

低风高目标压力固定7.6/7.8m/s、4.35/4.55MW和两初态，属于模型内压力描述。本轮未增加可达性扫描，沿用[初始诊断的数值估计与边界](PITCH_CROSS_WIND_RESULTS.md)；PI同约束表现更好说明存在更好的可执行闭环，不证明每秒目标可达、不证明全局最优、更不能外推为真实风机性能。控制输入不含未来风速/功率或测试信息。

## 预算、空间和独立交付核对

正式98304环境步、47622新增update；工程8次丢弃更新单列。实际训练Plant输入99072行=98304推进+768回合reset；评估217088推进、218784输入（含1696个reset），总317856行，低于381088总上限及278528评估推进上限。一次新test推进78848；14条不同Actor身份的时序被20个语义角色引用（含P/PI），880指标行不是880次独立执行。已知/validation语义指标分别720/360。

按批准的存储修订，每1024步保存全状态，run0两臂128步各额外一份，共104正式状态；工程仅1份输入。774份轻量commit包含初始及每128步轨迹/loss/来源，不是774份恢复权重。105个.pth合计2053774941B，最大19690453B；全实验最终空间及分类见[storage_stats.json](../experiments/20261029_pitch_actor_context/storage_stats.json)，低于3GiB。旧状态/失败attempt均未清理，未复制旧权重/回放目录，计划恢复重算0。

[独立交付复算](../experiments/20261029_pitch_actor_context/delivery_check.json)使用math.fsum从1696个真实完整128步回合复算RMSE/bias/std/MSE分解，RMSE最大差0W；独立重算验收与冻结判定一致，工程验证通过、性能验收失败。85项原模型/父/源码输入及11项分析源码SHA不变；数值结果没有因测试改写validation。

配置见[config.yaml](../experiments/20261029_pitch_actor_context/config.yaml)，核心测试指标见[metrics.csv](../experiments/20261029_pitch_actor_context/metrics.csv)，[policy_manifest.json](../experiments/20261029_pitch_actor_context/policy_manifest.json)记录18个角色的路径/SHA/严格加载器，[normalization.json](../experiments/20261029_pitch_actor_context/normalization.json)记录固定物理归一化、执行器、环境和模型契约。目标×初态×风况分组的RMSE、signed bias、std见known/validation/test_target_initial.csv；完整逐机原始轨迹在对应evaluations/*/attempt_*/traces.csv.gz，别名通过complete.json.reused_from解析。

Python图均已逐张查看，中文/坐标/单位/图例无裁切：

- [选模曲线与主组bias²/variance分解](../experiments/20261029_pitch_actor_context/validation_and_decomposition.png)。
- [新测试全风况/压力、跨流SD及pooled对照](../experiments/20261029_pitch_actor_context/test_comparison.png)。
- [事前指定主组代表的三流完整128秒时序](../../materials/洪祖名/20261106_optimization_final/README.md)：风速独立m/s轴，命令/实际分开；三机均值仅供展示，逐机运动统计取原始量。代表属于已知回归，不冒称新测试。

## 可复现入口与范围

当前完成目录只核验保存数据；写入入口拒绝覆盖，不能在原目录重跑select/test/review/figures。只读来源核验（本轮已通过，无第二轮训练）为：

```powershell
Set-Location -LiteralPath .
$py='./.venv/Scripts/python.exe'
$src='optimization_control/experiments/20261029_pitch_actor_context'
$new='optimization_control/experiments/20261030_actor_context_reproduction'
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_actor_context_reproduce --source $src --output $new --check-only
```

如另外执行同数据完整复现，使用不存在的新目录；这是同数据复现，不能称第二次独立泛化证据。先去掉上条命令的`--check-only`建立只含配置/噪声/清单的目录，再执行以下工程测试和源码冻结准备。它不复制旧权重/回放/选择/测试结果，仅引用只读训练验证风数据。不要再运行prepare，它的新命名空间防碰撞会拒绝已占用命名空间。

```powershell
@'
from pathlib import Path
import sys, unittest
from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
activate_runtime(Path('./.venv/pinn_tf216'))
from optimization_control.maddpg_wind_farm.pitch_actor_context_trial import context, js, put, digest
src=Path(sys.argv[1]).resolve(); out,cfg=context(sys.argv[2])
for suffix in ('reporting','bounds'):
    module='optimization_control.tests.test_pitch_actor_context_'+suffix
    suite=unittest.defaultTestLoader.loadTestsFromName(module)
    with (out/(suffix+'_tests.txt')).open('x',encoding='utf8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    assert result.wasSuccessful() and result.testsRun==2
    source=Path('optimization_control/tests/test_pitch_actor_context_'+suffix+'.py').resolve()
    js(out,out/(suffix+'_tests.json'),dict(status='passed',tests=2,plant_rows=0,optimizer_updates=0,source_sha256=digest(source)))
put(out,out/'verify_delivery.py',(src/'verify_delivery.py').read_bytes())
files=list(Path('optimization_control/maddpg_wind_farm').glob('pitch_actor_context*.py'))
files+=list(Path('optimization_control/tests').glob('test_pitch_actor_context*.py'))+[out/'verify_delivery.py']
assert not (out/'test_bank').exists() and not (out/'evaluations').exists()
js(out,out/'analysis_code_freeze.json',dict(status='frozen_before_known_and_test',test_bank_exists=False,known_evaluation_started=False,hashes={str(p.resolve()):digest(p) for p in files}))
'@ | & $py -B -X utf8 - $src $new
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_actor_context_trial engineering --output $new
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_actor_context_trial launch --output $new
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_actor_context_finish --output $new
# 完成后逐张查看三图，再运行新目录中的verify_delivery.py。
```

以上完整复现命令未再次开展训练。实际一次实验已留全部随机状态、环境时序、预算计数、恢复记录与阶段日志。源码在独立pitch分支形成原子提交，权重/轨迹/PNG仅本地保留；不合并master、不推送、不修改共享PROJECT_STATUS/TASKFLOW/README/PPT。speed历史17点方案的正向开发证据由协调侧提供，仍属于独立研究，不能记为本轮MADDPG学习收益；本侧未读取/复制其预测器。

本轮结束于“有诊断依据的单因素经配对训练和独立测试被否证”，保留原已交接n8候选及其流2final限制。后续需要新的可证伪机制与独立预算；本轮没有自动追加候选。
