"""Read-only mechanism/retention joins; creates derived CSV, never an environment."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import gzip
import itertools
from pathlib import Path
import json
import statistics
from .pitch_cross_wind_diagnostic import read_csv,write_csv,write_json
from .pitch_nstep_trial import read_json,verify


def run(root):
    import yaml
    root=Path(root).resolve(); cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify(cfg['protected_hashes']);source=Path(cfg['trial'])
    directions=read_csv(root/'metrics.csv')
    index={(r['run'],r['case_id'],r['anchor'],r['variant'],r['continuation'],r['horizon'],r['role']):r for r in directions}
    pairs=[]
    for r in directions:
        if r['role'] not in ('n8_selected','n8_final','n1_selected','n1_final'):continue
        reference='n1_selected' if r['role'].startswith('n8') else 'n1_initial'
        if r['role']=='n8_final':reference='n1_final'
        key=tuple(r[k] for k in ('run','case_id','anchor','variant','continuation','horizon'))
        b=index[(*key,reference)]
        assert r['delta_g']==b['delta_g']
        usable=int(r['usable']) and int(b['usable'])
        left,right=int(b['opposite']),int(r['opposite'])
        pairs.append(dict(role=r['role'],reference=reference,**{k:r[k] for k in ('run','case_id','family','target_w','anchor','variant','continuation','horizon')},
             paired_usable=int(usable),reference_wrong=left,candidate_wrong=right,
             fixed=int(usable and left and not right),introduced=int(usable and right and not left),
             both_local_inside=int(float(r['local_pitch_outside_fraction'])==float(b['local_pitch_outside_fraction'])==0)))
    summaries=[]
    for role,reference,continuation,horizon,run_id in itertools.product(('n8_selected','n8_final','n1_selected','n1_final'),('auto',),('n1_initial','n8_selected'),('8','32'),('all','0','1','2')):
        part=[r for r in pairs if r['role']==role and r['continuation']==continuation and r['horizon']==horizon and (run_id=='all' or r['run']==run_id)]
        usable=[r for r in part if r['paired_usable']]
        inside=[r for r in usable if r['both_local_inside']]
        summaries.append(dict(role=role,reference=part[0]['reference'],continuation=continuation,horizon=horizon,run=run_id,
             paired_usable=len(usable),reference_wrong=sum(r['reference_wrong'] for r in usable),candidate_wrong=sum(r['candidate_wrong'] for r in usable),
             fixed=sum(r['fixed'] for r in usable),introduced=sum(r['introduced'] for r in usable),inside_usable=len(inside),
             inside_reference_wrong=sum(r['reference_wrong'] for r in inside),inside_candidate_wrong=sum(r['candidate_wrong'] for r in inside)))
    write_csv(root/'critic_transition_pairs.csv',pairs);write_csv(root/'critic_transition_summary.csv',summaries)
    grids=[];initial_difference=0.;zero_difference=0.;zero_windows=0;shared_first_pairs=0
    selection=read_json(source/'selection.json');old_trace_cache={}
    for path in sorted((root/'jobs').glob('*/attempt_*/complete.json')):
        verify(read_json(path)['hashes'])
        directory=path.parent;q=read_csv(directory/'q_scores.csv');returns=read_csv(directory/'metrics.csv')
        branches=defaultdict(list)
        with gzip.open(directory/'branches.csv.gz','rt',encoding='utf-8') as f:
            for row in csv.DictReader(f):branches[row['branch_id']].append(row)
        rt={(r['anchor'],r['variant'],r['continuation'],r['horizon']):r for r in returns}
        for anchor,variant in itertools.product(('32','96'),sorted({r['variant'] for r in returns})):
            left=branches[rt[anchor,variant,'n1_initial','32']['branch_id']][0]
            right=branches[rt[anchor,variant,'n8_selected','32']['branch_id']][0]
            for key in ('reward','error_w',*[f'executed_pitch_normalized_{i}' for i in range(3)],*[f'pitch_before_{i}' for i in range(3)]):
                assert left[key]==right[key]
            shared_first_pairs+=1
        for row in read_csv(directory/'own_policy.csv'):
            if row['variant']!='zero' or row['horizon']!='32':continue
            n,state=row['role'].split('_',1);run_id=int(row['run'])
            checkpoint=next(r[state] for r in selection['results'] if r['run']==run_id and r['n']==int(n[1:]))
            cache_key=checkpoint,row['case_id']
            if cache_key not in old_trace_cache:
                with gzip.open(Path(checkpoint).with_name('validation_traces.csv.gz'),'rt',encoding='utf-8') as f:
                    old_trace_cache[cache_key]=[r for r in csv.DictReader(f) if r['case_id']==row['case_id']]
            expected=old_trace_cache[cache_key][int(row['anchor']):int(row['anchor'])+32]
            actual=branches[row['branch_id']]
            assert len(actual)==len(expected)==32
            zero_difference=max(zero_difference,max(abs(float(a['error_w'])-float(b['error_w'])) for a,b in zip(actual,expected)))
            zero_windows+=1
        q_index={(r['anchor'],r['role'],r['variant']):r for r in q}
        for r in q:
            if r['role']=='n1_initial':
                other=q_index[r['anchor'],'n8_initial',r['variant']]
                initial_difference=max(initial_difference,max(abs(float(r[k])-float(other[k])) for k in ('q_0','q_1','q_2','q_mean')))
        for role,anchor,continuation,horizon,head in itertools.product(sorted({r['role'] for r in q}),('32','96'),('n1_initial','n8_selected'),('8','32'),('q_0','q_1','q_2','q_mean')):
            part=[r for r in returns if r['anchor']==anchor and r['continuation']==continuation and r['horizon']==horizon]
            data=[(r['variant'],float(q_index[anchor,role,r['variant']][head]),float(r['discounted_return'])) for r in part]
            usable=discordant=0
            for a,b in itertools.combinations(data,2):
                dq,dg=a[1]-b[1],a[2]-b[2]
                if abs(dq)>1e-5 and abs(dg)>1e-5:
                    usable+=1;discordant+=dq*dg<0
            selected=max(data,key=lambda r:r[1]);best=max(data,key=lambda r:r[2])
            grids.append(dict(run=q[0]['run'],case_id=q[0]['case_id'],family=q[0]['family'],target_w=q[0]['target_w'],
                  role=role,anchor=anchor,continuation=continuation,horizon=horizon,head=head,pairs_usable=usable,pairs_discordant=discordant,
                  q_top_action=selected[0],realized_top_action=best[0],finite_return_regret=best[2]-selected[2]))
    assert initial_difference==0. and zero_difference<=20.
    write_csv(root/'grid_rankings.csv',grids)
    grid_summary=[]
    for role,continuation,horizon,head in itertools.product(sorted({r['role'] for r in grids}),('n1_initial','n8_selected'),('8','32'),('q_0','q_1','q_2','q_mean')):
        part=[r for r in grids if r['role']==role and r['continuation']==continuation and r['horizon']==horizon and r['head']==head]
        grid_summary.append(dict(role=role,continuation=continuation,horizon=horizon,head=head,grids=len(part),
              usable_pairs=sum(r['pairs_usable'] for r in part),discordant_pairs=sum(r['pairs_discordant'] for r in part),
              same_top_action=sum(r['q_top_action']==r['realized_top_action'] for r in part),
              mean_finite_return_regret=statistics.mean(r['finite_return_regret'] for r in part)))
    write_csv(root/'grid_ranking_summary.csv',grid_summary)
    # One role suffices to count realized-return reversals; six Critic copies are correlated.
    reference=[r for r in directions if r['role']=='n1_initial']
    d={(r['run'],r['case_id'],r['anchor'],r['variant'],r['continuation'],r['horizon']):float(r['delta_g']) for r in reference}
    flips=[]
    for r in reference:
        if r['horizon']!='8':continue
        key=tuple(r[k] for k in ('run','case_id','anchor','variant','continuation'))
        g8,g32=float(r['delta_g']),d[(*key,'32')]
        flips.append(dict(**{k:r[k] for k in ('run','case_id','family','target_w','anchor','variant','continuation')},g8=g8,g32=g32,
                          sign_flip=int(abs(g8)>1e-5 and abs(g32)>1e-5 and g8*g32<0)))
    write_csv(root/'horizon_sign_changes.csv',flips)
    retention=[]
    old=read_csv(source/'aggregate.csv');lookup={(r['evaluation'],r['label'],r['family']):r for r in old}
    for run_id,family in itertools.product((0,1,2),('stationary','ramp','gust','routine','low_wind_stress','all_44')):
        part=[lookup['test',f'n8_run{run_id}_{s}',family] for s in ('initial','selected','final')]
        for metric in ('mean_rmse_w','pooled_rmse_w'):
            a,b,c=[float(r[metric]) for r in part]
            retention.append(dict(source='saved_test_no_new_test_rollout',run=run_id,family=family,metric=metric,
                  parent=a,selected=b,final=c,selected_over_parent=b/a,final_over_parent=c/a,final_over_selected=c/b))
    write_csv(root/'retention_audit.csv',retention)
    summary=read_json(root/'summary.txt');handoff=read_json(root/'handoff_validation_replay/summary.txt')
    reserved=sum(json.loads(r)['reserved_steps'] for r in (root/'evaluation_budget.jsonl').read_text().splitlines())
    total=summary['actual_mechanism_steps']+handoff['actual_environment_steps']
    assert total==reserved and total<=65000
    result=dict(seed=42,formal_training_steps=0,new_test_steps=0,actual_mechanism_steps=summary['actual_mechanism_steps'],
          actual_handoff_steps=handoff['actual_environment_steps'],actual_total_environment_steps=total,hard_limit=65000,
          interrupted_uncommitted_reserved_steps=reserved-total,initial_q_arms_max_difference=initial_difference,
          own_zero_windows_verified=zero_windows,maximum_own_zero_trace_error_difference_w=zero_difference,
          common_first_action_and_response_pairs_exact=shared_first_pairs,
          horizon_sign_changes=sum(r['sign_flip'] for r in flips),unique_horizon_comparisons=len(flips),
          protected_files_unchanged=True,parameters_unchanged=True,candidate_manifest_verified=True,
          new_hyperparameters_or_checkpoint_selection=False,default_or_speed_parent_changed=False)
    write_json(root/'final_verification.json',result)
    write_json(root/'summary.txt',dict(summary,actual_handoff_steps=handoff['actual_environment_steps'],
               actual_total_environment_steps=total,conservative_reserved_steps=reserved,
               maximum_possible_uncommitted_steps=reserved-total,handoff_complete=True))
    print(json.dumps(result,indent=2),flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True);run(ap.parse_args().output)


if __name__=='__main__':main()
