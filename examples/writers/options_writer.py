"""The options desk's writer: two arms, each gated by its own budget key; debit structures pass a regime key, credit ones do not."""
from _common import GEN, HALTS, append_rows
from riskgate.gate import Gate

DESK = 'options desk'
BOOK = GEN / 'books' / 'options.csv'
REFUSALS = GEN / 'refusals' / 'options.csv'
ARMS = {'options arm A': 'debit', 'options arm B': 'credit'}


def book(entries, session):
    """Append NEW entries dated `session`. Each entry names its arm. Returns (allowed, refused)."""
    gate = Gate(HALTS, REFUSALS)
    allowed, refused = gate.admit(DESK, entries, today=session, writer='options_writer.py')
    append_rows(BOOK, allowed)
    return allowed, refused


def candidates(session, ticker):
    tickers = {'options arm A': ticker, 'options arm B': 'DDD'}
    return [{'date': session, 'ticker': tickers[arm], 'side': 'long', 'structure': structure, 'arm': arm, 'notional': 1.0,
             'thesis': f'[{arm}] synthetic'} for arm, structure in ARMS.items()]
