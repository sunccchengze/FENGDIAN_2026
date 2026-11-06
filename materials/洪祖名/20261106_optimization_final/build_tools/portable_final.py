"""Verify or replay the frozen NREL three-channel handoff from any directory.

Source records stay byte-identical. Only dependency file access is relocated;
policy identities, normalization, observations and commands are unchanged.
"""
import argparse,csv,hashlib,json,sys
from pathlib import Path
from copy import deepcopy
from contextlib import ExitStack
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
EXP=ROOT/'optimization_control/experiments/20261106_nrel_speed_regression'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('mode',choices=['verify','inference','replay'])
    ap.add_argument('--runtime',type=Path,help='Optional existing directory containing TensorFlow/NumPy packages')
    ap.add_argument('--case',type=int,choices=range(18),default=0)
    ap.add_argument('--controllers',nargs='+',default=['Y0_selected','Y1_selected','Y2_selected','p','pi'],choices=['Y0_selected','Y1_selected','Y2_selected','p','pi'])
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    aliases=read(ROOT/'provenance/path_map.json')
    def locate(value):
        key=str(value).replace('\\','/').lower()
        if key in aliases:p=ROOT/aliases[key]
        else:
            p=Path(value)
            if not p.is_absolute():p=ROOT/p
        p=p.resolve()
        if not p.is_relative_to(ROOT) or not p.is_file():raise FileNotFoundError('Dependency must exist inside the extracted bundle: '+str(value))
        return p
    def verify(ref):
        p=locate(ref['path'])
        if digest(p)!=ref['sha256']:raise ValueError('Dependency SHA mismatch: '+str(p))
        return p
    if args.mode=='verify':
        source=read(ROOT/'provenance/source_files.json')
        for r in source['files']:
            p=ROOT/r['path']
            assert p.stat().st_size==r['bytes'] and digest(p)==r['sha256'],r['path']
        rows=list(csv.DictReader((EXP/'metrics.csv').open(encoding='utf-8-sig')))
        assert len(rows)==180 and len({(r['rule'],r['controller'],r['case_id']) for r in rows})==180
        families={}
        for f in ['stationary','ramp','gust']:
            y=[float(r['rmse_w'])/1000 for r in rows if r['rule']=='nrel' and r['family']==f and r['controller'].startswith('Y')]
            pi=[float(r['rmse_w'])/1000 for r in rows if r['rule']=='nrel' and r['family']==f and r['controller']=='pi']
            assert len(y)==18 and len(pi)==6 and sum(y)/len(y)<sum(pi)/len(pi)
            families[f]={'MADDPG_kW':sum(y)/len(y),'PI_kW':sum(pi)/len(pi)}
        print(json.dumps({'verified_source_files':len(source['files']),'families':families,'training_steps':0},ensure_ascii=False));return
    sys.path.insert(0,str(ROOT))
    if args.runtime:
        from optimization_control.maddpg_wind_farm.fixed_pinn_demo import activate_runtime
        activate_runtime(args.runtime)
    import numpy as np
    import torch
    from optimization_control.maddpg_wind_farm import nrel_speed_regression as r
    from optimization_control.maddpg_wind_farm import forecast_speed_macro as macro
    from optimization_control.maddpg_wind_farm.algorithm import MADDPG
    from optimization_control.maddpg_wind_farm.history_wind_forecast import RidgeForecast
    from optimization_control.maddpg_wind_farm.nrel_speed_adapter import FrozenTransfer
    from types import SimpleNamespace
    torch.set_num_threads(1)
    lock=read(EXP/'lock.json')
    load_agent=MADDPG.load;load_forecast=RidgeForecast.load
    with ExitStack() as stack:
        stack.enter_context(patch.object(r.old,'verify',verify))
        stack.enter_context(patch.object(macro,'sha',lambda p:digest(locate(p))))
        stack.enter_context(patch.object(MADDPG,'load',side_effect=lambda p,*a,**kw:load_agent(locate(p),*a,**kw)))
        stack.enter_context(patch.object(RidgeForecast,'load',side_effect=lambda p:load_forecast(locate(p))))
        completed=read(EXP/'complete.json');results=[]
        transfer=deepcopy(lock['transfer'])
        backend=transfer['base_config']['plant']['backend']
        original_model=str(backend['run_dir']).replace('\\','/')
        backend['run_dir']=str(locate(original_model+'/trained.keras').parent)
        backend['script']=str(locate(backend['script']))
        world=r.transfer.World(transfer) if args.mode=='replay' else None
        for ctrl in args.controllers:
            entry=next(x for x in completed['results'] if x['controller']==ctrl)
            receipt=read(verify(entry['cases'][args.case]))
            with np.load(verify(receipt['eval']['trace']),allow_pickle=False) as data:
                trace=data['trace'];obs=data['obs'];inputs=data['inputs']
            if args.mode=='inference':
                if not ctrl.startswith('Y'):continue
                role=next(x for x in transfer['roles'] if x['id']==ctrl)
                raw=r.transfer.frozen.policy(transfer['source'],role)
                before=r.transfer.frozen.policy_digest(raw);counts=r.transfer.frozen.counters(raw)
                t=32;agent=FrozenTransfer(raw,SimpleNamespace(rule='nrel',effective_wind=trace[t,10:13].copy()))
                features=agent.features([x.astype(np.float32) for x in trace[:t+1,4:7]])
                action,_,_=agent.compose(obs[t],agent.speed_z(obs[t],features),agent.z(obs[t],features),(-.25,.25))
                np.testing.assert_array_equal(action,trace[t+1,28:37].reshape(3,3).astype(np.float32))
                assert before==r.transfer.frozen.policy_digest(raw) and counts==r.transfer.frozen.counters(raw)
                results.append({'controller':ctrl,'saved_action_exact':True,'model_queries':0})
            else:
                class Budget:
                    rows=0
                    def take(self,n,kind):
                        self.rows+=n
                        if self.rows>129:raise RuntimeError('129-row replay budget exceeded')
                budget=Budget()
                actual=r.transfer.rollout(world,budget,transfer,ctrl,'nrel',receipt['case'],trace[:,4:7].astype(np.float32))
                for name,expected in [('trace',trace),('obs',obs),('inputs',inputs)]:
                    np.testing.assert_array_equal(actual[name],expected)
                results.append({'controller':ctrl,'full_trace_exact':True,'model_queries':budget.rows,'rmse_kW':float(np.sqrt(np.mean(trace[1:,3]**2))/1000)})
        report={'mode':args.mode,'case':args.case,'results':results,'training_steps':0,'optimizer_updates':0,'original_worktrees_used':False}
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
        print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
