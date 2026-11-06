# NREL新规则三通道软件交接（2026-11-06）

**新规则在预定18条已用测试风的软件回归中3/3风况族通过，按协议完成本阶段交接。** 此入口使用用户指定的新参考曲线和正常运行低限，继续引用原冻结Y selected策略。新Y各族RMSE为432.051／459.627／454.080kW，同设置PI为488.042／532.200／523.088kW。完整结论见[NREL_SPEED_REGRESSION_RESULTS_20261106.md](../../maddpg_wind_farm/NREL_SPEED_REGRESSION_RESULTS_20261106.md)，机器判定见[primary_acceptance.json](primary_acceptance.json)。这份交接不扩公共部署接口，不复制大权重，也不把旧曲线验收改写为新曲线验收。

## 使用入口与参数

| 用途 | 现有入口 |
|---|---|
| 本轮固定库回归／断点按完成case跳过 | `optimization_control.maddpg_wind_farm.nrel_speed_regression`，prepare／run阶段均已执行，勿对现有目录重复采样 |
| 保存数据数值复核与图 | `optimization_control.maddpg_wind_farm.nrel_speed_regression_report`，已执行，产物采用独占创建 |
| 私有环境与动作适配 | [nrel_speed_adapter.py](../../maddpg_wind_farm/nrel_speed_adapter.py)：SpeedTransferEnv、FrozenTransfer、TransferPPI |
| 原完整闭环收集 | [nrel_speed_transfer.rollout](../../maddpg_wind_farm/nrel_speed_transfer.py)，由现有YawEpisode管理时钟／保持与每秒一次物理推进 |
| 本轮冻结来源 | [lock.json](lock.json)、[dependencies.json](dependencies.json)、[config.yaml](config.yaml) |

私有版本为`nrel_speed_transfer_old_coordinates_v1`。每机基础转速为`clip((7.55/63)*Ueff_i,6.9*2*pi/60,1.267)`rad/s。R=63m，斜率.11984126984126983rad/m，LOW=.7225663103256524rad/s，HIGH=1.267rad/s。Y加原C的±.1rad/s修正后再统一裁剪；P／PI使用同一基础函数和物理边界。基础参考每秒读取当时已观测的Ueff；不是入口U替代每机Ueff，也不求静态自洽固定点。

7.55来自参考机组零桨距条件的设计参考，不保证非零桨距、限功率、限幅或执行器滞后下最优。12.1rpm精确值略超当前登记PINN上界，继续采用获准的1.267rad/s。[来源和参数合同](../../maddpg_wind_farm/NREL_SPEED_TRANSFER_PROTOCOL.md)

环境观测、总命令和动作变化惩罚保留旧speed坐标[.6,1.267]；新物理低限独立施加于最终命令及执行器。不能直接把旧网络输入缩放边界改成LOW。metadata分别给出`network_speed_coordinates_rad_s`与`executed_speed_bounds_rad_s`，实际speed和上一执行speed总命令在观测0起列4／7，采用同一旧坐标。误差仍除15MW，reward_scale=100、action_change_weight=.001。

Y须经FrozenTransfer包装组合；直接调用原raw.compose仍使用旧基础曲线。P／PI须使用TransferPPI包装。当前speed接口仍是准静态运行点和原执行器模型，不新增起停或转矩控制模型。

每机动作顺序为[yaw失配参考、pitch参考、speed参考]，归一化矩阵[3,3]。yaw命令由原环境转为机舱heading参考，实际失配为wrap(heading−来流方向)。heading执行器原速率.005rad/s、时间常数5s；pitch速率.00872664626rad/s、时间常数2s；speed变化率.1rad/s²、时间常数5s。其余物理界限和模型域沿用来源锁。

本轮18例逐case沿用原target_w与pitch_rad：目标2.75／3.35／3.85MW，初始pitch .025／.055rad；初始speed .9rad/s、失配0。不要把原六条validation的2.85／3.45MW、初始pitch .04rad混入本轮回归。

pitch每秒反馈；speed／yaw head每8秒读取同一观测与已观测来流前缀，保持修正8秒，基础参考仍逐秒变化。需要完整时序时沿用YawEpisode；不能把单次compose调用替代宏时钟或改成每秒重算两个head。FrozenTransfer仅推理，update明确拒绝，原父online／target语义不变，本轮没有训练回放或bootstrap路径。

## 冻结策略与运行依赖

| 流 | 原pitch父选择步 | C speed选择步 | Y yaw新增选择步 | 身份限制 |
|---|---:|---:|---:|---|
| Y0 | 16384 | 0 | 2048 | C0仍为初始speed头 |
| Y1 | 12288 | 0 | 0 | selected=initial，yaw／speed没有新增学习记录 |
| Y2 | 8192 | 4096 | 2048 | 原选择保留，未重选 |

具体权重绝对路径、SHA和归一化参数沿用[原三通道依赖表](../../maddpg_wind_farm/THREE_CHANNEL_STAGE_HANDOFF_20261106.md)中的父／speed／yaw文件；该旧文档只用于依赖和原合同，转速参数以本新规则说明为准。机器可读依赖在本轮dependencies.json，完整来源保护在lock.json。只加载一份yaw inference.pt不足以构成完整策略。

共用forecast为`20261029_history_forecast/forecast_model.npz`，SHA=`a5571a19354015c8b5997823748fafd7f0a6a355a0422d35b539e4faa3992877`，从已观测前缀构造36维预测特征；本机观测为15维float32。PINN为原trained.keras，SHA=`7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`，桥接脚本SHA=`4db850074b62a7f86720534f6286b48c2a024efd9218f1b243c376fd54d5a270`。模型语义仍是合成标签软件代理，不是物理精度证书。

运行使用[./.venv/Scripts/python.exe（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)，在导入NumPy之前调用现有activate_runtime指向原`.venv/pinn_tf216`。保持项目根在Python导入路径，不安装新全局依赖。

## 可执行的纯读取／冻结推理示例

两个脚本位于新实验目录examples/，均已在本轮交付时验证。纯读取只用标准库读CSV／JSON；冻结推理只在保存观测和已观测前缀上调用现有PyTorch策略，不创建环境、不加载PINN或推进物理模型。推理示例固定case0、Y0、t=32的决策边界，生成step33总命令并与保存命令逐值比较，不使用未来信息生成动作。

```powershell
& './.venv/Scripts/python.exe' -B -X utf8 './optimization_control/experiments/20261106_nrel_speed_regression/examples/read_only.py'
& './.venv/Scripts/python.exe' -B -X utf8 './optimization_control/experiments/20261106_nrel_speed_regression/examples/frozen_inference.py'
```

纯推理例子保留原8秒决策边界；非决策秒应保持上次两个修正，pitch和基础参考继续反馈。保存数据上的单次动作复现不等于完成独立部署封装；后续真实模型与现场接入仍须各自定义接口和验证。

## 验收范围与交付边界

新规则本轮只在原18条已用测试风、原目标／初态和冻结身份下回归。主判断是三个风况族新Y均值分别低于新PI；旧绝对400／500kW、弱新增通道收益及selected=initial身份单列，不能据此继续本阶段训练。新结果不是新未见泛化证明，未做新低风压力验证。

全部旧／新各90回合、逐casebias／方差、speed／TSR边界及pitch实际速率边界占用均在本轮报告。转速限速未激活不能推出pitch或所有执行器未受约束。原曲线的原验收继续归属旧曲线，诊断夹具只提供模型响应限制信息，不作为无期限前置。

本轮到回归报告和这份交接结束，不自动训练、调P／PI、回滚新曲线、修改PINN、追加网格／角色／新风或发送队友消息。供PINN组的数据字段说明另见[PINN_SPEED_RESPONSE_INTERFACE_20261106.md](../../maddpg_wind_farm/PINN_SPEED_RESPONSE_INTERFACE_20261106.md)。
