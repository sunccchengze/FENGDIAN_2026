# Nature 级科研绘图工厂 - 成果汇总

## 技能库挖掘
- **仓库**：`sunccchengze/-SKILL-` 分支 `arena/019ff854-skill`（2264 SKILL.md）
- **核心绘图技能**：
  - `scipilot-figure-skill`：科研数据可视化顾问，8 步工作流（理解论证目标→剖析数据→选图→期刊规范→配环境→绘制→三层自检闭环→导出），主动拦截 18 种科研画图禁忌（饼图、双Y、rainbow、小n均值柱等），默认 Okabe-Ito 色盲安全 + 冗余编码，支持中英双语，矢量 PDF/SVG 优先，`setup_style(journal='nature')`，4:3 单栏 3.5in 89mm / 双栏 7.2in 183mm，字号 7-9pt，600 DPI TIFF 备选
  - `nature-figure`：Nature 家族投稿级 Figure 合约（核心结论→证据链→原型→后端→期刊导出契约），强调图表服务科学逻辑，hero panel 优先，统计完整性纳入图内
  - `victor-design-system`：瑞士国际主义网格，莫兰迪工科配色，Vercel 质感

## 数据盘点（可画什么）
- `cases.csv`：13 偏航角 (-30~30° step5 @8m/s) 串列 2 机：P1 1339-1753 kW，P2 436-1023 kW，Ptot 2190-2368 kW，最优 25° +8.13%
- `cases_multi.csv`：4 风速 (6/8/10/12) ×13偏航 =52 工况，增益 -?~+? ，最优随风速上移
- `cases_array.csv`：3×3 九机阵列统一偏航 13 工况：总功率 8095→9299→10041 kW，统一 30° +14.87%，独立 [30,20,0] +24.04%
- `array_independent_result.json`：greedy_yaws [30,30,30,20,20,20,0,0,0]，per-turbine baseline vs independent
- `fields/*.npz`：13 个 hub 高度 2D 切片 (128×64, 64×128)，已高斯平滑 sigma0.8 + 边界 8 m/s，case_0009(+10°) 经 5°/15° 平均修复条带
- `fields_array/*.npz`：baseline vs independent 3×3 流场 (128×64)
- `pod_results/pod_data.npz`：10 模态 (64×128)，energy_frac [76.38%,21.59%,...] 累积 97.97% 前2阶，偶极子+自恢复
- `cases_windrose_opt.csv`：12风向×4风速最优偏航，0°风向 8m/s 最优 0°（对齐），90°风向 (串列) 最优 25°，增益
- `optimizer_result.json`：8 m/s 0°→25° 2190→2368 kW

## 已生成图表（17 张 Nature 级 + 灰度预览）

### 主工厂 9 张（figures_nature/）
1. **fig1_tandem_yaw**：Tandem 2 机 5D 串列偏航优化，P1/P2/Ptot vs yaw + gain vs yaw，最优 25° 标注，金星号，填色增益区间
2. **fig2_multi_wind**：(a) 热力图 yaw×U_inf 增益矩阵 viridis，(b) 定风速增益切片折线，多风速趋势
3. **fig3_array**：(a) 总功率柱状 Baseline/Uniform/Independent，(b) 9 机单机功率并列柱，Row1 +30° Row2 +20° 协同
4. **fig4_wake_contour**：0° vs 25° 流场 contourf， turbine ^ 标记，viridis，颜色条 m/s，展示尾流横向偏转放行物理
5. **fig5_pod**：4 面板 - (a) 单模态能量柱 (b) 累积能量折线 97.97% 线 (c) Mode0 偶极子 76.4% (d) Mode1 自恢复 21.6% RdBu_r
6. **fig6_array_flow**：3×3 阵列 baseline vs independent 流场对比，T1-T9 标记，展示走廊清除
7. **fig7_windrose**：极坐标 8 m/s 最优增益 vs 风向，0°风向无增益，90°风向最大增益，viridis 映射
8. **fig8_main**：4 面板综合主图 Nature 主刊 Figure 1 候选：a Tandem gain, b Array power, c POD cum, d Wake 0°
9. **fig9_tracking**：seed 42 PPO 权重的真实代表测试回合，代表回合按 200 回合中位 MAE 规则自动选择，绘制目标功率、实际输出、±1.5% 调节带与调节时间

### 扩展疯狂画图 8 张（figures_nature/extended/）
10. **fig10_gain_box_strip**：箱线+stripplot 展示多风速下增益分布，n=4 风速 per yaw，拦截小样本均值柱错误
11. **fig11_corr**：P1/P2/Ptot 相关性热力图 RdBu_r，半矩阵易读
12. **fig12_hist**：4 风速下 Ptot 直方图分布，偏态 vs 双峰检测
13. **fig13_3d_gain**：3D 曲面 gain = f(yaw, U_inf)，viridis
14. **fig14_pod_coeff**：POD 系数随 yaw 变化，Mode0/1 随偏航线性/非线性
15. **fig15_waterfall**：9 机独立策略增益瀑布，上游 -24% 让利，下游 +100%+ 回升
16. **fig16_array_sweep**：统一偏航扫掠 3×3 总功率曲线，填色增益区间
17. **fig17_ppo_mae**：seed 42 PPO 权重在 200 个固定测试回合中的稳态 MAE 与调节时间分布；不作多模型种子稳定性声明

所有图已按 Nature 单栏 3.5in / 双栏 7.2in 最终尺寸出图，PDF+PNG+SVG+灰度版，300 DPI，字号 6-9pt，Okabe-Ito 色盲安全，冗余编码（线型+marker），viridis/RdBu_r 感知均匀，禁用 rainbow/jet。

## 下一步可画
- POD 重构误差 vs 模态数（降阶精度曲线）
- 3D 体渲染低速泡包络切片动画帧
- 风玫瑰 AEP 年发电量增量 ΔAEP 极坐标 + 风频玫瑰叠加
- PPO 训练 loss 曲线 + 调节时间分布箱线
- 可达域 4 维物理可达域平行坐标

所有脚本：`generate_nature_figures.py` + `generate_nature_figures_extended.py`，Notebook：`notebooks/nature_figures.ipynb`
