"""Eight discarded in-memory updates, no environment steps or new policy selection."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

from .pitch_gamma_trial import (HERE,NETS,OPTIMIZERS,context,inherit,load_agent,state,fingerprint,arm_config,
                                read_json,write_json,digest,verify)


def one_update(agent):
    targets=[];original=agent.td_target
    def tapped(*args,**kwargs):
        result=original(*args,**kwargs);targets.append(result.detach().cpu().clone());return result
    agent.td_target=tapped
    try:loss=agent.update()
    finally:agent.td_target=original
    return dict(loss=loss,targets_sha256=fingerprint(targets),sample_indices_sha256=fingerprint(agent.replay.last_indices),
                lengths_sha256=fingerprint(agent.replay.last_lengths),state_sha256=fingerprint(state(agent)))


def child(root):
    root,s=context(root);folder=root/'engineering';a,m=load_agent(folder/'restore_input.pth',1.)
    before=fingerprint(state(a));result=one_update(a);a.save(folder/'child_after.pth',m)
    write_json(folder/'child.json',dict(pid=os.getpid(),before=before,after=result))


def engineering(root):
    from .nstep_algorithm import NStepMADDPG
    import torch
    root,s=context(root)
    if (root/'engineering.json').exists():raise FileExistsError('engineering evidence frozen')
    folder=root/'engineering';folder.mkdir(exist_ok=False);pairs=[]
    for run in range(3):
        path=s['parents'][str(run)]['checkpoint']
        old,_=NStepMADDPG.inherit(path,8);a,_=inherit(path,'g099')
        assert fingerprint(state(old))==fingerprint(state(a))
        r0=one_update(old);r1=one_update(a)
        assert r0==r1,(run,r0,r1)
        pairs.append(dict(run=run,exact=True,**r0))
    a,_=inherit(s['parents']['0']['checkpoint'],'g100')
    assert all(len(getattr(a,k))==3 for k in OPTIMIZERS)
    m=dict(experiment='pitch_gamma_v1',gamma=1.,config=arm_config(s,'g100'),engineering_only=True)
    before=fingerprint(state(a));a.save(folder/'restore_input.pth',m)
    expected=one_update(a)
    cmd=[sys.executable,'-B','-X','utf8','-m',__package__+'.pitch_gamma_trial','engineering-child','--output',str(root)]
    with (folder/'child.log').open('wb') as log:
        process=subprocess.run(cmd,cwd=HERE.parents[1],stdout=log,stderr=subprocess.STDOUT,
                               creationflags=0x08000000 if os.name=='nt' else 0)
    assert process.returncode==0
    result=read_json(folder/'child.json');assert result['pid']!=os.getpid() and result['before']==before and result['after']==expected
    b,_=load_agent(folder/'child_after.pth',1.);assert fingerprint(state(b))==expected['state_sha256']
    try:load_agent(folder/'child_after.pth',.99)
    except ValueError:pass
    else:raise AssertionError('incorrect gamma accepted')
    # Tests use only small synthetic arrays; no optimizer call or temporary files.
    import unittest
    suite=unittest.defaultTestLoader.loadTestsFromName('optimization_control.tests.test_pitch_gamma')
    with (folder/'unittest.txt').open('w',encoding='utf-8',newline='\n') as log:
        test=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    assert test.wasSuccessful() and test.testsRun==2
    verify(s['protected_hashes'])
    write_json(root/'engineering.json',dict(status='passed',gamma099_real_parent_pairs=pairs,
               gamma1_new_process_exact=result,tests=2,discarded_optimizer_updates=8,environment_steps=0,
               no_policy_output=True,hashes={str(p.resolve()):digest(p) for p in folder.iterdir() if p.is_file()}))
    print(json.dumps(dict(engineering='passed',tests=2,discarded_updates=8,environment_steps=0)),flush=True)
