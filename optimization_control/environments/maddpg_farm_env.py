"""Three-agent quasi-static dispatch tracking with optimizer-owned actuators."""

from __future__ import annotations

import numpy as np
from gymnasium import spaces

from .plant_model import AppliedOperatingPoint, DisturbanceBatch
from ..utils.action_mapper import ActionMapper, ActionMapperConfig, ActionChannelConfig, ParameterSource
from ..utils.actuator_model import ActuatorModel, ActuatorModelConfig, ActuatorChannelConfig

COMMANDS = ("yaw_misalignment_reference_rad", "collective_pitch_reference_rad", "rotor_speed_reference_rad_s")
APPLIED = ("applied_yaw_misalignment_rad", "applied_collective_pitch_rad", "applied_rotor_speed_operating_point_rad_s")
OBSERVATIONS = ("power_fraction", "effective_wind_scaled", "yaw_scaled", "pitch_scaled", "speed_scaled",
                "previous_yaw_action", "previous_pitch_action", "previous_speed_action",
                "farm_target_fraction", "farm_error_fraction", "ambient_wind_scaled",
                "wind_direction_sin", "wind_direction_cos", "turbulence_intensity", "remaining_fraction")


def wrap_angle(angle):
    return (np.asarray(angle) + np.pi) % (2*np.pi) - np.pi


class MADDPGFarmEnv:
    """Array multi-agent API: observations [3,15], actions [3,3], rewards [3].

    Finite horizon is part of the task (remaining time is observed), so the
    final transition is terminated, not an artificial time-limit truncation.
    All three actors receive the same cooperative reward. No future wind is exposed.
    """

    def __init__(self, plant, config):
        self.plant, self.config = plant, dict(config)
        if len(plant.turbine_ids) != 3:
            raise ValueError("MADDPG requires exactly three turbines")
        self.rated = np.asarray(plant.rated_power_w, dtype=np.float64)
        self.dt = float(config["dt_s"])
        self.horizon = int(config["horizon"])
        self.wind_scale = float(config["wind_scale_m_s"])
        if self.dt <= 0 or not np.isfinite(self.dt) or self.horizon <= 0 or self.wind_scale <= 0:
            raise ValueError("invalid environment time/scaling")
        self.low = np.asarray(config["action_low"], dtype=float)
        self.high = np.asarray(config["action_high"], dtype=float)
        self.initial = np.asarray(config["initial_operating_point"], dtype=float)
        self.heading_mode = config.get("yaw_frame", "legacy_misalignment") == "nacelle_heading"
        if config.get("yaw_frame", "legacy_misalignment") not in ("nacelle_heading", "legacy_misalignment"):
            raise ValueError("unknown yaw frame")
        if config.get("inflow") and not self.heading_mode:
            raise ValueError("random inflow requires nacelle_heading yaw frame")
        raw_mask = np.asarray(config.get("control_mask", [1, 1, 1]))
        self.control_mask = raw_mask.astype(bool)
        if raw_mask.shape != (3,) or not np.all(np.isin(raw_mask, [0, 1])) or not self.control_mask[1]:
            raise ValueError("control_mask needs three channels and active pitch")
        if not np.isfinite(config.get("reward_scale", 1.0)) or config.get("reward_scale", 1.0) <= 0:
            raise ValueError("reward_scale must be finite and positive")
        if self.low.shape != (3,) or self.high.shape != (3,) or self.initial.shape != (3,):
            raise ValueError("action bounds and initial point must each have three channels")
        source = ParameterSource(**config["parameter_source"])
        channels = [ActionChannelConfig(n, self.low[k], self.high[k], ("rad", "rad", "rad/s")[k], source)
                    for k, n in enumerate(COMMANDS)]
        self.mapper = ActionMapper(ActionMapperConfig(3, channels))
        self.actuator_commands = (("nacelle_heading_reference_rad",) + COMMANDS[1:]) if self.heading_mode else COMMANDS
        self.actuator_applied = (("applied_nacelle_heading_rad",) + APPLIED[1:]) if self.heading_mode else APPLIED
        heading_bounds = config.get("heading_bounds_rad", [-100*np.pi, 100*np.pi])
        self.actuator = ActuatorModel(ActuatorModelConfig(3, self.dt, source, [
            ActuatorChannelConfig(self.actuator_commands[k], self.actuator_applied[k],
                                  heading_bounds[0] if k == 0 and self.heading_mode else self.low[k],
                                  heading_bounds[1] if k == 0 and self.heading_mode else self.high[k],
                                  config["rate_limits"][k], config["time_constants_s"][k],
                                  1, 0.0, ("rad", "rad", "rad/s")[k], source) for k in range(3)]))
        self.action_space = spaces.Box(-1, 1, (3, 3), dtype=np.float32)
        self.observation_space = spaces.Box(-np.inf, np.inf, (3, len(OBSERVATIONS)), dtype=np.float32)
        self._done = True

    def normalization(self):
        result = {"features": list(OBSERVATIONS), "rated_power_w": self.rated.tolist(),
                "wind_scale_m_s": self.wind_scale, "action_low": self.low.tolist(),
                "action_high": self.high.tolist(), "method": "fixed_physical_scales_no_running_statistics"}
        if self.heading_mode:
            result.update(yaw_frame="nacelle_heading", control_mask=self.control_mask.tolist())
        return result

    def project_action(self, action):
        fixed = self.normalize_commands(np.tile(self.initial, (3, 1)))
        return np.where(self.control_mask, action, fixed).astype(np.float32)

    def normalize_commands(self, physical):
        physical = np.asarray(physical)
        return self.mapper.normalize_physical({n: physical[:, k] for k, n in enumerate(COMMANDS)}).normalized_action.astype(np.float32)

    def reset(self, *, seed=42, options=None):
        options = dict(options or {})
        self.rng = np.random.default_rng(seed)
        self.t = 0
        self._done = False
        self.target = float(options.get("target_w", self.config["target_w"]))
        if not np.isfinite(self.target) or not 0 < self.target <= self.rated.sum():
            raise ValueError("target must be positive and at most farm rating; feasibility is not guaranteed")
        self.wind_base = float(options.get("wind_base_m_s", self.config["wind_base_m_s"]))
        self.trajectory = options.get("wind_trajectory")
        self.wind_metadata = {}
        self.inflow_trace = None
        if self.trajectory is not None and options.get("wind_trace_path") is not None:
            raise ValueError("choose either wind_trajectory or wind_trace_path")
        if options.get("wind_trace_path") is not None:
            from .farm_inflow import InflowTrace
            trace = InflowTrace.load(options["wind_trace_path"])
            if not np.isclose(trace.metadata["dt_s"], self.dt):
                raise ValueError("inflow time step mismatch")
            self.trajectory, self.wind_metadata = trace.values, trace.metadata
            self.inflow_trace = trace
        elif self.trajectory is None and self.config.get("inflow"):
            from .farm_inflow import generate_inflow
            inflow_config = dict(self.config["inflow"])
            for key, value in options.get("inflow", {}).items():
                inflow_config[key] = dict(inflow_config.get(key, {}), **value)
            trace = generate_inflow(inflow_config, dt_s=self.dt, horizon=self.horizon,
                                    seed=seed, split=options.get("split", "train"),
                                    episode=options.get("episode", 0))
            self.trajectory, self.wind_metadata = trace.values, trace.metadata
            self.inflow_trace = trace
        if self.trajectory is not None:
            self.trajectory = np.asarray(self.trajectory, dtype=np.float32)
            if self.trajectory.shape != (self.horizon + 1, 3) or not np.all(np.isfinite(self.trajectory)):
                raise ValueError("wind_trajectory must be finite [horizon+1,3]: speed,direction,TI")
            # Check every disturbance before starting, not midway after training updates.
            for k, name in enumerate(("ambient_wind_speed_m_s", "ambient_wind_direction_rad", "turbulence_intensity")):
                if name in self.plant.bounds:
                    lo, hi = self.plant.bounds[name]
                    if np.any((self.trajectory[:, k] < lo) | (self.trajectory[:, k] > hi)):
                        raise ValueError(f"inflow outside PINN domain: {name}")
        self._read_wind()
        physical = np.tile(self.initial, (3, 1))
        actuator_state = physical.copy()
        if self.heading_mode:
            actuator_state[:, 0] += self.wind[1]
        self.actuator.reset({n: actuator_state[:, k] for k, n in enumerate(self.actuator_applied)})
        self.previous_action = self.normalize_commands(physical)
        self.last_action_change = self.saturation_fraction = 0.0
        self.reward_terms = {"tracking": 0.0, "action_change": 0.0}
        self._query(read_wind=False)
        return self._observe(), self._info()

    def _read_wind(self):
        if self.trajectory is None:
            wind = self.wind_base + self.config["wind_amplitude_m_s"] * np.sin(2*np.pi*self.t/self.config["wind_period_steps"])
            wind += self.rng.normal(0, self.config["wind_noise_std_m_s"])
            direction, ti = self.config["wind_direction_rad"], self.config["turbulence_intensity"]
        else:
            wind, direction, ti = self.trajectory[self.t]
        self.wind = np.asarray([wind, direction, ti], dtype=np.float32)

    def _query(self, read_wind=True):
        if read_wind:
            self._read_wind()
        disturbance = DisturbanceBatch(*(np.array([[v]], dtype=np.float32) for v in self.wind))
        self.applied = np.stack([self.actuator.applied_control[n] for n in self.actuator_applied], axis=1)
        self.heading = self.applied[:, 0].copy() if self.heading_mode else self.applied[:, 0] + self.wind[1]
        if self.heading_mode:
            self.applied[:, 0] = wrap_angle(self.heading - self.wind[1])
        operating = AppliedOperatingPoint(self.plant.turbine_ids, *(self.applied[:, k][None, :] for k in range(3)))
        out = self.plant.predict_steady(disturbance, operating)
        if not bool(np.all(out.in_domain)):
            raise ValueError("plant reports out-of-domain condition")
        self.power = out.floris_turbine_power_w[0].copy()
        self.effective_wind = out.effective_wind_speed_m_s[0].copy()

    def _observe(self):
        applied_scaled = 2*(self.applied-self.low)/(self.high-self.low)-1
        globals_ = [self.target/self.rated.sum(), (self.power.sum()-self.target)/self.rated.sum(),
                    self.wind[0]/self.wind_scale, np.sin(self.wind[1]), np.cos(self.wind[1]),
                    self.wind[2], 1-self.t/self.horizon]
        return np.column_stack((self.power/self.rated, self.effective_wind/self.wind_scale,
                                applied_scaled, self.previous_action, np.tile(globals_, (3, 1)))).astype(np.float32)

    def _info(self):
        return {"step": self.t, "time_s": self.t*self.dt, "target_w": self.target,
                "farm_power_w": float(self.power.sum()), "power_w": self.power.copy(),
                "effective_wind_m_s": self.effective_wind.copy(), "applied": self.applied.copy(),
                "wind": self.wind.copy(), "error_w": float(self.power.sum()-self.target),
                "saturation_fraction": self.saturation_fraction, "action_change": self.last_action_change,
                "reward_terms": dict(self.reward_terms), "source": getattr(self.plant, "source", "unknown"),
                "power_semantics": getattr(self.plant, "power_semantics", "unspecified"),
                "heading_rad": self.heading.copy(), "executed_action": self.previous_action.copy(),
                "steady_feasibility": "not_certified"}

    def step(self, actions):
        if self._done:
            raise RuntimeError("reset required before step")
        a = np.asarray(actions, dtype=np.float32)
        if a.shape != (3, 3) or not np.all(np.isfinite(a)):
            raise ValueError("actions must be finite [3,3]")
        mapped = self.mapper.map(self.project_action(a))
        commands = {self.actuator_commands[k]: mapped.commanded_control[n].copy() for k, n in enumerate(COMMANDS)}
        if self.heading_mode:
            commands[self.actuator_commands[0]] = self.heading + wrap_angle(
                self.wind[1] + commands[self.actuator_commands[0]] - self.heading)
        result = self.actuator.step(commands)
        executed = mapped.clipped_action_normalized.astype(np.float32)
        self.last_action_change = float(np.mean((executed-self.previous_action)**2))
        self.saturation_fraction = float(np.mean(result.action_saturation_mask | mapped.action_saturation_mask))
        self.previous_action = executed
        self.t += 1
        self._query()
        error = (self.power.sum()-self.target)/self.rated.sum()
        self.reward_terms = {"tracking": -float(error**2),
                             "action_change": -self.config["action_change_weight"]*self.last_action_change}
        reward = self.config.get("reward_scale", 1.0) * sum(self.reward_terms.values())
        self._done = self.t >= self.horizon
        return self._observe(), np.full(3, reward, dtype=np.float32), self._done, False, self._info()
