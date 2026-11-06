# 因果历史风况：信息与闭环决策价值（2026-10-29）

**完成：固定历史预测在当前代理内同时产生了信息价值和闭环决策价值，原三流重复改善固定父条件通过。** training/validation的case RMSE均值分别364.32/340.78kW，相对固定父改善6.579%/3.601%，相对原17点改善1.907%/2.889%；两split均3/3父流均值改善。只形成冻结诊断候选和下一独立测试方案，不在本轮释放新test或启动RL。

这不是完整稳定化、物理泛化或新增MADDPG学习成功：validation最差509.60kW仍高于父483.32，5/18场比父更差，400/500kW精度仍只有2/3流通过；当前方案也不是已存策略中validation均值最低者。另有一次863.95s规划计时异常，保留并限制实时性结论。旧9/17点失败和全部不利case保持。

## 一次拟合与轨迹边界

按[运行前协议](HISTORY_FORECAST_PROTOCOL.md)和[唯一配置](configs/history_forecast.yaml)执行。唯一模型为32秒入口历史的正则线性直接多步预测，96个特征、36个响应，alpha=.1固定，一次闭式求解未来1..12秒，不扫validation。特征只有当前U/sin(theta)/cos(theta)和31个lag相对当前值的差；TI沿用当前已知常数，不拟合或计入预测收益。前史不足时重复首个已观测样本，不能从bank借用回合开始前数据。

fit_train使用seed42、新训练episode命名空间65000000起的600条128秒轨迹（每族200），与原环境入口分布一致；70200个完整12步训练窗口只来自这600条。标准化均值/总体标准差和目标均值均只取fit_train，截距不惩罚；没有读validation拟合或选参。Ridge求解残差最大3.33e-16，系数和统计量保存在本地[forecast_model.npz（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。训练风生成和线性拟合不调用PINN，不属于RL更新。

旧36个闭环case按入口float32值SHA去重后只有24条风：decision_train18、decision_validation6（每族2），后者在三父策略复用不能算18个独立风样本。fit_train、decision_train、decision_validation不交叠；训练/评分均按整条轨迹划分，不能把重叠预测窗口当独立样本。本validation已经参与此前开发，是留出评分集，不是新独立test。前述4秒差分/下一秒线性预测失败保持；本轮历史长度、训练估计器与1..12秒匹配任务不同，不能预设历史一定有新信息，也不据本次结果改写旧筛查。

## 预测层结果与冻结筛查

主区间1..8秒使用每轨迹t=0,8,..120共16个决策点；次区间1..12秒使用t=0,8,..112共15个完整点。均包含冷启动，不挑有利horizon；单步h=1..12全部保存在[metrics.csv](../experiments/20261029_history_forecast/metrics.csv)和[逐步预测](../../materials/洪祖名/20261106_optimization_final/README.md)。下表U MSE单位(m/s)²，ratio为history/persistence。

| 数据 | 区间 | persistence MSE | history MSE | ratio | 整轨迹分层bootstrap ratio 95%区间 |
|---|---|---:|---:|---:|---|
| decision_train，18条 | 1..8 | .219377 | .167593 | .76395 | [.71247,.85622] |
| decision_train，18条 | 1..12 | .271798 | .190469 | .70077 | [.65118,.78418] |
| decision_validation，6条 | 1..8 | .219647 | .163880 | .74610 | [.70635,.79192] |
| decision_validation，6条 | 1..12 | .274347 | .194760 | .70990 | [.68638,.73472] |

validation主区间按stationary/ramp/gust的ratio为.77008/.65175/.76202，分别改善22.99%/34.83%/23.80%，无族超过5%恶化。因此“总体严格改善、至少2/3族改善、无族>5%恶化”的运行前探索条件通过，才启动已授权闭环。bootstrap用seed42、2000次族内整轨迹重抽；每族仅2条，区间只描述这批轨迹的重抽不确定性，不证明新风况/物理泛化或控制收益。

validation逐h=1..12的U MSE ratio为.9629/.9053/.9197/.7452/.6745/.6927/.6613/.6559/.6793/.6883/.6867/.6200；不是只报告最有利的第8或第12秒。主区间U预测bias（预测减实际）+.04100m/s；方向wrapped角MSE9.90e-7rad²，persistence2.29e-5rad²。TI各回合恒定，预测误差0是已知常数保持，不计为学习收益。评分全部预测U域裁剪次数0、方向零向量回退0；冷启动与完整历史分开保存在后续审计表，仍以包含两者的主指标判定。

冷启动t<31与完整历史t>=31的1..8秒ratio，decision_train为.77307/.76065，decision_validation为.64445/.78712；1..12秒分别.69699/.70226、.65031/.73464，见[cold_warm_metrics.csv](../experiments/20261029_history_forecast/cold_warm_metrics.csv)。没有丢弃冷启动或根据其表现换初始化。

完整各族/每轨迹/两区间MSE、bias、裁剪与CI见[forecast_groups.csv](../experiments/20261029_history_forecast/forecast_groups.csv)。这是更长历史和多步估计器在当前入口设计内的信息价值证据，不是原4秒筛查的重复，也不是三通道学习成功。

## 闭环唯一变化与最终条件

只将1a7221a原17点规划器的持续风换成冻结history forecast。grid17、H12、每8步决策、tracking MSE、1e-12顺序选择、±.10rad/s修正、父当前状态反馈和执行器不变。每次预测只收本世界从reset到当前的已观测入口，反事实分支注入未来1..12秒的模型输出，不能读外部真实未来。父pitch和speed参考在各分支自身观测上每步反馈；真实闭环只保持选中speed偏置8步。

原36场相同初态、风况、目标与三父策略配对，旧17点及其9点/父/n1/n8/P/PI缓存核SHA后复用，没有重跑旧控制器。预测MSE改善不保证完整闭环改善。最终收益条件仍是training、validation各自三流均改善固定父，各自总体case均值至少改善1%；原400kW均值/500kW最差和工程不劣另报。正式RL训练/策略更新0，不拿失败轨迹作教师，不释放新独立test。

下表为每流6场case RMSE均值，单位kW；负变化表示改善。

| 数据 | 流 | 父 | 原17点持续风 | history17 | 相对原17点 | 相对父 |
|---|---:|---:|---:|---:|---:|---:|
| training | 0 | 438.34 | 422.12 | 421.08 | -.246% | -3.937% |
| training | 1 | 349.63 | 326.82 | 317.59 | -2.826% | -9.166% |
| training | 2 | 381.95 | 365.25 | 354.28 | -3.003% | -7.243% |
| validation | 0 | 364.34 | 353.69 | 351.67 | -.571% | -3.478% |
| validation | 1 | 360.06 | 367.83 | 352.36 | -4.206% | -2.138% |
| validation | 2 | 336.13 | 331.24 | 318.32 | -3.902% | -5.300% |

两split各自三流均改善父，且总体case均值均改善>1%，因此冻结的重复改善条件通过。14/18 training场和13/18 validation场改善原17点；对父为18/18和13/18。三流共享validation风，不能把这3次父策略配对当18条独立风或显著性检验。

全时步pooled、worst和bias（功率减目标）如下，单位kW；各场等长，pooled为case RMSE平方均值开方。

| 数据 | 方案 | case均值 | pooled | worst | bias |
|---|---|---:|---:|---:|---:|
| training | 父 | 389.97 | 398.80 | 522.93 | +36.73 |
| training | 原17点 | 371.40 | 382.05 | 519.89 | +17.86 |
| training | history17 | 364.32 | 373.86 | 515.85 | +8.47 |
| training | P组合 | 561.45 | 601.07 | 941.68 | +390.03 |
| training | PI组合 | 466.89 | 487.55 | 677.92 | +214.29 |
| validation | 父 | 353.51 | 367.00 | 483.32 | +1.47 |
| validation | 原17点 | 350.92 | 365.98 | 526.35 | +3.97 |
| validation | history17 | 340.78 | 357.18 | 509.60 | -6.64 |
| validation | P组合 | 526.42 | 537.85 | 641.33 | +370.19 |
| validation | PI组合 | 417.15 | 428.34 | 537.40 | +178.05 |

history17的均值/pooled/worst均优于原17点，但validation worst仍差于父，bias绝对值也增加。最不利的父配对是validation流1/ramp/3.45MW：父224.31、原17点262.12、history17为246.76kW，虽改善原17点，仍比父差10.01%。流0/stationary/3.45MW从原17点491.43变为498.96，父470.04；流1/stationary/3.45MW为509.60，父483.32。这些负结果全部保留，5%工程不劣不能替代均值收益，低于400kW亦不能宣布通道学习成功。

分风况/目标case均值如下（kW）；每组及逐流的pooled/worst/bias、命令和实际运动见[group_metrics.csv](../experiments/20261029_history_forecast/group_metrics.csv)，全部逐case配对见[paired_cases.csv](../experiments/20261029_history_forecast/paired_cases.csv)。

| 数据 | 分组 | 父 | 原17点 | history17 |
|---|---|---:|---:|---:|
| training | stationary | 362.08 | 351.48 | 349.71 |
| training | ramp | 436.53 | 407.03 | 402.20 |
| training | gust | 371.31 | 355.69 | 341.05 |
| training | 2.60MW | 417.23 | 402.13 | 387.14 |
| training | 3.80MW | 362.72 | 340.67 | 341.49 |
| validation | stationary | 442.68 | 455.66 | 446.20 |
| validation | ramp | 266.48 | 267.97 | 247.29 |
| validation | gust | 351.37 | 329.13 | 328.86 |
| validation | 2.85MW | 392.83 | 381.62 | 367.24 |
| validation | 3.45MW | 314.19 | 320.22 | 314.32 |

原400kW均值/500kW最差门槛：training父/原17/history均1/3，validation分别3/3、2/3、2/3；history逐场≤400/≤500计数为training12/15（共18）、validation11/17。复用n8 selected的validation均值336.67仍低于history340.78；不能把本轮称为全部已存策略最优，或据此修改旧selected/final及训练结论。

## 实际运动、预测实现与计时限制

每场三机合计、含初始到首步的平均总变差如下；speed命令/实际speed单位rad/s，pitch/heading单位rad；指令均方变化是每时步、三机和三通道平均。

| 数据 | 方案 | speed命令TV | 实际speed TV | 实际pitch TV | 实际heading TV | 指令均方变化 |
|---|---|---:|---:|---:|---:|---:|
| training | 父 | 9.271 | 2.153 | 1.978 | .278 | .044253 |
| training | 原17点 | 11.017 | 2.979 | 2.076 | .278 | .045051 |
| training | history17 | 10.411 | 2.640 | 2.045 | .278 | .045079 |
| validation | 父 | 9.493 | 2.217 | 2.121 | .307 | .056050 |
| validation | 原17点 | 11.207 | 3.065 | 2.240 | .307 | .060123 |
| validation | history17 | 10.801 | 2.818 | 2.185 | .307 | .060305 |

speed和pitch运动量相对原17点下降，但实际speed运动仍多于父，整体指令均方变化略增，不能说所有运动代价都改善。父在同一实际观测上的pitch/yaw动作逐位保留；history17实际pitch相对父RMS差training .01584rad、validation .02058rad，相对原17点为.01572/.01559rad。speed改状态会改父反馈，不是父权重漂移。heading-direction与gamma关系最大误差0。history17最大heading/pitch/speed速率.001969rad/s、.00872664626rad/s、.054155rad/s²，均在原限制内，包含首步。

576次决策中history17零3、原±.10端点393、中幅180（31.25%）；原17点为2/468/106。候选切换351次，原17点366。两方案speed总指令触界和实际speed触及[.6,1.267]rad/s边界比例均0（1e-6容差），修正端点选择不等于执行器饱和。控制误差变化不能只归因于某一通道边界。

选中项的前8步预测误差与随后真实8步比较，history17的预测/实际误差序列差的pooled RMSE为training329.96、validation325.03kW，原17点364.29/360.70；偏离减小但仍明显，见[forecast_realization.csv](../experiments/20261029_history_forecast/forecast_realization.csv)。这里的两版本来自各自状态和选择，不能把误差差值当同状态最优动作价值；本次单因素闭环配对才是决策价值证据。风速和风向预测同时替换，不将收益单独归给U。

规划计时原样报告：history17 mean/median/p95/max为2.481/.894/1.391/**863.951s**；原17点mean/p95/max为1.714/2.530/4.701s。异常发生在train_run0_ramp_3800000、t=40，一次正常204行预测规划；576次中仅此一次>8s。现有日志没有CPU时间或暂停/调度记录，不能判定原因，不删除异常或重跑改善统计，也不据较低median/p95宣称速度优势或实时性。上述时间包含预测/枚举/分支推进，排除规划前状态快照和模型装载；两实验运行时段不同。

## 冻结候选与下一独立测试方案（本轮不释放）

冻结候选仅指history17诊断控制器：forecast_model SHA256为`a5571a19354015c8b5997823748fafd7f0a6a355a0422d35b539e4faa3992877`，配原三父SHA、固定32样本/alpha.1、grid17/H12/8步/成本/执行器和本轮源代码摘要；见[candidate_manifest.json](../experiments/20261029_history_forecast/candidate_manifest.json)。没有新Actor、selected/final检查点或RL收益结论，不将36场轨迹升级为已验证教师。

后续提案：新test命名空间66000000+i（seed42、split=test，三个工作树检查无既有配置撞号，仅预留而未生成），三风况×目标2.75/3.35/3.85MW×初始pitch .025/.055rad，共18条独立新入口、每条配原三父共54场。其余入口分布/128秒/执行器原样；波形在下一次授权执行时才生成和锁SHA，模型/标准化不重新拟合，不用test重选模型或变超参。三父复用仍只算18条风。

同风配对history17、持续风17和父；统一P/PI在18个公共case上各跑一次。预计PINN行：两搜索器各179550、父6966、P/PI4644，合计370710，另行冻结含预检的预算（不占本轮170000，也不在本轮执行）。记录每次CPU和wall时间及暂停证据，同时保留所有长调用，不能只报告排除异常后的数字。

独立测试拟沿用三流父均值严格改善、总体≥1%的收益原则；预测器新增价值另要求三流均改善持续风17且总体≥1%。同时列pooled/worst/bias、每case5%工程不劣、400/500kW及运动代价，不用均值掩盖不利case。所有判断在生成前锁定；任何不通过都保留并停止，不按test续搜。此处是待执行方案，没有新test结果。

## 验证、预算与复现

4项不同测试通过：3项纯预测测试无PINN/mock推进；1项规划mock检查计821行。真实预检845行：未来数据扰动不改规划、persistence适配器17项成本与旧实现精确一致、原状态/父RNG未变、零修正12步闭环逐位一致。保存加载预测逐位重放通过。全程单样本代理推理，不调用已知不逐位一致的batch路径。

PINN/mock硬上限170000；正式36场每场3325行（内部3196、外部transition128、reset1），预检/mock预占2000，保守121700。生成600条训练风、线性拟合、预测评分及离线核算均不调用PINN。预算持久化按scope预占，禁止隐性重跑；旧结果源保护与本轮执行代码分别锁SHA。

实际总计121366行＝正式内部115056＋正式外部4644＋真实预检845＋mock821；真实PINN行为120545，38个scope全部完成，无重复分片。360条闭环指标/46080行轨迹中，41472行是旧9种控制器复用，新增实际闭环4608步。预测层336条指标/4512条逐步预测独立保存，不与功率RMSE混算。

正式与独立保存数据审计通过：预测MSE/功率RMSE/bias复算差0；全部17项逐步误差离线成本最大差6.66e-16MW²；600条训练数据重算标准化和目标均值逐位一致，normal equation残差3.33e-16，未重新求解/拟合；4608步父动作逐位重放、上一动作特征、执行命令、父RNG和36场实际入口/目标一致。576次预测的历史长度/SHA及未来预测逐位重放，外部未来扰动不改输出。41472行缓存逐字段复用，旧文件清单/输入/执行代码SHA不变。补充汇总脚本一次NumPy整数JSON序列化问题已转普通整数修正；没有追加PINN或改动原始结果。

三组图均为Python/Matplotlib、PNG/PDF同图导出，已逐张检查标题/单位/图例/轴：

- [预测MSE的全时域与整轨迹配对（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，保留training个别预测退化轨迹。
- [完整36场闭环相对父的比较（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，保留比父/原17更差的case。
- [预定validation高目标ramp实际功率/pitch/speed/命令（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)；全部heading/gamma等见[loop_trajectories.csv](../../materials/洪祖名/20261106_optimization_final/README.md)。

复现入口：[预测与评分实现](history_wind_forecast.py)、[训练bank/冻结实验](history_forecast_experiment.py)、[有条件闭环](history_speed_search.py)、[审计与三组图](history_forecast_report.py)。在本独立worktree用新的输出目录执行，不能覆盖本轮：

```powershell
$python = './.venv/Scripts/python.exe'
$out = 'optimization_control/experiments/20261029_history_forecast_reproduction'
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.history_forecast_experiment prepare --output $out
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.history_forecast_experiment evaluate --output $out
# 检查screen.json：未通过立即停止。通过后用下面片段记录单测预算，再执行：
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.history_speed_search precheck --output $out
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.history_speed_search run --output $out
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.history_forecast_report verify --output $out
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.history_forecast_report figures --output $out
```

单测片段在独立Python进程、现有runtime中运行，不重跑旧测试套件；数值测试用的toy拟合不是候选搜索：

```python
from pathlib import Path
import json, unittest
from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
activate_runtime(Path('./.venv/pinn_tf216'))
import torch
torch.set_num_threads(1)
torch.use_deterministic_algorithms(True)
import optimization_control.tests.test_history_forecast as forecast_tests
import optimization_control.tests.test_history_speed_search as planner_tests
suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(m)
                           for m in (forecast_tests, planner_tests)])
result = unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful() and result.testsRun == 4
rows = sum(planner_tests.MOCK_ROWS)
root = Path('optimization_control/experiments/20261029_history_forecast_reproduction')
(root/'tests.json').write_text(json.dumps(dict(passed=True, unique_tests=4,
    mock_model_rows=rows, mock_api_calls=rows), indent=2), encoding='utf-8')
```

本轮只报告当前合成标签代理的软件实验。P/PI使用统一pitch反馈加yaw/speed调度，与预测搜索器的误差比较是完整方案比较，不能归为新增MADDPG学习收益；后者仍需逐通道消融与同预算父续训。队友PINN、共享源码/项目状态、另一侧pitch实验未修改；本地提交，不合并master或推送，不开放yaw。
