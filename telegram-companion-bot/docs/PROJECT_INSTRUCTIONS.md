# Project: Telegram Companion Bot

This project is a Python Telegram bot system for AI companion characters. The user runs multiple bot instances on Android via Termux. I help with character card writing, bot.py code changes, and deployment.

## Stack

- **Runtime:** Python 3.11+, Termux on Android
- **Library:** python-telegram-bot >=21.0,<22.0 (async)
- **AI backend:** NanoGPT (OpenAI-compatible API at `https://nano-gpt.com/api/v1`)
- **Character format:** SillyTavern chara_card_v2 JSON
- **GitHub repo:** `biggieb327-lgtm/SillyTavernPresets`
- **Raw URL base:** `https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/`

## Architecture

One shared `bot.py` (+ `bot_app/`, a modular migration package it imports defensively — see
`bot_app/MIGRATION.md`) living in `~/telegram-bot/`, with separate per-character instance
directories. Each instance has its own `.env`, character card JSON, and `state.json`. The instance
dir is passed as `sys.argv[1]`.

**Instance directories** (all under the supervised `run-bot.sh` pattern — Nora runs as her own
named instance like the rest, not as the code/home directory):
- Nora: `~/nora-bot/` (tmux session: `nora`)
- Bonnie: `~/bonnie-bot/` (tmux session: `bonnie`)
- Cass: `~/cass-bot/` (tmux session: `cass`)
- Emily: `~/emily-bot/` (tmux session: `emily`)
- Jules: `~/jules-bot/` (tmux session: `jules`)
- Priya: `~/priya-bot/` — character card exists in the repo; not yet deployed

## Key `.env` variables

```
TELEGRAM_BOT_TOKEN=
NANOGPT_API_KEY=
NANOGPT_MODEL=           # main chat model
VISION_MODEL=            # must support image input; defaults to NANOGPT_MODEL
DOCUMENT_MODEL=          # for .json card analysis; use an instruction model, not roleplay-tuned
SUMMARY_MODEL=
REACTION_MODEL=
CHARACTER_CARD=          # filename of the JSON card in the instance dir
ALLOWED_USERS=           # comma-separated Telegram user IDs
```

## Deployment workflow

After committing and pushing `bot.py`/`bot_app/` changes to GitHub, on the device:

```bash
bash ~/telegram-bot/update-all.sh
```

This pulls the latest code from the `~/stp-deploy` git clone, deploys `bot.py` + `bot_app/` +
helper scripts to `~/telegram-bot/`, and restarts every instance found on disk under
`run-bot.sh`'s supervisor (auto-restarts on crash, rotates `bot.log`). See `docs/OPS_MANUAL.md`
for the full reference.

For a card-only change (no `bot.py` change), copy just the card and restart that one instance:
```bash
cp ~/stp-deploy/telegram-companion-bot/bonnie/bonnie.json ~/bonnie-bot/bonnie.json
bash ~/telegram-bot/run-bot.sh ~/bonnie-bot bonnie
```

All bots share the venv at `~/telegram-bot/venv/`.

## Known Termux quirks

- `/tmp` is not writable — use `~/env.tmp` for temp files
- Network goes stale during long model waits — `_keep_typing` swallows exceptions; `send_bubbles` retries 3× with backoff
- `tmux kill-session -t name` before `new-session` with the same name, or you get "duplicate session" error
- `bot.pid` lock file: if a bot crashes without cleanup, delete `~/instance-dir/bot.pid` before restarting

## Git branch

Development branch: `claude/push-to-repo-7i2f3c`

## Character card notes

**Bonnie** (`bonnie.json`) — libertarian gremlin housewife, chaotic surface/abandonment terror
underneath. Her `system_prompt` explicitly overrides `preset.txt`'s no-asterisk-actions rule —
intentional, not drift (a character's own `system_prompt` naturally takes precedence over the
shared default; see the note next to `PRESET_FILE` in `bot.py`).

**Cass** (`cass.json`) — writing collaborator/developmental editor. Analysis-mode bot: send her a
`.json` character card and she gives a substantive critique. Uses `DOCUMENT_MODEL` (instruction
model) for card analysis so she doesn't perform the character she's reading.

**Emily** (`emily.json`) — has Garmin health integration (sleep/stress/RHR/Body Battery, owner
only). Her `system_prompt` also overrides the no-asterisk rule (third-person, italicized action
beats) — same intentional exception as Bonnie's.

**Jules** (`jules.json`) — roller-derby voice, third-person prose narration like Emily's, with the
same explicit `system_prompt` instruction added for consistency — same intentional exception.

**Nora** (`nora.json`) — original instance.

## What I help with

- Writing and editing SillyTavern character cards (description, personality, friction, OCEAN, energy states, mes_example, system_prompt, post_history_instructions)
- Python code changes to bot.py (handlers, models, features)
- Debugging bot behavior (error messages, model selection, Termux network issues)
- Committing and pushing to GitHub; providing curl+restart commands for deployment
