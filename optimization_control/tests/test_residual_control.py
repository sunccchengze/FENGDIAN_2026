"""Residual total-action semantics, zero-head transfer and exact recovery."""
from copy import deepcopy
from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from optimization_control.tests import test_progressive_random_control as fixtures
from optimization_control.maddpg_wind_farm.algorithm import MADDPG
from optimization_control.maddpg_wind_farm.residual_algorithm import ResidualMADDPG, ResidualConfig
from optimization_control.maddpg_wind_farm import residual_random_control as flow


class ResidualTests(unittest.TestCase):
    setUp = fixtures.ProgressiveControlTests.setUp

    def child(self):
        return ResidualMADDPG.inherit(self.agent, (0, 1, 1), (0., 1., .3))

    def test_zero_speed_head_preserves_all_replay_and_next_obs_online_target(self):
        state = torch.get_rng_state().clone()
        old = deepcopy(self.agent.actors.state_dict())
        child = self.child()
        self.assertTrue(torch.equal(state, torch.get_rng_state()))
        for field in ("obs", "next_obs"):
            for kind in ("actors", "target_actors"):
                for i, actor in enumerate(getattr(self.agent, kind)):
                    obs = torch.tensor(self.agent.replay.data[field][:256, i])
                    np.testing.assert_array_equal(self.agent.policy(actor, obs).detach(), child.policy(getattr(child, kind)[i], obs).detach())
        for key, value in old.items():
            current = child.actors.state_dict()[key]
            self.assertTrue(torch.equal(value[[0, 1]], current[[0, 1]]) if key.endswith(("4.weight", "4.bias")) else torch.equal(value, current))
        np.testing.assert_equal(child.replay.state_dict(), self.agent.replay.state_dict())
        self.assertTrue(all(not o.state for o in child.actor_optimizers))

    def test_zero_yaw_preserves_learned_speed_and_pitch(self):
        child = self.child()
        child.actors[0][-2].bias.data[2] = .4
        other = ResidualMADDPG.inherit(child, (1, 1, 1), (.2, 1., .3))
        np.testing.assert_array_equal(child.act(self.obs), other.act(self.obs))
        self.assertTrue(all(not p.requires_grad for p in other.target_actors.parameters()))

    def test_raw_noise_cannot_escape_physical_residual_envelope(self):
        child = self.child()
        obs = torch.tensor(self.obs)
        baseline = child.compose(torch.zeros((3, 3)), obs).detach().numpy()
        for sign in (-1, 1):
            action = child.act(self.obs, noise=np.full((3, 3), sign * 100.))
            self.assertLessEqual(np.abs(action[:, 2] - baseline[:, 2]).max(), .300001)
            self.assertTrue(np.all(np.abs(action) <= 1))
            np.testing.assert_array_equal(action[:, 0], baseline[:, 0])

    def test_new_speed_and_yaw_rows_receive_nonzero_gradient(self):
        child = ResidualMADDPG.inherit(self.child(), (1, 1, 1), (.2, 1., .3))
        obs = torch.tensor(self.obs[0:1])
        obs[:, 1] = 8.5 / child.config.residual_speed_schedule[0]
        action = child.policy(child.actors[0], obs)
        (action[:, 0] + action[:, 2]).sum().backward()
        gradient = child.actors[0][-2].bias.grad
        self.assertGreater(abs(float(gradient[0])), 0.)
        self.assertGreater(abs(float(gradient[2])), 0.)

    def test_version_is_explicit_and_checkpoint_next_update_exact(self):
        child = self.child()
        stream = io.BytesIO()
        child.save(stream, dict(step=2048, training_scales=(0., 1., .18)))
        stream.seek(0)
        with self.assertRaises(ValueError):
            MADDPG.load(stream)
        stream.seek(0)
        other, meta = ResidualMADDPG.load(stream)
        self.assertEqual(meta["step"], 2048)
        np.testing.assert_array_equal(child.act(self.obs, .15), other.act(self.obs, .15))
        self.assertEqual(child.update(), other.update())
        old = io.BytesIO()
        self.agent.save(old, {})
        old.seek(0)
        with self.assertRaises(ValueError):
            ResidualMADDPG.load(old)

    def test_permission_order_and_parent_control_reset(self):
        with self.assertRaises(ValueError):
            ResidualMADDPG.inherit(self.agent, (1, 1, 1), (.2, 1., .3))
        control = ResidualMADDPG.inherit(self.agent, (0, 1, 0), (0., 1., 0.), open_channel=False)
        np.testing.assert_array_equal(control.act(self.obs), self.agent.act(self.obs))
        self.assertTrue(all(not o.state for o in control.actor_optimizers))

    def test_full_evaluation_and_training_envelope_are_distinct(self):
        p = flow.protocol(flow.DEFAULT)
        early = flow.scales(p, self.cfg, "pitch_speed", 0)
        full = flow.scales(p, self.cfg, "pitch_speed", 8192)
        self.assertLess(early[2], full[2])
        self.assertEqual(flow.scales(p, self.cfg, "all", 0)[2], full[2])
        self.assertEqual(flow.scales(p, self.cfg, "pitch_speed", 8192, True), (0., 1., 0.))

    def test_worker_cannot_skip_parent_gates_or_frozen_lock(self):
        import yaml
        Path("tmp").mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="residual_gate_", dir="tmp"))
        (root / "config.yaml").write_text(yaml.safe_dump(dict(protocol=flow.protocol(flow.DEFAULT), source_hashes={})), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "all speed streams"):
            flow.parent_for(root, "all", 0)
        (root / "selection.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "frozen selection"):
            flow.parent_for(root, "pitch_speed", 0)

    def test_resume_preserves_incomplete_segment_and_uses_next_directory(self):
        Path("tmp").mkdir(exist_ok=True)
        job = Path(tempfile.mkdtemp(prefix="residual_segment_", dir="tmp"))
        (job / "segment_000").mkdir()
        (job / "segment_001").mkdir()
        (job / "segment_000/state.json").write_text("{}", encoding="utf-8")
        self.assertEqual(flow.next_segment(job), 2)
        self.assertTrue((job / "segment_001").is_dir())


if __name__ == "__main__":
    unittest.main()
