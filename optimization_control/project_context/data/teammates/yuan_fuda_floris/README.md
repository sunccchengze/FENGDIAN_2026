# 袁夫达 — FLORIS 数据

## 目录说明

```
yuan_fuda_floris/
├── README.md      # 本文件
├── 说明.docx      # 袁夫达原始数据说明（2026-08-06 自 floris.zip 解压）
├── raw/           # 原始生成数据
│   ├── gch/       #   GCH（Gauss-Curl-Hybrid，高斯-卷曲混合）尾流模型
│   └── cc/        #   CC（Cumulative-Curl，累积卷曲）尾流模型
├── processed/     # 统一格式、清洗后的数据（供模型训练直接用，暂空）
└── scripts/       # FLORIS 调用与批处理脚本（zip 未包含，待袁夫达补充）
```

## 数据内容

- 来源：调用 FLORIS 内置尾流模型（GCH / CC），基于多种风况批量生成风机功率数据
- 说明：GCH 与 CC 精度不同（CC 对深阵列效应建模更准）。在 CFD 高保真数据产出前，
  可通过优化模型函数/参数提升数据精度，作为后续推进方向
- 字段、风况范围、风机布局、单位等：待袁夫达补充到下方「数据说明」并在每个文件旁附 `.json`

## 数据说明（袁夫达填写）

- FLORIS 版本：**v4.6.6**（NREL FLORIS，仓库 NatLabRockies/floris）
- 尾流模型：**GCH**（Gauss-Curl-Hybrid，更泛用）与 **CC**（Cumulative-Curl，精度更高），两套独立生成
- 风况范围：
  - 风速 4~12 m/s（步长 0.5，共 17 档）
  - 风向 0~345°（步长 15°，共 24 档）
  - 湍流强度 [0.06, 0.08, 0.10]（3 档）
  - 合计 **1224 条/套**（17×24×3）
- 风机布局与机型：NREL 5MW × 3 台，间距 378m（3D），沿 X 轴排列
  （注：NREL 5MW 全套参数面向海上风电，陆上应用需调整）
- 输出字段（CSV 实际列名，英文）：`wind_speed, wind_direction, turbulence_intensity,
  turbine_1_power(W), turbine_2_power(W), turbine_3_power(W), farm_power(W)`
- 每文件格式：`training_data_{gch|cc}.csv`，一行一个风况样本
- 数据质量：GCH 含 22 行零功率、CC 含 4 行零功率（某风机功率为 0）；
  零功率行在模型训练时已剔除（见 `li_jinfei_nn/README.md`）

## 更新记录

| 日期 | 更新内容 |
|------|----------|
| 2026-08-06 | 从 `floris.zip` 解压：说明.docx + raw/gch、raw/cc（数据+可视化图） |
| 2026-08-23 | 复核两套 CSV 均为 1224×7；GCH/CC 零功率行分别 22/4；确认没有偏航/桨距/转速列及同名 JSON |

## 控制模块可用性结论（2026-08-23）

当前 CSV 的原始输入只有 `wind_speed`、`wind_direction`、`turbulence_intensity` 三列；`说明.docx` 中“input 9维”描述包含固定风机坐标，但实际 CSV 不包含坐标列。由于布局固定，现有功率预测可用，但正式偏航/变桨 RL 仍需新增每台风机控制参数列及生成配置。