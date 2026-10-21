"""Mock-specific upper bound, constructive witnesses and error accounting."""
import unittest
import numpy as np
from optimization_control.maddpg_wind_farm.reachability import upper_bound,witness,predict,error_components,fixed_rollout
from optimization_control.maddpg_wind_farm.stable_workflow import load_protocol,DEFAULT
from optimization_control.maddpg_wind_farm.workflow import build_env


class ReachabilityTests(unittest.TestCase):
    def setUp(self):
        _,self.cfg=load_protocol(DEFAULT); self.env=build_env(self.cfg)

    def test_upper_encloses_random_controls_and_is_attained(self):
        rng=np.random.default_rng(42)
        for u in (3.,5.5,8.,11.4,13.):
            bound=upper_bound(self.env,u)
            for _ in range(40):
                a=rng.uniform(self.env.low,self.env.high,(3,3))
                self.assertLessEqual(predict(self.env,u,a),bound)
            if u<=11.4:
                w=witness(self.env,u,5e6)
                self.assertLess(bound-w["known_available_w"],15)

    def test_multigoal_witness_and_impossibility(self):
        for u in (5.5,7.5,8.,9.):
            for t in (.8e6,1.2e6,2.4e6,3e6,3.6e6,5e6):
                w=witness(self.env,u,t)
                self.assertNotEqual(w["status"],"unresolved")
                if w["status"]=="steady_feasible_witness":
                    self.assertLessEqual(abs(predict(self.env,u,np.array(w["physical"]))-t),10)
                else: self.assertGreater(t,w["upper_bound_w"])

    def test_foreign_model_and_changed_normalization_rejected(self):
        self.env.plant.predictor=lambda x:x
        with self.assertRaises(ValueError): upper_bound(self.env,8.)
        env=build_env(self.cfg); env.plant.input_scale[0]=2
        with self.assertRaises(ValueError): upper_bound(env,8.)
        env=build_env(self.cfg); env.plant.predictor.rated=env.plant.predictor.rated*2
        with self.assertRaises(ValueError): upper_bound(env,8.)

    def test_error_partition_and_rate_limited_witness(self):
        result=error_components([-4.,-3.,1.,0.],[2.,2.,6.,5.],5.)
        self.assertAlmostEqual(result["mean_shortfall_w"],result["certified_shortfall_floor_w"]+result["residual_shortfall_w"])
        with self.assertRaises(AssertionError): error_components([1.,1.],[1.,1.],5.)
        w=witness(self.env,8.,3e6)
        r=fixed_rollout(self.cfg,8.,3e6,physical=np.array(w["physical"]))
        self.assertLess(r["second_half_rmse_w"],10)
        self.assertGreater(r["first_half_rmse_w"],r["second_half_rmse_w"])


if __name__=="__main__": unittest.main()
