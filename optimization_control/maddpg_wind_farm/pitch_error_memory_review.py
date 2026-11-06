"""Locked paired analysis and saved-data figures for the pitch-memory trial."""
from __future__ import annotations

from collections import defaultdict
import io
from pathlib import Path
import math
import statistics

from .pitch_actor_context_review import gates
from .pitch_gamma_review import aggregates, gz_rows
from .pitch_error_memory_trial import (
    ARMS, FAMILIES, ROWS, STATE_CAP, STEPS, SELECTION_STEPS, Meter, Store,
    context, digest, read_csv, read_json, size, verify, episode_metrics,
)


def select(root):
    cfg = context(root)
    assert read_json(root/"entry_audit.json")["status"] == "passed"
    jobs = []
    full, light = [], []
    histories = []
    for run in range(3):
        all_losses = []
        for arm in ARMS:
            folder = root/f"{arm}_run{run}"
            assert not list(folder.glob("failed_*.json"))
            r = read_json(folder/"result.json")
            assert (r["steps"],r["added_updates"],r["added_insertions"]) == (STEPS,7937,STEPS)
            verify(r["hashes"])
            parent = cfg["parents"][str(run)]
            history = []
            losses = []
            assert len(list(folder.glob("step_*/complete.json"))) == 129
            for step in range(0,STEPS+1,128):
                path = folder/f"step_{step:08d}"
                commit = read_json(path/"complete.json")
                verify(commit["hashes"])
                assert commit["step"]==step and commit["insertions"]==parent["insertions"]+step
                count = 0 if step<512 else (step-512)//2+1
                assert commit["updates"]==parent["updates"]+count
                if step:
                    rows = read_csv(path/"losses.csv")
                    losses.extend((int(x["step"]),x["indices_sha256"],x["lengths_sha256"]) for x in rows if "step" in x)
                    assert all((path/n).is_file() for n in ("trace.csv.gz","transitions.npz"))
                    light.append(dict(arm=arm,run=run,step=step,manifest=str(path/"complete.json"),sha256=digest(path/"complete.json")))
                if step % 1024 == 0:
                    p = path/"state.pth"
                    assert commit["full"] and p.stat().st_size<=STATE_CAP
                    full.append(dict(arm=arm,run=run,step=step,path=str(p),sha256=commit["hashes"][str(p)],bytes=p.stat().st_size))
                if step in SELECTION_STEPS:
                    import numpy as np
                    metrics = read_csv(path/"validation/metrics.csv")
                    assert len(metrics)==18
                    history.append(dict(step=step,rmse_w=float(np.mean([float(row["rmse_w"]) for row in metrics]))))
            assert [v[0] for v in losses]==list(range(512,STEPS+1,2))
            assert history==r["history"]
            best = min(history,key=lambda x:(x["rmse_w"],x["step"]))["step"]
            assert best==r["selected_step"] and r["roles"]["selected"]==str(folder/f"step_{best:08d}/state.pth")
            if run==0:
                recovery = read_json(folder/"recovery.json")
                assert recovery["step"]==1024 and recovery["replayed_steps"]==0
                assert recovery["previous_pid"]!=recovery["current_pid"]
            jobs.append(r)
            histories.extend(dict(arm=arm,run=run,**h) for h in history)
            all_losses.append(losses)
        assert all_losses[0]==all_losses[1]
    assert len(full)==102 and len(light)==768 and len(list(root.rglob("*.pth")))==102
    store = Store(root)
    counts = Meter(store).counts
    assert counts==dict(train=99072,validation=69660,known=0,test=0,pressure=0)
    store.table("checkpoint_manifest.csv", full)
    store.table("light_manifest.csv", light)
    store.table("history.csv", histories)
    store.json("selection.json",dict(seed=42,jobs=jobs,rule=cfg["selection_rule"],config_sha=digest(root/"config.yaml"),
               train_steps=98304,updates=47622,indices_and_actual_m_paired_all_runs=True,validation_only=True,
               restart_steps=[1024,1024],recomputed_steps=0))


def role_sources(root, split):
    entries = read_json(root/f"{split}_index.json")
    if split=="validation":
        for result in read_json(root/"selection.json")["jobs"]:
            for role,path in result["roles"].items():
                entries.append(dict(arm=result["arm"],run=result["run"],role=role,
                                    cases=str(Path(path).parent/"validation/cases.json")))
    return entries


def resolve(entry):
    if "legacy_reference" in entry:
        reference = entry["legacy_reference"]
        verify({reference["metrics"]:reference["metrics_sha256"],reference["traces"]:reference["traces_sha256"]})
        groups = defaultdict(list)
        for row in gz_rows(reference["traces"]):
            groups[row["case_id"]].append(row)
        return read_csv(reference["metrics"]), groups
    manifest = read_json(entry["cases"])
    verify({manifest["metrics"]:manifest["metrics_sha256"]})
    verify({case["path"]:case["sha256"] for case in manifest["traces"].values()})
    return read_csv(manifest["metrics"]), {key:gz_rows(case["path"]) for key,case in manifest["traces"].items()}


def audit_case(saved, trace, design, values, has_memory):
    import numpy as np
    assert len(trace)==128 and [int(r["response_step"]) for r in trace]==list(range(1,129))
    assert np.array_equal([float(r["decision_wind_m_s"]) for r in trace], values[:-1,0])
    assert np.array_equal([float(r["response_wind_m_s"]) for r in trace], values[1:,0])
    assert np.array_equal([float(r["wind_direction_rad"]) for r in trace], values[1:,1])
    assert all(float(r["target_w"])==float(design["target_w"]) and
               float(r["initial_pitch_rad"])==float(design["initial_pitch_rad"]) for r in trace)
    computed = episode_metrics(trace)
    for key,value in computed.items():
        if key in ("case_id","split","family"):
            assert saved[key]==value
        else:
            assert abs(float(saved[key])-float(value))<1e-9
    errors = [float(r["error_w"]) for r in trace]
    mean = math.fsum(errors)/128
    square = math.fsum(e*e for e in errors)/128
    variance = math.fsum((e-mean)**2 for e in errors)/128
    assert math.isclose(float(saved["rmse_w"]),math.sqrt(square),rel_tol=1e-12)
    assert math.isclose(float(saved["mean_error_w"]),mean,abs_tol=1e-9)
    assert math.isclose(float(saved["error_std_w"]),math.sqrt(variance),rel_tol=1e-12)
    assert math.isclose(square,mean*mean+variance,rel_tol=1e-12)
    assert float(saved["pitch_min_rad"])>=-1e-9 and float(saved["pitch_max_rad"])<=.22+1e-9
    assert float(saved["pitch_max_rate_rad_s"])<=.00872664626+1e-9
    if has_memory:
        integral = 0.
        for row in trace:
            assert float(row["integral_rad"])==integral
            inc = .08*float(np.float32(float(row["decision_error_w"])/15e6))
            pitch = [float(row[f"pitch_command_{i}"]) for i in range(3)]
            blocked = (inc>0 and (integral==.02 or max(pitch)==.22)) or (inc<0 and (integral==-.02 or min(pitch)==0.))
            integral = integral if blocked else max(-.02,min(.02,integral+inc))
            assert integral==float(row["next_integral_rad"])
    return dict(saved, bias_squared_w2=mean*mean, error_variance_w2=variance)


def collect(root, split):
    import numpy as np
    from ..environments.farm_inflow import InflowTrace
    if split=="known":
        cases = read_json(root/"known_sources.json")["cases"]
    else:
        manifest = read_json(root/f"{split}_bank/manifest.json")
        verify(manifest["hashes"])
        cases = manifest["cases"]
    design = {c["id"]:c for c in cases}
    values = {c["id"]:InflowTrace.load(c["path"]).values.astype(np.float32) for c in cases}
    sources = role_sources(root,split)
    cached = {}
    output = []
    heading = {}
    for e in sources:
        key = e.get("cases") or e["legacy_reference"]["metrics"]
        if key not in cached:
            ms, traces = resolve(e)
            assert set(traces)==set(design)=={m["case_id"] for m in ms}
            rows = []
            for m in ms:
                case = m["case_id"]
                track = traces[case]
                yaw = np.array([[float(x[f"heading_{j}"]) for j in range(3)] for x in track])
                if case in heading:
                    assert np.max(np.abs(heading[case]-yaw))<=1e-9
                else:
                    heading[case]=yaw
                rows.append(audit_case(m,track,design[case],values[case],e["arm"] in ARMS and "cases" in e))
            cached[key] = rows
        output.extend(dict(arm=e["arm"],role=e["role"],run=e["run"],**row) for row in cached[key])
    assert len(output)==dict(known=612,validation=360,test=880)[split]
    return output


def groups(rows, fields):
    result=defaultdict(list)
    for row in rows:
        result[tuple(row[f] for f in fields)].append(row)
    return result


def mean(rows,key):
    return statistics.fmean(float(r[key]) for r in rows)


def summarize(store,split,rows):
    aggregate=aggregates(rows)
    store.table(f"{split}_aggregate.csv",aggregate)
    cross=[]
    for (arm,role,family),part in groups(aggregate,("arm","role","family")).items():
        averages=[r["mean_rmse_w"] for r in part]
        cross.append(dict(arm=arm,role=role,family=family,streams=len(part),case_mean_rmse_w=statistics.fmean(averages),
                          across_flow_sd_w=statistics.stdev(averages) if len(part)>1 else "",
                          pooled_rmse_w=math.sqrt(statistics.fmean(r["pooled_rmse_w"]**2 for r in part))))
    store.table(f"{split}_cross_stream.csv",cross)
    lookup={(r["arm"],r["run"],r["role"],r["case_id"]):r for r in rows}
    paired=[]
    for r in rows:
        if r["arm"] not in ARMS or r["role"]=="initial":
            continue
        for arm,role,run,ref in [("zero",r["role"],r["run"],"zero"),("zero","initial",r["run"],"parent"),
                                 ("p","p",-1,"p"),("pi","pi",-1,"pi")]:
            b=lookup[arm,run,role,r["case_id"]]
            paired.append(dict(arm=r["arm"],role=r["role"],run=r["run"],case_id=r["case_id"],family=r["family"],
                               target_w=r["target_w"],initial_pitch_rad=r["initial_pitch_rad"],reference=ref,
                               rmse_w=float(r["rmse_w"]),reference_rmse_w=float(b["rmse_w"]),
                               delta_rmse_w=float(r["rmse_w"])-float(b["rmse_w"]),
                               delta_bias_squared_w2=float(r["bias_squared_w2"])-float(b["bias_squared_w2"]),
                               delta_variance_w2=float(r["error_variance_w2"])-float(b["error_variance_w2"])))
    store.table(f"{split}_paired_cases.csv",paired)
    extended=paired+[dict(r,family="routine") for r in paired if r["family"]!="low_wind_stress"]
    if split=="test":
        extended += [dict(r,family="all_including_pressure") for r in paired]
    comparison=[]
    for (arm,role,family,reference),part in groups(extended,("arm","role","family","reference")).items():
        means=[mean(rs,"delta_rmse_w") for rs in groups(part,("run",)).values()]
        comparison.append(dict(arm=arm,role=role,family=family,reference=reference,slots=len(part),
                               delta_mean_rmse_w=mean(part,"delta_rmse_w"),delta_flow_sd_w=statistics.stdev(means),
                               improved=sum(r["delta_rmse_w"]<0 for r in part),worse=sum(r["delta_rmse_w"]>0 for r in part),
                               ratio=mean(part,"rmse_w")/mean(part,"reference_rmse_w")))
    store.table(f"{split}_comparisons.csv",comparison)
    strata=[]
    keys=("arm","role","run","family","target_w","initial_pitch_rad")
    for key,part in groups(rows,keys).items():
        strata.append(dict(zip(keys,key),slots=len(part),case_mean_rmse_w=mean(part,"rmse_w"),bias_w=mean(part,"mean_error_w"),
                           case_sd_w=mean(part,"error_std_w"),bias_squared_w2=mean(part,"bias_squared_w2"),
                           error_variance_w2=mean(part,"error_variance_w2")))
    store.table(f"{split}_target_initial.csv",strata)


def acceptance(rows,exclude_primary=False):
    # Apply the already validated gate formulas to the corresponding arm roles.
    return gates([dict(r,arm={"zero":"replay","memory":"current_pitch"}.get(r["arm"],r["arm"])) for r in rows],exclude_primary)


def pretest(root):
    cfg = context(root)
    assert not (root/"test_bank").exists()
    selection = read_json(root/"selection.json")
    assert selection["config_sha"]==digest(root/"config.yaml")
    for job in selection["jobs"]:
        verify(job["hashes"])
    store=Store(root)
    count=Meter(store).counts
    assert count["train"]==99072 and count["validation"]==74304 and count["test"]==count["pressure"]==0
    known,validation=collect(root,"known"),collect(root,"validation")
    for split,rows in (("known",known),("validation",validation)):
        store.table(f"{split}_metrics.csv",rows)
        summarize(store,split,rows)
    primary=[]
    for role in ("selected","final"):
        for reference,rr in (("parent","initial"),("zero",role)):
            pairs=[]
            for run in range(3):
                candidate=[r for r in known if r["arm"]=="memory" and r["run"]==run and r["role"]==role and r["case_id"].startswith("train_episode_8_")]
                baseline=[r for r in known if r["arm"]=="zero" and r["run"]==run and r["role"]==rr and r["case_id"].startswith("train_episode_8_")]
                assert len(candidate)==len(baseline)==2 and all(float(r["target_w"])==3.8e6 and r["family"]=="stationary" for r in candidate)
                pairs.append(dict(run=run,candidate_w=mean(candidate,"rmse_w"),reference_w=mean(baseline,"rmse_w")))
            ratio=mean(pairs,"candidate_w")/mean(pairs,"reference_w")
            wins=sum(p["candidate_w"]<p["reference_w"] for p in pairs)
            primary.append(dict(role=role,reference=reference,ratio=ratio,improved_flows=wins,passed=ratio<=.95 and wins>=2,flows=pairs))
    known_gate,validation_gate=acceptance(known,True),acceptance(validation)
    noninitial=sum(j["selected_step"]>0 for j in selection["jobs"] if j["arm"]=="memory")
    keys=("retention_pass","pi_count_pass","motion_pass","stability_pass","physical_pass")
    passed=noninitial==3 and all(p["passed"] for p in primary) and all(g[k] for g in (known_gate,validation_gate) for k in keys)
    store.json("development_acceptance.json",dict(passed=passed,noninitial_memory_selected=noninitial,primary=primary,
               known=known_gate,validation=validation_gate,test_cannot_revise=True))
    lock={str(root/name):digest(root/name) for name in ("config.yaml","input_lock.json","selection.json","test_spec.json",
          "checkpoint_manifest.csv","development_acceptance.json","known_metrics.csv","validation_metrics.csv")}
    lock.update(cfg["protected_hashes"])
    for job in selection["jobs"]:
        lock.update(job["hashes"])
    store.json("pretest_lock.json",dict(hashes=lock,model_rows_before_test=count,development_passed=passed,
               formal_steps=98304,updates=47622,test_generation_authorized_by_protocol=True))
    print(dict(pretest_locked=True,development_passed=passed,noninitial=noninitial),flush=True)


def plot(root,store,test,known):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","DejaVu Sans"],"axes.unicode_minus":False})

    def save(fig,name):
        buffer=io.BytesIO()
        fig.tight_layout()
        fig.savefig(buffer,format="png",dpi=150)
        plt.close(fig)
        store.put(name,buffer.getbuffer(),8*1024**2)

    history=read_csv(root/"history.csv")
    jobs=read_json(root/"selection.json")["jobs"]
    fig,axes=plt.subplots(2,3,figsize=(15,9))
    for run in range(3):
        for arm,color in (("zero","#3576b5"),("memory","#db8227")):
            part=[r for r in history if r["arm"]==arm and int(r["run"])==run]
            x=[int(r["step"]) for r in part]
            y=[float(r["rmse_w"])/1000 for r in part]
            selected=next(j["selected_step"] for j in jobs if j["arm"]==arm and j["run"]==run)
            axes[0,run].plot(x,y,"o-",label=arm,color=color)
            axes[0,run].scatter([selected],[y[x.index(selected)]],marker="*",s=140,color=color,edgecolor="black")
        axes[0,run].set(title=f"流 {run}：18 场验证",xlabel="新增训练步",ylabel="完整回合平均 RMSE (kW)")
        labels=["父","恒零选中","恒零终点","记忆选中","记忆终点","PI"]
        bias,var=[],[]
        for arm,role in (("zero","initial"),("zero","selected"),("zero","final"),("memory","selected"),("memory","final"),("pi","pi")):
            part=[r for r in known if r["arm"]==arm and r["role"]==role and r["run"]==(run if arm!="pi" else -1) and r["case_id"].startswith("train_episode_8_")]
            bias.append(mean(part,"bias_squared_w2")/1e12)
            var.append(mean(part,"error_variance_w2")/1e12)
        axes[1,run].bar(range(6),bias,label="平均 bias²")
        axes[1,run].bar(range(6),var,bottom=bias,label="平均方差")
        axes[1,run].set(title=f"流 {run}：已知 3.8 MW 两初态",ylabel="MSE (MW²)",xticks=range(6),xticklabels=labels)
        axes[1,run].tick_params(axis="x",labelrotation=23)
        for ax in axes[:,run]:
            ax.legend(fontsize=8)
            ax.grid(axis="y",alpha=.2)
    save(fig,"validation_and_decomposition.png")

    cross=read_csv(root/"test_cross_stream.csv")
    fig,axes=plt.subplots(2,3,figsize=(15,9))
    families=(*FAMILIES,"routine","low_wind_stress","all_including_pressure")
    for ax,family in zip(axes.flat,families):
        keys=[("zero","initial"),("zero","selected"),("zero","final"),("memory","selected"),("memory","final"),("p","p"),("pi","pi")]
        part=[next(r for r in cross if (r["arm"],r["role"],r["family"])==(arm,role,family)) for arm,role in keys]
        labels=["父","恒零选中","恒零终点","记忆选中","记忆终点","P","PI"]
        ax.bar(range(7),[float(r["case_mean_rmse_w"])/1000 for r in part],
               yerr=[float(r["across_flow_sd_w"] or 0)/1000 for r in part],capsize=3,
               color=["#aaa","#79a9d1","#3576b5","#eab477","#db8227","#888","#444"])
        ax.scatter(range(7),[float(r["pooled_rmse_w"])/1000 for r in part],marker="D",facecolor="white",edgecolor="black",label="pooled")
        ax.set(title=family,ylabel="RMSE (kW)",xticks=range(7),xticklabels=labels)
        ax.tick_params(axis="x",labelrotation=23)
        ax.legend()
    fig.suptitle("一次独立测试。误差棒为跨父流样本 SD，压力单列")
    save(fig,"independent_test.png")

    for split,case in (("known","train_episode_8_initial_0.025"),("test","test_ramp_t2.75e+06_r0_p0.03")):
        entries=role_sources(root,split)
        fig,axes=plt.subplots(3,2,figsize=(15,10),sharex=True)
        styles=[("zero","initial","父","#999"),("zero","selected","恒零选中","#79a9d1"),("zero","final","恒零终点","#3576b5"),
                ("memory","selected","记忆选中","#eab477"),("memory","final","记忆终点","#db8227"),("pi","pi","PI","#222")]
        for run in range(3):
            for arm,role,label,color in styles:
                e=next(v for v in entries if (v["arm"],v["role"],v["run"])==(arm,role,run if arm!="pi" else -1))
                if "legacy_reference" in e:
                    ts=[r for r in gz_rows(e["legacy_reference"]["traces"]) if r["case_id"]==case]
                else:
                    ts=gz_rows(read_json(e["cases"])["traces"][case]["path"])
                t=[int(r["response_step"]) for r in ts]
                axes[run,0].plot(t,[float(r["error_w"])/1e6 for r in ts],label=label,color=color)
                axes[run,1].plot(t,[statistics.fmean(float(r[f"pitch_actual_{j}"]) for j in range(3)) for r in ts],label=label,color=color)
                if arm=="memory":
                    axes[run,1].plot(t,[statistics.fmean(float(r[f"pitch_command_{j}"]) for j in range(3)) for r in ts],
                                     color=color,ls=":",alpha=.5,label=label+"指令")
                if arm=="pi":
                    wa=axes[run,0].twinx()
                    wa.plot(t,[float(r["response_wind_m_s"]) for r in ts],color="#36a88c",alpha=.25)
                    wa.set_ylabel("风速 (m/s)")
            axes[run,0].axhline(0,color="#222",lw=.5)
            axes[run,0].set(title=f"流 {run}",ylabel="功率有符号误差 (MW)")
            axes[run,1].set(ylabel="三机平均桨距 (rad)")
            for ax in axes[run]:
                ax.legend(ncol=2,fontsize=8)
        for ax in axes[-1]:
            ax.set_xlabel("响应时刻 (s)")
        fig.suptitle(case+"，完整 128 秒")
        save(fig,f"{split}_full_timeseries.png")


def report(root):
    context(root)
    verify(read_json(root/"pretest_lock.json")["hashes"])
    store=Store(root)
    test=collect(root,"test")
    store.table("metrics.csv",test)
    summarize(store,"test",test)
    known=[dict(row,run=int(row["run"])) for row in read_csv(root/"known_metrics.csv")]
    test_gate=acceptance(test)
    selected=read_json(root/"selection.json")
    development=read_json(root/"development_acceptance.json")
    stats=[]
    pi={r["case_id"]:r for r in test if r["arm"]=="pi"}
    for role in ("selected","final"):
        for scope in (*FAMILIES,"routine","low_wind_stress","all_including_pressure"):
            rs=[r for r in test if r["arm"]=="memory" and r["role"]==role and (
                r["family"]==scope or scope=="all_including_pressure" or (scope=="routine" and r["split"]!="stress"))]
            bs=[pi[r["case_id"]] for r in rs]
            n=sum(float(r["rmse_w"])<float(b["rmse_w"]) for r,b in zip(rs,bs))
            stats.append(dict(role=role,scope=scope,case_mean_rmse_w=mean(rs,"rmse_w"),pi_mean_rmse_w=mean(bs,"rmse_w"),
                              pooled_rmse_w=math.sqrt(mean(rs,"mse_w2")),pi_pooled_rmse_w=math.sqrt(mean(bs,"mse_w2")),
                              strict_wins=n,slots=len(rs),all_slots_better=n==len(rs)))
    store.json("test_acceptance.json",dict(gates=test_gate,pi_comparisons=stats,development_unchanged=True))
    plot(root,store,test,known)
    meter=Meter(store)
    assert sum(meter.counts.values())<=342624 and sum(meter.counts.values())+297<=346720
    assert len(list(root.rglob("*.pth")))==102 and size(root)==store.used
    summary=dict(status="complete",seed=42,training_steps=98304,updates=47622,evaluation_steps=(sum(meter.counts.values())-99072)//129*128,
                 actual_model_rows=meter.counts,prior_engineering_rows=297,rows_including_engineering=sum(meter.counts.values())+297,
                 development_passed=development["passed"],memory_noninitial_selected=development["noninitial_memory_selected"],
                 primary=development["primary"],test=stats,full_states=102,light_fragments=768,replayed_steps=0,
                 selected_steps=[dict(arm=j["arm"],run=j["run"],step=j["selected_step"]) for j in selected["jobs"]],
                 formal_bytes_before_summary=store.used,engineering_bytes=store.existing_engineering,
                 figures={p.name:digest(p) for p in root.glob("*.png")},default_policy_changed=False)
    store.json("numerical_summary.json",summary)
    lines=["因果误差记忆单因素正式配对对照完成。",f"开发验收通过 = {development['passed']}",
           f"正式训练 98304 步，47622 次联合更新。模型输入 {meter.counts}。",
           "一次常规新测试和已知低风压力分列。所有场景与三流保留。",
           "检查点角色、配对差、偏差和波动分解、完整时序、跨流离散详见清单及 CSV。",
           "默认策略沿用既有配置。"]
    for x in stats:
        lines.append(f"{x['role']} {x['scope']} memory={x['case_mean_rmse_w']/1000:.2f} kW PI={x['pi_mean_rmse_w']/1000:.2f} kW wins={x['strict_wins']}/{x['slots']}")
    store.put("summary.txt",("\n".join(lines)+"\n").encode("utf8"))
    print(dict(complete=True,development_passed=development["passed"],rows=meter.counts,storage=size(root)),flush=True)
