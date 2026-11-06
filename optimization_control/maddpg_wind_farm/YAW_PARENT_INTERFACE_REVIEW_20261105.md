# 偏航父接口与平均验收独立审查

2026-11-05。现有 C 父身份、8 秒 speed 决策和机舱角度转换支持开展获批的偏航工程验证。偏航方案需要落实同步决策、yaw 专用动作／回放语义和冻结父的目标计算三个合同，工程通过须有实现与验收记录。本轮审阅时另一工作树 HEAD 为 `c6a27774ec7cd34113ed7e37b47947b279fef86a`，未发现 yaw 实现文件，以下是对冻结设计与已有父代码的审查。具体反例描述直接复用旧接口或改变时序时的可观测错误，不认定尚未出现的 yaw 实现已有这些错误。[受审方案（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

**固定来源已核验。** 正式 `selection.json` 的 SHA256 为 `f244fb0d4bd899b549e8933fbbeb2c4013323a4aa799e1ab956f16d371fe65dd`，其 `lock_sha` 为 `01049ab2a4252f98e562f9c58f3ba55c0369903d616a3fefaa67339e4e204b4b`。三流 `selected` 均等于完整验证均值最小、平局取早的记录，步数为 0／0／4096，验证均值为 390.04／379.43／363.03 kW。以下快照文件内容与登记 SHA 一致，内部 purpose、arm、run、step、lock_sha 均核对通过。[正式选择锁](../experiments/20261104_forecast_speed_formal/selection.json)

| 父 | 相对正式实验根目录的推理快照 | SHA256 | 核验结果 |
|---|---|---|---|
| C0 | `jobs/C0/s0000/inference.pt` | `d3150ea9bb068b57c17db837740b9dd9303e57779583650f5a80b02b629df35b` | 与 initial 是同一选择记录，三 speed 输出末层 weight／bias 全零 |
| C1 | `jobs/C1/s0000/inference.pt` | `393461cbd1822f3e338396fa81b80edf94781dfa910d87edea111110ea9efd92` | 与 initial 是同一选择记录，三 speed 输出末层 weight／bias 全零 |
| C2 | `jobs/C2/s4096/inference.pt` | `81744bf336d4d469b68b96d8ef6af91e1c937583827434f81d131ad26490592e` | speed 非零，在线权重与对应完整状态逐张量相等 |

C2 的恢复引用 `jobs/C2/s4096/state_ref.json` SHA 为 `4214a4d874cc57376bca95857a8777207c73edef6b7da0387df12f10ea7c7ba5`，其 `state.pth` SHA 为 `bc343f4c9ab49739e4b3c2b1555cb2306b344fb17309f76d6991a4d4702d8d06`。完整状态使用 `forecast_speed_macro_boundary_v1`、purpose `formal_forecast_speed_v1`，计数为 4096 物理步、32 回合、225 次更新、512 次探索抽样、512 条宏回放。C0／C1 没有 step 0 完整恢复状态，推理可按正式初始化和快照重构；若未来 S 续训，须分别披露重建初态与 C2 完整继承。[初始化与推理加载（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [完整恢复入口（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

这批 C 的桨距父来自原项目 `20261023_progressive_random_control/pitch_run_N/segment_000/`，SHA 依次为 `28e221e6f6e74096ef74e9a9375c638823a055c38232ef4d3b5e16a5026996ea`、`0fcb0b9d474db0d04b3ac2d86c91d2f39d66bb3c025e30d911ce79b2ba445821`、`e2897be535e5c9bae27acbecc5edd57460a8a038ba28719e366ab4c904309a05`。forecaster SHA 为 `a5571a19354015c8b5997823748fafd7f0a6a355a0422d35b539e4faa3992877`。本侧交接的三份 n8 属于另一来源。C 的 `speed_reference_mode=observation_float32_v1`，本侧 n8 的参考模式为 `legacy_physical`。工程应锁 C 的原父和参考配置。当前仅 C2 含选中的新增 speed 学习修正，接通 yaw 后可称三控制通道接通，三流各通道的新增学习收益需要分别报告。[C 正式源锁](../experiments/20261104_forecast_speed_formal/lock.json) · [两侧既有来源说明](MADDPG_STAGE_HANDOFF_20261029.md)

**同步决策合同。** 现有 `Episode.step` 在宏开始选 speed z，8 秒中每秒重新调用桨距父，闭合时追加当前真实来流并计算一次下一 forecast。将它作为 yaw 的父反馈时，建议固定下列顺序，并在首回合记录调用计数和边界哈希。[父宏循环（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

1. reset 后只有 `obs_0` 和已观测 `wind_0`，共享历史长度为 1。计算一次 forecast。t=0、8、…、120 时，父在线 speed head 和 yaw head 读取同一个边界 obs 与 forecast。两者可依次调用，但中间没有环境推进、观测替换、历史追加或训练更新。yaw 输入不含本轮新 speed z 时，两次纯前向的先后不会改变动作。
2. 分别保持当次 speed 修正和 yaw 相对参考修正 8 秒。每个物理秒用该秒实际 obs 重新求父桨距和运行曲线，再组合两个已保持修正。保持的是修正，参考曲线本身继续响应闭环。每秒只有一次 `env.step`。
3. 接收 `obs_{t+1}`、奖励和 `wind_{t+1}`，历史恰追加一次。t+1=8、16、…、120 时关闭双方宏片段，计算一次共享 next forecast，并直接交给下一宏。128 时关闭 terminal，next forecast 为零、valid 为 false。完整回合有 16 次 speed 决策、16 次 yaw 决策、16 次有效 forecast、129 个已观测来流样本和 128 次执行器推进。[预测特征构造（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

以下是工程验收前必须解决的具体接口条件。表内当前行为由已有源码确认，反例可直接转为断言。

| 编号 | 当前依据与具体反例 | 可执行验收 |
|---|---|---|
| G1，yaw 权限与组合动作 | `World.env` 把 mask 写为 `[0,1,int(speed)]`。若直接复用，非零 yaw 会被 `project_action` 替换成原调度值 0，即使零头接管全部通过也看不出来 | Y 环境显式允许 yaw。同一保存观测令三 yaw z 为 `[1,0,-1]`，核对三个物理相对参考为 `[+π/180,0,−π/180]`，命令确实送到 yaw 执行器。再单独核对零修正与直接 C 等价。[工厂（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [投影（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) |
| G2，一秒只推进一次 | 父 `Episode.step` 已调用 `env.step`。若 yaw 外层再执行一次，会用两个不同观测选择所谓同边界动作，宏相位、奖励和预算均改变。若沿用旧 `command`，它只加 speed 修正，并断言 yaw／pitch 等于父 | 切分纯决策／命令组合与物理推进的职责，或在单一 episode 管理双方 held。检查物理 t、来流历史、环境查询和执行器 `_step_index` 同步。仅在边界更新两个 held，t=1…7 保持，桨距每秒反馈。[父物理推进（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [旧命令组合（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) |
| G3，冻结 C 的在线 speed 与目标 speed | C2 完整状态的 online／target speed head 共有 12 个张量不同。yaw target 若调用父的 `target=True` speed，会 bootstrap 到另一条冻结映射；只冻结参数并不能让两映射相等 | yaw online 和 target 的父反馈均使用 C 的部署在线 speed。target 只选择 yaw target head。保存父 online/target 校验和，检查两种 yaw 路径调用的父身份一致，父 Adam 与计数没有学习推进。[speed 前向（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [旧 speed bootstrap（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) |
| G4，新回放动作语义与私有恢复 | 旧宏字段 `z` 是归一化 speed 修正，执行时乘 .1 rad/s。其 shape 正好也是 3，直接沿用 schema 可让 speed 回放误当 yaw。旧 Critic 84 维的末 3 维语义也随之改变。旧类的 arm 只接受 B／C 信息模式，旧 checkpoint purpose 属于 speed | 新 yaw schema／purpose 单独登记父 C 的轻量/完整来源、forecast、±1°尺度、权限和参考模式。回放存实际施加的 yaw 宏 z、实际 m、逐秒奖励、边界 obs／forecast／history hash。必须拒绝旧 speed checkpoint、换流、换父、换 forecast、换尺度及带修改的宏记录。Y 初始回放和 Adam 独立为空，C2 的 512 条 speed 回放仅作父来源，不能搬入 yaw 数据。[旧回放字段（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [加载校验（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) |

私有回放是否足以表达父反馈，需要把同步假设写进格式。若两个决策严格同相，父 online speed 是冻结的 `f_C(obs, forecast)`，其本宏修正可在边界从这两个字段确定。Critic 的 45+36+3 维输入可以维持这个动作表示。建议额外登记父实际 speed z 作为审计字段，或在写入时核对其可重算一致性。若实现允许父宏与 yaw 宏错相，则必须纳入 held speed、剩余相位或等价状态。反例是在相同 obs／forecast 和 yaw z 下保留 speed z=+.5 或 −.5，两者物理 speed 修正相差 .1 rad/s。仅存 yaw z 无法区分。历史 hash 用于身份审计，无法还原完整历史；36 维 forecast 压缩也没有给出完整 Markov 性证明，报告应保留这一信息压缩限制。[speed offset 及持有（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [宏接续检查（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

冻结父是固定映射及来源，yaw 改变下一秒功率、有效风速和实际状态后，父桨距和后续 speed 决策应读取这个新 obs。检验非零 yaw 时，比较 `parent.act(obs_Y)` 与记录的父输出；预期它随观测反馈。只做零 yaw 等价不足以发现播放旧 C 轨迹的问题。

**角度与 SI 合同。** 源码使用 `gamma_actual=wrap(heading−theta)`，yaw 动作表示相对来流的参考角，环境再求 `heading+wrap(theta+gamma_ref−heading)`，随后执行器按一阶动态和 .005 rad/s 限速推进。来流读取在执行器推进之后，因此第 t 秒动作使用已观测 theta_t，响应的 PINN 使用 theta_{t+1} 与实际 heading_{t+1}。按这条顺序解释瞬态符号，不能要求执行器立刻达到命令参考。[实际角度和查询（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [命令到机舱（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [执行器一阶与限速（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

已用这些纯函数和公式核验下列数值，均没有调用模型或环境推进。

| 样例 | 预期与反例 |
|---|---|
| head z=±1 的单位 | δ=±.01745329252 rad。yaw 动作边界 ±.25 rad 时，归一化增量为 ±.06981317008。直接把 z=1 填入归一化 yaw 会变为 .25 rad，即 14.3239° |
| 固定风向 0，heading 0，参考 +1° | tau=5 s、dt=1 s，首秒 heading 为 +.00316374519 rad，未达 .005 限速；−1° 对称。若每秒将参考设为当前实际 gamma+1°，8 秒会累计约 .02531 rad，即 1.45°，与保持同一个相对参考不同 |
| 跨 2π 正向 | heading=2π−.01，theta=.01，δ=+1°，最短参考差 +.03745329252 rad，首秒 heading 增加 .005，保持同秒风向时实际 gamma 约 −.015 rad |
| 跨 2π 反向 | heading=.01，theta=2π−.01，δ=−1°，最短参考差 −.03745329252 rad，首秒 heading 减少 .005，实际 gamma 约 +.015 rad |
| 三机独立标记 | 默认物理输入 `[9,2π−.01,.08,.01,−.02,.03,.04,.05,.06,.7,.8,.9]` 依次为来流三量、三 yaw、三 pitch、三 speed。团队输入应为 `[9,−.01,.08,.01,.04,.7,−.02,.05,.8,.03,.06,.9]`，仍为 rad／rad/s。三机 yaw 与风向 wrap，pitch 和 speed 不做角度 wrap |
| 宏奖励 | 每机逐秒奖励全为 1 时，m=1／3／8 的 return 为 1／2.9701／7.72553055721，discount 为 .99／.970299／.922744694428。terminal 的 bootstrap 为零，m=3 的非终止片段应被现有契约拒绝 |

三机重排由适配器的命名物理字段先组合为 grouped 12 输入，再由 `team_inputs` 重排为 interleaved，模型内部完成该版本的编码。直接传一份已经交错的数组会二次重排，三机独立标记可定位。域检查在 PINN 调用前拒绝无效输入，工程应记录 case、物理步及具体字段。±1°是参考修正界限，实际 gamma 还受风向与执行器动态影响。分别核验命令幅值、heading 速率、实际 gamma 和模型圆周风向域，避免只查 yaw head 输出。[物理命名输入（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [SI 重排与圆周域（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

**恢复与最小工程验收。** 方案选择完整 128 步边界恢复，允许下一回合重新 reset，并应明确拒绝物理步 3／8／127 的存档请求。旧 `MacroSpeed.state/load` 会检查完整回合、回放插入数、末端历史 hash、Adam step 和 RNG。yaw 新格式还需核对双方边界相位、父角色和来源。terminal 的 `next_obs` 是终端响应，不能用下一回合 reset obs 替换；`next_forecast_valid=false`，下回合历史从新 wind_0 开始，pending、held 和执行器队列重置。旧执行器 reset 已清空延迟队列与 active reference，组合控制器也要清空自己的状态。[完整边界状态（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [执行器 reset（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

可按原工程预算把检查落实为下列记录。当前这份只读审查不代替这些动态验收。

- 三父 × 既有平稳／慢变／阵风各一场，直接 C 与零 yaw 接管逐秒比对输入、执行总命令、heading、实际量、功率及完整回合指标。共 18 回合，2,322 行含 reset。保留动作 2e−6、实际量 1e−6 和功率／RMSE 1 W 原容差，额外比较父 held speed 与 forecast 历史哈希。
- 零 yaw 检查 online 和 target 两条路径。纯输入检查非零 ±1°、三机独立 yaw、0/2π wrap、双时钟边界、terminal 禁止再决策及跨回合队列清空。旧 speed 回放错格式、断开 next_obs／next_forecast／history、换父或换尺度时应失败。
- 一流 mock 按 4 个完整回合后进行一次工程联合更新，保存后连续与新进程各跑下一回合和一次更新。比较实际抽样索引、yaw 回放、网络／target、Adam 矩、RNG、计数、forecast 和执行器完整时序。总共 6 回合即 774 行、3 次工程更新，均标明工程用途。两项合计 3,096 行，上限 4,096。正式训练的授权和预算仍由主对话另行控制。

**三通道平均验收表的最小定义。** 未来一次独立测试释放前，固定每流 selected 身份、三类风的 case 清单、目标与初态、共同 PI 配置及所有控制器的执行器。设完整回合 `R[s,c]=sqrt(mean_t((P[s,c,t]−target[c])²))`。每族 `M[f]=(1/3)Σ_s mean_{c∈f} R[s,c]`，公共 PI 为 `I[f]=mean_{c∈f} R[PI,c]`。主判定仅要求平稳、慢变、阵风分别满足 `M[f]<I[f]`。数值检查覆盖全部场景，终止早退或失败场景保留并报告，不能删掉后继续判通过。

| 表项 | 最小报告内容 | 用途 |
|---|---|---|
| 三族主表，每族一行 | case 数、3 流等权 selected 均值、公共 PI 均值、配对均值差、严格小于判定 | 用户平均目标，三行均通过才通过 |
| 逐流与离散 | 每流每族均值、三流 SD／范围、最差配对差和 case 身份 | 描述差异，逐流或逐 case 胜负不增加硬门槛 |
| selected 与 final | 每流预先固定步数／SHA、是否 initial、同风库的 final−selected | 区分部署角色与续训退化 |
| 低风高目标压力 | 独立分组均值、PI 差、最差案例，附含压力总体及 pooled | 保留压力范围及计权口径 |
| 新增 yaw 作用 | 同权重在线运行的 yaw 正常／关闭 yaw，以及固定 C 的差值、yaw 实际运动与饱和 | 解释新增通道贡献。Y−S 是完整训练方案对照，含可训练模块及继承状态差异 |
| 工程与模型边界 | 物理约束、三机通道接通、来源身份，合成 PINN 的 yaw 响应限制 | 接口正确性与平均功率指标各自给出结论 |

400／500 kW、逐 case 获胜率、1% 收益和统计区间可作为原有描述列。用户本轮平均目标没有增加这些门槛。C0／C1 选中的是零 speed 修正，当前 yaw 阶段只获批工程实现与验证。零头接管通过可证明接通与恢复，新增 speed／yaw 学习收益仍需各自的学习结果支持。

本轮实际只读核对文件、SHA、PyTorch 保存张量和上述纯算术样例，PINN／mock 输入行、环境推进、优化器更新、新风生成均为 0。写入仅本报告，低于 16 MiB。受审核心文件 SHA 为方案 `6a38103b3e4dc1d84558e71e0f780adaccc2b56c05e87e5d188630127f6ea6ab`，`forecast_speed_macro.py` 为 `283b508170031b50aaa769ac62497327391589c00dc169128ee4b5f6e52016be`，`forecast_speed_training.py` 为 `c0be99ace1f4d99cf120896027be21d830c7bc72393c259158e10802eaed5192`。新增 yaw 实现的动态结果留待工程侧验收。
