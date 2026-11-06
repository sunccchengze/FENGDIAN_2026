"""Compare already sampled local responses with their synthetic label source.

Postprocessing only: no new points, PINN calls, environment steps, training or test.
The synthetic formula is a software reference, never physical ground truth.
"""
import argparse
from pathlib import Path


def run(root, output_name="local_response_reference_runtime216"):
    import numpy as np
    from .anchor_closeout import context, read_csv, read_json, write_json, write_csv, sha
    from .wind_pinn_demo import synthetic_labels
    cfg,_,_,_=context(root)
    states={}
    for path in (root/"diagnostic").glob("*/local_states.json"):
        arm,run_id,endpoint=path.parent.name.split("_",2)
        for row in read_json(path):states[(arm,run_id,endpoint,row["case_id"],int(row["step"]))]=row
    rows=read_csv(root/"diagnostic/local_response.csv")
    inputs=[]
    for row in rows:
        state=states[(row["stage"],str(row["run_id"]),row["endpoint"],row["case_id"],int(row["step"]))]
        base=np.asarray(state["physical"],float); changed=base.copy()
        channel=0 if row["channel"]=="yaw" else 2
        indices=[3+channel*3+i for i in (range(3) if row["turbine"]=="all" else [int(row["turbine"])-1])]
        offset=float(row["offset"])*(np.pi/180 if channel==0 else 1.)
        changed[indices]=np.clip(changed[indices]+offset,*((-.4,.4) if channel==0 else (.6,1.267)))
        inputs.extend((base,changed))
    labels=synthetic_labels(np.asarray(inputs),[[0,0,90],[378,0,90],[756,0,90]])[:,:3].reshape(-1,2,3)
    output=[]
    for row,pair in zip(rows,labels):
        ref_delta=float((pair[1]-pair[0]).sum()); model_delta=float(row["farm_delta_w"])
        output.append(dict(**{k:row[k] for k in ("stage","run_id","endpoint","case_id","step","channel","turbine","offset","offset_unit")},
            model_farm_delta_w=model_delta,synthetic_reference_farm_delta_w=ref_delta,response_error_w=model_delta-ref_delta,
            model_tracking_absolute_error_change_w=float(row["tracking_absolute_error_change_w"]),
            reference_tracking_absolute_error_change_w=float(abs(pair[1].sum()-float(row["target_w"]))-abs(pair[0].sum()-float(row["target_w"])))))
    summary=[]
    for channel in ("speed","yaw"):
        for turbine in ("all","individual"):
            part=[r for r in output if r["channel"]==channel and ((r["turbine"]=="all")== (turbine=="all")) and float(r["offset"])!=0]
            model=np.array([r["model_farm_delta_w"] for r in part]); ref=np.array([r["synthetic_reference_farm_delta_w"] for r in part])
            mask=np.abs(ref)>=1000
            summary.append(dict(channel=channel,turbine=turbine,rows=len(part),median_abs_model_response_w=float(np.median(np.abs(model))),
                median_abs_reference_response_w=float(np.median(np.abs(ref))),median_absolute_response_error_w=float(np.median(np.abs(model-ref))),
                reference_response_at_least_1kw_rows=int(mask.sum()),sign_mismatch_fraction_for_reference_at_least_1kw=float(np.mean(np.sign(model[mask])!=np.sign(ref[mask]))) if mask.any() else None))
    if Path(output_name).name!=output_name:
        raise ValueError("output name must be one directory component")
    out=root/"audit"/output_name
    out.mkdir(exist_ok=False)
    write_csv(out/"metrics.csv",output)
    write_json(out/"summary.json",dict(seed=42,physical_validation=False,test_read=False,new_model_calls=0,new_environment_steps=0,
        additional_formal_training_steps=0,label_source="geometry_wind_controls_synthetic_test_v1_not_physical_truth",summary=summary,
        input_sha256=sha(root/"diagnostic/local_response.csv"),label_code_sha256=sha(Path(__file__).with_name("wind_pinn_demo.py")),code_sha256=sha(__file__),numpy_version=np.__version__))
    context(root)
    print(summary,flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--output",required=True)
    ap.add_argument("--origin",default=".")
    ap.add_argument("--output-name",default="local_response_reference_runtime216")
    args=ap.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path(args.origin)/".venv/pinn_tf216")
    run(Path(args.output).resolve(),args.output_name)
