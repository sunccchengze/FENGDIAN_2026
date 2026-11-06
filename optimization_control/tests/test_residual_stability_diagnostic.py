"""Channel swaps use current observations and ablate only residual components."""
import unittest

import numpy as np
import torch

from optimization_control.maddpg_wind_farm.residual_algorithm import ResidualConfig, ResidualMADDPG
from optimization_control.maddpg_wind_farm.residual_stability_diagnostic import MixedPolicy


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        config = ResidualConfig(hidden=8, action_mask=(1, 1, 1), residual_scales=(.2, 1., .3))
        self.selected = ResidualMADDPG(config)
        self.final = ResidualMADDPG(config)
        with torch.no_grad():
            for agent, bias in ((self.selected, .2), (self.final, -.3)):
                for actor in agent.actors:
                    for parameter in actor.parameters():
                        parameter.zero_()
                    actor[-2].bias.copy_(torch.tensor([bias, 2 * bias, -bias]))
        self.cfg = dict(environment=dict(action_low=[-.25, 0., .6], action_high=[.25, .22, 1.267]))
        self.obs = np.zeros((3, 15), np.float32)
        self.obs[:, 1] = 8.5 / 15

    def test_each_channel_selected_at_current_observation(self):
        policy = MixedPolicy(self.selected, self.final, self.cfg, "SFS")
        expected = self.selected.act(self.obs)
        expected[:, 1] = self.final.act(self.obs)[:, 1]
        np.testing.assert_array_equal(policy.act(self.obs), expected)
        changed = self.obs.copy()
        changed[:, 1] = 9.2 / 15
        after = policy.act(changed)
        self.assertFalse(np.array_equal(after[:, 2], expected[:, 2]))
        np.testing.assert_array_equal(after[:, 2], self.selected.act(changed)[:, 2])

    def test_zero_corrections_recompute_baseline_but_preserve_final_pitch(self):
        policy = MixedPolicy(self.selected, self.final, self.cfg, "FFF", "zero_both")
        action = policy.act(self.obs)
        baseline = self.final.compose(torch.zeros((3, 3)), torch.tensor(self.obs)).detach().numpy()
        np.testing.assert_array_equal(action[:, (0, 2)], baseline[:, (0, 2)])
        np.testing.assert_array_equal(action[:, 1], self.final.act(self.obs)[:, 1])
        report = policy.summary()
        self.assertEqual(report["speed_correction_rms_rad_s"], 0.)
        self.assertEqual(report["yaw_correction_rms_rad"], 0.)
        self.assertGreater(report["pitch_selected_final_drift_rms_rad"], 0.)

    def test_endpoints_and_invalid_mixture(self):
        for mixture, agent in (("SSS", self.selected), ("FFF", self.final)):
            np.testing.assert_array_equal(MixedPolicy(self.selected, self.final, self.cfg, mixture).act(self.obs), agent.act(self.obs))
        with self.assertRaises(ValueError):
            MixedPolicy(self.selected, self.final, self.cfg, "SF")


if __name__ == "__main__":
    unittest.main()
