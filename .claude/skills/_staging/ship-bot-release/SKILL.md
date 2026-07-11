---
name: ship-bot-release
description: End-to-end procedure for shipping any bot.py change (feature, bugfix, refactor). Load BEFORE editing bot.py whenever the change is meant to reach the fleet — i.e. almost every bot.py edit. Covers the read-first rules, versioning, changelog, verification, merge to main, and the deploy handoff.
---

# Ship a bot.py release

The fleet deploys by curling raw files from `main`. Merging to main = making it
deployable; the user then triggers the actual deploy from Telegram. Your job ends at
"merged, green, deploy instructions given" — you cannot run `/update` yourself.

## When NOT to use

- Card/seed/preset edits with no bot.py change → `edit-cards-and-presets`.
- Diagnosing a live problem (no fix known yet) → `debug-fleet-incident` first.
- Docs-only or `.claude/`-only changes: no BOT_VERSION bump, no changelog release
  entry (use a `## YYYY-MM-DD — ...` heading if the change deserves a changelog note
  at all). The delivery gate only fires when bot.py itself changed.

## Procedure

1. **Read before editing** (non-negotiable, in this order):
   - `telegram-companion-bot/CHANGELOG.md` — skim ALL headings, then fully read the
     entries touching the subsystems you'll change: if your planned change resembles
     a past incident, the entry usually contains the constraint that makes the naive
     fix wrong.
   - `telegram-companion-bot/AUDIT-2026-07-10.md` §"rejected" + ROADMAP §"Rejected or
     already covered" — do not re-implement rejected ideas.
   - If touching anything group-related → stop, load `group-chat-changes`.
   - Load `bot-code-invariants` and keep it open while writing the diff.

2. **Fresh-container setup** (once per session, before any test/eval run):
   ```bash
   pip install -r telegram-companion-bot/requirements.txt pytest
   pip install --upgrade cryptography   # if pytest panics with pyo3_runtime.PanicException
   ```
   Without these, the `bot-imports` eval fails on `ModuleNotFoundError: PIL` and
   pytest can die at collection inside Debian's system cryptography. Both are
   environment gaps, not code bugs. Do not "fix" bot.py for them.

3. **Implement.** Small diffs: one release = one theme (a mega-release risks all six
   bots at once). New/changed env vars get documented in `.env.example` with a safe
   default such that *unset = today's behavior* (the env flag is the kill switch).

4. **Tests.** Every new pure function gets pytest coverage in
   `telegram-companion-bot/tests/test_pure.py` (the `conftest.py` fixture stands up a
   fake instance so `import bot` works — reuse it, don't invent a new import path).

5. **Version + changelog** (the delivery-gate Stop hook blocks the turn otherwise):
   - Bump `BOT_VERSION` in bot.py (`grep -n '^BOT_VERSION' telegram-companion-bot/bot.py`),
     scheme `YYYY-MM-DD.N` — increment N for same-day releases.
   - Add a `## v<exact BOT_VERSION>` entry at the TOP of CHANGELOG.md, **root cause
     first, fix second**. The `version-changelog-sync` eval fails if the newest
     `## v` heading ≠ BOT_VERSION.

6. **Verify** — the standing block, all three, paste real output:
   ```bash
   python3 -m py_compile telegram-companion-bot/bot.py
   python -m pytest telegram-companion-bot/tests/ -q
   bash .claude/evals/run-evals.sh
   ```

7. **Commit on the session's `claude/...` branch, then merge to `main` and push.**
   Standing policy (owner-approved 2026-07-11): merge autonomously **only when step 6
   is fully green**. Any red check = stop, report, do not merge.
   ```bash
   git checkout main && git pull origin main && git merge <branch> && git push -u origin main
   ```
   Never force-push main (risk-guard blocks it; deploys would brick).

8. **Update planning docs in the same session**: mark the shipped item done in
   `ROADMAP.md` (this was skipped after R1–R6 and the docs drifted). If the release
   closed an operational-log "Next" item, note it there.

9. **Hand off the deploy.** Tell the user exactly:
   - `/update` to ONE bot → verify its `/audit` shows the new BOT_VERSION →
     `/restart` to the other five → `/audit` each.
   - If `run-bot.sh` changed, `/update` is NOT enough → point them at
     `deploy-and-verify-fleet`.

## Quality bar

- Diff does one thing; nothing unrelated reformatted or "improved".
- Zero new per-message LLM calls (extend `post_reply_analysis` JSON instead).
- Every invariant in `bot-code-invariants` checked against the final diff.
- Changelog entry explains the root cause well enough that a future session
  won't re-diagnose it from scratch.

## Verification checklist

- [ ] py_compile, pytest, run-evals.sh all green — actual output seen, not assumed
- [ ] BOT_VERSION bumped and equals the newest `## v` changelog heading
- [ ] New env vars in `.env.example`, unset = old behavior
- [ ] New pure functions have tests
- [ ] Merged to main and pushed; CI (`evals` workflow) green on main
- [ ] ROADMAP/plan docs updated
- [ ] Deploy instructions given to the user

## Common mistakes

- Fixing the environment's missing deps by editing bot.py (see step 2).
- Bumping BOT_VERSION but titling the changelog entry with a date heading (or vice
  versa) — the sync eval catches it late; get it right up front.
- Leaving work on the claude/ branch: the fleet deploys from main, so an unmerged
  green branch ships nothing.
- Proposing to split bot.py into modules. Recorded non-goal; the entire deploy
  model (`/update` swaps one file, `bot.py.bak` rollback) depends on a single file.
- Running `git checkout -- bot.py` to undo an experiment while the file holds
  uncommitted real work — this destroyed ~700 lines once. Commit real work first;
  revert experiments by re-editing.

## What to report back

Version shipped, one-line root cause, the three verification outputs (pasted),
merge commit on main, CI status, and the exact deploy commands the user should send
from Telegram.
