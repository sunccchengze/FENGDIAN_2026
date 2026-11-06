# 固定 n8 桨距策略按风况平均核验与交接

2026-11-05。**原 2026-10-28 的三份验证选中 n8 桨距检查点，在三批既有独立常规测试中，均达到每个风况族的平均 RMSE 低于 PI 的要求。** 低风高目标压力均值仍高于 PI。用户是在已有结果公开后调整验收标准，本报告按新口径回顾核验。原检查点、选模、历史验收和默认配置沿用其既有记录。[核验配置](../experiments/20261105_pitch_n8_average_handoff/config.yaml)

## 最新共同测试

主表使用误差记忆正式试验的独立测试风库，常规目标为 2.75／3.35／3.95 MW，初始桨距为 .03／.05 rad。每个常规风况族有 12 个完整 128 步场景。对三份固定策略先算每流场景均值，再等权平均。PI 使用每场一份公共轨迹，等权计算；三流比较共享同一份 PI。平稳、慢变、阵风三项均严格低于 PI 即通过。逐场胜负、各流范围、压力、pooled 值均另报。样本标准差描述这三条流，配对槽位共享场景与策略。

| 范围 | n8 场景均值 kW | PI 场景均值 kW | n8−PI kW | n8 相对 PI | 三流均值范围 kW | 跨流 SD kW | 逐场严格胜 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 平稳 | 366.84 | 398.55 | −31.71 | 低 7.96% | 355.96–377.94 | 10.99 | 23／36 |
| 慢变 | 369.43 | 454.46 | −85.04 | 低 18.71% | 360.02–381.13 | 10.74 | 30／36 |
| 阵风 | 353.95 | 442.21 | −88.26 | 低 19.96% | 344.74–366.98 | 11.61 | 25／36 |
| 常规共 36 场 | 363.40 | 431.74 | −68.33 | 低 15.83% | 357.13–375.35 | 10.35 | 78／108 |
| 低风高目标压力 8 场 | 1496.59 | 1321.09 | +175.50 | 高 13.28% | 1415.76–1592.66 | 89.43 | 0／24 |
| 含压力共 44 场 | 569.44 | 593.44 | −24.00 | 低 4.04% | 549.61–596.68 | 24.40 | 78／132 |

常规 pooled RMSE 为 n8 371.86、PI 453.19 kW。含压力后分别为 724.12、699.60 kW，pooled 排序反转。这里 pooled 对各回合 RMSE 平方等权平均后开根，因回合均为 128 步，等价于对全部响应步的平方误差计算 RMSE。压力为 7.6／7.8 m/s、4.35／4.55 MW 与两初态，三流均劣于 PI，最差配对高 308.90 kW。常规最差配对出现在流 1、3.95 MW、.03 rad 平稳场，n8 483.79 对 PI 296.25 kW。[最新原始指标](../experiments/20261104_pitch_error_memory_formal/metrics.csv) · [逐场配对](../experiments/20261105_pitch_n8_average_handoff/paired_cases.csv)

## 分批证据和终点限制

以下每批风库的常规均值独立计算，单位 kW，格式为 n8／该批公共 PI。各批常规波形文件哈希彼此无交集。Actor 条件和最新试验的 8 个压力槽位具有相同来流数组、目标和初态，这部分是重复压力证据。旧 n8 测试的压力初态为 .025／.055 rad。

| 批次及常规目标 MW | 平稳 | 慢变 | 阵风 | 常规总体 | 压力 |
|---|---:|---:|---:|---:|---:|
| 10-28 n8，2.65／3.25／3.95 | 464.23／532.52 | 397.86／501.16 | 397.66／494.16 | 419.92／509.28 | 1497.00／1321.91 |
| 10-29 Actor 条件，2.725／3.325／3.925 | 448.13／517.72 | 518.90／608.88 | 373.30／451.09 | 446.78／525.90 | 1496.59／1321.09 |
| 11-04 误差记忆，2.75／3.35／3.95 | 366.84／398.55 | 369.43／454.46 | 353.95／442.21 | 363.40／431.74 | 1496.59／1321.09 |

10-28 原 n8 的 `final` 在其自身测试上，平稳／慢变／阵风 RMSE 分别为 459.96／405.03／402.41 kW。慢变较 `selected` 上升 7.16 kW，流 2 从 401.14 上升到 421.72 kW。常规均值 419.92 升至 422.47 kW。流 2 终点较自身初始策略常规／慢变／阵风高 5.34%／6.02%／8.17%。后两批各自的续训终点属于别的干预，交接只采用其已核验的 n8 初始别名。`selected` 的常规平均结论适用于这三份固定检查点，继续训练的终点表现单独保留。[分批及逐流指标](../experiments/20261105_pitch_n8_average_handoff/metrics.csv)

原 n8 通过该轮 `selected` 慢变门槛，终点和压力限制保留。gamma 完整验收失败，该试验初始状态沿用 10-23 旧父，本报告将其排除在原 n8 的三批对照之外。Actor 条件和因果误差记忆各自的完整验收仍失败。闭环消融定位到续训后的策略差异，未据此实施冻结主干候选。[n8 原验收](PITCH_NSTEP_RESULTS.md) · [gamma 结果](PITCH_GAMMA_RESULTS.md) · [Actor 条件结果](PITCH_ACTOR_CONTEXT_RESULTS.md) · [记忆正式结果](PITCH_ERROR_MEMORY_FORMAL_RESULTS.md) · [记忆消融](PITCH_ERROR_MEMORY_ABLATION_RESULTS.md)

## 交接入口

唯一策略身份入口为 `20261028_pitch_nstep_mechanism/candidate_manifest.json`。三份策略由原训练的 18 个完整验证回合均值从含 initial 的保存点中选出，主种子为 42。表中 `selected` 步是 10-28 续训步数。各流保存当时的 online／target、Adam、回放、算法及采样 RNG，外部探索 RNG 在恢复元数据中。三份全部交接，使用方按事先确定的流号加载。历史 manifest 保持实验候选身份。原已完成的新进程验证回放覆盖三份策略各 18 场，轨迹和指标最大差均为 0。[候选清单](../experiments/20261028_pitch_nstep_mechanism/candidate_manifest.json) · [既有恢复验证（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

| 流 | 验证选中步 | 验证均值 kW | 检查点 | SHA256 |
|---|---:|---:|---|---|
| 0 | 16384 | 411.97 | [n8_run0（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) | `1f91cdba7676f1c32434e7e1e130cac6df155e4c41798ef6b88c6c58b032678a` |
| 1 | 12288 | 411.55 | [n8_run1（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) | `cc0b37ebd7da662ce435658891d660c2699bca438280d0ae51da992557a3a957` |
| 2 | 4096 | 403.35 | [n8_run2（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) | `0e19dd05fcdd58701aa1fd17e87739f05e60fe71a2a9bc60c162918607733b5b` |

使用已有 `pitch_nstep_handoff.load_candidate(manifest_path, run)` 校验清单与恢复元数据。底层私有格式 `pitch_nstep_v1` 由 `NStepMADDPG.load(path, expected_n=8)` 加载，gamma 为 .99。运行示例只加载一个预先指定的流。已有 `obs` 时用 `agent.act(obs, noise_std=0.0)` 得到归一化总目标，再通过清单环境的 `env.step(action)` 执行。

```powershell
Set-Location -LiteralPath .
$py = './.venv/Scripts/python.exe'
@'
from pathlib import Path
from optimization_control.maddpg_wind_farm.pitch_nstep_handoff import load_candidate

manifest_path = Path('./optimization_control/experiments/20261028_pitch_nstep_mechanism/candidate_manifest.json')
agent, meta, manifest = load_candidate(manifest_path, run=0)
print(meta['run'], meta['step'], manifest['model_version'])
'@ | & $py -B -X utf8 -
```

环境按 `manifest['base_config']` 由 `workflow.build_env` 构建，已有本地 TensorFlow 运行时先按 `fixed_pinn_demo.activate_runtime` 激活，再导入数值库。归一化固定为 `[3,15]` float32，额定功率每机 5 MW，入口及有效风速尺度 25 m/s，目标及误差尺度 15 MW。动作是 `[3,3]` 的 `[-1,1]` 归一化总目标，顺序 yaw／pitch／speed，权限 `[0,1,0]`。桨距范围 0–.22 rad，最大速率 .00872664626 rad/s，时间常数 2 s。采用原 `legacy_physical` 参考方式，环境投影 yaw 相对参考为 0，机舱跟踪风向，speed 按当前有效风速 × .11114035087719298 后裁剪至 .6–1.267 rad/s。PI 沿用 kp 1.5、ki .08、bias .04 rad、antiwindup .2 和 integral limit .3 rad。[观测列及归一化](../experiments/20261028_pitch_nstep_mechanism/candidate_normalization.json) · [加载入口](pitch_nstep_handoff.py)

固定代理为 `wind12-synthetic-7506554ac981`，SHA256 `7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`。结论限于该三机合成准静态代理、统一执行器和这些风况目标。真实风机和全局可达性仍超出证据范围。speed 任务可把清单作为新的桨距参考入口，使用前须核对本次 `legacy_physical` 与该任务自己的参考模式及父配置。正在冻结测试的 speed 父继续由其原清单管理，本报告只交接桨距策略。

## 只读复核

复核加载并核对三份原权重、选模元数据、测试中的初始 Actor 和零支路、初始轨迹别名、PI 唯一性、测试风库 SHA、所有纳入回合的 RMSE 及配对算术。最新测试有 20 个逻辑角色和 19 个实际轨迹索引，恒零流 2 的 `selected` 指向 `initial`；两个初始臂各三份记录在统计中合为三流。Actor 条件的复用链同样核对到原轨迹。10-28 最早的轨迹字段只够从时序复核风速，风向仍由共同风库身份和冻结环境核对。后两批另核对逐步风向和偏航。全部结果来自已有文件。新增模型推进、优化器更新、独立测试均为 0。[审计摘要](../experiments/20261105_pitch_n8_average_handoff/summary.txt)

```powershell
Set-Location -LiteralPath .
$py = './.venv/Scripts/python.exe'
& $py -B -X utf8 optimization_control/experiments/20261105_pitch_n8_average_handoff/verify_handoff.py
```
