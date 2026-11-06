# 冻结history17的新独立测试协议（2026-10-29）

用户接受6e91ccc的开发结果，批准本轮独立测试。计划从开发预测/决策诊断改为冻结候选验收：不再调预测器/网格/H/频率，不重新拟合或选择父，不做MADDPG蒸馏/RL/yaw。本轮结论只限当前合成标签PINN的软件实验。旧863.95秒计时异常继续保留，本轮不为改计时重跑历史。

目录沿现有职责：history_independent_test.py负责新测试生成/冻结、只增加计时的数值等价入口、预算/磁盘约束及逐回合运行；history_independent_report.py负责保存数据核算、统计和最多三组Python图；tests/test_history_independent_test.py保存计时入口等价性测试；configs/history_independent_test.yaml固定本轮身份/设计/门槛。experiments/20261029_history_independent_test保存config.yaml/metrics.csv/summary.txt；新风bank、压缩逐步外部/必要内部误差、时钟证据和审计按现行规则本地保存。不复制旧工作树/模型/回放，不新增.pth，不改旧文件、共享状态、master或远程。

## 候选、独立性与释放顺序

依赖只读绝对路径+SHA：6e91ccc对应candidate_manifest、forecast_model（SHA a5571a19354015c8b5997823748fafd7f0a6a355a0422d35b539e4faa3992877）、原三父、PINN/归一化/源生成器/执行器/策略源码均锁定。32样本历史、alpha=.1、grid17/H12/8步/mean tracking MSE/1e-12顺序选择/±.10rad/s修正/当前父反馈不变，零修正返回当前父参考。旧接管、因果隔离和保存加载证据只读复用。

顺序：先生成本轮空配置与空间/预算登记；用恒定已知风做mock和真实计时适配器等价性验证（不读新test），再锁执行源及预检结果；核对新test命名空间无实际生成撞号后，才生成并锁定18条新风及完整manifest/release。释放后不得改数值控制路径或候选/门槛，不按中间结果停跑某方案/重抽风；失败也完整保留。代码/数据/预算不一致则停止并保留，不隐性重跑。

seed42，split=test，episode=66000000+i，i按family stationary/ramp/gust、target 2.75/3.35/3.85MW、initial_pitch .025/.055rad的嵌套顺序0..17。每组合生成一条独立128秒入口，沿原环境分布、强制该family，仅生成器使用family/seed；控制器看不到这些元数据。生成前在三个工作树optimization_control的JSON中检查该episode区间不存在已生成入口，原proposal/配置中的命名空间预留不等于已用。新风float32值SHA与600条fit_train及24条开发评分风交叉核对且彼此唯一；不复制旧bank。

每条新风配原三父共54场，分别跑history17、persistence17、固定父，共162次物理回合；P/PI对公共18case各跑一次，共36次。总198次128步回合、25344个实际transition。P/PI在逐流展示中引用公共结果，不重跑或充作额外独立风。预测指标只对18条风统计一次；三父不是54条独立风，不把重叠窗口当独立重复。

## 门槛与统计先验固定

主收益：history17的18场case RMSE均值在三流均严格小于固定父，且54场总体case均值至少改善1%。预测器新增价值：相对persistence17也要求三流均严格改善且总体至少1%。两个条件分别判定；未通过不得调参或用test重新选父。完整原目标不降低，三通道学习/真实物理/全场景成功不能由均值通过推出。

同步完整报告每case相对父及persistence17的5%工程不劣、case均值/pooled/worst/bias、400kW均值+500kW最差门槛、分流/风况/目标/初始pitch、指令及实际heading/pitch/speed运动量、速率、修正端点/中幅/零与物理触界。若平均通过而worst/逐case失败，明确分开；工程容差不等于改善。P/PI比较属于完整控制方案比较。

预测报告固定未来1..8秒（t=0,8,..120）和1..12秒（t=0,8,..112）、逐h=1..12、每风/每族MSE配对、bias、裁剪、方向wrapped角误差及TI常数保持；不按test筛查决定是否运行。统计不确定性用seed42、2000次按族整风重抽（每族6条）；功率方案差先在每条风上跨三父等权汇总，再重抽18条风，不能把54场当独立样本。CI描述当前入口设计，不证明物理泛化。

## 计时、预算与磁盘

新的计时入口只包裹原history_speed_search.plan，不变更其动作/成本/分支/选择；history及persistence分别与原入口在相同状态对比，输出偏置/17成本/逐步内部误差/预测风/历史SHA精确一致，状态/父RNG不变。计时读取不得进入观测、动作或物理dt。

每次规划保存process CPU与perf wall、UTC起止、PID、Windows uptime/GetTickCount64、QueryUnbiasedInterruptTime（清醒时间）、机器idle/kernel/user累计时间；每回合保存同类起止，逐实际步记录action与transition的CPU/wall。保留全部异常长调用，不删异常或按重跑替换。counter证据只能辅助区分暂停/调度/计算，不能证明实时性；计时覆盖范围与开销如实记录。历史863.95秒原记录不变。

PINN/mock硬上限375000，精确正式预算：history17 54×3325=179550；persistence17同179550；父54×129=6966；P/PI36×129=4644，共370710。3325=17×(15×12+8)+128+1，129含reset。mock预检四次17点规划和reset/4步为821；真实预检同821，预计合计372352。预检/mock预占2000，整体保守372710。逐scope持久预占、逐forward按输入行收费，拒绝超额/重复scope；已中断预占保留。RL/update/forecaster重新拟合均0，风生成/离线审计不调用PINN。

用户给定本地工作目录 既有67.93GiB仅作既有数据登记，不整理/删除。新产物预计≤64MiB，硬上限1GiB，先记系统可用空间；新写入按实际bytes检查，单个wind写前保守预留1MiB、写后核实。外部轨迹/观测/动作及17项逐步内部误差用压缩NPZ保存，最终CSV只存必要聚合；不复制模型或旧回放，不重复保存整套旧产物。到达预计先定位新布局，超过1GiB禁止继续写入并报告，不删除已有文件。

若独立收益条件通过，只交付冻结候选的证据及下一阶段预测信息/合格搜索示范接入MADDPG的结构与对照提案，不实施新网络/训练；若失败保留并停止，不test后续调参。本地原子提交，不合并master、不推送、不改共享项目状态。
