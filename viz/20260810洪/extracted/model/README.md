# PPO 功率跟踪模型交付状态

## 可对外引用的权重

| 文件 | 状态 |
|---|---|
| `ppo_tracking_v3_seed42.pt` | 已完成复现训练与 200 个固定测试回合评测，55,420 字节。物理模型为 `P = P_base × cos(yaw)^1.88`，目标域为 `[0.78, 0.98] × P_base`。 |
| `ppo_repro_v1_nonconverged_DONOTSHIP.pt` | 首轮未收敛对照产物，禁止用于网页、图表或答辩结论。 |

## 复现命令

```bash
cd 20260810洪/extracted
python ppo_repro_train.py
python ppo_repro_eval.py
```

评测脚本输出两份同源文件：

- `metrics_repro.json`：200 回合汇总指标；
- `ppo_eval_traces.json`：逐回合指标和一个按中位 MAE 规则选出的真实代表回合时序。

当前审计锚点：稳态 MAE 0.523%，平均调节时间 0.944 s，95 分位调节时间 1.805 s，稳态动作抖动 0°/step。两份 JSON 均记录模型 SHA-256，图表必须读取这些文件，禁止手工编造额外种子或轨迹。
