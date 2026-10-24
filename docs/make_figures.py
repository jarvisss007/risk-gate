"""Render the figures from results/ (public SPY grid, synthetic demo). No account figure is read anywhere here.

  python docs/make_figures.py      # docs/stop_rule_grid.png, docs/stop_rule_grid_compact.png, docs/demo_timeline.png
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INK, MUTED, GRID = '#1d2433', '#6b7385', '#e6e8ee'
COLOR = {'N21': '#b45309', 'N63': '#d6a03f', 'SMA': '#2f6fd6', 'BOTH21': '#1d4ed8', 'HOLD': INK}
MARK = {'N21': 'v', 'N63': '^', 'SMA': 'o', 'BOTH21': 's'}


def grid_chart(path, compact=False):
    g = json.loads((ROOT / 'results' / 'stop_rule_grid.json').read_text())
    hold = g['hold']
    fig, ax = plt.subplots(figsize=(7.6, 5.0) if compact else (10, 5.9), dpi=200 if compact else 150)
    for lab in ('N21', 'N63', 'SMA', 'BOTH21'):
        cells = [c for c in g['cells'] if c['reentry'] == lab]
        xs = [-100 * c['maxdd'] for c in cells]
        ys = [100 * c['cagr'] for c in cells]
        ax.plot(xs, ys, '-', color=COLOR[lab], lw=1, alpha=0.5)
        ax.scatter(xs, ys, color=COLOR[lab], marker=MARK[lab], s=46 if compact else 40, zorder=3,
                   label={'N21': 'back in after 21 sessions', 'N63': 'back in after 63 sessions',
                          'SMA': 'back in on the first close above the 200-day average',
                          'BOTH21': 'both: 21 sessions AND above the average'}[lab])
        for c, x, y in zip(cells, xs, ys):
            if c['stop'] in ('5%', '10%', '25%') or (lab == 'SMA' and c['stop'] in ('8%', '12%')):
                ax.annotate(c['stop'], (x, y), textcoords='offset points', xytext=(5, 3), fontsize=7.5 if compact else 7.5, color=INK)
    ax.scatter([-100 * hold['maxdd']], [100 * hold['cagr']], color=INK, marker='*', s=160, zorder=4, label='buy and hold')
    ax.annotate('hold', (-100 * hold['maxdd'], 100 * hold['cagr']), textcoords='offset points', xytext=(6, -10), fontsize=8, color=INK)
    ax.axvspan(0, 30, color='#eef4fd', zorder=0)
    ax.text(20.6, 1.2, 'the 8-12% + 200-day plateau:\nworst fall under 35%,\nCAGR within 1.5 pts of hold',
            fontsize=7.5 if compact else 8, color='#1d4ed8', ha='left', va='bottom')
    ax.set_xlabel('worst peak-to-trough fall, % (smaller is left)', fontsize=9, color=MUTED)
    ax.set_ylabel('CAGR, %', fontsize=9, color=MUTED)
    ax.set_xlim(20, 66)
    ax.set_ylim(0, 12.5)
    ax.grid(color=GRID)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(labelsize=8, colors='#4a5163')
    ax.legend(fontsize=7.5 if compact else 8, loc='upper center', bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False)
    if not compact:
        ax.set_title('SPY 1993-2026: a trailing stop at 5-25%, four re-entry rules. The re-entry rule, not the threshold, decides',
                     fontsize=10, loc='left', color=INK)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def demo_chart(path):
    t = json.loads((ROOT / 'results' / 'demo_timeline.json').read_text())
    rows = t['timeline']
    x = list(range(len(rows)))
    eq = [r['equity'] for r in rows]
    line = [r['line'] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 3.6), dpi=150)
    ax.plot(x, eq, color=INK, lw=1.6, label='synthetic equity (index points)')
    ax.plot(x, line, color='#b45309', lw=1.2, ls='--', label='kill line: 90% of the closing high so far (never re-arms)')
    kill = [i for i, r in enumerate(rows) if any(h.startswith('kill ') for h in r['standing_after'])]
    if kill:
        ax.axvspan(kill[0] - 0.5, kill[-1] + 0.5, color='#fdecec', zorder=0, label='kill stands: every new entry refused')
    nb = 0
    for i, r in enumerate(rows):
        for a in r['actions']:
            if a.startswith('SET budget'):
                key = a.split(':', 1)[1].split(':')[0].strip() if 'sector' not in a else 'sector'
                ax.annotate(f'budget key set ({key})', (i, eq[i]), textcoords='offset points', xytext=(-60 - 70 * nb, 22 + 16 * nb),
                            fontsize=7.5, color='#2f6fd6', arrowprops=dict(arrowstyle='-', color='#2f6fd6', lw=0.8))
                nb += 1
            if a.startswith('brake NOT'):
                ax.annotate('brake would fire (not enforced)', (i, eq[i]), textcoords='offset points', xytext=(-70, -22), fontsize=7.5,
                            color=MUTED, arrowprops=dict(arrowstyle='-', color=MUTED, lw=0.8))
            if a.startswith('CLEARED kill'):
                ax.annotate('kill cleared: equity above the line,\nindex above its average, 21+ sessions', (i, eq[i]),
                            textcoords='offset points', xytext=(-150, -34), fontsize=7.5, color='#1d4ed8',
                            arrowprops=dict(arrowstyle='-', color='#1d4ed8', lw=0.8))
    ticks = [i for i, r in enumerate(rows) if r['session'][8:] == '01' or i == 0]
    ax.set_xticks(ticks)
    ax.set_xticklabels([rows[i]['session'] for i in ticks], fontsize=7.5)
    ax.grid(axis='y', color=GRID)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(labelsize=8, colors='#4a5163')
    ax.legend(fontsize=7.5, loc='lower left', frameon=False)
    ax.set_title('The synthetic estate: a kill-line trip, a budget key, a would-be brake, a mechanical clear (examples/demo.py)',
                 fontsize=10, loc='left', color=INK)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


if __name__ == '__main__':
    grid_chart(ROOT / 'docs' / 'stop_rule_grid.png')
    grid_chart(ROOT / 'docs' / 'stop_rule_grid_compact.png', compact=True)
    if (ROOT / 'results' / 'demo_timeline.json').exists():
        demo_chart(ROOT / 'docs' / 'demo_timeline.png')
    print('wrote docs/stop_rule_grid.png, docs/stop_rule_grid_compact.png, docs/demo_timeline.png')
