"""候选3：改进 MLP（扩展特征 + 多任务 + 功率守恒求和层，Keras）"""

import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
import numpy as np
import keras
from keras import layers, regularizers

from data_loader import make_features


OUTPUT_SCALES = np.array([5e6, 5e6, 5e6], dtype=np.float32)


def _extend_features(X6: np.ndarray) -> np.ndarray:
    """6 特征 -> 9 特征: 追加 sin3θ, cos3θ, U³（物理主项）"""
    u = X6[:, 0:1]
    s1, c1 = X6[:, 2:3], X6[:, 3:4]
    # sin3θ = 3s1 - 4s1^3 ; cos3θ = 4c1^3 - 3c1
    s3 = 3 * s1 - 4 * s1**3
    c3 = 4 * c1**3 - 3 * c1
    return np.concatenate([X6, s3, c3, u**3], axis=1).astype(np.float32)


class MLPv2Surrogate:
    """改进 MLP：扩展特征(9) + 归一化 + 64-128-64 Swish + 3 输出 Sigmoid，farm=Σturbine"""

    name = "mlp_v2"

    def __init__(self, seed: int = 42, epochs: int = 300, lr: float = 1e-3, l2: float = 1e-4, hidden: tuple = (64, 128, 64)):
        self.seed = seed
        self.epochs = epochs
        self.lr = lr
        self.l2 = l2
        self.hidden = hidden
        self.model = None
        self.mean = None
        self.std = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "MLPv2Surrogate":
        X9 = _extend_features(X)
        self.mean = X9.mean(axis=0, keepdims=True).astype(np.float32)
        self.std = X9.std(axis=0, keepdims=True).astype(np.float32) + 1e-8
        Xn = ((X9 - self.mean) / self.std).astype(np.float32)
        yf = (y[:, :3] / OUTPUT_SCALES).astype(np.float32)  # 0~1

        keras.utils.set_random_seed(self.seed)
        inp = keras.Input(shape=(9,), name="features_9d")
        h = inp
        for units in self.hidden:
            h = layers.Dense(units, activation="silu", kernel_regularizer=regularizers.L2(self.l2))(h)
        out = layers.Dense(3, activation="sigmoid", name="turbine_fraction")(h)
        model = keras.Model(inputs=inp, outputs=out, name="mlp_v2")
        model.compile(optimizer=keras.optimizers.Adam(learning_rate=self.lr), loss="mse")
        callbacks = [
            keras.callbacks.EarlyStopping(monitor="loss", patience=50, restore_best_weights=True),
            keras.callbacks.ReduceLROnPlateau(monitor="loss", factor=0.5, patience=20, min_lr=1e-5),
        ]
        model.fit(Xn, yf, epochs=self.epochs, batch_size=64, verbose=0, callbacks=callbacks)
        self.model = model
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        X9 = _extend_features(X)
        Xn = ((X9 - self.mean) / self.std).astype(np.float32)
        t = self.model.predict(Xn, verbose=0) * OUTPUT_SCALES
        farm = t.sum(axis=1, keepdims=True)
        return np.concatenate([t, farm], axis=1)
