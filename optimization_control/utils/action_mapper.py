"""Map normalized policy actions to named physical reference commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class ParameterSource:
    """Provenance for physical values used by an optimization-side model.

    ``kind`` should normally be one of ``simulation``, ``manufacturer``,
    ``team_decision``, ``assumption`` or ``test``.  Assumed values remain
    explicit so that they cannot silently become accepted turbine parameters.
    """

    kind: str
    reference: str
    note: str = ""

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("ParameterSource.kind must be non-empty")
        if not self.reference.strip():
            raise ValueError("ParameterSource.reference must be non-empty")

    @property
    def is_assumption(self) -> bool:
        return self.kind.lower() == "assumption"


@dataclass(frozen=True)
class ActionChannelConfig:
    """Configuration of one policy action channel.

    ``physical_min`` and ``physical_max`` may be scalars shared by all turbines
    or length-``N`` arrays.  No turbine-specific physical default is provided.
    """

    name: str
    physical_min: Any
    physical_max: Any
    unit: str
    source: ParameterSource
    control_mode: str = "absolute_reference"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("action channel name must be non-empty")
        if not self.unit.strip():
            raise ValueError(f"unit is required for action channel {self.name!r}")
        if self.control_mode != "absolute_reference":
            raise ValueError(
                "only control_mode='absolute_reference' is implemented; "
                f"got {self.control_mode!r} for {self.name!r}"
            )


@dataclass(frozen=True)
class ActionMapperConfig:
    """Static action layout for a fixed turbine layout."""

    turbine_count: int
    channels: Sequence[ActionChannelConfig]

    def __post_init__(self) -> None:
        if self.turbine_count <= 0:
            raise ValueError("turbine_count must be positive")
        if not self.channels:
            raise ValueError("at least one action channel is required")
        names = [channel.name for channel in self.channels]
        if len(names) != len(set(names)):
            raise ValueError(f"action channel names must be unique: {names}")


@dataclass(frozen=True)
class ActionMappingResult:
    """Result of a normalized-to-physical action mapping."""

    commanded_control: Mapping[str, np.ndarray]
    clipped_action_normalized: np.ndarray
    action_saturation_mask: np.ndarray

@dataclass(frozen=True)
class ActionNormalizationResult:
    """Result of converting named physical references back to policy space."""

    normalized_action: np.ndarray
    clipped_commanded_control: Mapping[str, np.ndarray]
    physical_saturation_mask: np.ndarray


class ActionMapper:
    """Convert PPO actions in ``[-1, 1]`` to physical absolute references.

    Input shape is ``[..., N, A]`` where ``N`` is the configured turbine count
    and ``A`` follows ``config.channels``.  Leading dimensions (for example a
    vectorized-environment batch) are preserved.  Values outside ``[-1, 1]``
    are explicitly clipped and reported in ``action_saturation_mask``.
    """

    def __init__(self, config: ActionMapperConfig):
        self.config = config
        self.channel_names = tuple(channel.name for channel in config.channels)
        self._minimum = np.stack(
            [self._per_turbine(channel.physical_min, channel.name) for channel in config.channels],
            axis=-1,
        )
        self._maximum = np.stack(
            [self._per_turbine(channel.physical_max, channel.name) for channel in config.channels],
            axis=-1,
        )
        if np.any(self._minimum >= self._maximum):
            raise ValueError("every action channel must satisfy physical_min < physical_max")

    def _per_turbine(self, value: Any, name: str) -> np.ndarray:
        array = np.asarray(value, dtype=np.float64)
        if array.ndim == 0:
            if not np.isfinite(array):
                raise ValueError(f"{name} bounds must be finite")
            return np.full(self.config.turbine_count, float(array), dtype=np.float64)
        if array.shape != (self.config.turbine_count,):
            raise ValueError(
                f"{name} bounds must be scalar or shape "
                f"({self.config.turbine_count},), got {array.shape}"
            )
        if not np.all(np.isfinite(array)):
            raise ValueError(f"{name} bounds must be finite")
        return array.astype(np.float64, copy=True)

    def map(self, action_normalized: Any) -> ActionMappingResult:
        """Map normalized actions to a dictionary of physical commands."""

        action = np.asarray(action_normalized, dtype=np.float64)
        expected_tail = (self.config.turbine_count, len(self.config.channels))
        if action.ndim < 2 or action.shape[-2:] != expected_tail:
            raise ValueError(
                f"action_normalized must end with shape {expected_tail}, got {action.shape}"
            )
        if not np.all(np.isfinite(action)):
            raise ValueError("action_normalized contains NaN or Inf")

        saturation_mask = (action < -1.0) | (action > 1.0)
        clipped = np.clip(action, -1.0, 1.0)
        midpoint = (self._minimum + self._maximum) / 2.0
        half_range = (self._maximum - self._minimum) / 2.0
        physical = midpoint + clipped * half_range
        commands = {
            name: physical[..., channel_index].copy()
            for channel_index, name in enumerate(self.channel_names)
        }
        return ActionMappingResult(
            commanded_control=commands,
            clipped_action_normalized=clipped.copy(),
            action_saturation_mask=saturation_mask.copy(),
        )

    def normalize_physical(
        self, commanded_control: Mapping[str, Any]
    ) -> ActionNormalizationResult:
        """Convert named physical absolute references to normalized actions.

        Use this inverse to construct a "hold current setting" baseline.  In
        absolute-reference mode, a numeric zero action means the midpoint of
        each physical range, not a no-op.  Out-of-bound physical values are
        clipped and reported through ``physical_saturation_mask``.
        """

        expected = set(self.channel_names)
        received = set(commanded_control)
        if received != expected:
            raise ValueError(
                f"commanded_control keys must be {sorted(expected)}, got {sorted(received)}"
            )

        arrays = []
        leading_shape: tuple[int, ...] | None = None
        for name in self.channel_names:
            value = np.asarray(commanded_control[name], dtype=np.float64)
            if value.ndim < 1 or value.shape[-1] != self.config.turbine_count:
                raise ValueError(
                    f"{name} must end with turbine dimension "
                    f"({self.config.turbine_count},), got {value.shape}"
                )
            if not np.all(np.isfinite(value)):
                raise ValueError(f"{name} contains NaN or Inf")
            if leading_shape is None:
                leading_shape = value.shape[:-1]
            elif value.shape[:-1] != leading_shape:
                raise ValueError(
                    "all physical command channels must have the same leading shape"
                )
            arrays.append(value)

        physical = np.stack(arrays, axis=-1)
        saturation_mask = (physical < self._minimum) | (physical > self._maximum)
        clipped = np.clip(physical, self._minimum, self._maximum)
        midpoint = (self._minimum + self._maximum) / 2.0
        half_range = (self._maximum - self._minimum) / 2.0
        normalized = (clipped - midpoint) / half_range
        clipped_commands = {
            name: clipped[..., channel_index].copy()
            for channel_index, name in enumerate(self.channel_names)
        }
        return ActionNormalizationResult(
            normalized_action=normalized.copy(),
            clipped_commanded_control=clipped_commands,
            physical_saturation_mask=saturation_mask.copy(),
        )
