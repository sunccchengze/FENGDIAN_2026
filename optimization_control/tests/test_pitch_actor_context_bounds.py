"""In-memory boundary probes; no files, actual plant calls or optimizer updates."""
from unittest.mock import Mock,patch
import unittest
from optimization_control.maddpg_wind_farm import pitch_actor_context_trial as trial


class HardBounds(unittest.TestCase):
    def test_storage_limits_reject_before_writing(self):
        with patch.object(trial,'size',return_value=trial.LIMIT-10):
            self.assertEqual(trial.space('unused',10),trial.LIMIT-10)
            with self.assertRaises(RuntimeError):trial.space('unused',11)
        handle=Mock();handle.tell.return_value=22*1024**2-1
        with patch.object(trial,'space',return_value=0),patch('builtins.open',return_value=handle):
            f=trial.LimitedFile('unused','never_created_storage_boundary_probe')
            with self.assertRaises(RuntimeError):f.write(b'xx')
            handle.write.assert_not_called();f.close()

    def test_model_row_caps_reject_before_predictor_call(self):
        meter=trial.Meter.__new__(trial.Meter);meter.counts={'T':99087,'E':0};meter.active='T';meter.f=Mock()
        predictor=Mock(return_value='one_mock_row');counted=meter.wrap(predictor)
        self.assertEqual(counted([None]),'one_mock_row')
        self.assertEqual(meter.counts['T'],99088)
        with self.assertRaises(RuntimeError):counted([None])
        predictor.assert_called_once();meter.f.write.assert_called_once_with(b'T')
        meter.counts={'T':99088,'E':282000};meter.active='E'
        with self.assertRaises(RuntimeError):counted([None])
        self.assertEqual(predictor.call_count,1)
        meter.active=None
        with self.assertRaises(AssertionError):counted([None])


if __name__=='__main__':unittest.main()
