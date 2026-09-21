# tools/ — 仓库维护脚本

只放**与仓库整理直接相关**、无需领域知识就能安全运行的脚本；科研代码不放这里（`viz/`、`twin/` 各有自己的脚本目录）。

| 脚本 | 作用 | 常用命令 |
|---|---|---|
| [`markitdown_sync.py`](markitdown_sync.py) | 为 `materials/` 下的 docx / pptx / xlsx / pdf 生成同名 Markdown 镜像（基于 [microsoft/markitdown](https://github.com/microsoft/markitdown)），首行注释记录来源与 sha256；镜像里不留死链（图片改为文字占位，pptx 软换行改为换行） | `python3 tools/markitdown_sync.py`（增量）· `--force`（全部重生成）· `--check`（只校验，不需要 markitdown）· `--root docs/` |

依赖：生成需要 `pip install 'markitdown[docx,pptx,pdf,xlsx]'`；`--check` 与 `ci/repo_quality.py` 只用标准库。

相关约定：`materials/README.md` 规则 8–10（聊天截图转录、Office/PDF 镜像、解压交付件的 `SHA256SUMS.txt`）；门禁在 [`ci/repo_quality.py`](../ci/repo_quality.py)。
