# 网页最终封板记录：v1.3-final

**固定分支**：`arena/01a012f1-wind-farm-viz`
**封板日期**：2026-08-19（Asia/Shanghai）
**最终代码审计基线**：`21a385e1 chore(site): harden final release checks and assets`
**状态**：**FINAL / 功能与视觉全部冻结**。

## 最终交付

- `site/` 为现役 15 页纯静态站，导航连续为 `00–13 + MAP`；另含同步首页原型和组会 Web Deck。
- 风玫瑰网页、站内入口、前端导出与专用站点图片副本已删除；根目录 CSV、生成脚本和科研图继续留档。
- 首页首屏采用浅色动态数字风洞：3×3 Canvas 风机、尾流、节点标注、鼠标耦合偏航、空间视差、全屏浅薄荷跟随光晕和点击涟漪。
- 首页所有动态数值均来自现有审计指标；结构场景不生成无来源功率。
- 全站 Hero、导航、字体、浅色玻璃和 1240px 网格统一；标题使用 Songti SC Black 栈，正文使用等线回退。
- 尾流三张动态图桌面同排同高；Nature 出版证据在 7 个页面按 2/3/4 张等高横排并响应式回落。
- Dashboard FIG.C/FIG.D 等高；模型精度 FIG.A/FIG.B 为 40%/60%；阵列四图、POD 三图均完成横排。
- 连续速度场使用 ColorBrewer BuGn 反向顺序色阶。
- Plotly 2.35.2、Three.js 0.160.0、Geist 1.7.2 全部本地化，核心演示断网可用。

## 最终门禁

```bash
python3 site/check_contract.py
python3 site/verify_all_pages.py
```

验收结果：

| 检查项 | 最终结果 |
|---|---|
| 源 CSV/JSON 与 `data.js/data_3d*.js` 契约 | 通过 |
| 15 个现役页面及附加页面 | 0 阻断错误，0 警告 |
| 首页数字风洞运行桩 | 九机、鼠标耦合、偏航、移动重绘通过 |
| 尾流运行桩 | 0°/+25°数据与三幅 Plotly 通过 |
| HTML/CSS/JS/Python 语法 | 通过 |
| 普通链接、CSS URL、页内锚点、重复 ID | 通过 |
| alt、title、viewport、noopener | 通过 |
| HTTP 冒烟 | 71 个现役路由 200；8 个下线路由 404 |
| `site/build_data.py` 幂等性 | 前后哈希一致 |
| PNG/PDF/WOFF2/MP4 文件签名 | 通过 |
| PPTX ZIP 结构 | 通过 |
| Cloudflare `_headers` | 安全头和固定依赖缓存规则齐全 |
| Git diff whitespace | 通过 |

根目录 `check_csv.py`、`check_fields.py` 需要 requirements 中的 pandas/matplotlib，当前沙箱未安装，未列入静态站发布门禁；纯标准库契约检查已覆盖发布数据同源性。

## 科研边界

1. FLORIS 是数值模拟，不写成现场实测。
2. `bg.mp4` 是风机数字孪生/线框结构运行示意，不是九机尾流实录。
3. 首页 Canvas 和 Three.js 包络是结构/策略示意，不冒充 CFD 等值面。
4. 浏览器功率反求是双线性代理搜索，不写成浏览器内 PPO 推理。
5. PPO 只声明 seed 42 的 200 个固定测试回合。
6. 模型精度页使用交付图源，不承诺仓内完整重训 XGBoost。
7. 风玫瑰研究数据继续留档，但不属于现役网页产品。

## 部署冻结

- Cloudflare Pages 输出目录：`site`；无构建命令、无环境变量、无后端。
- `site/_headers` 已配置基础安全响应头。
- 全站无第三方运行时请求、分析脚本、Cookie 或密钥。
- 本地预览：`python3 -m http.server 8000 --bind 0.0.0.0 --directory site`。

## 变更禁令

用户已确认当前视觉效果为最终版本：

- 不新增页面，不恢复风玫瑰网页，不再进行视觉重构。
- 不以历史原型覆盖 `index.html`。
- 不重新引入已清理的旧前端脚本和样式。
- 不添加无数据来源的动态值或科研结论。
- 只允许修复明确的运行错误、死链、数据错误、安全问题或文字溢出；修复后必须重跑全部门禁。

最终维护入口为 `HANDOFF_NEXT_AGENT.md`；历史过程仅在 Git 与 `.learnings/` 中追溯。
