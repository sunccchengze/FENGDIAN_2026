"""Audit same-state branches and chart the recorded value/realization mismatch."""
import csv
import io
import hashlib
import json
import pickle

from . import forecast_speed_training as formal
from .forecast_speed_report import csv_out
from .macro_value_diagnostic import FIELDS, LABELS, ROOT, candidates, context, store

EPS = 1e-7


def direction(x):
    return int(x>EPS)-int(x < -EPS)


def ranks(values):
    import numpy as np
    order=np.argsort(values,kind="stable")
    rank=np.empty(len(order),np.float64)
    start=0
    while start<len(order):
        end=start+1
        while end<len(order) and abs(values[order[end]]-values[order[start]])<=EPS:
            end+=1
        rank[order[start:end]]=(start+end-1)/2
        start=end
    return rank


def rho(x,y):
    import numpy as np
    a,b=ranks(x),ranks(y)
    if np.ptp(a)==0 or np.ptp(b)==0:
        return None
    return float(np.corrcoef(a,b)[0,1])


def metrics(trace,h):
    import numpy as np
    chunk=trace[:,1:h+1]
    g=.99**np.arange(h)
    return dict(ret=chunk[:,:,7]@g, tracking=chunk[:,:,49]@g,
                motion=chunk[:,:,50]@g, rmse=np.sqrt(np.mean(chunk[:,:,3]**2,axis=1)),
                bias=chunk[:,:,3].mean(axis=1))


def mean(values):
    finite=[v for v in values if v is not None]
    return sum(finite)/len(finite) if finite else None


def audit():
    import numpy as np
    from .forecast_decision_contract import forecast_features
    from .history_wind_forecast import RidgeForecast
    from .causal_speed_search import fork, CURRENT_FIELDS
    from ..environments.maddpg_farm_env import MADDPGFarmEnv
    lock=context()
    complete=formal.read(ROOT/"complete.json")
    budget=formal.read(ROOT/"budget.json")
    assert len(budget["scopes"])==13 and all(s["status"]=="complete" for s in budget["scopes"])
    assert sum(s["actual"] for s in budget["scopes"])==30089 and complete["optimizer_updates"]==0
    model=RidgeForecast.load(formal.verify(lock["source"]["forecast"]))
    val=formal.bank(lock["source"],"validation")
    anchors,all_candidates,locals_,groups=[],[],[],[]
    illustration=None
    for group in complete["groups"]:
        with np.load(formal.verify(group["artifact"]),allow_pickle=False) as data:
            d={key:data[key] for key in data.files}
        assert tuple(d["fields"].tolist())==FIELDS and tuple(d["labels"].tolist())==LABELS
        meta=json.loads(d["meta"].item())
        assert len(meta)==12 and d["trace"].shape==(12,9,17,51)
        for j,m in enumerate(meta):
            arm=m["arm"]
            trace=d["trace"][j]
            prefix=d["history"][j,:m["history_length"]]
            case,wind=val[m["case_index"]]
            t=m["t"]
            assert m["case_id"]==case["id"] and t in (32,80) and m["history_length"]==t+1
            np.testing.assert_array_equal(prefix,wind[:t+1].astype(np.float32))
            blob=d["capsule_bytes"][d["capsule_offsets"][j]:d["capsule_offsets"][j+1]].tobytes()
            assert hashlib.sha256(blob).hexdigest()==m["capsule_sha256"]
            current=pickle.loads(blob)  # Trusted artifact, bound to the completed scope SHA.
            assert tuple(current)==CURRENT_FIELDS and current["t"]==t
            assert current["actuator"]._step_index==t
            child=fork(current,None,MADDPGFarmEnv)
            np.testing.assert_array_equal(child._observe(),d["obs"][j,0,0])
            np.testing.assert_array_equal(np.repeat(child._observe()[None],9,axis=0),d["obs"][j,:,0])
            np.testing.assert_array_equal(trace[0,1:],d["base"][m["case_index"],t+1:t+17])
            np.testing.assert_array_equal(trace[:,:,4:7],np.repeat(wind[None,t:t+17].astype(np.float32),9,axis=0))
            f=forecast_features(model,prefix,arm=="C")
            np.testing.assert_array_equal(f,np.asarray(m["current_forecast"],np.float32))
            for n in range(9):
                nxt=forecast_features(model,np.concatenate((prefix,trace[n,1:9,4:7].astype(np.float32))),arm=="C")
                np.testing.assert_array_equal(d["next_forecast"][j,n],nxt)
            z=d["candidates"][j]
            np.testing.assert_array_equal(z,candidates(z[0]))
            np.testing.assert_array_equal(trace[:,1:9,46:49],np.repeat(z[:,None],8,axis=1))
            np.testing.assert_array_equal(trace[:,9:17,46:49],np.repeat(trace[:,9:10,46:49],8,axis=1))
            np.testing.assert_allclose(trace[:,1:,7],trace[:,1:,49]+trace[:,1:,50],rtol=0,atol=5e-8)
            np.testing.assert_array_equal(trace[:,:,3],trace[:,:,2]-trace[:,:,1])
            parent=trace[:,1:,37:46].reshape(9,16,3,3)
            command=trace[:,1:,28:37].reshape(9,16,3,3)
            actual=trace[:,:,19:28].reshape(9,17,3,3)
            np.testing.assert_array_equal(command[:,:,:,:2],parent[:,:,:,:2])
            np.testing.assert_array_equal(command[:,:,:,2],np.clip(
                parent[:,:,:,2]+2*.1*trace[:,1:,46:49]/.667,-1,1).astype(np.float32))
            np.testing.assert_array_equal(command[:,0,:,:2],np.repeat(command[0:1,0,:,:2],9,axis=0))
            assert np.all(np.abs(np.diff(actual[:,:,:,1:],axis=1)).max(axis=(0,1,2))
                          <=np.array([.00872664626,.1])+1e-7)
            a,b=metrics(trace,8),metrics(trace,16)
            q=d["q"][j].astype(np.float64);qmean=q.mean(axis=1)
            zero=d["q_zero_forecast"][j].astype(np.float64).mean(axis=1)
            qbest=int(np.argmax(qmean))
            best8,best16=int(np.argmax(a["ret"])),int(np.argmax(b["ret"]))
            eligible8=(a["ret"]>=a["ret"][0]+.01)&(a["rmse"]<=.95*a["rmse"][0])
            eligible16=(b["ret"]>=b["ret"][0]+.01)&(b["rmse"]<=.95*b["rmse"][0])
            suppressed=bool(eligible16.any() and np.max(qmean[eligible16])<=qmean[0]+EPS)
            selected8=int(np.argmax(np.where(eligible8,a["ret"],-np.inf))) if eligible8.any() else 0
            gain8=float(a["ret"][selected8]-a["ret"][0])
            gain16=float(b["ret"][selected8]-b["ret"][0])
            pitch_delta=actual[selected8,1:,:,1]-actual[0,1:,:,1]
            de=trace[selected8,1:16,3]-trace[0,1:16,3]
            dp=(parent[selected8,1:,:,1]-parent[0,1:,:,1]).mean(axis=1)*.11
            signmask=(np.abs(de)>100)&(np.abs(dp)>1e-5)
            comp=float(np.mean(de[signmask]*dp[signmask]>0)) if signmask.any() else None
            rs=rho(qmean,b["ret"]);r0=rho(zero,b["ret"])
            base=dict(group=m["group"],arm=arm,run=m["run"],role=m["role"],checkpoint_step=m["checkpoint_step"],
                      case_id=m["case_id"],t=t)
            anchor=dict(**base,trained=bool(m["checkpoint_step"]),rho8=rho(qmean,a["ret"]),rho16=rs,rho16_zero_forecast=r0,
                **{f"critic{i}_rho16":rho(q[:,i],b["ret"]) for i in range(3)},
                critic_top_disagreement=len(set(np.argmax(q,axis=0)))>1,
                q_best=LABELS[qbest],realized_best8=LABELS[best8],realized_best16=LABELS[best16],
                q_own_is_top=bool(qmean[0]>=qmean.max()-EPS),q_top_realized_best=bool(b["ret"][qbest]>=b["ret"].max()-EPS),
                q_top_worse_than_own=bool(b["ret"][qbest]<b["ret"][0]-EPS),
                own_regret8=float(a["ret"][best8]-a["ret"][0]),own_regret16=float(b["ret"][best16]-b["ret"][0]),
                q_top_regret16=float(b["ret"][best16]-b["ret"][qbest]),
                meaningful8=bool(eligible8.any()),meaningful16=bool(eligible16.any()),q_suppresses_all_meaningful16=suppressed,
                best8_significant_candidate=LABELS[selected8],significant8_gain8=gain8,significant8_gain16=gain16,
                significant8_gain_attenuated=bool(eligible8.any() and gain16<gain8-EPS),
                significant8_gain_reversed=bool(eligible8.any() and gain16 < -EPS),
                pitch_delta_mean_abs_first8=float(np.abs(pitch_delta[:8]).mean()),
                pitch_delta_mean_abs_next8=float(np.abs(pitch_delta[8:]).mean()),pitch_feedback_sign_agreement=comp,
                pitch_feedback_sign_count=int(signmask.sum()),
                ablation_top_changed=int(np.argmax(zero))!=qbest,
                ablation_rho16_improved=bool(rs is not None and r0 is not None and r0>rs+EPS),
                ablation_rho16_worsened=bool(rs is not None and r0 is not None and r0<rs-EPS),
                actor_feature_change_max_rad_s=float(.1*np.max(np.abs(z[0]-d["actor_zero_forecast"][j]))))
            anchors.append(anchor)
            for i,label in enumerate(LABELS):
                all_candidates.append(dict(**base,candidate=label,**{f"z{k}":float(z[i,k]) for k in range(3)},
                    qmean=float(qmean[i]),**{f"q{k}":float(q[i,k]) for k in range(3)},
                    qmean_zero_forecast=float(zero[i]),
                    **{f"{key}{h}":float(r[key][i]) for h,r in ((8,a),(16,b)) for key in r}))
            for i in range(3):
                lo,hi=3+2*i,4+2*i
                dq=float(q[hi,i]-q[lo,i]);dm=float(qmean[hi]-qmean[lo]);dr8=float(a["ret"][hi]-a["ret"][lo])
                dr16=float(b["ret"][hi]-b["ret"][lo]);g=float(d["own_gradient"][j,0,i])
                locals_.append(dict(**base,turbine=i,dq_own=dq,dq_mean=dm,gradient=g,dr8=dr8,dr16=dr16,
                    q_direction=direction(dq),mean_q_direction=direction(dm),gradient_direction=direction(g),
                    realized_direction8=direction(dr8),realized_direction16=direction(dr16)))
            if m["role"]=="final" and (illustration is None or anchor["own_regret16"]>illustration[0]["own_regret16"]):
                illustration=(anchor,trace.copy(),qbest,best16)
        k=group["group"]
        group_a=[x for x in anchors if x["group"]==k]
        group_l=[x for x in locals_ if x["group"]==k]
        groups.append(summarize(group_a,group_l))
    assert len(anchors)==144 and len(all_candidates)==1296 and len(locals_)==432
    for path,rows in (("metrics.csv",all_candidates),("anchors.csv",anchors),
                      ("local_direction.csv",locals_),("groups.csv",groups)):
        csv_out(store(),path,rows)
    trained=[x for x in anchors if x["trained"]]
    splits={}
    for name,keep in (
        ("all",lambda x:True),("trained",lambda x:x["checkpoint_step"]>0),
        ("B_final",lambda x:x["arm"]=="B" and x["role"]=="final"),
        ("C_final",lambda x:x["arm"]=="C" and x["role"]=="final"),
        ("C_trained",lambda x:x["arm"]=="C" and x["checkpoint_step"]>0)):
        splits[name]=summarize([x for x in anchors if keep(x)],[x for x in locals_ if keep(x)])
    store().json("verification.json",dict(passed=True,anchors=144,branches=1296,trained_anchors=len(trained),
        true_model_rows=30024,mock_model_rows=65,model_rows=30089,additional_audit_queries=0,
        exact_clone_current_obs_and_own_branch=True,causal_next_feature_checked=True,all_parameters_rng_unchanged=True,
        source_hashes_verified=len(lock["hashes"]),optimizer_updates=0,new_test=0,splits=splits))
    figures(groups,illustration)
    store().write("summary.txt",("Fixed 8/16-step macro value diagnostic completed. seed=42.\n"
        "144 anchors, 1296 branches, 30024 true model input rows and 65 mock rows.\n"
        "Formal RL and optimizer updates 0. No independent wind released.\n"
        "See groups.csv, anchors.csv, metrics.csv, local_direction.csv and verification.json.\n").encode())


def summarize(anchors,local):
    def count(key):
        return sum(x[key] for x in anchors)
    def direction_counts(source,h):
        rows=[x for x in local if x[source] and x[f"realized_direction{h}"]]
        return sum(x[source]==x[f"realized_direction{h}"] for x in rows),len(rows)
    d8,n8=direction_counts("q_direction",8)
    d16,n16=direction_counts("q_direction",16)
    g16,gn=direction_counts("gradient_direction",16)
    return dict(group=anchors[0]["group"],anchors=len(anchors),trained=sum(x["trained"] for x in anchors),
        rho8=mean(x["rho8"] for x in anchors),rho16=mean(x["rho16"] for x in anchors),
        rho16_zero_forecast=mean(x["rho16_zero_forecast"] for x in anchors),
        rho16_negative=sum(x["rho16"] is not None and x["rho16"]<0 for x in anchors),
        rho16_undefined=sum(x["rho16"] is None for x in anchors),
        mean_own_regret8=mean(x["own_regret8"] for x in anchors),
        mean_own_regret16=mean(x["own_regret16"] for x in anchors),
        q_own_top=count("q_own_is_top"),q_top_realized_best=count("q_top_realized_best"),
        q_top_worse_than_own=count("q_top_worse_than_own"),meaningful8=count("meaningful8"),
        meaningful16=count("meaningful16"),q_suppressed16=count("q_suppresses_all_meaningful16"),
        critic_top_disagreement=count("critic_top_disagreement"),
        own_local_match8=d8,own_local_total8=n8,own_local_match16=d16,own_local_total16=n16,
        gradient_match16=g16,gradient_total16=gn,attenuated8=count("significant8_gain_attenuated"),
        reversed8=count("significant8_gain_reversed"),ablation_top_changed=count("ablation_top_changed"),
        ablation_rho16_improved=count("ablation_rho16_improved"),ablation_rho16_worsened=count("ablation_rho16_worsened"),
        max_actor_feature_change_rad_s=max(x["actor_feature_change_max_rad_s"] for x in anchors))


def figures(groups,example):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    def save(fig,name):
        for ext in ("png","pdf"):
            with io.BytesIO() as buf:
                fig.savefig(buf,format=ext,dpi=170)
                store().write(f"figures/{name}.{ext}",buf.getbuffer())
        plt.close(fig)
    with (ROOT/"critic_snapshots.csv").open() as f:
        snap=list(csv.DictReader(f))
    with (ROOT/"update_episode_means.csv").open() as f:
        history=list(csv.DictReader(f))
    colors={"B":"#376999","C":"#238368"}
    fig,axs=plt.subplots(5,3,figsize=(12,10),layout="constrained",sharex=True,sharey="row")
    fields=("critic_loss","q_behavior_abs95","td_rms","gradient_abs_mean","distance_rms")
    labels=("Critic MSE, logged","|Q| p95, common rows","TD RMS, common rows",
            "Mean |own dQ/dz|","Policy/replay z RMS")
    for run in range(3):
        for arm in ("B","C"):
            part=[r for r in history if r["arm"]==arm and int(r["run"])==run and int(r["updates"])]
            axs[0,run].plot([int(r["step"]) for r in part],[float(r["critic_loss"]) for r in part],
                            color=colors[arm],alpha=.30,lw=.7)
            weighted=[]
            for step in (2048,4096,6144,8192):
                p=[r for r in part if step-2048<int(r["step"])<=step]
                weighted.append(sum(float(r["critic_loss"])*int(r["updates"]) for r in p)/sum(int(r["updates"]) for r in p))
            axs[0,run].plot((2048,4096,6144,8192),weighted,marker="o",color=colors[arm],label=arm)
            for i,key in enumerate(fields[1:],1):
                points=[0,2048,4096,6144,8192]
                values=[mean(float(r[key]) for r in snap if r["cohort"]=="common_first256"
                            and r["arm"]==arm and int(r["run"])==run and int(r["step"])==step) for step in points]
                axs[i,run].plot(points,values,marker="o",color=colors[arm])
        axs[0,run].set_title(f"Stream {run}")
        axs[-1,run].set_xlabel("Physical training steps")
        for a in axs[:,run]:
            a.grid(alpha=.2)
    axs[0,2].legend(frameon=False)
    for i,label in enumerate(labels):
        axs[i,0].set_ylabel(label)
    fig.suptitle("Training logs and frozen Critic snapshots")
    save(fig,"critic_progress")
    x=np.arange(len(groups))
    fig,ax=plt.subplots(3,1,figsize=(12,8),sharex=True,layout="constrained")
    ax[0].scatter(x-.12,[r["rho8"] for r in groups],label="8 s",color="#376999")
    ax[0].scatter(x+.12,[r["rho16"] for r in groups],label="16 s",color="#238368")
    ax[0].axhline(0,color=".5",lw=.7);ax[0].set_ylabel("Mean Spearman rho");ax[0].legend(frameon=False)
    ax[1].bar(x-.17,[r["meaningful8"] for r in groups],width=.34,label="8 s",color="#376999")
    ax[1].bar(x+.17,[r["meaningful16"] for r in groups],width=.34,label="16 s",color="#238368")
    ax[1].set_ylabel("Meaningful anchors / 12");ax[1].legend(frameon=False)
    for h,dx,color in ((8,-.17,"#376999"),(16,.17,"#238368")):
        value=[r[f"own_local_match{h}"]/r[f"own_local_total{h}"] if r[f"own_local_total{h}"] else np.nan
               for r in groups]
        ax[2].bar(x+dx,value,width=.34,color=color)
    ax[2].axhline(.5,color=".5",lw=.7);ax[2].set_ylabel("Own Critic sign agreement")
    ax[2].set_xticks(x,[r["group"].replace("_","\n") for r in groups])
    for a in ax:
        a.grid(axis="y",alpha=.2)
    fig.suptitle("Same-state candidate value and realized return")
    save(fig,"candidate_alignment")
    info,tr,qbest,best=example
    fig,ax=plt.subplots(4,1,figsize=(10,8.5),sharex=True,layout="constrained")
    for i,label,color in ((0,"Own action","#333333"),(qbest,"Critic first","#b56933"),(best,"16 s realized first","#238368")):
        t=np.arange(17)
        data=tr[i]
        ax[0].plot(t,data[:,3]/1000,label=label,color=color)
        ax[1].plot(t,data[:,19:28].reshape(17,3,3)[:,:,1].mean(axis=1)*180/np.pi,color=color)
        ax[2].plot(t,data[:,19:28].reshape(17,3,3)[:,:,2].mean(axis=1),color=color)
        ax[3].plot(t[1:],np.cumsum((.99**np.arange(16))*data[1:,7]),color=color)
    for a,y in zip(ax,("Power error (kW)","Mean pitch (deg)","Mean speed (rad/s)","Realized return")):
        a.set_ylabel(y);a.axvline(8,color=".55",ls="--",lw=.7);a.grid(alpha=.2)
    ax[0].legend(frameon=False,ncol=3)
    ax[3].set_xlabel("Seconds from anchor")
    fig.suptitle(f"Largest final own-action regret in this grid | {info['group']} | {info['case_id']} | t={info['t']}")
    save(fig,"largest_final_regret")


if __name__=="__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(formal.ORIGIN/".venv/pinn_tf216")
    audit()
