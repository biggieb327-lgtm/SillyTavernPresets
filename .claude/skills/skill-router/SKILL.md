---
name: skill-router
description: Index of available skills and when to load each. Consult this instead of preloading everything — load skills on demand.
---

Load a skill only when its trigger fires. Preloaded always (do not re-load): `artifact-first-delivery`, `repo-validation-gate`.

| Trigger | Load |
|---|---|
| Stress-testing a plan or design before building | `grilling` (alias: `grill-me`) |
| Anything else | Check `ListSkills`/`SearchSkills` for harness-provided skills (code-review, verify, security-review, update-config, …) — prefer those over improvising |

Rules:
- One skill at a time; finish applying it before loading another.
- If a needed skill doesn't exist and the need has come up twice, that's a finding for `improvement-analyst` — a candidate for a new skill, written by `system-fixer`.
- New skills added under `.claude/skills/` must be registered in this table in the same change, or they're invisible tomorrow.
