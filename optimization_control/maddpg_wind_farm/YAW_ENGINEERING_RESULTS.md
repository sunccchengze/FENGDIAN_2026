# C selected 偏航工程接管与恢复验收（2026-11-05）

**偏航软件接管通过。** 三个原 C selected 父策略、三类旧验证风况共 9 组完整闭环，零 yaw 修正时总动作、实际量、观测、功率、奖励和送入模型的输入逐值一致。正负 1° 工程序列实际改变机舱朝向及 PINN 失配输入。512 步落盘后，新进程下一回合和下一次联合更新与连续运行逐字段一致。[冻结协议](YAW_ENGINEERING_PROTOCOL.md) · [原 C 正式选择锁](../experiments/20261104_forecast_speed_formal/selection.json)

本轮共 3399 行输入，含 2580 行真实代理 PINN 和 819 行 mock，3 次隔离工程联合更新。各项预算均在 4096 行／12 次／128 MiB 上限内。正式学习步数为 0。工程检查点用途限定为 `yaw_engineering_only`。[计数与验收记录](../experiments/20261105_yaw_engineering/complete.json)

## 零修正接管

父身份保持 C selected 的 0／0／4096 步。父桨距每秒反馈，父转速每 8 秒按当时观测和自身因果来流前缀决定。新的 yaw head 在相同边界使用同一观测与前缀，之后组合动作并推进一次物理步。父权重冻结，物理轨迹随闭环反馈演化。

预定容差为动作 2e-6、实际量 1e-6、功率及 RMSE 1 W。下表各行实际误差均为零。父当前映射保持原选择权重，新增 yaw online／target 均为零末层。每步同时核对二者的零输出和组合动作，实际闭环执行 online 分支。

| 原父流 | 风况 | 父选中步 | 父／零 yaw RMSE kW | 动作最大差 | 实际量最大差 | 功率最大差 W |
|---|---|---:|---:|---:|---:|---:|
| C0 | 平稳 | 0 | 431.723 | 0 | 0 | 0 |
| C0 | 慢变 | 0 | 508.441 | 0 | 0 | 0 |
| C0 | 阵风 | 0 | 326.140 | 0 | 0 | 0 |
| C1 | 平稳 | 0 | 431.089 | 0 | 0 | 0 |
| C1 | 慢变 | 0 | 445.903 | 0 | 0 | 0 |
| C1 | 阵风 | 0 | 310.607 | 0 | 0 | 0 |
| C2 | 平稳 | 4096 | 418.955 | 0 | 0 | 0 |
| C2 | 慢变 | 4096 | 444.111 | 0 | 0 | 0 |
| C2 | 阵风 | 4096 | 298.631 | 0 | 0 | 0 |

三条风固定为原 validation 索引 0／2／4，目标均为 2.85 MW，初始 pitch .04 rad。C0／C1 的父 speed 修正全程为零。C2 三风归一化 speed 修正绝对最大值分别为 .210941、.216436、.182774，覆盖父已有非零转速修正。全部保持区间、16 个宏记录的实际执行动作、奖励、当前／下一观测、折扣和 terminal 均由保存轨迹复核。[逐对数值](../experiments/20261105_yaw_engineering/zero_pairs.csv)

## 偏航物理链路

三机不同独立标记核对了物理输入中的 yaw、pitch、speed 顺序及 SI 单位。角度核对覆盖穿越 0／2π、正负 1° 和最短转向。纯执行器算术样例把 .005 rad/s 限速推至饱和，角度域外算术值仅用于圆周测试。真实 PINN 回合仍由原环境做物理域检查。[SI 和圆周记录](../experiments/20261105_yaw_engineering/pure.json)

C2 在预选旧 stationary 风执行固定 +1° 和 −1°。新增修正改变原失配参考，经原执行器驱动实际机舱朝向。PINN 使用每步实际 heading 减当步来流再 wrap 的失配，三机 yaw／pitch／speed 输入均从轨迹独立复核。

| 工程序列 | RMSE kW | 相对零修正 kW | 最大 heading 差 rad | 最大 PINN gamma 差 rad | 最大 heading 速率 rad/s |
|---|---:|---:|---:|---:|---:|
| 零 yaw | 418.955 | 0 | 0 | 0 | — |
| +1° | 422.474 | +3.519 | .017453292 | .017453292 | .003163745 |
| −1° | 417.296 | −1.659 | .017453292 | .017453294 | .003163745 |

真实 pitch 最大速率 .00872664626 rad/s，speed 最大速率 .030391884 rad/s，均在原限制内。两个符号均为协议预定工程序列。它们只核对通道接通，没有用于选模或调整修正半径。父桨距和转速反馈会随功率改变，这里的 RMSE 差包含闭环补偿。[非零实际量表](../experiments/20261105_yaw_engineering/nonzero_physical.csv)

![偏航实际量及父策略闭环反馈（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

图中画 T01 实际机舱朝向变化、实际失配、桨距和转速，功率和误差为全场量。导出 PNG／PDF 使用保存轨迹，额外模型查询为零。[PDF（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)

已有代理响应扫描仍显示共同 yaw 响应绝对值中位数 .73 kW，标签对应 7.29 kW，部分响应方向与标签相反。本轮未定位到新的单位、机位顺序或角度接口错误。当前结论限于该代理内软件联调。[模型限制](ANCHOR_CLOSEOUT_RESULTS.md)

## 更新与恢复

新增 head 输入为 51 维，Critic 输入为 84 维。三机新 Adam 和私有宏回放为空，父 pitch／speed 权重和其目标来源文件冻结。yaw Critic 的动作字段记录实际裁剪后归一化修正。优化逻辑复用原宏 MADDPG，父 current 映射作为固定反馈背景，新增 yaw target 独立软更新。

- mock 前四回合收集 64 个完整宏样本，执行一次工程联合更新后保存 512 步边界。head 非零、Adam 有时钟及矩估计、回放随机状态均写入磁盘。
- 连续和新进程各跑下一 128 步并各更新一次。下一轨迹、采样索引、损失、梯度、current／target 网络、Adam、回放、RNG 和所有状态字段完全一致。工程联合更新总数为 3，包含恢复分支的那次更新。[跨进程记录（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- 状态保存两个控制时钟、held speed、因果 history／forecast、yaw pending 和执行器。19 步 mock 回合的宏长度为 8／8／3，末宏折扣为 .99³，terminal 清空下一 forecast 并跳过 bootstrap。t=5 的 pending 和 t=8 的新决策边界磁盘快照均恢复出完全一致的余下轨迹和终态。短快照恢复在同一进程完成，512 步完整检查点经过新进程验证。[t5（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md) · [t8（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)
- yaw 私有加载器拒绝 speed 推理快照和 speed replay，原 speed 私有加载器拒绝 yaw 状态。工程状态仅用于此次验收，后续学习需从引用的原 C selected 重新构造零 yaw。

实际输入计数为 2322 行零接管、258 行非零、774 行完整 mock 恢复和更新、45 行短回合及恢复，共 3399。运行首个尝试通过，保留完整日志。51 项锁定源文件、三个隔离工作区状态文档和原模型未改变。[保存产物复核](../experiments/20261105_yaw_engineering/saved_artifact_audit.json)

## 下一项小预算学习提案

工程通过后可按原提案审阅 Y／S 两臂、各三流、每流 2048 步，总 12288 物理步。Y 冻结原 C、仅训练 yaw，S 同预算续训原 C speed。Y 新空 Adam／回放与 S 继承状态的差别必须披露，Y 的零 yaw 消融和固定 C 对照用于通道归因。[原费用与超参表](YAW_SOFTWARE_PILOT_PROPOSAL.md)

正式执行前建议把以下条款一并锁定。用户的主指标继续为平稳、慢变、阵风各自平均 RMSE 严格优于共同 PI。验证集只用原六条风，initial／1024／2048 选模，平手保留早期。initial 的接管容差沿用本轮 2e-6／1e-6／1W。后期工程稳定性单列，三流分别要求 final／selected≤1.05 且 final／固定父≤1.05。新增 yaw 学习收益单列 Y selected 对同预算 S selected 的每族等权均值差、逐流差及关闭 yaw 差，selected=initial 的流记录为无新增选中学习收益。原 400／500 门槛、最差回合、压力和 final 退化继续报告。5% 工程不劣界只判断稳定性。

学习计划原定 37023 行输入，加本轮实际 3399 行为 40422 行，仍在原提案两阶段 42000 行上限内。新训练命名空间的占用扫描和来源锁须在学习释放前完成。未来独立测试另行冻结预算和候选。当前工程验收支持进入小预算软件学习审阅，yaw 的可重复训练收益仍待该对照实验验证。

## 复现与轻量勘误

实现入口为 [yaw_macro.py](yaw_macro.py)，验收入口为 [verify_yaw_takeover.py](../tests/verify_yaw_takeover.py)，保存数据复核与绘图入口为 [yaw_engineering_report.py](yaw_engineering_report.py)。配置和所有来源 SHA 在实验目录的 config.yaml／lock.json。沿用已有 `.venv`，入口会启用现有 pinn_tf216 兼容依赖，无新依赖安装。

```powershell
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.tests.verify_yaw_takeover prepare
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.tests.verify_yaw_takeover run
& './.venv/Scripts/python.exe' -B -X utf8 -m optimization_control.maddpg_wind_farm.yaw_engineering_report
```

上述为本轮实际命令。prepare 要求已审阅基础提交 c6a2777、全部引用产物存在、目标输出目录尚不存在，现有目录的重复执行会拒绝覆盖。已有产物可直接核对 SHA 和保存数据。重新执行须先在隔离目录建立新预算和输出身份。

上轮对话回复中的 C selected 平稳均值 339.657 kW 引用了 A selected 行。正确值为 **339.342023 kW**。原正式报告和 CSV 均正确，保留原数据。本轮将此勘误记录于协议和报告。独立测试三族 C selected 均值依次为 339.342023／419.693618／322.849668 kW，对应 PI 393.598596／487.465770／410.841864 kW，主均值条件 3／3 通过。[原独立测试报告](FORECAST_SPEED_USER_TEST_RESULTS.md)
