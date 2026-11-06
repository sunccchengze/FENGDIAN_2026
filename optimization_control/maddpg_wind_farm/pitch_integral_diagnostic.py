"""Bounded frozen-policy integral diagnosis. No training or test-data entry point."""
from __future__ import annotations
import argparse
from copy import deepcopy
import csv
import gzip
import io
import json
import os
from pathlib import Path
import sys

from .fixed_pinn_demo import activate_runtime, digest
from .pitch_cross_wind_diagnostic import ORIGINAL, SOURCE, read_csv
from .pitch_nstep_trial import read_json, verify

HERE=Path(__file__).resolve().parent
ACTOR=HERE.parent/'experiments/20261029_pitch_actor_context'
NSTEP=HERE.parent/'experiments/20261028_pitch_nstep'
PARENTS=HERE.parent/'experiments/20261028_pitch_nstep_mechanism/candidate_manifest.json'
OLD_CASES=HERE.parent/'experiments/20261027_pitch_cross_wind_diagnostic/case_manifest.json'
LIMIT=512*1024**2
ROWS=60000
FAMILIES=('stationary','ramp','gust')


def size(root):return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())


def put(root,path,data):
    path=Path(path)
    if path.exists():raise FileExistsError(path)
    if size(root)+len(data)>LIMIT:raise RuntimeError('512MiB output cap; retained without deletion')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)


def js(root,path,value):put(root,path,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8'))


def table(root,path,rows,compressed=False):
    rows=list(rows);fields=list(dict.fromkeys(k for r in rows for k in r));buffer=io.StringIO(newline='')
    w=csv.DictWriter(buffer,fields,lineterminator='\n');w.writeheader();w.writerows({k:r.get(k,'') for k in fields} for r in rows)
    data=buffer.getvalue().encode('utf8');put(root,path,gzip.compress(data,mtime=0) if compressed else data)


def context(root):
    import yaml
    root=Path(root).resolve();cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf8'))
    verify(cfg['protected_hashes']);verify(read_json(root/'input_lock.json')['hashes'])
    assert cfg['seed']==42 and cfg['formal_training_steps']==cfg['new_test_steps']==0
    return root,cfg


class Meter:
    def __init__(self,root):
        self.root=root;self.path=root/'plant_ticks.bin';self.count=self.path.stat().st_size if self.path.exists() else 0
        self.f=self.path.open('ab',buffering=0)
    def wrap(self,predictor):
        def counted(x):
            if len(x)!=1:raise ValueError('single input row required')
            if self.count>=ROWS or size(self.root)+1024**2>LIMIT:raise RuntimeError('actual input/storage budget exhausted')
            self.f.write(b'E');self.count+=1
            return predictor(x)
        return counted
    def close(self):self.f.close()


def environment(cfg,meter):
    from .workflow import build_env
    env=build_env(cfg['base_config']);env.plant.predictor=meter.wrap(env.plant.predictor)
    return env


def known_cases():
    """Reconstruct only registered routine cases; never construct pressure/test winds."""
    import numpy as np
    import yaml
    from ..environments.farm_inflow import generate_inflow
    from .random_wind_training import cases
    saved=yaml.safe_load((SOURCE/'config.yaml').read_text(encoding='utf8'));p=saved['protocol'];winds=[]
    first=[r for r in read_csv(SOURCE/'pitch_wind_preflight.csv') if int(r['run_id'])==0][:9]
    for r in first:
        spec=deepcopy(p['inflow']);spec['speed']['scenario']=r['family']
        w=generate_inflow(spec,dt_s=1.,horizon=128,seed=42,split='train',episode=p['training_episode_offset']+int(r['episode']))
        import hashlib
        assert hashlib.sha256(w.values.tobytes()).hexdigest()==r['values_sha256']
        winds.append((dict(id=f"train_episode_{r['episode']}",split='train',family=r['family'],target_w=float(r['target_w'])),w))
    for c,w in cases(SOURCE,'validation'):
        assert c['family'] in FAMILIES and c['split']=='validation';winds.append((c,w))
    output=[];registered={c['id']:c for c in read_json(OLD_CASES) if c['family'] in FAMILIES}
    for c,w in winds:
        for pitch in ((.025,.055) if c['split']=='train' else (.025,.04,.055)):
            case=dict(id=c['id']+f'_initial_{pitch}',split=c['split'],family=c['family'],target_w=c['target_w'],initial_pitch_rad=pitch)
            import hashlib
            assert registered[case['id']]['wind_values_sha256']==hashlib.sha256(w.values.tobytes()).hexdigest()
            output.append((case,w))
    assert len(output)==36
    return output


def prepare(root):
    import numpy as np
    import torch
    import yaml
    from .nstep_algorithm import NStepMADDPG
    from .pitch_gamma_trial import state,fingerprint,episode_metrics
    from .pitch_nstep_mechanism import actor_hash
    from .pitch_gamma_review import gz_rows,trace_location
    from ..environments.farm_inflow import InflowTrace
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=False)
    old=yaml.safe_load((ACTOR/'config.yaml').read_text(encoding='utf8'));verify(old['protected_hashes'])
    base=yaml.safe_load((NSTEP/'config.yaml').read_text(encoding='utf8'))['base_config'];assert base==old['base_config']
    assert base['baselines']['ki']==.08 and base['environment']['dt_s']==1 and base['plant']['rated_power_w']==[5000000]*3
    manifest=read_json(PARENTS);parents={};protected=dict(old['protected_hashes'])
    for p in manifest['candidates']:
        assert not p['selected_by_test'];verify({p['checkpoint']:p['sha256']})
        a,_=NStepMADDPG.load(p['checkpoint'],expected_n=8)
        assert fingerprint(state(a))==old['parents'][str(p['run'])]['initial_state_fingerprint']
        parents[str(p['run'])]=dict(checkpoint=p['checkpoint'],sha256=p['sha256'],selected_step=p['selected_step'],actor_sha256=actor_hash(a),state_fingerprint=fingerprint(state(a)))
    pairs=[(dict(c,collection='known'),w) for c,w in known_cases()]
    validation=read_json(ACTOR/'validation_bank/manifest.json');verify(validation['hashes'])
    pairs += [(dict(c,collection='validation'),InflowTrace.load(c['path'])) for c in validation['cases']]
    assert len(pairs)==54 and all(c['family'] in FAMILIES and c['split']!='stress' for c,w in pairs)
    winds={};cases=[]
    import hashlib
    for c,w in pairs:
        identity=hashlib.sha256(np.asarray(w.values,dtype=np.float64).tobytes()).hexdigest()
        if identity not in winds:
            path=root/'winds'/f'{identity}.csv';path.parent.mkdir(exist_ok=True);w.save(path);winds[identity]=str(path)
        cases.append({k:v for k,v in dict(c,path=winds[identity],wave_sha256=identity).items() if k not in ['csv_sha256','json_sha256']})
    js(root,root/'case_manifest.json',dict(seed=42,cases=cases,slots=54,unique_waveforms=len(winds),not_independent_slot_count=True))
    by_id={c['id']:c for c in cases};references=[];reference_rows=[]
    for collection in ('known','validation'):
        expected={c['id'] for c in cases if c['collection']==collection}
        for arm,run in [('parent',r) for r in range(3)]+[('p',-1),('pi',-1)]:
            if arm=='parent' and collection=='validation':
                folder=ACTOR/f'replay_run{run}/step_00000000/attempt_000';commit=read_json(folder/'commit.json');verify(commit['hashes'])
                saved=torch.load(folder/'state.pth',map_location='cpu',weights_only=False)
                identity=hashlib.sha256(b''.join(v.numpy().tobytes() for v in saved['actors'].values())).hexdigest()
                assert identity==parents[str(run)]['actor_sha256']
                metrics=folder/'validation_metrics.csv';trace=folder/'validation_traces.csv.gz'
            else:
                label=f'replay_run{run}_initial' if arm=='parent' else arm
                folder=ACTOR/f'evaluations/{collection}/{label}/attempt_000';done=read_json(folder/'complete.json');verify(done['hashes'])
                assert done['actor_identity']==(parents[str(run)]['actor_sha256'] if arm=='parent' else arm)
                metrics=folder/'metrics.csv';trace=trace_location(folder)
                protected[str(folder/'complete.json')]=digest(folder/'complete.json')
            ms=read_csv(metrics);ts=gz_rows(trace);groups={}
            for t in ts:groups.setdefault(t['case_id'],[]).append(t)
            assert set(groups)=={m['case_id'] for m in ms}==expected
            for m in ms:
                c=by_id[m['case_id']];series=groups[m['case_id']];recomputed=episode_metrics(series)
                weather=InflowTrace.load(c['path']).values.astype(np.float32)
                for t in series:
                    assert float(t['decision_wind_m_s'])==float(weather[int(t['decision_step']),0]) and float(t['response_wind_m_s'])==float(weather[int(t['response_step']),0])
                    assert float(t['target_w'])==c['target_w'] and float(t['initial_pitch_rad'])==c['initial_pitch_rad']
                for k,v in recomputed.items():
                    if k not in ('case_id','split','family'):assert abs(float(m[k])-float(v))<1e-9
                reference_rows.append(dict(arm=arm,run=run,collection=collection,wave_sha256=c['wave_sha256'],**recomputed))
            protected[str(metrics)]=digest(metrics);protected[str(trace)]=digest(trace)
            references.append(dict(arm=arm,run=run,collection=collection,metrics=str(metrics),traces=str(trace),metrics_sha256=digest(metrics),traces_sha256=digest(trace),cases=len(ms)))
    assert len(reference_rows)==270
    table(root,root/'reference_metrics.csv',reference_rows);js(root,root/'reference_reuse.json',dict(references=references,new_plant_rows=0,config_exact=True,native_metrics_recomputed=True))
    inputs=[PARENTS,OLD_CASES,ACTOR/'config.yaml',ACTOR/'validation_bank/manifest.json',SOURCE/'config.yaml',SOURCE/'pitch_wind_preflight.csv',
            HERE/'PITCH_INTEGRAL_DIAGNOSTIC_PROTOCOL.md',HERE.parent/'tests/test_pitch_integral_diagnostic.py']
    inputs+=list(HERE.glob('pitch_integral_*.py'))
    for path in inputs:protected[str(path.resolve())]=digest(path)
    settings=dict(seed=42,experiment='frozen_n8_integral_feasibility_v1',source_commit='5d34e612580e64092a96b40f5b8509926baf771c',base_config=base,parents=parents,
        formal_training_steps=0,optimizer_updates=0,new_test_steps=0,plant_rows_limit=ROWS,mock_rows=0,storage_limit_bytes=LIMIT,
        planned_hybrid_rows=3*54*129,planned_zero_engineering_rows=3*129,planned_total_new_rows=21285,
        correction=dict(limit_rad=.02,ki_rad_per_normalized_error_s=.08,error_index=9,error_scale_w=15e6,dt_s=1.,use_old_integral_this_action=True,conditional_any_unit_target_saturation=True),
        acceptance=dict(primary_mean_ratio_max=.95,primary_improved_runs_min=2,other_family_mean_worst_max=1.05,travel_and_rms_ratio_max=1.10,motion_floor=1e-4,pi_failures_must_not_increase=True),
        unique_waveforms=len(winds),protected_hashes=protected)
    put(root,root/'config.yaml',yaml.safe_dump(settings,allow_unicode=True,sort_keys=False).encode('utf8'))
    js(root,root/'input_lock.json',dict(hashes={str(p):digest(p) for p in list((root/'winds').iterdir())+[root/'case_manifest.json',root/'reference_metrics.csv',root/'reference_reuse.json']}))
    print(dict(prepared=str(root),unique_waveforms=len(winds),slots=54,reused_reference_metrics=270,new_plant_rows=0),flush=True)


def rollout(env,agent,case,enabled):
    from ..environments.farm_inflow import InflowTrace
    from .pitch_action_diagnostic import reset_case
    from .pitch_gamma_trial import row_step
    from .pitch_integral_controller import FrozenPitchIntegral
    obs,info=reset_case(env,case,InflowTrace.load(case['path']))
    control=FrozenPitchIntegral(env,agent,env._integral_baselines,enabled=enabled);control.reset();rows=[]
    for _ in range(128):
        action=control.act(obs);following,reward,done,truncated,after=env.step(action)
        row=row_step(env,obs,action,reward,info,after,case)
        row.update(control.last);rows.append(row);obs,info=following,after
    assert done and not truncated and rows[0]['integral_used_rad']==0
    return rows


def engineering(root):
    import unittest
    from .nstep_algorithm import NStepMADDPG
    from .pitch_gamma_trial import fingerprint,state
    from .pitch_gamma_review import gz_rows
    root,cfg=context(root);folder=root/'engineering';folder.mkdir(exist_ok=False)
    suite=unittest.defaultTestLoader.loadTestsFromName('optimization_control.tests.test_pitch_integral_diagnostic')
    log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    put(root,folder/'tests.txt',log.getvalue().encode('utf8'));assert result.wasSuccessful() and result.testsRun==4
    cases=read_json(root/'case_manifest.json')['cases'];case=next(c for c in cases if c['id']=='train_episode_8_initial_0.025')
    refs=read_json(root/'reference_reuse.json')['references'];meter=Meter(root);env=environment(cfg,meter);env._integral_baselines=cfg['base_config']['baselines'];proof=[]
    try:
        for run in range(3):
            a,_=NStepMADDPG.load(cfg['parents'][str(run)]['checkpoint'],expected_n=8);before=fingerprint(state(a));start=meter.count
            rows=rollout(env,a,case,False)
            ref=next(x for x in refs if x['arm']=='parent' and x['run']==run and x['collection']=='known')
            original=[r for r in gz_rows(ref['traces']) if r['case_id']==case['id']];difference=0.
            for x,y in zip(rows,original):
                for k in y:
                    if k in ('case_id','split','family'):assert x[k]==y[k]
                    else:difference=max(difference,abs(float(x[k])-float(y[k])))
            assert difference==0 and len(original)==128 and meter.count-start==129 and fingerprint(state(a))==before
            table(root,folder/f'zero_run{run}.csv.gz',rows,True);proof.append(dict(run=run,all_original_trace_fields_max_difference=difference,plant_rows=129,frozen_full_state_unchanged=True))
    finally:meter.close()
    js(root,root/'engineering.json',dict(status='passed',tests=4,mock_plant_rows=0,real_plant_rows=387,zero_correction=proof,training_steps=0,optimizer_updates=0,
        files={str(p):digest(p) for p in folder.iterdir()}))
    print(dict(engineering='passed',tests=4,real_rows=387,mock_rows=0),flush=True)


def run(root):
    from .nstep_algorithm import NStepMADDPG
    from .pitch_gamma_trial import state,fingerprint,episode_metrics
    root,cfg=context(root);proof=read_json(root/'engineering.json');verify(proof['files']);assert proof['status']=='passed'
    cases=read_json(root/'case_manifest.json')['cases'];folder=root/'hybrid';folder.mkdir(exist_ok=False)
    meter=Meter(root);env=environment(cfg,meter);env._integral_baselines=cfg['base_config']['baselines'];metrics=[];jobs=[]
    try:
        for run_id in range(3):
            a,_=NStepMADDPG.load(cfg['parents'][str(run_id)]['checkpoint'],expected_n=8);before=fingerprint(state(a));start=meter.count
            assert before==cfg['parents'][str(run_id)]['state_fingerprint']
            for i,c in enumerate(cases):
                case_start=meter.count;rows=rollout(env,a,c,True);assert meter.count-case_start==129
                path=folder/f'run{run_id}'/f'case_{i:02d}.csv.gz';table(root,path,rows,True)
                metrics.append(dict(arm='hybrid',run=run_id,collection=c['collection'],wave_sha256=c['wave_sha256'],**episode_metrics(rows),
                                    integral_mean_rad=sum(r['integral_used_rad'] for r in rows)/128,
                                    integral_max_abs_rad=max(abs(r['integral_used_rad']) for r in rows),
                                    integral_blocked_fraction=sum(r['integral_blocked'] for r in rows)/128,trace_path=str(path),trace_sha256=digest(path)))
                if (i+1)%9==0:print(dict(run=run_id,completed_cases=i+1,total_cases=54,actual_rows=meter.count),flush=True)
            assert fingerprint(state(a))==before
            jobs.append(dict(run=run_id,new_rows=meter.count-start,full_frozen_state_unchanged=True))
        assert len(metrics)==162 and meter.count==21285
    finally:meter.close()
    table(root,root/'hybrid_metrics.csv',metrics);js(root,root/'run_complete.json',dict(status='complete',jobs=jobs,actual_plant_rows=meter.count,mock_rows=0,
        training_steps=0,optimizer_updates=0,new_test_steps=0,storage_bytes=size(root),config_sha256=digest(root/'config.yaml')))
    print(dict(run='complete',rows=meter.count,storage_bytes=size(root)),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','engineering','run','report']);p.add_argument('--output',required=True);a=p.parse_args()
    activate_runtime(ORIGINAL/'.venv/pinn_tf216');import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    if a.mode=='report':
        from .pitch_integral_report import report
        report(a.output)
    else:globals()[a.mode](a.output)


if __name__=='__main__':main()
