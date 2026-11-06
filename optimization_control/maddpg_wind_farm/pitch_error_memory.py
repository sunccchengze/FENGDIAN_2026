"""Private n8 continuation with a causal scalar supplied alongside the original observation."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from functools import partial

import numpy as np
import torch
from torch import nn

from .algorithm import AlgorithmConfig
from .nstep_algorithm import NStepMADDPG, SequenceReplay, TAIL_RULE

VERSION = "pitch_error_memory_v1"
RULE = "current_obs9_float32_clipped_total_pitch_conditional_integral_v1"
LIMIT = .02
GAIN = .08
HORIZON = 128
CLOCKS = frozenset(i / HORIZON for i in range(1, HORIZON + 1))
NETWORKS = ("actors", "critics", "target_actors", "target_critics")
OPTIMIZERS = ("actor_optimizers", "critic_optimizers")


def advance_integral(integral, obs, clipped_command):
    """Use the current observation and this decision's post-mapper normalized command."""
    if not -LIMIT <= integral <= LIMIT:
        raise ValueError("invalid integral state")
    if obs.shape != (3, 15) or obs.dtype != np.float32:
        raise ValueError("expected the original float32 observation")
    if clipped_command.shape != (3, 3) or clipped_command.dtype != np.float32:
        raise ValueError("expected a float32 clipped total command")
    errors = obs[:, 9]
    if not np.isfinite(errors).all() or not np.all(errors == errors[0]):
        raise ValueError("expected one finite common farm error")
    if not np.isfinite(clipped_command).all() or np.any(np.abs(clipped_command) > 1):
        raise ValueError("invalid clipped normalized command")
    delta = GAIN * float(errors[0])
    pitch = clipped_command[:, 1]
    if (delta > 0 and (integral == LIMIT or np.any(pitch == 1))) or (
        delta < 0 and (integral == -LIMIT or np.any(pitch == -1))
    ):
        return float(integral)
    return max(-LIMIT, min(LIMIT, float(integral) + delta))


class MemoryReplay(SequenceReplay):
    def __init__(self, config):
        super().__init__(config, 8)
        self.data["integral"] = np.empty((self.capacity, 1), dtype=np.float64)
        self.data["next_integral"] = np.empty((self.capacity, 1), dtype=np.float64)

    def _order(self):
        slots = np.flatnonzero(self.sequence >= 0)
        order = slots[np.argsort(self.sequence[slots])]
        expected = (self.position - self.size + np.arange(self.size)) % self.capacity
        if not np.array_equal(order, expected):
            raise ValueError("sequence IDs and ring slots disagree")
        return order

    @staticmethod
    def _validate_transition(obs, command, next_obs, done):
        if obs.shape != (3, 15) or next_obs.shape != (3, 15):
            raise ValueError("expected original observation dimensions")
        clock = float(obs[0, 14])
        if (
            clock not in CLOCKS
            or not np.all(obs[:, 14] == clock)
            or not np.all(next_obs[:, 14] == clock - 1 / HORIZON)
            or done != (clock == 1 / HORIZON)
        ):
            raise ValueError("replay clock or terminal mismatch")
        if not np.array_equal(next_obs[:, 5:8], command):
            raise ValueError("replay action differs from next observation's previous command")
        return clock

    def _scan(self, reconstruct):
        previous = None
        following = None
        episodes = 0
        for slot in self._order():
            obs, command, next_obs, done = (
                self.data[key][slot] for key in ("obs", "actions", "next_obs", "terminated")
            )
            clock = self._validate_transition(obs, command, next_obs, self.shared_done(done))
            if clock == 1:
                if previous is not None and not self.data["terminated"][previous, 0]:
                    raise ValueError("reset without terminal")
                integral = 0.
                episodes += 1
            elif previous is None:
                if reconstruct or self.size != self.capacity:
                    raise ValueError("cannot reconstruct an incomplete oldest episode")
                integral = float(self.data["integral"][slot, 0])
            else:
                if self.data["terminated"][previous, 0] or not np.array_equal(
                    self.data["next_obs"][previous], obs
                ):
                    raise ValueError("broken chronological replay edge")
                integral = following
            following = advance_integral(integral, obs, command)
            if reconstruct:
                self.data["integral"][slot, 0] = integral
                self.data["next_integral"][slot, 0] = following
            elif (self.data["integral"][slot, 0], self.data["next_integral"][slot, 0]) != (
                integral, following
            ):
                raise ValueError("inconsistent saved memory")
            previous = slot
        if reconstruct and (previous is None or not self.data["terminated"][previous, 0]):
            raise ValueError("parent replay must end at a complete episode")
        return episodes

    def inherit(self, parent):
        old = parent.state_dict()
        # SequenceReplay loads every field in self.data. Supply storage for the new
        # columns, then fill every valid slot from complete chronological episodes.
        for key in ("integral", "next_integral"):
            old["data"][key] = np.empty((old["size"], 1), dtype=np.float64)
        super().load_state_dict(old)
        return self._scan(reconstruct=True)

    def load_state_dict(self, state):
        if state.get("n") != 8 or state.get("tail_rule") != TAIL_RULE:
            raise ValueError("invalid memory replay horizon")
        for key in ("integral", "next_integral"):
            column = state["data"].get(key)
            if column is None or column.dtype != np.float64 or column.shape != (state["size"], 1):
                raise ValueError("invalid memory replay column")
        super().load_state_dict(state)
        self._scan(reconstruct=False)

    def add(self, obs, actions, rewards, next_obs, terminated, *, integral):
        done = self.shared_done(terminated)
        clock = self._validate_transition(obs, actions, next_obs, done)
        if self.size:
            previous = (self.position - 1) % self.capacity
            previous_done = bool(self.data["terminated"][previous, 0])
            if (clock == 1) != previous_done:
                raise ValueError("reset does not match previous terminal")
            if not previous_done and (
                not np.array_equal(self.data["next_obs"][previous], obs)
                or integral != self.data["next_integral"][previous, 0]
            ):
                raise ValueError("memory or observation discontinuity")
        elif clock != 1:
            raise ValueError("empty replay requires a reset")
        if clock == 1 and integral != 0:
            raise ValueError("episode must begin at zero integral")
        following = advance_integral(integral, obs, actions)
        slot = self.position
        # The parent writer iterates its five original fields and preserves the
        # physical slot and sequence ID used by the two additional columns.
        super().add(obs, actions, rewards, next_obs, done)
        self.data["integral"][slot, 0] = integral
        self.data["next_integral"][slot, 0] = following
        return following

    def sample(self, size, device):
        # Delegate indices, rewards, discounts and the histogram to the original n8
        # sampler. Its "next_obs" convention must also apply to next_integral.
        batch = super().sample(size, device)
        ends = (self.last_indices + self.last_lengths - 1) % self.capacity
        batch["next_integral"] = torch.as_tensor(self.data["next_integral"][ends], device=device)
        return batch


class MemoryMLP(nn.Sequential):
    def __init__(self, original):
        super().__init__(*original.children())
        first = self[0].weight
        self.memory_weight = nn.Parameter(
            first.new_zeros((first.shape[0], 1)), requires_grad=first.requires_grad
        )

    def forward(self, inputs, *, context=None):
        if context is None:
            return super().forward(inputs)
        hidden = self[0](inputs) + nn.functional.linear(context, self.memory_weight)
        for layer in list(self)[1:]:
            hidden = layer(hidden)
        return hidden


class PitchErrorMemory(NStepMADDPG):
    def _attach(self, arm, purpose):
        c = self.config
        if (
            arm not in ("zero", "memory") or purpose not in ("engineering", "formal")
            or c.obs_dim != 15 or c.hidden != 64 or c.gamma != .99 or self.n != 8
            or tuple(c.action_mask) != (0, 1, 0) or self.device.type != "cpu"
        ):
            raise ValueError("unsupported pitch error memory contract")
        self.arm, self.purpose = arm, purpose
        for name in NETWORKS:
            setattr(self, name, nn.ModuleList(MemoryMLP(m) for m in getattr(self, name)))
        for name, models in zip(OPTIMIZERS, (self.actors, self.critics)):
            for optimizer, model in zip(getattr(self, name), models):
                optimizer.add_param_group({"params": [model.memory_weight]})

    @classmethod
    def from_parent(cls, path, arm, *, purpose):
        agent, metadata = NStepMADDPG.load(path, expected_n=8)
        agent.__class__ = cls
        agent._attach(arm, purpose)
        replay = MemoryReplay(agent.config)
        episodes = replay.inherit(agent.replay)
        agent.replay = replay
        return agent, metadata, episodes

    def act(self, obs, noise_std=0., *, integral=None):
        if self.arm == "zero":
            return super().act(obs, noise_std)
        if integral is None or not -LIMIT <= integral <= LIMIT:
            raise ValueError("memory arm requires current integral")
        obs = np.asarray(obs, dtype=np.float32)
        if obs.shape != (3, 15) or not np.isfinite(obs).all():
            raise ValueError("invalid observation")
        with torch.no_grad():
            x = torch.as_tensor(obs, device=self.device)
            z = x.new_tensor([integral / LIMIT])
            action = torch.stack([
                self.policy(partial(actor, context=z), x[i])
                for i, actor in enumerate(self.actors)
            ]).cpu().numpy()
        if noise_std:
            noise = self.rng.normal(0, noise_std, action.shape)
            action = np.where(self.config.action_mask, action + noise, action)
        return np.clip(action, -1, 1).astype(np.float32)

    def update(self):
        if self.arm == "zero":
            return super().update()
        c = self.config
        b = self.replay.sample(c.batch_size, self.device)
        obs, actions = b["obs"], b["actions"]
        flat_obs = obs.flatten(1)
        context = (b["integral"] / LIMIT).to(obs.dtype)
        next_context = (b["next_integral"] / LIMIT).to(obs.dtype)
        with torch.no_grad():
            next_actions = torch.stack([
                self.policy(partial(actor, context=next_context), b["next_obs"][:, i])
                for i, actor in enumerate(self.target_actors)
            ], dim=1)
            target_input = torch.cat((b["next_obs"].flatten(1), next_actions.flatten(1)), dim=1)
            targets = [
                self.td_target(b["rewards"][:, i:i+1], b["terminated"],
                               critic(target_input, context=next_context), c.gamma)
                for i, critic in enumerate(self.target_critics)
            ]
        actor_losses, critic_losses, actor_norms, critic_norms, q_values, td_errors = [], [], [], [], [], []
        for i, (actor, critic) in enumerate(zip(self.actors, self.critics)):
            q = critic(torch.cat((flat_obs, actions.flatten(1)), dim=1), context=context)
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
            critic.requires_grad_(False)
            try:
                joint = torch.stack([
                    self.policy(partial(actor, context=context), obs[:, i]) if i == j else actions[:, j].detach()
                    for j in range(c.agents)
                ], dim=1)
                actor_loss = -critic(torch.cat((flat_obs, joint.flatten(1)), dim=1), context=context).mean()
                if not torch.isfinite(actor_loss):
                    raise FloatingPointError("non-finite actor loss")
                self.actor_optimizers[i].zero_grad(set_to_none=True)
                actor_loss.backward()
                actor_norms.append(float(nn.utils.clip_grad_norm_(actor.parameters(), c.grad_clip, error_if_nonfinite=True)))
                self.actor_optimizers[i].step()
                actor_losses.append(actor_loss.item())
            finally:
                critic.requires_grad_(True)
        with torch.no_grad():
            for source, target in ((self.actors, self.target_actors), (self.critics, self.target_critics)):
                for p, tp in zip(source.parameters(), target.parameters()):
                    tp.lerp_(p, c.tau)
        self.updates += 1
        return dict(actor_loss=float(np.mean(actor_losses)), critic_loss=float(np.mean(critic_losses)),
                    actor_grad_norm=float(np.mean(actor_norms)), critic_grad_norm=float(np.mean(critic_norms)),
                    q_mean=float(np.mean(q_values)), td_abs_mean=float(np.mean(td_errors)))

    def checkpoint(self, metadata):
        if not self.replay.size or not self.replay.data["terminated"][(self.replay.position - 1) % self.replay.capacity, 0]:
            raise ValueError("checkpoint requires an episode boundary")
        state = dict(version=VERSION, memory_rule=RULE, integral_limit=LIMIT, integral_gain=GAIN,
                     arm=self.arm, purpose=self.purpose, config=asdict(self.config), n=8, tail_rule=TAIL_RULE,
                     replay=self.replay.state_dict(), rng=self.rng.bit_generator.state,
                     torch_rng=torch.get_rng_state(), updates=self.updates, metadata=metadata)
        state.update({name: getattr(self, name).state_dict() for name in NETWORKS})
        state.update({name: [o.state_dict() for o in getattr(self, name)] for name in OPTIMIZERS})
        return state

    def save(self, path, metadata):
        state = self.checkpoint(metadata)
        with open(path, "xb") as handle:
            torch.save(state, handle)

    @classmethod
    def load(cls, path, *, expected_arm, purpose):
        state = torch.load(path, map_location="cpu", weights_only=False)
        expected = (VERSION, RULE, LIMIT, GAIN, expected_arm, purpose, 8, TAIL_RULE)
        fields = ("version", "memory_rule", "integral_limit", "integral_gain", "arm", "purpose", "n", "tail_rule")
        if tuple(state.get(key) for key in fields) != expected:
            raise ValueError("incompatible memory checkpoint format, rule, arm or purpose")
        agent = cls(AlgorithmConfig(**state["config"]))
        agent.n = 8
        agent._attach(expected_arm, purpose)
        for name in NETWORKS:
            getattr(agent, name).load_state_dict(state[name])
        for name in OPTIMIZERS:
            for optimizer, saved in zip(getattr(agent, name), state[name], strict=True):
                optimizer.load_state_dict(saved)
        agent.replay = MemoryReplay(agent.config)
        agent.replay.load_state_dict(state["replay"])
        if not agent.replay.size or not agent.replay.data["terminated"][(agent.replay.position - 1) % agent.replay.capacity, 0]:
            raise ValueError("checkpoint does not end at an episode boundary")
        agent.rng.bit_generator.state = deepcopy(state["rng"])
        torch.set_rng_state(state["torch_rng"])
        agent.updates = state["updates"]
        return agent, state["metadata"]
