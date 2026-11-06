"""Bounded compatibility and restart checks. This module has no training entry point."""
from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from .fixed_pinn_demo import activate_runtime, digest
from .pitch_cross_wind_diagnostic import ORIGINAL
from .pitch_integral_diagnostic import size
from .pitch_nstep_trial import read_json, verify

MODULE = "optimization_control.maddpg_wind_farm.pitch_error_memory_engineering"
PROJECT = Path(__file__).resolve().parents[2]
EXPERIMENTS = PROJECT / "optimization_control/experiments"
PARENTS = EXPERIMENTS / "20261028_pitch_nstep_mechanism/candidate_manifest.json"
INTEGRAL = EXPERIMENTS / "20261030_pitch_integral_feasibility"
ROW_LIMIT = 4096
UPDATE_LIMIT = 24
STORAGE_LIMIT = 256 * 1024**2
EPISODE_STEPS = 32


def write(root, filename, data):
    if size(root) + len(data) > STORAGE_LIMIT:
        raise RuntimeError("engineering storage cap")
    with (root / filename).open("xb") as handle:
        handle.write(data)


def write_json(root, filename, data):
    write(root, filename, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf8"))


def charge(root, filename, limit, label):
    path = root / filename
    count = len(path.read_bytes().splitlines()) if path.exists() else 0
    data = (label + "\n").encode("ascii")
    if count >= limit or size(root) + len(data) > STORAGE_LIMIT:
        raise RuntimeError(f"engineering budget reached: {filename}")
    with path.open("ab", buffering=0) as handle:
        handle.write(data)


def update(root, agent, label):
    charge(root, "updates.log", UPDATE_LIMIT, label)
    return agent.update()


def same(expected, actual, location="root"):
    import numpy as np
    import torch
    if type(expected) is not type(actual):
        raise AssertionError(f"type mismatch at {location}")
    if isinstance(expected, dict):
        if expected.keys() != actual.keys():
            raise AssertionError(f"field mismatch at {location}")
        for key in expected:
            same(expected[key], actual[key], f"{location}.{key}")
        return
    if isinstance(expected, (tuple, list)):
        if len(expected) != len(actual):
            raise AssertionError(f"length mismatch at {location}")
        for index, (left, right) in enumerate(zip(expected, actual)):
            same(left, right, f"{location}[{index}]")
        return
    if isinstance(expected, torch.Tensor):
        equal = expected.dtype == actual.dtype and torch.equal(expected, actual)
    elif isinstance(expected, np.ndarray):
        equal = expected.dtype == actual.dtype and np.array_equal(expected, actual)
    else:
        equal = expected == actual
    if not equal:
        raise AssertionError(f"value mismatch at {location}")


def state(agent):
    from dataclasses import asdict
    import torch
    from .pitch_error_memory import NETWORKS, OPTIMIZERS
    result = dict(config=asdict(agent.config), replay=agent.replay.state_dict(), updates=agent.updates,
                  rng=agent.rng.bit_generator.state, torch_rng=torch.get_rng_state())
    result.update({name: getattr(agent, name).state_dict() for name in NETWORKS})
    result.update({name: [o.state_dict() for o in getattr(agent, name)] for name in OPTIMIZERS})
    return result


def legacy(agent):
    from .pitch_error_memory import NETWORKS, OPTIMIZERS
    view = state(agent)
    for name in NETWORKS:
        view[name] = type(view[name])(
            (k, v) for k, v in view[name].items() if not k.endswith(".memory_weight")
        )
    for name in OPTIMIZERS:
        for optimizer in view[name]:
            added = optimizer["param_groups"].pop()
            for key in added["params"]:
                optimizer["state"].pop(key, None)
    for key in ("integral", "next_integral"):
        del view["replay"]["data"][key]
    return view


def recorded_update(root, agent, label):
    import torch
    original = torch.nn.utils.clip_grad_norm_
    records = []

    def record(parameters, *args, **kwargs):
        params = list(parameters)
        before = [p.grad.detach().clone() for p in params if p.grad is not None]
        norm = original(params, *args, **kwargs)
        after = [p.grad.detach().clone() for p in params if p.grad is not None]
        records.append(dict(before=before, after=after, norm=norm.clone(), limit=args[0]))
        return norm

    with patch.object(torch.nn.utils, "clip_grad_norm_", record):
        stats = update(root, agent, label)
    sample = (agent.replay.last_indices, agent.replay.last_lengths, agent.replay.discounts)
    return stats, records, sample


def write_state(root, filename, agent, metadata):
    import torch
    buffer = io.BytesIO()
    torch.save(agent.checkpoint(metadata), buffer)
    write(root, filename, buffer.getbuffer())
    return buffer.tell()


def expect_rejection(fn, match):
    try:
        fn()
    except ValueError as error:
        if match not in str(error):
            raise
    else:
        raise AssertionError("incompatible state accepted")


def child(root, arm):
    import torch
    from .pitch_error_memory import PitchErrorMemory
    path = root / f"{arm}_restart_input.pth"
    source = torch.load(path, map_location="cpu", weights_only=False)
    agent, meta = PitchErrorMemory.load(path, expected_arm=arm, purpose="engineering")
    same(source, agent.checkpoint(meta))
    stats = update(root, agent, f"{arm}_child_next")
    write_state(root, f"{arm}_restart_output.pth", agent, meta)
    write_json(root, f"{arm}_child.json", dict(pid=os.getpid(), initial_fields_equal=True, stats=stats,
               sample_indices=agent.replay.last_indices.tolist(), lengths=agent.replay.last_lengths.tolist(),
               discounts=agent.replay.discounts.flatten().tolist()))


def restart(root, agent, parent_sha):
    import torch
    from .pitch_error_memory import PitchErrorMemory
    arm = agent.arm
    meta = dict(stage="engineering_discard", parent_sha256=parent_sha, seed=42, next_episode_integral=0.)
    input_bytes = write_state(root, f"{arm}_restart_input.pth", agent, meta)
    path = root / f"{arm}_restart_input.pth"
    expect_rejection(lambda: PitchErrorMemory.load(path, expected_arm=arm, purpose="formal"), "purpose")
    stats = update(root, agent, f"{arm}_local_next")
    command = [sys.executable, "-B", "-X", "utf8", "-m", MODULE, "--output", str(root), "--child", arm]
    subprocess.run(command, cwd=PROJECT, check=True)
    after = torch.load(root / f"{arm}_restart_output.pth", map_location="cpu", weights_only=False)
    same(agent.checkpoint(meta), after)
    proof = read_json(root / f"{arm}_child.json")
    same(stats, proof["stats"])
    same(agent.replay.last_indices.tolist(), proof["sample_indices"])
    same(agent.replay.last_lengths.tolist(), proof["lengths"])
    same(agent.replay.discounts.flatten().tolist(), proof["discounts"])
    assert proof["pid"] != os.getpid() and proof["initial_fields_equal"]
    return dict(arm=arm, initial_and_next_fields_equal=True, next_sample_equal=True,
                parent_pid=os.getpid(), child_pid=proof["pid"], formal_load_rejected=True,
                input_bytes=input_bytes, output_bytes=(root / f"{arm}_restart_output.pth").stat().st_size)


def closed_loop(root, env, case, wind, agent, label):
    import numpy as np
    from .pitch_action_diagnostic import reset_case
    from .pitch_error_memory import advance_integral
    obs, info = reset_case(env, case, wind)
    rows = [(obs.copy(), deepcopy(info))]
    integral = 0.
    nonzero = 0
    for _ in range(EPISODE_STEPS):
        action = agent.act(obs, integral=integral) if hasattr(agent, "arm") else agent.act(obs)
        issued = env.mapper.map(env.project_action(action)).clipped_action_normalized.astype(np.float32)
        next_integral = advance_integral(integral, obs, issued)
        following, rewards, done, truncated, info = env.step(action)
        assert not done and not truncated
        same(issued, info["executed_action"])
        rows.append((action, following.copy(), rewards.copy(), deepcopy(info), next_integral))
        obs, integral = following, next_integral
        nonzero += int(integral != 0.)
    assert nonzero > 0
    return rows, dict(label=label, nonzero_next_integral=nonzero, final_integral=integral)


def run(root):
    import numpy as np
    import torch
    import yaml
    from ..environments.farm_inflow import InflowTrace
    from .nstep_algorithm import NStepMADDPG
    from .pitch_error_memory import PitchErrorMemory, OPTIMIZERS, NETWORKS, RULE
    from .workflow import build_env

    root.mkdir(parents=True, exist_ok=False)
    old = yaml.safe_load((INTEGRAL / "config.yaml").read_text(encoding="utf8"))
    verify(old["protected_hashes"])
    verify(read_json(INTEGRAL / "input_lock.json")["hashes"])
    parents = read_json(PARENTS)["candidates"]
    assert [(p["run"], p["selected_step"]) for p in parents] == [(0, 16384), (1, 12288), (2, 4096)]
    assert all(p["selected_by_test"] is False for p in parents)
    case = next(c for c in read_json(INTEGRAL / "case_manifest.json")["cases"]
                if c["id"] == "train_episode_8_initial_0.025")
    frozen = {p["checkpoint"]: p["sha256"] for p in parents}
    protected_paths = [PARENTS, INTEGRAL / "config.yaml", INTEGRAL / "input_lock.json",
                       INTEGRAL / "case_manifest.json", Path(case["path"]),
                       Path(case["path"]).with_suffix(".json"), Path(__file__),
                       Path(__file__).with_name("pitch_error_memory.py"),
                       Path(__file__).with_name("PITCH_ERROR_MEMORY_ENGINEERING_PROTOCOL.md")]
    frozen.update({str(p): digest(p) for p in protected_paths})
    verify(frozen)
    write_json(root, "config.yaml", dict(seed=42, purpose="engineering_discard", memory_rule=RULE,
               formal_steps=0, new_test_steps=0, predictor_input_cap=ROW_LIMIT,
               joint_update_cap=UPDATE_LIMIT, artifact_cap_bytes=STORAGE_LIMIT,
               short_loop_steps=EPISODE_STEPS, case=case, protected_hashes=frozen))
    env = build_env(old["base_config"])
    predictor = env.plant.predictor

    def counted(inputs):
        if len(inputs) != 1:
            raise ValueError("expected single Plant row")
        charge(root, "plant_rows.log", ROW_LIMIT, "real")
        return predictor(inputs)

    env.plant.predictor = counted
    assert env.dt == 1 and sum(env.rated) == 15e6 and (env.low[1], env.high[1]) == (0., .22)
    wind = InflowTrace.load(case["path"])
    details, restores = [], []
    for parent in parents:
        run_id = parent["run"]
        path = parent["checkpoint"]
        original, _ = NStepMADDPG.load(path, expected_n=8)
        initial = deepcopy(state(original))
        zero, _, episodes = PitchErrorMemory.from_parent(path, "zero", purpose="engineering")
        same(initial, legacy(zero))
        memory, _, memory_episodes = PitchErrorMemory.from_parent(path, "memory", purpose="engineering")
        same(initial, legacy(memory))
        same(zero.replay.state_dict(), memory.replay.state_dict())
        assert episodes == memory_episodes == (256, 256, 224)[run_id]
        for agent in (zero, memory):
            for name in NETWORKS:
                assert all(not torch.count_nonzero(m.memory_weight) for m in getattr(agent, name))
            for name in OPTIMIZERS:
                assert all(o.param_groups[1]["params"][0] not in o.state for o in getattr(agent, name))
        loops = [closed_loop(root, env, case, wind, agent, name)
                 for agent, name in ((original, "original"), (zero, "zero"), (memory, "memory"))]
        same(loops[0][0], loops[1][0])
        same(loops[0][0], loops[2][0])
        same(initial, state(original))
        same(initial, legacy(zero))
        same(initial, legacy(memory))
        original_update = recorded_update(root, original, f"run{run_id}_old")
        zero_update = recorded_update(root, zero, f"run{run_id}_zero")
        same(original_update, zero_update)
        same(state(original), legacy(zero))
        clips = sum(float(row["norm"]) > row["limit"] for row in zero_update[1])
        assert clips > 0
        for name, models in zip(OPTIMIZERS, (zero.actors, zero.critics)):
            assert all(m.memory_weight.grad is None and m.memory_weight not in o.state
                       for m, o in zip(models, getattr(zero, name)))
        update(root, memory, f"run{run_id}_memory")
        gradients = {}
        for name, models in zip(OPTIMIZERS, (memory.actors, memory.critics)):
            magnitudes = []
            for model, optimizer, old_optimizer in zip(models, getattr(memory, name), initial[name]):
                weight = model.memory_weight
                assert torch.isfinite(weight.grad).all() and torch.count_nonzero(weight.grad)
                assert torch.count_nonzero(weight) and optimizer.state[weight]["step"].item() == 1
                current = optimizer.state_dict()
                for key, before in old_optimizer["state"].items():
                    assert current["state"][key]["step"].item() == before["step"].item() + 1
                magnitudes.append(float(weight.grad.norm()))
            gradients[name] = magnitudes
        for online, target in ((memory.actors, memory.target_actors), (memory.critics, memory.target_critics)):
            for model, target_model in zip(online, target):
                expected = torch.zeros_like(model.memory_weight).lerp_(model.memory_weight.detach(), memory.config.tau)
                same(expected, target_model.memory_weight.detach())
        details.append(dict(run=run_id, parent_sha256=parent["sha256"], full_episodes=episodes,
                            old_fields_exact=True, effective_clip_calls=clips, memory_gradient_norms=gradients,
                            zero_adam_uninitialized=True, memory_adam_first_step=1, target_exact=True,
                            short_loop_equal=True, loop=[row[1] for row in loops]))
        print(f"Verified parent {run_id}: {episodes} reconstructed episodes", flush=True)
        if run_id == 0:
            restores = [restart(root, agent, parent["sha256"]) for agent in (zero, memory)]
            expect_rejection(lambda: PitchErrorMemory.load(path, expected_arm="zero", purpose="engineering"), "format")
            # Exercise the real loader with a wrong rule without saving another replay copy.
            import copy
            valid = torch.load(root / "memory_restart_input.pth", map_location="cpu", weights_only=False)
            invalid = copy.copy(valid)
            invalid["memory_rule"] = "different_rule"
            with patch.object(torch, "load", return_value=invalid):
                expect_rejection(lambda: PitchErrorMemory.load(path, expected_arm="memory", purpose="engineering"), "rule")
            del valid, invalid
    verify(frozen)
    verify(old["protected_hashes"])
    rows = (root / "plant_rows.log").read_bytes().splitlines()
    updates = (root / "updates.log").read_bytes().splitlines()
    assert rows == [b"real"] * 297 and len(updates) == 13
    proof = dict(status="passed", parents=details, restores=restores, real_rows=len(rows), mock_rows=0,
                 discarded_joint_updates=len(updates), formal_training_steps=0, new_test_steps=0,
                 old_format_and_wrong_rule_rejected=True, artifacts_before_reports_bytes=size(root),
                 artifact_limit_bytes=STORAGE_LIMIT)
    write_json(root, "verification.json", proof)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["run", "episodes", "old_update_exact", "effective_clip_calls", "short_loop_exact", "real_memory_gradients"])
    for row in details:
        writer.writerow([row["run"], row["full_episodes"], True, row["effective_clip_calls"], True, True])
    write(root, "metrics.csv", buffer.getvalue().encode("utf8"))
    write(root, "summary.txt", b"Engineering passed. 297 real Plant rows, 0 mock, 13 discarded joint updates.\n"
          b"Three original/zero comparisons, three zero-initialized memory takeovers, both arm restarts.\n"
          b"Formal steps and new test rows: 0. See verification.json and the engineering protocol.\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--child", choices=("zero", "memory"))
    args = parser.parse_args()
    activate_runtime(ORIGINAL / ".venv/pinn_tf216")
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    root = args.output.resolve()
    if args.child:
        child(root, args.child)
    else:
        run(root)


if __name__ == "__main__":
    main()
