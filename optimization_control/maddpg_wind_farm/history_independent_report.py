"""Independent-test saved-data verification and bounded artifacts; no PINN queries."""
from collections import defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
from .anchor_closeout import read_json,read_csv,sha,verify_hashes
from .history_independent_test import Artifacts,context


def load_rollout(root,metric):
    import numpy as np
    path=root/metric['trace_path']
    if sha(path)!=metric['trace_sha256']:raise ValueError('compressed rollout hash changed')
    with np.load(path,allow_pickle=False) as saved:data={k:saved[k] for k in saved.files}
    meta=json.loads(data.pop('metadata').tobytes().decode('utf-8'))
    rows=[dict(zip(meta['trace_fields'],row)) for row in data['trace']]
    return meta,data,rows


def mean(values):
    values=list(values);return math.fsum(values)/len(values)


def group_metrics(metrics):
    rows=[]
    specs=[('all','all')]+[('run_id',str(i)) for i in range(3)]+[('family',f) for f in ('stationary','ramp','gust')]
    specs += [('target_w',str(t)) for t in (2750000,3350000,3850000)]+[('initial_pitch_rad',str(x)) for x in (.025,.055)]
    for axis,value in specs:
        for label in ('history17','persistence17','parent','p','pi'):
            part=[r for r in metrics if r['controller']==label and (axis=='all' or (label in ('p','pi') and axis=='run_id') or
                (float(r[axis])==float(value) if axis in ('run_id','target_w','initial_pitch_rad') else r[axis]==value))]
            errors=[float(r['rmse_w']) for r in part]
            row=dict(axis=axis,value=value,controller=label,cases=len(part),unique_winds=len({r['case_id'] for r in part}),
                baseline_shared_across_parents=label in ('p','pi'),mean_case_rmse_w=mean(errors),pooled_rmse_w=math.sqrt(mean(x*x for x in errors)),
                worst_case_rmse_w=max(errors),bias_w=mean(float(r['bias_w']) for r in part),case_le400=sum(x<=400000 for x in errors),case_le500=sum(x<=500000 for x in errors))
            for key in ('mean_action_change','speed_command_total_variation','actual_heading_total_variation','actual_pitch_total_variation','actual_speed_total_variation',
                'planning_mean_seconds','planning_cpu_mean_seconds','action_cpu_mean_seconds','action_wall_mean_seconds'):
                row[key]=mean(float(r[key]) for r in part)
            for key in ('maximum_heading_rate','maximum_pitch_rate','maximum_speed_rate'):row[key]=max(float(r[key]) for r in part)
            rows.append(row)
    return rows


def timing_row(plan,metric):
    timing=plan['timing'];a,b=timing['start'],timing['end']
    row=dict(scope=metric['scope'],case_id=metric['case_id'],run_id=int(metric['run_id']),controller=metric['controller'],step=plan['step'],
        wall_seconds=timing['wall_seconds'],cpu_seconds=timing['cpu_seconds'],native_wall_seconds=plan['native_wall_seconds'],utc_seconds=timing['utc_seconds'],
        utc_minus_perf_seconds=timing['utc_seconds']-timing['wall_seconds'],pid=a['pid'],utc_start_ns=a['utc_ns'],utc_end_ns=b['utc_ns'])
    for key,scale in [('uptime_ms',.001),('awake_100ns',1e-7),('machine_idle_100ns',1e-7),('machine_kernel_100ns',1e-7),('machine_user_100ns',1e-7)]:
        row[key+'_delta_seconds']=(b[key]-a[key])*scale if a.get(key) is not None and b.get(key) is not None else None
    awake=row['awake_100ns_delta_seconds'];row['wall_minus_awake_seconds']=timing['wall_seconds']-awake if awake is not None else None
    return row


def verify(root):
    import numpy as np
    import torch
    from .algorithm import MADDPG
    from .history_wind_forecast import RidgeForecast,score
    from .midgrid_speed_search import grid,choose
    cfg=context(root,released=True);store=Artifacts(root);verify_hashes({str(root/k):v for k,v in read_json(root/'complete.json').items()})
    release=read_json(root/'release.json');assert release['precheck_sha256']==sha(root/'precheck.json') and release['tests_sha256']==sha(root/'tests.json')
    metrics=read_csv(root/'metrics.csv');cases=read_json(root/'bank/manifest.json')['cases'];by_case={x['case_id']:x for x in cases}
    assert len(metrics)==198 and len({r['scope'] for r in metrics})==198 and len(cases)==18
    assert {label:sum(r['controller']==label for r in metrics) for label in ('history17','persistence17','parent','p','pi')}==dict(history17=54,persistence17=54,parent=54,p=18,pi=18)
    torch.set_num_threads(1);parents=[MADDPG.load(p['checkpoint'])[0] for p in cfg['parents']]
    parent_rng=[json.dumps(p.rng.bit_generator.state,sort_keys=True) for p in parents];model=RidgeForecast.load(cfg['model'])
    winds={c['case_id']:np.loadtxt(root/c['path'],delimiter=',',skiprows=1)[:,1:4].astype(np.float32) for c in cases}
    maximum=0.;cost_error=0.;gamma_error=0.;timings=[];motion=[];realization=[];steps=0
    for metric in metrics:
        meta,data,rows=load_rollout(root,metric);case=by_case[metric['case_id']];label=metric['controller'];run=int(metric['run_id']);wind=winds[case['case_id']]
        assert len(rows)==128 and [int(r['step']) for r in rows]==list(range(1,129)) and all(r['target_w']==case['target_w'] for r in rows)
        np.testing.assert_array_equal([[r[k] for k in ('wind_m_s','direction_rad','ti')] for r in rows],wind[1:])
        errors=[r['farm_power_w']-r['target_w'] for r in rows]
        maximum=max(maximum,abs(math.sqrt(mean(x*x for x in errors))-float(metric['rmse_w'])),abs(mean(errors)-float(metric['bias_w'])))
        commands=np.asarray([[[r[f'command_{i}_{j}'] for j in range(3)] for i in (1,2,3)] for r in rows],np.float32)
        np.testing.assert_array_equal(commands,data['action']);np.testing.assert_array_equal(data['obs'][1:,:,5:8],commands[:-1])
        if run>=0:
            for obs,reference in zip(data['obs'],data['parent_action']):np.testing.assert_array_equal(parents[run].act(obs),reference)
            np.testing.assert_array_equal(data['action'][:,:,:2],data['parent_action'][:,:,:2])
        e=cfg['base_config']['environment'];initial=np.tile([case['initial_wind_direction_rad']+e['initial_operating_point'][0],case['initial_pitch_rad'],e['initial_operating_point'][2]],(3,1))
        physical=np.asarray([[[r[f'heading_{i}_rad'],r[f'pitch_{i}'],r[f'speed_{i}']] for i in (1,2,3)] for r in rows])
        rates=np.abs(physical-np.concatenate((initial[None],physical[:-1])))/e['dt_s'];assert np.all(rates.max(axis=(0,1))<=np.asarray(e['rate_limits'])+1e-7)
        for r in rows:
            for i in (1,2,3):gamma_error=max(gamma_error,abs((r[f'heading_{i}_rad']-r['direction_rad']+np.pi)%(2*np.pi)-np.pi-r[f'gamma_{i}']))
        motion.append(dict(scope=metric['scope'],case_id=case['case_id'],controller=label,run_id=run,
            command_speed_bound_fraction=float(np.mean(np.abs(commands[:,:,2])>=1-1e-6)),
            actual_speed_bound_fraction=float(np.mean((physical[:,:,2]<=.6+1e-6)|(physical[:,:,2]>=1.267-1e-6)))))
        if label in ('history17','persistence17'):
            assert len(meta['plans'])==16
            for plan in meta['plans']:
                t=plan['step'];h=min(12,128-t);prefix=wind[:t+1]
                expected=model.predict(prefix)[0][:h] if label=='history17' else np.tile(prefix[-1],(h,1))
                np.testing.assert_array_equal(plan['predicted_wind'],expected)
                assert plan['observed_history_rows']==t+1 and plan['observed_history_sha256']==hashlib.sha256(prefix.tobytes()).hexdigest()
                raw=np.asarray(plan['predicted_error_w']);assert raw.shape==(17,h)
                for sequence,cost in zip(raw,plan['costs_MW2']):cost_error=max(cost_error,abs(math.fsum((x/1e6)**2 for x in sequence)/h-cost))
                assert choose(plan['costs_MW2'])==plan['chosen']
                np.testing.assert_array_equal(data['offset'][t:t+8],np.tile(grid()[plan['chosen']],(8,1)))
                predicted=raw[plan['chosen'],:8];observed=np.asarray(errors[t:t+8])
                realization.append(dict(scope=metric['scope'],case_id=case['case_id'],controller=label,run_id=run,step=t,
                    predicted8_rmse_w=float(np.sqrt(np.mean(predicted**2))),actual8_rmse_w=float(np.sqrt(np.mean(observed**2))),
                    prediction_actual_error_rmse_w=float(np.sqrt(np.mean((predicted-observed)**2)))))
                timings.append(timing_row(plan,metric))
            expected_action=(data['parent_action'][:,:,2]+2*data['offset']/.667).clip(-1,1).astype(np.float32)
            np.testing.assert_allclose(data['action'][:,:,2],expected_action,atol=1e-7,rtol=0)
        steps+=128
    assert maximum<1e-7 and cost_error<1e-12 and steps==25344 and len(timings)==1728
    assert parent_rng==[json.dumps(p.rng.bit_generator.state,sort_keys=True) for p in parents]
    paired=[];streams=[];parent_pass=True;forecast_pass=True
    for run in range(3):
        for case in cases:
            part={r['controller']:r for r in metrics if r['case_id']==case['case_id'] and int(r['run_id'])==run}
            a=float(part['history17']['rmse_w']);b=float(part['persistence17']['rmse_w']);p=float(part['parent']['rmse_w'])
            paired.append(dict(case_id=case['case_id'],family=case['family'],target_w=case['target_w'],initial_pitch_rad=case['initial_pitch_rad'],run_id=run,
                history17_rmse_w=a,persistence17_rmse_w=b,parent_rmse_w=p,history_over_parent=a/p,history_over_persistence=a/b,
                parent_case_noninferior=a<=1.05*p,persistence_case_noninferior=a<=1.05*b))
        part=[r for r in paired if r['run_id']==run];a=mean(r['history17_rmse_w'] for r in part);b=mean(r['persistence17_rmse_w'] for r in part);p=mean(r['parent_rmse_w'] for r in part)
        parent_pass &= a<p;forecast_pass &= a<b
        streams.append(dict(run_id=run,history17_mean_w=a,persistence17_mean_w=b,parent_mean_w=p,history_over_parent=a/p,history_over_persistence=a/b,
            improved_parent_cases=sum(r['history_over_parent']<1 for r in part),improved_persistence_cases=sum(r['history_over_persistence']<1 for r in part),
            parent_case_noninferior=sum(r['parent_case_noninferior'] for r in part),persistence_case_noninferior=sum(r['persistence_case_noninferior'] for r in part)))
    parent_pass &= mean(r['history17_rmse_w'] for r in paired)<=.99*mean(r['parent_rmse_w'] for r in paired)
    forecast_pass &= mean(r['history17_rmse_w'] for r in paired)<=.99*mean(r['persistence17_rmse_w'] for r in paired)
    uncertainty=[]
    for ref in ('parent','persistence17'):
        a=np.array([mean(r['history17_rmse_w'] for r in paired if r['case_id']==c['case_id']) for c in cases])
        b=np.array([mean(r[ref+'_rmse_w'] for r in paired if r['case_id']==c['case_id']) for c in cases]);rng=np.random.default_rng(42)
        groups=[np.array([i for i,c in enumerate(cases) if c['family']==f]) for f in ('stationary','ramp','gust')]
        sample=np.concatenate([rng.choice(g,size=(2000,len(g)),replace=True) for g in groups],axis=1);ratio=a[sample].mean(axis=1)/b[sample].mean(axis=1)
        uncertainty.append(dict(reference=ref,unique_wind_clusters=18,ratio=float(a.mean()/b.mean()),ratio_CI95_low=float(np.quantile(ratio,.025)),ratio_CI95_high=float(np.quantile(ratio,.975))))
    forecast_metrics=[];forecast_raw=[]
    for i,case in enumerate(cases):
        scored,raw=score(model,winds[case['case_id']]);tags=dict(trajectory=i,case_id=case['case_id'],family=case['family'])
        forecast_metrics.extend(dict(**tags,**r) for r in scored);forecast_raw.extend(dict(**tags,**r) for r in raw)
    forecast_groups=[]
    for interval in ('1_8','1_12'):
        for family in ('all','stationary','ramp','gust'):
            part=[r for r in forecast_metrics if r['interval']==interval and (family=='all' or r['family']==family)]
            a=np.array([r['speed_MSE'] for r in part]);b=np.array([r['persistence_speed_MSE'] for r in part]);rng=np.random.default_rng(42)
            group=[np.array([i for i,r in enumerate(part) if r['family']==f]) for f in ('stationary','ramp','gust')];group=[g for g in group if len(g)]
            sampled=np.concatenate([rng.choice(g,size=(2000,len(g)),replace=True) for g in group],axis=1);ratios=a[sampled].mean(axis=1)/b[sampled].mean(axis=1)
            row=dict(interval=interval,family=family,trajectories=len(part),speed_MSE=float(a.mean()),persistence_speed_MSE=float(b.mean()),speed_MSE_ratio=float(a.mean()/b.mean()),
                ratio_CI95_low=float(np.quantile(ratios,.025)),ratio_CI95_high=float(np.quantile(ratios,.975)))
            for key in ('speed_bias','direction_MSE','persistence_direction_MSE','direction_bias','speed_clip_fraction','mean_speed_clip_delta','ti_MSE'):row[key]=mean(r[key] for r in part)
            forecast_groups.append(row)
    budget=read_json(root/'budget.json');assert len(budget['scopes'])==200 and all(r['status']=='complete' for r in budget['scopes'])
    total=sum(r['actual'] for r in budget['scopes']);assert total==372352<=375000 and sum(float(r['new_model_rows']) for r in metrics)==370710
    for name,rows in [('group_metrics.csv',group_metrics(metrics)),('paired_cases.csv',paired),('stream_summary.csv',streams),('uncertainty.csv',uncertainty),
        ('planning_times.csv',timings),('physical_bounds.csv',motion),('forecast_realization.csv',realization),('forecast_metrics.csv',forecast_metrics),
        ('forecast_predictions.csv',forecast_raw),('forecast_groups.csv',forecast_groups)]:store.csv(name,rows)
    assert store.size()<cfg['protocol']['artifact_byte_hard_cap'] and not list(root.rglob('*.pth')) and not list(root.rglob('*.pt'))
    assert sorted(str(p) for p in Path(cfg['source']).rglob('*') if p.is_file())==cfg['source_inventory']
    result=dict(passed=True,parent_mean_gain_gate=bool(parent_pass),forecast_increment_gate=bool(forecast_pass),
        all_cases_parent_noninferior=all(r['parent_case_noninferior'] for r in paired),all_cases_persistence_noninferior=all(r['persistence_case_noninferior'] for r in paired),
        PINN_mock_rows=total,formal_RL_steps=0,forecast_refits=0,unique_test_winds=18,parent_stream_cases=54,physical_rollouts=198,transitions=steps,
        forecast_metric_trajectories=18,planning_calls=len(timings),maximum_metric_error=maximum,maximum_cost_error=cost_error,gamma_max_error=gamma_error,
        parent_actions_rng_exact=True,all_forecast_histories_exact=True,source_execution_hashes_unchanged=True,old_inventory_unchanged=True,
        artifact_bytes=store.size(),artifact_byte_hard_cap=1073741824,old_files_copied=0,old_863_95s_outlier_retained=True)
    store.json('verification.json',result);store.json('summary.txt',dict(result,status='verified',streams=streams,
        report='../../maddpg_wind_farm/HISTORY_INDEPENDENT_TEST_RESULTS.md'))
    print(result,flush=True)


def figures(root):
    import numpy as np
    Artifacts(root).ensure(1048576)
    os.environ.setdefault('MPLCONFIGDIR',str(root/'plot_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    store=Artifacts(root);files={}
    def save(fig,name):
        for ext in ('png','pdf'):
            import io
            with io.BytesIO() as buffer:fig.savefig(buffer,format=ext,dpi=150);store.write(f'figures/{name}.{ext}',buffer.getvalue())
            files[f'{name}.{ext}']=sha(root/f'figures/{name}.{ext}')
        plt.close(fig)
    paired=read_csv(root/'paired_cases.csv');fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained')
    for run,ax in enumerate(axes):
        part=[r for r in paired if int(r['run_id'])==run]
        for key,label,color in [('history17_rmse_w','history17','#277d9e'),('persistence17_rmse_w','persistence17','#bd764b')]:
            ax.plot(range(18),[float(r[key])/float(r['parent_rmse_w']) for r in part],'o-',color=color,label=label,ms=4)
        ax.axhline(1,color='black',ls='--');ax.axhline(1.05,color='#8b5960',ls=':');ax.set(title=f'Parent stream {run}',xlabel='18 unique test winds: 6 per family',ylabel='Case RMSE / fixed parent');ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Frozen candidate independent test | mean gates and individual failures are separate')
    save(fig,'independent_case_comparison')
    fm=read_csv(root/'forecast_metrics.csv');times=read_csv(root/'planning_times.csv');fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for name,key,ylabel in [('speed','speed_MSE','Wind speed MSE [(m/s)^2]'),('direction','direction_MSE','Wrapped direction MSE [rad^2]')]:
        ax=axes[0,0 if name=='speed' else 1]
        for prefix,label,color in [('', 'history forecast','#277d9e'),('persistence_','persistence','#bd764b')]:
            ax.plot(range(1,13),[mean(float(r[prefix+key]) for r in fm if r['interval']==f'h{h}') for h in range(1,13)],'o-',label=label,color=color)
        ax.set(xlabel='Forecast horizon [s]',ylabel=ylabel);ax.legend();ax.grid(alpha=.2)
    for label,color in [('history17','#277d9e'),('persistence17','#bd764b')]:
        part=[r for r in times if r['controller']==label];axes[1,0].scatter([float(r['cpu_seconds']) for r in part],[float(r['wall_seconds']) for r in part],s=8,alpha=.4,label=label,color=color)
    axes[1,0].set(xlabel='Process CPU seconds / plan',ylabel='Wall seconds / plan',xscale='log',yscale='log');axes[1,0].legend();axes[1,0].grid(alpha=.2)
    part=[r for r in fm if r['interval']=='1_8'];axes[1,1].plot(range(18),[float(r['speed_MSE_ratio']) for r in part],'o-',color='#277d9e');axes[1,1].axhline(1,color='black',ls='--')
    axes[1,1].set(xlabel='Unique test wind index',ylabel='1..8 s wind MSE / persistence');axes[1,1].grid(alpha=.2)
    fig.suptitle('Prediction scored once per wind | all timing calls retained | no real-time certificate')
    save(fig,'independent_forecast_timing')
    cfg=context(root,released=True);case=next(c for c in read_json(root/'bank/manifest.json')['cases'] if c['family']=='ramp' and c['target_w']==3850000 and c['initial_pitch_rad']==.055)
    metrics=read_csv(root/'metrics.csv');fig,axes=plt.subplots(4,3,figsize=(15,12),layout='constrained',sharex=True)
    for run in range(3):
        for label,color in [('parent','#8c979d'),('persistence17','#bd764b'),('history17','#277d9e')]:
            metric=next(m for m in metrics if m['case_id']==case['case_id'] and int(m['run_id'])==run and m['controller']==label);_,_,rows=load_rollout(root,metric);x=[r['step'] for r in rows]
            axes[0,run].plot(x,[r['farm_power_w']/1e6 for r in rows],label=label,color=color)
            for i,style in zip((1,2,3),('-','--',':')):
                for k,key in enumerate((f'pitch_{i}',f'speed_{i}',f'command_{i}_2'),1):axes[k,run].plot(x,[r[key] for r in rows],ls=style,color=color,lw=.9)
        axes[0,run].axhline(3.85,color='black',ls='--');axes[0,run].set_title(f'Parent stream {run}');axes[0,run].legend(fontsize=8);axes[3,run].set_xlabel('Step [1 s]')
    for i,label in enumerate(('Power [MW]','Applied pitch [rad]','Applied speed [rad/s]','Speed command [-1,1]')):
        axes[i,0].set_ylabel(label)
        for ax in axes[i]:ax.grid(alpha=.2)
    fig.suptitle('Fixed plot selection: ramp / 3.85 MW / initial pitch .055 rad | turbine 1/2/3 line styles')
    save(fig,'independent_actual_controls');store.json('figures/manifest.json',dict(python_matplotlib=True,generated=files))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('verify','figures'));parser.add_argument('--output',required=True);args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    globals()[args.command](Path(args.output).resolve())


if __name__=='__main__':main()
