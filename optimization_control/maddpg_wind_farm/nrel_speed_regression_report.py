"""Saved-only audit and fixed-bank comparison; no model or environment calls."""
import io
import json
import math

from . import nrel_speed_regression as run
from .forecast_speed_report import csv_out


def mean(rows,key):
    return sum(float(r[key]) for r in rows)/len(rows)


def plain(value):
    import numpy as np
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value


def report():
    import numpy as np
    from .nrel_speed_adapter import base_reference,speed_action
    old,s,lock=run.old,run.store(),run.context()
    refs=old.read(old.verify(lock["old_references"]));complete=old.read(run.ROOT/"complete.json")
    bank=run.cases(lock);records=[];traces={};new_files=[]
    for rule in ("legacy","nrel"):
        for name in run.CONTROLLERS:
            rows=[];arrays=[]
            if rule=="legacy":sources=refs[name]["cases"]
            else:sources=next(r for r in complete["results"] if r["controller"]==name)["cases"]
            for index,(source,(case,wind)) in enumerate(zip(sources,bank,strict=True)):
                entry=source if rule=="legacy" else old.read(old.verify(source))
                ev=entry["eval"]
                saved=old.read(old.verify(ev["metrics"]))[0]
                with np.load(old.verify(ev["trace"]),allow_pickle=False) as data:
                    trace=data["trace"]
                    if rule=="legacy":
                        assert trace.shape==(1,129,52)
                        trace=run.transfer.extend(trace[0],"legacy")
                    else:
                        assert trace.shape==(129,70) and tuple(data["fields"].tolist())==run.transfer.TRACE
                        obs,inputs=data["obs"],data["inputs"]
                        assert obs.shape==(129,3,15) and inputs.shape==(129,12)
                        applied=trace[:,19:28].reshape(129,3,3)
                        expected=np.concatenate((trace[:,4:7],applied[:,:,0],applied[:,:,1],applied[:,:,2]),axis=1).astype(np.float32)
                        np.testing.assert_array_equal(inputs,expected)
                        np.testing.assert_array_equal(obs[:,:,4],(2*(applied[:,:,2]-.6)/(1.267-.6)-1).astype(np.float32))
                        cmd=trace[:,28:37].reshape(129,3,3).astype(np.float32)
                        np.testing.assert_array_equal(obs[:,:,7],cmd[:,:,2])
                        np.testing.assert_array_equal(trace[1:,52:55],trace[:-1,10:13])
                        np.testing.assert_array_equal(cmd[1:,:,2],speed_action(base_reference(trace[1:,52:55])+.1*trace[1:,46:49]))
                        np.testing.assert_array_equal(np.mean(np.diff(cmd.reshape(129,9),axis=0)**2,axis=1),trace[1:,8])
                        for z in (trace[1:,46:49],trace[1:,49:52]):np.testing.assert_array_equal(z,np.repeat(z[::8],8,axis=0))
                        assert entry["parameters_frozen"] and entry["counters_unchanged"] and entry["updates"]==0
                        new_files.append(source)
                np.testing.assert_array_equal(trace[:,4:7],wind)
                assert np.all(trace[:,1]==case["target_w"])
                row=run.metric(trace,case,rule)
                if rule=="nrel":assert row==saved
                else:assert all(row[k]==v for k,v in saved.items() if k in row)
                rows.append(dict(rule=rule,controller=name,**{k:v for k,v in row.items() if k!="rule"}))
                arrays.append(trace)
            assert len(rows)==18
            records.extend(rows);traces[rule,name]=np.stack(arrays)
    assert len(records)==180 and len(new_files)==90
    csv_out(s,"metrics.csv",records)
    families=[];streams=[]
    stat_keys=("bias_kW","bias_sq_kW2","variance_kW2","mse_kW2","over_fraction","under_fraction",
        "pitch_rate_boundary_fraction","speed_rate_boundary_fraction","heading_rate_boundary_fraction",
        "speed_mean","base_mean","actual_TSR_mean","command_floor_fraction","command_ceiling_fraction","actual_floor_fraction","actual_ceiling_fraction")
    for rule in ("legacy","nrel"):
        for family in ("stationary","ramp","gust","overall"):
            def pool(name):
                return [r for r in records if r["rule"]==rule and (r["controller"].startswith("Y") if name=="Y" else r["controller"]==name)
                    and (family=="overall" or r["family"]==family)]
            y,p,pi=pool("Y"),pool("p"),pool("pi")
            row=dict(rule=rule,family=family,unique_winds=18 if family=="overall" else 6,Y_policy_cases=len(y),baseline_cases=len(pi),
                Y_kW=mean(y,"rmse_w")/1000,P_kW=mean(p,"rmse_w")/1000,PI_kW=mean(pi,"rmse_w")/1000,
                Y_minus_PI_kW=(mean(y,"rmse_w")-mean(pi,"rmse_w"))/1000,
                Y_at400=int(sum(r["rmse_w"]<=400000 for r in y)),Y_at500=int(sum(r["rmse_w"]<=500000 for r in y)))
            families.append(row)
            for name in ("Y",*run.CONTROLLERS):
                data=pool(name)
                entry=dict(rule=rule,controller=name,family=family,cases=len(data),mean_kW=mean(data,"rmse_w")/1000,
                    worst_kW=max(r["rmse_w"] for r in data)/1000,
                    original_precision=bool(mean(data,"rmse_w")<=400000 and max(r["rmse_w"] for r in data)<=500000),
                    speed_min=min(r["speed_min"] for r in data),speed_max=max(r["speed_max"] for r in data),
                    max_pitch_rate=max(r["max_pitch_rate"] for r in data),max_speed_rate=max(r["max_speed_rate"] for r in data),
                    actual_TSR_min=min(r["actual_TSR_min"] for r in data),actual_TSR_max=max(r["actual_TSR_max"] for r in data),
                    **{k:mean(data,k) for k in stat_keys})
                assert abs(entry["mse_kW2"]-entry["bias_sq_kW2"]-entry["variance_kW2"])<1e-7
                streams.append(entry)
    csv_out(s,"family.csv",families);csv_out(s,"operating_summary.csv",streams)
    pairs=[]
    for before in records:
        if before["rule"]!="legacy":continue
        after=next(r for r in records if r["rule"]=="nrel" and r["controller"]==before["controller"] and r["case_id"]==before["case_id"])
        pairs.append(dict(controller=before["controller"],case_id=before["case_id"],episode=before["episode"],family=before["family"],
            old_kW=before["rmse_w"]/1000,new_kW=after["rmse_w"]/1000,delta_kW=(after["rmse_w"]-before["rmse_w"])/1000,
            delta_bias_kW=after["bias_kW"]-before["bias_kW"],delta_bias_sq_kW2=after["bias_sq_kW2"]-before["bias_sq_kW2"],
            delta_variance_kW2=after["variance_kW2"]-before["variance_kW2"],delta_mse_kW2=after["mse_kW2"]-before["mse_kW2"],
            old_pitch_rate_boundary_fraction=before["pitch_rate_boundary_fraction"],new_pitch_rate_boundary_fraction=after["pitch_rate_boundary_fraction"]))
    csv_out(s,"paired.csv",pairs)
    y_pi=[]
    for row in records:
        if row["rule"]!="nrel" or not row["controller"].startswith("Y"):continue
        pi=next(r for r in records if r["rule"]=="nrel" and r["controller"]=="pi" and r["case_id"]==row["case_id"])
        y_pi.append(dict(controller=row["controller"],case_id=row["case_id"],episode=row["episode"],family=row["family"],
            Y_kW=row["rmse_w"]/1000,PI_kW=pi["rmse_w"]/1000,Y_minus_PI_kW=(row["rmse_w"]-pi["rmse_w"])/1000))
    csv_out(s,"new_Y_PI_pairs.csv",y_pi)
    changes=[]
    for family in ("stationary","ramp","gust","overall"):
        before=next(r for r in families if r["rule"]=="legacy" and r["family"]==family)
        after=next(r for r in families if r["rule"]=="nrel" and r["family"]==family)
        changes.append(dict(family=family,**{key+"_new_minus_old_kW":after[key+"_kW"]-before[key+"_kW"] for key in ("Y","P","PI")},new_Y_minus_PI_kW=after["Y_minus_PI_kW"]))
    csv_out(s,"family_changes.csv",changes)
    verdict=[dict(family=f,**{k:v for k,v in next(r for r in families if r["rule"]=="nrel" and r["family"]==f).items() if k!="family"},
        passed=bool(next(r for r in families if r["rule"]=="nrel" and r["family"]==f)["Y_minus_PI_kW"]<0)) for f in ("stationary","ramp","gust")]
    acceptance=dict(kind="used_test_bank_configuration_regression",criterion=lock["config"]["criterion"],families=verdict,
        passed_families=int(sum(x["passed"] for x in verdict)),passed=bool(all(x["passed"] for x in verdict)),new_unseen_test=False,
        unique_winds=18,new_rollouts=90,new_model_rows=complete["new_model_rows"],old_referenced_rollouts=90,
        old_reference_historical_rows=11610,old_reference_new_rows=0,training_steps=0,optimizer_updates=0,new_winds=0,new_pressure_cases=0)
    s.json("primary_acceptance.json",plain(acceptance))
    figures(s,traces,families)
    run.context()
    s.json("saved_audit.json",plain(dict(passed=True,metric_rows=180,paired_rows=90,Y_PI_pairs=54,unique_winds=18,
        all_old_and_new_case_metrics_recomputed=True,actual_model_input_trace_exact=True,old_network_coordinates_exact=True,
        speed_composition_and_causal_Ueff_exact=True,held_actions_exact=True,reward_coordinates_unchanged=True,
        weights_and_counters_frozen=True,training_steps=0,optimizer_updates=0,new_winds=0,report_model_rows=0,
        source_guards=len(lock["hashes"]),acceptance=acceptance)))
    print(json.dumps(plain(dict(families=families,acceptance=acceptance)),ensure_ascii=False),flush=True)


def figures(s,traces,families):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    def save(fig,name):
        fig.tight_layout()
        with io.BytesIO() as buffer:
            fig.savefig(buffer,format="png",dpi=140,bbox_inches="tight");s.write(name,buffer.getbuffer())
        plt.close(fig)
    fig,axes=plt.subplots(4,1,figsize=(12,11),sharex=True)
    for rule,style in (("legacy","--"),("nrel","-")):
        for name,color in (("Y2_selected","C0"),("pi","C1")):
            t=traces[rule,name][17]
            for ax,values in zip(axes,(t[:,2]/1e6,t[:,21],t[:,20],t[:,61]),strict=True):ax.plot(t[:,0],values,style,color=color,label=f"{name} {rule}")
    axes[0].axhline(traces["nrel","Y2_selected"][17][0,1]/1e6,color="black",alpha=.4)
    axes[0].legend(ncol=2);axes[0].set_title("Fixed used-bank case 17: same wind, target and initial state")
    for ax,label in zip(axes,("Farm power (MW)","Rotor 1 speed (rad/s)","Rotor 1 pitch (rad)","Rotor 1 actual TSR"),strict=True):ax.set_ylabel(label);ax.grid(alpha=.25)
    axes[-1].set_xlabel("Time (s)");save(fig,"fixed_case17_stream2.png")
    fig,ax=plt.subplots(figsize=(10,5))
    import numpy as np
    for index,(name,color) in enumerate((("Y","C0"),("P","C2"),("PI","C1"))):
        for rule,alpha,shift in (("legacy",.45,-.06),("nrel",1.,.06)):
            values=[next(r for r in families if r["rule"]==rule and r["family"]==family)[name+"_kW"] for family in ("stationary","ramp","gust")]
            ax.bar(np.arange(3)+(index-1)*.27+shift,values,width=.115,color=color,alpha=alpha,label=f"{name} {rule}")
    ax.set_xticks(range(3),["stationary","ramp","gust"]);ax.set_ylabel("Equal-case/stream mean full-episode RMSE (kW)");ax.legend(ncol=3);ax.grid(axis="y",alpha=.25)
    save(fig,"family_comparison.png")


if __name__=="__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(run.old.ORIGIN/".venv/pinn_tf216")
    report()
