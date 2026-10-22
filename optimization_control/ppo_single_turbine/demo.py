"""T1 演示：输入目标功率 → PPO 输出桨距/转速 → 显示功率跟踪效果图
用法:
  python demo.py --target-fraction 0.8          # 目标 = 最大可发功率 × 0.8（固定）
  python demo.py --target-fraction 0.8 --step    # 目标阶跃 0.8 -> 0.65（第 100 步）
  python demo.py --target-power 2.0              # 绝对目标功率 2.0 MW（自动 clamp 到可发上限）
效果图输出: runs/demo_*.png（上=功率跟踪，中=桨距角，下=转速）+ 终端指标打印
"""

import argparse
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from gymnasium import spaces

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "environments"))
from simplified_turbine_env import SimplifiedTurbineEnv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train import Agent


DEFAULT_MODEL = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "models", "ppo", "ppo_tracking_v3_seed42.pt"))


def parse_args():
    p = argparse.ArgumentParser(description="单机 PPO 功率跟踪演示：输入目标功率，查看控制效果")
    p.add_argument("--model", type=str, default=DEFAULT_MODEL, help="训练好的 PPO 模型 (.pt)")
    p.add_argument("--target-fraction", type=float, default=None,
                   help="目标功率 = 当前风况最大可发功率 × 该比例（推荐 0.5~0.95）")
    p.add_argument("--target-power", type=float, default=None,
                   help="绝对目标功率 (MW)，若超过物理可发上限会自动 clamp 并提示")
    p.add_argument("--step", action="store_true", help="目标在中点阶跃（比例 -0.15），演示动态响应")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default="", help="效果图输出路径（默认 runs/demo_*.png）")
    p.add_argument(
        "--policy-format",
        choices=("legacy_unsquashed", "tanh_squashed"),
        default="legacy_unsquashed",
        help="默认模型是历史模型；新训练模型请显式传 tanh_squashed",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if args.target_fraction is None and args.target_power is None:
        args.target_fraction = 0.8
    if args.target_fraction is not None and not (0.05 <= args.target_fraction <= 0.95):
        raise ValueError("--target-fraction 需在 0.05~0.95 之间")

    env = SimplifiedTurbineEnv(seed=args.seed)
    p_max_fn = env._P_max
    if args.target_power is not None:
        p_target_w = args.target_power * 1e6
        p_max_now = p_max_fn(env.U)
        if p_target_w > p_max_now:
            print(f"⚠ 目标 {args.target_power:.2f} MW 超过当前风况最大可发 {p_max_now/1e6:.2f} MW，已 clamp")
            p_target_w = p_max_now

        def target_fn():
            return float(min(p_target_w, p_max_fn(env.U)))

    else:
        def target_fn():
            k = args.target_fraction
            if args.step and env.t >= env.ep_len // 2:
                k = max(k - 0.15, 0.1)
            return p_max_fn(env.U) * k

    env._target_power = target_fn

    # 加载 PPO 模型（与训练一致的网络结构）
    class Dummy:
        single_observation_space = spaces.Box(low=0, high=1, shape=(5,), dtype=np.float32)
        single_action_space = spaces.Box(
            low=env.action_space.low,
            high=env.action_space.high,
            dtype=np.float32,
        )

    agent = Agent(Dummy())
    agent.load_state_dict(torch.load(args.model, map_location="cpu", weights_only=True))
    agent.eval()

    # rollout
    obs, _ = env.reset()
    P_hist, Pt_hist, beta_hist, omega_hist = [], [], [], []
    for _ in range(env.ep_len):
        with torch.no_grad():
            tensor_obs = torch.as_tensor(obs).unsqueeze(0)
            if args.policy_format == "tanh_squashed":
                tensor_action = agent.get_deterministic_action(tensor_obs)
            else:
                tensor_action = agent.actor_mean(tensor_obs)
            a = tensor_action.squeeze(0).numpy()
            a = np.clip(a, env.action_space.low, env.action_space.high)
        obs, _, _, _, _ = env.step(a)
        P_hist.append(obs[0] * env.obs_scale[0])
        Pt_hist.append(obs[4] * env.obs_scale[4])
        beta_hist.append(obs[2] * env.obs_scale[2])
        omega_hist.append(obs[1] * env.obs_scale[1])

    P, Pt = np.array(P_hist), np.array(Pt_hist)
    rmse = np.sqrt(np.mean((P - Pt) ** 2)) / 1e3
    mae = np.mean(np.abs(P - Pt)) / 1e3
    print("=" * 56)
    print(f"目标设定: {args.target_fraction if args.target_fraction else args.target_power}"
          f"{' (比例)' if args.target_fraction else ' MW'}{' + 阶跃' if args.step else ''}")
    print(f"跟踪 RMSE = {rmse:.2f} kW | MAE = {mae:.2f} kW "
          f"（目标 ~{np.mean(Pt)/1e6:.2f} MW，相对误差 {100*mae/(np.mean(Pt)/1e3):.2f}%）")
    print(f"桨距角范围: {min(beta_hist):.1f}~{max(beta_hist):.1f}° | 转速范围: {min(omega_hist):.2f}~{max(omega_hist):.2f} rad/s")
    print(f"动作平滑度（桨距变化 std）: {np.std(np.diff(beta_hist)):.3f}°")

    # 效果图
    t = np.arange(len(P))
    fig, axes = plt.subplots(3, 1, figsize=(11, 9))
    axes[0].plot(t, Pt / 1e6, "k--", lw=2, label="P_target (电网指令)")
    axes[0].plot(t, P / 1e6, "C0", lw=1.5, label="PPO 实际功率")
    axes[0].fill_between(t, (Pt - np.abs(P - Pt)) / 1e6, (Pt + np.abs(P - Pt)) / 1e6, alpha=0.15, color="C0")
    axes[0].set_ylabel("功率 (MW)")
    axes[0].set_title(f"功率跟踪效果（RMSE={rmse:.1f} kW）")
    axes[0].legend()
    axes[1].plot(t, beta_hist, "C1")
    axes[1].set_ylabel("桨距角 β (°)")
    axes[1].set_title("PPO 输出的桨距角")
    axes[2].plot(t, omega_hist, "C2")
    axes[2].set_ylabel("转速 ω (rad/s)")
    axes[2].set_xlabel("时间步 t (s)")
    axes[2].set_title("PPO 输出的转速")
    fig.tight_layout()
    out = args.out or os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "runs",
        f"demo_{args.target_fraction if args.target_fraction is not None else args.target_power}{'_step' if args.step else ''}.png"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=120)
    print(f"效果图已保存: {out}")


if __name__ == "__main__":
    main()
