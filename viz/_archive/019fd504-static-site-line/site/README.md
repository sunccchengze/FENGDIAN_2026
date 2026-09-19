# 风电场偏航优化可视化 · 静态站点

纯静态、零依赖的偏航优化可视化演示系统（替代原 Streamlit 版本），可直接部署到 Cloudflare Pages。

## 本地预览
```bash
python3 -m http.server 8000 --directory site
# 浏览器打开 http://localhost:8000
```

## 部署到 Cloudflare Pages
**方式 A（Dashboard，推荐）**
1. Cloudflare 控制台 → Pages → 连接 GitHub 仓库 `sunccchengze/wind_farm_viz`
2. 构建命令：留空
3. 输出目录（Build output directory）：`site`
4. 部署分支：`arena/019fd504-wind-farm-viz`
5. 保存并部署，获得 `*.pages.dev` 网址

**方式 B（CLI）**
```bash
npx wrangler pages deploy site --project-name wind-farm-viz
```

## 数据来源
- `assets/data.js` 由 `build_data.py` 从仓库根目录 CSV/JSON 导出（纯 Python，无需 numpy）
- 重新导出：`python3 site/build_data.py`
- 流场图片来自仓库根（`my_first_wake.png` 等）；模型精度图来自 `floris(1).zip` 与 `代理模型优化交付_20260808.zip`

## 接口契约（替换真实模型时只改函数体，界面零改动）
- `predict_power(yaw_angle, U_inf) -> (P1, P2) kW` —— 见 `assets/js/interp.js`
- `find_yaw_for_target(target_power, U_inf) -> (best_yaw, actual_power, error_pct)`

当前数据为 FLORIS 工程尾流模型占位；待袁夫达/厉今飞/洪祖名提供真实模型与优化结果后，按上述契约替换即可。
