"""Frozen gamma trial audit and complete-case reporting. No optimizer or environment calls."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import gzip
import json
from pathlib import Path

from .pitch_gamma_trial import (ARMS,FAMILIES,NETS,OPTIMIZERS,ORIGINAL,context,fingerprint,digest,
                                read_json,read_csv,write_csv,write_json,verify,episode_metrics,entropy,json_state)
from .pitch_nstep_trial import compressed_csv


def gz_rows(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:return list(csv.DictReader(f))


def table(path,rows):
    rows=list(rows);fields=list(dict.fromkeys(k for r in rows for k in r));write_csv(path,({k:r.get(k,'') for k in fields} for r in rows))


def latest(root,split,label):
    p=sorted((root/'evaluations'/split/label).glob('attempt_*/complete.json'))[-1]
    c=read_json(p);verify(c['hashes']);return p.parent,c


def trace_location(path):
    seen=set()
    while not (path/'traces.csv.gz').exists():
        if str(path) in seen:raise ValueError('alias cycle')
        seen.add(str(path));c=read_json(path/'complete.json');verify(c['hashes']);path=Path(c['reused_from'])
    return path/'traces.csv.gz'


def metric_check(path,traces):
    import numpy as np
    groups=defaultdict(list)
    for r in traces:groups[r['case_id']].append(r)
    rows=read_csv(path)
    assert len(rows)==len(groups)
    maximum=0.
    for m in rows:
        recomputed=episode_metrics(groups[m['case_id']])
        for k,v in recomputed.items():
            if k in ('case_id','split','family'):assert v==m[k]
            else:
                delta=abs(float(m[k])-float(v));maximum=max(maximum,delta)
                assert delta<1e-9,(path,k,delta)
        assert float(m['pitch_min_rad'])>=-1e-9 and float(m['pitch_max_rad'])<=.22+1e-9
        assert float(m['pitch_max_rate_rad_s'])<=.00872664626+1e-9
    return maximum


def regenerate_inputs(root,s,split):
    """Independent deterministic construction, zero plant queries or environment steps."""
    import numpy as np
    from .pitch_nstep_trial import wind
    from .stable_workflow import Exploration
    from ..environments.farm_inflow import InflowTrace
    expected={}
    if split=='train':
        designs=read_csv(root/'training_manifest.csv');states=read_json(root/'random_states.json')
        assert len(designs)==384
        for run in range(3):
            n=Exploration(int(entropy(5103,run).generate_state(1)[0]),[0.,.03,0.],[10.,3.,5.],1.,'white',.2)
            assert json_state(n.state_dict())==states[run]['initial']
            with np.load(root/f'noise_run{run}.npz') as values:
                for ep in range(128):
                    d=next(d for d in designs if int(d['run'])==run and int(d['episode_index'])==ep)
                    block,index=divmod(ep,9);order=np.random.default_rng(entropy(5101,run,block)).permutation(9)
                    family,target=[(f,t) for f in FAMILIES for t in (2.6e6,3.2e6,3.8e6)][order[index]]
                    pitch=float(np.random.default_rng(entropy(5102,run,ep)).uniform(.025,.055))
                    assert d['family']==family and float(d['target_w'])==target and float(d['initial_pitch_rad'])==pitch
                    assert int(d['episode'])==51000000+run*1000+ep
                    w=wind(s['base_config'],family,'train',int(d['episode']))
                    assert np.array_equal(w.values,InflowTrace.load(d['path']).values) and fingerprint(w.values)==d['values_sha256']
                    expected[run,ep]=w.values
                    assert json_state(n.state_dict())==states[run]['episodes'][ep]['before_reset']
                    n.reset();regenerated=np.stack([n.sample((ep*128+t)/16384) for t in range(128)])
                    assert np.array_equal(regenerated,values['noise'][ep]) and json_state(n.state_dict())==states[run]['episodes'][ep]['after']
        return expected
    manifest=read_json(root/f'{split}_bank/manifest.json');verify(manifest['hashes'])
    targets=(2.9e6,3.5e6) if split=='validation' else (2.7e6,3.3e6,3.9e6)
    pitches=(.025,.04,.055) if split=='validation' else (.03,.05);repeats=1 if split=='validation' else 2
    offset=52000000 if split=='validation' else 53000000
    spec={(family,target,pitch,offset+fi*100+ti*10+repeat) for fi,family in enumerate(FAMILIES) for ti,target in enumerate(targets) for pitch in pitches for repeat in range(repeats)}
    routine=[c for c in manifest['cases'] if c['split']!='stress']
    assert len(routine)==len(spec)
    assert {(c['family'],c['target_w'],c['initial_pitch_rad'],c['episode']) for c in routine}==spec
    for c in routine:
        assert np.array_equal(wind(s['base_config'],c['family'],split,c['episode']).values,InflowTrace.load(c['path']).values)
    pressure=[c for c in manifest['cases'] if c['split']=='stress']
    assert len(pressure)==(8 if split=='test' else 0)
    for c in pressure:
        w=InflowTrace.load(c['path']).values
        assert c['target_w'] in (4.35e6,4.55e6) and c['initial_pitch_rad'] in (.03,.05)
        assert c['episode'] in (53009000,53009001)
        assert np.array_equal(w,np.tile([7.6 if c['episode']==53009000 else 7.8,0.,.08],(129,1)))
    return dict(routine_cases=len(routine),known_pressure_cases=len(pressure))


def collect(root,split):
    selection=read_json(root/'selection.json');rows=[]
    for r in selection['results']:
        for role in ('initial','selected','final'):
            if split=='validation':data=read_csv(Path(r[role]).with_name('validation_metrics.csv'))
            else:
                path,_=latest(root,split,f'{r["arm"]}_run{r["run"]}_{role}');data=read_csv(path/'metrics.csv')
            for m in data:rows.append(dict(arm=r['arm'],run=r['run'],role=role,**m))
    for baseline in ('p','pi'):
        path,_=latest(root,split,baseline)
        # One common baseline. Pairing below refers to it without adding duplicate metric rows.
        for m in read_csv(path/'metrics.csv'):rows.append(dict(arm=baseline,run=-1,role=baseline,**m))
    return rows


def aggregates(rows):
    import numpy as np
    groups=defaultdict(list)
    has_pressure=any(r['split']=='stress' for r in rows)
    for r in rows:
        for family in (r['family'],):groups[r['arm'],int(r['run']),r['role'],family].append(r)
        if r['split']!='stress':groups[r['arm'],int(r['run']),r['role'],'routine'].append(r)
        if has_pressure:groups[r['arm'],int(r['run']),r['role'],'all_including_pressure'].append(r)
    result=[]
    for (arm,run,role,family),part in groups.items():
        rmse=np.array([float(r['rmse_w']) for r in part]);bias=np.array([float(r['mean_error_w']) for r in part]);std=np.array([float(r['error_std_w']) for r in part])
        mse=np.mean(rmse**2)
        result.append(dict(arm=arm,run=run,role=role,family=family,cases=len(part),mean_rmse_w=float(rmse.mean()),
                       pooled_rmse_w=float(np.sqrt(mse)),worst_rmse_w=float(rmse.max()),mean_error_w=float(bias.mean()),
                       pooled_error_std_w=float(np.sqrt(max(0.,mse-bias.mean()**2))),mean_case_std_w=float(std.mean()),
                       mean_travel_rad=float(np.mean([float(r['pitch_travel_rad']) for r in part])),
                       worst_travel_rad=max(float(r['pitch_travel_rad']) for r in part),
                       mean_rms_rate_rad_s=float(np.mean([float(r['pitch_rms_rate_rad_s']) for r in part])),
                       worst_rms_rate_rad_s=max(float(r['pitch_rms_rate_rad_s']) for r in part),
                       max_rate_rad_s=max(float(r['pitch_max_rate_rad_s']) for r in part),
                       mean_rate_fraction=float(np.mean([float(r['pitch_rate_fraction']) for r in part])),
                       mean_boundary_fraction=float(np.mean([float(r['pitch_boundary_fraction']) for r in part]))))
    return result


def stratified(root,split,rows):
    import numpy as np
    groups=defaultdict(list)
    for r in rows:groups[r['arm'],r['role'],r['family'],r['target_w'],r['initial_pitch_rad']].append(r)
    result=[]
    for key,rs in groups.items():
        stream=defaultdict(list)
        for r in rs:stream[int(r['run'])].append(float(r['rmse_w']))
        result.append(dict(arm=key[0],role=key[1],family=key[2],target_w=key[3],initial_pitch_rad=key[4],
                      trajectory_slots=len(rs),streams=len(stream),mean_rmse_w=float(np.mean([float(r['rmse_w']) for r in rs])),
                      pooled_rmse_w=float(np.sqrt(np.mean([float(r['mse_w2']) for r in rs]))),
                      stream_sd_w=float(np.std([np.mean(v) for v in stream.values()])),
                      mean_error_w=float(np.mean([float(r['mean_error_w']) for r in rs])),
                      mean_case_error_std_w=float(np.mean([float(r['error_std_w']) for r in rs])),
                      mean_pitch_travel_rad=float(np.mean([float(r['pitch_travel_rad']) for r in rs])),
                      mean_pitch_rms_rate_rad_s=float(np.mean([float(r['pitch_rms_rate_rad_s']) for r in rs]))))
    table(root/f'{split}_target_initial.csv',result)


def acceptance(root,split,rows):
    import numpy as np
    _,s=context(root);g=s['gates'];ag=aggregates(rows);lookup={(r['arm'],r['run'],r['role'],r['family']):r for r in ag}
    pairs=[]
    for run in range(3):
        for role in ('selected','final'):
            for family in (*FAMILIES,'routine')+ (('low_wind_stress','all_including_pressure') if split=='test' else ()):
                c=lookup['g100',run,role,family]
                for ref_arm,ref_role,label in [('g099',role,'control'),('g099','initial','parent'),('p','p','p'),('pi','pi','pi')]:
                    b=lookup[ref_arm,run if ref_arm in ARMS else -1,ref_role,family]
                    pairs.append(dict(split=split,run=run,role=role,family=family,reference=label,
                              candidate_rmse_w=c['mean_rmse_w'],reference_rmse_w=b['mean_rmse_w'],delta_rmse_w=c['mean_rmse_w']-b['mean_rmse_w'],
                              mean_ratio=c['mean_rmse_w']/b['mean_rmse_w'],worst_ratio=c['worst_rmse_w']/b['worst_rmse_w'],
                              pooled_ratio=c['pooled_rmse_w']/b['pooled_rmse_w'],
                              travel_ratio=c['mean_travel_rad']/max(b['mean_travel_rad'],g['motion_floor']),
                              rms_rate_ratio=c['mean_rms_rate_rad_s']/max(b['mean_rms_rate_rad_s'],g['motion_floor']),
                              candidate_travel_rad=c['mean_travel_rad'],reference_travel_rad=b['mean_travel_rad'],
                              candidate_rms_rate_rad_s=c['mean_rms_rate_rad_s'],reference_rms_rate_rad_s=b['mean_rms_rate_rad_s']))
    def filtered(**filters):return [r for r in pairs if all(r[k]==v for k,v in filters.items())]
    ramp={}
    for role in ('selected','final'):
        rs=filtered(role=role,family='ramp',reference='control')
        ratio=sum(r['candidate_rmse_w'] for r in rs)/sum(r['reference_rmse_w'] for r in rs)
        count=sum(r['mean_ratio']<1 for r in rs)
        ramp[role]=dict(ratio=ratio,improved_runs=count,passed=bool(ratio<=1-g['ramp_improvement'] and count>=2))
    sel=read_json(root/'selection.json');learned=sum(r['selected_step']>0 for r in sel['results'] if r['arm']=='g100')
    other=all(r['mean_ratio']<=1.05 and r['worst_ratio']<=1.05 for r in pairs if r['family'] in ('stationary','gust') and r['reference'] in ('control','parent'))
    stable=[]
    for run in range(3):
        final=lookup['g100',run,'final','routine'];selected=lookup['g100',run,'selected','routine']
        baseline=filtered(run=run,role='final',family='routine')
        stable.append(dict(run=run,final_over_selected=final['mean_rmse_w']/selected['mean_rmse_w'],
                     passed=bool(final['mean_rmse_w']/selected['mean_rmse_w']<=1.25 and all(r['mean_ratio']<=1.05 and r['worst_ratio']<=1.05 for r in baseline if r['reference'] in ('control','parent')))))
    motion=all(r['travel_ratio']<=1.10 and r['rms_rate_ratio']<=1.10 for r in pairs if r['family'] in FAMILIES and r['reference']=='control')
    physical=all(r['max_rate_rad_s']<=.00872664626+1e-9 for r in ag)
    verdict=dict(split=split,new_learning_runs=learned,new_learning_pass=learned==3,ramp=ramp,other_capability_preserved=other,
                 stability=stable,stable_runs=sum(r['passed'] for r in stable),actual_motion_pass=motion,physical_pass=physical,
                 passed=bool(learned==3 and all(r['passed'] for r in ramp.values()) and other and all(r['passed'] for r in stable) and motion and physical),
                 validation_decision_not_revised_by_test=True)
    table(root/f'{split}_aggregate.csv',ag);table(root/f'{split}_paired_groups.csv',pairs)
    # Paired case deltas to all references, preserving target and initial state.
    cases={(r['arm'],int(r['run']),r['role'],r['case_id']):r for r in rows};cp=[]
    for run in range(3):
        for arm in ARMS:
            for role in ('selected','final'):
                for c in [r for r in rows if r['arm']==arm and int(r['run'])==run and r['role']==role]:
                    refs=[('g099',role,'control'),('g099','initial','parent'),('p','p','p'),('pi','pi','pi')]
                    for ref_arm,ref_role,label in refs:
                        b=cases[ref_arm,run if ref_arm in ARMS else -1,ref_role,c['case_id']]
                        cp.append(dict(arm=arm,run=run,role=role,case_id=c['case_id'],family=c['family'],split=c['split'],target_w=c['target_w'],initial_pitch_rad=c['initial_pitch_rad'],reference=label,
                                       candidate_rmse_w=float(c['rmse_w']),reference_rmse_w=float(b['rmse_w']),delta_rmse_w=float(c['rmse_w'])-float(b['rmse_w'])))
    table(root/f'{split}_paired_cases.csv',cp)
    comparative=[]
    for arm in ARMS:
        for role in ('selected','final'):
            for family in (*FAMILIES,'routine')+(('low_wind_stress','all_including_pressure') if split=='test' else ()):
                for reference in ('control','parent','p','pi'):
                    part=[r for r in cp if r['arm']==arm and r['role']==role and r['reference']==reference and
                          (r['split']!='stress' if family=='routine' else True if family=='all_including_pressure' else r['family']==family)]
                    delta=[np.mean([r['delta_rmse_w'] for r in part if r['run']==run]) for run in range(3)]
                    comparative.append(dict(arm=arm,role=role,family=family,reference=reference,paired_case_slots=len(part),
                             mean_delta_rmse_w=float(np.mean(delta)),stream_sd_delta_w=float(np.std(delta)),
                             ratio_of_case_means=sum(r['candidate_rmse_w'] for r in part)/sum(r['reference_rmse_w'] for r in part),
                             strictly_better_case_slots=sum(r['delta_rmse_w']<0 for r in part),
                             all_finite_case_slots_strictly_better=all(r['delta_rmse_w']<0 for r in part)))
    table(root/f'{split}_comparisons.csv',comparative)
    cross=[]
    for arm in (*ARMS,'p','pi'):
        roles=('initial','selected','final') if arm in ARMS else (arm,)
        for role in roles:
            for family in (*FAMILIES,'routine')+(('low_wind_stress','all_including_pressure') if split=='test' else ()):
                part=[lookup[arm,run,role,family] for run in (range(3) if arm in ARMS else [-1])]
                cross.append(dict(arm=arm,role=role,family=family,mean_rmse_w=float(np.mean([r['mean_rmse_w'] for r in part])),
                      stream_sd_w=float(np.std([r['mean_rmse_w'] for r in part])),
                      pooled_all_streams_w=float(np.sqrt(np.mean([r['pooled_rmse_w']**2 for r in part]))),
                      travel_mean_rad=float(np.mean([r['mean_travel_rad'] for r in part])),rms_rate_mean_rad_s=float(np.mean([r['mean_rms_rate_rad_s'] for r in part]))))
    table(root/f'{split}_cross_stream.csv',cross);write_json(root/f'{split}_acceptance.json',verdict)
    stratified(root,split,rows)
    return verdict


def pretest(root):
    import numpy as np
    import torch
    root,s=context(root);selection=read_json(root/'selection.json')
    if (root/'pretest_audit.json').exists():raise FileExistsError('pretest audit frozen')
    assert not (root/'test_bank').exists() and selection['config_sha256']==digest(root/'config.yaml')
    verify(read_json(root/'data_lock.json')['hashes']);verify(read_json(root/'engineering.json')['hashes'])
    expected_winds=regenerate_inputs(root,s,'train');validation_bank_check=regenerate_inputs(root,s,'validation')
    design={(int(r['run']),int(r['episode_index'])):r for r in read_csv(root/'training_manifest.csv')}
    manifests=[];paired={};native_residual=0.;metric_residual=0.;update_count=0;histories=[];training_metrics=[]
    for arm,gamma in ARMS.items():
        for run in range(3):
            commits=sorted((root/f'{arm}_run{run}').glob('step_*/attempt_*/commit.json'));assert len(commits)==129
            noise=np.load(root/f'noise_run{run}.npz')['noise'];loss_stream=[]
            for p in commits:
                c=read_json(p);verify(c['hashes']);step=c['step'];saved=torch.load(c['checkpoint'],map_location='cpu',weights_only=False)
                meta=saved['metadata'];assert meta['experiment']=='pitch_gamma_v1' and meta['gamma']==gamma and meta['config']['algorithm']['gamma']==gamma
                assert saved['n']==8 and saved['config']['gamma']==gamma and saved['replay']['n']==8
                expected_cfg=__import__('copy').deepcopy(s['base_config']);expected_cfg['algorithm']['gamma']=gamma
                assert meta['config']==expected_cfg and tuple(saved['config']['action_mask'])==(0,1,0)
                assert meta['root_config_sha256']==digest(root/'config.yaml') and meta['step']==step and meta['episode']==step//128
                expected_updates=0 if step<512 else (step-512)//2+1
                assert saved['updates']==s['parents'][str(run)]['updates']+expected_updates
                replay=saved['replay'];parent=s['parents'][str(run)]
                assert replay['insertions']==parent['initial_insertions']+step
                assert replay['size']==min(32768,parent['replay_size']+step) and replay['position']==(parent['replay_position']+step)%32768
                assert sum(replay['m_histogram'])==expected_updates*64
                if step==0:
                    assert fingerprint(replay)==parent['initial_replay']
                    assert fingerprint({k:saved[k] for k in NETS})==parent['initial_networks']
                    assert fingerprint({k:saved[k] for k in OPTIMIZERS})==parent['initial_optimizers']
                else:
                    ep=step//128-1;d=design[run,ep]
                    with np.load(p.with_name('training.npz')) as a:
                        assert a['obs'].shape==(128,3,15) and np.array_equal(a['terminated'][:,0],[False]*127+[True])
                        assert np.array_equal(a['next_obs'][:-1],a['obs'][1:]) and np.array_equal(a['actions'][:-1],a['obs'][1:,:,5:8])
                        assert np.array_equal(a['obs'][:,:,14],np.tile(1-np.arange(128)[:,None]/128,(1,3)))
                        assert np.array_equal(a['next_obs'][:,:,14],np.tile(1-np.arange(1,129)[:,None]/128,(1,3)))
                        assert np.array_equal(a['exploration'],noise[ep])
                        assert np.array_equal(a['wind'],expected_winds[run,ep][1:].astype(np.float32))
                        native=expected_winds[run,ep].astype(np.float32)
                        expected_observed=(native[:-1,0].astype(float)/s['base_config']['environment']['wind_scale_m_s']).astype(np.float32)
                        assert np.array_equal(a['obs'][:,0,10],expected_observed)
                        physical=a['applied'][:,:,1];previous=np.vstack((np.full((1,3),float(d['initial_pitch_rad'])),physical[:-1]))
                        assert physical.min()>=-1e-9 and physical.max()<=.22+1e-9 and np.abs(physical-previous).max()<=.00872664626+1e-9
                        cost=np.mean((a['actions']-a['obs'][:,:,5:8])**2,axis=(1,2))
                        expected=100*(-(a['error_w']/15e6)**2-.001*cost)
                        residual=float(np.abs(a['rewards'][:,0]-expected).max());native_residual=max(native_residual,residual);assert residual<=5e-6
                        assert np.array_equal(a['rewards'],np.tile(a['rewards'][:,0,None],(1,3)))
                    losses=[r for r in read_csv(p.with_name('losses.csv')) if 'step' in r]
                    loss_stream.extend([(int(r['step']),r['sample_indices_sha256'],r['m_mean'],r['m_min'],r['m_max']) for r in losses]);update_count+=len(losses)
                    ts=gz_rows(p.with_name('training_traces.csv.gz'))
                    training_metrics.append(dict(arm=arm,run=run,episode_index=ep,exploratory_behavior=True,**episode_metrics(ts)))
                if step%4096==0:
                    metric_residual=max(metric_residual,metric_check(p.with_name('validation_metrics.csv'),gz_rows(p.with_name('validation_traces.csv.gz'))))
                    ms=read_csv(p.with_name('validation_metrics.csv'))
                    assert len(ms)==18 and {r['case_id'] for r in ms}=={c['id'] for c in read_json(root/'validation_bank/manifest.json')['cases']}
                    histories.append(dict(arm=arm,run=run,step=step,mean_rmse_w=float(np.mean([float(r['rmse_w']) for r in ms]))))
                manifests.append(dict(arm=arm,run=run,step=step,checkpoint=c['checkpoint'],sha256=digest(c['checkpoint']),gamma=gamma,
                         updates=saved['updates'],added_updates=expected_updates,replay_size=replay['size'],replay_position=replay['position'],insertions=replay['insertions'],m_histogram=json.dumps(replay['m_histogram'].tolist())))
            assert len(loss_stream)==7937 and [r[0] for r in loss_stream]==list(range(512,16385,2))
            paired[arm,run]=loss_stream
            result=next(r for r in selection['results'] if r['arm']==arm and r['run']==run)
            observed=[h for h in histories if h['arm']==arm and h['run']==run]
            assert min(observed,key=lambda r:(r['mean_rmse_w'],r['step']))['step']==result['selected_step']
            assert [h['mean_rmse_w'] for h in observed]==[h['rmse_w'] for h in result['history']]
    assert update_count==6*7937
    for run in range(3):assert paired['g099',run]==paired['g100',run]
    for run in range(3):
        for step in (128,256,384,512):
            paths=[sorted((root/f'{a}_run{run}'/f'step_{step:08d}').glob('attempt_*/training.npz'))[-1] for a in ARMS]
            with np.load(paths[0]) as a,np.load(paths[1]) as b:
                assert a.files==b.files
                for field in a.files:assert np.array_equal(a[field],b[field]),(run,step,field)
    processes=[read_json(p) for p in sorted((root/'processes').glob('process_*.json'))]
    assert len(processes)==10 and all(p['returncode']==0 for p in processes)
    assert not list(root.glob('*_run*/step_*/attempt_*/failed.json'))
    for kind,total in [('learning',98304),('evaluation',73728)]:
        ledger=[json.loads(x) for x in (root/f'{kind}_budget.jsonl').read_text(encoding='utf-8').splitlines()]
        assert sum(r['reserved_steps'] for r in ledger)==total
    for baseline in ('p','pi'):
        p,_=latest(root,'validation',baseline)
        metric_residual=max(metric_residual,metric_check(p/'metrics.csv',gz_rows(p/'traces.csv.gz')))
    rows=collect(root,'validation');verdict=acceptance(root,'validation',rows);table(root/'validation_metrics.csv',rows)
    table(root/'training_metrics.csv',training_metrics)
    table(root/'checkpoint_manifest.csv',manifests);table(root/'history.csv',histories)
    verify(s['protected_hashes'])
    write_json(root/'pretest_audit.json',dict(core_correct=True,formal_learning_steps=98304,new_updates=update_count,checkpoint_count=len(manifests),
               processes=10,all_normal_exit=True,planned_restore_at_4096=True,first128_within_budget=True,
               raw_reward_residual_max=native_residual,validation_metric_residual_max=metric_residual,
               regenerated_training_winds=384,regenerated_noise_steps=49152,validation_bank=validation_bank_check,
               postprocessor_sha256=digest(__file__),
               sample_indices_and_actual_m_paired=True,source_inputs_unchanged=True,validation=verdict,
               first512_behavior_identical_all_streams=True,
               hashes={str(p.resolve()):digest(p) for p in [root/'selection.json',root/'config.yaml',root/'validation_acceptance.json',root/'checkpoint_manifest.csv',root/'history.csv']}))
    print(json.dumps(dict(pretest='passed',validation=verdict,learning_steps=98304,updates=update_count)),flush=True)


def review(root):
    root,s=context(root);verify(read_json(root/'pretest_audit.json')['hashes']);maximum=0.;actual=0;canonical=set()
    assert read_json(root/'pretest_audit.json')['postprocessor_sha256']==digest(__file__)
    test_bank_check=regenerate_inputs(root,s,'test')
    pi_path,_=latest(root,'test','pi')
    common={(r['case_id'],int(r['response_step'])):r for r in gz_rows(trace_location(pi_path))}
    max_heading_difference=0.
    for label in [f'{r["arm"]}_run{r["run"]}_{role}' for r in read_json(root/'selection.json')['results'] for role in ('initial','selected','final')]+['p','pi']:
        path,c=latest(root,'test',label);actual+=c['actual_environment_steps'];trace=trace_location(path)
        ms=read_csv(path/'metrics.csv')
        assert len(ms)==44 and {r['case_id'] for r in ms}=={c['id'] for c in read_json(root/'test_bank/manifest.json')['cases']}
        if str(trace) not in canonical:
            ts=gz_rows(trace);maximum=max(maximum,metric_check(path/'metrics.csv',ts));canonical.add(str(trace))
            for r in ts:
                ref=common[r['case_id'],int(r['response_step'])]
                assert r['response_wind_m_s']==ref['response_wind_m_s'] and r['wind_direction_rad']==ref['wind_direction_rad']
                for i in range(3):max_heading_difference=max(max_heading_difference,abs(float(r[f'heading_{i}'])-float(ref[f'heading_{i}'])))
            assert max_heading_difference<=1e-9
    rows=collect(root,'test');verdict=acceptance(root,'test',rows);table(root/'metrics.csv',rows)
    validation=read_json(root/'validation_acceptance.json')
    write_json(root/'acceptance.json',dict(validation=validation,test=verdict,overall_pass=validation['passed'] and verdict['passed']))
    # All ratios and both aggregations are delivered; pressure is never silently removed.
    plots(root)
    export(root,s)
    learning=sum(json.loads(x)['reserved_steps'] for x in (root/'learning_budget.jsonl').read_text(encoding='utf-8').splitlines())
    evaluation=sum(json.loads(x)['reserved_steps'] for x in (root/'evaluation_budget.jsonl').read_text(encoding='utf-8').splitlines())
    assert learning==98304 and evaluation==73728+actual and evaluation<=186368
    verify(s['protected_hashes'])
    result=dict(status='complete',seed=42,formal_learning_steps=learning,new_updates=47622,engineering_discarded_updates=8,
                evaluation_steps=evaluation,independent_test_steps=actual,canonical_test_actor_traces=len(canonical),
                semantic_test_metrics=len(rows),test_metric_residual_max=maximum,validation=validation,test=verdict,
                regenerated_test_bank=test_bank_check,
                shared_wind_and_yaw_heading_verified=True,max_heading_difference_rad=max_heading_difference,
                overall_pass=validation['passed'] and verdict['passed'],test_not_used_for_selection=True,source_unchanged=True,
                files={str(p.resolve()):digest(p) for p in root.iterdir() if p.is_file() and p.name!='summary.txt'})
    write_json(root/'summary.txt',result);print(json.dumps({k:v for k,v in result.items() if k!='files'}),flush=True)


def export(root,s):
    import torch
    selection=read_json(root/'selection.json');policies=[]
    for r in selection['results']:
        for role in ('initial','selected','final'):
            path=Path(r[role]);saved=torch.load(path,map_location='cpu',weights_only=False)
            policies.append(dict(arm=r['arm'],gamma=r['gamma'],run=r['run'],role=role,checkpoint=str(path),sha256=digest(path),
                       step=saved['metadata']['step'],parent=s['parents'][str(r['run'])]['checkpoint'],parent_sha256=s['parents'][str(r['run'])]['sha256'],
                       version=saved['version'],n=8,algorithm_config=saved['config'],normalization='normalization.json',
                       loader='optimization_control.maddpg_wind_farm.pitch_gamma_trial.load_agent(checkpoint, expected_gamma)',
                       experimental_not_default=True))
    write_json(root/'policy_manifest.json',dict(seed=42,config_sha256=digest(root/'config.yaml'),selection_sha256=digest(root/'selection.json'),policies=policies))
    e=s['base_config']['environment'];plant=s['base_config']['plant']
    obs=['power_i/rated_i','effective_wind_i/wind_scale','actual_yaw_scaled','actual_pitch_scaled','actual_speed_scaled',
         'previous_yaw_reference_normalized','previous_pitch_reference_normalized','previous_speed_reference_normalized',
         'farm_target/farm_rating','farm_error/farm_rating','ambient_wind/wind_scale','sin_wind_direction','cos_wind_direction','background_ti','remaining_episode_fraction']
    write_json(root/'normalization.json',dict(kind='fixed_physical_no_running_scaler',model_version=plant['model_version'],model_sha256=plant['backend']['model_sha256'],
               power_semantics=plant['power_semantics'],observation_shape=[3,15],observation_fields=obs,action_shape=[3,3],
               action_semantics='normalized total command reference, not actual actuator state',action_order=['yaw_offset_rad','pitch_rad','speed_rad_s'],
               action_low=e['action_low'],action_high=e['action_high'],action_mask=e['control_mask'],rated_power_w=plant['rated_power_w'],
               farm_rating_w=sum(plant['rated_power_w']),wind_scale_m_s=e['wind_scale_m_s'],dt_s=e['dt_s'],horizon=e['horizon'],
               reference_schedule=e.get('reference_schedule'),reference_mode=e.get('action_reference_mode','legacy_physical'),
               time_constants_s=e['time_constants_s'],rate_limits=e['rate_limits'],yaw_frame=e['yaw_frame'],raw_reward_unchanged=True))
    import platform
    import numpy as np
    import tensorflow as tf
    write_json(root/'resolved_execution.json',dict(python=platform.python_version(),numpy=np.__version__,torch=torch.__version__,tensorflow=tf.__version__,
               torch_threads=torch.get_num_threads(),seed=42,device='cpu',n=8,arms=ARMS,
               actual_steps_per_job=16384,actual_updates_per_job=7937,warmup_steps=512,update_every=2,
               actual_noise_std=[0.,.03,0.],noise_kind='white',noise_end_fraction=.2,
               unused_base_config_training_template=s['base_config']['training'],
               actual_exploration_seeds=[dict(run=r['run'],entropy=r['entropy'],integer_seed=r['integer_seed']) for r in read_json(root/'random_states.json')]))


def plots(root):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    history=read_csv(root/'history.csv');plt.rcParams.update({'font.size':10,'figure.dpi':140})
    fig,axes=plt.subplots(2,3,figsize=(13,8),constrained_layout=True)
    selection=read_json(root/'selection.json')
    validation=read_csv(root/'validation_aggregate.csv')
    for run,ax in enumerate(axes[0]):
        for arm,color in [('g099','#d95f02'),('g100','#1b9e77')]:
            part=[r for r in history if r['arm']==arm and int(r['run'])==run]
            ax.plot([int(r['step']) for r in part],[float(r['mean_rmse_w'])/1000 for r in part],'-o',c=color,label=arm)
            result=next(r for r in selection['results'] if r['arm']==arm and r['run']==run)
            best=next(r for r in part if int(r['step'])==result['selected_step'])
            ax.scatter([result['selected_step']],[float(best['mean_rmse_w'])/1000],marker='*',s=150,c=color,edgecolors='black',zorder=3)
        ax.set_title(f'Validation stream {run}');ax.set_xlabel('New learning steps');ax.set_ylabel('18-case mean RMSE (kW)');ax.legend()
        bars=[('g099','initial','parent'),('g099','selected','.99 sel'),('g099','final','.99 final'),('g100','selected','1 sel'),('g100','final','1 final')]
        vals=[next(r for r in validation if r['arm']==a and int(r['run'])==run and r['role']==role and r['family']=='routine') for a,role,_ in bars]
        bias=np.array([float(r['mean_error_w'])**2/1e12 for r in vals]);variance=np.array([float(r['pooled_error_std_w'])**2/1e12 for r in vals])
        x=np.arange(5);bottom=axes[1,run]
        bottom.bar(x,bias,label='pooled signed bias squared',color='#d95f02');bottom.bar(x,variance,bottom=bias,label='pooled error variance',color='#377eb8')
        bottom.set_xticks(x,[r[2] for r in bars],rotation=25);bottom.set_title(f'Full-episode error decomposition: stream {run}')
        bottom.set_ylabel('Pooled MSE (MW squared)');bottom.legend(fontsize=8)
    fig.savefig(root/'validation_history.png');plt.close(fig)
    data=read_csv(root/'test_cross_stream.csv');ag=read_csv(root/'test_paired_groups.csv')
    fig,axes=plt.subplots(2,3,figsize=(15,8),constrained_layout=True)
    labels=[('g099','initial','parent'),('g099','selected','.99 sel'),('g099','final','.99 final'),('g100','selected','1 sel'),('g100','final','1 final'),('p','p','P'),('pi','pi','PI')]
    for ax,family in zip(axes.ravel(),(*FAMILIES,'routine','low_wind_stress')):
        means=[];sds=[];pooled=[]
        for arm,role,_ in labels:
            r=next(r for r in data if r['arm']==arm and r['role']==role and r['family']==family)
            means.append(float(r['mean_rmse_w'])/1000);sds.append(float(r['stream_sd_w'])/1000);pooled.append(float(r['pooled_all_streams_w'])/1000)
        x=np.arange(7);ax.bar(x,means,yerr=sds,color=['#999999','#e6ab02','#d95f02','#66a61e','#1b9e77','#7570b3','#377eb8'],alpha=.8,capsize=3)
        ax.scatter(x,pooled,marker='D',s=20,c='black',label='pooled RMSE')
        ax.set_xticks(x,[r[2] for r in labels],rotation=30);ax.set_title(family);ax.set_ylabel('RMSE (kW)');ax.legend(fontsize=8)
    ax=axes.ravel()[-1]
    for role,color in [('selected','#1b9e77'),('final','#d95f02')]:
        part=[r for r in ag if r['reference']=='control' and r['family'] in FAMILIES and r['role']==role]
        ax.scatter(np.arange(len(part)),[float(r['travel_ratio']) for r in part],marker='o',c=color,label=f'{role} travel')
        ax.scatter(np.arange(len(part)),[float(r['rms_rate_ratio']) for r in part],marker='x',c=color,label=f'{role} RMS rate')
    ax.axhline(1.10,c='black',ls='--',label='motion limit');ax.set_xlabel('Stream x family slots');ax.set_ylabel('gamma1 / .99 actual motion');ax.set_title('Actual pitch motion');ax.legend(fontsize=8)
    fig.savefig(root/'test_comparison.png');plt.close(fig)
    # Predeclared example: ramp, highest test target, repeat0, initial .03; all streams.
    manifest=read_json(root/'test_bank/manifest.json');case=next(c for c in manifest['cases'] if c['family']=='ramp' and c['target_w']==3.9e6 and c['initial_pitch_rad']==.03 and '_r0_' in c['id'])
    fig,axes=plt.subplots(3,2,figsize=(14,10),constrained_layout=True)
    for run in range(3):
        for label,color,style in [(f'g099_run{run}_initial','#999999','-'),(f'g099_run{run}_selected','#e6ab02','-'),(f'g099_run{run}_final','#d95f02','--'),
                                  (f'g100_run{run}_selected','#66a61e','-'),(f'g100_run{run}_final','#1b9e77','--'),('pi','#377eb8','-')]:
            path,_=latest(root,'test',label);rs=[r for r in gz_rows(trace_location(path)) if r['case_id']==case['id']]
            t=np.arange(1,129);axes[run,0].plot(t,[float(r['error_w'])/1000 for r in rs],style,c=color,label=label.replace(f'_run{run}',''),lw=1.)
            if label.endswith('final') or label=='pi':
                actual=np.mean([[float(r[f'pitch_actual_{i}']) for i in range(3)] for r in rs],axis=1)
                axes[run,1].plot(t,actual,style,c=color,label=label.replace(f'_run{run}','')+' actual')
                if label.endswith('final'):
                    command=np.mean([[float(r[f'pitch_command_{i}']) for i in range(3)] for r in rs],axis=1)
                    axes[run,1].plot(t,command,':',c=color,alpha=.65,lw=.8,label=label.replace(f'_run{run}','')+' command')
        axes[run,0].axhline(0,c='black',lw=.6);axes[run,0].set_title(f'Stream {run}: ramp, 3.90 MW, pitch0=.03')
        axes[run,0].set_ylabel('Signed error (kW)');axes[run,1].set_ylabel('Three-unit mean pitch (rad)')
        for ax in axes[run]:ax.set_xlabel('Response time (s), all 128 steps');ax.legend(fontsize=7,ncol=2)
    fig.savefig(root/'full_timeseries.png');plt.close(fig)


def progress(root):
    import time
    root=Path(root).resolve();jobs=[]
    for run in range(3):
        for arm in ARMS:
            folder=root/f'{arm}_run{run}'
            commits=[read_json(p)['step'] for p in folder.glob('step_*/attempt_*/commit.json')]
            r=dict(arm=arm,run=run,committed_steps=max(commits,default=0),complete=(folder/'result.json').exists())
            if r['complete']:
                end=read_json(folder/'result.json');r.update(selected_step=end['selected_step'],initial_rmse_w=end['history'][0]['rmse_w'],
                    selected_rmse_w=min(h['rmse_w'] for h in end['history']),final_rmse_w=end['history'][-1]['rmse_w'])
            jobs.append(r)
    budget={}
    for kind in ('learning','evaluation'):
        p=root/f'{kind}_budget.jsonl'
        budget[kind]=sum(json.loads(x)['reserved_steps'] for x in p.read_text(encoding='utf-8').splitlines()) if p.exists() else 0
    processes=[dict(path=str(p),**read_json(p)) for p in sorted((root/'processes').glob('process_*.json'))]
    result=dict(updated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),committed_learning_steps=sum(r['committed_steps'] for r in jobs),
                total_learning_budget=98304,conservative_reserved=budget,complete_jobs=sum(r['complete'] for r in jobs),jobs=jobs,
                active_processes=[r for r in processes if r['returncode'] is None],test_generated=(root/'test_bank').exists())
    write_json(root/'live_progress.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='active_processes'}),flush=True)


def main():
    from .fixed_pinn_demo import activate_runtime
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('pretest','review','progress'));p.add_argument('--output',required=True);args=p.parse_args()
    if args.command=='progress':progress(args.output);return
    activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    globals()[args.command](args.output)


if __name__=='__main__':main()
