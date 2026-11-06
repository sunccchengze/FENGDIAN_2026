"""Read-only model accounting and figures for the fixed forecast-speed experiment."""
import csv
import io
import json

from .forecast_speed_training import (
    ARMS, MIB, ORIGIN, POINTS, ROOT, RUNS, TRACE, Store, bank, context, job_cap, job_name,
    metric, read, sha, verify,
)


def csv_out(store, path, rows):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return store.write(path, buf.getvalue().encode())


def aggregate(rows):
    import numpy as np
    r = np.array([x["rmse_w"] for x in rows])
    return dict(mean_w=float(r.mean()), pooled_w=float(np.sqrt(np.mean(r*r))), worst_w=float(r.max()),
        bias_w=float(np.mean([x["bias_w"] for x in rows])),
        cases=len(rows), at400=int((r<=400000).sum()), at500=int((r<=500000).sum()),
        precision=bool(r.mean()<=400000 and r.max()<=500000),
        **{k:float(np.mean([x[k] for x in rows])) for k in (
            "heading_tv","pitch_tv","speed_tv","speed_command_tv","command_mse","saturation",
            "pitch_command_boundary","speed_command_boundary")})


def inspect_eval(entry, cases, *, macro, zero):
    import numpy as np
    saved = read(verify(entry["metrics"]))
    with np.load(verify(entry["trace"]),allow_pickle=False) as data:
        assert tuple(data["fields"].tolist())==TRACE
        traces=data["trace"]
    assert len(saved)==len(cases)==len(traces)
    max_rmse=0.
    for row,trace,(case,wind) in zip(saved,traces,cases,strict=True):
        assert np.isfinite(trace).all() and np.all(trace[:,1]==case["target_w"])
        # Reset ingests the frozen bank as float32, before exposing wind to either policy.
        np.testing.assert_array_equal(trace[:,4:7],wind.astype(np.float32))
        np.testing.assert_array_equal(trace[:,3],trace[:,2]-trace[:,1])
        expected=metric(trace,case)
        max_rmse=max(max_rmse,abs(row["rmse_w"]-expected["rmse_w"]))
        assert expected==row
        cmd=trace[:,28:37].astype(np.float32)
        np.testing.assert_array_equal(np.mean(np.square(np.diff(cmd,axis=0)),axis=1),trace[1:,8])
        if macro:
            actual=trace[1:,28:37].reshape(128,3,3)
            parent=trace[1:,37:46].reshape(128,3,3)
            z=trace[1:,46:49]
            assert np.max(np.abs(z))<=1 and (not zero or not np.any(z))
            np.testing.assert_array_equal(z,np.repeat(z[::8],8,axis=0))
            np.testing.assert_array_equal(actual[:,:,:2],parent[:,:,:2])
            expect=np.clip(parent[:,:,2]+2*(.1*z)/.667,-1,1).astype(np.float32)
            np.testing.assert_array_equal(actual[:,:,2],expect)
    return saved,traces,max_rmse


def inspect_states(lock, selection):
    import numpy as np
    import torch
    from .forecast_speed_macro import digest_array, discounted
    from .forecast_decision_contract import forecast_features
    from .history_wind_forecast import RidgeForecast
    from .forecast_speed_training import PURPOSE, expected_updates
    model=RidgeForecast.load(verify(lock["forecast"]))
    bytes_by_arm={arm:[] for arm in ARMS}
    clocks, rng, verified_macro = [],{},0
    for job in selection["jobs"]:
        arm,run=job["arm"],job["run"]
        training=bank(lock,f"train{run}")
        for point in job["points"][1:]:
            step=point["step"]
            ref=read(verify(point["checkpoint"]))
            path=verify(ref["state"])
            size=path.stat().st_size
            assert size==ref["state"]["bytes"] and size<=(28 if arm=="A" else 3)*MIB
            bytes_by_arm[arm].append(size)
            state=torch.load(path,map_location="cpu",weights_only=False)
            snap=torch.load(verify(point["snapshot"]),map_location="cpu",weights_only=True)
            assert snap["purpose"]==PURPOSE and snap["step"]==step
            updates=expected_updates(arm,step)
            if arm=="A":
                meta=state["metadata"]
                first=lock["A_initial"][run]
                assert meta["purpose"]==PURPOSE and meta["step"]==step and meta["episode"]==step//128
                assert state["updates"]==first["updates"]+updates
                assert state["replay"]["size"]==min(first["replay"]+step,32768)
                assert state["replay"]["position"]==(first["position"]+step)%32768
                weights=state["actors"]
            else:
                assert state["purpose"]==PURPOSE and state["identity"]["arm"]==arm
                assert (state["steps"],state["episodes"],state["draws"],state["updates"])==(
                    step,step//128,step//8,updates)
                replay=state["replay"]
                assert replay["insertions"]==step//8
                rng[arm,run,step]=(state["noise_rng"],replay["rng"])
                weights=state["networks"]["heads"]
                if step==8192:
                    data=replay["data"]
                    for k in range(1024):
                        e,interval=divmod(k,16)
                        t=interval*8
                        wind=training[e][1].astype(np.float32)
                        terminal=t+8==128
                        assert data["episode"][k]==e and data["t"][k]==t and data["m"][k]==8
                        assert data["terminal"][k]==terminal and data["next_forecast_valid"][k]!=terminal
                        prefix,next_prefix=wind[:t+1],wind[:t+9]
                        np.testing.assert_array_equal(data["history"][k],digest_array(prefix))
                        np.testing.assert_array_equal(data["next_history"][k],digest_array(next_prefix))
                        np.testing.assert_array_equal(data["forecast"][k],forecast_features(model,prefix,arm=="C"))
                        np.testing.assert_array_equal(data["next_forecast"][k],np.zeros(36,np.float32)
                            if terminal else forecast_features(model,next_prefix,arm=="C"))
                        r,d=discounted(data["raw_reward"][k],.99)
                        np.testing.assert_array_equal(data["return"][k],r)
                        assert data["discount"][k]==d
                        verified_macro+=1
            assert weights.keys()==snap["weights"].keys()
            assert all(torch.equal(w,snap["weights"][key]) for key,w in weights.items())
            clocks.append(dict(arm=arm,run=run,step=step,updates=updates,bytes=size))
    for run in RUNS:
        for step in POINTS[1:]:
            assert rng["B",run,step]==rng["C",run,step]
    assert len(clocks)==36 and verified_macro==6144
    return dict(states=36, verified_final_macro_rows=verified_macro, B_C_noise_and_sampling_rng_paired=True,
        snapshot_tensor_identity=True, bytes_by_arm=bytes_by_arm, clocks=clocks)


def audit():
    import numpy as np
    lock=context()
    store=Store(ROOT,68*MIB,shared=True)
    selection=read(ROOT/"selection.json")
    diagnostic=read(ROOT/"diagnostics_complete.json")
    assert diagnostic["selection_sha"]==sha(ROOT/"selection.json")
    state_checks=inspect_states(lock,selection)
    val,stress=bank(lock,"validation"),bank(lock,"stress")
    metrics,traces,training,scores,rows=[],{},{},[],0
    max_rmse=0.
    for job in selection["jobs"]:
        arm,run=job["arm"],job["run"]
        name=job_name(arm,run)
        expected=bank(lock,f"train{run}")
        seen=[]
        for point in job["points"]:
            step=point["step"]; key=f"{name}/s{step:04d}"
            assert read(verify(point["reservation"]))["rows"]==point["rows"]
            rows+=point["rows"]
            ep=read(verify(point["episodes"]));seen.extend(ep)
            case_rows, trace, diff=inspect_eval(point["eval"],val,macro=arm!="A",zero=step==0)
            max_rmse=max(max_rmse,diff)
            traces[key]=trace
            stats=aggregate(case_rows)
            assert stats["mean_w"]==point["mean_w"] and stats["worst_w"]==point["worst_w"]
            scores.append(dict(arm=arm,run=run,step=step,selected=job["selected"]["step"]==step,**stats))
            metrics.extend(dict(group=key,**r) for r in case_rows)
        assert len(seen)==64 and all(
            x["ordinal"]==i and x["step"]==128*(i+1) and all(x[k]==v for k,v in expected[i][0].items())
            for i,x in enumerate(seen))
        assert sum(x["updates"] for x in seen)==(3841 if arm=="A" else 481)
        assert min(job["points"],key=lambda x:(x["mean_w"],x["step"]))==job["selected"]
        training[name]=seen
        assert Store(ROOT/"jobs"/name,job_cap(arm)).used()<=job_cap(arm)
    assert rows==109134
    for group in diagnostic["groups"]:
        key=group["group"]
        receipt=read(verify(group["receipt"]))
        assert read(verify(receipt["reservation"]))["rows"]==receipt["rows"]
        data=stress if key.endswith("/stress") else val
        assert receipt["rows"]==129*len(data)
        rows+=receipt["rows"]
        macro=key.split("/")[1][0] in ("B","C")
        part,trace,diff=inspect_eval(receipt["eval"],data,macro=macro,zero=key.endswith("/zero"))
        traces[key]=trace
        max_rmse=max(max_rmse,diff)
        metrics.extend(dict(group=key,**r) for r in part)
    assert rows==125259 and len(traces)==85 and len(metrics)==395
    assert len(list(ROOT.rglob("reserved.json")))==85
    assert sum(x.shape[0]*x.shape[1] for x in traces.values())==50955
    by_group={name:[x for x in metrics if x["group"]==name] for name in traces}
    parent_check=[]
    for run in RUNS:
        ref=traces[f"diagnostics/parent{run}/validation"]
        checks=[f"{arm}{run}/s0000" for arm in ARMS]+[
            f"diagnostics/{arm}{run}/{role}/zero" for arm in ("B","C") for role in ("selected","final")]
        for key in checks:
            other=traces[key]
            d=dict(group=key,run=run,max_action=float(np.max(np.abs(ref[:,:,28:37]-other[:,:,28:37]))),
                max_applied=float(np.max(np.abs(ref[:,:,19:28]-other[:,:,19:28]))),
                max_power_w=float(np.max(np.abs(ref[:,:,2]-other[:,:,2]))),
                max_rmse_w=max(abs(x["rmse_w"]-y["rmse_w"]) for x,y in zip(
                    by_group[f"diagnostics/parent{run}/validation"],by_group[key],strict=True)))
            d["passed"]=d["max_action"]<=2e-6 and d["max_applied"]<=1e-6 and max(d["max_power_w"],d["max_rmse_w"])<=1
            parent_check.append(d)
    jobs={(j["arm"],j["run"]):j for j in selection["jobs"]}
    roles,pairs,stable,control=[],[],[],[]
    for (arm,run),job in jobs.items():
        role_rows={}
        for role in ("initial","selected","final"):
            step=job[role]["step"]
            part=by_group[f"{arm}{run}/s{step:04d}"]
            role_rows[role]=part
            roles.append(dict(arm=arm,run=run,role=role,step=step,**aggregate(part)))
            if arm!="A":
                sample=traces[f"{arm}{run}/s{step:04d}"][:,1:]
                z=sample[:,:,46:49]
                parent=sample[:,:,37:46].reshape(6,128,3,3)[:,:,:,2]
                command=sample[:,:,28:37].reshape(6,128,3,3)[:,:,:,2]
                control.append(dict(arm=arm,run=run,role=role,step=step,
                    mean_abs_requested_offset_rad_s=float(.1*np.mean(np.abs(z))),
                    max_abs_requested_offset_rad_s=float(.1*np.max(np.abs(z))),
                    mean_abs_executed_offset_rad_s=float(.667/2*np.mean(np.abs(command-parent))),
                    hold_z_near_boundary=float(np.mean(np.abs(z)>.98)),
                    requested_speed_clip=float(np.mean(np.abs(parent+2*.1*z/.667)>1))))
        father=by_group[f"diagnostics/parent{run}/validation"]
        for role in ("selected","final"):
            part=role_rows[role]
            opponents={"initial":role_rows["initial"],"parent":father,
                       "A":by_group[f"A{run}/s{jobs['A',run][role]['step']:04d}"]}
            if arm!="A":
                opponents["zero"]=by_group[f"diagnostics/{arm}{run}/{role}/zero"]
            if arm=="C":
                opponents["B"]=by_group[f"B{run}/s{jobs['B',run][role]['step']:04d}"]
            for comparator,baseline in opponents.items():
                for actual,ref in zip(part,baseline,strict=True):
                    assert actual["case_id"]==ref["case_id"]
                    a,b=actual["rmse_w"],ref["rmse_w"]
                    pairs.append(dict(arm=arm,run=run,role=role,comparator=comparator,case_id=actual["case_id"],
                        score_w=a,ref_w=b,ratio=a/b,improved=a<b,noninferior=a<=1.05*b))
        s,f,p=map(aggregate,(role_rows["selected"],role_rows["final"],father))
        a=aggregate(by_group[f"A{run}/s{jobs['A',run]['final']['step']:04d}"])
        stable.append(dict(arm=arm,run=run,selected_step=job["selected"]["step"],
            final_over_selected=f["mean_w"]/s["mean_w"], selected_over_parent=s["mean_w"]/p["mean_w"],
            final_over_parent=f["mean_w"]/p["mean_w"], selected_worst_over_parent=s["worst_w"]/p["worst_w"],
            final_worst_over_parent=f["worst_w"]/p["worst_w"], final_over_A=f["mean_w"]/a["mean_w"],
            stable=f["mean_w"]<=1.25*s["mean_w"] and max(s["mean_w"],f["mean_w"])<=1.05*p["mean_w"]
                and max(s["worst_w"],f["worst_w"])<=1.05*p["worst_w"],
            final_A_noninferior=f["mean_w"]<=1.05*a["mean_w"]))
    gates=[]
    for arm in ARMS:
        for role in ("selected","final"):
            for comparator in ("initial","parent","zero","B","A"):
                part=[x for x in pairs if (x["arm"],x["role"],x["comparator"])==(arm,role,comparator)]
                if not part:
                    continue
                stream_ratios=[]
                for run in RUNS:
                    r=[x for x in part if x["run"]==run]
                    stream_ratios.append(sum(x["score_w"] for x in r)/sum(x["ref_w"] for x in r))
                ratio=sum(x["score_w"] for x in part)/sum(x["ref_w"] for x in part)
                noninitial=all(jobs[arm,r]["selected"]["step"]>0 for r in RUNS)
                gates.append(dict(arm=arm,role=role,comparator=comparator,ratio=ratio,
                    run0_ratio=stream_ratios[0],run1_ratio=stream_ratios[1],run2_ratio=stream_ratios[2],
                    improved_cases=sum(x["improved"] for x in part),noninferior_cases=sum(x["noninferior"] for x in part),
                    all_streams_improve=max(stream_ratios)<1,all_selected_noninitial=noninitial,
                    mean_gate=max(stream_ratios)<1 and ratio<=.99 and (role!="selected" or noninitial)))
    baseline=[dict(controller=key,**aggregate(value)) for key,value in by_group.items()
              if key.startswith("diagnostics/") and key.endswith("/validation")]
    pressure=[dict(controller=key,**group[0]) for key,group in by_group.items() if key.endswith("/stress")]
    train_rows=[dict(arm=name[0],run=int(name[1]),ordinal=x["ordinal"],episode=x["episode"],step=x["step"],
        family=x["family"],target_w=x["target_w"],pitch_rad=x["pitch_rad"],wind_sha=x["wind_sha"],rmse_w=x["rmse_w"],
        bias_w=x["bias_w"],reward_mean=x["reward_mean"],command_mse=x["command_mse"],updates=x["updates"],
        **{k:x["loss_summary"].get(k,"") for k in ("actor_loss","critic_loss","actor_grad_norm","critic_grad_norm")})
        for name,value in training.items() for x in value]
    for path,values in (
        ("metrics.csv",metrics),("training_episodes.csv",train_rows),("curves.csv",scores),("roles.csv",roles),
        ("paired.csv",pairs),("gates.csv",gates),("stability.csv",stable),("pressure.csv",pressure),
        ("baselines.csv",baseline),("takeover.csv",parent_check),("speed_controls.csv",control),
    ):
        csv_out(store,path,values)
    store.json("verification.json",dict(formal_rows=rows,engineering_rows=1728,entry_rows=0,cumulative_rows=126987,
        formal_steps=73728,training_resets=576,validation_diagnostic_rollouts=395,eval_trace_rows=50955,
        max_rmse_recompute_diff_w=max_rmse,passed_takeover=sum(x["passed"] for x in parent_check),
        takeover_checks=len(parent_check),whole_macro_hold_verified=True,all_motion_rates_valid=True,
        no_new_independent_test=True,selection_sha=sha(ROOT/"selection.json"),checkpoint_checks=state_checks,
        report_source_sha=sha(__file__)))
    store.json("future_test_proposal.json",dict(released=False,namespace=list(range(69000000,69000018)),seed=42,
        wind_families=["stationary","ramp","gust"],targets_w=[2.75e6,3.35e6,3.85e6],
        initial_pitch_rad=[.025,.055],independent_waveforms=18,nominal_horizon=128,
        statistical_unit="whole_waveform_cluster_paired_over_three_parent_streams",
        roles=[dict(arm=a,run=r,role=role,step=j[role]["step"],snapshot=j[role]["snapshot"])
               for (a,r),j in jobs.items() for role in ("selected","final")],
        controllers=dict(learned_roles=18,frozen_parent=3,zero_speed_roles=12,common_P_PI=2),
        physical_rollouts_upper=630,query_rows_upper=81270,stress_separate=True,
        requires_review_and_release=True,selection_sha=sha(ROOT/"selection.json")))
    store.write("summary.txt",("Formal A/B/C experiment completed. seed=42. 73728 physical training steps.\n"
        "125259 formal query rows, 1728 prior engineering rows, 0 entry model queries, total 126987.\n"
        "All checkpoints, validation selection and post-selection diagnostics preserved.\n"
        "No independent test released. See roles.csv, gates.csv, stability.csv and pressure.csv.\n").encode())
    figures(store,scores,pairs,traces,jobs)
    print("Recomputed 395 rollout metrics from 50955 saved rows.",flush=True)


def figures(store,scores,pairs,traces,jobs):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors=dict(A="#ab502a",B="#36739b",C="#218666")
    def save(fig,name):
        for ext in ("png","pdf"):
            with io.BytesIO() as buf:
                fig.savefig(buf,format=ext,dpi=180)
                store.write(f"figures/{name}.{ext}",buf.getbuffer())
        plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(12,6.6),layout="constrained",sharex=True,sharey="row")
    for run in RUNS:
        for arm in ARMS:
            part=[x for x in scores if (x["arm"],x["run"])==(arm,run)]
            for row,(field,threshold) in enumerate((("mean_w",400),("worst_w",500))):
                ax=axes[row,run]
                y=np.array([x[field] for x in part])/1000
                ax.plot(POINTS,y,color=colors[arm],marker="o",label=arm)
                k=next(i for i,x in enumerate(part) if x["selected"])
                ax.scatter(POINTS[k],y[k],marker="*",s=100,color=colors[arm],zorder=5)
                ax.axhline(threshold,color=".65",lw=.7)
                ax.grid(alpha=.18)
        axes[0,run].set_title(f"Parent stream {run}")
        axes[1,run].set_xlabel("Physical training steps")
    axes[0,0].set_ylabel("Validation mean RMSE (kW)")
    axes[1,0].set_ylabel("Validation worst RMSE (kW)")
    axes[0,2].legend(title="Arm",frameon=False)
    fig.suptitle("A/B/C validation over training. Stars mark the selected step")
    save(fig,"validation_curves")
    fig,axes=plt.subplots(2,3,figsize=(13,6.8),layout="constrained",sharex=True,sharey=True)
    choices=[("parent","Frozen parent","#333333"),("zero","Speed off","#9c7e33"),("B","B","#36739b"),("A","A","#ab502a")]
    for row,role in enumerate(("selected","final")):
        for run in RUNS:
            ax=axes[row,run]
            for i,(comp,label,color) in enumerate(choices):
                part=[x for x in pairs if (x["arm"],x["run"],x["role"],x["comparator"])==("C",run,role,comp)]
                ax.scatter(np.arange(6)+(i-1.5)*.12,[x["ratio"] for x in part],label=label,color=color,s=18)
            ax.axhline(1,color=".2",lw=.8)
            ax.axhline(1.05,color=".65",lw=.8,ls="--")
            ax.set_title(f"Stream {run}, {role}")
            ax.grid(alpha=.18)
            ax.set_xticks(range(6),["S 2.85","S 3.45","R 2.85","R 3.45","G 2.85","G 3.45"],rotation=30)
        axes[row,0].set_ylabel("C RMSE / comparator")
    axes[0,2].legend(frameon=False,ncol=2,fontsize=8)
    fig.suptitle("Six paired validation winds per stream. Dashed line marks +5%")
    save(fig,"paired_validation")
    fig,axes=plt.subplots(4,3,figsize=(13,9.4),layout="constrained",sharex=True,sharey="row")
    for run in RUNS:
        # Fixed figure case, sixth validation entry, gust at 3.45 MW.
        series=[("Parent",traces[f"diagnostics/parent{run}/validation"][5],"#333333","--"),
                ("B final",traces[f"B{run}/s8192"][5],colors["B"],"-"),
                ("C final",traces[f"C{run}/s8192"][5],colors["C"],"-")]
        for label,trace,color,ls in series:
            actual=trace[:,19:28].reshape(129,3,3)
            axes[0,run].plot(trace[:,0],trace[:,2]/1e6,label=label,color=color,ls=ls)
            for row,(column,scale) in enumerate(((1,180/np.pi),(2,1),(0,180/np.pi)),1):
                axes[row,run].plot(trace[:,0],actual[:,:,column].mean(axis=1)*scale,label=label,color=color,ls=ls)
        axes[0,run].axhline(3.45,color=".65",lw=.9,ls=":")
        axes[0,run].set_title(f"Stream {run}")
        axes[3,run].set_xlabel("Physical time (s)")
        for ax in axes[:,run]:
            ax.grid(alpha=.18)
    for i,label in enumerate(("Farm power (MW)","Mean pitch (deg)","Mean speed (rad/s)","Mean yaw error (deg)")):
        axes[i,0].set_ylabel(label)
    axes[0,2].legend(frameon=False,fontsize=8)
    fig.suptitle("Gust validation at 3.45 MW. Applied actuator states")
    save(fig,"actual_controls")


if __name__=="__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(ORIGIN/".venv/pinn_tf216")
    audit()
