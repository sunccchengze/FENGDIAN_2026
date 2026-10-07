"""Tests for normalized-to-physical action mapping."""

import unittest

import numpy as np

from optimization_control.utils.action_mapper import (
    ActionChannelConfig,
    ActionMapper,
    ActionMapperConfig,
    ParameterSource,
)


class ActionMapperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = ParameterSource("test", "unit-test-only bounds")
        self.mapper = ActionMapper(
            ActionMapperConfig(
                turbine_count=2,
                channels=(
                    ActionChannelConfig(
                        "yaw_misalignment_reference_rad",
                        [-0.5, -0.4],
                        [0.5, 0.6],
                        "rad",
                        self.source,
                    ),
                    ActionChannelConfig(
                        "collective_pitch_reference_rad",
                        0.0,
                        0.4,
                        "rad",
                        self.source,
                    ),
                    ActionChannelConfig(
                        "rotor_speed_reference_rad_s",
                        0.2,
                        2.0,
                        "rad/s",
                        self.source,
                    ),
                ),
            )
        )

    def test_maps_batch_and_reports_normalized_saturation(self) -> None:
        action = np.array(
            [[[-1.0, 0.0, 1.0], [1.0, -1.0, 2.0]]], dtype=np.float64
        )
        result = self.mapper.map(action)

        np.testing.assert_allclose(
            result.commanded_control["yaw_misalignment_reference_rad"],
            [[-0.5, 0.6]],
        )
        np.testing.assert_allclose(
            result.commanded_control["collective_pitch_reference_rad"],
            [[0.2, 0.0]],
        )
        np.testing.assert_allclose(
            result.commanded_control["rotor_speed_reference_rad_s"],
            [[2.0, 2.0]],
        )
        self.assertEqual(result.action_saturation_mask.shape, (1, 2, 3))
        self.assertTrue(result.action_saturation_mask[0, 1, 2])
        self.assertEqual(int(result.action_saturation_mask.sum()), 1)
        self.assertEqual(result.clipped_action_normalized[0, 1, 2], 1.0)

    def test_supports_unbatched_multi_turbine_action(self) -> None:
        result = self.mapper.map(np.zeros((2, 3), dtype=np.float32))
        self.assertEqual(
            result.commanded_control["collective_pitch_reference_rad"].shape,
            (2,),
        )
        np.testing.assert_allclose(
            result.commanded_control["rotor_speed_reference_rad_s"], [1.1, 1.1]
        )

    def test_physical_inverse_builds_true_hold_action_and_round_trips(self) -> None:
        current_reference = {
            "yaw_misalignment_reference_rad": np.array([0.0, 0.1]),
            "collective_pitch_reference_rad": np.array([0.0, 0.2]),
            "rotor_speed_reference_rad_s": np.array([1.0, 1.1]),
        }
        inverse = self.mapper.normalize_physical(current_reference)
        self.assertFalse(np.any(inverse.physical_saturation_mask))
        round_trip = self.mapper.map(inverse.normalized_action)
        for name, expected in current_reference.items():
            np.testing.assert_allclose(round_trip.commanded_control[name], expected)

    def test_physical_inverse_clips_and_reports_out_of_bounds(self) -> None:
        physical = {
            "yaw_misalignment_reference_rad": np.array([-1.0, 0.1]),
            "collective_pitch_reference_rad": np.array([0.0, 0.2]),
            "rotor_speed_reference_rad_s": np.array([1.0, 3.0]),
        }
        result = self.mapper.normalize_physical(physical)
        self.assertEqual(int(result.physical_saturation_mask.sum()), 2)
        np.testing.assert_allclose(
            result.normalized_action[0], [-1.0, -1.0, -1.0 / 9.0]
        )
        np.testing.assert_allclose(result.normalized_action[1, 2], 1.0)

    def test_physical_inverse_rejects_keys_shape_and_nonfinite_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "keys must be"):
            self.mapper.normalize_physical({})
        physical = {
            "yaw_misalignment_reference_rad": np.array([0.0, 0.0]),
            "collective_pitch_reference_rad": np.array([0.0]),
            "rotor_speed_reference_rad_s": np.array([1.0, 1.0]),
        }
        with self.assertRaisesRegex(ValueError, "turbine dimension"):
            self.mapper.normalize_physical(physical)
        physical["collective_pitch_reference_rad"] = np.array([0.0, np.inf])
        with self.assertRaisesRegex(ValueError, "NaN or Inf"):
            self.mapper.normalize_physical(physical)

    def test_rejects_invalid_shape_and_nonfinite_action(self) -> None:
        with self.assertRaisesRegex(ValueError, "must end with shape"):
            self.mapper.map(np.zeros((2, 2)))
        action = np.zeros((2, 3))
        action[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "NaN or Inf"):
            self.mapper.map(action)

    def test_requires_explicit_parameter_source(self) -> None:
        with self.assertRaises(ValueError):
            ParameterSource("", "missing kind")
        with self.assertRaises(ValueError):
            ParameterSource("assumption", "")


if __name__ == "__main__":
    unittest.main()
