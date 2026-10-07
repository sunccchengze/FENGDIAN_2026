"""MADDPG: independent deterministic actors and centralized per-agent critics."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, asdict
import numpy as np
import torch
from torch import nn


@dataclass
class AlgorithmConfig:
    obs_dim: int = 15
    action_dim: int = 3
    agents: int = 3
    hidden: int = 64
    actor_lr: float = 0.0003
    critic_lr: float = 0.001
    gamma: float = 0.99
    tau: float = 0.01
    batch_size: int = 64
    capacity: int = 20000
    grad_clip: float = 1.0
    seed: int = 42
    action_mask: tuple = (1, 1, 1)
    fixed_action: tuple = (0.0, 0.0, 0.0)
    actor_initial_action: tuple | None = None
    actor_final_scale: float = 0.001

    def __post_init__(self):
        if self.agents != 3 or self.action_dim != 3 or min(self.obs_dim, self.hidden, self.batch_size) <= 0 or self.capacity < self.batch_size:
            raise ValueError("invalid algorithm dimensions or replay capacity")
        if not 0 <= self.gamma <= 1 or not 0 < self.tau <= 1 or min(self.actor_lr, self.critic_lr, self.grad_clip) <= 0:
            raise ValueError("invalid learning hyperparameters")
        if len(self.action_mask) != self.action_dim or len(self.fixed_action) != self.action_dim or not all(v in (0, 1) for v in self.action_mask):
            raise ValueError("invalid action mask")
        if not np.all(np.isfinite(self.fixed_action)) or np.any(np.abs(self.fixed_action) > 1):
            raise ValueError("invalid fixed action")
        if self.actor_initial_action is not None:
            a = np.asarray(self.actor_initial_action)
            if a.shape != (self.action_dim,) or not np.all(np.isfinite(a)) or np.any(np.abs(a) >= 1):
                raise ValueError("actor_initial_action must be strictly inside [-1,1]")
        if not np.isfinite(self.actor_final_scale) or self.actor_final_scale < 0:
            raise ValueError("invalid actor final initialization scale")


def mlp(n_in, hidden, n_out, bounded=False):
    layers = [nn.Linear(n_in, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, n_out)]
    if bounded:
        layers.append(nn.Tanh())
    return nn.Sequential(*layers)


class ReplayBuffer:
    """A transition stores all agents from the same environment step."""

    def __init__(self, c):
        self.capacity, self.size, self.position = c.capacity, 0, 0
        self.rng = np.random.default_rng(c.seed)
        self.data = {"obs": np.zeros((c.capacity, c.agents, c.obs_dim), np.float32),
                     "next_obs": np.zeros((c.capacity, c.agents, c.obs_dim), np.float32),
                     "actions": np.zeros((c.capacity, c.agents, c.action_dim), np.float32),
                     "rewards": np.zeros((c.capacity, c.agents), np.float32),
                     "terminated": np.zeros((c.capacity, 1), np.float32)}

    def add(self, obs, actions, rewards, next_obs, terminated):
        for key, value in dict(obs=obs, actions=actions, rewards=rewards, next_obs=next_obs, terminated=[terminated]).items():
            a = np.asarray(value, dtype=np.float32)
            if a.shape != self.data[key].shape[1:] or not np.all(np.isfinite(a)):
                raise ValueError(f"invalid replay field {key}")
        for key, value in dict(obs=obs, actions=actions, rewards=rewards, next_obs=next_obs, terminated=[terminated]).items():
            self.data[key][self.position] = value
        self.position = (self.position + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, size, device):
        if size > self.size:
            raise ValueError("insufficient replay data")
        idx = self.rng.choice(self.size, size, replace=False)
        return {k: torch.as_tensor(v[idx], device=device) for k, v in self.data.items()}

    def state_dict(self):
        return {"data": {k: v[:self.size].copy() for k, v in self.data.items()},
                "size": self.size, "position": self.position, "rng": self.rng.bit_generator.state}

    def load_state_dict(self, state):
        if state["size"] > self.capacity:
            raise ValueError("checkpoint replay exceeds capacity")
        for k in self.data:
            self.data[k][:state["size"]] = state["data"][k]
        self.size, self.position = state["size"], state["position"]
        self.rng.bit_generator.state = state["rng"]


class MADDPG:
    def __init__(self, config: AlgorithmConfig, device="cpu"):
        self.config, self.device = config, torch.device(device)
        torch.manual_seed(config.seed)
        self.rng = np.random.default_rng(config.seed)
        c = config
        self.actors = nn.ModuleList([mlp(c.obs_dim, c.hidden, c.action_dim, True) for _ in range(c.agents)]).to(device)
        self.critics = nn.ModuleList([mlp(c.agents*(c.obs_dim+c.action_dim), c.hidden, 1) for _ in range(c.agents)]).to(device)
        if c.actor_initial_action is not None:
            for actor in self.actors:
                nn.init.uniform_(actor[-2].weight, -c.actor_final_scale, c.actor_final_scale)
                with torch.no_grad():
                    actor[-2].bias.copy_(torch.as_tensor(np.arctanh(c.actor_initial_action), device=self.device))
        self.target_actors, self.target_critics = deepcopy(self.actors), deepcopy(self.critics)
        self.target_actors.requires_grad_(False)
        self.target_critics.requires_grad_(False)
        self.actor_optimizers = [torch.optim.Adam(m.parameters(), lr=c.actor_lr) for m in self.actors]
        self.critic_optimizers = [torch.optim.Adam(m.parameters(), lr=c.critic_lr) for m in self.critics]
        self.replay, self.updates = ReplayBuffer(c), 0

    def policy(self, actor, obs):
        mask = torch.as_tensor(self.config.action_mask, device=self.device, dtype=torch.bool)
        fixed = torch.as_tensor(self.config.fixed_action, device=self.device, dtype=torch.float32)
        return torch.where(mask, actor(obs), fixed)

    def act(self, obs, noise_std=0.0):
        obs = np.asarray(obs, dtype=np.float32)
        if obs.shape != (self.config.agents, self.config.obs_dim) or not np.all(np.isfinite(obs)):
            raise ValueError("invalid policy observation")
        with torch.no_grad():
            x = torch.as_tensor(obs, device=self.device)
            action = torch.stack([self.policy(actor, x[i]) for i, actor in enumerate(self.actors)]).cpu().numpy()
        if noise_std:
            action += self.rng.normal(0, noise_std, action.shape)
        return np.where(self.config.action_mask, np.clip(action, -1, 1), self.config.fixed_action).astype(np.float32)

    @staticmethod
    def td_target(rewards, terminated, next_q, gamma):
        return rewards + gamma*(1-terminated)*next_q

    def update(self):
        c = self.config
        b = self.replay.sample(c.batch_size, self.device)
        obs, actions = b["obs"], b["actions"]
        flat_obs = obs.flatten(1)
        with torch.no_grad():
            next_actions = torch.stack([self.policy(m, b["next_obs"][:, i]) for i, m in enumerate(self.target_actors)], dim=1)
            target_input = torch.cat((b["next_obs"].flatten(1), next_actions.flatten(1)), dim=1)
            targets = [self.td_target(b["rewards"][:, i:i+1], b["terminated"], critic(target_input), c.gamma)
                       for i, critic in enumerate(self.target_critics)]
        actor_losses, critic_losses, actor_norms, critic_norms, q_values, td_errors = [], [], [], [], [], []
        for i in range(c.agents):
            critic = self.critics[i]
            q = critic(torch.cat((flat_obs, actions.flatten(1)), dim=1))
            loss = nn.functional.mse_loss(q, targets[i])
            if not torch.isfinite(loss):
                raise FloatingPointError("non-finite critic loss")
            self.critic_optimizers[i].zero_grad(set_to_none=True)
            loss.backward()
            critic_norms.append(float(nn.utils.clip_grad_norm_(critic.parameters(), c.grad_clip, error_if_nonfinite=True)))
            q_values.append(float(q.detach().mean()))
            td_errors.append(float((q.detach()-targets[i]).abs().mean()))
            self.critic_optimizers[i].step()
            critic_losses.append(loss.item())
            # Other agents' replay actions remain fixed; gradient flows only to actor i.
            critic.requires_grad_(False)
            joint = torch.stack([self.policy(self.actors[i], obs[:, i]) if j == i else actions[:, j].detach()
                                 for j in range(c.agents)], dim=1)
            actor_loss = -critic(torch.cat((flat_obs, joint.flatten(1)), dim=1)).mean()
            if not torch.isfinite(actor_loss):
                raise FloatingPointError("non-finite actor loss")
            self.actor_optimizers[i].zero_grad(set_to_none=True)
            actor_loss.backward()
            actor_norms.append(float(nn.utils.clip_grad_norm_(self.actors[i].parameters(), c.grad_clip, error_if_nonfinite=True)))
            self.actor_optimizers[i].step()
            critic.requires_grad_(True)
            actor_losses.append(actor_loss.item())
        with torch.no_grad():
            for source, target in ((self.actors, self.target_actors), (self.critics, self.target_critics)):
                for p, tp in zip(source.parameters(), target.parameters()):
                    tp.lerp_(p, c.tau)
        self.updates += 1
        return {"actor_loss": float(np.mean(actor_losses)), "critic_loss": float(np.mean(critic_losses)),
                "actor_grad_norm":float(np.mean(actor_norms)), "critic_grad_norm":float(np.mean(critic_norms)),
                "q_mean":float(np.mean(q_values)), "td_abs_mean":float(np.mean(td_errors))}

    def save(self, path, metadata):
        torch.save({"version": 1, "config": asdict(self.config),
                    "actors": self.actors.state_dict(), "critics": self.critics.state_dict(),
                    "target_actors": self.target_actors.state_dict(), "target_critics": self.target_critics.state_dict(),
                    "actor_optimizers": [o.state_dict() for o in self.actor_optimizers],
                    "critic_optimizers": [o.state_dict() for o in self.critic_optimizers],
                    "replay": self.replay.state_dict(), "rng": self.rng.bit_generator.state,
                    "torch_rng": torch.get_rng_state(), "updates": self.updates,
                    "metadata": metadata}, path)

    @classmethod
    def load(cls, path, device="cpu"):
        # Full training checkpoints include NumPy/RNG objects. Only load trusted local files.
        state = torch.load(path, map_location=device, weights_only=False)
        if state["version"] != 1:
            raise ValueError("unsupported checkpoint version")
        agent = cls(AlgorithmConfig(**state["config"]), device)
        for name in ("actors", "critics", "target_actors", "target_critics"):
            getattr(agent, name).load_state_dict(state[name])
        for name in ("actor_optimizers", "critic_optimizers"):
            for optimizer, saved in zip(getattr(agent, name), state[name]):
                optimizer.load_state_dict(saved)
        agent.replay.load_state_dict(state["replay"])
        agent.rng.bit_generator.state = state["rng"]
        torch.set_rng_state(state["torch_rng"].cpu())
        agent.updates = state["updates"]
        return agent, state["metadata"]
