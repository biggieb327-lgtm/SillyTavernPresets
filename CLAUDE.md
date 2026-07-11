# SillyTavernPresets — Claude Code Standing Instructions

## What this repo is

A Python Telegram companion bot system (`telegram-companion-bot/bot.py`) running six AI
character instances on Android via Termux. One `bot.py` handles all characters;
instances differ only by directory, `.env`, and SillyTavern v2 character card. The repo
root also archives standalone SillyTavern presets/cards and an unrelated
`voicekit-starter/` project.

## Docs map — read the right doc, not all of them

All under `telegram-companion-bot/` unless noted:

- `CHANGELOG.md` — **read before any bot.py change** (root causes of every shipped
  fix); add an entry after shipping one (root cause first). Skip only for pure
  content edits.
- `ROADMAP.md` — what's next and why; Track 4 is the audit backlog.
- `IMPROVEMENTS_PLAN.md` — release-by-release handoff specs for the Track 4 work.
- `AUDIT-2026-07-10.md` — 2026-07 audit findings, incl. rejected claims (don't re-fix).
- `GROUP_CHAT_DESIGN.md` — **read before touching any GROUP_* code**; survived 4
  adversarial review rounds.
- `OPS_MANUAL.md` — day-to-day operation + the **full bot command reference**.
- `SETUP_GUIDE.md` — standing up a new instance (or use `new-bot.sh`).
- `.claude/memory/operational-log.md` — one row per failure that changed the system.

## Agent operating system (`.claude/`)

Rules here are backed by files that run, not prose:

- **Agents** (`.claude/agents/`): `chief-operator` (opus) orchestrates;
  `builder`/`system-fixer`/`qa-engineer` (sonnet) implement and verify;
  `adversarial-critic`/`eval-designer`/`improvement-analyst` (opus) audit;
  `context-librarian`/`research-scout` (haiku) handle hygiene and lookups.
- **Hooks** (`.claude/hooks/`, wired in `.claude/settings.json`): session-start audit,
  Bash risk guard, evidence logger, budget governor, **delivery gate** (blocks ending a
  turn with a modified bot.py lacking a BOT_VERSION bump, changelog entry, or compile
  evidence), pre-compact handoff writer.
- **Evals** (`.claude/evals/run-evals.sh`): past incidents pinned as runnable checks —
  **run before claiming any change done**. A failure recurring twice earns a new eval.
  Includes a secret scan (repo is public via raw URLs — a committed token is instantly
  leaked) and BOT_VERSION↔changelog sync.
- **CI** (`.github/workflows/evals.yml`): same evals + pytest on every push to
  `main`/`claude/**`. Deploys curl from `main` — a red run on main is a deploy blocker.
- **Improvement loop**: monthly Routine runs `improvement-analyst` over the logs;
  pushes at most one proposal to `claude/improvement-loop`, never to `main`.
- Runtime state in `.claude/.runtime/` is gitignored — never commit it.

## Bot instances

| Session | Directory | Character card |
|---------|-----------|----------------|
| `nora` | `~/telegram-bot/` | `nora.json` |
| `bonnie` | `~/bonnie-bot/` | `bonnie.json` |
| `cass` | `~/cass-bot/` | `cass.json` |
| `emily` | `~/emily-bot/` | `emily_harper.json` |
| `priya` | `~/priya-bot/` | `priya.json` |
| `jules` | `~/jules-bot/` | `jules_nakagawa.json` |

Authoritative instance list = the loop in `update-all.sh`. All share the venv at
`~/telegram-bot/venv/`. `bot.py` lives in `~/telegram-bot/` and takes the instance
directory as `sys.argv[1]`.

## Stack

- Python 3.13+ on Termux/Android (3.14 compat workaround in `main()`, see CHANGELOG
  v2026-07-05.6); `python-telegram-bot >=21.0,<22.0` (async, job-queue)
- NanoGPT — OpenAI-compatible API at `https://nano-gpt.com/api/v1`
- SillyTavern `chara_card_v2` JSON cards
- Repo `biggieb327-lgtm/SillyTavernPresets`; raw URL base
  `https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/`

## Deployment

**Preferred (no shell):** push to `main`, send `/update` to **one** bot (verifies
compile, keeps `bot.py.bak`, swaps the shared file, restarts), then `/restart` to the
others. Verify each with `/audit` (shows BOT_VERSION). **Bump `BOT_VERSION` on every
release** — it's how `/update` detects new versions and `/audit` proves deploys.

**When run-bot.sh changed (shell required)** — `/update` never regenerates the
supervisor:
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/update-all.sh | bash
```

**Card/seed-only update:** `sync-cards.sh`, or curl the card into the instance dir and
rerun `run-bot.sh <dir> <name>`. **.env edit:** edit on-device, then `/restart` that bot.

Full command reference: `OPS_MANUAL.md`. The ops essentials are `/update` `/restart`
`/audit` `/errors [N]` `/backup`.

## Working principles

1. **Ask, don't assume.** When unclear, ask first. Running unattended: pick the most
   reasonable interpretation, proceed, record the assumption.
2. **Simplest solution first.** No flexibility that isn't needed yet.
3. **Don't touch unrelated code** — but surface smells for separate follow-up.
4. **Flag uncertainty explicitly**; small low-risk experiments over confident guessing.
5. **Suggest better approaches** — durable wins over tactical patches are welcome.

## Git workflow

- Develop on `claude/...` branches if useful, but always merge to `main` — deploys and
  doc links pull from `main`.
- Commit real work **before** break-testing evals; revert test injections by
  re-editing, never `git checkout` on a file with uncommitted changes.

## Code invariants (each one paid for in debugging time)

- **bot.py stays a single file.** The whole deploy model depends on it. Recorded
  non-goal; don't propose splitting it.
- **One combined post-reply analysis call** (`post_reply_analysis`: mood + note +
  memory + any future extraction as extra JSON keys). Never add a per-message side
  call — side calls compete with user-facing replies for phone bandwidth.
- **Memory provenance:** generated content (day events, reflections) must never enter
  user-fact stores unlabeled — the `[own-day …]` tag + per-consumer handling is the
  template. Violating this caused the 2026-07-10 hallucinated-memories bug.
- **Concurrency:** state serialization happens on the event loop only (worker threads
  hand `save_state` back via `call_soon_threadsafe`); never iterate live state dicts
  from a worker thread; never run bare `requests` calls in an async handler (use
  `asyncio.to_thread`); never hold the group-ledger flock across an `await`.
- **Streaming error bodies must be force-read (`_ = resp.content`) before
  `raise_for_status()`** or 400s arrive empty and undiagnosable (`_do_request` does
  this; keep the pattern).
- Model output passes through `_strip_thinking` + `_strip_native_tool_calls` +
  `_fix_mojibake` at the `_do_request` choke point — new response paths must too.
- PTB's `run_polling()` silently overrides `signal.signal()` handlers — shutdown work
  goes in `post_shutdown` (see CHANGELOG v2026-07-05.8).
- Group chats: commands are default-deny (`GROUP_ALLOWED_COMMANDS = {"chatid"}`) and
  `_group_deliver` is allowlist-built — both pinned by CI evals; widen only with the
  eval in the same commit.

## Models & config constraints

Full documented template: `telegram-companion-bot/.env.example`. The constraints that
aren't obvious from it:

- `NANOGPT_MODEL=zai-org/glm-5:thinking` (chat), `REACTION_MODEL` cheap+fast
  (`glm-4.7-flash`). `SUMMARY_MODEL` defaults to `NANOGPT_MODEL` (the full chat
  model) — not flash.
- `FALLBACK_MODEL` must be roleplay-capable: `anthracite-org/magnum-v4-72b`
  (recommended) or `Sao10K/L3.3-70B-Euryale-v2.3`. Used on 400/429/5xx/timeout;
  `call_nanogpt` = 2 attempts/model, 2s/4s backoff, 150s primary budget.
- `DOCUMENT_MODEL` must be an **instruction** model (`deepseek/deepseek-v4-flash`) —
  a roleplay model will perform the character card it's analyzing.
- `VISION_MODEL` must be multimodal (`zai-org/glm-4.6v`) — the chat default rejects
  images with 400.
- `STREAM_TIMEOUT` (90s) is max silence between SSE chunks (stall detection);
  `REQUEST_TIMEOUT` (120s) for non-streaming. 30s proved too tight on a phone.
  Models that reject streaming are auto-retried non-streaming and cached in
  `_no_stream_models`.
- **Inworld voice (Emily):** TTS voice and model must come from the same engine — an
  Inworld voice ID sent to an OpenAI-style model 400s. `INWORLD_API_KEY` switches the
  engine; `TTS_VOICE` is then an Inworld voice ID.
- **WSDOT traffic (Emily):** `WSDOT_API_KEY` + `TRAFFIC_RADIUS_MILES` +
  `TRAFFIC_POLL_MINUTES`.
- **Group-chat pilot (Priya + Jules, experimental):** read `GROUP_CHAT_DESIGN.md`
  first — Telegram never delivers one bot's messages to another bot, so the feature
  runs on a shared flock'd ledger + atomic claim files. Fleet-wide even when unset:
  bots ignore all group chats (only `/chatid` answers) and `set_owner` refuses group
  chat_ids. Enable with `GROUP_MODE=1` + `GROUP_ALLOWED_CHATS` (fail closed) +
  `GROUP_PEERS`; loop caps `GROUP_BOT_CHAIN_MAX=2`, `GROUP_DAILY_BOT_BUDGET=30`.
  BotFather privacy must be DISABLED for pilot bots (re-add to group after changing).
  One-time on-device check: `python bot.py ~/priya-bot --claim-test` (two PASS lines).
- Bad numeric `.env` values no longer crash the bot (v2026-07-10.2): `_env_int`/
  `_env_float` fall back to defaults with a `[config]` warning — check logs after
  editing an `.env`.

## Continuity features (all characters)

- **Date-aware note follow-ups**: datable user mentions stored with `(due YYYY-MM-DD)`
  in `user_notes.txt`; a daily job (`NOTE_FOLLOWUP_TIME`, default 18:00) asks how it
  went after the date, then marks `(asked …)`. Respects quiet hours + nudge budget.
- **Multi-day life threads**: midnight rotation feeds yesterday's `day.txt` into
  today's event generation. Archived days are provenance-tagged (`[own-day …]`) so her
  own fiction is never presented as shared memory.
- **Shared world**: the `WORLD_GENERATOR=1` instance (nora) writes `world.txt` at
  midnight; all instances read it — same weather/backdrop fleet-wide.

## Character notes

**Nora** (`nora.json` / root `caa16137-nora.json`) — 25, bike messenger, Chicago South
Side → Seattle. Casual register; curious by talking, not interrogating. Mormor died a
year ago; mother left at 8. Three months into something with user she won't name.
Lorebook: Ingrid/jacket, Mother, Messenger work, The toothbrush, Money/The City,
Religion/Politics.

**Bonnie** (`bonnie.json`) — libertarian gremlin housewife; chaotic surface over
abandonment terror. Personality order: Friction → Core → OCEAN → Energy States →
Surface. Four-state calm opening in first_mes.

**Cass** (`cass.json`) — writing collaborator / developmental editor; send a `.json`
card for substantive critique (uses `DOCUMENT_MODEL`). Forward-momentum rule: leads
with fixes.

**Emily** (`emily_harper.json`) — vision model + WSDOT traffic integration
(`/traffic`, `/incidents`, live-location alerts) + Inworld voice.

**Priya** (`priya.json`) — 26, fintech software engineer, Bellevue WA (moved from
Austin 2026-07). Tamil-American, NJ-raised, Rutgers CS. Sardonic, lowercase, never
performative; quietly lonely. Her atlas references real Eastside/Seattle places —
keep edits geographically consistent with Bellevue.

**Jules** (`jules_nakagawa.json`) — treats attention like a contact sport; files
everything you say and deploys it later, flat and precise. Derby-culture "chirping"
register — when she actually likes you she gets *meaner*, not warmer. Group-chat
pilot pair with Priya.

## Termux / Android quirks

- **Phantom process killer (the big one).** Android 12+ silently SIGKILLs background
  processes when >32 exist system-wide; 6 bots sit at that limit. Signature:
  `STARTUP AUDIT` lines piling up in `/errors` with **no** `[shutdown] graceful stop`
  line before them (SIGKILL can't be caught). One-time fix via adb:
  `adb shell settings put global settings_enable_monitor_phantom_procs false`
  plus Termux battery → Unrestricted. **The setting reverts after an Android OS
  update/factory reset** — if silent restarts return, check
  `settings get global settings_enable_monitor_phantom_procs` before debugging
  anything else. Conversely, repeated *clean* `exited (code 0)` restarts WITH a
  graceful-stop line are NOT the phantom killer — that's a real SIGTERM, most likely
  an OEM battery manager (see dontkillmyapp.com for the manufacturer).
- run-bot.sh launches `~/telegram-bot/venv/bin/python` **explicitly** — bare `python`
  crash-loops on `ModuleNotFoundError` when the venv isn't on tmux's PATH. Never
  regress this.
- **`pkg upgrade` hazards:** android-tools can break (libprotobuf symbol —
  `pkg reinstall android-tools`); a Python **minor**-version bump breaks the shared
  venv — rebuild with `python -m venv --clear ~/telegram-bot/venv &&
  ~/telegram-bot/venv/bin/pip install -r ~/telegram-bot/requirements.txt`
  (`requirements.txt` is the single source of truth — hand-typing the list caused the
  tzdata bug). Pillow may need `pkg install libjpeg-turbo zlib freetype` first, or
  `pkg install python-pillow` + `--system-site-packages` venv. A big Python jump
  (3.13→3.14) can outrun PTB v21's deprecated `asyncio.get_event_loop()` call —
  bot.py works around it in `main()` (v2026-07-05.6); if worse appears, hold Termux's
  `python` package back.
- **Don't drop `tzdata`** — Termux has no system tz database; without it `ZoneInfo`
  silently degrades to naive local time, and a stored tz-aware reminder vs naive
  `now()` once crashed startup fleet-wide (`schedule_reminder` now normalizes
  defensively, v2026-07-05.5 — but reinstall tzdata rather than rely on that).
- `/tmp` is not writable — use `~/` for temp files.
- Stale `bot.pid` after a crash: delete it before restarting (run-bot.sh also clears).
- `tmux kill-session -t <name>` before reusing a session name; `httpx.ConnectError`
  at startup = transient network blip, restart the session.
- Wake lock is acquired automatically (`termux-wake-lock`). The supervisor writes
  `bot.log` via `>>` (no tee — fewer processes for the phantom limit), trims at 5 MB;
  `errors.log` rotates at 2 MB.

## Debugging protocol (lessons learned)

1. **Evidence before fixes.** Get `/errors` (or `tail -50 ~/<dir>/bot.log`) and the
   exact error text first. Three rounds of speculative fixes once lost to one pasted
   log line.
2. **Differential diagnosis.** Which bots work, which don't — the broken one's delta
   (.env, model, features) is usually the answer.
3. **Opaque error → instrument first.** Make the failure self-describing, deploy,
   reproduce, then fix.
4. **A bot that can't answer `/errors` is a startup crash** — go to `bot.log`; the
   supervisor lines show exit codes and cadence.
5. **Verify every deploy** with `/audit`.

## Monitoring

- **Restart-storm self-report**: `_self_audit` (every 30 min) DMs the owner at ≥3
  `STARTUP AUDIT` lines/hour (2h cooldown). Graceful-stop line present = catchable
  SIGTERM (battery manager or watchdog); absent = SIGKILL (phantom killer).
- **Dead man's switch**: set `HEALTHCHECK_URL` per instance (healthchecks.io, 30 min
  period + 15 min grace) — silence alerts on bot-down AND phone-dead.
- **`backup-all.sh`** (cron, on-device): nightly state archive to shared storage,
  `.env` excluded, 14-day retention, optional rclone. Curl-installed once; not managed
  by update-all.sh.
- **`watchdog.sh`** (on-device at `~/telegram-bot/watchdog.sh`; source now in repo,
  still installed manually): relaunches vanished tmux sessions AND bots whose `.alive`
  heartbeat is stale (>300s). **bot.py must touch `.alive` every 60s** (`_touch_alive`
  job) — if that job is ever removed, watchdog restarts the whole fleet forever (cost
  a full debugging session, 2026-07-05). `watchdog.log` states its reason before every
  relaunch — check it first.

## Repo layout

```
/
├── CLAUDE.md                        # this file
├── telegram-companion-bot/
│   ├── bot.py                       # single codebase, all instances
│   ├── run-bot.sh / update-all.sh   # start one / redeploy all
│   ├── watchdog.sh / backup-all.sh  # on-device helpers (curl-installed once)
│   ├── fleet-status.sh / sync-cards.sh / new-bot.sh   # ops tooling
│   ├── requirements.txt             # single source of truth for pip installs
│   ├── .env.example                 # documented config template
│   ├── preset.txt                   # shared voiceprint/texting-style preset
│   ├── *.json                       # character cards (bot copies)
│   ├── {bonnie,cass,emily,nora,priya}/   # per-character seed files
│   ├── meme_templates/ + fonts/     # shared meme assets
│   ├── tests/                       # pytest (pure-logic regression suite)
│   ├── deploy/                      # VPS: bot@.service, install-vps.sh, MIGRATION.md
│   └── *.md                         # docs — see Docs map above
├── caa16137-nora.json               # SillyTavern archive copy
├── voicekit-starter/                # separate project (not the bot)
└── [other SillyTavern presets/cards]
```
