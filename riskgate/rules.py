"""Stop-rule grid: trailing stop x re-entry rule on a public daily close series, in both halves of the sample.

Rule: fully invested; a trailing stop of X% off the equity high exits at THAT close; the re-entry rule decides when
the position is re-opened (reentry.py: N<k>, SMA, BOTH<k>); a cost per side is paid on each exit and each re-entry.
CAGR, worst peak-to-trough fall, Calmar, the number of fires and the share of sessions flat are reported for the full
sample and for each half, so a rule that only worked in one half is seen.

Conventions follow the original run so the committed table reproduces to 4 decimals: the series of simple returns
starts at the second close; CAGR is measured from the first equity point to the last over the span in years; the SMA
is computed on the full series and then sliced per half; the equity high re-arms at the re-entry equity.

    python -m riskgate grid --download SPY --end 2026-10-16 --out grid.json      # yfinance at run time
    python -m riskgate grid --csv closes.csv                                     # Date,Close (any adjusted series)
"""
import json

import numpy as np
import pandas as pd

from .reentry import parse

STOPS = (0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25)
REENTRIES = ('N21', 'N63', 'SMA', 'BOTH21')
SPLIT = '2010-01-01'
COST = 0.001
SMA_WINDOW = 200


def load_csv(path, column='Close'):
    """A Date + Close CSV (a plain one, or a yfinance one with its two header rows)."""
    df = pd.read_csv(path)
    if 'Date' not in df.columns:
        df = pd.read_csv(path, header=[0, 1], index_col=0)
        df.columns = [c[0] for c in df.columns]
        df.index.name = 'Date'
        df = df.reset_index()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    s = pd.to_numeric(df[column], errors='coerce')
    s.index = df['Date']
    return s.dropna().sort_index()


def download(symbol='SPY', start='1993-01-01', end=None):
    import yfinance as yf
    d = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    c = d['Close']
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c.index = pd.to_datetime(c.index).tz_localize(None)
    return c.astype(float).dropna()


def stats(eq):
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    return float(cagr), float(dd)


def run_stop(returns, closes, sma, stop, label, cost=COST):
    """(equity Series, position array, fires) for one cell. `label` is a re-entry label ('N21', 'SMA', 'BOTH21')."""
    mode, n = parse(label)
    v, p, m = returns.values, closes.values, sma.values
    pos = np.ones(len(v))
    out = np.empty(len(v))
    eq, hwm, flat, flat_i, fires = 1.0, 1.0, False, -1, 0
    for i in range(len(v)):
        if flat:
            above = (not np.isnan(m[i])) and p[i] > m[i]
            if mode == 'N':
                re = i - flat_i >= n
            elif mode == 'SMA':
                re = above
            else:
                re = i - flat_i >= n and above
            if re:
                flat = False
                eq *= 1 - cost
                hwm = eq
        pos[i] = 0 if flat else 1
        eq *= 1 + v[i] * pos[i]
        out[i] = eq
        if not flat:
            hwm = max(hwm, eq)
            if eq / hwm - 1 <= -stop:
                flat, flat_i, fires = True, i, fires + 1
                eq *= 1 - cost
    return pd.Series(out, index=returns.index), pos, fires


def _table(r, px, sma, stops, reentries, cost):
    bh = (1 + r).cumprod()
    c0, d0 = stats(bh)
    rows = [{'stop': 'HOLD', 'reentry': '', 'cagr': c0, 'maxdd': d0, 'fires': 0, 'flat': 0.0}]
    for X in stops:
        for lab in reentries:
            eq, pos, f = run_stop(r, px, sma, X, lab, cost)
            c, d = stats(eq)
            rows.append({'stop': f'{int(round(X * 100))}%', 'reentry': lab, 'cagr': c, 'maxdd': d, 'fires': f, 'flat': float(1 - pos.mean())})
    t = pd.DataFrame(rows)
    t['calmar'] = t['cagr'] / t['maxdd'].abs()
    return t


def grid(closes, stops=STOPS, reentries=REENTRIES, split=SPLIT, cost=COST, sma_window=SMA_WINDOW):
    s = closes.astype(float).sort_index()
    r = s.pct_change().dropna()
    px = s.loc[r.index]
    sma = s.rolling(sma_window).mean().loc[r.index]
    split = pd.Timestamp(split)
    full = _table(r, px, sma, stops, reentries, cost)
    h1 = _table(r[r.index < split], px[px.index < split], sma[sma.index < split], stops, reentries, cost)
    h2 = _table(r[r.index >= split], px[px.index >= split], sma[sma.index >= split], stops, reentries, cost)
    m = full.merge(h1, on=['stop', 'reentry'], suffixes=('', '_h1')).merge(h2, on=['stop', 'reentry'], suffixes=('', '_h2'))
    cols = ['stop', 'reentry', 'cagr', 'maxdd', 'calmar', 'fires', 'flat', 'cagr_h1', 'maxdd_h1', 'cagr_h2', 'maxdd_h2']
    cells = json.loads(m[cols].to_json(orient='records'))
    return {'data': f'{len(s)} closes {s.index[0].date()}..{s.index[-1].date()}', 'cost_per_side': cost, 'split': str(split.date()),
            'sma_window': sma_window,
            'rule': 'trailing stop X% off the equity high, exit at that close; re-entry: N = after N sessions; SMA = first close above the '
                    f'{sma_window}-day SMA; BOTH21 = both',
            'hold': {'cagr': round(float(full.cagr.iloc[0]), 4), 'maxdd': round(float(full.maxdd.iloc[0]), 4),
                     'h1_cagr': round(float(h1.cagr.iloc[0]), 4), 'h1_maxdd': round(float(h1.maxdd.iloc[0]), 4),
                     'h2_cagr': round(float(h2.cagr.iloc[0]), 4), 'h2_maxdd': round(float(h2.maxdd.iloc[0]), 4)},
            'cells': cells}


def after_drop(closes, drop=-0.03, horizon=21):
    """After a single-session fall of `drop` or worse, where is the close `horizon` sessions later? Against every day."""
    c = closes.astype(float).sort_index().values
    r = np.diff(c) / c[:-1]
    idx = [i for i in range(1, len(c) - horizon) if r[i - 1] <= drop]
    f = np.array([c[i + horizon] / c[i] - 1 for i in idx])
    base = np.array([c[i + horizon] / c[i] - 1 for i in range(len(c) - horizon)])
    return {'drop': drop, 'horizon_sessions': horizon, 'n_events': len(idx), 'share_up': round(float((f > 0).mean()), 4) if len(f) else None,
            'mean_return': round(float(f.mean()), 4) if len(f) else None,
            'all_days_share_up': round(float((base > 0).mean()), 4), 'all_days_mean_return': round(float(base.mean()), 4)}


def compare(a, b, tol=1e-4, fields=('cagr', 'maxdd', 'cagr_h1', 'maxdd_h1', 'cagr_h2', 'maxdd_h2')):
    """Cells of two grids that differ by more than `tol` in any field (plus fires), keyed by (stop, reentry)."""
    ka = {(c['stop'], c['reentry']): c for c in a['cells']}
    kb = {(c['stop'], c['reentry']): c for c in b['cells']}
    out = []
    for k in sorted(set(ka) | set(kb)):
        if k not in ka or k not in kb:
            out.append({'cell': k, 'missing_in': 'a' if k not in ka else 'b'})
            continue
        bad = [f for f in fields if abs(ka[k][f] - kb[k][f]) > tol] + (['fires'] if ka[k]['fires'] != kb[k]['fires'] else [])
        if bad:
            out.append({'cell': k, 'fields': bad})
    return out


def format_table(g):
    lines = [f"{'stop':>5} {'re-entry':>8} {'CAGR':>7} {'worst':>7} {'Calmar':>6} {'fires':>5} {'flat':>5} | {'CAGR h1':>7} {'worst h1':>8} | {'CAGR h2':>7} {'worst h2':>8}"]
    for c in g['cells']:
        lines.append(f"{c['stop']:>5} {c['reentry']:>8} {100 * c['cagr']:6.1f}% {100 * c['maxdd']:6.1f}% {c['calmar']:6.2f} {c['fires']:5d} "
                     f"{100 * c['flat']:4.0f}% | {100 * c['cagr_h1']:6.1f}% {100 * c['maxdd_h1']:7.1f}% | {100 * c['cagr_h2']:6.1f}% {100 * c['maxdd_h2']:7.1f}%")
    return '\n'.join(lines)
