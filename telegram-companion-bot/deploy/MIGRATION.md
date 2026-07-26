# VPS Migration Runbook

Step-by-step guide for moving bot instances from Termux (phone) to a VPS.
Follows the ROADMAP 1.2 plan: pilot one low-state bot (jules), soak, then
migrate the rest one at a time. **Only one process may poll a given bot token
at any time** — stop-then-start, never parallel.

---

## Prerequisites

| Item | Notes |
|------|-------|
| VPS running Ubuntu 24.04 | Recommended: ≥4 vCPU / 6 GB RAM (e.g. Contabo VPS S) |
| SSH access to VPS | Key-based auth recommended |
| Tailscale on VPS | For admin API access from your phone/laptop |
| Phone backup current | Run `bash ~/telegram-bot/backup-all.sh` on the phone first |
| `install-vps.sh` already run once | Sets up repo checkout, venv, systemd unit |

---

## Phase 1: Pilot (jules)

Jules is the lowest-state instance (fewest accumulated memories/notes), making
it the safest to move first. Total downtime: ~2 minutes.

### 1. Verify phone baseline

On the phone, record jules's current health so you can compare post-migration:
```bash
# From Telegram:
/audit   # note version, uptime, error counts

# Or from shell:
tmux attach -t jules   # check it's running clean, then Ctrl+B D to detach
```

### 2. Create a phone backup

```bash
bash ~/telegram-bot/backup-all.sh
```
This archives all state files. The jules backup will be restored onto the VPS.

### 3. Stop jules on the phone

```bash
# 1. If the phone watchdog runs, stop it FIRST (or drop this instance from its list):
#    it relaunches vanished bots and will resurrect jules mid-cutover.
tmux ls | grep -q watchdog && tmux kill-session -t watchdog
# 2. Kill the tmux SESSION — it owns the in-tmux supervisor .supervise.sh, which
#    respawns bot.py within seconds. Killing bot.py alone is NOT enough.
tmux kill-session -t jules
pkill -9 -f "jules-bot/.supervise.sh"   # backstop if the supervisor detached
```
Confirm it's REALLY dead — wait out a respawn cycle, then check both:
```bash
sleep 3
tmux ls | grep jules                                   # should show nothing
pgrep -af jules && echo "STILL RUNNING — kill again" || echo "clean"
```
> **Learned 2026-07-19 (jules pilot):** `tmux kill-session` alone left `.supervise.sh`
> respawning `bot.py`; the new process kept polling jules's token and fought the VPS
> instance with `telegram.error.Conflict` for ~15 min. A `pgrep` caught between respawns
> falsely reads "clean" — always kill the session **and** the supervisor, and confirm
> `pgrep` stays empty after a `sleep`, before starting on the VPS. Also: run these on the
> PHONE (prompt ends `$`), not the VPS — a mis-hosted `kill-session` silently no-ops.

### 4. Transfer state to the VPS

**Tar the WHOLE instance directory — do NOT cherry-pick files.** Real instances carry
more state than any fixed list: the jules pilot had `.episodes.jsonl` (2.3 MB),
`.memory_vectors.json`, `.episodes.model`, `lore_embeddings.json`, and context files
(`life_events.txt`, `places.txt`, `interests.txt`, `reading.txt`,
`time_personality.txt`) that an earlier curated list would have silently dropped —
losing her episodic memory.

From the phone (keeps all dotfiles incl. `.env`; excludes only bulky logs + bytecode):
```bash
cd ~ && tar czf jules-migrate.tar.gz \
  --exclude='jules-bot/bot.log*' --exclude='jules-bot/__pycache__' jules-bot
scp jules-migrate.tar.gz root@<vps>:/opt/telegram-bots/
```
On the VPS — unpack, rename to the systemd instance name, drop phone-only runtime
files, hand to the `bot` user:
```bash
cd /opt/telegram-bots && tar xzf jules-migrate.tar.gz && mv jules-bot jules
rm -f jules/bot.pid jules/.alive jules/bot.py jules/.supervise.sh   # phone-only cruft
chown -R bot:bot jules
```
The dir MUST be named `<instance>` (e.g. `jules`) to match `bot@jules` →
`WorkingDirectory=/opt/telegram-bots/jules`. The card is whatever `CHARACTER_CARD` in
`.env` points to — normalize it to the **repo filename** (jules: `jules_nakagawa.json`,
emily: `emily_harper.json`): a renamed on-device copy silently exempts the instance
from every future card deploy (bit jules on 2026-07-19; step 7c's `vps-sync.sh` fixes
it automatically on first run).

### 5. Verify VPS .env

On the VPS:
```bash
cat /opt/telegram-bots/jules/.env | grep -E "^(TELEGRAM_BOT_TOKEN|NANOGPT_API_KEY|CHARACTER_CARD|TIMEZONE)"
```
Confirm:
- `TELEGRAM_BOT_TOKEN` matches the phone's `~/jules-bot/.env`
- `CHARACTER_CARD=jules_nakagawa.json`
- `TIMEZONE` is set (avoid the tzdata-naive bug from v2026-07-05.5)

Also verify tzdata is installed in the venv:
```bash
/opt/telegram-bots/venv/bin/python -c "import zoneinfo; print(zoneinfo.ZoneInfo('America/Los_Angeles'))"
```

### 6. Set file ownership

```bash
sudo chown -R bot:bot /opt/telegram-bots/jules/
```

### 7. Start jules on VPS

```bash
sudo systemctl start bot@jules
sudo journalctl -u bot@jules -f   # watch for STARTUP AUDIT line
```

Wait for the bot to respond to `/audit` from Telegram. Confirm:
- Version matches the phone's version
- No errors on startup
- Memories/notes are present (`/memory`, check user notes)

### 7b. Enable the unit + prove a single poller

`systemctl start` does not survive a reboot — enable the unit:
```bash
sudo systemctl enable bot@jules
```

Then prove exactly ONE process polls this token:
```bash
systemctl list-units 'bot@*' --no-pager    # only the units you intend, nothing else
pgrep -af bot.py                           # exactly one line per intended instance
journalctl -u bot@jules --since "-10 min" | grep -c Conflict   # 0
```
From Telegram, `/audit` twice a few minutes apart: the PID must be stable and
uptime monotonically increasing. Two consecutive audits that disagree on
PID/uptime/log sizes are the signature of a hidden second poller — different
processes are answering in turn.

> **Learned 2026-07-19 (second incident, same pilot):** a staging dir cloned from
> a live instance sat on the VPS with a populated token in its `.env`; a
> `systemctl start bot@<name>` turned it into a second poller, and its cloned
> `errors.log` (full of old phone tracebacks) poisoned diagnosis for hours.
> Never leave a start-able instance dir seeded from a live instance — park
> anything not yet migrated (`mv nora nora.parked`). Never stack a second
> `TELEGRAM_BOT_TOKEN=` line in an `.env`: the loader takes the last value, and
> a blank-then-filled pair hides which token is live. And when reading pasted
> `/audit`/`/errors` evidence, remember log *content* proves where lines were
> written, not which host is answering — tar'd logs travel.

### 7c. Updating a VPS instance after cutover

`/update` and `sync-cards.sh` are phone tooling and know nothing of the VPS.
For content or bot.py deploys to a VPS instance use:
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/deploy/vps-sync.sh | bash -s -- jules
```
It pulls preset + card + bot.py from main, compile-checks bot.py before the swap
(keeps `bot.py.bak`), normalizes `CHARACTER_CARD` to the repo card filename
(a renamed on-device card silently exempts the instance from every card deploy —
found the hard way with `jules.json`), restarts + enables the unit, and prints
hash + STARTUP AUDIT verification.

### 8. Set up dead man's switch

In the VPS `.env`:
```
HEALTHCHECK_URL=https://hc-ping.com/<your-jules-uuid>
```
Create the check on healthchecks.io: 30-min period, 15-min grace, alert via Telegram.
Restart the unit:
```bash
sudo systemctl restart bot@jules
```

### 9. Soak period (7 days)

Monitor daily:
- `/audit` from Telegram (version, uptime, error count)
- `fleet-status.sh` from the VPS or over tailnet
- healthchecks.io dashboard (any missed pings?)

**What to watch for:**
- Restart storms (uptime resets without your intervention)
- Memory/note issues (data didn't transfer correctly)
- Timezone bugs (reminders firing at wrong times)
- Network issues (NanoGPT timeouts — different from phone's mobile connection)

### 10. Phone-side cleanup (required — do not skip)

> **Learned 2026-07-25 (cass):** leaving the phone instance dir intact and the
> phone scripts un-updated allowed the `setsid`'d watchdog loop (which survives
> closing all Termux sessions) to resurrect a VPS bot on the phone — two pollers
> on one token, silent state divergence. This step is not optional.

**a. Rename the phone-side instance dir** so no phone script can pick it up:
```bash
mv ~/<name>-bot ~/<name>-bot.migrated
```
Do NOT `rm -rf` yet — keep `.migrated` as a rollback until VPS soak completes.
The rename alone stops every phone script (they all guard with `[ -d "$dir" ]`).

**b. Re-curl phone scripts that list instances.**
These are curl-installed once and NOT pulled by `update-all.sh` — a stale copy
is how Cass came back:
```bash
REPO=https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot
curl -fsSL "$REPO/watchdog.sh"    -o ~/telegram-bot/watchdog.sh
curl -fsSL "$REPO/backup-all.sh"  -o ~/telegram-bot/backup-all.sh
curl -fsSL "$REPO/cleanup-all.sh" -o ~/telegram-bot/cleanup-all.sh
```

**c. Kill and restart the `setsid`'d watchdog loop** (it survives closed Termux
sessions — that's by design, but it must run the updated script):
```bash
pkill -f "watchdog.sh --loop"
setsid bash ~/telegram-bot/watchdog.sh --loop >> ~/telegram-bot/watchdog.log 2>&1 &
disown
```

**d. Check for stale boot scripts** in `~/.termux/boot/`:
```bash
ls ~/.termux/boot/
```
If `start-bots.sh` is still there (replaced by `termux-boot-start.sh`), disable it:
```bash
mv ~/.termux/boot/start-bots.sh ~/.termux/boot/start-bots.sh.disabled
```
Termux:Boot runs every executable script in that directory — a stale duplicate
fires the watchdog twice.

**e. Verify the phone Cass/Jules is really dead:**
```bash
tmux ls | grep -E "cass|jules"                          # should show nothing
pgrep -af "bot\.py.*(cass|jules)" && echo "STILL RUNNING" || echo "clean"
```
Then `/audit` on the VPS instance — PID and uptime should be stable across two
checks a few minutes apart (unstable = a second poller is fighting for the token).

### 11. Declare migration successful

After 7 days with no issues and step 10 complete, the bot is permanently on the
VPS. The `.migrated` dir on the phone can be deleted:
```bash
rm -rf ~/<name>-bot.migrated
```

---

## Phase 2: Migrate remaining instances

After the jules pilot succeeds, migrate one bot at a time. Order suggestion:
1. **jules** ✓ (pilot)
2. **cass** ✓ — migrated; phone cleanup learned the hard way (2026-07-25)
3. **bonnie** — moderate state
4. **emily** — has WSDOT integration (verify `WSDOT_API_KEY` in VPS .env)
5. **priya** — moderate state
6. **nora** — last (she's the home instance, shared venv root, world generator)

For each bot, repeat steps 3–11 above (step 10 is the one that bit us — don't
skip it). The soak period can be shorter (2–3 days) once you've validated the
pattern with jules.

### Nora-specific notes

Nora is the `WORLD_GENERATOR=1` instance. When migrating her:
- Ensure `WORLD_GENERATOR=1` is in her VPS `.env`
- The `world.txt` she writes must be readable by all other instances — on the
  VPS this is `/opt/telegram-bots/world.txt` (same shared directory). On the
  phone it was `~/telegram-bot/world.txt`. If bots are split across both
  platforms temporarily, world context won't sync (acceptable — it degrades to
  independent weather, which is the pre-3.2 behavior).
- She was the last session in `update-all.sh` on the phone. Once she's migrated,
  `update-all.sh` and `watchdog.sh` on the phone have nothing left to manage.

### Group-chat pilot (Priya + Jules) — split by the migration

Unlike `world.txt` above, this one does **not** degrade gracefully, and it is already in
effect: jules migrated 2026-07-19, priya did not.

- The bot-to-bot mechanism is a flock'd ledger plus atomic claim files in
  `GROUP_LEDGER_DIR` (defaults to the shared code dir). `GROUP_CHAT_DESIGN.md` §3 assumes
  every peer is on one filesystem — Telegram never delivers one bot's messages to another,
  so the filesystem *is* the channel.
- Split across hosts, each side gets its own copy: `_try_claim` always succeeds on both,
  and `GROUP_BOT_CHAIN_MAX` / `GROUP_DAILY_BOT_BUDGET` are computed from separate ledgers.
  The alternation and chain caps stop working; only each bot's own daily budget bounds it.
- **Therefore:** keep `GROUP_MODE=0` on both until the pair is co-located again — either
  migrate priya, or point both at genuinely shared storage via `GROUP_LEDGER_DIR`.
- Since v2026-07-25.12 a startup config warning prints the resolved ledger path whenever
  `GROUP_MODE` is on with peers configured. Compare it on both hosts; if the two paths
  aren't the same physical directory, coordination is not happening.
- **When migrating priya, verify co-location before re-enabling:** with both bots up, run
  `/chatid` in the group from each, then confirm a single `group_<chat_id>.jsonl` on the
  VPS grows for both — not one file per host.

---

## Phase 3: Retire the phone

Once all six instances are on the VPS and stable (14-day total soak):

1. Stop the watchdog loop on the phone:
   ```bash
   pkill -f "watchdog.sh --loop"
   tmux kill-session -t watchdog 2>/dev/null
   ```
2. Remove boot scripts:
   ```bash
   rm ~/.termux/boot/termux-boot-start.sh
   rm ~/.termux/boot/start-bots.sh.disabled 2>/dev/null
   ```
3. Update OPS_MANUAL.md: mark Termux-specific sections as historical.
4. Update CLAUDE.md: move Termux quirks to a "Historical (phone era)" section.
5. Optionally keep the phone as a cold spare — `update-all.sh` still works if
   you ever need to fall back.

---

## Rollback

If anything goes wrong during migration:

1. **Stop the VPS instance immediately:**
   ```bash
   sudo systemctl stop bot@jules
   ```
2. **Restart on the phone** (if the instance dir was renamed per step 10, undo
   that first):
   ```bash
   mv ~/<name>-bot.migrated ~/<name>-bot 2>/dev/null
   bash ~/telegram-bot/run-bot.sh ~/<name>-bot <name>
   ```
3. The phone's state files are untouched (we copied, not moved). The bot picks
   up right where it left off.

Never run the same bot token on both platforms simultaneously — Telegram will
deliver updates to only one of them (unpredictably), causing missed messages
and state divergence.

---

## Post-migration checklist

- [ ] All 6 bots responding to `/audit` on VPS
- [ ] healthchecks.io green for all 6 (14 days)
- [ ] Tailscale connected, `fleet-status.sh` works over tailnet
- [ ] `ADMIN_API_BIND` set to tailnet IP (not 127.0.0.1)
- [ ] Every phone instance dir renamed `.migrated` then deleted (step 10a/11)
- [ ] Phone scripts re-curled after each migration (step 10b)
- [ ] Watchdog loop restarted with clean scripts (step 10c)
- [ ] Stale boot scripts removed (step 10d)
- [ ] Phone stopped / kept as cold spare
- [ ] OPS_MANUAL.md updated with VPS-specific daily ops
- [ ] CLAUDE.md Termux section marked historical
