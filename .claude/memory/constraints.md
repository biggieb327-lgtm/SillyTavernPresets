# Constraints — mistakes made doing the work, and the rule each one earned

**This file is not the operational log.** Keep them apart or both rot:

| File | Records | Example |
|---|---|---|
| `operational-log.md` | the **system** failed — a bot, a deploy, the fleet | "five instances had a dead man's switch that reported OK while returning 400" |
| **this file** | the **work** went wrong — a wrong command, a premature "done", a theory asserted as fact | "ran phone tooling on the VPS" |

The test: *did a bot misbehave, or did we?* Bot → operational log. Us → here.

## Rules for this file

1. **Add an entry the moment a mistake is recognised**, before continuing the task.
   Not at the end of the session — that is when they get forgotten or softened.
2. **One line for what happened, one imperative line for the constraint.** If the
   constraint needs a paragraph it belongs in a skill; link it from here instead.
3. **Increment `seen` when the same mistake recurs.** The count is the whole point —
   it is what tells a future session which constraints are load-bearing.
4. **At `seen: 2`, it graduates.** A constraint that failed twice is not a documentation
   problem, it is a missing guard: write a hook, an eval, or a `sweep.py` scanner and
   link it. This mirrors the standing repo rule that a failure recurring twice earns an
   eval.
5. **Own it plainly.** "I asserted X without evidence" — not "it was unclear". A
   sanitised entry teaches nothing.

---

## Active constraints

### C1 — Confirm the host before any host-specific command
**seen: 4** (2026-07-19 ×1, 2026-07-26 ×3)
Phone tooling (`update-all.sh`, `tmux kill-session`, `pkg`) was run on the VPS, and
VPS commands (`journalctl`, `sudo`, `/opt/...`) on the phone. Each failure looked like
a broken tool rather than a wrong machine, and one silently no-op'd mid-cutover.
**Constraint:** before emitting a host-specific command, state which host it is for.
Before running one, `uname -o` — `Android` = phone, `GNU/Linux` = VPS.
**Graduated:** documented in `CHEATSHEET.md` (top section) and MIGRATION.md step 3.
Still recurring — needs a stronger guard than prose.

### C2 — Name the class before calling a fix done
**seen: 2** (2026-07-26 ×2)
v2026-07-26.6 fixed one `pip install` hint and shipped; three more hardcoded install
hints survived, one of them user-facing. Earlier the same night, the restart-storm fix
turned out to be three phone-era assumptions in one function, not one.
**Constraint:** write the class in one sentence before claiming done. Then run
`python3 .claude/tools/sweep.py` and triage every candidate.
**Graduated:** `.claude/skills/fix-the-class/SKILL.md`; new `install-hint` scanner in
`sweep.py` (v2026-07-26.8).

### C3 — Prove a check RED before trusting it GREEN
**seen: 2** (2026-07-25 ×1, 2026-07-26 ×1)
The `healthcheck-status-checked` eval passed its own break test — it grepped for
`status_code`, which still appeared in a log line after the guard was removed. The
earlier `audit-plain-text` eval had an awk range that collapsed to one line and could
never fail.
**Constraint:** every new eval, test, or scanner must be run against a deliberately
re-injected defect and observed to fail, before it is trusted.
**Graduated:** `add-regression-eval` and `fix-the-class` both require it.

### C4 — Search for the bug's shape, not its remembered vocabulary
**seen: 1** (2026-07-26)
Swept for phone-era assumptions by grepping `Termux|Android|tmux|run-bot`, and missed
`pip install "python-telegram-bot[job-queue]"` — a live instance of the class whose
string contains none of those words. The scanner found it immediately.
**Constraint:** grep for the *mechanism* (the shape of the defect), not the words you
remember writing. If a mechanical scan is possible, write it instead of grepping.

### C5 — Label a theory as a theory until evidence arrives
**seen: 1** (2026-07-26)
Asserted that `watchdog.sh` was running from cron and that this explained bonnie's
resurrection. The interval was consistent with it but never confirmed, and the real
mechanism (watchdog relaunches on a *missing tmux session*, in any mode) made the cron
question irrelevant. The wrong frame was stated as fact in the middle of an incident.
**Constraint:** while diagnosing, mark unconfirmed causes as unconfirmed, and say what
evidence would settle them. Confidence follows evidence, not fluency.

### C6 — A migration invalidates assertions, not just docs
**seen: 1** (2026-07-26)
After the VPS cutover, a *test* still asserted phone-era behaviour as correct
(`test_graceful_stop_alone_still_counts`, justified by "an OEM battery-manager
SIGTERM"), and an operator-facing alert still pointed at `bot.log` and the Android
phantom killer. Three stale assumptions in one function.
**Constraint:** after any platform change, sweep tests and user-facing strings, not
only documentation. An assertion is a claim about the world too.
