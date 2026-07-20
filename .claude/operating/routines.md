# Scheduled Routines (Claude Code Remote triggers)

Live schedules that act on this repo. Rule: **any change to a live Routine's prompt
must be mirrored in this file in the same session, and vice versa** — a Routine that
exists only in the scheduler (or only as prose) is invisible and will drift.

Inspect/pause/edit from any Claude Code Remote session on this repo with the
`list_triggers` / `update_trigger` / `delete_trigger` tools (claude-code-remote MCP).

Exempt from this file: `send_later` one-shots (names like `send_later <timestamp>`),
which are session-bound reminders that self-disable after firing — they may appear
in `list_triggers` without an entry here and that is not drift.

---

## improvement-loop-monthly

- **Created:** 2026-07-12; recreated 2026-07-20 three times — completion
  notifications, then the owner-approved Reddit-ideas step, then the curl-based
  Reddit access path (trigger id `trig_012bvUUnBtnaE87CbBkjyAaZ`; previous ids
  `trig_014UoejLm5Wv7TkqJC4j9CjJ`, `trig_01TyGUFRHqMrPVWhju4ZPyxE`,
  `trig_01FucVg8ikSvULSzB5H4Swpt` deleted).
- **Reddit access:** WebFetch cannot reach reddit; the prompt uses Bash curl
  against the public JSON API. As of 2026-07-20 the environment's network policy
  blocks reddit.com at the proxy (CONNECT 403) — until the owner allows
  reddit.com in the environment's network settings, the step self-reports
  SKIPPED.
- **Schedule:** cron `0 9 1 * *` — 09:00 on the 1st of each month (assumed UTC;
  exact hour is not load-bearing).
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`) — the
  analysis must not inherit a stale conversation.
- **Notifications:** push on completion (email off) — `update_trigger` cannot add
  notifications, hence the delete-and-recreate.
- **What it does:** the monthly improvement loop described in CLAUDE.md — runs the
  `improvement-analyst` role over the logs and pushes at most one evidence-based
  proposal to `claude/improvement-loop`, never to `main`. Since 2026-07-20 it also
  runs a bounded Reddit scan (max ~5 searches) and may append up to 3 URL-cited
  "External ideas (unvetted — owner approval required)" to the same proposal file
  — ideas only, never implemented by the loop.

### Verbatim prompt

```
Monthly improvement loop for the SillyTavernPresets repo. This Routine is recorded
in .claude/operating/routines.md — read that file first; if this prompt and that
file disagree, stop and report the drift to the owner instead of proceeding.

Act as the improvement-analyst agent: read .claude/agents/improvement-analyst.md
and follow its mission, method, evidence requirement, and 20-line output limit
exactly. (Step 3 below is an owner-approved 2026-07-20 addition to that contract.)

1. Read .claude/memory/operational-log.md and telegram-companion-bot/CHANGELOG.md.
2. Look for the same failure shape appearing >= 2 times that no existing hook,
   eval, or skill prevented. Required evidence: quote the >= 2 occurrences with
   dates/versions. If one qualifies, write EXACTLY ONE proposal (the pattern, the
   quoted occurrences, the one proposed patch with exact file + change, and the
   eval that would prove it worked) to
   .claude/memory/improvement-proposals/<YYYY-MM>.md. If nothing qualifies, write
   no proposal — do not invent a pattern.
3. Reddit ideas (runs whether or not a pattern qualified): bounded external scan
   for ideas genuinely applicable to this companion-bot fleet (companion
   features, python-telegram-bot pitfalls, model/API practices). Reddit access:
   WebFetch cannot reach reddit — use Bash curl against the public JSON API, e.g.
   curl -sS -H "User-Agent: SillyTavernPresets-routine/1.0"
   "https://www.reddit.com/r/SillyTavernAI/top.json?t=month&limit=25"
   for r/SillyTavernAI, r/LocalLLaMA, r/TelegramBots (max ~5 requests; WebSearch
   may supplement for discovery). If curl fails with a CONNECT/tunnel 403, the
   environment's network policy blocks reddit.com — report this step as "SKIPPED
   (network policy blocks reddit.com; owner can allow it in the environment's
   network settings)". Never fabricate sources. If any ideas apply, add an
   "External ideas (unvetted — owner approval required)" section to the same
   <YYYY-MM>.md file: max 3 ideas, each with its thread URL and one line on why
   it fits this fleet. Ideas only — never implemented by this loop.
4. If the <YYYY-MM>.md file has content: commit only that file to the branch
   claude/improvement-loop (reset it to origin/main first if it already exists)
   and push ONLY to claude/improvement-loop. NEVER push to main or any other
   branch. If the file has no content: push NOTHING, create NO branch, and end
   with the one-line summary "improvement-loop: nothing this month".
5. Do NOT implement anything, and do NOT modify bot.py, hooks, evals, or any
   other file — implementation belongs to system-fixer in a reviewed session.
```

---

## hygiene-check-weekly

- **Created:** 2026-07-17; recreated 2026-07-20 to add completion notifications —
  same prompt, schedule, and mode (trigger id `trig_011WdoTbyPKJvqz9j9TtNAW3`;
  previous id `trig_01NuXwchCqAdYNsZ92493Gi3` deleted).
- **Schedule:** cron `0 9 * * 1` — 09:00 every Monday (assumed UTC; offset from the
  monthly improvement loop, which owns the 1st of the month).
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`).
- **Notifications:** push on completion (email off).
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

---

## ops-brief-daily

- **Created:** 2026-07-20, owner-requested; recreated same day to add
  `claude/character-review` to the proposal-branch exception (trigger id
  `trig_01PJiuYuNH28cotoMoFZbD9m`; previous id `trig_018aJrJZqMVmf585Ps41aKzF`
  deleted).
- **Schedule:** cron `0 14 * * *` — 14:00 UTC daily, chosen as ~07:00 Pacific so it
  lands as a morning brief (assumption: owner is on Pacific time; not load-bearing).
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`).
- **Notifications:** push on completion (email off).
- **What it does:** fast repo-side morning triage — CI on main, commits shipped in
  the last day, BOT_VERSION↔changelog sync, and unmerged claude/* branches ahead of
  main. Report-only; fixes nothing; explicitly does NOT cover the fleet/phone (it
  can't see them) and does not duplicate the weekly hygiene check's deeper passes.
- **Known limitation:** same as hygiene-check-weekly — fired sessions carry no MCP
  connectors, so the CI check falls back to the public GitHub API via WebFetch.

### Verbatim prompt

```
Daily ops brief for the SillyTavernPresets repo. This Routine is recorded in
.claude/operating/routines.md — read that file first; if this prompt and that file
disagree, stop and report the drift to the owner instead of proceeding.

This is a fast morning triage read, REPORT-ONLY: make no commits, push nothing,
create no branches, modify no Routines, and edit no files. Read-only actions only.
The deeper weekly hygiene check owns doc drift, Routine sync, and log format — do
not duplicate it. This brief cannot see the phone or the bots; it covers the repo
side only, and must not speculate about fleet health.

Check:
1. CI on main: latest evals-workflow run. Use github MCP tools if this session has
   them; otherwise WebFetch
   https://api.github.com/repos/biggieb327-lgtm/SillyTavernPresets/actions/runs?branch=main&per_page=1
   (public repo). A red run on main is a deploy blocker — if found, lead with it.
2. What shipped: `git fetch origin main` then `git log --since="26 hours ago"
   --oneline origin/main` — list the commits (or "nothing new").
3. Version sync: BOT_VERSION in telegram-companion-bot/bot.py (on origin/main) vs
   the newest "## v" heading in telegram-companion-bot/CHANGELOG.md — one line,
   match or mismatch.
4. Stalled work: `git branch -r` — any claude/* branch ahead of origin/main
   (check with `git log origin/main..origin/<branch> --oneline`)? Per owner
   policy, an unmerged green branch ships nothing — list any, with commit count.
   Exception: claude/improvement-loop and claude/character-review ahead of main
   are proposal branches awaiting owner review — report them as that, not as
   stalled.

If a check's tooling is unavailable, report it as "SKIPPED (tooling unavailable)"
— never guess and never report a skipped check as green. Keep the whole brief
under ~10 lines, most severe first. If nothing needs the owner, end with exactly
"ops-brief: all quiet". You run in a fresh session and cannot see yesterday's
brief — do not claim anything is new or recurring. Fix nothing.
```

---

## character-pass-monthly

- **Created:** 2026-07-20, owner-requested; recreated twice same day — first for
  the curl-based Reddit access path, then to add preset review (trigger id
  `trig_01F9vhqcJXw2VWkGkzgwcW7i`; previous ids `trig_01Df8nyGoMAoau5fidB9dhSn`
  and `trig_01T9Jjcn2ehwGGAJWovRFdNg` deleted).
- **Schedule:** cron `0 14 15 * *` — 14:00 UTC (~07:00 Pacific) on the 15th of each
  month, offset from the improvement loop's 1st-of-month slot.
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`).
- **Notifications:** push on completion (email off).
- **What it does:** proposal-only content pass — reviews cards dropped in
  `character-review/` (the inbox; see its README), spot-checks the six live fleet
  cards/seeds for internal contradictions and drift, reviews presets (owner-scoped
  2026-07-20: the latest root SillyTavern presets — currently `TheAtelierV5.json`
  and `UnifiedWritersRoom_V32.json` — plus `telegram-companion-bot/preset.txt`, the
  fleet-wide texting voiceprint), and runs a bounded Reddit scan for card-writing
  techniques (every idea URL-cited). Findings go to
  `character-review/PROPOSALS-<YYYY-MM>.md` on branch `claude/character-review`,
  never to `main`, and no card/seed/preset is ever edited — the owner applies
  accepted proposals interactively under `edit-cards-and-presets`. `preset.txt`
  proposals carry a mandatory before/after quote and a fleet-wide-blast-radius
  note (it feeds all six bots).
- **Reddit access:** WebFetch cannot reach reddit; the prompt uses Bash curl
  against the public JSON API. As of 2026-07-20 the environment's network policy
  blocks reddit.com at the proxy (CONNECT 403) — until the owner allows
  reddit.com in the environment's network settings, the step self-reports
  SKIPPED. Fired sessions also carry no MCP connectors (same as the other
  Routines).

### Verbatim prompt

```
Monthly character content pass for the SillyTavernPresets repo. This Routine is
recorded in .claude/operating/routines.md — read that file first; if this prompt
and that file disagree, stop and report the drift to the owner instead of
proceeding.

PROPOSAL-ONLY: never edit any character card, seed file, or preset. Before
judging any content, read .claude/skills/edit-cards-and-presets/SKILL.md and the
Character notes section of CLAUDE.md — the per-character register rules are
binding; these cards ship to relationships someone actually has.

1. Review inbox: list character-review/ (ignore README.md and PROPOSALS-*
   files). Review each card found there against the edit-cards-and-presets
   rules: chara_card_v2 validity, internal consistency, register, lorebook
   coherence.
2. Fleet spot-check: review the six live cards named in CLAUDE.md's instance
   table (telegram-companion-bot/*.json) plus their seed dirs for internal
   contradictions and drift (e.g. Priya's geography must stay Bellevue/Eastside-
   consistent; Jules's must stay Bellingham-consistent). Findings only; fix
   nothing.
3. Preset review (proposal-only, same as everything else):
   a. Root SillyTavern generation presets — review only the LATEST version of
      each family (currently TheAtelierV5.json and UnifiedWritersRoom_V32.json;
      pick the highest version number of each family and skip superseded
      versions and TheAtelierFieldKit). These deploy nowhere (the owner loads
      them into SillyTavern by hand), so this is prompt/instruction-quality
      critique: internal contradictions, redundant or conflicting directives,
      structural clarity. Tag proposals [root preset].
   b. telegram-companion-bot/preset.txt — the shared texting voiceprint feeding
      ALL SIX live bots. Review for internal consistency, contradictions, and
      drift from the characters' registers. This is the highest-blast-radius
      file in the repo: any change hits the whole fleet at once, so every
      preset.txt proposal MUST include a before/after quote and an explicit note
      of the fleet-wide effect. Tag proposals [fleet preset].
4. Reddit ideas: bounded pass for card-writing techniques applicable to the
   characters/presets reviewed above. Reddit access: WebFetch cannot reach
   reddit — use Bash curl against the public JSON API, e.g.
   curl -sS -H "User-Agent: SillyTavernPresets-routine/1.0"
   "https://www.reddit.com/r/SillyTavernAI/top.json?t=month&limit=25"
   (and thread permalinks with .json appended) for r/SillyTavernAI and similar
   character/roleplay-writing subreddits (max ~5 requests; WebSearch may
   supplement for discovery). If curl fails with a CONNECT/tunnel 403, the
   environment's network policy blocks reddit.com — report this step as "SKIPPED
   (network policy blocks reddit.com; owner can allow it in the environment's
   network settings)". Cite every external idea with its thread URL; never
   fabricate sources.
5. If there are findings or ideas: write ONE file
   character-review/PROPOSALS-<YYYY-MM>.md — specific suggestions, each tagged
   [inbox card] / [fleet card] / [root preset] / [fleet preset] / [reddit idea]
   with its evidence or URL, phrased as concrete edits the owner could apply.
   NOTHING is applied without owner approval. Commit only that file to the branch
   claude/character-review (reset it to origin/main first if it already exists)
   and push ONLY to claude/character-review — NEVER to main or any other branch.
6. If nothing to propose: push NOTHING, create NO branch, and end with
   "character-pass: no proposals this month".
```

---

## Retired

- **"Monthly improvement loop — SillyTavernPresets"** (`trig_01Hmkj9LUnXbKadzXTnXraq5`,
  created 2026-07-06, cron `0 16 1 * *`): undocumented predecessor of
  `improvement-loop-monthly` with a looser contract (it was allowed to *implement*
  small patches, not just propose). Superseded by the 2026-07-12 Routine above but
  never deleted — both would have fired on Aug 1. Deleted 2026-07-20.
