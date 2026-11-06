"""Predeclared validation interventions and local model probes; never uses test."""
from copy import deepcopy
import itertools
from pathlib import Path

from .anchor_closeout import context, read_json, write_json, write_csv, read_csv, rollout, recompute, sha, make_env, save_job, load_job


def intervene(total, parent, name):
    import numpy as np
    result=np.asarray(total).copy()
    channel={"parent_yaw":0,"parent_pitch":1,"parent_speed":2}
    if name=="parent_all": return np.asarray(parent).copy()
    if name not in channel: raise ValueError("unknown parent intervention")
    result[:,channel[name]]=parent[:,channel[name]]
    return result


class ParentSwap:
    def __init__(self,final,parent,name):
        self.final,self.parent,self.name=final,parent,name

    def act(self,obs):
        return intervene(self.final.act(obs),self.parent.act(obs),self.name)


class OffsetPolicy:
    def __init__(self,parent,cfg,channel,offset):
        import numpy as np
        self.parent,self.channel,self.offset=parent,channel,offset
        self.width=np.asarray(cfg["environment"]["action_high"])-cfg["environment"]["action_low"]

    def act(self,obs):
        import numpy as np
        action=self.parent.act(obs).copy()
        if self.channel is not None:
            action[:,self.channel]=np.clip(action[:,self.channel]+2*self.offset/self.width[self.channel],-1,1)
        return action


def trajectory_differences(left,right):
    import numpy as np
    if [(r["case_id"],int(r["step"])) for r in left]!=[(r["case_id"],int(r["step"])) for r in right]:
        raise ValueError("takeover trace case identity mismatch")
    applied=[f"{name}_{i}" for i in (1,2,3) for name in ("heading","pitch","speed")]
    applied=[name+"_rad" if name.startswith("heading") else name for name in applied]
    command=[f"command_{i}_{j}" for i in (1,2,3) for j in range(3)]
    def maximum(keys):
        return max(abs(float(a[k])-float(b[k])) for a,b in zip(left,right) for k in keys)
    return dict(max_applied_difference=maximum(applied),max_action_difference=maximum(command),max_power_difference_w=maximum(["farm_power_w"]))


def takeover(root,cfg,source,selection,bank):
    import numpy as np
    import torch
    from .anchor_algorithm import load_policy
    records=[]
    old=read_json(Path(cfg["original_workspace"])/"optimization_control/experiments/20261023_residual_random_control/selection.json")
    jobs=[]
    for r in old["results"]:
        if r["stage"] in ("pitch_speed","all"):
            jobs.append((r["stage"],r["run_id"],r["lineage"]["parent_checkpoint"],r["initial"]))
    for r in selection["results"]:
        if r["stage"]=="anchor": jobs.append(("anchor",r["run_id"],r["lineage"]["parent_checkpoint"],r["initial"]))
    for stage,run,parent_path,child_path in jobs:
        parent,pm=load_policy(parent_path); child,cm=load_policy(child_path)
        maximum=0.
        for field in ("obs","next_obs"):
            for kind in ("actors","target_actors"):
                for i,(pa,ca) in enumerate(zip(getattr(parent,kind),getattr(child,kind))):
                    for start in range(0,parent.replay.size,4096):
                        x=torch.tensor(parent.replay.data[field][start:min(start+4096,parent.replay.size),i])
                        with torch.no_grad(): error=(parent.policy(pa,x)-child.policy(ca,x)).abs().max().item()
                        maximum=max(maximum,error)
        rows_a,trace_a,_=rollout(pm["config"],bank,agent=parent)
        rows_b,trace_b,_=rollout(cm["config"],bank,agent=child)
        diff=trajectory_differences(trace_a,trace_b)
        rmse=max(abs(a["rmse_w"]-b["rmse_w"]) for a,b in zip(rows_a,rows_b))
        passed=maximum<=cfg["takeover"]["action_atol"] and diff["max_action_difference"]<=cfg["takeover"]["action_atol"] and diff["max_applied_difference"]<=cfg["takeover"]["applied_atol"] and max(rmse,diff["max_power_difference_w"])<=cfg["takeover"]["power_and_rmse_atol_w"]
        record=dict(stage=stage,run_id=run,parent_checkpoint=parent_path,initial_checkpoint=child_path,max_online_target_replay_action_difference=maximum,max_rmse_difference_w=rmse,**diff,passed=bool(passed))
        records.append(record)
        print("Takeover",stage,run,passed,maximum,diff,flush=True)
    write_csv(root/"diagnostic/takeover.csv",records)
    write_json(root/"diagnostic/takeover.json",dict(checks=records,all_passed=all(r["passed"] for r in records),case_rollouts=108,environment_steps=13824))


def scan_model(config,states,offsets):
    import numpy as np
    predictor=make_env(config).plant.predictor
    inputs,tags=[],[]
    for state in states:
        base=np.asarray(state["physical"],dtype=float)
        for channel,key in ((0,"yaw_offsets_deg"),(2,"speed_offsets_rad_s")):
            for which in (0,1,2,3):
                indices=[3+channel*3+i for i in (range(3) if which==3 else [which])]
                values=offsets[key]
                for offset in values:
                    physical_offset=float(np.deg2rad(offset)) if channel==0 else float(offset)
                    changed=base.copy()
                    lo,hi=((-0.4,0.4) if channel==0 else (0.6,1.267))
                    changed[indices]=np.clip(changed[indices]+physical_offset,lo,hi)
                    inputs.append(changed)
                    tags.append(dict(case_id=state["case_id"],step=state["step"],target_w=state["target_w"],channel="yaw" if channel==0 else "speed",turbine="all" if which==3 else str(which+1),offset=offset,offset_unit="deg" if channel==0 else "rad/s",input_clipped=bool(np.any(np.abs(changed[indices]-base[indices]-physical_offset)>1e-7))))
    x=np.asarray(inputs); outputs=[]
    for start in range(0,len(x),2048): outputs.extend(predictor(x[start:start+2048]))
    y=np.asarray(outputs)
    bases={}
    for tag,out in zip(tags,y):
        if tag["offset"]==0:
            bases[(tag["case_id"],tag["step"],tag["channel"],tag["turbine"])]=out
    rows=[]
    for tag,out in zip(tags,y):
        base=bases[(tag["case_id"],tag["step"],tag["channel"],tag["turbine"])]
        delta=out-base
        rows.append(dict(**tag,farm_power_w=float(out[:3].sum()),baseline_power_w=float(base[:3].sum()),farm_delta_w=float(delta[:3].sum()),max_turbine_power_delta_w=float(np.abs(delta[:3]).max()),max_effective_wind_delta_m_s=float(np.abs(delta[3:]).max()),tracking_absolute_error_change_w=float(abs(out[:3].sum()-tag["target_w"])-abs(base[:3].sum()-tag["target_w"])),**{f"power_delta_{i+1}_w":float(delta[i]) for i in range(3)}))
    return rows


def diagnose(root):
    import numpy as np
    from . import random_wind_training as shared
    from .anchor_algorithm import load_policy
    from .residual_stability_diagnostic import MixedPolicy
    cfg,source,_,selection=context(root)
    if (root/"diagnostic/complete.json").exists():
        raise ValueError("diagnostic already frozen; use existing artifacts")
    if (root/"test/metrics.csv").exists():
        raise ValueError("diagnostic must not be redesigned after reading current test")
    bank=shared.cases(source,"validation")
    assert len(bank)==6
    # Prove new cached rollout matches the frozen evaluator on one full case.
    first=selection["results"][0]
    agent,meta=load_policy(first["initial"])
    expected,trace=shared.rollout(meta["config"],bank[:1],agent=agent,capture=True)
    actual,capture,_=rollout(meta["config"],bank[:1],agent=agent)
    np.testing.assert_equal(expected,actual); np.testing.assert_equal(trace,capture)
    write_json(root/"diagnostic/rollout_equivalence.json",dict(full_case_metrics_and_128_trace_rows_exact=True))
    takeover(root,cfg,source,selection,bank)
    aggregates,all_metrics,local_rows=[],[],[]
    for r in selection["results"]:
        selected,sm=load_policy(r["best"]["checkpoint"]); final,fm=load_policy(r["final"]); parent,pm=load_policy(r["lineage"]["parent_checkpoint"])
        variants=[("".join(p),None) for p in itertools.product("SF",repeat=3)]
        variants += [(name,name) for name in ("zero_yaw","zero_speed","zero_both","parent_yaw","parent_pitch","parent_speed","parent_all")]
        for name,ablation in variants:
            folder=root/"diagnostic"/f"{r['stage']}_{r['run_id']}_{name}"
            if folder.exists():
                rows,traces=load_job(folder); summary=read_json(folder/"corrections.json")
            else:
                if name.startswith("parent_"):
                    policy=ParentSwap(final,parent,name)
                else:
                    policy=MixedPolicy(selected,final,r["config"],name if ablation is None else "FFF",ablation)
                rows,traces,states=rollout(r["config"],bank,agent=policy,snapshots=cfg["diagnostic"]["snapshot_steps"])
                summary=policy.summary() if hasattr(policy,"summary") else {}
                save_job(folder,rows,traces,summary)
                # Only pure endpoints are used for local probes; same validation states.
                if name in ("SSS","FFF","parent_all"):
                    write_json(folder/"local_states.json",states)
            tags=dict(stage=r["stage"],run_id=r["run_id"],variant=name)
            recompute(rows,traces,("case_id",))
            aggregates.append(dict(**tags,mean_rmse_w=float(np.mean([float(v["rmse_w"]) for v in rows])),worst_rmse_w=max(float(v["rmse_w"]) for v in rows),**{k:float(v) for k,v in summary.items()}))
            all_metrics.extend(dict(**tags,**row) for row in rows)
            print("Validation intervention",r["stage"],r["run_id"],name,round(aggregates[-1]["mean_rmse_w"]/1000,2),flush=True)
        for name in ("SSS","FFF","parent_all"):
            folder=root/"diagnostic"/f"{r['stage']}_{r['run_id']}_{name}"
            states=read_json(folder/"local_states.json")
            local_rows.extend(dict(stage=r["stage"],run_id=r["run_id"],endpoint=name,**row) for row in scan_model(r["config"],states,cfg["diagnostic"]))
    assert len(aggregates)==90 and len(all_metrics)==540
    # heterogeneous keys require a common CSV schema.
    keys=list(dict.fromkeys(k for row in aggregates for k in row))
    write_csv(root/"diagnostic/metrics.csv",[{k:row.get(k,"") for k in keys} for row in aggregates])
    write_csv(root/"diagnostic/case_metrics.csv",all_metrics)
    write_csv(root/"diagnostic/local_response.csv",local_rows)
    offset_rows=[]
    offsets=cfg["diagnostic"]
    for r in selection["results"]:
        if r["stage"]!="anchor":continue
        parent,meta=load_policy(r["lineage"]["parent_checkpoint"])
        variants=[("reference",None,0.)]
        variants += [(f"speed_{v:+.2f}",2,v) for v in offsets["speed_offsets_rad_s"] if v]
        variants += [(f"yaw_{v:+.0f}",0,float(np.deg2rad(v))) for v in offsets["yaw_offsets_deg"] if v]
        for name,channel,offset in variants:
            folder=root/"diagnostic"/f"offset_{r['run_id']}_{name}"
            if folder.exists(): rows,traces=load_job(folder)
            else:
                rows,traces,_=rollout(meta["config"],bank,agent=OffsetPolicy(parent,meta["config"],channel,offset))
                save_job(folder,rows,traces)
            recompute(rows,traces,("case_id",))
            offset_rows.extend(dict(run_id=r["run_id"],variant=name,channel="none" if channel is None else "yaw" if channel==0 else "speed",offset_physical=offset,**row) for row in rows)
            print("Validation fixed offset",r["run_id"],name,round(np.mean([float(row["rmse_w"]) for row in rows])/1000,2),flush=True)
    assert len(offset_rows)==234
    write_csv(root/"diagnostic/fixed_offset_cases.csv",offset_rows)
    context(root)
    complete=dict(seed=42,split="validation",test_metrics_read=False,additional_formal_training_steps=0,
        intervention_variants=90,intervention_case_rollouts=540,intervention_environment_steps=69120,
        local_response_rows=len(local_rows),fixed_offset_variants=39,fixed_offset_case_rollouts=234,fixed_offset_environment_steps=29952,
        takeover=read_json(root/"diagnostic/takeover.json"),rollout_equivalence_extra_environment_steps=256,
        attribution="Current-state channel interactions are non-additive; local sensitivity is not a physical or closed-loop gain certificate")
    complete["artifact_hashes"]={str(p.relative_to(root/"diagnostic")):sha(p) for p in (root/"diagnostic").rglob("*") if p.is_file()}
    write_json(root/"diagnostic/complete.json",complete)
    print("Validation diagnostic frozen",complete,flush=True)
