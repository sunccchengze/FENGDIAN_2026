# 单项稳定化：仅降低Actor学习率

2026-10-24正式训练前冻结，承接[验证集诊断](RESIDUAL_STABILITY_DIAGNOSTIC_RESULTS.md)。三流显示联合策略漂移和通道补偿，不支持把yaw饱和或Critic断言为唯一根因。唯一待验证假设为较小Actor步长减少联合漂移，不保证必然稳定。

1. baseline Actor lr=1e-4，low_lr=3e-5。网络、version2动作语义、Critic lr/tau、奖励、噪声、更新频率、残差范围与ramp都相同。保留旧算法默认，干预仅显式配置开启。
2. 两臂按run0/1/2分别从20261023_residual_random_control的all初始handover检查点加载，不从旧测试选择父策略、不接旧final。初始化网络/target/Critic、Critic优化器、回放、RNG逐位相同；两臂统一重置Actor Adam空moments，唯一差异是agent.config.actor_lr和全部Actor optimizer param_groups中的lr。load/resume必须一致，否则报错。
3. 六个job各8192步，共49152环境步，eval2048、warmup512后每2步更新，无全随机warmup。speed保持最终.10 rad/s修正范围；yaw前4096步从1度扩大至5度，两臂同父、同风况顺序、同探索随机流、同预算。训练策略仍为原绝对pitch+基线yaw/speed加有界修正，Critic和回放均使用总动作。
4. 验证、选模、独立测试使用最终完整权限。所有检查点含initial可参与选模，但selected=initial只证明保留，不称学习收益。新main稳定性分开报告：final/selected<=1.25；final mean和worst分别<=父1.05；low_lr final相对同预算baseline mean/worst分别<=1.05。三流各项全过才称本轮稳定化通过。原400/500 kW精度另列，旧结论不改写。
5. 新train namespace1340000、validation1450000、routine test1560000，与旧1040000/1150000/1260000分离。目标划分和风况族保持不变。7.6 m/s、4.4 MW两初始pitch复用为已知低风压力回归；stress1569000仅用于生成接口，不把它当新独立样本。
6. 全部六个job及选模/配置冻结后一次释放test，报告initial/selected/final/parent及统一P/PI。只用validation选模；不因新测试结果调参或补预算。三流SD只是样本离散度，不作统计显著性声明。无第二个候选。
7. 支持已保存eval检查点处恢复，保存Actor lr、训练/评估尺度、网络/优化器/回放/随机状态与噪声；新segment避开未完成目录。计划baseline流0在2048步暂停并真实恢复；同一检查点分叉下一回合验证动作、更新及实际恢复回放一致，不写回训练模型。
8. 冻结源/父模型/诊断摘要，先运行受影响测试再开始正式训练。UTF-8 LF；保存config.yaml、metrics.csv、summary.txt、lineage、恢复/物理回放/残差范围审计和Python图。协议不后加结果，实际结果另放RESIDUAL_STABILITY_RESULTS.md。无新增PINN训练、推送、删除或全局依赖。
