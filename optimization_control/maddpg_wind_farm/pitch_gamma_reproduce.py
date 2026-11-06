"""Prepare an explicit same-data reproduction, never a new independent experiment.

Reuses only frozen training/validation inputs; no saved policy, selection or test
outcome is copied. This helper performs zero learning and zero environment steps.
"""
import argparse
from pathlib import Path
from .pitch_gamma_trial import ORIGINAL,read_json,write_csv,write_json,digest,verify


def prepare(source,output,check_only=False):
    import yaml
    source=Path(source).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError('fresh output required; no overwriting any experiment')
    cfg=yaml.safe_load((source/'config.yaml').read_text(encoding='utf-8'))
    assert cfg['experiment']=='pitch_gamma_v1'
    # Coordination documents are provenance, not numerical inputs. Relocate only
    # these two to byte-identical immutable snapshots; all scientific input checks stay strict.
    documents={str(ORIGINAL/'PROJECT_STATUS.md'):'PROJECT_STATUS.md',str(ORIGINAL/'optimization_control/TASKFLOW.md'):'TASKFLOW.md'}
    scientific={p:h for p,h in cfg['protected_hashes'].items() if p not in documents}
    contract=read_json(source/'model_contract_verification.json')
    assert digest(contract['prior_lock'])==contract['prior_lock_sha256']
    previous=yaml.safe_load(Path(contract['prior_lock']).read_text(encoding='utf-8'))
    for path,h in contract['files'].items():
        assert previous['protected_hashes'][path]==h
        scientific[path]=h
    verify(scientific);verify(read_json(source/'data_lock.json')['hashes'])
    verify(read_json(source/'validation_bank/manifest.json')['hashes'])
    relocations={}
    for original,name in documents.items():
        old=source/'source_coordination'/name;expected=cfg['protected_hashes'][original]
        assert digest(old)==expected
        scientific[str(output/'source_coordination'/name)]=expected
        relocations[original]=str(output/'source_coordination'/name)
    cfg['protected_hashes']=scientific
    names=['training_manifest.csv','random_states.json','data_lock.json','validation_bank/manifest.json']
    names += [f'noise_run{r}.npz' for r in range(3)]
    names += [f'source_coordination/{name}' for name in documents.values()]
    proof=dict(kind='same_input_reproduction_not_independent',source=str(source),output=str(output),
               environment_steps=0,optimizer_updates=0,trained_candidate_selection_test_not_read=True,
               shared_readonly_wind_paths=True,source_config_sha256=digest(source/'config.yaml'),
               coordination_only_relocations=relocations,files={name:digest(source/name) for name in names})
    if check_only:print(__import__('json').dumps(proof));return
    output.mkdir(parents=True,exist_ok=False)
    (output/'config.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    for name in names:
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((source/name).read_bytes())
        assert digest(target)==proof['files'][name]
    write_json(output/'reproduction.json',proof)
    write_csv(output/'metrics.csv',[dict(status='prepared_same_data_reproduction',formal_learning_steps=0,environment_steps=0)])
    write_json(output/'summary.txt',dict(status='prepared_same_data_reproduction',formal_learning_steps=0,test_locked=True))
    print(__import__('json').dumps(proof))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args();prepare(args.source,args.output,args.check_only)
