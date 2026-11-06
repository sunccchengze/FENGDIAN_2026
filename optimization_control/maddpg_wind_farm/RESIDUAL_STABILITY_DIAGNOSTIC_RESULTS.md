# 残差后期退化：验证集诊断结果

三流均出现通道联合漂移和补偿，不能把yaw饱和或某个通道视为唯一根因。当前证据支持检验较小的整体Actor步长，尚不能证明它一定改善稳定性。

本轮遵循[运行前协议](RESIDUAL_STABILITY_DIAGNOSTIC.md)，仅使用已有validation六场景；39个策略变体共234个闭环case、29952环境步，新增训练0步，未读取旧独立test CSV或风况。三个针对性测试通过，57个受保护文件/检查点摘要不变。

S/F顺序固定为yaw、pitch、speed；每一步在混合策略自身当前obs上分别调用selected和final，再按通道取动作。zero操作只关闭对应修正，基线参考仍随当前obs计算，pitch来自final。

| 组合 | 流0 mean RMSE kW | 流1 mean RMSE kW | 流2 mean RMSE kW |
|---|---:|---:|---:|
| SSS | 333.29 | 329.42 | 318.60 |
| SSF | 343.84 | 341.72 | 321.57 |
| SFS | 533.27 | 524.61 | 355.90 |
| SFF | 539.93 | 535.13 | 365.63 |
| FSS | 432.71 | 348.38 | 340.95 |
| FSF | 439.17 | 356.97 | 343.50 |
| FFS | 398.68 | 467.83 | 325.83 |
| FFF | 403.83 | 484.98 | 332.86 |
| zero_yaw | 392.12 | 535.13 | 361.98 |
| zero_speed | 391.01 | 573.61 | 360.59 |
| zero_both | 411.99 | 563.33 | 395.83 |

仅把pitch换成final（SFS），三流相对SSS均大幅变差；但把FFF的pitch恢复为selected（FSF），仅第1流改善，另两流反而变差。这说明旧pitch漂移可能参与退化，也显示它与已变化的yaw/speed有补偿关系，不能直接得出“冻结pitch即可修复”。

把FFF的speed恢复为selected（FFS）三流分别改善5.15/17.16/7.02 kW，但关闭speed修正只改善第0流，另两流恶化。关闭yaw修正也只改善第0流；两修正同时关闭三流全部恶化。更小的残差幅度不是由本诊断验证出的通用解。

| 流 | final闭环中yaw S/F漂移RMS deg | pitch漂移RMS deg | speed漂移RMS rad/s | yaw raw饱和% | speed raw饱和% |
|---|---:|---:|---:|---:|---:|
| 0 | 4.628 | 3.948 | 0.03711 | 50.09 | 6.03 |
| 1 | 4.986 | 3.792 | 0.08572 | 92.71 | 38.45 |
| 2 | 5.887 | 2.672 | 0.01898 | 64.89 | 58.33 |

上述漂移在FFF自身闭环访问状态上统计。yaw饱和很高，却不能从关掉yaw得到三流一致改善；漂移大小或饱和相关性本身不证明因果或Critic唯一根因。

不新增yaw的all_control端点也退化：mean RMSE为353.80→383.96、329.42→587.37、319.58→335.26 kW。退化不依赖新增yaw这一动作，因此下一项实验优先减少整体Actor更新步长，而不是同时修改多种控制权限。

[闭环通道组合图](../experiments/20261024_residual_stability_diagnostic/channel_swaps.png)由Python/Matplotlib生成。红色为FFF；S/F组合与zero操作分别重新闭环运行，不能把各柱差相加。各子图横轴范围不同，跨流比较应读刻度和表格数值，不能直接比较跨面板柱长。

正式实验唯一假设（已审阅通过）：Actor学习率1e-4降至3e-5，其余网络、Critic、奖励、噪声、残差幅度、更新频率和预算保持不变。正式实验从旧all初始handover开始，baseline与干预同父/同风况/同预算三流配对，另冻结新validation/test，不能用旧独立测试筛选超参数。运行前方案见[单项稳定化协议](RESIDUAL_STABILITY_PROTOCOL.md)，实际结果另见[稳定化结果](RESIDUAL_STABILITY_RESULTS.md)。

复现（输出目录必须不存在）：

```powershell
.venv/Scripts/python.exe -B -m unittest optimization_control.tests.test_residual_stability_diagnostic -v
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.residual_stability_diagnostic --output optimization_control/experiments/NEW_DIAGNOSTIC_DIRECTORY
```

产物在 `../experiments/20261024_residual_stability_diagnostic/`，config.yaml冻结来源与57个摘要，metrics.csv为39条聚合指标，case_metrics.csv保存234条case指标，summary.txt保留完整诊断；未改写源模型、旧策略和旧实验。
