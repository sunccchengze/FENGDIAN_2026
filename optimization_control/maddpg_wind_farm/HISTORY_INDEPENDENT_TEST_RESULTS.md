# 冻结history17的新独立测试（2026-10-30）

**完成：两个运行前冻结的均值收益条件均通过，但逐场工程不劣和400/500kW精度未全部通过。** history17在18条新风、三父54场上的case RMSE均值357.84kW，相对父377.17改善5.126%，相对persistence17的362.56改善1.303%，三流均严格改善两种对照。不能据此升级为全场景成功或MADDPG继续训练成功。

预测器新增价值的整风cluster bootstrap ratio 95%区间为[.96765,1.00322]，包含无改善；这是通过预定点估计门槛的有限增益证据，不是可靠显著优势。逐场5%不劣相对两对照都只52/54通过；history最差653.94kW比父673.70低，但比persistence644.08高，原400/500kW精度为0/3流。所有反例保留，不test后调参，不实施新网络/蒸馏/RL/yaw。

## 计划变更与冻结身份

本轮从6e91ccc的开发集诊断切换到获准的新独立测试，停止预测器/网格/时域的搜索；不实施MADDPG蒸馏、网络结构变更、RL或yaw训练。[运行前协议](HISTORY_INDEPENDENT_TEST_PROTOCOL.md)和[配置](configs/history_independent_test.yaml)先固定，计时适配器等价验证通过后才锁执行源和释放新风。

forecast_model SHA256固定为`a5571a19354015c8b5997823748fafd7f0a6a355a0422d35b539e4faa3992877`，32样本历史、alpha=.1、17候选/H12/8步重选、tracking MSE、1e-12顺序选择、±.10rad/s speed权限、父反馈和执行器均不变。原三父检查点依赖绝对路径和SHA，累计训练步32768/28672/24576，不重新筛选父或保存新Actor。PINN/归一化/入口生成器/背景调度亦锁定。正式RL/策略更新0、forecast重新拟合0。

## 新测试、公共P/PI与判据

seed42、split=test、episode66000000..66000017，按stationary/ramp/gust×2.75/3.35/3.85MW×初始pitch.025/.055rad顺序生成18条128秒新风。生成前扫描三个工作树6893个JSON，未发现该区间实际episode字段撞号；原提案的命名空间预留不算已生成数据。与600条fit及24条开发风的float32值SHA不交叠，新风彼此唯一。所有新风与配置/模型/执行源/预检/manifest的绑定均在[release.json](../experiments/20261029_history_independent_test/release.json)中锁定。

每条新风配三原父，共54场，history17/persistence17/父各执行54次。P和PI只对公共18case各跑一次，逐流展示引用同一结果，不将重复展示当新物理回合。总198回合、25344个真实transition。预测评价只按18条新风计算，不能把三父算54条独立风。

主收益沿用三流case RMSE均值均严格改善固定父且总体至少1%；预测器新增价值另外要求三流均改善persistence17且总体至少1%。每case5%工程不劣、worst/pooled/bias、400kW均值/500kW最差与运动代价独立报告。正向均值不能遮蔽逐case失败，工程容差不等于改善。按族整风bootstrap2000次、seed42；功率配对先每风跨三父等权汇总后重抽18条，不把54场或重叠窗口当独立重复。test不用于选模型/父/参数，不按结果重新抽风或续搜。

## 功率闭环结果与负例

下表为每流18场case RMSE均值（kW）；负变化表示history相对该对照改善。单流只要求严格改善，1%要求用于总体，未临时改成每流≥1%或用CI另改原判据。

| 父流 | 父 | persistence17 | history17 | 相对父 | 相对persistence |
|---:|---:|---:|---:|---:|---:|
| 0 | 387.24 | 375.40 | 372.19 | -3.886% | -.855% |
| 1 | 387.80 | 369.14 | 365.80 | -5.673% | -.904% |
| 2 | 356.47 | 343.14 | 335.51 | -5.879% | -2.223% |
| 总体 | 377.17 | 362.56 | 357.84 | -5.126% | -1.303% |

相对父43/54场改善，相对persistence34/54场改善。三流总体点估计均为正，forecast增量只有约4.72kW，不能用26.64%的风预测MSE改善替代这项控制效果。按18条风、族内6条cluster重抽的功率case均值ratio区间：history/父.94874 [.92593,.96904]；history/persistence .98697 [.96765,1.00322]。CI不另作选模或门槛，后者跨1的不确定性单列。

| 方案 | 物理回合数 | case均值kW | pooled kW | worst kW | bias kW |
|---|---:|---:|---:|---:|---:|
| history17 | 54 | 357.84 | 373.82 | 653.94 | +32.26 |
| persistence17 | 54 | 362.56 | 377.63 | 644.08 | +40.76 |
| 父 | 54 | 377.17 | 391.84 | 673.70 | +51.88 |
| P组合 | 18 | 543.95 | 567.97 | 875.75 | +389.67 |
| PI组合 | 18 | 444.48 | 463.90 | 824.72 | +208.98 |

pooled按全部等长回合时步合并，bias为功率减目标。P/PI是公共18case一次执行，不能把跨父引用算54次物理实验。history对父与persistence的5%不劣均52/54，分别按流为18/18、17/18、17/18及18/18、16/18、18/18。关键反例（完整54配对保存在[paired_cases.csv](../experiments/20261029_history_independent_test/paired_cases.csv)）：

| 新风/父流 | history kW | 对照kW | 不利变化 |
|---|---:|---:|---:|
| gust/3.85MW/pitch.055，流1，对父 | 518.97 | 479.21 | +8.30% |
| stationary/3.85MW/pitch.025，流2，对父 | 242.96 | 227.58 | +6.76% |
| ramp/3.85MW/pitch.055，流1，对persistence | 306.02 | 260.86 | +17.31% |
| gust/3.85MW/pitch.055，流1，对persistence | 518.97 | 484.08 | +7.21% |

history最差case属于低目标ramp（653.94kW）；各流均未满足500kW worst，因此history/persistence/父的原400均值+500最差门槛全部0/3。history逐case≤400为38/54、≤500为47/54；persistence35/54、49/54；父32/54、48/54。均值改善没有改善所有精度计数，低于400kW的stationary反例也不能算权限学习成功。

各分组case均值如下（kW）；每组pooled/worst/bias、每流和运动量见[group_metrics.csv](../experiments/20261029_history_independent_test/group_metrics.csv)。

| 分组 | 父 | persistence17 | history17 | P | PI |
|---|---:|---:|---:|---:|---:|
| stationary | 345.77 | 339.47 | 336.17 | 504.09 | 404.01 |
| ramp | 409.62 | 389.32 | 387.17 | 585.92 | 486.66 |
| gust | 376.11 | 358.89 | 350.17 | 541.85 | 442.77 |
| 2.75MW | 416.79 | 396.95 | 382.99 | 709.49 | 540.63 |
| 3.35MW | 337.62 | 325.20 | 319.04 | 536.61 | 422.24 |
| 3.85MW | 377.10 | 365.53 | 371.48 | 385.76 | 370.57 |
| pitch .025rad | 371.81 | 360.38 | 351.60 | 513.89 | 451.65 |
| pitch .055rad | 382.53 | 364.74 | 364.07 | 574.02 | 437.31 |

在3.85MW组history比persistence更差，均值也略高于统一PI的370.57kW；不能从总体优于PI推出每目标或完整三通道方案成功。背景yaw继续控制机舱heading，gamma由heading与来流差wrap得到，未开放学习yaw。

## 一次一条风的预测信息评价

下表U MSE单位(m/s)²，按18条整风等权；h1..8取16个决策起点，h1..12取15个完整起点，不事后挑horizon。

| 区间/族 | persistence MSE | history MSE | ratio | ratio 95%整风区间 |
|---|---:|---:|---:|---|
| 1..8总体 | .199065 | .146040 | .73363 | [.67096,.81006] |
| 1..8 stationary | .206223 | .142064 | .68889 | [.64643,.74187] |
| 1..8 ramp | .237804 | .164094 | .69004 | [.60273,.82882] |
| 1..8 gust | .153167 | .131962 | .86155 | [.71627,1.04476] |
| 1..12总体 | .229223 | .154047 | .67204 | [.60492,.76287] |

主区间总体改善26.637%、次区间改善32.796%；gust主区间的族内区间跨1，保留不确定性。逐h=1..12总体ratio为.8697/.7885/.7628/.7136/.7116/.7313/.7228/.6879/.6163/.6464/.6614/.6124。主区间U bias=-.00907m/s；方向wrapped MSE1.03e-6rad²，persistence2.08e-5rad²。全部3384个逐步预测的U裁剪0、方向零向量回退0，TI常数保持误差0不计为拟合收益。252条逐风/逐h指标和3384条预测分别见[forecast_metrics.csv](../experiments/20261029_history_independent_test/forecast_metrics.csv)、[forecast_predictions.csv](../experiments/20261029_history_independent_test/forecast_predictions.csv)；各族CI见[forecast_groups.csv](../experiments/20261029_history_independent_test/forecast_groups.csv)。

选中项前8步的功率误差预测与真实实现对齐，history的预测/实际误差序列差pooled RMSE321.02kW，persistence358.56；对应选中项预测8步pooled RMSE196.95/268.57，真实373.82/377.63。预测偏离仍明显，不能当作真实可达下界；两种控制器使用各自状态和选择，不将其差值误称为同状态动作价值。当前证据只支持新测试设计内有限均值收益。

## 实际运动与通道限制

每场三机合计、含首步的平均TV：speed命令和实际speed单位rad/s，pitch/heading单位rad；归一化指令均方变化为每步/三机/三通道平均。

| 方案 | speed命令TV | 实际speed TV | 实际pitch TV | 实际heading TV | 指令均方变化 |
|---|---:|---:|---:|---:|---:|
| history17 | 9.978 | 2.602 | 2.121 | .288 | .051006 |
| persistence17 | 10.503 | 2.871 | 2.153 | .288 | .051996 |
| 父 | 8.715 | 1.951 | 2.051 | .288 | .048218 |
| P | 8.683 | 1.980 | 2.406 | .288 | .035197 |
| PI | 8.698 | 1.968 | 2.331 | .288 | .036964 |

相对persistence几项运动量降低，相对父的speed运动和指令变化仍增加，不宣称无代价。history最大heading/pitch/speed变化率.001941rad/s、.00872664626rad/s、.048401rad/s²，均在原限制内；全部gamma关系误差0。history864次规划选择零9、±.10端点614、中幅241（27.89%），切换493次；persistence为7/680/177、切换566次。两方案speed总指令和实际speed触物理边界比例均0，不能将修正端点选择当执行器饱和或唯一失败原因。父在相同实际观测上的动作逐位保留；新权限改变物理状态后，父pitch反馈轨迹仍可改变。

## 计时等价性与历史异常

新增计时函数只包裹原history_speed_search.plan，未改变数值策略。1项新mock测试821行，真实代理预检821行；history和persistence两路径的偏置、17成本、逐步内部误差、预测风、选中项与历史SHA精确一致，原状态/父RNG未变。原零修正/因果隔离/保存加载工程证据只读复用，没有重跑旧大审计。

每次规划保存CPU、perf wall、UTC起止、PID、Windows uptime、QueryUnbiasedInterruptTime及机器idle/kernel/user累计时间；逐步保存action/transition CPU和wall，回合也保存完整起止证据。CPU为进程累计时间，可能因并行线程大于wall，不能按CPU/wall直接推实时性或单核使用率。计时不会进入动作/观测/物理dt；所有异常保留，不删后重算漂亮均值。

字段解释按官方合同核对：[Python 3.12 time](https://docs.python.org/3.12/library/time.html#time.process_time)将process_time定义为进程system+user CPU时间、不含休眠，而perf_counter含经过的休眠时间；[QueryUnbiasedInterruptTime](https://learn.microsoft.com/en-us/windows/win32/api/realtimeapiset/nf-realtimeapiset-queryunbiasedinterrupttime)不含系统sleep/hibernation、单位100ns；[GetSystemTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getsystemtimes)是跨处理器累计时间，kernel包含idle。因此机器kernel不能直接当忙CPU，需要与idle/user一起解释；本轮只保留计数证据，不据一次比值武断归因。

旧异常train_run0_ramp_3800000、t40、863.9507545秒的plans.json SHA已按其既有output_manifest核对，见[historical_outlier_guard.json](../experiments/20261029_history_independent_test/historical_outlier_guard.json)，没有写旧文件或重跑历史。旧日志无CPU/暂停证据，不能事后断言异常原因；本轮更完整的计时也不等于实时性证书。

| 方案/864次规划 | CPU mean/median/p95/max 秒 | wall mean/median/p95/max 秒 | wall>8秒 |
|---|---|---|---:|
| history17 | 1.281 / 1.203 / 1.875 / 2.813 | 1.044 / .990 / 1.452 / 2.248 | 0 |
| persistence17 | 1.260 / 1.203 / 1.797 / 2.656 | 1.029 / .986 / 1.398 / 2.090 | 0 |

1728次调用全部计入，完整字段和UTC/uptime/awake/system时间差见[planning_times.csv](../experiments/20261029_history_independent_test/planning_times.csv)；原始start/end整数在每个NPZ metadata中。没有出现新的>8秒规划，不代表1Hz父反馈与异步规划已完成真实部署调度验证；实际物理dt仍固定1秒。不能把本轮较短最大值用于抹去旧863.95秒异常。

## 查询和磁盘预算

正式查询精确为370710行：history17与persistence17各54×3325=179550，父54×129=6966，P/PI36×129=4644；预检/mock各821，预计总372352，硬上限375000。3325含17×(15×12+8)内部预测、128个外部transition和1次reset。逐scope持久预占、逐forward收费，中断预占保留，不隐性重跑；风生成、线性预测和保存数据审计不调用PINN。

用户登记既有本地工作目录 67.93GiB，本轮没有整理或删除旧文件。新产物预计≤64MiB、硬上限1GiB，写入前按实际bytes核查；新风写前预留1MiB。模型/旧工作树/回放只读绝对路径引用，不复制，无新.pth。198个回合的外部轨迹、观测/动作、必要内部误差及计时压缩到独立NPZ，不重复保存整套旧数据；预计与系统可用空间见[space_budget.json](../experiments/20261029_history_independent_test/space_budget.json)。

实际查询372352＝正式370710＋真实预检821＋mock821；真实PINN输入371531，scope200个全部完成。没有重跑旧实验回合/旧异常或抽换test。全部198回合压缩保存，新增实际transition25344。主审计与独立算术审计的功率RMSE/bias、风预测MSE复算差0，17项逐步误差成本最大差6.66e-16MW²；全部20736个父动作在保存观测上逐位重放、RNG不变，current/previous command、1728个历史SHA/预测风与18条入口一致。旧文件清单及输入/执行源SHA不变。

图与审计完成后的新产物约15MiB，最终bytes和逐文件SHA写入交付清单，低于64MiB预计量及1GiB硬上限；未复制模型/旧回放/工作树，未删除任何旧文件或当前文件。

三组Python/Matplotlib PNG/PDF已逐张检查标题、单位、图例、轴，未画新策略选模曲线或训练曲线（本轮无训练）：[全部逐场比较（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、[预测与全部CPU/wall计时（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)、[预定ramp高目标高初始pitch实际控制（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)。最后一图含流1相对persistence退化17.31%的反例，未据结果换绘图case。

## 下一阶段结构和对照提案（仅提案，未实施）

依据：相对父有5.13%的均值改善，预测增量点估计1.30%但CI跨无改善，且有逐场反例。建议下一步先做**冻结预测信息的接线与初始化工程验证**，再由单项训练协议检验其学习价值；不立即蒸馏全部搜索轨迹，也不把当前新test作为训练数据。搜索器不是全场景合格教师，若另做模仿，需新train专用数据、student视角可辨识性和自身闭环验收，不能抹去这些反例。

拟保留原15维输入送入父Actor/target，父pitch映射冻结，speed仍为当前父参考加±.10有界新头。共享预测向量取h1..12的[预测U-当前U、预测sin方向-当前sin、预测cos方向-当前cos]共36维，使用固定物理尺度，不重新拟合预测器或test标准化。为了与本轮相同8步保持语义，新头另读自身上一held delta及已知phase，共15+36+1+1=53维；每8步才改delta，父pitch每1秒反馈。phase来自物理步号，不能读wall时间。

集中Critic拟用原joint obs45+总执行动作9+共享forecast36+joint held delta3+phase1=94维；online/target都走同一组合。旧54维输入权重可映射到新Critic对应列，新列零初始化，以保留初始Q；新speed头末层零、target精确复制，以先保持父动作。该方案涉及新接口/回放版本和优化器状态形状，**须先确认方案并验证，不在本轮修改或静默迁移**。旧回放缺真实forecast/history时不能补零假装已观测；先核对是否能按原manifest重建，无法重建则另行明确共同新回放协议，不称作无损恢复。

后续学习对照拟三臂：A父权限同预算继续训练；B冻结父+新增speed、预测输入置零；C同B但读真实冻结预测。B/C结构、参数数、8步保持、Critic与回放语义一致，只变预测信息；不同时修改奖励/lr/n-step，不复制桨距侧Actor队友动作条件试验。三臂各3条seed42派生流，候选预算各8192环境步，正式总73728步，**本轮0步且未批准执行**。工程接线/恢复验证与训练收益验收分开；initial/selected/final均保存，只用另冻的开发validation选模，selected=initial不算学习收益，原稳定/父对照/400/500要求另行在训练前锁定，不能降低原目标。

当前18条test封存，不用它逐项挑网络/超参、记忆失败case或选学生；未来学生独立验收需新锁测试。训练查询与磁盘须另做精确预算，初始/父模型按引用共享，禁止每评估点复制整套旧回放。以上是可审查的下一阶段方案，没有创建网络、数据生成任务、优化器更新或训练检查点。

## 复核入口与复现边界

[执行入口](history_independent_test.py)、[保存数据审计与图](history_independent_report.py)、[计时等价测试](../tests/test_history_independent_test.py)。[config.yaml](../experiments/20261029_history_independent_test/config.yaml)绑定只读依赖，[metrics.csv](../experiments/20261029_history_independent_test/metrics.csv)保存物理回合指标，[bank manifest（交付范围说明）](../../materials/洪祖名/20261106_optimization_final/README.md)保存18条风身份。

本轮已释放后，不为改善结果重跑prepare/precheck/release/run或换seed。完整重复闭环需要单独预算并复用锁定的风，不能重新抽test。已有结果可以无PINN推进地读取NPZ，独立复算各场RMSE、动作/实际轨迹及计时：

仓库按现有Git文本规则将metrics.csv行尾保存为LF；本地冻结原始CSV是CRLF，未为提交改写。交付清单分别记录Git blob SHA和本地原始SHA，二者只差行尾，数值逐项一致；本地complete锁和output_manifest绑定原始文件。不要把行尾规范化当作新数据或据此重新抽风。

```python
from pathlib import Path
import csv, json, hashlib, math
import numpy as np
root = Path('./optimization_control/experiments/20261029_history_independent_test')
with (root/'metrics.csv').open(encoding='utf-8') as stream:
    metrics = list(csv.DictReader(stream))
for row in metrics:
    path = root/row['trace_path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['trace_sha256']
    with np.load(path, allow_pickle=False) as saved:
        meta = json.loads(saved['metadata'].tobytes().decode('utf-8'))
        fields = meta['trace_fields']
        error = saved['trace'][:, fields.index('farm_power_w')] - saved['trace'][:, fields.index('target_w')]
        rmse = math.sqrt(math.fsum(float(x)*float(x) for x in error)/len(error))
        assert abs(rmse-float(row['rmse_w'])) < 1e-7
        # saved['obs'], ['action'], ['parent_action'], ['offset'], ['step_timing']
        # meta['plans']含17项逐步内部误差、预测风、历史SHA和完整clock start/end。
```

策略加载与绘图使用既有runtime：先调用fixed_pinn_demo.activate_runtime指向原`.venv/pinn_tf216`，不安装依赖。原始NPZ/风/释放锁可按SHA逐项复核；图只从保存数据产生，不新增查询。P/PI是统一pitch反馈加yaw/speed调度的完整方案，搜索器额外使用预测推理，误差比较不能当作新增MADDPG学习收益。当前仅合成标签代理内软件结论，不宣称物理精度、三通道学习成功或部署实时性。
