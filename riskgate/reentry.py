"""Re-entry rules. The threshold of a stop rule gets the attention; the re-entry rule decides the result.

    N<k>      back in after k sessions flat (walks straight back into a bear market: 2000-02, 2008)
    SMA       back in on the first close above the long moving average (waits the bear out, late on the turn)
    BOTH<k>   both: at least k sessions flat AND close above the average

Labels are the ones the stop-rule grid prints ('N21', 'N63', 'SMA', 'BOTH21'). The layer's kill-line clear is
BOTH21 with a third condition stated in layer.py: the equity itself must be back above the line.
"""
import re

_LABEL = re.compile(r'^(N|BOTH)(\d+)$|^(SMA)$')


def parse(label):
    """'N21' -> ('N', 21); 'SMA' -> ('SMA', None); 'BOTH21' -> ('BOTH', 21)."""
    m = _LABEL.match(str(label).strip().upper())
    if not m:
        raise ValueError(f'unknown re-entry label {label!r}; use N<k>, SMA or BOTH<k>')
    if m.group(3):
        return 'SMA', None
    return m.group(1), int(m.group(2))


def may_reenter(mode, n=None, *, sessions_since, close=None, sma=None):
    """True when the rule allows re-entry. `sma` None (not enough history) never allows an SMA-based re-entry."""
    above = (close is not None and sma is not None and close > sma)
    if mode == 'N':
        return sessions_since >= n
    if mode == 'SMA':
        return above
    if mode == 'BOTH':
        return sessions_since >= n and above
    raise ValueError(mode)
