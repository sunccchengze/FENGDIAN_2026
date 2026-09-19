# -*- coding: utf-8 -*-
"""PPO 功率跟踪 · 忠实复现训练脚本 v2（2026-08-10 审计重建）。

背景：原交付包 model/ppo_tracking_v3_seed42.pt 为 0 B 占位，train/eval/demo 三脚本
逐字节相同且不训练不加载权重。本脚本按汇报接口契约重建可复现训练管线。

显式假设（原包未声明、必须钉死）：
  1. dt = 0.1 s/step（env 无时间尺度；取偏航执行器常见量级），episode 200 步 = 20 s；
  2. 目标域：target_p ∈ [0.78, 0.98] × p_base(u_inf)，u_inf ~ U[6, 12] m/s。
     ±30° 偏航下理论下界 cos^1.88(30°)=0.763，留出控制裕量后取 0.78；
  3. 奖励严格沿用原结构 r = -|err| - 0.05|a|，整体缩放 1/100（正仿射变换，
     保 err:action 相对权重 2000:1，仅稳定数值，不改变最优策略）；
  4. 观测契约 4 维 [u_inf, yaw, power_current, target_power]，归一化供给网络
     （u/10, yaw/30, p/5000, t/5000）——v1 教训：数千 kW 裸值灌 tanh 致饱和；
  5. PPO：actor/critic 双 MLP(4→64→64)，高斯策略，动作截断 ±5°，seed=42。
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

HERE = Path(__file__).parent

U_LO, U_HI = 6.0, 12.0
RHO, R_AREA, CP = 1.225, np.pi * 63.0**2, 0.45
DT = 0.1            # s/step（假设 1）
HORIZON = 200       # 步/episode（=20 s）
YAW_LIM = 30.0
A_LIM = 5.0         # 动作域 ±5°（汇报契约）
TARGET_LO, TARGET_HI = 0.78, 0.98   # × p_base（物理可达域：yaw±30°下cos^1.88(30°)=0.763）
R_SCALE = 0.01      # 假设 3（奖励整体缩放）
ACTION_PEN = 0.05
OBS_SCALE = np.array([10.0, 30.0, 5000.0, 5000.0])   # 假设 4


def p_base_of(u):
    return 0.5 * RHO * R_AREA * CP * u**3 / 1000.0


class VecEnv:
    """向量化环境：物理与 simplified_turbine_env.py 严格一致（cos^1.88 模型）。"""

    def __init__(self, n, rng):
        self.n, self.rng = n, rng
        self.reset_all()

    def reset_all(self):
        self.u = self.rng.uniform(U_LO, U_HI, self.n)
        self.p_base = p_base_of(self.u)
        self.target = self.rng.uniform(TARGET_LO, TARGET_HI, self.n) * self.p_base
        self.yaw = np.zeros(self.n)
        self.t = np.zeros(self.n, dtype=int)
        return self.obs()

    def obs_raw(self):
        p = self.p_base * np.cos(np.radians(self.yaw)) ** 1.88
        return np.stack([self.u, self.yaw, p, self.target], 1)

    def obs(self):
        return (self.obs_raw() / OBS_SCALE).astype(np.float32)

    def step(self, a):
        self.yaw = np.clip(self.yaw + a, -YAW_LIM, YAW_LIM)
        p = self.p_base * np.cos(np.radians(self.yaw)) ** 1.88
        err = p - self.target
        r = (-np.abs(err) - ACTION_PEN * np.abs(a)) * R_SCALE   # 原结构整体缩放
        self.t += 1
        done = self.t >= HORIZON
        obs = self.obs()
        if done.any():  # 界内自重置，GAE 用 done 断点
            idx = np.where(done)[0]
            self.u[idx] = self.rng.uniform(U_LO, U_HI, len(idx))
            self.p_base[idx] = p_base_of(self.u[idx])
            self.target[idx] = self.rng.uniform(TARGET_LO, TARGET_HI, len(idx)) * self.p_base[idx]
            self.yaw[idx] = 0.0
            self.t[idx] = 0
        return obs, r.astype(np.float32), done, {"power_actual": p, "error": np.abs(err)}


class ActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        trunk = lambda: nn.Sequential(nn.Linear(4, 64), nn.Tanh(), nn.Linear(64, 64), nn.Tanh())
        self.pi = nn.Sequential(trunk(), nn.Linear(64, 1))
        self.v = nn.Sequential(trunk(), nn.Linear(64, 1))
        self.log_std = nn.Parameter(torch.full((1,), float(np.log(1.5))))

    def dist(self, obs):
        mean = self.pi(obs).squeeze(-1)
        return torch.distributions.Normal(mean, self.log_std.exp().expand_as(mean))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--envs", type=int, default=64)
    ap.add_argument("--rollout", type=int, default=64)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    env = VecEnv(args.envs, rng)
    net = ActorCritic()
    opt = torch.optim.Adam(net.parameters(), lr=3e-4)

    GAMMA, LAM, CLIP, EPOCHS = 0.99, 0.95, 0.2, 4
    T, N = args.rollout, args.envs
    t0 = time.time()
    obs = torch.tensor(env.obs())
    log = []
    for it in range(args.iters):
        mb_obs = torch.zeros(T, N, 4)
        mb_a = torch.zeros(T, N)
        mb_logp = torch.zeros(T, N)
        mb_r = torch.zeros(T, N)
        mb_done = torch.zeros(T, N)
        mb_v = torch.zeros(T, N)
        mb_err = torch.zeros(T, N)
        with torch.no_grad():
            for t in range(T):
                d = net.dist(obs)
                a = d.sample()
                logp = d.log_prob(a)
                v = net.v(obs).squeeze(-1)
                nobs, r, done, info = env.step(a.numpy().clip(-A_LIM, A_LIM))
                mb_obs[t], mb_a[t], mb_logp[t] = obs, a, logp
                mb_r[t] = torch.tensor(r)
                mb_done[t] = torch.tensor(done.astype(np.float32))
                mb_v[t] = v
                mb_err[t] = torch.tensor(info["error"])
                obs = torch.tensor(nobs)
        with torch.no_grad():
            next_v = net.v(obs).squeeze(-1)
        adv = torch.zeros(T, N)
        lastgae = torch.zeros(N)
        for t in reversed(range(T)):
            nonterminal = 1.0 - mb_done[t]
            nv = next_v if t == T - 1 else mb_v[t + 1]
            delta = mb_r[t] + GAMMA * nv * nonterminal - mb_v[t]
            lastgae = delta + GAMMA * LAM * nonterminal * lastgae
            adv[t] = lastgae
        ret = adv + mb_v
        b_obs = mb_obs.reshape(-1, 4)
        b_a = mb_a.reshape(-1)
        b_logp = mb_logp.reshape(-1)
        b_adv = adv.reshape(-1)
        b_ret = ret.reshape(-1)
        b_adv = (b_adv - b_adv.mean()) / (b_adv.std() + 1e-8)
        idx = np.arange(len(b_obs))
        for _ in range(EPOCHS):
            rng.shuffle(idx)
            for s in range(0, len(idx), 1024):
                j = torch.tensor(idx[s:s + 1024])
                d = net.dist(b_obs[j])
                logp = d.log_prob(b_a[j])
                ratio = (logp - b_logp[j]).exp()
                loss_pi = -torch.min(ratio * b_adv[j],
                                     torch.clamp(ratio, 1 - CLIP, 1 + CLIP) * b_adv[j]).mean()
                loss_v = ((net.v(b_obs[j]).squeeze(-1) - b_ret[j]) ** 2).mean()
                loss = loss_pi + 0.5 * loss_v
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()
        err_mean = float(mb_err.mean())
        log.append({"iter": it + 1, "abs_err_mean_kw": round(err_mean, 2)})
        if (it + 1) % 50 == 0 or it == 0:
            print(f"iter {it+1:3d}/{args.iters}  abs_err_mean={err_mean:8.1f} kW  "
                  f"(std={net.log_std.exp().item():.3f}°)")

    wall = time.time() - t0
    out = HERE / "model" / "ppo_tracking_v3_seed42.pt"
    torch.save({
        "state_dict": net.state_dict(),
        "meta": {
            "obs": "[u_inf, yaw, power_current, target_power] (4-dim)",
            "obs_scale": OBS_SCALE.tolist(),
            "action": "delta_yaw in [-5, +5] deg", "hidden": 64, "dt": DT,
            "horizon": HORIZON, "u_inf_range": [U_LO, U_HI],
            "target_range_pct_p_base": [TARGET_LO, TARGET_HI],
            "reward": "-|err| - 0.05|a|, x0.01 scale",
            "seed": args.seed, "train_steps": args.iters * args.rollout * args.envs,
            "wall_time_s": round(wall, 1), "note": "2026-08-10 审计复现重建 v2（原为 0 B 占位）",
        },
        "train_log": log,
    }, out)
    print(f"saved {out} ({out.stat().st_size} bytes), steps={args.iters*args.rollout*args.envs}, wall={wall:.1f}s")


if __name__ == "__main__":
    main()
