"""Plot frozen CSV evidence; no model evaluation or training."""
from pathlib import Path

from .anchor_closeout import context, read_csv, write_json, sha


def figures(root):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cfg,_,_,selection=context(root)
    out=root/"figures"
    history=read_csv(root/"audit/history.csv")
    aggregate=read_csv(root/"test/aggregate.csv")
    generated=[]
    def save(fig,name):
        for extension in ("png","pdf"):
            path=out/f"{name}.{extension}"
            fig.savefig(path,dpi=170)
            generated.append(path)
        plt.close(fig)
    palette={"baseline":"#ce644f","anchor":"#247ba0"}
    fig,axes=plt.subplots(1,3,figsize=(15,4.6),sharey=True,layout="constrained")
    for run,ax in enumerate(axes):
        for arm in ("baseline","anchor"):
            rows=[r for r in history if r["stage"]==arm and int(r["run_id"])==run]
            ax.plot([int(r["steps"]) for r in rows],[float(r["validation_rmse_w"])/1000 for r in rows],"o-",label=arm,color=palette[arm])
            result=next(r for r in selection["results"] if r["stage"]==arm and r["run_id"]==run)
            ax.scatter([result["best"]["step"]],[result["best"]["score_w"]/1000],marker="*",s=160,color=palette[arm],edgecolor="black",zorder=5)
        ax.axhline(400,color="gray",ls=":",lw=1,label="400 kW mean only")
        ax.set(title=f"stream {run}",xlabel="Additional training steps")
        ax.grid(alpha=.2)
    axes[0].set_ylabel("Validation mean RMSE [kW]"); axes[0].legend(fontsize=8)
    fig.suptitle("Frozen lambda 0 / 1 | full authority at every evaluation | stars = validation selection")
    save(fig,"paired_validation")
    fig,axes=plt.subplots(1,2,figsize=(13,4.6),layout="constrained")
    labels=("initial","selected","final","p","pi")
    for ax,subset in zip(axes,("routine","known_stress")):
        for arm,shift in (("baseline",-.07),("anchor",.07)):
            rows=[next(r for r in aggregate if r["stage"]==arm and r["subset"]==subset and r["controller"]==label) for label in labels]
            ax.errorbar(np.arange(len(labels))+shift,[float(r["mean_rmse_w"])/1000 for r in rows],yerr=[float(r["std_across_runs_w"])/1000 for r in rows],fmt="o",capsize=4,label=arm,color=palette[arm])
        ax.set(xticks=np.arange(len(labels)),xticklabels=labels,ylabel="Mean case RMSE [kW]",title="Locked routine test" if subset=="routine" else "Known low-wind regression")
        ax.grid(alpha=.2); ax.legend()
    fig.suptitle("Same cases / actuators | SD across 3 derived streams, not a confidence interval")
    save(fig,"locked_test")
    fig,axes=plt.subplots(1,3,figsize=(15,4),layout="constrained")
    for ax,key,factor,label in zip(axes,("drift_yaw_rad","drift_pitch_rad","drift_speed_rad_s"),(180/np.pi,180/np.pi,1),("Yaw [deg]","Pitch [deg]","Speed [rad/s]")):
        for arm in ("baseline","anchor"):
            for run in range(3):
                rows=[r for r in history if r["stage"]==arm and int(r["run_id"])==run]
                ax.plot([int(r["steps"]) for r in rows],[float(r[key])*factor for r in rows],color=palette[arm],ls=("-","--",":")[run],label=f"{arm} / {run}")
        ax.set(xlabel="Training steps",ylabel="Current-state parent-action drift RMS",title=label); ax.grid(alpha=.2)
    axes[0].legend(fontsize=7)
    fig.suptitle("Action drift on each controller's own validation rollout")
    save(fig,"parent_action_drift")
    diagnostics=read_csv(root/"diagnostic/metrics.csv")
    names=["".join(p) for p in __import__("itertools").product("SF",repeat=3)]+["zero_yaw","zero_speed","zero_both","parent_yaw","parent_pitch","parent_speed","parent_all"]
    fig,axes=plt.subplots(2,3,figsize=(16,11),sharex=True,sharey=True,layout="constrained")
    for row,arm in enumerate(("baseline","anchor")):
        for run,ax in enumerate(axes[row]):
            values=[float(next(r for r in diagnostics if r["stage"]==arm and int(r["run_id"])==run and r["variant"]==name)["mean_rmse_w"])/1000 for name in names]
            ax.barh(np.arange(len(names)),values,color=["#ce644f" if name=="FFF" else "#247ba0" for name in names])
            ax.set(yticks=np.arange(len(names)),yticklabels=names,title=f"{arm} / stream {run}",xlabel="Validation mean RMSE [kW]")
            ax.invert_yaxis(); ax.grid(axis="x",alpha=.2)
    fig.suptitle("Yaw / pitch / speed recomputed at current obs | S=selected, F=final | differences are non-additive")
    save(fig,"channel_interventions")
    local=read_csv(root/"diagnostic/local_response.csv")
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),layout="constrained")
    for ax,channel in zip(axes,("speed","yaw")):
        offsets=sorted(set(float(r["offset"]) for r in local if r["channel"]==channel))
        for endpoint in ("parent_all","SSS","FFF"):
            parts=[[float(r["farm_delta_w"])/1000 for r in local if r["channel"]==channel and r["endpoint"]==endpoint and r["turbine"]=="all" and float(r["offset"])==offset] for offset in offsets]
            median=[np.median(p) for p in parts]
            ax.plot(offsets,median,"o-",label=endpoint)
            ax.fill_between(offsets,[np.quantile(p,.1) for p in parts],[np.quantile(p,.9) for p in parts],alpha=.1)
        ax.axhline(0,color="gray",lw=1); ax.set(xlabel="Applied offset [rad/s]" if channel=="speed" else "Applied offset [deg]",ylabel="Farm power change [kW]",title=f"Common {channel} perturbation"); ax.grid(alpha=.2); ax.legend(fontsize=8)
    fig.suptitle("Validation physical states: median and 10-90% range | static sensitivity, not tracking gain")
    save(fig,"local_model_response")
    offsets=read_csv(root/"diagnostic/fixed_offset_cases.csv")
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),layout="constrained")
    for ax,channel in zip(axes,("speed","yaw")):
        for run in range(3):
            rows=[r for r in offsets if int(r["run_id"])==run and r["channel"] in (channel,"none")]
            values=sorted(set(float(r["offset_physical"]) for r in rows))
            means=[np.mean([float(r["rmse_w"])/1000 for r in rows if float(r["offset_physical"])==value]) for value in values]
            ax.plot(np.asarray(values)*(180/np.pi if channel=="yaw" else 1),means,"o-",label=f"stream {run}")
        ax.set(xlabel="Common command offset [deg]" if channel=="yaw" else "Common command offset [rad/s]",ylabel="Validation mean RMSE [kW]",title=f"Frozen parent + {channel} offset"); ax.legend(); ax.grid(alpha=.2)
    fig.suptitle("Predeclared validation feasibility probe | same actuators | not a selected training candidate")
    save(fig,"fixed_offset_validation")
    traces=read_csv(root/"test/trajectories.csv")
    case="test_gust_1_pitch0.025"
    for run in range(3):
        fig,axes=plt.subplots(5,1,figsize=(12,13),sharex=True,layout="constrained")
        for label,color in (("initial","#7b8b96"),("selected","#247ba0"),("final","#ce644f"),("pi","#6e994e")):
            rows=[r for r in traces if r["stage"]=="anchor" and r["case_id"]==case and r["controller"]==label and int(r["run_id"])==(-1 if label=="pi" else run)]
            x=[int(r["step"]) for r in rows]
            axes[0].plot(x,[float(r["farm_power_w"])/1e6 for r in rows],label=label,color=color)
            for i,style in zip((1,2,3),("-","--",":")):
                for ax,key,factor in ((axes[1],f"heading_{i}_rad",180/np.pi),(axes[2],f"gamma_{i}",180/np.pi),(axes[3],f"pitch_{i}",180/np.pi),(axes[4],f"speed_{i}",1)):
                    ax.plot(x,[float(r[key])*factor for r in rows],color=color,ls=style,alpha=.85,lw=1)
        axes[0].axhline(float(rows[0]["target_w"])/1e6,color="black",ls="--",label="target")
        axes[1].plot(x,[float(r["direction_rad"])*180/np.pi for r in rows],color="black",label="wind direction")
        for ax,label in zip(axes,("Farm power [MW]","Nacelle heading [deg]","Actual misalignment [deg]","Applied pitch [deg]","Applied speed [rad/s]")):
            ax.set_ylabel(label); ax.grid(alpha=.2)
        axes[0].legend(ncol=5); axes[1].legend(); axes[-1].set_xlabel("Control step [1 s]")
        fig.suptitle(f"Predeclared gust case / stream {run} | turbine 1/2/3 = solid/dashed/dotted | synthetic PINN")
        save(fig,f"actual_controls_stream_{run}")
    inputs={str(root/name):sha(root/name) for name in ("audit/history.csv","test/aggregate.csv","test/trajectories.csv","diagnostic/metrics.csv","diagnostic/local_response.csv","diagnostic/fixed_offset_cases.csv")}
    write_json(out/"complete.json",dict(inputs=inputs,generated={p.name:sha(p) for p in generated},python_matplotlib=True,model_evaluations=0))
    context(root)
    print("Figures complete",len(generated),flush=True)
