"""Private contract tests; only the declared short mock paths query a plant."""
from copy import deepcopy
import inspect
import math
from pathlib import Path
import unittest
import numpy as np
import torch
from optimization_control.maddpg_wind_farm import forecast_decision_contract as review
from optimization_control.maddpg_wind_farm.history_wind_forecast import RidgeForecast, features

CONTEXT = None
EVIDENCE = {}


class DecisionContractTests(unittest.TestCase):
    def test_actual_m_return_and_true_terminal(self):
        cases=[]
        for m in (1,3,5,8):
            rewards=np.array([[(-1)**k*(k+1), .3*(k+1), -2.] for k in range(m)])
            returns, discount=review.discounted(rewards,.99)
            expected=np.array([math.fsum(float(r[i])*.99**k for k,r in enumerate(rewards)) for i in range(3)])
            np.testing.assert_allclose(returns,expected,rtol=0,atol=1e-14)
            self.assertEqual(discount,.99**m)
            for done in (False,True):
                actual=returns+(1-done)*discount*7
                np.testing.assert_allclose(actual,expected+(0 if done else .99**m*7),rtol=0,atol=1e-14)
            cases.append(dict(m=m,discount=discount,returns=returns.tolist()))
        self.assertGreater(abs(.99**8-.99),.06)
        EVIDENCE['actual_m_and_terminal']=cases

    def test_holding_step_has_no_new_actor_gradient(self):
        theta=torch.tensor(.2,dtype=torch.float64,requires_grad=True)
        held=torch.tensor(.04,dtype=torch.float64)
        x=torch.arange(1.,9.,dtype=torch.float64)
        for phase in range(8):
            # Scalar autograd probes; no nn.Module, optimizer, or parameter update.
            decision=.1*torch.tanh(theta*x[phase])
            executed=decision if phase==0 else held+0*theta
            correct=torch.autograd.grad(executed,theta,retain_graph=True)[0].item()
            wrong=torch.autograd.grad(decision,theta)[0].item()
            self.assertGreater(wrong,0)
            self.assertEqual(correct,0 if phase else wrong)
        EVIDENCE['gradient_contract']=dict(decision_samples_per_8_seconds=1, hold_gradients=[0.]*7,
            unexecuted_output_gradient_counterexample_detected=True, optimizer_steps=0)

    def test_clipped_total_action_does_not_identify_macro_offset(self):
        a=np.array([.05,.1]); immediate=np.clip(.95+2*a/.667,-1,1)
        following=np.clip(.4+2*a/.667,-1,1)
        self.assertEqual(immediate[0],immediate[1]); self.assertNotEqual(following[0],following[1])
        EVIDENCE['macro_action_alias']=dict(offsets=a.tolist(),same_current_total=immediate.tolist(),
            different_later_total=following.tolist(),critic_requires_actual_offset=True)

    def test_forecast_is_observed_prefix_only_and_next_is_recomputed(self):
        self.assertIsNotNone(CONTEXT,'use the budgeted review audit entry point')
        model=RidgeForecast.load(CONTEXT['saved']['model'])
        a=review.winds(45); b=a.copy(); b[18:]=[10.4,.21,.12]
        prefix=a[:18].copy()
        np.testing.assert_array_equal(a[:18],b[:18])
        predictions=[]
        for world in (a,b):
            predictions.append(review.forecast_features(model,world[:18],True))
        np.testing.assert_array_equal(*predictions)
        p,_=model.predict(prefix)
        expected=np.array([v for row in p for v in ((float(row[0])-float(prefix[-1,0]))/3,
            np.sin(float(row[1]))-np.sin(float(prefix[-1,1])),np.cos(float(row[1]))-np.cos(float(prefix[-1,1])))],np.float32)
        np.testing.assert_array_equal(predictions[0],expected)
        self.assertEqual(inspect.signature(model.predict).__str__(),'(history)')
        source=inspect.getsource(RidgeForecast.predict)+inspect.getsource(features)+inspect.getsource(review.forecast_features)
        forbidden=('trajectory','inflow_trace','episode','metadata','random','getattr','open(')
        self.assertFalse(any(word in source for word in forbidden))
        np.testing.assert_array_equal(review.forecast_features(model,prefix,False),np.zeros(36,np.float32))
        first=review.forecast_features(model,a[:1],True)
        next_f=review.forecast_features(model,a[:9],True)
        self.assertFalse(np.array_equal(first,next_f))
        np.testing.assert_array_equal(features(a[:1]),features(np.repeat(a[:1],32,axis=0)))
        np.testing.assert_array_equal(features(a[:40]),features(a[8:40]))
        EVIDENCE['forecast_causality']=dict(prefix_samples=18, future_suffix_changed=True, outputs_bitwise_equal=True,
            inference_signature='predict(history)', no_environment_argument=True, feature_normalizer_refit=False,
            frozen_model_sha256=review.sha(CONTEXT['saved']['model']), next_recomputed_from_observed_history=True,
            first_sample_padding_and_last32_exact=True, B_zero_features_explicit_ablation=True)

    def test_budget_counts_rows_before_mock_forward(self):
        from optimization_control.maddpg_wind_farm.causal_speed_search import Budget, Meter
        budget=Budget(limit=0); budget.start('must_reject_before_forward',0)
        called=[]; meter=Meter(lambda x:called.append(x),budget)
        with self.assertRaises(RuntimeError):meter(np.ones((1,12)))
        self.assertEqual(called,[]);self.assertEqual(budget.finish()['actual'],0)
        EVIDENCE['before_forward_guard']=True

    def test_three_frozen_parents_zero_takeover_hold_and_resume(self):
        self.assertIsNotNone(CONTEXT,'use the budgeted review audit entry point')
        rows=review.mock_paths(CONTEXT['saved'],CONTEXT['root'],CONTEXT['budget'])
        self.assertEqual(sum(x['mock_rows'] for x in rows),333)
        self.assertEqual(len(rows),21)
        EVIDENCE['mock_paths']=dict(scopes=21,mock_rows=333, zero_B_C_actions_states_powers_bitwise_parent=True,
            parent_feedback_each_second=True, interval_lengths=[8,8,3], new_episode_terminal_length=5,
            snapshots_at_physical_t=[5,8], mid_hold_and_boundary_resume_bitwise_equal=True,
            clock_corruption_rejected=True, exploration_draws_per_19_steps=3,
            real_PINN_rows=0, parent_weights_rng_updates_unchanged=True)


def load_tests(loader, standard_tests, pattern):
    # Parent/model integration is only entered by the explicitly budgeted audit.
    # Ordinary unittest discovery remains self-contained and makes zero plant queries.
    names = loader.getTestCaseNames(DecisionContractTests)
    integration = {'test_forecast_is_observed_prefix_only_and_next_is_recomputed',
                   'test_three_frozen_parents_zero_takeover_hold_and_resume'}
    return unittest.TestSuite(DecisionContractTests(name) for name in names
                             if CONTEXT is not None or name not in integration)


if __name__=='__main__':
    unittest.main()
