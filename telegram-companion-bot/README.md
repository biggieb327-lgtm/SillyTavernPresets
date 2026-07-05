# Telegram Companion Bot

A self-hosted AI companion that lives in your Telegram DMs. Powered by [NanoGPT](https://nano-gpt.com) (OpenAI-compatible API, or any other OpenAI-compatible provider). Runs on a phone via Termux, a VPS, or a Mac.

One `bot.py` runs any number of characters simultaneously, each in its own directory with its own `.env`, character card, and memory — fully isolated from one another. Includes six example characters (Nora, Bonnie, Cass, Emily, Priya, Jules) as a starting point; swap in your own SillyTavern v2 card to make it someone else entirely.

## Features

- Persistent memory across conversations (rolling history + summarization + fact extraction), plus a separate NPC/world-memory system for people and places in the character's own life
- Sends and receives photos, voice messages, video, documents, and location
- Proactive check-ins (optional — the bot can message you first) and date-aware follow-ups ("how did the interview go?")
- Reminders (`/remindme`) and recurring tasks (`/cron`)
- Selfie generation (`/selfie`) and optional TTS voice replies (`/voice`)
- Multi-instance support — run multiple characters simultaneously, sharing one codebase
- Standard SillyTavern v2 character card format
- Configurable models per task (chat, vision, summarization, reactions, mood)
- Self-deploy from Telegram (`/update`, `/restart`) — no shell needed for routine updates
- Self-diagnostics from Telegram (`/audit`, `/errors`) — see `OPS_MANUAL.md`

## Quick Start

See **SETUP_GUIDE.md** for full installation instructions.

```bash
git clone https://github.com/biggieb327-lgtm/sillytavernpresets.git
cd sillytavernpresets/telegram-companion-bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your tokens
bash run-bot.sh
```

## Files

| File | Purpose |
|---|---|
| `bot.py` | Main bot code |
| `nora.json`, `bonnie.json`, `cass.json`, `emily_harper.json`, `priya.json`, `jules_nakagawa.json` | Example character cards (SillyTavern v2 format) |
| `preset.txt` | Texting style instructions (injected into every prompt) |
| `.env.example` | Config template |
| `requirements.txt` | Python dependencies |
| `run-bot.sh` | Start/restart any instance (named, or the home instance with no argument) |
| `update-all.sh` | Pull latest `bot.py`/`run-bot.sh` and restart every configured instance |
| `SETUP_GUIDE.md` | Full setup walkthrough |
| `OPS_MANUAL.md` | Day-to-day operation reference, command list |
| `CHANGELOG.md` | Every shipped fix, with root causes — read before making changes |

## License

MIT
