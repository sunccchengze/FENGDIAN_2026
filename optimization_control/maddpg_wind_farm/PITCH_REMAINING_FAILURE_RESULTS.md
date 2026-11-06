# 固定n8候选的剩余失败结构与下一学习方案（2026-10-29）

**剩余失败主要是特定目标/风速条件下的持续欠发，伴随流2更新遗忘；并非普遍波动过大，也不能全部推给低风不可达。** 本轮RL步、优化器update、模型推进、环境step、新test释放均0。只用保存的训练/常规validation数据，提出一个“Actor更新采用当前队友桨距条件”的待审阅变体，未实现学习、未声称有效。

## 固定对象、来源与相关性

固定20261028_pitch_nstep n8 gamma=.99三份validation-selected，步数16384/12288/4096，身份与[原候选清单](../experiments/20261028_pitch_nstep_mechanism/candidate_manifest.json)一致；selection SHA d8081f0525987b8d6057a6902ad22c88460b1f5a103be36ce0531472d686f8e7，来源提交740d040。没有按已发布test拼选各流/实验；没有改用eef2a13 gamma实验里的.99检查点。

只比较已保存known数据中的18训练+18常规validation：9条训练波形×2初态，6条validation波形×3初态，共36输入case、15条波形、三训练流108个selected槽位。同case风速/初态/目标逐步核对一致，统一执行器来自原冻结配置，只读一份共同P/PI基线。初态、控制器、同波形窗口/梯度点高度相关，不把108槽位当108次独立训练，不作显著性或置信区间结论；三父原预算不同仍保留。

历史压力family=low_wind_stress的split也写validation；本次按family显式排除它们的方案选择，88条控制器×压力身份仅在excluded_pressure_identity.csv留证，无压力性能参与拟合/候选选择。test/test_bank未读取。旧独立test和压力结论只在历史报告/阶段索引保留。

本n8选模用的另18场validation有全部15个快照；没有对应PI轨迹，本轮只用它判断更新退化，不拿不同来流的PI补表。384个已有训练行为回合含探索，只作训练分布描述。841项原模型/源码/权重/轨迹逐文件SHA处理前后不变。

## 真正弱于PI的位置

完整128步同case RMSE差严格>0为失败，另列>100W标记；这11处全部超过100W，非浮点平局。不是按绝对RMSE最大挑选。

| 分组 | selected槽位 | 弱于PI数 | selected减PI的RMSE均值 kW |
|---|---:|---:|---:|
| 全36场×3流 | 108 | 11 | -68.70 |
| 训练18场×3流 | 54 | 9 | -79.18 |
| 常规validation18场×3流 | 54 | 2 | -58.21 |
| 平稳 | 36 | 6 | -49.91 |
| 慢变 | 36 | 5 | -67.52 |
| 阵风 | 36 | 0 | -88.65 |
| 2.60MW | 18 | 0 | -169.29 |
| 2.85MW | 27 | 0 | -85.25 |
| 3.20MW | 18 | 0 | -86.30 |
| 3.45MW | 27 | 2 | -31.16 |
| 3.80MW | 18 | 9 | +18.05 |

按初态.025/.04/.055分别有4/45、1/18、6/45个失败；按流0/1/2为2/36、4/36、5/36。各分母按实际设计，不假定初态等量。配对/分组完整CSV保留所有97个优于PI反例。

11个失败位置完整列举，单位kW；“—”表示该流优于PI，不是删场（完整值见paired_cases.csv）。

| 波形/目标 | 初始pitch rad | 流0减PI | 流1减PI | 流2减PI |
|---|---:|---:|---:|---:|
| 训练episode8，平稳3.8MW | .025 | +47.79 | +135.92 | +83.91 |
| 同上 | .055 | +48.93 | +138.83 | +85.04 |
| 训练episode0，慢变3.8MW | .025 | — | +7.62 | — |
| 同上 | .055 | — | +21.01 | +1.41 |
| 验证ramp1，3.45MW | .040 | — | — | +2.49 |
| 同上 | .055 | — | — | +14.27 |

同case至少2流重复失败的是3个case，但只有2条波形（episode8两初态及episode0的.055）。真正跨3流重复的是episode8，不能把两初态称为两次独立风况复制。3.8MW阵风6槽位全部优于PI，反驳“所有高目标必失败”。

## 持续偏差、风速域与启动反例

按固定目标使用ΔMSE=Δbias²+Δvariance复算：11个失败中10个bias²比PI大且variance反而小。反复失败的episode8风速均值8.597、范围7.742–9.718m/s；初态.025时PI RMSE428.33kW、平均误差-15.40kW，三流selected RMSE476.12/564.25/512.24kW、平均误差-235.29/-367.94/-284.43kW。初态.055时PI417.70kW、bias-59.90kW，三流466.63/556.53/502.74kW、bias-253.03/-381.47/-309.00kW。

以.025为例，三流相对PI的bias²增加.05512/.13515/.08066 MW²，而variance减少.01190/.00023/.00174 MW²，造成总MSE更差。三流1–32秒差较小，65–96秒RMSE为499.7/614.8/554.3kW，对应PI375.1kW；不是只靠启动段解释。所有四个预固定32秒窗仍保留，不裁去启动或困难段。

同一case的49个响应点在7.5–8.5m/s，三流平均误差-609.3/-769.5/-683.2kW，PI-402.2kW；它们贡献了相对PI的正MSE差。另77点在8.5–9.5m/s，PI过发+203.8kW，n8分别-25.5/-142.8/-59.9kW，n8在该区间的平方误差反而更好；9.5以上仅2点，不据小样本外推。风速点来自同一相关波形，不是49个独立样本。

因此低风时既有所有控制器的能力缺口，也有相对PI的额外策略欠发。PI在同执行器下实现更低完整误差证明有更好可执行轨迹，不证明3.8MW每秒可达，更不是全局上界或真实风机结论。本轮没有新可达性搜索；已发表压力结论不能作为新候选选择依据。

必须保留的反例是流1、episode0慢变3.8MW、初态.025：完整selected比PI差7.62kW，但bias²差为-.00085MW²、variance差为+.00519MW²。1–32秒RMSE410.1对321.8kW，末32秒202.9对248.1kW，主要启动段较差、后段较好；不能把11处全部称长期偏差。目标在回合内固定，本轮没有target-step数据，不能声称已识别目标阶跃响应。

## 学习后退化与已有能力

以下为36开发case的均值，kW；是开发回归，不是新独立测试。

| 流 | initial / selected / final | 弱于PI数 initial / selected / final | selected / final弱于自身initial的case数 |
|---|---:|---:|---:|
| 0 | 388.25 / 350.77 / 350.77 | 10 / 2 / 2 | 8 / 8 |
| 1 | 369.62 / 360.70 / 349.66 | 6 / 4 / 3 | 10 / 6 |
| 2 | 336.12 / 357.15 / 365.32 | 2 / 5 / 6 | 29 / 32 |

流0/1的episode8从父到selected已有改善，但仍落后PI；流2selected在同case相对父反而差约43.6–48.3kW。3.45MW慢变的流2父约199.5–200.3kW，selected约260.5–263.4kW，final虽回落到约242kW仍弱于父。不能把所有失败归成初始化就不会控制。

另一套18场选模validation上，final相对selected的均值变化为0/+2.41/+10.02kW，相对initial为-6.57/-4.91/+7.87kW；流2final的18场中10处弱于selected、11处弱于initial。它仍因另一开发集合均值最低合法选中了4096步，不能据已见test/known重新选父。流1在36开发case的final反而好于selected，说明遗忘并非三流普遍单调。

384条训练行为覆盖全部九格，每格每流均有多次访问，但不能据“访问过”证明覆盖足够。流2探索行为的归一化桨距参考边界占用从前32回合约10.9%到末32回合23.2%；不同回合来流不同，不能将该变化当同天气因果收益或部署性能。

## 观测、回放与实际参数梯度

Actor是两层64 ReLU的无循环MLP；15维含本机功率/有效风速、实际yaw/pitch/speed、上次三维参考、目标、当前全场有符号误差、当前入口风速/方向/TI与remaining。当前误差和执行器状态不是缺失项。三份selected在1024固定回放点上，桨距输出对当前误差坐标的绝对输入导数均值约6.29–18.46（归一化坐标单位），显示确有当前误差通路；不证明部分观测充分或所有历史都无用。本轮没有找到应增加哪一个历史状态的直接证据，因此不预设积分或重复4秒趋势。

固定回放按sequence等距抽1024点，32个按回放逐坐标std标准化的联合obs近邻，排除本点；只计算Actor/Critic离线forward和梯度，没有Plant代理查询/闭环推进，未调用sample/update，没有消耗训练RNG。“模型推进0”指Plant输入行数，不把离线价值网络运算误称环境仿真。current与behavior桨距差含旧策略漂移和探索，不能全部叫噪声。

| selected流 | 平均绝对桨距差 rad | 动作局部梯度变号 / 3072 | 实际参数梯度cosine<0批次 / 48 | 当前桨距超近邻逐坐标范围比例 |
|---|---:|---:|---:|---:|
| 0 | .04197 | 599 | 3 | 约34.1% |
| 1 | .03380 | 524 | 6 | 约23.5% |
| 2 | .04839 | 556 | 11 | 约30.0% |

每个Actor用固定16×64批次分别算完整参数梯度，队友分支detach；两个1024点聚合cosine为负的实例是流1 Actor2=-.469、流2 Actor0=-.215。这些不是历史采样批次，也未先执行原update中的Critic step；它们衡量保存网络上损失条件的敏感性，不冒充历史更新方向的逐次复现。原审计全当前投影与严格“仅换队友pitch、保留回放yaw/speed”的对照另存background_projection_check.csv：背景参考最大差2.98e-7，桨距动作梯度最大差0、变号数0；正式参数梯度采用仅换pitch条件，未让背景通道数值差混入候选。参数和Adam不更新，网络/回放RNG及841源SHA保持。

这说明Actor梯度对队友行为条件敏感，是下一单因素的具体动机；不是另做Q动作网格或证明新方向正确。原MADDPG Eq.(5)就允许回放队友动作，因此不是实现bug。[原论文](https://proceedings.neurips.cc/paper_files/paper/2017/file/68a9750337a418a86fe06c1991a1d64c-Paper.pdf)。流2final的局部变号比例下降、近邻范围外比例从约30%降至10.5%，同天气控制仍退化；Critic覆盖/队友条件不是唯一解释。近邻min/max不是可靠密度支持，离线Q梯度不是实际回报导数。

结合已完成奖励审计，动作惩罚和时间权重确有排序冲突，但单改gamma=1已完整失败；不能再次由“偏差存在”跳到换奖励或积分。旧动作修正也有低目标退化、LR/anchor/nstep各有已发表限制，均保留历史结论。

## 一个待审阅方案与交付

具体公式、只替换队友pitch的实现接口、完整继承、公平控制臂、固定98304步及278528评估推进上限、可失败验收见[PITCH_REMAINING_FAILURE_CANDIDATE.md](PITCH_REMAINING_FAILURE_CANDIDATE.md)。这是新Actor损失条件变体；不改观测/结构、Critic n8、gamma=.99、reward、采样、LR或权限。本轮没有实现该更新，也没有启动新训练。证据足以提出有界实验，仍不足以证明改善；最小未决证据是实际配对续训的收益/退化结果。

原“各风况、多流稳定优于PI”及三通道目标不降低。即使下一轮局部收益门槛通过，也必须与“平均优于PI”“各场稳定优于PI”分开判；压力全保留，不能删掉或把目标宣布为不可能。speed侧保持独立，阶段索引只更新到1a7221a，不复制其历史风预测器。

实验目录：[20261029_pitch_remaining_failures（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。config/metrics/summary齐全，candidate_proposal.yaml明确区分本轮零预算与待实施预算；paired_cases、groups、recurrence、time_windows、wind_bins、selection_history、training_behavior、replay_gradient、parameter_gradient等CSV保留全部正反例。独立math.fsum从原轨迹复算324个策略角色配对，核心指标最大差0；36输入case完整128步及实际pitch硬约束通过，原选择逐流重算一致。

Python图已逐张查看：

- [全部36开发case×三流的相对PI差值图](../experiments/20261029_pitch_remaining_failures/failure_map.png)。
- [重复失败的三流完整128秒误差、入口风速及目标/实际pitch](../experiments/20261029_pitch_remaining_failures/full_failure_timeseries.png)：代表case按至少2流失败中平均PI差最大选，仅展示，不选策略；三机平均pitch不冒充逐机行程。
- [偏差/方差、同天气更新轨迹与梯度条件](../experiments/20261029_pitch_remaining_failures/decomposition_and_updates.png)。

首版完整时序曾把风速偏移画在功率误差轴，已保留figure_v1源/图并改为独立m/s轴；没有新增环境或模型计算。context_v1保留初版全当前动作参数梯度；正式候选只替换pitch，背景差等价核对留证。两次均为零模型推进的后处理/条件澄清，不隐藏原输出。

复现使用已有环境、新输出目录，所有命令均0模型推进/0update：

```powershell
Set-Location -LiteralPath .
$py='./.venv/Scripts/python.exe'
$out='optimization_control/experiments/20261029_pitch_remaining_failures_reproduction'
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_audit prepare --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_audit trajectories --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_audit replay --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_context --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_report --output $out
# 已完成目录只核验保存数据：同report命令加--verify-only。
```

本轮在独立pitch分支原子提交；原模型/实验只读，不合并master或推送，不改共享PROJECT_STATUS/TASKFLOW/README/PPT或speed源码，不清理旧产物。
