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
  `trig_01FucVg8ikSvULSzB5H4Swpt` deleted). **Prompt updated 2026-08-03**, owner
  decision (same trigger id, via `update_trigger`, applied to the live trigger
  the same day — this file's own copy of that update was NOT written at the
  time, and only caught/backfilled 2026-08-07, see below): dropped Reddit as an
  external-ideas source entirely. Diagnosis (verified live 2026-08-03,
  superseding the 2026-07-20 "proxy CONNECT 403" note): the CONNECT tunnel and
  TLS handshake to `reddit.com` succeed fine — the block is a plain HTTP 403
  from Reddit's own Cloudflare, returned *after* a completed connection.
  `WebFetch` refuses `reddit.com` outright; `WebSearch` with
  `allowed_domains: ["reddit.com"]` errors `"reddit.com" not accessible to our
  user agent` (Anthropic's own crawler is blocked from the domain, independent
  of this environment's proxy); unrestricted `WebSearch` returns zero actual
  `reddit.com` URLs. Reddit's app-registration flow (`reddit.com/prefs/apps`)
  also redirects to **Devvit**, a platform for building apps that run *inside*
  Reddit (owner-confirmed by trying it) — not obviously a source of portable
  API credentials for external read access. The curl-based Reddit step
  (permanently SKIPPED since creation anyway — see 2026-07-20 note above) was
  replaced with a WebSearch-only "External ideas" scan. **Prompt updated again
  2026-08-07** (same trigger id, via `update_trigger`):
  restored Reddit — and added Substack — via a custom `idea-scraper-actor/`
  Apify actor (repo root), which reached both through Apify's own
  infrastructure instead of the fired session's own network path, so the
  2026-08-03 blocker doesn't apply to it. The WebSearch-only scan is kept as a
  fallback for when Apify itself isn't configured/reachable. **Prompt updated
  a third time later the same day 2026-08-07** (same trigger id, via
  `update_trigger`): retired `idea-scraper-actor/` a few hours after deploying
  it — the owner pointed at Apify's hosted `trudax/reddit-scraper-lite` actor
  (id `oAuCIx3ItNrs2okjQ`, confirmed via a live Apify Console session, not
  guessed) and asked to call it directly instead of wrapping it. **Prompt
  updated a fourth time the same day 2026-08-07** (same trigger id, via
  `update_trigger`): the direct call was rejected — `"The Creator plan does
  not include permission to run public Actors"` (owner-reported, verbatim
  Apify error), confirmed independently by an on-demand fire of this Routine
  finding nothing to propose. This is a billing-tier restriction on running
  *any* public Actor, called *any* way — it would have blocked the retired
  wrapper actor identically, since `Actor.call()` on a public Actor from
  inside your own Actor is still running a public Actor. Rebuilt
  `idea-scraper-actor/` v0.2 to depend on no other Actor at all: it fetches
  Reddit's own public `{subreddit}/top.json` listing directly, routed through
  Apify's own residential proxy (which the Creator plan does permit, since
  it's the actor's own network egress, not another Actor's execution) —
  unverified against a live run as of this update, see the actor's README.
  Substack unchanged, direct RSS, no proxy needed. **Actor rebuilt and verified
  live 2026-08-11** (owner session; live trigger prompt updated the same day and
  mirrored here in the same session, per this file's rule): the design described
  above never worked end to end. Five blockers, each hidden behind the last:
  (1) `main()` was defined but never invoked, so v0.2-v0.3.2 exited 0 having done
  nothing — indistinguishable from a genuinely empty result; (2) the Actor ran under
  `LIMITED_PERMISSIONS`, whose scoped run token cannot read the account proxy
  password, so `create_proxy_configuration()` failed with "Insufficient permissions"
  for *every* group — which is why swapping groups never helped. **The Actor must
  stay FULL_PERMISSIONS**; (3) with permissions fixed, httpx 0.28 had removed the
  `proxies=` kwarg the pinned apify SDK 1.x still passes, so `requirements.txt` now
  pins `httpx>=0.24,<0.28` — **do not remove that pin**; (4) with the proxy finally
  attaching, Reddit still returned an identical 403 from residential, static-
  datacenter and rotating-datacenter IPs, against both `www.reddit.com/*.json` and
  `api.reddit.com` — the block is Cloudflare fingerprinting the client, not IP
  reputation, so **buying more proxy types cannot fix it**; (5) Reddit's **Atom**
  feeds (`/r/{sub}/top.rss`) are not blocked at all, from any IP including Apify's
  bare compute IP. The Actor now reads Atom with no proxy (residential stays second
  in an ordered strategy list as automatic failover; a forced `direct` run returned
  `strategy=direct reddit=5`). Reddit OAuth is not an available fallback:
  `reddit.com/prefs/apps` still redirects to Devvit (re-confirmed 2026-08-11), so no
  client_id/secret can be issued. Substack verified live the same day (5 rows from
  emergingai.substack.com — the first time that path had ever been exercised). Also
  fixed in the same pass: `published_at` is now always ISO 8601 across both sources
  (Substack emitted RFC 2822, so the dataset could not be sorted across sources);
  summaries are no longer capped at 500 chars (one measured Reddit post carried
  14,360 chars of body); link/image posts carry an `external_url` instead of a
  boilerplate summary; and the Reddit-only `require_reddit` guard became
  `fail_on_empty_source`, covering every requested source — a total Substack failure
  previously exited 0 with an empty dataset. **`APIFY_API_TOKEN` was rotated
  2026-08-11** after the old value was exposed; the Claude Code Remote environment
  variable must hold the new token or every firing will 401.
- **Reddit + Substack access (rewritten 2026-08-11):** the Actor reads Reddit's
  **Atom** feed (`/r/{sub}/top.rss`) and Substack's RSS directly, with **no proxy**
  — see the 2026-08-11 history above for why the JSON listings are permanently
  unusable and why more proxy types will not help. Called over `api.apify.com` with
  the token in an `Authorization: Bearer` **header, never in the URL** (`?token=`
  leaks the credential into access logs and browser history). Requires
  `APIFY_API_TOKEN` (rotated 2026-08-11 — the environment variable must hold the
  current value) and `APIFY_ACTOR_ID` on the Claude Code Remote environment. If
  either is unset, or `api.apify.com` returns a CONNECT/tunnel 403, the step
  self-reports SKIPPED and falls back to the WebSearch-only scan. Note that
  `fail_on_empty_source` defaults true, so a run that reaches Reddit but produces
  nothing now FAILS with a status message naming the cause, instead of returning
  `[]`. Fired sessions carry no MCP connectors. **Substack moved out
  2026-08-11** (same session as the live prompt edit): `emergingai.substack.com`
  and `substack.com/@gencay` were removed from this Routine and given to the new
  `practice-scan-weekly` below. Evidence for the split — the 2026-08-11 on-demand
  fire of both monthly Routines pulled 20 Substack rows and yielded exactly one
  usable idea between them; character-pass's own report called the rest "general
  Claude/agent-building content with no card-writing angle." That material is
  about memory and working practice, which is what `practice-scan-weekly` is for.
  Each Routine now owns one source set.
- **Schedule:** cron `0 9 1 * *` — 09:00 on the 1st of each month (assumed UTC;
  exact hour is not load-bearing).
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`) — the
  analysis must not inherit a stale conversation.
- **Notifications:** push on completion (email off) — `update_trigger` cannot add
  notifications, hence the delete-and-recreate.
- **What it does:** the monthly improvement loop described in CLAUDE.md — runs the
  `improvement-analyst` role over the logs and pushes at most one evidence-based
  proposal to `claude/improvement-loop`, never to `main`. Since 2026-07-20 it also
  runs a bounded external-ideas scan — Reddit + Substack via `idea-scraper-actor/`
  (owner's own Apify Actor, fetching Reddit's public JSON directly through Apify's
  proxy — no public Actor involved), max 10 items per source per run and
  nothing older than 31 days, plus a WebSearch fallback/supplement — and may append up to 3 URL-cited "External ideas
  (unvetted — owner approval required)" to the same proposal file — ideas only,
  never implemented by the loop.

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
3. External ideas (runs whether or not a pattern qualified): bounded external
   scan for ideas genuinely applicable to this companion-bot fleet (companion
   features, python-telegram-bot pitfalls, model/API practices).
   Primary source: `idea-scraper-actor/` (repo root; see its README) — the
   owner's own Apify Actor, fetching Reddit's public JSON listing through
   Apify's own proxy and Substack's public RSS directly. Not a public Actor
   (this Apify account's plan cannot run one — see this Routine's history
   above). Requires APIFY_API_TOKEN and APIFY_ACTOR_ID set as environment
   variables; if either is unset, or the call fails with a CONNECT/tunnel 403
   (api.apify.com itself blocked), report this part as "SKIPPED (Apify not
   configured/reachable; see idea-scraper-actor/README.md)" and fall back to
   the WebSearch pass below only. Otherwise:
   curl -sS -X POST \
     "https://api.apify.com/v2/acts/$APIFY_ACTOR_ID/run-sync-get-dataset-items" \
     -H "Authorization: Bearer $APIFY_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"subreddits": ["SillyTavernAI", "LocalLLaMA", "TelegramBots"], "reddit_timeframe": "month", "substack_publications": [], "max_items_per_source": 10, "max_age_days": 31}'
   Never put the token in the URL (?token=) — it leaks into access logs.
   Read titles/URLs/body text straight out of whatever JSON keys the response
   actually has. Each row is {source, title, url, external_url, summary,
   published_at, community}. A link/image post has an EMPTY summary and its
   destination in external_url — that is normal, not a failure. published_at is
   always ISO 8601 or null.
   (max_items_per_source of 10 and max_age_days of 31 bound Apify usage and hold
   the scan to the last month — do not raise either without owner approval.
   substack_publications is empty ON PURPOSE as of 2026-08-11: both publications
   moved to practice-scan-weekly, which owns them. Do not add them back here.)
   Supplement with WebSearch (max ~5 queries), scoped to sources a fired
   session can actually reach — GitHub (python-telegram-bot's own issues/
   discussions/wiki, comparable companion-bot projects), technical blogs,
   Hacker News. Never fabricate sources. If any ideas apply, add an
   "External ideas (unvetted — owner approval required)" section to the same
   <YYYY-MM>.md file: max 3 ideas, each with its source URL and one line on
   why it fits this fleet. Ideas only — never implemented by this loop.
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
  ROADMAP/IMPROVEMENTS_PLAN status drift,
  operational-log format, and (added 2026-07-27) **mistake-trend
  escalation**: runs `sweep.py constraints-drift`, then judges whether Minor
  entries in `.claude/memory/constraints.md` share a root cause and proposes the
  constraint plus the mechanism that would prevent it (hook / scanner / eval /
  skill). It fixes nothing and pushes nothing; findings go to the owner, and
  recurring ones feed the monthly improvement loop.
- **Why here and not a new Routine (2026-07-27):** a weekly trend scanner was
  wanted for constraints.md. This Routine was already weekly, already
  report-only, and already fed the improvement loop — a fourth Routine would
  have duplicated it and drifted. The deterministic half lives in
  `sweep.py constraints-drift` so it is testable and runnable on demand; only
  the semantic clustering needs the LLM.
- **Two checks removed 2026-07-29 — they could never run.** Fired sessions carry no
  MCP tools at all (the trigger's `session_context.allowed_tools` lists none), and
  in this environment the GitHub REST API is reachable *only* through the `github`
  MCP tools: direct `api.github.com` calls are refused by the agent proxy with 403
  whether or not a token is sent, and the env's `GITHUB_TOKEN`/`GH_TOKEN` are
  14-char `prox…` sentinels that work only for git over the local relay. So:
  - **CI state on `main`** (was check 3) is gone. The old prompt's fallback —
    unauthenticated WebFetch of `api.github.com/…/actions/runs`, annotated
    "(public repo)" — broke when the repo went private on 2026-07-28 and was
    proxy-blocked regardless. GitHub's own failed-run email on `main` is the
    alerting path now.
  - **Routine↔this-file sync** (was check 4) is gone. It needs
    claude-code-remote `list_triggers`, also MCP-only. It is now an **on-demand
    check the owner runs in a full session** — where `list_triggers` does work.
  Both were failing safe (the prompt bans reporting a skipped check as green), so
  the brief degraded honestly rather than lying — but the checks were dead weight.

### Verbatim prompt

```
Weekly hygiene check for the SillyTavernPresets repo. This Routine is recorded in
.claude/operating/routines.md — read that file first; if this prompt and that file
disagree, stop and report the drift to the owner instead of proceeding.

Act as the context-librarian agent: read .claude/agents/context-librarian.md and
follow its role. This run is REPORT-ONLY: make no commits, push nothing, create no
branches, modify no Routines, and edit no files. Read-only actions only.

Two checks that used to be here are gone because a fired session cannot run them
(verified 2026-07-29): CI state on main needs the GitHub REST API, and
Routine-to-routines.md sync needs claude-code-remote list_triggers. Both are
MCP-only, and fired sessions carry no MCP tools. GitHub's own failed-run email on
main covers CI; Routine sync is now an on-demand check the owner runs in a full
session. Do not attempt either one, and do not report them as green, red, or
skipped — they are out of scope, not unavailable.

Check, quoting the exact lines/values you compared as evidence:
1. Version sync: BOT_VERSION in telegram-companion-bot/bot.py vs the newest "## v"
   heading in telegram-companion-bot/CHANGELOG.md.
2. Doc drift: do telegram-companion-bot/ROADMAP.md and IMPROVEMENTS_PLAN.md
   statuses agree with the CHANGELOG (anything shipped still marked pending, or
   marked shipped without a matching CHANGELOG entry)?
3. Operational log: rows in .claude/memory/operational-log.md still match the
   fixed format (| Date | failure | root cause | system patch | eval | next |).

4. MISTAKE TRENDS — escalate what is recurring. Run:
       python3 .claude/tools/sweep.py constraints-drift
   It mechanically reports three things: a constraint at seen: 2+ carrying no
   "**Graduated" line (by the file's own rule it owes a hook, eval, or sweep.py
   scanner, not more prose); a Minor backlog over 8 entries; and pairs of Minor
   entries sharing distinctive vocabulary.
   Then do the judgement the scanner cannot. Read .claude/memory/constraints.md and
   decide whether any Minor entries share a ROOT CAUSE — the scanner only matches
   words, so it both misses differently-worded pairs and invents pairs that merely
   mention the same file. For each real cluster, propose in your report: the shared
   cause in one sentence, the numbered constraint it should become, and which
   mechanism would actually prevent it (a hook for "the agent did X", a sweep.py
   scanner for "this shape exists elsewhere in the code", an eval for "this
   regression can recur in bot.py", a skill for "the procedure was wrong").
   PROPOSE ONLY — do not edit constraints.md, do not write the hook. Escalation is
   the owner's call, and the graduation itself belongs in a reviewed session.

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
- **What it does:** fast repo-side morning triage — commits shipped in
  the last day, BOT_VERSION↔changelog sync, and unmerged claude/* branches ahead of
  main. Report-only; fixes nothing; explicitly does NOT cover the fleet/phone (it
  can't see them) and does not duplicate the weekly hygiene check's deeper passes.
- **CI check removed 2026-07-29 — it could never run.** Same root cause as
  hygiene-check-weekly above: the GitHub REST API is MCP-only in this environment
  and fired sessions carry no MCP tools, so the prompt's "(public repo)" WebFetch
  fallback was doubly dead — the repo went private 2026-07-28, and the agent proxy
  403s `api.github.com` regardless. GitHub's own failed-run email on `main` is the
  alerting path. All three surviving checks are pure git, which **does** work in a
  fired session (`git fetch origin main` verified OK via the local relay).

### Verbatim prompt

```
Daily ops brief for the SillyTavernPresets repo. This Routine is recorded in
.claude/operating/routines.md — read that file first; if this prompt and that file
disagree, stop and report the drift to the owner instead of proceeding.

This is a fast morning triage read, REPORT-ONLY: make no commits, push nothing,
create no branches, modify no Routines, and edit no files. Read-only actions only.
The deeper weekly hygiene check owns doc drift and log format — do
not duplicate it. This brief cannot see the phone or the bots; it covers the repo
side only, and must not speculate about fleet health.

This brief does NOT check CI. The GitHub REST API is reachable only through the
github MCP tools, which fired sessions do not carry (verified 2026-07-29), so no CI
check here could ever run — GitHub's own failed-run email on main is the alerting
path. Do not attempt one, and do not report CI as green, red, or skipped.

Check:
1. What shipped: `git fetch origin main` then `git log --since="26 hours ago"
   --oneline origin/main` — list the commits (or "nothing new").
2. Version sync: BOT_VERSION in telegram-companion-bot/bot.py (on origin/main) vs
   the newest "## v" heading in telegram-companion-bot/CHANGELOG.md — one line,
   match or mismatch.
3. Stalled work: `git branch -r` — any claude/* branch ahead of origin/main
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

- **Created:** 2026-07-20, owner-requested; recreated 3× same day — curl Reddit
  path, then preset review, then the `TheAtelierV5`→`TheAtelier_2.0` rename
  (trigger id `trig_01VXMxTLk8ZKwQ61tC3JxkCA`; previous ids
  `trig_01Df8nyGoMAoau5fidB9dhSn`, `trig_01T9Jjcn2ehwGGAJWovRFdNg`,
  `trig_01F9vhqcJXw2VWkGkzgwcW7i` deleted). **Prompt updated 2026-07-26** (same
  trigger id, via `update_trigger` — no recreate): repointed at the
  `character-reviewer` agent contract instead of inlining the review rules, and two
  stale references fixed — the prompt told the fired session to read a "Character
  notes section of CLAUDE.md" that does not exist (the binding register rules are in
  `edit-cards-and-presets`, section "Respect per-character canon"), and the live
  prompt was missing this file's "don't be fooled by a leftover high V-number"
  clause, so the two disagreed and a literal reading of the drift rule would have
  halted the pass. **Prompt updated 2026-08-03** (same trigger id, via
  `update_trigger` — no recreate, and NOT mirrored to this file at the time —
  caught and backfilled 2026-08-07, same drift as `improvement-loop-monthly`
  above, same session): the curl-based Reddit step was replaced with a
  WebSearch-only "External ideas" scan that dropped Reddit as a source
  entirely, same diagnosis as `improvement-loop-monthly` (Cloudflare/WebFetch/
  WebSearch can't reach reddit.com; Reddit's app-registration now redirects to
  Devvit). **Prompt updated again 2026-08-07** (same trigger id, via
  `update_trigger`): restored Reddit, and added Substack, via a call to a
  custom `idea-scraper-actor/` (repo root) — same actor `improvement-loop-monthly`
  used, reaching both through Apify's infrastructure instead of the fired
  session's own network path. The WebSearch-only scan is kept as a fallback.
  **Prompt updated a third time later the same day 2026-08-07** (same trigger
  id, via `update_trigger`): retired `idea-scraper-actor/` in favor of calling
  Apify's hosted `trudax/reddit-scraper-lite` actor (id `oAuCIx3ItNrs2okjQ`)
  directly — same pivot and same rationale as `improvement-loop-monthly`
  above, same session. Substack moved to a direct RSS `curl`. **Prompt
  updated a fourth time the same day 2026-08-07** (same trigger id, via
  `update_trigger`): the direct call was rejected by the owner's Apify plan
  (Creator tier cannot run any public Actor) — same finding and same fix as
  `improvement-loop-monthly` above, same session. Rebuilt `idea-scraper-actor/`
  v0.2 to fetch Reddit's own public JSON directly through Apify's proxy
  instead of calling another Actor, and reinstated as the primary source. **Actor rebuilt and verified
  live 2026-08-11** (owner session; live trigger prompt updated the same day and
  mirrored here in the same session, per this file's rule): the design described
  above never worked end to end. Five blockers, each hidden behind the last:
  (1) `main()` was defined but never invoked, so v0.2-v0.3.2 exited 0 having done
  nothing — indistinguishable from a genuinely empty result; (2) the Actor ran under
  `LIMITED_PERMISSIONS`, whose scoped run token cannot read the account proxy
  password, so `create_proxy_configuration()` failed with "Insufficient permissions"
  for *every* group — which is why swapping groups never helped. **The Actor must
  stay FULL_PERMISSIONS**; (3) with permissions fixed, httpx 0.28 had removed the
  `proxies=` kwarg the pinned apify SDK 1.x still passes, so `requirements.txt` now
  pins `httpx>=0.24,<0.28` — **do not remove that pin**; (4) with the proxy finally
  attaching, Reddit still returned an identical 403 from residential, static-
  datacenter and rotating-datacenter IPs, against both `www.reddit.com/*.json` and
  `api.reddit.com` — the block is Cloudflare fingerprinting the client, not IP
  reputation, so **buying more proxy types cannot fix it**; (5) Reddit's **Atom**
  feeds (`/r/{sub}/top.rss`) are not blocked at all, from any IP including Apify's
  bare compute IP. The Actor now reads Atom with no proxy (residential stays second
  in an ordered strategy list as automatic failover; a forced `direct` run returned
  `strategy=direct reddit=5`). Reddit OAuth is not an available fallback:
  `reddit.com/prefs/apps` still redirects to Devvit (re-confirmed 2026-08-11), so no
  client_id/secret can be issued. Substack verified live the same day (5 rows from
  emergingai.substack.com — the first time that path had ever been exercised). Also
  fixed in the same pass: `published_at` is now always ISO 8601 across both sources
  (Substack emitted RFC 2822, so the dataset could not be sorted across sources);
  summaries are no longer capped at 500 chars (one measured Reddit post carried
  14,360 chars of body); link/image posts carry an `external_url` instead of a
  boilerplate summary; and the Reddit-only `require_reddit` guard became
  `fail_on_empty_source`, covering every requested source — a total Substack failure
  previously exited 0 with an empty dataset. **`APIFY_API_TOKEN` was rotated
  2026-08-11** after the old value was exposed; the Claude Code Remote environment
  variable must hold the new token or every firing will 401. **Substack moved out
  2026-08-11** (same session as the live prompt edit): `emergingai.substack.com`
  and `substack.com/@gencay` were removed from this Routine and given to the new
  `practice-scan-weekly` below. Evidence for the split — the 2026-08-11 on-demand
  fire of both monthly Routines pulled 20 Substack rows and yielded exactly one
  usable idea between them; character-pass's own report called the rest "general
  Claude/agent-building content with no card-writing angle." That material is
  about memory and working practice, which is what `practice-scan-weekly` is for.
  Each Routine now owns one source set.
- **Schedule:** cron `0 14 15 * *` — 14:00 UTC (~07:00 Pacific) on the 15th of each
  month, offset from the improvement loop's 1st-of-month slot.
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`).
- **Notifications:** push on completion (email off).
- **What it does:** proposal-only content pass, run by delegating to the
  `character-reviewer` agent contract (`.claude/agents/character-reviewer.md`) the
  same way the other Routines delegate to `improvement-analyst` and
  `context-librarian` — the contract owns the review method, the proposal-only
  posture, the per-character canon (via `edit-cards-and-presets`) and the evidence
  bar; this prompt owns only the run scope, the Reddit + Substack step, and the output/branch
  discipline. **Changing the review method means editing the agent file, not this
  prompt.** The contract's ≤25-line output limit binds the session's final report,
  not the PROPOSALS file. Concretely: reviews cards dropped in
  `character-review/` (the root-level inbox; see its README), spot-checks the six live fleet
  cards/seeds for internal contradictions and drift, reviews presets (owner-scoped
  2026-07-20: the latest root SillyTavern presets — currently `TheAtelier_2.0.json`
  and `UnifiedWritersRoom_V32.json` — plus `telegram-companion-bot/preset.txt`, the
  fleet-wide texting voiceprint), and runs a bounded Reddit + Substack scan via
  `idea-scraper-actor/` (owner's own Apify Actor) for card-writing techniques
  (every idea URL-cited). Findings go to
  `character-review/PROPOSALS-<YYYY-MM>.md` on branch `claude/character-review`,
  never to `main`, and no card/seed/preset is ever edited — the owner applies
  accepted proposals interactively under `edit-cards-and-presets`. `preset.txt`
  proposals carry a mandatory before/after quote and a fleet-wide-blast-radius
  note (it feeds all six bots).
- **Reddit + Substack access (rewritten 2026-08-11):** same path as
  `improvement-loop-monthly`. The Actor reads Reddit's
  **Atom** feed (`/r/{sub}/top.rss`) and Substack's RSS directly, with **no proxy**
  — see the 2026-08-11 history above for why the JSON listings are permanently
  unusable and why more proxy types will not help. Called over `api.apify.com` with
  the token in an `Authorization: Bearer` **header, never in the URL** (`?token=`
  leaks the credential into access logs and browser history). Requires
  `APIFY_API_TOKEN` (rotated 2026-08-11 — the environment variable must hold the
  current value) and `APIFY_ACTOR_ID` on the Claude Code Remote environment. If
  either is unset, or `api.apify.com` returns a CONNECT/tunnel 403, the step
  self-reports SKIPPED and falls back to the WebSearch-only scan. Note that
  `fail_on_empty_source` defaults true, so a run that reaches Reddit but produces
  nothing now FAILS with a status message naming the cause, instead of returning
  `[]`. Fired sessions carry no MCP connectors.

### Verbatim prompt

```
Monthly character content pass for the SillyTavernPresets repo. This Routine is
recorded in .claude/operating/routines.md — read that file first; if this prompt
and that file disagree, stop and report the drift to the owner instead of
proceeding.

Act as the character-reviewer agent: read .claude/agents/character-reviewer.md and
follow its mission, proposal-only posture, method, and evidence requirements
exactly. This run is Mode B (proactive review) — there is no reported voice defect
to triage, so the Mode A boundary check does not apply unless a finding turns out
to be a prompt-assembly bug rather than a content one, in which case report it as
a CODE verdict with its bot.py evidence and propose nothing for the card. The
contract's <=25-line output limit applies to your final report to the owner, NOT to
the PROPOSALS file, which is this Routine's deliverable and may run as long as the
findings require. Steps 4-6 below are owner-approved additions to that contract.

The contract loads .claude/skills/edit-cards-and-presets/SKILL.md, whose "Respect
per-character canon" section holds the binding register rules — these cards ship to
relationships someone actually has. PROPOSAL-ONLY: never edit any character card,
seed file, or preset, and never push to main.

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
      each family (currently TheAtelier_2.0.json and UnifiedWritersRoom_V32.json;
      pick the newest of each family and skip superseded versions. Note the
      Atelier numbering RESET: the "2.0" rebuild is newer than the old V-series,
      so "2.0" > "V28" > "V5" despite the smaller number — don't be fooled by a
      leftover high V-number). These deploy nowhere (the owner loads
      them into SillyTavern by hand), so this is prompt/instruction-quality
      critique: internal contradictions, redundant or conflicting directives,
      structural clarity. Tag proposals [root preset].
   b. telegram-companion-bot/preset.txt — the shared texting voiceprint feeding
      ALL SIX live bots. Review for internal consistency, contradictions, and
      drift from the characters' registers. The contract's fleet-wide
      blast-radius rule applies here: every preset.txt proposal MUST include a
      before/after quote and an explicit note of the fleet-wide effect. Tag
      proposals [fleet preset].
4. External ideas: bounded pass for card-writing techniques applicable to the
   characters/presets reviewed above.
   Primary source: `idea-scraper-actor/` (repo root; see its README) — the
   owner's own Apify Actor, fetching Reddit's public JSON listing through
   Apify's own proxy and Substack's public RSS directly. Not a public Actor
   (this Apify account's plan cannot run one — see this Routine's history
   above). Requires APIFY_API_TOKEN and APIFY_ACTOR_ID set as environment
   variables; if either is unset, or the call fails with a CONNECT/tunnel 403
   (api.apify.com itself blocked), report this part as "SKIPPED (Apify not
   configured/reachable; see idea-scraper-actor/README.md)" and fall back to
   the WebSearch pass below only. Otherwise:
   curl -sS -X POST \
     "https://api.apify.com/v2/acts/$APIFY_ACTOR_ID/run-sync-get-dataset-items" \
     -H "Authorization: Bearer $APIFY_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"subreddits": ["SillyTavernAI"], "reddit_timeframe": "month", "substack_publications": [], "max_items_per_source": 10, "max_age_days": 31}'
   Never put the token in the URL (?token=) — it leaks into access logs.
   Read titles/URLs/body text straight out of whatever JSON keys the response
   actually has. Each row is {source, title, url, external_url, summary,
   published_at, community}. A link/image post has an EMPTY summary and its
   destination in external_url — that is normal, not a failure. published_at is
   always ISO 8601 or null.
   (max_items_per_source of 10 and max_age_days of 31 bound Apify usage and hold
   the scan to the last month — do not raise either without owner approval.
   substack_publications is empty ON PURPOSE as of 2026-08-11: both publications
   moved to practice-scan-weekly, which owns them. Do not add them back here.)
   Supplement with WebSearch (max ~5 queries), scoped to sources a fired
   session can actually reach — SillyTavern's own GitHub (wiki, discussions,
   issues), character-card-writing blogs and guides, HuggingFace discussions.
   Cite every external idea with its source URL; never fabricate sources.
5. If there are findings or ideas: write ONE file
   character-review/PROPOSALS-<YYYY-MM>.md — specific suggestions, each tagged
   [inbox card] / [fleet card] / [root preset] / [fleet preset] / [reddit idea] /
   [substack idea] / [external idea] with its evidence or URL, phrased as
   concrete edits the owner could apply.
   NOTHING is applied without owner approval. Commit only that file to the branch
   claude/character-review (reset it to origin/main first if it already exists)
   and push ONLY to claude/character-review — NEVER to main or any other branch.
6. If nothing to propose: push NOTHING, create NO branch, and end with
   "character-pass: no proposals this month".
```

---

---

## practice-scan-weekly

- **Created:** 2026-08-11, owner-requested. Owns the two Substack publications
  that `improvement-loop-monthly` and `character-pass-monthly` gave up the same
  day (see their entries above). Reason for the split, from evidence rather than
  taste: the 2026-08-11 on-demand fire of both monthly Routines pulled 20 Substack
  rows and produced exactly one usable idea between them, and character-pass's own
  report judged the rest "general Claude/agent-building content with no
  card-writing angle." The material is good — it was pointed at the wrong two
  Routines. This one asks the questions that material actually answers.
- **Schedule:** cron `0 15 * * 4` — 15:00 UTC every Thursday. Offset from every
  other Routine (ops-brief 14:00 daily, hygiene-check Mon 09:00, improvement-loop
  1st 09:00, character-pass 15th 14:00) so two heavy unattended sessions never
  compete.
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`).
- **Notifications:** push on completion (email off).
- **Why weekly and `max_age_days: 8`:** the monthly Routines use 31 to match their
  cadence. This one runs every 7 days, so 8 gives one day of margin — consecutive
  runs neither skip a post published just after a run nor re-report one already
  seen. Raising it re-reports; lowering it drops posts.
- **No WebSearch fallback, deliberately.** The other Routines fall back to a
  WebSearch scan when Apify is unreachable, because their external-ideas step is a
  supplement to work they do anyway. This Routine *is* the two publications — with
  them unreachable there is nothing for it to do, and a WebSearch substitute would
  quietly turn a scoped scan into an open-ended trawl. It reports SKIPPED and ends.
- **What it does:** reads the week's posts from `emergingai.substack.com` and
  `substack.com/@gencay` via `idea-scraper-actor/` and judges each against two
  questions: (A) **fleet memory** — would this improve the companion bots' memory,
  retrieval, forgetting or grounding, judged against the live guard categories in
  `.claude/memory/operational-log.md`; and (B) **operating** — would this improve
  how this repo's own agent system works: `.claude/skills/`, `.claude/agents/`,
  `.claude/hooks/`, the Routines, or the evidence discipline in `CLAUDE.md`.
  Findings go to `.claude/memory/practice-scan/<YYYY-MM-DD>.md` on branch
  `claude/practice-scan`, max 5 ideas, each tagged `[fleet memory]` or
  `[operating]`. **Proposal-only** — it edits no code, card, preset, hook, skill,
  agent or eval, and never pushes to `main`.
- **Evidence rule** borrowed from `.claude/agents/research-scout.md`: every idea
  carries its source URL *and* an exact quoted line from the item's own text, and
  nothing may be quoted from a `WebFetch` summary — that output is a paraphrase
  from a small model and its quotes can be compressed or invented. To read more of
  an article than the scraped summary carries, `curl` the URL and quote those
  bytes.
- **Reddit + Substack access:** same `idea-scraper-actor/` path as the monthly
  Routines — Atom/RSS, no proxy, token in an `Authorization: Bearer` header, never
  in the URL. Requires `APIFY_API_TOKEN` (rotated 2026-08-11) and `APIFY_ACTOR_ID`
  on the Claude Code Remote environment. `subreddits` is empty for this Routine:
  Reddit belongs to the two monthly Routines.

### Verbatim prompt

```
Weekly practice scan for the SillyTavernPresets repo. This Routine is recorded in
.claude/operating/routines.md — read that file first; if this prompt and that file
disagree, stop and report the drift to the owner instead of proceeding.

PROPOSAL-ONLY. Write no code and edit no card, seed, preset, hook, skill, agent,
eval, or Routine. Never push to main. Your only deliverable is one proposals file
on the branch claude/practice-scan.

Scope — two questions, both about how things WORK, not what characters say:
  A. FLEET MEMORY. Would this make the companion bots' memory, retrieval,
     forgetting, or grounding better? Judge against the live guard categories
     named in .claude/memory/operational-log.md (e.g. memory_ungrounded,
     note_ungrounded), not against a general idea of what memory should be.
  B. OPERATING. Would this make this repo's own agent system work better —
     .claude/skills/, .claude/agents/, .claude/hooks/, the Routines themselves,
     or the evidence and verification discipline in CLAUDE.md?

1. Read .claude/memory/operational-log.md and .claude/memory/constraints.md first,
   so relevance is judged against real open problems rather than guessed ones.
2. Fetch the week's posts. Requires APIFY_API_TOKEN and APIFY_ACTOR_ID as
   environment variables; if either is unset, or the call fails with a
   CONNECT/tunnel 403 (api.apify.com itself blocked), report
   "SKIPPED (Apify not configured/reachable; see idea-scraper-actor/README.md)"
   and END. This Routine has no WebSearch fallback on purpose — it IS these two
   publications, and a substitute would turn a scoped scan into an open trawl.
   curl -sS -X POST \
     "https://api.apify.com/v2/acts/$APIFY_ACTOR_ID/run-sync-get-dataset-items" \
     -H "Authorization: Bearer $APIFY_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"subreddits": [], "substack_publications": ["https://emergingai.substack.com", "https://substack.com/@gencay"], "max_items_per_source": 10, "max_age_days": 8}'
   Never put the token in the URL (?token=) — it leaks into access logs.
   Each row is {source, title, url, external_url, summary, published_at,
   community}; published_at is always ISO 8601 or null. max_age_days of 8 covers
   the week since the last run plus a day of margin — do not change it without
   owner approval. An empty result is a normal quiet week, not a failure.
3. Judge each item against A and B. MOST ITEMS WILL NOT APPLY. Say so and drop
   them. Do not stretch an article into relevance to fill the file — a week with
   two real ideas is a better result than a week with five padded ones.
4. Evidence rule (from .claude/agents/research-scout.md): every idea carries its
   source URL AND an exact quoted line from the item's own text. Never quote from
   a WebFetch summary — that output is a paraphrase from a small model and its
   quotes can be compressed or invented. If you need more of an article than the
   scraped summary carries, curl the URL and quote the bytes you fetched.
5. If anything applies: write ONE file
   .claude/memory/practice-scan/<YYYY-MM-DD>.md, dated the day this Routine fired.
   Max 5 ideas, each tagged [fleet memory] or [operating], each with its URL, its
   quoted line, and one line naming the specific file or behavior it would change.
   Rank them by what you would do first. Commit only that file to the branch
   claude/practice-scan (reset it to origin/main first if it already exists) and
   push ONLY to claude/practice-scan — NEVER to main or any other branch.
6. If nothing applies: push NOTHING, create NO branch, and end with the one-line
   summary "practice-scan: nothing this week".
7. End with a report of <= 15 lines: what you read, what you kept, and what you
   dropped and why. You run in a fresh session and cannot see last week's report —
   do not claim an idea is new or recurring.
```

## map-fire-rate-review-2026-08-17 (one-shot)

- **Created:** 2026-08-10 (trigger id `trig_012TQTqApvyJcXWurcjVzmsV`).
- **Schedule:** `run_once_at` 2026-08-17T16:00:00Z — 09:00 Pacific. Self-disables after
  firing (`ended_reason=run_once_fired`).
- **Mode:** fresh session per firing (`create_new_session_on_fire: true`), so the prompt is
  written standalone.
- **Connectors:** none. The tool warned it could pass none through, which is correct for
  this Routine — it reads `/audit` output the owner pastes, and needs no TomTom MCP.
- **Listed here despite being a one-shot** because the exemption at the top of this file
  covers `send_later` session-bound reminders. This is a `create_trigger` one-shot that
  fires a *fresh* session a week from now, with nobody's context but its own prompt — the
  exact thing this file exists to keep visible.
- **What it does:** decides ROADMAP 3.5 phase 2's deferred per-chat map cooldown **from a
  week of evidence instead of a guess**. `MAP_INTENT` went default-on fleet-wide in
  v2026-08-10.8; v2026-08-10.10 added the `Map intent:` line to `/audit` reporting fires
  over messages-considered. ROADMAP conditioned the cooldown on "if the `[map]` log line
  ever shows over-firing", and until .10 that condition was unobservable.
- **Explicitly instructed NOT to build the cooldown by default.** The prompt says to close
  the follow-up as decided-against if the rate looks fine. A reminder that fires is not
  evidence that work is owed, and a fresh session with a build-shaped prompt will build.
- **Also carries** the open `network`-errors question (jules, ~8/day, capped at 200) so
  that thread is not lost if it goes unclosed this week.


## Retired

- **"Monthly improvement loop — SillyTavernPresets"** (`trig_01Hmkj9LUnXbKadzXTnXraq5`,
  created 2026-07-06, cron `0 16 1 * *`): undocumented predecessor of
  `improvement-loop-monthly` with a looser contract (it was allowed to *implement*
  small patches, not just propose). Superseded by the 2026-07-12 Routine above but
  never deleted — both would have fired on Aug 1. Deleted 2026-07-20.
