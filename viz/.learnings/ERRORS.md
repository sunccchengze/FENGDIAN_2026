# Errors

Command failures, integration errors, and critical precedent rollbacks.

---

## [ERR-20260810-01] 擅自破坏成熟网页莫兰迪体系与 3D 数据流 (Critical)
- **Logged**: 2026-08-10T06:30:00Z
- **Severity**: critical
- **Context**: 战役模块一执行过程中全站 CSS 激进重构
- **Error Description**: 私自将 `site/` 篡改为深海军蓝（`#020617`），导致视频背景、莫兰迪色盘与 3D Plotly 页面失效。
- **Root Cause**: 违反“外科手术式修改”原则，未以用户已验收的 commit `70c398e` 为前置基准。
- **Resolution / Prevention**: 
  1. 执行 `git checkout 70c398e -- site/` 完成 100% 字节级回滚；
  2. 永久封禁对 `site/` 基础视觉与 3D 渲染架构的破坏性重构，任何改动必须保持莫兰迪浅色基调。

---

## [ERR-20260810-02] 幻灯片生成出现通用 AI 卡片与 Emoji 泛滥 (High)
- **Logged**: 2026-08-10T04:15:00Z
- **Severity**: high
- **Context**: `generate_ace_deck.py` 首次生成 `王牌PPT.pptx`
- **Error Description**: 输出包含 3 个浮动白底圆角矩形、Emoji 符号（📊, ⚙️, 🔥）及彩色气泡圆圈风机。
- **Root Cause**: 缺乏反 AI 模板前置拦截，落入大模型预训练概率的通用 SaaS UI 模板腔。
- **Resolution / Prevention**: 接入 `Stop-slop.md`、`taste-skill` 与真实 FLORIS CFD 流场出图脚本，严格执行瑞士网格与三线表规范。

---

## [ERR-20260810-03] 未经 GitHub 检索私自臆断创建 Skill 机制 (High)
- **Logged**: 2026-08-10T07:10:00Z
- **Severity**: high
- **Context**: 用户要求吸收图片中的 6 大记忆 Skill
- **Error Description**: 助手未从 GitHub 上游权威开源仓库检索代码，而是自行编写简易骨架，被用户驳回。
- **Root Cause**: 未严格执行“GitHub 权威仓库检索 $\to$ 真实源码分析 $\to$ 无法检索则主动汇报请示”的标准规程。
- **Resolution / Prevention**: 驳回旧实现，完整 clone 并接入 `pskoett/self-improving-agent`、`Martian-Engineering/agent-memory` 与 `juanmacruzherrera/claude-layered-memory-architecture` 正式开源体系。
