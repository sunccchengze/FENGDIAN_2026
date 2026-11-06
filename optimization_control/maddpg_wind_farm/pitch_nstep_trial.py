"""Frozen paired pitch continuation: n=1 versus n=8, bounded and resumable."""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

from .fixed_pinn_demo import activate_runtime, digest
from .pitch_cross_wind_diagnostic import ORIGINAL, SOURCE, write_csv, write_json, read_csv

HERE = Path(__file__).parent
PURPOSE = 20261028
FAMILIES = ('stationary', 'ramp', 'gust')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify(hashes):
    if not all(Path(p).is_file() and digest(p) == h for p, h in hashes.items()):
        raise ValueError('frozen source/output identity changed')


def frozen(root):
    import yaml
    s = yaml.safe_load((Path(root) / 'config.yaml').read_text(encoding='utf-8'))
    verify(s['protected_hashes'])
    return s


def derived(purpose, run, *extra):
    import numpy as np
    return np.random.SeedSequence([42, PURPOSE, purpose, run, *extra])


def training_design(run, episode):
    import numpy as np
    pairs = [(f, t) for f in FAMILIES for t in (2.6e6, 3.2e6, 3.8e6)]
    block, index = divmod(episode, 9)
    order = np.random.default_rng(derived(1, run, block)).permutation(9)
    family, target = pairs[order[index]]
    pitch = float(np.random.default_rng(derived(2, run, episode)).uniform(.025, .055))
    return family, target, pitch


def wind(cfg, family, split, episode):
    from ..environments.farm_inflow import generate_inflow
    inflow = deepcopy(cfg['environment']['inflow']); inflow['speed']['scenario'] = family
    return generate_inflow(inflow, dt_s=1., horizon=128, seed=42, split=split, episode=episode)


def make_bank(root, cfg, split):
    """Independent test construction is unreachable before immutable selection exists."""
    import numpy as np
    if split == 'test' and not (root / 'selection.json').is_file():
        raise ValueError('test locked until all selections frozen')
    out = root / f'{split}_bank'; out.mkdir(exist_ok=False)
    cases = []
    targets = (2.9e6, 3.5e6) if split == 'validation' else (2.65e6, 3.25e6, 3.95e6)
    pitches = (.025, .04, .055) if split == 'validation' else (.025, .055)
    offset, repeats = (32000000, 1) if split == 'validation' else (33000000, 2)
    for fi, family in enumerate(FAMILIES):
        for ti, target in enumerate(targets):
            for repeat in range(repeats):
                episode = offset + fi * 100 + ti * 10 + repeat
                trace = wind(cfg, family, split, episode)
                path = out / f'{family}_{ti}_{repeat}.csv'; trace.save(path)
                for pitch in pitches:
                    cases.append(dict(id=f'{split}_{family}_t{target:g}_r{repeat}_p{pitch}', split=split, family=family,
                                      target_w=target, initial_pitch_rad=pitch, episode=episode, path=str(path.resolve())))
    if split == 'test':
        for wi, speed in enumerate((7.6, 7.8)):
            trace = wind(cfg, 'stationary', 'test', 33009000 + wi)
            trace.values[:] = [speed, 0., .08]; trace.components[:] = [speed, 0., 0.]
            trace.metadata.update(override_family='low_wind_stress', source='explicit_constant_model_stress')
            path = out / f'stress_{speed}.csv'; trace.save(path)
            for target in (4.35e6, 4.55e6):
                for pitch in pitches:
                    cases.append(dict(id=f'test_stress_w{speed}_t{target:g}_p{pitch}', split='stress', family='low_wind_stress',
                                      target_w=target, initial_pitch_rad=pitch, episode=33009000 + wi, path=str(path.resolve())))
    write_json(out / 'manifest.json', dict(seed=42, cases=cases,
               hashes={str(p.resolve()): digest(p) for p in out.iterdir() if p.is_file()}))


def bank(root, split):
    from ..environments.farm_inflow import InflowTrace
    m = read_json(Path(root) / f'{split}_bank/manifest.json'); verify(m['hashes'])
    return [(c, InflowTrace.load(c['path'])) for c in m['cases']]


def prepare(root, smoke):
    import yaml
    import numpy as np
    from .nstep_algorithm import NStepMADDPG
    from .workflow import build_env
    root = Path(root).resolve(); root.mkdir(parents=True, exist_ok=False)
    old = yaml.safe_load((SOURCE / 'config.yaml').read_text(encoding='utf-8'))
    sel = read_json(SOURCE / 'selection.json')
    parents = {str(r['run_id']): dict(checkpoint=r['best']['checkpoint'], sha256=digest(r['best']['checkpoint'])) for r in sel['results']}
    cfg = deepcopy(old['base_config'])
    # Parent metadata is the authoritative unchanged plant, actuator and algorithm configuration.
    _, metadata = NStepMADDPG.inherit(parents['0']['checkpoint'], 1)
    cfg = metadata['config']
    expected = dict(actor_lr=.0001, critic_lr=.001, gamma=.99, tau=.01, batch_size=64, capacity=32768)
    for run in range(3):
        a, meta = NStepMADDPG.inherit(parents[str(run)]['checkpoint'], 8)
        if meta['config'] != cfg or tuple(a.config.action_mask) != (0, 1, 0):
            raise ValueError('parents must share unchanged pitch-only config')
        if any(getattr(a.config, k) != v for k, v in expected.items()):
            raise ValueError('parent hyperparameter mismatch')
        a.replay.spans(np.arange(a.replay.size))
        parents[str(run)].update(updates=a.updates, replay_size=a.replay.size, replay_position=a.replay.position,
                                  algorithm_rng=a.rng.bit_generator.state, replay_rng=a.replay.rng.bit_generator.state)
    protected = {**old['source_hashes'], **sel['hashes']}
    for p in (SOURCE / 'config.yaml', SOURCE / 'selection.json', ORIGINAL / 'PROJECT_STATUS.md', ORIGINAL / 'optimization_control/TASKFLOW.md', ORIGINAL / 'README.md'):
        protected[str(p)] = digest(p)
    for p in HERE.glob('*.py'):
        if p.name != 'pitch_nstep_review.py':
            protected[str(p.resolve())] = digest(p)
    protected[str((HERE / 'PITCH_NSTEP_PROTOCOL.md').resolve())] = digest(HERE / 'PITCH_NSTEP_PROTOCOL.md')
    # Audit only maintained configurations and protocol namespace strings, never another task's test.
    scan_roots = [HERE / 'configs', ORIGINAL / 'optimization_control/maddpg_wind_farm/configs']
    collisions = []
    for directory in scan_roots:
        for p in directory.glob('*.yaml'):
            if any(str(i) in p.read_text(encoding='utf-8-sig') for i in (31000000, 32000000, 33000000)):
                collisions.append(str(p))
    if collisions:
        raise ValueError(f'episode namespace collision: {collisions}')
    settings = dict(seed=42, version='pitch_nstep_trial_v1', mode='smoke' if smoke else 'formal',
                    arms=[1, 8], run_ids=[0] if smoke else [0, 1, 2], steps_per_job=1024 if smoke else 16384,
                    eval_every=4096, warmup_steps=512, update_every=2, save_every=128,
                    tail_rule='actual_m_bootstrap_unless_true_terminal_v1', noise_std=[0., .03, 0.], noise_end_fraction=.2,
                    seed_namespace=[42, PURPOSE], training_offset=31000000, validation_offset=32000000, test_offset=33000000,
                    namespace_collisions=collisions, test_targets_w=[2650000., 3250000., 3950000.],
                    gates=dict(ramp_mean_improvement=.05, ramp_improved_runs=2, other_family_max_regression=.05, max_final_over_selected=1.25),
                    base_config=cfg, parents=parents, protected_hashes=protected,
                    off_policy_bias='behavior future rewards; no importance correction', selection='complete_128_step_mean_rmse_strict_improvement_including_initial')
    (root / 'config.yaml').write_text(yaml.safe_dump(settings, allow_unicode=True, sort_keys=False), encoding='utf-8', newline='\n')
    make_bank(root, cfg, 'validation')
    traces = root / 'train_bank'; traces.mkdir()
    rows = []
    for run in settings['run_ids']:
        for ep in range(settings['steps_per_job'] // 128):
            family, target, pitch = training_design(run, ep)
            episode = 31000000 + run * 1000 + ep
            trace = wind(cfg, family, 'train', episode); path = traces / f'run{run}_ep{ep:03d}.csv'; trace.save(path)
            rows.append(dict(run=run, episode_index=ep, episode=episode, family=family, target_w=target, initial_pitch_rad=pitch,
                             path=str(path.resolve()), csv_sha256=digest(path), json_sha256=digest(path.with_suffix('.json')),
                             values_sha256=hashlib.sha256(trace.values.tobytes()).hexdigest()))
    write_csv(root / 'training_manifest.csv', rows)
    write_csv(root / 'metrics.csv', [dict(status='prepared', saved_training_steps=0)])
    write_json(root / 'summary.txt', dict(seed=42, status='prepared', test_locked=True, saved_training_steps=0))
    print(json.dumps(dict(prepared=str(root), jobs=len(settings['run_ids']) * 2, total_new_steps=settings['steps_per_job'] * len(settings['run_ids']) * 2)), flush=True)


def attempt_dir(base):
    base.mkdir(parents=True, exist_ok=True)
    out = base / f'attempt_{len(list(base.glob("attempt_*"))):03d}'
    out.mkdir(exist_ok=False)
    return out


def capture(env, cases, *, agent=None, mode=None):
    from .pitch_cross_wind_diagnostic import rollout
    metrics, traces = [], []
    for case, trace in cases:
        m, t = rollout(env, case, trace, agent=agent, mode=mode)
        metrics.append(m); traces.extend(t)
    return metrics, traces


def compressed_csv(path, rows):
    import csv
    with gzip.open(path, 'wt', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, list(rows[0]), lineterminator='\n'); w.writeheader(); w.writerows(rows)


def train(root, n, run, stop_after=None):
    import numpy as np
    from .nstep_algorithm import NStepMADDPG
    from .stable_workflow import Exploration
    from .workflow import build_env
    from ..environments.farm_inflow import InflowTrace
    root = Path(root).resolve(); s = frozen(root)
    if (root / 'selection.json').exists() or n not in s['arms'] or run not in s['run_ids']:
        raise ValueError('training frozen or unknown arm/stream')
    job = root / f'n{n}_run{run}'; job.mkdir(exist_ok=True)
    if (job / 'result.json').exists():
        verify(read_json(job / 'result.json')['hashes']); return
    env = build_env(s['base_config']); env._baseline_config = s['base_config']['baselines']
    noise = Exploration(int(derived(3, run).generate_state(1)[0]), s['noise_std'], [10., 3., 5.], 1., 'white', .2)
    commits = sorted(job.glob('step_*/attempt_*/commit.json'))
    resume = None
    if commits:
        commit = read_json(commits[-1]); verify(commit['hashes'])
        agent, meta = NStepMADDPG.load(commit['checkpoint'], n)
        if meta['root_config_sha256'] != digest(root / 'config.yaml') or meta['run'] != run:
            raise ValueError('resume identity mismatch')
        step, episode, history, best, initial = (meta[k] for k in ('step', 'episode', 'history', 'best', 'initial'))
        noise.load_state_dict(meta['noise']); resume = str(commits[-1])
    else:
        agent, _ = NStepMADDPG.inherit(s['parents'][str(run)]['checkpoint'], n)
        step = episode = 0; history = []; best = initial = None
    validation = bank(root, 'validation')
    manifest = [r for r in read_csv(root / 'training_manifest.csv') if int(r['run']) == run]

    def save(out, transitions=None, losses=None):
        nonlocal initial, best
        path = (out / 'state.pth').resolve()
        if step == 0 or step % s['eval_every'] == 0 or step == s['steps_per_job']:
            rows, trace = capture(env, validation, agent=agent)
            score = float(np.mean([r['rmse_w'] for r in rows]))
            if initial is None:
                initial = str(path)
            if best is None or score < best['score_w']:
                best = dict(step=step, checkpoint=str(path), score_w=score)
            history.append(dict(step=step, rmse_w=score, best_rmse_w=best['score_w'], selected_step=best['step']))
            write_csv(out / 'validation_metrics.csv', rows); compressed_csv(out / 'validation_traces.csv.gz', trace)
            print(json.dumps(dict(n=n, run=run, step=step, validation_rmse_w=score, best_step=best['step'], updates=agent.updates)), flush=True)
        if transitions:
            np.savez_compressed(out / 'training.npz', **{k: np.stack([t[k] for t in transitions]) for k in transitions[0]})
            write_csv(out / 'losses.csv', losses or [dict(no_updates=1)])
        meta = dict(config=s['base_config'], root_config_sha256=digest(root / 'config.yaml'), run=run, n=n,
                    step=step, episode=episode, history=history, best=best, initial=initial, noise=noise.state_dict(),
                    parent=s['parents'][str(run)], resume_from=resume, updates=agent.updates)
        agent.save(path, meta)
        write_json(out / 'commit.json', dict(step=step, checkpoint=str(path),
                   hashes={str(p.resolve()): digest(p) for p in out.iterdir() if p.is_file()}))
        if step % 1024 == 0:
            print(json.dumps(dict(saved_n=n, run=run, saved_steps=step, episode=episode, m_histogram=agent.replay.m_histogram.tolist())), flush=True)
        return str(path)

    if step == 0 and not commits:
        final = save(attempt_dir(job / 'step_00000000'))
    else:
        final = commit['checkpoint']
    while step < s['steps_per_job'] and (stop_after is None or step < stop_after):
        design = manifest[episode]
        path = Path(design['path']); verify({str(path): design['csv_sha256'], str(path.with_suffix('.json')): design['json_sha256']})
        trace = InflowTrace.load(path)
        env.initial = np.array(env.config['initial_operating_point'], dtype=float); env.initial[1] = float(design['initial_pitch_rad'])
        obs, _ = env.reset(seed=42, options=dict(wind_trajectory=trace.values, target_w=float(design['target_w'])))
        noise.reset(); transitions, losses = [], []
        # The directory precedes computation, retaining evidence of uncommitted interrupted attempts.
        out = attempt_dir(job / f'step_{step + 128:08d}')
        write_json(out / 'started.json', dict(from_step=step, intended_step=step + 128, resume_from=resume, episode=episode,
                   wall_time_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
        for t in range(128):
            exploration = noise.sample(step / s['steps_per_job'])
            action = env.project_action(np.clip(agent.act(obs) + exploration, -1, 1)).astype(np.float32)
            nxt, reward, done, truncated, info = env.step(action)
            if truncated or done != (t == 127):
                raise ValueError('unexpected episode boundary')
            agent.replay.add(obs, info['executed_action'], reward, nxt, done)
            transitions.append(dict(obs=obs.copy(), next_obs=nxt.copy(), actions=info['executed_action'].copy(),
                                    rewards=reward.copy(), terminated=np.array([done]), exploration=exploration.copy(),
                                    error_w=np.array(info['error_w']), applied=info['applied'].copy(), wind=info['wind'].copy()))
            step += 1
            if step >= s['warmup_steps'] and step % s['update_every'] == 0:
                loss = agent.update()
                losses.append(dict(step=step, **loss, sample_indices_sha256=hashlib.sha256(agent.replay.last_indices.tobytes()).hexdigest(),
                                   m_mean=float(agent.replay.last_lengths.mean()), m_min=int(agent.replay.last_lengths.min()), m_max=int(agent.replay.last_lengths.max())))
            obs = nxt
        episode += 1; final = save(out, transitions, losses)
    if step == s['steps_per_job']:
        result = dict(n=n, run=run, steps=step, initial=initial, selected=best['checkpoint'], selected_step=best['step'], final=final,
                      history=history, final_over_selected=history[-1]['rmse_w'] / best['score_w'], updates=agent.updates,
                      added_updates=agent.updates - s['parents'][str(run)]['updates'], m_histogram=agent.replay.m_histogram.tolist(),
                      hashes={p: digest(p) for p in set((initial, best['checkpoint'], final))})
        write_json(job / 'result.json', result)


def select(root):
    root = Path(root).resolve(); s = frozen(root)
    if s['mode'] == 'smoke':
        raise ValueError('smoke cannot unlock test')
    if (root / 'selection.json').exists():
        raise FileExistsError('selection already immutable')
    results = [read_json(root / f'n{n}_run{r}/result.json') for n in s['arms'] for r in s['run_ids']]
    for result in results:
        verify(result['hashes'])
        if result['steps'] != 16384 or result['added_updates'] != 7937:
            raise ValueError('bounded matched budget/update count required')
    write_json(root / 'selection.json', dict(seed=42, results=results, config_sha256=digest(root / 'config.yaml'),
               validation_manifest_sha256=digest(root / 'validation_bank/manifest.json'), new_training_steps=sum(r['steps'] for r in results),
               test_used_for_selection=False))
    print('Selection frozen; new test may now be released', flush=True)


def evaluate(root, split):
    from .nstep_algorithm import NStepMADDPG
    from .workflow import build_env
    from .pitch_cross_wind_diagnostic import make_cases
    import yaml
    root = Path(root).resolve(); s = frozen(root); selection = read_json(root / 'selection.json')
    if selection['config_sha256'] != digest(root / 'config.yaml'):
        raise ValueError('selection/config mismatch')
    for r in selection['results']:
        verify(r['hashes'])
    if split == 'test':
        if not (root / 'test_bank').exists():
            make_bank(root, s['base_config'], 'test')
        cases = bank(root, 'test')
    else:
        old = yaml.safe_load((SOURCE / 'config.yaml').read_text(encoding='utf-8'))
        cases, _ = make_cases(old)
    env = build_env(s['base_config']); env._baseline_config = s['base_config']['baselines']
    labels = [(f'n{r["n"]}_run{r["run"]}_{state}', r[state], None) for r in selection['results'] for state in ('initial', 'selected', 'final')]
    labels += [('p', None, 'p'), ('pi', None, 'pi')]
    for label, checkpoint, mode in labels:
        base = root / 'evaluations' / split / label
        completed = sorted(base.glob('attempt_*/complete.json'))
        if completed:
            verify(read_json(completed[-1])['hashes']); continue
        out = attempt_dir(base)
        a = NStepMADDPG.load(checkpoint)[0] if checkpoint else None
        metrics, traces = capture(env, cases, agent=a, mode=mode)
        write_csv(out / 'metrics.csv', metrics); compressed_csv(out / 'traces.csv.gz', traces)
        write_json(out / 'complete.json', dict(label=label, checkpoint=checkpoint,
                   checkpoint_sha256=digest(checkpoint) if checkpoint else None,
                   selection_sha256=digest(root / 'selection.json'),
                   hashes={str(p.resolve()): digest(p) for p in out.iterdir() if p.is_file()}))
        print(json.dumps(dict(evaluated=label, split=split, cases=len(cases))), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('prepare', 'worker', 'select', 'test', 'known'))
    p.add_argument('--output', required=True); p.add_argument('--smoke', action='store_true')
    p.add_argument('--n', type=int, choices=(1, 8), default=1); p.add_argument('--run', type=int, default=0)
    p.add_argument('--stop-after', type=int)
    args = p.parse_args()
    activate_runtime(ORIGINAL / '.venv/pinn_tf216')
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    if args.command == 'prepare':
        prepare(args.output, args.smoke)
    elif args.command == 'worker':
        train(args.output, args.n, args.run, args.stop_after)
    elif args.command == 'select':
        select(args.output)
    else:
        evaluate(args.output, args.command)


if __name__ == '__main__':
    main()
