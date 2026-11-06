"""Audits, bounded validation diagnostic and Python plots for speed n1/n8."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import hashlib

from .anchor_closeout import sha,read_json,write_json,read_csv,write_csv,verify_hashes,rollout,recompute,make_env,save_job,load_job
from .speed_nstep_training import context,bank,initial,ARMS,scores


def audit(root):
    import numpy as np
    import torch
    from .verify_anchor import comparable
    from .speed_nstep_algorithm import FrozenSpeedNStepMADDPG
    from .algorithm import MADDPG
    saved,p=context(root);selection=read_json(root/'selection.json');verify_hashes(selection['hashes'])
    assert selection['root_config_sha256']==sha(root/'config.yaml') and len(selection['results'])==6
    checkpoints=[];pairing=[];validation=[];trace=[];parent_scores={}
    for run in range(3):
        parent,_=MADDPG.load(saved['parents'][run]['checkpoint'])
        m,t,_=rollout(saved['base_config'],bank(root,'validation'),agent=parent)
        tags=dict(arm='parent',run_id=run,controller='parent')
        validation.extend(dict(**tags,**r) for r in m);trace.extend(dict(**tags,**r) for r in t)
        parent_scores[run]=scores(m)
        originals=[];metadata=[]
        for arm,n in ARMS.items():
            r=next(r for r in selection['results'] if r['arm']==arm and r['run_id']==run)
            base=initial(saved,arm,run)
            first,im=FrozenSpeedNStepMADDPG.load(r['initial'],expected_n=n)
            for key in ('actors','target_actors','critics','target_critics','speed_heads','target_speed_heads'):
                np.testing.assert_equal(comparable(getattr(base,key).state_dict()),comparable(getattr(first,key).state_dict()))
            for key in ('head_optimizers','critic_optimizers'):
                np.testing.assert_equal(comparable([o.state_dict() for o in getattr(base,key)]),comparable([o.state_dict() for o in getattr(first,key)]))
            originals.append(first);metadata.append(im)
            paths=sorted((root/'formal'/f'{arm}_run_{run}').glob('attempt_*/step_*.pth'))
            assert len(paths)==65
            steps=[]
            for path in paths:
                s=torch.load(path,map_location='cpu',weights_only=False);meta=s['metadata'];step=meta['step'];steps.append(step)
                assert meta['root_config_sha256']==sha(root/'config.yaml') and meta['parent']==saved['parents'][run]
                for key,value in parent.actors.state_dict().items():assert torch.equal(value,s['actors'][key])
                assert s['replay']['insertions']==saved['parents'][run]['cumulative_parent_steps']+step
                expected_updates=0 if step<512 else (step-512)//2+1
                assert s['updates']==parent.updates+expected_updates
                checkpoints.append(dict(arm=arm,run_id=run,step=step,checkpoint=str(path.resolve()),sha256=sha(path),
                    updates=s['updates'],insertions=s['replay']['insertions'],n=n,initial=str(path.resolve())==r['initial'],
                    selected=str(path.resolve())==r['selected'],final=str(path.resolve())==r['final']))
            assert sorted(steps)==list(range(0,8193,128))
            final,fm=FrozenSpeedNStepMADDPG.load(r['final'],expected_n=n)
            d=final.replay.state_dict()['data'];env=saved['base_config']['environment']
            expected=env['reward_scale']*(-d['next_obs'][:,0,9]**2-env['action_change_weight']*np.mean((d['actions']-d['obs'][:,:,5:8])**2,axis=(1,2)))
            np.testing.assert_allclose(d['rewards'],expected[:,None].repeat(3,axis=1),atol=5e-6,rtol=4e-6)
            write_json(root/f'normalization_{arm}.json',fm['normalization'])
            assert scores(im['best']['validation'])[0]==r['initial_mean_w']
            for label,path in (('initial',r['initial']),('selected',r['selected']),('final',r['final'])):
                # Validation trajectories saved at the checkpoint's own attempt; no new policy rollout.
                s=torch.load(path,map_location='cpu',weights_only=False);step=s['metadata']['step']
                rows,ts=load_job(Path(path).parent/f'validation_{step:08d}')
                tags=dict(arm=arm,run_id=run,controller=label)
                validation.extend(dict(**tags,**row) for row in rows);trace.extend(dict(**tags,**row) for row in ts)
            if run==0:
                recoveries=list((root/'formal'/f'{arm}_run_0').glob('attempt_*/recovery.json'));assert len(recoveries)==1
                recovery=read_json(recoveries[0]);assert recovery['step']==2048 and recovery['source_process']!=recovery['new_process']
                assert not recovery['uncommitted_attempts']
            metadata[-1]=fm
        # Common starts/RNG/heads/critics before learning; n only affects replay target fields.
        a,b=originals
        for key in ('actors','target_actors','critics','target_critics','speed_heads','target_speed_heads'):
            np.testing.assert_equal(comparable(getattr(a,key).state_dict()),comparable(getattr(b,key).state_dict()))
        for key in ('rng','torch_rng'):
            sa=torch.load(next(r for r in selection['results'] if r['arm']=='n1' and r['run_id']==run)['initial'],weights_only=False,map_location='cpu')
            sb=torch.load(next(r for r in selection['results'] if r['arm']=='n8' and r['run_id']==run)['initial'],weights_only=False,map_location='cpu')
            np.testing.assert_equal(comparable(sa[key]),comparable(sb[key]))
        for left,right in zip(metadata[0]['episodes'],metadata[1]['episodes']):
            for key in ('episode','step','family','target_w','initial_pitch_rad','wind_sha256','noise_sha256'):assert left[key]==right[key]
        pairing.append(dict(run_id=run,common_initial_exact=True,paired_episode_weather_target_pitch_noise=True,episodes=64))
    common=[]
    for mode in ('fixed','p','pi'):
        m,t,_=rollout(saved['base_config'],bank(root,'validation'),mode=mode)
        tags=dict(arm='common',run_id=-1,controller=mode)
        validation.extend(dict(**tags,**r) for r in m);trace.extend(dict(**tags,**r) for r in t)
    write_csv(root/'validation_metrics.csv',validation);write_csv(root/'validation_trajectories.csv',trace)
    recompute(validation,trace,('arm','run_id','controller','case_id'))
    summary=[]
    for r in selection['results']:
        control=next(x for x in selection['results'] if x['arm']=='n1' and x['run_id']==r['run_id'])
        pm,pw=parent_scores[r['run_id']]
        row={k:r[k] for k in ('arm','run_id','selected_step','initial_mean_w','initial_worst_w','selected_mean_w','selected_worst_w','final_mean_w','final_worst_w','final_over_selected')}
        row.update(parent_mean_w=pm,parent_worst_w=pw,final_over_parent_mean=r['final_mean_w']/pm,
            final_over_parent_worst=r['final_worst_w']/pw,selected_over_parent_mean=r['selected_mean_w']/pm,
            final_over_n1_mean=r['final_mean_w']/control['final_mean_w'],final_over_n1_worst=r['final_worst_w']/control['final_worst_w'],
            selected_over_n1_mean=r['selected_mean_w']/control['selected_mean_w'],selected_learned=r['selected_step']>0,
            stable=r['final_over_selected']<=1.25 and r['final_mean_w']<=1.05*pm and r['final_worst_w']<=1.05*pw
                and r['final_mean_w']<=1.05*control['final_mean_w'] and r['final_worst_w']<=1.05*control['final_worst_w'])
        for label in ('initial','selected','final'):row[label+'_accuracy']=r[label+'_mean_w']<=400000 and r[label+'_worst_w']<=500000
        summary.append(row)
    n8=[r for r in summary if r['arm']=='n8'];n1=[r for r in summary if r['arm']=='n1']
    gain={label:sum(r[label+'_mean_w'] for r in n8)/sum(r[label+'_mean_w'] for r in n1) for label in ('selected','final')}
    passed=all(r['selected_learned'] and r['selected_over_n1_mean']<1 and r['final_over_n1_mean']<1 for r in n8) and max(gain.values())<=.99
    write_csv(root/'checkpoint_manifest.csv',checkpoints);write_csv(root/'metrics.csv',summary)
    write_json(root/'core_verification.json',dict(selection_sha256=sha(root/'selection.json'),formal_steps=49152,checkpoints=len(checkpoints),
        pairing=pairing,retained_final_transitions=6*32768,episode_saves_per_job=65,run0_new_process_restart=True,
        declared_n8_gain_passed=passed,n8_over_n1_ratios=gain,n8_stable_streams=sum(r['stable'] for r in n8)))
    if (root/'test/complete.json').exists():audit_test(root,saved)
    write_json(root/'summary.txt',dict(status='test_audited' if (root/'test/complete.json').exists() else 'core_audited',seed=42,
        formal_training_steps=49152,extra_smoke_steps=0,n8_gain_passed=passed,n8_stable_streams=sum(r['stable'] for r in n8),
        n8_over_n1_ratios=gain,source_hashes_verified=True,test_released=(root/'test/complete.json').exists()))
    print('Core audit',len(checkpoints),'checkpoints; gain passed',passed,'stable',sum(r['stable'] for r in n8),flush=True)


def audit_test(root,saved):
    import numpy as np
    rows=read_csv(root/'test/metrics.csv');traces=read_csv(root/'test/trajectories.csv')
    check=recompute(rows,traces,('arm','run_id','controller','case_id'));assert check['metric_rows']==720
    groups=defaultdict(list)
    for r in traces:groups[(r['arm'],int(r['run_id']),r['controller'],r['case_id'])].append(r)
    numeric=[k for k in traces[0] if k not in ('arm','controller','case_id','split','family')]
    zero_rows=0
    for (arm,run,label,case),part in groups.items():
        if label.startswith('zero_'):
            parent=groups[('parent',run,'parent',case)]
            fields=[k for k in numeric if k!='run_id']
            np.testing.assert_array_equal([[float(r[k]) for k in fields] for r in part],[[float(r[k]) for k in fields] for r in parent])
            zero_rows+=len(part)
    aggregate=[]
    for arm,label in sorted({(r['arm'],r['controller']) for r in rows}):
        for subset,families in [('routine',('stationary','ramp','gust')),('known_stress',('low_wind_stress',))]:
            group=[r for r in rows if r['arm']==arm and r['controller']==label and r['family'] in families]
            means=[np.mean([float(r['rmse_w']) for r in group if int(r['run_id'])==run]) for run in sorted({int(r['run_id']) for r in group})]
            aggregate.append(dict(arm=arm,controller=label,subset=subset,mean_rmse_w=float(np.mean(means)),
                sd_w=float(np.std(means,ddof=1)) if len(means)>1 else 0.,worst_case_w=max(float(r['rmse_w']) for r in group)))
    write_csv(root/'test/aggregate.csv',aggregate)
    write_json(root/'test/delivery_verification.json',dict(**check,zero_speed_rows_exact=zero_rows,all_cases_retained=True))


def diagnostic(root):
    """Exactly one public validation anchor and three actions per stream, max480 steps."""
    import numpy as np
    import torch
    from .algorithm import MADDPG
    from .speed_nstep_algorithm import FrozenSpeedNStepMADDPG
    saved,p=context(root);selection=read_json(root/'selection.json')
    if (root/'direction.json').exists():raise ValueError('bounded diagnostic already completed')
    case,wind=next((c,w) for c,w in bank(root,'validation') if c['family']=='ramp' and c['target_w']==3450000.)
    records=[];steps=0
    for run in range(3):
        parent,_=MADDPG.load(saved['parents'][run]['checkpoint']);env=make_env(saved['base_config'])
        env.initial=np.asarray(saved['base_config']['environment']['initial_operating_point'],float).copy();env.initial[1]=case['initial_pitch_rad']
        opts=dict(wind_trajectory=wind.values,target_w=case['target_w'])
        # Recreate each branch from the same prefix via deepcopy of the environment state.
        obs,_=env.reset(seed=42,options=opts)
        for _ in range(64):obs,_,_,_,_=env.step(parent.act(obs));steps+=1
        start=deepcopy({k:v for k,v in env.__dict__.items() if k!='plant'});initial_obs=obs.copy()
        branches=[]
        for offset in (-.05,0.,.05):
            env.__dict__.update(deepcopy(start));obs=initial_obs.copy();act=parent.act(obs);act[:,2]=np.clip(act[:,2]+2*offset/.667,-1,1)
            qinput=torch.tensor(np.r_[obs.flatten(),act.flatten()][None],dtype=torch.float32)
            tracking=penalty=total=0.
            for k in range(32):
                command=act if k==0 else parent.act(obs);previous=obs.copy()
                obs,reward,done,_,info=env.step(command);steps+=1
                tr=-100*float(obs[0,9])**2
                pe=-100*.001*float(np.mean((command-previous[:,5:8])**2))
                tracking+=(.99**k)*tr;penalty+=(.99**k)*pe;total+=(.99**k)*float(reward[0])
            branches.append(dict(offset_rad_s=offset,G32=total,tracking_G32=tracking,penalty_G32=penalty,qinput=qinput))
        for r in [r for r in selection['results'] if r['run_id']==run]:
            for label in ('initial','selected','final'):
                agent,_=FrozenSpeedNStepMADDPG.load(r[label],expected_n=ARMS[r['arm']])
                for branch in branches:
                    with torch.no_grad():q=[float(c(branch['qinput'])) for c in agent.critics]
                    records.append(dict(arm=r['arm'],run_id=run,controller=label,case_id=case['id'],anchor=64,
                        **{k:v for k,v in branch.items() if k!='qinput'},q1=q[0],q2=q[1],q3=q[2],q_mean=float(np.mean(q))))
    assert steps==480 and len(records)==54
    write_csv(root/'direction.csv',records)
    write_json(root/'direction.json',dict(environment_steps=steps,rows=len(records),selection_sha256=sha(root/'selection.json'),
        fixed_parent_continuation=True,finite_return_not_true_long_term_Q=True,no_candidate_selection=True))


def figures(root):
    import os
    import numpy as np
    os.environ.setdefault('MPLCONFIGDIR',str(root/'plot_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .anchor_heading_figures import relative_angle
    context(root);out=root/'figures';out.mkdir(exist_ok=False);files={}
    def save(fig,name):
        for ext in ('png','pdf'):
            path=out/f'{name}.{ext}';fig.savefig(path,dpi=150);files[path.name]=sha(path)
        plt.close(fig)
    history=read_csv(root/'history.csv');colors={'n1':'#c66a42','n8':'#237ca4'}
    fig,axes=plt.subplots(1,3,figsize=(14,4.5),layout='constrained',sharey=True)
    for run,ax in enumerate(axes):
        for arm in ARMS:
            part=[r for r in history if r['arm']==arm and int(r['run_id'])==run]
            x=[int(r['step']) for r in part];y=[float(r['mean_rmse_w'])/1000 for r in part]
            ax.plot(x,y,'o-',label=arm,color=colors[arm]);best=int(np.argmin(y));ax.scatter(x[best],y[best],marker='*',s=140,color=colors[arm],edgecolor='black')
        ax.axhline(400,color='gray',ls=':');ax.set(title=f'stream {run}',xlabel='Additional training steps');ax.grid(alpha=.2)
    axes[0].set_ylabel('Validation mean RMSE [kW]');axes[0].legend()
    fig.suptitle('Same frozen parents + speed heads | only Critic target n1 / n8 differs | synthetic surrogate')
    save(fig,'validation_stability')
    aggregates=read_csv(root/'test/aggregate.csv');fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for ax,subset in zip(axes,('routine','known_stress')):
        for arm in ARMS:
            rows=[next(r for r in aggregates if r['arm']==arm and r['controller']==label and r['subset']==subset) for label in ('initial','selected','final')]
            ax.errorbar(range(3),[float(r['mean_rmse_w'])/1000 for r in rows],yerr=[float(r['sd_w'])/1000 for r in rows],fmt='o-',capsize=4,color=colors[arm],label=arm)
        for arm,label,color in [('parent','parent','#899096'),('common','p','#8f843b'),('common','pi','#8262a1')]:
            row=next(r for r in aggregates if r['arm']==arm and r['controller']==label and r['subset']==subset)
            ax.axhline(float(row['mean_rmse_w'])/1000,label=label,color=color,ls='--')
        ax.set(xticks=range(3),xticklabels=['initial','selected','final'],ylabel='Case mean RMSE [kW]',title=subset);ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Fresh routine test / known pressure regression | SD across 3 derived streams, not confidence intervals')
    save(fig,'test_comparison')
    traces=read_csv(root/'test/trajectories.csv');case='test_gust_1_pitch0.025'
    fig,axes=plt.subplots(5,3,figsize=(16,13),layout='constrained',sharex=True)
    for run in range(3):
        for arm,label,color in [('parent','parent','#899096'),('n1','final',colors['n1']),('n8','selected',colors['n8']),('n8','final','#91319c')]:
            part=[r for r in traces if r['arm']==arm and int(r['run_id'])==run and r['controller']==label and r['case_id']==case]
            x=[int(r['step']) for r in part];origin=float(part[0]['direction_rad'])
            axes[0,run].plot(x,[float(r['farm_power_w'])/1e6 for r in part],color=color,label=f'{arm} {label}')
            for i,ls in zip((1,2,3),('-','--',':')):
                axes[1,run].plot(x,relative_angle([float(r[f'heading_{i}_rad']) for r in part],origin),ls=ls,color=color,lw=.9)
                for ax,key,factor in [(axes[2,run],f'gamma_{i}',180/np.pi),(axes[3,run],f'pitch_{i}',180/np.pi),(axes[4,run],f'speed_{i}',1)]:
                    ax.plot(x,[float(r[key])*factor for r in part],ls=ls,color=color,lw=.9)
        axes[0,run].axhline(float(part[0]['target_w'])/1e6,color='black',ls='--');axes[0,run].set_title(f'stream {run}');axes[0,run].legend(fontsize=7)
        axes[4,run].set_xlabel('Step [1 s]')
    for i,label in enumerate(('Farm power [MW]','Heading [deg]\nrelative to initial wind','Misalignment [deg]','Applied pitch [deg]','Applied speed [rad/s]')):
        axes[i,0].set_ylabel(label)
        for ax in axes[i]:ax.grid(alpha=.2)
    fig.suptitle('Predeclared gust case | turbine 1/2/3 solid/dashed/dotted | frozen pitch mapping, no yaw learning')
    save(fig,'actual_controls')
    write_json(out/'manifest.json',dict(python_matplotlib=True,generated=files))
