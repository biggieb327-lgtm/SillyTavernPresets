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
- Newest first, same as the operational log and mycelium.

---

## Entries

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
