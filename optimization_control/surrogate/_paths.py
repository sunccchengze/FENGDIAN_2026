"""仓库内路径解析：替代旧私有工作区的 `.\\data\\teammates\\...` 硬编码。

旧布局（作者本机）与本仓库布局的对应关系：
- data/teammates/yuan_fuda_floris/raw/{gch,cc}/training_data_*.csv
  → materials/袁夫达/20260808_FLORIS数据生成/extracted/output_{gch,cc}/training_data_*.csv
- data/teammates/li_jinfei_nn/models/{gch,cc}/wind_farm_power_model.keras
  → materials/厉今飞/20260808_功率预测神经网络基线/output_{gch,cc}/wind_farm_results/wind_farm_power_model.keras
- data/teammates/li_jinfei_nn/results/{gch,cc}/*.csv
  → 同上目录的 wind_farm_results/*.csv

找不到时抛 FileNotFoundError 并列出所有候选路径，不静默退回。
可用环境变量 FENGDIAN_YUAN_DATA_DIR / FENGDIAN_LI_NN_DIR 指向自备副本。
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _first_existing(candidates, what):
    for cand in candidates:
        if cand.exists():
            return str(cand)
    raise FileNotFoundError(
        f"{what} not found; tried: " + "; ".join(str(c) for c in candidates)
    )


def yuan_training_csv(model_key: str) -> str:
    candidates = []
    env = os.environ.get("FENGDIAN_YUAN_DATA_DIR")
    if env:
        candidates.append(Path(env) / f"training_data_{model_key}.csv")
    candidates += [
        REPO_ROOT / "materials" / "袁夫达" / "20260808_FLORIS数据生成" / "extracted"
        / f"output_{model_key}" / f"training_data_{model_key}.csv",
        REPO_ROOT / "optimization_control" / "project_context" / "data" / "teammates"
        / "yuan_fuda_floris" / "raw" / model_key / f"training_data_{model_key}.csv",
    ]
    return _first_existing(candidates, f"袁夫达 FLORIS {model_key} training csv")


def _li_dir(model_key: str) -> Path:
    env = os.environ.get("FENGDIAN_LI_NN_DIR")
    if env:
        return Path(env)
    return (
        REPO_ROOT / "materials" / "厉今飞" / "20260808_功率预测神经网络基线"
        / f"output_{model_key}" / "wind_farm_results"
    )


def li_model_path(model_key: str) -> str:
    return _first_existing(
        [_li_dir(model_key) / "wind_farm_power_model.keras"],
        f"厉今飞 MLP {model_key} model",
    )


def li_results_csv(model_key: str, name: str) -> str:
    return _first_existing(
        [_li_dir(model_key) / name],
        f"厉今飞 MLP {model_key} {name}",
    )


def repo_path(*parts: str) -> str:
    return str(REPO_ROOT.joinpath(*parts))
