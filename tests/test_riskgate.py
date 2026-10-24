import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from riskgate import census, exposure, layer, reentry, rules  # noqa: E402
from riskgate import halts as H  # noqa: E402
from riskgate.calendar import Calendar  # noqa: E402
from riskgate.gate import Gate  # noqa: E402
from riskgate.refusals import RefusalRecord, score, summary  # noqa: E402

CAL = Calendar()
LONG = {'desk': 'insider desk', 'side': 'long', 'structure': 'stock', 'ticker': 'AAA', 'sector': 'semiconductors'}
SHORT = {'desk': 'pattern desk', 'side': 'short', 'structure': 'stock', 'ticker': 'BBB'}
DEBIT = {'desk': 'options desk', 'arm': 'options arm A', 'side': 'long', 'structure': 'debit', 'ticker': 'CCC'}
CREDIT = {'desk': 'options desk', 'arm': 'options arm B', 'side': 'long', 'structure': 'credit', 'ticker': 'DDD'}


def fresh(tmp_path, name='halts.json'):
    hf = H.HaltFile(tmp_path / name)
    hf.create()
    return hf


def curve(start, values):
    """{session: equity} from a start date and a list of settled equities, one per session."""
    out, d = {}, CAL.roll_to_session(start)
    for v in values:
        out[d.isoformat()] = v
        d = CAL.next_session(d)
    return out


def index_series(end, n, level=100.0, sma_gap=+1.0):
    """n sessions of index closes ENDING AT `end`: a flat series at `level` whose last close is nudged by `sma_gap`,
    so close > SMA iff sma_gap > 0. The layer reads the SMA only when the series reaches the session."""
    d = CAL.roll_to_session(end)
    days = [d]
    for _ in range(n - 1):
        d = CAL.last_session(d, inclusive=False)
        days.append(d)
    c = {x.isoformat(): level for x in days}
    c[max(c)] = level + sma_gap
    return c


# ---------------------------------------------------------------- the halt file: reading, binding, refusing
def test_unreadable_file_refuses_and_never_assumes_no_halt(tmp_path):
    missing = H.HaltFile(tmp_path / 'nope.json')
    st = missing.standing('2026-10-26')
    assert [h.key for h in st] == [H.UNREADABLE]
    assert missing.binding(SHORT, '2026-10-26').key == H.UNREADABLE          # even a short, even a debit
    assert missing.binding(DEBIT, '2026-10-26').key == H.UNREADABLE
    (tmp_path / 'bad.json').write_text('{not json')
    assert H.HaltFile(tmp_path / 'bad.json').binding(LONG).key == H.UNREADABLE
    (tmp_path / 'shape.json').write_text(json.dumps({'halted': []}))
    assert H.HaltFile(tmp_path / 'shape.json').binding(LONG).key == H.UNREADABLE
    with pytest.raises(H.HaltsUnreadable):
        missing.set(H.KILL, session='2026-10-26', reason='x', by='rule:kill-line')   # never writes over an unreadable file


def test_kill_and_brake_bind_everything_regime_exempts_shorts_and_debits(tmp_path):
    hf = fresh(tmp_path)
    hf.set(H.REGIME, session='2026-10-30', reason='month-end close below the SMA', by='rule:regime')
    assert hf.binding(LONG, '2026-11-02').key == H.REGIME
    assert hf.binding(CREDIT, '2026-11-02').key == H.REGIME                 # a credit structure is not defined-risk here
    assert hf.binding(SHORT, '2026-11-02') is None
    assert hf.binding(DEBIT, '2026-11-02') is None
    hf.set(H.KILL, session='2026-11-02', reason='at the line', by='rule:kill-line')
    for e in (LONG, SHORT, DEBIT, CREDIT):
        assert hf.binding(e, '2026-11-03').key == H.KILL                    # kill outranks the exemptions
    hf2 = fresh(tmp_path, 'b.json')
    hf2.set(H.BRAKE, session='2026-11-02', until='2026-11-04', reason='-3% day', by='rule:brake')
    for e in (LONG, SHORT, DEBIT, CREDIT):
        assert hf2.binding(e, '2026-11-03').key == H.BRAKE


def test_budget_keys_bind_one_desk_arm_or_sector_only(tmp_path):
    hf = fresh(tmp_path)
    hf.set('budget:options arm A', session='2026-10-23', reason='over 8%', by='rule:budget')
    hf.set('budget:sector:semiconductors', session='2026-10-23', reason='over 25%', by='rule:budget')
    assert hf.binding(DEBIT, '2026-10-26').key == 'budget:options arm A'  # by arm
    assert hf.binding(CREDIT, '2026-10-26') is None                          # the other arm passes
    assert hf.binding(LONG, '2026-10-26').key == 'budget:sector:semiconductors'
    assert hf.binding(dict(LONG, sector='software'), '2026-10-26') is None
    assert hf.binding(dict(LONG, sector=None), '2026-10-26') is None         # no sector on file: not bound by a sector key
    assert hf.binding(SHORT, '2026-10-26') is None


def test_brake_expires_by_the_session_calendar_not_the_wall_clock(tmp_path):
    hf = fresh(tmp_path)
    # Thu 2026-11-25 trips; two sessions later is Mon 11-30 (Thu 11-26 is Thanksgiving, Fri 11-27 a session)
    until = CAL.add_sessions('2026-11-25', 2)
    assert until.isoformat() == '2026-11-30'
    hf.set(H.BRAKE, session='2026-11-25', until=until, reason='-3% day', by='rule:brake')
    assert hf.binding(LONG, '2026-11-27').key == H.BRAKE
    assert hf.binding(LONG, '2026-11-28').key == H.BRAKE                    # a Saturday rolls to Monday 11-30: still binds
    assert hf.binding(LONG, '2026-11-30').key == H.BRAKE
    assert hf.binding(LONG, '2026-12-01') is None                            # expired reads as not set
    assert hf.standing('2026-12-01') == []


def test_refusal_record_is_dated_idempotent_and_scored_as_a_forecast(tmp_path):
    hf = fresh(tmp_path)
    hf.set(H.KILL, session='2026-10-26', reason='at the line', by='rule:kill-line')
    rec = RefusalRecord(tmp_path / 'refusals.csv')
    g = Gate(hf, rec)
    allowed, refused = g.admit('insider desk', [LONG, dict(LONG, ticker='EEE')], today='2026-10-27', writer='t')
    assert allowed == [] and len(refused) == 2 and refused[0]['halt'].key == H.KILL
    g.admit('insider desk', [LONG], today='2026-10-27', writer='t')          # the writer runs again
    rows = rec.read()
    assert len(rows) == 2 and rows[0]['date'] == '2026-10-27' and rows[0]['halt_key'] == 'kill'
    closes = {'AAA': {'2026-10-27': 100.0, '2026-11-10': 94.0}, 'EEE': {'2026-10-27': 50.0, '2026-11-10': 55.0}}
    s = score(rows, closes, horizon=10)
    assert [r['refusal_looked'] for r in s] == ['protective', 'costly']
    assert summary(s) == {'n_refusals': 2, 'n_scored': 2, 'n_protective': 1, 'share_protective': 0.5, 'mean_entry_return_avoided': 0.02}


# ---------------------------------------------------------------- integrity: hand edits and rulings
def test_hand_edit_is_detected_and_a_ruling_cannot_lift_a_halt(tmp_path):
    hf = fresh(tmp_path)
    hf.set(H.KILL, session='2026-10-26', reason='at the line', by='rule:kill-line')
    with pytest.raises(PermissionError):
        hf.clear(H.KILL, session='2026-10-27', lifted='he said so', by='ruling:RG-001')     # a ruling never clears
    p = Path(hf.path)
    doc = json.loads(p.read_text())
    doc['halted'].pop(H.KILL)                                                            # lifted by hand
    p.write_text(json.dumps(doc))
    with pytest.raises(H.HaltsTampered, match='no clear row'):
        hf.read()
    assert hf.binding(SHORT, '2026-10-27').key == H.UNREADABLE                            # tampered refuses like unreadable
    with pytest.raises(H.HaltsUnreadable):
        hf.set(H.BRAKE, session='2026-10-27', reason='x', by='rule:brake')                 # and is never overwritten
    # a key added by hand, digest recomputed by hand: still no provenance row
    hf2 = fresh(tmp_path, 'b.json')
    doc = json.loads(Path(hf2.path).read_text())
    doc['halted'][H.KILL] = {'since': '2026-10-26'}
    doc['digest'] = H.digest(doc['halted'], doc['history'])
    Path(hf2.path).write_text(json.dumps(doc))
    with pytest.raises(H.HaltsTampered, match='ruling id'):
        hf2.read()


def test_a_ruling_may_hold_a_halt_longer_and_the_hold_blocks_the_mechanical_clear(tmp_path):
    hf = fresh(tmp_path)
    hf.set(H.KILL, session='2026-10-26', reason='at the line', by='rule:kill-line')
    hf.hold(H.KILL, ruling_id='RG-007', session='2026-10-27', reason='review: wait for the month-end')
    assert hf.standing('2026-10-28')[0].hold == 'RG-007'
    with pytest.raises(PermissionError):
        hf.clear(H.KILL, session='2026-11-30', lifted='rule met', by='rule:kill-line')
    rows = hf.read()['history']
    assert [r['action'] for r in rows] == ['set', 'hold'] and rows[1]['by'] == 'ruling:RG-007'
    hf.release_hold(H.KILL, ruling_id='RG-008', session='2026-12-01', reason='review done')
    hf.clear(H.KILL, session='2026-12-01', lifted='rule met', by='rule:kill-line')
    assert hf.standing('2026-12-02') == []
    with pytest.raises(ValueError):
        hf.set('stop-everything', session='2026-12-02', reason='x', by='rule:x')           # only typed keys


# ---------------------------------------------------------------- the layer: mechanical set and clear
def test_kill_line_sets_at_the_line_and_clears_only_by_the_full_reentry_rule(tmp_path):
    hf = fresh(tmp_path)
    pol = layer.Policy(kill_reentry_sessions=5, sma_window=10)
    eq = [100, 104, 108, 105, 97.2]                                                # 108 is the HWM; the line is 97.2
    c = curve('2026-09-01', eq)
    sessions = sorted(c)
    s = sessions[-1]
    rep = layer.close(hf, layer.SessionInputs(s, c, index_series(s, 40, sma_gap=-1.0)), pol)   # index below its SMA
    assert rep['kill']['tripped'] and 'SET kill' in rep['actions'][0]
    assert hf.standing(s)[0].key == H.KILL
    # equity back above the line the next session, index still below the SMA, only 1 session since: stands
    d = CAL.next_session(s); c[d.isoformat()] = 99.0
    rep = layer.close(hf, layer.SessionInputs(d.isoformat(), c, index_series(d, 40, sma_gap=-1.0)), pol)
    assert not rep['kill']['would_clear'] and hf.standing(d)[0].key == H.KILL
    # four sessions later (5 since set) the index is above its SMA but equity is AT the line: stands
    for _ in range(4):
        d = CAL.next_session(d); c[d.isoformat()] = 101.0
    c[d.isoformat()] = 97.2
    rep = layer.close(hf, layer.SessionInputs(d.isoformat(), c, index_series(d, 40, sma_gap=+1.0)), pol)
    assert rep['kill']['sessions_since_set'] == 5 and rep['kill']['index_above_sma'] and not rep['kill']['would_clear']
    # the next session all three hold: clears
    d = CAL.next_session(d); c[d.isoformat()] = 101.0
    rep = layer.close(hf, layer.SessionInputs(d.isoformat(), c, index_series(d, 40, sma_gap=+1.0)), pol)
    assert rep['kill']['would_clear'] and 'CLEARED kill' in ' '.join(rep['actions'])
    assert hf.standing(d) == []
    # an index series that does not reach the session gives no SMA, and no SMA never clears
    hf_b = fresh(tmp_path, 'b.json')
    hf_b.set(H.KILL, session='2026-09-01', reason='x', by='rule:kill-line')
    rep = layer.close(hf_b, layer.SessionInputs(d.isoformat(), c, index_series(s, 40, sma_gap=+1.0)), pol)
    assert rep['kill']['sma'] is None and not rep['kill']['would_clear'] and hf_b.standing(d)[0].key == H.KILL
    # the HWM never re-arms: 108 is still the high, so 97.2 trips again at once
    d = CAL.next_session(d); c[d.isoformat()] = 97.0
    rep = layer.close(hf, layer.SessionInputs(d.isoformat(), c, index_series(d, 40, sma_gap=+1.0)), pol)
    assert rep['kill']['hwm'] == 108 and rep['kill']['tripped'] and hf.standing(d)[0].key == H.KILL
    hist = hf.read()['history']
    assert [r['action'] for r in hist] == ['set', 'clear', 'set'] and all(r['by'] == 'rule:kill-line' for r in hist)


def test_blocked_rules_report_what_they_want_but_move_no_key(tmp_path):
    hf = fresh(tmp_path)
    pol = layer.Policy(sma_window=10, enforce_brake=False, enforce_regime=False)
    c = curve('2026-10-01', [100, 101, 96.5])                                      # a -4.46% day
    s = sorted(c)[-1]
    idx = index_series(s, 50, sma_gap=-1.0)
    rep = layer.close(hf, layer.SessionInputs(s, c, idx), pol)
    assert rep['brake']['tripped'] and rep['brake']['would_set'] and not rep['brake']['enforce']
    assert any('brake NOT ENFORCED: would set' in a for a in rep['actions'])
    assert hf.standing(s) == []                                                     # nothing moved
    on = layer.Policy(sma_window=10, enforce_brake=True)
    rep = layer.close(hf, layer.SessionInputs(s, c, idx), on)
    assert hf.standing(s)[0].key == H.BRAKE and hf.standing(s)[0].until == CAL.add_sessions(s, 2).isoformat()
    # regime: a month-end close below the SMA is reported, not set, while the flag is off
    hf2 = fresh(tmp_path, 'b.json')
    me = '2026-10-30'
    idx = index_series(me, 220, sma_gap=-1.0)
    c2 = curve('2026-10-01', [100] * 22); c2[me] = 100.0
    rep = layer.close(hf2, layer.SessionInputs(me, c2, idx), layer.Policy(sma_window=10))
    assert rep['regime']['month_end'] and rep['regime']['would_set'] and hf2.standing(me) == []


def test_budget_keys_set_and_clear_mechanically_and_unclassified_sectors_move_nothing(tmp_path):
    hf = fresh(tmp_path)
    pol = layer.Policy(sma_window=10)
    c = curve('2026-10-01', [100, 100.5, 100.2, 100.4])
    s = sorted(c)
    idx = index_series(s[-1], 50, sma_gap=+1.0)
    risk = {'insider desk': 9.1, 'fundamentals desk': 4.0, 'options arm A': 8.0}            # 8.0 is AT the ceiling: inside
    rep = layer.close(hf, layer.SessionInputs(s[0], c, idx, risk, {'semiconductors': 26.0, 'software': 10.0}), pol)
    assert rep['budgets']['would_set'] == ['budget:insider desk', 'budget:sector:semiconductors']
    assert sorted(h.key for h in hf.standing(s[0])) == ['budget:insider desk', 'budget:sector:semiconductors']
    assert hf.binding(DEBIT, s[0]) is None and hf.binding(LONG, s[0]) is not None
    # next close: the desk is back inside, the sector reading is UNCLASSIFIED -> the desk key clears, the sector key stands
    rep = layer.close(hf, layer.SessionInputs(s[1], c, idx, {'insider desk': 7.9}, None), pol)
    assert 'CLEARED budget:insider desk: back inside' in rep['actions']
    assert [h.key for h in hf.standing(s[1])] == ['budget:sector:semiconductors']
    rep = layer.close(hf, layer.SessionInputs(s[2], c, idx, {'insider desk': 7.9}, {'semiconductors': 20.0}), pol)
    assert hf.standing(s[2]) == []
    off = layer.Policy(sma_window=10, enforce_budgets=False)
    rep = layer.close(hf, layer.SessionInputs(s[3], c, idx, {'insider desk': 12.0}, None), off)
    assert rep['budgets']['would_set'] == ['budget:insider desk'] and hf.standing(s[3]) == []


def test_the_layer_never_writes_over_an_unreadable_or_tampered_file(tmp_path):
    hf = H.HaltFile(tmp_path / 'missing.json')
    c = curve('2026-10-01', [100, 89.0])
    s = sorted(c)[-1]
    rep = layer.close(hf, layer.SessionInputs(s, c, index_series(s, 50)), layer.Policy(sma_window=10))
    assert rep['halts_readable'] is False and not Path(hf.path).exists()


# ---------------------------------------------------------------- the census
def test_census_finds_a_writer_that_skips_the_read(tmp_path):
    good = tmp_path / 'good.py'
    good.write_text('from riskgate.gate import Gate\n\ndef book(entries, session):\n    ok, refused = Gate("h.json").admit("d", entries, today=session)\n    return ok\n')
    rogue = tmp_path / 'rogue.py'
    rogue.write_text('import csv\n\ndef book(entries, session):\n    return entries\n')
    rows = census.census([(str(good), 'book'), (str(rogue), 'book'), (str(tmp_path / 'absent.py'), 'book'), (str(good), 'nope')])
    assert [r['present'] for r in rows] == [True, False, False, False]
    assert 'does not call the gate' in rows[1]['note'] and rows[2]['note'] == 'file missing'
    # every committed example writer is gated
    writers = sorted((ROOT / 'examples' / 'writers').glob('*_writer.py'))
    assert writers, 'example writers missing'
    assert all(r['present'] for r in census.census([(str(w), 'book') for w in writers]))


# ---------------------------------------------------------------- re-entry rules and the stop-rule grid
def test_fixed_n_reentry_walks_back_into_a_bear_market_and_sma_waits():
    assert reentry.parse('N21') == ('N', 21) and reentry.parse('SMA') == ('SMA', None) and reentry.parse('BOTH21') == ('BOTH', 21)
    assert reentry.may_reenter('N', 21, sessions_since=21, close=90, sma=100)
    assert not reentry.may_reenter('SMA', sessions_since=400, close=90, sma=100)
    assert not reentry.may_reenter('BOTH', 21, sessions_since=400, close=90, sma=100)
    assert reentry.may_reenter('BOTH', 21, sessions_since=21, close=101, sma=100)
    assert not reentry.may_reenter('SMA', sessions_since=21, close=101, sma=None)          # no SMA yet: never re-enter on it
    # a long slide: 300 sessions falling 0.3%/day, then 300 rising 0.5%/day
    idx = pd.bdate_range('2000-01-03', periods=900)
    r = np.r_[np.full(300, 0.0005), np.full(300, -0.003), np.full(300, 0.005)]
    closes = pd.Series(100 * np.cumprod(1 + r), index=idx)
    g = rules.grid(closes, stops=(0.10,), reentries=('N21', 'SMA'), split='2001-06-01', sma_window=50)
    cells = {c['reentry']: c for c in g['cells'] if c['stop'] == '10%'}
    assert cells['N21']['fires'] > cells['SMA']['fires']                                  # N21 re-enters into the slide, again and again
    assert cells['N21']['maxdd'] < cells['SMA']['maxdd']                                  # and takes the deeper fall
    assert cells['SMA']['cagr'] > cells['N21']['cagr']


def test_grid_runner_hold_matches_the_formula_and_has_the_full_shape():
    idx = pd.bdate_range('2010-01-04', periods=1300)
    closes = pd.Series(100 * 1.0004 ** np.arange(1300), index=idx)                      # a smooth 10%/yr-ish ramp: no stop ever fires
    g = rules.grid(closes, split='2012-07-02')
    assert len(g['cells']) == 1 + len(rules.STOPS) * len(rules.REENTRIES)
    r = closes.pct_change().dropna()
    eq = (1 + r).cumprod()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    assert g['hold']['cagr'] == pytest.approx(round((eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1, 4), abs=1e-4)
    assert all(c['fires'] == 0 and c['cagr'] == pytest.approx(g['cells'][0]['cagr'], abs=1e-9) for c in g['cells'][1:])
    ad = rules.after_drop(closes, -0.03, 21)
    assert ad['n_events'] == 0 and ad['all_days_share_up'] == 1.0


def test_committed_grid_matches_its_yfinance_reproduction_except_the_disclosed_knife_edge_cell():
    a = json.loads((ROOT / 'results' / 'stop_rule_grid.json').read_text())
    b = json.loads((ROOT / 'results' / 'stop_rule_grid_yfinance_2026-10-24.json').read_text())
    assert a['hold'] == b['hold']
    diff = rules.compare(a, b, tol=1e-4)
    assert [d['cell'] for d in diff] == [('5%', 'SMA')]                                   # one fire apart; see README
    ten = {c['reentry']: c for c in a['cells'] if c['stop'] == '10%'}
    assert ten['SMA']['cagr'] == pytest.approx(0.1067, abs=5e-4) and ten['SMA']['maxdd'] == pytest.approx(-0.279, abs=5e-4)
    assert a['hold']['cagr'] == pytest.approx(0.1078, abs=1e-4) and a['hold']['maxdd'] == pytest.approx(-0.5519, abs=1e-4)


# ---------------------------------------------------------------- the measurement artefact
def test_bounded_exposure_caps_defined_risk_structures_at_their_max_loss_and_clips_betas():
    stock = exposure.Position('stock', delta_notional=50_000, beta=1.2)
    deep_itm_short_put = exposure.Position('short put, deep ITM', delta_notional=95_000, beta=1.0, max_loss=4_000)
    hot_name = exposure.Position('hot stock', delta_notional=10_000, beta=6.0)
    v1 = exposure.net_exposure([stock, deep_itm_short_put, hot_name], equity=100_000, version='v1')
    v2 = exposure.net_exposure([stock, deep_itm_short_put, hot_name], equity=100_000, version='v2')
    assert v1['net_exposure_pct'] == pytest.approx(215.0) and v1['n_structures_capped'] == 0
    assert v2['net_exposure_pct'] == pytest.approx(104.0)                                 # 60 + 4 + 10*4
    assert v2['n_structures_capped'] == 1 and v2['n_beta_clipped'] == 1 and v2['beta_clipped'][0]['clipped_to'] == 4.0
    with pytest.raises(ValueError):
        exposure.net_exposure([stock], 1.0, version='v3')


# ---------------------------------------------------------------- the calendar seam
def test_calendar_skips_weekends_and_holidays_and_knows_month_ends():
    assert CAL.next_session('2026-11-25').isoformat() == '2026-11-27'                     # Thanksgiving skipped
    assert CAL.roll_to_session('2026-09-05').isoformat() == '2026-09-08'                  # Sat -> Labor Day -> Tue
    assert [d.isoformat() for d in CAL.sessions_between('2026-10-22', '2026-10-27')] == ['2026-10-23', '2026-10-26', '2026-10-27']
    assert CAL.is_month_end('2026-10-30') and not CAL.is_month_end('2026-10-29')
    assert CAL.last_session('2026-07-04').isoformat() == '2026-07-02'                     # 07-03 observed holiday, 07-04 Saturday
    assert not CAL.is_session(dt.date(2027, 3, 26))                                      # Good Friday 2027
