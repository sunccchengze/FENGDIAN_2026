"""Speed n-step target, chronology, default compatibility and exact recovery."""
from copy import deepcopy
from dataclasses import replace
import io
import unittest
import numpy as np
import torch

from optimization_control.maddpg_wind_farm.frozen_speed_algorithm import FrozenSpeedConfig,FrozenSpeedMADDPG
from optimization_control.maddpg_wind_farm.speed_nstep_algorithm import FrozenSpeedNStepMADDPG,VerifiedSequenceReplay
from optimization_control.maddpg_wind_farm.verify_anchor import comparable
from optimization_control.utils.reference_schedule import speed_torch


def obs(t,episode=0):
    x=np.full((3,15),episode+t/100,np.float32)
    x[:,1]=.3+t/100;x[:,14]=1-t/16
    x[:,5:8]=action(t-1) if t else 0
    return x

def action(t):
    a=np.zeros((3,3),np.float32);a[:,1]=-.6+t/100;a[:,2]=t/100
    return a

def fill(replay,count,start=0):
    for j in range(start,start+count):
        episode,t=divmod(j,16)
        replay.add(obs(t,episode),action(t),np.full(3,100*(j+1),np.float32),obs(t+1,episode),t==15)

def clone(a):
    f=io.BytesIO();a.save(f,{});f.seek(0)
    return FrozenSpeedMADDPG.load(f)[0]

def adapt(a,n,count,actual_count=35):
    return FrozenSpeedNStepMADDPG.adapt(a,n,insertion_count=count,horizon=16,epoch='synthetic_seed42',
        evidence=dict(expected_insertions=actual_count,source_id='explicit_synthetic_generation'))

def equal_networks(a,b):
    for key in ('actors','target_actors','critics','target_critics','speed_heads','target_speed_heads'):
        np.testing.assert_equal(comparable(getattr(a,key).state_dict()),comparable(getattr(b,key).state_dict()))
    for key in ('head_optimizers','critic_optimizers'):
        np.testing.assert_equal(comparable([o.state_dict() for o in getattr(a,key)]),comparable([o.state_dict() for o in getattr(b,key)]))


class SpeedNStepTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.c=FrozenSpeedConfig(hidden=8,batch_size=4,capacity=32,gamma=.5,action_mask=(0,1,1))
        self.base=FrozenSpeedMADDPG(self.c);fill(self.base.replay,35)

    def test_n1_exact_losses_networks_adam_rng_and_legacy_v4_behavior(self):
        original=clone(self.base);candidate=adapt(clone(self.base),1,35)
        for _ in range(3):
            self.assertEqual(original.update(),candidate.update());equal_networks(original,candidate)
            np.testing.assert_equal(original.replay.state_dict(),{k:v for k,v in candidate.replay.state_dict().items() if k in original.replay.state_dict()})
        self.assertEqual(FrozenSpeedNStepMADDPG(self.c).n,1)
        f=io.BytesIO();original.save(f,{'legacy':True});f.seek(0)
        self.assertIs(type(FrozenSpeedMADDPG.load(f)[0]),FrozenSpeedMADDPG)

    def test_full_ring_wrap_new_writes_and_actual_tail(self):
        r=adapt(clone(self.base),8,35).replay
        rewards,ends,m=r.spans([2,3,30])
        np.testing.assert_array_equal(m,[1,8,2]);np.testing.assert_array_equal(ends,[2,10,31])
        fill(r,5,35)
        _,_,m=r.spans([2,7,8]);np.testing.assert_array_equal(m,[6,1,8])
        self.assertEqual(r.insertions,40)
        np.testing.assert_array_equal(r.sequence[(r.position+np.arange(32))%32],np.arange(8,40))

    def test_missing_count_wrong_count_and_continuity_fail_without_mutation(self):
        a=clone(self.base);before=a.replay.state_dict()
        for count in (None,34,67):
            with self.assertRaises(ValueError):adapt(a,8,count)
            self.assertIs(type(a),FrozenSpeedMADDPG)
        a.replay.data['obs'][4,0,0]+=.1
        with self.assertRaises(ValueError):adapt(a,8,35)
        r=adapt(clone(self.base),8,35).replay
        with self.assertRaises(ValueError):r.add(obs(5,2),action(5),np.ones(3,np.float32),obs(6,2),False)
        with self.assertRaises(ValueError):r.add(obs(3,2),action(3),np.ones(3,np.float32),obs(4,2),[True,False,False])

    def test_terminal_missing_tail_and_scaled_reward_once(self):
        a=FrozenSpeedMADDPG(self.c);fill(a.replay,20);a=adapt(a,8,20,20)
        values,ends,m=a.replay.spans([0,14,16,19])
        np.testing.assert_array_equal(m,[8,2,4,1]);np.testing.assert_array_equal(ends,[7,15,19,19])
        for j,(start,length) in enumerate(zip((0,14,16,19),m)):
            expected=np.zeros(3,np.float32)
            for k in range(length):expected+=(.5**k)*a.replay.data['rewards'][start+k]
            np.testing.assert_array_equal(values[j],expected)
        a.replay.sample(4,'cpu');discount=a.replay.discounts
        y=a.td_target(torch.ones((4,1)),torch.tensor([[1.],[0.],[0.],[1.]]),torch.full((4,1),7.),.5)
        np.testing.assert_array_equal(y.numpy(),(1+discount*torch.tensor([[0.],[1.],[1.],[0.]])*7).numpy())

    def test_endpoint_target_input_total_action_and_current_radius(self):
        a=adapt(clone(self.base),8,35);a.config=replace(a.config,speed_scale=2*.06/.667)
        with torch.no_grad():
            for h in a.target_speed_heads:h[-2].bias.fill_(.4)
            for h in a.speed_heads:h[-2].bias.fill_(-.2)
        inputs=[];handle=a.target_critics[0].register_forward_pre_hook(lambda _,args:inputs.append(args[0].detach().clone()))
        a.update();handle.remove()
        starts=a.replay.last_indices;_,ends,m=a.replay.spans(starts)
        future=torch.tensor(a.replay.data['next_obs'][ends]);joint=inputs[0][:,45:].reshape(-1,3,3)
        np.testing.assert_array_equal(inputs[0][:,:45].numpy(),future.flatten(1).numpy())
        # Captured before Polyak changed target heads; invert the inherited update with a pre-copy.
        before=adapt(clone(self.base),8,35);before.config=replace(before.config,speed_scale=2*.06/.667)
        with torch.no_grad():
            for h in before.target_speed_heads:h[-2].bias.fill_(.4)
            pitch=torch.stack([before.target_actors[i](future[:,i])[:,1] for i in range(3)],1)
            raw=torch.stack([before.target_speed_heads[i](future[:,i]).squeeze(-1) for i in range(3)],1)
            speed=(speed_torch(future,before.config.speed_schedule)+raw*before.config.speed_scale).clamp(-1,1)
        np.testing.assert_array_equal(joint[:,:,0].numpy(),np.zeros((4,3),np.float32))
        np.testing.assert_array_equal(joint[:,:,1].numpy(),pitch.numpy());np.testing.assert_array_equal(joint[:,:,2].numpy(),speed.numpy())

    def test_actor_and_parent_target_paths_stay_original_forms(self):
        a=adapt(clone(self.base),8,35)
        with torch.no_grad():
            for p in a.target_actors.parameters():p.add_(.03)
        old=deepcopy(a.actors.state_dict());targets=deepcopy(a.target_actors.state_dict())
        self.assertIs(FrozenSpeedNStepMADDPG.update,FrozenSpeedMADDPG.update)
        a.update()
        np.testing.assert_equal(comparable(old),comparable(a.actors.state_dict()))
        for k,v in targets.items():self.assertTrue(torch.equal(v.lerp(old[k],a.config.tau),a.target_actors.state_dict()[k]))

    def test_restore_next_update_and_reject_metadata_or_horizon(self):
        a=adapt(clone(self.base),8,35);a.update();f=io.BytesIO();a.save(f,{'engineering_only':True});f.seek(0)
        b,meta=FrozenSpeedNStepMADDPG.load(f,expected_n=8)
        self.assertTrue(meta['engineering_only']);self.assertEqual(a.update(),b.update());equal_networks(a,b)
        np.testing.assert_equal(a.replay.state_dict(),b.replay.state_dict())
        f.seek(0)
        with self.assertRaises(ValueError):FrozenSpeedNStepMADDPG.load(f,expected_n=1)
        f.seek(0)
        with self.assertRaises(ValueError):FrozenSpeedMADDPG.load(f)
        state=a.replay.state_dict()
        for key in ('epoch','horizon','sequence','migration_proof'):
            bad=deepcopy(state);bad.pop(key)
            with self.assertRaises(ValueError):a.replay.load_state_dict(bad)
        bad=deepcopy(state);bad['sequence'][0],bad['sequence'][1]=bad['sequence'][1],bad['sequence'][0]
        with self.assertRaises(ValueError):a.replay.load_state_dict(bad)

    def test_new_empty_sequence_buffer_serializes_without_legacy_defaults(self):
        r=VerifiedSequenceReplay(self.c,8,horizon=16,epoch='explicit_new_buffer')
        fill(r,5)
        state=r.state_dict();other=VerifiedSequenceReplay(self.c,8,horizon=16,epoch='explicit_new_buffer')
        other.load_state_dict(state)
        np.testing.assert_equal(state,other.state_dict())
        self.assertEqual(state['migration_proof']['insertion_count'],0)


if __name__=='__main__':unittest.main()
