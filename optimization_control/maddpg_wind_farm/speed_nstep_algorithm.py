"""Optional n1/n8 speed adapter; legacy v4 remains owned by its original loader."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json

import numpy as np
import torch

from .algorithm import MADDPG
from .frozen_speed_algorithm import FrozenSpeedMADDPG, FrozenSpeedConfig, SEMANTICS
from .nstep_replay_core import SequenceReplay, TAIL_RULE

VERSION = 'frozen_speed_nstep_v1'
REPLAY_SCHEMA = 'verified_joint_sequence_v1'


def ring_order(size, position, capacity):
    if not 0 <= size <= capacity or not 0 <= position < capacity or (size < capacity and position != size):
        raise ValueError('invalid replay size/next-write position')
    return (position + np.arange(size)) % capacity if size == capacity else np.arange(size)


def validate_ring(state, config, horizon, insertion_count):
    if type(insertion_count) is not int or insertion_count < 0 or type(horizon) is not int or horizon < 2:
        raise ValueError('explicit insertion count and episode horizon required')
    size, pos = state['size'], state['position']
    order = ring_order(size, pos, config.capacity)
    if size != min(config.capacity, insertion_count) or pos != insertion_count % config.capacity:
        raise ValueError('insertion metadata does not match retained ring')
    d = state['data']
    shapes = dict(obs=(size,3,15),next_obs=(size,3,15),actions=(size,3,3),rewards=(size,3),terminated=(size,1))
    for name, shape in shapes.items():
        if d[name].shape != shape or d[name].dtype != np.float32 or not np.isfinite(d[name]).all():
            raise ValueError('invalid joint replay field: ' + name)
    if not np.isin(d['terminated'],(0,1)).all() or np.any(np.abs(d['actions'])>1):
        raise ValueError('invalid termination or total command')
    if not np.array_equal(d['rewards'][:,0],d['rewards'][:,1]) or not np.array_equal(d['rewards'][:,0],d['rewards'][:,2]):
        raise ValueError('one cooperative reward per environment transition required')
    if not np.array_equal(d['actions'],d['next_obs'][:,:,5:8]):
        raise ValueError('replay must store executed total commands')
    current, following = d['obs'][:,:,14], d['next_obs'][:,:,14]
    if (np.any(current<=0) or np.any(current>1) or np.any(following<0) or
        not np.array_equal(current,current[:,0,None].repeat(3,axis=1)) or
        not np.array_equal(following,following[:,0,None].repeat(3,axis=1)) or
        not np.allclose(current-following,1/horizon,atol=1e-7,rtol=0) or
        not np.array_equal(d['terminated'][:,0].astype(bool),following[:,0]==0)):
        raise ValueError('episode clock/done metadata inconsistent')
    prev, nxt = order[:-1], order[1:]
    active = d['terminated'][prev,0] == 0
    if not np.array_equal(d['next_obs'][prev[active]],d['obs'][nxt[active]]):
        raise ValueError('retained nonterminal continuity broken')
    if np.any(current[nxt[~active]] != 1):
        raise ValueError('episode reset clock missing')
    h=hashlib.sha256()
    for name in sorted(d):h.update(name.encode());h.update(d[name].tobytes())
    h.update(json.dumps(dict(size=size,position=pos,count=insertion_count,horizon=horizon),sort_keys=True).encode())
    return dict(retained=size,position=pos,insertion_count=insertion_count,horizon=horizon,
        nonterminal_edges=int(active.sum()),terminal_edges=int((~active).sum()),digest=h.hexdigest(),
        full_retained_ring_checked=True)


class VerifiedSequenceReplay(SequenceReplay):
    def __init__(self, config, n, *, horizon, epoch):
        super().__init__(config,n)
        if not epoch or type(horizon) is not int or horizon<2:
            raise ValueError('explicit sequence epoch/horizon required')
        self.horizon,self.epoch=horizon,epoch
        self.proof=dict(validate_ring(super().state_dict(),config,horizon,0),epoch=epoch,
            evidence=dict(expected_insertions=0,source_id='new_empty_sequence_buffer'))

    def import_legacy(self,state,*,insertion_count, evidence):
        if ('sequence' in state or not isinstance(evidence,dict) or
            evidence.get('expected_insertions')!=insertion_count or
            not (evidence.get('source_sha256') or evidence.get('source_id'))):
            raise ValueError('explicit legacy state and count evidence required')
        proof=validate_ring(state,self_config(self),self.horizon,insertion_count)
        order=ring_order(state['size'],state['position'],self.capacity)
        sequence=np.full(self.capacity,-1,np.int64)
        sequence[order]=np.arange(insertion_count-state['size'],insertion_count)
        encoded=dict(state,sequence=sequence,insertions=insertion_count,n=self.n,tail_rule=TAIL_RULE,
            m_histogram=np.zeros(self.n+1,np.int64),replay_schema=REPLAY_SCHEMA,horizon=self.horizon,
            epoch=self.epoch,return_gamma=self.gamma,migration_proof=dict(proof,evidence=evidence,epoch=self.epoch))
        self.load_state_dict(encoded)
        return deepcopy(self.proof)

    def add(self,obs,actions,rewards,next_obs,terminated):
        done=self.shared_done(terminated)
        one=dict(data={k:np.asarray(v,np.float32)[None] for k,v in
            dict(obs=obs,actions=actions,rewards=rewards,next_obs=next_obs,terminated=[done]).items()},size=1,position=1)
        # Validate one transition using a one-slot-equivalent partial ring.
        validate_ring(one,type('ClockConfig',(),{'capacity':max(2,self.capacity)})(),self.horizon,1)
        if self.size:
            last=(self.position-1)%self.capacity
            if not self.data['terminated'][last,0] and not np.array_equal(self.data['next_obs'][last],obs):
                raise ValueError('new nonterminal transition is not the next state')
            if self.data['terminated'][last,0] and not np.all(np.asarray(obs)[:,14]==1):
                raise ValueError('new episode must reset its observed clock')
        super().add(obs,actions,rewards,next_obs,done)

    def state_dict(self):
        return dict(super().state_dict(),replay_schema=REPLAY_SCHEMA,horizon=self.horizon,epoch=self.epoch,
                    return_gamma=self.gamma,migration_proof=deepcopy(self.proof))

    def load_state_dict(self,state):
        required=('replay_schema','horizon','epoch','return_gamma','migration_proof','sequence','insertions','m_histogram','n','tail_rule')
        if any(k not in state for k in required):raise ValueError('missing explicit sequence restoration metadata')
        if (state['replay_schema'],state['horizon'],state['epoch'],state['return_gamma']) != (REPLAY_SCHEMA,self.horizon,self.epoch,self.gamma):
            raise ValueError('sequence schema/horizon/epoch/discount mismatch')
        proof=state['migration_proof']
        if (not proof or proof.get('epoch')!=self.epoch or not proof.get('full_retained_ring_checked') or
            not isinstance(proof.get('evidence'),dict) or
            proof['evidence'].get('expected_insertions')!=proof.get('insertion_count') or
            not (proof['evidence'].get('source_sha256') or proof['evidence'].get('source_id')) or
            proof['insertion_count']>state['insertions']):
            raise ValueError('missing verified migration origin')
        validate_ring(state,self_config(self),self.horizon,state['insertions'])
        order=ring_order(state['size'],state['position'],self.capacity)
        seq=np.asarray(state['sequence'])
        hist=np.asarray(state['m_histogram'])
        if (seq.shape!=(self.capacity,) or seq.dtype!=np.int64 or
            not np.array_equal(seq[order],np.arange(state['insertions']-state['size'],state['insertions'])) or
            (state['size']<self.capacity and np.any(seq[state['size']:]!=-1)) or
            hist.shape!=(self.n+1,) or hist.dtype!=np.int64 or np.any(hist<0)):
            raise ValueError('invalid slot sequence or length accounting')
        super().load_state_dict(state)
        self.proof=deepcopy(proof)


def self_config(replay):
    # Validation only needs capacity; explicit shapes and clock semantics above are fixed.
    return type('RingConfig',(),{'capacity':replay.capacity})()


class FrozenSpeedNStepMADDPG(FrozenSpeedMADDPG):
    def __init__(self,config,device='cpu'):
        super().__init__(config,device)
        self.configure(1,insertion_count=0,horizon=128,epoch='new_empty',
            evidence=dict(expected_insertions=0,source_id='new_empty_replay'))

    def configure(self,n=1,*,insertion_count,horizon,epoch,evidence):
        state=self.replay.state_dict()
        if 'sequence' in state:raise ValueError('horizon cannot be silently changed on a sequence replay')
        replay=VerifiedSequenceReplay(self.config,n,horizon=horizon,epoch=epoch)
        replay.import_legacy(state,insertion_count=insertion_count,evidence=evidence)
        self.replay,self.n=replay,n
        return self

    @classmethod
    def adapt(cls,agent,n=1,*,insertion_count,horizon,epoch,evidence):
        if type(agent) is not FrozenSpeedMADDPG:raise ValueError('unmodified FrozenSpeedMADDPG required')
        replay=VerifiedSequenceReplay(agent.config,n,horizon=horizon,epoch=epoch)
        replay.import_legacy(agent.replay.state_dict(),insertion_count=insertion_count,evidence=evidence)
        agent.__class__=cls
        agent.replay,agent.n=replay,n
        return agent

    @classmethod
    def from_parent(cls,parent,head_seed,*,n=1,insertion_count,horizon,epoch,evidence):
        base=FrozenSpeedMADDPG.from_parent(parent,head_seed)
        return cls.adapt(base,n,insertion_count=insertion_count,horizon=horizon,epoch=epoch,evidence=evidence)

    @classmethod
    def from_v4(cls,path,n=1):
        from .anchor_closeout import sha
        agent,meta=FrozenSpeedMADDPG.load(path)
        try:
            count=meta['parent']['cumulative_parent_steps']+meta['step']
            horizon=meta['config']['environment']['horizon']
        except KeyError as exc:raise ValueError('v4 lacks accountable insertion/horizon metadata') from exc
        agent=cls.adapt(agent,n,insertion_count=count,horizon=horizon,epoch=sha(path),
            evidence=dict(expected_insertions=count,source_sha256=sha(path),
                derivation='v4 metadata.parent.cumulative_parent_steps + metadata.step'))
        return agent,meta

    def td_target(self,rewards,terminated,next_q,gamma):
        if self.n==1:return MADDPG.td_target(rewards,terminated,next_q,gamma)
        if gamma!=self.replay.gamma or self.replay.discounts is None:raise ValueError('sampled actual-m discounts required')
        return rewards+self.replay.discounts*(1-terminated)*next_q

    def save(self,path,metadata):
        torch.save(dict(version=VERSION,action_semantics=SEMANTICS,config=asdict(self.config),n=self.n,tail_rule=TAIL_RULE,
            **{k:getattr(self,k).state_dict() for k in ('actors','target_actors','critics','target_critics','speed_heads','target_speed_heads')},
            head_optimizers=[o.state_dict() for o in self.head_optimizers],critic_optimizers=[o.state_dict() for o in self.critic_optimizers],
            replay=self.replay.state_dict(),rng=self.rng.bit_generator.state,torch_rng=torch.get_rng_state(),updates=self.updates,metadata=metadata),path)

    @classmethod
    def load(cls,path,device='cpu',expected_n=None):
        s=torch.load(path,map_location=device,weights_only=False)
        required=('version','action_semantics','config','n','tail_rule','replay','rng','torch_rng','updates','metadata',
                  'actors','target_actors','critics','target_critics','speed_heads','target_speed_heads','head_optimizers','critic_optimizers')
        if any(k not in s for k in required):raise ValueError('incomplete speed n-step checkpoint metadata')
        if s.get('version')!=VERSION or s.get('action_semantics')!=SEMANTICS or s.get('tail_rule')!=TAIL_RULE or (expected_n is not None and s['n']!=expected_n):
            raise ValueError('explicit speed n-step format/horizon required')
        if any(k not in s.get('replay',{}) for k in ('horizon','epoch','migration_proof','sequence','insertions','n','tail_rule','m_histogram','replay_schema','return_gamma')):
            raise ValueError('missing explicit sequence restoration metadata')
        a=cls(FrozenSpeedConfig(**s['config']),device)
        a.n=s['n'];rs=s['replay']
        a.replay=VerifiedSequenceReplay(a.config,a.n,horizon=rs['horizon'],epoch=rs['epoch'])
        a.replay.load_state_dict(rs)
        for k in ('actors','target_actors','critics','target_critics','speed_heads','target_speed_heads'):getattr(a,k).load_state_dict(s[k])
        for k in ('head_optimizers','critic_optimizers'):
            for dst,src in zip(getattr(a,k),s[k]):dst.load_state_dict(src)
        a.rng.bit_generator.state=deepcopy(s['rng']);torch.set_rng_state(s['torch_rng'].cpu());a.updates=s['updates']
        return a,s['metadata']
