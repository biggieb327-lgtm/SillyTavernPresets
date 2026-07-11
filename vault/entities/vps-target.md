# VPS target — next production host

Ubuntu 24.04 VPS (≥4 vCPU / 6 GB recommended) that will take the fleet over from
the phone, one instance at a time ([raw/2026-07-11-migration-runbook.md]).

- Supervisor is systemd (`bot@.service`), instance dirs under
  `/opt/telegram-bots/<name>/` — no tmux, no watchdog.sh, no phantom killer
  ([raw/2026-07-11-migration-runbook.md]).
- Hard rule: only one process may poll a given bot token at any time —
  stop-then-start cutover, never parallel ([raw/2026-07-11-migration-runbook.md]).
- Pilot is jules (lowest state), 7-day soak, then the rest; nora last-ish (she is
  the WORLD_GENERATOR) ([raw/2026-07-11-migration-runbook.md]).
- UNCERTAIN: no VPS exists yet at capture time (the runbook assumes
  `install-vps.sh` has been run once; whether a machine is provisioned is unknown
  from the repo).
