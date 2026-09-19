# -*- coding: utf-8 -*-
"""PPO 功率跟踪审计评测与可视化数据导出。

对 ``model/ppo_tracking_v3_seed42.pt`` 做 200 个固定测试回合，并同时输出：

- ``metrics_repro.json``：汇总指标；
- ``ppo_eval_traces.json``：逐回合指标与一个真实代表回合的完整时序。

目标功率域为物理可达的 ``[0.78, 0.98] * P_base``。代表回合取稳态
MAE 最接近 200 回合中位数的回合，避免人为挑选最好结果。两份 JSON 都记录
模型 SHA-256、评测种子、时间步长和误差带定义，供网页与 Nature 图同源引用。
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

HERE = Path(__file__).parent
MODEL_PATH = HERE / "model" / "ppo_tracking_v3_seed42.pt"
OUT_PATH = HERE / "metrics_repro.json"
TRACE_PATH = HERE / "ppo_eval_traces.json"

U_LO, U_HI = 6.0, 12.0
RHO, R_AREA, CP = 1.225, np.pi * 63.0**2, 0.45
DT = 0.1
HORIZON = 200
YAW_LIM = 30.0
A_LIM = 5.0
TARGET_LO, TARGET_HI = 0.78, 0.98
SETTLING_BAND = 0.015
OBS_SCALE = np.array([10.0, 30.0, 5000.0, 5000.0])


def p_base_of(u):
    return 0.5 * RHO * R_AREA * CP * u**3 / 1000.0


class ActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        trunk = lambda: nn.Sequential(nn.Linear(4, 64), nn.Tanh(), nn.Linear(64, 64), nn.Tanh())
        self.pi = nn.Sequential(trunk(), nn.Linear(64, 1))
        self.v = nn.Sequential(trunk(), nn.Linear(64, 1))
        self.log_std = nn.Parameter(torch.full((1,), float(np.log(1.5))))

    def act_deterministic(self, obs):
        with torch.no_grad():
            t_obs = torch.tensor(obs, dtype=torch.float32)
            mean = self.pi(t_obs).squeeze(-1)
            return np.clip(mean.numpy(), -A_LIM, A_LIM)


def _round_list(values, digits=6):
    return [round(float(v), digits) for v in values]


def evaluate(n_episodes=200, seed=1000):
    if not MODEL_PATH.exists() or MODEL_PATH.stat().st_size == 0:
        raise FileNotFoundError(f"缺少有效权重文件：{MODEL_PATH}")

    ckpt = torch.load(MODEL_PATH, map_location="cpu")
    net = ActorCritic()
    net.load_state_dict(ckpt["state_dict"])
    net.eval()

    model_sha = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    rng = np.random.default_rng(seed)
    u_list = rng.uniform(U_LO, U_HI, n_episodes)
    ratio_list = rng.uniform(TARGET_LO, TARGET_HI, n_episodes)

    episode_records = []
    full_histories = []

    for idx in range(n_episodes):
        u = float(u_list[idx])
        p_base = float(p_base_of(u))
        target_ratio = float(ratio_list[idx])
        target = target_ratio * p_base
        yaw = 0.0

        p_history = []
        yaw_history = []
        action_history = []
        for _step in range(HORIZON):
            p = p_base * np.cos(np.radians(yaw)) ** 1.88
            obs = np.array([u, yaw, p, target]) / OBS_SCALE
            action = float(np.asarray(net.act_deterministic(obs)).item())
            p_history.append(float(p))
            yaw_history.append(float(yaw))
            action_history.append(action)
            yaw = float(np.clip(yaw + action, -YAW_LIM, YAW_LIM))

        p_arr = np.asarray(p_history)
        a_arr = np.asarray(action_history)
        err_steady_kw = np.abs(p_arr[HORIZON // 2:] - target)
        steady_mae_kw = float(err_steady_kw.mean())
        steady_mae_pct = float((err_steady_kw / target).mean() * 100.0)

        rel_err = np.abs(p_arr - target) / target
        within_band = rel_err <= SETTLING_BAND
        settle_step = HORIZON
        for step in range(HORIZON):
            if within_band[step:].all():
                settle_step = step
                break
        settling_time = settle_step * DT
        steady_action_rate = float(np.abs(a_arr[HORIZON // 2:]).mean())

        episode_records.append({
            "episode": idx,
            "wind_speed_ms": round(u, 6),
            "target_ratio": round(target_ratio, 6),
            "target_power_kw": round(target, 6),
            "steady_mae_pct": round(steady_mae_pct, 6),
            "steady_mae_kw": round(steady_mae_kw, 6),
            "settling_time_s": round(settling_time, 6),
            "steady_action_rate_deg_per_step": round(steady_action_rate, 8),
        })
        full_histories.append((p_history, yaw_history, action_history))

    mae_pct = np.array([r["steady_mae_pct"] for r in episode_records])
    mae_kw = np.array([r["steady_mae_kw"] for r in episode_records])
    settle = np.array([r["settling_time_s"] for r in episode_records])
    action_rate = np.array([r["steady_action_rate_deg_per_step"] for r in episode_records])

    summary = {
        "steady_state_mae_pct": round(float(mae_pct.mean()), 3),
        "steady_state_mae_kw": round(float(mae_kw.mean()), 2),
        "settling_time_mean_s": round(float(settle.mean()), 3),
        "settling_time_p95_s": round(float(np.percentile(settle, 95)), 3),
        "steady_action_rate_deg_per_step": round(float(action_rate.mean()), 4),
    }
    provenance = {
        "model_file": MODEL_PATH.name,
        "model_sha256": model_sha,
        "evaluation_seed": seed,
        "n_episodes": n_episodes,
        "dt_s": DT,
        "horizon_steps": HORIZON,
        "target_range_fraction_p_base": [TARGET_LO, TARGET_HI],
        "steady_window_steps": [HORIZON // 2, HORIZON],
        "settling_band_fraction": SETTLING_BAND,
    }

    metrics = {
        "n_episodes": n_episodes,
        "seed": seed,
        "metrics": summary,
        "model_file": MODEL_PATH.name,
        "model_sha256": model_sha,
        "audit_note": "物理可达域 cos^1.88 理论模型下的独立 PPO 闭环验证；汇总值来自 200 个固定测试回合。",
    }
    OUT_PATH.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    median_mae = float(np.median(mae_pct))
    representative_idx = int(np.argmin(np.abs(mae_pct - median_mae)))
    rep = episode_records[representative_idx]
    p_history, yaw_history, action_history = full_histories[representative_idx]
    representative = {
        **rep,
        "selection_rule": "稳态 MAE 最接近 200 回合中位数",
        "time_s": _round_list(np.arange(HORIZON) * DT, 3),
        "power_actual_kw": _round_list(p_history, 6),
        "power_target_kw": [rep["target_power_kw"]] * HORIZON,
        "yaw_deg": _round_list(yaw_history, 6),
        "action_delta_yaw_deg": _round_list(action_history, 8),
    }
    traces = {
        "provenance": provenance,
        "summary": summary,
        "representative_episode": representative,
        "episodes": episode_records,
    }
    TRACE_PATH.write_text(json.dumps(traces, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== PPO 功率跟踪审计评测 ===")
    print(f"评测回合数       : {n_episodes}")
    print(f"稳态跟踪 MAE(%)  : {summary['steady_state_mae_pct']:.3f} %")
    print(f"稳态跟踪 MAE(kW) : {summary['steady_state_mae_kw']:.2f} kW")
    print(f"平均调节时间 (s) : {summary['settling_time_mean_s']:.3f} s")
    print(f"95分位调节时间(s): {summary['settling_time_p95_s']:.3f} s")
    print(f"代表回合         : episode {representative_idx}（中位 MAE 规则）")
    print(f"模型 SHA-256     : {model_sha}")
    print(f"汇总报告         : {OUT_PATH}")
    print(f"可视化数据       : {TRACE_PATH}")
    return metrics, traces


if __name__ == "__main__":
    evaluate()
