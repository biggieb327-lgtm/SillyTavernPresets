# Operational log

One row per failure that changed the system. Format is fixed — date, failure, root
cause, system patch, eval, next — nothing else. No narration, no diary. Newest first.
Full incident detail lives in `telegram-companion-bot/CHANGELOG.md`; this file is the
index of what the *system* learned.

| Date | Failure | Root cause | System patch | Eval | Next |
|---|---|---|---|---|---|
| 2026-07-10 | Break-testing a new eval wiped ~700 lines of uncommitted bot.py work | Used `git checkout <file>` to revert a one-line eval-test injection while the file carried the whole uncommitted feature — checkout reverts the FILE, not the injection | Rule: commit real work BEFORE break-testing evals; revert injections by re-editing, never `git checkout`, on files with uncommitted changes | none (procedural) | Consider a risk-guard hook pattern for `git checkout/restore` on modified files |
| 2026-07-10 | Group-chat design needed 4 adversarial rounds; rounds 1-2 each found flat-file write paths a hand-kept inventory missed | Per-item enumeration of write paths can't stay complete against a 7k-line codebase | Class-level closure: default-deny command choke point + allowlist-built `_group_deliver`, both pinned in CI | group-deliver-clean, group-cmd-allowlist | Watch pilot acceptance runs; media probe (§10.11) is manual-only |
| 2026-07-06 | Rules in CLAUDE.md (changelog-first, BOT_VERSION bump, evidence-before-fixes) had no enforcement — nothing failed when they were skipped | Conventions lived only in prose; no file enforced them tomorrow | Agent team + hooks + evals scaffold under `.claude/` (this commit); delivery-gate hook blocks unversioned/unlogged bot.py changes | `run-evals.sh` (all), settings-valid-json | Watch whether delivery-gate false-positives on legit doc-only sessions; tune, don't disable |
| 2026-07-05 | Whole fleet restarted every ~5 min for a full debugging session | watchdog.sh judged bots frozen from a stale `.alive` heartbeat file bot.py never wrote — not Samsung battery, not phantom killer | `_touch_alive` repeating job in bot.py; debugging protocol rule: check `watchdog.log` reason line first | heartbeat-alive | None — pinned |
| 2026-07-05 | Shutdown logging never fired; SIGTERM vs SIGKILL triage impossible | PTB `run_polling()` silently overrides `signal.signal()` handlers registered in main() | Wired via `post_shutdown()` hook instead (v2026-07-05.8) | graceful-shutdown | None — pinned |
| 2026-07-05 | Bots crashed at startup re-arming reminders (`TypeError: offset-naive vs offset-aware`) | `tzdata` missing from a hand-typed package list; Termux has no system tz database | `requirements.txt` made single source of truth; `schedule_reminder` normalizes defensively (v2026-07-05.5) | tzdata-pinned | None — pinned |
| pre-2026-07 | Streamed 400 errors arrived with empty bodies; three rounds of speculative fixes | Error body never read before `raise_for_status()` on streaming responses | `_do_request` force-reads `resp.content`; debugging protocol: instrument first when the error is opaque | streaming-error-body | None — pinned |
| pre-2026-07 | Bots crash-looped with `ModuleNotFoundError: requests` | Launcher used bare `python`; venv not on PATH when tmux starts | run-bot.sh launches `venv/bin/python` explicitly; dead launchers deleted (v2026-07-05.10) | venv-explicit-python | None — pinned |
