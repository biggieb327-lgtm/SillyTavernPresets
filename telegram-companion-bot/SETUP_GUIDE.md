# Setup Guide: Your Own AI Companion on Telegram

This guide walks through setting up the companion bot from scratch on an Android phone using Termux. It also covers running it on a Linux VPS or Mac if you prefer.

---

## What You'll Need

- A Telegram account
- A NanoGPT account and API key (https://nano-gpt.com) — this is what powers the AI
- Either: an Android phone (for Termux), a Linux VPS, or a Mac
- About 15–20 minutes

---

## Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts — pick a name (e.g. "Priya") and a username (e.g. `priya_companion_bot`)
4. BotFather will give you a **bot token** that looks like `7123456789:AAFxxxxx...`
5. Save that token — you'll need it in a moment

---

## Step 2: Get Your NanoGPT API Key

1. Go to https://nano-gpt.com and create an account
2. Add some credits (a few dollars goes a long way)
3. Go to your account settings and copy your API key

---

## Step 3: Get Your Telegram User ID

You'll want to restrict the bot to only respond to you.

1. Message **@userinfobot** on Telegram
2. It will reply with your numeric user ID (e.g. `123456789`)
3. Save this — you'll add it to `.env` as `ALLOWED_USERS`

---

## Step 4: Install the Bot

### Option A: Android (Termux) — Recommended for always-on

1. Install **Termux** from F-Droid (not the Play Store version — it's outdated)
   - https://f-droid.org/packages/com.termux/

2. Open Termux and run:
```bash
pkg update && pkg upgrade -y
pkg install python git tmux -y
```

3. Clone the repo:
```bash
git clone https://github.com/biggieb327-lgtm/sillytavernpresets.git
cd sillytavernpresets/telegram-companion-bot
```

4. Install Python dependencies:
```bash
pip install -r requirements.txt
```

5. Copy and fill in the config:
```bash
cp .env.example .env
nano .env
```

At minimum, set:
```
TELEGRAM_BOT_TOKEN=your-token-here
NANOGPT_API_KEY=your-key-here
ALLOWED_USERS=your-telegram-user-id
```

6. Start the bot:
```bash
bash run.sh
```

You should see `Starting Priya bot...` in the terminal. Message your bot on Telegram — it should respond.

7. Detach from the terminal so the bot keeps running:
   - Press `Ctrl+B`, then `D`
   - The bot continues running in the background

---

### Option B: Linux VPS (Ubuntu/Debian)

```bash
sudo apt update && sudo apt install python3 python3-pip git tmux -y
git clone https://github.com/biggieb327-lgtm/sillytavernpresets.git
cd sillytavernpresets/telegram-companion-bot
pip3 install -r requirements.txt
cp .env.example .env
nano .env   # fill in your tokens
bash run.sh
```

For a VPS, you may want to use a systemd service instead of tmux for auto-restart on reboot — see the ops manual for details.

---

### Option C: Mac

```bash
brew install tmux  # if you don't have it
git clone https://github.com/biggieb327-lgtm/sillytavernpresets.git
cd sillytavernpresets/telegram-companion-bot
pip3 install -r requirements.txt
cp .env.example .env
nano .env
bash run.sh
```

---

## Step 5: Test It

1. Open Telegram and find your bot (search by the username you gave it)
2. Send `/start` — the bot should send Priya's opening message
3. Send a regular message — she should respond naturally

If it doesn't respond, check the logs:
```bash
tmux attach -t priya
```

---

## Step 6: Customize the Character (Optional)

The character card is `priya.json`. It's a standard SillyTavern v2 character card — you can:

- Edit `description`, `personality`, `scenario`, and `first_mes` to change who she is
- Swap in a completely different character card (rename it to `priya.json` or update `card_path` in `bot.py`)
- Import any character from ChubAI or similar and drop the JSON into the folder

Additional texting style instructions live in `preset.txt`. Edit that to change how she formats responses.

---

## Step 7: Enable Proactive Messages (Optional)

The bot can send occasional unprompted check-ins. To enable:

1. Edit `.env`:
```
PROACTIVE_USER_ID=your-telegram-user-id
PROACTIVE_HOUR_START=9
PROACTIVE_HOUR_END=21
BOT_TIMEZONE=America/New_York
```

2. Restart the bot.

The bot will check every 30 minutes and has a ~30% chance of sending a message — so you'll get roughly one per day during your waking hours.

---

## Running a Second Character

Want to run Luna alongside Priya? Each character needs:
- A separate Telegram bot token (create another bot via @BotFather)
- A separate folder with its own `.env` and character card

```bash
mkdir ~/luna-bot
cp .env ~/luna-bot/.env
cp yourcard.json ~/luna-bot/priya.json   # or whatever name you use
# edit ~/luna-bot/.env with Luna's bot token
bash run-bot.sh ~/luna-bot luna
```

---

## Staying On (Android)

Termux can be killed by Android's battery optimizer. To prevent this:

1. Go to **Settings → Apps → Termux → Battery**
2. Set to **Unrestricted** (or "Don't optimize")
3. Some phones also need you to lock the Termux app in the recent apps view

Alternatively, run the bot on a cheap VPS ($3–5/month on Hetzner, DigitalOcean, etc.) and SSH in from your phone.

---

## Next Steps

- Read the **OPS_MANUAL.md** for day-to-day commands, memory management, and troubleshooting
- Check the available bot commands with the `/status`, `/summary`, and `/note` commands
- Explore NanoGPT's model list to try different AI models
