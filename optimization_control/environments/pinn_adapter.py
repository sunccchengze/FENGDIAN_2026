"""Versioned, named PINN features mapped to the fixed six-output contract."""

from __future__ import annotations

from typing import Callable, Mapping
import numpy as np

from .plant_model import AppliedOperatingPoint, DisturbanceBatch, SteadyPlantOutput

CONTROL_FEATURES = tuple(f"{name}_{i}" for name in ("gamma", "beta", "omega") for i in (1, 2, 3))
DEFAULT_FEATURES = ("ambient_wind_speed_m_s", "ambient_wind_direction_rad", "turbulence_intensity") + CONTROL_FEATURES


class PINNAdapter:
    """Predictor receives normalized [B,D]; returns normalized [B,6].

    Bounds refer to physical, encoded inputs before normalization. They must
    cover every configured feature; they do not prove model accuracy in-domain.
    Additional changing conditions can be supplied by extra_provider(d, op).
    """

    def __init__(self, predictor: Callable, *, features=DEFAULT_FEATURES,
                 turbine_ids=("T01", "T02", "T03"), rated_power_w=(5e6, 5e6, 5e6),
                 bounds: Mapping, input_mean=None, input_scale=None,
                 output_mean=None, output_scale=None, constants=None,
                 extra_provider=None, source="pinn", power_semantics=None):
        self.features = tuple(features)
        if len(set(self.features)) != len(self.features) or not set(CONTROL_FEATURES) <= set(self.features):
            raise ValueError("unique features must include all nine control operating points")
        self.turbine_ids = tuple(turbine_ids)
        if len(self.turbine_ids) != 3 or len(set(self.turbine_ids)) != 3:
            raise ValueError("exactly three ordered turbine IDs required")
        self.rated_power_w = np.asarray(rated_power_w, dtype=np.float32)
        if self.rated_power_w.shape != (3,) or not np.all(np.isfinite(self.rated_power_w)) or np.any(self.rated_power_w <= 0):
            raise ValueError("rated_power_w must contain three positive finite values")
        if not power_semantics or not source:
            raise ValueError("explicit source and power_semantics required")
        self.source, self.power_semantics = source, power_semantics
        self.model_kind = "quasi_static"
        self.predictor, self.extra_provider = predictor, extra_provider
        self.constants = dict(constants or {})
        self.bounds = dict(bounds)
        if set(bounds) != set(self.features):
            raise ValueError("physical input bounds must cover exactly the configured features")
        limits = np.asarray([bounds[n] for n in self.features], dtype=np.float32)
        if limits.shape != (len(self.features), 2) or not np.all(np.isfinite(limits)) or np.any(limits[:, 0] >= limits[:, 1]):
            raise ValueError("invalid input bounds")
        self.low, self.high = limits[:, 0], limits[:, 1]
        self.input_mean = self._vector(input_mean, len(self.features), 0)
        self.input_scale = self._vector(input_scale, len(self.features), 1, positive=True)
        self.output_mean = self._vector(output_mean, 6, 0)
        self.output_scale = self._vector(output_scale, 6, 1, positive=True)

    @staticmethod
    def _vector(value, size, default, positive=False):
        a = np.full(size, default, dtype=np.float32) if value is None else np.asarray(value, dtype=np.float32)
        if a.shape != (size,) or not np.all(np.isfinite(a)) or (positive and np.any(a <= 0)):
            raise ValueError("invalid normalization vector")
        return a

    def encode(self, disturbance, operating_point):
        if operating_point.turbine_ids != self.turbine_ids or disturbance.batch_size != operating_point.batch_size:
            raise ValueError("PINN turbine ordering or batch mismatch")
        values = {n: getattr(disturbance, n)[:, 0] for n in DEFAULT_FEATURES[:3]}
        direction = values["ambient_wind_direction_rad"]
        values.update(wind_direction_sin=np.sin(direction), wind_direction_cos=np.cos(direction))
        for prefix, a in zip(("gamma", "beta", "omega"), (
                operating_point.applied_yaw_misalignment_rad,
                operating_point.applied_collective_pitch_rad,
                operating_point.applied_rotor_speed_operating_point_rad_s)):
            values.update({f"{prefix}_{i+1}": a[:, i] for i in range(3)})
        extras = dict(self.constants)
        if self.extra_provider is not None:
            supplied = dict(self.extra_provider(disturbance, operating_point))
            if set(supplied) & set(extras):
                raise ValueError("extra provider cannot overwrite constants")
            extras.update(supplied)
        if set(extras) & set(values):
            raise ValueError("extra features cannot overwrite authoritative wind/control fields")
        values.update(extras)
        missing = set(self.features) - set(values)
        if missing:
            raise ValueError(f"missing PINN inputs: {sorted(missing)}")
        columns = []
        for n in self.features:
            a = np.asarray(values[n], dtype=np.float32)
            if a.ndim == 0:
                a = np.full(disturbance.batch_size, a, dtype=np.float32)
            if a.shape != (disturbance.batch_size,) or not np.all(np.isfinite(a)):
                raise ValueError(f"invalid feature {n}; expected scalar or [B]")
            columns.append(a)
        return np.stack(columns, axis=1)

    def predict_steady(self, disturbance: DisturbanceBatch, applied_operating_point: AppliedOperatingPoint):
        x = self.encode(disturbance, applied_operating_point)
        if np.any(x < self.low) or np.any(x > self.high):
            raise ValueError("PINN input outside configured valid domain; no silent extrapolation")
        raw = np.asarray(self.predictor((x - self.input_mean) / self.input_scale), dtype=np.float32)
        if raw.shape != (x.shape[0], 6) or not np.all(np.isfinite(raw)):
            raise ValueError("PINN must return finite [B,6] in P1,P2,P3,Ueff1,Ueff2,Ueff3 order")
        y = raw * self.output_scale + self.output_mean
        if not np.all(np.isfinite(y)) or np.any(y < 0):
            raise ValueError("PINN physical outputs must be finite and non-negative")
        if np.any(y[:, :3] > self.rated_power_w * 1.001):
            raise ValueError("PINN power exceeds configured rating")
        return SteadyPlantOutput(
            turbine_ids=self.turbine_ids, floris_turbine_power_w=y[:, :3],
            floris_farm_power_sum_w=y[:, :3].sum(axis=1, keepdims=True),
            effective_wind_speed_m_s=y[:, 3:], in_domain=np.ones((len(x), 1), dtype=bool),
            ood_score=np.zeros((len(x), 1), dtype=np.float32))


class CoupledIntegrationPredictor:
    """Uncalibrated toy coupling, ONLY for exercising the 12 -> 6 pipeline.

    Fixed index order represents upstream to downstream. No layout, direction,
    turbulence or physical wake dynamics are resolved by this test model.
    """

    def __init__(self, rated_power_w):
        self.rated = np.asarray(rated_power_w, dtype=np.float32)

    def __call__(self, x):
        if x.shape[1] != 12:
            raise ValueError("integration predictor requires DEFAULT_FEATURES and identity scaling")
        yaw, pitch, speed = x[:, 3:6], x[:, 6:9], x[:, 9:12]
        wind = np.repeat(x[:, :1], 3, axis=1)
        power = np.zeros_like(wind)
        for i in range(3):
            optimum = np.clip(wind[:, i] / 11.4 * 1.267, 0.2, 1.267)
            extraction = np.exp(-pitch[:, i] / 0.21) * np.exp(-0.5 * ((speed[:, i] - optimum) / 0.45)**2)
            power[:, i] = self.rated[i] * np.clip((wind[:, i] / 11.4)**3, 0, 1) * np.cos(yaw[:, i])**2 * extraction
            for j in range(i + 1, 3):
                wind[:, j] *= 1 - (0.12 / (j-i)) * extraction * np.cos(yaw[:, i])**2
        return np.concatenate((power, wind), axis=1).astype(np.float32)
