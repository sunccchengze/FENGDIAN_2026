"""Replaceable quasi-static wind-farm environment for PPO integration.

Pipeline for every pseudo-time step::

    normalized action -> ActionMapper -> ActuatorModel -> PlantModel
      -> StateAssembler -> ObservationBuilder / RewardCalculator

The concrete plant is injected.  A real PINN adapter can therefore replace
``MockQuasiStaticPlant`` without changing this environment.  The environment
does not pretend that repeated steady queries are plant dynamics: pseudo-time
exists only in the external disturbance, actuator and reference generator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import yaml

from optimization_control.utils.action_mapper import (
    ActionChannelConfig,
    ActionMapper,
    ActionMapperConfig,
    ParameterSource,
)
from optimization_control.utils.actuator_model import (
    ActuatorChannelConfig,
    ActuatorModel,
    ActuatorModelConfig,
)
from optimization_control.utils.reference_power import (
    ReferencePowerConfig,
    ReferencePowerGenerator,
    ReferencePowerStepResult,
)
from optimization_control.utils.reward import RewardCalculator, RewardConfig, RewardResult
from optimization_control.utils.state_pipeline import (
    AssembledState,
    ObservationBuilder,
    ObservationConfig,
    ObservationFeatureConfig,
    StateAssembler,
    StateAssemblerConfig,
)

from .mock_quasi_static_plant import MockPlantParameters, MockQuasiStaticPlant
from .plant_model import (
    AppliedOperatingPoint,
    DisturbanceBatch,
    PlantModel,
    SteadyPlantOutput,
    validate_plant_compatibility,
)


ACTION_CHANNELS = (
    "yaw_misalignment_reference_rad",
    "collective_pitch_reference_rad",
    "rotor_speed_reference_rad_s",
)
APPLIED_CHANNELS = (
    "applied_yaw_misalignment_rad",
    "applied_collective_pitch_rad",
    "applied_rotor_speed_operating_point_rad_s",
)


@dataclass(frozen=True)
class QuasiStaticEnvConfig:
    """Environment-only values; physical assumptions belong in the YAML file."""

    seed: int
    control_interval_s: float
    episode_horizon_steps: int
    synthetic_wind_speed_base_m_s: float
    synthetic_wind_speed_amplitude_m_s: float
    synthetic_wind_period_steps: int
    synthetic_wind_noise_std_m_s: float
    ambient_wind_direction_rad: float
    turbulence_intensity: float
    initial_applied_control: Mapping[str, float]
    available_power_operating_point: Mapping[str, float]
    farm_power_ramp_limit_w_s: float
    observation_wind_speed_scale_m_s: float

    def __post_init__(self) -> None:
        if self.control_interval_s <= 0.0 or not np.isfinite(self.control_interval_s):
            raise ValueError("control_interval_s must be finite and positive")
        if self.episode_horizon_steps <= 0:
            raise ValueError("episode_horizon_steps must be positive")
        if self.synthetic_wind_period_steps <= 0:
            raise ValueError("synthetic_wind_period_steps must be positive")
        if self.synthetic_wind_speed_base_m_s < 0.0:
            raise ValueError("synthetic_wind_speed_base_m_s must be non-negative")
        if self.synthetic_wind_speed_amplitude_m_s < 0.0:
            raise ValueError("synthetic_wind_speed_amplitude_m_s must be non-negative")
        if self.synthetic_wind_noise_std_m_s < 0.0:
            raise ValueError("synthetic_wind_noise_std_m_s must be non-negative")
        if self.turbulence_intensity < 0.0:
            raise ValueError("turbulence_intensity must be non-negative")
        if self.farm_power_ramp_limit_w_s <= 0.0:
            raise ValueError("farm_power_ramp_limit_w_s must be positive")
        if self.observation_wind_speed_scale_m_s <= 0.0:
            raise ValueError("observation_wind_speed_scale_m_s must be positive")
        if set(self.initial_applied_control) != set(APPLIED_CHANNELS):
            raise ValueError("initial_applied_control must contain the three applied channels")
        if set(self.available_power_operating_point) != set(APPLIED_CHANNELS):
            raise ValueError(
                "available_power_operating_point must contain the three applied channels"
            )



class DisturbanceProvider(Protocol):
    """Replaceable source of causal, single-environment wind conditions."""

    def reset(self, *, seed: int | None = None) -> None: ...

    def at(self, step_index: int) -> DisturbanceBatch: ...


class SyntheticDisturbanceProvider:
    """Seeded sine-plus-noise profile used only before real time series arrive."""

    def __init__(self, config: QuasiStaticEnvConfig):
        self.config = config
        self._rng = np.random.default_rng(config.seed)

    def reset(self, *, seed: int | None = None) -> None:
        if seed is not None:
            self._rng = np.random.default_rng(seed)

    def at(self, step_index: int) -> DisturbanceBatch:
        phase = 2.0 * np.pi * step_index / self.config.synthetic_wind_period_steps
        noise = self._rng.normal(0.0, self.config.synthetic_wind_noise_std_m_s)
        wind_speed = max(
            0.0,
            self.config.synthetic_wind_speed_base_m_s
            + self.config.synthetic_wind_speed_amplitude_m_s * np.sin(phase)
            + noise,
        )
        return DisturbanceBatch(
            ambient_wind_speed_m_s=np.array([[wind_speed]], dtype=np.float32),
            ambient_wind_direction_rad=np.array(
                [[self.config.ambient_wind_direction_rad]], dtype=np.float32
            ),
            turbulence_intensity=np.array(
                [[self.config.turbulence_intensity]], dtype=np.float32
            ),
        )

class QuasiStaticWindFarmEnv(gym.Env[np.ndarray, np.ndarray]):
    """Single-policy fixed-layout Gym environment with an injected plant."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        plant: PlantModel,
        config: QuasiStaticEnvConfig,
        action_mapper: ActionMapper,
        actuator_model: ActuatorModel,
        reference_power_generator: ReferencePowerGenerator,
        state_assembler: StateAssembler,
        observation_builder: ObservationBuilder,
        reward_calculator: RewardCalculator,
        disturbance_provider: DisturbanceProvider | None = None,
    ) -> None:
        super().__init__()
        validate_plant_compatibility(plant)
        self.plant = plant
        self.config = config
        self.action_mapper = action_mapper
        self.actuator_model = actuator_model
        self.reference_power_generator = reference_power_generator
        self.state_assembler = state_assembler
        self.observation_builder = observation_builder
        self.reward_calculator = reward_calculator
        self.turbine_ids = tuple(plant.turbine_ids)
        self.turbine_count = len(self.turbine_ids)
        self.action_channel_count = len(ACTION_CHANNELS)
        self._validate_dependencies()

        self.action_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(self.turbine_count * self.action_channel_count,),
            dtype=np.float32,
        )
        self.disturbance_provider = (
            disturbance_provider or SyntheticDisturbanceProvider(config)
        )
        self.disturbance_provider.reset(seed=config.seed)
        initial_observation, _ = self._start_episode()
        self.observation_space = spaces.Box(
            low=np.finfo(np.float32).min,
            high=np.finfo(np.float32).max,
            shape=initial_observation.shape,
            dtype=np.float32,
        )

    def _validate_dependencies(self) -> None:
        if self.action_mapper.config.turbine_count != self.turbine_count:
            raise ValueError("ActionMapper turbine count does not match plant")
        if tuple(self.action_mapper.channel_names) != ACTION_CHANNELS:
            raise ValueError(f"ActionMapper channels must be ordered as {ACTION_CHANNELS}")
        if self.actuator_model.config.turbine_count != self.turbine_count:
            raise ValueError("ActuatorModel turbine count does not match plant")
        if tuple(self.actuator_model.command_names) != ACTION_CHANNELS:
            raise ValueError("ActuatorModel command names do not match ActionMapper")
        if tuple(self.actuator_model.applied_names) != APPLIED_CHANNELS:
            raise ValueError(f"ActuatorModel applied names must be ordered as {APPLIED_CHANNELS}")
        intervals = (
            self.actuator_model.config.control_interval_s,
            self.state_assembler.config.control_interval_s,
            self.reference_power_generator.config.control_interval_s,
        )
        if any(
            not np.isclose(value, self.config.control_interval_s)
            for value in intervals
        ):
            raise ValueError("all optimization components must share control_interval_s")
        if self.state_assembler.config.turbine_count != self.turbine_count:
            raise ValueError("StateAssembler turbine count does not match plant")
        wind_features = [
            feature
            for feature in self.observation_builder.config.features
            if feature.path == "disturbance.ambient_wind_speed_m_s"
        ]
        if len(wind_features) != 1 or not np.allclose(
            np.asarray(wind_features[0].scale),
            self.config.observation_wind_speed_scale_m_s,
        ):
            raise ValueError("ObservationBuilder wind-speed scale does not match env config")

    def _per_turbine(self, values: Mapping[str, float]) -> dict[str, np.ndarray]:
        return {
            name: np.full(self.turbine_count, value, dtype=np.float64)
            for name, value in values.items()
        }

    def _disturbance(self, step_index: int) -> DisturbanceBatch:
        disturbance = self.disturbance_provider.at(step_index)
        if not isinstance(disturbance, DisturbanceBatch):
            raise TypeError("DisturbanceProvider.at must return DisturbanceBatch")
        if disturbance.batch_size != 1:
            raise ValueError(
                "single Gym environment requires DisturbanceBatch with B=1"
            )
        return disturbance

    def _operating_point(
        self, applied_control: Mapping[str, np.ndarray]
    ) -> AppliedOperatingPoint:
        def batched(name: str) -> np.ndarray:
            value = np.asarray(applied_control[name], dtype=np.float32)
            if value.shape != (self.turbine_count,):
                raise ValueError(
                    f"applied control {name!r} must have shape "
                    f"({self.turbine_count},), got {value.shape}"
                )
            return value[None, :]

        return AppliedOperatingPoint(
            turbine_ids=self.turbine_ids,
            applied_yaw_misalignment_rad=batched("applied_yaw_misalignment_rad"),
            applied_collective_pitch_rad=batched("applied_collective_pitch_rad"),
            applied_rotor_speed_operating_point_rad_s=batched(
                "applied_rotor_speed_operating_point_rad_s"
            ),
        )

    def _query_plant(
        self,
        disturbance: DisturbanceBatch,
        applied_control: Mapping[str, np.ndarray],
    ) -> SteadyPlantOutput:
        output = self.plant.predict_steady(
            disturbance=disturbance,
            applied_operating_point=self._operating_point(applied_control),
        )
        if output.turbine_ids != self.turbine_ids:
            raise ValueError("plant output changed turbine_ids order")
        return output

    def _available_power_query(
        self, disturbance: DisturbanceBatch
    ) -> SteadyPlantOutput:
        # Counterfactual query is independent of the current applied control.
        # This prevents curtailment -> lower availability -> lower reference
        # from forming a self-contracting feedback loop.
        baseline = self._per_turbine(self.config.available_power_operating_point)
        output = self._query_plant(disturbance, baseline)
        if not np.all(output.in_domain):
            score = float(np.max(output.ood_score))
            raise RuntimeError(
                "available-power counterfactual query is out of domain "
                f"(max ood_score={score:.6g}); refusing to generate a reference"
            )
        return output

    @staticmethod
    def _wrap_angle(angle_rad: np.ndarray) -> np.ndarray:
        return (angle_rad + np.pi) % (2.0 * np.pi) - np.pi

    def _assemble_state(
        self,
        disturbance: DisturbanceBatch,
        applied_control: Mapping[str, np.ndarray],
        plant_output: SteadyPlantOutput,
        action_saturation_mask: np.ndarray,
    ) -> AssembledState:
        wind_direction = np.full(
            self.turbine_count,
            float(disturbance.ambient_wind_direction_rad[0, 0]),
            dtype=np.float64,
        )
        yaw = np.asarray(applied_control["applied_yaw_misalignment_rad"])
        complete_control = dict(applied_control)
        complete_control.update(
            {
                "yaw_misalignment_rad": yaw.copy(),
                "collective_pitch_rad": np.asarray(
                    applied_control["applied_collective_pitch_rad"]
                ).copy(),
                "rotor_speed_rad_s": np.asarray(
                    applied_control[
                        "applied_rotor_speed_operating_point_rad_s"
                    ]
                ).copy(),
                "nacelle_heading_rad": self._wrap_angle(wind_direction + yaw),
            }
        )
        disturbance_unbatched = {
            "ambient_wind_speed_m_s": disturbance.ambient_wind_speed_m_s[0],
            "ambient_wind_direction_rad": disturbance.ambient_wind_direction_rad[0],
            "turbulence_intensity": disturbance.turbulence_intensity[0],
        }
        plant_unbatched = {
            "floris_turbine_power_w": plant_output.floris_turbine_power_w[0],
            "floris_farm_power_sum_w": plant_output.floris_farm_power_sum_w[0],
            "effective_wind_speed_m_s": plant_output.effective_wind_speed_m_s[0],
            "in_domain": plant_output.in_domain[0],
            "ood_score": plant_output.ood_score[0],
        }
        extra_states = {
            name: value[0]
            for name, value in plant_output.other_available_turbine_states.items()
        }
        collisions = set(plant_unbatched).intersection(extra_states)
        if collisions:
            raise ValueError(
                f"plant extra states cannot override core fields: {sorted(collisions)}"
            )
        plant_unbatched.update(extra_states)
        return self.state_assembler.assemble(
            disturbance=disturbance_unbatched,
            applied_control=complete_control,
            plant_output=plant_unbatched,
            action_saturation_mask=action_saturation_mask,
        )
    def _normalized_hold_action(
        self, applied_control: Mapping[str, np.ndarray]
    ) -> np.ndarray:
        commanded = {
            ACTION_CHANNELS[0]: applied_control[APPLIED_CHANNELS[0]],
            ACTION_CHANNELS[1]: applied_control[APPLIED_CHANNELS[1]],
            ACTION_CHANNELS[2]: applied_control[APPLIED_CHANNELS[2]],
        }
        normalized = self.action_mapper.normalize_physical(commanded)
        if np.any(normalized.physical_saturation_mask):
            raise RuntimeError("applied actuator state lies outside ActionMapper bounds")
        return normalized.normalized_action.copy()


    def _start_episode(self) -> tuple[np.ndarray, dict[str, Any]]:
        self._needs_reset = False
        self._step_index = 0
        self._previous_action = np.zeros(
            (self.turbine_count, self.action_channel_count), dtype=np.float64
        )
        applied_control = self.actuator_model.reset(
            self._per_turbine(self.config.initial_applied_control)
        )
        self._previous_action = self._normalized_hold_action(applied_control)
        self.hold_action_normalized = self._previous_action.reshape(-1).astype(
            np.float32
        )
        disturbance = self._disturbance(step_index=0)
        plant_output = self._query_plant(disturbance, applied_control)
        available_output = self._available_power_query(disturbance)
        available_power = available_output.floris_farm_power_sum_w[0]
        reference_result = self.reference_power_generator.reset(available_power)
        empty_saturation = np.zeros(
            (self.turbine_count, self.action_channel_count), dtype=np.bool_
        )
        state = self._assemble_state(
            disturbance, applied_control, plant_output, empty_saturation
        )
        self._previous_farm_power_w = np.asarray(
            state.farm["interval_mean_farm_active_power_w"], dtype=np.float64
        ).copy()
        self._last_state = state
        self._last_plant_output = plant_output
        self._last_available_output = available_output
        self._last_reference_result = reference_result
        observation = self.observation_builder.build(
            state,
            power_reference_w=reference_result.reference_power_w,
            previous_action_normalized=self._previous_action,
        )
        info = self._info(
            reward_result=None,
            mapping_saturation_mask=empty_saturation,
            actuator_result=None,
        )
        return np.asarray(observation, dtype=np.float32), info

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        del options
        super().reset(seed=seed)
        self.disturbance_provider.reset(seed=seed)
        return self._start_episode()

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if self._needs_reset:
            raise RuntimeError(
                "episode has ended; call reset() before the next step()"
            )
        action_array = np.asarray(action, dtype=np.float64)
        matrix_shape = (self.turbine_count, self.action_channel_count)
        if action_array.shape == self.action_space.shape:
            action_matrix = action_array.reshape(matrix_shape)
        elif action_array.shape == matrix_shape:
            action_matrix = action_array
        else:
            raise ValueError(
                f"action must have flat shape {self.action_space.shape}, got {action_array.shape}"
            )
        if not np.all(np.isfinite(action_matrix)):
            raise ValueError("action contains NaN or Inf")

        mapping_result = self.action_mapper.map(action_matrix)
        actuator_result = self.actuator_model.step(mapping_result.commanded_control)
        combined_saturation = (
            mapping_result.action_saturation_mask | actuator_result.action_saturation_mask
        )
        self.hold_action_normalized = self._normalized_hold_action(
            actuator_result.applied_control
        ).reshape(-1).astype(np.float32)

        self._step_index += 1
        disturbance = self._disturbance(self._step_index)
        plant_output = self._query_plant(
            disturbance, actuator_result.applied_control
        )
        available_output = self._available_power_query(disturbance)
        available_power = available_output.floris_farm_power_sum_w[0]
        reference_result = self.reference_power_generator.step(available_power)
        state = self._assemble_state(
            disturbance,
            actuator_result.applied_control,
            plant_output,
            combined_saturation,
        )

        farm_power = np.asarray(
            state.farm["interval_mean_farm_active_power_w"], dtype=np.float64
        )
        farm_power_ramp = (
            farm_power - self._previous_farm_power_w
        ) / self.config.control_interval_s
        constraint_violation = combined_saturation.astype(np.float64)
        ood_signal = np.maximum(
            (~plant_output.in_domain[0]).astype(np.float64),
            plant_output.ood_score[0],
        )
        reward_result = self.reward_calculator.calculate(
            farm_power_w=farm_power,
            power_reference_w=reference_result.reference_power_w,
            action_normalized=mapping_result.clipped_action_normalized,
            previous_action_normalized=self._previous_action,
            farm_power_ramp_w_s=farm_power_ramp,
            ramp_limit_w_s=np.full_like(
                farm_power_ramp, self.config.farm_power_ramp_limit_w_s
            ),
            constraint_violation=constraint_violation,
            ood_mask=ood_signal,
            interval_energy_j=state.farm["interval_energy_j"],
        )
        self._previous_action = mapping_result.clipped_action_normalized.copy()
        self._previous_farm_power_w = farm_power.copy()
        self._last_state = state
        self._last_plant_output = plant_output
        self._last_available_output = available_output
        self._last_reference_result = reference_result

        observation = self.observation_builder.build(
            state,
            power_reference_w=reference_result.reference_power_w,
            previous_action_normalized=self._previous_action,
        )
        terminated = False
        truncated = self._step_index >= self.config.episode_horizon_steps
        self._needs_reset = truncated
        info = self._info(
            reward_result=reward_result,
            mapping_saturation_mask=mapping_result.action_saturation_mask,
            actuator_result=actuator_result,
        )
        return (
            np.asarray(observation, dtype=np.float32),
            float(reward_result.total),
            terminated,
            truncated,
            info,
        )

    @staticmethod
    def _scalar(value: Any) -> float:
        array = np.asarray(value, dtype=np.float64)
        return float(array.reshape(-1)[0])

    def _info(
        self,
        *,
        reward_result: RewardResult | None,
        mapping_saturation_mask: np.ndarray,
        actuator_result: Any | None,
    ) -> dict[str, Any]:
        output = self._last_plant_output
        available = self._last_available_output
        reference = self._last_reference_result
        if actuator_result is None:
            actuator_flags = {
                "position_saturated": False,
                "rate_saturated": False,
                "held_for_multirate_update": False,
            }
        else:
            actuator_flags = {
                "position_saturated": any(
                    np.any(mask)
                    for mask in actuator_result.position_saturation_mask.values()
                ),
                "rate_saturated": any(
                    np.any(mask) for mask in actuator_result.rate_saturation_mask.values()
                ),
                "held_for_multirate_update": any(
                    np.any(mask) for mask in actuator_result.hold_mask.values()
                ),
            }
        reward_components = (
            {}
            if reward_result is None
            else {name: self._scalar(value) for name, value in reward_result.components.items()}
        )
        return {
            "step_index": self._step_index,
            "turbine_ids": self.turbine_ids,
            "model_kind": output.model_kind,
            "farm_power_w": self._scalar(output.floris_farm_power_sum_w),
            "farm_available_power_w": self._scalar(
                available.floris_farm_power_sum_w
            ),
            "farm_available_power_semantics": (
                "baseline_control_counterfactual_estimate"
            ),
            "hold_action_normalized": self.hold_action_normalized.copy(),
            "farm_power_reference_w": self._scalar(reference.reference_power_w),
            "reward_components": reward_components,
            "constraint_flags": {
                "normalized_action_clipped": bool(
                    np.any(mapping_saturation_mask)
                ),
                **actuator_flags,
            },
            "domain_flags": {
                "in_domain": bool(np.all(output.in_domain)),
                "ood_score": self._scalar(output.ood_score),
                "available_power_query_in_domain": bool(
                    np.all(available.in_domain)
                ),
            },
            "reference_flags": {
                "ramp_up_limited": bool(
                    np.any(reference.ramp_up_limited_mask)
                ),
                "ramp_down_limited": bool(
                    np.any(reference.ramp_down_limited_mask)
                ),
                "availability_clipped": bool(
                    np.any(reference.availability_clip_mask)
                ),
            },
        }

    def render(self) -> None:
        return None


def _value(document: Mapping[str, Any], *path: str) -> Any:
    node: Any = document
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            raise KeyError(f"configuration is missing {'.'.join(path)}")
        node = node[key]
    if not isinstance(node, Mapping) or "value" not in node:
        raise KeyError(f"configuration value {'.'.join(path)} must use value/source form")
    if "source" not in node:
        raise KeyError(f"configuration value {'.'.join(path)} is missing source")
    return node["value"]


def _assumption_source(config_path: Path, section: str) -> ParameterSource:
    return ParameterSource(
        kind="assumption",
        reference=str(config_path),
        note=f"Temporary quasi-static v0 integration value: {section}",
    )


def load_quasi_static_env(
    config_path: str | Path,
    *,
    plant: PlantModel | None = None,
    disturbance_provider: DisturbanceProvider | None = None,
) -> QuasiStaticWindFarmEnv:
    """Build the integration environment from the provenance-bearing YAML."""

    path = Path(config_path).resolve()
    with path.open("r", encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    if not isinstance(document, Mapping):
        raise ValueError("quasi-static environment config must be a mapping")

    model_kind = _value(document, "interface", "model_kind")
    model_dt_s = _value(document, "interface", "model_dt_s")
    control_mode = _value(document, "action_mapper", "control_mode")
    if model_kind != "quasi_static":
        raise ValueError(
            f"this loader only supports model_kind='quasi_static', got {model_kind!r}"
        )
    if model_dt_s is not None:
        raise ValueError("quasi-static model_dt_s must be null/not_applicable")
    if control_mode != "absolute_reference":
        raise ValueError(
            "this environment currently supports only absolute_reference actions"
        )

    turbine_ids = tuple(str(item) for item in _value(document, "interface", "turbine_ids"))
    if plant is None:
        mock_parameters = MockPlantParameters(
            cut_in_wind_speed_m_s=float(
                _value(document, "mock_plant", "cut_in_wind_speed_m_s")
            ),
            rated_wind_speed_m_s=float(
                _value(document, "mock_plant", "rated_wind_speed_m_s")
            ),
            cut_out_wind_speed_m_s=float(
                _value(document, "mock_plant", "cut_out_wind_speed_m_s")
            ),
            rated_rotor_speed_rad_s=float(
                _value(document, "mock_plant", "rated_rotor_speed_rad_s")
            ),
            yaw_power_exponent=float(
                _value(document, "mock_plant", "yaw_power_exponent")
            ),
            pitch_decay_scale_rad=float(
                _value(document, "mock_plant", "pitch_decay_scale_rad")
            ),
            rotor_speed_width_rad_s=float(
                _value(document, "mock_plant", "rotor_speed_width_rad_s")
            ),
            downstream_wake_loss_fraction=float(
                _value(document, "mock_plant", "downstream_wake_loss_fraction")
            ),
            valid_turbulence_intensity_max=float(
                _value(document, "mock_plant", "valid_turbulence_intensity_max")
            ),
        )
        plant = MockQuasiStaticPlant(
            turbine_ids=turbine_ids,
            rated_power_w=float(_value(document, "mock_plant", "rated_power_w")),
            parameters=mock_parameters,
        )
    elif tuple(plant.turbine_ids) != turbine_ids:
        raise ValueError("replacement plant turbine_ids do not match fixed YAML order")

    turbine_count = len(turbine_ids)
    control_interval_s = float(
        _value(document, "environment", "control_interval_s")
    )
    source = _assumption_source(path, "component parameters")
    action_bounds = {
        name: (
            float(_value(document, "action_mapper", name, "minimum")),
            float(_value(document, "action_mapper", name, "maximum")),
        )
        for name in ACTION_CHANNELS
    }
    units = ("rad", "rad", "rad/s")
    action_mapper = ActionMapper(
        ActionMapperConfig(
            turbine_count=turbine_count,
            channels=tuple(
                ActionChannelConfig(
                    name=name,
                    physical_min=action_bounds[name][0],
                    physical_max=action_bounds[name][1],
                    unit=unit,
                    source=source,
                )
                for name, unit in zip(ACTION_CHANNELS, units)
            ),
        )
    )

    actuator_sections = (
        ("yaw", ACTION_CHANNELS[0], APPLIED_CHANNELS[0], "rate_limit_rad_s", "rad"),
        (
            "collective_pitch",
            ACTION_CHANNELS[1],
            APPLIED_CHANNELS[1],
            "rate_limit_rad_s",
            "rad",
        ),
        (
            "rotor_speed_operating_point",
            ACTION_CHANNELS[2],
            APPLIED_CHANNELS[2],
            "acceleration_limit_rad_s2",
            "rad/s",
        ),
    )
    actuator_model = ActuatorModel(
        ActuatorModelConfig(
            turbine_count=turbine_count,
            control_interval_s=control_interval_s,
            control_interval_source=source,
            channels=tuple(
                ActuatorChannelConfig(
                    command_name=command_name,
                    applied_name=applied_name,
                    minimum=action_bounds[command_name][0],
                    maximum=action_bounds[command_name][1],
                    rate_limit_per_s=float(
                        _value(document, "actuator_model", section, rate_name)
                    ),
                    time_constant_s=float(
                        _value(document, "actuator_model", section, "time_constant_s")
                    ),
                    update_period_steps=int(
                        _value(document, "actuator_model", section, "update_period_steps")
                    ),
                    command_delay_s=float(
                        _value(document, "actuator_model", section, "command_delay_s")
                    ),
                    unit=unit,
                    source=source,
                )
                for section, command_name, applied_name, rate_name, unit in actuator_sections
            ),
        )
    )

    reference_power_generator = ReferencePowerGenerator(
        ReferencePowerConfig(
            control_interval_s=control_interval_s,
            headroom_fraction=float(
                _value(document, "reference_power", "headroom_fraction")
            ),
            low_pass_time_constant_s=float(
                _value(document, "reference_power", "low_pass_time_constant_s")
            ),
            ramp_up_limit_w_s=float(
                _value(document, "reference_power", "ramp_up_limit_w_s")
            ),
            ramp_down_limit_w_s=float(
                _value(document, "reference_power", "ramp_down_limit_w_s")
            ),
            source=source,
        )
    )
    state_assembler = StateAssembler(
        StateAssemblerConfig(
            turbine_count=turbine_count,
            control_interval_s=control_interval_s,
            turbine_power_field="floris_turbine_power_w",
            source=source,
        )
    )

    farm_rated_power_w = float(np.sum(plant.rated_power_w))
    yaw_scale = max(abs(value) for value in action_bounds[ACTION_CHANNELS[0]])
    pitch_scale = max(abs(value) for value in action_bounds[ACTION_CHANNELS[1]])
    speed_scale = max(abs(value) for value in action_bounds[ACTION_CHANNELS[2]])
    observation_builder = ObservationBuilder(
        ObservationConfig(
            features=(
                ObservationFeatureConfig(
                    "derived.power_tracking_error_w", 0.0, farm_rated_power_w, source
                ),
                ObservationFeatureConfig(
                    "farm.interval_mean_farm_active_power_w", 0.0, farm_rated_power_w, source
                ),
                ObservationFeatureConfig(
                    "disturbance.ambient_wind_speed_m_s",
                    0.0,
                    float(_value(document, "observation", "wind_speed_scale_m_s")),
                    source,
                ),
                ObservationFeatureConfig(
                    "disturbance.ambient_wind_direction_rad", 0.0, np.pi, source
                ),
                ObservationFeatureConfig(
                    "disturbance.turbulence_intensity", 0.0, 1.0, source
                ),
                ObservationFeatureConfig(
                    "turbine.floris_turbine_power_w", 0.0, plant.rated_power_w, source
                ),
                ObservationFeatureConfig(
                    "turbine.applied_rotor_speed_operating_point_rad_s",
                    0.0,
                    speed_scale,
                    source,
                ),
                ObservationFeatureConfig(
                    "turbine.applied_collective_pitch_rad", 0.0, pitch_scale, source
                ),
                ObservationFeatureConfig(
                    "turbine.applied_yaw_misalignment_rad", 0.0, yaw_scale, source
                ),
                ObservationFeatureConfig(
                    "previous_action_normalized", 0.0, 1.0, source
                ),
            )
        )
    )
    ramp_up = float(_value(document, "reference_power", "ramp_up_limit_w_s"))
    ramp_down = float(_value(document, "reference_power", "ramp_down_limit_w_s"))
    reward_calculator = RewardCalculator(
        RewardConfig(
            tracking_weight=float(_value(document, "reward", "tracking_weight")),
            ramp_weight=float(_value(document, "reward", "ramp_weight")),
            action_rate_weight=float(
                _value(document, "reward", "action_rate_weight")
            ),
            load_weight=float(_value(document, "reward", "load_weight")),
            constraint_weight=float(
                _value(document, "reward", "constraint_weight")
            ),
            ood_weight=float(_value(document, "reward", "ood_weight")),
            energy_weight=float(_value(document, "reward", "energy_weight")),
            tracking_error_scale_w=farm_rated_power_w,
            ramp_violation_scale_w_s=max(ramp_up, ramp_down),
            energy_scale_j=farm_rated_power_w * control_interval_s,
            source=source,
        )
    )

    initial_values = {
        APPLIED_CHANNELS[0]: float(
            _value(
                document,
                "actuator_model",
                "initial_applied_control",
                "yaw_misalignment_rad",
            )
        ),
        APPLIED_CHANNELS[1]: float(
            _value(
                document,
                "actuator_model",
                "initial_applied_control",
                "collective_pitch_rad",
            )
        ),
        APPLIED_CHANNELS[2]: float(
            _value(
                document,
                "actuator_model",
                "initial_applied_control",
                "rotor_speed_operating_point_rad_s",
            )
        ),
    }
    baseline_values = {
        APPLIED_CHANNELS[0]: float(
            _value(document, "available_power_counterfactual", "yaw_misalignment_rad")
        ),
        APPLIED_CHANNELS[1]: float(
            _value(document, "available_power_counterfactual", "collective_pitch_rad")
        ),
        APPLIED_CHANNELS[2]: float(
            _value(
                document,
                "available_power_counterfactual",
                "rotor_speed_operating_point_rad_s",
            )
        ),
    }
    env_config = QuasiStaticEnvConfig(
        seed=int(_value(document, "environment", "seed")),
        control_interval_s=control_interval_s,
        episode_horizon_steps=int(
            _value(document, "environment", "episode_horizon_steps")
        ),
        synthetic_wind_speed_base_m_s=float(
            _value(document, "environment", "synthetic_wind_speed_base_m_s")
        ),
        synthetic_wind_speed_amplitude_m_s=float(
            _value(document, "environment", "synthetic_wind_speed_amplitude_m_s")
        ),
        synthetic_wind_period_steps=int(
            _value(document, "environment", "synthetic_wind_period_steps")
        ),
        synthetic_wind_noise_std_m_s=float(
            _value(document, "environment", "synthetic_wind_noise_std_m_s")
        ),
        ambient_wind_direction_rad=float(
            _value(document, "environment", "ambient_wind_direction_rad")
        ),
        turbulence_intensity=float(
            _value(document, "environment", "turbulence_intensity")
        ),
        initial_applied_control=initial_values,
        available_power_operating_point=baseline_values,
        farm_power_ramp_limit_w_s=max(ramp_up, ramp_down),
        observation_wind_speed_scale_m_s=float(
            _value(document, "observation", "wind_speed_scale_m_s")
        ),
    )
    return QuasiStaticWindFarmEnv(
        plant=plant,
        config=env_config,
        action_mapper=action_mapper,
        actuator_model=actuator_model,
        reference_power_generator=reference_power_generator,
        state_assembler=state_assembler,
        observation_builder=observation_builder,
        reward_calculator=reward_calculator,
        disturbance_provider=disturbance_provider,
    )
