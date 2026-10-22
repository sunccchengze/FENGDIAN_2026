"""Shared state-dependent schedules, Cartesian scenarios and legacy behavior."""
from copy import deepcopy
import io
import unittest
import numpy as np
import torch

from optimization_control.maddpg_wind_farm.workflow import build_env, make_agent, load_config, DEFAULT_CONFIG
from optimization_control.maddpg_wind_farm.algorithm import MADDPG, AlgorithmConfig
from optimization_control.maddpg_wind_farm.controllers import PitchController
from optimization_control.maddpg_wind_farm.random_wind_training import read_protocol, DEFAULT, episode_design


class RandomTrainingTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.cfg = load_config(DEFAULT_CONFIG)
        self.cfg["environment"].update(horizon=8, control_mask=[0, 1, 0], wind_amplitude_m_s=0., wind_noise_std_m_s=0.,
            wind_base_m_s=9., wind_direction_rad=0., turbulence_intensity=.08,
            action_low=[-.25, 0., .6], action_high=[.25, .22, 1.267],
            reference_schedule=dict(yaw_offset_rad=0., speed_per_wind_rad_m=.11114035087719298))

    def test_policy_current_and_target_actions_match_background_schedule(self):
        env = build_env(self.cfg); obs, _ = env.reset()
        agent = make_agent(self.cfg, env)
        action = agent.act(obs)
        np.testing.assert_allclose(action, env.project_action(action), atol=3e-7, rtol=0)
        self.assertGreater(np.ptp(action[:, 2]), 0.)
        noisy = agent.act(obs, noise_std=100.)
        np.testing.assert_array_equal(action[:, [0, 2]], noisy[:, [0, 2]])
        nxt, reward, done, _, info = env.step(action)
        np.testing.assert_allclose(agent.act(nxt), env.project_action(agent.act(nxt)), atol=3e-7, rtol=0)
        target = agent.policy(agent.target_actors[0], torch.as_tensor(nxt[0])).detach().numpy()
        np.testing.assert_allclose(target[[0, 2]], env.project_action(np.zeros((3, 3)))[0, [0, 2]], atol=3e-7)

    def test_schedule_channels_have_no_actor_parameter_gradient(self):
        env = build_env(self.cfg); obs, _ = env.reset()
        agent = make_agent(self.cfg, env)
        value = agent.policy(agent.actors[0], torch.tensor(obs[0]))
        value[[0, 2]].sum().backward()
        self.assertTrue(all(p.grad is not None and torch.count_nonzero(p.grad) == 0 for p in agent.actors[0].parameters()))

    def test_p_pi_and_rl_share_curve_actuator_and_normalization(self):
        a, b = build_env(self.cfg), build_env(self.cfg)
        obs, _ = a.reset(); b.reset()
        controller = PitchController(a, self.cfg["baselines"], "pi")
        action = controller.act(obs)
        np.testing.assert_allclose(action[:, [0, 2]], make_agent(self.cfg, b).act(obs)[:, [0, 2]], atol=3e-7)
        _, _, _, _, x = a.step(action); _, _, _, _, y = b.step(action)
        np.testing.assert_array_equal(x["applied"], y["applied"])
        self.assertIn("reference_schedule", a.normalization())
        self.assertGreater(np.max(np.abs(x["applied"][:, 2] - .9)), 0.)

    def test_old_mask_still_holds_operating_points_without_schedule(self):
        self.cfg["environment"].pop("reference_schedule")
        env = build_env(self.cfg); obs, _ = env.reset()
        agent = make_agent(self.cfg, env)
        self.assertIsNone(agent.config.speed_reference_schedule)
        self.assertNotIn("reference_schedule", env.normalization())
        for _ in range(8):
            obs, _, _, _, info = env.step(agent.act(obs, noise_std=100.))
            np.testing.assert_allclose(info["applied"][:, 2], .9, atol=1e-7)

    def test_open_speed_channel_returns_to_rl_control(self):
        self.cfg["environment"]["control_mask"] = [0, 1, 1]
        env = build_env(self.cfg); obs, _ = env.reset()
        agent = make_agent(self.cfg, env)
        self.assertIsNone(agent.config.speed_reference_schedule)
        requested = np.ones((3, 3)); projected = env.project_action(requested)
        np.testing.assert_array_equal(projected[:, 2], np.ones(3))

    def test_saved_schedule_actions_and_next_update_are_exact(self):
        env = build_env(self.cfg); obs, _ = env.reset()
        agent = make_agent(self.cfg, env)
        for _ in range(64):
            if env._done: obs, _ = env.reset()
            action = agent.act(obs, noise_std=.1)
            nxt, reward, done, _, info = env.step(action)
            agent.replay.add(obs, info["executed_action"], reward, nxt, done); obs = nxt
        agent.update()
        stream = io.BytesIO(); agent.save(stream, dict(test=True)); stream.seek(0)
        other, _ = MADDPG.load(stream)
        np.testing.assert_array_equal(agent.act(obs, .2), other.act(obs, .2))
        self.assertEqual(agent.update(), other.update())

    def test_bad_schedule_rejected(self):
        for value in ((25., .1, .6, 1.2), (25., .1, 1.2, .6), (25., -1., .6, 1.2)):
            if value == (25., .1, .6, 1.2):
                with self.assertRaises(ValueError): AlgorithmConfig(speed_reference_schedule=value)
            else:
                with self.assertRaises(ValueError): AlgorithmConfig(action_mask=(0, 1, 0), speed_reference_schedule=value)
        bad = deepcopy(self.cfg); bad["environment"]["reference_schedule"]["speed_per_wind_rad_m"] = 0
        with self.assertRaises(ValueError): build_env(bad)

    def test_every_block_covers_all_wind_target_combinations(self):
        p = read_protocol(DEFAULT)
        expected = {(f, float(t)) for f in ("stationary", "ramp", "gust") for t in p["training_targets_w"]}
        for run in p["run_ids"]:
            for block in (0, 1, 17):
                values = [episode_design(p, run, block * len(expected) + j) for j in range(len(expected))]
                self.assertEqual({(f, t) for f, t, _ in values}, expected)
                self.assertTrue(all(.025 <= pitch <= .055 for _, _, pitch in values))
                self.assertEqual(values, [episode_design(p, run, block * len(expected) + j) for j in range(len(expected))])
        self.assertNotEqual(episode_design(p, 0, 0), episode_design(p, 1, 0))


if __name__ == "__main__":
    unittest.main()
