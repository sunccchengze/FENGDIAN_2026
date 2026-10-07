"""Curriculum gate safety and equal-permission replay behavior."""
import unittest
from unittest.mock import Mock, patch
import numpy as np

from optimization_control.maddpg_wind_farm.fixed_curriculum import read_protocol, DEFAULT, gate_rows, evaluate, attach_settings, next_segment
from optimization_control.maddpg_wind_farm.workflow import build_env, load_config, DEFAULT_CONFIG


class FixedCurriculumTests(unittest.TestCase):
    def setUp(self):
        self.p = read_protocol(DEFAULT)

    def test_test_metrics_cannot_advance_stage(self):
        with self.assertRaisesRegex(ValueError, "validation only"):
            gate_rows([dict(split="test", rmse_w=1, tail_rmse_w=1, target_w=3e6, final_power_w=3e6)], 1e6, self.p["gate"], multi=False)

    def test_good_average_cannot_hide_failed_target_or_flat_response(self):
        rows = [dict(split="validation", rmse_w=100, tail_rmse_w=10, target_w=2.75e6, final_power_w=3.5e6),
                dict(split="validation", rmse_w=100, tail_rmse_w=10, target_w=4.25e6, final_power_w=3.5e6)]
        self.assertFalse(gate_rows(rows, 1e6, self.p["gate"], multi=True)["passed"])
        rows[0]["final_power_w"] = 2.75e6
        rows[1]["final_power_w"] = 4.25e6
        self.assertTrue(gate_rows(rows, 1e6, self.p["gate"], multi=True)["passed"])
        rows[1]["tail_rmse_w"] = 100001
        self.assertFalse(gate_rows(rows, 1e6, self.p["gate"], multi=True)["passed"])

    def test_frozen_protocol_disjoint_targets(self):
        train, val, test = [set(self.p[k]) for k in ("multi_training_targets_w", "validation_targets_w", "test_targets_w")]
        self.assertFalse(train & val or train & test or val & test)

    def test_independent_probes_keep_explicit_stage_and_fresh_test_targets(self):
        speed = read_protocol(DEFAULT.with_name("fixed_pitch_speed_probe.yaml"))
        full = read_protocol(DEFAULT.with_name("fixed_all_probe.yaml"))
        self.assertEqual(speed["stages"], ["multi_pitch_speed"])
        self.assertEqual(full["stages"], ["multi_all"])
        self.assertEqual(speed["test_targets_w"], full["test_targets_w"])
        self.assertFalse(set(speed["test_targets_w"]) & set(self.p["test_targets_w"]))

    def test_resume_segment_ignores_logs_and_does_not_reuse_existing_index(self):
        entries = [Mock(), Mock(), Mock()]
        for entry, name, directory in zip(entries, ["segment_000", "segment_002", "segment_003.log"], [True, True, False]):
            entry.name = name
            entry.is_dir.return_value = directory
        with patch("pathlib.Path.glob", return_value=entries):
            self.assertEqual(next_segment("unused"), 3)

    def test_baseline_restores_initial_and_keeps_disabled_channels_fixed(self):
        cfg = load_config(DEFAULT_CONFIG)
        cfg["environment"].update(horizon=32, control_mask=[0, 1, 0], initial_operating_point=[0., .04, .9],
            wind_base_m_s=9., wind_direction_rad=0., turbulence_intensity=.1, wind_amplitude_m_s=0., wind_noise_std_m_s=0.)
        cfg["baselines"].update(three_channel=True, speed_per_wind_rad_m=.111, pitch_bias_rad=.04)
        env = attach_settings(build_env(cfg), cfg)
        before = env.initial.copy()
        a, trace = evaluate(env, None, [3e6], split="test", pitches=[.025, .055], mode="pi", capture=True)
        b, _ = evaluate(env, None, [3e6], split="test", pitches=[.025, .055], mode="pi")
        self.assertEqual(a, b)
        np.testing.assert_array_equal(env.initial, before)
        self.assertEqual(len(trace), 64)
        for row in trace:
            for i in (1, 2, 3):
                self.assertAlmostEqual(row[f"yaw_{i}"], 0.)
                self.assertAlmostEqual(row[f"speed_{i}"], .9, places=6)


if __name__ == "__main__":
    unittest.main()
