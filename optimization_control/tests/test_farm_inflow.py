"""Physical yaw semantics, controller parity, stochastic entrance and masking."""

from copy import deepcopy
import io
import json
import unittest
from unittest.mock import patch
import numpy as np
import torch

from optimization_control.environments.farm_inflow import generate_inflow, InflowTrace
from optimization_control.environments.maddpg_farm_env import wrap_angle
from optimization_control.maddpg_wind_farm.workflow import load_config, DEFAULT_CONFIG, build_env, make_agent
from optimization_control.maddpg_wind_farm.controllers import PitchController
from optimization_control.maddpg_wind_farm.algorithm import MADDPG


class FarmInflowTests(unittest.TestCase):
    def setUp(self):
        self.config = {"speed": {"mean_min_m_s":8, "mean_max_m_s":8, "gust_duration_s":20,
                                 "speed_min_m_s":3, "speed_max_m_s":20}}

    def test_reproducibility_split_and_scenarios(self):
        for scenario in ("stationary", "ramp", "gust"):
            cfg = deepcopy(self.config); cfg["speed"]["scenario"] = scenario
            a = generate_inflow(cfg, dt_s=1, horizon=128, episode=3)
            b = generate_inflow(cfg, dt_s=1, horizon=128, episode=3)
            c = generate_inflow(cfg, dt_s=1, horizon=128, episode=3, split="test")
            np.testing.assert_array_equal(a.values, b.values)
            self.assertFalse(np.array_equal(a.values, c.values))
            np.testing.assert_allclose(a.values[:,0], a.components.sum(axis=1))
            self.assertEqual(len(np.unique(a.values[:,2])), 1)
            self.assertEqual(a.metadata["speed_metadata"]["scenario"], scenario)
            self.assertTrue(np.all(np.abs(np.diff(np.unwrap(a.values[:,1]))) < .01))
            if scenario == "gust": self.assertGreater(a.components[:,2].max(), 0)
            if scenario == "ramp": self.assertGreater(np.ptp(a.components[:,0]), 0)

    def test_inflow_rejects_invalid_direction_and_time(self):
        cfg = dict(self.config, direction={"period_s":0})
        with self.assertRaises(ValueError): generate_inflow(cfg,dt_s=1,horizon=128)
        a = generate_inflow(self.config, dt_s=1, horizon=128)
        values = a.values.copy(); values[2,1] = 10
        with self.assertRaises(ValueError): InflowTrace(a.time_s,values,a.components,a.metadata)
        times = a.time_s.copy(); times[2] += .5
        with self.assertRaises(ValueError): InflowTrace(times,a.values,a.components,a.metadata)

    def test_tampered_file_rejected_before_parsing(self):
        meta=json.dumps({"version":"farm_entrance_v1","csv_sha256":"incorrect"})
        with patch("pathlib.Path.read_text",return_value=meta), patch("pathlib.Path.read_bytes",return_value=b"tampered"):
            with self.assertRaisesRegex(ValueError,"checksum"): InflowTrace.load("unused.csv")


class HeadingControllerTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(DEFAULT_CONFIG)
        self.cfg["environment"].update(horizon=8, wind_amplitude_m_s=0, wind_noise_std_m_s=0)

    def trajectory(self, theta):
        return np.column_stack((np.full(9,8), theta, np.full(9,.08)))

    def test_wind_step_changes_gamma_without_instant_heading_change(self):
        env = build_env(self.cfg)
        obs, initial = env.reset(options={"wind_trajectory":self.trajectory([1]+[1.1]*8)})
        _, _, _, _, nxt = env.step(env.previous_action)
        np.testing.assert_allclose(nxt["heading_rad"], initial["heading_rad"], atol=1e-7)
        np.testing.assert_allclose(nxt["applied"][:,0], -.1, atol=1e-6)
        self.assertTrue(np.all(np.abs(nxt["applied"][:,0]-initial["applied"][:,0]) > env.config["rate_limits"][0]))
        before = nxt["heading_rad"]
        _, _, _, _, nxt = env.step(env.previous_action)
        np.testing.assert_allclose(nxt["heading_rad"]-before, .005, atol=1e-7)

    def test_shortest_path_across_north_and_reset(self):
        env = build_env(self.cfg)
        env.reset(options={"wind_trajectory":self.trajectory([2*np.pi-.02]+[.02]*8)})
        env.step(env.previous_action)
        before = env.heading.copy()
        _, _, _, _, info = env.step(env.previous_action)
        self.assertTrue(np.all(info["heading_rad"] > before))
        self.assertTrue(np.all(info["heading_rad"]-before <= .005+1e-7))
        np.testing.assert_allclose(info["applied"][:,0],wrap_angle(info["heading_rad"]-.02),atol=1e-6)
        _,info = env.reset(options={"wind_trajectory":self.trajectory([1]*9)})
        np.testing.assert_allclose(info["heading_rad"],1)

    def test_domain_rejects_whole_trace_and_unclipped_gamma(self):
        env = build_env(self.cfg)
        trace = self.trajectory([1]*9); trace[-1,0] = 25
        with self.assertRaisesRegex(ValueError,"PINN domain"): env.reset(options={"wind_trajectory":trace})
        env.reset(options={"wind_trajectory":self.trajectory([1]+[2]*8)})
        with self.assertRaisesRegex(ValueError,"domain"): env.step(env.previous_action)

    def test_baseline_all_channels_and_shared_actuator(self):
        a, b = build_env(self.cfg), build_env(self.cfg)
        obs,_ = a.reset(); b.reset()
        cfg = dict(self.cfg["baselines"],yaw_offset_rad=.1)
        controller = PitchController(a,cfg,"pi")
        action = controller.act(obs)
        self.assertTrue(np.all(action[:,0] > 0))
        self.assertGreater(np.ptp(action[:,2]),0)
        self.assertFalse(np.array_equal(action[:,2],a.previous_action[:,2]))
        _,_,_,_,ia = a.step(action)
        _,_,_,_,ib = b.step(action)
        np.testing.assert_array_equal(ia["applied"],ib["applied"])
        np.testing.assert_array_equal(ia["power_w"],ib["power_w"])

    def test_masks_policy_noise_replay_and_target_gradients(self):
        torch.set_num_threads(1)
        self.cfg["environment"]["control_mask"] = [0,1,0]
        env=build_env(self.cfg); obs,_=env.reset(); agent=make_agent(self.cfg,env)
        fixed=env.previous_action.copy()
        action=agent.act(obs,noise_std=100)
        np.testing.assert_array_equal(action[:,[0,2]], fixed[:,[0,2]])
        nxt,rew,done,_,info=env.step(np.ones((3,3)))
        np.testing.assert_array_equal(info["executed_action"][:,[0,2]],fixed[:,[0,2]])
        agent.replay.add(obs,info["executed_action"],rew,nxt,done)
        np.testing.assert_array_equal(agent.replay.data["actions"][0,:,0],fixed[:,0])
        x=torch.tensor(obs[0]); output=agent.policy(agent.actors[0],x)
        output[[0,2]].sum().backward()
        self.assertTrue(all(torch.count_nonzero(p.grad)==0 for p in agent.actors[0].parameters()))
        baseline=PitchController(env,self.cfg["baselines"],"p")
        np.testing.assert_array_equal(baseline.act(obs)[:,[0,2]],fixed[:,[0,2]])
        buffer=io.BytesIO(); agent.save(buffer,{}); buffer.seek(0)
        restored,_=MADDPG.load(buffer)
        np.testing.assert_array_equal(agent.act(obs,.2),restored.act(obs,.2))

    def test_random_inflow_requires_heading_dynamics(self):
        self.cfg["environment"].update(yaw_frame="legacy_misalignment",inflow={"speed":{}})
        with self.assertRaisesRegex(ValueError,"requires nacelle_heading"): build_env(self.cfg)


if __name__ == "__main__": unittest.main()
