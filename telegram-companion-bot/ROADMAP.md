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

### 1.1 ~~Commit watchdog.sh to the repo~~ ✅ (shipped v2026-07-06.3)
- Committed as `telegram-companion-bot/watchdog.sh` with curl-install instructions in
  its header, matching backup-all.sh's pattern. Covered by `shell-scripts-parse` eval.

### 1.2 VPS migration Phase 2 — actually move the fleet — L
- **Evidence:** Changelog v2026-07-05.12 is explicitly "Phase 1 of VPS migration":
  `deploy/bot@.service` (Restart=always) and `deploy/install-vps.sh` already exist and
  are confirmed compatible with the PID-lock/exit patterns. Phase 2 was never specced.
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

### 1.3 ~~Fleet status one-shot~~ ✅ (shipped v2026-07-06.3)
- Committed as `telegram-companion-bot/fleet-status.sh`. Hits `/admin/health` per
  instance, prints a six-row table. Works on-phone (localhost) or over tailnet.

### 1.4 ~~Degradation alerts (fallback rate + monthly spend)~~ ✅ (shipped v2026-07-06.3)
- `_self_audit` watches fallback rate (≥3/hr → DM) and optional `USAGE_BUDGET_MONTHLY`
  (DM at 80%/100%). Both use the existing 2h-cooldown DM pattern.

---

## Track 2 — Engineering workflow

### 2.1 ~~Committed unit tests for the pure logic~~ ✅ (shipped v2026-07-06.4)
- `tests/test_pure.py` (pytest): 41 tests covering `extract_tags`, cron parsing,
  `_extract_json`, `parse_when`, `_est_tokens`, `_count_error` cap. CI runs pytest
  after the eval suite.

### 2.2 ~~New-instance bootstrap~~ ✅ (shipped v2026-07-06.4)
- `new-bot.sh <name> <card.json>`: interactive bootstrap, creates dir, prompts for
  tokens/models, curls card + seeds, launches via run-bot.sh.

### 2.3 ~~Card/seed sync tooling~~ ✅ (shipped v2026-07-06.3)
- `sync-cards.sh`: for each instance, reads CHARACTER_CARD from .env, pulls card +
  seed directory from main. Supports `--dry-run`.

---

## Track 3 — Character & product features

### 3.1 ~~Voice conversational symmetry~~ ✅ (shipped v2026-07-06.3)
- `VOICE_REPLY_TO_VOICE` (default 0.9) replaces ambient `TTS_CHANCE` when the
  incoming message is a voice note. Text messages unaffected.

### 3.2 ~~Shared world context~~ ✅ (shipped v2026-07-06.4)
- `WORLD_GENERATOR=1` instance writes `world.txt` at midnight; every instance reads it
  during day generation. Degrades gracefully if absent.

### 3.3 ~~Semantic memory recall~~ ✅ (shipped v2026-07-06.5)
- NanoGPT embeddings (`text-embedding-3-small`). Embeds on write, cosine top-k on
  recall merged with keyword results. Falls back to keyword-only on API failure.

### 3.4 Group chat / bot-to-bot — L, experimental, deliberately last
- **Evidence:** none of the plumbing assumes groups (`_is_allowed` is per-user, memory
  is per-chat_id); this is the one genuinely new surface. It's also the fun one:
  two characters + you in one Telegram group.
- **Hard problems to solve on paper before any code:** turn-taking (bots must not
  answer every message, especially each other's), loop prevention (hard cap on
  consecutive bot-to-bot exchanges), cost (two models per conversational beat), and
  memory semantics (group memories vs the private relationship state).
- **Done when:** a design doc survives adversarial-critic review; only then a
  prototype behind `GROUP_MODE=1` on two instances.

---

## Sequencing

| Phase | Items | Status |
|---|---|---|
| ~~**Now**~~ | ~~1.1 watchdog→repo, 1.3 fleet-status, 2.3 card sync, 3.1 voice symmetry, 1.4 alerts~~ | ✅ All shipped (v2026-07-06.3) |
| ~~**Next**~~ | ~~2.1 test suite, 2.2 new-bot.sh, 3.2 shared world, 3.3 semantic recall~~ | ✅ All shipped (v2026-07-06.4–5) |
| **Now** | 1.2 VPS Phase 2 — pilot jules | Runbook written (`deploy/MIGRATION.md`). Needs a provisioned VPS to execute. |
| **Someday** | 3.4 group chat | Gated on a design review |

Execution maps onto the agent system: builder implements one item per dispatch,
qa-engineer verifies against each item's "done when", research-scout owns the 3.3 gate,
adversarial-critic reviews the 3.4 design doc, and every bot.py-touching item ships
with the usual BOT_VERSION bump + changelog entry (the delivery gate enforces it).
