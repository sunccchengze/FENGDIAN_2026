"""候选2：高斯过程回归（RBF+白噪声核，每台机独立，farm=sum）"""

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel


class GPRSurrogate:
    """GPR 功率代理：3 台机各一个 GPR（低维小数据友好），farm=Σturbine"""

    name = "gpr"

    def __init__(self, seed: int = 42, length_scale: float = 1.0, alpha: float = 1e-6):
        self.seed = seed
        self.length_scale = length_scale
        self.alpha = alpha
        self.models = []

    def fit(self, X: np.ndarray, y: np.ndarray) -> "GPRSurrogate":
        for i in range(3):
            kernel = 1.0 * RBF(length_scale=self.length_scale) + WhiteKernel(noise_level=self.alpha)
            gpr = GaussianProcessRegressor(kernel=kernel, alpha=0.0, normalize_y=True, random_state=self.seed)
            gpr.fit(X, y[:, i])
            self.models.append(gpr)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        t = np.column_stack([m.predict(X, return_std=False) for m in self.models])
        farm = t.sum(axis=1, keepdims=True)
        return np.concatenate([t, farm], axis=1)

    def predict_with_std(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """返回 (功率均值 (N,3), 功率标准差 (N,3))，供不确定性分析"""
        means, stds = [], []
        for m in self.models:
            mu, sd = m.predict(X, return_std=True)
            means.append(mu)
            stds.append(sd)
        return np.column_stack(means), np.column_stack(stds)
