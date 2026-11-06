"""Read-only frozen-experiment closeout; all artifacts go to a separate worktree."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path

ORIGIN = Path(".")
SOURCE_REL = Path("optimization_control/experiments/20261024_parent_action_anchor")
COPIED = (
    "optimization_control/maddpg_wind_farm/ANCHOR_PROTOCOL.md",
    "optimization_control/maddpg_wind_farm/ANCHOR_RESULTS.md",
    "optimization_control/maddpg_wind_farm/anchor_algorithm.py",
    "optimization_control/maddpg_wind_farm/anchor_training.py",
    "optimization_control/maddpg_wind_farm/configs/anchor_training.yaml",
    "optimization_control/maddpg_wind_farm/verify_anchor.py",
    "optimization_control/tests/test_anchor_control.py",
)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def write_csv(path, rows):
    from .random_wind_training import write_csv as write
    write(path, rows)


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def checked_output(path, worktree, origin):
    path, worktree, origin = (Path(p).resolve() for p in (path, worktree, origin))
    if path == worktree or not path.is_relative_to(worktree) or path.is_relative_to(origin):
        raise ValueError("output must be a child of the isolated worktree, outside original workspace")
    return path


def validate_binding(selection, config_hash, bank_hash, release_hash):
    if selection["root_config_sha256"] != config_hash or selection["bank_sha256"] != bank_hash or release_hash != selection["selection_sha256_actual"]:
        raise ValueError("frozen config/bank/release identity mismatch")


def inventory(root):
    return {str(p.resolve()): sha(p) for p in sorted(Path(root).rglob("*")) if p.is_file()}


def verify_hashes(mapping):
    for name, expected in mapping.items():
        if not Path(name).is_file() or sha(name) != expected:
            raise ValueError("protected file changed: " + name)


def prepare(output, origin):
    import yaml
    worktree = Path(__file__).resolve().parents[2]
    output = checked_output(output, worktree, origin)
    source = origin / SOURCE_REL
    saved, selection = yaml.safe_load((source / "config.yaml").read_text(encoding="utf-8")), read_json(source / "selection.json")
    release = yaml.safe_load((source / "test/config.yaml").read_text(encoding="utf-8"))
    validate_binding(dict(selection, selection_sha256_actual=sha(source / "selection.json")), sha(source / "config.yaml"), sha(source / "bank/manifest.json"), release["selection_sha256"])
    if set(p.name for p in (source / "test").iterdir()) != {"config.yaml"}:
        raise ValueError("source test now contains other artifacts: inspect rather than silently replace")
    verify_hashes(saved["source_hashes"])
    verify_hashes(selection["hashes"])
    protected = inventory(source)
    protected.update(saved["source_hashes"])
    protected.update(selection["hashes"])
    residual_selection=read_json(origin/"optimization_control/experiments/20261023_residual_random_control/selection.json")
    for r in residual_selection["results"]:
        if r["stage"] in ("pitch_speed","all"):
            for path in (r["initial"],r["lineage"]["parent_checkpoint"]):
                protected[path]=sha(path)
    copies = []
    for name in COPIED:
        src, dst = origin / name, worktree / name
        if sha(src) != sha(dst):
            raise ValueError("copied uncommitted file differs: " + name)
        copies.append(dict(source=str(src), copy=str(dst), sha256=sha(src)))
        protected[str(src)] = sha(src)
    # Verify all pre-existing Python modules actually executed in this worktree.
    execution = {}
    for folder in ("optimization_control/maddpg_wind_farm", "optimization_control/environments", "optimization_control/utils"):
        for path in sorted((worktree / folder).glob("*.py")):
            original = origin / path.relative_to(worktree)
            if original.is_file():
                if sha(path) != sha(original):
                    raise ValueError("executed original module differs: " + str(path))
                protected[str(original)] = sha(original)
            execution[str(path)] = sha(path)
    for name in ("ANCHOR_CLOSEOUT_PROTOCOL.md",):
        path = Path(__file__).with_name(name)
        execution[str(path)] = sha(path)
    output.mkdir(parents=True, exist_ok=False)
    for name in ("audit", "diagnostic", "test", "figures"):
        (output / name).mkdir()
    cfg = dict(seed=42, source_experiment=str(source), original_workspace=str(origin), worktree=str(worktree),
        original_source_hash_count=len(saved["source_hashes"]), source_snapshot=protected,
        source_tree_files=sorted(str(p.resolve()) for p in source.rglob("*") if p.is_file()),
        copied_uncommitted=copies, executed_code_hashes=execution, protocol_sha256=sha(Path(__file__).with_name("ANCHOR_CLOSEOUT_PROTOCOL.md")),
        additional_formal_training_steps=0, source_training_steps=49152, selection_sha256=sha(source / "selection.json"),
        bank_sha256=sha(source / "bank/manifest.json"), source_test_release_sha256=sha(source / "test/config.yaml"),
        takeover=dict(action_atol=2e-6, applied_atol=1e-6, power_and_rmse_atol_w=1.),
        diagnostic=dict(split="validation", mixtures=8, zero_ablations=3, parent_swaps=4,
            variants=90, case_rollouts=540, snapshot_steps=[16,64,112],
            speed_offsets_rad_s=[-.1,-.05,-.02,0.,.02,.05,.1], yaw_offsets_deg=[-5.,-3.,-1.,0.,1.,3.,5.],
            fixed_offset_variants_per_parent=13, fixed_offset_case_rollouts=234),
        expected_test_metrics=600, expected_test_trace_rows=76800, physical_validation=False)
    (output / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
    write_json(output / "summary.txt", dict(status="prepared", seed=42, additional_formal_training_steps=0))
    print("Prepared isolated closeout", output, flush=True)
    return output


def context(root):
    import yaml
    root = Path(root).resolve()
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    checked_output(root, cfg["worktree"], cfg["original_workspace"])
    source = Path(cfg["source_experiment"])
    verify_hashes(cfg["source_snapshot"])
    verify_hashes(cfg["executed_code_hashes"])
    if sorted(str(p.resolve()) for p in source.rglob("*") if p.is_file()) != cfg["source_tree_files"]:
        raise ValueError("source experiment file inventory changed")
    saved = yaml.safe_load((source / "config.yaml").read_text(encoding="utf-8"))
    return cfg, source, saved, read_json(source / "selection.json")


_PLANTS = {}


def make_env(config):
    from .workflow import build_env
    from ..environments.maddpg_farm_env import MADDPGFarmEnv
    key = json.dumps(config["plant"], sort_keys=True)
    if key not in _PLANTS:
        _PLANTS[key] = build_env(config).plant
    return MADDPGFarmEnv(_PLANTS[key], config["environment"])


def rollout(config, cases, *, agent=None, mode=None, snapshots=None):
    """Same deterministic metrics as frozen rollout; cached stateless plant only."""
    import numpy as np
    from .controllers import PitchController
    from ..environments.maddpg_farm_env import wrap_angle
    if (agent is None) == (mode is None):
        raise ValueError("choose policy or baseline")
    env = make_env(config)
    metrics, traces, states = [], [], []
    for case, wind in cases:
        env.initial = np.asarray(config["environment"]["initial_operating_point"], dtype=float).copy()
        env.initial[1] = case["initial_pitch_rad"]
        obs, info = env.reset(seed=42, options=dict(wind_trajectory=wind.values, target_w=case["target_w"]))
        controller = PitchController(env, config["baselines"], mode) if mode else None
        errors, max_rates = [], np.zeros(3)
        previous = np.column_stack((info["heading_rad"], info["applied"][:, 1:]))
        for _ in range(env.horizon):
            action = agent.act(obs) if agent else controller.act(obs)
            projected = env.project_action(action)
            if agent and not np.allclose(action[:, ~env.control_mask], projected[:, ~env.control_mask], atol=3e-6, rtol=0):
                raise AssertionError("actor/environment inactive channel mismatch")
            obs, _, done, _, info = env.step(action)
            actual = np.column_stack((info["heading_rad"], info["applied"][:, 1:]))
            rate = np.abs(actual - previous).max(axis=0) / env.dt
            if np.any(rate > np.asarray(env.config["rate_limits"]) + 1e-7):
                raise AssertionError("physical actuator rate violation")
            previous = actual
            max_rates = np.maximum(max_rates, rate)
            np.testing.assert_allclose(info["applied"][:, 0], wrap_angle(info["heading_rad"] - info["wind"][1]), atol=1e-6, rtol=0)
            np.testing.assert_allclose(info["executed_action"], projected, atol=1e-7, rtol=0)
            errors.append(info["error_w"])
            row = dict(case_id=case["id"], split=case["split"], family=case["family"], target_w=env.target,
                initial_pitch_rad=case["initial_pitch_rad"], step=info["step"], farm_power_w=info["farm_power_w"], error_w=info["error_w"],
                wind_m_s=float(info["wind"][0]), direction_rad=float(info["wind"][1]), ti=float(info["wind"][2]))
            for i in range(3):
                row.update({f"power_{i+1}_w": float(info["power_w"][i]), f"ueff_{i+1}_m_s": float(info["effective_wind_m_s"][i]), f"heading_{i+1}_rad": float(info["heading_rad"][i])})
                for j, name in enumerate(("gamma", "pitch", "speed")):
                    row[f"{name}_{i+1}"] = float(info["applied"][i,j])
                    row[f"command_{i+1}_{j}"] = float(info["executed_action"][i,j])
            traces.append(row)
            if snapshots and info["step"] in snapshots:
                x = np.r_[info["wind"], info["applied"][:,0], info["applied"][:,1], info["applied"][:,2]]
                states.append(dict(case_id=case["id"], step=info["step"], target_w=env.target, physical=x.tolist()))
            if done:
                break
        error = np.asarray(errors)
        metrics.append(dict(case_id=case["id"], split=case["split"], family=case["family"], target_w=env.target,
            initial_pitch_rad=case["initial_pitch_rad"], rmse_w=float(np.sqrt(np.mean(error**2))), tail_rmse_w=float(np.sqrt(np.mean(error[-32:]**2))),
            mae_w=float(np.mean(np.abs(error))), mean_shortfall_w=float(np.maximum(-error,0).mean()),
            shortfall_duration_s=float(np.sum(error < -.02*env.target)*env.dt), max_heading_rate_rad_s=float(max_rates[0]),
            max_pitch_rate_rad_s=float(max_rates[1]), max_rotor_accel_rad_s2=float(max_rates[2]), final_power_w=float(info["farm_power_w"]), reachability_certified=False))
    return metrics, traces, states


def recompute(metrics, traces, keys, horizon=128):
    import numpy as np
    grouped = {}
    for row in traces:
        key = tuple(str(row[k]) for k in keys)
        grouped.setdefault(key, []).append(row)
    seen, maximum = set(), 0.
    for row in metrics:
        key = tuple(str(row[k]) for k in keys)
        if key in seen or key not in grouped:
            raise ValueError("duplicate or missing metric case")
        seen.add(key)
        part = grouped[key]
        if len(part) != horizon or [int(r["step"]) for r in part] != list(range(1,horizon+1)):
            raise ValueError("incomplete or disordered trace")
        errors = [float(r["farm_power_w"])-float(r["target_w"]) for r in part]
        if not np.isfinite(errors).all() or not np.isfinite(float(row["rmse_w"])):
            raise ValueError("nonfinite metric/trace")
        diff = abs(float(np.sqrt(np.mean(np.square(errors))))-float(row["rmse_w"]))
        maximum = max(maximum,diff)
    if seen != set(grouped) or maximum > 1e-7:
        raise ValueError("RMSE/trace identities differ")
    return dict(metric_rows=len(metrics), trace_rows=len(traces), max_rmse_difference_w=maximum)


def save_job(folder, metrics, traces, corrections=None):
    folder.mkdir(parents=True, exist_ok=False)
    write_csv(folder / "metrics.csv", metrics)
    write_csv(folder / "trajectories.csv", traces)
    if corrections is not None:
        write_json(folder / "corrections.json", corrections)
    write_json(folder / "complete.json", {p.name: sha(p) for p in folder.iterdir() if p.is_file()})


def load_job(folder):
    verify_hashes({str(folder/name): value for name,value in read_json(folder / "complete.json").items()})
    return read_csv(folder / "metrics.csv"), read_csv(folder / "trajectories.csv")


def evaluate_test(root):
    import numpy as np
    from . import random_wind_training as shared
    from .anchor_algorithm import load_policy
    from .anchor_training import DriftMonitor
    cfg, source, _, selection = context(root)
    if not (root / "diagnostic/complete.json").is_file():
        raise ValueError("validation diagnostic must freeze before reading test outcomes")
    verify_hashes({str(root/"diagnostic"/name):value for name,value in read_json(root/"diagnostic/complete.json")["artifact_hashes"].items()})
    bank = shared.cases(source, "test", allow_test=True)
    if len(bank)!=20:
        raise ValueError("original twenty-case test required")
    metrics, traces, corrections = [], [], []
    for r in selection["results"]:
        for label,path in (("initial",r["initial"]),("selected",r["best"]["checkpoint"]),("final",r["final"]),("parent",r["lineage"]["parent_checkpoint"])):
            folder = root / "test" / f"{r['stage']}_{r['run_id']}_{label}"
            if folder.exists() and not (folder / "complete.json").is_file():
                raise ValueError("incomplete output preserved; use a fresh closeout directory: " + str(folder))
            tags = dict(stage=r["stage"], run_id=r["run_id"], controller=label)
            if not folder.exists():
                agent,meta = load_policy(path)
                monitor = DriftMonitor(agent,meta["config"])
                rows,capture,_ = rollout(meta["config"],bank,agent=monitor)
                save_job(folder,[dict(**tags,**row) for row in rows],[dict(**tags,**row) for row in capture],dict(**tags,**monitor.summary()))
            rows,capture = load_job(folder)
            metrics.extend(rows); traces.extend(capture)
            corrections.append(read_json(folder / "corrections.json"))
            print("Frozen test",r["stage"],r["run_id"],label,flush=True)
    for stage in ("baseline","anchor"):
        config=next(r["config"] for r in selection["results"] if r["stage"]==stage)
        for mode in ("fixed","p","pi"):
            folder=root/"test"/f"{stage}_{mode}"
            if not folder.exists():
                rows,capture,_=rollout(config,bank,mode=mode)
                tags=dict(stage=stage,run_id=-1,controller=mode)
                save_job(folder,[dict(**tags,**row) for row in rows],[dict(**tags,**row) for row in capture])
            rows,capture=load_job(folder)
            metrics.extend(rows); traces.extend(capture)
    audit=recompute(metrics,traces,("stage","run_id","controller","case_id"))
    if audit["metric_rows"]!=600 or audit["trace_rows"]!=76800:
        raise ValueError("test completeness mismatch")
    aggregate=[]
    for stage in ("baseline","anchor"):
        for label in ("initial","selected","final","parent","fixed","p","pi"):
            for split_name, families in (("routine",shared.FAMILIES),("known_stress",("low_wind_stress",))):
                rows=[r for r in metrics if r["stage"]==stage and r["controller"]==label and r["family"] in families]
                means=[np.mean([float(r["rmse_w"]) for r in rows if str(r["run_id"])==run]) for run in sorted(set(str(r["run_id"]) for r in rows))]
                aggregate.append(dict(stage=stage,controller=label,subset=split_name,mean_rmse_w=float(np.mean(means)),std_across_runs_w=float(np.std(means,ddof=1)) if len(means)>1 else 0.))
    write_csv(root/"test/metrics.csv",metrics); write_csv(root/"test/trajectories.csv",traces)
    write_csv(root/"test/aggregate.csv",aggregate); write_csv(root/"test/corrections.csv",corrections)
    audit.update(routine_metrics=540,known_stress_metrics=60,original_release_preserved=True,new_test_draws=0)
    write_json(root/"test/verification.json",audit)
    context(root)
    print("Frozen test complete",audit,flush=True)


def audit(root):
    import numpy as np
    import torch
    from .anchor_algorithm import AnchoredMADDPG
    from .verify_anchor import audit_pairing, comparable, recovery_fork
    from .residual_random_control import scales
    from . import random_wind_training as shared
    from ..environments.farm_inflow import generate_inflow
    cfg,source,saved,selection=context(root)
    pairing=audit_pairing(source)
    checks,replays,histories=[],[],[]
    for r in selection["results"]:
        parent=torch.load(r["lineage"]["parent_checkpoint"],weights_only=False,map_location="cpu")
        initial=torch.load(r["initial"],weights_only=False,map_location="cpu")
        for key in ("actors","target_actors","critics","target_critics","critic_optimizers","replay","rng","torch_rng","updates"):
            np.testing.assert_equal(comparable(initial[key]),comparable(parent[key]))
        assert all(not o["state"] for o in initial["actor_optimizers"])
        np.testing.assert_equal(comparable(initial["teacher_actors"]),comparable(parent["actors"]))
        assert initial["teacher_config"]==parent["config"]
        for label,path in (("initial",r["initial"]),("selected",r["best"]["checkpoint"]),("final",r["final"])):
            a,meta=AnchoredMADDPG.load(path)
            assert all(not p.requires_grad and p.grad is None for p in a.teacher_actors.parameters())
            buf=io.BytesIO(); a.save(buf,meta); buf.seek(0)
            b,bmeta=AnchoredMADDPG.load(buf)
            np.testing.assert_equal(meta,bmeta)
            np.testing.assert_array_equal(a.act(a.replay.data["obs"][0],.15),b.act(b.replay.data["obs"][0],.15))
            assert a.update()==b.update()
            for key in ("actors","target_actors","critics","target_critics","teacher_actors"):
                np.testing.assert_equal(comparable(getattr(a,key).state_dict()),comparable(getattr(b,key).state_dict()))
            for key in ("actor_optimizers","critic_optimizers"):
                for left,right in zip(getattr(a,key),getattr(b,key)):
                    np.testing.assert_equal(comparable(left.state_dict()),comparable(right.state_dict()))
            np.testing.assert_equal(a.replay.state_dict(),b.replay.state_dict())
            checks.append(dict(stage=r["stage"],run_id=r["run_id"],checkpoint=label,roundtrip_action_next_update_all_states_exact=True))
        final,meta=AnchoredMADDPG.load(r["final"])
        data=final.replay.state_dict()["data"]; n=len(data["obs"])
        np.testing.assert_array_equal(data["actions"],data["next_obs"][:,:,5:8])
        e=r["config"]["environment"]; width=np.asarray(e["action_high"])-e["action_low"]
        gamma=(data["obs"][:,:,2]+1)*width[0]/2+e["action_low"][0]
        next_gamma=(data["next_obs"][:,:,2]+1)*width[0]/2+e["action_low"][0]
        theta=np.arctan2(data["obs"][:,0,11],data["obs"][:,0,12]); next_theta=np.arctan2(data["next_obs"][:,0,11],data["next_obs"][:,0,12])
        heading_delta=(next_gamma-gamma+(next_theta-theta)[:,None]+np.pi)%(2*np.pi)-np.pi
        delta=np.concatenate((heading_delta[...,None],(data["next_obs"][:,:,3:5]-data["obs"][:,:,3:5])*width[1:]/2),axis=-1)
        assert np.all(np.abs(delta).max(axis=(0,1))<=np.asarray(e["rate_limits"])*e["dt_s"]+1e-6)
        expected=e["reward_scale"]*(-data["next_obs"][:,0,9]**2-e["action_change_weight"]*np.mean((data["actions"]-data["obs"][:,:,5:8])**2,axis=(1,2)))
        np.testing.assert_allclose(data["rewards"],np.repeat(expected[:,None],3,axis=1),atol=5e-6,rtol=4e-6)
        assert n==min(final.replay.capacity,r["inherited_replay_size"]+r["steps"])
        assert final.updates-initial["updates"]==3841
        order=(np.arange(n)+final.replay.position)%final.replay.capacity if n==final.replay.capacity else np.arange(n)
        new=order[-r["steps"]:]; obs=data["obs"][new]
        scale,slope,low,high=final.config.residual_speed_schedule
        baseline=np.clip(2*(obs[:,:,1]*scale*slope-low)/(high-low)-1,-1,1)
        envelope=np.asarray([scales(saved["protocol"],r["config"],"all",s) for s in range(r["steps"])])
        assert np.all(np.abs(data["actions"][new,:,2]-baseline)<=envelope[:,2,None]+4e-6)
        assert np.all(np.abs(data["actions"][new,:,0]-final.config.fixed_action[0])<=envelope[:,0,None]+4e-6)
        terminal=obs[:,0,14]<=1/e["horizon"]+1e-7
        np.testing.assert_array_equal(data["terminated"][new,0],terminal.astype(np.float32))
        np.testing.assert_allclose(obs[:,:,8],data["next_obs"][new,:,8],atol=1e-7,rtol=0)
        assert len(meta["history"])==5 and meta["step"]==8192
        histories.extend(dict(stage=r["stage"],run_id=r["run_id"],**row) for row in meta["history"])
        replays.append(dict(stage=r["stage"],run_id=r["run_id"],retained_transitions=n,new_transitions=8192,updates_added=3841,total_commands_rewards_heading_rates_termination_envelopes_pass=True))
        print("Checkpoint/replay audit",r["stage"],r["run_id"],flush=True)
    preflight=read_csv(source/"training_wind_preflight.csv")
    for row in preflight:
        p=saved["protocol"]; inflow=deepcopy(p["inflow"]); inflow["speed"]["scenario"]=row["family"]
        episode=int(row["episode"]); run=int(row["run_id"])
        family,target,pitch=shared.episode_design(p,run,episode)
        assert family==row["family"] and target==float(row["target_w"]) and pitch==float(row["initial_pitch_rad"])
        wind=generate_inflow(inflow,dt_s=p["dt_s"],horizon=p["horizon"],seed=42,split="train",episode=p["training_episode_offset"]+run*1000+episode)
        assert hashlib.sha256(wind.values.tobytes()).hexdigest()==row["values_sha256"]
    recovery=recovery_fork(source,saved["protocol"],next(r for r in selection["results"] if r["stage"]=="baseline" and r["run_id"]==0))
    report=dict(seed=42,pairing=pairing,checkpoint_checks=checks,replay_checks=replays,training_wind_rows=len(preflight),
        recovery_fork=recovery,retained_transitions=sum(r["retained_transitions"] for r in replays),source_training_steps=49152,
        additional_formal_training_steps=0,discarded_recovery_environment_steps=256,discarded_roundtrip_update_calls=36,source_unchanged=True)
    write_csv(root/"audit/history.csv",histories)
    write_csv(root/"audit/replay.csv",replays)
    write_json(root/"audit/verification.json",report)
    context(root)
    print("Audit complete",flush=True)


def finish(root):
    cfg,_,_,selection=context(root)
    for name in ("audit/verification.json","diagnostic/complete.json","test/verification.json","figures/complete.json"):
        if not (root/name).is_file():
            raise ValueError("required closeout stage missing: "+name)
    rows=[]
    for r in selection["results"]:
        rows.append(dict(stage=r["stage"],run_id=r["run_id"],selected_step=r["best"]["step"],selected_mean_w=r["best"]["score_w"],
            final_mean_w=r["final_mean_w"],final_worst_w=r["final_worst_w"],final_over_selected=r["final_over_selected"],
            final_parent_noninferior=r["final_parent_noninferior"],paired_final_noninferior=r["paired_final_noninferior"],strict_accuracy_pass=r["strict_accuracy_pass"],learned_selected=r["learned_selected"]))
    write_csv(root/"metrics.csv",rows)
    write_json(root/"summary.txt",dict(seed=42,status="completed",source_experiment=cfg["source_experiment"],source_training_steps=49152,
        additional_formal_training_steps=0,source_unchanged=True,original_test_release_preserved=True,new_test_draws=0,
        original_gates=selection["gates"],test=read_json(root/"test/verification.json"),
        diagnostic=read_json(root/"diagnostic/complete.json"),audit=read_json(root/"audit/verification.json"),physical_validation=False))
    products={str(p.relative_to(root)):sha(p) for p in root.rglob("*") if p.is_file() and "mpl_cache" not in p.parts and p.name!="output_manifest.json"}
    write_json(root/"output_manifest.json",products)
    print("CLOSEOUT COMPLETED",root,flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command",choices=("prepare","audit","diagnose","test","figures","finish","all"))
    ap.add_argument("--output",required=True); ap.add_argument("--origin",default=str(ORIGIN))
    args=ap.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path(args.origin)/".venv/pinn_tf216")
    import torch
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    root=Path(args.output).resolve()
    os.environ.setdefault("MPLCONFIGDIR",str(root/"figures/mpl_cache"))
    if args.command in ("prepare","all"):
        prepare(root,Path(args.origin).resolve())
    if args.command in ("audit","all"): audit(root)
    if args.command in ("diagnose","all"):
        from .anchor_closeout_diagnostic import diagnose
        diagnose(root)
    if args.command in ("test","all"): evaluate_test(root)
    if args.command in ("figures","all"):
        from .anchor_closeout_figures import figures
        figures(root)
    if args.command in ("finish","all"): finish(root)


if __name__=="__main__": main()
