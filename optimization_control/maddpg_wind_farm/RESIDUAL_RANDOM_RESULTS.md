# 基线参考加MADDPG修正量：实测记录

本轮按[运行前协议](RESIDUAL_RANDOM_CONTROL.md)执行。模型仍是十二输入合成标签联调PINN，桨距由旧绝对策略控制，转速/偏航由后台基线加有界MADDPG修正；这是混合控制，不是网络独立产生全部物理参考。

实际完成两层、12个配对训练job，每个8192步，共**98304新增环境步**。speed工程晋级3/3；all工程晋级2/3，完整三流稳定性未通过。speed与yaw的零头接管均成功，解决了上一轮蒸馏无法保持后台转速参考的初始化问题；这不等于后续策略稳定或有真实收益。

| 阶段/训练臂 | 流 | selected步 | selected均值/最差 kW | final均值/最差 kW | final/selected | 工程通过 | 400/500 kW及比值门槛 |
|---|---:|---:|---:|---:|---:|---|---|
| pitch_speed | 0 | 0 | 366.94/504.86 | 381.32/554.32 | 1.0392 | 是 | 否 |
| pitch_speed_control | 0 | 0 | 366.94/504.86 | 372.64/509.45 | 1.0155 | 是 | 否 |
| pitch_speed | 1 | 2048 | 329.42/470.97 | 365.86/532.98 | 1.1106 | 是 | 是 |
| pitch_speed_control | 1 | 0 | 373.21/534.86 | 395.77/557.19 | 1.0604 | 是 | 否 |
| pitch_speed | 2 | 8192 | 330.38/459.57 | 330.38/459.57 | 1.0000 | 是 | 是 |
| pitch_speed_control | 2 | 0 | 340.26/481.56 | 357.08/505.97 | 1.0494 | 是 | 是 |
| all | 0 | 4096 | 333.29/465.22 | 403.83/556.09 | 1.2117 | 是 | 是 |
| all_control | 0 | 4096 | 353.80/503.82 | 383.96/531.46 | 1.0852 | 是 | 否 |
| all | 1 | 0 | 329.42/470.97 | 484.98/585.78 | 1.4722 | 否 | 否 |
| all_control | 1 | 0 | 329.42/470.97 | 587.37/807.05 | 1.7831 | 否 | 否 |
| all | 2 | 2048 | 318.60/445.05 | 332.86/479.23 | 1.0447 | 是 | 是 |
| all_control | 2 | 2048 | 319.58/443.68 | 335.26/466.94 | 1.0491 | 是 | 是 |

两层selected分别在各自父策略与完整权限下比较；后层父策略来自前层验证选中的检查点，不是无条件接最后一轮终点。speed第0流selected仍step0；all第1流selected也仍接管初始，这两项不能称新增通道学习收益。all第1流final/selected=1.4722超过1.25；其speed-only配对对照终点也明显退化（587.37 kW），不能把该流退化唯一归因于yaw。

独立测试在全部选择冻结后一次释放，1200条指标、153600行轨迹；常规统计只含stationary/ramp/gust，低风压力场另列。数值为RMSE kW，±为三个训练流的样本标准差，不是置信区间。

| 新增权限 | 残差selected | 同预算对照selected | 残差final | 同预算对照final | P | PI |
|---|---:|---:|---:|---:|---:|---:|
| pitch_speed | 338.84±22.45 | 351.74±13.89 | 355.20±18.61 | 354.68±10.93 | 518.57 | 437.25 |
| all | 326.15±7.62 | 331.22±13.88 | 391.18±73.00 | 416.39±133.55 | 518.57 | 437.25 |

speed的selected相对同预算pitch继续训练均值降低3.67%，但终点355.20对354.68 kW，没有终点总体收益；三配对终点仅第2流改善。yaw的selected相对同预算speed继续训练均值降低1.53%；final均值391.18对416.39 kW虽低6.05%，但三配对终点只有第1流改善，均值优势主要来自该流对照退化。不能以这些均值证明稳定收益，更不能将较低selected当作终点收敛。

| 低风压力场（7.6 m/s、4.4 MW） | 残差selected | 对照selected | 残差final | 对照final | P/PI |
|---|---:|---:|---:|---:|---:|
| pitch_speed | 1684.61 | 1607.95 | 1703.71 | 1562.73 | 1383.30 |
| all | 1745.88 | 1743.09 | 1785.05 | 1749.50 | 1383.30 |

低风压力场仍明显差于P/PI，speed与yaw的残差selected也没有改善对应同预算对照。这是当前合成模型内的失效场景，不是经过物理证明的全场可达性边界。

新增通道确实产生了修正：下表来自完整20个独立测试case（含压力场）的策略动作，yaw RMS换算为度。raw饱和定义为|raw|>=.99，总speed clip是最终归一化总目标接近±1的比例；两者含义不同，不能混为执行器限速。

| 阶段 | 流 | checkpoint | speed修正RMS rad/s | yaw修正RMS deg | speed raw饱和% | yaw raw饱和% | speed总目标clip% |
|---|---:|---|---:|---:|---:|---:|---:|
| pitch_speed | 0 | selected | 0.00000 | 0.000 | 0.00 | 0.00 | 0.00 |
| pitch_speed | 0 | final | 0.08712 | 0.000 | 30.04 | 0.00 | 0.22 |
| pitch_speed | 1 | selected | 0.09259 | 0.000 | 1.30 | 0.00 | 0.00 |
| pitch_speed | 1 | final | 0.08150 | 0.000 | 0.00 | 0.00 | 0.00 |
| pitch_speed | 2 | selected | 0.08494 | 0.000 | 36.56 | 0.00 | 3.31 |
| pitch_speed | 2 | final | 0.08494 | 0.000 | 36.56 | 0.00 | 3.31 |
| all | 0 | selected | 0.07459 | 3.195 | 7.59 | 33.33 | 3.31 |
| all | 0 | final | 0.06932 | 4.881 | 11.16 | 49.93 | 0.18 |
| all | 1 | selected | 0.09259 | 0.000 | 1.30 | 0.00 | 0.00 |
| all | 1 | final | 0.09235 | 4.977 | 35.87 | 91.35 | 0.07 |
| all | 2 | selected | 0.09056 | 3.577 | 66.56 | 29.92 | 0.07 |
| all | 2 | final | 0.09134 | 4.800 | 60.13 | 60.78 | 3.31 |

speed selected第0流和yaw selected第1流的新增修正仍为0，符合其selected=initial。其他两流的selected新增通道修正非零；all最终yaw raw饱和率最高91.35%，说明学习常贴近预设范围，并非小幅平滑修正或已证最优解。最大speed修正约.10 rad/s、yaw约5度，均在浮点容差内满足预设包络。

审计通过：37个受保护源/模型/旧产物摘要不变；12个job的初始网络和回放重建一致，online/target的旧总动作最大误差全为0。36个initial/selected/final加载测试中的带噪动作与下一update一致。12份最终回放共393216条保留转移（含继承重叠，不是独立新增训练数）通过总动作/next command、奖励、执行器限速和动态修正包络检查。1200条RMSE从153600行测试轨迹复算，最大差0 W。

真实恢复审计也通过：第0流2048检查点保留，run从其恢复至8192形成两个segment；同一2048检查点的两个128步内存分叉，其动作、回报、更新loss、探索状态和网络完全一致，并与真实恢复训练的下一回合回放动作逐位相同。256个诊断分叉环境步不写入实验训练检查点，不计入98304训练预算。

图表均由Python/Matplotlib从冻结指标绘制：

- [分阶段、分流验证曲线](../experiments/20261023_residual_random_control/residual_paired_validation.png)：蓝线为新增残差权限，橙虚线为相同父策略和预算的对照，圆点是冻结选中点。用来辨认阶段性改善与后期回退，不能只展示最低圆点。
- [同预算独立测试配对图](../experiments/20261023_residual_random_control/residual_paired_test.png)：每列selected/final分别比较，P/PI横线共用风况与执行器。图中all第1流终点的差异不能代表其余两流。

原冻结审计脚本仍保留原概览图；新增residual_figures.py只读CSV改善可读性，保留figure_inputs.json输入摘要，不新增策略评估或训练。

新增实现为 `residual_algorithm.py`、`residual_random_control.py` 和 `verify_residual.py`，图表后处理为 `residual_figures.py`。version2检查点显式记录动作语义、修正尺度和随机状态，version1加载器拒绝误读。原Actor/target的新增输出行置零，其他输出行和hidden逐位继承；Critic、优化器、回放、RNG保留。两配对臂均重置Actor Adam moments，避免仅一侧保留旧动量造成额外差异。Actor/target更新、执行器和回放始终使用合成后的总绝对目标。

speed物理范围从.02线性扩大至.10 rad/s，yaw从1度至5度；均在前4096环境步扩大，后续固定。噪声在raw修正坐标注入后先限幅，再合成基线和修正，最后裁剪全域动作边界。pitch仍使用绝对归一化噪声。范围是预设联调假设，不是风机硬件标准或已证最优权限。

每个检查点的验证/选模/测试都使用最终完整权限，训练时使用当步范围；检查点同时记录二者，恢复按step重新取得训练范围。因此selected=step0只说明旧行为在完整权限接口下得以保留，不代表新通道学到收益。工程相对门槛、旧400/500kW精度和同预算性能差异分别报告。

恢复限于已保存eval检查点的回合边界，不保存回合中间状态。最新检查点之后的未持久化计算在中断时会重做；新segment编号避开所有旧目录，保留未完成目录。真实第0流已先到2048步再通过 `run` 恢复至8192步。审计另将该检查点分叉两次运行下一回合，比较动作、回报、更新、探索状态和网络，并与实际恢复训练的下一回合回放核对；诊断分叉不写入实验训练检查点。

31项不同受影响测试通过：9项新残差契约、8项随机参考调度、14项MADDPG/接口/环境。覆盖零头在online/target父训练obs和next_obs上保持总动作、speed/yaw非零梯度、范围外噪声约束、v1/v2互拒、下一update恢复、权限门槛及不完整segment目录保留。

复现（输出目录须不存在；从仓库根目录执行）：

```powershell
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.residual_random_control prepare --output optimization_control/experiments/NEW_DIRECTORY
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.residual_random_control worker --output optimization_control/experiments/NEW_DIRECTORY --stage pitch_speed --run-id 0 --stop-after 2048
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.residual_random_control run --output optimization_control/experiments/NEW_DIRECTORY
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.verify_residual --output optimization_control/experiments/NEW_DIRECTORY
.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.residual_figures --output optimization_control/experiments/NEW_DIRECTORY
.venv/Scripts/python.exe -B -m unittest optimization_control.tests.test_residual_control optimization_control.tests.test_random_wind_training optimization_control.tests.test_maddpg -v
```

`run`可从已有eval检查点恢复未完成工作；所有阶段选模冻结后禁止追加训练，独立测试只释放一次。测试故障不会重新训练；保留已冻结策略并定位问题。本轮输出位于 `../experiments/20261023_residual_random_control/`，三类提交小文件为config.yaml、metrics.csv、summary.txt；其他权重、风况、审计JSON/CSV、轨迹和图沿用默认忽略约定保留本地。

上一轮联合蒸馏失败及全部旧模型/实验保持原样；本轮不把模型内功率指标解释为真实物理收益，也不以未通过晋级否定MADDPG或三通道控制的可行性。
