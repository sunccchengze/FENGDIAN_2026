# 大创项目风电 — 文件框架说明

> 本仓库是「融合数据-物理驱动的风电流场感知与智能调控研究」的代码与协作工作区。
> 规范文档：`CLAUDE.md`（项目详情）+ `AGENTS.md`（Codex 协作规则）。

## 当前状态

2026-10-22：[随机入口驱动的训练与独立评估](../../../../optimization_control/maddpg_wind_farm/RANDOM_WIND_TRAINING.md)完成。
已有生成器逐回合提供入口，RL学pitch、yaw/转速共用后台调度；三流49152步，常规测试449.72±40.11 kW，P552.37、PI477.54。
129项测试及完整回放通过；验证精度门槛未达，按协议停止增加权限。慢变与低风压力场仍有不足，结论限于当前合成网络。

2026-10-22：[新版十二输入 PINN 联调](../../../../optimization_control/maddpg_wind_farm/WIND_PINN_INTEGRATION.md)完成。
队友新接口与随机入口、统一三通道执行器、MADDPG/P/PI 和保存回放跑通；新增参数使用合成标签拟合，冻结主体不变。
三个仅桨距单目标共 49152 步，低/中目标通过，高目标初始最优且终点退化，按协议停止后续学习。121 项模块测试通过；没有物理精度结论。

2026-10-07：[固定风况九输入迁移网络联调](../../../../optimization_control/maddpg_wind_farm/FIXED_PINN_DEMO.md)完成。
使用队友预训练主体与合成标签，仅训练新增参数；MADDPG 2048 步/897 次更新、统一 P/PI、保存恢复和完整回放通过。
当前实现包含实际迁移网络推理，但没有真实精度验证；短策略在 4.5 MW 目标退化，不报告总体优势。

2026-09-23 后续：[价值学习离线诊断](../../../../optimization_control/maddpg_wind_farm/VALUE_BASELINE_DIAGNOSTIC.md)已完成。
分层采样中仅约 0.1% 的不可达终止样本贡献超过 82% 的回放 TD 平方误差；奖励基线等价性检查通过。
这是下一项配对训练的依据，尚无新策略性能结论；优化侧待办见 `optimization_control/TASKFLOW.md`。

2026-09-23 最新结果：[功率可达性、误差分解与采样干预](../../../../optimization_control/maddpg_wind_farm/REACHABILITY_TRACKING.md)完成。
24 点诊断、两组×三种子×16384 步、新验证/测试各 27 场，98 项不同测试通过。
分层采样未通过：常规 RMSE 394.26→590.19 kW，低风压力剩余欠功率没有一致改善；保留原训练默认与失败结果。
固定可达目标仍有控制误差，低风高目标则同时包含不可达下限与策略剩余损失，不能全部归因于 Mock。

2026-09-22 最新实验：[混合风况退化诊断与逐因素对照](../../../../optimization_control/maddpg_wind_farm/MIXED_STABILITY.md)完成。
四配置、三个配对种子、196608 步；仅降低 Actor 学习率至 1e-4 的测试均值为 430.21 kW，相对原验证选中策略降低 8.93%。
91 项不同测试通过；后期退化门槛通过，但固定风精度完整门槛未通过，综合表现仍不及验证选参 PI（378.37 kW）。

2026-09-22 最新增量：[MADDPG 稳定训练与固定评估流程](../../../../optimization_control/maddpg_wind_farm/STABLE_TRAINING.md)已实现并完成 106496 步实验。
三个独立训练的验证选中策略测试 RMSE 为 412.15±30.49 kW，最终策略为 554.60±74.31 kW；85 项测试及精确恢复验证通过。
两个运行后期退化超过预设门槛，完整稳定收敛验收尚未通过；当前全部结果仍限于未标定 Mock。

2026-09-22 后续增量：三机随机入口、机舱朝向执行器、三通道传统基线、逐通道学习诊断已完成。
结果见 [诊断报告](../../../../optimization_control/maddpg_wind_farm/DIAGNOSTIC_REPORT.md)：随机风和同权限基线已经跑通，
当前 MADDPG 学习对奖励尺度敏感，短策略仍未优于 PI，不将问题全部归因于模拟 PINN。

2026-09-22 增量：三机 MADDPG 软件闭环、可变 PINN 输入/固定六维输出适配、固定/P/PI 对照已完成。
使用入口：[三机 MADDPG](../../../../optimization_control/maddpg_wind_farm/README.md)。70 项相关测试通过，
2048 步 Mock 短训练和恢复/回放验证通过；真实 PINN 接入与正式策略效果仍待验证。

- 对话恢复与完整审阅摘要：[`PROJECT_STATUS.md`](../PROJECT_STATUS.md)。
- 实时任务看板：[`optimization_control/TASKFLOW.md`](../../../../optimization_control/TASKFLOW.md)。
- 已完成 FLORIS/Keras 基线复现、XGBoost 代理模型优化、解析公式单机 PPO 预研和 T1-R 工程复核；新训练策略使用有界 tanh 高斯动作。
- 已完成 T2.5 优化核心组件与 T4a 可替换准静态软件闭环；使用说明见 [优化侧准静态可替换闭环使用指南](../../../../optimization_control/OPTIMIZATION_SHELL_GUIDE.md)。
- 当前默认 Plant 和风况均为联调 Mock，不能形成物理控制结论；旧“PPO 优于 P 控制约 34 倍”结论已撤回。
- T4b 真实 PINN 接入和正式多机控制仍阻塞于含 yaw/pitch/转速运行点的数据及合格准静态 PINN 交付。
- 当前实际环境是根目录 `.venv`（Python 3.12），依赖冻结见 `optimization_control/requirements.txt`。

## 目标目录结构

> 下列树是长期目标结构，不代表所有目录已经创建。实际文件以 `PROJECT_STATUS.md` 的索引为准。

```
大创项目风电/
├── AGENTS.md                    # Codex 协作规则
├── CLAUDE.md                    # 项目详情/行动指南（Claude Code 使用）
├── README.md                    # 本文件：框架总览 + 队友数据接收指南
├── GIT_WORKFLOW.md              # 工作区→暂存区→本地仓库管理规范
├── .gitattributes               # 文本行尾与二进制文件规则
├── tools/                       # 项目级只读管理工具
├── 大创申报书/                   # 申报材料（只读）
├── 文献/                        # 参考文献 PDF（只读）│
├── data/                        # 所有外部数据/模型（不入 git）
│   ├── teammates/               # 【队友交付区】按人分目录，见下方
│   │   ├── yuan_fuda_floris/    #   袁夫达：FLORIS 批处理数据（GCH/CC）
│   │   └── li_jinfei_nn/        #   厉今飞：神经网络代理模型（.keras，按 gch/cc 分）
│   ├── flow_snapshots/          #   仿真组：CFD 流场快照（未来交付）
│   └── proxy_models/            #   PINN 组：代理 PINN 模型（未来交付）
│
├── optimization_control/        # 【优化控制模块：我的主目录】
│   ├── OPTIMIZATION_SHELL_GUIDE.md # 准静态闭环用途、用法与 PINN 替换指南
│   ├── environments/            #   Plant 协议、Mock、准静态 Gymnasium 环境
│   ├── ppo_single_turbine/      #   单机 PPO 控制（train.py / eval.py / demo.py）
│   ├── maddpg_wind_farm/        #   三机 MADDPG、训练/评估入口、控制基准与配置
│   ├── surrogate/               #   代理模型优化（WORKLOG.md 工作记录 / PLAN.md / models/）
│   ├── utils/                   #   动作、执行器、参考、状态、观测与奖励组件
│   ├── tests/                   #   unittest 单元与接口契约测试
│   └── experiments/             #   实验输出（不入 git）：YYYYMMDD_简短描述/
│
├── notebooks/                   # 探索性分析（临时，沉淀后整理进 experiments/）
├── models/ppo/                  # PPO state_dict（当前已有，默认不入 git）
├── runs/                        # PPO 训练/演示输出（当前已有，默认不入 git）
├── simulation/                  # 仿真组：OpenFOAM 算例（未来）
├── pinn/                        # PINN 组：训练代码（未来）
├── visualization/              # 可视化组：数字孪生看板（未来）
└── integration/                # 系统集成（未来）
```

### 优化侧可执行闭环约定

三机 MADDPG 文件约定：`maddpg_wind_farm/` 下 `algorithm.py` 放算法与回放，
`workflow.py` 放训练/评估入口，`controllers.py` 放对照控制器，`configs/` 放 YAML；
`diagnostics.py` 放固定风况逐通道学习诊断，`inflow_workflow.py` 放入口风况统计与回放验收；
`benchmark.py` 放固定场景清单、校验和与统一指标，`stable_workflow.py` 放单因素筛查、
验证集选模、重复训练与一次性测试；实验协议放 `configs/stable_training.yaml`。
`verify_stable.py` 验证独立实验目录中的恢复、固定场景校验和及回放；
`STABLE_TRAINING.md` 记录流程、验收与本轮实验结果。
`mixed_stability.py` 放混合风况逐因素实验、传统基线验证选参及冻结测试，
`reachability.py` 放当前 Mock 的功率上界、可行运行点和误差分解，`tracking_study.py` 放基于诊断的单项改进实验；
协议存 `configs/tracking_study.yaml`，结论与复现入口存 `REACHABILITY_TRACKING.md`。沿用实验目录、命名与保留约定。
`value_baseline_diagnostic.py` 放不可达任务的离线奖励/价值信号审计，
`VALUE_BASELINE_DIAGNOSTIC.md` 放等价性条件、诊断结果与后续试验边界；不修改默认环境奖励或训练策略。
`retrospective.py` 放旧检查点的验证集退化诊断；协议存 `configs/mixed_stability.yaml`，
结果与因果解释边界记录于 `MIXED_STABILITY.md`。沿用现有实验目录命名、三类小文件和不自动清理约定。
场景轨迹和不可覆盖的分步检查点放实验目录；顶层 config.yaml/metrics.csv/summary.txt 记录
协议、种子派生、选模结果及运行状态，模型/轨迹不入 Git；不自动清理历史检查点。
`environments/farm_inflow.py` 复用单点 Kaimal 生成器，输出入口风速/方向/背景 TI，
不计算尾流、不生成三机独立有效风速。轨迹 CSV 及同名 JSON 放实验目录，保留校验和，
命名按场景与种子编号，已有输出不覆盖，清理须由用户授权。
`README.md` 记录接口、观测、动作、运行和验证方法。PINN 适配器与三机环境放
`environments/`，测试放现有 `tests/`。实验使用现有日期目录约定，输出不覆盖、不自动清理。

### 2026-10-07 PINN 交付接收约定

本次用户指定 `pinn/` 中的原交付为检查来源，原文件、模型和配置只读保留，不移动或代填机位。
优化侧 `maddpg_wind_farm/audit_handover.py` 保存交付检查入口，`PINN_HANDOVER_REVIEW.md` 保存结果与后续安排；
`environments/teammate_pinn_backend.py` 只负责现有十二维物理接口到队友九维控制接口的顺序、单位和固定工况检查。
检查与验证结果放现有 `experiments/YYYYMMDD_简短描述/`；未训练或缺元数据的交付不能进入真实模型训练。
未来经过验证的运行目录仍按原队友数据约定管理；本次不将队友完整代码、原数据或权重纳入优化任务提交。

### 固定风况九输入迁移网络联调（2026-10-07）

用户已授权使用合成数据训练联调副本：`maddpg_wind_farm/fixed_pinn_demo.py` 负责固定配置、
合成数据、新增参数训练、MADDPG 短训练和统一评估；`configs/fixed_pinn_demo.yaml` 保存协议，
`FIXED_PINN_DEMO.md` 保存结果与复现说明。`environments/teammate_pinn_backend.py` 的演示工厂
仅接受明确标记为合成数据训练的副本，正式交付检查与演示准入分别执行。
九个控制输入和六个输出保持不变，外层十二维中的风速/风向/TI 仅检查固定上下文。
队友 `pinn/` 原文件保持只读；合成 CSV/JSON、联调权重、分步输出保存于现有实验日期目录，
配置/指标/摘要纳入 Git，其余产物沿用忽略规则；已有输出不覆盖、不自动清理。
兼容依赖安装到 `.venv/pinn_tf216/`，由演示入口显式启用，不改全局环境或原依赖目录。

`optimization_control/environments/` 放 Plant 协议、适配器和 Gymnasium 环境；
`optimization_control/utils/` 放动作映射、执行器、参考功率、状态与奖励组件；
`optimization_control/tests/` 放单元测试和接口契约测试。`Mock*` 仅用于软件联调，不得作为真实物理或控制性能结论。
架构、伪时间语义、配置来源、快速开始和真实 PINN 替换步骤见 [OPTIMIZATION_SHELL_GUIDE.md](../../../../optimization_control/OPTIMIZATION_SHELL_GUIDE.md)。

快速验证：

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s optimization_control\tests -p 'test_*.py' -v
& .\.venv\Scripts\python.exe -m unittest optimization_control.ppo_single_turbine.test_baseline -v
```

2026-08-24 收尾结果为优化框架 36 项、T1 回归 7 项全部通过。训练和历史模型评估命令见使用指南，历史模型必须显式选择 `legacy_unsquashed`，不能与当前 tanh 策略混用。

## 队友交付区使用说明（data/teammates/）

每个队友一个独立目录，**各自目录内有 `README.md` 说明格式与更新记录**。
请队友把成果放入对应目录，不要乱放。目录内文件约定：

### 袁夫达 — `data/teammates/yuan_fuda_floris/`

```
yuan_fuda_floris/
├── README.md          # 数据说明：风况范围、风机布局、字段含义、生成日期
├── raw/               # 原始生成数据（按尾流模型分子目录）
│   ├── gch/           #   GCH（Gauss-Curl-Hybrid）模型数据
│   └── cc/            #   CC（Cumulative-Curl）模型数据
├── processed/         # 统一格式、清洗后的数据（供 NN 训练）
└── scripts/           # FLORIS 调用/批处理脚本
```

格式要求（遵循 `CLAUDE.md` 第六节）：
- 数据文件推荐 `.csv`（表格型）或 `.npz`（数组型），命名 `YYYYMMDD_描述.csv`
- **每个数据文件必须附带同名 `.json` 元数据**：来源、日期、风况（风速/风向/湍流强度范围）、
  风机布局（坐标/机型）、尾流模型（gch/cc）、字段说明、单位
- GCH 与 CC 数据分开存放，文件名/元数据中标注尾流模型，便于对比两者精度差异

### 厉今飞 — `data/teammates/li_jinfei_nn/`

```
li_jinfei_nn/
├── README.md          # 模型说明：输入/输出、训练数据来源、精度指标、依赖版本
├── models/            # 训练好的模型（.pt / .onnx / .zip）
└── scripts/           # 训练与推理代码
```

格式要求：
- 模型文件：`.pt`（PyTorch）或 `.onnx`（跨框架），附同名 `.json` 元数据
- 元数据必须包含：输入特征与顺序（如 `[wind_speed, wind_direction, yaw, ...]`）、
  输出含义（如各风机功率）、归一化参数（mean/std）、训练数据来源、验证误差

## 本地 Git 管理

完整规范见 [`GIT_WORKFLOW.md`](../GIT_WORKFLOW.md)。默认仅本地管理；用户明确授权的 GitHub 分支交付使用独立克隆。

### 优化成果交付目录约定

`deliverables/` 保存日期命名的交付说明、清单、校验和及 ZIP；ZIP 默认不进入本地源代码仓库。
`deliverables/YYYYMMDD_optimization_handoff/` 包含本轮包和全部历史成果分卷，`qa/` 保存内部排版检查，`github_checkout/` 为本次授权上传的独立克隆，后二者不入源代码仓库或交付 ZIP。
包内保留原项目相对路径；`任务说明.docx` 面向人，`readme.md` 面向 AI，`manifest.json` 记录归属、文件大小和 SHA256。
已有交付不覆盖、不自动清理；需清理时先取得用户授权。
大批历史检查点可在 `compact/` 中生成 ZIP 包裹的无损 tar.xz，减少重复数据传输；自动恢复后逐文件校验。`github_checkout_compact/` 是同一次授权交付的独立克隆，不删除初始归档或改写其历史。
`maddpg_wind_farm/handoff_replay.py` 按解压位置加载已冻结模型与策略，只写新回放目录，不自动训练。

```text
本地文件目录（working tree）
    ↓ 显式选择当前任务文件
暂存区（index）
    ↓ 验证暂存快照并 commit
本地仓库（master + task branches）
```

- `master` 保存验证通过的稳定状态，任务在 `codex/<task>` 等短期分支完成。
- 使用 `git add -- <明确文件列表>`，默认不使用 `git add .`。
- 每个任务/实验一个原子 commit，格式为 `<type>(<scope>): <summary>`。
- `data/`、模型权重、训练日志和图片等大产物不入 Git；实验的 `config.yaml`、`metrics.csv`、`summary.txt` 入 Git。
- 运行 `powershell -ExecutionPolicy Bypass -File tools/project_git_status.ps1` 查看三层状态。

## 已知交付例外
首批 FLORIS CSV 没有逐文件同名 JSON 元数据；来源、风况和布局信息目前由队友目录 README、`说明.docx` 和模型 metadata 共同补足。该批次保留为历史例外，新交付仍严格执行元数据规范。

脚本、实验记录和图表的已知技术债统一维护在 `PROJECT_STATUS.md`，恢复工作时不要只依据历史组会材料。

### 随机风况与单机 v2 约定（2026-09-13）

- `environments/wind_generator.py` 负责风况生成和回放；`environments/stochastic_turbine_env.py` 为新版单机环境，保留旧环境兼容性。
- 新配置放 `ppo_single_turbine/configs/stochastic_wind_v1.yaml`，使用指南和 `wind_workflow.py` 放 `ppo_single_turbine/`，测试放现有 `tests/`；以上路径均相对 `optimization_control/`。
- 实验放 `optimization_control/experiments/YYYYMMDD_简短描述/`，先保存 `config.yaml`、`metrics.csv`、`summary.txt`；轨迹 CSV、同名 JSON、图像及权重为可再生产物，不入 Git，不自动清理旧实验。
- 主种子 42，按 split/worker/episode 派生独立子流；回放固定轨迹。新版策略附带配置、观测名称、归一化参数，禁止加载旧五维权重。
- 方法来源与设计假设分别记录。合成风是单点、带限纵向近似，不称为实测风、IEC 认证全场风或叶轮有效风；慢变化和阵风不计入背景 TI 验收。

使用命令、参数依据和本次验证见 [随机风况使用指南](../../../../optimization_control/ppo_single_turbine/随机风况使用指南.md)。
