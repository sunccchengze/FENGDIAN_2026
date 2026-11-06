"""A single metered mock planning contract, without legacy test rediscovery."""
import unittest
import numpy as np
import optimization_control.tests.test_causal_speed_search as fixtures
from optimization_control.maddpg_wind_farm import causal_speed_search as old,midgrid_speed_search as original
from optimization_control.maddpg_wind_farm.history_speed_search import plan,Persistence
from optimization_control.maddpg_wind_farm.history_wind_forecast import RidgeForecast

MOCK_ROWS=[]
class HistoryPlannerTests(unittest.TestCase):
    def setUp(self):fixtures.CausalSearchTests.setUp(self)
    def tearDown(self):MOCK_ROWS.append(self.budget.active['actual'])
    def test_causal_rollout_and_persistence_adapter_exact(self):
        history=np.tile(self.env.wind,(5,1));saved=history.copy();before=old.state_sha(self.env)
        target=np.zeros(36);target[::3]=-.1
        model=RidgeForecast(np.zeros(96),np.ones(96),target,np.zeros((96,36)))
        _,a=plan(self.env,self.parent,self.meter,model,history)
        self.env.trajectory[5:]=[10.,.03,.1]
        _,b=plan(self.env,self.parent,self.meter,model,history)
        np.testing.assert_array_equal(a['costs_MW2'],b['costs_MW2']);np.testing.assert_array_equal(history,saved)
        _,c=plan(self.env,self.parent,self.meter,Persistence(),history)
        _,d=original.plan(self.env,self.parent,self.p,self.meter)
        np.testing.assert_array_equal(c['costs_MW2'],d['costs_MW2']);self.assertEqual(before,old.state_sha(self.env))

if __name__=='__main__':unittest.main()
