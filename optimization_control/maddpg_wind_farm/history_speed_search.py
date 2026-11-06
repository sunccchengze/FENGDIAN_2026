"""Conditional closed loop: only replace persistence with frozen causal history forecast."""
from pathlib import Path
import argparse
import pickle
import time
import hashlib
from . import causal_speed_search as old
from .midgrid_speed_search import grid,choose
from .history_forecast_experiment import context
from .anchor_closeout import read_json,write_json,read_csv,write_csv,sha,verify_hashes


class Persistence:
    def predict(self,history):
        import numpy as np
        return np.tile(np.asarray(history,np.float32)[-1],(12,1)),dict(reference_only=True)


def plan(env,parent,meter,model,history):
    import numpy as np
    history=np.asarray(history,np.float32)
    if history.shape!=(env.t+1,3):raise ValueError('exactly the already observed prefix required')
    np.testing.assert_array_equal(history[-1],env.wind)
    before=old.state_sha(env);current=old.capture(env);h=min(12,env.horizon-env.t);started=time.perf_counter()
    future,forecast_details=model.predict(history);assert future.shape==(12,3)
    costs=[];errors=[];kind=meter.kind;meter.kind='internal_forecast'
    for offset in grid():
        child=old.fork(current,env.plant,type(env));child.trajectory[env.t+1:env.t+h+1]=future[:h]
        obs=child._observe();sequence=[]
        for _ in range(h):
            action,_=old.command(parent,obs,offset);obs,_,_,_,info=child.step(action);sequence.append(info['error_w'])
        errors.append(sequence);costs.append(float(np.mean(np.square([v/1e6 for v in sequence]))))
    meter.kind=kind;selected=choose(costs)
    assert old.state_sha(env)==before
    return grid()[selected],dict(step=env.t,chosen=selected,costs_MW2=costs,predicted_error_w=errors,
        predicted_wind=future[:h].tolist(),forecast_details=forecast_details,observed_history_rows=len(history),
        observed_history_sha256=hashlib.sha256(history.tobytes()).hexdigest(),current_state_sha256=before,
        predicted_steps=h,model_rows=17*h,wall_seconds=time.perf_counter()-started)


def loop_context(root):
    cfg=context(root);verify_hashes({str(root/k):v for k,v in read_json(root/'forecast_lock.json').items()})
    assert read_json(root/'screen.json')['passed']
    verify_hashes(read_json(root/'loop_code_lock.json'))
    return cfg


def precheck(root):
    import numpy as np
    from .algorithm import MADDPG
    from .workflow import build_env
    from .history_wind_forecast import RidgeForecast
    from .midgrid_speed_search import plan as original_plan
    cfg=context(root);assert read_json(root/'screen.json')['passed']
    verify_hashes({str(root/k):v for k,v in read_json(root/'forecast_lock.json').items()})
    if (root/'loop_code_lock.json').exists():raise ValueError('precheck already attempted; retain reservation')
    repo=Path(cfg['worktree'])
    code={str(p):sha(p) for p in (Path(__file__),repo/'optimization_control/tests/test_history_speed_search.py')}
    write_json(root/'loop_code_lock.json',code)
    env=build_env(cfg['base_config']);budget=old.Budget(root/'budget.json',limit=170000)
    tests=read_json(root/'tests.json');assert tests['passed']
    budget.start('mock_planner',2000);budget.take(tests['mock_model_rows'],'mock_correctness');budget.finish()
    budget.start('real_precheck',2000-tests['mock_model_rows']);meter=old.Meter(env.plant.predictor,budget);env.plant.predictor=meter
    model=RidgeForecast.load(root/'forecast_model.npz');parent,_=MADDPG.load(cfg['parents'][0]['checkpoint'])
    meter.kind='precheck_external';env.reset(seed=42,options=dict(wind_trajectory=np.tile([9.,0.,.08],(129,1)),target_w=3.2e6));history=[env.wind.copy()]
    for _ in range(4):env.step(parent.act(env._observe()));history.append(env.wind.copy())
    before=old.state_sha(env);rng=pickle.dumps(parent.rng.bit_generator.state)
    _,a=plan(env,parent,meter,model,history);env.trajectory[env.t+1:]=[9.2,.02,.1]
    _,b=plan(env,parent,meter,model,history);np.testing.assert_array_equal(a['costs_MW2'],b['costs_MW2'])
    _,c=plan(env,parent,meter,Persistence(),history);_,d=original_plan(env,parent,cfg['protocol'],meter)
    np.testing.assert_array_equal(c['costs_MW2'],d['costs_MW2'])
    left=old.fork(old.capture(env),env.plant,type(env));right=old.fork(old.capture(env),env.plant,type(env));meter.kind='zero_semantics'
    for _ in range(12):
        x,*_=left.step(old.command(parent,left._observe(),np.zeros(3))[0]);y,*_=right.step(parent.act(right._observe()));np.testing.assert_array_equal(x,y)
    assert before==old.state_sha(env) and rng==pickle.dumps(parent.rng.bit_generator.state)
    write_json(root/'precheck.json',dict(passed=True,future_invariant=True,persistence_adapter_exact=True,state_parent_rng_unchanged=True,
        zero_semantics_exact=True,batch_calls=0,budget=budget.finish()))
    print('Precheck passed, total charged',sum(x['actual'] for x in budget.data['scopes']),flush=True)


def run(root):
    import numpy as np
    from .workflow import build_env
    from .algorithm import MADDPG
    from .history_wind_forecast import RidgeForecast
    from .midgrid_speed_report import metric
    from ..environments.farm_inflow import InflowTrace
    cfg=loop_context(root);assert read_json(root/'precheck.json')['passed']
    if (root/'loop_complete.json').exists():raise ValueError('completed loop retained')
    source=Path(cfg['source']);env=build_env(cfg['base_config']);budget=old.Budget(root/'budget.json',limit=170000)
    meter=old.Meter(env.plant.predictor,budget);env.plant.predictor=meter;model=RidgeForecast.load(root/'forecast_model.npz')
    groups={}
    for row in read_csv(source/'trajectories.csv'):groups.setdefault((row['case_id'],row['controller']),[]).append(row)
    oldmetrics={(r['case_id'],r['controller']):r for r in read_csv(source/'metrics.csv')}
    metrics=[];traces=[]
    for case in read_json(source/'bank/manifest.json')['cases']:
        cid=case['case_id'];folder=root/'cases'/cid
        if folder.exists():raise ValueError('case already attempted; no implicit replay')
        folder.mkdir(parents=True)
        for label in ('grid17','grid9','parent','n1_selected','n1_final','n8_selected','n8_final','p','pi'):
            rows=groups[(cid,label)];m=dict(oldmetrics[(cid,label)]);m['historical_model_rows']=m['new_model_rows'];m['new_model_rows']=0;m['internal_model_rows']=0
            metrics.append(m);traces.extend(rows)
        parent,_=MADDPG.load(cfg['parents'][case['run_id']]['checkpoint']);rng=pickle.dumps(parent.rng.bit_generator.state)
        budget.start(cid,3393);meter.kind='external_reset'
        wind=InflowTrace.load(source/'bank'/case['path']);env.initial=np.asarray(cfg['base_config']['environment']['initial_operating_point'],float).copy();env.initial[1]=case['initial_pitch_rad']
        obs,_=env.reset(seed=42,options=dict(wind_trajectory=wind.values,target_w=case['target_w']));history=[env.wind.copy()]
        plans=[];rows=[];data=[]
        for t in range(128):
            if t%8==0:offset,details=plan(env,parent,meter,model,history);plans.append(details)
            action,reference=old.command(parent,obs,offset);data.append(dict(obs=obs.copy(),action=action.copy(),parent_action=reference,offset=offset.copy(),decision=t%8==0))
            meter.kind='external_transition';obs,_,done,_,info=env.step(action);history.append(env.wind.copy())
            np.testing.assert_array_equal(action,info['executed_action'])
            tags={k:case[k] for k in ('case_id','split','run_id','family','target_w','initial_pitch_rad')}
            rows.append(dict(**tags,controller='history17',**{k:v for k,v in old.trace_row(info).items() if k not in tags}))
        assert done and rng==pickle.dumps(parent.rng.bit_generator.state)
        spent=budget.finish();m=metric(rows,case,cfg['base_config'],plans,spent);m['historical_model_rows']=0
        write_json(folder/'plans.json',dict(plans=plans,budget=spent));write_csv(folder/'history17.csv',rows)
        np.savez_compressed(folder/'current_world.npz',**{k:np.asarray([r[k] for r in data]) for k in data[0]})
        write_json(folder/'complete.json',{p.name:sha(p) for p in folder.iterdir() if p.is_file()})
        metrics.append(m);traces.extend(rows)
        print('Completed',cid,'charged',sum(s['actual'] for s in budget.data['scopes']),flush=True)
    write_csv(root/'loop_metrics.csv',metrics);write_csv(root/'loop_trajectories.csv',traces);loop_context(root)
    write_json(root/'loop_complete.json',{name:sha(root/name) for name in ('loop_metrics.csv','loop_trajectories.csv','budget.json')})
    write_json(root/'summary.txt',dict(status='loop_executed',formal_RL_steps=0,screen=read_json(root/'screen.json'),
        PINN_mock_rows=sum(s['actual'] for s in budget.data['scopes']),metrics=len(metrics),trace_rows=len(traces)))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('precheck','run'));parser.add_argument('--output',required=True);args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    import os,torch
    os.environ.setdefault('TF_NUM_INTRAOP_THREADS','1');os.environ.setdefault('TF_NUM_INTEROP_THREADS','1')
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    globals()[args.command](Path(args.output).resolve())


if __name__=='__main__':main()
