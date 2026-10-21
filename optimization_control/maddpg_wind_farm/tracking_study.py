"""One-factor joint wind/target sampling study following reachability diagnosis."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
import json
import os
from pathlib import Path
import numpy as np
import torch
import yaml
from .algorithm import MADDPG
from .benchmark import case_trace, digest, load_cases, evaluate_cases
from .mixed_stability import worker, recover_job, tune_baselines, read_csv
from .stable_workflow import load_protocol, DEFAULT, run_config
from .workflow import fresh_output, write_csv

PROTOCOL=Path(__file__).parent/"configs"/"tracking_study.yaml"
REGULAR=["fixed","stationary","ramp","gust","direction"]
GROUPS=("baseline","stratified")


def read_protocol(path):
    spec=yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if spec["version"]!="tracking_study_v1" or spec["seed"]!=42 or spec["test_rule"]!="freeze_both_groups_and_baselines_before_test":
        raise ValueError("unsupported tracking protocol")
    if len(set(spec["run_ids"]))!=len(spec["run_ids"]) or len(spec["run_ids"])<3:
        raise ValueError("at least three distinct paired runs required")
    p,base=load_protocol(DEFAULT)
    if spec["steps"]<=0 or spec["steps"]%p["eval_every"] or spec["bank_episode_offset"]<170000:
        raise ValueError("full validation intervals and fresh case bank required")
    p["selection_families"]=spec["selection_families"]
    return spec,p,base


def freeze_tracking_bank(base,spec,directory):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=False)
    manifest={"version":"farm_benchmark_v1","seed":42,"cases":[]}
    for split in ("validation","test"):
        points=[]; b=spec["bank"][split]
        for wind in b["fixed_winds"]:
            points.extend(("fixed",wind,t) for t in spec["regular_targets_w"])
        for wind in b["low_winds"]:
            points.extend(("low_power",wind,t) for t in b["low_targets"])
            points.append(("low_shortfall",wind,b["high_target"]))
        for family in REGULAR[1:]:
            points.extend((family,None,t) for t in spec["regular_targets_w"])
        for j,(family,wind,target) in enumerate(points):
            trace=case_trace(base,"fixed" if wind is not None else family,split=split,episode=spec["bank_episode_offset"]+j)
            if wind is not None:
                trace.values[:,0]=wind; trace.components[:]=0; trace.components[:,0]=wind
                trace.metadata.update(override_family=family,override_wind_m_s=wind)
            case_id=f"{split}_{family}_{j}"
            path=directory/f"{case_id}.csv"; trace.save(path)
            manifest["cases"].append(dict(id=case_id,split=split,family=family,path=path.name,
                csv_sha256=digest(path),json_sha256=digest(path.with_suffix(".json")),target_w=target))
    (directory/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return digest(directory/"manifest.json")


def family_mean(rows,families,key="rmse_w"):
    means=[]
    for family in families:
        values=[float(r[key]) for r in rows if r["family"]==family]
        if not values or not np.all(np.isfinite(values)): raise ValueError("missing/nonfinite family")
        means.append(np.mean(values))
    return float(np.mean(means))


def aggregate(rows):
    output=[]
    for label in dict.fromkeys(r["controller"] for r in rows):
        subset=[r for r in rows if r["controller"]==label]
        for name,families,key in (("regular",REGULAR,"rmse_w"),("fixed",["fixed"],"rmse_w"),
                ("low_power",["low_power"],"rmse_w"),("low_shortfall_raw",["low_shortfall"],"rmse_w"),
                ("low_shortfall_floor",["low_shortfall"],"certified_shortfall_floor_w"),
                ("low_shortfall_residual",["low_shortfall"],"residual_shortfall_w")):
            values=[family_mean([r for r in subset if r["run_id"]==run],families,key) for run in sorted(set(r["run_id"] for r in subset))]
            output.append(dict(controller=label,metric=name,mean_w=float(np.mean(values)),
                std_w=float(np.std(values,ddof=1)) if len(values)>1 else 0.,runs=len(values)))
    return output


def locked_test(root):
    root=Path(root); torch.set_num_threads(1)
    selection=json.loads((root/"selection.json").read_text(encoding="utf-8"))
    config=yaml.safe_load((root/"config.yaml").read_text(encoding="utf-8"))
    spec=config["spec"]; base=config["base_config"]
    if digest(root/"bank"/"manifest.json")!=selection["bank_sha256"]: raise ValueError("changed bank")
    for path,value in selection["hashes"].items():
        if digest(path)!=value: raise ValueError("changed frozen model")
    out=fresh_output(root/"test",dict(seed=42,selection_sha256=digest(root/"selection.json")))
    cases=load_cases(root/"bank","test",allow_test=True)
    rows=[]; checks=[]
    for name,runs in selection["results"].items():
        for r in runs:
            for stage in ("selected","final"):
                agent,meta=MADDPG.load(r["best"]["checkpoint"] if stage=="selected" else r["final"])
                metrics=evaluate_cases(meta["config"],cases,agent=agent,timing=True,decomposition=True)
                rows.extend(dict(controller=f"{name}_{stage}",run_id=r["run_id"],**v) for v in metrics)
                if stage=="selected":
                    fixed=np.mean([v["rmse_w"] for v in metrics if v["family"]=="fixed" and v["target_w"]==3e6])
                    ratio=r["final_rmse_w"]/r["best"]["score_w"]
                    checks.append(dict(candidate=name,run_id=r["run_id"],selected_step=r["best"]["step"],
                        validation_improved=r["best"]["score_w"]<r["initial_rmse_w"],final_degradation_ratio=ratio,
                        fixed_3mw_rmse_w=float(fixed),fixed_gate_passed=bool(fixed<=spec["acceptance"]["fixed_3mw_rmse_w"])))
    cfg=run_config(base,spec["candidate"],[1,1,1])
    for mode in ("p","pi"):
        for variant in ("default","tuned"):
            bc=deepcopy(cfg)
            if variant=="tuned": bc["baselines"]=selection["baselines"][mode]
            rows.extend(dict(controller=f"{mode}_{variant}",run_id=-1,**v) for v in evaluate_cases(bc,cases,baseline=mode,timing=True,decomposition=True))
    write_csv(out/"metrics.csv",rows)
    summary_rows=aggregate(rows); write_csv(root/"test_summary.csv",summary_rows)
    paired=[]
    for run in spec["run_ids"]:
        for stage in ("selected","final"):
            delta={}
            for label,families,key in (("regular",REGULAR,"rmse_w"),("fixed",["fixed"],"rmse_w"),
                    ("low_power",["low_power"],"rmse_w"),("low_shortfall_residual",["low_shortfall"],"residual_shortfall_w")):
                means=[family_mean([r for r in rows if r["controller"]==f"{name}_{stage}" and r["run_id"]==run],families,key) for name in GROUPS]
                delta[label+"_delta_w"]=means[1]-means[0]
            paired.append(dict(run_id=run,stage=stage,**delta))
    acceptance=all(r["regular_delta_w"]<=0 and r["fixed_delta_w"]<0 and r["low_shortfall_residual_delta_w"]<0 for r in paired if r["stage"]=="selected")
    gate=all(r["validation_improved"] and r["fixed_gate_passed"] and r["final_degradation_ratio"]<=spec["acceptance"]["max_final_over_selected_validation_ratio"] for r in checks if r["candidate"]=="stratified")
    summary=dict(status="complete",aggregate=summary_rows,paired=paired,checks=checks,
        targeted_improvement_acceptance=acceptance,full_stability_gate_passed=gate,test_used_for_selection=False,
        baselines=selection["baselines"],scope="exact mock only; residual includes actuator transients; three paired runs are descriptive evidence",
        training_steps_total=2*len(spec["run_ids"])*spec["steps"],
        command="python -m optimization_control.maddpg_wind_farm.tracking_study --output <new-directory>",
        artifacts=["selection.json","test/metrics.csv","test_summary.csv","comparison.png","<group>_run_<id>/normalization.json"])
    for path in (root/"summary.txt",out/"summary.txt"):
        path.write_text(json.dumps(summary,indent=2),encoding="utf-8")
    plot(root,selection,summary_rows)
    return summary


def plot(root,selection,rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(17,5))
    for name,runs in selection["results"].items():
        histories=[read_csv(Path(r["final"]).parent/"metrics.csv") for r in runs]
        values=np.array([[float(v["validation_rmse_w"])/1000 for v in h] for h in histories])
        steps=[int(v["steps"]) for v in histories[0]]
        axes[0].plot(steps,values.mean(0),label=name)
        axes[0].fill_between(steps,values.min(0),values.max(0),alpha=.15)
    axes[0].set(xlabel="Training steps",ylabel="Validation RMSE [kW]",title="Three paired runs: mean/range"); axes[0].legend()
    for ax,metric in zip(axes[1:],("fixed","low_shortfall_residual")):
        selected=[r for r in rows if r["metric"]==metric and (r["controller"].endswith("selected") or r["controller"].endswith("tuned"))]
        ax.barh([r["controller"] for r in selected],[r["mean_w"]/1000 for r in selected],xerr=[r["std_w"]/1000 for r in selected])
        ax.set(xlabel="Error [kW]",title=metric+" | held-out")
    fig.suptitle("Joint wind/target sampling intervention | integration mock only")
    fig.tight_layout(); fig.savefig(root/"comparison.png",dpi=140); plt.close(fig)


def run(protocol,output,workers=3,resume_study=False):
    torch.set_num_threads(1)
    spec,p,base=read_protocol(protocol)
    config=dict(seed=42,spec=spec,training_protocol=p,base_config=base)
    if resume_study:
        root=Path(output)
        if yaml.safe_load((root/"config.yaml").read_text(encoding="utf-8"))!=config: raise ValueError("changed resume protocol")
        if (root/"selection.json").exists() or (root/"test").exists(): raise ValueError("already frozen; no repeat selection/test")
        load_cases(root/"bank","validation")
        bank_hash=digest(root/"bank"/"manifest.json")
    else:
        root=fresh_output(output,config); bank_hash=freeze_tracking_bank(base,spec,root/"bank")
    (root/"summary.txt").write_text("status=running; test locked\n",encoding="utf-8")
    results={name:[] for name in GROUPS}
    os.environ["OMP_NUM_THREADS"]="1"; os.environ["MKL_NUM_THREADS"]="1"
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[]
        for name in GROUPS:
            pp=deepcopy(p)
            if name=="stratified": pp["tracking_curriculum"]=spec["tracking_curriculum"]
            for run_id in spec["run_ids"]:
                finished,resume,destination=recover_job(root,name,run_id,spec["steps"])
                if finished is not None: results[name].append(finished)
                else: futures.append(pool.submit(worker,base,pp,dict(name=name,**spec["candidate"]),root/"bank",destination,spec["steps"],run_id,resume))
        if resume_study and (root/"baseline_validation.csv").exists():
            records=read_csv(root/"baseline_validation.csv"); baselines={}
            for mode in ("p","pi"):
                chosen=min((r for r in records if r["controller"]==mode),key=lambda r:float(r["validation_rmse_w"]))
                baselines[mode]=dict(base["baselines"],kp=float(chosen["kp"]),ki=float(chosen["ki"]))
        else: baselines=tune_baselines(base,p,spec,root/"bank",root)
        print("Validation P/PI tuning complete; independent test locked",flush=True)
        for future in as_completed(futures):
            name,result=future.result(); results[name].append(result)
            print(f"Completed {name} run {result['run_id']}",flush=True)
    for name in results: results[name].sort(key=lambda r:r["run_id"])
    write_csv(root/"metrics.csv",[dict(candidate=name,run_id=r["run_id"],initial_validation_rmse_w=r["initial_rmse_w"],
        best_validation_rmse_w=r["best"]["score_w"],final_validation_rmse_w=r["final_rmse_w"],selected_step=r["best"]["step"],
        final_degradation_ratio=r["final_rmse_w"]/r["best"]["score_w"]) for name in results for r in results[name]])
    selection=dict(results=results,baselines=baselines,bank_sha256=bank_hash,
        hashes={path:digest(path) for runs in results.values() for r in runs for path in (r["best"]["checkpoint"],r["final"])})
    (root/"selection.json").write_text(json.dumps(selection,indent=2),encoding="utf-8")
    print("Both groups frozen; opening new independent test once",flush=True)
    summary=locked_test(root)
    print(json.dumps({k:summary[k] for k in ("status","targeted_improvement_acceptance","full_stability_gate_passed")}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol",default=str(PROTOCOL)); parser.add_argument("--output",required=True)
    parser.add_argument("--workers",type=int,default=3); parser.add_argument("--resume-study",action="store_true")
    args=parser.parse_args(); run(args.protocol,args.output,args.workers,args.resume_study)
