"""Causal, headroom-preserving and ramp-limited farm power references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .action_mapper import ParameterSource


@dataclass(frozen=True)
class ReferencePowerConfig:
    """Physical configuration of :class:`ReferencePowerGenerator`.

    No project-wide physical defaults are supplied.  Values used before the
    simulation group freezes them must carry ``source.kind='assumption'`` (or
    ``test`` in unit tests) and later be covered by sensitivity analysis.
    """

    control_interval_s: float
    headroom_fraction: float
    low_pass_time_constant_s: float
    ramp_up_limit_w_s: float
    ramp_down_limit_w_s: float
    source: ParameterSource

    def __post_init__(self) -> None:
        finite_positive = {
            "control_interval_s": self.control_interval_s,
            "low_pass_time_constant_s": self.low_pass_time_constant_s,
            "ramp_up_limit_w_s": self.ramp_up_limit_w_s,
            "ramp_down_limit_w_s": self.ramp_down_limit_w_s,
        }
        for name, value in finite_positive.items():
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not np.isfinite(self.headroom_fraction) or not 0.0 <= self.headroom_fraction < 1.0:
            raise ValueError("headroom_fraction must lie in [0, 1)")


@dataclass(frozen=True)
class ReferencePowerStepResult:
    """Reference value plus filter/ramp/availability diagnostics."""

    reference_power_w: np.ndarray
    headroom_limited_power_w: np.ndarray
    filtered_power_w: np.ndarray
    ramp_up_limited_mask: np.ndarray
    ramp_down_limited_mask: np.ndarray
    availability_clip_mask: np.ndarray


class ReferencePowerGenerator:
    """Generate a feasible reference from an exogenous available-power estimate.

    The recursion uses only the current/past available power and prior internal
    states.  It is therefore causal.  The current implementation applies:

    ``available -> headroom -> first-order low-pass -> asymmetric ramp limits``.

    If available power collapses faster than the configured down-ramp, the final
    reference is clipped to current headroom-limited availability.  Feasibility
    wins over the ramp target and ``availability_clip_mask`` records the event.
    """

    def __init__(self, config: ReferencePowerConfig):
        self.config = config
        self._filtered_power_w: np.ndarray | None = None
        self._reference_power_w: np.ndarray | None = None

    @staticmethod
    def _available_array(available_power_w: Any) -> np.ndarray:
        available = np.asarray(available_power_w, dtype=np.float64)
        if not np.all(np.isfinite(available)):
            raise ValueError("available_power_w contains NaN or Inf")
        if np.any(available < 0.0):
            raise ValueError("available_power_w must be non-negative")
        return available.copy()

    def _headroom_target(self, available_power_w: np.ndarray) -> np.ndarray:
        return (1.0 - self.config.headroom_fraction) * available_power_w

    def reset(
        self,
        initial_available_power_w: Any,
        initial_reference_power_w: Any | None = None,
    ) -> ReferencePowerStepResult:
        """Reset filter and ramp memory for a new episode.

        By default the episode starts at the current headroom-limited feasible
        operating point.  An explicit initial reference must already be feasible.
        """

        available = self._available_array(initial_available_power_w)
        target = self._headroom_target(available)
        if initial_reference_power_w is None:
            reference = target.copy()
        else:
            reference = np.asarray(initial_reference_power_w, dtype=np.float64)
            if reference.shape != target.shape:
                raise ValueError(
                    "initial_reference_power_w must match initial_available_power_w shape"
                )
            if not np.all(np.isfinite(reference)):
                raise ValueError("initial_reference_power_w contains NaN or Inf")
            if np.any(reference < 0.0) or np.any(reference > target):
                raise ValueError(
                    "initial_reference_power_w must lie between zero and the "
                    "headroom-limited available power"
                )
            reference = reference.copy()

        self._filtered_power_w = target.copy()
        self._reference_power_w = reference.copy()
        false_mask = np.zeros_like(target, dtype=bool)
        return ReferencePowerStepResult(
            reference_power_w=reference.copy(),
            headroom_limited_power_w=target.copy(),
            filtered_power_w=target.copy(),
            ramp_up_limited_mask=false_mask.copy(),
            ramp_down_limited_mask=false_mask.copy(),
            availability_clip_mask=false_mask.copy(),
        )

    def step(self, available_power_w: Any) -> ReferencePowerStepResult:
        """Advance the causal reference generator by one control interval."""

        if self._filtered_power_w is None or self._reference_power_w is None:
            raise RuntimeError("ReferencePowerGenerator.reset must be called before step")
        available = self._available_array(available_power_w)
        if available.shape != self._reference_power_w.shape:
            raise ValueError(
                f"available_power_w shape changed from {self._reference_power_w.shape} "
                f"to {available.shape}"
            )

        target = self._headroom_target(available)
        alpha = 1.0 - np.exp(
            -self.config.control_interval_s / self.config.low_pass_time_constant_s
        )
        filtered = self._filtered_power_w + alpha * (target - self._filtered_power_w)

        requested_delta = filtered - self._reference_power_w
        maximum_up = self.config.ramp_up_limit_w_s * self.config.control_interval_s
        maximum_down = self.config.ramp_down_limit_w_s * self.config.control_interval_s
        ramp_up_mask = requested_delta > maximum_up
        ramp_down_mask = requested_delta < -maximum_down
        ramped = self._reference_power_w + np.clip(
            requested_delta, -maximum_down, maximum_up
        )
        feasible = np.clip(ramped, 0.0, target)
        availability_clip_mask = feasible != ramped

        self._filtered_power_w = filtered.copy()
        self._reference_power_w = feasible.copy()
        return ReferencePowerStepResult(
            reference_power_w=feasible.copy(),
            headroom_limited_power_w=target.copy(),
            filtered_power_w=filtered.copy(),
            ramp_up_limited_mask=ramp_up_mask.copy(),
            ramp_down_limited_mask=ramp_down_mask.copy(),
            availability_clip_mask=availability_clip_mask.copy(),
        )

    @property
    def reference_power_w(self) -> np.ndarray:
        """Return a defensive copy of the current reference."""

        if self._reference_power_w is None:
            raise RuntimeError("ReferencePowerGenerator has not been reset")
        return self._reference_power_w.copy()
