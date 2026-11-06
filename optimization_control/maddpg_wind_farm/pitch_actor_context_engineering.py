"""Eight discarded engineering updates, one stored restore input, zero plant rows."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import unittest

from .pitch_actor_context_trial import context,HERE,js,save_agent,read_json,digest,verify,fingerprint
from .pitch_gamma_trial import state
from .pitch_gamma_engineering import one_update


def child(root):
    from .pitch_actor_context_algorithm import PitchActorContextMADDPG
    root,s=context(root);a,m=PitchActorContextMADDPG.load(root/'engineering/restore_input.pth','current_pitch')
    before=fingerprint(state(a));result=one_update(a)
    js(root,root/'engineering/child.json',dict(pid=os.getpid(),before=before,after=result,metadata=m))


def engineering(root):
    import numpy as np
    import torch
    from .nstep_algorithm import NStepMADDPG
    from .pitch_actor_context_algorithm import PitchActorContextMADDPG
    root,s=context(root);folder=root/'engineering';folder.mkdir(exist_ok=False);pairs=[];initial=[]
    for run in range(3):
        path=s['parents'][str(run)]['checkpoint'];old,_=NStepMADDPG.load(path,expected_n=8)
        a,_=PitchActorContextMADDPG.inherit(path,'replay');b,_=PitchActorContextMADDPG.inherit(path,'current_pitch')
        assert fingerprint(state(old))==fingerprint(state(a))==fingerprint(state(b))
        obs=old.replay.data['obs'][:64]
        delta=max(float(np.max(np.abs(old.act(x)-b.act(x)))) for x in obs)
        assert delta==0;initial.append(dict(run=run,max_action_difference=delta))
        left,right=one_update(old),one_update(a);assert left==right
        pairs.append(dict(run=run,exact=True,**left))
    a,_=PitchActorContextMADDPG.inherit(s['parents']['0']['checkpoint'],'current_pitch')
    metadata=dict(experiment='pitch_actor_context_v1',arm='current_pitch',engineering_only=True,checkpoint_interval=1024,
                  step=0,external_noise={'kind':'frozen_white','rng_state':read_json(root/'random_states.json')[0]['initial']})
    before=fingerprint(state(a));save_agent(root,folder/'restore_input.pth',a,metadata)
    records=[];entry_identity=None
    def hook(agent,i,obs,actions,entry,peers,joint,loss):
        nonlocal entry_identity
        identity=fingerprint(entry)
        if entry_identity is None:entry_identity=identity
        assert identity==entry_identity and not entry.requires_grad and not peers.requires_grad
        assert torch.equal(peers[:,:,[0,2]],actions[:,:,[0,2]]) and torch.equal(peers[:,:,1],entry[:,:,1])
        others=[p for j,m in enumerate(agent.actors) if j!=i for p in m.parameters()]
        assert all(g is None for g in torch.autograd.grad(loss,others,allow_unused=True,retain_graph=True))
        own=torch.autograd.grad(loss,agent.actors[i].parameters(),retain_graph=True)
        assert all(torch.isfinite(x).all() for x in own) and sum(float(x.abs().sum()) for x in own)>0
        stale_difference=0.
        for j in range(i):
            now=agent.policy(agent.actors[j],obs[:,j]).detach()
            stale_difference=max(stale_difference,float((now[:,1]-entry[:,j,1]).abs().max()))
            assert torch.equal(joint[:,j,1].detach(),entry[:,j,1])
        records.append(dict(actor=i,entry_fingerprint=identity,peer_parameter_gradients='all_none',own_gradient_nonzero=True,
                            updated_peer_vs_cached_difference=stale_difference))
    a.engineering_hook=hook;expected=one_update(a);del a.engineering_hook
    assert len(records)==3 and max(r['updated_peer_vs_cached_difference'] for r in records)>0
    command=[sys.executable,'-B','-X','utf8','-m',__package__+'.pitch_actor_context_trial','engineering-child','--output',str(root)]
    with (folder/'child.log').open('xb') as log:
        p=subprocess.run(command,cwd=HERE.parents[1],stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000 if os.name=='nt' else 0)
    assert p.returncode==0
    result=read_json(folder/'child.json');assert result['pid']!=os.getpid() and result['before']==before and result['after']==expected and result['metadata']==metadata
    try:PitchActorContextMADDPG.load(folder/'restore_input.pth','replay')
    except ValueError:pass
    else:raise AssertionError('wrong arm accepted')
    suite=unittest.defaultTestLoader.loadTestsFromName('optimization_control.tests.test_pitch_actor_context')
    with (folder/'tests.txt').open('x',encoding='utf-8') as log:test=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    assert test.wasSuccessful() and test.testsRun==2
    verify(s['protected_hashes'])
    js(root,root/'engineering.json',dict(status='passed',old_n8_pairs=pairs,initial_action_equivalence=initial,
        candidate_gradient_and_snapshot=records,new_process_exact=result,tests=2,discarded_optimizer_updates=8,
        formal_learning_steps=0,plant_input_rows=0,stored_restore_states=1,
        hashes={str(p):digest(p) for p in folder.iterdir() if p.is_file()}))
    print(json.dumps(dict(engineering='passed',discarded_updates=8,plant_rows=0,stored_restore_states=1)),flush=True)
