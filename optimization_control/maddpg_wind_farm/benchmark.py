"""Frozen validation/test banks and physical-unit controller metrics.

Test traces can be generated before training, but evaluation requires an explicit
post-selection gate. Latency is excluded from deterministic model selection.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch

from .workflow import build_env
from .controllers import PitchController
from ..environments.farm_inflow import generate_inflow, InflowTrace

FAMILIES = ("fixed", "stationary", "ramp", "gust", "direction", "shortfall")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seed_for(master, stream, repeat):
    return int(np.random.SeedSequence([master, stream, repeat]).generate_state(1)[0])


def case_trace(config, family, *, split, episode):
    e = config["environment"]
    inflow = deepcopy(e["inflow"])
    inflow["speed"].update(scenario=family if family in ("stationary","ramp","gust") else "stationary",
                          gust_duration_s=min(40.0,e["horizon"]*e["dt_s"]/4))
    trace = generate_inflow(inflow,dt_s=e["dt_s"],horizon=e["horizon"],seed=42,split=split,episode=episode)
    if family in ("fixed","direction","shortfall"):
        # Slightly different fixed test points; no performance feedback involved.
        u = 5.5 if family == "shortfall" else 8.0 + .15*(episode%2) + (.05 if split == "test" else 0)
        trace.values[:,0] = u
        trace.components[:] = 0; trace.components[:,0] = u
        trace.values[:,1] = e["wind_direction_rad"]
        trace.values[:,2] = e["turbulence_intensity"]
        if family == "direction":
            trace.values[:,1] += .08*np.sin(2*np.pi*trace.time_s/(e["horizon"]*e["dt_s"]) + episode*.3)
        trace.metadata.update(override_family=family, override_wind_m_s=u,
                              speed_semantics="constant entrance speed for diagnostic or stress case")
    return trace


def freeze_bank(config, protocol, directory):
    offset=protocol.get("bank_episode_offset",20000)
    targets=protocol.get("bank_targets_w",[3e6])
    if not isinstance(offset,int) or offset<0 or not targets or any(not np.isfinite(t) or t<=0 for t in targets):
        raise ValueError("invalid bank episode offset or targets")
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=False)
    manifest={"version":"farm_benchmark_v1","seed":42,"cases":[]}
    for split in ("validation","test"):
        for family in FAMILIES:
            for j in range(protocol["cases_per_family"]):
                case_id=f"{split}_{family}_{j}"
                trace=case_trace(config,family,split=split,episode=offset+100*FAMILIES.index(family)+j)
                path=directory/f"{case_id}.csv"; trace.save(path)
                manifest["cases"].append({"id":case_id,"split":split,"family":family,"path":path.name,
                                           "csv_sha256":digest(path),"json_sha256":digest(path.with_suffix('.json')),
                                           "target_w":5e6 if family=="shortfall" else targets[j%len(targets)]})
    (directory/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return digest(directory/"manifest.json")


def load_cases(directory, split, *, allow_test=False, families=None):
    if split not in ("validation","test") or (split == "test" and not allow_test):
        raise ValueError("test evaluation is locked until selection is frozen")
    directory=Path(directory)
    manifest=json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    cases=[]
    for case in manifest["cases"]:
        if case["split"]!=split or (families is not None and case["family"] not in families): continue
        path=directory/case["path"]
        if digest(path)!=case["csv_sha256"] or digest(path.with_suffix('.json'))!=case["json_sha256"]:
            raise ValueError("frozen benchmark checksum mismatch")
        cases.append((case,InflowTrace.load(path)))
    if not cases: raise ValueError("empty benchmark selection")
    return cases


def evaluate_cases(config, cases, *, agent=None, baseline=None, timing=False, decomposition=False):
    if (agent is None)==(baseline is None): raise ValueError("choose one controller")
    rows=[]
    for case,trace in cases:
        env=build_env(config)
        obs,info=env.reset(seed=42,options={"wind_trajectory":trace.values,"target_w":case["target_w"]})
        controller=PitchController(env,config["baselines"],baseline) if baseline else None
        errors=[]; rewards=[]; saturation=[]; boundary=[]; latencies=[]; winds=[]
        motion=np.zeros(3); longest=streak=0
        heading=info["heading_rad"]; applied=info["applied"]
        if agent is not None:
            with torch.no_grad():
                o=torch.as_tensor(obs); a=torch.as_tensor(agent.act(obs))
                q=float(agent.critics[0](torch.cat((o.flatten(),a.flatten()))))
        else: q=0.0
        for _ in range(env.horizon):
            start=time.perf_counter_ns() if timing else 0
            action=agent.act(obs) if agent is not None else controller.act(obs)
            if timing: latencies.append((time.perf_counter_ns()-start)/1e6)
            obs,reward,done,_,info=env.step(action)
            delta=np.column_stack((info["heading_rad"]-heading,info["applied"][:,1:]-applied[:,1:]))
            if np.any(np.abs(delta)>np.asarray(env.config["rate_limits"])*env.dt+1e-7):
                raise AssertionError("actuator rate violation")
            motion+=np.abs(delta).sum(axis=0)
            heading,applied=info["heading_rad"],info["applied"]
            error=info["error_w"]; errors.append(error); rewards.append(float(reward[0]))
            if decomposition: winds.append(float(info["wind"][0]))
            saturation.append(info["saturation_fraction"])
            boundary.append(np.mean(np.abs(info["executed_action"][:,env.control_mask])>.98))
            streak=streak+1 if error < -.02*env.target else 0; longest=max(longest,streak)
            if done: break
        error=np.asarray(errors)
        rows.append({"case_id":case["id"],"split":case["split"],"family":case["family"],
                     "target_w":env.target,"rmse_w":float(np.sqrt(np.mean(error**2))),
                     "mae_w":float(np.mean(np.abs(error))),"max_abs_error_w":float(np.max(np.abs(error))),
                     "shortfall_duration_s":float(np.sum(error<-.02*env.target)*env.dt),
                     "longest_shortfall_s":longest*env.dt,"mean_shortfall_w":float(np.maximum(-error,0).mean()),
                     "yaw_travel_rad":motion[0],"pitch_travel_rad":motion[1],"rotor_speed_total_variation_rad_s":motion[2],
                     "saturation_fraction":float(np.mean(saturation)),"boundary_fraction":float(np.mean(boundary)),
                     "q_initial":q,"discounted_return":float(np.dot(np.power(agent.config.gamma if agent else config["algorithm"]["gamma"],np.arange(len(rewards))),rewards)),
                     "inference_median_ms":float(np.median(latencies)) if timing else 0.0,
                     "inference_p95_ms":float(np.quantile(latencies,.95)) if timing else 0.0,
                     "source":config["plant"]["source"],"power_semantics":config["plant"]["power_semantics"]})
        if decomposition:
            from .reachability import error_components, upper_bound
            rows[-1].update(error_components(errors,upper_bound(env,winds),env.target))
            rows[-1]["tight_upper_bound_fraction"]=float(np.mean(np.asarray(winds)<=11.4))
    return rows


def selection_score(rows, families):
    if not rows or any(r["split"]!="validation" for r in rows):
        raise ValueError("selection accepts validation results only")
    means=[]
    for family in families:
        values=[r["rmse_w"] for r in rows if r["family"]==family]
        if not values or not np.all(np.isfinite(values)): raise ValueError("missing/nonfinite validation family")
        means.append(float(np.mean(values)))
    return float(np.mean(means))


def update_best(best, rows, families, step, checkpoint):
    score=selection_score(rows,families)
    if best is None or score<best["score_w"]:
        return {"score_w":score,"step":step,"checkpoint":str(checkpoint)}
    return best
