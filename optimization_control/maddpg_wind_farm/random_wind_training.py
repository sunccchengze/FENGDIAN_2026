"""Frozen random-inflow training with shared reference schedules and locked test."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .fixed_pinn_demo import activate_runtime, digest

DEFAULT = Path(__file__).parent / "configs/random_wind_training.yaml"
FAMILIES = ("stationary", "ramp", "gust")
STAGES = (("pitch", [0, 1, 0]), ("pitch_speed", [0, 1, 1]), ("all", [1, 1, 1]))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def write_csv(path, rows):
    import csv
    if not rows:
        raise ValueError("nonempty result rows required")
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def fresh(path, cfg):
    import yaml
    path = Path(path); path.mkdir(parents=True, exist_ok=False)
    (path / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
    return path


def read_protocol(path):
    import yaml
    p = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    if p.get("version") != "wind12_random_training_v1" or p.get("seed") != 42:
        raise ValueError("random wind protocol version and master seed 42 required")
    groups = [set(p[k]) for k in ("training_targets_w", "validation_targets_w", "test_targets_w")]
    if any(groups[a] & groups[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("training/validation/test targets must be disjoint")
    if len(set(p["run_ids"])) < 3 or len(set(p["run_ids"])) != len(p["run_ids"]):
        raise ValueError("three distinct derived training streams required")
    if p["steps_per_run"] % p["horizon"] or p["eval_every"] % p["horizon"] or p["steps_per_run"] <= 0:
        raise ValueError("complete-episode budgets required")
    if p["warmup_steps"] < 0 or p["update_every"] < 1:
        raise ValueError("invalid training schedule")
    return p


def episode_design(p, run_id, episode):
    """Every block covers the Cartesian product, without family/target aliasing."""
    import numpy as np
    pairs = [(f, t) for f in FAMILIES for t in p["training_targets_w"]]
    block, index = divmod(episode, len(pairs))
    rng = np.random.default_rng(np.random.SeedSequence([42, 710, run_id, block]))
    family, target = pairs[int(rng.permutation(len(pairs))[index])]
    initial_rng = np.random.default_rng(np.random.SeedSequence([42, 711, run_id, episode]))
    pitch = float(initial_rng.uniform(*p["training_initial_pitch_rad"]))
    return family, float(target), pitch


def make_config(p):
    import yaml
    source = Path(p["source_experiment"])
    cfg = yaml.safe_load((source / "training/config.yaml").read_text(encoding="utf-8"))
    if cfg["plant"]["source"] != "teammate_20261021_synthetic_test":
        raise ValueError("pinned twelve-input synthetic network required")
    e = cfg["environment"]
    e.update(inflow=deepcopy(p["inflow"]), horizon=p["horizon"], dt_s=p["dt_s"], control_mask=[0, 1, 0],
             reference_schedule=deepcopy(p["background_schedule"]))
    cfg["algorithm"].update(actor_lr=p["actor_lr"], capacity=max(32768, p["steps_per_run"]))
    cfg["purpose"] = p["scope"]
    return cfg


def prepare(p, output):
    import numpy as np
    from ..environments.farm_inflow import generate_inflow
    from .workflow import build_env
    cfg = make_config(p)
    source = Path(p["source_experiment"]).resolve()
    protected = json.loads((source / "data/source_manifest.json").read_text(encoding="utf-8"))["source_hashes"]
    protected.update({str(source / "model" / n): digest(source / "model" / n) for n in ("trained.keras", "training_report.json", "config_used.json")})
    root = fresh(output, dict(seed=42, protocol=p, base_config=cfg, source_hashes=protected)).resolve()
    bank = root / "bank"; bank.mkdir()
    manifest = dict(version="farm_benchmark_v1", seed=42, cases=[])
    env = build_env(cfg)
    for split, targets, pitches, offset in (("validation", p["validation_targets_w"], [.04], 110000),
                                             ("test", p["test_targets_w"], p["test_initial_pitch_rad"], 220000)):
        for family_index, family in enumerate(FAMILIES):
            for j, target in enumerate(targets):
                inflow = deepcopy(p["inflow"]); inflow["speed"]["scenario"] = family
                trace = generate_inflow(inflow, dt_s=p["dt_s"], horizon=p["horizon"], seed=42,
                                        split=split, episode=offset + family_index * 100 + j)
                path = bank / f"{split}_{family}_{j}.csv"; trace.save(path)
                # Check ambient envelope and circular wind range before training.
                from ..environments.wind_pinn_backend import team_inputs, wrap
                model_domain = env.plant.predictor
                raw = np.tile(np.r_[9., 0., .1, [0.] * 3, [.04] * 3, [.9] * 3], (len(trace.values), 1))
                raw[:, :3] = trace.values
                converted = team_inputs(raw)
                if np.any(converted[:, 0] < model_domain.lo[0] - 1e-6) or np.any(converted[:, 0] > model_domain.hi[0] + 1e-6):
                    raise ValueError("bank wind speed outside trained network domain")
                arc = model_domain.arc
                if np.any(np.abs(wrap(converted[:, 1] - arc["start_rad"] - arc["width_rad"] / 2)) > arc["width_rad"] / 2 + 1e-6):
                    raise ValueError("bank wind direction outside trained network domain")
                if np.any((converted[:, 2] < model_domain.lo[2] - 1e-6) | (converted[:, 2] > model_domain.hi[2] + 1e-6)):
                    raise ValueError("bank TI outside trained network domain")
                for pitch in pitches:
                    manifest["cases"].append(dict(id=f"{split}_{family}_{j}_pitch{pitch}", split=split, family=family,
                        path=path.name, csv_sha256=digest(path), json_sha256=digest(path.with_suffix(".json")),
                        target_w=float(target), initial_pitch_rad=float(pitch)))
    # Explicit low-wind/high-target test, separated from routine aggregates.
    inflow = deepcopy(p["inflow"]); inflow["speed"]["scenario"] = "stationary"
    trace = generate_inflow(inflow, dt_s=p["dt_s"], horizon=p["horizon"], seed=42, split="test", episode=229000)
    trace.values[:] = [7.6, 0., .08]; trace.components[:] = [7.6, 0., 0.]
    trace.metadata.update(override_family="low_wind_stress", source="explicit_low_wind_test_not_generated_turbulence")
    path = bank / "test_low_wind_stress.csv"; trace.save(path)
    for pitch in p["test_initial_pitch_rad"]:
        manifest["cases"].append(dict(id=f"test_low_wind_stress_pitch{pitch}", split="test", family="low_wind_stress",
            path=path.name, csv_sha256=digest(path), json_sha256=digest(path.with_suffix(".json")), target_w=4.4e6, initial_pitch_rad=pitch))
    write_json(bank / "manifest.json", manifest)
    statistics(p, root)
    preflight_training_winds(p, root)
    write_csv(root / "metrics.csv", [dict(stage="prepared", rows=len(manifest["cases"]))])
    write_json(root / "summary.txt", dict(status="prepared", seed=42, test_locked=True))
    print("Prepared independent bank and wind statistics", flush=True)
    return root


def statistics(p, root):
    import numpy as np
    from scipy.signal import welch
    from ..environments.farm_inflow import generate_inflow
    from ..environments.wind_generator import kaimal_psd
    rows = []
    for family in FAMILIES:
        ratios, variances, rejected = [], [], []
        for episode in range(330000, 330064):
            inflow = deepcopy(p["inflow"]); inflow["speed"]["scenario"] = family
            trace = generate_inflow(inflow, dt_s=p["dt_s"], horizon=p["horizon"], seed=42, split="validation", episode=episode)
            m = trace.metadata["speed_metadata"]
            f, psd = welch(trace.components[:, 1], fs=1 / p["dt_s"], nperseg=min(128, len(trace.time_s)))
            theory = kaimal_psd(f, m["mean_m_s"], m["mean_m_s"] * m["ti_requested"], p["inflow"]["speed"]["length_scale_m"])
            band = (f >= .03) & (f <= .35)
            ratios.append(psd[band] / theory[band]); variances.append(np.mean(trace.components[:, 1] ** 2) / m["expected_band_variance_m2_s2"])
            rejected.append(m["rejected_attempts"])
        rows.append(dict(family=family, records=64, ensemble_psd_ratio=float(np.median(np.mean(ratios, axis=0))),
            ensemble_mean_square_ratio=float(np.mean(variances)), total_rejected_attempts=sum(rejected), max_rejected_attempts=max(rejected)))
    write_csv(Path(root) / "wind_statistics.csv", rows)


def preflight_training_winds(p, root):
    from ..environments.farm_inflow import generate_inflow
    rows = []
    for run_id in p["run_ids"]:
        for episode in range(p["steps_per_run"] // p["horizon"]):
            family, target, pitch = episode_design(p, run_id, episode)
            inflow = deepcopy(p["inflow"]); inflow["speed"]["scenario"] = family
            trace = generate_inflow(inflow, dt_s=p["dt_s"], horizon=p["horizon"], seed=42,
                split="train", episode=40000 + run_id * 1000 + episode)
            rows.append(dict(run_id=run_id, episode=episode, family=family, target_w=target, initial_pitch_rad=pitch,
                rejected_attempts=trace.metadata["speed_metadata"]["rejected_attempts"],
                values_sha256=hashlib.sha256(trace.values.tobytes()).hexdigest()))
    write_csv(Path(root) / "training_wind_preflight.csv", rows)
    return rows


def cases(root, split, *, allow_test=False):
    from .benchmark import load_cases
    return load_cases(Path(root) / "bank", split, allow_test=allow_test)


def rollout(cfg, bank_cases, *, agent=None, mode=None, capture=False):
    import numpy as np
    from .workflow import build_env
    from .controllers import PitchController
    from ..environments.maddpg_farm_env import wrap_angle
    if (agent is None) == (mode is None):
        raise ValueError("choose one policy or baseline")
    env = build_env(cfg)
    metrics, traces = [], []
    for case, wind in bank_cases:
        env.initial = np.asarray(cfg["environment"]["initial_operating_point"], dtype=float).copy()
        env.initial[1] = case["initial_pitch_rad"]
        obs, info = env.reset(seed=42, options=dict(wind_trajectory=wind.values, target_w=case["target_w"]))
        controller = PitchController(env, cfg["baselines"], mode) if mode else None
        errors, max_rates = [], np.zeros(3)
        previous = np.column_stack((info["heading_rad"], info["applied"][:, 1:]))
        for _ in range(env.horizon):
            action = agent.act(obs) if agent else controller.act(obs)
            projected = env.project_action(action)
            if agent and not np.allclose(action[:, ~env.control_mask], projected[:, ~env.control_mask], atol=3e-6, rtol=0):
                raise AssertionError("actor/target reference schedule disagrees with environment")
            obs, _, done, _, info = env.step(action)
            actual = np.column_stack((info["heading_rad"], info["applied"][:, 1:]))
            rate = np.abs(actual - previous).max(axis=0) / env.dt
            if np.any(rate > np.asarray(env.config["rate_limits"]) + 1e-7):
                raise AssertionError("physical actuator rate violation")
            previous = actual; max_rates = np.maximum(max_rates, rate)
            np.testing.assert_allclose(info["applied"][:, 0], wrap_angle(info["heading_rad"] - info["wind"][1]), atol=1e-6, rtol=0)
            np.testing.assert_allclose(info["executed_action"], projected, atol=1e-7, rtol=0)
            errors.append(info["error_w"])
            if capture:
                row = dict(case_id=case["id"], split=case["split"], family=case["family"], target_w=env.target,
                    initial_pitch_rad=case["initial_pitch_rad"], step=info["step"], farm_power_w=info["farm_power_w"],
                    error_w=info["error_w"], wind_m_s=float(info["wind"][0]), direction_rad=float(info["wind"][1]), ti=float(info["wind"][2]))
                for i in range(3):
                    row.update({f"power_{i+1}_w": float(info["power_w"][i]), f"ueff_{i+1}_m_s": float(info["effective_wind_m_s"][i]),
                                f"heading_{i+1}_rad": float(info["heading_rad"][i])})
                    for j, name in enumerate(("gamma", "pitch", "speed")):
                        row[f"{name}_{i+1}"] = float(info["applied"][i, j]); row[f"command_{i+1}_{j}"] = float(info["executed_action"][i, j])
                traces.append(row)
            if done:
                break
        error = np.asarray(errors)
        metrics.append(dict(case_id=case["id"], split=case["split"], family=case["family"], target_w=env.target,
            initial_pitch_rad=case["initial_pitch_rad"], rmse_w=float(np.sqrt(np.mean(error ** 2))),
            tail_rmse_w=float(np.sqrt(np.mean(error[-32:] ** 2))), mae_w=float(np.mean(np.abs(error))),
            mean_shortfall_w=float(np.maximum(-error, 0).mean()), shortfall_duration_s=float(np.sum(error < -.02 * env.target) * env.dt),
            max_heading_rate_rad_s=float(max_rates[0]), max_pitch_rate_rad_s=float(max_rates[1]), max_rotor_accel_rad_s2=float(max_rates[2]),
            final_power_w=float(info["farm_power_w"]), reachability_certified=False))
    return metrics, traces


def sampled_ranges(cfg, bank_cases, path):
    import numpy as np
    from .workflow import build_env
    env = build_env(cfg)
    slope = cfg["environment"]["reference_schedule"]["speed_per_wind_rad_m"]
    rows = []
    for case, wind in bank_cases:
        times = np.linspace(0, env.horizon, 5, dtype=int)
        conditions = wind.values[times]
        n = len(times) * 17
        x = np.empty((n, 12)); x[:, :3] = np.repeat(conditions, 17, axis=0)
        x[:, 3:6] = cfg["environment"]["reference_schedule"]["yaw_offset_rad"]
        x[:, 6:9] = np.tile(np.linspace(env.low[1], env.high[1], 17), len(times))[:, None]
        x[:, 9:12] = env.initial[2]
        residual = 0.
        for _ in range(12):
            y = env.plant.predictor(x)
            reference = np.clip(slope * y[:, 3:], env.low[2], env.high[2])
            residual = float(np.max(np.abs(reference - x[:, 9:12])))
            x[:, 9:12] = reference
            if residual < 1e-6:
                break
        powers = env.plant.predictor(x)[:, :3].sum(1).reshape(len(times), 17)
        for i, t in enumerate(times):
            rows.append(dict(case_id=case["id"], split=case["split"], family=case["family"], step=int(t),
                wind_m_s=float(conditions[i, 0]), target_w=case["target_w"], sampled_min_power_w=float(powers[i].min()),
                sampled_max_power_w=float(powers[i].max()), sampled_path_gap_w=max(0., case["target_w"] - float(powers[i].max())),
                speed_fixed_point_residual_rad_s=residual, global_upper_bound_certified=False))
    write_csv(path, rows)
    return rows


def train_job(root, stage, mask, run_id):
    import numpy as np
    import torch
    import yaml
    from .algorithm import MADDPG
    from .workflow import build_env, make_agent
    from .benchmark import seed_for
    from .stable_workflow import Exploration
    from ..environments.farm_inflow import generate_inflow
    root = Path(root)
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8")); p = saved["protocol"]
    cfg = deepcopy(saved["base_config"]); cfg["environment"]["control_mask"] = mask
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    job = root / f"{stage}_run_{run_id}"
    if (job / "result.json").exists():
        result = json.loads((job / "result.json").read_text(encoding="utf-8"))
        if not all(digest(f) == h for f, h in result["hashes"].items()):
            raise ValueError("completed checkpoint changed")
        return
    env = build_env(cfg)
    validation = cases(root, "validation")
    run_seed = seed_for(42, 712, run_id)
    noise = Exploration(seed_for(42, 713, run_id), p["noise_std"], [10., 3., 5.], env.dt, "white", p["noise_end_fraction"])
    identity = dict(config=cfg, protocol=p, stage=stage, run_id=run_id, bank_sha256=digest(root / "bank/manifest.json"))
    if job.exists():
        segments = sorted(job.glob("segment_*/state.json"))
        if not segments:
            raise ValueError("incomplete worker before first checkpoint; preserve and use a new experiment")
        last = json.loads(segments[-1].read_text(encoding="utf-8"))
        agent, meta = MADDPG.load(last["final"])
        if meta["identity"] != identity or meta["normalization"] != env.normalization():
            raise ValueError("resume identity differs")
        step, episode, history, best, initial = meta["steps"], meta["episodes"], meta["history"], meta["best"], meta["initial"]
        noise.load_state_dict(meta["noise"])
        from .fixed_curriculum import next_segment
        segment = next_segment(job)
    else:
        job.mkdir(); step = episode = 0; history = []; best = initial = None; segment = 0
        agent = make_agent(cfg, env, seed=run_seed)
    out = fresh(job / f"segment_{segment:03d}", dict(seed=42, **identity))
    write_json(out / "normalization.json", env.normalization())
    def snapshot(losses):
        nonlocal best, initial
        rows, _ = rollout(cfg, validation, agent=agent)
        score = float(np.mean([r["rmse_w"] for r in rows]))
        path = (out / f"step_{step:08d}.pth").resolve()
        if initial is None:
            initial = str(path)
        if best is None or score < best["score_w"]:
            best = dict(score_w=score, checkpoint=str(path), step=step, validation=rows)
        item = dict(steps=step, validation_rmse_w=score, worst_validation_rmse_w=max(r["rmse_w"] for r in rows), best_rmse_w=best["score_w"])
        for key in ("actor_loss", "critic_loss", "actor_grad_norm", "critic_grad_norm", "td_abs_mean"):
            item[key] = float(np.mean([v[key] for v in losses])) if losses else 0.
        history.append(item)
        agent.save(path, dict(identity=identity, config=cfg, steps=step, episodes=episode, history=history, best=best,
            initial=initial, noise=noise.state_dict(), normalization=env.normalization()))
        write_csv(out / "metrics.csv", history); write_json(out / "state.json", dict(final=str(path), completed=step == p["steps_per_run"]))
        print(json.dumps(dict(stage=stage, run_id=run_id, **item)), flush=True)
        return str(path)
    final = snapshot([]) if step == 0 else last["final"]
    losses = []
    while step < p["steps_per_run"]:
        family, target, pitch = episode_design(p, run_id, episode)
        inflow = deepcopy(p["inflow"]); inflow["speed"]["scenario"] = family
        trace = generate_inflow(inflow, dt_s=env.dt, horizon=env.horizon, seed=42, split="train", episode=40000 + run_id * 1000 + episode)
        env.initial = np.asarray(cfg["environment"]["initial_operating_point"], dtype=float).copy(); env.initial[1] = pitch
        obs, _ = env.reset(seed=42, options=dict(wind_trajectory=trace.values, target_w=target)); noise.reset()
        for _ in range(env.horizon):
            action = agent.rng.uniform(-1, 1, (3, 3)).astype(np.float32) if step < p["warmup_steps"] else np.clip(agent.act(obs) + noise.sample(step / p["steps_per_run"]), -1, 1)
            action = env.project_action(action).astype(np.float32)
            nxt, reward, done, _, info = env.step(action)
            agent.replay.add(obs, info["executed_action"], reward, nxt, done)
            step += 1
            if step >= p["warmup_steps"] and agent.replay.size >= agent.config.batch_size and step % p["update_every"] == 0:
                losses.append(agent.update())
            obs = nxt
        episode += 1
        if step % p["eval_every"] == 0 or step == p["steps_per_run"]:
            final = snapshot(losses); losses = []
    ratio = history[-1]["validation_rmse_w"] / max(best["score_w"], 1e-9)
    passed = (best["score_w"] < history[0]["validation_rmse_w"] and best["score_w"] <= p["gate"]["mean_validation_rmse_w"]
              and max(r["rmse_w"] for r in best["validation"]) <= p["gate"]["worst_validation_rmse_w"] and ratio <= p["gate"]["max_final_over_selected"])
    result = dict(stage=stage, run_id=run_id, config=cfg, initial=initial, best=best, final=final,
        final_over_best=ratio, passed=bool(passed), steps=step, initial_rmse_w=history[0]["validation_rmse_w"],
        hashes={f: digest(f) for f in set((initial, best["checkpoint"], final))})
    write_json(job / "result.json", result)


def execute(root, *, resume=False):
    import yaml
    root = Path(root).resolve()
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8")); p = saved["protocol"]
    if (root / "test").exists():
        raise ValueError("test already released; no additional training permitted")
    if not all(digest(f) == h for f, h in saved["source_hashes"].items()):
        raise ValueError("pinned source model changed")
    sampled_ranges(saved["base_config"], cases(root, "validation"), root / "validation_sampled_ranges.csv")
    results, gates = [], []
    for stage, mask in STAGES:
        current = []
        for run_id in p["run_ids"]:
            subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "optimization_control.maddpg_wind_farm.random_wind_training",
                            "worker", "--output", str(root), "--stage", stage, "--run-id", str(run_id)], check=True)
            current.append(json.loads((root / f"{stage}_run_{run_id}/result.json").read_text(encoding="utf-8")))
        results.extend(current)
        passed = all(v["passed"] for v in current); gates.append(dict(stage=stage, passed=passed))
        write_csv(root / "metrics.csv", [dict(stage=r["stage"], run_id=r["run_id"], selected_step=r["best"]["step"],
            selected_validation_rmse_w=r["best"]["score_w"], final_over_selected=r["final_over_best"], passed=r["passed"]) for r in results])
        write_json(root / "stage_gates.json", gates)
        if not passed:
            break
    selection = dict(seed=42, results=results, gates=gates, bank_sha256=digest(root / "bank/manifest.json"),
                     hashes={f: h for r in results for f, h in r["hashes"].items()})
    write_json(root / "selection.json", selection)
    test_locked(root)


def test_locked(root):
    import numpy as np
    import yaml
    from .algorithm import MADDPG
    root = Path(root)
    selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    if digest(root / "bank/manifest.json") != selection["bank_sha256"] or not all(digest(f) == h for f, h in selection["hashes"].items()):
        raise ValueError("frozen test identity changed")
    out = fresh(root / "test", dict(seed=42, selection_sha256=digest(root / "selection.json")))
    bank_cases = cases(root, "test", allow_test=True)
    metrics, traces = [], []
    for result in selection["results"]:
        for label, path in (("initial", result["initial"]), ("selected", result["best"]["checkpoint"]), ("final", result["final"])):
            agent, _ = MADDPG.load(path)
            rows, capture = rollout(result["config"], bank_cases, agent=agent, capture=True)
            tags = dict(stage=result["stage"], run_id=result["run_id"], controller=label)
            metrics.extend(dict(**tags, **r) for r in rows); traces.extend(dict(**tags, **r) for r in capture)
        print("Independent test", result["stage"], result["run_id"], flush=True)
    for stage in dict.fromkeys(r["stage"] for r in selection["results"]):
        cfg = next(r["config"] for r in selection["results"] if r["stage"] == stage)
        for mode in ("fixed", "p", "pi"):
            rows, capture = rollout(cfg, bank_cases, mode=mode, capture=True)
            tags = dict(stage=stage, run_id=-1, controller=mode)
            metrics.extend(dict(**tags, **r) for r in rows); traces.extend(dict(**tags, **r) for r in capture)
    write_csv(out / "metrics.csv", metrics); write_csv(out / "trajectories.csv", traces)
    sampled_ranges(saved["base_config"], bank_cases, out / "sampled_ranges.csv")
    aggregate = []
    for stage in dict.fromkeys(r["stage"] for r in selection["results"]):
        for label in ("initial", "selected", "final", "fixed", "p", "pi"):
            part = [r for r in metrics if r["stage"] == stage and r["controller"] == label and r["family"] in FAMILIES]
            per_run = [float(np.mean([r["rmse_w"] for r in part if r["run_id"] == i])) for i in sorted(set(r["run_id"] for r in part))]
            aggregate.append(dict(stage=stage, controller=label, runs=len(per_run), mean_rmse_w=float(np.mean(per_run)),
                                  std_across_runs_w=float(np.std(per_run, ddof=1)) if len(per_run) > 1 else 0.))
    write_csv(out / "aggregate.csv", aggregate)
    audit_replays(root, selection)
    if not all(digest(f) == h for f, h in saved["source_hashes"].items()):
        raise ValueError("source changed during training")
    summary = dict(seed=42, completed=True, physical_validation=False, gates=selection["gates"],
        training_steps=sum(r["steps"] for r in selection["results"]), jobs=len(selection["results"]), aggregate=aggregate,
        test_used_for_selection=False, source_files_unchanged=True, test_rows=len(metrics), trace_rows=len(traces),
        reachability_certified=False, comparison="shared actuator and background rules; pitch stage has identical yaw/speed schedules for RL and P/PI")
    write_json(root / "summary.txt", summary); write_json(out / "summary.txt", summary)
    plot(root)
    print(json.dumps(summary, indent=2), flush=True)


def audit_replays(root, selection):
    import numpy as np
    from .algorithm import MADDPG
    rows = []
    for result in selection["results"]:
        path = result["final"]; before = digest(path)
        agent, meta = MADDPG.load(path); data = agent.replay.state_dict()["data"]
        n = len(data["obs"]); cfg = meta["config"]["environment"]
        # Commands in next observation must be the exact references stored in replay.
        np.testing.assert_array_equal(data["actions"], data["next_obs"][:, :, 5:8])
        if agent.config.speed_reference_schedule:
            scale, slope, low, high = agent.config.speed_reference_schedule
            expected = np.clip(2 * (data["obs"][:, :, 1] * scale * slope - low) / (high - low) - 1, -1, 1)
            np.testing.assert_allclose(data["actions"][:, :, 2], expected, atol=4e-6, rtol=0)
        terminal = (np.arange(n) + 1) % cfg["horizon"] == 0
        np.testing.assert_array_equal(data["terminated"][:, 0], terminal)
        np.testing.assert_allclose(data["obs"][:, :, 8], data["next_obs"][:, :, 8], atol=1e-7, rtol=0)
        width = np.asarray(cfg["action_high"]) - cfg["action_low"]
        old_gamma = (data["obs"][:, :, 2] + 1) * width[0] / 2 + cfg["action_low"][0]
        new_gamma = (data["next_obs"][:, :, 2] + 1) * width[0] / 2 + cfg["action_low"][0]
        old_theta = np.arctan2(data["obs"][:, 0, 11], data["obs"][:, 0, 12])
        new_theta = np.arctan2(data["next_obs"][:, 0, 11], data["next_obs"][:, 0, 12])
        heading_delta = (new_gamma - old_gamma + (new_theta - old_theta)[:, None] + np.pi) % (2 * np.pi) - np.pi
        other_delta = (data["next_obs"][:, :, 3:5] - data["obs"][:, :, 3:5]) * width[1:] / 2
        delta = np.concatenate((heading_delta[:, :, None], other_delta), axis=-1)
        max_steps = np.max(np.abs(delta), axis=(0, 1))
        if np.any(max_steps > np.asarray(cfg["rate_limits"]) * cfg["dt_s"] + 1e-6):
            raise AssertionError("physical training replay actuator rate violation")
        if np.any(np.abs(data["next_obs"][:, :, 3:5]) > 1 + 1e-6):
            raise AssertionError("physical training replay pitch/speed bounds violation")
        cost = np.mean((data["actions"] - data["obs"][:, :, 5:8]) ** 2, axis=(1, 2))
        expected_reward = cfg["reward_scale"] * (-data["next_obs"][:, 0, 9] ** 2 - cfg["action_change_weight"] * cost)
        np.testing.assert_allclose(data["rewards"], np.repeat(expected_reward[:, None], 3, axis=1), atol=5e-6, rtol=4e-6)
        assert n == result["steps"] and digest(path) == before
        rows.append(dict(stage=result["stage"], run_id=result["run_id"], transitions=n, terminal_transitions=int(terminal.sum()),
            dynamic_speed_schedule_verified=bool(agent.config.speed_reference_schedule), reward_verified=True,
            max_heading_step_rad=float(max_steps[0]), max_pitch_step_rad=float(max_steps[1]),
            max_speed_step_rad_s=float(max_steps[2]), checkpoint_unchanged=True))
    write_csv(Path(root) / "replay_audit.csv", rows)


def plot(root):
    import csv
    import numpy as np
    import yaml
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    root = Path(root); selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for result in selection["results"]:
        with (Path(result["final"]).parent / "metrics.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        axes[0].plot([int(r["steps"]) for r in rows], [float(r["validation_rmse_w"]) / 1000 for r in rows], label=f"{result['stage']} / {result['run_id']}")
    with (root / "test/aggregate.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for stage in dict.fromkeys(r["stage"] for r in rows):
        part = [r for r in rows if r["stage"] == stage]
        axes[1].errorbar([r["controller"] for r in part], [float(r["mean_rmse_w"]) / 1000 for r in part],
            yerr=[float(r["std_across_runs_w"]) / 1000 for r in part], fmt="o", capsize=4, label=stage + " mean +/- run SD")
    protocol = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))["protocol"]
    axes[0].axhline(protocol["gate"]["mean_validation_rmse_w"] / 1000, color="k", linestyle="--", label="Mean validation gate")
    axes[0].set(xlabel="Training steps", ylabel="Validation RMSE [kW]")
    axes[1].set(xlabel="Frozen test controller", ylabel="Routine test RMSE [kW]")
    for ax in axes:
        ax.legend(); ax.grid(alpha=.2)
    fig.suptitle("Random entrance training | synthetic PINN | validation-only selection")
    fig.tight_layout(); fig.savefig(root / "training_and_test.png", dpi=140); plt.close(fig)
    chosen = "test_gust_1_pitch0.025"
    display = {name: [] for name in ("selected", "p", "pi")}
    with (root / "test/trajectories.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["case_id"] == chosen and row["stage"] == "pitch" and ((row["controller"] == "selected" and int(row["run_id"]) == 0)
                    or (row["controller"] in ("p", "pi") and int(row["run_id"]) == -1)):
                display[row["controller"]].append(row)
    if not all(display.values()):
        return
    fig, axes = plt.subplots(5, 1, figsize=(11, 13), sharex=True)
    wind = display["pi"]; t = [int(r["step"]) for r in wind]
    theta_raw = np.array([float(r["direction_rad"]) for r in wind])
    theta = np.unwrap((theta_raw + np.pi) % (2 * np.pi) - np.pi)
    axes[0].plot(t, [float(r["wind_m_s"]) for r in wind], label="Generated entrance")
    axes[0].set_ylabel("Wind [m/s]")
    axes[0].set_title(f"Gust test | target {float(wind[0]['target_w'])/1e6:g} MW | background TI {100*float(wind[0]['ti']):g}%")
    axes[1].plot(t, np.rad2deg(theta), "k--", label="Wind flow-to direction")
    for name, part in display.items():
        heading = np.array([float(r["heading_1_rad"]) for r in part])
        aligned_heading = theta + (heading - theta_raw + np.pi) % (2 * np.pi) - np.pi
        axes[1].plot(t, np.rad2deg(aligned_heading), label=name + " T1 nacelle")
        axes[2].plot(t, [float(r["farm_power_w"]) / 1e6 for r in part], label=name)
        axes[3].plot(t, np.rad2deg([float(r["pitch_1"]) for r in part]), label=name)
        axes[4].plot(t, [float(r["speed_1"]) for r in part], label=name)
    axes[1].set_ylabel("Heading [deg]")
    axes[2].axhline(float(wind[0]["target_w"]) / 1e6, color="k", linestyle="--", label="Target")
    axes[2].set_ylabel("Farm power [MW]")
    axes[3].set_ylabel("T1 pitch [deg]"); axes[4].set_ylabel("T1 speed [rad/s]")
    axes[4].set_xlabel("Control time [s]; quasi-steady synthetic plant")
    for ax in axes:
        ax.legend(fontsize=8, loc="best"); ax.grid(alpha=.2)
    fig.suptitle("Shared random entrance and applied actuators | synthetic PINN")
    fig.tight_layout(); fig.savefig(root / "random_wind_replay.png", dpi=140); plt.close(fig)


def replay(root, output, stage, run_id):
    import csv
    from .algorithm import MADDPG
    root = Path(root)
    selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    matches = [r for r in selection["results"] if r["stage"] == stage and r["run_id"] == run_id]
    if len(matches) != 1 or not (root / "test/trajectories.csv").exists():
        raise ValueError("select one completed, frozen tested policy")
    result = matches[0]
    if digest(root / "bank/manifest.json") != selection["bank_sha256"] or not all(digest(f) == h for f, h in result["hashes"].items()):
        raise ValueError("frozen replay identity changed")
    out = fresh(output, dict(seed=42, source_experiment=str(root.resolve()), stage=stage, run_id=run_id,
                             checkpoint=result["best"]["checkpoint"], purpose="frozen_replay_not_new_training"))
    agent, _ = MADDPG.load(result["best"]["checkpoint"])
    bank_cases = cases(root, "test", allow_test=True)
    actual, metrics = [], []
    for mode in ("selected", "fixed", "p", "pi"):
        rows, traces = rollout(result["config"], bank_cases, agent=agent if mode == "selected" else None,
                               mode=None if mode == "selected" else mode, capture=True)
        tags = dict(stage=stage, run_id=run_id if mode == "selected" else -1, controller=mode)
        metrics.extend(dict(**tags, **r) for r in rows); actual.extend(dict(**tags, **r) for r in traces)
    text_fields = {"case_id", "split", "family", "stage", "controller"}
    expected = []
    with (root / "test/trajectories.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["stage"] == stage and ((row["controller"] == "selected" and int(row["run_id"]) == run_id)
                    or (row["controller"] in ("fixed", "p", "pi") and int(row["run_id"]) == -1)):
                expected.append({k: v if k in text_fields else float(v) for k, v in row.items()})
    if actual != expected:
        raise AssertionError("new-process random-wind replay differs from frozen test")
    if not all(digest(f) == h for f, h in result["hashes"].items()):
        raise ValueError("replay modified checkpoint")
    write_csv(out / "metrics.csv", metrics); write_csv(out / "trajectories.csv", actual)
    write_json(out / "summary.txt", dict(seed=42, full_trace_equal=True, rows=len(actual), metric_rows=len(metrics),
        checkpoint_unchanged=True, new_training=False, physical_validation=False, stage=stage, run_id=run_id))
    print("Exact random-wind replay", len(actual), "rows", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("prepare", "run", "worker", "all", "replay", "plot"))
    ap.add_argument("--protocol", default=str(DEFAULT)); ap.add_argument("--output", required=True)
    ap.add_argument("--stage", choices=[s for s, _ in STAGES]); ap.add_argument("--run-id", type=int)
    ap.add_argument("--replay-output")
    args = ap.parse_args(); p = read_protocol(args.protocol)
    activate_runtime(p["runtime_site_packages"]); sys.dont_write_bytecode = True
    root = Path(args.output)
    if args.command in ("prepare", "all"):
        root = prepare(p, root)
    elif not root.exists():
        ap.error("prepare the experiment first")
    if args.command == "worker":
        train_job(root, args.stage, dict(STAGES)[args.stage], args.run_id)
    if args.command in ("run", "all"):
        execute(root)
    if args.command == "plot":
        plot(root)
    if args.command == "replay":
        if not args.replay_output:
            ap.error("replay requires --replay-output pointing to a new directory")
        replay(root, args.replay_output, args.stage or "pitch", args.run_id if args.run_id is not None else 0)


if __name__ == "__main__":
    main()
