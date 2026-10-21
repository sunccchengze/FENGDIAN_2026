"""Keras .keras 模型 numpy 前向推理（不依赖 TensorFlow，仅 numpy+h5py）"""

import json
import os
import tempfile
import zipfile

import h5py
import numpy as np


OUTPUT_SCALES_W = np.array([5_000_000.0, 5_000_000.0, 5_000_000.0, 15_000_000.0], dtype=np.float32)


def _silu(x: np.ndarray) -> np.ndarray:
    """Swish 激活: x * sigmoid(x)"""
    return x * (1.0 / (1.0 + np.exp(-x)))


class KerasMLPForward:
    """从 .keras (Keras3 zip 格式) 加载权重，numpy 前向计算。
    结构: Input(6) -> Normalization -> Dense(64,swish) -> Dense(128,swish)
          -> Dense(64,swish) -> Dense(3,sigmoid) -> Dense(3->1, linear) -> concat(4)
    """

    def __init__(self, keras_path: str):
        self.keras_path = keras_path
        self._load()

    def _load(self):
        with zipfile.ZipFile(self.keras_path) as z:
            cfg = json.loads(z.read("config.json"))
            tmp = os.path.join(tempfile.gettempdir(), "wind_read_model.weights.h5")
            with open(tmp, "wb") as f:
                f.write(z.read("model.weights.h5"))
        with h5py.File(tmp, "r") as h:
            self.mean = h["layers/normalization/vars/0"][:].astype(np.float32)
            self.var = h["layers/normalization/vars/1"][:].astype(np.float32)
            self.w1 = h["layers/dense/vars/0"][:].astype(np.float32)
            self.b1 = h["layers/dense/vars/1"][:].astype(np.float32)
            self.w2 = h["layers/dense_1/vars/0"][:].astype(np.float32)
            self.b2 = h["layers/dense_1/vars/1"][:].astype(np.float32)
            self.w3 = h["layers/dense_2/vars/0"][:].astype(np.float32)
            self.b3 = h["layers/dense_2/vars/1"][:].astype(np.float32)
            self.w4 = h["layers/dense_3/vars/0"][:].astype(np.float32)
            self.b4 = h["layers/dense_3/vars/1"][:].astype(np.float32)
            self.w5 = h["layers/dense_4/vars/0"][:].astype(np.float32)  # (3,1) farm 层
        # Keras 3 Normalization 推理时此处 epsilon=0（count=0 时无 eps 路径），实测 eps=0 与 Keras 输出完全一致
        self.eps = 0.0

    def predict_fraction(self, x: np.ndarray) -> np.ndarray:
        """输入 6 特征 (N,6)，输出归一化分数 (N,4): [t1,t2,t3,farm] ∈ ~[0,1]"""
        x = np.asarray(x, dtype=np.float32)
        h = (x - self.mean) / np.sqrt(self.var + self.eps)
        h = _silu(h @ self.w1 + self.b1)
        h = _silu(h @ self.w2 + self.b2)
        h = _silu(h @ self.w3 + self.b3)
        t = 1.0 / (1.0 + np.exp(-(h @ self.w4 + self.b4)))  # (N,3) sigmoid
        farm = t @ self.w5  # (N,1) farm 分数 = (t1+t2+t3)/3
        return np.concatenate([t, farm], axis=1)

    def predict_w(self, x: np.ndarray) -> np.ndarray:
        """输入 6 特征，输出功率 W (N,4): [t1,t2,t3,farm]"""
        return self.predict_fraction(x) * OUTPUT_SCALES_W
