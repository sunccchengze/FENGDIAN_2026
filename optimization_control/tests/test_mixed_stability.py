"""Study invariants: fresh bank, paired factors, validation ranking, aggregation."""
import json
from pathlib import Path
import unittest
from uuid import uuid4
import numpy as np
from optimization_control.maddpg_wind_farm.benchmark import freeze_bank,load_cases
from optimization_control.maddpg_wind_farm.mixed_stability import read_protocol,PROTOCOL,validation_rank,aggregate_test,recover_job
from optimization_control.maddpg_wind_farm.stable_workflow import run_config,training_options
from optimization_control.maddpg_wind_farm.workflow import write_csv


class MixedStabilityTests(unittest.TestCase):
    def directory(self):
        # Retain generated evidence; project rules prohibit automatic deletion.
        p=Path("tmp")/f"mixed_study_test_{uuid4().hex}"; p.mkdir(parents=True)
        return p

    def test_single_factor_and_paired_training(self):
        s,p,b=read_protocol(PROTOCOL)
        configs=[run_config(b,c,[1,1,1]) for c in s["candidates"]]
        for cfg in configs[1:]:
            changed=[k for k in cfg["algorithm"] if cfg["algorithm"][k]!=configs[0]["algorithm"][k]]
            self.assertEqual(len(changed),1)
            for episode in range(5):
                a=training_options(configs[0],p,"mixed",episode,1)
                z=training_options(cfg,p,"mixed",episode,1)
                np.testing.assert_array_equal(a["wind_trajectory"],z["wind_trajectory"])
                self.assertEqual(a["target_w"],z["target_w"])

    def test_new_bank_targets_and_test_lock(self):
        s,p,b=read_protocol(PROTOCOL); b["environment"]["horizon"]=32
        folder=self.directory(); freeze_bank(b,p,folder/"new")
        old=dict(p,bank_episode_offset=20000); freeze_bank(b,old,folder/"old")
        new=load_cases(folder/"new","validation",families=["stationary"])
        previous=load_cases(folder/"old","validation",families=["stationary"])
        self.assertEqual([c[0]["target_w"] for c in new],[2.4e6,3e6,3.6e6]*2)
        self.assertFalse(np.array_equal(new[0][1].values,previous[0][1].values))
        with self.assertRaises(ValueError): load_cases(folder/"new","test")
        manifest=json.loads((folder/"new"/"manifest.json").read_text())
        victim=folder/"new"/manifest["cases"][0]["path"]
        with victim.open("ab") as f: f.write(b"\n")
        with self.assertRaises(ValueError): load_cases(folder/"new","validation")

    def test_rank_prefers_improved_stability_then_tail(self):
        folder=self.directory()
        def result(name,initial,best,final,tail):
            d=folder/name; d.mkdir()
            write_csv(d/"metrics.csv",[{"validation_rmse_w":v} for v in tail])
            return dict(initial_rmse_w=initial,best={"score_w":best},final_rmse_w=final,final=str(d/"unused.pth"))
        stable=result("stable",1000,300,360,[340,350,360])
        unstable=result("unstable",1000,100,180,[100,120,180])
        unlearned=result("unlearned",100,100,100,[100,100,100])
        self.assertLess(validation_rank([stable]),validation_rank([unstable]))
        self.assertLess(validation_rank([stable]),validation_rank([unlearned]))

    def test_test_aggregate_excludes_stress_and_uses_run_sd(self):
        rows=[dict(controller="a",run_id=i,family=f,rmse_w=v) for i,v in [(1,100),(2,200),(3,300)] for f in ["fixed","gust"]]
        rows.append(dict(controller="a",run_id=1,family="shortfall",rmse_w=1e9))
        result=aggregate_test(rows,["fixed","gust"])[0]
        self.assertEqual(result["mean_rmse_w"],200)
        self.assertEqual(result["std_w"],100)

    def test_recovery_uses_committed_summary_not_partial_checkpoint(self):
        root=self.directory(); folder=root/"baseline_run_1"; folder.mkdir()
        committed=folder/"step_00002048.pth"; committed.write_bytes(b"test-placeholder")
        (folder/"step_00004096.pth").write_bytes(b"incomplete-save")
        (folder/"summary.txt").write_text(json.dumps({"final":str(committed.resolve())}))
        finished,path,destination=recover_job(root,"baseline",1,16384)
        self.assertIsNone(finished)
        self.assertEqual(path,committed.resolve())
        self.assertEqual(destination,root/"baseline_run_1_resume_2048")
        destination.mkdir()
        with self.assertRaises(ValueError): recover_job(root,"baseline",1,16384)

    def test_recovery_retains_completed_runs_without_retraining(self):
        root=self.directory(); folder=root/"baseline_run_1"; folder.mkdir()
        result={"run_id":1,"final":"saved.pth"}
        (folder/"result.json").write_text(json.dumps(result))
        self.assertEqual(recover_job(root,"baseline",1,16384),(result,None,None))


if __name__=="__main__": unittest.main()
