"""Frozen-parent speed experiment: precision gate, smoke, paired learning and test."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys

from .anchor_closeout import sha, write_json, write_csv, read_json, read_csv, verify_hashes, rollout, recompute, make_env, checked_output, save_job, load_job

DEFAULT=Path(__file__).with_name('configs')/'frozen_speed.yaml'
MODE='observation_float32_v1'


def protocol(path=DEFAULT):
    import yaml
    p=yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if p['version']!='frozen_parent_speed_v1' or p['seed']!=42 or (p['steps_per_run'],p['eval_every'],p['warmup_steps'],p['update_every'],p['smoke_steps_per_arm'])!=(8192,2048,512,2,1024):
        raise ValueError('frozen budget and master seed42 required')
    if p['gate']!=dict(action_atol=2e-6,applied_atol=1e-6,power_atol_w=1.,max_final_selected=1.25,max_noninferior_ratio=1.05,min_mean_gain_fraction=.01):
        raise ValueError('predeclared acceptance thresholds cannot change')
    return p


def prepare(output,p):
    import yaml
    import torch
    from . import random_wind_training as shared
    origin=Path(p['origin']).resolve();worktree=Path(__file__).resolve().parents[2]
    root=checked_output(output,worktree,origin)
    old=yaml.safe_load((Path(__file__).parent/'configs/residual_random_control.yaml').read_text(encoding='utf-8'))
    combined=dict(old,**p)
    combined.update(source_experiment=str(origin/'optimization_control/experiments/20261022_wind_pinn_integration'),actor_lr=1e-4,run_ids=[0,1,2],scope='frozen_parent_speed_software_only')
    parents=[]
    protected={}
    for run,(step,expected) in enumerate(zip(p['parent_steps'],p['parent_sha256'])):
        path=origin/f'optimization_control/experiments/20261023_progressive_random_control/pitch_run_{run}/segment_000/step_{step:08d}.pth'
        if sha(path)!=expected:raise ValueError('fixed parent SHA mismatch')
        state=torch.load(path,map_location='cpu',weights_only=False)
        if state['version']!=1 or state['config']['action_mask']!=[0,1,0] and tuple(state['config']['action_mask'])!=(0,1,0):raise ValueError('pitch parent required')
        parents.append(dict(run_id=run,checkpoint=str(path),sha256=expected,cumulative_parent_steps=state['metadata']['lineage']['cumulative_parent_steps']+step if 'cumulative_parent_steps' in state['metadata']['lineage'] else 16384+step))
        protected[str(path)]=expected
    root=shared.prepare(combined,root)
    saved=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    saved['base_config']['environment']['speed_reference_mode']=MODE
    saved['parents']=parents;saved['original_workspace']=str(origin);saved['worktree']=str(worktree)
    protected.update(saved['source_hashes'])
    for name in ('PROJECT_STATUS.md','README.md','optimization_control/TASKFLOW.md','optimization_control/environments/maddpg_farm_env.py'):
        protected[str(origin/name)]=sha(origin/name)
    saved['source_hashes']=protected
    execution={}
    for folder in ('maddpg_wind_farm','environments','utils'):
        for path in (worktree/'optimization_control'/folder).glob('*.py'):execution[str(path)]=sha(path)
    for path in (DEFAULT,Path(__file__).with_name('FROZEN_SPEED_PROTOCOL.md')):execution[str(path)]=sha(path)
    saved['executed_code_hashes']=execution
    saved['base_commit']=subprocess.check_output(['git','-c','safe.directory='+str(worktree),'rev-parse','HEAD'],text=True,cwd=worktree).strip()
    (root/'config.yaml').write_text(yaml.safe_dump(saved,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    write_json(root/'summary.txt',dict(status='prepared',seed=42,formal_training_steps=0,smoke_steps=0,test_locked=True))
    print('Prepared frozen speed',root,flush=True)
    return root


def context(root):
    import yaml
    root=Path(root).resolve();saved=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    checked_output(root,saved['worktree'],saved['original_workspace'])
    verify_hashes(saved['source_hashes']);verify_hashes(saved['executed_code_hashes'])
    return saved,saved['protocol']


def configure(parent):
    import torch
    parent.config=replace(parent.config,actor_lr=1e-4)
    parent.actor_optimizers=[torch.optim.Adam(a.parameters(),lr=1e-4) for a in parent.actors]


def initial(saved,arm,run):
    from .algorithm import MADDPG
    from .frozen_speed_algorithm import FrozenSpeedMADDPG
    from .benchmark import seed_for
    parent=saved['parents'][run]
    agent,_=MADDPG.load(parent['checkpoint']);configure(agent)
    if arm=='speed':agent=FrozenSpeedMADDPG.from_parent(agent,seed_for(42,saved['protocol']['head_namespace'],run))
    elif arm!='baseline':raise ValueError('unknown arm')
    cfg=deepcopy(saved['base_config']);cfg['environment']['control_mask']=[0,1,1] if arm=='speed' else [0,1,0]
    cfg['algorithm']['actor_lr']=1e-4
    return agent,cfg


def scale(step):return 2*(.02+.08*min(1.,step/4096))/.667


def set_scale(agent,step):
    if hasattr(agent.config,'speed_scale'):agent.config=replace(agent.config,speed_scale=scale(step))


def action(agent,arm,obs,noise):
    import numpy as np
    if arm=='speed':return agent.act(obs,noise=noise)
    a=agent.act(obs);a[:,1]=np.clip(a[:,1]+np.asarray(noise,dtype=np.float32)[:,1],-1,1)
    return a


def scores(rows):
    import numpy as np
    return float(np.mean([float(r['rmse_w']) for r in rows])),max(float(r['rmse_w']) for r in rows)


def gate(root):
    import numpy as np
    import torch
    from . import random_wind_training as shared
    from .anchor_closeout_diagnostic import trajectory_differences
    saved,p=context(root);bank=shared.cases(root,'validation');records=[]
    oldpath=Path(saved['original_workspace'])/'optimization_control/environments/maddpg_farm_env.py'
    spec=importlib.util.spec_from_file_location('optimization_control.environments._original_speed_gate',oldpath)
    oldmodule=importlib.util.module_from_spec(spec);spec.loader.exec_module(oldmodule)
    replay_records=[]
    for run in range(3):
        parent,pcfg=initial(saved,'baseline',run);child,ccfg=initial(saved,'speed',run)
        maximum=0.;schedule_delta=0.
        from ..utils.reference_schedule import speed_numpy
        for field in ('obs','next_obs'):
            data=parent.replay.data[field][:parent.replay.size]
            for target in (False,True):
                for i in range(3):
                    for start in range(0,len(data),4096):
                        x=torch.tensor(data[start:start+4096,i])
                        actor=(parent.target_actors if target else parent.actors)[i]
                        with torch.no_grad():delta=(parent.policy(actor,x)-child.total_action(i,x,target=target)).abs().max().item()
                        maximum=max(maximum,delta)
        data=parent.replay.state_dict()['data']
        np.testing.assert_array_equal(data['actions'],data['next_obs'][:,:,5:8])
        scheduled=speed_numpy(data['obs'],parent.config.speed_reference_schedule)
        schedule_delta=float(np.abs(data['actions'][:,:,2]-scheduled).max())
        replay_records.append(dict(run_id=run,rows=parent.replay.size,old_actions_preserved=True,total_action_next_command_exact=True,max_old_vs_new_schedule_difference=schedule_delta,same_physical_absolute_target_semantics=True))
        pa,pt,_=rollout(pcfg,bank,agent=parent);ca,ct,_=rollout(ccfg,bank,agent=child)
        diff=trajectory_differences(pt,ct);rmse=max(abs(a['rmse_w']-b['rmse_w']) for a,b in zip(pa,ca))
        # Compare legacy behavior with the untouched original environment class.
        legacy_cfg=deepcopy(pcfg);legacy_cfg['environment'].pop('speed_reference_mode')
        old_new_differences=[]
        for case,wind in bank:
            env=make_env(legacy_cfg);old_env=oldmodule.MADDPGFarmEnv(env.plant,legacy_cfg['environment'])
            env.initial[1]=old_env.initial[1]=case['initial_pitch_rad']
            opts=dict(wind_trajectory=wind.values,target_w=case['target_w'])
            oa,_=env.reset(seed=42,options=opts);ob,_=old_env.reset(seed=42,options=opts)
            np.testing.assert_array_equal(oa,ob)
            for _ in range(env.horizon):
                act=parent.act(oa);oa,ra,da,_,ia=env.step(act);ob,rb,db,_,ib=old_env.step(act)
                np.testing.assert_array_equal(oa,ob);np.testing.assert_array_equal(ra,rb)
                np.testing.assert_array_equal(ia['applied'],ib['applied']);assert da==db
        legacy_rows,legacy_trace,_=rollout(legacy_cfg,bank,agent=parent)
        legacy_diff=trajectory_differences(legacy_trace,pt)
        passed=maximum<=p['gate']['action_atol'] and diff['max_action_difference']<=p['gate']['action_atol'] and diff['max_applied_difference']<=p['gate']['applied_atol'] and max(rmse,diff['max_power_difference_w'])<=p['gate']['power_atol_w']
        records.append(dict(run_id=run,max_online_target_action_difference=maximum,max_rmse_difference_w=rmse,**diff,legacy_original_exact=True,old_mode_to_new_mode_max_power_difference_w=legacy_diff['max_power_difference_w'],passed=bool(passed)))
        print('Takeover gate',records[-1],flush=True)
    write_json(root/'handover.json',dict(seed=42,root_config_sha256=sha(root/'config.yaml'),checks=records,replay_checks=replay_records,passed=all(r['passed'] for r in records),formal_steps_added=0))
    write_csv(root/'handover.csv',records)
    write_json(root/'summary.txt',dict(status='handover_passed' if all(r['passed'] for r in records) else 'handover_failed',seed=42,formal_training_steps=0,smoke_training_steps=0))
    context(root)


def episode(root,p,run,episode,smoke=False):
    from . import random_wind_training as shared
    from ..environments.farm_inflow import generate_inflow
    family,target,pitch=shared.episode_design(p,run,episode)
    inflow=deepcopy(p['inflow']);inflow['speed']['scenario']=family
    wind=generate_inflow(inflow,dt_s=p['dt_s'],horizon=p['horizon'],seed=42,split='train',episode=(p['smoke_episode_offset'] if smoke else p['training_episode_offset'])+run*1000+episode)
    return wind,target,pitch


def train(root,arm,run,*,smoke=False,stop_after=None):
    import numpy as np
    from . import random_wind_training as shared
    from .frozen_speed_algorithm import load_policy
    from .stable_workflow import Exploration
    from .benchmark import seed_for
    saved,p=context(root)
    if run not in range(3) or arm not in ('baseline','speed'):raise ValueError('unknown paired stream or arm')
    handover=read_json(root/'handover.json')
    if not handover['passed'] or handover['root_config_sha256']!=sha(root/'config.yaml'):raise ValueError('strict handover failed or identity changed; learning prohibited')
    if (root/'selection.json').exists() or (root/'test').exists():raise ValueError('selection/test frozen; training prohibited')
    if not smoke and (not (root/'smoke/verification.json').exists() or not read_json(root/'smoke/verification.json')['passed']):raise ValueError('smoke must pass first')
    budget=p['smoke_steps_per_arm'] if smoke else p['steps_per_run']
    if stop_after is not None and (smoke or stop_after%2048 or not 0<stop_after<budget):raise ValueError('stop_after must be an interior formal evaluation boundary')
    job=root/('smoke' if smoke else 'formal')/f'{arm}_run_{run}'
    if (job/'result.json').exists():
        result=read_json(job/'result.json');verify_hashes(result['hashes']);return result
    noise=Exploration(seed_for(42,p['smoke_noise_namespace'] if smoke else p['noise_namespace'],run),[0.,0.,.15] if arm=='speed' else [0.,.03,0.],[10.,3.,5.],p['dt_s'],'white',.2)
    if job.exists():
        states=sorted(job.glob('segment_*/state.json'))
        if not states:raise ValueError('incomplete job retained; use a new experiment')
        state=read_json(states[-1]);agent,meta=load_policy(state['checkpoint'])
        if (meta['root_config_sha256'],meta['arm'],meta['run_id'],meta['smoke'])!=(sha(root/'config.yaml'),arm,run,smoke) or meta['parent']!=saved['parents'][run]:raise ValueError('recovery identity differs')
        step,ep,history,best,init=meta['step'],meta['episode'],meta['history'],meta['best'],meta['initial']
        cfg=meta['config'];noise.load_state_dict(meta['noise'])
        segment=max(int(path.name.split('_')[1]) for path in job.glob('segment_*'))+1
        final=state['checkpoint']
        if stop_after is not None and step>=stop_after:raise ValueError('stop_after must be later than the resumed checkpoint')
    else:
        job.mkdir(parents=True,exist_ok=False);agent,cfg=initial(saved,arm,run)
        step=ep=segment=0;history=[];best=init=None
    env=make_env(cfg);out=job/f'segment_{segment:03d}';out.mkdir()
    import torch
    parent_weights=torch.load(saved['parents'][run]['checkpoint'],map_location='cpu',weights_only=False)['actors']
    def snapshot(losses):
        nonlocal best,init
        set_scale(agent,8192)
        rows,_,_=rollout(cfg,shared.cases(root,'validation'),agent=agent)
        mean,worst=scores(rows);path=str((out/f'step_{step:08d}.pth').resolve())
        if init is None:init=path
        if best is None or mean<best['score_w']:best=dict(checkpoint=path,score_w=mean,step=step,validation=rows)
        if arm=='speed':
            for key,value in parent_weights.items():
                import torch
                assert torch.equal(value,agent.actors.state_dict()[key])
        history.append(dict(step=step,mean_rmse_w=mean,worst_rmse_w=worst,best_mean_w=best['score_w'],actor_loss=float(np.mean([l['actor_loss'] for l in losses])) if losses else 0.,critic_loss=float(np.mean([l['critic_loss'] for l in losses])) if losses else 0.))
        meta=dict(step=step,episode=ep,history=history,best=best,initial=init,config=cfg,arm=arm,run_id=run,smoke=smoke,
            root_config_sha256=sha(root/'config.yaml'),parent=saved['parents'][run],noise=noise.state_dict(),training_scale=scale(step),evaluation_scale=scale(8192),normalization=env.normalization())
        agent.save(path,meta);write_json(out/'state.json',dict(checkpoint=path,step=step,completed=step==budget));write_csv(out/'metrics.csv',history)
        set_scale(agent,step)
        print('Snapshot',arm,run,'smoke' if smoke else 'formal',step,round(mean/1000,2),flush=True)
        return path
    if step==0:final=snapshot([])
    losses=[]
    while step<budget:
        wind,target,pitch=episode(root,p,run,ep,smoke)
        env.initial=np.asarray(cfg['environment']['initial_operating_point'],float).copy();env.initial[1]=pitch
        obs,_=env.reset(seed=42,options=dict(wind_trajectory=wind.values,target_w=target));noise.reset()
        for _ in range(env.horizon):
            set_scale(agent,step);act=action(agent,arm,obs,noise.sample(step/8192))
            np.testing.assert_array_equal(act,env.project_action(act))
            nxt,reward,done,_,info=env.step(act)
            np.testing.assert_array_equal(act,info['executed_action'])
            agent.replay.add(obs,act,reward,nxt,done);step+=1
            if step>=512 and step%2==0:losses.append(agent.update())
            obs=nxt
        ep+=1
        if step%2048==0 or step==budget:
            final=snapshot(losses);losses=[]
            if stop_after==step and step<budget:return None
    r=dict(arm=arm,run_id=run,initial=init,selected=best['checkpoint'],selected_step=best['step'],selected_mean_w=best['score_w'],selected_worst_w=scores(best['validation'])[1],final=final,
        final_mean_w=history[-1]['mean_rmse_w'],final_worst_w=history[-1]['worst_rmse_w'],steps=step,parent=saved['parents'][run],config=cfg,
        final_over_selected=history[-1]['mean_rmse_w']/best['score_w'],initial_mean_w=history[0]['mean_rmse_w'],initial_worst_w=history[0]['worst_rmse_w'],segments=segment+1,
        hashes={path:sha(path) for path in set((init,best['checkpoint'],final))})
    write_json(job/'result.json',r);context(root)
    return r


def smoke(root):
    from .frozen_speed_verify import verify_smoke
    for arm in ('baseline','speed'):train(root,arm,0,smoke=True)
    verify_smoke(root)


def run(root):
    saved,p=context(root)
    if (root/'selection.json').exists():raise ValueError('selection already frozen')
    results=[]
    for run_id in range(3):
        for arm in ('baseline','speed'):
            if run_id==0 and not (root/f'formal/{arm}_run_0/segment_000/state.json').exists():train(root,arm,run_id,stop_after=2048)
            results.append(train(root,arm,run_id))
    rows=[]
    for r in results:
        b=next(v for v in results if v['arm']=='baseline' and v['run_id']==r['run_id'])
        r['parent_noninferior']=r['final_mean_w']<=1.05*r['initial_mean_w'] and r['final_worst_w']<=1.05*r['initial_worst_w']
        r['baseline_noninferior']=r['final_mean_w']<=1.05*b['final_mean_w'] and r['final_worst_w']<=1.05*b['final_worst_w']
        r['stable']=r['final_over_selected']<=1.25 and r['parent_noninferior'] and r['baseline_noninferior']
        r['selected_learned']=r['selected_step']>0 and r['selected_mean_w']<r['initial_mean_w']
        r['selected_accuracy']=r['selected_mean_w']<=400000 and r['selected_worst_w']<=500000
        r['final_accuracy']=r['final_mean_w']<=400000 and r['final_worst_w']<=500000
        rows.append({k:v for k,v in r.items() if k not in ('config','hashes') and not isinstance(v,dict)})
    hashes={k:v for r in results for k,v in r['hashes'].items()}
    selection=dict(seed=42,results=results,hashes=hashes,root_config_sha256=sha(root/'config.yaml'),bank_sha256=sha(root/'bank/manifest.json'))
    write_json(root/'selection.json',selection);write_csv(root/'metrics.csv',rows)
    write_json(root/'summary.txt',dict(status='selection_frozen',seed=42,formal_training_steps=49152,smoke_training_steps=2048,test_locked=True))
    print('Selection frozen; no further training',flush=True)


class ZeroSpeed:
    def __init__(self,agent):self.agent=agent
    def act(self,obs):return self.agent.act(obs,zero_speed=True)


class ControlMonitor:
    def __init__(self,agent,schedule):
        self.agent,self.schedule=agent,schedule;self.corrections=[];self.clips=[]
    def act(self,obs):
        import numpy as np
        from ..utils.reference_schedule import speed_numpy
        a=self.agent.act(obs)
        self.corrections.extend((a[:,2]-speed_numpy(obs,self.schedule))*.667/2)
        self.clips.extend(np.abs(a[:,2])>=1-1e-6)
        return a
    def summary(self):
        import numpy as np
        x=np.asarray(self.corrections)
        return dict(speed_correction_rms_rad_s=float(np.sqrt(np.mean(x*x))),speed_correction_max_rad_s=float(np.abs(x).max()),speed_total_clip_fraction=float(np.mean(self.clips)))


def test(root):
    import numpy as np
    from . import random_wind_training as shared
    from .frozen_speed_algorithm import load_policy
    saved,p=context(root);selection=read_json(root/'selection.json');verify_hashes(selection['hashes'])
    if selection['root_config_sha256']!=sha(root/'config.yaml') or selection['bank_sha256']!=sha(root/'bank/manifest.json'):raise ValueError('frozen identities changed')
    if not (root/'core_verification.json').exists() or read_json(root/'core_verification.json')['selection_sha256']!=sha(root/'selection.json'):raise ValueError('checkpoint audit must precede held-out test')
    out=root/'test'
    release=dict(selection_sha256=sha(root/'selection.json'),bank_sha256=sha(root/'bank/manifest.json'),root_config_sha256=sha(root/'config.yaml'))
    if out.exists():
        if read_json(out/'release.json')!=release:raise ValueError('existing test release identity differs')
    else:
        out.mkdir();write_json(out/'release.json',release)
    if (out/'complete.json').exists():
        verify_hashes({str(out/k):v for k,v in read_json(out/'complete.json').items()});return
    def completed_or_next(name):
        folder=out/name;folder.mkdir(exist_ok=True)
        for attempt in sorted(folder.glob('attempt_*')):
            if (attempt/'complete.json').exists():
                rows,capture=load_job(attempt)
                summary=read_json(attempt/'corrections.json') if (attempt/'corrections.json').exists() else None
                return attempt,(rows,capture,summary)
        index=max((int(p.name.split('_')[1]) for p in folder.glob('attempt_*')),default=-1)+1
        return folder/f'attempt_{index:03d}',None
    bank=shared.cases(root,'test',allow_test=True);metrics=[];traces=[];corrections=[]
    for r in selection['results']:
        choices=[('initial',r['initial']),('selected',r['selected']),('final',r['final']),('parent',r['parent']['checkpoint'])]
        if r['arm']=='speed':choices += [('zero_selected',r['selected']),('zero_final',r['final'])]
        for label,path in choices:
            folder,existing=completed_or_next(f"{r['arm']}_{r['run_id']}_{label}")
            if existing is None:
                agent,_=load_policy(path)
                schedule=agent.config.speed_schedule if hasattr(agent.config,'speed_schedule') else agent.config.speed_reference_schedule
                if label.startswith('zero_'):agent=ZeroSpeed(agent)
                monitor=ControlMonitor(agent,schedule)
                rows,capture,_=rollout(r['config'],bank,agent=monitor)
                stats=monitor.summary();save_job(folder,rows,capture,stats)
            else:rows,capture,stats=existing
            tags=dict(arm=r['arm'],run_id=r['run_id'],controller=label)
            corrections.append(dict(**tags,**stats))
            metrics.extend(dict(**tags,**row) for row in rows);traces.extend(dict(**tags,**row) for row in capture)
            print('Independent test',r['arm'],r['run_id'],label,flush=True)
    cfg=next(r['config'] for r in selection['results'] if r['arm']=='speed')
    for mode in ('fixed','p','pi'):
        folder,existing=completed_or_next(f'common_{mode}')
        if existing is None:
            rows,capture,_=rollout(cfg,bank,mode=mode);save_job(folder,rows,capture)
        else:rows,capture,_=existing
        tags=dict(arm='common',run_id=-1,controller=mode)
        metrics.extend(dict(**tags,**row) for row in rows);traces.extend(dict(**tags,**row) for row in capture)
    check=recompute(metrics,traces,('arm','run_id','controller','case_id'))
    assert check['metric_rows']==660 and check['trace_rows']==84480
    write_csv(out/'metrics.csv',metrics);write_csv(out/'trajectories.csv',traces)
    write_csv(out/'corrections.csv',corrections)
    write_json(out/'verification.json',check)
    write_json(out/'complete.json',{name:sha(out/name) for name in ('release.json','metrics.csv','trajectories.csv','corrections.csv','verification.json')})
    context(root)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=('prepare','gate','smoke','worker','run','test','verify','figures'))
    ap.add_argument('--output',required=True);ap.add_argument('--protocol',default=str(DEFAULT));ap.add_argument('--arm',choices=('baseline','speed'),default='baseline');ap.add_argument('--run-id',type=int,default=0)
    ap.add_argument('--stop-after',type=int)
    args=ap.parse_args();p=protocol(args.protocol)
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path(p['origin'])/'.venv/pinn_tf216')
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    root=Path(args.output).resolve()
    if args.command=='prepare':prepare(root,p)
    elif args.command=='gate':gate(root)
    elif args.command=='smoke':smoke(root)
    elif args.command=='worker':train(root,args.arm,args.run_id,stop_after=args.stop_after)
    elif args.command=='run':run(root)
    elif args.command=='test':test(root)
    elif args.command=='verify':
        from .frozen_speed_verify import verify
        verify(root)
    elif args.command=='figures':
        from .frozen_speed_figures import figures
        figures(root)


if __name__=='__main__':main()
