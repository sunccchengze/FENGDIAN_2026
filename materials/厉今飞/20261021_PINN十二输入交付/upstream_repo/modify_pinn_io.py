"""Modify the author's pretrained PINN; keep its existing hidden weights frozen.

Windows, in the same project root as prepare_pinn_outputchange.py:
    python modify_pinn_io.py
    python modify_pinn_io.py train --csv cases.csv

The first command builds and checks the structure, without fitting real data.
The nine new input connections and six new linear readouts are trainable.
The original coordinate scaling, shared layers and ALL six branches are reused.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

import numpy as np

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

ROOT = Path(__file__).resolve().parent
SOURCE_HEADS = ("output_u", "output_v", "output_w", "output_p", "output_k", "output_eps")
CONTROL_NAMES = tuple(name for i in range(1, 4)
                      for name in (f"yaw{i}", f"pitch{i}", f"rotor_speed{i}"))
OUTPUT_NAMES = ("P1", "P2", "P3", "Ueff1", "Ueff2", "Ueff3")
EXPECTED_TRAINABLE = 9 * 700 + 6 * (3000 + 1)  # 24,306; shared input kernel.


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def unique_directory(path):
    path = Path(path)
    candidate = path
    index = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}_{index}")
        index += 1
    candidate.mkdir(parents=True)
    return candidate


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")


@lru_cache(maxsize=1)
def tensorflow_components():
    """Keep --help and the data utilities usable without loading TensorFlow."""
    import tensorflow as tf
    import tf_keras as keras

    if tf.__version__.split(".")[:2] != ["2", "16"]:
        raise RuntimeError(f"Expected TensorFlow 2.16.x; found {tf.__version__}.")
    if keras.__version__.split(".")[:2] != ["2", "16"]:
        raise RuntimeError(f"Expected tf_keras 2.16.x; found {keras.__version__}.")
    tf.config.threading.set_intra_op_parallelism_threads(4)
    tf.config.threading.set_inter_op_parallelism_threads(2)

    @keras.utils.register_keras_serializable(package="PinnOutputChange")
    class ExtendedInputDense(keras.layers.Layer):
        """The SAME first hidden layer, with nine extra kernel rows.

        The original 3x700 kernel and 700 biases are separate frozen variables.
        Only the extra 9x700 kernel is trainable. No extra hidden layer is added.
        """

        def __init__(self, units=700, activation="swish", regularization=1e-4, **kwargs):
            super().__init__(**kwargs)
            self.units = int(units)
            self.activation = keras.activations.get(activation)
            self.regularization = float(regularization)

        def build(self, input_shape):
            if int(input_shape[0][-1]) != 3 or int(input_shape[1][-1]) != 9:
                raise ValueError("Expected three scaled coordinates and nine controls.")
            self.original_kernel = self.add_weight(
                name="original_coordinate_kernel", shape=(3, self.units),
                initializer="zeros", trainable=False)
            self.original_bias = self.add_weight(
                name="original_bias", shape=(self.units,),
                initializer="zeros", trainable=False)
            self.control_kernel = self.add_weight(
                name="new_control_kernel", shape=(9, self.units),
                initializer="zeros", trainable=True,
                regularizer=keras.regularizers.L2(self.regularization))
            super().build(input_shape)

        def call(self, inputs):
            coordinates, controls = inputs
            linear = (tf.linalg.matmul(coordinates, self.original_kernel)
                      + tf.linalg.matmul(controls, self.control_kernel))
            return self.activation(tf.nn.bias_add(linear, self.original_bias))

        def get_config(self):
            return {**super().get_config(), "units": self.units,
                    "activation": keras.activations.serialize(self.activation),
                    "regularization": self.regularization}

    @keras.utils.register_keras_serializable(package="PinnOutputChange")
    class FrozenStandardization(keras.layers.Layer):
        """Statistics are set from the TRAINING split; never optimized."""

        def __init__(self, width, inverse=False, **kwargs):
            kwargs["trainable"] = False
            super().__init__(**kwargs)
            self.width = int(width)
            self.inverse = bool(inverse)

        def build(self, input_shape):
            self.mean = self.add_weight(name="mean", shape=(self.width,),
                                        initializer="zeros", trainable=False)
            self.std = self.add_weight(name="std", shape=(self.width,),
                                       initializer="ones", trainable=False)
            super().build(input_shape)

        def call(self, inputs):
            if self.inverse:
                return inputs * self.std + self.mean
            return (inputs - self.mean) / self.std

        def get_config(self):
            return {**super().get_config(), "width": self.width, "inverse": self.inverse}

    @keras.utils.register_keras_serializable(package="PinnOutputChange")
    class TurbineCoordinates(keras.layers.Layer):
        def __init__(self, index, **kwargs):
            super().__init__(**kwargs)
            self.index = int(index)

        def call(self, inputs):
            return [inputs[:, self.index, j:j + 1] for j in range(3)]

        def get_config(self):
            return {**super().get_config(), "index": self.index}

    return tf, keras, ExtendedInputDense, FrozenStandardization, TurbineCoordinates


def trainable_count(model):
    return sum(int(np.prod(weight.shape.as_list())) for weight in model.trainable_weights)


def digest_arrays(named_arrays):
    digest = hashlib.sha256()
    for name, array in named_arrays:
        array = np.asarray(array)
        digest.update(name.encode("utf-8"))
        digest.update(str(array.shape).encode("ascii"))
        digest.update(array.tobytes())
    return digest.hexdigest()


def source_digest(model):
    return digest_arrays((weight.name, weight.numpy())
                         for weight in sorted(model.weights, key=lambda value: value.name))


def retained_digest(model):
    first = model.get_layer("extended_original_first_dense")
    entries = [("first_kernel", first.original_kernel.numpy()),
               ("first_bias", first.original_bias.numpy())]
    tail = model.get_layer("original_hidden_layers")
    for layer in sorted(tail.layers, key=lambda value: value.name):
        for index, weight in enumerate(layer.weights):
            entries.append((f"{layer.name}/{index}", weight.numpy()))
    return digest_arrays(entries)


def ensure_config(root):
    path = root / "OutputChange" / "project_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_json(path, {
            "turbine_positions_m": [[None, None, None] for _ in range(3)],
            "control_units": {"yaw": "deg", "pitch": "deg", "rotor_speed": "rpm"},
            "fixed_inlet_wind_speed_m_s": 9.0,
            "notes": [
                "将三个位置依次改为机组1、2、3的 [x,y,z]，单位m；z为轮毂高度。",
                "坐标系应与原模型一致：x沿来流方向，y横向，z竖直。",
                "角度可用deg或rad，转速可用rpm或rad/s；修改单位后CSV和预测输入必须一致。",
                "本版只有九个控制输入；训练数据的入口风速、风向、湍流强度须固定。",
                "9m/s是所选源模型的预训练风速，迁移到其他固定工况仍需验证。",
                "原模型预训练布置为四台风机，迁移到三台的准确性须由实际数据检验。",
                "结构检查使用的测试坐标不代表你们的实际布置。",
                "Ueff必须使用优化侧约定的转子盘有效风速定义，不能直接拿中心点风速替代标签。"
            ]
        })
    return path


def validate_config(path):
    config = read_json(path)
    try:
        positions = np.asarray(config["turbine_positions_m"], dtype=np.float32)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("配置中需填写三台机组各自的 [x,y,z]，单位m。") from exc
    if positions.shape != (3, 3) or not np.isfinite(positions).all():
        raise ValueError("请先填写 project_config.json 的 turbine_positions_m；不能保留null。")
    if (positions[:, 2] <= 0).any() or len(np.unique(positions, axis=0)) != 3:
        raise ValueError("三台风机位置需不同，轮毂高度需大于0。")
    units = config.get("control_units", {})
    if (units.get("yaw") not in ("deg", "rad")
            or units.get("pitch") not in ("deg", "rad")
            or units.get("rotor_speed") not in ("rpm", "rad/s")):
        raise ValueError("control_units: yaw/pitch可用deg或rad；rotor_speed可用rpm或rad/s。")
    wind = config.get("fixed_inlet_wind_speed_m_s")
    if not isinstance(wind, (float, int)) or not np.isfinite(wind) or wind <= 0:
        raise ValueError("配置需注明固定入口风速 fixed_inlet_wind_speed_m_s。")
    return config, positions


def inputs_for(controls, positions):
    controls = np.asarray(controls, dtype=np.float32)
    if controls.ndim != 2 or controls.shape[1] != 9:
        raise ValueError("Controls must have shape [number_of_cases, 9].")
    positions = np.asarray(positions, dtype=np.float32)
    if positions.shape == (3, 3):
        positions = np.broadcast_to(positions, (len(controls), 3, 3)).copy()
    if positions.shape != (len(controls), 3, 3):
        raise ValueError("Coordinates must have shape [number_of_cases, 3, 3].")
    return {"controls": controls, "turbine_positions": positions}


def build_modified(original, keras, ExtendedInputDense, FrozenStandardization, TurbineCoordinates):
    if int(original.count_params()) != 3_090_200 or len(original.inputs) != 3:
        raise ValueError("源模型与已核对的3,090,200参数模型不一致。")
    if set(original.output_names) != set(SOURCE_HEADS):
        raise ValueError(f"Unexpected original outputs: {original.output_names}")
    original.trainable = False
    first_candidates = [layer for layer in original.layers
                        if isinstance(layer, keras.layers.Dense)
                        and tuple(layer.kernel.shape.as_list()) == (3, 700)]
    if len(first_candidates) != 1:
        raise ValueError("Could not identify the original first 3-to-700 Dense layer.")
    first = first_candidates[0]
    if not first.use_bias:
        raise ValueError("Unexpected bias configuration in the first hidden layer.")
    features = [original.get_layer(name).input for name in SOURCE_HEADS]
    if any(int(tensor.shape[-1]) != 500 for tensor in features):
        raise ValueError("Expected six original 500-unit feature branches.")

    # These are graph views of the already loaded original layers, not new MLPs.
    prefix = keras.Model(original.inputs, first.input, name="original_coordinate_scaling")
    prefix.trainable = False
    tail = keras.Model(first.output, features, name="original_hidden_layers")
    tail.trainable = False
    if int(tail.count_params()) != 3_084_400:
        raise ValueError("Unexpected number of retained middle/branch parameters.")

    controls = keras.Input(shape=(9,), name="controls")
    positions = keras.Input(shape=(3, 3), name="turbine_positions")
    normalized_controls = FrozenStandardization(9, name="control_normalization")(controls)
    extended = ExtendedInputDense(
        units=700, activation=keras.activations.serialize(first.activation),
        name="extended_original_first_dense")
    feature_join = keras.layers.Concatenate(name="join_all_original_branches")
    outputs = {}
    for index in range(3):
        coordinates = TurbineCoordinates(index, name=f"coordinates_{index + 1}")(positions)
        scaled_coordinates = prefix(coordinates, training=False)
        hidden = extended([scaled_coordinates, normalized_controls])
        all_features = feature_join(tail(hidden, training=False))
        for name in (f"P{index + 1}", f"Ueff{index + 1}"):
            outputs[name] = keras.layers.Dense(
                1, activation="linear", name=f"{name}_readout",
                kernel_initializer=keras.initializers.GlorotUniform(seed=1234 + len(outputs)),
                kernel_regularizer=keras.regularizers.L2(1e-4))(all_features)
    normalized_outputs = keras.layers.Concatenate(name="normalized_predictions")(
        [outputs[name] for name in OUTPUT_NAMES])
    physical_outputs = FrozenStandardization(6, inverse=True, name="output_units")(
        normalized_outputs)
    model = keras.Model([controls, positions], physical_outputs, name="original_pinn_iochanged")
    extended.original_kernel.assign(first.kernel)
    extended.original_bias.assign(first.bias)

    expected = [extended.control_kernel]
    for name in OUTPUT_NAMES:
        expected.extend(model.get_layer(f"{name}_readout").trainable_weights)
    if {id(weight) for weight in model.trainable_weights} != {id(weight) for weight in expected}:
        raise RuntimeError("An original parameter was accidentally made trainable.")
    if trainable_count(model) != EXPECTED_TRAINABLE:
        raise RuntimeError("Unexpected trainable parameter count.")
    return model, prefix, tail, extended


def numerical_checks(original, model, prefix, tail, extended, tf, keras):
    """Check gradients and a temporary update; restore ALL new parameters.

    Probe positions are inside the author's domain. They are NOT project layout
    assumptions or power/effective-wind-speed accuracy tests.
    """
    rng = np.random.default_rng(1234)
    positions = np.asarray([[-120.4, -105.35, 35.0], [0.0, 0.0, 35.0],
                            [210.7, 105.35, 35.0]], dtype=np.float32)
    controls = rng.normal(0, 0.3, size=(4, 9)).astype(np.float32)
    batch = inputs_for(controls, positions)
    full_digest = source_digest(original)
    frozen_digest = retained_digest(model)
    snapshot = [weight.numpy().copy() for weight in model.trainable_weights]
    old_features = keras.Model(original.inputs,
                               [original.get_layer(name).input for name in SOURCE_HEADS])
    old_features.trainable = False
    try:
        # Extra kernel starts at zero: exact original features are preserved.
        for index in range(3):
            xyz = [batch["turbine_positions"][:, index, j:j + 1] for j in range(3)]
            before = old_features(xyz, training=False)
            after = tail(extended([prefix(xyz), controls]), training=False)
            for lhs, rhs in zip(before, after):
                np.testing.assert_allclose(lhs.numpy(), rhs.numpy(), rtol=1e-5, atol=1e-6)
        baseline = model(batch, training=False).numpy()
        if baseline.shape != (4, 6) or not np.isfinite(baseline).all():
            raise RuntimeError("Forward check produced invalid six-value outputs.")

        targets = tf.constant(rng.normal(size=(4, 6)).astype(np.float32))
        with tf.GradientTape() as tape:
            prediction = model(batch, training=False)
            loss = tf.reduce_mean(tf.square(prediction - targets))
        gradients = tape.gradient(loss, model.trainable_weights)
        if any(gradient is None or not np.isfinite(gradient.numpy()).all() for gradient in gradients):
            raise RuntimeError("Disconnected or invalid gradient in the new parameters.")
        control_index = next(index for index, weight in enumerate(model.trainable_weights)
                             if weight is extended.control_kernel)
        row_norms = np.linalg.norm(gradients[control_index].numpy(), axis=1)
        if (row_norms <= 0).any():
            raise RuntimeError("At least one of the nine input connection rows has no gradient.")
        clipped, _ = tf.clip_by_global_norm(gradients, 1.0)
        keras.optimizers.SGD(learning_rate=1e-3).apply_gradients(
            zip(clipped, model.trainable_weights))
        if not np.any(extended.control_kernel.numpy() != 0):
            raise RuntimeError("The new input kernel did not update in the numerical check.")
        if source_digest(original) != full_digest or retained_digest(model) != frozen_digest:
            raise RuntimeError("An original parameter changed in the numerical check.")

        # Give the extra rows temporary nonzero values to check all input paths.
        # This is rolled back below, not retained as training or initialization.
        extended.control_kernel.assign(rng.normal(0, 0.02, size=(9, 700)).astype(np.float32))
        control_tensor = tf.constant(controls[:2])
        with tf.GradientTape() as tape:
            tape.watch(control_tensor)
            output = model({"controls": control_tensor,
                            "turbine_positions": batch["turbine_positions"][:2]}, training=False)
        jacobian = tape.batch_jacobian(output, control_tensor).numpy()
        sensitivities = np.linalg.norm(jacobian, axis=(0, 1))
        if not np.isfinite(sensitivities).all() or (sensitivities <= 0).any():
            raise RuntimeError("At least one control cannot affect the replacement outputs.")
    finally:
        for weight, value in zip(model.trainable_weights, snapshot):
            weight.assign(value)
    if source_digest(original) != full_digest or retained_digest(model) != frozen_digest:
        raise RuntimeError("Original weights changed during the structural checks.")
    np.testing.assert_array_equal(extended.control_kernel.numpy(), np.zeros((9, 700), np.float32))
    np.testing.assert_allclose(model(batch, training=False).numpy(), baseline, rtol=1e-6, atol=1e-6)
    return {"original_features_preserved_at_zero_new_kernel": True,
            "all_nine_input_rows_have_gradients": True,
            "all_nine_inputs_can_affect_outputs_with_nonzero_connections": True,
            "temporary_check_update_rolled_back": True,
            "original_weights_unchanged": True}, batch


def build(args):
    tf, keras, Extended, Standardization, Coordinates = tensorflow_components()
    keras.utils.set_random_seed(1234)
    root = args.project_root.resolve()
    source = args.source or root / "OutputChange" / "prepared_9ms" / "original_frozen.keras"
    if not source.is_file():
        raise FileNotFoundError(f"未找到准备好的原模型：{source}\n请先运行 prepare_pinn_outputchange.py。")
    print("Loading:", source, flush=True)
    original = keras.models.load_model(str(source), compile=False)
    model, prefix, tail, extended = build_modified(
        original, keras, Extended, Standardization, Coordinates)
    print("Checking original weights, gradients and all nine input paths...", flush=True)
    checks, batch = numerical_checks(original, model, prefix, tail, extended, tf, keras)
    destination = unique_directory(args.output or root / "OutputChange" / "iochanged_9ms")
    model_path = destination / "untrained.keras"
    model.save(str(model_path))
    restored = keras.models.load_model(str(model_path), compile=False)
    if trainable_count(restored) != EXPECTED_TRAINABLE or retained_digest(restored) != retained_digest(model):
        raise RuntimeError("Save/reload changed the freezing or original weights.")
    np.testing.assert_allclose(model(batch).numpy(), restored(batch).numpy(), rtol=1e-5, atol=1e-6)
    checks["save_reload_equal_and_freezing_preserved"] = True
    config_path = ensure_config(root)
    with (destination / "training_data_template.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerow(CONTROL_NAMES + OUTPUT_NAMES)
    with (destination / "model_summary.txt").open("w", encoding="utf-8") as handle:
        model.summary(print_fn=lambda line: handle.write(line + "\n"))
    report = {"status": "structure_built_and_checked_NOT_trained", "built_at": timestamp(),
              "source": str(source.resolve()), "tensorflow": tf.__version__, "tf_keras": keras.__version__,
              "control_order": list(CONTROL_NAMES), "output_order": list(OUTPUT_NAMES),
              "output_units": ["W", "W", "W", "m/s", "m/s", "m/s"],
              "inputs": {"controls": [None, 9], "turbine_positions": [None, 3, 3]},
              "original_parameters": 3_090_200, "retained_original_hidden_parameters": 3_087_200,
              "new_input_trainable_parameters": 6300, "new_output_trainable_parameters": 18006,
              "total_trainable_parameters": trainable_count(model),
              "total_parameters_including_statistics": int(model.count_params()),
              "retained_original_sha256": retained_digest(model), "checks": checks,
              "config": str(config_path), "training_performed_on_real_data": False,
              "notes": ["All original hidden branches are retained; scalar flow heads are replaced.",
                        "No new hidden layer; extra rows in the original first kernel start at zero.",
                        "Coordinates are auxiliary inputs; use fixed project geometry during training/prediction.",
                        "The six readouts are data-fitted case outputs, not renamed u/v/w/p/k/eps.",
                        "Ueff labels require the project's rotor-disk effective-speed definition.",
                        "The original RANS/k-epsilon loss is not used for these six case outputs.",
                        "Frozen weights still participate in forward/backward calculations for the new input kernel.",
                        "No transfer accuracy or speedup is established by these structural checks."]}
    write_json(destination / "build_report.json", report)
    print("[OK] Original hidden parameters retained and frozen: 3,087,200", flush=True)
    print("New input trainable parameters: 6,300", flush=True)
    print("New output trainable parameters: 18,006", flush=True)
    print("Total trainable parameters: 24,306 (0.79% of original)", flush=True)
    print("Output order:", ", ".join(OUTPUT_NAMES), flush=True)
    print("[OK] Checks passed; temporary check changes were restored.", flush=True)
    print("Saved to:", destination, flush=True)
    print("Before training, fill turbine_positions_m and confirm units in:", config_path, flush=True)
    print("No real-data training performed. Untrained outputs must not be used for optimization.", flush=True)


def resolve_bundle(root, provided):
    if provided:
        folder = provided.resolve()
        if not (folder / "build_report.json").is_file():
            raise FileNotFoundError(f"No build_report.json in {folder}")
        return folder
    reports = list((root / "OutputChange").glob("iochanged_9ms*/build_report.json"))
    if not reports:
        raise FileNotFoundError("请先运行 python modify_pinn_io.py。")
    return max(reports, key=lambda path: path.stat().st_mtime_ns).parent


def read_cases(path, require_targets, fixed_wind_speed=None):
    names = CONTROL_NAMES + OUTPUT_NAMES if require_targets else CONTROL_NAMES
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV需要唯一列名和逗号分隔的表头。")
        missing = [name for name in names if name not in reader.fieldnames]
        if missing:
            raise ValueError("CSV缺少列：" + ", ".join(missing)
                             + "。缺失控制量不能用0自动补齐。")
        other_columns = [name for name in reader.fieldnames if name not in names]
        rows, extras = [], {name: [] for name in other_columns}
        for line, row in enumerate(reader, start=2):
            try:
                rows.append([float(row[name]) for name in names])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"CSV第{line}行存在空白或非数值。") from exc
            for name in other_columns:
                extras[name].append(row.get(name))
    values = np.asarray(rows, dtype=np.float64)
    if not len(rows) or not np.isfinite(values).all():
        raise ValueError("CSV不能为空，且所有控制量/标签必须为有限数值。")
    # Avoid silently ignoring known varying conditions with only nine inputs.
    for name in other_columns:
        lowered = name.lower()
        if any(token in lowered for token in ("wind", "turbulence", "inlet", "ti_ref", "u_ref")):
            try:
                condition = np.asarray([float(value) for value in extras[name]], dtype=np.float64)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"环境条件列{name}需要非空的数值。") from exc
            if not np.isfinite(condition).all():
                raise ValueError(f"环境条件列{name}包含非有限值。")
            if not np.allclose(condition, condition[0], rtol=1e-7, atol=1e-9):
                raise ValueError(f"列{name}随工况变化，但本版尚未把它接入模型；请先选固定环境的数据。")
            if (fixed_wind_speed is not None and lowered in
                    ("wind_speed", "wind_speed_m_s", "inlet_wind_speed_m_s", "u_ref")):
                if not np.isclose(condition[0], fixed_wind_speed, rtol=1e-6, atol=1e-8):
                    raise ValueError(f"CSV列{name}与配置的固定入口风速不一致，请检查配置和数据。")
    controls = values[:, :9]
    if (controls[:, [2, 5, 8]] < 0).any():
        raise ValueError("本版转速输入应为非负的转速大小。")
    if require_targets:
        targets = values[:, 9:]
        if (targets[:, :3] < 0).any() or (targets[:, 3:] <= 0).any():
            raise ValueError("标签P需非负（W），Ueff需大于0（m/s）。")
        return controls, targets
    return controls


def split_groups(controls, seed):
    # Repeated evaluations of an identical control setting stay in one split.
    _, group = np.unique(controls, axis=0, return_inverse=True)
    groups = np.arange(int(group.max()) + 1)
    if len(groups) < 5:
        raise ValueError("至少需要5组不同的九维控制组合，才能分开训练、验证和测试；这不代表数据已足够。")
    np.random.default_rng(seed).shuffle(groups)
    test_count = max(1, int(round(len(groups) * 0.2)))
    validation_count = max(1, int(round(len(groups) * 0.2)))
    test = groups[:test_count]
    validation = groups[test_count:test_count + validation_count]
    train = groups[test_count + validation_count:]
    if len(train) < 2:
        raise ValueError("Not enough independent training groups.")
    return tuple(np.flatnonzero(np.isin(group, selected)) for selected in (train, validation, test))


def statistics(values):
    mean = np.mean(values, axis=0, dtype=np.float64)
    std = np.std(values, axis=0, dtype=np.float64)
    # Constant columns are identified in the report, not falsely learned.
    std = np.where(std <= 1e-8, 1.0, std)
    return mean.astype(np.float32), std.astype(np.float32)


def predict_batches(model, controls, positions, batch_size=32):
    chunks = [model(inputs_for(controls[start:start + batch_size], positions),
                    training=False).numpy()
              for start in range(0, len(controls), batch_size)]
    return np.concatenate(chunks, axis=0)


def error_metrics(predictions, targets):
    difference = predictions.astype(np.float64) - targets
    return {name: {"MAE": float(np.mean(np.abs(difference[:, index]))),
                   "RMSE": float(np.sqrt(np.mean(difference[:, index] ** 2))),
                   "unit": "W" if index < 3 else "m/s"}
            for index, name in enumerate(OUTPUT_NAMES)}


def train(args):
    tf, keras, _, _, _ = tensorflow_components()
    keras.utils.set_random_seed(args.seed)
    root = args.project_root.resolve()
    bundle = resolve_bundle(root, args.bundle)
    config_path = args.config or root / "OutputChange" / "project_config.json"
    config, positions = validate_config(config_path)
    controls, targets = read_cases(args.csv, require_targets=True,
                                   fixed_wind_speed=config["fixed_inlet_wind_speed_m_s"])
    train_idx, validation_idx, test_idx = split_groups(controls, args.seed)
    # Conversion after grouping prevents distinct float64 settings leaking across splits.
    with np.errstate(over="ignore"):
        controls = controls.astype(np.float32)
        targets = targets.astype(np.float32)
    if not np.isfinite(controls).all() or not np.isfinite(targets).all():
        raise ValueError("CSV数值超出模型float32可表示范围，请检查单位。")
    _, float_group = np.unique(controls, axis=0, return_inverse=True)
    if any(np.intersect1d(float_group[left], float_group[right]).size
           for left, right in ((train_idx, validation_idx), (train_idx, test_idx), (validation_idx, test_idx))):
        raise ValueError("不同控制量在float32转换后重合；请检查数据精度后重新划分。")
    x_mean, x_std = statistics(controls[train_idx])
    y_mean, y_std = statistics(targets[train_idx])
    constants = [name for index, name in enumerate(CONTROL_NAMES)
                 if np.ptp(controls[train_idx, index]) <= 1e-8]
    if len(constants) == 9:
        raise ValueError("训练部分的九个控制量全部不变，不能学习控制作用。")
    if constants:
        print("Not varied in the training split; their effects cannot be validated:", ", ".join(constants), flush=True)
    model = keras.models.load_model(str(bundle / "untrained.keras"), compile=False)
    build_report = read_json(bundle / "build_report.json")
    if (trainable_count(model) != EXPECTED_TRAINABLE
            or retained_digest(model) != build_report["retained_original_sha256"]):
        raise RuntimeError("Prepared model freezing/original weights do not match the build report.")
    original_hash = retained_digest(model)
    model.get_layer("control_normalization").mean.assign(x_mean)
    model.get_layer("control_normalization").std.assign(x_std)
    model.get_layer("output_units").mean.assign(y_mean)
    model.get_layer("output_units").std.assign(y_std)
    fitting_view = keras.Model(model.inputs, model.get_layer("normalized_predictions").output)
    if trainable_count(fitting_view) != EXPECTED_TRAINABLE:
        raise RuntimeError("Training view unexpectedly changed the trainable parameter set.")
    fitting_view.compile(optimizer=keras.optimizers.Adam(learning_rate=args.learning_rate, clipnorm=1.0),
                         loss="mse")
    callback = keras.callbacks.EarlyStopping(monitor="val_loss", patience=args.patience,
                                             min_delta=1e-6, restore_best_weights=True)
    print("Training ONLY new input connections and output readouts: 24,306 parameters", flush=True)
    print("Train/validation/test cases:", len(train_idx), len(validation_idx), len(test_idx), flush=True)
    print("Loss uses standardized outputs; this is supervised transfer, without the original PDE loop.", flush=True)
    history = fitting_view.fit(
        inputs_for(controls[train_idx], positions), (targets[train_idx] - y_mean) / y_std,
        validation_data=(inputs_for(controls[validation_idx], positions),
                         (targets[validation_idx] - y_mean) / y_std),
        epochs=args.epochs, batch_size=args.batch_size, callbacks=[callback], verbose=2)
    if retained_digest(model) != original_hash:
        raise RuntimeError("Original weights changed during training; refusing to export.")
    test_predictions = predict_batches(model, controls[test_idx], positions)
    if not np.isfinite(test_predictions).all():
        raise RuntimeError("Training produced nonfinite outputs; refusing to export.")
    destination = unique_directory(bundle / f"training_{timestamp()}")
    model_path = destination / "trained.keras"
    model.save(str(model_path))
    restored = keras.models.load_model(str(model_path), compile=False)
    if retained_digest(restored) != original_hash or trainable_count(restored) != EXPECTED_TRAINABLE:
        raise RuntimeError("Trained model failed the original-weight/freeze reload check.")
    np.testing.assert_allclose(test_predictions,
                               predict_batches(restored, controls[test_idx], positions), rtol=1e-5, atol=1e-4)
    write_json(destination / "config_used.json", config)
    history_values = {key: [float(value) for value in values] for key, values in history.history.items()}
    report = {"status": "trained_supervised_transfer_requires_accuracy_review", "trained_at": timestamp(),
              "bundle": str(bundle), "csv": str(args.csv.resolve()), "config": config,
              "control_order": list(CONTROL_NAMES), "output_order": list(OUTPUT_NAMES),
              "output_units": ["W", "W", "W", "m/s", "m/s", "m/s"],
              "trainable_parameters": trainable_count(model), "original_parameters_unchanged": True,
              "retained_original_sha256": original_hash, "epochs_completed": len(history.epoch),
              "seed": args.seed, "train_rows_zero_based": train_idx.tolist(),
              "validation_rows_zero_based": validation_idx.tolist(), "test_rows_zero_based": test_idx.tolist(),
              "training_control_min": controls[train_idx].min(axis=0).tolist(),
              "training_control_max": controls[train_idx].max(axis=0).tolist(),
              "constant_controls_in_training": constants,
              "training_input_mean": x_mean.tolist(), "training_input_std": x_std.tolist(),
              "training_output_mean": y_mean.tolist(), "training_output_std": y_std.tolist(),
              "test_metrics": error_metrics(test_predictions, targets[test_idx]), "history": history_values,
              "negative_test_output_count": int((test_predictions < 0).sum()),
              "notes": ["All scaling statistics use only the training split.",
                        "Identical control settings are grouped before splitting.",
                        "Test data were not used for scaling or early stopping.",
                        "No original PDE loss is used; accuracy must be judged against physical labels.",
                        "The linear readouts do not enforce nonnegative outputs.",
                        "Wind speed, direction and turbulence intensity are fixed conditions in this version."]}
    write_json(destination / "training_report.json", report)
    print("[OK] Trained model saved:", model_path, flush=True)
    print("[OK] Original hidden weights unchanged; reload check passed.", flush=True)
    print("Held-out test errors:", json.dumps(report["test_metrics"], ensure_ascii=False), flush=True)


def predict(args):
    _, keras, _, _, _ = tensorflow_components()
    root = args.project_root.resolve()
    if args.run:
        run = args.run.resolve()
    else:
        bundle = resolve_bundle(root, args.bundle)
        reports = list(bundle.glob("training_*/training_report.json"))
        if not reports:
            raise FileNotFoundError("尚无训练完成的模型；先提供真实数据运行train。")
        run = max(reports, key=lambda path: path.stat().st_mtime_ns).parent
    report = read_json(run / "training_report.json")
    config, positions = validate_config(run / "config_used.json")
    controls = (np.asarray([args.controls], dtype=np.float32) if args.controls is not None
                else read_cases(args.csv, require_targets=False).astype(np.float32))
    if not np.isfinite(controls).all() or (controls[:, [2, 5, 8]] < 0).any():
        raise ValueError("控制量必须有限，转速大小需非负。")
    lower = np.asarray(report["training_control_min"])
    upper = np.asarray(report["training_control_max"])
    outside = (controls < lower) | (controls > upper)
    if outside.any():
        names = [name for index, name in enumerate(CONTROL_NAMES) if outside[:, index].any()]
        print("Outside training range; prediction is extrapolation:", ", ".join(names), flush=True)
    model = keras.models.load_model(str(run / "trained.keras"), compile=False)
    if retained_digest(model) != report["retained_original_sha256"]:
        raise RuntimeError("The original-weight digest does not match the trained report.")
    values = predict_batches(model, controls, positions)
    if not np.isfinite(values).all():
        raise RuntimeError("预测出现NaN/Inf。")
    if (values < 0).any():
        print("Some outputs are negative; review physical validity before using this model.", flush=True)
    if args.output:
        output = args.output.resolve()
        if output.exists():
            raise FileExistsError(f"为避免覆盖文件，请给输出指定新路径：{output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(CONTROL_NAMES + OUTPUT_NAMES)
            writer.writerows(np.concatenate([controls, values], axis=1).tolist())
        print("Predictions saved:", output, flush=True)
    else:
        for row in values:
            print(json.dumps(dict(zip(OUTPUT_NAMES, map(float, row))), ensure_ascii=False))
    print("Units: P1/P2/P3 in W; Ueff1/Ueff2/Ueff3 in m/s.", flush=True)


def parser():
    root_parser = argparse.ArgumentParser(description=__doc__)
    subparsers = root_parser.add_subparsers(dest="command")
    build_parser = subparsers.add_parser("build", help="Build/check the modified original model; no real-data fitting")
    build_parser.add_argument("--project-root", type=Path, default=ROOT)
    build_parser.add_argument("--source", type=Path)
    build_parser.add_argument("--output", type=Path)
    train_parser = subparsers.add_parser("train", help="Supervised fitting of ONLY new input/output parameters")
    train_parser.add_argument("--project-root", type=Path, default=ROOT)
    train_parser.add_argument("--bundle", type=Path)
    train_parser.add_argument("--config", type=Path)
    train_parser.add_argument("--csv", type=Path, required=True)
    train_parser.add_argument("--epochs", type=int, default=200)
    train_parser.add_argument("--batch-size", type=int, default=16)
    train_parser.add_argument("--learning-rate", type=float, default=1e-4)
    train_parser.add_argument("--patience", type=int, default=30)
    train_parser.add_argument("--seed", type=int, default=1234)
    predict_parser = subparsers.add_parser("predict", help="Predict using a completed training run and its fixed geometry")
    predict_parser.add_argument("--project-root", type=Path, default=ROOT)
    predict_parser.add_argument("--bundle", type=Path)
    predict_parser.add_argument("--run", type=Path)
    prediction_input = predict_parser.add_mutually_exclusive_group(required=True)
    prediction_input.add_argument("--controls", nargs=9, type=float, metavar="VALUE")
    prediction_input.add_argument("--csv", type=Path)
    predict_parser.add_argument("--output", type=Path)
    return root_parser


def main():
    arguments = sys.argv[1:] or ["build"]
    args = parser().parse_args(arguments)
    if args.command is None:
        parser().print_help()
        return 0
    try:
        if args.command == "train" and (args.epochs < 1 or args.batch_size < 1
                                        or args.learning_rate <= 0 or args.patience < 0):
            raise ValueError("训练参数需为合法的正数，patience可为0。")
        {"build": build, "train": train, "predict": predict}[args.command](args)
    except Exception:
        print("\n[ERROR] 操作未完成，请把末尾报错日志发来。", file=sys.stderr)
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
