"""Counterfactual isolation, real actuator batching and gradient semantics."""
from copy import deepcopy
import unittest

import numpy as np
import torch

from optimization_control.maddpg_wind_farm.pitch_action_diagnostic import (
    variants, clone_env, corrected_action, batch_step, critic_probe, gradients)
from optimization_control.maddpg_wind_farm.workflow import load_config, DEFAULT_CONFIG, build_env, make_agent
from optimization_control.maddpg_wind_farm.pitch_action_review import paired, aggregate


class PitchActionTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.cfg = load_config(DEFAULT_CONFIG)
        self.cfg['environment'].update(control_mask=[0, 1, 0], action_low=[-.25, 0., .6], action_high=[.25, .22, 1.267],
            reference_schedule=dict(yaw_offset_rad=0., speed_per_wind_rad_m=1.267/11.4), reward_scale=100.)
        self.env = build_env(self.cfg)
        t = np.arange(129)
        self.wind = np.column_stack((9+.4*np.sin(t/7), .02*np.sin(t/30)%(2*np.pi), .04+0*t))
        self.obs, _ = self.env.reset(seed=42, options=dict(wind_trajectory=self.wind, target_w=3.45e6))
        self.agent = make_agent(self.cfg, self.env)

    def test_clone_owns_actuator_and_all_mutable_state(self):
        other = clone_env(self.env)
        before = deepcopy(self.env.actuator.applied_control)
        other.step(np.ones((3, 3), dtype=np.float32))
        self.assertEqual(self.env.t, 0)
        self.assertEqual(other.t, 1)
        for key, value in before.items():
            np.testing.assert_array_equal(self.env.actuator.applied_control[key], value)
        other.trajectory[0, 0] = 100
        self.assertNotEqual(self.env.trajectory[0, 0], 100)
        self.assertIs(other.plant, self.env.plant)

    def test_fixed_grid_changes_pitch_only_and_maps_physical_delta(self):
        grid = variants()
        self.assertEqual(len(grid), 17)
        self.assertEqual(len({tuple(v['vector']) for v in grid}), 17)
        parent = self.agent.act(self.obs)
        for v in grid:
            raw, actual = corrected_action(self.env, parent, v)
            np.testing.assert_array_equal(raw[:, (0, 2)], parent[:, (0, 2)])
            expected = np.clip(parent[:, 1]+np.array(v['vector'])/.11, -1, 1)
            np.testing.assert_allclose(actual[:, 1], expected, atol=2e-7, rtol=0)

    def test_batch_calls_original_steps_and_matches_serial_with_constraints(self):
        grid = variants()
        a = [clone_env(self.env) for _ in grid]
        b = [clone_env(self.env) for _ in grid]
        ao = [self.obs.copy() for _ in grid]
        bo = [self.obs.copy() for _ in grid]
        original = self.env.plant.predictor
        for t in range(16):
            aa = [corrected_action(e, self.agent.act(o), v)[0] for e, o, v in zip(a, ao, grid)]
            ba = [corrected_action(e, self.agent.act(o), v)[0] for e, o, v in zip(b, bo, grid)]
            ar = [e.step(action) for e, action in zip(a, aa)]
            br = batch_step(b, ba)
            self.assertIs(self.env.plant.predictor, original)
            for i, (x, y) in enumerate(zip(ar, br)):
                np.testing.assert_array_equal(x[0], y[0])
                np.testing.assert_array_equal(x[1], y[1])
                np.testing.assert_array_equal(x[4]['applied'], y[4]['applied'])
                self.assertEqual(x[4]['reward_terms'], y[4]['reward_terms'])
                ao[i], bo[i] = x[0], y[0]

    def test_critic_action_gradients_match_finite_differences_without_updates(self):
        action = self.agent.act(self.obs)
        before = [p.detach().clone() for model in (self.agent.actors, self.agent.critics) for p in model.parameters()]
        result = gradients(self.agent, self.obs, action)
        for i in range(3):
            left, right = action.copy(), action.copy()
            left[i, 1] -= .001
            right[i, 1] += .001
            q = critic_probe(self.agent, self.obs, [left, right])
            estimate = float((q[1, i]-q[0, i])/.002)
            self.assertAlmostEqual(result[i]['q_diagonal_gradient_per_normalized_action'], estimate, delta=.001)
            self.assertGreaterEqual(result[i]['actor_pitch_parameter_jacobian_l2'], 0.)
        after = [p for model in (self.agent.actors, self.agent.critics) for p in model.parameters()]
        for x, y in zip(before, after):
            self.assertTrue(torch.equal(x, y))
            self.assertIsNone(y.grad)
        self.assertEqual(self.agent.updates, 0)

    def test_unit_action_ranking_uses_own_critic_and_keeps_outside_support(self):
        base = dict(run_id=0, case_id='example', split='validation', family='ramp', target_w=3.45e6,
                    anchor=32, horizon=8, variant='parent', direction='none', rmse_w=100., mean_error_w=-80.,
                    discounted_return=-1., tracking_return=-.9, action_return=-.1,
                    q_mean=0., q_0=0., q_1=0., q_2=0., local_pitch_outside_fraction=0.)
        candidate = dict(base, variant='unit2_-0.005', direction='unit2', rmse_w=80., discounted_return=-.8,
                         tracking_return=-.7, q_mean=1., q_0=2., q_1=-1., q_2=2., local_pitch_outside_fraction=1/3)
        rows = paired([base, candidate], fork=True)
        self.assertEqual(rows[1]['delta_q_actor'], -1.)
        self.assertEqual(rows[1]['q_sign_opposes_return'], 1)
        self.assertEqual(rows[1]['q_critics_disagree_on_sign'], 1)
        result = next(r for r in aggregate(rows, fork=True) if r['variant']==candidate['variant'])
        self.assertEqual(result['q_opposite_count'], 1)
        self.assertEqual(result['local_support_outside_count'], 1)
        self.assertEqual(result['q_opposite_inside_local_count'], 0)


if __name__ == '__main__':
    unittest.main()
