"""Synthetic provenance, independent splits and fixed-wind control contract."""
from copy import deepcopy
import unittest
import numpy as np
from optimization_control.maddpg_wind_farm.fixed_pinn_demo import read_config, DEFAULT, synthesize, physical_inputs
from optimization_control.environments.teammate_pinn_backend import validate_demo_run, validate_run
from optimization_control.tests import test_pinn_handover


class FixedDemoTests(unittest.TestCase):
    def test_synthetic_splits_reproducible_disjoint_and_endpoints_covered(self):
        cfg = read_config(DEFAULT)
        splits = {s: synthesize(cfg, s) for s in ("train", "validation", "test")}
        for s, (x, y) in splits.items():
            x2, y2 = synthesize(cfg, s)
            np.testing.assert_array_equal(x, x2)
            np.testing.assert_array_equal(y, y2)
            self.assertEqual(y.shape, (len(x), 6))
            self.assertTrue(np.all(y > 0))
        keys = {s: {tuple(r) for r in pair[0]} for s, pair in splits.items()}
        self.assertFalse(keys["train"] & keys["validation"])
        self.assertFalse(keys["train"] & keys["test"])
        x = physical_inputs(splits["train"][0], cfg["fixed_condition"])
        np.testing.assert_allclose(x[:, 3:6].min(0), cfg["controls"]["low"][0], atol=1e-7)
        np.testing.assert_allclose(x[:, 9:12].max(0), cfg["controls"]["high"][2], atol=1e-7)
        np.testing.assert_array_equal(x[:, :3], np.tile([9, 0, .1], (len(x), 1)).astype(np.float32))

    def test_physical_control_mapping(self):
        cfg = read_config(DEFAULT)
        x = physical_inputs([[10, 2, 6, 20, 3, 7, 30, 4, 8]], cfg["fixed_condition"])
        np.testing.assert_allclose(x[0, 3:6], np.deg2rad([10, 20, 30]), rtol=1e-6)
        np.testing.assert_allclose(x[0, 6:9], np.deg2rad([2, 3, 4]), rtol=1e-6)
        np.testing.assert_allclose(x[0, 9:12], np.array([6, 7, 8]) * np.pi / 30, rtol=1e-6)

    def test_demo_requires_explicit_provenance_and_cannot_pass_formal_gate(self):
        root, cfg, report, backend, save = test_pinn_handover.HandoverTests().run_fixture()
        report.update(status="synthetic_fixed_condition_demo", physical_validation=False,
            label_source="coupled_integration_mock", fixed_condition=dict(speed_m_s=9, direction_rad=1.5*np.pi, turbulence_intensity=.08))
        save()
        with self.assertRaisesRegex(ValueError, "allow_synthetic_demo"):
            validate_demo_run(root, backend)
        backend["allow_synthetic_demo"] = True
        validate_demo_run(root, backend)
        with self.assertRaises(ValueError):
            validate_run(root, backend)
        bad = deepcopy(backend); bad["fixed_condition"]["direction_rad"] = 0
        with self.assertRaisesRegex(ValueError, "differs"):
            validate_demo_run(root, bad)
        report["physical_validation"] = True; save()
        with self.assertRaisesRegex(ValueError, "provenance"):
            validate_demo_run(root, backend)


if __name__ == "__main__":
    unittest.main()
