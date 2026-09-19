import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator
from pathlib import Path

BASE = Path(__file__).parent

# 兼容本地和Streamlit Cloud的路径
_csv_path = BASE / "cases_multi.csv"
if not _csv_path.exists():
    _csv_path = Path("cases_multi.csv")

df = pd.read_csv(_csv_path)
df["power_total"] = df["power_1"] + df["power_2"]

wind_speeds = sorted(df["U_inf"].unique())
yaw_angles  = sorted(df["yaw_1"].unique())

P1_matrix   = np.zeros((len(wind_speeds), len(yaw_angles)))
P2_matrix   = np.zeros((len(wind_speeds), len(yaw_angles)))
Ptot_matrix = np.zeros((len(wind_speeds), len(yaw_angles)))

for i, U in enumerate(wind_speeds):
    for j, yaw in enumerate(yaw_angles):
        row = df[(df["U_inf"] == U) & (df["yaw_1"] == yaw)].iloc[0]
        P1_matrix[i, j]   = row["power_1"]
        P2_matrix[i, j]   = row["power_2"]
        Ptot_matrix[i, j] = row["power_total"]

interp_p1   = RegularGridInterpolator(
    (wind_speeds, yaw_angles), P1_matrix,   method="linear")
interp_p2   = RegularGridInterpolator(
    (wind_speeds, yaw_angles), P2_matrix,   method="linear")
interp_ptot = RegularGridInterpolator(
    (wind_speeds, yaw_angles), Ptot_matrix, method="linear")

U_min, U_max     = min(wind_speeds), max(wind_speeds)
yaw_min, yaw_max = min(yaw_angles),  max(yaw_angles)


def predict_power(yaw_angle, U_inf=8.0):
    """预测上游偏航yaw_angle°、下游0°时的功率"""
    U   = float(np.clip(U_inf,     U_min,   U_max))
    yaw = float(np.clip(yaw_angle, yaw_min, yaw_max))
    p1  = float(interp_p1([[U, yaw]]).item())
    p2  = float(interp_p2([[U, yaw]]).item())
    return p1, p2


def predict_power_2d(yaw1, yaw2, U_inf=8.0):
    U    = float(np.clip(U_inf, U_min, U_max))
    y1   = float(np.clip(yaw1, yaw_min, yaw_max))
    y2   = float(np.clip(yaw2, yaw_min, yaw_max))
    p1   = float(interp_p1([[U, y1]]).item())
    p2_0 = float(interp_p2([[U, y1]]).item())
    cos_factor = np.cos(np.radians(y2)) ** 1.5
    p2 = p2_0 * cos_factor

    # ===== 新增：截断到额定功率上限 =====
    p1 = min(p1, 5000.0)
    p2 = min(p2, 5000.0)

    return p1, p2


def find_optimal_yaw(U_inf=8.0, n_search=120):
    """单变量搜索最大总功率"""
    U = float(np.clip(U_inf, U_min, U_max))
    yaw_candidates = np.linspace(yaw_min, yaw_max, n_search)
    totals   = [float(interp_ptot([[U, y]]).item()) for y in yaw_candidates]
    best_idx = int(np.argmax(totals))
    best_yaw = yaw_candidates[best_idx]
    best_total = totals[best_idx]
    p1, p2   = predict_power(best_yaw, U)
    baseline = float(interp_ptot([[U, 0.0]]).item())
    gain_pct = (best_total - baseline) / baseline * 100
    return best_yaw, p1, p2, best_total, gain_pct


def find_yaw_for_target(target_power, U_inf=8.0,
                         p1_min=0, p1_max=5000,
                         p2_min=0, p2_max=5000,
                         n_search=60):
    """
    2D搜索：同时优化上下游偏航角，精确跟踪目标功率
    搜索空间：yaw1 × yaw2，共 n_search² 个候选点
    """
    U = float(np.clip(U_inf, U_min, U_max))
    yaw_candidates = np.linspace(yaw_min, yaw_max, n_search)

    best_yaw1   = 0.0
    best_yaw2   = 0.0
    best_power  = None
    best_err    = float("inf")

    for y1 in yaw_candidates:
        for y2 in yaw_candidates:
            p1, p2 = predict_power_2d(y1, y2, U)
            # 检查约束
            if not (p1_min <= p1 <= p1_max and p2_min <= p2 <= p2_max):
                continue
            total = p1 + p2
            err   = abs(total - target_power)
            if err < best_err:
                best_err   = err
                best_yaw1  = y1
                best_yaw2  = y2
                best_power = total

    if best_power is None:
        return 0.0, 0.0, 0.0, 100.0, False

    err_pct = abs(best_power - target_power) / max(target_power, 1) * 100
    return best_yaw1, best_yaw2, best_power, err_pct, True


if __name__ == "__main__":
    print("验证二维插值模型：")
    for U in [6, 8, 10, 12]:
        yaw, p1, p2, ptot, gain = find_optimal_yaw(U)
        print(f"  风速={U}m/s  最优偏航={yaw:+.1f}°  "
              f"P1={p1:.0f}kW  P2={p2:.0f}kW  "
              f"总={ptot:.0f}kW  增益={gain:+.1f}%")

    print("\n验证2D功率跟踪（目标2000kW，8m/s）：")
    y1, y2, p, e, ok = find_yaw_for_target(2000, 8.0)
    print(f"  yaw1={y1:+.1f}°  yaw2={y2:+.1f}°  "
          f"实际={p:.0f}kW  误差={e:.2f}%  可行={ok}")
    print("✅ 完成")