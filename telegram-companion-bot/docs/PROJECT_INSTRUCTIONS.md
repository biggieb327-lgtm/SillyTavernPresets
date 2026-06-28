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

One `bot.py` file, multiple instance directories. Each instance has its own `.env`, character card JSON, and `state.json`. The instance dir is passed as `sys.argv[1]` or `BOT_HOME` env var.

**Instance directories:**
- Nora: `~/telegram-bot/` (tmux session: `nora`)
- Bonnie: `~/bonnie-bot/` (tmux session: `bonnie`)
- Emily: `~/emily-bot/` (tmux session: `emily`)
- Cass: `~/cass-bot/` (tmux session: `cass`)

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

## Active model (Cass, as of last session)

`NANOGPT_MODEL=deepseek/deepseek-v4-flash`
`DOCUMENT_MODEL=deepseek/deepseek-v4-flash`

## Deployment workflow

After committing and pushing bot.py changes to GitHub:

```bash
# Update bot.py for an instance
curl -o ~/bonnie-bot/bot.py https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bot.py

# Restart the instance
tmux kill-session -t bonnie
tmux new-session -d -s bonnie -c ~/bonnie-bot 'python bot.py'
```

For a card-only change (no bot.py change), curl the card JSON instead:
```bash
curl -o ~/bonnie-bot/bonnie.json https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bonnie/bonnie.json
tmux kill-session -t bonnie
tmux new-session -d -s bonnie -c ~/bonnie-bot 'python bot.py'
```

All bots share the venv at `~/telegram-bot/venv/`.

## Known Termux quirks

- `/tmp` is not writable — use `~/env.tmp` for temp files
- Network goes stale during long model waits — `_keep_typing` swallows exceptions; `send_bubbles` retries 3× with backoff
- `tmux kill-session -t name` before `new-session` with the same name, or you get "duplicate session" error
- `bot.pid` lock file: if a bot crashes without cleanup, delete `~/instance-dir/bot.pid` before restarting

## Git branch

Development branch: `claude/telegram-emotion-concepts-prompt-s4eqzn`
Commits also land on `main` (same history).

## Character card notes

**Bonnie** (`bonnie.json`) — libertarian gremlin housewife, chaotic surface/abandonment terror underneath. Recently revised: personality reordered (Friction → Core → OCEAN → Energy States → Surface), friction rewritten, energy states section added, sexual behavior rewritten as observable patterns, first_mes changed to 4-state (calm) opening.

**Cass** (`cass.json`) — writing collaborator/developmental editor. Analysis-mode bot: send her a `.json` character card and she gives a substantive critique. Uses `DOCUMENT_MODEL` (instruction model) for card analysis so she doesn't perform the character she's reading. Recently tuned: leads with fixes not just diagnosis, advances conversations rather than circling.

**Emily** (`emily.json`) — has `VISION_MODEL=zai-org/glm-4.6v`. Currently investigating photo receipt issues (no response when photos sent; likely network timeout silencing the error reply).

**Nora** (`nora.json`) — original instance.

## What I help with

- Writing and editing SillyTavern character cards (description, personality, friction, OCEAN, energy states, mes_example, system_prompt, post_history_instructions)
- Python code changes to bot.py (handlers, models, features)
- Debugging bot behavior (error messages, model selection, Termux network issues)
- Committing and pushing to GitHub; providing curl+restart commands for deployment
