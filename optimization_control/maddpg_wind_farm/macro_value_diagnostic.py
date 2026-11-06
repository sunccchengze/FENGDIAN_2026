"""Read-only macro Critic audit and a locked same-state realization experiment."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import pickle
import time

from . import forecast_speed_training as formal
from .forecast_speed_report import csv_out

ROOT = formal.EXPS / "20261105_macro_value_diagnostic"
MIB = formal.MIB
BASE = "3ccadc45ad022e40e7edb33ff7e7b1ace8a36ce3"
TIMES = (32, 80)
LABELS = ("own", "zero", "half", "t0_minus", "t0_plus", "t1_minus", "t1_plus", "t2_minus", "t2_plus")
FIELDS = formal.TRACE + ("tracking_reward", "motion_reward")
MODULES = ("heads", "critics", "target_heads", "target_critics")


def store():
    return formal.Store(ROOT, 128*MIB)


def path_ref(path):
    return dict(path=str(path), sha256=formal.sha(path))


def prepare():
    import yaml
    source = formal.context()
    selection = formal.read(formal.ROOT/"selection.json")
    if formal.git("rev-parse", "HEAD").decode().strip() != BASE:
        raise ValueError("reviewed formal baseline required")
    assert formal.read(formal.ROOT/"verification.json")["checkpoint_checks"]["verified_final_macro_rows"] == 6144
    refs = dict(source["hashes"])
    files = [Path(__file__), Path(__file__).with_name("MACRO_VALUE_DIAGNOSTIC_PROTOCOL.md"),
             formal.ROOT/"selection.json", formal.ROOT/"verification.json", formal.ROOT/"git_delivery.json"]
    refs.update({str(path):formal.sha(path) for path in files})
    for ref in source["banks"].values():
        if "/stress." not in ref["path"].replace("\\","/"):
            refs[ref["path"]] = ref["sha256"]
    jobs = [j for j in selection["jobs"] if j["arm"] in ("B","C")]
    for job in jobs:
        for point in job["points"]:
            bound = [point["snapshot"], point["episodes"]]
            if point["checkpoint"]:
                bound += [point["checkpoint"], formal.read(formal.verify(point["checkpoint"]))["state"]]
            if point["step"] in (job["selected"]["step"],8192):
                bound.extend(point["eval"].values())
            for ref in bound:
                formal.verify(ref)
                refs[ref["path"]] = ref["sha256"]
    assert len(jobs)==6 and (65+72*129+144*9*16)==30089
    ROOT.mkdir(exist_ok=False)
    config=dict(seed=42, formal_source_commit=BASE, train_bank="formal_frozen", validation_bank="formal_frozen",
                anchor_times=list(TIMES), candidate_labels=list(LABELS), normalized_perturbation=.25,
                first_hold=8, continuation=8, minimum_return_gain=.01, minimum_rmse_gain_fraction=.05,
                meaningful_sign_tol=1e-7, planned_mock_rows=65, planned_PINN_rows=30024,
                row_hard_cap=40000, disk_hard_cap_MiB=128, formal_RL_steps=0, optimizer_updates=0, new_test=0)
    cfg=store().write("config.yaml",yaml.safe_dump(config,sort_keys=False).encode())
    refs[cfg["path"]]=cfg["sha256"]
    store().json("lock.json",dict(hashes=refs, jobs=jobs, source=source, design=config,
                                 selection_sha=formal.sha(formal.ROOT/"selection.json"), unsealed_test_sets=0))


def context():
    lock=formal.read(ROOT/"lock.json")
    for path,sha in lock["hashes"].items():
        formal.verify(dict(path=path,sha256=sha))
    return lock


def point_state(point):
    import torch
    ref=formal.read(formal.verify(point["checkpoint"]))["state"]
    state=torch.load(formal.verify(ref),map_location="cpu",weights_only=False)
    assert state["purpose"]==formal.PURPOSE
    return state


def policy(source, job, point, state=None):
    import torch
    agent,_=formal.fresh(source,job["arm"],job["run"])
    if point["step"]:
        state=point_state(point) if state is None else state
        assert state["identity"]==agent.identity and state["steps"]==point["step"]
        for name in MODULES:
            getattr(agent,name).load_state_dict(state["networks"][name])
    snapshot=torch.load(formal.verify(point["snapshot"]),map_location="cpu",weights_only=True)
    assert all(torch.equal(w,snapshot["weights"][key]) for key,w in agent.heads.state_dict().items())
    for name in MODULES:
        getattr(agent,name).requires_grad_(False)
    return agent


def fingerprint(agent):
    from .forecast_decision_contract import model_digest
    h=hashlib.sha256(model_digest(agent.parent).encode())
    for name in MODULES:
        for tensor in getattr(agent,name).state_dict().values():
            h.update(tensor.numpy().tobytes())
    for rng in (agent.noise,agent.replay.rng,agent.parent.rng):
        h.update(json.dumps(rng.bit_generator.state,sort_keys=True).encode())
    assert not any(opt.state for opt in [*agent.head_adam,*agent.critic_adam])
    return h.hexdigest()


def q_values(agent, obs, forecast, z):
    import torch
    from .forecast_speed_macro import joint_input
    x=joint_input(obs,forecast,z)
    return torch.cat([critic(x) for critic in agent.critics],dim=1)


def values_and_gradient(agent, obs, forecast, z):
    import torch
    z=z.detach().clone().requires_grad_(True)
    q=q_values(agent,obs,forecast,z)
    grad=torch.stack([torch.autograd.grad(q[:,i].sum(),z,retain_graph=i<2)[0][:,i]
                      for i in range(3)],dim=1)
    return q.detach().numpy(),grad.detach().numpy()


def replay_stats(agent,data):
    import numpy as np
    import torch
    obs,forecast,z=(torch.from_numpy(data[k]) for k in ("obs","forecast","z"))
    with torch.no_grad():
        current=agent.offsets(obs,forecast)
        target=agent.targets({k:torch.from_numpy(v) for k,v in data.items() if k in
                              ("return","terminal","next_obs","next_forecast","discount")})
        behavior=q_values(agent,obs,forecast,z)
    value,grad=values_and_gradient(agent,obs,forecast,current)
    actual=z.numpy()
    td=target.numpy()-behavior.numpy()
    distance=current.numpy()-actual
    fields=dict(q_behavior=behavior.numpy(),q_current=value,td=td,z_behavior=actual,
                z_current=current.numpy(),own_gradient=grad,action_distance=distance)
    summary=[]
    for i in range(3):
        summary.append(dict(turbine=i,count=len(obs),q_behavior_mean=float(behavior[:,i].mean()),
            q_behavior_abs95=float(np.quantile(np.abs(behavior[:,i].numpy()),.95)),
            q_current_mean=float(value[:,i].mean()),td_rms=float(np.sqrt(np.mean(td[:,i]**2))),
            td_abs95=float(np.quantile(np.abs(td[:,i]),.95)),td_bias=float(td[:,i].mean()),
            gradient_mean=float(grad[:,i].mean()),gradient_abs_mean=float(np.abs(grad[:,i]).mean()),
            gradient_positive_fraction=float(np.mean(grad[:,i]>1e-7)),
            behavior_z_mean=float(actual[:,i].mean()),behavior_z_p05=float(np.quantile(actual[:,i],.05)),
            behavior_z_p95=float(np.quantile(actual[:,i],.95)),behavior_negative_fraction=float(np.mean(actual[:,i]<0)),
            behavior_at_bound=float(np.mean(np.abs(actual[:,i])>=.98)),current_z_mean=float(current[:,i].mean()),
            current_z_abs_mean=float(current[:,i].abs().mean()),
            distance_rms=float(np.sqrt(np.mean(distance[:,i]**2))),distance_abs95=float(np.quantile(np.abs(distance[:,i]),.95))))
    return summary,fields


def offline():
    import numpy as np
    lock=context()
    historic,progress=[],[]
    for job in lock["jobs"]:
        arm,run=job["arm"],job["run"]
        updates=0
        first=point_state(job["points"][1])["replay"]["data"]
        for point in job["points"]:
            step=point["step"]
            for ep in formal.read(formal.verify(point["episodes"])):
                n=ep["updates"]
                updates+=n
                historic.append(dict(arm=arm,run=run,step=ep["step"],updates=n,cumulative_updates=updates,
                    **{key:ep["loss_summary"].get(key,"") for key in
                       ("critic_loss","actor_loss","critic_grad_norm","actor_grad_norm")}))
            state=point_state(point) if step else None
            data=first if state is None else state["replay"]["data"]
            agent=policy(lock["source"],job,point,state)
            before=fingerprint(agent)
            rows,arrays=replay_stats(agent,data)
            common,_=replay_stats(agent,{k:v[:256] for k,v in first.items()})
            assert fingerprint(agent)==before
            for name,group in (("retained" if step else "retrospective_initial",rows),("common_first256",common)):
                progress.extend(dict(arm=arm,run=run,step=step,cohort=name,**row) for row in group)
            store().arrays(f"offline/{arm}{run}/s{step:04d}.npz",**arrays,
                           episode=data["episode"],t=data["t"])
        assert updates==481
    csv_out(store(),"update_episode_means.csv",historic)
    csv_out(store(),"critic_snapshots.csv",progress)
    store().json("offline_complete.json",dict(arms=6,updates_per_job=481,optimizer_updates=0,
        model_queries=0,exact_update_q_td_available=False,checkpoint_points=[0,2048,4096,6144,8192],
        historical_rows=len(historic),snapshot_summary_rows=len(progress)))


def candidates(z):
    import numpy as np
    z=np.asarray(z,np.float32)
    moves=[z,np.zeros(3,np.float32),.5*z]
    for i in range(3):
        for sign in (-1,1):
            d=z.copy()
            d[i]=np.clip(float(d[i])+sign*.25,-1,1)
            moves.append(d)
    return np.stack(moves)


def row(env,info,parent,z,reward):
    scale=env.config["reward_scale"]
    return formal.trace_row(info,parent,z,reward)+[
        scale*info["reward_terms"]["tracking"],scale*info["reward_terms"]["action_change"]]


def forced_branch(env,current,history,agent,z,scoring_wind):
    import numpy as np
    from .causal_speed_search import fork, command
    child=fork(current,env.plant,type(env))
    obs=child._observe()
    prefix=[x.copy() for x in history]
    obs_trace=[obs.copy()]
    rows=[row(child,child._info(),agent.parent.act(obs),z,0)]
    continuation=None
    for k in range(16):
        if k==8:
            continuation=agent.features(prefix)
            z=agent.z(obs,continuation)
        action,parent=command(agent.parent,obs,.1*z.astype(np.float64))
        # This write belongs to the scorer and occurs after policy/action calculation.
        child.trajectory[child.t+1]=scoring_wind[child.t+1]
        obs,reward,done,truncated,info=child.step(action)
        assert not done and not truncated
        np.testing.assert_array_equal(info["executed_action"],action)
        prefix.append(info["wind"].copy())
        obs_trace.append(obs.copy())
        rows.append(row(child,info,parent,z,reward[0]))
    return np.asarray(rows,np.float64),np.stack(obs_trace),continuation


def value_at_anchor(agent,obs,forecast,z):
    import numpy as np
    import torch
    o=torch.from_numpy(np.repeat(obs[None],9,axis=0))
    f=torch.from_numpy(np.repeat(forecast[None],9,axis=0))
    zz=torch.from_numpy(z)
    q,grad=values_and_gradient(agent,o,f,zz)
    q0,grad0=values_and_gradient(agent,o,torch.zeros_like(f),zz)
    zero_actor=agent.z(obs,np.zeros(36,np.float32))
    return q,grad,q0,grad0,zero_actor


def mock_gate(lock,budget):
    import numpy as np
    from .causal_speed_search import capture,state_sha
    from .forecast_speed_macro import Episode
    from .workflow import DEFAULT_CONFIG,load_config
    job=next(j for j in lock["jobs"] if (j["arm"],j["run"])==("C",0))
    agent=policy(lock["source"],job,job["final"])
    cfg=deepcopy(lock["source"])
    cfg["base_config"]["plant"]=load_config(DEFAULT_CONFIG)["plant"]
    case,wind=formal.bank(lock["source"],"validation")[0]
    budget.start("clone_mock",65)
    world=formal.World(cfg)
    env=world.env(budget,True)
    env.plant.predictor.kind="mock"
    obs,info=formal.reset(env,case,wind)
    episode=Episode(agent,env,obs,info)
    for _ in range(32):
        episode.step()
    digest=state_sha(env)
    z=agent.z(episode.obs,episode.features)
    tr,ob,ft=forced_branch(env,capture(env),episode.observed,agent,z,wind)
    assert state_sha(env)==digest
    expected=[]
    for _ in range(16):
        parent,_,held,r,_,info=episode.step()
        expected.append(row(env,info,parent,held,r[0]))
    np.testing.assert_array_equal(tr[1:],expected)
    np.testing.assert_array_equal(ob[-1],episode.obs)
    receipt=budget.finish()
    assert receipt["actual"]==65
    store().json("clone_gate.json",dict(passed=True,rows=65,own_branch_exact=True,source_state_unchanged=True))


def evaluate_group(lock,world,budget,job,role):
    import numpy as np
    from .causal_speed_search import capture,state_sha
    from .forecast_speed_macro import Episode
    arm,run=job["arm"],job["run"]
    point=job[role]
    group=f"{arm}{run}_{role}"
    agent=policy(lock["source"],job,point)
    digest=fingerprint(agent)
    cases=formal.bank(lock["source"],"validation")
    meta,base,branches,observations,forecasts,zlist=[],[],[],[],[],[]
    qlist,gradlist,qzero,gradzero,actorzero,histories=[],[],[],[],[],[]
    blobs,offsets=[],[0]
    budget.start(group,2502)
    env=world.env(budget,True)
    env.plant.predictor.kind="real_PINN"
    with np.load(formal.verify(point["eval"]["trace"]),allow_pickle=False) as frozen:
        old_trace=frozen["trace"]
    for case_index,(case,wind) in enumerate(cases):
        obs,info=formal.reset(env,case,wind)
        episode=Episode(agent,env,obs,info)
        trajectory=[row(env,info,info["executed_action"],np.zeros(3),0)]
        for t in range(128):
            if t in TIMES:
                assert episode.pending is None and env.t==t and len(episode.observed)==t+1
                state=capture(env)
                before=state_sha(env)
                capsule=pickle.dumps(state,protocol=5)
                blobs.append(np.frombuffer(capsule,dtype=np.uint8))
                offsets.append(offsets[-1]+len(capsule))
                z=candidates(agent.z(episode.obs,episode.features))
                q,grad,q0,g0,z0=value_at_anchor(agent,episode.obs,episode.features,z)
                experiments=[forced_branch(env,state,episode.observed,agent,action,wind) for action in z]
                assert before==state_sha(env)
                branches.append(np.stack([r[0] for r in experiments]))
                observations.append(np.stack([r[1] for r in experiments]))
                forecasts.append(np.stack([r[2] for r in experiments]))
                history=np.zeros((81,3),np.float32);history[:t+1]=episode.observed
                histories.append(history)
                zlist.append(z)
                qlist.append(q);gradlist.append(grad);qzero.append(q0);gradzero.append(g0);actorzero.append(z0)
                meta.append(dict(group=group,arm=arm,run=run,role=role,checkpoint_step=point["step"],
                    case_index=case_index,case_id=case["id"],t=t,history_length=t+1,
                    capsule_sha256=hashlib.sha256(capsule).hexdigest(),current_forecast=episode.features.tolist()))
            parent,_,held,r,done,info=episode.step()
            assert done==(t==127)
            trajectory.append(row(env,info,parent,held,r[0]))
        complete=np.asarray(trajectory,np.float64)
        np.testing.assert_array_equal(complete[:,:len(formal.TRACE)],old_trace[case_index])
        for idx in range(len(meta)-2,len(meta)):
            t=meta[idx]["t"]
            np.testing.assert_array_equal(branches[idx][0,1:],complete[t+1:t+17])
        base.append(complete)
    assert len(meta)==12 and fingerprint(agent)==digest
    receipt=budget.finish()
    assert receipt["actual"]==2502
    ref=store().arrays(f"anchors/{group}.npz", base=np.stack(base),trace=np.stack(branches),
        obs=np.stack(observations),next_forecast=np.stack(forecasts),history=np.stack(histories),
        candidates=np.stack(zlist),q=np.stack(qlist),own_gradient=np.stack(gradlist),q_zero_forecast=np.stack(qzero),
        gradient_zero_forecast=np.stack(gradzero),actor_zero_forecast=np.stack(actorzero),
        capsule_bytes=np.concatenate(blobs),capsule_offsets=np.asarray(offsets),
        fields=np.array(FIELDS),labels=np.array(LABELS),meta=np.array(json.dumps(meta)))
    return dict(group=group,artifact=ref,rows=receipt["actual"],anchors=12,
                source_parameters_rng_unchanged=True,original_and_own_rollout_exact=True)


def run():
    import torch
    from .causal_speed_search import Budget
    lock=context()
    assert (ROOT/"offline_complete.json").exists()
    store().json("run_attempt.json",dict(pid=os.getpid(),max_rows=40000,predeclared_rows=30089))
    budget=Budget(ROOT/"budget.json",limit=40000)
    rng=torch.get_rng_state().clone()
    mock_gate(lock,budget)
    world=formal.World(lock["source"])
    results=[]
    for job in lock["jobs"]:
        for role in ("selected","final"):
            start=time.perf_counter()
            result=evaluate_group(lock,world,budget,job,role)
            results.append(result)
            print(result["group"],result["rows"],f"{time.perf_counter()-start:.1f}s",flush=True)
    assert torch.equal(rng,torch.get_rng_state())
    context()
    assert sum(x["actual"] for x in budget.data["scopes"])==30089
    store().json("complete.json",dict(groups=results,anchors=144,branches=1296,mock_rows=65,real_PINN_rows=30024,
        total_rows=30089,formal_RL_steps=0,optimizer_updates=0,new_test=0))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase",choices=("prepare","offline","run"))
    phase=parser.parse_args().phase
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(formal.ORIGIN/".venv/pinn_tf216")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS","1")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS","1")
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(42)
    {"prepare":prepare,"offline":offline,"run":run}[phase]()


if __name__=="__main__":
    main()
