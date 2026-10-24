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

---

## 2026-09-21 追记：队友交付件迁出与重复件去重台账

> 执行：Arena Agent（分支 `arena/01a0c193-dachuang-szls`），依用户「按人分类、不漏一个文件」的要求。
> 迁出前的完整快照仍可在提交 `66abeb5` 中取回（`git show 66abeb5:<原路径>`）。

两条归档线的 `20260808/` 目录里放的是**袁夫达、厉今飞、洪祖名的交付件和全组群聊纪要**，不是可视化平台代码，
且 A/B 两线各存一份、根目录又各存一份 `floris(1).zip`，同一份文件最多重复 4 次。本次处理原则：**唯一内容迁到 `materials/` 对应人目录，字节级重复件删除**。

### 迁出（`git mv`，内容不变）

| 原路径（B 线 `019fd504-static-site-line/`） | sha256 前 12 位 | 现路径 |
|---|---|---|
| `20260808/floris(1).zip` | `68b717ae89b4` | 先迁至 `materials/袁夫达/20260808_FLORIS数据生成/`，随后按用户决定**只留解压件**（袁夫达数据部分在同目录 `extracted/`，厉今飞网络部分在 `materials/厉今飞/20260808_功率预测神经网络基线/`；31 个文件逐条 sha256 与包内一致），zip 本体删除。完整 sha256：`68b717ae89b4081ed63a9ad4af3aaab0db314902a20a0685c54a3c7cfecda70c`；取回：`git show 66abeb5:"viz/_archive/019fd504-static-site-line/20260808/floris(1).zip"` |
| `20260808/代理模型优化交付_20260808.zip` | `552a44c3ea7b` | 先迁至 `materials/洪祖名/20260808_代理模型优化交付/`，随后按用户决定**只留解压件**（19 个文件逐条 sha256 与包内一致），zip 本体删除。完整 sha256：`552a44c3ea7be549513f243e1a38b918487be713adb7036c6b38decec4d7f4fb`；取回：`git show 66abeb5:"viz/_archive/019fd504-static-site-line/20260808/代理模型优化交付_20260808.zip"` |
| `20260808/README.md` | `08ce2762be41` | `materials/集体/20260808_群聊纪要_FLORIS数据·神经网络选型·导师意见.md` |
| `20260808/假期前PPT.md` | — | `materials/集体/假期前PPT_大创项目假期技术路线.md` |
| `20260808/本科生答辩材料可供参考.md` | `d5785119c8ab` | `materials/集体/参考资料/本科生答辩材料可供参考.md` |

### 删除的字节级重复件（`git rm`）

| 原路径 | sha256 前 12 位 | 与之相同的保留件 |
|---|---|---|
| `019fcc85-streamlit-line/20260808/README.md` | `08ce2762be41` | `materials/集体/20260808_群聊纪要_…md` |
| `019fcc85-streamlit-line/20260808/floris(1).zip` | `68b717ae89b4` | `materials/袁夫达/20260808_FLORIS数据生成/extracted/` + `materials/厉今飞/20260808_功率预测神经网络基线/`（解压件） |
| `019fcc85-streamlit-line/floris(1).zip` | `68b717ae89b4` | 同上 |
| `019fd504-static-site-line/floris(1).zip` | `68b717ae89b4` | 同上 |
| `019fcc85-streamlit-line/20260808/代理模型优化交付_20260808.zip` | `552a44c3ea7b` | `materials/洪祖名/20260808_代理模型优化交付/extracted/`（解压件） |
| `019fcc85-streamlit-line/20260808/本科生答辩材料可供参考.md` | `d5785119c8ab` | `materials/集体/参考资料/…md` |
| `019fcc85-streamlit-line/20260808/最高优先级AGENT必须遵守的宪法级文件.md` | `fbccfa3e1ff2` | `materials/孙承泽/学习计划与Agent准则/skills-notes/同名文件` |
| `019fd504-static-site-line/20260808/最高优先级AGENT必须遵守的宪法级文件.md` | `fbccfa3e1ff2` | 同上 |
| `019fcc85-streamlit-line/20260329-大创申请书-终版.docx` | `7f01fcb31a7e` | `materials/集体/20260329-大创申请书-终版.docx`（迁入时名为 `终版(1).docx`，后去掉下载后缀；正文 12,851 字与 11 张内嵌图逐条目相同；被删版本是 2026-08-04 由 `a94126` 另存，仅 docProps / styles 等元数据不同，保留的是原作者 `jinfei L` 2026-03-30 的原件） |
| `019fd504-static-site-line/20260329-大创申请书-终版.docx` | `7f01fcb31a7e` | 同上 |

### 另：`viz/` 根目录的一对相同 PPT

`viz/用户原版_风电场偏航优化可视化260809.pptx` 与 `viz/孙承泽原版微调_风电场偏航优化可视化.pptx` 逐字节相同（434,596 B，sha256 `8633246dc70c`），
两者先一并迁入 `materials/孙承泽/2026-08-09_首版PPT与王牌PPT/`，随后按用户指示（2026-09-21）删除「用户原版」、保留「孙承泽原版微调」。

### 未动的部分

两线其余全部文件（Streamlit 代码、数据、`site/` 旧版、`docs/` 文档中心、`.vscode/`、`wrangler.toml` 等）原样保留；
`019fd504-static-site-line/docs/` 里的 `team_inventory.md` / `communication_log.md` / `question.md` / `孙承泽个人待办.md` 等是孙承泽的 Agent 当时写的项目文档，属平台文档，留在归档内，
但它们是判断上述交付件归属的一手依据（尤其 `communication_log.md` 末尾孙承泽对 Q4/Q12/Q13 的答复）。

## 2026-10-24 追记：田铭雨三机串列数据包（非归档来源，仅记删除台账）

| 项目 | 记录 |
|---|---|
| 原路径 | `materials/田铭雨/三机串列_双模型对比数据及说明.zip` |
| 大小 / sha256 | 744,061 B / `240fe7e38c5c21106834565f18880205be5cc9c52df5f7612aa8bf98c96675c6` |
| 来源提交 | `cb6ec84`（田铭雨 2026-10-24 经 GitHub 网页上传） |
| 处理 | 按 `materials/README.md` §2 规矩 5 解包并逐文件核对后删除 zip 本体；解包结果 23 个文件留在 `materials/田铭雨/20261024_三机串列双模型对比/`，附 `SHA256SUMS.txt` |
| 取回 | `git show cb6ec84:"materials/田铭雨/三机串列_双模型对比数据及说明.zip" > /tmp/tandem.zip` |
| 备注 | 该 zip 用 GBK 记录文件名且未置 UTF-8 标志位，直接解包会得到乱码目录；须 `info.filename.encode("cp437").decode("gbk")` 转码（`tools/inspect_transfer_zip.py` 同样会显示为乱码）。可用性核查见 `docs/evidence/EVID-2026-003_三机串列CFD数据可用性核查.md` |
