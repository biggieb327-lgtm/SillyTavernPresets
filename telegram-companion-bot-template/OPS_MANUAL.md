# Companion Bot — Operations Manual

This covers day-to-day operation of your Telegram companion bot once it's set up. If
you haven't installed it yet, start with [`SETUP_GUIDE.md`](./SETUP_GUIDE.md).

Everything below assumes the layout from the setup guide: the bot's code and data live
together in `~/telegram-bot` (folder name is up to you), run via `run.sh` in a tmux
session.

A bot's **identity and data** live alongside `bot.py`: `.env` (token, models, knobs),
its character card JSON, `preset.txt` (texting-style instructions), `state.json`
(memory/mood/overrides), `owner_chat.txt`, `bot.log`, `reminders.json`, its selfie base
image, and optional `appearance.txt` / `setting.txt` / atlas file. If payments
reminders are enabled, it also gets `payments.json`.

---

## Daily operations

**Status:**
```bash
tmux ls                       # expect your bot's session name
pgrep -af bot.py               # expect one process
tail -n 15 ~/telegram-bot/bot.log
```

**Restart:**
```bash
tmux kill-session -t companion 2>/dev/null
pkill -9 -f run.sh; pkill -9 -f bot.py; sleep 2
tmux new -d -s companion "$HOME/telegram-bot/run.sh"
```

**Stop:** `tmux kill-server; pkill -9 -f run.sh; pkill -9 -f bot.py`

Logs auto-trim to the last 2000 lines on each (re)start. `run.sh` auto-restarts a
crashed bot after 5s and holds a wake-lock. On phone reboot, Termux:Boot runs
`~/.termux/boot/start-bots.sh`, which starts the bot.

---

## Updating the bot's code

`bot.py` is the shared engine — your character, memory, and settings all live in
separate files, so updating it doesn't touch your data:

```bash
curl -L -o ~/telegram-bot/bot.py https://raw.githubusercontent.com/<your-username>/<your-repo>/main/bot.py
# then restart (above)
```

(Replace the URL with wherever you keep your copy of this repo — e.g. your own fork.)

---

## Running a second character

This codebase supports multiple bots from one shared `bot.py`, each with its own
folder, token, and data:

1. @BotFather → `/newbot` → copy the **new** token (each bot needs its own).
2. `mkdir ~/<name>-bot`, put that character's SillyTavern v2 card in it.
3. Create `~/<name>-bot/.env` (copy your existing `.env` as a template) — set at
   minimum `TELEGRAM_BOT_TOKEN`, `NANOGPT_API_KEY`, `CHARACTER_CARD=<card>.json`.
4. Optional per-bot files: `<name>_base.png` + `SELFIE_BASE=` (selfies),
   `appearance.txt` (selfie look), `setting.txt` (world overlay), atlas file,
   `preset.txt` (texting style).
5. Launch with `run-bot.sh`, which points the shared code at that folder:
   `tmux new -d -s <name> "$HOME/telegram-bot/run-bot.sh $HOME/<name>-bot"`
6. Message the new bot once (any message claims you as heartbeat owner).
7. Add a line to `~/.termux/boot/start-bots.sh` so it survives reboots.

---

## Telegram commands

`/start` (reset chat + greeting) · `/clear` (wipe recent history) ·
`/memory` `/remember <fact>` `/forget` (long-term memory) · `/selfimage` (self-image +
next-conversation goal) · `/reflect` (run nightly reflection now) · `/selfie [scene]` ·
`/heartbeat` (proactive message now) · `/remindme <when> <msg>` `/reminders`
`/delreminder <n>` · `/cron <schedule> <what to do>` `/crons` `/crondel <n>` ·
`/backup` (DM data files) · `/model` `/setmodel` `/settings` `/usage` `/chatid`

`/remindme` when-formats: `30m` `2h` `3d` · `18:30` · `tomorrow [9:00]` · `2026-07-01 [14:30]`

`/cron` schedule formats: `daily HH:MM` or `every Nh`/`every Nm`.
Example: `/cron daily 08:00 check the news and tell me something interesting`

**Payments reminders (optional):** `/addpayment <name> <amt> <day> [xN]` ·
`/addevery <name> <amt> <start> <interval> [count]` · `/payments` ·
`/editpayment <n> <field> <val>` · `/delpayment <n>` · `/week` or `/remindpayments`

> **Editing a payment's date:** `/payments` is sorted by next due date, so changing a
> payment's `day`/`start`/`interval`/`count` **reshuffles the list numbering**. After any
> such edit, **re-run `/payments`** to get the current numbers before making further edits
> by number — otherwise `/editpayment 4 ...` may hit the wrong one. (The edit confirmation
> message reminds you when a change reorders the list.)

---

## Texting-style preset (`preset.txt`)

The bot's "how you text" system instructions live in `preset.txt` next to `bot.py`
(plain text, no special format). Edit it to change phrasing/punctuation rules,
asterisk-action usage, energy variation, etc. without touching `bot.py`. If the file is
missing, `bot.py` falls back to its built-in default. Controlled by `TEXTING_REALISM` /
`/settings texting_realism on|off`. Restart the bot after editing.

---

## Live config: `/setmodel` and `/settings`

Change models and feature toggles **without editing `.env` or restarting** — changes
persist to `state.json` and survive restarts.

**`/setmodel`** — shows the model assigned to each role (chat, summary, reaction, mood,
vision, fallback, visionfallback) plus the total count of models on your NanoGPT
subscription.
- `/setmodel search <term>` — list subscription models matching `<term>`, numbered.
- `/setmodel <role> <number>` — pick a model from the last search/list shown.
- `/setmodel <role> <exact name>` — set directly by full model id.

**`/settings`** — shows and toggles:
- `search` (web search), `links` (link reading), `reactions`, `mood`, `texting_realism`,
  `device_render` — all on/off (`/settings <name> on|off`)
- `ambient_chance`, `selfie_chance` — proactive-message hint probabilities, 0–1
  (`/settings <name> 0.25`)

---

## Automatic behaviors

- **Heartbeat:** proactive in-character message at a random interval (`HEARTBEAT_MIN_HOURS`–
  `HEARTBEAT_MAX_HOURS`, default 2–6h) when idle; quiet hours 23:00–08:00. Owner
  auto-claims on first interaction (any message). Occasionally includes an ambient
  "what are you up to" hint (`ambient_chance`, needs `SEARCH_ENABLED`) or a proactive
  selfie hint (`selfie_chance`).
- **Memory (two-tier):**
  - *Conversation window* — recent messages kept **verbatim** until they're older than
    **`SHORT_TERM_HOURS` (default 48h)** *or* the window passes **20 messages** (count
    cap), whichever first; always keeps the last 10 for continuity.
  - *Recent memory* — messages leaving the window are summarized into
    `recent_summaries`/`recent_facts`, covering roughly the **last week**. Facts
    auto-consolidate toward `RECENT_FACTS_TARGET` (default 20) when they exceed
    `RECENT_FACTS_MAX` (default 30).
  - *Long-term memory* — every `PROMOTION_INTERVAL_DAYS` (default 7), durable/identity
    facts get folded from recent memory into `summaries`/`facts`, which persist
    **indefinitely**. Long-term facts auto-consolidate toward `LONG_FACTS_TARGET`
    (default 15) when they exceed `LONG_FACTS_MAX` (default 22).
  - `/memory` shows both tiers; `/forget` wipes both (current conversation kept).
- **Nightly reflection (`REFLECTION_TIME`, default 03:00):** updates self-image
  (`/selfimage`) traits, resolves open recommendations, sets a "next conversation goal"
  the character may naturally bring up later, and runs long-term memory promotion.
- **Mood:** drifts with contact frequency (~24h half-life); colors tone and selfies.
- **Reactions:** a fast model (`REACTION_MODEL`) decides occasional emoji reactions to your
  messages (background); toggle with `/settings reactions on|off`.
- **Selfies:** img2img off the base portrait, with randomized framing / expression /
  activity / camera-look / outfit, mood- and weather-aware. SFW.
- **Link reading:** pasting a URL has the bot fetch and react to its content. Reddit links
  go through Reddit's OAuth API (`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` — see below);
  other links use a basic HTML fetch. Toggle with `/settings links on|off`.
- **Web search:** `[search:]` tags let the model look things up (DuckDuckGo), with a
  "let me check" message first. Toggle with `/settings search on|off`.
- **Fallback model:** if the chat model returns a 5xx / times out / rate-limits (429), the
  request auto-retries on `FALLBACK_MODEL` (and `VISION_FALLBACK` for photos) if set. It
  does *not* fall back on 4xx (real config errors).
- **Payments reminders (optional):** weekly digest of bills due, on `REMINDER_WEEKDAY` at
  `REMINDER_TIME` (default Thursday 09:00, covering Thu→next Wed). Disable with
  `PAYMENTS_ENABLED=0`.
- **Backup:** weekly on `BACKUP_WEEKDAY`/`BACKUP_TIME` (default Sunday 09:05), the bot
  DMs its data files (`state.json`, `reminders.json`, and `payments.json` if payments
  are enabled). Restore = copy files back into the bot's folder + restart.
- **Logs:** `bot.log` auto-trims to the last 2000 lines on each (re)start.
- **Live context:** real date/time + local weather injected every message.

## Key .env knobs

**Models:** `NANOGPT_MODEL` (chat) · `FALLBACK_MODEL` · `SUMMARY_MODEL` ·
`VISION_MODEL` + `VISION_FALLBACK` (photos) · `REACTION_MODEL` · `MOOD_MODEL` ·
`SELFIE_MODEL/_BASE/_SIZE/_GUIDANCE/_STEPS`
(Most of these can also be changed live with `/setmodel` — see above.)

**Behavior:** `REACTIONS_AUTO` · `MOOD_AUTO` · `TEXTING_REALISM` · `DEVICE_RENDER` ·
`HEARTBEAT_MIN_HOURS`/`MAX_HOURS` · `QUIET_START/END` ·
`SEARCH_ENABLED`/`SEARCH_RESULTS` · `LINK_READING`/`LINK_FETCH_TIMEOUT`/`LINK_MAX_CHARS`
(Most of these can also be toggled live with `/settings` — see above.)

**Reddit link reading:** `REDDIT_CLIENT_ID` · `REDDIT_CLIENT_SECRET` · `REDDIT_USER_AGENT`
— free "script" app at reddit.com/prefs/apps (requires a verified Reddit account; if
unset, Reddit links just get a "couldn't open that" reply).

**Memory:** `SHORT_TERM_HOURS` · `RECENT_FACTS_MAX`/`RECENT_FACTS_TARGET` ·
`LONG_FACTS_MAX`/`LONG_FACTS_TARGET` · `PROMOTION_INTERVAL_DAYS` ·
`BELIEF_TRAITS` · `RECS_MAX`

**World:** `WEATHER_LOCATION/LAT/LON`, `TIMEZONE` · `CHARACTER_CARD` · `ATLAS_FILE`

**Payments/jobs:** `PAYMENTS_ENABLED` · `REMINDER_TIME/WEEKDAY` · `BACKUP_WEEKDAY/TIME` ·
`REFLECTION_TIME`

After editing `.env`, restart the bot. (Settings changed via `/setmodel` or `/settings`
override `.env` until changed again — they're stored in `state.json`.)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Bot not responding | `tmux ls` + `tail bot.log`; restart if needed |
| `Conflict: terminated by other getUpdates` | Two processes share one token — kill all, restart; confirm each bot's `.env` token is unique |
| `ModuleNotFoundError` | Launcher must use the venv Python — it does; if venv broke: `~/telegram-bot/venv/bin/pip install -r requirements.txt` |
| Frequent `API Error: 500` | Set `FALLBACK_MODEL=` in `.env` so it auto-retries on another model |
| Heartbeat silent | Message the bot once (claims owner); check `owner_chat.txt`; remember quiet hours + the random window resets on restart |
| Wrong time / reminder hour | `pip install tzdata`; phone clock/timezone settings |
| `/editpayment` hit the wrong bill | The list reordered after a date change — re-run `/payments` and use the new number |
| Vision/selfie 400 errors | Model id in `.env` invalid for that job; selfie 402 = NanoGPT balance empty |
| Bot dies when phone sleeps | Termux + Termux:Boot battery **Unrestricted**; wake-lock notification present |
| Hand-edited `bot.py` lost | Expected — it's shared code; put customizations in `.env`/per-bot files instead |
| Link reading "couldn't open that" for Reddit | Set `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` (see Reddit knobs above); Reddit blocks plain scraping |
| `[link] fetch failed: ...` in `bot.log` | Check the printed error — site may be blocking scrapers, or a transient network issue |
