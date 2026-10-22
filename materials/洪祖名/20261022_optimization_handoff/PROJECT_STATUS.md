# 项目状态恢复摘要

> 2026-10-22 中期答辩图表完成：只读冻结随机入口实验，Python/Matplotlib绘制7张中文图，PNG/PDF/SVG共21文件；每图附意义、建议讲解与结论边界。
> 240条RMSE从30720行测试轨迹复算完全一致，输入摘要及25个受保护模型/源文件/检查点不变；逐张视觉检查通过，没有新增训练或调整结论。
> 入口 optimization_control/maddpg_wind_farm/MIDTERM_FIGURES.md，产物 optimization_control/experiments/20261022_midterm_figures/。

> 2026-10-22 随机入口驱动的训练完成：复用现有生成器逐回合生成stationary/ramp/gust，后台yaw跟踪与转速曲线、RL仅学pitch，共用执行器。
> 已补齐状态相关转速参考到当前/目标Actor，旧配置缺省行为保留。三条主种子42派生流各16384步，共49152；验证均值471.79/444.14/433.65 kW，均未通过400/500 kW精度门槛，按协议停止通道扩展。
> 新独立测试240条指标/30720行轨迹：常规选中449.72±40.11 kW，初始1083.62、P552.37、PI477.54；第0流、慢变与低风压力场仍弱于PI，不宣称稳定优势。
> 129项测试、49152条物理回放审计、新进程10240行和上一轮3072行回放完全一致；网络及队友源文件不变。
> 报告 optimization_control/maddpg_wind_farm/RANDOM_WIND_TRAINING.md；主实验20261022_random_wind_training、回放20261022_random_wind_replay。当前仅合成入口＋合成标签网络，没有物理精度或全局可达性证书。

> 2026-10-22 新版十二输入 PINN 软件联调完成：交付位于 pinn/2026_1021，旧版已搬至 pinn/2026_1007。
> 十二输入 SI 桥接、风向周期/机位/归一化与模型摘要检查；4096/512/512 合成样本、120 轮仅新增参数拟合，冻结主干不变。
> 混合入口短训练 2048 步/897 次更新，统一三通道执行器/P/PI、新进程 3072 行回放完全一致；旧策略搬家后 24 个指标完全一致。
> 三个仅桨距单目标各 16384 步（合计49152）；低/中目标验证选中末段误差18.14/1.69 kW，高目标选中仍为初始策略、最终/选中验证误差比2.306。
> 按冻结门槛停止晋级，未启动多目标/转速/偏航学习；三通道功能已接通。独立测试48条指标/4608行轨迹、49152条回放审计、121项模块测试通过。
> 软件流程完成，完整学习门槛未通过；无物理精度结论。报告 optimization_control/maddpg_wind_farm/WIND_PINN_INTEGRATION.md；实验 20261022_wind_pinn_integration / 20261022_wind_pinn_curriculum / 20261022_wind_pinn_replay / 20261022_legacy_pinn_replay。

> 2026-10-08 优化交付完成：本轮 ZIP（128.72 MiB）及任务说明.docx、AI readme.md 已就绪。
> 全部历史工作上传至 GitHub 分支 codex/optimization-handoff-20261007，首次完整上传 84d6f4b；
> 远程目录树与本地审查版本一致，团队 main 未变。1588 原文件恢复校验、110 测试、54 行移动路径回放通过。
> 原实验、队友源文件和失败结论保留，没有重训。交付记录位于 deliverables/20261007_optimization_handoff/，完整导航 optimization_control/WORK_INDEX.md。

> 2026-10-07 固定九输入逐级能力验证完成：单目标 pitch 的三个选中策略均学会跟踪，多目标 pitch、pitch+speed、all 各三个派生流的验证门槛通过数为 2/3、2/3、1/3，整体可靠性仍未通过。
> 原链条在多目标门槛失败处停止；后两权限按用户要求另以新冻结协议独立验证，未放宽原标准。
> 新测试 selected RMSE：pitch 169.75±9.17 kW，pitch+speed 172.89±5.33 kW，all 189.81±15.37 kW。
> 后两者同预算/目标/配对流，加入 yaw 三次均变差；pitch 的测试目标与预算不同，不能据均值归因通道收益。
> 12 次训练、245760 步/回放审计、26 项不同测试、576 行测试指标与59904行轨迹，队友文件及模型未变。
> 单目标 4.5 MW 最终仍明显退化；不把 best 当作稳定终点或把模型内收益当作物理优势。
> 报告 `optimization_control/maddpg_wind_farm/FIXED_CURRICULUM.md`，三组实验 `20261007_fixed_pinn_curriculum`、`20261007_fixed_pinn_pitch_speed_probe`、`20261007_fixed_pinn_all_probe`；本轮完成，没有启动下一轮调参。

> 2026-10-07 固定九输入结果异常诊断完成：24 个指标、3072 行轨迹复算正确，单位 kW。
> 初始保持 4.433 MW；训练后三目标均约 3.5 MW，目标已输入但响应弱。当前网络三目标均可达，
> 15 次首步反事实回放显示 Critic 值及部分动作排序失配，未证明唯一根因。
> P/PI 高目标的 3.53/2.89 kW 是无噪声网络内跟踪误差；同运行点合成标签源检查 289.59/287.94 kW，
> 不是实际真值或标签源闭环误差。未改算法/模型/对照、未新训练，队友源文件及原产物摘要未变。
> 报告 `optimization_control/maddpg_wind_farm/FIXED_PINN_DIAGNOSTIC.md`，产物 `20261007_fixed_pinn_diagnostic_checked/`。

> 2026-10-07 固定工况联调已完成：跟随队友九输入网络，2560 条合成样本、80 轮仅新增参数训练，
> MADDPG 2048 步/897 次更新及统一 fixed/P/PI。原交付仍为未训练改造结构，已训练副本单独保存。
> 本轮优先全流程联调，不等待仿真数据，不开展物理收益或多种子收敛验收；详情与复现见
> `optimization_control/maddpg_wind_farm/FIXED_PINN_DEMO.md`，实时状态见 `optimization_control/TASKFLOW.md`。
> 23 项相关测试、149 个模型探针、保存恢复/完整回放与实际轨迹约束检查通过；队友源文件及冻结主体未变。
> 3.5 MW 短策略改善、4.5 MW 退化，不能宣称稳定收敛。完整产物在 `optimization_control/experiments/20261007_fixed_pinn_demo_checked/`。

> 2026-09-23 自主后续诊断完成：六个已有终点、98304 条不同训练转移的离线审计发现，分层组不可达且终止的样本仅占 0.110%–0.146%，却占全回放 TD 平方误差 82.65%–86.63%；终止掩码正确，观测已包含剩余时间。
> 动作无关不可达平方误差基线保持同场景策略回报排序，一致价值坐标平移使 TD 残差不变（最大差 1.14e-13）。4 项新增测试通过，总计102项不同测试有记录。没有训练新模型、没有改默认奖励、没有读取旧独立测试做本诊断。
> 报告 `optimization_control/maddpg_wind_farm/VALUE_BASELINE_DIAGNOSTIC.md`；实验 `20260923_maddpg_value_baseline_diagnostic` 与 `20260923_maddpg_value_baseline_terminal`。下一项可做“相同分层采样下原奖励 vs 动作无关基线平移”的新配对训练；尚未执行，不可声称性能改善。

> 2026-09-23 功率可达性任务完成：24 点诊断（17 个稳态可行运行点、7 个目标超模型上界），98 项不同测试通过。
> 8 m/s 的 3/3.6 MW 可达但旧 MADDPG 后段欠功率；5.5 m/s 上限约 1.262 MW，5 MW 压力下仍有约 0.49 MW 平均剩余欠功率。
> 仅改变风速/目标采样，两组×三个配对种子×16384 步全部完成（98304 步），新验证/测试各 27 场、432 行测试。分层采样未通过：常规 RMSE 394.26→590.19 kW，三个种子均变差；低风压力剩余欠功率 472.52→468.72 kW，只有一个种子改善。保留原训练默认，不声称改进成功。
> 原采样/分层采样固定 3 MW 的 200 kW 门槛均 0/3 通过；分层采样后期退化门槛通过，但完整验收失败。PI 常规401.03、固定182.86、低风剩余6.99 kW。下一假设是不可达任务对价值学习及目标条件响应的影响，需要另立协议和新测试。
> 报告 `optimization_control/maddpg_wind_farm/REACHABILITY_TRACKING.md`；实验 `20260922_maddpg_reachability_checked`、`20260922_maddpg_tracking_study`。本轮已冻结并测试，不可据本测试再调参；所有模型、归一化、选模哈希和分解指标保留。

> 2026-09-22 混合风况退化定位增量：旧验证集 12 个检查点与通道干预发现价值估计失配增加及多通道联合策略漂移，回放终止/动作契约检查通过；没有证明单一根因。
> 完成四配置×三个配对种子×16384 步（196608 步），72 条冻结验证/测试轨迹，P/PI 验证选参，576 行独立测试。选中仅降低 Actor 学习率至 1e-4；三个配对种子均改善，测试均值 430.21±36.73 kW，相对原选中策略 472.40±9.34 kW 降低 8.93%，相对原终点 574.49±42.02 kW 降低 25.11%。
> 后期退化门槛 3/3 通过，固定风 3 MW 的 200 kW 门槛仅 1/3 通过，完整验收仍未通过；验证选参 PI 为 378.37 kW，整体优于当前 MADDPG。真实 PINN 依赖未解除，没有测试后调参。
> 报告：`optimization_control/maddpg_wind_farm/MIXED_STABILITY.md`；实验 `20260922_maddpg_mixed_stability`、`20260922_maddpg_retrospective`、`20260922_maddpg_channel_rollback`。91 项不同测试通过；三个 target_slow 运行在会话中断后从 12288 步恢复至原定预算，其他九个运行保留。下一步仍需解决固定工况精度及低风高目标行为，不能宣布稳定收敛或算法优于 PI。

> 2026-09-22 稳定训练/固定评估增量：已完成预声明配置筛查、分通道扩展、三个独立种子确认、24 条冻结验证/测试轨迹和严格验证集选模；累计训练 106496 步。
> 独立测试常规场景平均 RMSE：验证选中策略 412.15±30.49 kW，最终策略 554.60±74.31 kW，P 497.58 kW，PI 441.09 kW（± 为三个训练重复的样本标准差）。不宣称统计或真实物理优势。
> 三次选中策略均改善初始验证表现，固定测试均通过 200 kW 门槛；但两次最终/最佳验证误差超过 1.25，完整稳定性门槛未通过，稳定收敛仍待解决。不得把 best 当作最终收敛策略。
> 85 项测试通过，精确恢复/磁盘评估/场景校验通过。报告与复现：`optimization_control/maddpg_wind_farm/STABLE_TRAINING.md`；实验：`20260922_maddpg_stable_training`。保持真实 PINN 依赖，下一轮不得沿用已查看的测试集调参。

> 2026-09-22 随机入口/学习诊断增量：入口 Kaimal 风速 + 慢变方向 + 背景 TI 已接入默认 12 维 PINN 接口；三类场景、分流种子、CSV/JSON 校验回放完成。
> 偏航执行器改为机舱朝向，gamma 由新风向换算；P/PI 默认使用偏航跟踪、转速运行曲线和桨距反馈，统一动作映射/执行器。增加三种控制权限的同权限对照。
> 3×8192 步固定可达目标诊断、2×8192 步奖励尺度对照完成：仅桨距时也有学习不稳；尺度有影响，最终 MADDPG 仍未稳定优于 PI。未归咎于 Mock 或宣称问题已全部解决。
> 随机短训练 4800 步/2101 次联合更新；192 条风况统计、39 组内存/磁盘回放、执行器速率通过；512 步与 256+256 步恢复完全一致。
> 报告：`optimization_control/maddpg_wind_farm/DIAGNOSTIC_REPORT.md`；使用说明同目录 README。真实 PINN/物理标定仍待交付，不报告真实控制收益。

> 2026-09-22 增量：已实现固定三机 MADDPG（每机偏航/桨距/转速参考）、可配置 PINN 输入适配与固定六维输出 `[P1,P2,P3,Ueff1,Ueff2,Ueff3]`。
> 新任务使用外部给定、回合内固定的全场功率目标。目录入口：`optimization_control/maddpg_wind_farm/README.md`。
> 63 项优化/风况/多智能体测试 + 7 项旧 PPO 测试通过。2048 步联调训练完成 897 次联合更新；256 步连续训练与 128+128 步恢复的网络/回放/随机状态及下一更新完全一致，两次磁盘评估 CSV 逐字节一致。
> 两个 Mock 场景中短训练 MADDPG 的 RMSE 均高于 P/PI；仅证明软件闭环，不支持物理效果或算法优势。真实 PINN 权重、字段有效域、功率口径与执行器参数仍待交付确认，正式训练仍未完成。
> 实验：`20260922_maddpg_smoke`、`20260922_maddpg_eval_final`、`20260922_maddpg_verification`。此前“先 PPO 后 MADDPG”及平滑参考默认仅描述历史路线；当前用户优先要求跑通三机 MADDPG。

> 2026-09-13 增量：已完成 Kaimal 随机风况与独立单机 v2 环境、PPO 配置入口、CSV/JSON 回放和统计图。优化框架/风况 49 项、旧 PPO 7 项测试通过；8192 步短训练完成，六份 600 步磁盘回放与首次输出逐列精确一致。该短训练策略未优于 P 基准，正式随机风训练和同权限强基准仍待办。
>
> 使用入口：`optimization_control/ppo_single_turbine/随机风况使用指南.md`；实验：`20260913_kaimal_ppo_smoke`、`20260913_kaimal_wind_validation`、`20260913_kaimal_replay_check`。以下历史审阅中的“已有风况”描述以本增量为补充；真实 PINN/多机数据阻塞未解除。

> 依据：2026-08-23 完整分类审阅；2026-08-24 优化软件壳与 T1-R 实施收尾
>
> 用途：此前对话不可用时，从本文件恢复项目现状、结论、风险与下一动作

## 1. 一句话状态

FLORIS/Keras 基线、XGBoost 优化、解析公式单机 PPO 工具链、T1-R 修复以及 T2.5/T4a 准静态软件闭环已完成；默认仍是 Mock Plant，正式多机控制直接阻塞于含控制参数数据和合格准静态 PINN。

## 2. 项目总路线与当前阶段

申报书路线为：OpenFOAM+LES → POD+PINN → 代理模型 → PPO 单机控制 → MADDPG 多机协同 → 数字孪生/风洞闭环。

按申报书日程，2026-08-24 位于第二阶段（2026-07 至 2026-09）：大规模 CFD/LES 数据生成、流场快照和 POD 降阶。优化控制模块已经并行完成了解析环境、PPO 工具链和可替换准静态软件壳，但 Mock 联调不能替代后续代理 PINN、正式策略训练和高保真验证。

申报书把第三阶段写为“2025-10 至 2025-12”，与 2026-04 项目启动时间冲突，推定是年份笔误；原始申报材料保持只读，正式报告引用前需由项目组确认。

## 3. 已完成成果

### 3.1 队友数据与 Keras 基线

- 袁夫达提供 FLORIS v4.6.6 的 GCH/CC 两套数据，各 1224 行。
- 工况网格：风速 4–12 m/s（0.5 步长）× 风向 0–345°（15° 步长）× TI 0.06/0.08/0.10。
- 布局：3 台 NREL 5MW，沿 X 轴排列，间距 378 m。
- GCH 有 22 行、CC 有 4 行任一目标功率为 0。
- 厉今飞 Keras 模型：6 工程特征 → 64/128/64 Swish → 3 个 Sigmoid 单机功率 → 固定求和层。
- 基线全场功率：GCH MAE 86.53 kW、R² 0.999062；CC MAE 103.06 kW、R² 0.998709。

### 3.2 XGBoost 代理模型优化

- 统一比较 XGBoost、GPR、改进 MLP、two-stage，固定 `seed=42`。
- 最终选用每台风机一个 XGBoost 回归器；每个模型 529 棵树、6 特征输入。
- 5-fold CV：GCH 全场 MAE 7.79 kW、RMSE 22.43 kW；CC 全场 MAE 10.49 kW、RMSE 29.97 kW。
- 模型保存于 `optimization_control/surrogate/models/final/`，加载前后预测差 0 W。
- CC 预测存在约 −0.66 kW/+108 kW 的边界越界记录，推理必须将单机功率裁剪到 `[0, 5e6] W`。
- 当前代理模型只接收风速、湍流强度和风向周期编码，不含偏航/桨距/转速，定位是稳态功率预测器，不是可控动力学环境。

### 3.3 单机 PPO 预研

- 环境：NREL 5MW Cp 经验公式 + 转速一阶惯性，观测 `[P, ω, β, U, P_target]`，动作 `[Δβ, Δω]`。
- 历史模型：cleanrl 风格 PPO，64×64 Tanh Actor-Critic，请求 200000 步、实际完成 196608 步、4 环境、`seed=42`；当时使用未压缩高斯动作。
- 历史评估曾记录 PPO RMSE 28.49 kW、MAE 19.95 kW 和 P 基准 RMSE 959.68 kW；复核确认其跨越 episode、P 基准方向错误、策略 log-prob 与裁剪后动作不一致，因此这些数值只供追溯。
- 三版权重均为 9285 参数；推荐演示 `models/ppo/ppo_tracking_v3_seed42.pt`。
- T1-R 已修复回合回报、`PController` 方向、初始目标、终点/重置、动作平滑归一化，并将新 PPO 改为有界 tanh 高斯策略；512 步 smoke 与 7 项回归测试通过。
- 旧 v3 模型按显式 `legacy_unsquashed` 修正协议回归为 PPO RMSE 49.83 kW、PController RMSE 35.99 kW；仅一个确定性场景，不能形成正式性能结论。

### 3.4 优化侧准静态软件闭环

- T2.5 已实现 `ActionMapper`、`ActuatorModel`、因果参考生成、状态/观测和奖励组件；T4a 已将这些组件接成可替换 Plant 的 Gymnasium 环境。
- 统一入口是 `from optimization_control.environments import load_quasi_static_env`，默认注入 `MockQuasiStaticPlant` 和合成风况源。
- Mock、合成风况及 YAML 中所有 `source: assumed` 数值只用于软件联调，不支持真实物理效果、算法优劣或发电量结论。
- `info` 暴露功率、反事实可利用功率语义、保持动作、奖励分项、约束/OOD/参考 flags，便于训练日志和故障定位。
- 契约现会拒绝状态字段覆盖、非 bool 域标志、负 OOD、OOD 可利用功率参考和奖励 shape 隐式广播；优化框架 36 项测试通过。
- 完整架构、伪时间语义、快速开始和真实 PINN 替换清单见 `optimization_control/OPTIMIZATION_SHELL_GUIDE.md`。

## 4. 当前阻塞与下一动作

### 直接阻塞

现有 FLORIS CSV 只有风况与稳态功率，没有每台风机的 `yaw_i`、`pitch_i`、`rotor_speed_i` 等控制变量。优化侧已经能用 Mock 构建 v0 软件环境，但没有“风况 + 控制运行点 → 稳态输出”的受控映射，就不能把 Mock 替换为真实 Plant、开展 T4b 或形成正式控制结论；没有连续状态转移轨迹，则不能构建 `dynamic_transition` 环境。

### 已冻结的接口原则

`PINN_OPTIMIZATION_INTERFACE.md` 已更新到 v0.3：第一版采用 `quasi_static`；“调转速”采用高层转速参考并由优化组独立 `ActuatorModel` 处理；参考功率采用因果、限爬坡且预留 headroom 的可利用功率平滑目标；第一版固定布局和 `turbine_ids`，顶层 plant 返回完整结构化风机状态。v0.3 只增加现有代码映射和使用入口，不改变这些已冻结物理语义。

仍待三方确认：yaw/pitch/rotor-speed 字段能否由仿真真实扫描，执行器边界与时间参数，当前 FLORIS 功率的具体测量边界，以及 OOD/验收数值门槛。

### 推荐顺序

1. 按接口 v0.3 发出数据需求：固定布局与 `turbine_ids`、风况、逐机 yaw/pitch/rotor-speed operating point、逐机/全场功率、生成脚本与配置、单位、控制范围和功率语义。
2. 队友先确认三个控制字段分别能否真实扫描并影响输出；用小规模单变量和联合控制样本验证物理趋势，不能把始终固定的字段标成可控。
3. 数据到位后修复代理模型 pipeline 的路径参数，扩展特征并重训准静态可控代理，完成控制敏感性和有效域检查。
4. 实现符合 `PlantModel` 的真实 PINN Adapter，建立非 Mock 的版本化 YAML，并把已有 `source: assumed` 数值替换为可追溯参数；不重复搭建环境壳。
5. 先完成 Plant 契约、控制敏感性、OOD、吞吐量和高保真对照验收，再跑确定性基线、PPO 与后续 MADDPG。
6. 形成可复现的实验配置、多随机种子比较和结题图表；动态结论继续等待状态转移数据。

## 5. 已知技术债

1. `surrogate/eval_baseline.py`、`train_and_eval.py`、`optuna_tune.py`、`stage3_analysis.py` 含本机绝对路径，不可移植。
2. 代理模型历史实验仍缺少规范要求的 `config.yaml`；PPO 历史实验已补齐。
3. 历史 PPO `metrics.csv` 的 `episodic_return` 全为 0，只能追溯；当前 logger 已修复，但需新训练生成有效曲线。
4. `demo_*.png` 的中文标签渲染成方框，正式汇报前需配置中文字体并重新导出。
5. 历史模型使用未压缩高斯策略；当前训练已改为 tanh 有界策略，二者必须用 `--policy-format` 区分且不能混作同一实验。
6. `stage3_analysis.py` 从 sin/cos 反推风向的 `atan2` 参数顺序可疑，残差图的风向横坐标需复核后再用于论文。
7. `requirements.txt` 是完整环境冻结，包含 TensorFlow/ONNX 等非所有入口必需的重依赖；后续应拆分最小运行依赖与开发依赖。
8. 首批队友原始 CSV 没有同名 JSON 元数据，属于历史交付例外；信息分散在 README、`说明.docx` 和模型 metadata。

## 6. 文件与产物索引

| 内容 | 位置 |
|------|------|
| 实时任务看板 | `optimization_control/TASKFLOW.md` |
| 项目长期规范 | `AGENTS.md`、`CLAUDE.md` |
| 本地 Git 工作流 | `GIT_WORKFLOW.md`、`tools/project_git_status.ps1` |
| PINN—优化接口规范 | `optimization_control/PINN_OPTIMIZATION_INTERFACE.md` |
| 代理模型工作记录 | `optimization_control/surrogate/WORKLOG.md` |
| 代理模型实验 | `optimization_control/experiments/20260807_surrogate_baseline/` |
| 最终 XGB 模型 | `optimization_control/surrogate/models/final/` |
| PPO 环境与代码 | `optimization_control/environments/`、`optimization_control/ppo_single_turbine/` |
| PPO 实验 | `optimization_control/experiments/20260808_ppo_single_turbine/` |
| 队友 FLORIS 数据 | `data/teammates/yuan_fuda_floris/` |
| 队友 Keras 模型 | `data/teammates/li_jinfei_nn/` |
| 文献综述 | `文献综述_第一次组会.md` |
| 交付包 | `代理模型优化交付_20260808.zip`、`单机PPO功率跟踪交付_20260809.zip` |

## 7. 本次文件审阅范围

- 项目自有文件 119 个、约 61.32 MB；其中 51 个由 Git 跟踪。
- 逐个读取 16 个 Python 源文件、14 个 Markdown、依赖与 Git 规则。
- 检查 15 个 CSV 的字段/行数/小型指标表，10 个元数据 JSON 和 6 个 XGBoost 模型 JSON。
- 检查 3 个 PPO state_dict、2 个 Keras 包、2 个交付 ZIP 的内部结构。
- 提取 3 个 DOCX 的 OOXML 文本；LibreOffice 缺失，未能完成页面渲染。
- 提取并核对 11 篇 PDF 的题名、摘要/开篇和页数。
- 清点 28 张 PNG，并视觉检查尾流图、残差图、PPO 训练/评估与演示图的代表样本。

`.venv` 是第三方运行环境，只记录 Python/依赖版本，不把其内部库源码视为项目文件逐项总结；`.git` 与 `__pycache__` 同理。
