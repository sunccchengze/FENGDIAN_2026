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
