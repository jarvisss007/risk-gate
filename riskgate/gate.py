"""THE GATE a desk's writer calls before it appends a NEW entry to its book.

    gate = Gate('halts.json', 'refusals_<desk>.csv')
    allowed, refused = gate.admit('insider desk', entries, today=session, writer='insider_writer.py')
    for e in allowed: book.append(e)          # refused entries are already in the record

`binding(entry)` answers for one entry: the Halt that binds it (its `.reason` says why; `str()` is the full text),
or None. A writer that skips this call is found by `riskgate census` (census.py), not trusted.
"""
from .halts import HaltFile, binding as _binding
from .refusals import RefusalRecord


class Gate:
    def __init__(self, halts, refusals=None, calendar=None):
        self.halts = halts if isinstance(halts, HaltFile) else HaltFile(halts, calendar)
        self.calendar = self.halts.calendar
        self.refusals = (refusals if isinstance(refusals, RefusalRecord)
                         else RefusalRecord(refusals, self.calendar) if refusals else None)

    def standing(self, today=None):
        return self.halts.standing(today)

    def binding(self, entry, today=None):
        """The halt that binds `entry` for the session `today` rolls to, or None (allowed)."""
        return self.halts.binding(entry, today)

    def admit(self, desk, entries, *, today, writer=''):
        """(allowed, refused). Each entry is tested against every standing halt; refused entries carry entry['halt']
        and are written to the refusal record (when one is configured). An unreadable file refuses everything."""
        standing = self.standing(today)
        allowed, refused = [], []
        for e in entries:
            e = dict(e)
            e.setdefault('desk', desk)
            h = _binding(e, standing)
            if h is None:
                allowed.append(e)
            else:
                e['halt'] = h
                refused.append(e)
        if refused and self.refusals is not None:
            self.refusals.append(desk, refused, today=today, writer=writer)
        return allowed, refused
