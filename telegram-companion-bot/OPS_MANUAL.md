# Companion Bot — Operations Manual

Day-to-day operation reference for a running bot.

---

## Starting & Stopping

### Preferred: from Telegram, no shell needed
Send `/update` to **one** bot — it downloads the latest `bot.py`, refuses to install
anything that doesn't compile, and restarts itself. Then send `/restart` to the other
bots (they share the same `bot.py`, so they just need to reload it). Verify each with
`/audit` — it shows `BOT_VERSION` and uptime.

### Start everything (first run, or after a run-bot.sh/supervisor change)
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/update-all.sh | bash
```
Pulls the latest `bot.py` and `run-bot.sh`, then restarts every instance (`nora`,
`bonnie`, `cass`, `emily`, `priya`, `jules`) under its own supervisor, which
auto-restarts that bot if it ever crashes.

### Start or restart a single bot
```bash
bash ~/telegram-bot/run-bot.sh ~/nora-bot nora
```
(No folder argument starts the home/default instance instead of a named one.)

### Attach to a running session
```bash
tmux attach -t nora
tmux attach -t emily
# etc.
```
Detach without stopping it: `Ctrl+B`, then `D`.

### Stop one bot
```bash
tmux kill-session -t nora
```
The supervisor will *not* restart it after a manual kill like this — it only restarts
on a crash. To bring it back: `bash ~/telegram-bot/run-bot.sh ~/nora-bot nora` again.

### Stop everything
```bash
for s in nora bonnie cass emily priya jules; do tmux kill-session -t $s 2>/dev/null; done
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
| `/card` | Show the currently loaded character card |
| `/setcard <filename>` | Swap the character card (restart to fully apply; `/forget` for a clean slate) |
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
| `/addmem <text>` | Manually add an NPC/world memory (auto-collected too — see below) |
| `/mems` | List all stored NPC/world memories |
| `/delmem <keyword or #>` | Remove an NPC/world memory |

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
| `/backup` | Send state.json, memories.txt, user_notes.txt, setting.txt, reminders.json, payments.json to chat (`.env` excluded) |

### Operations (admin only — allowlist member or owner)
| Command | What it does |
|---|---|
| `/audit` | Self-audit: `BOT_VERSION`, uptime, error counts, state/disk health |
| `/errors [N]` | Show last N lines of errors.log (default 20, max 50) — check this first for anything odd |
| `/update` | Self-deploy: pull latest `bot.py` from `main`, verify it compiles, restart (`force` to reinstall the same version) |
| `/restart` | Clean restart via the supervisor — picks up `.env` edits and a swapped `bot.py` |

If a bot never responds to any of these either, it's not an app-level problem — see
Troubleshooting below (the tmux session or the process itself may be down).

### Western WA traffic (Emily only — needs `WSDOT_API_KEY`)
| Command | What it does |
|---|---|
| `/traffic` | Western WA congestion snapshot (scoped to you if location shared) |
| `/incidents` | Open WSDOT alerts (filtered nearby if live location active) |

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
| `atlas.txt` | — | Real local places she might naturally reference |

### Atlas file
Each character directory can have an `atlas.txt` (or override the filename via
`ATLAS_FILE=` in `.env`). One place per line — the bot samples a random handful each
message. Lines starting with `#` are comments. Keep this geographically consistent with
wherever the character actually lives now (see her entry in `CLAUDE.md`'s Character
notes) — it's plain text the bot reads verbatim, so nothing stops it from drifting.

### Memes
`/meme [hint]` sends a meme: template image + Pillow-rendered top/bottom text (not
AI-drawn — AI image models render text unreliably, this doesn't). She can also send
one unprompted via a `[meme: top | bottom]` tag when a moment calls for it, mirroring
how the `[selfie: ...]` tag works. Templates live in the shared `meme_templates/`
directory and the font in `fonts/Anton-Regular.ttf`, alongside `bot.py` — not
per-instance, and not part of `update-all.sh`'s routine pull (see Setup Guide Step 8
for the one-time fetch). Add your own templates by dropping a `.jpg` in
`meme_templates/` — no code change needed.

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
NANOGPT_BASE=https://api.your-provider.com/v1   # base URL (no trailing slash); defaults to NanoGPT if unset
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
- Context files: `life.txt`, `people.txt`, `projects.txt`, `schedule.txt`, `day.txt`, `user_notes.txt`, `atlas.txt`

The shared `~/telegram-bot/bot.py` is used by all instances — each instance just reads its own directory.

To swap the character card: change `CHARACTER_CARD=` in `.env` and restart. Use `/forget` for a clean memory slate.

---

## Running Multiple Characters

All 6 bots share one `bot.py` and launch from their own directories via `run-bot.sh` (see
Starting & Stopping above) or `update-all.sh` for all of them at once. Sessions: `nora`,
`bonnie`, `cass`, `emily`, `priya`, `jules`.

Each character is fully isolated — separate state, memory, context files, and bot token. They have no knowledge of each other.

---

## Running on a VPS (Phase 1: installer + admin API)

Alternative to Termux for anyone who'd rather not keep a phone on and awake 24/7. On a
VPS, systemd replaces the tmux+run-bot.sh+watchdog.sh stack (`Restart=always`) and this
whole category of Android-specific bug (phantom process killer, Samsung battery
management, the `.alive` heartbeat watchdog.sh needs) doesn't apply — Termux keeps its
existing mechanism unchanged for anyone still running that way.

**Install** (Ubuntu 24.04 recommended, e.g. a Hetzner CX22):
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/deploy/install-vps.sh -o install-vps.sh
sudo bash install-vps.sh
```
It's idempotent — re-run it to add another instance or after a `git pull` updates
`requirements.txt`; it skips already-configured `.env` files and only touches units
whose config changed. It prompts per instance for a Telegram token, NanoGPT key, and
character card filename, and generates an `ADMIN_API_TOKEN`.

**Supervision**: `systemctl {status,restart,stop} bot@nora`, logs via
`journalctl -u bot@nora -f` (the VPS equivalent of `tail -f bot.log`). `/update` and
`/restart` from Telegram work exactly as they do on Termux — systemd's
`Restart=always` picks the process back up.

**Admin HTTP API**: opt-in (`ADMIN_API_ENABLED=1`), mirrors `/audit /errors /backup
/update /restart` over HTTP for a non-Telegram client (e.g. a future control-panel
app). Reachable only over a private Tailscale network — the installer prints
Tailscale setup instructions and the API stays bound to loopback (unreachable) until
you set `ADMIN_API_BIND` to the host's tailnet IP. See `.env.example` for the full
`ADMIN_API_*` reference and `CHANGELOG.md` (v2026-07-05.12) for the design rationale.

The native Android control-panel app itself is a separate, later phase — not part of
this installer.

---

## Logs

```bash
tmux attach -t nora            # live output
tail -f ~/nora-bot/bot.log      # everything the supervisor has seen (trimmed at 5 MB)
tail -f ~/nora-bot/errors.log   # warnings/errors only (rotates at 2 MB)
```
Or from Telegram, no shell needed: `/errors [N]` tails `errors.log` straight into chat.

---

## Troubleshooting

**Bot doesn't respond**
- Try `/errors` and `/audit` first — if it answers those but not conversation, it's a
  feature-level bug, not a startup crash
- If it answers nothing at all: `tmux ls` (is the session even up?), then
  `tail -50 ~/nora-bot/bot.log` (the actual crash traceback, if any) — see
  `CHANGELOG.md` before assuming a new cause; several past crashes here have known,
  documented root causes
- Attach and watch output live: `tmux attach -t nora`

**`TELEGRAM_BOT_TOKEN not found`**
- Make sure `.env` exists in the character's directory (not just `.env.example`)
- Check for typos in the key name

**`ModuleNotFoundError: No module named 'requests'` (or similar)**
- The shared venv (`~/telegram-bot/venv/`) is missing or was built against a different
  Python than the one now installed. `run-bot.sh` always launches with
  `~/telegram-bot/venv/bin/python` explicitly, so this means the venv itself needs
  rebuilding, not that the launcher picked the wrong interpreter:
  ```bash
  python -m venv --clear ~/telegram-bot/venv
  ~/telegram-bot/venv/bin/pip install -r ~/telegram-bot/requirements.txt
  ```
  Then `update-all.sh` to restart everything on the rebuilt venv.

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
