"""Predeclared MADDPG experiments: screening -> confirmation -> locked test.

No test-driven tuning, no silent algorithm replacement, and no overwriting model
snapshots. Master seed 42 derives independent run/exploration/training streams.
"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import torch
import yaml

from .algorithm import MADDPG, AlgorithmConfig
from .workflow import load_config, build_env, fresh_output, write_csv
from .diagnostics import MASKS
from .benchmark import (digest, seed_for, freeze_bank, load_cases, case_trace,
                        evaluate_cases, selection_score, update_best)

DEFAULT=Path(__file__).parent/"configs"/"stable_training.yaml"


class Exploration:
    """AR(1) noise with specified stationary std and physical correlation time."""
    def __init__(self, seed, std, correlation_s, dt, kind, end_fraction):
        self.rng=np.random.default_rng(seed)
        self.std=np.asarray(std,dtype=float)
        self.rho=np.exp(-dt/np.asarray(correlation_s,dtype=float))
        if self.std.shape!=(3,) or self.rho.shape!=(3,) or np.any(self.std<0) or not np.all(np.isfinite(self.std)) or not np.all(np.isfinite(self.rho)) or np.any((self.rho<=0)|(self.rho>=1)):
            raise ValueError("invalid exploration parameters")
        if kind not in ("white","correlated") or not 0<=end_fraction<=1: raise ValueError("invalid exploration schedule")
        self.kind,self.end=kind,end_fraction
        self.state=np.zeros((3,3))

    def reset(self):
        self.state=self.rng.normal(size=(3,3))

    def sample(self, progress):
        z=self.rng.normal(size=(3,3))
        self.state=self.rho*self.state+np.sqrt(1-self.rho**2)*z if self.kind=="correlated" else z
        return self.state*self.std*(1-(1-self.end)*np.clip(progress,0,1))

    def state_dict(self):
        return {"state":self.state.copy(),"rng":self.rng.bit_generator.state}

    def load_state_dict(self,state):
        self.state=np.asarray(state["state"]).copy(); self.rng.bit_generator.state=state["rng"]


def load_protocol(path):
    p=yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if p.get("seed")!=42 or p.get("version")!="stable_training_v1": raise ValueError("master seed 42 and protocol version required")
    rules={"candidate_rule":"lowest_validation_best_rmse_then_candidate_order",
           "checkpoint_rule":"validation_only_strict_improvement_including_initial",
           "test_rule":"open_only_after_selection_and_all_confirmations_are_frozen"}
    if any(p.get(k)!=v for k,v in rules.items()): raise ValueError("unsupported selection protocol rule")
    for key in ("screen_steps","bridge_steps","confirm_steps","eval_every"):
        if p[key]<=0 or p[key]%p["horizon"]: raise ValueError(f"{key} must be positive episode multiple")
    if p["confirmation_repeats"]<3 or p["cases_per_family"]<1: raise ValueError("at least three confirmations required")
    names=[v["name"] for v in p["candidates"]]
    if len(names)!=len(set(names)): raise ValueError("duplicate candidates")
    for candidate in p["candidates"]:
        if candidate["parent"] is not None:
            parent=next(v for v in p["candidates"] if v["name"]==candidate["parent"])
            changes=[k for k in ("nominal_init","reward_scale","actor_lr","noise") if candidate[k]!=parent[k]]
            if len(changes)!=1: raise ValueError("screening edges must change exactly one factor")
    cfg=load_config(Path(path).parent/p["base_config"])
    cfg["environment"].update(horizon=p["horizon"],dt_s=p["dt_s"])
    return p,cfg


def run_config(base, candidate, mask):
    cfg=deepcopy(base)
    cfg["environment"].update(control_mask=mask,reward_scale=candidate["reward_scale"])
    cfg["algorithm"]["actor_lr"]=candidate["actor_lr"]
    for key in ("critic_lr","tau"):
        if key in candidate: cfg["algorithm"][key]=candidate[key]
    return cfg


def new_agent(cfg,candidate,run_seed):
    env=build_env(cfg)
    initial=env.normalize_commands(np.tile(env.initial,(3,1)))[0]
    a=dict(cfg["algorithm"],seed=run_seed,action_mask=tuple(int(v) for v in env.control_mask),fixed_action=tuple(float(v) for v in initial))
    if candidate["nominal_init"]: a["actor_initial_action"]=tuple(float(v) for v in initial)
    return MADDPG(AlgorithmConfig(**a))


def training_options(cfg,p,phase,episode,run_id):
    if phase=="fixed":
        e=cfg["environment"]
        return {"wind_trajectory":np.tile([8.0,e["wind_direction_rad"],e["turbulence_intensity"]],(e["horizon"]+1,1)),"target_w":3e6}
    curriculum=p.get("tracking_curriculum")
    if curriculum and episode%4 in (2,3):
        # One intervention: stratify joint wind/target sampling; no expert actions.
        block=curriculum["fixed" if episode%4==2 else "low"]
        index=episode//4
        wind=block["winds_m_s"][index%len(block["winds_m_s"])]
        target=block["targets_w"][(index//len(block["winds_m_s"]))%len(block["targets_w"])]
        e=cfg["environment"]
        return {"wind_trajectory":np.tile([wind,e["wind_direction_rad"],e["turbulence_intensity"]],(e["horizon"]+1,1)),"target_w":target}
    # Run-specific stream indices; disjoint from frozen validation/test split.
    family=p["training_scenarios"][episode%len(p["training_scenarios"])]
    trace=case_trace(cfg,family,split="train",episode=seed_for(42,301,run_id)+episode)
    return {"wind_trajectory":trace.values,"target_w":p["training_targets_w"][episode%len(p["training_targets_w"]) ]}


def train_run(base,p,candidate,mask,bank,output,*,steps,run_id,phase="fixed",resume=None,stop_at=None):
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    cfg=run_config(base,candidate,mask)
    env=build_env(cfg)
    run_seed=seed_for(42,101,run_id)
    noise=Exploration(seed_for(42,201,run_id),p["noise_std"],p["noise_correlation_s"],env.dt,candidate["noise"],p["noise_end_fraction"])
    families=["fixed"] if phase=="fixed" else p["selection_families"]
    validation=load_cases(bank,"validation",families=families)
    identity={"config":cfg,"protocol":p,"candidate":candidate,"mask":mask,"run_id":run_id,
              "planned_steps":steps,"phase":phase,"bank_sha256":digest(Path(bank)/"manifest.json")}
    end=steps if stop_at is None else stop_at
    if steps%env.horizon or end%env.horizon or not 0<end<=steps: raise ValueError("stop at episode boundaries within planned steps")
    if phase not in ("fixed","mixed") or (end!=steps and end%p["eval_every"]):
        raise ValueError("known training phase and scheduled validation boundary required")
    if resume:
        agent,meta=MADDPG.load(resume)
        if meta["identity"]!=identity: raise ValueError("resume identity mismatch")
        step,episode=meta["steps"],meta["episodes"]
        rows,case_rows,best=meta["history"],meta["validation_history"],meta["best"]
        noise.load_state_dict(meta["noise"])
        if end<=step: raise ValueError("resume must advance training")
    else:
        agent=new_agent(cfg,candidate,run_seed)
        step=episode=0; rows=[]; case_rows=[]; best=None
    out=fresh_output(output,dict(seed=42,**identity))
    (out/"normalization.json").write_text(json.dumps(env.normalization(),indent=2),encoding="utf-8")
    def snapshot(losses):
        nonlocal best
        result=evaluate_cases(cfg,validation,agent=agent)
        path=out/f"step_{step:08d}.pth"
        best=update_best(best,result,families,step,path.resolve())
        row={"steps":step,"validation_rmse_w":selection_score(result,families),"best_rmse_w":best["score_w"],
             "boundary_fraction":float(np.mean([v["boundary_fraction"] for v in result])),
             "q_return_gap_abs":float(np.mean([abs(v["q_initial"]-v["discounted_return"]) for v in result]))}
        for key in ("actor_loss","critic_loss","actor_grad_norm","critic_grad_norm","q_mean","td_abs_mean"):
            row[key]=float(np.mean([v[key] for v in losses])) if losses else 0.0
        rows.append(row); case_rows.extend(dict(steps=step,**v) for v in result)
        meta={"identity":identity,"config":cfg,"normalization":env.normalization(),"steps":step,"episodes":episode,
              "history":rows,"validation_history":case_rows,"best":best,"noise":noise.state_dict()}
        agent.save(path,meta)
        write_csv(out/"metrics.csv",rows); write_csv(out/"validation.csv",case_rows)
        (out/"summary.txt").write_text(json.dumps({"best":best,"final":str(path.resolve()),"completed":step==steps,
                                                      "master_seed":42,"derived_run_seed":run_seed},indent=2),encoding="utf-8")
        print(json.dumps({"run":out.name,**row}),flush=True)
        return path
    if not resume: snapshot([])
    losses=[]
    while step<end:
        obs,_=env.reset(seed=42,options=training_options(cfg,p,phase,episode,run_id))
        noise.reset()
        for _ in range(env.horizon):
            if step<p["warmup_steps"]:
                action=agent.rng.uniform(-1,1,(3,3)).astype(np.float32)
            else:
                action=np.clip(agent.act(obs)+noise.sample(step/steps),-1,1).astype(np.float32)
            nxt,rew,done,_,info=env.step(action)
            agent.replay.add(obs,info["executed_action"],rew,nxt,done)
            step+=1
            if step>=p["warmup_steps"] and agent.replay.size>=agent.config.batch_size and step%p["update_every"]==0:
                losses.append(agent.update())
            obs=nxt
        episode+=1
        if step%p["eval_every"]==0 or step==end:
            final=snapshot(losses); losses=[]
    return {"best":best,"final":str(final.resolve()),"initial_rmse_w":rows[0]["validation_rmse_w"],
            "final_rmse_w":rows[-1]["validation_rmse_w"],"run_id":run_id,"config":cfg}


def execute(protocol_path, output):
    p,base=load_protocol(protocol_path)
    root=fresh_output(output,{"seed":42,"protocol":p,"base_config":base})
    (root/"summary.txt").write_text("status=running\nTest set remains locked until all selections are frozen.\n",encoding="utf-8")
    bank=root/"bank"; bank_hash=freeze_bank(base,p,bank)
    screen=[]
    for candidate in p["candidates"]:
        result=train_run(base,p,candidate,MASKS["pitch"],bank,root/f"screen_{candidate['name']}",steps=p["screen_steps"],run_id=0)
        screen.append({"candidate":candidate,"result":result})
        write_csv(root/"metrics.csv",[{"phase":"screen","name":v["candidate"]["name"],"run_id":0,
                                       "best_validation_rmse_w":v["result"]["best"]["score_w"],
                                       "final_validation_rmse_w":v["result"]["final_rmse_w"]} for v in screen])
    winner=min(screen,key=lambda v:v["result"]["best"]["score_w"])["candidate"]
    (root/"candidate_selection.json").write_text(json.dumps({"candidate":winner,"criterion":p["candidate_rule"],
                                                             "screen":screen,"bank_sha256":bank_hash},indent=2),encoding="utf-8")
    bridges=[]
    for mode in ("pitch_speed","all"):
        bridges.append(train_run(base,p,winner,MASKS[mode],bank,root/f"bridge_{mode}",steps=p["bridge_steps"],run_id=0))
    confirmations=[]
    for repeat in range(p["confirmation_repeats"]):
        confirmations.append(train_run(base,p,winner,MASKS["all"],bank,root/f"confirm_{repeat}",steps=p["confirm_steps"],run_id=repeat+1,phase="mixed"))
    # Test boundary: commit exact selected and final artifacts BEFORE any test inference.
    selection={"candidate":winner,"bank_sha256":bank_hash,"confirmations":confirmations,
               "checkpoint_hashes":{r[k]["checkpoint"] if k=="best" else r[k]:digest(r[k]["checkpoint"] if k=="best" else r[k])
                                    for r in confirmations for k in ("best","final")}}
    (root/"selection.json").write_text(json.dumps(selection,indent=2),encoding="utf-8")
    test_locked(root)
    return root


def test_locked(root):
    root=Path(root)
    selection=json.loads((root/"selection.json").read_text(encoding="utf-8"))
    cfg_all=yaml.safe_load((root/"config.yaml").read_text(encoding="utf-8"))
    p=cfg_all["protocol"]; bank=root/"bank"
    if digest(bank/"manifest.json")!=selection["bank_sha256"]: raise ValueError("benchmark changed after selection")
    for path,expected in selection["checkpoint_hashes"].items():
        if digest(path)!=expected: raise ValueError("selected checkpoint changed")
    test_output=fresh_output(root/"test",{"seed":42,"selection_sha256":digest(root/"selection.json"),"bank_sha256":selection["bank_sha256"]})
    cases=load_cases(bank,"test",allow_test=True)
    rows=[]
    for repeat,result in enumerate(selection["confirmations"]):
        for label,path in (("selected",result["best"]["checkpoint"]),("final",result["final"])):
            agent,meta=MADDPG.load(path)
            rows.extend(dict(repeat=repeat,controller=label,**r) for r in evaluate_cases(meta["config"],cases,agent=agent,timing=True))
        initial=new_agent(result["config"],selection["candidate"],seed_for(42,101,result["run_id"]))
        rows.extend(dict(repeat=repeat,controller="initial",**r) for r in evaluate_cases(result["config"],cases,agent=initial,timing=True))
    for mode in ("fixed","p","pi"):
        rows.extend(dict(repeat=-1,controller=mode,**r) for r in evaluate_cases(selection["confirmations"][0]["config"],cases,baseline=mode,timing=True))
    write_csv(test_output/"metrics.csv",rows)
    summary=summarize(rows,p,selection)
    write_csv(root/"test_summary.csv",summary["aggregate"])
    (test_output/"summary.txt").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    (root/"summary.txt").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    plot(root,rows,selection)
    print(json.dumps(summary,indent=2),flush=True)


def summarize(rows,p,selection):
    groups=[]
    for label in ("initial","selected","final","fixed","p","pi"):
        part=[r for r in rows if r["controller"]==label and r["family"] in p["selection_families"]]
        values=[float(np.mean([r["rmse_w"] for r in part if r["repeat"]==repeat])) for repeat in sorted(set(r["repeat"] for r in part))]
        groups.append({"controller":label,"runs":len(values),"mean_rmse_w":float(np.mean(values)),
                       "std_across_runs_w":float(np.std(values,ddof=1)) if len(values)>1 else 0.0,
                       "min_run_rmse_w":min(values),"max_run_rmse_w":max(values)})
    checks=[]
    for repeat,r in enumerate(selection["confirmations"]):
        fixed=[v["rmse_w"] for v in rows if v["controller"]=="selected" and v["repeat"]==repeat and v["family"]=="fixed"]
        checks.append({"repeat":repeat,"selected_step":r["best"]["step"],
                       "validation_improved":r["best"]["score_w"]<r["initial_rmse_w"],
                       "fixed_test_gate_passed":float(np.mean(fixed))<=p["stability_gate"]["selected_fixed_rmse_w"],
                       "final_degradation_ratio":r["final_rmse_w"]/max(r["best"]["score_w"],1e-9)})
    return {"selected_candidate":selection["candidate"],"aggregate":groups,"checks":checks,
            "stability_gate_passed":all(r["validation_improved"] and r["fixed_test_gate_passed"] and
                                         r["final_degradation_ratio"]<=p["stability_gate"]["max_final_over_selected_validation_ratio"] for r in checks),
            "scope":"single uncalibrated mock; three runs describe variability, not statistical superiority; stress cases excluded from aggregate",
            "test_used_for_selection":False}


def plot(root,rows,selection):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import csv
    fig,axes=plt.subplots(1,2,figsize=(13,4.5))
    for i in range(len(selection["confirmations"])):
        hist=list(csv.DictReader((root/f"confirm_{i}"/"metrics.csv").open(encoding="utf-8")))
        axes[0].plot([int(v["steps"]) for v in hist],[float(v["validation_rmse_w"])/1e3 for v in hist],label=f"Run {i+1}")
    axes[0].set(xlabel="Training steps",ylabel="Validation mean RMSE [kW]",title="No test feedback during training")
    for label in ("selected","final","p","pi"):
        values=[np.mean([v["rmse_w"] for v in rows if v["controller"]==label and v["family"]==family])/1e3 for family in ("fixed","stationary","ramp","gust","direction","shortfall")]
        axes[1].plot(range(6),values,marker="o",label=label)
    axes[1].set_xticks(range(6),["fixed","turbulence","ramp","gust","direction","shortfall"],rotation=20)
    axes[1].set(ylabel="Test mean RMSE [kW]",title="Frozen cases | stress shown separately")
    for ax in axes: ax.legend(); ax.grid(alpha=.2)
    fig.suptitle("MADDPG validation selection and independent repeats | mock only")
    fig.tight_layout(); fig.savefig(root/"stability.png",dpi=140); plt.close(fig)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol",default=str(DEFAULT)); parser.add_argument("--output",required=True)
    args=parser.parse_args()
    existed=Path(args.output).exists()
    try:
        execute(args.protocol,args.output)
    except Exception as exc:
        if not existed and Path(args.output).exists():
            (Path(args.output)/"failure.json").write_text(json.dumps({"status":"failed","error_type":type(exc).__name__,
                                                                     "message":str(exc)},indent=2),encoding="utf-8")
        raise
