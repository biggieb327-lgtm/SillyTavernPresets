# Companion Bot — Operations Manual

This covers day-to-day operation once your bot is running.

---

## Starting & Stopping

### Start (Termux)
```bash
bash run.sh
```
This opens (or attaches to) a tmux session named `priya`.

### Attach to a running session
```bash
tmux attach -t priya
```

### Detach (leave bot running in background)
Press `Ctrl+B`, then `D`.

### Stop the bot
Attach to the session, then press `Ctrl+C`.

---

## Commands Reference

| Command | What it does |
|---|---|
| `/start` | Sends the character's opening message |
| `/reset` | Clears all history, summary, and facts for your user |
| `/summary` | Shows the current rolling summary and extracted facts |
| `/note <text>` | Save a personal note that gets injected into every prompt |
| `/note` | View current note |
| `/model` | Shows which models are active (chat, summary, vision) |
| `/retry` | Re-generates the last bot reply |
| `/edit <text>` | Replaces the last bot reply with your text (for steering) |
| `/undo` | Removes the last user + bot exchange from history |
| `/status` | Shows memory stats: history length, fact count, turn count |
| `/time` | Shows current time in the bot's configured timezone |
| `/remindme <min> <msg>` | One-off reminder after N minutes |
| `/setreminder <HH:MM> <msg>` | Daily reminder at a specific time |
| `/imagine <desc>` | Generate an image (requires model that supports image gen) |
| `/tts <text>` | Text-to-speech voice message |

---

## Memory System

The bot maintains three layers of memory:

1. **Rolling history** — the last N messages (controlled by `CONTEXT_LIMIT`). Always in context.
2. **Summary** — a condensed narrative of older conversation, regenerated every `SUMMARY_EVERY` turns. Injected at the top of the system prompt.
3. **Facts** — short extracted facts about the user (name, preferences, relationships, etc.). Extracted every ~10 turns. Injected into the system prompt.

All memory lives in `memory.json` in the bot's base directory. Back it up if you care about continuity.

### Viewing memory
```bash
cat memory.json | python3 -m json.tool
```

### Clearing memory for a user
Either use `/reset` in the chat, or manually edit `memory.json` and delete the user's entry.

### Editing facts directly
```bash
nano memory.json
```
Find your user ID key, edit the `"facts"` array. Save. Changes take effect on the next message.

---

## Changing the Character

The character card is `priya.json` (or whatever you named it). The bot reads it at startup.

To change character mid-run: edit `priya.json` (or swap in a new card), then restart the bot. Memory from the previous character will still be loaded—use `/reset` to clear it if you want a clean slate.

To point the bot at a differently named card, change `card_path` in `bot.py`:
```python
card_path = BASE_DIR / "yourcard.json"
```

---

## Running Multiple Characters

Each character needs:
- Its own folder with a `.env` file (separate `TELEGRAM_BOT_TOKEN`)
- Its own character card
- Its own `memory.json` (auto-created)

Run each instance:
```bash
bash run-bot.sh ~/luna-bot luna
bash run-bot.sh ~/priya-bot priya
```

Each gets its own tmux session.

---

## Proactive Messages

If `PROACTIVE_USER_ID` is set in `.env`, the bot will occasionally send unprompted check-ins during the configured hour range.

This runs every 30 minutes with a ~30% chance of firing, capped at once per day.

To disable: remove `PROACTIVE_USER_ID` from `.env` and restart.

---

## Logs

Logs go to `bot.log` in the bot's base directory (when launched via `run.sh`).

To tail logs:
```bash
tail -f bot.log
```

Common log prefixes:
- `[bot]` — startup
- `[summary]` — summarization events
- `[facts]` — fact extraction
- `[proactive]` — proactive message events
- `[error]` — caught errors
- `[nanogpt]` — fallback model events
- `[vision]` — vision model events
- `[card]` — card loading errors

---

## Backups

The only file you need to back up regularly is `memory.json`. Everything else is config.

```bash
cp memory.json memory.backup.$(date +%Y%m%d).json
```

Or sync to a private git repo, Dropbox, etc.

---

## Updating the Bot

```bash
git pull
pip install -r requirements.txt
# restart the bot
```

---

## Troubleshooting

**Bot doesn't respond**
- Check the tmux session is running: `tmux ls`
- Check logs: `tail -f bot.log`
- Verify `.env` has valid tokens

**`TELEGRAM_BOT_TOKEN not found`**
- Make sure `.env` exists in the bot's directory (not just `.env.example`)
- Check for typos in the key name

**Model errors / 5xx**
- NanoGPT may be having issues; check their status
- Set `FALLBACK_MODEL` in `.env` to automatically retry with a different model

**Summaries not triggering**
- Check `SUMMARY_EVERY` in `.env` — default is 20 turns
- Check logs for `[summary]` entries

**Reminders not firing**
- The job queue requires `python-telegram-bot[job-queue]` — make sure you installed with the extra
- APScheduler must be installed: `pip install apscheduler`
