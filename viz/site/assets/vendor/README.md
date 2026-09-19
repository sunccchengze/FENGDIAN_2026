# 本地浏览器依赖

静态站为断网演示锁定以下浏览器依赖，不再从 CDN 请求：

| 目录 | 版本 | 来源 | 协议 |
|---|---:|---|---|
| `plotly/` | 2.35.2 | `plotly.js-dist-min` npm 包 | MIT |
| `three/` | 0.160.0 | `three` npm 包 | MIT |

各目录保留上游许可证。字体 `assets/fonts/geist/` 来自 npm 包 `geist@1.7.2`，使用 SIL Open Font License。升级依赖时必须同步修改文件名、HTML 引用和 `verify_all_pages.py` 的锁定清单。
