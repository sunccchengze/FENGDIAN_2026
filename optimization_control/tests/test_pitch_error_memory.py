"""Synthetic clock, command and ring contracts with no predictor or joint updates."""
from copy import deepcopy
import unittest

import numpy as np

from optimization_control.maddpg_wind_farm.algorithm import AlgorithmConfig
from optimization_control.maddpg_wind_farm.nstep_algorithm import SequenceReplay
from optimization_control.maddpg_wind_farm.pitch_error_memory import MemoryReplay, advance_integral


def transition(t, command_pitch=.25):
    obs = np.zeros((3, 15), dtype=np.float32)
    obs[:, 9] = np.float32(.0625)
    obs[:, 14] = (128-t)/128
    obs[:, 6] = command_pitch if t else 0.
    command = np.zeros((3, 3), dtype=np.float32)
    command[:, 1] = command_pitch
    next_obs = obs.copy()
    next_obs[:, 14] -= 1/128
    next_obs[:, 5:8] = command
    return obs, command, np.full(3, t+1, dtype=np.float32), next_obs, t == 127


class ErrorMemoryTests(unittest.TestCase):
    def test_integral_direction_delay_and_command_saturation(self):
        obs, command, _, _, _ = transition(0)
        self.assertEqual(advance_integral(0., obs, command), .005)
        command[1, 1] = 1.
        self.assertEqual(advance_integral(.019, obs, command), .019)
        obs[:, 9] = -.0625
        self.assertEqual(advance_integral(.02, obs, command), .015)
        command[1, 1] = -1.
        self.assertEqual(advance_integral(.01, obs, command), .01)
        command[1, 1] = 0.
        self.assertEqual(advance_integral(-.019, obs, command), -.02)

    def test_reconstruct_wrap_reset_and_sample_actual_endpoint(self):
        config = AlgorithmConfig(capacity=128)
        parent = SequenceReplay(config, 8)
        for t in range(128):
            parent.add(*transition(t))
        replay = MemoryReplay(config)
        self.assertEqual(replay.inherit(parent), 1)
        self.assertEqual(replay.data["integral"][:5, 0].tolist(), [0., .005, .01, .015, .02])
        # Overwrite three slots. The newest span has length 1 and is nonterminal,
        # while the surviving end of the old episode has length 1 and is terminal.
        integral = 0.
        for t in range(3):
            integral = replay.add(*transition(t), integral=integral)
        restored = MemoryReplay(config)
        restored.load_state_dict(replay.state_dict())
        self.assertEqual(restored.sequence[:4].tolist(), [128, 129, 130, 3])
        batch = restored.sample(128, "cpu")
        for i, slot in enumerate(restored.last_indices):
            remaining = 3-slot if slot < 3 else 128-slot
            length = min(8, remaining)
            end = slot+length-1
            self.assertEqual(restored.last_lengths[i], length)
            self.assertEqual(float(batch["integral"][i]), restored.data["integral"][slot, 0])
            self.assertEqual(float(batch["next_integral"][i]), restored.data["next_integral"][end, 0])
            self.assertEqual(bool(batch["terminated"][i]), end == 127)
            np.testing.assert_array_equal(batch["next_obs"][i], restored.data["next_obs"][end])
        invalid = deepcopy(replay.state_dict())
        invalid["data"]["next_integral"][0] = 0.
        with self.assertRaisesRegex(ValueError, "inconsistent saved memory"):
            MemoryReplay(config).load_state_dict(invalid)

    def test_reconstruction_rejects_unknown_start_and_wrong_command(self):
        config = AlgorithmConfig(capacity=128)
        parent = SequenceReplay(config, 8)
        for t in range(128):
            parent.add(*transition(t))
        parent.add(*transition(0))
        with self.assertRaisesRegex(ValueError, "incomplete oldest episode"):
            MemoryReplay(config).inherit(parent)
        parent = SequenceReplay(config, 8)
        for t in range(128):
            parent.add(*transition(t))
        parent.data["actions"][23, 1, 1] = 0.
        with self.assertRaisesRegex(ValueError, "previous command"):
            MemoryReplay(config).inherit(parent)
