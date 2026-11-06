"""Small linear-plant checks for immutable forks and action/value semantics."""
from copy import deepcopy
import unittest

import numpy as np
import torch

from optimization_control.maddpg_wind_farm.workflow import load_config, DEFAULT_CONFIG, build_env, make_agent
from optimization_control.maddpg_wind_farm.frozen_speed_algorithm import FrozenSpeedMADDPG
from optimization_control.maddpg_wind_farm import speed_value_diagnostic as diagnostic
from optimization_control.maddpg_wind_farm.speed_value_analysis import direction


class SpeedValueTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.cfg=load_config(DEFAULT_CONFIG)
        self.cfg['environment'].update(horizon=128,control_mask=[0,1,0],yaw_frame='nacelle_heading',
            action_low=[-.25,0.,.6],action_high=[.25,.22,1.267],
            reference_schedule=dict(yaw_offset_rad=0.,speed_per_wind_rad_m=1.267/11.4),
            speed_reference_mode='observation_float32_v1')
        self.cfg['algorithm'].update(capacity=64,batch_size=16)
        env=build_env(self.cfg)
        parent=make_agent(self.cfg,env)
        self.agent=FrozenSpeedMADDPG.from_parent(parent,42)
        self.cfg['environment']['control_mask']=[0,1,1]
        self.env=build_env(self.cfg)
        wind=np.column_stack((np.linspace(8.7,9.3,129),np.mod(.02*np.sin(np.arange(129)/20),2*np.pi),np.full(129,.08)))
        obs,_=self.env.reset(seed=42,options=dict(wind_trajectory=wind,target_w=3000000.))
        for _ in range(64):obs,*_=self.env.step(self.agent.act(obs))
        self.obs=obs

    def test_clone_and_two_full_forks_preserve_source_state_and_rng(self):
        old=diagnostic.state_sha(self.env)
        a,first=diagnostic.branch(self.env,self.agent)
        b,second=diagnostic.branch(self.env,self.agent)
        self.assertEqual(a,b)
        for key in first:np.testing.assert_array_equal(first[key],second[key])
        self.assertEqual(old,diagnostic.state_sha(self.env))
        self.assertIs(diagnostic.clone_env(self.env).plant,self.env.plant)

    def test_radius_contract_and_head_weight_immutability(self):
        with torch.no_grad():
            for head in self.agent.speed_heads:head[-2].bias.fill_(np.arctanh(.5))
        old=diagnostic.fingerprint(self.agent)
        np.testing.assert_array_equal(diagnostic.radius_action(self.agent,self.obs,.1),self.agent.act(self.obs))
        np.testing.assert_array_equal(diagnostic.radius_action(self.agent,self.obs,0.),self.agent.act(self.obs,zero_speed=True))
        baseline=self.agent.act(self.obs,zero_speed=True)
        for radius in diagnostic.RADII:
            action=diagnostic.radius_action(self.agent,self.obs,radius)
            np.testing.assert_array_equal(action[:,:2],baseline[:,:2])
            self.assertLessEqual(float(np.abs(action[:,2]-baseline[:,2]).max())*diagnostic.WIDTH/2,radius+1e-7)
        self.assertEqual(old,diagnostic.fingerprint(self.agent))

    def test_pulse_changes_one_first_command_then_restores_feedback_policy(self):
        action=diagnostic.pulse_action(self.agent,self.obs,1,.04)
        original=diagnostic.radius_action(self.agent,self.obs)
        np.testing.assert_array_equal(action[[0,2]],original[[0,2]])
        result,data=diagnostic.branch(self.env,self.agent,first_action=action)
        clone=diagnostic.clone_env(self.env);obs,_,_,_,_=clone.step(action)
        np.testing.assert_array_equal(data['executed'][1],diagnostic.radius_action(self.agent,obs))
        self.assertAlmostEqual(result['return_8'],float((.99**np.arange(8))@data['reward'][:8]))
        self.assertAlmostEqual(result['return_32'],result['tracking_32']+result['penalty_32'],places=6)

    def test_q_gradient_refers_to_executed_total_speed_and_accumulates_no_parameter_grad(self):
        self.agent.critics=torch.nn.ModuleList([torch.nn.Linear(54,1) for _ in range(3)])
        with torch.no_grad():
            for i,critic in enumerate(self.agent.critics):
                critic.weight.zero_();critic.bias.zero_();critic.weight[0,45+i*3+2]=i+1
        action=diagnostic.radius_action(self.agent,self.obs)
        gradients=diagnostic.q_gradients(self.agent,self.obs,action)
        np.testing.assert_allclose(gradients,np.arange(1,4)*2/diagnostic.WIDTH)
        self.assertTrue(all(p.grad is None for p in self.agent.critics.parameters()))

    def test_offline_parent_pitch_is_explicit_replay_and_zero_head_matches(self):
        reference=diagnostic.clone_env(self.env);script=[]
        for _ in range(32):
            action=self.agent.act(reference._observe());script.append(action[:,1].copy());reference.step(action)
        normal,a=diagnostic.branch(self.env,self.agent)
        replay,b=diagnostic.branch(self.env,self.agent,pitch_script=np.asarray(script))
        self.assertEqual(normal,replay)
        for key in a:np.testing.assert_array_equal(a[key],b[key])

    def test_probe_clips_to_existing_envelope_and_numeric_ties_are_not_directions(self):
        with torch.no_grad():
            for head in self.agent.speed_heads:head[-2].bias.fill_(20.)
        action=diagnostic.pulse_action(self.agent,self.obs,0,.04)
        parent=self.agent.act(self.obs,zero_speed=True)
        self.assertLessEqual(float(action[0,2]-parent[0,2])*diagnostic.WIDTH/2,.1+1e-7)
        self.assertEqual(direction(1e-7,1e-4),0)
        self.assertEqual(direction(-.01,1e-4),-1)
        self.assertEqual(direction(.01,1e-4),1)


if __name__=='__main__':unittest.main()
