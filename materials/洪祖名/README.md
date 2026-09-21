# 洪祖名 · 优化控制模块 · 个人材料与交付件

> 本目录放**洪祖名本人**制作或负责解释的文件。2026-09-21 整理时，两份历史交付件从 `viz/` 迁入（`git mv`）。
>
> 📄 **Markdown 镜像**：本目录每份 docx / pptx / pdf 旁边都有同名 `.md`，由 `tools/markitdown_sync.py`（microsoft/markitdown）自动转换，首行带 `markitdown-mirror` 标记；它是**只读副本，以原文件为准**，原文件更新后重跑脚本即可刷新。

## 目录一览

| 文件 / 目录 | 日期 | 性质 | 原路径 | 说明 |
|---|---|---|---|---|
| `洪祖名——工作记录.docx` | ≤2026-09-19 | 源文件 | 本目录（原有） | 单机 PPO 预研（T1）、T1-R 基线修复、准静态软件闭环（T2→T2.5→T4a）工作记录 |
| [`20260808_代理模型优化交付/`](20260808_代理模型优化交付/) | 2026-08-08 | 交付快照（解压件） | `viz/_archive/019fd504-static-site-line/20260808/代理模型优化交付_20260808.zip` | FLORIS 功率代理模型机器学习优化：XGBoost / GPR / MLP / 两阶段 四模型 5-fold CV + Optuna，选定 XGBoost |
| [`20260810洪/`](20260810洪/) | 2026-08-09/10 | 交付快照 + 复现 | `viz/20260810洪/`（目录名原样保留） | 单机 PPO 功率需求跟踪闭环控制交付 + 可视化侧复现 |

## 20260808_代理模型优化交付/

归属依据：同日群聊纪要（现 [`materials/集体/20260808_群聊纪要_…md`](../集体/20260808_群聊纪要_FLORIS数据·神经网络选型·导师意见.md)）末行「洪祖名的工作成果是：代理模型优化交付_20260808.zip」；包内 `优化工作说明.md` 抬头「提供：优化控制模块（Codex）」。

| 路径 | 说明 |
|---|---|
| ~~`代理模型优化交付_20260808.zip`~~ | 原交付包（19 个文件，sha256 `552a44c3ea7be549513f243e1a38b918487be713adb7036c6b38decec4d7f4fb`）。**2026-09-21 按用户决定只保留解压件**：19 个文件逐条与 zip 内容 sha256 核对一致后删除 zip；原件可从提交 `c92ae9b` 的本路径取回 |
| `extracted/优化工作说明.md` | 做了什么 / 结果 / 交付物清单 / 给袁夫达、厉今飞的建议（**强烈建议补偏航维度数据**） |
| `extracted/final_models/` | GCH / CC 各三台机的 XGBoost 原生 JSON + metadata |
| `extracted/evaluation/` | 基线复现指标、5-fold CV 对比、Optuna 最优超参、残差图 |
| `extracted/scripts/` | `data_loader.py`、`keras_model.py`、`optuna_tune.py`、`stage3_analysis.py`、`train_and_eval.py` |

关键结论（来自 `优化工作说明.md`，未经本仓复算）：XGBoost 将 farm 功率 MAE 从厉今飞 MLP 基线的 86.5 / 103.1 kW 降到 7.79 / 10.49 kW（GCH / CC），R² > 0.99996。

## 20260810洪/

| 路径 | 作者 | 说明 |
|---|---|---|
| `单机PPO功率跟踪交付_20260809.zip`（原名带 `(1)`） | 洪祖名 | 原交付包（sha256 `c4c0bb4cbc5ee7d6dfdb7e52c2bf54556cc2d6fd519d3b53f85b8ff81d01fe92`）。**按用户 2026-09-21 决定保留**（不适用「只留解压件」规则）：包内 5 个文件中 `train.py` / `eval.py` / `demo.py` 与 `extracted/` 相同，但 `simplified_turbine_env.py`（1180 B 原版）只存在于 zip 内，`model/ppo_tracking_v3_seed42.pt` 在 zip 内为 0 字节而 `extracted/` 中是 8.10 复现出的权重。**注意**：包内 `model/ppo_tracking_v3_seed42.pt` 为 0 字节占位，`train/eval/demo.py` 为 526 B 存根 |
| `组会汇报_单机PPO功率跟踪.md`（原名带 `(1)`） | 洪祖名 | 汇报稿：接口契约 `[u_inf, yaw, power, target] → Δyaw`，指标 MAE < 1.2%、调节 < 0.8 s |
| `extracted/simplified_turbine_env.py`、`train.py`、`eval.py`、`demo.py` | 洪祖名（env 经可视化侧微调） | 环境与脚本 |
| `extracted/ppo_repro_train.py`、`ppo_repro_eval.py`、`requirements-ppo.txt` | 可视化侧（孙承泽的 Agent，2026-08-10） | 依据交付文档忠实复现训练与 200 回合评测（见 `viz/.learnings/AUDIT_20260810.md` §第八轮） |
| `extracted/model/ppo_tracking_v3_seed42.pt`（55,420 B）、`ppo_repro_v1_nonconverged_DONOTSHIP.pt` | 复现产物 | 前者是复现后的可用权重；后者是未收敛对照，禁止对外使用 |
| `extracted/metrics_repro.json`、`ppo_eval_traces.json` | 复现产物 | 稳态 MAE 0.523%、平均调节时间 0.944 s、95 分位 1.805 s（seed 42，200 回合） |

`viz/generate_nature_figures.py` 与 `viz/generate_nature_figures_extended.py` 读取本目录的 `extracted/ppo_eval_traces.json`（fig9 / fig17），路径已在 2026-09-21 改为 `../materials/洪祖名/20260810洪/…`，在 `viz/` 下运行即可。

## 未在仓库中的内容

`洪祖名——工作记录.docx` 提到的 `environments/plant_model.py`、`config.yaml`、`test_baseline.py` 等 T1-R / T2 代码**不在本仓库任何位置**，需要洪祖名本人通过 PR 提交。
