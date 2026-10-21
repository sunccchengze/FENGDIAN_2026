"""Quasi-static plant boundary shared by the optimizer and PINN adapters.

The optimizer only depends on :class:`PlantModel`.  A future PINN adapter and
the integration-only mock therefore expose the same physical, batched schema.
The plant is deliberately stateless: actuator dynamics belong to
``ActuatorModel`` and pseudo-time belongs to the Gym environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float32]
BoolArray = NDArray[np.bool_]

PLANT_RESERVED_STATE_FIELDS = frozenset(
    {
        "turbine_ids",
        "model_kind",
        "floris_turbine_power_w",
        "floris_farm_power_sum_w",
        "effective_wind_speed_m_s",
        "in_domain",
        "ood_score",
        "other_available_turbine_states",
        "applied_yaw_misalignment_rad",
        "applied_collective_pitch_rad",
        "applied_rotor_speed_operating_point_rad_s",
        "yaw_misalignment_rad",
        "collective_pitch_rad",
        "rotor_speed_rad_s",
        "nacelle_heading_rad",
    }
)


def _float_matrix(value: object, name: str) -> FloatArray:
    array = np.asarray(value, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError(f"{name} must have shape [B, D], got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN or Inf")
    return array.copy()


def _bool_matrix(value: object, name: str) -> BoolArray:
    array = np.asarray(value)
    if array.ndim != 2:
        raise ValueError(f"{name} must have shape [B, D], got {array.shape}")
    if array.dtype != np.bool_:
        raise TypeError(f"{name} must use boolean dtype, got {array.dtype}")
    return array.astype(np.bool_, copy=True)


def _validate_turbine_ids(turbine_ids: tuple[str, ...]) -> tuple[str, ...]:
    ids = tuple(str(item) for item in turbine_ids)
    if not ids:
        raise ValueError("turbine_ids must not be empty")
    if len(set(ids)) != len(ids):
        raise ValueError("turbine_ids must be unique and ordered")
    return ids


@dataclass(frozen=True)
class DisturbanceBatch:
    """External wind conditions using the frozen ``[B,1]`` convention."""

    ambient_wind_speed_m_s: FloatArray
    ambient_wind_direction_rad: FloatArray
    turbulence_intensity: FloatArray

    def __post_init__(self) -> None:
        speed = _float_matrix(self.ambient_wind_speed_m_s, "ambient_wind_speed_m_s")
        direction = _float_matrix(
            self.ambient_wind_direction_rad, "ambient_wind_direction_rad"
        )
        turbulence = _float_matrix(self.turbulence_intensity, "turbulence_intensity")
        if speed.shape[1] != 1 or direction.shape[1] != 1 or turbulence.shape[1] != 1:
            raise ValueError("disturbance fields must all have shape [B,1]")
        if not (speed.shape == direction.shape == turbulence.shape):
            raise ValueError("disturbance fields must use the same batch size")
        if np.any(speed < 0.0):
            raise ValueError("ambient_wind_speed_m_s must be non-negative")
        if np.any(turbulence < 0.0):
            raise ValueError("turbulence_intensity must be non-negative")
        object.__setattr__(self, "ambient_wind_speed_m_s", speed)
        object.__setattr__(self, "ambient_wind_direction_rad", direction)
        object.__setattr__(self, "turbulence_intensity", turbulence)

    @property
    def batch_size(self) -> int:
        return int(self.ambient_wind_speed_m_s.shape[0])

    def take(self, index: int) -> "DisturbanceBatch":
        selection = slice(index, index + 1)
        return DisturbanceBatch(
            ambient_wind_speed_m_s=self.ambient_wind_speed_m_s[selection],
            ambient_wind_direction_rad=self.ambient_wind_direction_rad[selection],
            turbulence_intensity=self.turbulence_intensity[selection],
        )


@dataclass(frozen=True)
class AppliedOperatingPoint:
    """Actuator-owned operating point passed to a quasi-static plant."""

    turbine_ids: tuple[str, ...]
    applied_yaw_misalignment_rad: FloatArray
    applied_collective_pitch_rad: FloatArray
    applied_rotor_speed_operating_point_rad_s: FloatArray

    def __post_init__(self) -> None:
        ids = _validate_turbine_ids(self.turbine_ids)
        values = {
            "applied_yaw_misalignment_rad": _float_matrix(
                self.applied_yaw_misalignment_rad, "applied_yaw_misalignment_rad"
            ),
            "applied_collective_pitch_rad": _float_matrix(
                self.applied_collective_pitch_rad, "applied_collective_pitch_rad"
            ),
            "applied_rotor_speed_operating_point_rad_s": _float_matrix(
                self.applied_rotor_speed_operating_point_rad_s,
                "applied_rotor_speed_operating_point_rad_s",
            ),
        }
        shapes = {array.shape for array in values.values()}
        if len(shapes) != 1:
            raise ValueError("all operating-point fields must have the same shape")
        shape = next(iter(shapes))
        if shape[1] != len(ids):
            raise ValueError(
                f"operating-point turbine dimension {shape[1]} does not match "
                f"turbine_ids length {len(ids)}"
            )
        object.__setattr__(self, "turbine_ids", ids)
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def batch_size(self) -> int:
        return int(self.applied_yaw_misalignment_rad.shape[0])

    @property
    def turbine_count(self) -> int:
        return len(self.turbine_ids)

    def take(self, index: int) -> "AppliedOperatingPoint":
        selection = slice(index, index + 1)
        return AppliedOperatingPoint(
            turbine_ids=self.turbine_ids,
            applied_yaw_misalignment_rad=self.applied_yaw_misalignment_rad[selection],
            applied_collective_pitch_rad=self.applied_collective_pitch_rad[selection],
            applied_rotor_speed_operating_point_rad_s=(
                self.applied_rotor_speed_operating_point_rad_s[selection]
            ),
        )


@dataclass(frozen=True)
class SteadyPlantOutput:
    """Raw quasi-static plant result before optimizer-side state assembly."""

    turbine_ids: tuple[str, ...]
    floris_turbine_power_w: FloatArray
    floris_farm_power_sum_w: FloatArray
    effective_wind_speed_m_s: FloatArray
    in_domain: BoolArray
    ood_score: FloatArray
    other_available_turbine_states: Mapping[str, FloatArray] = field(default_factory=dict)
    model_kind: str = "quasi_static"

    def __post_init__(self) -> None:
        ids = _validate_turbine_ids(self.turbine_ids)
        turbine_power = _float_matrix(self.floris_turbine_power_w, "floris_turbine_power_w")
        farm_power = _float_matrix(self.floris_farm_power_sum_w, "floris_farm_power_sum_w")
        effective_wind = _float_matrix(
            self.effective_wind_speed_m_s, "effective_wind_speed_m_s"
        )
        in_domain = _bool_matrix(self.in_domain, "in_domain")
        ood_score = _float_matrix(self.ood_score, "ood_score")
        if not str(self.model_kind).strip():
            raise ValueError("model_kind must be a non-empty string")
        if np.any(ood_score < 0.0):
            raise ValueError("ood_score must be non-negative")
        expected_turbine_shape = (turbine_power.shape[0], len(ids))
        if turbine_power.shape != expected_turbine_shape:
            raise ValueError(
                "floris_turbine_power_w turbine dimension does not match turbine_ids"
            )
        if effective_wind.shape != expected_turbine_shape:
            raise ValueError("effective_wind_speed_m_s must have shape [B,N]")
        expected_farm_shape = (turbine_power.shape[0], 1)
        if farm_power.shape != expected_farm_shape:
            raise ValueError("floris_farm_power_sum_w must have shape [B,1]")
        if in_domain.shape != expected_farm_shape or ood_score.shape != expected_farm_shape:
            raise ValueError("in_domain and ood_score must have shape [B,1]")
        summed = turbine_power.sum(axis=1, keepdims=True, dtype=np.float32)
        if not np.allclose(farm_power, summed, rtol=1e-5, atol=1e-2):
            raise ValueError("farm power must equal the ordered turbine-power sum")
        if np.any(turbine_power < 0.0) or np.any(farm_power < 0.0):
            raise ValueError("normal-generation power must be non-negative")
        extra: dict[str, FloatArray] = {}
        for name, raw_value in self.other_available_turbine_states.items():
            name = str(name)
            if name in PLANT_RESERVED_STATE_FIELDS:
                raise ValueError(
                    f"other_available_turbine_states cannot override reserved field {name!r}"
                )
            value = _float_matrix(raw_value, name)
            if value.shape != expected_turbine_shape:
                raise ValueError(f"{name} must have shape [B,N]")
            extra[name] = value
        object.__setattr__(self, "turbine_ids", ids)
        object.__setattr__(self, "floris_turbine_power_w", turbine_power)
        object.__setattr__(self, "floris_farm_power_sum_w", farm_power)
        object.__setattr__(self, "effective_wind_speed_m_s", effective_wind)
        object.__setattr__(self, "in_domain", in_domain)
        object.__setattr__(self, "ood_score", ood_score)
        object.__setattr__(self, "other_available_turbine_states", extra)

    @property
    def batch_size(self) -> int:
        return int(self.floris_turbine_power_w.shape[0])

    def take(self, index: int) -> "SteadyPlantOutput":
        selection = slice(index, index + 1)
        return SteadyPlantOutput(
            turbine_ids=self.turbine_ids,
            floris_turbine_power_w=self.floris_turbine_power_w[selection],
            floris_farm_power_sum_w=self.floris_farm_power_sum_w[selection],
            effective_wind_speed_m_s=self.effective_wind_speed_m_s[selection],
            in_domain=self.in_domain[selection],
            ood_score=self.ood_score[selection],
            other_available_turbine_states={
                name: value[selection]
                for name, value in self.other_available_turbine_states.items()
            },
            model_kind=self.model_kind,
        )


@runtime_checkable
class PlantModel(Protocol):
    """Replaceable, stateless plant interface used by the Gym environment."""

    @property
    def turbine_ids(self) -> tuple[str, ...]: ...

    @property
    def rated_power_w(self) -> FloatArray: ...

    def predict_steady(
        self,
        disturbance: DisturbanceBatch,
        applied_operating_point: AppliedOperatingPoint,
    ) -> SteadyPlantOutput: ...


def validate_plant_compatibility(plant: PlantModel) -> None:
    """Fail early when a replacement plant violates fixed-layout metadata."""

    ids = _validate_turbine_ids(tuple(plant.turbine_ids))
    rated_power = np.asarray(plant.rated_power_w, dtype=np.float32)
    if rated_power.shape != (len(ids),):
        raise ValueError("plant.rated_power_w must have shape [N]")
    if not np.all(np.isfinite(rated_power)) or np.any(rated_power <= 0.0):
        raise ValueError("plant.rated_power_w must be finite and positive")
