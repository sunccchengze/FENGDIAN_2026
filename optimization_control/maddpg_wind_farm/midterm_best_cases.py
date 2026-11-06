"""Plot explicitly selected demonstration cases from an already frozen test set."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from .midterm_figures import COLORS, LABELS, style


SOURCE = Path("optimization_control/experiments/20261022_random_wind_training")
DEFAULT_OUTPUT = Path("optimization_control/experiments/20261027_midterm_best_cases")
METHODS = ("initial", "p", "pi", "selected")
FAMILIES = {"gust": "阵风", "ramp": "慢变来流", "stationary": "平稳湍流"}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric_key(row):
    return row["stage"], row["run_id"], row["controller"], row["case_id"]


def find_trace(groups, choice, controller):
    run_id = choice["run_id"] if controller in ("initial", "selected") else "-1"
    return groups[(choice["stage"], run_id, controller, choice["case_id"])]


def array(rows, field, divisor=1):
    return np.array([float(row[field]) for row in rows]) / divisor


def plot_case(power_ax, error_ax, groups, choice, size=11):
    target = float(choice["target_w"]) / 1e6
    for method in METHODS:
        part = find_trace(groups, choice, method)
        rmse = np.sqrt(np.mean(array(part, "error_w") ** 2)) / 1000
        kwargs = {"color": COLORS[method], "lw": 2.3 if method == "selected" else 1.5,
                  "alpha": 1 if method == "selected" else .85,
                  "zorder": 5 if method == "selected" else 2}
        power_ax.plot(array(part, "step"), array(part, "farm_power_w", 1e6),
                      label=f"{LABELS[method]}  {rmse:.2f} kW", **kwargs)
        error_ax.plot(array(part, "step"), array(part, "error_w", 1000), **kwargs)
    power_ax.axhline(target, color="#243746", lw=1.5, ls="--", label=f"目标  {target:g} MW", zorder=6)
    error_ax.axhline(0, color="#243746", lw=1.3, ls="--", zorder=6)
    power_ax.set_ylabel("全场功率 / MW")
    error_ax.set_ylabel("功率跟踪误差 / kW")
    error_ax.set_title("正值：过发；负值：欠发", loc="left", fontsize=size - 1, pad=8)
    error_ax.set_xlabel("时间 / s")
    title = (f"{FAMILIES[choice['family']]} · 目标 {target:g} MW · 训练流 {choice['run_id']}"
             f" · 初始桨距 {float(choice['initial_pitch_rad']):g} rad")
    power_ax.set_title(title, fontsize=size + 1, pad=12)
    power_ax.legend(loc="upper right", fontsize=size, ncol=2, framealpha=.94)
    for ax in (power_ax, error_ax):
        ax.set_xlim(0, 128)
        ax.set_xticks(range(0, 129, 16))
        ax.grid(axis="y", alpha=.22)
        ax.tick_params(labelsize=size)


def save_figure(fig, output, stem, title, selection):
    fig.suptitle(title, x=.065, y=.974, ha="left", fontsize=21, fontweight="bold")
    fig.text(.065, .915, selection, fontsize=10.5, color="#526878")
    fig.text(.065, .027,
             "2026-10-22 合成标签代理模型实验；仅桨距学习。展示完整128 s，未平滑。单场结果不代表跨风况稳定优势。",
             fontsize=9.5, color="#526878")
    fig.subplots_adjust(left=.09, right=.97, top=.81, bottom=.13, hspace=.24, wspace=.28)
    for extension in ("png", "pdf", "svg"):
        fig.savefig(output / f"{stem}.{extension}", dpi=240, facecolor="white")
    plt.close(fig)


def run(output):
    if output.exists():
        raise FileExistsError(f"Output must be new: {output}")
    paths = [SOURCE / "test/metrics.csv", SOURCE / "test/trajectories.csv"]
    source_hashes = {str(path): digest(path) for path in paths}
    metrics = read_csv(paths[0])
    groups = defaultdict(list)
    for row in read_csv(paths[1]):
        groups[metric_key(row)].append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: int(row["step"]))
    maximum = 0.0
    for row in metrics:
        part = groups[metric_key(row)]
        assert [int(r["step"]) for r in part] == list(range(1, 129))
        errors = array(part, "farm_power_w") - float(row["target_w"])
        np.testing.assert_allclose(errors, array(part, "error_w"), atol=1e-8, rtol=0)
        measured = np.sqrt(np.mean(errors ** 2))
        maximum = max(maximum, abs(measured - float(row["rmse_w"])))
        assert abs(measured - float(row["rmse_w"])) < .001
    assert len(metrics) == 240 and sum(map(len, groups.values())) == 30720
    candidates = [r for r in metrics if r["controller"] == "selected" and r["family"] in FAMILIES]
    assert len(candidates) == 54
    order = lambda r: (float(r["rmse_w"]), int(r["run_id"]), r["case_id"])
    ranked = sorted(candidates, key=order)
    choices = [ranked[0], min((r for r in candidates if r["family"] == "ramp"), key=order)]
    lookup = {metric_key(row): row for row in metrics}
    ranking = []
    for rank, row in enumerate(ranked, 1):
        p = float(lookup[(row["stage"], "-1", "p", row["case_id"])]["rmse_w"])
        pi = float(lookup[(row["stage"], "-1", "pi", row["case_id"])]["rmse_w"])
        ranking.append({"rank": rank, "run_id": row["run_id"], "case_id": row["case_id"],
                        "family": row["family"], "maddpg_rmse_kw": float(row["rmse_w"]) / 1000,
                        "p_rmse_kw": p / 1000, "pi_rmse_kw": pi / 1000,
                        "maddpg_below_both": float(row["rmse_w"]) < min(p, pi)})
    comparisons = []
    waveform = []
    for choice in choices:
        ref = find_trace(groups, choice, "selected")
        for method in METHODS:
            part = find_trace(groups, choice, method)
            for field in ("wind_m_s", "direction_rad", "ti", "target_w", "initial_pitch_rad", "step"):
                np.testing.assert_array_equal(array(ref, field), array(part, field))
            comparisons.append({"case_id": choice["case_id"], "run_id": choice["run_id"],
                                "family": choice["family"], "controller": method,
                                "target_mw": float(choice["target_w"]) / 1e6,
                                "initial_pitch_rad": choice["initial_pitch_rad"], "steps": len(part),
                                "rmse_kw": float(np.sqrt(np.mean(array(part, "error_w") ** 2))) / 1000})
            power = array(part, "farm_power_w", 1000)
            error = array(part, "error_w", 1000)
            bias, fluctuation = float(error.mean()), float(power.std(ddof=0))
            np.testing.assert_allclose(np.mean(error ** 2), bias ** 2 + fluctuation ** 2, rtol=1e-12)
            difference = power - array(ref, "farm_power_w", 1000)
            waveform.append({"case_id": choice["case_id"], "controller": method,
                             "mean_power_kw": float(power.mean()), "bias_kw": bias,
                             "power_std_kw": fluctuation,
                             "rmse_kw": float(np.sqrt(np.mean(error ** 2))),
                             "corr_with_wind": float(np.corrcoef(power, array(part, "wind_m_s"))[0, 1]),
                             "corr_with_maddpg": float(np.corrcoef(power, array(ref, "farm_power_w"))[0, 1]),
                             "difference_vs_maddpg_min_kw": float(difference.min()),
                             "difference_vs_maddpg_max_kw": float(difference.max())})
    font = style()
    output.mkdir(parents=True)
    config = {"seed": 42, "new_training": False, "source_hashes": source_hashes,
              "selection": "Post-hoc minimum selected-policy full-episode RMSE: all 54 routine run/case pairs; separately 18 ramp pairs.",
              "choices": [{k: row[k] for k in ("run_id", "case_id", "family", "target_w", "initial_pitch_rad")} for row in choices],
              "font": font, "scope": "Frozen 20261022 synthetic-label proxy; no physical accuracy or stable superiority claim."}
    (output / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    write_csv(output / "metrics.csv", comparisons)
    write_csv(output / "waveform_diagnostics.csv", waveform)
    write_csv(output / "selection_ranking.csv", ranking)
    names = ("01_lowest_rmse_gust", "02_lowest_rmse_ramp")
    for choice, stem in zip(choices, names):
        fig, axes = plt.subplots(2, 1, figsize=(14, 7.875), sharex=True, gridspec_kw={"height_ratios": [1.45, 1]})
        plot_case(*axes, groups, choice, size=11)
        family = FAMILIES[choice["family"]]
        scope = "全部54条常规测试结果" if choice["family"] == "gust" else "18条慢变测试结果"
        save_figure(fig, output, stem, f"{family}示例：MADDPG的跟踪误差低于P与PI",
                    f"展示选择：事后从{scope}选取MADDPG最低RMSE案例；图例为本场完整回合RMSE。")
    fig, axes = plt.subplots(2, 2, figsize=(16, 9), sharex="col")
    for col, choice in enumerate(choices):
        plot_case(axes[0, col], axes[1, col], groups, choice, size=10)
    save_figure(fig, output, "03_two_favorable_cases", "已有测试中的两个表现较好案例",
                "事后展示选择：左为全部54条常规测试中MADDPG最低RMSE，右为慢变类最低；不能替代原总体对照图。")
    assert all(digest(Path(path)) == expected for path, expected in source_hashes.items())
    validation = {"metrics_recomputed": len(metrics), "trace_rows": sum(map(len, groups.values())),
                  "max_rmse_difference_w": maximum, "ranked_candidates": len(ranked),
                  "selected_trace_steps": 128, "same_inputs_across_controllers": True,
                  "source_hashes_unchanged": True, "new_training": False,
                  "maddpg_below_both_pairs": sum(row["maddpg_below_both"] for row in ranking),
                  "pair_count_not_independent_samples": True}
    (output / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = ["# 答辩补充时序图", "", "来源：20261022冻结随机入口测试。仅从保存CSV绘图，没有新训练、调参或策略选择。",
              "原图06固定展示训练流0、3.3 MW及初始桨距0.025 rad；本补图明确按表现事后挑选。",
              "候选为3条训练流×18场常规测试，共54条，不含低风压力场；不是54条独立风轨迹。",
              "选出的策略检查点仍是原验证集选中的策略，没有根据测试改选检查点。", "",
              "|场景|训练流|目标MW|初始桨距rad|方法|完整128秒RMSE/kW|", "|---|---:|---:|---:|---|---:|"]
    for row in comparisons:
        report.append(f"|{FAMILIES[row['family']]}|{row['run_id']}|{row['target_mw']:g}|{row['initial_pitch_rad']}|{LABELS[row['controller']]}|{row['rmse_kw']:.2f}|")
    report += ["", "## 图的用途与讲稿", "", "01为常规候选中MADDPG最低误差场景；02为慢变类最低误差场景；03并排展示二者。均有PNG/PDF/SVG。",
               "建议讲述：在这些展示案例中，训练后MADDPG的完整回合跟踪误差低于P和PI，说明已学到有效行为；",
               "但案例按表现事后选取，不能据此声称跨风况稳定领先。总体结论仍以原图04的三流18场汇总为准。",
               "所有曲线展示128个原始时间点，不平滑、不截取片段。灰线为初始策略，蓝线为训练后策略，橙/绿为相同条件下P/PI。",
               "慢变类平均表现仍弱于PI，与本补图单个慢变案例更优并不矛盾。", "",
               "## 为什么曲线起伏相似", "",
               "各方法使用同一风轨迹，偏航和转速采用相同调度，主要通过桨距调节功率；同一准静态代理模型会产生共同的风况响应。",
               "曲线并非严格平移，功率差随时间变化；相关性与差值范围见waveform_diagnostics.csv。",
               "固定目标下RMSE²=平均误差²+功率波动标准差²（总体标准差，ddof=0）。本例改善包含平均偏差减小，不能全部解释为波动抑制。",
               "例如阵风案例MADDPG/P/PI的平均误差约-84.62/+300.87/+146.54 kW，功率波动标准差约240.51/251.08/266.10 kW。",
               "当前模型为合成标签拟合的准静态网络，没有显式动态尾流传播或结构响应；相似曲线不能证明模型错误，也不能证明真实动态调节能力。", "",
               "模型为合成标签代理网络；结果不是实测/CFD精度或真实发电收益证明。",
               "完整候选排名见selection_ranking.csv，可用于核查选择过程。原始图、CSV和源ZIP均未修改。"]
    (output / "图表说明.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (output / "summary.txt").write_text(
        "Post-hoc demonstration cases from frozen 20261022 tests.\n"
        "54 routine run/case pairs ranked; global and ramp minima plotted over full 128 seconds.\n"
        "Three PNG/PDF/SVG figures; no new training or source changes.\n"
        "Case superiority does not establish stable aggregate superiority.\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "choices": config["choices"], "validation": validation}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.output)
