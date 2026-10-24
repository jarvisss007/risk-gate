"""The halt file: one JSON file of typed keys that every desk's writer reads before a NEW entry.

    {"halted": {<key>: {"since": "YYYY-MM-DD", "until": "YYYY-MM-DD"?, "reason": "...", "hold": "<ruling id>"?}},
     "history": [{"date": ..., "key": ..., "action": "set" | "clear" | "hold", "by": "rule:<name>" | "ruling:<id>", ...}],
     "digest": "<sha256 of halted + history>"}

Keys and what they bind:
    kill                    every new entry of every desk
    brake                   every new entry, through `until` (an expired brake reads as not set)
    regime                  new LONG entries; a short, or a defined-risk DEBIT structure, passes
    budget:<desk>           that desk's (or arm's) new entries
    budget:sector:<name>    a new entry in any name of that sector, every desk; a name with no sector is not bound

Three rules the file enforces on itself:
    * an UNREADABLE file (missing, malformed, wrong shape) REFUSES: the reader never assumes "no halt";
    * every change is a history row written by this module, and the digest covers both; a file edited by hand fails
      the digest and reads as TAMPERED, which refuses like unreadable and names what a human change needs: a ruling id;
    * a ruling may SET a key or HOLD one past its mechanical clear; it can never CLEAR one. Keys leave only by the
      pre-stated mechanical rules in layer.py.
"""
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field

from .calendar import Calendar, as_date

KILL, BRAKE, REGIME = 'kill', 'brake', 'regime'
BUDGET_PREFIX, SECTOR_PREFIX = 'budget:', 'budget:sector:'
UNREADABLE = 'UNREADABLE'
FIXED_KEYS = (KILL, BRAKE, REGIME)
REGIME_PASSES_SIDES = ('short',)
REGIME_PASSES_STRUCTURES = ('debit',)


class HaltsUnreadable(Exception):
    """The file cannot be read as a halt file. Every reader REFUSES on it."""


class HaltsTampered(HaltsUnreadable):
    """The file was changed outside this module. Refuses like unreadable; the message says what a human change needs."""


def is_valid_key(k):
    return k in FIXED_KEYS or (k.startswith(BUDGET_PREFIX) and len(k) > len(BUDGET_PREFIX))


def is_valid_by(by):
    return isinstance(by, str) and (by.startswith('rule:') or by.startswith('ruling:')) and len(by.split(':', 1)[1]) > 0


@dataclass
class Halt:
    key: str
    since: str = ''
    until: str = ''
    reason: str = ''
    hold: str = ''
    value: dict = field(default_factory=dict)

    @property
    def text(self):
        if self.key == UNREADABLE:
            return f'{UNREADABLE}: {self.reason}'
        s = f'{self.key} since {self.since or "?"}'
        if self.until:
            s += f' until {self.until}'
        if self.hold:
            s += f' (held by {self.hold})'
        return s + (f': {self.reason}' if self.reason else '')

    def __str__(self):
        return self.text


def digest(halted, history):
    body = json.dumps({'halted': halted, 'history': history}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(body.encode()).hexdigest()


def implied_state(history):
    """{key: last row} for every key whose last history action leaves it standing (anything but a clear)."""
    last = {}
    for r in history:
        last[r.get('key')] = r
    return {k: r for k, r in last.items() if r.get('action') != 'clear'}


def binding(entry, standing):
    """The first standing halt that binds ONE entry, or None.

    entry: {desk, side ('long'|'short'), structure ('stock'|'debit'|'credit'|...), sector?, arm?, ticker?}.
    Kill, brake and an unreadable file bind everything. The regime key binds unless the side is short or the
    structure is a debit. budget:<x> binds the desk or arm named x. budget:sector:<s> binds an entry whose sector is s.
    """
    side = str(entry.get('side') or '').strip().lower()
    structure = str(entry.get('structure') or '').strip().lower()
    desk = str(entry.get('desk') or '')
    arm = str(entry.get('arm') or '')
    sector = str(entry.get('sector') or '')
    for h in standing:
        k = h.key
        if k in (UNREADABLE, KILL, BRAKE):
            return h
        if k == REGIME:
            if side in REGIME_PASSES_SIDES or structure in REGIME_PASSES_STRUCTURES:
                continue
            return h
        if k.startswith(SECTOR_PREFIX):
            if sector and k == SECTOR_PREFIX + sector:
                return h
            continue
        if k.startswith(BUDGET_PREFIX):
            if k == BUDGET_PREFIX + desk or (arm and k == BUDGET_PREFIX + arm):
                return h
    return None


class HaltFile:
    def __init__(self, path, calendar=None):
        self.path = str(path)
        self.calendar = calendar or Calendar()

    # ------------------------------------------------------------------ reading
    def read(self):
        """The whole document, verified. Raises HaltsUnreadable / HaltsTampered; a caller REFUSES on either."""
        try:
            with open(self.path) as fh:
                doc = json.load(fh)
        except Exception as e:
            raise HaltsUnreadable(f'{os.path.basename(self.path)} could not be read ({type(e).__name__}: {e}); '
                                  f'REFUSING every new entry rather than assume no halt')
        if not isinstance(doc, dict) or not isinstance(doc.get('halted'), dict) or not isinstance(doc.get('history'), list):
            raise HaltsUnreadable(f'{os.path.basename(self.path)}: not a halt file (needs `halted` mapping, `history` list)')
        halted, history = doc['halted'], doc['history']
        if doc.get('digest') != digest(halted, history):
            raise HaltsTampered(self._tamper_message(halted, history))
        if set(halted) != set(implied_state(history)):           # a hand edit that recomputed the digest still has no provenance
            raise HaltsTampered(self._tamper_message(halted, history))
        for k in halted:
            if not is_valid_key(k):
                raise HaltsTampered(f'{k!r} is not a typed key (kill, brake, regime, budget:<desk>, budget:sector:<name>)')
        return doc

    def _tamper_message(self, halted, history):
        implied = implied_state(history)
        last_set = {r['key']: r for r in history if r.get('action') == 'set'}
        gaps = []
        for k in halted:
            if k not in implied:
                gaps.append(f'`{k}` is present with no history row that set it')
        for k, r in implied.items():
            if k not in halted:
                s = last_set.get(k, r)
                held = f' (held by {r["by"]})' if r.get('action') == 'hold' else ''
                gaps.append(f'`{k}` was set {s.get("date", "?")} by {s.get("by", "?")}{held} and is gone with no clear row: '
                            f'a review may hold a halt longer, never lift it earlier')
        what = '; '.join(gaps) if gaps else 'a value was changed in place'
        return (f'{os.path.basename(self.path)} was edited outside the layer (digest mismatch): {what}. A human change '
                f'is a history row with a ruling id: `riskgate ruling --id <RULING-ID> set|hold <key>`. Refusing every '
                f'new entry until the file is consistent.')

    def exists(self):
        return os.path.exists(self.path)

    def create(self, force=False):
        if self.exists() and not force:
            raise FileExistsError(self.path)
        self._write({'halted': {}, 'history': []})

    def _write(self, doc):
        doc['digest'] = digest(doc['halted'], doc['history'])
        d = os.path.dirname(os.path.abspath(self.path)) or '.'
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix='.halts-', suffix='.json')
        with os.fdopen(fd, 'w') as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
            fh.write('\n')
        os.replace(tmp, self.path)

    def _today(self, today):
        return self.calendar.roll_to_session(today) if today is not None else None

    def brake_expired(self, value, today):
        """True when the brake's `until` is before the session `today` rolls to. No `until` (a ruling's brake) never expires."""
        u = str((value or {}).get('until') or '') if isinstance(value, dict) else ''
        t = self._today(today)
        return bool(u) and t is not None and t.isoformat() > u

    def standing(self, today=None):
        """Every halt that stands for the session `today` rolls to, in precedence order: kill, brake, regime, budget keys.
        [] when none. [Halt(UNREADABLE)] when the file cannot be read or was tampered with: the caller REFUSES."""
        try:
            doc = self.read()
        except HaltsUnreadable as e:
            return [Halt(UNREADABLE, reason=str(e))]
        h = doc['halted']
        out = []

        def mk(k):
            v = h[k] if isinstance(h[k], dict) else {'since': str(h[k])}
            return Halt(k, since=str(v.get('since') or ''), until=str(v.get('until') or ''), reason=str(v.get('reason') or ''),
                        hold=str(v.get('hold') or ''), value=v)
        if KILL in h:
            out.append(mk(KILL))
        if BRAKE in h and not self.brake_expired(h[BRAKE], today):
            out.append(mk(BRAKE))
        if REGIME in h:
            out.append(mk(REGIME))
        for k in sorted(h):
            if k.startswith(BUDGET_PREFIX):
                out.append(mk(k))
        return out

    def binding(self, entry, today=None):
        """The halt that binds this entry today, or None. See module-level `binding`."""
        return binding(entry, self.standing(today))

    # ------------------------------------------------------------------ writing (the layer and a ruling; never a desk)
    def _mutate(self, fn):
        doc = self.read()                      # a tampered or unreadable file is never overwritten
        fn(doc['halted'], doc['history'])
        self._write(doc)
        return doc

    def set(self, key, *, session, reason, by, until=None, extra=None):
        """Set a key. `by` is 'rule:<name>' (the layer) or 'ruling:<id>' (a human). A key already standing is never rewritten."""
        if not is_valid_key(key):
            raise ValueError(f'{key!r} is not a typed key')
        if not is_valid_by(by):
            raise ValueError(f'`by` must be rule:<name> or ruling:<id>, got {by!r}')
        session = as_date(session).isoformat()

        def fn(halted, history):
            if key in halted:
                raise KeyError(f'{key} already stands since {halted[key].get("since")}; never rewritten')
            v = {'since': session, 'reason': reason}
            if until:
                v['until'] = as_date(until).isoformat()
            if by.startswith('ruling:'):
                v['hold'] = by.split(':', 1)[1]          # a ruling's key is held: no mechanical rule clears it
            if extra:
                v.update(extra)
            halted[key] = v
            history.append({'date': session, 'key': key, 'action': 'set', 'by': by, 'reason': reason, **({'until': v['until']} if until else {})})
        return self._mutate(fn)

    def clear(self, key, *, session, lifted, by):
        """Clear a key by a MECHANICAL rule only. A held key is not cleared. A ruling cannot clear (it may only hold)."""
        if not by.startswith('rule:'):
            raise PermissionError('a ruling never lifts a halt early; only a pre-stated mechanical rule clears a key')
        session = as_date(session).isoformat()

        def fn(halted, history):
            if key not in halted:
                raise KeyError(f'{key} is not standing')
            if halted[key].get('hold'):
                raise PermissionError(f'{key} is held by ruling {halted[key]["hold"]}; the mechanical clear does not apply')
            v = halted.pop(key)
            history.append({'date': session, 'key': key, 'action': 'clear', 'by': by, 'lifted': lifted, 'was': v})
        return self._mutate(fn)

    def hold(self, key, *, ruling_id, session, reason):
        """A recorded review holds a standing key past its mechanical clear. It cannot do the opposite."""
        session = as_date(session).isoformat()

        def fn(halted, history):
            if key not in halted:
                raise KeyError(f'{key} is not standing; a ruling can set a key (`set`) but there is nothing to hold')
            halted[key]['hold'] = ruling_id
            history.append({'date': session, 'key': key, 'action': 'hold', 'by': f'ruling:{ruling_id}', 'reason': reason})
        return self._mutate(fn)

    def release_hold(self, key, *, ruling_id, session, reason):
        """A later ruling may withdraw a hold; the key then leaves only when its mechanical clear rule next fires."""
        session = as_date(session).isoformat()

        def fn(halted, history):
            if key not in halted or not halted[key].get('hold'):
                raise KeyError(f'{key} is not held')
            halted[key].pop('hold')
            history.append({'date': session, 'key': key, 'action': 'release-hold', 'by': f'ruling:{ruling_id}', 'reason': reason})
        return self._mutate(fn)
