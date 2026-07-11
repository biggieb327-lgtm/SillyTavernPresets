# Raw capture: operational log

Source: `.claude/memory/operational-log.md` @ commit `d76dcdf`. Format: one row per
failure that changed the system. Condensed rows (Failure → Root cause → Patch):

- 2026-07-10 Hallucinated "memories" → character's own generated day fiction entered
  recent_facts unmarked, promoted weekly → own-day provenance tag honored by every
  memory consumer (v2026-07-10.2).
- 2026-07-10 Raw `<tool_call>` XML sent to user → models render taught intent in
  native function-call XML → `_strip_native_tool_calls` at the output choke point.
- 2026-07-10 External LLM audit: 15 claims, only 10 true (incl. a fictional
  "critical") → verify every external claim with line evidence before fixing.
- 2026-07-10 Break-testing an eval wiped ~700 lines of uncommitted bot.py →
  `git checkout <file>` reverts the FILE, not the injection → commit real work
  before break-testing; revert injections by re-editing.
- 2026-07-10 Group-chat design rounds 1–2 each found a missed flat-file write path →
  per-item enumeration can't stay complete → class-level closure (choke point +
  allowlist-built `_group_deliver`), pinned in CI.
- 2026-07-06 CLAUDE.md rules had no enforcement → hooks + evals scaffold; delivery
  gate blocks unversioned/unlogged bot.py changes.
- 2026-07-05 Fleet restarted every ~5 min for a session → watchdog judged bots
  frozen from a stale `.alive` heartbeat bot.py never wrote → `_touch_alive` job;
  check `watchdog.log` reason line first.
- 2026-07-05 Shutdown logging never fired → PTB `run_polling()` silently overrides
  `signal.signal()` → use `post_shutdown()`.
- 2026-07-05 Startup crash re-arming reminders (naive vs aware datetime) → tzdata
  missing from hand-typed package list → requirements.txt is single source of truth.
- pre-2026-07 Streamed 400s empty/undiagnosable → body never read before
  `raise_for_status()` → `_do_request` force-reads `resp.content`.
- pre-2026-07 `ModuleNotFoundError` crash-loop → bare `python`, venv off PATH →
  run-bot.sh launches `venv/bin/python` explicitly.
