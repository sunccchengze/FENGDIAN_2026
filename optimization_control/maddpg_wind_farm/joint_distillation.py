"""Bounded joint distillation, paired continuations and once-only held-out evaluation."""
from __future__ import annotations
import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from . import random_wind_training as shared
from .fixed_pinn_demo import activate_runtime, digest
from .progressive_random_control import verify_hashes

DEFAULT = Path(__file__).parent / 'configs/joint_distillation.yaml'
VERSION = 'wind12_joint_distillation_v1'

def read_protocol(path):
    import yaml
    p = yaml.safe_load(Path(path).read_text(encoding='utf-8-sig'))
    if p['version'] != VERSION or p['seed'] != 42 or p['run_ids'] != [0, 1, 2]:
        raise ValueError('fixed joint protocol and three seed42 streams required')
    if p['steps_per_run'] != 16384 or p['eval_every'] != 4096:
        raise ValueError('predeclared bounded budgets required')
    d = p['distillation']
    if len(d['candidates']) > 2 or d['old_max_error'] > .02 or d['new_max_error'] > .05:
        raise ValueError('distillation bound cannot be relaxed')
    if any(c['updates'] > 5000 for c in d['candidates']):
        raise ValueError('bounded mini-batch update count required')
    if p['engineering_gate'] != dict(max_parent_mean_ratio=1.05,max_parent_worst_ratio=1.05,max_final_over_selected=1.25):
        raise ValueError('predeclared engineering gates required')
    groups = [set(p[k]) for k in ('training_targets_w','validation_targets_w','test_targets_w')]
    if any(groups[a] & groups[b] for a,b in ((0,1),(0,2),(1,2))):
        raise ValueError('disjoint targets required')
    return p

def reset_actor_optimizers(agent):
    import torch
    agent.actor_optimizers = [torch.optim.Adam(m.parameters(), lr=agent.config.actor_lr) for m in agent.actors]

def distill(agent, mask, settings):
    """Teachers retain each parent's effective policy; fit no test or closed-loop data."""
    import numpy as np
    import torch
    old = tuple(agent.config.action_mask); new = tuple(mask)
    if {(0,1,0):(0,1,1),(0,1,1):(1,1,1)}.get(old) != new:
        raise ValueError('exactly speed then yaw permission must open')
    channel = next(i for i in range(3) if not old[i] and new[i])
    if agent.replay.size < 128:
        raise ValueError('parent training replay required')
    indices = np.linspace(0,agent.replay.size-1,min(settings['sample_rows'],agent.replay.size),dtype=int)
    held = np.arange(len(indices)) % 5 == 0
    diagnostics = []
    original = {kind:deepcopy(getattr(agent,kind).state_dict()) for kind in ('actors','target_actors')}
    for candidate_id, candidate in enumerate(settings['candidates']):
        reports = []
        for kind in ('actors','target_actors'):
            networks = getattr(agent,kind); networks.load_state_dict(original[kind])
            for i, actor in enumerate(networks):
                states = torch.as_tensor(agent.replay.data['obs'][indices,i],device=agent.device)
                with torch.no_grad(): teacher = agent.policy(actor,states).detach().clone()
                actor.requires_grad_(True)
                optimizer = torch.optim.Adam(actor.parameters(),lr=candidate['lr'])
                active = [j for j in range(3) if new[j]]
                weights = torch.tensor([settings['old_loss_weight'] if old[j] else 1. for j in active],device=agent.device)
                fit = np.flatnonzero(~held); rng = np.random.default_rng(np.random.SeedSequence([42,901,candidate_id,i,kind=='target_actors']))
                def errors():
                    with torch.no_grad(): error=(actor(states)-teacher).abs().cpu().numpy()
                    old_error=error[held][:,[j for j in range(3) if old[j]]]
                    new_error=error[held,channel]
                    return error, float(old_error.max()), float(new_error.max())
                for step in range(1,candidate['updates']+1):
                    batch = rng.choice(fit,size=min(settings['batch_size'],len(fit)),replace=False)
                    residual = actor(states[batch])[:,active]-teacher[batch][:,active]
                    loss=(residual.square()*weights).mean()
                    optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
                    if step % 100 == 0:
                        error,old_max,new_max=errors()
                        if old_max<=settings['old_max_error'] and new_max<=settings['new_max_error']: break
                error,old_max,new_max=errors()
                report=dict(candidate=candidate_id,network=kind,agent=i,updates=step,old_held_max=old_max,new_held_max=new_max,
                    held_p95=float(np.quantile(error[held][:,active],.95)),held_rms=float(np.sqrt(np.mean(error[held][:,active]**2))),
                    fit_max=float(error[~held][:,active].max()),passed=old_max<=settings['old_max_error'] and new_max<=settings['new_max_error'])
                reports.append(report)
                if kind=='target_actors': actor.requires_grad_(False)
        diagnostics.extend(reports)
        print('Distillation',json.dumps(reports),flush=True)
        if all(r['passed'] for r in reports):
            agent.config=replace(agent.config,action_mask=new,speed_reference_schedule=None if new[2] else agent.config.speed_reference_schedule)
            reset_actor_optimizers(agent)
            return dict(passed=True,selected_candidate=candidate_id,reports=diagnostics,rows=len(indices),held_rows=int(held.sum()))
    for kind in original: getattr(agent,kind).load_state_dict(original[kind])
    reset_actor_optimizers(agent)
    return dict(passed=False,selected_candidate=None,reports=diagnostics,rows=len(indices),held_rows=int(held.sum()))

def prepare(p, output):
    import yaml
    source=Path(p['bootstrap_experiment']).resolve()
    selection=json.loads((source/'selection.json').read_text(encoding='utf-8'))
    bootstrap={}
    for run in p['run_ids']:
        r=next(r for r in selection['results'] if r['stage']=='pitch' and r['run_id']==run)
        verify_hashes(r['hashes']); path=r['best']['checkpoint']
        bootstrap[str(run)]=dict(checkpoint=path,sha256=digest(path),cumulative_steps=r['cumulative_steps']-r['steps']+r['best']['step'])
    root=shared.prepare(p,output)
    saved=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8')); saved['bootstrap']=bootstrap
    files=[source/'selection.json',Path(__file__),DEFAULT,Path(__file__).with_name('JOINT_DISTILLATION.md')]
    files += [Path(v['checkpoint']) for v in bootstrap.values()]
    files += [Path(__file__).with_name(s) for s in ('algorithm.py','random_wind_training.py','controllers.py','workflow.py')]
    saved['source_hashes'].update({str(f.resolve()):digest(f) for f in files})
    (root/'config.yaml').write_text(yaml.safe_dump(saved,sort_keys=False,allow_unicode=True),encoding='utf-8')
    return root

def metrics(rows):
    import numpy as np
    return float(np.mean([r['rmse_w'] for r in rows])),max(r['rmse_w'] for r in rows)

def handover(root,stage,run,parent,p):
    import torch
    from .algorithm import MADDPG
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    agent,meta=MADDPG.load(parent['checkpoint']); verify_hashes({parent['checkpoint']:parent['sha256']})
    old_cfg=deepcopy(meta['config']); cfg=deepcopy(old_cfg); cfg['environment']['control_mask']=dict(shared.STAGES)[stage]
    parent_rows,_=shared.rollout(old_cfg,shared.cases(root,'validation'),agent=agent)
    report=distill(agent,dict(shared.STAGES)[stage],p['distillation'])
    before_mean,before_worst=metrics(parent_rows)
    if report['passed']:
        rows,_=shared.rollout(cfg,shared.cases(root,'validation'),agent=agent)
        after_mean,after_worst=metrics(rows)
    else: after_mean=after_worst=None
    report.update(parent_mean_w=before_mean,parent_worst_w=before_worst,initial_mean_w=after_mean,initial_worst_w=after_worst)
    report['engineering_handover_pass']=bool(report['passed'] and after_mean<=1.05*before_mean and after_worst<=1.05*before_worst)
    job=root/f'{stage}_run_{run}'; job.mkdir()
    shared.write_json(job/'distillation.json',report)
    if not report['engineering_handover_pass']: return None,report
    initial=job/'handover.pth'
    lineage=dict(parent_checkpoint=parent['checkpoint'],parent_sha256=parent['sha256'],cumulative_parent_steps=parent['cumulative_steps'],
        inherited_replay_size=agent.replay.size,parent_validation_rmse_w=before_mean,parent_worst_rmse_w=before_worst,
        actor_optimizer_reset=True,target_actor_fitted_separately=True,critic_optimizer_replay_inherited=True)
    agent.save(initial,dict(config=cfg,lineage=lineage,normalization=meta['normalization']))
    return dict(checkpoint=str(initial.resolve()),sha256=digest(initial),config=cfg,lineage=lineage),report

def train(root,stage,run,parent,p,*,control=False):
    import numpy as np
    import torch
    from .algorithm import MADDPG
    from .workflow import build_env
    from .stable_workflow import Exploration
    from .benchmark import seed_for
    from ..environments.farm_inflow import generate_inflow
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    agent,meta=MADDPG.load(parent['checkpoint']); verify_hashes({parent['checkpoint']:parent['sha256']})
    cfg=deepcopy(meta['config']); lineage=deepcopy(meta.get('lineage',{}))
    if control:
        reset_actor_optimizers(agent)
        lineage=dict(parent_checkpoint=parent['checkpoint'],parent_sha256=parent['sha256'],cumulative_parent_steps=parent['cumulative_steps'],
            inherited_replay_size=agent.replay.size,actor_optimizer_reset=True)
    label=stage+('_control' if control else '')
    job=root/f'{label}_run_{run}'
    if control: job.mkdir()
    if (job/'result.json').exists(): raise ValueError('completed job is immutable')
    env=build_env(cfg); validation=shared.cases(root,'validation')
    phase=['pitch_speed','all'].index(stage)
    noise_std=p['stage_noise_std']['pitch' if control and stage=='pitch_speed' else 'pitch_speed' if control else stage]
    noise=Exploration(seed_for(42,913+phase,run),noise_std,[10.,3.,5.],env.dt,'white',p['noise_end_fraction'])
    history=[]; best=None; step=episode=0
    initial_rows,_=shared.rollout(cfg,validation,agent=agent)
    parent_mean=lineage.get('parent_validation_rmse_w',metrics(initial_rows)[0]); parent_worst=lineage.get('parent_worst_rmse_w',metrics(initial_rows)[1])
    def snapshot(losses):
        nonlocal best
        rows,_=shared.rollout(cfg,validation,agent=agent); mean,worst=metrics(rows)
        path=str((job/f'step_{step:08d}.pth').resolve())
        if best is None or mean<best['score_w']: best=dict(score_w=mean,checkpoint=path,step=step,validation=rows)
        history.append(dict(steps=step,validation_rmse_w=mean,worst_validation_rmse_w=worst,best_rmse_w=best['score_w']))
        agent.save(path,dict(config=cfg,lineage=lineage,steps=step,episodes=episode,history=history,best=best,noise=noise.state_dict(),normalization=env.normalization()))
        shared.write_csv(job/'metrics.csv',history)
        print('Training',label,run,json.dumps(history[-1]),flush=True)
        return path
    initial=snapshot([])
    while step<p['steps_per_run']:
        family,target,pitch=shared.episode_design(p,run,episode)
        inflow=deepcopy(p['inflow']); inflow['speed']['scenario']=family
        wind=generate_inflow(inflow,dt_s=env.dt,horizon=env.horizon,seed=42,split='train',episode=p['training_episode_offset']+phase*10000+run*1000+episode)
        env.initial=np.asarray(cfg['environment']['initial_operating_point'],dtype=float).copy(); env.initial[1]=pitch
        obs,_=env.reset(seed=42,options=dict(wind_trajectory=wind.values,target_w=target)); noise.reset()
        for _ in range(env.horizon):
            action=env.project_action(np.clip(agent.act(obs)+noise.sample(step/p['steps_per_run']),-1,1)).astype(np.float32)
            nxt,reward,done,_,info=env.step(action); agent.replay.add(obs,info['executed_action'],reward,nxt,done)
            step+=1
            if step>=p['warmup_steps'] and step%p['update_every']==0: agent.update()
            obs=nxt
        episode+=1
        if step%p['eval_every']==0: final=snapshot([])
    ratio=history[-1]['validation_rmse_w']/best['score_w']; _,worst=metrics(best['validation'])
    engineering=best['score_w']<=1.05*parent_mean and worst<=1.05*parent_worst and ratio<=1.25
    strict=best['score_w']<=400000 and worst<=500000 and ratio<=1.25
    result=dict(stage=label,run_id=run,config=cfg,initial=initial,best=best,final=final,steps=step,final_over_best=ratio,
        initial_rmse_w=history[0]['validation_rmse_w'],engineering_pass=bool(engineering),strict_accuracy_pass=bool(strict),passed=bool(engineering),
        lineage=lineage,inherited_replay_size=lineage['inherited_replay_size'],cumulative_steps=lineage['cumulative_parent_steps']+step,
        hashes={f:digest(f) for f in set((initial,best['checkpoint'],final))})
    shared.write_json(job/'result.json',result)
    return result

def execute(root):
    import yaml
    root=Path(root).resolve(); saved=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8')); p=saved['protocol']
    if (root/'selection.json').exists() or (root/'test').exists(): raise ValueError('frozen selection prohibits additional training')
    verify_hashes(saved['source_hashes']); parents=saved['bootstrap']; results=[]; gates=[]
    for stage in ('pitch_speed','all'):
        transfers=[]; reports=[]
        for run in p['run_ids']:
            transfer,report=handover(root,stage,run,parents[str(run)],p); transfers.append(transfer); reports.append(report)
        gate=dict(stage=stage,handover_passed_runs=sum(r['engineering_handover_pass'] for r in reports),engineering_pass=False)
        gates.append(gate)
        if not all(transfers): break
        children=[]
        for run,transfer in zip(p['run_ids'],transfers):
            children.append(train(root,stage,run,transfer,p)); results.append(children[-1])
            results.append(train(root,stage,run,parents[str(run)],p,control=True))
        gate['engineering_pass']=all(r['engineering_pass'] for r in children)
        gate['strict_accuracy_passed_runs']=sum(r['strict_accuracy_pass'] for r in children)
        if not gate['engineering_pass']: break
        parents={str(r['run_id']):dict(checkpoint=r['best']['checkpoint'],sha256=digest(r['best']['checkpoint']),cumulative_steps=r['cumulative_steps']-r['steps']+r['best']['step']) for r in children}
    hashes={f:h for r in results for f,h in r['hashes'].items()}
    hashes.update({v['checkpoint']:v['sha256'] for v in saved['bootstrap'].values()})
    shared.write_json(root/'selection.json',dict(seed=42,results=results,gates=gates,bank_sha256=digest(root/'bank/manifest.json'),hashes=hashes,root_config_sha256=digest(root/'config.yaml')))
    shared.write_csv(root/'metrics.csv',[dict(stage=r['stage'],run_id=r['run_id'],steps=r['steps'],selected_step=r['best']['step'],selected_mean_w=r['best']['score_w'],selected_worst_w=metrics(r['best']['validation'])[1],final_over_selected=r['final_over_best'],engineering_pass=r['engineering_pass'],strict_accuracy_pass=r['strict_accuracy_pass']) for r in results] if results else [dict(stage=g['stage'],handover_passed_runs=g['handover_passed_runs'],engineering_pass=False) for g in gates])
    if results: shared.test_locked(root)
    else:
        shared.write_json(root/'summary.txt',dict(seed=42,completed=True,training_steps=0,gates=gates,test_released=False,reason='handover failed: no RL or independent test permitted',physical_validation=False))
    verify_hashes(saved['source_hashes'])

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('command',choices=['prepare','run','all']); ap.add_argument('--output',required=True); ap.add_argument('--protocol',default=str(DEFAULT)); a=ap.parse_args()
    p=read_protocol(a.protocol); activate_runtime(p['runtime_site_packages']); sys.dont_write_bytecode=True
    root=Path(a.output)
    if a.command in ('prepare','all'): root=prepare(p,root)
    if a.command in ('run','all'): execute(root)

if __name__=='__main__': main()
