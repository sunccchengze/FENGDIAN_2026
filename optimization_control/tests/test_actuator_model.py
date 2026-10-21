"""Tests for the independent multi-channel actuator model."""

import unittest
from dataclasses import replace

import numpy as np

from optimization_control.utils.action_mapper import ParameterSource
from optimization_control.utils.actuator_model import (
    ActuatorChannelConfig,
    ActuatorModel,
    ActuatorModelConfig,
)


class ActuatorModelTest(unittest.TestCase):
    def setUp(self) -> None:
        source = ParameterSource("test", "unit-test-only actuator values")
        self.channels = (
            ActuatorChannelConfig(
                "yaw_misalignment_reference_rad",
                "applied_yaw_misalignment_rad",
                -1.0,
                1.0,
                0.1,
                1.0,
                2,
                1.0,
                "rad",
                source,
            ),
            ActuatorChannelConfig(
                "collective_pitch_reference_rad",
                "applied_collective_pitch_rad",
                0.0,
                1.0,
                0.2,
                1.0,
                1,
                0.0,
                "rad",
                source,
            ),
            ActuatorChannelConfig(
                "rotor_speed_reference_rad_s",
                "applied_rotor_speed_operating_point_rad_s",
                0.5,
                2.0,
                0.5,
                2.0,
                1,
                0.0,
                "rad/s",
                source,
            ),
        )
        self.model = ActuatorModel(
            ActuatorModelConfig(2, 1.0, source, self.channels)
        )
        self.initial = {
            "applied_yaw_misalignment_rad": np.zeros(2),
            "applied_collective_pitch_rad": np.zeros(2),
            "applied_rotor_speed_operating_point_rad_s": np.ones(2),
        }

    @staticmethod
    def _commands() -> dict[str, np.ndarray]:
        return {
            "yaw_misalignment_reference_rad": np.array([1.0, -1.0]),
            "collective_pitch_reference_rad": np.array([1.0, 2.0]),
            "rotor_speed_reference_rad_s": np.array([2.0, 0.5]),
        }

    def test_three_channels_apply_delay_rate_lag_bounds_and_hold(self) -> None:
        self.model.reset(self.initial)
        first = self.model.step(self._commands())

        # One-step yaw delay exposes the reset value on the first step.
        np.testing.assert_allclose(
            first.effective_reference["yaw_misalignment_reference_rad"], [0.0, 0.0]
        )
        np.testing.assert_allclose(first.applied_control["applied_yaw_misalignment_rad"], 0.0)

        # Pitch first-order request is clipped by 0.2 rad/s; turbine 2's
        # out-of-range command is separately reported as position saturation.
        np.testing.assert_allclose(
            first.applied_control["applied_collective_pitch_rad"], [0.2, 0.2]
        )
        np.testing.assert_array_equal(
            first.position_saturation_mask["collective_pitch_reference_rad"],
            [False, True],
        )
        np.testing.assert_array_equal(
            first.rate_saturation_mask["collective_pitch_reference_rad"],
            [True, True],
        )

        alpha = 1.0 - np.exp(-0.5)
        np.testing.assert_allclose(
            first.applied_control["applied_rotor_speed_operating_point_rad_s"],
            [1.0 + alpha, 1.0 - 0.5 * alpha],
        )
        self.assertEqual(first.action_saturation_mask.shape, (2, 3))

        second = self.model.step(self._commands())
        np.testing.assert_array_equal(
            second.hold_mask["yaw_misalignment_reference_rad"], [True, True]
        )
        np.testing.assert_allclose(second.applied_control["applied_yaw_misalignment_rad"], 0.0)

        third = self.model.step(self._commands())
        # A new yaw reference is sampled here, while the physical actuator
        # advances by exactly one control interval.
        np.testing.assert_allclose(
            third.applied_control["applied_yaw_misalignment_rad"], [0.1, -0.1]
        )
        np.testing.assert_array_equal(
            third.rate_saturation_mask["yaw_misalignment_reference_rad"], [True, True]
        )

        fourth = self.model.step(self._commands())
        # Between command updates the sampled reference is held, but the
        # physical actuator continues evolving every control interval.
        np.testing.assert_array_equal(
            fourth.hold_mask["yaw_misalignment_reference_rad"], [True, True]
        )
        np.testing.assert_allclose(
            fourth.applied_control["applied_yaw_misalignment_rad"], [0.2, -0.2]
        )

    def test_reset_recreates_delay_queues_without_episode_leakage(self) -> None:
        self.model.reset(self.initial)
        for _ in range(3):
            self.model.step(self._commands())

        reset_state = self.model.reset(self.initial)
        np.testing.assert_allclose(reset_state["applied_yaw_misalignment_rad"], 0.0)
        neutral = {
            "yaw_misalignment_reference_rad": np.zeros(2),
            "collective_pitch_reference_rad": np.zeros(2),
            "rotor_speed_reference_rad_s": np.ones(2),
        }
        result = self.model.step(neutral)
        np.testing.assert_allclose(
            result.effective_reference["yaw_misalignment_reference_rad"], 0.0
        )
        np.testing.assert_allclose(result.applied_control["applied_yaw_misalignment_rad"], 0.0)
        np.testing.assert_allclose(result.applied_control["applied_collective_pitch_rad"], 0.0)
        np.testing.assert_allclose(
            result.applied_control["applied_rotor_speed_operating_point_rad_s"], 1.0
        )

    def test_requires_reset_and_integer_delay_steps(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "reset"):
            self.model.step(self._commands())
        invalid_channels = (replace(self.channels[0], command_delay_s=0.5),) + self.channels[1:]
        with self.assertRaisesRegex(ValueError, "integer multiple"):
            ActuatorModel(
                ActuatorModelConfig(
                    2,
                    1.0,
                    ParameterSource("test", "test dt"),
                    invalid_channels,
                )
            )


if __name__ == "__main__":
    unittest.main()
