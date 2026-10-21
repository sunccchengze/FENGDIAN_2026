"""Assemble plant/actuator state and build normalized PPO observations."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Dict, Mapping, Sequence

import numpy as np

from .action_mapper import ParameterSource


def _as_mapping(value: Any, object_name: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    try:
        attributes = vars(value)
    except TypeError as exc:
        raise TypeError(f"{object_name} must be a Mapping or dataclass-like object") from exc
    return {name: item for name, item in attributes.items() if not name.startswith("_")}


@dataclass(frozen=True)
class StateAssemblerConfig:
    """Fixed-layout and time semantics used while assembling state."""

    turbine_count: int
    control_interval_s: float
    turbine_power_field: str
    source: ParameterSource

    def __post_init__(self) -> None:
        if self.turbine_count <= 0:
            raise ValueError("turbine_count must be positive")
        if not np.isfinite(self.control_interval_s) or self.control_interval_s <= 0.0:
            raise ValueError("control_interval_s must be finite and positive")
        if not self.turbine_power_field.strip():
            raise ValueError("turbine_power_field must be non-empty")


@dataclass(frozen=True)
class AssembledState:
    """Complete structured state exposed to the optimization environment."""

    turbine: Mapping[str, np.ndarray]
    farm: Mapping[str, np.ndarray]
    disturbance: Mapping[str, np.ndarray]
    diagnostics: Mapping[str, np.ndarray]
    batched: bool


class StateAssembler:
    """Merge single-owner state fields without advancing any dynamics.

    ``applied_control`` comes from :class:`ActuatorModel`; plant power/effective
    wind comes from the plant adapter.  The assembler is the sole producer of
    farm power and interval energy.  Inputs can be mappings or dataclasses such
    as ``DisturbanceBatch``, ``AppliedOperatingPoint`` and
    ``SteadyPlantOutput`` from ``environments.plant_model``.
    """

    def __init__(self, config: StateAssemblerConfig):
        self.config = config

    @staticmethod
    def _array(value: Any, field_name: str) -> np.ndarray:
        array = np.asarray(value)
        if np.issubdtype(array.dtype, np.number) and not np.all(np.isfinite(array)):
            raise ValueError(f"{field_name} contains NaN or Inf")
        return array.copy()

    def assemble(
        self,
        *,
        disturbance: Any,
        applied_control: Any,
        plant_output: Any,
        action_saturation_mask: Any | None = None,
    ) -> AssembledState:
        """Assemble one unbatched ``[N]`` or batched ``[B,N]`` plant result."""

        disturbance_map = _as_mapping(disturbance, "disturbance")
        applied_map = _as_mapping(applied_control, "applied_control")
        plant_map = _as_mapping(plant_output, "plant_output")
        power_field = self.config.turbine_power_field
        if power_field not in plant_map:
            raise KeyError(f"plant_output is missing turbine power field {power_field!r}")

        turbine_power = np.asarray(plant_map[power_field], dtype=np.float64)
        if turbine_power.ndim < 1 or turbine_power.shape[-1] != self.config.turbine_count:
            raise ValueError(
                f"{power_field} must end with ({self.config.turbine_count},), "
                f"got {turbine_power.shape}"
            )
        if not np.all(np.isfinite(turbine_power)) or np.any(turbine_power < 0.0):
            raise ValueError(f"{power_field} must contain finite non-negative power")
        batched = turbine_power.ndim >= 2
        turbine_shape = turbine_power.shape

        turbine: Dict[str, np.ndarray] = {power_field: turbine_power.copy()}
        non_actuator_fields = {
            power_field,
            "floris_farm_power_sum_w",
            "farm_active_power_w",
            "in_domain",
            "ood_score",
            "violation_code",
            "turbine_active_mask",
            "other_available_turbine_states",
        }

        for name, value in applied_map.items():
            if name in {"turbine_ids", "model_kind"}:
                continue
            if name in non_actuator_fields or name in turbine:
                raise ValueError(f"applied_control cannot write reserved field {name!r}")
            array = self._array(value, name)
            if array.shape != turbine_shape:
                raise ValueError(
                    f"applied field {name!r} must have shape {turbine_shape}, got {array.shape}"
                )
            turbine[name] = array

        diagnostics: Dict[str, np.ndarray] = {}
        raw_farm: Dict[str, np.ndarray] = {}
        for name, value in plant_map.items():
            if name == power_field or name in {"turbine_ids", "model_kind"}:
                continue
            if name == "other_available_turbine_states":
                extra_states = _as_mapping(value, name)
                for extra_name, extra_value in extra_states.items():
                    if (
                        extra_name in turbine
                        or extra_name in non_actuator_fields
                    ):
                        raise ValueError(
                            f"plant extra state cannot override reserved field {extra_name!r}"
                        )

                    extra_array = self._array(extra_value, extra_name)
                    if extra_array.shape != turbine_shape:
                        raise ValueError(
                            f"extra turbine state {extra_name!r} must have shape "
                            f"{turbine_shape}, got {extra_array.shape}"
                        )
                    turbine[extra_name] = extra_array
                continue
            array = self._array(value, name)
            # Semantic names take precedence over shape.  This matters for the
            # N=1 case where a farm scalar [1] is shape-identical to [N].
            if name in {"in_domain", "ood_score", "violation_code", "turbine_active_mask"}:
                diagnostics[name] = array
            elif name in {"floris_farm_power_sum_w", "farm_active_power_w"}:
                raw_farm[name] = array
            elif array.shape == turbine_shape:
                if name in turbine:
                    raise ValueError(
                        f"plant output cannot override actuator-owned field {name!r}"
                    )
                turbine[name] = array
            else:
                raw_farm[name] = array

        active_mask = plant_map.get("turbine_active_mask")
        if active_mask is None:
            effective_power = turbine_power
        else:
            mask = np.asarray(active_mask, dtype=bool)
            if mask.shape != turbine_shape:
                raise ValueError(
                    f"turbine_active_mask must have shape {turbine_shape}, got {mask.shape}"
                )
            effective_power = np.where(mask, turbine_power, 0.0)
            diagnostics["turbine_active_mask"] = mask.copy()

        farm_power = np.sum(effective_power, axis=-1, keepdims=True)
        supplied_farm = plant_map.get("floris_farm_power_sum_w")
        if supplied_farm is not None:
            supplied_array = np.asarray(supplied_farm, dtype=np.float64)
            if supplied_array.shape != farm_power.shape:
                raise ValueError(
                    "floris_farm_power_sum_w must have shape "
                    f"{farm_power.shape}, got {supplied_array.shape}"
                )
            if not np.allclose(supplied_array, farm_power, rtol=1e-5, atol=1e-3):
                raise ValueError(
                    "floris_farm_power_sum_w is inconsistent with the authoritative "
                    "sum of turbine power"
                )

        farm = dict(raw_farm)
        farm["farm_active_power_w"] = farm_power.copy()
        farm["interval_mean_farm_active_power_w"] = farm_power.copy()
        farm["interval_energy_j"] = farm_power * self.config.control_interval_s

        if action_saturation_mask is not None:
            saturation = np.asarray(action_saturation_mask, dtype=bool)
            if saturation.ndim < 2 or saturation.shape[-2] != self.config.turbine_count:
                raise ValueError(
                    "action_saturation_mask must end with shape [N,A] and match "
                    f"N={self.config.turbine_count}, got {saturation.shape}"
                )
            expected_leading = turbine_shape[:-1]
            if saturation.shape[:-2] != expected_leading:
                raise ValueError("action_saturation_mask batch dimensions do not match power")
            diagnostics["action_saturation_mask"] = saturation.copy()

        return AssembledState(
            turbine=turbine,
            farm=farm,
            disturbance={
                name: self._array(value, name) for name, value in disturbance_map.items()
            },
            diagnostics=diagnostics,
            batched=batched,
        )


@dataclass(frozen=True)
class ObservationFeatureConfig:
    """One observation feature and its explicit affine normalization.

    Valid paths include ``turbine.<field>``, ``farm.<field>``,
    ``disturbance.<field>``, ``diagnostics.<field>``,
    ``reference.power_reference_w``, ``previous_action_normalized`` and
    ``derived.power_tracking_error_w``.
    """

    path: str
    offset: Any
    scale: Any
    source: ParameterSource
    normalized_clip_min: float | None = None
    normalized_clip_max: float | None = None

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise ValueError("observation feature path must be non-empty")
        scale = np.asarray(self.scale, dtype=np.float64)
        if not np.all(np.isfinite(scale)) or np.any(scale == 0.0):
            raise ValueError(f"observation scale for {self.path!r} must be finite and non-zero")
        offset = np.asarray(self.offset, dtype=np.float64)
        if not np.all(np.isfinite(offset)):
            raise ValueError(f"observation offset for {self.path!r} must be finite")
        if (
            self.normalized_clip_min is not None
            and self.normalized_clip_max is not None
            and self.normalized_clip_min >= self.normalized_clip_max
        ):
            raise ValueError("normalized_clip_min must be less than normalized_clip_max")


@dataclass(frozen=True)
class ObservationConfig:
    """Ordered observation schema."""

    features: Sequence[ObservationFeatureConfig]

    def __post_init__(self) -> None:
        if not self.features:
            raise ValueError("at least one observation feature is required")


class ObservationBuilder:
    """Build a deterministic flat normalized observation in configured order."""

    def __init__(self, config: ObservationConfig):
        self.config = config

    @staticmethod
    def _resolve_group(state: AssembledState, group_name: str) -> Mapping[str, np.ndarray]:
        group = getattr(state, group_name, None)
        if not isinstance(group, Mapping):
            raise KeyError(f"unknown observation state group {group_name!r}")
        return group

    def _resolve(
        self,
        path: str,
        state: AssembledState,
        power_reference_w: Any,
        previous_action_normalized: Any,
    ) -> np.ndarray:
        if path == "reference.power_reference_w":
            return np.asarray(power_reference_w, dtype=np.float64)
        if path == "previous_action_normalized":
            return np.asarray(previous_action_normalized, dtype=np.float64)
        if path == "derived.power_tracking_error_w":
            reference = np.asarray(power_reference_w, dtype=np.float64)
            power = np.asarray(
                state.farm["interval_mean_farm_active_power_w"], dtype=np.float64
            )
            return reference - power
        if "." not in path:
            raise KeyError(f"invalid observation feature path {path!r}")
        group_name, field_name = path.split(".", maxsplit=1)
        group = self._resolve_group(state, group_name)
        if field_name not in group:
            raise KeyError(f"state has no observation field {path!r}")
        return np.asarray(group[field_name], dtype=np.float64)

    def build(
        self,
        state: AssembledState,
        *,
        power_reference_w: Any,
        previous_action_normalized: Any,
    ) -> np.ndarray:
        """Return ``[F]`` for unbatched state or ``[B,F]`` for batched state."""

        flattened = []
        batch_size: int | None = None
        for feature in self.config.features:
            raw = self._resolve(
                feature.path, state, power_reference_w, previous_action_normalized
            )
            normalized = (raw - np.asarray(feature.offset)) / np.asarray(feature.scale)
            if feature.normalized_clip_min is not None:
                normalized = np.maximum(normalized, feature.normalized_clip_min)
            if feature.normalized_clip_max is not None:
                normalized = np.minimum(normalized, feature.normalized_clip_max)
            if not np.all(np.isfinite(normalized)):
                raise ValueError(f"normalized observation {feature.path!r} contains NaN or Inf")

            if state.batched:
                if normalized.ndim < 1:
                    raise ValueError(
                        f"batched observation feature {feature.path!r} has scalar shape"
                    )
                if batch_size is None:
                    batch_size = normalized.shape[0]
                elif normalized.shape[0] != batch_size:
                    raise ValueError("observation features have inconsistent batch sizes")
                flattened.append(normalized.reshape(normalized.shape[0], -1))
            else:
                flattened.append(normalized.reshape(1, -1))

        observation = np.concatenate(flattened, axis=-1).astype(np.float32)
        return observation if state.batched else observation[0]
