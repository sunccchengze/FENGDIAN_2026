"""Generate training-only wind, fit once, and score the frozen causal forecast."""
from pathlib import Path
import argparse
import hashlib
from .anchor_closeout import read_json,write_json,read_csv,write_csv,sha,verify_hashes,checked_output

DEFAULT=Path(__file__).with_name('configs')/'history_forecast.yaml'


def context(root):
    import yaml
    cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify_hashes(cfg['source_hashes']);verify_hashes(cfg['executed_code_hashes'])
    return cfg


def prepare(root):
    import yaml
    import numpy as np
    from ..environments.farm_inflow import InflowTrace,generate_inflow
    repo=Path(__file__).resolve().parents[2];source=repo/'optimization_control/experiments/20261029_speed_midgrid'
    root=checked_output(root,repo,Path('.'))
    p=yaml.safe_load(DEFAULT.read_text(encoding='utf-8'))
    assert read_json(source/'git_delivery.json')['commit']==p['source_commit']
    old=yaml.safe_load((source/'config.yaml').read_text(encoding='utf-8'))
    protected=dict(old['source_hashes']);protected.update(old['executed_code_hashes'])
    for name in ('config.yaml','metrics.csv','trajectories.csv','bank/manifest.json','budget.json','summary.txt','git_delivery.json','output_manifest.csv'):
        protected[str(source/name)]=sha(source/name)
    for case in read_json(source/'bank/manifest.json')['cases']:
        for name in ('plans.json','current_world.npz','grid17.csv','complete.json'):
            path=source/'cases'/case['case_id']/name;protected[str(path)]=sha(path)
    verify_hashes(protected)
    code={str(path):sha(path) for path in (Path(__file__),Path(__file__).with_name('history_wind_forecast.py'),DEFAULT,
        Path(__file__).with_name('HISTORY_FORECAST_PROTOCOL.md'),repo/'optimization_control/tests/test_history_forecast.py')}
    root.mkdir(parents=True,exist_ok=False);(root/'fit_bank').mkdir();(root/'score_bank').mkdir()
    manifest=[];seen=set()
    for f,family in enumerate(p['families']):
        for i in range(p['fit_trajectories_per_family']):
            episode=p['fit_episode_offset']+f*p['fit_trajectories_per_family']+i
            config=__import__('copy').deepcopy(old['base_config']['environment']['inflow']);config['speed']['scenario']=family
            wind=generate_inflow(config,dt_s=1,horizon=128,seed=42,split='train',episode=episode)
            path=root/'fit_bank'/f'{family}_{i:03}.csv';wind.save(path)
            digest=hashlib.sha256(wind.values.astype(np.float32).tobytes()).hexdigest();assert digest not in seen;seen.add(digest)
            manifest.append(dict(split='fit_train',family=family,path=str(path.relative_to(root)),values_sha256=digest,csv_sha256=sha(path),json_sha256=sha(path.with_suffix('.json'))))
    score=[];by_digest={}
    for case in read_json(source/'bank/manifest.json')['cases']:
        path=source/'bank'/case['path'];wind=InflowTrace.load(path);digest=hashlib.sha256(wind.values.astype(np.float32).tobytes()).hexdigest()
        assert digest not in seen
        split='decision_'+case['split']
        if digest in by_digest:
            entry=by_digest[digest];assert entry['split']==split and entry['family']==case['family'];entry['case_ids'].append(case['case_id']);continue
        dest=root/'score_bank'/case['path'];dest.write_bytes(path.read_bytes());dest.with_suffix('.json').write_bytes(path.with_suffix('.json').read_bytes())
        protected[str(path)]=sha(path);protected[str(path.with_suffix('.json'))]=sha(path.with_suffix('.json'))
        entry=dict(split=split,family=case['family'],path=str(dest.relative_to(root)),values_sha256=digest,csv_sha256=sha(dest),
            json_sha256=sha(dest.with_suffix('.json')),case_ids=[case['case_id']]);by_digest[digest]=entry;score.append(entry)
    write_json(root/'bank_manifest.json',dict(seed=42,fit=manifest,score=score,original_cases=36))
    cfg=dict(seed=42,protocol=p,worktree=str(repo),source=str(source),base_config=old['base_config'],parents=old['parents'],
        source_hashes=protected,executed_code_hashes=code,bank_manifest_sha256=sha(root/'bank_manifest.json'),
        source_inventory=sorted(str(x) for x in source.rglob('*') if x.is_file()))
    (root/'config.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    write_csv(root/'metrics.csv',[dict(status='prepared',formal_RL_steps=0)])
    write_json(root/'summary.txt',dict(status='prepared',formal_RL_steps=0,PINN_mock_rows=0))
    print('Prepared fit',len(manifest),'unique score',len(score),flush=True)


def evaluate(root):
    import numpy as np
    from .history_wind_forecast import fit,RidgeForecast,score,aggregate
    from ..environments.farm_inflow import InflowTrace
    cfg=context(root);manifest=read_json(root/'bank_manifest.json')
    assert sha(root/'bank_manifest.json')==cfg['bank_manifest_sha256']
    if (root/'forecast_model.npz').exists():raise ValueError('fit already exists; do not refit')
    for entry in manifest['fit']+manifest['score']:
        path=root/entry['path'];assert sha(path)==entry['csv_sha256'] and sha(path.with_suffix('.json'))==entry['json_sha256']
    values=[InflowTrace.load(root/entry['path']).values.astype(np.float32) for entry in manifest['fit']]
    model,details=fit(values);model.save(root/'forecast_model.npz');loaded=RidgeForecast.load(root/'forecast_model.npz')
    metrics=[];predictions=[]
    for i,entry in enumerate(manifest['score']):
        wind=InflowTrace.load(root/entry['path']).values.astype(np.float32)
        assert np.all(wind[:,2]==wind[0,2])
        for t in (0,8,32,64,120):np.testing.assert_array_equal(model.predict(wind[:t+1])[0],loaded.predict(wind[:t+1])[0])
        rows,raw=score(loaded,wind)
        tags=dict(trajectory=i,split=entry['split'],family=entry['family'],values_sha256=entry['values_sha256'])
        metrics.extend(dict(**tags,**r) for r in rows);predictions.extend(dict(**tags,**r) for r in raw)
    groups,screen=aggregate(metrics,cfg['protocol']['bootstrap_samples'])
    write_json(root/'fit_summary.json',dict(details,model_sha256=sha(root/'forecast_model.npz'),formal_fits=1,validation_used_for_fit=False))
    write_csv(root/'metrics.csv',metrics);write_csv(root/'predictions.csv',predictions);write_csv(root/'forecast_groups.csv',groups)
    write_json(root/'screen.json',screen)
    write_json(root/'forecast_lock.json',{name:sha(root/name) for name in ('forecast_model.npz','fit_summary.json','metrics.csv','predictions.csv','forecast_groups.csv','screen.json','bank_manifest.json')})
    write_json(root/'summary.txt',dict(status='forecast_scored',formal_RL_steps=0,PINN_mock_rows=0,screen=screen,
        unique_scoring_trajectories=len(manifest['score']),fit_trajectories=len(manifest['fit'])))
    print(screen,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('prepare','evaluate'));parser.add_argument('--output',required=True)
    args=parser.parse_args()
    import os
    os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    globals()[args.command](Path(args.output).resolve())


if __name__=='__main__':main()
