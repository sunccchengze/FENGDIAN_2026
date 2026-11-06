"""Numerical takeover, frozen-gradient paths, target lag and exact v4 recovery."""
from copy import deepcopy
import io
import unittest
import numpy as np
import torch

from optimization_control.tests import test_progressive_random_control as fixtures
from optimization_control.maddpg_wind_farm.frozen_speed_algorithm import FrozenSpeedMADDPG, load_policy
from optimization_control.maddpg_wind_farm.algorithm import MADDPG
from optimization_control.maddpg_wind_farm.residual_algorithm import ResidualMADDPG
from optimization_control.maddpg_wind_farm.anchor_algorithm import AnchoredMADDPG
from optimization_control.maddpg_wind_farm.verify_anchor import comparable
from optimization_control.maddpg_wind_farm.workflow import build_env
from optimization_control.maddpg_wind_farm.controllers import PitchController
from optimization_control.utils.reference_schedule import speed_numpy, speed_torch


class FrozenSpeedTests(unittest.TestCase):
    setUp=fixtures.ProgressiveControlTests.setUp

    def child(self):return FrozenSpeedMADDPG.from_parent(self.agent,8405)

    def test_float32_schedule_matches_torch_exactly(self):
        obs=np.random.default_rng(42).uniform(-.2,1.2,(10000,15)).astype(np.float32)
        schedule=(25.,1.267/11.4,.6,1.267)
        np.testing.assert_array_equal(speed_numpy(obs,schedule),speed_torch(torch.tensor(obs),schedule).numpy())

    def test_zero_head_online_target_and_inherited_training_state(self):
        child=self.child()
        for field in ('obs','next_obs'):
            for target in (False,True):
                for i in range(3):
                    obs=torch.tensor(self.agent.replay.data[field][:256,i])
                    actor=(self.agent.target_actors if target else self.agent.actors)[i]
                    np.testing.assert_array_equal(self.agent.policy(actor,obs).detach(),child.total_action(i,obs,target=target).detach())
        np.testing.assert_equal(child.replay.state_dict(),self.agent.replay.state_dict())
        for a,b in zip(child.critic_optimizers,self.agent.critic_optimizers):
            np.testing.assert_equal(comparable(a.state_dict()),comparable(b.state_dict()))
        self.assertTrue(all(not o.state for o in child.head_optimizers))

    def test_public_policy_dispatches_full_online_and_target_composition(self):
        child=self.child();obs=torch.tensor(self.obs)
        with torch.no_grad():child.speed_heads[0][-2].bias.fill_(.2)
        for target,actors in ((False,child.actors),(True,child.target_actors)):
            for i,actor in enumerate(actors):
                np.testing.assert_array_equal(child.policy(actor,obs[i]).detach(),child.total_action(i,obs[i],target=target).detach())
        with self.assertRaises(ValueError):child.policy(torch.nn.Identity(),obs[0])

    def test_only_heads_and_critics_train_parent_target_follows_polyak(self):
        child=self.child();old=deepcopy(child.actors.state_dict());targets=deepcopy(child.target_actors.state_dict())
        head=deepcopy(child.speed_heads.state_dict());seen=[]
        handle=child.critics[0].register_forward_pre_hook(lambda _,args:seen.append(args[0].shape[-1]))
        child.update();handle.remove()
        np.testing.assert_equal(comparable(old),comparable(child.actors.state_dict()))
        self.assertTrue(all(p.grad is None and not p.requires_grad for p in child.actors.parameters()))
        self.assertTrue(any(not torch.equal(v,child.speed_heads.state_dict()[k]) for k,v in head.items()))
        self.assertEqual(set(seen),{54})
        for k,v in targets.items():
            expected=v.clone().lerp_(old[k],child.config.tau)
            self.assertTrue(torch.equal(expected,child.target_actors.state_dict()[k]))

    def test_noise_only_changes_speed_inside_bounded_envelope(self):
        child=self.child();base=self.agent.act(self.obs)
        for sign in (-1,1):
            action=child.act(self.obs,noise=np.full((3,3),sign*100.))
            np.testing.assert_array_equal(action[:,:2],base[:,:2])
            self.assertLessEqual(float(np.abs(action[:,2]-base[:,2]).max()),child.config.speed_scale+1e-7)
        child.update()
        np.testing.assert_array_equal(child.act(self.obs,zero_speed=True),self.agent.act(self.obs))

    def test_v4_roundtrip_and_legacy_loaders_reject(self):
        child=self.child();child.update();buf=io.BytesIO();child.save(buf,{'step':128})
        for loader in (MADDPG,ResidualMADDPG,AnchoredMADDPG):
            buf.seek(0)
            with self.assertRaises(ValueError):loader.load(buf)
        buf.seek(0);other,meta=load_policy(buf)
        self.assertEqual(meta,{'step':128})
        self.assertEqual(child.update(),other.update())
        for k in ('actors','target_actors','critics','target_critics','speed_heads','target_speed_heads'):
            np.testing.assert_equal(comparable(getattr(child,k).state_dict()),comparable(getattr(other,k).state_dict()))
        for a,b in zip(child.head_optimizers,other.head_optimizers):np.testing.assert_equal(comparable(a.state_dict()),comparable(b.state_dict()))

    def test_new_projection_and_controller_match_actor_reference(self):
        cfg=deepcopy(self.cfg);cfg['environment']['speed_reference_mode']='observation_float32_v1'
        env=build_env(cfg);obs,_=env.reset()
        for _ in range(128):
            action=self.agent.act(obs)
            np.testing.assert_array_equal(action,env.project_action(action))
            obs,_,done,_,_=env.step(action)
        self.assertTrue(done)
        for mask in ([0,1,0],[0,1,1]):
            cfg['environment']['control_mask']=mask;e=build_env(cfg);o,_=e.reset()
            for mode in ('fixed','p','pi'):
                action=PitchController(e,cfg['baselines'],mode).act(o)
                np.testing.assert_array_equal(action[:,2],e.scheduled_speed_action(o))

    def test_legacy_default_unchanged_and_unknown_mode_rejected(self):
        cfg=deepcopy(self.cfg);cfg['environment']['speed_reference_mode']='legacy_physical'
        env=build_env(cfg);a,_=env.reset();b,_=self.env.reset()
        np.testing.assert_array_equal(a,b)
        self.assertEqual(env.normalization(),self.env.normalization())
        for _ in range(128):
            action=self.agent.act(a);a,ra,da,_,ia=env.step(action);b,rb,db,_,ib=self.env.step(action)
            np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(ra,rb)
        cfg['environment']['speed_reference_mode']='unknown'
        with self.assertRaises(ValueError):build_env(cfg)


if __name__=='__main__':unittest.main()
