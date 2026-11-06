"""Summaries and figures from saved ablation trajectories, with zero model calls."""
from collections import defaultdict
from pathlib import Path
from statistics import fmean

from .pitch_gamma_review import gz_rows
from .pitch_memory_ablation import OUTPUT, PLANNED, SPLITS, digest, read_csv, read_json, size, verify


METRICS = ("rmse_w", "mean_error_w", "bias_squared_w2", "variance_w2", "pitch_travel_rad",
           "pitch_rms_rate_rad_s", "pitch_rate_fraction", "pitch_boundary_fraction", "pitch_command_actual_rms_rad")
CONTRASTS = (("normal_minus_read0", "memory", "ablated"), ("read0_minus_zero", "ablated", "zero"),
             ("read0_minus_parent", "ablated", "parent"), ("normal_minus_zero", "memory", "zero"))


def paired(saved, generated):
    lookup = {(r["collection"], int(r["run"]), r["role"], r["arm"], r["case_id"]): r for r in saved+generated}
    result = []
    for row in generated:
        s, run, role, cid = row["collection"], int(row["run"]), row["role"], row["case_id"]
        key = (s, run, role, cid)
        pi = float(lookup[s, -1, "pi", "pi", cid]["rmse_w"])
        p = float(lookup[s, -1, "p", "p", cid]["rmse_w"])
        common = dict(collection=s, run=run, role=role, case_id=cid, family=row["family"],
                      target_w=float(row["target_w"]), initial_pitch_rad=float(row["initial_pitch_rad"]),
                      primary=int(s == "known" and cid.startswith("train_episode_8_initial_")), pi_rmse_w=pi, p_rmse_w=p)
        for name, left_arm, right_arm in CONTRASTS:
            left = lookup[key[0], key[1], key[2], left_arm, key[3]]
            right = lookup[s, run, "initial" if right_arm == "parent" else role, right_arm, cid]
            result.append(compare(common, name, left, right))
        if role == "final":
            for arm in ("memory", "ablated", "zero"):
                result.append(compare(common, f"{arm}_final_minus_selected", lookup[s, run, "final", arm, cid],
                                      lookup[s, run, "selected", arm, cid]))
    return result


def compare(common, name, left, right):
    out = dict(common, contrast=name, left_rmse_w=float(left["rmse_w"]), right_rmse_w=float(right["rmse_w"]))
    out.update({f"delta_{key}": float(left[key])-float(right[key]) for key in METRICS})
    out.update(left_weaker_pi=int(out["left_rmse_w"] > out["pi_rmse_w"]),
               right_weaker_pi=int(out["right_rmse_w"] > out["pi_rmse_w"]))
    return out


def groups(rows):
    result = defaultdict(list)
    for row in rows:
        prefix = (row["collection"], row["role"], row["contrast"])
        for run in ("all", row["run"]):
            family, target, pitch = (row[k] for k in ("family", "target_w", "initial_pitch_rad"))
            keys = [("all", None, None), (family, None, None), (family, target, None), (family, target, pitch)]
            if row["primary"]:
                keys.append(("primary", None, None))
            for key in keys:
                result[prefix+(run,)+key].append(row)
    labels = ("collection", "role", "contrast", "run", "family", "target_w", "initial_pitch_rad")
    result_rows = []
    for key, values in result.items():
        counts = [r["delta_rmse_w"] for r in values]
        result_rows.append(dict(zip(labels, key), cases=len(values), improved=sum(n < 0 for n in counts),
            worsened=sum(n > 0 for n in counts), worst_delta_rmse_w=max(counts),
            left_weaker_pi=sum(r["left_weaker_pi"] for r in values), right_weaker_pi=sum(r["right_weaker_pi"] for r in values),
            **{k: fmean(r[k] for r in values) for k in ("left_rmse_w", "right_rmse_w", "pi_rmse_w", "p_rmse_w", *(f"delta_{m}" for m in METRICS))}))
    return result_rows


def summarize_probes(rows):
    grouped = defaultdict(list)
    zeros = {(r["run"], r["role"], r["case_id"], r["step"], r["turbine"]): r for r in rows if r["arm"] == "zero"}
    for r in rows:
        if r["arm"] != "memory":
            continue
        z = zeros[r["run"], r["role"], r["case_id"], r["step"], r["turbine"]]
        e, integral = float(r["error_w"]), float(r["integral_rad"])
        dp = float(r["pitch_real"]) - float(r["pitch_zero"])
        g, g0, gz = map(float, (r["dq_da_real"], r["dq_da_zero"], z["dq_da_zero"]))
        values = dict(delta_pitch=dp, abs_pitch=abs(dp), sensitivity=float(r["d_pitch_d_i"]),
            same_error_sign=dp*e > 0, opposite_error_sign=dp*e < 0,
            delta_q=float(r["q_real"])-float(r["q_zero"]), delta_g=g-g0, gradient_flip=g*g0 < 0,
            drift_pitch_vs_parent=float(r["pitch_zero"])-float(r["parent_pitch_zero"]),
            drift_pitch_vs_zero=float(r["pitch_zero"])-float(z["pitch_zero"]),
            drift_q_vs_zero=float(r["q_zero"])-float(z["q_zero"]),
            drift_gradient_vs_zero=g0-gz, drift_gradient_flip=g0*gz < 0, active=integral != 0)
        for run in ("all", r["run"]):
            for family, target in (("all", ""), (r["family"], ""), (r["family"], r["target_w"])):
                grouped[r["role"], run, r["turbine"], family, target].append(values)
    output = []
    for (role, run, turbine, family, target), values in grouped.items():
        active = [v for v in values if v["active"]]
        output.append(dict(role=role, run=run, turbine=turbine, family=family, target_w=target,
            n=len(values), n_active=len(active), max_abs_pitch=max(v["abs_pitch"] for v in values),
            mean_abs_sensitivity=fmean(abs(v["sensitivity"]) for v in values),
            mean_abs_delta_q=fmean(abs(v["delta_q"]) for v in values),
            mean_abs_delta_g=fmean(abs(v["delta_g"]) for v in values),
            mean_abs_drift_pitch_vs_parent=fmean(abs(v["drift_pitch_vs_parent"]) for v in values),
            mean_abs_drift_pitch_vs_zero=fmean(abs(v["drift_pitch_vs_zero"]) for v in values),
            mean_abs_drift_gradient_vs_zero=fmean(abs(v["drift_gradient_vs_zero"]) for v in values),
            **{k: fmean(v[k] for v in (active if k in ("same_error_sign", "opposite_error_sign") else values))
                for k in values[0] if k != "active"}))
    return output


def figures(store, cfg, aggregate, index):
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from .pitch_error_memory_review import resolve

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    panels = (("known", "selected"), ("known", "final"), ("validation", "selected"), ("validation", "final"))
    families = ("stationary", "ramp", "gust", "all")
    for ax, (split, role) in zip(axes.flat, panels, strict=True):
        x = np.arange(len(families))
        for i, (contrast, label) in enumerate((("normal_minus_read0", "Normal − read 0"), ("read0_minus_zero", "Read 0 − trained zero"))):
            rows = [next(r for r in aggregate if (r["collection"], r["role"], r["contrast"], r["run"], r["family"], r["target_w"]) ==
                         (split, role, contrast, "all", f, None)) for f in families]
            ax.bar(x+(.34*i-.17), [r["delta_rmse_w"]/1000 for r in rows], .33, label=label)
        ax.axhline(0, color=".35", linewidth=.8)
        ax.set_xticks(x, ("Steady", "Slow ramp", "Gust", "Overall"))
        ax.set(title=f"{split.title()} · {role}", ylabel="Paired RMSE difference (kW)")
    axes[0, 0].legend(frameon=False, loc="best")
    save_figure(store, fig, "paired_ablation.png", io)

    fig, axes = plt.subplots(4, 2, figsize=(14, 11), sharex=True, layout="constrained")
    cases = [("known", "train_episode_8_initial_0.055"), ("validation", next(c["id"] for c in cfg["cases"]["validation"] if c["family"] == "ramp"))]
    for col, (split, cid) in enumerate(cases):
        normal_entry = next(e for e in cfg["sources"][split] if (e["arm"], e["run"], e["role"]) == ("memory", 0, "final"))
        _, normal = resolve(normal_entry)
        record = next(r for r in index if (r["collection"], r["run"], r["role"], r["case_id"]) == (split, 0, "final", cid))
        for trace, name in ((normal[cid], "Normal"), (gz_rows(OUTPUT / record["path"]), "Read 0")):
            time = [int(r["response_step"]) for r in trace]
            axes[0, col].plot(time, [float(r["error_w"])/1000 for r in trace], label=name)
            line, = axes[1, col].plot(time, [float(r["pitch_actual_0"]) for r in trace], label=name)
            axes[1, col].plot(time, [float(r["pitch_command_0"]) for r in trace], linestyle=":", color=line.get_color())
            axes[2, col].plot(time, [float(r["integral_rad"]) for r in trace], label=name)
        axes[3, col].plot(time, [float(r["response_wind_m_s"]) for r in normal[cid]], color=".25")
        axes[0, col].set_title(f"{split.title()} · {cid}", fontsize=10)
        axes[0, col].legend(frameon=False)
        for ax, label in zip(axes[:, col], ("Power error (kW)", "T1 pitch (rad)", "Recorded I (rad)", "Inlet wind (m/s)"), strict=True):
            ax.set_ylabel(label)
        axes[3, col].set_xlabel("Response time (s)")
    fig.suptitle("Stream 0 final · solid actual pitch, dotted pitch target", fontsize=13)
    save_figure(store, fig, "full_episode_ablation.png", io)
    plt.close("all")


def save_figure(store, fig, name, io):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=145)
    store.put(name, buffer.getvalue())


def report(cfg, store):
    import math

    run = read_json(OUTPUT / "execution.json")
    verify(run["hashes"])
    assert run["model_rows"] == PLANNED and run["config_sha"] == digest(OUTPUT / "config.yaml")
    index = read_json(OUTPUT / "trajectory_manifest.json")
    verify({str(OUTPUT / r["path"]): r["sha256"] for r in index})
    old, new = [read_csv(OUTPUT / f) for f in ("saved_metrics.csv", "ablation_metrics.csv")]
    assert len(old) == 918 and len(new) == 324
    for row in old+new:
        mse = float(row["bias_squared_w2"])+float(row["variance_w2"])
        assert math.isclose(float(row["rmse_w"])**2, mse, rel_tol=1e-12)
    for r in index:
        trace = gz_rows(OUTPUT / r["path"])
        assert len(trace) == 128 and all(float(t["context_input_rad"]) == 0. for t in trace)
    comparisons = paired(old, new)
    assert len(comparisons) == 1782
    aggregate = groups(comparisons)
    probes = summarize_probes(gz_rows(OUTPUT / "probes.csv.gz"))
    store.table("metrics.csv", old+new)
    store.table("paired_cases.csv", comparisons)
    store.table("aggregate.csv", aggregate)
    store.table("probe_aggregate.csv", probes)
    figures(store, cfg, aggregate, index)
    core = [r for r in aggregate if r["run"] == "all" and r["target_w"] is None and r["family"] in ("all", "ramp", "primary")]
    store.json("summary.txt", dict(status="complete", predictor_rows=PLANNED, optimizer_updates=0,
        new_test_cases=0, stored_bytes_before_summary=size(OUTPUT), metrics=len(old)+len(new), paired_rows=len(comparisons), core=core))
