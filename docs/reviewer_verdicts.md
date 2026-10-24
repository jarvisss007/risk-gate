# The reviewer's verdicts, Thu 2026-10-22 (Pacific)

The reviewer is a `prereg-reviewer` subagent with read-only tools (Read, Grep, Glob, Bash) and an adversarial brief: any
proposed change to a pre-registered rule goes to it BEFORE the change is made, and it returns a verdict and reasons,
never an edit. Four rules were put to it the night of the worst day. The quotes below are the parts of its verdicts
that decided each one; everything else in its reports concerns the estate's internals and stays private.

| Rule proposed | Verdict | In its words |
|---|---|---|
| **10% kill line** (pre-registered a week earlier; equity at or under 90% of the closing high-water mark halts every new entry), with the mechanical re-entry rule (equity back above the line, index above its 200-day average, 21 sessions passed; the high never re-arms) | **PASS** with conditions, all met in the enforcing commit | the re-entry rule's third condition to be stated everywhere the rule is described; the grid cell it rests on to be cited; the grid's high-water re-arm to be disclosed |
| **−3% brake** (a day at or under −3% halts new entries for two sessions) | **BLOCK** | "reinstates a mechanism already ruled out… he withdrew the 3% himself… the forward record is the only record, and there is none" |
| **200-day regime gate** (a month-end close below the 200-day average halts new longs until a month-end close above) | **BLOCK** as enforcement; register as a shadow-counted variant | "the evidence is SPY-on-SPY… SPY explains ~3% of the firm's daily variance… authority for the concept, not for SMA200 / month-end / longs-only" |
| **Per-desk budgets** (a desk over 8% of equity at risk, or a sector over 25%, halts that desk's or sector's new entries) | **BLOCK**; escalate to the owner | "four of twenty sessions cannot satisfy [the pre-stated review gates]… this is his sizing ruling, not an enforcement" |

What followed:

- The kill line was enforced from the next settled session. Every desk writer was given the read (the gate census, a
  static check that each writer's book-append function calls the gate, became a resolver check).
- The brake and the regime gate were built, their flags left off, and what they *would* have done is printed every
  session. The brake would have fired on the worst day; the record of would-fires is the forward record the reviewer
  said did not yet exist.
- The budgets were an escalation, and the owner answered it the next morning with two words, "budgets on": his sizing
  ruling, recorded under its own id. At that day's settled close the layer set five budget keys for desks and arms over
  their 8% ceiling.
- The same night, the reviewer found a measurement artefact unrelated to the four rules: the net-exposure reading
  counted each option structure at its full delta notional with no cap at the structure's maximum loss, which read as
  211% of equity. Capped at max loss and with betas clipped to a stated range, the same book read 113%. The bounded
  reading was proposed as version 2 of the pre-registered measure, went to the same reviewer (which escalated the
  question of which reading a rule is judged on), and the owner ruled the next morning: judged on the bounded reading
  from that date; version 1 printed beside it until the phase review; nothing back-filled.

What this is not: a return source. Both readings said the estate was over its exposure band. The kill line costs about
3.6 points a year of CAGR in the 2010–26 bull half of the SPY sample and earns about 3 points a year in 1993–2009; it
buys a smaller worst fall, not a higher return. None of the four rules makes a losing week green.
