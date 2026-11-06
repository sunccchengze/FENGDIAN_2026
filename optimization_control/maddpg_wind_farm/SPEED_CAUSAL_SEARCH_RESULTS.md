# 因果滚动 speed 搜索诊断结果（2026-10-29）

**完成；未获得跨 training/validation 三流可重复改善固定父的证据。** training 三流均值改善，validation 只有流0改善，流1/2退化。因此本轮不把诊断轨迹升级为已验证示范、不启动示范训练或新RL；不重试时域、候选、n或学习率。局部改善说明现模型中的speed并非完全无作用；本有限搜索失败不能证明三变量无法实现。

正式RL训练0、优化器更新0、新策略权重0，新独立test释放0。模型、旧产物、公共环境接口和默认控制器未修改；yaw仍等待响应复核。原三通道/优于PI目标及7ad3369的失败结论保留。

## 固定设计与因果边界

先冻结[协议](SPEED_CAUSAL_SEARCH_PROTOCOL.md)、[唯一配置](configs/causal_speed_search.yaml)，再做正确性预检和正式诊断。两种数据覆盖各3流×3风况×2目标，共36个128步完整回合。training取原预检表各流/风况2.6与3.8MW首次出现回合；validation沿用三风况×2.85/3.45MW、pitch=.04，不按收益挑case，不读已释放test选参数。

候选固定9个：零、共同±.10rad/s、三机各自±.10rad/s；预测12步、每8步重选，末端截断。预测中偏置保持，但父pitch及speed参考逐步读取该反事实世界自身当前观测；外部每时步也用本世界观测重算父动作，选中偏置最多保持8步。所有通道沿用同一执行器与原限制，未扩大权限。

预测风速、方向和TI只使用当前值持续假设。规划快照按白名单复制当前物理状态、previous_action、actuator状态/队列/滞后/步号及独立RNG，完全不复制原trajectory未来、inflow_trace或未来命令。模型无状态且只读，计数器不属于物理世界状态。不存在父世界未来pitch脚本或真实下一状态输入。

成本唯一为窗口mean((farm_power-target)/1e6)^2，单位MW²，无Critic、折扣、终值或动作惩罚。它匹配功率跟踪MSE，却不等于原训练reward（含动作变化惩罚）。零候选先列，只有严格更低成本才替换；在持续风假设下优于零，不保证真实未知未来回合不劣。枚举固定粗网格不是最优上界或真实物理MPC证书。

validation的固定父、n1/n8 selected/final及P/PI直接复用7ad3369保存的同case完整时序，0新增模型推进；其中P/PI共同六场在三父流配对表中复用，不算新增独立样本。training的7个对照用同一模型、风、目标、初态和冻结参数重放。完整控制方案比较不等于新增权限因果收益或同计算预算比较。

## 推进预算：内部预测和reset均计入

一次推进是一行三机状态的代理forward；batch B计B。计数器在本地predictor外，逐forward检查；分片前持久预占最坏预算，失败/中断保留且不自动重跑。

| 类别 | 计入的模型行数 |
|---|---:|
| 搜索内部预测，36×9×(15×12+8) | 60912 |
| 搜索真实回合，36×(128+1 reset) | 4644 |
| training 7对照，18×7×(128+1 reset) | 16254 |
| 真实正确性预检（含批量/单样本、分叉、reset） | 263 |
| mock正确性单测 | 376 |
| **合计** | **82449 / 100000** |

当前真实代理为82073行，单测mock376行也计入上限；比保守预占84106更少是因为终点预测窗口缩短。总API调用82438，与行数不同：一次9行代理batch和一次4行mock batch都按样本数计费。旧validation复用没有虚构成新推进。

4项单测通过。真实预检中9行batch对9次单样本最大功率差为0.875/0.750/1.6875 W，有效风速最大差2.38e-6m/s；没有宣称逐位一致，正式从一开始就固定逐样本，没有再探索已知差异路径。改变外界未来来流不改变规划分数和首动作；当前世界/RNG/执行器回滚、零分支等价均通过。全程未追加模型查询做参数选择。

## 固定父逐流比较

表中为每流六个case RMSE算术均值，单位kW；正改善表示误差降低。预声明要求training和validation各自三流都改善、各自总体至少1%，结果未通过。

| 覆盖 | 流 | 固定父 | 搜索 | 相对父变化 | 改善case |
|---|---:|---:|---:|---:|---:|
| training | 0 | 438.34 | 420.84 | -3.99% | 6/6 |
| training | 1 | 349.63 | 326.74 | -6.55% | 5/6 |
| training | 2 | 381.95 | 366.32 | -4.09% | 3/6 |
| validation | 0 | 364.34 | 354.05 | -2.82% | 4/6 |
| validation | 1 | 360.06 | 367.37 | +2.03% | 2/6 |
| validation | 2 | 336.13 | 336.59 | +0.14% | 3/6 |

逐case共training14/18、validation9/18改善。最大改善为train流2/ramp/2.6MW，441.13→342.73kW；最差反证为validation流1/ramp/3.45MW，224.31→256.26kW（退化14.24%）。完整36项保留在paired_parent.csv，不删除差case。

training总体case均值389.97→371.30kW，约改善4.79%；validation为353.51→352.67kW，仅约0.24%。另用所有时步汇总的pooled RMSE，training398.80→382.02kW，validation367.00→367.75kW，后者反而略差。case均值与先合并MSE再开方不是同一统计量，不能用微小均值下降宣布整体跟踪改善。

## 同场完整方案结果

每格为case RMSE均值 / signed bias均值（kW），bias=实际功率-target。training为已见子集；validation是本诊断使用场景，两者都不是新的独立泛化测试。

| 方案 | training RMSE / bias | validation RMSE / bias |
|---|---:|---:|
| 固定父 | 389.97 / +36.73 | 353.51 / +1.47 |
| n1 selected | 374.37 / -8.59 | 337.70 / -38.21 |
| n1 final | 393.42 / -60.39 | 348.58 / -94.20 |
| n8 selected | 373.91 / +0.61 | 336.67 / -30.93 |
| n8 final | 391.88 / -41.62 | 345.65 / -75.66 |
| 因果搜索 | 371.30 / +16.72 | 352.67 / +1.22 |
| P | 561.45 / +390.03 | 526.42 / +370.19 |
| PI | 466.89 / +214.29 | 417.15 / +178.05 |

搜索在此有限覆盖的均值低于PI，但validation仍差于已有n1/n8 selected/final，且不能重复改善父。不能据此把原“优于PI”整体目标宣布完成，也不能称搜索或新增speed权限的泛化收益成立。

## 动作、约束和规划代价

| 覆盖/方案 | mean归一化命令变化平方 | 三机speed命令总变差 rad/s | tracking return均值 | 动作惩罚return均值 |
|---|---:|---:|---:|---:|
| training 父 | .04425 | 9.27 | -9.0479 | -.5664 |
| training 搜索 | .04519 | 11.21 | -8.3025 | -.5784 |
| validation 父 | .05605 | 9.49 | -7.6623 | -.7174 |
| validation 搜索 | .06037 | 11.50 | -7.6937 | -.7728 |

return用原固定scale100、动作变化权重.001从保存时序重构，无折扣。validation搜索的tracking和动作惩罚都略差，不能把全部失败简单归因于Critic或奖励惩罚；本轮未搜索reward，另一对话的reward审计仍独立。

搜索实际最大heading/pitch/speed速率为.001969rad/s、.00872664626rad/s、.047206rad/s²，均在原限制内。speed总指令触及物理上下界的比例为0。576次规划中零候选11次（1.91%）、非零565次（98.09%）；所有非零候选本身就在±.10修正网格边界，不能把这一比例当作物理饱和的唯一原因或扩大权限依据。36回合都有候选切换，合计354次，实际是滚动反馈而非回放固定偏置。

平均每决策105.75次内部推进，每个外部时步平均13.21875次内部推进（另有外部自身查询）。本机单线程实测枚举/后验状态核对计时平均0.819s、经验p95约0.988s、最大1.082s；不含模型加载和规划前状态快照开销，不是硬实时或物理部署保证。

## 正确性、范围和结束决定

288条指标、36864行完整外部时序已复算，RMSE/bias独立实现复算最大差0。4608个搜索时步的父动作精确对应本世界当前观测，父RNG不变；实际命令、previous_action、8步内持有偏置和已观测风特征均核对。每个规划前后当前状态摘要不变，分支没有写真实世界。所有来源/执行SHA和旧目录清单保持一致，未保存新策略权重。

内部预测保留9候选成本、末步pitch及计时/计数，未保存所有逐步内部预测误差，因此不能无模型重算每项预测成本；实际闭环指标、预算、命令和成本选择次序均可从保存数据复核。因果性由白名单实现、真实未来扰动预检和每规划状态检查支撑。

**本轮选择“有限搜索未形成可重复验证改善”这一结论。** 训练子集有转速杠杆的正面证据，验证流1/2及部分case反证保留。9点粗网格、12步短视时域、8步重选、持续风假设、未预测未来控制序列和有限36回合都留下不确定性；没有排除其他因果预测或更合适控制序列的可能，也不证明代理中无可用余量，更不能否定真实三变量控制。

由于预声明重复改善条件未满足，不提出将本轨迹直接蒸馏为已验证教师的学习实施方案，不启动示范/价值校准训练，不改PINN或自动换下一配置。原三通道及优于PI目标保留；下一项决策交回主对话，不能拿剩余预算自动续搜。

## 产物和复现

根目录：./optimization_control/experiments/20261029_speed_causal_search。

- config.yaml、metrics.csv、summary.txt：冻结、逐case结果和结论入口。
- budget.json、precheck.json、tests.json、verification.json：逐分片预占/实际行数、批量差异、因果预检和复算。
- paired_parent.csv、stream_summary.csv、aggregate.csv、analysis_summary.json：逐case增益、三流、方案/动作/代价统计。
- trajectories.csv、cases/*/causal_demonstrations.npz：完整实际时序及当前obs/父动作/实际命令/偏置；仅为诊断记录，不是已验收示范策略。
- cases/*/search.json：9候选成本、选择、末步pitch、持续风和计时/计数；分片complete锁保护原数据。
- figures/parent_case_ratios、controller_comparison、causal_controls各PNG/PDF：Python图，均已查看。三机线型为实线/虚线/点线，实际状态和总命令分开显示。
- delivery_verification.json、git_delivery.json、output_manifest.csv：保存数据独立核查和提交/文件清单。

在本独立工作树使用已有./.venv/Scripts/python.exe。完整复现必须新建输出目录，依次执行模块optimization_control.maddpg_wind_farm.causal_speed_search的prepare、precheck、run、verify、figures，均传--output新目录。precheck前按下方执行4项单测并写tests.json；模块激活已有pinn_tf216，进程内TF/Torch线程固定1，无新依赖安装。原模型和检查点路径及SHA须可用；已完成目录只复查，不自动重跑run或未完成分片。

```python
# 用上述本地Python在独立工作树执行；先prepare新目录，再运行本段。
from pathlib import Path
import json, unittest, hashlib
from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
activate_runtime(Path('./.venv/pinn_tf216'))
import optimization_control.tests.test_causal_speed_search as tests
suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful()
rows = sum(tests.MOCK_ROWS)
record = dict(passed=True, tests=result.testsRun, mock_model_rows=rows,
              mock_api_calls=rows-3, per_case_mock_rows=tests.MOCK_ROWS)
# rows-3来自预算用例唯一4行mock batch：4行、1次API。
root = Path('optimization_control/experiments/20261029_speed_causal_search_reproduction')
(root/'tests.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
```

复现的单测及真实预检也包含在100000上限内；不能重复已完成预检而不记账。验证/图/交付checker只读保存数据，不新增代理推进。本轮本地原子提交，不合并master、不推送，不写共享PROJECT_STATUS/README/TASKFLOW。
