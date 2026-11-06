"""Synthetic reporting checks: a bad stream/family or motion must not hide in an average."""
from copy import deepcopy
import json
from pathlib import Path
import time
import unittest
import yaml

from optimization_control.maddpg_wind_farm.pitch_gamma_review import acceptance,aggregates


class GammaReportingTests(unittest.TestCase):
    def rows(self):
        rows=[]
        for arm in ('g099','g100','p','pi'):
            for run in (range(3) if arm.startswith('g') else [-1]):
                for role in (('initial','selected','final') if arm.startswith('g') else [arm]):
                    for family in ('stationary','ramp','gust'):
                        rmse=9000. if arm=='g100' and role!='initial' and family=='ramp' else 10000.
                        rows.append(dict(arm=arm,run=run,role=role,case_id=family,family=family,split='validation',target_w=3e6,initial_pitch_rad=.04,
                             rmse_w=rmse,mse_w2=rmse**2,mean_error_w=0.,error_std_w=rmse,pitch_travel_rad=.1,
                             pitch_rms_rate_rad_s=.001,pitch_max_rate_rad_s=.005,pitch_min_rad=0.,pitch_max_rad=.2,
                             pitch_rate_fraction=0.,pitch_boundary_fraction=0.))
        return rows

    def probe(self,rows,initial=False):
        root=Path(__file__).resolve().parents[1]/'experiments/20261029_pitch_gamma_control/reporting_probes'/str(time.time_ns())
        root.mkdir(parents=True,exist_ok=False)
        cfg=yaml.safe_load((root.parents[1]/'config.yaml').read_text(encoding='utf-8'))
        (root/'config.yaml').write_text(yaml.safe_dump(dict(protected_hashes={},gates=cfg['gates'])),encoding='utf-8')
        (root/'selection.json').write_text(json.dumps(dict(results=[dict(arm='g100',selected_step=0 if initial and r==2 else 4096) for r in range(3)])),encoding='utf-8')
        return acceptance(root,'validation',rows)

    def test_local_regression_and_motion_override_good_overall_average(self):
        good=self.rows();self.assertTrue(self.probe(good)['passed'])
        bad=deepcopy(good)
        for r in bad:
            if r['arm']=='g100' and r['run']==2 and r['role']=='final' and r['family']=='gust':
                r.update(rmse_w=12000.,mse_w2=12000.**2,error_std_w=12000.)
        v=self.probe(bad);self.assertFalse(v['other_capability_preserved']);self.assertFalse(v['passed'])
        moving=deepcopy(good)
        for r in moving:
            if r['arm']=='g100' and r['run']==1 and r['role']=='final' and r['family']=='ramp':r['pitch_travel_rad']=.111
        v=self.probe(moving);self.assertFalse(v['actual_motion_pass']);self.assertFalse(v['passed'])
        v=self.probe(good,initial=True);self.assertEqual(v['new_learning_runs'],2);self.assertFalse(v['passed'])

    def test_pooled_metric_is_not_case_mean_or_repeated_baseline(self):
        rows=[r for r in self.rows() if r['arm']=='pi']
        for r,error in zip(rows,(5000.,10000.,15000.)):r.update(rmse_w=error,mse_w2=error**2,error_std_w=error)
        a=next(r for r in aggregates(rows) if r['family']=='routine')
        self.assertEqual(a['cases'],3);self.assertEqual(a['run'],-1)
        self.assertEqual(a['mean_rmse_w'],10000.)
        self.assertGreater(a['pooled_rmse_w'],a['mean_rmse_w'])


if __name__=='__main__':unittest.main()
