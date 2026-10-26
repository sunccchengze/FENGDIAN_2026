# 已装载技能清单（27 项）

> 来源：用户通用技能库 [sunccchengze/-SKILL-](https://github.com/sunccchengze/-SKILL-)（26 项自 arena/01a0095c-skill，按其官方协议检索并以 `scripts/install_skills.py` 安装，2026-08-24；第 27 项 `gsap-plugins` 自最新提交分支 arena/01a048e7-skill 安装，2026-08-30，第 24 轮）。
> 目录即技能包：每项含 `SKILL.md`（+可能的脚本/资源），实施时按需展开阅读。

## 🎯 3D / WebGL / 游戏画质（本项目主角）
| 技能 | 用途 |
|---|---|
| threejs-data-visualization | OpenAI 官方：Three.js/WebGL/deck.gl/ECharts-GL 可视化选型与实现模式 |
| react-three-fiber-game | R3F 场景组织、状态与帧循环工程化（风电场主体即"游戏级场景"） |
| three-webgl-game | 裸 three.js 命令式控制后备（性能极限优化时参考） |
| game-studio | 游戏级项目流程总路由（设计/资产/实现/测试） |
| game-ui-frontend | HUD/菜单/覆盖层的视觉方向（孪生大屏 HUD 直接受益） |
| game-playtest | 浏览器端玩法/渲染 QA：截图验证、自动化巡检 |
| img2threejs | 参考图 → 程序化 three.js 资产（备：自制风机零件/装饰物） |
| scroll-world | 滚动驱动"穿越世界"运镜范式 → 我们的开场巡航/叙事镜头 |
| gsap-plugins | 官方 GSAP 插件技能（Inertia/MotionPath/CustomEase 等）→ 第 24 轮开场无人机运镜的"惯性"语义来源：track 速度→指数滑行减速停止、沿路径变速+切向对齐（本项目不新增依赖，按技能原则原生移植到 `twin/src/scene/introProfile.ts` + `CameraRig.tsx`） |
| epic-design | 影院级、沉浸式设计的目标设定与评审语言 |
| shaders-cursor-ripples | WebGPU/GLSL 交互涟漪 shader 模式（选中机组的拾取波纹可借鉴） |
| liquid-metal-border | WebGL 液态金属边框（旗舰面板的高光描边备选） |

## 📊 数据可视化 / 大屏
| 技能 | 用途 |
|---|---|
| data-visualization | 图表选择总路由 |
| dashboards-and-real-time-visualization | 监控大屏版式、流式图、协同联动（左右双栏 + 实时功率流依据） |
| react-and-nextjs-data-visualization | ECharts/uPlot 组件化集成模式 |
| testing-data-visualizations | 可视化的截图差分/契约测试 |
| visualization-strategy-and-critique | 设计评审框架（每 Phase 自查表） |
| scientific-visualization | 科研可视化诚信规范（尾流场不夸大、色标如实） |
| understand-dashboard | 交互式仪表盘结构理解工具 |

## 🏗️ 工程 / 部署 / 性能
| 技能 | 用途 |
|---|---|
| cloudflare-deploy | OpenAI 官方：Workers/Pages/R2/D1 部署全流程（§8 的依据之一） |
| web-perf | 官方 Cloudflare 系：Core Web Vitals 度量与优化 |
| frontend-app-builder | 高颜值前端应用搭建总则（首屏/英雄区/质感清单） |
| frontend-design-direction | 生产级 UI 设计方向设定流程 |
| react-performance | React/Vercel 系性能模式（并发/重渲染控制，护帧率） |
| performance-optimization | 端到端性能优化清单 |
| imagegen-frontend-web | 高级视觉方向提示词库（生成 HUD 装饰/背景概念图时参考） |

## 使用纪律（遵循技能库 README 协议）
1. 先检索→点名→完整执行→拿证据交付；
2. 每个阶段主用 1 个技能 + 至多 3 个互补技能，不滥载；
3. 引用结果需可验证（命令输出/截图/构建报告）。

## 📐 科研出图（2026-10-26 引入）

| 技能 | 用途 |
|---|---|
| scientific-figure-making（[figures4papers](https://github.com/ChenLiu-1996/figures4papers)） | 投稿级 matplotlib 出图规范：语义配色、去脊线、独立图例面板、300 dpi + 矢量导出。已落到 `tools/figstyle.py`，规则摘要见 `docs/figures-style-guide.md` |
