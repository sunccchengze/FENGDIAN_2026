"""Fixed-condition, nine-control transfer model and MADDPG integration demo.

The launcher activates project-local TensorFlow 2.16 BEFORE NumPy is imported.
Only synthetic labels are fitted; team files and the frozen backbone stay intact.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

DEFAULT = Path(__file__).parent / "configs/fixed_pinn_demo.yaml"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_team_path(path):
    """Resolve only the documented old delivery move; never guess a new version."""
    path = Path(path)
    if not path.exists():
        parts = path.parts
        for i in range(len(parts) - 1):
            if parts[i] == "pinn" and parts[i + 1] == "PINNs_multi_turbine_wake_simulation-outputchange":
                moved = Path(*parts[:i + 1], "2026_1007", *parts[i + 1:])
                if moved.exists():
                    return moved
    return path


def load_team_module(script):
    path = resolve_team_path(script).resolve()
    name = "_wind_team_pinn_io_" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name]


def activate_runtime(path):
    runtime = Path(path).resolve()
    if not (runtime / "tensorflow").is_dir() or not (runtime / "tf_keras").is_dir():
        raise RuntimeError("Install the documented project-local TensorFlow 2.16 runtime first: " + str(runtime))
    if "numpy" in sys.modules or "tensorflow" in sys.modules:
        raise RuntimeError("Runtime must be activated before importing numerical libraries")
    sys.path.insert(0, str(runtime))
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")


def read_config(path):
    import yaml
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if cfg.get("schema_version") != 1 or cfg.get("seed") != 42:
        raise ValueError("schema_version=1 and seed=42 required")
    if cfg["purpose"] != "synthetic_fixed_condition_integration_only" or cfg["data"]["source"] != "coupled_integration_mock":
        raise ValueError("explicit synthetic integration provenance required")
    return cfg


def physical_inputs(controls, fixed):
    """Interleaved team-unit deg/deg/rpm controls -> grouped physical 12 fields."""
    import numpy as np
    c = np.asarray(controls).reshape(-1, 3, 3)
    x = np.empty((len(c), 12), dtype=np.float32)
    x[:, :3] = [fixed["speed_m_s"], fixed["direction_rad"], fixed["turbulence_intensity"]]
    x[:, 3:6] = c[:, :, 0] * np.pi / 180
    x[:, 6:9] = c[:, :, 1] * np.pi / 180
    x[:, 9:12] = c[:, :, 2] * np.pi / 30
    return x


def synthesize(cfg, split):
    import numpy as np
    from ..environments.pinn_adapter import CoupledIntegrationPredictor
    from ..environments.teammate_pinn_backend import unit_factors
    index = {"train": 0, "validation": 1, "test": 2}[split]
    count = cfg["data"][split + "_rows"]
    if count < 32:
        raise ValueError("at least 32 rows per split required")
    rng = np.random.default_rng(np.random.SeedSequence([42, 700, index]))
    # Independent stratified marginals; validation/test never reused for fitting.
    u = np.column_stack([(rng.permutation(count) + rng.random(count)) / count for _ in range(9)])
    lo = np.tile(cfg["controls"]["low"], 3)
    hi = np.tile(cfg["controls"]["high"], 3)
    if np.any(lo >= hi):
        raise ValueError("nonempty nine-control domain required")
    values = lo + u * (hi - lo)
    if split == "train":
        # Include exact endpoints so every allowed actuator point is admitted.
        values[0], values[1] = lo, hi
    factors = unit_factors(dict(yaw="deg", pitch="deg", rotor_speed="rpm"))
    controls = (values * factors).astype(np.float32)
    x = physical_inputs(controls, cfg["fixed_condition"])
    labels = CoupledIntegrationPredictor([5e6] * 3)(x)
    return controls, labels


def prepare(cfg, root):
    import numpy as np
    from .workflow import fresh_output, write_csv
    from ..environments.teammate_pinn_backend import CONTROL_ORDER, OUTPUT_ORDER, validate_positions
    out = fresh_output(Path(root) / "data", cfg)
    validate_positions(cfg["geometry"]["positions_m"])
    metrics = []
    for split in ("train", "validation", "test"):
        x, y = synthesize(cfg, split)
        np.savez(out / (split + ".npz"), controls=x, labels=y)
        write_csv(out / (split + ".csv"), [dict(zip(CONTROL_ORDER + OUTPUT_ORDER, map(float, row))) for row in np.concatenate([x, y], axis=1)])
        metrics.append(dict(split=split, rows=len(x), minimum_power_w=float(y[:, :3].min()), maximum_power_w=float(y[:, :3].max())))
    metadata = dict(seed=42, source="coupled_integration_mock", physical_validation=False,
                    geometry=cfg["geometry"], fixed_condition=cfg["fixed_condition"],
                    controls=list(CONTROL_ORDER), outputs=list(OUTPUT_ORDER),
                    units=["deg", "deg", "rpm"] * 3 + ["W"] * 3 + ["m/s"] * 3,
                    split_hashes={s: digest(out / (s + ".npz")) for s in ("train", "validation", "test")},
                    note="Teacher has fixed index coupling; it does not resolve geometry, direction, TI or real wake steering.")
    package = Path(cfg["package"]).resolve()
    originals = [package / "modify_pinn_io.py", package / "prepare_pinn_outputchange.py",
        package / "OutputChange/project_config.json", package / "OutputChange/iochanged_9ms/build_report.json",
        *sorted((package / "OutputChange").rglob("*.keras"))]
    metadata["source_hashes"] = {str(p): digest(p) for p in originals}
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for split in ("train", "validation", "test"):
        split_meta = dict(metadata, split=split, rows=cfg["data"][split + "_rows"], csv_sha256=digest(out / (split + ".csv")))
        (out / (split + ".json")).write_text(json.dumps(split_meta, indent=2), encoding="utf-8")
    write_csv(out / "metrics.csv", metrics)
    (out / "summary.txt").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("Synthetic data ready:", out, flush=True)


def fit(cfg, root):
    import numpy as np
    from .workflow import fresh_output, write_csv
    from ..environments.teammate_pinn_backend import CONTROL_ORDER, OUTPUT_ORDER
    package = Path(cfg["package"]).resolve()
    team = load_team_module(package / "modify_pinn_io.py")
    tf, keras, *_ = team.tensorflow_components()
    keras.utils.set_random_seed(42)
    out = fresh_output(Path(root) / "model", cfg)
    source = package / "OutputChange/iochanged_9ms/untrained.keras"
    model = keras.models.load_model(str(source), compile=False, safe_mode=True)
    before = team.retained_digest(model)
    if team.trainable_count(model) != 24306:
        raise RuntimeError("unexpected trainable parameter set")
    data = {s: np.load(Path(root) / "data" / (s + ".npz")) for s in ("train", "validation", "test")}
    train_x, train_y = data["train"]["controls"], data["train"]["labels"]
    xm, xs = train_x.mean(0), train_x.std(0)
    ym, ys = train_y.mean(0), train_y.std(0)
    if np.any(xs <= 0):
        raise ValueError("training statistics require varied controls")
    # Upstream Ueff is exactly the fixed inlet in this synthetic teacher.
    ys = np.where(ys <= 1e-8, 1.0, ys)
    for name, mean, std in (("control_normalization", xm, xs), ("output_units", ym, ys)):
        layer = model.get_layer(name)
        layer.mean.assign(mean)
        layer.std.assign(std)
    # Initialize ONLY new readouts at the training mean, keeping constant Ueff1
    # exact and avoiding large arbitrary outputs from random untrained heads.
    for name in OUTPUT_ORDER:
        head = model.get_layer(name + "_readout")
        head.kernel.assign(tf.zeros_like(head.kernel))
        head.bias.assign(tf.zeros_like(head.bias))
    positions = np.asarray(cfg["geometry"]["positions_m"], dtype=np.float32)
    def inputs(x):
        return dict(controls=x, turbine_positions=np.broadcast_to(positions, (len(x), 3, 3)).copy())
    fitting = keras.Model(model.inputs, model.get_layer("normalized_predictions").output)
    settings = cfg["model_training"]
    fitting.compile(optimizer=keras.optimizers.Adam(settings["learning_rate"], clipnorm=1.0), loss="mse")
    class Progress(keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            print(json.dumps(dict(epoch=epoch + 1, **{k: float(v) for k, v in logs.items()})), flush=True)
    history = fitting.fit(inputs(train_x), (train_y - ym) / ys,
        validation_data=(inputs(data["validation"]["controls"]), (data["validation"]["labels"] - ym) / ys),
        epochs=settings["epochs"], batch_size=settings["batch_size"], verbose=0,
        callbacks=[Progress(), keras.callbacks.EarlyStopping(monitor="val_loss", patience=settings["patience"], restore_best_weights=True)])
    if team.retained_digest(model) != before:
        raise RuntimeError("frozen original backbone changed")
    write_csv(out / "metrics.csv", [dict(epoch=i + 1, loss=float(a), val_loss=float(b)) for i, (a, b) in enumerate(zip(history.history["loss"], history.history["val_loss"]))])
    run_cfg = dict(turbine_positions_m=cfg["geometry"]["positions_m"], control_units=dict(yaw="deg", pitch="deg", rotor_speed="rpm"),
                   fixed_inlet_wind_speed_m_s=cfg["fixed_condition"]["speed_m_s"], geometry_source=cfg["geometry"]["source"])
    model.save(str(out / "trained.keras"))
    restored = keras.models.load_model(str(out / "trained.keras"), compile=False, safe_mode=True)
    if team.retained_digest(restored) != before:
        raise RuntimeError("reloaded frozen backbone digest changed")
    prediction = np.asarray(restored(inputs(data["test"]["controls"]), training=False))
    np.testing.assert_allclose(prediction, np.asarray(model(inputs(data["test"]["controls"]), training=False)), rtol=1e-5, atol=1e-3)
    if not np.all(np.isfinite(prediction)):
        raise RuntimeError("nonfinite synthetic test predictions")
    errors = prediction - data["test"]["labels"]
    report = dict(status="synthetic_fixed_condition_demo", physical_validation=False, seed=42,
        label_source="coupled_integration_mock", original_parameters_unchanged=True, retained_original_sha256=before,
        runtime_versions=dict(tensorflow=tf.__version__, tf_keras=keras.__version__, numpy=np.__version__),
        new_control_row_norms=np.linalg.norm(model.get_layer("extended_original_first_dense").control_kernel.numpy(), axis=1).tolist(),
        source_model_sha256=digest(source), team_script_sha256=digest(package / "modify_pinn_io.py"),
        source_build_report_sha256=digest(source.parent / "build_report.json"),
        config=run_cfg, fixed_condition=cfg["fixed_condition"], control_order=list(CONTROL_ORDER), output_order=list(OUTPUT_ORDER),
        output_units=["W"] * 3 + ["m/s"] * 3, trainable_parameters=24306, epochs_completed=len(history.history["loss"]),
        best_epoch=int(np.argmin(history.history["val_loss"])) + 1,
        initialization="new_readouts_zero_standardized_output_equals_training_mean", constant_controls_in_training=[], training_control_min=train_x.min(0).tolist(), training_control_max=train_x.max(0).tolist(),
        negative_test_output_count=int(np.count_nonzero(prediction < 0)),
        test_metrics={n: dict(RMSE=float(np.sqrt(np.mean(errors[:, i] ** 2))), MAE=float(np.mean(np.abs(errors[:, i]))), unit="W" if i < 3 else "m/s") for i, n in enumerate(OUTPUT_ORDER)})
    (out / "config_used.json").write_text(json.dumps(run_cfg, indent=2), encoding="utf-8")
    (out / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "summary.txt").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    # No prediction clipping: domain problems must be diagnosed before RL.
    if report["negative_test_output_count"]:
        raise RuntimeError("negative synthetic test outputs; inspect training before proceeding")


def integration_config(cfg, root):
    import numpy as np
    from .workflow import load_config, DEFAULT_CONFIG
    run = load_config(DEFAULT_CONFIG)
    fixed = cfg["fixed_condition"]
    run["purpose"] = cfg["purpose"]
    plant = run["plant"]
    plant.update(kind="pinn", source="teammate_backbone_synthetic_demo", power_semantics="synthetic_mock_power_w_not_physical_validation",
        model_version="synthetic-demo-" + digest(Path(root) / "model/trained.keras")[:12],
        factory="optimization_control.environments.teammate_pinn_backend:create_demo_predictor",
        backend=dict(run_dir=str((Path(root) / "model").resolve()), script=str((Path(cfg["package"]) / "modify_pinn_io.py").resolve()),
            allow_synthetic_demo=True, fixed_condition=dict(direction_rad=fixed["direction_rad"], turbulence_intensity=fixed["turbulence_intensity"]),
            yaw_convention="misalignment_same_sign_as_gamma"),
        layout=dict(kind="fixed_collinear_equal_spacing", spacing_m=cfg["geometry"]["positions_m"][1][0] - cfg["geometry"]["positions_m"][0][0], source=cfg["geometry"]["source"]))
    for prefix, j in (("gamma", 0), ("beta", 1), ("omega", 2)):
        for i in range(1, 4):
            # Wider float32 envelope here; predictor still checks exact fitted domain.
            plant["bounds"][f"{prefix}_{i}"] = [cfg["controls"]["low"][j] - 1e-6, cfg["controls"]["high"][j] + 1e-6]
    e = run["environment"]
    e.update(action_low=cfg["controls"]["low"], action_high=cfg["controls"]["high"], initial_operating_point=cfg["controls"]["initial"],
        wind_base_m_s=fixed["speed_m_s"], wind_amplitude_m_s=0.0, wind_noise_std_m_s=0.0,
        wind_direction_rad=fixed["direction_rad"], turbulence_intensity=fixed["turbulence_intensity"],
        horizon=cfg["maddpg"]["horizon"], reward_scale=cfg["maddpg"]["reward_scale"])
    e["parameter_source"].update(reference="configs/fixed_pinn_demo.yaml", note="fixed-condition synthetic integration assumptions")
    run["training"].update({k: cfg["maddpg"][k] for k in ("total_steps", "warmup_steps", "update_every", "noise_std")})
    run["training"]["episode_target_fractions"] = [v / 15e6 for v in cfg["maddpg"]["training_targets_w"]]
    initial = 2 * (np.asarray(cfg["controls"]["initial"]) - e["action_low"]) / (np.asarray(e["action_high"]) - e["action_low"]) - 1
    run["algorithm"].update(actor_lr=cfg["maddpg"]["actor_lr"], actor_initial_action=initial.tolist())
    run["evaluation"]["scenarios"] = [dict(name=f"fixed9_target_{int(v)}w", wind_base_m_s=9.0, target_w=v) for v in cfg["maddpg"]["evaluation_targets_w"]]
    return run


def check_model(cfg, root, run):
    import numpy as np
    from .workflow import fresh_output, write_csv, build_env
    from ..environments.teammate_pinn_backend import CONTROL_ORDER, unit_factors
    env = build_env(run)
    out = fresh_output(Path(root) / "model_checks", cfg)
    low, high = np.asarray(cfg["controls"]["low"]), np.asarray(cfg["controls"]["high"])
    base = np.tile(cfg["controls"]["initial"], 3).astype(float)
    probes = [base, np.tile(low, 3), np.tile(high, 3)]
    for j in range(9):
        for v in (low[j % 3], high[j % 3]):
            p = base.copy(); p[j] = v; probes.append(p)
    # Joint in-domain probes plus endpoints; no silent bounds clipping.
    rng = np.random.default_rng(np.random.SeedSequence([42, 701]))
    probes.extend(rng.uniform(np.tile(low, 3), np.tile(high, 3), size=(128, 9)))
    factors = unit_factors(dict(yaw="deg", pitch="deg", rotor_speed="rpm"))
    x = physical_inputs(np.asarray(probes) * factors, cfg["fixed_condition"])
    y = env.plant.predictor(x)
    if np.any(y[:, :3] > env.rated * 1.001):
        raise RuntimeError("synthetic model exceeds declared rating in model checks")
    rows = []
    for j, name in enumerate(CONTROL_ORDER):
        # Yaw endpoints are symmetric in the teacher; compare zero to +yaw.
        a, b = (0, 4 + j * 2) if j % 3 == 0 else (3 + j * 2, 4 + j * 2)
        delta = y[b] - y[a]
        rows.append(dict(control=name, max_power_change_w=float(np.abs(delta[:3]).max()),
            max_ueff_change_m_s=float(np.abs(delta[3:]).max()),
            own_power_change_w=float(delta[j // 3]), responds=bool(np.abs(delta[:3]).max() > 1e-3 or np.abs(delta[3:]).max() > 1e-6)))
    if not all(r["responds"] for r in rows):
        raise RuntimeError("some controls have no measurable demo response")
    # Existing P/PI assumes increasing pitch decreases own/farm power.
    for j in (1, 4, 7):
        if rows[j]["own_power_change_w"] >= 0:
            raise RuntimeError("pitch feedback sign disagrees with existing P/PI in demo checks")
    write_csv(out / "metrics.csv", rows)
    summary = dict(probes=len(x), all_nine_controls_respond=True, pitch_feedback_sign_checked=True,
        min_power_w=float(y[:, :3].min()), max_power_w=float(y[:, :3].max()),
        min_ueff_m_s=float(y[:, 3:].min()), max_ueff_m_s=float(y[:, 3:].max()),
        physical_validation=False, scope="limited synthetic-domain response checks, not physics certification")
    (out / "summary.txt").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


def run_control(cfg, root):
    import numpy as np
    from .workflow import train, evaluate, make_agent, build_env, write_csv
    from .algorithm import MADDPG
    run = integration_config(cfg, root)
    check_model(cfg, root, run)
    env = build_env(run)
    obs, _ = env.reset(seed=42)
    initial_agent = make_agent(run, env)
    initial_dir = Path(root) / "initial"
    initial_dir.mkdir()
    initial_agent.save(initial_dir / "checkpoint.pth", dict(config=run, steps=0, episodes=0, normalization=env.normalization()))
    initial_metrics = evaluate(initial_dir / "checkpoint.pth", Path(root) / "initial_evaluation")
    checkpoint = train(run, Path(root) / "training")
    metrics = evaluate(checkpoint, Path(root) / "evaluation")
    trace_checks = verify_trace(cfg, root)
    loaded, saved = MADDPG.load(checkpoint)
    env2 = build_env(run)
    obs2, _ = env2.reset(seed=42)
    obs3, _ = env2.reset(seed=42)
    np.testing.assert_array_equal(obs2, obs3)
    a = loaded.act(obs2)
    reloaded, _ = MADDPG.load(checkpoint)
    np.testing.assert_array_equal(a, reloaded.act(obs2))
    if loaded.updates <= 0 or saved["steps"] != run["training"]["total_steps"]:
        raise RuntimeError("MADDPG did not complete planned updates")
    # The same controller + model reset must reproduce an entire episode.
    def replay():
        obs, _ = env2.reset(seed=42)
        values = []
        for _ in range(env2.horizon):
            obs, _, _, _, info = env2.step(loaded.act(obs))
            values.append(np.r_[info["power_w"], info["effective_wind_m_s"], info["applied"].ravel()])
        return np.asarray(values)
    np.testing.assert_array_equal(replay(), replay())
    rows = [dict(stage="initial" if label == "initial" else "trained", **r) for label, values in (("initial", initial_metrics), ("trained", metrics)) for r in values]
    write_csv(Path(root) / "metrics.csv", rows)
    report = dict(status="fixed_condition_integration_completed", seed=42, physical_validation=False,
        network_control_inputs=9, adapter_context_inputs=12, model_sha256=digest(Path(root) / "model/trained.keras"),
        fixed_condition=cfg["fixed_condition"], geometry=cfg["geometry"],
        steps=saved["steps"], updates=loaded.updates, checkpoint=str(checkpoint.resolve()),
        repeat_reset_equal=True, saved_loaded_actions_equal=True, full_episode_replay_equal=True,
        trace_checks=trace_checks,
        compared_controllers=["initial_maddpg", "trained_maddpg", "fixed", "p", "pi"],
        conclusion="Software integration only; synthetic-label fit and short RL are not physical accuracy, convergence or superiority evidence.")
    meta = json.loads((Path(root) / "data/metadata.json").read_text(encoding="utf-8"))
    if not meta.get("source_hashes"):
        raise RuntimeError("missing original-source manifest; prepare a new checked experiment")
    report["source_files_unchanged"] = all(digest(p) == h for p, h in meta["source_hashes"].items())
    if not report["source_files_unchanged"]:
        raise RuntimeError("team source changed during demo")
    (Path(root) / "summary.txt").write_text(json.dumps(report, indent=2), encoding="utf-8")
    plot_demo(root)
    print(json.dumps(report, indent=2), flush=True)


def verify_trace(cfg, root):
    """Audit actual rollout actuator bounds/rates, fixed wind and baseline reuse."""
    import csv
    import numpy as np
    root = Path(root)
    def read(path):
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    rows = read(root / "evaluation/trajectories.csv")
    fixed = cfg["fixed_condition"]
    wind = np.asarray([[float(r[k]) for k in ("wind_m_s", "direction_rad", "ti")] for r in rows])
    np.testing.assert_allclose(wind, np.tile([fixed["speed_m_s"], fixed["direction_rad"], fixed["turbulence_intensity"]], (len(wind), 1)), atol=1e-7, rtol=0)
    max_delta = np.zeros(3)
    for name in sorted({r["scenario"] for r in rows}):
        for mode in ("maddpg", "fixed", "p", "pi"):
            part = [r for r in rows if r["scenario"] == name and r["controller"] == mode]
            a = np.asarray([[[float(r[f"{k}_rad_{i}"]) for k in ("yaw", "pitch")] + [float(r[f"speed_rad_s_{i}"])] for i in (1, 2, 3)] for r in part])
            if np.any(a < np.asarray(cfg["controls"]["low"]) - 1e-6) or np.any(a > np.asarray(cfg["controls"]["high"]) + 1e-6):
                raise RuntimeError("actual actuator operating points outside demo domain")
            initial = np.tile(cfg["controls"]["initial"], (3, 1))[None, :, :]
            max_delta = np.maximum(max_delta, np.abs(np.diff(np.concatenate([initial, a]), axis=0)).max(axis=(0, 1)))
            heading = np.asarray([[float(r[f"heading_{i}_rad"]) for i in (1, 2, 3)] for r in part])
            wrapped = (heading - fixed["direction_rad"] + np.pi) % (2 * np.pi) - np.pi
            np.testing.assert_allclose(a[:, :, 0], wrapped, atol=1e-6, rtol=0)
    from .workflow import load_config, DEFAULT_CONFIG
    limits = np.asarray(load_config(DEFAULT_CONFIG)["environment"]["rate_limits"])
    if np.any(max_delta > limits + 1e-6):
        raise RuntimeError("actual actuator rates exceeded configured limits")
    initial_rows = read(root / "initial_evaluation/trajectories.csv")
    key = lambda r: (r["scenario"], r["controller"], r["step"])
    before = {key(r): r for r in initial_rows if r["controller"] != "maddpg"}
    after = {key(r): r for r in rows if r["controller"] != "maddpg"}
    if before != after:
        raise RuntimeError("P/PI/fixed baselines differ between initial and trained evaluations")
    return dict(fixed_wind_verified=True, applied_bounds_verified=True, heading_gamma_relation_verified=True,
        max_per_step_changes=max_delta.tolist(), rate_limits=limits.tolist(), baseline_trajectories_identical=True, evaluated_rows=len(rows))


def plot_demo(root):
    import csv
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    root = Path(root)
    def rows(path):
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    model, rl = rows(root / "model/metrics.csv"), rows(root / "training/metrics.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for key in ("loss", "val_loss"):
        axes[0].plot([float(r["epoch"]) for r in model], [float(r[key]) for r in model], label=key)
    axes[0].set(xlabel="Transfer epoch", ylabel="Standardized MSE + regularization")
    axes[1].plot([float(r["steps"]) for r in rl], [float(r["rmse_w"]) / 1e6 for r in rl], label="MADDPG train RMSE")
    axes[1].set(xlabel="Control steps", ylabel="RMSE [MW]")
    for ax in axes:
        ax.legend(); ax.grid(alpha=.2)
    fig.suptitle("Synthetic fixed-condition integration; not physical validation")
    fig.tight_layout(); fig.savefig(root / "training_curves.png", dpi=140); plt.close(fig)
    trace = rows(root / "evaluation/trajectories.csv")
    scenario = sorted({r["scenario"] for r in trace})[1]
    fig, axes = plt.subplots(3, 3, figsize=(12, 8), sharex=True)
    for i in range(3):
        for j, field in enumerate(("yaw_rad", "pitch_rad", "speed_rad_s")):
            for mode in ("maddpg", "fixed", "p", "pi"):
                part = [r for r in trace if r["scenario"] == scenario and r["controller"] == mode]
                axes[j, i].plot([float(r["time_s"]) for r in part], [float(r[f"{field}_{i+1}"]) for r in part], label=mode)
            axes[j, i].grid(alpha=.2)
            axes[j, i].set_ylabel(field)
            if j == 0: axes[j, i].set_title(f"Turbine {i+1}")
            if j == 2: axes[j, i].set_xlabel("Time [s]")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle(scenario + " | applied actuator operating points")
    fig.tight_layout(); fig.savefig(root / "applied_controls.png", dpi=140); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "fit", "control", "all"))
    parser.add_argument("--config", default=str(DEFAULT))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    cfg = read_config(args.config)
    if args.command != "prepare":
        activate_runtime(cfg["runtime_site_packages"])
    from .workflow import fresh_output
    root = Path(args.output)
    if args.command in ("prepare", "all"):
        root = fresh_output(root, cfg)
        prepare(cfg, root)
        (root / "metrics.csv").write_bytes((root / "data/metrics.csv").read_bytes())
        (root / "summary.txt").write_text("status=synthetic_data_prepared\nseed=42\nnext_stage=fit\nphysical_validation=false\n", encoding="utf-8")
    else:
        if not root.is_dir():
            raise ValueError("prepare the output directory first")
        existing = read_config(root / "config.yaml")
        if existing != cfg:
            raise ValueError("prepared experiment config differs; use a new output directory")
    if args.command in ("fit", "all"):
        fit(cfg, root)
    if args.command in ("control", "all"):
        run_control(cfg, root)


if __name__ == "__main__":
    main()
