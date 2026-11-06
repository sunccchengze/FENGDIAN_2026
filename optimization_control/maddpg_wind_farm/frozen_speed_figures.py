"""Python figures from frozen v4 study CSV only."""
import os
from pathlib import Path


def figures(root):
    import numpy as np
    os.environ.setdefault('MPLCONFIGDIR',str(root/'figures/mpl_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .frozen_speed_training import context
    from .anchor_closeout import read_csv,write_json,sha
    from .anchor_heading_figures import relative_angle
    context(root);out=root/'figures';out.mkdir(exist_ok=False)
    history=read_csv(root/'history.csv');aggregates=read_csv(root/'test/aggregate.csv');generated=[]
    colors={'baseline':'#ca694d','speed':'#247ba0'}
    def save(fig,name):
        for ext in ('png','pdf'):
            p=out/f'{name}.{ext}';fig.savefig(p,dpi=170);generated.append(p)
        plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(15,4.5),sharey=True,layout='constrained')
    for run,ax in enumerate(axes):
        for arm in ('baseline','speed'):
            rows=[r for r in history if r['arm']==arm and int(r['run_id'])==run]
            x=[int(r['step']) for r in rows];y=[float(r['mean_rmse_w'])/1000 for r in rows]
            ax.plot(x,y,'o-',label=arm,color=colors[arm]);best=int(np.argmin(y));ax.scatter([x[best]],[y[best]],s=130,marker='*',color=colors[arm],edgecolor='black')
        ax.axhline(400,ls=':',color='gray');ax.set(title=f'stream {run}',xlabel='Additional formal steps');ax.grid(alpha=.2)
    axes[0].set_ylabel('Validation mean RMSE [kW]');axes[0].legend()
    fig.suptitle('Frozen parent mapping + speed head | 400 kW is mean accuracy only | synthetic PINN')
    save(fig,'paired_validation')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    labels=('initial','selected','final')
    for ax,subset in zip(axes,('routine','known_stress')):
        for arm,shift in (('baseline',-.07),('speed',.07)):
            rows=[next(r for r in aggregates if r['arm']==arm and r['controller']==label and r['subset']==subset) for label in labels]
            ax.errorbar(np.arange(3)+shift,[float(r['mean_rmse_w'])/1000 for r in rows],yerr=[float(r['sd_w'])/1000 for r in rows],fmt='o-',capsize=4,label=arm,color=colors[arm])
        for mode,color in (('p','#8a8b46'),('pi','#7668a0')):
            r=next(r for r in aggregates if r['arm']=='common' and r['controller']==mode and r['subset']==subset)
            ax.axhline(float(r['mean_rmse_w'])/1000,label=mode,color=color,ls='--')
        ax.set(xticks=np.arange(3),xticklabels=labels,ylabel='Mean case RMSE [kW]',title='New routine test' if subset=='routine' else 'Known low-wind regression');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Identical mode / cases / actuators | SD across 3 derived streams, not a confidence interval')
    save(fig,'paired_test')
    traces=read_csv(root/'test/trajectories.csv');case='test_gust_1_pitch0.025'
    for run in range(3):
        fig,axes=plt.subplots(5,1,figsize=(12,13),sharex=True,layout='constrained')
        reference=[r for r in traces if r['arm']=='speed' and int(r['run_id'])==run and r['controller']=='parent' and r['case_id']==case]
        origin=float(reference[0]['direction_rad'])
        for arm,label,color in (('speed','parent','#7c8b96'),('speed','selected','#247ba0'),('speed','final','#ca694d'),('common','pi','#68994e')):
            rows=[r for r in traces if r['arm']==arm and int(r['run_id'])==(-1 if arm=='common' else run) and r['controller']==label and r['case_id']==case]
            x=[int(r['step']) for r in rows];axes[0].plot(x,[float(r['farm_power_w'])/1e6 for r in rows],color=color,label=label)
            for i,style in zip((1,2,3),('-','--',':')):
                axes[1].plot(x,relative_angle([float(r[f'heading_{i}_rad']) for r in rows],origin),color=color,ls=style,lw=1)
                for ax,key,factor in ((axes[2],f'gamma_{i}',180/np.pi),(axes[3],f'pitch_{i}',180/np.pi),(axes[4],f'speed_{i}',1)):
                    ax.plot(x,[float(r[key])*factor for r in rows],color=color,ls=style,lw=1)
        axes[0].axhline(float(rows[0]['target_w'])/1e6,color='black',ls='--',label='target')
        axes[1].plot(x,relative_angle([float(r['direction_rad']) for r in rows],origin),color='black',label='wind')
        for ax,label in zip(axes,('Farm power [MW]','Heading relative to\nfirst plotted wind [deg]','Misalignment [deg]','Applied pitch [deg]','Applied speed [rad/s]')):ax.set_ylabel(label);ax.grid(alpha=.2)
        axes[0].legend(ncol=5);axes[1].legend();axes[-1].set_xlabel('Step [1 s]')
        fig.suptitle(f'Fixed gust case / stream {run} | turbine 1/2/3 = solid/dashed/dotted | no yaw learning')
        save(fig,f'actual_controls_{run}')
    write_json(out/'manifest.json',dict(generated={p.name:sha(p) for p in generated},python_matplotlib=True,model_evaluations=0))
    context(root);print('Figures complete',len(generated),flush=True)
