# 供用户转交PINN组：当前yaw局部响应复核清单

本文件只整理优化侧已完成的模型内诊断，不向队友发送消息，不修改模型，也不把合成标签公式当作物理真值。当前speed任务暂不开放yaw；希望在任何新yaw训练立项前完成以下复核，具体交付日期由项目协调方确认。

模型为十二输入合成标签联调副本，SHA256：`7506554ac98157e220444e45eb6b19b28a02a57af165bc97237faed28108d451`。仅新增连接拟合，当前没有独立物理精度证书。

## 可复现证据与样本

完整冻结诊断位于`./optimization_control/experiments/20261027_anchor_closeout/`：

- `diagnostic/local_response.csv`：18144条局部扰动响应，含case、时刻、扰动机号、通道和幅度、各机/全场功率差。
- `diagnostic/baseline_0_parent_all/local_states.json`：代表性父策略实际运行点，physical顺序为`[U,theta,TI,gamma1,gamma2,gamma3,beta1,beta2,beta3,omega1,omega2,omega3]`；另外两流及selected/final同类目录保留。
- `audit/local_response_reference_runtime216/metrics.csv`：同一批扰动点的代理/合成标签源响应对照；`summary.json`保存统计及代码/输入摘要。
- 同工作树`maddpg_wind_farm/anchor_closeout_diagnostic.py::scan_model`和`anchor_response_reference.py`保存原始重建方法。所有点来自validation，不使用独立test选择样本或幅度。

复核时读取local_states中的physical，分别仅改变一个gamma（或共同改变三个gamma）0、±1/3/5度，换算为rad并保持其他输入不变，限制在原有效域[-0.4,0.4]rad。使用同一个模型分别预测基准/扰动点，取`P_changed-P_base`。风向为flow-to、从+x逆时针；gamma是机舱相对来流的实际失配角，不是机舱绝对heading。布局为`[[0,0,90],[378,0,90],[756,0,90]]`m。角度rad、omega rad/s、功率W、有效风速m/s；不要重复归一化。

## 需要确认的问题

1. 当前这些运行点上，yaw共同扰动的代理功率响应绝对值中位数0.73kW，合成标签源7.29kW；在标签响应>=1kW的1581条记录中，38.65%方向不一致。逐机扰动约44.04%。这些是相关/重复采样点的描述统计，不是独立样本显著性结论。请核对响应幅度压缩和方向差是否来自拟合能力、采样/损失尺度、输入映射或其他原因。
2. 同一诊断中speed共同/逐机扰动的方向不一致比例约4.18%/3.74%，对照可用于定位通道差异；不能仅凭yaw“非零响应”认定已达到可控代理验收。
3. 若有物理或高保真依据，请说明上述yaw偏移的预期单机损失与尾流收益、对来流方向/机位的依赖，以及有效域。合成标签源本身未标定，不应用它替代物理验证。
4. 控制扫描复核应包含正负方向、0点、基准值和三机完整输出，报告响应误差与符号，而不只报告整域平均拟合误差或选取响应最明显的点。

## 建议交付格式

CSV包含`case_id,run_id,step,turbine,offset_rad`、上述12列SI输入、`P1_W,P2_W,P3_W,Ueff1_m_s,Ueff2_m_s,Ueff3_m_s`，并标记baseline/perturbed及数据来源。JSON附模型与脚本SHA256、输入/输出列序、SI单位、布局、有效域、归一化归属、标签来源及physical_validation布尔值。若模型无需调整，也请提供上述响应差异的解释及适用限制。
