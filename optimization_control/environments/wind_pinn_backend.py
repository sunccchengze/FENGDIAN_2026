"""SI twelve-input bridge to the 2026-10-21 team model; no normalization twice."""
from __future__ import annotations

from pathlib import Path
import numpy as np

from .teammate_pinn_backend import OUTPUT_ORDER, validate_positions, read_json
from ..maddpg_wind_farm.fixed_pinn_demo import digest, load_team_module

SCHEMA = "pinn_wind_io_v1_si_flow_to"
INPUT_ORDER = ("ambient_wind_speed_m_s", "ambient_wind_direction_rad", "turbulence_intensity") + tuple(
    f"{name}{i}" for i in (1, 2, 3) for name in ("yaw", "pitch", "rotor_speed"))
ENCODED_ORDER = (INPUT_ORDER[0], "wind_direction_sin", "wind_direction_cos", INPUT_ORDER[2]) + INPUT_ORDER[3:]
TO_TEAM = (0, 1, 2, 3, 6, 9, 4, 7, 10, 5, 8, 11)
SI_UNITS = dict(yaw="rad", pitch="rad", rotor_speed="rad/s")


def wrap(angle):
    return (np.asarray(angle) + np.pi) % (2 * np.pi) - np.pi


def team_inputs(physical):
    x = np.asarray(physical, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 12 or not len(x) or not np.isfinite(x).all():
        raise ValueError("finite nonempty physical [B,12] default feature order required")
    raw = x[:, TO_TEAM].copy()
    raw[:, (1, 3, 6, 9)] = wrap(raw[:, (1, 3, 6, 9)])
    if np.any(raw[:, 0] <= 0) or np.any((raw[:, 2] < 0) | (raw[:, 2] > 1)) or np.any(raw[:, (5, 8, 11)] < 0):
        raise ValueError("invalid SI wind, TI or rotor speed")
    return raw


def validate_wind_run(run_dir, backend):
    root = Path(run_dir)
    if not all((root / name).is_file() for name in ("trained.keras", "training_report.json", "config_used.json")):
        raise ValueError("completed twelve-input model required; untrained.keras is not accepted")
    cfg, report = read_json(root / "config_used.json"), read_json(root / "training_report.json")
    if report.get("schema") != SCHEMA or cfg.get("schema") != SCHEMA:
        raise ValueError("twelve-input wind schema required")
    if report.get("status") != "trained_requires_independent_physical_validation" or report.get("epochs_completed", 0) <= 0:
        raise ValueError("completed training required")
    if report.get("config") != cfg or cfg.get("control_units") != SI_UNITS:
        raise ValueError("model configuration or SI units mismatch")
    if cfg.get("wind_direction_convention") != "flow_to_ccw_from_positive_x" or cfg.get("geometry_frame") != "fixed_source_origin_xy_at_zero_wind":
        raise ValueError("fixed-frame geometry and flow-to CCW wind required")
    if (report.get("physical_input_order") != list(INPUT_ORDER) or report.get("encoded_feature_order") != list(ENCODED_ORDER)
            or report.get("output_order") != list(OUTPUT_ORDER) or report.get("output_units") != ["W"] * 3 + ["m/s"] * 3):
        raise ValueError("wind input/output contract mismatch")
    if report.get("trainable_parameters") != 27106 or report.get("original_parameters_unchanged") is not True:
        raise ValueError("retained backbone and new parameter verification required")
    if report.get("constant_inputs_in_training") != [] or report.get("negative_test_output_count") != 0:
        raise ValueError("all twelve inputs must vary; negative test outputs rejected")
    if report.get("label_source") == "synthetic_test":
        if backend.get("allow_synthetic_demo") is not True or report.get("physical_validation") is not False:
            raise ValueError("synthetic_test requires explicit allow_synthetic_demo and no physical validation claim")
    elif report.get("label_source") in ("simulation", "experiment"):
        limits = np.asarray(backend.get("max_test_rmse"), dtype=float)
        if limits.shape != (6,) or not np.isfinite(limits).all() or np.any(limits <= 0):
            raise ValueError("six reviewed real-label error limits required")
        for j, name in enumerate(OUTPUT_ORDER):
            metric = report.get("test_metrics", {}).get(name, {})
            value = metric.get("RMSE", np.nan)
            if not np.isfinite(value) or not 0 <= value <= limits[j] or metric.get("unit") != ("W" if j < 3 else "m/s"):
                raise ValueError("unreviewed real-label error: " + name)
    else:
        raise ValueError("explicit label_source required")
    lo = np.asarray(report.get("training_input_min"), dtype=float)
    hi = np.asarray(report.get("training_input_max"), dtype=float)
    if lo.shape != (12,) or hi.shape != (12,) or not np.isfinite([lo, hi]).all() or np.any(lo >= hi):
        raise ValueError("twelve finite varying training ranges required")
    arc = report.get("training_direction_covering_arc", {})
    if not np.isfinite(arc.get("start_rad", np.nan)) or not 0 < arc.get("width_rad", 0) <= 2 * np.pi:
        raise ValueError("finite circular wind domain required")
    return cfg, report, validate_positions(cfg.get("turbine_positions_m")), lo, hi, arc


class WindConditionPredictor:
    expects_physical_default_inputs = True

    def __init__(self, model, positions, lo, hi, arc):
        self.model, self.positions = model, np.asarray(positions, dtype=np.float32)
        self.lo, self.hi, self.arc = np.asarray(lo), np.asarray(hi), dict(arc)
        self.spacing_m = float(self.positions[1, 0] - self.positions[0, 0])

    def __call__(self, physical):
        raw = team_inputs(physical)
        tolerance = 1e-6 * np.maximum(1, np.maximum(np.abs(self.lo), np.abs(self.hi)))
        outside = (raw < self.lo - tolerance) | (raw > self.hi + tolerance)
        center = self.arc["start_rad"] + self.arc["width_rad"] / 2
        outside[:, 1] = np.abs(wrap(raw[:, 1] - center)) > self.arc["width_rad"] / 2 + 1e-6
        if outside.any():
            raise ValueError("outside trained wind/control domain: " + ", ".join(n for j, n in enumerate(INPUT_ORDER) if outside[:, j].any()))
        inputs = dict(conditions_and_controls=raw.astype(np.float32),
                      turbine_positions=np.broadcast_to(self.positions, (len(raw), 3, 3)).copy())
        y = np.asarray(self.model(inputs, training=False), dtype=np.float32)
        if y.shape != (len(raw), 6) or not np.isfinite(y).all() or np.any(y[:, :3] < 0) or np.any(y[:, 3:] <= 0):
            raise ValueError("invalid physical six-output wind prediction")
        return y


def create_predictor(backend):
    run = Path(backend["run_dir"]).resolve()
    cfg, report, positions, lo, hi, arc = validate_wind_run(run, backend)
    script = Path(backend["script"]).resolve()
    expected_script = backend.get("script_sha256") or report.get("team_script_sha256")
    script_hash = digest(script)
    if not expected_script or any(value and script_hash != value for value in (expected_script, report.get("team_script_sha256"))):
        raise ValueError("team loading script differs from pinned provenance")
    expected_model = backend.get("model_sha256") or report.get("model_sha256")
    model_hash = digest(run / "trained.keras")
    if not expected_model or any(value and model_hash != value for value in (expected_model, report.get("model_sha256"))):
        raise ValueError("trained model differs from pinned provenance")
    team = load_team_module(script)
    tf, keras, *_ = team.tensorflow_components()
    model = keras.models.load_model(str(run / "trained.keras"), compile=False)
    if team.retained_digest(model) != report.get("retained_original_sha256") or team.trainable_count(model) != 27106:
        raise ValueError("loaded backbone or trainable parameter set mismatch")
    @tf.function(input_signature=[{"conditions_and_controls": tf.TensorSpec([None, 12], tf.float32),
                                  "turbine_positions": tf.TensorSpec([None, 3, 3], tf.float32)}])
    def inference(inputs):
        return model(inputs, training=False)
    predictor = WindConditionPredictor(lambda inputs, training: inference(inputs), positions, lo, hi, arc)
    predictor.model_sha256 = expected_model
    return predictor
