"""Independent-waveform paired statistics and figures for the frozen comparison."""
import io

from . import forecast_speed_training as formal
from .forecast_speed_report import aggregate, csv_out, inspect_eval
from .forecast_speed_user_test import FAMILIES, ROOT, evaluation_context, shared_store


def group_names(name):
    if name in ("p","pi"):
        return [name]
    if name=="parent":
        return [f"parent{run}" for run in range(3)]
    arm,role=name.split("_")
    return [f"{arm}{run}_{role}" for run in range(3)]


def bootstrap(actual, reference, groups, samples):
    """Each row is one waveform, already paired/averaged across relevant parents."""
    import numpy as np
    rng=np.random.default_rng(42)
    index=np.concatenate([rng.choice(g,size=(samples,len(g)),replace=True) for g in groups],axis=1)
    a=actual[index].mean(axis=1)
    b=reference[index].mean(axis=1)
    delta=np.quantile(a-b,[.025,.975])
    ratio=np.quantile(a/b,[.025,.975])
    return dict(delta_CI95_lo_w=float(delta[0]),delta_CI95_hi_w=float(delta[1]),
        ratio_CI95_lo=float(ratio[0]),ratio_CI95_hi=float(ratio[1]))


def audit():
    import numpy as np
    lock,cases=evaluation_context()
    s=shared_store()
    complete=formal.read(ROOT/"complete.json")
    assert complete["rows"]==53406 and complete["rollouts"]==414
    assert complete["selection_sha"]==lock["selection_sha"]
    rows,metrics,traces,counts=0,{}, {},[]
    for ref,role in zip(complete["results"],lock["roles"],strict=True):
        entry=formal.read(formal.verify(ref))
        reserved=formal.read(formal.verify(entry["reservation"]))
        assert entry["rows"]==reserved["rows"]==2322 and entry["role"]==reserved["role"]==role
        assert reserved["release_sha"]==formal.sha(ROOT/"release.json")
        rows+=entry["rows"]
        macro=role.get("arm") in ("B","C")
        part,trace,diff=inspect_eval(entry["eval"],cases,macro=macro,zero=macro and role["step"]==0)
        assert diff==0
        metrics[role["id"]]=part
        traces[role["id"]]=trace
        used=formal.Store(ROOT/"jobs"/role["id"],4*formal.MIB).used()
        assert used<=4*formal.MIB
        counts.append(dict(role=role["id"],physical_rollouts=len(part),rows=entry["rows"],artifact_bytes=used))
    assert rows==53406 and len(traces)==23 and len(list(ROOT.rglob("reserved.json")))==23
    baseline_checks=[]
    for role in lock["roles"]:
        if role.get("step")==0:
            a=traces[role["id"]]
            b=traces[f"parent{role['run']}"]
            np.testing.assert_array_equal(a,b)
            baseline_checks.append(role["id"])
    assert len(baseline_checks)==6
    all_rows=[dict(controller=key,**row) for key,part in metrics.items() for row in part]
    family_ids={name:np.asarray([i for i,(c,_) in enumerate(cases) if c["family"]==name])
                for name in FAMILIES}
    family_ids["all"]=np.arange(len(cases))
    names=[f"{a}_{r}" for a in "ABC" for r in ("selected","final")]+["parent","p","pi"]
    summaries,flow=[],[]
    for key in names:
        group=group_names(key)
        for fam,index in family_ids.items():
            part=[metrics[g][i] for g in group for i in index]
            summaries.append(dict(controller=key,family=fam,unique_winds=len(index),**aggregate(part)))
    for role in lock["roles"]:
        key=role["id"]
        for fam,index in family_ids.items():
            part=[metrics[key][i] for i in index]
            flow.append(dict(controller=key,family=fam,role=role.get("role",role["kind"]),
                stream=role.get("run",""),step=role.get("step",""),**aggregate(part)))
    paired,comparisons=[],[]
    specs=[]
    for name in names[:-3]:
        arm,role=name.split("_")
        specs.extend([(name,"pi"),(name,"parent")])
        if arm=="C":
            specs.extend([(name,f"B_{role}"),(name,f"A_{role}")])
        if role=="final":
            specs.append((name,f"{arm}_selected"))
    specs.extend([("parent","pi"),("p","pi")])
    def arr(name):
        return np.asarray([[x["rmse_w"] for x in metrics[g]] for g in group_names(name)])
    for name,against in specs:
        actual,ref=np.broadcast_arrays(arr(name),arr(against))
        for run in range(len(actual)):
            for i,(case,_) in enumerate(cases):
                a,b=float(actual[run,i]),float(ref[run,i])
                paired.append(dict(controller=name,comparator=against,run=run if len(actual)>1 else "",
                    family=case["family"],case_id=case["id"],episode=case["episode"],
                    rmse_w=a,ref_w=b,delta_w=a-b,ratio=a/b,win=a<b))
        for family,index in family_ids.items():
            a,b=actual[:,index],ref[:,index]
            blocks=list(family_ids[f] for f in FAMILIES) if family=="all" else [np.arange(len(index))]
            ci=bootstrap(a.mean(axis=0),b.mean(axis=0),blocks,lock["config"]["bootstrap_samples"])
            comparisons.append(dict(controller=name,comparator=against,family=family,unique_winds=len(index),
                paired_rows=a.size,mean_w=float(a.mean()),ref_mean_w=float(b.mean()),
                delta_w=float(a.mean()-b.mean()),ratio=float(a.mean()/b.mean()),wins=int((a<b).sum()),
                losses=int((a>b).sum()),ties=int((a==b).sum()),**ci))
    verdict=[x for x in comparisons if x["controller"]=="C_selected" and x["comparator"]=="pi" and x["family"]!="all"]
    assert len(verdict)==3
    for row in verdict:
        assert row["unique_winds"]==6 and row["paired_rows"]==18
    gate=dict(passed=all(row["mean_w"]<row["ref_mean_w"] for row in verdict),
        primary="C_selected",criterion="all_three_family_case_and_parent_equal_means_strictly_below_PI",
        families=[dict(**x,passed=x["mean_w"]<x["ref_mean_w"]) for x in verdict],
        no_additional_gate_on_case_or_stream_or_CI=True,prior_learning_failure_retained=True)
    for path,data in (("metrics.csv",all_rows),("family_summary.csv",summaries),("stream_summary.csv",flow),
                      ("paired_cases.csv",paired),("comparisons.csv",comparisons),("query_receipts.csv",counts)):
        csv_out(s,path,data)
    s.json("primary_acceptance.json",gate)
    s.json("pressure_reference.json",dict(reused=True,additional_PINN_rows=0,
        source=str(formal.ROOT/"pressure.csv"),sha256=formal.sha(formal.ROOT/"pressure.csv"),
        wind_m_s=7.6,target_w=4.4e6,initial_pitch_rad=.04))
    s.json("verification.json",dict(passed=True,rows=53406,rollouts=414,trace_rows=53406,unique_winds=18,
        recompute_rmse_max_diff_w=0,closed_loop_initial_matches_parent=baseline_checks,
        verified_actuator_rates=True,whole_macro_hold_verified=True,
        max_heading_rate=max(x["max_heading_rate"] for x in all_rows),
        max_pitch_rate=max(x["max_pitch_rate"] for x in all_rows),
        max_speed_rate=max(x["max_speed_rate"] for x in all_rows),
        prior_close_speed_groups_reused=21,new_close_speed_queries=0,optimizer_updates=0,
        released_wind_manifest_sha=formal.sha(ROOT/"bank/manifest.json"),primary_gate=gate["passed"]))
    figures(s,summaries,traces,paired,lock["config"])
    s.write("summary.txt",(f"Frozen A/B/C independent comparison, seed=42. User family-average PI criterion: {gate['passed']}.\n"
        "18 independent winds, 414 physical rollouts and 53406 PINN input rows including resets.\n"
        "Formal RL, optimizer updates and new weights=0. Prior formal learning failure remains part of the record.\n"
        "See primary_acceptance.json, comparisons.csv, stream_summary.csv and metrics.csv.\n").encode())
    print("C selected family-average criterion:",gate["passed"],flush=True)


def figures(store,summaries,traces,paired,config):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    def save(fig,name):
        for ext in ("png","pdf"):
            with io.BytesIO() as buf:
                fig.savefig(buf,format=ext,dpi=170)
                store.write(f"figures/{name}.{ext}",buf.getbuffer())
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,5.7),layout="constrained")
    names=("A_selected","A_final","B_selected","B_final","C_selected","C_final","parent","pi")
    colors=("#b36a45","#87432a","#648cae","#376999","#2b936e","#19684f","#555555","#c99532")
    for j,(name,color) in enumerate(zip(names,colors,strict=True)):
        means=[next(x["mean_w"] for x in summaries if x["controller"]==name and x["family"]==f)/1000 for f in FAMILIES]
        ax.bar(np.arange(3)+(j-3.5)*.105,means,width=.098,color=color,label=name.replace("_"," "))
    ax.set_xticks(range(3),["Stationary","Ramp","Gust"]);ax.set_ylabel("Mean case RMSE (kW)")
    ax.legend(frameon=False,ncol=4,loc="upper center")
    ax.set_ylim(0,max(x["mean_w"] for x in summaries if x["controller"] in names)/1000*1.24)
    ax.grid(axis="y",alpha=.18)
    ax.set_title("Frozen independent comparison. Six distinct winds per family")
    save(fig,"family_mean")
    fig,axs=plt.subplots(3,1,figsize=(12,8),sharex=True,layout="constrained")
    for run,ax in enumerate(axs):
        for role,color in (("selected","#238368"),("final","#376999")):
            data=[r for r in paired if r["controller"]==f"C_{role}" and r["comparator"]=="pi" and r["run"]==run]
            ax.plot(np.arange(18),[x["delta_w"]/1000 for x in data],color=color,marker="o",label=role)
        ax.axhline(0,color=".25",lw=.8)
        ax.axvline(5.5,color=".65",lw=.7,ls=":");ax.axvline(11.5,color=".65",lw=.7,ls=":")
        ax.set_ylabel("C − PI RMSE (kW)");ax.set_title(f"Parent stream {run}")
        ax.grid(alpha=.18)
    axs[0].legend(frameon=False)
    axs[-1].set_xticks(range(18));axs[-1].set_xlabel("Waveform index. 0–5 stationary, 6–11 ramp, 12–17 gust")
    save(fig,"C_paired_against_PI")
    case,run=config["plot_case"],config["plot_parent_stream"]
    fig,axs=plt.subplots(4,1,figsize=(11,9),sharex=True,layout="constrained")
    for key,label,color in ((f"C{run}_selected","C selected","#238368"),(f"C{run}_final","C final","#376999"),
                            (f"parent{run}","Parent","#555555"),("pi","PI","#b37b25")):
        d=traces[key][case]
        actual=d[:,19:28].reshape(129,3,3)
        values=(d[:,2]/1e6,actual[:,:,1].mean(axis=1)*180/np.pi,actual[:,:,2].mean(axis=1),
                actual[:,:,0].mean(axis=1)*180/np.pi)
        for ax,y in zip(axs,values,strict=True):
            ax.plot(d[:,0],y,label=label,color=color)
    axs[0].axhline(3.85,color=".55",lw=.8,ls=":")
    axs[0].legend(frameon=False,ncol=4)
    for ax,label in zip(axs,("Farm power (MW)","Mean pitch (deg)","Mean speed (rad/s)","Mean yaw error (deg)"),strict=True):
        ax.set_ylabel(label);ax.grid(alpha=.18)
    axs[-1].set_xlabel("Physical time (s)")
    fig.suptitle("Predeclared gust waveform 17. Target 3.85 MW, initial pitch .055 rad")
    save(fig,"actual_controls_gust17")


if __name__=="__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(formal.ORIGIN/".venv/pinn_tf216")
    audit()
