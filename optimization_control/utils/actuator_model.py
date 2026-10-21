"""Optimization-owned actuator dynamics for quasi-static plant coupling."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Mapping, Sequence

import numpy as np

from .action_mapper import ParameterSource


@dataclass(frozen=True)
class ActuatorChannelConfig:
    """Physical constraints and dynamics for one actuator channel.

    Bounds and rates may be scalars or per-turbine arrays.  ``command_delay_s``
    must be an integer multiple of ``control_interval_s``.  A channel updates
    samples a new reference only every update-period call.  Between samples,
    the reference is held while physical state advances every control interval.
    All physical values are mandatory and share the stated
    provenance record.
    """

    command_name: str
    applied_name: str
    minimum: Any
    maximum: Any
    rate_limit_per_s: Any
    time_constant_s: Any
    update_period_steps: int
    command_delay_s: float
    unit: str
    source: ParameterSource

    def __post_init__(self) -> None:
        if not self.command_name.strip() or not self.applied_name.strip():
            raise ValueError("command_name and applied_name must be non-empty")
        if not self.unit.strip():
            raise ValueError(f"unit is required for {self.command_name!r}")
        if self.update_period_steps <= 0:
            raise ValueError("update_period_steps must be a positive integer")
        if not np.isfinite(self.command_delay_s) or self.command_delay_s < 0.0:
            raise ValueError("command_delay_s must be finite and non-negative")


@dataclass(frozen=True)
class ActuatorModelConfig:
    """Configuration for the fixed-layout multi-channel actuator model."""

    turbine_count: int
    control_interval_s: float
    control_interval_source: ParameterSource
    channels: Sequence[ActuatorChannelConfig]

    def __post_init__(self) -> None:
        if self.turbine_count <= 0:
            raise ValueError("turbine_count must be positive")
        if not np.isfinite(self.control_interval_s) or self.control_interval_s <= 0.0:
            raise ValueError("control_interval_s must be finite and positive")
        if not self.channels:
            raise ValueError("at least one actuator channel is required")
        command_names = [channel.command_name for channel in self.channels]
        applied_names = [channel.applied_name for channel in self.channels]
        if len(command_names) != len(set(command_names)):
            raise ValueError(f"command names must be unique: {command_names}")
        if len(applied_names) != len(set(applied_names)):
            raise ValueError(f"applied names must be unique: {applied_names}")


@dataclass(frozen=True)
class ActuatorStepResult:
    """Applied state and diagnostics produced by one actuator step."""

    applied_control: Mapping[str, np.ndarray]
    effective_reference: Mapping[str, np.ndarray]
    position_saturation_mask: Mapping[str, np.ndarray]
    rate_saturation_mask: Mapping[str, np.ndarray]
    hold_mask: Mapping[str, np.ndarray]
    action_saturation_mask: np.ndarray


@dataclass(frozen=True)
class _PreparedChannel:
    config: ActuatorChannelConfig
    minimum: np.ndarray
    maximum: np.ndarray
    rate_limit_per_s: np.ndarray
    time_constant_s: np.ndarray
    delay_steps: int


class ActuatorModel:
    """Apply delay, multi-rate holding, first-order tracking and constraints.

    Typical v0 channels are:

    * ``yaw_misalignment_reference_rad`` -> ``applied_yaw_misalignment_rad``
    * ``collective_pitch_reference_rad`` -> ``applied_collective_pitch_rad``
    * ``rotor_speed_reference_rad_s`` ->
      ``applied_rotor_speed_operating_point_rad_s``

    ``reset`` is mandatory before ``step``.  It recreates every delay queue, so
    no command or applied state can leak from a previous episode.
    """

    def __init__(self, config: ActuatorModelConfig):
        self.config = config
        self._channels = tuple(self._prepare_channel(channel) for channel in config.channels)
        self.command_names = tuple(channel.config.command_name for channel in self._channels)
        self.applied_names = tuple(channel.config.applied_name for channel in self._channels)
        self._state: Dict[str, np.ndarray] = {}
        self._delay_queues: Dict[str, Deque[np.ndarray]] = {}
        self._active_reference: Dict[str, np.ndarray] = {}
        self._step_index = 0
        self._leading_shape: tuple[int, ...] | None = None

    def _per_turbine(self, value: Any, field_name: str) -> np.ndarray:
        array = np.asarray(value, dtype=np.float64)
        if array.ndim == 0:
            if not np.isfinite(array):
                raise ValueError(f"{field_name} must be finite")
            return np.full(self.config.turbine_count, float(array), dtype=np.float64)
        if array.shape != (self.config.turbine_count,):
            raise ValueError(
                f"{field_name} must be scalar or shape ({self.config.turbine_count},), "
                f"got {array.shape}"
            )
        if not np.all(np.isfinite(array)):
            raise ValueError(f"{field_name} must be finite")
        return array.astype(np.float64, copy=True)

    def _prepare_channel(self, channel: ActuatorChannelConfig) -> _PreparedChannel:
        minimum = self._per_turbine(channel.minimum, f"{channel.command_name}.minimum")
        maximum = self._per_turbine(channel.maximum, f"{channel.command_name}.maximum")
        rate_limit = self._per_turbine(
            channel.rate_limit_per_s, f"{channel.command_name}.rate_limit_per_s"
        )
        time_constant = self._per_turbine(
            channel.time_constant_s, f"{channel.command_name}.time_constant_s"
        )
        if np.any(minimum >= maximum):
            raise ValueError(f"{channel.command_name}: minimum must be less than maximum")
        if np.any(rate_limit <= 0.0):
            raise ValueError(f"{channel.command_name}: rate_limit_per_s must be positive")
        if np.any(time_constant <= 0.0):
            raise ValueError(f"{channel.command_name}: time_constant_s must be positive")

        delay_ratio = channel.command_delay_s / self.config.control_interval_s
        delay_steps = int(round(delay_ratio))
        if not np.isclose(delay_ratio, delay_steps, rtol=0.0, atol=1e-9):
            raise ValueError(
                f"{channel.command_name}: command_delay_s must be an integer multiple "
                "of control_interval_s"
            )
        return _PreparedChannel(
            config=channel,
            minimum=minimum,
            maximum=maximum,
            rate_limit_per_s=rate_limit,
            time_constant_s=time_constant,
            delay_steps=delay_steps,
        )

    def _validate_value(self, value: Any, field_name: str) -> np.ndarray:
        array = np.asarray(value, dtype=np.float64)
        if array.ndim < 1 or array.shape[-1] != self.config.turbine_count:
            raise ValueError(
                f"{field_name} must end with turbine dimension "
                f"({self.config.turbine_count},), got {array.shape}"
            )
        if not np.all(np.isfinite(array)):
            raise ValueError(f"{field_name} contains NaN or Inf")
        return array.astype(np.float64, copy=True)

    def reset(self, initial_applied_control: Mapping[str, Any]) -> Mapping[str, np.ndarray]:
        """Reset all applied states and delay queues for a new episode."""

        expected = set(self.applied_names)
        received = set(initial_applied_control)
        if received != expected:
            raise ValueError(
                f"initial_applied_control keys must be {sorted(expected)}, got {sorted(received)}"
            )

        new_state: Dict[str, np.ndarray] = {}
        leading_shape: tuple[int, ...] | None = None
        for channel in self._channels:
            name = channel.config.applied_name
            value = self._validate_value(initial_applied_control[name], name)
            if leading_shape is None:
                leading_shape = value.shape[:-1]
            elif value.shape[:-1] != leading_shape:
                raise ValueError("all initial actuator states must have the same leading shape")
            if np.any(value < channel.minimum) or np.any(value > channel.maximum):
                raise ValueError(f"initial state {name!r} is outside configured position bounds")
            new_state[name] = value

        self._leading_shape = leading_shape
        self._state = new_state
        self._delay_queues = {}
        self._active_reference = {}
        for channel in self._channels:
            name = channel.config.command_name
            initial = self._state[channel.config.applied_name]
            self._delay_queues[name] = deque(
                (initial.copy() for _ in range(channel.delay_steps))
            )
            self._active_reference[name] = initial.copy()
        self._step_index = 0
        return {name: value.copy() for name, value in self._state.items()}

    def step(self, commanded_control: Mapping[str, Any]) -> ActuatorStepResult:
        """Advance all configured actuators by one control interval."""

        if self._leading_shape is None:
            raise RuntimeError("ActuatorModel.reset must be called before step")
        expected = set(self.command_names)
        received = set(commanded_control)
        if received != expected:
            raise ValueError(f"commanded_control keys must be {sorted(expected)}, got {sorted(received)}")

        effective_reference: Dict[str, np.ndarray] = {}
        position_masks: Dict[str, np.ndarray] = {}
        rate_masks: Dict[str, np.ndarray] = {}
        hold_masks: Dict[str, np.ndarray] = {}
        combined_masks = []

        for channel in self._channels:
            config = channel.config
            command = self._validate_value(commanded_control[config.command_name], config.command_name)
            if command.shape[:-1] != self._leading_shape:
                raise ValueError(
                    f"{config.command_name} leading shape changed from "
                    f"{self._leading_shape} to {command.shape[:-1]}"
                )

            queue = self._delay_queues[config.command_name]
            queue.append(command.copy())
            delayed_reference = queue.popleft()

            due = self._step_index % config.update_period_steps == 0
            current = self._state[config.applied_name]
            if due:
                bounded_reference = np.clip(
                    delayed_reference, channel.minimum, channel.maximum
                )
                position_mask = bounded_reference != delayed_reference
                self._active_reference[config.command_name] = bounded_reference.copy()
                hold_mask = np.zeros_like(current, dtype=bool)
            else:
                bounded_reference = self._active_reference[config.command_name]
                position_mask = np.zeros_like(current, dtype=bool)
                hold_mask = np.ones_like(current, dtype=bool)

            effective_reference[config.command_name] = bounded_reference.copy()
            elapsed_s = self.config.control_interval_s
            alpha = 1.0 - np.exp(-elapsed_s / channel.time_constant_s)
            requested_delta = alpha * (bounded_reference - current)
            maximum_delta = channel.rate_limit_per_s * elapsed_s
            rate_mask = np.abs(requested_delta) > maximum_delta
            applied_delta = np.clip(
                requested_delta, -maximum_delta, maximum_delta
            )
            next_value_unclipped = current + applied_delta
            next_value = np.clip(
                next_value_unclipped, channel.minimum, channel.maximum
            )
            position_mask = position_mask | (
                next_value != next_value_unclipped
            )
            self._state[config.applied_name] = next_value


            position_masks[config.command_name] = position_mask.copy()
            rate_masks[config.command_name] = rate_mask.copy()
            hold_masks[config.command_name] = hold_mask.copy()
            combined_masks.append(position_mask | rate_mask)

        self._step_index += 1
        return ActuatorStepResult(
            applied_control={name: value.copy() for name, value in self._state.items()},
            effective_reference=effective_reference,
            position_saturation_mask=position_masks,
            rate_saturation_mask=rate_masks,
            hold_mask=hold_masks,
            action_saturation_mask=np.stack(combined_masks, axis=-1),
        )

    @property
    def applied_control(self) -> Mapping[str, np.ndarray]:
        """Return a defensive copy of the current applied state."""

        if self._leading_shape is None:
            raise RuntimeError("ActuatorModel has not been reset")
        return {name: value.copy() for name, value in self._state.items()}
