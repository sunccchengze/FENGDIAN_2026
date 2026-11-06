"""Joint transfer permission, rollback, optimizer and exact restore contracts."""
from copy import deepcopy
import contextlib
import io
import unittest
import numpy as np
import torch
from optimization_control.tests import test_progressive_random_control as fixtures
from optimization_control.maddpg_wind_farm import joint_distillation as flow
from optimization_control.maddpg_wind_farm.algorithm import MADDPG

class JointDistillationTests(unittest.TestCase):
    setUp = fixtures.ProgressiveControlTests.setUp

    def settings(self):
        return dict(sample_rows=256,batch_size=64,old_max_error=.02,new_max_error=.05,old_loss_weight=10.,candidates=[dict(updates=1000,lr=.001)])

    def transfer(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return flow.distill(self.agent,[0,1,1],self.settings())

    def test_joint_fit_preserves_critics_replay_rng_and_resets_actor_moments(self):
        critic=deepcopy(self.agent.critics.state_dict()); replay=self.agent.replay.state_dict()
        rng=deepcopy(self.agent.rng.bit_generator.state)
        report=self.transfer(); self.assertTrue(report['passed'])
        self.assertIsNone(self.agent.config.speed_reference_schedule)
        self.assertTrue(all(not optimizer.state for optimizer in self.agent.actor_optimizers))
        self.assertTrue(all(torch.equal(v,self.agent.critics.state_dict()[k]) for k,v in critic.items()))
        self.assertEqual(rng,self.agent.rng.bit_generator.state)
        self.assertEqual(replay['rng'],self.agent.replay.state_dict()['rng'])
        for key,value in replay['data'].items(): np.testing.assert_array_equal(value,self.agent.replay.state_dict()['data'][key])
        self.assertTrue(all(not p.requires_grad for p in self.agent.target_actors.parameters()))

    def test_failed_candidate_rolls_back_and_grants_no_permission(self):
        before=deepcopy(self.agent.actors.state_dict()); target=deepcopy(self.agent.target_actors.state_dict())
        d=self.settings(); d.update(old_max_error=0.,new_max_error=0.); d['candidates']=[dict(updates=1,lr=.001)]
        with contextlib.redirect_stdout(io.StringIO()): r=flow.distill(self.agent,[0,1,1],d)
        self.assertFalse(r['passed']); self.assertEqual(tuple(self.agent.config.action_mask),(0,1,0))
        self.assertTrue(all(torch.equal(v,self.agent.actors.state_dict()[k]) for k,v in before.items()))
        self.assertTrue(all(torch.equal(v,self.agent.target_actors.state_dict()[k]) for k,v in target.items()))

    def test_cannot_skip_or_remove_channel(self):
        for mask in ([1,1,1],[0,1,0],[0,0,1]):
            with self.assertRaises(ValueError): flow.distill(self.agent,mask,self.settings())

    def test_transferred_checkpoint_restores_exact_noise_and_next_update(self):
        self.assertTrue(self.transfer()['passed'])
        stream=io.BytesIO(); self.agent.save(stream,dict(test=True)); stream.seek(0)
        other,_=MADDPG.load(stream)
        np.testing.assert_array_equal(self.agent.act(self.obs,.03),other.act(self.obs,.03))
        self.assertEqual(self.agent.update(),other.update())

    def test_frozen_protocol_bounds_and_original_precision(self):
        p=flow.read_protocol(flow.DEFAULT)
        self.assertEqual(p['gate']['mean_validation_rmse_w'],400000.)
        self.assertEqual(p['gate']['worst_validation_rmse_w'],500000.)
        self.assertEqual(p['steps_per_run'],16384)
        self.assertEqual(len(p['distillation']['candidates']),2)

if __name__=='__main__': unittest.main()
