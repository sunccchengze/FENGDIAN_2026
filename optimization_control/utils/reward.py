"""Dimensionless, decomposed rewards for wind-farm power control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

import numpy as np

from .action_mapper import ParameterSource


@dataclass(frozen=True)
class RewardConfig:
    """Weights and physical normalization scales for reward calculation.

    Every value is explicit.  Setting a term's weight to zero disables it;
    otherwise the corresponding input to :meth:`RewardCalculator.calculate`
    is mandatory.  Action differences are already dimensionless because PPO
    actions are normalized before entering this class.
    """

    tracking_weight: float
    ramp_weight: float
    action_rate_weight: float
    load_weight: float
    constraint_weight: float
    ood_weight: float
    energy_weight: float
    tracking_error_scale_w: float
    ramp_violation_scale_w_s: float
    energy_scale_j: float
    source: ParameterSource

    def __post_init__(self) -> None:
        weights = {
            "tracking_weight": self.tracking_weight,
            "ramp_weight": self.ramp_weight,
            "action_rate_weight": self.action_rate_weight,
            "load_weight": self.load_weight,
            "constraint_weight": self.constraint_weight,
            "ood_weight": self.ood_weight,
            "energy_weight": self.energy_weight,
        }
        for name, value in weights.items():
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        scales = {
            "tracking_error_scale_w": self.tracking_error_scale_w,
            "ramp_violation_scale_w_s": self.ramp_violation_scale_w_s,
            "energy_scale_j": self.energy_scale_j,
        }
        for name, value in scales.items():
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class RewardResult:
    """Total reward and its signed, auditable components."""

    total: float | np.ndarray
    components: Mapping[str, float | np.ndarray]


class RewardCalculator:
    """Calculate tracking, ramp, action, safety, OOD and energy terms.

    The return components are already signed: penalties are non-positive and
    the optional energy term is non-negative.  Inputs can be unbatched
    (actions ``[N,A]``) or batched (actions ``[B,N,A]``).
    """

    def __init__(self, config: RewardConfig):
        self.config = config

    @staticmethod
    def _finite_array(value: Any, name: str) -> np.ndarray:
        array = np.asarray(value, dtype=np.float64)
        if not np.all(np.isfinite(array)):
            raise ValueError(f"{name} contains NaN or Inf")
        return array

    @staticmethod
    def _mean_per_sample(value: np.ndarray, batched: bool) -> float | np.ndarray:
        if not batched:
            return float(np.mean(value))
        if value.ndim == 0:
            raise ValueError("batched reward input cannot be scalar")
        if value.ndim == 1:
            return value
        return np.mean(value, axis=tuple(range(1, value.ndim)))

    @staticmethod
    def _require_shape(value: np.ndarray, expected: tuple[int, ...], name: str) -> None:
        if value.shape != expected:
            raise ValueError(f"{name} must have shape {expected}, got {value.shape}")

    @classmethod
    def _mean_square_per_sample(cls, value: np.ndarray, batched: bool) -> float | np.ndarray:
        return cls._mean_per_sample(np.square(value), batched)

    @staticmethod
    def _require_optional(value: Any | None, weight: float, name: str) -> Any | None:
        if weight > 0.0 and value is None:
            raise ValueError(f"{name} is required because its reward weight is non-zero")
        return value

    def calculate(
        self,
        *,
        farm_power_w: Any,
        power_reference_w: Any,
        action_normalized: Any,
        previous_action_normalized: Any,
        farm_power_ramp_w_s: Any | None = None,
        ramp_limit_w_s: Any | None = None,
        load_penalty_normalized: Any | None = None,
        constraint_violation: Any | None = None,
        ood_mask: Any | None = None,
        interval_energy_j: Any | None = None,
    ) -> RewardResult:
        """Return a scalar reward or one reward per leading batch item."""

        action = self._finite_array(action_normalized, "action_normalized")
        previous_action = self._finite_array(
            previous_action_normalized, "previous_action_normalized"
        )
        if action.shape != previous_action.shape or action.ndim not in (2, 3):
            raise ValueError(
                "current and previous actions must have identical [N,A] or [B,N,A] shape"
            )
        batched = action.ndim == 3
        farm_power = self._finite_array(farm_power_w, "farm_power_w")
        batch_size = action.shape[0] if batched else None
        turbine_count = action.shape[-2]
        power_shape = (batch_size, 1) if batched else (1,)
        turbine_shape = (
            (batch_size, turbine_count) if batched else (turbine_count,)
        )
        reference = self._finite_array(power_reference_w, "power_reference_w")
        self._require_shape(farm_power, power_shape, "farm_power_w")
        self._require_shape(reference, power_shape, "power_reference_w")

        tracking_error = (reference - farm_power) / self.config.tracking_error_scale_w
        tracking = -self.config.tracking_weight * self._mean_square_per_sample(
            tracking_error, batched
        )
        action_rate = -self.config.action_rate_weight * self._mean_square_per_sample(
            action - previous_action, batched
        )

        self._require_optional(farm_power_ramp_w_s, self.config.ramp_weight, "farm_power_ramp_w_s")
        self._require_optional(ramp_limit_w_s, self.config.ramp_weight, "ramp_limit_w_s")
        if self.config.ramp_weight > 0.0:
            ramp = self._finite_array(farm_power_ramp_w_s, "farm_power_ramp_w_s")
            limit = self._finite_array(ramp_limit_w_s, "ramp_limit_w_s")
            self._require_shape(ramp, power_shape, "farm_power_ramp_w_s")
            self._require_shape(limit, power_shape, "ramp_limit_w_s")
            if np.any(limit < 0.0):
                raise ValueError("ramp_limit_w_s must be non-negative")
            violation = np.maximum(np.abs(ramp) - limit, 0.0)
            ramp_term = -self.config.ramp_weight * self._mean_square_per_sample(
                violation / self.config.ramp_violation_scale_w_s, batched
            )
        else:
            ramp_term = np.zeros(action.shape[0], dtype=np.float64) if batched else 0.0

        self._require_optional(
            load_penalty_normalized, self.config.load_weight, "load_penalty_normalized"
        )
        if self.config.load_weight > 0.0:
            load = self._finite_array(load_penalty_normalized, "load_penalty_normalized")
            self._require_shape(load, turbine_shape, "load_penalty_normalized")
            load_term = -self.config.load_weight * self._mean_square_per_sample(load, batched)
        else:
            load_term = np.zeros(action.shape[0], dtype=np.float64) if batched else 0.0

        self._require_optional(
            constraint_violation, self.config.constraint_weight, "constraint_violation"
        )
        if self.config.constraint_weight > 0.0:
            constraint = self._finite_array(constraint_violation, "constraint_violation")
            self._require_shape(constraint, action.shape, "constraint_violation")
            if np.any(constraint < 0.0):
                raise ValueError("constraint_violation must be non-negative")
            constraint_term = -self.config.constraint_weight * self._mean_per_sample(
                constraint, batched
            )
        else:
            constraint_term = np.zeros(action.shape[0], dtype=np.float64) if batched else 0.0

        self._require_optional(ood_mask, self.config.ood_weight, "ood_mask")
        if self.config.ood_weight > 0.0:
            ood = self._finite_array(ood_mask, "ood_mask")
            self._require_shape(ood, power_shape, "ood_mask")
            if np.any(ood < 0.0):
                raise ValueError("ood_mask must be non-negative/bool")
            ood_term = -self.config.ood_weight * self._mean_per_sample(ood, batched)
        else:
            ood_term = np.zeros(action.shape[0], dtype=np.float64) if batched else 0.0

        self._require_optional(interval_energy_j, self.config.energy_weight, "interval_energy_j")
        if self.config.energy_weight > 0.0:
            energy_array = self._finite_array(interval_energy_j, "interval_energy_j")
            self._require_shape(energy_array, power_shape, "interval_energy_j")
            if np.any(energy_array < 0.0):
                raise ValueError("interval_energy_j must be non-negative")
            energy_term = self.config.energy_weight * self._mean_per_sample(
                energy_array / self.config.energy_scale_j, batched
            )
        else:
            energy_term = np.zeros(action.shape[0], dtype=np.float64) if batched else 0.0

        components: Dict[str, float | np.ndarray] = {
            "tracking": tracking,
            "ramp": ramp_term,
            "action_rate": action_rate,
            "load": load_term,
            "constraint": constraint_term,
            "ood": ood_term,
            "energy": energy_term,
        }
        total = sum(components.values())
        if isinstance(total, np.ndarray):
            total = total.astype(np.float64, copy=False)
        else:
            total = float(total)
        return RewardResult(total=total, components=components)
