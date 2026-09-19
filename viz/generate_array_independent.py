"""重建 3×3 阵列四策略数据契约。

输出 ``array_independent_result.json``，包含基准、第一排统一偏航、前两排接力偏航
和逐排贪心四组总功率及逐机功率。脚本与 ``site/array.html``、
``site/assets/js/farm.js`` 共用同一份 JSON，禁止在前端另写近似功率。
"""
import json
from pathlib import Path

import floris
import numpy as np
import pandas as pd
from floris import FlorisModel

ROOT = Path(__file__).parent
D = 126.0
LAYOUT_X = [row * 5 * D for row in range(3) for _col in range(3)]
LAYOUT_Y = [(col - 1) * 3 * D for _row in range(3) for col in range(3)]
YAW_CANDIDATES = np.arange(-30, 31, 5, dtype=float)

model = FlorisModel(str(Path(floris.__file__).parent / "default_inputs.yaml"))
model.set(
    layout_x=LAYOUT_X,
    layout_y=LAYOUT_Y,
    wind_directions=[270.0],
    wind_speeds=[8.0],
    turbulence_intensities=[0.06],
)


def evaluate(yaws):
    """运行一组九机偏航角，返回 (总功率kW, 九机功率kW)。"""
    model.set(yaw_angles=np.asarray([yaws], dtype=float))
    model.run()
    powers = model.get_turbine_powers()[0] / 1000.0
    return float(powers.sum()), powers


def greedy_by_row():
    """从上游到下游逐排固定，每排在 13 个离散角中搜索。"""
    best_yaws = np.zeros(9, dtype=float)
    for row in range(3):
        best_total = -np.inf
        best_yaw = 0.0
        for candidate in YAW_CANDIDATES:
            trial = best_yaws.copy()
            trial[row * 3:(row + 1) * 3] = candidate
            total, _powers = evaluate(trial)
            if total > best_total:
                best_total = total
                best_yaw = float(candidate)
        best_yaws[row * 3:(row + 1) * 3] = best_yaw
        print(f"第 {row + 1} 排固定为 {best_yaw:+.0f}°，当前总功率 {best_total:.2f} kW")
    return best_yaws


def rounded(values):
    return [round(float(v), 2) for v in values]


def main():
    print("=" * 52)
    print("3×3 阵列四策略同源重建")
    print("=" * 52)

    greedy_yaws = greedy_by_row()

    sweep = pd.read_csv(ROOT / "cases_array.csv")
    best_unified = sweep.loc[sweep["power_total"].idxmax()]
    unified_yaw = float(best_unified["yaw_upstream"])

    yaws_none = np.zeros(9)
    yaws_unified = np.array([unified_yaw] * 3 + [0.0] * 6)
    yaws_row2_30 = np.array([unified_yaw] * 6 + [0.0] * 3)

    p_none, powers_none = evaluate(yaws_none)
    p_unified, powers_unified = evaluate(yaws_unified)
    p_row2_30, powers_row2_30 = evaluate(yaws_row2_30)
    p_independent, powers_independent = evaluate(greedy_yaws)

    def gain(power):
        return (power - p_none) / p_none * 100.0

    result = {
        "greedy_yaws": [float(v) for v in greedy_yaws],
        "greedy_row_yaws": [float(greedy_yaws[i * 3]) for i in range(3)],
        "row2_30_yaws": [unified_yaw, unified_yaw, 0.0],
        "power_none": round(p_none, 2),
        "power_unified": round(p_unified, 2),
        "power_row2_30": round(p_row2_30, 2),
        "power_independent": round(p_independent, 2),
        "unified_yaw": unified_yaw,
        "gain_unified_pct": round(gain(p_unified), 2),
        "gain_row2_30_pct": round(gain(p_row2_30), 2),
        "gain_independent_pct": round(gain(p_independent), 2),
        "turbine_powers_none": rounded(powers_none),
        "turbine_powers_independent": rounded(powers_independent),
        "turbine_powers_unified": rounded(powers_unified),
        "turbine_powers_row2_30": rounded(powers_row2_30),
    }

    # 审计锚点：配置、布局或 FLORIS 版本漂移时立即失败。
    assert abs(result["power_none"] - 8095.15) < 1.0
    assert abs(result["power_unified"] - 9299.05) < 1.0
    assert abs(result["power_row2_30"] - 9934.99) < 1.0
    assert abs(result["power_independent"] - 10041.46) < 1.0
    assert result["greedy_row_yaws"] == [30.0, 20.0, 0.0]

    output = ROOT / "array_independent_result.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n四策略结果：")
    for name, power in [
        ("全部 0°", p_none),
        ("第一排 +30°", p_unified),
        ("前两排 +30°", p_row2_30),
        ("逐排贪心 [30,20,0]°", p_independent),
    ]:
        print(f"  {name:<24} {power:9.2f} kW  {gain(power):+6.2f}%")
    print(f"\n已写入 {output}")


if __name__ == "__main__":
    main()
