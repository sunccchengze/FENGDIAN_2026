"""Read-only saved train/validation audit. No plant, environment or optimizer steps."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parent / 'experiments'
SOURCE = EXPERIMENTS / '20261028_pitch_nstep'
MANIFEST = EXPERIMENTS / '20261028_pitch_nstep_mechanism/candidate_manifest.json'
ORIGINAL = Path('.')
ROLES = ('initial', 'selected', 'final')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def read_csv(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    if not rows:
        raise ValueError('empty audit output')
    with Path(path).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def eligible(row):
    return row['split'] in ('train', 'validation') and row['family'] != 'low_wind_stress'


def moments(errors):
    mean = statistics.fmean(errors)
    mse = statistics.fmean(x*x for x in errors)
    variance = statistics.fmean((x-mean)**2 for x in errors)
    return dict(rmse_w=math.sqrt(mse), mean_error_w=mean, error_std_w=math.sqrt(variance),
                mse_w2=mse, bias_squared_w2=mean*mean, variance_w2=variance)


def grouped(rows, keys):
    result = {}
    for row in rows:
        result.setdefault(tuple(row[k] for k in keys), []).append(row)
    return result


def wind_id(case):
    return case.split('_initial_')[0]


def sources():
    manifest = read_json(MANIFEST)
    selection = read_json(SOURCE/'selection.json')
    assert sha(SOURCE/'selection.json') == manifest['source_selection_sha256']
    assert sha(SOURCE/'config.yaml') == manifest['trial_config_sha256']
    items = [MANIFEST, SOURCE/'selection.json', SOURCE/'config.yaml', SOURCE/'training_manifest.csv',
             HERE/'algorithm.py', HERE/'nstep_algorithm.py', HERE/'pitch_nstep_trial.py',
             HERE.parent/'environments/maddpg_farm_env.py', HERE/'pitch_remaining_failure_audit.py',
             HERE/'PITCH_REMAINING_FAILURE_PROTOCOL.md']
    results = [r for r in selection['results'] if r['n'] == 8]
    for candidate, result in zip(manifest['candidates'], results):
        assert candidate['run'] == result['run']
        assert candidate['checkpoint'] == result['selected']
        assert sha(candidate['checkpoint']) == candidate['sha256']
        assert candidate['selected_by_test'] is False
        for role in ROLES:
            path = Path(result[role])
            assert sha(path) == result['hashes'][str(path)]
            items.append(path)
    for label in ['p', 'pi'] + [f'n8_run{r}_{st}' for r in range(3) for st in ROLES]:
        base = SOURCE/'evaluations/known'/label/'attempt_000'
        items.extend([base/'metrics.csv', base/'traces.csv.gz'])
    for run in range(3):
        for step in range(0, 16385, 4096):
            base = SOURCE/f'n8_run{run}'/f'step_{step:08d}'/'attempt_000'
            items.extend([base/'validation_metrics.csv', base/'validation_traces.csv.gz'])
        for base in sorted((SOURCE/f'n8_run{run}').glob('step_*/attempt_000')):
            if (base/'training.npz').is_file():
                items.extend([base/'training.npz', base/'losses.csv'])
    model = ORIGINAL/'optimization_control/experiments/20261022_wind_pinn_integration/model'
    items.extend([model/'trained.keras', model/'config_used.json', model/'training_report.json'])
    return manifest, results, {str(p.resolve()): sha(p) for p in sorted(set(items))}


def prepare(root):
    import yaml
    root.mkdir(parents=True, exist_ok=False)
    manifest, results, hashes = sources()
    config = dict(seed=42, version='pitch_remaining_failures_v1', source_commit='eef2a131e66e23b051bd1d148867d5402caec5a4',
                  formal_rl_steps=0, optimizer_updates=0, model_forward_rows=0, environment_steps=0,
                  new_test_released=False, excluded_families=['low_wind_stress'],
                  excluded_sources=['test', 'test_bank', 'gamma_trial_policy_selection', 'speed_predictor'],
                  candidate_manifest=str(MANIFEST), candidates=manifest['candidates'],
                  selected_steps=[r['selected_step'] for r in results],
                  replay_probe=dict(points_per_state=1024, selection='chronological_linspace_including_endpoints',
                                    nearest_neighbors=32, distance='per_coordinate_replay_std_floor_1e-6',
                                    remove_query_self=True, rng_consumption=False),
                  windows=[[1,32],[33,64],[65,96],[97,128]],
                  wind_bins_m_s=[7.5,8.5,9.5,10.500001], protected_hashes=hashes)
    (root/'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8', newline='\n')
    write_json(root/'summary.txt', dict(status='prepared', seed=42, formal_rl_steps=0, model_forward_rows=0))
    write_csv(root/'metrics.csv', [dict(status='prepared', seed=42, formal_rl_steps=0)])
    print(json.dumps(dict(prepared=str(root), protected_inputs=len(hashes), selected_steps=config['selected_steps'])))


def check_sources(root):
    import yaml
    config = yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    for path, value in config['protected_hashes'].items():
        if sha(path) != value:
            raise ValueError(f'protected input changed: {path}')
    return config


def trajectory_audit(root):
    config = check_sources(root)
    all_data, metrics, excluded = {}, [], []
    max_residual = 0.
    for label in ['p', 'pi'] + [f'n8_run{r}_{st}' for r in range(3) for st in ROLES]:
        base = SOURCE/'evaluations/known'/label/'attempt_000'
        raw = read_csv(base/'metrics.csv')
        traces = grouped([r for r in read_csv(base/'traces.csv.gz') if eligible(r)], ['case_id'])
        all_data[label] = {k[0]: v for k, v in traces.items()}
        for row in raw:
            if not eligible(row):
                excluded.append(dict(label=label, case_id=row['case_id'], family=row['family'], reason='known_pressure_not_for_candidate'))
                continue
            ts = all_data[label][row['case_id']]
            assert len(ts) == 128 and [int(x['response_step']) for x in ts] == list(range(1,129))
            mm = moments([float(x['error_w']) for x in ts])
            for key, value in mm.items():
                max_residual = max(max_residual, abs(value-float(row[key])))
                assert math.isclose(value, float(row[key]), rel_tol=1e-12, abs_tol=.001)
            metrics.append(dict(label=label, run=-1 if label in ('p','pi') else int(label[6]),
                                role=label if label in ('p','pi') else label.split('_')[-1],
                                **{k:row[k] for k in ('case_id','split','family','target_w','initial_pitch_rad')}, **mm))
    pi = {r['case_id']: r for r in metrics if r['label'] == 'pi'}
    lookup = {(r['label'], r['case_id']): r for r in metrics}
    pairs, windows, wind_rows = [], [], []
    for row in metrics:
        if row['run'] < 0:
            continue
        case, label, role, run = row['case_id'], row['label'], row['role'], row['run']
        ts, ps = all_data[label][case], all_data['pi'][case]
        assert [(x['decision_wind_m_s'], x['response_wind_m_s'],x['target_w'],x['initial_pitch_rad']) for x in ts] == [
            (x['decision_wind_m_s'],x['response_wind_m_s'],x['target_w'],x['initial_pitch_rad']) for x in ps]
        e, pe = [float(x['error_w']) for x in ts], [float(x['error_w']) for x in ps]
        p = pi[case]
        parent = lookup[(f'n8_run{run}_initial',case)]
        selected = lookup[(f'n8_run{run}_selected',case)]
        winds = [float(x['response_wind_m_s']) for x in ts]
        b = dict(run=run,role=role,case_id=case,waveform=wind_id(case),split=row['split'],family=row['family'],
                 target_w=float(row['target_w']),initial_pitch_rad=float(row['initial_pitch_rad']))
        pairs.append(dict(**b, rmse_w=row['rmse_w'],pi_rmse_w=p['rmse_w'],delta_pi_rmse_w=row['rmse_w']-p['rmse_w'],
                          worse_pi=row['rmse_w']>p['rmse_w'],worse_pi_over_100w=row['rmse_w']-p['rmse_w']>100,
                          delta_parent_rmse_w=row['rmse_w']-parent['rmse_w'],
                          delta_selected_rmse_w=row['rmse_w']-selected['rmse_w'],
                          mean_error_w=row['mean_error_w'],pi_mean_error_w=p['mean_error_w'],
                          delta_pi_bias_squared_w2=row['bias_squared_w2']-p['bias_squared_w2'],
                          delta_pi_variance_w2=row['variance_w2']-p['variance_w2'],
                          delta_pi_mse_w2=row['mse_w2']-p['mse_w2'],
                          mean_wind_m_s=statistics.fmean(winds),min_wind_m_s=min(winds),max_wind_m_s=max(winds),
                          under_target_fraction=statistics.fmean(x<0 for x in e),
                          pitch_command_mean_rad=statistics.fmean(float(x[f'pitch_command_{i}']) for x in ts for i in range(3)),
                          pitch_actual_mean_rad=statistics.fmean(float(x[f'pitch_actual_{i}']) for x in ts for i in range(3)),
                          pitch_rate_limited_fraction=statistics.fmean(float(x[f'pitch_rate_limited_{i}']) for x in ts for i in range(3))))
        for start, stop in config['windows']:
            m, pm = moments(e[start-1:stop]), moments(pe[start-1:stop])
            windows.append(dict(**b,start=start,stop=stop,**m,pi_rmse_w=pm['rmse_w'],pi_mean_error_w=pm['mean_error_w'],
                                delta_pi_mse_w2=m['mse_w2']-pm['mse_w2']))
        bins = config['wind_bins_m_s']
        for lo, hi in zip(bins,bins[1:]):
            idx = [i for i,w in enumerate(winds) if lo <= w < hi]
            if idx:
                m, pm = moments([e[i] for i in idx]), moments([pe[i] for i in idx])
                wind_rows.append(dict(**b,wind_low=lo,wind_high=hi,steps=len(idx),**m,
                                      pi_rmse_w=pm['rmse_w'],pi_mean_error_w=pm['mean_error_w'],
                                      full_mse_delta_contribution_w2=(m['mse_w2']-pm['mse_w2'])*len(idx)/128))
    write_csv(root/'metrics.csv',metrics)
    write_csv(root/'paired_cases.csv',pairs)
    write_csv(root/'time_windows.csv',windows)
    write_csv(root/'wind_bins.csv',wind_rows)
    write_csv(root/'excluded_pressure_identity.csv',excluded)
    groups = []
    for field in ('run','split','family','target_w','initial_pitch_rad','waveform'):
        for (role,value), part in grouped(pairs,['role',field]).items():
            groups.append(dict(role=role,dimension=field,value=value,slots=len(part),
                               distinct_waveforms=len(set(x['waveform'] for x in part)),
                               worse_pi=sum(x['worse_pi'] for x in part),worse_pi_over_100w=sum(x['worse_pi_over_100w'] for x in part),
                               mean_delta_pi_rmse_w=statistics.fmean(x['delta_pi_rmse_w'] for x in part),
                               mean_delta_parent_rmse_w=statistics.fmean(x['delta_parent_rmse_w'] for x in part),
                               mean_rmse_w=statistics.fmean(x['rmse_w'] for x in part)))
    write_csv(root/'groups.csv',groups)
    recurrence=[]
    for (case,), part in grouped([p for p in pairs if p['role']=='selected'],['case_id']).items():
        assert len(part)==3
        recurrence.append(dict(case_id=case,waveform=part[0]['waveform'],split=part[0]['split'],family=part[0]['family'],
                               target_w=part[0]['target_w'],initial_pitch_rad=part[0]['initial_pitch_rad'],
                               failed_runs=','.join(str(x['run']) for x in part if x['worse_pi']),
                               worse_pi_runs=sum(x['worse_pi'] for x in part),
                               mean_delta_pi_rmse_w=statistics.fmean(x['delta_pi_rmse_w'] for x in part),
                               max_delta_pi_rmse_w=max(x['delta_pi_rmse_w'] for x in part)))
    write_csv(root/'recurrence.csv',recurrence)
    history=[]
    for run in range(3):
        selected_step=config['selected_steps'][run]
        selected_rows={x['case_id']:x for x in read_csv(SOURCE/f'n8_run{run}/step_{selected_step:08d}/attempt_000/validation_metrics.csv')}
        initial_rows={x['case_id']:x for x in read_csv(SOURCE/f'n8_run{run}/step_00000000/attempt_000/validation_metrics.csv')}
        for step in range(0,16385,4096):
            for row in read_csv(SOURCE/f'n8_run{run}/step_{step:08d}/attempt_000/validation_metrics.csv'):
                history.append(dict(run=run,step=step,selected_step=selected_step,case_id=row['case_id'],family=row['family'],
                                    target_w=row['target_w'],initial_pitch_rad=row['initial_pitch_rad'],
                                    rmse_w=float(row['rmse_w']),mean_error_w=float(row['mean_error_w']),
                                    delta_selected_rmse_w=float(row['rmse_w'])-float(selected_rows[row['case_id']]['rmse_w']),
                                    delta_initial_rmse_w=float(row['rmse_w'])-float(initial_rows[row['case_id']]['rmse_w'])))
    write_csv(root/'selection_history.csv',history)
    selected_pairs=[x for x in pairs if x['role']=='selected']
    fail=[x for x in selected_pairs if x['worse_pi']]
    result=dict(status='passed',routine_cases=len(pi),distinct_waveforms=len(set(wind_id(c) for c in pi)),
                selected_slots=len(selected_pairs),selected_worse_pi=len(fail),
                recurrent_cases_at_least_2_runs=sum(x['worse_pi_runs']>=2 for x in recurrence),
                recurrent_waveforms_at_least_2_runs=len(set(x['waveform'] for x in recurrence if x['worse_pi_runs']>=2)),
                failures_with_positive_bias_square_difference=sum(x['delta_pi_bias_squared_w2']>0 for x in fail),
                failures_with_negative_variance_difference=sum(x['delta_pi_variance_w2']<0 for x in fail),
                saved_metric_max_abs_residual=max_residual,shared_weather_verified=True,
                original_selection_cases_without_pi=18,pressure_excluded_from_candidate=True,
                model_forward_rows=0,environment_steps=0,optimizer_updates=0)
    write_json(root/'trajectory_verification.json',result)
    print(json.dumps(result))


def replay_audit(root):
    config=check_sources(root)
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    import numpy as np
    import torch
    from .algorithm import MADDPG
    from .nstep_algorithm import NStepMADDPG
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    # No audit may silently learn or consume the sampled training stream.
    def forbidden(*args,**kwargs):
        raise AssertionError('optimizer/sampling forbidden in offline audit')
    MADDPG.update=forbidden
    states=[]
    cached={}
    selection=[x for x in read_json(SOURCE/'selection.json')['results'] if x['n']==8]
    torch_rng=torch.get_rng_state().clone()
    for r in selection:
        for role in ('selected','final'):
            identity=sha(r[role])
            if identity in cached:
                states.extend(dict(run=r['run'],role=role,checkpoint_sha256=identity,**x) for x in cached[identity])
                continue
            agent,meta=NStepMADDPG.load(r[role],expected_n=8)
            agent.replay.sample=forbidden
            assert agent.config.gamma==.99
            snapshot={k:{n:p.detach().clone() for n,p in getattr(agent,k).state_dict().items()}
                      for k in ('actors','critics','target_actors','target_critics')}
            rng=json.dumps(agent.replay.rng.bit_generator.state,sort_keys=True)
            order=np.argsort(agent.replay.sequence[:agent.replay.size],kind='stable')
            idx=order[np.linspace(0,len(order)-1,1024,dtype=int)]
            data=agent.replay.data
            obs=torch.as_tensor(data['obs'][idx])
            behavior=torch.as_tensor(data['actions'][idx])
            with torch.no_grad():
                current=torch.stack([agent.policy(m,obs[:,i]) for i,m in enumerate(agent.actors)],dim=1)
            db=(current[:,:,1]-behavior[:,:,1]).numpy()
            feature_obs=data['obs'][:agent.replay.size].reshape(agent.replay.size,-1).astype(np.float64)
            scale=np.maximum(feature_obs.std(axis=0),1e-6)
            query=feature_obs[idx]/scale
            reference=feature_obs/scale
            nearest=[]
            for start in range(0,1024,32):
                d=((query[start:start+32,None,:]-reference[None,:,:])**2).sum(axis=2)
                d[np.arange(len(d)),idx[start:start+32]]=np.inf
                nn=np.argpartition(d,31,axis=1)[:,:32]
                nearest.extend(nn)
            neighbor_actions=data['actions'][np.asarray(nearest),:,1]
            low,high=neighbor_actions.min(axis=1),neighbor_actions.max(axis=1)
            outside=(current[:,:,1].numpy()<low)|(current[:,:,1].numpy()>high)
            rawactor=[]
            for i in range(3):
                grad=[]
                for mode in ('replay_teammates','current_teammates'):
                    own=current[:,i,:].detach().clone().requires_grad_(True)
                    others=behavior.detach() if mode=='replay_teammates' else current.detach()
                    joint=torch.stack([own if j==i else others[:,j] for j in range(3)],dim=1)
                    q=agent.critics[i](torch.cat((obs.flatten(1),joint.flatten(1)),dim=1))
                    g=torch.autograd.grad(q.sum(),own)[0][:,1].detach().numpy()
                    grad.append(g)
                old,new=grad
                nonflat=(np.abs(old)>1e-6)&(np.abs(new)>1e-6)
                out=current[:,i,1].numpy()
                sensitivity=[]
                # Input derivative is a network sensitivity, not a physical correction proof.
                x=obs[:,i].detach().clone().requires_grad_(True)
                ownout=agent.policy(agent.actors[i],x)[:,1]
                sens=torch.autograd.grad(ownout.sum(),x)[0].detach().numpy()
                for j in (3,6,8,9,10,14):
                    sensitivity.append((j,float(np.mean(np.abs(sens[:,j])))))
                rawactor.append(dict(agent=i,nonflat_points=int(nonflat.sum()),
                                     sign_changed=int(((old*new<0)&nonflat).sum()),
                                     mean_abs_gradient_replay=float(np.abs(old).mean()),
                                     mean_abs_gradient_current=float(np.abs(new).mean()),
                                     saturation_fraction=float((np.abs(out)>=.99).mean()),
                                     mean_tanh_jacobian=float((1-out*out).mean()),
                                     outside_neighbor_range_fraction=float(outside[:,i].mean()),
                                     mean_abs_current_minus_behavior_rad=float(np.abs(db[:,i]).mean()*.11),
                                     p95_abs_current_minus_behavior_rad=float(np.quantile(np.abs(db[:,i])*.11,.95)),
                                     derivative_abs_by_feature=json.dumps(dict(sensitivity),sort_keys=True)))
            for st in rawactor:
                states.append(dict(run=r['run'],role=role,checkpoint_sha256=identity,**st))
            cached[identity]=rawactor
            for name,values in snapshot.items():
                assert all(torch.equal(p,values[n]) for n,p in getattr(agent,name).state_dict().items())
            assert json.dumps(agent.replay.rng.bit_generator.state,sort_keys=True)==rng
    torch.set_rng_state(torch_rng)
    write_csv(root/'replay_gradient.csv',states)
    training=[]
    manifest={(int(x['run']),int(x['episode_index'])):x for x in read_csv(SOURCE/'training_manifest.csv')}
    for run in range(3):
        for ep in range(128):
            step=(ep+1)*128
            z=np.load(SOURCE/f'n8_run{run}/step_{step:08d}/attempt_000/training.npz')
            design=manifest[(run,ep)]
            assert z['obs'].shape==(128,3,15)
            errors=z['error_w'].astype(np.float64)
            m=moments(errors.tolist())
            # Executed normalized pitch reference, not actuator position.
            action=z['actions'][:,:,1].astype(np.float64)
            training.append(dict(run=run,episode_index=ep,quarter=ep//32,family=design['family'],target_w=design['target_w'],
                                 initial_pitch_rad=design['initial_pitch_rad'],**m,
                                 command_boundary_fraction=float((np.abs(action)>=.99).mean())))
    write_csv(root/'training_behavior.csv',training)
    write_json(root/'replay_verification.json',dict(status='passed',loaded_role_states=6,unique_state_files=len(set(r['checkpoint_sha256'] for r in states)),
                points_per_state=1024,gradient_points_are_correlated=True,optimizer_updates=0,model_forward_rows=0,
                rng_consumed=False,network_parameters_unchanged=True,training_behavior_episodes=len(training),
                nearest_range_is_not_density_certificate=True))
    print(json.dumps(dict(replay_rows=len(states),training_episodes=len(training),optimizer_updates=0,model_forward_rows=0)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','trajectories','replay'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=args.output.resolve()
    {'prepare':prepare,'trajectories':trajectory_audit,'replay':replay_audit}[args.mode](root)


if __name__=='__main__':
    main()
