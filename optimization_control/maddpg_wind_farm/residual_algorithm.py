"""Version-2 bounded baseline-plus-correction MADDPG; replay stores total targets."""
from copy import deepcopy
from dataclasses import asdict, dataclass, replace

import numpy as np
import torch

from .algorithm import AlgorithmConfig, MADDPG

SEMANTICS = "pitch_absolute_yaw_speed_baseline_plus_bounded_correction_v1"


@dataclass
class ResidualConfig(AlgorithmConfig):
    residual_speed_schedule: tuple = (15., 1.267 / 11.4, .6, 1.267)
    residual_scales: tuple = (0., 1., 0.)
    action_semantics: str = SEMANTICS

    def __post_init__(self):
        super().__post_init__()
        schedule = np.asarray(self.residual_speed_schedule, dtype=float)
        scales = np.asarray(self.residual_scales, dtype=float)
        if self.speed_reference_schedule is not None or self.action_semantics != SEMANTICS:
            raise ValueError("residual policy requires explicit version-2 total-action semantics")
        if schedule.shape != (4,) or not np.isfinite(schedule).all() or min(schedule[:2]) <= 0 or not 0 <= schedule[2] < schedule[3]:
            raise ValueError("invalid residual speed baseline")
        if scales.shape != (3,) or not np.isfinite(scales).all() or np.any(scales < 0) or scales[1] != 1:
            raise ValueError("residual scales must preserve absolute pitch")


class ResidualMADDPG(MADDPG):
    def compose(self, raw, obs):
        """Differentiable total normalized reference, also used by target actors."""
        c = self.config
        scale, slope, low, high = c.residual_speed_schedule
        speed = torch.clamp(2 * (obs[..., 1] * scale * slope - low) / (high - low) - 1, -1, 1)
        yaw = torch.full_like(speed, c.fixed_action[0])
        raw = raw.clamp(-1, 1)
        yaw = yaw + raw[..., 0] * c.residual_scales[0] if c.action_mask[0] else yaw
        speed = speed + raw[..., 2] * c.residual_scales[2] if c.action_mask[2] else speed
        return torch.stack((yaw.clamp(-1, 1), raw[..., 1], speed.clamp(-1, 1)), dim=-1)

    def policy(self, actor, obs):
        return self.compose(actor(obs), obs)

    def act(self, obs, noise_std=0., *, noise=None):
        obs = np.asarray(obs, dtype=np.float32)
        if obs.shape != (3, self.config.obs_dim) or not np.isfinite(obs).all():
            raise ValueError("invalid residual policy observation")
        if noise is not None and noise_std:
            raise ValueError("supply one raw-coordinate noise source")
        if noise is None:
            noise = self.rng.normal(0, noise_std, (3, 3)) if noise_std else np.zeros((3, 3))
        noise = np.asarray(noise, dtype=np.float32)
        if noise.shape != (3, 3) or not np.isfinite(noise).all():
            raise ValueError("invalid raw-coordinate exploration")
        with torch.no_grad():
            x = torch.as_tensor(obs, device=self.device)
            raw = torch.stack([actor(x[i]) for i, actor in enumerate(self.actors)])
            raw = (raw + torch.as_tensor(noise, device=self.device)).clamp(-1, 1)
            return self.compose(raw, x).cpu().numpy().astype(np.float32)

    @classmethod
    def inherit(cls, parent, mask, scales, *, open_channel=True):
        """Preserve parent state and RNG, zero only the newly opened output row."""
        old = tuple(parent.config.action_mask)
        new = tuple(mask)
        allowed = {(0, 1, 0): (0, 1, 1), (0, 1, 1): (1, 1, 1)}
        if (open_channel and allowed.get(old) != new) or (not open_channel and old != new):
            raise ValueError("open speed then yaw, exactly one permission per stage")
        state = asdict(parent.config)
        schedule = state.pop("speed_reference_schedule")
        if isinstance(parent, cls):
            schedule = parent.config.residual_speed_schedule
        if schedule is None:
            raise ValueError("scheduled speed baseline must be inherited explicitly")
        state.update(action_mask=new, residual_speed_schedule=tuple(schedule),
                     residual_scales=tuple(scales), speed_reference_schedule=None)
        torch_rng = torch.get_rng_state().clone()
        child = cls(ResidualConfig(**state), str(parent.device))
        torch.set_rng_state(torch_rng)
        for kind in ("actors", "target_actors", "critics", "target_critics"):
            getattr(child, kind).load_state_dict(getattr(parent, kind).state_dict())
        for optimizer, old_optimizer in zip(child.critic_optimizers, parent.critic_optimizers):
            optimizer.load_state_dict(deepcopy(old_optimizer.state_dict()))
        child.replay.load_state_dict(parent.replay.state_dict())
        child.rng.bit_generator.state = deepcopy(parent.rng.bit_generator.state)
        child.updates = parent.updates
        if open_channel:
            channel = next(i for i in range(3) if new[i] and not old[i])
            with torch.no_grad():
                for networks in (child.actors, child.target_actors):
                    for actor in networks:
                        actor[-2].weight[channel].zero_()
                        actor[-2].bias[channel].zero_()
        # All Actor Adam moments reset in child AND paired parent-permission arm.
        return child

    def save(self, path, metadata):
        torch.save(dict(version=2, action_semantics=SEMANTICS, config=asdict(self.config),
            **{kind: getattr(self, kind).state_dict() for kind in ("actors", "target_actors", "critics", "target_critics")},
            actor_optimizers=[o.state_dict() for o in self.actor_optimizers],
            critic_optimizers=[o.state_dict() for o in self.critic_optimizers],
            replay=self.replay.state_dict(), rng=self.rng.bit_generator.state,
            torch_rng=torch.get_rng_state(), updates=self.updates, metadata=metadata), path)

    @classmethod
    def load(cls, path, device="cpu"):
        state = torch.load(path, map_location=device, weights_only=False)
        if state["version"] != 2 or state.get("action_semantics") != SEMANTICS:
            raise ValueError("explicit residual version-2 checkpoint required")
        agent = cls(ResidualConfig(**state["config"]), device)
        for kind in ("actors", "target_actors", "critics", "target_critics"):
            getattr(agent, kind).load_state_dict(state[kind])
        for kind in ("actor_optimizers", "critic_optimizers"):
            for optimizer, saved in zip(getattr(agent, kind), state[kind]):
                optimizer.load_state_dict(saved)
        agent.replay.load_state_dict(state["replay"])
        agent.rng.bit_generator.state = state["rng"]
        torch.set_rng_state(state["torch_rng"].cpu())
        agent.updates = state["updates"]
        return agent, state["metadata"]


def load_policy(path):
    """Trusted local dispatch; version-1 loaders never silently accept version 2."""
    state = torch.load(path, map_location="cpu", weights_only=False)
    return ResidualMADDPG.load(path) if state["version"] == 2 else MADDPG.load(path)
