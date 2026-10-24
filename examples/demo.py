"""The layer on the synthetic estate, end to end: every settled close moves keys by the mechanical rules, then every
desk's writer tries to enter and is admitted or refused through the one gate. Refusals are then scored as forecasts.

  python examples/demo.py              # ~2 seconds; writes examples/estate/generated/ and results/demo_timeline.json
"""
import csv
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'examples'))
sys.path.insert(0, str(ROOT / 'examples' / 'writers'))

import make_estate  # noqa: E402
from riskgate import layer  # noqa: E402
from riskgate.halts import HaltFile  # noqa: E402
from riskgate.refusals import RefusalRecord, score, summary  # noqa: E402
from riskgate.cli import _read_estate  # noqa: E402

EST = ROOT / 'examples' / 'estate'
GEN = Path(os.environ.get('RISKGATE_ESTATE_GENERATED', EST / 'generated'))     # the writers read the same variable
HORIZON = 10


def load_writers():
    import fundamentals_writer, insider_writer, options_writer, pattern_writer  # noqa: E401
    return [(insider_writer, 'AAA'), (fundamentals_writer, 'BBB'), (pattern_writer, 'EEE'), (options_writer, 'CCC')]


def main(quiet=False):
    if not (EST / 'equity_curve.csv').exists():
        make_estate.make()
    if GEN.exists():
        shutil.rmtree(GEN)
    GEN.mkdir(parents=True)
    hf = HaltFile(GEN / 'halts.json')
    hf.create()
    policy = layer.Policy(hwm_since=make_estate.FIRST)        # kill + budgets enforced; brake + regime report only
    days = make_estate.sessions(make_estate.FIRST, make_estate.LAST)
    writers = load_writers()
    timeline, n_refused, n_allowed = [], 0, 0
    say = (lambda *a: None) if quiet else print

    say(f'{"session":<11} {"equity":>8} {"line":>8} {"dd%":>6}  keys moved / entries refused')
    prev = None
    for d in days:
        rep = layer.close(hf, _read_estate(EST, d), policy)
        k = rep['kill']
        refused_here = []
        for mod, ticker in writers:
            allowed, refused = mod.book(mod.candidates(d, ticker), d)
            n_allowed += len(allowed); n_refused += len(refused)
            refused_here += [f"{e.get('arm') or e['desk']} {e['side']} {e['structure']} {e['ticker']} <- {e['halt'].key}" for e in refused]
        moves = [a for a in rep['actions'] if a.startswith(('SET', 'CLEARED', 'brake NOT', 'regime NOT', 'budgets NOT'))]
        if moves or (refused_here and refused_here != prev):
            line = f"{d:<11} {k['equity']:8.2f} {k['line']:8.2f} {k['drawdown_pct']:+6.2f}  " + ' | '.join(moves)
            if refused_here and refused_here != prev:
                line += f"\n{'':<37}refused: " + '; '.join(refused_here)
            elif refused_here:
                line += f"\n{'':<37}refused: the same {len(refused_here)} as the session before"
            say(line)
        prev = refused_here
        timeline.append({'session': d, 'equity': k['equity'], 'line': k['line'], 'drawdown_pct': k['drawdown_pct'],
                         'actions': rep['actions'], 'refused': refused_here, 'standing_after': rep['standing_after']})

    # refusals are forecasts: grade each at HORIZON sessions against the synthetic prices
    prices = {}
    for r in csv.DictReader(open(EST / 'prices.csv')):
        for t in make_estate.TICKERS:
            prices.setdefault(t, {})[r['date']] = float(r[t])
    rows = []
    for p in sorted((GEN / 'refusals').glob('*.csv')):
        rows += RefusalRecord(p).read()
    scored = score(rows, prices, HORIZON)
    s = summary(scored)
    hist = hf.read()['history']
    out = {'synthetic': True, 'sessions': len(days), 'entries_allowed': n_allowed, 'entries_refused': n_refused,
           'keys_set': sum(r['action'] == 'set' for r in hist), 'keys_cleared': sum(r['action'] == 'clear' for r in hist),
           'history': hist, 'refusal_scoring': dict(s, horizon_sessions=HORIZON), 'timeline': timeline}
    (ROOT / 'results' / 'demo_timeline.json').write_text(json.dumps(out, indent=1) + '\n')
    say(f"\n{len(days)} sessions: {n_allowed} entries admitted, {n_refused} refused and recorded; "
        f"{out['keys_set']} keys set, {out['keys_cleared']} cleared, every move by a rule (history rows: "
        f"{sorted(set(r['by'] for r in hist))}).")
    say(f"refusals as forecasts at {HORIZON} sessions: {s['n_scored']} of {s['n_refusals']} scored, "
        f"{s['n_protective']} looked protective ({(100 * s['share_protective']) if s['share_protective'] is not None else float('nan'):.0f}%), "
        f"mean return the refused entries would have made {100 * (s['mean_entry_return_avoided'] or 0):+.2f}%\n"
        f"  (synthetic prices know nothing about the halt, so this number means nothing here; the point is that it is computed and printed).")
    say(f"wrote results/demo_timeline.json and {GEN}/")
    return out


if __name__ == '__main__':
    main()
