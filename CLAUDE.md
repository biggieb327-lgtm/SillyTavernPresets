# SillyTavernPresets — Claude Code Standing Instructions

## What this repo is

A Python Telegram companion bot system (`telegram-companion-bot/bot.py`) running multiple AI character instances on Android via Termux. One `bot.py` handles all characters; instances are differentiated by their directory, `.env`, and SillyTavern v2 character card JSON. The repo also stores character card files (`.json`) at the root level for archiving and sharing.

---

## Bot instances

| Session | Directory | Character card |
|---------|-----------|----------------|
| `nora` | `~/telegram-bot/` | `nora.json` |
| `bonnie` | `~/bonnie-bot/` | `bonnie.json` |
| `cass` | `~/cass-bot/` | `cass.json` |
| `emily` | `~/emily-bot/` | `emily_harper.json` |
| `priya` | `~/priya-bot/` | `priya.json` |
| `jules` | `~/jules-bot/` | (per its `.env`) |

The authoritative instance list is the loop in `update-all.sh`. All instances share the venv at `~/telegram-bot/venv/`. `bot.py` always lives in `~/telegram-bot/` and is passed an instance directory as `sys.argv[1]`.

---

## Stack

- **Runtime:** Python 3.13, Termux on Android
- **Library:** `python-telegram-bot >=21.0,<22.0` (async, with job-queue)
- **AI backend:** NanoGPT — OpenAI-compatible API at `https://nano-gpt.com/api/v1`
- **Character format:** SillyTavern `chara_card_v2` JSON
- **Repo:** `biggieb327-lgtm/SillyTavernPresets`
- **Raw URL base:** `https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/`

---

## Deployment

### Preferred: from Telegram, no shell needed
After pushing to `main`, send `/update` to **one** bot — it downloads bot.py, refuses to
install anything that doesn't compile, keeps a `bot.py.bak`, swaps the shared file, and
restarts itself. Then send `/restart` to the other bots (bot.py is shared, so they just
need to reload it). Verify each with `/audit` — it shows `BOT_VERSION`.

**Bump `BOT_VERSION` in bot.py on every release** — it's how `/update` detects a new
version and how `/audit` proves a deploy took.

### When run-bot.sh (the supervisor) changed — shell required
`/update` and `/restart` never regenerate the supervisor script (`.supervise.sh` is baked
by run-bot.sh at launch). Any change to `run-bot.sh` needs one shell run of:
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/update-all.sh | bash
```
(update-all.sh pulls bot.py AND run-bot.sh, then restarts every instance.)

### Card-only update (no bot.py change)
```bash
curl -fsSL https://raw.githubusercontent.com/.../nora.json -o ~/telegram-bot/nora.json
bash ~/telegram-bot/run-bot.sh ~/telegram-bot nora
```

### Edit an instance .env
```bash
nano ~/emily-bot/.env
```
Then `/restart` that bot from Telegram — it picks up the .env on relaunch.

---

## Working principles

1. **Ask, don't assume.** If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements. When running unattended, pick the most reasonable interpretation, proceed, and record the assumption rather than blocking.
2. **Simplest solution first.** Implement the simplest solution for simple problems, better solutions for harder problems. Do not over-engineer or add flexibility that isn't needed yet.
3. **Don't touch unrelated code** — but do surface bad code or design smells so we can address them as a separate issue.
4. **Flag uncertainty explicitly.** If unsure, see rule 1. If appropriate, run a small, localised, low-risk experiment and bring the hypothesis and results to discuss. Confidence without certainty causes more damage than admitting a gap.
5. **Suggest better approaches.** Always open to ideas with long-lasting impact over tactical changes — don't hesitate to propose them.

---

## Git workflow

- Push all changes to `main`
- Development may happen on a feature branch (`claude/...`) but always merge to `main` before deploying, since the curl commands pull from `main`
- Commit messages should be descriptive; co-author line is added automatically by Claude Code

---

## Key .env variables

```
TELEGRAM_BOT_TOKEN=
NANOGPT_API_KEY=
NANOGPT_MODEL=zai-org/glm-5:thinking      # primary chat model
FALLBACK_MODEL=anthracite-org/magnum-v4-72b  # roleplay fallback on 5xx/timeout
VISION_MODEL=zai-org/glm-4.6v             # must support image input
DOCUMENT_MODEL=deepseek/deepseek-v4-flash  # instruction model for card analysis — NOT roleplay-tuned
SUMMARY_MODEL=zai-org/glm-4.7-flash
REACTION_MODEL=zai-org/glm-4.7-flash
CHARACTER_CARD=nora.json
ALLOWED_USERS=                             # comma-separated Telegram user IDs
STREAM_TIMEOUT=90                          # max silence between streamed chunks (s)
MAX_TOKENS=2048
NOTE_FOLLOWUP_TIME=18:00                   # when dated user notes get followed up
```

**Emily only (WSDOT traffic):**
```
WSDOT_API_KEY=
TRAFFIC_RADIUS_MILES=10
TRAFFIC_POLL_MINUTES=10
```

**Voice via Inworld (Emily):** TTS voice and model must come from the same engine — an
Inworld voice ID sent to an OpenAI-style model 400s. Setting `INWORLD_API_KEY` switches
voice replies to api.inworld.ai:
```
INWORLD_API_KEY=                           # base64 runtime key (Basic auth)
INWORLD_TTS_MODEL=inworld-tts-2
TTS_VOICE=Zadieova                         # Inworld voice ID (incl. cloned voices)
```

---

## NanoGPT connection notes

- Responses are **streamed** (SSE); `STREAM_TIMEOUT` (default 90s) is the max silence
  between chunks — stall detection, not total time. Non-streaming requests use
  `REQUEST_TIMEOUT` (default 120s). 30s proved too tight on a phone connection.
- `call_nanogpt`: 2 attempts per model with 2s/4s backoff, 150s wall-clock budget on the
  primary before forcing fallback. 400/429/5xx/timeouts are all fallback-eligible.
- Models that reject streaming get an automatic non-streaming retry and are cached in
  `_no_stream_models` for the process lifetime.
- **Streaming error bodies must be force-read (`resp.content`) before `raise_for_status()`**
  — otherwise a 400 arrives with an empty body and is undiagnosable. This bug cost three
  fix rounds; `_do_request` handles it now. Keep the pattern if touching that code.
- Per user message there is ONE combined post-reply analysis call (`post_reply_analysis`:
  mood + user note + NPC memory in one JSON response) — don't reintroduce separate calls;
  side calls compete with user-facing replies for phone bandwidth.
- `FALLBACK_MODEL=anthracite-org/magnum-v4-72b` is the recommended roleplay fallback; `Sao10K/L3.3-70B-Euryale-v2.3` is a solid alternative
- `DOCUMENT_MODEL` must be an instruction model — roleplay-tuned models will perform the character card they're analyzing
- `VISION_MODEL` must be multimodal — the chat default (`glm-5:thinking`) rejects images
  with 400; bot.py defaults `VISION_MODEL` to `zai-org/glm-4.6v` for this reason

---

## Continuity features (all characters)

- **Date-aware note follow-ups**: when the user mentions something datable ("interview Tuesday"), the note is stored with a `(due YYYY-MM-DD)` suffix in `user_notes.txt`; a daily job (default 18:00, `NOTE_FOLLOWUP_TIME`) proactively asks how it went once the date passes, then rewrites the marker to `(asked ...)`. Respects quiet hours and the nudge budget; max one per day.
- **Multi-day life threads**: the midnight day-context rotation feeds yesterday's `day.txt` into today's event generation, so one of today's events may continue or resolve a hanging thread instead of the character's life resetting daily.

## Character notes

**Nora** (`nora.json` / `caa16137-nora.json`) — 25, bike messenger, Chicago South Side, Seattle. Casual conversation register. Curious and conversational, shows it by talking not interrogating. Mormor (grandmother) died a year ago; mother left at 8. Three months into something with user she won't name. Friction section describes her fear/reset pattern. Lorebook has 6 entries: Ingrid/jacket, Mother, Messenger work, The toothbrush, Money/The City, Religion/Politics.

**Bonnie** (`bonnie.json`) — libertarian gremlin housewife, chaotic surface over abandonment terror underneath. Personality order: Friction → Core → OCEAN → Energy States → Surface. Sexual behavior written as observable patterns. Four-state calm opening in first_mes.

**Cass** (`cass.json`) — writing collaborator / developmental editor. Analysis-mode bot; send a `.json` card and she gives substantive critique. Uses `DOCUMENT_MODEL` for card analysis. Has a forward-momentum rule: leads with fixes, advances conversation rather than circling.

**Emily** (`emily_harper.json`) — has `VISION_MODEL=zai-org/glm-4.6v`. Has WSDOT Western Washington traffic integration: `/traffic`, `/incidents`, live location → proactive nearby incident alerts every 10 min.

---

## Termux / Android quirks

- **Phantom process killer (the big one).** Android 12+ silently SIGKILLs background
  processes when >32 exist system-wide; 6 bots × several processes sits at that limit.
  Signature: `STARTUP AUDIT` lines piling up in `/errors` with **no** "Received signal"
  line before them (a catchable SIGTERM would log one; SIGKILL can't). Fix (one-time,
  via adb — wireless debugging from Termux itself works):
  `adb shell settings put global settings_enable_monitor_phantom_procs false`
  plus Termux battery → Unrestricted. **The setting reverts after an Android OS update
  and factory reset** — if silent restarts ever return, check
  `settings get global settings_enable_monitor_phantom_procs` before debugging anything.
- run-bot.sh launches with `~/telegram-bot/venv/bin/python` **explicitly** — bare
  `python` only works if the venv happens to be on PATH when tmux starts; otherwise the
  bot crash-loops on `ModuleNotFoundError: requests`. Never regress this.
- `pkg upgrade` hazards: android-tools can break with a libprotobuf symbol error
  (`pkg reinstall android-tools` fixes); a Python **minor**-version bump breaks the
  shared venv — rebuild with
  `python -m venv --clear ~/telegram-bot/venv && ~/telegram-bot/venv/bin/pip install "python-telegram-bot[job-queue]>=21,<22" requests python-dotenv tzdata`
  then run update-all.sh. **Don't drop `tzdata`** — Termux has no system IANA timezone
  database, so `zoneinfo.ZoneInfo(TIMEZONE)` needs the pip package or it silently falls
  back to `TZ = None`. That alone won't crash anything, but a *stored* tz-aware
  timestamp (e.g. a reminder's `due`) compared against a now-naive `datetime.now()`
  raises `TypeError: can't compare offset-naive and offset-aware datetimes` — and if
  that comparison happens during startup (re-arming reminders), it takes the whole bot
  down before it can even answer Telegram. `schedule_reminder` normalizes this
  defensively as of v2026-07-05.5, but a missing `tzdata` still degrades every
  timezone-dependent feature (quiet hours, proactive windows, day rotation) to raw
  device local time — reinstall it rather than rely on the defensive fix alone.
- `/tmp` is not writable — use `~/` for temp files
- Network goes stale during long model waits — `_keep_typing` swallows exceptions; `send_bubbles` retries with backoff
- `tmux kill-session -t name` before `new-session` with the same name or you get "duplicate session" error
- Stale `bot.pid` lock file after a crash: delete `~/instance-dir/bot.pid` before restarting (run-bot.sh also clears it)
- `httpx.ConnectError` on startup or mid-session = transient network blip; kill and restart the session
- Termux wake lock is acquired automatically on startup via `termux-wake-lock`
- The supervisor writes `bot.log` via `>>` redirect (no tee — fewer processes for the
  phantom limit) and trims it to 1 MB when it exceeds 5 MB; `errors.log` rotates at 2 MB

---

## Debugging protocol (lessons learned)

1. **Evidence before fixes.** Get `/errors` output (or `tail -50 ~/<instance>-bot/bot.log`)
   and the exact error text before proposing anything. Three rounds of speculative fixes
   lost to one pasted log line in this project's history.
2. **Differential diagnosis.** Always establish which bots work and which don't — what's
   different about the broken one (its .env, its model, its extra features) is usually
   the answer.
3. **When the error is opaque, instrument first.** Make the failure self-describing
   (include the API error body, the model name), deploy, reproduce, then fix the real
   cause. The vision-400 bug was unsolvable until the error message included the body.
4. **A bot that can't answer `/errors` is a startup crash** — go to `bot.log` on the
   phone; the supervisor log lines show exit codes and restart cadence.
5. **Verify every deploy** with `/audit` (shows `BOT_VERSION`, uptime, error counts).

---

## Monitoring

Two layers, no supervisor bot (a same-phone watchdog shares fate with what it watches):

- **Restart-storm self-report**: `_self_audit` (every 30 min, first run 90s after boot)
  counts `STARTUP AUDIT` lines in errors.log; ≥3 in an hour → DMs the owner with the
  phantom-killer hint. 2h cooldown between alerts. A revived bot tells on its killer.
- **Dead man's switch**: if `HEALTHCHECK_URL` is set in an instance `.env`, `_self_audit`
  GETs it every 30 min. Pair with healthchecks.io (free): one check per bot, 30 min
  period + ~15 min grace, alert channel = Telegram/email. Silence = the alert — covers
  bot-fully-down and phone-dead, which nothing on the phone can report.

---

## Bot commands reference (quick)

| Command | What it does |
|---------|--------------|
| `/traffic` | W. WA congestion (scoped to user if location shared) |
| `/incidents` | Open WSDOT alerts (filtered nearby if live location active) |
| `/memory` | View long-term + recent memory |
| `/selfie [hint]` | Generate a selfie |
| `/vibe <name> [Xh]` | Set timed vibe |
| `/remindme <when> <msg>` | One-off reminder |
| `/cron <schedule> \| <instruction>` | Recurring task |
| `/heartbeat` | Trigger proactive message now |
| `/model` | Show active models |
| `/usage` | NanoGPT token usage |
| `/addmem <text>` | Manually add an NPC/world memory |
| `/mems` | List all stored memories |
| `/delmem <keyword or #>` | Remove a memory by keyword or number |
| `/audit` | Self-audit: version, uptime, error counts, state/disk health |
| `/errors [N]` | Show last N lines of errors.log (default 20, max 50) |
| `/update` | Self-deploy: pull latest bot.py from main, verify, restart (per instance; `force` to reinstall same version) |
| `/restart` | Clean restart via supervisor — picks up .env edits and a swapped bot.py |
| `/backup` | Send state.json, memories.txt, user_notes.txt, setting.txt, reminders.json, payments.json to chat (.env excluded) |

---

## Repo layout

```
/
├── CLAUDE.md                          # this file
├── telegram-companion-bot/
│   ├── bot.py                         # single bot codebase, all instances
│   ├── update-all.sh                  # curl + restart all bots
│   ├── run.sh                         # start nora (default instance)
│   ├── run-bot.sh                     # start any named instance
│   ├── .env.example                   # documented config template
│   ├── nora.json                      # Nora character card (bot copy)
│   ├── bonnie.json
│   ├── cass.json
│   ├── emily_harper.json
│   ├── priya.json
│   ├── OPS_MANUAL.md
│   ├── PROJECT_CONTEXT.md
│   └── PROJECT_INSTRUCTIONS.md
├── caa16137-nora.json                 # Nora card (SillyTavern archive copy)
└── [other SillyTavern presets/cards]
```
