"""Train, resume, evaluate and plot the three-turbine MADDPG pipeline."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
from pathlib import Path
import numpy as np
import torch
import yaml

from .algorithm import AlgorithmConfig, MADDPG
from .controllers import PitchController
from ..environments.pinn_adapter import PINNAdapter, CoupledIntegrationPredictor, DEFAULT_FEATURES
from ..environments.maddpg_farm_env import MADDPGFarmEnv, OBSERVATIONS

DEFAULT_CONFIG = Path(__file__).parent / "configs" / "default.yaml"


def load_config(path):
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if config.get("schema_version") != 1 or config.get("seed") != 42:
        raise ValueError("schema_version=1 and project seed=42 required")
    return config


def build_env(config):
    p = config["plant"]
    if p["kind"] == "mock":
        if tuple(p["features"]) != DEFAULT_FEATURES or any(k in p for k in ("input_mean", "input_scale", "output_mean", "output_scale")):
            raise ValueError("mock uses default features and physical identity normalization")
        predictor = CoupledIntegrationPredictor(p["rated_power_w"])
        if p["source"] != "coupled_integration_mock":
            raise ValueError("mock source must be explicitly labeled")
    elif p["kind"] == "pinn":
        # Backend owns model loading/device and converts its output to a NumPy [B,6].
        module, factory = p["factory"].split(":")
        predictor = getattr(importlib.import_module(module), factory)(p.get("backend", {}))
        if not callable(predictor):
            raise TypeError("PINN factory must return a callable")
        if not p.get("model_version") or p["layout"].get("spacing_m", 0) is None or p["layout"]["spacing_m"] <= 0:
            raise ValueError("real PINN requires model_version and positive fixed spacing_m")
        if getattr(predictor,"expects_physical_default_inputs",False):
            if tuple(p["features"])!=DEFAULT_FEATURES:
                raise ValueError("team bridge requires the default physical twelve-feature order")
            for key,value in (("input_mean",0),("input_scale",1),("output_mean",0),("output_scale",1)):
                if not np.all(np.asarray(p.get(key,value))==value):
                    raise ValueError("team model owns normalization; adapter must use identity scaling")
            if hasattr(predictor,"spacing_m") and not np.isclose(p["layout"]["spacing_m"],predictor.spacing_m):
                raise ValueError("optimization layout spacing differs from trained team geometry")
    else:
        raise ValueError("plant.kind must be mock or pinn; no implicit mock fallback")
    plant = PINNAdapter(predictor, features=p["features"], turbine_ids=p["turbine_ids"],
                        rated_power_w=p["rated_power_w"], bounds=p["bounds"], source=p["source"],
                        power_semantics=p["power_semantics"],
                        **{k: p[k] for k in ("input_mean", "input_scale", "output_mean", "output_scale", "constants") if k in p})
    return MADDPGFarmEnv(plant, config["environment"])


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fresh_output(path, config):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    (path / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def train(config, output, resume=None):
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    env = build_env(config)
    train_cfg = config["training"]
    total = int(train_cfg["total_steps"])
    if total <= 0 or total % env.horizon:
        raise ValueError("total_steps must be a positive multiple of horizon; checkpoints are episode-boundary snapshots")
    if int(train_cfg["update_every"]) <= 0 or train_cfg["noise_std"] < 0 or train_cfg["warmup_steps"] < 0:
        raise ValueError("invalid training schedule")
    fractions = np.asarray(train_cfg["episode_target_fractions"], dtype=float)
    if fractions.ndim != 1 or len(fractions) == 0 or not np.all(np.isfinite(fractions)) or np.any(fractions <= 0) or np.any(fractions > 1):
        raise ValueError("invalid episode target fractions")
    if resume:
        agent, saved = MADDPG.load(resume)
        previous = saved["config"]
        comparable = json.loads(json.dumps(config))
        comparable["training"]["total_steps"] = previous["training"]["total_steps"]
        if comparable != previous:
            raise ValueError("resume permits only total_steps to change; plant/scales/algorithm must match")
        step, episode = saved["steps"], saved["episodes"]
        if total <= step or step % env.horizon:
            raise ValueError("resume requires a larger total and an episode-boundary checkpoint")
    else:
        agent = make_agent(config, env)
        step, episode = 0, 0
    output = fresh_output(output, config)
    (output / "normalization.json").write_text(json.dumps(env.normalization(), indent=2), encoding="utf-8")
    rows = []
    while step < total:
        target = float(fractions[episode % len(fractions)] * env.rated.sum())
        obs, _ = env.reset(seed=config["seed"], options={"target_w": target, "episode": episode, "split": "train"}) if env.config.get("inflow") else env.reset(seed=config["seed"] + episode, options={"target_w": target})
        errors, returns, losses = [], 0.0, []
        for _ in range(env.horizon):
            action = agent.rng.uniform(-1, 1, (3, 3)).astype(np.float32) if step < train_cfg["warmup_steps"] else agent.act(obs, train_cfg["noise_std"])
            next_obs, rewards, terminated, truncated, info = env.step(action)
            agent.replay.add(obs, info["executed_action"], rewards, next_obs, terminated)
            step += 1
            if step >= train_cfg["warmup_steps"] and agent.replay.size >= agent.config.batch_size and step % train_cfg["update_every"] == 0:
                losses.append(agent.update())
            errors.append(info["error_w"])
            returns += float(rewards[0])
            obs = next_obs
            if terminated or truncated:
                break
        episode += 1
        row = {"episode": episode, "steps": step, "target_w": target, "return": returns,
               "rmse_w": float(np.sqrt(np.mean(np.square(errors)))), "updates": agent.updates,
               "actor_loss": float(np.mean([l["actor_loss"] for l in losses])) if losses else 0.0,
               "critic_loss": float(np.mean([l["critic_loss"] for l in losses])) if losses else 0.0}
        rows.append(row)
        print(json.dumps(row), flush=True)
    agent.save(output / "checkpoint.pth", {"config": config, "steps": step, "episodes": episode,
                                          "normalization": env.normalization()})
    write_csv(output / "metrics.csv", rows)
    (output / "summary.txt").write_text(
        f"source={config['plant']['source']}\npower_semantics={config['plant']['power_semantics']}\nsteps={step}\nepisodes={episode}\nupdates={agent.updates}\n"
        f"resume_from={resume}\ncheckpoint={output.resolve() / 'checkpoint.pth'}\n"
        "Integration training is not evidence of physical validity or algorithm superiority.\n", encoding="utf-8")
    return output / "checkpoint.pth"


def make_agent(config, env, *, seed=None):
    algorithm = dict(config["algorithm"])
    algorithm.update(action_mask=tuple(int(v) for v in env.control_mask),
                     fixed_action=tuple(float(v) for v in env.normalize_commands(np.tile(env.initial, (3, 1)))[0]))
    if env.reference_schedule:
        fixed = list(algorithm["fixed_action"])
        fixed[0] = 2 * (env.reference_schedule["yaw_offset_rad"] - env.low[0]) / (env.high[0] - env.low[0]) - 1
        algorithm["fixed_action"] = tuple(fixed)
        if not env.control_mask[2]:
            algorithm["speed_reference_schedule"] = (env.wind_scale, env.reference_schedule["speed_per_wind_rad_m"], float(env.low[2]), float(env.high[2]))
    return MADDPG(AlgorithmConfig(obs_dim=len(OBSERVATIONS), seed=config["seed"] if seed is None else seed, **algorithm))


def evaluate(checkpoint, output, *, backend_paths=None):
    torch.set_num_threads(1)
    agent, metadata = MADDPG.load(checkpoint)
    config = metadata["config"]
    if backend_paths is not None:
        from copy import deepcopy
        if config["plant"]["kind"] != "pinn" or not set(backend_paths) <= {"run_dir", "script"}:
            raise ValueError("evaluation may relocate only PINN run_dir/script; model identity stays pinned")
        config = deepcopy(config)
        config["plant"]["backend"].update(backend_paths)
    env = build_env(config)
    if metadata["normalization"] != env.normalization():
        raise ValueError("observation normalization mismatch")
    output = fresh_output(output, config)
    trace, metrics = [], []
    for s, scenario in enumerate(config["evaluation"]["scenarios"]):
        options = {k: v for k, v in scenario.items() if k != "name"}
        options.update(split="test", episode=s)
        env.reset(seed=config["seed"], options=options)
        if env.trajectory is not None:
            # Generate once, then replay the exact same array for every controller.
            if env.inflow_trace is not None:
                env.inflow_trace.save(output / f"inflow_{s}.csv")
            options.pop("wind_trace_path", None)
            options["wind_trajectory"] = env.trajectory.copy()
        for mode in ("maddpg", "fixed", "p", "pi"):
            obs, _ = env.reset(seed=config["seed"] + config["evaluation"]["seed_offset"] + s,
                               options=options)
            baseline = None if mode == "maddpg" else PitchController(env, config["baselines"], mode)
            rows = []
            for _ in range(env.horizon):
                action = agent.act(obs) if baseline is None else baseline.act(obs)
                obs, reward, terminated, truncated, info = env.step(action)
                row = {"scenario": scenario["name"], "controller": mode,
                       **{k: info[k] for k in ("step", "time_s", "target_w", "farm_power_w", "error_w", "saturation_fraction", "action_change")},
                       "reward": float(reward[0])}
                for i in range(3):
                    row[f"power_{i+1}_w"] = float(info["power_w"][i])
                    row[f"ueff_{i+1}_m_s"] = float(info["effective_wind_m_s"][i])
                    row[f"heading_{i+1}_rad"] = float(info["heading_rad"][i])
                    for j, field in enumerate(("yaw_rad", "pitch_rad", "speed_rad_s")):
                        row[f"{field}_{i+1}"] = float(info["applied"][i, j])
                        row[f"action_{i+1}_{j+1}"] = float(info["executed_action"][i, j])
                for j, field in enumerate(("wind_m_s", "direction_rad", "ti")):
                    row[field] = float(info["wind"][j])
                rows.append(row)
                if terminated or truncated:
                    break
            trace.extend(rows)
            error = np.array([r["error_w"] for r in rows])
            metrics.append({"scenario": scenario["name"], "controller": mode,
                            "comparison_scope": "shared_enabled_channels" if not np.all(env.control_mask) else "complete_three_channel_schemes",
                            "source": config["plant"]["source"], "power_semantics": config["plant"]["power_semantics"],
                            "rmse_w": float(np.sqrt(np.mean(error**2))),
                            "mae_w": float(np.mean(np.abs(error))),
                            "mean_action_change": float(np.mean([r["action_change"] for r in rows])),
                            "mean_saturation_fraction": float(np.mean([r["saturation_fraction"] for r in rows])),
                            "mean_shortfall_w": float(np.mean(np.maximum(-error, 0)))})
    write_csv(output / "metrics.csv", metrics)
    write_csv(output / "trajectories.csv", trace)
    (output / "summary.txt").write_text(
        f"checkpoint={Path(checkpoint).resolve()}\nsource={config['plant']['source']}\npower_semantics={config['plant']['power_semantics']}\n"
        f"control_mask={env.control_mask.tolist()}; traditional_three_channel={config['baselines'].get('three_channel', False)}\n"
        "Shared wind, target, initial states and actuators. P/PI use configured schedules; not learned joint optimization.\n"
        "Target feasibility not certified; shortfall is reported, target never silently reduced.\n", encoding="utf-8")
    plot_results(output, trace, config)
    print(json.dumps(metrics, indent=2), flush=True)
    return metrics


def plot_results(output, trace, config):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for scenario in config["evaluation"]["scenarios"]:
        rows = [r for r in trace if r["scenario"] == scenario["name"]]
        fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
        for mode in ("maddpg", "fixed", "p", "pi"):
            part = [r for r in rows if r["controller"] == mode]
            axes[0].plot([r["time_s"] for r in part], [r["farm_power_w"]/1e6 for r in part], label=mode)
        part = [r for r in rows if r["controller"] == "maddpg"]
        times = [r["time_s"] for r in part]
        axes[0].plot(times, [r["target_w"]/1e6 for r in part], "k--", label="target")
        for i in range(3):
            axes[1].plot(times, [r[f"power_{i+1}_w"]/1e6 for r in part], label=f"T{i+1}")
        for j, name in enumerate(("yaw", "pitch", "speed")):
            axes[2].plot(times, [r[f"action_1_{j+1}"] for r in part], label=f"T1 {name}")
        for ax in axes:
            ax.legend(loc="best")
            ax.grid(alpha=0.2)
        axes[0].set_ylabel("Farm power [MW]")
        axes[1].set_ylabel("MADDPG turbine power [MW]")
        axes[2].set_ylabel("Normalized command")
        axes[2].set_xlabel("Control time [s]; quasi-static plant")
        fig.suptitle(f"{scenario['name']} | {config['plant']['source']}")
        fig.tight_layout()
        fig.savefig(output / f"{scenario['name']}.png", dpi=140)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("train", "evaluate"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    parser.add_argument("--checkpoint")
    args = parser.parse_args()
    if args.command == "train":
        train(load_config(args.config), args.output, args.checkpoint)
    else:
        if not args.checkpoint:
            parser.error("evaluate requires --checkpoint")
        evaluate(args.checkpoint, args.output)


if __name__ == "__main__":
    main()
