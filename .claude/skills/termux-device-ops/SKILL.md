---
name: termux-device-ops
description: Android/Termux platform behavior and the on-device monitoring layer — phantom-process killer, exit-code triage, adb, pkg upgrade hazards, venv rebuilds, tzdata, watchdog/healthcheck/backup/cleanup scripts. Load when a fleet problem looks device-level rather than code-level, or when working on the on-device helper scripts.
---

# Termux device ops and fleet monitoring

The phone is not yours to touch. Everything here is a command the user runs and
pastes back. Quote commands exactly — they are copy-pasted verbatim.

## When NOT to use

- Diagnosing a live incident from scratch → `repo-debugging-playbook` first; it
  routes here once the cause looks device-level.
- Changing bot.py to work around a platform limit → `bot-code-invariants` rules
  11–13 already encode the constraints.
- VPS instances (cass, jules) — systemd, not tmux, and none of this applies →
  `vps-migration`.

## Phantom process killer (the big one)

Android 12+ silently SIGKILLs background processes when more than 32 exist
system-wide. Six bots sit at that limit.

**Triage by the EXIT CODE in the `[run-bot] … exited (code N)` line of `bot.log`.**
run-bot.sh logs the real `$?` (corrected 2026-07-25; the old "no graceful-stop
line" signature was wrong and cost two debugging rounds).

| exit code | meaning |
|---|---|
| `0` | Clean. `/update` and `/restart` exit here via `os._exit(0)` in `_schedule_exit()` (so the Telegram reply and admin-API response flush first). **No graceful-stop line is logged for these** — expected, not a kill. |
| `137` | SIGKILL (128+9) — phantom-process killer or OOM killer. Can't be caught, so no graceful-stop line either. |
| `143` | SIGTERM (128+15) that PTB didn't convert to a clean stop — most likely an OEM battery manager (see dontkillmyapp.com). |

`[shutdown] graceful stop` being **absent does NOT imply SIGKILL** — an ordinary
deploy looks identical in that respect. Only the exit code separates them.

**Check whether anything is actually being killed** (no permissions needed, and it
answers the question that matters):

```bash
grep -h "exited (code" ~/*-bot/bot.log | grep -v "code 0" | tail -20   # any 137 = SIGKILL
```

**Reading the Android setting needs adb.** `settings get global …` run directly in
Termux fails with `Failure calling service settings: Failed transaction
(2147483646)` — the settings service only accepts calls from the `shell` uid
(2000), and Termux is a normal app uid (confirmed 2026-07-25). Only reach for adb
if the behavioural check above shows kills.

One-time fix:
```bash
adb shell settings put global settings_enable_monitor_phantom_procs false
```
plus Termux battery → Unrestricted. **The setting reverts after an Android OS
update or factory reset.**

No PC needed — Android 11+ can adb to itself: Developer options → Wireless
debugging → *Pair device with pairing code*, then `pkg install android-tools`,
`adb pair 127.0.0.1:<PAIRING_PORT>`, then `adb connect 127.0.0.1:<CONNECT_PORT>`.
**The pairing port and the connect port are different** — the connect port is on
the main Wireless debugging screen.

Process count matters independently (limit is >32 system-wide):
```bash
pgrep -af "bot.py"   # more than one process per instance = duplicate pollers
tmux ls
```
Duplicate pollers surface as `telegram.error.Conflict` (2026-07-19 log row).

## Platform rules that must never regress

- run-bot.sh launches `~/telegram-bot/venv/bin/python` **explicitly** — bare
  `python` crash-loops on `ModuleNotFoundError` when the venv isn't on tmux's PATH.
- `/tmp` is not writable — use `~/` for temp files.
- Stale `bot.pid` after a crash: delete before restarting (run-bot.sh also clears).
- `tmux kill-session -t <name>` before reusing a session name.
- `httpx.ConnectError` at startup = transient network blip; restart the session.
- Wake lock is automatic (`termux-wake-lock`). The supervisor writes `bot.log` via
  `>>` (no `tee` — fewer processes for the phantom limit), trims at 5 MB;
  `errors.log` rotates at 2 MB.

## `pkg upgrade` hazards

- android-tools can break (libprotobuf symbol) → `pkg reinstall android-tools`.
- A Python **minor**-version bump breaks the shared venv. Rebuild:
  ```bash
  python -m venv --clear ~/telegram-bot/venv
  ~/telegram-bot/venv/bin/pip install -r ~/telegram-bot/requirements.txt
  ```
  `requirements.txt` is the single source of truth — hand-typing the list caused
  the tzdata bug.
- Pillow may need `pkg install libjpeg-turbo zlib freetype` first, or
  `pkg install python-pillow` + a `--system-site-packages` venv.
- A big Python jump (3.13→3.14) can outrun PTB v21's deprecated
  `asyncio.get_event_loop()` call — bot.py works around it in `main()`
  (v2026-07-05.6). If something worse appears, hold Termux's `python` package back.
- **Don't drop `tzdata`.** Termux has no system tz database; without it `ZoneInfo`
  silently degrades to naive local time, and a stored tz-aware reminder vs naive
  `now()` once crashed startup fleet-wide. `schedule_reminder` normalizes
  defensively (v2026-07-05.5) — but reinstall tzdata rather than rely on that.

## Monitoring layer

- **Restart-storm self-report:** `_self_audit` (every 30 min) DMs the owner at ≥3
  *unexpected* `STARTUP AUDIT` lines/hour (2h cooldown). `_tally_unexpected_restarts`
  excludes owner-initiated starts via the `[restart] requested` /
  `[update] …; restarting` markers in `errors.log`, so ordinary deploys don't trip
  it. It keys off those markers, **not** the graceful-stop line — to classify a
  restart yourself, use the exit-code table above.
- **Dead man's switch:** `HEALTHCHECK_URL` per instance (healthchecks.io, 30 min
  period + 15 min grace) — alerts on bot-down AND phone-dead.
- **`watchdog.sh`** (on-device at `~/telegram-bot/watchdog.sh`; source in repo,
  installed manually): relaunches vanished tmux sessions AND bots whose `.alive`
  heartbeat is stale (>300s). **bot.py must touch `.alive` every 60s**
  (`_touch_alive` job) — if that job is ever removed, watchdog restarts the whole
  fleet forever (cost a full debugging session, 2026-07-05). `watchdog.log` states
  its reason before every relaunch — **read it first for any restart storm.**
- **`backup-all.sh`** (cron): nightly state archive to shared storage, `.env`
  excluded, 14-day retention, optional rclone.
- **`cleanup-all.sh`** (cron): disk janitor — pip cache, `__pycache__`,
  SIGKILL-orphaned `.backup-stage.*` dirs, stale `*.tmp` sidecars. **Dry-run by
  default**; `--force` deletes. Never touches state, `.env`, `bot.py`/`.bak`, or
  live logs; character-card orphans are reported, never auto-deleted.

`backup-all.sh`, `cleanup-all.sh`, and `watchdog.sh` are curl-installed once and
are **not** managed by `update-all.sh` — if their source changed in the repo, the
user reinstalls them by hand.

## Quality bar

A device-level diagnosis names the exit code (or the watchdog log line) that
proves it. "Probably the phantom killer" without a `137` in hand is a guess.

## Verification checklist

- [ ] Exit code read from `bot.log`, not inferred from the missing graceful-stop line
- [ ] `watchdog.log` checked before blaming the platform for a restart storm
- [ ] Process census run if duplicate-poller symptoms (`Conflict`) appeared
- [ ] Device fix confirmed with `/audit` + a clean `/errors` afterwards

## Common mistakes

- Reading "no graceful stop line" as SIGKILL — an ordinary `/update` looks the same.
- Telling the user to run `settings get global …` in Termux — it cannot work.
- Proposing a bot.py fix for a SIGKILL; code cannot survive signal 9.
- Rebuilding the venv by hand-typing packages instead of `requirements.txt`.

## What to report back

The exit code or log line that identified the cause, the exact device command the
user should run, what output proves it worked, and whether the fix survives a
reboot (the phantom-killer setting does not survive an OS update).
