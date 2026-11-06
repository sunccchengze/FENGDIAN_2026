"""Recompute diagnostic evidence and draw every saved case with Python/Matplotlib."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

from .pitch_cross_wind_diagnostic import read_csv, write_csv, write_json, digest, error_parts

METHODS = ('parent_0', 'parent_1', 'parent_2', 'p', 'pi')
COLORS = ('#2563a6', '#a1479a', '#b65c36', '#c99b24', '#168275')
LABELS = ('父策略 流0', '父策略 流1', '父策略 流2', 'P', 'PI')
FAMILY = dict(stationary='平稳湍流', ramp='慢变来流', gust='阵风', low_wind_stress='低风高目标压力')


def numeric_rows(path):
    rows = read_csv(path)
    strings = {'controller', 'case_id', 'split', 'family'}
    return [{k: v if k in strings else float(v) for k, v in r.items()} for r in rows]


def verify(root):
    import numpy as np
    import yaml
    config = yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    summary = json.loads((root/'summary.txt').read_text(encoding='utf-8'))
    metrics = numeric_rows(root/'metrics.csv')
    traces = numeric_rows(root/'trajectories.csv')
    groups = defaultdict(list)
    for r in traces:
        groups[(r['controller'], r['case_id'])].append(r)
    assert len(groups) == len(metrics) == 220
    max_metric_delta = max_pitch_delta = max_wind_delta = 0.
    for metric in metrics:
        rows = groups[(metric['controller'], metric['case_id'])]
        assert [r['decision_step'] for r in rows] == list(range(128))
        assert [r['response_step'] for r in rows] == list(range(1, 129))
        actual = error_parts([r['error_w'] for r in rows])
        for key, value in actual.items():
            difference = abs(value-metric[key])
            assert difference <= max(1e-6, 1e-12*abs(value))
            max_metric_delta = max(max_metric_delta, difference)
        assert abs(metric['decomposition_residual_w2']) < .01
        for j, r in enumerate(rows):
            assert abs(r['farm_power_w']-r['target_w']-r['error_w']) < 1e-8
            if j:
                max_wind_delta = max(max_wind_delta, abs(r['decision_wind_m_s']-rows[j-1]['response_wind_m_s']))
            for i in range(3):
                command, before, after = (r[f'pitch_{n}_{i}'] for n in ('command', 'before', 'actual'))
                assert -1e-7 <= command <= .2200001 and 0 <= after <= .22
                requested = (1-np.exp(-.5))*(command-before)
                expected = before + np.clip(requested, -.00872664626, .00872664626)
                max_pitch_delta = max(max_pitch_delta, abs(expected-after))
                assert abs(expected-after) < 2e-8
                assert r[f'pitch_rate_limited_{i}'] == int(abs(requested) > .00872664626)
                if j:
                    assert abs(before-rows[j-1][f'pitch_actual_{i}']) < 1e-12
        common = groups[('pi', metric['case_id'])]
        for key in ('decision_wind_m_s', 'response_wind_m_s', 'target_w', 'initial_pitch_rad'):
            np.testing.assert_array_equal([r[key] for r in rows], [r[key] for r in common])
    assert max_wind_delta == 0.
    assert all(Path(p).is_file() and digest(p)==h for p, h in config['protected_hashes'].items())
    forecasts = numeric_rows(root/'forecast_metrics.csv')
    gate = all(next(v['relative_improvement'] for v in forecasts if v['split']=='validation' and
                    v['family']==family and v['ahead_s']==1) >= .05 for family in ('all', 'ramp'))
    assert gate == summary['forecast_gate']
    assert summary['candidate_supported'] == bool(summary['weak_variance_dominated_ramp_cases'] and gate)
    verify_rows = dict(metric_rows=len(metrics), trajectory_rows=len(traces), complete_cases=len(groups),
                       max_metric_recompute_difference=max_metric_delta, max_pitch_reconstruction_difference_rad=max_pitch_delta,
                       max_decision_response_wind_alignment_difference_m_s=max_wind_delta,
                       all_controllers_paired=True, protected_files=len(config['protected_hashes']), protected_files_unchanged=True,
                       formal_training_started=False, independent_test_opened=False)
    write_json(root/'verification.json', verify_rows)
    aggregate = []
    for split in ('train', 'validation'):
        for family in FAMILY:
            for method in METHODS:
                part = [r for r in metrics if r['split']==split and r['family']==family and r['controller']==method]
                if not part:
                    continue
                aggregate.append(dict(split=split, family=family, controller=method, cases=len(part),
                    mean_case_rmse_w=float(np.mean([r['rmse_w'] for r in part])),
                    mean_case_bias_squared_w2=float(np.mean([r['bias_squared_w2'] for r in part])),
                    mean_case_variance_w2=float(np.mean([r['variance_w2'] for r in part])),
                    mean_case_signed_error_w=float(np.mean([r['mean_error_w'] for r in part])),
                    mean_pitch_rate_limited_fraction=float(np.mean([r['pitch_rate_limited_fraction'] for r in part])),
                    mean_pitch_command_boundary_fraction=float(np.mean([r['pitch_command_boundary_fraction'] for r in part])),
                    mean_pitch_command_actual_rms_rad=float(np.mean([r['pitch_command_actual_rms_rad'] for r in part]))))
    write_csv(root/'aggregate.csv', aggregate)
    comparisons = []
    for r in metrics:
        if not r['controller'].startswith('parent'):
            continue
        baselines = {b: next(m for m in metrics if m['controller']==b and m['case_id']==r['case_id']) for b in ('p', 'pi')}
        comparisons.append(dict(controller=r['controller'], case_id=r['case_id'], split=r['split'], family=r['family'],
            target_w=r['target_w'], initial_pitch_rad=r['initial_pitch_rad'], parent_rmse_w=r['rmse_w'],
            delta_to_p_w=r['rmse_w']-baselines['p']['rmse_w'], delta_to_pi_w=r['rmse_w']-baselines['pi']['rmse_w']))
    write_csv(root/'paired_differences.csv', comparisons)
    spectra = []
    for (method, cid), rows in groups.items():
        if rows[0]['family'] == 'low_wind_stress':
            continue
        fractions, lag1 = [], []
        for i in range(3):
            command = np.array([r[f'pitch_command_{i}'] for r in rows])
            centered = command-command.mean()
            energy = np.abs(np.fft.rfft(centered))**2
            fractions.append(float(energy[np.fft.rfftfreq(128) >= .25].sum()/energy.sum()) if energy.sum() else 0.)
            lag1.append(float(np.corrcoef(command[:-1], command[1:])[0, 1]) if command.std()>1e-12 else 0.)
        spectra.append(dict(controller=method, case_id=cid, split=rows[0]['split'], family=rows[0]['family'],
                            command_high_frequency_energy_fraction=float(np.mean(fractions)),
                            command_lag1_correlation=float(np.mean(lag1)),
                            note='descriptive_only_not_causal_or_used_for_candidate_selection'))
    write_csv(root/'command_spectrum.csv', spectra)
    print(json.dumps(verify_rows), flush=True)
    return metrics, groups, forecasts, aggregate


def figures(root, metrics, groups, forecasts, aggregate, *, overview_only=False):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from .midterm_figures import style
    style()
    out = root/'figures'
    if out.exists() and not overview_only:
        raise FileExistsError('figures already exist; do not overwrite')
    out.mkdir(exist_ok=overview_only)
    fig, axes = plt.subplots(3, 1, figsize=(16, 14), constrained_layout=True)
    for ax, family in zip(axes, ('stationary', 'ramp', 'gust')):
        part = [r for r in metrics if r['split']=='validation' and r['family']==family]
        ids = list(dict.fromkeys(r['case_id'] for r in part))
        x = np.arange(len(ids))
        for k, (method, color) in enumerate(zip(METHODS, COLORS)):
            rows = [next(r for r in part if r['case_id']==c and r['controller']==method) for c in ids]
            offset = x+(k-2)*.15
            bias = np.array([r['bias_squared_w2'] for r in rows])/1e6
            variance = np.array([r['variance_w2'] for r in rows])/1e6
            ax.bar(offset, bias, .14, color=color)
            ax.bar(offset, variance, .14, bottom=bias, color=color, alpha=.30)
        ax.set_xticks(x, [f"{next(r['target_w'] for r in part if r['case_id']==c)/1e6:.2f} MW\nβ0={next(r['initial_pitch_rad'] for r in part if r['case_id']==c):.3f}" for c in ids])
        ax.set_title(FAMILY[family]+'：深色=平均误差平方，浅色=误差方差')
        ax.set_ylabel('MSE / kW²')
        ax.grid(axis='y')
    axes[0].legend(handles=[Patch(color=c, label=l) for c, l in zip(COLORS, LABELS)], ncols=5, loc='upper left')
    fig.suptitle('训练/验证诊断：逐场误差分解（验证集全部18场，非独立测试）', fontsize=18)
    fig.savefig(out/'validation_decomposition.png', dpi=140)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    families = ('stationary', 'ramp', 'gust', 'all')
    for i, ahead in enumerate((1, 4)):
        values = [next(r['relative_improvement'] for r in forecasts if r['split']=='validation' and r['family']==f and r['ahead_s']==ahead)*100 for f in families]
        ax.bar(np.arange(4)+(i-.5)*.3, values, .28, label=f'{ahead} 秒预测（'+('主指标' if ahead==1 else '辅助检查')+'）')
    ax.axhline(5, color='#b53c3c', linestyle='--', label='预先固定的主指标门槛 5%')
    ax.axhline(0, color='gray', linewidth=.7)
    ax.set_xticks(range(4), [FAMILY.get(f, '总体') for f in families])
    ax.set_ylabel('留出预测 MSE 相对改善 / %')
    ax.set_title('4秒因果风速差的额外预测信息：训练拟合，验证评分')
    ax.legend(ncols=2)
    fig.savefig(out/'forecast_information.png', dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(12, 5), constrained_layout=True)
    for k, (method, color) in enumerate(zip(METHODS, COLORS)):
        values = [next(r['mean_case_rmse_w'] for r in aggregate if r['split']=='validation' and r['family']==f and r['controller']==method)/1000 for f in FAMILY]
        ax.bar(np.arange(4)+(k-2)*.15, values, .14, color=color, label=LABELS[k])
    ax.set_xticks(range(4), list(FAMILY.values()))
    ax.set_ylabel('平均逐场全回合 RMSE / kW')
    ax.set_title('父策略、P、PI 配对诊断；压力场单列，未训练新候选')
    ax.legend(ncols=5)
    fig.savefig(out/'family_comparison.png', dpi=150)
    plt.close(fig)
    if overview_only:
        print(json.dumps(dict(overview_figures=3, output=str(out))), flush=True)
        return
    case_ids = list(dict.fromkeys(r['case_id'] for r in metrics))
    paths = []
    manifest = []
    for ci, cid in enumerate(case_ids):
        example = groups[('pi', cid)]
        fig, axes = plt.subplots(8, 1, figsize=(14, 17), sharex=True, constrained_layout=True)
        decision = np.arange(128)
        response = decision+1
        axes[0].plot(np.arange(129), [example[0]['decision_wind_m_s']]+[r['response_wind_m_s'] for r in example], color='#263b4b')
        axes[0].set_ylabel('入口风速\nm/s')
        axes[1].axhline(example[0]['target_w']/1e6, color='black', linestyle=':', label='目标')
        axes[2].axhline(0, color='gray', linewidth=.6)
        for method, color, label in zip(METHODS, COLORS, LABELS):
            rows = groups[(method, cid)]
            axes[1].plot(response, [r['farm_power_w']/1e6 for r in rows], color=color, label=label, linewidth=1.1)
            axes[2].plot(response, [r['error_w']/1000 for r in rows], color=color, linewidth=1.1)
            for i in range(3):
                axes[3+i].step(decision, np.rad2deg([r[f'pitch_command_{i}'] for r in rows]), where='post', color=color, linestyle='--', alpha=.75, linewidth=.8)
                axes[3+i].plot(response, np.rad2deg([r[f'pitch_actual_{i}'] for r in rows]), color=color, linewidth=1)
            axes[6].step(decision, [np.mean([r[f'pitch_rate_limited_{i}'] for i in range(3)]) for r in rows], color=color, linewidth=.8, where='post')
            axes[7].step(decision, [np.mean([r[f'pitch_command_boundary_{i}'] for i in range(3)]) for r in rows], color=color, linewidth=.8, where='post')
        axes[1].legend(ncols=6, loc='upper left', fontsize=9)
        axes[1].set_ylabel('全场功率\nMW')
        axes[2].set_ylabel('功率误差\nkW')
        for i in range(3):
            axes[3+i].set_ylabel(f'机{i+1}桨距\n°')
            axes[3+i].set_title('虚线：决策时刻命令；实线：响应时刻实际桨距', fontsize=9, loc='right')
        axes[6].set_ylabel('速率限制\n三机占比')
        axes[7].set_ylabel('命令边界\n三机占比')
        axes[7].set_xlabel('回合时间 / s（完整128秒）')
        for ax in axes:
            ax.grid(alpha=.2)
            ax.set_xlim(0, 128)
        for ax in axes[6:]:
            ax.set_ylim(-.05, 1.05)
        split = '训练' if example[0]['split']=='train' else '验证'
        fig.suptitle(f"{split} · {FAMILY[example[0]['family']]} · 目标 {example[0]['target_w']/1e6:.2f} MW · 初始桨距 {example[0]['initial_pitch_rad']:.3f} rad\n代理模型内诊断；不代表物理精度或全局可达性", fontsize=15)
        path = out/f'case_{ci:02d}.png'
        fig.savefig(path, dpi=110)
        plt.close(fig)
        paths.append(path)
        manifest.append(dict(case_id=cid, figure=path.name))
    write_csv(out/'case_figures.csv', manifest)
    from PIL import Image, ImageOps, ImageDraw
    for page, start in enumerate(range(0, len(paths), 12)):
        sheet = Image.new('RGB', (1600, 1620), 'white')
        draw = ImageDraw.Draw(sheet)
        for offset, path in enumerate(paths[start:start+12]):
            with Image.open(path) as source:
                thumb = ImageOps.contain(source.convert('RGB'), (390, 510))
                x, y = (offset%4)*400, (offset//4)*540
                sheet.paste(thumb, (x, y+20))
                draw.text((x+5, y+3), path.name, fill='black')
        sheet.save(out/f'contact_{page:02d}.png')
    write_json(out/'manifest.json', dict(case_figures=len(paths), overview_figures=3, input_hashes={str(root/n):digest(root/n) for n in ('metrics.csv', 'trajectories.csv', 'forecast_metrics.csv')}))
    print(json.dumps(dict(figures=len(paths)+3, output=str(out))), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify', 'figures', 'overview'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    data = verify(root)
    if args.command in ('figures', 'overview'):
        figures(root, *data, overview_only=args.command=='overview')


if __name__ == '__main__':
    main()
