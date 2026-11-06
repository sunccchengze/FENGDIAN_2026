"""Parent regularization isolation, gradients and complete recovery."""
from copy import deepcopy
import io
import unittest
import numpy as np
import torch

from optimization_control.tests.test_residual_control import ResidualTests
from optimization_control.maddpg_wind_farm.residual_algorithm import ResidualMADDPG
from optimization_control.maddpg_wind_farm.anchor_algorithm import AnchoredMADDPG
from optimization_control.maddpg_wind_farm.verify_residual_stability import comparable


class AnchorTests(unittest.TestCase):
    setUp = ResidualTests.setUp

    def parent(self):
        speed = ResidualMADDPG.inherit(self.agent, (0, 1, 1), (0., 1., .3))
        return ResidualMADDPG.inherit(speed, (1, 1, 1), (.2, 1., .3))

    def test_zero_weight_exact_original_updates(self):
        parent = self.parent()
        agent = AnchoredMADDPG.from_parent(parent, 0., (.2, 1., .3))
        np.testing.assert_array_equal(parent.act(self.obs), agent.act(self.obs))
        for _ in range(3):
            self.assertEqual(parent.update(), agent.update())
            for kind in ("actors", "target_actors", "critics", "target_critics"):
                np.testing.assert_equal(comparable(getattr(parent, kind).state_dict()), comparable(getattr(agent, kind).state_dict()))
        for kind in ("actor_optimizers", "critic_optimizers"):
            for a, b in zip(getattr(parent, kind), getattr(agent, kind)):
                np.testing.assert_equal(comparable(a.state_dict()), comparable(b.state_dict()))

    def test_teacher_frozen_and_all_channels_receive_gradient(self):
        agent = AnchoredMADDPG.from_parent(self.parent(), 1., (.2, 1., .3))
        before = deepcopy(agent.teacher_actors.state_dict())
        obs = torch.tensor(self.obs[:1])
        obs[:, 1] = 8.5 / agent.config.residual_speed_schedule[0]
        reference = agent.teacher_action(0, obs)
        action = (reference + .03).detach().requires_grad_(True)
        agent.anchor_penalty(0, obs, action).backward()
        self.assertTrue(torch.all(action.grad > 0))
        with torch.no_grad():
            agent.actors[0][-2].bias.add_(.1)
        agent.actor_optimizers[0].zero_grad()
        agent.anchor_penalty(0, obs, agent.policy(agent.actors[0], obs)).backward()
        self.assertTrue(torch.all(agent.actors[0][-2].bias.grad.abs() > 0))
        agent.update()
        np.testing.assert_equal(comparable(before), comparable(agent.teacher_actors.state_dict()))
        self.assertTrue(all(p.grad is None and not p.requires_grad for p in agent.teacher_actors.parameters()))

    def test_same_current_state_and_fixed_teacher_scales(self):
        agent = AnchoredMADDPG.from_parent(self.parent(), 1., (.2, 1., .3))
        obs = torch.tensor(self.obs[:1]); obs[:, 1] = 8.5 / 15
        other = obs.clone(); other[:, 1] = 9.5 / 15
        self.assertFalse(torch.equal(agent.teacher_action(0, obs), agent.teacher_action(0, other)))
        self.assertEqual(float(agent.anchor_penalty(0, obs, agent.teacher_action(0, obs))), 0.)
        from dataclasses import replace
        agent.config = replace(agent.config, residual_scales=(.05, 1., .3))
        self.assertEqual(agent.teacher_config.residual_scales, (.2, 1., .3))
        self.assertEqual(agent.anchor_scales, (.2, 1., .3))

    def test_version3_roundtrip_next_update_and_legacy_rejection(self):
        agent = AnchoredMADDPG.from_parent(self.parent(), 1., (.2, 1., .3))
        agent.update()
        buffer = io.BytesIO(); agent.save(buffer, {"step": 2048}); buffer.seek(0)
        with self.assertRaises(ValueError):
            ResidualMADDPG.load(buffer)
        buffer.seek(0); restored, meta = AnchoredMADDPG.load(buffer)
        self.assertEqual(meta, {"step": 2048})
        np.testing.assert_array_equal(agent.act(self.obs, .1), restored.act(self.obs, .1))
        self.assertEqual(agent.update(), restored.update())
        for kind in ("actors", "critics", "target_actors", "target_critics", "teacher_actors"):
            np.testing.assert_equal(comparable(getattr(agent, kind).state_dict()), comparable(getattr(restored, kind).state_dict()))
        legacy = io.BytesIO(); self.parent().save(legacy, {}); legacy.seek(0)
        with self.assertRaises(ValueError):
            AnchoredMADDPG.load(legacy)

    def test_invalid_penalty_configuration_rejected(self):
        for weight, scales in ((-1, (1, 1, 1)), (float("nan"), (1, 1, 1)), (1, (0, 1, 1))):
            with self.assertRaises(ValueError):
                AnchoredMADDPG.from_parent(self.parent(), weight, scales)


if __name__ == "__main__":
    unittest.main()
