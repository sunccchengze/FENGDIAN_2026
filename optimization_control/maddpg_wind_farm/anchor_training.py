"""Paired frozen-parent action regularization from three-channel handovers."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

from .fixed_pinn_demo import activate_runtime, digest
from .progressive_random_control import verify_hashes
from . import random_wind_training as shared
from .residual_random_control import next_segment, scales, score, Monitor

DEFAULT = Path(__file__).parent / "configs/anchor_training.yaml"
VERSION = "parent_action_anchor_v1"


def read_protocol(path):
    import yaml
    p = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if p["version"] != VERSION or p["seed"] != 42 or p["run_ids"] != [0, 1, 2]:
        raise ValueError("three paired seed42 streams required")
    if p["arms"] != dict(baseline=dict(actor_lr=1e-4, anchor_weight=0.), anchor=dict(actor_lr=1e-4, anchor_weight=1.)):
        raise ValueError("only the predeclared parent-action penalty intervention is allowed")
    if (p["steps_per_run"], p["eval_every"], p["warmup_steps"], p["update_every"]) != (8192, 2048, 512, 2):
        raise ValueError("fixed equal-budget training schedule required")
    if p["final_parent_max_ratio"] != 1.05 or p["paired_final_max_ratio"] != 1.05:
        raise ValueError("final-state noninferiority limits cannot change")
    if p["anchor_scales"] != [0.3490658503988659, 1., 0.2998500749625188]:
        raise ValueError("fixed full-authority anchor scales required")
    return p


def assert_actor_lr(agent, expected):
    if agent.config.actor_lr != expected or any(group["lr"] != expected for optimizer in agent.actor_optimizers for group in optimizer.param_groups):
        raise ValueError("Actor config/optimizer learning rates differ from the frozen arm")


def configure_actor_lr(agent, value):
    """The ONLY between-arm difference; both arms use fresh empty Actor moments."""
    import torch
    agent.config = replace(agent.config, actor_lr=value)
    agent.actor_optimizers = [torch.optim.Adam(actor.parameters(), lr=value) for actor in agent.actors]
    assert_actor_lr(agent, value)


def prepare(p, output):
    import yaml
    source = Path(p["bootstrap_experiment"]).resolve()
    old = json.loads((source / "selection.json").read_text(encoding="utf-8"))
    old_cfg = yaml.safe_load((source / "config.yaml").read_text(encoding="utf-8"))
    verify_hashes(old_cfg["source_hashes"])
    verify_hashes(old["hashes"])
    parents = {}
    for run in p["run_ids"]:
        r = next(r for r in old["results"] if r["stage"] == "all" and r["run_id"] == run)
        path = r["initial"]
        parents[str(run)] = dict(checkpoint=path, sha256=digest(path), cumulative_steps=r["lineage"]["cumulative_parent_steps"])
    root = shared.prepare(p, output)
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    saved["parents"] = parents
    saved["source_hashes"].update(old_cfg["source_hashes"])
    files = [Path(__file__).with_name(n) for n in ("anchor_training.py", "anchor_algorithm.py", "verify_anchor.py", "ANCHOR_PROTOCOL.md")]
    files += [DEFAULT, source / "selection.json", source / "config.yaml", source / "summary.txt"]
    files += [Path(parent["checkpoint"]) for parent in parents.values()]
    files += [Path(p["diagnostic_experiment"]) / name for name in ("config.yaml", "metrics.csv", "summary.txt")]
    saved["source_hashes"].update({str(path.resolve()): digest(path) for path in files})
    (root / "config.yaml").write_text(yaml.safe_dump(saved, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
    return root


def train(root, arm, run, stop_after=None):
    import numpy as np
    import torch
    import yaml
    from .residual_algorithm import ResidualMADDPG
    from .anchor_algorithm import AnchoredMADDPG
    from .workflow import build_env
    from .stable_workflow import Exploration
    from .benchmark import seed_for
    from ..environments.farm_inflow import generate_inflow
    root = Path(root).resolve()
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    p = saved["protocol"]
    if arm not in p["arms"] or run not in p["run_ids"]:
        raise ValueError("unknown frozen arm or run")
    if (root / "selection.json").exists() or (root / "test").exists():
        raise ValueError("selection/test frozen: additional training prohibited")
    verify_hashes(saved["source_hashes"])
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    job = root / f"{arm}_run_{run}"
    if (job / "result.json").exists():
        r = json.loads((job / "result.json").read_text(encoding="utf-8"))
        verify_hashes(r["hashes"])
        return r
    lr = p["arms"][arm]["actor_lr"]
    weight = p["arms"][arm]["anchor_weight"]
    cfg = deepcopy(saved["base_config"])
    cfg["environment"]["control_mask"] = [1, 1, 1]
    cfg["algorithm"]["actor_lr"] = lr
    env = build_env(cfg)
    parent = saved["parents"][str(run)]
    identity = dict(arm=arm, stage="all", control=False, run_id=run, parent=parent,
        actor_lr=lr, anchor_weight=weight, root_config_sha256=digest(root / "config.yaml"))
    noise = Exploration(seed_for(42, p["noise_seed_namespace"], run), p["stage_noise_std"]["all"],
        [10., 3., 5.], env.dt, "white", p["noise_end_fraction"])
    if job.exists():
        states = sorted(job.glob("segment_*/state.json"))
        if not states:
            raise ValueError("incomplete initialization; preserve artifacts and use a fresh experiment")
        last = json.loads(states[-1].read_text(encoding="utf-8"))
        agent, meta = AnchoredMADDPG.load(last["checkpoint"])
        if agent.anchor_weight != weight or agent.anchor_scales != tuple(p["anchor_scales"]):
            raise ValueError("anchor recovery identity differs")
        if meta["identity"] != identity or meta["normalization"] != env.normalization():
            raise ValueError("resume identity differs")
        assert_actor_lr(agent, lr)
        step, episode, history, best = meta["step"], meta["episode"], meta["history"], meta["best"]
        initial, lineage = meta["initial"], meta["lineage"]
        noise.load_state_dict(meta["noise"])
        segment = next_segment(job)
        final = last["checkpoint"]
    else:
        verify_hashes({parent["checkpoint"]: parent["sha256"]})
        agent, parent_meta = ResidualMADDPG.load(parent["checkpoint"])
        if tuple(agent.config.action_mask) != (1, 1, 1):
            raise ValueError("existing all-channel handover required, do not reopen a channel")
        if parent_meta["config"]["environment"] != cfg["environment"] or parent_meta["config"]["plant"] != cfg["plant"]:
            raise ValueError("only anchor penalty may change, environment and plant must match")
        configure_actor_lr(agent, lr)
        agent = AnchoredMADDPG.from_parent(agent, weight, p["anchor_scales"])
        parent_rows, _ = shared.rollout(cfg, shared.cases(root, "validation"), agent=agent)
        pm, pw = score(parent_rows)
        lineage = dict(parent_checkpoint=parent["checkpoint"], parent_sha256=parent["sha256"],
            cumulative_parent_steps=parent["cumulative_steps"], inherited_replay_size=agent.replay.size,
            inherited_updates=agent.updates, parent_mean_w=pm, parent_worst_w=pw,
            actor_optimizer_reset=True, only_intervention="anchor_weight", initial_actor_lr=lr)
        job.mkdir()
        step = episode = segment = 0
        best = initial = None
        history = []
    out = job / f"segment_{segment:03d}"
    out.mkdir()
    full = scales(p, cfg, "all", p["steps_per_run"])

    def snapshot(losses):
        nonlocal best, initial
        training_scales = scales(p, cfg, "all", step)
        agent.config = replace(agent.config, residual_scales=full)
        assert_actor_lr(agent, lr)
        monitor = DriftMonitor(agent, cfg)
        rows, _ = shared.rollout(cfg, shared.cases(root, "validation"), agent=monitor)
        drift = monitor.summary()
        mean, worst = score(rows)
        path = str((out / f"step_{step:08d}.pth").resolve())
        if initial is None:
            initial = path
        if best is None or mean < best["score_w"]:
            best = dict(checkpoint=path, score_w=mean, step=step, validation=rows)
        history.append(dict(steps=step, validation_rmse_w=mean, worst_validation_rmse_w=worst,
            best_rmse_w=best["score_w"], actor_lr=lr, anchor_weight=weight,
            drift_yaw_rad=drift["parent_yaw_drift_rms_rad"], drift_pitch_rad=drift["parent_pitch_drift_rms_rad"],
            drift_speed_rad_s=drift["parent_speed_drift_rms_rad_s"],
            actor_loss=float(np.mean([v["actor_loss"] for v in losses])) if losses else 0.,
            critic_loss=float(np.mean([v["critic_loss"] for v in losses])) if losses else 0.))
        agent.save(path, dict(identity=identity, config=cfg, step=step, episode=episode, history=history,
            best=best, initial=initial, lineage=lineage, actor_lr=lr, training_scales=training_scales,
            evaluation_scales=full, noise=noise.state_dict(), normalization=env.normalization()))
        shared.write_json(out / "state.json", dict(checkpoint=path, step=step, completed=step == p["steps_per_run"]))
        shared.write_csv(out / "metrics.csv", history)
        agent.config = replace(agent.config, residual_scales=training_scales)
        print(json.dumps(dict(arm=arm, run_id=run, **history[-1])), flush=True)
        return path

    if step == 0:
        final = snapshot([])
    if stop_after is not None and (stop_after % p["eval_every"] or not step < stop_after <= p["steps_per_run"]):
        raise ValueError("stop_after must be a later evaluation boundary")
    losses = []
    while step < p["steps_per_run"]:
        family, target, pitch = shared.episode_design(p, run, episode)
        inflow = deepcopy(p["inflow"])
        inflow["speed"]["scenario"] = family
        wind = generate_inflow(inflow, dt_s=env.dt, horizon=env.horizon, seed=42, split="train",
            episode=p["training_episode_offset"] + run * 1000 + episode)
        env.initial = np.asarray(cfg["environment"]["initial_operating_point"], dtype=float).copy()
        env.initial[1] = pitch
        obs, _ = env.reset(seed=42, options=dict(wind_trajectory=wind.values, target_w=target))
        noise.reset()
        for _ in range(env.horizon):
            agent.config = replace(agent.config, residual_scales=scales(p, cfg, "all", step))
            action = agent.act(obs, noise=noise.sample(step / p["steps_per_run"]))
            projected = env.project_action(action)
            np.testing.assert_array_equal(action, projected)
            nxt, reward, done, _, info = env.step(action)
            np.testing.assert_array_equal(info["executed_action"], action)
            agent.replay.add(obs, info["executed_action"], reward, nxt, done)
            step += 1
            if step >= p["warmup_steps"] and step % p["update_every"] == 0:
                losses.append(agent.update())
            obs = nxt
        episode += 1
        if step % p["eval_every"] == 0:
            final = snapshot(losses)
            losses = []
            if stop_after == step and step < p["steps_per_run"]:
                return None
    ratio = history[-1]["validation_rmse_w"] / best["score_w"]
    final_mean, final_worst = history[-1]["validation_rmse_w"], history[-1]["worst_validation_rmse_w"]
    parent_pass = final_mean <= 1.05 * lineage["parent_mean_w"] and final_worst <= 1.05 * lineage["parent_worst_w"]
    result = dict(stage=arm, run_id=run, config=cfg, initial=initial, final=final, best=best, steps=step,
        lineage=lineage, inherited_replay_size=lineage["inherited_replay_size"], actor_lr=lr, anchor_weight=weight, resume_segments=segment + 1,
        final_over_selected=ratio, final_mean_w=final_mean, final_worst_w=final_worst,
        stable_ratio_pass=ratio <= 1.25, final_parent_noninferior=parent_pass,
        stability_pass=ratio <= 1.25 and parent_pass,
        strict_accuracy_pass=best["score_w"] <= 400000 and score(best["validation"])[1] <= 500000,
        learned_selected=best["step"] > 0 and best["score_w"] < history[0]["validation_rmse_w"],
        hashes={path: digest(path) for path in set((initial, best["checkpoint"], final))})
    shared.write_json(job / "result.json", result)
    return result


class DriftMonitor(Monitor):
    """On-policy action drift measured on the same current observations."""
    def __init__(self, agent, cfg):
        super().__init__(agent, cfg)
        self.parent_deltas = []

    def act(self, obs):
        import numpy as np
        import torch
        action = super().act(obs)
        if hasattr(self.agent, "teacher_action"):
            x = torch.as_tensor(obs, device=self.agent.device)
            reference = torch.stack([self.agent.teacher_action(i, x[i]) for i in range(3)]).cpu().numpy()
            self.parent_deltas.append((action - reference) * self.width / 2)
        else:
            self.parent_deltas.append(np.zeros_like(action))
        return action

    def summary(self):
        import numpy as np
        result = super().summary()
        rms = np.sqrt(np.mean(np.asarray(self.parent_deltas) ** 2, axis=(0, 1)))
        result.update(parent_yaw_drift_rms_rad=float(rms[0]), parent_pitch_drift_rms_rad=float(rms[1]),
                      parent_speed_drift_rms_rad_s=float(rms[2]))
        return result


def release_test(root):
    import yaml
    from .anchor_algorithm import load_policy
    root = Path(root)
    selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    verify_hashes(saved["source_hashes"])
    verify_hashes(selection["hashes"])
    if selection["root_config_sha256"] != digest(root / "config.yaml") or selection["bank_sha256"] != digest(root / "bank/manifest.json"):
        raise ValueError("frozen test identity changed")
    out = shared.fresh(root / "test", dict(seed=42, selection_sha256=digest(root / "selection.json")))
    bank = shared.cases(root, "test", allow_test=True)
    metrics, traces, corrections = [], [], []
    for r in selection["results"]:
        choices = [("initial", r["initial"]), ("selected", r["best"]["checkpoint"]), ("final", r["final"]),
                   ("parent", r["lineage"]["parent_checkpoint"])]
        for label, path in choices:
            agent, meta = load_policy(path)
            monitor = DriftMonitor(agent, meta["config"])
            rows, capture = shared.rollout(meta["config"], bank, agent=monitor, capture=True)
            tags = dict(stage=r["stage"], run_id=r["run_id"], controller=label)
            metrics.extend(dict(**tags, **row) for row in rows)
            traces.extend(dict(**tags, **row) for row in capture)
            corrections.append(dict(**tags, **monitor.summary()))
        print("Independent residual test", r["stage"], r["run_id"], flush=True)
    for stage in dict.fromkeys(r["stage"] for r in selection["results"]):
        cfg = next(r["config"] for r in selection["results"] if r["stage"] == stage)
        for mode in ("fixed", "p", "pi"):
            rows, capture = shared.rollout(cfg, bank, mode=mode, capture=True)
            tags = dict(stage=stage, run_id=-1, controller=mode)
            metrics.extend(dict(**tags, **row) for row in rows)
            traces.extend(dict(**tags, **row) for row in capture)
    shared.write_csv(out / "metrics.csv", metrics)
    shared.write_csv(out / "trajectories.csv", traces)
    shared.write_csv(out / "corrections.csv", corrections)
    shared.write_json(root / "summary.txt", dict(seed=42, completed=True, training_steps=sum(r["steps"] for r in selection["results"]),
        gates=selection["gates"], test_rows=len(metrics), trace_rows=len(traces), physical_validation=False,
        test_used_for_selection=False, action_semantics="baseline_plus_residual_total_absolute_targets"))


def execute(root):
    import yaml
    root = Path(root).resolve()
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    if (root / "selection.json").exists():
        raise ValueError("selection frozen: no additional training")
    results = []
    for run in saved["protocol"]["run_ids"]:
        for arm in saved["protocol"]["arms"]:
            subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", __spec__.name, "worker", "--output", str(root),
                "--arm", arm, "--run-id", str(run)], check=True)
            results.append(json.loads((root / f"{arm}_run_{run}/result.json").read_text(encoding="utf-8")))
    for r in results:
        baseline = next(v for v in results if v["stage"] == "baseline" and v["run_id"] == r["run_id"])
        r["paired_final_noninferior"] = bool(r["final_mean_w"] <= 1.05 * baseline["final_mean_w"] and r["final_worst_w"] <= 1.05 * baseline["final_worst_w"])
    gates = [dict(stage=arm, stable_ratio_passed=sum(r["stable_ratio_pass"] for r in results if r["stage"] == arm),
        final_parent_passed=sum(r["final_parent_noninferior"] for r in results if r["stage"] == arm),
        paired_final_passed=sum(r["paired_final_noninferior"] for r in results if r["stage"] == arm),
        passed=all(r["stability_pass"] and r["paired_final_noninferior"] for r in results if r["stage"] == arm)) for arm in saved["protocol"]["arms"]]
    shared.write_csv(root / "metrics.csv", [dict(stage=r["stage"], run_id=r["run_id"], actor_lr=r["actor_lr"], anchor_weight=r["anchor_weight"], steps=r["steps"],
        selected_step=r["best"]["step"], selected_mean_w=r["best"]["score_w"], selected_worst_w=score(r["best"]["validation"])[1],
        final_mean_w=r["final_mean_w"], final_worst_w=r["final_worst_w"], final_over_selected=r["final_over_selected"],
        stable_ratio_pass=r["stable_ratio_pass"], final_parent_noninferior=r["final_parent_noninferior"],
        paired_final_noninferior=r["paired_final_noninferior"], learned_selected=r["learned_selected"], strict_accuracy_pass=r["strict_accuracy_pass"]) for r in results])
    hashes = {path: expected for r in results for path, expected in r["hashes"].items()}
    hashes.update({r["lineage"]["parent_checkpoint"]: r["lineage"]["parent_sha256"] for r in results})
    shared.write_json(root / "selection.json", dict(seed=42, results=results, gates=gates, hashes=hashes,
        root_config_sha256=digest(root / "config.yaml"), bank_sha256=digest(root / "bank/manifest.json")))
    release_test(root)
    summary = json.loads((root / "summary.txt").read_text(encoding="utf-8"))
    summary.update(independent_routine_metric_rows=540, known_low_wind_regression_rows=60,
        pressure_case_is_new_independent_data=False, intervention="parent action penalty lambda 0 -> 1 only")
    shared.write_json(root / "summary.txt", summary)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("prepare", "all", "run", "worker"))
    ap.add_argument("--protocol", default=str(DEFAULT))
    ap.add_argument("--output", required=True)
    ap.add_argument("--arm", choices=("baseline", "anchor"), default="baseline")
    ap.add_argument("--run-id", type=int, default=0)
    ap.add_argument("--stop-after", type=int)
    args = ap.parse_args()
    p = read_protocol(args.protocol)
    activate_runtime(p["runtime_site_packages"])
    sys.dont_write_bytecode = True
    root = Path(args.output)
    if args.command in ("prepare", "all"):
        root = prepare(p, root)
    if args.command in ("run", "all"):
        execute(root)
    if args.command == "worker":
        train(root, args.arm, args.run_id, args.stop_after)


if __name__ == "__main__":
    main()
