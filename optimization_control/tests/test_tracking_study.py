"""Sampling isolation, feasible bank and optional evaluation accounting."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import unittest
import numpy as np
from optimization_control.maddpg_wind_farm.tracking_study import read_protocol,PROTOCOL,freeze_tracking_bank,family_mean
from optimization_control.maddpg_wind_farm.stable_workflow import training_options
from optimization_control.maddpg_wind_farm.benchmark import load_cases,evaluate_cases
from optimization_control.maddpg_wind_farm.reachability import witness
from optimization_control.maddpg_wind_farm.workflow import build_env


class TrackingStudyTests(unittest.TestCase):
    def test_sampling_only_changes_declared_slots_and_covers_grid(self):
        spec,p,cfg=read_protocol(PROTOCOL)
        trial=deepcopy(p); trial["tracking_curriculum"]=spec["tracking_curriculum"]
        observed={2:set(),3:set()}
        for episode in range(40):
            a=training_options(cfg,p,"mixed",episode,1)
            b=training_options(cfg,trial,"mixed",episode,1)
            if episode%4 in (0,1):
                np.testing.assert_array_equal(a["wind_trajectory"],b["wind_trajectory"])
                self.assertEqual(a["target_w"],b["target_w"])
            else:
                self.assertEqual(np.ptp(b["wind_trajectory"][:,0]),0)
                observed[episode%4].add((b["wind_trajectory"][0,0],b["target_w"]))
        self.assertEqual(len(observed[2]),9); self.assertEqual(len(observed[3]),9)
        a=training_options(cfg,p,"fixed",0,1); b=training_options(cfg,trial,"fixed",0,1)
        np.testing.assert_array_equal(a["wind_trajectory"],b["wind_trajectory"])

    def test_bank_feasibility_test_lock_and_decomposition(self):
        spec,_,cfg=read_protocol(PROTOCOL); env=build_env(cfg)
        # Preserve evidence under the project's existing temporary-output convention.
        bank=Path("tmp")/f"tracking_bank_test_{uuid4().hex}"
        freeze_tracking_bank(cfg,spec,bank)
        with self.assertRaises(ValueError): load_cases(bank,"test")
        for split in ("validation","test"):
            cases=load_cases(bank,split,allow_test=True)
            self.assertEqual(len(cases),27)
            for c,trace in cases:
                if c["family"] in ("fixed","low_power","low_shortfall"):
                    w=witness(env,trace.values[0,0],c["target_w"])
                    expected="unreachable_above_certified_upper" if c["family"]=="low_shortfall" else "steady_feasible_witness"
                    self.assertEqual(w["status"],expected)
        cases=load_cases(bank,"validation",families=["low_shortfall"])
        plain=evaluate_cases(cfg,cases,baseline="pi")
        detailed=evaluate_cases(cfg,cases,baseline="pi",decomposition=True)
        for a,b in zip(plain,detailed):
            self.assertEqual(a["rmse_w"],b["rmse_w"])
            self.assertAlmostEqual(b["mean_shortfall_w"],b["certified_shortfall_floor_w"]+b["residual_shortfall_w"])

    def test_family_balance_does_not_weight_by_case_count(self):
        rows=[dict(family="a",rmse_w=1.)]*9+[dict(family="b",rmse_w=9.)]
        self.assertEqual(family_mean(rows,["a","b"]),5.)
        with self.assertRaises(ValueError): family_mean(rows,["missing"])


if __name__=="__main__": unittest.main()
