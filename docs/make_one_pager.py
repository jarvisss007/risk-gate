"""Render the one-page case study (docs/one_pager.html -> .pdf + .png) with headless Chrome. Public SPY numbers, the
reviewer's quoted verdicts and the synthetic demo only; no account figure is read anywhere here.

  python docs/make_one_pager.py [--out DIR] [--stem NAME] [--copy-to DIR]      # CHROME=/path/to/chrome to override
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME = os.environ.get('CHROME', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
W, H = 1400, 1850


def img(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def page():
    g = json.loads((ROOT / 'results' / 'stop_rule_grid.json').read_text())
    ad = json.loads((ROOT / 'results' / 'after_3pct_day.json').read_text())
    demo = json.loads((ROOT / 'results' / 'demo_timeline.json').read_text())
    three = {c['reentry']: c for c in json.loads((ROOT / 'results' / 'stop_rule_3pct.json').read_text())['cells'] if c['stop'] == '3%'}['N21']
    cells = {(c['stop'], c['reentry']): c for c in g['cells']}
    hold, ten = g['hold'], cells[('10%', 'SMA')]
    n21 = cells[('10%', 'N21')]
    n_tests = (ROOT / 'tests' / 'test_riskgate.py').read_text().count('\ndef test_')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: {W}px {H}px; margin: 0 }}
* {{ box-sizing: border-box }}
body {{ margin: 0; width: {W}px; font: 15px/1.5 -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #1d2433; background: #fff }}
.wrap {{ padding: 44px 52px 30px }}
h1 {{ font-size: 30px; margin: 0 0 4px; letter-spacing: -0.3px }}
.sub {{ color: #6b7385; font-size: 13.5px; margin-bottom: 18px }}
ol {{ margin: 0 0 16px; padding-left: 24px }} ol li {{ margin: 0 0 7px }}
.why {{ background: #f2f4f8; border-left: 5px solid #1d2433; padding: 12px 18px; margin: 0 0 20px; font-size: 15px }}
h2 {{ font-size: 16px; margin: 18px 0 8px }}
.row {{ display: flex; gap: 26px; align-items: flex-start }}
.chart img {{ width: 760px; display: block }}
.loop {{ flex: 1; font-size: 12.5px }}
.step {{ border: 1.5px solid #b9c0ce; border-radius: 7px; padding: 6px 10px; margin: 0 0 4px; background: #fff }}
.step b {{ font-size: 13px }} .step.rev {{ border-color: #d6a03f; background: #fdf6e8 }}
.step.gate {{ border-color: #2f6fd6; background: #eef4fd }} .step.human {{ border-color: #1d2433; background: #f2f4f8 }}
.arrow {{ text-align: center; color: #8a93a6; font-size: 12px; line-height: 1; margin: 0 0 4px }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px }}
th {{ text-align: left; color: #6b7385; font-weight: 600; border-bottom: 1.5px solid #d5d9e2; padding: 6px 8px }}
td {{ border-bottom: 1px solid #e6e8ee; padding: 6px 8px; vertical-align: top }}
.bad {{ color: #b45309; font-weight: 600 }} .good {{ color: #1d4ed8; font-weight: 600 }}
.two {{ display: flex; gap: 26px }} .two > div {{ flex: 1 }}
.notes {{ color: #4a5163; font-size: 12.5px; margin-top: 16px }} .notes li {{ margin: 0 0 4px }}
code {{ font: 12px Menlo, monospace; background: #f2f4f8; padding: 1px 4px; border-radius: 3px }}
q {{ font-style: italic }}
</style></head><body><div class="wrap">
<h1>A risk layer the agents cannot talk their way around</h1>
<div class="sub">risk-gate · a case study in agent-governed research · Anupam Patil · 2026-10-24 ·
github.com/jarvisss007/risk-gate · research and engineering, not investment advice</div>

<ol>
<li><b>The ask.</b> A paper-only research estate of about eight trading desks, each run by agents, had its worst day on Thu 2026-10-22:
<b>−4.6%</b> on a day the S&amp;P 500 fell 1.2%. Its operator asked for a −3% stop, for the agents to short when the market falls,
and to "make it positive".</li>
<li><b>The data said no to the 3%.</b> On SPY 1993–2026 a 3% trailing stop turns {100 * hold['cagr']:.1f}%/yr into {100 * three['cagr']:.1f}%/yr
(re-entering after 21 sessions) and still falls {100 * abs(three['maxdd']):.0f}% at worst. After a −3% day SPY is up {100 * ad['share_up']:.0f}% of the time over
the next 21 sessions, the same as any day ({100 * ad['all_days_share_up']:.1f}%). Selling the close of a bad day buys nothing.</li>
<li><b>No market hedge would have helped.</b> SPY explains 3.4% of the account's daily P&amp;L (beta 0.50, n=34); semiconductors 7%.
Two of its three worst days were flat-SPY days. The risk was single names and option arms, and only size protects against that.</li>
<li><b>The re-entry rule decides, not the threshold.</b> Re-entering after a fixed number of sessions walks back into 2000–02 and 2008
(10% stop: worst fall {100 * n21['maxdd']:.0f}%). Re-entering on the first close above the 200-day average at 8–12% is one plateau:
<b>CAGR {100 * ten['cagr']:.1f}% vs {100 * hold['cagr']:.1f}% hold, worst fall {100 * ten['maxdd']:.1f}% vs {100 * hold['maxdd']:.1f}%</b>, in both halves of the sample.</li>
<li><b>A reviewer agent passed one rule and blocked three.</b> PASSED: the pre-registered 10% kill line with that re-entry rule.
BLOCKED: a −3% brake (<q>reinstates a mechanism already ruled out… he withdrew the 3% himself</q>), a 200-day regime gate
(<q>the evidence is SPY-on-SPY… authority for the concept, not for SMA200 / month-end / longs-only</q>), and per-desk budgets
(<q>this is his sizing ruling, not an enforcement</q>). The operator made that ruling himself the next morning, "budgets on", and
at that close the layer set five budget keys.</li>
<li><b>The same night the reviewer found a measurement artefact.</b> Options counted at full delta notional with no cap at their
maximum loss read net exposure as <span class="bad">211%</span> of equity; capped at max loss, <span class="good">113%</span>. Still over
the band, which is the honest finding. The fix went through the same reviewer as a versioned change to the pre-registered measure.</li>
</ol>

<div class="why"><b>Why this is in a portfolio:</b> the agents did not get a prompt saying "be careful". They got a file. Every
desk's writer must read one halt file before any new entry; an unreadable file refuses; a refused entry is recorded and later scored;
keys set and clear by rules written down in advance; a human may hold a halt longer and never lift it earlier; nothing is ever
sold to fix a number. Swap "trading desk" for "dispatch agent" or "pricing agent" and the layer is the same.</div>

<div class="row">
 <div class="chart"><h2 style="margin-top:0">SPY 1993–2026: a trailing stop at 5–25%, four re-entry rules</h2>
 <img src="data:image/png;base64,{img(ROOT / 'docs' / 'stop_rule_grid_compact.png')}"></div>
 <div class="loop"><h2 style="margin-top:0">The gate</h2>
  <div class="step"><b>Settled close</b> · the layer computes what every rule wants; marks are not results, so it runs once, after the close</div><div class="arrow">▼</div>
  <div class="step rev"><b>Reviewer agent</b> · read-only tools, adversarial brief · a key moves only behind a flag it passed</div><div class="arrow">▼</div>
  <div class="step gate"><b>Halt file</b> · typed keys (kill, brake, regime, budget:&lt;desk&gt;) · every change a history row · digest over both</div><div class="arrow">▼</div>
  <div class="step gate"><b>Writer</b> · reads <code>binding(entry)</code> before every new entry · a static census proves each writer has the call</div><div class="arrow">▼</div>
  <div class="step gate"><b>Refusal</b> · dated record, idempotent · scored later as a forecast: did the refused entry go on to win?</div><div class="arrow">▼</div>
  <div class="step gate"><b>Clear</b> · by the pre-stated rule only · a ruling may hold a key, never lift it · the high-water mark never re-arms</div><div class="arrow">▼</div>
  <div class="step human"><b>Owner decides</b> · at the gates: "budgets on" was his sizing ruling, recorded under its own id</div>
 </div>
</div>

<div class="two">
<div><h2>Enforced vs blocked (the week of 2026-10-22)</h2>
<table><tr><th>Rule</th><th>Reviewer</th><th>State</th></tr>
<tr><td><b>10% kill line</b> + mechanical re-entry</td><td class="good">PASS, conditions met</td><td>enforced from the next settled session</td></tr>
<tr><td><b>−3% brake</b>, 2 sessions</td><td class="bad">BLOCK</td><td>built, flag off; would-fires printed every session</td></tr>
<tr><td><b>200-day regime gate</b>, longs only</td><td class="bad">BLOCK</td><td>built, flag off; shadow-counted to the phase review</td></tr>
<tr><td><b>Per-desk 8% / sector 25% budgets</b></td><td class="bad">BLOCK → escalate</td><td>owner ruled "budgets on"; five keys set at that close</td></tr>
<tr><td><b>Exposure measure v1 → v2</b> (cap at max loss)</td><td>escalate: whose call?</td><td>owner: judged on v2 from that date; v1 printed beside it</td></tr>
</table></div>
<div><h2>Three ways around the gate, all refused (<code>examples/walkthrough.sh</code>)</h2>
<table><tr><th>Attempt</th><th>What happens</th></tr>
<tr><td>A writer skips the read</td><td>the census finds the function has no gate call; exit 2; the test suite fails before it ships</td></tr>
<tr><td>The halt file is deleted</td><td>every entry refused, shorts included: an unreadable file is never "no halt"</td></tr>
<tr><td>A key is lifted by hand</td><td>digest mismatch; the history row names the key that is gone with no clear; the only human move accepted is a ruling id that <i>holds</i></td></tr>
</table>
<p style="font-size:12.5px;color:#4a5163;margin:8px 0 0">Synthetic estate, {demo['sessions']} sessions: {demo['entries_allowed']} entries admitted,
{demo['entries_refused']} refused and recorded, {demo['keys_set']} keys set and {demo['keys_cleared']} cleared, every move by a rule.
The kill line tripped at −10.7%, stood 24 sessions, and cleared only when equity, the index's 200-day average and the 21-session count all agreed.</p></div>
</div>

<h2>Who did what</h2>
<table><tr><th>Role</th><th>What it is</th><th>What keeps it honest</th></tr>
<tr><td>Orchestrator</td><td>Claude Code session that ran the night's research and built the layer</td><td>Every rule it proposed went to the reviewer first; three of four did not pass</td></tr>
<tr><td>Reviewer</td><td>Subagent with no file-editing tools and an adversarial brief</td><td>Returns verdicts and reasons, never edits; its quotes are in <code>docs/reviewer_verdicts.md</code></td></tr>
<tr><td>Layer</td><td>Python, runs once per settled close</td><td>Computes what every rule wants; moves a key only behind a reviewed flag; never overwrites an unreadable file</td></tr>
<tr><td>Desk writers</td><td>One per desk, the only path to each book</td><td>Each reads the gate before a new entry; a static census proves it; refusals are recorded, not dropped</td></tr>
<tr><td>Owner</td><td>Anupam</td><td>Asked for the 3%; accepted the data's answer; made the sizing ruling himself, in his own words</td></tr>
</table>

<ul class="notes">
<li><b>In the repo:</b> the halt file, gate, refusal record, layer, re-entry rules, census and exposure measure, written fresh and generic;
the SPY stop-rule grid runner that reproduces the table from a yfinance download (28 of 29 cells to 4 decimals; the 5%/SMA cell is one
fire apart, a knife edge); a synthetic estate and demo; {n_tests} tests; the reviewer's quoted verdicts.</li>
<li><b>Kept out:</b> every account figure (equity, P&amp;L in currency, position counts, desk names beyond generic labels, any row), the
estate's code and paths, and anything that trades. The estate is paper-only; nothing here is advice or a return source.</li>
<li><b>Limits:</b> the SPY study is one index, one cost assumption (0.10%/side), one split (2010); the 10% was chosen before the grid, not
fitted to it; the account's beta and R² rest on 34 sessions; the layer gates entries, never exits, so it cannot stop a loss already held.</li>
</ul>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'docs'))
    ap.add_argument('--stem', default='one_pager')
    ap.add_argument('--copy-to', help='also copy the PDF and PNG here, named Risk_Gate_Case_Study_<date>')
    ap.add_argument('--date', default='2026-10-24')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    html, png, pdf = out / f'{a.stem}.html', out / f'{a.stem}.png', out / f'{a.stem}.pdf'
    html.write_text(page())
    profile = tempfile.mkdtemp(prefix='risk-gate-chrome-')          # a fresh profile per run: no lock left by an earlier run
    base = [CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', f'--user-data-dir={profile}']
    try:
        subprocess.run(base + [f'--window-size={W},{H}', f'--screenshot={png}', html.resolve().as_uri()], check=True,
                       capture_output=True, timeout=180)
        subprocess.run(base + ['--no-pdf-header-footer', f'--print-to-pdf={pdf}', html.resolve().as_uri()], check=True,
                       capture_output=True, timeout=180)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    print(f'wrote {html}, {png}, {pdf}')
    if a.copy_to:
        d = Path(a.copy_to).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        for src in (png, pdf):
            dst = d / f'Risk_Gate_Case_Study_{a.date}{src.suffix}'
            shutil.copyfile(src, dst)
            print(f'copied to {dst}')


if __name__ == '__main__':
    main()
