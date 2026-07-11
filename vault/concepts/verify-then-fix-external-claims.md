# Verify-then-fix for external claims

**Idea:** claims arriving from outside (LLM audits, reviews, scanners) get a
per-claim verdict with line evidence before any code changes; rejected claims are
recorded so they can't return as new work.

- Origin: a 15-claim external audit where only 10 claims were true and the sole
  "critical" was fictional ([raw/2026-07-11-roadmap-audit.md]).
- Realized as: verdicts recorded in AUDIT-2026-07-10.md; a standing
  rejected-ideas registry in ROADMAP.md (e.g. /rollback command, DRY_RUN) that
  gets checked before anything is re-implemented
  ([raw/2026-07-11-roadmap-audit.md]).
- Working rule: order confirmed fixes by user impact, not the auditor's severity
  labels — external severity has been wrong ([raw/2026-07-11-roadmap-audit.md]).
