"""Audit frozen residual checkpoints, physical replay, recovery and held-out CSV."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import csv
import hashlib
import io
import json
from pathlib import Path

from .fixed_pinn_demo import activate_runtime, digest
from .progressive_random_control import verify_hashes
from . import random_wind_training as shared


def recovery_fork(root, p, result):
    """Two disposable identical forks; no experiment checkpoint is changed."""
    import numpy as np
    import torch
    from .residual_algorithm import ResidualMADDPG
    from .residual_random_control import scales, STAGES
    from .stable_workflow import Exploration
    from .benchmark import seed_for
    from .workflow import build_env
    from ..environments.farm_inflow import generate_inflow
    job = root / f"{result['stage']}_run_{result['run_id']}"
    path = next(job.glob("segment_000/step_00002048.pth"))
    original_sha = digest(path)
    outputs = []
    for _ in range(2):
        agent, meta = ResidualMADDPG.load(path)
        cfg = meta["config"]
        identity = meta["identity"]
        stage, control, run = identity["stage"], identity["control"], identity["run_id"]
        phase = STAGES.index(stage)
        env = build_env(cfg)
        noise_std = p["stage_noise_std"]["pitch" if control and stage == "pitch_speed" else "pitch_speed" if control else stage]
        noise = Exploration(seed_for(42, 1013 + phase, run), noise_std, [10., 3., 5.], env.dt, "white", p["noise_end_fraction"])
        noise.load_state_dict(meta["noise"])
        episode, step = meta["episode"], meta["step"]
        family, target, pitch = shared.episode_design(p, run, episode)
        inflow = deepcopy(p["inflow"])
        inflow["speed"]["scenario"] = family
        wind = generate_inflow(inflow, dt_s=env.dt, horizon=env.horizon, seed=42, split="train",
            episode=p["training_episode_offset"] + phase * 10000 + run * 1000 + episode)
        env.initial = np.asarray(cfg["environment"]["initial_operating_point"], dtype=float).copy()
        env.initial[1] = pitch
        obs, _ = env.reset(seed=42, options=dict(wind_trajectory=wind.values, target_w=target))
        noise.reset()
        actions, rewards, losses = [], [], []
        for _ in range(env.horizon):
            agent.config = replace(agent.config, residual_scales=scales(p, cfg, stage, step, control))
            action = agent.act(obs, noise=noise.sample(step / p["steps_per_run"]))
            nxt, reward, done, _, info = env.step(action)
            agent.replay.add(obs, info["executed_action"], reward, nxt, done)
            step += 1
            if step % p["update_every"] == 0:
                losses.append(agent.update())
            actions.append(info["executed_action"])
            rewards.append(reward)
            obs = nxt
        outputs.append((agent, np.asarray(actions), np.asarray(rewards), losses, noise.state_dict()))
    left, right = outputs
    np.testing.assert_array_equal(left[1], right[1])
    np.testing.assert_array_equal(left[2], right[2])
    assert left[3] == right[3]
    np.testing.assert_equal(left[4], right[4])
    for kind in ("actors", "target_actors", "critics", "target_critics"):
        assert all(torch.equal(v, getattr(right[0], kind).state_dict()[key]) for key, v in getattr(left[0], kind).state_dict().items())
    # For the actual resumed worker, also compare against its saved replay tail.
    final, _ = ResidualMADDPG.load(result["final"])
    size, position = final.replay.size, final.replay.position
    order = (np.arange(size) + position) % final.replay.capacity if size == final.replay.capacity else np.arange(size)
    new = order[-result["steps"]:]
    actual_indices = new[2048:2176]
    np.testing.assert_array_equal(left[1], final.replay.data["actions"][actual_indices])
    assert digest(path) == original_sha
    return dict(source_checkpoint=str(path), fork_steps=128, fork_count=2, actions_rewards_losses_noise_networks_exact=True,
        actual_resumed_replay_next_episode_exact=True, source_unchanged=True, experiment_steps_added=0)


def verify(root):
    import numpy as np
    import torch
    import yaml
    from .residual_algorithm import ResidualMADDPG
    from .residual_random_control import initialize, scales, engineering_pass
    root = Path(root)
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    p = saved["protocol"]
    verify_hashes(saved["source_hashes"])
    verify_hashes(selection["hashes"])
    assert digest(root / "config.yaml") == selection["root_config_sha256"]
    assert digest(root / "bank/manifest.json") == selection["bank_sha256"]
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    checks, replay_rows = [], []
    for r in selection["results"]:
        initial, meta = ResidualMADDPG.load(r["initial"])
        identity = meta["identity"]
        reconstructed, original, _, maximum = initialize(identity["parent"], identity["stage"], p, meta["config"], identity["control"])
        for kind in ("actors", "target_actors", "critics", "target_critics"):
            assert all(torch.equal(v, getattr(reconstructed, kind).state_dict()[key]) for key, v in getattr(initial, kind).state_dict().items())
        np.testing.assert_equal(initial.replay.state_dict(), original.replay.state_dict())
        for label, path in (("initial", r["initial"]), ("selected", r["best"]["checkpoint"]), ("final", r["final"])):
            before = digest(path)
            agent, metadata = ResidualMADDPG.load(path)
            buffer = io.BytesIO()
            agent.save(buffer, metadata)
            buffer.seek(0)
            other, other_meta = ResidualMADDPG.load(buffer)
            np.testing.assert_equal(metadata, other_meta)
            obs = agent.replay.data["obs"][0]
            np.testing.assert_array_equal(agent.act(obs, .15), other.act(obs, .15))
            assert agent.update() == other.update()
            assert digest(path) == before
            assert tuple(agent.config.residual_scales) == tuple(metadata["evaluation_scales"])
        final, metadata = ResidualMADDPG.load(r["final"])
        data = final.replay.state_dict()["data"]
        n = len(data["obs"])
        np.testing.assert_array_equal(data["actions"], data["next_obs"][:, :, 5:8])
        envcfg = r["config"]["environment"]
        width = np.asarray(envcfg["action_high"]) - envcfg["action_low"]
        gamma_old = (data["obs"][:, :, 2] + 1) * width[0] / 2 + envcfg["action_low"][0]
        gamma_new = (data["next_obs"][:, :, 2] + 1) * width[0] / 2 + envcfg["action_low"][0]
        theta_old = np.arctan2(data["obs"][:, 0, 11], data["obs"][:, 0, 12])
        theta_new = np.arctan2(data["next_obs"][:, 0, 11], data["next_obs"][:, 0, 12])
        heading_delta = (gamma_new - gamma_old + (theta_new - theta_old)[:, None] + np.pi) % (2 * np.pi) - np.pi
        delta = np.concatenate((heading_delta[..., None], (data["next_obs"][:, :, 3:5] - data["obs"][:, :, 3:5]) * width[1:] / 2), axis=-1)
        assert np.all(np.abs(delta).max(axis=(0, 1)) <= np.asarray(envcfg["rate_limits"]) * envcfg["dt_s"] + 1e-6)
        expected = envcfg["reward_scale"] * (-data["next_obs"][:, 0, 9] ** 2 - envcfg["action_change_weight"] * np.mean((data["actions"] - data["obs"][:, :, 5:8]) ** 2, axis=(1, 2)))
        np.testing.assert_allclose(data["rewards"], np.repeat(expected[:, None], 3, axis=1), atol=5e-6, rtol=4e-6)
        assert n == min(final.replay.capacity, r["inherited_replay_size"] + r["steps"])
        order = (np.arange(n) + final.replay.position) % final.replay.capacity if n == final.replay.capacity else np.arange(n)
        new = order[-r["steps"]:]
        current = data["obs"][new]
        scale, slope, low, high = final.config.residual_speed_schedule
        baseline = np.clip(2 * (current[:, :, 1] * scale * slope - low) / (high - low) - 1, -1, 1)
        correction = np.abs(data["actions"][new, :, 2] - baseline)
        envelopes = np.array([scales(p, r["config"], identity["stage"], step, identity["control"])[2] for step in range(r["steps"])])
        assert np.all(correction <= envelopes[:, None] + 4e-6)
        yaw_correction = np.abs(data["actions"][new, :, 0] - final.config.fixed_action[0])
        yaw_envelopes = np.array([scales(p, r["config"], identity["stage"], step, identity["control"])[0] for step in range(r["steps"])])
        assert np.all(yaw_correction <= yaw_envelopes[:, None] + 4e-6)
        assert r["engineering_pass"] == engineering_pass(r, p)
        checks.append(dict(stage=r["stage"], run_id=r["run_id"], zero_head_initial_state_exact=True,
            max_replay_handover_error=maximum, load_noise_and_next_update_exact=True, resume_segments=r["resume_segments"]))
        replay_rows.append(dict(stage=r["stage"], run_id=r["run_id"], retained_transitions=n, new_transitions=r["steps"],
            total_action_next_command_exact=True, physical_rates_reward_verified=True, dynamic_residual_envelope_verified=True))
    grouped = {}
    with (root / "test/trajectories.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = tuple(row[k] for k in ("stage", "run_id", "controller", "case_id"))
            grouped.setdefault(key, []).append(float(row["farm_power_w"]) - float(row["target_w"]))
    maximum = 0.
    count = 0
    with (root / "test/metrics.csv").open(encoding="utf-8") as f:
        test_metrics = list(csv.DictReader(f))
    for row in test_metrics:
        key = tuple(row[k] for k in ("stage", "run_id", "controller", "case_id"))
        maximum = max(maximum, abs(float(np.sqrt(np.mean(np.square(grouped[key])))) - float(row["rmse_w"])))
        count += 1
    assert maximum < 1e-7
    fork_result = next(r for r in selection["results"] if r["stage"] == "pitch_speed" and r["run_id"] == 0)
    recovery = recovery_fork(root, p, fork_result)
    aggregate = []
    for stage in dict.fromkeys(r["stage"] for r in test_metrics):
        for controller in ("initial", "selected", "final", "parent", "fixed", "p", "pi"):
            rows = [r for r in test_metrics if r["stage"] == stage and r["controller"] == controller and r["family"] in shared.FAMILIES]
            means = [np.mean([float(r["rmse_w"]) for r in rows if r["run_id"] == run]) for run in sorted(set(r["run_id"] for r in rows))]
            aggregate.append(dict(stage=stage, controller=controller, mean_rmse_w=float(np.mean(means)),
                std_across_runs_w=float(np.std(means, ddof=1)) if len(means) > 1 else 0.))
    shared.write_csv(root / "test/aggregate.csv", aggregate)
    shared.write_csv(root / "replay_audit.csv", replay_rows)
    report = dict(seed=42, protected_files=len(saved["source_hashes"]), protected_unchanged=True,
        checkpoint_audit=checks, replay_audit=replay_rows, recovery_fork=recovery,
        test_metrics=count, test_trace_rows=sum(map(len, grouped.values())), max_rmse_recompute_difference_w=maximum,
        experiment_training_steps=sum(r["steps"] for r in selection["results"]), physical_validation=False)
    shared.write_json(root / "verification.json", report)
    summary = json.loads((root / "summary.txt").read_text(encoding="utf-8"))
    summary.update(verification=report, aggregate=aggregate, results=[dict(stage=r["stage"], run_id=r["run_id"],
        selected_step=r["best"]["step"], mean_w=r["best"]["score_w"], worst_w=max(v["rmse_w"] for v in r["best"]["validation"]),
        final_over_selected=r["final_over_selected"], engineering_pass=r["engineering_pass"], strict_accuracy_pass=r["strict_accuracy_pass"],
        lineage=r["lineage"], handover=r["handover"]) for r in selection["results"]])
    with (root / "test/corrections.csv").open(encoding="utf-8") as f:
        summary["test_corrections"] = list(csv.DictReader(f))
    shared.write_json(root / "summary.txt", summary)
    plot(root, selection, aggregate)
    verify_hashes(saved["source_hashes"])
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def plot(root, selection, aggregate):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    for result in selection["results"]:
        _, meta = __import__("optimization_control.maddpg_wind_farm.residual_algorithm", fromlist=["ResidualMADDPG"]).ResidualMADDPG.load(result["final"])
        rows = meta["history"]
        axes[0].plot([r["steps"] for r in rows], [r["validation_rmse_w"] / 1000 for r in rows],
            linestyle="--" if "control" in result["stage"] else "-", label=f"{result['stage']} / stream{result['run_id']}")
    for stage in dict.fromkeys(r["stage"] for r in aggregate):
        rows = [r for r in aggregate if r["stage"] == stage]
        axes[1].errorbar([r["controller"] for r in rows], [r["mean_rmse_w"] / 1000 for r in rows],
            yerr=[r["std_across_runs_w"] / 1000 for r in rows], fmt="o", capsize=3, label=stage)
    axes[0].set(xlabel="Additional training steps", ylabel="Validation RMSE [kW]", title="Always evaluated at full residual authority")
    axes[1].set(xlabel="Frozen test controller", ylabel="Routine test RMSE [kW]", title="Mean +/- SD across training streams")
    for ax in axes:
        ax.grid(alpha=.2)
        ax.legend(fontsize=7)
    fig.suptitle("Baseline + bounded MADDPG correction | synthetic PINN")
    fig.savefig(root / "residual_validation_test.png", dpi=180)
    fig.savefig(root / "residual_validation_test.pdf")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    activate_runtime(".venv/pinn_tf216")
    verify(args.output)


if __name__ == "__main__":
    main()
