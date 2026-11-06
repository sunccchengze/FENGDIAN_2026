# 冻结父策略映射与独立转速修正头（2026-10-28）

接管功能已通过严格一致性检查；候选在两流选中非初始策略，训练终点三流均优于同预算pitch续训，但完整稳定性仅2/3通过，selected收益未覆盖三流，不能认定可重复的新增学习收益。所有失败与选模结果保留。

本报告承接[动作约束实验收尾及其原产物](ANCHOR_CLOSEOUT_RESULTS.md)，执行用户批准的唯一候选：完整冻结父线上Actor映射，只新增并训练有界speed头和Critic。只扩大转速权限，偏航仍由后台调度跟踪，未修改PINN。实验协议、门槛和父检查点在运行前冻结，见[FROZEN_SPEED_PROTOCOL.md](FROZEN_SPEED_PROTOCOL.md)及[配置](configs/frozen_speed.yaml)。

## 来源与执行边界

工作树为`.`，分支`codex/frozen-parent-speed-20261027`，基点`a49eb90d942fc50f68cedb3d00b2b53a3a80da02`。原工作区`.`的分支、PROJECT_STATUS.md、TASKFLOW.md、README.md、父权重和模型均只读；不合并master、不推送，不向队友发消息。

最终产物根目录为[20261028_frozen_speed_checked](../experiments/20261028_frozen_speed_checked/config.yaml)。首目录`20261028_frozen_speed`只完成接管工程检查，smoke和正式训练均0步；审查中补齐v4通用`policy(actor, obs)`的完整动作分派后，保留首目录、原执行字节快照和旧摘要，重新冻结最终目录。它不是第二个学习候选。

父检查点均来自原`20261023_progressive_random_control/pitch_run_i/segment_000`，不是在本轮独立测试上挑选。继承线上/目标Actor、Critic/目标Critic、Critic Adam、回放、NumPy/replay/Torch RNG和更新计数；两臂可训练Actor或新头Adam moments均从空开始。

| 流 | 父文件 | SHA256 | 继承回放行数 | 父累计环境步 |
|---|---|---|---:|---:|
| 0 | step_00016384.pth | `28e221e6f6e74096ef74e9a9375c638823a055c38232ef4d3b5e16a5026996ea` | 32768 | 32768 |
| 1 | step_00012288.pth | `0fcb0b9d474db0d04b3ac2d86c91d2f39d66bb3c025e30d911ce79b2ba445821` | 28672 | 28672 |
| 2 | step_00008192.pth | `e2897be535e5c9bae27acbecc5edd57460a8a038ba28719e366ab4c904309a05` | 24576 | 24576 |

三流父训练历史和起点权重不同，因此主要判断均在各流内部配对，新增预算均为8192；不能把三流绝对误差差异归因于本轮随机性，汇总的样本SD也不是置信区间或显著性证据。

模型SHA256为`7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`，来源是合成标签联调副本；所有结论均限于该代理中的软件实验，没有物理精度或高保真验证证据。

## 接管工程检查

新模式`observation_float32_v1`统一策略、环境投影和P/PI的speed参考：从同一个float32有效风速观测按相同运算顺序重建参考。默认仍为`legacy_physical`，旧模式代码路径和旧实验保持。首轮发现的2 W量级数值差没有被用来解释几十kW训练退化，也没有放宽1 W功率容差。

| 流 | offline online/target动作最大差 | 零头闭环动作差 | 实际状态差 | 功率最大差/RMSE差 W | 原环境legacy逐步复现 | 旧模式→新模式最大功率差 W |
|---|---:|---:|---:|---:|---|---:|
| 0 | 0 | 0 | 0 | 0 / 0 | 精确 | 2.0 |
| 1 | 0 | 0 | 0 | 0 / 0 | 精确 | 2.5 |
| 2 | 0 | 0 | 0 | 0 / 0 | 精确 | 2.5 |

offline检查覆盖各父策略完整回放的obs及next_obs、线上及目标Actor；闭环覆盖6个validation case各128步。动作容差2e-6、实际状态1e-6、功率max和RMSE各1 W，三流全过。原回放`actions == next_obs[:,:,5:8]`，仍表示执行器的总绝对归一化目标；未改写旧样本。旧后台调度和新float32参考的最大归一化差为2.980232e-7，约9.94e-8 rad/s。

## 学习方案与固定预算

候选每机独立15→32→1 ReLU/Tanh头，末层权重/偏置置0。完整父线上Actor逐位冻结，父target继承原滞后状态并按tau=.01跟随冻结线上Actor；新target头正常Polyak更新。Critic仍接收45维联合观测与9维联合总动作，Actor i梯度只进入本机speed头，其他机使用同批回放总动作。目标动作使用当步训练范围且不加探索噪声。

speed修正物理范围前4096步由±.02扩大至±.10 rad/s，验证/选模/测试始终使用最终范围。baseline只保留pitch学习权限，按同预算续训。另保留原冻结父策略，以及候选selected/final的zero-speed闭环消融。冻结映射与新增权限共同构成方案差异，不能把候选与可训练baseline的全部差值归因于转速维数。

| 参数 | 固定值 |
|---|---|
| 主seed、训练流 | 42；三条派生流 |
| 正式预算 | 2臂 × 3流 × 8192 = 49152条新增状态转移 |
| smoke | 只用run0，两臂各1024，共2048步；正式从原父重启 |
| warmup / update / eval | 512步 / 每2步 / 每2048步 |
| 每job新增更新 | 3841次；smoke每job257次 |
| Actor或头 / Critic LR | 1e-4 / 1e-3 |
| gamma / tau / batch / capacity | .99 / .01 / 64 / 32768 |
| baseline探索 | 仅pitch白噪声std=.03 |
| 候选探索 | 仅speed raw白噪声std=.15 |
| 风况namespace | train8400000，validation8510000，test8620000，已知压力8639000，smoke8450000 |

两臂风况、目标、初态和完整3×3噪声抽样流配对，再按各自权限使用噪声。旧模板`base_config.training`中的total_steps、warmup等字段不驱动本实验；本轮`protocol`和`frozen_speed_training.py`决定实际执行，交付另附`resolved_execution.json`避免混淆。

run0两臂均在2048步由worker保存退出，再由新进程恢复；审计各做两个128步内存分叉，并对齐正式恢复后的实际动作。续做时此前训练进程已不存在，baseline1从保留的4096步状态继续，新segment保留。有效训练状态链仍各8192步；无法从持久产物重建前一进程是否存在未保存后又丢弃的工作，不能把49152宣称为主机所有尝试执行步数的精确计数。该说明见`continuation_record.json`。

冻结验收分别为：接管按上述严格容差；稳定性要求final/selected<=1.25，final mean/worst相对父及同预算baseline均<=1.05，三流全过；学习收益要求selected_step>0，selected和final相对同预算baseline分别三流严格改善、总体至少1%。5%工程不劣不等于性能改善，1%为效应尺度，不是统计显著性。原mean<=400、worst<=500 kW单列报告，不替代这些判定。


## 验证集结果

单位kW，均值为6个case RMSE的平均，worst为最差case RMSE。

| 流 | 父策略=initial | baseline selected步/均值 | baseline final | speed selected步/均值 | speed final | speed final worst | speed final/selected |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 334.02 | 0 / 334.02 | 421.57 | 0 / 334.02 | 356.10 | 487.57 | 1.0661 |
| 1 | 316.69 | 0 / 316.69 | 381.40 | 4096 / 308.27 | 313.06 | 446.72 | 1.0155 |
| 2 | 296.20 | 4096 / 295.86 | 321.18 | 2048 / 283.25 | 301.34 | 412.49 | 1.0638 |

候选selected步为0/4096/2048，baseline为0/0/4096。候选只有流1/2出现选中的学习改善；流0 selected=initial，不能计作新增学习收益。流2在6144步升至313.37 kW、8192步回落到301.34，仍未保住2048步的283.25；因此完整曲线比只看终点更能显示退化。

| 原冻结判据 | baseline | 冻结父映射+speed |
|---|---:|---:|
| final/selected<=1.25 | 2/3 | 3/3 |
| final mean/worst相对父<=1.05 | 0/3 | 2/3 |
| final mean/worst相对配对baseline<=1.05 | 3/3，自身参照 | 3/3 |
| 完整稳定性 | 0/3，失败 | 2/3，整体失败 |
| selected_step>0且优于initial | 1/3 | 2/3 |
| selected mean<=400且worst<=500 kW | 3/3 | 3/3 |
| final mean<=400且worst<=500 kW | 1/3 | 3/3 |

候选三流final均比配对baseline好，但流0相对父均值恶化6.61%，超过5%不劣容差，完整稳定性仍失败。流1 final相对父改善1.15%；流2 final相对父恶化1.73%，虽在5%工程容差内，也不是性能改善。候选全部通过400/500精度条件仍不能宣布三流学习成功。

候选selected验证均值308.51 kW，对照315.52 kW，总体相对改善2.22%，配对严格改善2/3。
候选final验证均值323.50 kW，对照374.72 kW，总体相对改善13.67%，配对严格改善3/3。

selected未三流改善且流0为initial，原可重复学习收益验收失败。final总体优势主要不能脱离基线本身退化来解释；未追加训练、替换父策略、换阈值或开放yaw。

## 冻结后的独立测试

选择锁、bank、配置身份固定后才释放测试。共20 case：18个新routine（stationary/ramp/gust，各3个风况/目标、2个初始pitch），2个已知7.6 m/s、4.4 MW压力回归。后者不是新独立样本，没有可达性证明。总计660条指标（594常规、66压力）、84480行轨迹；所有RMSE由保存轨迹复算，最大差0 W。没有用测试改选模、父策略或参数。

先对每流各case RMSE取平均，再汇总三流均值±样本SD，单位kW；公共方案只评一次，无跨训练流SD。

| 控制方案 | 新routine均值±SD | 已知压力均值±SD |
|---|---:|---:|
| 冻结父=initial | 365.60 ± 18.30 | 1607.95 ± 143.00 |
| 仅pitch续训 selected | 366.01 ± 17.61 | 1603.32 ± 150.69 |
| 仅pitch续训 final | 409.72 ± 27.53 | 1587.18 ± 157.17 |
| 冻结父+speed selected | 355.08 ± 25.55 | 1647.88 ± 113.61 |
| 冻结父+speed final | 367.43 ± 29.77 | 1712.00 ± 174.70 |
| 固定pitch＋后台调度 | 981.04 | 1812.34 |
| P组合 | 491.38 | 1383.30 |
| PI组合 | 436.07 | 1383.30 |

P/PI为“pitch反馈＋yaw/speed调度”的统一完整控制方案；与MADDPG的比较是完整方案比较，不单独证明新增speed的贡献。已知压力中P与PI指标相同，图中横线重合。候选在routine优于本轮P/PI，在压力中则更差，不能给出全风况优胜结论。

| 流 | routine父 | baseline selected | baseline final | speed selected | speed final |
|---|---:|---:|---:|---:|---:|
| 0 | 380.15 | 380.15 | 434.10 | 380.15 | 400.60 |
| 1 | 371.60 | 371.60 | 415.20 | 356.03 | 358.66 |
| 2 | 345.05 | 346.28 | 379.86 | 329.08 | 343.03 |

routine selected总体相对同预算baseline改善2.98%，相对冻结父变化-2.88%。
routine final总体相对同预算baseline改善10.32%，相对冻结父变化+0.50%。

routine selected只有流1/2严格优于配对baseline，流0与initial完全相同；final三流优于配对baseline，但仅2/3优于冻结父。压力selected和final三流均劣于冻结父，final也三流均劣于配对baseline。压力终点均值1712.00 kW对baseline1587.18、父1607.95，保留该退化结果，不重新抽风况。

| routine精度报告（mean<=400且worst<=500 kW） | initial | selected | final |
|---|---:|---:|---:|
| baseline | 0/3 | 0/3 | 0/3 |
| speed | 0/3 | 0/3 | 0/3 |

该精度表是独立测试的附加描述，不是重新定义验证集验收。压力结果单列，未与routine混合以改变400/500统计。

## 通道诊断与三层结论

zero_selected/zero_final在三流、全部20 case的15360行轨迹中，全部数值字段逐位等于冻结父轨迹，包括目标、初态、来流、总动作、heading、gamma、pitch、speed、各机功率和有效风速。归零后精确回到父策略闭环，表明冻结映射及组合路径保持；非零修正会改变下一步观测，从而改变冻结pitch映射的输出轨迹。

下表是routine实际闭环相对冻结父的差异；pitch/speed为三机、18 case合并RMS，raw接近边界比例来自保存步骤1..127重建观测后的head输出，阈值为abs(raw)>=.95。这是诊断统计，不是新的验收门槛。重建完整动作与下一步保存命令的最大差小于1e-6，满足原2e-6动作容差。

| 流/策略 | 实际pitch轨迹差 RMS deg | 实际speed轨迹差 RMS rad/s | raw均值 | raw接近边界比例 |
|---|---:|---:|---:|---:|
| 0 / selected | 0.000 | 0.00000 | 0.000 | 0.00% |
| 0 / final | 1.303 | 0.04765 | -0.425 | 2.87% |
| 1 / selected | 0.474 | 0.05870 | -0.361 | 0.00% |
| 1 / final | 0.492 | 0.07449 | -0.659 | 36.47% |
| 2 / selected | 3.376 | 0.07955 | -0.738 | 0.00% |
| 2 / final | 1.289 | 0.07188 | -0.451 | 33.33% |

父线上权重未漂移，但流2 selected的pitch闭环轨迹已与父有3.376度RMS差异，说明冻结权重不保证控制轨迹不变。流1/2 final的raw接近边界比例增加，speed修正幅度和pitch状态反馈共同变化；总speed指令饱和比例（含压力）为0.052%/0%/3.281%，不能把某一个饱和数直接认定为唯一退化原因。流1 final在无总speed饱和时也比selected退化，已知压力中三流均变差，进一步说明应评价学习目标和闭环结果。

已有局部模型诊断支持speed具有可利用的代理内作用，本轮流1/2 selected相对父的闭环改善也提供软件证据；它未证明物理响应可信。yaw仍存在响应幅度压缩和方向不一致的前置问题，详见复核清单。本轮不改模型、不训练yaw。

| 控制权限阶段 | 功能/初始化接管 | 接管后稳定 | 学习收益 |
|---|---|---|---|
| 仅pitch父策略 | 固定三份已存在策略，原能力作为配对起点 | 本轮同预算续训0/3过完整稳定性 | 另一个pitch任务负责跨风况改进，本轮不改其源码 |
| pitch＋speed | 三流严格接管通过；最终zero消融完整复现父轨迹 | 候选2/3，整体未通过 | 两流有非initial selected；三流可重复收益未通过 |
| pitch＋speed＋yaw | 旧三通道动作约束实验已收尾，见先前报告 | 旧anchor完整验收失败；本轮未追加yaw训练 | 不能宣称成功，也不能据此认定无法实现 |

下一步仍应停留在speed学习稳定性和模型适用边界；本轮授权的唯一候选已完成，不自动追加预算或第二个结构改动。


## 检查点、执行器和恢复审计

37个相关单元测试通过：新v4与数值契约8个、旧逐通道7个、随机来流参考8个、MADDPG环境/接口/算法14个；重复运行不重复计数，记录见产物根目录`tests_passed.json`。本轮没有改CI、环境文件、依赖或系统设置。

正式审计覆盖三组配对起点、18个逻辑initial/selected/final保存加载槽位，以及六份终点回放共196608条保留转移。它们包含继承旧样本，不能称为新增196608步。核对了总动作、next command、奖励、有限时域终止、heading/pitch/speed速率、speed动态包络及192个风况/目标/初态设计。候选父线上Actor无梯度且逐位不变，父target与3841次原tau迭代路径精确一致。

两臂run0的两次128步恢复分叉在动作、奖励、loss、噪声RNG和全部网络上精确一致，且与正式新进程恢复后的实际动作相同。smoke另有两个128步分叉；768条审计环境步均只在内存副本执行后丢弃，不写回正式或smoke检查点。保存加载后的下一次更新也只在副本执行。

偏航执行器始终控制机舱heading，失配角由`wrap(heading - direction)`计算；未把失配角直接当成有速率限制的heading。P/PI和所有策略使用同一执行器、物理边界、风况、目标及新speed参考模式。图中heading相对第一条绘制风向连续展开，gamma单独显示，避免0/360度图轴歧义。

全部测试逐步核对bank经环境float32转换后的来流、目标和初态，包含第一步在内的最大heading/pitch/speed变化率分别为0.0018351 rad/s、0.00872665 rad/s、0.0543808 rad/s²，均在原限制内。gamma关系误差0，按环境float32求和的总功率误差0；若改用Python float64重加三机功率，最多有0.5 W求和舍入差，该统计另存于交付审计，不与1 W接管检查混用。

五份PNG均已逐图视觉检查：标题、单位、图例、selected星标、压力分栏及连续heading轴完整，三份实际控制图包含功率、heading、gamma、pitch、speed五行；对应PDF为同一图形导出。

交付QA核对26个保护源、73个冻结执行文件的SHA256，检查9个Python文件语法、5个文档链接及表格/代码块格式；五份PDF均为单页，PNG与图清单摘要匹配。`qa_delivery.json`及其一次性脚本保留复现结果，辅助通道审计代码另有独立SHA，不改写训练冻结清单。

## 交付与复现

所有大产物均留在`./optimization_control/experiments/20261028_frozen_speed_checked/`，不放入Git。源码、测试、协议、报告及两个实验目录的config.yaml/metrics.csv/summary.txt形成本地原子提交；本轮不合并master、不推送。

- `checkpoint_manifest.csv`：30份正式检查点的版本、步数、更新数、角色和SHA256；保留全部initial、中间、selected、final。
- `normalization_baseline.json`、`normalization_speed.json`：15维固定物理缩放及各自权限；不使用运行均值方差。
- `selection.json`、`test/release.json`、`test/complete.json`：配置、数据bank、检查点与测试释放绑定。
- `handover.json`、`smoke/verification.json`、`core_verification.json`、`verification.json`、`delivery_verification.json`：接管、最小运行、恢复、轨迹复算及交付审计。
- `history.csv`、`test/metrics.csv`、`test/aggregate.csv`、`test/trajectories.csv`、`test/corrections.csv`、`test/channel_diagnostics.csv`：完整曲线、逐case误差和控制轨迹。
- `figures/paired_validation.png/.pdf`、`paired_test.png/.pdf`、`actual_controls_0/1/2.png/.pdf`：五组图，各有PNG/PDF；选定的gust case在绘图前固定，不按效果挑图。
- `resolved_execution.json`、`continuation_record.json`、`supplementary_code.json`、`output_manifest.csv`、`delivery_files.csv`、`git_delivery.json`：执行参数、续做说明、辅助审计代码和交付来源。

`summary.txt`是便于Git审阅的压缩结果索引；验证器原样展开记录保存在`summary_full.json`，索引附其SHA256。该整理只去掉重复嵌入的配置和回放审计详情，所有原记录仍在；再次运行verify会重建展开摘要，随后delivery命令可重新整理。

候选是显式version4，使用`frozen_speed_algorithm.load_policy(path)`或`FrozenSpeedMADDPG.load(path)`。旧v1/v2/v3加载器拒绝v4；不能把它当旧Actor文件直接加载。环境必须使用检查点metadata里的`config.environment`，其中包括`observation_float32_v1`，并使用对应归一化JSON。`agent.act(obs, zero_speed=True)`恢复冻结父动作组合，用于消融，不是重新训练。

在本工作树运行，Python使用原本地`.venv/Scripts/python.exe`；驱动会激活已存在的`pinn_tf216`运行库，无新安装。现有冻结目录可执行`verify`复查保存结果，`test`遇到完成锁只核对摘要并返回；训练命令遇到selection/test会拒绝继续。

完整重现必须使用新的空输出路径，下面仅是复现说明，本轮没有再执行第二套训练。依次执行模块`optimization_control.maddpg_wind_farm.frozen_speed_training`的命令，所有命令传同一个`--output <fresh_output>`：

```text
prepare
gate
smoke
worker --arm baseline --run-id 0 --stop-after 2048
worker --arm speed --run-id 0 --stop-after 2048
run
verify
test
verify
figures
```

最后执行`python -B -X utf8 -m optimization_control.maddpg_wind_farm.frozen_speed_delivery --output <fresh_output>`做不调用代理的保存产物审计。绘图进程将MPLCONFIGDIR设为`<fresh_output>/plot_cache`，与一次创建的figures目录分开；五组图与PDF均需视觉检查。原父、模型和本地路径必须存在且SHA匹配；新复现会重新冻结实际执行字节，不应改写现有冻结config或测试集以迁就路径。

本轮停留在转速阶段。偏航的模型局部响应限制已整理成[供用户转交PINN组的复核清单](PINN_YAW_RESPONSE_QUESTIONS.md)，所需CSV/JSON格式、单位、模型SHA和验证样本位置都已写明，未向队友发送。现有yaw响应差异支持暂缓新yaw训练，不等于认定三通道控制无法实现。
