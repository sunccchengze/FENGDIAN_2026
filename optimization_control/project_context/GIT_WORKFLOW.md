# 本地 Git 项目管理规范

> 适用范围：本项目本地文件目录、Git 暂存区和本地仓库。默认仅本地管理；明确授权的远程交付见第八节。

## 1. 三层模型

| 层级 | Git 对象 | 作用 | 本项目要求 |
|---|---|---|---|
| 本地文件目录 | working tree | 编写代码、文档和实验配置 | 可以处于未完成状态，但不能混入密钥和无关生成物 |
| 暂存区 | index（`.git/index`） | 组成下一次提交的精确快照 | 一次只暂存一个任务，使用明确文件列表 |
| 本地仓库 | commits/refs（`.git/`） | 保存已验证、可回溯的历史 | 每个任务形成一个原子提交，`master` 只保留验证通过的状态 |

暂存区和本地仓库都不是供人工整理的普通目录。不得直接编辑 `.git/`，所有操作通过 Git 命令完成。

## 2. 文件进入仓库的边界

### 默认跟踪

- 源代码、测试代码、项目规范和说明文档。
- 小型配置文件、数据字段说明和模型元数据。
- 每次实验的 `config.yaml`、`metrics.csv`、`summary.txt`。
- 能解释结果来源、参数和复现方法的脚本。

### 默认不跟踪

- `.venv/`、缓存、编辑器状态和系统临时文件。
- 队友原始数据、训练日志、TensorBoard/W&B 输出。
- 模型权重、交付压缩包和可重新生成的图像。
- 密钥、token、密码和任何 `.env` 文件。

具体规则以 `.gitignore` 为准。单文件超过 100 MB 时，无论是否匹配忽略规则，都不得进入 Git。

## 3. 分支模型

- `master`：本地稳定分支，只接收已经验证的任务提交。
- `codex/<task>`：Codex 执行任务时使用的短期分支。
- `<type>/<task>`：人工开发可使用 `feat/`、`fix/`、`exp/`、`docs/` 等前缀。
- 一个任务分支只处理一个目标；验证后使用 `git merge --ff-only <branch>` 快进合并。
- 默认不设置 remote 或上传；用户明确授权的远程交付按第八节执行。

分支名使用小写英文和连字符，例如：

```text
codex/local-project-management
feat/yaw-control-environment
exp/ppo-reward-ablation
docs/final-report
```

## 4. 标准工作流

以下分支、提交和合并流程仅适用于实际修改任务；只读咨询或审查不触发这些操作。

### 4.1 开始任务

```powershell
git status --short --branch
git switch master
git switch -c codex/<task>
```

执行分支切换前，记录工作区和暂存区已有改动，判断是否与本任务重叠；无关改动原样保留，不要求全局干净。仅在会覆盖已有内容、混入其他任务或无法安全隔离时说明具体阻塞，不擅自清理、暂存或提交其他任务。上面的切换命令只在检查通过后执行。

### 4.2 在本地文件目录工作

```powershell
git status --short
git diff -- <file>
```

代码修改运行受影响模块的测试或最小复现；算法性能结论运行对应实验；文档修改检查内容、链接和格式。验证通过后，仅在新改动或新证据需要时扩大或重复验证。实验必须留下固定 `seed=42` 的配置和结果摘要。

### 4.3 精确放入暂存区

```powershell
git add -- <file1> <file2>
git diff --cached --stat
git diff --cached
git diff --cached --check
```

- 默认禁止使用 `git add .`，避免把数据、模型或其他任务的改动一起暂存。
- `git diff --cached --check` 非零退出时停止提交，先处理空白符或冲突标记。
- 提交前再次运行 `git status --short`，确认暂存区只包含当前任务。

### 4.4 写入本地仓库

```powershell
git commit -m "<type>(<scope>): <summary>"
git log --oneline --decorate -5
```

推荐提交类型：

| 类型 | 用途 |
|---|---|
| `feat` | 新功能或新环境 |
| `fix` | 缺陷修复 |
| `exp` | 可复现实验与结果 |
| `docs` | 文档与报告 |
| `test` | 测试与验证 |
| `refactor` | 不改变行为的代码重构 |
| `chore` | 工程配置和仓库管理 |

提交摘要说明“完成了什么”，不要写“update”“修改一下”等无信息文本。

### 4.5 合并到本地稳定分支

仅在不会覆盖或混入其他任务状态且能够快进时执行；否则保留已验证的任务提交并报告阻塞，不自行 rebase、重置或清理其他任务。

```powershell
git switch master
git merge --ff-only codex/<task>
git status --short --branch
```

合并后保留任务分支，直到阶段性整理时再决定是否删除。删除分支属于清理操作，必须先征得用户同意。

## 5. 实验提交规则

实验目录使用：

```text
optimization_control/experiments/YYYYMMDD_简短描述/
├── config.yaml
├── metrics.csv
├── summary.txt
├── *.png           # 默认不跟踪
└── checkpoints/    # 默认不跟踪
```

- `config.yaml`：算法、环境、数据版本、超参数和 `seed=42`。
- `metrics.csv`：用于比较的核心数值，字段和单位保持稳定。
- `summary.txt`：目的、命令、结论、异常和模型/大文件位置。
- 大产物不入 Git，但摘要必须能从本地路径定位它们。
- 每次只改变一个主要因素；否则实验结论不可归因。

## 6. 安全恢复

只取消暂存、保留工作区内容：

```powershell
git restore --staged -- <file>
```

查看某个历史版本，不改动当前文件：

```powershell
git show <commit>:<path>
git log --oneline -- <path>
```

会覆盖文件、删除文件或改写历史的操作不得自行执行，包括 `git restore <file>`、`git clean`、`git reset --hard`、`git rebase`。命中这些情况时先向用户说明影响并取得许可。

## 7. 快速状态检查

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File tools/project_git_status.ps1
```

脚本只读取状态，依次显示工作区、暂存区、本地提交和 remote。实际修改任务结束应满足：

- 本任务改动已验证并提交；无法安全提交时报告具体阻塞和保留位置；
- 本任务没有遗留暂存内容，其他任务原有的工作区和暂存区内容不变；
- 能够安全快进时当前提交位于 `master`，否则保留任务分支并说明原因；
- 原工作仓库的 remote 保持原状态；授权交付可使用独立克隆。

## 8. 用户明确授权的远程交付

2026-10-07 用户授权将自己的全部优化工作整理至 `https://github.com/sunccchengze/FENGDIAN_2026` 的独立分支。

- 在独立交付克隆中从目标仓库默认分支建立 `codex/optimization-handoff-20261007`，保留团队现有文件，不直接改远程默认分支。
- 上传优化代码、测试、配置、报告和全部实验小文件；模型与轨迹按实验 ZIP 分卷保存于交付目录，单文件小于 100 MB，清单保存 SHA256 和原始相对路径。
- 交付中的 PINN 加载依赖只复制必要文件，明确队友来源和合成联调用途；不上传队友原始数据、整个 PINN 交付、凭据或本地环境。
- 使用明确文件列表暂存、审查提交和扫描敏感信息后普通 push；不强推、不合并远程默认分支、不自动建 PR。
- 后续其他仓库或公开发布仍须用户授权；本次授权不扩大到其他目标。

### 2026-10-22 本轮交付授权

用户要求再次打包本轮工作，并核对上次分支是否进入main。只读核对已确认上次最终提交 `782368a31e412ff318595d7166a7e8eae30104fe` 是当前main的祖先，旧分支不存在。因此本轮在独立克隆中基于最新main建立 `codex/optimization-handoff-20261022`，补充全部优化工作的新增代码、报告及归档，普通push并创建PR；不合并远程main、不强推、不删除旧成果。该明确授权替代上一轮“不自动建PR”的限制，其余凭据、大文件和团队边界不变。

### 2026-10-22 本轮收口

该分支于 2026-10-22 由维护方吸收进 `main`：新增代码、报告、证据卡与两份轨迹 CSV 直接入库；163.3 MB 的分片归档按 ADR-2026-003 留在 Release `intake-2026-10-22`，不入 git。PR #19 以「内容已并入 main」关闭，分支随后删除；`main` 不保留该分支的合并父提交（避免把 163.8 MB 分片带进历史）。上一轮「不自动建 PR」的限制继续生效。
