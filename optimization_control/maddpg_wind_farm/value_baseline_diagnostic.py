"""Read-only replay audit of action-independent infeasibility reward offsets."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from .algorithm import MADDPG
from .benchmark import digest
from .reachability import upper_bound
from .stable_workflow import training_options
from .workflow import build_env, fresh_output, write_csv


def reward_offset(env,wind,target):
    """Current exogenous entrance/target only; never use policy-dependent power."""
    target=np.asarray(target,dtype=float)
    if np.any(~np.isfinite(target)) or np.any(target<=0): raise ValueError("positive finite target required")
    floor=np.maximum(target-upper_bound(env,wind),0)
    return env.config.get("reward_scale",1.0)*(floor/float(env.rated.sum()))**2


def returns_by_episode(values,horizon,gamma):
    values=np.asarray(values,dtype=float)
    if values.ndim!=1 or horizon<=0 or len(values)%horizon or not 0<=gamma<=1:
        raise ValueError("complete fixed-length episodes required")
    a=values.reshape(-1,horizon); out=np.zeros_like(a)
    for t in range(horizon-1,-1,-1): out[:,t]=a[:,t]+(gamma*out[:,t+1] if t+1<horizon else 0)
    return out.ravel()


def replay_exogenous(agent,meta):
    cfg=meta["config"]; identity=meta["identity"]; p=identity["protocol"]
    env=build_env(cfg); n=agent.replay.size
    if n!=meta["steps"] or n>=agent.replay.capacity or n!=meta["episodes"]*env.horizon:
        raise ValueError("audit requires complete, unwrapped replay from episode-boundary checkpoint")
    data={k:v[:n] for k,v in agent.replay.data.items()}
    expected_done=np.zeros(n); expected_done[env.horizon-1::env.horizon]=1
    if not np.array_equal(data["terminated"][:,0],expected_done): raise ValueError("invalid episode boundary")
    winds=[]; targets=[]
    for ep in range(meta["episodes"]):
        options=training_options(cfg,p,identity["phase"],ep,identity["run_id"])
        winds.extend(np.asarray(options["wind_trajectory"],dtype=np.float32)[1:,0])
        targets.extend([options["target_w"]]*env.horizon)
    winds=np.asarray(winds,dtype=float); targets=np.asarray(targets,dtype=float)
    if not np.allclose(winds,data["next_obs"][:,0,10]*env.wind_scale,atol=2e-6,rtol=0):
        raise ValueError("reconstructed wind disagrees with replay")
    if not np.allclose(targets,data["next_obs"][:,0,8]*env.rated.sum(),atol=1,rtol=0):
        raise ValueError("reconstructed target disagrees with replay")
    if not np.all(data["rewards"]==data["rewards"][:,0:1]): raise ValueError("expected shared reward")
    return env,data,winds,targets


def critic_values(agent,data):
    q=[]; nq=[]
    with torch.no_grad():
        for start in range(0,len(data["obs"]),256):
            b={k:torch.as_tensor(v[start:start+256]) for k,v in data.items()}
            x=torch.cat((b["obs"].flatten(1),b["actions"].flatten(1)),dim=1)
            next_actions=torch.stack([agent.policy(a,b["next_obs"][:,i]) for i,a in enumerate(agent.target_actors)],dim=1)
            nx=torch.cat((b["next_obs"].flatten(1),next_actions.flatten(1)),dim=1)
            q.append(torch.cat([m(x) for m in agent.critics],dim=1).numpy())
            nq.append(torch.cat([m(nx) for m in agent.target_critics],dim=1).numpy())
    return np.concatenate(q).astype(float),np.concatenate(nq).astype(float)


def audit_checkpoint(path):
    agent,meta=MADDPG.load(path); env,data,winds,targets=replay_exogenous(agent,meta)
    raw=data["rewards"][:,0].astype(float); offset=reward_offset(env,winds,targets); centered=raw+offset
    if np.any(centered>5e-5): raise AssertionError("offset exceeds original nonpositive tracking reward")
    gamma=agent.config.gamma; c=returns_by_episode(offset,env.horizon,gamma)
    next_c=np.zeros_like(c); next_c[:-1]=c[1:]; next_c[data["terminated"][:,0]==1]=0
    q,nq=critic_values(agent,data); done=data["terminated"].astype(float)
    td=raw[:,None]+gamma*(1-done)*nq-q
    centered_td=centered[:,None]+gamma*(1-done)*(nq+next_c[:,None])-(q+c[:,None])
    if not np.allclose(td,centered_td,atol=1e-10,rtol=0): raise AssertionError("inconsistent value-coordinate shift")
    ret=returns_by_episode(raw,env.horizon,gamma); centered_ret=returns_by_episode(centered,env.horizon,gamma)
    if not np.allclose(centered_ret-ret,c,atol=1e-10,rtol=0): raise AssertionError("return shift failed")
    rows=[]
    terminal=data["terminated"][:,0]==1
    buckets=(("all",np.ones(len(raw),bool)),("positive_floor",offset>0),("zero_floor",offset==0),
             ("terminal",terminal),("positive_floor_terminal",(offset>0)&terminal),
             ("positive_floor_nonterminal",(offset>0)&~terminal))
    for name,mask in buckets:
        if not mask.any(): continue
        rms=lambda a:float(np.sqrt(np.mean(np.asarray(a)[mask]**2)))
        rows.append(dict(bucket=name,samples=int(mask.sum()),sample_fraction=float(mask.mean()),
            mean_reward=float(raw[mask].mean()),reward_rms=rms(raw),centered_reward_rms=rms(centered),
            mean_offset=float(offset[mask].mean()),offset_fraction_abs_reward=float(offset[mask].sum()/np.abs(raw[mask]).sum()),
            return_rms=rms(ret),centered_return_rms=rms(centered_ret),q_rms=rms(q),
            td_rms=rms(td),td_squared_share=float(np.square(td[mask]).sum()/np.square(td).sum()),
            consistent_td_shift_max_error=float(np.max(np.abs(td[mask]-centered_td[mask])))))
    return rows


def run(source,output):
    torch.set_num_threads(1)
    source=Path(source); selection=json.loads((source/"selection.json").read_text(encoding="utf-8"))
    paths={name:[r["final"] for r in selection["results"][name]] for name in ("baseline","stratified")}
    hashes={p:digest(p) for group in paths.values() for p in group}
    if any(selection["hashes"][p]!=h for p,h in hashes.items()): raise ValueError("changed source checkpoint")
    out=fresh_output(output,dict(seed=42,purpose="offline_training_replay_diagnosis_not_performance_test",source=str(source.resolve()),
        source_selection_sha256=digest(source/"selection.json"),checkpoint_hashes=hashes,
        intervention="analysis_only_r_plus_action_independent_infeasibility_floor_squared",new_training_steps=0,
        buckets=["all","positive_floor","zero_floor","terminal","positive_floor_terminal","positive_floor_nonterminal"]))
    rows=[]
    for group in paths:
        for i,path in enumerate(paths[group]):
            rows.extend(dict(group=group,run_id=i+1,**r) for r in audit_checkpoint(path))
            print(f"Audited {group} run {i+1}",flush=True)
    write_csv(out/"metrics.csv",rows)
    summary=dict(status="complete",checkpoints=len(hashes),training_replay_transitions=sum(r["samples"] for r in rows if r["bucket"]=="all"),
        test_cases_used=0,new_training_steps=0,source_files_unchanged=all(digest(p)==h for p,h in hashes.items()),
        consistent_td_shift_max_error=max(r["consistent_td_shift_max_error"] for r in rows),
        scope="Exogenous finite-horizon reward offsets preserve policy ordering; offline amplitude change is not performance improvement.",
        command="python -m optimization_control.maddpg_wind_farm.value_baseline_diagnostic --source <tracking-study> --output <new-directory>")
    (out/"summary.txt").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True); parser.add_argument("--output",required=True)
    args=parser.parse_args(); run(args.source,args.output)
