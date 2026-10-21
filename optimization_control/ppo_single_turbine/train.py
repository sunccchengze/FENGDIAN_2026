"""T1: 单机 PPO 功率跟踪训练（基于 cleanrl ppo_continuous_action.py 单文件改造）
环境: SimplifiedTurbineEnv（Cp 解析公式 + 一阶转速动力学）
"""

import argparse
import json
from pathlib import Path
import yaml
import os
import random
import sys
import time

import gymnasium as gym
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions.normal import Normal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "environments"))
from simplified_turbine_env import SimplifiedTurbineEnv
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from optimization_control.environments.wind_generator import load_config
from optimization_control.environments.stochastic_turbine_env import StochasticTurbineEnv


class CSVLogger:
    """轻量日志：CSV 记录训练指标（替代 tensorboard，规避 tf gfile 沙箱问题）"""
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.header = ["global_step", "episodic_return", "value_loss", "policy_loss",
                       "entropy", "approx_kl", "explained_variance"]
        with open(path, "w", encoding="utf-8") as f:
            f.write(",".join(self.header) + "\n")
        self.rows = []

    def log(self, **kw):
        row = [kw.get(h, "") for h in self.header]
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(",".join(str(v) for v in row) + "\n")
        self.rows.append(kw)


def extract_episode_returns(infos) -> list[float]:
    """兼容 Gymnasium 当前/旧版 vector info，提取本步结束的 episode 回报。"""
    if not isinstance(infos, dict):
        return []

    episode = infos.get("episode")
    if isinstance(episode, dict) and "r" in episode:
        values = np.asarray(episode["r"], dtype=np.float64).reshape(-1)
        mask_source = infos.get("_episode", episode.get("_r"))
        if mask_source is None:
            mask = np.ones(values.shape, dtype=bool)
        else:
            mask = np.asarray(mask_source, dtype=bool).reshape(-1)
            if mask.size == 1 and values.size > 1:
                mask = np.full(values.shape, bool(mask[0]))
        if mask.size != values.size:
            raise ValueError("episode return mask shape does not match return values")
        return [float(value) for value, keep in zip(values, mask) if keep]

    final_infos = infos.get("final_info")
    if final_infos is None:
        return []
    if isinstance(final_infos, dict):
        final_infos = [final_infos]
    final_mask = infos.get("_final_info")
    if final_mask is None:
        final_mask = np.ones(len(final_infos), dtype=bool)
    returns = []
    for keep, final_info in zip(np.asarray(final_mask, dtype=bool), final_infos):
        if keep and final_info and "episode" in final_info:
            value = np.asarray(final_info["episode"]["r"], dtype=np.float64).reshape(-1)
            returns.extend(float(item) for item in value)
    return returns


def make_env(seed, idx, run_name, gamma, wind_config=None):
    """构造带 episode 统计的 SimplifiedTurbineEnv。"""
    def thunk():
        env = (SimplifiedTurbineEnv(seed=seed + idx) if wind_config is None else
               StochasticTurbineEnv(wind_config, seed=seed, worker=idx))
        env = gym.wrappers.RecordEpisodeStatistics(env)
        return env
    return thunk


def layer_init(layer, std=np.sqrt(2), bias_const=0.0):
    torch.nn.init.orthogonal_(layer.weight, std)
    torch.nn.init.constant_(layer.bias, bias_const)
    return layer


class Agent(nn.Module):
    """Actor-Critic MLP：tanh 压缩高斯策略严格映射到物理动作边界。"""
    def __init__(self, envs):
        super().__init__()
        obs_dim = np.array(envs.single_observation_space.shape).prod()
        act_dim = np.prod(envs.single_action_space.shape)
        action_low = torch.as_tensor(
            envs.single_action_space.low, dtype=torch.float32
        ).reshape(1, -1)
        action_high = torch.as_tensor(
            envs.single_action_space.high, dtype=torch.float32
        ).reshape(1, -1)
        if not torch.all(torch.isfinite(action_low)) or not torch.all(
            torch.isfinite(action_high)
        ):
            raise ValueError("tanh-squashed policy requires finite action bounds")
        if not torch.all(action_high > action_low):
            raise ValueError("each action upper bound must exceed its lower bound")
        self.register_buffer("action_bias", (action_high + action_low) / 2.0, persistent=False)
        self.register_buffer("action_scale", (action_high - action_low) / 2.0, persistent=False)
        self.critic = nn.Sequential(
            layer_init(nn.Linear(obs_dim, 64)), nn.Tanh(),
            layer_init(nn.Linear(64, 64)), nn.Tanh(),
            layer_init(nn.Linear(64, 1), std=1.0),
        )
        self.actor_mean = nn.Sequential(
            layer_init(nn.Linear(obs_dim, 64)), nn.Tanh(),
            layer_init(nn.Linear(64, 64)), nn.Tanh(),
            layer_init(nn.Linear(64, act_dim), std=0.01),
        )
        self.actor_logstd = nn.Parameter(torch.zeros(1, act_dim))

    def get_value(self, x):
        return self.critic(x)

    def get_action_and_value(self, x, action=None):
        mean = self.actor_mean(x)
        logstd = self.actor_logstd.expand_as(mean)
        probs = Normal(mean, torch.exp(logstd))
        if action is None:
            pre_tanh = probs.rsample()
            squashed = torch.tanh(pre_tanh)
            action = self.action_bias + self.action_scale * squashed
        else:
            normalized = (action - self.action_bias) / self.action_scale
            squashed = torch.clamp(normalized, -1.0 + 1e-6, 1.0 - 1e-6)
            pre_tanh = torch.atanh(squashed)

        log_abs_det_jacobian = torch.log(
            self.action_scale * (1.0 - squashed.pow(2)) + 1e-6
        )
        logprob = (
            probs.log_prob(pre_tanh) - log_abs_det_jacobian
        ).sum(dim=1)
        # A single-sample transformed-distribution entropy estimate. The
        # default ent_coef is zero; retaining this keeps diagnostics finite.
        entropy = -logprob
        return action, logprob, entropy, self.critic(x)

    def get_deterministic_action(self, x):
        """Map the latent Gaussian mean to a valid physical action."""
        return self.action_bias + self.action_scale * torch.tanh(
            self.actor_mean(x)
        )


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--total-timesteps", type=int, default=196608)
    p.add_argument("--num-envs", type=int, default=4)
    p.add_argument("--num-steps", type=int, default=2048)
    p.add_argument("--num-minibatches", type=int, default=32)
    p.add_argument("--update-epochs", type=int, default=10)
    p.add_argument("--learning-rate", type=float, default=3e-4)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--gae-lambda", type=float, default=0.95)
    p.add_argument("--clip-coef", type=float, default=0.2)
    p.add_argument("--ent-coef", type=float, default=0.0)
    p.add_argument("--vf-coef", type=float, default=0.5)
    p.add_argument("--max-grad-norm", type=float, default=0.5)
    p.add_argument("--anneal-lr", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--save-model", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--run-tag", type=str, default="ppo_tracking")
    p.add_argument("--wind-config", type=Path, default=None)
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--torch-threads", type=int, default=1)
    return p.parse_args()


def main():
    args = parse_args()
    if args.torch_threads < 1:
        raise ValueError("torch threads must be positive")
    torch.set_num_threads(args.torch_threads)
    wind_config = load_config(args.wind_config) if args.wind_config else None
    run_name = f"{args.run_tag}__seed{args.seed}__{int(time.time())}"
    runs_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "runs"))
    run_dir = os.path.join(runs_dir, run_name)
    if args.output_dir is not None:
        run_dir = str(args.output_dir.resolve())
    os.makedirs(run_dir, exist_ok=False)
    saved_config = {"seed": args.seed, "training": {k: str(v) if isinstance(v, Path) else v
                    for k, v in vars(args).items()}, "environment_config": wind_config,
                    "versions": {"numpy": np.__version__, "torch": str(torch.__version__),
                                 "gymnasium": gym.__version__}}
    Path(run_dir, "config.yaml").write_text(yaml.safe_dump(saved_config), encoding="utf-8")
    Path(run_dir, "summary.txt").write_text("Training started; no performance claim.\n", encoding="utf-8")
    logger = CSVLogger(os.path.join(run_dir, "metrics.csv"))

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.backends.cudnn.deterministic = True
    device = torch.device("cpu")

    envs = gym.vector.SyncVectorEnv(
        [make_env(args.seed, i, run_name, args.gamma, wind_config) for i in range(args.num_envs)],
        autoreset_mode=gym.vector.AutoresetMode.SAME_STEP,
    )
    assert isinstance(envs.single_action_space, gym.spaces.Box)
    agent = Agent(envs).to(device)
    optimizer = optim.Adam(agent.parameters(), lr=args.learning_rate, eps=1e-5)

    batch_size = args.num_envs * args.num_steps
    if args.num_minibatches <= 0:
        raise ValueError("--num-minibatches must be positive")
    if batch_size % args.num_minibatches != 0:
        raise ValueError("num_envs * num_steps must be divisible by num_minibatches")
    minibatch_size = batch_size // args.num_minibatches
    num_iterations = args.total_timesteps // batch_size
    if args.total_timesteps % batch_size != 0:
        raise ValueError(
            "--total-timesteps must be divisible by num_envs * num_steps"
        )
    if num_iterations < 1:
        raise ValueError("--total-timesteps must cover at least one rollout batch")

    obs = torch.zeros((args.num_steps, args.num_envs) + envs.single_observation_space.shape)
    actions = torch.zeros((args.num_steps, args.num_envs) + envs.single_action_space.shape)
    logprobs = torch.zeros((args.num_steps, args.num_envs))
    rewards = torch.zeros((args.num_steps, args.num_envs))
    dones = torch.zeros((args.num_steps, args.num_envs))
    values = torch.zeros((args.num_steps, args.num_envs))

    global_step = 0
    start_time = time.time()
    next_obs, _ = envs.reset(seed=[args.seed] * args.num_envs if wind_config else args.seed)
    next_obs = torch.Tensor(next_obs)
    next_done = torch.zeros(args.num_envs)

    for iteration in range(1, num_iterations + 1):
        iteration_episode_returns = []
        if args.anneal_lr:
            frac = 1.0 - (iteration - 1.0) / num_iterations
            optimizer.param_groups[0]["lr"] = frac * args.learning_rate
        for step in range(args.num_steps):
            global_step += args.num_envs
            obs[step], dones[step] = next_obs, next_done
            with torch.no_grad():
                action, logprob, _, value = agent.get_action_and_value(next_obs)
                values[step] = value.flatten()
            actions[step], logprobs[step] = action, logprob
            next_obs, reward, term, trunc, infos = envs.step(action.cpu().numpy())
            next_done = np.logical_or(term, trunc)
            rewards[step] = torch.tensor(reward).view(-1)
            next_obs = torch.Tensor(next_obs)
            next_done = torch.Tensor(next_done)
            for episode_return in extract_episode_returns(infos):
                iteration_episode_returns.append(episode_return)
                print(f"global_step={global_step}, episodic_return={episode_return:.3f}")

        with torch.no_grad():
            next_value = agent.get_value(next_obs).reshape(1, -1)
            advantages = torch.zeros_like(rewards)
            lastgaelam = 0.0
            for t in reversed(range(args.num_steps)):
                if t == args.num_steps - 1:
                    nextnonterminal = 1.0 - next_done
                    nextvalues = next_value
                else:
                    nextnonterminal = 1.0 - dones[t + 1]
                    nextvalues = values[t + 1]
                delta = rewards[t] + args.gamma * nextvalues * nextnonterminal - values[t]
                advantages[t] = lastgaelam = delta + args.gamma * args.gae_lambda * nextnonterminal * lastgaelam
            returns = advantages + values

        b_obs = obs.reshape((-1,) + envs.single_observation_space.shape)
        b_logprobs = logprobs.reshape(-1)
        b_actions = actions.reshape((-1,) + envs.single_action_space.shape)
        b_advantages = advantages.reshape(-1)
        b_returns = returns.reshape(-1)
        b_values = values.reshape(-1)
        b_inds = np.arange(batch_size)

        for epoch in range(args.update_epochs):
            np.random.shuffle(b_inds)
            for start in range(0, batch_size, minibatch_size):
                mb = b_inds[start:start + minibatch_size]
                _, newlogprob, entropy, newvalue = agent.get_action_and_value(b_obs[mb], b_actions[mb])
                logratio = newlogprob - b_logprobs[mb]
                ratio = logratio.exp()
                with torch.no_grad():
                    old_approx_kl = (-logratio).mean()
                    approx_kl = ((ratio - 1) - logratio).mean()
                mb_adv = b_advantages[mb]
                mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)
                pg1 = -mb_adv * ratio
                pg2 = -mb_adv * torch.clamp(ratio, 1 - args.clip_coef, 1 + args.clip_coef)
                pg_loss = torch.max(pg1, pg2).mean()
                newvalue = newvalue.view(-1)
                v_unclipped = (newvalue - b_returns[mb]) ** 2
                v_clipped = b_values[mb] + torch.clamp(newvalue - b_values[mb], -args.clip_coef, args.clip_coef)
                v_loss = 0.5 * torch.max(v_unclipped, (v_clipped - b_returns[mb]) ** 2).mean()
                entropy_loss = entropy.mean()
                loss = pg_loss - args.ent_coef * entropy_loss + v_loss * args.vf_coef
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), args.max_grad_norm)
                optimizer.step()
            if approx_kl > 0.02:
                break

        mean_episode_return = float(np.mean(iteration_episode_returns)) if iteration_episode_returns else np.nan
        y_pred, y_true = b_values.cpu().numpy(), b_returns.cpu().numpy()
        var_y = np.var(y_true)
        explained_var = np.nan if var_y == 0 else 1 - np.var(y_true - y_pred) / var_y
        logger.log(
            global_step=global_step,
            episodic_return=mean_episode_return,
            value_loss=v_loss.item(),
            policy_loss=pg_loss.item(),
            entropy=entropy_loss.item(),
            approx_kl=approx_kl.item(),
            explained_variance=explained_var,
        )
        print(f"iter={iteration}/{num_iterations} SPS={int(global_step/(time.time()-start_time))} "
              f"loss={loss.item():.4f} ev={explained_var:.3f} episodes={len(iteration_episode_returns)}")

    if args.save_model:
        model_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "models", "ppo"))
        if wind_config is not None:
            model_dir = run_dir
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, f"{args.run_tag}_seed{args.seed}.pt")
        if os.path.exists(model_path):
            raise FileExistsError(f"refusing to overwrite model: {model_path}")
        torch.save(agent.state_dict(), model_path)
        env0 = envs.envs[0].unwrapped
        metadata = {"policy_format": "tanh_squashed", "environment_config": wind_config,
                    "observation_names": list(getattr(env0, "observation_names", ["P", "omega", "beta", "U", "P_target"])),
                    "obs_scale": env0.obs_scale.tolist(), "seed": args.seed,
                    "total_timesteps": global_step, "training_config": saved_config}
        Path(model_path).with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"model saved: {model_path}")
        # 训练曲线图
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd
        df = pd.read_csv(logger.path)
        fig, axes = plt.subplots(2, 2, figsize=(11, 8))
        axes[0, 0].plot(df["global_step"], df["episodic_return"])
        axes[0, 0].set_title("episodic_return"); axes[0, 0].set_xlabel("step")
        axes[0, 1].plot(df["global_step"], df["explained_variance"])
        axes[0, 1].set_title("explained_variance"); axes[0, 1].set_xlabel("step")
        axes[1, 0].plot(df["global_step"], df["policy_loss"])
        axes[1, 0].set_title("policy_loss"); axes[1, 0].set_xlabel("step")
        axes[1, 1].plot(df["global_step"], df["value_loss"])
        axes[1, 1].set_title("value_loss"); axes[1, 1].set_xlabel("step")
        fig.tight_layout()
        curve_path = os.path.join(run_dir, "training_curve.png")
        fig.savefig(curve_path, dpi=120)
        print("曲线图:", curve_path)
    Path(run_dir, "summary.txt").write_text(
        f"Completed {global_step} transitions; seed={args.seed}; environment={'stochastic_single_v2' if wind_config else 'legacy'}.\n"
        "Smoke/individual training run does not establish controller superiority.\n", encoding="utf-8")
    envs.close()
    print("训练完成:", run_name)


if __name__ == "__main__":
    main()
