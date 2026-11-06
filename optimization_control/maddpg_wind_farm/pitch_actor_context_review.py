"""Frozen pretest audit, paired complete-case metrics and sparse-state delivery."""
from __future__ import annotations
import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path

from .pitch_actor_context_trial import (ARMS,FAMILIES,OLD,context,read_json,read_csv,verify,digest,js,table,
    size,episode_metrics,fingerprint,entropy,json_state,known_cases)
from .pitch_gamma_review import aggregates,metric_check,trace_location,gz_rows


def latest(root,split,label):
    p=sorted((root/'evaluations'/split/label).glob('attempt_*/complete.json'))[-1]
    d=read_json(p);verify(d['hashes']);return p.parent,d


def collect(root,split):
    rows=[];selection=read_json(root/'selection.json')
    for r in selection['results']:
        for role in ('initial','selected','final'):
            p=Path(r[role]).with_name('validation_metrics.csv') if split=='validation' else latest(root,split,f'{r["arm"]}_run{r["run"]}_{role}')[0]/'metrics.csv'
            rows.extend(dict(arm=r['arm'],run=r['run'],role=role,**x) for x in read_csv(p))
    for b in ('p','pi'):
        p,_=latest(root,split,b);rows.extend(dict(arm=b,run=-1,role=b,**x) for x in read_csv(p/'metrics.csv'))
    return rows


def summarize(root,split,rows):
    import numpy as np
    ag=aggregates(rows);table(root,root/f'{split}_aggregate.csv',ag)
    lookup={(r['arm'],int(r['run']),r['role'],r['case_id']):r for r in rows};paired=[]
    for r in rows:
        if r['arm'] not in ARMS or r['role']=='initial':continue
        for a,role,ref in [('replay',r['role'],'control'),('replay','initial','parent'),('p','p','p'),('pi','pi','pi')]:
            b=lookup[a,int(r['run']) if a in ARMS else -1,role,r['case_id']]
            paired.append(dict(arm=r['arm'],run=r['run'],role=r['role'],case_id=r['case_id'],split=r['split'],family=r['family'],
                target_w=r['target_w'],initial_pitch_rad=r['initial_pitch_rad'],reference=ref,
                candidate_rmse_w=float(r['rmse_w']),reference_rmse_w=float(b['rmse_w']),delta_rmse_w=float(r['rmse_w'])-float(b['rmse_w'])))
    table(root,root/f'{split}_paired_cases.csv',paired)
    cross=[];comparison=[];strata=[]
    families=(*FAMILIES,'routine')+(('low_wind_stress','all_including_pressure') if split=='test' else ())
    for arm in (*ARMS,'p','pi'):
        for role in (('initial','selected','final') if arm in ARMS else (arm,)):
            for family in families:
                part=[r for r in ag if r['arm']==arm and r['role']==role and r['family']==family]
                cross.append(dict(arm=arm,role=role,family=family,streams=len(part),
                    mean_rmse_w=float(np.mean([r['mean_rmse_w'] for r in part])),
                    sample_sd_across_streams_w=float(np.std([r['mean_rmse_w'] for r in part],ddof=1)) if len(part)>1 else '',
                    pooled_rmse_w=float(np.sqrt(np.mean([r['pooled_rmse_w']**2 for r in part])))))
    expanded=[]
    for r in paired:
        expanded.append(r)
        if r['split']!='stress':expanded.append(dict(r,family='routine'))
        if split=='test':expanded.append(dict(r,family='all_including_pressure'))
    for (arm,role,family,ref),part in _groups(expanded,('arm','role','family','reference')).items():
        means=[float(np.mean([r['delta_rmse_w'] for r in part if int(r['run'])==run])) for run in range(3)]
        comparison.append(dict(arm=arm,role=role,family=family,reference=ref,slots=len(part),mean_delta_rmse_w=float(np.mean(means)),
            sample_sd_delta_w=float(np.std(means,ddof=1)),strictly_better_slots=sum(r['delta_rmse_w']<0 for r in part),
            ratio_of_case_means=sum(r['candidate_rmse_w'] for r in part)/sum(r['reference_rmse_w'] for r in part)))
    for key,part in _groups(rows,('arm','role','family','target_w','initial_pitch_rad')).items():
        means=[np.mean([float(r['rmse_w']) for r in part if int(r['run'])==run]) for run in sorted(set(int(r['run']) for r in part))]
        strata.append(dict(arm=key[0],role=key[1],family=key[2],target_w=key[3],initial_pitch_rad=key[4],slots=len(part),
            mean_rmse_w=float(np.mean(means)),sample_sd_w=float(np.std(means,ddof=1)) if len(means)>1 else '',
            mean_error_w=float(np.mean([float(r['mean_error_w']) for r in part])),mean_case_std_w=float(np.mean([float(r['error_std_w']) for r in part]))))
    table(root,root/f'{split}_cross_stream.csv',cross);table(root,root/f'{split}_comparisons.csv',comparison);table(root,root/f'{split}_target_initial.csv',strata)


def _groups(rows,keys):
    result=defaultdict(list)
    for r in rows:result[tuple(r[k] for k in keys)].append(r)
    return result


def validate_bank(root,s,split):
    """Bind saved banks to the predeclared seed/grid without any Plant query."""
    import numpy as np
    from .pitch_nstep_trial import wind
    from ..environments.farm_inflow import InflowTrace
    manifest=read_json(root/f'{split}_bank/manifest.json');verify(manifest['hashes']);expected={}
    targets=(2.9e6,3.5e6) if split=='validation' else (2725000.,3325000.,3925000.)
    pitches=(.025,.04,.055) if split=='validation' else (.03,.05)
    for fi,family in enumerate(FAMILIES):
        for ti,target in enumerate(targets):
            for repeat in range(1 if split=='validation' else 2):
                episode=(62000000 if split=='validation' else 63000000)+fi*100+ti*10+repeat
                values=wind(s['base_config'],family,split,episode).values
                for pitch in pitches:expected[f'{split}_{family}_t{target:g}_r{repeat}_p{pitch}']=(family,target,pitch,episode,values)
    if split=='test':
        for wi,speed in enumerate((7.6,7.8)):
            values=np.tile([speed,0.,.08],(129,1))
            for target in (4.35e6,4.55e6):
                for pitch in pitches:expected[f'pressure_w{speed}_t{target:g}_p{pitch}']=('low_wind_stress',target,pitch,63009000+wi,values)
    assert len(manifest['cases'])==len(expected)==(18 if split=='validation' else 44)
    for c in manifest['cases']:
        family,target,pitch,episode,values=expected[c['id']]
        assert c['family']==family and c['target_w']==target and c['initial_pitch_rad']==pitch and c['episode']==episode
        assert np.array_equal(InflowTrace.load(c['path']).values,values)
    return {k:v[-1].astype(np.float32) for k,v in expected.items()}


def gates(rows,exclude_primary=False):
    """Per-stream/per-family retention, PI failures, stability and actual motion."""
    import numpy as np
    pairs=[];failures=[];motion=[];stability=[];physical=True
    for run in range(3):
        for role in ('selected','final'):
            candidate=[r for r in rows if r['arm']=='current_pitch' and int(r['run'])==run and r['role']==role and r['split']!='stress']
            pi={r['case_id']:r for r in rows if r['arm']=='pi'}
            for family in FAMILIES:
                original=[r for r in candidate if r['family']==family]
                chosen=[r for r in original if not(exclude_primary and r['case_id'].startswith('train_episode_8_'))]
                for ref,rr in [('control',role),('parent','initial')]:
                    baseline={r['case_id']:r for r in rows if r['arm']=='replay' and int(r['run'])==run and r['role']==rr}
                    c=[float(r['rmse_w']) for r in chosen];b=[float(baseline[r['case_id']]['rmse_w']) for r in chosen]
                    mean_ratio=float(np.mean(c)/np.mean(b));worst_ratio=max(c)/max(b)
                    pairs.append(dict(run=run,role=role,family=family,reference=ref,mean_ratio=mean_ratio,worst_ratio=worst_ratio,passed=mean_ratio<=1.05 and worst_ratio<=1.05))
                    for split in sorted(set(r['split'] for r in chosen)):
                        subset=[r for r in chosen if r['split']==split]
                        cf=sum(float(r['rmse_w'])>float(pi[r['case_id']]['rmse_w']) for r in subset)
                        bf=sum(float(baseline[r['case_id']]['rmse_w'])>float(pi[r['case_id']]['rmse_w']) for r in subset)
                        failures.append(dict(run=run,role=role,family=family,split=split,reference=ref,candidate_failures=cf,reference_failures=bf,passed=cf<=bf))
                baseline={r['case_id']:r for r in rows if r['arm']=='replay' and int(r['run'])==run and r['role']==role}
                travel=np.mean([float(r['pitch_travel_rad']) for r in original])/max(np.mean([float(baseline[r['case_id']]['pitch_travel_rad']) for r in original]),1e-4)
                rms=np.mean([float(r['pitch_rms_rate_rad_s']) for r in original])/max(np.mean([float(baseline[r['case_id']]['pitch_rms_rate_rad_s']) for r in original]),1e-4)
                motion.append(dict(run=run,role=role,family=family,travel_ratio=float(travel),rms_rate_ratio=float(rms),passed=bool(travel<=1.10 and rms<=1.10)))
            if role=='final':
                selected=[r for r in rows if r['arm']=='current_pitch' and int(r['run'])==run and r['role']=='selected' and r['split']!='stress']
                ratio=np.mean([float(r['rmse_w']) for r in candidate])/np.mean([float(r['rmse_w']) for r in selected])
                refs=[]
                for rr in ('initial','final'):
                    base=[r for r in rows if r['arm']=='replay' and int(r['run'])==run and r['role']==rr and r['split']!='stress']
                    refs.extend([np.mean([float(r['rmse_w']) for r in candidate])/np.mean([float(r['rmse_w']) for r in base])<=1.05,
                                 max(float(r['rmse_w']) for r in candidate)/max(float(r['rmse_w']) for r in base)<=1.05])
                stability.append(dict(run=run,final_over_selected=float(ratio),passed=bool(ratio<=1.25 and all(refs))))
    for r in rows:
        physical &= float(r['pitch_min_rad'])>=-1e-9 and float(r['pitch_max_rad'])<=.22+1e-9 and float(r['pitch_max_rate_rad_s'])<=.00872664626+1e-9
    return dict(retention=pairs,pi_failure_counts=failures,motion=motion,stability=stability,physical_pass=bool(physical),
        retention_pass=all(x['passed'] for x in pairs),pi_count_pass=all(x['passed'] for x in failures),
        motion_pass=all(x['passed'] for x in motion),stability_pass=all(x['passed'] for x in stability))


def verdict(root,known,validation):
    import numpy as np
    selection=read_json(root/'selection.json');primary=[]
    for role in ('selected','final'):
        candidate=[]
        for ref,rr in [('control',role),('parent','initial')]:
            cm=[];bm=[]
            for run in range(3):
                c=[float(r['rmse_w']) for r in known if r['arm']=='current_pitch' and int(r['run'])==run and r['role']==role and r['case_id'].startswith('train_episode_8_')]
                b=[float(r['rmse_w']) for r in known if r['arm']=='replay' and int(r['run'])==run and r['role']==rr and r['case_id'].startswith('train_episode_8_')]
                assert len(c)==len(b)==2;cm.append(np.mean(c));bm.append(np.mean(b))
            ratio=float(np.mean(cm)/np.mean(bm));improved=sum(c<b for c,b in zip(cm,bm))
            primary.append(dict(role=role,reference=ref,ratio=ratio,improved_runs=improved,passed=ratio<=.95 and improved>=2))
    kg,vg=gates(known,True),gates(validation)
    learned=sum(r['selected_step']>0 for r in selection['results'] if r['arm']=='current_pitch')
    passed=learned==3 and all(x['passed'] for x in primary) and all(g[k] for g in (kg,vg) for k in ('retention_pass','pi_count_pass','motion_pass','stability_pass','physical_pass'))
    return dict(primary=primary,new_learning_runs=learned,known=kg,validation=vg,passed=bool(passed),test_cannot_revise_validation=True)


def pretest(root):
    import numpy as np
    import torch
    root,s=context(root);selection=read_json(root/'selection.json')
    assert not (root/'test_bank').exists() and selection['config_sha256']==digest(root/'config.yaml')
    verify(read_json(root/'engineering.json')['hashes']);verify(read_json(root/'data_lock.json')['hashes'])
    validation_winds=validate_bank(root,s,'validation')
    for filename,source in [('reporting_tests.json','test_pitch_actor_context_reporting.py'),('bounds_tests.json','test_pitch_actor_context_bounds.py')]:
        proof=read_json(root/filename)
        assert proof['status']=='passed' and proof['tests']==2 and proof['plant_rows']==0 and proof['optimizer_updates']==0
        assert proof['source_sha256']==digest(Path(__file__).parents[1]/'tests'/source)
    designs={(int(r['run']),int(r['episode_index'])):r for r in read_csv(root/'training_manifest.csv')}
    states=read_json(root/'random_states.json');updates=0;fulls=[];light=[];hist=[];train_metrics=[];paired={};residual=0.
    for arm in ARMS:
        for run in range(3):
            job=root/f'{arm}_run{run}';commits=sorted(job.glob('step_*/attempt_*/commit.json'));assert len(commits)==129
            parent=s['parents'][str(run)];loss_stream=[];noise=np.load(root/f'noise_run{run}.npz')['noise']
            for p in commits:
                c=read_json(p);verify(c['hashes']);step=c['step'];expected=0 if step<512 else (step-512)//2+1
                assert c['updates']==parent['updates']+expected and c['replay_insertions']==parent['insertions']+step
                if c['checkpoint']:
                    saved=torch.load(c['checkpoint'],map_location='cpu',weights_only=False);meta=saved['metadata']
                    assert saved['version']=='pitch_actor_context_v1' and saved['actor_teammates']==arm and saved['n']==8 and saved['config']['gamma']==.99
                    assert meta['step']==step and meta['episode']==step//128 and meta['config']==s['base_config'] and meta['root_config_sha256']==digest(root/'config.yaml')
                    assert saved['replay']['insertions']==parent['insertions']+step
                    assert saved['replay']['size']==min(32768,parent['replay_size']+step) and saved['replay']['position']==(parent['replay_position']+step)%32768
                    assert sum(saved['replay']['m_histogram'])-sum(parent['m_histogram'])==expected*64
                    if step==0:
                        from .pitch_actor_context_algorithm import NETS,OPTIMIZERS
                        core=dict(config=saved['config'],n=8,replay_gamma=.99,networks={k:saved[k] for k in NETS},
                                  optimizers={k:saved[k] for k in OPTIMIZERS},replay=saved['replay'],rng=saved['rng'],torch_rng=saved['torch_rng'],updates=saved['updates'])
                        assert fingerprint(core)==parent['initial_state_fingerprint']
                    if step:
                        assert json_state(meta['noise'])==states[run]['episodes'][step//128-1]['after']
                    fulls.append(dict(arm=arm,run=run,step=step,checkpoint=c['checkpoint'],sha256=digest(c['checkpoint']),bytes=Path(c['checkpoint']).stat().st_size,
                                      added_updates=expected,insertions=saved['replay']['insertions'],m_histogram=json.dumps(saved['replay']['m_histogram'].tolist())))
                light.append(dict(arm=arm,run=run,step=step,commit=str(p),checkpoint=c['checkpoint'],sha256=digest(p)))
                if step:
                    ep=step//128-1;d=designs[run,ep]
                    from ..environments.farm_inflow import InflowTrace
                    weather=InflowTrace.load(d['path']).values
                    with np.load(p.with_name('training.npz')) as z:
                        assert z['obs'].shape==(128,3,15) and np.array_equal(z['next_obs'][:-1],z['obs'][1:]) and np.array_equal(z['actions'][:-1],z['obs'][1:,:,5:8])
                        assert np.array_equal(z['terminated'][:,0],[False]*127+[True]) and np.array_equal(z['exploration'],noise[ep])
                        assert np.array_equal(z['wind'],weather[1:].astype(np.float32))
                        cost=np.mean((z['actions']-z['obs'][:,:,5:8])**2,axis=(1,2))
                        delta=float(np.abs(z['rewards'][:,0]-100*(-(z['error_w']/15e6)**2-.001*cost)).max());residual=max(residual,delta);assert delta<=5e-6
                        before=np.vstack((np.full((1,3),float(d['initial_pitch_rad'])),z['applied'][:-1,:,1]))
                        assert z['applied'][:,:,1].min()>=-1e-9 and z['applied'][:,:,1].max()<=.22+1e-9 and np.abs(z['applied'][:,:,1]-before).max()<=.00872664626+1e-9
                    ls=[x for x in read_csv(p.with_name('losses.csv')) if 'step' in x]
                    loss_stream.extend([(int(x['step']),x['sample_indices_sha256'],x['m_mean'],x['m_min'],x['m_max']) for x in ls]);updates+=len(ls)
                    train_metrics.append(dict(arm=arm,run=run,episode_index=ep,exploratory_behavior=True,**episode_metrics(gz_rows(p.with_name('training_traces.csv.gz')))))
                if step%4096==0:
                    ts=gz_rows(p.with_name('validation_traces.csv.gz'))
                    metric_check(p.with_name('validation_metrics.csv'),ts)
                    for row in ts:
                        values=validation_winds[row['case_id']]
                        assert float(row['decision_wind_m_s'])==float(values[int(row['decision_step']),0]) and float(row['response_wind_m_s'])==float(values[int(row['response_step']),0])
                    ms=read_csv(p.with_name('validation_metrics.csv'));hist.append(dict(arm=arm,run=run,step=step,mean_rmse_w=float(np.mean([float(x['rmse_w']) for x in ms]))))
            assert len(loss_stream)==7937 and [x[0] for x in loss_stream]==list(range(512,16385,2));paired[arm,run]=loss_stream
    assert len(fulls)==104 and len(light)==774 and updates==47622
    for r in selection['results']:
        observed=[h for h in hist if h['arm']==r['arm'] and h['run']==r['run']]
        assert [(h['step'],h['mean_rmse_w']) for h in observed]==[(h['step'],h['rmse_w']) for h in r['history']]
        assert min(observed,key=lambda h:(h['mean_rmse_w'],h['step']))['step']==r['selected_step']
    for run in range(3):
        assert paired['replay',run]==paired['current_pitch',run]
        for step in (128,256,384,512):
            with np.load(root/f'replay_run{run}/step_{step:08d}/attempt_000/training.npz') as a,np.load(root/f'current_pitch_run{run}/step_{step:08d}/attempt_000/training.npz') as b:
                assert all(np.array_equal(a[k],b[k]) for k in a.files)
    processes=[read_json(p) for p in sorted((root/'processes').glob('process_*.json')) if not p.name.endswith('started.json')]
    assert len(processes)==10 and all(p['returncode']==0 for p in processes)
    assert not list(root.glob('*_run*/step_*/attempt_*/failed.json'))
    ticks=(root/'query_ticks.bin').read_bytes();assert ticks.count(b'T')==99072
    learning=[json.loads(x) for x in (root/'learning_budget.jsonl').read_text(encoding='utf-8').splitlines()];assert sum(x['steps'] for x in learning)==98304
    for split in ('validation','known'):
        rows=collect(root,split);summarize(root,split,rows);table(root,root/f'{split}_metrics.csv',rows)
        labels=['p','pi'] if split=='validation' else [f'{r["arm"]}_run{r["run"]}_{role}' for r in selection['results'] for role in ('initial','selected','final')]+['p','pi']
        seen=set()
        for label in labels:
            folder,_=latest(root,split,label);trace=trace_location(folder)
            if str(trace) not in seen:metric_check(folder/'metrics.csv',gz_rows(trace));seen.add(str(trace))
    known_input=collect(root,'known')
    assert all(r['family']=='stationary' and float(r['target_w'])==3.8e6 and float(r['initial_pitch_rad']) in (.025,.055) for r in known_input if r['case_id'].startswith('train_episode_8_'))
    result=verdict(root,known_input,collect(root,'validation'))
    golden_difference=0.
    known_rows=collect(root,'known')
    for label,arm,run,role in [('p','p',-1,'p'),('pi','pi',-1,'pi')]+[(f'n8_run{r}_selected','replay',r,'initial') for r in range(3)]:
        old={r['case_id']:r for r in read_csv(OLD/f'evaluations/known/{label}/attempt_000/metrics.csv')}
        for r in [r for r in known_rows if r['arm']==arm and int(r['run'])==run and r['role']==role]:
            for key in ('rmse_w','mean_error_w','error_std_w'):
                golden_difference=max(golden_difference,abs(float(r[key])-float(old[r['case_id']][key])))
    assert golden_difference<=1e-9
    js(root,root/'validation_acceptance.json',result)
    table(root,root/'checkpoint_manifest.csv',fulls);table(root,root/'fragment_manifest.csv',light);table(root,root/'history.csv',hist);table(root,root/'training_metrics.csv',train_metrics)
    postprocessor_files=[Path(__file__),Path(__file__).with_name('pitch_actor_context_figures.py'),Path(__file__).with_name('pitch_actor_context_reproduce.py'),Path(__file__).with_name('pitch_actor_context_finish.py'),
                        Path(__file__).parents[1]/'tests/test_pitch_actor_context_reporting.py',Path(__file__).parents[1]/'tests/test_pitch_actor_context_bounds.py']
    verify(read_json(root/'analysis_code_freeze.json')['hashes'])
    js(root,root/'pretest_audit.json',dict(core_correct=True,validation_passed=result['passed'],formal_steps=98304,updates=updates,full_states=104,light_commits=774,
        engineering_full_states=1,actual_training_plant_rows=99072,recomputed_learning_steps=0,first512_paired=True,sample_indices_and_m_paired=True,
        native_reward_residual_max=residual,storage_bytes=size(root),postprocessor_sha256=digest(__file__),
        validation_bank_regenerated=True,known_parent_and_baseline_metric_difference_max=golden_difference,
        postprocessor_hashes={str(p):digest(p) for p in postprocessor_files},
        hashes={str(p):digest(p) for p in [root/'selection.json',root/'config.yaml',root/'validation_acceptance.json',root/'checkpoint_manifest.csv',root/'validation_bank/manifest.json',root/'analysis_code_freeze.json']}))
    print(json.dumps(dict(pretest='passed',validation_passed=result['passed'],full_states=104,storage_bytes=size(root))),flush=True)


def review(root):
    import numpy as np
    root,s=context(root);pre=read_json(root/'pretest_audit.json');verify(pre['hashes']);verify(pre['postprocessor_hashes']);assert pre['postprocessor_sha256']==digest(__file__)
    test_winds=validate_bank(root,s,'test')
    rows=collect(root,'test');summarize(root,'test',rows);table(root,root/'metrics.csv',rows)
    test_gates=gates(rows);pi={r['case_id']:r for r in rows if r['arm']=='pi'};pi_status=[]
    for role in ('selected','final'):
        cs=[r for r in rows if r['arm']=='current_pitch' and r['role']==role]
        for scope in ('routine','all_including_pressure','low_wind_stress'):
            part=[r for r in cs if (r['split']!='stress' if scope=='routine' else r['split']=='stress' if scope=='low_wind_stress' else True)]
            c=np.mean([float(r['rmse_w']) for r in part]);p=np.mean([float(pi[r['case_id']]['rmse_w']) for r in part])
            pi_status.append(dict(role=role,scope=scope,candidate_case_mean_rmse_w=float(c),pi_case_mean_rmse_w=float(p),average_better=bool(c<p),
                strictly_better_slots=sum(float(r['rmse_w'])<float(pi[r['case_id']]['rmse_w']) for r in part),slots=len(part),
                all_cases_all_streams_better=all(float(r['rmse_w'])<float(pi[r['case_id']]['rmse_w']) for r in part)))
    canonical=set();steps=0;max_heading=0.;base,_=latest(root,'test','pi');common={(r['case_id'],r['response_step']):r for r in gz_rows(trace_location(base))}
    for label in [f'{r["arm"]}_run{r["run"]}_{role}' for r in read_json(root/'selection.json')['results'] for role in ('initial','selected','final')]+['p','pi']:
        folder,d=latest(root,'test',label);steps+=d['actual_environment_steps'];path=trace_location(folder)
        if str(path) in canonical:continue
        canonical.add(str(path));traces=gz_rows(path);metric_check(folder/'metrics.csv',traces)
        for r in traces:
            ref=common[r['case_id'],r['response_step']];assert r['response_wind_m_s']==ref['response_wind_m_s'] and r['wind_direction_rad']==ref['wind_direction_rad']
            assert float(r['response_wind_m_s'])==float(test_winds[r['case_id']][int(r['response_step']),0])
            max_heading=max(max_heading,max(abs(float(r[f'heading_{i}'])-float(ref[f'heading_{i}'])) for i in range(3)))
    assert max_heading<=1e-9
    js(root,root/'test_acceptance.json',dict(gates=test_gates,PI=pi_status,validation_not_revised=True))
    selection=read_json(root/'selection.json');policies=[]
    for r in selection['results']:
        for role in ('initial','selected','final'):policies.append(dict(arm=r['arm'],run=r['run'],role=role,checkpoint=r[role],sha256=digest(r[role]),
            parent=s['parents'][str(r['run'])],loader='PitchActorContextMADDPG.load(path, expected_arm)',version='pitch_actor_context_v1',experimental_not_default=True))
    js(root,root/'policy_manifest.json',dict(seed=42,policies=policies,aliases_are_references_not_copies=True))
    contract=OLD.parent/'20261028_pitch_nstep_mechanism/candidate_normalization.json'
    from ..environments.maddpg_farm_env import OBSERVATIONS
    e=s['base_config']['environment'];plant=s['base_config']['plant']
    js(root,root/'normalization.json',dict(kind='fixed_physical_no_running_scaler',observation_shape=[3,15],observation_fields=list(OBSERVATIONS),action_shape=[3,3],action_mask=[0,1,0],
        action_low=e['action_low'],action_high=e['action_high'],farm_rating_w=15e6,wind_scale_m_s=e['wind_scale_m_s'],dt_s=1,horizon=128,
        source_contract=str(contract),source_contract_sha256=digest(contract),original_contract=read_json(contract),
        model_version=plant['model_version'],model_sha256=plant['backend']['model_sha256'],power_semantics=plant['power_semantics'],
        rated_power_w=plant['rated_power_w'],reference_schedule=e['reference_schedule'],reference_mode=e.get('action_reference_mode','legacy_physical'),
        action_semantics='normalized total reference, not actual actuator state',action_order=['yaw_offset_rad','pitch_rad','speed_rad_s'],
        time_constants_s=e['time_constants_s'],rate_limits=e['rate_limits'],yaw_frame=e['yaw_frame']))
    import platform,torch,tensorflow as tf
    js(root,root/'resolved_execution.json',dict(python=platform.python_version(),numpy=np.__version__,torch=torch.__version__,tensorflow=tf.__version__,
        device='cpu',training_torch_threads=1,training_tensorflow_intra_threads=1,training_tensorflow_inter_threads=1,
        training_runtime_source='pitch_actor_context_trial.main and launch, frozen SHA in config',seed=42,arms=list(ARMS),n=8,gamma=.99,
        actual_steps_per_job=16384,actual_update_calls_per_job=7937,actual_warmup_steps=512,actual_update_every=2,
        actual_noise_kind='white',actual_noise_std=[0.,.03,0.],actual_noise_end_fraction=.2,
        unused_base_training_template=s['base_config']['training'],actual_exploration_streams=[
            dict(run=r['run'],entropy=r['entropy'],integer_seed=r['integer_seed']) for r in read_json(root/'random_states.json')]))
    ticks=(root/'query_ticks.bin').read_bytes();reservations=[json.loads(x) for x in (root/'evaluation_budget.jsonl').read_text(encoding='utf-8').splitlines()]
    evalsteps=sum(x['steps'] for x in reservations);assert evalsteps<=278528 and ticks.count(b'E')==evalsteps+evalsteps//128 and len(ticks)<=381088
    actual=size(root);assert actual<=s['storage_limit_bytes']
    validation=read_json(root/'validation_acceptance.json')
    js(root,root/'numerical_summary.json',dict(status='complete',seed=42,completed_date='2026-10-30',formal_learning_steps=98304,new_updates=47622,engineering_discarded_updates=8,
        actual_training_plant_rows=ticks.count(b'T'),actual_evaluation_plant_rows=ticks.count(b'E'),actual_total_plant_rows=len(ticks),evaluation_transition_steps=evalsteps,
        independent_test_steps=steps,unique_test_actor_traces=len(canonical),semantic_test_metrics=len(rows),formal_full_states=104,engineering_full_states=1,
        recomputed_learning_steps=0,storage_bytes_before_summary=actual,storage_cap_bytes=3*1024**3,validation_passed=validation['passed'],test_PI=pi_status,
        default_policy_changed=False,shared_sources_unchanged=True,validation_not_revised_by_test=True,
        files={p.name:digest(p) for p in root.iterdir() if p.is_file()}))
    print(json.dumps(dict(complete=True,validation_passed=validation['passed'],evaluation_steps=evalsteps,actual_model_rows=len(ticks),storage_bytes=size(root))),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['pretest','review']);p.add_argument('--output',required=True);a=p.parse_args()
    from .fixed_pinn_demo import activate_runtime
    from .pitch_actor_context_trial import ORIGINAL
    activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    (pretest if a.mode=='pretest' else review)(a.output)


if __name__=='__main__':main()
