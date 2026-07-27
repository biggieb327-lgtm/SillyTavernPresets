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
**Graduated 2026-07-27:** `.claude/hooks/host-guard.sh` + `host_guard.py`, a Stop hook.
It blocks the turn when a fenced command block mixes VPS-only and phone-only commands,
when a host-specific block appears in a message that never names its host, or when a
`# host:` pragma contradicts the commands inside the block. Nine-case matrix, including
fail-open on a malformed payload.
**What it does NOT cover, deliberately:** the fleet is on a machine this container
cannot reach and the owner runs these commands by hand, so nothing here can stop a
paste into the wrong shell. The hook enforces only the agent's half — that every block
handed over is attributable to exactly one host. The operator's half stays prose
(`CHEATSHEET.md`: `uname -o` before anything host-specific).

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

### C7 — Anchor edits on content, not position
**seen: 2** (2026-07-26, 2026-07-27) — *promoted from the Minor log by
`sweep.py constraints-drift`, its first real find.*
Two edits went wrong the same way: **the surrounding structure was not confirmed before
writing.** A paragraph was added to a function anchored on `n = 0` — a content anchor,
correctly matched — but the docstring had already closed above it, so the prose landed
in the function body and broke the module until `py_compile` caught it. A Routine
prompt was spliced into `routines.md` using line indexes read off `sed` output, off by
one, in a file already edited twice that session.
**Corrected framing (2026-07-27):** the first draft of this entry said both failures
"located the edit point by *where it was* rather than *what it says*". That is only
true of the second. The first used a content anchor and still failed, because the
anchor was right and the assumption about what sat *above* it was wrong. The shared
cause is not "used line numbers" — it is "did not verify the surrounding structure".
Getting this wrong would have aimed the guard at the wrong thing.
**Constraint:** before an in-place edit, confirm what actually surrounds the anchor —
read it, do not infer it. Never address an edit by line number; prefer the Edit tool,
which matches on a unique surrounding string and cannot drift.
**Graduated 2026-07-27 (partially, and the gap is the point):**
`.claude/hooks/anchor-guard.sh`, a PreToolUse hook, blocks `sed -i` carrying a numeric
line address against anything outside `/tmp`/scratchpad. Nine-case matrix; the four
must-not-fire cases (content-anchored substitution, read-only `sed -n`, throwaway
paths, `# anchor-ok`) all pass.
**What it does NOT cover:** the docstring failure. That was an Edit-tool call whose
anchor matched correctly — no hook can see that the *assumption above the anchor* was
wrong. Detecting line-index splicing inside a Python heredoc was also rejected:
`readlines()` + slice + write cannot be matched without false positives, and a guard
that misfires gets disabled. Both halves stay prose here. The existing backstop for the
first is the compile check, which caught it on the next call.

---

## Minor — running log

**Mistakes made and fixed mid-task** — the ones that never reach the owner because
they were caught a minute later: a wrong path, a grep for the wrong variable name, a
broken test harness, a script that didn't parse, an assumption corrected the moment
evidence arrived. **These do not earn constraints on their own** — kept separate so
the numbered list above stays high-signal and the `seen: 2` graduation rule keeps
meaning something.

**Log it *because* you fixed it, not despite that.** "I caught it immediately, no harm
done" is the reflex that keeps this section empty and useless. Self-corrected errors
are the highest-frequency signal available — they are invisible to everyone but the
person who made them, they cost real minutes, and they are where the repeating shapes
show up first. A section with nothing in it means under-reporting, not a clean run.

**The promotion rule:** when two minor entries share a cause, delete both and write a
numbered constraint. That is the whole reason to log them; a minor entry nobody ever
promotes was still worth ten seconds to write.

Format: `date — what happened → what to do instead`. One line. Newest first.

- 2026-07-27 — Recommended jules as the 3.8 A/B subject on a model reading taken hours
  earlier; she had been moved to `glm-5.1:thinking` since, which disqualified her under
  that item's own precondition → re-read live config at the moment of a recommendation,
  not from earlier in the same session. State-in-context goes stale.
- 2026-07-27 — Break-tested the C1 hook through a bash heredoc; backtick escaping meant
  the code fences never reached the transcript, so all three cases "passed" and the
  guard looked dead. The *test* was broken, not the code → when a break-test shows
  nothing firing, suspect the harness before the check. Build fixtures in Python, not
  shell quoting.
- 2026-07-27 — Wrote a `sweep-ok` pragma check for `install-hint` that matched
  `"sweep-ok:"` with a colon, while the inline markers had none, so the helper kept
  self-reporting → match pragmas loosely; make the scanner fit the annotation, not the
  other way round.
- 2026-07-26 — `paste -sd '; '` in session-audit.sh produced `C1;C2 C3`: `-d` takes a
  *cycling list* of delimiter characters, not a delimiter string → join with one
  character, then substitute.
- 2026-07-26 — Grepped for the primary model as `^MODEL=` when the variable is
  `NANOGPT_MODEL`, and reported "no model set" on six instances → check the variable's
  real name in source before drawing conclusions from a grep that found nothing.
- 2026-07-26 — Read `/audit` output as live state when `errors.log` is historical and
  survives migration in the tar; concluded a fight was ongoing that had ended → for
  "is it happening now", use a bounded `journalctl` window, never a log tail.
