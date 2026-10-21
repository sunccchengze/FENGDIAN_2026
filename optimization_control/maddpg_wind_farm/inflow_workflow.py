"""Validate entrance spectra, exact file replay and shared-controller scenarios."""

import argparse
from copy import deepcopy
from pathlib import Path
import json
import numpy as np
from scipy.signal import welch
import torch

from .workflow import load_config, build_env, make_agent, fresh_output, write_csv
from .algorithm import MADDPG
from .controllers import PitchController
from .diagnostics import MASKS
from ..environments.farm_inflow import generate_inflow, InflowTrace
from ..environments.wind_generator import kaimal_psd

DEFAULT = Path(__file__).parent / "configs" / "stochastic_inflow.yaml"


def replay(config, trace, mode, agent=None, path=None):
    env = build_env(config)
    options = {"wind_trace_path":str(path)} if path else {"wind_trajectory":trace.values}
    obs, info = env.reset(seed=42, options=options)
    policy = make_agent(config, env) if mode == "initial_maddpg" else agent
    baseline = PitchController(env, config["baselines"], mode) if mode in ("fixed", "p", "pi") else None
    rows = []
    heading = info["heading_rad"]
    applied = info["applied"]
    max_rates = np.zeros(3)
    for _ in range(env.horizon):
        action = baseline.act(obs) if baseline is not None else policy.act(obs)
        obs, _, done, _, info = env.step(action)
        changes = np.column_stack((info["heading_rad"]-heading, info["applied"][:,1:]-applied[:,1:]))
        rates = np.max(np.abs(changes), axis=0)/env.dt
        max_rates = np.maximum(max_rates, rates)
        if np.any(rates > np.asarray(env.config["rate_limits"])+1e-7):
            raise AssertionError("physical actuator rate violation")
        heading, applied = info["heading_rad"], info["applied"]
        row = {"time_s":info["time_s"],"wind_m_s":info["wind"][0],"direction_rad":info["wind"][1],
               "background_ti":info["wind"][2],"target_w":info["target_w"],"farm_power_w":info["farm_power_w"],
               "error_w":info["error_w"],"saturation_fraction":info["saturation_fraction"]}
        for i in range(3):
            row[f"heading_{i+1}_rad"] = info["heading_rad"][i]
            row[f"power_{i+1}_w"] = info["power_w"][i]
            row[f"ueff_{i+1}_m_s"] = info["effective_wind_m_s"][i]
            for j, field in enumerate(("gamma_rad", "beta_rad", "omega_rad_s")):
                row[f"{field}_{i+1}"] = info["applied"][i,j]
                row[f"command_{i+1}_{j+1}"] = info["executed_action"][i,j]
        rows.append(row)
        if done:
            break
    error = np.array([r["error_w"] for r in rows])
    stats = {"rmse_w":float(np.sqrt(np.mean(error**2))), "mae_w":float(np.mean(np.abs(error))),
             "mean_shortfall_w":float(np.mean(np.maximum(-error,0))),
             "max_heading_rate_rad_s":max_rates[0],"max_pitch_rate_rad_s":max_rates[1],
             "max_rotor_acceleration_rad_s2":max_rates[2],
             "feasibility":"not_certified_target_never_reduced"}
    return rows, stats


def run(config, output, samples=64, checkpoint=None):
    if samples < 32:
        raise ValueError("spectral validation requires at least 32 independent records")
    torch.set_num_threads(1)
    agent = None
    if checkpoint:
        agent, meta = MADDPG.load(checkpoint)
        if meta["normalization"] != build_env(config).normalization():
            raise ValueError("checkpoint normalization or control permissions mismatch")
        if meta["config"]["plant"] != config["plant"] or meta["config"]["environment"] != config["environment"]:
            raise ValueError("checkpoint physical environment mismatch")
    root = fresh_output(output, dict(config, verification={"samples_per_scenario":samples,"checkpoint":str(checkpoint)}))
    results, checks, traces, spectral = [], [], {}, []
    e = config["environment"]
    for number, scenario in enumerate(("stationary", "ramp", "gust")):
        inflow = deepcopy(e["inflow"]); inflow["speed"]["scenario"] = scenario
        trace = generate_inflow(inflow,dt_s=e["dt_s"],horizon=e["horizon"],split="test",episode=number)
        path = root / f"wind_{scenario}.csv"
        trace.save(path); loaded = InflowTrace.load(path)
        np.testing.assert_array_equal(trace.values,loaded.values)
        np.testing.assert_array_equal(trace.components,loaded.components)
        ratios, variance_ratios, rejected = [], [], []
        for episode in range(1000,1000+samples):
            member = generate_inflow(inflow,dt_s=e["dt_s"],horizon=e["horizon"],split="validation",episode=episode)
            m = member.metadata["speed_metadata"]
            freq, psd = welch(member.components[:,1],fs=1/e["dt_s"],nperseg=min(256,len(member.time_s)))
            theory = kaimal_psd(freq,m["mean_m_s"],m["mean_m_s"]*m["ti_requested"],inflow["speed"]["length_scale_m"])
            band = (freq>=.03)&(freq<=.35)&(theory>0)
            if not np.any(band) or m["expected_band_variance_m2_s2"] <= 0:
                raise ValueError("spectral validation needs positive TI and resolved frequency band")
            ratios.append(psd[band]/theory[band])
            variance_ratios.append(np.mean(member.components[:,1]**2)/m["expected_band_variance_m2_s2"])
            rejected.append(m["rejected_attempts"])
        spectral.append({"scenario":scenario,"ensemble_psd_ratio":float(np.median(np.mean(ratios,axis=0))),
                         "ensemble_mean_square_ratio":float(np.mean(variance_ratios)),
                         "total_rejected_attempts":int(sum(rejected))})
        if not .8 < spectral[-1]["ensemble_psd_ratio"] < 1.2 or not .75 < spectral[-1]["ensemble_mean_square_ratio"] < 1.25:
            raise AssertionError(f"spectral acceptance failed: {spectral[-1]}")
        for name, mask in MASKS.items():
            cfg = deepcopy(config); cfg["environment"]["control_mask"] = mask
            modes = ["initial_maddpg","fixed","p","pi"] + (["trained_maddpg"] if agent is not None and name == "all" else [])
            for mode in modes:
                rows, stats = replay(cfg,loaded,mode,agent,path=path)
                again, _ = replay(cfg,trace,mode,agent)
                if rows != again:
                    raise AssertionError("file replay differs from in-memory run")
                np.testing.assert_array_equal(np.array([[r[k] for k in ("wind_m_s","direction_rad","background_ti")] for r in rows]),
                                               trace.values[1:].astype(np.float32))
                write_csv(root/f"{scenario}_{name}_{mode}.csv",rows)
                result = dict(scenario=scenario, channels=name, controller=mode,
                              comparison_scope="same_enabled_channels" if name != "all" else "complete_three_channel_schemes",
                              source=config["plant"]["source"],power_semantics=config["plant"]["power_semantics"],
                              **stats,**{k:v for k,v in spectral[-1].items() if k!="scenario"})
                results.append(result)
                if name == "all": traces[scenario,mode] = rows
        checks.append({"scenario":scenario,"disk_replay_exact":True,"all_controllers_same_inflow":True,
                       "actuator_rates_passed":True,**spectral[-1]})
    write_csv(root / "metrics.csv",results)
    (root/"summary.txt").write_text(
        "Command: python -m optimization_control.maddpg_wind_farm.inflow_workflow --output <new-dir> --checkpoint <optional>\n"
        +json.dumps(checks,indent=2)+"\nMock does not model direction/TI wake physics. No spatial field or physical superiority claim.\n"
        "Yaw command restricted to +/-0.45 rad in this config; PINN gamma domain remains +/-0.524 rad.\n"
        "This headroom covers designed slow directions, not arbitrary direction jumps; OOD always raises.\n",encoding="utf-8")
    plot(root, traces)
    print(json.dumps(checks,indent=2),flush=True)
    return results


def plot(root, traces):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3,3,figsize=(16,10))
    for i, name in enumerate(("stationary","ramp","gust")):
        one=traces[name,"pi"]
        times=[r["time_s"] for r in one]
        axes[i,0].plot(times,[r["wind_m_s"] for r in one]); axes[i,0].set_ylabel(f"{name}\nInlet wind [m/s]")
        axes[i,1].plot(times,np.rad2deg(np.unwrap([r["direction_rad"] for r in one])),label="Wind direction")
        axes[i,1].plot(times,np.rad2deg([r["heading_1_rad"] for r in one]),label="PI T1 heading")
        axes[i,1].set_ylabel("Angle [deg]"); axes[i,1].legend()
        for (scenario,mode),rows in traces.items():
            if scenario == name:
                axes[i,2].plot(times,[r["farm_power_w"]/1e6 for r in rows],label=mode)
        axes[i,2].plot(times,[r["target_w"]/1e6 for r in one],"k--",label="Target")
        axes[i,2].set_ylabel("Farm power [MW]"); axes[i,2].legend(fontsize=8)
        for ax in axes[i]: ax.grid(alpha=.2); ax.set_xlabel("Time [s]")
    fig.suptitle("Random entrance / shared actuator replay | coupled integration mock")
    fig.tight_layout(); fig.savefig(root/"inflow_and_controls.png",dpi=140); plt.close(fig)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",default=str(DEFAULT))
    parser.add_argument("--output",required=True)
    parser.add_argument("--samples",type=int,default=64)
    parser.add_argument("--checkpoint")
    args=parser.parse_args()
    run(load_config(args.config),args.output,args.samples,args.checkpoint)
