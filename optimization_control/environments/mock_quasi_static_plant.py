"""Deterministic mock plant for interface and control-loop integration tests.

This model is intentionally not a calibrated wind-turbine surrogate.  Its
formula only provides smooth, bounded sensitivities to wind, yaw, pitch and
rotor-speed operating point so the optimizer can be developed before a real
PINN is delivered.  Results from this class are not physical evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .plant_model import (
    AppliedOperatingPoint,
    DisturbanceBatch,
    FloatArray,
    SteadyPlantOutput,
)


@dataclass(frozen=True)
class MockPlantParameters:
    """Assumed constants for a software-integration-only response surface."""

    cut_in_wind_speed_m_s: float = 3.0
    rated_wind_speed_m_s: float = 11.4
    cut_out_wind_speed_m_s: float = 25.0
    rated_rotor_speed_rad_s: float = 1.267
    yaw_power_exponent: float = 1.88
    pitch_decay_scale_rad: float = float(np.deg2rad(12.0))
    rotor_speed_width_rad_s: float = 0.45
    downstream_wake_loss_fraction: float = 0.06
    valid_turbulence_intensity_max: float = 0.30

    def __post_init__(self) -> None:
        if not (
            0.0 <= self.cut_in_wind_speed_m_s
            < self.rated_wind_speed_m_s
            < self.cut_out_wind_speed_m_s
        ):
            raise ValueError("mock wind-speed limits must be strictly ordered")
        positive = (
            self.rated_rotor_speed_rad_s,
            self.yaw_power_exponent,
            self.pitch_decay_scale_rad,
            self.rotor_speed_width_rad_s,
        )
        if any(value <= 0.0 for value in positive):
            raise ValueError("mock response parameters must be positive")
        if not 0.0 <= self.downstream_wake_loss_fraction < 1.0:
            raise ValueError("downstream_wake_loss_fraction must be in [0,1)")


class MockQuasiStaticPlant:
    """Smooth batched stand-in that implements the exact ``PlantModel`` API."""

    model_kind = "mock_quasi_static_integration_only"

    def __init__(
        self,
        turbine_ids: tuple[str, ...] = ("T01",),
        rated_power_w: float | NDArray[np.floating] = 5_000_000.0,
        parameters: MockPlantParameters | None = None,
    ) -> None:
        ids = tuple(str(item) for item in turbine_ids)
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("turbine_ids must be non-empty, unique and ordered")
        rated = np.asarray(rated_power_w, dtype=np.float32)
        if rated.ndim == 0:
            rated = np.full(len(ids), float(rated), dtype=np.float32)
        if rated.shape != (len(ids),) or np.any(rated <= 0.0):
            raise ValueError("rated_power_w must be positive with shape [N]")
        self._turbine_ids = ids
        self._rated_power_w = rated.copy()
        self.parameters = parameters or MockPlantParameters()

    @property
    def turbine_ids(self) -> tuple[str, ...]:
        return self._turbine_ids

    @property
    def rated_power_w(self) -> FloatArray:
        return self._rated_power_w.copy()

    def predict_steady(
        self,
        disturbance: DisturbanceBatch,
        applied_operating_point: AppliedOperatingPoint,
    ) -> SteadyPlantOutput:
        if applied_operating_point.turbine_ids != self.turbine_ids:
            raise ValueError(
                "applied_operating_point.turbine_ids must exactly match plant order"
            )
        if disturbance.batch_size != applied_operating_point.batch_size:
            raise ValueError("disturbance and operating point batch sizes differ")

        p = self.parameters
        batch_size = disturbance.batch_size
        turbine_count = len(self.turbine_ids)
        wind = np.broadcast_to(
            disturbance.ambient_wind_speed_m_s, (batch_size, turbine_count)
        ).astype(np.float32, copy=True)

        denominator = p.rated_wind_speed_m_s**3 - p.cut_in_wind_speed_m_s**3
        wind_fraction = (
            wind**3 - np.float32(p.cut_in_wind_speed_m_s**3)
        ) / np.float32(denominator)
        wind_fraction = np.clip(wind_fraction, 0.0, 1.0)
        generating = (wind >= p.cut_in_wind_speed_m_s) & (
            wind <= p.cut_out_wind_speed_m_s
        )
        wind_fraction = np.where(generating, wind_fraction, 0.0)

        yaw = applied_operating_point.applied_yaw_misalignment_rad
        yaw_factor = np.cos(np.clip(yaw, -np.pi / 2.0, np.pi / 2.0))
        yaw_factor = np.power(np.maximum(yaw_factor, 0.0), p.yaw_power_exponent)

        pitch = applied_operating_point.applied_collective_pitch_rad
        pitch_factor = np.exp(-np.maximum(pitch, 0.0) / p.pitch_decay_scale_rad)

        speed = applied_operating_point.applied_rotor_speed_operating_point_rad_s
        speed_optimum = np.clip(
            p.rated_rotor_speed_rad_s
            * wind
            / np.float32(p.rated_wind_speed_m_s),
            0.25 * p.rated_rotor_speed_rad_s,
            p.rated_rotor_speed_rad_s,
        )
        speed_factor = np.exp(
            -0.5 * ((speed - speed_optimum) / p.rotor_speed_width_rad_s) ** 2
        )

        wake_factor = 1.0 - p.downstream_wake_loss_fraction * np.arange(
            turbine_count, dtype=np.float32
        )
        wake_factor = np.clip(wake_factor, 0.5, 1.0)[None, :]
        effective_wind = wind * np.cbrt(wake_factor).astype(np.float32)
        turbine_power = (
            self._rated_power_w[None, :]
            * wind_fraction
            * wake_factor
            * yaw_factor
            * pitch_factor
            * speed_factor
        )
        turbine_power = np.clip(
            turbine_power, 0.0, self._rated_power_w[None, :]
        ).astype(np.float32)
        farm_power = turbine_power.sum(axis=1, keepdims=True, dtype=np.float32)

        valid_wind = (disturbance.ambient_wind_speed_m_s >= p.cut_in_wind_speed_m_s) & (
            disturbance.ambient_wind_speed_m_s <= p.cut_out_wind_speed_m_s
        )
        valid_turbulence = (
            disturbance.turbulence_intensity >= 0.0
        ) & (
            disturbance.turbulence_intensity <= p.valid_turbulence_intensity_max
        )
        valid_yaw = np.all(np.abs(yaw) <= np.deg2rad(45.0), axis=1, keepdims=True)
        valid_pitch = np.all(
            (pitch >= 0.0) & (pitch <= np.deg2rad(30.0)), axis=1, keepdims=True
        )
        valid_speed = np.all(
            (speed >= 0.1) & (speed <= 1.35), axis=1, keepdims=True
        )
        in_domain = valid_wind & valid_turbulence & valid_yaw & valid_pitch & valid_speed

        wind_ood = np.maximum(p.cut_in_wind_speed_m_s - wind, 0.0) / max(
            p.cut_in_wind_speed_m_s, 1e-6
        ) + np.maximum(wind - p.cut_out_wind_speed_m_s, 0.0) / max(
            p.cut_out_wind_speed_m_s, 1e-6
        )
        yaw_ood = np.maximum(np.abs(yaw) - np.deg2rad(45.0), 0.0) / np.deg2rad(45.0)
        pitch_ood = np.maximum(pitch - np.deg2rad(30.0), 0.0) / np.deg2rad(30.0)
        speed_ood = np.maximum(0.1 - speed, 0.0) / 0.1 + np.maximum(
            speed - 1.35, 0.0
        ) / 1.35
        ood_score = np.maximum.reduce(
            [
                wind_ood.max(axis=1, keepdims=True),
                yaw_ood.max(axis=1, keepdims=True),
                pitch_ood.max(axis=1, keepdims=True),
                speed_ood.max(axis=1, keepdims=True),
            ]
        ).astype(np.float32)

        return SteadyPlantOutput(
            turbine_ids=self.turbine_ids,
            floris_turbine_power_w=turbine_power,
            floris_farm_power_sum_w=farm_power,
            effective_wind_speed_m_s=effective_wind,
            in_domain=in_domain.astype(np.bool_),
            ood_score=ood_score,
            model_kind=self.model_kind,
        )
