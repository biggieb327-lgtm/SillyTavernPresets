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

### 3.4 ~~Group chat / bot-to-bot~~ ✅ (shipped v2026-07-10.1)
- Design doc (`GROUP_CHAT_DESIGN.md`) survived four adversarial-critic review rounds,
  then the prototype shipped behind `GROUP_MODE=1` for the Priya + Jules pilot.
  Shared flock'd ledger + atomic claim files (Telegram never delivers bot messages to
  bots); chain cap 2; fleet-wide fail-closed group posture; two CI evals pin the
  group/private memory boundary. On-device rollout steps in OPS_MANUAL.

### 3.5 TomTom Maps — S
- **Phase 1 ✅ (shipped v2026-07-11.7):** slash commands `/route`, `/nearby`, `/place`
  behind `TOMTOM_API_KEY` (fail-closed); per-instance `TOMTOM_TRAVEL_MODE`. Raw
  `api.tomtom.com` REST, defensive parsers, 20 tests. Owner provisions the key.
- **`/food` ✅ (shipped v2026-07-11.13):** GPS-based nearby restaurant list
  (`/food [cuisine]`); "open now" held for a follow-up (tz-safe opening-hours parse).
- **In-character restaurant recs ✅ (shipped v2026-07-11.14, `FOOD_SUGGESTIONS`):**
  food-ish message + shared location → real nearby restaurants pre-fetched and
  injected into the single reply so the character recommends them in her own voice.
  No extra LLM call; default off. Proves the pre-fetch-and-inject pattern.
- **Phase 2 ✅ (shipped v2026-07-17.1, `MAP_INTENT`):** generalized map intent —
  route asks ("how do I get to X", "how far is X") and nearby asks ("is there a
  <thing> nearby") pre-fetch real TomTom data into the single reply via regex intent
  detection (`_map_intent`), honoring the budget rule (no per-message LLM side call).
  Deferred follow-ups (owner-settled 2026-07-17): "what's near <remote place>",
  memory-resolved "home"/"work" destinations, and a per-chat cooldown if the `[map]`
  log line ever shows over-firing.

### 3.6 ~~Schedule-driven unavailability~~ ✅ (shipped v2026-07-18.2, `SCHED_BUSY`)
- **Evidence:** `REVIEW-BRAINENGINE-2026-07-18.md` item A (owner-approved 2026-07-18).
  `schedule.txt` is injected into context every turn (`_read_schedule_today`) but
  nothing enforces it behaviorally — the character is always instantly available,
  never says she has to go, never replies slower mid-commitment. The always-on
  companion is the single biggest "puppet" tell.
- **Plan:** parse today's schedule section for time-ranged entries; when `now` falls
  inside a busy block, inject a system line (replying in stolen moments, shorter,
  may say she has to go and pick the thread up later) and optionally scale typing
  delay via the existing `send_bubbles` `pre_delay` plumbing. Env kill switch per
  owner policy 2026-07-18 (default on, `0` disables without redeploy). Zero extra
  LLM calls. Proactive sends unchanged — existing quiet-hours/nudge checks stay
  authoritative; this only adds restraint.
- **Risk:** low — prompt + arithmetic only. Main hazard is over-firing on loosely
  formatted schedule entries; parse conservatively (explicit `HH:MM-HH:MM` ranges
  only) and log a `[sched-busy]` line so over-firing is visible.
- **Done when:** a bot with a busy block active visibly changes register (and can
  exit a conversation), verified in a live exchange; no behavior change when the
  kill switch is set to `0` or schedule.txt has no timed entries.

### 3.7 ~~Fatigue accumulator + silence license + day-mood residue~~ ✅ (shipped v2026-07-18.3, `FATIGUE_STATE`/`DAY_MOOD_RESIDUE`)
- **Evidence:** `REVIEW-BRAINENGINE-2026-07-18.md` items B + C (owner-approved
  2026-07-18, bundled — they share the state plumbing and injection point). Mood
  tracks what she feels *about* things but nothing tracks remaining social capacity;
  and every message currently earns a full reply, another realism tell. Residue
  sub-item from `REVIEW-YURALUME-2026-07-18.md`: mood changes ONLY through
  conversation, so her generated day (`day.txt`) never colors how she opens.
- **Plan:** per-chat `fatigue` float 0–100 updated arithmetically where
  `post_reply_analysis` already lands valence (intense exchange +10–15, calm
  positive −15, else −5; decay with `_gap_hours`). No LLM call. Above a threshold,
  one system line ("socially drained — shorter replies, less patience"), plus a
  license for a bare "k"/reaction to be a complete reply when drained, busy (3.6),
  or low-mood. **Residue:** one extra JSON key (`opening_mood`: label + valence)
  on the existing midnight day-generation call, written into the normal mood state
  at rotation so her day seeds how she shows up — mood is presentation state, not
  a fact store, so the `[own-day]` provenance rule is untouched. Env kill switch
  per owner policy 2026-07-18 (default on, `0` disables without redeploy).
  Explicitly NOT adopting BrainEngine's "ego depletion" (dropping social
  regulation) — recorded rejection in the review.
- **Risk:** low — tuning risk only (fatigue that accumulates too fast reads as
  sulking). Start with conservative constants; log `[fatigue]` transitions.
- **Done when:** a long intense conversation produces a visible register shift that
  recovers after a gap; minimal replies occur but stay rare; a notable day.txt
  event visibly colors her first exchange after rotation; behavior with the
  kill switch set to `0` identical to today.

---

## Track 4 — Audit backlog & memory integrity (from AUDIT-2026-07-10.md)

The 2026-07-10 audit (external Deepseek pass + verification + two user-observed bugs)
shipped its confirmed fixes as v2026-07-10.2. What remains, triaged below — and specced
in full, release-by-release, in **`IMPROVEMENTS_PLAN.md`** (self-contained handoff for
whichever agent implements it):

### 4.1 ~~Memory auditor~~ ✅ (shipped as R1, v2026-07-11.1)
- Source-attached memories (`memory_meta.json`), quote grounding, confidence + review
  queue (`/reviewmem`), `/editmem` + `/sourcemem`, `[memcheck:]` correction flow,
  append-only memory audit log — per the IMPROVEMENTS_PLAN.md R1 spec. "Done when"
  met: a wrong memory is traceable and correctable from Telegram in under a minute.
  Follow-up memory-loop refinements shipped v2026-07-12.1–.2.

### 4.2 ~~Availability awareness~~ ✅ (shipped as R2, v2026-07-11.2)
- `/away` + `/back`, remote-default framing, auto-extraction via post-reply analysis
  (auto-away expires after `AWAY_AUTO_HOURS`), busy/working/driving vibe presets.

### 4.3 ~~Robustness leftovers~~ ✅ (shipped as R3, v2026-07-11.3)
- Atomic small-file writes (`_atomic_write_text`), `_last_request` pruning, config
  warnings surfaced in `/audit` (`_CONFIG_WARNINGS` — the useful core of the suggested
  `validate_config()`), persisted error counts, graceful drain, LLM usage counters.

*(R4 prompt hygiene, R5 UX, and R6 evolution experiments from the same plan shipped as
v2026-07-11.4–.6 — see IMPROVEMENTS_PLAN.md and CHANGELOG.md.)*

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
| ~~**Now**~~ | ~~1.1 watchdog→repo, 1.3 fleet-status, 2.3 card sync, 3.1 voice symmetry, 1.4 alerts~~ | ✅ All shipped (v2026-07-06.3) |
| ~~**Next**~~ | ~~2.1 test suite, 2.2 new-bot.sh, 3.2 shared world, 3.3 semantic recall~~ | ✅ All shipped (v2026-07-06.4–5) |
| ~~**Someday**~~ | ~~3.4 group chat~~ | ✅ Shipped (v2026-07-10.1) after 4-round design review |
| ~~**Next**~~ | ~~4.1 memory auditor, 4.3 robustness leftovers~~ | ✅ Shipped as R1/R3 (v2026-07-11.1, .3) |
| ~~**Someday**~~ | ~~4.2 availability awareness~~ | ✅ Shipped as R2 (v2026-07-11.2) |
| **Now** | 1.2 VPS Phase 2 — pilot jules | **Jules migrated to the VPS 2026-07-19** (Contabo, Ubuntu 24.04, systemd `bot@jules`, PID live); in 7-day soak. Pending: re-point `HEALTHCHECK_URL` to the VPS, remove the phone-side `~/jules-bot` after soak. Runbook updated with the stop-supervisor + whole-dir-tar fixes the pilot surfaced (see operational-log 2026-07-19). Remaining five bots next, same procedure. |
| ~~**Next**~~ | ~~3.5 TomTom Phase 2 — generalized map intent~~ | ✅ Shipped (v2026-07-17.1, `MAP_INTENT`) |
| ~~**Next**~~ | ~~3.6 schedule-driven unavailability, then 3.7 fatigue + silence license + day-mood residue~~ | ✅ Shipped (v2026-07-18.2, .3) same day as the reviews that sourced them |

Execution maps onto the agent system: builder implements one item per dispatch,
qa-engineer verifies against each item's "done when", research-scout owns the 3.3 gate,
adversarial-critic reviews the 3.4 design doc, and every bot.py-touching item ships
with the usual BOT_VERSION bump + changelog entry (the delivery gate enforces it).
