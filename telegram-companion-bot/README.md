# Telegram Companion Bot

A self-hosted AI companion that lives in your Telegram DMs. Powered by [NanoGPT](https://nano-gpt.com) (OpenAI-compatible API). Runs on a phone via Termux, a VPS, or a Mac.

Includes an example character — Priya, a 26-year-old software engineer — designed for realistic, casual texting rather than assistant-style responses.

## Features

- Persistent memory across conversations (rolling history + summarization + fact extraction)
- Sends and receives photos, voice messages, documents, stickers, and location
- Proactive check-ins (optional — the bot can message you first)
- Reminders (`/remindme`, `/setreminder`)
- Image generation and TTS via `/imagine` and `/tts`
- Multi-instance support — run multiple characters simultaneously
- Standard SillyTavern v2 character card format
- Configurable models for chat, vision, and summarization

## Quick Start

See **SETUP_GUIDE.md** for full installation instructions.

```bash
git clone https://github.com/biggieb327-lgtm/sillytavernpresets.git
cd sillytavernpresets/telegram-companion-bot
pip install -r requirements.txt
cp .env.example .env
# edit .env with your tokens
bash run.sh
```

## Files

| File | Purpose |
|---|---|
| `bot.py` | Main bot code |
| `priya.json` | Example character card (SillyTavern v2 format) |
| `preset.txt` | Texting style instructions (injected into every prompt) |
| `.env.example` | Config template |
| `requirements.txt` | Python dependencies |
| `run.sh` | Start script (Termux/tmux) |
| `run-bot.sh` | Start script for named instances |
| `SETUP_GUIDE.md` | Full setup walkthrough |
| `OPS_MANUAL.md` | Day-to-day operation reference |

## License

MIT
