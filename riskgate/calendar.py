"""The session calendar seam.

Every date the layer reasons about is a SESSION date, never a calendar date: a brake that runs "two sessions" must
know that a Friday trip ends on Tuesday, and a re-entry rule that counts "21 sessions" must not count holidays.
`Calendar` is a weekday calendar with an explicit holiday set; plug an exchange calendar in by passing its holidays,
or subclass and override `is_session`. The holidays below are the NYSE's published full-day closures; check them
against the exchange before relying on them past the listed years.
"""
import datetime as dt

NYSE_HOLIDAYS = {
    '2025-01-01', '2025-01-09', '2025-01-20', '2025-02-17', '2025-04-18', '2025-05-26', '2025-06-19', '2025-07-04',
    '2025-09-01', '2025-11-27', '2025-12-25',
    '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07',
    '2026-11-26', '2026-12-25',
    '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18', '2027-07-05', '2027-09-06',
    '2027-11-25', '2027-12-24',
}


def as_date(x):
    """date | datetime | 'YYYY-MM-DD[...]' -> date."""
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x)[:10])


class Calendar:
    def __init__(self, holidays=NYSE_HOLIDAYS):
        self.holidays = {as_date(h) for h in holidays}

    def is_session(self, d):
        d = as_date(d)
        return d.weekday() < 5 and d not in self.holidays

    def next_session(self, d, inclusive=False):
        d = as_date(d)
        if not inclusive:
            d += dt.timedelta(days=1)
        while not self.is_session(d):
            d += dt.timedelta(days=1)
        return d

    def last_session(self, d, inclusive=True):
        d = as_date(d)
        if not inclusive:
            d -= dt.timedelta(days=1)
        while not self.is_session(d):
            d -= dt.timedelta(days=1)
        return d

    def roll_to_session(self, d):
        """A decision dated on a non-session belongs to the NEXT session (it queues; it does not pretend)."""
        return self.next_session(d, inclusive=True)

    def add_sessions(self, d, n):
        d = as_date(d)
        for _ in range(n):
            d = self.next_session(d)
        return d

    def sessions_between(self, a, b):
        """Sessions strictly after a, up to and including b."""
        a, b = as_date(a), as_date(b)
        out, d = [], a + dt.timedelta(days=1)
        while d <= b:
            if self.is_session(d):
                out.append(d)
            d += dt.timedelta(days=1)
        return out

    def is_month_end(self, d):
        d = as_date(d)
        return self.next_session(d).month != d.month
