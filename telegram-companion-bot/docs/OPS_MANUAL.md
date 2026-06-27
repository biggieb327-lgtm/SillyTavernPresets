# Companion Bot — Operations Manual

Day-to-day operation reference for a running bot.

---

## Starting & Stopping

### Start all 5 bots at once
```bash
bash ~/start-bots.sh
```
Kills any running instances, then opens each character in its own tmux session (`emily`, `bonnie`, `nora`, `cass`, `priya`).

### Start a single bot
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

### Stop all bots
```bash
pkill -f bot.py
```

### Update bot.py and restart
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bot.py -o ~/telegram-bot/bot.py
bash ~/start-bots.sh
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

### Memory
| Command | What it does |
|---|---|
| `/memory` | View long-term and recent memory summaries + facts |
| `/remember <fact>` | Save a fact to long-term memory |
| `/forget` | Wipe all memory (or `/forget <keyword>` to remove matching facts) |
| `/recall <keyword>` | Search memory for a keyword |
| `/exportmemory` | Download a full memory export as text |
| `/milestones` | View relationship milestones |
| `/pin <fact>` | Pin something that's always in context |
| `/pinned` | List pinned memories |
| `/unpin <n>` | Remove a pinned memory by number |
| `/boundary <text>` | Add a soft boundary note |
| `/boundaries` | List boundaries |

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

### Inside Jokes & Wardrobe
| Command | What it does |
|---|---|
| `/addjoke phrase \| meaning \| tone` | Add an inside joke |
| `/jokes` | List inside jokes |
| `/deljoke <id>` | Remove a joke by ID |
| `/wardrobe` | List saved outfits |
| `/addoutfit <desc>` | Add an outfit description |
| `/outfit <n>` | Set current outfit (used in selfie generation) |
| `/deloutfit <n>` | Remove an outfit |

### Selfie
| Command | What it does |
|---|---|
| `/selfie [hint]` | Generate a selfie (optional scene hint) |
| `/selfimage` | View the character's current self-image traits |
| `/reflect` | Trigger the nightly self-reflection now |

### Proactive Messages
| Command | What it does |
|---|---|
| `/heartbeat` | Trigger a proactive check-in now |
| `/nudges` | Show today's proactive message budget |
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
| `/week` | Payment summary for the current week |

### Settings & Info
| Command | What it does |
|---|---|
| `/model` | Show active models |
| `/setmodel <field> <value>` | Change a model (fields: `chat`, `summary`, `vision`, `reaction`, `mood`, `fallback`) |
| `/settings` | Show current settings |
| `/usage` | Token usage stats |
| `/chatid` | Show your Telegram user ID |
| `/backup` | Download a memory backup file |

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
| `portland_places.txt` | — | Atlas of real local places she might naturally reference |

### Atlas file
Each character directory can have a `portland_places.txt` (or override via `ATLAS_FILE=` in `.env`). One place per line — the bot samples a random handful each message. Lines starting with `#` are comments.

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

The bot sends unprompted check-ins on a random timer (default 2–6 hours) during waking hours.

Before sending, it runs a quick background call to generate a concrete hook — drawing on her current life arc, weather, your notes, and the last exchange — so the message feels like she actually thought of something rather than a templated check-in.

Configure in `.env`:
```
HEARTBEAT_MIN=2          # minimum hours between heartbeats
HEARTBEAT_MAX=6          # maximum hours
PROACTIVE_HOUR_START=9   # don't send before this hour (local time)
PROACTIVE_HOUR_END=21    # don't send after this hour
NUDGE_MAX=3              # max proactive messages per day
```

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
- Context files: `life.txt`, `people.txt`, `projects.txt`, `schedule.txt`, `day.txt`, `user_notes.txt`, `portland_places.txt`

The shared `~/telegram-bot/bot.py` is used by all instances — each instance just reads its own directory.

To swap the character card: change `CHARACTER_CARD=` in `.env` and restart. Use `/forget` for a clean memory slate.

---

## Running Multiple Characters

All 5 bots share one `bot.py` and launch from their own directories:

```bash
bash ~/start-bots.sh
```

The script kills any running instances and opens each in a named tmux session. Sessions: `emily`, `bonnie`, `nora`, `cass`, `priya`.

Each character is fully isolated — separate state, memory, context files, and bot token. They have no knowledge of each other.

---

## Logs

```bash
tmux attach -t nora          # live output
tail -f ~/nora-bot/bot.log   # if launched via run-bot.sh
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
- Check that `BOT_TIMEZONE` in `.env` is set correctly (e.g. `America/Chicago`)

**State file corrupted on startup**
- The bot renames `state.json` to `state.json.corrupted` and starts fresh
- Restore from backup: `cp state.json.corrupted state.json` after fixing the JSON

**Proactive messages stopped**
- Check `/nudges` — daily budget may be exhausted
- Check `/quiet` status in `/status`
- Verify `PROACTIVE_HOUR_START`/`END` match your timezone
