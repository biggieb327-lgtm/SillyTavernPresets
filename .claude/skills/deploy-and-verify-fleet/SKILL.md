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
- *Migrating* an instance from phone to VPS → `vps-migration`. Routine deploys to
  the VPS instances that already exist (cass, jules) are path E below.

## The fleet is split

Phone: **nora, bonnie, emily, priya** (tmux + `run-bot.sh`).
VPS: **cass, jules** (systemd `bot@<instance>` units).
Both pull from `main`, but the commands differ — a phone path applied to a VPS
instance silently does nothing, because the phone scripts skip instances with no
local directory.

## Decision tree — what changed?

| Changed | Path |
|---|---|
| bot.py only (and/or docs) — **phone bots** | **A: `/update` from Telegram** |
| run-bot.sh (supervisor) — with or without bot.py | **B: `update-all.sh` via shell** (`/update` never regenerates the supervisor) |
| Character cards / seed txt files only — **phone bots** | **C: `sync-cards.sh`** (or curl one card + rerun run-bot.sh) |
| An instance's `.env` | **D: edit on-device or on the VPS, `/restart` that bot** |
| Anything at all on a **VPS bot** (code, card, or preset) | **E: `vps-sync.sh`** |

## Procedure

**Path A — bot.py release (the normal case):**
1. User sends `/update` to ONE bot (any). It downloads bot.py from main, verifies
   it compiles, keeps `bot.py.bak`, swaps the shared file at `~/telegram-bot/bot.py`,
   restarts itself.
2. User sends `/audit` to that bot — MUST show the new BOT_VERSION. If it still
   shows the old one, stop: the update didn't take (see failure modes below).
3. Only then: `/restart` to the other **phone** bots (they share the swapped file
   at `~/telegram-bot/bot.py`).
4. Run path E for cass and jules — they do not share the phone's file.
5. `/audit` to each — all six show the new version.

**Path B — supervisor changed. DEAD, kept for history.** Phone-only (tmux, `~/telegram-bot`)
and the phone has been empty since 2026-07-26; the URL also 404s now that the repo is
private. Never hand this to the operator — use path E.
```bash
# DEAD: phone-era, and raw URLs 404 on a private repo. Do not run.
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/update-all.sh | bash
```
It prints the downloaded BOT_VERSION and restarts every tmux session. Then `/audit`
each bot. Note: `watchdog.sh` and `backup-all.sh` are NOT managed by update-all.sh —
if those changed, the user reinstalls them manually (one-time curl, see OPS_MANUAL).

**Path C — cards/seeds:** `bash sync-cards.sh --dry-run` first (shows what would be
pulled), then without the flag, then `/restart` each affected bot. Card changes
don't bump BOT_VERSION — verify by asking the character something the edit changed.

**Path D — .env:** user edits on-device (phone) or on the VPS, `/restart` that bot,
then check `/errors` for `[config]` warnings — bad numeric values fall back to
defaults with a warning rather than crashing, so a typo shows up as a warning, not
a crash.

**Path E — every instance (all six are on the VPS since 2026-07-26).** One command per
instance, and it covers code, card, and preset together:
```bash
# host: VPS (as root). NOT curl-piped: the repo went private 2026-07-28 and
# raw.githubusercontent.com 404s. vps-sync.sh fetches and hard-resets the checkout to
# origin/main before copying, so running the on-disk copy is correct even when stale.
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh cass
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh jules
```
`vps-sync.sh` pulls preset + card + bot.py, compile-checks, normalizes
`CHARACTER_CARD`, restarts and enables the systemd unit, then prints verification
output. Confirm with `/audit` to that bot as usual. Phone paths A/B/C never reach
these instances — `update-all.sh`, `sync-cards.sh`, and `watchdog.sh` skip them
automatically because there's no local directory.

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
- [ ] Phone path AND path E both run when the change affects all six
- [ ] All six bots verified — `/audit` shows expected BOT_VERSION (paths A/B/E) or
      behavior/config confirmed (paths C/D)
- [ ] Any `[config]` warnings in `/errors` after an .env change reviewed
- [ ] CI green on main before telling the user to deploy

## Common mistakes

- Sending `/update` to all six bots — one `/update` + three `/restart` covers the
  phone bots; six parallel downloads on phone bandwidth is not the design.
- Forgetting cass and jules entirely. A "fleet deploy" that only ran the phone
  paths has left two production bots on the old version, and nothing warns you —
  the phone scripts skip them silently.
- Using path A when run-bot.sh changed — the stale supervisor keeps running and
  the "deployed" behavior never appears.
- Telling the user to deploy before the work is merged and CI is green on main.
- Forgetting that `/audit` is the only proof a deploy landed — "the bot restarted"
  proves nothing about the version.

## What to report back

Which path was used, per-bot verification results (six `/audit` versions), any
warnings seen, and rollback status if one was needed.
