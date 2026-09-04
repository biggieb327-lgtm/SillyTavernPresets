# Apply Sprint 1 remaining code/docs

This directory holds the machine-applied remainder of `feat/sprint1-proactive-quality`.

1. Apply `sprint1-proactive-receipts.bot.py.patch` to `telegram-companion-bot/bot.py` with `patch -p1` from repo root (or equivalent).
2. Prepend `sprint1-CHANGELOG.entry.md` to `telegram-companion-bot/CHANGELOG.md` (before the existing `## v2026-09-04.1` heading).
3. In `telegram-companion-bot/ROADMAP.md`:
   - Rename `## Track 5 — Proposed (lateral-thinking session, 2026-08-04, owner triage pending)` to `## Track 5-A — …` and add a short naming callout that this is 5-A vs 5-B below.
   - Rename `## Track 5 — Lateral-thinking exploratory ideas (sourced 2026-08-05)` to `## Track 5-B — …` with a matching callout.
   - Update section 5.11 to mark skip-reason on `/nudges` shipped (v2026-09-01.2; receipts in v2026-09-04.2).
4. In `telegram-companion-bot/.env.example`, above `PROACTIVE_TRIAGE`, document `PROACTIVE_RECEIPTS` (default on, observability only, path `proactive-receipts.jsonl`).
5. Delete this `patches/` directory after applying (do not leave apply scaffolding on the branch).
