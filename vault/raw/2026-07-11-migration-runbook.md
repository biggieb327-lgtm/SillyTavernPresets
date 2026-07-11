# Raw capture: VPS migration runbook

Source: `telegram-companion-bot/deploy/MIGRATION.md` @ commit `d76dcdf`.

> Follows the ROADMAP 1.2 plan: pilot one low-state bot (jules), soak, then
> migrate the rest one at a time. **Only one process may poll a given bot token
> at any time** — stop-then-start, never parallel.

Prerequisites: Ubuntu 24.04 VPS (≥4 vCPU/6 GB), SSH, Tailscale, phone backup
current, `install-vps.sh` run once.

Phase structure: Phase 1 pilot jules (verify baseline → backup → stop on phone →
transfer state → verify VPS .env → ownership → start via systemd `bot@.service` →
dead man's switch → 7-day soak → declare success); Phase 2 remaining instances one
at a time (nora has specific notes — WORLD_GENERATOR); Phase 3 retire the phone.
Rollback section exists; phone restart is always the fallback. VPS instance dirs
under `/opt/telegram-bots/<name>/`.
