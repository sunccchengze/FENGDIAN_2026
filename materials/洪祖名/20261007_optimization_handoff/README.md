# 2026 年 10 月 7 日优化控制完整交付

本目录归属优化控制模块洪祖名。本次用户授权提交独立分支，没有合并 main 或替代团队审阅。

文件约定：任务说明.docx 面向人，同名 Markdown 为内容镜像；readme.md 面向 AI；manifest.json 和 SHA256SUMS.txt 记录归档来源和完整性。archives 中 task_bundle.zip.001 等为本轮 ZIP 的顺序字节分片，其他 partNN.zip 为独立历史归档。每卷小于 95 MiB。既有材料不覆盖、不删除。

- [给 AI 的接手说明](ai/readme.md)
- [给人的任务说明](任务说明.docx)
- [任务说明内容镜像](任务说明.md)
- [全部优化工作索引](../../../optimization_control/WORK_INDEX.md)
- [全部归档清单](manifest.json)
- [传输校验和](SHA256SUMS.txt)

代码及报告位于仓库根 optimization_control。全部成果归档保存原字节；GitHub 上的导航副本将本机路径改成项目相对路径，并在 source_snapshot_manifest.json 中记录源与副本 SHA256。历史记录与权重元数据中的原路径通过回放入口在内存重定位。

从仓库根执行 python tools/unpack_optimization.py --handoff materials/洪祖名/20261007_optimization_handoff --output optimization_handoff_restored；加 --all-history 可恢复全部历史成果。工具验证每卷及每个文件，不覆盖已有目录。

当前结果仅属于固定 9 m/s、方向 0、TI 0.1 的合成迁移联调模型。软件流程已验证，多目标可靠性、后期退化与真实精度尚未验收，失败实验保留。以最新报告的限制为准，旧 PPO 优势数字不作为当前结论。

2026-10-08 已核验首次完整上传提交 84d6f4b：远程目录树与本地审查版本一致，main 未变。详见 [上传核验记录](upload_receipt.json)。本分支采用普通 ZIP 历史分卷；本地另有压缩传输试验，未替换本分支归档。

## 2026-10-21 · 并入主线后的状态与一处清单订正

本节由孙承泽在吸收分支时追加，只补「现状 + 订正」，**不改上文 10-07 / 10-08 的历史陈述**——那些句子描述的是当时的时点状态。

- **已并入主线**：本目录随 `codex/optimization-handoff-20261007`（`84d6f4b` + `782368a3`）以合并提交吸收进会话分支并进入 `main`（PR #17，2026-10-21）。上文「本次用户授权提交独立分支，没有合并 main」与「main 未变」自此为历史记录。
- **订正 `SHA256SUMS.txt` 共 3 条条目**：逐条 `sha256sum -c` 时，66 条里 `manifest.json` 与 `任务说明.md` 两条**在分支上就与仓库字节不符**（其余 64 条通过）——原因是导航副本重写本机路径后未回写清单。**这两个文件本身一字未改**（字节与分支 tip `782368a3` 一致）。第 3 条是本文件 `README.md`：本次在文末追加本节后，它的 sha256 必然变化，按新字节登记。

  | 文件 | 清单原值（分支 tip 上的值） | 现值 | 原因 |
  |---|---|---|---|
  | `manifest.json` | `40cb05e973d69f0ad376d21f05308adb35a22dc571a9a1c87433a6a81665a4fa` | `019587ec2f5e6d7ef663260c06a40f4c8fb17e6b7880ad5c749c2f53107e2d9a` | 分支上即不符 |
  | `任务说明.md` | `970b4fab102ff4d178737738aa0c44f45b014bb3d8a9395b1c1e9a0f6a06f098` | `4e6cad5aa30096c6b6a508985ac57487aebee52883b43ee58d769d44af7e1a30` | 分支上即不符 |
  | `README.md` | `（原为 10-07 版本）` | 见 `SHA256SUMS.txt` 现值 | 本节追加后更新 |

  `verification.json` 里的 `checksum_manifests_checked: 1` 是 2026-10-07 的核验记录，保留原样、不回填。订正过程见 [`docs/audits/2026-10-21_分支吸收与合并审计.md`](../../../docs/audits/2026-10-21_分支吸收与合并审计.md)。
- **体积**：本目录 **≈1.01 GiB**（1,087.6 MB / 67 个文件，其中 `archives/` 58 卷、最大单卷 80 MiB）。它是当前仓库最大的单目录，存储口径的争议已登记到 [`materials/README.md`](../../README.md) §7。
- **未通过我复跑的部分**：本机无 `torch`，`optimization_control/tests/` 中 7 个直接或间接 `import torch` 的测试模块未执行；其余 48 项 `unittest` 全通过（详见审计 §4）。
