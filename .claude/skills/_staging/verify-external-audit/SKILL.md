---
name: verify-external-audit
description: Verify-then-fix protocol for claims from external sources — LLM audits, code reviews, security scanners, or a pasted list of "bugs found". Load whenever a batch of claimed defects arrives from outside this session, BEFORE fixing any of them.
---

# Verify an external audit

History: the 2026-07-10 external LLM audit made 15 claims; only 10 were true, and
one false positive was labeled "critical" (an import crash that didn't exist).
Every claim gets a verdict with line evidence before any fix.

## When NOT to use

- Findings YOU generated this session by reading the code — you already have the
  evidence; fix via `ship-bot-release`.
- A single user-observed bug with a symptom — that's `debug-fleet-incident`.
- CI/eval failures — those checks are already verified-by-construction; just fix.

## Procedure

1. **Check the rejected-claims registries first.** Two files exist specifically so
   rejected ideas don't come back:
   - `telegram-companion-bot/AUDIT-2026-07-10.md` § "Deepseek claims rejected after verification"
   - `telegram-companion-bot/ROADMAP.md` § "Rejected or already covered"
   Any incoming claim matching an entry is closed with a citation, zero code read.

2. **Triage each remaining claim to a verdict**, reading the actual code at the
   claimed location (Grep/Read; claims often cite wrong line numbers — search for
   the pattern, not the line):
   - **CONFIRMED** — reproduced in code with file:line evidence; state the
     failure scenario in one sentence.
   - **FALSE** — code shows otherwise; quote the disproving lines.
   - **ALREADY FIXED** — check `CHANGELOG.md`; cite the version.
   - **REAL BUT REJECTED** — true observation, but fixing it violates a recorded
     decision (single-file bot.py, no side calls, DRY_RUN rejection…); cite it.
   - **UNVERIFIABLE HERE** — needs on-device behavior; say what evidence would
     settle it and how to get it (`/errors`, log line, `--claim-test`).

3. **Record verdicts before fixing.** For a sizable audit, append a dated verdict
   section to `AUDIT-2026-07-10.md`'s pattern (or a new `AUDIT-<date>.md`), so the
   next audit's duplicates die in step 1. Small batches: verdicts in the session
   report are enough.

4. **Fix only CONFIRMED claims**, via `ship-bot-release` (one release; audit fixes
   are a coherent theme). Order by user impact, not by the auditor's severity
   labels — external severity was wrong before.

5. If a CONFIRMED claim reveals a failure class that has now bitten twice →
   `add-regression-eval`.

## Quality bar

- Zero fixes to unverified claims — including "harmless" ones; an unnecessary
  diff to bot.py is fleet risk for nothing.
- Every verdict carries evidence a skeptic could check: file:line + quoted code,
  or a changelog/registry citation.

## Verification checklist

- [ ] Both rejected-claims registries consulted
- [ ] Every claim has exactly one verdict with evidence
- [ ] No code changed for FALSE / ALREADY FIXED / REJECTED / UNVERIFIABLE claims
- [ ] CONFIRMED fixes went through the full ship-bot-release gate
- [ ] Verdicts recorded somewhere durable if the batch was sizable

## Common mistakes

- Fixing down the list in order because each item "sounds plausible" — the 33%
  false-positive rate is the base rate to assume.
- Trusting the claim's line numbers after the file has drifted — grep for the
  construct.
- Re-implementing rejected ideas (a `/rollback` command, DRY_RUN, splitting
  bot.py) because the auditor independently reinvented them.
- Letting an auditor's "critical" label stampede a same-day fleet deploy without
  verification — the last "critical" was fictional.

## What to report back

A verdict table (claim → verdict → evidence), what was fixed and shipped, what was
rejected and why, and any new eval created.
