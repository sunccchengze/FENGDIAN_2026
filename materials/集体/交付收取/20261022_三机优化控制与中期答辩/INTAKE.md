# 2026-10-22 交付入库记录（十二输入 PINN + 随机入口训练 + 中期答辩 7 图）

> **状态**：**已入库并推送**（2026-10-22）。代码进 `optimization_control/`，材料按主责人归位。
> **口径**：[`ADR-2026-003`](../../../docs/decisions/ADR-2026-003-大交付包存储口径.md) —— >50 MiB 的二进制走 Release 资产，git 只收代码/配置/文档/清单。
> **来源**：用户 2026-10-22 直接上传到会话分支（原提交 `c11627d`，857 文件 / 1,916.4 MB）。

---

## 1. 入库时做了体积裁剪（原样 1,916.4 MB → 79.5 MB）

| 内容 | 原大小 | 处理 |
|---|---|---|
| PINN 包 `Diamond_grid` / `Rectangular_grid` / `Transfer_learning` 的 CFD 与绘图数据 | ≈1,630 MB | **不入库**（`Plots/Data`、`Plots/csv_data`、`data/` 全部跳过；单文件最大 46.5 MB） |
| 优化侧 `experiments/` 的 `.pth` 检查点、`.npz`、>2 MiB 的轨迹 CSV | ≈310 MB | **不入库**（每流 5 个检查点、共 15 个 `.pth`） |
| 重复的 4 个 `.keras` 权重（`pinn/2026_1021` 与上游包逐字节相同，已比对 blob 一致） | 47.9 MB | **只留一份**，上游包仅存代码 |
| 代码、配置、文档、清单、报告、7 张图（PNG/PDF/SVG）、4 个 `.keras` | 79.5 MB | **入库** |

完整原包与两份 zip 仍在 Release `intake-2026-10-22`（sha256 见 [`RELEASE_ASSETS.sha256`](../../集体/交付收取/20261022_三机优化控制与中期答辩/RELEASE_ASSETS.sha256)）。

> **原提交 `c11627d` 已被重做**（`git push --force-with-lease`），本分支历史不再包含那 1.9 GB。
> 若要回看原始上传，见该 SHA 或 Release 资产。

## 2. 装到哪里

| 内容 | 位置 |
|---|---|
| 十二输入 PINN 交付包（16 文件，含 4 个 `.keras` 权重、`build_report.json`、`project_config.json`、`wind_project_config.json`、两个改造脚本） | [`materials/厉今飞/20261021_PINN十二输入交付/pinn_2026_1021/`](../../厉今飞/20261021_PINN十二输入交付/) |
| 上游 PINN 工程代码与说明（`modify_pinn_io.py`、`prepare_pinn_outputchange.py`、`README`、`requirements`、各网格 `.py` 配置） | 同目录 `upstream_repo/`（**不含任何数据与权重**） |
| 优化控制代码（新增 `environments/wind_generator.py`、`wind_pinn_backend.py`、`maddpg_wind_farm/midterm_figures.py`、`tests/test_wind_pinn.py`、`tests/test_random_wind_training.py` 等 34 个文件更新） | [`optimization_control/`](../../../optimization_control/WORK_INDEX.md) |
| 交付说明、任务说明 docx + markitdown 镜像、`PROJECT_STATUS.md`、`CLAUDE.md`、`GIT_WORKFLOW.md`、`AGENTS.md`、`manifest.json`、`environment_versions.txt`、`文献综述_第一次组会.md`、`project_context/` | [`materials/洪祖名/20261022_optimization_handoff/`](../../洪祖名/20261022_optimization_handoff/README.md) |
| 7 张中期图（PNG 220 dpi / PDF / SVG，共 21 个图形文件）+ 逐图讲解 | [`optimization_control/experiments/20261022_midterm_figures/`](../../../optimization_control/experiments/20261022_midterm_figures/图表说明.md) |

## 3. 入库时修的问题

| # | 问题 | 处理 |
|---|---|---|
| 1 | 包内 20 余条相对链接按「仓库根」写死（如 `](optimization_control/TASKFLOW.md)`），放到 `materials/` 下全部断链 | 逐条改为正确层级（`project_context/` 深一层用 `../../../../`，同级文件用 `../../../`） |
| 2 | `文献综述_第一次组会.md` 与 `CLAUDE.md` 指向未随包上传的 `大创申报书/`、`文献/` | 改为锚点 `#`，不假装它们存在 |
| 3 | `任务说明.docx` 缺 markitdown 镜像（materials 规则 9） | 用 `tools/markitdown_sync.py` 生成，22 份镜像全过 |
| 4 | 新包不含 `optimization_control/AGENTS.md` 与部分 `project_context/` 旧文件 | **保持仓库原样，未删**（防「打包漏带」被误当「上游删除」） |

## 4. 三个必答题（用户 2026-10-22 答复后的状态）

| # | 问题 | 现状 |
|---|---|---|
| 1 | 614.8 MB 包与 10-03 的 603.8 MB 是什么关系？ | 用户答「**应该是最新版**」。仓库侧证据支持：包内 `pinn/2026_1021` 的四个 `.keras` 与 `OutputChange/{iochanged_9ms,prepared_9ms,wind_iochanged_9ms}` 一一对应，且多出 `wind_iochanged_9ms`（十二输入版）——**判定为「新增十二输入支线的新版本」，不是同包重打包**。仍待厉今飞一句确认 |
| 2 | 优化侧是否摆脱「风况写死」？ | 用户答「**不知道**」。仓库侧证据：**已摆脱**——`environments/wind_generator.py` 生成 Kaimal 平稳湍流/慢变/阵风，`RANDOM_WIND_TRAINING.md` 记录三流各 16384 步训练。但 10-11 会上他说的「风速/风向/TI 写死配置文件」指的是 `20261007` 那版，**两句话不矛盾，是版本差** |
| 3 | 中期答辩交付里有没有新数字？ | 用户答「**不清楚**」。**有，且不少**：常规测试平均 RMSE 1083.62 → 449.72±40.11 kW（−58.5%）、P 552.37、PI 477.54；验证 471.79/444.14/433.65；十二输入 PINN 低/中目标 18.14/1.69 kW。**这些是「代理模型内」的数字，不是实测发电收益**，引用必须带限定语 |

## 5. 不能对外宣称的四条（与交付包自述一致）

1. 不是真实风场精度，也不是发电收益——入口与标签都是**合成**的；
2. MADDPG 只是**均值**略低于 PI（449.72 vs 477.54），三条训练流中有一条输，慢变（432.08 vs 417.19）与低风压力场（1727.89 vs 1383.30）都输；
3. 只让 RL **学桨距**，偏航与转速是统一后台规则——**不是三通道都学会了**；
4. 十二输入 PINN 的高目标门槛未通过（最终/选中验证误差比 2.306），已按冻结协议**停止晋级**。
