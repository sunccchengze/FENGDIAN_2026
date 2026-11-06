"""Only add +/-0.05 speed candidates to the frozen nine-point diagnostic."""
from copy import deepcopy
from pathlib import Path
import argparse
import time
import pickle

from . import causal_speed_search as old
from .anchor_closeout import sha,read_json,write_json,read_csv,write_csv,verify_hashes,checked_output

DEFAULT=Path(__file__).with_name('configs')/'midgrid_speed_search.yaml'


def grid():
    import numpy as np
    return np.concatenate((old.candidates(.1),old.candidates(.05)[1:]))


def choose(costs,tolerance=1e-12):
    selected=0
    for i,cost in enumerate(costs):
        if cost<costs[selected]-tolerance:selected=i
    return selected


def plan(env,parent,p,meter):
    import numpy as np
    before=old.state_sha(env);current=old.capture(env);h=min(12,env.horizon-env.t)
    costs=[];errors=[];last_pitch=[];started=time.perf_counter();kind=meter.kind;meter.kind='internal_forecast'
    for offset in grid():
        child=old.fork(current,env.plant,type(env));obs=child._observe();sequence=[]
        for _ in range(h):
            action,_=old.command(parent,obs,offset);obs,_,_,_,info=child.step(action)
            sequence.append(info['error_w'])
        errors.append(sequence);costs.append(float(np.mean(np.square([value/1e6 for value in sequence]))));last_pitch.append(action[:,1].tolist())
    meter.kind=kind;selected=choose(costs)
    assert old.state_sha(env)==before and costs[selected]<=min(costs[:9])+1e-12
    return grid()[selected],dict(step=env.t,chosen=selected,costs_MW2=costs,predicted_error_w=errors,last_pitch_commands=last_pitch,
        predicted_steps=h,model_rows=17*h,wall_seconds=time.perf_counter()-started,current_state_sha256=before,current_wind=env.wind.tolist(),
        best_original9_MW2=min(costs[:9]),best_all17_MW2=costs[selected])


def protocol():
    import yaml
    p=yaml.safe_load(DEFAULT.read_text(encoding='utf-8'))
    assert p['seed']==42 and (p['prediction_steps'],p['decision_interval'],p['candidate_count'])==(12,8,17)
    assert p['outer_radius_rad_s']==.1 and p['middle_radius_rad_s']==.05 and p['hard_cap']==170000
    return p


def prepare(root):
    import yaml
    repo=Path(__file__).resolve().parents[2];source=repo/'optimization_control/experiments/20261029_speed_causal_search'
    root=checked_output(root,repo,Path('.'));p=protocol()
    if root.is_relative_to(source):raise ValueError('original experiment is read-only')
    saved=yaml.safe_load((source/'config.yaml').read_text(encoding='utf-8'))
    assert read_json(source/'git_delivery.json')['commit']==p['source_commit']
    protected=dict(saved['source_hashes']);protected.update(saved['executed_code_hashes'])
    for name in ('config.yaml','metrics.csv','trajectories.csv','bank/manifest.json','budget.json','git_delivery.json','output_manifest.csv'):
        protected[str(source/name)]=sha(source/name)
    for case in read_json(source/'bank/manifest.json')['cases']:
        path=source/'cases'/case['case_id']/'search.json';protected[str(path)]=sha(path)
    verify_hashes(protected)
    root.mkdir(parents=True,exist_ok=False);(root/'bank').mkdir()
    for path in (source/'bank').iterdir():
        if path.is_file():(root/'bank'/path.name).write_bytes(path.read_bytes());protected[str(path)]=sha(path)
    execution={str(path):sha(path) for path in (Path(__file__),Path(__file__).with_name('midgrid_speed_report.py'),DEFAULT,
        Path(__file__).with_name('SPEED_MIDGRID_PROTOCOL.md'),repo/'optimization_control/tests/test_midgrid_speed_search.py')}
    cfg=dict(seed=42,protocol=p,source=str(source),worktree=str(repo),parents=saved['parents'],base_config=saved['base_config'],
        source_hashes=protected,executed_code_hashes=execution,bank_sha256=sha(root/'bank/manifest.json'),
        source_inventory=sorted(str(path) for path in source.rglob('*') if path.is_file()),conservative_reserve=123648)
    (root/'config.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    write_csv(root/'metrics.csv',[dict(status='prepared',formal_RL_steps=0)])
    write_json(root/'summary.txt',dict(status='prepared',seed=42,hard_cap=170000,formal_RL_steps=0))


def context(root):
    import yaml
    cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    checked_output(root,cfg['worktree'],Path('.'))
    verify_hashes(cfg['source_hashes']);verify_hashes(cfg['executed_code_hashes'])
    assert sha(root/'bank/manifest.json')==cfg['bank_sha256']
    return cfg,cfg['protocol']


def setup(cfg,root):
    from .workflow import build_env
    env=build_env(cfg['base_config']);budget=old.Budget(root/'budget.json',limit=170000)
    meter=old.Meter(env.plant.predictor,budget);env.plant.predictor=meter
    return env,budget,meter


def precheck(root):
    import numpy as np
    from .algorithm import MADDPG
    cfg,p=context(root);env,budget,meter=setup(cfg,root);tests=read_json(root/'tests.json');assert tests['passed']
    budget.start('mock_tests',1500);budget.take(tests['mock_model_rows'],'mock_correctness')
    budget.active['api_calls']=tests['mock_api_calls'];budget.finish()
    budget.start('real_precheck',1500-tests['mock_model_rows'])
    parent,_=MADDPG.load(cfg['parents'][0]['checkpoint'])
    meter.kind='precheck_external';env.reset(seed=42,options=dict(wind_trajectory=np.tile([9.,0.,.08],(129,1)),target_w=3.2e6))
    for _ in range(4):env.step(old.command(parent,env._observe(),np.full(3,.1))[0])
    before=old.state_sha(env);rng=pickle.dumps(parent.rng.bit_generator.state)
    _,coarse=old.plan(env,parent,p,meter);_,fine=plan(env,parent,p,meter)
    np.testing.assert_array_equal(coarse['costs_MW2'],fine['costs_MW2'][:9])
    assert fine['best_all17_MW2']<=min(coarse['costs_MW2'])+1e-12
    env.trajectory[env.t+1:]=[9.2,.02,.1]
    _,repeat=plan(env,parent,p,meter);np.testing.assert_array_equal(fine['costs_MW2'],repeat['costs_MW2'])
    zero,reference=old.command(parent,env._observe(),np.zeros(3));np.testing.assert_array_equal(zero,reference)
    assert not np.array_equal(zero[:,2],env.previous_action[:,2])
    a=old.fork(old.capture(env),env.plant,type(env));b=old.fork(old.capture(env),env.plant,type(env));meter.kind='precheck_zero_semantics'
    for _ in range(12):
        oa,*_=a.step(old.command(parent,a._observe(),np.zeros(3))[0]);ob,*_=b.step(parent.act(b._observe()))
        np.testing.assert_array_equal(oa,ob)
    assert old.state_sha(env)==before and pickle.dumps(parent.rng.bit_generator.state)==rng
    result=dict(passed=True,original9_costs_exact=True,fine_min_not_higher_same_state=True,future_invariant=True,
        zero_means_current_reference_not_hold=True,state_and_parent_rng_unchanged=True,budget=budget.finish(),batch_calls=0)
    write_json(root/'precheck.json',result);print(result,flush=True)


def run(root):
    import numpy as np
    from .algorithm import MADDPG
    from ..environments.farm_inflow import InflowTrace
    from .midgrid_speed_report import metric
    cfg,p=context(root);assert read_json(root/'precheck.json')['passed']
    if (root/'complete.json').exists():raise ValueError('completed experiment retained; no rerun')
    env,budget,meter=setup(cfg,root);source=Path(cfg['source'])
    reference=read_csv(source/'trajectories.csv');groups={}
    for row in reference:groups.setdefault((row['case_id'],row['controller']),[]).append(row)
    oldmetrics={(row['case_id'],row['controller']):row for row in read_csv(source/'metrics.csv')}
    metrics=[];traces=[]
    for case in read_json(root/'bank/manifest.json')['cases']:
        folder=root/'cases'/case['case_id']
        if folder.exists():raise ValueError('case already exists; no hidden repeat')
        folder.mkdir(parents=True)
        for label in ('grid9','parent','n1_selected','n1_final','n8_selected','n8_final','p','pi'):
            role='search' if label=='grid9' else label
            rows=[dict(row,controller=label) for row in groups[(case['case_id'],role)]]
            details=read_json(source/'cases'/case['case_id']/'search.json') if label=='grid9' else dict(plans=[])
            spent=dict(actual=0,kinds={});m=metric(rows,case,cfg['base_config'],details['plans'],spent)
            m['historical_model_rows']=int(float(oldmetrics[(case['case_id'],role)]['new_model_rows']))
            metrics.append(m);traces.extend(rows)
        parent,_=MADDPG.load(cfg['parents'][case['run_id']]['checkpoint']);parent_rng=pickle.dumps(parent.rng.bit_generator.state)
        budget.start(case['case_id'],17*12*16+129);meter.kind='external_reset'
        wind=InflowTrace.load(root/'bank'/case['path']);env.initial=np.asarray(cfg['base_config']['environment']['initial_operating_point'],float).copy();env.initial[1]=case['initial_pitch_rad']
        obs,_=env.reset(seed=42,options=dict(wind_trajectory=wind.values,target_w=case['target_w']))
        plans=[];data=[];rows=[];offset=np.zeros(3)
        for t in range(128):
            if t%8==0:offset,details=plan(env,parent,p,meter);plans.append(details)
            action,reference_action=old.command(parent,obs,offset)
            data.append(dict(obs=obs.copy(),action=action.copy(),parent_action=reference_action,offset=offset.copy(),decision=t%8==0))
            meter.kind='external_transition';obs,_,done,_,info=env.step(action)
            np.testing.assert_array_equal(action,info['executed_action'])
            tags={key:case[key] for key in ('case_id','split','run_id','family','target_w','initial_pitch_rad')}
            rows.append(dict(**tags,controller='grid17',**{k:v for k,v in old.trace_row(info).items() if k not in tags}))
        assert done and pickle.dumps(parent.rng.bit_generator.state)==parent_rng
        spent=budget.finish();m=metric(rows,case,cfg['base_config'],plans,spent);m['historical_model_rows']=0
        write_json(folder/'plans.json',dict(plans=plans,budget=spent));write_csv(folder/'grid17.csv',rows)
        np.savez_compressed(folder/'current_world.npz',**{k:np.asarray([r[k] for r in data]) for k in data[0]})
        write_json(folder/'complete.json',{path.name:sha(path) for path in folder.iterdir() if path.is_file()})
        metrics.append(m);traces.extend(rows)
        print('Completed',case['case_id'],'charged',sum(r['actual'] for r in budget.data['scopes']),flush=True)
    write_csv(root/'metrics.csv',metrics);write_csv(root/'trajectories.csv',traces)
    context(root)
    execution=dict(status='executed',seed=42,formal_RL_steps=0,model_rows=sum(s['actual'] for s in budget.data['scopes']),metrics=len(metrics),trace_rows=len(traces))
    write_json(root/'execution_summary.json',execution);write_json(root/'summary.txt',execution)
    write_json(root/'complete.json',{name:sha(root/name) for name in ('config.yaml','metrics.csv','trajectories.csv','budget.json','execution_summary.json')})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('prepare','precheck','run','verify','figures'));parser.add_argument('--output',required=True)
    args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    import os,torch
    os.environ.setdefault('TF_NUM_INTRAOP_THREADS','1');os.environ.setdefault('TF_NUM_INTEROP_THREADS','1')
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    root=Path(args.output).resolve()
    if args.command in ('verify','figures'):
        from . import midgrid_speed_report
        getattr(midgrid_speed_report,args.command)(root)
    else:globals()[args.command](root)


if __name__=='__main__':main()
