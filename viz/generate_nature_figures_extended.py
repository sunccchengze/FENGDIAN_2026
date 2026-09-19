#!/usr/bin/env python3
"""
Extended Nature Figure Factory - 疯狂画图模式
基于现有数据的深度可视化，覆盖所有可画类型
"""
import sys
sys.path.insert(0, 'scripts/nature')
from setup_style import setup_style
from export_figure import export_figure
import os, json, glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

os.makedirs('figures_nature/extended', exist_ok=True)
setup_style(journal='nature', lang='en')
PAL = sns.color_palette('colorblind')
OKABE = ['#000000', '#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7']

cases = pd.read_csv('cases.csv')
cases_multi = pd.read_csv('cases_multi.csv')
cases_array = pd.read_csv('cases_array.csv')
with open('array_independent_result.json') as f:
    arr = json.load(f)
with open('20260810洪/extracted/ppo_eval_traces.json') as f:
    ppo_eval = json.load(f)
pod = np.load('pod_results/pod_data.npz')

def add_labels(axes):
    if not isinstance(axes, (list, np.ndarray)):
        axes = [axes]
    labs = ['a','b','c','d','e','f']
    for i, ax in enumerate(axes):
        ax.text(-0.18, 1.05, labs[i], transform=ax.transAxes, fontsize=9, fontweight='bold')

# Fig10: Box + strip for multi-wind gain distribution per yaw
print("Fig10 box+strip")
fig, ax = plt.subplots(figsize=(7.2, 3.0), constrained_layout=True)
sns.boxplot(data=cases_multi, x='yaw_1', y='gain_pct', color='white', showfliers=False, linewidth=0.6, ax=ax)
sns.stripplot(data=cases_multi, x='yaw_1', y='gain_pct', hue='U_inf', palette='viridis', size=4, alpha=0.7, ax=ax, jitter=True)
ax.set_xlabel('Yaw γ₁ (°)'); ax.set_ylabel('Gain (%)')
ax.legend(title='Wind (m/s)', frameon=False, fontsize=6)
add_labels([ax])
export_figure(fig, 'figures_nature/extended/fig10_gain_box_strip', formats=['pdf','png'], size_inches=(7.2,3.0), dpi=300)
plt.close()

# Fig11: Correlation heatmap of powers
print("Fig11 corr")
corr = cases[['power_1','power_2','power_total']].corr()
fig, ax = plt.subplots(figsize=(3.5,3.0), constrained_layout=True)
sns.heatmap(corr, annot=True, fmt='.2f', cmap='RdBu_r', vmin=-1, vmax=1, center=0, square=True, linewidths=0.5, linecolor='white', cbar_kws={'shrink':0.8}, ax=ax)
ax.set_title('Power correlation (tandem)', fontsize=8)
export_figure(fig, 'figures_nature/extended/fig11_corr', formats=['pdf','png'], size_inches=(3.5,3.0), dpi=300)
plt.close()

# Fig12: Distribution histograms of Ptot across yaws per wind
print("Fig12 hist")
fig, axes = plt.subplots(2,2, figsize=(7.2,4.0), constrained_layout=True)
axes=axes.flatten()
for i, u in enumerate(sorted(cases_multi['U_inf'].unique())):
    sub = cases_multi[cases_multi['U_inf']==u]
    axes[i].hist(sub['power_1']+sub['power_2'], bins=15, color=PAL[i], edgecolor='black', lw=0.3, alpha=0.7)
    axes[i].set_title(f'U={u} m/s', fontsize=8)
    axes[i].set_xlabel('Ptot (kW)'); axes[i].set_ylabel('Count')
add_labels(axes)
export_figure(fig, 'figures_nature/extended/fig12_hist', formats=['pdf','png'], size_inches=(7.2,4.0), dpi=300)
plt.close()

# Fig13: 3D surface gain
print("Fig13 3D")
from mpl_toolkits.mplot3d import Axes3D
pivot = cases_multi.pivot(index='U_inf', columns='yaw_1', values='gain_pct')
X, Y = np.meshgrid(pivot.columns, pivot.index)
Z = pivot.values
fig = plt.figure(figsize=(3.5,3.0), constrained_layout=True)
ax = fig.add_subplot(111, projection='3d')
surf = ax.plot_surface(X, Y, Z, cmap='viridis', edgecolor='none', alpha=0.9)
ax.set_xlabel('Yaw (°)'); ax.set_ylabel('Wind (m/s)'); ax.set_zlabel('Gain (%)')
ax.set_title('Gain surface', fontsize=8)
fig.colorbar(surf, shrink=0.6, label='Gain (%)')
export_figure(fig, 'figures_nature/extended/fig13_3d_gain', formats=['pdf','png'], size_inches=(3.5,3.0), dpi=300)
plt.close()

# Fig14: POD coefficients vs yaw
print("Fig14 POD coeff")
# pod_analysis.py stores coefficients = diag(S) @ Vt, shape (mode, snapshot).
coeff = pod['coefficients']
yaws = pod['yaw_angles']
fig, ax = plt.subplots(figsize=(3.5,2.6), constrained_layout=True)
ax.plot(yaws, coeff[0, :], marker='o', label='Coeff Mode0 (dipole)', color=PAL[0])
ax.plot(yaws, coeff[1, :], marker='s', label='Coeff Mode1 (recovery)', color=PAL[2])
ax.set_xlabel('Yaw (°)'); ax.set_ylabel('Coefficient')
ax.legend(frameon=False, fontsize=6)
ax.set_title('POD coeff vs yaw', fontsize=8)
add_labels([ax])
export_figure(fig, 'figures_nature/extended/fig14_pod_coeff', formats=['pdf','png'], size_inches=(3.5,2.6), dpi=300)
plt.close()

# Fig15: Array per-turbine gain waterfall
print("Fig15 waterfall")
fig, ax = plt.subplots(figsize=(3.5,3.0), constrained_layout=True)
turb = np.arange(1,10)
p_none = np.array(arr['turbine_powers_none'])
p_ind = np.array(arr['turbine_powers_independent'])
gain = (p_ind - p_none)/p_none*100
colors = ['#ad5038' if g<0 else '#1e675c' for g in gain]
ax.bar(turb, gain, color=colors, edgecolor='black', lw=0.4)
ax.axhline(0, color='k', lw=0.5)
ax.set_xlabel('Turbine T1-T9'); ax.set_ylabel('Gain vs baseline (%)')
ax.set_title('Per-turbine gain independent', fontsize=8)
for i,g in enumerate(gain):
    ax.text(i+1, g+ (0.5 if g>0 else -1.5), f"{g:+.1f}%", ha='center', va='bottom' if g>0 else 'top', fontsize=5)
add_labels([ax])
export_figure(fig, 'figures_nature/extended/fig15_waterfall', formats=['pdf','png'], size_inches=(3.5,3.0), dpi=300)
plt.close()

# Fig16: Violin + strip for array power distribution across yaw strategies
print("Fig16 violin")
# Build long form from cases_array (13 rows, each with 9 turbine powers + total)
# Melt total power vs yaw
fig, ax = plt.subplots(figsize=(3.5,2.8), constrained_layout=True)
# Use total power
ax.plot(cases_array['yaw_upstream'], cases_array['power_total'], marker='o', color=PAL[3], lw=1.2)
ax.fill_between(cases_array['yaw_upstream'], cases_array['power_total'], 8095, color=PAL[3], alpha=0.15)
ax.axvline(30, ls='--', color='#a87817', lw=0.8, label='Unified optimum 30°')
ax.set_xlabel('Unified yaw (°)'); ax.set_ylabel('3×3 total power (kW)')
ax.set_title('Array unified yaw sweep', fontsize=8)
ax.legend(frameon=False, fontsize=6)
export_figure(fig, 'figures_nature/extended/fig16_array_sweep', formats=['pdf','png'], size_inches=(3.5,2.8), dpi=300)
plt.close()

# Fig17: Audited 200-episode PPO evaluation distributions
print("Fig17 audited PPO distributions")
episodes = ppo_eval['episodes']
summary = ppo_eval['summary']
mae = np.asarray([r['steady_mae_pct'] for r in episodes])
settle = np.asarray([r['settling_time_s'] for r in episodes])
fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), constrained_layout=True)
for ax, values, ylabel, color in [
    (axes[0], mae, 'Steady-state MAE (%)', '#0070f3'),
    (axes[1], settle, 'Settling time (s)', '#E69F00'),
]:
    ax.boxplot(values, positions=[1], widths=0.28, patch_artist=True, showfliers=False,
               boxprops={'facecolor':'white', 'edgecolor':'#4d4d4d', 'linewidth':0.8},
               medianprops={'color':'#171717', 'linewidth':1.0},
               whiskerprops={'color':'#888888', 'linewidth':0.7},
               capprops={'color':'#888888', 'linewidth':0.7})
    order = np.argsort(values)
    jitter = np.linspace(-0.16, 0.16, len(values))
    x = np.empty_like(jitter)
    x[order] = 1 + jitter
    ax.scatter(x, values, s=8, color=color, alpha=0.46, edgecolors='none')
    ax.set_xlim(0.72, 1.28)
    ax.set_xticks([1]); ax.set_xticklabels(['200 episodes'])
    ax.set_ylabel(ylabel)
axes[0].axhline(summary['steady_state_mae_pct'], color='#0070f3', ls='--', lw=0.8)
axes[0].text(1.27, summary['steady_state_mae_pct'],
             f" mean {summary['steady_state_mae_pct']:.3f}%", ha='right', va='bottom', fontsize=6)
axes[1].axhline(summary['settling_time_p95_s'], color='#E69F00', ls='--', lw=0.8)
axes[1].text(1.27, summary['settling_time_p95_s'],
             f" p95 {summary['settling_time_p95_s']:.3f} s", ha='right', va='bottom', fontsize=6)
axes[0].set_title('Tracking error distribution', fontsize=8)
axes[1].set_title('Settling-time distribution', fontsize=8)
add_labels(axes)
export_figure(fig, 'figures_nature/extended/fig17_ppo_mae', formats=['pdf','png'], size_inches=(7.2,2.8), dpi=300)
plt.close()

print("Extended done")
for f in sorted(glob.glob('figures_nature/extended/*.png')):
    print(f)
