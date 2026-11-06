# 供PINN组核查的接口响应说明：48点冻结夹具

2026-11-06。本文只整理已有软件诊断数据及重放合同，不发送队友消息、不修改模型／标签，也不要求完成物理响应认证后才结束新参考软件回归。48点不能划定模型可靠全域，合成标签不是物理真值，TSR=7.55不保证变桨或限功率时最优。

## 来源与选点

数据在[20261106_nrel_speed_diagnostic](../experiments/20261106_nrel_speed_diagnostic/summary.txt)，代码／结果提交`7656428641538fb63e0d6872dfbc930a92177cf6`，协议提交`9467cfc169156b58218aa37b707471019b4fb971`。选点是旧／新Y2 selected与PI、原六条validation、响应t=32／96，共48点；这是六条validation诊断，不是后续18条已用测试风库的回归数据。

完整SHA及原始轨迹指针见[lock.json](../experiments/20261106_nrel_speed_diagnostic/lock.json)、[anchors.json](../experiments/20261106_nrel_speed_diagnostic/anchors.json)和[output_manifest.csv](../experiments/20261106_nrel_speed_diagnostic/output_manifest.csv)。不需要重扫更早1720项归档。

原PINN权重为[trained.keras（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)，SHA256为`7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`；桥接团队脚本SHA为`4db850074b62a7f86720534f6286b48c2a024efd9218f1b243c376fd54d5a270`。原配置／训练报告和优化侧SI桥接均在来源锁中登记。

## 数组、字段与单位

每点文件为`anchors/a00.npz`…`a47.npz`，用`numpy.load(..., allow_pickle=False)`读取。当前每点30个请求均唯一，仍应使用mapping解释语义。

| 字段 | 当前形状／类型 | 含义 |
|---|---|---|
| inputs | [30,12] float32 | 实际传给优化侧PINN适配器的SI物理输入 |
| outputs | [30,6] float32 | 冻结代理重新预测的三机P及Ueff |
| labels | [30,6] float32 | 原synthetic_labels在相同inputs与机位上的参考输出 |
| mapping | [30] int32 | 第k个语义请求对应inputs／outputs的哪一行 |

inputs顺序为`[U, theta, TI, gamma1, gamma2, gamma3, pitch1, pitch2, pitch3, omega1, omega2, omega3]`。U为入口风速，m/s；theta为来流flow-to方向，从+x逆时针，rad；TI无量纲；gamma为实际偏航失配角、pitch为实际桨距，均rad；omega为实际转速，rad/s。三机固定顺序T01／T02／T03。

outputs及labels顺序均为`[P1,P2,P3,Ueff1,Ueff2,Ueff3]`，功率W、有效风速m/s。Ueff是输出，不是把入口U换成三机Ueff作为模型输入。外层归一化为identity，内部`wind_pinn_backend.team_inputs`负责转换到团队交错三机顺序、角度wrap及模型内部编码，不能再重复归一化。

原机位见positions.npz，单位m，依次为`[[0,0,90],[378,0,90],[756,0,90]]`。每个锚点固定入口U／theta／TI、实际pitch／gamma和机位，只改变omega；P和Ueff均重新输出。gamma来自保存的实际失配角，并核对`wrap(heading-theta)`，机舱执行器本身控制的是heading。

## 30种请求及一次性参考

[semantic_requests.json](../experiments/20261106_nrel_speed_diagnostic/semantic_requests.json)给出权威顺序。当前顺序为：0实际omega重放；1旧基础参考；2新基础参考；3…9仅T1的7点网格；10…16仅T2；17…23仅T3；24／25为T1实际点−／＋.01，26／27为T2，28／29为T3。

旧／新参考均从该响应时刻保存Ueff生成一次：旧函数沿用原数值顺序及[.6,1.267]；新函数为`clip((7.55/63)*Ueff,6.9*2*pi/60,1.267)`。三机直接替换基础参考，不叠加C残差，不把预测的新Ueff代回求固定点。网格7点覆盖新允许范围，局部扰动按该范围裁剪，float32端点向范围内取值。网格采样最大不等于全局最优或真实最佳TSR。

请求合集[requests.npz（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)另存全体inputs[1440,12]、offsets[49]、mapping[48,30]、expected[48,6]。expected是实际点保存的P／Ueff，anchors.json提供源版本、控制器、case、t、源轨迹SHA及源行SHA。所有反事实都是静态软件点，不证明执行器可达或闭环性能。

## 重放容差及结果范围

实际点先单行查询，再查询余下29行。事前重放容差为每机P绝对误差≤2W、每机Ueff≤2e-5m/s、全场功率≤6W；这是接口／数值一致性容差，不是物理预测精度要求。本栈48点实际重放误差均为0，详见[replay.csv](../experiments/20261106_nrel_speed_diagnostic/replay.csv)。模型域检查继续有效，域内不等于联合点已有充分训练覆盖或物理验证。

已有响应记录：三机旧→新基础参考时代理功率12点增加、36点降低，平均−8.450kW；原合成标签48点增加，平均＋23.131kW。局部自身功率方向130/144一致，全场方向124/144一致，T2分别37/48与33/48。它们只描述固定夹具中的软件差异，不要求模型强行输出某个NREL功率曲线。

核查可从[48点参考替换表](../experiments/20261106_nrel_speed_diagnostic/metrics.csv)、[局部差分](../experiments/20261106_nrel_speed_diagnostic/local_response.csv)、[432项跨机响应](../experiments/20261106_nrel_speed_diagnostic/local_cross_response.csv)与[完整诊断报告](NREL_SPEED_RESPONSE_RESULTS_20261106.md)开始，无需重新训练或重复模型查询。

原标签函数以入口U和旧曲线构造合成提取因子及尾流，未用实测或CFD真值验证。本说明不据48点划定可靠全域，也不把限功率RMSE上升解释为Cp效率下降；后续模型精度工作由相应负责人另行定义，不作为本轮新规则软件交接的无限前置。
