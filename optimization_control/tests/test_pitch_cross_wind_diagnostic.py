"""Causality, held-out fit isolation, decomposition and instrumentation neutrality."""
import unittest
from types import SimpleNamespace

import numpy as np

from optimization_control.maddpg_wind_farm.pitch_cross_wind_diagnostic import (
    trend_feature, error_parts, forecast_check, rollout)


class PitchDiagnosticTests(unittest.TestCase):
    def test_trend_is_causal_and_resets_at_episode_start(self):
        u = np.linspace(8, 10, 129)
        before = trend_feature(u)
        modified = u.copy()
        modified[50:] = 100
        np.testing.assert_array_equal(before[:50], trend_feature(modified)[:50])
        self.assertEqual(before[0], 0.)
        self.assertAlmostEqual(before[2], u[2]-u[0])
        self.assertAlmostEqual(before[70], u[70]-u[66])

    def test_decomposition_uses_population_variance_without_cancelling_cases(self):
        e = np.tile([-4., 2.], 64)
        parts = error_parts(e)
        self.assertEqual(parts['mean_error_w'], -1.)
        self.assertEqual(parts['variance_w2'], 9.)
        self.assertEqual(parts['bias_squared_w2'], 1.)
        self.assertAlmostEqual(parts['rmse_w']**2, 10.)
        self.assertAlmostEqual(parts['decomposition_residual_w2'], 0.)
        self.assertEqual(error_parts(-e)['bias_squared_w2'], 1.)
        with self.assertRaises(ValueError):
            error_parts(e[:-1])

    def test_validation_does_not_change_forecast_fit(self):
        rng = np.random.default_rng(42)
        winds = []
        for split in ('train', 'validation'):
            for family in ('stationary', 'ramp', 'gust'):
                u = 9+np.cumsum(rng.normal(0, .1, 129))
                winds.append((dict(split=split, family=family), SimpleNamespace(values=np.column_stack((u, u*0, u*0+.04)))))
        _, before = forecast_check(winds)
        for case, trace in winds:
            if case['split'] == 'validation':
                trace.values[:, 0] *= 10
        _, after = forecast_check(winds)
        self.assertEqual(before, after)

    def test_capture_preserves_pi_trajectory_and_decision_response_alignment(self):
        from optimization_control.maddpg_wind_farm.workflow import build_env, load_config, DEFAULT_CONFIG
        from optimization_control.maddpg_wind_farm.controllers import PitchController
        cfg = load_config(DEFAULT_CONFIG)
        cfg['environment'].update(control_mask=[0, 1, 0], action_low=[-.25, 0, .6], action_high=[.25, .22, 1.267],
                                  reference_schedule=dict(yaw_offset_rad=0., speed_per_wind_rad_m=1.267/11.4))
        u = 9+.4*np.sin(np.arange(129)/8)
        values = np.column_stack((u, u*0, u*0+.04))
        case = dict(id='unit', split='validation', family='ramp', target_w=3e6, initial_pitch_rad=.025)
        a, b = build_env(cfg), build_env(cfg)
        a._baseline_config = cfg['baselines']
        metric, rows = rollout(a, case, SimpleNamespace(values=values), mode='pi')
        b.initial = np.array(cfg['environment']['initial_operating_point'])
        b.initial[1] = .025
        obs, _ = b.reset(seed=42, options=dict(wind_trajectory=values, target_w=3e6))
        controller = PitchController(b, cfg['baselines'], 'pi')
        for t in range(128):
            obs, _, _, _, info = b.step(controller.act(obs))
            self.assertEqual(rows[t]['error_w'], info['error_w'])
            self.assertAlmostEqual(rows[t]['decision_wind_m_s'], float(np.float32(u[t])))
            self.assertAlmostEqual(rows[t]['response_wind_m_s'], float(np.float32(u[t+1])))
            alpha = 1-np.exp(-1/cfg['environment']['time_constants_s'][1])
            for i in range(3):
                requested = alpha*(rows[t][f'pitch_command_{i}']-rows[t][f'pitch_before_{i}'])
                self.assertEqual(rows[t][f'pitch_rate_limited_{i}'], int(abs(requested)>cfg['environment']['rate_limits'][1]))
        self.assertEqual(metric['rmse_w'], error_parts([r['error_w'] for r in rows])['rmse_w'])


if __name__ == '__main__':
    unittest.main()
