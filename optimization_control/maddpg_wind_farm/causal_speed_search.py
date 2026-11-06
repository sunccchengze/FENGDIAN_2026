"""Experimental causal speed rolling search; no learning or public env changes."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import pickle
import time

from .anchor_closeout import sha,read_json,write_json,read_csv,write_csv,verify_hashes,checked_output

DEFAULT=Path(__file__).with_name('configs')/'causal_speed_search.yaml'
CURRENT_FIELDS=('config','rated','dt','horizon','wind_scale','low','high','initial','heading_mode','control_mask',
    'reference_schedule','speed_reference_mode','mapper','actuator','actuator_commands','actuator_applied',
    't','_done','target','wind_base','wind','power','effective_wind','applied','heading','previous_action',
    'last_action_change','saturation_fraction','reward_terms','rng')


def candidates(radius=.1):
    import numpy as np
    values=[np.zeros(3),np.full(3,-radius),np.full(3,radius)]
    for i in range(3):
        for sign in (-1,1):
            a=np.zeros(3);a[i]=sign*radius;values.append(a)
    return np.asarray(values)


def capture(env):
    # No getattr/array read of trajectory, inflow_trace, or future metadata.
    return {key:deepcopy(getattr(env,key)) for key in CURRENT_FIELDS}


def state_sha(env):return hashlib.sha256(pickle.dumps(capture(env),protocol=5)).hexdigest()


def fork(current,plant,env_type):
    import numpy as np
    child=object.__new__(env_type);child.__dict__=deepcopy(current);child.plant=plant
    child.trajectory=np.tile(child.wind,(child.horizon+1,1)).astype(np.float32)
    child.inflow_trace=None;child.wind_metadata={'forecast':'current_persistence_only'}
    return child


def command(parent,obs,offset):
    import numpy as np
    action=parent.act(obs);baseline=action.copy()
    action[:,2]=np.clip(action[:,2]+2*np.asarray(offset)/.667,-1,1)
    assert np.array_equal(action[:,:2],baseline[:,:2])
    assert np.max(np.abs(action[:,2]-baseline[:,2]))*.667/2<=.1000001
    return action.astype(np.float32),baseline


class Budget:
    def __init__(self,path=None,limit=100000):
        self.path=Path(path) if path is not None else None;self.limit=limit
        self.data=read_json(self.path) if self.path is not None and self.path.exists() else dict(limit=limit,scopes=[])
        assert self.data['limit']==limit
        self.active=None
    def save(self):
        if self.path is not None:write_json(self.path,self.data)
    def start(self,name,reserve):
        if self.active is not None or any(r['name']==name for r in self.data['scopes']):raise ValueError('scope already run or active; incomplete work retained')
        charged=sum(r['actual'] if r['status']=='complete' else r['reserve'] for r in self.data['scopes'])
        if charged+reserve>self.limit:raise RuntimeError('model-row budget reservation exceeded')
        self.active=dict(name=name,reserve=reserve,actual=0,api_calls=0,status='running',kinds={})
        self.data['scopes'].append(self.active);self.save()
    def take(self,rows,kind):
        if self.active is None:raise RuntimeError('every model forward needs an active reserved scope')
        if self.active['actual']+rows>self.active['reserve']:raise RuntimeError('scope model-row reserve exceeded')
        self.active['actual']+=rows;self.active['api_calls']+=1
        self.active['kinds'][kind]=self.active['kinds'].get(kind,0)+rows
    def finish(self):
        result=deepcopy(self.active);self.active['status']='complete';self.save();self.active=None
        result['status']='complete';return result


class Meter:
    def __init__(self,predictor,budget):self.predictor,self.budget,self.kind=predictor,budget,'unspecified'
    def __call__(self,x):
        self.budget.take(len(x),self.kind)
        return self.predictor(x)


def plan(env,parent,p,meter):
    import numpy as np
    before=state_sha(env);current=capture(env);scores=[];last_pitches=[]
    horizon=min(p['prediction_steps'],env.horizon-env.t)
    started=time.perf_counter();old_kind=meter.kind;meter.kind='internal_forecast'
    for offset in candidates():
        branch=fork(current,env.plant,type(env));obs=branch._observe();errors=[]
        for _ in range(horizon):
            action,_=command(parent,obs,offset);obs,_,_,_,info=branch.step(action)
            errors.append(info['error_w']/1e6)
        scores.append(float(np.mean(np.square(errors))));last_pitches.append(action[:,1].tolist())
    meter.kind=old_kind
    chosen=0
    for i,value in enumerate(scores):
        if value<scores[chosen]-p['strict_cost_tolerance']:chosen=i
    assert state_sha(env)==before
    return candidates()[chosen],dict(step=env.t,chosen=chosen,costs_MW2=scores,last_pitch_commands=last_pitches,
        predicted_steps=horizon,model_rows=9*horizon,wall_seconds=time.perf_counter()-started,current_state_sha256=before,
        current_wind=env.wind.tolist())


def read_protocol():
    import yaml
    p=yaml.safe_load(DEFAULT.read_text(encoding='utf-8'))
    assert p['seed']==42 and (p['prediction_steps'],p['decision_interval'])==(12,8)
    assert p['speed_radius_rad_s']==.1 and p['model_row_hard_cap']==100000 and p['formal_RL_steps']==0
    return p


def prepare(root):
    import yaml
    import numpy as np
    from .speed_nstep_training import episode
    from ..environments.farm_inflow import InflowTrace
    repo=Path(__file__).resolve().parents[2];source=repo/'optimization_control/experiments/20261029_speed_nstep_control'
    root=checked_output(root,repo,Path('.'));p=read_protocol()
    old=yaml.safe_load((source/'config.yaml').read_text(encoding='utf-8'));selection=read_json(source/'selection.json')
    assert read_json(source/'git_delivery.json')['commit']=='7ad33692591ec458e8995e1dbfb75b11522e57d7'
    protected=dict(old['source_hashes']);protected.update(selection['hashes'])
    for name in ('config.yaml','selection.json','validation_metrics.csv','validation_trajectories.csv','training_wind_preflight.csv','bank/manifest.json','git_delivery.json','output_manifest.csv'):
        protected[str(source/name)]=sha(source/name)
    for path,digest in old['executed_code_hashes'].items():protected[path]=digest
    verify_hashes(protected)
    root.mkdir(parents=True,exist_ok=False);(root/'bank').mkdir()
    manifest=[];preflight=read_csv(source/'training_wind_preflight.csv');validation=read_json(source/'bank/manifest.json')['cases']
    for split in ('train','validation'):
        for run in range(3):
            for family in p['families']:
                for target in p['train_targets_w'] if split=='train' else p['validation_targets_w']:
                    if split=='train':
                        row=next(r for r in preflight if int(r['run_id'])==run and r['family']==family and float(r['target_w'])==target)
                        number=int(row['episode']);wind,_,pitch,_=episode(old['protocol'],run,number)
                        assert hashlib.sha256(wind.values.tobytes()).hexdigest()==row['values_sha256']
                        source_case=None
                    else:
                        row=next(r for r in validation if r['family']==family and r['target_w']==target)
                        path=source/'bank'/row['path'];assert sha(path)==row['csv_sha256']
                        wind=InflowTrace.load(path);pitch=row['initial_pitch_rad'];number=None;source_case=row['id']
                        protected[str(path)]=sha(path);protected[str(path.with_suffix('.json'))]=sha(path.with_suffix('.json'))
                    cid=f'{split}_run{run}_{family}_{int(target)}';path=root/'bank'/f'{cid}.csv';wind.save(path)
                    manifest.append(dict(case_id=cid,split=split,run_id=run,family=family,target_w=target,initial_pitch_rad=pitch,
                        initial_wind_direction_rad=float(np.float32(wind.values[0,1])),path=path.name,csv_sha256=sha(path),json_sha256=sha(path.with_suffix('.json')),source_case_id=source_case,source_episode=number))
    write_json(root/'bank/manifest.json',dict(seed=42,cases=manifest))
    code={str(path):sha(path) for path in [Path(__file__),Path(__file__).with_name('causal_speed_report.py'),DEFAULT,
        Path(__file__).with_name('SPEED_CAUSAL_SEARCH_PROTOCOL.md'),repo/'optimization_control/tests/test_causal_speed_search.py']}
    for folder in ('environments','utils'):
        for path in (repo/'optimization_control'/folder).glob('*.py'):code[str(path)]=sha(path)
    saved=dict(seed=42,protocol=p,base_config=old['base_config'],parents=old['parents'],selection=selection,
        source=str(source),worktree=str(repo),source_hashes=protected,executed_code_hashes=code,
        bank_sha256=sha(root/'bank/manifest.json'),source_inventory=sorted(str(path) for path in source.rglob('*') if path.is_file()),
        source_manifest_sha256=sha(source/'output_manifest.csv'),conservative_reserve=84106)
    (root/'config.yaml').write_text(yaml.safe_dump(saved,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    write_csv(root/'metrics.csv',[dict(status='prepared',formal_RL_steps=0)])
    write_json(root/'summary.txt',dict(seed=42,status='prepared',formal_RL_steps=0,max_model_rows=100000))


def context(root):
    import yaml
    saved=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    checked_output(root,saved['worktree'],Path('.'))
    verify_hashes(saved['source_hashes']);verify_hashes(saved['executed_code_hashes'])
    assert sha(root/'bank/manifest.json')==saved['bank_sha256']
    return saved,saved['protocol']


def setup(saved,root):
    from .workflow import build_env
    env=build_env(saved['base_config']);budget=Budget(root/'budget.json')
    meter=Meter(env.plant.predictor,budget);env.plant.predictor=meter
    return env,budget,meter


def precheck(root):
    import numpy as np
    from .algorithm import MADDPG
    saved,p=context(root);env,budget,meter=setup(saved,root)
    tests=read_json(root/'tests.json');assert tests['passed']
    budget.start('unit_mock_correctness',1000);budget.take(tests['mock_model_rows'],'mock_correctness')
    budget.active['api_calls']=tests['mock_api_calls'];budget.finish()
    budget.start('real_precheck',1000-tests['mock_model_rows'])
    parent,_=MADDPG.load(saved['parents'][0]['checkpoint'])
    meter.kind='precheck_external';obs,_=env.reset(seed=42,options=dict(wind_trajectory=np.tile([9.,0.,.08],(129,1)),target_w=3.2e6))
    for _ in range(4):obs,*_=env.step(parent.act(obs))
    x=np.tile(np.r_[env.wind,env.applied[:,0],env.applied[:,1],env.applied[:,2]],(9,1))
    x[:,9:12]=np.clip(x[:,9:12]+candidates(),env.low[2],env.high[2])
    meter.kind='batch_single_gate';batch=meter(x);single=np.concatenate([meter(row[None]) for row in x])
    delta=np.abs(batch-single).max(axis=0)
    before=state_sha(env);a,first=plan(env,parent,p,meter)
    # Different *synthetic* future in the external world, never used by plan().
    env.trajectory[env.t+1:,0]=9.2
    b,second=plan(env,parent,p,meter)
    np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(first['costs_MW2'],second['costs_MW2'])
    assert state_sha(env)==before
    current=capture(env);left=fork(current,env.plant,type(env));right=fork(current,env.plant,type(env))
    left.rng.normal();assert pickle.dumps(env.rng.bit_generator.state)==pickle.dumps(right.rng.bit_generator.state)
    left=fork(current,env.plant,type(env));meter.kind='zero_branch_check'
    for _ in range(12):
        a=command(parent,left._observe(),np.zeros(3))[0];b=parent.act(right._observe())
        np.testing.assert_array_equal(a,b);oa,*_=left.step(a);ob,*_=right.step(b);np.testing.assert_array_equal(oa,ob)
    assert state_sha(env)==before
    result=dict(passed=True,batch_vs_single_max_abs_delta=delta.tolist(),production_inference='single_sample_only',
        future_change_did_not_change_plan=True,source_state_unchanged=True,clone_rng_independent=True,zero_branch_exact=True,
        budget=budget.finish())
    write_json(root/'precheck.json',result);print(result,flush=True)


def trace_row(info):
    row=dict(step=info['step'],farm_power_w=info['farm_power_w'],error_w=info['error_w'],target_w=info['target_w'],
        wind_m_s=float(info['wind'][0]),direction_rad=float(info['wind'][1]),ti=float(info['wind'][2]))
    for i in range(3):
        row.update({f'power_{i+1}_w':float(info['power_w'][i]),f'ueff_{i+1}_m_s':float(info['effective_wind_m_s'][i]),
            f'heading_{i+1}_rad':float(info['heading_rad'][i])})
        for j,name in enumerate(('gamma','pitch','speed')):
            row[f'{name}_{i+1}']=float(info['applied'][i,j]);row[f'command_{i+1}_{j}']=float(info['executed_action'][i,j])
    return row


def run(root):
    import numpy as np
    from .algorithm import MADDPG
    from .speed_nstep_algorithm import FrozenSpeedNStepMADDPG
    from .controllers import PitchController
    from ..environments.farm_inflow import InflowTrace
    from .causal_speed_report import metric
    saved,p=context(root)
    assert read_json(root/'precheck.json')['passed']
    if (root/'complete.json').exists():raise ValueError('completed search cannot be rerun')
    env,budget,meter=setup(saved,root)
    source=Path(saved['source']);oldtraces=read_csv(source/'validation_trajectories.csv')
    lookup={}
    for row in oldtraces:lookup.setdefault((row['arm'],int(row['run_id']),row['controller'],row['case_id']),[]).append(row)
    metrics=[];all_traces=[]
    for case in read_json(root/'bank/manifest.json')['cases']:
        folder=root/'cases'/case['case_id']
        if folder.exists():raise ValueError('case retained; no implicit rerun or hidden budget reuse')
        folder.mkdir(parents=True)
        wind=InflowTrace.load(root/'bank'/case['path']);assert sha(root/'bank'/case['path'])==case['csv_sha256']
        run_id=case['run_id'];parent,_=MADDPG.load(saved['parents'][run_id]['checkpoint'])
        modes=['search','parent','n1_selected','n1_final','n8_selected','n8_final','p','pi']
        for label in modes:
            scope=f"{case['case_id']}:{label}";plans=[];demonstrations=[]
            reused=case['split']=='validation' and label!='search'
            if reused:
                arm,run,role=('parent',run_id,'parent') if label=='parent' else ('common',-1,label) if label in ('p','pi') else (label[:2],run_id,label[3:])
                raw=lookup[(arm,run,role,case['source_case_id'])]
                assert len(raw)==128
                fields=['step','farm_power_w','error_w','target_w','wind_m_s','direction_rad','ti']
                # Old column names include explicit physical units for these three fields.
                fields=fields[:7]+[k for i in (1,2,3) for k in
                    (f'power_{i}_w',f'ueff_{i}_m_s',f'heading_{i}_rad',f'gamma_{i}',f'pitch_{i}',f'speed_{i}',
                     f'command_{i}_0',f'command_{i}_1',f'command_{i}_2')]
                rows=[{k:float(row[k]) for k in fields} for row in raw];spent=dict(actual=0,kinds={},status='reused_validation')
            else:
                budget.start(scope,1857 if label=='search' else 129)
                meter.kind='external_reset';env.initial=np.asarray(saved['base_config']['environment']['initial_operating_point'],float).copy()
                env.initial[1]=case['initial_pitch_rad']
                obs,_=env.reset(seed=42,options=dict(wind_trajectory=wind.values,target_w=case['target_w']))
                policy=parent
                if label.startswith(('n1_','n8_')):
                    arm,role=label.split('_');result=next(r for r in saved['selection']['results'] if r['arm']==arm and r['run_id']==run_id)
                    policy,_=FrozenSpeedNStepMADDPG.load(result[role],expected_n=1 if arm=='n1' else 8)
                controller=PitchController(env,saved['base_config']['baselines'],label) if label in ('p','pi') else None
                rows=[];offset=np.zeros(3)
                for t in range(128):
                    before=obs.copy()
                    if label=='search':
                        if t%8==0:
                            offset,details=plan(env,parent,p,meter);plans.append(details)
                        action,reference=command(parent,obs,offset)
                        demonstrations.append(dict(obs=before,action=action.copy(),parent_action=reference,offset=offset.copy(),decision=t%8==0))
                    else:action=controller.act(obs) if controller else policy.act(obs)
                    meter.kind='external_transition';obs,_,done,_,info=env.step(action)
                    np.testing.assert_array_equal(info['executed_action'],env.project_action(action) if not done else action)
                    rows.append(trace_row(info))
                assert done
                spent=budget.finish()
            # Uniform external trace schema, including reused paths; all numeric fields retained.
            tags={k:case[k] for k in ('case_id','split','run_id','family','target_w','initial_pitch_rad')};tags['controller']=label
            rows=[dict(**tags,**{k:v for k,v in row.items() if k not in tags}) for row in rows]
            m=metric(rows,case,saved['base_config'],plans,spent)
            write_csv(folder/f'{label}.csv',rows);write_json(folder/f'{label}.json',dict(metric=m,plans=plans,budget=spent,reused=reused))
            if demonstrations:
                np.savez_compressed(folder/'causal_demonstrations.npz',
                    **{k:np.asarray([d[k] for d in demonstrations]) for k in demonstrations[0]})
            metrics.append(m);all_traces.extend(rows)
        write_json(folder/'complete.json',{path.name:sha(path) for path in folder.iterdir() if path.is_file()})
        print('Completed',case['case_id'],'model rows',sum(r['actual'] for r in budget.data['scopes']),flush=True)
    write_csv(root/'metrics.csv',metrics);write_csv(root/'trajectories.csv',all_traces)
    context(root)
    actual=sum(r['actual'] for r in budget.data['scopes']);assert actual<=100000
    execution=dict(seed=42,status='executed',formal_RL_steps=0,model_rows=actual,
        api_calls=sum(r['api_calls'] for r in budget.data['scopes']),full_cases=36,metrics=len(metrics),trace_rows=len(all_traces))
    write_json(root/'summary.txt',execution);write_json(root/'execution_summary.json',execution)
    write_json(root/'complete.json',{name:sha(root/name) for name in ('config.yaml','metrics.csv','trajectories.csv','budget.json','execution_summary.json')})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('prepare','precheck','run','verify','figures'))
    parser.add_argument('--output',required=True);args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    import os
    os.environ.setdefault('TF_NUM_INTRAOP_THREADS','1');os.environ.setdefault('TF_NUM_INTEROP_THREADS','1')
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    root=Path(args.output).resolve()
    if args.command in ('verify','figures'):
        from . import causal_speed_report
        getattr(causal_speed_report,args.command)(root)
    else:globals()[args.command](root)


if __name__=='__main__':main()
