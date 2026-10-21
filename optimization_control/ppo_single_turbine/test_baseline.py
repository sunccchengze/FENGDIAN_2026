"""T1-R 轻量回归测试：日志、奖励尺度、控制方向与 episode 生命周期。"""

import os
import sys
import unittest

import gymnasium as gym
import numpy as np
import torch

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.normpath(os.path.join(CURRENT_DIR, "..", "environments"))
sys.path.insert(0, ENV_DIR)
sys.path.insert(0, CURRENT_DIR)

from simplified_turbine_env import SimplifiedTurbineEnv
from eval import (
    PController,
    finite_difference_pitch_sensitivity,
    rollout,
    validate_p_controller_direction,
)
from train import Agent, extract_episode_returns


class CountingEnv(SimplifiedTurbineEnv):
    def __init__(self, *args, **kwargs):
        self.reset_count = 0
        super().__init__(*args, **kwargs)

    def reset(self, *args, **kwargs):
        self.reset_count += 1
        return super().reset(*args, **kwargs)


class BaselineRegressionTests(unittest.TestCase):
    def test_episode_returns_support_current_vector_info(self):
        envs = gym.vector.SyncVectorEnv(
            [
                lambda seed=seed: gym.wrappers.RecordEpisodeStatistics(
                    SimplifiedTurbineEnv(seed=seed)
                )
                for seed in (42, 43)
            ],
            autoreset_mode=gym.vector.AutoresetMode.SAME_STEP,
        )
        try:
            envs.reset(seed=42)
            returns = []
            zero_action = np.zeros((2, 2), dtype=np.float32)
            for _ in range(200):
                _, _, _, _, infos = envs.step(zero_action)
                returns.extend(extract_episode_returns(infos))
        finally:
            envs.close()
        self.assertEqual(len(returns), 2)
        self.assertTrue(all(np.isfinite(value) and value != 0.0 for value in returns))

    def test_episode_returns_support_legacy_final_info(self):
        infos = {
            "final_info": np.array(
                [{"episode": {"r": np.array([1.5])}}, None], dtype=object
            ),
            "_final_info": np.array([True, False]),
        }
        self.assertEqual(extract_episode_returns(infos), [1.5])

    def test_action_penalty_is_normalized_by_each_limit(self):
        env = SimplifiedTurbineEnv(seed=42)
        env.reset()
        _, _, _, _, pitch_info = env.step([env.d_beta_max, 0.0])
        env.reset()
        _, _, _, _, speed_info = env.step([0.0, env.d_omega_max])
        self.assertAlmostEqual(pitch_info["action_penalty"], env.lam / 2)
        self.assertAlmostEqual(speed_info["action_penalty"], env.lam / 2)

        env.reset()
        _, _, _, _, clipped_info = env.step([10.0, -10.0])
        self.assertTrue(clipped_info["action_was_clipped"])
        self.assertAlmostEqual(clipped_info["action_penalty"], env.lam)

    def test_p_controller_direction_matches_pitch_sensitivity(self):
        env = SimplifiedTurbineEnv(seed=42)
        controller = PController(obs_scale=env.obs_scale)
        sensitivity = validate_p_controller_direction(env, controller)
        self.assertLess(sensitivity, 0.0)
        self.assertAlmostEqual(sensitivity, finite_difference_pitch_sensitivity(env))

        env.P_target = env.P * 1.1
        self.assertLess(controller.act(env._obs())[0], 0.0)
        env.P_target = env.P * 0.9
        self.assertGreater(controller.act(env._obs())[0], 0.0)

    def test_rollout_resets_and_stops_at_episode_end(self):
        env = CountingEnv(seed=42)
        controller = PController(kp=0.0, obs_scale=env.obs_scale)
        power, target, action = rollout(env, controller=controller, n_episodes=2)
        self.assertEqual(env.reset_count, 2)
        self.assertEqual(len(power), 2 * env.ep_len)
        self.assertEqual(power.shape, target.shape)
        self.assertEqual(action.shape, (2 * env.ep_len, 2))
        self.assertEqual(env.t, env.ep_len)



    def test_reset_target_matches_first_reward_target(self):
        env = SimplifiedTurbineEnv(seed=42)
        observation, _ = env.reset()
        self.assertAlmostEqual(
            float(observation[4] * env.obs_scale[4]),
            env._target_power(),
            delta=1.0,
        )

    def test_squashed_policy_actions_and_logprob_are_consistent(self):
        class Dummy:
            single_observation_space = gym.spaces.Box(
                low=0.0, high=1.0, shape=(5,), dtype=np.float32
            )
            single_action_space = SimplifiedTurbineEnv().action_space

        torch.manual_seed(42)
        agent = Agent(Dummy())
        observation = torch.zeros((64, 5), dtype=torch.float32)
        action, old_logprob, _, _ = agent.get_action_and_value(observation)
        self.assertTrue(torch.all(action >= agent.action_bias - agent.action_scale))
        self.assertTrue(torch.all(action <= agent.action_bias + agent.action_scale))
        _, recomputed_logprob, _, _ = agent.get_action_and_value(
            observation, action
        )
        self.assertTrue(torch.all(torch.isfinite(recomputed_logprob)))
        torch.testing.assert_close(old_logprob, recomputed_logprob)
if __name__ == "__main__":
    unittest.main()
