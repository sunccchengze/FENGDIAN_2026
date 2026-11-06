"""Bounded pitch action forks and Critic diagnostics. No optimizer updates."""
from __future__ import annotations

import argparse
from copy import copy, deepcopy
import csv
import gzip
import hashlib
import json
from pathlib import Path
import time

from .fixed_pinn_demo import activate_runtime, digest
from .pitch_cross_wind_diagnostic import ORIGINAL, SOURCE, make_cases, read_csv, write_csv, write_json

PREVIOUS = Path(__file__).resolve().parents[1]/'experiments/20261027_pitch_cross_wind_diagnostic'
DEFAULT = PREVIOUS.parent/'20261028_pitch_action_diagnostic'
PITCH = 'collective_pitch_reference_rad'


def variants():
    rows = [dict(id='parent', direction='none', delta_rad=0., vector=[0., 0., 0.])]
    for name, vector in [('common', [1, 1, 1]), ('unit1', [1, 0, 0]), ('unit2', [0, 1, 0]), ('unit3', [0, 0, 1])]:
        for delta in (-.01, -.005, .005, .01):
            rows.append(dict(id=f'{name}_{delta:+.3f}', direction=name, delta_rad=delta,
                             vector=[delta*v for v in vector]))
    return rows


def clone_env(env):
    """Copy every mutable environment/actuator field; share stateless plant only."""
    result = copy(env)
    result.__dict__ = {k: v if k == 'plant' else deepcopy(v) for k, v in env.__dict__.items()}
    return result


def corrected_action(env, parent, variant):
    import numpy as np
    raw = parent.copy()
    raw[:, 1] += np.asarray(variant['vector'], dtype=np.float32)*2/(env.high[1]-env.low[1])
    return raw, np.clip(env.project_action(raw), -1, 1).astype(np.float32)


def batch_step(envs, actions):
    """Canonical single-row inference per branch after batched arithmetic failed QA."""
    assert len(envs)==len(actions)
    return [env.step(action) for env, action in zip(envs, actions)]


def critic_probe(agent, obs, candidates):
    import numpy as np
    import torch
    x = torch.as_tensor(np.stack([np.concatenate((obs.ravel(), a.ravel())) for a in candidates]))
    with torch.no_grad():
        q = torch.cat([c(x) for c in agent.critics], dim=1).cpu().numpy()
    return q


def gradients(agent, obs, parent):
    import numpy as np
    import torch
    actions = torch.tensor(parent[None], requires_grad=True)
    state = torch.as_tensor(obs[None])
    x = torch.cat((state.flatten(1), actions.flatten(1)), dim=1)
    all_grad = []
    for critic in agent.critics:
        g = torch.autograd.grad(critic(x).sum(), actions, retain_graph=True)[0][0, :, 1]
        all_grad.append(g.detach().cpu().numpy())
    rows = []
    for i, actor in enumerate(agent.actors):
        value = agent.policy(actor, torch.as_tensor(obs[i]))[1]
        j = torch.autograd.grad(value, tuple(actor.parameters()), allow_unused=True)
        norm2 = float(sum((v*v).sum().item() for v in j if v is not None))
        diagonal = float(all_grad[i][i])
        rows.append(dict(unit=i+1, q_diagonal_gradient_per_normalized_action=diagonal,
                         ensemble_gradient_per_normalized_action=float(np.mean(all_grad, axis=0)[i]),
                         actor_pitch_parameter_jacobian_l2=norm2**.5,
                         raw_actor_objective_gradient_l2=abs(diagonal)*norm2**.5,
                         first_order_pitch_drift_per_sgd_lr_rad=diagonal*norm2*.11,
                         **{f'q{j+1}_gradient_for_this_unit':float(all_grad[j][i]) for j in range(3)}))
    return rows


def support(agent, obs, candidates):
    import numpy as np
    states = agent.replay.data['obs'][:agent.replay.size].reshape(agent.replay.size, -1)
    distance = np.sqrt(np.mean((states-obs.ravel())**2, axis=1))
    idx = np.argsort(distance, kind='stable')[:32]
    pitches = agent.replay.data['actions'][:agent.replay.size, :, 1]
    low, high = pitches[idx].min(0), pitches[idx].max(0)
    global_low, global_high = pitches.min(0), pitches.max(0)
    common = dict(knn32_mean_obs_rms_distance=float(distance[idx].mean()),
                  obs_outside_replay_coordinate_fraction=float(np.mean((obs.ravel()<states.min(0)) | (obs.ravel()>states.max(0)))))
    return [dict(**common, local_pitch_outside_fraction=float(np.mean((a[:, 1]<low) | (a[:, 1]>high))),
                 global_pitch_outside_fraction=float(np.mean((a[:, 1]<global_low) | (a[:, 1]>global_high)))) for a in candidates]


def trace_row(env, before, action, variant, info, reward, h):
    import numpy as np
    mapped = env.mapper.map(env.project_action(action))
    command = mapped.commanded_control[PITCH]
    pitch_before = before['applied'][:, 1]
    requested = (1-np.exp(-env.dt/env.config['time_constants_s'][1]))*(command-pitch_before)
    row = dict(h=h, decision_step=info['step']-1, response_step=info['step'],
               decision_wind_m_s=float(before['wind'][0]), response_wind_m_s=float(info['wind'][0]),
               error_w=info['error_w'], farm_power_w=info['farm_power_w'], reward=float(reward[0]),
               tracking_reward=env.config.get('reward_scale', 1.)*info['reward_terms']['tracking'],
               action_reward=env.config.get('reward_scale', 1.)*info['reward_terms']['action_change'],
               action_change=info['action_change'],
               requested_pitch_clip_fraction=float(np.mean((action[:, 1]<-1) | (action[:, 1]>1))),
               pitch_rate_fraction=float(np.mean(np.abs(requested)>env.config['rate_limits'][1])))
    for i in range(3):
        row.update({f'pitch_command_{i}':float(command[i]), f'pitch_before_{i}':float(pitch_before[i]),
                    f'pitch_actual_{i}':float(info['applied'][i, 1]), f'power_{i}_w':float(info['power_w'][i]),
                    f'executed_pitch_normalized_{i}':float(info['executed_action'][i, 1])})
    return row


def totals(rows, gamma):
    import numpy as np
    errors = np.array([r['error_w'] for r in rows])
    discount = gamma**np.arange(len(rows))
    return dict(steps=len(rows), rmse_w=float(np.sqrt(np.mean(errors**2))), mean_error_w=float(errors.mean()),
                error_std_w=float(errors.std()), discounted_return=float(discount@np.array([r['reward'] for r in rows])),
                tracking_return=float(discount@np.array([r['tracking_reward'] for r in rows])),
                action_return=float(discount@np.array([r['action_reward'] for r in rows])),
                pitch_rate_fraction=float(np.mean([r['pitch_rate_fraction'] for r in rows])),
                pitch_clip_fraction=float(np.mean([r['requested_pitch_clip_fraction'] for r in rows])))


class TraceWriter:
    def __init__(self, path):
        self.file = gzip.open(path, 'wt', encoding='utf-8', newline='', compresslevel=1)
        self.writer = None

    def add(self, row):
        if self.writer is None:
            self.writer = csv.DictWriter(self.file, list(row), lineterminator='\n')
            self.writer.writeheader()
        self.writer.writerow(row)

    def close(self):
        self.file.close()


def reset_case(env, case, wind):
    import numpy as np
    env.initial = np.array(env.config['initial_operating_point'], dtype=float)
    env.initial[1] = case['initial_pitch_rad']
    return env.reset(seed=42, options=dict(wind_trajectory=wind.values, target_w=case['target_w']))


def evaluate_case(env, agent, case, wind, run_id, output, old_rows):
    import numpy as np
    grid = variants()
    obs, info = reset_case(env, case, wind)
    envs = [clone_env(env) for _ in grid]
    observations = [obs.copy() for _ in grid]
    infos = [deepcopy(info) for _ in grid]
    series = [[] for _ in grid]
    forks = {}
    identity = dict(run_id=run_id, case_id=case['id'], split=case['split'], family=case['family'],
                    target_w=case['target_w'], initial_pitch_rad=case['initial_pitch_rad'])
    full_writer = TraceWriter(output/'full_trajectories.csv.gz')
    fork_writer = TraceWriter(output/'fork_trajectories.csv.gz')
    try:
        for t in range(128):
            if t in (32, 96):
                forks[t] = (clone_env(envs[0]), observations[0].copy(), deepcopy(infos[0]))
            actions = [corrected_action(e, agent.act(o), v)[0] for e, o, v in zip(envs, observations, grid)]
            results = batch_step(envs, actions)
            for k, (e, action, v, result) in enumerate(zip(envs, actions, grid, results)):
                nxt, reward, done, _, after = result
                assert done == (t==127)
                row = trace_row(e, infos[k], action, v, after, reward, t+1)
                full_writer.add(dict(**identity, variant=v['id'], anchor=-1, **row))
                series[k].append(row)
                observations[k], infos[k] = nxt, after
        baseline_difference = max(abs(a['error_w']-float(b['error_w'])) for a, b in zip(series[0], old_rows))
        assert baseline_difference <= 20., baseline_difference
        full_metrics = [dict(**identity, variant=v['id'], direction=v['direction'], delta_rad=v['delta_rad'],
                             **totals(rows, agent.config.gamma)) for v, rows in zip(grid, series)]
        fork_metrics, gradient_rows = [], []
        for anchor, (original, obs, info) in forks.items():
            parent = agent.act(obs)
            first = [corrected_action(original, parent, v) for v in grid]
            candidates = [a for _, a in first]
            q = critic_probe(agent, obs, candidates)
            supports = support(agent, obs, candidates)
            gradient_rows.extend(dict(**identity, anchor=anchor, **g) for g in gradients(agent, obs, parent))
            branched = [clone_env(original) for _ in grid]
            observations = [obs.copy() for _ in grid]
            infos = [deepcopy(info) for _ in grid]
            data = [[] for _ in grid]
            for step in range(32):
                actions = [a for a, _ in first] if step==0 else [agent.act(o) for o in observations]
                results = batch_step(branched, actions)
                for k, (e, action, v, result) in enumerate(zip(branched, actions, grid, results)):
                    nxt, reward, done, _, after = result
                    assert done == (anchor+step+1==128)
                    row = trace_row(e, infos[k], action, v, after, reward, step+1)
                    fork_writer.add(dict(**identity, variant=v['id'], anchor=anchor, **row))
                    data[k].append(row)
                    observations[k], infos[k] = nxt, after
            for k, v in enumerate(grid):
                for horizon in (8, 32):
                    fork_metrics.append(dict(**identity, anchor=anchor, horizon=horizon, variant=v['id'],
                        direction=v['direction'], delta_rad=v['delta_rad'], q_mean=float(q[k].mean()),
                        **{f'q_{i}':float(q[k, i]) for i in range(3)}, **supports[k],
                        **totals(data[k][:horizon], agent.config.gamma)))
    finally:
        full_writer.close()
        fork_writer.close()
    write_csv(output/'metrics.csv', full_metrics)
    write_csv(output/'fork_metrics.csv', fork_metrics)
    write_csv(output/'gradients.csv', gradient_rows)
    audit = dict(complete=True, baseline_max_difference_w=baseline_difference,
                 full_environment_steps=17*128, fork_environment_steps=2*17*32,
                 hashes={p.name:digest(p) for p in output.iterdir() if p.is_file()})
    write_json(output/'audit.json', audit)
    return audit


def preflight(env, agent, bank, output):
    import numpy as np
    examples = (bank[0], next(v for v in bank if v[0]['id']=='validation_ramp_1_pitch0.04_initial_0.04'), bank[-1])
    maxima = dict(power_difference_w=0., action_difference=0., reward_difference=0.)
    for case, wind in examples:
        obs, info = reset_case(env, case, wind)
        serial = [clone_env(env) for _ in variants()]
        parallel = [clone_env(env) for _ in variants()]
        so = [obs.copy() for _ in variants()]
        po = [obs.copy() for _ in variants()]
        for step in range(8):
            sa = [corrected_action(e, agent.act(o), v)[0] for e, o, v in zip(serial, so, variants())]
            pa = [corrected_action(e, agent.act(o), v)[0] for e, o, v in zip(parallel, po, variants())]
            sr = [e.step(a) for e, a in zip(serial, sa)]
            pr = batch_step(parallel, pa)
            for i, (a, b) in enumerate(zip(sr, pr)):
                maxima['power_difference_w'] = max(maxima['power_difference_w'], abs(a[4]['error_w']-b[4]['error_w']))
                maxima['action_difference'] = max(maxima['action_difference'], float(np.max(np.abs(sa[i]-pa[i]))))
                maxima['reward_difference'] = max(maxima['reward_difference'], float(np.max(np.abs(a[1]-b[1]))))
                so[i], po[i] = a[0], b[0]
    assert maxima['power_difference_w'] <= 20. and maxima['action_difference'] <= 1e-5 and maxima['reward_difference'] <= 1e-5, maxima
    write_json(output/'preflight.json', dict(**maxima, serial_steps=408, batch_environment_steps=408, complete=True))
    return maxima


def run(output, only_preflight=False):
    import numpy as np
    import torch
    import tensorflow as tf
    import yaml
    from .algorithm import MADDPG
    from .workflow import build_env
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    tf.config.threading.set_intra_op_parallelism_threads(1)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    root = Path(output).resolve()
    prior = yaml.safe_load((PREVIOUS/'config.yaml').read_text(encoding='utf-8'))
    saved = yaml.safe_load((SOURCE/'config.yaml').read_text(encoding='utf-8'))
    selection = json.loads((SOURCE/'selection.json').read_text(encoding='utf-8'))
    protection = dict(prior['protected_hashes'])
    for path in PREVIOUS.iterdir():
        if path.is_file():
            protection[str(path)] = digest(path)
    for name in ('pitch_action_diagnostic.py', 'PITCH_ACTION_DIAGNOSTIC_PROTOCOL.md'):
        path = Path(__file__).with_name(name)
        protection[str(path)] = digest(path)
    assert all(digest(p)==h for p, h in protection.items())
    config = dict(seed=42, source_commit='48d4dd4061f68605314b9a3f01dda7e36ba8368d', base_config=prior['base_config'],
                  previous=str(PREVIOUS), variants=variants(), anchors=[32, 96], fork_horizons=[8, 32],
                  support_neighbors=32, evaluation_environment_steps=430848, rl_training_steps=0,
                  test_access=False, protected_hashes=protection, only_preflight=only_preflight)
    if root.exists():
        existing = yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
        assert existing == config, 'resume configuration changed'
        if (root/'summary.txt').exists():
            raise ValueError('completed run is frozen')
    else:
        root.mkdir(parents=True)
        (root/'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8', newline='\n')
    bank, _ = make_cases(saved)
    expected = {r['id']:r for r in json.loads((PREVIOUS/'case_manifest.json').read_text(encoding='utf-8'))}
    for case, wind in bank:
        assert hashlib.sha256(wind.values.tobytes()).hexdigest()==expected[case['id']]['wind_values_sha256']
    assert len(bank)==len(expected)==44
    env = build_env(prior['base_config'])
    agents = [MADDPG.load(r['best']['checkpoint'])[0] for r in selection['results']]
    parameter_hashes = [hashlib.sha256(b''.join(v.detach().cpu().numpy().tobytes() for model in
                        (a.actors, a.critics, a.target_actors, a.target_critics) for v in model.state_dict().values())).hexdigest() for a in agents]
    if not (root/'preflight.json').exists():
        print(json.dumps(dict(preflight=preflight(env, agents[0], bank, root))), flush=True)
    if only_preflight:
        return
    old = {}
    for row in read_csv(PREVIOUS/'trajectories.csv'):
        old.setdefault((row['controller'], row['case_id']), []).append(row)
    start = time.perf_counter()
    all_full, all_forks, all_gradients, audits = [], [], [], []
    for run_id, agent in enumerate(agents):
        for case_index, (case, wind) in enumerate(bank):
            job = root/'jobs'/f'run{run_id}_case{case_index:03d}'
            attempts = sorted(job.glob('attempt_*')) if job.exists() else []
            complete = next((p for p in reversed(attempts) if (p/'audit.json').exists()), None)
            if complete:
                out = complete
                audit = json.loads((out/'audit.json').read_text(encoding='utf-8'))
                assert all(digest(out/n)==h for n, h in audit['hashes'].items())
            else:
                out = job/f'attempt_{len(attempts):03d}'
                out.mkdir(parents=True)
                audit = evaluate_case(env, agent, case, wind, run_id, out, old[(f'parent_{run_id}', case['id'])])
            all_full.extend(read_csv(out/'metrics.csv'))
            all_forks.extend(read_csv(out/'fork_metrics.csv'))
            all_gradients.extend(read_csv(out/'gradients.csv'))
            audits.append(dict(run_id=run_id, case_id=case['id'], path=str(out), **audit))
            if case_index%4==0 or case_index==43:
                print(json.dumps(dict(run=run_id, case=case_index+1, total_cases=44, elapsed_s=round(time.perf_counter()-start, 1))), flush=True)
    for agent, expected_hash in zip(agents, parameter_hashes):
        actual = hashlib.sha256(b''.join(v.detach().cpu().numpy().tobytes() for model in
                 (agent.actors, agent.critics, agent.target_actors, agent.target_critics) for v in model.state_dict().values())).hexdigest()
        assert actual==expected_hash
    assert all(digest(p)==h for p, h in protection.items())
    write_csv(root/'metrics.csv', all_full)
    write_csv(root/'fork_metrics.csv', all_forks)
    write_csv(root/'gradients.csv', all_gradients)
    write_json(root/'jobs.json', audits)
    write_json(root/'summary.txt', dict(seed=42, complete=True, jobs=len(audits), full_metric_rows=len(all_full),
               fork_metric_rows=len(all_forks), gradient_rows=len(all_gradients), rl_training_steps=0,
               evaluation_environment_steps=sum(a['full_environment_steps']+a['fork_environment_steps'] for a in audits),
               protected_files=len(protection), protected_files_unchanged=True, parameters_unchanged=True,
               maximum_parent_replay_difference_w=max(a['baseline_max_difference_w'] for a in audits), elapsed_s=time.perf_counter()-start,
               test_access=False, physical_validation=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'run'))
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args()
    activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    run(args.output, only_preflight=args.command=='preflight')


if __name__ == '__main__':
    main()
