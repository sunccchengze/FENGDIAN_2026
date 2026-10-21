"""Model selection boundaries, initialization, exploration and frozen metrics."""

from copy import deepcopy
import unittest
import numpy as np
import torch

from optimization_control.maddpg_wind_farm.algorithm import AlgorithmConfig, MADDPG
from optimization_control.maddpg_wind_farm.benchmark import load_cases, selection_score, update_best, seed_for, case_trace, evaluate_cases
from optimization_control.maddpg_wind_farm.stable_workflow import Exploration, load_protocol, DEFAULT


class StableTrainingTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)

    def test_nominal_initialization_and_independent_critics(self):
        plain=MADDPG(AlgorithmConfig(hidden=16))
        nominal=MADDPG(AlgorithmConfig(hidden=16,actor_initial_action=(0,-.8,.3),actor_final_scale=0))
        for a,b in zip(plain.critics.parameters(),nominal.critics.parameters()):
            torch.testing.assert_close(a,b,rtol=0,atol=0)
        for obs in (np.zeros((3,15)),np.ones((3,15))*10):
            np.testing.assert_allclose(nominal.act(obs),np.tile([0,-.8,.3],(3,1)),atol=1e-6)
        with self.assertRaises(ValueError): AlgorithmConfig(actor_initial_action=(0,-1,0))

    def test_test_split_cannot_select_or_load_before_release(self):
        with self.assertRaisesRegex(ValueError,"locked"): load_cases("unused","test")
        rows=[{"split":"test","family":"fixed","rmse_w":1}]
        with self.assertRaises(ValueError): selection_score(rows,["fixed"])
        with self.assertRaises(ValueError): update_best(None,rows,["fixed"],0,"file")

    def test_selection_is_family_balanced_strict_and_excludes_stress(self):
        rows=[{"split":"validation","family":"fixed","rmse_w":10},
              {"split":"validation","family":"fixed","rmse_w":30},
              {"split":"validation","family":"gust","rmse_w":40},
              {"split":"validation","family":"shortfall","rmse_w":1e9}]
        self.assertEqual(selection_score(rows,["fixed","gust"]),30)
        best=update_best(None,rows,["fixed","gust"],0,"initial")
        self.assertEqual(update_best(best,rows,["fixed","gust"],100,"later"),best)
        rows[2]["rmse_w"]=20
        self.assertEqual(update_best(best,rows,["fixed","gust"],200,"improved")["step"],200)
        rows[2]["rmse_w"]=float("nan")
        with self.assertRaises(ValueError): selection_score(rows,["fixed","gust"])

    def test_exploration_save_restore_decay_and_correlation(self):
        args=([.05,.15,.08],[10,3,5],1,"correlated",.2)
        a=Exploration(42,*args); a.reset()
        samples=np.array([a.sample(0)[0] for _ in range(5000)])
        self.assertGreater(np.corrcoef(samples[:-1,0],samples[1:,0])[0,1],.85)
        np.testing.assert_allclose(samples.std(axis=0),args[0],rtol=.15)
        saved=a.state_dict(); b=Exploration(99,*args); b.load_state_dict(saved)
        np.testing.assert_array_equal(a.sample(.5),b.sample(.5))
        a.load_state_dict(saved); b.load_state_dict(saved)
        np.testing.assert_allclose(a.sample(1),b.sample(0)*.2,atol=1e-12)

    def test_run_seeds_independent_reproducible(self):
        seeds=[seed_for(42,s,r) for s in (101,201,301) for r in range(4)]
        self.assertEqual(len(set(seeds)),12)
        self.assertEqual(seed_for(42,101,2),seed_for(42,101,2))

    def test_protocol_and_metric_reset_reproducible(self):
        p,cfg=load_protocol(DEFAULT)
        self.assertEqual(len(p["candidates"]),5)
        cfg["environment"]["horizon"]=32
        trace=case_trace(cfg,"direction",split="validation",episode=100)
        case={"id":"check","split":"validation","family":"direction","target_w":3e6}
        a=evaluate_cases(cfg,[(case,trace)],baseline="pi")
        b=evaluate_cases(cfg,[(case,trace)],baseline="pi")
        self.assertEqual(a,b)
        self.assertGreater(a[0]["yaw_travel_rad"],0)
        self.assertTrue(np.isfinite(a[0]["rmse_w"]))


if __name__=="__main__": unittest.main()
