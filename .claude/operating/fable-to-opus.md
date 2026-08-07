# Handoff: Fable 5 → Opus 4.8

Written 2026-07-11 by the outgoing session that built the staged skill library and
the operating manual. This file is what that session knew that the repo's other
docs don't say. Read order for your first session here: `CLAUDE.md` (Operating
rule) → `.claude/OPERATING_MANUAL.md` → the skill the router points you at.

**Numbers below (BOT_VERSION, test/eval counts) are a snapshot at 2026-07-11
handoff time, not live state** — check `bot.py` and `CHANGELOG.md` for current
figures. The decisions and traps below still hold; only the counts have aged.

## Decisions made with the owner's explicit authority (2026-07-11)

These were asked and answered — don't re-ask, don't re-litigate:

1. **Merge policy:** merge `claude/...` work to `main` autonomously when
   py_compile + pytest + run-evals.sh are ALL green. Any red = stop and report.
   Encoded in `repo-change-control` step 7.
2. **Root presets** (`TheAtelier*.json`, `UnifiedWritersRoom_*.json`,
   `caa16137-nora.json`, …) are LIVE files the owner still edits — not frozen
   archives. Covered by `edit-cards-and-presets`.
3. **voicekit-starter/ is in scope** — separate project, own rules
   (`voicekit-work` skill).
4. **Next major work is VPS migration** (ROADMAP 1.2, runbook
   `telegram-companion-bot/deploy/MIGRATION.md`, guardrails in `vps-migration`).

## State you inherit

- Skill library is in `.claude/skills/_staging/` — **staged, not live**. The owner
  has not yet reviewed it for promotion. Promotion procedure and router rows:
  `_staging/README.md`. Do not promote on your own initiative.
- Skill names were chosen by the owner: `repo-debugging-playbook`,
  `repo-change-control`, `repo-validation-gate` (this one is live and preloaded).
  `bot-code-invariants` is the companion checklist `repo-change-control` loads.
- Baseline at handoff (2026-07-11): `main` at `253c7bd`, BOT_VERSION `2026-07-11.6`,
  162 pytest tests, 14 evals, CI green. R1–R6 from `IMPROVEMENTS_PLAN.md` are all
  shipped.
- Current state (refreshed 2026-08-03, three weeks and dozens of releases later —
  re-verify rather than trusting this line too): `origin/main` at `e96443d`,
  BOT_VERSION `2026-08-02.15`, 36 evals (35 pass + 1 environment-only skip, this
  sandbox is missing Pillow — see `.claude/evals/run-evals.sh` output), ~902
  `test_*` functions in `telegram-companion-bot/tests/test_pure.py` (grep count;
  `pytest` isn't installed in this sandbox to collect it directly). **Local `main`
  can be a stale, unrelated ref with no merge-base against `origin/main`** (hit
  2026-07-29 and again while writing this line, 2026-08-03) — always check
  `origin/main`, never local `main`.
- Known doc drift I did NOT fix (deliberately — not asked): `ROADMAP.md` Track 4
  and `IMPROVEMENTS_PLAN.md` still show R1–R6 as pending. First bot.py session
  should mark them done per `repo-change-control` step 8.

## Traps verified this session (each cost real time; don't rediscover them)

- Fresh remote container: `pip install -r telegram-companion-bot/requirements.txt
  pytest` or the `bot-imports` eval fails on missing Pillow. Then, if pytest dies
  at collection with `pyo3_runtime.PanicException`, `pip install --upgrade
  cryptography` (broken Debian system package). Neither is a code bug.
- Container Python is 3.11; phone and CI are 3.13. Local green is evidence; CI on
  main is authority.
- `run-evals.sh` must be run from the repo root; from a subdirectory the relative
  path fails and — this bit me — a `&&` chain can swallow the failure and commit
  anyway. Run it as its own command and look at the last line.
- `nora.json` and `caa16137-nora.json` have genuinely diverged (14 data keys).
  Not an error to fix; they serve different frontends. Ask before syncing.

## Judgment calls you'll have to keep making

- The delivery gate, risk guard, and evals are the repo's memory of past pain.
  When one blocks you, the correct response is almost always to satisfy it, not to
  argue with it — and never to edit a check just to make it pass (`add-regression-
  eval` and `group-chat-changes` both spell out the one legitimate exception:
  widening an eval deliberately, in the same commit, with rationale).
- The owner values root-cause-first writing (changelog style) and honest
  uncertainty over polish. When a verification can't be run here (phone-only
  behavior), saying so plainly has always been received better than implying
  coverage.
- This repo's owner runs six emotionally-real companion characters. Content edits
  are not cosmetic — an off-register sentence in a card ships to a relationship
  someone actually has. `edit-cards-and-presets` carries the per-character rules;
  take them as seriously as the code invariants.

## What I would do first in your position

Nothing, until asked. The operating layer is built; the fleet is green; the next
work (VPS pilot, skill promotion) both need the owner's go. When it comes, the
skills above carry the procedures.
