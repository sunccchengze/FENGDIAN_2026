"""Bounded paired actor-context trial with sparse full checkpoints and row accounting."""
from __future__ import annotations
import argparse
from copy import deepcopy
import csv
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .fixed_pinn_demo import activate_runtime,digest
from .pitch_gamma_trial import fingerprint,json_state,row_step,episode_metrics,entropy
from .pitch_nstep_trial import read_json,verify,bank,attempt_dir,wind
from .pitch_cross_wind_diagnostic import ORIGINAL,read_csv

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'experiments/20261028_pitch_nstep'
MANIFEST=HERE.parent/'experiments/20261028_pitch_nstep_mechanism/candidate_manifest.json'
ARMS=('replay','current_pitch')
FAMILIES=('stationary','ramp','gust')
LIMIT=3*1024**3


def size(root):return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())


def space(root,extra):
    used=size(root)
    if used+extra>LIMIT:raise RuntimeError(f'3GiB storage cap: used={used}, proposed={extra}; no deletion')
    return used


def put(root,path,payload):
    path=Path(path)
    if path.exists():raise FileExistsError(path)
    space(root,len(payload));path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)


def js(root,path,value):put(root,path,(json.dumps(json_state(value),ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def table(root,path,rows,compressed=False):
    rows=list(rows);fields=list(dict.fromkeys(k for r in rows for k in r));buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fields,lineterminator='\n');writer.writeheader();writer.writerows({k:r.get(k,'') for k in fields} for r in rows)
    value=buffer.getvalue().encode('utf-8');put(root,path,gzip.compress(value,mtime=0) if compressed else value)


class LimitedFile:
    def __init__(self,root,path):
        if Path(path).exists():raise FileExistsError(path)
        self.base=space(root,22*1024**2);self.handle=open(path,'wb');self.maximum=0
    def write(self,data):
        end=self.handle.tell()+len(data)
        if self.base+max(end,self.maximum)>LIMIT or end>22*1024**2:raise RuntimeError('checkpoint exceeds reserved storage; partial file retained')
        result=self.handle.write(data);self.maximum=max(self.maximum,end);return result
    def __getattr__(self,name):return getattr(self.handle,name)
    def close(self):self.handle.close()


def save_agent(root,path,agent,meta):
    f=LimitedFile(root,path)
    try:agent.save(f,meta)
    finally:f.close()


def context(root):
    import yaml
    root=Path(root).resolve();s=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify(s['protected_hashes']);return root,s


def append(root,name,row):
    payload=(json.dumps(json_state(row),ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
    space(root,len(payload))
    with (root/name).open('ab') as f:f.write(payload)


def reserve(root,kind,steps,label):
    path=root/f'{kind}_budget.jsonl';rows=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
    if kind=='evaluation' and sum(x['steps'] for x in rows)+steps>278528:raise RuntimeError('evaluation transition cap')
    append(root,path.name,dict(label=label,steps=steps,physical_reservation=True))


class Meter:
    def __init__(self,root):
        self.root=root;self.path=root/'query_ticks.bin';ticks=self.path.read_bytes() if self.path.exists() else b''
        if set(ticks)-set(b'TE'):raise ValueError('invalid query ticks')
        self.counts={'T':ticks.count(b'T'),'E':ticks.count(b'E')};self.active=None
        space(root,1024**2);self.f=self.path.open('ab',buffering=0)
    def begin(self,kind,label):
        if self.active is not None:raise RuntimeError('nested query scope')
        self.active=kind;self.label=label;self.start=sum(self.counts.values())
        append(self.root,'query_scopes.jsonl',dict(event='begin',label=label,kind=kind,offset=self.start))
    def end(self):
        append(self.root,'query_scopes.jsonl',dict(event='end',label=self.label,kind=self.active,offset=sum(self.counts.values()),rows=sum(self.counts.values())-self.start))
        self.active=None
    def wrap(self,predictor):
        def counted(x):
            if self.active not in ('T','E') or len(x)!=1:raise AssertionError('all single-row plant inputs require an explicit scope')
            if sum(self.counts.values())>=381088 or self.counts[self.active]>=({'T':99088,'E':282000}[self.active]):raise RuntimeError('actual Plant row cap, including reset/recomputation')
            self.f.write(self.active.encode());self.counts[self.active]+=1
            return predictor(x)
        return counted


def environment(s,meter):
    from .workflow import build_env
    env=build_env(s['base_config']);env._baseline_config=s['base_config']['baselines']
    env.plant.predictor=meter.wrap(env.plant.predictor)
    return env


def make_bank(root,cfg,split):
    if split=='test' and not (root/'pretest_audit.json').exists():raise RuntimeError('test locked')
    folder=root/f'{split}_bank';folder.mkdir(exist_ok=False);cases=[]
    targets=(2.9e6,3.5e6) if split=='validation' else (2725000.,3325000.,3925000.)
    pitches=(.025,.04,.055) if split=='validation' else (.03,.05)
    for fi,family in enumerate(FAMILIES):
        for ti,target in enumerate(targets):
            for repeat in range(1 if split=='validation' else 2):
                episode=(62000000 if split=='validation' else 63000000)+fi*100+ti*10+repeat
                trace=wind(cfg,family,split,episode);path=folder/f'{family}_{ti}_{repeat}.csv';trace.save(path)
                for pitch in pitches:cases.append(dict(id=f'{split}_{family}_t{target:g}_r{repeat}_p{pitch}',split=split,family=family,target_w=target,initial_pitch_rad=pitch,episode=episode,path=str(path)))
    if split=='test':
        for wi,speed in enumerate((7.6,7.8)):
            trace=wind(cfg,'stationary','test',63009000+wi);trace.values[:]=[speed,0.,.08];trace.components[:]=[speed,0.,0.]
            trace.metadata['override_family']='known_pressure_regression';path=folder/f'pressure_{speed}.csv';trace.save(path)
            for target in (4.35e6,4.55e6):
                for pitch in pitches:cases.append(dict(id=f'pressure_w{speed}_t{target:g}_p{pitch}',split='stress',family='low_wind_stress',target_w=target,initial_pitch_rad=pitch,episode=63009000+wi,path=str(path)))
    js(root,folder/'manifest.json',dict(seed=42,cases=cases,hashes={str(p):digest(p) for p in folder.iterdir() if p.is_file()}))


def prepare(root):
    import numpy as np
    import yaml
    from .pitch_actor_context_algorithm import PitchActorContextMADDPG
    from .stable_workflow import Exploration
    from .pitch_gamma_trial import state
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=False)
    source=read_json(MANIFEST);old=yaml.safe_load((OLD/'config.yaml').read_text(encoding='utf-8'))
    assert digest(OLD/'selection.json')==source['source_selection_sha256'] and digest(OLD/'config.yaml')==source['trial_config_sha256']
    cfg=old['base_config'];parents={};protected={str(MANIFEST):digest(MANIFEST),str(OLD/'config.yaml'):digest(OLD/'config.yaml'),str(OLD/'selection.json'):digest(OLD/'selection.json')}
    for p in source['candidates']:
        assert digest(p['checkpoint'])==p['sha256'] and p['selected_by_test'] is False
        a,_=PitchActorContextMADDPG.inherit(p['checkpoint'],'replay');v=state(a)
        parents[str(p['run'])]=dict(**{k:p[k] for k in ('checkpoint','sha256','selected_step')},updates=a.updates,replay_size=a.replay.size,replay_position=a.replay.position,
            insertions=a.replay.insertions,m_histogram=a.replay.m_histogram.tolist(),initial_state_fingerprint=fingerprint(v),algorithm_rng=json_state(a.rng.bit_generator.state),replay_rng=json_state(a.replay.rng.bit_generator.state))
        protected[p['checkpoint']]=p['sha256']
    scan=[]
    for tree in (ORIGINAL,HERE.parents[1],Path('.')):
        for p in list((tree/'optimization_control/maddpg_wind_farm/configs').glob('*.yaml'))+list((tree/'optimization_control/experiments').glob('*/config.yaml')):
            occupied=[n for n in (61000000,62000000,63000000,63009000) if str(n) in p.read_text(encoding='utf-8-sig')]
            scan.append(dict(path=str(p),occupied=occupied,sha256=digest(p)))
    assert not any(x['occupied'] for x in scan),'namespace collision'
    js(root,root/'namespace_audit.json',dict(files=scan,collisions=[]))
    inputs=list(HERE.glob('*.py'))+list((HERE.parent/'environments').glob('*.py'))
    inputs += [HERE/'PITCH_ACTOR_CONTEXT_PROTOCOL.md',HERE/'PITCH_REMAINING_FAILURE_CANDIDATE.md',HERE.parent/'tests/test_pitch_actor_context.py',
               Path(cfg['plant']['backend']['script'])]
    model=Path(cfg['plant']['backend']['run_dir']);inputs += [model/n for n in ('trained.keras','config_used.json','training_report.json')]
    for p in inputs:protected[str(p.resolve())]=digest(p)
    settings=dict(seed=42,experiment='pitch_actor_context_v1',source_commit='99a48037ff0a39322fbb3df1117088b2b810e63e',arms=list(ARMS),parents=parents,base_config=cfg,
                  steps_per_job=16384,logical_learning_steps=98304,evaluation_transition_limit=278528,model_row_limit=381088,
                  storage_limit_bytes=LIMIT,full_every=1024,light_every=128,extra_full_run0_step=128,expected_full_formal=104,
                  checkpoint_reservation_bytes=22*1024**2,estimated_all_bytes=105*22*1024**2+400*1024**2,
                  namespace=dict(train=61000000,validation=62000000,test=63000000,pressure=63009000,purposes=[6101,6102,6103]),
                  selection='18_complete_128_step_case_rmse_mean_strict_improvement_including_initial',protected_hashes=protected)
    assert settings['estimated_all_bytes']<LIMIT
    put(root,root/'config.yaml',yaml.safe_dump(settings,allow_unicode=True,sort_keys=False).encode())
    make_bank(root,cfg,'validation');(root/'train_bank').mkdir();designs=[];rng=[]
    for run in range(3):
        seed=int(entropy(6103,run).generate_state(1)[0]);noise=Exploration(seed,[0.,.03,0.],[10.,3.,5.],1.,'white',.2)
        states=dict(run=run,entropy=[42,20261029,6103,run],integer_seed=seed,initial=json_state(noise.state_dict()),episodes=[]);all_noise=[]
        for ep in range(128):
            block,index=divmod(ep,9);order=np.random.default_rng(entropy(6101,run,block)).permutation(9)
            family,target=[(f,t) for f in FAMILIES for t in (2.6e6,3.2e6,3.8e6)][order[index]]
            pitch=float(np.random.default_rng(entropy(6102,run,ep)).uniform(.025,.055));episode=61000000+run*1000+ep
            trace=wind(cfg,family,'train',episode);path=root/'train_bank'/f'run{run}_ep{ep:03d}.csv';trace.save(path)
            before=json_state(noise.state_dict());noise.reset();values=np.stack([noise.sample((ep*128+t)/16384) for t in range(128)]);all_noise.append(values)
            states['episodes'].append(dict(before_reset=before,after=json_state(noise.state_dict()),noise_sha256=fingerprint(values)))
            designs.append(dict(run=run,episode_index=ep,episode=episode,family=family,target_w=target,initial_pitch_rad=pitch,path=str(path),values_sha256=fingerprint(trace.values)))
        data=io.BytesIO();np.savez_compressed(data,noise=np.stack(all_noise));put(root,root/f'noise_run{run}.npz',data.getvalue());rng.append(states)
    table(root,root/'training_manifest.csv',designs);js(root,root/'random_states.json',rng)
    js(root,root/'data_lock.json',dict(hashes={str(p):digest(p) for p in list((root/'train_bank').iterdir())+[root/'training_manifest.csv',root/'random_states.json']+list(root.glob('noise_run*.npz')) if p.is_file()}))
    js(root,root/'prepared.json',dict(storage_estimate_bytes=settings['estimated_all_bytes'],storage_cap_bytes=LIMIT,full_formal_states=104,formal_steps=0,source_parent_check=True))
    print(json.dumps(dict(prepared=str(root),storage_estimate_bytes=settings['estimated_all_bytes'],full_formal_states=104)),flush=True)


def capture(root,env,meter,cases,label,agent=None,mode=None):
    from .pitch_action_diagnostic import reset_case
    from .controllers import PitchController
    reserve(root,'evaluation',128*len(cases),label);metrics=[];traces=[]
    for case,trace in cases:
        meter.begin('E',label+':'+case['id'])
        try:
            obs,info=reset_case(env,case,trace);controller=PitchController(env,env._baseline_config,mode) if mode else None;rows=[]
            for t in range(128):
                action=agent.act(obs) if agent else controller.act(obs);nxt,reward,done,truncated,after=env.step(action)
                assert not truncated and done==(t==127)
                rows.append(row_step(env,obs,action,reward,info,after,case));obs,info=nxt,after
            metrics.append(episode_metrics(rows));traces.extend(rows)
        finally:meter.end()
    return metrics,traces


def worker(root,arm,run,stop_after=None):
    import numpy as np
    from .pitch_actor_context_algorithm import PitchActorContextMADDPG,full_checkpoint,recovery_plan
    from .stable_workflow import Exploration
    from .pitch_action_diagnostic import reset_case
    from ..environments.farm_inflow import InflowTrace
    root,s=context(root)
    if (root/'selection.json').exists() or not (root/'engineering.json').exists():raise RuntimeError('training locked')
    verify(read_json(root/'engineering.json')['hashes']);verify(read_json(root/'data_lock.json')['hashes'])
    job=root/f'{arm}_run{run}';job.mkdir(exist_ok=True)
    if (job/'result.json').exists():verify(read_json(job/'result.json')['hashes']);return
    paths=sorted(job.glob('step_*/attempt_*/commit.json'));commits=[read_json(p) for p in paths]
    commit,repeats=recovery_plan(commits)
    meter=Meter(root);env=environment(s,meter);noise=Exploration(int(entropy(6103,run).generate_state(1)[0]),[0.,.03,0.],[10.,3.,5.],1.,'white',.2)
    resumed=None
    if commit:
        verify(commit['hashes']);agent,meta=PitchActorContextMADDPG.load(commit['checkpoint'],arm)
        assert meta['run']==run and meta['root_config_sha256']==digest(root/'config.yaml')
        step,episode,history,best,initial=[meta[k] for k in ('step','episode','history','best','initial')]
        noise.load_state_dict(meta['noise']);resumed=commit['checkpoint']
        append(root,'recoveries.jsonl',dict(arm=arm,run=run,from_step=step,replayed_committed_light_steps=[c['step'] for c in repeats],
               prior_query_ticks=sum(meter.counts.values()),pid=os.getpid()))
    else:
        agent,_=PitchActorContextMADDPG.inherit(s['parents'][str(run)]['checkpoint'],arm);step=episode=0;history=[];best=initial=None
    validation=bank(root,'validation');designs=[r for r in read_csv(root/'training_manifest.csv') if int(r['run'])==run]
    expected_noise=np.load(root/f'noise_run{run}.npz')['noise'];states=read_json(root/'random_states.json')[run]
    def finish(out,transitions=None,losses=None,trace=None):
        nonlocal best,initial
        full=full_checkpoint(step,run);checkpoint=str((out/'state.pth').resolve()) if full else None
        if step%4096==0:
            ms,ts=capture(root,env,meter,validation,f'{arm}:{run}:validation:{step}',agent=agent)
            score=float(np.mean([x['rmse_w'] for x in ms]))
            if initial is None:initial=checkpoint
            if best is None or score<best['score_w']:best=dict(step=step,checkpoint=checkpoint,score_w=score)
            history.append(dict(step=step,rmse_w=score,best_rmse_w=best['score_w'],selected_step=best['step']))
            table(root,out/'validation_metrics.csv',ms);table(root,out/'validation_traces.csv.gz',ts,True)
            print(json.dumps(dict(arm=arm,run=run,step=step,validation_rmse_w=score,selected_step=best['step'])),flush=True)
        if transitions:
            data=io.BytesIO();np.savez_compressed(data,**{k:np.stack([v[k] for v in transitions]) for k in transitions[0]});put(root,out/'training.npz',data.getvalue())
            table(root,out/'losses.csv',losses or [dict(no_updates=1)]);table(root,out/'training_traces.csv.gz',trace,True)
        if full:
            meta=dict(experiment='pitch_actor_context_v1',arm=arm,n=8,config=s['base_config'],run=run,step=step,episode=episode,
                      history=history,best=best,initial=initial,noise=noise.state_dict(),parent=s['parents'][str(run)],
                      root_config_sha256=digest(root/'config.yaml'),resume_from=resumed,updates=agent.updates,checkpoint_interval=1024)
            save_agent(root,checkpoint,agent,meta)
        js(root,out/'commit.json',dict(step=step,arm=arm,run=run,attempt=int(out.name.split('_')[-1]),checkpoint=checkpoint,
            resume_from=resumed,updates=agent.updates,replay_insertions=agent.replay.insertions,
            hashes={str(p):digest(p) for p in out.iterdir() if p.is_file()}))
        space(root,0)
        if full:print(json.dumps(dict(full_saved=checkpoint,step=step,storage_bytes=size(root))),flush=True)
        return checkpoint
    final=commit['checkpoint'] if commit else finish(attempt_dir(job/'step_00000000'))
    while step<16384 and (stop_after is None or step<stop_after):
        space(root,1024**2)
        design=designs[episode];weather=InflowTrace.load(design['path']);case=dict(id=f'train_run{run}_ep{episode:03d}',split='train',family=design['family'],target_w=float(design['target_w']),initial_pitch_rad=float(design['initial_pitch_rad']))
        out=attempt_dir(job/f'step_{step+128:08d}');reserve(root,'learning',128,f'{arm}:{run}:episode:{episode}:attempt:{out.name}')
        js(root,out/'started.json',dict(from_step=step,intended_step=step+128,episode=episode,resume_from=resumed,pid=os.getpid()))
        meter.begin('T',f'{arm}:{run}:{episode}:{out.name}');transitions=[];losses=[];trace=[];actual=0
        try:
            obs,info=reset_case(env,case,weather);noise.reset()
            for t in range(128):
                exploration=noise.sample(step/16384);assert np.array_equal(exploration,expected_noise[episode,t])
                action=env.project_action(np.clip(agent.act(obs)+exploration,-1,1)).astype(np.float32)
                nxt,reward,done,truncated,after=env.step(action);actual+=1
                assert not truncated and done==(t==127) and float(nxt[0,14])==1-(t+1)/128
                trace.append(row_step(env,obs,action,reward,info,after,case));agent.replay.add(obs,after['executed_action'],reward,nxt,done)
                transitions.append(dict(obs=obs.copy(),next_obs=nxt.copy(),actions=after['executed_action'].copy(),rewards=reward.copy(),terminated=np.array([done]),exploration=exploration.copy(),error_w=np.array(after['error_w']),applied=after['applied'].copy(),wind=after['wind'].copy()))
                step+=1
                if step>=512 and step%2==0:
                    loss=agent.update();losses.append(dict(step=step,**loss,sample_indices_sha256=fingerprint(agent.replay.last_indices),m_mean=float(agent.replay.last_lengths.mean()),m_min=int(agent.replay.last_lengths.min()),m_max=int(agent.replay.last_lengths.max())))
                obs,info=nxt,after
            assert json_state(noise.state_dict())==states['episodes'][episode]['after']
        except Exception as exc:
            js(root,out/'failed.json',dict(actual_transition_steps=actual,error=repr(exc),step=step));raise
        finally:meter.end()
        episode+=1;checkpoint=finish(out,transitions,losses,trace)
        if checkpoint:final=checkpoint
    if step==128 and not (job/'minimal_check.json').exists():js(root,job/'minimal_check.json',dict(steps=128,added_updates=agent.updates-s['parents'][str(run)]['updates'],checkpoint=final))
    if step==16384:
        js(root,job/'result.json',dict(arm=arm,run=run,steps=step,initial=initial,selected=best['checkpoint'],selected_step=best['step'],final=final,history=history,
            updates=agent.updates,added_updates=agent.updates-s['parents'][str(run)]['updates'],m_histogram=agent.replay.m_histogram.tolist(),hashes={p:digest(p) for p in set((initial,best['checkpoint'],final))}))


def launch(root):
    root=Path(root).resolve();folder=root/'processes';folder.mkdir(exist_ok=True)
    schedule=[(a,0,128) for a in ARMS]+[(a,0,4096) for a in ARMS]+[(a,0,None) for a in ARMS]+[(a,r,None) for r in (1,2) for a in ARMS]
    for i,(arm,run,stop) in enumerate(schedule):
        marker=folder/f'process_{i:02d}.json'
        if marker.exists():
            assert read_json(marker)['returncode']==0;continue
        if i==2:
            for a in ARMS:assert read_json(root/f'{a}_run0/minimal_check.json')['added_updates']==0
        command=[sys.executable,'-B','-X','utf8','-m',__package__+'.pitch_actor_context_trial','worker','--output',str(root),'--arm',arm,'--run',str(run)]
        if stop:command+=['--stop-after',str(stop)]
        env=os.environ.copy();env.update(TF_NUM_INTRAOP_THREADS='1',TF_NUM_INTEROP_THREADS='1',PYTHONHASHSEED='42');start=time.time()
        with (folder/f'process_{i:02d}.log').open('xb') as log:
            p=subprocess.Popen(command,cwd=HERE.parents[1],stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=0x08000000 if os.name=='nt' else 0)
            js(root,folder/f'process_{i:02d}.started.json',dict(command=command,pid=p.pid,start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
            code=p.wait()
        js(root,marker,dict(command=command,pid=p.pid,returncode=code,elapsed_s=time.time()-start))
        print(json.dumps(dict(process=i,arm=arm,run=run,stop=stop,returncode=code,storage_bytes=size(root))),flush=True)
        if code:raise RuntimeError(f'worker failed; evidence retained at {marker}')


def select(root):
    root,s=context(root);results=[read_json(root/f'{a}_run{r}/result.json') for a in ARMS for r in range(3)]
    for r in results:
        verify(r['hashes']);assert r['steps']==16384 and r['added_updates']==7937
        assert min(r['history'],key=lambda h:(h['rmse_w'],h['step']))['step']==r['selected_step']
    js(root,root/'selection.json',dict(seed=42,results=results,config_sha256=digest(root/'config.yaml'),logical_learning_steps=98304,test_used_for_selection=False))


def known_cases():
    import yaml
    from .pitch_cross_wind_diagnostic import make_cases,SOURCE
    cases,_=make_cases(yaml.safe_load((SOURCE/'config.yaml').read_text(encoding='utf-8')))
    cases=[(c,w) for c,w in cases if c['family']!='low_wind_stress'];assert len(cases)==36
    return cases


def evaluate(root,split):
    from .pitch_actor_context_algorithm import PitchActorContextMADDPG
    from .pitch_nstep_mechanism import actor_hash
    root,s=context(root);selection=read_json(root/'selection.json');assert selection['config_sha256']==digest(root/'config.yaml')
    if split=='test':
        assert (root/'pretest_audit.json').exists()
        if not (root/'test_bank').exists():make_bank(root,s['base_config'],'test')
    cases=known_cases() if split=='known' else bank(root,split)
    meter=Meter(root);env=environment(s,meter)
    labels=[(f'{r["arm"]}_run{r["run"]}_{role}',r[role],r['arm'],None) for r in selection['results'] for role in ('initial','selected','final')] if split!='validation' else []
    labels += [(b,None,None,b) for b in ('p','pi')];cache={}
    for label,path,arm,mode in labels:
        base=root/'evaluations'/split/label
        done=sorted(base.glob('attempt_*/complete.json'))
        if done:
            d=read_json(done[-1]);verify(d['hashes']);cache[d['actor_identity']]=str(done[-1].parent);continue
        agent=PitchActorContextMADDPG.load(path,arm)[0] if path else None;identity=actor_hash(agent) if agent else mode
        out=attempt_dir(base)
        if identity in cache:
            previous=Path(cache[identity]);metrics=read_csv(previous/'metrics.csv');reused=str(previous)
        else:
            metrics,traces=capture(root,env,meter,cases,f'{split}:{label}',agent,mode)
            table(root,out/'traces.csv.gz',traces,True);reused=None
        table(root,out/'metrics.csv',metrics)
        js(root,out/'complete.json',dict(label=label,checkpoint=path,checkpoint_sha256=digest(path) if path else None,actor_identity=identity,
              reused_from=reused,actual_environment_steps=0 if reused else len(cases)*128,hashes={str(p):digest(p) for p in out.iterdir() if p.is_file()}))
        cache[identity]=str(out);print(json.dumps(dict(evaluated=label,split=split,reused=bool(reused))),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','engineering','engineering-child','worker','launch','select','validation','known','test'])
    p.add_argument('--output',required=True);p.add_argument('--arm',choices=ARMS,default='replay');p.add_argument('--run',type=int,choices=range(3),default=0);p.add_argument('--stop-after',type=int)
    a=p.parse_args()
    if a.mode=='launch':launch(a.output);return
    activate_runtime(ORIGINAL/'.venv/pinn_tf216');import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    if a.mode=='prepare':prepare(a.output)
    elif a.mode in ('engineering','engineering-child'):
        from .pitch_actor_context_engineering import engineering,child
        (engineering if a.mode=='engineering' else child)(a.output)
    elif a.mode=='worker':worker(a.output,a.arm,a.run,a.stop_after)
    elif a.mode=='select':select(a.output)
    else:evaluate(a.output,a.mode)


if __name__=='__main__':main()
