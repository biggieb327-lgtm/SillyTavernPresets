# Termux phone host — current production

Android phone running all six bots in tmux sessions under Termux
([raw/2026-07-11-claude-md.md]).

- Python 3.13; shared venv at `~/telegram-bot/venv/`; `requirements.txt` is the
  single source of truth after the hand-typed-list tzdata incident
  ([raw/2026-07-11-operational-log.md]).
- Defining hazard: Android's phantom-process killer SIGKILLs background processes
  above 32 system-wide; six bots sit near the limit, so no new OS processes
  ([raw/2026-07-11-claude-md.md]).
- `/tmp` is not writable; temp files go in `~/` or the instance dir
  ([raw/2026-07-11-improvements-plan.md]).
- SIGKILL vs SIGTERM triage: startup audits without a graceful-stop line = phantom
  killer; clean exit-0 restarts with the line = battery manager
  ([raw/2026-07-11-claude-md.md]).
- Scheduled to be replaced by the VPS ([entities/vps-target.md]); owner confirmed
  migration is the next major work (2026-07-11, session Q&A — recorded in
  `.claude/operating/fable-to-opus.md`).
