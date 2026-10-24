# 答辩素材目录

三层，都是**图**，不是成品 PPT。

| 目录 | 内容 | 数量 | 产生方式 |
|---|---|---:|---|
| [`generated/`](generated/) | 本轮新画的 16:9 答辩图（1920×1080） | 22 | `python3 tools/make_defense_figures.py` |
| [`animated/`](animated/) | 两个 GIF（七步演示、偏航扫描） | 2 | `python3 tools/make_defense_figures.py gif` |
| [`extracted/`](extracted/) | 从 .docx / .pptx 里解出来的原图 | 12 | `python3 tools/extract_defense_assets.py` |

**每张图配哪一页、能支持什么结论、不能说什么** → [`../2026-10-23_答辩素材清单.md`](../2026-10-23_答辩素材清单.md)。

两条纪律：

1. **不要手改 PNG。** 数字要改就改脚本里的常量再重画，否则图与数据脱钩。
2. **图上的角标要与口播一致。** 「模拟真值 · FLORIS」不能说成实测；「合成标签 · 非物理精度」不能省掉这半句。

## 整包下载

全部素材打成一个 zip，随仓库一起推：`../defense_assets_20261024.zip`（7.7 MiB）。
重打用 `python3 tools/build_defense_pack.py`，它会顺带做完整性、清单、格式与尺寸自检。
