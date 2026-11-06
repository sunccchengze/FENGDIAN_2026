"""Target semantics and recovery tests for the single frozen n-step trial."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import numpy as np
import torch
from optimization_control.maddpg_wind_farm.algorithm import AlgorithmConfig, MADDPG
from optimization_control.maddpg_wind_farm.nstep_algorithm import NStepMADDPG, SequenceReplay


def equal(test, a, b):
    if isinstance(a, torch.Tensor):
        test.assertTrue(torch.equal(a, b))
    elif isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b)
    elif isinstance(a, dict):
        test.assertEqual(a.keys(), b.keys())
        for k in a:
            equal(test, a[k], b[k])
    elif isinstance(a, (list, tuple)):
        for x, y in zip(a, b):
            equal(test, x, y)
    else:
        test.assertEqual(a, b)


def observation(t, episode=0):
    x = np.full((3, 15), episode + t / 100, np.float32)
    x[:, 14] = 1 - t / 16
    x[:, 1] = .7 + t / 100
    return x


def fill(replay, count, start=0):
    for j in range(start, start + count):
        ep, t = divmod(j, 16)
        replay.add(observation(t, ep), np.full((3, 3), t / 32, np.float32),
                   np.array([1, 2, 3], np.float32) * (j + 1), observation(t + 1, ep), t == 15)


class NStepTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.c = AlgorithmConfig(batch_size=4, capacity=32, hidden=8, gamma=.5,
                                 action_mask=(0, 1, 0), speed_reference_schedule=(12., .11114035087719298, .6, 1.267))

    def test_one_step_exact_original_updates_and_adam(self):
        original = MADDPG(self.c); fill(original.replay, 32)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'legacy.pth'; original.save(p, {})
            candidate, _ = NStepMADDPG.inherit(p, 1)
            for _ in range(3):
                equal(self, original.update(), candidate.update())
                for name in ('actors', 'critics', 'target_actors', 'target_critics'):
                    equal(self, getattr(original, name).state_dict(), getattr(candidate, name).state_dict())
                for name in ('actor_optimizers', 'critic_optimizers'):
                    for a, b in zip(getattr(original, name), getattr(candidate, name)):
                        equal(self, a.state_dict(), b.state_dict())
            equal(self, original.replay.rng.bit_generator.state, candidate.replay.rng.bit_generator.state)

    def test_returns_terminal_actual_tail_and_all_agents(self):
        r = SequenceReplay(self.c, 8); fill(r, 20)
        values, end, m = r.spans([0, 14, 16, 19])
        np.testing.assert_array_equal(m, [8, 2, 4, 1]); np.testing.assert_array_equal(end, [7, 15, 19, 19])
        for row, (start, length) in enumerate(zip([0, 14, 16, 19], m)):
            expected = sum(.5**k * np.array([1, 2, 3]) * (start + k + 1) for k in range(length))
            np.testing.assert_array_equal(values[row], expected)
        self.assertEqual(r.data['terminated'][end[1], 0], 1)
        self.assertEqual(r.data['terminated'][end[-1], 0], 0)
        with self.assertRaises(ValueError):
            r.add(observation(1), np.zeros((3, 3)), np.zeros(3), observation(2), [False, True, False])

    def test_wrap_overwrite_and_new_future_changes_only_available_tail(self):
        r = SequenceReplay(self.c, 8); fill(r, 35)
        _, ends, m = r.spans([2, 3, 30])
        np.testing.assert_array_equal(m, [1, 8, 2])
        np.testing.assert_array_equal(ends, [2, 10, 31])
        fill(r, 5, start=35)
        _, _, m = r.spans([2, 7, 8])
        np.testing.assert_array_equal(m, [6, 1, 8])
        legacy = {k: v for k, v in r.state_dict().items() if k in ('data', 'size', 'position', 'rng')}
        restored = SequenceReplay(self.c, 8); restored.load_state_dict(legacy)
        equal(self, r.spans([2, 7, 8]), restored.spans([2, 7, 8]))

    def test_reject_nonterminal_episode_crossing_and_continuity(self):
        r = SequenceReplay(self.c, 8); fill(r, 20)
        r.data['terminated'][15] = 0
        with self.assertRaises(ValueError):
            r.spans([15])
        r = SequenceReplay(self.c, 8); fill(r, 20)
        r.data['obs'][2, 0, 0] += .1
        with self.assertRaises(ValueError):
            r.spans([0])

    def test_target_uses_endpoint_policy_scaled_reward_and_gamma_power(self):
        agent = NStepMADDPG(self.c); agent.configure(8); fill(agent.replay, 20)
        b = agent.replay.sample(4, 'cpu')
        idx = agent.replay.last_indices
        values, end, lengths = agent.replay.spans(idx)
        equal(self, b['next_obs'].numpy(), agent.replay.data['next_obs'][end])
        next_actions = torch.stack([agent.policy(a, b['next_obs'][:, i]) for i, a in enumerate(agent.target_actors)], 1)
        expected_speed = torch.clamp(2 * (b['next_obs'][:, :, 1] * 12 * .11114035087719298 - .6) / (1.267 - .6) - 1, -1, 1)
        self.assertTrue(torch.equal(next_actions[:, :, 2], expected_speed))
        self.assertTrue(torch.equal(next_actions[:, :, 0], torch.zeros_like(expected_speed)))
        target = agent.td_target(b['rewards'][:, 1:2], b['terminated'], torch.full((4, 1), 7.), .5)
        np.testing.assert_array_equal(target.numpy()[:, 0], values[:, 1] + .5**lengths * (1 - agent.replay.data['terminated'][end, 0]) * 7)

    def test_restore_next_update_exact_and_reject_wrong_horizon(self):
        agent = NStepMADDPG(self.c); agent.configure(8); fill(agent.replay, 35); agent.update()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'n8.pth'; agent.save(p, {'steps': 35})
            restored, meta = NStepMADDPG.load(p, 8)
            self.assertEqual(meta['steps'], 35)
            equal(self, agent.update(), restored.update())
            for name in ('actors', 'critics', 'target_actors', 'target_critics'):
                equal(self, getattr(agent, name).state_dict(), getattr(restored, name).state_dict())
            equal(self, agent.replay.state_dict(), restored.replay.state_dict())
            with self.assertRaises(ValueError):
                NStepMADDPG.load(p, 1)


if __name__ == '__main__':
    unittest.main()
