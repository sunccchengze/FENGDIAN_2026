# 桨距n8 gamma=.99/1配对实验结果（2026-10-29）

**固定98304步实验与一次新独立测试完成，gamma=1完整验收失败，不升级为默认策略。** 慢变selected相对同预算.99在validation差1.43%、新test差2.45%，两者0/3流改善；final分别只改善1.21%/1.03%，均未达到5%。gamma1流2 selected仍initial，其他风况能力保留和实际运动代价门槛也未全过。本轮预算和候选到此结束，不追加gamma、去动作项或换reward。

这是对[3b4acc9奖励一致性审计](PITCH_REWARD_ALIGNMENT_RESULTS.md)后、主对话已明确批准的[具体单因素方案](PITCH_REWARD_ALIGNMENT_CANDIDATE.md)的执行；[PITCH_GAMMA_PROTOCOL.md](PITCH_GAMMA_PROTOCOL.md)与实验config在学习前冻结。原方案文档保留其“当时尚未执行”的历史口径，实际结果以本文为准。离线排序更一致没有在本轮续训中转化为稳定慢变收益，不能把前轮离线菜单变化称为训练收益。

## 唯一改动、模型和父来源

两臂都n8，仅gamma=.99/1不同。保留逐步reward：

\[
r_t=100[-((P_{t+1}-P^*)/(15\times10^6))^2-.001\,\mathrm{mean}_{3\times3}(a^{exec}_t-a^{exec}_{t-1})^2].
\]

原始新旧回放reward不重标。采样时按该臂gamma即时计算实际m步和gamma^m bootstrap；true terminal不bootstrap、非终止缺尾按实际m。同步AlgorithmConfig、SequenceReplay和metadata，派生缓存清空。旧gamma=.99 Critic/target/Adam同源继承，不作额外校准或重置；gamma1起始值语义不匹配的限制保留，不能外推为冷启动gamma1普遍无效。

观测[3,15]、网络、LR、采样规则、执行器、奖励/惩罚、seed42主入口都不改；Actor只学pitch，yaw跟踪风向、speed继续相同的当前有效风速曲线。后续实际speed可因pitch影响闭环有效风速而不同，不是新开放speed学习。参考指令与实际执行器量分开保存，偏航观测取风向相对失配角，机舱heading另存。没有未来风速/功率输入。

模型为wind12-synthetic-7506554ac981，SHA `7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`。75项本轮源锁不变；model/config_used.json与training_report.json另外核对旧nstep冻结清单，SHA分别为658163d05742215bf304839218115d2c7f75d5e4cd79ba0a043b1da8d9876034、3996fbec8618e74e307d85a43224d667732d06ab2c39725a0dded98df74a25aa，均一致。没有改PINN或其模型契约。

原三父均来自20261023 validation选中状态，不利用已发布独立test重选。绝对根为./optimization_control/experiments/20261023_progressive_random_control：

| 流 | 父相对路径 | 累计插入 | SHA256 |
|---|---|---:|---|
| 0 | pitch_run_0/segment_000/step_00016384.pth | 32768 | 28e221e6f6e74096ef74e9a9375c638823a055c38232ef4d3b5e16a5026996ea |
| 1 | pitch_run_1/segment_000/step_00012288.pth | 28672 | 0fcb0b9d474db0d04b3ac2d86c91d2f39d66bb3c025e30d911ce79b2ba445821 |
| 2 | pitch_run_2/segment_000/step_00008192.pth | 24576 | e2897be535e5c9bae27acbecc5edd57460a8a038ba28719e366ab4c904309a05 |

各流内两臂初始online/target、六个Adam、回放/指针/序列ID及RNG一致；跨流原起点预算不同，流间SD不能全归因于本轮训练随机性。

## 实际执行、随机流和审计

2臂×3流×16384=98304新增环境学习步，各job7937次MADDPG.update调用，共47622次；单次调用内部包含三机Actor/Critic优化，不把内部优化器次数当新的环境预算。warmup512、update_every2、actor_lr1e-4、critic_lr.001、tau.01、batch64、capacity32768，白噪声std[0,.03,0]为归一化参考单位，末比例.2。

主SeedSequence熵为[42,20261029,purpose,run,...]，purpose5101场景九格排列、5102初态、5103探索；实际探索整数种子为3136298109、535851581、3377689212。train episode51000000+run1000+ep，validation52000000，test53000000，已知压力53009000系列；三个工作树维护config及顶层实验config再次扫描无冲突。384条设计/风数组、逐回合探索状态与完整噪声在训练前锁定，并独立重新生成逐值一致。

流0两臂先各128步检查，新增update均0，计入正式预算；均到4096退出后新进程恢复。总10个正常worker进程，774份检查点，每128保存、每4096验证。无未提交片段重算/失败attempt，无额外环境学习smoke。每个checkpoint的gamma/config/replay身份、更新/插入计数及选择历史核对；三流前512步行为逐字段一致，之后两臂采样起点和实际m一致，经验内容可因不同策略而不同。

专项工程为三真实父上的.99对原n8逐batch目标/loss/四网络/Adam/RNG精确一致，gamma1手算ring/terminal/短尾与新进程下一update精确恢复；共8次核验update没有进入正式训练或候选选模。两份工程恢复状态仅留证，不作候选策略。另2项纯数据报告测试验证单流/单风况退化与运动超限不能被总体平均掩盖、pooled与case均值不混淆。共4项不同单元测试，不重跑全项目suite。

评估分开记：30×18×128=69120验证步、P/PI验证4608、新test78848，共152576，低于冻结186368上限。test共有18个策略角色和2个共同基线，880条语义case指标；相同Actor映射复用后为12个不同策略映射+P/PI共14组、616条完整回合/78848行时序。别名保留，不把重复initial/selected/final当独立样本。

原始reward重构最大残差1.19e-7，完整验证/测试指标从保存时序复算最大差0；全部128步done/remaining和实际pitch硬约束通过，tol保持1e-9。新test的共同来流及机舱heading逐步核对，heading最大差0。运动指标由逐机实际量计算，包含首步；三机平均图不用于反推实际总行程。

实际运行版本Python3.12.14、NumPy1.26.4、Torch2.13.0+cpu、TensorFlow2.16.1，CPU单Torch线程。resolved_execution.json明确：base_config.training中旧2048步/warmup256/noise.15只是未读取的继承模板，本轮实际执行由顶层16384/512/[0,.03,0]控制，不能按旧模板重算预算。

## Validation：先判验收，不以test翻案

每格为完整18场case-RMSE均值，kW；selected按严格最低均值且含initial。相同角色权重没有额外独立证据。

| 流 | 父/initial | .99 selected步 | .99 selected / final | gamma1 selected步 | gamma1 selected / final |
|---|---:|---:|---:|---:|---:|
| 0 | 447.25 | 16384 | 432.68 / 432.68 | 8192 | 446.99 / 452.29 |
| 1 | 440.21 | 4096 | 431.75 / 442.20 | 4096 | 431.37 / 435.15 |
| 2 | 422.68 | 0 | 422.68 / 451.76 | 0 | 422.68 / 437.94 |

gamma1流0 selected仅较initial少258.26W（约.058%），不能仅凭selected_step>0称实质改善。两臂流2 selected均initial；gamma1新增选中点仅2/3，门槛要求3/3。

| 冻结验收项 | validation结果 |
|---|---|
| 慢变selected对.99均值减少≥5%、至少2/3流改善 | 差1.43%，0/3，失败 |
| 慢变final同要求 | 好1.21%，2/3，未达5%，失败 |
| 平稳/阵风逐流selected/final mean/worst对父与对照≤1.05 | 流0平稳final worst对对照+6.59%、对父+7.66%，失败 |
| final/selected≤1.25，常规final mean/worst对父与对照≤1.05 | 此终点稳定性子条件3/3通过，不代表完整验收通过 |
| 分风况/流实际行程与RMS速率对照比≤1.10 | 流0 selected平稳/慢变行程+13.66%/+11.56%；流2 final阵风+14.97%，失败 |
| 实际pitch幅值/速率 | 通过，无放宽tol |

完整18场mean±流间SD：父436.71±10.33，.99 selected429.03±4.51/final442.21±7.79，gamma1 selected433.68±10.06/final441.79±7.51kW。final按case均值相对对照只少.417kW，按pooled却450.84对449.84kW更差；相对父的case均值也更差。不能用退化对照的一个微小平均差宣称新增收益。

## 一次新test：风况、总体与压力全保留

六job/选择锁和pretest_audit冻结后才生成：三风况×2.70/3.30/3.90MW×两条轨迹×初态.03/.05=36常规；7.6/7.8m/s×4.35/4.55MW×.03/.05=8已知压力回归。P/PI共用同模型/天气/目标/初态/执行器，kp1.5、ki.08、bias.04、antiwindup.2、integral_limit.3不重整定。

以下均为case-RMSE算术均值±三训练流SD，kW。P/PI是一次共同评估，表中不提供伪造的三独立流SD；它们不是训练重复。所有指标均完整128步，未去启动段。

| 策略 | 平稳 | 慢变 | 阵风 | 常规36场 | 压力8场 | 含压力全部44场 |
|---|---:|---:|---:|---:|---:|---:|
| 父/initial | 447.52±27.34 | 370.54±16.99 | 436.30±21.94 | 418.12±20.59 | 1554.17±120.31 | 624.67±38.44 |
| .99 selected | 420.64±10.71 | 358.20±6.39 | 419.80±8.54 | 399.54±8.11 | 1448.57±67.78 | 590.28±18.40 |
| .99 final | 424.86±5.97 | 378.76±20.24 | 429.44±2.52 | 411.02±8.15 | 1415.44±48.56 | 593.64±8.54 |
| gamma1 selected | 422.24±11.53 | 366.98±11.86 | 418.92±9.25 | 402.71±9.69 | 1442.28±60.07 | 591.72±16.96 |
| gamma1 final | 426.70±7.70 | 374.87±7.68 | 432.63±13.02 | 411.40±7.63 | 1416.71±42.84 | 594.18±5.17 |
| P | 580.91 | 468.52 | 599.26 | 549.56 | 1321.09 | 689.84 |
| PI | 523.99 | 415.34 | 498.70 | 479.34 | 1321.09 | 632.39 |

同时交付pooled-RMSE，不能根据输赢改选汇总方式：

| 策略 | 慢变pooled | 常规pooled | 压力pooled | 全44场pooled |
|---|---:|---:|---:|---:|
| 父 | 386.82 | 437.19 | 1564.65 | 775.57 |
| .99 selected | 374.97 | 417.19 | 1456.94 | 726.87 |
| .99 final | 395.94 | 426.73 | 1423.09 | 719.17 |
| gamma1 selected | 383.18 | 419.31 | 1450.37 | 725.48 |
| gamma1 final | 390.79 | 426.79 | 1424.08 | 719.55 |
| P | 491.20 | 575.78 | 1329.55 | 769.84 |
| PI | 438.71 | 503.33 | 1329.55 | 727.10 |

典型汇总反向：全44场selected，gamma1 case均值591.72差于.99的590.28，pooled725.48却好于726.87。报告两者，不把这个反向称全面改善。父本身按全44场case均值624.67优于PI632.39，pooled775.57却差于PI727.10，说明“优于PI”必须带明确指标和范围。

## 配对差、终点退化与动作代价

下表是gamma1减参照的配对case-RMSE差，kW±三流差值SD，负为较好；场景与初态逐条对齐，数据相关，不作独立样本显著性或置信区间声明。

| 范围/角色 | 对同预算.99 | 对固定父 | 对PI |
|---|---:|---:|---:|
| 慢变selected | +8.78±8.01 | -3.56±11.39 | -48.36±11.86 |
| 慢变final | -3.89±15.21 | +4.33±24.61 | -40.47±7.68 |
| 常规selected | +3.17±3.93 | -15.41±10.92 | -76.63±9.69 |
| 常规final | +.38±13.46 | -6.72±22.79 | -67.94±7.63 |
| 全44场selected | +1.45±3.92 | -32.95±23.39 | -40.66±16.96 |
| 全44场final | +.54±9.81 | -30.49±33.60 | -38.21±5.17 |

对P的配对差及逐case差同样保存在test_comparisons.csv/test_paired_cases.csv，未省略失败case。平均优于PI是当前有限集的正面描述，不是gamma1优于原方法的证据：常规selected只87/108流×case槽位严格优于PI，final79/108；加压力分别87/132、79/132。压力24/24均差于P/PI，不能称各场稳定优于PI。只统计三流为训练重复，不把108/132个相关槽位当独立训练样本。

新test慢变selected相对.99差2.45%、0/3流改善，final好1.03%、2/3；final相对原父反而差1.17%。常规gamma1 selected/final相对.99差.79%/.09%，均没有新增整体收益。正面反例保留：流1 final常规401.63对.99的411.40kW，流2 final412.31对.99的420.80更好；但流2仍差于父389.02约5.99%。

gamma1 test final/selected逐流1.02610/.98064/1.05989；终点稳定性子条件仅2/3，流2因final对父mean>1.05失败。其他能力保留也失败：流0平稳final worst对照+6.24%、阵风mean+5.44%；流2阵风final mean对父+5.66%。这些不被总体小差或SD掩盖。

动作代价未通过：流0 selected慢变实际pitch行程比对照增加23.01%、RMS速率增加13.68%；平稳行程增加10.56%。这是逐机实际量统计，硬幅值/速率仍全部满足；不能用未越硬约束代替运动代价验收。姿态/行程并不是实测载荷或疲劳寿命，当前模型没有这类物理验收。

## 结论边界与交付

validation已先判失败，test结果不反向改选或更改门槛。gamma1在部分流/终点有正面结果，保留；完整目标未通过，当前不支持用它替代原桨距方法。前轮奖励排序诊断仍成立，但不足以证明折扣是唯一根因或保证新训练5%收益；多步行为回报off-policy偏差、Critic近似与gamma1旧值适配问题仍未由本轮消除。

压力全部保留且单列；此处仅是冻结合成准静态代理和统一运行曲线内的数值结果，没有本轮新增全局可达性搜索，更不是真实风机/高保真收益或不可达证明。不改PINN、不开放yaw/speed、不接手另侧网格搜索。

实验根：[20261029_pitch_gamma_control（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。

- config.yaml/namespace_audit.json/training_manifest.csv/random_states.json/data_lock.json：冻结配置、数据与实际随机状态。
- checkpoint_manifest.csv/policy_manifest.json/normalization.json：774份完整状态身份，18个initial/selected/final角色及固定物理归一化；策略仍为实验交付，不改默认。加载入口为pitch_gamma_trial.load_agent(checkpoint,gamma)，校验n8与gamma元数据，不用普通MADDPG分派猜格式。
- engineering.json/engineering/child.json、processes/、learning/evaluation_budget.jsonl：工程、新进程恢复、实际/保守预算。
- training_metrics.csv为探索行为完整回合；validation/test的aggregate、cross_stream、target_initial、paired_cases、paired_groups、comparisons及acceptance.json保存全部指标和门槛。
- 每个test角色的metrics.csv及traces.csv.gz；相同Actor角色的complete.json保存reused_from，沿别名找到同一完整时序。
- 模型附属契约、原共享状态的私有只读快照和复现检查分别在model_contract_verification.json、source_coordination/、reproduction_check.json；未修改原共享入口。

三张Python/Matplotlib图已逐张查看，未截启动段：

1. [validation_history.png](../experiments/20261029_pitch_gamma_control/validation_history.png)：三流完整验证历史和selected星标；下排MSE=pooled有符号偏差²+方差。跨case正负偏差可抵消，逐case/目标/初态分解仍在CSV，不能据pooled偏差小否认个别case持续偏差。
2. [test_comparison.png](../experiments/20261029_pitch_gamma_control/test_comparison.png)：三风况/常规/压力case均值±流SD、pooled菱形与实际运动比；运动槽位顺序为run0三风况、run1三风况、run2三风况。
3. [full_timeseries.png](../experiments/20261029_pitch_gamma_control/full_timeseries.png)：事前固定慢变3.90MW、repeat0、初始.03的三流完整128秒。左为有符号功率误差，右为三机平均目标/实际桨距；逐机、风速、heading及speed完整记录均保留，不从平均图推运动代价。

## 可复现命令

使用已有./.venv/Scripts/python.exe，模块在NumPy前启用已有pinn_tf216，不安装依赖。原轮执行顺序如下，**当前目录已完成，不重复训练**：

```powershell
$py = './.venv/Scripts/python.exe'
$out = 'optimization_control/experiments/20261029_pitch_gamma_control'
$env:TF_NUM_INTRAOP_THREADS = '1'
$env:TF_NUM_INTEROP_THREADS = '1'
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_trial prepare --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_trial engineering --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_trial launch --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_trial select --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_trial validation --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_review pretest --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_trial test --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_review review --output $out
```

prepare会拒绝重复占用本轮命名空间。需要**同数据完整复现**时用下面专用入口；这会另跑98304步，**本轮未执行**，也不能称新独立检验。它只复制配置/训练噪声及训练/验证输入清单，共享只读风文件并核对原父策略身份；不读取/复制本轮训练候选、selection或test结果。仅两份协调文档可重定位到同字节私有快照，数值模型/代码/父策略的身份检查继续严格执行。

```powershell
$newOut = 'optimization_control/experiments/20261029_pitch_gamma_reproduction'
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_reproduce --source $out --output $newOut --check-only
# 需要实际同数据复现时再去掉check-only；输出目录必须不存在。
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_gamma_reproduce --source $out --output $newOut
# 随后对$newOut执行上面的engineering、launch、select、validation、pretest、test、review，跳过prepare。
```

本轮验证了check-only和私有子目录中的准备复制/输入身份核对（均0环境步/0update），没有执行第二份复现训练。复制检查在reproduction_prepare_verification.json留证；未复制训练候选或旧test结果。普通局部测试命令：

```powershell
& $py -B -X utf8 -m unittest optimization_control.tests.test_pitch_gamma_reporting -v
# gamma核验已在engineering命令内运行，日志engineering/unittest.txt。
```

源码/协议/报告和必要元数据在独立pitch分支形成原子提交，权重/完整时序/图片按项目规则本地保留。未修改另一侧、原PROJECT_STATUS/TASKFLOW/README，未合并master或推送，未启动下一候选。
