"""Only gamma-related new contracts; no environment rollouts or learning updates."""
from copy import deepcopy
import unittest
import numpy as np
import torch
from optimization_control.maddpg_wind_farm.algorithm import AlgorithmConfig
from optimization_control.maddpg_wind_farm.nstep_algorithm import NStepMADDPG,SequenceReplay
from optimization_control.maddpg_wind_farm.pitch_gamma_trial import adapt_gamma,fingerprint,state


class GammaTests(unittest.TestCase):
    def test_gamma1_ring_terminal_and_short_tail_by_hand(self):
        c=AlgorithmConfig(hidden=8,capacity=8,batch_size=3,gamma=1.)
        replay=SequenceReplay(c,8)
        def obs(j):
            ep,t=divmod(j,4);x=np.full((3,15),ep,np.float32);x[:,14]=1-t/128;return x
        for j in range(13):
            ep,t=divmod(j,4);nxt=obs(j+1) if t!=3 else np.full((3,15),99,np.float32)
            replay.add(obs(j),np.zeros((3,3),np.float32),np.array([1,2,3],np.float32)*(j+1),nxt,t==3)
        values,end,lengths=replay.spans([6,0,4])
        np.testing.assert_array_equal(lengths,[2,4,1]);np.testing.assert_array_equal(end,[7,3,4])
        np.testing.assert_array_equal(values,np.array([15,42,13])[:,None]*np.array([1,2,3]))
        a=NStepMADDPG(c).configure(8);a.replay=replay
        a.replay.discounts=torch.ones((3,1))
        done=torch.as_tensor(replay.data['terminated'][end])
        target=a.td_target(torch.as_tensor(values),done,torch.full((3,3),5.),1.)
        np.testing.assert_array_equal(target.numpy(),values+np.array([0,0,5])[:,None])

    def test_adaptation_changes_only_gamma_and_derived_cache(self):
        c=AlgorithmConfig(hidden=8,capacity=8,batch_size=3,gamma=.99)
        a=NStepMADDPG(c).configure(8);before=fingerprint(state(a));adapt_gamma(a,.99)
        self.assertEqual(before,fingerprint(state(a)))
        raw=fingerprint(a.replay.state_dict());net=fingerprint(a.actors.state_dict());rng=deepcopy(a.rng.bit_generator.state)
        a.replay.discounts=torch.zeros((1,1));adapt_gamma(a,1.)
        self.assertEqual(a.config.gamma,1.);self.assertEqual(a.replay.gamma,1.)
        self.assertIsNone(a.replay.discounts);self.assertEqual(raw,fingerprint(a.replay.state_dict()))
        self.assertEqual(net,fingerprint(a.actors.state_dict()));self.assertEqual(rng,a.rng.bit_generator.state)


if __name__=='__main__':unittest.main()
