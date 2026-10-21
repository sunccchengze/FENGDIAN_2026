"""T1-R：训练好的 PPO 与 PController 基线的 episode 级功率跟踪评估。"""

import argparse
import os
import sys

import numpy as np
import torch
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "environments"))
from simplified_turbine_env import SimplifiedTurbineEnv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train import Agent


class PController:
    """比例控制基线：根据功率误差调整桨距，转速设定保持不变。"""

    def __init__(self, kp: float = 2e-6, obs_scale=None):
        self.kp = kp
        default_scale = [5e6, 1.27, 25.0, 12.0, 5e6]
        self.scale = np.asarray(obs_scale if obs_scale is not None else default_scale)

    def act(self, obs: np.ndarray) -> np.ndarray:
        power, _, _, _, target_power = obs * self.scale
        power_error = target_power - power
        # 当前工作域中 dP/d_beta < 0：欠发时减小桨距，超发时增大桨距。
        d_beta = float(np.clip(-self.kp * power_error, -0.5, 0.5))
        return np.array([d_beta, 0.0], dtype=np.float32)


def finite_difference_pitch_sensitivity(
    env: SimplifiedTurbineEnv, epsilon_deg: float = 1e-3
) -> float:
    """在当前状态用有限差分估计 dP/d_beta，且不改变环境状态。"""
    if epsilon_deg <= 0:
        raise ValueError("epsilon_deg must be positive")
    original_beta = env.beta
    beta_plus = min(original_beta + epsilon_deg, env.beta_max)
    beta_minus = max(original_beta - epsilon_deg, env.beta_min)
    if beta_plus == beta_minus:
        raise ValueError("finite-difference points collapse at the pitch boundary")
    try:
        env.beta = beta_plus
        power_plus = env._calc_power()
        env.beta = beta_minus
        power_minus = env._calc_power()
    finally:
        env.beta = original_beta
    return float((power_plus - power_minus) / (beta_plus - beta_minus))


def validate_p_controller_direction(
    env: SimplifiedTurbineEnv, controller: PController, seed: int = 42
) -> float:
    """确认比例控制动作在初始工作点会把功率推向目标。"""
    obs, _ = env.reset(seed=seed)
    sensitivity = finite_difference_pitch_sensitivity(env)
    if sensitivity >= 0:
        raise RuntimeError(f"expected dP/d_beta < 0, got {sensitivity:.3f} W/deg")
    power, _, _, _, target_power = obs * env.obs_scale
    power_error = target_power - power
    pitch_action = float(controller.act(obs)[0])
    predicted_power_change = sensitivity * pitch_action
    if abs(power_error) > 1.0 and predicted_power_change * power_error <= 0:
        raise RuntimeError("PController pitch action moves power away from the target")
    return sensitivity


def rollout(env, agent=None, controller=None, n_episodes=1, policy_format="tanh_squashed"):
    """按完整 episode 评估；遇到 terminated/truncated 后停止并在下一轮 reset。"""
    scale = env.obs_scale
    if (agent is None) == (controller is None):
        raise ValueError("provide exactly one of agent or controller")
    if n_episodes <= 0:
        raise ValueError("n_episodes must be positive")
    power_hist, target_hist, action_hist = [], [], []
    for _ in range(n_episodes):
        obs, _ = env.reset()
        max_steps = int(getattr(env, "ep_len", 10_000)) + 1
        for _ in range(max_steps):
            if agent is not None:
                with torch.no_grad():
                    observation = torch.as_tensor(obs).unsqueeze(0)
                    if policy_format == "tanh_squashed":
                        tensor_action = agent.get_deterministic_action(observation)
                    elif policy_format == "legacy_unsquashed":
                        tensor_action = agent.actor_mean(observation)
                    else:
                        raise ValueError(f"unknown policy_format: {policy_format}")
                    action = tensor_action.squeeze(0).cpu().numpy()
                    action = np.clip(action, env.action_space.low, env.action_space.high)
            else:
                action = controller.act(obs)
            next_obs, _, terminated, truncated, info = env.step(action)
            applied_action = info.get("applied_action", action)
            power_hist.append(next_obs[0] * scale[0])
            target_hist.append(next_obs[4] * scale[4])
            action_hist.append(applied_action)
            obs = next_obs
            if terminated or truncated:
                break
        else:
            raise RuntimeError("environment did not end within its declared episode length")
    return np.array(power_hist), np.array(target_hist), np.array(action_hist)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, required=True, help="训练好的 .pt 模型路径")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--episodes", type=int, default=1, help="独立评估 episode 数")
    ap.add_argument("--out", type=str, default="")
    ap.add_argument(
        "--policy-format",
        choices=("tanh_squashed", "legacy_unsquashed"),
        required=True,
        help="新训练模型用 tanh_squashed；2026-08-08 历史模型用 legacy_unsquashed",
    )
    args = ap.parse_args()

    device = torch.device("cpu")
    # 直接加载 state_dict 需要正确的网络结构：用 dummy 构建
    import gymnasium as gym
    from gymnasium import spaces

    class Dummy:
        single_observation_space = spaces.Box(low=0, high=1, shape=(5,), dtype=np.float32)
        single_action_space = spaces.Box(
            low=np.array([-0.5, -0.1], dtype=np.float32),
            high=np.array([0.5, 0.1], dtype=np.float32),
            dtype=np.float32,
        )

    agent = Agent(Dummy()).to(device)
    agent.load_state_dict(torch.load(args.model, map_location=device, weights_only=True))
    agent.eval()

    env_ppo = SimplifiedTurbineEnv(seed=args.seed)
    env_p = SimplifiedTurbineEnv(seed=args.seed)
    controller = PController(obs_scale=env_p.obs_scale)
    sensitivity = validate_p_controller_direction(env_p, controller, seed=args.seed)
    print(f"有限差分 dP/d_beta={sensitivity:.1f} W/deg（负值，控制方向已校验）")
    P_ppo, Pt_ppo, A_ppo = rollout(
        env_ppo,
        agent=agent,
        n_episodes=args.episodes,
        policy_format=args.policy_format,
    )
    P_p, Pt_p, A_p = rollout(env_p, controller=controller, n_episodes=args.episodes)

    def metrics(P, Pt, A):
        rmse = np.sqrt(np.mean((P - Pt) ** 2)) / 1e3  # kW
        mae = np.mean(np.abs(P - Pt)) / 1e3
        act_std = np.std(A[:, 0])  # 桨距角动作标准差
        return rmse, mae, act_std

    r_ppo, m_ppo, s_ppo = metrics(P_ppo, Pt_ppo, A_ppo)
    r_p, m_p, s_p = metrics(P_p, Pt_p, A_p)
    print("=" * 50)
    print(f"PPO: 跟踪RMSE={r_ppo:.2f}kW MAE={m_ppo:.2f}kW 桨距动作std={s_ppo:.3f}")
    print(f"PController: 跟踪RMSE={r_p:.2f}kW MAE={m_p:.2f}kW 桨距动作std={s_p:.3f}")

    # 对比图
    fig, axes = plt.subplots(3, 1, figsize=(11, 10))
    t = np.arange(len(Pt_ppo))
    axes[0].plot(t, Pt_ppo / 1e6, "k--", label="P_target")
    axes[0].plot(t, P_ppo / 1e6, "C0", label="PPO")
    axes[0].plot(t, P_p / 1e6, "C3", alpha=0.8, label="PController")
    axes[0].set_ylabel("power (MW)")
    axes[0].legend(); axes[0].set_title("Power tracking")
    axes[1].plot(t, A_ppo[:, 0], "C0", label="PPO pitch action")
    axes[1].plot(t, A_p[:, 0], "C3", label="PController pitch action")
    axes[1].set_ylabel("d_beta (deg)")
    axes[1].legend(); axes[1].set_title("Pitch action")
    axes[2].plot(t, np.abs(P_ppo - Pt_ppo) / 1e3, "C0", label="PPO |err| kW")
    axes[2].plot(t, np.abs(P_p - Pt_p) / 1e3, "C3", label="PController |err| kW")
    axes[2].set_ylabel("|error| (kW)")
    axes[2].legend(); axes[2].set_title("Tracking error")
    fig.tight_layout()
    out = args.out or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "runs", "ppo_vs_p_controller.png"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=120)
    print("对比图:", out)
    plt.close(fig)
    env_ppo.close()
    env_p.close()


if __name__ == "__main__":
    main()
