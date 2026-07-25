# Termux phone host — current production

Android phone running FOUR bots in tmux sessions under Termux (nora, bonnie,
emily, priya — cass and jules moved to the VPS; updated 2026-07-25)
([raw/2026-07-11-claude-md.md]).

- Python **3.14** (observed 3.14.6, 2026-07-25 — Termux upgraded from 3.13 and the
  shared venv was rebuilt to match; the STARTUP AUDIT line is authoritative). Practical
  effect: cp314 wheels are scarce, so new binary deps tend to compile from source.
  Shared venv at `~/telegram-bot/venv/`; `requirements.txt` is the
  single source of truth after the hand-typed-list tzdata incident
  ([raw/2026-07-11-operational-log.md]).
- Defining hazard: Android's phantom-process killer SIGKILLs background processes
  above 32 system-wide; six bots sit near the limit, so no new OS processes
  ([raw/2026-07-11-claude-md.md]).
- `/tmp` is not writable; temp files go in `~/` or the instance dir
  ([raw/2026-07-11-improvements-plan.md]).
- SIGKILL vs SIGTERM triage: read the **exit code** in run-bot.sh's
  `[run-bot] … exited (code N)` line — 137 = SIGKILL (phantom killer/OOM), 143 =
  SIGTERM (battery manager), 0 = clean or owner-initiated. **Corrected 2026-07-25:**
  the old "no graceful-stop line = SIGKILL" rule was wrong — `/update` and `/restart`
  exit via `os._exit(0)`, bypassing `post_shutdown`, so they log no graceful stop either
  ([raw/2026-07-11-claude-md.md]).
- Scheduled to be replaced by the VPS ([entities/vps-target.md]); owner confirmed
  migration is the next major work (2026-07-11, session Q&A — recorded in
  `.claude/operating/fable-to-opus.md`).
