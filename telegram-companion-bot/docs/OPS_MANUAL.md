# Companion Bot — Operations Manual

Day-to-day operation reference for a running bot.

---

## Starting & Stopping

### Update bot.py + bot_app/ and restart everything (normal day-to-day operation)
```bash
bash ~/telegram-bot/update-all.sh
```
Pulls the latest `bot.py`/`bot_app/`/helper scripts from the `~/stp-deploy` git clone, then
restarts every deployed instance (`nora`, `bonnie`, `cass`, `emily`, `jules`, and `priya` if her
directory exists) supervised under `run-bot.sh`. This is the one command to run after any code
change — see the repo-root `CLAUDE.md` for the full deploy workflow.

### Start (or restart) a single bot, supervised
```bash
bash ~/telegram-bot/run-bot.sh ~/nora-bot nora
```
Kills any existing session/process for that instance, then relaunches it under a supervisor loop
that auto-restarts it if it ever exits (crash, OOM kill, etc.) and rotates `bot.log` at ~5MB.

### Run a single bot in the foreground (debugging only, not supervised)
```bash
source ~/telegram-bot/venv/bin/activate
python ~/telegram-bot/bot.py ~/nora-bot
```

### Attach to a running session
```bash
tmux attach -t nora
tmux attach -t emily
# etc.
```

### Detach (leave bot running)
Press `Ctrl+B`, then `D`.

### Stop one bot
```bash
tmux kill-session -t nora
```
Note: a session under `run-bot.sh`'s supervisor will restart itself after a few seconds unless you
also kill the supervisor process for that instance.

### Stop all bots
```bash
pkill -f bot.py
```

---

## Commands Reference

### Conversation
| Command | What it does |
|---|---|
| `/start` | Reset history and send the character's opening message |
| `/clear` | Wipe conversation history (keeps long-term memory) |
| `/status` | Dashboard: mood, life arc, today's context, user notes, weather, last chat |
| `/recap` | 2–3 sentence summary of recent conversation |
| `/help` | Show all available commands |
| `/menu` | Open the inline button shortcut menu |
| `/diag` | Health/feature report: what's on, embedded counts, Garmin status, recent log errors |
| `/chatid` | Show your Telegram chat ID (works even if you're not in `ALLOWED_USERS` yet) |

### Memory — long-term facts/summary (`/memory`, `/forget`)
| Command | What it does |
|---|---|
| `/memory` | View long-term and recent memory summaries + facts |
| `/remember <fact>` | Save a fact to long-term memory |
| `/forget` | Wipe all long-term + recent memory (or `/forget <keyword>` to remove matching facts) |
| `/correct <wrong> => <right>` | Remove a wrong memory and optionally replace it, routed to the correct store |
| `/recall <keyword>` | Search memory for a keyword |
| `/exportmemory` | Download a full memory export as text |
| `/milestones` | View relationship milestones |
| `/pin <fact>` | Pin something that's always in context |
| `/pinned` | List pinned memories |
| `/unpin <n>` | Remove a pinned memory by number |
| `/boundary <text>` | Add a soft boundary note |
| `/boundaries` | List boundaries |
| `/backup` | Sends `state.json`/`reminders.json`/`payments.json` to you (owner-only) |

### Memory — NPC/world notes (`/mems`, `/delmem`)
A separate, keyword-retrieved store for facts about third parties (NPCs, relationships) — distinct
from the long-term facts above. If `/delmem` says nothing matched, the keyword is probably in the
other store — try `/forget` instead (and vice versa).

| Command | What it does |
|---|---|
| `/addmem <text>` | Manually add an NPC/world memory |
| `/mems` | List all NPC/world memories |
| `/delmem <keyword or n>` | Remove an NPC/world memory by keyword or list number |
| `/episodes <query>` | Search archived past conversation moments (requires `EMBED_MODEL` + `EPISODIC_RECALL`) |

### Context Files
These files shape what the character knows and references. All are editable from Telegram.

| Command | What it does |
|---|---|
| `/life [text]` | View or replace the character's current life arc (long-running context) |
| `/life add <text>` | Append a line to the life arc |
| `/people [text]` | View or replace the people in her life |
| `/people add <text>` | Append a person or relationship note |
| `/projects [text]` | View or replace her ongoing projects |
| `/projects add <text>` | Append a project |
| `/schedule [text]` | View or replace her weekly schedule |
| `/schedule add <text>` | Append a schedule entry |
| `/today <note>` | Append a mid-day note (what's happening today) |
| `/note <text>` | Manually add something to what she knows about you |
| `/notes` | List your auto-collected notes, numbered |
| `/notes del <n>` | Remove a specific note by number |
| `/notes clear` | Wipe all user notes |

### Mood & Modes
| Command | What it does |
|---|---|
| `/mood` | Check her current mood |
| `/vibe <name> [Xh]` | Set a timed vibe: `cozy` / `flirty` / `serious` / `chaotic` / `low-energy` / `playful` / `chill` / `in-person` |
| `/vent` | Toggle vent mode (listening only, no advice) |
| `/energy <level>` | Set your energy: `high` / `low` / `crash` |

### Wardrobe
| Command | What it does |
|---|---|
| `/wardrobe` | List saved outfits |
| `/addoutfit <desc>` | Add an outfit description |
| `/outfit <n>` | Set current outfit (used in selfie generation) |
| `/deloutfit <n>` | Remove an outfit |

### Selfie
| Command | What it does |
|---|---|
| `/selfie [hint]` | Generate a selfie (optional scene hint) |

### Reading & News (offline-life features)
| Command | What it does |
|---|---|
| `/reading` | View what she's read lately (requires `SEARCH_ENABLED`) |
| `/readnow` | Trigger an interest-topic reading pass now |
| `/news` | View recent things that happened in her own life |
| `/newsnow` | Trigger an offline-life event now |

### Health (Garmin — only on bots with `GARMIN_EMAIL`/`GARMIN_PASSWORD` set)
| Command | What it does |
|---|---|
| `/health` | Latest cached Garmin snapshot (sleep, HR, steps, body battery, stress) |
| `/healthnow` | Force a fresh Garmin pull |
| `/stress` | Current stress-monitoring status and threshold |

### Proactive Messages
| Command | What it does |
|---|---|
| `/heartbeat` | Trigger a proactive check-in now |
| `/nudges [n]` | Show today's proactive message budget, or set the daily limit (`/nudges 0` = unlimited) |
| `/quiet <h>` | Pause proactive messages for X hours (e.g. `/quiet 3`) |
| `/quiet off` | Cancel quiet mode early |

### Voice
| Command | What it does |
|---|---|
| `/voice` | Toggle voice (TTS) replies on/off |

### Reminders
| Command | What it does |
|---|---|
| `/remindme <when> <msg>` | One-off reminder. When: `30m`, `2h`, `18:30`, `tomorrow 9:00` |
| `/setreminder HH:MM <msg>` | Daily recurring reminder at a fixed time |
| `/reminders` | List all pending reminders |
| `/delreminder <n>` | Cancel a reminder by list number |

### Recurring Tasks (Cron)
| Command | What it does |
|---|---|
| `/cron <schedule> \| <instruction>` | Add a recurring task. Schedule: `daily HH:MM`, `weekly Mon HH:MM` |
| `/crons` | List recurring tasks |
| `/crondel <id>` | Remove a recurring task |

### Payments (if enabled)
| Command | What it does |
|---|---|
| `/addpayment <name> <amount> <day>` | Add a monthly bill |
| `/addevery <name> <amount> <days>` | Add a bill recurring every N days |
| `/payments` | List all bills |
| `/delpayment <n>` | Remove a bill |
| `/editpayment <n> <field> <value>` | Edit a bill field |
| `/week` / `/remindpayments` | Payment summary / reminder for the current week |

### Traffic (if `TRAFFIC_ENABLED` and a location has been shared)
| Command | What it does |
|---|---|
| `/traffic` | Current traffic-polling status |
| `/incidents` | Recent traffic incidents near the shared location |

### Settings & Info
| Command | What it does |
|---|---|
| `/card` | Show info about the active character card |
| `/setcard <file>` | Switch the character card (file must exist in the bot's directory) |
| `/model` | Show active models |
| `/setmodel <field> <value>` | Change a model (fields: `chat`, `summary`, `vision`, `reaction`, `mood`, `fallback`) |
| `/settings` | Show current settings |
| `/usage` | Token usage stats |

---

## Context Files

The bot reads a set of plain-text files from the character's directory to build context for each message. All can be edited directly in Termux or managed via Telegram commands.

| File | Command | Purpose |
|---|---|---|
| `life.txt` | `/life` | Character's current story arc — what's going on in her life long-term |
| `people.txt` | `/people` | People in her life: names + one-line relationship notes |
| `projects.txt` | `/projects` | Ongoing projects or things spanning multiple days |
| `schedule.txt` | `/schedule` | Weekly routine by day name; today's section is auto-extracted |
| `day.txt` | `/today` | Generated each morning; append mid-day notes with `/today` |
| `user_notes.txt` | `/note`, `/notes` | Auto-collected notes about you; also manually added with `/note` |
| `places.txt` | — | Atlas of real local places she might naturally reference |

### Atlas file
Each character directory can have a `places.txt` (or override via `ATLAS_FILE=` in `.env`). One place per line — the bot samples a random handful each message. Lines starting with `#` are comments.

### User notes (auto-collection)
After each message you send, the bot runs a background pass to extract upcoming events, appointments, or things you mentioned (job interview Thursday, doctor on Friday, etc.) and appends them to `user_notes.txt`. She references these naturally in conversation when the moment fits.

To see what's collected: `/notes`
To remove an entry: `/notes del <n>`
To add something manually: `/note <text>`

---

## Memory System

Two tiers:

**Long-term** (`summaries`, `facts`)
- Condensed narrative of the full conversation history
- Extracted facts about you
- Promoted from recent memory during nightly reflection

**Recent** (`recent_summaries`, `recent_facts`)
- Shorter window covering roughly the last week
- Refreshed more frequently

All memory lives in `state.json` in the character's directory. Back it up:
```bash
cp ~/nora-bot/state.json ~/nora-bot/state.backup.$(date +%Y%m%d).json
```
Or use `/backup` from the chat.

### Editing memory directly
```bash
nano ~/nora-bot/state.json
```
Find your chat ID key and edit `facts`. Changes take effect on the next message.

---

## Proactive Messages (Heartbeat)

The bot sends unprompted check-ins on a random timer (default 2–6 hours). The next tick is
persisted across restarts (`.next_heartbeat`), so redeploying doesn't reset the countdown. A tick
is skipped (not rescheduled early) during quiet hours, if you were recently active, or if the
daily nudge budget is exhausted — in all three cases it saves a draft instead of sending nothing.

Before sending, it runs a quick background call to generate a concrete hook — drawing on her current life arc, weather, your notes, and the last exchange — so the message feels like she actually thought of something rather than a templated check-in.

Configure in `.env`:
```
HEARTBEAT_MIN_HOURS=2    # minimum hours between heartbeats
HEARTBEAT_MAX_HOURS=6    # maximum hours
QUIET_START=23:00        # no proactive messages sent after this local time
QUIET_END=08:00          # ...until this local time
```

Daily proactive message limit (not an env var) — set per chat with `/nudges N` (e.g. `/nudges 6`,
or `/nudges 0` for unlimited; defaults to 3/day).

Pause proactives temporarily: `/quiet 3` (3 hours), `/quiet off` to cancel.

---

## Typing Delay

The bot holds a "typing..." indicator before sending, simulating compose time based on message length. Configurable in `.env`:

```
TYPING_DELAY=1           # set to 0 to disable
TYPING_WPM=45            # simulated typing speed
TYPING_DELAY_MIN=1.5     # minimum seconds
TYPING_DELAY_MAX=8.0     # maximum seconds
```

A ±20% random jitter is applied so the same-length message doesn't always take exactly the same time.

---

## LLM API Configuration

The bot uses any OpenAI-compatible API endpoint. Configure in `.env`:

```
NANOGPT_BASE_URL=https://api.your-provider.com/v1   # base URL (no trailing slash)
NANOGPT_API_KEY=your-api-key-here
NANOGPT_MODEL=your-default-chat-model
```

### Model slots

The bot uses different models for different tasks — cheap/fast for background work, capable for actual chat:

| Env var | Purpose | Default |
|---|---|---|
| `NANOGPT_MODEL` | Main chat model | required |
| `SUMMARY_MODEL` | Memory summarization | falls back to chat model |
| `REACTION_MODEL` | Auto-reactions, quick calls | falls back to chat model |
| `MOOD_MODEL` | Mood scoring, note extraction, proactive hooks | falls back to reaction model |
| `VISION_MODEL` | Photo descriptions | falls back to chat model |
| `FALLBACK_MODEL` | Retry on error | optional |

Change a model at runtime (no restart): `/setmodel chat gpt-4o`

---

## Character Configuration

Each character lives in its own directory (e.g. `~/nora-bot/`) containing:
- `.env` — bot token, API key, model settings
- `nora.json` (or whatever `CHARACTER_CARD=` points to) — persona card
- `state.json` — conversation history, memory, mood (auto-created)
- Context files: `life.txt`, `people.txt`, `projects.txt`, `schedule.txt`, `day.txt`, `user_notes.txt`, `places.txt`

The shared `~/telegram-bot/bot.py` is used by all instances — each instance just reads its own directory.

To swap the character card: change `CHARACTER_CARD=` in `.env` and restart. Use `/forget` for a clean memory slate.

---

## Running Multiple Characters

All bots share one `bot.py` (+ `bot_app/`) and launch from their own directories. Currently live:
`nora`, `bonnie`, `cass`, `emily`, `jules` (Priya's character files exist in the repo but she isn't
deployed yet). Restart all of them at once with:

```bash
bash ~/telegram-bot/update-all.sh
```

This pulls the latest code and relaunches each instance found on disk under `run-bot.sh`'s
supervisor, in its own named tmux session (`nora`, `bonnie`, `cass`, `emily`, `jules`, and `priya`
once she's built).

Each character is fully isolated — separate state, memory, context files, and bot token. They have no knowledge of each other.

---

## Crash Recovery (Watchdog)

Two layers, catching different failure modes:

1. **In-tmux supervisor** (`run-bot.sh`, always on once a bot is started) — if the bot process
   itself exits (crash, unhandled exception escaping `main()`), the supervisor loop inside that
   bot's tmux session relaunches it after 5s. This dies if the tmux session itself dies.
2. **`watchdog.sh`** — catches what the supervisor can't: the tmux session (or all of Termux)
   getting killed by Android. It checks every bot's tmux session and `.alive` heartbeat file
   (stamped every 60s; a session that's up but hasn't stamped recently is treated as frozen) and
   relaunches anything missing or stale.

`watchdog.sh` only checks **once** unless something keeps re-invoking it — a single check at boot
is not enough to catch Termux getting killed *mid-session*. `termux-boot-start.sh` (installed as
`~/.termux/boot/termux-boot-start.sh` via the Termux:Boot app — see SETUP_GUIDE.md) launches
`watchdog.sh --loop` in the background at boot, which re-checks every `WATCHDOG_INTERVAL` seconds
(default 300) for as long as the device stays up. This is what actually provides continuous
coverage, not just a fresh-boot check.

Manual checks:
```bash
bash ~/telegram-bot/watchdog.sh           # one-shot check, relaunches anything missing/stale
pgrep -f "watchdog.sh --loop"             # confirm the continuous loop is actually running
tail -f ~/telegram-bot/watchdog.log       # watchdog's own relaunch log
```

If `pgrep -f "watchdog.sh --loop"` comes back empty after a reboot, Termux:Boot likely isn't
installed/granted, or `termux-boot-start.sh` wasn't copied to `~/.termux/boot/`.

---

## Logs

```bash
tmux attach -t nora          # live output
tail -f ~/nora-bot/bot.log   # full log (rotates to bot.log.1 at ~5MB, one backup kept)
```

---

## Troubleshooting

**Bot doesn't respond**
- Check sessions: `tmux ls`
- Attach and watch output: `tmux attach -t nora`
- Run in foreground: `python ~/telegram-bot/bot.py ~/nora-bot`

**`TELEGRAM_BOT_TOKEN not found`**
- Make sure `.env` exists in the character's directory (not just `.env.example`)
- Check for typos in the key name

**`ModuleNotFoundError`**
- Activate the venv: `source ~/telegram-bot/venv/bin/activate`

**Model errors / 5xx from the API**
- Set `FALLBACK_MODEL` in `.env` to retry with a different model automatically
- Check your provider's status page

**Vision / selfie errors (503)**
- The vision or image model is temporarily down
- Set `VISION_FALLBACK` in `.env` to automatically try a backup model

**Reminders not firing**
- Requires `python-telegram-bot[job-queue]`: `pip install "python-telegram-bot[job-queue]"`
- Check that `TIMEZONE` in `.env` is set correctly (e.g. `America/Chicago`)

**State file corrupted on startup**
- The bot renames `state.json` to `state.json.corrupted` and starts fresh
- Restore from backup: `cp state.json.corrupted state.json` after fixing the JSON

**Proactive messages stopped**
- Check `/nudges` — daily budget may be exhausted
- Check `/quiet` status in `/status`
- Verify `QUIET_START`/`QUIET_END` match your timezone (set via `TIMEZONE`)

**`bot_app unavailable` warning in the log**
- `bot.py` imports the `bot_app/` package defensively — a missing/half-deployed copy disables the
  guard-consolidation/untrusted-notes/action-allowlist subsystems but never crashes the bot
- Confirm `bot_app/` exists next to `bot.py` (`ls ~/telegram-bot/bot_app/`); if not, re-run
  `update-all.sh`, which syncs it in lockstep with `bot.py`
