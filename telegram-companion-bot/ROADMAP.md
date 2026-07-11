# Roadmap — telegram-companion-bot

Written 2026-07-06 from a code survey of bot.py v2026-07-05.12 (7,626 lines), the
changelog, and CLAUDE.md. Each item names its evidence — why it's on the list — plus
effort (S/M/L), risk, and what "done" means. Ordered by track, sequenced at the bottom.

**Deliberate non-goal, recorded to prevent future refactor urges:** bot.py stays a
single file. The entire deploy model (`/update` swapping one shared file, update-all.sh
curling one URL, `bot.py.bak` rollback) depends on it. The monolith's real cost —
regressions in pure logic — is covered by Track 2.1 instead.

---

## Track 1 — Reliability & platform

The phone is the existential risk (phantom process killer, OEM battery managers,
Python-bump venv breaks — all documented in CLAUDE.md). Everything here reduces
single-device blast radius.

### ✅ 1.1 watchdog.sh (v2026-07-06.3), 1.3 fleet-status (v2026-07-06.3), 1.4 alerts (v2026-07-06.3)

### 1.2 VPS migration Phase 2 — actually move the fleet — L
- **Status:** Migration runbook written (`deploy/MIGRATION.md`). Pilot with jules is
  next — requires a VPS to be provisioned and `install-vps.sh` run once.
- **Plan:**
  1. Pilot with one low-state bot (jules). Cutover is per-bot and brief: stop the
     instance on the phone → restore its directory from the latest backup-all.sh
     archive onto the VPS → `systemctl start bot@jules`. Only one process may poll a
     bot token, so stop-then-start, never parallel.
  2. Set `HEALTHCHECK_URL` per migrated instance (dead man's switch already built).
  3. `ADMIN_API_ENABLED=1`, bound to the Tailscale IP (Phase 1 auth model, never 0.0.0.0).
  4. Soak the pilot for a week (watch `/audit` error counts vs its phone baseline),
     then migrate the rest one at a time. Phone keeps nora last — she's the shared-venv
     home instance; retire the phone (or keep it as a spare) when she moves.
- **Risk:** state divergence if a bot runs on both hosts — the stop-before-start rule
  is the whole safety story. Timezone: verify tzdata + TIMEZONE on the VPS before the
  first start (the v2026-07-05.5 startup-crash class).
- **Done when:** all six instances on systemd, healthchecks green for 14 days,
  OPS_MANUAL has a "VPS operations" section, and the Termux quirks in CLAUDE.md are
  marked historical.

---

## Track 2 — Engineering workflow ✅ Complete

2.1 test suite (v2026-07-06.4), 2.2 new-bot.sh (v2026-07-06.4), 2.3 sync-cards.sh (v2026-07-06.3).

---

## Track 3 — Character & product features ✅ Complete

3.1 voice symmetry (v2026-07-06.3), 3.2 shared world (v2026-07-06.4), 3.3 semantic
recall (v2026-07-06.5), 3.4 group chat (v2026-07-10.1).

---

## Track 4 — Audit backlog & memory integrity (from AUDIT-2026-07-10.md)

The 2026-07-10 audit (external Deepseek pass + verification + two user-observed bugs)
shipped its confirmed fixes as v2026-07-10.2. What remains, triaged below — and specced
in full, release-by-release, in **`IMPROVEMENTS_PLAN.md`** (self-contained handoff for
whichever agent implements it):

### ✅ 4.1 Memory auditor (v2026-07-11.1) — see CHANGELOG + IMPROVEMENTS_PLAN R1

### ✅ 4.2 Availability awareness (v2026-07-11.2) — see CHANGELOG + IMPROVEMENTS_PLAN R2

### 4.3 Robustness leftovers — S each
- Atomic writes (tmp+replace) for jokes.json / reminders.json / cron_jobs.json —
  a process death mid-write can truncate them today.
- Prune `_last_request` (rate-limit dict grows unbounded; trivial but unclean).
- Central `validate_config()` startup summary (bad values already fall back with
  warnings since v2026-07-10.2; this would surface them all in one place + /audit).

### Rejected or already covered (recorded so they don't come back)
- `/rollback` command — `bot.py.bak` + shell already covers it; a bad bot.py can't be
  trusted to run its own rollback anyway.
- Group ledger pruning / bot liveness heartbeats — rotation already exists; liveness
  adds machinery the claim-file design deliberately avoids (a down bot just loses
  claims).
- "Unit tests, DRY_RUN" — test suite exists (95 tests); DRY_RUN adds a second untested
  code path to every send site for little value on a 1-user fleet.
- Self-evolution ideas (closeness score, auto inside-jokes, live self-image updates)
  — product direction, not audit debt; revisit deliberately, not as a checklist.

---

## Sequencing

| Phase | Items | Status |
|---|---|---|
| **Now** | 1.2 VPS Phase 2 — pilot jules | Runbook written (`deploy/MIGRATION.md`). Needs a provisioned VPS to execute. |
| **Next** | 4.3 robustness leftovers (atomic writes, `_last_request` prune, config warnings) | From AUDIT-2026-07-10.md; specced in IMPROVEMENTS_PLAN R3 |

Execution maps onto the agent system: builder implements one item per dispatch,
qa-engineer verifies against each item's "done when", research-scout owns the 3.3 gate,
adversarial-critic reviews the 3.4 design doc, and every bot.py-touching item ships
with the usual BOT_VERSION bump + changelog entry (the delivery gate enforces it).
