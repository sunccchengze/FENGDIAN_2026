"""Saved-data audits and three fixed figure groups; no PINN inference."""
from pathlib import Path
from collections import defaultdict
import argparse
import hashlib
import math
from .anchor_closeout import read_json,write_json,read_csv,write_csv,sha,verify_hashes


def verify(root):
    import numpy as np
    from .history_speed_search import loop_context
    from .history_wind_forecast import RidgeForecast
    from .midgrid_speed_report import group_metrics
    cfg=loop_context(root);verify_hashes({str(root/k):v for k,v in read_json(root/'loop_complete.json').items()})
    source=Path(cfg['source']);manifest=read_json(root/'bank_manifest.json');model=RidgeForecast.load(root/'forecast_model.npz')
    forecast=read_csv(root/'predictions.csv');fm=read_csv(root/'metrics.csv');groups=defaultdict(list)
    for row in forecast:groups[int(row['trajectory'])].append(row)
    max_forecast_metric=0.;cold=[]
    for i,entry in enumerate(manifest['score']):
        values=np.loadtxt(root/entry['path'],delimiter=',',skiprows=1)[:,1:4].astype(np.float32)
        for origin in range(0,128,8):
            prediction,_=model.predict(values[:origin+1]);changed=values.copy();changed[origin+1:]=[7.5,1.,.04]
            np.testing.assert_array_equal(prediction,model.predict(changed[:origin+1])[0])
            for row in [r for r in groups[i] if int(r['origin'])==origin]:
                h=int(row['horizon']);assert float(row['predicted_speed'])==float(prediction[h-1,0])
                assert float(row['actual_speed'])==float(values[origin+h,0]) and float(row['persistence_speed'])==float(values[origin,0])
        for row in [r for r in fm if int(r['trajectory'])==i]:
            interval=row['interval'];h=int(interval[1:]) if interval.startswith('h') else int(interval.split('_')[1])
            part=[r for r in groups[i] if (int(r['horizon'])==h if interval.startswith('h') else int(r['horizon'])<=h)
                and (interval!='1_12' or int(r['origin'])<=112)]
            for key,raw in [('speed_MSE','speed_error'),('persistence_speed_MSE','persistence_speed_error')]:
                value=math.fsum(float(r[raw])**2 for r in part)/len(part);max_forecast_metric=max(max_forecast_metric,abs(value-float(row[key])))
        for interval in ('1_8','1_12'):
            for period in ('cold','full_history'):
                part=[r for r in groups[i] if int(r['horizon'])<=(8 if interval=='1_8' else 12) and (interval!='1_12' or int(r['origin'])<=112)
                    and ((int(r['origin'])<31)==(period=='cold'))]
                a=math.fsum(float(r['speed_error'])**2 for r in part)/len(part);b=math.fsum(float(r['persistence_speed_error'])**2 for r in part)/len(part)
                cold.append(dict(trajectory=i,split=entry['split'],family=entry['family'],interval=interval,period=period,samples=len(part),speed_MSE=a,persistence_speed_MSE=b,ratio=a/b))
    assert max_forecast_metric<1e-12
    metrics=read_csv(root/'loop_metrics.csv');traces=read_csv(root/'loop_trajectories.csv');groups=defaultdict(list)
    assert len(metrics)==360 and len(traces)==46080
    for row in traces:groups[(row['case_id'],row['controller'])].append(row)
    maximum=0.;pairs=[];realization=[];count=0
    for case in read_json(source/'bank/manifest.json')['cases']:
        cid=case['case_id'];folder=root/'cases'/cid
        verify_hashes({str(folder/k):v for k,v in read_json(folder/'complete.json').items()})
        wind=np.loadtxt(source/'bank'/case['path'],delimiter=',',skiprows=1)[:,1:4].astype(np.float32)
        part=groups[(cid,'history17')];data=np.load(folder/'current_world.npz')
        np.testing.assert_array_equal([[float(r[k]) for k in ('wind_m_s','direction_rad','ti')] for r in part],wind[1:])
        assert all(float(r['target_w'])==case['target_w'] for r in part)
        np.testing.assert_array_equal(data['action'][:,:,:2],data['parent_action'][:,:,:2])
        for i,plan in enumerate(read_json(folder/'plans.json')['plans']):
            t=plan['step'];prediction,_=model.predict(wind[:t+1]);h=min(12,128-t)
            np.testing.assert_array_equal(plan['predicted_wind'],prediction[:h])
            assert plan['observed_history_rows']==t+1 and plan['observed_history_sha256']==hashlib.sha256(wind[:t+1].tobytes()).hexdigest()
            error=np.asarray(plan['predicted_error_w']);cost=np.mean((error/1e6)**2,axis=1)
            np.testing.assert_allclose(cost,plan['costs_MW2'],atol=1e-15,rtol=0)
            chosen=plan['chosen'];predicted=error[chosen,:8];observed=np.array([float(r['error_w']) for r in part[t:t+8]])
            realization.append(dict(case_id=cid,split=case['split'],run_id=case['run_id'],step=t,chosen=chosen,
                predicted8_rmse_w=float(np.sqrt(np.mean(predicted**2))),actual8_rmse_w=float(np.sqrt(np.mean(observed**2))),
                prediction_actual_error_rmse_w=float(np.sqrt(np.mean((predicted-observed)**2))),wall_seconds=plan['wall_seconds']))
            count+=1
        per={r['controller']:r for r in metrics if r['case_id']==cid}
        pairs.append(dict(**{k:case[k] for k in ('case_id','split','run_id','family','target_w')},
            history17_rmse_w=float(per['history17']['rmse_w']),grid17_rmse_w=float(per['grid17']['rmse_w']),parent_rmse_w=float(per['parent']['rmse_w']),
            history_over_grid17=float(per['history17']['rmse_w'])/float(per['grid17']['rmse_w']),
            history_over_parent=float(per['history17']['rmse_w'])/float(per['parent']['rmse_w'])))
        for label,row in per.items():
            errors=[float(r['farm_power_w'])-float(r['target_w']) for r in groups[(cid,label)]]
            maximum=max(maximum,abs(math.sqrt(math.fsum(x*x for x in errors)/128)-float(row['rmse_w'])),abs(math.fsum(errors)/128-float(row['bias_w'])))
    assert maximum<1e-7 and count==576
    streams=[];repeated=True
    for split in ('train','validation'):
        for run in range(3):
            part=[r for r in pairs if r['split']==split and r['run_id']==run]
            a=np.mean([r['history17_rmse_w'] for r in part]);b=np.mean([r['grid17_rmse_w'] for r in part]);p=np.mean([r['parent_rmse_w'] for r in part])
            streams.append(dict(split=split,run_id=run,history17_mean_w=float(a),grid17_mean_w=float(b),parent_mean_w=float(p),history_over_grid17=float(a/b),history_over_parent=float(a/p),
                improved_grid17_cases=sum(r['history_over_grid17']<1 for r in part),improved_parent_cases=sum(r['history_over_parent']<1 for r in part)))
            repeated &= a<p
        part=[r for r in pairs if r['split']==split];repeated &= sum(r['history17_rmse_w'] for r in part)<=.99*sum(r['parent_rmse_w'] for r in part)
    budget=read_json(root/'budget.json');total=sum(r['actual'] for r in budget['scopes'])
    assert all(r['status']=='complete' for r in budget['scopes']) and len(budget['scopes'])==38 and total==121366<=170000
    assert sum(float(r['new_model_rows']) for r in metrics)==119700
    write_csv(root/'cold_warm_metrics.csv',cold);write_csv(root/'group_metrics.csv',group_metrics(metrics));write_csv(root/'paired_cases.csv',pairs)
    write_csv(root/'stream_summary.csv',streams);write_csv(root/'forecast_realization.csv',realization)
    result=dict(passed=True,forecast_metric_recompute_max_error=max_forecast_metric,loop_metric_recompute_max_error=maximum,
        forecast_screen_passed=True,repeated_parent_improvement=bool(repeated),formal_RL_steps=0,PINN_mock_rows=total,
        new_independent_test_released=False,metrics=360,trace_rows=46080,all_plan_histories_forecasts_exact=True,
        source_and_execution_hashes_unchanged=True)
    write_json(root/'verification.json',result);write_json(root/'summary.txt',dict(result,status='verified',seed=42,streams=streams,
        forecast_screen=read_json(root/'screen.json'),report='../../maddpg_wind_farm/HISTORY_FORECAST_RESULTS.md'))
    print(result,flush=True)


def figures(root):
    import os
    os.environ.setdefault('MPLCONFIGDIR',str(root/'plot_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    out=root/'figures';out.mkdir(exist_ok=False);files={}
    def save(fig,name):
        for ext in ('png','pdf'):
            path=out/f'{name}.{ext}';fig.savefig(path,dpi=150);files[path.name]=sha(path)
        plt.close(fig)
    metrics=read_csv(root/'metrics.csv');fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for s,split in enumerate(('decision_train','decision_validation')):
        ax=axes[s,0]
        for key,label,color in [('persistence_speed_MSE','persistence','#bd764b'),('speed_MSE','history ridge','#277d9e')]:
            ax.plot(range(1,13),[np.mean([float(r[key]) for r in metrics if r['split']==split and r['interval']==f'h{h}']) for h in range(1,13)],'o-',label=label,color=color)
        ax.set(title=split,xlabel='Forecast horizon [s]',ylabel='Wind speed MSE [(m/s)^2]');ax.legend();ax.grid(alpha=.2)
        part=[r for r in metrics if r['split']==split and r['interval']=='1_8'];ax=axes[s,1]
        for family,color in [('stationary','#277d9e'),('ramp','#bd764b'),('gust','#6f8e4c')]:
            indices=[i for i,r in enumerate(part) if r['family']==family];ax.scatter(indices,[float(part[i]['speed_MSE_ratio']) for i in indices],label=family,color=color)
        ax.axhline(1,color='black',ls='--');ax.set(title=f'{len(part)} unique whole trajectories | 1..8 s',xlabel='Trajectory index (no parent duplication)',ylabel='History MSE / persistence MSE');ax.legend();ax.grid(alpha=.2)
    fig.suptitle('One fixed causal model | train-only fit | forecast improvement is not control gain')
    save(fig,'forecast_information')
    paired=read_csv(root/'paired_cases.csv');fig,axes=plt.subplots(2,3,figsize=(14,8),layout='constrained')
    for s,split in enumerate(('train','validation')):
        for run in range(3):
            ax=axes[s,run];part=[r for r in paired if r['split']==split and int(r['run_id'])==run]
            for label,key,color in [('persistence 17','grid17_rmse_w','#bd764b'),('history 17','history17_rmse_w','#277d9e')]:
                ax.plot(range(6),[float(r[key])/float(r['parent_rmse_w']) for r in part],'o-',label=label,color=color)
            ax.axhline(1,color='black',ls='--');ax.set(title=f'{split} / stream {run}',xlabel='stationary / ramp / gust x 2 targets',ylabel='Case RMSE / fixed parent');ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Only wind forecast changes | fixed grid17 / H12 / 8-step decisions | no RL or new test')
    save(fig,'forecast_control_value')
    traces=read_csv(root/'loop_trajectories.csv');fig,axes=plt.subplots(4,3,figsize=(15,12),layout='constrained',sharex=True)
    for run in range(3):
        cid=f'validation_run{run}_ramp_3450000'
        for label,color in [('parent','#8c979d'),('grid17','#bd764b'),('history17','#277d9e')]:
            part=[r for r in traces if r['case_id']==cid and r['controller']==label];x=[int(float(r['step'])) for r in part]
            axes[0,run].plot(x,[float(r['farm_power_w'])/1e6 for r in part],label=label,color=color)
            for i,ls in zip((1,2,3),('-','--',':')):
                for k,key in enumerate((f'pitch_{i}',f'speed_{i}',f'command_{i}_2'),1):axes[k,run].plot(x,[float(r[key]) for r in part],color=color,ls=ls,lw=.9)
        axes[0,run].axhline(3.45,color='black',ls='--');axes[0,run].set_title(f'stream {run}');axes[0,run].legend(fontsize=8);axes[3,run].set_xlabel('Step [1 s]')
    for i,label in enumerate(('Power [MW]','Applied pitch [rad]','Applied speed [rad/s]','Speed command [-1,1]')):
        axes[i,0].set_ylabel(label)
        for ax in axes[i]:ax.grid(alpha=.2)
    fig.suptitle('Predeclared validation ramp / high target | actual actuator trajectories | turbine styles 1/2/3')
    save(fig,'forecast_actual_controls');write_json(out/'manifest.json',dict(python_matplotlib=True,generated=files))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('verify','figures'));parser.add_argument('--output',required=True);args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    globals()[args.command](Path(args.output).resolve())


if __name__=='__main__':main()
