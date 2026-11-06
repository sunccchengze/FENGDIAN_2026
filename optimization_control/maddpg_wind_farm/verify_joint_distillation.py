"""Read-only source checks, checkpoint restore and Python figures for joint transfer."""
from __future__ import annotations
import argparse
import csv
import io
import json
from pathlib import Path
from .fixed_pinn_demo import activate_runtime,digest

def verify(root):
    import numpy as np
    import torch
    import yaml
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .algorithm import MADDPG
    from .progressive_random_control import verify_hashes
    from .random_wind_training import write_json,write_csv
    root=Path(root); saved=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    selection=json.loads((root/'selection.json').read_text(encoding='utf-8'))
    verify_hashes(saved['source_hashes']); verify_hashes(selection['hashes'])
    assert digest(root/'config.yaml')==selection['root_config_sha256']
    assert digest(root/'bank/manifest.json')==selection['bank_sha256']
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    checks=[]
    paths=[v['checkpoint'] for v in saved['bootstrap'].values()]
    paths += [r[label] for r in selection['results'] for label in ('initial','final')]
    for path in dict.fromkeys(paths):
        before=digest(path); agent,meta=MADDPG.load(path)
        stream=io.BytesIO(); agent.save(stream,meta); stream.seek(0); other,restored=MADDPG.load(stream)
        np.testing.assert_equal(meta,restored)
        obs=agent.replay.data['obs'][0]
        np.testing.assert_array_equal(agent.act(obs,.03),other.act(obs,.03))
        assert agent.update()==other.update()
        for kind in ('actors','target_actors','critics','target_critics'):
            assert all(torch.equal(v,getattr(other,kind).state_dict()[k]) for k,v in getattr(agent,kind).state_dict().items())
        assert digest(path)==before
        checks.append(dict(checkpoint=path,sha256=before,noise_actions_and_next_update_exact=True))
    rows=[]
    for path in sorted(root.glob('*_run_*/distillation.json')):
        report=json.loads(path.read_text(encoding='utf-8'))
        for row in report['reports']: rows.append(dict(job=path.parent.name,**row))
    write_csv(root/'distillation_metrics.csv',rows)
    if not selection['results']:
        write_csv(root/'metrics.csv',rows)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    labels=[]; old=[]; new=[]
    for job in dict.fromkeys(r['job'] for r in rows):
        for candidate in sorted(set(r['candidate'] for r in rows if r['job']==job)):
            subset=[r for r in rows if r['job']==job and r['candidate']==candidate]
            labels.append(f"stream {job.rsplit('_',1)[1]} / candidate {candidate+1}")
            old.append(max(r['old_held_max'] for r in subset)); new.append(max(r['new_held_max'] for r in subset))
    for ax,values,threshold,title in zip(axes,(old,new),(.02,.05),('Previously enabled action drift','New speed reference fit')):
        ax.bar(np.arange(len(values)),values,color='#4878a8'); ax.axhline(threshold,color='#c44e52',ls='--',label=f'Protocol limit {threshold}')
        ax.set_xticks(np.arange(len(labels)),labels,rotation=35,ha='right'); ax.set_ylabel('Maximum normalized action error')
        ax.set_title(title); ax.legend(); ax.grid(axis='y',alpha=.2)
    fig.suptitle('Joint MLP distillation: internal validation (not independent test)')
    fig.savefig(root/'distillation_errors.png',dpi=180); fig.savefig(root/'distillation_errors.pdf'); plt.close(fig)
    metric_count=0; maximum=0.
    if (root/'test/trajectories.csv').exists():
        grouped={}
        with (root/'test/trajectories.csv').open(encoding='utf-8') as f:
            for row in csv.DictReader(f):
                key=tuple(row[k] for k in ('stage','run_id','controller','case_id'))
                grouped.setdefault(key,[]).append(float(row['farm_power_w'])-float(row['target_w']))
        with (root/'test/metrics.csv').open(encoding='utf-8') as f:
            for row in csv.DictReader(f):
                key=tuple(row[k] for k in ('stage','run_id','controller','case_id'))
                maximum=max(maximum,abs(float(np.sqrt(np.mean(np.square(grouped[key]))))-float(row['rmse_w']))); metric_count+=1
        assert maximum<1e-7
    report=dict(seed=42,protected_files=len(saved['source_hashes']),protected_unchanged=True,root_config_and_bank_locked=True,
        checkpoints=checks,distillation_network_candidate_rows=len(rows),distillation_optimizer_updates=sum(r['updates'] for r in rows),
        test_metric_rows=metric_count,max_rmse_recompute_difference_w=maximum,independent_test_released=(root/'test').exists(),
        automatic_cli_resume_supported=False,physical_validation=False)
    write_json(root/'verification.json',report)
    summary=json.loads((root/'summary.txt').read_text(encoding='utf-8'))
    summary.update(verification=report,distillation_diagnostics=rows,protocol_sha256=digest(Path(__file__).with_name('configs')/'joint_distillation.yaml'),
        limitation='No candidate state persisted: cannot localize worst-error Ueff/clip boundary; no new training for diagnosis',
        reproducible_commands=['.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.joint_distillation all --output NEW_DIRECTORY',
        '.venv/Scripts/python.exe -B -m optimization_control.maddpg_wind_farm.verify_joint_distillation --output EXPERIMENT_DIRECTORY'])
    write_json(root/'summary.txt',summary)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--output',required=True); args=ap.parse_args()
    activate_runtime('.venv/pinn_tf216'); verify(args.output)
if __name__=='__main__': main()
