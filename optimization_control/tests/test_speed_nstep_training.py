"""New workflow contracts; algorithm equivalence is covered by existing tests."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from optimization_control.maddpg_wind_farm.speed_nstep_training import protocol,design,radius,learning_gate,ARMS


class SpeedNStepTrainingTests(unittest.TestCase):
    def test_design_complete_blocks_and_paired_streams(self):
        p=dict(protocol(),training_targets_w=[2600000.,3200000.,3800000.],training_initial_pitch_rad=[.025,.055])
        for run in range(3):
            for block in range(7):
                rows=[design(p,run,block*9+j) for j in range(9)]
                self.assertEqual(len(set((f,t) for f,t,_ in rows)),9)
                self.assertTrue(all(.025<=pitch<=.055 for _,_,pitch in rows))
                self.assertEqual(rows,[design(deepcopy(p),run,block*9+j) for j in range(9)])
        self.assertNotEqual(design(p,0,0),design(p,1,0))

    def test_radius_and_inclusive_update_budget(self):
        self.assertEqual(radius(0),.02)
        self.assertEqual(radius(4096),.1)
        self.assertEqual(radius(8191),.1)
        self.assertLess(radius(511),radius(512))
        self.assertEqual(len([k for k in range(1,8193) if k>=512 and k%2==0]),3841)
        self.assertEqual(ARMS,{'n1':1,'n8':8})

    def test_missing_takeover_cannot_start_learning(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):learning_gate(Path(folder),{})


if __name__=='__main__':unittest.main()
