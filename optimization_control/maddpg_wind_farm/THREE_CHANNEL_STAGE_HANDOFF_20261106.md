# 三通道阶段交接（2026-11-06）

**本阶段按“三类风况各自平均 RMSE 严格低于共同 PI”验收通过，交接候选固定为 Y selected 的2048／0／2048新增步。** 18条独立风的总体均值为416.210 kW，PI为476.100 kW。S selected的415.516 kW保留为同预算对照身份，本次候选身份沿用测试释放前的冻结选择。[独立结果](YAW_INDEPENDENT_TEST_RESULTS.md) · [主验收记录](../experiments/20261105_yaw_independent/primary_acceptance.json)

| 独立风况 | Y selected平均RMSE kW | 共同PI kW | Y−PI kW |
|---|---:|---:|---:|
| 平稳 | 408.866 | 455.730 | −46.864 |
| 慢变 | 418.773 | 484.430 | −65.657 |
| 阵风 | 420.992 | 488.139 | −67.147 |
| 总体 | 416.210 | 476.100 | −59.889 |

本交接只整理现有冻结结果、依赖及调用方法。模型查询、环境推进、优化器更新和新风生成为0，权重继续引用原文件。已完成独立测试对应代码提交为 `2b533677f9a08c6ed9682002a6668b6c25f9a802`，小试为 `eec78180f2679d65ab4a71ee074d9f57a98375e5`，工程为 `a12288fd1dfdd2b299e4d949288d8a5908bcbe3f`。

## 冻结成果入口

| 用途 | 现有文件 |
|---|---|
| 独立测试协议、编号更正、统计规则 | [YAW_INDEPENDENT_TEST_PROTOCOL.md](YAW_INDEPENDENT_TEST_PROTOCOL.md) |
| 三族、逐流、最差case、收益与限制 | [YAW_INDEPENDENT_TEST_RESULTS.md](YAW_INDEPENDENT_TEST_RESULTS.md) |
| 23角色及各通道动作身份 | [identity_manifest.json](../experiments/20261105_yaw_independent/identity_manifest.json) |
| 完整依赖、物理配置和来源SHA | [独立测试lock.json](../experiments/20261105_yaw_independent/lock.json) |
| 旧六条validation选模记录 | [小试selection.json](../experiments/20261105_yaw_pilot/selection.json) |
| 414条指标与逐case轨迹索引 | [metrics.csv](../experiments/20261105_yaw_independent/metrics.csv) · [complete.json](../experiments/20261105_yaw_independent/complete.json) |
| 数值复算、查询及SHA交付记录 | [独立数值审计](../experiments/20261105_yaw_independent/independent_numeric_audit.json) · [git_delivery.json](../experiments/20261105_yaw_independent/git_delivery.json) · [output_manifest.csv](../experiments/20261105_yaw_independent/output_manifest.csv) |
| 接管与恢复工程证据 | [YAW_ENGINEERING_RESULTS.md](YAW_ENGINEERING_RESULTS.md) |
| 同预算学习、初始化和数据类型修复 | [YAW_PILOT_PROTOCOL.md](YAW_PILOT_PROTOCOL.md) · [YAW_PILOT_RESULTS.md](YAW_PILOT_RESULTS.md) |

## Y三流的完整动作依赖

每流使用原桨距父、固定 C 的部署在线speed head和自己的yaw head。下列“步”分别指其所属阶段的选择记录，Y新步与原C步数分开登记。每项完整SHA保存在独立锁的 `source.identities[run]` 和 `roles` 中，表中附摘要前缀便于人工核对。

| 流 | 原桨距父 | 固定C speed | 交接yaw |
|---|---|---|---|
| Y0 | [pitch_run_0／16384步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，`28e221e6` | [C0／0步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，`d3150ea9` | [Y0／新增2048步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，`32fd20fb` |
| Y1 | [pitch_run_1／12288步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，`0fcb0b9d` | [C1／0步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，`393461cb` | `initial=true`，由现有工厂按固定seed42派生种子重建零末层，选中新增步0；合同摘要 `5d5b8d15` |
| Y2 | [pitch_run_2／8192步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，`e2897be5` | [C2／4096步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，`81744bf3` | [Y2／新增2048步（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，`e893cb85` |

三流共用以下依赖。

- forecast为 [forecast_model.npz（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，SHA为 `a5571a19354015c8b5997823748fafd7f0a6a355a0422d35b539e4faa3992877`。现有 `agent.features(observed_prefix)` 从已观测前缀构造36维特征，12个预测时刻依次排列速度差除3、风向sin差、cos差，均为float32。yaw／speed head各接收本机15维观测和同一36维forecast。
- PINN为 [trained.keras（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，SHA为 `7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`。同目录的 [config_used.json](../experiments/20261022_wind_pinn_integration/model/config_used.json) 和 [training_report.json](../experiments/20261022_wind_pinn_integration/model/training_report.json) 是现有backend校验依赖。
- 团队模型代码为 [modify_pinn_wind_io.py（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，SHA为 `4db850074b62a7f86720534f6286b48c2a024efd9218f1b243c376fd54d5a270`。加载工厂为 `optimization_control.environments.wind_pinn_backend:create_predictor`，模型标识 `wind12-synthetic-7506554ac981`。
- 精确物理配置位于独立锁的 `source.source.base_config`，精确Y合同位于 `source.contracts.Y0/Y1/Y2`。其中包括父／forecast、半径、权限、参考模式和PINN来源。顶层 [config.yaml](../experiments/20261105_yaw_independent/config.yaml) 保存本次测试设计与预算。
- 三份桨距父的 `metadata.normalization` 保存固定归一化参数，`config.speed_reference_schedule` 均为 `(25.0, 0.11114035087719298, 0.6, 1.267)`。原父metadata的mask记录桨距权限，独立锁的基础环境mask为 `[0,1,1]`，执行Y时由现有 `yaw_pilot.World.env(scope, "Y")` 设为 `[1,1,1]`。Y权限以此入口和合同为准。
- 配套运行环境使用 [项目Python（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) 及现有 [pinn_tf216目录（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。加载入口在导入NumPy前调用 `activate_runtime`。模型输出语义为 `synthetic_test_power_w_not_physical_validation`。

这些文件按原路径引用。当前入口依赖原实验目录和跨来源SHA锁，属于实验流程调用，独立部署接口尚未提供。只取一份yaw `inference.pt` 仍需上述父映射、forecast、配置和环境语义才能得到完整动作。

严格加载还会校验实验审计依赖。完整路径集合位于独立锁的 `hashes`，以及 [小试修订锁（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) 的 `original_source`、`bank_overrides` 引用。它们登记原源码、float32修订风库及旧报告等已有文件。当前流程要求这些已登记路径与SHA匹配，完整依赖可由两份锁机器枚举。

## 物理、归一化和时钟合同

三机顺序固定T01／T02／T03。每机动作依次为失配参考角、collective pitch参考、rotor speed参考，归一化动作均在[-1,1]。对应物理边界为yaw参考[-.25,.25] rad、pitch[0,.22] rad、speed[.6,1.267] rad/s。初态为失配0 rad、pitch .04 rad、speed .9 rad/s。

| 通道 | 决策和组合 | 原执行器 |
|---|---|---|
| pitch | 原冻结父每秒按当秒实际观测重新计算 | 一阶时间常数2 s，速率上限.00872664626 rad/s |
| speed | 原C在线head每8秒决定一次±.1 rad/s有界修正；参考曲线仍每秒响应有效风速 | 一阶时间常数5 s，变化率上限.1 rad/s² |
| yaw | 新head每8秒决定一次±1°修正，叠加到原0失配参考 | 原机舱朝向执行器，时间常数5 s，速率上限.005 rad/s，heading位置界[-100π,100π] rad |

参考转速曲线斜率为.11114035087719298 rad/m，采用 `observation_float32_v1` 的原运算顺序。保持的是speed／yaw修正，桨距和基础曲线继续闭环反馈。t=0,8,…,120时两head读取同一观测和forecast，再组合为总命令。每秒仅推进一次执行器，接收下一观测后追加一次真实来流。episode统一管理held修正、两个时钟、pending回报和history。

偏航命令经原环境构造成最近的机舱参考朝向，实际失配为 `wrap(heading_actual - wind_direction_current)`。执行器使用已观测风向决定本秒命令，PINN响应使用推进后的机舱朝向和下一秒真实来流。新增head输出有界修正，完整参考还依赖父映射、参考曲线及执行器。[组合与时钟](yaw_macro.py) · [环境与实际量](../environments/maddpg_farm_env.py)

15维观测严格采用环境原float32顺序。

```text
power_fraction, effective_wind_scaled, yaw_scaled, pitch_scaled, speed_scaled,
previous_yaw_action, previous_pitch_action, previous_speed_action,
farm_target_fraction, farm_error_fraction, ambient_wind_scaled,
wind_direction_sin, wind_direction_cos, turbulence_intensity, remaining_fraction
```

单机功率除5 MW，全场目标和误差除15 MW，风速除25 m/s。实际yaw／pitch／speed使用上述动作物理边界作仿射缩放，前次命令保留原归一化坐标，风向用sin／cos，TI为无量纲，remaining为 `1-t/128`。使用固定物理尺度，归一化参数随父metadata和冻结配置引用。

PINN适配器接收SI物理12输入，依次为 `[U,theta,TI,gamma1..3,pitch1..3,speed1..3]`。U及有效风速为m/s，角度rad，speed为rad/s，功率输出为W。wind direction为从+x逆时针的flow-to方向。现有 `wind_pinn_backend.team_inputs` 负责团队三机重排和角度wrap，模型内部负责该版本的编码与归一化，外层适配器采用identity缩放。原域检查及约1e-6数值裕量以锁内 `plant.bounds` 为准。[SI桥接](../environments/wind_pinn_backend.py)

## 直接读取与纯保存数据复核

下列PowerShell示例可从任意当前目录执行，只读原结果，不导入PINN、不创建环境、不写文件。它核对1720项产物SHA及三个主均值。图像、CSV和身份清单可直接打开，已有报告生成命令具有独占写入语义，查看现有结果使用本例即可。

```powershell
@'
import csv
import hashlib
import json
import math
from pathlib import Path

root = Path("./optimization_control/experiments/20261105_yaw_independent")
delivery = json.loads((root / "git_delivery.json").read_text(encoding="utf-8"))
manifest_path = root / "output_manifest.csv"
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == delivery["manifest_sha256"]
with manifest_path.open(encoding="utf-8", newline="") as stream:
    manifest = list(csv.DictReader(stream))
for item in manifest:
    path = root / item["relative_path"]
    assert path.stat().st_size == int(item["bytes"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
with (root / "metrics.csv").open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream))
assert len(rows) == 414
for family in ("stationary", "ramp", "gust"):
    actual = [float(r["rmse_w"]) for r in rows
              if r["family"] == family and r["controller"] in
              ("Y0_selected", "Y1_selected", "Y2_selected")]
    reference = [float(r["rmse_w"]) for r in rows
                 if r["family"] == family and r["controller"] == "pi"]
    assert len(actual) == 18 and len(reference) == 6
    y_mean = math.fsum(actual) / 18
    pi_mean = math.fsum(reference) / 6
    assert y_mean < pi_mean
    print(family, "Y kW", y_mean / 1000, "PI kW", pi_mean / 1000)
print("Verified saved files", len(manifest), "PINN rows 0, environment steps 0")
'@ | & './.venv/Scripts/python.exe' -B -X utf8 -
```

逐case完整轨迹从顶层 `complete.json` 的 `results` 列表定位，该列表与 `lock.json.roles` 同序。读取对应引用中的角色 `complete.json`，再读取其 `cases[index]` 引用指向的case记录，最后由 `eval.trace.path` 读取NPZ。NPZ字段顺序保存在 `fields`，数组形状为[1,129,52]，第0行为reset。独立RMSE取响应步1…128的 `error_w`。源代码 [forecast_speed_training.TRACE](forecast_speed_training.py) 定义前49列，末3列为yaw z。现有数值审计已逐条从轨迹重算RMSE、总命令变化和奖励。

## 现有加载与单边界纯推理示例

准确入口为 [yaw_independent_test.policy](yaw_independent_test.py)，内部调用 [yaw_pilot.inference](yaw_pilot.py)。角色从冻结锁选择 `kind="policy"`、`arm="Y"`、`role="selected"`。Y0／Y2轻量快照仅保存新增yaw权重，工厂同时恢复父pitch、C在线speed和forecast；Y1按锁重建零yaw初态。推理快照与完整训练状态的用途分别由私有schema／purpose及来源合同验证。

下例使用已有工程记录中的t=0观测和当时forecast，三流各计算一次策略命令。它仅执行策略MLP前向，PINN查询、环境推进和更新均为0，返回三机总命令参考。输入来自旧工程样本，输出用于检查加载和动作组合。

```powershell
@'
import json
import sys
from pathlib import Path

repo = Path(".")
origin = Path(".")
sys.path.insert(0, str(repo))
from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
activate_runtime(origin / ".venv/pinn_tf216")
import numpy as np
import torch
torch.set_num_threads(1)
torch.use_deterministic_algorithms(True)
torch.manual_seed(42)
from optimization_control.maddpg_wind_farm import yaw_independent_test as test
from optimization_control.maddpg_wind_farm import forecast_speed_training as source

lock = test.context()
cfg = lock["source"]["source"]["base_config"]["environment"]
low = np.asarray(cfg["action_low"], dtype=float)
high = np.asarray(cfg["action_high"], dtype=float)
engineering = repo / "optimization_control/experiments/20261105_yaw_engineering"
entries = json.loads((engineering / "real_zero.json").read_text(encoding="utf-8"))["cases"]
for run in range(3):
    role = next(r for r in lock["roles"] if r["kind"] == "policy"
                and r["arm"] == "Y" and r["role"] == "selected" and r["run"] == run)
    agent = test.policy(lock, role)
    ref = entries[run * 3]["artifact"]
    sample = torch.load(source.verify(ref), map_location="cpu", weights_only=False)["actual"]
    obs = sample["obs"][0].copy()
    features = sample["macros"][0]["forecast"].copy()
    before = test.counters(agent)
    speed_z = agent.speed_z(obs, features)
    yaw_z = agent.z(obs, features)
    action, fixed_C_action, pitch_parent = agent.compose(obs, speed_z, yaw_z, (low[0], high[0]))
    assert action.shape == (3, 3) and np.isfinite(action).all()
    assert np.max(np.abs(action)) <= 1
    assert before == test.counters(agent)
    references = (low + high) / 2 + action.astype(float) * (high - low) / 2
    print(role["id"], "selected new step", role["step"])
    print("columns: yaw reference rad, pitch reference rad, rotor speed reference rad/s")
    print(references)
print("PINN rows 0, environment steps 0, optimizer updates 0")
'@ | & './.venv/Scripts/python.exe' -B -X utf8 -
```

真实闭环使用现有 [YawEpisode](yaw_macro.py) 管理双方held和单次环境推进，入口示例可在 [yaw_pilot.evaluate](yaw_pilot.py) 与 [独立测试worker](yaw_independent_test.py) 阅读。新的有效边界forecast由 `agent.features(observed_prefix)` 计算。上面一次边界纯调用不能直接替代整段episode管理。

重新创建 `World` 会加载PINN，`env.reset` 已消费1行模型输入，完整128步回合再消费128行。回放、报告和测试生成入口还会写入新产物。重新运行环境属于另一次有预算的实验工作，应先确定新输出身份、固定风库和查询额度，再复用这些私有流程。当前交接使用读取及纯策略示例。

## 保留的结论边界

- 关闭yaw的108个独立测试回合与固定C完整轨迹逐值一致，工程接管和保父等价成立。独立测试中的Y0／Y2各有.190／.031 kW平均改善，Y1 selected仍为initial；前两流speed修正也为零。
- 新增yaw总体仅.073671 kW模型内平均差值，Y又比同预算S高.694296 kW。该数值未建立实际物理意义或三流各通道共同新增学习收益。已有PINN弱yaw响应和部分符号问题继续限制解释。
- 原400／500 kW联合精度门槛在本次新独立测试下仍为Y、S各0／3流，Y最差668.935 kW。平稳族Y−PI的95%描述区间为[−128.119,+36.316] kW，跨0，冻结主指标仍按三族平均判定。
- Y final比selected总体高.085854 kW，S高1.403204 kW，S2退化4.251680 kW。5%比值保留为诊断。
- 旧压力结果为Y1609.551 kW、PI1381.903 kW，Y仍较差。本轮引用的是既有低风高目标压力，新增独立压力查询为0。[压力来源](../experiments/20261105_yaw_independent/known_pressure_source.json)

关键图可直接查看 [分族均值（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、[固定case17实际控制（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、[selected到final（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。它们来自当前代理模型的软件实验。

## 交接核对与独立终审

本交接核对原依赖路径、SHA、三份parent的归一化metadata及speed schedule、Y快照身份、保存数据核查代码和纯策略调用。两段示例已从原项目目录执行通过，第一段核对1720项SHA和三族主均值，第二段三流各计算一次策略命令，TensorFlow/PINN未加载，环境推进和更新为0。原成果目录和归档保持只读，新增内容为本文件，低于16 MiB。本地提交后以Git记录定位本交接版本。

交接写成时 [最终独立审核](FINAL_OPTIMIZATION_REVIEW_20261106.md) 已完成，本轮已读取。终审覆盖既有候选、新测试完整性、编号时序、保存轨迹和统计口径，结论为本阶段可以收尾，未发现影响既定候选或主判定的已证实错误。本文两段交接示例另外完成本轮只读执行核验。

终审将桨距n8与C→Y分别交接，二者的父源、参考模式及风库各自独立。三通道继续采用本表10-23 progressive父源和 `observation_float32_v1`，本次交接沿用这一身份链。已有小试复核的释放时快照也可查看 [review_at_release.md](../experiments/20261105_yaw_independent/review_at_release.md)。
