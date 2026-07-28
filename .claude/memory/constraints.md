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
   problem, it is a missing guard: write a hook (the agent did X), a `sweep.py` scanner
   (this shape exists elsewhere in the repo), an eval (this can regress in bot.py), or —
   when no mechanism can see the mistake — **a section in the relevant skill**, and link
   it. This mirrors the standing repo rule that a failure recurring twice earns an eval.
   *Skills were added to this list on 2026-07-27: the original three-way rule would have
   rejected the only correct answer for C8, whose failure mode no hook or scanner can
   detect. Prefer a mechanism; accept prose only when you can say why nothing mechanical
   would see it.*
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

### C8 — Ask what a reading actually measures before concluding from it
**seen: 3** (2026-07-26 ×2, 2026-07-27) — *promoted by check 6 of the weekly hygiene
Routine, from three Minor entries sharing one cause.*
Three conclusions were drawn from readings that did not mean what they appeared to:
- an `/audit` line reporting jules on `mimo-v2.5-pro` was hours old; her model had been
  changed since, and a test recommendation was built on it — **stale**
- `grep '^MODEL='` returned nothing across six instances, read as "no model set"; the
  variable is `NANOGPT_MODEL` — **wrong scope**; the grep was answering a question
  nobody asked
- `/errors` output full of `Conflict` tracebacks was read as a live fight; `errors.log`
  is historical, persists across restarts, and travels inside migration tars — **wrong
  currency**
Two of these sent a live diagnosis down the wrong path for several rounds.
**Constraint:** before concluding from any output, state what it actually covers — how
current is it, what scope does it span, and what would absence of a result mean? A grep
that finds nothing is only evidence if the pattern was right. A log tail proves what was
written, never what is happening now. A reading from earlier in the session is a
historical claim, not a live one.
**Graduated 2026-07-27 — prose, deliberately.** No hook, scanner, or eval can see
"trusted a reading that did not mean what it appeared to": there is no code shape and no
tool call to intercept. Extended
`.claude/skills/fix-the-class/SKILL.md` §"The two questions that catch what greps miss",
which already carries the same family of lesson (`BOT_TIMEZONE` was *referenced*
everywhere and still did nothing). This is the case that forced rule 4 above to admit
skills as a graduation target.

### C9 — Verify a load-bearing hypothesis before shipping, not after
**seen: 1** (2026-07-27)
v2026-07-27.1 shipped to `main`, CI-green, on the claim that all six instances had run
for two weeks with their memory-hygiene loops disabled. The claim was **labelled
`[hypothesis]`** in the operational log, in the changelog, and in the report to the
owner — and the release's entire justification still rested on it. It was false: every
`.env` set all three variables explicitly. The evidence that would settle it was one
command, and the owner ran it in one message when finally asked — *after* the merge.

The inference itself was empty, not merely unlucky: bot.py's default and a commented-out
`.env.example` say nothing whatsoever about a live `.env`, and per-instance override is
the normal way this fleet is configured. There was no weak evidence here to weigh, only
the absence of any.

**Constraint:** before a change ships, list what it *depends on being true*. Anything on
that list marked `[hypothesis]` is a blocker, not a caveat — verify it, or scope the
change so it doesn't depend on it. Honest labelling discharges the duty to *flag*
uncertainty; it does not discharge the duty to *resolve* it. Specifically: **this
container cannot reach the fleet, so every claim about live instance state is a question
for the owner.** Ask before, not after — it cost one message here and one rewritten
release entry.

**Relation to C5/C8:** C5 says label a theory as a theory (complied with — and it was not
enough). C8 says ask what a reading measures (this failure had *no* reading to measure).
C9 is the missing third: what a conclusion is allowed to carry.

**Not graduated to a mechanism.** A hook cannot know which of a diff's premises are
load-bearing, and an eval cannot query a machine it has no route to. Prose, deliberately,
per rule 4 — with the concrete precondition written into ROADMAP 4.5 so the next instance
of this exact question hits a check instead of an inference.

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

- 2026-07-27 — `find . -name .env.example` returned `./.env.example` and I read that as
  repo-root; the sandbox had reset cwd to `telegram-companion-bot/`, so both Edit calls
  failed on a path that did not exist → a relative path is only as good as the cwd you
  assumed. This shell resets cwd between calls: use absolute paths, or print `pwd` in
  the same command that prints the relative result. (C8 family — the reading was true,
  its base was not what I assumed.)
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
