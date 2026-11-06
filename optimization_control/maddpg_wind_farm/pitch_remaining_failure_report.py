"""Plot and verify the saved-only remaining-failure audit. No model runtime."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics

from .pitch_remaining_failure_audit import (
    HERE, ORIGINAL, SOURCE, check_sources, eligible, grouped, read_csv, read_json, sha, write_csv, write_json,
)


def verify(root):
    cfg=check_sources(root)
    pairs=read_csv(root/'paired_cases.csv')
    selected=[x for x in pairs if x['role']=='selected']
    assert len(pairs)==324 and len(selected)==108
    assert all(x['family']!='low_wind_stress' for x in pairs)
    assert len(set(x['case_id'] for x in pairs))==36
    assert len(set(x['waveform'] for x in pairs))==15
    assert sum(float(x['delta_pi_rmse_w'])>0 for x in selected)==11
    # Independently recompute every role/case from raw traces, without moments().
    residuals=[]
    baseline={}
    for role in ('pi','p'):
        raw=read_csv(SOURCE/f'evaluations/known/{role}/attempt_000/traces.csv.gz')
        baseline[role]={k[0]:v for k,v in grouped([x for x in raw if eligible(x)],['case_id']).items()}
    for run in range(3):
        for role in ('initial','selected','final'):
            raw=read_csv(SOURCE/f'evaluations/known/n8_run{run}_{role}/attempt_000/traces.csv.gz')
            cases={k[0]:v for k,v in grouped([x for x in raw if eligible(x)],['case_id']).items()}
            for row in [x for x in pairs if int(x['run'])==run and x['role']==role]:
                ts=cases[row['case_id']]
                e=[float(x['error_w']) for x in ts]
                pe=[float(x['error_w']) for x in baseline['pi'][row['case_id']]]
                rm=math.sqrt(math.fsum(x*x for x in e)/128)
                prm=math.sqrt(math.fsum(x*x for x in pe)/128)
                bias=math.fsum(e)/128
                pbias=math.fsum(pe)/128
                dbias=bias*bias-pbias*pbias
                variance=math.fsum((x-bias)**2 for x in e)/128
                pvariance=math.fsum((x-pbias)**2 for x in pe)/128
                for key,value in [('rmse_w',rm),('pi_rmse_w',prm),('delta_pi_rmse_w',rm-prm),
                                  ('delta_pi_bias_squared_w2',dbias),('delta_pi_variance_w2',variance-pvariance)]:
                    residuals.append(abs(value-float(row[key])))
                    assert math.isclose(value,float(row[key]),rel_tol=1e-12,abs_tol=.001)
                assert math.isclose(dbias+variance-pvariance,float(row['delta_pi_mse_w2']),rel_tol=1e-12,abs_tol=.001)
                for x in ts:
                    assert int(x['response_step'])==int(x['decision_step'])+1
                    for i in range(3):
                        pitch=float(x[f'pitch_actual_{i}'])
                        before=float(x[f'pitch_before_{i}'])
                        assert -1e-9<=pitch<=.22+1e-9
                        assert abs(pitch-before)<=.00872664626+1e-9
    history=read_csv(root/'selection_history.csv')
    for run in range(3):
        means={step:statistics.fmean(float(x['rmse_w']) for x in history if int(x['run'])==run and int(x['step'])==step)
               for step in range(0,16385,4096)}
        assert min(means,key=means.get)==cfg['selected_steps'][run]
    # Input filtering and decomposition fixtures exercise the observed historical split trap.
    assert eligible(dict(split='validation',family='low_wind_stress')) is False
    assert eligible(dict(split='test',family='stationary')) is False
    assert eligible(dict(split='train',family='stationary')) is True
    assert eligible(dict(split='validation',family='ramp')) is True
    stats=dict(status='passed',raw_trace_independent_recalculation=True,pair_rows=324,selected_slots=108,
               ordinary_cases=36,ordinary_waveforms=15,selected_worse_pi=11,metric_max_abs_residual=max(residuals),
               exact_validation_selection_reproduced=True,all_cases_retained=True,
               pressure_split_trap_fixture_pass=True,hard_pitch_constraints_pass=True,
               source_hashes_checked=len(cfg['protected_hashes']),formal_rl_steps=0,optimizer_updates=0,
               model_forward_rows=0,environment_steps=0,new_test_released=False)
    write_json(root/'verification.json',stats)
    return stats


def plots(root):
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Microsoft YaHei','DejaVu Sans'],
                         'axes.unicode_minus':False,'font.size':10})
    pairs=read_csv(root/'paired_cases.csv')
    selected=[x for x in pairs if x['role']=='selected']
    cases=list(dict.fromkeys(x['case_id'] for x in selected))
    arr=np.asarray([[float(next(x for x in selected if x['case_id']==c and int(x['run'])==run)['delta_pi_rmse_w'])/1000
                     for run in range(3)] for c in cases])
    fig,ax=plt.subplots(figsize=(10,13))
    lim=float(np.max(np.abs(arr)))
    im=ax.imshow(arr,aspect='auto',cmap='RdBu_r',norm=TwoSlopeNorm(vmin=-lim,vcenter=0,vmax=lim))
    labels=[]
    for c in cases:
        row=next(x for x in selected if x['case_id']==c)
        stem=c.split('_initial_')[0].replace('validation_','val_').replace('_pitch0.04','')
        labels.append(f"{stem} | {float(row['target_w'])/1e6:g} MW | β0={float(row['initial_pitch_rad']):g}")
    ax.set(xticks=range(3),xticklabels=['流0','流1','流2'],yticks=range(len(cases)),yticklabels=labels,
           title='固定n8 selected：同case RMSE减PI（kW）\n18训练+18常规验证；红色较差，压力不参与方案选择')
    ax.tick_params(axis='y',labelsize=8)
    for j in range(36):
        for i in range(3):
            ax.text(i,j,f'{arr[j,i]:+.1f}',ha='center',va='center',fontsize=8,color='white' if abs(arr[j,i])>.6*lim else 'black')
    fig.colorbar(im,ax=ax,label='ΔRMSE (kW)')
    fig.tight_layout();fig.savefig(root/'failure_map.png',dpi=160);plt.close(fig)
    # Representative selection is descriptive and based only on eligible development cases.
    recurrent=[x for x in read_csv(root/'recurrence.csv') if int(x['worse_pi_runs'])>=2]
    representative=max(recurrent,key=lambda x:float(x['mean_delta_pi_rmse_w']))['case_id']
    fig,axes=plt.subplots(3,2,figsize=(15,10),sharex=True)
    colors={'initial':'#999999','selected':'#2864b7','final':'#d89122','pi':'#222222'}
    for run in range(3):
        weather=[x for x in read_csv(SOURCE/'evaluations/known/pi/attempt_000/traces.csv.gz') if x['case_id']==representative]
        wind_axis=axes[run,0].twinx()
        wind_axis.plot([int(x['response_step']) for x in weather],
                       [float(x['response_wind_m_s']) for x in weather],color='#2c9b79',alpha=.22,lw=1)
        wind_axis.set(ylabel='入口风速 (m/s，绿色)',ylim=(7.5,10.5))
        wind_axis.tick_params(axis='y',labelcolor='#2c9b79',labelsize=8)
        for role in ('initial','selected','final','pi'):
            label='pi' if role=='pi' else f'n8_run{run}_{role}'
            ts=[x for x in read_csv(SOURCE/f'evaluations/known/{label}/attempt_000/traces.csv.gz') if x['case_id']==representative]
            t=[int(x['response_step']) for x in ts]
            axes[run,0].plot(t,[float(x['error_w'])/1e6 for x in ts],color=colors[role],ls='--' if role=='final' else '-',label=role)
            actual=[statistics.fmean(float(x[f'pitch_actual_{i}']) for i in range(3)) for x in ts]
            command=[statistics.fmean(float(x[f'pitch_command_{i}']) for i in range(3)) for x in ts]
            axes[run,1].plot(t,actual,color=colors[role],ls='--' if role=='final' else '-',label=role+' actual')
            if role in ('selected','pi'):
                axes[run,1].plot(t,command,color=colors[role],ls=':',alpha=.6,label=role+' command')
        axes[run,0].axhline(0,color='black',lw=.6)
        axes[run,0].set(ylabel='功率误差 (MW)',title=f'流{run}：全128秒')
        axes[run,1].set(ylabel='三机平均桨距 (rad)',title=f'流{run}：目标/实际分开')
        for ax in axes[run]:ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=2)
    for ax in axes[-1]:ax.set_xlabel('响应时刻 (s)')
    fig.suptitle(representative+'\n事后展示训练/验证重复失败；不据此更换父策略，逐机量保留于原始时序')
    fig.tight_layout();fig.savefig(root/'full_failure_timeseries.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,9))
    failed=[x for x in selected if float(x['delta_pi_rmse_w'])>0]
    x=np.arange(len(failed))
    axes[0,0].bar(x,[float(r['delta_pi_bias_squared_w2'])/1e12 for r in failed],label='Δbias²',color='#d18a38')
    axes[0,0].bar(x,[float(r['delta_pi_variance_w2'])/1e12 for r in failed],label='Δvariance',color='#4a83c7')
    axes[0,0].set(xticks=x,xticklabels=[f"r{r['run']}\n{r['case_id'].split('_initial_')[0].replace('train_episode_','tr').replace('validation_ramp_1_pitch0.04','valR')}" for r in failed],
                  ylabel='相对PI的MSE分量 (MW²)',title='11个弱于PI位置：10个偏差增加而方差减少')
    axes[0,0].tick_params(axis='x',labelsize=7)
    axes[0,0].axhline(0,color='black',lw=.6);axes[0,0].legend()
    history=read_csv(root/'selection_history.csv')
    for run in range(3):
        steps=list(range(0,16385,4096))
        means=[statistics.fmean(float(v['rmse_w']) for v in history if int(v['run'])==run and int(v['step'])==step)/1000 for step in steps]
        axes[0,1].plot(steps,means,'o-',label=f'流{run}')
    axes[0,1].set(xlabel='本轮新增学习步',ylabel='18场选模验证RMSE均值 (kW)',title='同天气更新轨迹：流2终点高于父与selected')
    axes[0,1].legend()
    grad=read_csv(root/'replay_gradient.csv')
    params=read_csv(root/'parameter_gradient.csv')
    labels=[]; flips=[]; outside=[];cos=[]
    for run in range(3):
        for role in ('selected','final'):
            g=[r for r in grad if int(r['run'])==run and r['role']==role]
            p=[r for r in params if int(r['run'])==run and r['role']==role]
            labels.append(f'r{run} {role}')
            flips.append(sum(int(r['sign_changed']) for r in g)/sum(int(r['nonflat_points']) for r in g))
            outside.append(statistics.fmean(float(r['outside_neighbor_range_fraction']) for r in g))
            cos.append([float(r['aggregate_parameter_cosine']) for r in p])
    x=np.arange(6)
    axes[1,0].bar(x-.18,flips,.36,label='动作局部梯度变号比例')
    axes[1,0].bar(x+.18,outside,.36,label='当前动作超32近邻坐标范围比例')
    axes[1,0].set(xticks=x,xticklabels=labels,ylabel='相关诊断点比例',title='队友动作条件改变梯度；近邻范围不是密度证明')
    axes[1,0].tick_params(axis='x',labelrotation=20);axes[1,0].legend(fontsize=8)
    for i in range(3):axes[1,1].plot(x,[v[i] for v in cos],'o-',label=f'Actor {i}')
    axes[1,1].axhline(0,color='black',lw=.7)
    axes[1,1].set(xticks=x,xticklabels=labels,ylabel='两种队友条件下参数梯度cosine',ylim=(-1.05,1.05),title='1024点聚合梯度：变号不证明新方向正确')
    axes[1,1].tick_params(axis='x',labelrotation=20);axes[1,1].legend(fontsize=8)
    for ax in axes.flat:ax.grid(axis='y',alpha=.2)
    fig.tight_layout();fig.savefig(root/'decomposition_and_updates.png',dpi=160);plt.close(fig)
    write_json(root/'figure_manifest.json',dict(representative_rule='eligible_recurrent_at_least_2_runs_max_mean_delta_pi_rmse',
                representative_case=representative,files={p.name:sha(p) for p in root.glob('*.png')}))


def finish(root):
    result=verify(root)
    check_sources(root)
    write_json(root/'summary.txt',dict(status='complete',seed=42,formal_rl_steps=0,optimizer_updates=0,model_forward_rows=0,
                environment_steps=0,new_test_released=False,default_policy_changed=False,
                selected_steps=[16384,12288,4096],candidate_implemented=False,
                conclusion='persistent conditional underproduction plus stream-specific forgetting; one actor-context candidate proposed, not validated',
                verification=result,files={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.name!='summary.txt'},
                reproduction_commands=[
                    'python -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_audit prepare --output NEW_DIRECTORY',
                    'python -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_audit trajectories --output NEW_DIRECTORY',
                    'python -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_audit replay --output NEW_DIRECTORY',
                    'python -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_context --output NEW_DIRECTORY',
                    'python -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_remaining_failure_report --output NEW_DIRECTORY']))
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    root=args.output.resolve()
    if not args.verify_only:plots(root)
    finish(root)
