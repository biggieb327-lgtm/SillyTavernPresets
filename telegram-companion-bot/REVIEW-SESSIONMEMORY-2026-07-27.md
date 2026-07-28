# External review — Shared Session Memory Protocol (2026-07-27)

Reviewed at owner request:
https://github.com/Milanprobe/Shared-Session-Memory-Protocol-Codex-Claude_Code-main

## What it is

A **tool-agnostic template** for coordinating AI *coding-agent* sessions — specifically
Codex ↔ Claude Code handoff — so that work survives across sessions and across tools.
It is documentation and JSON schema only: no runtime code, no hooks that execute, no
recorded receipts. There is nothing to install.

Its unit of memory is an **immutable receipt**: one JSON file written per finished
session, append-only, into `session-memory/receipts/<spec-id>/`. Required fields
(`receipt.schema.json`, `receipt_version: 1`):

- identity — `receipt_id`, `spec_id`, `producer`, `created_at`, `mode`, `objective`
- git context — `branch`, `head`, `commit` (7–40 hex)
- `result` — `COMPLETE` / `PARTIAL` / `BLOCKED` / `NOOP`
- `acceptance[]` — each criterion with `PASS` / `OPEN` / `FAIL` / `NOT_APPLICABLE`
- `evidence[]` — indexed statements, each with a `ref` into a repo artifact
- `artifacts[]` — `{kind, path}` links (never inlined content)
- `open_findings`, `blockers`, `supersedes`, `related_receipts`
- optional `mechanism_matrix`, `review_findings`

Session entry is a **bounded context load**: read the one active spec, read
`index.json`, read the latest receipt for that `spec_id`, read only the receipts that
receipt explicitly links, then take the first `OPEN` criterion by the spec's priority
selector. Historical receipts are not read by default. `index.json` is a lookup cache
and must be derivable from the receipts.

## Category note, stated up front

The owner's question was whether this could improve **bot memory**. It cannot, directly:
the protocol governs how *development agents* remember work across sessions, not how a
companion character remembers a user. Different layer, different failure mode. The layer
it speaks to is `.claude/`.

And on measurable substance, `bot.py`'s memory system is **ahead of** anything in this
protocol. It has semantic recall over embeddings, dedup by cosine similarity, per-line
confidence with quote grounding, an origin/source provenance sidecar
(`memory_meta.json`), recency decay, repeat-injection suppression, a weekly
contradiction audit, and an owner-approval queue. The protocol has none of these — its
"memory" is a filing convention. Nothing in it should be ported into `bot.py`.

## What we already have (no action)

| Their protocol | Our equivalent | Evidence |
|---|---|---|
| Immutable append-only receipts | `.claude/memory/operational-log.md` (one row per system failure) + `constraints.md` (one entry per *our* mistake, with `seen:` counts) | both files |
| Memory injection at session start | `.claude/hooks/session-audit.sh`, a `SessionStart` hook — it fired at the top of this session with the last log row and 5 repeat constraints | hook output |
| Bounded / token-efficient context load | `skill-router` + the standing "do not load unrelated skills" rule | `CLAUDE.md` |
| Evidence artifacts linked, not inlined | `.claude/hooks/evidence-log.sh` — one line per tool call to a per-day log, read by the delivery gate | hook |
| Handoff prompt for the next session | `.claude/hooks/handoff-writer.sh`, a `PreCompact` hook writing git state + diffstat + evidence tail | hook |
| `MODE=REVIEW` for external claims | `verify-external-audit` skill + `AUDIT-2026-07-10.md`'s rejected-claims registry | skill |
| One active spec + priority selector | `ROADMAP.md` Track 4 → `IMPROVEMENTS_PLAN.md` release-by-release specs | docs |
| `result: BLOCKED` / `blockers[]` | operational-log `Next` column | log |

The important asymmetry: **theirs is advisory, ours is enforced.** Their `AGENTS.md`
says hooks "should not rewrite specs" and receipts "must remain immutable" — with
nothing checking. Ours has a Stop hook that blocks the turn when `bot.py` changed
without a `BOT_VERSION` bump, an eval suite pinning past incidents, and CI on `main`.
A protocol with no enforcement is a style guide.

Their `constraints.md` equivalent does not exist at all. The protocol records what the
*work* did; it has no channel for what the *agent* got wrong. That is the more valuable
of our two memory files and the one they are missing.

## Adopted

### 1. `evidence_kind` — tag each claim by how it was learned — HIGH value, S effort

Their `evidence[]` entries carry an `evidence_kind` enum: `RUNTIME_OBSERVATION`,
`CODE_FACT`, `EXTERNAL_CONTRACT`, `DESIGN_DECISION`, `HYPOTHESIS`. This is the sharpest
idea in the repo and it lands precisely on a failure we have twice:

- **C5** — *label a theory as a theory until evidence arrives* (asserted `watchdog.sh`
  ran from cron, mid-incident, as fact)
- **C8**, `seen: 3` — *ask what a reading actually measures* (a stale `/audit` line, a
  grep for the wrong variable, a historical log read as live)

Both graduated to **prose**, because no hook or scanner can see "trusted a reading that
did not mean what it appeared to." A required tag is the mechanism prose couldn't be:
it does not detect the error, it makes the distinction impossible to omit silently.

**Shipped:** an evidence-tag table in `operational-log.md`, adapted to five tags
(`[observed]` / `[code]` / `[external]` / `[decision]` / `[hypothesis]`) with a column
for *how each ages* — an addition of ours, since C8's three failures were all about a
claim whose shelf life had expired. Applied to the new row; the 29 prior rows are
deliberately **not** retro-tagged, since reconstructing provenance from memory is the
exact error the tags prevent.

### 2. Splitting `verdict` from `disposition` — HIGH value, S effort

They keep two independent fields on every external finding: `verdict` (`CONFIRMED` /
`FALSE_POSITIVE` / `STALE` / `NOT_REPRODUCED` / `NOT_APPLICABLE`) and `disposition`
(`OPEN` / `FIXED` / `NO_ACTION`).

Our `verify-external-audit` collapsed these into one five-way label, and one of those
labels — `REAL BUT REJECTED` — welded a truth-claim to a policy decision. Once written
you could no longer ask the two questions separately, so when a recorded decision was
later reversed, nothing could answer *"which past findings were true but closed under
the old rule?"*

That is not hypothetical. It is the mechanism behind this session's own bug fix (below).

Also worth having: `STALE` (true when written, fixed since) and `NOT_REPRODUCED`
(couldn't settle it here) are distinctions our single `FALSE` could not express — and
conflating "you were wrong" with "I couldn't check" is how a real finding gets dropped.

**Shipped:** `verify-external-audit` step 2 rewritten to two fields;
`REAL BUT REJECTED` → `CONFIRMED` + `NO_ACTION` with a required citation of the closing
decision; checklist and report-back format updated.

### 3. What reading it prompted — v2026-07-27.1, and a correction

Their case for auditing memory against ground truth sent me to check ours. All three
memory-hygiene loops (`MEMORY_AUDIT`, `MEMORY_DECAY_HALFLIFE_DAYS`, `MEMORY_HEDGE`)
shipped default-OFF in v2026-07-12.3 under the convention in force at the time;
v2026-07-18.1 reversed that convention to default-ON-with-kill-switch and nothing swept
backwards. v2026-07-27.1 aligns the defaults.

**Correction (2026-07-28).** This section originally claimed the defenses were "inert"
on the live fleet. That was false, and the manner of the error is worth recording *here*
of all places. All six `.env` files set all three variables explicitly; the fleet was
never unprotected, and the release is a live no-op whose real value is what a newly
provisioned instance inherits.

The claim was an inference from bot.py's defaults plus a commented-out `.env.example` —
neither of which says anything about a live `.env` — and it was shipped to `main`,
CI-green, having been correctly labelled `[hypothesis]` at every step. Which is the
sharpest possible demonstration of the limit of idea #1 above: **a tag records how well
a claim is supported; it does not stop the claim being load-bearing.** The protocol this
document reviews has the same gap — `evidence_kind: HYPOTHESIS` is a field on a receipt,
and nothing in the schema prevents a `PASS` in `acceptance[]` from resting on one.

Recorded as constraints **C9** (verify a load-bearing hypothesis before shipping, not
after), with the concrete precondition written into ROADMAP 4.5, whose premise rests on
the identical reasoning.

## Rejected

| Idea | Why not |
|---|---|
| Per-session JSON receipts against a strict schema | Ceremony for a benefit we already get. `session-audit.sh` injects the same continuity at session start with zero authoring cost, and the operational log already carries the durable half. Receipts would add a write step to every session to re-encode what two hooks produce automatically. |
| `index.json` as a rebuildable receipt cache | Nothing to index. Our log is one file, read whole, and read by humans. |
| Nested per-subtree `AGENTS.md` | `bot.py` is one file by recorded non-goal — there are no subtrees to scope. |
| Two-producer alternation (Codex ↔ Claude) | The premise of the whole protocol, and we run one tool. Everything built to support alternation (`producer`, receipt-before-select, handoff prompts) is cost with no return here. |
| `mechanism_matrix` | Its enum is `dom_structured` / `text_ai` / `vision` / `dino_sam` — leftover from the author's own web-scraping project. Meaningless here. |
| `supersedes` on bot memories | Tempting by analogy — a memory that replaces another could link to it. Rejected: recalled memories are ranked against a token budget, so carrying tombstones spends the budget on text the character must never say. `memory_log.txt` already keeps the audit trail off the injection path. |

## Quality assessment of the source

Mixed, and worth recording since the owner is likely to be sent more of these.

**Good:** the `evidence_kind` and `verdict`/`disposition` enums are genuinely
well-designed — they encode real distinctions that most workflow docs slur. The
"receipt is not complete until it is written down; a finding in chat is not a handoff"
principle is correct and well argued. Artifacts linked rather than inlined is right.

**Weak:** it is a template that has never been run. There are no example receipts from
real sessions, `index.json` is empty scaffolding, and the "hooks" are described rather
than implemented. `mechanism_matrix` proves the genericization was incomplete — the
author's original domain leaks straight through an enum that is supposed to be
tool-agnostic. The repository also has its own source zip committed inside itself
(`Shared-Session-Memory-Protocol-Codex-Claude_Code-main/` nested in the repo root, with
`README.md` and `ARCHITECTURE.md` duplicated at both levels), which is why direct file
paths 404 — a sloppiness that undercuts a document about rigorous record-keeping.

**Verdict:** take the two enums, leave the artifact. Nothing here needs to be a
dependency, and nothing here should reach `bot.py`.
