---
name: deploy-and-verify-fleet
description: Choosing the correct deploy path for merged work and verifying it landed on all seven bots. Load when work is on main and the user needs deploy instructions, when the user asks "how do I get this onto the bots", or when a deploy appears to have failed or half-landed.
---

# Deploy and verify the fleet

All seven instances run on the VPS under systemd. Deploys read from a git checkout at
`/opt/telegram-bots/.repo` (a read-only deploy key, not raw URLs — the repo has been
private since 2026-07-28 and anonymous `raw.githubusercontent.com` URLs 404). Claude
cannot run this from a session without VPS access — give the user exact commands and
tell them what output proves success.

## When NOT to use

- Work isn't merged to main yet → finish `repo-change-control` first (`vps-sync.sh`
  hard-resets to `origin/main`, so deploying an unmerged branch is impossible).
- The bot is broken for non-deploy reasons → `repo-debugging-playbook`.
- *Migrating* an instance onto the VPS in the first place (there is no VPS directory
  for it yet) → `vps-migration` / `install-vps.sh`. This skill is for the seven
  instances that already exist.

## The fleet

All seven — **nora, bonnie, cass, emily, priya, jules, marcus** — are VPS instances at
`/opt/telegram-bots/<instance>/`, running as systemd unit `bot@<instance>`. There is no
phone fleet anymore (empty since 2026-07-26; the 14-day rollback soak on the phone ends
2026-08-09). One deploy path covers all seven — no decision tree, no per-instance path
letter.

**`/update` is dead as a deploy path**, though the handler still exists: on the private
repo it hits `repo_not_readable` and replies telling the owner to run `vps-sync.sh`
instead (`update_cmd` in bot.py). **`update-all.sh` and `sync-cards.sh` are phone-era
and manage nothing now** — do not hand them to the user.

## Procedure

**One command per instance** — covers code, card, and preset layers together:
```bash
# host: VPS (as root). NOT curl-piped: the repo is private and raw URLs 404.
# vps-sync.sh fetches and hard-resets the checkout to origin/main before copying,
# so running it is correct even when the on-disk checkout looks stale.
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh nora
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh bonnie
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh cass
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh emily
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh priya
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh jules
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh marcus
```
Only send the instances actually affected — a card-only edit needs just the instance(s)
using that card; a bot.py change needs all seven. Each invocation: compile-checks
bot.py before swapping it (keeping `bot.py.bak`), copies `preset.txt` + whatever preset
layers that instance's own `PRESET_FILES` names, normalizes `CHARACTER_CARD` in
`.env` to the repo's filename, restarts + enables the unit, then prints hash and
`STARTUP AUDIT` verification. It also reports (never copies) any seed file
(`people.txt`/`projects.txt`/`schedule.txt`/`atlas.txt`) present in the repo but
missing on that instance — diff a sibling instance before copying one over, since a
repo seed file can be an older generation than what's live (jules, 2026-07-29).

**The shared swap is locked** (ROADMAP 1.6, shipped 2026-08-01, race-confirmed on the
real VPS). `vps-sync.sh` takes a non-blocking `flock` on `$BASE/.vps-sync.lock` before it
touches the shared `/opt/telegram-bots/bot.py` and `bot.py.bak`, and `set -euo pipefail`
makes the backup `cp` fatal rather than `|| true`. So a concurrent second run cannot
corrupt the rollback point — **it refuses**: `flock -n` fails, the run prints
`another sync is swapping bot.py on this host; retry` and exits 1.

Still run them **sequentially**, for a different reason than the old one: a rejected run
deploys nothing, so a concurrent launch leaves that instance silently on the previous
version. The loop below stops on the first non-zero exit, which is what you want.

**Verify:** `/audit` to each synced instance — MUST show the new BOT_VERSION. If it
still shows the old one, stop: the sync didn't take (see failure modes below).

**Rollback (shared bot.py, all instances):**
```bash
cp /opt/telegram-bots/bot.py.bak /opt/telegram-bots/bot.py
for b in $(systemctl list-units 'bot@*' --no-legend --plain \
          | awk '{print $1}' | sed 's/^bot@//; s/\.service$//'); do
  systemctl restart "bot@$b"
done
```
There is deliberately no `/rollback` command — a broken bot can't be trusted to roll
itself back. Cards and preset layers aren't versioned by `vps-sync.sh`'s backup step;
if a card/preset edit needs rolling back, re-run `vps-sync.sh` after reverting the
change on `main`.

## Refreshing the checkout by hand (repo tools, not a deploy)

`tools/` never deploys, so a fix to `atlas_audit.py` / `selfie_prompt_preview.py` reaches the
VPS only when `/opt/telegram-bots/.repo` is updated. **A bare `git pull` or `git fetch` there
fails** — `git@github.com: Permission denied (publickey)`. The remote is SSH and the
read-only deploy key is not in root's default identity set; `vps-sync.sh` exports it per-run
(line 79) rather than configuring it globally, so nothing outside the script inherits it.

```bash
# host: vps (as root)
export GIT_SSH_COMMAND="ssh -i /root/.ssh/stpresets_ro -o IdentitiesOnly=yes"
git -C /opt/telegram-bots/.repo fetch origin main
git -C /opt/telegram-bots/.repo reset --hard origin/main
```

`reset --hard`, not `pull` — it is what the script does and it works from any HEAD state.
The key path honours `STPRESETS_DEPLOY_KEY` if that is set. Simpler alternative when a
restart is acceptable: **any `vps-sync.sh <instance>` run does this fetch-and-reset first**,
so deploying one instance also refreshes the checkout for every tool.

**Running a repo tool on the VPS needs the fleet venv**, not system python — system python
has none of `bot.py`'s dependencies and the three tools that import it die on
`ModuleNotFoundError` (they now name the venv in the error):

```bash
# host: vps (as root)
/opt/telegram-bots/venv/bin/python3 \
  /opt/telegram-bots/.repo/telegram-companion-bot/tools/atlas_audit.py priya --near "Seattle"
```

## Deploy failure modes

- `vps-sync.sh` exits at "FATAL: no git checkout" → the deploy key or checkout is
  missing on this host; see the script's own header and `deploy/MIGRATION.md` §
  "Private-repo deploys".
- `vps-sync.sh` exits at the `py_compile` step → the downloaded bot.py doesn't
  compile; main is broken — fix forward on main immediately (red main is a fleet-wide
  deploy blocker, and `evals.yml`'s hard-reset-before-copy note in CLAUDE.md says the
  same).
- `/audit` still shows the old BOT_VERSION after a sync reports success → check the
  script's printed checkout HEAD against `git log origin/main`; the push may not have
  actually reached `origin/main`.
- One instance won't restart after others succeeded → `journalctl -u bot@<instance> -n 60`
  for the crash reason; a stale unit state is `systemctl restart bot@<instance>` again,
  not a fresh sync.

## Quality bar

The user got: copy-pasteable commands for exactly the instances affected, the expected
output at each step, and the rollback move — before they started.

## Verification checklist

- [ ] Correct instance list chosen for what actually changed (check the merged diff,
      not memory — a card change needs only that card's instance(s); bot.py needs all
      seven)
- [ ] Every synced instance verified — `/audit` shows the expected BOT_VERSION
- [ ] Any seed-file gap `vps-sync.sh` reported was triaged (diffed against a sibling),
      not silently copied over
- [ ] CI green on main before telling the user to deploy
- [ ] Every instance actually synced — a concurrent run is refused by the `flock`
      (ROADMAP 1.6), so a rejected one leaves that instance on the OLD version

## Common mistakes

- Handing the user `/update`, `update-all.sh`, or `sync-cards.sh` — all three are dead
  phone-era paths that manage nothing on the VPS fleet.
- Forgetting an instance entirely — there is no automatic "skip if not present"
  behavior to fall back on; a `vps-sync.sh` never run for an instance leaves it on the
  old version with nothing announcing it except a stale `/audit`.
- Telling the user to deploy before the work is merged and CI is green on main.
- Forgetting that `/audit` is the only proof a deploy landed — "the bot restarted"
  proves nothing about the version.
- Running two `vps-sync.sh` invocations at once. The lock (ROADMAP 1.6) makes this
  safe rather than corrupting, but the loser exits 1 without deploying — check every
  instance's `/audit`, don't assume the batch landed.

## What to report back

Which instances were synced, per-instance verification (`/audit` versions), any seed-file
or `[config]` warnings surfaced, and rollback status if one was needed.
