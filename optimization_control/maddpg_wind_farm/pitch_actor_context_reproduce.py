"""Prepare a separate same-data reproduction without copying policies or replay folders."""
from __future__ import annotations
import argparse
from copy import deepcopy
from pathlib import Path
import yaml
from .pitch_actor_context_trial import context,put,js,digest,read_json


def reproduce(source,output,check_only=False):
    source,s=context(source);output=Path(output).resolve()
    if output.exists():raise FileExistsError('reproduction output must be new')
    data=read_json(source/'data_lock.json')
    from .pitch_nstep_trial import verify
    verify(data['hashes']);verify(read_json(source/'validation_bank/manifest.json')['hashes'])
    if check_only:return dict(status='passed',prepared=False,plant_rows=0,optimizer_updates=0,source_config_sha256=digest(source/'config.yaml'),protected_inputs=len(s['protected_hashes']))
    output.mkdir(parents=True,exist_ok=False)
    new=deepcopy(s);new['same_data_reproduction_of']=str(source);new['same_data_is_not_new_independent_test']=True
    put(output,output/'config.yaml',yaml.safe_dump(new,allow_unicode=True,sort_keys=False).encode('utf-8'))
    names=['training_manifest.csv','random_states.json','noise_run0.npz','noise_run1.npz','noise_run2.npz','validation_bank/manifest.json']
    for name in names:put(output,output/name,(source/name).read_bytes())
    hashes=dict(data['hashes'])
    hashes.update({str(output/name):digest(output/name) for name in names if name!='validation_bank/manifest.json'})
    js(output,output/'data_lock.json',dict(hashes=hashes))
    js(output,output/'reproduction_inputs.json',dict(source=str(source),source_config_sha256=digest(source/'config.yaml'),
        no_weights_or_replay_copied=True,no_selection_or_test_results_copied=True,read_only_training_validation_wind_paths=True,
        plant_rows=0,optimizer_updates=0))
    return dict(status='passed',prepared=True,output=str(output),plant_rows=0,optimizer_updates=0)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--check-only',action='store_true')
    a=p.parse_args();print(reproduce(a.source,a.output,a.check_only))
