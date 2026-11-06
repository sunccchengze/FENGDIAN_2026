"""Paired full-episode attribution and three diagnostic figures, never new policy selection."""
from __future__ import annotations
import argparse
from collections import defaultdict, Counter
from itertools import combinations
from pathlib import Path

from .pitch_reward_alignment import (ACTION, GAMMA, HORIZON, ORIGINAL, activate_runtime, digest,
                                     read_csv, read_json, write_csv, write_json, gz_rows, verify)


def table(path, rows):
    rows=list(rows)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    write_csv(path,({k:r.get(k,'') for k in fields} for r in rows))


def classify(better, worse, has_action=True, tol=1e-6):
    """Orient by full RMSE first, then decompose uniform tracking -> gamma -> action."""
    if better['rmse_w']>worse['rmse_w']:
        better,worse=worse,better
    gap=worse['rmse_w']-better['rmse_w']
    dt=better['tracking_discounted']-worse['tracking_discounted']
    du=better['tracking_uniform']-worse['tracking_uniform']
    out=dict(better_id=better['trajectory_id'],worse_id=worse['trajectory_id'],rmse_gap_w=gap,
             delta_tracking_uniform=du,delta_tracking_discounted=dt,rmse_tie=int(gap<=100.),
             discount_conflict=int(gap>100. and dt < -tol), discount_tie=int(abs(dt)<=tol))
    if gap>100. and du<=0:
        raise ValueError('constant normalization/squared error failed to preserve RMSE ranking')
    if has_action:
        dg=better['return_discounted']-worse['return_discounted']
        da=better['action_discounted']-worse['action_discounted']
        if gap<=100.:
            kind='rmse_tie'
        elif abs(dg)<=tol or abs(dt)<=tol:
            kind='return_tie'
        elif dt>tol and dg < -tol:
            kind='action_created'
        elif dt < -tol and dg>tol:
            kind='action_repaired'
        elif dt < -tol and dg < -tol:
            kind='discount_survives'
        else:
            kind='aligned'
        out.update(delta_action_discounted=da,delta_return_discounted=dg,attribution=kind,
                   total_conflict=int(gap>100. and dg < -tol),
                   action_reinforces_discount=int(gap>100. and dt < -tol and da < -tol),
                   action_partly_repairs_discount=int(gap>100. and dt < -tol and da>tol and dg < -tol),
                   delta_pitch_travel_rad=better['pitch_travel_rad']-worse['pitch_travel_rad'],
                   delta_pitch_rms_rate_rad_s=better['pitch_rms_rate_rad_s']-worse['pitch_rms_rate_rad_s'],
                   delta_command_cost_sum=better['command_cost_sum']-worse['command_cost_sum'])
    else:
        out.update(attribution='tracking_only',total_conflict='',delta_return_discounted='',delta_action_discounted='')
    return out


def numeric(rows):
    keys=('rmse_w','mse_w2','mae_w','tracking_uniform','tracking_discounted','return_uniform','return_discounted',
          'action_discounted','command_cost_sum','pitch_travel_rad','pitch_rms_rate_rad_s','pitch_rate_fraction',
          'native_residual_max','pitch_command_cost_sum','background_command_cost_sum')
    for r in rows:
        for k in keys:
            if r.get(k,'')!='':
                r[k]=float(r[k])
    return rows


def group_rows(rows, keys):
    groups=defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in keys)].append(r)
    return groups


def pair_summary(rows, group, trajectories):
    import numpy as np
    non_ties=[r for r in rows if not r['rmse_tie']]
    full=[r for r in non_ties if r['total_conflict']!='']
    conflict=[r for r in full if r['total_conflict']]
    case=lambda r:(r['run'],r['case_id'])
    tc={case(r) for r in trajectories}; compared={case(r) for r in rows}
    dc={case(r) for r in non_ties if r['discount_conflict']}
    cc={case(r) for r in conflict}
    def mean(key, subset):
        return float(np.mean([r[key] for r in subset])) if subset else 0.
    return dict(**group,unique_trajectories=len(trajectories),case_slots=len(tc),compared_case_slots=len(compared),all_pairs=len(rows),
                rmse_non_tie_pairs=len(non_ties),discount_conflicts=sum(r['discount_conflict'] for r in non_ties),
                discount_conflict_cases=len(dc),full_reward_pairs=len(full),
                total_conflicts=len(conflict),total_conflict_cases=len(cc),
                action_created=sum(r['attribution']=='action_created' for r in non_ties),
                action_repaired=sum(r['attribution']=='action_repaired' for r in non_ties),
                discount_survives=sum(r['attribution']=='discount_survives' for r in non_ties),
                discount_reinforced=sum(r.get('action_reinforces_discount',0) for r in non_ties),
                discount_partly_repaired=sum(r.get('action_partly_repairs_discount',0) for r in non_ties),
                conflict_gap_mean_w=mean('rmse_gap_w',conflict),
                conflict_gap_max_w=max([r['rmse_gap_w'] for r in conflict],default=0.),
                conflict_delta_travel_mean_rad=mean('delta_pitch_travel_rad',conflict),
                conflict_delta_rms_rate_mean_rad_s=mean('delta_pitch_rms_rate_rad_s',conflict),
                conflict_delta_command_cost_mean=mean('delta_command_cost_sum',conflict))


def preferences(rows):
    """Finite realized-trajectory menu only; this is not a deployable case oracle."""
    out=[]
    for key,group in group_rows(rows,('source','run','case_id')).items():
        best=min(group,key=lambda r:(r['rmse_w'],r['trajectory_id']))
        scores=['tracking_uniform','tracking_discounted']
        if group[0].get('return_discounted','')!='':
            scores+=['return_uniform','return_discounted']
        for score in scores:
            preferred=max(group,key=lambda r:(r[score],-float(r['trajectory_id'][1:])))
            out.append(dict(source=key[0],run=key[1],case_id=key[2],split=best['split'],family=best['family'],
                            target_w=best['target_w'],initial_pitch_rad=best['initial_pitch_rad'],score=score,
                            preferred_id=preferred['trajectory_id'],rmse_best_id=best['trajectory_id'],
                            preferred_rmse_w=preferred['rmse_w'],rmse_best_w=best['rmse_w'],
                            regret_w=preferred['rmse_w']-best['rmse_w'],
                            delta_pitch_travel_rad=preferred['pitch_travel_rad']-best['pitch_travel_rad'],
                            delta_pitch_rms_rate_rad_s=preferred['pitch_rms_rate_rad_s']-best['pitch_rms_rate_rad_s']))
    return out


def review(root):
    import numpy as np
    import yaml
    root=Path(root).resolve(); cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify(cfg['protected_hashes']); verify(read_json(root/'collection.json')['files'])
    rows=numeric(read_csv(root/'trajectory_metrics.csv')); pairs=[]
    # Preserve the original stored split; the protocol requires pressure to be reported separately.
    for r in rows:
        r['recorded_split']=r['split']
        if r['family']=='low_wind_stress':
            r['split']='stress'
    for key,group in group_rows(rows,('source','run','case_id')).items():
        for a,b in combinations(group,2):
            pairs.append(dict(source=key[0],run=key[1],case_id=key[2],split=a['split'],family=a['family'],
                    target_w=a['target_w'],initial_pitch_rad=a['initial_pitch_rad'],
                    **classify(a,b,a.get('return_discounted','')!='')))
    table(root/'pairs.csv',pairs)
    summaries=[]
    for dimension in (('source',),('source','split'),('source','split','family'),('source','split','target_w'),
                      ('source','split','initial_pitch_rad'),('source','split','run')):
        for key,group in group_rows(pairs,dimension).items():
            identity=dict(zip(dimension,key))
            matching=[r for r in rows if all(r[k]==v for k,v in identity.items())]
            summaries.append(dict(grouping='/'.join(dimension),**pair_summary(group,identity,matching)))
    table(root/'metrics.csv',summaries)
    pref=preferences(rows); table(root/'finite_menu_preferences.csv',pref)
    prefs=[]
    for dimension in (('source','score'),('source','split','score'),('source','split','family','score'),('source','split','run','score')):
        for key,group in group_rows(pref,dimension).items():
            prefs.append(dict(grouping='/'.join(dimension),**dict(zip(dimension,key)),case_slots=len(group),
                    regret_cases=sum(r['regret_w']>100 for r in group),
                    regret_mean_w=float(np.mean([r['regret_w'] for r in group])),
                    regret_max_w=max(r['regret_w'] for r in group),
                    preferred_minus_rmse_best_travel_mean_rad=float(np.mean([r['delta_pitch_travel_rad'] for r in group])),
                    preferred_minus_rmse_best_rate_mean_rad_s=float(np.mean([r['delta_pitch_rms_rate_rad_s'] for r in group]))))
    table(root/'preference_groups.csv',prefs)
    # Compare fixed semantic roles with each other, preserving the three streams as the replication unit.
    roles=read_csv(root/'trajectory_roles.csv'); lookup={r['trajectory_id']:r for r in rows}; role_metrics=[]
    for r in roles:
        if r['family']=='low_wind_stress':
            r['split']='stress'
    for key,group in group_rows(roles,('source','role','run','split','family')).items():
        values=[lookup[r['trajectory_id']] for r in group]
        role_metrics.append(dict(source=key[0],role=key[1],run=key[2],split=key[3],family=key[4],cases=len(values),
                 mean_case_rmse_w=float(np.mean([r['rmse_w'] for r in values])),
                 pooled_rmse_w=float(np.sqrt(np.mean([r['mse_w2'] for r in values]))),
                 tracking_discounted_mean=float(np.mean([r['tracking_discounted'] for r in values])),
                 mean_pitch_travel_rad=float(np.mean([r['pitch_travel_rad'] for r in values])),
                 mean_pitch_rms_rate_rad_s=float(np.mean([r['pitch_rms_rate_rad_s'] for r in values]))))
    table(root/'role_groups.csv',role_metrics)
    counts=Counter(r['source'] for r in rows); semantic=Counter(r['source'] for r in roles)
    reward_rows=[r for r in rows if r.get('return_discounted','')!='']
    d=GAMMA**np.arange(HORIZON)
    result=dict(seed=42,status='audit_complete',formal_training_steps=0,
                actual_environment_steps=read_json(root/'supplement.json')['actual_environment_steps'],
                reserved_environment_steps=sum(__import__('json').loads(s)['reserved_steps'] for s in (root/'evaluation_budget.jsonl').read_text(encoding='utf-8').splitlines()),
                unique_trajectory_counts=dict(counts),semantic_trajectory_counts=dict(semantic),all_pairs=len(pairs),
                max_native_reward_residual=max(r['native_residual_max'] for r in reward_rows),
                time_weight=dict(last_over_first=float(d[-1]),first32_share=float(d[:32].sum()/d.sum()),last32_share=float(d[-32:].sum()/d.sum())),
                source_summaries=[s for s in summaries if s['grouping']=='source'],
                source_split_summaries=[s for s in summaries if s['grouping']=='source/split'],
                average_background_cost_share=float(sum(r['background_command_cost_sum'] for r in reward_rows)/sum(r['command_cost_sum'] for r in reward_rows)),
                no_test_selection=True,offline_rescoring_is_not_retraining=True)
    write_json(root/'audit.json',result)
    figures(root,rows,pairs,pref)
    outputs=[p for p in root.iterdir() if p.is_file() and p.name not in ('summary.txt',)]
    result['hashes']={str(p.resolve()):digest(p) for p in outputs}
    verify(cfg['protected_hashes']); write_json(root/'summary.txt',result)
    print(__import__('json').dumps({k:v for k,v in result.items() if k not in ('hashes',)}),flush=True)


def figures(root,rows,pairs,pref):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'figure.dpi':140})
    sources=['action_full','nstep_training','nstep_validation_reward','nstep_validation_tracking']
    names=['Parent + fixed pitch offsets','n1/n8 training behavior','Frozen validation roles','All validation snapshots']
    fig,axes=plt.subplots(1,3,figsize=(15,4.6),constrained_layout=True)
    colors={'discount_survives':'#d95f02','action_created':'#7570b3','action_repaired':'#1b9e77'}
    x=np.arange(4); bottom=np.zeros(4)
    for category,color in colors.items():
        values=[]
        for source in sources:
            sample=[r for r in pairs if r['source']==source and not r['rmse_tie']]
            values.append(100*sum(r['attribution']==category or (source==sources[-1] and category=='discount_survives' and r['discount_conflict']) for r in sample)/len(sample))
        axes[0].barh(x,values,left=bottom,color=color,label=category.replace('_',' ')); bottom+=values
    axes[0].set_yticks(x,names); axes[0].invert_yaxis(); axes[0].set_xlabel('% of non-tie pairs'); axes[0].legend(fontsize=8)
    axes[0].set_title('Rank attribution (last row: tracking only)')
    for i,score in enumerate(('tracking_discounted','return_discounted','return_uniform')):
        values=[np.mean([r['regret_w'] for r in pref if r['source']==s and r['score']==score])/1000
                if any(r['source']==s and r['score']==score for r in pref) else np.nan for s in sources]
        axes[1].bar(x+(i-1)*.24,values,width=.24,label=score.replace('_',' '))
    axes[1].set_xticks(x,['Offsets','Train','Val roles','Val all']); axes[1].set_ylabel('Mean finite-menu RMSE regret (kW)')
    axes[1].set_title('Retrospective preference loss'); axes[1].legend(fontsize=8)
    d=GAMMA**np.arange(128); axes[2].plot(np.arange(1,129),d,label='gamma = .99')
    axes[2].axhline(1,color='gray',ls='--',label='uniform RMSE weight'); axes[2].set_xlabel('Response time (s)')
    axes[2].set_ylabel('Relative tracking weight'); axes[2].set_title('Discount within a complete episode'); axes[2].legend()
    fig.savefig(root/'attribution.png'); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11.8,4.5),constrained_layout=True)
    for family,color in [('stationary','#1b9e77'),('ramp','#d95f02'),('gust','#7570b3'),('low_wind_stress','#666666')]:
        subset=[r for r in pref if r['source']=='action_full' and r['score']=='return_discounted' and r['family']==family]
        if subset:
            axes[0].scatter([r['regret_w']/1000 for r in subset],[r['delta_pitch_travel_rad'] for r in subset],s=18,alpha=.65,label=family,c=color)
    axes[0].set_xlabel('Original reward preference: RMSE regret (kW)'); axes[0].set_ylabel('Preferred minus RMSE-best pitch travel (rad, 3 units)')
    axes[0].axhline(0,color='gray',lw=.7); axes[0].legend(); axes[0].set_title('Complete offset menu; all 132 case slots')
    for source,color in zip(sources[:3],('#1b9e77','#d95f02','#7570b3')):
        subset=[r for r in pairs if r['source']==source and r.get('total_conflict')==1]
        axes[1].scatter([r['rmse_gap_w']/1000 for r in subset],[r['delta_pitch_travel_rad'] for r in subset],s=12,alpha=.4,label=source,c=color)
    axes[1].set_xlabel('Reward-favored worse trajectory: RMSE loss (kW)')
    axes[1].set_ylabel('RMSE-better minus worse pitch travel (rad)'); axes[1].axhline(0,color='gray',lw=.7)
    axes[1].set_title('All opposing pairs; negative = accuracy + less travel'); axes[1].legend(fontsize=8)
    fig.savefig(root/'tracking_motion_cost.png'); plt.close(fig)
    lookup={r['trajectory_id']:r for r in rows}; chosen=[]
    # Fixed rule: largest robust routine validation gap in each attribution, from the full offset source.
    for kind in ('action_created','discount_survives'):
        subset=[r for r in pairs if r['source']=='action_full' and r['split']=='validation' and r['attribution']==kind]
        if subset:
            chosen.append(max(subset,key=lambda r:(r['rmse_gap_w'],r['case_id'],r['better_id'])))
    if not chosen:
        raise ValueError('expected explanatory examples absent; report before changing figure rule')
    table(root/'examples.csv',chosen)
    fig,axes=plt.subplots(len(chosen),3,figsize=(15,3.6*len(chosen)),squeeze=False,constrained_layout=True)
    for i,p in enumerate(chosen):
        job=next(j for j in read_json(ACTION/'jobs.json') if str(j['run_id'])==p['run'] and j['case_id']==p['case_id'])
        allrows=gz_rows(Path(job['path'])/'full_trajectories.csv.gz'); traces=[]
        for identity in ('better_id','worse_id'):
            m=lookup[p[identity]]; traces.append([r for r in allrows if r['variant']==m['representative']])
        t=np.arange(1,129); d=GAMMA**np.arange(128)
        for r,color,label in zip(traces,('#1b9e77','#d95f02'),('RMSE better','RMSE worse / reward favored')):
            axes[i,0].plot(t,[float(a['error_w'])/1000 for a in r],c=color,label=label)
            axes[i,2].plot(t,np.mean([[float(a[f'pitch_actual_{j}']) for j in range(3)] for a in r],axis=1),c=color,label=label)
            axes[i,2].plot(t,np.mean([[float(a[f'pitch_command_{j}']) for j in range(3)] for a in r],axis=1),c=color,ls=':',lw=.9)
        for field,color,label in [('tracking_reward','#377eb8','tracking discounted'),('action_reward','#984ea3','action discounted'),('reward','#222222','native total discounted')]:
            delta=np.array([float(a[field])-float(b[field]) for a,b in zip(*traces)])
            axes[i,1].plot(t,np.cumsum(d*delta),c=color,label=label)
        axes[i,0].set_title(f"{p['attribution']}; {p['family']}; run {p['run']}; {float(p['target_w'])/1e6:g} MW")
        axes[i,0].set_ylabel('Signed power error (kW)'); axes[i,0].axhline(0,color='gray',lw=.6)
        axes[i,1].set_title(f"Better minus worse return; RMSE gap {p['rmse_gap_w']/1000:.1f} kW")
        axes[i,1].axhline(0,color='gray',lw=.6); axes[i,1].set_ylabel('Cumulative return difference')
        axes[i,2].set_title('Three-unit mean pitch\ncommand dotted / actual solid'); axes[i,2].set_ylabel('Pitch (rad)')
        for ax in axes[i]:
            ax.set_xlabel('Response time (s), all 128 steps'); ax.legend(fontsize=8)
    fig.savefig(root/'full_episode_examples.png'); plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',required=True); args=p.parse_args()
    activate_runtime(ORIGINAL/'.venv/pinn_tf216'); review(args.output)


if __name__=='__main__':
    main()
