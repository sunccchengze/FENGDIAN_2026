#!/usr/bin/env python3
"""
Nature-level Figure Factory for Wind Farm Yaw Optimization
Uses scipilot-figure-skill (setup_style, export_figure) + nature-figure contract
Data inventory: cases.csv, cases_multi.csv, cases_array.csv, windrose, POD, fields, fields_array
Outputs: figures_nature/*.pdf,*.png (300 DPI)
"""
import sys
sys.path.insert(0, 'scripts/nature')
from setup_style import setup_style
from export_figure import export_figure
import os, json, glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import seaborn as sns
from scipy.ndimage import gaussian_filter

# ensure output dir
os.makedirs('figures_nature', exist_ok=True)

# Setup Nature style
setup_style(journal='nature', lang='en')
# Okabe-Ito colorblind safe
OKABE = ['#000000', '#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7']
PAL = sns.color_palette('colorblind')

print("=== Data Inventory ===")
# Load cases
cases = pd.read_csv('cases.csv')
cases_multi = pd.read_csv('cases_multi.csv')
cases_array = pd.read_csv('cases_array.csv')
cases_windrose_opt = pd.read_csv('cases_windrose_opt.csv')
with open('optimizer_result.json') as f:
    opt = json.load(f)
with open('array_independent_result.json') as f:
    arr_ind = json.load(f)
with open('20260810洪/extracted/ppo_eval_traces.json') as f:
    ppo_eval = json.load(f)

# POD
pod = np.load('pod_results/pod_data.npz')
print(f"cases {cases.shape}, multi {cases_multi.shape}, array {cases_array.shape}")
print(f"POD modes {pod['modes'].shape}, energy cum {pod['energy_cum']}")

# Helper to add panel labels a,b,c,d Nature style
def add_labels(axes, style='nature'):
    if not isinstance(axes, (list, np.ndarray)):
        axes = [axes]
    labels = ['a','b','c','d','e','f','g','h']
    for i, ax in enumerate(axes):
        if i < len(labels):
            ax.text(-0.18, 1.05, labels[i], transform=ax.transAxes,
                    fontsize=9, fontweight='bold', va='top', ha='right')

# -------------------------------------------------
# Fig1: Tandem yaw optimization (P1,P2,Ptot, Gain)
print("\n[Fig1] Tandem")
fig, axes = plt.subplots(2,1, figsize=(3.5, 3.8), sharex=True, constrained_layout=True)
ax = axes[0]
ax.plot(cases['yaw_1'], cases['power_1'], label='P1 upstream', color=PAL[0], lw=1.2, marker='o', ms=3)
ax.plot(cases['yaw_1'], cases['power_2'], label='P2 downstream', color=PAL[2], lw=1.2, marker='s', ms=3)
ax.plot(cases['yaw_1'], cases['power_total'], label='Ptot', color=PAL[3], lw=1.5, marker='^', ms=3)
# optimal marker
opt_row = cases.loc[cases['power_total'].idxmax()]
ax.axvline(opt_row['yaw_1'], color='#a87817', ls='--', lw=0.8, alpha=0.7)
ax.plot(opt_row['yaw_1'], opt_row['power_total'], color='#a87817', marker='*', ms=8, mec='white')
ax.set_ylabel('Power (kW)')
ax.legend(frameon=False, fontsize=6, loc='upper left')
ax.set_title('Two-turbine 5D tandem', fontsize=8, pad=4)

ax2 = axes[1]
base = cases[cases['yaw_1']==0]['power_total'].values[0]
gain = (cases['power_total']-base)/base*100
ax2.plot(cases['yaw_1'], gain, color='#1e675c', lw=1.5, marker='D', ms=3)
ax2.fill_between(cases['yaw_1'], gain, 0, where=(gain>0), color='#1e675c', alpha=0.15)
ax2.axhline(0, color='k', lw=0.5, ls='-')
ax2.axvline(opt_row['yaw_1'], color='#a87817', ls='--', lw=0.8, alpha=0.7)
ax2.text(opt_row['yaw_1']+1, gain.max()-0.5, f"+{gain.max():.1f}% @ {opt_row['yaw_1']}°", fontsize=6, color='#a87817', fontweight='bold')
ax2.set_xlabel('Upstream yaw γ₁ (°)')
ax2.set_ylabel('Gain vs 0° (%)')
add_labels(axes)
export_figure(fig, 'figures_nature/fig1_tandem_yaw', formats=['pdf','png','svg'], size_inches=(3.5,3.8), dpi=300, grayscale_preview=True)
plt.close()

# -------------------------------------------------
# Fig2: Multi-wind heatmap + slices
print("[Fig2] Multi-wind")
# Pivot gain matrix
pivot = cases_multi.pivot(index='U_inf', columns='yaw_1', values='gain_pct')
# gains already? cases_multi has gain_pct? Let's compute if not
if 'gain_pct' not in cases_multi.columns:
    # compute
    base_map = cases_multi[cases_multi['yaw_1']==0].set_index('U_inf')['power_total']
    cases_multi['gain_pct'] = cases_multi.apply(lambda r: (r['power_total']-base_map[r['U_inf']])/base_map[r['U_inf']]*100, axis=1)
    pivot = cases_multi.pivot(index='U_inf', columns='yaw_1', values='gain_pct')

fig, axes = plt.subplots(1,2, figsize=(7.2, 2.8), constrained_layout=True, gridspec_kw={'width_ratios':[1.2,1]})
ax = axes[0]
sns.heatmap(pivot, cmap='viridis', center=0, vmin=-5, vmax=9, annot=True, fmt='.1f', annot_kws={'fontsize':5},
            cbar_kws={'label':'Gain (%)','shrink':0.8}, linewidths=0.3, linecolor='white', ax=ax)
ax.set_xlabel('Yaw γ₁ (°)'); ax.set_ylabel('Wind speed (m/s)')
ax.set_title('Gain matrix (yaw × wind)', fontsize=8)

ax = axes[1]
for u in sorted(cases_multi['U_inf'].unique()):
    sub = cases_multi[cases_multi['U_inf']==u].sort_values('yaw_1')
    ax.plot(sub['yaw_1'], sub['gain_pct'], marker='o', ms=3, lw=1, label=f'{u:.0f} m/s')
ax.axhline(0, color='k', lw=0.5)
ax.set_xlabel('Yaw γ₁ (°)'); ax.set_ylabel('Gain (%)')
ax.legend(frameon=False, fontsize=6, title='U∞', title_fontsize=6)
add_labels(axes)
export_figure(fig, 'figures_nature/fig2_multi_wind', formats=['pdf','png'], size_inches=(7.2,2.8), dpi=300)
plt.close()

# -------------------------------------------------
# Fig3: 3x3 Array comparison
print("[Fig3] Array")
fig, axes = plt.subplots(1,2, figsize=(7.2, 3.0), constrained_layout=True)
# left: total power bar
ax = axes[0]
labels = ['Baseline\n0°','Unified\n30°','Independent\n[30,20,0]°']
powers = [arr_ind['power_none'], arr_ind['power_unified'], arr_ind['power_independent']]
gains = [0, arr_ind['gain_unified_pct'], arr_ind['gain_independent_pct']]
colors = [PAL[0], PAL[2], PAL[3]]
bars = ax.bar(labels, powers, color=colors, edgecolor='black', linewidth=0.5, width=0.6)
for bar, g in zip(bars, gains):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+50, f"+{g:.1f}%", ha='center', va='bottom', fontsize=7, fontweight='bold')
ax.set_ylabel('Total power (kW)')
ax.set_title('3×3 array strategy', fontsize=8)
# right: per-turbine
ax = axes[1]
turb = [f'T{i+1}' for i in range(9)]
p_none = arr_ind['turbine_powers_none']
p_ind = arr_ind['turbine_powers_independent']
x = np.arange(len(turb))
w=0.35
ax.bar(x - w/2, p_none, w, label='Baseline', color='#94a3b8', edgecolor='black', lw=0.4)
ax.bar(x + w/2, p_ind, w, label='Independent', color=PAL[3], edgecolor='black', lw=0.4)
ax.set_xticks(x); ax.set_xticklabels(turb, fontsize=6)
ax.set_ylabel('Turbine power (kW)')
ax.legend(frameon=False, fontsize=6)
ax.set_title('Per-turbine gain (Row1 +30°, Row2 +20°)', fontsize=8)
add_labels(axes)
export_figure(fig, 'figures_nature/fig3_array', formats=['pdf','png'], size_inches=(7.2,3.0), dpi=300)
plt.close()

# -------------------------------------------------
# Fig4: Wake field contour 0° vs 25°
print("[Fig4] Wake fields")
# Load fields for 0 and 25
def load_field(yaw):
    path=f"fields/case_{yaw+7:04d}.npz" if yaw>=0 else f"fields/case_{yaw+7:04d}.npz"
    # Actually mapping yaw -30..30 step5 -> case 1..13
    # yaw -30 => case1, -25=>2,...0=>7, 25=>12
    idx = int((yaw+30)/5) # 0..12
    case_id = idx+1
    d=np.load(f"fields/case_{case_id:04d}.npz")
    return d['x'], d['y'], d['u']

x0,y0,u0 = load_field(0)
x25,y25,u25 = load_field(25)

fig, axes = plt.subplots(1,2, figsize=(7.2, 3.0), sharex=True, sharey=True, constrained_layout=True)
for ax, x,y,u, ttl in zip(axes, [x0,x25],[y0,y25],[u0,u25], ['0° baseline (2190 kW)','+25° optimal (2368 kW +8.13%)']):
    # contourf
    levels = np.linspace(2,8.5,30)
    cf = ax.contourf(x, y, u, levels=levels, cmap='viridis', extend='both')
    # turbine markers
    ax.plot(0,0,'^', ms=8, color='white', mec='black', mew=0.8)
    ax.plot(630,0,'^', ms=8, color='white', mec='black', mew=0.8)
    ax.text(0, 30, 'T1', ha='center', va='bottom', fontsize=7, color='white', fontweight='bold')
    ax.text(630, 30, 'T2', ha='center', va='bottom', fontsize=7, color='white', fontweight='bold')
    ax.set_title(ttl, fontsize=8)
    ax.set_xlabel('x (m)'); ax.set_ylabel('y (m)')
add_labels(axes)
cbar = fig.colorbar(cf, ax=axes, shrink=0.8, label='Wind speed (m/s)', pad=0.02)
cbar.ax.tick_params(labelsize=6)
export_figure(fig, 'figures_nature/fig4_wake_contour', formats=['pdf','png'], size_inches=(7.2,3.0), dpi=300)
plt.close()

# -------------------------------------------------
# Fig5: POD modes and energy
print("[Fig5] POD")
fig, axes = plt.subplots(2,2, figsize=(7.2, 4.5), constrained_layout=True)
# energy
ax = axes[0,0]
ax.bar(np.arange(1, len(pod['energy_frac'])+1), pod['energy_frac']*100, color=PAL[0], edgecolor='black', lw=0.4)
ax.set_xlabel('Mode index'); ax.set_ylabel('Energy fraction (%)')
ax.set_title('POD energy per mode', fontsize=8)
ax.set_xticks([1,2,3,4,5])

ax = axes[0,1]
ax.plot(np.arange(1, len(pod['energy_cum'])+1), pod['energy_cum']*100, marker='o', color=PAL[3], lw=1.2)
ax.axhline(95, color='gray', ls='--', lw=0.6)
ax.axhline(97.97, color='#a87817', ls='--', lw=0.8, label='97.97% (2 modes)')
ax.set_xlabel('Cumulative modes'); ax.set_ylabel('Cumulative energy (%)')
ax.legend(frameon=False, fontsize=6)
ax.set_title('Cumulative energy', fontsize=8)

# mode 0 and 1 contour
for idx, axi in enumerate([axes[1,0], axes[1,1]]):
    mode = pod['modes'][idx]
    # mode shape (64,128)
    im = axi.contourf(pod['x'], pod['y'], mode, levels=20, cmap='RdBu_r', extend='both')
    axi.set_title(f'Mode {idx} ({pod["energy_frac"][idx]*100:.1f}%)', fontsize=8)
    axi.set_xlabel('x (m)'); axi.set_ylabel('y (m)')
    plt.colorbar(im, ax=axi, shrink=0.7)

add_labels(axes.flatten())
export_figure(fig, 'figures_nature/fig5_pod', formats=['pdf','png'], size_inches=(7.2,4.5), dpi=300)
plt.close()

# -------------------------------------------------
# Fig6: Array baseline vs independent flow
print("[Fig6] Array flow")
# Load fields_array
base = np.load('fields_array/baseline.npz')
indep = np.load('fields_array/independent.npz')
fig, axes = plt.subplots(2,1, figsize=(7.2, 4.0), sharex=True, sharey=True, constrained_layout=True)
for ax, d, ttl in zip(axes, [base, indep], ['Baseline 0° (8095 kW)','Independent [30°,20°,0°] (10041 kW +24%)']):
    x=d['x']; y=d['y']; u=d['u']
    cf = ax.contourf(x, y, u, levels=np.linspace(2,9,25), cmap='viridis')
    # turbine positions: 3x3 grid: x = 0, 630,1260? Actually D=126, 5D=630, rows x 0,630,1260? y -378,0,378?
    D=126
    for rx in [0, 5*D, 10*D]:
        for cy in [-3*D,0,3*D]:
            ax.plot(rx, cy, '^', ms=5, color='white', mec='black', mew=0.5)
    ax.set_title(ttl, fontsize=8)
    ax.set_xlabel('x (m)'); ax.set_ylabel('y (m)')
add_labels(axes)
cbar = fig.colorbar(cf, ax=axes, shrink=0.8, label='U (m/s)')
export_figure(fig, 'figures_nature/fig6_array_flow', formats=['pdf','png'], size_inches=(7.2,4.0), dpi=300)
plt.close()

# -------------------------------------------------
# Fig7: Windrose optimal gain
print("[Fig7] Windrose")
# For simplicity, plot gain vs wind direction at 8 m/s
sub = cases_windrose_opt[cases_windrose_opt['U_inf']==8.0].sort_values('wind_direction')
fig, ax = plt.subplots(figsize=(3.5, 3.5), subplot_kw=dict(polar=True), constrained_layout=True)
theta = np.deg2rad(sub['wind_direction'])
gain = sub['gain_pct']
# polar bar
bars = ax.bar(theta, gain, width=np.deg2rad(20), color=plt.cm.viridis(gain/gain.max()), edgecolor='black', lw=0.3, alpha=0.8)
ax.set_theta_zero_location('N')
ax.set_theta_direction(-1)
ax.set_title('Optimal gain vs wind direction (8 m/s)', fontsize=8, pad=20)
export_figure(fig, 'figures_nature/fig7_windrose', formats=['pdf','png'], size_inches=(3.5,3.5), dpi=300)
plt.close()

# -------------------------------------------------
# Fig8: Comprehensive 4-panel main figure for Nature
print("[Fig8] Main 4-panel")
fig = plt.figure(figsize=(7.2, 6.0), constrained_layout=True)
gs = fig.add_gridspec(2,2)
ax0 = fig.add_subplot(gs[0,0])
# tandem gain vs yaw
base = cases[cases['yaw_1']==0]['power_total'].values[0]
gain = (cases['power_total']-base)/base*100
ax0.plot(cases['yaw_1'], gain, color='#1e675c', lw=1.2, marker='o', ms=3)
ax0.axvline(25, ls='--', color='#a87817', lw=0.8)
ax0.set_xlabel('Yaw (°)'); ax0.set_ylabel('Gain (%)')
ax0.set_title('Tandem gain', fontsize=8)

ax1 = fig.add_subplot(gs[0,1])
# array bar
ax1.bar(['None','Unified','Indep'], [arr_ind['power_none'], arr_ind['power_unified'], arr_ind['power_independent']], color=[PAL[0],PAL[2],PAL[3]], edgecolor='black', lw=0.4)
ax1.set_ylabel('Power (kW)'); ax1.set_title('3×3 array', fontsize=8)

ax2 = fig.add_subplot(gs[1,0])
# POD cum energy
ax2.plot(np.arange(1, len(pod['energy_cum'])+1), pod['energy_cum']*100, marker='o', color=PAL[3])
ax2.set_xlabel('Modes'); ax2.set_ylabel('Cum. energy (%)')
ax2.set_title('POD', fontsize=8)

ax3 = fig.add_subplot(gs[1,1])
# wake contour quick
x,y,u = x0,y0,u0
ax3.contourf(x,y,u, levels=15, cmap='viridis')
ax3.set_title('Wake 0°', fontsize=8)
ax3.set_xlabel('x (m)'); ax3.set_ylabel('y (m)')

for ax, lab in zip([ax0,ax1,ax2,ax3], ['a','b','c','d']):
    ax.text(-0.18, 1.05, lab, transform=ax.transAxes, fontsize=9, fontweight='bold')

export_figure(fig, 'figures_nature/fig8_main', formats=['pdf','png'], size_inches=(7.2,6.0), dpi=300)
plt.close()

# -------------------------------------------------
# Fig9: Real PPO evaluation trajectory from the audited seed-42 checkpoint
print("[Fig9] Audited PPO evaluation trajectory")
rep = ppo_eval['representative_episode']
summary = ppo_eval['summary']
t = np.asarray(rep['time_s'])
target = np.asarray(rep['power_target_kw'])
actual = np.asarray(rep['power_actual_kw'])
settle = float(rep['settling_time_s'])
fig, ax = plt.subplots(figsize=(3.5, 2.8), constrained_layout=True)
ax.fill_between(t, target * 0.985, target * 1.015, color='#94a3b8', alpha=0.18,
                label='±1.5% settling band')
ax.plot(t, target, color='#4d4d4d', ls='--', lw=1.0, label='Target power')
ax.plot(t, actual, color='#0070f3', lw=1.3, label='PPO output')
ax.axvline(settle, color='#f5a623', ls=':', lw=0.9,
           label=f'Settling {settle:.1f} s')
ax.set_xlabel('Time (s)')
ax.set_ylabel('Power (kW)')
ax.legend(frameon=False, fontsize=5.8, loc='best')
ax.set_title(f"Audited PPO trajectory · episode {rep['episode']}", fontsize=8)
ax.text(0.98, 0.62,
        f"Representative rule: median episode MAE\n200-episode mean MAE {summary['steady_state_mae_pct']:.3f}%",
        transform=ax.transAxes, ha='right', va='center', fontsize=5.5, color='#4d4d4d')
add_labels([ax])
export_figure(fig, 'figures_nature/fig9_tracking', formats=['pdf','png'], size_inches=(3.5,2.8), dpi=300)
plt.close()

print("\nAll figures exported to figures_nature/")
# List files
import glob
for f in sorted(glob.glob('figures_nature/*')):
    print(f)

