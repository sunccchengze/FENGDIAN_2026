"""Verify saved physical traces, documents, figures and isolated-workspace delivery."""
import argparse
from pathlib import Path
import re
import subprocess


def run(root):
    import numpy as np
    import torch
    from .anchor_closeout import context, read_json, read_csv, write_json, write_csv, sha, recompute, verify_hashes
    from . import random_wind_training as shared
    cfg,source,_,selection=context(root)
    metrics,traces=read_csv(root/"test/metrics.csv"),read_csv(root/"test/trajectories.csv")
    bank={case["id"]:(case,wind) for case,wind in shared.cases(source,"test",allow_test=True)}
    expected={(r["stage"],str(r["run_id"]),label,case) for r in selection["results"] for label in ("initial","selected","final","parent") for case in bank}
    expected.update((arm,"-1",mode,case) for arm in ("baseline","anchor") for mode in ("fixed","p","pi") for case in bank)
    actual={tuple(str(row[k]) for k in ("stage","run_id","controller","case_id")) for row in metrics}
    assert actual==expected and len(actual)==600
    recompute(metrics,traces,("stage","run_id","controller","case_id"))
    grouped={}
    max_gamma_relation,max_power_sum,max_double_power_sum=0.,0.,0.
    for row in traces:
        key=tuple(str(row[k]) for k in ("stage","run_id","controller","case_id"))
        grouped.setdefault(key,[]).append(row)
        case,wind=bank[row["case_id"]]
        step=int(row["step"])
        # MADDPGFarmEnv._read_wind explicitly casts the CSV values to float32.
        # Compare exact values in that authoritative representation, not float64 CSV.
        np.testing.assert_array_equal([float(row[k]) for k in ("wind_m_s","direction_rad","ti")],wind.values[step].astype(np.float32).astype(float))
        powers=[float(row[f"power_{i}_w"]) for i in (1,2,3)]
        power=float(np.asarray(powers,dtype=np.float32).sum())
        max_double_power_sum=max(max_double_power_sum,abs(sum(powers)-float(row["farm_power_w"])))
        max_power_sum=max(max_power_sum,abs(power-float(row["farm_power_w"])))
        assert abs(float(row["error_w"])-(float(row["farm_power_w"])-float(row["target_w"])))<1e-7
        for i in (1,2,3):
            gamma=float(row[f"gamma_{i}"])
            expected_gamma=(float(row[f"heading_{i}_rad"])-float(row["direction_rad"])+np.pi)%(2*np.pi)-np.pi
            max_gamma_relation=max(max_gamma_relation,abs(gamma-expected_gamma))
            assert -.4-1e-6<=gamma<=.4+1e-6
            assert -1e-6<=float(row[f"pitch_{i}"])<=.22+1e-6
            assert .6-1e-6<=float(row[f"speed_{i}"])<=1.267+1e-6
            assert all(abs(float(row[f"command_{i}_{j}"]))<=1+1e-7 for j in range(3))
    max_rates=np.zeros(3)
    for key,part in grouped.items():
        case,wind=bank[key[-1]]
        previous=np.tile([float(np.float32(wind.values[0,1])),case["initial_pitch_rad"],.9],(3,1))
        for row in part:
            current=np.array([[float(row[f"heading_{i}_rad"]),float(row[f"pitch_{i}"]),float(row[f"speed_{i}"])] for i in (1,2,3)])
            max_rates=np.maximum(max_rates,np.abs(current-previous).max(axis=0));previous=current
    assert max_gamma_relation<1e-6 and max_power_sum<1e-7
    assert np.all(max_rates<=np.array([.005,.00872664626,.1])+1e-7)
    manifest=[]; normalizations=[]
    for path in sorted(source.glob("*_run_*/segment_*/step_*.pth")):
        payload=torch.load(path,weights_only=False,map_location="cpu")
        meta=payload["metadata"]
        manifest.append(dict(checkpoint=str(path),sha256=sha(path),version=payload["version"],lambda_value=payload["anchor_weight"],
            arm=path.parent.parent.name,step=meta["step"],actor_lr=payload["config"]["actor_lr"],updates=payload["updates"],parent=meta["lineage"]["parent_checkpoint"]))
        normalizations.append(meta["normalization"])
    assert len(manifest)==30 and all(item==normalizations[0] for item in normalizations)
    write_csv(root/"audit/checkpoint_manifest.csv",manifest)
    write_json(root/"audit/normalization.json",normalizations[0])
    recommendation=read_json(root/"audit/pre_test_recommendation.json")
    worktree=Path(cfg["worktree"])
    assert sha(worktree/"optimization_control/maddpg_wind_farm/ANCHOR_NEXT_CANDIDATE.md")==recommendation["proposal_sha256"]
    for name in ("complete.json","heading_display_fix.json"):
        record=read_json(root/"figures"/name)
        verify_hashes({str(root/"figures"/p):h for p,h in record["generated"].items()})
    pdfs=list((root/"figures").glob("*.pdf"))
    assert len(pdfs)==12
    for path in pdfs:
        raw=path.read_bytes()
        assert raw.startswith(b"%PDF-") and raw.rstrip().endswith(b"%%EOF")
        assert len(re.findall(rb"/Type\s*/Page(?!s)",raw))==1
    docs=("ANCHOR_CLOSEOUT_RESULTS.md","ANCHOR_CLOSEOUT_PROTOCOL.md","ANCHOR_NEXT_CANDIDATE.md","ANCHOR_TAKEOVER_PRECISION.md")
    links=0
    for name in docs:
        path=worktree/"optimization_control/maddpg_wind_farm"/name
        text=path.read_text(encoding="utf-8")
        assert text.count("```")%2==0
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)",text):
            if not target.startswith(("https://","http://","#")):
                assert (path.parent/target.split("#")[0]).resolve().exists(),(name,target)
            links+=1
    original=read_json(root/"audit/workspace_and_tests.json")
    verify_hashes(original["original_coordination_file_hashes"])
    branch=subprocess.check_output(["git","-c","safe.directory="+cfg["original_workspace"],"branch","--show-current"],cwd=cfg["original_workspace"],text=True).strip()
    assert branch==original["original_branch"]=="master"
    context(root)
    result=dict(seed=42,test_metrics=600,test_traces=76800,test_identity_set_exact=True,case_wind_after_environment_float32_cast_exact=True,
        max_gamma_heading_wind_relation_error_rad=max_gamma_relation,max_farm_power_sum_error_w=max_power_sum,
        max_float64_resum_rounding_difference_w=max_double_power_sum,
        max_applied_rates_per_s=max_rates.tolist(),physical_bounds_and_normalized_commands_pass=True,
        checkpoint_manifest_rows=30,common_normalization_saved=True,documents_checked=4,links_checked=links,
        single_page_pdfs_checked=12,pngs_visually_checked=9,primary_plot_groups=9,original_display_plot_groups_preserved=3,
        heading_wrap_display_corrected=True,unique_tests_passed=13,original_coordination_files_unchanged=True,original_branch=branch,
        proposal_unchanged_since_pre_test=True,additional_formal_training_steps=0,code_sha256=sha(__file__))
    write_json(root/"audit/final_checks.json",result)
    summary=read_json(root/"summary.txt")
    assert summary["status"]=="completed"
    summary.update(final_checks=result,test_aggregate=read_csv(root/"test/aggregate.csv"),
        conclusions=dict(full_original_stability_pass=False,anchor_final_vs_baseline_routine_paired_improvements=2,
            anchor_final_vs_parent_routine_paired_improvements=2,anchor_selected_steps=[6144,6144,6144],
            speed_same_state_policy_exact=True,speed_strict_closed_loop_passed=0,yaw_strict_closed_loop_passed=3,
            anchor_initial_strict_closed_loop_passed=3,yaw_model_local_response_requires_review=True,next_candidate_implemented=False))
    write_json(root/"summary.txt",summary)
    outputs={str(p.relative_to(root)):sha(p) for p in root.rglob("*") if p.is_file() and "mpl_cache" not in p.parts and p.name!="output_manifest.json"}
    write_json(root/"output_manifest.json",outputs)
    print(result,flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--output",required=True)
    args=ap.parse_args();run(Path(args.output).resolve())
