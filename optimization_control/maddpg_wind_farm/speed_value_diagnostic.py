"""Zero-update speed value/feedback diagnostics on a frozen validation design."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import pickle
import subprocess

from .anchor_closeout import sha, read_json, write_json, read_csv, write_csv, verify_hashes, make_env, checked_output

STEPS = (0, 2048, 4096, 6144, 8192)
RADII = (0., .02, .05, .1)
DELTAS = (-.04, -.02, .02, .04)
HORIZONS = (8, 32)
WIDTH = .667
MAX_STEPS = 65000
_BUDGET = None


def step_env(env, action):
    if _BUDGET is not None:
        if _BUDGET['steps'] >= MAX_STEPS:
            raise RuntimeError('Frozen diagnostic environment-step cap reached')
        _BUDGET['steps'] += 1
    return env.step(action)


def clone_env(env):
    result = object.__new__(type(env))
    result.__dict__ = deepcopy({k: v for k, v in env.__dict__.items() if k != 'plant'})
    result.plant = env.plant  # Frozen, stateless predictor; never deepcopy TensorFlow.
    return result


def state_sha(env):
    keys = ('t', '_done', 'wind', 'power', 'effective_wind', 'applied', 'heading',
            'previous_action', 'last_action_change', 'saturation_fraction', 'reward_terms')
    state = {k: getattr(env, k) for k in keys}
    state['rng'] = env.rng.bit_generator.state
    state['actuator'] = {k: getattr(env.actuator, k) for k in
        ('_state', '_delay_queues', '_active_reference', '_step_index', '_leading_shape')}
    return hashlib.sha256(pickle.dumps(state, protocol=5)).hexdigest()


def radius_action(agent, obs, radius=.1):
    import numpy as np
    import torch
    if radius not in RADII:
        raise ValueError('Only predeclared radii are permitted')
    with torch.no_grad():
        x = torch.as_tensor(np.asarray(obs, np.float32), device=agent.device)
        values = []
        for i in range(3):
            parent = agent.parent_action(i, x[i])
            raw = agent.speed_heads[i](x[i]).squeeze(-1)
            speed = (parent[2] + raw * (2 * radius / WIDTH)).clamp(-1, 1)
            values.append(torch.stack((parent[0], parent[1], speed)))
        return torch.stack(values).cpu().numpy().astype(np.float32)


def pulse_action(agent, obs, turbine, delta):
    import numpy as np
    if turbine not in range(3) or delta not in DELTAS:
        raise ValueError('Unregistered symmetric probe')
    action = radius_action(agent, obs)
    parent = agent.act(obs, zero_speed=True)
    action[turbine, 2] = np.clip(action[turbine, 2] + 2 * delta / WIDTH,
        max(-1, float(parent[turbine, 2]) - 2 * .1 / WIDTH),
        min(1, float(parent[turbine, 2]) + 2 * .1 / WIDTH))
    return action


def q_values(agent, obs, action, target=False):
    import numpy as np
    import torch
    critics = agent.target_critics if target else agent.critics
    with torch.no_grad():
        x = torch.as_tensor(np.r_[np.asarray(obs).ravel(), np.asarray(action).ravel()], dtype=torch.float32, device=agent.device)[None]
        return [float(critic(x).item()) for critic in critics]


def q_gradients(agent, obs, action, target=False):
    import numpy as np
    import torch
    critics = agent.target_critics if target else agent.critics
    result = []
    for i, critic in enumerate(critics):
        a = torch.tensor(np.asarray(action), dtype=torch.float32, device=agent.device, requires_grad=True)
        x = torch.cat((torch.as_tensor(np.asarray(obs), dtype=torch.float32, device=agent.device).flatten(), a.flatten()))[None]
        derivative = torch.autograd.grad(critic(x).sum(), a)[0][i, 2]
        result.append(float(derivative.item()) * 2 / WIDTH)
    return result


def branch(anchor, agent, *, first_action=None, radius=.1, pitch_script=None):
    """One first-action intervention or persistent radius, always real actuators."""
    import numpy as np
    env = clone_env(anchor)
    before = state_sha(anchor)
    obs = env._observe()
    ledger = {k: [] for k in ('reward', 'tracking', 'penalty', 'error_w', 'action_change',
        'executed', 'physical', 'power', 'wind', 'gamma')}
    terminals = {}
    start = np.column_stack((env.heading, env.applied[:, 1:]))
    start_command = env.previous_action.copy()
    for step in range(32):
        action = np.asarray(first_action).copy() if step == 0 and first_action is not None else radius_action(agent, obs, radius)
        if pitch_script is not None:
            action[:, 1] = pitch_script[step]
        projected = env.project_action(action)
        nxt, reward, done, _, info = step_env(env, action)
        np.testing.assert_array_equal(projected, info['executed_action'])
        assert not done  # t64..96, no unreported episode truncation.
        values = dict(reward=float(reward[0]),
            tracking=env.config.get('reward_scale',1.) * info['reward_terms']['tracking'],
            penalty=env.config.get('reward_scale',1.) * info['reward_terms']['action_change'],
            error_w=info['error_w'], action_change=info['action_change'], executed=info['executed_action'].copy(),
            physical=np.column_stack((info['heading_rad'], info['applied'][:, 1:])),
            power=info['power_w'].copy(), wind=info['wind'].copy(), gamma=info['applied'][:, 0].copy())
        for key, value in values.items():
            ledger[key].append(value)
        obs = nxt
        if step + 1 in HORIZONS:
            current = radius_action(agent, obs)
            target = np.stack([agent.total_action(i, __import__('torch').as_tensor(obs[i]), target=True).detach().cpu().numpy() for i in range(3)])
            terminals[step + 1] = dict(online=q_values(agent, obs, current), target=q_values(agent, obs, target, True))
    assert state_sha(anchor) == before, 'A branch mutated its shared initial state'
    data = {k: np.asarray(v) for k, v in ledger.items()}
    previous = np.concatenate((start[None], data['physical'][:-1]))
    max_rates = np.abs(data['physical'] - previous).max(axis=(0, 1)) / env.dt
    assert np.all(max_rates <= np.asarray(env.config['rate_limits']) + 1e-7)
    np.testing.assert_allclose(data['reward'], data['tracking'] + data['penalty'], atol=1e-7, rtol=1e-6)
    info = dict(start_state_sha256=before, start_physical=start.tolist(), start_command=start_command.tolist(),
        first_action=data['executed'][0].tolist(), max_rates=max_rates.tolist(), terminal_bootstrap=terminals)
    for h in HORIZONS:
        discount = agent.config.gamma ** np.arange(h)
        info[f'return_{h}'] = float(discount @ data['reward'][:h])
        info[f'tracking_{h}'] = float(discount @ data['tracking'][:h])
        info[f'penalty_{h}'] = float(discount @ data['penalty'][:h])
        info[f'rmse_{h}_w'] = float(np.sqrt(np.mean(data['error_w'][:h] ** 2)))
    return info, data


def fingerprint(agent):
    """Include trainable/target parameters, moments, replay and all RNG snapshots."""
    from .verify_anchor import comparable
    return hashlib.sha256(pickle.dumps(comparable(dict(
        networks={k: {n: v.detach().cpu().numpy() for n, v in getattr(agent, k).state_dict().items()}
                  for k in ('actors', 'target_actors', 'critics', 'target_critics', 'speed_heads', 'target_speed_heads')},
        heads=[o.state_dict() for o in agent.head_optimizers], critics=[o.state_dict() for o in agent.critic_optimizers],
        replay=agent.replay.state_dict(), rng=agent.rng.bit_generator.state, updates=agent.updates)), protocol=5)).hexdigest()


def inventory(folder):
    return {str(p.resolve()): sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def prepare(root):
    import yaml
    worktree = Path(__file__).resolve().parents[2]
    source = worktree / 'optimization_control/experiments/20261028_frozen_speed_checked'
    retired = source.with_name('20261028_frozen_speed')
    root = checked_output(root, worktree, Path('.'))
    if root.is_relative_to(source) or root.is_relative_to(retired):
        raise ValueError('Old experiments are read-only')
    old = yaml.safe_load((source / 'config.yaml').read_text(encoding='utf-8'))
    selection = read_json(source / 'selection.json')
    points = []
    for run in range(3):
        result = next(r for r in selection['results'] if r['arm'] == 'speed' and r['run_id'] == run)
        for step in STEPS:
            paths = list((source / f'formal/speed_run_{run}').glob(f'segment_*/step_{step:08d}.pth'))
            assert len(paths) == 1
            points.append(dict(run_id=run, step=step, path=str(paths[0]), sha256=sha(paths[0]),
                selected=str(paths[0]) == result['selected'], final=step == 8192))
    cases = [c for c in read_json(source / 'bank/manifest.json')['cases'] if c['split'] == 'validation']
    assert len(cases) == 6 and {c['target_w'] for c in cases} == {2850000., 3450000.}
    protected = inventory(source) | inventory(retired)
    for path, digest in old['source_hashes'].items():
        if Path(path).name not in ('PROJECT_STATUS.md', 'README.md', 'TASKFLOW.md'):
            assert sha(path) == digest
            protected[path] = digest
    coordination = {str(Path('.') / n): sha(Path('.') / n)
                    for n in ('PROJECT_STATUS.md', 'README.md', 'optimization_control/TASKFLOW.md')}
    executed = dict(old['executed_code_hashes'])
    verify_hashes(executed)
    for path in [*Path(__file__).parent.glob('speed_value_*.py'),
                 Path(__file__).with_name('SPEED_VALUE_PROTOCOL.md'),
                 worktree / 'optimization_control/tests/test_speed_value_diagnostic.py']:
        executed[str(path)] = sha(path)
    root.mkdir(parents=True, exist_ok=False)
    cfg = dict(seed=42, source_experiment=str(source), retired_experiment=str(retired), worktree=str(worktree),
        base_commit=subprocess.check_output(['git', '-c', 'safe.directory=' + str(worktree), 'rev-parse', 'HEAD'], cwd=worktree, text=True).strip(),
        cases=cases, checkpoints=points, parents=old['parents'], environment_config=old['base_config'],
        source_hashes=protected, executed_code_hashes=executed, coordination_at_start=coordination,
        anchor_step=64, horizons=list(HORIZONS), symmetric_speed_offsets_rad_s=list(DELTAS), radii_rad_s=list(RADII),
        snapshot_steps=list(STEPS), expected_main_environment_steps=64512, max_environment_steps=MAX_STEPS,
        expected_branches=1902, expected_horizon_rows=3804, formal_training_steps=0, optimizer_updates=0,
        thresholds=dict(action_rad_s=1e-5, return_difference=1e-4, q_difference=1e-5),
        source_test_performance_read=False, physical_validation=False)
    (root / 'config.yaml').write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding='utf-8', newline='\n')
    write_csv(root / 'metrics.csv', [dict(stage='prepared', formal_training_steps=0)])
    write_json(root / 'summary.txt', dict(seed=42, status='prepared', formal_training_steps=0, optimizer_updates=0))
    print('Prepared zero-update diagnostic', root, flush=True)


def context(root):
    import yaml
    cfg = yaml.safe_load((root / 'config.yaml').read_text(encoding='utf-8'))
    verify_hashes(cfg['source_hashes']); verify_hashes(cfg['executed_code_hashes'])
    return cfg


def build_anchor(agent, config, case, wind, limit=64):
    import numpy as np
    env = make_env(config)
    env.initial = np.asarray(config['environment']['initial_operating_point'], float).copy()
    env.initial[1] = case['initial_pitch_rad']
    obs, _ = env.reset(seed=42, options=dict(wind_trajectory=wind.values, target_w=case['target_w']))
    saved = None; future = []; reference = []
    for step in range(limit):
        a = radius_action(agent, obs)
        obs, _, _, _, info = step_env(env, a)
        if step + 1 == 64:
            saved = clone_env(env)
        if step >= 64:
            future.append(info['executed_action'][:, 1].copy())
            reference.append(dict(executed=info['executed_action'].copy(), power=info['power_w'].copy(),
                physical=np.column_stack((info['heading_rad'],info['applied'][:,1:]))))
    assert saved is not None
    return saved, np.asarray(future), limit, reference


def execute_case(root, cfg, run, case, agents):
    import numpy as np
    import torch
    from ..environments.farm_inflow import InflowTrace
    out = root / f'run_{run}' / case['id']
    if (out / 'complete.json').exists():
        verify_hashes({str(out / name): digest for name, digest in read_json(out / 'complete.json').items()})
        return
    if out.exists():
        raise ValueError('Incomplete case retained; inspect its budget before any restart')
    out.mkdir(parents=True)
    config = deepcopy(cfg['environment_config']); config['environment']['control_mask'] = [0, 1, 1]
    wind = InflowTrace.load(Path(cfg['source_experiment']) / 'bank' / case['path'])
    anchor, pitch_script, warm_steps, parent_future = build_anchor(agents[0], config, case, wind, 96)
    assert pitch_script.shape == (32, 3)
    weights_before = [fingerprint(a) for a in agents]
    torch_rng = torch.get_rng_state().clone()
    rows = []; arrays = []; anchors = []
    def evaluate(env, index, variant, *, mode='pulse', first=None, radius=.1, replay=False, focus=-1, requested_delta=0.):
        source = state_sha(env); obs = env._observe(); agent = agents[index]
        a = radius_action(agent, obs, radius) if first is None else np.asarray(first).copy()
        if replay: a[:, 1] = pitch_script[0]
        a = env.project_action(a)
        q = [[q_values(rater, obs, a, kind) for kind in (False, True)] for rater in agents]
        result, data = branch(env, agent, first_action=a if mode == 'pulse' else None,
            radius=radius, pitch_script=pitch_script if replay else None)
        np.testing.assert_array_equal(np.asarray(result['first_action']), a)
        result.update(index=len(rows), run_id=run, case_id=case['id'], family=case['family'], target_w=case['target_w'],
            actor_step=STEPS[index], mode=mode, variant=variant, radius_rad_s=radius, focus_agent=focus,
            requested_delta_rad_s=requested_delta, q_scores=q, start_observation=obs.tolist(),
            start_raw_heads=[float(h(torch.tensor(obs[i])).detach().item()) for i, h in enumerate(agent.speed_heads)],
            q_gradient_online=q_gradients(agent, obs, radius_action(agent, obs)),
            q_gradient_target=q_gradients(agent, obs, radius_action(agent, obs), True),
            start_state_source_sha256=source, offline_future_parent_pitch=replay,
            continuation='current_state_closed_loop_radius_0.1' if mode == 'pulse' else mode,
            bootstrap_is_self_estimate_not_independent_truth=True)
        rows.append(result); arrays.append(data)
        return result
    for index, step in enumerate(STEPS):
        agent = agents[index]; obs = anchor._observe(); center = radius_action(agent, obs)
        evaluate(anchor, index, 'center', first=center)
        if step == 0:
            for key in ('executed','power','physical'):
                np.testing.assert_array_equal(arrays[-1][key],np.asarray([r[key] for r in parent_future]))
        for turbine in range(3):
            for delta in DELTAS:
                evaluate(anchor, index, f't{turbine}_delta{delta:+.2f}',
                    first=pulse_action(agent, obs, turbine, delta), focus=turbine, requested_delta=delta)
        for radius in RADII[:-1]:
            evaluate(anchor, index, f'radius{radius:.2f}_first', first=radius_action(agent, obs, radius))
            evaluate(anchor, index, f'radius{radius:.2f}_persistent', mode='persistent_canonical', radius=radius)
        if step:
            evaluate(anchor, index, 'offline_parent_pitch', mode='offline_parent_pitch', replay=True)
        roles = next(r for r in cfg['checkpoints'] if r['run_id'] == run and r['step'] == step)
        if step and (roles['selected'] or roles['final']):
            own, _, used, _ = build_anchor(agent, config, case, wind)
            warm_steps += used
            anchors.append(dict(actor_step=step, source='own', state_sha256=state_sha(own), observation=own._observe().tolist()))
            for radius in RADII:
                evaluate(own, index, f'radius{radius:.2f}_own', mode='persistent_own', radius=radius)
        print('Value probes', run, case['id'], step, 'branches', len(rows), flush=True)
    assert [fingerprint(a) for a in agents] == weights_before
    assert torch.equal(torch_rng, torch.get_rng_state())
    for a in agents:
        assert all(p.grad is None for p in a.critics.parameters())
    anchors.insert(0, dict(source='canonical_parent', state_sha256=state_sha(anchor), observation=anchor._observe().tolist(),
        future_wind_sha256=hashlib.sha256(anchor.trajectory[64:97].tobytes()).hexdigest(), future_pitch_commands=pitch_script.tolist()))
    (out / 'branches.json').write_text(json.dumps(rows, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    write_json(out / 'anchors.json', anchors)
    np.savez_compressed(out / 'ledger.npz', **{k: np.stack([a[k] for a in arrays]) for k in arrays[0]})
    write_json(out / 'audit.json', dict(seed=42, warmup_environment_steps=warm_steps,
        branch_environment_steps=len(rows)*32, formal_training_steps=0, optimizer_updates=0,
        source_agents_unchanged=True, torch_rng_unchanged=True, no_parameter_gradients_accumulated=True,
        initial_center_vs_parent_future_exact=True))
    write_json(out / 'complete.json', {p.name: sha(p) for p in out.iterdir() if p.is_file()})


def run(root):
    global _BUDGET
    import torch
    from .frozen_speed_algorithm import load_policy
    cfg = context(root)
    if (root / 'complete.json').exists():
        raise ValueError('Diagnostic complete; use existing results')
    _BUDGET = dict(steps=sum(a['warmup_environment_steps'] + a['branch_environment_steps']
        for path in root.glob('run_*/*/audit.json') for a in [read_json(path)] if (path.parent / 'complete.json').exists()))
    for run_id in range(3):
        points = [p for p in cfg['checkpoints'] if p['run_id'] == run_id]
        agents = [load_policy(p['path'])[0] for p in points]
        for a in agents:
            assert abs(a.config.speed_scale - 2*.1/WIDTH) < 1e-12
        for case in cfg['cases']:
            execute_case(root, cfg, run_id, case, agents)
    context(root)
    assert _BUDGET['steps'] == cfg['expected_main_environment_steps']
    from .speed_value_analysis import analyze
    analyze(root, cfg)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'verify', 'figures'))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    root = Path(args.output).resolve()
    if args.command == 'prepare': prepare(root)
    elif args.command == 'run': run(root)
    else:
        cfg = context(root)
        from .speed_value_analysis import verify, figures
        (verify if args.command == 'verify' else figures)(root, cfg)


if __name__ == '__main__':
    main()
