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

**RENAME THE DIRECTORY FIRST.** This is the whole trick — do not reorder these:
```bash
# 1. Remove the resurrection vector. watchdog.sh's check_instance starts with
#    `[ -d "$dir" ] || return`, so a renamed dir is invisible to it — permanently,
#    in every mode (its own tmux session OR cron). Do this BEFORE any kill.
mv ~/jules-bot ~/jules-bot.migrated
# 2. Now kill the stack: session, then the supervisor, then any straggler bot.py.
tmux kill-session -t jules
pkill -9 -f "jules-bot/.supervise.sh"
pkill -9 -f "jules-bot"
```
Confirm it's REALLY dead — wait out BOTH resurrection layers before believing it:
```bash
sleep 10
tmux ls | grep jules                                   # should show nothing
pgrep -af jules && echo "STILL RUNNING — kill again" || echo "clean"
```
If anything comes back, read the watchdog's own reasoning — it logs before every
relaunch and names the instance:
```bash
tail -20 ~/telegram-bot/watchdog.log
```

> **Learned 2026-07-19 (jules pilot):** `tmux kill-session` alone left `.supervise.sh`
> respawning `bot.py`; the new process kept polling jules's token and fought the VPS
> instance with `telegram.error.Conflict` for ~15 min. A `pgrep` caught between respawns
> falsely reads "clean" — always kill the session **and** the supervisor, and confirm
> `pgrep` stays empty after a `sleep`, before starting on the VPS. Also: run these on the
> PHONE (prompt ends `$`), not the VPS — a mis-hosted `kill-session` silently no-ops.

> **Learned 2026-07-26 (bonnie, third recurrence — this is why the rename moved to
> step 1):** there are TWO independent resurrection layers, and the old kill order
> defeated one while *arming* the other. `.supervise.sh` reacts to `bot.py` dying
> (seconds). `watchdog.sh` reacts to the **tmux session** being missing — which is
> exactly what a correct kill produces — and relaunches the entire stack via
> `run-bot.sh` on its next cycle (up to 5 min later). So the kill genuinely works,
> `pgrep` genuinely reads clean, and then everything returns minutes later with a
> fresh session timestamp. Two `tmux ls` outputs whose "created" times differ by one
> watchdog interval are the signature. Killing the watchdog's tmux session does not
> help if it runs from cron; renaming the instance dir defeats it in both modes.
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

### 4b. Verify the transferred state, by content — not presence, size, or hash alone

`/audit`'s "State file" reading only proves `state.json` exists and parses; it says
nothing about whether it's the *real* history or an empty shell the VPS process
built from scratch after starting with none. Compare structurally on both sides:
```bash
python3 -c "
import json
d = json.load(open('<path-to-state.json>'))
for k in ('conversation_history','facts','moods','summaries','milestones','pinned'):
    print(k, ':', len(d.get(k, {})), 'entries')
"
```
Run against the phone's last backup archive and the VPS's live file; matching counts
across every key confirm nothing was dropped. A byte-identical hash is NOT required —
real activity on the VPS after transfer legitimately changes the file — but the dict
*keys and counts* must line up.

> **Learned 2026-07-26 (priya):** a re-attempted migration is a different risk profile
> than a first attempt. Priya's phone directory had somehow lost its live `state.json`
> sometime between an earlier (evidently incomplete) migration attempt that morning and
> this evening's — the phone's `.supervise.sh` kept the bot running fine on empty state
> in the meantime, with no error to flag the gap. `/audit`'s "State file: MISSING" only
> surfaced because the phone process happened to answer that particular command instead
> of the VPS one — a symptom easy to miss if you don't know which host answered. That
> morning's backup tar (`<instance>-migrate.tar.gz`), not the live phone directory,
> turned out to be the trustworthy source once compared this way. If a bot has ever had
> a prior incomplete cutover attempt, verify against that instance's most recent backup
> archive, not just whatever the live phone directory currently holds.

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
# host: vps (as root). Superseded 2026-07-28: the repo is private, raw URLs 404.
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh jules
```
It pulls preset + card + bot.py from main, compile-checks bot.py before the swap
(keeps `bot.py.bak`), normalizes `CHARACTER_CARD` to the repo card filename
(a renamed on-device card silently exempts the instance from every card deploy —
found the hard way with `jules.json`), restarts + enables the unit, and prints
hash + STARTUP AUDIT verification.

### 8. Set up dead man's switch

Create the check on healthchecks.io first (45-60 min period, 15-min grace, alert via
Telegram — the bot pings every 30 min, so a 30-min period leaves zero headroom and
flaps), then copy **its full ping URL** into the instance's `.env` as
`HEALTHCHECK_URL`. The value is the complete URL from the dashboard and nothing else:
`https://hc-ping.com/` followed by the check's UUID, 56 characters total.

Do not hand-assemble it, and do not paste a full URL after an existing
`https://hc-ping.com/` — that produces
`https://hc-ping.com/https://hc-ping.com/<uuid>`, which hc-ping answers with HTTP 400.

```bash
sudo systemctl restart bot@jules
```

**Verify it — the ping is not self-announcing.** Before v2026-07-26.5 a rejected ping
logged nothing at all (`requests` doesn't raise on 4xx), and five of six instances ran
for weeks on the doubled URL above with every audit line reading `[audit] OK`. Test the
URL the bot actually uses, from its own `.env`:
```bash
for b in nora bonnie cass emily priya jules; do
  url=$(grep '^HEALTHCHECK_URL=' /opt/telegram-bots/$b/.env | cut -d= -f2- | tr -d '"')
  printf '%s: len=%s ' "$b" "${#url}"
  curl -fsS -o /dev/null "$url" && echo OK || echo FAILED
done
grep -h '^HEALTHCHECK_URL=' /opt/telegram-bots/*/.env | sort -u | wc -l   # want one per instance
```
Every line must read `len=56 OK`. The distinct-URL count matters as much as the pings:
if two instances share a UUID, one bot's pings keep the check green while the other
dies unseen. On v2026-07-26.5+, a rejected ping also logs a loud warning and counts a
`healthcheck_rejected` error visible in `/audit`.

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
**If you followed step 3 correctly this is already done** — the rename moved to the
top of the stop sequence on 2026-07-26, because doing it here (after cutover) left
the watchdog free to resurrect the instance *during* the cutover window. Verify
rather than re-run:
```bash
ls -d ~/<name>-bot ~/<name>-bot.migrated 2>/dev/null
```
Do NOT `rm -rf` yet — keep `.migrated` as a rollback until VPS soak completes.
The rename alone stops every phone script (they all guard with `[ -d "$dir" ]`).

**b. Re-curl phone scripts that list instances.** *(Historical — this step belonged to
the cutover. The phone is empty, and these URLs 404 now that the repo is private.)*
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

**Her tmux session may be named `nora` OR `telegram-bot`.** Check `tmux ls` and kill
whichever exists — `watchdog.sh` checks both names against the same dir for exactly
this reason.

**Do NOT rename `~/telegram-bot/`.** That is the shared CODE dir (venv, `bot.py`, all
the ops scripts) — her *instance* dir is `~/nora-bot`. Renaming the code dir breaks
every remaining phone script.

**The step-3 rename does not silence the watchdog for nora — she is the one
exception.** The other five instances are checked by `check_instance`, which opens
with `[ -d "$dir" ] || return`, so a renamed dir makes them invisible. Nora's branch
in `run_checks` bypasses that function entirely:
```bash
if [ "$nora_up" = false ]; then
  _log "RELAUNCH nora: session down (...)"
  bash "$BOT_SRC/run-bot.sh" "$nora_dir" nora     # no [ -d ] guard
fi
```
With `~/nora-bot` renamed, `nora_up` is false forever, so the watchdog retries every
cycle. **Nothing actually starts** — `run-bot.sh` has its own guard (`cd` fails →
"Instance folder not found" → `exit 1`) — so there is no second poller, only an
endless `RELAUNCH nora` in `watchdog.log`.

The real hazard is conditional: **if `~/nora-bot` ever reappears** (restoring a backup
to inspect it, an rsync, a stray `mkdir`), the watchdog starts her within one cycle
and she immediately fights the VPS instance for the token. Her directory must stay
gone under its `.migrated` name.

**So nora's cutover gets one step the others don't — actually retire the watchdog**,
which by then has nothing left to supervise:
```bash
tmux ls | grep -q watchdog && tmux kill-session -t watchdog
crontab -l | grep -i watchdog     # it may run from cron instead of (or as well as) tmux
crontab -e                        # remove the watchdog line if present
```
Verify it stays gone across one full interval (default 300s) before declaring done:
```bash
sleep 310; tail -5 ~/telegram-bot/watchdog.log     # no new RELAUNCH entries
```

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

---

## Private-repo deploys (2026-07-28)

The repo went private so character cards aren't published via raw URLs. **Anonymous
`raw.githubusercontent.com` fetches 404 on a private repo**, which breaks every
curl-based deploy path at once — `vps-sync.sh`, `install-vps.sh`, and bot.py's own
`/update`. `deploy/vps-sync.sh` therefore syncs from a **git checkout** on the VPS
instead. A checkout authenticates once and behaves identically whether the repo is
public or private, so this migration can be done *before* the visibility flip with no
window where the fleet is unreachable.

### One-time setup (VPS, as root)

**The checkout already exists.** `install-vps.sh` has maintained one at
`/opt/telegram-bots/.repo` since 2026-07-06 (install-vps.sh:33) and chowns it to
`bot:bot` (line 69). Do **not** clone a new one — `git clone` into that path fails with
"already exists and is not an empty directory", and a `chown` to root would be reverted
by the next `install-vps.sh` run. Setup is only the key and the remote:

```bash
# host: vps
ssh-keygen -t ed25519 -f /root/.ssh/stpresets_ro -N '' -C "vps-$(hostname)-stpresets-ro"
cat /root/.ssh/stpresets_ro.pub
# → add that line under the repo's Settings → Deploy keys, READ-ONLY (leave write unticked)
git config --global --add safe.directory /opt/telegram-bots/.repo
git -C /opt/telegram-bots/.repo remote set-url origin git@github.com:biggieb327-lgtm/SillyTavernPresets.git
GIT_SSH_COMMAND="ssh -i /root/.ssh/stpresets_ro -o IdentitiesOnly=yes" git -C /opt/telegram-bots/.repo fetch origin main && echo "deploy key OK"
```

Four traps, all hit for real on 2026-07-28:

- **"Key already in use"** when adding the deploy key means that public key is already
  registered elsewhere in the account — a key can be attached to only one place. Do not
  delete the old one (something depends on it); generate a second key under a distinct
  filename. Deploy keys are per-repo by design.
- **"dubious ownership"** is expected, not a fault: the checkout is `bot`-owned and you
  are root. The `safe.directory` line above fixes it for interactive use;
  `vps-sync.sh` passes `-c safe.directory=` on every git call so it works without it.
- **The host key prompt.** The first SSH connection asks you to accept
  `github.com`'s fingerprint. `vps-sync.sh` runs non-interactively, so do this
  interactive fetch once first or the first real deploy stalls on an unanswered prompt.
- **`ssh-keygen` offering to overwrite** an existing key: answer **n**. Overwriting
  invalidates whatever that key already authenticates.

### First run only: move the working tree by hand

`git fetch` updates `origin/main` but **not** the working tree, and the script that
hard-resets the tree lives inside the tree. On a checkout older than 2026-07-19,
`deploy/vps-sync.sh` does not exist yet at the checked-out commit, so the first run has
to be bootstrapped:

```bash
# host: vps
git -c safe.directory=/opt/telegram-bots/.repo -C /opt/telegram-bots/.repo status --porcelain | head
git -c safe.directory=/opt/telegram-bots/.repo -C /opt/telegram-bots/.repo reset --hard origin/main
git -c safe.directory=/opt/telegram-bots/.repo -C /opt/telegram-bots/.repo log --oneline -1
```

Check `status --porcelain` is empty first — `reset --hard` discards local changes, and
this checkout may not have been touched in weeks. Every run after this one is
self-maintaining: the script fetches *and* resets before it copies anything.

### Deploying from then on

The script is no longer curl-piped into bash — run it from the checkout:

```bash
# host: vps
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh <instance>
```

It fetches and hard-resets the checkout to `origin/main` first, prints the resolved
HEAD, and compares repo-vs-instance hashes at the end, so a stale checkout can't
silently deploy old content.

### Order of operations for the flip

Do **not** flip visibility first — once private, you cannot deploy the fix that teaches
the fleet to authenticate, because that fix would have to arrive over the channel that
just broke.

1. Deploy-key setup above — key, deploy-key registration, SSH remote, one
   interactive fetch to accept the host key. Works while the repo is still public.
2. Run `vps-sync.sh` once from the checkout on ONE instance and confirm the
   `checkout HEAD` line, the matching repo/local hashes, and its STARTUP AUDIT. This is
   the step that proves the new path; everything after it is repetition.
3. Run it for the remaining instances.
4. **Then** flip the repo to private (GitHub → Settings → General → Danger Zone).
5. Re-run `vps-sync.sh` on one instance to prove the private path works end to end. The
   fetch is the only part visibility can break, and it is the first thing the script
   does, so a failure here is loud and harmless.

### What stays broken, deliberately

`/update` from Telegram cannot work against a private repo — raw URLs have no way to
authenticate. As of v2026-07-28.3 it detects the 401/403/404 and replies with the
`vps-sync.sh` command instead of a bare HTTP error. The phone-era scripts
(`update-all.sh`, `sync-cards.sh`, `watchdog.sh`, `new-bot.sh`, `backup-all.sh`,
`cleanup-all.sh`) still contain raw URLs and are now dead against a private repo; they
already managed nothing post-migration, so they are left alone rather than half-fixed.
