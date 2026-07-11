# Raw capture: ROADMAP.md + AUDIT-2026-07-10.md

Sources: `telegram-companion-bot/ROADMAP.md`, `telegram-companion-bot/AUDIT-2026-07-10.md`
@ commit `d76dcdf`.

Tracks: 1 reliability/platform (1.2 VPS migration Phase 2 is the open L-size item),
2 engineering workflow (all shipped), 3 character/product features (all shipped),
4 audit backlog & memory integrity (specced in IMPROVEMENTS_PLAN.md; shipped as
R1–R6 per git log, roadmap not yet updated — drift).

Rejected-ideas registry (ROADMAP §"Rejected or already covered", verbatim gist):
- `/rollback` command — bak + shell covers it; a bad bot.py can't run its own rollback.
- Group ledger pruning / bot liveness heartbeats — rotation exists; liveness adds
  machinery the claim-file design deliberately avoids.
- "Unit tests, DRY_RUN" — suite exists; DRY_RUN adds a second untested code path to
  every send site.
- Self-evolution ideas — product direction, revisit deliberately (later shipped
  deliberately as R6, gated).

AUDIT-2026-07-10.md: external Deepseek audit made 15 claims; 10 confirmed, 5
rejected after line-evidence verification — including a "critical" import crash
that did not exist. Rejected claims are recorded in the audit file so they don't
come back.
