"""Reward-offset conditions, return ordering, and replay audit protections."""
import unittest
import numpy as np
from optimization_control.maddpg_wind_farm.value_baseline_diagnostic import reward_offset,returns_by_episode,replay_exogenous
from optimization_control.maddpg_wind_farm.stable_workflow import load_protocol,DEFAULT,training_options
from optimization_control.maddpg_wind_farm.workflow import build_env
from optimization_control.maddpg_wind_farm.algorithm import MADDPG,AlgorithmConfig


class ValueBaselineDiagnosticTests(unittest.TestCase):
    def test_reward_offset_uses_only_exogenous_inputs_and_rejects_foreign_model(self):
        _,cfg=load_protocol(DEFAULT); cfg["environment"]["reward_scale"]=100
        env=build_env(cfg); env.reset()
        self.assertEqual(reward_offset(env,8.,3e6),0.)
        value=reward_offset(env,5.5,5e6)
        self.assertGreater(value,6); self.assertLess(value,6.3)
        env.power[:]=0
        self.assertEqual(reward_offset(env,5.5,5e6),value)
        with self.assertRaises(ValueError): reward_offset(env,5.5,0)
        env.plant.predictor=lambda x:x
        with self.assertRaises(ValueError): reward_offset(env,5.5,5e6)

    def test_discounted_baseline_and_td_coordinate_identity(self):
        offset=np.array([1.,2.,3.,4.]); c=returns_by_episode(offset,2,.5)
        np.testing.assert_array_equal(c,[2.,2.,5.,4.])
        next_c=np.array([2.,0.,4.,0.]); done=np.array([0,1,0,1])
        q=np.array([-.2,-3,-9,-10]); nq=np.array([-2,-4,-6,-8]); r=np.array([-8.,-5,-7,-10])
        raw=r+.5*(1-done)*nq-q
        transformed=r+offset+.5*(1-done)*(nq+next_c)-(q+c)
        np.testing.assert_allclose(raw,transformed,atol=1e-12)
        with self.assertRaises(ValueError): returns_by_episode([1,2,3],2,.99)

    def test_same_trace_policy_return_difference_is_unchanged(self):
        _,cfg=load_protocol(DEFAULT); cfg["environment"]["reward_scale"]=100
        e=cfg["environment"]; h=e["horizon"]
        trace=np.column_stack((np.linspace(5.5,8.5,h+1),np.full(h+1,e["wind_direction_rad"]),np.full(h+1,.08)))
        returns=[]; corrected=[]; shifts=[]
        for action in (np.tile([0.,-.8,.2],(3,1)),np.tile([.3,.1,-.4],(3,1))):
            env=build_env(cfg); env.reset(options={"wind_trajectory":trace,"target_w":5e6})
            rewards=[]; offsets=[]
            for _ in range(h):
                _,r,_,_,info=env.step(action)
                rewards.append(float(r[0])); offsets.append(float(reward_offset(env,info["wind"][0],env.target)))
            returns.append(returns_by_episode(rewards,h,.99)[0])
            corrected.append(returns_by_episode(np.array(rewards)+offsets,h,.99)[0])
            shifts.append(returns_by_episode(offsets,h,.99)[0])
        self.assertEqual(shifts[0],shifts[1])
        self.assertAlmostEqual(returns[0]-returns[1],corrected[0]-corrected[1],places=9)

    def test_reconstructed_replay_and_boundary_tampering(self):
        p,cfg=load_protocol(DEFAULT); cfg["environment"]["horizon"]=32
        env=build_env(cfg); agent=MADDPG(AlgorithmConfig(hidden=8,capacity=128,batch_size=8))
        for ep in range(2):
            obs,_=env.reset(options=training_options(cfg,p,"mixed",ep,1))
            for _ in range(env.horizon):
                nxt,r,done,_,info=env.step(np.zeros((3,3)))
                agent.replay.add(obs,info["executed_action"],r,nxt,done); obs=nxt
        meta=dict(config=cfg,steps=64,episodes=2,identity=dict(protocol=p,phase="mixed",run_id=1))
        _,_,wind,target=replay_exogenous(agent,meta)
        self.assertEqual(len(wind),64); self.assertEqual(len(target),64)
        agent.replay.data["terminated"][31,0]=0
        with self.assertRaises(ValueError): replay_exogenous(agent,meta)


if __name__=="__main__": unittest.main()
