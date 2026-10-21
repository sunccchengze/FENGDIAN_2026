# GitHub Project 配置蓝图

> 📍 **本文件只讲 GitHub Project 的配置蓝图，不是 `docs/project/` 目录的全部。**
> 同目录的 [`TIMELINE.md`](TIMELINE.md) 是**全仓唯一的项目时间线主干**（六个阶段、按事件日期的主表、事件↔入库滞后对照、分区明细职责划分、八项已知缺口），2026-10-05 建立。
> 要回答「某件事什么时候发生」去 `TIMELINE.md`；要回答「Project 建好后有哪些字段和视图」看下面。

> 状态：配置规格已入库，远端 Project 尚未创建。
> 原因：当前 GitHub App 无权在 `sunccchengze` 用户名下创建 Projects；创建 mutation 返回 `FORBIDDEN`。这不是“已配置”的同义词。

## 目标

Project 只管理可执行工作的状态、负责人、优先级、领域和里程碑；研究事实、实验结果和长期决策仍回写仓库文件，不把 Project 当成第二个知识库。

## 建议字段

| 字段 | 类型 | 建议值 | 来源 |
|---|---|---|---|
| Status | 单选 | Todo / Ready / In progress / Blocked / In review / Done | Issue/PR 状态 |
| Type | 单选 | Task / Experiment / Decision / Evidence / Literature / Material | Issue Form 类型 |
| Area | 单选 | twin / viz / physics / model / data / control / docs / materials / infra | Issue Form 领域 |
| Priority | 单选 | P0 / P1 / P2 | 任务验收影响 |
| Assignee | 人员 | 五位实际成员 | 主责人，不等于目录所有者 |
| Milestone | 里程碑 | R41、阶段总结、答辩等 | 项目计划 |
| Provenance | 单选 | 真实 / 代理 / 演示 / 示意 / 不适用 | 关键数字和材料任务 |
| Due date | 日期 | 明确截止日或空 | 会议/Issue |

## 建议视图

1. **总览**：按 Status 分组，显示 Assignee、Area、Priority、Milestone；
2. **当前迭代**：筛选 `Status != Done`，按 Priority 和 Due date 排序；
3. **按领域**：按 Area 分组，便于 CFD、模型、数据、控制和 twin/viz 集成负责人查看；
4. **材料与证据**：筛选 Type 为 Material 或 Evidence，显示 Provenance、审阅状态和引用位置。

## 自动化边界

- 新建 Issue 自动进入 Todo；
- Issue 被分配后保留对应 Assignee，不因为目录路径自动猜负责人；
- PR 打开时进入 In review，合并后进入 Done；
- Issue 关闭前必须在 Issue 留下结果摘要和仓库内链接；
- 自动化不修改研究结论、不生成数字、不替代领域审阅。

## 建立后核验

Project 创建后，由项目管理员完成并记录：

- [ ] Project 名称、可见性和 owner 正确；
- [ ] 上述字段和视图已建立；
- [ ] 仓库已加入 Project；
- [ ] Issue/PR 自动化规则已试跑；
- [ ] 一条真实实验任务能从 Issue 进入 Project、关联 PR，并在关闭时保留证据链接；
- [ ] Project URL 回填本文件和 `docs/meetings/` 的配置记录。

当前 GitHub 账号可从 [个人 Projects 页面](https://github.com/users/sunccchengze/projects) 创建；创建后不要把 URL 只留在聊天记录中。
