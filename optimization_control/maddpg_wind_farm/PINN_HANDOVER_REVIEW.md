# 2026-10-07 队友 PINN 交付检查

交付包含原论文的预训练网络，以及面向三机控制任务的未训练改造网络。原网络权重并非从零开始；
新增九控制输入连接和六个功率/有效风速输出仍需训练。用户已决定当前优先固定风况全流程联调，
允许用合成数据训练副本；实施与结果见 [FIXED_PINN_DEMO.md](FIXED_PINN_DEMO.md)。

## 查明的文件事实

- 来源：`pinn/PINNs_multi_turbine_wake_simulation-outputchange/`，原文件只读保留。
- `OutputChange/prepared_9ms/preparation_report.json`：原坐标到流场网络已加载和冻结，
  输入 `[x,y,z]`，输出 `[u,v,w,p,k,eps]`；保留隐藏参数 3,087,200 个。
- `OutputChange/iochanged_9ms/build_report.json`：状态 `structure_built_and_checked_NOT_trained`，
  `training_performed_on_real_data=false`；新增可训练参数 24,306 个。
- 改造模型控制顺序按机组交错：`yaw1,pitch1,rotor_speed1,...,yaw3,pitch3,rotor_speed3`，
  单位 deg/deg/rpm；输出 `P1,P2,P3,Ueff1,Ueff2,Ueff3`，单位 W/W/W/m/s/m/s/m/s。
- 独立读取 `.keras` 内 HDF5：保存的新增控制矩阵形状 `(9,700)`，非零元素数 0。
  给定位置时，当前权重输出与九个控制量无关。脚本中的临时梯度/连接检查在保存前已恢复。
- 新输出层为重新初始化的线性读出，并未直接继承原六个流场输出的物理含义。
- 训练模板只有表头，位置配置均为 null，交付中未找到新任务的 `trained.keras` 和训练报告。
- `project_config.json` 明确限制九输入版本的风速、风向和 TI 固定；源模型为四机布局。

## 当前边界与下一阶段

外层优化接口仍为默认十二维，适配器把九个控制运行点转换为队友顺序与单位，前三个风况量
用于检查固定上下文。不会丢弃三个风况量后宣称支持变化风况。模型内部负责归一化，外层必须恒等缩放。

当前联调不等待真实标签或物理精度验收。演示准入要求合成来源明确、训练确实完成、
冻结主体未变、输出有限、控制有响应以及固定风况和域检查通过；原正式准入条件独立保留。

后续物理效果验证仍需要实际布局、控制扫描数据、训练模型、独立误差、功率/Ueff 定义、
偏航符号与有效域。合成拟合和短 RL 训练不能代替这些材料。

## 复现与证据

只读审计入口 `audit_handover.py` 针对这次初始结构交付；证据保存于
`optimization_control/experiments/20261007_pinn_handover_audit/` 的 config.yaml/metrics.csv/summary.txt。
报告中的包版本来自安装元数据，缺失元数据不等于模块不能导入；随后实际导入确认原环境
TensorFlow 为 2.21.0、缺少 tf_keras。联调使用项目内独立 TensorFlow 2.16.1 / tf_keras 2.16.0 运行目录。
