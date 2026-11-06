"""Audit a frozen inherited training run without changing saved policies."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .fixed_pinn_demo import activate_runtime, digest


def verify(root):
    import numpy as np
    import torch
    import yaml
    from .algorithm import MADDPG
    from .progressive_random_control import initialize_heads, passes, verify_hashes
    from .random_wind_training import STAGES, write_json
    root = Path(root)
    selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8")); p = saved["protocol"]
    verify_hashes(saved["source_hashes"]); verify_hashes(selection["hashes"])
    assert selection["root_config_sha256"] == digest(root / "config.yaml")
    assert selection["bank_sha256"] == digest(root / "bank/manifest.json")
    stages = list(dict.fromkeys(r["stage"] for r in selection["results"]))
    assert stages == [s for s, _ in STAGES[:len(stages)]]
    for index, stage in enumerate(stages):
        if index:
            previous = [r for r in selection["results"] if r["stage"] == stages[index - 1]]
            assert len(previous) == 3 and all(passes(r, p) for r in previous)
        assert {r["run_id"] for r in selection["results"] if r["stage"] == stage} == {0, 1, 2}
    rows, head_readiness = [], []
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    for result in selection["results"]:
        initial, meta = MADDPG.load(result["initial"])
        parent, _ = MADDPG.load(result["lineage"]["parent_checkpoint"])
        reports = initialize_heads(parent, initial.config.action_mask,
                                   max_action_error=p["head_max_action_error"], strict=False)
        assert asdict(initial.config) == asdict(parent.config)
        for name in ("actors", "target_actors", "critics", "target_critics"):
            assert all(torch.equal(v, getattr(parent, name).state_dict()[k])
                       for k, v in getattr(initial, name).state_dict().items())
        for name in ("actor_optimizers", "critic_optimizers"):
            for a, b in zip(getattr(initial, name), getattr(parent, name)):
                a, b = a.state_dict(), b.state_dict()
                assert a["param_groups"] == b["param_groups"]
                assert a["state"].keys() == b["state"].keys()
                for key in a["state"]:
                    assert all(torch.equal(value, b["state"][key][field]) for field, value in a["state"][key].items())
        a, b = initial.replay.state_dict(), parent.replay.state_dict()
        assert (a["size"], a["position"], a["rng"]) == (b["size"], b["position"], b["rng"])
        for key in a["data"]:
            np.testing.assert_array_equal(a["data"][key], b["data"][key])
        assert initial.rng.bit_generator.state == parent.rng.bit_generator.state and initial.updates == parent.updates
        assert meta["lineage"]["head_initialization"] == reports
        for label, path in (("initial", result["initial"]), ("selected", result["best"]["checkpoint"]), ("final", result["final"])):
            before = digest(path)
            agent, _ = MADDPG.load(path); other, _ = MADDPG.load(path)
            obs = agent.replay.data["obs"][0]
            np.testing.assert_array_equal(agent.act(obs, .03), other.act(obs, .03))
            assert agent.update() == other.update()
            assert digest(path) == before
        rows.append(dict(stage=result["stage"], run_id=result["run_id"], inherited_state_exact=True,
            updates_at_initial=initial.updates, replay_at_initial=initial.replay.size,
            checkpoint_reload_action_noise_and_next_update_exact=True,
            best_step=result["best"]["step"], passed=passes(result, p)))
        if result["stage"] == stages[-1] and len(stages) < len(STAGES):
            probe, _ = MADDPG.load(result["best"]["checkpoint"])
            reports = initialize_heads(probe, STAGES[len(stages)][1], strict=False)
            maximum_error = max(v["held_out_max_action_error"] for v in reports)
            head_readiness.append(dict(stage=result["stage"], run_id=result["run_id"],
                next_stage=STAGES[len(stages)][0], held_out_max_action_error=maximum_error,
                fit_passed=maximum_error <= p["head_max_action_error"], permission_granted=False,
                source="selected_training_replay_only", new_environment_rollouts=0, reports=reports))
    # Phase-specific preflight tables are authoritative; the generic shared file
    # is only the most recently prepared phase, not the current training stage.
    import csv
    import hashlib
    from copy import deepcopy
    from ..environments.farm_inflow import generate_inflow
    from .random_wind_training import episode_design
    wind_count = 0
    for index, stage in enumerate(stages):
        with (root / f"{stage}_wind_preflight.csv").open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                run, episode = int(row["run_id"]), int(row["episode"])
                family, target, pitch = episode_design(p, run, episode)
                assert family == row["family"] and target == float(row["target_w"]) and pitch == float(row["initial_pitch_rad"])
                inflow = deepcopy(p["inflow"]); inflow["speed"]["scenario"] = family
                trace = generate_inflow(inflow, dt_s=p["dt_s"], horizon=p["horizon"], seed=42, split="train",
                    episode=p["training_episode_offset"] + index * 10000 + run * 1000 + episode)
                assert hashlib.sha256(trace.values.tobytes()).hexdigest() == row["values_sha256"]
                wind_count += 1
    # Prove reported test errors are computed from the saved power trajectories.
    grouped = {}
    with (root / "test/trajectories.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = tuple(row[k] for k in ("stage", "run_id", "controller", "case_id"))
            error = float(row["farm_power_w"]) - float(row["target_w"])
            assert abs(error - float(row["error_w"])) < 1e-8
            grouped.setdefault(key, []).append(error)
    maximum = 0.; count = 0
    with (root / "test/metrics.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = tuple(row[k] for k in ("stage", "run_id", "controller", "case_id"))
            value = float(np.sqrt(np.mean(np.square(grouped[key]))))
            maximum = max(maximum, abs(value - float(row["rmse_w"]))); count += 1
    assert maximum < 1e-7
    report = dict(seed=42, inherited_state_audit=rows, permission_order_and_gates_verified=True,
        test_metric_rows=count, test_trace_rows=sum(map(len, grouped.values())), max_rmse_recompute_difference_w=maximum,
        protected_files=len(saved["source_hashes"]), protected_files_unchanged=True, checkpoints_unchanged=True,
        regenerated_training_wind_episodes=wind_count,
        offline_next_head_readiness=head_readiness,
        new_training=False, physical_validation=False)
    write_json(root / "verification.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True); args = ap.parse_args()
    activate_runtime(".venv/pinn_tf216")
    verify(args.output)


if __name__ == "__main__":
    main()
