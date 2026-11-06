"""Audit frozen independent test and compute waveform-paired descriptive statistics."""
import io

from . import forecast_speed_training as old
from . import yaw_pilot as pilot
from . import yaw_independent_test as test
from .forecast_speed_report import aggregate, csv_out
from .forecast_speed_user_test_report import bootstrap


def group(name):
    if name in ("p", "pi"):
        return [name]
    if name == "fixed":
        return [f"fixed{r}" for r in range(3)]
    arm, role = name.split("_")
    zero = role.endswith("zero")
    role = role.removesuffix("zero")
    return [f"{arm}{r}_{role}"+("_zero" if zero else "") for r in range(3)]


def audit():
    import numpy as np
    from .yaw_pilot_saved_report import frozen
    lock, cases = test.evaluation_context()
    complete, s = old.read(test.ROOT/"complete.json"), test.shared()
    assert complete["rows"] == 53406 and complete["rollouts"] == 414
    metrics, traces, counts = {}, {}, []
    rows = 0
    for ref, role in zip(complete["results"], lock["roles"], strict=True):
        entry = old.read(old.verify(ref))
        assert entry["role"] == role and entry["optimizer_updates_during_test"] == 0
        assert entry["counters_before"] == entry["counters_after"]
        values, arrays = [], []
        arm = role.get("arm", "S") if role["kind"] != "baseline" else "baseline"
        for receipt, case in zip(entry["cases"], cases, strict=True):
            result = old.read(old.verify(receipt))
            assert result["rows"] == 129 and result["partition_accounting"]["actual"] == 129
            reservation = old.read(old.verify(result["reservation"]))
            assert reservation["role"] == role and reservation["case"] == case[0]
            assert reservation["release_sha"] == old.sha(test.ROOT/"release.json")
            part, trace = frozen.read_eval(result["eval"], [case], arm)
            assert trace.shape == (1, 129, len(pilot.TRACE))
            values.extend(part); arrays.append(trace[0]); rows += 129
        metrics[role["id"]], traces[role["id"]] = values, np.stack(arrays)
        counts.append(dict(controller=role["id"], rollouts=18, input_rows=2322,
            bytes=old.Store(test.ROOT/"jobs"/role["id"], 4*test.MIB).used(),
            optimizer_updates=0, parameter_digest=entry["parameter_digest"]))
    assert rows == 53406 and len(list(test.ROOT.rglob("reserved.json"))) == 414
    exact = []
    for run in range(3):
        for role in ("selected", "final"):
            key = f"Y{run}_{role}_zero"
            np.testing.assert_array_equal(traces[key], traces[f"fixed{run}"])
            exact.append(key)
    np.testing.assert_array_equal(traces["Y1_selected"], traces["fixed1"])
    equality_roles = []
    for arm, run in (("Y", 0), ("Y", 2), ("S", 0)):
        np.testing.assert_array_equal(traces[f"{arm}{run}_selected"], traces[f"{arm}{run}_final"])
        equality_roles.append(f"{arm}{run}")
    all_rows = [dict(controller=name, **m) for name, values in metrics.items() for m in values]
    families = {f: np.array([i for i, (c, _) in enumerate(cases) if c["family"] == f]) for f in test.FAMILIES}
    families["all"] = np.arange(18)
    names = ("Y_selected", "Y_final", "S_selected", "S_final", "fixed", "p", "pi", "Y_selectedzero", "Y_finalzero")
    summary, stream = [], []
    for name in names:
        for family, ids in families.items():
            data = [metrics[g][i] for g in group(name) for i in ids]
            summary.append(dict(controller=name, family=family, unique_winds=len(ids), **aggregate(data)))
    identities = []
    for role in lock["roles"]:
        data, trace = metrics[role["id"]], traces[role["id"]]
        for family, ids in families.items():
            stream.append(dict(controller=role["id"], run=role.get("run", ""), step=role.get("step", ""),
                family=family, selected_is_initial=role.get("step") == 0 and role.get("role") == "selected",
                **aggregate([data[i] for i in ids])))
        identities.append(dict(controller=role["id"], kind=role["kind"], arm=role.get("arm", ""),
            run=role.get("run", ""), new_step=role.get("step", ""), source=role,
            speed_z_abs_max=float(np.abs(trace[:, 1:, 46:49]).max()),
            yaw_z_abs_max=float(np.abs(trace[:, 1:, 49:52]).max()),
            speed_residual_nonzero=bool(np.any(trace[:, 1:, 46:49] != 0)),
            yaw_residual_nonzero=bool(np.any(trace[:, 1:, 49:52] != 0)),
            yaw_z_saturation=float(np.mean(np.abs(trace[:, 1:, 49:52]) >= .98)),
            actual_yaw_mean_abs=float(np.abs(trace[:, 1:, 19:28].reshape(18, 128, 3, 3)[:, :, :, 0]).mean()),
            max_heading_rate=max(m["max_heading_rate"] for m in data)))
    specs = []
    for arm in ("Y", "S"):
        for role in ("selected", "final"):
            name = f"{arm}_{role}"
            specs.extend(((name, "pi"), (name, "fixed")))
            if arm == "Y":
                specs.extend(((name, f"S_{role}"), (name, f"Y_{role}zero")))
            if role == "final":
                specs.append((name, f"{arm}_selected"))
    specs.extend((("fixed", "pi"), ("p", "pi")))
    def array(name):
        return np.array([[row["rmse_w"] for row in metrics[g]] for g in group(name)])
    paired, comparisons = [], []
    for name, ref in specs:
        a, b = np.broadcast_arrays(array(name), array(ref))
        for run in range(len(a)):
            for i, (case, _) in enumerate(cases):
                paired.append(dict(controller=name, comparator=ref, run=run if len(a)>1 else "",
                    case=case["id"], episode=case["episode"], family=case["family"],
                    rmse_w=float(a[run, i]), ref_w=float(b[run, i]), delta_w=float(a[run, i]-b[run, i])))
        for family, ids in families.items():
            x, y = a[:, ids], b[:, ids]
            blocks = [families[f] for f in test.FAMILIES] if family == "all" else [np.arange(len(ids))]
            ci = bootstrap(x.mean(axis=0), y.mean(axis=0), blocks, lock["config"]["bootstrap_samples"])
            comparisons.append(dict(controller=name, comparator=ref, family=family, unique_winds=len(ids),
                paired_rows=x.size, mean_w=float(x.mean()), ref_mean_w=float(y.mean()),
                delta_w=float(x.mean()-y.mean()), ratio=float(x.mean()/y.mean()),
                wins=int((x<y).sum()), losses=int((x>y).sum()), ties=int((x==y).sum()), **ci))
    main = [r for r in comparisons if r["controller"] == "Y_selected" and r["comparator"] == "pi" and r["family"] != "all"]
    acceptance = dict(passed=all(r["mean_w"]<r["ref_mean_w"] for r in main), primary="Y_selected",
        criterion=lock["config"]["criterion"], families=main, independent_winds=18,
        case_stream_CI_precision_not_additional_gates=True, selected_by_validation_only=True)
    for name, data in (("metrics.csv", all_rows), ("family_summary.csv", summary), ("stream_summary.csv", stream),
        ("paired_cases.csv", paired), ("comparisons.csv", comparisons), ("query_receipts.csv", counts)):
        csv_out(s, name, data)
    s.json("identity_manifest.json", dict(roles=identities, source_selection_sha=lock["selection_sha"],
        actual_role_rollouts=414, aliases_reused=False, exact_duplicate_policy_roles=equality_roles))
    s.json("primary_acceptance.json", acceptance)
    pressure = pilot.ROOT/"pressure.csv"
    s.write("known_pressure.csv", pressure.read_bytes())
    s.json("known_pressure_source.json", dict(source=str(pressure), sha256=old.sha(pressure), reused=True,
        description="Prior pilot known-pressure evaluation, not a new independent pressure test",
        new_model_rows=0, new_pressure_cases=0, candidate_selection_sha=lock["selection_sha"]))
    s.json("verification.json", dict(passed=True, rollouts=414, input_rows=53406, unique_winds=18,
        optimizer_updates=0, training_steps=0, role_aliases_reused=False, recomputed_metric_records=414,
        zero_yaw_fixed_exact_roles=exact, zero_yaw_fixed_exact_cases=108,
        selected_initial_exact_fixed="Y1_selected", duplicate_roles_exact=equality_roles,
        max_heading_rate=max(r["max_heading_rate"] for r in all_rows),
        max_pitch_rate=max(r["max_pitch_rate"] for r in all_rows), max_speed_rate=max(r["max_speed_rate"] for r in all_rows),
        stage_primary_passed=acceptance["passed"], prior_model_and_learning_limits_retained=True))
    figures(s, summary, traces, comparisons)
    s.write("summary.txt", (f"Frozen Y/S independent test, seed=42. Three-family mean Y selected below PI: {acceptance['passed']}.\n"
        "18 new winds, corrected namespace 74000000..17, 23 roles, 414 actual rollouts, 53406/55000 rows.\n"
        "New training/optimizer updates=0. Known pressure reused from prior pilot with zero new pressure queries.\n"
        "See YAW_INDEPENDENT_TEST_RESULTS.md, primary_acceptance.json, identity_manifest.json and comparisons.csv.\n").encode())
    print("Independent three-family stage acceptance", acceptance["passed"], flush=True)


def figures(s, summary, traces, comparisons):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": .22, "pdf.fonttype": 42})
    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    names = ("Y_selected", "Y_final", "S_selected", "S_final", "fixed", "pi")
    for j, name in enumerate(names):
        a = [next(r["mean_w"] for r in summary if r["controller"] == name and r["family"] == f)/1000 for f in test.FAMILIES]
        ax.bar(np.arange(3)+(j-2.5)*.13, a, width=.12, label=name.replace("_", " "))
    ax.set_xticks(range(3), ("Stationary", "Ramp", "Gust")); ax.set_ylabel("Mean case RMSE (kW)")
    ax.set_title("Frozen independent test | six distinct winds per family"); ax.legend(ncol=3, frameon=False)
    export(s, fig, "family_means")
    fig, axs = plt.subplots(3, 1, figsize=(11, 8), constrained_layout=True)
    for name, label in (("Y2_selected", "Y selected/final"), ("S2_selected", "S selected"),
                         ("fixed2", "fixed C"), ("pi", "PI")):
        tr = traces[name][17]
        axs[0].plot(tr[:, 0], np.rad2deg(tr[:, 19]), label=label)
        axs[1].plot(tr[:, 0], tr[:, 21], label=label)
        axs[2].plot(tr[:, 0], tr[:, 3]/1000, label=label)
    for ax, label in zip(axs, ("T01 actual yaw (deg)", "T01 actual speed (rad/s)", "Farm tracking error (kW)"), strict=True):
        ax.set_ylabel(label); ax.set_xlabel("Time (s)"); ax.legend(ncol=4)
    fig.suptitle("Preselected case 17, gust 3.85 MW / initial pitch .055 rad | stream 2 | current surrogate")
    export(s, fig, "actual_controls_case17")
    fig, ax = plt.subplots(figsize=(9, 4), constrained_layout=True)
    for arm, color in (("Y", "#287eaa"), ("S", "#b36b2e")):
        selected = [np.sqrt(np.mean(traces[f"{arm}{r}_selected"][:, 1:, 3]**2, axis=1)).mean()/1000 for r in range(3)]
        final = [np.sqrt(np.mean(traces[f"{arm}{r}_final"][:, 1:, 3]**2, axis=1)).mean()/1000 for r in range(3)]
        for r in range(3):
            ax.plot([r-.14, r+.14], [selected[r], final[r]], marker="o", color=color, label=arm if r == 0 else None)
    ax.set_xticks(range(3), ("Stream 0", "Stream 1", "Stream 2")); ax.set_ylabel("Independent mean RMSE (kW)")
    ax.set_title("Frozen selected (left) to final (right), identical independent winds"); ax.legend()
    export(s, fig, "selected_final")


def export(s, fig, name):
    import matplotlib.pyplot as plt
    for ext in ("png", "pdf"):
        data = io.BytesIO(); fig.savefig(data, format=ext, dpi=180)
        s.write(f"figures/{name}.{ext}", data.getvalue())
    plt.close(fig)


if __name__ == "__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(old.ORIGIN/".venv/pinn_tf216")
    audit()
