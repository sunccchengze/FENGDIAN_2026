"""Export wind statistics and replay the same wind/reference for P and optional PPO."""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import welch
import yaml

from optimization_control.environments.wind_generator import WindConfig, WindTrace, generate_wind, kaimal_psd, load_config
from optimization_control.environments.stochastic_turbine_env import StochasticTurbineEnv

DEFAULT_CONFIG = Path(__file__).parent / "configs" / "stochastic_wind_v1.yaml"


def replay(config, trace, policy=None):
    env = StochasticTurbineEnv(config, trace=trace)
    obs, _ = env.reset()
    rows = []
    while True:
        if policy is None:
            physical = obs * env.obs_scale
            action = np.array([np.clip(-2e-6 * (physical[4] - physical[0]), -0.5, 0.5), 0.0])
        else:
            action = policy(obs)
        obs, reward, done, truncated, info = env.step(action)
        rows.append({k: v for k, v in info.items() if k != "applied_action"} | {
            "pitch_rate_command_deg_s": float(info["applied_action"][0]),
            "speed_setpoint_rate_rad_s2": float(info["applied_action"][1]), "reward": reward})
        if done or truncated:
            break
    env.close()
    return pd.DataFrame(rows)


def policy_from_checkpoint(path, config):
    import torch
    from optimization_control.ppo_single_turbine.train import Agent
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if metadata["environment_config"] != config or metadata["policy_format"] != "tanh_squashed":
        raise ValueError("checkpoint config/policy mismatch; old 5D weights are unsupported")
    env = StochasticTurbineEnv(config)
    if metadata["observation_names"] != list(env.observation_names) or not np.allclose(metadata["obs_scale"], env.obs_scale):
        raise ValueError("checkpoint observation metadata mismatch")
    class Spaces:
        single_action_space = env.action_space
        single_observation_space = env.observation_space
    torch.set_num_threads(1)
    agent = Agent(Spaces())
    agent.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    agent.eval()
    def policy(obs):
        with torch.no_grad():
            return agent.get_deterministic_action(torch.as_tensor(obs)[None]).numpy()[0]
    return policy


def control_metrics(frame):
    error = frame.power_w - frame.reference_applied_w
    return {"rmse_kw": float(np.sqrt(np.mean(error**2)) / 1000),
            "mae_kw": float(np.mean(np.abs(error)) / 1000),
            "mean_abs_pitch_rate_deg_s": float(frame.pitch_rate_command_deg_s.abs().mean()),
            "unavailable_fraction": float(frame.target_exceeds_steady_availability.mean())}


def run(config, output, split="test", samples=32, model=None, replay_paths=None):
    if split == "train":
        raise ValueError("evaluation exports must use validation or test split")
    if samples < 4:
        raise ValueError("at least four independent wind records required")
    policy = policy_from_checkpoint(model, config) if model else None
    base = WindConfig(**config["wind"])
    supplied = [WindTrace.load(p) for p in replay_paths] if replay_paths else []
    for trace in supplied:
        if trace.metadata["split"] != split:
            raise ValueError("replay split does not match evaluation split")
        expected = asdict(base)
        recorded = asdict(WindConfig(**trace.metadata["config"]))
        expected.pop("scenario")
        recorded.pop("scenario")
        if expected != recorded:
            raise ValueError("replay wind configuration mismatch")
    output.mkdir(parents=True, exist_ok=False)
    saved = {"seed": 42, "environment_config": config, "split": split,
             "ensemble_records_per_scenario": samples, "model": str(model) if model else None,
             "replay_paths": [str(p.resolve()) for p in (replay_paths or [])]}
    (output / "config.yaml").write_text(yaml.safe_dump(saved, sort_keys=False), encoding="utf-8")
    (output / "summary.txt").write_text("Validation in progress. Synthetic wind only.\n", encoding="utf-8")
    (output / "metrics.csv").write_text("scenario,controller\n", encoding="utf-8")
    cases = [(str(i) + "_" + t.metadata["scenario"], t) for i, t in enumerate(supplied)] if supplied else [
        (name, generate_wind(replace(base, scenario=name), split=split, episode=0))
        for name in ("stationary", "ramp", "gust")]
    stats_fig, axes = plt.subplots(len(cases), 4, figsize=(18, 3.8 * len(cases)), squeeze=False)
    replay_fig, replay_axes = plt.subplots(len(cases), 2, figsize=(13, 3.8 * len(cases)), squeeze=False)
    results = []
    spectral_checks = []
    for row, (name, trace) in enumerate(cases):
        trace.save(output / f"wind_{name}.csv")
        ensemble_config = WindConfig(**trace.metadata["config"])
        ensemble = [generate_wind(ensemble_config, seed=trace.metadata["seed"], split=trace.metadata["split"],
                                  worker=trace.metadata["worker"], episode=i + 1000) for i in range(samples)]
        normalized_psds, ratios = [], []
        for member in ensemble:
            m = member.metadata
            freq, psd = welch(member.turbulence_m_s, fs=1 / base.dt_s, nperseg=256)
            theory = kaimal_psd(freq, m["mean_m_s"], m["mean_m_s"] * m["ti_requested"], base.length_scale_m)
            valid = (freq >= 0.03) & (freq <= 0.35) & (theory > 0)
            if np.any(valid):
                normalized_psds.append(psd[valid] / theory[valid])
            expected = m["expected_band_variance_m2_s2"]
            if expected > 0:
                ratios.append(np.mean(member.turbulence_m_s**2) / expected)
        ratio = float(np.median(np.mean(normalized_psds, axis=0))) if normalized_psds else 1.0
        variance_ratio = float(np.mean(ratios)) if ratios else 1.0
        spectral_checks.append({"scenario": name, "ensemble_psd_ratio": ratio,
                                "ensemble_mean_square_ratio": variance_ratio})
        axes[row, 0].plot(trace.time_s, trace.speed_m_s, lw=0.8, label="Total wind")
        axes[row, 0].plot(trace.time_s, trace.background_m_s + trace.event_m_s, label="Background + event")
        axes[row, 0].set(title=name, xlabel="Time (s)", ylabel="Wind (m/s)")
        axes[row, 0].legend(fontsize=8)
        axes[row, 1].hist(trace.turbulence_m_s, bins=30, density=True, alpha=0.7)
        axes[row, 1].set(xlabel="Turbulent component (m/s)", ylabel="Density")
        z = trace.turbulence_m_s - trace.turbulence_m_s.mean()
        autocorr = np.correlate(z, z, mode="full")[len(z)-1:]
        autocorr = autocorr / autocorr[0] if autocorr[0] > 0 else np.zeros_like(autocorr)
        axes[row, 2].plot(np.arange(min(61, len(autocorr))) * base.dt_s, autocorr[:61])
        axes[row, 2].set(xlabel="Lag (s)", ylabel="Autocorrelation")
        freq, psd = welch(trace.turbulence_m_s, fs=1 / base.dt_s, nperseg=256)
        m = trace.metadata
        theory = kaimal_psd(freq, m["mean_m_s"], m["mean_m_s"] * m["ti_requested"], base.length_scale_m)
        axes[row, 3].loglog(freq[1:], psd[1:], label="Single-record Welch")
        axes[row, 3].loglog(freq[1:], theory[1:], label="Kaimal target")
        axes[row, 3].set(xlabel="Frequency (Hz)", ylabel="PSD ((m/s)^2/Hz)")
        axes[row, 3].legend(fontsize=8)
        baseline = replay(config, trace)
        controllers = [("PController", baseline)]
        if policy:
            ppo = replay(config, trace, policy)
            np.testing.assert_array_equal(baseline.wind_speed_m_s, ppo.wind_speed_m_s)
            np.testing.assert_array_equal(baseline.reference_applied_w, ppo.reference_applied_w)
            controllers.append(("PPO", ppo))
        for label, frame in controllers:
            frame.to_csv(output / f"replay_{name}_{label}.csv", index=False)
            results.append({"scenario": name, "controller": label, **control_metrics(frame),
                            "wind_mean_m_s": float(trace.speed_m_s.mean()),
                            "background_ti_realized": float(trace.turbulence_m_s.std() / m["mean_m_s"]),
                            "requested_ti": m["ti_requested"], "rejected_attempts": m["rejected_attempts"],
                            "ensemble_psd_ratio": ratio, "ensemble_mean_square_ratio": variance_ratio})
            replay_axes[row, 0].plot(frame.time_s, frame.power_w / 1e6, label=label)
            replay_axes[row, 1].plot(frame.time_s, frame.pitch_deg, label=label)
        replay_axes[row, 0].plot(baseline.time_s, baseline.reference_applied_w / 1e6, "k--", label="Held reference")
        replay_axes[row, 0].set(title=name, xlabel="Time (s)", ylabel="Power (MW)")
        replay_axes[row, 1].set(xlabel="Time (s)", ylabel="Pitch (deg)")
        for ax in replay_axes[row]:
            ax.legend(fontsize=8)
    stats_fig.tight_layout()
    stats_fig.savefig(output / "wind_statistics.png", dpi=150)
    replay_fig.tight_layout()
    replay_fig.savefig(output / "control_replay.png", dpi=150)
    plt.close("all")
    pd.DataFrame(results).to_csv(output / "metrics.csv", index=False)
    summary = ("Synthetic single-point wind; assumptions, not measured site data or IEC full-field certification.\n"
               "TI requested is infinite-band stationary background; realized finite-record TI is not forced.\n"
               "No clipping or per-record renormalization; envelope rejection conditions the distribution.\n"
               "Each replay uses identical stored wind and action-independent reference.\n"
               "P baseline changes pitch only; PPO controls pitch and speed reference: not equal-authority algorithm comparison.\n"
               "Checkpoint smoke is not a trained-performance result.\n" + json.dumps(spectral_checks, indent=2))
    (output / "summary.txt").write_text(summary, encoding="utf-8")
    print(pd.DataFrame(results).to_string(index=False))
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--split", choices=("validation", "test"), default="test")
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--model", type=Path)
    p.add_argument("--replay", type=Path, nargs="+")
    args = p.parse_args()
    run(load_config(args.config), args.output_dir, args.split, args.samples, args.model, args.replay)
