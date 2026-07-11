# Incident-pinned evals

**Idea:** every automated check exists because something real went wrong; the
check's job is to make that exact class of mistake impossible to silently repeat.
The changelog remembers *why*; the eval enforces the *what*.

- Realized as: 14 checks in `.claude/evals/run-evals.sh`, each with a comment
  naming its incident, run per-session and in CI on every push
  ([raw/2026-07-11-run-evals.md]).
- Admission bar: a failure class earns an eval when it recurs (twice), not on
  first occurrence — keeps the suite meaningful
  ([raw/2026-07-11-claude-md.md]).
- Quality bar: a new eval must be break-tested (seen red on the injected old bug,
  then green) — after committing real work, because a `git checkout` revert of an
  injection once destroyed 700 uncommitted lines
  ([raw/2026-07-11-operational-log.md]).
