"""Private inference transfer: old network coordinates, new physical speed rule."""
from copy import deepcopy
from dataclasses import replace
import math

import numpy as np

from ..environments.maddpg_farm_env import MADDPGFarmEnv
from ..utils.actuator_model import ActuatorModel
from .controllers import PitchController

SCHEMA = "nrel_speed_transfer_old_coordinates_v1"
RADIUS_M = 63.
LAMBDA_REF = 7.55
SLOPE = LAMBDA_REF/RADIUS_M
LOW = 6.9*2*math.pi/60
HIGH = 1.267
OLD_LOW = .6
OLD_SLOPE = .11114035087719298
MID = (OLD_LOW+HIGH)/2
HALF = (HIGH-OLD_LOW)/2
# The physical reference decoded from float32 must also satisfy the exact low bound.
LOW_ACTION = np.float32((LOW-MID)/HALF)
if MID+float(LOW_ACTION)*HALF < LOW:
    LOW_ACTION = np.nextafter(LOW_ACTION, np.float32(np.inf))


def base_reference(effective_wind):
    wind = np.asarray(effective_wind, dtype=np.float64)
    if not np.isfinite(wind).all() or np.any(wind <= 0):
        raise ValueError("positive finite effective wind required")
    return np.clip(SLOPE*wind, LOW, HIGH)


def physical_speed(action):
    return MID+np.asarray(action, dtype=np.float64)*HALF


def speed_action(physical):
    value = np.asarray(physical, dtype=np.float64)
    if not np.isfinite(value).all():
        raise ValueError("finite physical speed required")
    action = ((np.clip(value, LOW, HIGH)-MID)/HALF).astype(np.float32)
    return np.clip(action, LOW_ACTION, np.float32(1.))


class SpeedTransferEnv(MADDPGFarmEnv):
    def __init__(self, plant, config, rule):
        if rule not in ("legacy", "nrel"):
            raise ValueError("explicit transfer rule required")
        cfg = deepcopy(config)
        if (cfg["action_low"][2], cfg["action_high"][2], cfg["speed_reference_mode"]) != (
                OLD_LOW, HIGH, "observation_float32_v1"):
            raise ValueError("frozen old observation and command coordinates required")
        self.rule = rule
        if rule == "nrel":
            cfg["reference_schedule"]["speed_per_wind_rad_m"] = SLOPE
        super().__init__(plant, cfg)
        if rule == "nrel":
            channels = [replace(c, minimum=LOW) if i == 2 else c
                        for i, c in enumerate(self.actuator.config.channels)]
            self.actuator = ActuatorModel(replace(self.actuator.config, channels=channels))

    def project_action(self, action):
        result = super().project_action(action)
        if self.rule == "nrel":
            result[:, 2] = np.clip(result[:, 2], LOW_ACTION, np.float32(1.))
        return result

    def normalization(self):
        return super().normalization() | dict(transfer_schema=SCHEMA, rule=self.rule,
            network_speed_coordinates_rad_s=[OLD_LOW, HIGH],
            executed_speed_bounds_rad_s=[LOW if self.rule == "nrel" else OLD_LOW, HIGH],
            command_penalty_coordinates="unchanged_old_normalized_total_commands",
            execution_reference_mode="effective_wind_physical_float64" if self.rule == "nrel"
                                     else "original_observation_float32_v1")


class FrozenTransfer:
    """Adapt only the physical speed reference after frozen deployment inference."""
    def __init__(self, raw, env):
        self.raw, self.env = raw, env
        self.active = False
        self.episodes = raw.episodes
        self.steps = raw.steps
        self.draws = raw.draws
        self.updates = raw.updates
        for name in ("heads", "critics", "target_heads", "target_critics", "speed_heads"):
            getattr(raw, name).requires_grad_(False)

    def features(self, observed):
        return self.raw.features(observed)

    def speed_z(self, obs, forecast):
        return self.raw.speed_z(obs, forecast)

    def z(self, obs, forecast, *, target=False):
        return self.raw.z(obs, forecast, target=target)

    def compose(self, obs, speed_z, yaw_z, bounds):
        action, fixed_C, pitch_parent = self.raw.compose(obs, speed_z, yaw_z, bounds)
        if self.env.rule == "nrel":
            base = base_reference(self.env.effective_wind)
            speed = speed_action(base+.1*np.asarray(speed_z, dtype=np.float64))
            action[:, 2] = speed
            fixed_C[:, 2] = speed
        return action, fixed_C, pitch_parent

    def update(self, *args, **kwargs):
        raise ValueError("frozen migration supports inference only")


class TransferPPI:
    def __init__(self, env, config, mode):
        self.env = env
        self.feedback = PitchController(env, config, mode)

    def act(self, obs):
        action = self.feedback.act(obs)
        if self.env.rule == "nrel":
            action[:, 2] = speed_action(base_reference(self.env.effective_wind))
        return self.env.project_action(action)
