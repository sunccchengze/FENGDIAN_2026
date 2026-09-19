# _archive/ — 孤立分支内容全量归档

> 归档时间：2026-09-03 · 执行者：Arena Agent（分支 `arena/01a06516-wind-farm-viz`）
> 操作性质：用户批准的"全分支取并集"收仓操作，遵循 **零遗漏** 原则。

## 背景

仓库曾存在 10 条 `arena/*` 会话分支 + `main`（单提交快照 `35f76a8`，2026-08-08）。
本次收仓将全部内容以并集方式汇入 `arena/01a06516-wind-farm-viz`，再经"快进推送绕过 PR"
（`git push origin <分支>:main`）送达 `main`，全程 0 个 PR。

## 并集构成

| 来源 | 并入方式 | 位置 |
|---|---|---|
| `main`（8/8 快照） | 基线 | 仓库根 |
| `arena/01a012f1`（8/24，+141） | 快进合并，含 `019fe0c0`/`019fe42f`/`019feacd`/`019feb53`/`019ff8da` 全部提交 | 仓库根（现役树） |
| `arena/019ff8d6`（8/13，+62） | 正常合并（独有技能底座提交 `9c2a18a2`；`LEARNINGS.md`/`HANDOFF.md` 冲突按并集化解，019ff8d6 版全文存于 `HANDOFF.md` 文末"📦 历史存档"） | 仓库根 |
| `arena/019fcc85`（孤立线A，+21） | `-s ours` 历史嫁接（提交图谱可查）+ 全量文件树归档 | `_archive/019fcc85-streamlit-line/` |
| `arena/019fd504`（孤立线B，+26） | `-s ours` 历史嫁接（提交图谱可查）+ 全量文件树归档 | `_archive/019fd504-static-site-line/` |

## 归档目录身份卡

### `019fcc85-streamlit-line/`
- 原分支：`arena/019fcc85-wind-farm-viz`（tip `6e654b8b`，2026-08-08）
- 内容：7 月末–8 月初 **Streamlit 修复线**：plotly 模板修复、Streamlit Cloud 路径兼容、
  全页面统一加载提示/导出/单位规范、3D 体渲染 30° 偏航伪影修复、封面设计 + Master Dashboard 试验页。
- 与现役树关系：与 main 无共同祖先的平行线，Streamlit 技术栈（现役产品为 `site/` 纯静态站）。

### `019fd504-static-site-line/`
- 原分支：`arena/019fd504-wind-farm-viz`（tip `fe1dc480`，2026-08-08）
- 内容：8 月 4 日–8 日 **静态站重写 + 文档中心线**：11 页多页面静态站
  （3D 曲面/体渲染/热力矩阵/POD/总览/Dashboard 还原）、风玫瑰/模型精度/接口 3 个额外页、
  群聊与洪祖名代理模型交付消化、阶段性交付方案、成员清单、研究综述、李良星 20 问、沟通记录。
- 与 A 线关系：与 A 线部分同源但不同 SHA，内容各有独有部分，故两条均全量归档。

## 查阅方式

- 归档线的**提交历史**已嫁接进本仓图谱：`git log --all --oneline | grep <关键词>` 或
  `git log origin/arena/019fcc85-wind-farm-viz --oneline`（分支删除前）均可追溯；
  分支删除后其提交仍通过合并提交 `5dbd23ea`（A 线）、`61313850`（B 线）可达。
- 归档线的**文件内容**即本目录下的原样拷贝，目录结构 = 原分支根目录结构。

## 注意

- 本目录为历史存档，**不是现役产品的组成部分**；现役产品为仓库根的 `site/`（15 页纯静态站，
  状态 FINAL，见根目录 `FREEZE.md` / `HANDOFF_NEXT_AGENT.md`）。
- 归档内容一律不再维护；如需引用其中的数字/设计，请先与 `HANDOFF_NEXT_AGENT.md` 的可信口径核对。
