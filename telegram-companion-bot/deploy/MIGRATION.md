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
`.env` points to — jules uses **`jules.json`**, not `jules_nakagawa.json`.

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

### 10. Declare pilot successful

After 7 days with no issues, jules is permanently on the VPS. Remove its
directory from the phone (or just leave it idle — it won't start without the
tmux session):
```bash
rm ~/jules-bot/bot.pid 2>/dev/null   # clean up stale lock
# Optional: rm -rf ~/jules-bot/      # only after confirming VPS is stable
```

---

## Phase 2: Migrate remaining instances

After the jules pilot succeeds, migrate one bot at a time. Order suggestion:
1. **jules** ✓ (pilot)
2. **cass** — low conversational state, analysis-mode bot
3. **bonnie** — moderate state
4. **emily** — has WSDOT integration (verify `WSDOT_API_KEY` in VPS .env)
5. **priya** — moderate state
6. **nora** — last (she's the home instance, shared venv root, world generator)

For each bot, repeat steps 3–9 above. The soak period can be shorter (2–3 days)
once you've validated the pattern with jules.

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

---

## Phase 3: Retire the phone

Once all six instances are on the VPS and stable (14-day total soak):

1. Stop watchdog on the phone:
   ```bash
   tmux kill-session -t watchdog 2>/dev/null
   crontab -r   # or edit out the watchdog line
   ```
2. Remove the cron/backup if running:
   ```bash
   tmux kill-session -t backup 2>/dev/null
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
2. **Restart on the phone:**
   ```bash
   bash ~/telegram-bot/run-bot.sh ~/jules-bot jules
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
- [ ] Phone stopped / kept as cold spare
- [ ] OPS_MANUAL.md updated with VPS-specific daily ops
- [ ] CLAUDE.md Termux section marked historical
