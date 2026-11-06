"""One frozen independent test for the user's family-average PI criterion."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from . import forecast_speed_training as formal

ROOT = formal.EXPS / "20261105_forecast_speed_independent"
PROTOCOL = Path(__file__).with_name("FORECAST_SPEED_USER_TEST_PROTOCOL.md")
BASE = "3941510c785771ab569771bce974399285fdb983"
NS = tuple(range(69000000, 69000018))
FAMILIES = ("stationary", "ramp", "gust")
MIB = formal.MIB


def shared_store():
    return formal.Store(ROOT,36*MIB,shared=True)


def scan_namespace():
    collisions,scanned=[],0
    def entries(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in ("episode","source_episode") and type(v) is int and v in NS:
                    yield v
                yield from entries(v)
        elif isinstance(value,list):
            for v in value:
                yield from entries(v)
    for repo in (formal.REPO,formal.ORIGIN,formal.PITCH):
        paths=subprocess.check_output(["rg","--files","--hidden","--no-ignore","-g","*.json",
                                       str(repo/"optimization_control")],encoding="utf-8")
        for name in paths.splitlines():
            path=Path(name)
            if path.is_relative_to(ROOT):
                continue
            scanned+=1
            raw=path.read_bytes()
            if re.search(rb"(?<!\d)690000(?:0[0-9]|1[0-7])(?!\d)",raw):
                collisions.extend(dict(path=name,episode=n) for n in entries(json.loads(raw.decode("utf-8-sig"))))
    return dict(scanned_json=scanned,collisions=collisions,episode_range=list(NS),
                checks_actual_episode_fields=True)


def prepare():
    import yaml
    source=formal.context()
    proposal=formal.read(formal.ROOT/"future_test_proposal.json")
    selection=formal.read(formal.ROOT/"selection.json")
    assert formal.git("rev-parse","HEAD").decode().strip()==BASE
    assert tuple(proposal["namespace"])==NS and not proposal["released"]
    assert proposal["selection_sha"]==formal.sha(formal.ROOT/"selection.json")
    assert (proposal["seed"],tuple(proposal["wind_families"]),proposal["targets_w"],
            proposal["initial_pitch_rad"],proposal["nominal_horizon"])==(
            42,FAMILIES,[2.75e6,3.35e6,3.85e6],[.025,.055],128)
    jobs={(j["arm"],j["run"]):j for j in selection["jobs"]}
    roles=[]
    hashes=dict(source["hashes"])
    for r in proposal["roles"]:
        arm,run,role=r["arm"],r["run"],r["role"]
        point=jobs[arm,run][role]
        assert r["step"]==point["step"] and r["snapshot"]==point["snapshot"]
        path=formal.verify(r["snapshot"])
        hashes[str(path)]=r["snapshot"]["sha256"]
        roles.append(dict(**r,kind="policy",id=f"{arm}{run}_{role}"))
    assert [r["step"] for r in roles if r["arm"]=="C" and r["role"]=="selected"]==[0,0,4096]
    roles.extend(dict(kind="parent",id=f"parent{run}",run=run,source=source["parents"][run]) for run in range(3))
    roles.extend(dict(kind="baseline",id=mode,mode=mode) for mode in ("p","pi"))
    assert len(roles)==len({r["id"] for r in roles})==23
    for ref in source["banks"].values():
        hashes[ref["path"]]=ref["sha256"]
    data_sources=[formal.ROOT/"selection.json",formal.ROOT/"future_test_proposal.json",
        formal.ROOT/"pressure.csv",formal.ROOT/"verification.json",formal.ROOT/"takeover.csv",
        formal.EXPS/"20261029_history_forecast/bank_manifest.json",
        formal.EXPS/"20261029_history_independent_test/bank/manifest.json",
        PROTOCOL,Path(__file__),Path(__file__).with_name("forecast_speed_user_test_report.py"),
        Path(__file__).with_name("forecast_speed_report.py")]
    hashes.update({str(p):formal.sha(p) for p in data_sources})
    assert formal.read(formal.ROOT/"verification.json")["passed_takeover"]==21
    scan=scan_namespace()
    ROOT.mkdir(exist_ok=False)
    s=shared_store()
    s.json("namespace_check.json",scan)
    if scan["collisions"]:
        raise ValueError("test episodes already generated")
    config=dict(seed=42,source_head=BASE,primary="C_selected",comparator="shared_PI",
        primary_metric="equal_case_and_parent_stream_mean_RMSE_W_each_family_strictly_below_PI",
        families=list(FAMILIES),targets_w=[2.75e6,3.35e6,3.85e6],initial_pitch_rad=[.025,.055],
        episode_range=list(NS),horizon=128,dt_s=1,split="test",n_roles=23,physical_rollouts=414,
        planned_rows=53406,precheck_rows=0,row_hard_cap=55000,disk_hard_cap_MiB=128,
        shared_partition_MiB=36,role_partition_MiB=4,bootstrap_samples=2000,bootstrap_seed=42,
        plot_case=17,plot_parent_stream=2,formal_RL_steps=0,optimizer_updates=0,
        fixed_PI=source["base_config"]["baselines"],test_release_once=True)
    ref=s.write("config.yaml",yaml.safe_dump(config,allow_unicode=True,sort_keys=False).encode())
    hashes[ref["path"]]=ref["sha256"]
    s.json("lock.json",dict(source=source,hashes=hashes,roles=roles,config=config,
        selection_sha=proposal["selection_sha"],model_queries_before_release=0,
        reuse_zero_speed_exact_cases=21,roles_deduplicated=False))


def context():
    lock=formal.read(ROOT/"lock.json")
    for path,digest in lock["hashes"].items():
        formal.verify(dict(path=path,sha256=digest))
    return lock


def release():
    import numpy as np
    from ..environments.farm_inflow import generate_inflow
    lock=context()
    s=shared_store()
    fresh=scan_namespace()
    if fresh["collisions"]:
        raise ValueError("test namespace occupied since prepare")
    s.json("release_attempt.json",dict(namespace=fresh,lock_sha=formal.sha(ROOT/"lock.json")))
    old=set()
    for name in ("train0","train1","train2","validation"):
        old.update(hashlib.sha256(w.astype(np.float32).tobytes()).hexdigest()
                   for _,w in formal.bank(lock["source"],name))
    previous=formal.read(formal.EXPS/"20261029_history_forecast/bank_manifest.json")
    old.update(x["values_sha256"] for x in previous["fit"]+previous["score"])
    old_test=formal.read(formal.EXPS/"20261029_history_independent_test/bank/manifest.json")
    old.update(x["values_sha256"] for x in old_test["cases"])
    seen=set()
    cases,winds=[],[]
    for family in FAMILIES:
        for target in lock["config"]["targets_w"]:
            for pitch in lock["config"]["initial_pitch_rad"]:
                n=len(cases)
                inflow=deepcopy(lock["source"]["base_config"]["environment"]["inflow"])
                inflow["speed"]["scenario"]=family
                trace=generate_inflow(inflow,dt_s=1,horizon=128,seed=42,split="test",episode=NS[n])
                wind=trace.values.astype(np.float32)
                digest=hashlib.sha256(wind.tobytes()).hexdigest()
                assert digest not in old and digest not in seen and wind.shape==(129,3)
                seen.add(digest)
                cases.append(dict(id=f"test_{n:02d}_{family}_{int(target)}_pitch{round(1000*pitch):03d}",
                    family=family,split="test",target_w=target,pitch_rad=pitch,episode=NS[n],wind_sha=digest))
                winds.append(wind)
    assert len(winds)==18
    bank=s.arrays("bank/test.npz",wind=np.stack(winds),meta=np.array(json.dumps(cases)))
    s.json("bank/manifest.json",dict(cases=cases,bank=bank,unique_float32=18,prior_waveform_hashes=len(old)))
    s.json("release.json",dict(lock_sha=formal.sha(ROOT/"lock.json"),bank_manifest_sha=formal.sha(ROOT/"bank/manifest.json"),
        banks={"test":bank},selection_sha=lock["selection_sha"],frozen=True,model_rows=0))
    print("Released 18 fixed independent winds, 0 model rows.",flush=True)


def evaluation_context():
    lock=context()
    release=formal.read(ROOT/"release.json")
    assert release["lock_sha"]==formal.sha(ROOT/"lock.json")
    assert release["bank_manifest_sha"]==formal.sha(ROOT/"bank/manifest.json")
    assert release["selection_sha"]==lock["selection_sha"]
    cases=formal.bank(release,"test")
    assert tuple(x["episode"] for x,_ in cases)==NS
    return lock,cases


def worker(part):
    import torch
    lock,cases=evaluation_context()
    assert (ROOT/"run_attempt.json").exists()
    world=formal.World(lock["source"])
    for role in lock["roles"][part::3]:
        start=time.perf_counter()
        if role["kind"]=="policy":
            policy=formal.inference(lock["source"],role["snapshot"],role["arm"],role["run"],role["step"])
        elif role["kind"]=="parent":
            policy,_=formal.fresh(lock["source"],"A",role["run"])
        else:
            policy=None
        rng=torch.get_rng_state().clone()
        local=formal.Store(ROOT/"jobs"/role["id"],4*MIB)
        scope=formal.QueryScope(local,"evaluation",2322,role=role,release_sha=formal.sha(ROOT/"release.json"))
        scores,trace=formal.evaluate(world,scope,cases,policy,mode=role.get("mode"))
        assert torch.equal(rng,torch.get_rng_state()) and trace.shape==(18,129,len(formal.TRACE))
        result=formal.save_eval(local,"evaluation",scores,trace)
        scope.finish(eval=result,role=role,elapsed_s=time.perf_counter()-start)
        print(role["id"],scope.actual,f"{time.perf_counter()-start:.1f}s",flush=True)


def run():
    lock,_=evaluation_context()
    s=shared_store()
    s.json("run_attempt.json",dict(release_sha=formal.sha(ROOT/"release.json"),roles=23,workers=3,formal_rows=53406,
        max_rows=55000,query_precheck=0))
    def launch(part):
        cmd=[sys.executable,"-B","-X","utf8","-m",
             "optimization_control.maddpg_wind_farm.forecast_speed_user_test","worker","--part",str(part)]
        p=subprocess.Popen(cmd,cwd=formal.REPO,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                           creationflags=subprocess.CREATE_NO_WINDOW,text=True,encoding="utf-8",errors="replace")
        log=[]
        for line in p.stdout:
            print(f"worker{part}",line.rstrip(),flush=True)
            log.append(line)
        status=p.wait()
        return dict(part=part,command=cmd,pid=p.pid,status=status,log="".join(log))
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts=list(pool.map(launch,range(3)))
    for r in receipts:
        s.write(f"processes/part{r['part']}.log",r.pop("log").encode())
    s.json("processes/complete.json",receipts)
    if any(r["status"] for r in receipts):
        raise RuntimeError("test attempt failed; original reservations preserved")
    results=[]
    for role in lock["roles"]:
        path=ROOT/"jobs"/role["id"]/"evaluation/complete.json"
        receipt=formal.read(path)
        assert receipt["rows"]==2322 and receipt["role"]==role
        results.append(dict(path=str(path),sha256=formal.sha(path)))
    assert len(list(ROOT.rglob("reserved.json")))==23
    context()
    s.json("complete.json",dict(results=results,roles=23,rollouts=414,test_winds=18,rows=53406,
        additional_queries=0,formal_RL_steps=0,optimizer_updates=0,new_weights=0,selection_sha=lock["selection_sha"]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase",choices=("prepare","release","run","worker"))
    parser.add_argument("--part",type=int,choices=(0,1,2))
    args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(formal.ORIGIN/".venv/pinn_tf216")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS","1")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS","1")
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(42)
    if args.phase=="worker":
        worker(args.part)
    else:
        {"prepare":prepare,"release":release,"run":run}[args.phase]()


if __name__=="__main__":
    main()
