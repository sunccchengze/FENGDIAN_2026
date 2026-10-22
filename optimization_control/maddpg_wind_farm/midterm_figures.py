"""Render midterm-defense evidence from frozen CSVs; no model or training calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np
import yaml


SOURCE = Path("optimization_control/experiments/20261022_random_wind_training")
OUTPUT = Path("optimization_control/experiments/20261022_midterm_figures")
COLORS = {"initial": "#8C98A5", "selected": "#2065A6", "fixed": "#ABB6C1",
          "p": "#D59232", "pi": "#218C78"}
LABELS = {"initial": "初始 MADDPG", "selected": "训练后 MADDPG", "fixed": "固定桨距",
          "p": "P 控制", "pi": "PI 控制"}
FAMILIES = {"stationary": "平稳湍流", "ramp": "慢变来流", "gust": "阵风", "low_wind_stress": "低风高目标"}
METHODS = ("initial", "fixed", "p", "pi", "selected")
FOOTER = "数据范围：冻结十二输入代理模型的软件联调；尚无实测/CFD精度验证。误差越低越好。"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_text(path, text):
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def style():
    installed = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((n for n in ("Microsoft YaHei", "Noto Sans SC", "SimHei") if n in installed), None)
    if chosen is None:
        raise RuntimeError("A Chinese font (Microsoft YaHei / Noto Sans SC / SimHei) is required")
    plt.rcParams.update({"font.family": chosen, "font.size": 12, "axes.titlesize": 14,
                         "axes.labelsize": 12, "axes.unicode_minus": False,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#D0D7DE", "text.color": "#243746",
                         "axes.labelcolor": "#243746", "xtick.color": "#465966",
                         "ytick.color": "#465966", "grid.alpha": .2,
                         "figure.facecolor": "white", "axes.facecolor": "white",
                         "pdf.fonttype": 42, "svg.fonttype": "path"})
    return chosen


def finish(fig, output, stem, title, subtitle):
    fig.suptitle(title, x=.06, y=.98, ha="left", fontsize=22, fontweight="bold")
    fig.text(.06, .925, subtitle, fontsize=11, color="#526878")
    fig.text(.06, .025, FOOTER, fontsize=10, color="#647785")
    fig.subplots_adjust(top=.85, bottom=.13, left=.09, right=.96, wspace=.3, hspace=.4)
    for ext in ("png", "pdf", "svg"):
        fig.savefig(output / f"{stem}.{ext}", dpi=220, facecolor="white")
    plt.close(fig)


def run_means(metrics, method, family=None):
    grouped = defaultdict(list)
    for r in metrics:
        if r["controller"] != method:
            continue
        if (family is None and r["family"] == "low_wind_stress") or (family is not None and r["family"] != family):
            continue
        grouped[int(r["run_id"])].append(float(r["rmse_w"]) / 1000)
    return np.array([np.mean(grouped[k]) for k in sorted(grouped)])


def trace(traces, case, method, run_id=0):
    rid = str(run_id if method in ("initial", "selected", "final") else -1)
    part = [r for r in traces if r["case_id"] == case and r["controller"] == method and r["run_id"] == rid]
    part.sort(key=lambda r: int(r["step"]))
    if len(part) != 128:
        raise ValueError(f"Expected 128 saved steps: {case}/{method}/{rid}, got {len(part)}")
    return part


def values(rows, field, scale=1.):
    return np.array([float(r[field]) for r in rows]) * scale


def degrees(rad):
    return np.rad2deg((np.asarray(rad) + np.pi) % (2 * np.pi) - np.pi)


def audit(source, config, selection, metrics, traces):
    groups = defaultdict(list)
    for r in traces:
        groups[(r["stage"], r["run_id"], r["controller"], r["case_id"])].append(r)
    maximum = 0.
    for r in metrics:
        part = groups[(r["stage"], r["run_id"], r["controller"], r["case_id"])]
        assert len(part) == config["protocol"]["horizon"]
        errors = values(part, "farm_power_w") - float(r["target_w"])
        measured = float(np.sqrt(np.mean(errors ** 2)))
        difference = abs(measured - float(r["rmse_w"]))
        maximum = max(maximum, difference)
        assert difference < .001, (r["case_id"], difference)
        np.testing.assert_allclose(errors, values(part, "error_w"), atol=1e-8, rtol=0)
    assert len(metrics) == 240 and len(traces) == 30720
    for method in METHODS:
        n = len(run_means(metrics, method))
        assert n == (3 if method in ("initial", "selected") else 1)
    aggregate = {r["controller"]: r for r in read_csv(source / "test/aggregate.csv")}
    for method in METHODS:
        a = run_means(metrics, method)
        np.testing.assert_allclose(np.mean(a) * 1000, float(aggregate[method]["mean_rmse_w"]), atol=1e-6, rtol=0)
    protected = {**config["source_hashes"], **selection["hashes"]}
    assert all(digest(k) == v for k, v in protected.items())
    assert digest(source / "bank/manifest.json") == selection["bank_sha256"]
    return {"metrics_recomputed": len(metrics), "trace_rows": len(traces),
            "max_rmse_difference_w": maximum, "protected_files": len(protected),
            "source_and_checkpoint_hashes_match": True}


def interface_figure(output):
    fig, ax = plt.subplots(figsize=(14, 7.875))
    ax.set_axis_off()
    ax.set(xlim=(0, 1), ylim=(0, 1))
    def box(x, y, w, h, title, text, color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012", facecolor=color, edgecolor="#D5E0E7"))
        ax.text(x + w/2, y + h - .065, title, ha="center", va="center", fontsize=15, fontweight="bold")
        ax.text(x + w/2, y + h/2 - .025, text, ha="center", va="center", fontsize=11, linespacing=1.8)
    def arrow(a, b, color="#526878"):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=16, color=color, lw=1.8))
    box(.01, .59, .25, .32, "随机入口生成器", "风速 U∞(t) · 风向 θ∞(t)\n背景湍流强度 TI\n平稳 / 慢变 / 阵风", "#EEF5FB")
    box(.37, .57, .28, .36, "冻结 PINN / 代理模型", "12输入：U∞、θ∞、TI\n＋三机 γ、β、ω（共9个）\n6输出：三机 P、Ueff", "#ECF6F1")
    box(.76, .59, .23, .32, "反馈与评估", "三机状态与全场功率\n功率目标 / 跟踪误差\n验证选模 → 独立测试", "#FFF5E8")
    box(.04, .05, .43, .29, "MADDPG / P / PI", "本轮 RL 只学习桨距参考\n偏航跟踪风向、转速按运行曲线调度\n三种方法采用相同后台规则", "#EEF5FB")
    box(.60, .05, .36, .29, "统一执行器", "接收偏航 / 桨距 / 转速目标\n施加限速、时间常数和边界\n机舱朝向 ψ → 失配角 γ=wrap(ψ−θ∞)", "#F2F0F8")
    arrow((.26,.76),(.37,.76))
    arrow((.65,.76),(.76,.76))
    arrow((.47,.20),(.60,.20))
    ax.plot([.87,.87,.25],[.59,.44,.44], color="#526878", lw=1.8)
    arrow((.25,.44),(.25,.34))
    ax.plot([.77,.77,.51],[.34,.49,.49], color="#526878", lw=1.8)
    arrow((.51,.49),(.51,.57))
    ax.text(.72,.51,"实际运行点",fontsize=10)
    finish(fig, output, "01_closed_loop", "优化模块已接成可回放的闭环", "本轮软件链路｜三台直线等间距风机｜冻结模型，未进行物理精度验收")


def inflow_figure(source, output):
    fig, axes = plt.subplots(3, 2, figsize=(14, 9))
    for i, family in enumerate(("stationary", "ramp", "gust")):
        rows = read_csv(source / "bank" / f"test_{family}_1.csv")
        t = values(rows, "time_s")
        background = values(rows, "background_m_s") + values(rows, "event_m_s")
        axes[i,0].plot(t, values(rows,"speed_m_s"), color=COLORS["selected"], lw=1.5, label="实际入口风速")
        axes[i,0].plot(t, background, color=COLORS["p"], ls="--", lw=1.8, label="背景＋慢变/阵风分量")
        axes[i,0].set(ylabel="入口风速 / (m/s)", title=FAMILIES[family] + f" · 背景 TI={float(rows[0]['background_ti']):.0%}", ylim=(7.5,10.5))
        axes[i,1].plot(t, degrees(values(rows,"direction_rad")), color=COLORS["pi"], lw=1.8)
        axes[i,1].set(ylabel="来流方向 / °", title="方向采用圆周角换算，零点附近连续展示", ylim=(-4.8,4.8))
        for ax in axes[i]:
            ax.grid(axis="y"); ax.set_xlim(0,127)
            if i==2: ax.set_xlabel("时间 / s")
    axes[0,0].legend(fontsize=10, loc="upper right")
    finish(fig, output, "02_random_inflow", "训练入口覆盖三类随时间变化的来流", "固定展示独立测试各类的第2条风轨迹；TI为背景谱参数，不等于每条短记录的std/mean")


def training_figure(source, output, config):
    fig, axes = plt.subplots(1,2,figsize=(14,7.875))
    colors = ("#2065A6", "#218C78", "#A169A4")
    for run_id in range(3):
        rows = read_csv(source / f"pitch_run_{run_id}/segment_000/metrics.csv")
        for j,field in enumerate(("validation_rmse_w", "worst_validation_rmse_w")):
            x=values(rows,"steps"); y=values(rows,field,.001)
            axes[j].plot(x,y,marker="o",lw=2.4,color=colors[run_id],label=f"训练流 {run_id}")
    for ax,limit,title in zip(axes,(config["protocol"]["gate"]["mean_validation_rmse_w"]/1000,
                                  config["protocol"]["gate"]["worst_validation_rmse_w"]/1000),
                             ("六场验证的平均误差", "六场验证中的最大误差")):
        ax.axhline(limit,ls="--",color="#A24B40",lw=1.6,label=f"原定门槛 {limit:.0f} kW")
        ax.set(xlabel="每条训练流的环境步数",ylabel="功率跟踪 RMSE / kW",title=title,ylim=(0,1850))
        ax.set_xticks([0,4096,8192,12288,16384],["0","4,096","8,192","12,288","16,384"])
        ax.grid(axis="y"); ax.legend(fontsize=10)
    finish(fig, output, "03_validation_learning", "三条训练流均有改善，精度门槛仍未通过", "每流16,384步、总49,152步；只依据验证集选模，失败后停止增加学习通道")


def overall_figure(metrics, output):
    fig, ax = plt.subplots(figsize=(14,7.875))
    for i,method in enumerate(METHODS):
        a=run_means(metrics,method); mean=float(np.mean(a)); sd=float(np.std(a,ddof=1)) if len(a)>1 else 0.
        ax.bar(i,mean,width=.58,color=COLORS[method],alpha=.88)
        if len(a)>1:
            ax.errorbar(i,mean,yerr=sd,fmt="none",color="#243746",capsize=6,lw=1.5)
            ax.scatter(i+np.linspace(-.13,.13,len(a)),a,color="#243746",s=42,zorder=5)
        ax.text(i,mean+sd+38,f"{mean:.2f}"+(f" ± {sd:.2f}" if len(a)>1 else ""),ha="center",fontsize=12,fontweight="bold")
    ax.set_xticks(range(len(METHODS)),[LABELS[m] for m in METHODS])
    ax.set(ylabel="18场常规独立测试的平均 RMSE / kW",ylim=(0,1320))
    ax.grid(axis="y"); ax.set_axisbelow(True)
    improvement=100*(1-np.mean(run_means(metrics,"selected"))/np.mean(run_means(metrics,"initial")))
    ax.text(.98,.90,f"相对初始均值降低 {improvement:.1f}%\n训练流0仍弱于PI，尚无稳定优势结论",transform=ax.transAxes,ha="right",fontsize=12,
            bbox=dict(boxstyle="round,pad=.7",fc="#EEF5FB",ec="none"))
    finish(fig,output,"04_independent_test","独立测试显示学习有效，但不能宣称稳定优于 PI", "黑点为3条独立训练流；误差棒为流均值的样本标准差。P/PI与固定桨距为同场景确定性对照")


def family_figure(metrics, output):
    fig,axes=plt.subplots(1,2,figsize=(14,7.875),gridspec_kw={"width_ratios":[2.2,1]})
    width=.23
    for j,method in enumerate(("selected","p","pi")):
        means=[float(np.mean(run_means(metrics,method,f))) for f in ("stationary","ramp","gust")]
        x=np.arange(3)+(j-1)*width
        axes[0].bar(x,means,width=width,color=COLORS[method],label=LABELS[method])
        for a,b in zip(x,means): axes[0].text(a,b+12,f"{b:.1f}",ha="center",fontsize=10)
        stress=float(np.mean(run_means(metrics,method,"low_wind_stress")))
        axes[1].bar(j,stress,width=.6,color=COLORS[method])
        axes[1].text(j,stress+35,f"{stress:.1f}",ha="center",fontsize=11)
    axes[0].set_xticks(range(3),[FAMILIES[f] for f in ("stationary","ramp","gust")])
    axes[0].set(title="常规场景：MADDPG在慢变来流中仍弱于PI",ylabel="平均 RMSE / kW",ylim=(0,800))
    axes[0].legend(fontsize=10,loc="upper right")
    axes[1].set_xticks(range(3),["MADDPG","P","PI"])
    axes[1].set(title="压力场：7.6 m/s，目标4.4 MW",ylabel="平均 RMSE / kW",ylim=(0,2150))
    for ax in axes: ax.grid(axis="y"); ax.set_axisbelow(True)
    finish(fig,output,"05_scenario_breakdown","按场景拆分后，薄弱环节更加清楚", "两面板纵轴尺度不同；压力场单列、不计入常规均值。MADDPG为三流均值，非全局可达性证明")


def tracking_figure(traces, output):
    fig,axes=plt.subplots(2,2,figsize=(14,9),sharex=True)
    for col,family in enumerate(("gust","ramp")):
        case=f"test_{family}_1_pitch0.025"
        initial=trace(traces,case,"initial")
        target=float(initial[0]["target_w"])/1e6
        axes[0,col].axhline(target,color="#243746",ls="--",lw=1.8,label="功率目标")
        for method in ("initial","selected","p","pi"):
            rows=trace(traces,case,method)
            t=values(rows,"step"); power=values(rows,"farm_power_w",1e-6)
            error=values(rows,"error_w",.001)
            rmse=float(np.sqrt(np.mean(error**2)))
            axes[0,col].plot(t,power,lw=1.7,color=COLORS[method],label=f"{LABELS[method]} ({rmse:.0f} kW)",alpha=.95)
            axes[1,col].plot(t,error,lw=1.7,color=COLORS[method])
        axes[0,col].set(title=f"{FAMILIES[family]} · 目标{target:.1f} MW · 初始桨距0.025 rad",ylabel="全场功率 / MW")
        axes[0,col].legend(fontsize=9,loc="upper right",ncol=1)
        axes[1,col].axhline(0,color="#243746",ls="--",lw=1)
        axes[1,col].set(xlabel="时间 / s",ylabel="出力−目标 / kW")
        for ax in axes[:,col]: ax.grid(axis="y"); ax.set_xlim(1,128)
    finish(fig,output,"06_power_tracking","时序对照说明误差来自哪里", "固定使用训练流0与中间测试目标3.3 MW；未按效果挑选场景。图例括号为本场完整回合RMSE")


def actuator_figure(traces, output, config):
    fig,axes=plt.subplots(3,1,figsize=(14,9),sharex=True)
    case="test_gust_1_pitch0.025"
    first=trace(traces,case,"selected"); t=values(first,"step")
    axes[0].plot(t,degrees(values(first,"direction_rad")),color="#243746",ls="--",lw=1.6,label="来流方向")
    for method in ("selected","p","pi"):
        rows=trace(traces,case,method)
        axes[0].plot(t,degrees(values(rows,"heading_1_rad")),color=COLORS[method],label=LABELS[method],lw=1.9)
        axes[1].plot(t,values(rows,"pitch_1",180/np.pi),color=COLORS[method],lw=1.9)
        axes[2].plot(t,values(rows,"speed_1"),color=COLORS[method],lw=1.9)
    axes[0].set(ylabel="机舱朝向 / °",title="T1 机舱跟踪来流；γ由机舱朝向与风向之差计算")
    axes[0].legend(fontsize=10,ncol=4,loc="upper right")
    axes[1].set(ylabel="实际桨距角 / °",title="不同控制器给出不同桨距目标，统一执行器限制实际变化")
    axes[2].set(ylabel="实际转速 / (rad/s)",xlabel="时间 / s",title="相同运行曲线生成转速参考，受统一动力学限制")
    lo=config["base_config"]["environment"]["action_low"][2]
    hi=config["base_config"]["environment"]["action_high"][2]
    axes[2].set_ylim(lo-.03,hi+.03)
    for ax in axes: ax.grid(axis="y"); ax.set_xlim(1,128)
    finish(fig,output,"07_actuator_replay","控制器输出参考值，由同一执行器执行", "阵风、目标3.3 MW、训练流0，仅展示T1；yaw/转速曲线重叠源于同一后台规则，参数尚未按实际机型标定")


def explanations(metrics):
    selected=np.mean(run_means(metrics,"selected"))
    initial=np.mean(run_means(metrics,"initial"))
    sd=np.std(run_means(metrics,"selected"),ddof=1)
    table="\n".join(f"| {LABELS[m]} | {np.mean(run_means(metrics,m)):.2f} |" for m in METHODS)
    return f"""# 中期答辩图表及讲解稿

全部图片由 `midterm_figures.py` 使用 Python/Matplotlib 从冻结实验 CSV 绘制，没有使用 AI 图像生成。每图同时提供 PNG（220 dpi）、PDF、SVG。建议正文用图01、02、03、04、06，图05和07用于局限分析及答辩追问。

数据来源：2026-10-22 十二输入代理模型随机入口实验。三台直线等间距风机；主种子42派生三条独立训练流，各16,384步。当前优先跑通软件闭环，PINN训练副本仍采用合成标签，不能据此宣称真实风场精度或真实发电收益。本组图不将旧九输入模型与新模型结果放在同一性能比较中。

## 图01：优化闭环与接口

![闭环接口](01_closed_loop.png)

**读图与意义：** 上部展示随机入口、代理模型及反馈；下部展示控制器和统一执行器。代理模型外部输入为风速、风向、TI及三机各自的偏航失配角、桨距角、转速，共12维；输出为三机功率与有效风速，共6维。它说明接口和职责已经接通，优化器有了可训练、可评估、可回放的对象。

**建议讲解：** “我完成的是优化闭环：把随机来流接到队友模型，使用相同执行器比较学习控制和传统控制。本轮先让MADDPG只学习桨距，偏航和转速采用共同后台规则。”

**边界：** 这是软件数据流示意，不是完整流场仿真或物理精度证明；本轮没有让RL同时学习三个通道。

## 图02：三类随机入口

![随机来流](02_random_inflow.png)

**读图与意义：** 左列是实际风速和背景加事件分量，右列是风向，三行分别为平稳湍流、慢变和阵风。固定选择各类独立测试的中间目标所对应风轨迹，未挑选“最好看”的记录。它说明环境已经使用随时间变化的入口，而不是只在固定风下训练。

**建议讲解：** “随机入口包含湍流波动、慢变化与阵风，同时给模型传入风向和背景TI。我们先把入口限制在当前模型的约定范围，建立可重复的场景库。”

**边界：** Kaimal单点入口并非TurbSim全场风，不包含完整空间相干结构；TI为背景谱参数，短记录的总标准差/均值不必等于TI。图中方向已换算为零点附近连续角度。风速包络拒绝采样也会影响有限记录统计。

## 图03：训练改善与晋级门槛

![验证曲线](03_validation_learning.png)

**读图与意义：** 三条线表示独立训练流，左图是六场验证的平均RMSE，右图是六场中的最大RMSE；横轴是每流环境步数。两条虚线分别为原定400/500 kW门槛。训练均值从约1290 kW下降至471.79、444.14、433.65 kW，但三流均未达到完整精度门槛。

**建议讲解：** “三次训练都确实学到了降低误差的行为，但精度尚未达到预先设定标准，因此我没有直接增加转速和偏航的学习难度。当前是学习有效，完整能力验收仍未通过。”

**边界：** 这是验证曲线而非训练奖励或独立测试曲线；只在保存的4096步间隔评估。最终检查点恰好也是本轮验证最佳，不证明更长训练仍然稳定，也不等于已经收敛。

## 图04：统一基线下的独立测试

![独立测试](04_independent_test.png)

**读图与意义：** 每条训练流先在18场常规测试上分别求完整回合RMSE，再对这些场景RMSE取平均；MADDPG柱高是三个流均值的平均。黑点对应三个流，误差棒是三个流均值的样本标准差，不是置信区间。P、PI和固定桨距各使用相同场景、后台调度与执行器，仅计算一次确定性对照。

| 控制方法 | 常规平均RMSE / kW |
|---|---:|
{table}

**建议讲解：** “训练后平均误差为{selected:.2f}±{sd:.2f} kW，相对初始的{initial:.2f} kW下降{100*(1-selected/initial):.1f}%。平均值略低于PI，但三次训练中仍有一次弱于PI，所以目前不能宣称稳定或统计显著优于PI。”

**边界：** 测试目标2.7/3.3/3.9 MW和测试风轨迹在选模后启用，压力场不计入本均值。此指标不是所有时间点混合计算的一次RMSE，也不是功率预测精度。

## 图05：分风况表现与压力场

![分场景对照](05_scenario_breakdown.png)

**读图与意义：** 左侧拆分平稳湍流、慢变和阵风；右侧单列固定7.6 m/s、4.4 MW的低风高目标场景。两个面板纵轴不同。MADDPG在慢变场景仍弱于PI（432.08对417.19 kW），压力场也更差（1727.89对1383.30 kW）。

**建议讲解：** “总体均值会掩盖失效场景。我保留了慢变和低风高目标的结果，下一步重点解决欠功率行为和目标响应，而不是仅通过增加控制通道追求更低平均值。”

**边界：** 压力场是固定风，不能称为湍流测试。有限稳态候选扫描显示采样能力缺口，但没有全局功率上界证书，不能把全部跟踪损失都解释成物理不可达。

## 图06：功率跟踪与有符号误差

![功率时序](06_power_tracking.png)

**读图与意义：** 上排是全场功率与3.3 MW目标，下排为“出力−目标”，正值为过发、负值为欠功率。左右分别为阵风与慢变。固定展示第0训练流、初始桨距0.025 rad及测试各类第2条风轨迹；图例中的RMSE只针对本场，不与18场总体均值混淆。

**建议讲解：** “柱状图说明总体误差，时序图进一步显示误差发生在什么时候、表现为过发还是欠功率。这里展示了固定规则选出的场景，包括MADDPG仍表现不理想的部分。”

**边界：** 单场曲线不能替代多场、多随机流统计；并且第0流是预先固定的展示选择，不代表最佳策略。

## 图07：统一执行器的实际运行点

![执行器轨迹](07_actuator_replay.png)

**读图与意义：** 展示同一阵风场T1的机舱朝向、实际桨距与实际转速。机舱跟踪来流方向，偏航失配由两者之差计算。三种控制器的yaw和转速轨迹重叠源于相同后台规则；桨距则由各自功率控制决定，经过同一执行器产生实际运行点。

**建议讲解：** “算法不直接瞬间改变物理状态，而是给出目标值，再由统一执行器施加速率、时间常数与运行边界。这保证P、PI与MADDPG的控制权限和约束一致。”

**边界：** 图中只展示T1的一个场景。完整训练转移审计在上一轮已完成；当前执行器参数是联调假设，不是实际机型标定值。图中的后台转速参考不由RL学习。

## 答辩可使用的结论

“已完成三机优化的软件闭环、随机来流训练、统一传统控制基线、多随机流验证与冻结独立测试。MADDPG能明显降低初始策略的功率跟踪误差，但跨训练流可靠性、慢变跟踪与低风高目标表现尚未达到预设要求。当前以接口和流程验证为主，真实物理精度及发电收益有待仿真或实测数据验证。”

不宜写“已实现真实风场高精度预测”“MADDPG全面优于PI”“三通道协同优化已稳定收敛”。本轮没有新增训练、调参或读取测试后再修改策略。

## 复现与数据核验

从项目根目录运行：

```powershell
.venv\\Scripts\\python.exe -B -X utf8 -m optimization_control.maddpg_wind_farm.midterm_figures --output optimization_control/experiments/20261022_midterm_figures_new
```

输出目录必须不存在，旧图不会自动清理。`config.yaml`记录输入文件摘要和展示选择，`metrics.csv`提供图03至05的绘图数值，`validation.json`记录240条测试RMSE复算与来源检查。原始实验、模型及检查点不被修改。
"""


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument("--source",type=Path,default=SOURCE)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args=parser.parse_args()
    source=args.source.resolve(); output=args.output.resolve()
    if output.exists():
        raise FileExistsError("Choose a new output directory; existing evidence is preserved")
    config=yaml.safe_load((source/"config.yaml").read_text(encoding="utf-8"))
    selection=json.loads((source/"selection.json").read_text(encoding="utf-8"))
    assert config["protocol"]["version"]=="wind12_random_training_v1"
    inputs=[source/n for n in ("config.yaml","selection.json","metrics.csv","test/metrics.csv","test/aggregate.csv","test/trajectories.csv","bank/manifest.json")]
    inputs += [source/f"pitch_run_{r}/segment_000/metrics.csv" for r in range(3)]
    inputs += [source/"bank"/f"test_{f}_1.csv" for f in ("stationary","ramp","gust")]
    hashes={str(p):digest(p) for p in inputs}
    metrics=read_csv(source/"test/metrics.csv"); traces=read_csv(source/"test/trajectories.csv")
    result=audit(source,config,selection,metrics,traces)
    font=style()
    output.mkdir(parents=True,exist_ok=False)
    write_text(output/"config.yaml",yaml.safe_dump(dict(seed=42,source=str(source),purpose="midterm_frozen_evidence_only",
        source_hashes=hashes,font=font,formats=["png","pdf","svg"],png_dpi=220,
        representative_selection=dict(run_id=0,target_w=3300000,initial_pitch_rad=.025,wind_index=1),
        error_bars="sample_std_of_three_run_means_not_confidence_interval",physical_validation=False),allow_unicode=True,sort_keys=False))
    interface_figure(output)
    inflow_figure(source,output)
    training_figure(source,output,config)
    overall_figure(metrics,output)
    family_figure(metrics,output)
    tracking_figure(traces,output)
    actuator_figure(traces,output,config)
    chart_rows=[]
    for group in ("routine",*FAMILIES):
        for method in METHODS:
            a=run_means(metrics,method,None if group=="routine" else group)
            chart_rows.append(dict(figure="04" if group=="routine" else "05",group=group,method=method,run_id="mean",
                step="",value_kw=float(np.mean(a)),std_kw=float(np.std(a,ddof=1)) if len(a)>1 else 0.))
    for run in range(3):
        for row in read_csv(source/f"pitch_run_{run}/segment_000/metrics.csv"):
            for group,field in (("validation_mean","validation_rmse_w"),("validation_worst","worst_validation_rmse_w")):
                chart_rows.append(dict(figure="03",group=group,method="maddpg",run_id=run,step=int(row["steps"]),value_kw=float(row[field])/1000,std_kw=""))
    write_csv(output/"metrics.csv",chart_rows)
    write_text(output/"图表说明.md",explanations(metrics))
    assert all(digest(k)==v for k,v in hashes.items()), "Input file changed during rendering"
    result.update(completed=True,figures=7,rendered_files=21,source_files_unchanged=True,physical_validation=False)
    write_text(output/"validation.json",json.dumps(result,ensure_ascii=False,indent=2))
    write_text(output/"summary.txt",json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False))
    print(output)


if __name__=="__main__":
    main()
