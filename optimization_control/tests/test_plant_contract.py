"""Contract tests shared by the mock and future PINN plant adapters."""

from __future__ import annotations

import numpy as np
import unittest

from optimization_control.environments.mock_quasi_static_plant import (
    MockQuasiStaticPlant,
)
from optimization_control.environments.plant_model import (
    AppliedOperatingPoint,
    DisturbanceBatch,
    SteadyPlantOutput,
    PlantModel,
)


TURBINE_IDS = ("T03", "T01", "T02")
_CASE = unittest.TestCase()



def _inputs(batch_size: int = 4):
    wind = np.linspace(7.0, 10.0, batch_size, dtype=np.float32)[:, None]
    disturbance = DisturbanceBatch(
        ambient_wind_speed_m_s=wind,
        ambient_wind_direction_rad=np.linspace(
            0.0, np.pi / 3.0, batch_size, dtype=np.float32
        )[:, None],
        turbulence_intensity=np.full((batch_size, 1), 0.08, dtype=np.float32),
    )
    yaw = np.linspace(-0.10, 0.10, batch_size * 3, dtype=np.float32).reshape(
        batch_size, 3
    )
    operating_point = AppliedOperatingPoint(
        turbine_ids=TURBINE_IDS,
        applied_yaw_misalignment_rad=yaw,
        applied_collective_pitch_rad=np.full(
            (batch_size, 3), 0.03, dtype=np.float32
        ),
        applied_rotor_speed_operating_point_rad_s=np.full(
            (batch_size, 3), 1.0, dtype=np.float32
        ),
    )
    return disturbance, operating_point


def test_mock_implements_structured_plant_contract_and_preserves_id_order():
    plant = MockQuasiStaticPlant(
        turbine_ids=TURBINE_IDS,
        rated_power_w=np.array([4.0e6, 5.0e6, 6.0e6], dtype=np.float32),
    )
    assert isinstance(plant, PlantModel)
    disturbance, operating_point = _inputs(batch_size=4)

    output = plant.predict_steady(disturbance, operating_point)

    assert output.turbine_ids == TURBINE_IDS
    assert output.floris_turbine_power_w.shape == (4, 3)
    assert output.floris_farm_power_sum_w.shape == (4, 1)
    assert output.effective_wind_speed_m_s.shape == (4, 3)
    assert output.in_domain.shape == (4, 1)
    assert output.ood_score.shape == (4, 1)
    assert output.floris_turbine_power_w.dtype == np.float32
    assert output.in_domain.dtype == np.bool_
    np.testing.assert_allclose(
        output.floris_farm_power_sum_w[:, 0],
        output.floris_turbine_power_w.sum(axis=1),
        rtol=1e-6,
    )


def test_batched_prediction_matches_concatenated_single_predictions():
    plant = MockQuasiStaticPlant(turbine_ids=TURBINE_IDS)
    disturbance, operating_point = _inputs(batch_size=5)
    batched = plant.predict_steady(disturbance, operating_point)
    singles = [
        plant.predict_steady(disturbance.take(i), operating_point.take(i))
        for i in range(5)
    ]

    for field in (
        "floris_turbine_power_w",
        "floris_farm_power_sum_w",
        "effective_wind_speed_m_s",
        "in_domain",
        "ood_score",
    ):
        expected = np.concatenate([getattr(item, field) for item in singles], axis=0)
        np.testing.assert_allclose(getattr(batched, field), expected, rtol=1e-6, atol=1e-6)


def test_plant_rejects_reordered_or_unknown_turbine_ids():
    plant = MockQuasiStaticPlant(turbine_ids=TURBINE_IDS)
    disturbance, operating_point = _inputs(batch_size=1)
    reordered = AppliedOperatingPoint(
        turbine_ids=("T01", "T03", "T02"),
        applied_yaw_misalignment_rad=operating_point.applied_yaw_misalignment_rad,
        applied_collective_pitch_rad=operating_point.applied_collective_pitch_rad,
        applied_rotor_speed_operating_point_rad_s=(
            operating_point.applied_rotor_speed_operating_point_rad_s
        ),
    )

    with _CASE.assertRaisesRegex(ValueError, "exactly match plant order"):
        plant.predict_steady(disturbance, reordered)


def test_contract_objects_reject_wrong_shapes_and_nonfinite_values():
    with _CASE.assertRaisesRegex(ValueError, r"\[B,1\]"):
        DisturbanceBatch(
            ambient_wind_speed_m_s=np.ones((2, 2)),
            ambient_wind_direction_rad=np.zeros((2, 1)),
            turbulence_intensity=np.full((2, 1), 0.08),
        )
    with _CASE.assertRaisesRegex(ValueError, "NaN or Inf"):
        DisturbanceBatch(
            ambient_wind_speed_m_s=np.array([[np.nan]]),
            ambient_wind_direction_rad=np.zeros((1, 1)),
            turbulence_intensity=np.full((1, 1), 0.08),
        )

def test_steady_output_rejects_ambiguous_domain_and_reserved_extra_fields():
    common = dict(
        turbine_ids=("T01",),
        floris_turbine_power_w=np.array([[100.0]], dtype=np.float32),
        floris_farm_power_sum_w=np.array([[100.0]], dtype=np.float32),
        effective_wind_speed_m_s=np.array([[8.0]], dtype=np.float32),
        in_domain=np.array([[True]], dtype=bool),
        ood_score=np.array([[0.0]], dtype=np.float32),
        model_kind="contract_test",
    )

    with _CASE.assertRaisesRegex(TypeError, "boolean dtype"):
        SteadyPlantOutput(**{**common, "in_domain": np.array([[np.nan]])})
    with _CASE.assertRaisesRegex(ValueError, "non-negative"):
        SteadyPlantOutput(
            **{**common, "ood_score": np.array([[-0.1]], dtype=np.float32)}
        )
    with _CASE.assertRaisesRegex(ValueError, "non-empty"):
        SteadyPlantOutput(**{**common, "model_kind": "  "})
    with _CASE.assertRaisesRegex(ValueError, "reserved field"):
        SteadyPlantOutput(
            **{
                **common,
                "other_available_turbine_states": {
                    "applied_collective_pitch_rad": np.array(
                        [[0.1]], dtype=np.float32
                    )
                },
            }
        )


def test_steady_output_accepts_named_non_reserved_extra_state():
    output = SteadyPlantOutput(
        turbine_ids=("T01",),
        floris_turbine_power_w=np.array([[100.0]], dtype=np.float32),
        floris_farm_power_sum_w=np.array([[100.0]], dtype=np.float32),
        effective_wind_speed_m_s=np.array([[8.0]], dtype=np.float32),
        in_domain=np.array([[True]], dtype=bool),
        ood_score=np.array([[0.0]], dtype=np.float32),
        other_available_turbine_states={"tower_load_proxy": np.array([[0.2]])},
    )
    assert output.other_available_turbine_states["tower_load_proxy"].shape == (1, 1)

def load_tests(loader, tests, pattern):
    del loader, tests, pattern
    suite = unittest.TestSuite()
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            suite.addTest(unittest.FunctionTestCase(function))
    return suite
