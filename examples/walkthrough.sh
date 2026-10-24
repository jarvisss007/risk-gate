#!/usr/bin/env bash
# The gate end to end on the synthetic estate, then three attempts to get around it. All three are refused.
#   1. a writer that skips the read      -> the census fails (exit 2), as the test suite would
#   2. the halt file deleted             -> every entry refused: an unreadable file is never "no halt"
#   3. a key lifted by hand              -> the file reads as tampered; the history demands a ruling id, and a ruling can only hold
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"
W=$(mktemp -d)
export RISKGATE_ESTATE_GENERATED="$W/generated"

echo "== 0. the layer runs on the synthetic estate (kill + budgets enforced; brake + regime report only)"
$PY examples/demo.py | tail -4
H="$W/generated/halts.json"
echo
echo "== the halt file is consistent and its keys have provenance"
$PY -m riskgate verify --halts "$H" | head -3

echo
echo "== 1. a writer that skips the read: copy a desk writer and remove its gate call"
sed 's/gate.admit(DESK, entries, today=session, writer=.*)/(list(entries), [])/' examples/writers/insider_writer.py > "$W/rogue_writer.py"
$PY -m riskgate census examples/writers/insider_writer.py:book examples/writers/options_writer.py:book "$W/rogue_writer.py:book" \
    || echo "   (refused: exit $? - a writer without the read never passes the census, so the suite fails before it ships)"

echo
echo "== 2. the halt file is deleted: does a quiet morning follow?"
$PY -m riskgate ruling --halts "$H" --id RG-DEMO set kill --session 2026-12-07 --reason "a review halts the estate" >/dev/null
mv "$H" "$H.gone"
$PY -m riskgate check --halts "$H" --desk "pattern desk" --side short --structure stock --ticker EEE \
    || echo "   (refused: exit $? - even a short, which no regime key would bind)"
mv "$H.gone" "$H"

echo
echo "== 3. a key is lifted by hand: edit the JSON and delete the kill key"
$PY - "$H" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d['halted'].pop('kill'); json.dump(d, open(p, 'w'), indent=1)
PY
$PY -m riskgate check --halts "$H" --desk "insider desk" --side long --structure stock --ticker AAA \
    || echo "   (refused: exit $?)"
echo "   ... and the only human move the file accepts is a ruling that HOLDS a key, never one that lifts it:"
$PY -m riskgate ruling --halts "$H" --id RG-DEMO-2 clear kill --session 2026-12-08 || true
echo "scratch folder: $W"
