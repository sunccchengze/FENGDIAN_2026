"""Post-selection delivery audit from saved artifacts; no training or plant calls."""
import argparse
from collections import defaultdict
from pathlib import Path


def audit(root):
    import numpy as np
    import torch
    from .frozen_speed_training import context
    from .anchor_closeout import read_json, read_csv, write_json, write_csv, sha

    saved, protocol = context(root)
    selection = read_json(root / 'selection.json')
    metrics = read_csv(root / 'test/metrics.csv')
    traces = read_csv(root / 'test/trajectories.csv')
    groups = defaultdict(list)
    for row in traces:
        groups[(row['arm'], int(row['run_id']), row['controller'], row['case_id'])].append(row)
    assert len(metrics) == len(groups) == 660 and len(traces) == 84480
    numeric = [k for k in traces[0] if k not in ('arm', 'run_id', 'controller', 'case_id', 'split', 'family')]
    zero_rows = 0
    for (arm, run, label, case), rows in groups.items():
        if label in ('zero_selected', 'zero_final'):
            parent = groups[('speed', run, 'parent', case)]
            np.testing.assert_array_equal([[float(r[k]) for k in numeric] for r in rows],
                                          [[float(r[k]) for k in numeric] for r in parent])
            zero_rows += len(rows)
    bank = read_json(root / 'bank/manifest.json')
    cases = {c['id']: c for c in bank['cases'] if c['split'] == 'test'}
    winds = {}
    for case in cases.values():
        path = root / 'bank' / case['path']
        assert sha(path) == case['csv_sha256']
        # Preserve the environment's explicit float32 disturbance conversion.
        winds[case['id']] = np.loadtxt(path, delimiter=',', skiprows=1)[:, 1:4].astype(np.float32)
    cfg = saved['base_config']['environment']
    rated = np.asarray(saved['base_config']['plant']['rated_power_w'], dtype=float)
    maximum_rate = np.zeros(3)
    max_float64_sum_delta = 0.
    control_rows = []
    policies = {}
    from .frozen_speed_algorithm import load_policy
    for (arm, run, label, case_id), rows in groups.items():
        case = cases[case_id]
        wind = winds[case_id]
        assert len(rows) == 128 and [int(r['step']) for r in rows] == list(range(1, 129))
        np.testing.assert_array_equal([[float(r[k]) for k in ('wind_m_s', 'direction_rad', 'ti')] for r in rows], wind[1:])
        assert all(float(r['target_w']) == case['target_w'] and float(r['initial_pitch_rad']) == case['initial_pitch_rad'] for r in rows)
        previous = np.tile([float(wind[0, 1]) + cfg['initial_operating_point'][0],
                            case['initial_pitch_rad'], cfg['initial_operating_point'][2]], (3, 1))
        for r in rows:
            current = np.asarray([[float(r[f'heading_{i}_rad']), float(r[f'pitch_{i}']), float(r[f'speed_{i}'])] for i in (1, 2, 3)])
            rate = np.max(np.abs(current - previous), axis=0) / cfg['dt_s']
            maximum_rate = np.maximum(maximum_rate, rate)
            assert np.all(rate <= np.asarray(cfg['rate_limits']) + 1e-7)
            commands = np.asarray([[float(r[f'command_{i}_{j}']) for j in range(3)] for i in (1, 2, 3)])
            assert np.abs(commands).max() <= 1 + 1e-7
            assert float(r['error_w']) == float(r['farm_power_w']) - float(r['target_w'])
            max_float64_sum_delta = max(max_float64_sum_delta, abs(sum(float(r[f'power_{i}_w']) for i in (1, 2, 3)) - float(r['farm_power_w'])))
            previous = current
        if arm == 'speed' and label in ('selected', 'final'):
            parent = groups[('speed', run, 'parent', case_id)]
            diffs = np.asarray([[[float(a[k]) - float(b[k]) for k in (f'pitch_{i}', f'speed_{i}')] for i in (1, 2, 3)] for a, b in zip(rows, parent)])
            # Reconstruct observations at saved steps 1..127 and verify their
            # complete policy actions against commands at steps 2..128 before
            # interpreting raw head outputs. The initial query is not saved.
            observations = []
            for r in rows[:-1]:
                powers = np.asarray([float(r[f'power_{i}_w']) for i in (1, 2, 3)], np.float32)
                effective = np.asarray([float(r[f'ueff_{i}_m_s']) for i in (1, 2, 3)], np.float32)
                applied = np.asarray([[float(r[f'{name}_{i}']) for name in ('gamma', 'pitch', 'speed')] for i in (1, 2, 3)])
                previous_commands = np.asarray([[float(r[f'command_{i}_{j}']) for j in range(3)] for i in (1, 2, 3)], np.float32)
                direction = np.float32(r['direction_rad'])
                global_values = [float(r['target_w']) / rated.sum(), float(r['error_w']) / rated.sum(),
                    np.float32(r['wind_m_s']) / cfg['wind_scale_m_s'], np.sin(direction), np.cos(direction),
                    np.float32(r['ti']), 1 - int(r['step']) / cfg['horizon']]
                observations.append(np.column_stack((powers / rated, effective / cfg['wind_scale_m_s'],
                    2 * (applied - cfg['action_low']) / (np.asarray(cfg['action_high']) - cfg['action_low']) - 1,
                    previous_commands, np.tile(global_values, (3, 1)))).astype(np.float32))
            key = (run, label)
            if key not in policies:
                result = next(r for r in selection['results'] if r['arm'] == 'speed' and r['run_id'] == run)
                policies[key] = load_policy(result[label])[0]
            agent = policies[key]
            x = torch.tensor(np.asarray(observations))
            with torch.no_grad():
                commands = torch.stack([agent.total_action(i, x[:, i]) for i in range(3)], dim=1).numpy()
                raw = torch.stack([agent.speed_heads[i](x[:, i]).squeeze(-1) for i in range(3)], dim=1).numpy()
            actual = np.asarray([[[float(r[f'command_{i}_{j}']) for j in range(3)] for i in (1, 2, 3)] for r in rows[1:]])
            action_error = float(np.max(np.abs(commands - actual)))
            assert action_error <= 2e-6
            control_rows.append(dict(run_id=run, controller=label, case_id=case_id, family=case['family'],
                applied_pitch_difference_rms_rad=float(np.sqrt(np.mean(diffs[..., 0] ** 2))),
                applied_speed_difference_rms_rad_s=float(np.sqrt(np.mean(diffs[..., 1] ** 2))),
                raw_head_mean=float(np.mean(raw)), raw_head_abs_mean=float(np.mean(np.abs(raw))),
                raw_head_near_limit_fraction=float(np.mean(np.abs(raw) >= .95)),
                diagnostic_observations=127, reconstructed_action_max_error=action_error,
                explanation='different closed-loop observations; frozen pitch mapping is unchanged'))
    paths = sorted((root / 'formal').glob('*/segment_*/*.pth'))
    assert len(paths) == 30
    checkpoint_rows = []
    for path in paths:
        state = torch.load(path, weights_only=False, map_location='cpu')
        m = state['metadata']
        result = next(r for r in selection['results'] if r['arm'] == m['arm'] and r['run_id'] == m['run_id'])
        checkpoint_rows.append(dict(arm=m['arm'], run_id=m['run_id'], step=m['step'], version=state['version'],
            checkpoint=str(path), sha256=sha(path), updates=state['updates'], parent_sha256=m['parent']['sha256'],
            initial=str(path) == result['initial'], selected=str(path) == result['selected'], final=str(path) == result['final']))
    for arm in ('baseline', 'speed'):
        result = next(r for r in selection['results'] if r['arm'] == arm)
        state = torch.load(result['final'], weights_only=False, map_location='cpu')
        write_json(root / f'normalization_{arm}.json', state['metadata']['normalization'])
    write_json(root / 'resolved_execution.json', dict(seed=42,
        formal_steps_per_job=protocol['steps_per_run'], smoke_steps_per_job=protocol['smoke_steps_per_arm'],
        formal_jobs=6, warmup_steps=protocol['warmup_steps'], update_every=protocol['update_every'],
        evaluation_every=protocol['eval_every'], evaluation_speed_radius_rad_s=.1,
        actor_and_head_lr=.0001, critic_lr=.001, tau=.01, gamma=.99, batch_size=64,
        inherited_critic_optimizer_and_replay=True, actor_moments_reset_both_arms=True,
        baseline_white_noise_active_column=1, baseline_white_noise_std=.03,
        speed_white_noise_active_column=2, speed_white_noise_std=.15,
        noise_decay_floor=.2, initial_speed_radius_rad_s=.02, radius_ramp_steps=4096,
        authoritative='frozen_speed.yaml protocol + frozen_speed_training.py; parent algorithm fields inherited',
        inherited_template_training_fields_not_read_by_this_driver=saved['base_config']['training']))
    write_csv(root / 'checkpoint_manifest.csv', checkpoint_rows)
    write_csv(root / 'test/channel_diagnostics.csv', control_rows)
    write_json(root / 'delivery_verification.json', dict(seed=42, surrogate_model_calls=0,
        saved_trajectory_policy_forward_diagnostics=True, training_steps_added=0,
        full_zero_speed_trace_rows_exact=zero_rows, compared_numeric_fields=numeric,
        case_groups_checked=660, wind_target_pitch_exact_after_environment_float32_conversion=True,
        first_step_inclusive_max_rates=maximum_rate.tolist(), max_float64_vs_saved_float32_power_sum_w=max_float64_sum_delta,
        formal_checkpoints=30, source_and_frozen_execution_hashes_passed=True,
        supplementary_script_sha256=sha(__file__)))
    summary = read_json(root / 'summary.txt')
    if 'full_verifier_summary' not in summary:
        full = root / 'summary_full.json'
        if full.exists():
            assert sha(full) == sha(root / 'summary.txt')
        else:
            full.write_bytes((root / 'summary.txt').read_bytes())
        compact = {k: v for k, v in summary.items() if k not in ('results', 'verification')}
        compact['results'] = [{k: v for k, v in r.items() if k not in ('config', 'hashes')} for r in summary['results']]
        compact.update(full_verifier_summary='summary_full.json', full_verifier_summary_sha256=sha(full),
            checkpoint_manifest='checkpoint_manifest.csv', normalization=['normalization_baseline.json', 'normalization_speed.json'],
            report='../../maddpg_wind_farm/FROZEN_SPEED_RESULTS.md',
            restore_audit='core_verification.json', delivery_audit='delivery_verification.json',
            limitations=['Synthetic surrogate software experiment only.', 'Selected remains initial in stream0.',
                        'Known low-wind pressure cases worsened in all three streams.',
                        'Discarded work after an interrupted process cannot be counted from durable artifacts.'],
            reproduce='See report. Frozen directory permits verify/test audits; a fresh output is required for full training.')
        write_json(root / 'summary.txt', compact)
    context(root)
    assert zero_rows == 15360
    print('Delivery audit complete: 660 cases, 15360 exact zero-speed rows, 30 checkpoints', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    # Match the frozen workflow's local runtime without modifying dependencies.
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    audit(Path(args.output).resolve())


if __name__ == '__main__':
    main()
