"""Audit v4 parent preservation, paired budgets, exact recovery and held-out data."""
from copy import deepcopy
import io
from pathlib import Path

from .frozen_speed_training import context, initial, set_scale, action, episode, scale
from .anchor_closeout import read_json, read_csv, write_json, write_csv, sha, verify_hashes, recompute, rollout, make_env
from .verify_anchor import comparable


def forks(root,path,result=None):
    import numpy as np
    import torch
    from .frozen_speed_algorithm import load_policy
    from .stable_workflow import Exploration
    from .benchmark import seed_for
    saved,p=context(root);outputs=[]
    for _ in range(2):
        agent,meta=load_policy(path);arm=meta['arm'];run=meta['run_id'];smoke=meta['smoke'];step=meta['step']
        noise=Exploration(seed_for(42,p['smoke_noise_namespace'] if smoke else p['noise_namespace'],run),[0,0,.15] if arm=='speed' else [0,.03,0],[10,3,5],1.,'white',.2)
        noise.load_state_dict(meta['noise'])
        env=make_env(meta['config']);wind,target,pitch=episode(root,p,run,meta['episode'],smoke)
        env.initial=__import__('numpy').asarray(meta['config']['environment']['initial_operating_point'],float).copy();env.initial[1]=pitch
        obs,_=env.reset(seed=42,options=dict(wind_trajectory=wind.values,target_w=target));noise.reset();actions=[];rewards=[];losses=[]
        for _ in range(128):
            set_scale(agent,step);a=action(agent,arm,obs,noise.sample(step/8192))
            nxt,r,done,_,info=env.step(a);agent.replay.add(obs,info['executed_action'],r,nxt,done);step+=1
            if step>=512 and step%2==0:losses.append(agent.update())
            actions.append(info['executed_action']);rewards.append(r);obs=nxt
        outputs.append((agent,np.asarray(actions),np.asarray(rewards),losses,noise.state_dict()))
    a,b=outputs
    np.testing.assert_array_equal(a[1],b[1]);np.testing.assert_array_equal(a[2],b[2]);assert a[3]==b[3]
    np.testing.assert_equal(a[4],b[4])
    kinds=['actors','target_actors','critics','target_critics']+(['speed_heads','target_speed_heads'] if hasattr(a[0],'speed_heads') else [])
    for k in kinds:np.testing.assert_equal(comparable(getattr(a[0],k).state_dict()),comparable(getattr(b[0],k).state_dict()))
    if result is not None:
        final,_=load_policy(result['final']);n=final.replay.size
        order=(np.arange(n)+final.replay.position)%final.replay.capacity if n==final.replay.capacity else np.arange(n)
        new=order[-result['steps']:]
        np.testing.assert_array_equal(a[1],final.replay.data['actions'][new[2048:2176]])
    return dict(source=str(path),forks=2,environment_steps=256,exact_actions_rewards_losses_noise_networks=True,actual_resumed_actions_match=result is not None,discarded=True,formal_steps_added=0)


def roundtrip(path):
    import numpy as np
    from .frozen_speed_algorithm import load_policy
    a,meta=load_policy(path);buf=io.BytesIO();a.save(buf,meta);buf.seek(0)
    b,bmeta=load_policy(buf);np.testing.assert_equal(meta,bmeta)
    np.testing.assert_array_equal(a.act(a.replay.data['obs'][0]),b.act(b.replay.data['obs'][0]));assert a.update()==b.update()
    kinds=['actors','target_actors','critics','target_critics']+(['speed_heads','target_speed_heads'] if hasattr(a,'speed_heads') else [])
    for k in kinds:np.testing.assert_equal(comparable(getattr(a,k).state_dict()),comparable(getattr(b,k).state_dict()))
    opts=['critic_optimizers']+(['head_optimizers'] if hasattr(a,'speed_heads') else ['actor_optimizers'])
    for k in opts:
        for x,y in zip(getattr(a,k),getattr(b,k)):np.testing.assert_equal(comparable(x.state_dict()),comparable(y.state_dict()))
    np.testing.assert_equal(a.replay.state_dict(),b.replay.state_dict())


def verify_smoke(root):
    import numpy as np
    import torch
    saved,p=context(root);records=[]
    for arm in ('baseline','speed'):
        r=read_json(root/f'smoke/{arm}_run_0/result.json');verify_hashes(r['hashes'])
        a=torch.load(r['initial'],weights_only=False,map_location='cpu');b=torch.load(r['final'],weights_only=False,map_location='cpu')
        assert r['steps']==1024 and b['updates']-a['updates']==257
        if arm=='speed':
            np.testing.assert_equal(comparable(a['actors']),comparable(b['actors']))
            assert any(not torch.equal(v,b['speed_heads'][k]) for k,v in a['speed_heads'].items())
        roundtrip(r['final']);records.append(dict(arm=arm,steps=1024,updates_added=257,restore_next_update_exact=True))
    recovery=forks(root,read_json(root/'smoke/speed_run_0/result.json')['final'])
    write_json(root/'smoke/verification.json',dict(seed=42,passed=True,training_steps=2048,not_inherited_by_formal=True,checks=records,recovery=recovery,root_config_sha256=sha(root/'config.yaml')))
    write_json(root/'summary.txt',dict(status='smoke_passed',seed=42,formal_training_steps=0,smoke_training_steps=2048))
    context(root);print('Smoke verified',flush=True)


def core_audit(root):
    import numpy as np
    import torch
    from .frozen_speed_algorithm import load_policy
    saved,p=context(root);sel=read_json(root/'selection.json');verify_hashes(sel['hashes'])
    checks=[];histories=[];paired=[]
    for run in range(3):
        left=next(r for r in sel['results'] if r['arm']=='baseline' and r['run_id']==run)
        right=next(r for r in sel['results'] if r['arm']=='speed' and r['run_id']==run)
        a=torch.load(left['initial'],weights_only=False,map_location='cpu');b=torch.load(right['initial'],weights_only=False,map_location='cpu')
        for k in ('actors','target_actors','critics','target_critics','critic_optimizers','replay','rng','torch_rng','updates'):
            np.testing.assert_equal(comparable(a[k]),comparable(b[k]))
        np.testing.assert_equal(a['metadata']['noise']['rng'],b['metadata']['noise']['rng'])
        assert all(not o['state'] for o in a['actor_optimizers']) and all(not o['state'] for o in b['head_optimizers'])
        parent=torch.load(saved['parents'][run]['checkpoint'],weights_only=False,map_location='cpu')
        for k in ('actors','target_actors','critics','target_critics','critic_optimizers','replay','rng','torch_rng','updates'):
            np.testing.assert_equal(comparable(a[k]),comparable(parent[k]))
        paired.append(dict(run_id=run,common_parent_networks_critics_optimizers_replay_rng_exact=True,trainable_actor_moments_empty=True))
    for r in sel['results']:
        for path in (r['initial'],r['selected'],r['final']):roundtrip(path)
        agent,meta=load_policy(r['final']);first=torch.load(r['initial'],weights_only=False,map_location='cpu')
        data=agent.replay.state_dict()['data'];n=len(data['obs'])
        np.testing.assert_array_equal(data['actions'],data['next_obs'][:,:,5:8]);assert agent.updates-first['updates']==3841
        e=r['config']['environment'];width=np.asarray(e['action_high'])-e['action_low']
        gamma=(data['obs'][:,:,2]+1)*width[0]/2+e['action_low'][0];ngamma=(data['next_obs'][:,:,2]+1)*width[0]/2+e['action_low'][0]
        theta=np.arctan2(data['obs'][:,0,11],data['obs'][:,0,12]);ntheta=np.arctan2(data['next_obs'][:,0,11],data['next_obs'][:,0,12])
        heading=(ngamma-gamma+(ntheta-theta)[:,None]+np.pi)%(2*np.pi)-np.pi
        delta=np.concatenate((heading[...,None],(data['next_obs'][:,:,3:5]-data['obs'][:,:,3:5])*width[1:]/2),axis=-1)
        assert np.all(np.abs(delta).max(axis=(0,1))<=np.asarray(e['rate_limits'])+1e-6)
        reward=e['reward_scale']*(-data['next_obs'][:,0,9]**2-e['action_change_weight']*np.mean((data['actions']-data['obs'][:,:,5:8])**2,axis=(1,2)))
        np.testing.assert_allclose(data['rewards'],np.repeat(reward[:,None],3,axis=1),atol=5e-6,rtol=4e-6)
        order=(np.arange(n)+agent.replay.position)%agent.replay.capacity if n==agent.replay.capacity else np.arange(n)
        new=order[-8192:];obs=data['obs'][new]
        np.testing.assert_array_equal(data['terminated'][new,0],(obs[:,0,14]<=1/128+1e-7).astype(np.float32))
        from ..utils.reference_schedule import speed_numpy
        schedule=agent.config.speed_schedule if r['arm']=='speed' else agent.config.speed_reference_schedule
        baseline=speed_numpy(obs,schedule);correction=np.abs(data['actions'][new,:,2]-baseline)
        if r['arm']=='baseline':assert correction.max()==0
        else:
            assert np.all(correction<=np.asarray([scale(s) for s in range(8192)])[:,None]+1e-6)
            np.testing.assert_equal(comparable(first['actors']),comparable(agent.actors.state_dict()))
            assert all(not param.requires_grad and param.grad is None for param in agent.actors.parameters())
            expected=deepcopy(first['target_actors'])
            for _ in range(3841):
                for k,v in expected.items():v.lerp_(first['actors'][k],agent.config.tau)
            np.testing.assert_equal(comparable(expected),comparable(agent.target_actors.state_dict()))
        histories.extend(dict(arm=r['arm'],run_id=r['run_id'],**row) for row in meta['history'])
        checks.append(dict(arm=r['arm'],run_id=r['run_id'],retained_transitions=n,new_steps=8192,updates_added=3841,replay_commands_rewards_termination_rates_envelope=True,frozen_parent_and_target_path=r['arm']=='speed'))
        print('Audit formal',r['arm'],r['run_id'],flush=True)
    recovery=[]
    for arm in ('baseline','speed'):
        resumed=next(r for r in sel['results'] if r['arm']==arm and r['run_id']==0)
        recovery.append(forks(root,root/f'formal/{arm}_run_0/segment_000/step_00002048.pth',resumed))
    # Reproduce the fixed 192 formal wind/target/pitch designs.
    preflight=read_csv(root/'training_wind_preflight.csv')
    for row in preflight:
        wind,target,pitch=episode(root,p,int(row['run_id']),int(row['episode']))
        import hashlib
        assert hashlib.sha256(wind.values.tobytes()).hexdigest()==row['values_sha256'] and target==float(row['target_w']) and pitch==float(row['initial_pitch_rad'])
    write_csv(root/'history.csv',histories)
    write_json(root/'core_verification.json',dict(seed=42,paired=paired,checks=checks,recovery=recovery,formal_steps=49152,smoke_steps=2048,retained_transitions=sum(r['retained_transitions'] for r in checks),training_wind_rows=len(preflight),selection_sha256=sha(root/'selection.json')))
    context(root)


def verify(root):
    import numpy as np
    saved,p=context(root);sel=read_json(root/'selection.json');verify_hashes(sel['hashes'])
    if not (root/'core_verification.json').exists():core_audit(root)
    assert read_json(root/'core_verification.json')['selection_sha256']==sha(root/'selection.json')
    if not (root/'test/metrics.csv').exists():return
    metrics,traces=read_csv(root/'test/metrics.csv'),read_csv(root/'test/trajectories.csv')
    check=recompute(metrics,traces,('arm','run_id','controller','case_id'));assert (check['metric_rows'],check['trace_rows'])==(660,84480)
    aggregates=[]
    for arm in ('baseline','speed','common'):
        for label in sorted(set(r['controller'] for r in metrics if r['arm']==arm)):
            for subset in ('routine','known_stress'):
                rows=[r for r in metrics if r['arm']==arm and r['controller']==label and ((r['family']=='low_wind_stress')==(subset=='known_stress'))]
                means=[np.mean([float(r['rmse_w']) for r in rows if r['run_id']==run]) for run in sorted(set(r['run_id'] for r in rows))]
                aggregates.append(dict(arm=arm,controller=label,subset=subset,mean_rmse_w=float(np.mean(means)),sd_w=float(np.std(means,ddof=1)) if len(means)>1 else 0.))
    # Zero speed must recover the frozen online parent on the full test bank.
    reference={(r['run_id'],r['case_id']):r for r in metrics if r['arm']=='speed' and r['controller']=='parent'}
    maximum_zero=0.
    for row in metrics:
        if row['controller'] in ('zero_selected','zero_final'):
            maximum_zero=max(maximum_zero,abs(float(row['rmse_w'])-float(reference[(row['run_id'],row['case_id'])]['rmse_w'])))
    assert maximum_zero==0
    max_relation=0.;max_sum=0.
    for row in traces:
        power=np.asarray([float(row[f'power_{i}_w']) for i in (1,2,3)],np.float32)
        max_sum=max(max_sum,abs(float(power.sum())-float(row['farm_power_w'])))
        for i in (1,2,3):
            expected=(float(row[f'heading_{i}_rad'])-float(row['direction_rad'])+np.pi)%(2*np.pi)-np.pi
            max_relation=max(max_relation,abs(expected-float(row[f'gamma_{i}'])))
            assert 0<=float(row[f'pitch_{i}'])<=.22+1e-6 and .6-1e-6<=float(row[f'speed_{i}'])<=1.267+1e-6
    assert max_relation<1e-6 and max_sum==0
    gain={}
    for label in ('selected','final'):
        speed=[next(r for r in sel['results'] if r['arm']=='speed' and r['run_id']==i)[label+'_mean_w'] for i in range(3)]
        baseline=[next(r for r in sel['results'] if r['arm']=='baseline' and r['run_id']==i)[label+'_mean_w'] for i in range(3)]
        gain[label]=dict(validation_paired_improvements=sum(a<b for a,b in zip(speed,baseline)),validation_mean_gain_fraction=1-float(np.mean(speed)/np.mean(baseline)),
            passed=bool(all(a<b for a,b in zip(speed,baseline)) and 1-np.mean(speed)/np.mean(baseline)>=.01))
    speed_results=[r for r in sel['results'] if r['arm']=='speed']
    stable=all(r['stable'] for r in speed_results)
    repeatable=all(bool(v['passed']) for v in gain.values()) and all(r['selected_learned'] for r in speed_results)
    check.update(max_zero_speed_rmse_difference_w=maximum_zero,max_heading_gamma_relation_error=max_relation,max_power_sum_error_w=max_sum)
    write_csv(root/'test/aggregate.csv',aggregates)
    write_json(root/'summary.txt',dict(seed=42,status='completed',formal_training_steps=49152,smoke_training_steps=2048,physical_validation=False,
        stability_pass=stable,repeatable_learning_gain_pass=repeatable,validation_gain=gain,results=sel['results'],test=check,aggregate=aggregates,verification=read_json(root/'core_verification.json'),test_used_for_selection=False))
    write_json(root/'verification.json',check);context(root)
    print('Full verification complete',check,'stability',stable,'gain',repeatable,flush=True)
