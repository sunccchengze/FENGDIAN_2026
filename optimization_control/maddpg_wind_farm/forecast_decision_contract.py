"""Private timing/reward review only: no trainable network or production schema."""
from copy import deepcopy
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import pickle
import subprocess

DEFAULT = Path(__file__).with_name('configs') / 'forecast_decision_contract.yaml'
CONTRACT = Path(__file__).with_name('FORECAST_DECISION_CONTRACT.md')
LIMIT = 268435456


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Output:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def write(self, name, payload):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('new review outputs only')
        used = sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        previous = path.stat().st_size if path.exists() else 0
        if used + len(payload) - previous > LIMIT:
            raise RuntimeError('256 MiB output cap')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def json(self, name, value):
        self.write(name, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))

    def csv(self, name, rows):
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        self.write(name, stream.getvalue().encode('utf-8'))


def prepare(root, retry_after=None):
    import yaml
    repo = Path(__file__).resolve().parents[2]
    root = Path(root).resolve()
    retry_after = Path(retry_after).resolve() if retry_after else None
    expected_parent = retry_after if retry_after else repo / 'optimization_control/experiments'
    if root.parent != expected_parent or root.exists():
        raise ValueError('new sibling review directory required; no overwrite')
    previous_attempt = None
    if retry_after:
        failed = json.loads((retry_after/'verification.json').read_text(encoding='utf-8'))
        assert not failed['passed']
        if any(json.loads(path.read_text(encoding='utf-8')).get('passed') is True
               for path in retry_after.rglob('verification.json')):
            raise ValueError('a review attempt already passed; no implicit repeat')
        budget_files = {str(path):sha(path) for path in retry_after.rglob('budget.json')}
        previous_rows = sum(x['actual'] if x['status']=='complete' else max(x['actual'],x['reserve'])
            for name in budget_files for x in json.loads(Path(name).read_text(encoding='utf-8'))['scopes'])
        assert previous_rows+333<=4096
        previous_attempt = dict(root=str(retry_after), conservative_charged_rows=previous_rows,
            verification_sha256=sha(retry_after/'verification.json'),budget_sha256=sha(retry_after/'budget.json'),
            prior_code_lock_sha256=sha(retry_after/'run_lock.json'),all_prior_budget_hashes=budget_files)
    p = yaml.safe_load(DEFAULT.read_text(encoding='utf-8'))
    previous = repo / p['source_experiment']
    source = yaml.safe_load((previous / 'config.yaml').read_text(encoding='utf-8'))
    assert p['formal_RL_steps'] == p['parameter_updates'] == p['real_PINN_rows'] == 0
    assert [x['sha256'] for x in source['parents']] == p['parent_sha256']
    protected = {x['checkpoint']: x['sha256'] for x in source['parents']}
    protected[source['model']] = p['forecast_sha256']
    # Reuse the completed independent-test audit, without loading its trajectories/results.
    for name in ('config.yaml', 'complete.json', 'release.json', 'output_manifest.csv', 'historical_outlier_guard.json'):
        protected[str(previous / name)] = sha(previous / name)
    for name in ('algorithm.py', 'frozen_speed_algorithm.py', 'speed_nstep_algorithm.py',
                 'nstep_replay_core.py', 'speed_nstep_training.py', 'history_wind_forecast.py',
                 'history_speed_search.py', 'causal_speed_search.py'):
        path = Path(__file__).with_name(name)
        protected[str(path)] = sha(path)
    protected[str(repo / 'optimization_control/environments/maddpg_farm_env.py')] = sha(repo / 'optimization_control/environments/maddpg_farm_env.py')
    for directory in (repo, Path('.')):
        for name in ('PROJECT_STATUS.md', 'optimization_control/TASKFLOW.md', 'README.md'):
            path = directory / name
            protected[str(path)] = sha(path)
    for name, digest in protected.items():
        assert sha(name) == digest, name
    command = ['git', '-c', f'safe.directory={repo.as_posix()}', 'rev-parse', 'HEAD']
    commit = subprocess.check_output(command, cwd=repo, text=True).strip()
    # Reproduction may run from this review's descendant commit; source artifacts stay pinned.
    subprocess.run(['git','-c',f'safe.directory={repo.as_posix()}','merge-base','--is-ancestor',
        p['source_commit'],commit],cwd=repo,check=True)
    code = {str(path): sha(path) for path in (Path(__file__), DEFAULT, CONTRACT,
            repo / 'optimization_control/tests/test_forecast_decision_contract.py')}
    saved = dict(seed=42, protocol=p, base_config=source['base_config'], parents=source['parents'],
                 model=source['model'], worktree=str(repo), base_commit=commit,
                 protected=protected, executed_code=code, previous_attempt=previous_attempt)
    root.mkdir(parents=True)
    store = Output(root)
    store.write('config.yaml', yaml.safe_dump(saved, allow_unicode=True, sort_keys=False).encode('utf-8'))
    store.json('run_lock.json', dict(config_sha256=sha(root / 'config.yaml'), code=code,
        cases_fixed_before_forward=True, expected_mock_rows=333, hard_cap_rows=4096,
        formal_RL_steps=0, parameter_updates=0, real_PINN_rows=0))
    store.csv('metrics.csv', [dict(check='prepared', passed=True, mock_rows=0, real_PINN_rows=0, parameter_updates=0)])
    store.write('summary.txt', b'Prepared private decision contract review; no training or new test.\n')


def forecast_features(model, history, enabled):
    import numpy as np
    if not enabled:
        return np.zeros(36, np.float32)
    observed = np.asarray(history, np.float32)
    future, _ = model.predict(observed)
    current = observed[-1].astype(np.float64)
    return np.column_stack(((future[:, 0].astype(float) - current[0]) / 3,
        np.sin(future[:, 1].astype(float)) - np.sin(current[1]),
        np.cos(future[:, 1].astype(float)) - np.cos(current[1]))).astype(np.float32).ravel()


def discounted(rewards, gamma):
    import numpy as np
    rewards = np.asarray(rewards, np.float64)
    if rewards.ndim != 2 or rewards.shape[1] != 3 or not 1 <= len(rewards) <= 8:
        raise ValueError('one actual physical interval of length 1..8')
    return (rewards * (gamma ** np.arange(len(rewards)))[:, None]).sum(axis=0), gamma ** len(rewards)


class DecisionLedger:
    """In-memory software oracle, deliberately not a production replay/checkpoint."""
    def __init__(self, parent, model, obs, wind, *, enabled, explore, seed, horizon):
        import numpy as np
        self.parent, self.model = parent, model
        self.enabled, self.explore, self.horizon = enabled, explore, horizon
        self.t, self.done = 0, False
        self.history = [np.asarray(wind, np.float32).copy()]
        self.obs = np.asarray(obs, np.float32).copy()
        self.rng = np.random.default_rng(seed)
        self.pending, self.records = None, []
        self.decisions = self.noise_draws = 0

    def action(self):
        import numpy as np
        from .causal_speed_search import command
        if self.done:
            raise ValueError('terminal requires a fresh reset, not another action')
        if self.pending is None:
            if self.t % 8:
                raise ValueError('speed may be chosen only on a decision boundary')
            z = np.clip(self.rng.normal(0, .15, 3), -1, 1) if self.explore else np.zeros(3)
            self.noise_draws += int(self.explore)
            self.decisions += 1
            self.pending = dict(t=self.t, obs=self.obs.copy(),
                forecast=forecast_features(self.model, self.history, self.enabled),
                history_sha256=sha_history(self.history), z=z, offset=.1*z, rewards=[], actions=[], parents=[])
        action, parent = command(self.parent, self.obs, self.pending['offset'])
        return action, parent

    def observe(self, obs, wind, reward, done, action, parent, executed):
        import numpy as np
        if self.pending is None or self.done:
            raise ValueError('observation requires an active physical interval')
        np.testing.assert_array_equal(action, executed)
        np.testing.assert_array_equal(obs[:, 5:8], executed)
        np.testing.assert_array_equal(action[:, :2], parent[:, :2])
        self.pending['rewards'].append(np.asarray(reward).copy())
        self.pending['actions'].append(action.copy())
        self.pending['parents'].append(parent.copy())
        self.t += 1
        self.done = bool(done)
        if self.done != (self.t == self.horizon):
            raise ValueError('only true task terminal closes a short interval')
        self.history.append(np.asarray(wind, np.float32).copy())
        self.obs = np.asarray(obs, np.float32).copy()
        if self.t % 8 == 0 or self.done:
            item = deepcopy(self.pending)
            item['m'] = self.t - item['t']
            item['return'], item['discount'] = discounted(item['rewards'], .99)
            item['next_obs'] = self.obs.copy()
            item['terminated'] = self.done
            item['next_forecast_valid'] = not self.done
            item['next_forecast'] = np.zeros(36, np.float32) if self.done else forecast_features(self.model, self.history, self.enabled)
            item['next_history_sha256'] = sha_history(self.history)
            self.records.append(item)
            self.pending = None

    def snapshot(self):
        return deepcopy({k: v for k, v in self.__dict__.items() if k not in ('parent', 'model', 'rng')}) | dict(rng_state=deepcopy(self.rng.bit_generator.state))

    @classmethod
    def restore(cls, state, parent, model, physical_t):
        import numpy as np
        if state['t'] != physical_t or len(state['history']) != physical_t + 1:
            raise ValueError('physical clock/history restoration mismatch')
        pending = state['pending']
        if pending is not None and (pending['t'] % 8 or len(pending['rewards']) != physical_t - pending['t'] or not 0 < physical_t - pending['t'] < 8):
            raise ValueError('pending interval/phase restoration mismatch')
        if pending is None and physical_t % 8 and not state['done']:
            raise ValueError('lost held interval on a nonboundary restore')
        a = object.__new__(cls)
        a.__dict__ = deepcopy({k: v for k, v in state.items() if k != 'rng_state'})
        a.parent, a.model = parent, model
        a.rng = np.random.default_rng()
        a.rng.bit_generator.state = deepcopy(state['rng_state'])
        np.testing.assert_allclose(a.obs[:, 14], 1-physical_t/a.horizon, rtol=0, atol=1e-7)
        return a


def sha_history(history):
    import numpy as np
    return hashlib.sha256(np.asarray(history, np.float32).tobytes()).hexdigest()


def mock_env(saved, budget, horizon):
    from .workflow import load_config, DEFAULT_CONFIG, build_env
    from .causal_speed_search import Meter
    cfg = deepcopy(saved['base_config'])
    cfg['plant'] = load_config(DEFAULT_CONFIG)['plant']
    cfg['environment']['horizon'] = horizon
    assert cfg['plant']['kind'] == 'mock'
    env = build_env(cfg)
    env.plant.predictor = Meter(env.plant.predictor, budget)
    env.plant.predictor.kind = 'new_deterministic_mock_forward'
    return env


def winds(horizon):
    import numpy as np
    t = np.arange(horizon+1)
    return np.column_stack((9+.02*t+.06*np.sin(t/3), .002*t, np.full(len(t), .08))).astype(np.float32)


def model_digest(parent):
    h = hashlib.sha256()
    for group in ('actors', 'target_actors', 'critics', 'target_critics'):
        for name, value in getattr(parent, group).state_dict().items():
            h.update(group.encode()); h.update(name.encode()); h.update(value.cpu().numpy().tobytes())
    return h.hexdigest()


def exact_tree(actual, expected, location='state'):
    """Compare state values/types, not pickle memo IDs or object alias layouts."""
    import numpy as np
    if isinstance(expected,np.ndarray):
        if not isinstance(actual,np.ndarray) or actual.dtype!=expected.dtype or actual.shape!=expected.shape:
            raise AssertionError(location+': array type/shape differs')
        np.testing.assert_array_equal(actual,expected,err_msg=location)
    elif isinstance(expected,dict):
        if not isinstance(actual,dict) or set(actual)!=set(expected):
            raise AssertionError(location+': dictionary keys differ')
        for key,value in expected.items():exact_tree(actual[key],value,location+'.'+str(key))
    elif isinstance(expected,(tuple,list)):
        if type(actual) is not type(expected) or len(actual)!=len(expected):
            raise AssertionError(location+': sequence differs')
        for index,value in enumerate(expected):exact_tree(actual[index],value,location+f'[{index}]')
    elif type(actual) is not type(expected) or actual!=expected:
        raise AssertionError(location+': scalar differs')


def mock_paths(saved, root, budget):
    import math
    import numpy as np
    from .algorithm import MADDPG
    from .history_wind_forecast import RidgeForecast
    from .causal_speed_search import capture, fork
    model = RidgeForecast.load(saved['model'])
    store, results, parent_audit = Output(root), [], []
    for run, source in enumerate(saved['parents']):
        parent, meta = MADDPG.load(source['checkpoint'])
        before = model_digest(parent)
        rng_before = pickle.dumps(parent.rng.bit_generator.state)
        updates_before = parent.updates
        replay = parent.replay.state_dict()
        fields = list(replay['data'])
        assert set(fields) == {'obs', 'next_obs', 'actions', 'rewards', 'terminated'}
        parent_audit.append(dict(run=run, checkpoint=source['checkpoint'], sha256=source['sha256'],
            replay_fields=fields, retained=replay['size'], position=replay['position'],
            earliest_retained_clock=float(replay['data']['obs'][replay['position'] if replay['size']==parent.config.capacity else 0, 0, 14]),
            missing_episode_identity_history_forecast_and_hold=True, updates_before=updates_before,
            metadata_keys=sorted(meta)))
        del replay  # Only releases a private RAM view; no files are removed.
        reference = None
        for label in ('direct', 'zero_B', 'zero_C', 'explore_C'):
            scope = f'run{run}_{label}'
            budget.start(scope, 20)
            env = mock_env(saved, budget, 19)
            obs, _ = env.reset(seed=42, options=dict(wind_trajectory=winds(19), target_w=3.2e6))
            ledger = None if label == 'direct' else DecisionLedger(parent, model, obs, env.wind,
                enabled=label != 'zero_B', explore=label == 'explore_C', seed=np.random.SeedSequence([42,20261030,run]), horizon=19)
            records, snapshots = [], {}
            while not env._done:
                action, base = (parent.act(obs), parent.act(obs)) if ledger is None else ledger.action()
                nxt, reward, done, truncated, info = env.step(action)
                assert not truncated
                if ledger is not None:
                    ledger.observe(nxt, env.wind, reward, done, action, base, info['executed_action'])
                records.append((obs.copy(), action.copy(), nxt.copy(), info['applied'].copy(), info['power_w'].copy()))
                obs = nxt
                if label == 'explore_C' and env.t in (5, 8):
                    snapshots[env.t] = pickle.dumps(dict(physical=capture(env), ledger=ledger.snapshot()), protocol=5)
            scope_result = budget.finish()
            if label == 'direct':
                reference = records
            elif label.startswith('zero'):
                for actual, expected in zip(records, reference):
                    for a, b in zip(actual, expected):
                        np.testing.assert_array_equal(a, b)
            else:
                assert ledger.decisions == ledger.noise_draws == 3
                assert [x['m'] for x in ledger.records] == [8,8,3]
                assert [x['terminated'] for x in ledger.records] == [False,False,True]
                assert not ledger.records[-1]['next_forecast_valid']
                for interval in ledger.records:
                    independent = np.array([math.fsum(float(r[i])*.99**k for k,r in enumerate(interval['rewards'])) for i in range(3)])
                    np.testing.assert_allclose(interval['return'], independent, atol=1e-12, rtol=0)
                assert not np.array_equal(ledger.records[0]['forecast'], ledger.records[0]['next_forecast'])
                assert any(not np.array_equal(records[0][1][:,1], x[1][:,1]) for x in records[1:8])
                store.json(f'run{run}_intervals.json', [dict(t=x['t'],m=x['m'],terminated=x['terminated'],
                    offset=x['offset'].tolist(),discount=x['discount'],returns=x['return'].tolist(),
                    rewards=np.asarray(x['rewards']).tolist(),forecast=x['forecast'].tolist(),next_forecast=x['next_forecast'].tolist(),
                    forecast_valid=True,next_forecast_valid=x['next_forecast_valid'],history_sha256=x['history_sha256'],
                    next_history_sha256=x['next_history_sha256'],actions=np.asarray(x['actions']).tolist(),
                    parents=np.asarray(x['parents']).tolist()) for x in ledger.records])
            results.append(dict(check=scope, passed=True, mock_rows=scope_result['actual'], real_PINN_rows=0, parameter_updates=0))
            if label == 'explore_C':
                final_state = ledger.snapshot()
                for t, payload in snapshots.items():
                    budget.start(f'run{run}_resume_t{t}', 19-t)
                    state = pickle.loads(payload)
                    child = fork(state['physical'], env.plant, type(env))
                    child.trajectory = winds(19)  # Only the mock plant reads future disturbances.
                    restored = DecisionLedger.restore(state['ledger'], parent, model, child.t)
                    assert len(restored.records) == (0 if t==5 else 1)
                    if t == 5:
                        assert len(restored.pending['rewards']) == 5
                    while not child._done:
                        action, base = restored.action()
                        nxt, reward, done, _, info = child.step(action)
                        restored.observe(nxt, child.wind, reward, done, action, base, info['executed_action'])
                    recovered = restored.snapshot()
                    exact_tree(recovered,final_state)
                    store.json(f'run{run}_resume_t{t}.json',dict(state_fields_exact=True,
                        compared_fields=list(final_state), array_values_types_shapes_exact=True,
                        rng_state_exact=True,physical_t=restored.t,
                        pickle_bytes_equal=pickle.dumps(recovered,protocol=5)==pickle.dumps(final_state,protocol=5)))
                    results.append(dict(check=f'run{run}_resume_t{t}', passed=True,
                        mock_rows=budget.finish()['actual'], real_PINN_rows=0, parameter_updates=0))
                    bad = deepcopy(state['ledger']); bad['t'] += 1
                    try:
                        DecisionLedger.restore(bad, parent, model, t)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('corrupt restore clock accepted')
                try:
                    ledger.action()
                except ValueError:
                    pass
                else:
                    raise AssertionError('terminal action accepted')
        budget.start(f'run{run}_new_reset', 6)
        env = mock_env(saved, budget, 5)
        obs, _ = env.reset(seed=42, options=dict(wind_trajectory=winds(5), target_w=3.2e6))
        fresh = DecisionLedger(parent, model, obs, env.wind, enabled=True, explore=False, seed=42, horizon=5)
        assert len(fresh.history)==1 and fresh.t==0 and fresh.pending is None and fresh.decisions==0
        while not env._done:
            action, base = fresh.action()
            nxt, r, d, _, info = env.step(action)
            fresh.observe(nxt, env.wind, r, d, action, base, info['executed_action'])
        assert fresh.records[0]['m']==5 and fresh.records[0]['terminated']
        results.append(dict(check=f'run{run}_new_reset', passed=True, mock_rows=budget.finish()['actual'], real_PINN_rows=0, parameter_updates=0))
        assert model_digest(parent) == before and parent.updates == updates_before
        assert pickle.dumps(parent.rng.bit_generator.state)==rng_before
        parent_audit[-1].update(weights_unchanged=True, rng_unchanged=True, updates_after=parent.updates)
    store.json('parent_replay_review.json', parent_audit)
    store.csv('metrics.csv', results)
    return results


def audit(root):
    import unittest
    import yaml
    import torch
    from .causal_speed_search import Budget
    from optimization_control.tests import test_forecast_decision_contract as tests
    root = Path(root).resolve()
    store = Output(root)
    if (root/'audit_attempt.json').exists():
        raise ValueError('attempt already exists; preserve failures and budget before any new attempt')
    saved = yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    lock = json.loads((root/'run_lock.json').read_text(encoding='utf-8'))
    assert sha(root/'config.yaml') == lock['config_sha256']
    for name,digest in dict(saved['protected'], **saved['executed_code']).items():
        assert sha(name)==digest, name
    store.json('audit_attempt.json', dict(formal_RL_steps=0, parameter_updates=0, mock_limit=4096, real_PINN_rows=0))
    prior = saved.get('previous_attempt')
    previous_rows = prior['conservative_charged_rows'] if prior else 0
    if prior:
        for name in ('verification','budget'):
            assert sha(Path(prior['root'])/(name+'.json'))==prior[name+'_sha256']
        for name,digest in prior.get('all_prior_budget_hashes',{}).items():
            assert sha(name)==digest
    budget = Budget(root/'budget.json', limit=4096-previous_rows)
    tests.CONTEXT = dict(saved=saved, root=root, budget=budget)
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    store.write('tests.txt', stream.getvalue().encode('utf-8'))
    consumed = sum(x['actual'] for x in budget.data['scopes'])
    evidence = dict(passed=result.wasSuccessful(), tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        mock_rows=consumed, prior_conservative_charged_rows=previous_rows,cumulative_mock_rows=consumed+previous_rows,
        real_PINN_rows=0, formal_RL_steps=0, parameter_updates=0,
        evidence=tests.EVIDENCE, model_or_replay_files_copied=0, new_independent_winds=0)
    store.json('verification.json', evidence)
    print(stream.getvalue(), flush=True)
    if not result.wasSuccessful():
        raise RuntimeError('review tests failed; attempt and consumed budget preserved')
    assert consumed==333 and consumed+previous_rows<=4096 and all(x['status']=='complete' for x in budget.data['scopes'])
    for name,digest in dict(saved['protected'], **saved['executed_code']).items():
        assert sha(name)==digest, name
    store.json('source_guard.json', dict(unchanged=saved['protected'], executed_code=saved['executed_code'],
        old_test_replayed=False, new_test_generated=False, source_model_copies=0, parent_replay_copies=0))
    store.write('summary.txt', ('PASS: private forecast decision contract review; seed=42\n'
        f'{result.testsRun} tests, {consumed} current / {consumed+previous_rows} cumulative / 4096 mock input rows; real PINN rows=0, RL steps=0, parameter updates=0.\n'
        'Recommend decision-boundary speed learning; 51-input heads and 84-input macro Critics remain proposals.\n'
        'No production network, checkpoint/replay migration, yaw, old test rerun, or new independent test.\n').encode('utf-8'))
    print(json.dumps({k:v for k,v in evidence.items() if k!='evidence'}, ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare','audit'))
    parser.add_argument('--output',required=True)
    parser.add_argument('--retry-after',help='preserved failed review directory; new child attempt only')
    args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    if args.command=='prepare':prepare(Path(args.output),args.retry_after)
    else:audit(Path(args.output))


if __name__=='__main__':
    main()
