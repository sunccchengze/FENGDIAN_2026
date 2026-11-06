"""Frozen paired residual-control experiment with episode-boundary recovery."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

from . import random_wind_training as shared
from .fixed_pinn_demo import activate_runtime, digest
from .progressive_random_control import verify_hashes

DEFAULT = Path(__file__).parent / "configs/residual_random_control.yaml"
VERSION = "wind12_residual_random_v1"
STAGES = ("pitch_speed", "all")


def protocol(path):
    import yaml
    p = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if p["version"] != VERSION or p["seed"] != 42 or p["run_ids"] != [0, 1, 2]:
        raise ValueError("residual protocol and three seed42 streams required")
    if (p["steps_per_run"], p["eval_every"], p["horizon"]) != (8192, 2048, 128):
        raise ValueError("fixed bounded budgets required")
    if p["residual"] != dict(ramp_steps=4096, speed_start_rad_s=.02, speed_final_rad_s=.1,
            yaw_start_deg=1., yaw_final_deg=5., handover_action_atol=2e-6):
        raise ValueError("predeclared residual envelope required")
    if p["engineering_gate"] != dict(max_parent_mean_ratio=1.05, max_parent_worst_ratio=1.05, max_final_over_selected=1.25):
        raise ValueError("fixed engineering gates required")
    groups = [set(p[k]) for k in ("training_targets_w", "validation_targets_w", "test_targets_w")]
    if any(groups[a] & groups[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("disjoint targets required")
    return p


def scales(p, cfg, stage, step, control=False):
    import numpy as np
    width = np.asarray(cfg["environment"]["action_high"]) - cfg["environment"]["action_low"]
    fraction = min(1., max(0., step / p["residual"]["ramp_steps"]))
    speed = .1 if stage == "all" else .02 + .08 * fraction
    yaw = np.deg2rad(1 + 4 * fraction) if stage == "all" and not control else 0.
    if stage == "pitch_speed" and control:
        speed = 0.
    return (float(2 * yaw / width[0]), 1., float(2 * speed / width[2]))


def score(rows):
    import numpy as np
    return float(np.mean([r["rmse_w"] for r in rows])), max(r["rmse_w"] for r in rows)


def prepare(p, output):
    import yaml
    source = Path(p["bootstrap_experiment"]).resolve()
    old = json.loads((source / "selection.json").read_text(encoding="utf-8"))
    bootstrap = {}
    for run in p["run_ids"]:
        r = next(r for r in old["results"] if r["stage"] == "pitch" and r["run_id"] == run)
        verify_hashes(r["hashes"])
        path = r["best"]["checkpoint"]
        bootstrap[str(run)] = dict(checkpoint=path, sha256=digest(path),
            cumulative_steps=r["cumulative_steps"] - r["steps"] + r["best"]["step"])
    root = shared.prepare(p, output)
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    saved["bootstrap"] = bootstrap
    files = [Path(__file__).with_name(n) for n in ("residual_algorithm.py", "residual_random_control.py",
        "verify_residual.py", "RESIDUAL_RANDOM_CONTROL.md", "algorithm.py", "random_wind_training.py", "controllers.py", "workflow.py")]
    files += [DEFAULT] + [Path(v["checkpoint"]) for v in bootstrap.values()]
    for name in ("20261023_progressive_random_control", "20261023_joint_distillation"):
        files += [source.parent / name / n for n in ("config.yaml", "metrics.csv", "summary.txt")]
    saved["source_hashes"].update({str(f.resolve()): digest(f) for f in files})
    (root / "config.yaml").write_text(yaml.safe_dump(saved, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n")
    for phase, stage in enumerate(STAGES):
        phase_p = deepcopy(p)
        phase_p["training_episode_offset"] += phase * 10000
        shared.write_csv(root / f"{stage}_wind_preflight.csv", shared.preflight_training_winds(phase_p, root))
    return root


def parent_for(root, stage, run):
    import yaml
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    p = saved["protocol"]
    if stage not in STAGES or run not in p["run_ids"]:
        raise ValueError("unknown residual worker")
    if (root / "selection.json").exists() or (root / "test").exists():
        raise ValueError("frozen selection prohibits additional training")
    verify_hashes(saved["source_hashes"])
    if stage == "pitch_speed":
        return saved["bootstrap"][str(run)]
    parents = []
    for i in p["run_ids"]:
        path = root / f"pitch_speed_run_{i}/result.json"
        if not path.exists():
            raise ValueError("all speed streams must finish before yaw")
        r = json.loads(path.read_text(encoding="utf-8"))
        if not engineering_pass(r, p):
            raise ValueError("all speed streams must pass before yaw")
        verify_hashes(r["hashes"])
        parents.append(r)
    r = next(r for r in parents if r["run_id"] == run)
    return dict(checkpoint=r["best"]["checkpoint"], sha256=digest(r["best"]["checkpoint"]),
        cumulative_steps=r["lineage"]["cumulative_parent_steps"] + r["best"]["step"])


def engineering_pass(r, p):
    mean, worst = score(r["best"]["validation"])
    return bool(r["steps"] == p["steps_per_run"] and r["handover"]["passed"]
        and mean <= 1.05 * r["lineage"]["parent_mean_w"]
        and worst <= 1.05 * r["lineage"]["parent_worst_w"] and r["final_over_selected"] <= 1.25)


def next_segment(job):
    numbers = [int(path.name.split("_")[1]) for path in Path(job).glob("segment_*") if path.is_dir()]
    return max(numbers, default=-1) + 1


def initialize(parent, stage, p, cfg, control):
    import numpy as np
    import torch
    from .residual_algorithm import ResidualMADDPG, load_policy
    original, meta = load_policy(parent["checkpoint"])
    verify_hashes({parent["checkpoint"]: parent["sha256"]})
    mask = tuple(original.config.action_mask) if control else tuple(dict(shared.STAGES)[stage])
    child = ResidualMADDPG.inherit(original, mask, scales(p, cfg, stage, p["steps_per_run"], control), open_channel=not control)
    maximum = 0.
    for key in ("obs", "next_obs"):
        data = original.replay.data[key][:original.replay.size]
        for kind in ("actors", "target_actors"):
            for i, (old_actor, new_actor) in enumerate(zip(getattr(original, kind), getattr(child, kind))):
                states = torch.as_tensor(data[:, i], device=child.device)
                with torch.no_grad():
                    error = (original.policy(old_actor, states) - child.policy(new_actor, states)).abs().max().item()
                maximum = max(maximum, error)
    if maximum > p["residual"]["handover_action_atol"]:
        raise AssertionError("zero-head handover changed parent total references")
    # Compare all unchanged parameters and every training state inherited by design.
    new_channel = next((j for j in range(3) if mask[j] and not original.config.action_mask[j]), None)
    for kind in ("actors", "target_actors", "critics", "target_critics"):
        for key, value in getattr(original, kind).state_dict().items():
            current = getattr(child, kind).state_dict()[key]
            if kind in ("actors", "target_actors") and key.split(".", 1)[1] in ("4.weight", "4.bias") and new_channel is not None:
                keep = [j for j in range(3) if j != new_channel]
                assert torch.equal(value[keep], current[keep])
            else:
                assert torch.equal(value, current)
    np.testing.assert_equal(original.replay.state_dict(), child.replay.state_dict())
    assert original.rng.bit_generator.state == child.rng.bit_generator.state
    return child, original, meta, maximum


def train(root, stage, run, *, control=False, stop_after=None):
    import numpy as np
    import torch
    import yaml
    from .residual_algorithm import ResidualMADDPG
    from .workflow import build_env
    from .stable_workflow import Exploration
    from .benchmark import seed_for
    from ..environments.farm_inflow import generate_inflow
    root = Path(root).resolve()
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    p = saved["protocol"]
    parent = parent_for(root, stage, run)
    label = stage + ("_control" if control else "")
    job = root / f"{label}_run_{run}"
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    if (job / "result.json").exists():
        result = json.loads((job / "result.json").read_text(encoding="utf-8"))
        verify_hashes(result["hashes"])
        return result
    cfg = deepcopy(saved["base_config"])
    if control:
        cfg["environment"]["control_mask"] = [0, 1, 0] if stage == "pitch_speed" else [0, 1, 1]
    else:
        cfg["environment"]["control_mask"] = dict(shared.STAGES)[stage]
    env = build_env(cfg)
    phase = STAGES.index(stage)
    noise_std = p["stage_noise_std"]["pitch" if control and stage == "pitch_speed" else "pitch_speed" if control else stage]
    noise = Exploration(seed_for(42, 1013 + phase, run), noise_std, [10., 3., 5.], env.dt, "white", p["noise_end_fraction"])
    identity = dict(stage=stage, run_id=run, control=control, parent=parent, root_config_sha256=digest(root / "config.yaml"))
    if job.exists():
        previous = sorted(job.glob("segment_*/state.json"))
        if not previous:
            raise ValueError("incomplete initialization: preserve directory and use a fresh experiment")
        last = json.loads(previous[-1].read_text(encoding="utf-8"))
        agent, meta = ResidualMADDPG.load(last["checkpoint"])
        if meta["identity"] != identity or meta["normalization"] != env.normalization():
            raise ValueError("resume identity mismatch")
        step, episode, history, best = meta["step"], meta["episode"], meta["history"], meta["best"]
        initial, lineage, handover = meta["initial"], meta["lineage"], meta["handover"]
        noise.load_state_dict(meta["noise"])
        segment = next_segment(job)
        final = last["checkpoint"]
    else:
        agent, original, original_meta, maximum = initialize(parent, stage, p, cfg, control)
        old_rows, _ = shared.rollout(original_meta["config"], shared.cases(root, "validation"), agent=original)
        rows, _ = shared.rollout(cfg, shared.cases(root, "validation"), agent=agent)
        pm, pw = score(old_rows)
        mean, worst = score(rows)
        handover = dict(max_replay_total_action_error=maximum, replay_observations_checked=2 * original.replay.size,
            initial_mean_w=mean, initial_worst_w=worst, passed=maximum <= 2e-6 and mean <= pm * 1.05 and worst <= pw * 1.05)
        lineage = dict(parent_checkpoint=parent["checkpoint"], parent_sha256=parent["sha256"],
            cumulative_parent_steps=parent["cumulative_steps"], inherited_replay_size=original.replay.size,
            inherited_updates=original.updates, parent_mean_w=pm, parent_worst_w=pw,
            actor_optimizer_reset=True, critic_optimizer_replay_rng_inherited=True)
        job.mkdir()
        shared.write_json(job / "handover.json", dict(**handover, lineage=lineage))
        step = episode = segment = 0
        history = []
        best = initial = None
    out = job / f"segment_{segment:03d}"
    out.mkdir()
    full = scales(p, cfg, stage, p["steps_per_run"], control)

    def snapshot(losses):
        nonlocal best, initial
        training = scales(p, cfg, stage, step, control)
        agent.config = replace(agent.config, residual_scales=full)
        rows, _ = shared.rollout(cfg, shared.cases(root, "validation"), agent=agent)
        mean, worst = score(rows)
        path = str((out / f"step_{step:08d}.pth").resolve())
        if initial is None:
            initial = path
        if best is None or mean < best["score_w"]:
            best = dict(checkpoint=path, score_w=mean, step=step, validation=rows)
        history.append(dict(steps=step, validation_rmse_w=mean, worst_validation_rmse_w=worst,
            best_rmse_w=best["score_w"], actor_loss=float(np.mean([l["actor_loss"] for l in losses])) if losses else 0.,
            critic_loss=float(np.mean([l["critic_loss"] for l in losses])) if losses else 0.))
        agent.save(path, dict(identity=identity, config=cfg, normalization=env.normalization(), step=step, episode=episode,
            history=history, best=best, initial=initial, lineage=lineage, handover=handover,
            training_scales=training, evaluation_scales=full, noise=noise.state_dict()))
        shared.write_csv(out / "metrics.csv", history)
        shared.write_json(out / "state.json", dict(checkpoint=path, step=step, completed=step == p["steps_per_run"]))
        agent.config = replace(agent.config, residual_scales=training)
        print(json.dumps(dict(stage=label, run_id=run, **history[-1])), flush=True)
        return path

    if step == 0:
        final = snapshot([])
    if not handover["passed"]:
        raise AssertionError("zero-head closed-loop handover failed: preserve artifacts, no training")
    if stop_after is not None and (stop_after % p["eval_every"] or not step < stop_after <= p["steps_per_run"]):
        raise ValueError("stop_after must be a later declared evaluation boundary")
    losses = []
    while step < p["steps_per_run"]:
        family, target, pitch = shared.episode_design(p, run, episode)
        inflow = deepcopy(p["inflow"])
        inflow["speed"]["scenario"] = family
        wind = generate_inflow(inflow, dt_s=env.dt, horizon=env.horizon, seed=42, split="train",
            episode=p["training_episode_offset"] + phase * 10000 + run * 1000 + episode)
        env.initial = np.asarray(cfg["environment"]["initial_operating_point"], dtype=float).copy()
        env.initial[1] = pitch
        obs, _ = env.reset(seed=42, options=dict(wind_trajectory=wind.values, target_w=target))
        noise.reset()
        for _ in range(env.horizon):
            agent.config = replace(agent.config, residual_scales=scales(p, cfg, stage, step, control))
            action = agent.act(obs, noise=noise.sample(step / p["steps_per_run"]))
            projected = env.project_action(action)
            np.testing.assert_allclose(action, projected, atol=3e-6, rtol=0)
            nxt, reward, done, _, info = env.step(action)
            np.testing.assert_array_equal(info["executed_action"], projected)
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
    result = dict(stage=label, run_id=run, config=cfg, initial=initial, best=best, final=final, steps=step,
        final_over_selected=ratio, lineage=lineage, handover=handover, resume_segments=segment + 1,
        inherited_replay_size=lineage["inherited_replay_size"],
        strict_accuracy_pass=best["score_w"] <= 400000 and score(best["validation"])[1] <= 500000 and ratio <= 1.25,
        hashes={path: digest(path) for path in set((initial, best["checkpoint"], final))})
    result["engineering_pass"] = engineering_pass(result, p)
    shared.write_json(job / "result.json", result)
    return result


class Monitor:
    def __init__(self, agent, cfg):
        import numpy as np
        self.agent = agent
        self.width = np.asarray(cfg["environment"]["action_high"]) - cfg["environment"]["action_low"]
        self.corrections, self.raw, self.total = [], [], []

    def act(self, obs):
        import numpy as np
        import torch
        from .residual_algorithm import ResidualMADDPG
        action = self.agent.act(obs)
        if isinstance(self.agent, ResidualMADDPG):
            with torch.no_grad():
                x = torch.as_tensor(obs, device=self.agent.device)
                raw = torch.stack([actor(x[i]) for i, actor in enumerate(self.agent.actors)])
                baseline = self.agent.compose(torch.zeros_like(raw), x).cpu().numpy()
                correction = (action - baseline) * self.width / 2
                correction[:, 1] = 0.
                self.raw.append(raw.cpu().numpy() * np.asarray(self.agent.config.action_mask))
        else:
            correction = np.zeros_like(action)
            self.raw.append(np.zeros_like(action))
        self.corrections.append(correction)
        self.total.append(action)
        return action

    def summary(self):
        import numpy as np
        correction, raw, total = map(np.asarray, (self.corrections, self.raw, self.total))
        return dict(speed_correction_rms_rad_s=float(np.sqrt(np.mean(correction[..., 2] ** 2))),
            speed_correction_max_rad_s=float(np.abs(correction[..., 2]).max()),
            yaw_correction_rms_rad=float(np.sqrt(np.mean(correction[..., 0] ** 2))),
            yaw_correction_max_rad=float(np.abs(correction[..., 0]).max()),
            speed_raw_saturation_fraction=float(np.mean(np.abs(raw[..., 2]) >= .99)),
            yaw_raw_saturation_fraction=float(np.mean(np.abs(raw[..., 0]) >= .99)),
            speed_total_clip_fraction=float(np.mean(np.abs(total[..., 2]) >= 1 - 1e-6)))


def release_test(root):
    import yaml
    from .residual_algorithm import load_policy
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
            monitor = Monitor(agent, meta["config"])
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
        raise ValueError("selection frozen; no additional training")
    results, gates = [], []
    for stage in STAGES:
        for run in saved["protocol"]["run_ids"]:
            for control in (False, True):
                command = [sys.executable, "-B", "-X", "utf8", "-m", __spec__.name, "worker", "--output", str(root), "--stage", stage, "--run-id", str(run)]
                if control:
                    command.append("--control")
                subprocess.run(command, check=True)
                label = stage + ("_control" if control else "")
                results.append(json.loads((root / f"{label}_run_{run}/result.json").read_text(encoding="utf-8")))
        children = [r for r in results if r["stage"] == stage]
        gate = dict(stage=stage, passed=all(engineering_pass(r, saved["protocol"]) for r in children),
            passed_runs=sum(engineering_pass(r, saved["protocol"]) for r in children), runs=len(children))
        gates.append(gate)
        shared.write_csv(root / "metrics.csv", [dict(stage=r["stage"], run_id=r["run_id"], steps=r["steps"], selected_step=r["best"]["step"],
            selected_validation_rmse_w=r["best"]["score_w"], worst_validation_rmse_w=score(r["best"]["validation"])[1],
            final_over_selected=r["final_over_selected"], engineering_pass=r["engineering_pass"], strict_accuracy_pass=r["strict_accuracy_pass"]) for r in results])
        shared.write_json(root / "stage_gates.json", gates)
        print("Residual stage gate", json.dumps(gate), flush=True)
        if not gate["passed"]:
            break
    hashes = {path: value for r in results for path, value in r["hashes"].items()}
    hashes.update({r["lineage"]["parent_checkpoint"]: r["lineage"]["parent_sha256"] for r in results})
    shared.write_json(root / "selection.json", dict(seed=42, results=results, gates=gates, hashes=hashes,
        root_config_sha256=digest(root / "config.yaml"), bank_sha256=digest(root / "bank/manifest.json")))
    release_test(root)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("prepare", "run", "all", "worker"))
    ap.add_argument("--output", required=True)
    ap.add_argument("--protocol", default=str(DEFAULT))
    ap.add_argument("--stage", choices=STAGES, default="pitch_speed")
    ap.add_argument("--run-id", type=int, default=0)
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--stop-after", type=int)
    a = ap.parse_args()
    p = protocol(a.protocol)
    activate_runtime(p["runtime_site_packages"])
    sys.dont_write_bytecode = True
    root = Path(a.output)
    if a.command in ("prepare", "all"):
        root = prepare(p, root)
    if a.command in ("run", "all"):
        execute(root)
    if a.command == "worker":
        train(root, a.stage, a.run_id, control=a.control, stop_after=a.stop_after)


if __name__ == "__main__":
    main()
