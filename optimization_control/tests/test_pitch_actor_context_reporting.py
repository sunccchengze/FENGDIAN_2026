"""Adversarial reporting fixtures: averages cannot hide a stream/family or motion failure."""
from copy import deepcopy
import unittest
from optimization_control.maddpg_wind_farm.pitch_actor_context_review import gates


def fixture():
    cases=[('train_episode_8_initial_0.025','stationary'),('train_episode_8_initial_0.055','stationary'),
           ('other_stationary','stationary'),('other_ramp','ramp'),('other_gust','gust')]
    rows=[]
    for arm in ('replay','current_pitch'):
        for run in range(3):
            for role in ('initial','selected','final'):
                for case,family in cases:
                    rmse=110000. if role=='initial' else 100000. if arm=='replay' else 90000.
                    rows.append(dict(arm=arm,run=run,role=role,case_id=case,family=family,split='train',rmse_w=rmse,
                                     pitch_travel_rad=1.,pitch_rms_rate_rad_s=.001,pitch_min_rad=.01,pitch_max_rad=.1,pitch_max_rate_rad_s=.005))
    for case,family in cases:
        rows.append(dict(arm='pi',run=-1,role='pi',case_id=case,family=family,split='train',rmse_w=95000.,
                         pitch_travel_rad=1.,pitch_rms_rate_rad_s=.001,pitch_min_rad=.01,pitch_max_rad=.1,pitch_max_rate_rad_s=.005))
    return rows


class ReportingContracts(unittest.TestCase):
    def test_one_family_stream_regression_cannot_hide_under_average_gain(self):
        rows=fixture();self.assertTrue(gates(rows,True)['retention_pass'])
        for r in rows:
            if (r['arm'],r['run'],r['role'],r['case_id'])==('current_pitch',2,'final','other_gust'):r['rmse_w']=130000.
        selected=[r['rmse_w'] for r in rows if r['arm']=='current_pitch' and r['role']=='final']
        self.assertLess(sum(selected)/len(selected),100000.)
        result=gates(rows,True)
        self.assertFalse(result['retention_pass'])
        self.assertTrue(any(not x['passed'] and x['run']==2 and x['family']=='gust' for x in result['retention']))

    def test_motion_and_hard_limit_are_separate_checks(self):
        rows=fixture();self.assertTrue(gates(rows)['physical_pass'])
        for r in rows:
            if r['arm']=='current_pitch' and r['run']==0 and r['role']=='selected' and r['family']=='ramp':r['pitch_travel_rad']=1.11
        result=gates(rows)
        self.assertTrue(result['physical_pass']);self.assertFalse(result['motion_pass'])


if __name__=='__main__':unittest.main()
