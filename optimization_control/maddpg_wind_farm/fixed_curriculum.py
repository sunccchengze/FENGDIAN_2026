"""Gated fixed-condition control learning; activate local TF before NumPy."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from copy import deepcopy
import json
from pathlib import Path

from .fixed_pinn_demo import activate_runtime, digest

DEFAULT = Path(__file__).parent / "configs/fixed_curriculum.yaml"
STAGES = (("single_pitch", [0, 1, 0]), ("multi_pitch", [0, 1, 0]),
          ("multi_pitch_speed", [0, 1, 1]), ("multi_all", [1, 1, 1]))


def next_segment(directory):
    indices = [int(p.name.rsplit("_", 1)[1]) for p in Path(directory).glob("segment_*") if p.is_dir()]
    return max(indices, default=-1) + 1


def read_protocol(path):
    import yaml
    p = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if p["version"] != "fixed_pinn_curriculum_v1" or p["seed"] != 42:
        raise ValueError("fixed protocol and master seed 42 required")
    if p["selection_rule"] != "lowest_validation_mean_rmse_including_initial" or p["test_rule"] != "freeze_completed_stages_and_baselines_before_test":
        raise ValueError("unsupported selection boundary")
    for key in ("single_steps", "multi_steps", "expansion_steps", "eval_every"):
        if p[key] <= 0 or p[key] % p["horizon"]:
            raise ValueError("budgets must end at complete episodes")
    if len(set(p["run_ids"])) != len(p["run_ids"]) or len(p["run_ids"]) < 3:
        raise ValueError("three independent multi-target runs required")
    stages = p.get("stages", [s for s, _ in STAGES])
    if not stages or stages != [s for s, _ in STAGES if s in stages]:
        raise ValueError("stages must be unique and in declared order")
    training = set(p["multi_training_targets_w"])
    validation, test = set(p["validation_targets_w"]), set(p["test_targets_w"])
    if training & validation or training & test or validation & test:
        raise ValueError("multi-target training/validation/test targets must be disjoint")
    if any(not 0 < t <= 15e6 for t in training | validation | test | set(p["single_targets_w"])):
        raise ValueError("invalid power target")
    return p


def gate_rows(rows, initial_score, rule, *, multi):
    """Only validation results may decide curriculum advancement."""
    import numpy as np
    if not rows or any(r["split"] != "validation" for r in rows):
        raise ValueError("curriculum gates accept validation only")
    score = float(np.mean([r["rmse_w"] for r in rows]))
    tail = max(r["tail_rmse_w"] for r in rows)
    if not np.all(np.isfinite([score, tail, initial_score])):
        raise ValueError("nonfinite validation metric")
    response = 1.0
    if multi:
        ordered = sorted(rows, key=lambda r: r["target_w"])
        response = (ordered[-1]["final_power_w"] - ordered[0]["final_power_w"]) / (ordered[-1]["target_w"] - ordered[0]["target_w"])
    improved = score < initial_score
    return dict(passed=bool(improved and tail <= rule["max_tail_rmse_w"] and response >= rule["min_endpoint_response_fraction"]),
                improved=improved, worst_tail_rmse_w=float(tail), response_fraction=float(response), mean_rmse_w=score)


def evaluate(env, agent, targets, *, split, pitches, mode=None, capture=False):
    import numpy as np
    import torch
    from .controllers import PitchController
    rows, traces = [], []
    original = env.initial.copy()
    try:
        for target in targets:
            for pitch in pitches:
                env.initial = original.copy()
                env.initial[1] = pitch
                obs, info = env.reset(seed=42, options={"target_w": target})
                baseline = PitchController(env, env.study_baselines, mode) if mode else None
                if agent:
                    with torch.no_grad():
                        x = torch.tensor(np.concatenate((obs.ravel(), agent.act(obs).ravel())), dtype=torch.float32)[None, :]
                        q = float(np.mean([critic(x).item() for critic in agent.critics]))
                else:
                    q = 0.
                errors, rewards, saturation = [], [], []
                motion = np.zeros(3)
                previous = info["applied"].copy()
                for step in range(env.horizon):
                    action = agent.act(obs) if baseline is None else baseline.act(obs)
                    obs, reward, done, _, info = env.step(action)
                    delta = info["applied"] - previous
                    if np.any(np.abs(delta) > np.asarray(env.config["rate_limits"])*env.dt + 1e-7):
                        raise AssertionError("actuator rate violation")
                    if np.any(np.abs(delta[:, ~env.control_mask]) > 1e-7):
                        raise AssertionError("disabled operating-point channel moved")
                    if not np.allclose(info["wind"], [9., 0., .1], rtol=0, atol=1e-7):
                        raise AssertionError("fixed model wind changed")
                    previous = info["applied"].copy()
                    motion += np.abs(delta).sum(axis=0)
                    errors.append(info["error_w"])
                    rewards.append(float(reward[0]))
                    saturation.append(info["saturation_fraction"])
                    if capture:
                        row = dict(target_w=target, initial_pitch_rad=pitch, step=step+1,
                                   power_w=info["farm_power_w"], error_w=info["error_w"])
                        for i in range(3):
                            for j, field in enumerate(("yaw", "pitch", "speed")):
                                row[f"{field}_{i+1}"] = float(info["applied"][i, j])
                        traces.append(row)
                    if done:
                        break
                error = np.asarray(errors)
                gamma = agent.config.gamma if agent else env.study_gamma
                realized = float(np.dot(np.power(gamma, np.arange(len(rewards))), rewards))
                rows.append(dict(split=split, target_w=target, initial_pitch_rad=pitch,
                    rmse_w=float(np.sqrt(np.mean(error**2))), tail_rmse_w=float(np.sqrt(np.mean(error[-32:]**2))),
                    final_power_w=info["farm_power_w"], max_abs_error_w=float(np.max(np.abs(error))),
                    q_initial=q, discounted_return=realized, q_return_gap=q-realized if agent else 0.,
                    yaw_travel_rad=motion[0], pitch_travel_rad=motion[1], speed_total_variation_rad_s=motion[2],
                    saturation_fraction=float(np.mean(saturation))))
    finally:
        env.initial = original
    return rows, traces


def attach_settings(env, cfg):
    env.study_baselines = cfg["baselines"]
    env.study_gamma = cfg["algorithm"]["gamma"]
    return env


def train_job(p, base, stage, mask, target, run_id, directory):
    """Spawn-safe worker; each job owns its replay, runtime, RNG and snapshots."""
    activate_runtime(p["runtime_site_packages"])
    import numpy as np
    import torch
    from .algorithm import MADDPG, AlgorithmConfig
    from .benchmark import seed_for
    from .stable_workflow import Exploration
    from .workflow import build_env, fresh_output, write_csv
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    directory = Path(directory)
    if (directory / "result.json").exists():
        saved = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        if any(digest(path) != h for path, h in saved["hashes"].items()):
            raise ValueError("completed checkpoint changed")
        return saved
    cfg = deepcopy(base)
    cfg["environment"].update(control_mask=mask, horizon=p["horizon"])
    cfg["algorithm"]["capacity"] = 32768
    env = attach_settings(build_env(cfg), cfg)
    steps = p["single_steps"] if stage == "single_pitch" else p["multi_steps"] if stage == "multi_pitch" else p["expansion_steps"]
    targets = [target] if stage == "single_pitch" else p["multi_training_targets_w"]
    validation_targets = [target] if stage == "single_pitch" else p["validation_targets_w"]
    identity = dict(seed=42, config=cfg, protocol=p, stage=stage, mask=mask, run_id=run_id,
                    single_target_w=target, planned_steps=steps)
    noise = Exploration(seed_for(42, 420, run_id), p["noise_std"], p["noise_correlation_s"], env.dt, p["noise_kind"], p["noise_end_fraction"])
    segments = sorted(directory.glob("segment_*/summary.txt"))
    if segments:
        last = json.loads(segments[-1].read_text(encoding="utf-8"))
        agent, meta = MADDPG.load(last["final"])
        if meta["identity"] != identity:
            raise ValueError("checkpoint resume identity mismatch")
        step, episode = meta["steps"], meta["episodes"]
        history, case_history, best, initial_path = meta["history"], meta["case_history"], meta["best"], meta["initial"]
        noise.load_state_dict(meta["noise"])
    else:
        fixed = tuple(float(v) for v in env.normalize_commands(np.tile(env.initial, (3, 1)))[0])
        a = dict(cfg["algorithm"], seed=seed_for(42, 410, run_id), action_mask=tuple(mask), fixed_action=fixed,
                 actor_initial_action=fixed)
        agent = MADDPG(AlgorithmConfig(**a))
        step = episode = 0
        history, case_history, best, initial_path = [], [], None, None
    segment = next_segment(directory)
    directory.mkdir(parents=True, exist_ok=True)
    out = fresh_output(directory / f"segment_{segment:03d}", identity)
    (out / "normalization.json").write_text(json.dumps(env.normalization(), indent=2), encoding="utf-8")

    def snapshot(losses):
        nonlocal best, initial_path
        rows, _ = evaluate(env, agent, validation_targets, split="validation", pitches=[.04])
        score = float(np.mean([r["rmse_w"] for r in rows]))
        path = (out / f"step_{step:08d}.pth").resolve()
        if initial_path is None:
            initial_path = str(path)
        if best is None or score < best["score_w"]:
            best = dict(score_w=score, step=step, checkpoint=str(path), validation=rows)
        result = dict(steps=step, validation_rmse_w=score, worst_tail_rmse_w=max(r["tail_rmse_w"] for r in rows),
                      best_rmse_w=best["score_w"], q_return_gap_abs=float(np.mean([abs(r["q_return_gap"]) for r in rows])))
        for key in ("actor_loss", "critic_loss", "actor_grad_norm", "critic_grad_norm", "td_abs_mean"):
            result[key] = float(np.mean([l[key] for l in losses])) if losses else 0.
        history.append(result)
        case_history.extend(dict(steps=step, **r) for r in rows)
        meta = dict(identity=identity, config=cfg, normalization=env.normalization(), steps=step, episodes=episode,
                    history=history, case_history=case_history, best=best, initial=initial_path, noise=noise.state_dict())
        agent.save(path, meta)
        write_csv(out / "metrics.csv", history)
        write_csv(out / "validation.csv", case_history)
        (out / "summary.txt").write_text(json.dumps(dict(best=best, final=str(path), completed=step == steps), indent=2), encoding="utf-8")
        print(json.dumps(dict(job=directory.name, **result)), flush=True)
        return str(path)

    with (directory / f"segment_{segment:03d}.log").open("w", encoding="utf-8") as log, redirect_stdout(log):
        if step == 0:
            final = snapshot([])
        elif step == steps:
            final = snapshot([])
        losses = []
        while step < steps:
            obs, _ = env.reset(seed=42, options={"target_w": targets[episode % len(targets)]})
            noise.reset()
            for _ in range(env.horizon):
                action = agent.rng.uniform(-1, 1, (3, 3)).astype(np.float32) if step < p["warmup_steps"] else np.clip(agent.act(obs) + noise.sample(step/steps), -1, 1)
                action = env.project_action(action).astype(np.float32)
                nxt, reward, done, _, info = env.step(action)
                agent.replay.add(obs, info["executed_action"], reward, nxt, done)
                step += 1
                if step >= p["warmup_steps"] and agent.replay.size >= agent.config.batch_size and step % p["update_every"] == 0:
                    losses.append(agent.update())
                obs = nxt
            episode += 1
            if step % p["eval_every"] == 0 or step == steps:
                final = snapshot(losses)
                losses = []
    gate = gate_rows(best["validation"], history[0]["validation_rmse_w"], p["gate"], multi=stage != "single_pitch")
    result = dict(stage=stage, run_id=run_id, target_w=target, config=cfg, best=best, final=final, initial=initial_path,
                  gate=gate, final_rmse_w=history[-1]["validation_rmse_w"],
                  final_over_best=history[-1]["validation_rmse_w"]/max(best["score_w"], 1e-9),
                  hashes={path: digest(path) for path in set([best["checkpoint"], final, initial_path])})
    (directory / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def locked_test(root, p, results):
    import numpy as np
    from .algorithm import MADDPG
    from .workflow import build_env, fresh_output, write_csv
    if (root / "test").exists():
        raise ValueError("test already released; no retraining or overwrite permitted")
    selection = dict(seed=42, protocol_sha256=digest(root/"config.yaml"), results=results,
                     hashes={path: h for r in results for path, h in r["hashes"].items()})
    (root / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    for path, h in selection["hashes"].items():
        if digest(path) != h:
            raise ValueError("frozen model changed")
    out = fresh_output(root / "test", dict(seed=42, selection_sha256=digest(root / "selection.json")))
    metrics, traces = [], []
    for r in results:
        cfg = r["config"]
        env = attach_settings(build_env(cfg), cfg)
        targets = [r["target_w"]] if r["stage"] == "single_pitch" else p["test_targets_w"]
        for label, path in (("initial", r["initial"]), ("selected", r["best"]["checkpoint"]), ("final", r["final"])):
            agent, _ = MADDPG.load(path)
            rows, trace = evaluate(env, agent, targets, split="test", pitches=p["test_initial_pitch_rad"], capture=True)
            tags = dict(stage=r["stage"], run_id=r["run_id"], single_target_w=r["target_w"], controller=label, comparison="same_permissions")
            metrics.extend(dict(**tags, **row) for row in rows)
            traces.extend(dict(**tags, **row) for row in trace)
        for mode in ("fixed", "p", "pi"):
            rows, trace = evaluate(env, None, targets, split="test", pitches=p["test_initial_pitch_rad"], mode=mode, capture=True)
            tags = dict(stage=r["stage"], run_id=r["run_id"], single_target_w=r["target_w"], controller=mode, comparison="same_permissions")
            metrics.extend(dict(**tags, **row) for row in rows)
            traces.extend(dict(**tags, **row) for row in trace)
        if cfg["environment"]["control_mask"] != [1, 1, 1]:
            full = deepcopy(cfg)
            full["environment"]["control_mask"] = [1, 1, 1]
            full_env = attach_settings(build_env(full), full)
            for mode in ("p", "pi"):
                rows, _ = evaluate(full_env, None, targets, split="test", pitches=p["test_initial_pitch_rad"], mode=mode)
                metrics.extend(dict(stage=r["stage"], run_id=r["run_id"], single_target_w=r["target_w"], controller=mode,
                                    comparison="complete_traditional_scheme", **row) for row in rows)
        print(f"Frozen test complete: {r['stage']} / run {r['run_id']} / target {r['target_w']}", flush=True)
    write_csv(out / "metrics.csv", metrics)
    write_csv(out / "trajectories.csv", traces)
    groups = []
    for stage, _ in STAGES:
        for comparison in ("same_permissions", "complete_traditional_scheme"):
            for label in ("initial", "selected", "final", "fixed", "p", "pi"):
                part = [r for r in metrics if r["stage"] == stage and r["controller"] == label and r["comparison"] == comparison]
                if not part:
                    continue
                runs = sorted(set(r["run_id"] for r in part))
                means = [float(np.mean([r["rmse_w"] for r in part if r["run_id"] == i])) for i in runs]
                groups.append(dict(stage=stage, comparison=comparison, controller=label, runs=len(runs),
                    mean_rmse_w=float(np.mean(means)), std_rmse_w=float(np.std(means, ddof=1)) if len(runs)>1 else 0.,
                    worst_tail_rmse_w=max(r["tail_rmse_w"] for r in part),
                    mean_q_return_gap_abs=float(np.mean([abs(r["q_return_gap"]) for r in part]))))
    write_csv(out / "aggregate.csv", groups)
    (out / "summary.txt").write_text(json.dumps(dict(test_used_for_selection=False, aggregate=groups,
        scope="fixed synthetic network only; single-target test changes initial state, multi-target test also changes target"), indent=2), encoding="utf-8")
    return groups


def execute(p, output, *, resume=False):
    import yaml
    from .workflow import fresh_output, write_csv
    source = Path(p["source_experiment"]).resolve()
    base = yaml.safe_load((source / "training/config.yaml").read_text(encoding="utf-8"))
    if base["plant"]["source"] != "teammate_backbone_synthetic_demo" or base["environment"]["wind_noise_std_m_s"] != 0:
        raise ValueError("requires the saved fixed synthetic PINN environment")
    protected = json.loads((source / "data/metadata.json").read_text(encoding="utf-8"))["source_hashes"]
    protected[str(source / "model/trained.keras")] = digest(source / "model/trained.keras")
    saved = dict(seed=42, protocol=p, base_config=base, source_hashes=protected)
    root = Path(output)
    if resume:
        if yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8")) != saved or (root / "test").exists():
            raise ValueError("resume identity changed or test already released")
    else:
        root = fresh_output(root, saved)
    if not all(digest(path) == h for path, h in protected.items()):
        raise ValueError("source model/team manifest changed")
    (root / "summary.txt").write_text("status=running; test remains locked\n", encoding="utf-8")
    results, gates = [], []
    planned_stages = p.get("stages", [s for s, _ in STAGES])
    for stage, mask in STAGES:
        if stage not in planned_stages:
            continue
        jobs = [(target, 0, f"{stage}_{int(target)}w") for target in p["single_targets_w"]] if stage == "single_pitch" else [(None, run_id, f"{stage}_run_{run_id}") for run_id in p["run_ids"]]
        stage_results = []
        with ProcessPoolExecutor(max_workers=p["workers"]) as pool:
            pending = {pool.submit(train_job, p, base, stage, mask, target, run_id, str(root/name)): name for target, run_id, name in jobs}
            for future in as_completed(pending):
                r = future.result()
                stage_results.append(r)
                print(json.dumps(dict(completed=pending[future], gate=r["gate"])), flush=True)
        stage_results.sort(key=lambda r: (r["target_w"] or 0, r["run_id"]))
        results.extend(stage_results)
        passed = all(r["gate"]["passed"] for r in stage_results)
        gates.append(dict(stage=stage, passed=passed, jobs=len(stage_results)))
        write_csv(root / "metrics.csv", [dict(stage=r["stage"], run_id=r["run_id"], target_w=r["target_w"],
            selected_step=r["best"]["step"], selected_rmse_w=r["best"]["score_w"], final_rmse_w=r["final_rmse_w"],
            final_over_best=r["final_over_best"], gate_passed=r["gate"]["passed"], worst_tail_rmse_w=r["gate"]["worst_tail_rmse_w"],
            response_fraction=r["gate"]["response_fraction"]) for r in results])
        (root / "stage_gates.json").write_text(json.dumps(gates, indent=2), encoding="utf-8")
        print(json.dumps(dict(stage_gate=stage, passed=passed)), flush=True)
        if not passed:
            break
    groups = locked_test(root, p, results)
    unchanged = all(digest(path) == h for path, h in protected.items())
    if not unchanged:
        raise AssertionError("source files changed during curriculum")
    summary = dict(seed=42, gates=gates, planned_stages=planned_stages, stages_completed=len(gates), all_stages_passed=len(gates)==len(planned_stages) and all(g["passed"] for g in gates),
                   source_files_unchanged=unchanged, test_used_for_selection=False, aggregate=groups,
                   final_stable_runs=sum(r["final_over_best"]<=p["gate"]["max_final_over_best_validation_ratio"] for r in results), jobs=len(results))
    (root / "summary.txt").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot_results(root)
    print(json.dumps(summary, indent=2), flush=True)


def plot_results(root):
    """Plot saved metrics only; does not run models or release a test set."""
    import csv
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    root = Path(root)
    selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    with (root / "test/metrics.csv").open(encoding="utf-8") as stream:
        test = list(csv.DictReader(stream))
    stages = list(dict.fromkeys(r["stage"] for r in selection["results"]))
    fig, axes = plt.subplots(len(stages), 2, figsize=(12, 4*len(stages)), squeeze=False)
    for index, stage in enumerate(stages):
        jobs = [r for r in selection["results"] if r["stage"] == stage]
        for r in jobs:
            with (Path(r["final"]).parent / "metrics.csv").open(encoding="utf-8") as stream:
                history = list(csv.DictReader(stream))
            label = f"Target {r['target_w']/1e6:g} MW" if stage == "single_pitch" else f"Run {r['run_id']}"
            axes[index, 0].plot([int(row["steps"]) for row in history], [float(row["validation_rmse_w"])/1000 for row in history], label=label)
        axes[index, 0].set(xlabel="Training steps", ylabel="Validation full RMSE [kW]", title=stage)
        part = [r for r in test if r["stage"] == stage and r["comparison"] == "same_permissions"]
        for label in ("selected", "final", "p", "pi"):
            rows = [r for r in part if r["controller"] == label]
            targets = sorted(set(float(r["target_w"]) for r in rows))
            means = [np.mean([float(r["final_power_w"]) for r in rows if float(r["target_w"]) == target])/1e6 for target in targets]
            axes[index, 1].plot(np.array(targets)/1e6, means, marker="o", label=label)
        axes[index, 1].plot(np.array(targets)/1e6, np.array(targets)/1e6, "k--", label="Target")
        axes[index, 1].set(xlabel="Test target [MW]", ylabel="Final predicted power [MW]",
                          title="Test response | mean over initial states and runs")
        for ax in axes[index]:
            ax.legend()
            ax.grid(alpha=.25)
    fig.suptitle("Gated control learning | fixed synthetic PINN | validation selects, test reports")
    fig.tight_layout()
    fig.savefig(root / "curriculum_results.png", dpi=150)
    plt.close(fig)


def audit_replay(root):
    """Audit actual saved transitions; no training or PINN modification."""
    import numpy as np
    from .algorithm import MADDPG
    from .workflow import fresh_output, write_csv
    root = Path(root)
    selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    out = fresh_output(root / "replay_audit", dict(seed=42, selection_sha256=digest(root / "selection.json")))
    rows = []
    for r in selection["results"]:
        path = r["final"]
        before = digest(path)
        agent, meta = MADDPG.load(path)
        cfg = meta["config"]["environment"]
        n = agent.replay.size
        data = {k: v[:n] for k, v in agent.replay.data.items()}
        mask = np.asarray(cfg["control_mask"], dtype=bool)
        width = np.asarray(cfg["action_high"])-cfg["action_low"]
        delta = (data["next_obs"][:, :, 2:5]-data["obs"][:, :, 2:5])*width/2
        if np.any(np.abs(delta) > np.asarray(cfg["rate_limits"])*cfg["dt_s"]+1e-7):
            raise AssertionError("saved replay actuator rate violation")
        if np.any(np.abs(delta[:, :, ~mask]) > 1e-7):
            raise AssertionError("disabled replay channel moved")
        if not np.allclose(data["actions"][:, :, ~mask], np.asarray(agent.config.fixed_action)[~mask], rtol=0, atol=1e-7):
            raise AssertionError("disabled replay action varied")
        for key in ("obs", "next_obs"):
            if not np.allclose(data[key][:, :, 10:14], [.36, 0., 1., .1], rtol=0, atol=1e-7):
                raise AssertionError("replay fixed wind mismatch")
        terminal = (np.arange(n)+1) % cfg["horizon"] == 0
        np.testing.assert_array_equal(data["terminated"][:, 0], terminal)
        if meta["steps"] != n:
            raise AssertionError("unexpected replay rollover or missing transitions")
        action_cost = np.mean((data["actions"]-data["obs"][:, :, 5:8])**2, axis=(1, 2))
        expected = cfg["reward_scale"]*(-data["next_obs"][:, 0, 9]**2-cfg["action_change_weight"]*action_cost)
        np.testing.assert_allclose(data["rewards"], np.repeat(expected[:, None], 3, axis=1), rtol=3e-6, atol=5e-6)
        assert digest(path) == before
        rows.append(dict(stage=r["stage"], run_id=r["run_id"], target_w=r["target_w"], transitions=n,
            terminal_transitions=int(terminal.sum()), max_yaw_step_rad=float(np.abs(delta[:, :, 0]).max()),
            max_pitch_step_rad=float(np.abs(delta[:, :, 1]).max()), max_speed_step_rad_s=float(np.abs(delta[:, :, 2]).max()),
            max_reward_reconstruction_error=float(np.abs(data["rewards"][:, 0]-expected).max()), checkpoint_unchanged=True))
    write_csv(out / "metrics.csv", rows)
    summary = dict(seed=42, jobs=len(rows), transitions=sum(r["transitions"] for r in rows),
                   checks="fixed wind, disabled channels, physical rates, terminal masks, cooperative reward, unchanged checkpoint")
    (out / "summary.txt").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default=str(DEFAULT))
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--plot-only", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    if args.plot_only:
        plot_results(args.output)
        return
    p = read_protocol(args.protocol)
    activate_runtime(p["runtime_site_packages"])
    if args.audit_only:
        audit_replay(args.output)
        return
    execute(p, args.output, resume=args.resume)


if __name__ == "__main__":
    main()
