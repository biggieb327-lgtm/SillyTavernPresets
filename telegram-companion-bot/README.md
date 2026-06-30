# Telegram Companion Bot

A self-hosted AI companion that lives in your Telegram DMs. Powered by [NanoGPT](https://nano-gpt.com) (OpenAI-compatible API). Runs on a phone via Termux, a VPS, or a Mac.

Includes an example character — Priya, a 26-year-old software engineer — designed for realistic, casual texting rather than assistant-style responses.

## Features

- Persistent memory across conversations (rolling history + summarization + fact extraction)
- Sends and receives photos, voice messages, documents, stickers, and location
- Proactive check-ins (optional — the bot can message you first)
- Reminders (`/remindme`, `/setreminder`)
- Selfie generation (`/selfie`) and optional voice (TTS) replies (`/voice`)
- Multi-instance support — run multiple characters simultaneously
- Standard SillyTavern v2 character card format
- Configurable models for chat, vision, and summarization

## Quick Start

See **[docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)** for full installation instructions.

```bash
git clone https://github.com/biggieb327-lgtm/sillytavernpresets.git
cd sillytavernpresets/telegram-companion-bot
pip install -r requirements.txt
cp .env.example .env
# edit .env with your tokens
bash run-bot.sh
```

## Files

| File | Purpose |
|---|---|
| `bot.py` | Main bot code (entry point — imports `bot_app/` defensively) |
| `bot_app/` | Modular migration package (guards, untrusted-notes quarantine, action allowlist, ingestion) — see `bot_app/MIGRATION.md` for status |
| `main.py` | Standalone smoke test for `bot_app/` in isolation; not the bot's entry point |
| `<character>/` | Per-character folder — card, appearance, and context files (people, projects, schedule, places) |
| `priya/priya.json` | Example character card (SillyTavern v2 format) |
| `preset.txt` | Texting style instructions (injected into every prompt) |
| `.env.example` | Config template |
| `common.env` | Optional shared config loaded before each bot's `.env` (API key, model/feature defaults) |
| `requirements.txt` | Python dependencies |
| `run-bot.sh` | Start script (supervised, named instances) |
| `update-all.sh` | Pull latest `bot.py`/`bot_app/`/helper scripts from `~/stp-deploy` and restart all instances |
| `status.sh` | At-a-glance health of every bot (session, heartbeat, recent errors) |
| `watchdog.sh` | Relaunch any bot whose tmux session has died (for cron/boot) |
| `termux-boot-start.sh` | Termux:Boot launcher — brings bots back after a reboot |
| `docs/` | Setup guide, ops manual, project docs |

## License

MIT
