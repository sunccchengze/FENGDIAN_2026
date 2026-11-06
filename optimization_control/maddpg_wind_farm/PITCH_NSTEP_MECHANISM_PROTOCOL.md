# n-step机制核查与候选交接（2026-10-28，评估前冻结）

主对话批准本轮机制审计和实验候选交接，新增正式训练0，新增评估环境步硬上限65000。
沿用独立worktree/分支；740d040及此前源码、模型、实验只读，不改默认，不合并master/推送/改原状态文件。
不改n、不追加超参、候选或checkpoint选择，不重抽独立test，不为三通道替换父。

## 文件职责与保存

`pitch_nstep_mechanism.py`：小型锚点审计、同动作跨Critic评分、同延续反事实、自身闭环核查及汇总。
`pitch_nstep_handoff.py`：已锁定三个n8 selected的只读清单和新进程验证回放，不训练或选择。
`PITCH_NSTEP_MECHANISM_RESULTS.md`：机制证据、反证、能力保留和可审阅迁移决定。
实验20261028_pitch_nstep_mechanism，沿用config.yaml/metrics.csv/summary.txt；UTF-8 LF，逐流×case分片摘要恢复，半成品另开attempt保留。
交接清单/归一化/回放结果均在该实验目录，不打ZIP，不重复12张图；权重不复制不写回、不入Git。

## 预声明锚点与网格

仅复用740d040的validation bank：stationary/ramp/gust×目标2.9/3.5MW，初始pitch=.04rad，共6场，三训练流全部保留。
每策略t32/96保存当前环境完整状态；延续32步，同时计前8/32步。复用旧完整128步验证指标/轨迹，不再运行整套验证网格。
固定父参考为本流n1 initial（与n8 initial参数相同）。动作集合9个：零、共同±.005rad、机1/2/3各±.005rad。
修正加在当前物理pitch参考，经原project/mapper/actuator，不直接改实际pitch；执行控制输入只有当前obs。
三机共享yaw/speed后台曲线、执行器、冻结PINN，不开放speed/yaw权限。

## 隔离Critic与自身策略两层口径

1. **同锚点交叉评分**：在父参考的同一t32/96状态，使用同一9动作，交给本流n1/n8各initial/selected/final六个Critic组评分；
   三个Q_i都保存，逐机用本机Q，共同用均值Q。对每个动作实际执行一次首步修正，随后分别用父参考、n8 selected两种固定延续策略。
   在每一种延续内，各Critic面对的状态、首动作、未来风和后续策略都相同，区分Q函数变化与Actor/状态变化。
   交叉Critic本来针对各自训练策略，不把跨延续结果当该Critic真实期望Q的无偏标签；两种延续差异也单列。
2. **各策略自身闭环**：六个policy role各用自己的t32/96状态，零/共同±.005rad三动作，后续恢复该策略；只作自身策略有限回报解释，不能用它隔离Critic变化。
   完整128秒RMSE/bias/std直接复用对应checkpoint已保存validation轨迹，重新复算；新前96步与旧记录严格复现核对。
3. 全部有限G按gamma=.99折扣实际scale100奖励，保存tracking/action_change分项及RMSE；不是长期期望Q或全局动态最优。
   固定|deltaQ|、|deltaG|>1e-5为非平局；保存全部小值，不按支持或目标删除。
4. 复用pitch_action诊断的clone_env/corrected_action/critic_probe/support/totals/trace_row；使用原单样本env.step，不做批量PINN替换。
   支持仍32近邻逐坐标min/max，不称密度支持证明；额外记录每critic当下回放32近邻锚点的真实m分布及原训练m直方图，不消耗采样RNG。

## 固定预算与复用

无复用的最坏预算：六policy×三流×六case×96前缀=10368；公共网格三流×六case×两锚点×9动作×两延续×32=20736；
自身网格三流×六case×六policy×两锚点×3动作×32=20736；合计51840步。
新进程三候选各18场统一验证回放另6912步，合计最坏58752，低于65000硬上限；不追加场景。
可按Actor参数SHA、case/初态、锚点、实际首动作、固定延续参数SHA精确复用相同状态/分支，记录实际步数与复用步数。
已有完整回合轨迹只读复用；重复role（如n1/n8 initial、selected=initial）保留语义标签，不能计作独立样本。
每个新分片保存来源SHA、实耗步数、完整分叉时序、评分、m/支持；完成后只复算，不重新评估。
seed42，无探索/训练/optimizer调用；运行前后源/模型/策略摘要和网络参数一致。失败保留，不删场景或放宽容差。
原验证复现容差功率≤20W、归一化pitch动作≤1e-5；超限停止修复，不放宽。

## 能力保留与交接决定

仅核对既存训练/validation和已保存独立test结果，不新增test执行或重选checkpoint；保留case均值与pooled两种口径、压力及流2反证。
交接锁定selection.json中的全部三个n8 selected，清单记录绝对路径/SHA、归一化、模型/环境/权限/加载类、n与tail_rule、恢复状态和validation来源。
新进程加载后回放原18场validation，并与对应保存轨迹/指标核对；不是独立测试或额外选模。
结论分开回答：是否观察到相同参考下Q方向变化、是否支持稳定控制、是否足以把单独TD目标作为speed的待检验候选。
speed未在本轮实际训练；最多支持工程适配/后续预声明对照，不把pitch结果当speed收益或三通道稳定性证明。证据不足时明确停止正式迁移，不自动换父或启动RL。
