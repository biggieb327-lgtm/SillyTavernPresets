---
name: repo-debugging-playbook
description: Evidence-first protocol for a live bot problem — a bot is silent, restarting, crashing, or replying wrongly. Load when the user reports fleet trouble BEFORE proposing any fix. Encodes the triage order past incidents proved out (OOM/SIGKILL, crash-loops, venv, tzdata).
---

# Debug a fleet incident

You cannot reach the VPS directly. Every piece of evidence arrives because the user
runs a command — on the VPS as root, or via Telegram — and pastes the output. Your job
is to ask for the *right* evidence in the right order, then diagnose — never to
speculate fixes first. Three rounds of speculative fixes once lost to one pasted log
line.

The fleet runs on the VPS under systemd (`bot@<instance>`), logging to the journal.
The authoritative instance list is whatever `systemctl list-units 'bot@*'` reports.
The Termux phone is empty (migration complete 2026-07-29) — device-level Android causes
below are marked **historical** and cannot recur on what is running now.

## When NOT to use

- The bug is already understood and reproducible in-repo → `repo-change-control`.
- Reviewing external audit claims (no live symptom) → `verify-external-audit`.
- A deploy just happened and something's off → `deploy-and-verify-fleet` first
  (it covers the immutable `current`/`previous` rollback); come back here if it's
  not deploy-caused.

## Procedure

1. **Get evidence before any hypothesis.** Ask the user for, in order of cheapness:
   - `/errors` to the affected bot (Telegram) — recent errors + startup audits.
   - If the bot can't answer `/errors`, that IS a finding: it's a startup crash →
     VPS: `journalctl -u bot@<instance> -n 80 --no-pager` (the crash reason and
     restart cadence), and `systemctl status bot@<instance> --no-pager` (running?
     PID? since when? how many restarts?).
   - `/audit` — BOT_VERSION (is it what you think is deployed?), uptime, config.

   **While you wait for that paste, ask whether it has happened before** — the
   operational log holds dozens of incidents and you cannot read it whole:
   ```bash
   python3 .claude/tools/oplog-search.py "the symptom in your own words"
   ```
   Ranks rows by relevance instead of making you skim a grep's matches, and prints
   the `incidents/` link when the row has one. **Not a substitute for grep** when you
   know the exact string, and measured at 7/10 — it misses when the log's vocabulary
   and yours differ (it writes "offset-naive", you say "timezone"), which is C4 in
   miniature. A miss means "search again in other words", never "this is new".

2. **Differential diagnosis.** Which bots are affected, which aren't? The broken
   one's delta (.env, model slots, Emily's integrations, group pilot on priya/jules)
   is usually the answer. All seven broken at once = shared cause: bot.py release,
   venv, the VPS host, network.

3. **Match against the known signature table before inventing a new theory:**

   | Signature | Cause | Check |
   |---|---|---|
   | `systemctl status` shows `Result: oom-kill`, or exit code 137 | SIGKILL — the VPS OOM-killer (host RAM) or a manual kill | `journalctl -u bot@<instance> -n 80 --no-pager`; check host memory (`free -m`, `dmesg \| grep -i oom`). *(Historical phone cause — the Android phantom-process killer, uid-restricted `adb`; the phone is empty now)* |
   | exit code 143 | SIGTERM the process didn't convert to a clean stop | `journalctl` around the stop timestamp — a `systemctl stop`/`restart` or a deploy usually explains it |
   | exit code 0, no graceful-stop line | **Normal.** `/update` and `/restart` exit via `os._exit(0)` in `_schedule_exit()` and never log a graceful stop. NOT a kill | correlate the timestamps with deploys before investigating further |
   | A bot restarting every few seconds/minutes | systemd `Restart=always` relaunching a bot that keeps crashing at startup | `systemctl status bot@<instance>` (restart count) + `journalctl -u bot@<instance> -n 80` for the crash reason — read this FIRST for any restart loop |
   | `ModuleNotFoundError` crash-loop | selected immutable dependency layer is absent/damaged, or the lock omitted a real import | `journalctl` names the module; run `vps-sync.sh --rollback`, then fix `requirements.txt` + regenerate `requirements.lock` on main — never mutate `current/venv` |
   | Startup `TypeError: offset-naive vs offset-aware` | tzdata missing from the declared/locked environment | roll back, confirm `tzdata` is in both requirements files, then fix forward through `vps-sync.sh` |
   | `httpx.ConnectError` at startup | transient network blip | restart the unit (`systemctl restart bot@<instance>`) |
   | Empty/undiagnosable 400s from the API | a response path skipping the `_do_request` force-read pattern | find the new path |

4. **Opaque error → instrument first.** If the error text doesn't identify the
   cause, ship a small logging change (via `repo-change-control` — it's still a
   release) that makes the failure self-describing, have the user reproduce, then
   fix.

5. **Fix** via `repo-change-control` if it's code; via the user's hands on the VPS if
   it's host state (a damaged release pointer, a stuck systemd unit, disk full). Exact live
   commands live in `OPS_MANUAL.md`; the phone-era device layer in `termux-device-ops`
   is historical (the phone runs nothing) — read it only for the reasoning behind a
   past Android incident, never for a command to run now.

6. **Close the loop:** after the fix, `/audit` on affected bots, and add an
   operational-log row (`.claude/memory/operational-log.md`, fixed format: date,
   failure, root cause, system patch, eval, next) if the failure changed the
   system. If this failure class has now happened twice → `add-regression-eval`.

## Quality bar

Diagnosis names a root cause that explains ALL the evidence, including which bots
were unaffected and why. "Restart it and see" is not a diagnosis.

## Verification checklist

- [ ] Saw actual pasted evidence (journal lines / command output) before proposing a fix
- [ ] Signature table consulted; if matched, the cheap check ran before anything else
- [ ] Fix verified on the VPS (`/audit`, `/errors` clean, or reproduced-then-gone)
- [ ] Operational log updated if the system learned something

## Common mistakes

- Proposing bot.py fixes for host-level causes (OOM-kill, disk full) — code cannot
  fix a SIGKILL.
- Debugging a restart loop without reading `journalctl` / `systemctl status` — systemd
  states the restart count and the journal carries the crash reason (the phone-era
  watchdog once masqueraded as a platform bug for a full session; systemd's own
  `Restart=always` is the mechanism now, not `watchdog.sh`).
- Treating "STARTUP AUDIT piling up" and "clean exit code 0 restarts" as the same
  symptom — they have opposite causes (SIGKILL vs SIGTERM).
- Asking the user for five things at once; get the cheapest discriminating
  evidence first.

## What to report back

The evidence trail (what was asked for, what it showed), the diagnosis and what
ruled alternatives out, the fix and how it was verified, and whether an
operational-log row or new eval was warranted.
