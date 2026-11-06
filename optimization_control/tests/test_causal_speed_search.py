"""Cheap causal/rollback checks; toy model advances are recorded as well."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import numpy as np
from optimization_control.maddpg_wind_farm.workflow import load_config,DEFAULT_CONFIG,build_env
from optimization_control.maddpg_wind_farm.causal_speed_search import Budget,Meter,capture,fork,plan,command,candidates,state_sha,read_protocol
from optimization_control.utils.reference_schedule import speed_numpy

MOCK_ROWS=[]


class FeedbackParent:
    def act(self,obs):
        a=np.zeros((3,3),np.float32);a[:,1]=np.clip(-.6+.2*obs[:,0],-1,1)
        a[:,2]=speed_numpy(obs,(25.,1.267/11.4,.6,1.267));return a


class CausalSearchTests(unittest.TestCase):
    def setUp(self):
        cfg=load_config(DEFAULT_CONFIG)
        cfg['environment'].update(horizon=128,control_mask=[0,1,1],yaw_frame='nacelle_heading',
            action_low=[-.25,0.,.6],action_high=[.25,.22,1.267],
            reference_schedule=dict(yaw_offset_rad=0.,speed_per_wind_rad_m=1.267/11.4),speed_reference_mode='observation_float32_v1')
        self.env=build_env(cfg);self.parent=FeedbackParent();self.p=read_protocol()
        self.budget=Budget();self.budget.start('toy_case',1000)
        self.meter=Meter(self.env.plant.predictor,self.budget);self.env.plant.predictor=self.meter
        self.env.reset(seed=42,options=dict(wind_trajectory=np.tile([9.,0.,.08],(129,1)),target_w=3.2e6))
        for _ in range(4):self.env.step(self.parent.act(self.env._observe()))
    def tearDown(self):MOCK_ROWS.append(self.budget.active['actual'])
    def test_future_invariance_and_full_current_state_rollback(self):
        before=state_sha(self.env);a,x=plan(self.env,self.parent,self.p,self.meter)
        self.env.trajectory[self.env.t+1:]=[10.,.03,.1]
        b,y=plan(self.env,self.parent,self.p,self.meter)
        np.testing.assert_array_equal(a,b);self.assertEqual(x['costs_MW2'],y['costs_MW2']);self.assertEqual(before,state_sha(self.env))
        child=fork(capture(self.env),self.env.plant,type(self.env));child.rng.normal();child.actuator._state[next(iter(child.actuator._state))][:]+=1
        self.assertEqual(before,state_sha(self.env))
    def test_zero_branch_and_current_counterfactual_pitch(self):
        a=fork(capture(self.env),self.env.plant,type(self.env));b=fork(capture(self.env),self.env.plant,type(self.env))
        for _ in range(12):
            action,ref=command(self.parent,a._observe(),np.zeros(3));np.testing.assert_array_equal(action,ref)
            oa,*_=a.step(action);ob,*_=b.step(self.parent.act(b._observe()));np.testing.assert_array_equal(oa,ob)
        c=fork(capture(self.env),self.env.plant,type(self.env));initial=self.parent.act(c._observe())[:,1]
        for _ in range(4):c.step(command(self.parent,c._observe(),np.full(3,.1))[0])
        self.assertFalse(np.array_equal(initial,self.parent.act(c._observe())[:,1]))
    def test_action_envelope_and_zero_first_ties(self):
        obs=self.env._observe();base=self.parent.act(obs)
        for offset in candidates():
            action,_=command(self.parent,obs,offset);np.testing.assert_array_equal(action[:,:2],base[:,:2])
            self.assertLessEqual(np.abs(action[:,2]-base[:,2]).max()*.667/2,.1000001)
        with patch('optimization_control.maddpg_wind_farm.causal_speed_search.candidates',return_value=np.zeros((9,3))):
            _,details=plan(self.env,self.parent,self.p,self.meter)
            self.assertEqual(details['chosen'],0)
    def test_row_budget_counts_batch_rows_and_rejects_before_forward(self):
        b=Budget(limit=5);b.start('batch',5);calls=[]
        meter=Meter(lambda x:calls.append(len(x)) or x,b)
        meter(np.zeros((4,12)));self.assertEqual(b.active['actual'],4)
        with self.assertRaises(RuntimeError):meter(np.zeros((2,12)))
        self.assertEqual(calls,[4]);self.assertEqual(b.active['actual'],4)
        MOCK_ROWS.append(4)
        b.finish()
        with self.assertRaises(ValueError):b.start('batch',1)


if __name__=='__main__':unittest.main()
