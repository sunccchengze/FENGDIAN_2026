"""Storage and recovery contracts without environment steps or optimizer calls."""
import unittest
from optimization_control.maddpg_wind_farm.pitch_actor_context_algorithm import full_checkpoint,recovery_plan


class StorageContracts(unittest.TestCase):
    def test_schedule_has_104_formal_states_and_valid_selection_points(self):
        jobs=[(a,r) for a in range(2) for r in range(3)]
        points={job:[s for s in range(0,16385,128) if full_checkpoint(s,job[1])] for job in jobs}
        self.assertEqual(sum(map(len,points.values())),104)
        for (a,r),steps in points.items():
            self.assertTrue(set(range(0,16385,4096))<=set(steps))
            self.assertEqual(128 in steps,r==0)
            self.assertNotIn(256,steps)

    def test_recovery_retains_unrecoverable_light_tail_for_recompute_accounting(self):
        commits=[dict(step=1024,attempt=0,checkpoint='full'),dict(step=1152,attempt=0,checkpoint=None),
                 dict(step=1280,attempt=0,checkpoint=None)]
        full,repeats=recovery_plan(commits)
        self.assertEqual(full['step'],1024)
        self.assertEqual([x['step'] for x in repeats],[1152,1280])
        self.assertEqual(sum(128 for x in repeats),256)
        self.assertEqual(len(commits),3)


if __name__=='__main__':unittest.main()
