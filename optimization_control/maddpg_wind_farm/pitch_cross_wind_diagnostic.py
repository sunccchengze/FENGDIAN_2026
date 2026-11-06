"""Frozen pitch-only train/validation diagnosis; never opens an old test case."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import time

from .fixed_pinn_demo import activate_runtime, digest

ORIGINAL = Path('.')
SOURCE = ORIGINAL / 'optimization_control/experiments/20261023_progressive_random_control'
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / 'experiments/20261027_pitch_cross_wind_diagnostic'
PITCH = 'collective_pitch_reference_rad'


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8', newline='\n')


def write_csv(path, rows):
    rows = list(rows)
    if not rows:
        raise ValueError('empty result table')
    with Path(path).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def trend_feature(wind):
    """At t=0 use U0; early steps use U0, not future/padded unknown history."""
    import numpy as np
    wind = np.asarray(wind, dtype=float)
    return wind - wind[np.maximum(0, np.arange(len(wind)) - 4)]


def error_parts(errors):
    import numpy as np
    e = np.asarray(errors, dtype=float)
    if e.shape != (128,) or not np.isfinite(e).all():
        raise ValueError('all 128 finite response errors required')
    mse, bias, variance = float(np.mean(e**2)), float(e.mean()), float(e.var(ddof=0))
    return dict(rmse_w=mse**.5, mean_error_w=bias, error_std_w=variance**.5,
                mse_w2=mse, bias_squared_w2=bias**2, variance_w2=variance,
                bias_share=bias**2 / mse if mse else 0.,
                decomposition_residual_w2=mse-bias**2-variance)


def correlation(x, y):
    import numpy as np
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return 0.
    return float(np.corrcoef(x, y)[0, 1])


def forecast_check(winds):
    """Future wind is an offline label only. Fit train, then score validation."""
    import numpy as np
    rows, coefficients = [], []
    for ahead in (1, 4):
        samples = {}
        for split in ('train', 'validation'):
            samples[split] = []
            for case, trace in winds:
                if case['split'] != split:
                    continue
                u = trace.values[:, 0]
                z = trend_feature(u)
                x = np.column_stack((np.ones(len(u)-ahead), u[:-ahead]-9., z[:-ahead]))
                y = u[ahead:]-u[:-ahead]
                samples[split].append((case, x, y))
        train_x = np.concatenate([x for _, x, _ in samples['train']])
        train_y = np.concatenate([y for _, _, y in samples['train']])
        fits = []
        for width in (2, 3):
            x = train_x[:, :width]
            penalty = np.diag([0.] + [1e-3]*(width-1))
            fits.append(np.linalg.solve(x.T@x + penalty, x.T@train_y))
        coefficients.append(dict(ahead_s=ahead, baseline=fits[0].tolist(), trend=fits[1].tolist()))
        for split, cases in samples.items():
            for family in ('stationary', 'ramp', 'gust', 'all'):
                part = [(x, y) for c, x, y in cases if family == 'all' or c['family'] == family]
                base = np.concatenate([(y-x[:, :2]@fits[0])**2 for x, y in part])
                extra = np.concatenate([(y-x@fits[1])**2 for x, y in part])
                rows.append(dict(split=split, family=family, ahead_s=ahead, samples=len(base),
                                 baseline_mse_m2_s2=float(base.mean()), trend_mse_m2_s2=float(extra.mean()),
                                 relative_improvement=1-float(extra.mean()/base.mean())))
    return rows, coefficients


def make_cases(saved):
    import numpy as np
    from ..environments.farm_inflow import generate_inflow, InflowTrace
    from .random_wind_training import cases as old_cases
    p = saved['protocol']
    winds = []
    first = [r for r in read_csv(SOURCE/'pitch_wind_preflight.csv') if int(r['run_id']) == 0][:9]
    assert len({(r['family'], r['target_w']) for r in first}) == 9
    for row in first:
        inflow = deepcopy(p['inflow'])
        inflow['speed']['scenario'] = row['family']
        trace = generate_inflow(inflow, dt_s=1., horizon=128, seed=42, split='train',
                                episode=p['training_episode_offset']+int(row['episode']))
        assert hashlib.sha256(trace.values.tobytes()).hexdigest() == row['values_sha256']
        winds.append((dict(id=f"train_episode_{row['episode']}", split='train', family=row['family'],
                           target_w=float(row['target_w'])), trace))
    # load_cases filters validation before loading trace data. Test is never opened.
    for case, trace in old_cases(SOURCE, 'validation'):
        assert case['split'] == 'validation'
        winds.append((dict(case), trace))
    bank = []
    for case, trace in winds:
        pitches = (.025, .055) if case['split'] == 'train' else (.025, .04, .055)
        for pitch in pitches:
            c = dict(case, id=case['id']+f'_initial_{pitch}', initial_pitch_rad=pitch)
            bank.append((c, trace))
    for ui, u in enumerate((7.55, 7.7)):
        for ti, target in enumerate((4.3e6, 4.5e6)):
            inflow = deepcopy(p['inflow'])
            inflow['speed']['scenario'] = 'stationary'
            trace = generate_inflow(inflow, dt_s=1., horizon=128, seed=42, split='validation',
                                    episode=26000000+ui*10+ti)
            trace.values[:, 0] = u
            trace.values[:, 1] = 0.
            trace.values[:, 2] = .04
            trace.components[:] = 0.
            trace.components[:, 0] = u
            trace.metadata['diagnostic_fixed_override'] = dict(wind_m_s=u, target_w=target)
            trace = InflowTrace(trace.time_s, trace.values, trace.components, trace.metadata)
            for pitch in (.025, .055):
                bank.append((dict(id=f'validation_stress_u{u}_p{target}_b{pitch}', split='validation',
                                  family='low_wind_stress', target_w=target, initial_pitch_rad=pitch), trace))
    return bank, winds


def rollout(env, case, trace, *, agent=None, mode=None):
    import numpy as np
    from .controllers import PitchController
    assert (agent is None) != (mode is None)
    env.initial = np.array(env.config['initial_operating_point'], dtype=float)
    env.initial[1] = case['initial_pitch_rad']
    obs, info = env.reset(seed=42, options=dict(wind_trajectory=trace.values, target_w=case['target_w']))
    controller = PitchController(env, env._baseline_config, mode) if mode else None
    original_step = env.actuator.step
    captured = []
    def tap(commands):
        result = original_step(commands)
        captured[:] = [result]
        return result
    env.actuator.step = tap
    rows = []
    try:
        for t in range(128):
            before = info
            integral = controller.integral if controller else 0.
            raw_pi = (env._baseline_config['pitch_bias_rad'] + env._baseline_config['kp']*float(obs[0, 9])
                      + integral) if controller else None
            action = agent.act(obs) if agent else controller.act(obs)
            np.testing.assert_allclose(action[:, (0, 2)], env.project_action(action)[:, (0, 2)], atol=3e-6, rtol=0)
            obs, _, done, _, info = env.step(action)
            command = env.low[1] + (info['executed_action'][:, 1]+1)*(env.high[1]-env.low[1])/2
            delta = info['applied'][:, 1]-before['applied'][:, 1]
            assert np.all(np.abs(delta) <= env.config['rate_limits'][1]+1e-7)
            row = dict(case_id=case['id'], split=case['split'], family=case['family'], target_w=case['target_w'],
                       initial_pitch_rad=case['initial_pitch_rad'], decision_step=t, response_step=t+1,
                       decision_wind_m_s=float(before['wind'][0]), response_wind_m_s=float(info['wind'][0]),
                       trend_m_s=float(trend_feature(trace.values[:, 0])[t]),
                       decision_error_w=before['error_w'], error_w=info['error_w'], farm_power_w=info['farm_power_w'])
            for i in range(3):
                row.update({f'pitch_before_{i}':float(before['applied'][i, 1]), f'pitch_command_{i}':float(command[i]),
                            f'pitch_actual_{i}':float(info['applied'][i, 1]), f'pitch_delta_{i}':float(delta[i]),
                            f'pitch_rate_limited_{i}':int(captured[0].rate_saturation_mask[PITCH][i]),
                            f'pitch_position_clipped_{i}':int(captured[0].position_saturation_mask[PITCH][i]),
                            f'pitch_command_boundary_{i}':int(command[i] <= env.low[1]+1e-6 or command[i] >= env.high[1]-1e-6),
                            f'pitch_command_clipped_baseline_{i}':int(raw_pi is not None and not env.low[1] <= raw_pi <= env.high[1]),
                            f'power_{i}_w':float(info['power_w'][i])})
            rows.append(row)
            assert done == (t == 127)
    finally:
        env.actuator.step = original_step
    errors = [r['error_w'] for r in rows]
    metric = dict(case_id=case['id'], split=case['split'], family=case['family'], target_w=case['target_w'],
                  initial_pitch_rad=case['initial_pitch_rad'], **error_parts(errors))
    for name in ('rate_limited', 'position_clipped', 'command_boundary', 'command_clipped_baseline'):
        metric['pitch_'+name+'_fraction'] = float(np.mean([r[f'pitch_{name}_{i}'] for r in rows for i in range(3)]))
    metric['pitch_command_actual_rms_rad'] = float(np.sqrt(np.mean([(r[f'pitch_command_{i}']-r[f'pitch_actual_{i}'])**2
                                                                  for r in rows for i in range(3)])))
    metric['pitch_travel_rad'] = float(sum(abs(r[f'pitch_delta_{i}']) for r in rows for i in range(3)))
    return metric, rows


def sampled_ranges(env, bank):
    import numpy as np
    rows = []
    for case, trace in bank:
        if case['family'] != 'low_wind_stress' or case['initial_pitch_rad'] != .025:
            continue
        for t in (0, 32, 64, 96, 128):
            x = np.zeros((65, 12))
            x[:, :3] = trace.values[t]
            x[:, 6:9] = np.linspace(0, .22, 65)[:, None]
            x[:, 9:12] = .9
            for iteration in range(64):
                y = env.plant.predictor(x)
                speed = np.clip(.11114035087719298*y[:, 3:], .6, 1.267)
                residual = float(np.max(np.abs(speed-x[:, 9:12])))
                x[:, 9:12] = speed
                if residual < 1e-7:
                    break
            powers = env.plant.predictor(x)[:, :3].sum(1)
            rows.append(dict(case_id=case['id'], wind_m_s=float(trace.values[t, 0]), target_w=case['target_w'], step=t,
                             candidates=65, sampled_min_power_w=float(powers.min()), sampled_max_power_w=float(powers.max()),
                             sampled_path_gap_w=max(0., case['target_w']-float(powers.max())),
                             speed_fixed_point_residual_rad_s=residual, global_upper_bound_certified=False))
    return rows


def run(output):
    import numpy as np
    import torch
    import yaml
    from .algorithm import MADDPG
    from .workflow import build_env
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    start = time.perf_counter()
    root = Path(output).resolve()
    if root.exists():
        raise FileExistsError('preserve prior output; choose a new directory')
    saved = yaml.safe_load((SOURCE/'config.yaml').read_text(encoding='utf-8'))
    selection = json.loads((SOURCE/'selection.json').read_text(encoding='utf-8'))
    protected = {**saved['source_hashes'], **selection['hashes']}
    for name in ('config.yaml', 'selection.json', 'bank/manifest.json', 'pitch_wind_preflight.csv'):
        protected[str(SOURCE/name)] = digest(SOURCE/name)
    for path in Path(__file__).parent.glob('*.py'):
        protected[str(path)] = digest(path)
    protected[str(Path(__file__).with_name('PITCH_CROSS_WIND_PROTOCOL.md'))] = digest(Path(__file__).with_name('PITCH_CROSS_WIND_PROTOCOL.md'))
    assert all(Path(p).is_file() and digest(p) == h for p, h in protected.items())
    root.mkdir(parents=True)
    config = dict(seed=42, source=str(SOURCE), base_config=saved['base_config'], protected_hashes=protected,
                  main_forecast_horizon_s=1, additional_forecast_horizon_s=4, ridge=1e-3, trend_window_s=4,
                  forecast_improvement_gate=.05, test_access=False, new_training_steps=0,
                  command=f'python -B -X utf8 -m optimization_control.maddpg_wind_farm.pitch_cross_wind_diagnostic run --output "{root}"')
    (root/'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8', newline='\n')
    bank, winds = make_cases(saved)
    write_json(root/'case_manifest.json', [dict(c, wind_values_sha256=hashlib.sha256(w.values.tobytes()).hexdigest()) for c, w in bank])
    forecasts, coefficients = forecast_check(winds)
    write_csv(root/'forecast_metrics.csv', forecasts)
    write_json(root/'forecast_coefficients.json', coefficients)
    agents = {f'parent_{r["run_id"]}': MADDPG.load(r['best']['checkpoint'])[0] for r in selection['results']}
    env = build_env(saved['base_config'])
    env._baseline_config = saved['base_config']['baselines']
    all_metrics, all_traces, responses = [], [], []
    labels = list(agents) + ['p', 'pi']
    for label in labels:
        for case, trace in bank:
            metric, traces = rollout(env, case, trace, agent=agents.get(label), mode=label if label in ('p', 'pi') else None)
            all_metrics.append(dict(controller=label, **metric))
            all_traces.extend(dict(controller=label, **row) for row in traces)
            z = np.array([r['trend_m_s'] for r in traces])
            e = np.array([r['error_w'] for r in traces])
            de = e-np.array([r['decision_error_w'] for r in traces])
            for lag in range(9):
                n = 128-lag
                responses.append(dict(controller=label, case_id=case['id'], split=case['split'], family=case['family'], lag_s=lag,
                                      trend_error_correlation=correlation(z[:n], e[lag:]),
                                      trend_error_increment_correlation=correlation(z[:n], de[lag:])))
        print(json.dumps(dict(completed_controller=label, cases=len(bank), elapsed_s=round(time.perf_counter()-start, 1))), flush=True)
    write_csv(root/'metrics.csv', all_metrics)
    write_csv(root/'trajectories.csv', all_traces)
    write_csv(root/'response_correlations.csv', responses)
    write_csv(root/'sampled_ranges.csv', sampled_ranges(env, bank))
    # Original validation .04 is a direct numerical check against the frozen parent selection.
    validation_differences = []
    for r in selection['results']:
        for old in r['best']['validation']:
            actual = next(m for m in all_metrics if m['controller'] == f'parent_{r["run_id"]}' and
                          m['case_id'] == old['case_id']+'_initial_0.04')
            validation_differences.append(abs(actual['rmse_w']-old['rmse_w']))
    assert max(validation_differences) < 1e-6
    forecast_gate = all(next(v['relative_improvement'] for v in forecasts if v['split']=='validation' and
                            v['family']==f and v['ahead_s']==1) >= .05 for f in ('all', 'ramp'))
    weak = []
    for m in all_metrics:
        if m['split']=='validation' and m['family']=='ramp' and m['controller'].startswith('parent'):
            pi = next(v for v in all_metrics if v['controller']=='pi' and v['case_id']==m['case_id'])
            if m['rmse_w'] > pi['rmse_w'] and m['bias_share'] <= .25:
                weak.append(dict(controller=m['controller'], case_id=m['case_id'], rmse_gap_to_pi_w=m['rmse_w']-pi['rmse_w']))
    unchanged = all(digest(p)==h for p, h in protected.items())
    assert unchanged
    summary = dict(seed=42, complete=True, new_training_steps=0, test_access=False, cases=len(bank),
                   metric_rows=len(all_metrics), trajectory_rows=len(all_traces), protected_files=len(protected),
                   protected_files_unchanged=unchanged, original_validation_max_difference_w=max(validation_differences),
                   weak_variance_dominated_ramp_cases=weak, forecast_gate=forecast_gate,
                   candidate_supported=bool(weak and forecast_gate),
                   elapsed_s=time.perf_counter()-start, global_upper_bound_certified=False, physical_validation=False)
    write_json(root/'summary.txt', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run',))
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    run(args.output)


if __name__ == '__main__':
    main()
