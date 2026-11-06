"""Deliver a complete frozen-transfer report from saved results, without queries."""
import csv
import io
import json
from pathlib import Path

from . import nrel_speed_transfer as run
from .forecast_speed_report import csv_out

REPORT = Path(__file__).with_name("NREL_SPEED_TRANSFER_RESULTS_20261106.md")


def read_csv(name):
    with (run.ROOT/name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def deliver():
    import numpy as np
    old, s, lock = run.old, run.store(), run.context()
    complete = old.read(run.ROOT/"complete.json")
    audit = old.read(run.ROOT/"saved_audit.json")
    admission = old.read(run.ROOT/"review_admission.json")
    assert complete["new_rows"] == 4030 and audit["passed"] and admission["performance_allowed"]
    assert old.sha(run.ROOT/"review_at_performance.md") == admission["review_sha256"]
    budget = old.read(run.ROOT/"model_budget.json")
    assert len(budget["scopes"]) == 38 and all(x["status"] == "complete" for x in budget["scopes"])
    assert sum(x["actual"] for x in budget["scopes"]) == 4030
    assert sum(x["kinds"].get("PINN", 0) for x in budget["scopes"]) == 3990
    assert sum(x["kinds"].get("mock", 0) for x in budget["scopes"]) == 40
    metrics, pairs, families, physical = [read_csv(n) for n in ("metrics.csv", "paired.csv", "family.csv", "physical.csv")]
    assert len(metrics) == 60 and len(pairs) == 30 and len(families) == 8 and len(physical) == 10
    # Preserve the engineering receipt's exact, pre-performance versions of mutable files.
    aliases = old.read(run.ROOT/"engineering_stage/aliases.json")
    with (run.ROOT/"engineering_stage/output_manifest.csv").open(encoding="utf-8", newline="") as stream:
        engineering_files = list(csv.DictReader(stream))
    for entry in engineering_files:
        p = run.ROOT/aliases.get(entry["relative_path"], entry["relative_path"])
        assert p.stat().st_size == int(entry["bytes"]) and old.sha(p) == entry["sha256"]
    ranges = []
    for item in complete["results"]:
        with np.load(old.verify(item["eval"]["trace"]), allow_pickle=False) as data:
            trace = data["trace"]
        values = trace[:, 1:]
        actual = values[:, :, 19:28].reshape(6, 128, 3, 3)[:, :, :, 2]
        commands, base = values[:, :, 58:61], values[:, :, 55:58]
        from .nrel_speed_adapter import LOW, HIGH
        model_input_speed = actual.astype(np.float32)
        assert model_input_speed.min() >= LOW-1e-7 and model_input_speed.max() <= HIGH+1e-7
        for index, (case, _) in enumerate(run.cases(lock)):
            ranges.append(dict(controller=item["controller"], case_id=case["id"], family=case["family"],
                base_TSR_min=float(values[index, :, 64:67].min()), base_TSR_max=float(values[index, :, 64:67].max()),
                actual_TSR_min=float(values[index, :, 61:64].min()), actual_TSR_max=float(values[index, :, 61:64].max()),
                command_TSR_min=float(values[index, :, 67:70].min()), command_TSR_max=float(values[index, :, 67:70].max()),
                base_floor_samples=int(np.sum(base[index] <= LOW+1e-7)), base_ceiling_samples=int(np.sum(base[index] >= HIGH-1e-7)),
                command_floor_samples=int(np.sum(commands[index] <= LOW+1e-7)), command_ceiling_samples=int(np.sum(commands[index] >= HIGH-1e-7)),
                actual_floor_samples=int(np.sum(actual[index] <= LOW+1e-7)), actual_ceiling_samples=int(np.sum(actual[index] >= HIGH-1e-7)),
                model_input_speed_min=float(model_input_speed[index].min()), model_input_speed_max=float(model_input_speed[index].max()),
                model_input_speed_domain_passed=True))
    csv_out(s, "new_case_physical_audit.csv", ranges)
    def f(value):
        return f"{float(value):.6f}"
    def row(rule, family):
        return next(x for x in families if x["rule"] == rule and x["family"] == family)
    summary = []
    for family in ("stationary", "ramp", "gust", "overall"):
        before, after = row("legacy", family), row("nrel", family)
        summary.append(dict(family=family, **{k+"_new_minus_old_kW":float(after[k+"_kW"])-float(before[k+"_kW"]) for k in ("Y", "P", "PI")}))
    csv_out(s, "family_paired_changes.csv", summary)
    # The report is completed after the observed results determine one follow-up recommendation.
    payload = dict(passed=True, new_performance_cases=30, old_saved_cases=30,
        new_performance_rows=3870, engineering_PINN_rows=120, engineering_mock_rows=40,
        cumulative_new_rows=4030, cumulative_PINN_rows=3990, row_hard_cap=10000,
        training_steps=0, optimizer_updates=0, new_wind_generation=0, report_queries=0,
        old_historical_rows=3870, old_reference_new_cost=0, engineering_receipt_files_verified=len(engineering_files),
        old_1720_archive_not_rechecked=True, source_guards_verified=len(lock["hashes"]),
        review_sha256=admission["review_sha256"], performance_code_commit="faeb02940c4819796a2914d7991249d3826525aa",
        base_TSR_min=min(r["base_TSR_min"] for r in ranges), base_TSR_max=max(r["base_TSR_max"] for r in ranges),
        actual_TSR_min=min(r["actual_TSR_min"] for r in ranges), actual_TSR_max=max(r["actual_TSR_max"] for r in ranges),
        boundary_samples={k:sum(r[k] for r in ranges) for k in ("base_floor_samples", "base_ceiling_samples", "command_floor_samples", "command_ceiling_samples", "actual_floor_samples", "actual_ceiling_samples")},
        family_changes=summary)
    s.json("performance_delivery_audit.json", payload)
    lines = ["# NREL参考转速：冻结策略迁移结果（2026-11-06）", "",
        "工程检查已通过。本报告只评估冻结旧策略在新基础曲线和正常运行低限下的迁移，使用旧validation，不是新独立测试或新增训练收益。", "",
        "## 全部风况族的旧／新对照", "", "RMSE单位kW；Y对三条流及每族两场等权，公共P／PI每场只执行一次。Δ为Y−PI，负值表示Y误差较小。", "",
        "| 版本 | 风况族 | Y | P | PI | Y−PI |", "|---|---|---:|---:|---:|---:|"]
    for item in families:
        lines.append("| "+" | ".join([item["rule"],item["family"],*[f(item[k]) for k in ("Y_kW","P_kW","PI_kW","Y_minus_PI_kW")]])+" |")
    lines += ["", "## 全部30个新回合的配对变化", "", "新−旧为负表示新设置误差下降。没有删除不利回合，也没有依据这些结果重选权重或调曲线。", "",
        "| 控制器 | 旧validation场景 | 旧RMSE kW | 新RMSE kW | 新−旧 kW |", "|---|---|---:|---:|---:|"]
    for item in pairs:
        lines.append("| "+" | ".join([item["controller"],item["case_id"],*[f(item[k]) for k in ("old_kW","new_kW","new_minus_old_kW")]])+" |")
    lines += ["", "## 实际控制与TSR", "", "| 版本 | 控制器 | 平均基础speed | 平均实际speed | 平均实际TSR | 命令触底% | 命令触顶% | 最大speed速率 |",
        "|---|---|---:|---:|---:|---:|---:|---:|"]
    for item in physical:
        lines.append("| "+" | ".join([item["rule"],item["controller"],f(item["base_mean"]),f(item["speed_mean"]),f(item["actual_TSR_mean"]),
            f(100*float(item["command_floor_fraction"])),f(100*float(item["command_ceiling_fraction"])),f(item["max_speed_rate"])] )+" |")
    lines += ["", "speed单位rad/s，速率单位rad/s²，原speed速率上限.1；逐回合上下限、TSR范围与边界样本数见`new_case_physical_audit.csv`。实际TSR使用实际speed及当次响应Ueff，基础／命令TSR使用下发时已观测到的Ueff。7.55仅是未限幅基础参考的设计值。", "",
        "## 版本、审查与费用", "", "Y selected仍为2048／0／2048新增步，C父为0／0／4096。Y第1流仍selected=initial。原父权重、forecast、桨距／偏航、P／PI增益、执行器时间常数／速率及PINN未变。网络、总命令与动作惩罚仍用旧[.6,1.267]坐标，新物理低限单独执行。", "",
        f"实现审查覆盖faeb029；实际审查SHA256 `{admission['review_sha256']}`，快照见`review_at_performance.md`，允许依据见`review_admission.json`。新增30回合×129=3870 PINN行，前期120 PINN＋40 mock，累计4030；训练／更新／新风／本报告模型查询均0。", "",
        "旧30个完整回合只引用核验后的原指标和轨迹，出处与SHA见`legacy_reuse.json`／`lock.json`。历史3870行另记，本轮引用费用0。全预算硬限10000行，存储128MiB。工程阶段24项清单通过版本映射复核，没有重复扫描旧1720项归档。", "",
        "原400／500kW门槛的逐族及总体通过计数见`family.csv`；其含义仍为每条流均值≤400且最差≤500，不能替代学习收益或独立泛化验收。当前曲线没有训练过程，不能把物理轨迹称作训练退化曲线。", "",
        "## 图与复现", "", "![基础参考曲线](./optimization_control/experiments/20261106_nrel_speed_transfer/reference_curves.png)", "",
        "![预定case4、stream2实际轨迹](./optimization_control/experiments/20261106_nrel_speed_transfer/fixed_case4_stream2.png)", "",
        "实验目录`optimization_control/experiments/20261106_nrel_speed_transfer/`。固定case4、stream2来自协议预定，不按结果选图。模型输入实际执行量、物理界限及速率已在每回合运行时检查，保存数据报告再次核对命令组合、因果Ueff、奖励坐标和全部指标。", "",
        "在隔离工作树使用原`.venv/Scripts/python.exe -B -X utf8`执行模块`nrel_speed_transfer performance`、`nrel_speed_transfer_report performance`、`nrel_speed_transfer_delivery`。这些阶段均已执行且采用独占创建，不重复执行或覆盖账本；只读复核使用`nrel_speed_transfer.context()`及保存的CSV／NPZ／JSON。准备／工程不重跑。", "",
        "现代理合成标签的speed特性依据入口风及旧曲线，新基础参考按各机有效风速计算。结果只说明当前代理内的软件迁移，不把RMSE变化当作NREL物理性能证据；本轮未修改模型或标签。", ""]
    s.write("performance_report_draft.md", "\n".join(lines).encode())
    print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(run.old.ORIGIN/".venv/pinn_tf216")
    deliver()
