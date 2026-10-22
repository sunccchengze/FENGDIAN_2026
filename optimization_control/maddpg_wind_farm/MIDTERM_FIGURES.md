# 中期答辩图表（2026-10-22）

本任务仅整理已冻结的十二输入模型随机入口实验，使用 Python/Matplotlib 绘图；不重训、不修改算法、模型或原始实验，不用 AI 图像生成。当前结论限于合成入口与合成标签代理模型的软件联调。

## 产物约定

- 绘图源代码：`midterm_figures.py`，只读 `../experiments/20261022_random_wind_training/` 的保存数据。
- 输出：`../experiments/20261022_midterm_figures/`，沿用日期实验目录规范；保留 `config.yaml`、`metrics.csv`、`summary.txt`，另存 PNG/PDF/SVG、每图说明和来源 SHA256。
- 图片以 `01_` 至 `07_` 加英文用途命名；适合答辩插图，不覆盖原实验图。输出目录必须不存在；复画时指定新的输出目录，旧产物不自动清理。
- 数据检查：复算全部测试 RMSE；验证三条训练流与 P/PI 的汇总；图中展示固定第 0 流及预先指定的中间目标场景，不按表现筛选。

## 已完成图组

1. 十二输入与六输出的闭环接口及本轮控制权限。
2. 平稳湍流、慢变、阵风的入口风速与风向。
3. 三条独立训练流的平均/最差验证 RMSE，保留原晋级门槛。
4. 初始、训练后、固定桨距、P、PI 的独立测试比较，展示随机流差异。
5. 常规风况与低风高目标压力场分别比较，不将压力场混入常规均值。
6. 固定第 0 流在中间功率目标下的阵风/慢变时序，展示初始与训练后及 P/PI。
7. 同一阵风场的机舱跟踪、桨距与转速执行轨迹，说明统一执行器。

每张图的说明需要包含“读图方法、图中证据、能支持的结论、适用边界”，并明确 kW/MW、误差棒定义及代表场景选择方法。

## 交付与验证

7张图均提供PNG（220 dpi）、PDF、SVG，共21个图形文件。已逐张检查中文、图例、单位、曲线和排版；使用 `-W error` 运行，未出现字体或绘图警告。

- [每张图的意义与建议讲稿](../experiments/20261022_midterm_figures/图表说明.md)
- [闭环接口](../experiments/20261022_midterm_figures/01_closed_loop.png)
- [三类入口](../experiments/20261022_midterm_figures/02_random_inflow.png)
- [验证学习曲线](../experiments/20261022_midterm_figures/03_validation_learning.png)
- [独立测试对照](../experiments/20261022_midterm_figures/04_independent_test.png)
- [分场景与压力场](../experiments/20261022_midterm_figures/05_scenario_breakdown.png)
- [功率跟踪与有符号误差](../experiments/20261022_midterm_figures/06_power_tracking.png)
- [实际执行器轨迹](../experiments/20261022_midterm_figures/07_actuator_replay.png)

从30,720行保存轨迹复算240条测试RMSE，差值为0 W；均值与原汇总一致。19个模型/队友源文件与6个策略检查点摘要一致，绘图读取的13个输入文件在运行前后不变。绘图数值保存在本轮 `metrics.csv`，配置记录展示选择、字体及来源摘要。

推荐正文使用01、02、03、04、06；05、07用于局限分析和追问。当前平均误差下降58.5%，但流0、慢变及压力场仍弱于PI，不将平均值写成稳定优势。

```powershell
.venv\Scripts\python.exe -B -X utf8 -W error -m optimization_control.maddpg_wind_farm.midterm_figures --output optimization_control/experiments/20261022_midterm_figures_new
```

复现时使用不存在的新输出目录。源代码、摘要和绘图数值纳入Git，图片及长讲稿按可再生产物保留在本地实验目录。
