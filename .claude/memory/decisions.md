# Decisions — what we chose, what we chose it over, and why

Sessions and the owner keep deciding things: an architecture, a deploy path, a memory-layer
shape, an approach ruled out. The rationale used to scatter — some in `CHANGELOG.md`, some
in `AUDIT-*.md` rejected claims, some in `GROUP_CHAT_DESIGN.md`, some in
`.claude/operating/fable-to-opus.md`, some only in a commit message or a chat nobody kept.
This file is the one place to answer **"why did we do it this way and not the other way?"**

It is a system-of-record file, like `operational-log.md` and `constraints.md` — durable,
reviewed, committed, greppable. It is **not** `mycelium.md`: mycelium holds transient
messages that get pruned; a decision does not age out.

## What belongs here

A decision qualifies when **all three** hold:

1. It chose among **real alternatives** — there was a fork, not one obvious path.
2. It **changes the project** — architecture, a file's or system's contract, the deploy or
   memory layer, a default that ships, a standing "we will / won't do X", or an approach
   **ruled out** so nobody re-attempts it.
3. Its rationale is **worth more than the diff** — a future session reading only the code
   would not recover *why*, and might undo it.

Record the **rejected** options as carefully as the winner. The record of what was ruled
out is worth as much as the record of what was chosen — the same reason `AUDIT-2026-07-10.md`
keeps its rejected claims instead of deleting them. A decision logged without its
alternatives is just a changelog entry in the wrong file.

## What does NOT belong here

- A routine implementation choice with one obvious path → nothing, or a code comment.
- A **system failure** and its fix → `operational-log.md` (+ `CHANGELOG.md` for bot.py).
- **Your own mistake** doing the work → `constraints.md`.
- A **standing rule** everyone must follow → `CLAUDE.md`.
- A **transient message** to the next session → `mycelium.md`.
- A raw observation you haven't classified yet → `inbox.md`.
- A fast-moving finding you don't want to commit → Notion Fleet Knowledge Base.

If a decision here hardens into a rule everyone must follow, **promote it to `CLAUDE.md`**
and leave the entry as the record of why the rule exists.

## Relationship to the older homes (cross-link, don't copy)

Decisions predating this file (2026-08-25) stay where they were written; this file does not
transcribe them. When one comes up, link it:

- **`CLAUDE.md` → "Known-deliberate — do not 'fix' these"** — standing "won't do X" calls.
- **`telegram-companion-bot/AUDIT-2026-07-10.md`** and other `*-AUDIT-*.md` — rejected claims.
- **`telegram-companion-bot/GROUP_CHAT_DESIGN.md`** — the group-chat design, and the
  alternatives its four adversarial review rounds ruled out.
- **`.claude/operating/fable-to-opus.md`** — owner-settled decisions and session-earned traps.

New decisions from here on get an entry **here**, with a link back to fuller detail if any.

## How to log one

Load the `log-decision` skill for the full procedure. The short version: append a new entry
at the top, newest first, in the format below. The session (or the owner) that **made or
ratified** the decision logs it. If a **subagent** surfaced it, the main session records it —
translated out of the agent's shorthand into repo terms first (CLAUDE.md §Vocabulary #4).

## Entry format

```
### YYYY-MM-DD | <short decision title> | status: current
**Decided:** what won, in one line.
**Over:** each alternative considered, and why it lost.
**Why:** the deciding reason — the thing that made the winner win.
**By:** owner / a session / an eval — and how it was settled (owner-confirmed, verification, etc.).
**Detail:** link to the fuller record, or `—` if this entry is the whole record.
```

- **status** — `current` (the decision stands) or `superseded` (a later entry reversed it;
  never delete the old one — point the new entry back at it, the same append-don't-erase rule
  mycelium uses). The `decisions-format` eval counts `^### 20` headers and fails on any whose
  line does not end `| status: current` or `| status: superseded`.
- **Related:** (optional) name 2-3 entries across memory files this connects to, by file
  and date or ID (e.g., `Related: oplog 2026-08-25, watchlist 2026-09-01, mycelium 2026-08-26`).
- Newest first, same as the operational log and mycelium.

---

## Entries

### 2026-09-26 | Important memories fade slower, using stored memory_confidence; only ever lengthens | status: current
**Decided:** `MEMORY_CONFIDENCE_DECAY` (default on, v2026-09-26.2, ROADMAP 7.8) scales the
decay half-life per line by `_halflife_factor`: `memory_confidence` 10 = 2x, 9 = 1.5x,
everything else 1x; an `/addmem` line (origin `manual`, no confidence) counts as 10.
**Over:** (1) a new `weight` field in the `post_reply_analysis` extraction JSON: a truer
emotional signal, but it covers only memories written after the change and changes the
extraction prompt; the owner chose confidence. (2) a graded factor across the whole 1-10
range (e.g. shortening low-confidence half-lives): auto-stored lines are all 7-10
(`MEMORY_AUTOCONF`), the live spread is unverified, and shortening would punish legacy and
review-approved lines on a signal nobody has measured; boost-only makes the worst case
"does nothing" or "auto lines fade half as fast". (3) leaving `/addmem` lines at 1x: they
would be demoted relative to auto lines rated 10, which nobody chose; this `/addmem` rule
is the session's call, stated to the owner, not the owner's instruction.
**Why:** the extraction prompt already defines `memory_confidence` as "worth remembering
long-term (10 = clearly important fact)", so the importance signal was stored and unused.
**By:** owner ("use confidence as the stand-in and build 7.8 if you're confident"); the
session checked the prompt's definition before building and could not check the live
spread, which the owner can with one grep (CHANGELOG v2026-09-26.2).
**Detail:** `telegram-companion-bot/CHANGELOG.md` v2026-09-26.2; ROADMAP 7.8.

### 2026-09-26 | A memory's use resets its decay clock; a use is a private reply the user's message is close to | status: current
**Decided:** ship `MEMORY_REINFORCE` (default on, v2026-09-26.1, ROADMAP 7.7). A use is an
archival line injected in a private chat, on the reply path (query vector present), with a
semantic term of at least `_REINFORCE_MIN_SEM` (1.5 of 3.0), counted once per calendar day.
A use fully resets the recency clock (`last_used` replaces the write date when later), and
`uses` ranks after `confidence` in `_evict_by_value`. Emotional weight slowing decay is
planned separately as ROADMAP 7.8, not built.
**Over:** (1) counting a use only when the reply actually references the memory: needs a
model call per reply, which bot-code-invariants #3 rules out. (2) counting every injected
line: code review showed a line can keep itself fresh, because `scan_text` holds the bot's
own recent replies and re-matches on keywords; proactive sends would also count with no
user present. (3) a partial reset (e.g. halving the age per use): harder to read in
`/whymem` and no evidence it ranks better; recency is capped at 1.0, so a full reset can
only undo decay, never boost a line above a fresh one, and relevance still gates every
line. (4) letting `uses` outrank `confidence` in eviction: confidence measures whether the
fact is true, and a hand-corrected conf-10 line must still outlive a busy conf-5 one.
(5) the rest of the counterparts.ai/ecosystem mechanisms: power-law decay (ranking-only,
no evidence it helps) and recall rewriting a memory (works against the audit's quote
grounding) were rejected; everything else was already built.
**Why:** before this, recency and eviction read only the write date, so the memories the
relationship keeps coming back to faded exactly like ones it never touched.
**By:** owner asked to build it and to plan 7.8 (2026-09-26); the use definition was
narrowed by a pre-merge `/code-review`, and group chats were excluded by
GROUP_CHAT_DESIGN.md §5 (no writes to per-instance files from a group).
**Detail:** `telegram-companion-bot/CHANGELOG.md` v2026-09-26.1; ROADMAP 7.7, 7.8.

### 2026-09-25 | theory-guard reads the session transcript for evidence; no new ledger hook | status: current
**Decided:** C5's Stop hook checks a code-shaped claim against the transcript it already receives
(`transcript_path`): the name ran in a non-search Bash command that did not error → pass; only
read, or never seen → block. `.claude/tools/probe.py` makes running a function one command.
**Over:** a PostToolUse hook appending every tool call to `.claude/.runtime/evidence.jsonl`
(proposed first, to the owner). The transcript already records every tool call and result, so
the ledger would have been a second copy that runs on every tool call, can drift from the
transcript, and adds latency — for no information the transcript lacks.
**Why:** C5 hit seen 13; the wording-only guard blocked verified claims and missed the one wrong
claim's shape. Replaying the day's transcript through the new guard blocked the wrong claim with
"read but never run" and passed the corrected one.
**By:** owner (build both), session `claude/bot-database-schema-qllz12` (transcript over ledger),
2026-09-25. **Detail:** `theory_guard.py` docstring; constraints C5 "Widened" note.

### 2026-09-25 | Message log hooks remember(), stays on the VPS, and a weekly audit judges it with fixed rules | status: current
**Decided:** every turn `remember()` records is also appended to
`<instance>/msglog/<chat_id>/<date>.jsonl` (default on, `MESSAGE_LOG=0` kill switch, 30-day
retention by filename date, admin `/msglog`). `tools/weekly_audit.py` runs from root's crontab on
Sundays and reports FLAG / OK / BASELINE / NOT CHECKED over `tools/rpzlib.py` metrics, with no model call.
**Over:** (a) logging at each send path (`_deliver`, `_group_deliver`, `send_triggered`): three
sites to keep in sync, where `remember()` is the one function all of them already call;
(b) the proactive-receipt pipe (journald → observer unit → jsonl): the text would also sit in
journald under journald's retention, so "gone after 30 days" would not be true; (c) the
suggestions written by a model: `rpzlib.py`'s thresholds have never been checked against real
bot output, so a model would present guesses as verdicts, and it would spend NanoGPT quota weekly.
**Why:** the owner wanted the fleet's output analyzable and audited, with 30-day retention and
the data kept on the VPS. The log sits in a subfolder because `vps-backup.sh` copies top-level
instance files only (pinned by a test that runs the real script). Threshold rules show values without
judging them until three weekly reports exist.
**By:** owner (log, `/msglog`, 30 days, VPS-only, weekly audit, rule set); session
`claude/bot-database-schema-qllz12` (hook point, storage layout, fixed rules over a model), 2026-09-25.
**Detail:** `telegram-companion-bot/MESSAGE_LOG_DESIGN.md`; CHANGELOG v2026-09-25.1.

### 2026-09-24 | Cloud sessions get the 3.12 deps from an async SessionStart hook via a symlinked venv | status: current
**Decided:** `.claude/hooks/session-deps.sh` runs async in cloud sessions, builds a venv from
`requirements.lock` + the CI pytest pin in a lock-keyed directory outside the repo, and switches the
`~/.venvs/sillytavernpresets-py312` symlink to it only when the install is complete.
**Over:** (a) synchronous, which was shipped first and is safe but makes every session start wait;
rejected by the owner in favour of faster startup; (b) async installing straight into the PATH
directory, rejected because `python3` would resolve to a half-built venv during the install.
**Why:** the default container Python is 3.11 with no bot packages, so `verify.sh` went red before
checking anything and sessions skipped it. Async plus the symlink swap means the first seconds run the
old 3.11 at worst, never a broken environment.
**By:** owner (async), session `claude/svipall-review-g3s2fy` (symlink design), 2026-09-24.
Confirmed live: a fresh session's `python3` is the venv's 3.12.3.
**Detail:** the hook's header comment; `skill-impact.md` 2026-09-24.

### 2026-09-24 | Reddit stays on Atom/RSS; no browser-based access, no Svipall | status: current
**Decided:** `idea-scraper-actor` keeps reading Reddit through `/r/{sub}/top.rss`; the NSFW flag,
sticky flag and scores lost with the JSON path stay lost.
**Over:** (a) Chrome TLS impersonation (`curl_cffi`, or Svipall's http tier); tested and it gets
the same `403`; (b) a full headless browser (Svipall's heavier tiers, or Playwright); not tried,
because it would deliberately work around a block Reddit put up on purpose, for fields nothing
here currently needs; (c) adopting `ilien-dev/svipall` generally; reviewed, and it fits
nothing the fleet runs.
**Why:** every endpoint tried that carries those fields is blocked without a login, and the Routines that
consumed the Actor are retired.
**By:** owner + session `claude/svipall-review-g3s2fy`, 2026-09-24 (evidence-backed).
**Detail:** `idea-scraper-actor/README.md` "Every other Reddit endpoint"; oplog 2026-09-24.

### 2026-09-23 | Hook and eval blocks are counted by a wrapper plus a debrief harvest | status: current
**Decided:** blocking hooks run through `.claude/hooks/count-block.sh`, and `run-evals.sh`'s
`bad()` writes a row per FAIL outside CI. Rows go to `.claude/.runtime/blocks.log` and are folded
into the committed `.claude/memory/mechanism-tally.tsv` by `mechanism-tally.py harvest` at
session-debrief. The `block-tally` eval pins the wrapper's exit-code passthrough.
**Over:** (a) editing each of the 12 hooks to write its own row — 12 copies of the same code
that drift apart; (b) writing straight into the committed file on every block — every blocked
turn would dirty the tree mid-task; (c) counting from the evidence log — a blocked tool call
never reaches the PostToolUse hook that writes it.
**Why:** the 2026-08-23 benchmark (mycelium) named "nothing checks whether a mechanism ever
fired" as the one real gap in the learning layer. The accepted cost: rows from a session that
never debriefs are lost, so counts are a floor. QUIET (no firing in 60 days) means "review",
never "delete" — a guard can work by being known about.

### 2026-09-22 | Pre-meta memories decay by their text date instead of staying exempt | status: current
**Decided:** a memory with no recorded `ts` but a leading `[auto YYYY-MM-DD]` is ranked by that
date for both recency decay and the time boost (`MEMORY_DATE_FALLBACK_DECAY`,
`MEMORY_DATE_FALLBACK`, both default on, v2026-09-22.2).
**Over:** (a) **keep them exempt from decay** (the rule since v2026-07-12.1, "legacy pre-meta
memories are never punished") and apply the date to the time boost only -- the session
recommended this, because decay changes which memories the character recalls; (b) **leave both
neutral** -- lost because a "remember when" question could never reach the earliest
relationship memories.
**Why:** the owner chose to treat old memories by their real age: an exemption that exists only
because of when the metadata file was introduced is an accident of history, not a design. The
separate decay switch keeps the riskier half reversible without a redeploy.
**By:** owner, 2026-09-22 ("build the time-boost fix ... and the decay one as well"), after a
live `/whymem` reading showed every injected line at `recency 1.00`.
**Detail:** `telegram-companion-bot/CHANGELOG.md` v2026-09-22.2.
Related: decisions 2026-09-22 (GraphRAG), watchlist 2026-09-22 (keyword crowding).

### 2026-09-22 | GraphRAG is not adopted for bot memory or the dev memory layer; only per-step retrieval visibility is copied | status: current
**Decided:** keep `triggered_memories()`'s flat hybrid scoring (keyword + semantic + BM25, summed,
then multiplied by recency, repeat, urgency and temporal terms, capped at `MEMORY_TOKEN_BUDGET`).
Add no knowledge graph. Copy one idea from the article, "log what each retrieval step
contributed", as ROADMAP 7.6 (`/whymem`).
**Over:** (a) **an LLM-extracted knowledge graph** (the base of all six patterns) -- lost because
every memory write would spend NanoGPT quota on entity/relation extraction, and would need a graph
database on the VPS, for a few thousand short lines per instance; (b) **Pattern 5, a router that
picks a retrieval path per message** -- lost because it adds an LLM call before every reply,
against the per-reply LLM-call budget in `bot-code-invariants`; (c) **Pattern 6, agentic
retrieval** -- lost because the article itself says it takes minutes and is not for real-time
chat; (d) **a sparse graph of key entities** (the article's cheap variant) -- already exists in the
form that fits: `people.txt` is about six lines per instance and is always injected, so there is
nothing to retrieve; (e) **graph retrieval over `.claude/memory/`** -- lost on the 2026-08-21
measurement (plain grep finds the right operational-log row 9 times in 10), and the optional
`Related:` field already links entries by hand.
**Why:** the article targets multi-hop and aggregation questions over large document corpora.
A companion bot's queries are single chat turns over one person's memory lines, where the
article's recommended pattern for mixed queries (Pattern 2, parallel hybrid) is what shipped in
ROADMAP 7.1-7.4. The one gap it names that applies here is Challenge 4: `triggered_memories()`
computes each score term and discards it, so a wrong or missing memory cannot be traced to the
term that caused it, and ROADMAP 7.3's done-when ("temporal boost visible in `/audit` or log
output") is unmet -- `grep -n -i 'temporal\|time_anchor' bot.py` shows no log or `/audit` use.
**By:** a session read the article (via Nimble extract; towardsdatascience.com is egress-blocked)
and compared it against `bot.py`; the owner confirmed "log the decision" 2026-09-22.
**Detail:** `telegram-companion-bot/ROADMAP.md` 7.6. Open, unmeasured: whether aliases ("my
sister" vs "Jen") are missed by the current scorers -- no recorded miss, and checking needs real
memory files from the VPS.
Related: decisions 2026-09-22 (MEX not adopted), mycelium 2026-08-21 (semantic search over the
oplog ruled out), ROADMAP Track 7 (SAGE/Mem0 rejected 2026-09-09).

### 2026-09-22 | MEX (mex-memory/mex) is not adopted as a memory layer; two of its ideas are copied by hand | status: current
**Decided:** do not install MEX (`mex-agent` 0.8.2). Copy two ideas into the existing memory
layer instead: an eval that checks code identifiers named in docs still exist, and a commit SHA
on mycelium entries so a reader can see what changed since the entry was written. Plan:
`.claude/memory/improvement-proposals/2026-09-mex-ideas.md`.
**Over:** (a) **full adoption** — lost because nearly every MEX feature already has a home here
(project notes / Wiki decisions -> `decisions.md`; Relays -> `mycelium.md`; Inbox -> `inbox.md`
+ `session-debrief`; path grounding -> `claude-md-refs-resolve` / `skill-refs-resolve`; Codex
support -> the harness-neutral mycelium rule in `CLAUDE.md`), and a parallel system beside those
plus Notion is the drift this repo keeps paying for (F2, `.claude/SCAFFOLDING-AUDIT-2026-07-30.md`);
(b) **the Code Graph only** (`mex graph scope`) — lost because its SQLite indexes are
never committed, so every ephemeral cloud session would need Node >=22.5 plus a rebuild over a
19,841-line `bot.py` before use, and its token-savings benchmark is 12 tasks run once each on one
model, with accuracy 7/12 vs 6/12, which is inside noise; the savings are on Claude's side, not the
NanoGPT quota; (c) **body-hash drift** (MEX flags a doc claim whenever the grounded function's body
changes) — lost because `bot.py` changes almost every session, so nearly every claim would be
flagged, and a check that noisy on day one gets switched off (the lesson recorded in the
`skill-refs-resolve` comment); only the decidable half, "the named identifier no longer exists",
is copied.
**Why:** MEX's review step lives in a Hub bound to `127.0.0.1` on the machine running it, and the
owner works from Android against cloud sessions, so the human-approval path it is built around is
not usable here. Other costs: telemetry is on by default (public repo), setup writes
`.claude/skills/mex-*` into files `skill-index-integrity` guards, and the tool is 0.8.x with a
handoff schema already on v4.
**By:** a session evaluated it (cloned 0.8.2, read README + `evaluate/RESULTS.md`, measured this
repo's doc identifiers: 115 identifier-shaped names in `CLAUDE.md` + skills, 13 absent from
`bot.py`, all 13 legitimately defined elsewhere, so zero drift today); the owner confirmed
"log the decision" 2026-09-22.
**Detail:** `.claude/memory/improvement-proposals/2026-09-mex-ideas.md`.
Related: mycelium 2026-08-21 (semantic search over the oplog ruled out), mycelium 2026-08-23
(literature scan, do not re-run).

### 2026-09-04 | Model context windows are measured against the live endpoint, never read from a spec | status: current
**Decided:** the served context window of any model this fleet uses is established by probing
the live NanoGPT endpoint (`probe-context.py`), and `FALLBACK_CONTEXT_BUDGET` is set from that
measurement.
**Over:** (a) the provider's own model listing — `/v1/models` exposes no context field at all;
(b) public aggregators (OpenRouter, Puter, hfviewer) — they disagree with each other and with
reality; (c) the base model's native window from its HuggingFace config — describes the
weights, not what the provider chose to serve; (d) leaving `FALLBACK_CONTEXT_BUDGET=0` and
letting oversize prompts fail — that is the `context_length_exceeded` bug the var exists for.
**Why:** measured `anthracite-org/magnum-v4-72b` at ~19,859 tokens. The published figures were
32,768 and 131,072 — wrong by 1.65x and 6.6x, both in the direction that ships prompts the
model rejects. A number that decides whether a prompt is accepted cannot come from a source
that is wrong this often, and every off-box source is egress-blocked from a Claude Code
session anyway (nano-gpt.com, huggingface.co, openrouter.ai all 403 or unreachable), so the
measurement has to run on the VPS.
**By:** a session, settled by running the probe against the live endpoint from the VPS and
recording the accept/reject boundary (accepted 19,859, rejected 20,375).
**Detail:** `telegram-companion-bot/probe-context.py`; `.env.example` FALLBACK_CONTEXT_BUDGET
block; commits 26facec, 8e74cc2, 157b447. Open: `Sao10K/L3.3-70B-Euryale-v2.3` is still
unmeasured (blocked by a 429 quota exhaustion), so the choice to stay on magnum is provisional
rather than a comparison won on merit.

### 2026-09-01 | The offline life becomes subordinate to relationship memory (read-ground, write-firewalled) | status: current
**Decided:** the offline-life generators (`_generate_life_event`, `_maybe_rotate_life_arc`) will
READ the owner chat's relationship memory (long-term `summaries` + durable `facts` + recent summary,
via `get_owner()`) for grounding, so the arc can no longer drift into contradicting threads the
relationship already resolved. Memory is the source of truth; the life defers to it. Behind a new
default-ON `LIFE_GROUNDING` kill switch. **Implemented and shipped v2026-09-01.1** (plan:
`telegram-companion-bot/PLAN-lifearc-memory-grounding.md`).
**Over:**
- *Rebuild/fix the memory system* — rejected: the VPS `state.json` dump proved memory is the
  strongest subsystem (174-word long-term summary + 15 accurate facts, promoting weekly). It isn't
  broken; the arc is.
- *Texture-only / kill the arc rotation* — rejected: owner wants grounded continuity, a followable
  personal storyline, not just disposable daily flavor.
- *Ground both directions (life writes into memory too)* — rejected: violates memory-provenance
  invariants #10/#17 (invented events becoming "things that happened with the user"). The existing
  `[own-day]` write firewall stays closed; grounding is READ-only.
- *Exclude NSFW specifics from the grounding block* — rejected (owner-surfaced): Emily is an NSFW
  companion whose intimate dynamic is her core emotional throughline; filtering it flattens her and
  re-creates the disconnect. The guard is content-neutral — provenance (don't re-narrate grounding as
  events) + domain (solo events stay in her own world), not an NSFW filter.
**Why:** the life arc was a closed generative loop isolated from memory, so it froze stale/wrong
threads (Warren "was it a test", "photo series") verbatim while the real relationship moved on and
resolved them — the arc *contradicted* her own memory. Grounding on the reliable store fixes the
class at its source; the firewall keeps provenance intact.
**Residual accepted (fifth fork, at implementation):** `/code-review` found that `life.txt` and
`life_events.txt` are injected into group and non-owner chats (no owner-gate, predating this change),
so grounding now feeds owner-private/intimate memory into generators whose output can reach a group —
guarded only by the prompt ("consistency context, do not restate") + solo-domain scoping. Owner chose
to **accept the risk** over gating the injection to the owner chat (would strip her offline-life texture
from groups) or dropping facts from grounding. Revisit by owner-gating `life.txt`/`life_events.txt`
injection if a leak is ever observed; `LIFE_GROUNDING=0` is the off-switch. (Two other review findings
were fixed, not accepted: order-sensitive near-dup, decorative-line own-day note.) Tracked in
`watchlist.md`.
**By:** owner (brianault327), interactively, 2026-09-01 — answered all five forks (grounding depth,
weekly cadence kept, near-duplicate dedup, no NSFW filter, accept the cross-chat injection residual).
**Detail:** `telegram-companion-bot/PLAN-lifearc-memory-grounding.md`; diagnosis in this session's
mycelium entry.

### 2026-08-31 | MECHANISM REVIEW surfaces recurrence by freshness, not presence | status: current
**Decided:** the `session-audit.sh` MECHANISM REVIEW startup line now names a guarded
constraint only when its newest `seen:` date is on/after the last debrief date — i.e. the
guard failed again and nobody has triaged it yet. Recurrences that predate the last debrief
(already reviewed) collapse to a one-number "already reviewed" line. C8 (last recurrence
2026-08-27, before the 2026-08-31 debrief) therefore drops off the loud line; it returns only
if it recurs again. The `mechanism-recurrence-surfaced` eval gained a fixture case (C84,
recurred-but-reviewed) that must NOT reach the loud line; break-tested red then green.
**Over:** (a) more prose against C8 — rejected: C8 is at seen 10 and has survived a hook
(`theory-guard`), a constraint, and an OPERATING_MANUAL rule; the owner-asked "fix" was not
another restatement. (b) a "prune guards with zero catches" meta-eval (the second half the
2026-08-23 mycelium finding named) — rejected as unsound: this repo has no catch-counter, and
a break-tested guard that never fires is working as designed (it prevents a rare disaster), so
"never fired" is not evidence it is dead. (c) leaving MECHANISM REVIEW as a presence list —
rejected: it named the same ~9 constraints every session, was at its own watchlist wallpaper
trigger, and a signal that never changes stops being read (C8's own shape).
**Why:** the one sound, in-scope lever on C8 was the meta-signal's quality, not its wording —
turn a permanent list into a delta that goes quiet until a guard actually fails again. Reuses
data already present (seen dates + the last-debrief date the hook already reads), so no new
state file.
**By:** a session, 2026-08-31, at owner request ("do what you think will actually fix it and
put it to bed"). Break-tested via the eval; full `run-evals.sh` exit 0.
**Detail:** hook block in `.claude/hooks/session-audit.sh` (the `last_debrief_date` /
`recurred_fresh` / `recurred_stale` split, rationale in-comment); eval C84 case in
`run-evals.sh`.

### 2026-08-29 | prompter concept adopted as a hook, not the skill; default-ON with PROMPTER kill switch | status: current
**Decided:** rebuild the `prompter` concept (github.com/Terryc21/prompter) as a
`UserPromptSubmit` hook, `.claude/hooks/prompt-rewrite.py`, wired in `settings.json` beside
`agent-authorization.py`. A deterministic regex gate (`should_rewrite`) decides *whether* to
nudge; the model does the rewrite. Ships **default-ON** with a `PROMPTER=0` kill switch, and no
per-session emit cap.
**Over:** (a) installing prompter's own SKILL.md as-is — rejected: a skill cannot intercept a
prompt (it is invoked mid-turn by the model's choice), so its "rewrite every prompt this
session / via CLAUDE.md" behavior is advisory, and the model just runs the task; the hook is the
only mechanism that fires before the model acts. (b) opt-in default (`PROMPTER=1` to enable) —
built first, then reversed by the owner: it reshapes the human's own prompt loop, so I defaulted
it off to avoid springing it on a session; owner chose default-ON, which also restores the
repo's standard kill-switch polarity (unset = active, `0` = off) instead of inverting it.
(c) a per-session emit cap like agent-authorization's `MAX_EMITS` — rejected: agent-auth caps
because CLAUDE.md carries its standing grant afterward, but each qualifying prompt needs its own
nudge about *that* prompt, so a cap would silently stop rewriting prompt N+1; cost is instead
held down by the tight gate + short body (F4 additionalContext-accumulation lesson).
**Why:** the mechanism, not the packaging, was the whole value — interception is a hook's job.
Default-ON matches repo policy (new features default ON with a mandatory switch) and the owner
ratified it.
**By:** a session, 2026-08-29, built at owner request; default-ON flip owner-settled. Gate
behavior break-tested red then green, pinned by the `prompt-rewrite-gate` eval (18 cases); full
suite exit 0.
**Detail:** commits 4b391dd (hook + eval) and d2ea508 (default-ON flip); hook docstring carries
the mechanism rationale.

### 2026-08-29 | bug-echo not adopted as a plugin; its one new idea folded into fix-the-class | status: current
**Decided:** do not install the external `bug-echo` skill (github.com/Terryc21/bug-echo); keep
`fix-the-class` as the repo's post-fix sweep and add bug-echo's one non-redundant idea to it —
validate a search pattern against the pre-fix source before trusting a *clean* sweep.
**Over:** (a) installing bug-echo as a standing Claude Code plugin — rejected: it is
functionally the same discipline as `fix-the-class` (which is already wired into CLAUDE.md's
working principles and the `the class` vocabulary term), and it is Swift/SwiftUI-shaped
(`**/*.swift` default, AST-grep Swift path, `#if os()` handling, >500-file sub-agent batching)
— all inert on a single-file Python bot, so it would add a redundant, mostly-dead skill to the
surface. (b) Ignoring it entirely — rejected: its self-validation step ("prove the pattern
matches the original bug before believing a zero-match result") was the one thing `fix-the-class`
genuinely lacked, and it closes a real false-all-clear gap.
**Why:** the value was one idea, not a tool; harvesting the idea keeps the surface small (the
repo's standing anti-bloat + `skill-index-integrity` posture) while capturing the gain.
**By:** a session, 2026-08-29 — verification: read the whole skill, traced its flagship mode
against our latest fix (the additive reasoning-leak guard, which it cannot seed from), confirmed
redundancy against `fix-the-class`.
**Detail:** commit b064813 (fix-the-class edit + `test_send_triggered_rerolls_leak_end_to_end`).

### 2026-08-25 | Decision log lives in its own durable file, not in mycelium | status: current
**Decided:** the consolidated decision log is `.claude/memory/decisions.md`, a system-of-record
file alongside `operational-log.md` and `constraints.md`.
**Over:** (a) appending decisions inside `mycelium.md` — rejected because mycelium is transient
by design (entries prune at 14/30 days, are append-only messages, and are counted by
`session-audit.sh`); a permanent log there fights every one of those mechanics and the
`mycelium-format` eval. (b) Using the Notion Fleet KB as the log — rejected because it is not
committed or greppable; the repo's own rule is that reviewed durable knowledge lives in
`.claude/memory/`, with Notion as the faster-moving uncommitted layer.
**Why:** a decision does not age out, so it needs a home whose contract is permanence, not
message-passing.
**By:** owner, 2026-08-25 (interactive), via AskUserQuestion.
**Detail:** —

### 2026-08-25 | Consolidate by cross-linking, not by merging the memory files | status: current
**Decided:** create the decision log and point the other decision-bearing files at it; do not
physically merge `CHANGELOG.md`, `operational-log.md`, `constraints.md`, `fable-to-opus.md`, or
the `AUDIT-*.md` files together.
**Over:** folding several of those files into one — rejected because each has a distinct,
eval-enforced job (`oplog-rows-are-index`, `skill-index-integrity`, the constraints
`seen`/graduation rules), and merging them would break those guards and blur purposes that the
memory layer deliberately keeps apart.
**Why:** the scatter to fix was *decision rationale with no single home*, not the existence of
several files each doing one thing well.
**By:** owner, 2026-08-25 (interactive), via AskUserQuestion.
**Detail:** —

### 2026-08-22 | Scheduled Routines retired; automation is hooks and evals only | status: current
**Decided:** all seven scheduled Routines are paused and the recurring work (improvement loop,
character pass, external idea scans) moved to ChatGPT.
**Over:** keeping the Routines running in this repo — rejected; the work is done elsewhere now.
**Why:** owner moved that workload off this system; keeping paused triggers "in sync" with a
live thing they no longer drive was pure maintenance cost.
**By:** owner, 2026-08-22.
**Detail:** `.claude/operating/routines.md` (now a historical record, not a live spec).

### 2026-08-21 | Not building semantic/vector search over the operational log | status: current
**Decided:** keep plain `grep` for operational-log retrieval; do not build embedding/vector or
BM25 search.
**Over:** (a) embeddings/vector search and (b) BM25 — both rejected on measured evidence: over
71 rows with queries and ground truth fixed before the run, plain grep found the right row 9
times in 10, leaving almost no recall headroom; BM25's gain came from smaller chunks, a lever
the `incidents/` split already pulled.
**Why:** the real cost was precision, not recall, and no retrieval algorithm addresses that at
this corpus size.
**By:** session `claude/reddit-post-review-3oe3rx`, 2026-08-21 (evidence-backed).
**Detail:** `.claude/experiments/2026-08-21-oplog-retrieval/RESULTS.md` (protocol frozen; the
embedding arm never ran — HuggingFace 403 through the proxy — so the claim is "lexical leaves
little headroom", not "embeddings would not help").

### (seed) bot.py stays a single file | status: current
**Decided:** `bot.py` is one file; do not split it into modules.
**Over:** splitting into a package — rejected because the whole selector/release/deploy model
depends on shipping one file.
**Why:** recorded non-goal; the deploy model is the constraint.
**By:** owner (standing).
**Detail:** `CLAUDE.md` → "Known-deliberate — do not 'fix' these".

### (seed) Emily runs glm-4.7:thinking, not glm-5 | status: superseded
**Decided:** the `emily` instance runs `zai-org/glm-4.7:thinking`.
**Over:** moving her to glm-5 with the rest — rejected; per-instance model choice is expected,
not drift.
**Why:** owner preference for that instance's voice.
**By:** owner-confirmed, 2026-07-25.
**Detail:** `CLAUDE.md` → "Known-deliberate".
**Superseded 2026-08-31 (owner):** retired from the decision log at owner request — this is a
log cleanup, NOT a config reversal. Emily still runs `zai-org/glm-4.7:thinking`. The live
"do not 'correct' it to glm-5" guard-rail lives in the `bot-config-reference` skill (its model
table + Common-mistakes list), which is where a session actually looks before touching an
instance's `.env`, so nothing about her config or its protection changes. The `CLAUDE.md` →
"Known-deliberate" pointer above is stale (that note was removed 2026-08-31); the skill
guard-rail is intact.

### 2026-08-31 | /update self-deploy permanently retired (unconditional, no re-enable) | status: current
**Decided:** `/update` and admin `/admin/update` are retired unconditionally — `perform_self_update`
returns `reason: "retired"` before any network/filesystem work, with no env flag to turn it back
on. `/admin/update` returns 410 Gone. Shipped v2026-08-31.2.
**Over:** three alternatives — (a) an env opt-in `LEGACY_SELF_UPDATE` (default off) re-enabling the
old in-place swap for emergencies; built and shipped as the unmerged v2026-08-31.1, then removed at
owner request; (b) a bare unconditional gate leaving the fetch/swap body as dead code — the
`/code-review` objection that first drove (a); (c) deleting the fetch/swap body outright — rejected
because it scatters the same vestige across an unused `_RAW_BOT_URL` and a host-wide lock that then
guards nothing.
**Why:** the repo going public (2026-08-31) re-armed the path — its raw fetch resolves again, so it
would SUCCEED at an in-place bot.py swap that bypasses the immutable-release/selector/locked-venv
deploy and is erased by the next `vps-sync.sh` hard-reset (silent divergence). Owner wants zero
re-enable capability, so no toggle. The now-unreachable body is retained as one commented, tested
block so the concurrency lock + reason-branch regression tests stay meaningful.
**By:** owner, 2026-08-31 ("zero re-enable capability").
**Detail:** `CHANGELOG.md` → v2026-08-31.2; `_perform_self_update_locked` / `update_cmd` in `bot.py`;
deploy stays `deploy/vps-sync.sh` per instance.

### 2026-08-31 | WikiSkill built as a standalone offline-testable project, not grafted into .claude/ | status: current
**Decided:** implemented WikiSkill (arXiv:2608.27454) as a new top-level `skillforge/` project —
a self-contained skill-evolution loop + skill-quality benchmark, stdlib-only core, runnable
offline with a deterministic MockLLM and against a real OpenAI-compatible endpoint. It never
reads or writes the `.claude/` memory layer.
**Over:** two alternatives the owner was shown — (a) analysis-doc only (map WikiSkill onto the
existing `.claude/` layer, build nothing); (b) graft WikiSkill's one genuinely-missing piece,
the `skill-impact.md` audit trail, directly into `.claude/memory/`. Owner chose the ambitious
path: "build the skill-quality benchmark first, then the full evolution loop."
**Why:** the finding is that `.claude/` already implements ~85% of WikiSkill by hand
(operational-log/constraints/decisions = wiki pattern pages; `.claude/skills/` + evals + CI =
the gated skill layer). The only real gap is the change→diff→did-it-work ledger. Building the
full loop *inside* `.claude/` would (1) duplicate live systems, (2) need a skill-quality
benchmark the repo doesn't have, and (3) risk a competing memory layer — all against the repo's
single-system norms. A separate project (the `voicekit-starter/` precedent) delivers the full
loop the owner asked for, offline-testable, without touching governed machinery. Whether to
later graft just the `skill-impact.md` ledger into `.claude/memory/` is left as a separate,
smaller decision.
**Honesty bound:** the offline demo proves the harness mechanics (gating, skills-only rollback,
never-rolled-back wiki, audit trail, early stop), NOT that "skill evolution works" — that claim
is the paper's and needs a real model via `skillforge evolve`.
**By:** owner (this session), 2026-08-31.
**Detail:** `skillforge/README.md`; `CLAUDE.md` → Repo layout; branch `claude/arxiv-2608-27454-build-b1epe6`.
