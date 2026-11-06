"""Correct circular-angle display only; retain all original frozen plot files."""
import argparse
from pathlib import Path


def relative_angle(values, origin):
    import numpy as np
    return (np.unwrap(np.asarray(values,dtype=float))-origin)*180/np.pi


def plot(root):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .anchor_closeout import context, read_csv, write_json, sha
    context(root)
    traces=read_csv(root/"test/trajectories.csv")
    case="test_gust_1_pitch0.025"
    outputs=[]; origins=[]
    for run in range(3):
        reference=[r for r in traces if r["stage"]=="anchor" and r["case_id"]==case and r["controller"]=="initial" and int(r["run_id"])==run]
        origin=float(reference[0]["direction_rad"])
        origins.append(dict(run_id=run,origin_rad=origin))
        fig,axes=plt.subplots(5,1,figsize=(12,13),sharex=True,layout="constrained")
        for label,color in (("initial","#7b8b96"),("selected","#247ba0"),("final","#ce644f"),("pi","#6e994e")):
            rows=[r for r in traces if r["stage"]=="anchor" and r["case_id"]==case and r["controller"]==label and int(r["run_id"])==(-1 if label=="pi" else run)]
            x=[int(r["step"]) for r in rows]
            axes[0].plot(x,[float(r["farm_power_w"])/1e6 for r in rows],label=label,color=color)
            for i,style in zip((1,2,3),("-","--",":")):
                heading=relative_angle([float(r[f"heading_{i}_rad"]) for r in rows],origin)
                axes[1].plot(x,heading,color=color,ls=style,alpha=.85,lw=1)
                for ax,key,factor in ((axes[2],f"gamma_{i}",180/np.pi),(axes[3],f"pitch_{i}",180/np.pi),(axes[4],f"speed_{i}",1)):
                    ax.plot(x,[float(r[key])*factor for r in rows],color=color,ls=style,alpha=.85,lw=1)
        axes[0].axhline(float(rows[0]["target_w"])/1e6,color="black",ls="--",label="target")
        axes[1].plot(x,relative_angle([float(r["direction_rad"]) for r in rows],origin),color="black",label="wind direction")
        for ax,label in zip(axes,("Farm power [MW]","Heading / wind relative\nto initial wind [deg]","Actual misalignment [deg]","Applied pitch [deg]","Applied speed [rad/s]")):
            ax.set_ylabel(label); ax.grid(alpha=.2)
        axes[0].legend(ncol=5);axes[1].legend();axes[-1].set_xlabel("Control step [1 s]")
        fig.suptitle(f"Predeclared gust / stream {run} | turbine 1/2/3 = solid/dashed/dotted | circular heading display")
        for ext in ("png","pdf"):
            output=root/"figures"/f"actual_controls_unwrapped_stream_{run}.{ext}"
            if output.exists():raise ValueError("corrected display already exists; retain it")
            fig.savefig(output,dpi=170);outputs.append(output)
        plt.close(fig)
    write_json(root/"figures/heading_display_fix.json",dict(data_unchanged=True,model_evaluations=0,case_id=case,origins=origins,
        reason="Wrapped wind direction crossed 2pi/0. Unwrap heading and wind, then use one common initial-wind origin per stream.",
        original_plots_preserved=True,trace_sha256=sha(root/"test/trajectories.csv"),code_sha256=sha(__file__),generated={p.name:sha(p) for p in outputs}))
    context(root)
    print("Corrected circular display",len(outputs),flush=True)


if __name__=="__main__":
    import os
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--output",required=True)
    args=ap.parse_args();root=Path(args.output).resolve()
    os.environ.setdefault("MPLCONFIGDIR",str(root/"figures/mpl_cache"))
    plot(root)
