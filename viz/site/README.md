# 风电场偏航优化可视化 · 静态站点

纯静态、零后端的偏航优化可视化演示系统，已于 2026-08-19 完成 `v1.3-final` 封板。Plotly 2.35.2、Three.js 0.160.0 和 Geist 字体均锁定在 `assets/vendor/` / `assets/fonts/`，核心演示断网可用；后续不再继续视觉改版。

## 本地预览
```bash
python3 -m http.server 8000 --bind 0.0.0.0 --directory site
# 浏览器打开 http://localhost:8000
```

## 视觉母版

- `css/unified-glass.css` 是 15 个现役页面与首页原型共用的精密浅色母版：`#fafafa/#ffffff/#171717` 灰阶、本地 Geist、发丝线和克制玻璃材质。
- 玻璃只用于 Hero、一级工作台和主要图表外壳；数据格、表格与图内区域保持平面，避免全站泛滥透明卡片。
- 连续速度场使用 ColorBrewer `BuGn` 九级顺序色的反向版本：低速尾流为森林绿，高速清洁来流为浅薄荷。二维和三维速度图共用该语义。
- `wake.html` 在桌面端把三张动态图压成左、中、右同高一行；1100px 以下回落为单列，保证坐标和图例可读。
- 首页首屏右侧采用无卡片化 3×3 数字风洞结构示意：Canvas 风机、尾流与节点标注持续运行，并与鼠标位置耦合偏航、流线和空间视差；不生成无来源功率读数。
- 7 个含 Nature 出版证据的页面共用 `.nature-row/.nature-card`：桌面按每页图数以 2/3/4 列等高横排，平板最多两列、手机单列；单图页面居中显示，不作无意义拉伸。

## 部署到 Cloudflare Pages
**方式 A（Dashboard，推荐）**

连接 GitHub 仓库 `sunccchengze/wind_farm_viz` 后：

| 字段 | 值 |
|---|---|
| 生产分支 | 在 Cloudflare Pages 控制台核对并绑定当前交付分支；本次固定开发分支为 `arena/01a012f1-wind-farm-viz`，永不并入 `main` |
| 框架预设 | None |
| 构建命令 | 留空 |
| 构建输出目录 | `site` |
| 根目录 | 留空 |
| 环境变量 | 无 |

**方式 B（CLI）**
```bash
npx wrangler pages deploy site --project-name wind-farm-viz
```

## 数据与构建
- `assets/data.js` 由 `build_data.py` 从仓库根的 CSV/JSON 导出（纯标准库，无需 numpy）
- `assets/data_3d.js` 由 `build_3d_data.py` 从 `fields/`、`fields_3d/` 导出（需 numpy/pandas）
- 重新导出：
  ```bash
  python3 site/build_data.py
  python3 site/build_3d_data.py        # 需要 numpy/pandas
  python3 site/render_assets.py        # 重新生成 POD/3D 等 PNG（需 matplotlib/numpy）
  ```
- 模型精度图来自队友交付的 `floris(1).zip` 与 `代理模型优化交付_20260808.zip`。

## 替换真实数据 / 真实模型（界面零改动）

数据契约见根 `README.md`。替换步骤：

1. **更新源数据**：用真实数据覆盖仓库根的 `cases*.csv`、`fields*/`、`optimizer_result.json`、`array_independent_result.json`（保持字段、单位、数组形状不变）。
2. **重新导出前端数据**：运行上面的 `build_data.py` / `build_3d_data.py`。
3. **替换代理模型**（可选）：只改 `assets/js/interp.js` 中 `predict_power` / `find_yaw_for_target` 的函数体，保持返回字段兼容：
   - `predict_power(yaw, U)` 返回 `{p1, p2, ptot, outOfRange, reasons}`
   - `find_yaw_for_target(target, U)` 返回 `{yaw, ptot, error, base, outOfRange, reasons}`
4. **更新来源与边界说明**：在对应页面的图注、方法说明和可信域提示中同步修改数据来源，不使用全站悬浮状态条遮挡导航。
5. **双重质量门禁（必跑）**：
   ```bash
   python3 site/check_contract.py
   python3 site/verify_all_pages.py
   ```
   前者校验源 CSV/JSON 与 `data.js/data_3d*.js` 同源；后者检查页面资源、导航、锚点、可访问性、JavaScript、离线依赖、安全响应头，并调用 `test_home_runtime.js` 与 `test_wake_runtime.js` 实跑首页数字风洞和尾流 0°/+25°交互。任一退出码非 0 时禁止部署。

- Cloudflare Pages 基础安全响应头与 vendor/font 长缓存规则位于 `site/_headers`。
- 全站无第三方运行时请求、分析脚本、Cookie、密钥或后端服务。

> 数据来源与边界按页面就近标注：FLORIS 结果明确写为数值模拟，浏览器代理明确写为双线性插值；风速 6–12 m/s、偏航 ±30°为当前可信域，越界目标由交互区就地提示。

## 接口契约
- `predict_power(yaw_angle, U_inf) -> {p1,p2,ptot}` kW —— 见 `assets/js/interp.js`
- `find_yaw_for_target(target_power, U_inf) -> {yaw,ptot,error,base}`

当前现役基线为 FLORIS 4.6.6 GCH 数值模拟数据，浏览器功率接口为双线性插值；PPO 权重评测作为独立证据链展示。后续收到更高保真 CFD、NN 代理或新优化结果时，按同一契约重建前端数据，不把数值模拟写成现场实测。
