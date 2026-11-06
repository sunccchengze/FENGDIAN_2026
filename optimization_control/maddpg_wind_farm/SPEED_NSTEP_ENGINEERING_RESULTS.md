# speed n-step 工程核查结果（2026-10-28）

可选 n1/n8 适配通过本轮实现核查；正式训练启动条件仍未证实，未启动 49152 步草案。结果只支持回放、目标构造、默认兼容和恢复正确性，不支持 speed 性能改善或三通道学习成功。正式训练 0 步、环境新采样 0 步、代理模型预测 0 次、新候选权重文件 0；yaw、队友模型及历史实验保持只读。

本轮依据为先行冻结的 [工程协议](SPEED_NSTEP_ENGINEERING_PROTOCOL.md)，待审阅设计见 [n1/n8 草案](SPEED_NSTEP_DRAFT.md)。主对话提供的桨距结果仍为：n8 selected 397.86 kW 对 n1 420.54 kW，改善 5.39%；final 优势仅 1.57%，流 2 final 对父回归 5.34%，尚缺同锚点 Q 方向复核。因此不能将 selected 通过视为“方向和稳定性同时改善”，也不能由本工程的精确相等推出迁移收益。

## 实现边界与检查结果

- 逐字复用桨距提交 `740d04044e6b046dfe6256bfa3c2d4ef88925783` 的 `SequenceReplay` 类，独立核对 Git blob、保存源码及本地类文本。原文件 SHA256 为 `17badc54c0be33dfb97447c6c17eee448d8d3c2c788cf27b94e4561662f73590`，类文本 SHA256 为 `20196f46f83558be2b4ea8882fab02617f96f745a94fb8a9a59c9810ae682ecb`。严格包装器沿用该类的采样和窗口方法，不经过来源类的缺省 legacy 推断。
- 原 `FrozenSpeedMADDPG`、v4 加载器和训练入口未改；新增独立 `FrozenSpeedNStepMADDPG`，默认 n1，显式新格式 `frozen_speed_nstep_v1`。旧 v4 仍由原加载器处理；适配旧回放须提供独立累计计数、horizon、来源 SHA/epoch，并通过全保留环的连续性检查。缺少证据即拒绝，不按 size 自动补齐。
- 新类直接继承原 `update` 方法。三条真实父流各做 3 对 n1 更新，共 9 对；原实现与适配实现的锚点、损失、网络、target、Adam 和 RNG 精确一致。三份父 Actor 在线权重不动，父 target 保留原滞后并按原 tau 路径更新。
- n8 只替换 Critic 的累计奖励、末状态、终止标记和实际 `gamma^m`。对全部实际更新挂钩检查集中 Critic 输入：起点动作是回放的三机总指令；未来动作由末状态的 target 父 reference 加 target speed 头组成，统一采用当前更新 radius。真实检查覆盖 `.02/.06/.10` rad/s。合成算例另将在线/目标头设为不同值，防止误用在线头。
- 短尾以实际 m bootstrap，true done 不 bootstrap，禁止跨 episode；同一采样资格和 RNG，不仅抽完整八步窗口。环回卷、覆盖后新写入、缺尾及恢复均检查。新格式保存全部六组网络、head/Critic 优化器、回放、单调序号、插入计数、m 直方图和 RNG。
- 对六份真实训练回放全部保留 transition 独立复算共同奖励，共 184320 条。使用各检查点明确保存的 `reward_scale=100`、`action_change_weight=.001`，最大重构误差 `4.76837158203125e-7`；n-step 直接累计已缩放奖励，不再乘 scale。没有使用 test 状态。

## 真实回放迁移与内存分叉

以下计数由检查点 lineage/steps 元数据独立推导，再与 size、position、全环状态连续性及时钟/done 交叉核对。表中旧 final 只用于工程恢复检查，不是新实验起点。追加 8 条取自同一回放内最早完整训练 episode 的前 8 条，仅在内存副本追加。

| 流 | 原 pitch 父累计 / 保留 / position | 旧 speed final 累计 / 保留 / position | 副本追加 8 条后累计 / position | 真实丢弃更新 |
|---|---|---|---|---:|
| 0 | 32768 / 32768 / 0 | 40960 / 32768 / 8192 | 40968 / 8200 | 13 |
| 1 | 28672 / 28672 / 28672 | 36864 / 32768 / 4096 | 36872 / 4104 | 13 |
| 2 | 24576 / 24576 / 24576 | 32768 / 32768 / 0 | 32776 / 8 | 13 |

每流 13 次由父副本原 n1/适配 n1/n8 各 3 次、n8 内存保存前后各 1 次、旧 final 追加后内存保存前后各 1 次构成，共 39 次。全部丢弃，不写候选权重。三份追加副本的指定探针均为实际 `m=[8,1,1]`、`done=[0,0,1]`，分别覆盖完整新窗口、最新非终止缺尾、追加前真实终止。恢复后下一次更新的锚点、损失、网络、优化器及回放/RNG 精确一致。

## 验证记录和局限

受影响单测共 16 个唯一用例通过：新增 n-step 8 个、原 frozen-speed 8 个。执行顺序为新增早期 7 个与原 8 个组合通过，再补原生空回放证明用例、运行新增最终 8 个通过；不是声称单次运行了 16 个。新增用例覆盖 n1 精确更新、环回卷与覆盖、拒绝不完整迁移、实际 m/单次奖励缩放、未来目标总动作与当前 radius、父冻结和 target 滞后、恢复与缺字段拒绝、原生空序列。

开发时曾发现“错误累计数 67”与“真实累计数 35”在容量 32 下有同一个 position，单凭环内容无法识别整圈计数差。随后在工程输入冻结前改为强制独立 `expected_insertions` 和来源证据；错误累计数、缺计数、断连续边及混合 done 均拒绝。此限制不能靠重新编号掩盖。

最终保存产物 QA 不运行 optimizer 或环境：核对完成锁、源码/历史 SHA、历史目录文件清单、六份奖励重构、六份迁移证明、39 次更新台账、9 对 n1 目标/损失相等以及 v4 缺迁移证据拒绝。原工作区 `PROJECT_STATUS.md`、`README.md`、`optimization_control/TASKFLOW.md` 与工程冻结时 SHA 一致。4 个新增 Python 文件 AST 解析通过；提交另检查精确文件清单与空白符。

这些检查不评估闭环性能，也未重复旧初始化接管或独立测试。原 speed 的稳定性和可重复收益失败结论保留。未来 n1/n8 比较只识别该 TD 目标改动的收益；它本身不能替代新增 speed 权限相对同预算父策略的验证。n-step 的行为策略后续奖励仍有 off-policy 偏差，未增加 IS 或其他算法改动。

## 产物与复现

实验目录为 [20261028_speed_nstep_engineering（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，保留 `config.yaml`、`metrics.csv`、`summary.txt`；本地完整核查材料还有 `complete.json`、`updates.json`、`migration_proofs.json`、`qa_saved_data.py/json`、`source_740d040/`。config 固定全部输入和实际执行字节；完成锁存在时驱动拒绝重复执行。工程更新只有 loss/目标复现台账，没有性能曲线或候选权重。

在本工作树使用已有本地 Python，无新依赖安装。单测复现如下；下面给出两模块合并复现的命令，不表示本轮此前曾以此单次组合执行。

```powershell
$python = './.venv/Scripts/python.exe'
$testCode = @'
from pathlib import Path
from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
activate_runtime(Path('./.venv/pinn_tf216'))
import unittest
suite = unittest.defaultTestLoader.loadTestsFromNames([
    'optimization_control.tests.test_speed_nstep',
    'optimization_control.tests.test_frozen_speed'])
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
'@
& $python -B -X utf8 -c $testCode
```

工程复现命令如下，只能指向新的独立输出目录；`run` 仅执行上述有限内存分叉。保留现有冻结目录，禁止覆盖或重新释放 test。

```powershell
$python = './.venv/Scripts/python.exe'
$engineeringOutput = './optimization_control/experiments/20261028_speed_nstep_engineering_reproduction'
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_engineering prepare --output $engineeringOutput
& $python -B -X utf8 -m optimization_control.maddpg_wind_farm.speed_nstep_engineering run --output $engineeringOutput
```

原路径源检查点、旧实验目录及固定提交须仍可读且哈希相符。保存产物复查在当前已完成目录运行 `qa_saved_data.py`，不重复 39 次更新。未来训练草案仍为未启动状态，由主对话审阅桨距机制证据后决定；本分支不合并 master、不推送、不写共享状态入口。
