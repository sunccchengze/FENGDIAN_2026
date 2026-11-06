# speed n1/n8 固定预算实验结果（2026-10-29）

**本轮完成；预声明 n8 可重复学习收益门槛未通过，完整稳定性 2/3。**
正式2×3×8192=49152步已完成并锁定，n8 selected为新增训练点2/3；不追加预算、不换父、不开放yaw、不启动下一候选。结果仅是当前合成代理模型内的软件实验结论。

## 授权、来源与唯一改动

本轮按主对话2026-10-29新前瞻决定执行，接受桨距dd6f400中selected局部改善与终点/流2反证并存的情况，不把旧停止条件称为通过。旧[SPEED_NSTEP_DRAFT.md](SPEED_NSTEP_DRAFT.md)、[工程结论](SPEED_NSTEP_ENGINEERING_RESULTS.md)及历史失败保持原文。正式冻结协议为[SPEED_NSTEP_PROTOCOL.md](SPEED_NSTEP_PROTOCOL.md)，实际config SHA见[config.yaml](../experiments/20261029_speed_nstep_control/config.yaml)。

独立审查完整读取，报告SHA为26aeeff15c92c9c9aa6563224e1efab76670739da930a67cd9738cac372aae09，确认被审c3e9cc0核心范围无阻断项；新入口自身3项契约测试、顺序检查及零头gate通过。未改核心文件，旧v4加载器仍独立；优化器列表长度的非阻断加固建议没有混入本算法对照。审查快照、读取决定和入口检查在本地实验目录保存。

两臂都完整冻结原20261023三份pitch父Actor，独立speed头，仅Critic TD目标n1/n8不同。原父累计插入32768/28672/24576，沿用原头seed8405、末层零、继承Critic/target/Adam/回放/RNG及父target滞后。未使用新n8桨距父、旧speed终点或新reward/lr。回放所有起点同资格，实际m短尾bootstrap、true done停止；未来target联合总动作使用末状态和当前更新radius。探索、天气/目标/初态成对一致，逐流64回合。

## 接管、预算与恢复

原父/v4零头/n1/n8在三流全部保留父回放上的online/target动作最大差0；新validation六场完整闭环执行状态、动作、功率和RMSE差全为0，9项比较全部通过。接管评估9216步、学习更新0；不以400/500 kW替代接管。

正式六job各8192步、3841次update，共23046次update。warmup512在预算内，无环境学习smoke。每回合保存，全390份检查点（每job65份）核对来源、父online不变、累计插入和更新计数。run0两臂在2048处由不同进程恢复，探索状态/回放/RNG随检查点恢复，完整天气和噪声哈希配对一致；8个子进程正常退出，无未完成attempt或未保存重算。原39次工程内存update没有重复；其updates.json为30行分组台账，不称39份逐调用轨迹。

新增评估步单列：接管9216、正式验证30×6×128=23040、共同固定父及fixed/P/PI验证4608、独立test92160、方向核查480，共129504。没有新的环境学习smoke或额外训练流。测试各角色评估次数包含initial与selected相同权重时的重复评估，不能当独立训练证据。

六job各记录245824个采样起点。n8实际m均值逐流为7.78210/7.77795/7.78084，完整八步比例94.522%/94.455%/94.526%；短尾未过滤，详见actual_m_statistics.json。两臂最终父target与Replay RNG精确一致，新增权限引起的观测/回报差异不冒充相同回放内容。

resolved_execution.json记录实际入口参数和Python3.12.14、NumPy1.26.4、Torch2.13.0+cpu、TensorFlow2.16.1。冻结config中继承的旧smoke_steps_per_arm=1024、noise_namespace=8404、smoke命名空间及base_config.training模板均未被新入口读取；本轮实际smoke为0，探索使用新design_entropy的purpose=3，不应按旧模板重算预算。

## Validation：分清稳定、父能力与n1改善

每格mean/worst为六场case RMSE算术均值/最大值，单位kW。严格均值改善选模，initial参与；下表比值用未四舍五入值计算，父为相同新场景下的固定父。

| 臂 | 流 | selected步 | initial mean | selected mean | final mean | final worst | final/selected | final/父 mean / worst | final/n1 mean / worst | 完整稳定 |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| n1 | 0 | 2048 | 364.34 | 362.27 | 375.89 | 510.66 | 1.0376 | 1.0317 / 1.0864 | 1.0000 / 1.0000 | False |
| n8 | 0 | 0 | 364.34 | 364.34 | 379.45 | 516.34 | 1.0415 | 1.0415 / 1.0985 | 1.0095 / 1.0111 | False |
| n1 | 1 | 4096 | 360.06 | 342.88 | 348.01 | 524.98 | 1.0150 | 0.9665 / 1.0862 | 1.0000 / 1.0000 | False |
| n8 | 1 | 4096 | 360.06 | 338.91 | 342.19 | 504.60 | 1.0097 | 0.9504 / 1.0440 | 0.9833 / 0.9612 | True |
| n1 | 2 | 2048 | 336.13 | 307.96 | 321.84 | 453.29 | 1.0451 | 0.9575 / 1.0158 | 1.0000 / 1.0000 | True |
| n8 | 2 | 2048 | 336.13 | 306.75 | 315.31 | 432.62 | 1.0279 | 0.9380 / 0.9695 | 0.9797 / 0.9544 | True |

n8相对同预算n1，selected总体比值0.996928，final总体比值0.991595；预声明门槛要求三流selected_step>0，selected/final均三流严格改善且总体至少1%，结果未通过。稳定还要求final/selected<=1.25，final mean/worst对父及n1均<=1.05，不能只用宽松selected比值宣称稳定。

5%是不劣容差，不是性能改善；相对冻结父的mean/worst比值与相对同预算n1分列。没有同预算pitch续训臂，本轮不能证明新增speed权限本身的因果收益。

原精度门槛单独报告为mean<=400、worst<=500 kW，通过流数如下。测试精度仅是冻结后描述，不用于改选模型。

| 臂 | 角色 | validation精度 | 新常规test精度 |
|---|---|---:|---:|
| n1 | initial | 3/3 | 0/3 |
| n1 | selected | 3/3 | 0/3 |
| n1 | final | 1/3 | 0/3 |
| n8 | initial | 3/3 | 0/3 |
| n8 | selected | 3/3 | 0/3 |
| n8 | final | 1/3 | 0/3 |

## 一次新独立测试及完整控制方案比较

六job/选择锁和核心审计完成后才生成新test。18常规case为三风况×2.75/3.35/3.85MW×初始pitch.025/.055；另2个7.6m/s、4.4MW已知压力回归单列，不称新独立风况。没有重抽或用测试整定。所有策略和固定/P/PI使用同一模型、来流、目标、初态、reference模式与执行器。

| 策略 | 新常规case均值±流间SD kW | 已知压力均值 kW |
|---|---:|---:|
| parent parent | 378.33 ± 21.22 | 1607.95 |
| n1 initial | 378.33 ± 21.22 | 1607.95 |
| n1 selected | 358.96 ± 30.69 | 1668.78 |
| n1 final | 374.29 ± 25.43 | 1717.61 |
| n8 initial | 378.33 ± 21.22 | 1607.95 |
| n8 selected | 360.60 ± 33.89 | 1653.41 |
| n8 final | 369.56 ± 36.86 | 1711.76 |
| common p | 527.47 ± 0.00 | 1383.30 |
| common pi | 434.99 ± 0.00 | 1383.30 |

SD来自三条主seed42派生训练流，不是置信区间；P/PI固定方案只有一个共同评估，SD为0。新常规test中n8 selected相对n1约差0.46%，final约改善1.26%；逐流selected仅流1改善，final为流1/2改善。压力下两臂selected/final都弱于固定父及P/PI。完整MADDPG与“pitch反馈＋yaw/speed调度”是完整控制方案比较，新增权限收益仍需同预算父续训控制与逐通道消融，不据此表替代。

新常规test单独应用相同工程不劣比值时，n8稳定为3/3、n1为2/3，见paired_results.csv；这是有限的终点能力保留正面证据，不反向修改validation稳定2/3的验收，也不把5%不劣称为改善。新test中n8 selected仅1/3配对改善、流0仍无新增学习，未构成三流可重复收益。

完整720条指标/92160行轨迹从保存时序复算RMSE；三流两臂的zero-speed selected/final共30720行时序与固定父精确一致。保存时序重构策略动作、同观测父pitch映射、首步在内执行器速率、heading-direction失配语义、风/目标/初态均核对。逐case channel_diagnostics区分冻结映射不漂移与闭环观测变化引起的pitch轨迹差异，speed头近边界比例只作描述，不认定唯一原因。

## 小范围公共锚点方向核查

只执行预声明ramp高目标t64、三流公共父状态、共同speed±.05rad/s和0，随后固定父延续32步，480评估步；同一状态与完整首动作由六组Critic评分，三机Q/均值、G32和tracking/动作惩罚分项全部保留，不增锚点或搜索配置。

| 臂 | Critic角色 | 均值Q的反向/6个非零比较 |
|---|---|---:|
| n1 | initial | 4/6 |
| n1 | selected | 1/6 |
| n1 | final | 2/6 |
| n8 | initial | 4/6 |
| n8 | selected | 2/6 |
| n8 | final | 3/6 |

反向定义为|ΔQ|、|ΔG32|都>1e-5且异号。样本高度相关且很小，G32是单条未来风下有限实现回报，不是真实长期Q；selected的训练时刻不同，不能冒充同预算Critic对比。多步TD仍有行为策略off-policy偏差，不解释为普遍Q修复，也不改变由完整回合得到的结论。

## 产物、图和复现

根目录为./optimization_control/experiments/20261029_speed_nstep_control。Git保留config.yaml/metrics.csv/summary.txt和本轮源码/测试/协议/报告；权重、轨迹和图按项目规则本地保留。

- checkpoint_manifest.csv：390份路径/SHA、initial/selected/final、n、插入数和更新数；normalization_n1.json/normalization_n8.json保存固定物理归一化。
- processes.jsonl与formal/*/attempt_*/：进程/完整恢复与每回合状态；history.csv为训练退化曲线。
- test/metrics.csv、trajectories.csv、aggregate.csv、paired_results.csv、channel_diagnostics.csv、delivery_verification.json：测试、父/配对比值与执行核查。
- direction.csv、direction_summary.json：预声明方向检查；independent_review_read.md、prelaunch_entry_check.json、namespace_audit.json保存前置证据。
- figures/validation_stability、test_comparison、actual_controls各PNG/PDF：Python/Matplotlib绘制，图像查看记录随交付核验保存。
- delivery_verification.json、git_delivery.json、delivery_files.csv、output_manifest.csv：保存数据与提交清单。

图中heading相对该场首个已绘制风向（t=1）显示，绝对机舱heading及来流方向均在原始轨迹保留；失配角仍按heading-direction计算。图的参考零点不改变执行器语义。

在该独立工作树使用已有./.venv/Scripts/python.exe，模块speed_nstep_training会激活已有pinn_tf216运行库，不安装新依赖。新复现须指定新的独立输出目录；不覆盖当前冻结产物。

```powershell
$py = './.venv/Scripts/python.exe'
$out = 'optimization_control/experiments/20261029_speed_nstep_reproduction'
$env:TF_NUM_INTRAOP_THREADS = '1'
$env:TF_NUM_INTEROP_THREADS = '1'
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training prepare --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training gate --output $out
# 阅读固定独立审查报告并核对核心SHA后，记录接受；不得凭该命令替代审阅。
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training accept-review --output $out
foreach ($runId in 0..2) {
    foreach ($arm in @('n1', 'n8')) {
        if ($runId -eq 0) {
            & $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training worker --output $out --arm $arm --run-id $runId --stop-after 2048
            if ($LASTEXITCODE -ne 0) { throw 'Planned restart worker failed' }
        }
        & $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training worker --output $out --arm $arm --run-id $runId
        if ($LASTEXITCODE -ne 0) { throw 'Formal worker failed' }
    }
}
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training lock --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training audit --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training test --output $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training diagnostic --output $out
# 测试聚合只读保存数据，不重跑core audit中的父/PPI环境评估。
$aggregateCode = @'
from pathlib import Path
import sys
from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
activate_runtime(Path('./.venv/pinn_tf216'))
from optimization_control.maddpg_wind_farm.speed_nstep_training import context
from optimization_control.maddpg_wind_farm.speed_nstep_audit import audit_test
root = Path(sys.argv[1]).resolve()
saved, _ = context(root)
audit_test(root, saved)
'@
& $py -B -X utf8 -c $aggregateCode $out
& $py -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_training figures --output $out
```

原路径父/模型须仍可读且SHA相符。现有目录只复查保存结果，不再训练；恢复不得越过选择/test锁。源码冻结后未修改；交付checker/report writer为带SHA的后处理，不调用环境或优化器。本轮结束，不自动新候选、追加训练、降低门槛、合并master或推送。
