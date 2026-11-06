# speed 原9点与中幅17点单因素诊断（2026-10-29）

**完成；追加±.05rad/s中幅没有解决跨training/validation三流可重复收益问题。** validation总体case RMSE均值由9点352.67降到17点350.92kW，但流1仍比固定父差2.16%，validation相对父的总体改善仅.733%，未达原1%条件。training对9点两流略退、一流略进。因此保留否定结果，不启动新RL/示范训练，不释放新test，也不自动继续加密网格。

这不是三通道不可实现的判定。17点同状态预测确实可选到更低成本，中幅实际被选106次；但预测更低未转化成所要求的重复闭环收益。原9点、n1/n8和前述稳定化失败结果均保留。

## 范围与冻结

按[协议](SPEED_MIDGRID_PROTOCOL.md)与[唯一配置](configs/midgrid_speed_search.yaml)执行，仅在原9点后追加8个±.05rad/s中幅候选。原零、共同±.10、各机±.10的数值和顺序不变；严格沿原1e-12MW²顺序选最小成本，同分优先原项。预测H=12、每8步重选、当前风速/风向/TI持续预测、跟踪MSE、±.10rad/s权限、执行器和父策略均保持固定。没有尝试其他幅度、时域、频率或惩罚。

原[9点结果](SPEED_CAUSAL_SEARCH_RESULTS.md)来自2273d0af71fe258db25f3b2bba0ea1913e4b35ab，原36场及其父、n1/n8 selected/final、P/PI完整轨迹复用，未重跑旧9点。新17点从相同初态独立运行，并在每步读取自身当前观测重算父pitch和speed参考；只保持选中的speed偏置8步。零项回到当前参考，不是保持上一偏置或上一绝对目标，也不会消除已有状态差异。

training与validation各18场、每场128步；三父流×stationary/ramp/gust×各split两目标，源波形和初态按原manifest逐项锁定。此网格修改由已见validation反证提出，是开发诊断；不是新的独立泛化证据，不用既有test选择参数。正式RL步0、优化器更新0、新权重0、新独立test释放0。固定父不是本轮重新训练的同预算对照，故本轮不支持新增学习收益结论。

## 闭环结果

下表为每流6场case RMSE均值，单位kW；变化为17点相对9点，负值表示改善。

| 数据 | 流 | 固定父 | 原9点 | 17点 | 对9点变化 | 对父变化 |
|---|---:|---:|---:|---:|---:|---:|
| training | 0 | 438.34 | 420.84 | 422.12 | +.304% | -3.700% |
| training | 1 | 349.63 | 326.74 | 326.82 | +.025% | -6.524% |
| training | 2 | 381.95 | 366.32 | 365.25 | -.290% | -4.371% |
| validation | 0 | 364.34 | 354.05 | 353.69 | -.102% | -2.924% |
| validation | 1 | 360.06 | 367.37 | 367.83 | +.125% | +2.159% |
| validation | 2 | 336.13 | 336.59 | 331.24 | -1.589% | -1.455% |

原判据要求training和validation各自三流均严格改善父，并且各自总体case均值至少改善1%。17点training三流通过，总体改善4.763%；validation只有2/3流改善，总体.733%，**重复收益未通过**。17对9的training case均值反而增加.027%，validation下降.496%；不是一致优势。逐case完整配对见[paired_cases.csv](../experiments/20261029_speed_midgrid/paired_cases.csv)，不删除失败case。

全场等长，pooled为全部时步合并RMSE，等于case RMSE平方均值开方；bias符号为功率减目标，以下均为kW。

| 数据 | 控制器 | case均值 | pooled | worst | bias |
|---|---|---:|---:|---:|---:|
| training | 父 | 389.97 | 398.80 | 522.93 | +36.73 |
| training | 9点 | 371.30 | 382.02 | 519.89 | +16.72 |
| training | 17点 | 371.40 | 382.05 | 519.89 | +17.86 |
| training | P组合 | 561.45 | 601.07 | 941.68 | +390.03 |
| training | PI组合 | 466.89 | 487.55 | 677.92 | +214.29 |
| validation | 父 | 353.51 | 367.00 | 483.32 | +1.47 |
| validation | 9点 | 352.67 | 367.75 | 525.95 | +1.22 |
| validation | 17点 | 350.92 | 365.98 | 526.35 | +3.97 |
| validation | P组合 | 526.42 | 537.85 | 641.33 | +370.19 |
| validation | PI组合 | 417.15 | 428.34 | 537.40 | +178.05 |

17点validation pooled虽比9点和父低，但worst526.35高于父483.32。最差case为validation流1/stationary/3.45MW。validation流1/ramp/3.45MW更显示低绝对误差不代表权限收益：父224.31、9点256.26、17点262.12kW，17点比父差16.86%，即便三者都低于400kW。

分风况/目标的case均值如下，单位kW；每组的pooled/worst/bias、命令变化、实际运动和规划时间全部保存在[group_metrics.csv](../experiments/20261029_speed_midgrid/group_metrics.csv)，包括各流及n1/n8 selected/final。

| 数据 | 分组 | 父 | 9点 | 17点 |
|---|---|---:|---:|---:|
| training | stationary | 362.08 | 350.43 | 351.48 |
| training | ramp | 436.53 | 407.12 | 407.03 |
| training | gust | 371.31 | 356.35 | 355.69 |
| training | 2.60MW | 417.23 | 400.04 | 402.13 |
| training | 3.80MW | 362.72 | 342.56 | 340.67 |
| validation | stationary | 442.68 | 459.28 | 455.66 |
| validation | ramp | 266.48 | 269.26 | 267.97 |
| validation | gust | 351.37 | 329.47 | 329.13 |
| validation | 2.85MW | 392.83 | 383.74 | 381.62 |
| validation | 3.45MW | 314.19 | 321.60 | 320.22 |

原400kW均值/500kW最差的精度报告另列：training父/9/17均为1/3流通过；validation父3/3、9点和17点均2/3。17点training18场中11场≤400、15场≤500；validation为10场≤400、17场≤500。精度门槛、工程不劣与权限收益不互相替代。n1/n8原结果未改，复用的validation selected均值337.70/336.67、final348.58/345.65kW，不能据诊断控制器的数据替它们重新选模或改写原重复性结论。

## 动作、预测与计算代价

576次决策中，中幅106（18.40%）、原±.10端点468（81.25%）、零2（.35%）；9点原为端点565、零11。17点36场均有候选切换，共366次，原9点354次。106次中幅选择均有大于1e-12MW²的同状态预测成本优势，但这是17点当前世界内的前缀比较，不是原9点实际闭环成本比较。

三种控制器父/9/17的总speed指令触界比例和实际speed触及[.6,1.267]rad/s边界比例均为0（1e-6容差）。修正端点高频被选不能等同执行器饱和，也不能单独解释失败。以下是每场三机合计、含初始到首步的平均总变差；speed命令和实际speed单位rad/s，pitch/heading单位rad，归一化指令均方变化为逐时步/三机/三通道均值。

| 数据 | 控制器 | speed命令TV | 实际speed TV | 实际pitch TV | 实际heading TV | 指令均方变化 |
|---|---|---:|---:|---:|---:|---:|
| training | 父 | 9.271 | 2.153 | 1.978 | .278 | .044253 |
| training | 9点 | 11.208 | 3.084 | 2.083 | .278 | .045186 |
| training | 17点 | 11.017 | 2.979 | 2.076 | .278 | .045051 |
| validation | 父 | 9.493 | 2.217 | 2.121 | .307 | .056050 |
| validation | 9点 | 11.504 | 3.258 | 2.245 | .307 | .060371 |
| validation | 17点 | 11.207 | 3.065 | 2.240 | .307 | .060123 |

17点实际speed运动量比9点少，但仍比父多；降低动作量没有带来完整重复收益。父pitch权重与当前观测上的函数输出精确保留，但17点pitch实际轨迹相对父RMS差为training .01643rad、validation .02148rad，说明speed改变状态后，冻结父反馈仍会产生不同pitch轨迹。不能把它称为父权重漂移，亦不能排除通道补偿。全部控制器的heading-direction与gamma关系误差0。17点最大heading/pitch/speed变化率.001969rad/s、.00872664626rad/s、.047206rad/s²，均在原限制内，包含首步。

为对齐实际持有区间，只取每次选中项前8个预测误差与随后真实8步比较，所有窗口等长；不是拿12步成本与8步闭环直接相减。

| 数据 | 选中项预测8步pooled RMSE kW | 真实8步pooled RMSE kW | 预测误差序列减真实误差序列的pooled RMSE kW |
|---|---:|---:|---:|
| training | 294.28 | 382.05 | 364.29 |
| validation | 237.07 | 365.98 | 360.70 |

validation同窗口预测/实际偏离按stationary/ramp/gust为456.57/264.99/334.10kW，见[forecast_summary.csv](../experiments/20261029_speed_midgrid/forecast_summary.csv)和[全部576个窗口](../experiments/20261029_speed_midgrid/forecast_actual.csv)。两边使用同一代理、同一起点、同样保持8步的偏置；真实来流变化及其引起的父反馈分叉会带来差异。持续风假设值得独立审查，但这里没有将它确认为唯一根因，也没有验证模型物理准确性。

9点原计时mean/p95/max为.819/.989/1.082s；17点为1.714/2.530/4.701s。是不同执行时段的实际CPU观测，包含枚举和分支推进，排除规划前的当前状态快照/模型装载；不是受控硬件基准或实时性保证。17点正式内部输入行115056，原9点60912，计算量按17/9增加。

**后续边界：**本轮只验证了追加这一层中幅，不能穷尽所有控制序列或证明speed无可用作用。现证据不支持自动继续加密或启动示范学习；若另行立项，较值得先检查仅基于历史观测的因果风况预测及其闭环决策误差，固定H/决策间隔/网格/执行器做单因素比较，先在开发数据验证，不释放新test。当前代理仍是合成标签软件模型，未验证的物理响应不能靠更多训练解决；yaw继续沿[响应复核清单](PINN_YAW_RESPONSE_QUESTIONS.md)待核查，不擅自更改队友模型。

P/PI是统一“pitch反馈＋yaw/speed调度”完整方案；搜索方案额外使用代理预测和更多推理，其整体误差优于P/PI不能直接归因于MADDPG新增通道学习。新增speed价值仍需逐通道消融和同预算父续训，本轮未将搜索器替代为学习收益证据。

## 接管、因果性与审计

3项不同单测全部通过，共4次执行（535行mock的完整3项，fixture导入调整后1项5行），计540行mock输入。真实预检计545行：同状态9点成本精确等于17点前缀、细网格预测最小成本不高于原前缀、未来轨迹扰动不影响规划、零偏置与当前父动作精确一致、12步零闭环一致、外部状态和父RNG未变；批量推理调用0。采用已验证的单样本推理路径。

每次规划仅复制白名单当前物理/执行器/previous_action/RNG状态，预测风保持当前值。不会复制真实trajectory未来、未来父命令、旧9点下一状态或未来动作。每次规划保存全部17项逐步误差，可离线复算成本。前9项优势只在17点当下世界内成立；旧9点与17点分叉后的同一步号不是相同状态。

正式保存数据审计通过324条指标、41472行轨迹；独立math.fsum功率误差复算RMSE/bias差0，全部17项原始预测成本复算最大差4.44e-16MW²。4608个真实当前观测上重算父动作逐位一致、RNG未动、pitch/yaw指令逐位一致、上一动作特征和保存命令逐位一致；36场共同起点前9项成本精确等于旧9点。旧8种逻辑控制器36864行轨迹逐字段完全复用。所有场景逐步来流/目标相同，旧文件清单和冻结输入/执行代码SHA未变，新权重文件0。

图限于三组，均由Python/Matplotlib从保存数据绘制PNG/PDF并逐张检查标题、单位、图例和轴：

- [逐case的9/17相对父（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)：保留比父更差的case。
- [预测/实际、选择频率与规划代价（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)：同状态预测优势不等于闭环收益。
- [预定validation高目标ramp实际功率/三机转速/命令（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)：包括流0/1比父更差的轨迹；全部heading/gamma/pitch/speed见[原始时序](../../materials/洪祖名/20261106_optimization_final/README.md)。

## 预算与复现

逐行计数包括三机状态的一行模型输入、外部推进、reset、真实预检和mock。保守预占123648、硬上限170000；逐scope持久预占、逐forward检查，保留未完成scope，禁止隐性重跑。预检只做一次，正式36场每场3325行（内部3196、外部128、reset1）。图和保存数据审计不新增代理查询。

实际合计120785行：正式内部115056、正式外部4644（36reset＋4608transition）、真实预检545、mock540；其中真实代理输入120245。38个scope全部完成，没有恢复/重跑或未验证分片。17点36场外部执行与旧数据复用的8种控制器合计324条指标；本轮新增实际闭环只有4608步，不能把41472行全称为新增仿真或训练。

入口：[控制器及实验](midgrid_speed_search.py)、[保存数据核算与三组图](midgrid_speed_report.py)、[单测](../tests/test_midgrid_speed_search.py)。本地产物：[config](../experiments/20261029_speed_midgrid/config.yaml)、[逐case指标](../experiments/20261029_speed_midgrid/metrics.csv)、[状态摘要](../experiments/20261029_speed_midgrid/summary.txt)。其余case时序、当前世界动作与观测、全部预测误差、审计及图沿现行规则本地保留。

在此独立worktree执行，使用新的输出目录，禁止覆盖本轮或旧实验：

```powershell
$python = './.venv/Scripts/python.exe'
$out = 'optimization_control/experiments/20261029_speed_midgrid_reproduction'
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.midgrid_speed_search prepare --output $out
# 用下方单测片段生成新输出的tests.json，然后只运行一次precheck和run。
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.midgrid_speed_search precheck --output $out
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.midgrid_speed_search run --output $out
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.midgrid_speed_search verify --output $out
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.midgrid_speed_search figures --output $out
```

单测在独立Python进程运行，先激活现有runtime再导入numpy/Torch；复现完整3项535行，均计入预检/mock的1500行上限。本轮另执行的5行导入检查也如实记账，不要求复现时重复：

```python
from pathlib import Path
import json, unittest
from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
activate_runtime(Path('./.venv/pinn_tf216'))
import torch
torch.set_num_threads(1)
torch.use_deterministic_algorithms(True)
import optimization_control.tests.test_midgrid_speed_search as tests
suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful() and result.testsRun == 3
rows = sum(tests.MOCK_ROWS)
root = Path('optimization_control/experiments/20261029_speed_midgrid_reproduction')
(root/'tests.json').write_text(json.dumps(dict(passed=True, unique_tests=3,
    test_executions=3, mock_model_rows=rows, mock_api_calls=rows), indent=2), encoding='utf-8')
```

本轮只作当前十二输入合成标签代理内的软件比较。没有独立物理精度证书，不改队友模型、默认控制器、共享状态或另侧pitch实验；不合并master、不推送。三通道和优于统一P/PI的最终目标保留，yaw响应复核仍是开放yaw前的限制。
