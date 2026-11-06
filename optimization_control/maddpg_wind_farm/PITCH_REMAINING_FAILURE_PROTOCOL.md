# n8有效候选剩余失败核查（2026-10-29，零训练）

本轮只读原模型/实验，在独立pitch工作树输出分析与一个待审阅学习方案。正式RL步、优化器更新、模型推进（含reset）、新test释放均固定为0；不启用备用10000步额度。不修改公共训练代码、观测接口、默认策略或其他工作树。

## 固定对象与数据隔离

- 唯一有效候选组固定为20261028_pitch_nstep的n8、gamma=.99三份validation-selected，步数16384/12288/4096；身份按20261028_pitch_nstep_mechanism/candidate_manifest.json逐项SHA核对。保留initial/final及各验证快照作为诊断参照，不用它们拼挑新候选。
- 同case相对PI核查只使用该实验evaluations/known已保存的18训练+18常规validation场；low_wind_stress即使split字段为validation也严格排除方案选择。P/PI固定参数不重整定，真实基线只读一次，不复制为三独立训练流。
- n8原18场选模validation的15个快照仅用于同场景更新后退化分析；若没有该套PI轨迹，不借不同天气的PI补齐。不新增闭环评估。
- 已保存n8的384个训练行为回合及原回放只作探索分布、覆盖/梯度/更新过程核查，不称部署性能。不读取test目录或test_bank；已发表test/pressure数字只在历史索引中保留，不参与特征、参数或候选选择。
- 网络核查固定读取三候选与各自final，文件别名去重；每状态回放按插入顺序等距取1024起点（含首尾）。不调用sample/update，不消耗其RNG。对同观测比较回放队友动作与当前队友动作的Actor梯度、动作差和32近邻支持代理；均为离线函数计算，不冒充闭环收益或真实价值梯度。

## 固定统计与解释边界

完整128步RMSE/bias/std及RMSE²=bias²+variance均复算。弱于PI以同case RMSE严格差>0为原始定义，另列>100W数值稳健标记；不按绝对RMSE选择弱场。逐场、目标、来流族、初态、训练流及实际风速域全部保留。时间窗固定1–32/33–64/65–96/97–128，仅帮助分解，完整指标为主。

同波形不同初态/目标/控制器、同回合不同时窗及梯度点是相关观察。报告15个常规波形、36个输入case、108个selected流×case槽位及三条训练流，不把槽位或轨迹对当独立训练重复，不作显著性/置信区间声明。三父原起点训练预算不同的限制保留。

正反例均保留：持续偏差、方差、启动响应、同天气的selected→final或initial→selected退化分别列证；当前输入不能证明全局可达性。PI在同weather执行更好可作为“存在额外可避免误差”的有限证据，不作为目标每秒全可达证明。没有target-step试验时不能称已识别目标阶跃响应。

先完成上述核查再提出一个具体学习候选；与既有4秒趋势、LR、anchor、nstep及gamma历史逐项区分。涉及新结构/观测时只提交公式、继承/接口/公平对照/固定预算/可失败验收方案，等待确认，本轮不实现或训练候选。不复制speed侧预测器。

## 输出与复现

目录沿用experiments/YYYYMMDD_简短描述：20261029_pitch_remaining_failures/，config.yaml、metrics.csv、summary.txt及逐场/分组/网络诊断CSV、PNG和源SHA清单。源码仅新建离线审计入口，原实验只读，不清理旧输出。结果及单候选方案分别写PITCH_REMAINING_FAILURE_RESULTS.md、PITCH_REMAINING_FAILURE_CANDIDATE.md。
