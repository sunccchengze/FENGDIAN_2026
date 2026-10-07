"""Paired mixed-wind single-factor MADDPG study, validation tuning, held-out test."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from copy import deepcopy
import csv
import json
import os
from pathlib import Path
import numpy as np
import torch
import yaml
from .algorithm import MADDPG
from .benchmark import digest, freeze_bank, load_cases, evaluate_cases, selection_score
from .stable_workflow import load_protocol, DEFAULT, train_run, run_config
from .workflow import fresh_output, write_csv

PROTOCOL=Path(__file__).parent/"configs"/"mixed_stability.yaml"


def read_csv(path):
    with Path(path).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_protocol(path):
    spec=yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if spec["version"]!="mixed_stability_v1" or spec["seed"]!=42:
        raise ValueError("unsupported study")
    if spec["selection_rule"]!="most_stable_runs_then_lowest_tail3_validation_then_declared_order" or spec["test_rule"]!="freeze_all_models_and_baselines_before_test":
        raise ValueError("unsupported selection boundary")
    if len(spec["run_ids"])<3 or len(set(spec["run_ids"]))!=len(spec["run_ids"]):
        raise ValueError("three distinct training runs required")
    candidates=spec["candidates"]
    if candidates[0]["name"]!="baseline" or len(set(c["name"] for c in candidates))!=len(candidates):
        raise ValueError("unique candidates and baseline first required")
    keys=set(candidates[0]) - {"name"}
    for c in candidates[1:]:
        if set(c)-{"name"}!=keys or sum(c[k]!=candidates[0][k] for k in keys)!=1:
            raise ValueError("each candidate must change exactly one baseline factor")
    p,base=load_protocol(DEFAULT)
    p.update({k:spec[k] for k in ("bank_episode_offset","bank_targets_w","cases_per_family")})
    if spec["bank_episode_offset"]<=20500 or spec["steps"]%p["eval_every"]:
        raise ValueError("fresh bank and full validation intervals required")
    return spec,p,base


def worker(base,p,candidate,bank,out,steps,run_id,resume=None):
    # Independent processes use one Torch thread each, never share a replay or RNG.
    with Path(str(out)+".log").open("w",encoding="utf-8") as log, redirect_stdout(log):
        result=train_run(base,p,candidate,[1,1,1],bank,out,steps=steps,run_id=run_id,phase="mixed",resume=resume)
    (Path(out)/"result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return candidate["name"],result


def validation_rank(candidate_results):
    stable=0; tails=[]
    for r in candidate_results:
        stable+=int(r["best"]["score_w"]<r["initial_rmse_w"] and r["final_rmse_w"]/r["best"]["score_w"]<=1.25)
        rows=read_csv(Path(r["final"]).parent/"metrics.csv")
        tails.append(float(np.mean([float(v["validation_rmse_w"]) for v in rows[-3:]])))
    return -stable,float(np.mean(tails))


def tune_baselines(base,p,spec,bank,root):
    cases=load_cases(bank,"validation",families=p["selection_families"])
    rows=[]; selected={}
    for mode in ("p","pi"):
        options=[]
        for kp in spec["baseline_kp"]:
            for ki in (spec["baseline_ki"] if mode=="pi" else [base["baselines"]["ki"]]):
                cfg=deepcopy(base); cfg["baselines"].update(kp=kp,ki=ki)
                score=selection_score(evaluate_cases(cfg,cases,baseline=mode),p["selection_families"])
                rows.append(dict(controller=mode,kp=kp,ki=ki,validation_rmse_w=score))
                options.append((score,cfg["baselines"]))
        selected[mode]=min(options,key=lambda x:x[0])[1]
    write_csv(root/"baseline_validation.csv",rows)
    return selected


def aggregate_test(rows,families):
    aggregated=[]
    for label in dict.fromkeys(r["controller"] for r in rows):
        subset=[r for r in rows if r["controller"]==label and r["family"] in families]
        values=[np.mean([r["rmse_w"] for r in subset if r["run_id"]==run]) for run in sorted(set(r["run_id"] for r in subset))]
        aggregated.append(dict(controller=label,runs=len(values),mean_rmse_w=float(np.mean(values)),
            std_w=float(np.std(values,ddof=1)) if len(values)>1 else 0.0,min_w=float(min(values)),max_w=float(max(values))))
    return aggregated


def locked_test(root):
    root=Path(root)
    selection=json.loads((root/"selection.json").read_text(encoding="utf-8"))
    saved=yaml.safe_load((root/"config.yaml").read_text(encoding="utf-8"))
    p=saved["training_protocol"]; base=saved["base_config"]
    if digest(root/"bank"/"manifest.json")!=selection["bank_sha256"]: raise ValueError("changed bank")
    for path,value in selection["hashes"].items():
        if digest(path)!=value: raise ValueError("changed frozen model")
    out=fresh_output(root/"test",{"seed":42,"selection_sha256":digest(root/"selection.json")})
    cases=load_cases(root/"bank","test",allow_test=True)
    rows=[]; checks=[]
    labels=list(dict.fromkeys(["baseline",selection["winner"]]))
    for name in labels:
        for r in selection["results"][name]:
            for stage in ("selected","final"):
                path=r["best"]["checkpoint"] if stage=="selected" else r["final"]
                agent,meta=MADDPG.load(path)
                metrics=evaluate_cases(meta["config"],cases,agent=agent,timing=True)
                rows.extend(dict(controller=f"{name}_{stage}",run_id=r["run_id"],**v) for v in metrics)
                if stage=="selected":
                    fixed=[v["rmse_w"] for v in metrics if v["family"]=="fixed" and v["target_w"]==3e6]
                    checks.append(dict(candidate=name,run_id=r["run_id"],selected_step=r["best"]["step"],
                        validation_improved=r["best"]["score_w"]<r["initial_rmse_w"],
                        final_degradation_ratio=r["final_rmse_w"]/r["best"]["score_w"],
                        fixed_3mw_rmse_w=float(np.mean(fixed)),fixed_3mw_gate_passed=bool(np.mean(fixed)<=200000)))
    # Reward scaling matches MADDPG for consistent return diagnostics; physical metrics unaffected.
    cfg=run_config(base,selection["spec"]["candidates"][0],[1,1,1])
    for mode in ("p","pi"):
        for variant in ("default","tuned"):
            bc=deepcopy(cfg)
            if variant=="tuned": bc["baselines"]=selection["baselines"][mode]
            rows.extend(dict(controller=f"{mode}_{variant}",run_id=-1,**v) for v in evaluate_cases(bc,cases,baseline=mode,timing=True))
    write_csv(out/"metrics.csv",rows)
    aggregated=aggregate_test(rows,p["selection_families"])
    paired=[]
    if selection["winner"]!="baseline":
        for run in selection["spec"]["run_ids"]:
            for stage in ("selected","final"):
                means=[]
                for name in ("baseline",selection["winner"]):
                    means.append(np.mean([r["rmse_w"] for r in rows if r["controller"]==f"{name}_{stage}" and r["run_id"]==run and r["family"] in p["selection_families"]]))
                paired.append(dict(run_id=run,stage=stage,delta_rmse_w=float(means[1]-means[0])))
    summary={"winner":selection["winner"],"aggregate":aggregated,"paired_differences":paired,"checks":checks,
        "full_stability_gate_passed":all(c["validation_improved"] and c["final_degradation_ratio"]<=1.25 and c["fixed_3mw_gate_passed"] for c in checks if c["candidate"]==selection["winner"]),
        "scope":"uncalibrated mock; three paired runs; no statistical superiority claim; stress excluded from aggregate",
        "test_used_for_selection":False,"selection_ranks":selection["ranks"],"baselines":selection["baselines"],
        "command":"python -m optimization_control.maddpg_wind_farm.mixed_stability --output <new-directory>",
        "artifacts":["selection.json","test/metrics.csv","test_summary.csv","comparison.png","<candidate>_run_<id>/normalization.json"]}
    write_csv(root/"test_summary.csv",aggregated)
    for path in (out/"summary.txt",root/"summary.txt"):
        path.write_text(json.dumps(summary,indent=2),encoding="utf-8")
    plot(root,selection,aggregated)
    return summary


def plot(root,selection,aggregated):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(14,5))
    for name,runs in selection["results"].items():
        histories=[read_csv(Path(r["final"]).parent/"metrics.csv") for r in runs]
        values=np.array([[float(r["validation_rmse_w"])/1000 for r in h] for h in histories])
        steps=[int(r["steps"]) for r in histories[0]]
        axes[0].plot(steps,values.mean(0),label=name)
        axes[0].fill_between(steps,values.min(0),values.max(0),alpha=.1)
    axes[0].set(xlabel="Training steps",ylabel="Validation RMSE [kW]",title="Three paired runs: mean and range")
    axes[0].legend(); axes[0].grid(alpha=.2)
    axes[1].barh([r["controller"] for r in aggregated],[r["mean_rmse_w"]/1000 for r in aggregated],xerr=[r["std_w"]/1000 for r in aggregated])
    axes[1].set(xlabel="Held-out RMSE [kW]",title="Regular cases | error bars: run sample SD")
    fig.suptitle("Mixed-wind MADDPG single-factor study | mock only")
    fig.tight_layout(); fig.savefig(root/"comparison.png",dpi=140); plt.close(fig)


def recover_job(root,name,run_id,steps):
    """Trust only snapshots committed by a completed summary write, not partial saves."""
    original=root/f"{name}_run_{run_id}"
    folders=[original,*sorted(root.glob(f"{name}_run_{run_id}_resume_*"))]
    completed=[]; saved=[]
    for folder in folders:
        if (folder/"result.json").exists():
            completed.append(json.loads((folder/"result.json").read_text(encoding="utf-8")))
        elif (folder/"summary.txt").exists():
            summary=json.loads((folder/"summary.txt").read_text(encoding="utf-8"))
            path=Path(summary["final"])
            saved.append((int(path.stem.split("_")[-1]),path))
    if completed:
        if len(completed)!=1: raise ValueError("ambiguous completed run")
        return completed[0],None,None
    if not saved:
        if original.exists(): raise ValueError("run has no committed checkpoint; inspect its artifacts")
        return None,None,original
    step,path=max(saved,key=lambda v:v[0])
    if step>=steps:
        # Recovery between final snapshot and result.json: derive result without training.
        _,meta=MADDPG.load(path)
        return dict(best=meta["best"],final=str(path.resolve()),initial_rmse_w=meta["history"][0]["validation_rmse_w"],
            final_rmse_w=meta["history"][-1]["validation_rmse_w"],run_id=run_id,config=meta["config"]),None,None
    destination=root/f"{name}_run_{run_id}_resume_{step}"
    if destination.exists(): raise ValueError("resume destination exists; inspect interrupted run before proceeding")
    return None,path,destination


def run(protocol,output,workers=3,resume_study=False):
    torch.set_num_threads(1)
    spec,p,base=read_protocol(protocol)
    config={"seed":42,"spec":spec,"training_protocol":p,"base_config":base}
    if resume_study:
        root=Path(output)
        if yaml.safe_load((root/"config.yaml").read_text(encoding="utf-8"))!=config:
            raise ValueError("resume study protocol/config changed")
        if (root/"selection.json").exists() or (root/"test").exists():
            raise ValueError("study already frozen; do not repeat selection/test")
        bank_hash=digest(root/"bank"/"manifest.json")
        load_cases(root/"bank","validation")
    else:
        root=fresh_output(output,config)
        bank_hash=freeze_bank(base,p,root/"bank")
    (root/"summary.txt").write_text("status=running; test locked\n",encoding="utf-8")
    bank=root/"bank"
    results={c["name"]:[] for c in spec["candidates"]}
    os.environ["OMP_NUM_THREADS"]="1"; os.environ["MKL_NUM_THREADS"]="1"
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[]
        for c in spec["candidates"]:
            for i in spec["run_ids"]:
                finished,resume,destination=recover_job(root,c["name"],i,spec["steps"])
                if finished is not None: results[c["name"]].append(finished)
                else: futures.append(pool.submit(worker,base,p,c,bank,destination,spec["steps"],i,resume))
        if resume_study and (root/"baseline_validation.csv").exists():
            records=read_csv(root/"baseline_validation.csv"); baselines={}
            for mode in ("p","pi"):
                chosen=min((r for r in records if r["controller"]==mode),key=lambda r:float(r["validation_rmse_w"]))
                baselines[mode]=dict(base["baselines"],kp=float(chosen["kp"]),ki=float(chosen["ki"]))
        else:
            baselines=tune_baselines(base,p,spec,bank,root)
        print("P/PI validation selection complete; test remains locked",flush=True)
        for future in as_completed(futures):
            name,r=future.result(); results[name].append(r)
            progress=[dict(candidate=n,run_id=v["run_id"],initial_validation_rmse_w=v["initial_rmse_w"],best_validation_rmse_w=v["best"]["score_w"],final_validation_rmse_w=v["final_rmse_w"],selected_step=v["best"]["step"],final_degradation_ratio=v["final_rmse_w"]/v["best"]["score_w"]) for n in results for v in sorted(results[n],key=lambda z:z["run_id"])]
            write_csv(root/"metrics.csv",progress)
            print(json.dumps(progress[-1]) if len(results[name])==3 else f"Completed {name} run {r['run_id']}",flush=True)
    for name in results: results[name].sort(key=lambda r:r["run_id"])
    ranks={name:validation_rank(runs) for name,runs in results.items()}
    winner=min(results,key=lambda name:ranks[name])
    selection={"spec":spec,"winner":winner,"ranks":ranks,"results":results,"baselines":baselines,"bank_sha256":bank_hash,
        "hashes":{path:digest(path) for runs in results.values() for r in runs for path in (r["best"]["checkpoint"],r["final"])}}
    (root/"selection.json").write_text(json.dumps(selection,indent=2),encoding="utf-8")
    print(f"Frozen winner={winner}; opening test once",flush=True)
    print(json.dumps(locked_test(root),indent=2),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol",default=str(PROTOCOL)); parser.add_argument("--output",required=True)
    parser.add_argument("--workers",type=int,default=3)
    parser.add_argument("--resume-study",action="store_true")
    args=parser.parse_args()
    if not 1<=args.workers<=3: parser.error("workers must be between 1 and 3")
    existed=Path(args.output).exists()
    try: run(args.protocol,args.output,args.workers,args.resume_study)
    except Exception as exc:
        if not existed and Path(args.output).exists():
            (Path(args.output)/"failure.json").write_text(json.dumps({"error":type(exc).__name__,"message":str(exc)}),encoding="utf-8")
        raise
