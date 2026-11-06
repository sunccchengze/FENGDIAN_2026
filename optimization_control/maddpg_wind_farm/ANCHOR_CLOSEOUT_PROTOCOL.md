# 动作约束收尾与验证集诊断：运行前约定

2026-10-27 获准实施。正式新增训练预算为 0；原六次 8192 步训练、选择锁、测试释放标记、模型及全部旧产物只读。原 lambda=0/1 协议及门槛不变。新入口 `anchor_closeout.py` 负责身份校验、内存恢复审计和固定测试续接，`anchor_closeout_diagnostic.py` 负责验证集诊断，`anchor_closeout_figures.py` 负责 Python 绘图；不调用原训练/prepare/release_test，也不改冻结源码。结果报告为 `ANCHOR_CLOSEOUT_RESULTS.md`，后续结构建议在报告中单列，不训练新候选。

沿用已有目录职责：代码在 maddpg_wind_farm，契约测试在 tests；输出在独立工作树的 experiments/YYYYMMDD_anchor_closeout。保留 config.yaml、metrics.csv、summary.txt；子目录 audit、test、diagnostic、figures 分别保存审计、原锁定测试、验证集诊断和 Python 图。文件英文小写下划线，图同时保存 PNG/PDF；不覆盖既有结果，不自动清理。原工作区的 PROJECT_STATUS.md、TASKFLOW.md、README.md 不修改；集成摘要写本轮报告。

1. 在独立 worktree/codex 分支执行，显式输出路径必须位于当前 worktree，且不能是原工作区或其子目录。复制本任务 7 个未提交文件并记录逐字节 SHA256；所有执行的原模块与其原工作区版本匹配。保留源配置、选择锁、原 test/config.yaml 及旧目录全部文件的 SHA256 快照；每阶段结束复核。源/配置/manifest/检查点任何不一致立即失败，不重新生成风况或重选模型。
2. 原测试 20 case（18 routine，2 已知低风压力），initial/selected/final/parent × 两臂三流及 fixed/P/PI × 两臂，共 600 指标、76800 行轨迹。所有方案同 case/执行器；保留已释放事实，即使原结果未落盘也不抽新测试。每个策略 job 独立落盘并校验完整性，续接只补缺失 job，不覆盖完成 job。只在全部完成后聚合。540 routine 指标为本轮锁定常规测试，60 压力指标不是新独立样本。
3. 先完成训练/验证证据诊断并冻结其摘要，再运行锁定测试。诊断不读取测试指标。两臂三流对 selected/final 在当前闭环观测上运行 8 种 S/F 通道组合、zero_yaw/zero_speed/zero_both，以及 final 中分别替换 parent_yaw/parent_pitch/parent_speed/parent_all，共 90 变体、540 case、69120 环境步；均无梯度更新。S/F 顺序为 yaw/pitch/speed。所有变体保留，不据结果新增变体。保存实际命令、执行器轨迹和原始饱和统计，组合差不可相加或作唯一根因证明。
4. 接管检查分别覆盖真实旧 speed/yaw 三流初始化（online/target 的父回放 obs/next_obs），以及 anchor 初始与原父策略。零新增头只指新通道，不能把全部动作归零。总动作最大误差 <=2e-6；六个验证 case 的128步闭环要求实际 heading/pitch/speed 差 <=1e-6（rad 或 rad/s），功率及RMSE差 <=1 W。新执行器约束违例为0。容差在本次新复核前固定，不追溯改写历史结果。
5. 局部模型扫描只使用 validation 中 parent/selected/final 的实际运行点，每 case 步16/64/112，三机逐机改变实际 speed ±0.02/0.05/0.10 rad/s 或 gamma ±1/3/5度，及共同改变该通道；保留0点。严格在原模型域及物理范围内，记录裁剪。保存各机/全场功率差、尾流响应、跟踪绝对误差的局部改变和正负不对称；非零响应不等于可利用收益，单步准静态差也不等于执行器闭环收益。另在统一执行器内对父策略分别叠加上述固定偏置（独立验证的12种偏置及0参考），仅作预声明的可利用性诊断，不选训练超参。两臂父相同，三个父流各13变体、234 case、29952步；不将最好偏置作为冻结候选。
6. 核对配对网络/所有优化器/回放/RNG/探索、30份teacher/lambda/lr/尺度、保留转移的总命令/奖励/终止/heading语义/速率/动态残差包络；复算训练风况预检。initial/selected/final的内存保存加载、带噪动作与下一update一致；两条128步内存恢复分叉与实际恢复后回放比较。更新仅存在于丢弃的内存副本，原检查点不写回，新增正式训练0。
7. 原稳定性 final/selected<=1.25、final相对父策略与配对baseline的mean/worst<=1.05，三流全过才通过。原400/500 kW精度单列；selected=initial不算新学习。测试只评价冻结lambda0/1方案，不能据其调系数或设计下一结构。报告流0损失、全部失败及来源；P/PI是桨距反馈+偏航/转速调度的完整方案比较。本实验不直接证明新增控制权限的因果收益。
8. 新代码先运行有意义的身份/输出隔离、CSV完整性与指标复算、通道干预语义测试，再跑正式收尾。每阶段记录输入/输出摘要，图逐张检查。产物及精确提交清单留本工作树；不合并master、不推送、不删除、不安装全局依赖。

实际控制图预先固定使用 test_gust_1_pitch0.025，三个训练流均展示，不按表现挑场景。功率、机舱/来流方向、实际失配角、桨距和转速均由保存轨迹作图。局部响应和固定偏置完整展示正负方向，不能只报最好点。
