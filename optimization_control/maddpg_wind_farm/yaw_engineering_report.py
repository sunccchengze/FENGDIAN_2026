"""Recompute saved yaw engineering trajectories and draw physical controls, query-free."""
import csv
import hashlib
import io
from pathlib import Path

from ..tests.verify_yaw_takeover import CAP, ROOT, context, equal, torch_load
from . import forecast_speed_training as formal


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def report():
    import numpy as np
    import torch
    lock = context()
    store = formal.Store(ROOT, CAP)
    complete = formal.read(ROOT/"complete.json")
    assert complete["passed"] and complete["rows"] == 3399 and complete["updates"] == 3
    zeros = formal.read(ROOT/"real_zero.json")["cases"]
    audits, references = [], {}
    for entry in zeros:
        saved = torch_load(entry["artifact"])
        a, b = saved["actual"], saved["reference"]
        for key in ("trace", "obs", "inputs", "speed", "rewards", "prefix_sha", "decisions"):
            equal(a[key], b[key])
        assert len(a["macros"]) == 16
        assert np.all(a["yaw"] == 0)
        held = a["speed"].reshape(16, 8, 3)
        np.testing.assert_array_equal(held, np.repeat(held[:, :1], 8, axis=1))
        for i, row in enumerate(a["macros"]):
            # Replay action, rewards, state and next-state are independently tied to saved execution.
            np.testing.assert_array_equal(row["z"], a["yaw"][i*8])
            np.testing.assert_array_equal(row["raw_reward"], a["rewards"][i*8:i*8+8])
            np.testing.assert_array_equal(row["obs"], a["obs"][i*8])
            np.testing.assert_array_equal(row["next_obs"], a["obs"][i*8+8])
            np.testing.assert_array_equal(row["return"],
                (a["rewards"][i*8:i*8+8].astype(float)*(.99**np.arange(8))[:, None]).sum(axis=0))
            assert row["discount"] == .99**8 and bool(row["terminal"]) == (i == 15)
        rmse = float(np.sqrt(np.mean(a["trace"][1:, 3]**2)))
        assert rmse == entry["rmse_w"]
        references[entry["run"], entry["case"]] = a
        audits.append(dict(run=entry["run"], case=entry["case"], original_step=entry["original_step"],
            rmse_kW=rmse/1000, action_max_diff=0., actual_max_diff=0., power_max_diff_W=0.,
            speed_z_max=float(np.max(np.abs(a["speed"]))), online_target_zero=True,
            replay_execution_exact=True))
    store.write("zero_pairs.csv", csv_bytes(audits))
    nonzero = formal.read(ROOT/"real_nonzero.json")["cases"]
    base = references[2, "val_stationary_2850000"]
    curves = [("zero", base)]
    physical_rows = []
    for row in nonzero:
        data = torch_load(row["artifact"])
        sign, trace = row["sign"], data["trace"]
        actual = trace[:, 19:28].reshape(129, 3, 3)
        heading = trace[:, 16:19]
        gamma = (heading-trace[:, 5, None]+np.pi)%(2*np.pi)-np.pi
        np.testing.assert_allclose(gamma, actual[:, :, 0], atol=1e-7, rtol=0)
        np.testing.assert_allclose(data["inputs"][:, 3:6], gamma, atol=1e-7, rtol=0)
        np.testing.assert_allclose(data["inputs"][:, 6:9], actual[:, :, 1], atol=1e-7, rtol=0)
        np.testing.assert_allclose(data["inputs"][:, 9:12], actual[:, :, 2], atol=1e-7, rtol=0)
        rmse = float(np.sqrt(np.mean(trace[1:, 3]**2)))
        assert rmse == row["metrics"]["rmse_w"]
        assert float(np.max(np.abs(np.diff(heading, axis=0)))) <= .005+1e-12
        np.testing.assert_array_equal(data["yaw"], np.full((128, 3), sign, np.float32))
        physical_rows.append(dict(sign=sign, case="val_stationary_2850000", run=2,
            yaw_radius_deg=1., rmse_kW=rmse/1000, rmse_delta_kW=row["RMSE_delta_w"]/1000,
            heading_delta_max_rad=row["max_heading_delta_rad"],
            PINN_gamma_delta_max_rad=row["max_PINN_gamma_delta_rad"],
            heading_rate_max_rad_s=row["metrics"]["max_heading_rate"],
            pitch_rate_max_rad_s=row["metrics"]["max_pitch_rate"],
            speed_rate_max_rad_s=row["metrics"]["max_speed_rate"]))
        curves.append((f"{sign:+d} deg", data))
    store.write("nonzero_physical.csv", csv_bytes(physical_rows))
    # Compare durable data and reject state files that omit replay/Adam/target equivalence.
    continuous = torch_load(dict(path=str(ROOT/"mock_continuous/state.pt"),
        sha256=formal.sha(ROOT/"mock_continuous/state.pt")))
    disk_receipt = formal.read(ROOT/"mock_disk/result.json")
    equal(continuous, torch_load(disk_receipt["state"]))
    assert continuous["updates"] == 2 and continuous["steps"] == 640
    assert continuous["replay"]["insertions"] == 80
    assert continuous["boundary"]["pending"] is None
    for name in ("head_adam", "critic_adam"):
        assert all(bool(x["state"]) for x in continuous["adam"][name])
    # Executed reusable tensor comparer is an unchanged file from the reviewed base.
    comparator = Path(__file__).parents[1]/"tests/verify_forecast_speed_macro.py"
    blob = formal.git("show", f"c6a27774ec7cd34113ed7e37b47947b279fef86a:{comparator.relative_to(formal.REPO).as_posix()}")
    assert hashlib.sha256(blob).hexdigest() == formal.sha(comparator)
    # Produce a shareable scientific figure from saved trajectories only.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": .25,
                         "pdf.fonttype": 42, "savefig.dpi": 180})
    fig, axs = plt.subplots(3, 2, figsize=(11, 9), constrained_layout=True)
    t = np.arange(129)
    colors = ("#444444", "#cc6611", "#3366bb")
    for (label, d), color in zip(curves, colors, strict=True):
        tr = d["trace"]
        applied = tr[:, 19:28].reshape(129, 3, 3)
        axs[0, 0].plot(t, np.rad2deg(tr[:, 16]-tr[0, 16]), label=label, color=color)
        axs[0, 1].plot(t, np.rad2deg(applied[:, 0, 0]), label=label, color=color)
        axs[1, 0].plot(t, tr[:, 2]/1e6, label=label, color=color)
        axs[1, 1].plot(t[1:], tr[1:, 3]/1000, label=label, color=color)
        axs[2, 0].plot(t, np.rad2deg(applied[:, 0, 1]), label=label, color=color)
        axs[2, 1].plot(t, applied[:, 0, 2], label=label, color=color)
    axs[1, 0].axhline(2.85, color="black", linestyle="--", alpha=.7, label="target")
    labels = (("T01 actual heading change (deg)", "T01 actual yaw misalignment (deg)"),
              ("Farm power (MW)", "Farm tracking error (kW)"),
              ("T01 actual pitch (deg)", "T01 actual rotor speed (rad/s)"))
    for i in range(3):
        for j in range(2):
            axs[i, j].set_ylabel(labels[i][j]); axs[i, j].set_xlabel("Time (s)")
    axs[0, 0].legend(ncol=3)
    axs[1, 0].legend(ncol=2)
    fig.suptitle("C2 frozen parent with imposed yaw offsets | old stationary validation, 2.85 MW\n"
                 "Current surrogate software engineering | feedback pitch and speed remain active", fontsize=12)
    for ext in ("png", "pdf"):
        buf = io.BytesIO()
        fig.savefig(buf, format=ext)
        store.write(f"figures/yaw_physical_controls.{ext}", buf.getvalue())
    plt.close(fig)
    store.json("saved_artifact_audit.json", dict(source_files=len(lock["hashes"]), sources_verified=True,
        zero_pairs=len(audits), zero_trace_RMSE_and_replay_exact=True,
        physical_nonzero_cases=2, SI_pitch_speed_gamma=True, disk_state_exact=True,
        comparator_matches_base=True, saved_current_target_Adam_replay_rng_checked=True,
        additional_model_rows=0, additional_updates=0, plotted_old_validation_only=True))
    print("Saved artifacts verified, 0 new model rows. Figure exported.", flush=True)


if __name__ == "__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(formal.ORIGIN/".venv/pinn_tf216")
    report()
