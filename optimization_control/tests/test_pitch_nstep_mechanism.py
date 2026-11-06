"""Small tests for the new audit bookkeeping, not another algorithm trial."""
import unittest
import numpy as np
from optimization_control.maddpg_wind_farm.pitch_nstep_mechanism import grid,comparison,branch_key
from optimization_control.maddpg_wind_farm.pitch_nstep_handoff import validate_manifest


class MechanismTests(unittest.TestCase):
    def test_same_unit_critic_for_candidate_and_zero(self):
        base=dict(direction='none',q_mean=100.,q_0=1.,q_1=10.,q_2=289.,discounted_return=2.,tracking_return=3.,action_return=-1.)
        row=dict(base,direction='unit2',q_1=11.,discounted_return=1.,tracking_return=4.,action_return=-3.)
        result=comparison(row,base,base)
        self.assertEqual(result['delta_q'],1.)
        self.assertEqual(result['delta_g'],-1.)
        self.assertEqual(result['opposite'],1)
        self.assertEqual(result['delta_tracking'],1.)
        self.assertEqual(result['delta_action'],-2.)

    def test_symmetric_grid_and_exact_cache_boundaries(self):
        variants=grid();self.assertEqual(len(variants),9)
        for name in ('common','unit1','unit2','unit3'):
            a,b=[v for v in variants if v['direction']==name]
            np.testing.assert_array_equal(a['vector'],-np.array(b['vector']))
        a=np.zeros((3,3),np.float32);key=branch_key('parent',32,a,'continue')
        self.assertEqual(key,branch_key('parent',32,a.copy(),'continue'))
        self.assertNotEqual(key,branch_key('selected',32,a,'continue'))
        self.assertNotEqual(key,branch_key('parent',96,a,'continue'))
        self.assertNotEqual(key,branch_key('parent',32,a,'different_continue'))

    def test_handoff_rejects_permission_and_stream_selection_changes(self):
        m=dict(seed=42,status='experimental_candidates_not_default',control_mask=[0,1,0],observation_shape=[3,15],n=8,
               tail_rule='actual_m_bootstrap_unless_true_terminal_v1',candidates=[dict(run=i,checkpoint='missing',sha256='bad') for i in range(3)],protected_hashes={})
        for altered in (dict(m,control_mask=[0,1,1]),dict(m,n=1),dict(m,candidates=m['candidates'][:2])):
            with self.assertRaises(ValueError):validate_manifest(altered)


if __name__=='__main__':unittest.main()
