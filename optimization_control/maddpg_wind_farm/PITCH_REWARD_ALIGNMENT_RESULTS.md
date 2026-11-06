# 桨距奖励与完整回合跟踪目标一致性审计（2026-10-29）

**奖励排序与完整128秒RMSE确有冲突，折扣与参考指令惩罚共同参与；没有证据把动作惩罚认定为唯一根因。** 本轮正式RL新增0步，补齐评估6912步，预算预留也是6912，未超过10000。只提交一个待审阅候选：保留原奖励和动作惩罚，仅对照gamma=.99/1；没有开始新学习，没有更换父策略。

本轮不是Q网格，也没有用已经发布的pitch独立测试选奖励。以下都是冻结train/validation的已实现完整轨迹；离线重计分不能证明重新训练会获益。speed完成事实只更新[阶段索引](MADDPG_STAGE_HANDOFF_20261029.md)，不参与本pitch候选选择。

## 公式、离散时序和实际目标

核对源码`maddpg_farm_env.reset/step/_observe`、原训练入口及原始分项，实际每机共享奖励为：

\[
r_t=100\left[-\left(\frac{P_{t+1}-P^*}{15\times10^6}\right)^2
 -0.001\,\frac1{9}\sum_{i=1}^{3}\sum_{k=1}^{3}(a^{exec}_{t,i,k}-a^{exec}_{t-1,i,k})^2\right].
\]

`a_exec`是经过后台参考投影及幅值裁剪的**归一化参考指令**，不是执行器实际位置/速度。yaw指令保持0偏置、机舱跟踪风向；speed仍由当前有效风速统一曲线调度，其参考变化也被九维均值计入。不能把非学习通道的惩罚直接置0。本轮所有完整分项记录的背景通道占累计参考变化代价约5.97%，这是相关轨迹的描述量。

时序是观测t → 指令/执行器一步 → 读来流t+1及代理功率 → 奖励t。首步previous_action来自reset初态，不是全零；完整指标使用响应t=1..128，未去启动段。训练npz另外检查next_obs与下一步obs连续、上一参考在obs[:,5:8]中一致、唯一true terminal在第128步、next_obs误差与原W误差相符。

误差项实际是平方，不是绝对值；分母始终为三机额定和15MW，不随2.6–4.55MW目标变化。固定目标、相同长度下，RMSE开方及该正的常数缩放不改变平方误差排名；本轮19548个RMSE非平局的同case比较均保持均匀tracking与RMSE方向一致。MAE同时保存，未把假想的MAE目标当成实际训练目标。

gamma=.99使第128个奖励的权重为第1个的0.2790；前32步占总权重38.00%，末32步仅14.48%。本轮分别保存：完整MSE/RMSE/偏差/标准差、均匀tracking、折扣tracking、均匀/折扣动作项、均匀/折扣总回报。完整轨迹的RMSE²=偏差²+方差复算通过，native reward及分项最大重构残差2.23e-7，小于事前5e-6。

从回合起点计算的单条折扣实现回报，是本次一致性审计视角。MADDPG实际从回放状态分布优化Critic/Actor，存在函数逼近、分布和多步off-policy误差；这个视角不能被称为完整的实际学习目标证明，也不是真实长期Q。

## 数据覆盖、来源和复现

实验根：[20261029_pitch_reward_alignment（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。模型仍为`wind12-synthetic-7506554ac981`，SHA为`7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`。原三父来源、mask[0,1,0]、执行器、P/PI和归一化不改，详见[阶段索引](MADDPG_STAGE_HANDOFF_20261029.md)。

| 来源 | 原语义完整轨迹 | 来源内去重后 | 输入case×流槽位 | 说明 |
|---|---:|---:|---:|---|
| pitch_action完整固定修正闭环 | 2244 | 2208 | 132 | 54训练、54常规验证、24验证压力；17种合法固定修正 |
| nstep训练行为 | 768 | 756 | 384 | n1/n8各128回合×3流；12组完全相同，仍保留覆盖分母 |
| nstep全验证快照tracking | 540 | 486 | 54 | 两臂×3流×5快照×18场；完整误差/桨距，全初态保留 |
| nstep冻结角色完整reward | 108 | 72 | 18 | 初态.04，三风况×两目标×三流；initial/selected/final别名复用 |

去重键含source、run、case身份和完整128步误差/代价/命令/实际桨距字节摘要；角色别名保存在trajectory_roles.csv。两份validation视图有重叠，不把3522条来源内记录之和当独立样本，也不把同一轨迹的selected/initial别名当训练重复。训练行为含探索，不能称部署性能。

旧validation只有桨距及误差，没有完整九维参考变化。按[事前协议](PITCH_REWARD_ALIGNMENT_PROTOCOL.md)，只补12个不同Actor映射×6场的前96步，实际6912步；末32步复用mechanism原有零扰动延续。72条完整结果与旧validation误差逐步差0，最大归一化桨距指令差1.35e-7（门槛1e-5）。其他初态.025/.055及中间快照保留tracking-only，不伪造动作分项。8/32步分支回报没有与128步回报混比。

1831份来源文件/代码/模型被逐文件SHA锁定并在处理前后核对。config记录base_config和源身份；collection.json、supplement.json和评估预算账留证。本轮后处理曾修正压力分组和去重覆盖分母，首版全部保留在postprocess_v1；图标题换行前版本保留postprocess_v2。两次均没有新增环境步、改变阈值、评分公式或原始轨迹，修正记录分别为postprocessing_correction.json、figure_layout_correction.json。

## 同case排序冲突的覆盖和损失

以下方向先按完整RMSE确定“较好/较差”，只把RMSE差>100W、回报差>1e-6计为非平局；全部平局与数值也保存。依次比较均匀tracking→折扣tracking→折扣总回报，动作引入和动作修复分开记。配对高度相关，不作独立样本显著性推断。

| 数据 | RMSE非平局对 | 折扣反向 | 动作新引入 | 动作修复折扣反向 | 最终反向对 | 最终反向覆盖case | 反向RMSE损失均值/最大 kW |
|---|---:|---:|---:|---:|---:|---:|---:|
| 固定修正·训练 | 7174 | 263 | 69 | 112 | 220 | 35/54 | .813 / 3.837 |
| 固定修正·常规验证 | 7198 | 545 | 254 | 74 | 725 | 48/54 | 1.691 / 18.491 |
| 固定修正·压力 | 2753 | 14 | 0 | 0 | 14 | 12/24 | 1.100 / 1.764 |
| nstep训练行为 | 371 | 33 | 32 | 13 | 52 | 52/384 | 8.995 / 35.307 |
| nstep完整reward验证角色 | 114 | 10 | 14 | 2 | 22 | 10/18 | 7.486 / 26.035 |
| nstep全验证tracking | 1938 | 136 | 缺分项 | 缺分项 | 未估算 | 折扣反向51/54 | 不填总回报损失 |

例如常规验证的725对=471对折扣反向仍保留+254对动作新引入；不能全部归到动作项。训练固定修正中动作项净修复更多（112修复对比69引入），是必须保留的反例。

慢变单列：固定修正训练60/2372对最终反向、覆盖12/18；常规验证363/2389对、覆盖18/18，反向损失均值1.973kW、最大18.491kW。nstep训练慢变18/125对、覆盖18/127输入槽位；完整reward验证慢变2/38对，动作没有新引入反向、反而修复2对。全验证tracking慢变48/647对折扣反向。目标/初态/流的完整分组见metrics.csv；不删困难场，也不以是否发生冲突重新加权总体。

误差平方/归一化在同case的实际额外反向数是0。跨case聚合则不同：按相同case集合、去掉完整相同角色映射后，3103个非平局聚合比较中109个case-RMSE均值与pooled-RMSE反向；这是相关的描述性比较，不能和上表逐轨迹对相加。例：流0训练慢变，parent均值429.727kW优于common+.010的431.257，pooled却443.447差于440.858。gamma=1只去掉时间权重，不会自动让平均MSE等同于case平均RMSE。

## 冲突是否只是合理运动代价

部分反向确实换来较少桨距运动，不能只按RMSE称奖励错误；也存在准确性与实际运动同时更好的轨迹被排后。固定修正959个最终反向对中266对的RMSE较好轨迹实际总行程也较少；nstep训练52对中16对、完整reward验证22对中9对如此。动作新引入的14个验证反向对中，有6对的RMSE较好轨迹实际行程和RMS速率均更低，但参考变化软代价更高。

这说明参考跳变惩罚不是实际桨距运动代价的严格单调替代；不说明所有软惩罚都应移除。全部完整reward轨迹实际桨距范围约[4.30e-30,.22]rad，最大实际步速率.008726646260000012rad/s，与.00872664626的差是浮点尾数。动作惩罚与硬幅值/速率限制不是同一机制；统一执行器仍限制实际量。本轮没有改变任何限制。

## 反事实重计分：改善与反例一起保留

下表是在**同case既有有限轨迹菜单中**，某评分首选相对菜单内最小完整RMSE的平均损失（W），不是新控制器结果、可部署case选择器或全局最优损失。

| 菜单 | 原折扣总回报 | 离线去动作项、保留gamma=.99 | 离线gamma=1、保留动作项 |
|---|---:|---:|---:|
| 固定修正训练54槽位 | 53.29 | 96.84 | 74.00 |
| 固定修正常规验证54槽位 | 862.53 | 409.99 | 112.97 |
| 固定修正慢变验证18槽位 | 1337.95 | 196.27 | 274.68 |
| 固定修正压力24槽位 | 0 | 0 | 0 |
| nstep训练384槽位 | 1218.01 | 346.43 | 539.30 |
| nstep完整reward验证18槽位 | 1074.21 | 173.68 | 141.17 |
| nstep慢变完整reward验证6槽位 | 0 | 176.66 | 0 |

gamma=1的菜单重计分相对原评分：固定修正常规验证14槽位改善、1槽位变差，平均RMSE减少749.56W、实际行程均值减少7.06e-5rad；慢变8/18改善、0变差，平均减少1063.28W、行程减少.003454rad。它在固定修正训练中2改善/2变差，平均反而恶化20.71W，慢变0改善/2变差；这不是一致获益。

nstep训练中gamma=1重计分24槽位改善、9变差，平均减少678.71W，最坏恶化12.396kW，实际行程平均增加.006695rad，6槽位RMS速率比原首选增加>10%。完整reward验证角色2改善/0变差、其余不变，平均减少933.04W、行程减少.002059rad；慢变6槽位的菜单首选均不变。所有重计分变化和实际代价在detail.json保留。

因此候选证据是中等强度的目标一致性动机。已见慢变菜单平均变化约1kW，远小于几百kW跟踪误差及5%改善目标；不能靠这个诊断宣称解决了弱场景。有限小修正网格也不能给新训练收益设全局上界。没有选择“去动作项”作为第二个候选，没有改平方误差/归一化/采样/LR。

压力组虽然有少数非最优轨迹间的排序差，四个评分的菜单首选都相同；奖励重排没有在该菜单中改善低风高目标。既存[PITCH_ACTION_DIAGNOSTIC_RESULTS.md](PITCH_ACTION_DIAGNOSTIC_RESULTS.md)的模型内路径候选功率缺口继续单列；不能把有限菜单或旧数值扫描当真实风机不可达或全局最优证明。

## 唯一候选、图和复现命令

完整待审阅方案见[PITCH_REWARD_ALIGNMENT_CANDIDATE.md](PITCH_REWARD_ALIGNMENT_CANDIDATE.md)：同原三父、两臂都n8，仅gamma=.99/1，原始reward及回放逐步奖励不重标；Critic/target/Adam同源继承，配置与replay.gamma同步，保留128步终止。建议一次固定2×3×16384=98304环境学习步，保留原慢变/其他风况验收并加强final及实际动作代价检查。**本轮没有运行这个预算；方案确认和工程契约验证在正式训练之前。**

三张Python图仅用于解释保存结果，已查看渲染：

- [归因、菜单偏好损失和折扣权重](../experiments/20261029_pitch_reward_alignment/attribution.png)
- [RMSE损失与实际桨距运动代价](../experiments/20261029_pitch_reward_alignment/tracking_motion_cost.png)
- [两个最大常规验证冲突的完整128秒误差、分项、指令/实际桨距](../experiments/20261029_pitch_reward_alignment/full_episode_examples.png)：按事前固定的source/split和每归因最大RMSE差规则选示例，全部轨迹仍保留，未据此选父/超参。

在.使用已有本地Python；新的输出目录才可重新prepare。原实验可复算review/detail，无需再补齐，supplement遇到完成锁只核对复用。

```powershell
$py = './.venv/Scripts/python.exe'
$out = 'optimization_control/experiments/20261029_pitch_reward_alignment'
$env:TF_NUM_INTRAOP_THREADS = '1'
$env:TF_NUM_INTEROP_THREADS = '1'
& $py -m unittest optimization_control.tests.test_pitch_reward_alignment -v
# 已完成目录只重读保存数据；不重放环境、不更新策略：
& $py -m optimization_control.maddpg_wind_farm.pitch_reward_alignment_review --output $out
& $py "$out/detail.py"
# 完整复现用一个新的目录（另计6912评估步），不覆盖本轮冻结数据：
$newOut = 'optimization_control/experiments/20261029_pitch_reward_alignment_reproduction'
& $py -m optimization_control.maddpg_wind_farm.pitch_reward_alignment prepare --output $newOut
& $py -m optimization_control.maddpg_wind_farm.pitch_reward_alignment supplement --output $newOut
& $py -m optimization_control.maddpg_wind_farm.pitch_reward_alignment collect --output $newOut
& $py -m optimization_control.maddpg_wind_farm.pitch_reward_alignment_review --output $newOut
& $py "$out/detail.py" --output $newOut
```

新增4项局部测试通过，覆盖128步拒绝短窗口、公式/分解/折扣、归因符号/修复反例、菜单最大回报方向、重复唯一case覆盖分母；见unittest.txt。未调用新优化器更新，未改共享训练/环境代码，未改PINN/原父/原PROJECT_STATUS/TASKFLOW，未合并master或push。结论限冻结合成准静态代理及其统一执行器。
