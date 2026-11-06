"""Load the three locked pitch candidates, then replay validation without updates."""
from __future__ import annotations
import argparse
import csv
import gzip
import json
from pathlib import Path

from .fixed_pinn_demo import activate_runtime,digest
from .pitch_cross_wind_diagnostic import ORIGINAL,read_csv,write_csv,write_json
from .pitch_nstep_trial import read_json,verify,frozen,bank,capture
from .pitch_nstep_mechanism import TRIAL,charge,parameter_hash


def validate_manifest(manifest):
    if manifest['seed']!=42 or manifest['status']!='experimental_candidates_not_default':
        raise ValueError('candidate role identity invalid')
    if manifest['control_mask']!=[0,1,0] or manifest['observation_shape']!=[3,15]:
        raise ValueError('pitch-only [3,15] candidate contract required')
    if manifest['n']!=8 or manifest['tail_rule']!='actual_m_bootstrap_unless_true_terminal_v1':
        raise ValueError('return format contract changed')
    if [v['run'] for v in manifest['candidates']]!=[0,1,2]:
        raise ValueError('all three frozen streams required, no test-based stream picking')
    verify(manifest['protected_hashes'])
    verify({v['checkpoint']:v['sha256'] for v in manifest['candidates']})
    selection=read_json(manifest['source_selection'])
    if digest(manifest['source_selection'])!=manifest['source_selection_sha256']:
        raise ValueError('authoritative selection digest changed')
    for entry in manifest['candidates']:
        old=next(r for r in selection['results'] if r['n']==8 and r['run']==entry['run'])
        if (entry['checkpoint'],entry['sha256'],entry['selected_step'])!=(old['selected'],old['hashes'][old['selected']],old['selected_step']):
            raise ValueError('candidate differs from locked validation selection')


def load_candidate(manifest_path,run):
    from .nstep_algorithm import NStepMADDPG
    manifest=read_json(manifest_path);validate_manifest(manifest)
    entry=next(v for v in manifest['candidates'] if v['run']==run)
    agent,meta=NStepMADDPG.load(entry['checkpoint'],expected_n=8)
    if list(agent.config.action_mask)!=manifest['control_mask'] or meta['config']!=manifest['base_config']:
        raise ValueError('checkpoint environment or permissions differ')
    if meta['step']!=entry['selected_step'] or meta['run']!=run or meta['root_config_sha256']!=manifest['trial_config_sha256']:
        raise ValueError('frozen selection/recovery metadata differ')
    return agent,meta,manifest


def create(root):
    from .nstep_algorithm import NStepMADDPG,TAIL_RULE
    from .workflow import build_env
    root=Path(root).resolve();source=frozen(TRIAL);selection=read_json(TRIAL/'selection.json')
    if (root/'candidate_manifest.json').exists():raise FileExistsError('handoff manifest immutable')
    env=build_env(source['base_config']);normalization=env.normalization()
    write_json(root/'candidate_normalization.json',normalization)
    candidates=[]
    protected={str((TRIAL/'config.yaml').resolve()):digest(TRIAL/'config.yaml'),
               str((TRIAL/'selection.json').resolve()):digest(TRIAL/'selection.json'),
               str((root/'candidate_normalization.json').resolve()):digest(root/'candidate_normalization.json')}
    for r in selection['results']:
        if r['n']!=8:continue
        agent,meta=NStepMADDPG.load(r['selected'],8)
        candidates.append(dict(run=r['run'],checkpoint=r['selected'],sha256=digest(r['selected']),selected_step=r['selected_step'],
              validation_score_w=next(x['rmse_w'] for x in r['history'] if x['step']==r['selected_step']),
              validation_rule='18_complete_128_step_case_rmse_mean_strict_improvement_including_initial',
              selected_by_test=False,validation_metrics_path=str(Path(r['selected']).with_name('validation_metrics.csv')),
              validation_metrics_sha256=digest(Path(r['selected']).with_name('validation_metrics.csv')),
              normalization_path=str((root/'candidate_normalization.json').resolve()),updates=agent.updates,
              replay_size=agent.replay.size,replay_position=agent.replay.position,replay_insertions=agent.replay.insertions,
              m_histogram=agent.replay.m_histogram.tolist(),recovery_metadata_keys=sorted(meta),
              inheritance='all online/target networks, Adam, replay and algorithm/replay/torch/noise RNG retained'))
    for p,h in source['protected_hashes'].items():protected[p]=h
    protected[str(Path(__file__).resolve())]=digest(__file__)
    manifest=dict(seed=42,status='experimental_candidates_not_default',source_commit='740d04044e6b046dfe6256bfa3c2d4ef88925783',
         source_selection=str((TRIAL/'selection.json').resolve()),source_selection_sha256=digest(TRIAL/'selection.json'),
         trial_config_sha256=digest(TRIAL/'config.yaml'),candidates=candidates,control_mask=[0,1,0],observation_shape=[3,15],
         normalized_action_shape=[3,3],n=8,tail_rule=TAIL_RULE,base_config=source['base_config'],normalization=normalization,
         model_version=source['base_config']['plant']['model_version'],
         load_entry='optimization_control.maddpg_wind_farm.nstep_algorithm.NStepMADDPG.load(path, expected_n=8)',
         checked_loader='optimization_control.maddpg_wind_farm.pitch_nstep_handoff.load_candidate(manifest_path, run)',
         runtime_python=str(ORIGINAL/'.venv/Scripts/python.exe'),runtime_site_packages=str(ORIGINAL/'.venv/pinn_tf216'),
         action_meaning='normalized total command reference, projected by unchanged environment; only pitch learned',
         default_or_speed_parent_changed=False,
         limitations=['synthetic quasi-static model only','biased off-policy multistep engineering candidate',
                      'selected gate passed; final ramp advantage weakened','stream2 generalization regressed',
                      'pressure all paired slots worse than P/PI','not evidence of real Q correction or speed-channel benefit'],
         protected_hashes=protected)
    validate_manifest(manifest);write_json(root/'candidate_manifest.json',manifest)
    print('Three locked experimental candidates recorded',flush=True)


def replay(root):
    import numpy as np
    from .workflow import build_env
    root=Path(root).resolve();manifest_path=root/'candidate_manifest.json'
    manifest=read_json(manifest_path);validate_manifest(manifest)
    out=root/'handoff_validation_replay';out.mkdir(exist_ok=False)
    rows=[];max_metric=max_trace=0.
    env=build_env(manifest['base_config']);env._baseline_config=manifest['base_config']['baselines']
    assert env.normalization()==manifest['normalization']
    cases=bank(TRIAL,'validation');assert len(cases)==18
    for run in (0,1,2):
        agent,meta,_=load_candidate(manifest_path,run);before=parameter_hash(agent)
        charge(root,2304,f'handoff_validation_run{run}',limit=65000)
        metrics,traces=capture(env,cases,agent=agent)
        old_metrics=read_csv(Path(meta['best']['checkpoint']).with_name('validation_metrics.csv'))
        old_lookup={r['case_id']:r for r in old_metrics}
        with gzip.open(Path(meta['best']['checkpoint']).with_name('validation_traces.csv.gz'),'rt',encoding='utf-8') as f:
            expected=list(csv.DictReader(f))
        assert len(expected)==len(traces)==2304
        for actual,old in zip(traces,expected):
            for key,value in actual.items():
                if key in ('case_id','split','family'):assert value==old[key]
                else:max_trace=max(max_trace,abs(float(value)-float(old[key])))
        for actual in metrics:
            old=old_lookup[actual['case_id']]
            for key,value in actual.items():
                if key in ('case_id','split','family'):assert value==old[key]
                else:max_metric=max(max_metric,abs(float(value)-float(old[key])))
            rows.append(dict(run=run,**actual))
        assert before==parameter_hash(agent)
        print(json.dumps(dict(replayed_run=run,cases=18,max_trace_difference=max_trace)),flush=True)
    assert max_metric==0. and max_trace==0.,(max_metric,max_trace)
    validate_manifest(manifest);write_csv(out/'metrics.csv',rows)
    write_json(out/'summary.txt',dict(seed=42,complete=True,new_process_load=True,validation_not_independent_test=True,
               candidates=3,cases_per_candidate=18,actual_environment_steps=6912,formal_training_steps=0,
               maximum_metric_difference=max_metric,maximum_trace_difference=max_trace,
               parameters_unchanged=True,manifest_sha256=digest(manifest_path),default_or_speed_parent_changed=False))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=('create','replay'));ap.add_argument('--output',required=True)
    args=ap.parse_args();activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    {'create':create,'replay':replay}[args.command](args.output)


if __name__=='__main__':main()
