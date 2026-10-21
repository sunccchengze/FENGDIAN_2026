"""Validation-only checkpoint diagnostics; diagnostic updates are never saved."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from .algorithm import MADDPG
from .benchmark import load_cases, digest
from .workflow import build_env, fresh_output, write_csv
from .stable_workflow import training_options

CHANNELS=("yaw","pitch","speed")


def rollout(agent,cfg,cases):
    rows=[]
    for case,trace in cases:
        env=build_env(cfg)
        obs,info=env.reset(options={"wind_trajectory":trace.values,"target_w":case["target_w"]})
        with torch.no_grad():
            x=torch.cat((torch.tensor(obs).flatten(),torch.tensor(agent.act(obs)).flatten()))
            q=np.array([float(c(x)) for c in agent.critics])
        actions=[]; changes=[]; motions=[]; reward=[]; errors=[]
        previous=info["executed_action"]; heading=info["heading_rad"]; applied=info["applied"]
        for _ in range(env.horizon):
            a=agent.act(obs)
            obs,r,done,_,info=env.step(a)
            actions.append(a); changes.append(np.abs(a-previous)); previous=a
            motions.append(np.column_stack((info["heading_rad"]-heading,info["applied"][:,1:]-applied[:,1:])))
            heading=info["heading_rad"]; applied=info["applied"]
            reward.append(float(r[0])); errors.append(info["error_w"])
            if done: break
        ret=float(np.dot(np.power(agent.config.gamma,np.arange(len(reward))),reward))
        for i in range(3):
            for j,ch in enumerate(CHANNELS):
                rows.append(dict(case_id=case["id"],family=case["family"],agent=i+1,channel=ch,
                    rmse_w=float(np.sqrt(np.mean(np.square(errors)))),q_initial=q[i],return_observed=ret,
                    q_minus_return=q[i]-ret,boundary_fraction=float(np.mean(np.abs(np.array(actions)[:,i,j])>.98)),
                    mean_action_change=float(np.mean(np.array(changes)[:,i,j])),
                    applied_travel=float(np.abs(np.array(motions)[:,i,j]).sum())))
    return rows


def run(source,output):
    torch.set_num_threads(1)
    source=Path(source)
    out=fresh_output(output,{"seed":42,"source":str(source.resolve()),"split":"validation","diagnostic_updates_saved":False})
    cases=load_cases(source/"bank","validation",families=["fixed","stationary","ramp","gust","direction"])
    rows=[]; probes=[]; audits=[]
    for repeat in range(3):
        folder=source/f"confirm_{repeat}"
        summary=json.loads((folder/"summary.txt").read_text())
        best=summary["best"]["step"]
        final=16384
        # Include neighbors of the best to distinguish transient changes from endpoints.
        for step in sorted(set([max(2048,best-2048),best,min(final,best+2048),final])):
            path=folder/f"step_{step:08d}.pth"
            checksum=digest(path)
            agent,meta=MADDPG.load(path)
            rows.extend(dict(repeat=repeat,steps=step,is_best=step==best,**r) for r in rollout(agent,meta["config"],cases))
            replay=agent.replay
            data=replay.data; n=replay.size
            indices=np.linspace(0,n-1,min(256,n),dtype=int)
            states=data["obs"][indices]
            def batch_actions():
                with torch.no_grad():
                    return torch.stack([agent.policy(m,torch.tensor(states[:,i])) for i,m in enumerate(agent.actors)],1).numpy()
            before=batch_actions()
            losses=agent.update()
            after=batch_actions()
            for i in range(3):
                for j,ch in enumerate(CHANNELS):
                    delta=after[:,i,j]-before[:,i,j]
                    probes.append(dict(repeat=repeat,steps=step,agent=i+1,channel=ch,
                        mean_abs_delta=float(np.abs(delta).mean()),max_abs_delta=float(np.abs(delta).max()),**losses))
            terminated=data["terminated"][:n,0].astype(bool)
            assert np.allclose(data["next_obs"][:n,:,14][terminated],0)
            assert np.all(data["next_obs"][:n,:,14][~terminated]>0)
            np.testing.assert_array_equal(data["actions"][:n],data["next_obs"][:n,:,5:8])
            target_counts={str(round(float(t)*15e6)):int(c) for t,c in zip(*np.unique(data["obs"][:n,0,8],return_counts=True))}
            episodes=[]
            for e in range(meta["episodes"]):
                p=meta["identity"]["protocol"]
                opts=training_options(meta["config"],p,"mixed",e,meta["identity"]["run_id"])
                family=p["training_scenarios"][e%len(p["training_scenarios"]) ]
                episodes.append((family,opts["target_w"]))
            counts={f"{f}/{t:.0f}":episodes.count((f,t)) for f,t in sorted(set(episodes))}
            audits.append(dict(repeat=repeat,steps=step,replay_size=n,terminated_count=int(terminated.sum()),
                terminal_and_command_contract=True,target_step_counts=target_counts,training_episode_counts=counts,
                replay_capacity_exceeded=False,applied_observation_indices=[2,3,4],previous_command_indices=[5,6,7],
                partial_observability="No wind history; hidden random wind realization is not observed."))
            assert digest(path)==checksum
            print(f"diagnosed repeat={repeat} step={step}",flush=True)
    write_csv(out/"metrics.csv",rows); write_csv(out/"update_probes.csv",probes)
    (out/"replay_audit.json").write_text(json.dumps(audits,indent=2),encoding="utf-8")
    (out/"summary.txt").write_text(json.dumps({"checkpoint_count":len(audits),"rows":len(rows),
        "command":"python -m optimization_control.maddpg_wind_farm.retrospective --source <old-study> --output <new-directory>",
        "terminal_and_command_contract":True,"source_checkpoints_unchanged":True,
        "artifacts":["metrics.csv","update_probes.csv","replay_audit.json"],
        "scope":"validation only; Q-return differences use one realized wind continuation, not exact conditional expected value"},indent=2),encoding="utf-8")


def channel_rollback(source,output):
    """Intervene on one action channel on validation: no model fitting or test use."""
    torch.set_num_threads(1)
    source=Path(source)
    out=fresh_output(output,{"seed":42,"source":str(source.resolve()),"split":"validation",
        "intervention":"final policy with one channel replaced by best policy at the current state"})
    cases=load_cases(source/"bank","validation",families=["fixed","stationary","ramp","gust","direction"])
    rows=[]
    for repeat in range(3):
        folder=source/f"confirm_{repeat}"; s=json.loads((folder/"summary.txt").read_text())
        best,_=MADDPG.load(s["best"]["checkpoint"]); final,meta=MADDPG.load(s["final"])
        for mode in ("best","final",*CHANNELS):
            for case,trace in cases:
                env=build_env(meta["config"])
                obs,_=env.reset(options={"wind_trajectory":trace.values,"target_w":case["target_w"]})
                errors=[]
                for _ in range(env.horizon):
                    a=(best if mode=="best" else final).act(obs)
                    if mode in CHANNELS:
                        j=CHANNELS.index(mode); a[:,j]=best.act(obs)[:,j]
                    obs,_,done,_,info=env.step(a); errors.append(info["error_w"])
                    if done: break
                rows.append(dict(repeat=repeat,mode=mode,family=case["family"],case_id=case["id"],rmse_w=float(np.sqrt(np.mean(np.square(errors))))))
        print(f"channel rollback repeat={repeat} complete",flush=True)
    write_csv(out/"metrics.csv",rows)
    means=[dict(repeat=i,mode=mode,mean_rmse_w=float(np.mean([r["rmse_w"] for r in rows if r["repeat"]==i and r["mode"]==mode]))) for i in range(3) for mode in ("best","final",*CHANNELS)]
    (out/"summary.txt").write_text(json.dumps({"aggregate":means,
        "command":"python -m optimization_control.maddpg_wind_farm.retrospective --source <old-study> --output <new-directory> --channel-rollback",
        "scope":"validation-only channel intervention; cross-channel/state interactions remain; not a new selected policy"},indent=2),encoding="utf-8")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True); parser.add_argument("--output",required=True)
    parser.add_argument("--channel-rollback",action="store_true")
    args=parser.parse_args()
    (channel_rollback if args.channel_rollback else run)(args.source,args.output)
