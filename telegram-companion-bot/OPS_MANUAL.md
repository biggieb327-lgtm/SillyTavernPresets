# Companion Bot — Operations Manual

Day-to-day operation reference for a running bot.

---

## VPS operations

**All seven instances run on the VPS under systemd** (six migrated 2026-07-26; marcus
created 2026-07-29; the Termux phone is empty). Layout:

| Path | What |
|---|---|
| `/opt/telegram-bots/selectors/<instance>/current` | that bot's atomic release selector |
| `/opt/telegram-bots/selectors/<instance>/previous` | that bot's rollback target |
| `/opt/telegram-bots/releases/<git-sha>/` | immutable code, assets, lock, and venv pointer |
| `/opt/telegram-bots/venvs/py312-<lock-sha256>/` | exact hashed dependency layer, reused across code-only releases |
| `/opt/telegram-bots/shared/` | bot-writable group ledgers and the inert `/update` lock; release pointers stay root-owned |
| `/opt/telegram-bots/<instance>/` | per-instance dir: `.env`, card, state, memory |
| `/opt/telegram-bots/world.txt` | shared world context (nora writes it) |
| `/etc/systemd/system/bot@.service` | installed from `deploy/bot-selector@.service`; resolves `%i` through its selector |
| `/etc/systemd/system/bot@<instance>.service.d/10-hardening.conf` | per-instance sandbox; installed from `deploy/bot-hardening.conf` |

Each bot is `bot@<instance>` — `bot@nora`, `bot@bonnie`, `bot@cass`, `bot@emily`,
`bot@priya`, `bot@jules`, `bot@marcus`. The authoritative list is whatever
`systemctl list-units 'bot@*'` reports, not this sentence. All commands below run as
root on the VPS.

### Start, stop, restart
```bash
systemctl start bot@nora
systemctl restart bot@nora
systemctl stop bot@nora
systemctl status bot@nora --no-pager      # running? PID? since when?
```
`Restart=always` in the unit replaces the phone's `.supervise.sh` supervisor — a
crashed bot comes back on its own. **`systemctl stop` stays stopped** (that's the
difference from a crash); `systemctl start` brings it back.

**Always `enable` a unit you intend to survive a reboot** — `start` alone does not:
```bash
systemctl enable bot@nora
systemctl list-units 'bot@*' --no-pager   # what's running right now
systemctl list-unit-files 'bot@*'         # enabled vs disabled
```

### Whole fleet
```bash
for b in $(systemctl list-units 'bot@*' --no-legend --plain \
          | awk '{print $1}' | sed 's/^bot@//; s/\.service$//'); do
  systemctl restart "bot@$b"
done
systemctl list-units 'bot@*' --no-pager
pgrep -af bot.py                          # one line per instance (7 today)
```

### Logs — journalctl replaces tmux attach and bot.log
```bash
journalctl -u bot@nora -f                 # live tail
journalctl -u bot@nora -n 50 --no-pager   # last 50 lines
journalctl -u bot@nora --since "-1 h" | grep -iE 'error|traceback'
journalctl -u bot@nora | grep "STARTUP AUDIT" | tail -1   # what version is live
```
`/errors [N]` from Telegram still works and reads the instance's own `errors.log`.
Note that `errors.log` is *historical* — a tail of it proves what was written, not
what is happening now. For "is it happening right now", use a bounded journalctl
window with a count.

The bot also emits payload-free `OP_EVENT` JSON records at model, external HTTP,
scheduled-job, and Telegram delivery boundaries. Compare latency, failures, and model
fallback across every instance represented in a journal window with one pipeline:
```bash
journalctl -u 'bot@*' --since '24 hours ago' -o cat --no-pager \
  | python3 /opt/telegram-bots/.repo/telegram-companion-bot/deploy/fleet_events.py
```
Add `--boundary model` (or `external_fetch`, `scheduled_job`, `delivery`) to narrow the
report. The journal is the source of truth; the script performs no network calls and
does not require a hosted telemetry service. `OP_EVENTS=0` is the per-instance emergency
kill switch. Events never contain prompts, replies, URLs, chat IDs, tokens, or raw
exception text.

### Deploying
One command per instance; it prepares the full-git-SHA immutable code release and exact
lock-addressed dependency layer, pulls `preset.txt`, that instance's preset layers and
card from `main`, atomically selects the release (keeping `previous`), normalizes
`CHARACTER_CARD`, restarts + enables the unit, and prints release, hash, and STARTUP
AUDIT verification:
```bash
# host: VPS (as root). NOT curl-piped — the repo is private since 2026-07-28 and
# raw.githubusercontent.com 404s. The script fetches + hard-resets the checkout to
# origin/main before copying, so the on-disk copy is correct even if it looks stale.
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh nora
```
`/update`, `update-all.sh` and `sync-cards.sh` are phone-era and manage nothing now.

**Canary rollout:** deploy one instance, verify `/audit`, its journal, and the effective
sandbox, then promote that exact immutable code/runtime release and tested hardening
drop-in to every active bot. Promotion deliberately does not copy mutable cards or
preset layers. Because a running shell cannot replace its own already-loaded body, run
the canary command a second time when this hardening release first updates an older
checkout.
```bash
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh nora
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh nora  # first adoption only
systemctl show bot@nora -p NoNewPrivileges -p PrivateTmp -p PrivateDevices \
  -p ProtectSystem -p ProtectHome -p ProtectProc -p RestrictAddressFamilies
systemd-analyze security bot@nora --no-pager
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh --promote nora
```

**Rollback:** atomically swaps only the named instance's `current` and `previous`, then
restarts it if it was active.
```bash
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh --rollback nora
```

To remove only the sandbox drop-in while leaving the selected code release untouched:
```bash
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh --rollback-hardening nora
```

The sandbox keeps the network available and permits writes only beneath the named
instance, `/opt/telegram-bots/shared`, and `/opt/telegram-bots/world.txt`. The unit's
`HOME` is its instance directory, which is where PDF scratch directories and default
Garmin tokens live after hardening. The deploy copies a legacy shared Garmin token store
once if the instance does not already have one.

### File ownership
Bots run as the `bot` user. Anything you create or unpack in an instance dir must be
handed over, or the bot silently can't read it (`Path.exists()` returns False on a
permissions error, so it looks *missing*, not *forbidden*):
```bash
chown -R bot:bot /opt/telegram-bots/<instance>
```

### The one hard rule: a single poller per token
`telegram.error.Conflict: terminated by other getUpdates request` means two processes
are polling one bot's token. Find the second one before doing anything else:
```bash
pgrep -af bot.py                          # more than one line for an instance = there it is
systemctl list-units 'bot@*' --no-pager   # a unit running that shouldn't be
journalctl -u bot@<instance> --since "-2 min" | grep -c Conflict   # 0 = resolved
```
Two consecutive `/audit`s that disagree on PID or show uptime going backwards are the
signature of a hidden second poller answering in turn. Causes seen in practice: a
phone instance that was never fully stopped, and an instance dir cloned from a live
one whose `.env` still held a working token.

### Health
```bash
systemctl status bot@nora --no-pager | head -12
df -h /opt                                # state + logs live here
grep -c HEALTHCHECK_URL /opt/telegram-bots/*/.env   # dead-man's-switch coverage
```

---

## Commands Reference

### Conversation
| Command | What it does |
|---|---|
| `/start` | Reset history and send the character's opening message |
| `/clear` | Wipe conversation history (keeps long-term memory) |
| `/status` | Dashboard: mood, life arc, today's context, user notes, weather, last chat |
| `/recap` | 2–3 sentence summary of recent conversation |
| `/card` | Show the currently loaded character card |
| `/setcard <filename>` | Swap the character card (restart to fully apply; `/forget` for a clean slate) |
| `/help` | Show all available commands |
| `/menu` | Open the inline button shortcut menu |

### Memory
| Command | What it does |
|---|---|
| `/memory` | View long-term and recent memory summaries + facts |
| `/remember <fact>` | Save a fact to long-term memory |
| `/forget` | Wipe all memory (or `/forget <keyword>` to remove matching facts) |
| `/recall <keyword>` | Search memory for a keyword |
| `/exportmemory` | Download a full memory export as text |
| `/milestones` | View relationship milestones |
| `/pin <fact>` | Pin something that's always in context |
| `/pinned` | List pinned memories |
| `/unpin <n>` | Remove a pinned memory by number |
| `/boundary <text>` | Add a soft boundary note |
| `/boundaries` | List boundaries |
| `/addmem <text>` | Manually add an NPC/world memory (auto-collected too — see below) |
| `/mems` | List all stored NPC/world memories |
| `/delmem <keyword or #>` | Remove an NPC/world memory |
| `/editmem <n> <new text>` | Edit a memory entry by number |
| `/sourcemem <n>` | Show a memory entry's source/provenance |
| `/reviewmem` | List memories pending review (low-confidence extractions); `/reviewmem ok <n>` or `/reviewmem no <n>` to resolve one |
| `/dupefacts` | Diagnostic: flag near-duplicate facts in `facts`/`recent_facts` via embedding similarity (cosine ≥ `MEMORY_DEDUP_SIM`, same threshold `/addmem`'s auto-dedup uses). Reports candidate pairs only — never merges or deletes anything |

### Context Files
These files shape what the character knows and references. All are editable from Telegram.

| Command | What it does |
|---|---|
| `/life [text]` | View or replace the character's current life arc (long-running context) |
| `/life add <text>` | Append a line to the life arc |
| `/people [text]` | View or replace the people in her life |
| `/people add <text>` | Append a person or relationship note |
| `/projects [text]` | View or replace her ongoing projects |
| `/projects add <text>` | Append a project |
| `/schedule [text]` | View or replace her weekly schedule |
| `/schedule add <text>` | Append a schedule entry |
| `/today <note>` | Append a mid-day note (what's happening today) |
| `/note <text>` | Manually add something to what she knows about you |
| `/notes` | List your auto-collected notes, numbered |
| `/notes del <n>` | Remove a specific note by number |
| `/notes clear` | Wipe all user notes |

### Mood & Modes
| Command | What it does |
|---|---|
| `/mood` | Check her current mood |
| `/vibe <name> [Xh]` | Set a timed vibe: `cozy` / `flirty` / `serious` / `chaotic` / `low-energy` / `playful` / `chill` / `in-person` |
| `/vent` | Toggle vent mode (listening only, no advice) |
| `/energy <level>` | Set your energy: `high` / `low` / `crash` |

### Inside Jokes & Wardrobe
| Command | What it does |
|---|---|
| `/addjoke phrase \| meaning \| tone` | Add an inside joke |
| `/jokes` | List inside jokes |
| `/deljoke <id>` | Remove a joke by ID |
| `/wardrobe` | List saved outfits |
| `/addoutfit <desc>` | Add an outfit description |
| `/outfit <n>` | Set current outfit (used in selfie generation) |
| `/deloutfit <n>` | Remove an outfit |

### Selfie
| Command | What it does |
|---|---|
| `/selfie [hint]` | Generate a selfie (optional scene hint) |
| `/selfimage` | View the character's current self-image traits |
| `/reflect` | Trigger the nightly self-reflection now |

### Proactive Messages
| Command | What it does |
|---|---|
| `/heartbeat` | Trigger a proactive check-in now |
| `/nudges` | Show today's proactive message budget |
| `/quiet <h>` | Pause proactive messages for X hours (e.g. `/quiet 3`) |
| `/quiet off` | Cancel quiet mode early |
| `/quietwin add <day> <HH:MM-HH:MM>` | Add a recurring weekly quiet window (e.g. `/quietwin add Fri 23:00-08:00`) |
| `/quietwin list` | List recurring quiet windows |
| `/quietwin del <n>` | Remove a recurring quiet window by number |
| `/away [reason]` | Suppress proactive messages until `/back` or your next message |
| `/back` | Clear away mode |

### Voice
| Command | What it does |
|---|---|
| `/voice` | Toggle voice (TTS) replies on/off |

### Reminders
| Command | What it does |
|---|---|
| `/remindme <when> <msg>` | One-off reminder. When: `30m`, `2h`, `18:30`, `tomorrow 9:00` |
| `/setreminder HH:MM <msg>` | Daily recurring reminder at a fixed time |
| `/reminders` | List all pending reminders |
| `/delreminder <n>` | Cancel a reminder by list number |

### Recurring Tasks (Cron)
| Command | What it does |
|---|---|
| `/cron <schedule> \| <instruction>` | Add a recurring task. Schedule: `daily HH:MM`, `weekly Mon HH:MM` |
| `/crons` | List recurring tasks |
| `/crondel <id>` | Remove a recurring task |

### Payments (if enabled)
| Command | What it does |
|---|---|
| `/addpayment <name> <amount> <day>` | Add a monthly bill |
| `/addevery <name> <amount> <days>` | Add a bill recurring every N days |
| `/payments` | List all bills |
| `/delpayment <n>` | Remove a bill |
| `/editpayment <n> <field> <value>` | Edit a bill field |
| `/week` | Payment summary for the current week |
| `/remindpayments` | Trigger the payment-reminder check now, instead of waiting for its scheduled run |

### Settings & Info
| Command | What it does |
|---|---|
| `/model` | Show every model role and its current value (chat, summary, caption, reaction, mood, vision, fallback, visionfallback) — read-only, no API call |
| `/setmodel <field> <value>` | Change a model (fields: `chat`, `summary`, `vision`, `reaction`, `mood`, `fallback`) |
| `/settings` | Show current settings |
| `/usage` | Token usage stats (subscription limits from NanoGPT) |
| `/chatid` | Show your Telegram user ID |
| `/backup` | Send state.json, memories.txt, user_notes.txt, setting.txt, the current human-readable reminders.json export, and payments.json to chat (`.env` excluded) |

### Operations (admin only — allowlist member or owner)
| Command | What it does |
|---|---|
| `/preset` | Show this instance's preset (voice) layers, per-layer and total token cost, and which layer files are on disk |
| `/preset <names>` | Swap the layer stack live — `/preset core,rp`. Also `add <name>`, `drop <name>`, `reset` (back to `.env`). Effective on the next message, no restart; persists across restarts. Reports the token delta. Kill switch `PRESET_COMMAND=0` (also makes startup ignore a saved override — the recovery path for a stack that ruins a character's voice) |
| `/audit` | Self-audit: `BOT_VERSION`, uptime, error counts, state/disk health. Marks the preset line `(via /preset)` when an override is active |
| `/fleet` | Fleet console (designated instance): probes every peer's admin API — up/down, version, uptime, err/1h. Needs `FLEET_PEERS` in that instance's `.env`; peers need `ADMIN_API_ENABLED=1`. Kill switch `FLEET_CMD=0` |
| `/errors [N]` | Show last N lines of errors.log (default 20, max 50) — check this first for anything odd |
| `/update` | Dead as a deploy path on this private repo — downloads over a raw URL that 404s. Replies pointing at `vps-sync.sh` instead of silently failing. |
| `/restart` | Clean restart via systemd — picks up `.env` edits and a swapped `bot.py` |

If a bot never responds to any of these either, it's not an app-level problem — see
Troubleshooting below (the systemd unit or the process itself may be down).

### Maps (needs `TOMTOM_API_KEY`)
Handlers register unconditionally and reply "Maps aren't set up" without a key, so
these are always in the Telegram command menu regardless of `TOMTOM_ENABLED`.
| Command | What it does |
|---|---|
| `/route <from> to <destination>` | Travel time & directions, e.g. `/route Bellevue to SeaTac airport` |
| `/nearby <thing>` | Places near your shared location, e.g. `/nearby coffee` |
| `/place <name or address>` | Look up an address or business |
| `/food` | Restaurants near your shared location |

### Health (needs Garmin credentials — `GARMIN_EMAIL`/`GARMIN_PASSWORD`, see `.env.example`)
| Command | What it does |
|---|---|
| `/health` | Latest cached metrics from your watch (sleep, resting HR, steps, Body Battery) |
| `/healthnow` | Pull fresh watch data right now, bypassing the scheduled pull (rate-limited — see `GARMIN_LOGIN_COOLDOWN`) |
| `/stress` | Recent sustained-stress reading (needs `STRESS_ALERTS=1`) |

### Western WA traffic (Emily only — needs `WSDOT_API_KEY`)
| Command | What it does |
|---|---|
| `/traffic` | Western WA congestion snapshot (scoped to you if location shared) |
| `/incidents` | Open WSDOT alerts (filtered nearby if live location active) |

---

## Context Files

The bot reads a set of plain-text files from the character's directory to build context for each message. All can be edited directly on the VPS or managed via Telegram commands.

| File | Command | Purpose |
|---|---|---|
| `life.txt` | `/life` | Character's current story arc — what's going on in her life long-term |
| `people.txt` | `/people` | People in her life: names + one-line relationship notes |
| `projects.txt` | `/projects` | Ongoing projects or things spanning multiple days |
| `schedule.txt` | `/schedule` | Weekly routine by day name; today's section is auto-extracted |
| `day.txt` | `/today` | Generated each morning; append mid-day notes with `/today` |
| `user_notes.txt` | `/note`, `/notes` | Auto-collected notes about you; also manually added with `/note` |
| `atlas.txt` | — | Real local places she might naturally reference |

### Atlas file
Each character directory can have an `atlas.txt` (or override the filename via
`ATLAS_FILE=` in `.env`). One place per line — the bot samples a random handful each
message. Lines starting with `#` are comments. Keep this geographically consistent with
wherever the character actually lives now (see her entry in `CLAUDE.md`'s Character
notes) — it's plain text the bot reads verbatim, so nothing stops it from drifting.

### Memes
`/meme [hint]` sends a meme: template image + Pillow-rendered top/bottom text (not
AI-drawn — AI image models render text unreliably, this doesn't). She can also send
one unprompted via a `[meme: top | bottom]` tag when a moment calls for it, mirroring
how the `[selfie: ...]` tag works. Templates live in the shared `meme_templates/`
directory and the font in `fonts/Anton-Regular.ttf`, alongside `bot.py` — shared, not
per-instance. Neither `install-vps.sh` nor `vps-sync.sh` currently copies
`meme_templates/` or `fonts/`; add your own template by dropping a `.jpg` in
`meme_templates/` **in the repo**, then copy it onto the VPS by hand (e.g. from the
`/opt/telegram-bots/.repo` checkout) — no code change needed, but no automated sync
path exists yet either.

### User notes (auto-collection)
After each message you send, the bot runs a background pass to extract upcoming events, appointments, or things you mentioned (job interview Thursday, doctor on Friday, etc.) and appends them to `user_notes.txt`. She references these naturally in conversation when the moment fits.

To see what's collected: `/notes`
To remove an entry: `/notes del <n>`
To add something manually: `/note <text>`

---

## Memory System

Two tiers:

**Long-term** (`summaries`, `facts`)
- Condensed narrative of the full conversation history
- Extracted facts about you
- Promoted from recent memory during nightly reflection

**Recent** (`recent_summaries`, `recent_facts`)
- Shorter window covering roughly the last week
- Refreshed more frequently

All memory lives in `state.json` in the character's directory. Back it up:
```bash
cp /opt/telegram-bots/nora/state.json /opt/telegram-bots/nora/state.backup.$(date +%Y%m%d).json
```
Or use `/backup` from the chat.

### Reminder persistence and rollback

Reminders are the first machine-managed store in the per-instance
`machine-state.sqlite3`. On first startup, the bot imports `reminders.json`, keeps a
dated `reminders.json.pre-sqlite-*.bak`, and verifies the database readback. Every later
save also refreshes `reminders.json`, so `/backup` stays human-readable and restore does
not depend on SQLite tooling. Character cards, presets, memories, and owner-edited text
files remain file-backed.

For immediate rollback, set `REMINDERS_SQLITE=0` in that instance's `.env` and restart;
the bot resumes JSON-only reads and writes. To rebuild SQLite after repairing/restoring
the export, stop the instance, rename `machine-state.sqlite3` (and any `-wal`/`-shm`
sidecars) to dated recovery names, unset the kill switch, and start the instance. The
startup import will rebuild the database from `reminders.json`. Rename rather than
delete so the previous database remains recoverable.

### Automated fleet backup — no VPS equivalent shipped yet

`backup-all.sh` (phone-era, kept only for its rclone/cron notes — DEAD as a runnable
script: it targets Android shared storage at `~/telegram-bot`, and its curl-based fetch
404s now that the repo is private) archived every instance's state files (same list as
`/backup`, `.env` always excluded) and could push off-phone via rclone. Nothing on the
VPS replaces it yet — the only current backup path is per-instance, either `/backup`
from Telegram or manually copying each instance's `state.json` (see "Memory System"
above). A cron'd fleet-backup script for `/opt/telegram-bots/` would be a reasonable
follow-up, but does not exist today.

### Editing memory directly
```bash
nano /opt/telegram-bots/nora/state.json
```
Find your chat ID key and edit `facts`. Changes take effect on the next message.

---

## Proactive Messages (Heartbeat)

The bot sends unprompted check-ins on a random timer (default 2–6 hours) during waking hours.

Before sending, it runs a quick background call to generate a concrete hook — drawing on her current life arc, weather, your notes, and the last exchange — so the message feels like she actually thought of something rather than a templated check-in.

Configure in `.env`:
```
HEARTBEAT_MIN=2          # minimum hours between heartbeats
HEARTBEAT_MAX=6          # maximum hours
PROACTIVE_HOUR_START=9   # don't send before this hour (local time)
PROACTIVE_HOUR_END=21    # don't send after this hour
NUDGE_MAX=3              # max proactive messages per day
```

Pause proactives temporarily: `/quiet 3` (3 hours), `/quiet off` to cancel.

---

## Typing Delay

The bot holds a "typing..." indicator before sending, simulating compose time based on message length. Configurable in `.env`:

```
TYPING_DELAY=1           # set to 0 to disable
TYPING_WPM=45            # simulated typing speed
TYPING_DELAY_MIN=1.5     # minimum seconds
TYPING_DELAY_MAX=8.0     # maximum seconds
```

A ±20% random jitter is applied so the same-length message doesn't always take exactly the same time.

---

## LLM API Configuration

The bot uses any OpenAI-compatible API endpoint. Configure in `.env`:

```
NANOGPT_BASE=https://api.your-provider.com/v1   # base URL (no trailing slash); defaults to NanoGPT if unset
NANOGPT_API_KEY=your-api-key-here
NANOGPT_MODEL=your-default-chat-model
```

### Model slots

The bot uses different models for different tasks — cheap/fast for background work, capable for actual chat:

| Env var | Purpose | Default |
|---|---|---|
| `NANOGPT_MODEL` | Main chat model | required |
| `SUMMARY_MODEL` | Memory summarization | falls back to chat model |
| `REACTION_MODEL` | Auto-reactions, quick calls | falls back to chat model |
| `MOOD_MODEL` | Mood scoring, note extraction, proactive hooks | falls back to reaction model |
| `VISION_MODEL` | Photo descriptions | falls back to chat model |
| `FALLBACK_MODEL` | Retry on error | optional |

Change a model at runtime (no restart): `/setmodel chat gpt-4o`

**Reading the token numbers.** Since v2026-07-26.2 the daily `/audit` and `/usage` totals
are the provider's own counts (labelled `measured`), not estimates. Figures that can only
be estimated — `/preset` layer costs, `/audit`'s `Preset layers:` and `Card:` lines — are
scaled by a calibration ratio each bot measures from its own traffic, and both commands
print which they are showing (`Counts: calibrated x1.28 from 41 measured call(s)`). A
fresh instance shows `estimate — no measured API call yet` until it has held one real
conversation. The ratio is model-specific: expect it to move after `/setmodel`. Kill
switch `TOKEN_CALIBRATION=0` reverts to the raw `len//4` unit that every pre-.2 number in
the docs was measured in.

Change the **voice** at runtime (no restart): `/preset core,rp` — see `PRESET_FILES` in
`.env.example` for what each layer contains. `/preset` can only pick layers present in
that instance's directory — `vps-sync.sh` pulls only what `PRESET_FILES` names, so an
instance can only switch among those until its `.env` names more (then re-run
`vps-sync.sh` to fetch the newly named layer file before the next `/preset`).

---

## Character Configuration

Each character lives in its own directory (`/opt/telegram-bots/<instance>/` on the VPS)
containing:
- `.env` — bot token, API key, model settings
- `nora.json` (or whatever `CHARACTER_CARD=` points to) — persona card
- `state.json` — conversation history, memory, mood (auto-created)
- Context files: `life.txt`, `people.txt`, `projects.txt`, `schedule.txt`, `day.txt`, `user_notes.txt`, `atlas.txt`

The release selected by `/opt/telegram-bots/selectors/<instance>/current` is used only
by that instance. Each bot reads and writes only its own directory plus the explicitly
shared world/group paths in `bot@.service`.

To swap the character card: change `CHARACTER_CARD=` in `.env` and restart. Use `/forget` for a clean memory slate.

---

## Running Multiple Characters

All seven bots have independent root-owned release selectors and run from their own
directories as systemd unit `bot@<instance>` (see "VPS operations" at the top
for start/stop/restart and the whole-fleet loop). Instances: `nora`, `bonnie`, `cass`,
`emily`, `priya`, `jules`, `marcus`.

Each character is fully isolated — separate state, memory, context files, and bot token.
They have no knowledge of each other (except instances opted into the group-chat pilot —
see the next section).

---

## Group chat (experimental)

Two character bots + you in one Telegram group, behind `GROUP_MODE=1`. **Two pilot
pairs are live**: Priya+Jules (the original pilot) and Emily+Marcus (planned since
Marcus's onboarding 2026-07-28, co-location confirmed 2026-08-01). Every other
instance stays fully isolated — being on the VPS doesn't put a bot in a group; only
`GROUP_MODE=1` + `GROUP_PEERS` does. **Read `GROUP_CHAT_DESIGN.md` before touching
this** — the mechanisms (shared ledger, atomic claims, chain cap) exist because
Telegram never delivers one bot's messages to another bot, and the design survived
four adversarial review rounds; don't casually "simplify" it.

Setup, once per pilot pair — steps below use Priya+Jules as the worked example;
substitute the pair's own names and directories for a new one (this is exactly what
Emily+Marcus's setup did):

1. BotFather → `/setprivacy` → **Disable** (or the bot never sees unaddressed group
   messages). Then remove and re-add the bot to the group — Telegram applies privacy
   changes only on re-add.
2. Create the group, add both bots + yourself. Send `/chatid` in it to get the id
   (negative number).
3. **Precondition — both pilots must share one ledger directory** (`GROUP_CHAT_DESIGN.md`
   §0). Bot-to-bot flow is a shared *filesystem* side channel, not Telegram; split hosts
   silently give each bot its own ledger and the loop caps stop being enforced. All seven
   instances run on the VPS under `/opt/telegram-bots/`, and `bot@.service` explicitly
   pins `GROUP_LEDGER_DIR` there so moving code into immutable release directories cannot
   split the ledger. Verify rather than assume:
   ```bash
   # host: VPS
   sudo -u bot test -w /opt/telegram-bots/shared && echo "ledger dir writable" || echo "NOT WRITABLE"
   systemctl show bot@priya bot@jules -p ExecStart | grep -o '/opt/[^ ]*bot\.py'
   grep -H "^[[:space:]]*GROUP_LEDGER_DIR=" /opt/telegram-bots/{priya,jules}/.env
   ```
   The service-level environment is the shared default for every instance; an instance
   `.env` does not override an already-set process variable. The last grep printing
   nothing is the passing result. If the dir is not writable by `bot`, repair ownership
   on `/opt/telegram-bots/shared` before enabling group mode.

   > **Do not try to verify this from the logs before enabling.** The startup config
   > warning that names the resolved path is gated `if GROUP_MODE and GROUP_PEERS`
   > (bot.py:387), so on a not-yet-enabled instance it never prints and an empty
   > `journalctl | grep` means nothing at all. It is a *post*-enable confirmation —
   > see step 6.
4. In `/opt/telegram-bots/priya/.env` and `/opt/telegram-bots/jules/.env` only:
   ```
   GROUP_MODE=1
   GROUP_ALLOWED_CHATS=<the id>
   GROUP_PEERS=<the other character's first name>
   ```
5. One-time smoke test of the atomicity primitives, on the VPS:
   ```bash
   # host: VPS
   sudo -u bot /opt/telegram-bots/selectors/priya/current/venv/bin/python \
     /opt/telegram-bots/selectors/priya/current/bot.py \
     /opt/telegram-bots/priya --claim-test
   ```
   (must print two PASS lines — run it as `bot` so it exercises the real permissions).
6. `systemctl restart bot@priya bot@jules`. **Now** the ledger-dir warning fires (it
   needs `GROUP_MODE` + `GROUP_PEERS`), so confirm both bots resolved the same path:
   ```bash
   # host: VPS
   journalctl -u bot@priya -u bot@jules --since "5 min ago" | grep -o "share this exact directory[^.]*"
   ```
   Then run the acceptance script in `GROUP_CHAT_DESIGN.md` §10 before calling it
   working.

Behavior notes:

- Every other instance ignores groups entirely (fail closed) — adding nora to some
  group does nothing; she answers only `/chatid` there.
- ALL commands except `/chatid` are refused in groups, for everyone, including admins.
  Ops happen in DMs.
- Nothing said in a group ever writes `memories.txt`, `user_notes.txt`, `jokes.json`,
  etc., and `user_notes.txt` / inside jokes are never shown in group prompts — the
  private 1:1 relationship stays private. Group conversation state lives under the
  group's chat_id in each instance's `state.json`.
- `/audit` (in DM) shows a per-group line: ledger size, bot-send budget used, current
  bot chain length — that answers "why did she stop replying to Jules?" (budget or cap).
- Only **one human** in the group, and only **two bots** — both are §9 v1 scope limits,
  not tunables. A second person breaks the two-participant `{{user}}` assumption in the
  prompt; a third bot is N-safe by construction but unvalidated.
- Kill switch: remove `GROUP_MODE=1` from both `.env`s and `/restart` — pure DM
  behavior returns; the ledger file (`group_<id>.jsonl` next to bot.py) goes inert.

---

## Installing a new instance on the VPS

All seven instances already run this way (migration complete 2026-07-26; marcus stood up
directly here 2026-07-29) — this section is for adding an eighth, or rebuilding a host
from scratch, not an alternative to a phone fleet that no longer exists. systemd
(`Restart=always`) replaces what the Termux-era tmux+run-bot.sh+watchdog.sh stack did,
and the whole category of Android-specific bug it existed for (phantom process killer,
Samsung battery management, the `.alive` heartbeat watchdog.sh needed) doesn't apply here.

**Install** (Ubuntu 24.04 recommended, e.g. Contabo's ~€4.50/mo 4 vCPU/6GB RAM tier —
best RAM headroom per dollar for running all seven bots comfortably as of mid-2026 pricing):
```bash
# First install on a fresh box: the repo is private, so fetch install-vps.sh over
# authenticated git rather than raw HTTP — clone once with the read-only deploy key
# (see deploy/MIGRATION.md § "Private-repo deploys"), then run it from the clone.
sudo git clone git@github.com:biggieb327-lgtm/SillyTavernPresets.git /opt/telegram-bots/.repo
sudo bash /opt/telegram-bots/.repo/telegram-companion-bot/deploy/install-vps.sh
```
It's idempotent — re-run it to add another instance or after a `git pull`; it reuses an
existing dependency layer when `requirements.lock` is unchanged, skips already-configured
`.env` files, and only touches units whose config changed. It prompts per instance for a
Telegram token, NanoGPT key, and character card filename, and generates an
`ADMIN_API_TOKEN`.

**Supervision**: `systemctl {status,restart,stop} bot@nora`, logs via
`journalctl -u bot@nora -f` (see "VPS operations" at the top). `/restart` from Telegram
works as before — systemd's `Restart=always` picks the process back up. **`/update`
does not**: it downloads over a raw GitHub URL, which 404s on this private repo; the
handler detects that and replies pointing at `vps-sync.sh` instead. Deploy with
`vps-sync.sh`, not `/update` (see "Deploying" above).

**Admin HTTP API**: opt-in (`ADMIN_API_ENABLED=1`), mirrors `/audit /errors /backup
/update /restart` over HTTP for a non-Telegram client (e.g. a future control-panel
app). Reachable only over a private Tailscale network — the installer prints
Tailscale setup instructions and the API stays bound to loopback (unreachable) until
you set `ADMIN_API_BIND` to the host's tailnet IP. See `.env.example` for the full
`ADMIN_API_*` reference and `CHANGELOG.md` (v2026-07-05.12) for the design rationale.

The native Android control-panel app itself is a separate, later phase — not part of
this installer.

**Migrating from Termux to VPS:** see [`deploy/MIGRATION.md`](deploy/MIGRATION.md) for
the step-by-step runbook (pilot one bot, soak, then migrate the rest).

---

## Logs

On the VPS (all seven instances): `journalctl -u bot@nora -f` — see "Logs" under
"VPS operations" at the top of this file for the full set of commands.

Termux (legacy — no instance runs this way anymore, kept for reference):
```bash
tmux attach -t nora            # live output
tail -f ~/nora-bot/bot.log      # everything the supervisor has seen (trimmed at 5 MB)
tail -f ~/nora-bot/errors.log   # warnings/errors only (rotates at 2 MB)
```
Either way, from Telegram, no shell needed: `/errors [N]` tails `errors.log` straight into chat.

---

## Monitoring

### Dead man's switch (`HEALTHCHECK_URL`)

A crash-loop that dies at import (a missing/bad `.env` value, for example) never
reaches `_self_audit` or the `.alive` heartbeat job — those only run once a bot is
actually up. `HEALTHCHECK_URL` is the one mechanism that catches that case without
you noticing manually: it happened on 2026-07-17, when Nora crash-looped silently
after losing `NANOGPT_API_KEY` from her `.env`, and none of the other monitoring
caught it because none of the six instances had this configured.

**Setup, per bot:**
1. At [healthchecks.io](https://healthchecks.io) (free tier is enough), create one
   check per bot. Set period **30 min**, grace **15 min**.
2. Copy that check's **Ping URL** — `https://hc-ping.com/<uuid>`. This is *not* the
   `healthchecks.io/checks/<uuid>/details/` dashboard link (that's the management
   page, requires login); the Ping URL is a separate field shown on that page.
3. Add it to that instance's `.env`:
   ```
   HEALTHCHECK_URL=https://hc-ping.com/<that-bot's-uuid>
   ```
4. `/restart` that bot so it picks up the new variable.

**Use a distinct check/URL per bot.** Reusing one URL across instances collapses
their signals into a single check, so a dead bot can hide behind another one's
healthy pings.

**Verify:** the check flips to "up" on healthchecks.io within 30 min, or immediately
after sending that bot `/audit` (`_self_audit` fires the ping inline with that job).

---

## Troubleshooting

**Bot doesn't respond**
- Try `/errors` and `/audit` first — if it answers those but not conversation, it's a
  feature-level bug, not a startup crash
- If it answers nothing at all (all seven run on the VPS): `systemctl status bot@nora
  --no-pager` (is the unit even up?), then `journalctl -u bot@nora -n 50 --no-pager`
  (the actual crash traceback, if any) — see `CHANGELOG.md` before assuming a new
  cause; several past crashes here have known, documented root causes
- Watch output live: `journalctl -u bot@nora -f`

**`TELEGRAM_BOT_TOKEN not found`**
- Make sure `.env` exists in the character's directory (not just `.env.example`)
- Check for typos in the key name

**`ModuleNotFoundError: No module named 'requests'` (or similar)**
- On the VPS, do not mutate the selected venv. Re-run the deploy path: it verifies the
  hashed lock, builds a new immutable dependency layer if needed, runs `pip check`, and
  activates only after those pass:
  ```bash
  /opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh nora
  ```
  If the selected release itself was damaged, remove nothing: use `vps-sync.sh
  --rollback nora`, inspect `selectors/nora/current` and `previous`, then repair forward on `main`.

**Model errors / 5xx from the API**
- Set `FALLBACK_MODEL` in `.env` to retry with a different model automatically
- Check your provider's status page

**Vision / selfie errors (503)**
- The vision or image model is temporarily down
- Set `VISION_FALLBACK` in `.env` to automatically try a backup model

**Reminders not firing**
- Requires `python-telegram-bot[job-queue]`: `pip install "python-telegram-bot[job-queue]"`
- Check that `BOT_TIMEZONE` in `.env` is set correctly (e.g. `America/Chicago`)
- Run the release preflight; it checks `machine-state.sqlite3` integrity. If SQLite is
  unreadable, the bot logs the failure and uses the current `reminders.json` rollback
  export. Set `REMINDERS_SQLITE=0` before restart to stay on that legacy path.

**State file corrupted on startup**
- The bot renames `state.json` to `state.json.corrupted` and starts fresh
- Restore from backup: `cp state.json.corrupted state.json` after fixing the JSON

**Proactive messages stopped**
- Check `/nudges` — daily budget may be exhausted
- Check `/quiet` status in `/status`
- Verify `PROACTIVE_HOUR_START`/`END` match your timezone
