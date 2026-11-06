"""Recompute bounded counterfactual returns, retain support warnings, draw focused plots."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import json
from pathlib import Path

from .fixed_pinn_demo import digest
from .pitch_cross_wind_diagnostic import read_csv, write_csv, write_json
from .pitch_action_diagnostic import totals

TEXT = {'case_id', 'split', 'family', 'variant', 'direction'}


def numeric(rows):
    return [{k:v if k in TEXT else float(v) for k, v in r.items()} for r in rows]


def read_gzip(path):
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
        return numeric(csv.DictReader(f))


def paired(rows, fork=False):
    keys = ('run_id', 'case_id', 'anchor', 'horizon') if fork else ('run_id', 'case_id')
    parents = {tuple(r[k] for k in keys):r for r in rows if r['variant']=='parent'}
    output = []
    for r in rows:
        base = parents[tuple(r[k] for k in keys)]
        delta = {f'delta_{k}':r[k]-base[k] for k in ('rmse_w', 'mean_error_w', 'discounted_return', 'tracking_return', 'action_return')}
        if fork:
            index = int(r['direction'][-1])-1 if r['direction'].startswith('unit') else None
            q = 'q_mean' if index is None else f'q_{index}'
            delta['delta_q_mean'] = r['q_mean']-base['q_mean']
            delta['delta_q_actor'] = r[q]-base[q]
            delta['q_sign_opposes_return'] = int(abs(delta['delta_q_actor'])>1e-5 and abs(delta['delta_discounted_return'])>1e-5 and
                                                  delta['delta_q_actor']*delta['delta_discounted_return']<0)
            delta['q_critics_disagree_on_sign'] = int(any(r[f'q_{i}']-base[f'q_{i}']>1e-5 for i in range(3)) and
                                                       any(r[f'q_{i}']-base[f'q_{i}']<-1e-5 for i in range(3)))
        output.append(dict(r, **delta))
    return output


def aggregate(rows, fork=False):
    import numpy as np
    groups = defaultdict(list)
    columns = ['run_id', 'split', 'family', 'target_w', 'variant'] + (['horizon'] if fork else [])
    for r in rows:
        groups[tuple(r[k] for k in columns)].append(r)
    output = []
    for key, part in groups.items():
        row = dict(zip(columns, key), cases=len(part))
        for k in ('delta_rmse_w', 'delta_mean_error_w', 'delta_discounted_return', 'delta_tracking_return', 'delta_action_return'):
            row['mean_'+k] = float(np.mean([r[k] for r in part]))
        row['rmse_improved_count'] = sum(r['delta_rmse_w'] < -1 for r in part)
        row['return_improved_count'] = sum(r['delta_discounted_return'] > 1e-5 for r in part)
        if fork:
            row['q_opposite_count'] = sum(r['q_sign_opposes_return'] for r in part)
            row['local_support_outside_count'] = sum(r['local_pitch_outside_fraction']>0 for r in part)
            row['q_opposite_inside_local_count'] = sum(r['q_sign_opposes_return'] for r in part if r['local_pitch_outside_fraction']==0)
            row['q_critic_disagreement_count'] = sum(r['q_critics_disagree_on_sign'] for r in part)
        output.append(row)
    return output


def verify(root):
    import numpy as np
    import yaml
    import torch
    from .algorithm import MADDPG
    config = yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    summary = json.loads((root/'summary.txt').read_text(encoding='utf-8'))
    audits = json.loads((root/'jobs.json').read_text(encoding='utf-8'))
    prior_source = Path(config['previous'])
    prior_cfg = yaml.safe_load((prior_source/'config.yaml').read_text(encoding='utf-8'))
    source = Path(prior_cfg['source'])
    selection = json.loads((source/'selection.json').read_text(encoding='utf-8'))
    bounds = []
    for r in selection['results']:
        agent, _ = MADDPG.load(r['best']['checkpoint'])
        actions = agent.replay.data['actions'][:agent.replay.size, :, 1]
        bounds.append((actions.min(0), actions.max(0)))
    max_metric = max_reward = max_actuator = 0.
    full_rows = fork_rows = 0
    support_rows, gradient_alignment = [], []
    for job in audits:
        out = Path(job['path'])
        assert all(digest(out/n)==h for n, h in job['hashes'].items())
        for mode in ('full', 'fork'):
            traces = read_gzip(out/f'{mode}_trajectories.csv.gz')
            groups = defaultdict(list)
            for row in traces:
                groups[(row['variant'], row['anchor'])].append(row)
                max_reward = max(max_reward, abs(row['reward']-row['tracking_reward']-row['action_reward']))
                assert abs((row['error_w']/15e6)**2*100 + row['tracking_reward']) < 1e-9
                for i in range(3):
                    before, command, after = (row[f'pitch_{k}_{i}'] for k in ('before', 'command', 'actual'))
                    expected = before+np.clip((1-np.exp(-.5))*(command-before), -.00872664626, .00872664626)
                    max_actuator = max(max_actuator, abs(expected-after))
                    assert 0 <= command <= .22 and 0 <= after <= .22
            table = numeric(read_csv(out/('metrics.csv' if mode=='full' else 'fork_metrics.csv')))
            if mode=='full':
                full_parent = groups[('parent', -1)]
            else:
                for anchor in (32, 96):
                    for fork_row, full_row in zip(groups[('parent', anchor)], full_parent[anchor:anchor+32]):
                        assert fork_row['error_w']==full_row['error_w']
                        assert fork_row['reward']==full_row['reward']
                    starts = [data[0] for (variant, a), data in groups.items() if a==anchor]
                    for i in range(3):
                        assert len({r[f'pitch_before_{i}'] for r in starts})==1
            for row in table:
                anchor = row['anchor'] if mode=='fork' else -1
                data = groups[(row['variant'], anchor)]
                horizon = int(row['horizon']) if mode=='fork' else 128
                actual = totals(data[:horizon], .99)
                for k, value in actual.items():
                    difference = abs(value-row[k])
                    max_metric = max(max_metric, difference)
                    assert difference <= max(1e-7, abs(value)*1e-11), (k, difference)
                if mode=='full':
                    lo, hi = bounds[int(row['run_id'])]
                    array = np.array([[v[f'executed_pitch_normalized_{i}'] for i in range(3)] for v in data])
                    support_rows.append(dict(run_id=row['run_id'], case_id=row['case_id'], variant=row['variant'],
                        global_pitch_outside_fraction=float(np.mean((array<lo)|(array>hi)))))
            if mode=='full':
                full_rows += len(traces)
            else:
                fork_rows += len(traces)
        gradients = numeric(read_csv(out/'gradients.csv'))
        for gradient in gradients:
            anchor, unit = int(gradient['anchor']), int(gradient['unit'])
            positive, negative = f'unit{unit}_+0.005', f'unit{unit}_-0.005'
            upper = groups[(positive, anchor)][0][f'executed_pitch_normalized_{unit-1}']
            lower = groups[(negative, anchor)][0][f'executed_pitch_normalized_{unit-1}']
            assert upper > lower
            row = dict(gradient)
            for horizon in (8, 32):
                plus = next(r for r in table if r['anchor']==anchor and r['horizon']==horizon and r['variant']==positive)
                minus = next(r for r in table if r['anchor']==anchor and r['horizon']==horizon and r['variant']==negative)
                slope = (plus['discounted_return']-minus['discounted_return'])/(upper-lower)
                row[f'realized_g{horizon}_finite_action_slope'] = slope
                row[f'own_q_gradient_opposes_g{horizon}_slope'] = int(abs(slope)>1e-5 and abs(row['q_diagonal_gradient_per_normalized_action'])>1e-5 and
                    slope*row['q_diagonal_gradient_per_normalized_action']<0)
                row[f'ensemble_gradient_opposes_g{horizon}_slope'] = int(abs(slope)>1e-5 and abs(row['ensemble_gradient_per_normalized_action'])>1e-5 and
                    slope*row['ensemble_gradient_per_normalized_action']<0)
                row['either_direction_outside_local_support'] = int(plus['local_pitch_outside_fraction']>0 or minus['local_pitch_outside_fraction']>0)
            gradient_alignment.append(row)
    assert full_rows==287232 and fork_rows==143616
    assert max_reward < 1e-5 and max_actuator < 1e-12
    assert all(digest(p)==h for p, h in config['protected_hashes'].items())
    full = paired(numeric(read_csv(root/'metrics.csv')))
    forks = paired(numeric(read_csv(root/'fork_metrics.csv')), fork=True)
    assert len(full)==2244 and len(forks)==8976
    write_csv(root/'full_paired.csv', full)
    write_csv(root/'fork_paired.csv', forks)
    write_csv(root/'full_aggregate.csv', aggregate(full))
    write_csv(root/'fork_aggregate.csv', aggregate(forks, fork=True))
    write_csv(root/'full_global_support.csv', support_rows)
    write_csv(root/'gradient_alignment.csv', gradient_alignment)
    rank_groups = defaultdict(list)
    for r in forks:
        if r['variant']!='parent':
            rank_groups[(r['run_id'], r['split'], r['family'], r['target_w'], r['horizon'])].append(r)
    rank_summary = []
    for keys, part in rank_groups.items():
        usable = [r for r in part if abs(r['delta_q_actor'])>1e-5 and abs(r['delta_discounted_return'])>1e-5]
        inside = [r for r in usable if r['local_pitch_outside_fraction']==0]
        rank_summary.append(dict(zip(('run_id','split','family','target_w','horizon'), keys),
            all_nonparent_slots=len(part), non_tie_slots=len(usable), own_q_opposite=sum(r['q_sign_opposes_return'] for r in usable),
            inside_local_non_tie_slots=len(inside), inside_local_own_q_opposite=sum(r['q_sign_opposes_return'] for r in inside),
            critic_sign_disagreement=sum(r['q_critics_disagree_on_sign'] for r in usable),
            mean_q_opposite=sum(abs(r['delta_q_mean'])>1e-5 and r['delta_q_mean']*r['delta_discounted_return']<0 for r in usable)))
    write_csv(root/'ranking_summary.csv', rank_summary)
    groups = {(r['run_id'], r['case_id'], r['anchor'], r['variant'], r['horizon']):r for r in forks}
    reversals = []
    for r in forks:
        if r['horizon'] != 8 or r['variant']=='parent':
            continue
        later = groups[(r['run_id'], r['case_id'], r['anchor'], r['variant'], 32)]
        reversals.append(dict(run_id=r['run_id'], case_id=r['case_id'], split=r['split'], family=r['family'],
            target_w=r['target_w'], anchor=r['anchor'], variant=r['variant'],
            delta_g8=r['delta_discounted_return'], delta_g32=later['delta_discounted_return'],
            benefit8_loss32=int(r['delta_discounted_return']>1e-5 and later['delta_discounted_return']<-1e-5)))
    write_csv(root/'horizon_reversals.csv', reversals)
    result = dict(jobs=len(audits), full_trajectory_rows=full_rows, fork_trajectory_rows=fork_rows,
                  max_metric_recompute_difference=max_metric, max_reward_components_difference=max_reward,
                  max_actuator_reconstruction_difference_rad=max_actuator,
                  protected_files_unchanged=True, rl_training_steps=0, test_access=False,
                  baseline_max_replay_difference_w=summary['maximum_parent_replay_difference_w'])
    write_json(root/'verification.json', result)
    print(json.dumps(result), flush=True)
    return full, forks, audits


def figures(root, full, forks, audits):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .midterm_figures import style
    from .pitch_cross_wind_review import FAMILY
    style()
    out = root/'figures'
    if out.exists():
        raise FileExistsError('choose new figures directory rather than overwrite')
    out.mkdir()
    weak = [r for r in full if r['run_id']==0 and r['split']=='validation' and r['family']=='ramp' and r['target_w']==3.45e6]
    fig, axes = plt.subplots(3, 2, figsize=(15, 13), constrained_layout=True)
    for i, initial in enumerate((.025, .04, .055)):
        part = [r for r in weak if r['initial_pitch_rad']==initial]
        labels = [r['variant'] for r in part]
        for j, key in enumerate(('delta_rmse_w', 'delta_discounted_return')):
            values = [r[key]/(1000 if j==0 else 1) for r in part]
            axes[i, j].bar(range(17), values, color=['#277e91' if (v<0 if j==0 else v>0) else '#c55f50' for v in values])
            axes[i, j].axhline(0, color='gray', linewidth=.6)
            axes[i, j].set_xticks(range(17), labels, rotation=80, fontsize=8)
            axes[i, j].set_title(f'初始桨距 {initial:.3f} rad')
            axes[i, j].set_ylabel('Δ RMSE / kW（负为改善）' if j==0 else 'Δ 折扣回报（正为改善）')
    fig.suptitle('流0 · 慢变3.45 MW：固定17个持续修正的完整128秒闭环', fontsize=17)
    fig.savefig(out/'weak_full_grid.png', dpi=130)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    for ax, horizon in zip(axes, (8, 32)):
        part = [r for r in forks if r['horizon']==horizon and r['variant']!='parent']
        for outside, marker in ((False, 'o'), (True, 'x')):
            rows = [r for r in part if (r['local_pitch_outside_fraction']>0)==outside]
            ax.scatter([r['delta_q_actor'] for r in rows], [r['delta_discounted_return'] for r in rows],
                       s=12, alpha=.25, marker=marker, label='超出近邻动作范围' if outside else '近邻范围内')
        highlight = [r for r in part if r['run_id']==0 and r['family']=='ramp' and r['target_w']==3.45e6 and r['split']=='validation']
        ax.scatter([r['delta_q_actor'] for r in highlight], [r['delta_discounted_return'] for r in highlight],
                   s=25, facecolors='none', edgecolors='#c63b36', label='流0慢变高目标')
        ax.axhline(0, color='gray', linewidth=.6)
        ax.axvline(0, color='gray', linewidth=.6)
        ax.set_xscale('symlog', linthresh=1e-4)
        ax.set_yscale('symlog', linthresh=1e-4)
        ax.set_xlabel('修正动作 ΔQ（逐机用本机Critic，共同用三机均值）')
        ax.set_ylabel(f'实际 {horizon} 秒 ΔG（一次修正后恢复父策略）')
        ax.set_title('异号象限表示有限回报方向与Q相反')
    axes[0].legend(fontsize=8)
    fig.suptitle('当前状态的Q排序与实际有限步回报；有限G不等于长期期望Q', fontsize=15)
    fig.savefig(out/'q_return_directions.png', dpi=140)
    plt.close(fig)
    ids = list(dict.fromkeys(r['case_id'] for r in full))
    directions = ('common', 'unit1', 'unit2', 'unit3')
    matrix = np.array([[next(r['delta_rmse_w']/1000 for r in full if r['case_id']==cid and r['run_id']==run and r['variant']==d+'_-0.005')
                        for run in range(3) for d in directions] for cid in ids])
    fig, ax = plt.subplots(figsize=(13, 14), constrained_layout=True)
    scale = max(abs(matrix.min()), abs(matrix.max()), 1)
    im = ax.imshow(matrix, cmap='RdBu_r', vmin=-scale, vmax=scale, aspect='auto')
    ax.set_xticks(range(12), [f'流{r} {d}' for r in range(3) for d in directions], rotation=45, ha='right')
    row_labels = []
    for i, cid in enumerate(ids):
        row = next(r for r in full if r['case_id']==cid and r['run_id']==0 and r['variant']=='parent')
        split = '训练' if row['split']=='train' else '验证'
        row_labels.append(f"{i:02d} {split} {FAMILY[row['family']]} {row['target_w']/1e6:.2f}MW β0={row['initial_pitch_rad']:.3f}")
    ax.set_yticks(range(44), row_labels, fontsize=8)
    ax.set_title('固定 -0.005 rad 修正：全部44场与三流（ΔRMSE，红色退化）')
    fig.colorbar(im, ax=ax, label='Δ RMSE / kW')
    fig.savefig(out/'all_case_regressions.png', dpi=130)
    plt.close(fig)
    examples = ['validation_ramp_1_pitch0.04_initial_'+str(p) for p in (.025, .04, .055)]
    examples += ['validation_ramp_0_pitch0.04_initial_0.04', 'validation_stress_u7.55_p4500000.0_b0.055']
    display = ('parent', 'common_-0.005', 'common_+0.005', 'unit2_-0.005', 'unit3_-0.005')
    colors = ('#2563a6', '#168275', '#c79a28', '#a1479a', '#b65c36')
    for index, cid in enumerate(examples):
        job = next(j for j in audits if j['run_id']==0 and j['case_id']==cid)
        data = read_gzip(Path(job['path'])/'full_trajectories.csv.gz')
        fig, axes = plt.subplots(6, 1, figsize=(13, 13), sharex=True, constrained_layout=True)
        for name, color in zip(display, colors):
            rows = [r for r in data if r['variant']==name]
            t = [r['response_step'] for r in rows]
            axes[0].plot(t, [r['farm_power_w']/1e6 for r in rows], color=color, label=name)
            axes[1].plot(t, [r['error_w']/1000 for r in rows], color=color)
            for i in range(3):
                axes[2+i].plot(t, np.rad2deg([r[f'pitch_actual_{i}'] for r in rows]), color=color)
            axes[5].step(t, [r['pitch_rate_fraction'] for r in rows], color=color, linewidth=.8, where='post')
        target = data[0]['target_w']/1e6
        axes[0].axhline(target, color='black', linestyle=':')
        axes[1].axhline(0, color='gray', linewidth=.7)
        axes[0].legend(ncols=3, fontsize=8)
        for ax, label in zip(axes, ('功率 / MW', '误差 / kW', '机1桨距 / °', '机2桨距 / °', '机3桨距 / °', '速率限制比例')):
            ax.set_ylabel(label)
            ax.grid(alpha=.2)
            ax.set_xlim(0, 128)
        axes[-1].set_xlabel('回合时间 / s')
        fig.suptitle(f'流0 · {cid}\n固定修正的完整闭环诊断，不是新训练策略', fontsize=13)
        fig.savefig(out/f'full_case_{index}.png', dpi=120)
        plt.close(fig)
    write_json(out/'manifest.json', dict(overview_figures=3, selected_complete_case_figures=5,
                                       note='fixed examples and fixed displayed variants; no best-case selection'))
    print(json.dumps(dict(figures=8, path=str(out))), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify', 'figures'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = verify(args.output.resolve())
    if args.command=='figures':
        figures(args.output.resolve(), *data)


if __name__ == '__main__':
    main()
