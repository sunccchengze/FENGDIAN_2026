# speed n-step适配工程审计（2026-10-28）

本轮只实现可选适配、有限内存正确性分叉和待审阅实验草案；正式RL训练0、环境新采样0、不保存候选策略。桨距740d040的selected表现不能代替尚缺的同锚点价值方向与稳定性证据，不启动拟议49152步训练，不等待另一对话才能完成工程。yaw停止、模型和历史实验只读，不合并master、不推送、不改原状态。

目录沿用现行职责：nstep_replay_core.py仅复用740d040的SequenceReplay连续窗口逻辑并记录出处；speed_nstep_algorithm.py增加严格迁移元数据和FrozenSpeedMADDPG可选子类，不修改旧v4类/加载器；speed_nstep_engineering.py只读来源、运行小型分叉和复算；tests/test_speed_nstep.py保存针对性检查。SPEED_NSTEP_DRAFT.md为未启动草案，SPEED_NSTEP_ENGINEERING_RESULTS.md记录工程结论。experiments/20261028_speed_nstep_engineering保留config.yaml/metrics.csv/summary.txt，其余审计台账/JSON/源码快照按实验忽略规则保存，不删除失败。

1. 只读核对.提交740d040的nstep_algorithm.py、测试和协议，保存commit和SHA；逐字复用SequenceReplay类及tail_rule，不能整分支合并或依赖另一worktree运行。严格包装补充完整迁移证据，不能使用原类缺省legacy推断绕过验证。
2. n1默认行为精确复用FrozenSpeedMADDPG.update和原td_target，采样锚点/RNG相同。n8只替换Critic的累计奖励、末状态/终止及gamma^m；Actor目标、父冻结与target路径、head/优化器、采样起点、reward、radius规则均不变。目标联合动作由s_t+m的父reference和目标speed头以当前更新时统一radius组合。
3. v4缺少sequence元数据时必须提供可溯源累计插入计数、episode horizon和来源epoch，核对size/position、完整环形次序、非终止边next_obs==下一个obs、time递减、done/reset及总动作字段；不能仅按size默认补全历史计数。证据不足则拒绝适配并报告。新格式显式保存n/tail_rule/horizon/epoch、单调序号、计数/实际m直方图、全部网络/优化器/回放/RNG；旧v4加载行为保持不变。
4. 检查跨episode、回卷、覆盖后最新尾部、新写入、true done与缺尾：真实终止不bootstrap，缺尾以实际m和gamma^m bootstrap。奖励直接使用已存scale后的共同奖励，不再缩放。恢复缺关键元数据、错误顺序或错误n必须拒绝。
5. 合成数据做显式目标算例和n1精确更新。真实三份原pitch父及旧speed训练回放只做有限内存分叉：每流n1原实现/适配/n8各3次更新；n8保存到BytesIO后原/恢复各1次；三个旧final回放追加已存训练episode前8条，再做n8原/恢复各1次。真实审计总上限39次丢弃更新；不调用环境或test，不根据loss解释收益。保留父状态继承、同锚点、目标输入、实际m和恢复证据。
6. 源码修改前先固定本协议；实现和测试通过后冻结本地工程输入摘要。单位测试可创建合成网络和内存副本，无正式训练预算或候选权重。测试与工程通过只证明实现正确，不满足未来训练的启动条件。
