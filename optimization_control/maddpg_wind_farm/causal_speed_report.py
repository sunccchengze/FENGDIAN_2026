"""Saved-data metrics, audit and Python figures for causal speed search."""
from pathlib import Path
from .anchor_closeout import read_json,write_json,read_csv,write_csv,sha,verify_hashes


def metric(rows,case,cfg,plans,spent):
    import numpy as np
    errors=np.asarray([float(r['error_w']) for r in rows]);e=cfg['environment']
    commands=np.asarray([[[float(r[f'command_{i}_{j}']) for j in range(3)] for i in (1,2,3)] for r in rows])
    initial=np.tile([0.,case['initial_pitch_rad'],e['initial_operating_point'][2]],(3,1))
    initial_command=(2*(initial-e['action_low'])/(np.asarray(e['action_high'])-e['action_low'])-1).astype(np.float32)
    previous=np.concatenate((initial_command[None],commands[:-1]));changes=np.mean((commands-previous)**2,axis=(1,2))
    physical=np.asarray([[[float(r[f'heading_{i}_rad']),float(r[f'pitch_{i}']),float(r[f'speed_{i}'])] for i in (1,2,3)] for r in rows])
    initial[:,0]=case['initial_wind_direction_rad']+e['initial_operating_point'][0]
    last=np.concatenate((initial[None],physical[:-1]));rates=np.abs(physical-last)/e['dt_s']
    chosen=[r['chosen'] for r in plans];wall=np.asarray([r['wall_seconds'] for r in plans])
    m={k:case[k] for k in ('case_id','split','run_id','family','target_w','initial_pitch_rad')}
    m.update(controller=rows[0]['controller'],rmse_w=float(np.sqrt(np.mean(errors**2))),bias_w=float(errors.mean()),
        mae_w=float(np.abs(errors).mean()),tracking_return=float(-e['reward_scale']*np.sum((errors/sum(cfg['plant']['rated_power_w']))**2)),
        action_penalty_return=float(-e['reward_scale']*e['action_change_weight']*changes.sum()),mean_action_change=float(changes.mean()),
        speed_command_total_variation=float(np.abs(commands[:,:,2]-previous[:,:,2]).sum()*.667/2),
        maximum_heading_rate=float(rates[:,:,0].max()),maximum_pitch_rate=float(rates[:,:,1].max()),maximum_speed_rate=float(rates[:,:,2].max()),
        speed_near_physical_bound_fraction=float(np.mean(np.abs(commands[:,:,2])>=1-1e-6)),
        decisions=len(plans),zero_decisions=chosen.count(0),boundary_decisions=sum(i!=0 for i in chosen),
        planning_mean_seconds=float(wall.mean()) if len(wall) else 0.,planning_p95_seconds=float(np.quantile(wall,.95)) if len(wall) else 0.,
        planning_max_seconds=float(wall.max()) if len(wall) else 0.,internal_model_rows=spent['kinds'].get('internal_forecast',0),new_model_rows=spent['actual'])
    assert np.all(rates.max(axis=(0,1))<=np.asarray(e['rate_limits'])+1e-7)
    return m


def verify(root):
    import numpy as np
    from .causal_speed_search import context
    saved,p=context(root);verify_hashes({str(root/k):v for k,v in read_json(root/'complete.json').items()})
    rows=read_csv(root/'metrics.csv');traces=read_csv(root/'trajectories.csv');manifest=read_json(root/'bank/manifest.json')['cases']
    assert len(rows)==288 and len(traces)==36864 and len(manifest)==36
    groups={}
    for r in traces:groups.setdefault((r['case_id'],r['controller']),[]).append(r)
    maximum=0.;pairwise=[];recomputed=[]
    for case in manifest:
        folder=root/'cases'/case['case_id'];verify_hashes({str(folder/k):v for k,v in read_json(folder/'complete.json').items()})
        wind=np.loadtxt(root/'bank'/case['path'],delimiter=',',skiprows=1)[:,1:4].astype(np.float32)
        for controller in ('search','parent','n1_selected','n1_final','n8_selected','n8_final','p','pi'):
            part=groups[(case['case_id'],controller)];assert len(part)==128 and [int(float(r['step'])) for r in part]==list(range(1,129))
            np.testing.assert_array_equal([[float(r[k]) for k in ('wind_m_s','direction_rad','ti')] for r in part],wind[1:])
            assert all(float(r['target_w'])==case['target_w'] for r in part)
            old=next(r for r in rows if r['case_id']==case['case_id'] and r['controller']==controller)
            details=read_json(folder/f'{controller}.json')
            now=metric(part,case,saved['base_config'],details['plans'],details['budget'])
            for key,value in now.items():
                if isinstance(value,(int,float)):
                    delta=abs(value-float(old[key]));maximum=max(maximum,delta);assert delta<1e-7
            recomputed.append(now)
            if controller=='search':
                data=np.load(folder/'causal_demonstrations.npz')
                assert data['obs'].shape==(128,3,15) and data['action'].shape==(128,3,3)
                np.testing.assert_array_equal(data['action'][:,:,:2],data['parent_action'][:,:,:2])
                assert np.abs(data['offset']).max()<=.1 and int(data['decision'].sum())==16
                for plan in details['plans']:
                    assert len(plan['costs_MW2'])==9 and plan['costs_MW2'][plan['chosen']]<=plan['costs_MW2'][0]+1e-12
                    assert plan['predicted_steps']==min(12,128-plan['step'])
                parent=next(r for r in rows if r['case_id']==case['case_id'] and r['controller']=='parent')
                pairwise.append(dict(case_id=case['case_id'],split=case['split'],run_id=case['run_id'],family=case['family'],target_w=case['target_w'],
                    parent_rmse_w=float(parent['rmse_w']),search_rmse_w=float(old['rmse_w']),ratio=float(old['rmse_w'])/float(parent['rmse_w']),
                    improvement_w=float(parent['rmse_w'])-float(old['rmse_w'])))
    aggregates=[];passed=True
    for split in ('train','validation'):
        for run in range(3):
            part=[r for r in pairwise if r['split']==split and r['run_id']==run]
            ratio=sum(r['search_rmse_w'] for r in part)/sum(r['parent_rmse_w'] for r in part)
            aggregates.append(dict(split=split,run_id=run,parent_mean_w=float(np.mean([r['parent_rmse_w'] for r in part])),
                search_mean_w=float(np.mean([r['search_rmse_w'] for r in part])),ratio=ratio,improved_cases=sum(r['ratio']<1 for r in part),cases=6))
            passed &= ratio<1
        part=[r for r in pairwise if r['split']==split]
        passed &= sum(r['search_rmse_w'] for r in part)<=.99*sum(r['parent_rmse_w'] for r in part)
    budget=read_json(root/'budget.json');assert all(s['status']=='complete' for s in budget['scopes'])
    actual=sum(s['actual'] for s in budget['scopes']);kinds={}
    for scope in budget['scopes']:
        for key,value in scope['kinds'].items():kinds[key]=kinds.get(key,0)+value
    assert actual==sum(kinds.values())<=100000
    assert sum(r['new_model_rows'] for r in recomputed)+read_json(root/'precheck.json')['budget']['actual']+read_json(root/'tests.json')['mock_model_rows']==actual
    write_csv(root/'paired_parent.csv',pairwise);write_csv(root/'stream_summary.csv',aggregates)
    write_json(root/'verification.json',dict(passed=True,metrics=288,trace_rows=36864,maximum_metric_recompute_difference=maximum,
        source_and_execution_hashes_unchanged=True,model_rows=actual,model_rows_by_kind=kinds,model_row_hard_cap=100000,
        formal_RL_steps=0,repeated_parent_improvement=bool(passed),new_test_released=False))
    write_json(root/'summary.txt',dict(seed=42,status='verified',formal_RL_steps=0,model_rows=actual,
        model_rows_by_kind=kinds,repeated_parent_improvement=bool(passed),stream_results=aggregates,new_test_released=False,
        report='../../maddpg_wind_farm/SPEED_CAUSAL_SEARCH_RESULTS.md'))
    print('Verified model rows',actual,'repeated improvement',passed,flush=True)


def figures(root):
    import os
    import numpy as np
    os.environ.setdefault('MPLCONFIGDIR',str(root/'plot_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out=root/'figures';out.mkdir(exist_ok=False);generated={}
    def save(fig,name):
        for ext in ('png','pdf'):
            path=out/f'{name}.{ext}';fig.savefig(path,dpi=150);generated[path.name]=sha(path)
        plt.close(fig)
    rows=read_csv(root/'metrics.csv');paired=read_csv(root/'paired_parent.csv')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for ax,split in zip(axes,('train','validation')):
        for run in range(3):
            part=[r for r in paired if r['split']==split and int(r['run_id'])==run]
            ax.plot(range(6),[float(r['ratio']) for r in part],'o-',label=f'stream {run}')
        ax.axhline(1,color='black',ls='--');ax.set(title=split,xlabel='stationary / ramp / gust x 2 targets',ylabel='Search / fixed-parent case RMSE');ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Causal rolling speed search | fixed 9 candidates, H=12, replan every 8 steps | no RL training')
    save(fig,'parent_case_ratios')
    labels=('parent','n1_selected','n1_final','n8_selected','n8_final','search','p','pi')
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,split in zip(axes,('train','validation')):
        y=[np.mean([float(r['rmse_w']) for r in rows if r['split']==split and r['controller']==label])/1000 for label in labels]
        ax.bar(range(8),y,color=['#88949c']+['#c77c4b']*2+['#277fa2']*2+['#5a9b4f','#a49a4e','#8e63a0'])
        ax.set(xticks=range(8),xticklabels=labels,ylabel='Mean case RMSE [kW]',title=split);ax.tick_params(axis='x',rotation=35);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Finite seen training / diagnostic validation | full control-scheme comparison, no held-out test')
    save(fig,'controller_comparison')
    traces=read_csv(root/'trajectories.csv');fig,axes=plt.subplots(4,3,figsize=(15,11),layout='constrained',sharex=True)
    for run in range(3):
        cid=f'validation_run{run}_ramp_3450000'
        for label,color in [('parent','#88949c'),('search','#5a9b4f'),('n8_final','#277fa2'),('pi','#8e63a0')]:
            part=[r for r in traces if r['case_id']==cid and r['controller']==label];x=[int(float(r['step'])) for r in part]
            axes[0,run].plot(x,[float(r['farm_power_w'])/1e6 for r in part],color=color,label=label)
            for i,ls in zip((1,2,3),('-','--',':')):
                for ax,key,factor in [(axes[1,run],f'pitch_{i}',180/np.pi),(axes[2,run],f'speed_{i}',1),(axes[3,run],f'command_{i}_2',1)]:
                    ax.plot(x,[float(r[key])*factor for r in part],color=color,ls=ls,lw=.9)
        axes[0,run].axhline(3.45,color='black',ls='--');axes[0,run].set_title(f'stream {run}');axes[0,run].legend(fontsize=7)
        axes[3,run].set_xlabel('Step [1 s]')
    for i,label in enumerate(('Power [MW]','Applied pitch [deg]','Applied speed [rad/s]','Total speed command\nnormalized [-1,1]')):
        axes[i,0].set_ylabel(label)
        for ax in axes[i]:ax.grid(alpha=.2)
    fig.suptitle('Predeclared validation ramp high target | parent pitch follows each own current state | no yaw learning')
    save(fig,'causal_controls')
    write_json(out/'manifest.json',dict(python_matplotlib=True,generated=generated))
