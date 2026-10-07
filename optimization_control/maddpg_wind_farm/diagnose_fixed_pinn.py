"""Audit saved fixed-condition PINN results without training or changing them."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from .fixed_pinn_demo import activate_runtime, digest, read_config


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def run(experiment, output):
    import numpy as np
    import torch
    from .algorithm import MADDPG
    from .controllers import PitchController
    from .workflow import build_env, fresh_output, write_csv
    from ..environments.pinn_adapter import CoupledIntegrationPredictor

    torch.set_num_threads(1)
    experiment = Path(experiment).resolve()
    agent, metadata = MADDPG.load(experiment / "training/checkpoint.pth")
    initial, _ = MADDPG.load(experiment / "initial/checkpoint.pth")
    config = metadata["config"]
    protected = [experiment / "training/checkpoint.pth", experiment / "initial/checkpoint.pth",
                 experiment / "model/trained.keras", experiment / "evaluation/trajectories.csv",
                 experiment / "initial_evaluation/trajectories.csv"]
    hashes = {str(p): digest(p) for p in protected}
    team_hashes = json.loads((experiment / "data/metadata.json").read_text(encoding="utf-8"))["source_hashes"]
    if not all(digest(p) == h for p, h in team_hashes.items()):
        raise ValueError("team sources differ from the saved source manifest")
    out = fresh_output(output, dict(seed=42, source_experiment=str(experiment),
        purpose="saved_fixed_condition_diagnosis_no_training", source_hashes=hashes, team_source_hashes=team_hashes,
        first_action_counterfactual="one candidate action, then saved policy until termination",
        teacher_check="offline predictions at saved operating points, NOT teacher closed loop or physical truth",
        critic_candidates=["actor", "fixed", "p", "actor_pitch_minus_0.1", "actor_pitch_plus_0.1"]))
    teacher = CoupledIntegrationPredictor([5e6] * 3)
    metrics, traces = [], {}
    for stage, folder in (("initial", "initial_evaluation"), ("trained", "evaluation")):
        stored = {(r["scenario"], r["controller"]): r for r in read_csv(experiment / folder / "metrics.csv")}
        groups = defaultdict(list)
        for row in read_csv(experiment / folder / "trajectories.csv"):
            groups[(row["scenario"], row["controller"])].append(row)
        for (scenario, controller), rows in groups.items():
            power = np.array([float(r["farm_power_w"]) for r in rows])
            target = np.array([float(r["target_w"]) for r in rows])
            error = power - target
            assert len(rows) == config["environment"]["horizon"]
            assert np.ptp(target) == 0
            assert np.allclose(error, [float(r["error_w"]) for r in rows], rtol=0, atol=1e-6)
            assert np.allclose(power, [sum(float(r[f"power_{i}_w"]) for i in (1, 2, 3)) for r in rows], rtol=0, atol=1)
            rmse = float(np.sqrt(np.mean(error**2)))
            assert abs(rmse - float(stored[(scenario, controller)]["rmse_w"])) < 1e-6
            x = np.array([[float(r[k]) for k in ("wind_m_s", "direction_rad", "ti")]
                + [float(r[f"{field}_{i}"]) for field in ("yaw_rad", "pitch_rad", "speed_rad_s")
                   for i in (1, 2, 3)] for r in rows], dtype=np.float32)
            assert np.all(np.ptp(x[:, :3], axis=0) == 0)
            teacher_power = teacher(x)[:, :3].sum(axis=1)
            metrics.append(dict(stage=stage, scenario=scenario, controller=controller,
                target_mw=target[0]/1e6, rmse_kw=rmse/1000,
                first32_rmse_kw=float(np.sqrt(np.mean(error[:32]**2)))/1000,
                last32_rmse_kw=float(np.sqrt(np.mean(error[-32:]**2)))/1000,
                first32_squared_error_share=float(np.sum(error[:32]**2)/np.sum(error**2)),
                first_power_mw=power[0]/1e6, final_power_mw=power[-1]/1e6,
                teacher_same_points_rmse_kw=float(np.sqrt(np.mean((teacher_power-target)**2)))/1000,
                mean_network_minus_teacher_kw=float(np.mean(power-teacher_power))/1000))
            traces[(stage, scenario, controller)] = (rows, teacher_power)
    write_csv(out / "metrics.csv", metrics)
    for scenario in config["evaluation"]["scenarios"]:
        for mode in ("fixed", "p", "pi"):
            assert traces[("initial", scenario["name"], mode)][0] == traces[("trained", scenario["name"], mode)][0]
    print("Saved metrics, units, baseline identity and fixed wind audited", flush=True)

    env = build_env(config)
    policy_rows, feasibility, critic_rows = [], [], []
    # A one-dimensional numerical witness certifies each target in this demo
    # model only. It is not a global capacity bound or a physical certificate.
    wind = [config["environment"][k] for k in ("wind_base_m_s", "wind_direction_rad", "turbulence_intensity")]

    def static_power(pitch):
        operating = np.tile(env.initial, (3, 1)).astype(np.float32)
        operating[:, 1] = pitch
        x = np.concatenate((wind, operating[:, 0], operating[:, 1], operating[:, 2]))[None, :]
        return float(env.plant.predictor(x)[0, :3].sum())

    grid = np.linspace(env.low[1], env.high[1], 101)
    powers = np.array([static_power(p) for p in grid])
    write_csv(out / "pitch_scan.csv", [dict(pitch_rad=p, power_w=w) for p, w in zip(grid, powers)])
    for scenario in config["evaluation"]["scenarios"]:
        target = scenario["target_w"]
        delta = powers - target
        brackets = np.where(delta[:-1] * delta[1:] <= 0)[0]
        if len(brackets):
            j = brackets[0]
            low, high = grid[j], grid[j+1]
            low_error = static_power(low) - target
            for _ in range(24):
                mid = (low + high)/2
                if (static_power(mid)-target)*low_error > 0:
                    low = mid
                else:
                    high = mid
            pitch = (low + high)/2
            feasibility.append(dict(target_mw=target/1e6, feasible_witness=True,
                pitch_rad=pitch, yaw_rad=float(env.initial[0]), speed_rad_s=float(env.initial[2]),
                power_w=static_power(pitch), residual_w=static_power(pitch)-target))
        else:
            feasibility.append(dict(target_mw=target/1e6, feasible_witness=False,
                pitch_rad="", yaw_rad=float(env.initial[0]), speed_rad_s=float(env.initial[2]),
                power_w="", residual_w=""))
        obs, _ = env.reset(seed=42, options={"target_w": target})
        assert abs(float(obs[0, 8])*env.rated.sum()-target) < 1
        for stage, policy in (("initial", initial), ("trained", agent)):
            command = env.low + (policy.act(obs)+1)*(env.high-env.low)/2
            for i in range(3):
                policy_rows.append(dict(stage=stage, target_mw=target/1e6, turbine=i+1,
                    yaw_ref_rad=command[i, 0], pitch_ref_rad=command[i, 1], speed_ref_rad_s=command[i, 2]))
        action = agent.act(obs)
        candidates = {"actor": action, "fixed": PitchController(env, config["baselines"], "fixed").act(obs),
                      "p": PitchController(env, config["baselines"], "p").act(obs)}
        for name, change in (("actor_pitch_minus_0.1", -.1), ("actor_pitch_plus_0.1", .1)):
            candidate = action.copy()
            candidate[:, 1] = np.clip(candidate[:, 1]+change, -1, 1)
            candidates[name] = candidate
        for name, first_action in candidates.items():
            obs, _ = env.reset(seed=42, options={"target_w": target})
            with torch.no_grad():
                joint = torch.tensor(np.concatenate((obs.ravel(), first_action.ravel())), dtype=torch.float32)[None, :]
                q = [float(c(joint).item()) for c in agent.critics]
            discounted_return, errors, action_cost = 0., [], 0.
            for t in range(env.horizon):
                current = first_action if t == 0 else agent.act(obs)
                obs, reward, terminated, truncated, info = env.step(current)
                assert np.allclose(info["executed_action"], current)
                discounted_return += agent.config.gamma**t * float(reward[0])
                errors.append(info["error_w"])
                action_cost += config["environment"]["reward_scale"] * config["environment"]["action_change_weight"] * info["action_change"]
                if terminated or truncated:
                    break
            critic_rows.append(dict(target_mw=target/1e6, first_action=name,
                q_mean=float(np.mean(q)), q1=q[0], q2=q[1], q3=q[2],
                realized_discounted_return=discounted_return,
                rmse_kw=float(np.sqrt(np.mean(np.square(errors))))/1000,
                undiscounted_action_penalty=action_cost))
        print(f"Target {target/1e6:g} MW: feasibility and first-action replay complete", flush=True)
    write_csv(out / "target_response.csv", policy_rows)
    write_csv(out / "feasibility.csv", feasibility)
    write_csv(out / "critic_probes.csv", critic_rows)
    training_rows = read_csv(experiment / "training/metrics.csv")
    counts = defaultdict(int)
    for row in training_rows:
        counts[float(row["target_w"])] += 1
    target_counts = {str(k): v for k, v in sorted(counts.items())}
    replay_counts = {str(k): int(np.sum(np.isclose(agent.replay.data["obs"][:agent.replay.size, 0, 8]*env.rated.sum(), k, atol=1))) for k in counts}
    assert sum(replay_counts.values()) == agent.replay.size
    summary = dict(seed=42, metrics_verified=24, trajectory_rows_verified=3072,
        baseline_identical=True, training_episodes=target_counts, replay_transitions=replay_counts,
        training_steps=metadata["steps"], updates=agent.updates,
        weighted_target_mean_mw=sum(k*v for k,v in counts.items())/sum(counts.values())/1e6,
        feasible_targets=sum(bool(r["feasible_witness"]) for r in feasibility),
        initial_pitch_scan_min_w=float(powers.min()), initial_pitch_scan_max_w=float(powers.max()),
        source_files_unchanged=all(digest(p)==h for p,h in hashes.items()) and all(digest(p)==h for p,h in team_hashes.items()),
        critic_scope="reset states; finite 128-step return of first candidate then saved actor; no new training",
        teacher_scope="same operating points only; synthetic label source, not real truth or closed-loop teacher performance")
    assert summary["source_files_unchanged"]
    (out / "summary.txt").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    for ax, scenario in zip(axes, config["evaluation"]["scenarios"]):
        for stage, mode, label in (("initial", "maddpg", "Initial MADDPG"), ("trained", "maddpg", "Trained MADDPG"),
                                   ("trained", "p", "P"), ("trained", "pi", "PI")):
            rows = traces[(stage, scenario["name"], mode)][0]
            ax.plot([float(r["time_s"]) for r in rows], [float(r["farm_power_w"])/1e6 for r in rows], label=label)
        ax.axhline(scenario["target_w"]/1e6, color="k", linestyle="--", label="Target")
        ax.set_title(f"Target {scenario['target_w']/1e6:g} MW")
        ax.set_xlabel("Time [s]")
        ax.grid(alpha=.25)
    axes[0].set_ylabel("Predicted farm power [MW]")
    axes[-1].legend()
    fig.suptitle("Fixed-condition synthetic transfer-model demo; not physical performance")
    fig.tight_layout()
    fig.savefig(out / "power_diagnosis.png", dpi=150)
    plt.close(fig)
    print(json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--runtime", default=".venv/pinn_tf216")
    args = parser.parse_args()
    cfg = read_config(Path(args.experiment) / "config.yaml")
    if not cfg["purpose"].startswith("synthetic_fixed_condition"):
        raise ValueError("only the explicit fixed-condition demo is supported")
    activate_runtime(args.runtime)
    run(args.experiment, args.output)


if __name__ == "__main__":
    main()
