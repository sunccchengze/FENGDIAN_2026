"""New SI contract, circular wind domain, source admission and split isolation."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
import numpy as np

from optimization_control.environments.wind_pinn_backend import (
    INPUT_ORDER, ENCODED_ORDER, OUTPUT_ORDER, SCHEMA, SI_UNITS,
    WindConditionPredictor, team_inputs, validate_wind_run, create_predictor)
from optimization_control.maddpg_wind_farm.fixed_pinn_demo import resolve_team_path, digest
from optimization_control.maddpg_wind_farm.handoff_replay import resolve_recorded
from optimization_control.maddpg_wind_farm.wind_pinn_demo import read_config, DEFAULT, synthesize, synthetic_labels, verify_rollouts
from optimization_control.maddpg_wind_farm.wind_pinn_curriculum import read_protocol, DEFAULT as CURRICULUM


class WindPINNTests(unittest.TestCase):
    def predictor(self):
        cfg = read_config(DEFAULT)
        lo = np.r_[cfg["domain"]["wind_low"], cfg["domain"]["control_low"] * 3]
        hi = np.r_[cfg["domain"]["wind_high"], cfg["domain"]["control_high"] * 3]
        captured = {}
        def model(inputs, training):
            captured.update(inputs)
            self.assertFalse(training)
            return np.tile([1e6, 1e6, 1e6, 9, 8, 7], (len(inputs["conditions_and_controls"]), 1))
        predictor = WindConditionPredictor(model, cfg["geometry"]["positions_m"], lo, hi,
                                          dict(start_rad=2 * np.pi - .15, width_rad=.3))
        return captured, predictor

    def base(self):
        return np.array([[9, 0, .1, .1, .2, .3, .01, .02, .03, .7, .8, .9]])

    def test_interleave_si_geometry_not_rotated_twice(self):
        captured, p = self.predictor()
        x = np.repeat(self.base(), 2, axis=0); x[:, 1] = .1
        p(x)
        np.testing.assert_allclose(captured["conditions_and_controls"][0], [9, .1, .1, .1, .01, .7, .2, .02, .8, .3, .03, .9], rtol=1e-6)
        np.testing.assert_array_equal(captured["turbine_positions"][0], [[0, 0, 90], [378, 0, 90], [756, 0, 90]])

    def test_periodic_aliases_and_circular_seam(self):
        _, p = self.predictor()
        values = []
        for theta in (-.1, 2 * np.pi - .1, 4 * np.pi - .1):
            x = self.base(); x[0, 1] = theta
            values.append(team_inputs(x))
            p(x)
        np.testing.assert_allclose(values[0], values[1], atol=1e-12)
        np.testing.assert_allclose(values[0], values[2], atol=1e-12)
        x = self.base(); x[0, 1] = .16
        with self.assertRaisesRegex(ValueError, "domain"):
            p(x)

    def test_bad_inputs_outputs_rejected_without_clipping(self):
        _, p = self.predictor()
        for column, value in ((0, 7), (2, .2), (3, .5), (6, .3), (9, 2), (1, np.nan)):
            x = self.base(); x[0, column] = value
            with self.assertRaises(ValueError):
                p(x)
        for output in ([1, 1, 1, -1, 8, 7], [-1, 1, 1, 9, 8, 7], [1, 1, 1, 0, 8, 7]):
            p.model = lambda inputs, training: np.array([output])
            with self.assertRaisesRegex(ValueError, "six-output"):
                p(self.base())

    def test_synthetic_splits_and_training_envelope(self):
        cfg = read_config(DEFAULT)
        pairs = {s: synthesize(cfg, s) for s in ("train", "validation", "test")}
        keys = {}
        for s, (x, y) in pairs.items():
            x2, y2 = synthesize(cfg, s)
            np.testing.assert_array_equal(x, x2); np.testing.assert_array_equal(y, y2)
            self.assertTrue(np.all(y > 0))
            keys[s] = {tuple(row) for row in x}
        for a, b in (("train", "validation"), ("train", "test"), ("validation", "test")):
            self.assertFalse(keys[a] & keys[b])
        np.testing.assert_allclose(pairs["train"][0].min(0), cfg["domain"]["wind_low"] + cfg["domain"]["control_low"] * 3, atol=1e-6)
        self.assertEqual(pairs["train"][0].shape[1], 12)

    def test_teacher_uses_wind_direction_ti_controls_and_layout(self):
        cfg = read_config(DEFAULT)
        base = np.array([[9, 0, .1] + [0] * 3 + [.04] * 3 + [.9] * 3], dtype=float)
        y0 = synthetic_labels(base, cfg["geometry"]["positions_m"])
        for j, v in enumerate((9.5, .1, .14, .2, .2, .2, .1, .1, .1, 1.2, 1.2, 1.2)):
            x = base.copy(); x[0, j] = v
            self.assertGreater(np.max(np.abs(synthetic_labels(x, cfg["geometry"]["positions_m"]) - y0)), .001)
        pos = deepcopy(cfg["geometry"]["positions_m"]); pos[1][1] = 500
        self.assertGreater(np.max(np.abs(synthetic_labels(base, pos) - y0)), .001)
        p = base.copy(); p[:, 6:9] = .2
        self.assertTrue(np.all(synthetic_labels(p, cfg["geometry"]["positions_m"])[:, :3] < y0[:, :3]))

    def fixture(self):
        root = Path("tmp") / ("wind_pinn_test_" + uuid4().hex); root.mkdir(parents=True)
        cfg = dict(schema=SCHEMA, control_units=SI_UNITS, wind_direction_convention="flow_to_ccw_from_positive_x",
                   geometry_frame="fixed_source_origin_xy_at_zero_wind", turbine_positions_m=[[0, 0, 90], [378, 0, 90], [756, 0, 90]])
        config = read_config(DEFAULT)
        report = dict(schema=SCHEMA, status="trained_requires_independent_physical_validation", epochs_completed=2,
            config=cfg, physical_input_order=list(INPUT_ORDER), encoded_feature_order=list(ENCODED_ORDER),
            output_order=list(OUTPUT_ORDER), output_units=["W"] * 3 + ["m/s"] * 3,
            trainable_parameters=27106, original_parameters_unchanged=True, constant_inputs_in_training=[],
            label_source="synthetic_test", physical_validation=False, negative_test_output_count=0,
            training_input_min=config["domain"]["wind_low"] + config["domain"]["control_low"] * 3,
            training_input_max=config["domain"]["wind_high"] + config["domain"]["control_high"] * 3,
            training_direction_covering_arc=dict(start_rad=2 * np.pi - .15, width_rad=.3))
        def save():
            for name, value in (("config_used.json", cfg), ("training_report.json", report)):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
        (root / "trained.keras").write_bytes(b"fixture not model"); save()
        return root, cfg, report, save

    def test_training_provenance_and_contract_enforced(self):
        root, cfg, report, save = self.fixture()
        with self.assertRaisesRegex(ValueError, "allow_synthetic_demo"):
            validate_wind_run(root, {})
        backend = dict(allow_synthetic_demo=True)
        validate_wind_run(root, backend)
        for key, value in (("physical_validation", True), ("constant_inputs_in_training", ["turbulence_intensity"]),
                           ("trainable_parameters", 24306), ("status", "structure_checked_NOT_trained")):
            old = report[key]; report[key] = value; save()
            with self.assertRaises(ValueError):
                validate_wind_run(root, backend)
            report[key] = old
        cfg["control_units"] = dict(yaw="deg", pitch="deg", rotor_speed="rpm"); save()
        with self.assertRaisesRegex(ValueError, "units"):
            validate_wind_run(root, backend)

    def test_old_move_resolution_and_traversal_guard(self):
        root = Path("tmp") / ("wind_move_test_" + uuid4().hex)
        moved = root / "pinn/2026_1007/PINNs_multi_turbine_wake_simulation-outputchange"
        moved.mkdir(parents=True)
        script = moved / "modify_pinn_io.py"; script.write_text("# fixture", encoding="utf-8")
        old = root / "pinn/PINNs_multi_turbine_wake_simulation-outputchange/modify_pinn_io.py"
        self.assertEqual(resolve_team_path(old), script)
        self.assertEqual(resolve_recorded(root.resolve(), "pinn/PINNs_multi_turbine_wake_simulation-outputchange/modify_pinn_io.py"), script.resolve())
        with self.assertRaises(ValueError):
            resolve_recorded(root.resolve(), "../outside")

    def test_bounded_protocol_has_disjoint_targets_and_one_factor_stages(self):
        p = read_protocol(CURRICULUM)
        self.assertEqual(p["single_steps"], 16384)
        self.assertEqual(p["seed"], 42)
        from optimization_control.maddpg_wind_farm.fixed_curriculum import STAGES
        self.assertEqual([mask for _, mask in STAGES], [[0, 1, 0], [0, 1, 0], [0, 1, 1], [1, 1, 1]])

    def test_model_pin_conflict_rejected_before_tensorflow_loading(self):
        root, cfg, report, save = self.fixture()
        script = root / "layers.py"; script.write_text("# fixture", encoding="utf-8")
        report.update(team_script_sha256=digest(script), model_sha256="wrong")
        save()
        with self.assertRaisesRegex(ValueError, "model differs"):
            create_predictor(dict(run_dir=str(root), script=str(script), allow_synthetic_demo=True,
                                  model_sha256=digest(root / "trained.keras")))

    def test_replay_cannot_override_control_parameters(self):
        from optimization_control.maddpg_wind_farm.workflow import evaluate, load_config, DEFAULT_CONFIG
        cfg = load_config(DEFAULT_CONFIG); cfg["plant"]["kind"] = "pinn"
        with patch("optimization_control.maddpg_wind_farm.workflow.MADDPG.load", return_value=(None, dict(config=cfg))):
            with self.assertRaisesRegex(ValueError, "only PINN"):
                evaluate("fixture", "unused", backend_paths=dict(action_low=[0, 0, 0]))

    def test_rollout_audit_checks_first_heading_step_not_gamma_rate(self):
        from optimization_control.maddpg_wind_farm.workflow import load_config, DEFAULT_CONFIG
        cfg = load_config(DEFAULT_CONFIG)
        traces = []
        for mode in ("maddpg", "fixed", "p", "pi"):
            row = dict(scenario="test", controller=mode, wind_m_s=9., direction_rad=.02, ti=.1, farm_power_w=3e6)
            for i in (1, 2, 3):
                row.update({f"power_{i}_w": 1e6, f"heading_{i}_rad": 0., f"yaw_rad_{i}": -.02,
                            f"pitch_rad_{i}": .04, f"speed_rad_s_{i}": .9})
            traces.append(row)
        verify_rollouts(cfg, traces, dict(test=0.))
        for row in traces:
            row["heading_1_rad"] = .006
            row["yaw_rad_1"] = -.014
        with self.assertRaisesRegex(RuntimeError, "rate exceeded"):
            verify_rollouts(cfg, traces, dict(test=0.))


if __name__ == "__main__":
    unittest.main()
