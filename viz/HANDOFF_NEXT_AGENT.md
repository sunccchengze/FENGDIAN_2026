# 风电场偏航优化网页最终交接总账本

**固定分支**：`arena/01a012f1-wind-farm-viz`
**最终封板日期**：2026-08-19（Asia/Shanghai）
**最终代码审计基线**：`21a385e1 chore(site): harden final release checks and assets`
**状态**：**FINAL / 网页开发结束**。15 页静态站已完成视觉、交互、数据、离线依赖、资源和部署前检查；除明确运行故障、死链或数据纠错外，不再继续改版。

## 1. 项目与交付边界

西安交通大学大学生创新训练项目“风电场偏航优化可视化系统”。孙承泽负责可视化与交互系统；田铭雨负责 CFD，袁夫达负责 POD/代理，厉今飞负责基线，洪祖名负责 PPO，指导教师为李良星副教授。

现役产品是 `site/` 下 15 页纯静态站，导航为 `00–13 + MAP`：

`index → wake → optimization → solver → dashboard → array → heatmap → pod → model → power_tracking → 3d_farm → 3d_surface → 3d_volume → interface → overview`

附加 HTML：`index_v2.html`（同步首页原型）与 `slides_823.html`（组会 Web Deck）。根目录 Streamlit 应用仅作留档工具，不是现役网页。

风玫瑰网页已经下线；根目录风向扫描 CSV、生成脚本与 `figures_nature/fig7_windrose.*` 继续作为科研留档，不得误删，也不得重新接回现役导航。

## 2. 最终视觉与交互状态

- 全站采用浅色白绿/水青科研工作台、Songti SC Black 标题栈、等线正文回退、Geist/Geist Mono 技术标签。
- 首页首屏为高明度动态数字风洞：全屏网格、浅薄荷鼠标光晕、点击涟漪、3×3 Canvas 风机与尾流、鼠标耦合偏航和空间视差；结构示意不生成无来源功率读数。
- 首页大标题三行字体已统一；褐色与过暗绿色光斑已清除。
- 尾流页 Hero 与全站 1240px 网格居中对齐；三张动态图桌面同排同高，控制在上、动态图居中、Nature 证据沉底。
- 7 个含 Nature 证据的页面共展示 15 张图：桌面按 2/3/4 张等高横排，平板最多两列，手机单列；单图页面居中收束。
- Dashboard FIG.C/FIG.D 等高双栏，控制室配图已删除。
- 模型精度 FIG.A/FIG.B 使用 40%/60% 比例，右侧统计区填满高度。
- 阵列四张 Nature 图同排；POD 三张 Nature 图同排。
- 速度场使用 ColorBrewer BuGn 反向顺序色阶：低速森林绿，高速浅薄荷。
- 玻璃只用于一级工作面和必要仪器层，不再堆叠重复透明卡片。

## 3. 科研表达边界与可信数字

必须继续遵守：

1. FLORIS 结果是数值模拟，不写成现场实测。
2. 首页 `bg.mp4` 仅是风机数字孪生/线框结构运行示意，不是 3×3 阵列尾流实录。
3. 首页 Canvas 数字风洞与 Three.js 尾流包络属于结构/策略示意；双机速度纹理才读取 FLORIS 三维速度数据。
4. `power_tracking.html` 上部是浏览器双线性代理反向搜索，下部是 PPO 权重离线评测；不得混写为浏览器内 PPO 推理。
5. PPO 当前只验证 seed 42 权重的 200 个固定测试回合，不声称多模型种子稳定性。
6. 模型精度页面保留交付图源；仓库不承诺可从原始训练压缩包完整重训 XGBoost。

可信数字：

- 两机 5D 串列，8 m/s：0° `2190.39 kW`；+25° `2368.40 kW`；增益 `8.13%`。
- 3×3：基准 `8095.15 kW`；第一排 +30° `9299.05 kW / +14.87%`；前两排 +30° `9934.99 kW / +22.73%`；逐排贪心 `[30,20,0]°` `10041.46 kW / +24.04%`。
- POD：Mode 0 `76.38%`，Mode 1 `21.58%`，前两阶累计 `97.97%`。
- PPO seed 42：200 回合稳态 MAE `0.523%`，平均调节时间 `0.944 s`，95 分位 `1.805 s`。

## 4. 最终质量门禁

部署前只需执行：

```bash
python3 site/check_contract.py
python3 site/verify_all_pages.py
```

`verify_all_pages.py` 已覆盖：

- 15 页导航顺序、17 个 HTML 页面、普通资源、CSS URL、页内锚点、重复 ID。
- HTML 元数据、图片 alt、`target=_blank rel=noopener`。
- 内联与外部 JavaScript 语法、离线 Plotly/Three.js/Geist。
- 首页数字风洞运行桩：九机绘制、鼠标耦合、偏航响应、移动端重绘、无伪功率。
- 尾流运行桩：0°与 +25°功率、三幅 Plotly、绿色速度色阶和顶部图例。
- Nature 等高横排、Dashboard 双栏、模型精度比例、尾流统一 Hero。
- 风玫瑰下线残留、旧无入口前端文件、伪数据、远程依赖和装饰性 Emoji。
- Cloudflare Pages `_headers` 基础安全头与固定版本依赖缓存策略。

最终审计结果：

- `check_contract.py`：通过。
- `verify_all_pages.py`：`0` 个阻断错误，`0` 个警告。
- `test_home_runtime.js`：通过。
- `test_wake_runtime.js`：通过。
- `site/build_data.py`：重复构建哈希不变。
- HTTP：71 个现役页面/资源路由返回 200；8 个下线页面/旧资源返回 404。
- HTML、CSS、JavaScript、Python 语法：通过。
- 36 PNG、16 PDF、2 WOFF2、1 MP4 文件签名：通过。
- PPTX ZIP 结构：通过。
- 6 个 `cases*.csv`、关键 JSON 结构：通过。

环境未安装 pandas/matplotlib，因此根目录探索工具 `check_csv.py`、`check_fields.py` 未执行；它们不是静态站发布链路。源数据与前端导出的同源关系已由纯标准库 `site/check_contract.py` 完整通过。

## 5. 部署与安全

Cloudflare Pages：

- 构建命令：留空。
- 输出目录：`site`。
- 环境变量：无。
- 固定开发/交付分支：`arena/01a012f1-wind-farm-viz`。
- `site/_headers` 提供 `nosniff`、Referrer Policy、Permissions Policy、同源框架限制及 vendor/font 长缓存。
- 全站浏览器运行不请求第三方接口，不使用分析脚本、Cookie 或后端服务。

## 6. 冻结规则

用户已明确决定按当前视觉状态收官。后继维护者应遵守：

- 不再重做设计语言、不新增页面、不恢复风玫瑰网页。
- 不以旧 `index_v2.html` 覆盖现役首页；两者当前保持同步。
- 不添加无数据来源的指标、功率、速度场、经济收益或种子结论。
- 不重新引入已删除的 `app.js`、`charts.js`、`bg-video.js`、`dashboard.css`、`media.css`。
- 只有出现明确死链、运行错误、数据错误、安全问题或文字溢出时才允许修复；修复后必须重新运行两道门禁。
- 软著截图、申请材料和答辩文件属于网页之外的后续交付，不应再触发站点视觉改版。

本文件与 `FREEZE.md` 是最终交接入口；`HANDOFF.md` 和 `.learnings/` 仅用于历史追溯。
