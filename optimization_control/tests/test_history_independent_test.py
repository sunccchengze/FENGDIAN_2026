"""Only timing adaptation equivalence; source causal contracts are reused."""
import unittest
import numpy as np
import optimization_control.tests.test_causal_speed_search as fixtures
from optimization_control.maddpg_wind_farm import causal_speed_search as old
from optimization_control.maddpg_wind_farm.history_speed_search import plan,Persistence
from optimization_control.maddpg_wind_farm.history_wind_forecast import RidgeForecast
from optimization_control.maddpg_wind_farm.history_independent_test import measured_plan

MOCK_ROWS=[]
class IndependentTimingTests(unittest.TestCase):
    def setUp(self):fixtures.CausalSearchTests.setUp(self)
    def tearDown(self):MOCK_ROWS.append(self.budget.active['actual'])
    def test_timing_wrapper_preserves_both_numeric_policies(self):
        history=np.tile(self.env.wind,(5,1));before=old.state_sha(self.env)
        target=np.zeros(36);target[::3]=-.1;model=RidgeForecast(np.zeros(96),np.ones(96),target,np.zeros((96,36)))
        for predictor in (model,Persistence()):
            a,x=plan(self.env,self.parent,self.meter,predictor,history);b,y=measured_plan(self.env,self.parent,self.meter,predictor,history)
            np.testing.assert_array_equal(a,b)
            for key in ('costs_MW2','predicted_error_w','predicted_wind'):np.testing.assert_array_equal(x[key],y[key])
            self.assertEqual(x['chosen'],y['chosen']);self.assertGreaterEqual(y['timing']['cpu_seconds'],0);self.assertGreaterEqual(y['timing']['wall_seconds'],0)
        self.assertEqual(before,old.state_sha(self.env))

if __name__=='__main__':unittest.main()
