# 厉今飞 · 项目负责人 · AI 模块（神经网络 / PINN）· 个人材料与交付件

> 本目录放**厉今飞本人**制作或负责解释的文件。2026-09-21 整理时，从 2026-08-08 的 FLORIS 交付包中把厉今飞训练的神经网络部分按作者解压到这里；同日晚些时候从孙承泽提供的 `新建文件夹.zip` 收进 8.24 的《模型需求》。
>
> 📄 **Markdown 镜像**：本目录每份 docx / pptx / pdf 旁边都有同名 `.md`，由 `tools/markitdown_sync.py`（microsoft/markitdown）自动转换，首行带 `markitdown-mirror` 标记；它是**只读副本，以原文件为准**，原文件更新后重跑脚本即可刷新。

## 目录一览

| 文件 / 目录 | 日期 | 性质 | 原路径 | 说明 |
|---|---|---|---|---|
| `厉今飞——风电场项目个人工作总结与答辩素材_截至20260918.docx` | 2026-09-18 | 源文件 | 本目录（原有） | 项目负责人兼 AI 模块负责人的工作总结：技术路线梳理、组会筹备、功率预测代码原型、尾流 PINN 论文研读、多风机 PINN 本地复现、POD + 小型网络路线评估 |
| `模型需求.docx` | 2026-08-24 11:28 发到群里并 @袁夫达 | 源文件 · 需求单 | 孙承泽 2026-09-21 `新建文件夹.zip`（群聊截图证实发送人为厉今飞） | 向建模侧提出的 4 条要求：模型完整描述（可配图）、全部参数变量定义、给定初始参数后如何得到结果、需求解的方程与定理顺序——袁夫达 8.30 的《模型与数据来源说明_终版》即对此的回应 |
| [`20260808_功率预测神经网络基线/`](20260808_功率预测神经网络基线/) | 2026-08-08 | 交付快照（解压自袁夫达的 `floris(1).zip`，逐文件 sha256 与包内一致） | `viz/_archive/019fd504-static-site-line/20260808/floris(1).zip` → `floris/output_*/{train_wind_farm_model.py, wind_farm_results/}` | 在袁夫达 GCH / CC 各 1224 条样本上训练的多层全连接功率预测网络（Keras） |

## 归属依据

同日群聊纪要（[`materials/集体/20260808_群聊纪要_…md`](../集体/20260808_群聊纪要_FLORIS数据·神经网络选型·导师意见.md)）：「……然后厉今飞用数据训练了一个简单的神经网络」，以及厉今飞对李良星老师的正式答复（6 维输入含风向正余弦周期编码 + 二阶谐波；隐藏层 Swish、输出层 Sigmoid 以在结构上限制 0–5 MW；三机功率求和保证守恒）。`train_wind_farm_model.py` 中的网络结构与该答复一致：`Normalization → Dense(64, swish) → Dense(128, swish) → Dense(64, swish) → Dense(3, sigmoid) → 求和`。2026-09-21 `新建文件夹 (2).zip` 带回此事的**原始截图**（8/4 发包、8/7 选型说明），转录见 [`群聊记录 8/4`](../集体/聊天记录/群聊记录_2026-07-26至09-20.md#2026-08-04周二--厉今飞发-floriszip) 与 [`8/7`](../集体/聊天记录/群聊记录_2026-07-26至09-20.md#2026-08-07周五--厉今飞网络选型说明)。

## 20260808_功率预测神经网络基线/ 内容

| 路径 | 说明 |
|---|---|
| `output_gch/train_wind_farm_model.py`、`output_cc/train_wind_farm_model.py` | 训练脚本（两份仅数据路径不同）：70/15/15 划分、Adam 1e-3、MSE、L2、EarlyStopping、ReduceLROnPlateau、seed 42 |
| `output_*/wind_farm_results/wind_farm_power_model.keras` | 训练好的模型（各 250 KB） |
| `output_*/wind_farm_results/test_metrics.csv` | MAE / RMSE / R² 测试指标 |
| `output_*/wind_farm_results/test_predictions.csv` | 测试集逐行真值 / 预测 / 误差 |
| `output_*/wind_farm_results/training_history.csv`、`training_curve.png` | 训练曲线 |
| `output_*/wind_farm_results/true_vs_pred_{farm,turbine_1,turbine_2,turbine_3}_power.png` | 预测-真值散点 |
| `output_*/wind_farm_results/model_metadata.json` | 特征、结构、超参元数据 |
| `SHA256SUMS.txt` | 2026-09-21 生成的逐文件 sha256 清单（22 个文件，`sha256sum -c` 格式）；与袁夫达侧的清单合起来即原 `floris(1).zip` 31 个文件，`ci/repo_quality.py` 自动校验 |

训练数据本身（`training_data_gch.csv` / `training_data_cc.csv`）在 [`materials/袁夫达/20260808_FLORIS数据生成/extracted/`](../袁夫达/20260808_FLORIS数据生成/extracted/)；原始 zip（sha256 `68b717ae89b4…`）已按用户决定删除，只保留解压件，取回路径见袁夫达目录 README。

洪祖名随后在同一数据上做的对比（[`materials/洪祖名/20260808_代理模型优化交付/`](../洪祖名/20260808_代理模型优化交付/)）以本目录的 Keras 模型为「厉今飞 MLP（基线）」：farm MAE 86.5 kW（GCH）/ 103.1 kW（CC），R² 0.99906 / 0.99871。

## 相关但放在别处的内容

- **两份 PINN 三机模型交接文档已归位本目录**：[`三台风机PINN模型交接与训练指南.docx`](三台风机PINN模型交接与训练指南.docx)（交接日期 2026-10-03，46,329 B，sha256 `5d8bdce36636…`，附[镜像](三台风机PINN模型交接与训练指南.md)）与 [`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md)（13 章项目说明）。原在仓库根目录（2026-10-04 孙承泽上传，提交 `b65ca49`）；用户说明 `PROJECT_DOCUMENTATION.md` 是**厉今飞 2026-10-04 提交的一个 zip 的总结版**。**2026-10-05 第二轮**按 10-04 群聊截图的归属依据（规则 8：归属以截图发送人为准，发送人 = 厉今飞）`git mv` 到本目录，保留原文件名，并重跑 `tools/markitdown_sync.py` 补上 docx 镜像（全仓镜像 19 → 20）。截图转录见 [`../集体/聊天记录/群聊记录_2026-07-26至09-20.md`](../集体/聊天记录/群聊记录_2026-07-26至09-20.md) §2026-10-04。内容摘要见根 [`README.md`](../../README.md) §「PINN 线（2026-10-03 交接）」；
- 厉今飞 2026-09-14 发到群里的两篇尾流 PINN 论文（Gafoor et al., Phys. Fluids 2025 / 2026）在 [`../集体/参考资料/`](../集体/参考资料/)，附 Markdown 镜像；
- 厉今飞 9.12 的「Fluent 十二问」、9.15–16 的工作安排（会议记录 / 三模型比较 / 先 PINN 后 POD / 个人工作记录周六截止）与 9.16 深夜的 8 GB 显存问题，原文见 [`../集体/聊天记录/群聊记录_2026-07-26至09-20.md`](../集体/聊天记录/群聊记录_2026-07-26至09-20.md)；
- 7.26 的《大创项目假期技术路线.pptx》由厉今飞发出，仓库只有其 Markdown 导出（`../集体/假期前PPT_大创项目假期技术路线.md`）。

## 未在仓库中的内容

工作总结 docx 中提到的**功率预测训练 Notebook、两篇尾流 PINN 论文译文、多风机 PINN 开源项目的本地修改**均不在本仓库，需要厉今飞本人通过 PR 提交（大文件先讨论）。

### 2026-10-05 更新：第三项已有文档，但交付包本体仍未入库

「多风机 PINN 开源项目的本地修改」这项**已有说明文档**（2026-10-03 交接指南 + `PROJECT_DOCUMENTATION.md`，见上节，均已归位本目录），但**代码与权重本体没有入库**。

**2026-10-05 第二轮新增证据**：10-04 00:06 群聊截图（转录见 [`../集体/聊天记录/群聊记录_2026-07-26至09-20.md`](../集体/聊天记录/群聊记录_2026-07-26至09-20.md) §2026-10-04）显示厉今飞发 docx 的同时发了交付 zip，微信显示 **603.8M**，即 `PINNs_multi_turbine_wake_simulation-outputchange.zip`。**该包存在但未入库**；603.8 MB 超过 GitHub 单文件 100 MB 硬限与 Cloudflare Pages 单文件 25 MiB 约束，Git LFS 免费额度（1 GB 存储 / 1 GB 月流量）装得下但流量吃紧。**用户 2026-10-05 裁定：先不处理、维持现状**，本项保持开放，等 9.19 方案 §四 的 PINN 14 天检查点需要复现时再启动存储方式裁定（LFS / 外部存储 / 拆包）。

交接指南 §2 列明的打包内容全部缺失：

| 缺失项 | 用途（据交接指南 §2） |
|---|---|
| `prepare_pinn_outputchange.py`、`modify_pinn_io.py` | 原模型准备、结构改造、训练与预测入口 |
| `OutputChange/prepared_9ms/`（含 `original_frozen.keras` 等） | 原模型导出文件与准备报告 |
| `OutputChange/iochanged_9ms/`（含 `untrained.keras`、`build_report.json`、训练数据模板、结构摘要） | **接收方要训练的待训练模型** |
| `OutputChange/project_config.json` | 由接收方填写真实坐标并核对单位 |
| 原仓库代码 + LICENSE + README | 项目来源、原模型与复现依据 |

**后果**：这份交付当前**无法复现、无法审阅**，只能读文档。它是 9.19 方案「两条并行工作线」中物理线的第一份实质交付，也是 [`../集体/9.19会议——总——风电场项目结题目标与倒排实施方案_20260919.md`](../集体/9.19会议——总——风电场项目结题目标与倒排实施方案_20260919.md) §四「PINN：用可验证的小目标突破」的 14 天检查点所依赖的对象。

**待裁定**：`.keras` 权重（原模型 3,090,200 参数）的体积与入库方式——直接入 git / Git LFS / 外部存储。仓库当前**没有** LFS 配置，且 Cloudflare Pages 有单文件 ≤25 MiB 的硬约束（根 `README.md` §历史选型期基线）。

另注：交接发生在 **2026-09-22 → 10-02 的 12 天空白期**之后（该期间 0 提交、0 材料、0 群聊记录），模型改造的**过程记录同样缺失**，只有 10-03 的结论。见 [`docs/project/TIMELINE.md`](../../docs/project/TIMELINE.md) §6 第 3 项。

## 分工口径

根 `README.md` / `CONTRIBUTING.md` / `docs/14` 曾把厉今飞写成「基线数据和数据口径」。2026-09-21 用户裁定以申请书封面与本人工作总结为准——**项目负责人兼 AI 模块负责人**（神经网络 / PINN / 降阶与代理模型路线）——三处治理文档已按 [`ADR-2026-002`](../../docs/decisions/ADR-2026-002-五人分工表以申请书与成员自述为准.md) 同步修订。
