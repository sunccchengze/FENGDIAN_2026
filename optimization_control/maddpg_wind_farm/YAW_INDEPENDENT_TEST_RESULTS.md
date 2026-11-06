# 三通道冻结方案独立测试与阶段验收（2026-11-05）

**按用户“三类风况各自平均 RMSE 严格低于共同 PI”的新目标，三通道冻结方案 Y selected 阶段验收通过，3／3 族满足条件。** 新独立测试总体 Y selected 为416.210 kW，PI为476.100 kW，平均低59.889 kW，即12.58%。原固定 C 为416.284 kW，新增 yaw 平均贡献仅.074 kW，Y 又比同预算 S selected 高.694 kW。这支持当前代理内完整控制方案的平均目标，新增权限收益仍须按其小幅结果解释。[冻结协议](YAW_INDEPENDENT_TEST_PROTOCOL.md) · [主验收记录](../experiments/20261105_yaw_independent/primary_acceptance.json)

## 冻结身份与独立性

部署候选继续使用旧 validation 选出的 Y 新步2048／0／2048、S新步2048／1024／1024，final均2048，父为原 C selected 0／0／4096。独立测试没有用于选模。23角色包含12个 Y／S selected／final、固定 C三流、公共 P／PI、Y两角色关闭yaw六个。全部按原计划实际执行，角色重合也各自实际回放；独立风况数为18，统计没有把重复角色当作新训练流。

原提案71000000…71000017被桨距工作树训练风占用。测试风生成前，按72000000、73000000、74000000的预定顺序扫描，前两段也已有使用／预留，改为首个空区间 **74000000…74000017**。更正仅因编号冲突，原提案和占用路径保留，释放前再次扫描。独立审查最终确认小试训练／修复没有已证实错误，更正后的测试设计可执行。[命名空间记录](../experiments/20261105_yaw_independent/namespace_correction.json) · [释放时独立审查](../experiments/20261105_yaw_independent/review_at_release.md)

主seed42、test split、128秒。三族各六条，来自2.75／3.35／3.85 MW三目标和初始pitch .025／.055 rad两初态组合。扫描三个工作区5069个已保存来流文件，得到3943条唯一float32完整波形；本次18条互不重复，且与这些已保存波形均无重合。数组、metadata摘要和环境输入均为同一float32合同。[风库身份与来源清单（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

## 三族平均与完整方案

先按每条完整128步误差计算RMSE，再对同族六风和三父流等权。PI每族六个实际回合，全部控制器共享同一来流、目标、初态及原执行器。单位kW。

| 方案 | 平稳 | 慢变 | 阵风 | 总体 |
|---|---:|---:|---:|---:|
| **Y selected** | **408.866** | **418.773** | **420.992** | **416.210** |
| Y final | 408.955 | 418.829 | 421.103 | 416.296 |
| S selected | 407.179 | 418.715 | 420.654 | 415.516 |
| S final | 408.487 | 420.095 | 422.175 | 416.919 |
| 固定 C | 408.953 | 418.859 | 421.039 | 416.284 |
| P | 520.569 | 576.781 | 589.349 | 562.233 |
| **PI** | **455.730** | **484.430** | **488.139** | **476.100** |
| **Y selected−PI** | **−46.864** | **−65.657** | **−67.147** | **−59.889** |

Y final 和 S selected／final 也满足三族平均低于 PI。固定 C 本身已满足同一平均条件。MADDPG三通道方案与“桨距反馈＋yaw／speed调度”的 P／PI 比较是完整控制方案比较，新增 yaw 的解释由同预算 S 和逐通道关闭对照承担。[全表](../experiments/20261105_yaw_independent/family_summary.csv) · [逐case指标](../experiments/20261105_yaw_independent/metrics.csv)

![独立测试分族均值（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

54个风况与父流的配对中，Y selected 相对PI有41个较低、13个较高。相对PI最差配对为Y1、74000004、平稳3.85 MW／pitch .025，Y为393.782 kW、PI216.998 kW，差+176.784 kW。Y自身最差回合为Y0、74000000、平稳2.75 MW／pitch .025，668.935 kW，PI对应799.161 kW。所有case均保留。

2000次seed42配对bootstrap以完整波形为重采样单位，每族6个，总体按族分层，先在同一风上平均三流。Y−PI三族95%描述区间为平稳[−128.119,+36.316]、慢变[−101.724,−32.168]、阵风[−114.624,−15.593] kW，总体[−92.565,−23.387] kW。平稳区间跨0，主判定仍按已冻结平均条件。区间没有增设硬闸。[配对统计与区间](../experiments/20261105_yaw_independent/comparisons.csv)

## 新增 yaw、同预算与后期退化

Y selected 相对固定 C／关闭yaw的分族差依次为−.087650／−.085760／−.047604 kW，总体−.073671 kW，描述区间[−.149702,−.005228] kW。54配对中16改善、20退化、18相同。Y selected／final关闭yaw的108个独立测试回合，与固定 C 完整轨迹逐值一致，Y1 selected与固定 C1 也逐值一致。

Y selected 对同预算 S selected 总体高.694296 kW，描述区间[−.308219,+1.906634] kW，54配对23较低、31较高。三个父流各自总体均值也均高于对应 S。Y／S 比较包含不同可训练模块和继承状态，Y使用空新yaw回放／Adam，S2继承原C2完整speed状态。当前结果没有给出新增yaw相对同预算speed的整体优势。

| 臂／流 | selected新步 | selected＝initial | selected kW | final kW | 对固定C改善 kW | final−selected kW |
|---|---:|---|---:|---:|---:|---:|
| Y0 | 2048 | 否 | 427.421 | 427.421 | .190 | 0 |
| Y1 | 0 | **是** | 431.279 | 431.537 | 0 | +.258 |
| Y2 | 2048 | 否 | 389.930 | 389.930 | .031 | 0 |
| S0 | 2048 | 否 | 426.796 | 426.796 | .815 | 0 |
| S1 | 1024 | 否 | 431.227 | 431.185 | .052 | −.042 |
| S2 | 1024 | 否 | 388.524 | 392.776 | 1.437 | +4.252 |

Y0、Y2在新风上仍有微小平均改善，Y1没有新增选中yaw学习收益。Y final总体比selected高.085854 kW，S高1.403204 kW。最大final／selected为S2的1.010943。5%比值只作诊断，后期退化没有从记录中消失。[逐流稳定性](../experiments/20261105_yaw_independent/per_stream_stability.csv) · [逐流分族表](../experiments/20261105_yaw_independent/stream_summary.csv)

![selected到final（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

## 权限、实际量与原门槛

| Y selected流 | speed修正绝对最大值 rad/s | 新yaw修正绝对最大值 ° | 来源与选中学习 |
|---|---:|---:|---|
| 0 | 0 | .062796 | 父speed selected仍初态，新增yaw为2048步 |
| 1 | 0 | 0 | 原父与新增yaw均保留零修正 |
| 2 | .023997 | .095112 | speed继承原C2已选4096步，新增yaw为2048步 |

speed栏指MADDPG有界修正，物理转速仍由参考曲线与原执行器共同推进。三通道工程接通和本轮平均方案目标已有证据，三流每通道均产生新增学习收益的结论仍不成立。Y final三流yaw均非零；S各流speed非零、yaw由原调度控制。全部角色yaw修正饱和率为0，完整通道记录见身份表。[角色与动作清单](../experiments/20261105_yaw_independent/identity_manifest.json)

最大实际heading和pitch速率为.001972034和.00872664626 rad/s，最大转速变化率为.048538688 rad/s²，均在原限制内。偏航执行器仍驱动机舱朝向，PINN实际失配为heading减实时来流再wrap。原400／500 kW联合门槛下，Y和S selected均0／3流通过，Y selected最差668.935 kW、pooled428.813 kW。该描述不改变用户本轮三族平均主判定。

![固定case17实际控制（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

图按释放前规则固定case17、流2，gust3.85 MW、初始pitch .055。Y2 selected与final权重相同，图中合并标识，两角色仍各自实际执行。三机完整heading／yaw／pitch／speed、命令、父动作、修正与功率均保存在逐case NPZ，图导出额外模型查询为0。

## 既有压力与模型范围

压力直接引用旧小试7.6 m/s、4.4 MW评估。Y selected1609.551 kW、S selected1611.426 kW、固定C1609.791 kW、PI1381.903 kW，Y高于PI227.648 kW。来源为旧测试／已知压力复评，新增压力case和模型查询均0。本轮没有新的独立压力通过结论。[旧压力表](../experiments/20261105_yaw_independent/known_pressure.csv) · [来源SHA](../experiments/20261105_yaw_independent/known_pressure_source.json)

已有PINN的yaw弱响应及部分响应方向问题、有限forecast信息表示和工程物理假设仍限定结论。新增yaw的平均作用只有数十W，整套方案对PI的主要优势来自父方案已有能力。报告范围为当前代理内软件实验，真实风场物理性能仍需要相应模型与独立依据。[既有模型限制](ANCHOR_CLOSEOUT_RESULTS.md)

## 查询、身份审计与复现

本轮实际414回合、53406行输入，含reset，硬限55000，余1594行。三worker分区实耗18576／18576／16254。414个预留全部完成，实际等于预留；失败与重试case为0。新增训练、优化器更新和候选替换为0。旧小试40422／42000预算单独保留。

414条RMSE从完整保存轨迹用独立math.fsum复算，最大差0 W。逐秒总命令MSE和奖励均逐值一致，宏保持、物理域与限速通过；参数摘要和更新计数逐角色前后相同。源小试275项、工程42项产物SHA仍不变。新产物约14 MiB，准确字节数、全部SHA和本地提交见交付记录。[独立数值审计](../experiments/20261105_yaw_independent/independent_numeric_audit.json)

评估入口为 [yaw_independent_test.py](yaw_independent_test.py)，统计与图入口为 [yaw_independent_report.py](yaw_independent_report.py)。锁记录保留候选和源码SHA、旧六val选模身份、PI参数、命名空间更正、审查及波形清单。一次释放和独占写入会拒绝覆盖既有运行。

```powershell
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.yaw_independent_test prepare
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.yaw_independent_test release
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.yaw_independent_test run
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.yaw_independent_report
```

重现需要冻结的原父、forecast、PINN与小试来源文件。现有结果可直接按清单和保存轨迹复核，重新执行须先在隔离目录建立新的输出身份和预算。本轮按一次独立测试和报告完成阶段交付。
