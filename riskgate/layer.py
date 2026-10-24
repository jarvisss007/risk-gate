"""The layer: runs once per SETTLED session, computes what every rule wants, and moves keys only behind a flag.

Rules (every number CHOSEN, not fitted; changing one is a reviewed change, never a quiet edit):
    kill       equity at or under (1 - kill_drawdown_pct) x the closing high-water mark since `hwm_since` -> set `kill`.
               Cleared mechanically only when ALL hold: equity back above the line, the index close above its SMA,
               >= kill_reentry_sessions sessions since the key was set, and no ruling holds it. The HWM never re-arms.
    brake      day return <= brake_day_return_pct -> `brake` through `until` = session + brake_sessions. Nothing sold.
    regime     at a month-end session, index close below its SMA -> `regime`; a month-end close back above clears it.
    budget     a desk (or arm) over desk_ceiling_pct of equity at risk -> `budget:<desk>`; cleared when back inside.
               a sector over sector_cap_pct -> `budget:sector:<name>`; an UNCLASSIFIED sector reading moves no sector key.

What a rule WANTS is computed and reported whatever its flag says ("would set"); a key MOVES only behind its flag. The
flags' defaults are the state of the week this repo describes: kill and budgets on, brake and regime off (blocked by the
reviewer, see README). An unreadable or tampered halt file is never overwritten here: the run reports it and stops.
"""
from dataclasses import dataclass, asdict, field

from . import halts as H
from .calendar import Calendar, as_date
from .reentry import may_reenter


@dataclass
class Policy:
    kill_drawdown_pct: float = 10.0
    kill_reentry_sessions: int = 21
    sma_window: int = 200
    brake_day_return_pct: float = -3.0
    brake_sessions: int = 2
    desk_ceiling_pct: float = 8.0
    sector_cap_pct: float = 25.0
    hwm_since: str = ''                      # '' = the whole curve
    enforce_kill: bool = True
    enforce_brake: bool = False
    enforce_regime: bool = False
    enforce_budgets: bool = True


@dataclass
class SessionInputs:
    """What the layer reads at one settled close. Shares are percent of equity at risk, measured by the estate's own rule."""
    session: str
    equity_curve: dict                       # {date: equity} through the session (the settled curve; marks are not results)
    index_closes: dict                       # {date: close} of the reference index through the session
    desk_risk: dict = field(default_factory=dict)       # {desk or arm: share_pct}
    sector_risk: dict = None                 # {sector: share_pct}; None = UNCLASSIFIED (coverage too low to judge)


def kill_line(curve, session, policy):
    rows = {d: float(v) for d, v in curve.items() if (not policy.hwm_since or d >= policy.hwm_since) and d <= session}
    if not rows or session not in rows:
        raise ValueError(f'no settled equity for {session} on the curve (since {policy.hwm_since or "start"}); nothing moves')
    hwm_date = max(rows, key=lambda d: (rows[d], d))
    hwm = rows[hwm_date]
    line = hwm * (1 - policy.kill_drawdown_pct / 100.0)
    equity = rows[session]
    return {'hwm': round(hwm, 2), 'hwm_date': hwm_date, 'line': round(line, 2), 'equity': round(equity, 2),
            'drawdown_pct': round((equity / hwm - 1) * 100, 2), 'cushion_pct': round((equity - line) / equity * 100, 2),
            'tripped': equity <= line}


def index_sma(closes, session, window):
    """(close, sma, above | None). The SMA over `window` closes ENDING AT the session; None when there are not enough."""
    days = sorted(d for d in closes if d <= session)
    if not days or days[-1] != session:
        return closes.get(session), None, None
    if len(days) < window:
        return closes[session], None, None
    sma = sum(closes[d] for d in days[-window:]) / window
    return closes[session], round(sma, 4), closes[session] > sma


def day_return_pct(curve, session):
    days = sorted(d for d in curve if d <= session)
    if len(days) < 2 or days[-1] != session:
        return None
    prev, cur = float(curve[days[-2]]), float(curve[days[-1]])
    return round((cur / prev - 1) * 100, 4) if prev > 0 else None


def budget_keys_wanted(inp, policy):
    wanted = {}
    for desk, share in sorted(inp.desk_risk.items()):
        if share > policy.desk_ceiling_pct:
            wanted[H.BUDGET_PREFIX + desk] = f'{desk} at {share:.2f}% of equity at risk > {policy.desk_ceiling_pct:g}% ceiling'
    judgeable = inp.sector_risk is not None
    if judgeable:
        for sec, share in sorted(inp.sector_risk.items()):
            if share > policy.sector_cap_pct:
                wanted[H.SECTOR_PREFIX + sec] = f'sector {sec} at {share:.2f}% of equity at risk > {policy.sector_cap_pct:g}% cap'
    return wanted, judgeable


def close(halt_file, inp, policy=None, calendar=None):
    """Run the layer for one settled session. Returns a report; keys move inside halt_file only behind the flags."""
    policy = policy or Policy()
    cal = calendar or (halt_file.calendar if isinstance(halt_file, H.HaltFile) else Calendar())
    hf = halt_file if isinstance(halt_file, H.HaltFile) else H.HaltFile(halt_file, cal)
    session = as_date(inp.session).isoformat()
    report = {'session': session, 'policy': asdict(policy), 'actions': [], 'halts_readable': True}

    try:
        doc = hf.read()
    except H.HaltsUnreadable as e:
        report.update(halts_readable=False, actions=[f'halt file not touched: {e}'])
        return report
    held = doc['halted']

    k = kill_line(inp.equity_curve, session, policy)
    px, sma, above = index_sma(inp.index_closes, session, policy.sma_window)
    ret = day_return_pct(inp.equity_curve, session)
    month_end = cal.is_month_end(session)
    wanted, judgeable = budget_keys_wanted(inp, policy)

    # ---- kill line
    kill = dict(k, enforce=policy.enforce_kill, key_present=H.KILL in held, would_set=k['tripped'] and H.KILL not in held)
    if H.KILL in held:
        v = held[H.KILL]
        n_since = len(cal.sessions_between(v.get('since'), session))
        hold = bool(v.get('hold'))
        reentry = may_reenter('BOTH', policy.kill_reentry_sessions, sessions_since=n_since, close=px, sma=sma)
        kill.update(sessions_since_set=n_since, index_close=px, sma=sma, index_above_sma=above, held_by=v.get('hold', ''),
                    would_clear=(not k['tripped']) and reentry and not hold,
                    reentry_rule=f'equity above the line AND index > SMA{policy.sma_window} AND >= {policy.kill_reentry_sessions} '
                                 f'sessions since set AND no hold; the HWM never re-arms')
    if policy.enforce_kill:
        if kill['would_set']:
            hf.set(H.KILL, session=session, by='rule:kill-line',
                   reason=f'equity {k["equity"]:,.2f} at or under the line {k["line"]:,.2f} ({100 - policy.kill_drawdown_pct:g}% of the '
                          f'closing high-water mark {k["hwm"]:,.2f} on {k["hwm_date"]}); every desk\'s NEW entries are refused; nothing is sold')
            report['actions'].append(f'SET kill: drawdown {k["drawdown_pct"]:+.2f}% from the HWM')
        elif kill.get('would_clear'):
            hf.clear(H.KILL, session=session, by='rule:kill-line',
                     lifted=f'{session}: equity {k["equity"]:,.2f} above the line {k["line"]:,.2f}; index {px} > SMA{policy.sma_window} {sma}; '
                            f'{kill["sessions_since_set"]} sessions since set (>= {policy.kill_reentry_sessions})')
            report['actions'].append('CLEARED kill: re-entry rule met')
        elif H.KILL in held:
            report['actions'].append('kill stands: ' + ('held by a ruling' if kill['held_by'] else
                                     f'equity {"above" if not k["tripped"] else "at or under"} the line; index '
                                     f'{"above" if above else "not above" if above is False else "? (no SMA)"} the SMA; '
                                     f'{kill["sessions_since_set"]} of {policy.kill_reentry_sessions} sessions'))
    elif kill['would_set'] or kill.get('would_clear'):
        report['actions'].append(f'kill NOT ENFORCED: would {"set" if kill["would_set"] else "clear"}')
    report['kill'] = kill

    # ---- brake
    until = cal.add_sessions(session, policy.brake_sessions).isoformat()
    trip = ret is not None and ret <= policy.brake_day_return_pct
    cur = held.get(H.BRAKE)
    expired = cur is not None and hf.brake_expired(cur, session)
    brake = {'enforce': policy.enforce_brake, 'day_return_pct': ret, 'tripped': trip, 'would_set': trip and (cur is None or expired),
             'would_run_until': until if trip else None, 'key_present': cur is not None, 'expired': expired}
    if policy.enforce_brake:
        if expired and not trip:
            hf.clear(H.BRAKE, session=session, by='rule:brake', lifted=f'{session}: brake ran through {cur.get("until")} and expired')
            report['actions'].append('CLEARED brake: expired')
        if trip and (cur is None or expired):
            if expired:
                hf.clear(H.BRAKE, session=session, by='rule:brake', lifted=f'{session}: superseded by a new trip')
            hf.set(H.BRAKE, session=session, until=until, by='rule:brake',
                   reason=f'the {session} session closed {ret:+.2f}% (<= {policy.brake_day_return_pct:g}%); NEW entries of every desk '
                          f'refused through {until}; nothing is sold')
            report['actions'].append(f'SET brake until {until}: day return {ret:+.2f}%')
    elif brake['would_set']:
        report['actions'].append(f'brake NOT ENFORCED: would set until {until} (day return {ret:+.2f}%)')
    report['brake'] = brake

    # ---- regime
    regime = {'enforce': policy.enforce_regime, 'month_end': month_end, 'index_close': px, 'sma': sma, 'index_above_sma': above,
              'key_present': H.REGIME in held,
              'would_set': bool(month_end and above is False and H.REGIME not in held),
              'would_clear': bool(month_end and above is True and H.REGIME in held and not held.get(H.REGIME, {}).get('hold'))}
    if policy.enforce_regime:
        if regime['would_set']:
            hf.set(H.REGIME, session=session, by='rule:regime',
                   reason=f'month-end index close {px} below its SMA{policy.sma_window} {sma}; NEW LONG entries refused until a month-end '
                          f'close back above; shorts and debit structures pass; nothing is sold')
            report['actions'].append('SET regime: month-end close below the SMA')
        elif regime['would_clear']:
            hf.clear(H.REGIME, session=session, by='rule:regime', lifted=f'{session}: month-end index close {px} > SMA{policy.sma_window} {sma}')
            report['actions'].append('CLEARED regime: month-end close above the SMA')
    elif regime['would_set'] or regime['would_clear']:
        report['actions'].append(f'regime NOT ENFORCED: would {"set" if regime["would_set"] else "clear"}')
    report['regime'] = regime

    # ---- budgets
    present = sorted(x for x in held if x.startswith(H.BUDGET_PREFIX))
    to_set = sorted(x for x in wanted if x not in held)
    to_clear = [x for x in present if x not in wanted and not held[x].get('hold')
                and not (x.startswith(H.SECTOR_PREFIX) and not judgeable)]
    budgets = {'enforce': policy.enforce_budgets, 'wanted': sorted(wanted), 'present_before': present, 'would_set': to_set,
               'would_clear': to_clear, 'sector_judgeable': judgeable}
    if policy.enforce_budgets:
        for key in to_set:
            hf.set(key, session=session, by='rule:budget', reason=f'{wanted[key]} at the {session} close; NEW entries of that '
                   f'{"sector" if key.startswith(H.SECTOR_PREFIX) else "desk"} refused until back inside; nothing is sold')
            report['actions'].append(f'SET {key}: {wanted[key]}')
        for key in to_clear:
            hf.clear(key, session=session, by='rule:budget', lifted=f'{session}: back inside its limit at the close')
            report['actions'].append(f'CLEARED {key}: back inside')
    elif to_set or to_clear:
        report['actions'].append(f'budgets NOT ENFORCED: would set {to_set}, clear {to_clear}')
    report['budgets'] = budgets

    report['standing_after'] = [h.text for h in hf.standing(session)]
    if not report['actions']:
        report['actions'].append('no key moved')
    return report
