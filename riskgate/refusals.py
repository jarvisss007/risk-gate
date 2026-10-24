"""The refusal record, and the rule that a refusal is a forecast.

A writer that is refused does not drop the entry: it appends it to a dated CSV with the halt that bound it. The
record is idempotent on (date, desk, ticker, structure, side), so a writer that runs twice records once. Nothing in
it is ever back-filled into a book when the halt lifts.

A refusal says "not now"; that is a forecast about the entry, and forecasts get graded. `score` grades each refusal
at a fixed horizon from its own date: did the refused entry go on to win or lose? A gate whose refusals mostly
"looked protective" is doing work; one whose refusals mostly cost return is a tax, and both are findings.
"""
import csv
import datetime as dt
import os
import tempfile

from .calendar import Calendar, as_date

COLS = ['date', 'desk', 'ticker', 'structure', 'side', 'notional', 'halt_key', 'halt_since', 'halt_until', 'reason',
        'writer', 'written_at']


def _key(r):
    return (str(r.get('date') or ''), str(r.get('desk') or ''), str(r.get('ticker') or '').upper(),
            str(r.get('structure') or ''), str(r.get('side') or '').lower())


class RefusalRecord:
    def __init__(self, path, calendar=None):
        self.path = str(path)
        self.calendar = calendar or Calendar()

    def read(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, newline='') as fh:
            return list(csv.DictReader(fh))

    def append(self, desk, refused, *, today, writer=''):
        """Append refused entries (each carrying entry['halt'], a Halt). Returns the number newly written."""
        day = self.calendar.roll_to_session(today).isoformat()
        old = self.read()
        seen = {_key(r) for r in old}
        now = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        add = []
        for e in refused:
            h = e['halt']
            r = {'date': str(e.get('date') or day), 'desk': desk, 'ticker': str(e.get('ticker') or '').upper(),
                 'structure': str(e.get('structure') or ''), 'side': str(e.get('side') or ''), 'notional': e.get('notional', ''),
                 'halt_key': h.key, 'halt_since': h.since, 'halt_until': h.until,
                 'reason': f'NEW entry refused while the halt file carries {h.key}; {h.reason or h.text}',
                 'writer': writer, 'written_at': now}
            if _key(r) in seen:
                continue
            seen.add(_key(r))
            add.append(r)
        if add:
            d = os.path.dirname(os.path.abspath(self.path)) or '.'
            os.makedirs(d, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=d, prefix='.refusals-', suffix='.csv')
            with os.fdopen(fd, 'w', newline='') as fh:
                w = csv.DictWriter(fh, COLS, extrasaction='ignore', restval='')
                w.writeheader()
                w.writerows(old + add)
            os.replace(tmp, self.path)
        return len(add)


def score(rows, closes, horizon, calendar=None):
    """Grade refusals as forecasts. closes: {ticker: {date: close}}. Entry at the close of the refusal date (rolled to a
    session), exit `horizon` sessions later. A refusal "looked protective" when the refused entry would have lost."""
    cal = calendar or Calendar()
    out = []
    for r in rows:
        t = r['ticker'].upper()
        series = closes.get(t) or {}
        d0 = cal.roll_to_session(r['date'])
        d1 = cal.add_sessions(d0, horizon)
        p0, p1 = series.get(d0.isoformat()), series.get(d1.isoformat())
        if p0 is None or p1 is None:
            out.append({**r, 'scored': False, 'why': f'no close for {t} on {d0} and {d1}'})
            continue
        fwd = p1 / p0 - 1
        side = -1 if r['side'].lower() == 'short' else 1
        pnl = side * fwd
        out.append({**r, 'scored': True, 'exit_date': d1.isoformat(), 'fwd_return': round(fwd, 6), 'entry_return': round(pnl, 6),
                    'refusal_looked': 'protective' if pnl < 0 else 'costly'})
    return out


def summary(scored):
    s = [r for r in scored if r.get('scored')]
    n = len(s)
    prot = sum(1 for r in s if r['refusal_looked'] == 'protective')
    return {'n_refusals': len(scored), 'n_scored': n, 'n_protective': prot,
            'share_protective': round(prot / n, 4) if n else None,
            'mean_entry_return_avoided': round(sum(r['entry_return'] for r in s) / n, 6) if n else None}
