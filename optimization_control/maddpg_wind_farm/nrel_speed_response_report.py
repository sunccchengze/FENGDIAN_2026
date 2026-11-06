"""Saved-only decomposition and static response summaries for the bounded audit."""
import io
import math

from . import nrel_speed_response_audit as run
from .forecast_speed_report import csv_out


def mean(rows,key):
    return sum(float(x[key]) for x in rows)/len(rows)


def plain(value):
    import numpy as np
    if isinstance(value,np.generic): return value.item()
    if isinstance(value,dict): return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [plain(v) for v in value]
    return value


def decomposition(lock,s):
    import numpy as np
    records=[]
    cases=run.transfer.cases(lock["source"])
    for item in lock["evaluations"]:
        traces=run.load_traces(item["ref"])
        stored=run.old.read(run.old.verify(item["ref"]["metrics"]))
        for trace,saved,(case,wind) in zip(traces,stored,cases,strict=True):
            np.testing.assert_array_equal(trace[:,4:7],wind)
            e=trace[1:,3]/1000
            bias=float(e.mean()); bs=bias*bias; var=float(np.mean((e-bias)**2)); mse=float(np.mean(e**2))
            assert abs(mse-bs-var)<1e-7
            assert abs(math.sqrt(mse)-saved["rmse_w"]/1000)<1e-9
            assert abs(bias-saved["bias_w"]/1000)<1e-9
            over=e>0;under=e<0
            row=dict(rule=item["rule"],controller=item["controller"],case_id=case["id"],family=case["family"],
                target_kW=case["target_w"]/1000,steps=128,mean_rmse_kW=math.sqrt(mse),bias_kW=bias,
                bias_sq_kW2=bs,variance_kW2=var,mse_kW2=mse,
                over_fraction=float(over.mean()),under_fraction=float(under.mean()),equal_fraction=float(np.mean(e==0)),
                over_mse_kW2=float(np.mean(np.where(over,e*e,0))),under_mse_kW2=float(np.mean(np.where(under,e*e,0))))
            assert abs(row["over_mse_kW2"]+row["under_mse_kW2"]-mse)<1e-7
            records.append(row)
    assert len(records)==60
    csv_out(s,"closed_loop_decomposition.csv",records)
    aggregates=[]
    keys=("mean_rmse_kW","bias_kW","bias_sq_kW2","variance_kW2","mse_kW2","over_fraction","under_fraction","equal_fraction","over_mse_kW2","under_mse_kW2")
    for rule in ("legacy","nrel"):
        for controller in ("Y0_selected","Y1_selected","Y2_selected","Y","p","pi"):
            for family in ("stationary","ramp","gust","overall"):
                rows=[r for r in records if r["rule"]==rule and
                      (r["controller"].startswith("Y") if controller=="Y" else r["controller"]==controller) and
                      (family=="overall" or r["family"]==family)]
                entry=dict(rule=rule,controller=controller,family=family,cases=len(rows),**{key:mean(rows,key) for key in keys})
                entry["pooled_rmse_kW"]=math.sqrt(entry["mse_kW2"])
                assert abs(entry["mse_kW2"]-entry["bias_sq_kW2"]-entry["variance_kW2"])<1e-7
                aggregates.append(entry)
    csv_out(s,"decomposition_groups.csv",aggregates)
    paired=[]
    for before in records:
        if before["rule"]!="legacy":continue
        after=next(r for r in records if r["rule"]=="nrel" and r["controller"]==before["controller"] and r["case_id"]==before["case_id"])
        paired.append(dict(controller=before["controller"],case_id=before["case_id"],family=before["family"],
            **{"delta_"+key:after[key]-before[key] for key in keys}))
    csv_out(s,"decomposition_paired_cases.csv",paired)
    changes=[]
    for before in aggregates:
        if before["rule"]!="legacy":continue
        after=next(r for r in aggregates if r["rule"]=="nrel" and r["controller"]==before["controller"] and r["family"]==before["family"])
        delta={"delta_"+key:after[key]-before[key] for key in keys}
        dm=delta["delta_mse_kW2"]
        changes.append(dict(controller=before["controller"],family=before["family"],**delta,
            bias_sq_share_of_mse_increase=delta["delta_bias_sq_kW2"]/dm if dm else 0.,
            variance_share_of_mse_increase=delta["delta_variance_kW2"]/dm if dm else 0.))
    csv_out(s,"decomposition_changes.csv",changes)
    return records,aggregates,changes


def direction(delta):
    return 0 if abs(float(delta))<=2 else (1 if delta>0 else -1)


def response(lock,s):
    import numpy as np
    meta=run.old.read(run.old.verify(lock["anchors"]));semantic=run.old.read(run.old.verify(lock["semantic"]))
    complete=run.old.read(run.ROOT/"complete.json")
    assert complete["replay_passed"]==48
    raw_rows=[]; references=[];local=[];grid=[];replays=[]
    for outcome,anchor in zip(complete["outcomes"],meta,strict=True):
        assert outcome["anchor"]==anchor["id"]
        with np.load(run.old.verify(outcome["artifact"]),allow_pickle=False) as data:
            x,y,label,index=[data[k] for k in ("inputs","outputs","labels","mapping")]
        f=y[:,:3].astype(float).sum(axis=1);tf=label[:,:3].astype(float).sum(axis=1)
        common={k:anchor[k] for k in ("id","rule","controller","case_id","family","t")}
        replays.append(dict(**common,**outcome["replay"],unique_rows=len(x)))
        for request,i in zip(semantic,index,strict=True):
            raw_rows.append(dict(**common,**request,query_row=int(i),
                **{f"omega_{j+1}":float(x[i,9+j]) for j in range(3)},
                **{f"P_{j+1}_w":float(y[i,j]) for j in range(3)},
                **{f"Ueff_{j+1}_m_s":float(y[i,3+j]) for j in range(3)},
                farm_w=float(f[i]),delta_farm_vs_actual_w=float(f[i]-f[0]),
                **{f"label_P_{j+1}_w":float(label[i,j]) for j in range(3)},
                **{f"label_Ueff_{j+1}_m_s":float(label[i,3+j]) for j in range(3)},
                label_farm_w=float(tf[i]),label_delta_farm_vs_actual_w=float(tf[i]-tf[0])))
        il,ir=int(index[1]),int(index[2])
        delta=float(f[ir]-f[il]);td=float(tf[ir]-tf[il])
        references.append(dict(**common,actual_farm_kW=float(f[0]/1000),legacy_reference_farm_kW=float(f[il]/1000),
            nrel_reference_farm_kW=float(f[ir]/1000),new_minus_old_reference_kW=delta/1000,
            label_new_minus_old_reference_kW=td/1000,model_direction=direction(delta),label_direction=direction(td),
            directions_equal=direction(delta)==direction(td),
            **{f"model_delta_P_{j+1}_kW":(float(y[ir,j])-float(y[il,j]))/1000 for j in range(3)},
            **{f"label_delta_P_{j+1}_kW":(float(label[ir,j])-float(label[il,j]))/1000 for j in range(3)},
            **{f"model_delta_Ueff_{j+1}":float(y[ir,3+j])-float(y[il,3+j]) for j in range(3)},
            legacy_reference_below_new_min=int(np.sum(x[il,9:12]<lock["config"]["speed_low"]))))
        for turbine in range(3):
            im,ip=[int(index[next(k for k,r in enumerate(semantic) if r["kind"]=="local" and r["turbine"]==turbine and r["level"]==sign)]) for sign in (-1,1)]
            width=float(x[ip,9+turbine])-float(x[im,9+turbine]);assert width>0
            own=float(y[ip,turbine])-float(y[im,turbine]);t_own=float(label[ip,turbine])-float(label[im,turbine])
            farm=float(f[ip]-f[im]);t_farm=float(tf[ip]-tf[im])
            local.append(dict(**common,turbine=turbine+1,omega_actual=float(x[0,9+turbine]),actual_width_rad_s=width,
                own_delta_w=own,label_own_delta_w=t_own,farm_delta_w=farm,label_farm_delta_w=t_farm,
                own_slope_w_per_rad_s=own/width,label_own_slope_w_per_rad_s=t_own/width,
                farm_slope_w_per_rad_s=farm/width,label_farm_slope_w_per_rad_s=t_farm/width,
                own_direction=direction(own),label_own_direction=direction(t_own),
                farm_direction=direction(farm),label_farm_direction=direction(t_farm),
                own_directions_equal=direction(own)==direction(t_own),farm_directions_equal=direction(farm)==direction(t_farm)))
            ig=[int(index[k]) for k,r in enumerate(semantic) if r["kind"]=="grid" and r["turbine"]==turbine]
            own_i=ig[int(np.argmax(y[ig,turbine]))];farm_i=ig[int(np.argmax(f[ig]))]
            teacher_own=ig[int(np.argmax(label[ig,turbine]))];teacher_farm=ig[int(np.argmax(tf[ig]))]
            grid.append(dict(**common,turbine=turbine+1,grid_points=7,
                sampled_max_own_omega=float(x[own_i,9+turbine]),sampled_max_farm_omega=float(x[farm_i,9+turbine]),
                label_sampled_max_own_omega=float(x[teacher_own,9+turbine]),label_sampled_max_farm_omega=float(x[teacher_farm,9+turbine]),
                own_power_span_w=float(np.ptp(y[ig,turbine])),farm_power_span_w=float(np.ptp(f[ig])),
                label_own_power_span_w=float(np.ptp(label[ig,turbine])),label_farm_power_span_w=float(np.ptp(tf[ig])),
                sampled_max_own_TSR=float(63*x[own_i,9+turbine]/y[own_i,3+turbine])))
    csv_out(s,"replay.csv",replays);csv_out(s,"queries.csv",raw_rows);csv_out(s,"metrics.csv",references)
    csv_out(s,"local_response.csv",local);csv_out(s,"sampled_grid.csv",grid)
    groups=[]
    for rule in ("legacy","nrel","all"):
        for controller in ("Y2_selected","pi","all"):
            for family in ("stationary","ramp","gust","overall"):
                rows=[r for r in references if (rule=="all" or r["rule"]==rule) and
                    (controller=="all" or r["controller"]==controller) and (family=="overall" or r["family"]==family)]
                groups.append(dict(rule=rule,controller=controller,family=family,anchors=len(rows),
                    model_reference_change_kW=mean(rows,"new_minus_old_reference_kW"),
                    label_reference_change_kW=mean(rows,"label_new_minus_old_reference_kW"),
                    model_increase=int(sum(r["model_direction"]==1 for r in rows)),
                    model_decrease=int(sum(r["model_direction"]==-1 for r in rows)),
                    same_direction=int(sum(r["directions_equal"] for r in rows))))
    csv_out(s,"reference_groups.csv",groups)
    return references,local,grid,replays,groups


def figures(s,groups):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    def save(fig,name):
        fig.tight_layout()
        with io.BytesIO() as out:
            fig.savefig(out,format="png",dpi=140,bbox_inches="tight");s.write(name,out.getbuffer())
        plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(14,4.4),sharey=True)
    for ax,controller in zip(axes,("Y","p","pi"),strict=True):
        for rule,offset in (("legacy",-.18),("nrel",.18)):
            rows=[next(r for r in groups if r["rule"]==rule and r["controller"]==controller and r["family"]==fam) for fam in ("stationary","ramp","gust","overall")]
            x=np.arange(4)+offset;b=np.array([r["bias_sq_kW2"] for r in rows])/1e6;v=np.array([r["variance_kW2"] for r in rows])/1e6
            ax.bar(x,b,.32,color="C1",label="Bias squared" if rule=="legacy" else None)
            ax.bar(x,v,.32,bottom=b,color="C0",label="Error variance" if rule=="legacy" else None)
            for xx,bb,vv in zip(x,b,v,strict=True):ax.text(xx,bb+vv, "old" if rule=="legacy" else "new",rotation=90,ha="center",va="bottom",fontsize=8)
        ax.set_xticks(range(4),["steady","ramp","gust","all"]);ax.set_title(controller);ax.grid(axis="y",alpha=.25)
    axes[0].set_ylabel("Mean per-case MSE (MW squared)");axes[-1].legend()
    save(fig,"mse_decomposition.png")
    complete=run.old.read(run.ROOT/"complete.json")
    with np.load(run.old.verify(complete["outcomes"][0]["artifact"]),allow_pickle=False) as data:
        x,y,label,index=[data[k] for k in ("inputs","outputs","labels","mapping")]
    semantic=run.old.read(run.ROOT/"semantic_requests.json")
    fig,axes=plt.subplots(2,3,figsize=(14,7))
    for turbine in range(3):
        ig=[int(index[k]) for k,r in enumerate(semantic) if r["kind"]=="grid" and r["turbine"]==turbine]
        omega=x[ig,9+turbine]
        for ax,values,tvalues,title in ((axes[0,turbine],y[ig,turbine],label[ig,turbine],"Own power"),
            (axes[1,turbine],y[ig,:3].astype(float).sum(axis=1),label[ig,:3].astype(float).sum(axis=1),"Farm power")):
            ax.plot(omega,values/1000,"o-",label="Frozen PINN");ax.plot(omega,tvalues/1000,"s--",label="Synthetic teacher")
            ax.axvline(x[int(index[1]),9+turbine],color="black",linestyle=":",label="Old reference")
            ax.axvline(x[int(index[2]),9+turbine],color="C2",linestyle=":",label="NREL reference")
            ax.set_title(f"T{turbine+1}: {title}");ax.set_ylabel("kW");ax.set_xlabel("Varied speed (rad/s)");ax.grid(alpha=.25)
    axes[0,0].legend(fontsize=8)
    fig.suptitle("Static only: legacy Y2, validation case 0, response t=32; other inputs fixed")
    save(fig,"fixed_anchor_grid.png")


def report():
    lock,s=run.context(),run.store()
    closed,groups,changes=decomposition(lock,s)
    refs,local,grid,replays,refgroups=response(lock,s)
    figures(s,groups)
    result=dict(passed=True,closed_loop_cases=60,paired_cases=30,anchors=48,local_pairs=len(local),sampled_grids=len(grid),
        PINN_rows=run.old.read(run.ROOT/"complete.json")["PINN_rows"],report_PINN_queries=0,
        max_replay_power_w=max(r["power_max_abs_w"] for r in replays),max_replay_ueff_m_s=max(r["ueff_max_abs_m_s"] for r in replays),
        reference_power_increases=sum(r["model_direction"]==1 for r in refs),reference_power_decreases=sum(r["model_direction"]==-1 for r in refs),
        reference_label_direction_matches=sum(r["directions_equal"] for r in refs),
        local_own_direction_matches=sum(r["own_directions_equal"] for r in local),local_farm_direction_matches=sum(r["farm_directions_equal"] for r in local),
        aggregate_closed=[r for r in groups if r["controller"] in ("Y","p","pi") and r["family"]=="overall"],
        aggregate_changes=[r for r in changes if r["controller"] in ("Y","p","pi") and r["family"]=="overall"],
        reference_overall=next(r for r in refgroups if r["rule"]==r["controller"]=="all" and r["family"]=="overall"),
        training_steps=0,environment_steps=0,new_winds=0)
    s.json("saved_audit.json",plain(result))
    run.context()
    import json
    print(json.dumps(plain(result),ensure_ascii=False),flush=True)


if __name__=="__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(run.old.ORIGIN/".venv/pinn_tf216")
    report()
