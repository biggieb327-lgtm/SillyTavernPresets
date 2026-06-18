# Setup Guide: AI Companion Bot on Telegram

This guide walks through setting up the companion bot from scratch on Android (Termux). Also covers Linux VPS and Mac.

---

## What You'll Need

- A Telegram account
- A NanoGPT account and API key (https://nano-gpt.com) — powers the AI
- Android (Termux), a Linux VPS, or a Mac
- About 15–20 minutes

---

## Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Pick a name (e.g. "Nora") and a username (e.g. `nora_companion_bot`)
4. BotFather gives you a **bot token** like `7123456789:AAFxxxxx...` — save it

---

## Step 2: Get Your NanoGPT API Key

1. Go to https://nano-gpt.com and create an account
2. Add some credits (a few dollars goes a long way)
3. Copy your API key from account settings

---

## Step 3: Get Your Telegram User ID

1. Send `/chatid` to your bot after setting it up, **or**
2. Message **@userinfobot** on Telegram — it replies with your numeric user ID

Save this — you'll add it to `.env` as `ALLOWED_USERS` to lock the bot to only you.

---

## Step 4: Install

### Option A: Android (Termux) — Recommended

1. Install **Termux** from F-Droid (not the Play Store — it's outdated):
   https://f-droid.org/packages/com.termux/

2. Open Termux and install dependencies:
```bash
pkg update && pkg upgrade -y
pkg install python git tmux -y
```

3. Create the bot directory and download the files:
```bash
mkdir ~/telegram-bot && cd ~/telegram-bot
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bot.py -o bot.py
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/run.sh -o run.sh
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/run-bot.sh -o run-bot.sh
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/.env.example -o .env.example
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/preset.txt -o preset.txt
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/nora.json -o nora.json
```

4. Set up a virtual environment:
```bash
python -m venv venv
source venv/bin/activate
pip install "python-telegram-bot[job-queue]>=21.0,<22.0" python-dotenv requests tzdata
```

5. Configure the bot:
```bash
cp .env.example .env
nano .env
```

At minimum set:
```
TELEGRAM_BOT_TOKEN=your-token-here
NANOGPT_API_KEY=your-key-here
ALLOWED_USERS=your-telegram-user-id
CHARACTER_CARD=nora.json
BOT_TIMEZONE=America/New_York
```

6. Start the bot:
```bash
source venv/bin/activate
bash run.sh
```

You should see the startup log lines. Message your bot on Telegram — she should respond.

7. Detach so the bot keeps running in the background:
   Press `Ctrl+B`, then `D`

---

### Option B: Linux VPS (Ubuntu/Debian)

```bash
sudo apt update && sudo apt install python3 python3-pip python3-venv git tmux -y
mkdir ~/telegram-bot && cd ~/telegram-bot
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bot.py -o bot.py
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/run.sh -o run.sh
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/.env.example -o .env.example
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/preset.txt -o preset.txt
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/nora.json -o nora.json
python3 -m venv venv
source venv/bin/activate
pip install "python-telegram-bot[job-queue]>=21.0,<22.0" python-dotenv requests tzdata
cp .env.example .env && nano .env
bash run.sh
```

Alternatively, use Docker (see Dockerfile + docker-compose.yml in the repo).

---

### Option C: Mac

```bash
brew install tmux python
mkdir ~/telegram-bot && cd ~/telegram-bot
# download files as above (same curl commands)
python3 -m venv venv
source venv/bin/activate
pip install "python-telegram-bot[job-queue]>=21.0,<22.0" python-dotenv requests tzdata
cp .env.example .env && nano .env
bash run.sh
```

---

## Step 5: Add a Character Photo (for selfies)

Drop a reference photo in the bot directory:
```bash
# Example — copy a photo named nora_base.png into the folder
```

Then set it in `.env`:
```
SELFIE_BASE=nora_base.png
SELFIE_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key-here
```

Restart the bot, then try `/selfie`.

---

## Step 6: Run a Second Character (e.g. Bonnie)

Each character needs its own folder with its own `.env` and a separate bot token from @BotFather:

```bash
mkdir ~/bonnie-bot
cp ~/telegram-bot/.env ~/bonnie-bot/.env
# edit ~/bonnie-bot/.env — change TELEGRAM_BOT_TOKEN and CHARACTER_CARD=bonnie.json
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bonnie.json -o ~/bonnie-bot/bonnie.json

source ~/telegram-bot/venv/bin/activate
bash ~/telegram-bot/run-bot.sh ~/bonnie-bot bonnie
```

---

## Step 7: Keep Android from Killing It

Termux can be killed by Android's battery optimizer:

1. **Settings → Apps → Termux → Battery → Unrestricted**
2. Lock Termux in the recent apps view (long-press the card and pin it)

Or run on a VPS instead ($3–5/month on Hetzner or DigitalOcean).

---

## Next Steps

- `/help` in the bot chat shows all available commands
- Read **OPS_MANUAL.md** for day-to-day operation and troubleshooting
- Edit `preset.txt` to change texting style and behavioral rules
- Edit the character card JSON to change personality, backstory, and scenario
