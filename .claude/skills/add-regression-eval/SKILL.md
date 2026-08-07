---
name: add-regression-eval
description: Turning a failure into a permanent check in .claude/evals/run-evals.sh — including how to break-test the new eval WITHOUT destroying uncommitted work. Load when the same failure class has happened twice, when an operational-log row says a check is needed, or when the user asks to pin something.
---

# Add a regression eval

Every eval in `run-evals.sh` pins a real incident. The suite runs in every session
(self-verification) AND in CI on every push (`.github/workflows/evals.yml`), so a
new eval is fleet-level enforcement — and a badly written one either misfires (gets
deleted, guards nothing) or silently passes forever (worse than nothing).

## When NOT to use

- First occurrence of a failure — fix it, log it in the operational log, and wait.
  An eval per one-off bloats the suite; "recurred twice" is the bar.
- The rule is about *process*, not repo state (e.g. "ask before merging") — evals
  can only check files; process rules belong in hooks or skills.
- Pinning something a pytest test can express better (pure-function behavior) —
  put it in `tests/test_pure.py`; evals are for repo/config/structure invariants
  pytest can't reach.

## Procedure

1. **COMMIT ALL REAL WORK FIRST.** Break-testing means temporarily injecting the
   old bug to prove the eval catches it. Reverting that injection with
   `git checkout <file>` on a file carrying uncommitted work destroyed ~700 lines
   of bot.py once (operational-log 2026-07-10). The rule: commit first; revert
   injections by re-editing the line back, never by `git checkout`/`git restore`.

2. **For a PATTERN-matching check, write the inputs before the check.** A regex or
   parser check is not done when it passes; it is done when it fails on inputs built to
   slip past it. Write those first — the ones that SHOULD trip it and the ones that must
   NOT — then write the checker against them. On 2026-08-02 the reverse order shipped
   three guards with anchor bugs in one session, and a fourth that passed silently
   whenever the thing it called raised.
   - Fixtures and a runner live in `.claude/tools/gate_corpus/`; add cases there and the
     `gate-corpus` eval runs them in CI. Its README has the case format.
   - **Watch for a case that cannot fail.** Two of the first batch passed against the
     UNFIXED scanner because their fixtures produced the finding either way — C13 in
     corpus form. Run every new case against the current code and watch it go red before
     you fix anything.
   - The `adversarial-critic` agent is worth a pass here specifically: it did not write
     the checker, so it is not anchored to what the author meant it to match.

3. **Write the check** in `.claude/evals/run-evals.sh`, matching house style:
   - A comment naming the incident it pins (date/version + one-line story).
   - `ok "name: what passed"` / `bad "name" "what broke and what it costs"` —
     the failure message must tell a future session what to DO, not just what
     failed.
   - Prefer class-level checks over instance lists (the group-chat evals check
     "no DM side effects in `_group_deliver`'s body", not a hand-kept list of
     lines — hand-kept lists go stale; two adversarial rounds proved it).
   - Keep it fast and dependency-light: CI gives the whole suite 5 minutes, and
     the suite must run on a bare container *plus* pip-installed requirements.

4. **Break-test it:**
   ```bash
   bash .claude/evals/run-evals.sh          # green baseline
   # inject the old bug with a minimal edit
   bash .claude/evals/run-evals.sh          # MUST go red on your new check
   # revert the injection by re-editing (NOT git checkout)
   bash .claude/evals/run-evals.sh          # green again
   git diff                                  # MUST be exactly your eval addition
   ```

5. **Document:** add the eval's name to the relevant operational-log row's "Eval"
   column, and if it enforces a rule stated in CLAUDE.md or a design doc, note
   there that it's now eval-pinned.

6. **Ship:** commit, merge to main (CI now enforces it on every future push).

## Quality bar

- Fails loudly on the exact historical bug (proven by the break-test, not argued).
- Cannot false-positive on legitimate work you can foresee (e.g. anchor patterns
  precisely; exclude the eval file itself from greps like the secret-scan does).
- Failure message names the incident and the remedy.

## Verification checklist

- [ ] Real work committed BEFORE any injection
- [ ] Red-green cycle observed and output pasted (green → red on injection → green)
- [ ] `git diff` after revert shows only the eval change
- [ ] `bash -n .claude/evals/run-evals.sh` passes (the suite checks itself, but check first)
- [ ] Suite still completes fast enough for CI's 5-minute budget
- [ ] Operational log's Eval column updated

## Common mistakes

- Skipping the break-test — an eval that has never been seen red proves nothing.
- `git checkout` to undo the injection (see step 1; this is the #1 hazard).
- Greps that match their own eval file or docs quoting the bad pattern —
  scope with pathspecs like `':!.claude/evals/run-evals.sh'`.
- Writing an eval for something that happened once and will never recur.
- Failure messages like "check failed" — the message itself must carry the
  incident and the fix direction (the reader won't have this context).

## What to report back

The incident being pinned, the check's logic, the pasted red-green break-test
output, and confirmation the operational log was updated.
