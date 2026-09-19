# 成员工作清单（team inventory）

> ⚠️ 本文件是**项目背景与集成参考**（全组视角），**不是孙承泽需交付的内容**。孙承泽本人只看 `孙承泽个人待办.md` 与自己 `site/`。
> 目的：把"谁做了什么"列清楚，便于阶段交付时各取所需。标注（推测）的条目为推断，请组会确认。
> 已结合 `20260808/` 更新（厉 NN 理由、洪 代理模型优化交付）。

## 一、按成员划分

### 袁夫达（建模组）
| 产出 | 文件 | 状态 | 下一步 |
| --- | --- | --- | --- |
| FLORIS GCH/CC 数据 | `floris(1).zip` → `training_data_*.csv` | ✅ 1224/套 | 归档原始生成脚本；**补偏航维度数据**（洪建议） |
| 3×3 阵列 / 风玫瑰 | `generate_array_data.py`、`cases_array.csv`、`cases_windrose*.csv` | ✅ | 写入交付包 |

### 厉今飞（AI 组，主持人）
| 产出 | 文件 | 状态 | 下一步 |
| --- | --- | --- | --- |
| 原始 keras NN（基线） | `floris(1).zip` → `wind_farm_results/*.keras` | ✅ 已被洪复现验证 | 若追精度用洪的 XGB；继续深度路线参考 mlp_v2 |
| **NN 选型理由（正式答复）** | `20260808/README.md` | ✅ 已记录 | 并入研究综述 |
| 大创申请书 | `20260329-大创申请书-终版.docx` | ✅ 终版 | 目标基准 |

### 田铭雨（仿真组）
| 产出 | 文件 | 状态 | 下一步 |
| --- | --- | --- | --- |
| 流场快照 | `fields/*.npz`、`fields_3d/`、`fields_array/` | ✅（FLORIS） | 接 Fluent 高保真 |
| POD 分解 | `pod_analysis.py`、`pod_results/` | 🟡 | 明确用途：降维代理 or PINN 模态基（Q13） |

### 洪祖名（优化控制组）
| 产出 | 文件 | 状态 | 下一步 |
| --- | --- | --- | --- |
| **代理模型 ML 优化交付** | `20260808/代理模型优化交付_20260808.zip` → `final_models/`(XGBoost json)、`evaluation/`、`scripts/` | ✅ **选定 XGBoost**（farm MAE 7.8/10.5kW，R²>0.99996） | 接入可视化；立项 PINN 衔接 |
| 双机/9 机偏航优化 | `optimizer_result.json`、`array_independent_result.json` | ✅ +8.1% / +24.0% | 扩展大风场（Q15） |
| 两阶段零功率模型 | 同上 zip（two_stage） | ✅ farm MAE ~13kW、零类 99.9% | 是否定为含零正式方案（Q23） |

### 孙承泽（可视化组，本分支维护人）
| 产出 | 文件 | 状态 | 下一步 |
| --- | --- | --- | --- |
| Streamlit 演示 | `app.py`、`pages/dashboard.py` | ✅ | 统一用洪的 XGBoost 接口（Q1） |
| 双机插值后端 | `surrogate_model.py` | ✅（过渡） | 评估替换 NN/XGB（Q1） |
| 文档中心 | `docs/*` | 维护中 | 持续更新 |

## 二、按资产类型划分

| 资产 | 关键文件 | 主责 |
| --- | --- | --- |
| 原始样本（CC/GCH 1224） | `floris(1).zip` | 袁夫达 |
| **最终代理模型（XGBoost）** | `20260808/代理模型优化交付_20260808.zip` → `final_models/` | 洪祖名 |
| 原始 NN 基线（keras） | `floris(1).zip` → `wind_farm_results/` | 厉今飞 |
| 双机/阵列/风玫瑰 | `cases*.csv` | 袁夫达 |
| 流场快照 | `fields/`、`fields_3d/`、`fields_array/` | 田铭雨 |
| 优化结果 | `optimizer_result.json`、`array_independent_result.json` | 洪祖名 |
| 演示与文档 | `app.py`、`pages/`、`docs/` | 孙承泽 |

## 三、协作链路与卡点

```
袁夫达(FLORIS数据) ─┐
厉今飞(原始NN)     ─┼─► 洪祖名(选XGBoost代理+偏航优化) ─► 孙承泽(可视化) ─► 全组
田铭雨(流场/POD)   ─┘
```

**卡点**：
1. 可视化仍吃 `cases_multi.csv` 双机插值，未接洪的 XGBoost（Q1）。
2. **数据无偏航维度**，偏航控制（PPO）无法训练——最大短板（Q22）。
3. 优化结果 JSON 写死，演示里未做成可调（Q14）。
