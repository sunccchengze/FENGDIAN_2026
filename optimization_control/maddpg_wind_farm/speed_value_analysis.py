"""Finite-return aggregation, invariants and three predeclared diagnostic plots."""
from collections import defaultdict
from pathlib import Path
import json

from .anchor_closeout import read_json, read_csv, write_json, write_csv, verify_hashes, sha
from .speed_value_diagnostic import STEPS, RADII, HORIZONS, WIDTH


def load_jobs(root):
    jobs = sorted(root.glob('run_*/*/complete.json'))
    assert len(jobs) == 18
    output = []
    for lock in jobs:
        folder = lock.parent
        verify_hashes({str(folder / name): digest for name, digest in read_json(lock).items()})
        output.append((folder, read_json(folder / 'branches.json')))
    return output


def direction(value, tolerance):
    return 1 if value >= tolerance else -1 if value <= -tolerance else 0


def analyze(root, cfg):
    import numpy as np
    rows = [r for _, records in load_jobs(root) for r in records]
    assert len(rows) == cfg['expected_branches']
    centers = {(r['run_id'], r['case_id'], r['actor_step']): r for r in rows if r['mode'] == 'pulse' and r['variant'] == 'center'}
    pairs = []; horizons = []; radius_rows = []; feedback = []
    for row in rows:
        tags = {k: row[k] for k in ('run_id', 'case_id', 'family', 'target_w', 'actor_step', 'mode', 'variant', 'radius_rad_s')}
        center = centers[(row['run_id'], row['case_id'], row['actor_step'])]
        for h in HORIZONS:
            horizons.append(dict(**tags, horizon=h, realized_return=row[f'return_{h}'],
                tracking_return=row[f'tracking_{h}'], action_penalty_return=row[f'penalty_{h}'],
                reward_rounding=row[f'return_{h}']-row[f'tracking_{h}']-row[f'penalty_{h}'],
                rmse_w=row[f'rmse_{h}_w'], start_state_sha256=row['start_state_sha256']))
        if row['mode'] == 'pulse' and row['focus_agent'] >= 0:
            i = row['focus_agent']
            effective = (row['first_action'][i][2] - center['first_action'][i][2]) * WIDTH / 2
            for h in HORIZONS:
                delta_g = row[f'return_{h}'] - center[f'return_{h}']
                for rater_index, rater_step in enumerate(STEPS):
                    for kind_index, kind in enumerate(('online', 'target')):
                        delta_q = row['q_scores'][rater_index][kind_index][i] - center['q_scores'][rater_index][kind_index][i]
                        ds, qs = direction(delta_g, cfg['thresholds']['return_difference']), direction(delta_q, cfg['thresholds']['q_difference'])
                        valid = abs(effective) >= cfg['thresholds']['action_rad_s']
                        gradient = center['q_gradient_' + kind][i] if rater_step == row['actor_step'] else None
                        pairs.append(dict(**tags, horizon=h, turbine=i, rater_step=rater_step, critic_kind=kind,
                            requested_delta_rad_s=row['requested_delta_rad_s'], effective_delta_rad_s=effective,
                            action_clipped=abs(effective-row['requested_delta_rad_s'])>1e-6,
                            delta_return=delta_g, delta_tracking=row[f'tracking_{h}']-center[f'tracking_{h}'],
                            delta_penalty=row[f'penalty_{h}']-center[f'penalty_{h}'],
                            delta_rmse_w=row[f'rmse_{h}_w']-center[f'rmse_{h}_w'], delta_q=delta_q,
                            q_gradient_phys=gradient if gradient is not None else '',
                            action_valid=valid, material_return=ds!=0, q_resolved=qs!=0,
                            mismatch=bool(valid and ds and qs and ds!=qs),
                            useful_finite_action=bool(valid and ds>0), useful_action_downranked=bool(valid and ds>0 and qs<0),
                            local_gradient_opposes_return=bool(gradient is not None and valid and ds and direction(gradient*effective,cfg['thresholds']['q_difference'])==-ds),
                            diagonal=rater_step==row['actor_step']))
        if row['mode'].startswith('persistent') or (row['mode']=='pulse' and row['variant']=='center'):
            source = 'own' if row['mode'] == 'persistent_own' else 'canonical'
            radius_rows.append(dict(**tags, state_source=source, return_8=row['return_8'], return_32=row['return_32'],
                tracking_32=row['tracking_32'], penalty_32=row['penalty_32'], rmse_32_w=row['rmse_32_w']))
        if row['mode'] == 'offline_parent_pitch':
            feedback.append(dict(**tags, normal_return_8=center['return_8'], replay_return_8=row['return_8'],
                normal_return_32=center['return_32'], replay_return_32=row['return_32'],
                normal_rmse_32_w=center['rmse_32_w'], replay_rmse_32_w=row['rmse_32_w'],
                replay_minus_normal_return_32=row['return_32']-center['return_32'], deployable=False))
    grouped = defaultdict(list)
    for row in pairs:
        if row['diagonal']:
            grouped[(row['run_id'],row['actor_step'],row['horizon'],row['critic_kind'])].append(row)
    metrics = []
    for (run, step, horizon, kind), part in sorted(grouped.items()):
        valid = [r for r in part if r['action_valid'] and r['material_return']]
        resolved = [r for r in valid if r['q_resolved']]
        useful = [r for r in valid if r['useful_finite_action']]
        metrics.append(dict(run_id=run,actor_step=step,horizon=horizon,critic_kind=kind,
            comparisons=len(part),nondegenerate=sum(r['action_valid'] for r in part),material_returns=len(valid),
            resolved=len(resolved),mismatches=sum(r['mismatch'] for r in part),
            mismatch_fraction=sum(r['mismatch'] for r in part)/len(resolved) if resolved else '',
            useful_actions=len(useful),useful_downranked=sum(r['useful_action_downranked'] for r in part),
            gradient_opposes=sum(r['local_gradient_opposes_return'] for r in part),
            action_clipped=sum(r['action_clipped'] for r in part),formal_training_steps=0))
    write_csv(root/'metrics.csv',metrics)
    write_csv(root/'pairwise.csv',pairs)
    write_csv(root/'finite_returns.csv',horizons)
    write_csv(root/'radius_comparison.csv',radius_rows)
    write_csv(root/'pitch_feedback.csv',feedback)
    verify(root,cfg)
    write_json(root/'summary.txt',dict(seed=42,status='completed',formal_training_steps=0,optimizer_updates=0,
        checkpoints=15,canonical_states=18,additional_own_states=30,branches=len(rows),horizon_rows=len(horizons),
        pair_rows=len(pairs),counterfactual_environment_steps=64512,source_test_performance_read=False,
        physical_validation=False,interpretation='Finite deterministic returns and model-local directions; not long-run expected Q.',
        verification='verification.json',next_proposal='See SPEED_VALUE_RESULTS.md; no new training is authorized by this diagnostic.'))
    write_json(root/'complete.json',{p.name:sha(p) for p in root.iterdir() if p.is_file() and p.name not in ('complete.json','summary.txt')})


def verify(root, cfg):
    import numpy as np
    jobs = load_jobs(root); count=steps=0; max_return_error=0.; max_terms_error=0.; max_power=0.; max_gamma=0.
    for folder, rows in jobs:
        audit=read_json(folder/'audit.json');steps+=audit['warmup_environment_steps']+audit['branch_environment_steps']
        assert audit['formal_training_steps']==audit['optimizer_updates']==0 and audit['source_agents_unchanged'] and audit['torch_rng_unchanged']
        with np.load(folder/'ledger.npz') as ledger:
            for j,row in enumerate(rows):
                for h in HORIZONS:
                    error=abs(float((.99**np.arange(h))@ledger['reward'][j,:h])-row[f'return_{h}'])
                    max_return_error=max(max_return_error,error)
                    for key, field in (('tracking','tracking'),('penalty','penalty')):
                        assert abs(float((.99**np.arange(h))@ledger[key][j,:h])-row[f'{field}_{h}'])<1e-10
                max_terms_error=max(max_terms_error,float(np.abs(ledger['reward'][j]-ledger['tracking'][j]-ledger['penalty'][j]).max()))
                max_power=max(max_power,float(np.abs(ledger['power'][j].sum(axis=1)-ledger['error_w'][j]-row['target_w']).max()))
                expected=(ledger['physical'][j,:, :,0]-ledger['wind'][j,:,1,None]+np.pi)%(2*np.pi)-np.pi
                max_gamma=max(max_gamma,float(np.abs(expected-ledger['gamma'][j]).max()))
                previous=np.concatenate((np.asarray(row['start_physical'])[None],ledger['physical'][j,:-1]))
                rates=np.abs(ledger['physical'][j]-previous).max(axis=(0,1))
                assert np.all(rates<=np.asarray(cfg['environment_config']['environment']['rate_limits'])+1e-7)
                previous_action=np.concatenate((np.asarray(row['start_command'],np.float32)[None],ledger['executed'][j,:-1]))
                np.testing.assert_allclose(np.mean((ledger['executed'][j]-previous_action)**2,axis=(1,2)),ledger['action_change'][j],atol=1e-8)
                count+=1
    assert (count,steps)==(1902,64512) and steps<=cfg['max_environment_steps']
    assert max_return_error<1e-10 and max_terms_error<1e-7 and max_power==0 and max_gamma==0
    verify_hashes(cfg['source_hashes']);verify_hashes(cfg['executed_code_hashes'])
    write_json(root/'verification.json',dict(seed=42,passed=True,branches=count,environment_steps=steps,
        formal_training_steps=0,optimizer_updates=0,max_return_recompute_error=max_return_error,
        max_reward_terms_rounding=max_terms_error,max_power_error_w=max_power,max_gamma_error=max_gamma,
        old_experiments_read_only=True,finite_return_not_long_run_Q=True))


def figures(root,cfg):
    import os
    os.environ.setdefault('MPLCONFIGDIR',str(root/'plot_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    out=root/'figures';out.mkdir(exist_ok=False)
    metrics=read_csv(root/'metrics.csv');pairs=read_csv(root/'pairwise.csv');radius=read_csv(root/'radius_comparison.csv');feedback=read_csv(root/'pitch_feedback.csv')
    generated={}
    def save(fig,name):
        for ext in ('png','pdf'):
            path=out/f'{name}.{ext}';fig.savefig(path,dpi=170);generated[path.name]=sha(path)
        plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,4.6),layout='constrained')
    for ax,h in zip(axes,HORIZONS):
        matrix=np.asarray([[float(next(r for r in metrics if int(r['run_id'])==run and int(r['actor_step'])==step and int(r['horizon'])==h and r['critic_kind']=='online')['mismatch_fraction'] or 'nan') for step in STEPS] for run in range(3)])
        im=ax.imshow(matrix,vmin=0,vmax=1,cmap='YlOrRd',aspect='auto')
        for run in range(3):
            for j,step in enumerate(STEPS):
                r=next(r for r in metrics if int(r['run_id'])==run and int(r['actor_step'])==step and int(r['horizon'])==h and r['critic_kind']=='online')
                ax.text(j,run,f"{100*matrix[run,j]:.0f}%\n{r['mismatches']}/{r['resolved']}",ha='center',va='center',fontsize=9)
        ax.set(xticks=range(5),xticklabels=STEPS,yticks=range(3),yticklabels=range(3),xlabel='Snapshot step',ylabel='Stream',title=f'Online Q vs {h}-step realized return')
    fig.colorbar(im,ax=axes,label='Opposite ordering / material resolved pairs');fig.suptitle('Same canonical states | current-policy continuation | finite realized returns only')
    save(fig,'value_ordering')
    fig,axes=plt.subplots(1,3,figsize=(15,4.8),layout='constrained')
    matrices=[]
    for run in range(3):
        matrix=[]
        for step in STEPS:
            part=[r for r in radius if r['state_source']=='canonical' and int(r['run_id'])==run and int(r['actor_step'])==step]
            base=np.mean([float(r['return_32']) for r in part if float(r['radius_rad_s'])==0])
            matrix.append([np.mean([float(r['return_32']) for r in part if float(r['radius_rad_s'])==rad])-base for rad in RADII])
        matrices.append(np.asarray(matrix))
    limit=max(abs(m).max() for m in matrices)
    for run,(ax,matrix) in enumerate(zip(axes,matrices)):
        im=ax.imshow(matrix,cmap='RdBu',vmin=-limit,vmax=limit,aspect='auto')
        for i in range(5):
            for j in range(4):ax.text(j,i,f'{matrix[i,j]:+.3f}',ha='center',va='center',fontsize=8)
        ax.set(xticks=range(4),xticklabels=RADII,yticks=range(5),yticklabels=STEPS,xlabel='Persistent speed radius [rad/s]',ylabel='Frozen head snapshot',title=f'Stream {run}')
    fig.colorbar(im,ax=axes,label='32-step return minus zero-speed parent');fig.suptitle('Weights x radius separated | same initial state / wind / actuators | validation only')
    save(fig,'radius_and_weights')
    fig,axes=plt.subplots(1,3,figsize=(15,4.5),layout='constrained')
    for run,ax in enumerate(axes):
        part=[r for r in feedback if int(r['run_id'])==run]
        closed=[np.mean([float(r['normal_return_32']) for r in part if int(r['actor_step'])==s]) for s in STEPS[1:]]
        replay=[np.mean([float(r['replay_return_32']) for r in part if int(r['actor_step'])==s]) for s in STEPS[1:]]
        ax.plot(STEPS[1:],closed,'o-',label='Parent mapping on current state');ax.plot(STEPS[1:],replay,'s--',label='Offline parent pitch replay')
        ax.set(xlabel='Snapshot step',ylabel='32-step realized return',title=f'Stream {run}');ax.grid(alpha=.2)
    axes[0].legend(fontsize=8);fig.suptitle('Feedback intervention | replay uses unavailable parent-world future commands; diagnostic only')
    save(fig,'pitch_feedback')
    write_json(out/'manifest.json',dict(generated=generated,model_calls=0,formal_training_steps=0))
