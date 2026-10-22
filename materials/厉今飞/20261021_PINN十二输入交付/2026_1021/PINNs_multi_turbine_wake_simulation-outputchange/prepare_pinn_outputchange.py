"""Load and freeze the author's original PINN without running its training loop.

Place this file in the newly extracted project root and run it in pinn-multi.
This prepares the existing pretrained backbone. It does NOT yet construct a
nine-control-input power predictor or train replacement output layers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

# Only this preparation process is CPU-only; the conda environment is unchanged.
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

ORIGINAL_OUTPUTS = (
    "output_u", "output_v", "output_w", "output_p", "output_k", "output_eps"
)
TARGET_OUTPUTS = ("P1", "P2", "P3", "Ueff1", "Ueff2", "Ueff3")


def weights_digest(model):
    digest = hashlib.sha256()
    # Traversal order may change after trainable flags change, so sort by name.
    for weight in sorted(model.weights, key=lambda item: item.name):
        array = weight.numpy()
        digest.update(weight.name.encode("utf-8"))
        digest.update(str(array.shape).encode("ascii"))
        digest.update(array.tobytes())
    return digest.hexdigest()


def count_trainable(model):
    return sum(int(weight.shape.num_elements()) for weight in model.trainable_weights)


def prepare(args):
    import numpy as np
    import tensorflow as tf

    print("Python:", sys.version.split()[0], flush=True)
    print("TensorFlow:", tf.__version__, flush=True)
    if tf.__version__.split(".")[:2] != ["2", "16"]:
        raise RuntimeError(
            "This script is prepared for TensorFlow 2.16.x. "
            "Send the displayed version before changing the environment."
        )
    tf.config.threading.set_intra_op_parallelism_threads(4)
    tf.config.threading.set_inter_op_parallelism_threads(2)
    try:
        import tf_keras as keras
    except ImportError as exc:
        raise RuntimeError(
            'Run in pinn-multi: python -m pip install "tf-keras==2.16.0" --no-deps'
        ) from exc
    if keras.__version__.split(".")[:2] != ["2", "16"]:
        raise RuntimeError(
            "tf_keras must be 2.16.x for this TensorFlow version; "
            f"found {keras.__version__}."
        )
    print("TF-Keras:", keras.__version__, flush=True)

    root = args.project_root.resolve()
    source = root / "Rectangular_grid" / "Pre_trained" / f"{args.velocity}ms"
    required = (
        source / "saved_model.pb",
        source / "keras_metadata.pb",
        source / "variables" / "variables.index",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if not list((source / "variables").glob("variables.data-*")):
        missing.append(str(source / "variables" / "variables.data-*"))
    if missing:
        raise FileNotFoundError("Pretrained files missing:\n" + "\n".join(missing))
    print("Source:", source, flush=True)
    print("Loading the original pretrained model; no training is started.", flush=True)
    model = keras.models.load_model(str(source), compile=False)

    if len(model.inputs) != 3 or set(model.output_names) != set(ORIGINAL_OUTPUTS):
        raise RuntimeError(
            "The loaded model does not match the expected original PINN. "
            f"Inputs={len(model.inputs)}, outputs={model.output_names}"
        )
    for tensor in model.inputs:
        if tuple(tensor.shape.as_list()) != (None, 1):
            raise RuntimeError(f"Unexpected input shape: {tensor.shape}")
    total = int(model.count_params())
    if total != 3_090_200:
        raise RuntimeError(
            f"Expected the author's 3,090,200-parameter model; found {total:,}. "
            "Send this log so the actual architecture can be checked."
        )
    print("Original parameter count:", f"{total:,}", flush=True)

    # Four in-domain locations are a serialization check, not CFD validation.
    points = np.asarray(
        [[-120.4, -105.35, 35.0], [0.0, 0.0, 35.0],
         [210.7, 105.35, 35.0], [300.0, 0.0, 35.0]],
        dtype=np.float32,
    )
    probe = [tf.convert_to_tensor(points[:, i:i + 1]) for i in range(3)]
    before = [value.numpy() for value in model(probe, training=False)]
    if not all(np.isfinite(value).all() for value in before):
        raise RuntimeError("The original model produced NaN or infinity at check points.")
    original_digest = weights_digest(model)

    # Reuse the exact original layers and weights. No layer is reinitialized.
    model.trainable = False
    after = [value.numpy() for value in model(probe, training=False)]
    for lhs, rhs in zip(before, after):
        np.testing.assert_allclose(lhs, rhs, rtol=1e-6, atol=1e-6)
    if weights_digest(model) != original_digest:
        raise RuntimeError("Original weights changed during preparation.")
    if count_trainable(model) != 0:
        raise RuntimeError("Freezing failed: original trainable parameters remain.")
    print("Frozen original trainable parameters: 0", flush=True)

    # A view of the six existing 500-unit branches before their original heads.
    # These tensors reuse the original graph; this is not an independent network.
    feature_tensors = [model.get_layer(name).input for name in ORIGINAL_OUTPUTS]
    if any(int(tensor.shape[-1]) != 500 for tensor in feature_tensors):
        raise RuntimeError("The original branch feature widths are not all 500.")
    features = keras.Model(
        model.inputs, feature_tensors, name="original_pinn_frozen_features"
    )
    features.trainable = False
    feature_shapes = [list(value.shape) for value in features(probe, training=False)]
    if int(features.count_params()) != 3_087_200:
        raise RuntimeError("Unexpected parameter count in the original hidden layers.")
    print("Original branch feature shapes:", feature_shapes, flush=True)

    # A new directory makes reruns safe and leaves the extracted source untouched.
    destination = root / "OutputChange" / f"prepared_{args.velocity}ms"
    if destination.exists():
        index = 2
        while destination.with_name(f"prepared_{args.velocity}ms_{index}").exists():
            index += 1
        destination = destination.with_name(f"prepared_{args.velocity}ms_{index}")
    destination.mkdir(parents=True, exist_ok=False)
    frozen_path = destination / "original_frozen.keras"
    feature_path = destination / "original_frozen_features.keras"
    model.save(str(frozen_path))
    features.save(str(feature_path))

    # Check that saving and reloading preserved both predictions and freezing.
    restored = keras.models.load_model(str(frozen_path), compile=False)
    if count_trainable(restored) != 0 or weights_digest(restored) != original_digest:
        raise RuntimeError("Reloaded original model did not preserve weights/freezing.")
    for lhs, rhs in zip(before, restored(probe, training=False)):
        np.testing.assert_allclose(lhs, rhs.numpy(), rtol=1e-5, atol=1e-6)
    restored_features = keras.models.load_model(str(feature_path), compile=False)
    if count_trainable(restored_features) != 0:
        raise RuntimeError("Reloaded original features are not frozen.")
    for lhs, rhs in zip(features(probe, training=False), restored_features(probe, training=False)):
        np.testing.assert_allclose(lhs.numpy(), rhs.numpy(), rtol=1e-5, atol=1e-6)

    report = {
        "status": "original_pretrained_backbone_frozen_and_verified",
        "tensorflow": tf.__version__, "tf_keras": keras.__version__,
        "source_model": str(source),
        "source_saved_model_sha256": hashlib.sha256(
            (source / "saved_model.pb").read_bytes()).hexdigest(),
        "original_weights_sha256": original_digest,
        "original_parameters": total,
        "frozen_backbone_parameters": int(features.count_params()),
        "frozen_backbone_trainable_parameters": count_trainable(features),
        "original_input_names": [tensor.name for tensor in model.inputs],
        "original_output_names": list(model.output_names),
        "feature_order": list(ORIGINAL_OUTPUTS),
        "feature_shapes_for_four_check_points": feature_shapes,
        "intended_future_outputs": list(TARGET_OUTPUTS),
        "control_inputs_connected": False,
        "replacement_outputs_built": False,
        "training_performed": False,
        "checks": "weight equality, finite predictions, save/reload equality, freezing",
        "scope": (
            "Only the original coordinate-to-flow network is prepared. "
            "Nine control variables and condition-level power/effective-speed "
            "outputs require a separate input/readout design. This is not yet "
            "a trained power predictor or a validated nine-variable optimizer."
        ),
    }
    (destination / "preparation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("[OK] Original weights loaded, frozen, exported and checked.", flush=True)
    print("Saved to:", destination, flush=True)
    print("This is the frozen original backbone; controls/new outputs are not connected yet.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--velocity", type=int, choices=(7, 8, 9, 10, 11), default=9)
    args = parser.parse_args()
    try:
        prepare(args)
    except Exception:
        print("\n[ERROR] Preparation failed. Send the last 30 lines of this log.", file=sys.stderr)
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
