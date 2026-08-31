---
name: vps-migration
description: HISTORICAL — the phone→VPS migration (ROADMAP 1.2) completed 2026-07-29; all seven bots are on the VPS. Load ONLY if standing up an 8th instance from scratch, and even then prefer SETUP_GUIDE.md / new-bot.sh. Not for day-to-day VPS ops (that is OPS_MANUAL.md and deploy-and-verify-fleet).
---

# VPS migration (ROADMAP 1.2)

**HISTORICAL (complete 2026-07-29).** The migration is finished; this skill describes a
one-time move that will not recur. Load it only if adding a new instance. For running
bots on the VPS, use `OPS_MANUAL.md` and `deploy-and-verify-fleet`.

The runbook is `telegram-companion-bot/deploy/MIGRATION.md` — follow it literally;
don't reconstruct it from memory. This skill covers only the constraints around the
runbook and the mixed-fleet period. Sequence: pilot **jules** (lowest-state
instance) → 7-day soak → migrate the rest one at a time → retire the phone.

## When NOT to use

- Normal fleet work while everything is still on the phone → other skills.
- Writing/altering the VPS tooling itself (`install-vps.sh`, `bot@.service`) — that
  is code work via normal review + `repo-change-control`-style verification; this
  skill governs *executing* a migration.

## Hard constraints (each can cause real damage)

1. **One poller per token — ever.** Two processes polling the same bot token fight
   over updates (Telegram getUpdates conflict, messages randomly split). The
   runbook's stop-then-start order is mandatory: confirm the phone instance is DEAD
   (`tmux ls | grep <name>` empty AND `pgrep -f "bot.py.*<dir>"` empty) before
   starting it on the VPS. Never leave both "just to compare".
2. **Backup before stopping anything:** `bash ~/telegram-bot/backup-all.sh` on the
   phone. State files are the character's memory — unrecoverable if lost.
3. **`.env` files move by hand, never through git** (tokens must never land in the
   repo — it is public, so anything committed is world-readable; the rule holds in every
   visibility state). scp them; the secret-scan eval and risk-guard exist because of this.
4. **Rollback stays available:** don't delete the phone-side instance directory
   until the runbook's soak criteria pass (7 days for the pilot). `MIGRATION.md`
   § Rollback is the procedure — phone restart is always the fallback.

## Procedure

1. Read `deploy/MIGRATION.md` end to end this session. Identify which phase the
   user is in (pilot / remaining instances / retire phone) and which numbered step
   is next; do not skip verification steps to "save time".
2. For each step, give the user the exact command from the runbook (phone vs VPS
   clearly labeled — the commands look similar and run on different machines).
3. **Verify per instance after cutover:** bot responds in Telegram; `/audit` shows
   the right version AND its `State file:` line now points under
   `/opt/telegram-bots/` (that line is how you prove which host answered);
   `/errors` clean; dead man's switch (healthchecks.io) re-pointed per runbook §8.
4. **Mixed-fleet awareness** (some bots on phone, some on VPS — weeks, possibly):
   - `/update` swaps the *shared file on the machine that receives it*. A release
     must be deployed on BOTH hosts: phone path (`/update` + `/restart`) AND the
     VPS path from the runbook/`install-vps.sh` (systemd units, repo checkout).
   - Phone-only machinery does not exist on the VPS: no tmux sessions, no
     watchdog.sh, no phantom-process killer, no Termux path quirks; `bot@.service`
     (systemd) is the supervisor. Diagnose per host — `repo-debugging-playbook`'s
     Android signature table does NOT apply to VPS instances (`journalctl -u
     bot@<name>` replaces bot.log tailing there).
   - Shared-world: nora is `WORLD_GENERATOR=1`; instances read `world.txt` from
     their local filesystem. Until nora and a given bot are on the same host, that
     bot won't see fresh world files — known mixed-fleet limitation; don't "fix"
     it mid-migration.
5. **Remove migrated bot from phone scripts immediately after cutover.**
   `sync-cards.sh`, `update-all.sh`, and `watchdog.sh` each have an instance
   list — delete the migrated entry from all three in the same commit. A stale
   entry is harmless only until someone runs the script and gets confused about
   why it was skipped. The VPS deploy path (`vps-sync.sh`) is the replacement.
6. After each migrated instance, update `ROADMAP.md` 1.2 status and add an
   operational-log row if anything failed and taught something.

## Quality bar

- Every cutover followed backup → stop → verify-dead → start → verify-alive, with
  evidence at each arrow.
- At no point could two pollers hold the same token, even transiently "to test".
- The user always knows the current rollback move for the instance in flight.

## Verification checklist

- [ ] Phone backup taken and its timestamp confirmed before any stop
- [ ] Old poller verified dead before new one started (both checks, pasted)
- [ ] Migrated bot: Telegram reply + `/audit` + `/errors` clean + healthcheck ping
- [ ] No `.env` or state file ever staged into git (`git status` clean of them)
- [ ] Migrated bot removed from phone script instance lists (sync-cards.sh, update-all.sh, watchdog.sh)
- [ ] ROADMAP 1.2 status updated after each instance

## Common mistakes

- Starting the VPS instance "to check it works" before killing the phone one.
- Migrating nora (highest-state, WORLD_GENERATOR) first because she's "the main
  bot" — jules is first precisely because she has the least to lose.
- Applying phone triage (phantom killer, watchdog, tmux) to a VPS instance.
- Deleting phone-side state right after a successful first response, before soak.
- Committing a migrated instance's `.env` while "committing the migration".

## What to report back

Which runbook phase/step was completed, per-instance verification evidence, the
current rollback position (what's still on the phone), and any runbook step that
didn't match reality (that's a MIGRATION.md fix to make).
