# 厉今飞 · 项目负责人 · AI 模块（神经网络 / PINN）· 个人材料与交付件

> 本目录放**厉今飞本人**制作或负责解释的文件。2026-09-21 整理时，从 2026-08-08 的 FLORIS 交付包中把厉今飞训练的神经网络部分按作者解压到这里。

## 目录一览

| 文件 / 目录 | 日期 | 性质 | 原路径 | 说明 |
|---|---|---|---|---|
| `厉今飞——风电场项目个人工作总结与答辩素材_截至20260918.docx` | 2026-09-18 | 源文件 | 本目录（原有） | 项目负责人兼 AI 模块负责人的工作总结：技术路线梳理、组会筹备、功率预测代码原型、尾流 PINN 论文研读、多风机 PINN 本地复现、POD + 小型网络路线评估 |
| [`20260808_功率预测神经网络基线/`](20260808_功率预测神经网络基线/) | 2026-08-08 | 交付快照（解压自袁夫达的 `floris(1).zip`） | `viz/_archive/019fd504-static-site-line/20260808/floris(1).zip` → `floris/output_*/{train_wind_farm_model.py, wind_farm_results/}` | 在袁夫达 GCH / CC 各 1224 条样本上训练的多层全连接功率预测网络（Keras） |

## 归属依据

同日群聊纪要（[`materials/集体/20260808_群聊纪要_…md`](../集体/20260808_群聊纪要_FLORIS数据·神经网络选型·导师意见.md)）：「……然后厉今飞用数据训练了一个简单的神经网络」，以及厉今飞对李良星老师的正式答复（6 维输入含风向正余弦周期编码 + 二阶谐波；隐藏层 Swish、输出层 Sigmoid 以在结构上限制 0–5 MW；三机功率求和保证守恒）。`train_wind_farm_model.py` 中的网络结构与该答复一致：`Normalization → Dense(64, swish) → Dense(128, swish) → Dense(64, swish) → Dense(3, sigmoid) → 求和`。

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

训练数据本身（`training_data_gch.csv` / `training_data_cc.csv`）在 [`materials/袁夫达/20260808_FLORIS数据生成/extracted/`](../袁夫达/20260808_FLORIS数据生成/extracted/)；原始 zip 也在袁夫达目录原样保留。

洪祖名随后在同一数据上做的对比（[`materials/洪祖名/20260808_代理模型优化交付/`](../洪祖名/20260808_代理模型优化交付/)）以本目录的 Keras 模型为「厉今飞 MLP（基线）」：farm MAE 86.5 kW（GCH）/ 103.1 kW（CC），R² 0.99906 / 0.99871。

## 未在仓库中的内容

工作总结 docx 中提到的**功率预测训练 Notebook、两篇尾流 PINN 论文译文、多风机 PINN 开源项目的本地修改**均不在本仓库，需要厉今飞本人通过 PR 提交（大文件先讨论）。

## 分工口径

根 `README.md` / `CONTRIBUTING.md` / `docs/14` 曾把厉今飞写成「基线数据和数据口径」。2026-09-21 用户裁定以申请书封面与本人工作总结为准——**项目负责人兼 AI 模块负责人**（神经网络 / PINN / 降阶与代理模型路线）——三处治理文档已按 [`ADR-2026-002`](../../docs/decisions/ADR-2026-002-五人分工表以申请书与成员自述为准.md) 同步修订。
