# 优化控制完整接手说明 2026年10月22日

本文件面向接手的AI或开发者。先理解任务边界，再运行已有回放；不要看到未通过的门槛就自动重训、放宽门槛或修改冻结测试。

## 一 本包与全部历史工作的关系

本轮ZIP保存当前优化代码、项目上下文、2026-10-22的全部实验文件、必要的队友加载依赖、模型、策略、归一化、图表和失败记录。目录保留项目相对路径，原始字节由manifest.json记录；不包含虚拟环境、凭据、队友原始数据、完整PINN交付及无关目录。

全部优化工作还包括此前的FLORIS代理模型复现与优化、单机PPO、随机入口生成器、动作映射和执行器、MADDPG稳定性研究、功率可达性与误差分解、固定九输入联调及逐通道验证。总入口为 `optimization_control/WORK_INDEX.md`，实时状态为 `optimization_control/TASKFLOW.md`。

旧成果已随2026-10-07交付进入团队main：最终提交 `782368a31e412ff318595d7166a7e8eae30104fe` 是本次核对时main `83fd589fff9128f2750508e830179b26f074318e` 的祖先，main领先9个提交，旧分支已不存在。本次在最新main上补充新增成果，通过PR交付，保留上轮归档，不重复改写历史。历史包位于GitHub `materials/洪祖名/20261007_optimization_handoff/`；本轮交付位于 `materials/洪祖名/20261022_optimization_handoff/`。

## 二 先读什么

1. `任务说明.docx`：简洁的人类阅读版。
2. `optimization_control/WORK_INDEX.md`、`optimization_control/TASKFLOW.md`：全部工作导航与当前状态。
3. `optimization_control/maddpg_wind_farm/WIND_PINN_INTEGRATION.md`：新版模型来源、接口与固定风学习。
4. `optimization_control/maddpg_wind_farm/RANDOM_WIND_TRAINING.md`：随机入口协议、三流训练、统一对照及失败结果。
5. `optimization_control/experiments/20261022_midterm_figures/图表说明.md`：7张图的意义、建议讲解和适用边界。
6. 需要运行时，先做下述冻结策略回放；不要默认执行训练入口。

## 三 当前接口与物理含义

固定三台风机，沿直线等间距排列。演示机位为 `[0,0,90]`、`[378,0,90]`、`[756,0,90]` m，每机额定5 MW；几何和执行器参数均为联调假设，不是队友标定。

外部12维输入按组排列：`[U_inf, theta_inf, TI, gamma_1,gamma_2,gamma_3, beta_1,beta_2,beta_3, omega_1,omega_2,omega_3]`。单位分别为m/s、rad、无量纲、rad、rad、rad/s。桥接层转换为队友的逐机顺序；网络内部将方向编码为sin/cos，共13个特征。不要再次在外部重复旋转机位或编码方向。

输出为 `[P_1,P_2,P_3,Ueff_1,Ueff_2,Ueff_3]`，单位W和m/s。功率目标人为给定，回合内固定，属于优化任务输入而非PINN输出。

执行器转动机舱朝向psi，实际偏航失配为 `gamma=wrap(psi-theta_inf)`。控制器给参考值，统一执行器施加边界、限速和时间常数；禁止把偏航失配本身当作机舱朝向执行。

当前模型约定域：U为7.5至10.5 m/s，风向为零点附近±0.15 rad及圆周等价角，TI为0.02至0.15，gamma为±0.4 rad，beta为0至0.22 rad，omega为0.6至1.267 rad/s。越界应报错，不通过裁剪输入或输出掩盖问题。

## 四 模型来源与结论边界

队友2026_1021交付含冻结预训练主干和未训练的新增控制连接。优化侧在副本中用4096/512/512合成训练、验证、测试样本拟合新增27106个参数，冻结主干保持不变。运行模型在 `optimization_control/experiments/20261022_wind_pinn_integration/model/`，trained.keras摘要为 `7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`。

包内 `pinn/2026_1021/` 仅为带来源摘要的必要运行依赖，不应宣称为优化侧独立PINN成果；队友原文件不改写。旧九输入版本已搬至 `pinn/2026_1007/`，本轮少量历史兼容回放仍引用旧实验。当前随机入口主回放只使用新版模型。

现在有入口随机性和执行器动态，但没有真实数据标定、完整空间湍流结构、动态尾流验证或全局可达性证书。本项目当前目标是流程跑通；模型内功率跟踪误差不能作为真实预测精度或发电收益。

## 五 已完成的实验

- 新版联调：120轮上限，仅新增参数拟合；MADDPG 2048步短训练，统一P/PI与三通道执行器；新进程3072行回放一致。
- 新版固定风学习：三个仅桨距单目标各16384步，共49152步；低、中目标通过，高目标初始策略仍最优且终点退化。按门槛停止多目标与通道扩展。
- 随机入口训练：三条主种子42派生的独立流，各16384步，共49152步。首层RL仅学pitch；yaw跟风向，转速按有效风速运行曲线，当前/目标Actor均使用同一后台调度。没有启动speed或yaw学习。
- 风况为stationary/ramp/gust；128步、dt=1 s，训练目标2.6/3.2/3.8 MW，验证2.8/3.4 MW，测试2.7/3.3/3.9 MW。每9回合交叉覆盖风况与目标，防止二者一一绑定。
- 背景TI为4%或8%，属于生成器谱参数，不等于每个短回合实测std/mean。Kaimal单点入口不等同于完整TurbSim风场。
- 验证三流均值471.79/444.14/433.65 kW，原定平均400 kW、最差500 kW门槛均未通过，不能声称稳定收敛。

常规18场独立测试，先求每场完整回合RMSE，再对场景取平均；三流均值的均值与样本标准差如下：

| 方法 | 常规平均RMSE kW |
|---|---:|
| 初始MADDPG | 1083.62 |
| 训练后MADDPG | 449.72 ± 40.11 |
| 固定桨距加后台调度 | 1100.34 |
| P加相同后台调度 | 552.37 |
| PI加相同后台调度 | 477.54 |

第0流492.28 kW弱于PI；第1和第2流444.24/412.63 kW较低。慢变中MADDPG为432.08 kW、PI为417.19 kW；低风高目标压力场为1727.89对1383.30 kW。压力场固定7.6 m/s、目标4.4 MW，不计常规均值，也不能称作湍流样本。采样路径功率缺口不是真实全局上界证明。最终检查点与本轮验证最佳一致，不推断更长训练仍然稳定。

## 六 环境与安全回放

包内不附带环境。建议Python 3.11，并使用项目虚拟环境。本轮运行依赖为torch、gymnasium、PyYAML、matplotlib、pandas等；项目原安装版本见 `environment_versions.txt`。TensorFlow隔离依赖由 `optimization_control/maddpg_wind_farm/requirements_pinn_demo.txt` 固定，不要用队友旧requirements覆盖已有RL环境。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r environment_versions.txt
.venv\Scripts\python.exe -m pip install --target .venv/pinn_tf216 -r optimization_control/maddpg_wind_farm/requirements_pinn_demo.txt
```

依赖安装作用于本地虚拟环境，不需要全局安装。依赖清单用于重建；平台、CPU库版本或数值后端不同可能出现浮点差异，严格逐行回放以记录环境为准。

在解压后的项目根目录，执行已冻结第0流策略和fixed/P/PI的20场回放：

```powershell
.venv\Scripts\python.exe -B -X utf8 -m optimization_control.maddpg_wind_farm.portable_random_replay --root . --runtime .venv/pinn_tf216 --run-id 0 --output optimization_control/experiments/replay_from_handoff_run0
```

run-id可用0/1/2，输出目录必须不存在。入口只在内存重定位原绝对路径，校验源文件、冻结模型、场景库和策略SHA256，最后逐行对照已保存测试。每流应有80条指标、10240行轨迹，summary中 `full_trace_equal=true`、`new_training=false`。不得改写原config、selection或模型来“修复”路径。

运行模块测试：

```powershell
.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s optimization_control/tests -q
```

重画答辩图，仅读取冻结数据，不重训：

```powershell
.venv\Scripts\python.exe -B -X utf8 -m optimization_control.maddpg_wind_farm.midterm_figures --output optimization_control/experiments/midterm_figures_reproduced
```

使用Microsoft YaHei、Noto Sans SC或SimHei中文字体。图组有PNG、PDF、SVG和逐图说明，原图不覆盖。

## 七 文件完整性与历史恢复

本地ZIP可直接解压。manifest.json记录每个成员SHA256、大小及来源；SHA256SUMS.txt记录ZIP和远程传输分片的SHA256。ZIP以原字节保存数据，历史绝对路径作为实验记录保留，移动路径由回放入口在内存处理。

GitHub单文件小于100 MB；较大的本轮ZIP拆为archives/task_bundle.zip.001等顺序字节分片，不能单独解压。从仓库根使用既有恢复工具：

```powershell
python tools/unpack_optimization.py --handoff materials/洪祖名/20261022_optimization_handoff --output optimization_handoff_20261022_restored
```

历史全部产物在旧交付包中，按需恢复到另一个新目录：

```powershell
python tools/unpack_optimization.py --handoff materials/洪祖名/20261007_optimization_handoff --output optimization_handoff_20261007_restored --all-history
```

源码根目录的optimization_control为当前完整代码；旧归档为保留的历史字节。两者任务和模型不同，不混用策略、归一化或测试集。GitHub导航副本若进行了路径整理，会在source_snapshot_manifest.json记录源和副本摘要；原始数据以ZIP内字节为准。

## 八 接下来可以做什么

优先诊断慢变跟踪、目标响应和低风高目标下的桨距行为；若改算法，应冻结新协议、预算、验证及独立测试，再做多流与统一P/PI对照。原门槛未通过前，不默认进入转速或偏航学习。真实物理验收依赖仿真或实测数据。

不要删除失败实验、覆盖旧策略、修改队友源交付、裁剪非法输出或将best说成稳定终点。后续提交遵守本地AGENTS和Git工作流；本轮只创建PR，不合并团队main。
