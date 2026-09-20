# 仓库质量检查

`ci/repo_quality.py` 是不依赖第三方包的仓库级检查，目的是尽早发现协作和证据链问题，而不是替代领域审阅。

当前 CI 文件分工：

- `repo_quality.py`：仓库级本地检查，也是 `repo-quality.yml` 的执行内容；
- `workflow-drafts/repo-quality.yml`：待 GitHub 权限恢复后激活的仓库检查；
- `workflow-drafts/twin-quality.yml`：待激活的 `twin` lint/selftest/typecheck/build 检查；
- `qa-gates.yml`：R38 以来的历史 QA 草案，保留供追溯，**不要与 `twin-quality.yml` 同时激活**。

受治理的 Markdown 链接应保持为零断链。`skills/` 和 `viz/` 中存在历史资料引用的边界例外；它们不属于本轮封板/治理文件的强制链接门禁，若要修复需另开 Issue，不能借治理改造顺手重排 `viz/`。

## 本地运行

在仓库根目录执行：

`python3 ci/repo_quality.py`

它会检查：

- 治理入口、模板和导航是否存在；
- 新增 Issue Form 和 PR 模板是否有必要字段；
- 受治理文档中的本地链接是否存在；
- 是否有 0 字节图片；
- 是否有超过安全阈值的大文件；
- 是否有明显的临时版本命名。

大文件只在超过 95 MiB 时阻断；50 MiB 以上先给出警告。已有历史资产不因一次治理改造而被强制重写，但新增大文件必须在 PR 中说明来源、用途和长期存储方案。

本检查不联网，不验证外部 URL，不判断科学结论是否正确，也不把沙箱帧率当成真实硬件性能。
