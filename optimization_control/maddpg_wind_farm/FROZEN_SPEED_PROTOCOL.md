# 冻结父映射与独立speed头：执行前冻结协议

2026-10-27 用户明确批准实施ANCHOR_NEXT_CANDIDATE第1—6项。只新增speed权限，yaw不训练，PINN不改。工程接管通过后才进行独立最小运行及正式49152步；失败不放宽阈值、不换父、不追加候选或预算。只在本独立worktree/codex分支写入，不改原工作区、原实验或共享状态文件，不合并master、不推送。

目录职责沿用现有约定：utils/reference_schedule.py放可复用数值参考；环境和controllers增加默认关闭的新模式；frozen_speed_algorithm.py放显式v4策略；frozen_speed_training.py放冻结身份、接管、smoke、配对训练、选择锁、独立测试和审计；frozen_speed_figures.py只读CSV绘图。协议为configs/frozen_speed.yaml，报告FROZEN_SPEED_RESULTS.md；实验目录YYYYMMDD_frozen_speed及独立smoke子目录，保留config.yaml/metrics.csv/summary.txt，权重/轨迹/JSON/PNG/PDF按旧忽略约定保存，不覆盖旧结果，不自动清理。

1. 父固定为20261023_progressive_random_control的pitch_run_0/segment_000/step_00016384.pth（28e221e6f6e74096ef74e9a9375c638823a055c38232ef4d3b5e16a5026996ea）、run1 step00012288（0fcb0b9d474db0d04b3ac2d86c91d2f39d66bb3c025e30d911ce79b2ba445821）、run2 step00008192（e2897be535e5c9bae27acbecc5edd57460a8a038ba28719e366ab4c904309a05）。继承Actor、target、所有Critic/优化器、回放和RNG；两臂Actor moments均从空开始。模型/奖励/学习率/Critic结构/执行器不变。
2. 新模式observation_float32_v1：从与Actor相同的float32 obs[:,1]重建有效风速，逐步执行相同乘减除及clip，得到总归一化speed参考。环境投影及P/PI都调用同一数值约定；旧模式默认legacy_physical，旧分支行为/旧元数据保持。原回放仍为相同SI映射的总绝对目标，不重标记；单独量化其旧调度与新参考差，不能把数值修复称为解决后期退化。
3. 候选每机15→32→1 ReLU/Tanh头，末层权重和偏置0；父线上完整Actor冻结。父target继承旧target，更新时按原tau=.01的lerp跟随冻结线上Actor；新target头按同tau更新。Critic保持45维联合obs+9维联合总动作=54输入，目标动作无探索，Actor i梯度只流向其speed头，其他机使用同批回放总动作。线上父无梯度且逐位保持；yaw后台0参考，pitch来自冻结父当前obs映射。
4. 训练speed raw在[-1,1]内叠加白噪声后clip，再乘当步物理范围（前4096步±.02→±.10 rad/s），与参考合成并clip总边界。target也使用当前训练更新时的同一范围，不加噪声；不是回放采样时历史范围。验证/选模/测试均用最终±.10。baseline按原仅pitch权限续训，外部pitch归一化噪声std=.03；候选只给新speed raw噪声std=.15，均衰减至.2。两臂每回合从同一42派生探索流抽完整3×3噪声，再按权限启用，风况、目标和初态配对。
5. 新version4显式存父线上/目标、speed线上/目标、Critic/target、head Adam、Critic Adam、配置、动态范围、回放、NumPy/replay/Torch RNG和metadata；旧v1/v2/v3加载器行为保留且拒绝v4。baseline保留v1并在metadata记录新模式。新头初始化用42派生专用流；恢复全训练状态，不改变父权重或复制source文件到原目录。
6. 工程门槛：三流父回放obs/next_obs上的online/target零头总动作max<=2e-6；6个新validation case各128步新两臂零头动作max<=2e-6，heading/pitch/speed差<=1e-6，功率max及RMSE差<=1 W，无执行器违例。另逐case比较本分支legacy与原始环境类，要求精确复现；旧模式到新模式的微小变化只记录，不改变旧失败结果。
7. smoke独立于正式目录，只有run0两臂各1024步（共2048），前512采样不更新，每2步更新，噪声衰减及范围仍按8192预算进度；只验功能/梯度/冻结/保存加载和一次真实回合恢复分叉，不按smoke分数改配置。正式6次从原父状态重启，不继承smoke。正式每臂三流×8192=49152新增步，eval每2048，warmup512，每2步更新，无全随机warmup。baseline0和speed0先由worker在2048保存边界退出，再由新进程恢复，保留原segment；两者各做两个128步内存分叉并对齐真实恢复动作，分叉不写回实验检查点。
8. 主seed42，run0/1/2派生流；train namespace8400000，validation8510000，test8620000，已知压力8639000，smoke train8450000；探索8404（smoke8454），新头8405。生成器和常规目标沿用旧协议；新validation仅用于选模，包含initial，只按mean严格改善选中。所有结果冻结selection后一次释放新test；不使用已读anchor test选择参数或父策略。
9. 三类判定独立：接管按第6条；稳定性要求final/selected<=1.25，final mean/worst相对父及配对baseline<=1.05且三流全过；收益要求selected_step>0，selected及final相对同预算父续训三流均严格改善、总体至少1%，两者分别列结果且共同满足才称可重复收益。1%是效应尺度，5%是工程不劣，三流不作显著性证明。400/500kW精度分别列initial/selected/final，不替代前述验收。
10. 正式冻结测试20 case（18新routine，2已知7.6m/s/4.4MW回归）。baseline每流initial/selected/final/parent，候选再加zero_selected/zero_final；共同fixed/P/PI只评一次，合计660指标/84480轨迹。零speed消融应精确回到冻结父闭环。P/PI同新参考模式、风况、初态、目标、执行器，是完整方案比较。冻结与权限同时改变，不能将全部差值归因speed维数。
11. 验证复制起点、Critic优化器/RNG/回放、父及target路径、目标梯度/输入拼接、新旧加载互拒、动态包络、next command/奖励/终止/执行器、真实恢复、全测试RMSE复算、源保护。保留所有失败、initial/selected/final、曲线和真实控制轨迹。仅报告当前合成代理内结论；yaw局部响应限制和给PINN组的材料单独附录，不发消息。

v4通用policy(actor,obs)必须按已登记的online/target Actor分派到对应完整合成动作，不能继承旧原始输出的默认实现。首个20261028_frozen_speed目录仅完成工程接管（3/3、正式及smoke均0）；接口审查补齐此入口后，最终目录20261028_frozen_speed_checked重新冻结并复核接管。首目录及执行字节快照保留，不作为另一个学习候选或增加训练预算。
