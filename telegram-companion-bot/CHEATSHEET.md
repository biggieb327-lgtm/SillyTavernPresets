# Cheat sheet — most-used commands

Quick crib for day-to-day ops. Full reference: `OPS_MANUAL.md`.
Raw base URL used below:
`BASE=https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot`

## Which machine am I on? (check BEFORE running anything)

```bash
uname -o     # "Android" = phone (Termux) · "GNU/Linux" = VPS
```
Prompt `root@vmi…` = VPS. Phone commands on the VPS (and vice versa) have burned
us three times — check first.

## Telegram (any bot, no shell needed)

| Command | What it does |
|---|---|
| `/audit` | Version, uptime, error counts, PID — the only proof a deploy landed |
| `/errors [N]` | Last N error lines from that bot's log |
| `/update` | Downloads bot.py from main, compile-checks, swaps, restarts (**send to ONE phone bot only**, then `/restart` the rest) |
| `/restart` | Restart that bot (picks up swapped bot.py, edited .env, new preset/card) |
| `/backup` | On-demand state backup |
| `/nudges [N]` | Show/set daily proactive-message budget |

## Deploy — pick the path by what changed

| Changed | Phone | VPS |
|---|---|---|
| bot.py | `/update` to one bot → `/audit` → `/restart` others → `/audit` each | vps-sync (below) |
| preset.txt / cards / seeds | curl loop below (or `bash sync-cards.sh`) → `/restart` affected | vps-sync (below) |
| run-bot.sh | update-all one-liner (below) | n/a (systemd, no supervisor) |
| an `.env` | edit on-device → `/restart` that bot → check `/errors` for `[config]` warnings | edit → `systemctl restart bot@<name>` |

**Phone: preset to all phone bots** (then `/restart` each from Telegram):
```bash
for d in nora bonnie cass emily priya; do
  curl -fsSL $BASE/preset.txt -o ~/$d-bot/preset.txt
done
```

**Phone: full redeploy** (bot.py + supervisor, restarts every session):
```bash
curl -fsSL $BASE/update-all.sh | bash
```

**VPS: everything for one instance** (preset + card + bot.py, compile-checked,
CHARACTER_CARD normalized, restart + enable, prints verification):
```bash
curl -fsSL $BASE/deploy/vps-sync.sh | bash -s jules
```

## Verify a deploy actually landed

```bash
# Telegram: /audit → BOT_VERSION matches the release you shipped
# Content changes don't bump BOT_VERSION — hash-check the file instead:
curl -fsSL $BASE/preset.txt | sha256sum        # remote
sha256sum <instance-dir>/preset.txt            # local — must match
```
A matching file with an old process is still the old content — preset and card
load once at startup; a restart is always required.

## VPS service basics

```bash
systemctl status bot@jules --no-pager          # running? PID? since when?
systemctl restart bot@jules
journalctl -u bot@jules -n 50 --no-pager       # recent log / STARTUP AUDIT line
journalctl -u bot@jules --since "-10 min" | grep -c Conflict   # >0 = two pollers
systemctl list-units 'bot@*' --no-pager        # what's running that shouldn't be?
```

## Trouble one-liners

```bash
# Phone: who's running? (empty pgrep for a migrated bot = correct)
tmux ls && pgrep -af bot.py

# Phone: why did the watchdog restart something? It says so before every relaunch:
tail -20 ~/telegram-bot/watchdog.log

# Phone: dead session recovery
tmux kill-session -t <name>; bash ~/telegram-bot/run-bot.sh ~/<name>-bot <name>

# Restart triage — read the EXIT CODE, not the graceful-stop line (corrected 2026-07-25:
# /update and /restart exit via os._exit(0) and log no graceful stop either, so its
# absence proves nothing). 137 = SIGKILL/phantom killer, 143 = SIGTERM/battery manager,
# 0 = clean or owner-initiated:
grep -h "exited (code" ~/*-bot/bot.log | grep -v "code 0" | tail -20

# Only if that shows 137s. NB: `settings` must run under adb — in Termux it fails with
# "Failure calling service settings". Android 11+ can adb to itself over wireless debugging.
adb shell settings get global settings_enable_monitor_phantom_procs   # want: false

# Process census (phantom limit is >32 system-wide; stacked shell loops show as
# paired bash/sleep counts):
ps -o pid,ppid,args -u $(id -u) | awk '{print $3}' | sort | uniq -c | sort -rn | head
```

`telegram.error.Conflict` = two processes polling one token. Find the second
poller (both machines!) before touching anything else — see MIGRATION.md 7b.

## Rules of thumb

- Deploys pull from **main** — unmerged work ships nothing.
- `/audit` (or a hash match + fresh STARTUP AUDIT) is the only "done."
- One `/update`, five `/restart` — never six `/update`s.
- Rollback: phone `~/telegram-bot/bot.py.bak`, VPS `/opt/telegram-bots/bot.py.bak`
  — copy back over bot.py and restart.
- Termux frozen ≠ bots dead: `/audit` from Telegram first, force-close last.
