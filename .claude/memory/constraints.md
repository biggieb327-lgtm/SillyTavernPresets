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
**seen: 3** (2026-07-25 ×1, 2026-07-26 ×1, 2026-07-28 ×1)
The `healthcheck-status-checked` eval passed its own break test — it grepped for
`status_code`, which still appeared in a log line after the guard was removed. The
earlier `audit-plain-text` eval had an awk range that collapsed to one line and could
never fail.
**2026-07-28 — a new form: a check handed to the operator.** The group-chat pre-enable
step told the owner to `journalctl | grep GROUP_LEDGER_DIR` to confirm both pilots
shared a ledger directory. That warning is gated `if GROUP_MODE and GROUP_PEERS`
(bot.py:387), so on a not-yet-enabled instance it can never print: the check was
circular — it verified a precondition using a signal that only exists after the thing
the precondition gates. Empty output was the only possible result, and I would have read
it as a finding. Caught only because the owner reported the empty output rather than the
expected line.
**Constraint:** every new eval, test, scanner **or operator-facing verification step**
must be shown capable of producing a signal before it is trusted — run it against a
deliberately re-injected defect, or for a manual check, state the conditions under which
the expected output appears and confirm those hold. **"Nothing printed" is a result only
if something could have printed.**
**Graduated:** `add-regression-eval` and `fix-the-class` both require it for automated
checks. The operator-facing form is new here and is why this entry now names it
explicitly — a handed-over check is one nobody will break-test unless the author did.

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

### C10 — An unexplained default is not an unintended one: read the registries first
**seen: 1** (2026-07-27)
Having flipped three memory flags to default-on, I grepped for the rest of the "class"
(`os.getenv("X", "0")`), found five, and shipped ROADMAP 4.5 to `main` calling them
policy-grandfathered oversights needing re-decision. Four are the R6 evolution
experiments and were deliberately off, with the rationale written down in **three**
places I did not open: the changelog release title (*"R6 evolution experiments (all
gated, default off)"*), the `.env.example` section header (*"default off, pilot one
instance at a time"*), and — most damningly — ROADMAP's own rejected registry six lines
below where I typed the new item (*"revisit deliberately, not as a checklist"*). The
fifth, `DEVICE_RENDER`, is a cosmetic preference whose correct default is off.

The enumeration was by **code shape**, and code shape cannot distinguish an oversight
from a decision. Both look like `os.getenv("X", "0")`.

**Constraint:** before classifying anything as drift, oversight, or debt, check whether
it was a decision. This repo keeps four registries for exactly that — CLAUDE.md
§"Known-deliberate — do not 'fix' these", ROADMAP §"Rejected or already covered",
`AUDIT-2026-07-10.md` §rejected, and the originating changelog entry. Read the feature's
own release entry and its `.env.example` block before writing a proposal about it.

**The sharpest part:** `verify-external-audit` step 1 *is* this rule — "check the
rejected-claims registries first… any incoming claim matching an entry is closed with a
citation, zero code read" — and I had that skill loaded in the same session. I applied
it to claims arriving from outside and not to a claim I generated myself. **Findings you
produce are not exempt from your own verification protocol**; if anything they are the
ones nobody else will check.

**Not graduated.** A scanner could list default-off flags but not read intent, which is
the whole failure. The nearest mechanical aid already exists — `sweep.py` — and the
lesson is about what to do with its output: a sweep emits *candidates*, and C2 already
says triage every one. Prose, per rule 4.

### C11 — A diagnostic sent into a group chat is an in-world event
**seen: 1** (2026-07-28)
Debugging why priya was silent in the pilot group, I gave the owner `@priya_bot hi` as a
privacy-mode discriminator. It worked as a probe. It is also plain text in a live group,
so it entered jules's ledger and her persisted `conversation_history` as
`Brian: @priya_bot hi` — a handle ending in `_bot`, sitting beside a participant who
never answered. Jules then referred to priya as "a bot that's not gonna answer",
contradicting her own prompt ("To you they're all real people you know"). She did not
break character; she read the evidence I put in front of her and inferred correctly.

The group design works hard to keep mechanism out of the characters' world —
`_group_deliver` is allowlist-built so DM side effects cannot leak in, `/backup` is
refused in groups so state files can never be posted, commands other than `/chatid` are
default-denied. I routed around all of it with a debugging command, because I was
thinking about the handler path and not about the context window it lands in.

**Constraint:** before sending anything into a group chat as a diagnostic, ask what it
looks like *in the fiction*. Commands are safe — `group_guard` raises
`ApplicationHandlerStop` before `handle_message`, so they never reach the ledger or
history. **Plain text is not**: it is permanent, it is shared with every participating
character, and it cannot be cleared from inside the group (`/clear` targets
`update.effective_chat.id`, and commands are refused there). Probe from a DM, use
`/chatid`-style allowlisted commands, or phrase the probe in-world.

**Not graduated.** No hook can see this: the damaging call is the owner typing in
Telegram, not a tool call I make. The mechanical half is already covered by the group
evals; this is the operator-instruction half. Recorded in `group-chat-changes` under the
same reasoning as C1's split between the agent's half and the operator's half.

### C13 — A verification command that cannot fail is not verification
**seen: 4** (2026-07-27, 2026-07-28, 2026-07-29 ×2) — *promoted from the Minor log on the
third occurrence, as that entry said it should be.*
Three times a check was run against the wrong working directory, because this shell
persists cwd across calls and an earlier `cd` had moved it: `find .env.example` read as
repo-root when cwd was `telegram-companion-bot/`; `sed -n fleet-status.sh` failed on a file
that exists; and on 2026-07-29 `bash .claude/evals/run-evals.sh` printed *No such file or
directory*.

**Fourth occurrence (2026-07-29) — wrong *tree*, not wrong directory, and it printed a
green.** Merging the Routine fix, `git checkout main` succeeded and the suite reported
`23 passed, 0 failed` — a clean result that said nothing about my work, because **this
container's local `main` is a stale branch with no merge-base against `origin/main`**
(`ahead 76, behind 65`; `git merge-base` returns nothing, `git merge` refuses as
"unrelated histories"). Only the *count* gave it away: 23, when the suite I had just
extended has 28. A dropped eval count is a weak signal to depend on — a green from the
wrong tree looks exactly like a green.
**Durable repo fact:** merge to main by pushing the branch ref
(`git push origin <branch>:main`, a fast-forward when the branch sits on `origin/main`'s
tip). Do **not** `git checkout main` in a fresh cloud session and merge there.

**The third one exposed the sharper half.** The command was
`bash .claude/evals/run-evals.sh 2>&1 | tail -2 && git add -A && git commit …`. A pipeline's
exit status is the *last* command's, so `tail` returned 0, `&&` did not short-circuit, and
the commit proceeded on an eval run that never happened. The gate reported nothing and
blocked nothing — it could not have.

**What saved it, and what did not.** `.claude/hooks/eval-gate.sh` is a Stop hook that runs
the suite itself, from `$CLAUDE_PROJECT_DIR`, on every turn touching gated surfaces. So the
work was still verified and nothing shipped unchecked. The residual damage is narrower and
entirely mine: **I told the user a suite had passed when I had not seen it pass.**

**Constraint:** run repo tooling by absolute path, or `cd` in the same command. Never put a
gate in a pipeline — `cmd | tail` discards its exit status; capture output and echo `$?`,
or run the gate on its own line and read the result. And never report a check as green
without having read its actual output in this turn.
**Graduated 2026-07-29 — the mechanism already existed, which is the finding.**
`.claude/hooks/eval-gate.sh` is a Stop hook that runs the suite itself from
`$CLAUDE_PROJECT_DIR` on every turn touching gated surfaces, so the enforcement half was
never actually at risk: my broken invocation could not have shipped anything unverified.
No new hook is owed. The reporting half — claiming a green you did not observe — has no
code shape to intercept and stays prose, per rule 4.

### C12 — A command copied out of documentation is a claim about the past
**seen: 1** (2026-07-29)
I handed the owner `curl -fsSL <raw-base>/deploy/vps-sync.sh | bash -s -- emily`, lifted
from CLAUDE.md's Deployment block. It failed twice over: `<raw-base>` was a literal
placeholder I never substituted, and the URL is dead regardless — **the repo went private
the day before, which was the entire point of the release I had just been reading about.**
I had read v2026-07-28.3's changelog entry, which says in its first line that raw URLs 404
on a private repo, and still shipped the raw-URL command, because I copied the deploy doc
instead of the deploy script.

The doc was not lying; it was *stale*. CLAUDE.md described a deploy path that was correct
until 2026-07-28. A command in documentation is a historical claim about how the system
worked when someone last wrote it down — exactly the C8 problem, applied to instructions
rather than to readings.

**Constraint:** before handing over any operational command, take it from the thing that
executes it — the script's own usage header, the unit file, `--help` — not from prose
describing it. If it must come from a doc, check the doc against the most recent change to
the subsystem. Never emit a placeholder (`<raw-base>`, `<instance>`) inside a command you
present as runnable without saying explicitly that it needs substituting.

**Graduated immediately** — `no-live-raw-urls` in `run-evals.sh` fails on any
`curl`/`wget`/`BASE=` line carrying a `raw.githubusercontent` URL unless it is annotated
dead within 6 lines or its file opens with `<!-- evals: raw-urls-historical -->`. The
whole class is now mechanical: seven live deploy instructions across CLAUDE.md,
OPS_MANUAL.md, CHEATSHEET.md, MIGRATION.md and the `deploy-and-verify-fleet` skill were
rewritten to run from the checkout, and the phone-era remainder is annotated.

---

### C14 — A scanner cannot tell "this file does the bad thing" from "this file explains it"
**seen: 3** (2026-07-29 ×3) — *promoted immediately: two fresh occurrences in one session,
and `sweep.py constraints-drift` then surfaced a third already in the Minor log.*
Three times a checker confused executable text with the prose documenting it:
1. An extraction assertion asserted `'list_triggers' not in prompt` — and tripped on the
   new paragraph that *explains* `list_triggers` is unavailable.
2. The `routine-prompts-runnable` eval matched `"(public repo)"` across the whole of
   `routines.md` — and failed on the two prose lines recording that the "(public repo)"
   annotation was the stale thing being removed.
3. **(2026-07-29, found in the Minor log)** `no-live-raw-urls`'s first draft exempted a
   whole file if a marker word appeared early; CHEATSHEET.md's header *explains* that raw
   URLs 404, so the file the check most needed to guard went entirely unchecked.

Note 1–2 fail loud (false flag) and 3 fails silent (false exempt) — the same cause points
both ways, and the silent direction is the dangerous one. In every case the string was a
defect *in one region* (a `### Verbatim prompt` block, a runnable `curl` line) and
legitimate everywhere else. A file-wide match cannot tell those apart, so it makes
documenting a fix impossible — the more carefully a removal is explained, the worse the
check behaves.

**Constraint: before matching a defect string, name the region where it is a defect and
scope the match to it.** If the same string is legal elsewhere in the file, a file-wide
`in`/`grep` is the wrong instrument. Ask "where would this be *correct*?" — if the answer
isn't "nowhere", the pattern needs a boundary, not a longer blocklist.
**Graduated:** the eval now parses `### Verbatim prompt` fenced blocks and only searches
inside them (`.claude/evals/run-evals.sh`, `routine-prompts-runnable`), break-tested RED
on all three branches with the surrounding prose left intact.

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

- 2026-07-29 — Quoted a `for … ; do` loop as a two-line fragment to *illustrate* a change,
  with no body and no `done`. The owner pasted it and bash sat at a `>` continuation
  prompt — "didn't return to the command prompt" → **a fenced bash block is read as
  runnable, whatever it was meant to illustrate.** Show partial shell as prose or with an
  explicit `# fragment, not runnable` marker, or show the complete construct. (C12 family:
  the first case was a command that could not authenticate, this one cannot even parse.)
- 2026-07-29 — Told the owner `grep -c Warren emily_harper.json` should "expect 1". It is
  2 — the lorebook key *and* the content line, in a file I had written myself an hour
  earlier. The deploy was correct; my predicted value was wrong, and a wrong expectation
  handed to an operator reads as a failed deploy → when stating the expected output of a
  verification command, **measure it against the repo copy first**, don't recall it. (C3's
  neighbour: a check with a wrong expected value is as misleading as one that cannot fire.)
- 2026-07-29 — The first draft of the `no-live-raw-urls` eval let a whole file opt out if
  any marker word (`404`, `historical`, `DEAD`) appeared in its first 25 lines. CHEATSHEET.md's
  header *explains* that raw URLs 404, so the entire file was exempt and a re-injected
  defect passed — in the file the check most needed to guard. Caught only because I
  break-tested against a second file → **an opt-out matched loosely is an opt-out for
  everything.** Use a literal pragma for exemptions, and break-test in a file that is
  *not* the one you developed against. (C3 family, and the reason the 26→27 eval is
  trustworthy.) — **promoted 2026-07-29 into C14** as its third and only silent-failing
  instance; kept here because the pragma lesson is narrower than C14's region-scoping rule.
- 2026-07-28 — Wrote two full drafts of `preset-marcus.txt` arbitrating a paragraph-length
  conflict, because the handoff predicted his card would fight `preset-core.txt` "the way
  Bonnie's did". It doesn't: Bonnie's card states a numeric contract, his states no length
  at all. I had reasoned about the arbitration from `preset-core.txt` alone and had not
  read the other three layers in his stack; the real conflict (`preset-explicit.txt`'s
  standing-consent block deleting his defining behaviour) only appeared when I did →
  a per-character layer arbitrates against the WHOLE stack. Read every layer the instance
  will load before writing the one that resolves them. An inherited prediction is a
  hypothesis, not a finding (C9 family — this one was caught before shipping).
- 2026-07-28 — Filled the `.env.example` stack row for marcus by doing arithmetic off the
  table's own published numbers (8501 − emily's layer + marcus's) instead of measuring.
  The table is stale: `preset-core.txt` and `preset-explicit.txt` have grown since those
  rows were written, so every row reads ~60 raw low and my derived figure inherited the
  error → measure, don't derive from a published figure whose measurement date you did not
  check (C8 family). Fixed by measuring and annotating the staleness in the table.
- 2026-07-28 — `anchor-guard.sh` blocked a *content-anchored* `sed -i 's/^Layer is …/'`.
  Not my mistake and not a guard bug in the dangerous direction, but worth recording: line
  28 scans the entire command string for a line-address shape, and the `grep -n "434 raw
  tokens…"` half of the same compound command supplied `"` + digits + space + `r`, which
  is in its `[acdipsr]` command-letter class → the guard cannot tell which segment of a
  compound command the address-shaped text belongs to. Fail-safe direction, but "a guard
  that misfires gets disabled" is this file's own rule (C7), so it needs either
  per-segment matching or a note in the skill.
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
