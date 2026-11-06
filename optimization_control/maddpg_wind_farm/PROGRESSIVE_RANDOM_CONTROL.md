# 随机风下逐通道接管 2026年10月23日

用户确认执行顺序为仅桨距通过后接管转速，再通过后接管偏航，每次只增加一种控制权限。当前基础随机风沿用平稳湍流、慢变、阵风三类及原入口范围，不降低湍流强度或精度门槛来制造通过。

## 执行约定

1. 复用冻结十二输入模型及统一执行器，PINN组源文件和全部旧实验不变。已有观测、三维动作及检查点version=1不变，不改网络结构。
2. 新实验首层承接20261022随机入口实验各流的验证选中策略，继续学pitch。旧结果仍记失败，不追加训练到已经释放测试的旧目录。
3. 后续从同流上一层验证选中检查点继承Actor、Critic、目标网络、优化器与物理含义相同的联合回放。只在三流均通过时增加一个通道；手动worker也须检查全部父阶段门槛，不能绕过。
4. 接管speed前只拟合新输出行，使其近似旧有效风速到转速参考曲线；接管yaw时新输出行精确初始化到旧失配角参考。仅使用旧训练回放状态、保留未参与拟合的状态检查接管误差；原已学习通道和隐藏层逐位不变。目标Actor也按同一规则初始化。
5. 每层每流新增预算16384步、每4096步验证；前三流最多新增49152步，全三层最多147456步。启动后无全随机动作预热，前512步采样但不更新，采用衰减的小噪声，避免破坏已有策略。
6. 沿用平均验证RMSE≤400 kW、最差场景≤500 kW、最终/选中≤1.25，且验证选中优于本层初始、选中步数>0；任一流失败停止晋级。新增通道初始验证误差超过父阶段选中值的1.05倍时记录接管失败并停止该层。
7. 训练目标2.6/3.2/3.8 MW；新验证目标2.85/3.45 MW，新测试目标2.75/3.35/3.85 MW；新的风轨迹episode命名空间不重用20261022测试。压力场单列，测试只在本轮策略和阶段结果全部冻结后开启。
8. P/PI仍为桨距功率反馈加偏航/转速调度，共用执行器。扩展权限后称完整方案对照；同时回放同流父策略。父子阶段训练预算累计不同，不把均值变化全部归因于新增通道。
9. 保留所有接管审计、检查点、阶段门槛、失败结果与归一化。新模块及新协议放本目录及configs；产物沿用experiments/YYYYMMDD_描述，不覆盖或清理旧文件，不自动推送GitHub。

本轮只声称冻结代理模型内的软件和控制能力，不作真实风场精度、全局可达性或稳定优势承诺。

## 实现与运行

入口为 `progressive_random_control.py`，协议为 `configs/progressive_random_control.yaml`；底层复用
`random_wind_training.py` 的训练、统一回放和独立测试。旧协议默认行为保持不变。
`prepare` 会固定旧三流选中检查点、网络与相关代码的 SHA256，并预检三层所有候选训练入口。
`run` 可从回合边界保存点恢复；一旦生成 selection.json，禁止追加训练，测试不能反向晋级。
一次有界运行最多新增147456步；未达门槛时停止本轮并保存失败，不持续加预算直到通过。

```powershell
# 已有目录是本轮原始记录；重新实验应换新目录，不覆盖。
& .\.venv\Scripts\python.exe -B -X utf8 -m optimization_control.maddpg_wind_farm.progressive_random_control all --output optimization_control/experiments/YYYYMMDD_progressive_random_control_new
# 会话中断且尚未冻结 selection/test 时，在原目录恢复。
& .\.venv\Scripts\python.exe -B -X utf8 -m optimization_control.maddpg_wind_farm.progressive_random_control run --output optimization_control/experiments/YYYYMMDD_progressive_random_control_new
# 已冻结实验只能评估/回放，不继续训练。
& .\.venv\Scripts\python.exe -B -X utf8 -m optimization_control.maddpg_wind_farm.progressive_random_control replay --output optimization_control/experiments/20261023_progressive_random_control --stage pitch --run-id 0 --replay-output optimization_control/experiments/YYYYMMDD_progressive_replay_new
```

每个阶段的目录为 `{stage}_run_{run_id}/segment_NNN/`，stage依次为pitch、pitch_speed、all。
归一化仍使用原15维观测与三维动作；每个检查点metadata增加内部lineage，权重格式version=1不变。
lineage记录父检查点、累计预算、继承回放/更新数、新通道拟合误差及父策略在新验证集上的分数。
`handover.json` 记录初始化质量；`stage_gates.json` 记录是否允许下一层。
`metrics.csv` 的additional_steps表示本层新增预算，cumulative_steps表示所承接路径的累计训练步数。
回放缓冲区达到32768条后循环覆盖，审计的保留转移条数不能当作全部历史采样数。

## 后台转速调度的依据与边界

`speed_per_wind_rad_m=0.11114035087719298` 数值上等于 `1.267/11.4`。
11.4 m/s与12.1 rpm（约1.267 rad/s）可参考Jonkman等，2009，
[NREL/TP-500-38060，表1-1](https://www.nlr.gov/docs/fy09osti/38060.pdf#page=13)。
但用额定点比例构造全域线性调度、采用0.6 rad/s下限，均为本项目的联调设置。
报告最低转速为6.9 rpm（约0.723 rad/s），峰值功率系数对应叶尖速比为7.55，
均不能与当前调度混同。此处不声称复现NREL完整发电机转矩/桨距控制器。
保持叶尖速比可解释转速随风速线性变化的形式，但当前系数尚未标定为最优。
此外，现有合成标签源按入口风速设置其转速特性，后台调度按各机有效风速设置，二者不完全相同。
本轮保持网络与调度不变；不在权限实验中同时修改模型或对照来改善分数。

## 验证

```powershell
& .\.venv\Scripts\python.exe -B -m unittest discover -s optimization_control/tests -p 'test_*.py' -v
```

新增测试覆盖权限顺序、三父流联合门槛、测试冻结锁、训练回放拟合与留出检查、
已学习输出/隐藏层/优化器/回放的保留，以及接管后的保存恢复与下一次更新一致。
测试中的Mock只用于实现正确性；性能结论必须引用本轮冻结十二输入模型上的实际训练结果。

## 2026-10-23 实测：仅桨距阶段

实验目录为 `optimization_control/experiments/20261023_progressive_random_control/`。
从旧三流各16384步的选中策略承接，新增三流各16384步，共49152步；累计每流实际采样32768步。
验证/测试风轨迹和目标已换新，因此下表是同一新验证集上的前后对照，不能与旧实验的均值直接相减。

| 训练流 | 继承时平均RMSE / kW | 选中平均 / kW | 选中最差 / kW | 本层选中步数 | 终点/选中 | 通过 |
|---|---:|---:|---:|---:|---:|---|
| 0 | 389.70 | 349.90 | 504.68 | 16384 | 1.000 | 否 |
| 1 | 343.80 | 325.91 | 499.69 | 12288 | 1.110 | 是 |
| 2 | 318.42 | 297.33 | 481.13 | 8192 | 1.007 | 是 |

整体2/3通过，未晋级到pitch_speed或all。第0流失败场为ramp、2.85 MW，
最差误差超过原500 kW门槛4.68 kW；虽接近仍保留失败判定。
三流平均均改善，后期仍有波动；不能把验证选中策略当作每次训练的稳定终点。

另用第0流选中策略的训练回放检查接管初始化，不运行新增权限环境，也不训练新增通道。
在隐藏层和已学输出行逐位保持不变时，六个Actor/目标Actor的转速拟合留出最大误差
为0.25975–0.39542（归一化动作），超过0.05门槛；偏航固定参考可精确初始化。
该证据说明当前单行转速初始化尚未就绪，不能把单元测试的Mock成功外推到真实训练权重。
即使后续桨距通过，仍须先通过接管质量检查才能进入转速训练；初始化失败将保存零新增步数的失败记录。

训练步骤和源文件由config.yaml固定；每层的候选入口预检以 `{stage}_wind_preflight.csv` 为准。
共享辅助函数生成的 `training_wind_preflight.csv` 仅保留最后预检的一层，不代表已执行该层。

冻结后的审计与图表命令：

```powershell
& .\.venv\Scripts\python.exe -B -X utf8 -m optimization_control.maddpg_wind_farm.verify_progressive --output optimization_control/experiments/20261023_progressive_random_control
& .\.venv\Scripts\python.exe -B -X utf8 -m optimization_control.maddpg_wind_farm.progressive_figures --output optimization_control/experiments/20261023_progressive_random_control
```

`verification.json` 检查初始化与父策略状态一致、检查点恢复后动作/噪声/下一次更新一致、
训练入口与预检逐条一致、测试指标从保存轨迹复算一致，并给出下一通道的离线拟合就绪情况。
下一通道拟合检查只在内存副本上操作，不增加训练权限、不写回检查点。
图表为 `progressive_validation.png` 与 `progressive_test_families.png`，解释存 `figure_notes.md`；
全部由Python/Matplotlib绘制，没有使用AI图像生成。

独立测试在全部选模和阶段判定冻结后开启，常规结果如下。±为三个训练流的样本标准差，
不代表物理精度或统计显著性；P/PI没有随机训练方差。

| 控制器 | 常规测试RMSE / kW |
|---|---:|
| 继承前策略 | 359.92 ± 34.42 |
| 本轮验证选中策略 | 338.19 ± 23.82 |
| 本轮终点策略 | 342.94 ± 24.71 |
| P组合基线 | 504.87 |
| PI组合基线 | 399.61 |

选中策略的平稳/慢变/阵风误差分别为342.09/401.67/270.82 kW，
PI分别为404.78/443.56/350.51 kW。低风高目标压力场仍较弱：
选中MADDPG为1607.95±143.00 kW，P/PI均为1383.30 kW。
常规测试均值改善不替代验证晋级门槛；压力场不混入常规均值。
MADDPG独立输出三机桨距，P/PI采用共同功率误差产生统一桨距参考，控制结构不同，
结论仅为当前实现的完整方案对照，不声称相同调参预算下的普遍算法优势。

核对结果：136项模块测试通过；三流初始化的网络、目标网络、优化器、回放和RNG与父检查点一致；
九个初始/选中/终点加载检查的动作、噪声及下一次更新完全一致；
384个实际训练入口逐条重生成与预检SHA256一致；98304条保留转移的执行器、奖励及终止掩码审计通过。
300条独立测试RMSE从38400行保存轨迹复算，最大差为0；28个固定源文件/模型/检查点摘要一致。
新进程在 `20261023_progressive_random_replay/` 重放第0流选中策略及fixed/P/PI，
80条指标、10240行轨迹与冻结测试完全一致；未新增训练或修改检查点。
三流下一转速头离线拟合的最大留出误差分别为0.39542/0.30365/0.33908，均未通过；
这些检查只修改内存副本，未开启下一权限。

本轮有界续训与评估已结束，完整三通道学习尚未完成。下一步先改善仅桨距慢变场景的最差误差，
并修正“只改一行就能匹配后台调度”的初始化假设，再用新的冻结协议检验晋级。
可优先研究保持原MLP结构的联合蒸馏，以旧桨距动作留出误差约束隐藏层调整；这仍需实际验证，
当前未实现或宣称成功。涉及改变转速动作语义的残差控制方案另行提出，不能与当前绝对参考混用。
