# -*- coding: utf-8 -*-
"""
Simplified Wind Turbine Power Tracking Environment
Author: Hong Zuming
"""
import numpy as np

class SimplifiedTurbineEnv:
    def __init__(self, u_inf=8.0, p_max=5000.0):
        self.u_inf = u_inf
        self.p_max = p_max
        self.yaw = 0.0
        self.target_p = 1800.0
        
    def reset(self, target_p=1800.0, u_inf=8.0):
        self.target_p = target_p
        self.u_inf = u_inf
        self.yaw = 0.0
        return self._get_obs()
        
    def step(self, action_delta_yaw):
        self.yaw = float(np.clip(self.yaw + action_delta_yaw, -30.0, 30.0))
        # Power model: P = P_base * cos^1.88(yaw)
        p_base = 0.5 * 1.225 * (np.pi * 63**2) * 0.45 * (self.u_inf**3) / 1000.0
        p_act = p_base * (np.cos(np.radians(self.yaw)) ** 1.88)
        
        # Reward
        reward = - abs(p_act - self.target_p) - 0.05 * abs(action_delta_yaw)
        done = False
        info = {"power_actual": p_act, "yaw": self.yaw, "error": abs(p_act - self.target_p)}
        return self._get_obs(), reward, done, info
        
    def _get_obs(self):
        # 契约对齐（汇报接口文档：State = [u_inf, yaw_current, power_current, target_power]）：
        # 原包实现缺 power_current（3 维），2026-08-10 复现修复补齐为 4 维。
        p_act = 0.5 * 1.225 * (np.pi * 63**2) * 0.45 * (self.u_inf**3) / 1000.0 \
            * (np.cos(np.radians(self.yaw)) ** 1.88)
        return np.array([self.u_inf, self.yaw, p_act, self.target_p], dtype=np.float32)
