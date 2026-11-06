"""Causal timing, PI units, reset and conditional saturation; no Plant inputs."""
from types import SimpleNamespace
import unittest
import numpy as np
from optimization_control.maddpg_wind_farm.pitch_integral_controller import FrozenPitchIntegral
from optimization_control.maddpg_wind_farm.controllers import PitchController


class Parent:
    def __init__(self): self.action = np.zeros((3, 3), np.float32)
    def act(self, obs): return self.action.copy()


def env():
    return SimpleNamespace(dt=1., rated=np.array([5e6]*3), low=np.array([-.4, 0., .6]),
                           high=np.array([.4, .22, 1.267]), initial=np.array([0., .04, 1.]),
                           applied=np.tile([0., .19, 1.], (3, 1)),
                           normalize_commands=lambda p: p.copy(), project_action=lambda p: p.copy())


class IntegralContracts(unittest.TestCase):
    def test_zero_correction_preserves_exact_parent_and_background(self):
        p=Parent();p.action=np.arange(9,dtype=np.float32).reshape(3,3)/10
        c=FrozenPitchIntegral(env(),p,{'ki':.08},enabled=False);obs=np.zeros((3,15),np.float32);obs[:,9]=.1
        for _ in range(4):self.assertTrue(np.array_equal(c.act(obs),p.action));self.assertEqual(c.integral,0.)

    def test_pi_units_and_one_action_delay_use_current_error_only(self):
        e=env();p=Parent();c=FrozenPitchIntegral(e,p,{'ki':.08});obs=np.zeros((3,15),np.float32);obs[:,9]=.1
        config=dict(pitch_bias_rad=.04,kp=1.5,ki=.08,antiwindup_gain=.2,integral_limit_rad=.3)
        # Actual equals this PI decision, so the existing tracking term is exactly zero.
        e.applied[:,1]=.04+1.5*float(obs[0,9]);pi=PitchController(e,config,'pi');pi.act(obs)
        a=c.act(obs);self.assertTrue(np.array_equal(a,p.action));self.assertEqual(c.integral,pi.integral)
        self.assertAlmostEqual(c.integral,.008,places=8)
        obs[:,9]=-.1;b=c.act(obs)
        np.testing.assert_allclose(b[:,1],2*pi.integral/.22,atol=1e-8)
        self.assertEqual(c.last['integral_used_rad'],pi.integral);self.assertEqual(c.integral,0.)

    def test_reset_and_correction_limit_allow_reverse_unwinding(self):
        c=FrozenPitchIntegral(env(),Parent(),{'ki':.08});obs=np.zeros((3,15),np.float32);obs[:,9]=.1
        for _ in range(5):c.act(obs)
        self.assertEqual(c.integral,.02);self.assertEqual(c.last['integral_blocked'],1)
        obs[:,9]=-.1;c.act(obs);self.assertLess(c.integral,.02)
        c.reset();self.assertEqual(c.integral,0.);self.assertIsNone(c.last)

    def test_total_target_saturation_blocks_same_direction_and_allows_reverse(self):
        p=Parent();p.action[0,1]=1.;c=FrozenPitchIntegral(env(),p,{'ki':.08});obs=np.zeros((3,15),np.float32);obs[:,9]=.1
        c.act(obs);self.assertEqual(c.integral,0.);self.assertEqual(c.last['integral_blocked'],1)
        obs[:,9]=-.1;c.act(obs);self.assertLess(c.integral,0.)
        p.action[:,1]=-1.;c.reset();c.act(obs);self.assertEqual(c.integral,0.)
        obs[:,9]=.1;c.act(obs);self.assertGreater(c.integral,0.)
        for _ in range(20):a=c.act(obs)
        self.assertTrue(np.all(np.abs(a)<=1.));self.assertEqual(c.integral,.02)


if __name__=='__main__':unittest.main()
