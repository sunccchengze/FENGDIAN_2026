"""简化单机风机环境：Cp 经验公式 + 一阶转速动力学，供 PPO 链路回归测试。"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces


class SimplifiedTurbineEnv(gym.Env):
    """NREL 5MW 简化单机环境（解析公式版，供 PPO 功率跟踪训练）
    状态: [P, omega, beta, U, P_target]（功率 W / 转速 rad/s / 桨距角 deg / 风速 m/s / 目标功率 W）
    动作: [d_beta, d_omega]（桨距角变化 deg / 转速设定变化 rad/s）
    奖励: 跟踪误差惩罚 + 按动作上限归一化的动作增量惩罚
    动力学: omega 一阶惯性跟踪设定值（tau 秒）；beta 直接累计；P 由 Cp 稳态公式计算
    """

    metadata = {"render_modes": []}

    def __init__(self, seed: int = 42, dt: float = 1.0, tau: float = 5.0,
                 wind_profile: str = "step", target_profile: str = "step"):
        super().__init__()
        self.rng = np.random.default_rng(seed)
        self.dt = dt                      # 步长 s
        self.tau = tau                    # 转速惯性时间常数 s
        self.wind_profile = wind_profile  # step / sine / random
        self.target_profile = target_profile

        # NREL 5MW 参数
        self.rho = 1.225                  # 空气密度 kg/m^3
        self.R = 63.0                     # 叶轮半径 m
        self.A = np.pi * self.R**2        # 扫风面积 m^2
        self.P_rated = 5e6                # 额定功率 W
        self.omega_rated = 12.1 * np.pi / 30.0   # 额定转速 rad/s (12.1 rpm)
        self.beta_min, self.beta_max = 0.0, 25.0 # 桨距角范围 deg
        self.omega_min, self.omega_max = 0.1, self.omega_rated
        self.d_beta_max = 0.5             # 每步桨距角最大变化 deg
        self.d_omega_max = 0.1            # 每步转速设定最大变化 rad/s

        # 奖励权重
        self.lam = 0.1                    # 动作平滑惩罚系数
        self.power_scale = (1e6) ** 2     # 功率误差归一化尺度

        # 观测/动作空间（观测已归一化到 ~[0,1]）
        self.obs_scale = np.array([self.P_rated, self.omega_max, self.beta_max, 12.0, self.P_rated], dtype=np.float32)
        self.observation_space = spaces.Box(low=np.zeros(5, dtype=np.float32),
                                            high=np.ones(5, dtype=np.float32), dtype=np.float32)
        self.action_space = spaces.Box(low=np.array([-self.d_beta_max, -self.d_omega_max], dtype=np.float32),
                                       high=np.array([self.d_beta_max, self.d_omega_max], dtype=np.float32),
                                       dtype=np.float32)

        self.ep_len = 200
        self._reset_state()

    def _reset_state(self):
        self.t = 0
        self.beta = 2.0
        self.omega = 0.9 * self.omega_rated
        self.omega_set = self.omega
        self.U = 8.0
        self.P_target = self._target_power()
        self.P = self._calc_power()

    def _calc_power(self):
        """稳态功率: P = 0.5*rho*A*Cp(lambda,beta)*U^3，限额定"""
        lam = self.omega * self.R / max(self.U, 0.01)
        cp = self._cp(lam, self.beta)
        return min(0.5 * self.rho * self.A * cp * self.U**3, self.P_rated)

    @staticmethod
    def _cp(lam, beta):
        """Cp 经验公式（Heier 1996）"""
        lam = np.maximum(lam, 1e-6)
        beta = np.maximum(beta, 0.0)
        lam_i = 1.0 / (1.0 / (lam + 0.08 * beta) - 0.035 / (beta**3 + 1.0))
        cp = 0.5176 * (116.0 / lam_i - 0.4 * beta - 5.0) * np.exp(-21.0 / lam_i) + 0.0068 * lam
        return max(cp, 0.0)

    def _wind_speed(self):
        """风速 profile: 阶跃/正弦/随机，8±2 m/s"""
        if self.wind_profile == "sine":
            return 8.0 + 2.0 * np.sin(2 * np.pi * self.t / 80.0)
        if self.wind_profile == "random":
            return float(np.clip(8.0 + self.rng.normal(0, 0.8), 4.0, 12.0))
        return 8.0 if self.t < self.ep_len // 2 else 9.5  # 阶跃

    def _target_power(self):
        """功率指令：当前风况最大可发功率的 80%→65%（降载跟踪，始终可达）"""
        p_max = self._P_max(self.U)
        if self.target_profile == "sine":
            return p_max * (0.8 - 0.15 * (0.5 + 0.5 * np.sin(2 * np.pi * self.t / 60.0)))
        return p_max * (0.8 if self.t < self.ep_len // 2 else 0.65)

    @staticmethod
    def _P_max(U: float) -> float:
        """当前风况下最大可发功率（最优叶尖速比 λ≈7.5、桨距 0）"""
        cp_max = SimplifiedTurbineEnv._cp(7.5, 0.0)
        p = 0.5 * 1.225 * np.pi * 63.0**2 * cp_max * U**3
        return min(p, 5e6)

    def reset(self, *, seed=None, options=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action):
        raw_action = np.asarray(action, dtype=np.float64)
        if raw_action.shape != (2,):
            raise ValueError(f"action shape must be (2,), got {raw_action.shape}")
        applied_action = np.clip(raw_action, self.action_space.low, self.action_space.high)
        d_beta, d_omega = float(applied_action[0]), float(applied_action[1])
        # 桨距角累计（限幅）
        self.beta = np.clip(self.beta + d_beta, self.beta_min, self.beta_max)
        # 转速设定累计 + 一阶惯性（秒级动态）
        self.omega_set = np.clip(self.omega_set + d_omega, self.omega_min, self.omega_max)
        self.omega += (self.omega_set - self.omega) * (self.dt / self.tau)
        # 风况与指令更新
        self.U = self._wind_speed()
        self.P_target = self._target_power()
        self.P = self._calc_power()
        self.t += 1

        # 奖励：跟踪误差 + 动作平滑
        track_err = (self.P_target - self.P) ** 2 / self.power_scale
        action_limits = np.array([self.d_beta_max, self.d_omega_max], dtype=np.float64)
        normalized_action = applied_action / action_limits
        smooth = self.lam * float(np.mean(normalized_action**2))
        reward = -(track_err + smooth)
        terminated = self.t >= self.ep_len
        truncated = False
        info = {
            "tracking_penalty": float(track_err),
            "action_penalty": float(smooth),
            "applied_action": applied_action.astype(np.float32),
            "action_was_clipped": bool(np.any(raw_action != applied_action)),
        }
        return self._obs(), float(reward), terminated, truncated, info

    def _obs(self):
        return (np.array([self.P, self.omega, self.beta, self.U, self.P_target], dtype=np.float32) / self.obs_scale)

    def render(self):
        pass


if __name__ == "__main__":
    # 自检：随机动作跑两个完整 episode，检查观测、奖励和终止边界。
    env = SimplifiedTurbineEnv(seed=42)
    total_r = 0.0
    for episode in range(2):
        obs, _ = env.reset(seed=42 + episode)
        assert env.observation_space.contains(obs), obs
        for step in range(env.ep_len):
            obs, r, term, trunc, info = env.step(env.action_space.sample())
            total_r += r
            assert env.observation_space.contains(obs), obs
            assert term == (step == env.ep_len - 1)
            assert not trunc
            assert info["action_penalty"] >= 0.0
    print(f"自检通过：2 个完整 episode，累计奖励 {total_r:.2f}")
