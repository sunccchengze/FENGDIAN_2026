# pinn/ 路径约定（本目录只有说明，代码不在这里）

2026-10-22 的多份实验配置（`optimization_control/experiments/20261022_*/config.yaml`）
把队友 PINN 交付写为仓库根相对路径：

```yaml
script: pinn/2026_1021/PINNs_multi_turbine_wake_simulation-outputchange/modify_pinn_wind_io.py
```

但 `pinn/` 目录从未入库，所以这些配置在本仓库原样检出后跑不通（审计 AUD-05）。
实际交付位置（内容与配置钉扎的 `script_sha256` 已核验一致）：

| 配置里写的路径 | 仓库内实际位置 |
|---|---|
| `pinn/2026_1021/PINNs_multi_turbine_wake_simulation-outputchange/...` | `materials/厉今飞/20261021_PINN十二输入交付/2026_1021/PINNs_multi_turbine_wake_simulation-outputchange/...` |
| `run_dir: optimization_control/experiments/20261022_wind_pinn_integration/model` | 同名目录已入库（含 `config_used.json`、`training_report.json`），但 **`trained.keras` 不在 git 里**，在 Release `intake-2026-10-22` 的 `_20261022.zip` 内（ADR-2026-003 大文件口径） |

## 解析规则（已代码化）

`optimization_control/environments/teammate_pinn_backend.py` 与
`wind_pinn_backend.py` 的 `create_predictor` 现经 `_resolve_repo_path()` 解析
`run_dir` / `script`：

1. 路径本身存在 → 直接用；
2. 否则按仓库根拼接再试；
3. 仍不存在且以 `pinn/<版本>/` 开头 → 映射到
   `materials/厉今飞/20261021_PINN十二输入交付/<版本>/...`；
4. 都找不到 → 返回原路径，由既有完整性/哈希校验报出明确缺失（不静默降级）。

## 复现实验前还要做的事

1. 从 Release 下载并校验大包，把 `trained.keras` 放回
   `optimization_control/experiments/20261022_wind_pinn_integration/model/`
   （校验方法见 `materials/集体/交付收取/20261022_三机优化控制与中期答辩/RELEASE_ASSETS.sha256`）；
2. 按 `optimization_control/requirements.txt` 建环境（文件头注释注明了
   `torch==2.13.0+cpu` 所需的 PyTorch CPU 索引）；
3. 从**仓库根**运行（测试与工作流都按仓库根相对路径设计）。

> 注意科学口径：2026_1021 新输入的训练标签为合成标签，PINN 精度结论待真实/CFD
> 数据复核，见审计 AUD-08 与 `docs/project/WORKLIST.md`。路径修通不等于结论成立。
