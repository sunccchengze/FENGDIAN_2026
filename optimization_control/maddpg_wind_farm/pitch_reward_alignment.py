"""Frozen train/validation reward audit; no optimizer calls or independent test access."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path

from .fixed_pinn_demo import activate_runtime, digest
from .pitch_cross_wind_diagnostic import ORIGINAL, read_csv, write_csv, write_json
from .pitch_nstep_trial import read_json, verify, bank, attempt_dir, compressed_csv

HERE = Path(__file__).parent
EXPERIMENTS = HERE.parent / 'experiments'
ACTION = EXPERIMENTS / '20261028_pitch_action_diagnostic'
TRIAL = EXPERIMENTS / '20261028_pitch_nstep'
MECHANISM = EXPERIMENTS / '20261028_pitch_nstep_mechanism'
FARM_RATING = 15e6
GAMMA = .99
SCALE = 100.
LAMBDA = .001
HORIZON = 128


def gz_rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def summarize(error, cost, command, before, actual, rate, *, reward=None, tracking=None, action=None):
    """One complete episode, t=0 command paired with t=1 response and reward."""
    import numpy as np
    error, cost = np.asarray(error, dtype=float), np.asarray(cost, dtype=float)
    command, before, actual = (np.asarray(a, dtype=float) for a in (command, before, actual))
    if error.shape != (HORIZON,) or cost.shape != (HORIZON,):
        raise ValueError('only complete 128-step trajectories may be ranked')
    if any(a.shape != (HORIZON, 3) for a in (command, before, actual)):
        raise ValueError('pitch shape mismatch')
    if not all(np.isfinite(a).all() for a in (error, cost, command, before, actual)) or cost.min() < 0:
        raise ValueError('nonfinite or negative native command-change cost')
    tracking_calc = -SCALE * (error / FARM_RATING)**2
    action_calc = -SCALE * LAMBDA * cost
    tracking = tracking_calc if tracking is None else np.asarray(tracking, dtype=float)
    action = action_calc if action is None else np.asarray(action, dtype=float)
    reward = tracking + action if reward is None else np.asarray(reward, dtype=float)
    residual = max(float(np.max(np.abs(tracking-tracking_calc))),
                   float(np.max(np.abs(action-action_calc))),
                   float(np.max(np.abs(reward-tracking-action))))
    if residual > 5e-6:
        raise ValueError(f'native reward formula mismatch: {residual}')
    discount = GAMMA**np.arange(HORIZON)
    delta = actual - before
    previous_command = np.vstack((before[0], command[:-1]))
    pitch_cost = np.sum(((command-previous_command)/.11)**2, axis=1)/9
    # Native cost is float32 while the decoded command is SI float64.
    background = cost - pitch_cost
    if background.min() < -1e-6:
        raise ValueError('pitch-only contribution exceeds native nine-channel cost')
    data = dict(rmse_w=float(np.sqrt(np.mean(error**2))), mse_w2=float(np.mean(error**2)),
                mae_w=float(np.mean(np.abs(error))), mean_error_w=float(error.mean()),
                error_std_w=float(error.std()), tracking_uniform=float(tracking.sum()),
                tracking_discounted=float(discount @ tracking), action_uniform=float(action.sum()),
                action_discounted=float(discount @ action), return_uniform=float((tracking+action).sum()),
                return_discounted=float(discount @ (tracking+action)), native_discounted=float(discount @ reward),
                native_residual_max=residual, command_cost_sum=float(cost.sum()),
                pitch_command_cost_sum=float(pitch_cost.sum()), background_command_cost_sum=float(background.sum()),
                pitch_travel_rad=float(np.abs(delta).sum()), pitch_rms_rate_rad_s=float(np.sqrt(np.mean(delta**2))),
                pitch_rate_fraction=float(np.mean(rate)), pitch_max_rate_rad_s=float(np.abs(delta).max()),
                pitch_min_rad=float(actual.min()), pitch_max_rad=float(actual.max()), steps=HORIZON)
    if abs(data['mse_w2']-data['mean_error_w']**2-data['error_std_w']**2) > .001:
        raise ValueError('error decomposition failed')
    identity = hashlib.sha256()
    for array in (error, cost, command, actual):
        identity.update(array.astype('<f8').tobytes())
    data['trajectory_sha256'] = identity.hexdigest()
    return data


def summarize_rows(rows):
    import numpy as np
    if [int(r['decision_step']) for r in rows] != list(range(HORIZON)):
        raise ValueError('decision timing is not 0..127')
    if [int(r['response_step']) for r in rows] != list(range(1, HORIZON+1)):
        raise ValueError('response timing is not 1..128')
    arrays = {name: np.array([[float(r[f'{name}_{i}']) for i in range(3)] for r in rows])
              for name in ('pitch_command', 'pitch_before', 'pitch_actual')}
    return summarize([float(r['error_w']) for r in rows], [float(r['action_change']) for r in rows],
                     arrays['pitch_command'], arrays['pitch_before'], arrays['pitch_actual'],
                     [float(r['pitch_rate_fraction']) for r in rows],
                     reward=[float(r['reward']) for r in rows], tracking=[float(r['tracking_reward']) for r in rows],
                     action=[float(r['action_reward']) for r in rows])


def latest_commits(n, run):
    commits = {}
    for p in sorted((TRIAL/f'n{n}_run{run}').glob('step_*/attempt_*/commit.json')):
        step = int(read_json(p)['step'])
        commits[step] = p
    if sorted(commits) != list(range(0, 16385, 128)):
        raise ValueError('incomplete immutable training source')
    return commits


def prepare(root):
    import yaml
    root = Path(root).resolve()
    if root.exists():
        raise FileExistsError('use existing frozen audit or a new dated experiment; never overwrite preparation')
    root.mkdir(parents=True)
    protected = {}

    def pin(p, expected=None):
        p = Path(p).resolve(); h = digest(p)
        if expected is not None and h != expected:
            raise ValueError(f'source digest mismatch: {p}')
        protected[str(p)] = h

    selection = read_json(TRIAL/'selection.json')
    pin(TRIAL/'config.yaml', selection['config_sha256']); pin(TRIAL/'selection.json')
    old = yaml.safe_load((TRIAL/'config.yaml').read_text(encoding='utf-8'))
    cfg = old['base_config']
    e = cfg['environment']
    assert e['horizon'] == HORIZON and e['dt_s'] == 1. and e['action_change_weight'] == LAMBDA and e['reward_scale'] == SCALE
    assert cfg['algorithm']['gamma'] == GAMMA and cfg['plant']['rated_power_w'] == [5000000]*3
    pin(Path(cfg['plant']['backend']['run_dir'])/'trained.keras', cfg['plant']['backend']['model_sha256'])
    pin(ACTION/'jobs.json'); pin(TRIAL/'training_manifest.csv')
    for p in (TRIAL/'validation_bank').glob('*'):
        if p.is_file():
            pin(p)
    for job in read_json(ACTION/'jobs.json'):
        for name in ('full_trajectories.csv.gz',):
            pin(Path(job['path'])/name, job['hashes'][name])
    for result in selection['results']:
        for p,h in result['hashes'].items():
            pin(p,h)
        commits = latest_commits(result['n'],result['run'])
        for step,p in commits.items():
            pin(p); saved = read_json(p)
            names = ['training.npz'] if step else []
            if step % 4096 == 0:
                names += ['validation_traces.csv.gz','validation_metrics.csv']
            for name in names:
                q = p.with_name(name); pin(q,saved['hashes'][str(q.resolve())])
    for p in (MECHANISM/'jobs').glob('run*_case*/attempt_*/complete.json'):
        pin(p); saved=read_json(p)
        for name in ('branches.csv.gz','own_policy.csv'):
            q=p.with_name(name); pin(q,saved['hashes'][str(q.resolve())])
    for p in [HERE/'PITCH_REWARD_ALIGNMENT_PROTOCOL.md',HERE/'pitch_reward_alignment.py',HERE/'pitch_reward_alignment_review.py',
              HERE/'pitch_action_diagnostic.py',HERE/'pitch_nstep_mechanism.py',HERE/'pitch_nstep_trial.py',
              HERE/'nstep_algorithm.py',HERE/'algorithm.py',HERE/'workflow.py',
              HERE.parent/'environments/maddpg_farm_env.py']:
        pin(p)
    frozen=dict(seed=42,kind='full_episode_reward_alignment_v1',formal_training_steps=0,
                evaluation_limit=10000, expected_new_environment_steps=6912, prefix_steps=96, reused_tail_steps=32,
                gamma=GAMMA,reward_scale=SCALE,action_change_weight=LAMBDA,farm_rating_w=FARM_RATING,
                pair_rmse_tie_w=100.,return_tie=1e-6,native_reward_tolerance=5e-6,
                replay_power_tolerance_w=20.,replay_normalized_pitch_tolerance=1e-5,
                base_config=cfg, protected_hashes=protected,
                sources=dict(action=str(ACTION.resolve()),nstep=str(TRIAL.resolve()),mechanism=str(MECHANISM.resolve())),
                test_data_read=False,selection='unchanged frozen roles; no new checkpoint selection',
                source_commit='63db394257481c7c04c86803cd8bff38f733db93')
    (root/'config.yaml').write_text(yaml.safe_dump(frozen,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    write_json(root/'summary.txt',dict(status='prepared',formal_training_steps=0,expected_environment_steps=6912))
    print(json.dumps(dict(prepared=str(root),pinned_files=len(protected),formal_training_steps=0)),flush=True)


def charge(root, label):
    ledger=root/'evaluation_budget.jsonl'
    old=[json.loads(s) for s in ledger.read_text(encoding='utf-8').splitlines()] if ledger.exists() else []
    total=sum(r['reserved_steps'] for r in old)+96
    if total>10000:
        raise ValueError('hard cap includes interrupted reservations')
    with ledger.open('a',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps(dict(label=label,reserved_steps=96,cumulative_reserved=total))+'\n')


def supplement(root):
    import yaml
    import numpy as np
    from .workflow import build_env
    from .pitch_nstep_mechanism import role_agents, actor_hash, parameter_hash, original_validation
    from .pitch_action_diagnostic import reset_case, trace_row
    root=Path(root).resolve(); cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify(cfg['protected_hashes'])
    if (root/'supplement.json').exists():
        verify(read_json(root/'supplement.json')['hashes']); print('supplement already frozen'); return
    cases=[(c,w) for c,w in bank(TRIAL,'validation') if c['initial_pitch_rad']==.04]
    assert len(cases)==6
    env=build_env(cfg['base_config']); selection=read_json(TRIAL/'selection.json'); completed=[]
    for run in range(3):
        roles,paths=role_agents(run,selection)
        before={k:parameter_hash(v) for k,v in roles.items()}
        for ci,(case,wind) in enumerate(cases):
            base=root/'supplement'/f'run{run}_case{ci}'
            done=sorted(base.glob('attempt_*/complete.json'))
            if done:
                verify(read_json(done[-1])['hashes']); completed.append(read_json(done[-1])); continue
            out=attempt_dir(base)
            oldbase=sorted((MECHANISM/'jobs'/f'run{run}_case{ci}').glob('attempt_*/complete.json'))[-1].parent
            own=read_csv(oldbase/'own_policy.csv'); branches=gz_rows(oldbase/'branches.csv.gz')
            cache={}; data=[]; mapping=[]; max_error=max_command=0.
            for role,agent in roles.items():
                ah=actor_hash(agent)
                if ah not in cache:
                    charge(root,f'run{run}:{case["id"]}:{role}')
                    obs,info=reset_case(env,case,wind); rows=[]
                    for t in range(96):
                        action=agent.act(obs); nxt,reward,done,truncated,after=env.step(action)
                        assert not done and not truncated
                        rows.append(trace_row(env,info,action,dict(id='zero'),after,reward,t+1))
                        obs,info=nxt,after
                    ownrow=next(r for r in own if r['role']==role and r['anchor']=='96' and r['variant']=='zero' and r['horizon']=='32')
                    tail=[r for r in branches if r['branch_id']==ownrow['branch_id']]
                    assert len(tail)==32
                    rows += [{k:v for k,v in r.items() if k not in ('branch_id','anchor')} for r in tail]
                    for t,row in enumerate(rows):
                        row['h']=t+1
                    cache[ah]=rows
                    data += [dict(actor_sha256=ah,**r) for r in rows]
                _,old=original_validation(paths[role],case['id'])
                rows=cache[ah]
                for a,b in zip(rows,old):
                    max_error=max(max_error,abs(float(a['error_w'])-float(b['error_w'])))
                    max_command=max(max_command,max(abs(float(a[f'pitch_command_{i}'])-float(b[f'pitch_command_{i}']))/.11 for i in range(3)))
                if max_error>20. or max_command>1e-5:
                    raise ValueError(f'old full validation mismatch: {max_error}, {max_command}')
                summarize_rows(rows)
                mapping.append(dict(run=run,case_id=case['id'],family=case['family'],split='validation',
                               target_w=case['target_w'],initial_pitch_rad=.04,role=role,actor_sha256=ah,checkpoint=paths[role]))
            compressed_csv(out/'full_trajectories.csv.gz',data); write_csv(out/'roles.csv',mapping)
            complete=dict(run=run,case_id=case['id'],unique_actors=len(cache),roles=len(mapping),
                          actual_environment_steps=len(cache)*96,reused_tail_steps=len(cache)*32,
                          max_power_difference_w=max_error,max_normalized_pitch_difference=max_command,
                          hashes={str(p.resolve()):digest(p) for p in out.iterdir() if p.is_file()})
            write_json(out/'complete.json',complete); completed.append(complete)
            print(json.dumps({k:v for k,v in complete.items() if k!='hashes'}),flush=True)
        assert before=={k:parameter_hash(v) for k,v in roles.items()}
    verify(cfg['protected_hashes'])
    write_json(root/'supplement.json',dict(jobs=completed,actual_environment_steps=sum(c['actual_environment_steps'] for c in completed),
               hashes={p:h for c in completed for p,h in c['hashes'].items()},parameters_unchanged=True,formal_training_steps=0))


def tracking_metrics(rows):
    import numpy as np
    if len(rows)!=128 or [int(r['response_step']) for r in rows]!=list(range(1,129)):
        raise ValueError('incomplete validation tracking episode')
    error=np.array([float(r['error_w']) for r in rows]); d=GAMMA**np.arange(128)
    t=-SCALE*(error/FARM_RATING)**2
    command=np.array([[float(r[f'pitch_command_{i}']) for i in range(3)] for r in rows])
    actual=np.array([[float(r[f'pitch_actual_{i}']) for i in range(3)] for r in rows])
    before=np.array([[float(r[f'pitch_before_{i}']) for i in range(3)] for r in rows])
    sha=hashlib.sha256(b''.join(a.astype('<f8').tobytes() for a in (error,command,actual))).hexdigest()
    return dict(rmse_w=float(np.sqrt(np.mean(error**2))),mse_w2=float(np.mean(error**2)),mae_w=float(np.abs(error).mean()),
                mean_error_w=float(error.mean()),error_std_w=float(error.std()),tracking_uniform=float(t.sum()),
                tracking_discounted=float(d@t),trajectory_sha256=sha,steps=128,
                pitch_travel_rad=float(np.abs(actual-before).sum()),pitch_rms_rate_rad_s=float(np.sqrt(np.mean((actual-before)**2))),
                pitch_rate_fraction=float(np.mean([[int(r[f'pitch_rate_limited_{i}']) for i in range(3)] for r in rows])))


def collect(root):
    import yaml
    import numpy as np
    root=Path(root).resolve(); cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify(cfg['protected_hashes']); verify(read_json(root/'supplement.json')['hashes'])
    metrics=[]; roles=[]; seen={}

    def add(identity,label,m):
        key=(identity['source'],identity['run'],identity['case_id'],m['trajectory_sha256'])
        if key not in seen:
            uid=f't{len(metrics):05d}'; seen[key]=uid
            metrics.append(dict(trajectory_id=uid,**identity,representative=label,**m))
        roles.append(dict(trajectory_id=seen[key],**identity,role=label))

    for job in read_json(ACTION/'jobs.json'):
        groups=defaultdict(list)
        for r in gz_rows(Path(job['path'])/'full_trajectories.csv.gz'):
            groups[r['variant']].append(r)
        assert len(groups)==17
        for label,rows in groups.items():
            a=rows[0]
            identity=dict(source='action_full',run=job['run_id'],case_id=job['case_id'],split=a['split'],family=a['family'],
                          target_w=float(a['target_w']),initial_pitch_rad=float(a['initial_pitch_rad']))
            add(identity,label,summarize_rows(rows))
    print('collected action_full',flush=True)
    designs={(int(r['run']),int(r['episode_index'])):r for r in read_csv(TRIAL/'training_manifest.csv')}
    for n in (1,8):
        for run in range(3):
            for step,p in latest_commits(n,run).items():
                if step==0:
                    continue
                ep=step//128-1; design=designs[run,ep]
                with np.load(p.with_name('training.npz'),allow_pickle=False) as a:
                    assert a['obs'].shape==(128,3,15) and a['actions'].shape==(128,3,3)
                    assert a['terminated'][:,0].tolist()==[False]*127+[True]
                    assert np.array_equal(a['next_obs'][:-1],a['obs'][1:])
                    assert np.array_equal(a['actions'][:-1],a['obs'][1:,:,5:8])
                    assert np.max(np.abs(a['next_obs'][:,0,9]*FARM_RATING-a['error_w']))<1.
                    native_cost=np.mean((a['actions']-a['obs'][:,:,5:8])**2,axis=(1,2))
                    command=(a['actions'][:,:,1].astype(float)+1)*.11
                    actual=a['applied'][:,:,1]; before=np.vstack((np.full((1,3),float(design['initial_pitch_rad'])),actual[:-1]))
                    rate=np.mean(np.abs((1-np.exp(-.5))*(command-before))>cfg['base_config']['environment']['rate_limits'][1],axis=1)
                    m=summarize(a['error_w'],native_cost,command,before,actual,rate,reward=a['rewards'][:,0])
                identity=dict(source='nstep_training',run=run,case_id=f'train_episode_{ep}',split='train',family=design['family'],
                              target_w=float(design['target_w']),initial_pitch_rad=float(design['initial_pitch_rad']))
                add(identity,f'n{n}_behavior',m)
    print('collected nstep_training',flush=True)
    for n in (1,8):
        for run in range(3):
            for step,p in latest_commits(n,run).items():
                if step%4096:
                    continue
                groups=defaultdict(list)
                for r in gz_rows(p.with_name('validation_traces.csv.gz')):
                    groups[r['case_id']].append(r)
                assert len(groups)==18
                for case_id,rows in groups.items():
                    a=rows[0]
                    identity=dict(source='nstep_validation_tracking',run=run,case_id=case_id,split='validation',family=a['family'],
                                  target_w=float(a['target_w']),initial_pitch_rad=float(a['initial_pitch_rad']))
                    add(identity,f'n{n}_step{step}',tracking_metrics(rows))
    for job in read_json(root/'supplement.json')['jobs']:
        path=Path(next(iter(job['hashes']))).parent
        groups=defaultdict(list)
        for r in gz_rows(path/'full_trajectories.csv.gz'):
            groups[r['actor_sha256']].append(r)
        for a in read_csv(path/'roles.csv'):
            identity=dict(source='nstep_validation_reward',run=int(a['run']),case_id=a['case_id'],split='validation',family=a['family'],
                          target_w=float(a['target_w']),initial_pitch_rad=float(a['initial_pitch_rad']))
            add(identity,a['role'],summarize_rows(groups[a['actor_sha256']]))
    write_csv(root/'trajectory_metrics.csv',metrics); write_csv(root/'trajectory_roles.csv',roles)
    verify(cfg['protected_hashes'])
    write_json(root/'collection.json',dict(unique_trajectories=len(metrics),semantic_trajectories=len(roles),
               files={str((root/name).resolve()):digest(root/name) for name in ('trajectory_metrics.csv','trajectory_roles.csv')},
               formal_training_steps=0))
    print(json.dumps(read_json(root/'collection.json')),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('prepare','supplement','collect')); p.add_argument('--output',required=True)
    args=p.parse_args()
    activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    globals()[args.command](args.output)


if __name__=='__main__':
    main()
