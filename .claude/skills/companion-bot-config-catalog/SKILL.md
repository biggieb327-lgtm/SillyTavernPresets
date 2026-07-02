---
name: companion-bot-config-catalog
description: >
  Complete catalog of every configuration knob in telegram-companion-bot: all env vars read by
  bot.py / bot_app/core/config.py (name, default, type, purpose, whether .env.example documents
  it), plus runtime settings that are NOT env vars (/nudges, /voice, /quiet). Load this when:
  adding or renaming an env var; editing .env.example; diagnosing a setting that seems ignored
  ("I set X in .env and nothing changed"); checking whether a var name is real or phantom;
  deciding per-instance .env vs shared common.env; setting up a new character's .env; or
  answering "what knob controls X". Do NOT use for: secrets handling / deploy mechanics /
  device commands (use companion-bot-device-ops) or how a subsystem actually behaves
  (use companion-bot-architecture-contract).
---

# Companion-bot configuration catalog

**Cataloged 2026-07-02 at commit `faea119`** ("Replace NanoGPT with Inworld TTS for voice
replies"). Every row below comes from greps run against that commit — see "Provenance and
maintenance" at the bottom to re-certify. Config drifts fast in this repo; if HEAD has moved,
re-run the verification commands before trusting a specific default.

## How configuration loads (read this first)

- Config = env vars read via `os.getenv(...)` at import time in
  `telegram-companion-bot/bot.py` (all but 4 of them) and
  `telegram-companion-bot/bot_app/core/config.py` (refactor scaffold — see its section).
- Load order (bot.py lines 61–76): `common.env` next to the code (shared defaults, optional,
  skipped if missing) is loaded first, then the instance's own `~/<char>-bot/.env` loaded
  **over** it. So per-bot `.env` always wins. Instance home comes from `argv[1]` or `BOT_HOME`.
- `migrate_common_env.py` is the one-time tool that moves keys identical across every bot's
  `.env` into `common.env`. It hard-refuses to centralize `TELEGRAM_BOT_TOKEN`, `BOT_TOKEN`,
  `CHARACTER_CARD`, `NAME`, `BOT_HOME` (its `NEVER_SHARE` set). Note: `NAME` is in that set
  but is not read anywhere in code — it's device-side-only / vestigial.
- `.env.example` is documentation ONLY. It is synced to the device as a reference and is
  never auto-applied. Real `.env` files are hand-managed device state; **no automation ever
  touches them** (owner non-negotiable). A new var shipped in bot.py takes effect via its
  default; the owner opts in by manually editing each bot's `.env` and restarting.
- Env vars are read once at startup. Changing `.env` requires a bot restart to take effect.

**Headline numbers (2026-07-02):** 178 unique env var names in code (174 via bot.py,
4 scaffold-only in bot_app/core/config.py). 99 are documented in `.env.example`,
79 are undocumented (work fine, just not in the template), and **0 phantom vars** —
`.env.example` currently contains no var the code doesn't read (the phantom class was
purged in e9e3880; see "Dead and renamed vars" below).

Legend: **Doc** = appears in `.env.example` (Y/N). Defaults are the exact code defaults.
"= X" means the default is another var's resolved value.

## Required at startup (bot exits without these)

| Var | Type | Doc | Purpose |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | str | Y | Bot token from @BotFather. Missing → `SystemExit` (bot.py:82). Per-instance, never shared. |
| `NANOGPT_API_KEY` | str | Y | NanoGPT (OpenAI-compatible) API key for all chat/utility model calls. Missing → `SystemExit` (bot.py:84). |

Conditionally required: `GEMINI_API_KEY` if `SELFIE_PROVIDER=gemini` (SystemExit at
bot.py:284); `INWORLD_API_KEY` if voice notes or `/voice` replies are used (runtime
RuntimeError, not startup — voice notes return "[couldn't make out that voice note]").

## Identity, instance and access

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `BOT_HOME` | (none) | path | N | Instance data dir (its .env, card, memory). `argv[1]` overrides it; unset = script's own folder. Set by run-bot.sh in production. |
| `CHARACTER_CARD` | `priya.json` | str | Y | SillyTavern v2 card filename in the instance dir. Per-instance, never shared. |
| `PRESET_FILE` | `preset.txt` | str | N | Extra system-instruction text file (texting style) in the instance dir. |
| `OWNER_CHAT_ID` | (none) | int | N | Overrides `owner_chat.txt` as the proactive-message target chat. Normally unset (file is written on first contact). |
| `ALLOWED_USERS` | `""` (allow all) | csv of ints | Y | Telegram user-ID allowlist. Empty = anyone can talk to the bot. |
| `RATE_LIMIT_SECONDS` | `2` | float | Y | Min seconds between messages per user. |
| `ATLAS_FILE` | `places.txt` | str | N | Local-places file (selfie backgrounds, references). |
| `ATLAS_SAMPLE` | `6` | int | N | How many atlas places to sample into context. |

## API provider and models

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `NANOGPT_BASE` | `https://nano-gpt.com/api/v1` | url | Y | OpenAI-compatible API base (swap for Together/Ollama/etc.). |
| `NANOGPT_MODEL` | `zai-org/glm-5:thinking` | str | Y | Main chat model (her replies). |
| `SUMMARY_MODEL` | = `NANOGPT_MODEL` | str | Y | Rolling-summary model (point at something faster/cheaper). |
| `VISION_MODEL` | `zai-org/glm-4.6v` | str | Y | Image-input model (main model is text-only). |
| `FALLBACK_MODEL` | `""` (off) | str | Y | Used when the chat model 5xx/times out. |
| `VISION_FALLBACK` | `""` (off) | str | Y | Fallback for the vision model; must accept images. |
| `REACTION_MODEL` | `zai-org/glm-4.7-flash` | str | Y | Fast/cheap emoji-reaction picker. |
| `MOOD_MODEL` | = `REACTION_MODEL` | str | Y | Cheap appraiser; also the default for SAFETY/SCENE/EVENT/INNER_VOICE/READING/LIFE models. |
| `DOCUMENT_MODEL` | `meta-llama/llama-3.3-70b-instruct` | str | N | Document/card analysis — deliberately an instruction model, not a roleplay one. |
| `REQUEST_TIMEOUT` | `300` | int (s) | Y | API call timeout. |

## Sampling knobs (her replies only, not utility calls)

All unset by default — only vars you set are sent in the request; a bad value is ignored
with a `[config] ignoring bad ...` print (bot.py:129–145). All documented (Y), with
per-character starting points in `.env.example` (Jules 1.1 … Cass 0.85). Per-instance by design.

`TEMPERATURE` (float), `TOP_P` (float), `TOP_K` (int), `MIN_P` (float),
`FREQUENCY_PENALTY` (float), `PRESENCE_PENALTY` (float), `REPETITION_PENALTY` (float),
`MAX_TOKENS` (int). top_k/min_p/repetition_penalty are open-model extras; a model that
rejects one returns 400 — unset it.

## Mood, inner voice, safety, scene

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `REACTIONS_AUTO` | `1` | bool | N | Auto emoji reactions to user messages. |
| `MOOD_AUTO` | `1` | bool | N | Automatic mood appraisal after exchanges. |
| `MOOD_LABEL_FRESH_HOURS` | `12` | float | N | How long a mood label stays fresh. |
| `INNER_VOICE_ENABLED` | `true` | bool | N | Private inner-monologue pass. NOTE: parsed with `== "true"` — only the literal string `true` enables it (unlike most flags here). |
| `INNER_VOICE_MODEL` | = `MOOD_MODEL` | str | N | Model for the inner-voice pass. |
| `SAFETY_ENABLED` | `1` | bool | Y | Distress screening: drop the performance on genuine crisis. |
| `SAFETY_MODEL` | = `MOOD_MODEL` | str | Y | Cheap classifier for the safety screen. |
| `SAFETY_RESOURCES` | US 988 line text | str | Y | Crisis resource line she can offer (change per country). Multi-line `os.getenv(` call — naive one-line greps miss it. |
| `SCENE_CONTINUITY` | `1` | bool | Y | Track her physical location so she doesn't teleport mid-scene. |
| `SCENE_MODEL` | = `MOOD_MODEL` | str | Y | Scene tracker model. |
| `SCENE_MAX_AGE_HOURS` | `3` | float | Y | Stop injecting a stale scene after this. |

## Event reminders

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `EVENT_REMINDERS` | `1` | bool | Y | Extract dated events; schedule "good luck" / "how'd it go" nudges. |
| `EVENT_MODEL` | = `MOOD_MODEL` | str | Y | Event-extraction model. |
| `EVENT_HORIZON_DAYS` | `120` | int | Y | Ignore events further out. |
| `EVENT_BEFORE_MIN` | `45` | int | Y | "Good luck" minutes before a timed event. |
| `EVENT_AFTER_HOURS` | `2.5` | float | Y | "How'd it go" hours after. |
| `EVENT_NUDGE_BUFFER_MIN` | `15` | int | Y | Defer a nudge if the user was active within this window. |
| `EVENT_NUDGE_MAX_DEFERS` | `3` | int | Y | Fire anyway after this many deferrals. |

## Voice and audio (Inworld since 2026-07-01 — read carefully)

The 2026-07-01 swap (ed15b25 STT, faea119 TTS) replaced NanoGPT with Inworld for BOTH
directions of voice. Verified against faea119:

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `INWORLD_API_KEY` | `""` | str (base64) | Y | **One key for both voice-note STT and TTS replies.** Sent as `Authorization: Basic <key>` (bot.py:6874, 6913) — the key from inworld.ai is already base64, don't re-encode. Missing → voice notes fail with "[couldn't make out that voice note]"; `/voice` replies silently don't send. |
| `INWORLD_STT_MODEL` | `inworld/inworld-stt-1` | str | Y | Voice-note transcription model. |
| `INWORLD_STT_LANG` | `en` | str | Y | STT language hint. |
| `INWORLD_TTS_MODEL` | `inworld-tts-1.5-max` | str | Y | TTS model for voice replies. |
| `TTS_VOICE` | `Sarah` | str | Y | **Inworld voiceId**, per-instance. OpenAI voice names (nova, shimmer, …) are INVALID since faea119. Custom cloned voices use generated IDs. List: `curl https://api.inworld.ai/voices/v1/voices -H "Authorization: Basic $KEY"`. |
| `TTS_CHANCE` | `0.30` | float 0–1 | Y | Chance a reply becomes a voice message *when `/voice` is on* (see runtime section — on/off is a command, not an env var). |
| `WHISPER_MODEL` | `whisper-1` | str | Y | **Video-file audio only** now. Voice notes do NOT use this anymore. |
| `VOICE_TONE_ENABLED` | `true` | bool | Y | Local FFT vocal-tone note (pace/volume/pitch) beside the transcript. Needs the optional `acoustic_ears` module + numpy; missing module just disables it. |
| `VIDEO_MAX_SIZE_MB` | `50` | int | Y | Max accepted video size (needs ffmpeg on device). |
| `FFMPEG_TIMEOUT` | `25` | int (s) | N | Kill a hung/adversarial ffmpeg job. |

**Dead:** `TTS_MODEL` was REMOVED at faea119. If you find it in an old `.env`, it is
silently ignored — delete it and set `INWORLD_TTS_MODEL` instead. STT/TTS endpoint URLs
are hardcoded constants (`INWORLD_STT_URL`, `INWORLD_TTS_URL`), not env vars.

## Documents, PDFs, links, search, reading feed

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `DOCUMENT_MAX_SIZE_MB` | `2` | int | N | Max document upload size. |
| `PDF_MAX_SIZE_MB` | `20` | int | N | Max PDF size. |
| `PDF_MAX_CHARS` | `16000` | int | N | Truncate extracted PDF text. |
| `PDF_OCR_MAX_PAGES` | `4` | int | N | OCR page cap. |
| `LINK_READING` | `1` | bool | N | Fetch and read URLs the user sends. |
| `LINK_FETCH_TIMEOUT` | `15` | int (s) | N | Link fetch timeout. |
| `LINK_MAX_CHARS` | `2200` | int | N | Truncate fetched page text. |
| `LINK_MAX_REDIRECTS` | `5` | int | N | Redirect cap. |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | `""` | str | N | Reddit OAuth app (script type) — required to read reddit links at all. |
| `REDDIT_USER_AGENT` | `CompanionBot/1.0` | str | N | Reddit UA. |
| `SEARCH_ENABLED` | `1` | bool | N | DuckDuckGo web search tool. Gating parent of READING_ENABLED. |
| `SEARCH_RESULTS` | `4` | int | N | Results per search. |
| `READING_ENABLED` | `1` (AND `SEARCH_ENABLED`) | bool | N | Periodic interest-topic reading feed ("things she read"). |
| `READING_MODEL` | = `MOOD_MODEL` | str | N | Reading-summary model. |
| `READING_MAX` | `5` | int | N | Items kept. |
| `READING_TIMES` | `09:40,13:40,18:40` | HH:MM csv | N | Local times to refresh the feed. |

## Selfies / image generation

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `SELFIE_PROVIDER` | `gemini` if `GEMINI_API_KEY` set, else `nanogpt` | str | Y | Backend picker. `gemini` without a key = SystemExit. |
| `GEMINI_API_KEY` | `""` | str | Y | Google key for Gemini image gen. |
| `GEMINI_IMAGE_MODEL` | `gemini-2.5-flash-image` | str | Y | Gemini image model. |
| `GEMINI_IMAGE_URL` | `https://generativelanguage.googleapis.com/v1beta/models` | url | N | Gemini API base. |
| `NANOGPT_IMAGE_URL` | `https://nano-gpt.com/v1/images/generations` | url | N | NanoGPT image endpoint. |
| `SELFIE_MODEL` | `flux-kontext` | str | N | NanoGPT-path image model. |
| `SELFIE_BASE` | `""` | filename | Y | Reference portrait in the instance dir (img2img base). Per-instance. |
| `SELFIE_SIZE` | `1024x1024` | str | N | Output size. |
| `SELFIE_GUIDANCE` | `3.5` | float | N | Guidance scale (NanoGPT path). |
| `SELFIE_STEPS` | `28` | int | N | Diffusion steps (NanoGPT path). |
| `IMAGE_TIMEOUT` | `180` | int (s) | N | Image-gen call timeout. |
| `PHOTO_SELFIE_CHANCE` | `0.20` | float 0–1 | Y | Chance she fires back a selfie after the user sends a photo. |
| `SELFIE_DEDUP_SIZE` | `6` | int | N | Recent-scene memory to avoid repeat selfie scenarios. |

Appearance text is a file, not an env var: `appearance.txt` in the instance dir.

## Texting realism and conversational behavior

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `TEXTING_REALISM` | `1` | bool | N | Split replies into multiple phone-like bubbles. |
| `TYPING_DELAY` | `1` | bool | N | Simulated typing pauses. |
| `TYPING_WPM` | `120` | float | N | Simulated typing speed. |
| `TYPING_DELAY_MIN` / `TYPING_DELAY_MAX` | `0.5` / `3.5` | float (s) | N | Delay clamp. |
| `STYLE_MIRROR` | `1` | bool | Y | Heuristic mirroring of the user's texting register (no model call). |
| `STYLE_SAMPLE` | `20` | int | Y | Recent user messages to read. |
| `STYLE_MIN_MSGS` | `6` | int | Y | Minimum before adapting. |
| `DEVICE_RENDER` | `0` | bool | N | Render her bubbles in monospace "phone log" style. |
| `FOLLOWUP_ENABLED` | `false` | bool | N | "brb"-style auto follow-up messages. Off by default; parsed with `== "true"`. |
| `FOLLOWUP_MIN_SECS` / `FOLLOWUP_MAX_SECS` | `45` / `120` | float | N | Follow-up delay window. |
| `LULL_THRESHOLD` | `3` | int | N | Consecutive terse user replies before an approach shift. |
| `GAP_AWARE_HOURS` | `12` | float | N | Long-absence threshold noted in context on return. |
| `QUESTION_MEMORY_SIZE` | `8` | int | N | Recent bot questions remembered to avoid repeats. |
| `PROACTIVE_HOOK_DEDUP_SIZE` | `8` | int | N | Recent proactive hooks remembered to avoid repeats. |

## Proactive / heartbeat / scheduled jobs

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `HEARTBEAT_MIN_HOURS` | `2` | float | Y | Random proactive-tick window, low end. **Not** `HEARTBEAT_MIN` — that was a real phantom-var bug, fixed in e9e3880. |
| `HEARTBEAT_MAX_HOURS` | `6` | float | Y | Window high end. |
| `QUIET_START` / `QUIET_END` | `23:00` / `08:00` | HH:MM | Y | No proactive messages in this local window. This is the ONLY hour gate — there is no PROACTIVE_HOUR_START/END. |
| `LIFE_SIM_ENABLED` | `1` | bool | Y | "Offline life": invents concrete events in her world. |
| `LIFE_MODEL` | = `MOOD_MODEL` | str | Y | Event-generation model. |
| `LIFE_EVENTS_MAX` | `8` | int | Y | Events kept. |
| `LIFE_EVENT_TIMES` | `13:00,20:30` | HH:MM csv | Y | Generation times. |
| `ONTHISDAY_ENABLED` | `1` (AND episodic recall) | bool | Y | Anniversary reminiscing off the episode archive. |
| `ONTHISDAY_TIME` | `10:30` | HH:MM | Y | Daily check time. |
| `ONTHISDAY_WINDOW_DAYS` | `3` | int | Y | ± days that count as an anniversary. |
| `ONTHISDAY_MIN_GAP_DAYS` | `5` | int | Y | Min days between reminisces. |
| `REFLECTION_TIME` | `03:00` | HH:MM | Y | Nightly maintenance (memory promotion, mood reset, milestones). |
| `BACKUP_TIME` | `09:05` | HH:MM | Y | Weekly backup time. |
| `BACKUP_WEEKDAY` | `6` (Sun) | int 0–6 | N | Backup day. |
| `TIMEZONE` | `America/Los_Angeles` | IANA tz | Y | All time-aware features. **Not** `BOT_TIMEZONE` (phantom, fixed in e9e3880). Bad value falls back to device-local time with a printed warning. |

Heartbeat *count* per day is NOT an env var — see the runtime section (`/nudges`).

## Payments (home-instance feature)

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `PAYMENTS_ENABLED` | `1` on the home instance, `0` on named instances | bool | Y | Payment-tracking commands. Instance-dependent default (`IS_NAMED_INSTANCE`); multi-line `os.getenv(` call — one-line greps miss it. |
| `REMINDER_TIME` | `09:00` | HH:MM | Y | Weekly payment-summary time. |
| `REMINDER_WEEKDAY` | `3` (Thu) | int 0–6 | Y | Summary day (example comment suggests 0; code default is 3). |
| `REMINDER_WINDOW_DAYS` | `6` | int | N | Look-ahead window for the summary. |

## Memory, facts, notes (non-embedding)

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `SHORT_TERM_HOURS` | `48` | float | N | Verbatim messages older than this get distilled into summary. |
| `MEMORY_TOKEN_BUDGET` | `300` | int | N | Token budget for injected NPC/world memories. |
| `MEMORY_MODEL` | `zai-org/glm-5.2` | str | N | Memory extraction/consolidation model. |
| `MEMORIES_MAX` | `200` | int | N | Cap on memories.txt entries. |
| `MEMORY_AUTO` | `1` | bool | N | Automatic memory capture. |
| `USER_NOTES_MAX` | `15` | int | N | Cap on follow-up user notes (user_notes.txt). |
| `RECENT_FACTS_MAX` / `RECENT_FACTS_TARGET` | `30` / `20` | int | N | Consolidate recent-facts list past MAX down to TARGET. |
| `LONG_FACTS_MAX` / `LONG_FACTS_TARGET` | `22` / `15` | int | N | Same for durable facts. |
| `PROMOTION_INTERVAL_DAYS` | `7` | float | N | Recent→long-term promotion cadence. |
| `MILESTONES_MAX` | `30` | int | Y | Relationship-milestone cap. |
| `MAX_UNTRUSTED_NOTES` | `60` | int | N | Cap on quarantined attachment-derived notes (also in scaffold config). |
| `MAX_MEMORY_ITEM_CHARS` | `500` | int | N | Per-item memory length cap (also in scaffold config). |

## Embeddings, episodic recall, reranker (opt-in, pay-as-you-go)

Master switch: `EMBED_MODEL` set = embeddings on; empty = free keyword retrieval only.
Episodic recall additionally needs numpy (optional import; missing = feature off).

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `EMBED_MODEL` | `""` (off) | str | Y | NanoGPT embedding model (e.g. `BAAI/bge-large-en-v1.5`). Differs per bot in practice (some have it, some don't). |
| `EMBED_DIM` | `0` (model default) | int | Y | Dim reduction, text-embedding-3-* only. Changing it invalidates the vector cache (by design, via `EMBED_CACHE_KEY`). |
| `EMBED_MIN_SIM` | `0.35` | float | Y | Cosine floor for a memory to count as relevant. |
| `EMBED_MAX_CHARS` | `1600` | int | N | Truncate each embed input. |
| `EPISODIC_RECALL` | `1` (AND `EMBED_MODEL`) | bool | Y | Archive scrolled-off conversation; recall past exchanges per turn. |
| `EPISODE_MAX` | `4000` | int | Y | Archived-chunk cap. |
| `EPISODE_CHUNK_MSGS` | `6` | int | Y | Messages per chunk. |
| `EPISODE_EMBED_CHARS` | `1600` | int | N | Truncate chunk before embedding. |
| `EPISODE_MIN_SIM` | `0.40` | float | Y | Cosine floor to surface a past moment. |
| `EPISODE_TOPK` | `1` | int | Y | Moments surfaced per turn. |
| `EPISODE_MIN_AGE_HOURS` | `24` | float | Y | Don't recall very recent stuff. |
| `LORE_MIN_SIM` | `0.42` | float | N | Cosine floor for semantic lore matches. |
| `MEMORY_DEDUP_SIM` | `0.93` | float | N | Skip a new memory this similar to an existing one. |
| `RERANK_MODEL` | `""` (off) | str | Y | Cross-encoder reranker for episode candidates; falls back to cosine on failure. |
| `RERANK_CANDIDATES` | `12` | int | Y | Cosine top-N handed to the reranker. |
| `RERANK_ENDPOINT` | `/rerank` | path | Y | Appended to `NANOGPT_BASE`. |

## World: weather, timezone, traffic

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `WEATHER_LOCATION` | `Seattle` | str | N | Display name for her local weather. |
| `WEATHER_LAT` / `WEATHER_LON` | `47.6062` / `-122.3321` | str | N | Open-Meteo coordinates. Per-instance if characters live in different cities. |
| `WSDOT_API_KEY` | `""` (feature off) | str | N | WSDOT traffic feed (Western WA). `TRAFFIC_ENABLED = bool(key)`. |
| `TRAFFIC_RADIUS_MILES` | `10` | float | N | Alert radius. |
| `TRAFFIC_POLL_MINUTES` | `30` | int | N | Poll cadence. |

## Garmin health feed (opt-in; needs `pip install garminconnect`)

`GARMIN_ENABLED = bool(GARMIN_EMAIL and GARMIN_PASSWORD)` — both set = on. The library is a
defensive optional import; missing it just disables the feature (and `/garmin` says so).
All STRESS_/RHR_/BB_ flags are additionally gated on `GARMIN_ENABLED`.

| Var | Default | Type | Doc | Purpose |
|---|---|---|---|---|
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | `""` | str | Y | Garmin Connect login (unofficial API; password only used for first login, then tokens). |
| `GARMIN_TIMES` | `07:30,16:00` | HH:MM csv | Y | Snapshot refresh times. |
| `GARMINTOKENS` | `~/.garminconnect` | path | N | Token store dir (note: no underscore in the name — upstream lib convention). |
| `GARMIN_MAX_AGE_HOURS` | `18` | float | Y | Don't inject a stale snapshot. |
| `GARMIN_LOGIN_COOLDOWN` | `1800` | int (s) | N | Back off after a failed login. |
| `STRESS_ALERTS` | `1` | bool | Y | Reach out when stress stays high. |
| `STRESS_THRESHOLD` | `60` | int 0–100 | Y | Sustained-above = high. |
| `STRESS_SUSTAINED_MIN` | `45` | int (min) | Y | Must stay high this long. |
| `STRESS_POLL_MIN` | `30` | int (min) | Y | Poll cadence (BB shares it). |
| `STRESS_ALERT_COOLDOWN_HOURS` | `4` | float | Y | Re-alert suppression. |
| `RHR_ALERTS` | `1` | bool | Y | Elevated resting-HR morning check-in. |
| `RHR_ELEVATED_DELTA` | `7` | int (bpm) | Y | Above-baseline delta to flag. |
| `RHR_BASELINE_DAYS` | `14` | int | Y | Rolling baseline window. |
| `RHR_CHECK_TIME` | `08:00` | HH:MM | Y | Once-daily check. |
| `BB_ALERTS` | `1` | bool | Y | Body-battery-low nudge. |
| `BB_LOW_THRESHOLD` | `20` | int 0–100 | Y | At/below = drained. |
| `BB_ALERT_COOLDOWN_HOURS` | `8` | float | Y | Re-alert suppression. |

## Refactor scaffold: bot_app/core/config.py (mostly NOT production)

`bot_app/core/config.py` defines a `Settings` dataclass consumed only by `main.py`
("Refactor starter") — production runs `bot.py`, which imports bot_app *services* directly
and passes its own constants. Vars unique to the scaffold:

| Var | Default | Doc | Status |
|---|---|---|---|
| `BOT_TOKEN` | `""` | N | **Scaffold only. NOT the production token** — that's `TELEGRAM_BOT_TOKEN`. (Also in migrate_common_env's NEVER_SHARE, defensively.) |
| `MODEL_SIDE_EFFECTS_ENABLED` | `0` | N | Scaffold flag; unused by bot.py path. |
| `STRICT_MEMORY_MODE` | `1` | N | Scaffold flag; unused by bot.py path. |
| `MAX_USER_TEXT_CHARS` | `4000` | N | Scaffold only. |

`MAX_MEMORY_ITEM_CHARS`, `MAX_UNTRUSTED_NOTES`, `FFMPEG_TIMEOUT` appear in BOTH files and
DO work in production (bot.py reads them itself at lines 1442–1443 / 188).

## Dead and renamed vars — the "silently ignored" trap

python-dotenv loads whatever is in `.env`; bot.py only reads the names above. A var the
code doesn't read fails SILENTLY — no warning, no error, the default just applies. This
bug class was real. Known corpses to recognize on sight:

| If you see… | Reality |
|---|---|
| `TTS_MODEL` | Removed at faea119 (Inworld TTS swap). Use `INWORLD_TTS_MODEL`. |
| `TTS_VOICE=nova` (or any OpenAI voice name) | Invalid since faea119 — TTS_VOICE is now an Inworld voiceId (default `Sarah`). |
| `HEARTBEAT_MIN` / `HEARTBEAT_MAX` | Never read. Real names: `HEARTBEAT_MIN_HOURS` / `HEARTBEAT_MAX_HOURS` (mismatch fixed in .env.example at e9e3880). |
| `BOT_TIMEZONE` | Never read. Real name: `TIMEZONE` (fixed in e9e3880). |
| `PROACTIVE_HOUR_START` / `PROACTIVE_HOUR_END` | Phantom — never existed in code. QUIET_START/QUIET_END is the only hour gate. |
| `NUDGE_MAX` | Phantom. The nudge budget is the `/nudges` command, not an env var. |
| `CONTEXT_LIMIT`, `SUMMARY_EVERY` | Phantom — removed from .env.example in e9e3880. |
| `NAME` | In migrate_common_env's NEVER_SHARE set but read by no code. |

First move when "I set X and nothing changed": `grep -n '"X"' telegram-companion-bot/bot.py`.
No hit = the var does not exist (check this table, then the rename history). Hit = check the
gating parents (e.g. STRESS_* without Garmin creds does nothing; EPISODE_* without
EMBED_MODEL does nothing; READING_* with SEARCH_ENABLED=0 does nothing) and remember env
is read at startup — did the bot restart?

## Runtime config that is NOT env vars (stop hunting)

Command-driven, per-chat state persisted in the instance's `state.json` (atomic writes,
survives restarts). There is no env var for any of these:

| Setting | Command | Storage | Default |
|---|---|---|---|
| Proactive messages/day budget | `/nudges N` (`/nudges 0` = unlimited) | `nudge_budget` in state.json | 3/day |
| Voice replies on/off | `/voice` (or `/voice on|off`) | `voice_reply` in state.json | off (TTS_CHANCE only applies while on) |
| Temporary proactive silence | `/quiet [hours]` | `quiet_until` in state.json | none |

Also file-based (instance dir), not env: `preset.txt` (style), `appearance.txt` (selfie
look), `setting.txt` (where she lives), `places.txt`, `interests.txt`, `day.txt` (day
context), `memories.txt`, `payments.json`, `reminders.json`, `owner_chat.txt`.

## Per-instance vs shared (common.env) in practice

**Always per-instance (NEVER_SHARE-enforced or identity-bound):** `TELEGRAM_BOT_TOKEN`,
`CHARACTER_CARD`, `BOT_HOME`. **Per-character by nature:** `TTS_VOICE`, `SELFIE_BASE`,
sampling knobs (TEMPERATURE/TOP_P — see the per-character table in .env.example),
`SAFETY_RESOURCES`-style locale text if characters differ, WEATHER_*/`TIMEZONE` if they
live in different places, and anything the owner tuned for one bot only (`EMBED_MODEL`
is per-bot .env per CLAUDE.md).

**Naturally fleet-wide (common.env candidates):** `NANOGPT_API_KEY`, `INWORLD_API_KEY`,
`GEMINI_API_KEY`, `NANOGPT_BASE`, model defaults, feature flags, GARMIN_* (it's the one
owner's watch), timeouts. Don't decide by hand — `migrate_common_env.py` only centralizes
keys whose values are ALREADY identical across every bot's .env, and it backs up first.

## Checklist: adding a new config axis

1. **Read it once at module level** with `os.getenv("NEW_VAR", "<sane default>")` next to
   its subsystem's constants block in bot.py (match the neighborhood: bool flags use the
   `not in ("0", "false", "no", "off")` idiom; keep the trailing one-line comment style).
   The default must make the feature safe with no .env edits anywhere.
2. **Document it in `.env.example`** in the matching section, commented out, with the code
   default shown. This is the step people skip — it's why 79 vars are undocumented today.
   Never rename a var without updating .env.example in the same commit (see e9e3880 for
   what drift costs).
3. **Decide per-instance vs common.env** (see previous section) and say so in the
   .env.example comment if it's clearly one or the other.
4. **Deploy note for the owner:** bot.py ships via `bash ~/telegram-bot/update-all.sh`
   (auto-deploys code only). Any actual `.env` value change is MANUAL, per bot, on the
   device, plus a restart — no automation may touch `.env` files. Tell the owner exactly
   which bots need the new line, or "none, the default is fine".
5. **If user-facing**, mention it in `telegram-companion-bot/docs/OPS_MANUAL.md`.
6. Before committing: `python -m py_compile telegram-companion-bot/bot.py`, and re-run the
   parity check below so the doc'd/undoc'd counts stay honest.

## Provenance and maintenance

Certified 2026-07-02 against commit `faea119`. To re-certify (couple of minutes):

```bash
cd telegram-companion-bot
git rev-parse --short HEAD   # compare against faea119; if moved, re-run everything below

# 1. Every env var read by code (one-line calls):
grep -oE 'os\.getenv\(\s*"[A-Z_0-9]+"' bot.py bot_app/core/config.py \
  | grep -oE '"[A-Z_0-9]+"' | tr -d '"' | sort -u > /tmp/code_vars.txt
# Multi-line getenv calls the one-liner misses (verify these are still the only two):
grep -n -A1 'os\.getenv($' bot.py            # SAFETY_RESOURCES, PAYMENTS_ENABLED
printf 'SAFETY_RESOURCES\nPAYMENTS_ENABLED\n' >> /tmp/code_vars.txt
# Sampling vars read via the loop at bot.py:130:
printf 'TEMPERATURE\nTOP_P\nTOP_K\nMIN_P\nFREQUENCY_PENALTY\nPRESENCE_PENALTY\nREPETITION_PENALTY\nMAX_TOKENS\n' >> /tmp/code_vars.txt
sort -u -o /tmp/code_vars.txt /tmp/code_vars.txt

# 2. Every var .env.example mentions (commented or not):
grep -oE '^#? ?[A-Z_0-9]+=' .env.example | sed 's/^#\? \?//; s/=$//' | sort -u > /tmp/example_vars.txt

# 3. Parity:
comm -13 /tmp/code_vars.txt /tmp/example_vars.txt   # PHANTOM: documented but never read — must be empty
comm -23 /tmp/code_vars.txt /tmp/example_vars.txt   # undocumented (79 on 2026-07-02)
wc -l /tmp/code_vars.txt /tmp/example_vars.txt      # 178 / 99 on 2026-07-02

# 4. Spot-check a default before quoting it:
grep -n '"VAR_NAME"' bot.py
```

If the phantom check is non-empty, that's a live bug of the HEARTBEAT_MIN class — fix
.env.example or the code name in the same commit. If counts moved, update the headline
numbers, the affected table rows, and this date stamp.
