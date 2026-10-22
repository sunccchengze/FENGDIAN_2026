"""Physical 12-input bridge for the team's fixed-condition 9-control readout."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

CONTROL_ORDER=tuple(f"{n}{i}" for i in (1,2,3) for n in ("yaw","pitch","rotor_speed"))
OUTPUT_ORDER=("P1","P2","P3","Ueff1","Ueff2","Ueff3")
INTERLEAVE=(3,6,9,4,7,10,5,8,11)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def unit_factors(units):
    if units.get("yaw") not in ("rad","deg") or units.get("pitch") not in ("rad","deg") or units.get("rotor_speed") not in ("rad/s","rpm"):
        raise ValueError("explicit yaw/pitch rad or deg and speed rad/s or rpm required")
    return np.tile([180/np.pi if units["yaw"]=="deg" else 1,
                    180/np.pi if units["pitch"]=="deg" else 1,
                    30/np.pi if units["rotor_speed"]=="rpm" else 1],3)


def validate_positions(value):
    p=np.asarray(value,dtype=float)
    if p.shape!=(3,3) or not np.all(np.isfinite(p)) or np.any(p[:,2]<=0):
        raise ValueError("three finite actual turbine [x,y,z] positions with positive hub height required")
    delta=np.diff(p,axis=0)
    if not np.allclose(delta[0],delta[1],atol=1e-5,rtol=1e-6) or delta[0,0]<=0 or not np.allclose(delta[:,1:],0,atol=1e-5):
        raise ValueError("this bridge requires three equally spaced turbines ordered along model +x, equal y/hub height")
    return p.astype(np.float32)


def validate_run(run_dir,backend):
    run=Path(run_dir)
    missing=[n for n in ("trained.keras","config_used.json","training_report.json") if not (run/n).is_file()]
    if missing: raise ValueError("trained delivery incomplete: "+", ".join(missing)+"; untrained.keras is not accepted")
    cfg=read_json(run/"config_used.json"); report=read_json(run/"training_report.json")
    if report.get("status")!="trained_supervised_transfer_requires_accuracy_review" or report.get("epochs_completed",0)<=0:
        raise ValueError("completed real-label training report required")
    if report.get("control_order")!=list(CONTROL_ORDER) or report.get("output_order")!=list(OUTPUT_ORDER) or report.get("output_units")!=["W"]*3+["m/s"]*3:
        raise ValueError("control/output order or units disagree with team contract")
    if report.get("config")!=cfg: raise ValueError("training report and saved run config disagree")
    if report.get("constant_controls_in_training")!=[]:
        raise ValueError("all nine controls must vary for the full three-channel task")
    if report.get("negative_test_output_count")!=0 or report.get("original_parameters_unchanged") is not True:
        raise ValueError("negative test outputs or missing retained-weight verification")
    positions=validate_positions(cfg.get("turbine_positions_m")); factors=unit_factors(cfg.get("control_units",{}))
    lo=np.asarray(report.get("training_control_min"),dtype=float); hi=np.asarray(report.get("training_control_max"),dtype=float)
    if lo.shape!=(9,) or hi.shape!=(9,) or not np.all(np.isfinite([lo,hi])) or np.any(lo>=hi):
        raise ValueError("nine varying finite training control ranges required")
    limits=np.asarray(backend.get("max_test_rmse"),dtype=float)
    if limits.shape!=(6,) or not np.all(np.isfinite(limits)) or np.any(limits<=0):
        raise ValueError("six explicitly reviewed test RMSE limits in W and m/s required")
    for i,n in enumerate(OUTPUT_ORDER):
        m=report.get("test_metrics",{}).get(n,{})
        value=m.get("RMSE")
        if m.get("unit")!=("W" if i<3 else "m/s") or not isinstance(value,(float,int)) or not np.isfinite(value) or value<0 or value>limits[i]:
            raise ValueError("test error missing or outside reviewed limit: "+n)
    fixed=backend.get("fixed_condition",{})
    ambient=np.asarray([cfg.get("fixed_inlet_wind_speed_m_s"),fixed.get("direction_rad"),fixed.get("turbulence_intensity")],dtype=float)
    if not np.all(np.isfinite(ambient)) or ambient[0]<=0 or not 0<=ambient[1]<=2*np.pi or not 0<=ambient[2]<=.3:
        raise ValueError("confirmed fixed speed, direction and background TI required")
    if backend.get("yaw_convention")!="misalignment_same_sign_as_gamma":
        raise ValueError("team yaw must be confirmed as same-sign misalignment, not nacelle heading")
    return cfg,report,positions,factors,lo,hi,ambient


class FixedConditionPredictor:
    """Model owns normalization; receives raw team-unit controls plus positions."""
    expects_physical_default_inputs=True
    def __init__(self,model,positions,factors,lo,hi,ambient):
        self.model,self.positions,self.factors=model,positions,factors
        self.lo,self.hi,self.ambient=np.asarray(lo),np.asarray(hi),np.asarray(ambient)

    def __call__(self,x):
        x=np.asarray(x,dtype=float)
        if x.ndim!=2 or x.shape[1]!=12 or not np.all(np.isfinite(x)) or len(x)==0:
            raise ValueError("physical [B,12] default feature order required")
        difference=x[:,:3]-self.ambient
        difference[:,1]=np.arctan2(np.sin(difference[:,1]),np.cos(difference[:,1]))
        if np.any(np.abs(difference)>np.array([1e-5,1e-6,1e-6])):
            raise ValueError("fixed-condition PINN cannot evaluate varying inlet speed, direction or TI")
        controls=x[:,INTERLEAVE]*self.factors
        tolerance=1e-6*np.maximum(1,np.maximum(np.abs(self.lo),np.abs(self.hi)))
        if np.any(controls<self.lo-tolerance) or np.any(controls>self.hi+tolerance):
            raise ValueError("applied controls outside trained ranges; no clipping/extrapolation")
        inputs={"controls":controls.astype(np.float32),"turbine_positions":np.broadcast_to(self.positions,(len(x),3,3)).copy()}
        value=self.model(inputs,training=False)
        y=np.asarray(value.numpy() if hasattr(value,"numpy") else value,dtype=np.float32)
        if y.shape!=(len(x),6) or not np.all(np.isfinite(y)) or np.any(y[:,:3]<0) or np.any(y[:,3:]<=0):
            raise ValueError("invalid physical six-output prediction")
        return y


def _resolve_repo_path(raw):
    """Resolve config paths that historical configs wrote relative to a repo-root
    ``pinn/<version>/`` tree. That tree was never committed; the delivery lives
    under ``materials/厉今飞/20261021_PINN十二输入交付/<version>/`` (see pinn/README.md).
    Missing paths are returned resolved as-is so existing validation reports them.
    """
    p = Path(raw)
    if p.exists():
        return p.resolve()
    for parent in Path(__file__).resolve().parents:
        if not (parent / "optimization_control").is_dir():
            continue
        cand = parent / p
        if cand.exists():
            return cand.resolve()
        if len(p.parts) >= 2 and p.parts[0] == "pinn":
            cand = parent / "materials" / "厉今飞" / "20261021_PINN十二输入交付" / Path(*p.parts[1:])
            if cand.exists():
                return cand.resolve()
        break
    return p.resolve()


def create_predictor(backend):
    """Factory for existing workflow; reject incomplete handover before loading TF."""
    run=_resolve_repo_path(backend["run_dir"])
    cfg,report,p,f,lo,hi,ambient=validate_run(run,backend)
    script=_resolve_repo_path(backend["script"])
    if not script.is_file(): raise ValueError("team custom-layer module is missing")
    name="_wind_team_pinn_io_"+hashlib.sha256(str(script).encode()).hexdigest()[:12]
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,script)
        module=importlib.util.module_from_spec(spec); sys.modules[name]=module
        try: spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name,None)
            raise
    module=sys.modules[name]
    _,keras,*_=module.tensorflow_components()
    model=keras.models.load_model(str(run/"trained.keras"),compile=False,safe_mode=True)
    if module.retained_digest(model)!=report.get("retained_original_sha256"):
        raise ValueError("loaded retained backbone does not match training report")
    predictor=FixedConditionPredictor(model,p,f,lo,hi,ambient)
    predictor.spacing_m=float(p[1,0]-p[0,0])
    predictor.model_sha256=hashlib.sha256((run/"trained.keras").read_bytes()).hexdigest()
    return predictor


def validate_demo_run(run_dir,backend):
    """Synthetic demo has explicit provenance; no physical-accuracy admission."""
    run=Path(run_dir)
    if backend.get("allow_synthetic_demo") is not True:
        raise ValueError("synthetic demo requires explicit allow_synthetic_demo=true")
    cfg=read_json(run/"config_used.json"); report=read_json(run/"training_report.json")
    if report.get("status")!="synthetic_fixed_condition_demo" or report.get("physical_validation") is not False or report.get("label_source")!="coupled_integration_mock":
        raise ValueError("explicit synthetic fixed-condition provenance required")
    if report.get("config")!=cfg or report.get("epochs_completed",0)<=0 or report.get("original_parameters_unchanged") is not True:
        raise ValueError("completed synthetic training and frozen-backbone verification required")
    if report.get("control_order")!=list(CONTROL_ORDER) or report.get("output_order")!=list(OUTPUT_ORDER) or report.get("output_units")!=["W"]*3+["m/s"]*3:
        raise ValueError("synthetic control/output contract mismatch")
    if report.get("negative_test_output_count")!=0 or report.get("constant_controls_in_training")!=[]:
        raise ValueError("nonnegative test outputs and all nine varying controls required")
    positions=validate_positions(cfg.get("turbine_positions_m")); factors=unit_factors(cfg.get("control_units",{}))
    lo=np.asarray(report.get("training_control_min"),dtype=float); hi=np.asarray(report.get("training_control_max"),dtype=float)
    if lo.shape!=(9,) or hi.shape!=(9,) or not np.all(np.isfinite([lo,hi])) or np.any(lo>=hi):
        raise ValueError("finite synthetic nine-control domain required")
    fixed=report["fixed_condition"]
    ambient=np.array([fixed["speed_m_s"],fixed["direction_rad"],fixed["turbulence_intensity"]])
    requested=backend.get("fixed_condition",{})
    if not np.all(np.isfinite(ambient)) or ambient[0]<=0 or not 0<=ambient[1]<2*np.pi or not 0<=ambient[2]<=.3 or cfg["fixed_inlet_wind_speed_m_s"]!=ambient[0]:
        raise ValueError("invalid fixed synthetic wind")
    if requested!=dict(direction_rad=fixed["direction_rad"],turbulence_intensity=fixed["turbulence_intensity"]):
        raise ValueError("requested demo wind differs from model training condition")
    if backend.get("yaw_convention")!="misalignment_same_sign_as_gamma":
        raise ValueError("explicit same-sign yaw misalignment required")
    return cfg,report,positions,factors,lo,hi,ambient


def create_demo_predictor(backend):
    from ..maddpg_wind_farm.fixed_pinn_demo import load_team_module, resolve_team_path
    run=Path(backend["run_dir"]).resolve()
    cfg,report,p,f,lo,hi,ambient=validate_demo_run(run,backend)
    script=resolve_team_path(backend["script"]).resolve()
    if hashlib.sha256(script.read_bytes()).hexdigest()!=report.get("team_script_sha256"):
        raise ValueError("team loading script differs from training provenance")
    module=load_team_module(script)
    tf,keras,*_=module.tensorflow_components()
    model=keras.models.load_model(str(run/"trained.keras"),compile=False,safe_mode=True)
    if module.retained_digest(model)!=report.get("retained_original_sha256") or module.trainable_count(model)!=24306:
        raise ValueError("demo retained backbone or trainable parameter set mismatch")
    @tf.function(input_signature=[{"controls":tf.TensorSpec([None,9],tf.float32),"turbine_positions":tf.TensorSpec([None,3,3],tf.float32)}])
    def inference(inputs):
        return model(inputs,training=False)
    predictor=FixedConditionPredictor(lambda inputs,training:inference(inputs),p,f,lo,hi,ambient)
    predictor.spacing_m=float(p[1,0]-p[0,0])
    predictor.model_sha256=hashlib.sha256((run/"trained.keras").read_bytes()).hexdigest()
    return predictor
