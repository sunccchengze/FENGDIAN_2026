"""Frozen independent test with read-only dependencies, bounded disk and measured planning."""
from pathlib import Path
from copy import deepcopy
import argparse
import csv
import ctypes
import hashlib
import io
import json
import os
import pickle
import platform
import subprocess
import sys
import time
from . import causal_speed_search as old
from .history_speed_search import plan as native_plan,Persistence
from .anchor_closeout import read_json,read_csv,sha,verify_hashes,checked_output

DEFAULT=Path(__file__).with_name('configs')/'history_independent_test.yaml'
LIMIT=1073741824


class Artifacts:
    def __init__(self,root):self.root=Path(root).resolve()
    def size(self):return sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
    def ensure(self,extra):
        if self.size()+extra>LIMIT:raise RuntimeError('new experiment artifact hard cap 1 GiB exceeded')
    def write(self,name,data):
        path=(self.root/name).resolve()
        if not path.is_relative_to(self.root):raise ValueError('output escaped new experiment')
        self.ensure(max(0,len(data)-(path.stat().st_size if path.exists() else 0)))
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    def json(self,name,value):self.write(name,json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8'))
    def csv(self,name,rows):
        buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        self.write(name,buffer.getvalue().encode('utf-8'))
    def npz(self,name,**values):
        import numpy as np
        with io.BytesIO() as buffer:np.savez_compressed(buffer,**values);self.write(name,buffer.getvalue())


class TestBudget(old.Budget):
    def save(self):
        if self.path is not None:Artifacts(self.path.parent).json(self.path.name,self.data)


def stamp():
    result=dict(utc_ns=time.time_ns(),perf_ns=time.perf_counter_ns(),process_cpu_ns=time.process_time_ns(),pid=os.getpid())
    if os.name=='nt':
        from ctypes import wintypes
        kernel=ctypes.windll.kernel32;kernel.GetTickCount64.restype=ctypes.c_ulonglong
        result['uptime_ms']=int(kernel.GetTickCount64());awake=ctypes.c_ulonglong()
        result['awake_100ns']=int(awake.value) if kernel.QueryUnbiasedInterruptTime(ctypes.byref(awake)) else None
        idle,kern,user=wintypes.FILETIME(),wintypes.FILETIME(),wintypes.FILETIME()
        if kernel.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kern),ctypes.byref(user)):
            for name,value in [('machine_idle_100ns',idle),('machine_kernel_100ns',kern),('machine_user_100ns',user)]:
                result[name]=(int(value.dwHighDateTime)<<32)+int(value.dwLowDateTime)
    return result


def elapsed(before,after):
    return dict(wall_seconds=(after['perf_ns']-before['perf_ns'])/1e9,cpu_seconds=(after['process_cpu_ns']-before['process_cpu_ns'])/1e9,
        utc_seconds=(after['utc_ns']-before['utc_ns'])/1e9,start=before,end=after)


def measured_plan(env,parent,meter,model,history):
    before=stamp();offset,details=native_plan(env,parent,meter,model,history);timing=elapsed(before,stamp())
    details['native_wall_seconds']=details['wall_seconds'];details['wall_seconds']=timing['wall_seconds'];details['timing']=timing
    return offset,details


def context(root,released=False):
    import yaml
    cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify_hashes(cfg['source_hashes'])
    if released:
        release=read_json(root/'release.json');verify_hashes(release['executed_code_hashes'])
        assert release['config_sha256']==sha(root/'config.yaml') and release['manifest_sha256']==sha(root/'bank/manifest.json')
        verify_hashes({str(root/k):v for k,v in release['new_wind_hashes'].items()})
    return cfg


def prepare(root):
    import yaml
    repo=Path(__file__).resolve().parents[2];source=repo/'optimization_control/experiments/20261029_history_forecast'
    root=checked_output(root,repo,Path('.'))
    if root.parent!=repo/'optimization_control/experiments':raise ValueError('new sibling experiment only; archives are read-only')
    p=yaml.safe_load(DEFAULT.read_text(encoding='utf-8'));saved=yaml.safe_load((source/'config.yaml').read_text(encoding='utf-8'))
    assert read_json(source/'git_delivery.json')['commit']==p['source_commit']
    candidate=read_json(source/'candidate_manifest.json');assert candidate['model_sha256']==p['forecast_model_sha256']==sha(candidate['model'])
    assert p['formal_model_rows']==108*3325+90*129==370710 and p['model_row_hard_cap']==375000
    protected=dict(saved['source_hashes']);protected.update(saved['executed_code_hashes']);protected.update(read_json(source/'loop_code_lock.json'))
    for name in ('candidate_manifest.json','next_test_proposal.json','forecast_model.npz','config.yaml','git_delivery.json','bank_manifest.json','precheck.json','verification.json','delivery_verification.json'):
        protected[str(source/name)]=sha(source/name)
    verify_hashes(protected);root.mkdir(parents=True,exist_ok=False);store=Artifacts(root)
    cfg=dict(seed=42,protocol=p,worktree=str(repo),source=str(source),model=candidate['model'],parents=saved['parents'],base_config=saved['base_config'],
        source_hashes=protected,source_inventory=sorted(str(x) for x in source.rglob('*') if x.is_file()))
    store.write('config.yaml',yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False).encode('utf-8'))
    store.json('space_budget.json',dict(user_report_existing_D_VSCODE_GiB=67.93,expected_new_bytes=67108864,hard_cap_bytes=LIMIT,
        available_drive_bytes=__import__('shutil').disk_usage(root).free,old_models_worktrees_replays_copied=0))
    store.csv('metrics.csv',[dict(status='prepared',formal_RL_steps=0)]);store.json('summary.txt',dict(status='prepared',formal_RL_steps=0,forecast_refits=0))


def precheck(root):
    import numpy as np
    from .workflow import build_env
    from .algorithm import MADDPG
    from .history_wind_forecast import RidgeForecast
    cfg=context(root);store=Artifacts(root);tests=read_json(root/'tests.json');assert tests['passed']
    budget=TestBudget(root/'budget.json',limit=375000);budget.start('mock_equivalence',1000);budget.take(tests['mock_model_rows'],'mock_equivalence')
    budget.active['api_calls']=tests['mock_api_calls'];budget.finish()
    budget.start('real_equivalence',1000);env=build_env(cfg['base_config']);meter=old.Meter(env.plant.predictor,budget);env.plant.predictor=meter
    parent,_=MADDPG.load(cfg['parents'][0]['checkpoint']);model=RidgeForecast.load(cfg['model']);meter.kind='precheck_external'
    env.reset(seed=42,options=dict(wind_trajectory=np.tile([9.,0.,.08],(129,1)),target_w=3.2e6));history=[env.wind.copy()]
    for _ in range(4):env.step(parent.act(env._observe()));history.append(env.wind.copy())
    state=old.state_sha(env);rng=pickle.dumps(parent.rng.bit_generator.state);proof=[]
    for label,predictor in [('history17',model),('persistence17',Persistence())]:
        a,x=native_plan(env,parent,meter,predictor,history);b,y=measured_plan(env,parent,meter,predictor,history)
        np.testing.assert_array_equal(a,b)
        for key in ('costs_MW2','predicted_error_w','predicted_wind'):np.testing.assert_array_equal(x[key],y[key])
        assert x['chosen']==y['chosen'] and x['observed_history_sha256']==y['observed_history_sha256']
        proof.append(dict(controller=label,numerical_outputs_exact=True,timing=y['timing']))
    assert state==old.state_sha(env) and rng==pickle.dumps(parent.rng.bit_generator.state)
    store.json('precheck.json',dict(passed=True,proof=proof,state_parent_rng_unchanged=True,budget=budget.finish(),
        reused_engineering_evidence=str(Path(cfg['source'])/'precheck.json'),new_policy_parameters=False))
    print('Equivalent; total rows',sum(x['actual'] for x in budget.data['scopes']),flush=True)


def namespace_check(root):
    cfg=context(root);lo=cfg['protocol']['test_episode_offset'];hi=lo+18;collisions=[];scanned=0
    roots=[Path(cfg['worktree'])/'optimization_control',Path('./optimization_control'),Path('./optimization_control')]
    def find(value,path):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('episode','source_episode') and isinstance(item,int) and lo<=item<hi:collisions.append(dict(path=str(path),episode=item))
                find(item,path)
        elif isinstance(value,list):
            for item in value:find(item,path)
    for directory in roots:
        paths=subprocess.check_output(['rg','--files','--hidden','--no-ignore','-g','*.json',str(directory)],text=True,encoding='utf-8').splitlines()
        for name in paths:
            path=Path(name)
            if path.is_relative_to(root):continue
            scanned+=1;raw=path.read_text(encoding='utf-8-sig')
            if '660000' in raw:find(json.loads(raw),path)
    result=dict(passed=not collisions,actual_episode_fields_scanned=True,JSON_files=scanned,roots=[str(x) for x in roots],range=[lo,hi-1],collisions=collisions)
    Artifacts(root).json('namespace_check.json',result)
    if collisions:raise ValueError('new test namespace already used')


def release(root):
    import numpy as np
    from ..environments.farm_inflow import generate_inflow
    cfg=context(root);store=Artifacts(root)
    assert read_json(root/'precheck.json')['passed']
    if (root/'release.json').exists() or (root/'bank').exists():raise ValueError('test generation already attempted; do not resample')
    namespace_check(root)
    code={str(path):sha(path) for path in (Path(__file__),DEFAULT,Path(__file__).with_name('HISTORY_INDEPENDENT_TEST_PROTOCOL.md'),
        Path(cfg['worktree'])/'optimization_control/tests/test_history_independent_test.py')}
    store.json('execution_lock.json',code);(root/'bank').mkdir()
    old_bank=read_json(Path(cfg['source'])/'bank_manifest.json');seen={x['values_sha256'] for x in old_bank['fit']+old_bank['score']}
    cases=[];hashes={};p=cfg['protocol']
    for family in p['families']:
        for target in p['targets_w']:
            for pitch in p['initial_pitch_rad']:
                i=len(cases);episode=p['test_episode_offset']+i;inflow=deepcopy(cfg['base_config']['environment']['inflow']);inflow['speed']['scenario']=family
                wind=generate_inflow(inflow,dt_s=1,horizon=128,seed=42,split='test',episode=episode)
                digest=hashlib.sha256(wind.values.astype(np.float32).tobytes()).hexdigest();assert digest not in seen;seen.add(digest)
                cid=f'test_{i:02}_{family}_{target}_pitch{int(round(pitch*1000)):03}'
                path=root/'bank'/f'{cid}.csv';store.ensure(1048576);wind.save(path);store.ensure(0)
                for file in (path,path.with_suffix('.json')):hashes[str(file.relative_to(root))]=sha(file)
                cases.append(dict(case_id=cid,split='test',family=family,target_w=target,initial_pitch_rad=pitch,
                    initial_wind_direction_rad=float(np.float32(wind.values[0,1])),episode=episode,path=str(path.relative_to(root)),values_sha256=digest))
    store.json('bank/manifest.json',dict(seed=42,cases=cases,unique_winds=18,parent_stream_cases=54))
    store.json('release.json',dict(source_commit=p['source_commit'],candidate_model_sha256=p['forecast_model_sha256'],config_sha256=sha(root/'config.yaml'),
        manifest_sha256=sha(root/'bank/manifest.json'),new_wind_hashes=hashes,executed_code_hashes=code,precheck_sha256=sha(root/'precheck.json'),
        tests_sha256=sha(root/'tests.json'),released_at=stamp(),forecast_refits=0,formal_RL_steps=0))
    store.json('summary.txt',dict(status='independent_test_released',new_winds=18,formal_RL_steps=0,forecast_refits=0))
    print('Released 18 new winds, artifact bytes',store.size(),flush=True)


def execute_rollout(root,cfg,env,meter,budget,case,parent,label,run_id,model):
    import numpy as np
    from .controllers import PitchController
    from .midgrid_speed_report import metric
    from ..environments.farm_inflow import InflowTrace
    store=Artifacts(root);scope=f"{case['case_id']}_run{run_id}_{label}";rows_required=3325 if label in ('history17','persistence17') else 129
    budget.start(scope,rows_required);whole_start=stamp();meter.kind='external_reset';wind=InflowTrace.load(root/case['path'])
    env.initial=np.asarray(cfg['base_config']['environment']['initial_operating_point'],float).copy();env.initial[1]=case['initial_pitch_rad']
    obs,_=env.reset(seed=42,options=dict(wind_trajectory=wind.values,target_w=case['target_w']));history=[env.wind.copy()]
    baseline=PitchController(env,cfg['base_config']['baselines'],label) if label in ('p','pi') else None
    rng=pickle.dumps(parent.rng.bit_generator.state) if parent is not None else None
    plans=[];data=[];rows=[];step_timing=[];offset=np.zeros(3)
    for t in range(128):
        a_cpu=time.process_time_ns();a_wall=time.perf_counter_ns()
        if label in ('history17','persistence17'):
            if t%8==0:offset,details=measured_plan(env,parent,meter,model if label=='history17' else Persistence(),history);plans.append(details)
            action,reference=old.command(parent,obs,offset)
        else:action=baseline.act(obs) if baseline else parent.act(obs);reference=action.copy()
        action_timing=[(time.process_time_ns()-a_cpu)/1e9,(time.perf_counter_ns()-a_wall)/1e9]
        data.append(dict(obs=obs.copy(),action=action.copy(),parent_action=reference.copy(),offset=offset.copy()))
        a_cpu=time.process_time_ns();a_wall=time.perf_counter_ns();meter.kind='external_transition'
        obs,_,done,_,info=env.step(action);history.append(env.wind.copy())
        step_timing.append(action_timing+[(time.process_time_ns()-a_cpu)/1e9,(time.perf_counter_ns()-a_wall)/1e9])
        np.testing.assert_array_equal(action,info['executed_action']);rows.append(old.trace_row(info))
    assert done and (parent is None or rng==pickle.dumps(parent.rng.bit_generator.state))
    timing=elapsed(whole_start,stamp());spent=budget.finish();assert spent['actual']==rows_required
    tags=dict(case,run_id=run_id);tagged=[dict(**tags,controller=label,**{k:v for k,v in r.items() if k not in tags}) for r in rows]
    m=metric(tagged,tags,cfg['base_config'],plans,spent);m.update(scope=scope,rollout_cpu_seconds=timing['cpu_seconds'],rollout_wall_seconds=timing['wall_seconds'],
        planning_cpu_mean_seconds=float(np.mean([x['timing']['cpu_seconds'] for x in plans])) if plans else 0.,
        action_cpu_mean_seconds=float(np.mean(np.asarray(step_timing)[:,0])),action_wall_mean_seconds=float(np.mean(np.asarray(step_timing)[:,1])))
    path=f'rollouts/{scope}.npz';fields=list(rows[0]);meta=dict(case=tags,controller=label,trace_fields=fields,plans=plans,budget=spent,rollout_timing=timing,
        step_timing_fields=['action_cpu_s','action_wall_s','transition_cpu_s','transition_wall_s'])
    store.npz(path,metadata=np.frombuffer(json.dumps(meta,ensure_ascii=False).encode('utf-8'),dtype=np.uint8),trace=np.asarray([[r[k] for k in fields] for r in rows]),
        step_timing=np.asarray(step_timing),**{k:np.asarray([r[k] for r in data]) for k in data[0]})
    m.update(trace_path=path,trace_sha256=sha(root/path));return m


def run(root):
    from .workflow import build_env
    from .algorithm import MADDPG
    from .history_wind_forecast import RidgeForecast
    cfg=context(root,released=True);store=Artifacts(root)
    if (root/'run_attempt.json').exists():raise ValueError('run already attempted; no hidden repeat')
    store.json('run_attempt.json',dict(started=stamp(),platform=platform.platform(),python=sys.version,executable=sys.executable))
    env=build_env(cfg['base_config']);budget=TestBudget(root/'budget.json',limit=375000);meter=old.Meter(env.plant.predictor,budget);env.plant.predictor=meter
    parents=[MADDPG.load(x['checkpoint'])[0] for x in cfg['parents']];model=RidgeForecast.load(cfg['model']);metrics=[]
    for case in read_json(root/'bank/manifest.json')['cases']:
        for label in ('p','pi'):metrics.append(execute_rollout(root,cfg,env,meter,budget,case,None,label,-1,model))
        for run_id,parent in enumerate(parents):
            for label in ('history17','persistence17','parent'):metrics.append(execute_rollout(root,cfg,env,meter,budget,case,parent,label,run_id,model))
        store.json('progress.json',dict(metrics=metrics,completed_winds=len(metrics)//11,artifact_bytes=store.size()))
        print('Completed wind',case['case_id'],'rollouts',len(metrics),'charged',sum(x['actual'] for x in budget.data['scopes']),'bytes',store.size(),flush=True)
    context(root,released=True);store.csv('metrics.csv',metrics)
    result=dict(status='executed',formal_RL_steps=0,forecast_refits=0,PINN_mock_rows=sum(x['actual'] for x in budget.data['scopes']),
        unique_winds=18,physical_rollouts=len(metrics),transitions=128*len(metrics),artifact_bytes=store.size())
    store.json('summary.txt',result);store.json('complete.json',{k:sha(root/k) for k in ('metrics.csv','budget.json','release.json')})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('prepare','precheck','release','run'));parser.add_argument('--output',required=True);args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    import torch
    os.environ.setdefault('TF_NUM_INTRAOP_THREADS','1');os.environ.setdefault('TF_NUM_INTEROP_THREADS','1');torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    globals()[args.command](Path(args.output).resolve())


if __name__=='__main__':main()
