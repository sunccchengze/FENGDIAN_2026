#!/usr/bin/env python3
"""从仓库里的 .docx / .pptx 中提取可上屏的图片，存到 docs/defense/assets/extracted/。

为什么需要这一步：Fluent 截图、早期 PPT 里的界面截图都封在 Office 文件里，
答辩时没法直接用；解出来一份小图，PPT 里插图就不用再开原文件。

只提取白名单里的图，其余（聊天截图、别人的私有截图）一律不提。
每张图在 ASSETS_INDEX.md 里都有来源与可用性说明。

用法：
    python3 tools/extract_defense_assets.py
"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/defense/assets/extracted"

# (源文件, 包内路径, 输出名, 说明)
ITEMS = [
    # ── 田铭雨：Fluent 仿真（NREL-5MW 双机串列 MRF）
    ("materials/田铭雨/田铭雨——仿真阶段记录.docx", "word/media/image1.png",
     "fluent_contour_scene.png", "Fluent 求解窗口：双机串列、速度云图与残差曲线"),
    ("materials/田铭雨/田铭雨——仿真阶段记录.docx", "word/media/image4.png",
     "fluent_velocity_contour.png", "Fluent 速度云图：上游机尾流进入下游机"),
    ("materials/田铭雨/田铭雨——仿真阶段记录.docx", "word/media/image2.png",
     "fluent_solver_settings.png", "Fluent 松弛因子设置（伪时间稳态）"),
    ("materials/田铭雨/fluent仿真疑问.docx", "word/media/image2.png",
     "fluent_mesh_issue.png", "网格与求解设置疑问（向导师提问时的截图）"),
    # ── 袁夫达：建模与 FLORIS 数据生成
    ("materials/袁夫达/建模与数据生成.docx", "word/media/image7.png",
     "turbine_model_render.png", "NREL-5MW 整机几何（叶轮 + 塔架）"),
    ("materials/袁夫达/建模与数据生成.docx", "word/media/image8.png",
     "turbine_blade_closeup.png", "叶片几何近景"),
    ("materials/袁夫达/建模与数据生成.docx", "word/media/image6.png",
     "floris_array_flowfield.png", "FLORIS 3×3 阵列流场（不同偏航对比）"),
    ("materials/袁夫达/建模与数据生成.docx", "word/media/image4.png",
     "floris_power_curve.png", "功率曲线与推力系数曲线"),
    ("materials/袁夫达/建模与数据生成.docx", "word/media/image5.png",
     "floris_wake_profile.png", "单机尾流速度亏损剖面"),
    # ── 洪祖名：优化控制结构图
    ("materials/洪祖名/洪祖名——工作记录.docx", "word/media/image1.png",
     "control_architecture_ppo.png", "PPO 控制模块结构（ActionMapper / ActuatorModel / PlantModel）"),
    # ── 早期 PPT：界面截图
    ("materials/孙承泽/2026-08-09_首版PPT与王牌PPT/王牌PPT.pptx", "ppt/media/image1.png",
     "ui_demo_early_deck.png", "早期答辩 PPT 里的界面截图（含人物，慎用）"),
    ("materials/孙承泽/2026-08-23_组会汇报/8.23组会汇报_可视化暑期进展_孙承泽.pptx",
     "ppt/media/image1.jpg", "ui_3x3_overview_0823.png", "8.23 组会用的 3×3 全景界面截图"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for src, member, name, _ in ITEMS:
        path = ROOT / src
        if not path.exists():
            print(f"跳过（源文件不存在）：{src}")
            continue
        with zipfile.ZipFile(path) as zf:
            try:
                data = zf.read(member)
            except KeyError:
                print(f"跳过（包内无 {member}）：{src}")
                continue
        target = OUT / name
        target.write_bytes(data)
        total += len(data)
        print(f"  {name:32s} {len(data) / 1024:7.0f} KB  ← {src}")
    print(f"\n{total / 1024 / 1024:.1f} MiB，共 {len(list(OUT.glob('*')))} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
