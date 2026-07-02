---
name: companion-bot-architecture-contract
description: >
  The architecture contract for telegram-companion-bot (bot.py + bot_app/). Load this whenever
  you are designing or adding ANY feature, refactoring or moving code, or asking "where does this
  change belong?", "what depends on this?", "why is it built this way?", "can I split bot.py?",
  "should this go in bot_app?", "what must this not break?". Covers the single-file entry-point
  rule, the strangler-fig migration status, shared-code vs per-instance-state split, the
  assemble_messages prompt-layering order, every proactive-messaging path and its gates, the
  memory-layer inventory, trust boundaries, the external-services map, the supervision chain,
  and the pre-merge invariants checklist. Do NOT use for: operating/deploying the device
  (companion-bot-device-ops), debugging a live symptom (companion-bot-debugging-playbook),
  env-var/config specifics (companion-bot-config-catalog), or commit/deploy rules
  (companion-bot-change-control).
---

# Companion-bot architecture contract

Verified against the code on **2026-07-02**. Line numbers are approximate ("~") — re-grep the
named function before relying on an exact position.

**The system in one paragraph:** ONE ~8,900-line file, `telegram-companion-bot/bot.py`, runs
**six** independent character instances (nora, bonnie, cass, emily, jules, priya) as separate
Python processes on a single Termux/Android phone. Same code for all six; each process gets its
own instance directory (`~/<char>-bot/`) holding its `.env`, `state.json`, character-card JSON,
and life files. `bot_app/` is a partially-adopted modular package that bot.py imports
defensively. Each process is one asyncio event loop (python-telegram-bot polling + JobQueue).

Note: the repo-root `CLAUDE.md` still says "five bots" — Priya was added later. The authoritative
instance list is the `BOTS` list in `watchdog.sh` and the loop in `update-all.sh` (six entries).

## 1. bot.py stays the entry point (owner's #1 non-negotiable)

`bot.py` is and remains the process entry point (`run-bot.sh` runs `python -u bot.py
[instance-dir]`). Do NOT switch to `main.py` (it is an unused scaffold initializer), do not
rewrite `main()` / handler registration, and do not split bot.py into modules on your own
initiative.

**Rationale:** the deploy target is a phone. `update-all.sh` copies `bot.py` (plus `bot_app/`,
`acoustic_ears.py`, and helper scripts) into `~/telegram-bot/` and restarts everything. One file
that always runs beats an elegant package that can arrive half-deployed and take six bots down.
All the scheduling lives in `bot.py:main()` (~line 8717); rewriting registration is pure risk
for zero user-visible gain.

### bot_app/ — strangler-fig migration, partially adopted ON PURPOSE

`bot_app/MIGRATION.md` is the **canonical** record. bot.py imports the package defensively
(~line 1444): a `try/except` sets `_mem_service`/`_guards`/`_ActionRequest`/`_ingestion` to
`None` on any failure, and every call site falls back to inline behavior. A missing or
half-deployed `bot_app/` disables the migrated subsystems; it can NEVER crash the bots.

Wired in and live (the four security-relevant steps, per MIGRATION.md):

| Subsystem | Where used |
|---|---|
| `GuardService` | `_guard()` ~line 1480 — all guarded handlers route through it |
| `MemoryService` | untrusted-notes quarantine: `_note_untrusted()` ~1495, prompt block in `assemble_messages` ~3268, persisted in state.json |
| `ActionRequest` | `_action_allowed()` ~1462 — allowlist + bounds on model-requested react/selfie/search |
| `IngestionService` | JSON document parsing in `handle_document` |

Deliberately **unused scaffold** — the known trap for a new maintainer: `bot_app/handlers/*`
(ChatHandler/DocumentHandler/MediaHandler), `bot_app/services/model_api.py` (ModelService), and
`main.py:build_app()`. None of this is in the request path. Do not "finish the migration" by
wiring these in, and do not assume code in `bot_app/handlers/` runs — the real handlers are all
in bot.py. MIGRATION.md records steps 1 (config) and 7 (command bodies) as deliberately
skipped/deferred, and step 6 (`assemble_messages`) as intentionally last, only ever behind
parity tests.

## 2. Shared code vs per-instance state

- **In git = shared and deployable:** `bot.py`, `bot_app/`, `acoustic_ears.py`, helper scripts,
  `preset.txt`, `.env.example`, per-character card/life-file templates under `nora/`, `bonnie/`,
  `cass/`, `emily/`, `jules/`, `priya/`, and `docs/`.
- **Device-only, gitignored, hand-managed:** the authoritative list is
  `telegram-companion-bot/.gitignore` — `.env`, `state.json`, `state.json.corrupted`,
  `payments.json`, `reminders.json`, `cron_jobs.json`, `jokes.json`, `wardrobe.json`,
  `owner_chat.txt`, `bot.log`, `reading.txt`, `*.tmp`, images, venvs. Plus everything else the
  bot writes next to itself (`.alive`, `bot.pid`, vector caches, episode archives, cooldown/
  alert stamp files, `day.txt`, `memories.txt` on device).

**Invariant:** no code path may assume a per-instance file exists. Every reader is
best-effort (`exists()` check or try/except returning a default) — keep it that way. `.env` is
never touched by deploys, so per-bot config (API keys, `EMBED_MODEL`, Garmin creds, feature
flags) survives every update.

## 3. Message assembly order — the prompt-layering contract

`assemble_messages()` (bot.py **~line 3170**) builds the message list "the way SillyTavern
layers a card." The ORDER is load-bearing: later = closer to the reply = more salient. Verified
order (each block only appears if non-empty / feature-enabled):

1. Filled system prompt (character card, cached per user-name)
2. Setting (`SETTING`)
3. People in her life → life arc + projects → life-sim events (last 3) → Garmin snapshot → atlas
   (local places sample)
4. Capabilities block (`[react:]`, `[selfie:]`, `[search:]` tag instructions)
5. **Full verbatim conversation history**
6. Dynamic per-turn state, deliberately after history: `memory_block` (summaries + facts) →
   **untrusted-notes quarantine block** → user notes → mood note → vent mode → vibe → user
   energy → milestones → pinned "never forget" items → recently-asked questions (anti-repeat)
7. Retrieval, keyed off the latest turn: triggered lore → triggered memories (memories.txt) →
   episodic recall block → scene note → recent reading
8. Boundaries ("hard constraints") → post-history instructions (`POST_HISTORY_RAW`) → texting
   style → style mirror → selfie appearance → today's schedule + day context
9. `environment_note()` (local time + weather) — **deliberately last system block** so the real
   clock is the most salient thing the model sees (prevents wrong day/time drift)
10. The user message (with image parts if any)
11. Optional inner-voice private-thought block

Two callers append AFTER assembly, in `handle_message` (~7599–7608): the inner voice (skipped
during distress), then — if the safety screen tripped — `_safety_prompt()` is appended **LAST**
so care instructions outrank everything else. Preserve that ordering.

If you add a prompt block: decide its salience tier consciously, never displace the
environment-note-last rule, and never move the safety prompt off the final slot. Replacing this
function wholesale is forbidden without parity tests (MIGRATION.md step 6).

## 4. The proactive-messaging constellation

Every system that can message the owner **unprompted**. Grep the log tag to find each one.

| System | Function (~line) | Trigger | Gates | Log tag |
|---|---|---|---|---|
| Heartbeat check-in | `heartbeat` ~8117, `send_proactive` ~7950 | random `HEARTBEAT_MIN–MAX`, persisted across restarts (`schedule_next_heartbeat` ~8095) | owner set; skip if owner active < `HEARTBEAT_MIN*0.9` ago; quiet hours → saved draft; `/quiet` skip; daily nudge budget → draft; low-mood random skip → draft | `[heartbeat]` / `[proactive]` |
| "brb" follow-up | `_send_followup` ~7652, scheduled in `_deliver` ~7366 | bot's own reply matched `_FOLLOWUP_RE`; `FOLLOWUP_ENABLED` (default off) | cancelled if user replies first (~7527); skipped in "in-person" vibe | `[followup]` |
| Event reminders (auto-noticed events) | `fire_reminder` ~6430 (`kind == "event"`), scheduled by `_schedule_event`/`update_upcoming` | model-extracted upcoming event's before/after/recurring phase | **defers `EVENT_NUDGE_BUFFER_MIN` min if owner active (`last_seen`), capped at `EVENT_NUDGE_MAX_DEFERS`** — added in commit `6a8061f` after it interrupted live conversations | `[event-reminder]` |
| Explicit `/remindme` reminders | `fire_reminder` ~6480 (else branch) | user-set time | none — raw utility text `⏰ Reminder: ...`, out of character, by design | — |
| Cron jobs (`/cron`) | `run_cron_job` ~8021 | user-defined daily/interval schedule | none beyond schedule (user asked for it) | `[cron #id]` |
| Garmin stress monitor | `stress_monitor_job` ~2840 | sustained high stress over `STRESS_SUSTAINED_MIN` | cooldown stamp file (`STRESS_ALERT_COOLDOWN_HOURS`); quiet hours; `/quiet` | `[stress]` |
| Garmin body-battery monitor | `bb_monitor_job` ~2896 | BB ≤ `BB_LOW_THRESHOLD` | cooldown stamp; quiet hours; `/quiet` | `[bb]` |
| Garmin resting-HR monitor | `rhr_monitor_job` ~2963 | daily; RHR ≥ own median baseline + `RHR_ELEVATED_DELTA`, needs ≥3 days history | once-per-day stamp; quiet hours; `/quiet` | `[rhr]` |
| On-this-day reminiscing | `onthisday_job` ~3040 | daily; an archived episode's ~1mo/6mo/1yr anniversary | once/day + `ONTHISDAY_MIN_GAP_DAYS`; quiet hours; `/quiet` | `[onthisday]` |
| Traffic alerts | `traffic_poll_job` ~8549 | every `TRAFFIC_POLL_MINUTES`; new WSDOT incident nearby | **only while a live location share is active** (`live_until`); deduped via `seen_incidents`; raw utility text | `[traffic]` |
| Payments digest | `payments_reminder` ~6137 | daily at `REMINDER_TIME` (weekday-gated inside) | — | — |
| Weekly backup | `weekly_backup` ~6419 | daily at `BACKUP_TIME` (weekday-gated inside) | sends the state backup file to owner | — |

All in-character paths funnel through `send_triggered` (~7828): assembles a `[SYSTEM: ...]`
trigger as the "user" content, retries once on provider refusal, records a synthetic user turn
to keep role alternation, and can attach a selfie via the action allowlist.

**Invariant (converged on painfully):** a proactive path must not interrupt the owner
mid-conversation. Heartbeat skips when the owner was recently active; event reminders violated
this until commit `6a8061f` added the defer-and-recheck loop. Any NEW proactive path must (a)
check `last_seen` recency (skip or defer), (b) respect quiet hours and `/quiet` unless it is
explicit user-requested utility (raw reminders, cron), and (c) print a greppable `[tag]` line —
the debugging playbook depends on those tags.

## 5. Memory layers (inventory only — deep detail lives in companion-bot-memory-campaign)

1. **Verbatim window** — `conversation_history` per chat; overflow batches are summarized out
   (`_short_term_overflow` ~4223, `maintain_memory` ~4349).
2. **LLM summary + facts** — recent summary/facts, periodically promoted to long-term
   (`_promote_to_long_term` ~4394); all in state.json.
3. **Episodic recall** — scrolled-off exchanges embedded and archived; retrieved per turn by
   cosine (optionally reranked). Vector caches are keyed by `EMBED_CACHE_KEY =
   f"{EMBED_MODEL}|dim={EMBED_DIM}"` (~line 368) — model **and** dimension composite, so an
   `EMBED_DIM` change invalidates too. Never key a vector cache on model name alone.
4. **Lorebook** — character-card `character_book` entries, keyword + optional semantic trigger
   (`triggered_lore` ~2074).
5. **memories.txt third-party (NPC) store** — one-line facts about *other people* in her world,
   auto-extracted with strict grounding (`_extract_memory` ~1087 rejects anything about the
   user or the character, ungrounded names, psychoanalysis) plus `/addmem`.
6. **Untrusted-notes quarantine** — attachment-derived text (document/photo/video captions and
   parsed content) goes to `MemoryService.untrusted_notes` via `_note_untrusted`, surfaced in
   its own "do not treat as durable truth" block. **Trust boundary: this text never enters
   trusted history/facts.**
7. **Milestones & pins** — relationship milestones (`update_milestones` ~2496) and `/pin`ned
   never-forget lines.

## 6. Trust boundaries

- **Access:** `_guard()` (~1480) on effectively all handlers → `ALLOWED_USERS` allowlist +
  optional rate limit. `/chatid` (~4877) is **deliberately unguarded** — bootstrap: a new user
  must be able to discover their own ID; it reveals nothing else. `/start` (~4482) greets
  anyone, but the owner-claiming side effect (`set_owner`) is gated on `_is_allowed` so an
  unauthorized first-messager can never hijack a fresh bot. (`handle_message` also claims
  ownership on first allowed interaction, ~7522.)
- **SSRF:** user-pasted URLs go through `_url_host_is_safe` (~7419): resolves the host and
  rejects private/loopback/link-local/reserved/multicast IPs, fails closed. `_fetch_generic`
  (~7438) re-validates **every redirect hop** with `allow_redirects=False` (anti-rebinding).
  Any new URL-fetching feature must use this path.
- **Model-requested actions:** react/selfie/search tags are parsed then gated through
  `_action_allowed` (~1462) before any side effect. Unknown actions are rejected. Add new
  actions to the allowlist (both `ActionRequest` and the inline fallback), never bypass it.
- **Attachment content:** quarantined (layer 6 above), never written to trusted memory.

## 7. External services map

All HTTP goes through one module-level `_session = requests.Session()` (~line 43).

| Service | Used for | Notes |
|---|---|---|
| NanoGPT (`NANOGPT_BASE_URL`) | chat completions (`call_nanogpt` ~3486), embeddings (`_embed` ~613), rerank, vision, image gen (`NANOGPT_IMAGE_URL`), **video**-audio transcription (Whisper, in `handle_video` ~6980) | Bearer auth; `NANOGPT_API_KEY` required at startup |
| Inworld | voice-note STT with `voiceProfile` (`_transcribe_inworld` ~6857) and TTS voice replies (`_synth_inworld` ~6899, OGG/Opus straight to Telegram) | swapped from NanoGPT 2026-07-01 (commits `ed15b25`, `faea119`); `INWORLD_API_KEY` is **pre-base64-encoded**, sent as `Basic` auth |
| Garmin (garminconnect) | health snapshot + stress/BB/RHR monitors | `_garmin_client` (~2693) caches the login and persists a **login cooldown** on failure so restarts can't hammer Garmin's rate-limited login; failed fetches drop the cached client to force re-login |
| Telegram Bot API | everything user-facing | python-telegram-bot, polling |
| DuckDuckGo HTML | `web_search` (~7465), reading feed | no key |
| Open-Meteo-style weather | `_fetch_weather`, cached with TTL | prompt context |
| WSDOT | traffic alerts/times (optional) | `WSDOT_API_KEY` |

**Async discipline (real audit finding):** one event loop per process — a single blocking call
freezes that character entirely (typing indicators, jobs, polling). Every network/disk-heavy
sync helper must be called via `asyncio.to_thread` from async code. Commit `2012fbc`
("Reliability: stop blocking the event loop") fixed a batch of violations; the discipline is
convention-enforced, not structural, so check every new call site.

## 8. Supervision chain (device)

```
bot.py process  (writes .alive every 60s via _touch_liveness; bot.pid lock)
  ^ started/restarted by
run-bot.sh <dir> <session>   — per-instance supervisor loop inside a tmux session;
  restarts the process on any exit (crash, OOM kill)
  ^ sessions checked by
watchdog.sh --loop   — every WATCHDOG_INTERVAL: relaunches a bot whose tmux session is
  gone OR whose .alive stamp is stale (frozen-but-alive detection); BOTS list lives here
  ^ started at boot by
termux-boot-start.sh (in ~/.termux/boot/) — uses **setsid, NOT nohup**: nohup only blocks
  SIGHUP, and Android/Termux's process-group cleanup killed the nohup'd loop anyway when the
  launcher exited. setsid detaches into a new session; confirmed on-device (commit a080f99,
  settled 2026-06). Idempotent via pgrep.
```

Deploy = `bash ~/telegram-bot/update-all.sh` on the device (see companion-bot-device-ops and
companion-bot-change-control). It syncs `bot.py`, `bot_app/`, `acoustic_ears.py`,
`run-bot.sh`/`watchdog.sh`/`status.sh`, and `.env.example` — **not** `update-all.sh` itself
(unsafe to overwrite mid-run) and never `.env` or state files.

## Known weak points (state these plainly when relevant)

- **Unused bot_app scaffold** (`bot_app/handlers/*`, `model_api.py`, `main.py`) looks like the
  real code path but isn't — the single most likely thing to mislead a maintainer.
- **No tests, no CI.** The only automated check is a `py_compile` pre-commit hook. Every change
  is verified by on-device smoke test (Emily first, per MIGRATION.md).
- **Blocking-call discipline is by convention** — a new un-wrapped `requests` call in an async
  path freezes the whole character (see §7).
- **`seen_incidents` grows unbounded** (per-chat set of every WSDOT alert ID ever seen,
  persisted in state.json; `traffic_poll_job` adds, nothing ever trims).
- **`on_error` (~8579) echoes raw exception text to the chat** (`❌ {type}: {err}`) — breaks
  character and can leak internals; a NetworkError/TimedOut special case is the only filter.
- **Single-phone SPOF** — all six bots, their state, and the supervisor live on one Android
  device; the weekly backup message is the only off-device copy.
- **state.json is one JSON blob per instance.** Writes are atomic (tmp + `replace`, ~1601), and
  a corrupt file is renamed to `state.json.corrupted` and abandoned (`load_state` ~1510) — so a
  corruption event silently loses all conversational state rather than crashing.

## Invariants checklist — before merging, confirm you didn't break:

- [ ] `bot.py` is still the entry point; `run-bot.sh` still runs `python -u bot.py`.
- [ ] Any new `bot_app` usage is behind the defensive import — the bot still starts (and only
      degrades) if `bot_app/` is missing.
- [ ] No code path assumes a per-instance file exists in the repo or on a fresh device.
- [ ] `assemble_messages` block ORDER preserved; `environment_note()` still the last system
      block before the user turn; the safety prompt still appended last on distress.
- [ ] Any new proactive path: gates on owner activity (`last_seen`) and quiet hours//quiet, and
      prints a greppable `[tag]` log line.
- [ ] Attachment-derived text still only reaches the untrusted-notes channel, never trusted
      memory.
- [ ] New handlers call `_guard()`; `/chatid` and `/start`'s greeting stay open;
      owner-claiming stays `_is_allowed`-gated.
- [ ] Any new outbound URL fetch goes through `_url_host_is_safe` (including redirects); any
      new model-requested action goes through `_action_allowed`.
- [ ] No blocking network/CPU call added on the event loop — wrap in `asyncio.to_thread`.
- [ ] Vector/episode caches still keyed by `EMBED_CACHE_KEY` (model **and** dim).
- [ ] Nothing new hard-fails on a Garmin login (cooldown path intact).
- [ ] state.json writes stay atomic (tmp + replace); new persistent state added to BOTH
      `save_state` and `load_state`.
- [ ] `python -m py_compile telegram-companion-bot/bot.py` passes; instance count (six)
      consistent across `watchdog.sh` and `update-all.sh` if touched.

## Provenance and maintenance

Written 2026-07-02 against branch `claude/push-to-repo-7i2f3c`. To re-verify each section:

- §1: `grep -n "from bot_app" telegram-companion-bot/bot.py` and read `bot_app/MIGRATION.md`
  (canonical status).
- §2: `cat telegram-companion-bot/.gitignore`.
- §3: read `assemble_messages` top-to-bottom (`grep -n "def assemble_messages" bot.py`) and the
  distress append in `handle_message`.
- §4: `grep -n "async def .*_job\|send_triggered\|fire_reminder\|heartbeat" bot.py` and the
  JobQueue registrations at the bottom of `main()`; `git show 6a8061f` for the defer rationale.
- §5: `grep -n "EMBED_CACHE_KEY\|_extract_memory\|untrusted" bot.py`.
- §6: read `_guard`, `chatid`, `start`, `_url_host_is_safe`, `_action_allowed`.
- §7: `grep -n "INWORLD_\|NANOGPT_\|_garmin_client\|asyncio.to_thread" bot.py`.
- §8: read `run-bot.sh`, `watchdog.sh` (BOTS list), `termux-boot-start.sh` (setsid comment).

If a re-check contradicts this file, the CODE wins — update this file in the same change.
