"""Shared by the example writers: where the synthetic estate's generated files live, and the one way to append a row."""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
GEN = Path(os.environ.get('RISKGATE_ESTATE_GENERATED', ROOT / 'examples' / 'estate' / 'generated'))
HALTS = GEN / 'halts.json'
COLS = ['date', 'desk', 'ticker', 'side', 'structure', 'notional', 'thesis']


def append_rows(book, rows):
    book.parent.mkdir(parents=True, exist_ok=True)
    new = not book.exists()
    with open(book, 'a', newline='') as fh:
        w = csv.DictWriter(fh, COLS, extrasaction='ignore', restval='')
        if new:
            w.writeheader()
        w.writerows(rows)
