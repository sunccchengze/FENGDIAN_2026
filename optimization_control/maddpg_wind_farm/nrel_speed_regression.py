"""One fixed-bank NREL configuration regression; frozen policies, no training."""
import argparse
import os
from pathlib import Path

from . import nrel_speed_transfer as transfer
from . import yaw_independent_test as original

old=transfer.old
ROOT=old.EXPS/"20261106_nrel_speed_regression"
PROTOCOL=Path(__file__).with_name("NREL_SPEED_REGRESSION_PROTOCOL_20261106.md")
BASE="03a769459c1d538792904afa2c83ade95d6e090e"
CONTROLLERS=("Y0_selected","Y1_selected","Y2_selected","p","pi")
MIB=1024**2


def store():
    return old.Store(ROOT,32*MIB)


def context():
    lock=old.read(ROOT/"lock.json")
    for path,sha in lock["hashes"].items():old.verify(dict(path=path,sha256=sha))
    return lock


def cases(lock):
    import numpy as np
    data=old.bank(lock["release"],"test")
    assert [x[0]["episode"] for x in data]==list(range(74000000,74000018))
    return [(case,wind.astype(np.float32)) for case,wind in data]


def metric(trace,case,rule):
    import numpy as np
    row=transfer.metric(trace,case,rule)
    e=trace[1:,3]/1000;bias=float(e.mean());variance=float(np.mean((e-bias)**2));mse=float(np.mean(e**2))
    assert abs(mse-bias*bias-variance)<1e-7
    applied=trace[:,19:28].reshape(129,3,3)
    pitch=np.abs(np.diff(applied[:,:,1],axis=0));speed=np.abs(np.diff(applied[:,:,2],axis=0))
    heading=np.abs(np.diff(trace[:,16:19],axis=0))
    row.update(bias_kW=bias,bias_sq_kW2=bias*bias,variance_kW2=variance,mse_kW2=mse,
        over_fraction=float(np.mean(e>0)),under_fraction=float(np.mean(e<0)),equal_fraction=float(np.mean(e==0)),
        pitch_rate_boundary_fraction=float(np.mean(pitch>=.00872664626-1e-7)),
        pitch_rate_boundary_samples=int(np.sum(pitch>=.00872664626-1e-7)),
        speed_rate_boundary_fraction=float(np.mean(speed>=.1-1e-7)),
        heading_rate_boundary_fraction=float(np.mean(heading>=.005-1e-7)),
        episode=case["episode"])
    return row


def prepare():
    import numpy as np
    import yaml
    from .yaw_pilot_report import read_eval
    from .nrel_speed_adapter import LOW,HIGH,SLOPE,SCHEMA
    assert old.git("rev-parse","HEAD").decode().strip()==BASE
    source=transfer.context()
    release=old.read(original.ROOT/"release.json")
    assert release["lock_sha"]==old.sha(original.ROOT/"lock.json")
    assert release["selection_sha"]==source["source"]["selection_sha"]
    old.verify(release["bank_manifest"])
    bank=old.bank(release,"test")
    physical=[(case,w.astype(np.float32)) for case,w in bank]
    assert [x[0]["episode"] for x in physical]==list(range(74000000,74000018))
    assert all(sum(c["family"]==f for c,_ in physical)==6 for f in original.FAMILIES)
    hashes=dict(source["hashes"]);references={}
    completed=old.read(original.ROOT/"complete.json")
    physical_hashes=[]
    for case,wind in physical:
        physical_hashes.append(dict(case_id=case["id"],episode=case["episode"],
            raw_saved_wind_sha=case["wind_sha"],actual_float32_wind_sha=old.hashlib.sha256(wind.tobytes()).hexdigest()))
    for name in CONTROLLERS:
        ref=next(x for x in completed["results"] if Path(x["path"]).parent.name==name)
        entry=old.read(old.verify(ref))
        role=next(r for r in source["source"]["roles"] if r["id"]==name)
        assert entry["role"]==role and entry["optimizer_updates_during_test"]==0
        assert entry["counters_before"]==entry["counters_after"] and len(entry["cases"])==18
        if name.startswith("Y"):
            assert role==next(r for r in source["roles"] if r["id"]==name)
        hashes[ref["path"]]=ref["sha256"];refs=[]
        for receipt,(case,wind) in zip(entry["cases"],physical,strict=True):
            result=old.read(old.verify(receipt));reservation=old.read(old.verify(result["reservation"]))
            assert result["rows"]==result["partition_accounting"]["actual"]==129
            assert reservation["role"]==role and reservation["case"]==case
            assert reservation["release_sha"]==old.sha(original.ROOT/"release.json")
            rows,traces=read_eval(result["eval"],[(case,wind)],"Y" if name.startswith("Y") else "baseline")
            assert traces.shape==(1,129,52) and rows[0]["case_id"]==case["id"]
            for value in [receipt,result["reservation"],*result["eval"].values()]:
                hashes[value["path"]]=value["sha256"]
            refs.append(dict(case_id=case["id"],receipt=receipt,eval=result["eval"]))
        references[name]=dict(role=role,complete=ref,cases=refs)
    cfg=dict(seed=42,base_commit=BASE,start_commit="7656428641538fb63e0d6872dfbc930a92177cf6",
        purpose="used_test_bank_configuration_regression_not_new_independent_test",controllers=list(CONTROLLERS),
        wind_namespace=list(range(74000000,74000018)),unique_winds=18,rollouts_new=90,rollouts_old_referenced=90,
        horizon=128,dt_s=1,planned_model_rows=11610,model_row_hard_cap=12000,disk_cap_MiB=32,
        old_reference_historical_rows=11610,old_reference_new_rows=0,prior_transfer_rows=4030,prior_diagnostic_rows=1440,
        schema=SCHEMA,radius_m=63,lambda_ref=7.55,speed_slope=SLOPE,physical_speed_bounds=[LOW,HIGH],
        network_command_reward_speed_coordinates=[.6,HIGH],Y_selected_steps=[2048,0,2048],C_selected_steps=[0,0,4096],
        training_steps=0,optimizer_updates=0,new_winds=0,new_pressure_cases=0,
        criterion="each_family_equal_case_and_stream_mean_new_Y_strictly_below_new_PI",
        pitch_rate_boundary_tolerance_rad=1e-7,plot_case=17,plot_stream=2,initial_worktree_status=[])
    ROOT.mkdir(exist_ok=False);s=store()
    cfgref=s.write("config.yaml",yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False).encode())
    oldrefs=s.json("old_references.json",references);winds=s.json("wind_identity.json",physical_hashes)
    paths=[Path(__file__),PROTOCOL,Path(__file__).with_name("nrel_speed_regression_report.py"),
        original.ROOT/"release.json",original.ROOT/"lock.json",original.ROOT/"complete.json",
        old.EXPS/"20261106_nrel_speed_transfer/model_budget.json",old.EXPS/"20261106_nrel_speed_diagnostic/model_budget.json"]
    for p in paths:hashes[str(p)]=old.sha(p)
    for ref in [cfgref,oldrefs,winds,release["bank_manifest"],release["banks"]["test"]]:hashes[ref["path"]]=ref["sha256"]
    s.json("lock.json",dict(hashes=hashes,transfer=source,release=release,config=cfg,old_references=oldrefs,wind_identity=winds))
    print("Frozen 18 existing winds and 5 identities; old90 verified, new90 planned, 11610 rows. New queries0.",flush=True)


def run():
    import numpy as np
    from .causal_speed_search import Budget
    lock,s=context(),store()
    world=transfer.World(lock["transfer"]);budget=Budget(ROOT/"model_budget.json",12000)
    results=[]
    for name in CONTROLLERS:
        receipts=[]
        for index,(case,wind) in enumerate(cases(lock)):
            label=f"new/{name}/{index:02d}"
            done=ROOT/(label+"/complete.json")
            if done.exists():
                saved=old.read(done)
                assert saved["controller"]==name and saved["case"]==case
                for ref in saved["eval"].values():old.verify(ref)
                receipts.append(dict(path=str(done),sha256=old.sha(done)))
                continue
            attempts=[r for r in budget.data["scopes"] if r["name"].startswith(label+"/")]
            attempt=f"{label}/attempt{len(attempts):02d}"
            budget.start(attempt,129)
            try:
                data=transfer.rollout(world,budget,lock["transfer"],name,"nrel",case,wind)
                row=metric(data["trace"],case,"nrel")
                assert data["parameters_frozen"] and data["counters_unchanged"]
                ev=dict(trace=s.arrays(attempt+"/trace.npz",trace=data["trace"],fields=np.array(transfer.TRACE),
                    obs=data["obs"],inputs=data["inputs"]),metrics=s.json(attempt+"/metrics.json",[row]))
                account=budget.finish();assert account["actual"]==129
                ref=s.json(label+"/complete.json",dict(controller=name,case=case,eval=ev,budget=account,
                    normalization=data["normalization"],parameters_frozen=True,counters_unchanged=True,updates=0))
                receipts.append(ref)
            except BaseException as error:
                if budget.active is not None:
                    budget.active["status"]="failed"
                    budget.active["error"]=str(error)
                budget.save();raise
            print(name,f"case{index:02d}","RMSE kW",f"{row['rmse_w']/1000:.6f}",flush=True)
        results.append(dict(controller=name,cases=receipts,rollouts=18,input_rows=2322))
    context()
    charged=sum(x["actual"] if x["status"]=="complete" else x["reserve"] for x in budget.data["scopes"])
    assert charged<=12000 and all(x["status"] in ("complete","failed") for x in budget.data["scopes"])
    actual=sum(x["actual"] for x in budget.data["scopes"])
    s.json("complete.json",dict(results=results,new_model_rows=actual,charged_model_rows=charged,
        failed_scopes=int(sum(x["status"]=="failed" for x in budget.data["scopes"])),new_rollouts=90,old_referenced_rollouts=90,
        unique_winds=18,old_reference_new_rows=0,training_steps=0,optimizer_updates=0,new_winds=0,new_pressure_cases=0,
        schema=lock["config"]["schema"],kind=lock["config"]["purpose"]))
    print("Fixed-bank regression complete: new90, model rows",charged,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("phase",choices=("prepare","run"));args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(old.ORIGIN/".venv/pinn_tf216")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS","1");os.environ.setdefault("TF_NUM_INTEROP_THREADS","1")
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(42)
    dict(prepare=prepare,run=run)[args.phase]()
