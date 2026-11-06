"""Parameter-gradient companion to the frozen offline replay audit; no learning."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pitch_remaining_failure_audit import ORIGINAL, SOURCE, check_sources, read_json, sha, write_csv, write_json


def run(root):
    config=check_sources(root)
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(ORIGINAL/'.venv/pinn_tf216')
    import numpy as np
    import torch
    from .algorithm import MADDPG
    from .nstep_algorithm import NStepMADDPG
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    def forbidden(*args,**kwargs):
        raise AssertionError('no optimization or replay sampling in diagnostic')
    MADDPG.update=forbidden
    rows=[]
    background_rows=[]
    cache={}
    saved_rng=torch.get_rng_state().clone()
    for r in [r for r in read_json(SOURCE/'selection.json')['results'] if r['n']==8]:
        for role in ('selected','final'):
            identity=sha(r[role])
            if identity in cache:
                rows.extend(dict(run=r['run'],role=role,checkpoint_sha256=identity,**v) for v in cache[identity])
                continue
            agent,_=NStepMADDPG.load(r[role],expected_n=8)
            agent.replay.sample=forbidden
            before={k:v.detach().clone() for k,v in agent.actors.state_dict().items()}
            rng=json.dumps(agent.replay.rng.bit_generator.state,sort_keys=True)
            order=np.argsort(agent.replay.sequence[:agent.replay.size],kind='stable')
            idx=order[np.linspace(0,len(order)-1,1024,dtype=int)]
            obs=torch.as_tensor(agent.replay.data['obs'][idx])
            behavior=torch.as_tensor(agent.replay.data['actions'][idx])
            with torch.no_grad():
                current=torch.stack([agent.policy(m,obs[:,i]) for i,m in enumerate(agent.actors)],dim=1)
            pitch_current=behavior.clone()
            pitch_current[:,:,1]=current[:,:,1]
            values=[]
            for i in range(3):
                action_grad=[]
                for other_actions in (current,pitch_current):
                    own=current[:,i].detach().clone().requires_grad_(True)
                    joint=torch.stack([own if j==i else other_actions[:,j].detach() for j in range(3)],dim=1)
                    q=agent.critics[i](torch.cat((obs.flatten(1),joint.flatten(1)),dim=1))
                    action_grad.append(torch.autograd.grad(q.sum(),own)[0][:,1].detach())
                background_rows.append(dict(run=r['run'],role=role,agent=i,
                    max_background_action_difference=float((current[:,:,[0,2]]-behavior[:,:,[0,2]]).abs().max()),
                    max_pitch_action_gradient_difference=float((action_grad[0]-action_grad[1]).abs().max()),
                    changed_gradient_signs=int(((action_grad[0]*action_grad[1])<0).sum())))
                gradients=[[],[]]
                for start in range(0,1024,64):
                    for mode in range(2):
                        own=agent.policy(agent.actors[i],obs[start:start+64,i])
                        other=(behavior if mode==0 else pitch_current)[start:start+64].detach()
                        joint=torch.stack([own if j==i else other[:,j] for j in range(3)],dim=1)
                        loss=-agent.critics[i](torch.cat((obs[start:start+64].flatten(1),joint.flatten(1)),dim=1)).mean()
                        g=torch.cat([x.flatten() for x in torch.autograd.grad(loss,agent.actors[i].parameters())])
                        gradients[mode].append(g.detach())
                a,b=[torch.stack(g) for g in gradients]
                cosine=(a*b).sum(dim=1)/(a.norm(dim=1)*b.norm(dim=1)).clamp(min=1e-20)
                aa,bb=a.mean(dim=0),b.mean(dim=0)
                value=dict(agent=i,batches=16,batch_size=64,
                           aggregate_parameter_cosine=float(torch.dot(aa,bb)/(aa.norm()*bb.norm()).clamp(min=1e-20)),
                           mean_batch_parameter_cosine=float(cosine.mean()),min_batch_parameter_cosine=float(cosine.min()),
                           negative_cosine_batches=int((cosine<0).sum()),
                           mean_parameter_relative_difference=float(((b-a).norm(dim=1)/a.norm(dim=1).clamp(min=1e-20)).mean()),
                           aggregate_gradient_norm_replay=float(aa.norm()),aggregate_gradient_norm_current=float(bb.norm()))
                values.append(value)
                rows.append(dict(run=r['run'],role=role,checkpoint_sha256=identity,**value))
            cache[identity]=values
            assert all(torch.equal(v,before[k]) for k,v in agent.actors.state_dict().items())
            assert all(p.grad is None for p in agent.actors.parameters())
            assert json.dumps(agent.replay.rng.bit_generator.state,sort_keys=True)==rng
    torch.set_rng_state(saved_rng)
    write_csv(root/'parameter_gradient.csv',rows)
    write_csv(root/'background_projection_check.csv',background_rows)
    check_sources(root)
    write_json(root/'parameter_gradient_verification.json',dict(status='passed',source_sha256=sha(__file__),
                frozen_replay_selection=config['replay_probe'],unique_states=len(cache),logical_role_rows=len(rows),
                backward_parameter_gradients_only=True,optimizer_updates=0,model_forward_rows=0,environment_steps=0,
                no_rng_consumed=True,no_parameter_or_optimizer_change=True,
                changed_context='teammate_pitch_only_background_replay_preserved',
                cosine_is_context_sensitivity_not_correctness=True))
    print(json.dumps(dict(status='passed',unique_states=len(cache),parameter_gradient_rows=len(rows))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    run(parser.parse_args().output.resolve())
