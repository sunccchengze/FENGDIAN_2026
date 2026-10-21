"""Fixed feasible mock task: initial/trained policies, channel ablations, P/PI.

One-factor experiments: identical seed, inflow, target, actuator and horizon;
only channel mask or the uniform reward multiplier changes. No physical claims.
"""

import argparse
from copy import deepcopy
import json
import numpy as np
import torch

from .workflow import load_config, DEFAULT_CONFIG, build_env, make_agent, fresh_output, write_csv
from .controllers import PitchController
from ..environments.plant_model import AppliedOperatingPoint, DisturbanceBatch

MASKS = {"pitch": [0, 1, 0], "pitch_speed": [0, 1, 1], "all": [1, 1, 1]}


def rollout(env, controller, *, keep_trace=False):
    obs, _ = env.reset(seed=42)
    errors, rewards, actions, trace = [], [], [], []
    for _ in range(env.horizon):
        action = controller(obs)
        obs, reward, done, _, info = env.step(action)
        errors.append(info["error_w"])
        rewards.append(float(reward[0]))
        actions.append(info["executed_action"])
        if keep_trace:
            row = {"step": info["step"], "farm_power_w": info["farm_power_w"], "error_w": info["error_w"]}
            for i in range(3):
                for j, field in enumerate(("gamma_rad", "beta_rad", "omega_rad_s")):
                    row[f"{field}_{i+1}"] = info["applied"][i, j]
            trace.append(row)
        if done:
            break
    active = np.asarray(actions)[:, :, env.control_mask]
    result = {"rmse_w": float(np.sqrt(np.mean(np.square(errors)))),
              "steady_rmse_w": float(np.sqrt(np.mean(np.square(errors[len(errors)//2:])))),
              "mean_error_w": float(np.mean(errors)), "return": float(np.sum(rewards)),
              "command_boundary_fraction": float(np.mean(np.abs(active) > .98))}
    return result, trace, rewards


def feasible_witness(env):
    """Find a common pitch equilibrium by bisection; explicit mock witness only."""
    env.reset(seed=42)
    d = DisturbanceBatch(*(np.array([[v]], dtype=np.float32) for v in env.wind))
    def power(beta):
        op = AppliedOperatingPoint(env.plant.turbine_ids, np.full((1,3), env.initial[0]),
                                  np.full((1,3), beta), np.full((1,3), env.initial[2]))
        return float(env.plant.predict_steady(d, op).floris_farm_power_sum_w[0,0])
    lo, hi = env.low[1], env.high[1]
    p_lo, p_hi = power(lo), power(hi)
    if not p_hi < env.target < p_lo:
        raise ValueError("diagnostic target lacks pitch-only equilibrium bracket")
    for _ in range(45):
        mid = (lo+hi)/2
        if power(mid) > env.target:
            lo = mid
        else:
            hi = mid
    return {"target_w": env.target, "common_pitch_rad": (lo+hi)/2,
            "equilibrium_power_w": power((lo+hi)/2), "bracket_power_w": [p_hi, p_lo],
            "scope": "steady mock feasibility, not instantaneous reachability"}


def run(output, steps=8192, reward_scales=(1.0,), modes=tuple(MASKS)):
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    base = load_config(DEFAULT_CONFIG)
    base["environment"].update(horizon=128, wind_amplitude_m_s=0, wind_noise_std_m_s=0,
                                wind_base_m_s=8, target_w=3e6, yaw_frame="nacelle_heading")
    base["environment"].pop("inflow", None)
    base["training"].update(total_steps=steps, episode_target_fractions=[.2])
    if steps < 1024 or steps % 128:
        raise ValueError("diagnostic steps must be >=1024 and multiple of 128")
    root = fresh_output(output, dict(base, diagnostic={"modes": list(modes), "reward_scales": list(reward_scales)}))
    witness = feasible_witness(build_env(base))
    results = []
    for scale in reward_scales:
        for name in modes:
            cfg = deepcopy(base)
            cfg["environment"].update(control_mask=MASKS[name], reward_scale=scale)
            folder = fresh_output(root / f"{name}_reward{scale:g}", cfg)
            env, evaluation = build_env(cfg), build_env(cfg)
            agent = make_agent(cfg, env)
            local = []
            def measure(label, count, policy):
                stats, trace, returns = rollout(evaluation, policy, keep_trace=True)
                row = dict(channels=name, reward_scale=scale, controller=label, steps=count, **stats)
                if label == "maddpg":
                    initial_obs, _ = evaluation.reset(seed=42)
                    with torch.no_grad():
                        o = torch.as_tensor(initial_obs)
                        a = torch.as_tensor(agent.act(initial_obs))
                        q = agent.critics[0](torch.cat((o.flatten(), a.flatten()))).item()
                    row["q_initial"] = q
                    row["discounted_return"] = float(np.dot(np.power(agent.config.gamma, np.arange(len(returns))), returns))
                else:
                    row.update(q_initial="", discounted_return="")
                local.append(row); results.append(row)
                print(json.dumps(row), flush=True)
                if count in (0, steps):
                    write_csv(folder / f"{label}_{count}_trajectory.csv", trace)
            measure("maddpg", 0, agent.act)
            for mode in ("fixed", "p", "pi"):
                baseline = PitchController(evaluation, cfg["baselines"], mode)
                measure(mode, 0, baseline.act)
            obs, _ = env.reset(seed=42)
            for step in range(1, steps+1):
                action = agent.rng.uniform(-1,1,(3,3)).astype(np.float32) if step <= cfg["training"]["warmup_steps"] else agent.act(obs, cfg["training"]["noise_std"])
                nxt, rew, done, _, info = env.step(action)
                agent.replay.add(obs, info["executed_action"], rew, nxt, done)
                if step >= cfg["training"]["warmup_steps"] and step % cfg["training"]["update_every"] == 0:
                    agent.update()
                obs = nxt
                if done:
                    obs, _ = env.reset(seed=42)
                if step % 1024 == 0 or step == steps:
                    measure("maddpg", step, agent.act)
            agent.save(folder / "checkpoint.pth", {"config":cfg, "steps":steps, "episodes":steps//env.horizon,
                                                   "normalization":env.normalization()})
            write_csv(folder / "metrics.csv", local)
            (folder / "summary.txt").write_text(json.dumps(witness, indent=2)+"\nOne-seed mock diagnostic, not physical validation.\n", encoding="utf-8")
    write_csv(root / "metrics.csv", results)
    (root / "summary.txt").write_text(
        "Command: python -m optimization_control.maddpg_wind_farm.diagnostics --output <new-dir> --steps <steps> --reward-scales <scales>\n"
        + json.dumps(witness, indent=2)+"\nFixed inlet, seed 42; uniform reward scaling preserves the task optimum.\n"
        "Same permissions within each channel mask. Single seed: no statistical superiority claim.\n", encoding="utf-8")
    plot(root, results)
    return results


def plot(root, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(15,4), sharey=True)
    for ax, name in zip(axes, MASKS):
        for scale in sorted(set(r["reward_scale"] for r in rows)):
            part = [r for r in rows if r["channels"] == name and r["reward_scale"] == scale and r["controller"] == "maddpg"]
            ax.plot([r["steps"] for r in part], [r["rmse_w"]/1e3 for r in part], label=f"MADDPG reward x{scale:g}")
        for mode in ("p", "pi"):
            part = [r for r in rows if r["channels"] == name and r["controller"] == mode]
            if part:
                ax.axhline(part[0]["rmse_w"]/1e3, linestyle="--", label=mode.upper())
        ax.set_title(name); ax.set_xlabel("Training steps"); ax.grid(alpha=.2); ax.legend()
    axes[0].set_ylabel("Fixed-inlet RMSE [kW]")
    fig.suptitle("Mock-only learning diagnosis | seed 42")
    fig.tight_layout(); fig.savefig(root / "learning_curves.png", dpi=140); plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--steps", type=int, default=8192)
    p.add_argument("--reward-scales", type=float, nargs="+", default=[1.0])
    p.add_argument("--modes", choices=list(MASKS), nargs="+", default=list(MASKS))
    args = p.parse_args()
    run(args.output, args.steps, args.reward_scales, args.modes)
