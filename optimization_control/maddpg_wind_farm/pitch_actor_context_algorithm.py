"""One approved variant: current detached teammate pitch in the actor loss only."""
from __future__ import annotations

from dataclasses import asdict
from copy import deepcopy
import numpy as np
import torch
from torch import nn

from .algorithm import AlgorithmConfig
from .nstep_algorithm import NStepMADDPG, SequenceReplay, TAIL_RULE

ARMS=('replay','current_pitch')
NETS=('actors','critics','target_actors','target_critics')
OPTIMIZERS=('actor_optimizers','critic_optimizers')


def full_checkpoint(step,run):
    return step%1024==0 or (run==0 and step==128)


def recovery_plan(commits):
    complete=[c for c in commits if c.get('checkpoint')]
    if not complete:return None,[]
    newest=max(complete,key=lambda c:(c['step'],c.get('attempt',0)))
    repeats=[c for c in commits if c['step']>newest['step']]
    return newest,repeats


class PitchActorContextMADDPG(NStepMADDPG):
    @classmethod
    def inherit(cls,path,arm):
        if arm not in ARMS:raise ValueError('unknown actor context')
        agent,meta=NStepMADDPG.load(path,expected_n=8)
        if agent.config.gamma!=.99 or tuple(agent.config.action_mask)!=(0,1,0):raise ValueError('fixed n8 pitch source required')
        agent.__class__=cls;agent.actor_teammates=arm
        return agent,meta

    def update(self):
        if self.actor_teammates=='replay':return super().update()
        c=self.config
        b=self.replay.sample(c.batch_size,self.device)
        obs,actions=b['obs'],b['actions'];flat_obs=obs.flatten(1)
        with torch.no_grad():
            # Cache before any actor step. Background channels stay bitwise replay values.
            entry=torch.stack([self.policy(m,obs[:,j]) for j,m in enumerate(self.actors)],dim=1)
            peers=actions.detach().clone();peers[:,:,1]=entry[:,:,1]
            next_actions=torch.stack([self.policy(m,b['next_obs'][:,i]) for i,m in enumerate(self.target_actors)],dim=1)
            target_input=torch.cat((b['next_obs'].flatten(1),next_actions.flatten(1)),dim=1)
            targets=[self.td_target(b['rewards'][:,i:i+1],b['terminated'],critic(target_input),c.gamma) for i,critic in enumerate(self.target_critics)]
        actor_losses,critic_losses,actor_norms,critic_norms,q_values,td_errors=[],[],[],[],[],[]
        for i in range(c.agents):
            critic=self.critics[i]
            q=critic(torch.cat((flat_obs,actions.flatten(1)),dim=1))
            loss=nn.functional.mse_loss(q,targets[i])
            if not torch.isfinite(loss):raise FloatingPointError('non-finite critic loss')
            self.critic_optimizers[i].zero_grad(set_to_none=True);loss.backward()
            critic_norms.append(float(nn.utils.clip_grad_norm_(critic.parameters(),c.grad_clip,error_if_nonfinite=True)))
            q_values.append(float(q.detach().mean()));td_errors.append(float((q.detach()-targets[i]).abs().mean()))
            self.critic_optimizers[i].step();critic_losses.append(loss.item())
            critic.requires_grad_(False)
            joint=torch.stack([self.policy(self.actors[i],obs[:,i]) if j==i else peers[:,j].detach() for j in range(c.agents)],dim=1)
            actor_loss=-critic(torch.cat((flat_obs,joint.flatten(1)),dim=1)).mean()
            if not torch.isfinite(actor_loss):raise FloatingPointError('non-finite actor loss')
            hook=getattr(self,'engineering_hook',None)
            if hook:hook(self,i,obs,actions,entry,peers,joint,actor_loss)
            self.actor_optimizers[i].zero_grad(set_to_none=True);actor_loss.backward()
            actor_norms.append(float(nn.utils.clip_grad_norm_(self.actors[i].parameters(),c.grad_clip,error_if_nonfinite=True)))
            self.actor_optimizers[i].step();critic.requires_grad_(True);actor_losses.append(actor_loss.item())
        with torch.no_grad():
            for source,target in ((self.actors,self.target_actors),(self.critics,self.target_critics)):
                for p,tp in zip(source.parameters(),target.parameters()):tp.lerp_(p,c.tau)
        self.updates+=1
        return dict(actor_loss=float(np.mean(actor_losses)),critic_loss=float(np.mean(critic_losses)),
                    actor_grad_norm=float(np.mean(actor_norms)),critic_grad_norm=float(np.mean(critic_norms)),
                    q_mean=float(np.mean(q_values)),td_abs_mean=float(np.mean(td_errors)))

    def payload(self,metadata):
        result=dict(version='pitch_actor_context_v1',actor_teammates=self.actor_teammates,config=asdict(self.config),
                    n=8,tail_rule=TAIL_RULE,replay=self.replay.state_dict(),rng=self.rng.bit_generator.state,
                    torch_rng=torch.get_rng_state(),updates=self.updates,metadata=metadata)
        result.update({k:getattr(self,k).state_dict() for k in NETS})
        result.update({k:[o.state_dict() for o in getattr(self,k)] for k in OPTIMIZERS})
        return result

    def save(self,path,metadata):
        torch.save(self.payload(metadata),path)

    @classmethod
    def load(cls,path,expected_arm):
        s=torch.load(path,map_location='cpu',weights_only=False)
        if (s['version']!='pitch_actor_context_v1' or s['actor_teammates']!=expected_arm or expected_arm not in ARMS
            or s['n']!=8 or s['tail_rule']!=TAIL_RULE or s['config']['gamma']!=.99):
            raise ValueError('private actor context restoration contract mismatch')
        agent=cls(AlgorithmConfig(**s['config']));agent.n=8;agent.actor_teammates=expected_arm
        agent.replay=SequenceReplay(agent.config,8)
        for k in NETS:getattr(agent,k).load_state_dict(s[k])
        for k in OPTIMIZERS:
            for o,v in zip(getattr(agent,k),s[k]):o.load_state_dict(v)
        agent.replay.load_state_dict(s['replay']);agent.rng.bit_generator.state=deepcopy(s['rng'])
        torch.set_rng_state(s['torch_rng'].cpu());agent.updates=s['updates']
        return agent,s['metadata']
