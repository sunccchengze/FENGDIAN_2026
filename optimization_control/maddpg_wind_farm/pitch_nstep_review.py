"""Recompute the bounded n-step trial; no parameter selection or extra training."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import gzip
import json
from pathlib import Path
from copy import deepcopy
from .fixed_pinn_demo import activate_runtime, digest
from .pitch_cross_wind_diagnostic import ORIGINAL, write_csv, write_json, read_csv, error_parts
from .pitch_nstep_trial import read_json, frozen, verify, derived, bank


def exact(a, b):
    import numpy as np
    import torch
    if isinstance(a, torch.Tensor):
        assert torch.equal(a, b)
    elif isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b)
    elif isinstance(a, dict):
        assert a.keys() == b.keys()
        for k in a:
            exact(a[k], b[k])
    elif isinstance(a, (tuple, list)):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            exact(x, y)
    else:
        assert a == b


def training_state(agent):
    import torch
    return dict(**{k: deepcopy(getattr(agent, k).state_dict()) for k in ('actors', 'critics', 'target_actors', 'target_critics')},
                **{k: [deepcopy(o.state_dict()) for o in getattr(agent, k)] for k in ('actor_optimizers', 'critic_optimizers')},
                replay=agent.replay.state_dict(), rng=deepcopy(agent.rng.bit_generator.state), updates=agent.updates)


def recovery_check(root):
    """Real interrupted smoke forks, 128 steps each; never retained for formal training."""
    import numpy as np
    from .algorithm import MADDPG
    from .nstep_algorithm import NStepMADDPG
    from .stable_workflow import Exploration
    from .workflow import build_env
    from ..environments.farm_inflow import InflowTrace
    root = Path(root).resolve(); s = frozen(root)
    out = root / 'recovery_audit'; out.mkdir(exist_ok=False)
    checks = []
    # Three genuine frozen parents: original n=1 update is exactly equivalent.
    for run in range(3):
        parent = s['parents'][str(run)]['checkpoint']
        original, _ = MADDPG.load(parent); candidate, _ = NStepMADDPG.inherit(parent, 1)
        exact(original.update(), candidate.update())
        for key in ('actors', 'critics', 'target_actors', 'target_critics'):
            exact(getattr(original, key).state_dict(), getattr(candidate, key).state_dict())
        for key in ('actor_optimizers', 'critic_optimizers'):
            for a, b in zip(getattr(original, key), getattr(candidate, key)):
                exact(a.state_dict(), b.state_dict())
        checks.append(dict(check='real_parent_n1_exact_update', run=run, passed=True, env_steps=0))
    env = build_env(s['base_config'])
    for n in (1, 8):
        commit_path = sorted((root / f'n{n}_run0/step_00000512').glob('attempt_*/commit.json'))[-1]
        commit = read_json(commit_path); verify(commit['hashes'])
        trajectories, states = [], []
        design = next(r for r in read_csv(root / 'training_manifest.csv') if int(r['episode_index']) == 4)
        for branch in range(2):
            agent, meta = NStepMADDPG.load(commit['checkpoint'], n)
            noise = Exploration(int(derived(3, 0).generate_state(1)[0]), [0., .03, 0.], [10., 3., 5.], 1., 'white', .2)
            noise.load_state_dict(meta['noise']); noise.reset()
            trace = InflowTrace.load(design['path'])
            env.initial = np.array(env.config['initial_operating_point'], dtype=float); env.initial[1] = float(design['initial_pitch_rad'])
            obs, _ = env.reset(seed=42, options=dict(wind_trajectory=trace.values, target_w=float(design['target_w'])))
            rows = []
            for t in range(128):
                a = env.project_action(np.clip(agent.act(obs) + noise.sample((512 + t) / 1024), -1, 1)).astype(np.float32)
                nxt, reward, done, _, info = env.step(a)
                agent.replay.add(obs, info['executed_action'], reward, nxt, done)
                if (513 + t) % 2 == 0:
                    agent.update()
                rows.append(np.r_[nxt.ravel(), info['executed_action'].ravel(), reward]); obs = nxt
            trajectories.append(np.stack(rows)); states.append(training_state(agent))
            agent.save(out / f'n{n}_branch{branch}.pth', dict(source=commit['checkpoint'], audit_only=True, env_steps=128, noise=noise.state_dict()))
        exact(trajectories[0], trajectories[1]); exact(states[0], states[1])
        checks.append(dict(check='real_512_resume_two_128_step_forks', run=n, passed=True, env_steps=256))
    write_csv(out / 'metrics.csv', checks)
    write_json(out / 'summary.txt', dict(seed=42, all_exact=True, real_audit_training_env_steps=512,
               not_formal_training=True, parent_files_unchanged=True))
    print(json.dumps(checks), flush=True)


def audit_training(root):
    import numpy as np
    from .nstep_algorithm import NStepMADDPG
    root = Path(root).resolve(); s = frozen(root)
    rows, details, validation_groups = [], {}, []
    max_reward = 0.; saved_steps = 0; interrupted = []
    for n in s['arms']:
        for run in s['run_ids']:
            job = root / f'n{n}_run{run}'; result = read_json(job / 'result.json'); verify(result['hashes'])
            records, losses, explored = [], [], []
            commits = sorted(job.glob('step_*/attempt_*/commit.json'))
            assert [read_json(p)['step'] for p in commits] == list(range(0, s['steps_per_job'] + 1, 128))
            for path in commits:
                commit = read_json(path); verify(commit['hashes'])
                if commit['step'] == 0:
                    continue
                directory = path.parent; d = np.load(directory / 'training.npz')
                assert len(d['obs']) == 128
                np.testing.assert_array_equal(d['obs'][1:], d['next_obs'][:-1])
                np.testing.assert_array_equal(d['actions'], d['next_obs'][:, :, 5:8])
                expected_done = np.zeros((128, 1), bool); expected_done[-1] = True
                np.testing.assert_array_equal(d['terminated'], expected_done)
                cost = np.mean((d['actions'] - d['obs'][:, :, 5:8])**2, axis=(1, 2))
                e = s['base_config']['environment']
                expected_reward = e['reward_scale'] * (-d['next_obs'][:, 0, 9]**2 - e['action_change_weight'] * cost)
                difference = np.max(np.abs(d['rewards'] - expected_reward[:, None])); max_reward = max(max_reward, float(difference))
                np.testing.assert_allclose(d['rewards'], np.repeat(expected_reward[:, None], 3, 1), atol=5e-6, rtol=4e-6)
                width = np.array(e['action_high']) - e['action_low']
                change = (d['next_obs'][:, :, 3:5] - d['obs'][:, :, 3:5]) * width[1:] / 2
                assert np.all(np.max(np.abs(change), axis=(0, 1)) <= np.array(e['rate_limits'][1:]) + 1e-6)
                a, meta = None, None
                losses.extend(r for r in read_csv(directory / 'losses.csv') if 'step' in r)
                explored.append(d['exploration']); records.append(d['obs'][:, :, 8].copy())
                saved_steps += 128
            for directory in job.glob('step_*/attempt_*'):
                if not (directory / 'commit.json').exists():
                    interrupted.append(str(directory))
            initial, imeta = NStepMADDPG.load(result['initial'], n)
            parent, pmeta = NStepMADDPG.inherit(s['parents'][str(run)]['checkpoint'], n)
            exact(training_state(initial), training_state(parent))
            final, fmeta = NStepMADDPG.load(result['final'], n)
            for optimizers, expected in ((final.actor_optimizers, .0001), (final.critic_optimizers, .001)):
                assert all(g['lr'] == expected for o in optimizers for g in o.param_groups)
            assert fmeta['step'] == s['steps_per_job'] and result['added_updates'] == len(losses)
            assert sum(result['m_histogram']) == len(losses) * 64
            exact(final.replay.m_histogram.tolist(), result['m_histogram'])
            details[n, run] = dict(losses=losses, exploration=np.concatenate(explored), targets=np.concatenate(records),
                                  replay_rng=deepcopy(final.replay.rng.bit_generator.state), noise_rng=fmeta['noise']['rng'])
            rows.append(dict(n=n, run=run, saved_steps=fmeta['step'], committed_episode_shards=len(commits) - 1,
                             new_updates=result['added_updates'], selected_step=result['selected_step'],
                             initial_state_exact=True, m_histogram=json.dumps(result['m_histogram']),
                             final_over_selected=result['final_over_selected']))
            for state in ('initial', 'selected', 'final'):
                validation_rows = read_csv(Path(result[state]).with_name('validation_metrics.csv'))
                for family in ('routine', *FAMILIES):
                    part = [r for r in validation_rows if r['family'] == family] if family != 'routine' else validation_rows
                    validation_groups.append(dict(n=n, run=run, state=state, family=family, cases=len(part),
                                                  mean_rmse_w=float(np.mean([float(r['rmse_w']) for r in part]))))
    for run in s['run_ids']:
        a, b = details[1, run], details[8, run]
        exact(a['exploration'], b['exploration']); exact(a['targets'], b['targets'])
        exact(a['replay_rng'], b['replay_rng']); exact(a['noise_rng'], b['noise_rng'])
        assert [r['sample_indices_sha256'] for r in a['losses']] == [r['sample_indices_sha256'] for r in b['losses']]
    write_csv(root / 'training_audit.csv', rows)
    write_csv(root / 'validation_groups.csv', validation_groups)
    audit = dict(seed=42, saved_formal_training_steps=saved_steps, paired_exploration_targets_anchors_exact=True,
                 maximum_reward_reconstruction_difference=max_reward, protected_files=len(s['protected_hashes']),
                 protected_files_unchanged=True, interrupted_uncommitted_attempts=interrupted,
                 max_possible_recomputed_steps=len(interrupted) * 128, all_complete=True)
    write_json(root / 'training_verification.json', audit)
    if s['mode'] == 'smoke':
        write_csv(root / 'metrics.csv', rows)
        write_json(root / 'summary.txt', dict(seed=42, status='smoke_complete', saved_training_steps=saved_steps,
                   paired_checks_passed=True, test_locked=True, formal_training=False,
                   recovery_audit='recovery_audit/summary.txt'))
    print(json.dumps(audit), flush=True)
    return audit


def review(root):
    import numpy as np
    root = Path(root).resolve(); s = frozen(root); selection = read_json(root / 'selection.json')
    validation_count = validation_trace_count = 0
    for result in selection['results']:
        verify(result['hashes'])
        job = root / f'n{result["n"]}_run{result["run"]}'
        paths = sorted(job.glob('step_*/attempt_*/validation_metrics.csv'))
        assert len(paths) == 5
        for path, history in zip(paths, result['history']):
            part = read_csv(path)
            with gzip.open(path.with_name('validation_traces.csv.gz'), 'rt', encoding='utf-8') as f:
                grouped = defaultdict(list)
                for t in csv.DictReader(f):
                    grouped[t['case_id']].append(float(t['error_w']))
                    validation_trace_count += 1
            assert len(part) == 18
            for r in part:
                for key, value in error_parts(grouped[r['case_id']]).items():
                    assert value == float(r[key])
                validation_count += 1
            assert float(np.mean([float(r['rmse_w']) for r in part])) == history['rmse_w']
        best = min(result['history'], key=lambda r: r['rmse_w'])
        assert best['step'] == result['selected_step']
    metrics, paired, aggregates, evaluation_audit = [], [], [], []
    common_wind = {}
    expected_labels = {f'n{n}_run{k}_{state}' for n in (1, 8) for k in (0, 1, 2) for state in ('initial', 'selected', 'final')} | {'p', 'pi'}
    for split in ('test', 'known'):
        assert {p.name for p in (root / 'evaluations' / split).iterdir()} == expected_labels
        for base in sorted((root / 'evaluations' / split).iterdir()):
            complete = sorted(base.glob('attempt_*/complete.json'))[-1]
            record = read_json(complete); verify(record['hashes'])
            assert record['selection_sha256'] == digest(root / 'selection.json')
            directory = complete.parent
            part = read_csv(directory / 'metrics.csv')
            assert len(part) == 44 and len({r['case_id'] for r in part}) == 44
            with gzip.open(directory / 'traces.csv.gz', 'rt', encoding='utf-8', newline='') as f:
                traces = list(csv.DictReader(f))
            grouped = defaultdict(list)
            for row in traces:
                grouped[row['case_id']].append(row)
            maximum = 0.
            for row in part:
                assert len(grouped[row['case_id']]) == 128
                fingerprint = [(t['decision_step'], t['response_step'], t['target_w'], t['initial_pitch_rad'], t['decision_wind_m_s'], t['response_wind_m_s']) for t in grouped[row['case_id']]]
                key = split, row['case_id']
                if key in common_wind:
                    assert fingerprint == common_wind[key]
                else:
                    common_wind[key] = fingerprint
                values = [float(t['error_w']) for t in grouped[row['case_id']]]
                recomputed = error_parts(values)
                for k, v in recomputed.items():
                    maximum = max(maximum, abs(v - float(row[k])))
                label = base.name
                tags = dict(evaluation=split, label=label, n=int(label[1]) if label.startswith('n') else 0,
                            run=int(label.split('_')[1][3:]) if label.startswith('n') else -1,
                            state=label.split('_')[-1] if label.startswith('n') else label)
                numeric = {k: float(v) if k not in ('case_id', 'split', 'family') else v for k, v in row.items()}
                metrics.append(dict(**tags, **numeric))
            assert maximum == 0.
            evaluation_audit.append(dict(evaluation=split, label=base.name, cases=len(part), trajectory_rows=len(traces), maximum_metric_difference=maximum))
    lookup = {(r['evaluation'], r['label'], r['case_id']): r for r in metrics}
    previous = read_csv(Path(__file__).resolve().parents[1] / 'experiments/20261027_pitch_cross_wind_diagnostic/metrics.csv')
    maximum_known_parent_difference = max(abs(lookup['known', f'n1_run{k}_initial', r['case_id']]['rmse_w'] - float(r['rmse_w']))
         for k in (0, 1, 2) for r in previous if r['controller'] == f'parent_{k}')
    assert maximum_known_parent_difference <= 20.
    for evaluation in ('test', 'known'):
        for run in (0, 1, 2):
            initial1 = [r for r in metrics if r['evaluation'] == evaluation and r['label'] == f'n1_run{run}_initial']
            for r in initial1:
                assert r['rmse_w'] == lookup[evaluation, f'n8_run{run}_initial', r['case_id']]['rmse_w']
    for r in metrics:
        if not r['n']:
            continue
        item = dict(r)
        for name, label in (('p', 'p'), ('pi', 'pi'), ('parent', f'n{r["n"]}_run{r["run"]}_initial'), ('n1', f'n1_run{r["run"]}_{r["state"]}')):
            reference = lookup[r['evaluation'], label, r['case_id']]
            item[f'delta_{name}_rmse_w'] = r['rmse_w'] - reference['rmse_w']
        paired.append(item)
    for evaluation in ('test', 'known'):
        for label in sorted({r['label'] for r in metrics}):
            part = [r for r in metrics if r['evaluation'] == evaluation and r['label'] == label]
            for family in ('all_44', 'routine', *FAMILIES, 'low_wind_stress'):
                group = part if family == 'all_44' else ([r for r in part if r['family'] in FAMILIES] if family == 'routine' else [r for r in part if r['family'] == family])
                aggregates.append(dict(evaluation=evaluation, label=label, family=family, cases=len(group),
                                       mean_rmse_w=float(np.mean([r['rmse_w'] for r in group])),
                                       pooled_rmse_w=float(np.sqrt(np.mean([r['mse_w2'] for r in group])))))
    cross = []
    for state in ('initial', 'selected', 'final'):
        for family in ('all_44', 'routine', *FAMILIES, 'low_wind_stress'):
            for n in (1, 8):
                a = [r for r in aggregates if r['evaluation'] == 'test' and r['family'] == family and r['label'] in [f'n{n}_run{k}_{state}' for k in (0, 1, 2)]]
                means = [r['mean_rmse_w'] for r in a]
                pooled = [r['pooled_rmse_w'] for r in a]
                cross.append(dict(n=n, state=state, family=family, mean_rmse_w=float(np.mean(means)), std_across_runs_w=float(np.std(means, ddof=1)),
                                  pooled_rmse_w=float(np.sqrt(np.mean(np.array(pooled)**2))), std_pooled_across_runs_w=float(np.std(pooled, ddof=1))))
    degradation = []
    for r in paired:
        if r['state'] == 'final':
            selected = lookup[r['evaluation'], f'n{r["n"]}_run{r["run"]}_selected', r['case_id']]
            degradation.append(dict(evaluation=r['evaluation'], n=r['n'], run=r['run'], case_id=r['case_id'], family=r['family'],
                selected_rmse_w=selected['rmse_w'], final_rmse_w=r['rmse_w'], delta_final_selected_w=r['rmse_w'] - selected['rmse_w'],
                final_over_selected=r['rmse_w'] / selected['rmse_w']))
    grouped_differences = []
    for n in (1, 8):
        for state in ('initial', 'selected', 'final'):
            for family in ('all_44', 'routine', *FAMILIES, 'low_wind_stress'):
                part = [r for r in paired if r['evaluation'] == 'test' and r['n'] == n and r['state'] == state and
                        (True if family == 'all_44' else (r['family'] in FAMILIES if family == 'routine' else r['family'] == family))]
                for reference in ('p', 'pi', 'parent', 'n1'):
                    values = [r[f'delta_{reference}_rmse_w'] for r in part]
                    per_run = [float(np.mean([r[f'delta_{reference}_rmse_w'] for r in part if r['run'] == k])) for k in (0, 1, 2)]
                    grouped_differences.append(dict(n=n, state=state, family=family, reference=reference, paired_slots=len(values),
                        mean_delta_rmse_w=float(np.mean(values)), std_delta_across_run_means_w=float(np.std(per_run, ddof=1)),
                        improved_slots=sum(v < 0 for v in values), worst_delta_rmse_w=max(values)))
    get = lambda label, family: next(r['mean_rmse_w'] for r in aggregates if r['evaluation'] == 'test' and r['label'] == label and r['family'] == family)
    ramp_n1 = [get(f'n1_run{k}_selected', 'ramp') for k in (0, 1, 2)]
    ramp_n8 = [get(f'n8_run{k}_selected', 'ramp') for k in (0, 1, 2)]
    parent_ramp = [get(f'n1_run{k}_initial', 'ramp') for k in (0, 1, 2)]
    gate = dict(ramp_relative_improvement=1 - float(np.mean(ramp_n8)) / float(np.mean(ramp_n1)),
                ramp_improved_runs=sum(a < b for a, b in zip(ramp_n8, ramp_n1)),
                ramp_improvement_over_parent=1 - float(np.mean(ramp_n8)) / float(np.mean(parent_ramp)),
                ramp_improved_over_parent_runs=sum(a < b for a, b in zip(ramp_n8, parent_ramp)),
                other_family_ratios={f'run{k}_{f}': get(f'n8_run{k}_selected', f) / get(f'n1_run{k}_selected', f) for k in (0, 1, 2) for f in ('stationary', 'gust')},
                final_over_selected={f'n{r["n"]}_run{r["run"]}': get(f'n{r["n"]}_run{r["run"]}_final', 'routine') / get(f'n{r["n"]}_run{r["run"]}_selected', 'routine') for r in selection['results']},
                validation_final_over_selected={f'n{r["n"]}_run{r["run"]}': r['final_over_selected'] for r in selection['results']},
                n8_selected_after_initial=sum(r['n'] == 8 and r['selected_step'] > 0 for r in selection['results']),
                selected_initial_jobs=[f'n{r["n"]}_run{r["run"]}' for r in selection['results'] if r['selected_step'] == 0])
    gate['passed'] = bool(gate['ramp_relative_improvement'] >= .05 and gate['ramp_improved_runs'] >= 2 and max(gate['other_family_ratios'].values()) <= 1.05 and max(gate['final_over_selected'].values()) <= 1.25 and max(gate['validation_final_over_selected'].values()) <= 1.25)
    write_csv(root / 'metrics.csv', metrics); write_csv(root / 'paired.csv', paired)
    write_csv(root / 'aggregate.csv', aggregates); write_csv(root / 'cross_stream.csv', cross)
    write_csv(root / 'checkpoint_degradation.csv', degradation); write_csv(root / 'paired_groups.csv', grouped_differences)
    write_csv(root / 'evaluation_audit.csv', evaluation_audit)
    write_json(root / 'acceptance.json', gate)
    write_json(root / 'evaluation_verification.json', dict(seed=42, metrics=len(metrics), trajectories=sum(r['trajectory_rows'] for r in evaluation_audit),
               validation_metric_rows=validation_count, validation_trace_rows=validation_trace_count, all_validation_scores_and_selections_recomputed=True,
               maximum_recomputed_metric_difference=0., maximum_known_parent_rmse_difference_w=maximum_known_parent_difference,
               all_labels_and_44_cases_present=True, paired_weather_targets_initials_exact=True, initial_arms_rmse_exact=True,
               test_used_for_selection=False, selection_sha256=digest(root / 'selection.json')))
    write_json(root / 'summary.txt', dict(seed=42, status='complete', formal_training_steps=98304, smoke_steps=2048,
               recovery_audit_training_env_steps=512, test_used_for_selection=False, physical_validation=False,
               acceptance=gate, selection_sha256=digest(root / 'selection.json'), metrics=len(metrics),
               evaluation_trajectory_rows=sum(r['trajectory_rows'] for r in evaluation_audit),
               source_files_unchanged=True, off_policy_bias_acknowledged=True))
    print(json.dumps(dict(cross_stream=cross, acceptance=gate), indent=2), flush=True)


FAMILIES = ('stationary', 'ramp', 'gust')


def figures(root, figure_dir='figures'):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    root = Path(root).resolve(); out = (root / figure_dir).resolve()
    if out.parent != root:
        raise ValueError('figure directory must be an immediate child of experiment root')
    out.mkdir(exist_ok=False)
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    s = read_json(root / 'selection.json')
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for run, ax in enumerate(axes):
        for n, color in ((1, '#2468a0'), (8, '#ce6835')):
            r = next(r for r in s['results'] if r['n'] == n and r['run'] == run)
            ax.plot([v['step'] for v in r['history']], [v['rmse_w'] / 1000 for v in r['history']], 'o-', color=color, label=f'n={n}')
            best = next(v for v in r['history'] if v['step'] == r['selected_step'])
            ax.scatter([best['step']], [best['rmse_w'] / 1000], marker='*', s=160, color=color)
        ax.set(title=f'派生流 {run}', xlabel='新增训练环境步'); ax.grid(alpha=.2); ax.legend()
    axes[0].set_ylabel('18场完整回合验证RMSE均值 [kW]')
    fig.suptitle('仅验证选模；星号为selected，包含initial'); fig.tight_layout(); fig.savefig(out / 'validation.png', dpi=160); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for run in (0, 1, 2):
        r = next(r for r in s['results'] if r['n'] == 8 and r['run'] == run)
        counts = np.array(r['m_histogram'][1:], dtype=float)
        ax.bar(np.arange(1, 9) + (run - 1) * .23, counts / counts.sum(), width=.23, label=f'流{run}')
    ax.set(xticks=range(1, 9), xlabel='真实可用回报长度 m', ylabel='全部采样锚点的比例', title='n=8实际使用长度；终止/尾部缩短，锚点不丢弃')
    ax.legend(); ax.grid(axis='y', alpha=.2); fig.tight_layout(); fig.savefig(out / 'effective_m.png', dpi=160); plt.close(fig)
    cross = read_csv(root / 'cross_stream.csv')
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    families = ('stationary', 'ramp', 'gust', 'routine', 'low_wind_stress')
    for ax, state in zip(axes, ('selected', 'final')):
        for ni, n in enumerate((1, 8)):
            rows = [next(r for r in cross if r['state'] == state and int(r['n']) == n and r['family'] == f) for f in families]
            ax.errorbar(np.arange(5) + (ni - .5) * .12, [float(r['mean_rmse_w']) / 1000 for r in rows],
                        yerr=[float(r['std_across_runs_w']) / 1000 for r in rows], fmt='o', capsize=4, label=f'n={n} 均值±跨流SD')
        agg = read_csv(root / 'aggregate.csv')
        for label, marker in (('p', '_'), ('pi', 'x')):
            values = [next(float(r['mean_rmse_w']) / 1000 for r in agg if r['evaluation'] == 'test' and r['label'] == label and r['family'] == f) for f in families]
            ax.plot(range(5), values, marker=marker, linestyle=':', label=label.upper())
        ax.set(title=state, xticks=range(5), xticklabels=['平稳', '慢变', '阵风', '常规总体', '低风压力'], ylabel='完整回合RMSE [kW]'); ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.suptitle('新独立测试；压力单列，所有困难样本保留'); fig.tight_layout(); fig.savefig(out / 'independent_test.png', dpi=160); plt.close(fig)
    paired = [r for r in read_csv(root / 'paired.csv') if r['evaluation'] == 'test' and r['state'] == 'selected' and int(r['n']) == 8]
    fig, axes = plt.subplots(1, 3, figsize=(16, 10), sharey=True)
    cases = sorted(set(r['case_id'] for r in paired))
    for run, ax in enumerate(axes):
        part = {r['case_id']: r for r in paired if int(r['run']) == run}
        data = np.array([[float(part[c][f'delta_{ref}_rmse_w']) / 1000 for ref in ('parent', 'n1', 'pi')] for c in cases])
        limit = max(1., np.max(np.abs(data)))
        im = ax.imshow(data, aspect='auto', cmap='RdBu_r', vmin=-limit, vmax=limit)
        ax.set(title=f'流{run}：n8 selected配对差', xticks=range(3), xticklabels=['相对父', '相对n1', '相对PI'], yticks=range(len(cases)), yticklabels=cases)
        ax.tick_params(axis='y', labelsize=6); fig.colorbar(im, ax=ax, label='ΔRMSE [kW]；负值改善')
    fig.tight_layout(); fig.savefig(out / 'all_test_paired.png', dpi=170); plt.close(fig)
    # Fixed representatives selected before reading outcomes: ramp low/high, stationary, gust, stress.
    test_cases = [c for c, _ in bank(root, 'test')]
    representatives = [next(c['id'] for c in test_cases if c['family'] == f and c['target_w'] == target and c['initial_pitch_rad'] == .055) for f, target in
                       (('ramp', 2.65e6), ('ramp', 3.95e6), ('stationary', 3.25e6), ('gust', 3.25e6), ('low_wind_stress', 4.55e6))]
    known_rows = [r for r in read_csv(root / 'metrics.csv') if r['evaluation'] == 'known' and r['label'] == 'n8_run0_selected']
    weak = next(r['case_id'] for r in known_rows if r['family'] == 'ramp' and float(r['target_w']) == 3450000 and float(r['initial_pitch_rad']) == .04 and r['split'] == 'validation')
    displayed = [('test', c) for c in representatives] + [('known', weak)]
    controllers = ('n1_run0_initial', 'n1_run0_selected', 'n8_run0_selected', 'n8_run0_final', 'p', 'pi')
    colors = dict(zip(controllers, plt.rcParams['axes.prop_cycle'].by_key()['color']))
    for index, (evaluation, case) in enumerate(displayed):
        fig, axes = plt.subplots(6, 1, figsize=(13, 15), sharex=True)
        for label in controllers:
            directory = sorted((root / 'evaluations' / evaluation / label).glob('attempt_*/complete.json'))[-1].parent
            with gzip.open(directory / 'traces.csv.gz', 'rt', encoding='utf-8') as f:
                rows = [r for r in csv.DictReader(f) if r['case_id'] == case]
            t = [int(r['response_step']) for r in rows]
            if label == 'pi':
                axes[0].plot(t, [float(r['response_wind_m_s']) for r in rows], 'k', label='入口风速')
            axes[1].plot(t, [float(r['error_w']) / 1000 for r in rows], color=colors[label], label=label)
            for i in range(3):
                axes[2 + i].plot(t, [float(r[f'pitch_actual_{i}']) for r in rows], color=colors[label], label=label + ' 实际')
                axes[2 + i].plot(t, [float(r[f'pitch_command_{i}']) for r in rows], ':', color=colors[label], alpha=.55)
            axes[5].plot(t, [sum(float(r[f'pitch_rate_limited_{i}']) for i in range(3)) / 3 for r in rows], color=colors[label], label=label)
        for ax, ylabel in zip(axes, ('风速 [m/s]', '功率误差 [kW]', 'T1桨距 [rad]', 'T2桨距 [rad]', 'T3桨距 [rad]', '速率饱和比例')):
            ax.set_ylabel(ylabel); ax.grid(alpha=.2)
        axes[1].axhline(0, color='k', linewidth=.7); axes[1].legend(ncol=3, fontsize=8)
        axes[-1].set_xlabel('完整回合响应时间 [s]；桨距虚线为目标，实线为实际')
        fig.suptitle(case + f' | {evaluation} | 固定代理模型 | 流0'); fig.tight_layout(); fig.savefig(out / f'full_series_{index}.png', dpi=140); plt.close(fig)
    metric = [r for r in read_csv(root / 'metrics.csv') if r['evaluation'] == 'test' and r['family'] == 'ramp' and int(r['run']) == 0 and r['state'] in ('initial', 'selected', 'final')]
    fig, ax = plt.subplots(figsize=(12, 5))
    labels = sorted(set(r['label'] for r in metric))
    bias2 = [np.mean([float(r['mean_error_w'])**2 for r in metric if r['label'] == label]) / 1e6 for label in labels]
    variance = [np.mean([float(r['variance_w2']) for r in metric if r['label'] == label]) / 1e6 for label in labels]
    ax.bar(labels, bias2, label='平均有符号误差²'); ax.bar(labels, variance, bottom=bias2, label='误差方差')
    ax.set(ylabel='场景平均MSE [(kW)²]', title='慢变新测试误差分解（流0）；MSE=bias²+variance'); ax.legend(); ax.tick_params(axis='x', rotation=20)
    fig.tight_layout(); fig.savefig(out / 'error_decomposition.png', dpi=160); plt.close(fig)
    all_metrics = read_csv(root / 'metrics.csv')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), sharey=True)
    labels = ('n1_run0_initial', 'n8_run0_selected', 'pi')
    for ax, pitch in zip(axes, (.025, .04, .055)):
        part = [r for r in all_metrics if r['evaluation'] == 'known' and r['split'] == 'validation' and r['family'] == 'ramp' and
                float(r['target_w']) == 3450000 and float(r['initial_pitch_rad']) == pitch]
        points = [next(r for r in part if r['label'] == label) for label in labels]
        a = np.array([float(r['bias_squared_w2']) / 1e6 for r in points]); b = np.array([float(r['variance_w2']) / 1e6 for r in points])
        ax.bar(range(3), a, label='bias²'); ax.bar(range(3), b, bottom=a, label='variance')
        ax.set(title=f'初始桨距 {pitch} rad', xticks=range(3), xticklabels=['父策略', 'n8选中', 'PI'])
        for i, r in enumerate(points):
            ax.text(i, a[i] + b[i], f"RMSE {float(r['rmse_w']) / 1000:.1f}", ha='center', va='bottom', fontsize=9)
    axes[0].set_ylabel('完整回合MSE [(kW)²]'); axes[-1].legend()
    fig.suptitle('已知薄弱组：流0、慢变3.45MW；不是新独立样本'); fig.tight_layout(); fig.savefig(out / 'known_weak_decomposition.png', dpi=160); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('command', choices=('recovery', 'training', 'review', 'figures')); ap.add_argument('--output', required=True)
    ap.add_argument('--figure-dir', default='figures')
    args = ap.parse_args(); activate_runtime(ORIGINAL / '.venv/pinn_tf216')
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    if args.command == 'figures':
        figures(args.output, args.figure_dir)
    else:
        {'recovery': recovery_check, 'training': audit_training, 'review': review}[args.command](args.output)


if __name__ == '__main__':
    main()
