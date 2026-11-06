# 偏航实现独立复核

2026-11-05，受审实现 `a12288f`。**现有代码与工程记录支持进入既定 Y／S 两臂、三流各 2048 步的软件小试，未发现当前已证实的代码阻断项。** 正式入口应从原 C selected 重新构造 Y 的零 yaw 和空回放／Adam，独立登记正式 purpose 和来源锁。已有 yaw 工程状态仅供工程复现。初始化、权限和新格式的入口检查应纳入小试启动验证。

源码已落实单一物理循环、同边界观测与 forecast、yaw 权限、独立 yaw replay schema。Critic 动作只表示 yaw，固定 C 的在线 speed 反馈由 `speed_heads` 提供；yaw 的 bootstrap 未调用父 speed target，这与本次动作表示一致。旧报告对“父 online／target 选择”的要求在当前实现中无需新增父动作字段。[实现（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

**G1 已解决，特定序列的实测范围需准确表述。** 工程工厂设 `[1,1,1]`，`YawEpisode` 入口同时检查全通道可用，组合函数按原 yaw 物理范围加入 `2*(π/180)*z/(hi−lo)`。本轮纯函数输入 `[1,0,−1]` 得到物理参考 `[.017453292385,0,−.017453292385]` rad。保存的短 mock 回合实际执行 `[1,−1,.5]`，首秒三机 heading 分别为 `[.003163745167,−.003163745167,.001581872583]` rad，与记录的 float32 总命令经原一阶执行器公式一致。原工程还保存了三机共同 ±1° 的真实 PINN 轨迹和全三机零 yaw 轨迹。因此逐机异号及幅值传递有实际执行器证据，精确 `[1,0,−1]` 未单独跑过完整闭环。这是具体测试向量的覆盖缺口，对当前小试不构成阻断，后续若增加该向量应计入剩余工程预算。[权限工厂（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [组合函数（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [短回合序列（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

**G2 已解决。** yaw 和父 speed 在同一边界读取同一 `self.obs`、`self.features`，之后只有一次 `env.step`。两种修正分别保持，父桨距每秒重算。每次响应后历史追加一次，仅在宏闭合时计算下一 forecast，terminal 使用零 forecast。独立复算了 9 对保存的零 yaw 轨迹，动作、观测、实际量、送入模型的输入、奖励与父轨迹逐值一致；每个宏的 obs／next_obs、实际 yaw z、逐秒奖励和 speed 保持均与实际记录一致。另从保存的当时来流前缀重新计算 forecast，各边界逐值相等。源码只有这一个闭合预测入口，记录没有单独保存 forecast 调用计数。现有证据支持同观测和因果前缀合同。[决策与单次推进（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [保存轨迹索引](../20261105_yaw_engineering/real_zero.json)

**G3 已解决。** C 的已选在线 speed 权重被拷贝到独立 `speed_heads` 并冻结。`speed_z` 只访问该组，实际父反馈使用这条映射。继承的 `targets` 输入为 next obs、next forecast 和 yaw target z，动作变量只表示 yaw；父 C 是固定反馈背景。这里没有调用 C 的 speed target，也无需为了匹配旧审查措辞显式加入父动作。非零 yaw 会改变后续实际观测，父桨距和 speed 据此反馈，保存轨迹体现了该闭环关系。[冻结 speed 与重置 yaw（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [父在线 speed（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [继承的 yaw 目标计算（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

**G4 的来源与错格式保护已解决，尺度及权限由外层冻结合同保护。** yaw 状态／回放均使用新 schema，加载严格比对 purpose、完整 identity 和文件 SHA。identity 记录原 pitch 父、forecast、C 快照、选中步、流号及原源锁。工程记录已有 speed／yaw 错格式双向拒绝。本轮以保存的 512 步 yaw 状态做只读加载，分别改变 expected identity 的 parent、forecast、snapshot、step、run、source_lock_sha，全部拒绝。以不同正式 purpose 的本地探针类加载工程状态也被拒绝。[状态与恢复（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [原错格式检查（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

`RADIUS` 是冻结源码常量，动作边界和权限来自锁定环境及 episode 入口，不是 checkpoint identity 中独立存储的字段。因此通用 loader 单独使用时，不能声称它自身验证了全部尺度／环境权限。当前工程 `context` 校验包括 yaw 源码在内的 51 项来源，已有检查可覆盖此工程范围。正式小试入口继续锁源码／环境，显式核对 `RADIUS=π/180`、两时钟 8 秒、Y 权限 `[1,1,1]`、父参考模式和来源，并用独立正式 purpose。无需扩大公共接口。[工程来源锁检查（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [episode 权限检查（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

**Adam 仍绑定正确参数。** `super().__init__` 创建的 Adam 先绑定 heads／critics，随后 `Linear.reset_parameters()` 原位更新原参数。代码没有替换 online head／critic 参数对象。复核了新实例和加载实例的六个 Adam 参数对象列表，分别与三组 yaw head／critic 的参数对象逐项一致，不含任何父 pitch 或 `speed_heads` 参数。新实例 Adam 为空，加载的工程 Adam 时钟为 1。目标网重新复制和 `.load_state_dict` 也没有替换 online 参数对象。此处未执行 optimizer step。[原位重置（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [Adam 恢复（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

完整恢复方面，本轮比较了保存的连续与新进程下一回合后的整个状态树，逐字段相等；原记录两个进程 PID 不同。短回合 m 为 8／8／3，末宏 terminal、`.99³` 和零 next forecast 已有保存证据，t=5 pending、t=8 边界恢复覆盖同进程分支。完整训练状态入口仍只允许 128 步完整边界，S 的 C2 继承状态和 Y 的新零 yaw 必须分开登记。工程累计 3 次隔离更新，其中存档时更新计数为 1，连续和恢复两分支的终点计数各为 2。`yaw_engineering_only` 状态不作小试的初始父。[跨进程证据（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md) · [短回合证据（交付范围说明）](../../../materials/洪祖名/20261106_optimization_final/README.md)

**既定小试预算可容纳。** 学习与评估计划为 37,023 行，工程已实耗 3,399 行，总计 40,422，距 42,000 上限余 1,578 行。工程分项账本均 complete 且 actual=reserve，实耗 3,399 行和 3 次更新。128 MiB 按工程与小试合计计数，未来独立测试另行冻结。失败／预检／恢复分支也计入实际预算，固定候选和预算不因结果追加。[预算账本](../20261105_yaw_engineering/model_budget.json)

启动时需要完成以下局部核验。它们用于约束本次运行入口，不增加算法候选或新测试。

- Y 三流从原 C selected 的 0／0／4096 构造，yaw online／target 末层为零，Adam／宏回放及新增计数为空。S0／S1 重建已锁初态，S2 完整继承 C2 的 Adam／回放／随机状态，分别披露新增与继承计数。双方探索衰减、首次更新和总更新预算按本轮新增物理步安排，避免直接用 C2 的继承 4096 步代入新 2048 步的调度。
- 完成新训练命名空间占用检查和正式配置／源码冻结。只用旧六条 validation，从 initial／1024／2048 按均值选择，平手取早，保留三个角色及 `selected=initial`。
- 主判定继续采用平稳、慢变、阵风各族 case 等权、三流等权的完整回合 RMSE 与同 case 公共 PI 比较。每族均值严格低于 PI 才满足该项。报告中的 final／selected≤1.05、final／父≤1.05 可作稳定性描述或独立子项，不作为用户主验收的附加硬闸。逐流、worst、400／500、压力与 pooled 同样另列。
- Y−S 比较含不同可训练模块与继承状态。Y 相对固定 C，以及同权重 yaw 开／关的在线闭环差值用于解释新增 yaw 作用。前两流 speed selected 仍是初态，接通三通道不代表三通道均有新增学习收益。

复核确认原工程输出 42 项登记产物和 51 项输入 SHA 与账本相符。使用了纯命令组合、保存张量加载、已有轨迹和 forecast 前缀复算。此次 PINN／mock 查询、环境推进、优化器更新和新风均为 0，仅写本报告，低于 16 MiB。当前结论为可以开始既定小试的工程准备与执行，正式入口需落实上列来源和预算检查；本报告没有运行该小试。
