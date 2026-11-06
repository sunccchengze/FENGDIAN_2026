# speed n-step 独立工程审查（2026-10-29）

**审查结论：在下述被审范围内，未发现阻断性的实现或实验公平性问题。**
`blocking_issues: []`；`review_status: no_blocking_issues_in_reviewed_scope`。
这允许按主对话新授权继续一次49152步的可证伪speed n1/n8实验，不证明性能有效，也不等于未完成的新训练入口已获端到端验证。

## 身份与范围

- 被审工作树：`.`，分支`codex/speed-nstep-engineering-20261028`。
- 被审提交：`c3e9cc07b004ae5fc3f2033d00a25f756c0edb03`。
- 被审实现、测试和历史草案的工作树字节均与该提交Git blob相等，审查前后未变；原工作区与对方工作树只读。
- 最小复现：真实流0父回放的一次原n1/适配n1/n8目标挂钩对比，加三个针对性合成用例；实际4次内存update全部丢弃。正式训练0、环境step0、代理模型预测0，不写候选权重。
- 证据：[probe.json](../experiments/20261029_speed_nstep_independent_review/probe.json)、[复现脚本（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、[单测记录](../experiments/20261029_speed_nstep_independent_review/unittest.txt)。

| 文件（相对被审工作树） | SHA256 |
|---|---|
| optimization_control/maddpg_wind_farm/nstep_replay_core.py | 20f979700fcbe2f2aa479148fb1c12e2095431aa8da199fa47c704f79e44e8da |
| optimization_control/maddpg_wind_farm/speed_nstep_algorithm.py | a85b3f2a134c64a8403bfdf556f01eced1c81f8b12b635f724df9303338d5274 |
| optimization_control/maddpg_wind_farm/speed_nstep_engineering.py | a620c11c1ee60978996c13d82413a1fbb424c48a962eca8b8a1e48dc4dbd6e18 |
| optimization_control/maddpg_wind_farm/frozen_speed_algorithm.py | eab8d8091174b268a5d37d97a1dfcc5b9f35224edc204e27cfc528b20a7db0f8 |
| optimization_control/maddpg_wind_farm/algorithm.py | ee89948d8d98aa33b9b4ee20675ccc588c2005a6f8bec01b41cd555ba271febb |
| optimization_control/tests/test_speed_nstep.py | 8198dee6330bb3060c98c11682ae557e370b9b3c4e4a78a32ca420387b7c65d7 |
| optimization_control/maddpg_wind_farm/SPEED_NSTEP_DRAFT.md | c8add13d326c8e97edfae4e29bd45b279ecc5b006f42e0ae9322c36b9f104396 |
| optimization_control/maddpg_wind_farm/SPEED_NSTEP_ENGINEERING_RESULTS.md | 50fd36080de6bf7fd98efd9e5696b7d39d2de4f0a69eca380a4f26b84541cd23 |

## 核查结果

1. **无同名定义覆盖。** 对上述Python文件递归检查每个module/class/function作用域的定义名称，重复为0。父子类有意重写不作重复覆盖。`FrozenSpeedNStepMADDPG`没有另写update，使用原`FrozenSpeedMADDPG.update`，n1的td_target直接走原公式。
2. **回放时序/m/done正确。** `speed_nstep_algorithm.py:18-127`先以独立累计插入数、horizon及来源证据校验整个保留ring；逐步检查共同reward、执行总动作与next_obs命令、三机时钟、done及非终止连续边。单调sequence区分回卷后的最新尾和最旧槽。真实done停止，缺未来尾用实际m bootstrap，未筛掉短尾锚点。新增三机done不一致会拒绝。最小复现通过回卷/覆盖、新写入、终止和缺尾用例。
3. **未来Critic输入为总动作，使用当前radius。** 原update在实际s_(t+m)调用target父reference加target speed头，集中Critic接收45维obs+9维联合总动作；不是原始head输出，也不取历史窗口radius。真实流0挂钩复现通过，合成用例将online/target头设为不同值后也通过。radius锁存在agent.config，正式入口仍须在每次执行transition及其update使用同一锁存值。
4. **父/target/优化器/RNG路径一致。** 原父online Actor冻结；target保留继承滞后并沿原tau路径更新。原Critic/target及Critic Adam、回放和RNG继承，新speed头使用同seed且末层零、head Adam空；父Actor Adam不再参与更新。真实流0n1的loss、网络、target、head/Critic Adam和采样锚点与原实现精确相等；n1/n8抽到相同锚点。
5. **reward仅缩放一次。** 序列直接累计回放中已含scale100的reward，`gamma^m`只作用于末端bootstrap。已有工程产物的奖励重构和本次scaled-reward/terminal算例一致。未发现额外乘100或终止后bootstrap路径。
6. **新恢复格式与旧v4分离。** 新格式显式保存n/tail_rule、sequence/epoch/horizon/插入数、六组网络、head/Critic Adam及RNG；旧v4仍走旧loader。迁移计数由parent lineage/steps或v4 parent累计+step推导，而非保留size。已有工程记录覆盖恢复下一update；本次未重跑全部39次工程更新。
7. **草案配对与隔离设计成立。** 两臂固定相同原三父，不换用pitch新n8候选，不用旧speed终点起步；各8192步、每job3841次更新、相同头seed/天气/初态/探索和回放抽样资格，仅TD目标不同。validation选模含initial；六job/检查点/审计锁冻结后才释放新test。固定父单列，不冒充同预算n1臂。

## 计数核对

c3e9cc0的工程驱动每流执行9次三radius原n1/适配n1/n8更新、2次父副本恢复对照、2次旧final追加回放恢复对照，即13次，三流39次，源码计数自洽，未发现计数伪造证据。
保存的updates.json实际有30行：27行radius探针和3行追加/恢复分组记录，**不是39条逐调用记录**。其余恢复调用由源码中的成对执行/assert、metrics和完成锁支撑，不能把30行称作39份独立逐调用轨迹。
本次逐一复核27行中的同流同update锚点，以及9对legacy n1/适配n1的目标和loss相等；完成锁中的文件摘要均匹配。
本次新增4次内存update另有动态计数，不计入对方原39次、不计入正式49152步。

## 非阻断风险与未覆盖内容

- 行为策略多步奖励有已知off-policy偏差；这是候选假设的风险，不作为自动阻断可证伪实验的理由。pitch selected门槛通过、终点不稳及混合机制证据原样保留，不要求先证明性能有效才做speed实验。
- 本次审查时，2026-10-29的新SPEED_NSTEP_PROTOCOL.md和configs/speed_nstep.yaml尚未提交，正式训练/审计入口未进入被审c3e9cc0。**未审其最终源码**，因此不声称已验证新入口的逐回合保存、2048步新进程恢复、actual-m统计、同噪声/radius锁存、namespace碰撞、验证选模或test释放锁的端到端行为；应按新协议完成自身针对测试与零头gate，并记录实际执行源码SHA。
- 新loader在`speed_nstep_algorithm.py:202-203`用zip恢复优化器，未显式核对列表长度等于3。标准save始终写3项且实验有SHA身份锁，当前没有缺项产物证据，故不阻断本实验。后续格式加固可在加载前拒绝长度不为3的head/Critic optimizer列表，避免人为构造但字段存在的短列表被静默部分恢复；不要为此改变算法或重置有效状态。
- 对满ring的总插入数，单凭内容无法区分相差整圈的计数；严格包装器依赖可信的lineage/step及来源SHA。这是显式信任边界，已有测试拒绝计数证据不一致，未发现当前三父推导错误。
- 本审查不验证speed性能、物理精度、yaw可控性或多通道因果收益；没有新增独立环境评估。

## 启动与版本边界

主对话已在读取dd6f400和c3e9cc0后明确接受反证，批准一次2×3×8192=49152步对照。旧SPEED_NSTEP_DRAFT中“未获准/旧条件未证实”的文字是历史状态，不能据此否定这次新授权。
对方可据本报告在**上述核心文件SHA保持一致**且新入口自身契约测试/gate通过后执行本次授权；本报告不是对任意后续源码的通用批准。若修改核心实现，请保留旧冻结来源、复核受影响项并记录新身份；无需因既有off-policy风险重复请示。
报告一写完即完整可读，不必等待本侧阶段索引或Git提交。审查者未修改对方代码、状态、模型或checkpoint，也未发送跨对话消息。
