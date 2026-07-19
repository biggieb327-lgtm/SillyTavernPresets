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

---

## hygiene-check-weekly

- **Created:** 2026-07-17 (trigger id `trig_01NuXwchCqAdYNsZ92493Gi3`)
- **Schedule:** cron `0 9 * * 1` — 09:00 every Monday (assumed UTC; offset from the
  monthly improvement loop, which owns the 1st of the month).
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`).
- **What it does:** report-only context-librarian pass — version/changelog sync,
  ROADMAP/IMPROVEMENTS_PLAN status drift, CI state on `main`, Routine↔this-file
  sync, operational-log format. It fixes nothing and pushes nothing; findings go
  to the owner, and recurring ones feed the monthly improvement loop.
- **Known limitation:** fired sessions carry no MCP connectors, so the CI check
  falls back to the public GitHub API via WebFetch and the Routine-sync check may
  be SKIPPED — the prompt requires skipped checks to be reported as skipped, never
  as green.

### Verbatim prompt

```
Weekly hygiene check for the SillyTavernPresets repo. This Routine is recorded in
.claude/operating/routines.md — read that file first; if this prompt and that file
disagree, stop and report the drift to the owner instead of proceeding.

Act as the context-librarian agent: read .claude/agents/context-librarian.md and
follow its role. This run is REPORT-ONLY: make no commits, push nothing, create no
branches, modify no Routines, and edit no files. Read-only actions only.

Check, quoting the exact lines/values you compared as evidence:
1. Version sync: BOT_VERSION in telegram-companion-bot/bot.py vs the newest "## v"
   heading in telegram-companion-bot/CHANGELOG.md.
2. Doc drift: do telegram-companion-bot/ROADMAP.md and IMPROVEMENTS_PLAN.md
   statuses agree with the CHANGELOG (anything shipped still marked pending, or
   marked shipped without a matching CHANGELOG entry)?
3. CI on main: latest evals-workflow run on main. Use the github MCP tools if this
   session has them; otherwise WebFetch
   https://api.github.com/repos/biggieb327-lgtm/SillyTavernPresets/actions/runs?branch=main&per_page=1
   (public repo). A red run on main is a deploy blocker — if found, lead the
   report with it.
4. Routine sync: if the claude-code-remote MCP list_triggers tool is available,
   compare its output to .claude/operating/routines.md (every live Routine
   documented, every documented Routine live, prompts matching).
5. Operational log: rows in .claude/memory/operational-log.md still match the
   fixed format (| Date | failure | root cause | system patch | eval | next |).

If a check's tooling is unavailable in this session, report that check as
"SKIPPED (tooling unavailable)" — never guess and never report a skipped check as
green. End with a short report: "hygiene-check: all green" if nothing found,
otherwise one line per finding, most severe first. You run in a fresh session and
cannot see last week's report — do not claim a finding is new or recurring; the
owner and the monthly improvement loop own that judgment. Fix nothing.
```
