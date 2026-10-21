"""Model-specific steady feasibility certificates and finite-actuator diagnostics.

For equal-rated turbines and U<=11.4, write a_i=extraction_i*cos(gamma_i)^2.
P/R/(U/11.4)^3 = a1+(1-.12*a1)^3*a2
                   +(1-.06*a1)^3*(1-.12*a2)^3*a3.
On [0,1]^3, derivatives in a1>=1-.36-.18>0, a2>=.88^3-.36>0,
and a3>0. Thus a_i=1 is a global upper bound, attained at zero pitch/yaw
and local optimal speed when that speed lies inside the declared controls.
This proof applies ONLY to CoupledIntegrationPredictor, not a real PINN.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import torch
from .algorithm import MADDPG
from .controllers import PitchController
from .workflow import build_env,fresh_output,write_csv
from ..environments.pinn_adapter import CoupledIntegrationPredictor,DEFAULT_FEATURES
from ..environments.plant_model import DisturbanceBatch,AppliedOperatingPoint

TOLERANCE_W=10.0


def check_model(env):
    p=env.plant
    if type(p.predictor) is not CoupledIntegrationPredictor or p.features!=DEFAULT_FEATURES:
        raise ValueError("certificate only supports the exact integration mock")
    if not np.all(p.rated_power_w==p.rated_power_w[0]) or env.low[1]<0:
        raise ValueError("equal ratings and nonnegative pitch required")
    if not np.array_equal(p.predictor.rated,p.rated_power_w) or not np.array_equal(env.rated,p.rated_power_w):
        raise ValueError("predictor, adapter and environment ratings must agree")
    if not (np.all(p.input_mean==0) and np.all(p.input_scale==1) and np.all(p.output_mean==0) and np.all(p.output_scale==1)):
        raise ValueError("certificate requires identity model normalization")


def upper_bound(env,wind):
    check_model(env)
    wind=np.asarray(wind,dtype=float)
    if np.any(~np.isfinite(wind)) or np.any(wind<=0): raise ValueError("positive finite wind required")
    rated=float(env.rated[0])
    tight=rated*(wind/11.4)**3*(1+.88**3+(.94*.88)**3)
    loose=3*rated*np.minimum((wind/11.4)**3,1)
    # Float32 predictor arithmetic is allowed a conservative 10 W margin.
    return np.where(wind<=11.4,tight,loose)+TOLERANCE_W


def operating_point(env,wind,beta,speed_fraction=1.):
    check_model(env)
    u=np.full(3,float(wind)); physical=np.zeros((3,3)); physical[:,1]=beta
    for i in range(3):
        speed=np.clip(u[i]/11.4*1.267,.2,1.267)
        physical[i,2]=env.low[2]+speed_fraction*(np.clip(speed,env.low[2],env.high[2])-env.low[2])
        extraction=np.exp(-beta/.21)*np.exp(-.5*((physical[i,2]-speed)/.45)**2)
        for j in range(i+1,3): u[j]*=1-.12/(j-i)*extraction
    return physical


def predict(env,wind,physical):
    d=DisturbanceBatch(*(np.array([[v]],dtype=np.float32) for v in (wind,env.config["wind_direction_rad"],env.config["turbulence_intensity"])))
    op=AppliedOperatingPoint(env.plant.turbine_ids,*(physical[:,i][None,:] for i in range(3)))
    return float(env.plant.predict_steady(d,op).floris_farm_power_sum_w[0,0])


def witness(env,wind,target):
    check_model(env)
    if not np.isfinite(target) or target<=0: raise ValueError("positive target required")
    if not env.low[0]<=0<=env.high[0] or env.low[1]!=0:
        raise ValueError("witness requires zero yaw/pitch inside control domain")
    peak=operating_point(env,wind,0); achieved=predict(env,wind,peak)
    upper=float(upper_bound(env,wind))
    if achieved>upper: raise AssertionError("certificate violated")
    a,b=0.,float(env.high[1]); low=predict(env,wind,operating_point(env,wind,b))
    point=peak
    if low<=target<=achieved:
        for _ in range(35):
            mid=(a+b)/2; candidate=operating_point(env,wind,mid)
            if predict(env,wind,candidate)>target: a=mid
            else: b=mid
        point=operating_point(env,wind,(a+b)/2)
    elif target<low:
        # Feathered pitch plus slower rotor extends the constructive low-power path.
        slow=operating_point(env,wind,b,0)
        point=slow
        if predict(env,wind,slow)<=target:
            left,right=0.,1.
            for _ in range(35):
                mid=(left+right)/2; candidate=operating_point(env,wind,b,mid)
                if predict(env,wind,candidate)<target: left=mid
                else: right=mid
            point=operating_point(env,wind,b,(left+right)/2)
    value=predict(env,wind,point)
    status="unreachable_above_certified_upper" if target>upper else ("steady_feasible_witness" if abs(value-target)<=TOLERANCE_W else "unresolved")
    return {"wind_m_s":float(wind),"target_w":float(target),"upper_bound_w":upper,
        "known_available_w":achieved,"witness_power_w":value,"status":status,
        "certified_shortfall_floor_w":max(target-upper,0),"physical":point.tolist(),
        "bound_kind":"tight_mock_low_speed" if wind<=11.4 else "loose_no_wake_bound"}


def error_components(errors,upper,target):
    errors=np.asarray(errors,dtype=float); upper=np.broadcast_to(upper,errors.shape)
    shortfall=np.maximum(-errors,0); floor=np.maximum(target-upper,0)
    if np.any(shortfall+1e-4<floor): raise AssertionError("power above certified upper")
    residual=np.maximum(shortfall-floor,0)
    split=len(errors)//2
    return dict(rmse_w=float(np.sqrt(np.mean(errors**2))),
        first_half_rmse_w=float(np.sqrt(np.mean(errors[:split]**2))),
        second_half_rmse_w=float(np.sqrt(np.mean(errors[split:]**2))),
        tail_mean_error_w=float(np.mean(errors[split:])),
        mean_shortfall_w=float(shortfall.mean()),certified_shortfall_floor_w=float(floor.mean()),
        residual_shortfall_w=float(residual.mean()),mean_overshoot_w=float(np.maximum(errors,0).mean()))


def fixed_rollout(cfg,wind,target,*,agent=None,baseline=None,physical=None):
    env=build_env(cfg)
    trace=np.tile([wind,cfg["environment"]["wind_direction_rad"],cfg["environment"]["turbulence_intensity"]],(env.horizon+1,1))
    obs,info=env.reset(options={"wind_trajectory":trace,"target_w":target})
    controller=PitchController(env,cfg["baselines"],baseline) if baseline else None
    errors=[]; powers=[]; actions=[]
    for _ in range(env.horizon):
        a=agent.act(obs) if agent else (controller.act(obs) if controller else env.normalize_commands(physical))
        obs,_,done,_,info=env.step(a)
        errors.append(info["error_w"]); powers.append(info["farm_power_w"]); actions.append(a)
        if done: break
    result=error_components(errors,upper_bound(env,wind),target)
    result.update(tail_mean_power_w=float(np.mean(powers[len(powers)//2:])),
                  boundary_fraction=float(np.mean(np.abs(actions)>.98)))
    return result


def diagnose(source,output):
    torch.set_num_threads(1)
    source=Path(source); selection=json.loads((source/"selection.json").read_text(encoding="utf-8"))
    models=[MADDPG.load(r["best"]["checkpoint"]) for r in selection["results"][selection["winner"]]]
    cfg=models[0][1]["config"]; env=build_env(cfg)
    out=fresh_output(output,{"seed":42,"source":str(source.resolve()),"config":cfg,
        "winds_m_s":[5.5,7.5,8.,9.],"targets_w":[.8e6,1.2e6,2.4e6,3e6,3.6e6,5e6],"purpose":"development_diagnosis_not_test"})
    rows=[]; witnesses=[]; probes=[]
    for wind in (5.5,7.5,8.,9.):
        for target in (.8e6,1.2e6,2.4e6,3e6,3.6e6,5e6):
            w=witness(env,wind,target); witnesses.append(w)
            common={k:v for k,v in w.items() if k not in ("physical","certified_shortfall_floor_w")}
            for i,(agent,_) in enumerate(models):
                rows.append(dict(controller="maddpg",run_id=i+1,**common,**fixed_rollout(cfg,wind,target,agent=agent)))
                trace=np.tile([wind,cfg["environment"]["wind_direction_rad"],.08],(env.horizon+1,1))
                obs,_=env.reset(options={"wind_trajectory":trace,"target_w":target})
                a=agent.act(obs)
                probes.append(dict(run_id=i+1,wind_m_s=wind,target_w=target,**{f"T{i+1}_{ch}":float(a[i,j]) for i in range(3) for j,ch in enumerate(("yaw","pitch","speed"))}))
            for mode in ("p","pi"):
                bc=deepcopy(cfg); bc["baselines"]=selection["baselines"][mode]
                rows.append(dict(controller=mode,run_id=-1,**common,**fixed_rollout(bc,wind,target,baseline=mode)))
            rows.append(dict(controller="steady_witness_through_actuator",run_id=-1,**common,
                             **fixed_rollout(cfg,wind,target,physical=np.array(w["physical"]))))
        print(f"reachability diagnostic U={wind} complete",flush=True)
    write_csv(out/"metrics.csv",rows); write_csv(out/"same_state_target_probe.csv",probes)
    (out/"witnesses.json").write_text(json.dumps(witnesses,indent=2),encoding="utf-8")
    plot_diagnosis(out,rows)
    (out/"summary.txt").write_text(json.dumps({"cases":len(witnesses),"rows":len(rows),
        "steady_feasible":sum(w["status"]=="steady_feasible_witness" for w in witnesses),
        "certified_unreachable":sum(w["status"].startswith("unreachable") for w in witnesses),
        "scope":"exact mock only; static floor not a dynamic optimality certificate; residual includes actuator transients",
        "command":"python -m optimization_control.maddpg_wind_farm.reachability --source <mixed-study> --output <new-directory>",
        "artifacts":["metrics.csv","witnesses.json","same_state_target_probe.csv","diagnosis.png"]},indent=2),encoding="utf-8")


def plot_diagnosis(output,rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(12,9))
    for ax,wind in zip(axes.flat,sorted(set(float(r["wind_m_s"]) for r in rows))):
        subset=[r for r in rows if float(r["wind_m_s"])==wind]
        targets=sorted(set(float(r["target_w"]) for r in subset))
        samples=np.array([[float(r["tail_mean_power_w"])/1e6 for r in subset if float(r["target_w"])==t and r["controller"]=="maddpg"] for t in targets])
        x=np.array(targets)/1e6
        ax.plot(x,samples.mean(1),"o-",label="Previous MADDPG mean")
        ax.fill_between(x,samples.min(1),samples.max(1),alpha=.2,label="Three-run range")
        ax.plot(x,[float(next(r["tail_mean_power_w"] for r in subset if float(r["target_w"])==t and r["controller"]=="pi"))/1e6 for t in targets],"s-",label="PI, same actuator")
        ax.plot(x,x,"--",color="gray",label="Target")
        ax.axhline(float(subset[0]["upper_bound_w"])/1e6,color="red",linestyle=":",label="Certified mock upper")
        ax.set(xlabel="Requested farm power [MW]",ylabel="Mean power, last 64 s [MW]",title=f"Constant entrance wind: {wind:g} m/s")
        ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8)
    fig.suptitle("Reachability and target response | development diagnosis, integration mock only")
    fig.tight_layout(); fig.savefig(Path(output)/"diagnosis.png",dpi=150); plt.close(fig)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True); parser.add_argument("--output",required=True)
    args=parser.parse_args(); diagnose(args.source,args.output)
