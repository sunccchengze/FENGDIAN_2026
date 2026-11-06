# 单因素候选方案：有限128秒桨距任务的gamma=.99/1对照

**仅提交方案，尚未执行。** 本轮正式RL为0；依据[一致性审计](PITCH_REWARD_ALIGNMENT_RESULTS.md)提出一个可证伪候选。保留原逐步奖励及.001参考变化惩罚，只改变TD折扣gamma=.99→1。其他观测、网络、动作权限、奖励、采样规则、学习率、n=8及预算相同，不开第二候选，也不利用已发布独立test改参数。

## 选择理由和可能失败

折扣把末32秒权重压到14.48%，与完整回合均匀平方误差存在可复算冲突。保留动作项、离线gamma=1在固定修正常规验证菜单中把平均偏好损失862.53W降到112.97W；慢变1337.95→274.68W。原惩罚同时能修复反向，尤其nstep验证慢变，没有充分理由一并删除。

反例保留：固定修正训练平均偏好损失53.29→74.00W；nstep训练9个槽位变差，6个槽位运动RMS增加>10%；nstep慢变验证菜单首选没有新增改善。离线损失量级不足说明会达到5%精度改善。gamma=1增加长尾bootstrap权重，旧Critic由gamma=.99训练，可能更难适配或更不稳定；有限128秒并不保证函数逼近/行为多步TD稳定。

## 公式和权限

两臂逐步reward完全相同：

\[
r_t=100[-((P_{t+1}-P^*)/15\mathrm{MW})^2-.001C_t],\quad
C_t=\mathrm{mean}_{3\times3}(a^{exec}_t-a^{exec}_{t-1})^2.
\]

n8更新均为实际m步，只有gamma不同：

\[
y_t=\sum_{k=0}^{m-1}\gamma^k r_{t+k}
 +\gamma^m(1-d_{t+m})Q_{target}(o_{t+m},a_{target}(o_{t+m})).
\]

true done在128步停止bootstrap，回放短尾非终止按实际m bootstrap，不跨回合；观测保留remaining。gamma=1的完整实现回报是均匀tracking加均匀软动作项，仍非纯RMSE；跨case平均MSE也不等于case平均RMSE，选模仍用后者。

Actor只学pitch。yaw继续跟踪风向，speed继续统一曲线；模型、执行器硬幅值/速率、PINN、父源均不改。软动作项不是物理硬约束的替代；动作代价需另外验收。

## 同源初始化及回放一致性

三流仍承接原20261023的validation选中父，绝不按已发布test重选：

| 流 | 原segment_000父 | SHA256 |
|---|---|---|
| 0 | pitch_run_0/segment_000/step_00016384.pth | 28e221e6f6e74096ef74e9a9375c638823a055c38232ef4d3b5e16a5026996ea |
| 1 | pitch_run_1/segment_000/step_00012288.pth | 0fcb0b9d474db0d04b3ac2d86c91d2f39d66bb3c025e30d911ce79b2ba445821 |
| 2 | pitch_run_2/segment_000/step_00008192.pth | e2897be535e5c9bae27acbecc5edd57460a8a038ba28719e366ab4c904309a05 |

绝对根为./optimization_control/experiments/20261023_progressive_random_control。两臂均通过现有NStepMADDPG.inherit(parent,8)接入；不用本轮或旧独立test挑出的新父。

四套online/target网络、六个Adam及其状态、replay全部原始(obs/actions/rewards/next_obs/done)、序列ID/指针/size/累计插入、Actor/Replay/Torch RNG同源继承。两臂不重置Critic/target、不额外拟合、不丢旧回放、不做奖励重标。原因是单步reward没变；所有旧/新行在采样时按该臂gamma重新算m步回报，不能混用预先缓存的旧折扣return。

候选须同步替换不可变AlgorithmConfig.gamma与SequenceReplay.gamma为1，清除只含派生值的采样缓存，检查replay/agent/base_config/metadata的gamma一致；对照显式保持.99。现有SequenceReplay保存原始reward，加载按AlgorithmConfig构建gamma，无需修改通用公共网络或权重格式。实验入口可检查expected_n=8及expected_gamma，不悄悄扩展普通MADDPG通用分派。

initial动作两臂必须精确一致。Critic/target初值相同但对gamma=1的值语义已经不准确，报告这一适配偏差；把额外Critic校准或重置混进候选会成为第二因素，本方案不做。

## 预算、随机流与工程门槛

一次固定2臂×3流×16384=98304新增环境学习步，每job128完整回合；沿用warmup512/update_every2，每job7937新增update。warmup、最小运行、计划恢复都计入预算，不额外开展环境学习smoke；不因结果不佳增预算。

seed42为主种子。拟用SeedSequence([42,20261029,purpose,run,...])：purpose5101场景排列、5102初始pitch、5103探索；来流沿用现有generate_inflow(seed42,split,episode)，train episode51000000+run×1000+episode_index，validation52000000系列、test53000000系列、已知压力53009000系列。初步只读查三个工作树的维护config未见这些命名空间；正式prepare前必须再核查并冻结，不能把草案种子称实际RNG。

沿用原训练九格（stationary/ramp/gust×2.6/3.2/3.8MW）分块排列和初态uniform(.025,.055)、白噪声pitch std=.03、末比例.2；改变流身份对两臂相同，不改变采样规则。先生成并SHA锁定共同manifest、129点风数组、目标/初态和完整探索序列；记录实际SeedSequence熵、生成的整数种子、初始/各回合RNG状态及探索状态。Actor分歧后状态/反馈功率不同是预期，不能称同一内容回放。

学习前契约检查必须包括：

1. 两臂原始回放reward逐位不变、初始四网络/Adam/RNG/回放相同；仅gamma标识及其纯派生return不同。
2. n8 gamma=.99适配与原n8逐batch目标、loss、参数更新一致；工程内存更新丢弃，不算正式收益。
3. gamma=1的已知短序列、ring wrap、true terminal、非终止短尾用手算m步和bootstrap验证；保存新进程恢复时gamma与旧回放/RNG相符，拒绝错误臂配置。
4. 最小真实环境检查放在正式run0两臂首128预算内，先验证动作/奖励分项、字段和保存恢复，再展开剩余预算。任何工程错误保留失败attempt与实际/保守步账，不能重置台账后称同预算；必要时停止并报告。

每128步保存完整状态；每4096步验证，含initial；每job固定16384步终点。run0两臂4096处计划新进程恢复，包含预算内。只用完整18场validation的case-RMSE均值严格改善选selected，保留initial/selected/final，不能用回报选模或test重选。

## 事前精度、稳定和动作代价验收

以下作为正式训练前待确认的整套门槛，不因结果改动。它们保留原pitch慢变≥5%、至少2/3流、其他风况逐流≤5%退化和final/selected≤1.25，并对final和实际运动单独要求：

| 项目 | 固定判断 |
|---|---|
| 新增学习 | 候选三流selected_step>0；有initial被选中则不得称三流新增学习 |
| 慢变主收益 | selected和final各自case-RMSE均值较同预算gamma=.99减少≥5%，各至少2/3流改善；同时列相对原父，不用退化对照掩盖父能力损失 |
| 其他能力保留 | 平稳/阵风selected、final逐流的均值与worst-case相对同预算对照及固定父均≤1.05；所有case保留，压力独立单列 |
| 终点稳定 | 各流final/selected≤1.25；全常规final mean/worst对固定父及对照≤1.05。只满足不劣不能称改善 |
| 实际运动代价 | 各风况、各流selected/final的case平均实际pitch总行程和RMS速率分别≤对照1.10倍；分母下限行程1e-4rad、RMS1e-4rad/s，并列原始绝对值。worst-case也报，不以平均藏掉极端 |
| 硬约束 | 实际pitch[0,.22]rad、速率≤.00872664626rad/s，数值核验tol1e-9；无越界；报参考饱和/速率饱和/目标与实际量 |
| 结论等级 | validation先判；冻结后新test单独检验。区分原策略改善、平均优于PI、每场优于PI；不预设PI全面获胜或MADDPG全面获胜 |

完整均值/偏差/波动分解、paired ΔRMSE对P/PI、selected→final退化、三流SD、每case明细都报告；流间SD不是置信区间。无新增绝对kW通过线来替换原pitch相对改善门槛，P/PI仍为冻结kp1.5、ki.08、bias.04、antiwindup.2、integral_limit.3。

## 冻结后的独立测试计划

新validation仍18场：三风况×2.9/3.5MW×初始.025/.04/.055，但用52000000系列新轨迹。所有选择锁定、六job/核心审计通过后才一次生成53000000系列test：三风况×2.70/3.30/3.90MW×两条轨迹×初始.03/.05，共36常规场；所有控制器共享模型/天气/目标/初态/执行器。

压力7.6/7.8m/s×4.35/4.55MW×初始.03/.05，共8场，称已知低风压力回归，单独报告；只作当前模型内数值估计，不称真实/全局不可达证书。P/PI不重整定。测试后不改gamma、不改门槛、不追加候选。全部学习与评估实际/保守预算分开记，正式启动前冻结各项最大评估量。

本方案尚无实际种子状态、学习结果、新test或候选权重；不能把拟定98304步记成已执行。本轮提交供确认，现有实现和默认策略继续保持冻结。
