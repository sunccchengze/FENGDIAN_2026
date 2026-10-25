# -*- coding: utf-8 -*-
"""诊断「坐标尺度」：从冻结主干里读出它自己的归一化尺度，算出各口径落在哪。

冻结主干的第一层是 Rescaling(scale=100/x_lim, offset=0)，
把米制坐标压到 0~100。本脚本反解 x_lim / y_lim / z_lim，
再算三种坐标口径下三台机在主干眼里的归一化位置，与它训练时的布局比较。

需要 TF：

    pinn_wind_data\\.venv-tf\\Scripts\\python.exe pinn_wind_data\\coord_diagnosis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
PINN = PROJECT / "PINNs_multi_turbine_wake_simulation-outputchange"
OUT = HERE / "out"

sys.path.insert(0, str(PINN))
import modify_pinn_wind_io as io  # noqa: E402


def feature_diagnosis(model, lims) -> dict:
    """直接看冻结主干在每种坐标口径下吐出的 6x500 特征，验证"失效机制"。

    关注两件事：
      1) 特征量级是否落在训练分布内（用原 4 机布局当参照）；
      2) 三台机之间的特征是否还分得开（余弦相似度、相对差异）。
    """
    R_SRC = 15.05
    ref = np.array([[0.0, -7 * R_SRC, 35.0], [14 * R_SRC, 7 * R_SRC, 35.0]])
    # 参照：原训练布局里的两台机，作为"分布内"的标尺
    ref_feat = np.concatenate(
        [np.asarray(f) for f in model([ref[:, 0:1], ref[:, 1:2], ref[:, 2:3]])],
        axis=-1)  # (2, 3000)

    out = {}
    for cfg_name in ("wind_project_config_scaled_half.json", "wind_project_config.json",
                     "wind_project_config_spacing7D.json", "wind_project_config_physical.json"):
        cfg = json.loads((OUT / cfg_name).read_text(encoding="utf-8"))
        pos = np.array(cfg["turbine_positions_m"], dtype=float)
        feats = np.concatenate(
            [np.asarray(f) for f in model([pos[:, 0:1], pos[:, 1:2], pos[:, 2:3]])],
            axis=-1)  # (3, 3000)
        norms = np.linalg.norm(feats, axis=1)
        unit = feats / norms[:, None]
        cos = unit @ unit.T
        # 与"分布内参照"的余弦相似度（每台机 vs 参照第 1 台）
        cos_ref = unit @ (ref_feat[0] / np.linalg.norm(ref_feat[0]))
        out[cfg.get("coordinate_mode", cfg_name)] = {
            "scale": cfg.get("coordinate_scale", 1.0),
            "feature_norm": norms.tolist(),
            "norm_vs_reference": (norms / np.linalg.norm(ref_feat[0])).tolist(),
            "cos_T1_T2": float(cos[0, 1]),
            "cos_T2_T3": float(cos[1, 2]),
            "cos_T1_T3": float(cos[0, 2]),
            "cos_with_in_distribution_ref": cos_ref.tolist(),
        }
    return out


def main() -> int:
    tf, keras, *_ = io.tensorflow_components()
    frozen = PINN / "OutputChange" / "prepared_9ms" / "original_frozen_features.keras"
    model = keras.models.load_model(str(frozen), compile=False)

    # 找 Rescaling 层，反解原域边界
    resc = [l for l in model.layers if isinstance(l, keras.layers.Rescaling)]
    if len(resc) != 3:
        raise SystemExit(f"预期 3 个 Rescaling 层，实际 {len(resc)}")
    # Rescaling 的 scale 可能是标量也可能是长度 1 的 ListWrapper，统一取第一个元素
    def to_scalar(v):
        arr = np.asarray(v, dtype=float).reshape(-1)
        return float(arr[0])

    lims = [100.0 / to_scalar(l.scale) for l in resc]
    names = ["x_lim", "y_lim", "z_lim"]

    # 原论文 Rectangular_grid_config.py：x∈[-10R,42R], y∈±17R, z∈[0.02R,15R]，R=15.05
    R_SRC = 15.05
    expected = [42 * R_SRC, 17 * R_SRC, 15 * R_SRC]

    print("冻结主干的归一化尺度（由 Rescaling 层反解）:")
    for n, v, e in zip(names, lims, expected):
        print(f"  {n:6s} = {v:9.2f} m   理论值 {e:9.2f} m   偏差 {100*(v-e)/e:+.2f}%")

    def norm(pos):
        return np.array(pos, dtype=float) * 100.0 / np.array(lims)

    # 原 4 机布局在归一化坐标里的样子（供比较）
    src_layout = np.array([[0.0, -7 * R_SRC, 35.0], [0.0, 7 * R_SRC, 35.0],
                           [14 * R_SRC, -7 * R_SRC, 35.0], [14 * R_SRC, 7 * R_SRC, 35.0]])
    print("\n主干训练时的 4 机布局（归一化坐标）:")
    for p, q in zip(src_layout, norm(src_layout)):
        print(f"  ({p[0]:8.2f},{p[1]:8.2f},{p[2]:6.2f}) m -> ({q[0]:6.2f},{q[1]:6.2f},{q[2]:6.2f})")
    src_span_x = norm(src_layout)[2, 0] - norm(src_layout)[0, 0]
    print(f"  源布局顺流向间距 = {src_span_x:.2f}（归一化单位）")

    rows = []
    for cfg_name in ("wind_project_config.json", "wind_project_config_spacing7D.json",
                     "wind_project_config_physical.json"):
        cfg = json.loads((OUT / cfg_name).read_text(encoding="utf-8"))
        pos = np.array(cfg["turbine_positions_m"], dtype=float)
        npos = norm(pos)
        span = npos[-1, 0] - npos[0, 0]
        inside = bool((npos >= 0).all() and (npos <= 100).all())
        rows.append({
            "口径": cfg.get("coordinate_mode", cfg_name),
            "缩放": cfg.get("coordinate_scale", 1.0),
            "机位(m)": " / ".join(f"{p[0]:.0f}" for p in pos),
            "轮毂(m)": f"{pos[0, 2]:.1f}",
            "归一化 x": " / ".join(f"{q[0]:.1f}" for q in npos),
            "归一化 z": f"{npos[0, 2]:.1f}",
            "顺流向跨度": f"{span:.1f}",
            "全在 0~100 内": "是" if inside else "否",
            "跨度/源跨度": f"{span / src_span_x:.2f}",
        })

    print("\n三种坐标口径在主干眼里的位置:")
    header = ["口径", "缩放", "机位(m)", "轮毂(m)", "归一化 x", "归一化 z", "顺流向跨度",
              "全在 0~100 内", "跨度/源跨度"]
    widths = {h: max(len(str(r[h])) for r in rows + [{h: h}]) for h in header}
    print("  " + "  ".join(h.ljust(widths[h]) for h in header))
    for r in rows:
        print("  " + "  ".join(str(r[h]).ljust(widths[h]) for h in header))

    # ---------------- 特征层面的机制验证
    feats = feature_diagnosis(model, lims)
    print("\n冻结主干吐出的 6x500 特征（验证失效机制）:")
    print(f"  {'口径':14s} {'缩放':>7s} {'特征范数/参照':>16s} {'cos(T1,T2)':>11s} "
          f"{'cos(T2,T3)':>11s} {'与分布内参照的余弦':>18s}")
    for name, v in feats.items():
        nv = "/".join(f"{x:.2f}" for x in v["norm_vs_reference"])
        cr = "/".join(f"{x:.3f}" for x in v["cos_with_in_distribution_ref"])
        print(f"  {name:14s} {v['scale']:7.3f} {nv:>16s} {v['cos_T1_T2']:11.4f} "
              f"{v['cos_T2_T3']:11.4f} {cr:>18s}")

    (OUT / "coord_diagnosis.json").write_text(
        json.dumps({"normalization_limits_m": dict(zip(names, lims)),
                    "theoretical": dict(zip(names, expected)),
                    "source_layout_normalized": norm(src_layout).tolist(),
                    "variants": rows,
                    "frozen_feature_diagnosis": feats}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"\n[OK] 写出 {OUT / 'coord_diagnosis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
