# 风电场偏航优化可视化模块

西安交通大学 · 能源与动力工程学院 · 大创项目  
负责人：孙承泽 · 可视化模块

---

## 在线演示

https://sunccchengze-wind-farm-viz-app-xxxxxx.streamlit.app

---

## 页面功能

| 页面 | 功能 | 标签 |
|---|---|---|
| 🏠 主页 | 项目入口与模块导航 | - |
| 📊 尾流分析 | 交互式尾流云图 + 代理模型实时功率曲线 | CORE |
| 🎯 优化结果 | 偏航前后对比图 + 速度差值图 + 动画 | CORE |
| 📋 数据总览 | 各工况功率柱状图 + 统计表格 | ANALYSIS |
| 🌐 3D尾流曲面 | 三维速度曲面，鼠标拖拽旋转 | 3D |
| 🫧 3D体渲染 | 真实三维尾流低速泡 + 风机转子几何 | 3D |
| 🔥 热力矩阵 | 偏航角 × 风速功率增益矩阵 | ANALYSIS |
| ⚡ 优化求解器 | 任意风速输入，实时输出最优偏航角 | AI · OPT |
| 🔬 POD降阶分析 | 本征正交分解，模态能量，重构误差 | POD · ROM |
| ⚡ 3×3阵列优化 | 九台风机协同偏航，全场功率热力图 | ARRAY |
| 🎛️ 功率需求跟踪 | 输入目标功率，自动搜索最优偏航角 | CONTROL |

---

## 文件结构

```
Python001/
├── app.py                      # 主页入口
├── surrogate_model.py          # 二维插值代理模型（开学后替换为神经网络）
├── pod_analysis.py             # POD分解脚本（生成pod_results/）
├── generate_data.py            # 单风速数据生成（cases.csv + fields/）
├── generate_multiwind_data.py  # 多风速数据生成（cases_multi.csv）
├── generate_3d_data.py         # 三维流场数据生成（fields_3d/）
├── generate_array_data.py      # 3×3阵列数据生成（cases_array.csv）
├── export_gif.py               # 动画导出脚本
├── cases.csv                   # 单风速工况数据（8 m/s，13个偏航角）
├── cases_multi.csv             # 多风速工况数据（6/8/10/12 m/s × 13）
├── cases_array.csv             # 3×3阵列工况数据（13个偏航角）
├── optimizer_result.json       # 优化器推荐结果
├── wake_animation.gif          # 偏航角扫描动画
├── requirements.txt            # 依赖库列表
├── fields/                     # 单风速流场文件（128×64）
├── fields_3d/                  # 三维流场文件（9层高度）
├── pod_results/                # POD分解结果
└── pages/
    ├── 1_wake.py
    ├── 2_optimization.py
    ├── 3_overview.py
    ├── 4_3d_surface.py
    ├── 5_3d_volume.py
    ├── 6_heatmap.py
    ├── 7_solver.py
    ├── 8_pod.py
    ├── 9_array.py
    └── 10_power_tracking.py
```

---

## 数据接口规范

### 仿真组提供：`cases.csv`

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| case_id | str | - | 工况编号，格式 case_0001 |
| U_inf | float | m/s | 来流风速 |
| yaw_1 | float | ° | 上游风机偏航角 |
| yaw_2 | float | ° | 下游风机偏航角 |
| power_1 | float | kW | 上游风机功率 |
| power_2 | float | kW | 下游风机功率 |

### 仿真组提供：`fields/case_XXXX.npz`

| 变量 | 形状 | 单位 | 说明 |
|---|---|---|---|
| x | (128,) | m | 顺风方向坐标 |
| y | (64,) | m | 横向坐标 |
| u | (64, 128) | m/s | 轮毂高度水平截面风速 |

> ⚠️ 速度场请存绝对风速（m/s），不要归一化  
> ⚠️ 网格尺寸固定为 128×64，如需更改请提前告知

### 仿真组提供：`fields_3d/yaw_±XX.npz`

| 变量 | 形状 | 单位 | 说明 |
|---|---|---|---|
| x | (64,) | m | 顺风方向坐标 |
| y | (32,) | m | 横向坐标 |
| z | (9,) | m | 高度坐标（20~180m） |
| u | (9, 32, 64) | m/s | 三维速度场 |

### 控制组提供：`optimizer_result.json`

```json
{
  "wind_speed": 8.0,
  "original_yaw": 0,
  "recommended_yaw": 25,
  "power_before": 2190.4,
  "power_after": 2368.4,
  "power_gain_pct": 8.13
}
```

### 控制组提供：功率需求跟踪函数接口

```python
def find_yaw_for_target(target_power, U_inf):
    """
    输入：
        target_power : float，电网目标功率需求 (kW)
        U_inf        : float，当前来流风速 (m/s)
    输出：
        best_yaw     : float，推荐偏航角 (°)
        actual_power : float，对应实际总功率 (kW)
        error_pct    : float，跟踪误差百分比 (%)
    """
    ...
    return best_yaw, actual_power, error_pct
```

将此函数放入 `surrogate_model.py` 覆盖同名函数，`10_power_tracking.py` 无需修改。

### AI组提供：神经网络代理模型接口

```python
def predict_power(yaw_angle, U_inf):
    """
    输入：偏航角（度），风速（m/s）
    输出：(p1, p2)，单位 kW
    """
    ...
    return p1, p2
```

将此函数放入 `surrogate_model.py` 覆盖同名函数，所有页面自动使用新模型。

---

## 本地运行方法

```bash
pip install -r requirements.txt
cd Python001
streamlit run app.py
```

## 重新生成所有数据

```bash
python generate_data.py            # 单风速数据
python generate_multiwind_data.py  # 多风速数据
python generate_3d_data.py         # 三维流场数据
python generate_array_data.py      # 3×3阵列数据
python pod_analysis.py             # POD分解
python export_gif.py               # 动画
```

---

## 替换真实数据方法

1. 将仿真组的 `cases.csv` 覆盖本地文件
2. 将流场文件放入 `fields/`，命名格式保持 `case_XXXX.npz`
3. 将控制组的 `optimizer_result.json` 覆盖本地文件
4. 重新运行 `streamlit run app.py`

**无需修改任何代码。**

---

## 当前数据说明（FLORIS模拟数据）

| 参数 | 数值 |
|---|---|
| 风机型号 | NREL 5MW 基准风机 |
| 额定功率 | 5000 kW |
| 轮毂高度 | 90 m |
| 转子直径 | 126 m |
| 尾流模型 | GCH（Gauss-Curl Hybrid） |
| 单风速工况 | 8 m/s，13个偏航角（-30°~+30°，步长5°） |
| 多风速工况 | 6/8/10/12 m/s × 13个偏航角，共52条 |
| 三维工况 | 5个偏航角 × 9个高度层（20~180m） |
| 阵列工况 | 3×3布局，13个上游偏航角 |
| 两台最优偏航角 | +25°，功率提升 8.1% |
| 阵列最优偏航角 | +30°，功率提升 14.9% |
```

