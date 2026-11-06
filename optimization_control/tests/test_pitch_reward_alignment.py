"""Full-episode attribution is ordered, signed, and rejects partial windows."""
import unittest
import numpy as np
from optimization_control.maddpg_wind_farm.pitch_reward_alignment import summarize
from optimization_control.maddpg_wind_farm.pitch_reward_alignment_review import classify, preferences, pair_summary


class RewardAlignmentTests(unittest.TestCase):
    def test_full_horizon_formula_and_timing_weight(self):
        error=np.r_[np.full(64,1e6),np.full(64,2e6)]
        pitch=np.full((128,3),.04)
        m=summarize(error,np.zeros(128),pitch,pitch,pitch,np.zeros(128))
        self.assertAlmostEqual(m['mse_w2'],2.5e12)
        self.assertAlmostEqual(m['mean_error_w']**2+m['error_std_w']**2,m['mse_w2'])
        self.assertAlmostEqual(m['return_discounted'],-100*sum(.99**i*(error[i]/15e6)**2 for i in range(128)))
        with self.assertRaises(ValueError):
            summarize(error[:32],np.zeros(32),pitch[:32],pitch[:32],pitch[:32],np.zeros(32))

    def test_attribution_keeps_repairs_and_non_action_conflicts(self):
        better=dict(trajectory_id='t0',rmse_w=10000.,tracking_uniform=-1.,tracking_discounted=-1.,
                    return_discounted=-3.,action_discounted=-2.,pitch_travel_rad=.1,pitch_rms_rate_rad_s=.001,command_cost_sum=.1)
        worse=dict(trajectory_id='t1',rmse_w=20000.,tracking_uniform=-2.,tracking_discounted=-2.,
                   return_discounted=-2.,action_discounted=0.,pitch_travel_rad=.2,pitch_rms_rate_rad_s=.002,command_cost_sum=.2)
        self.assertEqual(classify(worse,better)['attribution'],'action_created')
        better.update(tracking_discounted=-3.,return_discounted=-3.,action_discounted=0.)
        worse.update(tracking_discounted=-2.,return_discounted=-4.,action_discounted=-2.)
        self.assertEqual(classify(better,worse)['attribution'],'action_repaired')
        better.update(return_discounted=-5.,action_discounted=-2.)
        self.assertEqual(classify(better,worse)['attribution'],'discount_survives')
        better['rmse_w']=19950.
        self.assertEqual(classify(better,worse)['attribution'],'rmse_tie')

    def test_preference_loss_never_confuses_max_reward_with_min_cost(self):
        common=dict(source='s',run='0',case_id='x',split='train',family='ramp',target_w='3e6',initial_pitch_rad='.04',
                    pitch_travel_rad=.1,pitch_rms_rate_rad_s=.001)
        a=dict(common,trajectory_id='t00000',rmse_w=1e4,tracking_uniform=-1.,tracking_discounted=-2.)
        b=dict(common,trajectory_id='t00001',rmse_w=2e4,tracking_uniform=-2.,tracking_discounted=-1.)
        p=preferences([a,b])
        self.assertEqual(p[0]['regret_w'],0.)
        self.assertEqual(p[1]['regret_w'],1e4)

    def test_duplicate_only_case_stays_in_coverage_denominator(self):
        trajectories=[dict(run='0',case_id='same')]
        s=pair_summary([],dict(source='s'),trajectories)
        self.assertEqual(s['case_slots'],1)
        self.assertEqual(s['compared_case_slots'],0)
        self.assertEqual(s['all_pairs'],0)


if __name__=='__main__':
    unittest.main()
