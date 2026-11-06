"""Frozen parent-action regularization; independent version-3 checkpoints."""
from copy import deepcopy
from dataclasses import asdict
import io
from types import SimpleNamespace

import numpy as np
import torch
from torch import nn

from .residual_algorithm import ResidualMADDPG, ResidualConfig, SEMANTICS


class AnchoredMADDPG(ResidualMADDPG):
    @classmethod
    def from_parent(cls, parent, weight, action_scales, *, reset_actor=True):
        scales = np.asarray(action_scales, dtype=float)
        if not np.isfinite(weight) or weight < 0 or scales.shape != (3,) or not np.isfinite(scales).all() or np.any(scales <= 0):
            raise ValueError("finite nonnegative weight and three positive scales required")
        rng = torch.get_rng_state().clone()
        agent = cls(deepcopy(parent.config), str(parent.device))
        torch.set_rng_state(rng)
        for kind in ("actors", "target_actors", "critics", "target_critics"):
            getattr(agent, kind).load_state_dict(getattr(parent, kind).state_dict())
        for kind in ("actor_optimizers", "critic_optimizers"):
            if kind == "actor_optimizers" and reset_actor:
                continue
            for opt, source in zip(getattr(agent, kind), getattr(parent, kind)):
                opt.load_state_dict(deepcopy(source.state_dict()))
        agent.replay.load_state_dict(parent.replay.state_dict())
        agent.rng.bit_generator.state = deepcopy(parent.rng.bit_generator.state)
        agent.updates = parent.updates
        agent.anchor_weight = float(weight)
        agent.anchor_scales = tuple(float(x) for x in scales)
        agent.teacher_config = deepcopy(parent.config)
        agent.teacher_actors = deepcopy(parent.actors).requires_grad_(False).eval()
        return agent

    def teacher_action(self, index, obs):
        with torch.no_grad():
            return ResidualMADDPG.compose(SimpleNamespace(config=self.teacher_config), self.teacher_actors[index](obs), obs)

    def anchor_penalty(self, index, obs, action):
        reference = self.teacher_action(index, obs)
        scale = torch.as_tensor(self.anchor_scales, dtype=action.dtype, device=action.device)
        return ((action - reference) / scale).square().mean()

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
            # Zero weight executes the original objective without extra arithmetic.
            if self.anchor_weight:
                actor_loss = actor_loss + self.anchor_weight * self.anchor_penalty(i, obs[:, i], joint[:, i])
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
        buffer = io.BytesIO()
        super().save(buffer, metadata)
        buffer.seek(0)
        payload = torch.load(buffer, map_location=self.device, weights_only=False)
        payload.update(version=3, anchor_weight=self.anchor_weight, anchor_scales=self.anchor_scales,
                       teacher_config=asdict(self.teacher_config), teacher_actors=self.teacher_actors.state_dict())
        torch.save(payload, path)

    @classmethod
    def load(cls, path, device="cpu"):
        payload = torch.load(path, map_location=device, weights_only=False)
        if payload.get("version") != 3 or payload.get("action_semantics") != SEMANTICS:
            raise ValueError("explicit anchored version-3 checkpoint required")
        weight, scales = payload["anchor_weight"], payload["anchor_scales"]
        teacher_config, teacher_state = payload["teacher_config"], payload["teacher_actors"]
        payload = dict(payload, version=2)
        buffer = io.BytesIO()
        torch.save(payload, buffer)
        buffer.seek(0)
        base, metadata = ResidualMADDPG.load(buffer, device)
        agent = cls.from_parent(base, weight, scales, reset_actor=False)
        agent.teacher_config = ResidualConfig(**teacher_config)
        agent.teacher_actors.load_state_dict(teacher_state)
        return agent, metadata


def load_policy(path):
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if payload.get("version") == 3:
        return AnchoredMADDPG.load(path)
    from .residual_algorithm import load_policy as legacy
    return legacy(path)
