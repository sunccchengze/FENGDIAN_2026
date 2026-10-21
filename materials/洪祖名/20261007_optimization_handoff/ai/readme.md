# 三机 MADDPG 逐级控制验证 AI 接手说明

本包对应 2026-10-07 已完成任务：先分别验证仅桨距单目标学习，再验证多目标，最后开放转速和偏航。原成果提交为 `042c634`。先阅读本文和 `任务说明.docx`，再读 `optimization_control/WORK_INDEX.md` 与 `maddpg_wind_farm/FIXED_CURRICULUM.md`。默认接手动作是查看记录或回放已保存策略，不自动重训、不继续调参。

## 事实与适用范围

- 三台机沿直线等间距。演示间距 378 m、轮毂高度 90 m 是联调假设，不宣称队友真实机位。
- 当前实际网络是九个控制输入，按每台机 yaw、pitch、rotor_speed 交错排列；队友层的单位为 deg、deg、rpm。优化物理接口内部为 rad、rad、rad/s，适配器负责顺序和单位转换。
- 网络输出固定为 `[P1,P2,P3,Ueff1,Ueff2,Ueff3]`，单位为 W、W、W、m/s、m/s、m/s。不要再把目标功率当作 PINN 输出。
- 固定风速 9 m/s、方向 0 rad、TI 0.1。外层仍有 12 个物理输入，但前三个环境量仅用于固定上下文检查；不能据此说网络已学习风速、风向、TI 的变化。
- PINN 是队友冻结主体加合成 Mock 标签训练新增参数的联调副本。不是经真实仿真数据标定的物理模型。`pinn/` 只包含加载与来源核查必需文件，归属队友。
- MADDPG、P、PI 共用执行器。偏航执行器更新机舱朝向，模型输入是相对来流的失配角。禁用通道保持初始运行点。
- 随机入口生成器属于此前外层环境成果；不能直接施加给本轮固定工况网络。

## 已完成与未通过

本轮 12 次训练合计 245760 步。仅桨距单目标 2.5/3.5/4.5 MW 的选中策略末段 RMSE 为 28.73/1.23/5.13 kW，均学到有效跟踪。4.5 MW 的最终策略全程 RMSE 为 189.44 kW，选中策略为 7.46 kW，后期退化仍存在。

多目标选中策略独立测试全程 RMSE：pitch 169.75±9.17 kW；pitch+speed 172.89±5.33；yaw+pitch+speed 189.81±15.37。±为三个训练种子的样本标准差。验证门槛通过数依次为 2/3、2/3、1/3，均未达到全部种子通过。

原晋级链在 multi_pitch 失败处停止；转速和偏航是另两项新冻结协议的独立能力实验。未修改失败判定或放宽门槛。pitch 与后两项预算/测试目标不同，不直接归因；后两项同预算同目标配对，加入 yaw 三次均变差。PI 的最差末段误差更小，不能只用全程平均声称 RL 全面更优。

26 项相关软件测试和全部保存训练回放的约束审计通过。软件正确性通过与策略稳定性/真实精度通过是不同结论。

## 文件入口

| 位置 | 内容 |
|---|---|
| `optimization_control/maddpg_wind_farm/fixed_curriculum.py` | 本轮训练、验证选模、冻结测试、恢复和审计入口 |
| `optimization_control/maddpg_wind_farm/handoff_replay.py` | 随解压位置解析历史路径并回放，模型不变 |
| `optimization_control/maddpg_wind_farm/configs/fixed_*.yaml` | 冻结协议，主种子 42 |
| `optimization_control/experiments/20261007_fixed_pinn_curriculum/` | 单目标与多目标仅桨距 |
| `optimization_control/experiments/20261007_fixed_pinn_pitch_speed_probe/` | 桨距和转速 |
| `optimization_control/experiments/20261007_fixed_pinn_all_probe/` | 三通道 |
| 每个实验的 `selection.json` | 初始、验证选中、最终权重、验证指标与 SHA256 |
| 每个实验的 `test/` | 独立测试明细、功率轨迹与汇总 |
| 每个训练 `segment_000/normalization.json` | 观测缩放与控制权限 |
| `optimization_control/experiments/20261007_fixed_pinn_demo_checked/model/` | 本轮实际联调模型与训练来源报告 |
| `manifest.json` | 文件归属、大小、原字节 SHA256 |

本轮 ZIP 包含每次训练的初始/选中/最终完整检查点，没有打包全部中间检查点。全部历史成果分卷另包含剩余中间检查点、以前的实验、PPO 模型与运行记录。原始文件未被覆盖或删除。

## 依赖

参考环境为 Python 3.12。已有环境的冻结依赖位于 `optimization_control/requirements.txt`；TensorFlow 兼容依赖位于 `maddpg_wind_farm/requirements_pinn_demo.txt`。不要安装到全局环境。需要在导入 NumPy、Torch、TensorFlow 之前激活 `.venv/pinn_tf216`，本轮入口已经处理这一顺序。

新电脑准备示例，均在解压根目录执行：

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r optimization_control/requirements.txt
& .\.venv\Scripts\python.exe -m pip install --target .venv/pinn_tf216 -r optimization_control/maddpg_wind_farm/requirements_pinn_demo.txt
```

原冻结依赖包含历史开发组件；若包源无法提供某个版本，先定位缺失项并记录差异，不擅自换模型版本或绕过检查。单纯查看 CSV/报告不需要上述依赖。

## 换路径回放

历史配置和权重元数据保留生成时的路径以保证原始记录完整。请通过随包入口在内存中重定位，避免直接使用历史绝对路径。只加载清单内通过 SHA256 校验的权重。

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m optimization_control.maddpg_wind_farm.handoff_replay --root . --experiment 20261007_fixed_pinn_curriculum --stage multi_pitch --run-id 1 --checkpoint selected --output replay_pitch_run1
& .\.venv\Scripts\python.exe -X utf8 -m optimization_control.maddpg_wind_farm.handoff_replay --root . --experiment 20261007_fixed_pinn_curriculum --stage single_pitch --run-id 0 --target-w 4500000 --checkpoint selected --output replay_single45_selected
```

`--checkpoint initial/selected/final` 可检查初始、选中、终点差异；输出目录必须尚不存在。每次生成同权限 MADDPG、P、PI 的指标和轨迹，不训练、不改变策略、不重新选模。后两组分别使用对应 experiment 与 stage `multi_pitch_speed` / `multi_all`。

本次没有因打包而重新执行 245760 步训练。要重训时，先复制并重定位源实验 `training/config.yaml` 的 backend 路径及 `data/metadata.json` 的 source_hashes 键，保留其对应源文件 SHA256；使用新的输出目录并事先声明协议。不要覆盖已释放测试的实验或降低门槛。

## 从 GitHub 获取完整产物

GitHub 分支的代码位于 `optimization_control/`；交付文件位于 `materials/洪祖名/20261007_optimization_handoff/`。本轮大 ZIP 以 `task_bundle.zip.001` 等顺序字节分片保存；历史 `*_partNN.zip` 是可独立解压的 ZIP，不是字节分片。

下载分支后，可校验、合并并解压本轮包：

```powershell
python tools/unpack_optimization.py --handoff materials/洪祖名/20261007_optimization_handoff --output optimization_handoff_restored
```

加 `--all-history` 恢复全部历史成果。工具拒绝已有输出目录，检查所有相关归档和解压文件的 SHA256；可用任意具备标准库的 Python，不依赖训练环境。`manifest.json` 与 `SHA256SUMS.txt` 是传输完整性依据。

## 下一步与边界

优先修复仅桨距多目标的中间目标与种子差异，并保留 4.5 MW 单目标后期退化回归；之后再推进可靠通道扩展。没有用户继续研究的指令时，不自动启动训练。正式 PINN 或随机风训练需要新的适用域确认，不把本轮合成联调结果移植成真实结论。

GitHub 上传只建立授权分支，没有合并 main 或替代队友审阅。全部历史工作的导航见 `optimization_control/WORK_INDEX.md`；失败实验和撤回结论同样保留。
