# Debrief ledger

One row per `session-debrief` run. Exists because **the reach-rate cannot be measured from
inside a session**: `evidence-log.sh` writes to the gitignored `.claude/.runtime/`, and
session transcripts live in an ephemeral container — after a restart there is exactly one,
the current session. The repo is the only durable substrate, so the record has to live here
or not exist.

**What this measures:** commits of real work between recorded debriefs. That is a proxy for
"is a debrief overdue", surfaced by `session-audit.sh` at the start of the next session,
where it is actionable.

**What it deliberately does NOT measure:** whether the debrief was reached for unprompted
or asked for. That distinction matters and is exactly the thing a self-report cannot
establish — the agent whose reliability is in question is not a witness to it. The owner is
the only reliable observer of that, and this file does not pretend otherwise.

**No threshold yet.** One session is one data point, and picking a "debrief every N commits"
rule from it would be the estimate-as-fact trap this repo has already paid for twice.
`session-audit.sh` reports the number without judging it. Set a threshold once there are
enough rows to see a distribution.

## Why there is still only one row (2026-08-21)

The skill, `debrief-check.sh` and this ledger were all built on 2026-08-11, and the single
row below is that session recording itself. **170 commits of real work later, nothing had
run the skill again.** The tooling was never the problem — `debrief-check.sh` works and is
honest about what it cannot check. Nothing invoked it.

The only prompt was a `session-audit.sh` line saying "run `debrief-check.sh` when this
session reaches a stopping point": a request delivered at the **start** of a session about
something to do at the **end**, by which time it has scrolled away or been compacted out.
That hook's own comment argued SessionStart was the only actionable moment. One row in ten
days settles it — a reminder nobody acts on is not actionable, whatever the reasoning.

The ask now lives in **`.claude/hooks/debrief-nudge.sh`**, a Stop hook that fires once per
session when the tree is clean and the session committed something that day. It does not
judge whether the work deserves a debrief; `debrief-check.sh` still owns that and can
answer "not a stopping point yet". Deliberately no commit-count gate — that would be the
invented threshold this file has twice refused, and firing on every session that ships
something is also what produces the rows a real threshold would need.

**Read the next several rows as measuring the nudge, not the ritual.** If they cluster at
one row per working session, the mechanism works and a threshold becomes answerable. If
rows appear and say nothing worth keeping, the gate is too loose and should tighten.

Append with: `bash .claude/tools/debrief-check.sh --record`

| date | head | commits since previous | notes |
|---|---|---|---|
| 2026-08-11 | d3fa2b1 | 28 (first row — counted from 3ecd5db, the session's starting point) | first run of the skill, on the session that produced it; C23 minted, C22 → 7, 4 Minor entries retired |
| 2026-08-21 | 87f6b83 | 174 | **First run reached by `debrief-nudge.sh` rather than by asking** — the hook shipped this session and fired on its own first live stop. Found the session's biggest defect *during* the harvest, not before it: 12 of 15 evals reported PASS on a dead parser. C13 → 9, C14 → 5, 3 Minor entries, 5 evals added (41 → 46). |
| 2026-08-22 | 563ab65 | 13 | Artifact-only session (Fleet Graphs workflow diagrams). All 13 commits belong to the prior session that ran earlier today; this session produced 0 commits, 0 code changes. Nudge fired on per-day commit count, not per-session. No constraints to update, no incidents. verify.sh RED is missing PIL/pytest in container, not a regression. |
