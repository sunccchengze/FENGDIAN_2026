"""Frozen small-anchor mechanism audit. No training or independent-test rollout."""
from __future__ import annotations
import argparse
from collections import defaultdict
from copy import deepcopy
import csv
import gzip
import hashlib
import json
from pathlib import Path

from .fixed_pinn_demo import activate_runtime, digest
from .pitch_cross_wind_diagnostic import ORIGINAL, read_csv, write_csv, write_json, error_parts
from .pitch_nstep_trial import read_json, verify, frozen, bank, attempt_dir, compressed_csv
from .pitch_action_diagnostic import clone_env, corrected_action, critic_probe, support, totals, trace_row, reset_case

HERE = Path(__file__).parent
TRIAL = HERE.parent / 'experiments/20261028_pitch_nstep'


def grid(common_only=False):
    v = [dict(id='zero', direction='none', delta_rad=0., vector=[0., 0., 0.])]
    directions = [('common', [1, 1, 1])]
    if not common_only:
        directions += [(f'unit{i+1}', [int(j == i) for j in range(3)]) for i in range(3)]
    for name, vector in directions:
        for delta in (-.005, .005):
            v.append(dict(id=f'{name}_{delta:+.3f}', direction=name, delta_rad=delta, vector=[delta*x for x in vector]))
    return v


def actor_hash(agent):
    return hashlib.sha256(b''.join(v.detach().cpu().numpy().tobytes() for v in agent.actors.state_dict().values())).hexdigest()


def parameter_hash(agent):
    return hashlib.sha256(b''.join(v.detach().cpu().numpy().tobytes() for name in
           ('actors', 'critics', 'target_actors', 'target_critics') for v in getattr(agent, name).state_dict().values())).hexdigest()


def branch_key(source_actor, anchor, raw, continuation_actor):
    """Case/run are isolated by the enclosing cache; raw flags also remain identical."""
    return source_actor, anchor, raw.tobytes(), continuation_actor


def charge(root, steps, label, limit=58088):
    ledger = root / 'evaluation_budget.jsonl'
    previous = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()] if ledger.exists() else []
    total = sum(r['reserved_steps'] for r in previous)
    if total + steps > limit:
        raise ValueError('conservative evaluation budget exhausted, including interrupted reservations')
    with ledger.open('a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(dict(reserved_steps=steps, label=label, cumulative_reserved=total + steps)) + '\n')


def role_agents(run, selection):
    from .nstep_algorithm import NStepMADDPG
    roles = {}
    paths = {}
    for n in (1, 8):
        r = next(r for r in selection['results'] if r['run'] == run and r['n'] == n)
        for state in ('initial', 'selected', 'final'):
            label = f'n{n}_{state}'
            roles[label] = NStepMADDPG.load(r[state], n)[0]
            paths[label] = r[state]
    return roles, paths


def original_validation(checkpoint, case_id):
    directory = Path(checkpoint).parent
    metric = next(r for r in read_csv(directory / 'validation_metrics.csv') if r['case_id'] == case_id)
    with gzip.open(directory / 'validation_traces.csv.gz', 'rt', encoding='utf-8') as f:
        rows = [r for r in csv.DictReader(f) if r['case_id'] == case_id]
    assert len(rows) == 128
    for k, v in error_parts([float(r['error_w']) for r in rows]).items():
        assert v == float(metric[k])
    return metric, rows


def replay_m(agent, obs):
    import numpy as np
    data = agent.replay.data['obs'][:agent.replay.size].reshape(agent.replay.size, -1)
    distance = np.sqrt(np.mean((data - obs.ravel())**2, axis=1))
    idx = np.argsort(distance, kind='stable')[:32]
    _, _, lengths = agent.replay.spans(idx)
    return dict(m_nearby_mean=float(lengths.mean()), m_nearby_min=int(lengths.min()),
                m_nearby_histogram=json.dumps(np.bincount(lengths, minlength=agent.n + 1).tolist()),
                training_m_histogram=json.dumps(agent.replay.m_histogram.tolist()), return_horizon=agent.n)


def evaluate_job(root, env, roles, paths, case, wind, run, out):
    import numpy as np
    prefixes, branches = {}, {}
    traces, metrics, q_rows, own_rows, full_rows = [], [], [], [], []
    before_parameters = {k: parameter_hash(a) for k, a in roles.items()}
    used = reused = 0
    for label, agent in roles.items():
        policy = actor_hash(agent)
        metric, old = original_validation(paths[label], case['id'])
        full_rows.append(dict(run=run, role=label, **metric))
        if policy in prefixes:
            reused += 96
            continue
        charge(root, 96, f'run{run}:{case["id"]}:{label}:prefix')
        obs, info = reset_case(env, case, wind)
        snapshots = {}; max_power = max_action = 0.
        for t in range(96):
            if t == 32:
                snapshots[t] = clone_env(env), obs.copy(), deepcopy(info)
            action = agent.act(obs)
            obs, _, done, _, info = env.step(action); used += 1
            expected = old[t]
            max_power = max(max_power, abs(info['error_w'] - float(expected['error_w'])))
            for i in range(3):
                command = env.low[1] + (info['executed_action'][i, 1] + 1) * (env.high[1] - env.low[1]) / 2
                max_action = max(max_action, abs(command - float(expected[f'pitch_command_{i}'])) * 2 / (env.high[1] - env.low[1]))
            assert not done
        snapshots[96] = clone_env(env), obs.copy(), deepcopy(info)
        assert max_power <= 20. and max_action <= 1e-5, (max_power, max_action)
        prefixes[policy] = snapshots

    def fork(source, anchor, variant, continuation):
        nonlocal used, reused
        source_hash, continuation_hash = actor_hash(source), actor_hash(continuation)
        original, obs, before = prefixes[source_hash][anchor]
        raw, executed = corrected_action(original, source.act(obs), variant)
        key = branch_key(source_hash, anchor, raw, continuation_hash)
        if key in branches:
            reused += 32
            return branches[key], executed
        charge(root, 32, f'run{run}:{case["id"]}:{anchor}:{variant["id"]}:{source_hash[:8]}:{continuation_hash[:8]}')
        branch = clone_env(original); data = []
        for h in range(32):
            action = raw if h == 0 else continuation.act(obs)
            nxt, reward, done, _, after = branch.step(action); used += 1
            assert done == (anchor + h + 1 == 128)
            row = trace_row(branch, before, action, variant, after, reward, h + 1)
            row['branch_id'] = len(branches)
            row['anchor'] = anchor
            data.append(row); obs, before = nxt, after
        branches[key] = data
        traces.extend(data)
        return data, executed

    identity = dict(run=run, case_id=case['id'], family=case['family'], target_w=case['target_w'], initial_pitch_rad=case['initial_pitch_rad'])
    parent = roles['n1_initial']
    for anchor in (32, 96):
        original, obs, info = prefixes[actor_hash(parent)][anchor]
        variants = grid()
        actions = [corrected_action(original, parent.act(obs), v)[1] for v in variants]
        for role, agent in roles.items():
            values = critic_probe(agent, obs, actions)
            supported = support(agent, obs, actions)
            m = replay_m(agent, obs)
            for i, variant in enumerate(variants):
                q_rows.append(dict(**identity, anchor=anchor, role=role, variant=variant['id'], direction=variant['direction'],
                     q_mean=float(values[i].mean()), **{f'q_{j}':float(values[i,j]) for j in range(3)}, **supported[i], **m))
        for continuation_name in ('n1_initial', 'n8_selected'):
            for variant in variants:
                data, _ = fork(parent, anchor, variant, roles[continuation_name])
                for horizon in (8, 32):
                    metrics.append(dict(**identity, anchor=anchor, continuation=continuation_name, variant=variant['id'],
                        direction=variant['direction'], horizon=horizon, branch_id=data[0]['branch_id'], **totals(data[:horizon], .99)))
                if continuation_name == 'n1_initial' and variant['id'] == 'zero':
                    _, old = original_validation(paths['n1_initial'], case['id'])
                    assert max(abs(v['error_w'] - float(old[anchor+i]['error_w'])) for i,v in enumerate(data)) <= 20.
        for role, agent in roles.items():
            own_env, own_obs, _ = prefixes[actor_hash(agent)][anchor]
            variants = grid(True)
            actions = [corrected_action(own_env, agent.act(own_obs), v)[1] for v in variants]
            values = critic_probe(agent, own_obs, actions)
            supported = support(agent, own_obs, actions)
            m = replay_m(agent, own_obs)
            for i, variant in enumerate(variants):
                data, _ = fork(agent, anchor, variant, agent)
                for horizon in (8, 32):
                    own_rows.append(dict(**identity, anchor=anchor, role=role, variant=variant['id'], direction=variant['direction'],
                        horizon=horizon, branch_id=data[0]['branch_id'], q_mean=float(values[i].mean()),
                        **{f'q_{j}':float(values[i,j]) for j in range(3)}, **supported[i], **m, **totals(data[:horizon], .99)))
    assert before_parameters == {k: parameter_hash(a) for k,a in roles.items()}
    write_csv(out / 'metrics.csv', metrics); write_csv(out / 'q_scores.csv', q_rows)
    write_csv(out / 'own_policy.csv', own_rows); write_csv(out / 'full_validation_reused.csv', full_rows)
    compressed_csv(out / 'branches.csv.gz', traces)
    write_json(out / 'complete.json', dict(actual_environment_steps=used, reused_environment_steps=reused,
               parameters_unchanged=True, branches=len(branches), prefix_policies=len(prefixes),
               hashes={str(p.resolve()):digest(p) for p in out.iterdir() if p.is_file()}))


def prepare(root):
    import yaml
    source = frozen(TRIAL); selection = read_json(TRIAL / 'selection.json')
    protection = dict(source['protected_hashes'])
    for name in ('config.yaml','selection.json','cross_stream.csv','aggregate.csv','paired_groups.csv','checkpoint_degradation.csv','acceptance.json'):
        protection[str((TRIAL/name).resolve())] = digest(TRIAL/name)
    for result in selection['results']:
        for label in ('initial','selected','final'):
            p = Path(result[label]); protection[str(p)] = digest(p)
            for name in ('validation_metrics.csv','validation_traces.csv.gz'):
                protection[str(p.with_name(name))] = digest(p.with_name(name))
    for name in ('pitch_nstep_mechanism.py','pitch_nstep_handoff.py','PITCH_NSTEP_MECHANISM_PROTOCOL.md'):
        p = HERE / name; protection[str(p.resolve())] = digest(p)
    cases = [(c,w) for c,w in bank(TRIAL,'validation') if c['initial_pitch_rad'] == .04]
    assert len(cases) == 6
    root = Path(root).resolve(); root.mkdir(parents=True,exist_ok=False)
    cfg = dict(seed=42,source_commit='740d04044e6b046dfe6256bfa3c2d4ef88925783',trial=str(TRIAL.resolve()),
               base_config=source['base_config'], selection_sha256=digest(TRIAL/'selection.json'),
               anchors=[32,96], horizons=[8,32], cases=[c for c,w in cases], variants=grid(),
               own_variants=grid(True), evaluation_limit=65000, worst_mechanism_steps=51840,
               handoff_steps=6912, worst_total_steps=58752, formal_training_steps=0,test_rollout=False,
               protected_hashes=protection)
    (root/'config.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    write_csv(root/'metrics.csv',[dict(status='prepared',formal_training_steps=0)])
    write_json(root/'summary.txt',dict(seed=42,status='prepared',formal_training_steps=0,test_rollout=False))


def run(root):
    import yaml
    import torch
    from .workflow import build_env
    root=Path(root).resolve(); cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify(cfg['protected_hashes'])
    if read_json(root/'summary.txt').get('status')=='mechanism_complete':
        raise ValueError('completed evaluation frozen; use review')
    env=build_env(cfg['base_config']); selection=read_json(TRIAL/'selection.json')
    cases=[(c,w) for c,w in bank(TRIAL,'validation') if c['initial_pitch_rad']==.04]
    for run_id in (0,1,2):
        agents,paths=role_agents(run_id,selection)
        for i,(case,wind) in enumerate(cases):
            job=root/'jobs'/f'run{run_id}_case{i}'
            done=sorted(job.glob('attempt_*/complete.json'))
            if done:
                verify(read_json(done[-1])['hashes'])
            else:
                out=attempt_dir(job); evaluate_job(root,env,agents,paths,case,wind,run_id,out)
            print(json.dumps(dict(run=run_id,case=i+1,total=6)),flush=True)
    verify(cfg['protected_hashes']); review(root)


def chosen_q(row):
    return float(row['q_'+str(int(row['direction'][-1])-1)]) if row['direction'].startswith('unit') else float(row['q_mean'])


def comparison(row, base_q, base_g):
    dq=chosen_q(row)-chosen_q(dict(base_q,direction=row['direction'])); dg=float(row['discounted_return'])-float(base_g['discounted_return'])
    return dict(delta_q=dq,delta_g=dg,delta_tracking=float(row['tracking_return'])-float(base_g['tracking_return']),
                delta_action=float(row['action_return'])-float(base_g['action_return']),
                usable=int(abs(dq)>1e-5 and abs(dg)>1e-5),opposite=int(abs(dq)>1e-5 and abs(dg)>1e-5 and dq*dg<0))


def review(root):
    import numpy as np
    import yaml
    root=Path(root); cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8')); verify(cfg['protected_hashes'])
    cross,own,full,job_records=[],[],[],[]
    max_reward=max_metric=0.; branch_rows=0
    for path in sorted((root/'jobs').glob('*/attempt_*/complete.json')):
        job=read_json(path); verify(job['hashes']); job_records.append(job)
        directory=path.parent; q=read_csv(directory/'q_scores.csv'); returns=read_csv(directory/'metrics.csv')
        grouped=defaultdict(list)
        with gzip.open(directory/'branches.csv.gz','rt',encoding='utf-8') as f:
            for r in csv.DictReader(f):
                typed={k:float(v) for k,v in r.items()}; grouped[int(typed['branch_id'])].append(typed); branch_rows+=1
                max_reward=max(max_reward,abs(typed['reward']-typed['tracking_reward']-typed['action_reward']))
                assert abs(typed['tracking_reward']+100*(typed['error_w']/15e6)**2)<1e-9
        def checked(r):
            nonlocal max_metric
            actual=totals(grouped[int(r['branch_id'])][:int(r['horizon'])],.99)
            for k,v in actual.items():
                max_metric=max(max_metric,abs(v-float(r[k])))
                assert abs(v-float(r[k]))<=max(1e-7,abs(v)*1e-11)
        for r in returns: checked(r)
        ret={(r['anchor'],r['variant'],r['continuation'],r['horizon']):r for r in returns}
        qs={(r['anchor'],r['variant'],r['role']):r for r in q}
        for r in q:
            if r['variant']=='zero': continue
            for cont in ('n1_initial','n8_selected'):
                for horizon in ('8','32'):
                    g=ret[r['anchor'],r['variant'],cont,horizon]; base=ret[r['anchor'],'zero',cont,horizon]
                    cross.append(dict(**r,continuation=cont,horizon=horizon,
                        discounted_return=g['discounted_return'],tracking_return=g['tracking_return'],action_return=g['action_return'],
                        **comparison(dict(r,**{k:g[k] for k in ('discounted_return','tracking_return','action_return')}),qs[r['anchor'],'zero',r['role']],base)))
        rows=read_csv(directory/'own_policy.csv'); zero={(r['anchor'],r['role'],r['horizon']):r for r in rows if r['variant']=='zero'}
        for r in rows:
            checked(r)
            if r['variant']!='zero':
                base=zero[r['anchor'],r['role'],r['horizon']]
                own.append(dict(**r,**comparison(r,base,base)))
        full.extend(read_csv(directory/'full_validation_reused.csv'))
    assert len(job_records)==18
    def aggregate(rows,kind):
        result=[]
        for role in sorted({r['role'] for r in rows}):
            for horizon in ('8','32'):
                for continuation in (('n1_initial','n8_selected') if kind=='cross' else ('self',)):
                    for run_id in ('all','0','1','2'):
                        part=[r for r in rows if r['role']==role and r['horizon']==horizon and
                              (r.get('continuation','self')==continuation) and (run_id=='all' or str(r['run'])==run_id)]
                        usable=[r for r in part if r['usable']]
                        inside=[r for r in usable if float(r['local_pitch_outside_fraction'])==0]
                        result.append(dict(kind=kind,role=role,horizon=horizon,continuation=continuation,run=run_id,
                             slots=len(part),usable=len(usable),opposite=sum(r['opposite'] for r in usable),
                             inside_usable=len(inside),inside_opposite=sum(r['opposite'] for r in inside),
                             local_outside_slots=sum(float(r['local_pitch_outside_fraction'])>0 for r in part),
                             positive_tracking_negative_total=sum(float(r['delta_tracking'])>1e-5 and float(r['delta_g'])< -1e-5 for r in part)))
        return result
    write_csv(root/'metrics.csv',cross);write_csv(root/'own_policy.csv',own);write_csv(root/'full_validation_reused.csv',full)
    write_csv(root/'ranking_summary.csv',aggregate(cross,'cross')+aggregate(own,'own'))
    used=sum(j['actual_environment_steps'] for j in job_records);reused=sum(j['reused_environment_steps'] for j in job_records)
    reserved=sum(json.loads(line)['reserved_steps'] for line in (root/'evaluation_budget.jsonl').read_text().splitlines())
    handoff_summary=root/'handoff_validation_replay/summary.txt'
    handoff=read_json(handoff_summary)['actual_environment_steps'] if handoff_summary.exists() else 0
    write_json(root/'summary.txt',dict(seed=42,status='mechanism_complete',formal_training_steps=0,test_rollout=False,jobs=18,
        actual_mechanism_steps=used,reused_new_run_steps=reused,conservative_reserved_steps=reserved,
        actual_handoff_steps=handoff,maximum_possible_uncommitted_steps=reserved-used-handoff,maximum_metric_difference=max_metric,maximum_reward_components_difference=max_reward,
        branch_trace_rows=branch_rows,cross_direction_rows=len(cross),own_direction_rows=len(own),reused_full_validation_rows=len(full),
        protected_files=len(cfg['protected_hashes']),protected_files_unchanged=True,parameters_unchanged=True))
    print((root/'summary.txt').read_text(),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('prepare','run','review'));p.add_argument('--output',required=True)
    args=p.parse_args();activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    {'prepare':prepare,'run':run,'review':review}[args.command](args.output)


if __name__=='__main__': main()
