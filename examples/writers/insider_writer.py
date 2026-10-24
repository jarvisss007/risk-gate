"""A desk writer. The ONE write path to its book goes through the gate first; refused entries are recorded, not dropped."""
from _common import GEN, HALTS, append_rows
from riskgate.gate import Gate

DESK = 'insider desk'
BOOK = GEN / 'books' / 'insider.csv'
REFUSALS = GEN / 'refusals' / 'insider.csv'


def book(entries, session):
    """Append NEW entries dated `session`. Returns (allowed, refused)."""
    gate = Gate(HALTS, REFUSALS)
    allowed, refused = gate.admit(DESK, entries, today=session, writer=__file__.rsplit('/', 1)[-1])
    append_rows(BOOK, allowed)
    return allowed, refused


def candidates(session, ticker):
    return [{'date': session, 'ticker': ticker, 'side': 'long', 'structure': 'stock', 'notional': 1.0,
             'thesis': '[insider] synthetic'}]
