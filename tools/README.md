# tools/ — 仓库维护脚本

只放**与仓库整理直接相关**、无需领域知识就能安全运行的脚本；科研代码不放这里（`viz/`、`twin/` 各有自己的脚本目录）。

| 脚本 | 作用 | 常用命令 |
|---|---|---|
| [`intake_bundle.py`](intake_bundle.py) | 交付包**入库前**的只读体检与清单：文件数、解压后体积、最大文件、绝对路径 / `..` / 符号链接、超 95 MiB 项、CRC；可生成逐文件 sha256 清单；可校验 `.zip.NNN` 分卷连续性。纯标准库 | `python3 tools/intake_bundle.py --inspect 包.zip` · `--manifest 包.zip --out m.json` · `--check-splits 目录/` |
| [`markitdown_sync.py`](markitdown_sync.py) | 为 `materials/` 下的 docx / pptx / xlsx / pdf 生成同名 Markdown 镜像（基于 [microsoft/markitdown](https://github.com/microsoft/markitdown)），首行注释记录来源与 sha256；镜像里不留死链（图片改为文字占位，pptx 软换行改为换行） | `python3 tools/markitdown_sync.py`（增量）· `--force`（全部重生成）· `--check`（只校验，不需要 markitdown）· `--root docs/` |
| [`package_optimization.py`](package_optimization.py) | 生成一份**新**的优化控制交付包与分卷归档（不删除、不覆盖、不推送） | 见文件头 `--help` |
| [`unpack_optimization.py`](unpack_optimization.py) | 校验交付分卷并解包到**新目录**（从不覆盖既有文件） | 见文件头 `--help`；`--all-history` 恢复全部历史成果 |
| [`mk_softcopy_code.py`](mk_softcopy_code.py) | 软著源代码 60 页文档生成器（前 30 页 + 后 30 页，每页 50 非空行）；文件顺序见 [`softcopy_code_order.txt`](softcopy_code_order.txt) | 见文件头 |
| [`mk_softcopy_doc.py`](mk_softcopy_doc.py) | 软著说明文档（用户手册）markdown → docx 生成器 | 见文件头 |
| [`project_git_status.ps1`](project_git_status.ps1) | Windows PowerShell 下的仓库状态速览 | `pwsh tools/project_git_status.ps1` |

依赖：`markitdown_sync.py` 生成镜像需要 `pip install 'markitdown[docx,pptx,pdf,xlsx]'`（`--check` 与 `ci/repo_quality.py` 只用标准库）；`mk_softcopy_code.py` / `mk_softcopy_doc.py` 需要 `pip install python-docx`；`intake_bundle.py`、`package_optimization.py`、`unpack_optimization.py` 纯标准库。

大文件口径：>50 MiB 的二进制按 [`ADR-2026-003`](../docs/decisions/ADR-2026-003-大交付包存储口径.md) 走 Release 资产，不入 git；`intake_bundle.py --inspect` 会把超线文件直接列为 ✗，`ci/repo_quality.py` 的 `check_large_assets()` 则要求它出现在某个 `SHA256SUMS.txt` 里。

相关约定：`materials/README.md` 规则 8–10（聊天截图转录、Office/PDF 镜像、解压交付件的 `SHA256SUMS.txt`）；门禁在 [`ci/repo_quality.py`](../ci/repo_quality.py)。
