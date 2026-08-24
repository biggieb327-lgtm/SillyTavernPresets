# Cheat sheet — most-used commands

Quick crib for day-to-day ops. Full reference: `OPS_MANUAL.md` §VPS operations.

All **seven** bots run on the **VPS** under systemd (`bot@<instance>`) — six migrated
2026-07-26, marcus created 2026-07-29.
The phone is empty — its tooling (`/update`, `update-all.sh`, `sync-cards.sh`,
`watchdog.sh`, tmux) manages nothing now. Everything below runs as root on the VPS
unless it says otherwise.

**The repo is private since 2026-07-28**, so `raw.githubusercontent.com` URLs 404 and
`BASE=<raw url>` no longer works. Everything deploys from the authenticated checkout
already on the box:
`REPO=/opt/telegram-bots/.repo/telegram-companion-bot`

## Telegram (any bot, no shell needed)

| Command | What it does |
|---|---|
| `/audit` | Version, uptime, error counts, PID — the proof a deploy landed |
| `/errors [N]` | Last N lines of that bot's errors.log (**historical** — not "right now") |
| `/restart` | Restart that bot (reloads bot.py, .env, preset, card) |
| `/backup` | On-demand state backup |
| `/nudges [N]` | Show/set daily proactive-message budget |
| `/fleet` | Every peer's up/down, version, uptime, errors in one table |

## Deploy

One command per instance — prepares the git-SHA immutable release and exact hashed
dependency layer, pulls preset + layers + card from `main`, atomically selects the
release (keeps `previous`), normalizes `CHARACTER_CARD`, restarts + enables the unit,
and prints verification:

```bash
$REPO/deploy/vps-sync.sh nora
```

Whole fleet:
```bash
for b in $(systemctl list-units 'bot@*' --no-legend --plain \
          | awk '{print $1}' | sed 's/^bot@//; s/\.service$//'); do
  $REPO/deploy/vps-sync.sh "$b"
done
```

Canary code/runtime + sandbox rollout:
```bash
$REPO/deploy/vps-sync.sh nora          # canary only
# run it twice on the first hardening adoption (the first run self-updates this script)
systemctl show bot@nora -p NoNewPrivileges -p ProtectSystem -p ProtectHome -p ProtectProc
# verify /audit and journalctl, then:
$REPO/deploy/vps-sync.sh --promote nora
```
Promotion selects the canary's immutable release and tested sandbox for every active bot;
it does not copy cards or preset layers. Sandbox-only rollback leaves code selected:
`$REPO/deploy/vps-sync.sh --rollback-hardening nora`.

`.env` change only: edit the file → `systemctl restart bot@<name>` → check `/errors`
for `[config]` warnings.

## Verify a deploy actually landed

```bash
# bot.py release: /audit shows the new BOT_VERSION
# content change (no version bump): hash-check instead
sha256sum $REPO/preset.txt                             # checkout (vps-sync fetches it)
sha256sum /opt/telegram-bots/<instance>/preset.txt      # must match
journalctl -u bot@<instance> | grep "STARTUP AUDIT" | tail -1
```
A matching file with an old process is still the old content — presets and cards load
once at startup, so a restart is always required.

## Service basics

```bash
systemctl status bot@nora --no-pager       # running? PID? since when?
systemctl restart bot@nora
systemctl enable bot@nora                  # survive reboot — start alone does NOT
systemctl list-units 'bot@*' --no-pager    # what's running
pgrep -af bot.py                           # one line per instance (7 today)
```

## Logs

```bash
journalctl -u bot@nora -f                  # live tail
journalctl -u bot@nora -n 50 --no-pager
journalctl -u bot@nora --since "-1 h" | grep -iE 'error|traceback'
```

## Trouble one-liners

```bash
# Two pollers on one token (telegram.error.Conflict) — find the second one FIRST
pgrep -af bot.py                                   # >1 line for an instance = there it is
systemctl list-units 'bot@*' --no-pager            # a unit running that shouldn't be
journalctl -u bot@<name> --since "-2 min" | grep -c Conflict    # 0 = resolved

# Bot can't read its own files (perms look like "missing", not "forbidden")
ls -la /opt/telegram-bots/<name>/state.json        # want: bot bot
chown -R bot:bot /opt/telegram-bots/<name>

# Roll back only one bot to its previous immutable release
$REPO/deploy/vps-sync.sh --rollback nora

# Disk (state + journals)
df -h /opt
```

`telegram.error.Conflict` = two processes polling one token. Two consecutive
`/audit`s that disagree on PID, or uptime going backwards, is the same signature.

## Rules of thumb

- Deploys pull from **main** — unmerged work ships nothing.
- `/audit` (or a hash match + fresh STARTUP AUDIT) is the only "done."
- `systemctl start` ≠ `enable`. Unenabled units vanish on reboot.
- `/errors` and `errors.log` are history; a bounded `journalctl` window is *now*.
- Verify migrated/copied state by **content** (dict entry counts), not size or hash.
- Rollback: `$REPO/deploy/vps-sync.sh --rollback <instance>`.

## Phone (historical)

The Termux phone holds only `~/<name>-bot.migrated` rollback dirs and
`~/<name>-migrate.tar.gz` archives, kept until the 14-day soak passes (~2026-08-09).
Nothing runs there. If a `~/<name>-bot` dir ever reappears **and** `watchdog.sh` is
still installed, the watchdog will relaunch that bot and it will fight the VPS for
the token — keep the dirs under their `.migrated` names.
