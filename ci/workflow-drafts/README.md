# GitHub Actions 工作流草案

这里保存 `.github/workflows/` 的只读工作流草案。当前 GitHub App 没有 `workflows` 权限，直接推送到 `.github/workflows/` 会被远端拒绝，因此这些文件暂不宣称已经在 GitHub 上生效。

重新连接具备 `workflows` 权限的 GitHub 后：

```bash
mkdir -p .github/workflows
cp ci/workflow-drafts/repo-quality.yml .github/workflows/repo-quality.yml
cp ci/workflow-drafts/twin-quality.yml .github/workflows/twin-quality.yml
git add .github/workflows
git commit -m "ci: activate repository and twin quality workflows"
git push
```

激活后，在 GitHub Actions 页面确认两份 workflow 均能触发，并将成功的检查名配置到 `main` 的 branch protection；“文件已存在”“workflow 已触发”“状态检查已成为合并门禁”是三个不同状态。

2026-10-22 审计（AUD-03）补齐了 `optimization-quality.yml`（优化控制 129+7 单元测试）与 `viz-quality.yml`（封板静态站两道门禁）两份草案，四块代码面至此都有对应草案；激活方式与上同。激活前先在本地等价跑通：`python3 ci/repo_quality.py`、`cd twin && npm run verify`、`python -m unittest discover -s optimization_control/tests`（仓库根执行）、`python viz/site/check_contract.py && python viz/site/verify_all_pages.py`。
