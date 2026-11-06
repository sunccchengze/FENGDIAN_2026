"""One-factor Actor learning-rate state and checkpoint contract."""
from copy import deepcopy
import io
import unittest
import numpy as np
import torch
from optimization_control.tests import test_residual_control as fixtures
from optimization_control.maddpg_wind_farm import residual_stability as flow
from optimization_control.maddpg_wind_farm.residual_algorithm import ResidualMADDPG
from optimization_control.maddpg_wind_farm.verify_residual_stability import comparable

class ActorLearningRateTests(unittest.TestCase):
    setUp = fixtures.ResidualTests.setUp
    def child(self):
        speed = ResidualMADDPG.inherit(self.agent, (0, 1, 1), (0., 1., .3))
        return ResidualMADDPG.inherit(speed, (1, 1, 1), (.2, 1., .3))
    def test_only_lr_differs_and_parent_state_preserved(self):
        parent = self.child()
        a,b=deepcopy(parent),deepcopy(parent)
        state=torch.get_rng_state().clone()
        for agent,lr in ((a,1e-4),(b,3e-5)):
            flow.configure_actor_lr(agent,lr)
            flow.assert_actor_lr(agent,lr)
            self.assertTrue(all(not opt.state for opt in agent.actor_optimizers))
            np.testing.assert_equal(agent.replay.state_dict(),parent.replay.state_dict())
            for kind in ('actors','target_actors','critics','target_critics'):
                for key,value in getattr(agent,kind).state_dict().items():
                    self.assertTrue(torch.equal(value,getattr(parent,kind).state_dict()[key]))
            np.testing.assert_equal(comparable(agent.critic_optimizers[0].state_dict()),comparable(parent.critic_optimizers[0].state_dict()))
        self.assertTrue(torch.equal(state,torch.get_rng_state()))
        cfg_a,cfg_b=dict(a.config.__dict__),dict(b.config.__dict__)
        cfg_a.pop('actor_lr');cfg_b.pop('actor_lr')
        self.assertEqual(cfg_a,cfg_b)
    def test_lr_roundtrip_and_next_update(self):
        agent=self.child();flow.configure_actor_lr(agent,3e-5)
        out=io.BytesIO();agent.save(out,{'step':2048});out.seek(0)
        restored,meta=ResidualMADDPG.load(out)
        flow.assert_actor_lr(restored,3e-5)
        self.assertEqual(meta['step'],2048)
        self.assertEqual(agent.update(),restored.update())
        for key,value in agent.actors.state_dict().items():
            self.assertTrue(torch.equal(value,restored.actors.state_dict()[key]))
    def test_mismatched_config_optimizer_is_rejected(self):
        agent=self.child();flow.configure_actor_lr(agent,3e-5)
        agent.actor_optimizers[1].param_groups[0]['lr']=1e-4
        with self.assertRaisesRegex(ValueError,'learning rates'):
            flow.assert_actor_lr(agent,3e-5)
    def test_protocol_rejects_extra_candidate(self):
        import tempfile,yaml
        from pathlib import Path
        p=flow.read_protocol(flow.DEFAULT)
        p['arms']['low_lr']['actor_lr']=2e-5
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.yaml';path.write_text(yaml.safe_dump(p),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'predeclared'):
                flow.read_protocol(path)

if __name__=='__main__':unittest.main()
