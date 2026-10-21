"""候选4：两阶段模型（零功率分类 + 正功率回归），训练用含零行全量数据"""

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
import xgboost as xgb


class TwoStageSurrogate:
    """每台机：GBDT 分类器判断功率>0，XGBoost 回归器预测正功率；farm=Σturbine。
    与其它候选不同：fit 输入可含零功率行（用 y 为 0 判定发电状态）。"""

    name = "two_stage"

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.clfs = []
        self.regs = []

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TwoStageSurrogate":
        for i in range(3):
            y_i = y[:, i]
            pos = y_i > 0
            if len(np.unique(pos)) < 2:
                # 该 fold 内此风机恒为正（无零功率样本），分类器恒输出 1
                clf = None
            else:
                clf = GradientBoostingClassifier(random_state=self.seed)
                clf.fit(X, pos.astype(int))
            reg = xgb.XGBRegressor(
                objective="reg:squarederror", n_estimators=500, max_depth=6,
                learning_rate=0.05, subsample=0.9, colsample_bytree=0.9,
                random_state=self.seed, n_jobs=-1,
            )
            reg.fit(X[pos], y_i[pos])
            self.clfs.append(clf)
            self.regs.append(reg)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        t = np.zeros((X.shape[0], 3))
        for i in range(3):
            if self.clfs[i] is None:
                prob = np.ones(X.shape[0])
            else:
                prob = self.clfs[i].predict_proba(X)[:, 1]
            pred_pos = self.regs[i].predict(X)
            t[:, i] = np.where(prob > 0.5, pred_pos, 0.0)
        farm = t.sum(axis=1, keepdims=True)
        return np.concatenate([t, farm], axis=1)
