"""Validation-only summary of the frozen small yaw/speed pilot, no model queries."""
from . import yaw_pilot as pilot
from . import forecast_speed_training as old
from .forecast_speed_report import aggregate, csv_out


def read_eval(ref, cases, arm):
    import numpy as np
    rows = old.read(old.verify(ref["metrics"]))
    with np.load(old.verify(ref["trace"]), allow_pickle=False) as data:
        assert tuple(data["fields"].tolist()) == pilot.TRACE
        traces = data["trace"]
    assert len(rows) == len(traces) == len(cases)
    for metric, trace, (case, wind) in zip(rows, traces, cases, strict=True):
        assert np.isfinite(trace).all()
        np.testing.assert_array_equal(trace[:, 4:7], wind)
        recomputed = old.metric(trace[:, :len(old.TRACE)], case)
        assert all(metric[k] == v for k, v in recomputed.items())
        cmd, parent = (trace[1:, lo:lo+9].reshape(128, 3, 3) for lo in (28, 37))
        sy, yz = trace[1:, 46:49], trace[1:, 49:52]
        for z in (sy, yz):
            assert np.max(np.abs(z)) <= 1
            np.testing.assert_array_equal(z, np.repeat(z[::8], 8, axis=0))
        np.testing.assert_array_equal(cmd[:, :, 1], parent[:, :, 1]) if arm in ("Y", "S") else None
        if arm in ("Y", "S"):
            np.testing.assert_array_equal(cmd[:, :, 2], np.clip(parent[:, :, 2]+2*(.1*sy)/.667, -1, 1).astype(np.float32))
        if arm == "Y":
            width = .5  # Frozen C environment yaw bounds are checked again below.
            expected = np.clip(parent[:, :, 0]+2*(pilot.math_radius("Y")*yz)/width, -1, 1).astype(np.float32)
            np.testing.assert_allclose(cmd[:, :, 0], expected, atol=5e-9, rtol=0)
        elif arm == "S":
            np.testing.assert_array_equal(cmd[:, :, 0], parent[:, :, 0])
    return rows, traces


def report():
    import io
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lock = pilot.context()
    complete = old.read(pilot.ROOT/"complete.json")
    selection = old.read(pilot.ROOT/"selection.json")
    assert complete["formal_rows"] == 37023 and complete["cumulative_rows"] == 40422
    assert lock["source"]["base_config"]["environment"]["action_high"][0]-lock["source"]["base_config"]["environment"]["action_low"][0] == .5
    s = pilot.store()
    val, stress = old.bank(lock, "validation"), old.bank(lock, "stress")
    groups, trajectories, records, progress, streams = {}, {}, [], [], []
    def register(name, ref, cases, arm):
        rows, trace = read_eval(ref, cases, arm)
        groups[name], trajectories[name] = rows, trace
        records.extend(dict(controller=name, **r) for r in rows)
        return rows
    for j in selection["jobs"]:
        arm, run = j["arm"], j["run"]
        for point in j["points"]:
            rows = register(f"{arm}{run}_s{point['step']}", point["eval"], val, arm)
            progress.append(dict(arm=arm, run=run, step=point["step"], mean_kW=point["mean_w"]/1000,
                new_updates=point["new_updates"], inherited_updates=point["origin"]["updates"],
                worst_kW=max(r["rmse_w"] for r in rows)/1000))
        for role in ("initial", "selected", "final"):
            point = j[role]
            groups[f"{arm}{run}_{role}"] = groups[f"{arm}{run}_s{point['step']}"]
            trajectories[f"{arm}{run}_{role}"] = trajectories[f"{arm}{run}_s{point['step']}"]
    for g in complete["groups"]:
        parts = g["label"].split("/")
        if parts[1].startswith(("Y", "S")):
            _, job, role, split = parts
            label, arm = f"{job}_{role}_{split}", job[0]
        else:
            _, job, split = parts
            label, arm = f"{job}_{split}", "S" if job.startswith("fixed") else "baseline"
        register(label, g["eval"], val if split in ("validation", "zero") else stress, arm)
    families = ("stationary", "ramp", "gust")
    family_rows, summary, comparisons = [], [], []
    def pool(name, role="selected", split="validation"):
        if name in ("Y", "S"):
            suffix = "_stress" if split == "stress" else ""
            return [r for run in range(3) for r in groups[f"{name}{run}_{role}{suffix}"]]
        if name == "fixed":
            return [r for run in range(3) for r in groups[f"fixed{run}_{split}"]]
        return groups[f"{name}_{split}"]
    for name, role in (("Y", "initial"), ("Y", "selected"), ("Y", "final"),
                       ("S", "initial"), ("S", "selected"), ("S", "final"),
                       ("fixed", "selected"), ("p", "selected"), ("pi", "selected")):
        rows = pool(name, role)
        label = f"{name}_{role}" if name in ("Y", "S") else name
        summary.append(dict(controller=label, **aggregate(rows)))
        for family in (*families, "all"):
            a = [r["rmse_w"] for r in rows if family == "all" or r["family"] == family]
            b = [r["rmse_w"] for r in pool("pi") if family == "all" or r["family"] == family]
            family_rows.append(dict(controller=label, family=family, case_stream_pairs=len(a),
                mean_kW=float(np.mean(a)/1000), PI_mean_kW=float(np.mean(b)/1000),
                difference_kW=float((np.mean(a)-np.mean(b))/1000), strict_below_PI=bool(np.mean(a)<np.mean(b))))
    for j in selection["jobs"]:
        arm, run = j["arm"], j["run"]
        def mean(name):
            return float(np.mean([r["rmse_w"] for r in groups[name]]))
        selected, final = mean(f"{arm}{run}_selected"), mean(f"{arm}{run}_final")
        fixed = mean(f"fixed{run}_validation")
        streams.append(dict(arm=arm, run=run, selected_step=j["selected"]["step"],
            selected_is_initial=j["selected"]["step"] == 0, selected_kW=selected/1000, final_kW=final/1000,
            fixed_kW=fixed/1000, final_minus_selected_kW=(final-selected)/1000,
            final_over_selected=final/selected, final_over_fixed=final/fixed,
            over_1p05_selected_diagnostic=final/selected>1.05, over_1p05_fixed_diagnostic=final/fixed>1.05))
        for role in ("selected", "final"):
            a = groups[f"{arm}{run}_{role}"]
            refs = dict(fixed=groups[f"fixed{run}_validation"])
            if arm == "Y":
                refs.update(S_same_budget=groups[f"S{run}_{role}"], yaw_disabled=groups[f"Y{run}_{role}_zero"])
            for ref, b in refs.items():
                for x, y in zip(a, b, strict=True):
                    assert x["case_id"] == y["case_id"]
                    comparisons.append(dict(arm=arm, run=run, role=role, reference=ref, family=x["family"],
                        case=x["case_id"], difference_kW=(x["rmse_w"]-y["rmse_w"])/1000))
    pressure_rows = []
    for name, role in (("Y", "selected"), ("Y", "final"), ("S", "selected"), ("S", "final"),
                       ("fixed", "selected"), ("p", "selected"), ("pi", "selected")):
        r = pool(name, role, "stress")
        pi_mean = np.mean([v["rmse_w"] for v in pool("pi", split="stress")])
        pressure_rows.append(dict(controller=f"{name}_{role}" if name in ("Y", "S") else name,
            mean_kW=float(np.mean([v["rmse_w"] for v in r])/1000),
            PI_difference_kW=float((np.mean([v["rmse_w"] for v in r])-pi_mean)/1000),
            worst_kW=max(v["rmse_w"] for v in r)/1000, cases=len(r),
            validation_plus_pressure_mean_kW=float(np.mean([v["rmse_w"] for v in pool(name, role)+r])/1000),
            validation_plus_pressure_pooled_kW=float(np.sqrt(np.mean([v["rmse_w"]**2 for v in pool(name, role)+r]))/1000)))
    for path, rows in (("metrics.csv", records), ("family_means.csv", family_rows), ("summary_metrics.csv", summary),
                       ("stream_summary.csv", streams), ("paired_differences.csv", comparisons),
                       ("pressure.csv", pressure_rows), ("validation_progress.csv", progress)):
        csv_out(s, path, rows)
    plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": .25, "pdf.fonttype": 42})
    fig, axs = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for axis, arm in zip(axs, pilot.ARMS, strict=True):
        for run in range(3):
            selected = [r for r in progress if r["arm"] == arm and r["run"] == run]
            axis.plot([r["step"] for r in selected], [r["mean_kW"] for r in selected], marker="o", label=f"stream {run}")
        axis.set_title(f"{arm} validation mean"); axis.set_xlabel("New physical steps"); axis.set_ylabel("RMSE (kW)")
        axis.legend()
    fig.suptitle("Frozen 2048-step software pilot | selection uses six old validation winds")
    export(s, fig, "validation_curves")
    fig, axs = plt.subplots(3, 1, figsize=(10, 8), constrained_layout=True)
    # Fixed before training in this executed source: stream 2, old gust case 4.
    for role, color in (("selected", "#2277aa"), ("final", "#cc7711")):
        trace = trajectories[f"Y2_{role}"][4]
        axs[0].plot(trace[:, 0], np.rad2deg(trace[:, 19]), label=role, color=color)
        axs[1].plot(trace[1:, 0], trace[1:, -3], label=role, color=color)
        axs[2].plot(trace[:, 0], trace[:, 3]/1000, label=role, color=color)
    for ax, ylabel in zip(axs, ("T01 actual yaw (deg)", "T01 yaw correction z", "Farm error (kW)"), strict=True):
        ax.set_ylabel(ylabel); ax.set_xlabel("Time (s)"); ax.legend()
    fig.suptitle("Y stream 2 selected/final | old gust 2.85 MW validation | current surrogate")
    export(s, fig, "yaw_actual_trajectories")
    main = [r for r in family_rows if r["controller"] == "Y_selected" and r["family"] != "all"]
    s.json("verification.json", dict(passed_saved_data_audit=True, rollout_metric_records=len(records),
        formal_steps=12288, formal_updates=582, model_rows=37023, engineering_rows=3399, cumulative_rows=40422,
        selected_Y=[j["selected"]["step"] for j in selection["jobs"] if j["arm"] == "Y"],
        selected_S=[j["selected"]["step"] for j in selection["jobs"] if j["arm"] == "S"],
        primary_validation_three_families_passed=all(r["strict_below_PI"] for r in main),
        primary_validation=main, ratios_are_diagnostics=True, independent_test=False, additional_queries=0))
    s.write("summary.txt", ("Frozen Y/S yaw-speed pilot complete. seed=42, 12288 new physical steps, 582 joint updates.\n"
        "37023 model rows plus 3399 engineering = 40422/42000. New independent tests=0.\n"
        "Primary screening uses per-family equal-stream/case validation RMSE below shared PI.\n"
        "See YAW_PILOT_RESULTS.md, family_means.csv, stream_summary.csv, pressure.csv and selection.json.\n").encode())
    print("Pilot validation report saved, 0 new model rows.", flush=True)


def export(s, fig, name):
    import io
    import matplotlib.pyplot as plt
    for extension in ("png", "pdf"):
        output = io.BytesIO(); fig.savefig(output, format=extension, dpi=180)
        s.write(f"figures/{name}.{extension}", output.getvalue())
    plt.close(fig)


if __name__ == "__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(old.ORIGIN/".venv/pinn_tf216")
    report()
