"""Closeout identity, trace-completeness and intervention contracts."""
import unittest
import numpy as np

from optimization_control.maddpg_wind_farm.anchor_closeout import checked_output, validate_binding, recompute
from optimization_control.maddpg_wind_farm.anchor_closeout_diagnostic import intervene, OffsetPolicy


class CloseoutTests(unittest.TestCase):
    def test_output_must_stay_in_isolated_worktree(self):
        checked_output('D:/isolated/experiments/new','D:/isolated','D:/original')
        for output in ('D:/original/experiments/new','D:/isolated','D:/outside/new'):
            with self.assertRaises(ValueError): checked_output(output,'D:/isolated','D:/original')

    def test_all_three_freeze_bindings_required(self):
        selection=dict(root_config_sha256='cfg',bank_sha256='bank',selection_sha256_actual='sel')
        validate_binding(selection,'cfg','bank','sel')
        for arguments in (('other','bank','sel'),('cfg','other','sel'),('cfg','bank','other')):
            with self.assertRaises(ValueError):validate_binding(selection,*arguments)

    def trace(self):
        return [dict(case_id='case',step=i,farm_power_w=11.,target_w=10.) for i in range(1,129)]

    def test_recomputation_accepts_complete_trace(self):
        result=recompute([dict(case_id='case',rmse_w=1.)],self.trace(),('case_id',))
        self.assertEqual(result['metric_rows'],1); self.assertEqual(result['trace_rows'],128)

    def test_recomputation_rejects_missing_duplicate_disordered_and_nan(self):
        metric=[dict(case_id='case',rmse_w=1.)]
        for traces in (self.trace()[:-1],self.trace()[::-1],self.trace()+self.trace()):
            with self.assertRaises(ValueError):recompute(metric,traces,('case_id',))
        with self.assertRaises(ValueError):recompute(metric+metric,self.trace(),('case_id',))
        with self.assertRaises(ValueError):recompute([dict(case_id='case',rmse_w=float('nan'))],self.trace(),('case_id',))

    def test_parent_channel_swap_preserves_other_channels_and_inputs(self):
        final=np.ones((3,3),np.float32); parent=np.zeros((3,3),np.float32)
        changed=intervene(final,parent,'parent_pitch')
        np.testing.assert_array_equal(changed[:,1],0.)
        np.testing.assert_array_equal(changed[:,[0,2]],1.)
        np.testing.assert_array_equal(final,1.)
        with self.assertRaises(ValueError):intervene(final,parent,'unknown')

    def test_offset_uses_physical_units_then_global_bounds(self):
        class Parent:
            def act(self,obs):return np.zeros((3,3),np.float32)
        cfg=dict(environment=dict(action_low=[-.25,0.,.6],action_high=[.25,.22,1.267]))
        policy=OffsetPolicy(Parent(),cfg,2,.1)
        result=policy.act(None)
        np.testing.assert_allclose(result[:,2],2*.1/.667,atol=1e-7)
        np.testing.assert_array_equal(result[:,:2],0.)
        np.testing.assert_array_equal(OffsetPolicy(Parent(),cfg,0,10.).act(None)[:,0],1.)


if __name__=='__main__':unittest.main()
