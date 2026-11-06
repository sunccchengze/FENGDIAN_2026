"""Saved-data metrics, frozen screening gates and scientific plots; no predictor."""
from __future__ import annotations
from collections import defaultdict
import io
import json
import math
from pathlib import Path
import statistics

from .pitch_integral_diagnostic import context,read_csv,read_json,verify,digest,js,table,put,size,LIMIT
from .pitch_gamma_review import gz_rows


def mean(rows,key):return statistics.fmean(float(r[key]) for r in rows)


def groups(rows,keys):
    out=defaultdict(list)
    for r in rows:out[tuple(r[k] for k in keys)].append(r)
    return out


def aggregates(rows):
    result=[]
    for (arm,run,collection),part in groups(rows,('arm','run','collection')).items():
        for family in ('stationary','ramp','gust','all'):
            rs=[r for r in part if family=='all' or r['family']==family]
            result.append(dict(arm=arm,run=run,collection=collection,family=family,slots=len(rs),mean_rmse_w=mean(rs,'rmse_w'),
                pooled_rmse_w=math.sqrt(mean(rs,'mse_w2')),worst_rmse_w=max(float(r['rmse_w']) for r in rs),
                mean_error_w=mean(rs,'mean_error_w'),mean_case_std_w=mean(rs,'error_std_w'),mean_bias_squared_w2=mean(rs,'bias_squared_w2'),
                mean_variance_w2=mean(rs,'variance_w2'),mean_travel_rad=mean(rs,'pitch_travel_rad'),mean_rms_rate_rad_s=mean(rs,'pitch_rms_rate_rad_s')))
    return result


def assess(rows):
    primary=[];gates=[];pi={(r['collection'],r['case_id']):r for r in rows if r['arm']=='pi'}
    chosen=lambda arm,run:[r for r in rows if r['arm']==arm and int(r['run'])==run]
    for run in range(3):
        hybrid=chosen('hybrid',run);parent=chosen('parent',run);baseline={(r['collection'],r['case_id']):r for r in parent}
        c=[r for r in hybrid if r['case_id'].startswith('train_episode_8_')];b=[r for r in parent if r['case_id'].startswith('train_episode_8_')]
        assert len(c)==len(b)==2
        primary.append(dict(run=run,hybrid_rmse_w=mean(c,'rmse_w'),parent_rmse_w=mean(b,'rmse_w'),ratio=mean(c,'rmse_w')/mean(b,'rmse_w')))
        for collection in ('known','validation'):
            for family in ('stationary','ramp','gust'):
                full=[r for r in hybrid if r['collection']==collection and r['family']==family]
                part=[r for r in full if not(collection=='known' and r['case_id'].startswith('train_episode_8_'))]
                base=[baseline[r['collection'],r['case_id']] for r in part];all_base=[baseline[r['collection'],r['case_id']] for r in full]
                mr=mean(part,'rmse_w')/mean(base,'rmse_w');wr=max(float(r['rmse_w']) for r in part)/max(float(r['rmse_w']) for r in base)
                travel=mean(full,'pitch_travel_rad')/max(mean(all_base,'pitch_travel_rad'),1e-4)
                rms=mean(full,'pitch_rms_rate_rad_s')/max(mean(all_base,'pitch_rms_rate_rad_s'),1e-4)
                cf=sum(float(r['rmse_w'])>float(pi[r['collection'],r['case_id']]['rmse_w']) for r in part)
                bf=sum(float(r['rmse_w'])>float(pi[r['collection'],r['case_id']]['rmse_w']) for r in base)
                gates.append(dict(run=run,collection=collection,family=family,retention_slots=len(part),mean_ratio=mr,worst_ratio=wr,
                    retention_pass=mr<=1.05 and wr<=1.05,hybrid_pi_failures=cf,parent_pi_failures=bf,pi_count_pass=cf<=bf,
                    travel_ratio=travel,rms_rate_ratio=rms,motion_pass=travel<=1.10 and rms<=1.10))
    ratio=statistics.fmean(p['hybrid_rmse_w'] for p in primary)/statistics.fmean(p['parent_rmse_w'] for p in primary)
    wins=sum(p['ratio']<1 for p in primary);physical=all(float(r['pitch_min_rad'])>=-1e-9 and float(r['pitch_max_rad'])<=.22+1e-9 and float(r['pitch_max_rate_rad_s'])<=.00872664626+1e-9 for r in rows)
    passes=dict(primary=ratio<=.95 and wins>=2,retention=all(r['retention_pass'] for r in gates),
                pi_count=all(r['pi_count_pass'] for r in gates),motion=all(r['motion_pass'] for r in gates),physical=physical)
    return dict(primary=primary,primary_mean_ratio=ratio,primary_improved_runs=wins,gates=gates,component_pass=passes,passed=all(passes.values()))


def figures(root,rows,refs,cases):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':10})
    def save(fig,name):
        fig.tight_layout();buffer=io.BytesIO();fig.savefig(buffer,format='png',dpi=150);plt.close(fig);put(root,root/name,buffer.getvalue())
    fig,axes=plt.subplots(1,3,figsize=(15,5))
    for run,ax in enumerate(axes):
        bias=[];variance=[]
        for arm in ('parent','hybrid','pi'):
            rs=[r for r in rows if r['arm']==arm and int(r['run'])==(run if arm!='pi' else -1) and r['case_id'].startswith('train_episode_8_')]
            bias.append(mean(rs,'bias_squared_w2')/1e12);variance.append(mean(rs,'variance_w2')/1e12)
        ax.bar(range(3),bias,label='mean case bias²');ax.bar(range(3),variance,bottom=bias,label='mean case variance')
        ax.set(xticks=range(3),xticklabels=['冻结n8','n8+积分','PI'],ylabel='完整MSE分解 (MW²)',title=f'父流{run}：3.8MW平稳，两初态')
        ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
    fig.suptitle('唯一固定积分修正；逐case分解后平均，完整128秒');save(fig,'primary_decomposition.png')
    index={(r['arm'],int(r['run']),r['case_id']):r for r in rows};matrix=np.zeros((54,3))
    for i,c in enumerate(cases):
        for run in range(3):matrix[i,run]=(float(index['hybrid',run,c['id']]['rmse_w'])-float(index['parent',run,c['id']]['rmse_w']))/1000
    vmax=max(abs(matrix.min()),abs(matrix.max()),1.);fig,ax=plt.subplots(figsize=(11,15))
    im=ax.imshow(matrix,aspect='auto',cmap='RdBu_r',norm=TwoSlopeNorm(vmin=-vmax,vcenter=0,vmax=vmax))
    ax.set(xticks=range(3),xticklabels=['父流0','父流1','父流2'],yticks=range(54),yticklabels=[c['collection']+': '+c['id'] for c in cases])
    ax.tick_params(axis='y',labelsize=7);fig.colorbar(im,ax=ax,label='混合−父 RMSE (kW)，负为改善')
    ax.axhline(35.5,color='black',lw=1);ax.set_title('全部54开发槽位×三父；相同波形的不同初态不是独立重复')
    save(fig,'all_case_paired_differences.png')
    case='train_episode_8_initial_0.025';fig,axes=plt.subplots(3,2,figsize=(15,10),sharex=True)
    for run in range(3):
        for arm,color,label in [('parent','#3576b5','冻结n8'),('hybrid','#db8227','n8+积分'),('pi','#222222','PI')]:
            if arm=='hybrid':ts=gz_rows(index[arm,run,case]['trace_path'])
            else:
                source=next(r for r in refs if r['arm']==arm and r['run']==(run if arm=='parent' else -1) and r['collection']=='known')
                ts=[r for r in gz_rows(source['traces']) if r['case_id']==case]
            t=[int(r['response_step']) for r in ts];axes[run,0].plot(t,[float(r['error_w'])/1e6 for r in ts],label=label,color=color)
            axes[run,1].plot(t,[statistics.fmean(float(r[f'pitch_actual_{j}']) for j in range(3)) for r in ts],label=label+' actual',color=color)
            if arm in ('hybrid','pi'):axes[run,1].plot(t,[statistics.fmean(float(r[f'pitch_command_{j}']) for j in range(3)) for r in ts],label=label+' command',color=color,ls=':',alpha=.6)
            if arm=='hybrid':
                extra=axes[run,1].twinx();extra.plot(t,[float(r['integral_used_rad']) for r in ts],color='#9d4eae',ls='--',alpha=.5)
                extra.set(ylabel='积分修正 (rad，紫色)',ylim=(-.025,.025));extra.tick_params(axis='y',labelsize=8,labelcolor='#9d4eae')
            if arm=='pi':
                wind=axes[run,0].twinx();wind.plot(t,[float(r['response_wind_m_s']) for r in ts],color='#36a88c',alpha=.25);wind.set(ylabel='入口风速 (m/s，绿色)',ylim=(7.5,10.5))
                wind.tick_params(axis='y',labelsize=8,labelcolor='#36a88c')
        axes[run,0].set(title=f'父流{run}：完整128秒',ylabel='有符号功率误差 (MW)');axes[run,0].axhline(0,color='black',lw=.5)
        axes[run,1].set(title=f'父流{run}：命令、实际与积分state分开',ylabel='三机平均pitch (rad)')
        for ax in axes[run]:ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=2)
    for ax in axes[-1]:ax.set_xlabel('响应时刻 (s)')
    fig.suptitle('事前固定已知主组代表：'+case+'；没有新独立测试');save(fig,'full_integral_timeseries.png')
    js(root,root/'figure_manifest.json',dict(files={p.name:digest(p) for p in root.glob('*.png')},plotting_plant_rows=0,full_steps=128))


def report(root):
    root,cfg=context(root);complete=read_json(root/'run_complete.json');assert complete['status']=='complete' and complete['config_sha256']==digest(root/'config.yaml')
    cases=read_json(root/'case_manifest.json')['cases'];reference=read_json(root/'reference_reuse.json')['references']
    refs=read_csv(root/'reference_metrics.csv');hybrid=read_csv(root/'hybrid_metrics.csv');rows=refs+hybrid
    assert len(rows)==432 and len(hybrid)==162
    residual=0.;episodes=0
    for path,metrics in [(r['traces'],[m for m in refs if m['arm']==r['arm'] and int(m['run'])==r['run'] and m['collection']==r['collection']]) for r in reference]+[(r['trace_path'],[r]) for r in hybrid]:
        ts=gz_rows(Path(path));gs=groups(ts,('case_id',))
        for m in metrics:
            series=gs[m['case_id'],];assert len(series)==128 and [int(x['response_step']) for x in series]==list(range(1,129))
            errors=[float(x['error_w']) for x in series];mu=math.fsum(errors)/128;mse=math.fsum(x*x for x in errors)/128;var=math.fsum((x-mu)**2 for x in errors)/128
            for key,value in [('rmse_w',math.sqrt(mse)),('mean_error_w',mu),('error_std_w',math.sqrt(var)),('bias_squared_w2',mu*mu),('variance_w2',var)]:
                assert math.isclose(float(m[key]),value,rel_tol=1e-12,abs_tol=.001),(m['case_id'],key)
            residual=max(residual,abs(float(m['rmse_w'])-math.sqrt(mse)))
            for x in series:
                for j in range(3):assert -1e-9<=float(x[f'pitch_actual_{j}'])<=.22+1e-9 and abs(float(x[f'pitch_delta_{j}']))<=.00872664626+1e-9
            episodes+=1
    table(root,root/'metrics.csv',rows);ag=aggregates(rows);table(root,root/'aggregate.csv',ag);paired=[]
    lookup={(r['arm'],int(r['run']),r['collection'],r['case_id']):r for r in refs}
    for r in hybrid:
        for arm in ('parent','p','pi'):
            b=lookup[arm,int(r['run']) if arm=='parent' else -1,r['collection'],r['case_id']]
            paired.append(dict(run=r['run'],collection=r['collection'],case_id=r['case_id'],family=r['family'],wave_sha256=r['wave_sha256'],target_w=r['target_w'],initial_pitch_rad=r['initial_pitch_rad'],reference=arm,
                delta_rmse_w=float(r['rmse_w'])-float(b['rmse_w']),delta_bias_squared_w2=float(r['bias_squared_w2'])-float(b['bias_squared_w2']),delta_variance_w2=float(r['variance_w2'])-float(b['variance_w2']),
                hybrid_rmse_w=r['rmse_w'],reference_rmse_w=b['rmse_w']))
    table(root,root/'paired_cases.csv',paired);strata=[]
    for key,rs in groups(rows,('arm','run','collection','family','target_w','initial_pitch_rad')).items():
        strata.append(dict(zip(('arm','run','collection','family','target_w','initial_pitch_rad'),key),slots=len(rs),rmse_w=mean(rs,'rmse_w'),mean_error_w=mean(rs,'mean_error_w'),mean_case_std_w=mean(rs,'error_std_w'),
                           bias_squared_w2=mean(rs,'bias_squared_w2'),variance_w2=mean(rs,'variance_w2'),travel_rad=mean(rs,'pitch_travel_rad'),rms_rate_rad_s=mean(rs,'pitch_rms_rate_rad_s')))
    table(root,root/'target_initial.csv',strata)
    waves=[dict(wave_sha256=key[0],slots=len(part),collections=','.join(sorted(set(c['collection'] for c in part))),case_ids='|'.join(c['id'] for c in part)) for key,part in groups(cases,('wave_sha256',)).items()]
    table(root,root/'wave_identity.csv',waves);verdict=assess(rows);js(root,root/'acceptance.json',verdict)
    table(root,root/'screening_gates.csv',verdict['gates'])
    all_pi=[]
    for run in range(3):
        for collection in ('known','validation','all'):
            for arm in ('parent','hybrid'):
                rs=[r for r in rows if r['arm']==arm and int(r['run'])==run and (collection=='all' or r['collection']==collection)]
                fails=sum(float(r['rmse_w'])>float(lookup['pi',-1,r['collection'],r['case_id']]['rmse_w']) for r in rs)
                all_pi.append(dict(run=run,collection=collection,arm=arm,slots=len(rs),pi_failures=fails))
    table(root,root/'all_pi_failure_counts.csv',all_pi)
    cross=[]
    for collection in ('known','validation','all'):
        for family in ('stationary','ramp','gust','all'):
            for arm in ('parent','hybrid','p','pi'):
                rs=[r for r in rows if r['arm']==arm and (collection=='all' or r['collection']==collection) and (family=='all' or r['family']==family)]
                per=[mean(part,'rmse_w') for part in groups(rs,('run',)).values()]
                cross.append(dict(collection=collection,family=family,arm=arm,case_mean_rmse_w=statistics.fmean(per),sample_sd_across_parent_streams_w=statistics.stdev(per) if len(per)>1 else '',pooled_rmse_w=math.sqrt(mean(rs,'mse_w2'))))
    table(root,root/'cross_stream.csv',cross);figures(root,rows,reference,cases)
    verify(cfg['protected_hashes']);verify(read_json(root/'input_lock.json')['hashes'])
    ticks=(root/'plant_ticks.bin').read_bytes();assert ticks==b'E'*21285 and len(ticks)+cfg['mock_rows']<=60000 and not list(root.rglob('*.pth'))
    result=dict(status='complete',screening_passed=verdict['passed'],component_pass=verdict['component_pass'],primary_mean_ratio=verdict['primary_mean_ratio'],primary_improved_runs=verdict['primary_improved_runs'],
        formal_training_steps=0,optimizer_updates=0,new_test_steps=0,actual_real_plant_rows=len(ticks),actual_mock_plant_rows=0,engineering_rows=387,hybrid_rows=20898,
        reused_metric_slots=270,hybrid_metric_slots=162,independent_saved_metric_episodes=episodes,max_rmse_recompute_residual_w=residual,
        slots_per_parent=54,unique_waveforms=len(waves),repeated_waveforms_not_independent=True,frozen_sources_unchanged=True,default_changed=False,
        storage_bytes_before_summary=size(root),storage_limit_bytes=LIMIT,config_sha256=digest(root/'config.yaml'))
    js(root,root/'numerical_summary.json',result)
    put(root,root/'summary.txt',('Frozen n8 + bounded integral feasibility diagnosis, seed=42.\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\nFull report: optimization_control/maddpg_wind_farm/PITCH_INTEGRAL_DIAGNOSTIC_RESULTS.md\nCommands: pitch_integral_diagnostic prepare / engineering / run / report --output NEW_DIRECTORY. No training or new independent test.\n').encode('utf8'))
    assert size(root)<LIMIT
    print(result,flush=True)
