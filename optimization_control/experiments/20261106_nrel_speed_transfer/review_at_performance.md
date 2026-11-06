# NREL 参考转速曲线迁移独立审查

2026-11-06。**实际实现审查通过，无实质阻断；允许按既定协议执行有限迁移性能对照。** 已审查提交 `faeb02940c4819796a2914d7991249d3826525aa` 的三个私有实现文件，并独立复核保存的160行工程数据、30个旧完整回合及冻结网络的纯推理路径。本次审查新增PINN／mock查询、环境推进和训练均为0。正式性能对照尚未执行，缺少其结果不构成工程阻断。

本结论只适用于下表文件及原锁定配置，工作树为 `.`，分支 `codex/speed-nstep-engineering-20261028`。协议提交为 `11ba03d18be653fe0f10b2d020ede55ce4561984`，任务起点为 `a98ef917f7826c553065163b26c81201655e495f`。本报告写入独立pitch工作树，未修改上述实现、共享状态、模型或来源锁。

| 已审查文件 | SHA256 |
|---|---|
| `optimization_control/maddpg_wind_farm/nrel_speed_adapter.py` | `f976ae6a20c01404a5b913824a00d67eab8d2eec5fb708b9d16ee391dae24b0b` |
| `optimization_control/maddpg_wind_farm/nrel_speed_transfer.py` | `5eb05d5bc08c893eda3758f059d8512f661849c02735c3619b6d0c4905363d70` |
| `optimization_control/maddpg_wind_farm/nrel_speed_transfer_report.py` | `743c38865b23680d00d5ca7010c53aa8b7075b08b1d6eaedfc7833ec31a8b148` |

旧Y selected的2048／0／2048、原C selected的0／0／4096、pitch／yaw网络及forecast来源继续冻结。Y第1流的selected仍为initial，C前两流仍没有新增speed学习；迁移不改变这些身份或其学习收益记录。三份Y身份已与原selection逐项核对，未依据旧独立测试重新选择。迁移后的物理轨迹可以改变，旧设置路径才要求兼容复现。

批准曲线为 `omega_ref=clip((7.55/63)*Ueff, 6.9*2*pi/60, 1.267)`，按各机当时有效风速计算。总转速命令必须在加入原MADDPG物理speed修正后，再统一裁剪到这个新范围，P／PI使用同一基础曲线和物理边界。执行器时间常数、速率限制、风生成器和PINN均沿用原冻结配置。原逐秒风、forecast历史与两个8秒决策的信息条件不增加未来量。

**实际兼容方案。** 当前适配保留环境 `action_low/high` 的旧speed坐标 `[.6,1.267]`，单独将执行器speed物理minimum设为`.7225663103256524`，并限制最终归一化speed命令的可用下端。这比原设计审查建议的“新环境坐标加旧网络视图”更直接，也满足本轮合同；无需增加观测仿射转换。原报告对直接改环境坐标的风险提示，不能当作当前实现已有错误。[实际环境与物理低限（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

实际组合路径先调用旧冻结映射，保留pitch、yaw和父输出，再以物理量重算 `clip(base_reference(Ueff)+.1*z_speed, LOW,HIGH)`，编码回旧动作坐标并替换最终speed列。当前坐标宽度仍为`.667rad/s`，旧分母在旧映射中保持正确；新的可执行物理范围宽度约`.5444336897rad/s`不作为归一化宽度。只有把环境坐标宽度也改小却沿用旧分母，才会缩小物理修正半径。[物理组合与替换（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

**来源与数值。** 已核对官方报告表1-1、7.2节和表7-2。名义直径126m对应本次R=63m，6.9rpm和12.1rpm为参考机组的低速与额定转速。7.55是在固定8m/s、零桨距条件下得到的峰值功率系数对应TSR，本次据此设定基础参考。变桨、限功率、限幅、执行器滞后及MADDPG修正后的实际TSR应由实际量计算。[NREL 5-MW参考报告，第2／19／27页](https://www.nlr.gov/docs/fy09osti/38060.pdf)

| 合同量 | 本轮纯算术复核 |
|---|---:|
| 基础斜率7.55/63 | .119841269841270 rad/m |
| 正常运行下限6.9×2π/60 | .722566310325652 rad/s |
| 采用的上限 | 1.267 rad/s，约12.098958774rpm |
| 精确12.1rpm | 1.267109036947883 rad/s |
| 新可执行物理范围宽度 | .544433689674347 rad/s |
| 实际保留的网络／命令归一化宽度 | .667 rad/s |
| 基础曲线下／上限对应Ueff | 6.029361265／10.572317881 m/s |

冻结PINN三个omega字段上界均为1.2670009599456786rad/s、下界约.599999rad/s。新下限在当前域内，精确12.1rpm会超出已登记上界，所以保留1.267。该配置适配不应改写PINN域或旧模型来源。初始物理speed=.9rad/s位于新旧范围内，可沿用既有reset初态。[原模型域来源](../20261105_yaw_pilot/lock.json)

**固定网络视图与实际物理边界分别登记。** 旧pitch、C speed和Y yaw网络使用原15维观测，其中0起索引4／7，即第5／8列，分别为实际speed和上一条实际执行speed总命令的旧坐标。环境自身继续用旧坐标，因此所有正常网络入口直接获得原语义。实际闭环的物理量、上一条已裁剪指令和执行器状态继续实时反馈；新轨迹没有播放旧动作。其他观测列、forecast输入、目标和历史时序保持原含义，speed／yaw头的36维预测仍来自已观测来流前缀。[固定pitch策略输入（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [speed头输入（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

同一个物理speed=.9rad/s，实际保留的归一化值为−.1004497751；若直接改环境低限则会变成−.3481898970。当前代码保持前者。对六份保存前缀的全部观测独立重算，列4严格等于实际物理speed按旧边界缩放后转float32，列7严格等于该时刻记录的实际执行总命令。metadata同时登记旧网络坐标、新物理边界及命令惩罚坐标，避免将两类边界混读。[归一化metadata（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

宏循环的 `next_obs[:,5:8]==executed_action` 仍使用同一旧坐标，未引入混合坐标。独立纯推理复核了三流online／target yaw输出、speed输出、旧模式全部组合输出及新模式同输入的pitch／yaw命令：适配前后对应值相同；新模式只替换speed。参数摘要与步数／回放／更新计数保持不变，`update()`明确拒绝执行。本轮无bootstrap、回放插入或新训练接口。[宏执行检查（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [冻结包装（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

**统一组合与公平性。** 每机使用决策时已观测的Ueff，先裁剪基础曲线，再加原物理修正`.1*z_speed`，最后统一裁剪至新物理范围，再编码为旧坐标动作。独立复核三机不同风速、z=−1／0／1、低／高端以及未饱和段，物理解码与该公式在3e−8rad/s内一致。Ueff=9时基础为1.078571429rad/s，修正±.1后分别为.978571429和1.178571429；Ueff=10.5时基础1.258333333，加+.1后总指令为1.267。修正半径未被缩小。

P、PI、Y使用各自闭环当时的各机Ueff和同一 `base_reference`／`speed_action`。P／PI本身speed修正为0，Y使用固定原C的speed修正。实际baseline路径的speed通道在新模式下设为可接收包装器命令，由包装器覆盖旧调度值，再通过同一 `project_action`；没有遗漏成仍由旧曲线执行。独立调用实际P、PI的 `act()`，在元数据环境与保存观测上确认了这一点，未调用reset／step或任何predictor。[共用P／PI包装（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [实际控制掩码（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

实际配置对象比较确认：仅speed执行器minimum改变，其他通道、时间常数、速率、更新周期、延迟、dt和来源均保持原值，reset初态speed=.9有效。新下端命令取朝范围内的float32可表示值：直接舍入解码为`.7225663014352322`，略低于精确下限；当前 `nextafter` 后为`.7225663213133813`，满足下限。三个物理标记LOW／.9／1.267的解码分别为`.7225663213133813`／`.8999999989904464`／`1.267`，最大误差约1.10e−8rad/s。[下端处理（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

RMSE须按完整回合报告，运动代价同时保留物理speed行程、速率和边界比例。当前归一化宽度没有改变，相同物理变化对应的 `action_change` 定义也没有改变；先前设计审查关于更换动作坐标后奖励不可直接比较的提示，不适用于本实现。已由六份保存前缀的float32执行命令逐值重算动作MSE，误差仍除原15MW、reward_scale=100、action_change_weight=.001均未变。本轮更新为0，奖励仅作记录。[原奖励计算（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

**实际工程证据与独立复核。** 已读取并重新核验 `engineering.json` 的六个带SHA前缀文件和两个mock保存文件。每份20行，含reset及19步；三条旧／新真实模型前缀仍使用horizon=128，mock的horizon=19。保存数据来自先前工程执行，本次只读复核。

| 条件 | 本次实现审查与复核结果 | 结论 |
|---|---|---|
| N1，版本与旧复现 | 三份Y旧模式前缀前52字段与各自已保存旧轨迹前20行逐值相等；五控制器×六条旧validation的风、目标、来源SHA和原指标重算通过 | 通过，旧30回合严格复用成立 |
| N2，全部网络入口的坐标 | 环境和执行命令均保留旧坐标；所有保存obs列4／7复核通过，三流冻结头及组合入口的纯推理一致 | 通过，无需新增坐标转换 |
| N3，物理修正半径和总限幅 | 三机不同Ueff及±.1／0物理修正、端点舍入通过；新前缀每步命令与实际物理公式逐值对应 | 通过，保留旧.667坐标宽度是正确行为 |
| N4，基线、物理域和执行器 | 实际P／PI包装纯调用与Y共用曲线；新前缀命令／实际speed有效，模型保存输入对应实际量，原三通道速率均通过 | 通过，未改时间常数或速率 |
| N5，纯迁移与信息条件 | 原selected来源一致，参数摘要及计数不变，update拒绝；参考Ueff逐行等于上一响应Ueff，保持原因果forecast与8秒保持条件 | 通过，未加入未来量或学习路径 |

| 冻结策略 | 旧前缀复现 | 旧实际speed范围 rad/s | 新实际speed范围 rad/s | 旧／新最大speed速率 rad/s² |
|---|---|---:|---:|---:|
| Y0 selected | 逐值一致 | .858537～1.022323 | .900000～1.100491 | .029079／.044127 |
| Y1 selected=initial | 逐值一致 | .858935～1.022713 | .900000～1.100939 | .029079／.044127 |
| Y2 selected | 逐值一致 | .845322～1.029496 | .897729～1.108527 | .030392／.045440 |

新前缀没有触及新物理低限，因此触底处的命令合同由上述端点纯函数和执行器配置检查支持，不夸大为长期触底动态验证。两个同初态mock保存回合的轨迹、观测、输入和metadata逐值相等。保存的模型输入speed与实际执行speed在1e−7rad/s内一致，物理执行状态边界使用1e−12容差。新轨迹改变属于配置迁移结果；这些短前缀不能用于判断完整回合优劣或是否重训。

**预算和执行准入。** 按[冻结协议](../../maddpg_wind_farm/NREL_SPEED_TRANSFER_PROTOCOL.md)执行：旧／新两版本×三份Y及公共P／PI五控制器×原六条validation，共60个完整回合身份。旧30回合已严格验证并引用，原费用3870行，本轮新增费用0。新30回合实际执行 `30×129=3870` 行；加既有工程120行PINN＋40行mock，本轮计划累计4030行，硬限10000行、存储128MiB。当前账本八个scope均完成，合计160行，无失败／重试；正式新30回合尚未产生。

**主对话可据本报告记录 `performance_allowed=true` 并绑定本报告SHA，继续既定对照。** 该准入仅覆盖上述版本、旧六条validation和原冻结身份，不增加训练、调参、压力回合或新风；本审查没有写入另一工作树的准入文件或启动运行。实现若变化须按实际变化核对适用性。旧30引用已成立，当前不需要重复执行旧模型回合。

后续所有控制器共享原129行实际float32风、初态、目标和执行器。按每族及总体等权报告完整回合RMSE、Y−PI与新−旧配对差、跨三父离散程度、物理speed／TSR和边界比例；保留全部场景及原400／500kW门槛。三份Y的重复initial／selected身份照实登记，不增加独立样本数。本次没有根据工程前缀追加候选或变更验收条件。

本轮是冻结旧策略在新基础曲线及边界下的迁移评估，使用旧validation，不重称新的独立泛化验收。旧配置的阶段通过继续归属旧配置，新版本均值是否变化由这60回合回答。7.55是设计基础参考，限幅、修正和执行器下的实际`lambda=63*omega_actual/Ueff`可以偏离7.55，限功率或变桨时也没有普遍最优保证。

现有合成标签中，参考最优speed取`clip(U_inlet/11.4*1.267,.6,1.267)`，使用入口风；控制参考采用各机Ueff。冻结模型的标签假设与新曲线不同，迁移表现只说明当前代理内响应，不能自动当作NREL物理优化收益。[合成标签源码（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

**复核方法与范围。** 使用原工作区 `.venv/Scripts/python.exe -B -X utf8`，从实现树导入实际适配模块，以内联Python完成上述纯函数、冻结网络推理和保存张量比较。复核时将环境reset／step与元数据plant的predictor替换为会立即抛错的禁止调用函数；构造环境仅为检查配置和纯命令函数，没有物理推进。脚本以exit=0结束，打印 `passed=true`、`old_complete_rollouts_rechecked=30`、`saved_engineering_rows_rechecked=160`、`old_prefix_exact=3`、`P_PI_shared_base_verified=true`，新增PINN／mock输入行和环境推进均为0。

下列命令可只读核对版本和已保存结果，不调用模型。应在实现树运行，`python`指上述原解释器；`context()`仅做来源SHA核对，不执行工程或性能阶段。工程数据及原来源均保留在其已登记位置，本报告未重新审计另一阶段的1720份归档。

```powershell
git rev-parse HEAD
Get-FileHash -Algorithm SHA256 -LiteralPath optimization_control/maddpg_wind_farm/nrel_speed_adapter.py,optimization_control/maddpg_wind_farm/nrel_speed_transfer.py,optimization_control/maddpg_wind_farm/nrel_speed_transfer_report.py
python -B -X utf8 -c "from optimization_control.maddpg_wind_farm import nrel_speed_transfer as r; from optimization_control.maddpg_wind_farm.yaw_pilot_report import read_eval; l=r.context(); c=r.cases(l); print([(k,len(read_eval(v,c,'Y' if k.startswith('Y') else 'baseline')[1])) for k,v in l['old_evaluations'].items()])"
Get-Content -LiteralPath optimization_control/experiments/20261106_nrel_speed_transfer/engineering.json
Get-Content -LiteralPath optimization_control/experiments/20261106_nrel_speed_transfer/pure.json
Get-Content -LiteralPath optimization_control/experiments/20261106_nrel_speed_transfer/model_budget.json
```

本次唯一写入为本报告，低于16MiB；未合并、push、删除文件、改共享状态或向其他对话发消息。**实现已通过审查，可继续原批准预算的冻结迁移对照；性能结论等待完整对照数据。**
