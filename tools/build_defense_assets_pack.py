#!/usr/bin/env python3
"""把做答辩 PPT 可能用到的**所有图像素材**打成一个包，并生成中文图名索引。

为什么要有这个脚本
------------------
素材散在 8 个目录里（答辩整页图 / 论文插图 / 数字孪生截图 / Fluent 与 FLORIS 流场 /
控制结果图 / 示意图 / 科普插图）。人找图靠记路径，答辩前一小时最容易在这里浪费时间。
本脚本做三件事：

1. **归类**：按「这图在答辩里干什么」分成 7 个文件夹，文件名统一改成
   `编号_中文图名.png`，不再出现 `after_r10_wide_noloop` 这种只有作者看得懂的名字；
2. **瘦身**：截图类资源改成 JPEG（长边 ≤ 1600 px），图表类保留原 PNG 不重压缩；
3. **出索引**：`00_索引/INDEX.md` + `INDEX.csv`，逐条写清「图名 / 讲什么 / 建议放第几页 / 不能说什么」。

输出：`docs/defense/defense_assets_pack_20261026.zip`

用法
----
    python3 tools/build_defense_assets_pack.py            # 打包
    python3 tools/build_defense_assets_pack.py --list     # 只打印清单，不打包

原则：**只读**既有素材，不重画任何图；截图只做缩放与转码，不改内容。
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "defense" / "defense_assets_pack_20261026.zip"
GEN = ROOT / "docs" / "defense" / "assets" / "generated"
PAPER = ROOT / "docs" / "defense" / "assets" / "paper"
EXTRACTED = ROOT / "docs" / "defense" / "assets" / "extracted"
ANIMATED = ROOT / "docs" / "defense" / "assets" / "animated"
SHOTS = ROOT / "docs" / "research" / "shots"
UISHOTS = ROOT / "docs" / "screenshots"
CFD = ROOT / "materials" / "田铭雨" / "20261024_三机串列双模型对比"
YUAN = ROOT / "materials" / "袁夫达" / "20261025_仿真建模数据交接" / "figures"
FLORIS = ROOT / "materials" / "袁夫达" / "20260808_FLORIS数据生成" / "extracted"
NATURE = ROOT / "viz" / "figures_nature"
MIDTERM = ROOT / "optimization_control" / "experiments" / "20261022_midterm_figures"
LIJINFEI = ROOT / "materials" / "厉今飞" / "20260808_功率预测神经网络基线"
WP = ROOT / "materials" / "孙承泽" / "自学白皮书" / "images"

# ── 01 答辩整页图（g01–g37）──────────────────────────────────────────────
# (编号, 中文图名, 讲什么, 建议页)
G_FIGS = [
    ("g01", "尾流损失", "串列布局尾流吃掉 48.6% 功率（5262→2702 kW）", "p2"),
    ("g02", "统一偏航扫描与逐台贪心", "0°→+20° 为 +15.0%，逐台贪心 30/25/0 为 +22.11%", "p2 追问"),
    ("g03", "偏航把尾流推开", "尾流中心偏移 −3→−62 m，最低风速 4.1→5.4 m/s（示意，非流场重建）", "p2 追问"),
    ("g04", "四模块技术路线与完成度", "四个框分开标完成度，不做一根箭头糊过去", "p3"),
    ("g05", "四种代理模型对比", "两阶段 29/36 kW，MLP 232/236 kW；交叉验证，不是独立测试", "p4"),
    ("g06", "方法谱系与自己的位置", "文献四类做法 + 本项目的落点（有意不报外部数值）", "p4"),
    ("g07", "PINN 冻结主干迁移", "3,090,200 冻结 + 27,106 可训练；loss 1.01→0.019；MAE 51.0/48.3/44.5 kW", "p7"),
    ("g08", "五段数据流架构", "每步 1 s、128 步一回合；「跑通」不等于「物理精度」", "p8"),
    ("g09", "七步演示界面", "演示关键帧 4 张；三段计时是浏览器实测，不是控制周期", "p9 备用"),
    ("g10", "三条流训练收敛", "471.79/444.14/433.65 kW，均未过 400 kW 目标", "p4/p13"),
    ("g11", "独立测试控制器对比", "1083.6/1100.3/552.4/477.5/449.7±40.1 kW", "p8"),
    ("g12", "按来流族拆开", "阵风 406 vs 453、平稳 511 vs 562、慢变 432 vs 417（慢变落后）", "p8 展开"),
    ("g13", "三处没达标", "低风 1727.9 vs 1383.3；慢变 432.1 vs 417.2；高目标 24.0 vs 10.4", "p10"),
    ("g14", "四条可复算证据链", "161/158 项；30,720 行差 0 W；1.25e-12 kW；28 份记录", "p12"),
    ("g15", "证据等级定位（国际 vs 我们）", "只列名不列数；不说「达到国际水平」", "p12 备选"),
    ("g16", "后续三段时间表", "10-31 / 11-30 / 12-31 / 2027-06，计划值不是承诺", "p11"),
    ("g17", "数据集覆盖", "1,224 条；17 档风速 × 24 风向 × 3 档 TI；标签来自 FLORIS", "p7"),
    ("g18", "PINN 结构改造", "12 输入 / 6 输出；不新增隐藏层、复用主干", "p6"),
    ("g19", "Fluent 现状与卡点", "三机 3D 378 m、1,055,511 单元、双湍流模型；单机推力 388.0/378.7 kN", "p5"),
    ("g20", "偏航收益账：上游少发、下游多发", "+25° 时上游 −295 kW、下游 +473 kW、合计 +178 kW（+8.1%）", "p2"),
    ("g21", "两条控制线（偏航 / 桨距）分开讲", "偏航 +22.11%；桨距误差 1083.6→449.7（−58.5%），两数不相加", "p8 追问"),
    ("g22", "五条卡点与下一步", "标签全是代理、尾流区 13 m 网格、三条流未过 400、口径未冻结、验收带差异明显", "p10"),
    ("g23", "界面实拍与面板值含义对照", "模型建议 3,299.8 kW、优化计时 5.5 ms；左栏 1.2 MW 是带角标的占位值", "p9"),
    ("g24", "同一工况的功率跟踪对比", "阵风 2.7 MW：初始 1543 / PI 512 / 训练后 376 kW；慢变反而落后", "p9 追问"),
    ("g25", "三项阶段技术贡献", "接口适配 / 统一执行器 / 冻结测试回放；说「能复算的评估链」", "备选页"),
    ("g26", "CFD 尾流中心线", "1D 处降到 4.5 m/s；第 2/3 台位置各压一个台阶；>7D 两模型差 3%–4%", "p5"),
    ("g27", "CFD 盘面柱状对比", "盘面速度差不到 1%，盘面 TI 差 32%–45%", "p5"),
    ("g28", "CFD 尾流横向剖面", "2D 有回流区，8D 才恢复到来流八成", "备用"),
    ("g29", "来流方向扫描（尾流损失）", "正对丢 38%、侧向只丢 2%（2249/2230 vs 3634 kW）", "p7"),
    ("g30", "数据集口径自检（反算 Cp）", "分三层带、不过 0.457 上限 → 三台机同一把尺子", "备用"),
    ("g31", "TI 敏感性", "TI 6%→10%，正对来流总功率高 2.5%–5.1%", "p7"),
    ("g32", "逐场配对胜负", "18 场 12 胜 6 负；449.7 vs 477.5 kW（−5.8%）；最大落后 +172 kW", "p9"),
    ("g33", "六工况跟踪小倍数", "阵风 2.7 MW 目标下训练后 376 kW；慢变高目标落后", "p9"),
    ("g34", "执行器约束核对", "偏航/转速在上限内；桨距实际角速度超上限 11.8 倍（82% 步越界）", "追问"),
    ("g35", "单场三机分解", "三机合计 2.0–3.8 MW；下游两台长期低 1–2 m/s", "追问"),
    ("g36", "PINN 训练诊断", "loss 0.700→0.0084（降 83×）；MAE 40.9/55.0/56.7 kW；负输出 445 条", "p13"),
    ("g37", "四项指标并排", "赢两项（RMSE/MAE）、输两项（尾段误差 +16.8%、缺额 +121%）", "p9 追加"),
]

# ── 02 论文插图（fig01–fig14）────────────────────────────────────────────
P_FIGS = [
    ("fig01", "设计空间热图（风速×风向 / 风速×TI）", "覆盖 8 档风速 × 30 风向 × 3 档 TI", "论文"),
    ("fig02", "五种偏航策略功率曲线", "偏航一律低于对齐，仅作余弦损失旁证", "论文"),
    ("fig03", "湍流强度敏感性", "TI 6%→10%，8 m/s 处 2194→2305 kW", "论文"),
    ("fig04", "尾流中心线与两模型偏差", "近场重合、远场差 3%–4%；单条取样线不是流场重建", "论文"),
    ("fig05", "三机盘面速度极坐标", "逐单元波动大，不要按等值线读流场结构", "论文"),
    ("fig06", "盘面湍流强度径向分布", "k-ω 明显高于 k-ε，差 32%–45%", "论文"),
    ("fig07", "四控制器 RMSE 箱线", "平稳 516、阵风 406 最好；慢变 465 输给 PI 441", "论文"),
    ("fig08", "跟踪误差累积分布", "小误差段整体左移，中段与 PI 有交叉", "论文"),
    ("fig09", "逐场配对散点（含差值边缘）", "12 胜 6 负；均值 449.7 vs 477.5 kW", "论文"),
    ("fig10", "训练收敛与参数冻结", "3.09 M 冻结 / 0.027 M 可训练", "论文"),
    ("fig11", "预测-真值一致性与残差", "R²=0.999、RMSE 142.8 kW；合成标签上的基线", "论文"),
    ("fig12", "执行器步进分布与上限", "桨距中位数已达上限 3.3 倍、最大 11.8 倍", "论文"),
    ("fig13", "来流方向极坐标功率", "串列正对 2249/2230 kW，侧向 3634 kW", "论文"),
    ("fig14", "反算 Cp 与桨距", "三台机塌缩到同一带，自洽 ≠ 效率实测", "论文"),
]

# ── 03 数字孪生截图 ────────────────────────────────────────────────────
TWIN_FULL = [
    ("after_hero_1920.png", "数字孪生主视图", "1920×1080 默认英雄机位，日间"),
    ("after_hero_noveil.png", "主视图（关尾流纱）", "与上图同机位、关闭尾流纱对照"),
    ("after_az92_east.png", "东侧视角", "三方位巡检之一"),
    ("after_az182_north.png", "北侧视角", "三方位巡检之一"),
    ("after_az272_west.png", "西侧视角", "三方位巡检之一"),
    ("baseline_dawn_0612.png", "黎明光照基线", "06:12 光照，用于说「昼夜与光照可切换」"),
    ("baseline_morning_0800.png", "清晨光照基线", "08:00 光照"),
    ("fog_before_022.png", "雾天（去雾前）", "雾密度 0.00022 的旧状态"),
    ("fog_after_013.png", "雾天（去雾后）", "雾密度 0.00013，当前验收态"),
    ("after_r10_substation.png", "升压站机位", "集电线路与升压站前景"),
    ("after_r10_wide_noloop.png", "广角无环线", "宽视角、不画环线的版本"),
    ("after_narrow_1280.png", "窄屏适配 1280", "等比居中、无溢出"),
    ("after_mobile_390.png", "竖屏适配 390", "竖屏提示条"),
]
TWIN_UI = [
    ("after_optimize.png", "一键寻优闭环实拍", "5 路滑杆停在 −1.5…−33°，功率 4.82→6.00 MW（+24.3%），wake 40.9%→26.5%"),
    ("after_curtail_12mw.png", "限功率指令 12 MW", "指令 12 MW → 全场 12.00 MW，9 机降容、DERATE 告警"),
    ("after_wake_veil_on.png", "尾流纱开启", "与下一张同 t 同相位的真 A/B"),
    ("after_wake_veil_off.png", "尾流纱关闭", "关纱对照，显著差异集中在轮毂高走廊与尾流羽带"),
    ("after_rotor_upwind_closeup.png", "转子迎风近景", "北侧见叶盘正面"),
    ("after_rotor_downwind_closeup.png", "转子背风近景", "南侧见机舱尾锥"),
]
DESIGN = [
    ("topbar_hitech_v2.png", "顶栏设计（科技版 v2）", "界面设计稿"),
    ("topbar_fix_v2.png", "顶栏修正稿", "界面设计稿"),
    ("beacon_night.png", "夜间信标灯", "航空障碍灯夜间效果"),
    ("beacon_feathered.png", "信标羽化", "灯晕羽化后的效果"),
    ("ground_continuous.png", "地面连续化", "海面/地面材质连续化"),
    ("ground_close_cont.png", "地面近景连续化", "近景地面材质"),
]

# ── 04 CFD 与流场 ──────────────────────────────────────────────────────
FLUENT = [
    (EXTRACTED / "fluent_velocity_contour.png", "Fluent 速度云图", "单机尾流速度场，只作「算出来了」的观感，不当精度证据"),
    (EXTRACTED / "fluent_contour_scene.png", "Fluent 流场场景", "整场视角的云图"),
    (EXTRACTED / "fluent_mesh_issue.png", "Fluent 网格问题", "尾流区网格 13 m、盘面 648 点四成越界——主动交代的卡点"),
    (EXTRACTED / "fluent_solver_settings.png", "Fluent 求解器设置", "求解器与湍流模型设置截图"),
    (YUAN / "fig09_fluent_single_wake.png", "单机尾流（Fluent 后处理）", "单机尾流轴向速度"),
]
FLOW = [
    (CFD / "comparison.png", "两湍流模型总对比", "三机串列 k-ω / k-ε 对比总图（来自数据交接方）"),
    (EXTRACTED / "floris_array_flowfield.png", "FLORIS 阵列流场", "3×3 阵列尾流叠加"),
    (EXTRACTED / "floris_power_curve.png", "FLORIS 功率曲线", "功率曲线校核"),
    (EXTRACTED / "floris_wake_profile.png", "FLORIS 尾流剖面", "尾流模型剖面"),
    (FLORIS / "output_cc" / "layout_visualization.png", "CC 场布局", "FLORIS 机位布局"),
    (FLORIS / "output_cc" / "wake_horizontal_slice_265.png", "CC 场水平切片 265°", "轮毂高度水平切片"),
    (FLORIS / "output_cc" / "wake_horizontal_slice_270.png", "CC 场水平切片 270°", "轮毂高度水平切片"),
    (FLORIS / "output_gch" / "layout_visualization.png", "GCH 场布局", "FLORIS 机位布局"),
    (FLORIS / "output_gch" / "wake_horizontal_slice_265.png", "GCH 场水平切片 265°", "轮毂高度水平切片"),
    (FLORIS / "output_gch" / "wake_horizontal_slice_270.png", "GCH 场水平切片 270°", "轮毂高度水平切片"),
]
YUAN_FIGS = [
    ("fig00_power_curve.png", "功率曲线（交付方）", "单机功率曲线"),
    ("fig01_cp_ct_surface.png", "Cp–Ct 曲面", "反算口径的曲面"),
    ("fig02_power_blocks.png", "功率分块", "数据分块方式"),
    ("fig03_vs_official.png", "与官方曲线对比", "与参考功率曲线比对"),
    ("fig04_farm_vs_wd.png", "全场功率随来流方向", "方向扫描"),
    ("fig05_gch_cc.png", "GCH 与 CC 两场对比", "两个算例规模对比"),
    ("fig06_consistency.png", "口径一致性检查", "同一把尺子的自检"),
    ("fig10_training_curve.png", "训练曲线（交付方）", "代理模型训练"),
    ("fig11_parity.png", "预测-真值（交付方）", "代理模型 parity"),
    ("fig14_response_check.png", "响应核对", "输入扰动响应"),
]
# viz/figures_nature：Nature 级科研绘图工厂产出（17 张），含义见同目录 README
NATURE_FIGS = [
    ("fig1_tandem_yaw.png", "两机串列偏航优化", "P1/P2/Ptot 随偏航 + 增益，最优 25°"),
    ("fig2_multi_wind.png", "多风速偏航增益矩阵", "yaw×U∞ 增益热图 + 定风速切片"),
    ("fig3_array.png", "3×3 阵列统一 vs 独立", "总功率柱 + 9 机单机功率"),
    ("fig4_wake_contour.png", "0° vs 25° 流场", "尾流横向偏转放行物理"),
    ("fig5_pod.png", "POD 模态", "前 2 阶累积 97.97%"),
    ("fig6_array_flow.png", "阵列流场 baseline vs independent", "走廊清除效果"),
    ("fig7_windrose.png", "最优增益随风向", "0° 无增益、90° 最大"),
    ("fig8_main.png", "主图（四合一）", "偏航优化全链路"),
    ("fig9_tracking.png", "跟踪效果", "PPO 跟踪历史工作"),
]
NATURE_EXT = [
    ("fig10_gain_box_strip.png", "增益箱线 + 散点", "多风速增益分布"),
    ("fig11_corr.png", "相关性矩阵", "变量相关性"),
    ("fig12_hist.png", "增益直方图", "增益分布"),
    ("fig13_3d_gain.png", "三维增益曲面", "yaw×风速×增益"),
    ("fig14_pod_coeff.png", "POD 系数", "模态系数随工况"),
    ("fig15_waterfall.png", "瀑布图", "逐机增益分解"),
    ("fig16_array_sweep.png", "阵列扫描", "统一偏航扫描"),
    ("fig17_ppo_mae.png", "PPO 跟踪 MAE", "标注为 8 月工作"),
]

# ── 05 控制与优化结果图 ────────────────────────────────────────────────
MIDTERM_FIGS = [
    ("01_closed_loop.png", "闭环总览", "五段数据流闭环示意"),
    ("02_random_inflow.png", "随机来流训练", "随机化训练过程"),
    ("03_validation_learning.png", "验证与学习曲线", "训练/验证同屏"),
    ("04_independent_test.png", "独立测试", "三种控制器对比"),
    ("05_scenario_breakdown.png", "场景拆分", "按来流族拆分"),
    ("06_power_tracking.png", "功率跟踪过程", "同一工况跟踪曲线"),
    ("07_actuator_replay.png", "执行器回放", "指令 vs 实际"),
]
NN_FIGS = [
    (LIJINFEI / "output_gch" / "wind_farm_results" / "training_curve.png", "GCH 算例训练曲线", "功率预测基线"),
    (LIJINFEI / "output_gch" / "wind_farm_results" / "true_vs_pred_farm_power.png", "GCH 全场预测-真值", "R²=0.999（合成标签）"),
    (LIJINFEI / "output_cc" / "wind_farm_results" / "training_curve.png", "CC 算例训练曲线", "功率预测基线"),
    (LIJINFEI / "output_cc" / "wind_farm_results" / "true_vs_pred_farm_power.png", "CC 全场预测-真值", "功率预测基线"),
]

# ── 06 示意图与素材 ────────────────────────────────────────────────────
SCHEMA = [
    (EXTRACTED / "control_architecture_ppo.png", "PPO 控制架构", "策略网络 + 环境接口"),
    (EXTRACTED / "turbine_model_render.png", "机组三维模型渲染", "机型外观"),
    (EXTRACTED / "turbine_blade_closeup.png", "叶片近景", "翼型与叶片细节"),
    (EXTRACTED / "ui_3x3_overview_0823.jpg", "3×3 阵列总览界面（08-23）", "早期界面总览"),
    (EXTRACTED / "ui_demo_early_deck.png", "早期演示界面", "与 g23 对照可讲「界面演进」"),
]

# ── 07 科普插图（白皮书）──────────────────────────────────────────────
WP_FIGS = [
    ("wp_cover_hero.png", "白皮书封面主图", "风机 + 风场意象"),
    ("wp_01_wake_zh.png", "尾流是什么", "尾流概念图解"),
    ("wp_01_comic_zh.png", "尾流漫画", "科普向"),
    ("wp_02_yaw_zh.png", "偏航与尾流转向", "偏航改变尾流方向"),
    ("wp_02_mindmap_zh.png", "知识地图（总）", "学习路径"),
    ("wp_03_floris_zh.png", "FLORIS 是什么", "工程尾流模型"),
    ("wp_04_solver_zh.png", "求解器与 CFD", "数值求解概念"),
    ("wp_05_ladder_zh.png", "技术阶梯", "从机理到控制"),
    ("wp_06_windrose_zh.png", "风玫瑰图", "风向统计"),
    ("wp_07_pod_zh.png", "POD 降维", "模态分解直觉"),
    ("wp_08_pipeline_zh.png", "数据流水线", "从数据到策略"),
    ("wp_09_ppo_zh.png", "PPO 强化学习", "策略梯度直觉"),
    ("wp_10_reachdomain_zh.png", "到达域", "控制可达范围"),
    ("wp_11_site_zh.png", "风场与机位", "布局概念"),
    ("wp_12_audit_zh.png", "复算与审计", "可复算证据"),
    ("wp_60_knowledge_map_zh.png", "知识地图（详版）", "全章串联"),
    ("wp_ch0_mindmap_zh.png", "绪论思维导图", "开场可用"),
    ("wp_ch0_subway_zh.png", "技术地铁图", "章节关系"),
    ("wp_ch0_turbine_zh.png", "风机结构解剖", "机组组成"),
]


def _safe(name: str) -> str:
    """文件名里不能出现路径分隔符与冒号，否则解压时会变成子目录。"""
    for a, b in (("/", "·"), ("\\", "·"), (":", "·"), ("*", ""), ("?", ""),
                 ('"', ""), ("<", ""), (">", ""), ("|", "")):
        name = name.replace(a, b)
    return name.strip()


def _prepare_jpeg(src: Path, dst: Path, maxw: int = 1600, quality: int = 88) -> None:
    from PIL import Image

    im = Image.open(src).convert("RGB")
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=quality, optimize=True)


def collect() -> list[dict]:
    """返回 [{cat, group, src, name, title, desc, page, tag}]，name 是包内文件名。"""
    items: list[dict] = []

    for gid, title, desc, page in G_FIGS:
        srcs = sorted(GEN.glob(f"{gid}_*.png"))
        if not srcs:
            continue
        items.append(dict(cat="01_答辩整页图", group="", src=srcs[0],
                          name=f"{gid}_{title}.png", title=title, desc=desc, page=page,
                          tag="16:9 整页 · 已带角标与读法行"))

    for f in sorted(ANIMATED.glob("*.gif")):
        title = "七步演示动图" if "seven" in f.name else "偏航扫描动图"
        items.append(dict(cat="01_答辩整页图", group="动图", src=f, name=f.name,
                          title=title, desc="答辩播放用，PPT 可插入", page="p9",
                          tag="GIF"))

    for fid, title, desc, page in P_FIGS:
        srcs = sorted(PAPER.glob(f"{fid}_*.png"))
        if not srcs:
            continue
        items.append(dict(cat="02_论文插图", group="", src=srcs[0],
                          name=f"{fid}_{title}.png", title=title, desc=desc, page=page,
                          tag="论文用 · 无页眉角标 · 400 dpi"))

    for i, (f, title, desc) in enumerate(TWIN_FULL, 1):
        items.append(dict(cat="03_数字孪生页面截图", group="整页视角", src=SHOTS / f,
                          name=f"{i:02d}_{title}.jpg", title=title, desc=desc, page="p9",
                          tag="截图 · 图上「0000」类方块是软渲染缺字伪影，别引用图上数字"))
    for i, (f, title, desc) in enumerate(TWIN_UI, 1):
        items.append(dict(cat="03_数字孪生页面截图", group="功能交互", src=SHOTS / f,
                          name=f"{i:02d}_{title}.jpg", title=title, desc=desc, page="p9",
                          tag="界面演示 · 数值是演示值不是实验结论"))
    for i, (f, title, desc) in enumerate(DESIGN, 1):
        items.append(dict(cat="03_数字孪生页面截图", group="界面设计稿", src=UISHOTS / f,
                          name=f"{i:02d}_{title}.jpg", title=title, desc=desc, page="p9 追问",
                          tag="设计稿 · 非最终页面"))

    for src, title, desc in FLUENT:
        if src.exists():
            items.append(dict(cat="04_CFD与流场", group="Fluent", src=src,
                              name=f"{title}.png", title=title, desc=desc, page="p5",
                              tag="云图不当精度证据"))
    for src, title, desc in FLOW:
        if src.exists():
            items.append(dict(cat="04_CFD与流场", group="FLORIS 与流场切片", src=src,
                              name=f"{title}.png", title=title, desc=desc, page="p5/p7",
                              tag="合成数据"))
    for f, title, desc in YUAN_FIGS:
        src = YUAN / f
        if src.exists():
            items.append(dict(cat="04_CFD与流场", group="交付方原始图（袁夫达）", src=src,
                              name=f"{title}.png", title=title, desc=desc, page="p7",
                              tag="交付方原图"))
    for f, title, desc in NATURE_FIGS:
        src = NATURE / f
        if src.exists():
            items.append(dict(cat="04_CFD与流场", group="科研绘图（两机/阵列）", src=src,
                              name=f"{title}.png", title=title, desc=desc, page="p2 备选",
                              tag="两机/阵列历史工作"))
    for f, title, desc in NATURE_EXT:
        src = NATURE / "extended" / f
        if src.exists():
            items.append(dict(cat="04_CFD与流场", group="科研绘图（两机/阵列）", src=src,
                              name=f"{title}.png", title=title, desc=desc, page="备选",
                              tag="两机/阵列历史工作"))

    for f, title, desc in MIDTERM_FIGS:
        src = MIDTERM / f
        if src.exists():
            items.append(dict(cat="05_控制与优化结果图", group="中期实验图", src=src,
                              name=f"{title}.png", title=title, desc=desc, page="p8/p9",
                              tag="实验产出"))
    for src, title, desc in NN_FIGS:
        if src.exists():
            items.append(dict(cat="05_控制与优化结果图", group="功率预测基线", src=src,
                              name=f"{title}.png", title=title, desc=desc, page="p13",
                              tag="合成标签"))

    for src, title, desc in SCHEMA:
        if src.exists():
            ext = src.suffix.lower()
            items.append(dict(cat="06_示意图与素材", group="", src=src,
                              name=f"{title}{ext}", title=title, desc=desc, page="任意",
                              tag="示意图"))

    for f, title, desc in WP_FIGS:
        src = WP / f
        if src.exists():
            items.append(dict(cat="07_科普插图", group="", src=src,
                              name=f"{title}.jpg", title=title, desc=desc, page="p2 开场可选",
                              tag="科普 · 非实验证据（已转 JPEG 瘦身）"))
    return items


def main(argv: list[str]) -> int:
    items = collect()
    cats: dict[str, list[dict]] = {}
    for it in items:
        it["name"] = _safe(it["name"])
        cats.setdefault(it["cat"], []).append(it)

    print(f"共 {len(items)} 个文件，{len(cats)} 个分类：")
    for c, lst in cats.items():
        print(f"  {c}: {len(lst)}")
    if "--list" in argv:
        for it in items:
            print(f"{it['cat']}/{it['group']}/{it['name']}")
        return 0

    hist = sorted(p for p in SHOTS.glob("*.png")
                  if p.name not in {f for f, _t, _d in TWIN_FULL + TWIN_UI})

    index_md = io.StringIO()
    index_csv = io.StringIO()
    w = csv.writer(index_csv)
    w.writerow(["分类", "子目录", "包内文件名", "图名", "讲什么", "建议页", "标注"])

    index_md.write("# 答辩 PPT 素材总索引（2026-10-26）\n\n")
    index_md.write("> 一个包搞定「做 PPT 时可能用到的所有图」。分类按**这图在答辩里干什么**分，"
                   "文件名是 `编号_中文图名`，图名与用途逐条列在下面。\n>\n"
                   "> 三条纪律：① 图上的数就是索引里的数；② 「标注」一列写的是这张图的边界，"
                   "口播不能越过去；③ 数字孪生截图里的功率/计时是**界面演示值**，不是实验结论。\n\n")
    index_md.write("| 分类 | 文件数 | 说明 |\n|---|---:|---|\n")
    notes = {
        "01_答辩整页图": "16:9 整页图 g01–g37（含角标与读法行），插进 PPT 直接用",
        "02_论文插图": "期刊 figure fig01–fig14，无页眉角标，投稿与正文用",
        "03_数字孪生页面截图": "可视化页面实拍：整页视角 / 功能交互 / 界面设计稿 / 历史迭代"
                               "（沙箱软渲染会在个别数字处缺字，图上数字不可直接引用）",
        "04_CFD与流场": "Fluent 云图与网格、FLORIS 流场切片、交付方原始图、两机/阵列科研图",
        "05_控制与优化结果图": "中期实验七图 + 功率预测基线图",
        "06_示意图与素材": "架构图、机组渲染、早期界面截图",
        "07_科普插图": "白皮书科普插图，开场破题或讲背景时用",
    }
    for c, lst in cats.items():
        index_md.write(f"| {c} | {len(lst)} | {notes.get(c, '')} |\n")
    index_md.write("\n")

    for c, lst in cats.items():
        index_md.write(f"\n## {c}\n\n")
        head = "| 文件 | 图名 | 讲什么 | 建议页 | 标注 |\n|---|---|---|---|---|\n"
        groups: dict[str, list[dict]] = {}
        for it in lst:
            groups.setdefault(it["group"], []).append(it)
        for grp, gl in groups.items():
            if grp:
                index_md.write(f"### {grp}\n\n")
            index_md.write(head)
            for it in gl:
                index_md.write(f"| `{it['name']}` | {it['title']} | {it['desc']} | "
                               f"{it['page']} | {it['tag']} |\n")
                w.writerow([c, grp, it["name"], it["title"], it["desc"], it["page"], it["tag"]])
            index_md.write("\n")

    index_md.write(
        "\n### 历史迭代备查（%d 张）\n\n"
        "`03_数字孪生页面截图/04_历史迭代备查/` 里是 r4→r40 各轮视觉迭代的原始截图（已缩到 1100 px JPEG），"
        "文件名即轮次；**每张的含义逐条写在同目录 `附_截图验货记录.md`**（该文件从 `docs/research/shots/README.md` 原样带入）。"
        "这些图**不进正文页**，只在被追问「界面怎么迭代出来的」时翻。\n\n" % len(hist))

    index_md.write("""
## 附录：几个常见用法

1. **只要一页一张图**：从 `01_答辩整页图` 里按「建议页」取，`g01/g04/g07/g08/g09/g11/g13/g22` 是保底组合。
2. **要纯论文风**（无角标、无读法行）：用 `02_论文插图`，14 张都配了 caption，见仓库 `docs/defense/paper_captions.md`。
3. **讲系统/可视化**：`03_数字孪生页面截图/整页视角` 3 张起，`功能交互` 里挑寻优、限功率、尾流纱 A/B。
4. **讲仿真**：`04_CFD与流场/Fluent` 只放云图观感，数字一律来自 `g19`/`g26`/`g27`。
5. **历史迭代截图**（`03_数字孪生页面截图/04_历史迭代备查`）**不放进正文页**，只在被问「这界面怎么来的」时翻。
""")

    # 同一份索引也落到仓库里，不打开 zip 也能查
    idx_path = ROOT / "docs" / "defense" / "2026-10-26_素材总索引.md"
    idx_path.write_text(index_md.getvalue(), encoding="utf-8")
    (ROOT / "docs" / "defense" / "2026-10-26_素材总索引.csv").write_text(
        "\ufeff" + index_csv.getvalue(), encoding="utf-8")

    total = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("00_索引/INDEX.md", index_md.getvalue())
        z.writestr("00_索引/INDEX.csv", "\ufeff" + index_csv.getvalue())
        z.writestr("00_索引/README_怎么用.md", index_md.getvalue().split("## 附录")[0])
        for it in items:
            src: Path = it["src"]
            arc = f"{it['cat']}/{it['group'] + '/' if it['group'] else ''}{it['name']}"
            if it["name"].endswith(".jpg"):
                tmp = Path("/tmp/_pack_jpg.jpg")
                _prepare_jpeg(src, tmp)
                z.write(tmp, arc)
                total += tmp.stat().st_size
            else:
                z.write(src, arc)
                total += src.stat().st_size

        # 历史迭代截图：整目录瘦身后放进「04_历史迭代备查」
        for p in hist:
            tmp = Path("/tmp/_pack_hist.jpg")
            _prepare_jpeg(p, tmp, maxw=1100, quality=78)
            z.write(tmp, f"03_数字孪生页面截图/04_历史迭代备查/{p.stem}.jpg")
            total += tmp.stat().st_size
        # 附：截图验货记录（解释每个 rXX / after_* 的含义）
        for extra, arc in (
            (SHOTS / "README.md", "03_数字孪生页面截图/04_历史迭代备查/附_截图验货记录.md"),
            (NATURE / "README.md", "04_CFD与流场/科研绘图（两机/阵列）/附_图说明.md"),
        ):
            if extra.exists():
                z.write(extra, arc)

    size = OUT.stat().st_size / 1e6
    print(f"\n写出 {OUT.relative_to(ROOT)}：{size:.1f} MB，"
          f"{len(items) + len(hist) + 5} 个条目（历史迭代 {len(hist)} 张 JPEG）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
