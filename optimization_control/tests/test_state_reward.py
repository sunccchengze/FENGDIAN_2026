"""Tests for state assembly, observations and decomposed rewards."""

import unittest
from dataclasses import dataclass

import numpy as np

from optimization_control.utils.action_mapper import ParameterSource
from optimization_control.utils.reward import RewardCalculator, RewardConfig
from optimization_control.utils.state_pipeline import (
    ObservationBuilder,
    ObservationConfig,
    ObservationFeatureConfig,
    StateAssembler,
    StateAssemblerConfig,
)


@dataclass(frozen=True)
class _Disturbance:
    ambient_wind_speed_m_s: np.ndarray
    ambient_wind_direction_rad: np.ndarray
    turbulence_intensity: np.ndarray


@dataclass(frozen=True)
class _Applied:
    applied_yaw_misalignment_rad: np.ndarray
    applied_collective_pitch_rad: np.ndarray
    applied_rotor_speed_operating_point_rad_s: np.ndarray


@dataclass(frozen=True)
class _PlantOutput:
    floris_turbine_power_w: np.ndarray
    floris_farm_power_sum_w: np.ndarray
    effective_wind_speed_m_s: np.ndarray
    in_domain: np.ndarray
    ood_score: np.ndarray


class StateAndObservationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = ParameterSource("test", "unit-test-only state values")
        self.assembler = StateAssembler(
            StateAssemblerConfig(
                turbine_count=2,
                control_interval_s=2.0,
                turbine_power_field="floris_turbine_power_w",
                source=self.source,
            )
        )
        self.disturbance = _Disturbance(
            ambient_wind_speed_m_s=np.array([[8.0]]),
            ambient_wind_direction_rad=np.array([[0.0]]),
            turbulence_intensity=np.array([[0.08]]),
        )
        self.applied = _Applied(
            applied_yaw_misalignment_rad=np.array([[0.0, 0.1]]),
            applied_collective_pitch_rad=np.array([[0.01, 0.02]]),
            applied_rotor_speed_operating_point_rad_s=np.array([[1.0, 1.1]]),
        )
        self.output = _PlantOutput(
            floris_turbine_power_w=np.array([[100.0, 200.0]]),
            floris_farm_power_sum_w=np.array([[300.0]]),
            effective_wind_speed_m_s=np.array([[7.0, 6.5]]),
            in_domain=np.array([[True]]),
            ood_score=np.array([[0.0]]),
        )

    def test_assembler_accepts_dataclasses_and_is_authoritative_for_farm_power(self) -> None:
        state = self.assembler.assemble(
            disturbance=self.disturbance,
            applied_control=self.applied,
            plant_output=self.output,
            action_saturation_mask=np.zeros((1, 2, 3), dtype=bool),
        )
        self.assertTrue(state.batched)
        np.testing.assert_allclose(state.farm["farm_active_power_w"], [[300.0]])
        np.testing.assert_allclose(
            state.farm["interval_mean_farm_active_power_w"], [[300.0]]
        )
        np.testing.assert_allclose(state.farm["interval_energy_j"], [[600.0]])
        np.testing.assert_allclose(
            state.turbine["applied_rotor_speed_operating_point_rad_s"],
            [[1.0, 1.1]],
        )
        self.assertIn("in_domain", state.diagnostics)

    def test_observation_order_and_normalization_are_explicit(self) -> None:
        state = self.assembler.assemble(
            disturbance=self.disturbance,
            applied_control=self.applied,
            plant_output=self.output,
        )
        builder = ObservationBuilder(
            ObservationConfig(
                features=(
                    ObservationFeatureConfig(
                        "derived.power_tracking_error_w", 0.0, 100.0, self.source
                    ),
                    ObservationFeatureConfig(
                        "turbine.applied_collective_pitch_rad", 0.0, 0.1, self.source
                    ),
                    ObservationFeatureConfig(
                        "previous_action_normalized", 0.0, 1.0, self.source
                    ),
                )
            )
        )
        observation = builder.build(
            state,
            power_reference_w=np.array([[350.0]]),
            previous_action_normalized=np.zeros((1, 2, 3)),
        )
        self.assertEqual(observation.shape, (1, 9))
        np.testing.assert_allclose(observation[0, :3], [0.5, 0.1, 0.2])

    def test_rejects_inconsistent_plant_farm_sum(self) -> None:
        invalid = _PlantOutput(
            self.output.floris_turbine_power_w,
            np.array([[999.0]]),
            self.output.effective_wind_speed_m_s,
            self.output.in_domain,
            self.output.ood_score,
        )
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            self.assembler.assemble(
                disturbance=self.disturbance,
                applied_control=self.applied,
                plant_output=invalid,
            )


class RewardCalculatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.calculator = RewardCalculator(
            RewardConfig(
                tracking_weight=2.0,
                ramp_weight=3.0,
                action_rate_weight=4.0,
                load_weight=5.0,
                constraint_weight=6.0,
                ood_weight=7.0,
                energy_weight=8.0,
                tracking_error_scale_w=100.0,
                ramp_violation_scale_w_s=50.0,
                energy_scale_j=1000.0,
                source=ParameterSource("test", "unit-test-only reward values"),
            )
        )

    def test_reward_components_are_dimensionless_signed_and_auditable(self) -> None:
        action = np.array([[0.5, 0.0], [0.0, 0.0]])
        result = self.calculator.calculate(
            farm_power_w=np.array([300.0]),
            power_reference_w=np.array([400.0]),
            action_normalized=action,
            previous_action_normalized=np.zeros_like(action),
            farm_power_ramp_w_s=np.array([150.0]),
            ramp_limit_w_s=np.array([100.0]),
            load_penalty_normalized=np.array([0.5, 0.5]),
            constraint_violation=np.array([[1.0, 0.0], [1.0, 0.0]]),
            ood_mask=np.array([1.0]),
            interval_energy_j=np.array([1000.0]),
        )
        self.assertAlmostEqual(result.components["tracking"], -2.0)
        self.assertAlmostEqual(result.components["action_rate"], -0.25)
        self.assertAlmostEqual(result.components["ramp"], -3.0)
        self.assertAlmostEqual(result.components["load"], -1.25)
        self.assertAlmostEqual(result.components["constraint"], -3.0)
        self.assertAlmostEqual(result.components["ood"], -7.0)
        self.assertAlmostEqual(result.components["energy"], 8.0)
        self.assertAlmostEqual(result.total, -8.5)

    def test_nonzero_weight_requires_corresponding_signal(self) -> None:
        action = np.zeros((2, 2))
        with self.assertRaisesRegex(ValueError, "farm_power_ramp_w_s"):
            self.calculator.calculate(
                farm_power_w=np.array([1.0]),
                power_reference_w=np.array([1.0]),
                action_normalized=action,
                previous_action_normalized=action,
            )

    def test_shape_contract_rejects_accidental_broadcasting(self) -> None:
        action = np.zeros((2, 2))
        common = dict(
            farm_power_w=np.array([1.0]),
            power_reference_w=np.array([1.0]),
            action_normalized=action,
            previous_action_normalized=action,
            farm_power_ramp_w_s=np.array([0.0]),
            ramp_limit_w_s=np.array([1.0]),
            load_penalty_normalized=np.zeros(2),
            constraint_violation=np.zeros_like(action),
            ood_mask=np.array([0.0]),
            interval_energy_j=np.array([1.0]),
        )
        for field, invalid in (
            ("farm_power_w", np.array([[1.0]])),
            ("load_penalty_normalized", np.zeros((1, 2))),
            ("constraint_violation", np.zeros(2)),
            ("ood_mask", np.zeros(2)),
        ):
            with self.subTest(field=field):
                values = dict(common)
                values[field] = invalid
                with self.assertRaisesRegex(ValueError, "must have shape"):
                    self.calculator.calculate(**values)

    def test_batched_reward_returns_one_value_per_batch_item(self) -> None:
        action = np.zeros((3, 2, 2))
        result = self.calculator.calculate(
            farm_power_w=np.ones((3, 1)),
            power_reference_w=np.ones((3, 1)),
            action_normalized=action,
            previous_action_normalized=action,
            farm_power_ramp_w_s=np.zeros((3, 1)),
            ramp_limit_w_s=np.ones((3, 1)),
            load_penalty_normalized=np.zeros((3, 2)),
            constraint_violation=np.zeros((3, 2, 2)),
            ood_mask=np.zeros((3, 1)),
            interval_energy_j=np.ones((3, 1)),
        )
        self.assertEqual(result.total.shape, (3,))


if __name__ == "__main__":
    unittest.main()
