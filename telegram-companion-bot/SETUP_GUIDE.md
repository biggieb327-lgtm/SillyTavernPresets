# Setup Guide: AI Companion Bot on Telegram

This guide walks through setting up the companion bot from scratch on Android (Termux). Also covers Linux VPS and Mac.

---

## What You'll Need

- A Telegram account and a bot token from @BotFather
- An API key from an OpenAI-compatible LLM provider
- Android (Termux), a Linux VPS, or a Mac
- About 15–20 minutes

### Choosing an LLM provider

The bot works with any provider that exposes an OpenAI-compatible `/v1/chat/completions` endpoint. Set `NANOGPT_BASE` to their base URL and `NANOGPT_API_KEY` to your key. Popular options:

| Provider | Base URL |
|---|---|
| NanoGPT (default if unset) | `https://nano-gpt.com/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Ollama (local) | `http://localhost:11434/v1` |

---

## Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Pick a name (e.g. "Nora") and a username (e.g. `nora_companion_bot`)
4. BotFather gives you a **bot token** like `7123456789:AAFxxxxx...` — save it

If you're running multiple characters, repeat this step for each one — each character needs its own bot token.

---

## Step 2: Get Your Telegram User ID

1. Message **@userinfobot** on Telegram — it replies with your numeric user ID

Save this — you'll add it to `.env` as `ALLOWED_USERS` to lock the bot to only you.

---

## Step 3: Install

### Option A: Android (Termux) — Recommended

1. Install **Termux** from F-Droid (not the Play Store — it's outdated):
   https://f-droid.org/packages/com.termux/

2. Open Termux and install dependencies:
```bash
pkg update && pkg upgrade -y
pkg install python git tmux -y
```

3. Create the shared bot directory and download the files:
```bash
mkdir -p ~/telegram-bot
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bot.py -o ~/telegram-bot/bot.py
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/run-bot.sh -o ~/telegram-bot/run-bot.sh
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/update-all.sh -o ~/telegram-bot/update-all.sh
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/requirements.txt -o ~/telegram-bot/requirements.txt
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/.env.example -o ~/telegram-bot/.env.example
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/preset.txt -o ~/telegram-bot/preset.txt
```

4. Set up a virtual environment:
```bash
cd ~/telegram-bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Step 4: Set Up a Character

Each character runs from its own directory with its own `.env` and character card. The shared `bot.py` in `~/telegram-bot/` is used by all of them.

### Single character

```bash
mkdir ~/nora-bot
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/nora.json -o ~/nora-bot/nora.json
cp ~/telegram-bot/.env.example ~/nora-bot/.env
nano ~/nora-bot/.env
```

At minimum set:
```
TELEGRAM_BOT_TOKEN=your-token-here
NANOGPT_BASE=https://api.your-provider.com/v1
NANOGPT_API_KEY=your-key-here
NANOGPT_MODEL=your-model-name
ALLOWED_USERS=your-telegram-user-id
CHARACTER_CARD=nora.json
BOT_TIMEZONE=America/New_York
```

Start the bot:
```bash
bash ~/telegram-bot/run-bot.sh ~/nora-bot nora
```
This runs it in a tmux session under a supervisor that auto-restarts it if it ever
crashes — you don't need to keep a terminal open or use `nohup`.

You should see startup log lines. Message your bot on Telegram — she should respond.

Detach without stopping it: attach with `tmux attach -t nora`, then press `Ctrl+B`, then `D`.

---

## Step 5: Run All 6 Characters

Download all character cards and create a directory for each:

```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/nora.json          -o ~/nora-bot/nora.json
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bonnie.json       -o ~/bonnie-bot/bonnie.json
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/cass.json         -o ~/cass-bot/cass.json
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/emily_harper.json -o ~/emily-bot/emily_harper.json
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/priya.json        -o ~/priya-bot/priya.json
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/jules_nakagawa.json -o ~/jules-bot/jules_nakagawa.json
```

Create a `.env` in each directory. Each needs its own bot token; the API key and model can be the same across all:

```bash
cp ~/telegram-bot/.env.example ~/nora-bot/.env   # then edit
cp ~/telegram-bot/.env.example ~/bonnie-bot/.env
# etc. — set CHARACTER_CARD= to match the filename you downloaded into each directory
```

Start (or restart) everything at once:
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/update-all.sh | bash
```

Each character runs in its own tmux session (`nora`, `bonnie`, `cass`, `emily`, `priya`, `jules`), under a supervisor that auto-restarts it if it ever crashes. Attach to any with `tmux attach -t nora`. `update-all.sh` also doubles as your update command later — see `OPS_MANUAL.md`, or just send `/update` to a bot from Telegram once it's running.

---

## Step 6: Optional — Atlas Files (Local Places)

Each character can have an `atlas.txt` in her directory — a list of real local places she might naturally reference in conversation. The bot samples a handful per message.

Download the pre-seeded ones:
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/nora/atlas.txt   -o ~/nora-bot/atlas.txt
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bonnie/atlas.txt -o ~/bonnie-bot/atlas.txt
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/cass/atlas.txt   -o ~/cass-bot/atlas.txt
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/emily/atlas.txt  -o ~/emily-bot/atlas.txt
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/priya/atlas.txt  -o ~/priya-bot/atlas.txt
```

Each file is just one place per line, matching wherever that character actually lives —
keep it geographically consistent if you edit it. Override the filename with `ATLAS_FILE=` in `.env`.

---

## Step 7: Optional — Selfies

Drop a reference photo in the character's directory and configure in `.env`:

```
SELFIE_BASE=nora_base.png
SELFIE_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key-here
```

Restart, then try `/selfie` in the chat.

---

## Step 8: Optional — Memes

Memes use bundled template images + text overlay (Pillow), not AI image generation —
reliable, legible captions instead of AI-garbled text. Templates and the font are
shared across all characters, not per-instance:

```bash
mkdir -p ~/telegram-bot/meme_templates ~/telegram-bot/fonts
# Download each template you want from the repo's meme_templates/ folder, e.g.:
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/meme_templates/drake.jpg -o ~/telegram-bot/meme_templates/drake.jpg
# ...repeat for the other templates in that folder...
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/fonts/Anton-Regular.ttf -o ~/telegram-bot/fonts/Anton-Regular.ttf
```

These are one-time assets, not part of `update-all.sh`'s routine `bot.py` pull — no
need to re-fetch them on every deploy. Then try `/meme` in the chat, or let her reach
for a `[meme: ...]` tag on her own when a moment calls for it.

---

## Step 9: Keep Android from Killing It

Termux can be killed by Android's battery optimizer:

1. **Settings → Apps → Termux → Battery → Unrestricted**
2. Lock Termux in the recent apps view (long-press the card and pin it)

On Samsung specifically, also check **Settings → Battery → Background usage limits** —
add Termux to **Never sleeping apps**, and turn off **Put unused apps to sleep**.
Newer One UI versions also have **Settings → Security and privacy → Auto Blocker**,
which restricts apps installed outside the Play Store (which is how Termux is
installed); either disable it or add a Termux exception. See `CLAUDE.md`'s
Termux/Android quirks section for the full troubleshooting story if bots keep
restarting even after this.

Or run on a Linux VPS instead (~€4.50/month on Contabo — 4 vCPU/6GB RAM/100GB NVMe,
the best RAM-per-dollar tier for running all 6 bots comfortably; see `OPS_MANUAL.md`'s
"Running on a VPS" section for the installer).

---

### Option B: Linux VPS (Ubuntu/Debian)

```bash
sudo apt update && sudo apt install python3 python3-pip python3-venv git tmux -y
mkdir -p ~/telegram-bot && cd ~/telegram-bot
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bot.py -o bot.py
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/run-bot.sh -o run-bot.sh
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/requirements.txt -o requirements.txt
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/.env.example -o .env.example
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Then follow Step 4 onwards. `run-bot.sh` uses tmux and works the same here as on Termux;
no Docker setup needed.

---

### Option C: Mac

```bash
brew install tmux python
mkdir -p ~/telegram-bot && cd ~/telegram-bot
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bot.py -o bot.py
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/run-bot.sh -o run-bot.sh
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/requirements.txt -o requirements.txt
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/.env.example -o .env.example
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Then follow Step 4 onwards.

---

## Next Steps

Once the bot is running:

- `/help` in the bot chat shows all available commands
- `/status` gives a quick dashboard: mood, life arc, today's context, weather, last chat
- `/audit` confirms it's actually running the version you deployed
- Set up her **context files** from Telegram — start with `/life`, `/people`, and `/schedule` to give her something to draw on
- Read **OPS_MANUAL.md** for day-to-day operation, the full command list, and troubleshooting
- Read **CHANGELOG.md** before making any code changes — it has the root cause behind every fix so far
- Edit `preset.txt` to change texting style and behavioral rules
- Edit the character card JSON to change personality, backstory, and scenario
