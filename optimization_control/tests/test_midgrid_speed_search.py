"""Only the appended-grid, zero-history and causal-prefix contracts."""
import unittest
import numpy as np
import optimization_control.tests.test_causal_speed_search as fixtures
from optimization_control.maddpg_wind_farm import causal_speed_search as old
from optimization_control.maddpg_wind_farm import midgrid_speed_search as fine

MOCK_ROWS=[]


class MidgridTests(unittest.TestCase):
    def setUp(self):fixtures.CausalSearchTests.setUp(self)
    def tearDown(self):MOCK_ROWS.append(self.budget.active['actual'])
    def test_prefix_middle_and_zero_returns_current_reference_after_nonzero_history(self):
        grid=fine.grid();self.assertEqual(grid.shape,(17,3))
        np.testing.assert_array_equal(grid[:9],old.candidates(.1))
        np.testing.assert_array_equal(grid[9:],old.candidates(.05)[1:])
        self.assertEqual(len(np.unique(grid,axis=0)),17)
        for _ in range(4):self.env.step(old.command(self.parent,self.env._observe(),np.full(3,.1))[0])
        zero,reference=old.command(self.parent,self.env._observe(),np.zeros(3))
        np.testing.assert_array_equal(zero,reference)
        self.assertFalse(np.array_equal(zero[:,2],self.env.previous_action[:,2]))
    def test_exact_original_cost_prefix_and_future_invariance(self):
        before=old.state_sha(self.env)
        _,a=old.plan(self.env,self.parent,self.p,self.meter)
        _,b=fine.plan(self.env,self.parent,self.p,self.meter)
        np.testing.assert_array_equal(a['costs_MW2'],b['costs_MW2'][:9])
        self.assertLessEqual(b['best_all17_MW2'],min(a['costs_MW2'])+1e-12)
        self.env.trajectory[self.env.t+1:]=[10.,.03,.1]
        _,c=fine.plan(self.env,self.parent,self.p,self.meter)
        np.testing.assert_array_equal(b['costs_MW2'],c['costs_MW2'])
        self.assertEqual(before,old.state_sha(self.env))
    def test_ties_keep_zero_and_original_order(self):
        self.assertEqual(fine.choose([1.]*17),0)
        costs=[1.]*17;costs[5]=.2;costs[12]=.2
        self.assertEqual(fine.choose(costs),5)
        costs[12]=.2-1e-13;self.assertEqual(fine.choose(costs),5)
        costs[12]=.1;self.assertEqual(fine.choose(costs),12)


if __name__=='__main__':unittest.main()
