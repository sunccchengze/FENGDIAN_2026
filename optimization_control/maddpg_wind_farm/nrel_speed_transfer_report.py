"""Saved-data audits and figures for frozen speed-rule transfer; no plant calls."""
import argparse
import io
import json

from . import nrel_speed_transfer as run
from . import forecast_speed_training as old
from .forecast_speed_report import csv_out


def legacy(lock):
    from .yaw_pilot_report import read_eval
    groups, traces = {}, {}
    for name, ref in lock["old_evaluations"].items():
        _, saved = read_eval(ref, run.cases(lock), "Y" if name.startswith("Y") else "baseline")
        traces[name] = [run.extend(t, "legacy") for t in saved]
        groups[name] = [run.metric(t, case, "legacy")
                        for t, (case, _) in zip(traces[name], run.cases(lock), strict=True)]
    return groups, traces


def engineering():
    import numpy as np
    import torch
    lock, s = run.context(), run.store()
    record = old.read(run.ROOT/"engineering.json")
    assert record["passed"]
    rows = []
    for entry in record["outcomes"]:
        data = torch.load(old.verify(entry["artifact"]), map_location="cpu", weights_only=False)
        trace = data["trace"]
        actual = trace[:, 19:28].reshape(-1, 3, 3)
        rows.append(dict(controller=entry["controller"], rule=entry["rule"], input_rows=entry["budget"]["actual"],
            old_prefix_exact=entry["old_path_exact"], speed_min=float(actual[:, :, 2].min()),
            speed_max=float(actual[:, :, 2].max()), max_speed_rate=float(np.abs(np.diff(actual[:, :, 2], axis=0)).max()),
            command_min=float(trace[1:, 58:61].min()), command_max=float(trace[1:, 58:61].max()),
            PINN_speed_min=float(data["inputs"][:, 9:12].min()), PINN_speed_max=float(data["inputs"][:, 9:12].max())))
    csv_out(s, "engineering_metrics.csv", rows)
    s.json("engineering_saved_audit.json", dict(passed=True, engineering_rows=160, PINN_rows=120, mock_rows=40,
        full_performance_run=False, trace_fields=list(run.TRACE), guard_count=len(lock["hashes"]),
        parameter_updates=0, frozen_policy_steps=[r["step"] for r in lock["roles"]],
        normalization="old .6..1.267 coordinates; new physical lower bound separate",
        no_model_calls_in_report=True, mock_reset_exact=record["same_mock_reset_trajectory_exact"]))
    print(json.dumps(rows, ensure_ascii=False), flush=True)


def performance():
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from . import nrel_speed_adapter as a
    lock, s = run.context(), run.store()
    complete = old.read(run.ROOT/"complete.json")
    assert complete["new_rows"] == 4030 and complete["training_steps"] == complete["optimizer_updates"] == 0
    groups, traces = legacy(lock)
    groups = {("legacy", key): value for key, value in groups.items()}
    traces = {("legacy", key): value for key, value in traces.items()}
    for entry in complete["results"]:
        name = entry["controller"]
        with np.load(old.verify(entry["eval"]["trace"]), allow_pickle=False) as data:
            assert tuple(data["fields"].tolist()) == run.TRACE
            saved = data["trace"]
        rows = old.read(old.verify(entry["eval"]["metrics"]))
        for row, trace, (case, wind) in zip(rows, saved, run.cases(lock), strict=True):
            assert run.metric(trace, case, "nrel") == row
            np.testing.assert_array_equal(trace[:, 4:7], wind)
            commands = trace[:, 28:37].astype(np.float32)
            np.testing.assert_array_equal(np.mean(np.square(np.diff(commands, axis=0)), axis=1), trace[1:, 8])
            # Speed reference uses the causal previous response; residual is held for eight seconds.
            sy, yz = trace[1:, 46:49], trace[1:, 49:52]
            for z in (sy, yz):
                np.testing.assert_array_equal(z, np.repeat(z[::8], 8, axis=0))
            expected = a.speed_action(a.base_reference(trace[1:, 52:55])+.1*sy)
            np.testing.assert_array_equal(commands[1:].reshape(128, 3, 3)[:, :, 2], expected)
            np.testing.assert_array_equal(trace[1:, 52:55], trace[:-1, 10:13])
        groups["nrel", name], traces["nrel", name] = rows, saved
    csv_out(s, "metrics.csv", [dict(controller=name, **row) for (_, name), rows in groups.items() for row in rows])
    pairs, families = [], []
    for name in [r["id"] for r in lock["roles"]]+["p", "pi"]:
        for before, after in zip(groups["legacy", name], groups["nrel", name], strict=True):
            assert before["case_id"] == after["case_id"]
            pairs.append(dict(controller=name, case_id=before["case_id"], family=before["family"],
                old_kW=before["rmse_w"]/1000, new_kW=after["rmse_w"]/1000,
                new_minus_old_kW=(after["rmse_w"]-before["rmse_w"])/1000))
    csv_out(s, "paired.csv", pairs)
    y = [r["id"] for r in lock["roles"]]
    for rule in ("legacy", "nrel"):
        for family in ("stationary", "ramp", "gust", "overall"):
            def pool(names):
                return [row for name in names for row in groups[rule, name]
                        if family == "overall" or row["family"] == family]
            policy, p, pi = pool(y), pool(["p"]), pool(["pi"])
            means = [float(np.mean([r["rmse_w"] for r in rows])/1000) for rows in (policy, p, pi)]
            families.append(dict(rule=rule, family=family, Y_kW=means[0], P_kW=means[1], PI_kW=means[2],
                Y_minus_PI_kW=means[0]-means[2], Y_cases=len(policy), shared_PI_cases=len(pi),
                Y_at400=sum(r["rmse_w"] <= 400000 for r in policy), Y_at500=sum(r["rmse_w"] <= 500000 for r in policy),
                Y_old_precision_streams=sum(np.mean([r["rmse_w"] for r in pool([name])]) <= 400000
                    and max(r["rmse_w"] for r in pool([name])) <= 500000 for name in y)))
    csv_out(s, "family.csv", families)
    physical = []
    for (rule, name), rows in groups.items():
        physical.append(dict(rule=rule, controller=name, rmse_kW=float(np.mean([r["rmse_w"] for r in rows])/1000),
            speed_min=min(r["speed_min"] for r in rows), speed_max=max(r["speed_max"] for r in rows),
            max_speed_rate=max(r["max_speed_rate"] for r in rows),
            **{key:float(np.mean([r[key] for r in rows])) for key in (
                "base_mean", "command_mean", "speed_mean", "actual_TSR_mean", "base_TSR_mean", "command_TSR_mean",
                "command_floor_fraction", "command_ceiling_fraction", "actual_floor_fraction", "actual_ceiling_fraction",
                "speed_tv", "speed_command_tv", "pitch_tv", "heading_tv", "command_mse")}))
    csv_out(s, "physical.csv", physical)
    def save(fig, name):
        with io.BytesIO() as buffer:
            fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
            s.write(name, buffer.getbuffer())
        plt.close(fig)
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    for rule, style in (("legacy", "--"), ("nrel", "-")):
        for name, color in (("Y2_selected", "C0"), ("pi", "C1")):
            t = traces[rule, name][4]
            axes[0].plot(t[:, 0], t[:, 2]/1e6, style, color=color, label=f"{name} {rule}")
            axes[1].plot(t[:, 0], t[:, 21], style, color=color, label=f"{name} rotor 1 actual {rule}")
            axes[2].plot(t[:, 0], t[:, 61], style, color=color)
    axes[0].axhline(traces["nrel", "Y2_selected"][4][0, 1]/1e6, color="black", alpha=.4)
    axes[0].set_ylabel("Farm power (MW)"); axes[0].legend(ncol=2)
    axes[1].set_ylabel("Rotor 1 speed (rad/s)"); axes[1].axhline(a.LOW, color="black", alpha=.4)
    axes[2].set_ylabel("Rotor 1 actual TSR"); axes[2].set_xlabel("Time (s)")
    for ax in axes: ax.grid(alpha=.25)
    save(fig, "fixed_case4_stream2.png")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    u = np.linspace(4, 14, 501)
    for slope, low, label in ((a.OLD_SLOPE, .6, "Legacy"), (a.SLOPE, a.LOW, "NREL reference")):
        ref = np.clip(slope*u, low, a.HIGH)
        axes[0].plot(u, ref, label=label); axes[1].plot(u, ref*63/u, label=label)
    axes[0].set_ylabel("Base speed (rad/s)"); axes[1].set_ylabel("Base TSR")
    axes[1].axhline(7.55, color="black", linestyle=":")
    for ax in axes: ax.set_xlabel("Effective wind (m/s)"); ax.grid(alpha=.25); ax.legend()
    save(fig, "reference_curves.png")
    run.context()
    s.json("saved_audit.json", dict(passed=True, comparisons=60, old_rollouts_reused=30,
        new_rollouts=30, new_rows=4030, report_queries=0, guard_count=len(lock["hashes"]),
        old_and_new_reward_coordinates_identical=True, causal_effective_wind_verified=True,
        training_steps=0, optimizer_updates=0, migration_only=True, families=families))
    print(json.dumps(families, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("engineering", "performance"))
    args = parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(old.ORIGIN/".venv/pinn_tf216")
    dict(engineering=engineering, performance=performance)[args.phase]()
