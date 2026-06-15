# Setup Guide: Your Own AI Companion on Telegram

This guide walks you through setting up a personal AI companion bot that lives in
Telegram, has a memory, moods, can send selfies, and texts you on its own. It runs
entirely on your **Android phone** using an app called Termux — no computer or
server required (though it also works on a PC/Linux server if you prefer).

No programming experience needed — just follow the steps in order. Plan for about
30–45 minutes the first time.

---

## What you'll end up with

- A private Telegram chat with a character of your choosing
- She remembers things about you (short-term and long-term memory)
- She can send selfies, react with emoji, search the web, read links you send her
- She occasionally texts you first (like a real person would)
- Everything runs on your phone in the background, even when the screen is off

---

## Before you start: accounts and keys you'll need

You'll create three free accounts. Do this first so you have the keys ready.

### 1. A Telegram bot token (free, required)

1. Open Telegram and search for **@BotFather** (it has a blue checkmark).
2. Send it `/newbot`.
3. Pick a name for your bot (e.g. "Nora") — this is the display name.
4. Pick a username ending in `bot` (e.g. `nora_companion_bot`) — this must be unique.
5. BotFather will reply with a **token** that looks like
   `123456789:ABCdefGhIJKlmNoPQRsTUvwxyZ`. **Save this somewhere safe** — you'll
   paste it into a config file later.

### 2. A NanoGPT API key (required — this powers the AI's brain)

1. Go to **nano-gpt.com** and create an account.
2. Add credit, or sign up for their subscription plan (recommended — it gives you
   access to a large library of models for a flat monthly fee instead of
   per-message charges).
3. In your account settings, find the **API key** section and generate a key. It
   will look like a long random string. **Save it.**

### 3. (Optional) A Google Gemini API key — for selfies

If you want your companion to send AI-generated selfies:

1. Go to **aistudio.google.com**, sign in with a Google account.
2. Create an API key (there's a free tier).
3. Save the key.

If you skip this, selfies can still work through NanoGPT's image models, but Gemini
("nano-banana") tends to give better, more consistent results.

### 4. (Optional) A Reddit API key — for reading Reddit links

Only needed if you want the bot to read Reddit posts you send it. See the
**Reddit setup** section near the end — it's easy to skip for now and add later.

---

## Step 1: Install Termux

Termux is a terminal app that lets your phone run real programs like Python.

1. Install **Termux** from F-Droid (recommended) or the Play Store:
   - F-Droid: https://f-droid.org/packages/com.termux/
2. Also install **Termux:Boot** (same source) — this lets the bot auto-start when
   your phone reboots. You can do this later too.
3. Open Termux. You'll see a black screen with a text prompt — this is normal.
4. Give it storage permission (lets it access your Downloads folder):
   ```bash
   termux-setup-storage
   ```
   Tap "Allow" when Android asks.

### Battery settings (important!)

Android will try to kill background apps to save battery. To stop it from killing
your bot:

1. Go to **Settings → Apps → Termux → Battery** → set to **Unrestricted**.
2. Do the same for **Termux:Boot** if you installed it.
3. Keep the "Termux is acquiring a wakelock" notification — that's the bot keeping
   itself alive. (The setup below creates this automatically.)

---

## Step 2: Install the required packages

In Termux, run:

```bash
pkg update -y
pkg upgrade -y
pkg install -y python git
```

This installs Python and Git. It may take a few minutes.

---

## Step 3: Download the bot

```bash
cd ~
git clone https://github.com/biggieb327-lgtm/SillyTavernPresets.git
cp -r SillyTavernPresets/telegram-bot ~/telegram-bot
cd ~/telegram-bot
```

(You can delete the `SillyTavernPresets` folder afterward if you want — only
`~/telegram-bot` matters going forward.)

---

## Step 4: Set up the Python environment

Creating a "virtual environment" keeps this bot's packages separate from the rest
of Termux:

```bash
cd ~/telegram-bot
python -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

This downloads and installs everything the bot needs. It can take several minutes
on mobile data — Wi-Fi is recommended.

---

## Step 5: Create your config file (`.env`)

This file holds your secret keys and settings. Copy the example and edit it:

```bash
cp .env.example .env
nano .env
```

`nano` is a simple text editor. Fill in at least these two lines with the values
you saved in the "Before you start" section:

```
TELEGRAM_BOT_TOKEN=your_telegram_token_here
NANOGPT_API_KEY=your_nanogpt_key_here
```

If you got a Gemini key for selfies, also fill in:

```
GEMINI_API_KEY=your_gemini_key_here
```

Everything else in `.env` has a working default — you can leave it as-is for now
and come back to tune it later (model choice, weather location, timezone, etc. —
see `OPS_MANUAL.md` for what each setting does).

To save and exit nano: press `Ctrl+O`, then `Enter`, then `Ctrl+X`.

**Adjust your location/timezone** while you're in there — find these lines and set
them to where you live, so the bot's weather and time-of-day are accurate:

```
WEATHER_LOCATION=Seattle
WEATHER_LAT=47.6062
WEATHER_LON=-122.3321
TIMEZONE=America/Los_Angeles
```

---

## Step 6: Pick (or customize) your character

The bot comes with a sample character, **Nora** (`nora.json`). You can:

- **Use her as-is** — just to get things working, then customize later.
- **Edit her** — `nora.json` is a SillyTavern v2 character card (JSON). You can
  edit her personality, backstory, and first message directly in the file, or
  build a new card in SillyTavern's character creator and export it as JSON.
- **Use a different card** — drop your own `<name>.json` card into
  `~/telegram-bot`, then set `CHARACTER_CARD=<name>.json` in `.env`.

### Selfies (optional)

If you want selfies to work, add a clear photo of the character's face as
`nora_base.png` (or whatever `SELFIE_BASE` is set to in `.env`) in this folder.
Without it, the bot can still describe what she's doing but won't generate images
well.

### Texting style (optional)

`preset.txt` controls how casually/formally she texts (punctuation, emoji use,
message length). The default is a natural, casual texting style — edit this file
if you want something different.

---

## Step 7: First run (test it)

Run the bot directly so you can see any errors:

```bash
cd ~/telegram-bot
venv/bin/python bot.py
```

You should see something like:
```
[state] Loaded history for 0 chat(s).
🚀 Nora is running... (home: /data/data/com.termux/files/home/telegram-bot)
```

Now open Telegram, find the bot you created with BotFather (search its username),
and send `/start`. You should get a greeting message back within a few seconds.

Try chatting normally for a minute. If it responds, you're good!

Press `Ctrl+C` in Termux to stop it before continuing.

**If something goes wrong**, see the Troubleshooting section at the bottom.

---

## Step 8: Keep it running in the background

Right now the bot stops if you close Termux. To run it permanently:

### Install tmux (lets the bot keep running after you close the app)

```bash
pkg install -y tmux
```

### Start the bot in a tmux session

`run.sh` (already included) auto-restarts the bot if it ever crashes, and trims
its log file so it doesn't grow forever.

```bash
chmod +x ~/telegram-bot/run.sh
tmux new -d -s nora "$HOME/telegram-bot/run.sh"
```

Check it's running:
```bash
tmux ls
tail -n 20 ~/telegram-bot/bot.log
```

You should now be able to close Termux entirely (don't "force stop" it — just
switch away or close the app), and your bot will keep running and texting you.

### Auto-start on phone reboot (optional but recommended)

If you installed Termux:Boot in Step 1:

```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start-bots.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
sleep 10
tmux new -d -s nora "$HOME/telegram-bot/run.sh"
EOF
chmod +x ~/.termux/boot/start-bots.sh
```

Now restarting your phone will automatically bring the bot back up after ~10
seconds.

---

## Step 9: Claim ownership / try the features

Send the bot a message (any message) — this marks you as its "owner" so its
proactive heartbeat messages and reminders go to you.

A few commands to try:
- `/memory` — see what she remembers about you
- `/selfie` — ask for a selfie
- `/heartbeat` — trigger a proactive message right now (normally random, every
  few hours)
- `/setmodel` — see/change which AI models power her
- `/settings` — toggle features like web search and link reading

For the **full command reference and how everything works**, see
[`OPS_MANUAL.md`](./OPS_MANUAL.md) in this same folder.

---

## (Optional) Reddit link reading setup

If you want the bot to read Reddit posts/links you send it:

1. Make sure your Reddit account has a **verified email**.
2. Go to https://www.reddit.com/prefs/apps → "create another app..."
3. Choose type **script**, give it any name, and set the redirect URI to
   `http://localhost:8080` (required but unused).
4. Copy the **client ID** (under the app name) and **secret**.
5. Add to `.env`:
   ```
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_secret
   REDDIT_USER_AGENT=CompanionBot/1.0 by u/your_reddit_username
   ```
6. Restart the bot (see "Restarting" below).

If Reddit blocks app creation with a "Responsible Builder Policy" message, your
account likely needs email verification or more account age — Reddit links will
just be skipped gracefully until then.

---

## (Optional) Running a second character

Want a second bot with a different personality? See "Adding a new character" in
[`OPS_MANUAL.md`](./OPS_MANUAL.md) — it reuses the same code and packages you just
installed, so it's quick.

---

## Restarting after changes

Whenever you edit `.env`, a character card, or `preset.txt`, restart the bot:

```bash
tmux kill-session -t nora
tmux new -d -s nora "$HOME/telegram-bot/run.sh"
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `TELEGRAM_BOT_TOKEN not found in .env` | Check `.env` exists in `~/telegram-bot` and the line has no extra spaces/quotes |
| `NANOGPT_API_KEY not found in .env` | Same as above, for your NanoGPT key |
| Bot doesn't respond on Telegram | Make sure you ran `python bot.py` (or it's running in tmux) and check `bot.log` for errors |
| `ModuleNotFoundError: No module named '...'` | Run `venv/bin/pip install -r requirements.txt` again |
| `Conflict: terminated by other getUpdates` | The same token is running in two places — make sure only one process is using this bot's token |
| Bot stops when phone sleeps/screen off | Set Termux battery to **Unrestricted** (Step 1); make sure it's running via `run.sh` in tmux |
| Selfies fail with a 402 error | Your NanoGPT balance is empty, or check `SELFIE_PROVIDER`/API keys |
| Want to see what's happening | `tail -f ~/telegram-bot/bot.log` (Ctrl+C to stop watching) |

For deeper operational details (commands, memory system, scheduled jobs, env
variables), see [`OPS_MANUAL.md`](./OPS_MANUAL.md).
