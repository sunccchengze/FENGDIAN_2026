"""Locate the newly observed precision difference without changing frozen code."""
import argparse
from pathlib import Path


def run(root):
    import numpy as np
    from .anchor_closeout import context, read_json, make_env, sha, write_json, write_csv
    from .anchor_algorithm import load_policy
    from . import random_wind_training as shared
    cfg,_,_,_=context(root)
    source=Path(cfg["original_workspace"])/"optimization_control/experiments/20261023_residual_random_control"
    old=read_json(source/"selection.json")
    bank=shared.cases(Path(cfg["source_experiment"]),"validation")[:1]
    out=root/"audit/takeover_precision"
    out.mkdir(exist_ok=False)
    rows=[]
    for r in old["results"]:
        if r["stage"]!="pitch_speed":continue
        parent,pm=load_policy(r["lineage"]["parent_checkpoint"]); child,cm=load_policy(r["initial"])
        env=make_env(pm["config"]); child_env=make_env(cm["config"])
        case,wind=bank[0]
        env.initial=np.asarray(pm["config"]["environment"]["initial_operating_point"],float).copy()
        env.initial[1]=case["initial_pitch_rad"]
        obs,_=env.reset(seed=42,options=dict(wind_trajectory=wind.values,target_w=case["target_w"]))
        for step in range(env.horizon):
            pa,ca=parent.act(obs),child.act(obs)
            child_env.effective_wind=env.effective_wind.copy()
            projected_parent,projected_child=env.project_action(pa),child_env.project_action(ca)
            scale,slope,low,high=child.config.residual_speed_schedule
            quantized_wind=obs[:,1]*scale
            # float32 Torch composition and environment's physical-wind schedule
            # use mathematically equivalent expressions with different inputs.
            for i in range(3):
                rows.append(dict(run_id=r["run_id"],case_id=case["id"],step=step,turbine=i+1,
                    same_obs_requested_action_max_difference=float(np.abs(pa-ca).max()),
                    requested_speed_normalized=float(pa[i,2]),projected_parent_speed_normalized=float(projected_parent[i,2]),projected_child_speed_normalized=float(projected_child[i,2]),
                    projection_delta=float(projected_parent[i,2]-projected_child[i,2]),effective_wind_m_s=float(env.effective_wind[i]),
                    reconstructed_effective_wind_m_s=float(quantized_wind[i]),effective_wind_quantization_error_m_s=float(quantized_wind[i]-env.effective_wind[i])))
            obs,_,_,_,_=env.step(pa)
    summary=dict(seed=42,case=bank[0][0]["id"],environment_steps=384,additional_formal_training_steps=0,test_read=False,
        max_same_obs_requested_action_difference=max(r["same_obs_requested_action_max_difference"] for r in rows),
        max_projection_delta=max(abs(r["projection_delta"]) for r in rows),
        max_effective_wind_quantization_error_m_s=max(abs(r["effective_wind_quantization_error_m_s"]) for r in rows),
        nonzero_projection_rows=sum(r["projection_delta"]!=0 for r in rows),rows=len(rows),
        explanation="Inactive speed is recomputed from physical effective wind in environment projection; active zero-head speed uses float32 quantized observation. Same-observation policy equality does not imply identical projected commands.",
        code_sha256=sha(__file__),protocol_sha256=sha(Path(__file__).with_name("ANCHOR_TAKEOVER_PRECISION.md")),
        original_strict_takeover_failures_preserved=True)
    write_csv(out/"metrics.csv",rows); write_json(out/"summary.json",summary)
    context(root)
    print(summary,flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--output",required=True); ap.add_argument("--origin",default=".")
    args=ap.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path(args.origin)/".venv/pinn_tf216")
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    run(Path(args.output).resolve())
