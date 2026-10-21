"""候选1：XGBoost 树模型（每台机独立回归，farm=sum 守恒）"""

import numpy as np
import xgboost as xgb


class XGBSurrogate:
    """XGBoost 功率代理：3 台机各一个 XGBRegressor，farm=Σturbine"""

    name = "xgb"

    def __init__(self, seed: int = 42, params: dict | None = None):
        defaults = dict(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            min_child_weight=5,
            random_state=seed,
            n_jobs=-1,
        )
        if params:
            defaults.update(params)
        self.params = defaults
        self.models = [xgb.XGBRegressor(objective="reg:squarederror", **defaults) for _ in range(3)]

    def fit(self, X: np.ndarray, y: np.ndarray) -> "XGBSurrogate":
        """y: (N,4) 功率 W，只取前 3 列训练，farm 由求和得到"""
        for i, m in enumerate(self.models):
            m.fit(X, y[:, i])
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """返回 (N,4): [t1,t2,t3,farm] 单位 W"""
        t = np.column_stack([m.predict(X) for m in self.models])
        farm = t.sum(axis=1, keepdims=True)
        return np.concatenate([t, farm], axis=1)
