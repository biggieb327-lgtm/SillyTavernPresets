# Evals — recurring failures, pinned

Every check in `run-evals.sh` exists because something actually went wrong in this
project, usually expensively. This is the enforcement layer behind
`telegram-companion-bot/CHANGELOG.md`: the changelog remembers *why*, the eval makes
sure the *what* can't silently come back.

Run before claiming any change done (the `repo-validation-gate` skill and the
delivery-gate hook both expect it):

```bash
bash .claude/evals/run-evals.sh
```

## Adding an eval

The rule: **the same class of mistake happening twice earns a permanent eval.** Don't
write a memory note and hope — memory notes don't run; evals do.

1. Get the real root cause first (check the changelog; an eval built on a symptom pins
   the wrong thing). Dispatch `eval-designer` for this.
2. Add a check to `run-evals.sh` following the existing pattern: a cheap, deterministic
   assertion with a comment naming the incident it guards.
3. Prove both directions: it PASSES on the current tree, and it FAILS if you
   temporarily reintroduce the bug (then restore).

Keep checks fast (< 1s each) and dependency-free (bash + python3 only) — they run on
every delivery.
