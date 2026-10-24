"""Command line.

  python -m riskgate init    --halts halts.json
  python -m riskgate status  --halts halts.json [--today YYYY-MM-DD]
  python -m riskgate check   --halts halts.json --desk D --side long|short --structure stock|debit|credit [--sector S] [--ticker T]
  python -m riskgate verify  --halts halts.json
  python -m riskgate ruling  --halts halts.json --id RULING-ID set|hold|release-hold KEY --session D --reason "..." [--until D]
  python -m riskgate close   --halts halts.json --estate DIR --session D [--enforce kill,budgets,brake,regime]
  python -m riskgate census  writer.py:function [...]
  python -m riskgate grid    --download SPY [--end D] | --csv closes.csv  [--out grid.json] [--compare other.json]
  python -m riskgate after-drop --download SPY | --csv closes.csv [--drop -0.03 --horizon 21]

Exit code 0 = allowed / consistent / all writers gated; 2 = refused / tampered / unreadable / a writer missing the gate.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from . import census as C
from . import halts as H
from . import layer, rules


def _hf(a):
    return H.HaltFile(a.halts)


def cmd_init(a):
    _hf(a).create(force=a.force)
    print(f'created {a.halts}: no keys, empty history')


def cmd_status(a):
    st = _hf(a).standing(a.today)
    if not st:
        print('no halt stands')
        return 0
    for h in st:
        print(('REFUSING: ' if h.key == H.UNREADABLE else 'standing: ') + h.text)
    return 2 if any(h.key == H.UNREADABLE for h in st) else 0


def cmd_check(a):
    entry = {'desk': a.desk, 'side': a.side, 'structure': a.structure, 'sector': a.sector, 'ticker': a.ticker, 'arm': a.arm}
    h = _hf(a).binding(entry, a.today)
    if h is None:
        print(f'ALLOWED: {a.desk} {a.side} {a.structure}{" " + a.ticker if a.ticker else ""}: no standing halt binds it')
        return 0
    print(f'REFUSED: {a.desk} {a.side} {a.structure}{" " + a.ticker if a.ticker else ""}: {h.text}')
    return 2


def cmd_verify(a):
    try:
        doc = _hf(a).read()
    except H.HaltsUnreadable as e:
        print(f'REFUSED: {e}')
        return 2
    print(f'consistent: {len(doc["halted"])} key(s) standing, {len(doc["history"])} history row(s), digest OK')
    for r in doc['history']:
        print(f'  {r["date"]}  {r["action"]:<12} {r["key"]:<28} by {r["by"]}')
    return 0


def cmd_ruling(a):
    hf = _hf(a)
    try:
        if a.action == 'set':
            hf.set(a.key, session=a.session, reason=a.reason, by=f'ruling:{a.id}', until=a.until)
        elif a.action == 'hold':
            hf.hold(a.key, ruling_id=a.id, session=a.session, reason=a.reason)
        elif a.action == 'release-hold':
            hf.release_hold(a.key, ruling_id=a.id, session=a.session, reason=a.reason)
        else:
            print(f'REFUSED: a ruling may set or hold a key; it never clears one ({a.action!r})')
            return 2
    except (KeyError, PermissionError, ValueError, H.HaltsUnreadable) as e:
        print(f'REFUSED: {e}')
        return 2
    print(f'recorded ruling {a.id}: {a.action} {a.key} on {a.session}')
    return 0


def _read_estate(estate, session):
    """The example estate layout: equity_curve.csv (date,equity), index.csv (date,close), risk.json
    ({session: {"desks": {desk: share_pct}, "sectors": {sector: share_pct} | null}})."""
    e = Path(estate)
    curve = {r['date']: float(r['equity']) for r in csv.DictReader(open(e / 'equity_curve.csv')) if r['date'] <= session}
    index = {r['date']: float(r['close']) for r in csv.DictReader(open(e / 'index.csv')) if r['date'] <= session}
    rp = e / 'risk.json'
    risk = (json.loads(rp.read_text()) if rp.exists() else {}).get(session) or {'desks': {}, 'sectors': None}
    return layer.SessionInputs(session=session, equity_curve=curve, index_closes=index, desk_risk=risk.get('desks') or {},
                               sector_risk=risk.get('sectors'))


def cmd_close(a):
    flags = set((a.enforce or 'kill,budgets').split(','))
    pol = layer.Policy(enforce_kill='kill' in flags, enforce_brake='brake' in flags, enforce_regime='regime' in flags,
                       enforce_budgets='budgets' in flags, hwm_since=a.hwm_since or '')
    rep = layer.close(_hf(a), _read_estate(a.estate, a.session), pol)
    k = rep.get('kill') or {}
    print(f"{rep['session']}: " + (f"equity {k.get('equity'):,.2f} vs line {k.get('line'):,.2f} (drawdown {k.get('drawdown_pct'):+.2f}%)"
                                   if k else 'halt file unreadable'))
    for x in rep['actions']:
        print('  ' + x)
    if rep.get('standing_after'):
        print('  standing: ' + '; '.join(rep['standing_after']))
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1) + '\n')
    return 0 if rep['halts_readable'] else 2


def cmd_census(a):
    rows = C.census([C.parse_spec(s) for s in a.writers])
    bad = 0
    for r in rows:
        bad += not r['present']
        print(f"{'gated  ' if r['present'] else 'MISSING'}  {r['writer']}:{r['function']}  {r['note']}")
    print(f'{len(rows) - bad} of {len(rows)} writers gated')
    return 2 if bad else 0


def _closes(a):
    if a.csv:
        return rules.load_csv(a.csv)
    return rules.download(a.download, end=a.end)


def cmd_grid(a):
    stops = tuple(float(x) / 100 for x in a.stops.split(',')) if a.stops else rules.STOPS
    g = rules.grid(_closes(a), stops=stops)
    print(rules.format_table(g))
    print(f"\nhold: CAGR {100 * g['hold']['cagr']:.1f}%, worst fall {100 * g['hold']['maxdd']:.1f}%  ({g['data']}, cost {g['cost_per_side']}/side)")
    if a.out:
        Path(a.out).write_text(json.dumps(g, indent=1) + '\n')
        print(f'wrote {a.out}')
    if a.compare:
        other = json.loads(Path(a.compare).read_text())
        diff = rules.compare(g, other, tol=a.tol)
        print(f'compared with {a.compare}: {len(g["cells"]) - len(diff)} of {len(g["cells"])} cells match to {a.tol}' +
              (f'; differ: {diff}' if diff else ''))
        return 2 if diff else 0
    return 0


def cmd_after_drop(a):
    r = rules.after_drop(_closes(a), a.drop, a.horizon)
    print(f"after a {100 * r['drop']:+.0f}% session ({r['n_events']} events): up {100 * r['share_up']:.1f}% of the time over the next "
          f"{r['horizon_sessions']} sessions, mean {100 * r['mean_return']:+.2f}%; every day: up {100 * r['all_days_share_up']:.1f}%, "
          f"mean {100 * r['all_days_mean_return']:+.2f}%")
    if a.out:
        Path(a.out).write_text(json.dumps(r, indent=1) + '\n')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='riskgate', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('init'); p.add_argument('--halts', required=True); p.add_argument('--force', action='store_true'); p.set_defaults(fn=cmd_init)
    p = sub.add_parser('status'); p.add_argument('--halts', required=True); p.add_argument('--today'); p.set_defaults(fn=cmd_status)
    p = sub.add_parser('check'); p.add_argument('--halts', required=True); p.add_argument('--desk', required=True)
    p.add_argument('--side', default='long'); p.add_argument('--structure', default='stock'); p.add_argument('--sector')
    p.add_argument('--ticker'); p.add_argument('--arm'); p.add_argument('--today'); p.set_defaults(fn=cmd_check)
    p = sub.add_parser('verify'); p.add_argument('--halts', required=True); p.set_defaults(fn=cmd_verify)
    p = sub.add_parser('ruling'); p.add_argument('--halts', required=True); p.add_argument('--id', required=True)
    p.add_argument('action'); p.add_argument('key'); p.add_argument('--session', required=True); p.add_argument('--reason', default='')
    p.add_argument('--until'); p.set_defaults(fn=cmd_ruling)
    p = sub.add_parser('close'); p.add_argument('--halts', required=True); p.add_argument('--estate', required=True)
    p.add_argument('--session', required=True); p.add_argument('--enforce'); p.add_argument('--hwm-since'); p.add_argument('--out')
    p.set_defaults(fn=cmd_close)
    p = sub.add_parser('census'); p.add_argument('writers', nargs='+'); p.set_defaults(fn=cmd_census)
    for name, fn in (('grid', cmd_grid), ('after-drop', cmd_after_drop)):
        p = sub.add_parser(name); p.add_argument('--csv'); p.add_argument('--download', default='SPY'); p.add_argument('--end')
        p.add_argument('--out')
        if name == 'grid':
            p.add_argument('--compare'); p.add_argument('--tol', type=float, default=1e-4)
            p.add_argument('--stops', help='comma-separated stop percentages, e.g. 3,5,10 (default: the committed grid\'s 5..25)')
        else:
            p.add_argument('--drop', type=float, default=-0.03); p.add_argument('--horizon', type=int, default=21)
        p.set_defaults(fn=fn)

    a = ap.parse_args(argv)
    rc = a.fn(a)
    sys.exit(rc or 0)
