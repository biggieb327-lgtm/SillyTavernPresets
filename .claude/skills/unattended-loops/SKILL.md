---
name: unattended-loops
description: Designing unattended multi-iteration work — an overnight session, a Routine, a /loop, or any run where nobody is around to answer questions. Load BEFORE writing the prompt or kicking off the run. Covers deciding whether a loop is warranted at all, resolving stall-points up front, and the durable-state file contract.
---

# Unattended loops

Three rules for work that iterates without a human present. (Concepts adapted
from pro-vi/loopgen — that repo has no license, so nothing is copied; these are
the ideas rewritten for this repo at native size.)

## Rule 1 — Prove the loop is necessary before scaffolding it

A loop earns its machinery only when you do NOT expect first-attempt success —
when the route to done is discovered through attempt → fail → revise cycles
(flaky hunt, "until the suite passes" over many tries, open-ended hardening).

If the path is known and a terminal verifier gates completion, it is a
one-shot task wearing loop clothes — an IMPROVEMENTS_PLAN release is exactly
this. Do it directly under `repo-change-control`; no loop artifacts, no
schedule. When genuinely unsure, ask the owner: loop or one-shot.

## Rule 2 — Frontload every decision the run could stall on

An unattended run must never block on a question. Before kickoff, resolve and
write into the loop prompt:

- **Exact verification commands** (for bot work: `py_compile`, pytest,
  `bash .claude/evals/run-evals.sh` from repo root) and what "done" means.
- **Scope boundary** — which files/dirs are in play; everything else untouched.
- **The irreversible list** — actions the loop must NOT take alone (deploys to
  the fleet, deleting data, pushing to main with red checks, anything touching
  secrets or paid budgets). On hitting one: halt and write the question into
  STATE.md for the owner — never guess, never block waiting.
- **Everything else** gets a default now: smallest reversible choice, recorded
  as an assumption (working principle #1), reviewable in the journal later.

Anything you can't resolve or default is a named gap — surface it to the owner
before kickoff, not at 3am.

## Rule 3 — Split live state from history, in files

Context gets compacted and containers get recycled; conversation memory is not
state. Each loop keeps two files under `.claude/.runtime/loops/<loop-name>/`
(gitignored, per the `.runtime` convention):

- **STATE.md** — live status only, rewritten in place, ≤ ~30 lines, fixed
  keys: `iteration`, `current_item`, `last_action`, `next_action`,
  `halt_cause`, `assumptions`. Never append; a key that grows every iteration
  is history in disguise and belongs in the journal.
- **JOURNAL.md** — append-only, one dated line per attempt: what was tried,
  verdict, evidence pointer (commit hash, eval output line). Never edited.

The loop prompt must be re-entrant: iteration 1 setup is gated on "STATE.md
absent", so re-sending the same prompt (which Routines and /loop do) never
re-runs bootstrap. Durable conclusions graduate OUT of the loop dir — into
commits, the changelog, or the operational log; if the loop must survive this
ephemeral container, commit its state files to the working branch instead of
using `.runtime`, and delete them when the loop ends.

## Common mistakes

- Scaffolding a loop for a spec'd task with clear acceptance criteria (Rule 1
  exists because this is the most tempting misuse).
- A kickoff prompt with first-iteration instructions baked in ("start by…") —
  it misfires on iteration 2. All sequencing lives behind the STATE.md gate.
- Treating quiet hours, nudge budgets, or the delivery gate as suspended
  because nobody's watching — hooks and invariants bind every iteration.

## What to report back

Loop-or-one-shot verdict with reasoning; the frontload list (resolved /
defaulted / gaps); where the state files live; and the kickoff prompt.
