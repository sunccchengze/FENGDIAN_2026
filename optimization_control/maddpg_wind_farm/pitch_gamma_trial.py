"""Approved, fixed-budget n8 gamma .99/1 experiment. Public algorithm stays unchanged."""
from __future__ import annotations
import argparse
from copy import deepcopy
from dataclasses import replace, asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .fixed_pinn_demo import activate_runtime, digest
from .pitch_cross_wind_diagnostic import ORIGINAL, read_csv, write_csv, write_json, error_parts
from .pitch_nstep_trial import read_json, verify, compressed_csv, attempt_dir, bank

HERE=Path(__file__).parent
OLD=HERE.parent/'experiments/20261028_pitch_nstep'
ARMS={'g099':.99,'g100':1.}
NETS=('actors','critics','target_actors','target_critics')
OPTIMIZERS=('actor_optimizers','critic_optimizers')
FAMILIES=('stationary','ramp','gust')


def entropy(purpose,run,*extra):
    import numpy as np
    return np.random.SeedSequence([42,20261029,purpose,run,*extra])


def adapt_gamma(agent,gamma):
    if gamma not in ARMS.values() or agent.n!=8:
        raise ValueError('only the approved two n8 arms')
    agent.config=replace(agent.config,gamma=gamma)
    agent.replay.gamma=gamma
    agent.replay.last_indices=agent.replay.last_lengths=agent.replay.discounts=None
    return agent


def inherit(path,arm):
    from .nstep_algorithm import NStepMADDPG
    a,m=NStepMADDPG.inherit(path,8)
    return adapt_gamma(a,ARMS[arm]),m


def load_agent(path,gamma):
    from .nstep_algorithm import NStepMADDPG
    a,m=NStepMADDPG.load(path,8)
    if a.config.gamma!=gamma or a.replay.gamma!=gamma or m['gamma']!=gamma or m['config']['algorithm']['gamma']!=gamma or m['experiment']!='pitch_gamma_v1':
        raise ValueError('gamma/config/replay/metadata restoration mismatch')
    return a,m


def fingerprint(value):
    import numpy as np
    import torch
    h=hashlib.sha256()
    def visit(x):
        if isinstance(x,torch.Tensor):
            visit(x.detach().cpu().numpy())
        elif isinstance(x,np.ndarray):
            h.update(str((x.dtype,x.shape)).encode());h.update(x.tobytes())
        elif isinstance(x,dict):
            for k in sorted(x,key=str):visit(k);visit(x[k])
        elif isinstance(x,(list,tuple)):
            for v in x:visit(v)
        else:h.update(repr(x).encode());h.update(b'\0')
    visit(value);return h.hexdigest()


def state(agent):
    import torch
    return dict(config=asdict(agent.config),n=agent.n,replay_gamma=agent.replay.gamma,
                networks={k:getattr(agent,k).state_dict() for k in NETS},
                optimizers={k:[o.state_dict() for o in getattr(agent,k)] for k in OPTIMIZERS},
                replay=agent.replay.state_dict(),rng=agent.rng.bit_generator.state,
                torch_rng=torch.get_rng_state(),updates=agent.updates)


def json_state(value):
    import numpy as np
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,dict):return {k:json_state(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [json_state(v) for v in value]
    if isinstance(value,np.generic):return value.item()
    return value


def context(root):
    import yaml
    root=Path(root).resolve();s=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify(s['protected_hashes']);return root,s


def arm_config(s,arm):
    cfg=deepcopy(s['base_config']);cfg['algorithm']['gamma']=ARMS[arm];return cfg


def reserve(root,kind,steps,label):
    ledger=root/f'{kind}_budget.jsonl'
    rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8').splitlines()] if ledger.exists() else []
    total=sum(r['reserved_steps'] for r in rows)+steps
    limit=98304 if kind=='learning' else 186368
    if total>limit:raise ValueError('conservative budget exhausted, including failed reservations')
    with ledger.open('a',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps(dict(label=label,reserved_steps=steps,cumulative_reserved=total))+'\n')


def make_bank(root,cfg,split):
    from .pitch_nstep_trial import wind
    if split=='test' and not (root/'pretest_audit.json').exists():raise ValueError('test still locked')
    out=root/f'{split}_bank';out.mkdir(exist_ok=False);cases=[]
    targets=(2.9e6,3.5e6) if split=='validation' else (2.7e6,3.3e6,3.9e6)
    pitches=(.025,.04,.055) if split=='validation' else (.03,.05)
    offset,repeats=(52000000,1) if split=='validation' else (53000000,2)
    for fi,family in enumerate(FAMILIES):
        for ti,target in enumerate(targets):
            for repeat in range(repeats):
                episode=offset+fi*100+ti*10+repeat
                trace=wind(cfg,family,split,episode);path=out/f'{family}_{ti}_{repeat}.csv';trace.save(path)
                for pitch in pitches:
                    cases.append(dict(id=f'{split}_{family}_t{target:g}_r{repeat}_p{pitch}',split=split,family=family,
                                      target_w=target,initial_pitch_rad=pitch,episode=episode,path=str(path.resolve())))
    if split=='test':
        for wi,speed in enumerate((7.6,7.8)):
            trace=wind(cfg,'stationary','test',53009000+wi)
            trace.values[:]=[speed,0.,.08];trace.components[:]=[speed,0.,0.]
            trace.metadata['override_family']='known_low_wind_pressure_regression'
            path=out/f'pressure_{speed}.csv';trace.save(path)
            for target in (4.35e6,4.55e6):
                for pitch in pitches:
                    cases.append(dict(id=f'pressure_w{speed}_t{target:g}_p{pitch}',split='stress',family='low_wind_stress',
                                      target_w=target,initial_pitch_rad=pitch,episode=53009000+wi,path=str(path.resolve())))
    write_json(out/'manifest.json',dict(seed=42,cases=cases,hashes={str(p.resolve()):digest(p) for p in out.iterdir() if p.is_file()}))


def prepare(root):
    import numpy as np
    import yaml
    from .nstep_algorithm import NStepMADDPG
    from .stable_workflow import Exploration
    from .pitch_nstep_trial import wind
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=False)
    old=yaml.safe_load((OLD/'config.yaml').read_text(encoding='utf-8'));cfg=old['base_config']
    verify({str(OLD/'config.yaml'):read_json(OLD/'selection.json')['config_sha256']})
    assert digest(Path(cfg['plant']['backend']['run_dir'])/'trained.keras')==cfg['plant']['backend']['model_sha256']
    assert digest(cfg['plant']['backend']['script'])==cfg['plant']['backend']['script_sha256']
    assert cfg['algorithm']['gamma']==.99 and cfg['environment']['horizon']==128 and cfg['environment']['control_mask']==[0,1,0]
    assert cfg['environment']['action_change_weight']==.001 and cfg['environment']['reward_scale']==100
    scans=[];collisions=[]
    for tree in (ORIGINAL,HERE.parents[1],Path('.')):
        paths=list((tree/'optimization_control/maddpg_wind_farm/configs').glob('*.yaml'))+list((tree/'optimization_control/experiments').glob('*/config.yaml'))
        for p in paths:
            text=p.read_text(encoding='utf-8-sig')
            occupied=[x for x in (51000000,52000000,53000000,53009000) if str(x) in text]
            scans.append(dict(path=str(p.resolve()),sha256=digest(p),occupied=occupied))
            if occupied:collisions.append(str(p))
    if collisions:raise ValueError(f'namespace already occupied: {collisions}')
    write_json(root/'namespace_audit.json',dict(scanned=scans,collisions=collisions))
    parents=deepcopy(old['parents']);protected={}
    for run,p in parents.items():
        verify({p['checkpoint']:p['sha256']})
        a,m=NStepMADDPG.inherit(p['checkpoint'],8)
        assert m['config']==cfg
        p.update(initial_replay=fingerprint(a.replay.state_dict()),initial_networks=fingerprint({k:getattr(a,k).state_dict() for k in NETS}),
                 initial_optimizers=fingerprint({k:[o.state_dict() for o in getattr(a,k)] for k in OPTIMIZERS}),
                 torch_rng_sha256=fingerprint(__import__('torch').get_rng_state()),initial_insertions=a.replay.insertions)
        protected[p['checkpoint']]=p['sha256']
    inputs=[OLD/'config.yaml',HERE/'pitch_gamma_trial.py',HERE/'PITCH_GAMMA_PROTOCOL.md',HERE/'PITCH_REWARD_ALIGNMENT_CANDIDATE.md',
            HERE.parent/'tests/test_pitch_gamma.py',HERE.parent/'environments/maddpg_farm_env.py']
    inputs+=list(HERE.glob('*.py'))+list((HERE.parent/'environments').glob('*.py'))
    inputs += [Path(cfg['plant']['backend']['run_dir'])/'trained.keras',Path(cfg['plant']['backend']['script']),
               ORIGINAL/'PROJECT_STATUS.md',ORIGINAL/'optimization_control/TASKFLOW.md']
    for p in inputs:protected[str(p.resolve())]=digest(p)
    settings=dict(seed=42,experiment='pitch_gamma_v1',source_commit='3b4acc9eb64e6ca17650e2bd0c53617912a3b5bf',arms=ARMS,
                  runs=[0,1,2],n=8,steps_per_job=16384,total_learning_steps=98304,eval_every=4096,save_every=128,
                  warmup_steps=512,update_every=2,noise_std=[0.,.03,0.],noise_end_fraction=.2,
                  namespace=dict(entropy=[42,20261029],scenario=5101,pitch=5102,exploration=5103,
                                 train=51000000,validation=52000000,test=53000000,pressure=53009000),
                  evaluation_limit=186368,evaluation_maxima=dict(validation=69120,validation_baselines=4608,test=112640),
                  gates=dict(ramp_improvement=.05,ramp_improved_runs=2,selected_noninitial=3,other_max_ratio=1.05,
                             final_over_selected=1.25,final_parent_control_max_ratio=1.05,motion_max_ratio=1.10,
                             motion_floor=1e-4,pitch_min=0.,pitch_max=.22,pitch_rate=.00872664626,physical_tolerance=1e-9),
                  selection='validation_complete_case_mean_rmse_strict_improvement_including_initial',
                  critic_initialization_limitation='gamma=.99 critic inherited unchanged into gamma1; no calibration/reset',
                  base_config=cfg,parents=parents,protected_hashes=protected)
    (root/'config.yaml').write_text(yaml.safe_dump(settings,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    make_bank(root,cfg,'validation');(root/'train_bank').mkdir();designs=[];random_states=[]
    for run in range(3):
        seed=int(entropy(5103,run).generate_state(1)[0]);noise=Exploration(seed,[0.,.03,0.],[10.,3.,5.],1.,'white',.2)
        states=dict(run=run,entropy=[42,20261029,5103,run],integer_seed=seed,initial=json_state(noise.state_dict()),episodes=[])
        all_noise=[]
        for ep in range(128):
            block,index=divmod(ep,9);order=np.random.default_rng(entropy(5101,run,block)).permutation(9)
            family,target=[(f,t) for f in FAMILIES for t in (2.6e6,3.2e6,3.8e6)][order[index]]
            pitch=float(np.random.default_rng(entropy(5102,run,ep)).uniform(.025,.055));episode=51000000+run*1000+ep
            trace=wind(cfg,family,'train',episode);path=root/'train_bank'/f'run{run}_ep{ep:03d}.csv';trace.save(path)
            before=json_state(noise.state_dict());noise.reset();values=np.stack([noise.sample((ep*128+t)/16384) for t in range(128)])
            all_noise.append(values);states['episodes'].append(dict(episode_index=ep,before_reset=before,after=json_state(noise.state_dict()),noise_sha256=fingerprint(values)))
            designs.append(dict(run=run,episode_index=ep,episode=episode,family=family,target_w=target,initial_pitch_rad=pitch,
                                path=str(path.resolve()),csv_sha256=digest(path),json_sha256=digest(path.with_suffix('.json')),values_sha256=fingerprint(trace.values)))
        np.savez_compressed(root/f'noise_run{run}.npz',noise=np.stack(all_noise));random_states.append(states)
    write_csv(root/'training_manifest.csv',designs);write_json(root/'random_states.json',random_states)
    write_json(root/'data_lock.json',dict(hashes={str(p.resolve()):digest(p) for p in list((root/'train_bank').iterdir())+
               [root/'training_manifest.csv',root/'random_states.json']+list(root.glob('noise_run*.npz')) if p.is_file()}))
    write_csv(root/'metrics.csv',[dict(status='prepared',formal_training_steps=0)]);write_json(root/'summary.txt',dict(status='prepared',formal_training_steps=0,test_locked=True))
    print(json.dumps(dict(prepared=str(root),parents=3,training_cases=384,learning_budget=98304)),flush=True)


def physical_check(before,after):
    import numpy as np
    actual=after['applied'][:,1];delta=actual-before['applied'][:,1]
    if actual.min() < -1e-9 or actual.max()>.22+1e-9 or np.max(np.abs(delta))>.00872664626+1e-9:
        raise ValueError(f'physical pitch constraint failed on actual dtype: {actual}, {delta}')


def row_step(env,obs,action,reward,before,info,case):
    import numpy as np
    physical_check(before,info)
    row=dict(case_id=case['id'],split=case['split'],family=case['family'],target_w=case['target_w'],initial_pitch_rad=case['initial_pitch_rad'],
             decision_step=info['step']-1,response_step=info['step'],decision_remaining=float(obs[0,14]),
             decision_wind_m_s=float(before['wind'][0]),response_wind_m_s=float(info['wind'][0]),wind_direction_rad=float(info['wind'][1]),
             decision_error_w=before['error_w'],error_w=info['error_w'],farm_power_w=info['farm_power_w'],
             reward=float(reward[0]),tracking_reward=100*info['reward_terms']['tracking'],action_reward=100*info['reward_terms']['action_change'],action_change=info['action_change'])
    assert abs(float(obs[0,14])-(1-(info['step']-1)/128))<1e-7
    expected=100*(-(info['error_w']/15e6)**2-.001*info['action_change'])
    if abs(float(reward[0])-expected)>5e-6:raise ValueError('native raw reward changed')
    for i in range(3):
        command=(float(info['executed_action'][i,1])+1)*.11
        requested=(1-np.exp(-.5))*(command-before['applied'][i,1])
        row.update({f'pitch_before_{i}':float(before['applied'][i,1]),f'pitch_actual_{i}':float(info['applied'][i,1]),
                    f'pitch_command_{i}':command,f'pitch_delta_{i}':float(info['applied'][i,1]-before['applied'][i,1]),
                    f'pitch_rate_limited_{i}':int(abs(requested)>.00872664626),
                    f'pitch_boundary_{i}':int(command<=1e-6 or command>=.22-1e-6),f'power_{i}_w':float(info['power_w'][i]),
                    f'heading_{i}':float(info['heading_rad'][i]),f'yaw_misalignment_{i}':float(info['applied'][i,0]),
                    f'speed_actual_{i}':float(info['applied'][i,2]),
                    f'speed_command_{i}':float(env.low[2]+(float(info['executed_action'][i,2])+1)*(env.high[2]-env.low[2])/2)})
    return row


def episode_metrics(rows):
    import numpy as np
    if len(rows)!=128 or [int(r['response_step']) for r in rows]!=list(range(1,129)):raise ValueError('full episode required')
    r=rows[0];delta=np.array([[float(r[f'pitch_delta_{i}']) for i in range(3)] for r in rows])
    actual=np.array([[float(r[f'pitch_actual_{i}']) for i in range(3)] for r in rows])
    command=np.array([[float(r[f'pitch_command_{i}']) for i in range(3)] for r in rows])
    return dict(**{k:r[k] for k in ('case_id','split','family','target_w','initial_pitch_rad')},**error_parts([float(r['error_w']) for r in rows]),
                pitch_travel_rad=float(np.abs(delta).sum()),pitch_rms_rate_rad_s=float(np.sqrt(np.mean(delta**2))),
                pitch_rate_fraction=float(np.mean([[int(r[f'pitch_rate_limited_{i}']) for i in range(3)] for r in rows])),
                pitch_boundary_fraction=float(np.mean([[int(r[f'pitch_boundary_{i}']) for i in range(3)] for r in rows])),
                pitch_command_actual_rms_rad=float(np.sqrt(np.mean((command-actual)**2))),
                pitch_min_rad=float(actual.min()),pitch_max_rad=float(actual.max()),pitch_max_rate_rad_s=float(np.abs(delta).max()))


def capture(root,env,cases,label,agent=None,mode=None):
    import numpy as np
    from .controllers import PitchController
    from .pitch_action_diagnostic import reset_case
    metrics=[];traces=[]
    reserve(root,'evaluation',len(cases)*128,label)
    for case,wind in cases:
        obs,info=reset_case(env,case,wind);controller=PitchController(env,env._baseline_config,mode) if mode else None;rows=[]
        assert float(obs[0,14])==1.
        for t in range(128):
            action=agent.act(obs) if agent else controller.act(obs)
            nxt,reward,done,truncated,after=env.step(action)
            assert not truncated and done==(t==127) and float(nxt[0,14])==(1-(t+1)/128)
            rows.append(row_step(env,obs,action,reward,info,after,case));obs,info=nxt,after
        metrics.append(episode_metrics(rows));traces.extend(rows)
    return metrics,traces


def worker(root,arm,run,stop_after=None):
    import numpy as np
    from .workflow import build_env
    from .stable_workflow import Exploration
    from ..environments.farm_inflow import InflowTrace
    root,s=context(root)
    if (root/'selection.json').exists() or not (root/'engineering.json').exists():raise ValueError('training locked or engineering gate missing')
    verify(read_json(root/'engineering.json')['hashes']);verify(read_json(root/'data_lock.json')['hashes'])
    job=root/f'{arm}_run{run}';job.mkdir(exist_ok=True)
    if (job/'result.json').exists():verify(read_json(job/'result.json')['hashes']);return
    for started in job.glob('step_*/attempt_*/started.json'):
        if not started.with_name('commit.json').exists():raise ValueError(f'uncommitted reserved learning fragment; no silent recomputation: {started}')
    cfg=arm_config(s,arm);env=build_env(cfg);env._baseline_config=cfg['baselines']
    noise=Exploration(int(entropy(5103,run).generate_state(1)[0]),s['noise_std'],[10.,3.,5.],1.,'white',.2)
    commits=sorted(job.glob('step_*/attempt_*/commit.json'));resumed=None
    if commits:
        commit=read_json(commits[-1]);verify(commit['hashes']);agent,meta=load_agent(commit['checkpoint'],ARMS[arm])
        if meta['root_config_sha256']!=digest(root/'config.yaml') or meta['run']!=run:raise ValueError('restore identity mismatch')
        step,episode,history,best,initial=(meta[k] for k in ('step','episode','history','best','initial'))
        noise.load_state_dict(meta['noise']);resumed=str(commits[-1])
    else:
        agent,_=inherit(s['parents'][str(run)]['checkpoint'],arm);step=episode=0;history=[];best=initial=None
    validation=bank(root,'validation');manifest=[r for r in read_csv(root/'training_manifest.csv') if int(r['run'])==run]
    expected_noise=np.load(root/f'noise_run{run}.npz')['noise'];random_states=read_json(root/'random_states.json')[run]
    def save(out,transitions=None,losses=None,trace=None):
        nonlocal initial,best
        checkpoint=(out/'state.pth').resolve()
        if step%4096==0:
            rows,ts=capture(root,env,validation,f'{arm}:{run}:validation:{step}',agent=agent)
            score=float(np.mean([r['rmse_w'] for r in rows]))
            if initial is None:initial=str(checkpoint)
            if best is None or score<best['score_w']:best=dict(step=step,checkpoint=str(checkpoint),score_w=score)
            history.append(dict(step=step,rmse_w=score,best_rmse_w=best['score_w'],selected_step=best['step']))
            write_csv(out/'validation_metrics.csv',rows);compressed_csv(out/'validation_traces.csv.gz',ts)
            print(json.dumps(dict(arm=arm,run=run,step=step,validation_rmse_w=score,best_step=best['step'])),flush=True)
        if transitions:
            np.savez_compressed(out/'training.npz',**{k:np.stack([t[k] for t in transitions]) for k in transitions[0]})
            write_csv(out/'losses.csv',losses or [dict(no_updates=1)]);compressed_csv(out/'training_traces.csv.gz',trace)
        meta=dict(experiment='pitch_gamma_v1',gamma=ARMS[arm],n=8,config=cfg,run=run,step=step,episode=episode,
                  history=history,best=best,initial=initial,noise=noise.state_dict(),parent=s['parents'][str(run)],
                  root_config_sha256=digest(root/'config.yaml'),resume_from=resumed,updates=agent.updates)
        agent.save(checkpoint,meta)
        write_json(out/'commit.json',dict(step=step,checkpoint=str(checkpoint),gamma=ARMS[arm],
                   hashes={str(p.resolve()):digest(p) for p in out.iterdir() if p.is_file()}))
        if step%1024==0:print(json.dumps(dict(saved_arm=arm,run=run,steps=step,episode=episode,updates=agent.updates)),flush=True)
        return str(checkpoint)
    if not commits:final=save(attempt_dir(job/'step_00000000'))
    else:final=commit['checkpoint']
    while step<16384 and (stop_after is None or step<stop_after):
        design=manifest[episode];wind=InflowTrace.load(design['path'])
        case=dict(id=f'train_run{run}_ep{episode:03d}',split='train',family=design['family'],target_w=float(design['target_w']),initial_pitch_rad=float(design['initial_pitch_rad']))
        from .pitch_action_diagnostic import reset_case
        obs,info=reset_case(env,case,wind);noise.reset();transitions=[];losses=[];trace=[]
        out=attempt_dir(job/f'step_{step+128:08d}');reserve(root,'learning',128,f'{arm}:{run}:episode:{episode}')
        write_json(out/'started.json',dict(from_step=step,intended_step=step+128,episode=episode,resume_from=resumed,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
        actual=0
        try:
            for t in range(128):
                exploration=noise.sample(step/16384)
                if not np.array_equal(exploration,expected_noise[episode,t]):raise ValueError('frozen exploration/RNG mismatch')
                action=env.project_action(np.clip(agent.act(obs)+exploration,-1,1)).astype(np.float32)
                nxt,reward,done,truncated,after=env.step(action);actual+=1
                assert not truncated and done==(t==127) and float(nxt[0,14])==1-(t+1)/128
                trace.append(row_step(env,obs,action,reward,info,after,case))
                agent.replay.add(obs,after['executed_action'],reward,nxt,done)
                transitions.append(dict(obs=obs.copy(),next_obs=nxt.copy(),actions=after['executed_action'].copy(),rewards=reward.copy(),terminated=np.array([done]),
                                        exploration=exploration.copy(),error_w=np.array(after['error_w']),applied=after['applied'].copy(),wind=after['wind'].copy()))
                step+=1
                if step>=512 and step%2==0:
                    loss=agent.update();losses.append(dict(step=step,**loss,sample_indices_sha256=fingerprint(agent.replay.last_indices),
                           m_mean=float(agent.replay.last_lengths.mean()),m_min=int(agent.replay.last_lengths.min()),m_max=int(agent.replay.last_lengths.max())))
                obs,info=nxt,after
            if json_state(noise.state_dict())!=random_states['episodes'][episode]['after']:raise ValueError('episode RNG endpoint mismatch')
            episode+=1;final=save(out,transitions,losses,trace)
        except Exception as exc:
            write_json(out/'failed.json',dict(actual_environment_steps=actual,step=step,error=repr(exc),reserved=128));raise
    if step==128:
        write_json(job/'minimal_check.json',dict(learning_steps=128,added_updates=agent.updates-s['parents'][str(run)]['updates'],horizon=128,remaining_and_done=True,raw_reward_and_physical_limits=True,checkpoint=final))
    if step==16384:
        write_json(job/'result.json',dict(arm=arm,gamma=ARMS[arm],run=run,steps=step,initial=initial,selected=best['checkpoint'],selected_step=best['step'],final=final,
                   history=history,final_over_selected=history[-1]['rmse_w']/best['score_w'],updates=agent.updates,
                   added_updates=agent.updates-s['parents'][str(run)]['updates'],m_histogram=agent.replay.m_histogram.tolist(),
                   hashes={p:digest(p) for p in set((initial,best['checkpoint'],final))}))


def launch(root):
    root=Path(root).resolve();schedule=[(a,0,128) for a in ARMS]+[(a,0,4096) for a in ARMS]+[(a,0,None) for a in ARMS]+[(a,r,None) for r in (1,2) for a in ARMS]
    (root/'processes').mkdir(exist_ok=True)
    for i,(arm,run,stop) in enumerate(schedule):
        marker=root/'processes'/f'process_{i:02d}.json'
        if marker.exists():
            if read_json(marker).get('returncode')!=0:raise ValueError('failed/running worker retained; no automatic retry')
            continue
        if i==2:
            for a in ARMS:
                m=read_json(root/f'{a}_run0/minimal_check.json');assert m['learning_steps']==128 and m['added_updates']==0
        cmd=[sys.executable,'-B','-X','utf8','-m',__package__+'.pitch_gamma_trial','worker','--output',str(root),'--arm',arm,'--run',str(run)]
        if stop:cmd+=['--stop-after',str(stop)]
        env=os.environ.copy();env.update(TF_NUM_INTRAOP_THREADS='1',TF_NUM_INTEROP_THREADS='1',PYTHONHASHSEED='42')
        start=time.time()
        with (root/'processes'/f'process_{i:02d}.log').open('wb') as log:
            p=subprocess.Popen(cmd,cwd=HERE.parents[1],stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=0x08000000 if os.name=='nt' else 0)
            write_json(marker,dict(command=cmd,pid=p.pid,start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),returncode=None))
            code=p.wait()
        record=read_json(marker);record.update(returncode=code,elapsed_s=time.time()-start);write_json(marker,record)
        print(json.dumps(dict(process=i,arm=arm,run=run,stop=stop,returncode=code,elapsed_s=record['elapsed_s'])),flush=True)
        if code:raise RuntimeError(f'worker failed; see {marker.with_suffix(".log")}')


def select(root):
    root,s=context(root)
    if (root/'selection.json').exists():raise FileExistsError('selection immutable')
    results=[read_json(root/f'{a}_run{r}/result.json') for a in ARMS for r in range(3)]
    for r in results:
        verify(r['hashes']);assert r['steps']==16384 and r['added_updates']==7937
        candidates=[(h['rmse_w'],h['step']) for h in r['history']];assert min(candidates)[1]==r['selected_step']
    ledger=[json.loads(x) for x in (root/'learning_budget.jsonl').read_text(encoding='utf-8').splitlines()]
    assert sum(r['reserved_steps'] for r in ledger)==98304
    write_json(root/'selection.json',dict(seed=42,results=results,config_sha256=digest(root/'config.yaml'),new_training_steps=98304,test_used_for_selection=False))
    print('six jobs and checkpoint choices frozen; run pretest audit before test',flush=True)


def evaluate(root,split):
    from .workflow import build_env
    from .pitch_nstep_mechanism import actor_hash
    root,s=context(root);selection=read_json(root/'selection.json')
    assert selection['config_sha256']==digest(root/'config.yaml')
    if split=='test' and not (root/'pretest_audit.json').exists():raise ValueError('core pretest audit missing')
    if split=='test' and not (root/'test_bank').exists():make_bank(root,s['base_config'],'test')
    cases=bank(root,split);env=build_env(s['base_config']);env._baseline_config=s['base_config']['baselines']
    policy_labels=[(f'{r["arm"]}_run{r["run"]}_{role}',r[role],r['gamma'],None) for r in selection['results'] for role in ('initial','selected','final')]
    labels=(policy_labels if split=='test' else [])+[(b,None,None,b) for b in ('p','pi')]
    cache={}
    for label,path,gamma,mode in labels:
        base=root/'evaluations'/split/label;done=sorted(base.glob('attempt_*/complete.json'))
        if done:
            c=read_json(done[-1]);verify(c['hashes']);cache[c['actor_identity']]=str(done[-1].parent);continue
        agent=load_agent(path,gamma)[0] if path else None;identity=actor_hash(agent) if agent else mode
        out=attempt_dir(base)
        if identity in cache:
            old=Path(cache[identity]);rows=read_csv(old/'metrics.csv');reuse=str(old)
        else:
            rows,trace=capture(root,env,cases,f'{split}:{label}',agent=agent,mode=mode)
            compressed_csv(out/'traces.csv.gz',trace);reuse=None
        write_csv(out/'metrics.csv',rows)
        write_json(out/'complete.json',dict(label=label,actor_identity=identity,checkpoint=path,checkpoint_sha256=digest(path) if path else None,
                   reused_from=reuse,actual_environment_steps=0 if reuse else len(cases)*128,
                   hashes={str(p.resolve()):digest(p) for p in out.iterdir() if p.is_file()}))
        cache[identity]=str(out);print(json.dumps(dict(evaluated=label,split=split,reused_from=reuse,cases=len(cases))),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('prepare','engineering','engineering-child','worker','launch','select','validation','test'))
    p.add_argument('--output',required=True);p.add_argument('--arm',choices=tuple(ARMS),default='g099');p.add_argument('--run',type=int,choices=(0,1,2),default=0);p.add_argument('--stop-after',type=int)
    args=p.parse_args()
    if args.command=='launch':launch(args.output);return
    activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    if args.command=='prepare':prepare(args.output)
    elif args.command in ('engineering','engineering-child'):
        from .pitch_gamma_engineering import engineering,child
        (engineering if args.command=='engineering' else child)(args.output)
    elif args.command=='worker':worker(args.output,args.arm,args.run,args.stop_after)
    elif args.command=='select':select(args.output)
    else:evaluate(args.output,args.command)


if __name__=='__main__':main()
