# 冻结父策略动作约束：实际结果

本轮遵循[冻结协议](ANCHOR_PROTOCOL.md)，检验Actor损失中增加父策略动作偏离惩罚。baseline lambda=0，anchor lambda=1，Actor学习率均1e-4；网络、Critic、环境reward、执行器、探索和预算相同。冻结父Actor在当前采样状态上给出总动作参照，惩罚不进入Critic TD目标。

结果尚在生成中，不能将实现测试通过视为性能通过。两臂三个主种子42派生流各8192步，固定预算49152步，不追加候选。父策略为20261023_residual_random_control三个all初始交接；version3保存teacher及完整训练状态，旧version1/2源码和加载行为保留。

## 验证和复现

5项针对性测试通过：lambda0与旧算法连续三次参数/优化器更新精确一致，teacher冻结、三通道梯度、当前状态参照/固定尺度、version3恢复及非法参数拒绝。

```powershell
.venv/Scripts/python.exe -B -m unittest optimization_control.tests.test_anchor_control.AnchorTests -v
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.anchor_training prepare --output optimization_control/experiments/NEW_ANCHOR_DIRECTORY
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.anchor_training worker --output optimization_control/experiments/NEW_ANCHOR_DIRECTORY --arm baseline --run-id 0 --stop-after 2048
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.anchor_training run --output optimization_control/experiments/NEW_ANCHOR_DIRECTORY
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.verify_anchor --output optimization_control/experiments/NEW_ANCHOR_DIRECTORY
```

NEW_ANCHOR_DIRECTORY必须不存在；中断训练只在已保存的eval回合边界恢复。version3策略用`anchor_algorithm.load_policy(path)`或`AnchoredMADDPG.load(path)`加载，返回agent和metadata；之后仍调用`agent.act(obs)`。旧v2加载器有意拒绝v3，避免丢失teacher和惩罚配置。

产物为`../experiments/20261024_parent_action_anchor/`下的config.yaml、metrics.csv、summary.txt及检查点、选择锁、独立测试、恢复审计和Python图。7.6m/s、4.4MW只算已知压力回归；新常规随机轨迹才是新独立测试。当前仍是合成数据PINN联调，不代表真实物理精度。
