# 桨距一步与最多8步TD目标对照（2026-10-28）

**本轮完成：最多8步TD的selected通过事前门槛，改善了原薄弱慢变组和新慢变测试均值；流2回归、终点优势减弱、低风压力仍弱于P/PI。**
正式新增98304步，未追加候选或预算。这里支持“本轮有针对性改善”，不支持“各流、各场景稳定优于PI”或“已修复真实Q”。
三父原已在常规均值上优于PI；本轮新增收益由配对原方法/父策略差值衡量，不能把原有优势全部归因于n8。

## 新独立测试与验收

全部选择冻结后才生成36场常规测试（3目标×3风况×2初态×2轨迹）和8场压力，所有控制器共享风况、目标、初态与执行器。
表中为**完整128秒回合RMSE的场景均值，单位kW**；±为三个训练流各自场景均值的样本标准差，不是置信区间。
初态/风轨迹/训练流之间存在相关，108个常规配对槽位不当作108个独立统计样本。

| 风况 | 父/initial | n1 selected | n8 selected | P | PI |
|---|---:|---:|---:|---:|---:|
| 平稳 | 465.85±17.80 | 464.59±19.84 | 464.23±5.86 | 583.73 | 532.52 |
| 慢变 | 424.56±26.36 | 420.54±32.65 | 397.86±4.23 | 624.78 | 501.16 |
| 阵风 | 409.80±21.37 | 409.43±21.97 | 397.66±0.92 | 590.09 | 494.16 |
| 常规36场 | 433.40±20.37 | 431.52±23.58 | 419.92±2.70 | 599.53 | 509.28 |
| 低风压力8场 | 1554.54±147.03 | 1546.39±160.66 | 1497.00±89.40 | 1321.91 | 1321.91 |
| 全44场（含压力） | 637.25±42.28 | 634.22±47.49 | 615.75±17.37 | 730.87 | 657.03 |

慢变n8 selected相对n1为-22.67kW（5.39%），相对父为-26.69kW（6.29%）；两项均2/3流改善。
相对n1的三流配对差值标准差为36.52kW，收益并非三个流一致。常规总体相对n1为-11.60±24.68kW，相对父为-13.48±21.55kW。
平稳/阵风逐流相对n1的最大回归4.33%，低于固定5%上限；验证和测试所有final/selected均≤1.25，n8三流selected均非initial。
上述条件使acceptance.json的passed=true；5.39%仅略高于预设5%，不称有充足统计把握或普遍稳定优势。

汇合全部逐步误差后再开方的**pooled RMSE**是另一口径，完整保留在aggregate/cross_stream.csv：

| 范围 | 父 | n1 selected | n8 selected | P | PI |
|---|---:|---:|---:|---:|---:|
| 慢变 | 437.61 | 433.69 | 416.62 | 638.10 | 510.38 |
| 常规36场 | 444.94 | 443.55 | 434.26 | 618.56 | 523.14 |
| 全44场 | 779.29 | 776.03 | 752.15 | 796.77 | 738.72 |

pooled慢变相对n1改善3.93%，没有达到5%；验收采用事前固定的场景RMSE均值，未改用更有利的口径。
全44场pooled下n8 selected还差于PI约13.43kW，说明“平均优于PI”必须说明指标口径和压力范围。

## 三流、终点与反例

| 流 | 父慢变 | n1 selected慢变 | n8 selected慢变 | n8 final慢变 | n8常规final/selected |
|---|---:|---:|---:|---:|---:|
| 0 | 450.47 | 450.47 | 393.09 | 393.09 | 1.0000 |
| 1 | 425.42 | 425.42 | 399.37 | 400.28 | .9905 |
| 2 | 397.78 | 385.72 | 401.14 | 421.72 | 1.0278 |

n8 final常规422.47±8.47kW，高于selected419.92±2.70；慢变final405.03±14.90kW，高于selected397.86±4.23。
final相对n1 final的慢变收益只剩1.57%，不能把selected的5.39%写成终点收益。
流2常规由父410.31变为selected420.54、final432.21kW，终点比父回归5.34%；没有实现所有流能力都提高。
它在验证中selected虽改善，也不能保证新测试改善，故不使用测试重新选择流2的4096步状态。

常规n8 selected相对PI有93/108槽位改善，15个更差；相对P为86/108改善，相对父65/108，相对n1为60/108。
常规最差PI差值+121.75kW：流1、平稳3.95MW、轨迹0、初始.055rad。
相对n1最差+82.83kW、相对父最差+54.22kW均在流2同一目标/风况/初态组合，全部保留在paired.csv和全场图。

压力n8 selected相对父平均改善57.54kW，但只16/24槽位改善；对P/PI则24/24全部更差，平均+175.10kW。
n8 final压力1448.62±75.97kW，仍差于1321.91kW的P/PI。
本轮不新增可达性最优搜索；前轮7.55/7.7m/s数值候选路径不冒充本轮7.6/7.8m/s、TI=.08的上界。
这些是当前冻结模型内实际执行结果；剩余误差不能全归为不可达，也不能外推真实风机或全局最优。

## 原薄弱组的回归证据（已知样本）

流0、旧验证慢变3.45MW，完整RMSE如下，单位kW。它们用于已知能力回归，未参与本轮选模，也不是新独立样本。

| 初始pitch rad | 父 | n8 selected | 冻结PI |
|---|---:|---:|---:|
| .025 | 289.74 | 222.02 | 267.49 |
| .040 | 290.27 | 218.05 | 257.98 |
| .055 | 290.82 | 218.17 | 249.12 |

初始.04的平均误差-197.66→-36.72kW，std212.57→214.94kW，bias²占MSE的46.37%→2.84%。
改善主要来自持续欠发减少，波动没有同步下降；这与先前偏差诊断相符，但没有证明bootstrap是唯一根因。
此前共同固定负修正在低目标全部退化，不能把本轮学到的策略简化为通用pitch负偏置。
44个旧训练/验证/压力case全部保留于evaluation=known的880条指标和112640行轨迹，包含所有跨目标反例。

## 验证选模历史

| 流 | 父/initial kW | n1 selected步 | n1 selected kW | n1 final kW | n8 selected步 | n8 selected kW | n8 final kW |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 418.55 | 0 | 418.55 | 437.73 | 16384 | 411.97 | 411.97 |
| 1 | 418.86 | 0 | 418.86 | 432.87 | 12288 | 411.55 | 413.96 |
| 2 | 405.50 | 12288 | 402.11 | 414.61 | 4096 | 403.35 | 413.37 |

数字为18场完整128秒回合RMSE均值。n8三流均非initial；流1、2的final较selected回落，不能只报最佳。

正式768个回合分片齐全，每作业7937次更新。训练目标/探索/采样锚点在配对两臂精确一致，reward复算最大差4.77e-7。
86个保护文件未变；未提交分片数0，正式重算步数0。所有父状态、initial、selected和final完整保留。
三条n8流的实际m均值为7.7809/7.7786/7.7801，满8步比例94.485%/94.469%/94.513%；完整直方图见各作业result.json和training_audit.csv。
选择文件SHA256=d8081f0525987b8d6057a6902ad22c88460b1f5a103be36ce0531472d686f8e7，测试在该选择写入后才生成。

## 协议、来源与唯一变化

运行前冻结协议：[PITCH_NSTEP_PROTOCOL.md](PITCH_NSTEP_PROTOCOL.md)。诊断依据：[PITCH_ACTION_DIAGNOSTIC_RESULTS.md](PITCH_ACTION_DIAGNOSTIC_RESULTS.md)。
Critic在部分局部回放范围内对可执行改善动作排序反向，但不是唯一根因；只检验时间展开目标。
唯一候选n=8对照原n=1，使用旧行为轨迹的多步奖励，有off-policy偏差，不声称无偏或真实Q已修复。
原algorithm.py未改；两臂共用其完整update，只替换目标所需奖励、末状态、终止及折扣。
Actor目标、观测/网络、reward、lr、采样锚点、更新频率、tau、执行器与权限不变。

三父状态均由20261023_progressive_random_control验证选中，完整继承online/target、Adam、回放和RNG：

| 流 | 父文件（pitch_run_N/segment_000/） | SHA256 |
|---|---|---|
| 0 | step_00016384.pth | 28e221e6f6e74096ef74e9a9375c638823a055c38232ef4d3b5e16a5026996ea |
| 1 | step_00012288.pth | 0fcb0b9d474db0d04b3ac2d86c91d2f39d66bb3c025e30d911ce79b2ba445821 |
| 2 | step_00008192.pth | e2897be535e5c9bae27acbecc5edd57460a8a038ba28719e366ab4c904309a05 |

父目录位于原项目optimization_control/experiments/20261023_progressive_random_control/，只读。
模型wind12-synthetic-7506554ac981，SHA256=7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451；只限准静态合成代理模型。
P/PI kp1.5、ki.08、bias.04rad、antiwindup.2、integral_limit.3，不重新整定；mask=[0,1,0]。
yaw继续跟踪风向；speed=clip(.11114035087719298×当前effective wind,.6,1.267)，仍经过统一执行器。

## 实现与验证

回放物理槽另存单调插入序号，在容量回卷和后续新写入时识别真实相邻关系；旧状态按size/position还原时间顺序。
遇真实done停止并不bootstrap；未来尾部缺失时用实际m及gamma^m bootstrap，不把缺数据当done，不删采样锚点。
相邻next_obs与obs精确相等，剩余时间递减；多agent done必须一致。目标动作在真实s_(t+m)使用原policy映射，奖励不重复scale。
独立格式pitch_nstep_v1保存n、tail_rule、时序、RNG及m直方图，恢复严格核对；旧检查点不写回。

6项针对性单元测试通过，包含n1三次更新全参数/Adam/target精确等价、8步实际回报/终止/尾部、ring覆盖/新增未来、错误跨回合拒绝、末状态动作/scale/gamma以及恢复下一更新精确一致。
三份真实父状态的原update与n1也精确等价；两臂从真实512步检查点各延续两条128步恢复分叉，动作、回放、网络、Adam全部精确一致。
两臂各1024步smoke完成，天气/目标/初态/探索与采样锚点配对一致；两臂selected均initial，不能视作学习成功。
smoke实际新增2048步，恢复分叉另512步，均不继承到正式训练；正式三流重新载入原父状态。
一次smoke汇总命令在作业result写完前被调用，因文件尚不存在退出；作业完成后正常复算通过，未修改学习实现或重跑训练。

## 固定预算与复现

实验根目录./optimization_control/experiments/20261028_pitch_nstep/。
smoke位于同级20261028_pitch_nstep_smoke/。正式2臂×3流×16384=98304新增步；每臂每流7937次更新。
每128步保存完整训练状态及该回合压缩转移；每4096步验证18个完整128步回合，以RMSE均值严格改善选模，initial也参与。
main seed42，训练设计/初态/探索由SeedSequence([42,20261028,purpose,run,...])派生，回放RNG完整继承；实际父RNG写入config。
train episode31000000+run×1000+ep，validation32000000起，test33000000起，stress33009000起。
已扫描当前独立树及原项目维护配置，未发现这些episode起点冲突；不读取另一任务的测试。
正式两进程各串行执行一种n的三流；PyTorch/TF intra/inter线程均1，Torch deterministic；runtime_execution.json保存实际命令和UTC起点。

```powershell
Set-Location -LiteralPath .
$env:TF_NUM_INTRAOP_THREADS='1'
$env:TF_NUM_INTEROP_THREADS='1'
$py='./.venv/Scripts/python.exe'
& $py -B -X utf8 -m unittest optimization_control.tests.test_pitch_nstep -v
# 复现实验使用新目录，不能覆盖本轮结果。
$smoke='optimization_control/experiments/20261028_pitch_nstep_smoke_repro'
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_trial prepare --smoke --output $smoke
foreach ($n in 1,8) {
  & $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_trial worker --output $smoke --n $n --run 0 --stop-after 512
}
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_review recovery --output $smoke
foreach ($n in 1,8) {
  & $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_trial worker --output $smoke --n $n --run 0
}
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_review training --output $smoke
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_trial prepare --output optimization_control/experiments/20261028_pitch_nstep_repro
foreach ($n in 1,8) {
  foreach ($run in 0..2) {
    & $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_trial worker --output optimization_control/experiments/20261028_pitch_nstep_repro --n $n --run $run
  }
}
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_review training --output optimization_control/experiments/20261028_pitch_nstep_repro
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_trial select --output optimization_control/experiments/20261028_pitch_nstep_repro
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_trial test --output optimization_control/experiments/20261028_pitch_nstep_repro
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_trial known --output optimization_control/experiments/20261028_pitch_nstep_repro
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_review review --output optimization_control/experiments/20261028_pitch_nstep_repro
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_nstep_review figures --output optimization_control/experiments/20261028_pitch_nstep_repro
```

worker同目录只恢复SHA匹配的完整分片，已完成作业只核验后返回；selection冻结后拒绝任何继续训练。
测试仅在六作业完成并冻结选择后生成；每控制器完整评估分片可恢复，不再生成第二套测试或追加候选。
原工作区分支/状态文件、PINN、父文件和旧实验均未改，不合并master、不推送。

## 完整审计与产物索引

全部540条正式验证指标/69120行验证时序复算相等，30次验证均值和六次选择重新计算一致。
新test与known各20控制器状态×44场，共1760条指标/225280行完整时序，error分解指标复算最大差0。
三父initial的全部旧场RMSE与前轮差0W；两臂initial、天气、目标和初态配对精确一致，全部标签/场景齐全。
这些评估不计RL新增步：正式RL98304，smoke2048，恢复审计512；正式验证69120评估步、冻结后225280评估步，smoke验证9216评估步。
没有把继承或两臂重复的回放大小算作新训练样本。

- `config.yaml / metrics.csv / summary.txt`：冻结配置、1760条完整回合指标、结论和预算。
- `selection.json / training_manifest.csv / runtime_execution.json`：冻结选择、384条配对天气/目标/初态及实际运行参数。
- `training_audit.csv / training_verification.json / validation_groups.csv`：六作业、768回合、m分布、同锚点与reward/执行器审计。
- `evaluation_verification.json / evaluation_audit.csv`：2300条指标、294400行验证+冻结评估时序复算和来源检查。
- `paired.csv / paired_groups.csv / cross_stream.csv / aggregate.csv / checkpoint_degradation.csv / acceptance.json`：逐场差值、三流离散度、两种总体口径、退化和固定门槛。
- `nN_runR/step_*/attempt_*/`：全部回合转移、采样锚点摘要、损失、可恢复完整状态；保留initial/selected/final。
- `evaluations/test|known/标签/attempt_000/traces.csv.gz`：所有44场的128秒轨迹，未截去启动段、饱和段或压力。

Python/Matplotlib绘制12张科学图。首版完整时序的command/actual颜色循环没有对应同一控制器，视觉检查后只修复后处理，
首版保留在figures/；正式展示用figures_v2/，目标与实际使用同色虚/实线。无重新训练或重新环境评估。
汇总图、误差分解和全场差值已逐张检查；六张完整时序经联系表及薄弱组大图检查，修正后的同色对应也已查看。

- [训练与验证（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [有效m（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [新独立测试均值与跨流SD（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [含压力全部44场配对差值（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [新慢变误差分解（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [已知薄弱组误差分解（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [新慢变低目标完整时序（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [新慢变高目标完整时序（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [新平稳完整时序（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [新阵风完整时序（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [新压力完整时序（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- [原薄弱组完整时序（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

本轮到固定预算和独立测试结束；不增加n、重要性校正、奖励、采样或学习率候选，不修改默认控制器。
