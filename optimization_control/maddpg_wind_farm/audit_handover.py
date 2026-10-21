"""Read-only team PINN handover audit; does not run or train delivered code."""
import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import zipfile
import numpy as np
from .workflow import fresh_output,write_csv
from ..environments.teammate_pinn_backend import validate_positions,CONTROL_ORDER,OUTPUT_ORDER


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_keras(path):
    import h5py
    with zipfile.ZipFile(path) as z:
        config=json.loads(z.read("config.json"))
        controls=[]; statistics=[]
        with h5py.File(io.BytesIO(z.read("model.weights.h5")),"r") as h:
            def visit(name,item):
                if isinstance(item,h5py.Dataset) and (item.shape==(9,700) or "frozen_standardization" in name):
                    a=np.asarray(item)
                    row=dict(path=name,shape=list(a.shape),nonzero=int(np.count_nonzero(a)),minimum=float(a.min()),maximum=float(a.max()))
                    (controls if item.shape==(9,700) else statistics).append(row)
            h.visititems(visit)
    return dict(input_layers=config["config"]["input_layers"],output_layers=config["config"]["output_layers"],
        control_kernels=controls,statistics=statistics,all_control_connections_zero=bool(controls) and all(r["nonzero"]==0 for r in controls))


def audit(package,output):
    package=Path(package).resolve(); output_change=package/"OutputChange"
    cfg_path=output_change/"project_config.json"; build_path=output_change/"iochanged_9ms/build_report.json"
    cfg=json.loads(cfg_path.read_text(encoding="utf-8-sig")); build=json.loads(build_path.read_text(encoding="utf-8-sig"))
    models=sorted(output_change.rglob("*.keras")); training_reports=sorted(output_change.rglob("training_report.json"))
    untrained=output_change/"iochanged_9ms/untrained.keras"
    evidence=inspect_keras(untrained)
    template=untrained.parent/"training_data_template.csv"
    with template.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.reader(f)); labelled_rows=len(rows)-1
    try: validate_positions(cfg.get("turbine_positions_m")); positions_ready=True
    except (ValueError,TypeError): positions_ready=False
    checks=[dict(check="trained_model_present",passed=any(p.name=="trained.keras" for p in models),detail="requires trained.keras, not original_frozen.keras/untrained.keras"),
        dict(check="training_report_present",passed=bool(training_reports),detail="independent physical-label errors and control ranges required"),
        dict(check="real_geometry_filled",passed=positions_ready,detail="three actual ordered equally spaced positions; do not use structural test coordinates"),
        dict(check="source_reports_real_training",passed=build.get("training_performed_on_real_data") is True,detail=str(build.get("status"))),
        dict(check="controls_have_nonzero_saved_connections",passed=not evidence["all_control_connections_zero"],detail="saved 9x700 new control kernel inspected directly"),
        dict(check="labelled_training_template",passed=labelled_rows>0,detail=f"template contains {labelled_rows} labelled rows; original flow CSVs are not control/power labels"),
        dict(check="six_output_order",passed=build.get("output_order")==list(OUTPUT_ORDER),detail="W,W,W,m/s,m/s,m/s"),
        dict(check="nine_control_order",passed=build.get("control_order")==list(CONTROL_ORDER),detail="interleaved by turbine, unlike optimization grouped controls"),
        dict(check="random_inflow_supported",passed=False,detail="documented fixed-condition nine-input model; no inlet speed/direction/TI features")]
    versions={}
    for name in ("tensorflow","tf-keras","h5py"):
        try: versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: versions[name]=None
    hashed=[cfg_path,build_path,template,*models,package/"modify_pinn_io.py",package/"prepare_pinn_outputchange.py"]
    hashes={str(p):digest(p) for p in hashed}
    out=fresh_output(output,dict(seed=42,purpose="handover_admission_audit_not_model_performance",package=str(package),source_hashes=hashes))
    write_csv(out/"metrics.csv",checks)
    summary=dict(status="blocked_untrained_delivery",ready_for_maddpg=False,checks=checks,model_inspection=evidence,
        model_files=[str(p.relative_to(package)) for p in models],training_reports=[str(p.relative_to(package)) for p in training_reports],
        runtime_versions=versions,source_files_unchanged=all(digest(p)==h for p,h in hashes.items()),
        future_scope="fixed-condition supervised transfer using frozen coordinate-to-flow backbone; needs physical labels and independent validation",
        new_training_steps=0,command="python -m optimization_control.maddpg_wind_farm.audit_handover --package <delivery-root> --output <new-directory>")
    (out/"summary.txt").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package",required=True); parser.add_argument("--output",required=True)
    args=parser.parse_args(); audit(args.package,args.output)
