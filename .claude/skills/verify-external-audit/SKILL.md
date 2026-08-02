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
  evidence; fix via `repo-change-control`.
- A single user-observed bug with a symptom — that's `repo-debugging-playbook`.
- CI/eval failures — those checks are already verified-by-construction; just fix.

## Procedure

1. **Check the rejected-claims registries first.** Two files exist specifically so
   rejected ideas don't come back:
   - `telegram-companion-bot/AUDIT-2026-07-10.md` § "Deepseek claims rejected after verification"
   - `telegram-companion-bot/ROADMAP.md` § "Rejected or already covered"
   Any incoming claim matching an entry is closed with a citation, zero code read.

2. **Triage each remaining claim to a verdict AND a disposition** — two independent
   fields, not one label. Read the actual code at the claimed location (Grep/Read;
   claims often cite wrong line numbers — search for the pattern, not the line).

   **Verdict — is the claim true?**
   - **CONFIRMED** — reproduced in code with file:line evidence; state the failure
     scenario in one sentence.
   - **FALSE_POSITIVE** — code shows otherwise; quote the disproving lines.
   - **STALE** — was true when written, fixed since; check `CHANGELOG.md`, cite the
     version.
   - **NOT_REPRODUCED** — can't settle it with the evidence available here (needs
     on-device behavior); say what evidence would settle it and how to get it
     (`/errors`, log line, `--claim-test`).
   - **NOT_APPLICABLE** — describes a system we don't run (a framework we don't use,
     a deploy path that isn't ours).

   **Disposition — what did we do?**
   - **FIXED** — shipped, cite the version.
   - **NO_ACTION** — closed deliberately.
   - **OPEN** — true and unfixed; belongs in ROADMAP or an operational-log Next.

   **Why the split (adopted 2026-07-27, from the Shared Session Memory Protocol
   review).** The old vocabulary had a single label `REAL BUT REJECTED`, which welded
   a truth-claim to a policy decision. Once written it was impossible to ask the two
   questions separately — so when a recorded decision was later revisited (as the
   default-off convention was on 2026-07-18), nothing could answer "which past
   findings were *true* but closed under the old rule?" That is exactly how the
   memory-hygiene loops stayed off for two weeks (v2026-07-27.1). `REAL BUT REJECTED`
   is now **CONFIRMED + NO_ACTION**, and it stays queryable.

   The combination that most needs writing down is **CONFIRMED + NO_ACTION** — record
   *which* recorded decision closed it (single-file bot.py, no side calls, DRY_RUN
   rejection…), because that decision may not outlive the finding.

3. **Record verdicts before fixing.** For a sizable audit, append a dated verdict
   section to `AUDIT-2026-07-10.md`'s pattern (or a new `AUDIT-<date>.md`), so the
   next audit's duplicates die in step 1. Small batches: verdicts in the session
   report are enough. Record both fields — a table of claim → verdict → disposition →
   evidence. A verdict with no disposition is half a record.

4. **Before fixing a batch, classify each CONFIRMED claim INDEPENDENT or COUPLED** —
   does it touch the same function or lines as another? Coupled ones must be worked in
   sequence by one worker; independent ones can be split across `coder` subagents with a
   strict scope contract (fix only your finding, add one test that fails before and
   passes after, touch nothing else). Two reasons this is worth the minute it takes: a
   fix for finding 3 silently reverting finding 1 is the failure it prevents, and the
   classification is what tells you whether parallelism is even available. On 2026-08-02
   six findings all landed in bot.py and four were coupled through the same feature
   table, so the batch was correctly worked inline — the answer is often "sequential",
   and knowing that is the point.

5. **Fix only CONFIRMED claims**, via `repo-change-control` (one release; audit fixes
   are a coherent theme). Order by user impact, not by the auditor's severity
   labels — external severity was wrong before.

6. If a CONFIRMED claim reveals a failure class that has now bitten twice →
   `add-regression-eval`.

## Quality bar

- Zero fixes to unverified claims — including "harmless" ones; an unnecessary
  diff to bot.py is fleet risk for nothing.
- Every verdict carries evidence a skeptic could check: file:line + quoted code,
  or a changelog/registry citation.

## Verification checklist

- [ ] Both rejected-claims registries consulted
- [ ] Every claim has exactly one verdict AND one disposition, with evidence
- [ ] Every CONFIRMED + NO_ACTION cites the decision that closed it
- [ ] No code changed for FALSE_POSITIVE / STALE / NOT_REPRODUCED / NOT_APPLICABLE
      claims, or for CONFIRMED ones dispositioned NO_ACTION
- [ ] CONFIRMED fixes went through the full repo-change-control gate
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

A verdict table (claim → verdict → disposition → evidence), what was fixed and
shipped, what was closed and under which decision, and any new eval created.
