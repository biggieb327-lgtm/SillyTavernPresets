---
name: deploy-and-verify-fleet
description: Choosing the correct deploy path for merged work and verifying it landed on all six bots. Load when work is on main and the user needs deploy instructions, when the user asks "how do I get this onto the bots", or when a deploy appears to have failed or half-landed.
---

# Deploy and verify the fleet

Deploys pull raw files from `main` over public URLs. Claude cannot execute any of
this — the phone runs it. Give the user exact commands and tell them what output
proves success. There are four deploy paths; picking the wrong one is the main
failure mode.

## When NOT to use

- Work isn't merged to main yet → finish `repo-change-control` first (deploying a
  branch is impossible; the curl URLs are pinned to main).
- The bot is broken for non-deploy reasons → `repo-debugging-playbook`.
- VPS hosts → `vps-migration` (systemd, not tmux; different commands).

## Decision tree — what changed?

| Changed | Path |
|---|---|
| bot.py only (and/or docs) | **A: `/update` from Telegram** |
| run-bot.sh (supervisor) — with or without bot.py | **B: `update-all.sh` via shell** (`/update` never regenerates the supervisor) |
| Character cards / seed txt files only | **C: `sync-cards.sh`** (or curl one card + rerun run-bot.sh) |
| An instance's `.env` | **D: edit on-device, `/restart` that bot** |

## Procedure

**Path A — bot.py release (the normal case):**
1. User sends `/update` to ONE bot (any). It downloads bot.py from main, verifies
   it compiles, keeps `bot.py.bak`, swaps the shared file at `~/telegram-bot/bot.py`,
   restarts itself.
2. User sends `/audit` to that bot — MUST show the new BOT_VERSION. If it still
   shows the old one, stop: the update didn't take (see failure modes below).
3. Only then: `/restart` to the other five bots (they share the swapped file).
4. `/audit` to each — all six show the new version.

**Path B — supervisor changed:**
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/update-all.sh | bash
```
It prints the downloaded BOT_VERSION and restarts every tmux session. Then `/audit`
each bot. Note: `watchdog.sh` and `backup-all.sh` are NOT managed by update-all.sh —
if those changed, the user reinstalls them manually (one-time curl, see OPS_MANUAL).

**Path C — cards/seeds:** `bash sync-cards.sh --dry-run` first (shows what would be
pulled), then without the flag, then `/restart` each affected bot. Card changes
don't bump BOT_VERSION — verify by asking the character something the edit changed.

**Path D — .env:** user edits on-device, `/restart` that bot, then check `/errors`
for `[config]` warnings — bad numeric values fall back to defaults with a warning
rather than crashing, so a typo shows up as a warning, not a crash.

**Rollback (any path):** `~/telegram-bot/bot.py.bak` is the previous bot.py. Shell:
copy it back over bot.py and restart sessions. There is deliberately no `/rollback`
command — a broken bot can't be trusted to roll itself back.

## Deploy failure modes

- `/update` says success, `/audit` shows old version → the push to main didn't
  happen or CI-visible main differs from what you think; check the raw URL content
  and `git log origin/main`.
- `/update` refuses → downloaded bot.py doesn't compile; main is broken; fix
  forward on main immediately (red main is a deploy blocker for the whole fleet).
- One bot won't restart after the others succeeded → stale `bot.pid` or dead tmux
  session: `tmux kill-session -t <name>` then rerun `run-bot.sh <dir> <name>`.

## Quality bar

The user got: the path letter, exact copy-pasteable commands, the expected output
at each step, and the rollback move — before they started.

## Verification checklist

- [ ] Correct path chosen for what actually changed (check the merged diff, not memory)
- [ ] All six bots verified — `/audit` shows expected BOT_VERSION (paths A/B) or
      behavior/config confirmed (paths C/D)
- [ ] Any `[config]` warnings in `/errors` after an .env change reviewed
- [ ] CI green on main before telling the user to deploy

## Common mistakes

- Sending `/update` to all six bots — one `/update` + five `/restart` is the
  design; six parallel downloads on phone bandwidth is not.
- Using path A when run-bot.sh changed — the stale supervisor keeps running and
  the "deployed" behavior never appears.
- Telling the user to deploy before the work is merged and CI is green on main.
- Forgetting that `/audit` is the only proof a deploy landed — "the bot restarted"
  proves nothing about the version.

## What to report back

Which path was used, per-bot verification results (six `/audit` versions), any
warnings seen, and rollback status if one was needed.
