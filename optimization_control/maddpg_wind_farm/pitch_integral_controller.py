"""Private frozen-policy wrapper; no learning, future input or actuator bypass."""
from __future__ import annotations
import numpy as np


class FrozenPitchIntegral:
    LIMIT = .02

    def __init__(self, env, parent, baseline_config, *, enabled=True):
        self.env, self.parent, self.enabled = env, parent, enabled
        self.ki = float(baseline_config['ki'])
        if self.ki != .08 or env.dt != 1. or float(np.sum(env.rated)) != 15e6:
            raise ValueError('frozen PI units do not match the approved mapping')
        if not np.array_equal(env.low[[1]], [0.]) or not np.array_equal(env.high[[1]], [.22]):
            raise ValueError('frozen pitch bounds required')
        self.reset()

    def reset(self):
        self.integral = 0.
        self.last = None

    def act(self, obs):
        raw = self.parent.act(obs)  # The parent's own mapping observes this hybrid loop.
        current = self.integral
        beta = (raw[:, 1].astype(np.float64) + 1.) * .11
        error = float(obs[0, 9])
        increment = self.env.dt * self.ki * error if self.enabled else 0.
        desired = beta + current
        blocked = bool((increment > 0 and (current >= self.LIMIT or np.any(desired >= .22))) or
                       (increment < 0 and (current <= -self.LIMIT or np.any(desired <= 0.))))
        following = current if blocked else float(np.clip(current + increment, -self.LIMIT, self.LIMIT))
        action = raw.copy()
        if current != 0.:
            action[:, 1] = np.clip(raw[:, 1].astype(np.float64) + 2*current/.22, -1., 1.).astype(np.float32)
        self.integral = following
        self.last = dict(integral_used_rad=current, integral_next_rad=following,
                         decision_error_normalized=error, integral_increment_rad=increment,
                         integral_blocked=int(blocked), total_target_clipped_units=int(np.sum((desired < 0) | (desired > .22))))
        assert np.array_equal(action[:, [0, 2]], raw[:, [0, 2]])
        return action
