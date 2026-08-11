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

Append with: `bash .claude/tools/debrief-check.sh --record`

| date | head | commits since previous | notes |
|---|---|---|---|
| 2026-08-11 | d3fa2b1 | 28 (first row — counted from 3ecd5db, the session's starting point) | first run of the skill, on the session that produced it; C23 minted, C22 → 7, 4 Minor entries retired |
