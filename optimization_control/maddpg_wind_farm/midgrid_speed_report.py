"""Saved-data audit and plots for the single added mid-amplitude grid."""
from collections import defaultdict
from pathlib import Path
import numpy as np
from .anchor_closeout import read_json,write_json,read_csv,write_csv,sha,verify_hashes
from .causal_speed_report import metric as original_metric


def metric(rows,case,cfg,plans,spent):
    m=original_metric(rows,case,cfg,plans,spent)
    chosen=[p['chosen'] for p in plans]
    m['boundary_decisions']=sum(0<i<9 for i in chosen);m['middle_decisions']=sum(i>=9 for i in chosen)
    m['candidate_switches']=sum(a!=b for a,b in zip(chosen,chosen[1:]))
    e=cfg['environment'];initial=np.tile([case['initial_wind_direction_rad']+e['initial_operating_point'][0],case['initial_pitch_rad'],e['initial_operating_point'][2]],(3,1))
    physical=np.asarray([[[float(r[f'heading_{i}_rad']),float(r[f'pitch_{i}']),float(r[f'speed_{i}'])] for i in (1,2,3)] for r in rows])
    change=np.abs(physical-np.concatenate((initial[None],physical[:-1])))
    for i,name in enumerate(('heading','pitch','speed')):m[f'actual_{name}_total_variation']=float(change[:,:,i].sum())
    return m


def group_metrics(rows):
    result=[]
    for split in ('train','validation'):
        specs=[('all','all')]+[('run_id',str(i)) for i in range(3)]+[('family',f) for f in ('stationary','ramp','gust')]
        specs += [('target_w',str(t)) for t in sorted({float(r['target_w']) for r in rows if r['split']==split})]
        for axis,value in specs:
            for controller in sorted({r['controller'] for r in rows}):
                part=[r for r in rows if r['split']==split and r['controller']==controller and
                    (axis=='all' or (float(r[axis])==float(value) if axis in ('run_id','target_w') else r[axis]==value))]
                if not part:continue
                errors=np.asarray([float(r['rmse_w']) for r in part])
                row=dict(split=split,axis=axis,value=value,controller=controller,cases=len(part),
                    mean_case_rmse_w=float(errors.mean()),pooled_rmse_w=float(np.sqrt(np.mean(errors**2))),
                    worst_case_rmse_w=float(errors.max()),bias_w=float(np.mean([float(r['bias_w']) for r in part])))
                for key in ('mean_action_change','speed_command_total_variation','actual_heading_total_variation','actual_pitch_total_variation',
                    'actual_speed_total_variation','planning_mean_seconds','middle_decisions','zero_decisions','boundary_decisions','candidate_switches'):
                    row[key]=float(np.mean([float(r[key]) for r in part]))
                result.append(row)
    return result


def verify(root):
    from .midgrid_speed_search import context,grid
    cfg,p=context(root);verify_hashes({str(root/k):v for k,v in read_json(root/'complete.json').items()})
    rows=read_csv(root/'metrics.csv');traces=read_csv(root/'trajectories.csv');cases=read_json(root/'bank/manifest.json')['cases']
    assert len(rows)==324 and len(traces)==41472 and len(cases)==36
    groups=defaultdict(list)
    for row in traces:groups[(row['case_id'],row['controller'])].append(row)
    paired=[];forecast=[];max_error=0.;prefix_advantages=[];middle_count=zero_count=boundary_count=0
    for case in cases:
        cid=case['case_id'];folder=root/'cases'/cid
        verify_hashes({str(folder/k):v for k,v in read_json(folder/'complete.json').items()})
        details=read_json(folder/'plans.json');plans=details['plans']
        for controller in sorted({r['controller'] for r in rows}):
            part=groups[(cid,controller)];assert len(part)==128 and [int(float(r['step'])) for r in part]==list(range(1,129))
            row=next(r for r in rows if r['case_id']==cid and r['controller']==controller)
            error=np.asarray([float(r['farm_power_w'])-float(r['target_w']) for r in part])
            max_error=max(max_error,abs(float(np.sqrt(np.mean(error**2)))-float(row['rmse_w'])),abs(float(error.mean())-float(row['bias_w'])))
            assert np.isfinite(error).all()
        a=next(r for r in rows if r['case_id']==cid and r['controller']=='grid17')
        b=next(r for r in rows if r['case_id']==cid and r['controller']=='grid9')
        parent=next(r for r in rows if r['case_id']==cid and r['controller']=='parent')
        paired.append(dict(case_id=cid,split=case['split'],run_id=case['run_id'],family=case['family'],target_w=case['target_w'],
            grid9_rmse_w=float(b['rmse_w']),grid17_rmse_w=float(a['rmse_w']),parent_rmse_w=float(parent['rmse_w']),
            fine_over_coarse=float(a['rmse_w'])/float(b['rmse_w']),fine_over_parent=float(a['rmse_w'])/float(parent['rmse_w'])))
        actual=np.asarray([float(r['error_w']) for r in groups[(cid,'grid17')]])
        data=np.load(folder/'current_world.npz')
        assert data['obs'].shape==(128,3,15);np.testing.assert_array_equal(data['action'][:,:,:2],data['parent_action'][:,:,:2])
        for i,plan in enumerate(plans):
            errors=np.asarray(plan['predicted_error_w']);costs=np.mean((errors/1e6)**2,axis=1)
            np.testing.assert_allclose(costs,plan['costs_MW2'],atol=1e-15,rtol=0)
            assert errors.shape==(17,min(12,128-plan['step']))
            assert plan['costs_MW2'][plan['chosen']]<=min(plan['costs_MW2'][:9])+1e-12
            prefix_advantages.append(min(plan['costs_MW2'][:9])-plan['costs_MW2'][plan['chosen']])
            np.testing.assert_array_equal(data['offset'][i*8:i*8+8],np.tile(grid()[plan['chosen']],(8,1)))
            chosen=plan['chosen'];middle_count+=chosen>=9;zero_count+=chosen==0;boundary_count+=0<chosen<9
            predicted=errors[chosen,:8];observed=actual[i*8:i*8+8]
            forecast.append(dict(case_id=cid,split=case['split'],run_id=case['run_id'],decision_step=plan['step'],chosen=chosen,
                best_original9_MW2=min(plan['costs_MW2'][:9]),best_all17_MW2=plan['costs_MW2'][chosen],
                predicted8_rmse_w=float(np.sqrt(np.mean(predicted**2))),actual8_rmse_w=float(np.sqrt(np.mean(observed**2))),
                forecast_actual_error_rmse_w=float(np.sqrt(np.mean((predicted-observed)**2))),wall_seconds=plan['wall_seconds']))
    assert max_error<1e-7 and len(forecast)==576
    agg=group_metrics(rows);stream=[];repeated=True
    for split in ('train','validation'):
        for run in range(3):
            part=[r for r in paired if r['split']==split and r['run_id']==run]
            fine=np.mean([r['grid17_rmse_w'] for r in part]);coarse=np.mean([r['grid9_rmse_w'] for r in part]);parent=np.mean([r['parent_rmse_w'] for r in part])
            stream.append(dict(split=split,run_id=run,grid9_mean_w=float(coarse),grid17_mean_w=float(fine),parent_mean_w=float(parent),
                fine_over_coarse=float(fine/coarse),fine_over_parent=float(fine/parent),improved_coarse_cases=sum(r['fine_over_coarse']<1 for r in part),improved_parent_cases=sum(r['fine_over_parent']<1 for r in part)))
            repeated &= fine<parent
        part=[r for r in paired if r['split']==split];repeated &= sum(r['grid17_rmse_w'] for r in part)<=.99*sum(r['parent_rmse_w'] for r in part)
    budget=read_json(root/'budget.json');assert all(s['status']=='complete' for s in budget['scopes'])
    total=sum(s['actual'] for s in budget['scopes']);assert total<=170000
    assert sum(int(float(r['new_model_rows'])) for r in rows)+read_json(root/'precheck.json')['budget']['actual']+read_json(root/'tests.json')['mock_model_rows']==total
    write_csv(root/'paired_cases.csv',paired);write_csv(root/'group_metrics.csv',agg);write_csv(root/'stream_summary.csv',stream);write_csv(root/'forecast_actual.csv',forecast)
    result=dict(passed=True,formal_RL_steps=0,model_rows=total,hard_cap=170000,repeated_parent_improvement=bool(repeated),
        metrics=324,trace_rows=41472,maximum_metric_recompute_error=max_error,forecast_min_never_above_same_state_prefix9=True,
        positive_same_state_prediction_advantage_decisions=sum(x>1e-12 for x in prefix_advantages),
        decisions=576,middle_decisions=int(middle_count),zero_decisions=int(zero_count),endpoint_decisions=int(boundary_count),
        new_test_released=False,source_and_execution_hashes_unchanged=True)
    write_json(root/'verification.json',result);write_json(root/'summary.txt',dict(result,status='verified',seed=42,streams=stream,
        report='../../maddpg_wind_farm/SPEED_MIDGRID_RESULTS.md'))
    print(result,flush=True)


def figures(root):
    import os
    os.environ.setdefault('MPLCONFIGDIR',str(root/'plot_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out=root/'figures';out.mkdir(exist_ok=False);files={}
    def save(fig,name):
        for ext in ('png','pdf'):
            path=out/f'{name}.{ext}';fig.savefig(path,dpi=150);files[path.name]=sha(path)
        plt.close(fig)
    paired=read_csv(root/'paired_cases.csv');fig,axes=plt.subplots(2,3,figsize=(14,8),layout='constrained')
    for s,split in enumerate(('train','validation')):
        for run in range(3):
            ax=axes[s,run];part=[r for r in paired if r['split']==split and int(r['run_id'])==run]
            for label,key,color in [('grid9','grid9_rmse_w','#bd764b'),('grid17','grid17_rmse_w','#277d9e')]:
                ax.plot(range(6),[float(r[key])/float(r['parent_rmse_w']) for r in part],'o-',label=label,color=color)
            ax.axhline(1,color='black',ls='--');ax.set(title=f'{split} / stream {run}',xlabel='stationary / ramp / gust x 2 targets',ylabel='Case RMSE / fixed parent');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Only candidate grid changes: original endpoints vs appended +/-0.05 | no RL, no new test')
    save(fig,'grid_case_comparison')
    forecast=read_csv(root/'forecast_actual.csv');fig,axes=plt.subplots(1,3,figsize=(15,4.5),layout='constrained')
    for split,color in [('train','#bd764b'),('validation','#277d9e')]:
        part=[r for r in forecast if r['split']==split];x=[float(r['predicted8_rmse_w'])/1000 for r in part];y=[float(r['actual8_rmse_w'])/1000 for r in part]
        axes[0].scatter(x,y,s=12,alpha=.4,label=split,color=color)
    limit=max(float(r['actual8_rmse_w'])/1000 for r in forecast);axes[0].plot([0,limit],[0,limit],'k--');axes[0].set(xlabel='Chosen forecast 8-step RMSE [kW]',ylabel='Realized same 8-step RMSE [kW]');axes[0].legend()
    axes[1].hist([int(r['chosen']) for r in forecast],bins=np.arange(-.5,17.5),color='#277d9e');axes[1].axvline(8.5,color='black',ls='--');axes[1].set(xlabel='Candidate index (9..16 are middle amplitude)',ylabel='Choices')
    axes[2].hist([float(r['wall_seconds']) for r in forecast],bins=24,color='#277d9e');axes[2].set(xlabel='Measured enumeration seconds / decision',ylabel='Count')
    fig.suptitle('Prediction advantage is not closed-loop gain | persistence forecast | fixed 8-step hold')
    save(fig,'forecast_choices_cost')
    traces=read_csv(root/'trajectories.csv');fig,axes=plt.subplots(3,3,figsize=(15,10),layout='constrained',sharex=True)
    for run in range(3):
        cid=f'validation_run{run}_ramp_3450000'
        for label,color in [('parent','#8c979d'),('grid9','#bd764b'),('grid17','#277d9e')]:
            part=[r for r in traces if r['case_id']==cid and r['controller']==label];x=[int(float(r['step'])) for r in part]
            axes[0,run].plot(x,[float(r['farm_power_w'])/1e6 for r in part],color=color,label=label)
            for i,ls in zip((1,2,3),('-','--',':')):
                axes[1,run].plot(x,[float(r[f'speed_{i}']) for r in part],ls=ls,color=color,lw=.9)
                axes[2,run].plot(x,[float(r[f'command_{i}_2']) for r in part],ls=ls,color=color,lw=.9)
        axes[0,run].axhline(3.45,color='black',ls='--');axes[0,run].set_title(f'stream {run}');axes[0,run].legend(fontsize=8);axes[2,run].set_xlabel('Step [1 s]')
    for i,label in enumerate(('Power [MW]','Applied speed [rad/s]','Total speed command [-1,1]')):
        axes[i,0].set_ylabel(label)
        for ax in axes[i]:ax.grid(alpha=.2)
    fig.suptitle('Predeclared validation ramp high target | own current-state parent feedback | turbine 1/2/3 line styles')
    save(fig,'grid_actual_controls');write_json(out/'manifest.json',dict(python_matplotlib=True,generated=files))
