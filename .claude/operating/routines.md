# Scheduled Routines (Claude Code Remote triggers)

Live schedules that act on this repo. Rule: **any change to a live Routine's prompt
must be mirrored in this file in the same session, and vice versa** — a Routine that
exists only in the scheduler (or only as prose) is invisible and will drift.

Inspect/pause/edit from any Claude Code Remote session on this repo with the
`list_triggers` / `update_trigger` / `delete_trigger` tools (claude-code-remote MCP).

---

## improvement-loop-monthly

- **Created:** 2026-07-12 (trigger id `trig_014UoejLm5Wv7TkqJC4j9CjJ`)
- **Schedule:** cron `0 9 1 * *` — 09:00 on the 1st of each month (assumed UTC;
  exact hour is not load-bearing).
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`) — the
  analysis must not inherit a stale conversation.
- **What it does:** the monthly improvement loop described in CLAUDE.md — runs the
  `improvement-analyst` role over the logs and pushes at most one proposal to
  `claude/improvement-loop`, never to `main`.

### Verbatim prompt

```
Monthly improvement loop for the SillyTavernPresets repo. This Routine is recorded
in .claude/operating/routines.md — read that file first; if this prompt and that
file disagree, stop and report the drift to the owner instead of proceeding.

Act as the improvement-analyst agent: read .claude/agents/improvement-analyst.md
and follow its mission, method, evidence requirement, and 20-line output limit
exactly.

1. Read .claude/memory/operational-log.md and telegram-companion-bot/CHANGELOG.md.
2. Look for the same failure shape appearing >= 2 times that no existing hook,
   eval, or skill prevented. Required evidence: quote the >= 2 occurrences with
   dates/versions.
3. If nothing qualifies: push NOTHING, create NO branch, and end with the one-line
   summary "improvement-loop: no qualifying pattern this month".
4. If one qualifies: write EXACTLY ONE proposal (the pattern, the quoted
   occurrences, the one proposed patch with exact file + change, and the eval that
   would prove it worked) to .claude/memory/improvement-proposals/<YYYY-MM>.md.
5. Commit only that file to the branch claude/improvement-loop (reset it to
   origin/main first if it already exists) and push ONLY to
   claude/improvement-loop. NEVER push to main or any other branch.
6. Do NOT implement the patch, do NOT modify bot.py, hooks, evals, or any other
   file — implementation belongs to system-fixer in a reviewed session.
```
