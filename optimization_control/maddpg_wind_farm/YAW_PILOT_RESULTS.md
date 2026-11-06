# 偏航 Y／转速 S 三流小预算学习结果（2026-11-05）

**Y selected 在旧 validation 的平稳、慢变、阵风均值均严格低于共同 PI，筛查主条件 3／3 通过。** Y 比固定 C 平均低 .108 kW，比同预算续训 S 高 .413 kW。新增 yaw 只有两流选中新增训练点，第三流仍为 initial。同预算对照未显示 yaw 整体优于继续训练 speed。[冻结协议](YAW_PILOT_PROTOCOL.md) · [选中身份](../experiments/20261105_yaw_pilot/selection.json)

六 job 共完成 12288 个新增物理步、582 次联合更新。Y 只训练 ±1° yaw，S 保持 yaw 调度并续训 .1 rad/s speed。两臂每流均 2048 新步、97 次更新、同风同目标同初态、新探索 RNG 配对。全部选模只用原六条 validation，本轮没有新的独立测试。

## 分族等权主表

每场完整 128 秒计算 RMSE，再对各族两个风况、三个父流等权平均。PI 每族两个实际回合，各父共享同一 PI。单位 kW。

| 方案 | 平稳 | 慢变 | 阵风 | 总体 |
|---|---:|---:|---:|---:|
| Y selected | **457.593** | **404.169** | **270.413** | **377.392** |
| Y final | 457.616 | 404.307 | 270.450 | 377.458 |
| S selected | 457.080 | 402.619 | 271.236 | 376.978 |
| S final | 459.054 | 403.899 | 272.173 | 378.376 |
| 固定 C | 457.480 | 404.197 | 270.821 | 377.499 |
| P | 661.105 | 658.942 | 450.064 | 590.037 |
| PI | **580.209** | **511.381** | **357.944** | **483.178** |
| Y selected−PI | **−122.615** | **−107.212** | **−87.532** | **−105.786** |
| Y selected−S selected | +.514 | +1.549 | −.824 | +.413 |
| Y selected−固定 C | +.114 | −.028 | −.408 | −.108 |

固定 C 也满足三族均值低于 PI，Y 的新增偏航改善集中在阵风，平稳族相对父略退化。主条件比较完整控制方案，新增权限的作用由逐通道消融与同预算 S 比较解释。[完整分族表](../experiments/20261105_yaw_pilot/family_means.csv) · [逐对差值](../experiments/20261105_yaw_pilot/paired_differences.csv)

## 三流选模与后期退化

下表 RMSE 为六风等权均值，步数均指本轮新增预算。initial／1024／2048 严格均值最小，平手取早。

| 臂／流 | selected 新步 | selected＝initial | selected kW | final kW | final−selected kW |
|---|---:|---|---:|---:|---:|
| Y0 | 2048 | 否 | 389.869 | 389.869 | 0 |
| Y1 | 0 | **是** | 379.427 | 379.625 | +.198 |
| Y2 | 2048 | 否 | 362.879 | 362.879 | 0 |
| S0 | 2048 | 否 | 388.792 | 388.792 | 0 |
| S1 | 1024 | 否 | 379.171 | 379.377 | +.206 |
| S2 | 1024 | 否 | 362.973 | 366.958 | +3.985 |

Y0／Y2 相对各自固定 C 分别改善 .174／.149 kW，Y1 的选中模型无新增 yaw 学习收益。S 三流分别改善 1.250／.256／.055 kW。Y−S 配对只有 Y2 优于 S2，另外两流较差。Y final 比 selected 总体高 .066 kW，S 高 1.397 kW。最大 final／selected 为 S2 的 1.010978。比值和 1.05 标记只作诊断，本轮用户主判据没有附加稳定性硬闸。[逐流表](../experiments/20261105_yaw_pilot/stream_summary.csv)

![验证进展（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

原 400／500 kW 联合门槛仍按原定义报告。Y、S selected 均 2／3 流通过。Y0 最差 508.778 kW、S0 505.494 kW，因而未达到三流全通过。均值阈值、最差值和用户本轮主条件分别保留。[逐流原精度审计](../experiments/20261105_yaw_pilot/final_saved_audit.json)

## 消融、动作和压力

Y selected／final 关闭 yaw 的 36 个回合与各自固定 C 完整轨迹逐值一致。两臂 initial 的 36 个回合也与固定 C 一致。Y 对固定 C 的 .108 kW 改善同时等于对关闭 yaw 的改善。它由两流选中新增 yaw 修正产生，所选三流 speed 父仍为原 C selected 的 0／0／4096，前两流没有新增选中的 speed 学习修正。

Y0、Y1、Y2 selected 的 yaw z 绝对最大值为 .061466／0／.088152，物理参考修正最大为相同数值的度数。selected 的 yaw 归一化修正饱和率均为 0。三流实际机舱最大速率 .001985022／.001971568／.001972867 rad/s，低于原 .005 rad/s 限制。全通道执行器饱和比例约 .15，保留于逐场指标，不能据此指定单一退化原因。

![实际 yaw 与误差（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

图固定为 Y2、旧 gust 验证第 4 场，selected 与 final 身份相同，因此曲线重合。图中实际 yaw 为实际机舱朝向减实时来流，受风向和执行器动态共同影响。完整轨迹含三机实际量、命令、父动作、speed 和 yaw 修正。导出图的额外模型查询为零。

已知 7.6 m/s、4.4 MW 压力单列。Y selected 平均 1609.551 kW、S selected 1611.426 kW、固定 C 1609.791 kW，共同 PI 为 1381.903 kW。Y 比 PI 高 227.648 kW。包含压力的总体和 pooled 口径另列于 CSV，压力不混入三族主均值。[压力表](../experiments/20261105_yaw_pilot/pressure.csv)

## 来源、恢复与失败记录

独立实现审查明确无已证实阻断后才释放训练，其快照 SHA 为 `40892662577ef62507278aafcd2a77c6889fd37a0b66988822ae817fcf92dfb3`。G1 精确 `[1,0,−1]` 纯投影得到 `[+.017453292385,0,−.017453292385]` rad。G2 复用 9 组工程全轨迹。G3 确认 C2 的 online／target speed 有 12 张量不同，yaw 背景始终用 C 部署在线映射。G4 正式 envelope 绑定尺度、权限、父／forecast 和原参考模式，拒绝工程／旧 speed、换流、换尺度及权限变更。[审查快照](../experiments/20261105_yaw_pilot/review_snapshot.md) · [启动预检](../experiments/20261105_yaw_pilot/preflight_001.json)

Y 各流从确定性零 yaw 和空回放／Adam 开始。S0／S1 重建正式初态，S2 继承原 C2 的 4096 步、225 次更新、512 条宏回放及抽样状态。S2 最终累计为 6144 步、322 次更新，本轮新增仍只有 2048 步、97 次更新。所有探索衰减、warmup 和更新时间按本轮新增步计算。两臂比较包含可训练模块和继承状态差异。

共保存 12 份 1024／2048 完整状态。每份写盘后按正式入口加载，current／target、Adam、回放、RNG、计数和边界字段逐值比较，1024 步后直接用恢复对象继续。实际 96 个训练回合和 582 次更新日志已复算。6 job 的三个点、28 个对照评估范围共 46 个预留均完成，实际等于预留。

首次启动因新训练风库 float64 存储与 float32 波形摘要不一致，在读取阶段停止，模型查询和训练步为零。原始风库、源码和失败进程日志保留。修复仅将同一批风转为环境实际使用的 float32，48 条物理来流逐值不变，命名空间无占用，48 波形唯一。`repair_001/amendment.json` 绑定原锁、原源码和修复源，完整状态绑定有效修订锁摘要。[修复登记（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

首次保存数据报告同样因旧 validation 风库为 float64、实际环境输入为 float32 而停止。查询为零，尚未写入数值报告。保留运行时冻结报告源码，使用 [保存数据报告入口](yaw_pilot_saved_report.py) 在对照前执行与 `env.reset` 相同的 float32 转换，所有逐值断言继续执行。算法和已完成训练不重跑。

原工程 42 项产物及来源锁仍不变，旧正式失败和桨距成果保留。当前 36 维 forecast 与边界观测是有限信息表示，此处没有给出完整 Markov 性证明。已有 PINN yaw 弱响应和部分符号异常仍限制软件结果的物理解释。[模型限制](ANCHOR_CLOSEOUT_RESULTS.md)

## 预算、候选与复现

小试实际 37023 行，加原工程 3399 行为 **40422／42000**。两次数据类型校验失败均增加 0 查询、0 更新。没有使用剩余 1578 行追加训练或选模。正式小试新增产物约 18 MiB，连同工程远低于 128 MiB，准确字节数和文件 SHA 以交付记录为准。

Y 三族 validation 满足主条件且两条流选中新增 yaw，已冻结其 selected 身份。为审阅而登记一次新独立测试提案，预留 71000000…71000017、每族六条风，三目标 2.75／3.35／3.85 MW 和两初始 pitch .025／.055 rad。共 23 个固定角色，含 Y／S selected 和 final 12、固定 C 3、P／PI 2、Y 两角色关闭 yaw 6。计划 414 回合、53406 行，建议单独上限 55000 行／128 MiB，训练步为零。尚未生成或释放这批新测试风，需主对话核查该提案。[一次测试提案](../experiments/20261105_yaw_pilot/future_test_proposal.json)

本轮仅验证集筛查支持冻结候选。新增 yaw 相对父的改善很小，整体弱于同预算 S，仍缺独立测试及三流可重复新增 yaw 收益。按已批准预算收尾。

实现与复现入口为 [yaw_pilot.py](yaw_pilot.py)。本轮首次 prepare 及失败 run 的记录保留，修复后的正式 run 见 `run_001.log`。现有目录独占写入，重复执行会拒绝覆盖。

```powershell
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.yaw_pilot run
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.yaw_pilot diagnostics
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.yaw_pilot_saved_report
```

重现需要原 C／forecast／PINN 引用、工程和正式 speed 来源文件、原锁及修订锁。独立重跑先建立新输出身份和预算。已有结果可通过 metrics.csv、selection.json、完整状态、保存轨迹和 [保存数据审计](../experiments/20261105_yaw_pilot/final_saved_audit.json) 复核，模型、物理限制与共享状态无需修改。
