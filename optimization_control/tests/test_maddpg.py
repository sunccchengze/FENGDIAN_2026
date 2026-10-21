"""Behavioral tests for PINN mapping, three-agent transitions and MADDPG updates."""

from copy import deepcopy
import io
import unittest
import numpy as np
import torch

from optimization_control.environments.pinn_adapter import PINNAdapter, DEFAULT_FEATURES
from optimization_control.environments.plant_model import AppliedOperatingPoint, DisturbanceBatch
from optimization_control.maddpg_wind_farm.algorithm import AlgorithmConfig, MADDPG
from optimization_control.maddpg_wind_farm.controllers import PitchController
from optimization_control.maddpg_wind_farm.workflow import build_env, load_config, DEFAULT_CONFIG


def fixture_backend(config):
    """Backend-factory fixture; no real PINN or external access."""
    return lambda x: np.tile([1e6, 2e6, 3e6, 8, 7, 6], (len(x), 1)).astype(np.float32)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(DEFAULT_CONFIG)
        self.d = DisturbanceBatch(np.array([[8], [9]]), np.array([[1], [2]]), np.array([[.08], [.1]]))
        self.op = AppliedOperatingPoint(("T01", "T02", "T03"), np.array([[.01,.02,.03]]*2),
                                        np.array([[.1,.2,.3]]*2), np.array([[.7,.8,.9]]*2))

    def adapter(self, predictor=None, **kwargs):
        p = self.cfg["plant"]
        return PINNAdapter(predictor or fixture_backend({}), bounds=kwargs.pop("bounds", p["bounds"]),
                           power_semantics="test", **kwargs)

    def test_order_and_output_split(self):
        a = self.adapter()
        np.testing.assert_allclose(a.encode(self.d, self.op)[0], [8,1,.08,.01,.02,.03,.1,.2,.3,.7,.8,.9])
        out = a.predict_steady(self.d, self.op)
        np.testing.assert_array_equal(out.floris_turbine_power_w[0], [1e6,2e6,3e6])
        np.testing.assert_array_equal(out.effective_wind_speed_m_s[0], [8,7,6])
        np.testing.assert_array_equal(out.floris_farm_power_sum_w, [[6e6],[6e6]])

    def test_reordered_extended_features_and_scaling(self):
        names = tuple(reversed(DEFAULT_FEATURES)) + ("density",)
        bounds = dict(self.cfg["plant"]["bounds"], density=[1,2])
        seen = []
        def predict(x):
            seen.append(x.copy())
            return np.tile([1,2,3,4,5,6], (len(x),1))
        a = self.adapter(predict, features=names, bounds=bounds, constants={"density":1.225},
                         input_mean=[1]*13, input_scale=[2]*13,
                         output_mean=[10]*6, output_scale=[2]*6)
        out = a.predict_steady(self.d, self.op)
        np.testing.assert_allclose(seen[0], (a.encode(self.d,self.op)-1)/2)
        np.testing.assert_array_equal(out.floris_turbine_power_w[0], [12,14,16])
        self.assertAlmostEqual(float(a.encode(self.d,self.op)[0,0]), .9, places=6)

    def test_direction_encoding_and_dynamic_extra(self):
        names = tuple(n for n in DEFAULT_FEATURES if n != "ambient_wind_direction_rad") + ("wind_direction_sin", "wind_direction_cos", "density")
        bounds = {n: self.cfg["plant"]["bounds"][n] for n in names if n in self.cfg["plant"]["bounds"]}
        bounds.update(wind_direction_sin=[-1,1], wind_direction_cos=[-1,1], density=[1,2])
        a = self.adapter(features=names, bounds=bounds, extra_provider=lambda d,o: {"density":np.array([1.2,1.3])})
        encoded = a.encode(self.d,self.op)
        np.testing.assert_allclose(encoded[:,-3], np.sin([1,2]), rtol=1e-6)
        np.testing.assert_allclose(encoded[:,-1], [1.2,1.3])

    def test_missing_control_unknown_input_and_override_rejected(self):
        with self.assertRaises(ValueError):
            self.adapter(features=DEFAULT_FEATURES[:-1])
        bounds = dict(self.cfg["plant"]["bounds"], density=[1,2])
        with self.assertRaisesRegex(ValueError,"missing PINN"):
            self.adapter(features=DEFAULT_FEATURES+("density",),bounds=bounds).encode(self.d,self.op)
        with self.assertRaisesRegex(ValueError,"overwrite"):
            self.adapter(constants={"gamma_1":0}).encode(self.d,self.op)

    def test_output_and_domain_failures(self):
        for output in (np.zeros((2,5)), np.full((2,6),np.nan), np.full((2,6),-1), np.full((2,6),1e8)):
            with self.subTest(output=output.shape), self.assertRaises(ValueError):
                self.adapter(lambda x: output).predict_steady(self.d,self.op)
        bad = DisturbanceBatch(np.array([[25],[25]]),np.array([[1],[1]]),np.array([[.1],[.1]]))
        with self.assertRaisesRegex(ValueError,"domain"):
            self.adapter().predict_steady(bad,self.op)

    def test_factory_backend_uses_real_path_without_mock_fallback(self):
        cfg=deepcopy(self.cfg)
        cfg["plant"].update(kind="pinn", source="backend_contract_fixture", model_version="test", factory=__name__+":fixture_backend")
        cfg["plant"]["layout"]["spacing_m"] = 378
        env=build_env(cfg)
        _,info=env.reset()
        self.assertEqual(info["farm_power_w"],6e6)
        self.assertEqual(info["source"],"backend_contract_fixture")


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.cfg=load_config(DEFAULT_CONFIG)
        self.cfg["environment"]["horizon"]=8
        self.env=build_env(self.cfg)

    def test_shapes_target_terminal_and_rate_bounds(self):
        obs,info=self.env.reset(options={"target_w":2e6})
        self.assertEqual(obs.shape,(3,15))
        before=info["applied"]
        for k in range(8):
            obs,reward,done,truncated,info=self.env.step(np.ones((3,3)))
            self.assertTrue(np.all(np.abs(info["applied"]-before) <= np.array(self.cfg["environment"]["rate_limits"])+1e-7))
            before=info["applied"]
            self.assertEqual(info["target_w"],2e6)
            self.assertEqual(done,k==7)
            self.assertFalse(truncated)
            np.testing.assert_array_equal(reward,np.repeat(reward[0],3))
        self.assertEqual(obs[0,-1],0)
        with self.assertRaises(RuntimeError): self.env.step(np.zeros((3,3)))

    def test_seeded_reset_and_history_reset(self):
        first=[]
        for _ in range(2):
            obs,_=self.env.reset(seed=42)
            trajectory=[obs]
            for k in range(8): trajectory.append(self.env.step(np.full((3,3),.1*k))[0])
            first.append(trajectory)
        np.testing.assert_array_equal(first[0],first[1])

    def test_coupled_mock_changes_downstream(self):
        self.env.reset()
        plant=self.env.plant
        d=DisturbanceBatch(np.array([[8]]),np.array([[4.71]]),np.array([[.08]]))
        op=AppliedOperatingPoint(plant.turbine_ids,np.zeros((1,3)),np.zeros((1,3)),np.full((1,3),.9))
        original=plant.predict_steady(d,op)
        op2=AppliedOperatingPoint(plant.turbine_ids,np.array([[.4,0,0]]),np.zeros((1,3)),np.full((1,3),.9))
        changed=plant.predict_steady(d,op2)
        self.assertGreater(changed.effective_wind_speed_m_s[0,1],original.effective_wind_speed_m_s[0,1])

    def test_baseline_p_sign_and_pi_antiwindup(self):
        obs,_=self.env.reset()
        p=PitchController(self.env,self.cfg["baselines"],"p")
        low=obs.copy(); high=obs.copy()
        low[:,9]=-.1; high[:,9]=.1
        self.assertTrue(np.all(p.act(high)[:,1]>p.act(low)[:,1]))
        pi=PitchController(self.env,self.cfg["baselines"],"pi")
        for _ in range(2000): pi.act(high)
        self.assertLessEqual(abs(pi.integral),self.cfg["baselines"]["integral_limit_rad"])
        pi.reset(); self.assertEqual(pi.integral,0)


class AlgorithmTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.agent=MADDPG(AlgorithmConfig(hidden=16,batch_size=8,capacity=64))
        rng=np.random.default_rng(42)
        for _ in range(32):
            self.agent.replay.add(rng.normal(size=(3,15)),rng.uniform(-1,1,(3,3)),
                                  rng.normal(size=3),rng.normal(size=(3,15)),False)

    def test_all_actors_critics_and_soft_targets_update(self):
        a=self.agent
        before=[[p.detach().clone() for p in m.parameters()] for m in a.actors]
        critics=[[p.detach().clone() for p in m.parameters()] for m in a.critics]
        targets=[p.detach().clone() for p in a.target_actors.parameters()]
        loss=a.update()
        self.assertTrue(all(np.isfinite(list(loss.values()))))
        for i in range(3):
            self.assertTrue(any(not torch.equal(x,y) for x,y in zip(before[i],a.actors[i].parameters())))
            self.assertTrue(any(not torch.equal(x,y) for x,y in zip(critics[i],a.critics[i].parameters())))
        for old,current,target in zip(targets,a.actors.parameters(),a.target_actors.parameters()):
            torch.testing.assert_close(target,old*(1-a.config.tau)+current*a.config.tau)
            self.assertIsNone(target.grad)

    def test_terminal_mask(self):
        y=MADDPG.td_target(torch.tensor([[2.],[2.]]),torch.tensor([[1.],[0.]]),torch.tensor([[10.],[10.]]),.9)
        torch.testing.assert_close(y,torch.tensor([[2.],[11.]]))

    def test_checkpoint_exact_action_noise_replay_and_next_update(self):
        a=self.agent; a.update()
        buffer=io.BytesIO(); a.save(buffer,{"test":True}); buffer.seek(0)
        b,metadata=MADDPG.load(buffer)
        obs=np.ones((3,15),np.float32)
        np.testing.assert_array_equal(a.act(obs),b.act(obs))
        np.testing.assert_array_equal(a.act(obs,.1),b.act(obs,.1))
        self.assertEqual(metadata,{"test":True})
        self.assertEqual(a.update(),b.update())
        for x,y in zip(a.actors.parameters(),b.actors.parameters()): torch.testing.assert_close(x,y,rtol=0,atol=0)

    def test_replay_ring_and_action_bounds(self):
        a=self.agent
        for k in range(80): a.replay.add(np.full((3,15),k),np.zeros((3,3)),np.zeros(3),np.ones((3,15)),k%2==0)
        self.assertEqual(a.replay.size,64)
        self.assertTrue(np.all(a.replay.data["obs"][:,0,0]>=16))
        action=a.act(np.zeros((3,15)),noise_std=100)
        self.assertTrue(np.all(np.abs(action)<=1))


if __name__ == "__main__":
    unittest.main()
