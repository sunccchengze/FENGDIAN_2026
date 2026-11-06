"""Version 4: frozen parent Actor mapping plus independent bounded speed heads."""
from copy import deepcopy
from dataclasses import asdict, dataclass

import numpy as np
import torch
from torch import nn

from .algorithm import MADDPG, AlgorithmConfig
from ..utils.reference_schedule import speed_torch

SEMANTICS = "frozen_parent_pitch_plus_observation_speed_residual_v1"


@dataclass
class FrozenSpeedConfig(AlgorithmConfig):
    speed_schedule: tuple = (25., 1.267 / 11.4, .6, 1.267)
    speed_scale: float = 2 * .1 / .667
    head_seed: int = 42

    def __post_init__(self):
        super().__post_init__()
        if self.obs_dim != 15 or tuple(self.action_mask) != (0,1,1) or self.speed_reference_schedule is not None:
            raise ValueError("version4 enables speed only, with its own explicit schedule")
        s=np.asarray(self.speed_schedule,float)
        if s.shape!=(4,) or not np.isfinite(s).all() or min(s[:2])<=0 or not 0<=s[2]<s[3]:
            raise ValueError("invalid inherited speed schedule")
        if not np.isfinite(self.speed_scale) or self.speed_scale<0:
            raise ValueError("nonnegative finite speed scale required")


class FrozenSpeedMADDPG(MADDPG):
    def __init__(self, config, device="cpu"):
        super().__init__(config,device)
        self.actors.requires_grad_(False)
        with torch.random.fork_rng():
            torch.manual_seed(config.head_seed)
            self.speed_heads=nn.ModuleList([nn.Sequential(nn.Linear(15,32),nn.ReLU(),nn.Linear(32,1),nn.Tanh()) for _ in range(3)]).to(self.device)
            with torch.no_grad():
                for head in self.speed_heads:
                    head[-2].weight.zero_();head[-2].bias.zero_()
        self.target_speed_heads=deepcopy(self.speed_heads).requires_grad_(False)
        self.head_optimizers=[torch.optim.Adam(h.parameters(),lr=config.actor_lr) for h in self.speed_heads]
        self.actor_optimizers=[]

    @classmethod
    def from_parent(cls,parent,head_seed):
        if tuple(parent.config.action_mask)!=(0,1,0) or parent.config.speed_reference_schedule is None:
            raise ValueError("fixed pitch-only parent with scheduled speed required")
        config=asdict(parent.config)
        schedule=config.pop("speed_reference_schedule")
        config.update(action_mask=(0,1,1),speed_reference_schedule=None,speed_schedule=tuple(schedule),head_seed=head_seed)
        rng=torch.get_rng_state().clone()
        agent=cls(FrozenSpeedConfig(**config),str(parent.device))
        torch.set_rng_state(rng)
        for name in ("actors","target_actors","critics","target_critics"):
            getattr(agent,name).load_state_dict(getattr(parent,name).state_dict())
        for dst,src in zip(agent.critic_optimizers,parent.critic_optimizers):dst.load_state_dict(deepcopy(src.state_dict()))
        agent.replay.load_state_dict(parent.replay.state_dict())
        agent.rng.bit_generator.state=deepcopy(parent.rng.bit_generator.state)
        agent.updates=parent.updates
        return agent

    def parent_action(self,index,obs,*,target=False):
        actor=(self.target_actors if target else self.actors)[index]
        with torch.no_grad():raw=actor(obs)
        return torch.stack((torch.full_like(raw[...,1],self.config.fixed_action[0]),raw[...,1],speed_torch(obs,self.config.speed_schedule)),dim=-1)

    def policy(self,actor,obs):
        for target,actors in ((False,self.actors),(True,self.target_actors)):
            for index,registered in enumerate(actors):
                if actor is registered:return self.total_action(index,obs,target=target)
        raise ValueError("policy requires a registered online or target parent Actor")

    def total_action(self,index,obs,*,target=False,noise=None,zero_speed=False):
        parent=self.parent_action(index,obs,target=target)
        head=(self.target_speed_heads if target else self.speed_heads)[index]
        raw=head(obs).squeeze(-1)
        if noise is not None:raw=raw+noise
        correction=raw.clamp(-1,1)*self.config.speed_scale if not zero_speed else torch.zeros_like(raw)
        return torch.stack((parent[...,0],parent[...,1],(parent[...,2]+correction).clamp(-1,1)),dim=-1)

    def act(self,obs,*,noise=None,zero_speed=False):
        obs=np.asarray(obs,dtype=np.float32)
        if obs.shape!=(3,15) or not np.isfinite(obs).all():raise ValueError("finite [3,15] observation required")
        noise=np.zeros((3,3),np.float32) if noise is None else np.asarray(noise,np.float32)
        if noise.shape!=(3,3) or not np.isfinite(noise).all():raise ValueError("finite raw-coordinate [3,3] noise required")
        with torch.no_grad():
            x=torch.as_tensor(obs,device=self.device)
            return torch.stack([self.total_action(i,x[i],noise=torch.as_tensor(noise[i,2],device=self.device),zero_speed=zero_speed) for i in range(3)]).cpu().numpy().astype(np.float32)

    def update(self):
        c=self.config;b=self.replay.sample(c.batch_size,self.device)
        obs,actions=b["obs"],b["actions"];flat=obs.flatten(1)
        with torch.no_grad():
            nxt=torch.stack([self.total_action(i,b["next_obs"][:,i],target=True) for i in range(3)],dim=1)
            target_input=torch.cat((b["next_obs"].flatten(1),nxt.flatten(1)),dim=1)
            targets=[self.td_target(b["rewards"][:,i:i+1],b["terminated"],critic(target_input),c.gamma) for i,critic in enumerate(self.target_critics)]
        actor_losses,critic_losses,actor_norms,critic_norms=[],[],[],[]
        for i in range(3):
            critic=self.critics[i]
            loss=nn.functional.mse_loss(critic(torch.cat((flat,actions.flatten(1)),dim=1)),targets[i])
            if not torch.isfinite(loss):raise FloatingPointError("nonfinite Critic loss")
            self.critic_optimizers[i].zero_grad(set_to_none=True);loss.backward()
            critic_norms.append(float(nn.utils.clip_grad_norm_(critic.parameters(),c.grad_clip,error_if_nonfinite=True)))
            self.critic_optimizers[i].step();critic_losses.append(loss.item())
            critic.requires_grad_(False)
            joint=torch.stack([self.total_action(i,obs[:,i]) if j==i else actions[:,j].detach() for j in range(3)],dim=1)
            actor_loss=-critic(torch.cat((flat,joint.flatten(1)),dim=1)).mean()
            if not torch.isfinite(actor_loss):raise FloatingPointError("nonfinite speed-head loss")
            self.head_optimizers[i].zero_grad(set_to_none=True);actor_loss.backward()
            actor_norms.append(float(nn.utils.clip_grad_norm_(self.speed_heads[i].parameters(),c.grad_clip,error_if_nonfinite=True)))
            self.head_optimizers[i].step();actor_losses.append(actor_loss.item())
            critic.requires_grad_(True)
        with torch.no_grad():
            # Parent target follows the unchanged online mapping; initial lag is inherited.
            for source,target in ((self.actors,self.target_actors),(self.speed_heads,self.target_speed_heads),(self.critics,self.target_critics)):
                for p,tp in zip(source.parameters(),target.parameters()):tp.lerp_(p,c.tau)
        self.updates+=1
        return dict(actor_loss=float(np.mean(actor_losses)),critic_loss=float(np.mean(critic_losses)),actor_grad_norm=float(np.mean(actor_norms)),critic_grad_norm=float(np.mean(critic_norms)))

    def save(self,path,metadata):
        torch.save(dict(version=4,action_semantics=SEMANTICS,config=asdict(self.config),
            **{k:getattr(self,k).state_dict() for k in ("actors","target_actors","critics","target_critics","speed_heads","target_speed_heads")},
            head_optimizers=[o.state_dict() for o in self.head_optimizers],critic_optimizers=[o.state_dict() for o in self.critic_optimizers],
            replay=self.replay.state_dict(),rng=self.rng.bit_generator.state,torch_rng=torch.get_rng_state(),updates=self.updates,metadata=metadata),path)

    @classmethod
    def load(cls,path,device="cpu"):
        state=torch.load(path,map_location=device,weights_only=False)
        if state.get("version")!=4 or state.get("action_semantics")!=SEMANTICS:raise ValueError("explicit frozen-speed version4 required")
        agent=cls(FrozenSpeedConfig(**state["config"]),device)
        for k in ("actors","target_actors","critics","target_critics","speed_heads","target_speed_heads"):getattr(agent,k).load_state_dict(state[k])
        for k in ("head_optimizers","critic_optimizers"):
            for dst,src in zip(getattr(agent,k),state[k]):dst.load_state_dict(src)
        agent.replay.load_state_dict(state["replay"]);agent.rng.bit_generator.state=state["rng"]
        torch.set_rng_state(state["torch_rng"].cpu());agent.updates=state["updates"]
        return agent,state["metadata"]


def load_policy(path):
    position=path.tell() if hasattr(path,"tell") else None
    state=torch.load(path,map_location="cpu",weights_only=False)
    if position is not None:path.seek(position)
    return FrozenSpeedMADDPG.load(path) if state.get("version")==4 else MADDPG.load(path)
