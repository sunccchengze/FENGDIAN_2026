"""Versioned finite-horizon single turbine task with causal references.

Empirical Cp plus actuator lag: not a validated NREL aeroelastic model.
Reward uses next-state power and the reference observed before taking the action.
"""
from copy import deepcopy

import gymnasium as gym
import numpy as np

from optimization_control.environments.simplified_turbine_env import SimplifiedTurbineEnv
from optimization_control.environments.wind_generator import WindConfig, generate_wind
from optimization_control.utils.action_mapper import ParameterSource
from optimization_control.utils.reference_power import ReferencePowerConfig, ReferencePowerGenerator


class StochasticTurbineEnv(SimplifiedTurbineEnv):
    observation_names = ("power_w", "rotor_speed_rad_s", "pitch_deg", "wind_speed_m_s",
                         "reference_power_w", "rotor_speed_setpoint_rad_s",
                         "filtered_reference_w", "remaining_fraction")

    def __init__(self, config, *, seed=42, split="train", worker=0, trace=None):
        self.config_v2 = deepcopy(config)
        self.wind_config = WindConfig(**config["wind"])
        self.master_seed, self.split, self.worker = seed, split, worker
        self.episode_index = 0
        self.replay_trace = trace
        super().__init__(seed=seed, dt=self.wind_config.dt_s, tau=float(config["environment"]["rotor_tau_s"]))
        if not np.isfinite(self.tau) or self.tau <= 0:
            raise ValueError("rotor_tau_s must be positive")
        self.ep_len = self.wind_config.steps
        self.obs_scale = np.array([self.P_rated, self.omega_max, self.beta_max,
                                  self.wind_config.speed_max_m_s, self.P_rated,
                                  self.omega_max, self.P_rated, 1.0], dtype=np.float32)
        self.observation_space = gym.spaces.Box(0.0, 1.0, shape=(8,), dtype=np.float32)
        reference = dict(config["reference"])
        self.reference = ReferencePowerGenerator(ReferencePowerConfig(
            control_interval_s=self.dt, **reference,
            source=ParameterSource("assumption", "stochastic_wind_v1.yaml")))
        self._finished = True
        self._omega_grid = np.linspace(self.omega_min, self.omega_max, 128)[:, None]
        self._beta_grid = np.linspace(self.beta_min, self.beta_max, 101)[None, :]

    @staticmethod
    def _cp_array(lam, beta):
        inverse = 1 / (lam + 0.08 * beta) - 0.035 / (beta**3 + 1)
        cp = 0.5176 * (116 * inverse - 0.4 * beta - 5) * np.exp(-21 * inverse) + 0.0068 * lam
        return np.maximum(cp, 0)

    def available_power(self, wind):
        """Feasible sampled steady upper operating point; not dynamic reachability."""
        cp = self._cp_array(self._omega_grid * self.R / wind, self._beta_grid)
        return float(min(self.P_rated, 0.5 * self.rho * self.A * np.max(cp) * wind**3))

    def reset(self, *, seed=None, options=None):
        gym.Env.reset(self, seed=seed)
        if seed is not None:
            self.master_seed, self.episode_index = int(seed), 0
        if options:
            raise ValueError("use explicit trace injection for replay")
        self.trace = self.replay_trace or generate_wind(
            self.wind_config, seed=self.master_seed, split=self.split,
            worker=self.worker, episode=self.episode_index)
        self.trace.__post_init__()
        if len(self.trace.time_s) != self.ep_len + 1 or not np.allclose(
                np.diff(self.trace.time_s), self.dt):
            raise ValueError("replay trace timing differs from environment")
        if np.any(self.trace.speed_m_s > self.wind_config.speed_max_m_s):
            raise ValueError("replay wind exceeds observation scale")
        self.episode_index += 1
        self.t, self.beta = 0, 2.0
        self.omega = self.omega_set = 0.9 * self.omega_rated
        self.U = float(self.trace.speed_m_s[0])
        self.P = self._calc_power()
        result = self.reference.reset(np.array([self.available_power(self.U)]))
        self.P_target = float(result.reference_power_w[0])
        self.filtered_reference = float(result.filtered_power_w[0])
        self._finished = False
        return self._obs(), {"wind_metadata": deepcopy(self.trace.metadata)}

    def step(self, action):
        if self._finished:
            raise RuntimeError("reset required before stepping or after episode end")
        raw = np.asarray(action, dtype=float)
        if raw.shape != (2,) or not np.all(np.isfinite(raw)):
            raise ValueError("action must have two finite values")
        applied = np.clip(raw, self.action_space.low, self.action_space.high)
        target_applied = self.P_target
        # Existing limits are per second; preserve their rate when dt changes.
        self.beta = float(np.clip(self.beta + applied[0] * self.dt, self.beta_min, self.beta_max))
        self.omega_set = float(np.clip(self.omega_set + applied[1] * self.dt, self.omega_min, self.omega_max))
        self.omega += (self.omega_set - self.omega) * (1 - np.exp(-self.dt / self.tau))
        self.t += 1
        self.U = float(self.trace.speed_m_s[self.t])
        self.P = self._calc_power()
        available = self.available_power(self.U)
        tracking = (target_applied - self.P)**2 / self.power_scale
        action_penalty = self.lam * float(np.mean((applied / self.action_space.high)**2))
        result = self.reference.step(np.array([available]))
        self.P_target = float(result.reference_power_w[0])
        self.filtered_reference = float(result.filtered_power_w[0])
        self._finished = self.t == self.ep_len
        info = {
            "power_w": self.P, "reference_applied_w": target_applied,
            "reference_next_w": self.P_target, "available_power_w": available,
            "wind_speed_m_s": self.U, "time_s": self.t * self.dt,
            "tracking_penalty": float(tracking), "action_penalty": action_penalty,
            "applied_action": applied.astype(np.float32),
            "action_was_clipped": bool(np.any(raw != applied)),
            "reference_availability_clipped": bool(result.availability_clip_mask[0]),
            "target_exceeds_steady_availability": bool(target_applied > available),
            "pitch_deg": self.beta, "rotor_speed_rad_s": self.omega,
        }
        return self._obs(), -float(tracking + action_penalty), self._finished, False, info

    def _obs(self):
        return np.array([self.P, self.omega, self.beta, self.U, self.P_target,
                         self.omega_set, self.filtered_reference,
                         1 - self.t / self.ep_len], dtype=np.float32) / self.obs_scale
