"""One authorized, locked-budget frozen-parent speed n1/n8 comparison."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import argparse
import hashlib
from pathlib import Path
import subprocess

from .anchor_closeout import (sha, read_json, write_json, write_csv, read_csv, verify_hashes,
    checked_output, make_env, rollout, save_job, load_job, recompute)

DEFAULT=Path(__file__).with_name('configs')/'speed_nstep.yaml'
ARMS={'n1':1,'n8':8}
ENGINEERING_COMMIT='c3e9cc07b004ae5fc3f2033d00a25f756c0edb03'


def now():return datetime.now(timezone.utc).isoformat()


def protocol(path=DEFAULT):
    import yaml
    p=yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if (p['version'],p['seed'],p['steps_per_run'],p['eval_every'],p['warmup_steps'],p['update_every']) != ('frozen_speed_nstep_control_v1',42,8192,2048,512,2):
        raise ValueError('fixed authorized budget/seed required')
    if p['arms']!=ARMS or p['design_entropy']!=[42,20261028,8405001]:raise ValueError('fixed arms/namespaces required')
    return p


def design(p,run,episode):
    import numpy as np
    from .random_wind_training import FAMILIES
    pairs=[(family,target) for family in FAMILIES for target in p['training_targets_w']]
    block,index=divmod(episode,len(pairs))
    rng=np.random.default_rng(np.random.SeedSequence(p['design_entropy']+[1,run,block]))
    family,target=pairs[int(rng.permutation(len(pairs))[index])]
    rng=np.random.default_rng(np.random.SeedSequence(p['design_entropy']+[2,run,episode]))
    return family,float(target),float(rng.uniform(*p['training_initial_pitch_rad']))


def episode(p,run,number):
    from ..environments.farm_inflow import generate_inflow
    family,target,pitch=design(p,run,number)
    inflow=deepcopy(p['inflow']);inflow['speed']['scenario']=family
    trace=generate_inflow(inflow,dt_s=p['dt_s'],horizon=p['horizon'],seed=42,split='train',
        episode=p['training_episode_offset']+run*1000+number)
    return trace,target,pitch,family


def freeze_bank(folder,p,split):
    from ..environments.farm_inflow import generate_inflow
    from .random_wind_training import FAMILIES
    folder.mkdir(parents=True,exist_ok=False);cases=[]
    targets=p[split+'_targets_w'];pitches=[.04] if split=='validation' else p['test_initial_pitch_rad']
    for f,family in enumerate(FAMILIES):
        for j,target in enumerate(targets):
            inflow=deepcopy(p['inflow']);inflow['speed']['scenario']=family
            trace=generate_inflow(inflow,dt_s=p['dt_s'],horizon=p['horizon'],seed=42,split=split,
                episode=p[split+'_episode_offset']+f*100+j)
            path=folder/f'{split}_{family}_{j}.csv';trace.save(path)
            for pitch in pitches:cases.append(dict(id=f'{split}_{family}_{j}_pitch{pitch}',split=split,family=family,
                path=path.name,csv_sha256=sha(path),json_sha256=sha(path.with_suffix('.json')),target_w=float(target),initial_pitch_rad=pitch))
    if split=='test':
        inflow=deepcopy(p['inflow']);inflow['speed']['scenario']='stationary'
        trace=generate_inflow(inflow,dt_s=p['dt_s'],horizon=p['horizon'],seed=42,split='test',episode=p['stress_episode'])
        trace.values[:]=[7.6,0.,.08];trace.components[:]=[7.6,0.,0.]
        trace.metadata.update(override_family='low_wind_stress',source='known_regression_not_new_independent_sample')
        path=folder/'test_low_wind_stress.csv';trace.save(path)
        for pitch in pitches:cases.append(dict(id=f'test_low_wind_stress_pitch{pitch}',split='test',family='low_wind_stress',
            path=path.name,csv_sha256=sha(path),json_sha256=sha(path.with_suffix('.json')),target_w=4.4e6,initial_pitch_rad=pitch))
    write_json(folder/'manifest.json',dict(version='farm_benchmark_v1',seed=42,cases=cases))


def bank(root,split):
    from .benchmark import load_cases
    return load_cases(root/('bank' if split=='validation' else 'test/bank'),split,allow_test=split=='test')


def namespace_inventory(p,worktree):
    """Read protocol/config declarations in both worktrees, excluding this new protocol."""
    import re
    patterns=[str(p[k]) for k in ('training_episode_offset','validation_episode_offset','test_episode_offset','stress_episode')]+['8405001']
    matches=[];checked=[]
    for repo in (worktree,Path('.')):
        for folder in ('maddpg_wind_farm','tests'):
            for path in sorted((repo/'optimization_control'/folder).rglob('*')):
                if not path.is_file() or path.suffix not in ('.py','.md','.yaml'):continue
                if path.name.startswith('SPEED_NSTEP') or path.name in ('speed_nstep.yaml','speed_nstep_training.py','test_speed_nstep_training.py','speed_nstep_audit.py'):continue
                checked.append(dict(path=str(path),sha256=sha(path)))
                text=path.read_text(encoding='utf-8-sig')
                for line_no,line in enumerate(text.splitlines(),1):
                    if any(re.search(r'(?<!\d)'+value+r'(?!\d)',line) for value in patterns):
                        matches.append(dict(path=str(path),line=line_no,text=line))
    if matches:raise ValueError('namespace collision requiring inspection: '+str(matches))
    return dict(patterns=patterns,checked=checked,collisions=matches)


def prepare(root,p):
    import yaml
    import torch
    worktree=Path(__file__).resolve().parents[2];origin=Path(p['origin'])
    root=checked_output(root,worktree,origin)
    oldroot=worktree/'optimization_control/experiments/20261028_frozen_speed_checked'
    old=yaml.safe_load((oldroot/'config.yaml').read_text(encoding='utf-8'))
    eng=read_json(worktree/'optimization_control/experiments/20261028_speed_nstep_engineering/git_delivery.json')
    if eng['commit']!=ENGINEERING_COMMIT or eng['status']!='verified':raise ValueError('engineering identity differs')
    p=dict(old['protocol'],**p)
    # Data design values originate from the old frozen protocol, not its test outcomes.
    base=deepcopy(old['base_config']);base['environment']['control_mask']=[0,1,1]
    base['algorithm']['actor_lr']=1e-4
    assert base['environment']['reward_scale']==100 and base['environment']['action_change_weight']==.001
    parents=deepcopy(old['parents']);protected={}
    for parent in parents:
        assert sha(parent['checkpoint'])==parent['sha256']
        state=torch.load(parent['checkpoint'],map_location='cpu',weights_only=False)
        meta=state['metadata'];count=meta['lineage']['cumulative_parent_steps']+meta['steps']
        assert count==parent['cumulative_parent_steps'] and meta['config']['environment']['horizon']==128
        assert state['config']['gamma']==.99 and state['config']['critic_lr']==.001 and state['config']['tau']==.01
        assert state['config']['batch_size']==64 and state['config']['capacity']==32768 and state['config']['grad_clip']==1
        protected[parent['checkpoint']]=parent['sha256']
    for name,digest in old['source_hashes'].items():
        if Path(name).name not in ('PROJECT_STATUS.md','README.md','TASKFLOW.md'):protected[name]=digest
    verify_hashes(protected)
    namespaces=namespace_inventory(p,worktree)
    code={str(path):sha(path) for folder in ('maddpg_wind_farm','environments','utils')
          for path in (worktree/'optimization_control'/folder).glob('*.py')}
    for path in (DEFAULT,Path(__file__).with_name('SPEED_NSTEP_PROTOCOL.md'),worktree/'optimization_control/tests/test_speed_nstep_training.py'):
        code[str(path)]=sha(path)
    root.mkdir(parents=True,exist_ok=False)
    write_json(root/'namespace_audit.json',namespaces)
    freeze_bank(root/'bank',p,'validation')
    preflight=[]
    for run in range(3):
        for number in range(64):
            trace,target,pitch,family=episode(p,run,number)
            preflight.append(dict(run_id=run,episode=number,family=family,target_w=target,initial_pitch_rad=pitch,
                values_sha256=hashlib.sha256(trace.values.tobytes()).hexdigest()))
    write_csv(root/'training_wind_preflight.csv',preflight)
    saved=dict(seed=42,protocol=p,base_config=base,parents=parents,worktree=str(worktree),original_workspace=str(origin),
        engineering_commit=ENGINEERING_COMMIT,engineering_evidence_sha256=sha(worktree/'optimization_control/experiments/20261028_speed_nstep_engineering/git_delivery.json'),
        source_hashes=protected,executed_code_hashes=code,bank_sha256=sha(root/'bank/manifest.json'),
        preflight_sha256=sha(root/'training_wind_preflight.csv'),namespace_audit_sha256=sha(root/'namespace_audit.json'),
        formal_budget=49152,extra_learning_smoke=0,coordination={str(origin/n):sha(origin/n) for n in ('PROJECT_STATUS.md','README.md','optimization_control/TASKFLOW.md')})
    (root/'config.yaml').write_text(yaml.safe_dump(saved,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    write_csv(root/'metrics.csv',[dict(status='prepared',formal_training_steps=0)])
    write_json(root/'summary.txt',dict(status='prepared',seed=42,formal_training_steps=0,test_released=False))
    print('Prepared',root,flush=True)


def context(root):
    import yaml
    saved=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    checked_output(root,saved['worktree'],saved['original_workspace'])
    verify_hashes(saved['source_hashes']);verify_hashes(saved['executed_code_hashes'])
    assert sha(root/'bank/manifest.json')==saved['bank_sha256']
    assert sha(root/'training_wind_preflight.csv')==saved['preflight_sha256']
    return saved,saved['protocol']


def initial(saved,arm,run):
    from .algorithm import MADDPG
    from .speed_nstep_algorithm import FrozenSpeedNStepMADDPG
    from .benchmark import seed_for
    parent=saved['parents'][run];agent,meta=MADDPG.load(parent['checkpoint'])
    agent.config=replace(agent.config,actor_lr=1e-4)
    return FrozenSpeedNStepMADDPG.from_parent(agent,seed_for(42,8405,run),n=ARMS[arm],
        insertion_count=parent['cumulative_parent_steps'],horizon=meta['config']['environment']['horizon'],epoch=parent['sha256'],
        evidence=dict(expected_insertions=parent['cumulative_parent_steps'],source_sha256=parent['sha256'],
                      derivation='metadata.lineage.cumulative_parent_steps + metadata.steps'))


def gate(root):
    import numpy as np
    import torch
    from .algorithm import MADDPG
    from .frozen_speed_algorithm import FrozenSpeedMADDPG
    from .benchmark import seed_for
    from .anchor_closeout_diagnostic import trajectory_differences
    saved,p=context(root);rows=[];cases=bank(root,'validation')
    if (root/'handover.json').exists():raise ValueError('gate already recorded')
    metrics=[];traces=[]
    for run in range(3):
        parent,_=MADDPG.load(saved['parents'][run]['checkpoint'])
        v4=FrozenSpeedMADDPG.from_parent(parent,seed_for(42,8405,run))
        agents=[('parent',parent),('v4',v4)]+[(arm,initial(saved,arm,run)) for arm in ARMS]
        largest=0.
        for field in ('obs','next_obs'):
            data=parent.replay.data[field][:parent.replay.size]
            for target in (False,True):
                for i in range(3):
                    for start in range(0,len(data),4096):
                        x=torch.tensor(data[start:start+4096,i]);actor=(parent.target_actors if target else parent.actors)[i]
                        with torch.no_grad():
                            expected=parent.policy(actor,x)
                            for _,child in agents[1:]:largest=max(largest,float((expected-child.total_action(i,x,target=target)).abs().max()))
        reference=None
        for label,agent in agents:
            m,t,_=rollout(saved['base_config'],cases,agent=agent)
            tags=dict(run_id=run,controller=label);metrics.extend(dict(**tags,**r) for r in m);traces.extend(dict(**tags,**r) for r in t)
            if reference is None:reference=(m,t)
            else:
                diff=trajectory_differences(reference[1],t)
                rmse=max(abs(a['rmse_w']-b['rmse_w']) for a,b in zip(reference[0],m))
                passed=largest<=2e-6 and diff['max_action_difference']<=2e-6 and diff['max_applied_difference']<=1e-6 and max(rmse,diff['max_power_difference_w'])<=1
                rows.append(dict(run_id=run,controller=label,max_online_target_action_difference=largest,max_rmse_difference_w=rmse,**diff,passed=bool(passed)))
        print('Gate stream',run,'max action',largest,flush=True)
    write_csv(root/'handover.csv',rows)
    save_job(root/'gate',metrics,traces)
    write_json(root/'handover.json',dict(root_config_sha256=sha(root/'config.yaml'),passed=all(r['passed'] for r in rows),
        checks=rows,environment_evaluation_steps=len(traces),learning_steps=0,engineering_updates_repeated=0))


def accept_review(root):
    saved,p=context(root);path=Path(p['review_path'])
    if not path.is_file():raise ValueError('independent review absent: preparation/gate complete; await report, no formal training')
    text=path.read_text(encoding='utf-8');print(text,flush=True)
    # The human-readable conclusion must be inspected before this command is invoked.
    write_json(root/'review_acceptance.json',dict(root_config_sha256=sha(root/'config.yaml'),review_path=str(path),
        review_sha256=sha(path),read_at=now(),decision='review_read_no_unresolved_correctness_or_fairness_blocker',
        authorization='2026-10-29 main chat explicit prospective decision; not old performance gate passed'))


def learning_gate(root,saved):
    for name in ('handover.json','review_acceptance.json'):
        state=read_json(root/name)
        if state['root_config_sha256']!=sha(root/'config.yaml'):raise ValueError('gate identity changed')
    if not read_json(root/'handover.json')['passed']:raise ValueError('takeover failed')
    review=read_json(root/'review_acceptance.json')
    if sha(review['review_path'])!=review['review_sha256']:raise ValueError('independent review changed; read again')
    if (root/'selection.json').exists() or (root/'test').exists():raise ValueError('selection/test frozen')


def scores(rows):
    import numpy as np
    return float(np.mean([float(r['rmse_w']) for r in rows])),max(float(r['rmse_w']) for r in rows)


def radius(k):return .02+.08*min(1.,k/4096)


def train(root,arm,run,stop_after=None):
    import numpy as np
    import torch
    from .speed_nstep_algorithm import FrozenSpeedNStepMADDPG
    from .stable_workflow import Exploration
    saved,p=context(root)
    if arm not in ARMS or run not in range(3):raise ValueError('unknown arm/run')
    learning_gate(root,saved)
    if stop_after is not None and stop_after!=2048:raise ValueError('only declared 2048 restart boundary')
    job=root/'formal'/f'{arm}_run_{run}'
    if (job/'result.json').exists():
        result=read_json(job/'result.json');verify_hashes(result['hashes']);return
    noise=Exploration(np.random.SeedSequence(p['design_entropy']+[3,run,0]),[0.,0.,.15],[10.,3.,5.],1.,'white',.2)
    if (job/'state.json').exists():
        previous=read_json(job/'state.json');assert sha(previous['checkpoint'])==previous['sha256']
        agent,m=FrozenSpeedNStepMADDPG.load(previous['checkpoint'],expected_n=ARMS[arm])
        assert (m['arm'],m['run_id'],m['root_config_sha256'])==(arm,run,sha(root/'config.yaml'))
        step,ep,history,best,init,episodes,losses=m['step'],m['episode'],m['history'],m['best'],m['initial'],m['episodes'],m['pending_losses']
        noise.load_state_dict(m['noise']);restart=dict(checkpoint=previous['checkpoint'],sha256=previous['sha256'],
            step=step,episode=ep,source_process=previous['process'],new_process=None,uncommitted_attempts=[])
    else:
        if job.exists():raise ValueError('incomplete first state retained; inspect before continuing')
        job.mkdir(parents=True);agent=initial(saved,arm,run)
        step=ep=0;history=[];episodes=[];losses=[];best=init=None;restart=None
    attempts=list(job.glob('attempt_*'));attempt=max((int(x.name.split('_')[1]) for x in attempts),default=-1)+1
    out=job/f'attempt_{attempt:03d}';out.mkdir()
    import os
    pid=os.getpid()
    if restart:
        restart['new_process']=pid
        restart['uncommitted_attempts']=[str(x/'started.json') for x in attempts if (x/'started.json').exists() and not (x/'finished.json').exists()]
        write_json(out/'recovery.json',restart)
    write_json(out/'started.json',dict(process=pid,time=now(),from_step=step,formal_budget=8192))
    env=make_env(saved['base_config']);validation=bank(root,'validation')
    parent_weights=torch.load(saved['parents'][run]['checkpoint'],map_location='cpu',weights_only=False)['actors']
    def save(evaluate=False):
        nonlocal best,init,losses
        agent.config=replace(agent.config,speed_scale=2*.1/.667)
        path=str((out/f'step_{step:08d}.pth').resolve())
        if init is None:init=path
        if evaluate:
            m,t,_=rollout(saved['base_config'],validation,agent=agent);mean,worst=scores(m)
            if best is None or mean<best['score_w']:best=dict(checkpoint=path,step=step,score_w=mean,validation=m)
            history.append(dict(step=step,mean_rmse_w=mean,worst_rmse_w=worst,best_mean_w=best['score_w'],
                actor_loss=float(np.mean([l['actor_loss'] for l in losses])) if losses else 0.,
                critic_loss=float(np.mean([l['critic_loss'] for l in losses])) if losses else 0.))
            save_job(out/f'validation_{step:08d}',m,t);losses=[]
            print('Validation',arm,run,step,round(mean/1000,3),'best',best['step'],flush=True)
        for k,v in parent_weights.items():assert torch.equal(v,agent.actors.state_dict()[k])
        metadata=dict(arm=arm,run_id=run,step=step,episode=ep,history=history,best=best,initial=init,episodes=episodes,
            pending_losses=losses,noise=noise.state_dict(),root_config_sha256=sha(root/'config.yaml'),parent=saved['parents'][run],
            config=saved['base_config'],evaluation_radius=.1,next_transition_radius=radius(step),normalization=env.normalization())
        agent.save(path,metadata)
        write_json(job/'state.json',dict(checkpoint=path,sha256=sha(path),step=step,episode=ep,process=pid,attempt=attempt))
        return path
    if step==0:final=save(True)
    while step<8192:
        wind,target,pitch,family=episode(p,run,ep)
        env.initial=np.asarray(saved['base_config']['environment']['initial_operating_point'],float).copy();env.initial[1]=pitch
        obs,_=env.reset(seed=42,options=dict(wind_trajectory=wind.values,target_w=target));noise.reset()
        noise_hash=hashlib.sha256()
        errors=[];reward_total=0.
        for _ in range(128):
            agent.config=replace(agent.config,speed_scale=2*radius(step)/.667)
            perturb=noise.sample(step/8192);noise_hash.update(perturb.tobytes())
            action=agent.act(obs,noise=perturb);np.testing.assert_array_equal(action,env.project_action(action))
            nxt,reward,done,_,info=env.step(action);np.testing.assert_array_equal(action,info['executed_action'])
            agent.replay.add(obs,action,reward,nxt,done);step+=1
            if step>=512 and step%2==0:losses.append(agent.update())
            obs=nxt;errors.append(info['error_w']);reward_total+=float(reward[0])
        assert done
        episodes.append(dict(episode=ep,step=step,family=family,target_w=target,initial_pitch_rad=pitch,
            wind_sha256=hashlib.sha256(wind.values.tobytes()).hexdigest(),noise_sha256=noise_hash.hexdigest(),
            rmse_w=float(np.sqrt(np.mean(np.square(errors)))),reward_sum=reward_total))
        ep+=1;final=save(step%2048==0)
        if ep%8==0:print('Episode',arm,run,ep,'step',step,flush=True)
        if stop_after==step:
            write_json(out/'finished.json',dict(time=now(),saved_step=step,planned_exit=True));return
    assert ep==64
    result=dict(arm=arm,run_id=run,initial=init,selected=best['checkpoint'],selected_step=best['step'],final=final,
        initial_mean_w=history[0]['mean_rmse_w'],initial_worst_w=history[0]['worst_rmse_w'],
        selected_mean_w=best['score_w'],selected_worst_w=scores(best['validation'])[1],
        final_mean_w=history[-1]['mean_rmse_w'],final_worst_w=history[-1]['worst_rmse_w'],
        final_over_selected=history[-1]['mean_rmse_w']/best['score_w'],history=history,parent=saved['parents'][run],
        hashes={path:sha(path) for path in set((init,best['checkpoint'],final))},steps=8192)
    write_json(job/'result.json',result);write_json(out/'finished.json',dict(time=now(),saved_step=step,completed=True))
    context(root)


def lock(root):
    saved,p=context(root);results=[read_json(root/'formal'/f'{arm}_run_{run}'/'result.json') for run in range(3) for arm in ARMS]
    if (root/'selection.json').exists():raise ValueError('selection already locked')
    assert sum(r['steps'] for r in results)==49152
    for r in results:verify_hashes(r['hashes'])
    selection=dict(seed=42,results=results,hashes={k:v for r in results for k,v in r['hashes'].items()},
        root_config_sha256=sha(root/'config.yaml'),bank_sha256=saved['bank_sha256'],locked_at=now())
    write_json(root/'selection.json',selection)
    write_csv(root/'metrics.csv',[{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in results])
    write_csv(root/'history.csv',[dict(arm=r['arm'],run_id=r['run_id'],**h) for r in results for h in r['history']])
    write_json(root/'summary.txt',dict(status='selection_locked',seed=42,formal_training_steps=49152,smoke_steps=0,test_released=False))


def evaluate_test(root):
    saved,p=context(root);selection=read_json(root/'selection.json');verify_hashes(selection['hashes'])
    assert read_json(root/'core_verification.json')['selection_sha256']==sha(root/'selection.json')
    from .speed_nstep_algorithm import FrozenSpeedNStepMADDPG
    from .algorithm import MADDPG
    from .frozen_speed_training import ZeroSpeed,ControlMonitor
    out=root/'test'
    release=dict(selection_sha256=sha(root/'selection.json'),root_config_sha256=sha(root/'config.yaml'))
    if out.exists():assert read_json(out/'release.json')==release
    else:
        out.mkdir();write_json(out/'release.json',release);freeze_bank(out/'bank',p,'test')
    if (out/'complete.json').exists():
        verify_hashes({str(out/k):v for k,v in read_json(out/'complete.json').items()});return
    cases=bank(root,'test');metrics=[];traces=[];corrections=[]
    def evaluate(name,tags,agent=None,mode=None):
        folder=out/name
        if not folder.exists():
            monitor=ControlMonitor(agent,agent.agent.config.speed_schedule if isinstance(agent,ZeroSpeed) else
                (agent.config.speed_schedule if hasattr(agent.config,'speed_schedule') else agent.config.speed_reference_schedule)) if agent else None
            rows,t,_=rollout(saved['base_config'],cases,agent=monitor,mode=mode)
            save_job(folder,rows,t,monitor.summary() if monitor else {})
        rows,t=load_job(folder);metrics.extend(dict(**tags,**r) for r in rows);traces.extend(dict(**tags,**r) for r in t)
        corrections.append(dict(**tags,**read_json(folder/'corrections.json')))
        print('Test',name,flush=True)
    for r in selection['results']:
        for label in ('initial','selected','final','zero_selected','zero_final'):
            role=label.removeprefix('zero_');agent,_=FrozenSpeedNStepMADDPG.load(r[role],expected_n=ARMS[r['arm']])
            if label.startswith('zero_'):agent=ZeroSpeed(agent)
            evaluate(f"{r['arm']}_{r['run_id']}_{label}",dict(arm=r['arm'],run_id=r['run_id'],controller=label),agent=agent)
    for run in range(3):
        agent,_=MADDPG.load(saved['parents'][run]['checkpoint'])
        evaluate(f'parent_{run}',dict(arm='parent',run_id=run,controller='parent'),agent=agent)
    for mode in ('fixed','p','pi'):evaluate('common_'+mode,dict(arm='common',run_id=-1,controller=mode),mode=mode)
    check=recompute(metrics,traces,('arm','run_id','controller','case_id'))
    assert check['metric_rows']==720 and check['trace_rows']==92160
    write_csv(out/'metrics.csv',metrics);write_csv(out/'trajectories.csv',traces)
    # Baselines have no correction fields; keep a consistent superset schema.
    fields=set().union(*(r.keys() for r in corrections))
    write_csv(out/'corrections.csv',[{k:r.get(k,'') for k in sorted(fields)} for r in corrections])
    write_json(out/'verification.json',check)
    write_json(out/'complete.json',{n:sha(out/n) for n in ('release.json','metrics.csv','trajectories.csv','corrections.csv','verification.json')})
    context(root)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','gate','accept-review','worker','lock','test','audit','diagnostic','figures'))
    parser.add_argument('--output',required=True);parser.add_argument('--arm',choices=tuple(ARMS));parser.add_argument('--run-id',type=int)
    parser.add_argument('--stop-after',type=int);args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    root=Path(args.output).resolve()
    if args.command=='prepare':prepare(root,protocol())
    elif args.command=='gate':gate(root)
    elif args.command=='accept-review':accept_review(root)
    elif args.command=='worker':train(root,args.arm,args.run_id,args.stop_after)
    elif args.command=='lock':lock(root)
    elif args.command=='test':evaluate_test(root)
    else:
        from . import speed_nstep_audit
        getattr(speed_nstep_audit,args.command)(root)


if __name__=='__main__':main()
