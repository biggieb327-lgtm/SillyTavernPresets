# Companion Bot — Operations Manual

Day-to-day operation reference for a running bot.

---

## Starting & Stopping

### Start (Termux — default instance)
```bash
cd ~/telegram-bot
source venv/bin/activate
bash run.sh
```
Opens (or attaches to) a tmux session named `nora`.

### Start a second instance (e.g. Bonnie)
```bash
source ~/telegram-bot/venv/bin/activate
bash ~/telegram-bot/run-bot.sh ~/bonnie-bot bonnie
```

### Attach to a running session
```bash
tmux attach -t nora
tmux attach -t bonnie
```

### Detach (leave bot running)
Press `Ctrl+B`, then `D`.

### Stop the bot
```bash
tmux kill-session -t nora
```

### Update the bot
```bash
cd ~/telegram-bot
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bot.py -o bot.py
tmux kill-session -t nora 2>/dev/null
bash run.sh
```

---

## Commands Reference

### Conversation
| Command | What it does |
|---|---|
| `/start` | Reset history and send the character's opening message |
| `/clear` | Wipe conversation history (keeps long-term memory) |
| `/help` | Show all available commands |
| `/menu` | Open the inline button shortcut menu |

### Memory
| Command | What it does |
|---|---|
| `/memory` | View long-term and recent memory summaries + facts |
| `/remember <fact>` | Save a fact to long-term memory |
| `/forget` | Wipe all memory for your chat |
| `/exportmemory` | Download a full memory export as text |
| `/pin <fact>` | Pin something that's always in context |
| `/pinned` | List pinned memories |
| `/unpin <n>` | Remove a pinned memory by number |
| `/boundary <text>` | Add a soft boundary note |
| `/boundaries` | List boundaries |

### Mood & Modes
| Command | What it does |
|---|---|
| `/vibe <name> [Xh]` | Set a timed vibe: cozy / flirty / serious / chaotic / low-energy / playful / chill |
| `/vent` | Toggle vent mode (listening only, no fixing or advice) |
| `/vent off` | Turn off vent mode |
| `/energy <level>` | Set your energy: high / low / crash |

### Inside Jokes
| Command | What it does |
|---|---|
| `/addjoke phrase \| meaning \| tone` | Add an inside joke |
| `/jokes` | List inside jokes |
| `/deljoke <id>` | Remove a joke by ID |

### Selfie & Wardrobe
| Command | What it does |
|---|---|
| `/selfie [hint]` | Generate a selfie (optional scene hint) |
| `/wardrobe` | List saved outfits |
| `/addoutfit <desc>` | Add an outfit description |
| `/outfit <n>` | Set current outfit (used in selfie generation) |
| `/deloutfit <n>` | Remove an outfit |
| `/selfimage` | View the character's current self-image traits |
| `/reflect` | Trigger the nightly self-reflection now |

### Reminders
| Command | What it does |
|---|---|
| `/remindme <when> <msg>` | One-off reminder. When: `30m`, `2h`, `18:30`, `tomorrow 9:00`, `2026-07-01 14:30` |
| `/setreminder HH:MM <msg>` | Daily recurring reminder at a fixed time |
| `/reminders` | List all pending reminders |
| `/delreminder <n>` | Cancel a reminder by list number |

### Recurring Tasks (Cron)
| Command | What it does |
|---|---|
| `/cron <schedule> \| <instruction>` | Add a recurring task. Schedule: `daily HH:MM`, `weekly Mon HH:MM`, `monthly 1 HH:MM` |
| `/crons` | List recurring tasks |
| `/crondel <id>` | Remove a recurring task |

### Proactive Messages
| Command | What it does |
|---|---|
| `/heartbeat` | Trigger a proactive check-in now |
| `/nudges` | Show today's proactive message budget |

### Payments (if enabled)
| Command | What it does |
|---|---|
| `/addpayment <desc> \| <amount> \| <due>` | Add a bill |
| `/addevery <desc> \| <amount> \| <day>` | Add a monthly recurring bill |
| `/payments` | List all bills |
| `/delpayment <n>` | Remove a bill |
| `/editpayment <n> <field> <value>` | Edit a bill field |
| `/week` | Payment summary for the current week |

### Settings & Info
| Command | What it does |
|---|---|
| `/model` | Show active models |
| `/setmodel <field> <value>` | Change a model (fields: chat, summary, vision, reaction, mood, fallback, visionfallback) |
| `/settings` | Show current settings |
| `/usage` | NanoGPT token usage stats |
| `/chatid` | Show your Telegram user ID |
| `/backup` | Download a memory backup file |

---

## Memory System

The bot maintains two tiers of memory:

**Long-term memory** (`summaries`, `facts`)
- A condensed narrative of the full conversation history
- Extracted facts about you (name, preferences, relationships, etc.)
- Promoted from recent memory during nightly reflection

**Recent memory** (`recent_summaries`, `recent_facts`)
- A shorter window summarizing the last ~20 turns
- Extracted facts from recent conversation
- Refreshed more frequently

All memory lives in `state.json` in the bot's base directory. Back it up with `/backup` or:
```bash
cp ~/telegram-bot/state.json ~/telegram-bot/state.backup.$(date +%Y%m%d).json
```

### Viewing memory
```
/memory
```

### Editing facts directly
```bash
nano ~/telegram-bot/state.json
```
Find your chat ID key, edit the `facts` array. Changes take effect on the next message.

---

## Character Configuration

The character card is set by `CHARACTER_CARD` in `.env` (e.g. `nora.json`).

Texting style and behavioral rules live in `preset.txt`. Edit that to change how she formats responses.

To swap characters mid-run: change `CHARACTER_CARD` in `.env` and restart. Use `/forget` if you want a clean memory slate.

---

## Running Multiple Characters

Each character needs its own folder with a `.env` and character card:

```bash
# Nora (default instance in ~/telegram-bot)
bash run.sh

# Bonnie
bash ~/telegram-bot/run-bot.sh ~/bonnie-bot bonnie
```

Each instance gets its own tmux session and its own state files.

---

## Proactive Messages (Heartbeat)

The bot sends unprompted check-ins on a random timer (default 2–6 hours) during quiet hours.

Configure in `.env`:
```
HEARTBEAT_MIN=2        # minimum hours between heartbeats
HEARTBEAT_MAX=6        # maximum hours
PROACTIVE_HOUR_START=9 # don't send before this hour (local time)
PROACTIVE_HOUR_END=21  # don't send after this hour
NUDGE_MAX=3            # max proactive messages per day
```

---

## Logs

Logs go to `bot.log` in the bot's base directory (when launched via `run.sh`).

```bash
tail -f ~/telegram-bot/bot.log
```

---

## Troubleshooting

**Bot doesn't respond**
- Check if the session is running: `tmux ls`
- Check logs: `tail -f ~/telegram-bot/bot.log`
- Run in foreground to see errors: `python ~/telegram-bot/bot.py`

**`TELEGRAM_BOT_TOKEN not found`**
- Make sure `.env` exists in the bot's directory (not just `.env.example`)
- Check for typos in the key name

**`ModuleNotFoundError`**
- Activate the venv first: `source ~/telegram-bot/venv/bin/activate`

**Model errors / 5xx**
- Set `FALLBACK_MODEL` in `.env` to retry with a different model automatically
- Check NanoGPT status if failures are widespread

**Vision / selfie errors (503)**
- The vision or image model is temporarily down on the provider's side
- Set `VISION_FALLBACK` in `.env` to automatically try a backup model

**Reminders not firing**
- Requires `python-telegram-bot[job-queue]` — install with `pip install "python-telegram-bot[job-queue]"`
- Check that `BOT_TIMEZONE` in `.env` is set correctly

**State file corrupted on startup**
- The bot renames `state.json` to `state.json.corrupted` and starts fresh
- Restore from a backup: `cp state.json.corrupted state.json` after fixing the JSON
