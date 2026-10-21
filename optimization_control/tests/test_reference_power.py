"""Tests for causal headroom/ramp-limited reference generation."""

import unittest

import numpy as np

from optimization_control.utils.action_mapper import ParameterSource
from optimization_control.utils.reference_power import (
    ReferencePowerConfig,
    ReferencePowerGenerator,
)


class ReferencePowerGeneratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = ReferencePowerGenerator(
            ReferencePowerConfig(
                control_interval_s=1.0,
                headroom_fraction=0.1,
                low_pass_time_constant_s=1.0,
                ramp_up_limit_w_s=100.0,
                ramp_down_limit_w_s=200.0,
                source=ParameterSource("test", "unit-test-only reference values"),
            )
        )

    def test_headroom_filter_and_asymmetric_ramp_are_causal(self) -> None:
        initial = self.generator.reset(np.array([1000.0]))
        np.testing.assert_allclose(initial.headroom_limited_power_w, [900.0])
        np.testing.assert_allclose(initial.reference_power_w, [900.0])

        result = self.generator.step(np.array([2000.0]))
        expected_filtered = 900.0 + (1800.0 - 900.0) * (1.0 - np.exp(-1.0))
        np.testing.assert_allclose(result.filtered_power_w, [expected_filtered])
        np.testing.assert_allclose(result.reference_power_w, [1000.0])
        np.testing.assert_array_equal(result.ramp_up_limited_mask, [True])
        np.testing.assert_array_equal(result.ramp_down_limited_mask, [False])

        # The result above depends only on the past state and current 2000 W
        # input; a later collapse cannot retroactively change it.
        collapsed = self.generator.step(np.array([0.0]))
        np.testing.assert_allclose(collapsed.reference_power_w, [0.0])
        np.testing.assert_array_equal(collapsed.availability_clip_mask, [True])

    def test_reset_clears_filter_and_ramp_memory(self) -> None:
        self.generator.reset(np.array([1000.0, 2000.0]))
        self.generator.step(np.array([3000.0, 4000.0]))
        reset = self.generator.reset(np.array([500.0, 600.0]))
        np.testing.assert_allclose(reset.filtered_power_w, [450.0, 540.0])
        np.testing.assert_allclose(reset.reference_power_w, [450.0, 540.0])

    def test_rejects_invalid_available_power_and_requires_reset(self) -> None:
        fresh = ReferencePowerGenerator(self.generator.config)
        with self.assertRaisesRegex(RuntimeError, "reset"):
            fresh.step(100.0)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            self.generator.reset(-1.0)
        with self.assertRaisesRegex(ValueError, "shape"):
            self.generator.reset(np.array([100.0]), initial_reference_power_w=np.array([1.0, 2.0]))


if __name__ == "__main__":
    unittest.main()
