"""Three scientific figures from saved data only, with complete 128-step traces."""
from __future__ import annotations
import argparse
from pathlib import Path
import statistics

from .pitch_actor_context_trial import context,read_csv,read_json,js,digest,size,space,ORIGINAL
from .pitch_actor_context_review import latest
from .pitch_gamma_review import trace_location,gz_rows


def figures(root):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    root,s=context(root);space(root,20*1024**2)
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Microsoft YaHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':10})
    history=read_csv(root/'history.csv');known=read_csv(root/'known_metrics.csv')
    colors={'replay':'#3576b5','current_pitch':'#db8227'}
    fig,axes=plt.subplots(2,3,figsize=(15,9))
    sel=read_json(root/'selection.json')
    for run in range(3):
        for arm in ('replay','current_pitch'):
            rows=[r for r in history if r['arm']==arm and int(r['run'])==run]
            axes[0,run].plot([int(r['step']) for r in rows],[float(r['mean_rmse_w'])/1000 for r in rows],'o-',color=colors[arm],label=arm)
            step=next(r['selected_step'] for r in sel['results'] if r['arm']==arm and r['run']==run)
            row=next(r for r in rows if int(r['step'])==step)
            axes[0,run].scatter([step],[float(row['mean_rmse_w'])/1000],marker='*',s=180,color=colors[arm],edgecolor='black',zorder=5)
        axes[0,run].set(title=f'流{run}：新validation选模，星号selected',xlabel='新增环境学习步',ylabel='18场完整RMSE均值 (kW)')
        labels=[];bias=[];variance=[]
        for arm,role,label in [('replay','initial','parent'),('replay','selected','ctrl sel'),('replay','final','ctrl final'),('current_pitch','selected','cand sel'),('current_pitch','final','cand final'),('pi','pi','PI')]:
            part=[r for r in known if r['arm']==arm and int(r['run'])==(run if arm!='pi' else -1) and r['role']==role and r['case_id'].startswith('train_episode_8_')]
            mse=np.mean([float(r['mse_w2']) for r in part]);mean=np.mean([float(r['mean_error_w']) for r in part]);labels.append(label);bias.append(mean**2/1e12);variance.append((mse-mean**2)/1e12)
        x=np.arange(6);axes[1,run].bar(x,bias,label='pooled bias²');axes[1,run].bar(x,variance,bottom=bias,label='pooled variance')
        axes[1,run].set(xticks=x,xticklabels=labels,ylabel='完整MSE分解 (MW²)',title=f'流{run}：已知3.8MW平稳两初态')
        axes[1,run].tick_params(axis='x',labelrotation=25)
        for ax in axes[:,run]:ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('固定单因素：原n8更新 vs 当前队友pitch条件；全部128秒，不裁启动段')
    fig.tight_layout();fig.savefig(root/'validation_and_decomposition.png',dpi=150);plt.close(fig)
    cross=read_csv(root/'test_cross_stream.csv')
    fig,axes=plt.subplots(2,3,figsize=(15,9))
    controls=[('replay','initial','parent'),('replay','selected','ctrl sel'),('replay','final','ctrl final'),('current_pitch','selected','cand sel'),('current_pitch','final','cand final'),('p','p','P'),('pi','pi','PI')]
    for ax,family in zip(axes.flat,('stationary','ramp','gust','routine','low_wind_stress','all_including_pressure')):
        rows=[next(r for r in cross if r['arm']==a and r['role']==role and r['family']==family) for a,role,_ in controls]
        means=[float(r['mean_rmse_w'])/1000 for r in rows];sd=[float(r['sample_sd_across_streams_w'])/1000 if r['sample_sd_across_streams_w'] else 0 for r in rows]
        ax.bar(range(7),means,yerr=sd,capsize=3,color=['#aaaaaa','#79a9d1','#3576b5','#eab477','#db8227','#8e8e8e','#444444'])
        ax.scatter(range(7),[float(r['pooled_rmse_w'])/1000 for r in rows],marker='D',facecolor='white',edgecolor='black',label='pooled RMSE',zorder=4)
        ax.set(title=family,ylabel='完整case-RMSE均值 (kW)',xticks=range(7),xticklabels=[x[2] for x in controls]);ax.tick_params(axis='x',labelrotation=25);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('冻结后一次新测试：误差棒为三训练流样本SD；P/PI为一次共同评估，压力全保留')
    fig.tight_layout();fig.savefig(root/'test_comparison.png',dpi=150);plt.close(fig)
    case='train_episode_8_initial_0.025';fig,axes=plt.subplots(3,2,figsize=(15,10),sharex=True)
    style=[('replay','initial','#999999','parent'),('replay','selected','#74a3ca','ctrl sel'),('replay','final','#2364a0','ctrl final'),('current_pitch','selected','#edb16c','cand sel'),('current_pitch','final','#d27922','cand final'),('pi','pi','#222222','PI')]
    for run in range(3):
        for arm,role,color,label in style:
            folder,_=latest(root,'known','pi' if arm=='pi' else f'{arm}_run{run}_{role}')
            ts=[r for r in gz_rows(trace_location(folder)) if r['case_id']==case];t=[int(r['response_step']) for r in ts]
            axes[run,0].plot(t,[float(r['error_w'])/1e6 for r in ts],color=color,ls='--' if role=='final' else '-',label=label)
            axes[run,1].plot(t,[statistics.fmean(float(r[f'pitch_actual_{i}']) for i in range(3)) for r in ts],color=color,ls='--' if role=='final' else '-',label=label+' actual')
            if (arm,role) in (('current_pitch','selected'),('pi','pi')):
                axes[run,1].plot(t,[statistics.fmean(float(r[f'pitch_command_{i}']) for i in range(3)) for r in ts],color=color,ls=':',alpha=.6,label=label+' command')
            if arm=='pi':
                wa=axes[run,0].twinx();wa.plot(t,[float(r['response_wind_m_s']) for r in ts],color='#36a88c',alpha=.2,lw=1);wa.set(ylabel='入口风速 (m/s，绿色)',ylim=(7.5,10.5));wa.tick_params(axis='y',labelsize=8,labelcolor='#36a88c')
        axes[run,0].axhline(0,color='black',lw=.6);axes[run,0].set(ylabel='功率有符号误差 (MW)',title=f'流{run}：完整128秒')
        axes[run,1].set(ylabel='三机平均pitch (rad)',title=f'流{run}：参考与实际分开，逐机数据保留')
        for ax in axes[run]:ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=2)
    for ax in axes[-1]:ax.set_xlabel('响应时刻 (s)')
    fig.suptitle(case+'；事前固定已知回归代表，非新独立测试')
    fig.tight_layout();fig.savefig(root/'full_timeseries.png',dpi=150);plt.close(fig)
    space(root,0);js(root,root/'figure_manifest.json',dict(source_sha256=digest(__file__),full_timeseries_case=case,complete_steps=128,
        files={p.name:digest(p) for p in root.glob('*.png')},plotting_environment_steps=0,storage_bytes=size(root)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(ORIGINAL/'.venv/pinn_tf216');figures(a.output)
