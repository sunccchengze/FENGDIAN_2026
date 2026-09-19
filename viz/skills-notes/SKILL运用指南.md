# SKILL 运用指南（风电场偏航优化可视化版 · 全能增强版）

> 本文件是本仓库「技能库&准则」的统一入口、技能路由表和全流程质量控制最高准则。
>
> **适用项目**：西安交通大学大创 · 风电场偏航优化可视化系统（组员孙承泽负责可视化与交互模块，指导教师：李良星）
> **历史同步来源**：`sunccchengze/turbine-blade-ai-platform` 分支 `arena/019fe072-turbine-blade-ai-platform` + 本地蒸馏大师库与领域技能库
> **2026-08-13 新增底座**：`sunccchengze/-SKILL-` 分支 `arena/019ff854-skill`（通用技能路由器 + 4 项新装载）

---

## 0. 必须遵守的回复声明规范（铁律）

每次回答用户问题时，开篇必须严格包含以下声明结构：

```markdown
### 🛠️ 技能调用与执行声明
- **本次显式调度大师**：【大师名1】（角色定位）、【大师名2】（角色定位）
- **本次显式调用SKILL**：`技能路径/名称1`、`技能路径/名称2`
```

---

## 1. 核心装载技能全景矩阵（33 大技能模块库）

| 技能分类 | 核心库/目录 | 主要能力与在本项目中的定位 |
|---|---|---|
| **AI 痕迹消除与去模板化** | `Stop-slop.md`, `Humanizer - 中文版.md` | 彻底消除 AI 浮夸词汇、空洞排比、破折号泛滥与二元对立结构，还原真实工科研究语气 |
| **宪法级准则与决策仲裁** | `最高优先级AGENT必须遵守的宪法级文件 - 副本.md`, `内阁决策.md` | 编码前思考（不脑补）、极简至上、外科手术式修改、追问/反对/机会/外行/执行五方红蓝对抗 |
| **设计美学与视觉品味** | `victor-design/`, `taste-skill/`, `impeccable/`, `huashu-design/`, `awesome-design-md/`, `awesome-shadcn-ui/` | 证据驱动跨载体设计（海报/演示/产品 UI）；杜绝廉价 AI 卡片与浮动阴影，建立网格对齐、发丝线与莫兰迪工科美学 |
| **活人感中文写作** | `human-writing/`, `Stop-slop.md`, `Humanizer - 中文版.md` | 材料先于篇幅；成稿禁翻案腔、破折号与提示性冒号；审校只选一个技能，避免把作者声音磨平 |
| **截图复刻与代码库 Wiki** | `screencoder/`, `openwiki/` | UI 截图先建成可编辑 HTML/CSS 基线再谈再设计；代码库文档以源码为事实源 |
| **演示文稿与路演答辩** | `guizang-ppt-skill-main/`, `frontend-slides/`, `skills-main/skills/pptx/` | 瑞士国际主义网格排版（Vignelli/Tufte 风格）、单文件 Web 演示、高密度大创/挑战杯答辩 Deck |
| **UI/UX 与前端工程** | `ui-ux-pro-max/`, `gsap-skills/`, `agent-browser/`, `browser-use/`, `playwright/` | 现代 UI/UX 设计规范、GSAP 动效物理仿真、无后端纯静态边缘渲染、自动化端到端测试 |
| **女娲蒸馏 12 大师智囊** | `nuwa-distilled/` | 【老弗】FLORIS流场 · 【老贝】贝兹极限 · 【老冯】涡动力学 · 【老布】POD/SVD · 【老卡】神经网络 · 【老鲍】统计误差 · 【费曼】物理直觉 · 【老塔】信息设计 · 【老乔】极致美学 · 【老达】手稿美学 · 【老加】高密度路演 · 【老芒】逆向决策 |
| **工程开发与全流程质控** | `ECC/`, `gstack/`, `addyosmani-agent-skills/`, `agent-skills-main/`, `superpowers-main/`, `obra-superpowers/`, `karpathy-skills/`, `boraoztunc-skills/` | 系统级调试、TDD 测试驱动、性能优化、代码审查、API 契约治理、复杂任务自动化调度 |
| **论文写作与知识图谱** | `Research-Paper-Writing-Skills-main/`, `llm-wiki-skill-main/`, `anydoc-main/`, `DeepTutor/` | 顶刊学术论文框架、文献知识图谱构建、苏格拉底式 C 模式深度知识拆解 |

---

## 2. 自动专家与技能调度路由表

根据孙承泽的具体问题属性，助手自动调度对应领域的大师与 SKILL：

1. **涉及尾流机理、偏航几何、FLORIS 模拟、阵列拓扑**：
   - 调度大师：**【老弗】(Paul Fleming)**、**【老贝】(Albert Betz)**、**【老冯】(Theodore von Kármán)**
   - 挂载 SKILL：`self-inspection`, `DeepTutor`, `skills-main/skills/pptx`
2. **涉及 POD/SVD 降阶模型、流场基模态重构、能量累积占比**：
   - 调度大师：**【老布】(Steve Brunton)**、**【费曼】(Richard Feynman)**
   - 挂载 SKILL：`karpathy-skills`, `DeepTutor`, `boraoztunc-skills`
3. **涉及 PPT 制作、答辩排版、图表去 AI 味、视觉美化、产品 UI 重塑**：
   - 调度大师：**【老塔】(Edward Tufte)**、**【老乔】(Steve Jobs)**、**【老加】(Garry Tan)**、**【老达】(Leonardo da Vinci)**
   - 挂载 SKILL：`victor-design`（主技能，产品 UI 读 `references/adapters/product-ui.md`）、`taste-skill`、`ui-ux-pro-max`、`Stop-slop.md`
   - 截图复刻先走 `screencoder` 建忠实基线，再设计才切回 `victor-design`
4. **涉及强化学习 PPO、神经网络代理模型、损失收敛与误差分析**：
   - 调度大师：**【老卡】(Andrej Karpathy)**、**【老鲍】(George Box)**
   - 挂载 SKILL：`karpathy-skills`, `agent-skills-main/skills/code-review-and-quality`
5. **涉及技术选型、答辩质疑应对、逆向防翻车**：
   - 调度大师：**【老芒】(Charlie Munger)**、**【老加】(Garry Tan)**
   - 挂载 SKILL：`内阁决策.md`, `superpowers-main/skills/brainstorming`, `boraoztunc-skills`

---

## 3. PPT 与图表制作“零 AI 味”核心规范

1. **绝对禁用悬浮卡片堆砌（SaaS UI Slop）**：严禁使用带浅灰描边和柔和阴影的通用圆角矩形堆叠。一律采用严谨的瑞士国际主义网格系统（Swiss Grid），以纯色底、1px 发丝线和清晰空间分栏排布。
2. **严禁任何 Emoji 装饰**：工科汇报严禁出现 🗺️, 📊, 🔥, ⚙️, ★ 等符号，一律替换为国际通用的章节代号（如 `08 / ARRAY TOPOLOGY`）或标准物理数学变量。
3. **拒绝卡通彩色泡泡**：风机布局必须呈现真实空间坐标（$x/D, y/D$）、实际偏航倾斜叶轮面（线段）、轮毂定位点与真实流场等值线图。
4. **最大化数据墨水比（Data-Ink Ratio）**：优先使用标准三线学术表格（Nature/IEEE 规范）、真实能量阶梯瀑布柱状图，直接标注物理机理与功率变化量。

---

## 4. 图像生成与视觉工程规范 (GPTImage2Skill)

装载模块：`技能库&准则/gpt-image-2-skill/`
参考文件：`技能库&准则/gpt-image-2-skill/31大场景提示词库与七条铁律.md`

### 4.1 七条铁律执行准则
1. **结构先于华丽**：`场景 (Scene) → 主体 (Subject) → 材质细节 (Key Details) → 光影构图 (Lighting/Angle) → 约束 (Constraints)`；
2. **文字严格加引号**：图内文字必须使用英文双引号界定（如 `"10041 kW"`, `"YAW +30°"`）；
3. **物理与工业词汇精准**：使用 *matte brushed titanium*, *cividis velocity contour*, *streamline ribbons*, *300 DPI vector* 等具体术语；
4. **显式构图参数**：明确 *Top-down orthographic 2D*, *Isometric 30°*, *Telephoto macro*；
5. **局部重绘守恒律**：先列 *Preserve Invariants*，再列 *Change only X*；
6. **分辨率严格对齐**：边缘为 16 的倍数，宽高比 $\le 3:1$；
7. **透明通道工程化**：透明素材一律走 Chroma 单色底（Magenta/Cyan）或黑白双背景对齐提取，严禁直出脏边。

---

## 5. 前端交互与动效设计系统 (MotionSites × Refero)

装载模块：`技能库&准则/motionsites-design-system/`
核心规范：`site/DESIGN.md` 与 `技能库&准则/motionsites-design-system/references/motion-recipes.md`

### 5.1 黄金工作流
$$\text{PRD 功能需求} \xrightarrow{\text{Refero DESIGN.md (设计约束)}} \text{锁定莫兰迪色盘/字体阶梯/8px网格} \xrightarrow{\text{MotionSites (动效配方)}} \text{物理插值/流线粒子/平滑转场}$$

### 5.2 核心运用场景
1. **静态站 15 个现役页面视觉重构**：统一按照 `site/DESIGN.md` 的颜色、圆角（$\le 12\text{px}$）、1px 发丝边框和 14px 毛玻璃背景规范执行，彻底消除粗糙的 AI 模板感；
2. **气动流场与 3D 动画交互**：采用 `motion-recipes.md` 中的 Canvas 粒子流线、Three.js 机舱平滑阻尼转动插值（`lerp`）与数据跳动器，提升交互专业度。

---

## 6. 多 Agent 协作与红蓝对抗架构 (Multi-Agent Architecture)

参考规范：`技能库&准则/MULTI_AGENT_ORCHESTRATION.md`
- **总指挥 (Chief Orchestrator)**：负责承泽需求的全局拆解与路由；
- **工兵 Agent 组**：负责具体流场计算（FLORIS）、神经网络（PPO）、PSD 绘图、前端动效；
- **独立红队审查 Agent（老塔/老芒/老贝）**：拥有交付前**一票否决权**，在提交前严格拦截 AI 模板味、物理违背与逻辑漏洞；
- **Self-Harness 进化器**：将审查打回的失败样本自动提炼为 Harness 拦截规则。

---

## 7. 阿里开源 Open Code Review (AI 代码审查规范)

装载模块：`技能库&准则/open-code-review/`
配置文件：`.opencodereview/rule.json`
执行命令：`ocr delegate preview` / `ocr rules check <path>` / `ocr review`

### 7.1 核心价值
- **工业级规则库**：阿里万级开发者海量验证的缺陷检测规则（空指针/死代码/资源泄漏/浮点相等/安全注入/并发竞争）；
- **定制规则合并**：自动合并 `.opencodereview/rule.json` 针对本项目的 Python 流体力学计算、JS WebGL 渲染与 HTML 莫兰迪规范；
- **红队审查集成**：作为多 Agent 架构中代码交付的硬性验收门禁。

---

## 8. 现代 AI Agent 全栈工程 (李博杰体系)

装载模块：`技能库&准则/ai-agent-engineering/`
大师入驻：`技能库&准则/nuwa-distilled/bojie-li-perspective/` (【李博杰】· 现代 AI Agent 架构宗师)
核心原理：$\text{Agent} = \text{LLM} + \text{上下文} + \text{工具}$

### 8.1 核心实践要求
1. **Harness 优先**：任何质量问题优先从上下文组织、工具契约与验证门禁找解法；
2. **代码即工具**：复杂流场计算与图表生成一律使用 Python 脚本作为现场动态生成的即时工具，执行后即时验证；
3. **上下文预算严控**：避免无关长文本膨胀，关键数据一律走结构化制品契约（`.npz` / `.json` / `DESIGN.md`）。

---

## 9. Codex 10 大科研全流程工作流 (小葛 AI / Nature Skills)

装载模块：`技能库&准则/codex-research-workflow/`
核心手册：`技能库&准则/codex-research-workflow/CODEX_10大科研工作流全景实战手册.md`

### 9.1 10 大阶段技能路由表
1. **01 选题**：`scientific-brainstorming`
2. **02 检索**：`nature-academic-search`
3. **03 综述**：`nature-reader` / `nature-literature-pipeline`
4. **04 统筹**：`academic-research-suite`
5. **05 统计**：`nature-statistics`
6. **06 绘图**：`nature-figure`
7. **07 写作**：`nature-writing`
8. **08 润色**：`nature-polishing`
9. **09 投稿/答辩**：`nature-reviewer` / `nature-response` / `nature-data`
10. **10 汇报**：`nature-paper2ppt`

---

## 10. UI UX Pro Max 顶级设计智能库 (109k Stars)

装载模块：`技能库&准则/ui-ux-pro-max/`
实战指南：`技能库&准则/ui-ux-pro-max/UI_UX_PRO_MAX运用实战指南.md`
数据底座：161 条行业设计推理规则、67 种 UI 风格、95 套色盘、56 组字体对、24 类图表规范。

### 10.1 强制调用规则
任何网页改动、CSS 优化、图表渲染、PPT 布局设计前，必须调用 `ui-ux-pro-max` 规则库进行预审，严格执行 7 项 Pre-Delivery 检查清单，从根本上杜绝“AI 网站廉价感”。

---

## 11. 免费域名与独立站部署 (DigitalPlat FreeDomain)

装载模块：`技能库&准则/free-domain-service/`
实战指南：`技能库&准则/free-domain-service/免费域名与CloudflarePages绑定实战指南.md`
上游项目：`DigitalPlatDev/FreeDomain` (支持 `.dpdns.org` / `.qzz.io` 等多后缀与自定义 NS 委托)

### 11.1 核心用途
为科研静态站 `site/`（原默认 `https://wind-farm-viz.pages.dev/`）提供免费独立域名（如 `https://wind-farm-viz.dpdns.org/`），无缝绑定 Cloudflare Pages 与免费 SSL 证书。

---

## 12. 全网多平台连接器 (Agent Reach - 69k Stars)

装载模块：`技能库&准则/agent-reach/`
实操指南：`技能库&准则/agent-reach/AGENT_REACH实战操作与多平台接入指南.md`
覆盖平台：B站、小红书、微信公众号、小宇宙播客、雪球、Twitter/X、Reddit、YouTube 等 15+ 平台。

### 12.1 核心价值
通过本地 Cookie 映射与各平台专用 CLI（`bili-cli`、`xhs-cli`、`yt-dlp`），让 Agent 能够实时检索并读取国内全平台内容，作为风电行业动态与答辩素材的一手来源。

---

## 13. 6阶全栈智能体记忆系统 (Memory System)

装载模块：`技能库&准则/memory-system/`
记忆存储目录：`.learnings/`
核心档案：
- `.learnings/LEARNINGS.md`（用户偏好、莫兰迪色盘、物理金标准）
- `.learnings/ERRORS.md`（判例式负向记忆：绝不改暗色、绝无Emoji/悬浮卡片、绝不弹窗）
- `.learnings/FEATURE_REQUESTS.md`（四大战役攻坚任务表）

### 13.1 跨 Session 接力铁律
任何新会话的 Agent 必须在第一步检索 `.learnings/` 与 `HANDOFF.md`，实现 100% 风格、认知与行为约束的无缝继承。
