"""Extend the ORIGINAL pretrained PINN to three wind conditions + nine controls.

Run in the existing project root (TensorFlow 2.16.1, tf-keras 2.16.0):
    python modify_pinn_wind_io.py

Build checks do not train a physical predictor. All original hidden weights
remain frozen. External inputs are 12 SI-valued physical quantities; wind
direction becomes sin/cos INSIDE the saved graph, giving 13 kernel rows.
This is supervised transfer, without the original PDE residual training loop.
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
SCHEMA = "pinn_wind_io_v1_si_flow_to"
SOURCE_HEADS = ("output_u", "output_v", "output_w", "output_p", "output_k", "output_eps")
WIND_NAMES = ("ambient_wind_speed_m_s", "ambient_wind_direction_rad", "turbulence_intensity")
CONTROL_NAMES = tuple(name for i in range(1, 4)
                      for name in (f"yaw{i}", f"pitch{i}", f"rotor_speed{i}"))
INPUT_NAMES = WIND_NAMES + CONTROL_NAMES
FEATURE_NAMES = (WIND_NAMES[0], "wind_direction_sin", "wind_direction_cos", WIND_NAMES[2]) + CONTROL_NAMES
OUTPUT_NAMES = ("P1", "P2", "P3", "Ueff1", "Ueff2", "Ueff3")
INPUT_WIDTH, FEATURE_WIDTH = 12, 13
EXPECTED_TRAINABLE = 13 * 700 + 6 * (3000 + 1)  # 27,106.
SI_UNITS = {"yaw": "rad", "pitch": "rad", "rotor_speed": "rad/s"}
DIRECTION_CONVENTION = "flow_to_ccw_from_positive_x"


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def unique_directory(path):
    path = Path(path)
    candidate, index = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}_{index}")
        index += 1
    candidate.mkdir(parents=True)
    return candidate


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")


def validated_cases(values):
    values = np.array(values, dtype=np.float64, copy=True)
    if values.ndim != 2 or values.shape[1] != INPUT_WIDTH or not len(values):
        raise ValueError("每个工况需12个输入：三个风况量，然后按机组交错排列的九个控制量。")
    if not np.isfinite(values).all():
        raise ValueError("所有输入必须是有限数值，不能有空白、NaN或Inf。")
    if (values[:, 0] <= 0).any():
        raise ValueError("入口风速须大于0，单位m/s。")
    if ((values[:, 2] < 0) | (values[:, 2] > 1)).any():
        raise ValueError("本接口TI使用0到1的小数：10%填0.10，不能填10。")
    if (values[:, [5, 8, 11]] < 0).any():
        raise ValueError("转速须为非负大小，单位rad/s；旧版rpm须先转换。")
    # Canonical angles group periodic aliases together before data splitting.
    for column in (1, 3, 6, 9):
        values[:, column] = (values[:, column] + np.pi) % (2 * np.pi) - np.pi
    return values


def encoded_features(cases):
    cases = validated_cases(cases)
    return np.column_stack((cases[:, 0], np.sin(cases[:, 1]),
                            np.cos(cases[:, 1]), cases[:, 2], cases[:, 3:]))


def rotate_positions(cases, positions):
    cases = validated_cases(cases)
    positions = np.asarray(positions, dtype=np.float64)
    if positions.shape == (3, 3):
        positions = np.broadcast_to(positions, (len(cases), 3, 3))
    if positions.shape != (len(cases), 3, 3) or not np.isfinite(positions).all():
        raise ValueError("位置应为[3,3]，或与工况对应的[N,3,3]。")
    c, s = np.cos(cases[:, 1:2]), np.sin(cases[:, 1:2])
    x, y, z = positions[:, :, 0], positions[:, :, 1], positions[:, :, 2]
    return np.stack((c * x + s * y, -s * x + c * y, z), axis=-1)


def inputs_for(cases, positions):
    raw = validated_cases(cases)
    positions = np.asarray(positions, dtype=np.float64)
    if positions.shape == (3, 3):
        positions = np.broadcast_to(positions, (len(raw), 3, 3)).copy()
    if positions.shape != (len(raw), 3, 3) or not np.isfinite(positions).all():
        raise ValueError("位置须为有限的[3,3]或[N,3,3]数组。")
    with np.errstate(over="ignore"):
        raw, positions = raw.astype(np.float32), positions.astype(np.float32)
    if not np.isfinite(raw).all() or not np.isfinite(positions).all():
        raise ValueError("输入超出float32表示范围，请检查单位。")
    return {"conditions_and_controls": raw, "turbine_positions": positions}


@lru_cache(maxsize=1)
def tensorflow_components():
    import tensorflow as tf
    import tf_keras as keras

    if tf.__version__.split(".")[:2] != ["2", "16"] or keras.__version__.split(".")[:2] != ["2", "16"]:
        raise RuntimeError("请使用TensorFlow 2.16.x和tf-keras 2.16.x，不要改用默认Keras 3接口。")
    tf.config.threading.set_intra_op_parallelism_threads(4)
    tf.config.threading.set_inter_op_parallelism_threads(2)

    @keras.utils.register_keras_serializable(package="PinnWindOutputChange")
    class ExtendedInputDense(keras.layers.Layer):
        """Same first hidden layer: frozen coordinate kernel + 13 new rows."""

        def __init__(self, units=700, activation="swish", **kwargs):
            super().__init__(**kwargs)
            self.units = int(units)
            self.activation = keras.activations.get(activation)

        def build(self, input_shape):
            if int(input_shape[0][-1]) != 3 or int(input_shape[1][-1]) != FEATURE_WIDTH:
                raise ValueError("Expected three scaled coordinates and thirteen encoded features.")
            self.original_kernel = self.add_weight(
                name="original_coordinate_kernel", shape=(3, self.units), initializer="zeros", trainable=False)
            self.original_bias = self.add_weight(
                name="original_bias", shape=(self.units,), initializer="zeros", trainable=False)
            self.condition_kernel = self.add_weight(
                name="new_condition_kernel", shape=(FEATURE_WIDTH, self.units), initializer="zeros",
                trainable=True, regularizer=keras.regularizers.L2(1e-4))
            super().build(input_shape)

        def call(self, inputs):
            xyz, features = inputs
            value = tf.matmul(xyz, self.original_kernel) + tf.matmul(features, self.condition_kernel)
            return self.activation(tf.nn.bias_add(value, self.original_bias))

        def get_config(self):
            return {**super().get_config(), "units": self.units,
                    "activation": keras.activations.serialize(self.activation)}

    @keras.utils.register_keras_serializable(package="PinnWindOutputChange")
    class FrozenStandardization(keras.layers.Layer):
        def __init__(self, width, inverse=False, **kwargs):
            kwargs["trainable"] = False
            super().__init__(**kwargs)
            self.width, self.inverse = int(width), bool(inverse)

        def build(self, input_shape):
            self.mean = self.add_weight(name="mean", shape=(self.width,), initializer="zeros", trainable=False)
            self.std = self.add_weight(name="std", shape=(self.width,), initializer="ones", trainable=False)
            super().build(input_shape)

        def call(self, inputs):
            return inputs * self.std + self.mean if self.inverse else (inputs - self.mean) / self.std

        def get_config(self):
            return {**super().get_config(), "width": self.width, "inverse": self.inverse}

    @keras.utils.register_keras_serializable(package="PinnWindOutputChange")
    class WindFeatures(keras.layers.Layer):
        def call(self, raw):
            controls = [((raw[:, j:j + 1] + np.pi) % (2 * np.pi) - np.pi)
                        if j in (3, 6, 9) else raw[:, j:j + 1] for j in range(3, 12)]
            return tf.concat([raw[:, 0:1], tf.sin(raw[:, 1:2]), tf.cos(raw[:, 1:2]), raw[:, 2:3]]
                             + controls, axis=-1)

    @keras.utils.register_keras_serializable(package="PinnWindOutputChange")
    class WindCoordinates(keras.layers.Layer):
        def call(self, inputs):
            raw, positions = inputs
            c, s = tf.cos(raw[:, 1:2]), tf.sin(raw[:, 1:2])
            x, y, z = positions[:, :, 0], positions[:, :, 1], positions[:, :, 2]
            return tf.stack([c * x + s * y, -s * x + c * y, z], axis=-1)

    @keras.utils.register_keras_serializable(package="PinnWindOutputChange")
    class TurbineCoordinates(keras.layers.Layer):
        def __init__(self, index, **kwargs):
            super().__init__(**kwargs)
            self.index = int(index)

        def call(self, inputs):
            return [inputs[:, self.index, j:j + 1] for j in range(3)]

        def get_config(self):
            return {**super().get_config(), "index": self.index}

    return tf, keras, ExtendedInputDense, FrozenStandardization, WindFeatures, WindCoordinates, TurbineCoordinates


def trainable_count(model):
    return sum(int(np.prod(weight.shape.as_list())) for weight in model.trainable_weights)


def digest_arrays(entries):
    digest = hashlib.sha256()
    for name, value in entries:
        array = np.asarray(value)
        digest.update(name.encode("utf-8"))
        digest.update(str(array.shape).encode("ascii"))
        digest.update(array.tobytes())
    return digest.hexdigest()


def source_digest(model):
    return digest_arrays((weight.name, weight.numpy())
                         for weight in sorted(model.weights, key=lambda value: value.name))


def retained_digest(model):
    first = model.get_layer("extended_original_first_dense")
    entries = [("first_kernel", first.original_kernel.numpy()), ("first_bias", first.original_bias.numpy())]
    for layer in sorted(model.get_layer("original_hidden_layers").layers, key=lambda value: value.name):
        entries.extend((f"{layer.name}/{i}", weight.numpy()) for i, weight in enumerate(layer.weights))
    return digest_arrays(entries)


def ensure_config(root):
    path = root / "OutputChange" / "wind_project_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_json(path, {
            "schema": SCHEMA,
            "turbine_positions_m": [[None, None, None] for _ in range(3)],
            "control_units": SI_UNITS,
            "wind_direction_convention": DIRECTION_CONVENTION,
            "geometry_frame": "fixed_source_origin_xy_at_zero_wind",
            "time_scale": "quasi_steady_or_case_mean",
            "turbine_model": None,
            "rotor_diameter_m": None,
            "air_density_kg_m3": None,
            "fixed_inlet_profile_description": None,
            "power_definition": None,
            "ueff_definition": None,
            "notes": [
                "本配置与旧版project_config.json独立。构建不需要填写；训练前填真实三机位置。",
                "新接口固定使用rad、rad、rad/s。旧版deg与rpm须转换，不能仅改单位文字。",
                "风向为风吹向的方向：0沿+x，pi/2沿+y，从上往下看逆时针为正。不是气象来向。",
                "偏航输入是相对来流的失配角；优化侧应先完成执行器映射，再传实际运行点。",
                "机位以原模型的固定原点为基准，零风向时x沿流、y横向、z向上，单位m。",
                "图内按每行风向将固定机位旋转到随来流对齐的坐标系，不改变机组编号。",
                "机型、尺寸、密度及入口剖面在本版固定。请在数据说明中补齐这些条件。",
                "补齐机械/电功率口径及转子盘有效风速定义；单点风速不能直接替代Ueff。",
                "原预训练权重来自9m/s四机工况；旋转坐标和增加输入本身不证明迁移准确。",
                "当前训练是监督迁移，不包含原RANS/k-epsilon方程残差或新的边界条件损失。"
            ]
        })
    return path


def validate_config(path):
    config = read_json(path)
    if config.get("schema") != SCHEMA or config.get("control_units") != SI_UNITS:
        raise ValueError("请使用新版wind_project_config.json；本接口单位固定为rad、rad、rad/s。")
    if (config.get("wind_direction_convention") != DIRECTION_CONVENTION
            or config.get("geometry_frame") != "fixed_source_origin_xy_at_zero_wind"):
        raise ValueError("风向或坐标约定不匹配，须先把数据转换为新版接口约定。")
    try:
        positions = np.asarray(config["turbine_positions_m"], dtype=np.float64)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("请填三台风机真实的[x,y,z]坐标，单位m。") from exc
    if positions.shape != (3, 3) or not np.isfinite(positions).all():
        raise ValueError("训练前请填写wind_project_config.json的真实机位；不能保留null。")
    if (positions[:, 2] <= 0).any() or len(np.unique(positions, axis=0)) != 3:
        raise ValueError("三机位置必须不同，轮毂高度必须大于0。")
    return config, positions


def build_modified(original, components):
    _, keras, Extended, Standardization, Features, WindCoordinates, Coordinates = components
    if original.count_params() != 3_090_200 or len(original.inputs) != 3 or set(original.output_names) != set(SOURCE_HEADS):
        raise ValueError("源模型不是已核对的3,090,200参数原PINN。")
    original.trainable = False
    candidates = [layer for layer in original.layers if isinstance(layer, keras.layers.Dense)
                  and tuple(layer.kernel.shape.as_list()) == (3, 700)]
    if len(candidates) != 1 or not candidates[0].use_bias:
        raise ValueError("无法唯一识别原3-to-700第一隐藏层。")
    first = candidates[0]
    tensors = [original.get_layer(name).input for name in SOURCE_HEADS]
    if any(int(tensor.shape[-1]) != 500 for tensor in tensors):
        raise ValueError("原模型必须具有六个500维特征分支。")
    prefix = keras.Model(original.inputs, first.input, name="original_coordinate_scaling")
    tail = keras.Model(first.output, tensors, name="original_hidden_layers")
    prefix.trainable = tail.trainable = False
    if tail.count_params() != 3_084_400:
        raise ValueError("原主干/分支参数数目不匹配。")
    raw = keras.Input(shape=(INPUT_WIDTH,), name="conditions_and_controls")
    positions = keras.Input(shape=(3, 3), name="turbine_positions")
    features = Features(name="wind_features")(raw)
    normalized = Standardization(FEATURE_WIDTH, name="input_normalization")(features)
    aligned = WindCoordinates(name="wind_aligned_coordinates")([raw, positions])
    extended = Extended(units=700, activation=keras.activations.serialize(first.activation),
                        name="extended_original_first_dense")
    join = keras.layers.Concatenate(name="join_all_original_branches")
    outputs = {}
    for i in range(3):
        xyz = Coordinates(i, name=f"coordinates_{i + 1}")(aligned)
        hidden = extended([prefix(xyz, training=False), normalized])
        branch_features = join(tail(hidden, training=False))
        for name in (f"P{i + 1}", f"Ueff{i + 1}"):
            outputs[name] = keras.layers.Dense(
                1, activation="linear", name=f"{name}_readout",
                kernel_initializer=keras.initializers.GlorotUniform(seed=1234 + len(outputs)),
                kernel_regularizer=keras.regularizers.L2(1e-4))(branch_features)
    prediction = keras.layers.Concatenate(name="normalized_predictions")([outputs[n] for n in OUTPUT_NAMES])
    prediction = Standardization(6, inverse=True, name="output_units")(prediction)
    model = keras.Model([raw, positions], prediction, name="original_pinn_wind_iochanged")
    extended.original_kernel.assign(first.kernel)
    extended.original_bias.assign(first.bias)
    expected = [extended.condition_kernel]
    for name in OUTPUT_NAMES:
        expected.extend(model.get_layer(f"{name}_readout").trainable_weights)
    if ({id(w) for w in model.trainable_weights} != {id(w) for w in expected}
            or trainable_count(model) != EXPECTED_TRAINABLE):
        raise RuntimeError("可训练参数不符合预期，拒绝导出。")
    return model, prefix, tail, extended


def numerical_checks(original, model, prefix, tail, extended, components):
    tf, keras, *_ = components
    rng = np.random.default_rng(1234)
    positions = np.array([[-120.4, -105.35, 35], [0, 0, 35], [210.7, 105.35, 35]], dtype=np.float32)
    raw = np.column_stack(([8.0, 9.0, 10.0, 11.0], [0.0, 0.12, -0.20, 0.35],
                           [0.06, 0.10, 0.14, 0.08], rng.normal(0.1, 0.2, (4, 9)))).astype(np.float32)
    raw[:, [5, 8, 11]] = np.abs(raw[:, [5, 8, 11]]) + 1
    batch = inputs_for(raw, positions)
    full_hash, frozen_hash = source_digest(original), retained_digest(model)
    snapshot = [w.numpy().copy() for w in model.trainable_weights]
    old_features = keras.Model(original.inputs, [original.get_layer(name).input for name in SOURCE_HEADS])
    old_features.trainable = False
    baseline = model(batch, training=False).numpy()
    try:
        tf_features = model.get_layer("wind_features")(batch["conditions_and_controls"]).numpy()
        np.testing.assert_allclose(tf_features, encoded_features(raw), rtol=2e-6, atol=5e-7)
        aligned = model.get_layer("wind_aligned_coordinates")(
            [batch["conditions_and_controls"], batch["turbine_positions"]]).numpy()
        np.testing.assert_allclose(aligned, rotate_positions(raw, positions), rtol=2e-6, atol=5e-5)
        for i in range(3):
            xyz = [aligned[:, i, j:j + 1] for j in range(3)]
            before = old_features(xyz, training=False)
            after = tail(extended([prefix(xyz), tf_features]), training=False)
            for a, b in zip(before, after):
                np.testing.assert_allclose(a.numpy(), b.numpy(), rtol=1e-5, atol=1e-6)
        if baseline.shape != (4, 6) or not np.isfinite(baseline).all():
            raise RuntimeError("前向计算未返回有限六维输出。")
        targets = tf.constant(rng.normal(size=(4, 6)).astype(np.float32))
        with tf.GradientTape() as tape:
            loss = tf.reduce_mean(tf.square(model(batch, training=False) - targets))
        gradients = tape.gradient(loss, model.trainable_weights)
        if any(g is None or not np.isfinite(g.numpy()).all() for g in gradients):
            raise RuntimeError("新增参数存在无效或断开的梯度。")
        idx = next(i for i, w in enumerate(model.trainable_weights) if w is extended.condition_kernel)
        if (np.linalg.norm(gradients[idx].numpy(), axis=1) <= 0).any():
            raise RuntimeError("十三行新增连接中存在没有梯度的行。")
        clipped, _ = tf.clip_by_global_norm(gradients, 1.0)
        keras.optimizers.SGD(learning_rate=1e-3).apply_gradients(zip(clipped, model.trainable_weights))
        if not np.any(extended.condition_kernel.numpy() != 0):
            raise RuntimeError("新增连接未通过临时更新检查。")
        extended.condition_kernel.assign(rng.normal(0, 0.005, (FEATURE_WIDTH, 700)).astype(np.float32))
        probe = tf.constant(batch["conditions_and_controls"][:2])
        with tf.GradientTape() as tape:
            tape.watch(probe)
            output = model({"conditions_and_controls": probe,
                            "turbine_positions": batch["turbine_positions"][:2]}, training=False)
        sensitivity = np.linalg.norm(tape.batch_jacobian(output, probe).numpy(), axis=(0, 1))
        if not np.isfinite(sensitivity).all() or (sensitivity <= 0).any():
            raise RuntimeError("十二个物理输入中有输入不能影响新输出。")
    finally:
        for w, value in zip(model.trainable_weights, snapshot):
            w.assign(value)
    if source_digest(original) != full_hash or retained_digest(model) != frozen_hash:
        raise RuntimeError("检查中原模型权重发生了变化。")
    np.testing.assert_array_equal(extended.condition_kernel.numpy(), np.zeros((FEATURE_WIDTH, 700), np.float32))
    np.testing.assert_allclose(model(batch).numpy(), baseline, rtol=1e-6, atol=1e-6)
    periodic = raw.astype(np.float64)
    periodic[:, 1] += 2 * np.pi
    np.testing.assert_allclose(model(inputs_for(periodic, positions)).numpy(), baseline, rtol=1e-5, atol=1e-5)
    return {"original_features_preserved_at_zero_new_kernel": True,
            "wind_encoding_and_coordinate_rotation_checked": True,
            "all_thirteen_new_kernel_rows_have_gradients": True,
            "all_twelve_physical_input_paths_checked": True,
            "wind_direction_periodicity_checked": True,
            "temporary_check_updates_restored": True, "original_hidden_weights_unchanged": True}, batch


def build(args):
    components = tensorflow_components()
    tf, keras, *_ = components
    keras.utils.set_random_seed(1234)
    root = args.project_root.resolve()
    source = args.source or root / "OutputChange" / "prepared_9ms" / "original_frozen.keras"
    if not source.is_file():
        raise FileNotFoundError(f"未找到原模型：{source}\n需要之前已生成的prepared_9ms/original_frozen.keras。")
    print("Loading original frozen model:", source, flush=True)
    original = keras.models.load_model(str(source), compile=False)
    model, prefix, tail, extended = build_modified(original, components)
    print("Checking original weights, 13 kernel rows, 12 physical inputs and wind coordinates...", flush=True)
    checks, batch = numerical_checks(original, model, prefix, tail, extended, components)
    destination = unique_directory(args.output or root / "OutputChange" / "wind_iochanged_9ms")
    model.save(str(destination / "untrained.keras"))
    restored = keras.models.load_model(str(destination / "untrained.keras"), compile=False)
    if trainable_count(restored) != EXPECTED_TRAINABLE or retained_digest(restored) != retained_digest(model):
        raise RuntimeError("保存重载改变了冻结状态或原权重。")
    np.testing.assert_allclose(restored(batch).numpy(), model(batch).numpy(), rtol=1e-5, atol=1e-6)
    checks["save_reload_equal_and_freezing_preserved"] = True
    config_path = ensure_config(root)
    for name, columns in (("training_data_template.csv", INPUT_NAMES + OUTPUT_NAMES),
                          ("prediction_data_template.csv", INPUT_NAMES)):
        with (destination / name).open("w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle).writerow(columns)
    with (destination / "model_summary.txt").open("w", encoding="utf-8") as handle:
        model.summary(print_fn=lambda line: handle.write(line + "\n"))
    report = {"schema": SCHEMA, "status": "structure_checked_NOT_trained", "built_at": timestamp(),
              "source": str(source.resolve()), "tensorflow": tf.__version__, "tf_keras": keras.__version__,
              "physical_input_order": list(INPUT_NAMES), "encoded_feature_order": list(FEATURE_NAMES),
              "output_order": list(OUTPUT_NAMES), "control_units": SI_UNITS,
              "inputs": {"conditions_and_controls": [None, 12], "turbine_positions": [None, 3, 3]},
              "wind_direction_convention": DIRECTION_CONVENTION,
              "original_parameters": 3_090_200, "retained_original_hidden_parameters": 3_087_200,
              "new_input_trainable_parameters": 9100, "new_output_trainable_parameters": 18006,
              "total_trainable_parameters": trainable_count(model),
              "total_parameters_including_statistics": int(model.count_params()),
              "retained_original_sha256": retained_digest(model), "checks": checks,
              "config": str(config_path), "training_performed_on_real_data": False,
              "notes": ["All six original hidden branches are reused and frozen; no extra hidden network.",
                        "The physical interface has 12 SI-valued inputs; sin/cos expansion is inside the saved graph.",
                        "Fixed geometry is rotated into the flow-aligned source coordinates for each case.",
                        "Geometry transformation does not make a four-turbine 9m/s source physically valid for new cases.",
                        "These are new data-fitted outputs, without the original PDE residual loss.",
                        "No physical accuracy, dynamic wake response, or hardware speedup is established."]}
    write_json(destination / "build_report.json", report)
    print("[OK] Original hidden parameters retained and frozen: 3,087,200", flush=True)
    print("Physical input values: 12; encoded features: 13", flush=True)
    print("New input parameters: 9,100; new output parameters: 18,006", flush=True)
    print("Total trainable parameters: 27,106 (0.88% of original)", flush=True)
    print("[OK] Checks passed; temporary changes restored. Saved to:", destination, flush=True)
    print("Config for later real-data training:", config_path, flush=True)
    print("No project coordinates or training data were invented. No real-data training performed.", flush=True)


def resolve_bundle(root, provided):
    if provided:
        folder = provided.resolve()
    else:
        reports = list((root / "OutputChange").glob("wind_iochanged_9ms*/build_report.json"))
        if not reports:
            raise FileNotFoundError("请先运行python modify_pinn_wind_io.py。")
        folder = max(reports, key=lambda p: p.stat().st_mtime_ns).parent
    if read_json(folder / "build_report.json").get("schema") != SCHEMA:
        raise ValueError("这不是新版多风况模型目录；不能传入旧版iochanged_9ms。")
    return folder


def read_cases(path, require_targets):
    names = INPUT_NAMES + OUTPUT_NAMES if require_targets else INPUT_NAMES
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV需要唯一列名、逗号分隔的表头。")
        missing = [n for n in names if n not in reader.fieldnames]
        extra = [n for n in reader.fieldnames if n not in names]
        if missing or extra:
            raise ValueError(f"CSV表头不匹配。缺少：{missing}；额外：{extra}。请使用新版模板。")
        rows = []
        for line, row in enumerate(reader, 2):
            if None in row:
                raise ValueError(f"CSV第{line}行数值个数超过表头列数。")
            try:
                rows.append([float(row[n]) for n in names])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"CSV第{line}行有空白或非数值，不能填占位数。") from exc
    values = np.asarray(rows, dtype=np.float64)
    if not rows or not np.isfinite(values).all():
        raise ValueError("CSV不能为空，所有输入和标签须为有限数值。")
    raw = validated_cases(values[:, :INPUT_WIDTH])
    if require_targets:
        targets = values[:, INPUT_WIDTH:]
        if (targets[:, :3] < 0).any() or (targets[:, 3:] <= 0).any():
            raise ValueError("P标签须非负，单位W；Ueff须大于0，单位m/s。")
        return raw, targets
    return raw


def split_groups(cases, seed):
    _, group = np.unique(cases, axis=0, return_inverse=True)
    groups = np.arange(int(group.max()) + 1)
    if len(groups) < 5:
        raise ValueError("至少5组不同的完整12输入工况才可划分数据；这只是程序下限，不代表样本足够。")
    np.random.default_rng(seed).shuffle(groups)
    n_test = max(1, int(round(len(groups) * 0.2)))
    n_validation = max(1, int(round(len(groups) * 0.2)))
    selected = (groups[n_test + n_validation:], groups[n_test:n_test + n_validation], groups[:n_test])
    if len(selected[0]) < 2:
        raise ValueError("独立训练工况不足。")
    return tuple(np.flatnonzero(np.isin(group, part)) for part in selected)


def statistics(values):
    mean, std = np.mean(values, axis=0, dtype=np.float64), np.std(values, axis=0, dtype=np.float64)
    return mean.astype(np.float32), np.where(std <= 1e-8, 1.0, std).astype(np.float32)


def predict_batches(model, cases, positions, batch_size=32):
    return np.concatenate([model(inputs_for(cases[i:i + batch_size], positions), training=False).numpy()
                           for i in range(0, len(cases), batch_size)], axis=0)


def error_metrics(predictions, targets):
    error = predictions.astype(np.float64) - targets
    return {name: {"MAE": float(np.mean(np.abs(error[:, i]))),
                   "RMSE": float(np.sqrt(np.mean(error[:, i] ** 2))),
                   "unit": "W" if i < 3 else "m/s"} for i, name in enumerate(OUTPUT_NAMES)}


def direction_arc(angles):
    ordered = np.unique(np.mod(angles, 2 * np.pi))
    gaps = np.diff(np.r_[ordered, ordered[0] + 2 * np.pi])
    i = int(np.argmax(gaps))
    return {"start_rad": float(ordered[(i + 1) % len(ordered)]),
            "width_rad": float(2 * np.pi - gaps[i])}


def train(args):
    _, keras, *_ = tensorflow_components()
    keras.utils.set_random_seed(args.seed)
    root = args.project_root.resolve()
    bundle = resolve_bundle(root, args.bundle)
    config, positions = validate_config(args.config or root / "OutputChange" / "wind_project_config.json")
    raw, targets = read_cases(args.csv, require_targets=True)
    # Match the effective float32 graph inputs before grouping repeated cases.
    raw = validated_cases(inputs_for(raw, positions)["conditions_and_controls"])
    train_idx, validation_idx, test_idx = split_groups(raw, args.seed)
    with np.errstate(over="ignore"):
        targets = targets.astype(np.float32)
    if not np.isfinite(targets).all():
        raise ValueError("标签超出float32范围，请检查单位。")
    features = encoded_features(raw)
    # Identical encoded values must not leak across the three splits.
    _, encoded_group = np.unique(features.astype(np.float32), axis=0, return_inverse=True)
    if any(np.intersect1d(encoded_group[a], encoded_group[b]).size
           for a, b in ((train_idx, validation_idx), (train_idx, test_idx), (validation_idx, test_idx))):
        raise ValueError("编码后相同的工况跨越数据集划分，请检查角度精度或重复工况。")
    constants = [n for i, n in enumerate(INPUT_NAMES) if np.ptp(raw[train_idx, i]) <= 1e-8]
    if all(n in constants for n in CONTROL_NAMES):
        raise ValueError("训练部分九个控制量全不变，不能验证控制优化；需补充实际控制变化数据。")
    if constants:
        print("Not varied in training; their effects remain unvalidated:", ", ".join(constants), flush=True)
    model = keras.models.load_model(str(bundle / "untrained.keras"), compile=False)
    build_report = read_json(bundle / "build_report.json")
    original_hash = retained_digest(model)
    if original_hash != build_report["retained_original_sha256"] or trainable_count(model) != EXPECTED_TRAINABLE:
        raise RuntimeError("模型冻结或原权重校验不通过。")
    # Statistics use exactly the float32 encoding executed by the saved graph.
    train_features = model.get_layer("wind_features")(
        inputs_for(raw[train_idx], positions)["conditions_and_controls"]).numpy()
    x_mean, x_std = statistics(train_features)
    y_mean, y_std = statistics(targets[train_idx])
    model.get_layer("input_normalization").mean.assign(x_mean)
    model.get_layer("input_normalization").std.assign(x_std)
    model.get_layer("output_units").mean.assign(y_mean)
    model.get_layer("output_units").std.assign(y_std)
    view = keras.Model(model.inputs, model.get_layer("normalized_predictions").output)
    if trainable_count(view) != EXPECTED_TRAINABLE:
        raise RuntimeError("训练视图参数集合不匹配。")
    view.compile(optimizer=keras.optimizers.Adam(learning_rate=args.learning_rate, clipnorm=1), loss="mse")
    callback = keras.callbacks.EarlyStopping(monitor="val_loss", patience=args.patience,
                                             min_delta=1e-6, restore_best_weights=True)
    print("Training ONLY the new 27,106 parameters; original hidden weights remain frozen.", flush=True)
    print("Train/validation/test cases:", len(train_idx), len(validation_idx), len(test_idx), flush=True)
    print("Label source:", args.label_source, "(independent physical validation still required)", flush=True)
    history = view.fit(
        inputs_for(raw[train_idx], positions), (targets[train_idx] - y_mean) / y_std,
        validation_data=(inputs_for(raw[validation_idx], positions), (targets[validation_idx] - y_mean) / y_std),
        epochs=args.epochs, batch_size=args.batch_size, callbacks=[callback], verbose=2)
    if retained_digest(model) != original_hash:
        raise RuntimeError("训练改变了原权重，拒绝导出。")
    predictions = predict_batches(model, raw[test_idx], positions)
    if not np.isfinite(predictions).all():
        raise RuntimeError("测试输出含NaN/Inf，拒绝导出。")
    destination = unique_directory(bundle / f"training_{timestamp()}")
    model.save(str(destination / "trained.keras"))
    restored = keras.models.load_model(str(destination / "trained.keras"), compile=False)
    if retained_digest(restored) != original_hash or trainable_count(restored) != EXPECTED_TRAINABLE:
        raise RuntimeError("训练模型保存重载后原权重或冻结状态不一致。")
    np.testing.assert_allclose(predictions, predict_batches(restored, raw[test_idx], positions), rtol=1e-5, atol=1e-4)
    write_json(destination / "config_used.json", config)
    report = {"schema": SCHEMA, "status": "trained_requires_independent_physical_validation",
              "trained_at": timestamp(), "label_source": args.label_source,
              "csv": str(args.csv.resolve()), "csv_sha256": hashlib.sha256(args.csv.read_bytes()).hexdigest(),
              "config": config, "physical_input_order": list(INPUT_NAMES),
              "encoded_feature_order": list(FEATURE_NAMES), "output_order": list(OUTPUT_NAMES),
              "output_units": ["W", "W", "W", "m/s", "m/s", "m/s"],
              "trainable_parameters": trainable_count(model), "original_parameters_unchanged": True,
              "retained_original_sha256": original_hash, "epochs_completed": len(history.epoch),
              "seed": args.seed, "train_rows_zero_based": train_idx.tolist(),
              "validation_rows_zero_based": validation_idx.tolist(), "test_rows_zero_based": test_idx.tolist(),
              "training_input_min": raw[train_idx].min(axis=0).tolist(),
              "training_input_max": raw[train_idx].max(axis=0).tolist(),
              "training_direction_covering_arc": direction_arc(raw[train_idx, 1]),
              "constant_inputs_in_training": constants,
              "training_feature_mean": x_mean.tolist(), "training_feature_std": x_std.tolist(),
              "training_output_mean": y_mean.tolist(), "training_output_std": y_std.tolist(),
              "test_metrics": error_metrics(predictions, targets[test_idx]),
              "negative_test_output_count": int((predictions < 0).sum()),
              "history": {k: [float(v) for v in values] for k, values in history.history.items()},
              "notes": ["Scaling uses training cases only; identical complete input cases share one split.",
                        "Random held-out errors do not certify generalization to unseen wind regimes or all control combinations.",
                        "Synthetic test labels cannot establish physical control accuracy.",
                        "Outputs are quasi-steady/case means, not a dynamic wake propagation simulation.",
                        "No original PDE residual loss; linear outputs do not enforce nonnegativity."]}
    write_json(destination / "training_report.json", report)
    print("[OK] Trained model saved:", destination, flush=True)
    print("[OK] Original hidden weights unchanged; save/reload passed.", flush=True)
    print("Held-out errors:", json.dumps(report["test_metrics"], ensure_ascii=False), flush=True)


def predict(args):
    _, keras, *_ = tensorflow_components()
    root = args.project_root.resolve()
    if args.run:
        run = args.run.resolve()
    else:
        bundle = resolve_bundle(root, args.bundle)
        reports = list(bundle.glob("training_*/training_report.json"))
        if not reports:
            raise FileNotFoundError("还没有训练模型；结构构建成功不等于已经学会预测。")
        run = max(reports, key=lambda p: p.stat().st_mtime_ns).parent
    report = read_json(run / "training_report.json")
    if report.get("schema") != SCHEMA:
        raise ValueError("不能用此入口读取旧版九输入模型。")
    config, positions = validate_config(run / "config_used.json")
    if config != report.get("config"):
        raise ValueError("训练配置快照与报告不一致；不能通过改机位或单位让原模型适配新条件。")
    raw = validated_cases([args.inputs]) if args.inputs is not None else read_cases(args.csv, False)
    outside = (raw < np.asarray(report["training_input_min"]) - 1e-7) | (
        raw > np.asarray(report["training_input_max"]) + 1e-7)
    arc = report["training_direction_covering_arc"]
    delta = np.mod(raw[:, 1] - arc["start_rad"], 2 * np.pi)
    outside[:, 1] = (delta > arc["width_rad"] + 1e-6) & (delta < 2 * np.pi - 1e-6)
    if outside.any():
        print("Outside training range (extrapolation):",
              ", ".join(n for i, n in enumerate(INPUT_NAMES) if outside[:, i].any()), flush=True)
    if report.get("label_source") == "synthetic_test":
        print("TEST LABELS ONLY: this run does not establish physical prediction accuracy.", flush=True)
    model = keras.models.load_model(str(run / "trained.keras"), compile=False)
    if retained_digest(model) != report["retained_original_sha256"] or trainable_count(model) != EXPECTED_TRAINABLE:
        raise RuntimeError("训练模型校验未通过。")
    prediction = predict_batches(model, raw, positions)
    if not np.isfinite(prediction).all():
        raise RuntimeError("预测产生NaN/Inf。")
    if (prediction < 0).any():
        print("Negative outputs detected; review the data and physical accuracy.", flush=True)
    if args.output:
        output = args.output.resolve()
        if output.exists():
            raise FileExistsError(f"输出文件已存在，请换新路径：{output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(INPUT_NAMES + OUTPUT_NAMES)
            writer.writerows(np.column_stack((raw, prediction)).tolist())
        print("Predictions saved:", output, flush=True)
    else:
        for row in prediction:
            print(json.dumps(dict(zip(OUTPUT_NAMES, map(float, row))), ensure_ascii=False))
    print("Output units: W, W, W, m/s, m/s, m/s.", flush=True)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command")
    builder = commands.add_parser("build", help="Build/check only; no data fitting")
    builder.add_argument("--project-root", type=Path, default=ROOT)
    builder.add_argument("--source", type=Path)
    builder.add_argument("--output", type=Path)
    trainer = commands.add_parser("train", help="Fit only new parameters with labeled data")
    trainer.add_argument("--project-root", type=Path, default=ROOT)
    trainer.add_argument("--bundle", type=Path)
    trainer.add_argument("--config", type=Path)
    trainer.add_argument("--csv", type=Path, required=True)
    trainer.add_argument("--label-source", choices=("simulation", "experiment", "synthetic_test"), required=True)
    trainer.add_argument("--epochs", type=int, default=200)
    trainer.add_argument("--batch-size", type=int, default=16)
    trainer.add_argument("--learning-rate", type=float, default=1e-4)
    trainer.add_argument("--patience", type=int, default=30)
    trainer.add_argument("--seed", type=int, default=1234)
    predictor = commands.add_parser("predict", help="Use a trained run with its saved fixed geometry")
    predictor.add_argument("--project-root", type=Path, default=ROOT)
    choose = predictor.add_mutually_exclusive_group()
    choose.add_argument("--bundle", type=Path)
    choose.add_argument("--run", type=Path)
    data = predictor.add_mutually_exclusive_group(required=True)
    data.add_argument("--inputs", nargs=INPUT_WIDTH, type=float, metavar="VALUE")
    data.add_argument("--csv", type=Path)
    predictor.add_argument("--output", type=Path)
    return result


def main():
    args = parser().parse_args(sys.argv[1:] or ["build"])
    if args.command is None:
        parser().print_help()
        return 0
    try:
        if args.command == "train" and (args.epochs < 1 or args.batch_size < 1 or args.patience < 0
                                        or not np.isfinite(args.learning_rate) or args.learning_rate <= 0):
            raise ValueError("训练参数须合法：轮数和batch为正，学习率为有限正数，patience非负。")
        {"build": build, "train": train, "predict": predict}[args.command](args)
    except Exception:
        print("\n[ERROR] 操作未完成，请保留末尾完整日志。", file=sys.stderr)
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
