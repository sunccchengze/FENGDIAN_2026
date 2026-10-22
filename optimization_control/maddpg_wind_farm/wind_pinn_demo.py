"""Twelve-input team network: explicit synthetic fit, control, save and replay.

Launch before importing NumPy so project-local TF 2.16 owns its NumPy runtime.
Team delivery stays read-only; this file is optimizer-owned integration tooling.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from .fixed_pinn_demo import activate_runtime, digest, load_team_module

DEFAULT = Path(__file__).parent / "configs/wind_pinn_demo.yaml"


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_config(path):
    import yaml
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    if cfg.get("schema_version") != 1 or cfg.get("seed") != 42 or cfg.get("purpose") != "synthetic_wind_pinn_integration_only":
        raise ValueError("explicit synthetic wind integration config with seed=42 required")
    if cfg["data"]["source"] != "geometry_wind_controls_synthetic_test_v1":
        raise ValueError("pinned synthetic teacher required")
    return cfg


def synthetic_labels(physical, positions):
    """Small geometry-aware SOFTWARE teacher; coefficients are uncalibrated.

    Shared entrance only. Projected separation and lateral Gaussian overlap
    exercise direction/layout; TI changes overlap width and power factor.
    No CFD, disk integration, wake time delay or physical identification.
    """
    import numpy as np
    x = np.asarray(physical, dtype=float)
    if x.ndim != 2 or x.shape[1] != 12 or not np.isfinite(x).all():
        raise ValueError("finite grouped twelve-input teacher cases required")
    pos = np.asarray(positions, dtype=float)
    if pos.shape != (3, 3) or not np.isfinite(pos).all():
        raise ValueError("three fixed positions required")
    theta, ti = x[:, 1], x[:, 2]
    c, s = np.cos(theta), np.sin(theta)
    along = c[:, None] * pos[:, 0] + s[:, None] * pos[:, 1]
    cross = -s[:, None] * pos[:, 0] + c[:, None] * pos[:, 1]
    yaw, pitch, speed = x[:, 3:6], x[:, 6:9], x[:, 9:12]
    # Operating extraction participates in upstream/downstream coupling.
    optimum = np.clip(x[:, :1] / 11.4 * 1.267, .6, 1.267)
    extraction = np.exp(-pitch / .21) * np.exp(-.5 * ((speed - optimum) / .45) ** 2)
    effective = np.repeat(x[:, :1], 3, axis=1)
    for j in range(3):
        for i in range(3):
            if i == j:
                continue
            dx = along[:, j] - along[:, i]
            dy = cross[:, j] - cross[:, i]
            width = 80 + 300 * ti + .07 * np.maximum(dx, 0)
            offset = .12 * np.maximum(dx, 0) * np.sin(yaw[:, i])
            overlap = np.exp(-.5 * ((dy - offset) / width) ** 2)
            deficit = np.where(dx > 1e-6, .18 / (1 + np.maximum(dx, 0) / 1000) * overlap * extraction[:, i] * np.cos(yaw[:, i]) ** 2, 0)
            effective[:, j] *= 1 - deficit
    power = 5e6 * np.minimum((effective / 11.4) ** 3, 1) * np.cos(yaw) ** 2 * extraction * (1 - .6 * ti[:, None])
    return np.column_stack((power, effective)).astype(np.float32)


def synthesize(cfg, split):
    import numpy as np
    from ..environments.wind_pinn_backend import TO_TEAM
    index = ("train", "validation", "test").index(split)
    n = int(cfg["data"][split + "_rows"])
    rng = np.random.default_rng(np.random.SeedSequence([42, 1022, index]))
    domain = cfg["domain"]
    lo = np.r_[domain["wind_low"], np.repeat(domain["control_low"], 3)]
    hi = np.r_[domain["wind_high"], np.repeat(domain["control_high"], 3)]
    if n < 32 or np.any(lo >= hi):
        raise ValueError("at least 32 cases and nonempty twelve-input domain required")
    u = np.column_stack([(rng.permutation(n) + rng.random(n)) / n for _ in range(12)])
    physical = lo + u * (hi - lo)
    # Independent fixed-condition slices support the initial fixed-wind curriculum.
    physical[:n // 4, :3] = [9., 0., .1]
    if split == "train":
        physical[-2], physical[-1] = lo, hi
    raw = physical[:, TO_TEAM].astype(np.float32)
    return raw, synthetic_labels(physical, cfg["geometry"]["positions_m"])


def prepare(cfg, root):
    import numpy as np
    from .workflow import write_csv
    from ..environments.wind_pinn_backend import INPUT_ORDER, OUTPUT_ORDER
    root = Path(root)
    data = root / "data"
    data.mkdir()
    package = Path(cfg["package"]).resolve()
    originals = [*package.glob("*.py"), *package.glob("*.txt"), package / "README.md",
                 *sorted((package / "OutputChange").rglob("*.json")),
                 *sorted((package / "OutputChange").rglob("*.keras"))]
    manifest = {str(p): digest(p) for p in originals}
    rows = []
    keys = {}
    for split in ("train", "validation", "test"):
        x, y = synthesize(cfg, split)
        np.savez(data / (split + ".npz"), inputs=x, labels=y)
        write_csv(data / (split + ".csv"), [dict(zip(INPUT_ORDER + OUTPUT_ORDER, map(float, row))) for row in np.column_stack((x, y))])
        keys[split] = {tuple(v) for v in x}
        meta = dict(seed=42, split=split, label_source="synthetic_test", teacher=cfg["data"]["source"],
                    geometry=cfg["geometry"], physical_validation=False, rows=len(x),
                    csv_sha256=digest(data / (split + ".csv")))
        save_json(data / (split + ".json"), meta)
        rows.append(dict(split=split, rows=len(x), minimum_power_w=float(y[:, :3].min()), minimum_ueff_m_s=float(y[:, 3:].min())))
    if any(keys[a] & keys[b] for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))):
        raise RuntimeError("complete cases leaked across splits")
    save_json(data / "source_manifest.json", dict(source_hashes=manifest, seed=42, physical_validation=False))
    write_csv(data / "metrics.csv", rows)
    (data / "summary.txt").write_text("synthetic_test; independent complete-case splits; not physical data\n", encoding="utf-8")
    print("Prepared synthetic cases", flush=True)


def fit(cfg, root):
    import numpy as np
    from .workflow import fresh_output, write_csv
    from ..environments.wind_pinn_backend import SCHEMA, SI_UNITS, INPUT_ORDER, ENCODED_ORDER, OUTPUT_ORDER
    package, root = Path(cfg["package"]).resolve(), Path(root)
    team = load_team_module(package / "modify_pinn_wind_io.py")
    tf, keras, *_ = team.tensorflow_components()
    keras.utils.set_random_seed(42)
    out = fresh_output(root / "model", cfg)
    source = package / "OutputChange/wind_iochanged_9ms/untrained.keras"
    model = keras.models.load_model(str(source), compile=False, safe_mode=True)
    before = team.retained_digest(model)
    build = team.read_json(source.parent / "build_report.json")
    if team.trainable_count(model) != 27106 or before != build["retained_original_sha256"]:
        raise RuntimeError("source trainable/frozen parameters disagree with delivery")
    data = {s: np.load(root / "data" / (s + ".npz")) for s in ("train", "validation", "test")}
    tx, ty = data["train"]["inputs"], data["train"]["labels"]
    xm, xs = team.statistics(team.encoded_features(tx))
    ym, ys = team.statistics(ty)
    for name, mean, std in (("input_normalization", xm, xs), ("output_units", ym, ys)):
        model.get_layer(name).mean.assign(mean)
        model.get_layer(name).std.assign(std)
    for name in OUTPUT_ORDER:
        head = model.get_layer(name + "_readout")
        head.kernel.assign(tf.zeros_like(head.kernel)); head.bias.assign(tf.zeros_like(head.bias))
    positions = np.asarray(cfg["geometry"]["positions_m"], dtype=np.float32)
    fitting = keras.Model(model.inputs, model.get_layer("normalized_predictions").output)
    settings = cfg["model_training"]
    fitting.compile(optimizer=keras.optimizers.Adam(settings["learning_rate"], clipnorm=1.), loss="mse")
    class Progress(keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            print(json.dumps(dict(epoch=epoch + 1, **{k: float(v) for k, v in logs.items()})), flush=True)
    history = fitting.fit(team.inputs_for(tx, positions), (ty - ym) / ys,
        validation_data=(team.inputs_for(data["validation"]["inputs"], positions), (data["validation"]["labels"] - ym) / ys),
        epochs=settings["epochs"], batch_size=settings["batch_size"], verbose=0,
        callbacks=[Progress(), keras.callbacks.EarlyStopping(monitor="val_loss", patience=settings["patience"], restore_best_weights=True)])
    if team.retained_digest(model) != before:
        raise RuntimeError("frozen original backbone changed")
    model.save(str(out / "trained.keras"))
    restored = keras.models.load_model(str(out / "trained.keras"), compile=False, safe_mode=True)
    if team.retained_digest(restored) != before or team.trainable_count(restored) != 27106:
        raise RuntimeError("saved/reloaded backbone changed")
    test = data["test"]
    predicted = team.predict_batches(restored, test["inputs"], positions)
    np.testing.assert_allclose(predicted, team.predict_batches(model, test["inputs"], positions), rtol=1e-5, atol=.001)
    if not np.isfinite(predicted).all():
        raise RuntimeError("nonfinite test prediction")
    rcfg = team.read_json(package / "OutputChange/wind_project_config.json")
    rcfg.update(turbine_positions_m=cfg["geometry"]["positions_m"], geometry_source=cfg["geometry"]["source"],
                turbine_model="synthetic_5mw_assumption", rotor_diameter_m=126., air_density_kg_m3=1.225,
                fixed_inlet_profile_description="software shared entrance only; no resolved vertical profile",
                power_definition="synthetic_test_power_w", ueff_definition="synthetic_test_local_wake_formula_not_disk_integration")
    report = dict(schema=SCHEMA, status="trained_requires_independent_physical_validation", seed=42,
        label_source="synthetic_test", teacher=cfg["data"]["source"], physical_validation=False,
        config=rcfg, physical_input_order=list(INPUT_ORDER), encoded_feature_order=list(ENCODED_ORDER),
        output_order=list(OUTPUT_ORDER), output_units=["W"] * 3 + ["m/s"] * 3,
        trainable_parameters=27106, original_parameters_unchanged=True, retained_original_sha256=before,
        epochs_completed=len(history.epoch), best_epoch=int(np.argmin(history.history["val_loss"])) + 1,
        training_input_min=tx.min(0).tolist(), training_input_max=tx.max(0).tolist(),
        training_direction_covering_arc=team.direction_arc(tx[:, 1]), constant_inputs_in_training=[],
        training_feature_mean=xm.tolist(), training_feature_std=xs.tolist(),
        training_output_mean=ym.tolist(), training_output_std=ys.tolist(),
        new_condition_row_norms=np.linalg.norm(model.get_layer("extended_original_first_dense").condition_kernel.numpy(), axis=1).tolist(),
        source_model_sha256=digest(source), model_sha256=digest(out / "trained.keras"),
        team_script_sha256=digest(package / "modify_pinn_wind_io.py"),
        negative_test_output_count=int(np.count_nonzero(predicted < 0)), test_metrics=team.error_metrics(predicted, test["labels"]),
        split_sha256={s: digest(root / "data" / (s + ".npz")) for s in data},
        runtime_versions=dict(tensorflow=tf.__version__, tf_keras=keras.__version__, numpy=np.__version__),
        initialization="new_readouts_zero; only_training_statistics; source_graph_unchanged")
    save_json(out / "training_report.json", report); save_json(out / "config_used.json", rcfg)
    write_csv(out / "metrics.csv", [dict(epoch=i + 1, loss=float(a), val_loss=float(b)) for i, (a, b) in enumerate(zip(history.history["loss"], history.history["val_loss"]))])
    save_json(out / "summary.txt", report)
    print(json.dumps(report, indent=2), flush=True)
    if report["negative_test_output_count"]:
        raise RuntimeError("negative test outputs; model layer requires diagnosis before RL")


def integration_config(cfg, root):
    import numpy as np
    from .workflow import load_config, DEFAULT_CONFIG
    from ..environments.wind_pinn_backend import TO_TEAM
    run = load_config(DEFAULT_CONFIG)
    root = Path(root).resolve()
    report = json.loads((root / "model/training_report.json").read_text(encoding="utf-8"))
    p, e = run["plant"], run["environment"]
    run["purpose"] = cfg["purpose"]
    p.update(kind="pinn", source="teammate_20261021_synthetic_test", power_semantics="synthetic_test_power_w_not_physical_validation",
        model_version="wind12-synthetic-" + report["model_sha256"][:12],
        factory="optimization_control.environments.wind_pinn_backend:create_predictor",
        backend=dict(run_dir=str(root / "model"), script=str((Path(cfg["package"]) / "modify_pinn_wind_io.py").resolve()),
                     allow_synthetic_demo=True, model_sha256=report["model_sha256"], script_sha256=report["team_script_sha256"]),
        layout=dict(kind="fixed_collinear_equal_spacing", spacing_m=cfg["geometry"]["positions_m"][1][0] - cfg["geometry"]["positions_m"][0][0], source=cfg["geometry"]["source"]))
    lo, hi = np.asarray(report["training_input_min"])[np.argsort(TO_TEAM)], np.asarray(report["training_input_max"])[np.argsort(TO_TEAM)]
    p["bounds"] = {name: [float(a - 1e-6), float(b + 1e-6)] for name, a, b in zip(p["features"], lo, hi)}
    p["bounds"]["ambient_wind_direction_rad"] = [0., float(2 * np.pi + 1e-6)]  # backend enforces circular learned arc
    e.update(action_low=cfg["controls"]["low"], action_high=cfg["controls"]["high"], initial_operating_point=cfg["controls"]["initial"],
             wind_base_m_s=9., wind_amplitude_m_s=0., wind_noise_std_m_s=0., wind_direction_rad=0., turbulence_intensity=.1,
             horizon=cfg["maddpg"]["horizon"], reward_scale=cfg["maddpg"]["reward_scale"], inflow=deepcopy(cfg["inflow"]))
    e["parameter_source"].update(reference="configs/wind_pinn_demo.yaml", note="synthetic integration limits, not calibrated actuators")
    run["training"].update({k: cfg["maddpg"][k] for k in ("total_steps", "warmup_steps", "update_every", "noise_std")})
    initial = 2 * (np.asarray(e["initial_operating_point"]) - e["action_low"]) / (np.asarray(e["action_high"]) - e["action_low"]) - 1
    run["algorithm"].update(actor_lr=cfg["maddpg"]["actor_lr"], actor_initial_action=initial.tolist())
    return run


def check_model(cfg, root, run):
    import numpy as np
    from .workflow import build_env, fresh_output, write_csv
    from ..environments.wind_pinn_backend import INPUT_ORDER, TO_TEAM
    env = build_env(run)
    out = fresh_output(Path(root) / "model_checks", cfg)
    base = np.r_[9., 0., .1, [0.] * 3, [.04] * 3, [.9] * 3]
    domain = cfg["domain"]
    low = np.r_[domain["wind_low"], np.repeat(domain["control_low"], 3)]
    high = np.r_[domain["wind_high"], np.repeat(domain["control_high"], 3)]
    probes = [base.copy()]
    for j in range(12):
        for v in (low[j], high[j]):
            a = base.copy(); a[j] = v; probes.append(a)
    rng = np.random.default_rng(np.random.SeedSequence([42, 1023]))
    probes.extend(rng.uniform(low, high, (256, 12)))
    x = np.asarray(probes)
    y = env.plant.predictor(x)
    if np.any(y[:, :3] > env.rated * 1.001):
        raise RuntimeError("model exceeds demonstration rated power")
    rows = []
    inverse = np.argsort(TO_TEAM)
    for j in range(12):
        a, b = 1 + j * 2, 2 + j * 2
        # Symmetric yaw and direction endpoints need not differ; compare to zero.
        if j in (1, 3, 4, 5):
            a = 0
        delta = y[b] - y[a]
        rows.append(dict(input=INPUT_ORDER[int(inverse[j])], grouped_column=j,
            power_response_w=float(np.abs(delta[:3]).max()), ueff_response_m_s=float(np.abs(delta[3:]).max()),
            own_power_change_w=float(delta[j - 6]) if 6 <= j <= 8 else 0.,
            responds=bool(np.abs(delta[:3]).max() > .001 or np.abs(delta[3:]).max() > 1e-6)))
    if not all(r["responds"] for r in rows) or any(rows[j]["own_power_change_w"] >= 0 for j in (6, 7, 8)):
        raise RuntimeError("missing input response or incorrect pitch feedback sign")
    aliases = np.tile(base, (3, 1)); aliases[:, 1] = [0, 2 * np.pi, -2 * np.pi]
    np.testing.assert_allclose(env.plant.predictor(aliases), np.tile(y[0], (3, 1)), rtol=1e-5, atol=.1)
    # Feasible points along a continuous common-pitch path, not a global bound.
    sweep = np.tile(base, (257, 1)); sweep[:, 6:9] = np.linspace(0, cfg["controls"]["high"][1], 257)[:, None]
    powers = env.plant.predictor(sweep)[:, :3].sum(1)
    minimum, maximum = float(powers.min()), float(powers.max())
    targets = [minimum + f * (maximum - minimum) for f in (.25, .5, .75)]
    write_csv(out / "metrics.csv", rows)
    write_csv(out / "pitch_sweep.csv", [dict(pitch_rad=float(a), farm_power_w=float(b)) for a, b in zip(sweep[:, 6], powers)])
    summary = dict(seed=42, probes=len(x), all_twelve_inputs_respond=True, pitch_sign_verified=True,
        circular_aliases_equal=True, min_power_w=float(y[:, :3].min()), min_ueff_m_s=float(y[:, 3:].min()),
        common_pitch_power_range_w=[minimum, maximum], single_targets_w=targets,
        monotone_common_pitch=bool(np.all(np.diff(powers) <= 0)), physical_validation=False)
    save_json(out / "summary.txt", summary)
    print(json.dumps(summary), flush=True)
    return summary


def verify_rollouts(run, traces, initial_directions):
    """Audit heading rate (gamma can also move when the entrance direction moves)."""
    import numpy as np
    e = run["environment"]
    maximum = np.zeros(3)
    for scenario in {r["scenario"] for r in traces}:
        winds = []
        for mode in ("maddpg", "fixed", "p", "pi"):
            part = [r for r in traces if r["scenario"] == scenario and r["controller"] == mode]
            wind = np.array([[r[k] for k in ("wind_m_s", "direction_rad", "ti")] for r in part])
            winds.append(wind)
            heading = np.array([[r[f"heading_{i}_rad"] for i in (1, 2, 3)] for r in part])
            gamma = np.array([[r[f"yaw_rad_{i}"] for i in (1, 2, 3)] for r in part])
            np.testing.assert_allclose((heading - wind[:, 1:2] + np.pi) % (2 * np.pi) - np.pi, gamma, atol=1e-6)
            applied = np.array([[[r[f"heading_{i}_rad"], r[f"pitch_rad_{i}"], r[f"speed_rad_s_{i}"]] for i in (1, 2, 3)] for r in part])
            initial = np.tile(e["initial_operating_point"], (3, 1)).astype(float)
            initial[:, 0] += initial_directions[scenario]
            delta = np.diff(np.concatenate((initial[None, :, :], applied)), axis=0)
            maximum = np.maximum(maximum, np.abs(delta).max(axis=(0, 1)))
            if np.any(applied[:, :, 1:] < np.asarray(e["action_low"])[1:] - 1e-6) or np.any(applied[:, :, 1:] > np.asarray(e["action_high"])[1:] + 1e-6):
                raise RuntimeError("actual pitch/speed outside actuator bounds")
            np.testing.assert_allclose(np.array([r["farm_power_w"] for r in part]), np.array([[r[f"power_{i}_w"] for i in (1, 2, 3)] for r in part]).sum(1), atol=.01)
        for wind in winds[1:]:
            np.testing.assert_array_equal(winds[0], wind)
    if np.any(maximum > np.asarray(e["rate_limits"]) * e["dt_s"] + 1e-6):
        raise RuntimeError("actual actuator rate exceeded")
    return dict(rows=len(traces), heading_gamma_verified=True, shared_inflow_verified=True,
                farm_power_sum_verified=True, max_actuator_step=maximum.tolist())


def initial_directions(run, evaluation_dir):
    import numpy as np
    values = {}
    for i, scenario in enumerate(run["evaluation"]["scenarios"]):
        if "wind_trajectory" in scenario:
            values[scenario["name"]] = scenario["wind_trajectory"][0][1]
        else:
            values[scenario["name"]] = float(np.loadtxt(Path(evaluation_dir) / f"inflow_{i}.csv", delimiter=",", skiprows=1, ndmin=2)[0, 2])
    return values


def read_traces(path):
    import csv
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [{k: (v if k in ("scenario", "controller") else float(v)) for k, v in row.items()} for row in csv.DictReader(f)]


def replay(cfg, root, output):
    """Reload saved policy/network in a new process; compare every saved row."""
    from .algorithm import MADDPG
    from .workflow import build_env, evaluate
    root = Path(root).resolve()
    checkpoint = root / "training/checkpoint.pth"
    before = digest(checkpoint)
    _, saved = MADDPG.load(checkpoint)
    # Rebind paths in memory only, so the experiment can be copied to a new root.
    saved["config"]["plant"]["backend"]["run_dir"] = str(root / "model")
    saved["config"]["plant"]["backend"]["script"] = str((Path(cfg["package"]) / "modify_pinn_wind_io.py").resolve())
    run = saved["config"]
    env = build_env(run)
    if env.normalization() != saved["normalization"]:
        raise RuntimeError("replay normalization differs")
    evaluate(checkpoint, output, backend_paths={k: run["plant"]["backend"][k] for k in ("run_dir", "script")})
    traces = read_traces(Path(output) / "trajectories.csv")
    expected = read_traces(root / "evaluation/trajectories.csv")
    if traces != expected:
        raise RuntimeError("full new-process replay differs from saved trajectory")
    audit = verify_rollouts(run, traces, initial_directions(run, output))
    if digest(checkpoint) != before:
        raise RuntimeError("replay modified checkpoint")
    save_json(Path(output) / "replay_audit.json", dict(seed=42, full_replay_equal=True,
        checkpoint_sha256=before, model_sha256=env.plant.predictor.model_sha256,
        checkpoint_unchanged=True, physical_validation=False, **audit))
    print(json.dumps(audit), flush=True)


def control(cfg, root):
    import numpy as np
    from .workflow import build_env, make_agent, train, evaluate, write_csv
    from .algorithm import MADDPG
    root = Path(root)
    run = integration_config(cfg, root)
    checks = check_model(cfg, root, run)
    targets = checks["single_targets_w"]
    run["environment"]["target_w"] = targets[1]
    run["training"]["episode_target_fractions"] = [v / 15e6 for v in targets]
    fixed = np.tile([9., 0., .1], (cfg["maddpg"]["horizon"] + 1, 1)).tolist()
    run["evaluation"]["scenarios"] = [dict(name=f"fixed_{i}", target_w=v, wind_trajectory=fixed) for i, v in enumerate(targets)]
    run["evaluation"]["scenarios"] += [dict(name=name, target_w=targets[1], inflow=dict(speed=dict(scenario=name))) for name in ("stationary", "ramp", "gust")]
    env = build_env(run)
    initial = make_agent(run, env)
    initial_dir = root / "initial"; initial_dir.mkdir()
    initial_path = initial_dir / "checkpoint.pth"
    initial.save(initial_path, dict(config=run, steps=0, episodes=0, normalization=env.normalization()))
    initial_metrics = evaluate(initial_path, root / "initial_evaluation")
    checkpoint = train(run, root / "training")
    final_metrics = evaluate(checkpoint, root / "evaluation")
    traces, before = read_traces(root / "evaluation/trajectories.csv"), read_traces(root / "initial_evaluation/trajectories.csv")
    if [r for r in traces if r["controller"] != "maddpg"] != [r for r in before if r["controller"] != "maddpg"]:
        raise RuntimeError("baseline changed between initial/final evaluation")
    audit = verify_rollouts(run, traces, initial_directions(run, root / "evaluation"))
    agent, meta = MADDPG.load(checkpoint)
    replay_env = build_env(run)
    def replay(policy):
        obs, _ = replay_env.reset(seed=42, options=dict(split="validation", episode=900, target_w=targets[1]))
        values = []
        for _ in range(replay_env.horizon):
            obs, _, _, _, info = replay_env.step(policy.act(obs))
            values.append(np.r_[info["power_w"], info["effective_wind_m_s"], info["heading_rad"], info["applied"].ravel()])
        return np.asarray(values)
    other, _ = MADDPG.load(checkpoint)
    np.testing.assert_array_equal(replay(agent), replay(other))
    if agent.updates <= 0 or meta["steps"] != cfg["maddpg"]["total_steps"]:
        raise RuntimeError("short training updates incomplete")
    manifest = json.loads((root / "data/source_manifest.json").read_text(encoding="utf-8"))["source_hashes"]
    if not all(digest(p) == h for p, h in manifest.items()):
        raise RuntimeError("team source changed")
    write_csv(root / "metrics.csv", [dict(stage=label, **r) for label, rows in (("initial", initial_metrics), ("trained", final_metrics)) for r in rows])
    save_json(root / "summary.txt", dict(status="wind12_software_integration_completed", seed=42,
        physical_validation=False, source_files_unchanged=True, model_sha256=digest(root / "model/trained.keras"),
        steps=meta["steps"], updates=agent.updates, full_saved_reloaded_replay_equal=True,
        baselines_identical=True, checks=checks, trace_audit=audit))
    print("Twelve-input synthetic integration complete", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("prepare", "fit", "control", "all", "replay"))
    ap.add_argument("--config", default=str(DEFAULT)); ap.add_argument("--output", required=True)
    ap.add_argument("--replay-output")
    args = ap.parse_args()
    cfg = read_config(args.config)
    activate_runtime(cfg["runtime_site_packages"])
    sys.dont_write_bytecode = True
    from .workflow import fresh_output
    root = Path(args.output)
    if args.command in ("prepare", "all"):
        fresh_output(root, cfg); prepare(cfg, root)
        (root / "metrics.csv").write_bytes((root / "data/metrics.csv").read_bytes())
        save_json(root / "summary.txt", dict(status="synthetic_data_prepared", seed=42, physical_validation=False))
    elif read_config(root / "config.yaml") != cfg:
        raise ValueError("experiment identity changed; use a new output")
    if args.command == "replay":
        if not args.replay_output:
            ap.error("replay requires --replay-output pointing to a new directory")
        replay(cfg, root, args.replay_output)
        return
    if args.command in ("fit", "all"):
        fit(cfg, root)
    if args.command in ("control", "all"):
        control(cfg, root)


if __name__ == "__main__":
    main()
