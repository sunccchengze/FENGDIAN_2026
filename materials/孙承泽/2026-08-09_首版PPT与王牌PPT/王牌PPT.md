<!-- markitdown-mirror: source="王牌PPT.pptx" sha256="7f61c96545f2" generated="2026-09-21" | 只读镜像，正文由 microsoft/markitdown 自动转换，以同目录原文件为准；重新生成：python3 tools/markitdown_sync.py -->

<!-- Slide number: 1 -->

全场净增益: +24.04% (+1946.3 kW)
08 / ARRAY TOPOLOGY · MULTI-TURBINE COLLABORATIVE WAKE STEERING
3×3 九机阵列阶梯协同偏航全景拓扑与能量倍增解析
物理机理：前排偏航 +30° 开启主通道 → 中排偏航 +20° 二次导流借道穿行 → 后排 0° 迎风满发，打通全场气动流动瓶颈
表 1. 3×3 九机阵列单机功率分布与排级出力汇总 (kW)

![scientific_cfd_fig.png](Picture7.jpg)
| 机组阵列 | Col 1 | Col 2 | Col 3 | 排级合计 |
| --- | --- | --- | --- | --- |
| Row 1 (30°) | 1340 kW | 1340 kW | 1340 kW | 4020 kW |
| Row 2 (20°) | 909 kW | 935 kW | 943 kW | 2787 kW |
| Row 3 ( 0°) | 1060 kW | 1088 kW | 1086 kW | 3234 kW |

![scientific_bar_fig.png](Picture11.jpg)
【优化模型与求解收敛】
• 目标函数：max_γ ∑ P_i(γ_1, γ_2, γ_3)，γ_i ∈ [-30°, +30°]• 寻优结果：最优偏航向量 γ* = [30.0°, 20.0°, 0.0°]• 算法特性：FLORIS GCH + 逐排贪心搜索，单次评估耗时 < 1.5 ms• 能量重构：后排出力占比由基准的 18.8% 跃升至 32.2%，实现全场最优功率跃迁。
【阵列几何与流场特征】顺风间距 5D (630 m)，横向间距 3D (378 m)。基准状态下中下游机组遭受强尾流双重叠加，轮毂风速由 8.0 m/s 衰减至 3.6 m/s；阶梯偏航 [30°, 20°, 0°] 将前中排高亏损尾流核心精准偏转至列间空隙，实现后排机组迎风风速恢复至 7.2 m/s。
