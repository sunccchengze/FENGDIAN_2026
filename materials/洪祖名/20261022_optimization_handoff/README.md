# 2026年10月22日优化控制与中期答辩交付

归属优化控制模块洪祖名。当前交付在已合入main的历史成果上增量补齐新版十二输入模型适配、随机入口训练、冻结评估与7张Python图表；不重训或覆盖旧实验。

- [简洁任务说明](任务说明.docx)
- [任务说明文字镜像](任务说明.md)
- [详细接手说明](ai/readme.md)
- [全部优化工作索引](../../../optimization_control/WORK_INDEX.md)
- [本轮结果报告](../../../optimization_control/maddpg_wind_farm/RANDOM_WIND_TRAINING.md)
- [答辩图表及逐图讲稿](../../../optimization_control/maddpg_wind_farm/MIDTERM_FIGURES.md)
- [原始产物清单](manifest.json)
- [ZIP分片校验和](ARCHIVE_SHA256.txt)
- [移动目录验证](verification.json)
- [历史完整成果](../20261007_optimization_handoff/README.md)

本目录archives是本轮单个ZIP的顺序字节分片，每片小于100 MB，使用仓库tools/unpack_optimization.py恢复。模型及所有原始字节在ZIP内，代码和结果导航副本的路径适配记入source_snapshot_manifest.json。旧归档和团队其他模块保持不变。

当前常规测试选中策略449.72±40.11 kW，初始1083.62、P552.37、PI477.54；第0流、慢变和低风压力场仍弱于PI，未通过精度门槛。此为代理模型的软件联调结果，不是真实风场收益或预测精度结论。审阅前不合并main。

> **仓库侧追加（非作者正文）**：`archives/task_bundle.zip.001–003`（163.3 MiB）按 [`ADR-2026-003`](../../../docs/decisions/ADR-2026-003-大交付包存储口径.md) **不入 git**，整包存于 Release `intake-2026-10-22` 的 `_20261022.zip`（171,202,920 B）。原 `SHA256SUMS.txt` 的校验对象是交付方原始包、且仓库内副本做过路径归一，故改名为 `ARCHIVE_SHA256.txt` 并加前言说明，避免门禁按「本地必须存在」逐条校验。本目录其余文件已随分支吸收进 `main`（见 [`docs/audits/2026-10-22_分支收口与合并审计.md`](../../../docs/audits/2026-10-22_分支收口与合并审计.md)）。正文「审阅前不合并main」为交付当时状态，本目录其后已并入 main。另：交付方原名 `readme.md` 与本索引 `README.md` 只差大小写，在 Windows/macOS 检出时会互相覆盖，2026-10-22 已改名为 `接手说明.md`（内容未动；`manifest.json` 内仍记原名 `readme.md`，以原始包为准）。
