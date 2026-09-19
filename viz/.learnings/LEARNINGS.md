# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20260810-01] 必须在每条回复开头强制声明大师与技能 (Zero Exception)
- **Logged**: 2026-08-10T08:00:00Z
- **Priority**: critical
- **Status**: verified
- **Category**: best_practice
- **Trigger**: user_correction
- **Context**: 助手与用户的每一次对话交互
- **Correct Approach**:
  每条回复第一行必须以绝对一致的格式显式声明：
  ```markdown
  ### 🛠️ 技能调用与执行声明
  - **本次显式调度大师**：【大师名】（角色定位）
  - **本次显式调用SKILL**：`技能路径`
  ```

---

## [LRN-20260810-02] 网页优化原则：保持莫兰迪基调，继续稳步提升
- **Logged**: 2026-08-10T08:20:00Z
- **Priority**: critical
- **Status**: verified
- **Category**: correction
- **Trigger**: user_correction
- **Context**: 静态站 `site/` 的后续优化与视觉准则
- **What Happened**: 助手使用了“基线锁死”等机械术语，给用户造成了“不能再优化网页”的误解。用户的真实诉求是：**喜欢莫兰迪浅色风格（米白底色、风机旋转背景视频、宋体-简）和现有的 3D 数据渲染体系，反对粗暴改成深海军蓝，但希望在现有基础上继续把网页改好、改精**。
- **Correct Approach**:
  1. 在现有 `site/` 莫兰迪风格的基础上稳步推进优化；
  2. 保持浅色米白底、动态背景视频与 3D 流场渲染功能；
  3. 后续优化以细节提升（如精细 SVG 图标、消除未编译 LaTeX、数值排版）为主，绝不破坏整体视觉与功能。

---

## [LRN-20260810-03] 孙承泽团队角色与定位精确校准
- **Logged**: 2026-08-10T06:50:00Z
- **Priority**: critical
- **Status**: verified
- **Category**: correction
- **Trigger**: user_correction
- **Context**: 大创项目成员角色确权
- **Correct Approach**: 孙承泽为交大大创组员，具体负责**“可视化与交互系统（Visualization & Interactive System）模块”**（非总负责人）。指导教师为李良星副教授，其他队友为田铭雨（CFD）、袁夫达（代理模型）、厉今飞（基线）、洪祖名（PPO 优化）。

---

## [LRN-20260810-04] 真实进度客观核算，严禁虚报完成
- **Logged**: 2026-08-10T08:05:00Z
- **Priority**: high
- **Status**: verified
- **Category**: correction
- **Trigger**: user_correction
- **Context**: 14 天四大战役推进进度
- **Correct Approach**:
  1. 战役模块一（网页系统优化）：进行中（在现有莫兰迪基础上继续打磨）；
  2. 战役模块二（物理与算法通识）：进行中（讲义就绪，等待承泽逐项深入学习）；
  3. 战役模块三（PS 300DPI 顶刊图与 A0 展板实战）：待开展；
  4. 战役模块四（20页 PPT 与答辩）：待开展。

---

## [LRN-20260810-05] 决策交互偏好：禁止选择题（已覆盖旧规则）
- **Logged**: 2026-08-10T10:30:00Z
- **Updated**: 2026-08-13
- **Priority**: critical
- **Status**: superseded
- **Category**: best_practice
- **Trigger**: user_explicit_request
- **Context**: 用户后来说“以后不要给我发选择题了。”
- **Correct Approach**: 不再发送多选问答。能执行就执行；关键歧义用一两句直接问，或写明假设后动手。

---

## [LRN-20260810-06] 分支铁律：永不 merge 到 main（Zero Exception）
- **Logged**: 2026-08-10T10:30:00Z
- **Priority**: critical
- **Status**: verified
- **Category**: correction
- **Trigger**: user_explicit_request
- **Context**: 2026-08-10 曾改绑历史部署分支（部署分支改绑 `arena/019feacd-wind-farm-viz` 时用户明确禁令）；Arena 会话分支会随交接变化，但“永不写入 main”不变。
- **Correct Approach**: 当时各会话只在自己固定分支上 commit/push（8/13 会话为 `arena/019ff8d6-wind-farm-viz`，8/19 封板会话为 `arena/01a012f1-wind-farm-viz`）；代码事实继承 `arena/019feb53-wind-farm-viz` 的 `cf554c9a`；历史分支 `019feacd` / `019fe42f` 只作资产来源，不回写；Cloudflare Pages 生产分支必须在控制台另行核对。
- **Union Note (2026-09-03)**: 2026-09-03 经用户批准执行“全分支取并集 → 快进推送至 main”一次性收仓操作（`git push origin arena/01a06516-wind-farm-viz:main`，即“快进推送绕过 PR”妙招，不触发 Arena 会话通道关闭）。该操作为收仓特例，不改变“日常会话永不直接写入 main”的规则。

---

## [LRN-20260810-07] PPO强化学习功率跟踪目标域物理可达界限定律
- **Logged**: 2026-08-10T12:00:00Z
- **Priority**: critical
- **Status**: verified
- **Category**: algorithm_physics
- **Trigger**: ppo_repro_train_convergence
- **Context**: 训练偏航功率跟踪时平均绝对误差（MAE）无法收敛的机理排查
- **Correct Approach**: 在纯偏航气动衰减模型（`P = P_base * cos(yaw)^1.88`，最大偏航限位 $\pm 30^\circ$）下，单机气动下限功率比为 $\cos^{1.88}(30^\circ) = 0.76306$。当训练目标功率下限设为 `0.35 * P_base` 等超出该下限的值时，系统必带巨大的不可达绝对误差（如 `u=10 m/s` 时下界不可达差高达 1419 kW）。强化学习功率跟踪优化必须将目标功率下限限制在物理可达域 `[0.78, 0.98] * P_base` 范围内，方可实现 0.523% MAE 的真实验证收敛。

---

## [LRN-20260810-08] 工作重心确权：锚定8.23组会可视化部分暑期进展汇报与通识打底
- **Logged**: 2026-08-10T14:00:00Z
- **Priority**: critical
- **Status**: verified
- **Category**: workflow_strategy
- **Trigger**: user_correction（十四天不是给我冲刺补基础的吗...我只是要准备8.23号组会的可视化部分暑期进展汇报）
- **Context**: 14 天学习攻坚与开发路线的优先级回归
- **Correct Approach**: 绝对不能脱离承泽真实诉求而空谈远期竞赛（A0 展板/挑战杯大 Deck）或学术发表（顶刊 300DPI 分层图）；当前会话与随后工作 100% 聚焦于 **8月23日组会 · 可视化与交互模块暑期研发进展汇报**。工作主线调整为两手抓：第一，用“大白话+第一性原理”协助承泽**冲刺补强流场基础、协同偏航和降阶加速通识**，练出汇报底气；第二，准备组会现场演示的**网页可视化讲演脚本、核心截屏与数据链路解释**。组会只讲风电项目，禁止夹带两机叶片优化。

---

## [LRN-20260813-01] 019ff854 技能底座已吸收；前端待命
- **Logged**: 2026-08-13
- **Priority**: critical
- **Status**: verified
- **Category**: best_practice
- **Trigger**: user_explicit_request
- **Context**: 新会话接手 019feb53，要求更新技能库后等指令再改前端
- **Correct Approach**:
  1. 技能检索走最小组队，主技能前端为 `victor-design` + `product-ui`；
  2. 维持现有浅色莫兰迪/瑞士网格，不另起暗色或另一套视觉语言；
  3. 用户未点名的页面一律不改；
  4. 用户说“先不要动手”时只确认就绪，不预改 `site/`。

## [LRN-20260813-02] 逐页重塑与排版红线
- **Logged**: 2026-08-13
- **Priority**: critical
- **Status**: verified
- **Category**: correction
- **Trigger**: user_correction（019feb53 会话）
- **Correct Approach**:
  1. 中文标题宋体黑，中文正文/UI 等线；等宽栈末尾挂 DengXian，防宋体回滚；
  2. 文字永不溢出；cause-bar / pill 禁止折行；
  3. 内容按 `t-container` 左对齐，子块不得再加一层 32px 左垫；
  4. Plotly legend 置顶，禁止压 X 轴标题；
  5. `bg.mp4` 口径是数字孪生线框运行示意，不是 3×3 九机实录；非视口页删除 `bg-video.js`；
  6. 0° 基线色用墨色，不要给基态乱上绿/黄。
