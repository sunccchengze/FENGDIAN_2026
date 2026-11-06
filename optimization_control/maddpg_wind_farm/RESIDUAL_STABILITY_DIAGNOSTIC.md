# 残差后期退化：验证集诊断协议

2026-10-24运行前固定。仅使用20261023_residual_random_control已有validation bank，禁止读取旧test指标或风况作本轮归因和改进选择。

1. 三流all策略的selected/final，在同一当前观测上分别计算两策略动作，按yaw/pitch/speed三个通道逐项选择，共2^3=8个闭环组合。S为selected，F为final，顺序固定yaw、pitch、speed；不得回放原策略轨迹动作来代替闭环调用。
2. 另在final上分别把yaw修正、speed修正和两者修正设为0，基线参考依赖当前观测重新计算，pitch仍来自final。三流各11策略×6validation case×128步=25344步。all_control三流selected/final端点另6策略×6case×128步=4608步，总上限29952环境步；RL训练步为0。
3. 记录每case与聚合mean/worst/tail RMSE、相对同流final改善、物理修正RMS/max、raw饱和率及selected/final动作漂移。全部在各混合策略自身闭环状态上统计，不假定作用可加，不把单通道替换改善说成唯一根因。
4. 先核对旧selection、validation manifest、检查点和源文件摘要。新诊断代码/协议使用UTF-8 LF，冻结输入后运行；config.yaml、metrics.csv、summary.txt和Python图表保留，旧模型和实验不改写。
5. 依据三个流及其父权限对照的诊断，提出唯一一项最小稳定化干预，交父agent审阅后再固定新训练协议；本诊断不启动候选搜索或正式训练。结果另放独立报告，协议不后加结果。
