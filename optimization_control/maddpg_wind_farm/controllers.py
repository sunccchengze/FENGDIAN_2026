"""Fixed and scheduled yaw/speed plus P/PI pitch references; shared actuators."""

import numpy as np


class PitchController:
    """Farm-error pitch feedback with optional yaw and speed reference schedules.

    Positive power error increases feathering pitch. This sign must be verified
    for a real plant's supported operating range. PI uses tracking anti-windup
    against actual applied pitch to handle both position and rate saturation.
    """

    def __init__(self, env, config, mode):
        if mode not in ("fixed", "p", "pi"):
            raise ValueError("unknown baseline")
        self.env, self.config, self.mode = env, config, mode
        self.reset()

    def reset(self):
        self.integral = 0.0

    def act(self, obs):
        e = self.env
        physical = np.tile(e.initial, (3, 1))
        if self.mode == "fixed":
            return e.project_action(e.normalize_commands(physical))
        if self.config.get("three_channel", False):
            physical[:, 0] = self.config.get("yaw_offset_rad", 0.0)
            # Reference curve is an explicit integration assumption, not a rotor torque model.
            physical[:, 2] = np.clip(self.config["speed_per_wind_rad_m"] * e.effective_wind,
                                      e.low[2], e.high[2])
        error = float(obs[0, 9])
        pitch = self.config["pitch_bias_rad"] + self.config["kp"]*error + self.integral
        if self.mode == "pi":
            # Integrator has pitch units; update for the next control instant.
            actual = float(e.applied[:, 1].mean())
            self.integral += e.dt * (self.config["ki"]*error + self.config["antiwindup_gain"]*(actual-pitch))
            self.integral = float(np.clip(self.integral, -self.config["integral_limit_rad"], self.config["integral_limit_rad"]))
        physical[:, 1] = np.clip(pitch, e.low[1], e.high[1])
        return e.project_action(e.normalize_commands(physical))
