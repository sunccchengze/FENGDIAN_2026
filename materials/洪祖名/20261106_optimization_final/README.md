# 优化控制最终阶段交付 · 2026-11-06

当前软件版本：冻结三通道组合策略 + NREL 5 MW 参数参考的转速曲线。模型是合成标签联调代理；不是已验证真实风机精度的控制器。

## 最新结果和边界

| 风况 | MADDPG RMSE kW | P RMSE kW | PI RMSE kW |
|---|---:|---:|---:|
| 平稳 | 432.050552 | 549.743291 | 488.041868 |
| 慢变 | 459.626697 | 622.074412 | 532.200097 |
| 阵风 | 454.080321 | 621.766122 | 523.087915 |
| 总体 | 448.585857 | 597.861275 | 514.443293 |

三类平均低于 PI；54 个策略/场景配对中 43 胜、11 负。新规则相比旧规则的 MADDPG 416.210058 kW 退化，不能称换曲线提升绝对精度。本轮为原 18 条已用风的配置回归，不是新未见独立测试。原 400/500 kW 精度门槛未达；新增转速/偏航收益弱，Y1 仍选初始偏航分支，C0/C1 仍是初始转速分支。低风高目标不纳入常规三族成功结论，本轮未新增压力测试。

## 最终版本和历史成果

- 最终运行以 `NREL_THREE_CHANNEL_HANDOFF_20261106.md` 为准，转速参考 `clip((7.55/63)*Ueff, 6.9*2*pi/60, 1.267)` rad/s；旧网络坐标不改，最终命令和执行器使用新边界。
- 三份 Y selected 的偏航选择步为 2048/0/2048；C 转速父选择步 0/0/4096；三个原桨距父分别为 16384/12288/8192 步。
- 独立桨距成果为原 n8 三份冻结策略，入口 `PITCH_N8_AVERAGE_HANDOFF_20261105.md`。它与三通道使用不同父策略和测试，不能拼成同一条收益链。
- 包内保存 10-23 至 11-06 的后续源码、配置、报告、结果和失败记录；早期 PPO、代理优化、九输入及十二输入联调的历史交付已在 GitHub main/既有归档。本包包含现有源码，不重复所有旧权重和旧归档。
- `provenance/source_files.json` 记录四个工作树的提交和原始字节。唯一共用源码差异为 controllers.py：运行副本以 speed 最终版本为准，旧原字节保留在 variants 中。
- `provenance/excluded_training_storage.json` 记录未打包的训练状态、重复缓存；选中依赖优先纳入。没有删除任何原文件；本包保证冻结推理/回放，不保证所有历史中间训练状态可恢复。

## 解压后使用

在解压根目录运行。需要 Python 3.12；CPU PyTorch、NumPy、PyYAML、Gymnasium，以及实际模型回放所需 TensorFlow 2.16 / tf-keras。完整历史依赖见 `optimization_control/requirements.txt`；环境记录见 `environment_versions.txt`。不包含虚拟环境，不安装全局依赖。

```powershell
python -B portable_final.py verify
python -B portable_final.py inference
python -B portable_final.py replay --case 0 --output replay_case0.json
```

若 TensorFlow 等装在独立目录，可加 `--runtime <现有依赖目录>`。verify 仅用标准库；inference 对三份 Y 的保存观测执行冻结推理；replay 默认对三份 Y、P、PI 完整重放一个 128 步回合，逐值比较功率、动作、观测和全部模型输入。每控制器最多 129 行模型输入，不训练、不选模、不改变原实验。本包测试使用 case0，含误差较大场景，并非挑选最优场景。可用 --case 0..17 与 --controllers 选择保存场景。

`portable_final.py` 通过来源路径表重新定位文件，检查来源摘要，并仅在加载依赖时映射路径。不会修改冻结身份、观测归一化、旧锁文件或命令；依赖必须位于包内，缺件报错，不回落到原工作树。

## 文件导航

- `optimization_control/maddpg_wind_farm/NREL_SPEED_REGRESSION_RESULTS_20261106.md`：最终详细结果。
- `optimization_control/maddpg_wind_farm/NREL_THREE_CHANNEL_HANDOFF_20261106.md`：参数、依赖、决策时钟。
- `optimization_control/maddpg_wind_farm/PINN_SPEED_RESPONSE_INTERFACE_20261106.md`：供模型组对接的字段与响应限制。
- `optimization_control/experiments/20261106_nrel_speed_regression/`：180 行旧新指标、90 组新旧配对、54 组新 Y/PI 对照、完整新回合和 Python 图表。
- `verification/`：本次打包核验记录；不改变历史实验结论。

历史协议及记录中的本机路径是原始来源，不应按原路径直接运行旧 prepare/run 命令；新使用入口是包根 portable_final.py。原件保留其字节/SHA；GitHub 导航副本另行转换相对路径，两者不混淆。

交付兼容性修复：沿用团队主线的 weights_only 安全加载，只修复 NumPy 1.26 的 _core 兼容分支；原算法源码字节保存在 provenance/original_runtime。24 项相关单元测试通过，冻结权重与控制行为不变。

历史报告中指向“交付范围说明”的链接表示原目标属于外部运行产物或旧目录。最终必需依赖已在 ZIP 内；未保留的中间权重、训练状态和重复轨迹以包内 excluded_training_storage.json 为准，不承诺所有历史训练可以中断续跑。原始记录及 SHA 不变，导航副本转换了路径；请勿用导航副本的文本字节替代原始锁文件做摘要校验。

最终 ZIP：677,036,471 字节（约 645.67 MiB），已逐项核对 25,003 个成员。SHA256：`6f67a5f4be5b8ccf0ae6ae54e5808206e13c0c5f9b92ec6d7249a8edea3c70f3`。校验清单见 [RELEASE_ASSETS.sha256](RELEASE_ASSETS.sha256)。

校验：25,003 个成员完整字节验证；24 项相关单元测试通过；三份策略冻结动作一致；case0 及移动解压后的 case17 的五控制器完整回放一致。新运行仅用于交付复现，无训练或选模。PR 变更文件使用仓库检查器完成链接、语法、文件大小、大小写冲突与文本检查，0 错误/0 警告。全仓检查在本地稀疏检出下报告未检出的团队文件缺失，因此不宣称全仓门禁通过；本 PR 的变更已单独完整检查。
