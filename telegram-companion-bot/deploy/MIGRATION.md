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
tmux kill-session -t jules
```
Confirm it's dead:
```bash
tmux ls | grep jules   # should show nothing
pgrep -f "bot.py.*jules-bot" && echo "STILL RUNNING" || echo "clean"
```

### 4. Transfer state to the VPS

From the phone (or wherever the backup lives):
```bash
# SCP the instance directory (or the backup archive) to the VPS.
# The key files to transfer:
scp ~/jules-bot/state.json      user@vps:/opt/telegram-bots/jules/
scp ~/jules-bot/memories.txt    user@vps:/opt/telegram-bots/jules/
scp ~/jules-bot/user_notes.txt  user@vps:/opt/telegram-bots/jules/
scp ~/jules-bot/reminders.json  user@vps:/opt/telegram-bots/jules/
scp ~/jules-bot/payments.json   user@vps:/opt/telegram-bots/jules/
scp ~/jules-bot/embeddings.json user@vps:/opt/telegram-bots/jules/
scp ~/jules-bot/day.txt         user@vps:/opt/telegram-bots/jules/
scp ~/jules-bot/setting.txt    user@vps:/opt/telegram-bots/jules/

# Transfer seed/context files if not already seeded by install-vps.sh:
scp ~/jules-bot/jules_nakagawa.json user@vps:/opt/telegram-bots/jules/
```

**Alternative — tar the whole instance:**
```bash
tar czf /sdcard/jules-state.tar.gz -C ~/jules-bot \
  state.json memories.txt user_notes.txt reminders.json \
  payments.json embeddings.json day.txt setting.txt \
  jules_nakagawa.json 2>/dev/null
# Then scp the tar to VPS and extract into /opt/telegram-bots/jules/
```

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
