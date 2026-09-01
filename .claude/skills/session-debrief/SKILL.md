---
name: session-debrief
description: Close out a session that has reached a real stopping point — harvest the lessons into the memory layer, decide what earns a mechanism, and leave a handoff the next session can act on. Load when the work is done and green, when the user says they're wrapping up, or before a long session ends. Encodes the 2026-08-10 autopsy, where the dominant failure was verification instruments that could not fail.
---

# Session debrief

A session's mistakes are worth more than its commits, and they evaporate first. The commits
are in git; the five near-misses, the hypothesis you withdrew for a bad reason, and the
check that passed for the wrong reason exist only in the transcript, which nobody reads
again. This turns that into constraints, mechanisms, and a handoff — before the context
window closes.

**This is a harvest, not a victory lap.** If the output reads like a summary of
accomplishments, it has failed.

## When NOT to use

- **Mid-task.** A stopping point means the work is done and green, or deliberately parked
  with the state written down. A debrief over unfinished work invents lessons from a
  situation that has not finished teaching them.
- **Short or single-purpose sessions.** One fix, one review, one question — an
  operational-log row (if something failed) or a Minor entry (if you slipped) is the whole
  debrief. A three-file ceremony for a two-commit session is noise.
- **When nothing went wrong and nothing shipped.** Say so in one line and stop. A clean
  session is a real outcome; manufacturing findings to fill sections is how the memory
  layer fills with entries nobody promotes.

## What counts as a good stopping point

**Run the check first — do not eyeball this list:**

```bash
bash .claude/tools/debrief-check.sh
```

It decides three of the four conditions mechanically and refuses to guess the fourth. If
it is red, you are not at a stopping point and the debrief would be recording fiction.

All four, or it is not one:

1. `bash .claude/tools/verify.sh` green, output read in this turn.
2. Work merged to `main` and pushed; CI polled and reported `<sha> | completed | success`.
3. Everything the user asked for is either done or explicitly named as not-done, with why.
4. Anything left running (a PR subscription, a background task, a `/loop`) is recorded
   somewhere durable, not just described in chat.

## Procedure

### 1. Rebuild the session from the record, not from memory

Memory of a long session is compressed and flattering. Read the actual artifacts:

```bash
git log --oneline <first-sha>..HEAD                      # what shipped
git diff --stat <first-sha>..HEAD                        # and how big
grep -c "^- $(date +%Y-%m-%d) —" .claude/memory/constraints.md
grep -c "^| $(date +%Y-%m-%d) |" .claude/memory/operational-log.md
```

**Count, don't estimate.** On 2026-08-10 the phrase "~20 hand-rolled boolean idioms"
reached a shipped changelog; the real number was 55, and a whole third idiom matched
neither pattern behind the estimate. If a number is a floor — a capped counter, a
pattern-limited scan, a sample — say *floor* and say what bounds it.

### 2. Group the mistakes by cause, never by chronology

A list in the order things happened teaches nothing; the same cause wearing four costumes
is the finding. For each group ask: **is there already a constraint for this?**

- Already a constraint, and it fired again → increment `seen`, add the occurrence as a
  bullet, and **re-read its graduation note against the new occurrence**. A stated reason
  for leaving something prose has a *scope*; check the new failure against the scope, not
  against the conclusion. That is what unblocked C18 on 2026-08-10 — its "nothing can
  observe this" was true of multi-injection and false of "did the injection land".
- Two-plus entries sharing a cause → mint a numbered constraint, delete the entries.
- No pattern, self-corrected → Minor log, one line, and move on.

### 3. Separate what *worked*, and say it plainly

The debrief is not only a defect list. Record the hooks that fired correctly, the check
that caught something, the mechanism added earlier that paid off. Machinery whose wins go
unrecorded looks like pure overhead at the next cleanup pass and gets deleted.

### 4. Decide what earns a mechanism — and grep before proposing one

Rule 4 of `constraints.md`: at `seen: 2` a constraint owes a hook, eval, scanner, or skill
section. Prefer a mechanism; accept prose only when you can say *why nothing mechanical
would see it*, and scope that claim narrowly.

**Before proposing any mechanism, check whether it already exists:**

```bash
grep -rn "<the thing>" .claude/evals/ .claude/tools/ .claude/hooks/
```

On 2026-08-10 a `verify.sh` change was proposed "because nothing catches a module-level
NameError" — `run-evals.sh` had had the `bot-imports` eval since 2026-07-11, and the
proposal was written into a committed autopsy before the grep happened. That is C22, made
while documenting the session's other mistakes.

### 5. Build it, and break-test it with the tool

Any check written during a debrief goes through `.claude/tools/break-test.sh`, which proves
the injection landed and the revert restored. Hand-run break-tests failed ~28% of the time
in the session that produced it. If the new check is a `sweep.py` scanner, add
`gate_corpus` fixtures too — break-tests run against the *real* `bot.py`, so they are blind
to any defect that only shows up on input shaped differently, which is exactly how the
`async-blocking` allowlist shipped with a false-positive mode.

### 6. Write the outputs

| what | where | when |
|---|---|---|
| a failure the **system** had | `.claude/memory/operational-log.md` row | it was diagnosed and resolved |
| a mistake **we** made doing the work | `.claude/memory/constraints.md` (numbered or Minor) | always, including self-corrected |
| an **intervention to the machinery** that targeted a failure class (a new/widened guard, eval, hook, skill, or preset) → a `pending` row; or a prior `pending` intervention that this session saw **hold** or **recur** → flip it | `.claude/memory/skill-impact.md` | whenever the session shipped such a change, or observed one's outcome |
| a **project-changing decision** — a choice among real alternatives (architecture, a contract, deploy/memory layer, a shipped default, a will/won't, an approach ruled out) | `.claude/memory/decisions.md` (`log-decision`) | whenever the session settled one and it isn't logged yet |
| the session-level pattern analysis | `.claude/SESSION-AUTOPSY-<date>.md` | only for long/multi-release sessions |
| shipped item status | `ROADMAP.md` / `IMPROVEMENTS_PLAN.md` | anything moved |
| a live Routine created | — | n/a: Routines are retired here (2026-08-22); `routines.md` is historical |
| the fact that a debrief ran | `.claude/memory/debrief-log.md` via `bash .claude/tools/debrief-check.sh --record` | always — it is the only durable trace |

### 7. Leave the handoff in the repo, not in chat

Name what is open, what is scheduled, and what the next session should NOT redo. Anything
that exists only in the final message is gone. **Give open threads a stopping rule** — the
condition under which the right answer is to stop looking — and write it down *before* the
data arrives, so it cannot be revised to fit.

## Quality bar

- Every count came from a command run this turn, not from recall.
- Mistakes grouped by cause; each mapped to a constraint (new, incremented, or Minor).
- Every proposed mechanism was grepped for first.
- Every new check break-tested through the tool; scanners also corpus-pinned.
- What worked is recorded, not just what failed.
- Open threads carry a stopping rule.

## Verification checklist

- [ ] `bash .claude/tools/debrief-check.sh` green (it runs `verify.sh` for you)
- [ ] CI confirmed by hand for HEAD — the one condition the check refuses to guess
- [ ] Session reconstructed from `git log` / memory-layer greps, not memory
- [ ] Constraints updated: `seen` counts incremented, Minor entries added, promotions done
- [ ] `skill-impact.md` updated: a class-targeting change shipped this session got a `pending` row (with a holds-when); any prior `pending` intervention observed this session was flipped to `holding`/`recurred`
- [ ] Any project-changing decision this session settled is logged in `decisions.md` (what won, what over, why) — `debrief-check.sh` prints an advisory `decision` note when the session changed decision-shaped surfaces (CLAUDE.md, skills, agents, hooks, evals, deploy, design/roadmap docs) but logged no entry dated today
- [ ] Graduation notes of any re-fired constraint re-read against the new occurrence
- [ ] Mechanisms grepped for before being proposed
- [ ] New checks break-tested RED then GREEN; scanners have `gate_corpus` cases
- [ ] (Routines retired 2026-08-22 — nothing to mirror)
- [ ] Everything merged to `main`; CI polled, not assumed
- [ ] `bash .claude/tools/debrief-check.sh --record` run, and the ledger row given a note

## Common mistakes

- **Writing the debrief from memory.** It compresses toward the flattering version, and
  every number in it will be a guess presented as a fact.
- **Listing mistakes chronologically.** Four instances of one cause read as four unrelated
  slips, and none of them graduates.
- **Minting a constraint per mistake.** 22 constraints where 8 sit at `seen: 1` and never
  recur is fine; 22 where each describes the same thing differently is a diary.
- **Proposing a mechanism that already exists** (C22) — the single most likely mistake
  *during* a debrief, because you are reasoning about the machinery rather than reading it.
- **Skipping the debrief because the session went well.** The near-misses are the cheapest
  lessons available and the first to be forgotten.
- **Leaving the analysis in chat.** If it is not in `.claude/memory/` or a committed file,
  it did not happen.

## What to report back

The commits, the constraint changes (which incremented, which minted, which retired), the
mechanisms built and their break-test results, what is open with its stopping rule, and
what is scheduled. Lead with the mistakes and what now prevents them — not with the
shipped list, which git already has.
