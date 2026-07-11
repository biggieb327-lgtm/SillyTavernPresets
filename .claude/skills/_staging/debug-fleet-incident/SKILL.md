---
name: debug-fleet-incident
description: Evidence-first protocol for a live bot problem — a bot is silent, restarting, crashing, or behaving wrongly on the phone. Load when the user reports fleet trouble BEFORE proposing any fix. Encodes the triage order that past incidents proved out (phantom killer, watchdog, venv, tzdata).
---

# Debug a fleet incident

You cannot touch the phone. Every piece of evidence arrives because the user runs a
command (Telegram or Termux shell) and pastes output. Your job is to ask for the
*right* evidence in the right order, then diagnose — never to speculate fixes first.
Three rounds of speculative fixes once lost to one pasted log line.

## When NOT to use

- The bug is already understood and reproducible in-repo → `ship-bot-release`.
- Reviewing external audit claims (no live symptom) → `verify-external-audit`.
- A deploy just happened and something's off → `deploy-and-verify-fleet` first
  (it covers rollback via `bot.py.bak`); come back here if it's not deploy-caused.

## Procedure

1. **Get evidence before any hypothesis.** Ask the user for, in order of cheapness:
   - `/errors` to the affected bot (Telegram) — recent errors + startup audits.
   - If the bot can't answer `/errors`, that IS a finding: it's a startup crash →
     shell: `tail -50 ~/<instance-dir>/bot.log` (supervisor lines show exit codes
     and restart cadence).
   - `/audit` — BOT_VERSION (is it what you think is deployed?), uptime, config.

2. **Differential diagnosis.** Which bots are affected, which aren't? The broken
   one's delta (.env, model slots, Emily's integrations, group pilot on priya/jules)
   is usually the answer. All six broken at once = shared cause: bot.py release,
   venv, Android setting, network.

3. **Match against the known signature table before inventing a new theory:**

   | Signature | Cause | Check |
   |---|---|---|
   | `STARTUP AUDIT` lines piling up, NO `[shutdown] graceful stop` before them | Android phantom-process killer (SIGKILL) | `settings get global settings_enable_monitor_phantom_procs` — reverts after OS updates |
   | Repeated clean `exited (code 0)` WITH graceful-stop line | Real SIGTERM — OEM battery manager, not phantom killer | dontkillmyapp.com for the manufacturer |
   | Whole fleet restarting every ~5 min | watchdog.sh judging bots frozen | `tail ~/telegram-bot/watchdog.log` — it states its reason before every relaunch. Check this FIRST for any restart storm |
   | `ModuleNotFoundError` crash-loop | bare `python` instead of venv interpreter, or venv broken by a Python minor-version bump | `run-bot.sh` uses `venv/bin/python`? `pkg upgrade` recently? |
   | Startup `TypeError: offset-naive vs offset-aware` | tzdata missing from venv | reinstall tzdata / rebuild venv from requirements.txt |
   | `httpx.ConnectError` at startup | transient network blip | just restart the session |
   | Empty/undiagnosable 400s from the API | a response path skipping the `_do_request` force-read pattern | find the new path |

4. **Opaque error → instrument first.** If the error text doesn't identify the
   cause, ship a small logging change (via `ship-bot-release` — it's still a
   release) that makes the failure self-describing, have the user reproduce, then
   fix.

5. **Fix** via `ship-bot-release` if it's code; via the user's hands if it's
   device state (Android settings, venv rebuild, stale `bot.pid`, tmux sessions).
   Exact device commands live in CLAUDE.md §"Termux / Android quirks" and
   `OPS_MANUAL.md` — quote them precisely, the user copy-pastes.

6. **Close the loop:** after the fix, `/audit` on affected bots, and add an
   operational-log row (`.claude/memory/operational-log.md`, fixed format: date,
   failure, root cause, system patch, eval, next) if the failure changed the
   system. If this failure class has now happened twice → `add-regression-eval`.

## Quality bar

Diagnosis names a root cause that explains ALL the evidence, including which bots
were unaffected and why. "Restart it and see" is not a diagnosis.

## Verification checklist

- [ ] Saw actual pasted evidence (log lines / command output) before proposing a fix
- [ ] Signature table consulted; if matched, the cheap check ran before anything else
- [ ] Fix verified on-device (`/audit`, `/errors` clean, or reproduced-then-gone)
- [ ] Operational log updated if the system learned something

## Common mistakes

- Proposing bot.py fixes for Android-level causes (phantom killer, battery
  manager) — code cannot fix a SIGKILL.
- Debugging a restart storm without reading `watchdog.log` — the watchdog states
  its reason and once masqueraded as a platform bug for a full session.
- Treating "STARTUP AUDIT piling up" and "clean exit code 0 restarts" as the same
  symptom — they have opposite causes (SIGKILL vs SIGTERM).
- Asking the user for five things at once; get the cheapest discriminating
  evidence first.

## What to report back

The evidence trail (what was asked for, what it showed), the diagnosis and what
ruled alternatives out, the fix and how it was verified, and whether an
operational-log row or new eval was warranted.
