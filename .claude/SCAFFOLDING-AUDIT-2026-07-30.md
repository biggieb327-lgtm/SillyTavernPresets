# Scaffolding Ghost-Token Audit — 2026-07-30

Same lens as `telegram-companion-bot/GHOST-TOKEN-AUDIT-2026-07-30.md`, turned on the agent
system instead of the bot: **scaffolding loaded but never read, instructions repeated in
several places, context assembled and then ignored.**

**Bias disclosure.** This audits my own operating context, so "I ignored X" is self-report
and the weakest evidence in the file. Wherever possible the finding rests on structure
instead — a claim that is false on disk, an index that diverges from its source, a
selector that cannot prioritize. Findings are labelled `[structural]` or `[self-report]`.

## The always-loaded budget

Only this set is paid unconditionally. The 19-skill corpus (~24,000 tok on disk) is *not*
in it — skills genuinely load on demand, which is the correct architecture and the reason
this audit's numbers are small.

| Surface | est. tok | Cadence |
|---|---|---|
| `CLAUDE.md` | 3,080 | once per session |
| SessionStart hook output | 881 | once per session |
| 19 skill descriptions (frontmatter) | 1,120 | once per session |
| 11 agent descriptions (frontmatter) | 518 | once per session |
| **UserPromptSubmit hook output** | **224** | **every turn, accumulating** |

Session floor ≈ **5,599 tok**, plus 224 × turns.

---

## What is clean (checked, no action)

- **Skills load on demand and the router is honoured.** ~24k tok of skill bodies cost only
  1,120 tok of descriptions until something triggers. This is the single best decision in
  the scaffolding.
- **Agent descriptions are tight** — 518 tok for 11 agents.
- **Hooks are real, not advisory.** The delivery gate, eval gate, and budget governor all
  do work; none is a no-op stub.
- **`session-audit.sh` already knows the right principle** — it filters constraints to
  `seen: 2+` repeat offenders rather than dumping all 14. See Finding 3 for where it
  doesn't apply its own idea.

---

## Finding 1 — `skill-router` claims two skills are preloaded that are not `[structural]`

**Severity: high. Not a cost defect — a correctness defect that suppresses loading.**

`.claude/skills/skill-router/SKILL.md:6`:

> Load a skill only when its trigger fires. Preloaded always (do not re-load):
> `artifact-first-delivery`, `repo-validation-gate`.

Neither is preloaded. Their bodies appear in no auto-loaded surface — `grep -c "artifact"
CLAUDE.md` returns **0**, and neither is in the SessionStart output, the system prompt, or
any hook. Only their one-line frontmatter descriptions are present.

The instruction is worse than merely wrong, because it is an active *suppression*: a
session that trusts the router is told **not to load** the two skills the repo considers
universal. And `CLAUDE.md`'s own table contradicts it in the same breath — it lists
`repo-validation-gate` under "Before declaring anything done" as something to **Load**. The
two indexes disagree about the same skill.

`[self-report]` Observed outcome this session: neither skill was loaded, across two
delivered audits. I satisfied their content by other routes (CLAUDE.md's standing rules,
the eval suite), which is exactly why the defect is invisible — it degrades quietly into
"good enough," never into an error.

**Fix:** delete the "Preloaded always" sentence. One line.

## Finding 2 — `CLAUDE.md` ships a stale partial copy of the router index `[structural]`

**Severity: high.** `CLAUDE.md:200` states the architecture correctly —

> Detailed procedure lives in skills, not here. `.claude/skills/skill-router/SKILL.md`
> is the index — consult it and load on demand (table below for the common cases).

— and then ships a second, divergent index: 8 rows against the router's 16. Absent from
the always-loaded copy:

`grilling` · `fix-the-class` · `add-regression-eval` · **`verify-external-audit`** ·
`vps-migration` · `voicekit-work` · `unattended-loops`

**That omission has a cost I can demonstrate rather than assert.** The task immediately
preceding this one was *"look at this link and run an audit based on what you learn"* —
verbatim `verify-external-audit`'s trigger ("claims from an external source… a pasted list
of claimed defects"). The index loaded into every session has no row for it. I knew the
skill existed only because the harness lists all skill descriptions independently; had the
scaffolding been my only map, it would have routed me past it.

So the always-loaded copy costs ~200 tok/session and its only distinguishing property is
being incomplete in a way that misroutes.

**Fix:** replace the table with the pointer that already precedes it, or regenerate it as
the full 16 rows and add an eval asserting table↔router equality. The pointer is cheaper
and cannot drift.

## Finding 3 — 75% of the SessionStart injection is chosen by recency, not relevance `[structural]`

**Severity: medium.**

`session-audit.sh:7` selects the operational-log entry with `grep -m1 '^| 20'` — the log is
newest-first, so this is "whatever happened most recently," untruncated:

| SessionStart line | tok | share |
|---|---|---|
| **last operational-log entry** | **661** | **75%** |
| REPEAT MISTAKES (C1…C14 names) | 124 | 14% |
| standing rules | 58 | 7% |
| branch / dirty state | 18 | 2% |
| constraints count | 17 | 2% |

The 661-token row injected into this session was the 2026-07-29 Routine-prompts incident —
six dense columns about MCP tool availability in fired triggers. `[self-report]` It had no
bearing on either task and I did not use it.

The sharp version of this finding is that **the script already contains the correct
principle and applies it to the wrong line.** Its own comment on the constraints block:

> Constraints are only worth keeping if they are read BEFORE the same mistake recurs.
> Surface the repeat offenders (seen: 2+) by name — those are the ones prose has already
> failed to prevent at least once.

That is relevance-filtering, and it produced the 124-token line I actually used (I invoked
C13, C8 and C14 by name today). The 661-token line got no filter at all. A log row earns
its place by being *about what this session is doing*, and recency is not a proxy for that.

**Fix:** inject the row's first column (date + headline, ~30 tok) and a pointer, not the
whole row. The full log is one `Read` away when it's relevant — which is the same bet the
skill architecture already makes successfully.

## Finding 4 — the per-turn hook re-injects 224 identical tokens and they accumulate `[structural]`

**Severity: medium.** `agent-authorization.py` fires on `UserPromptSubmit` — every turn —
and emits a byte-identical standing-authorization paragraph. Directly observable: both
turns of this session carry the same copy, so by turn *N* the context holds *N* copies.

- 10-turn session: ~2,240 tok
- 40-turn session: **~8,960 tok — roughly 3× the entire `CLAUDE.md`**

This is the purest ghost token in the scaffolding: invariant text, re-billed per turn,
carrying no new information after its first appearance. It is also the closest analogue to
the bot audit's Finding 3, with the roles reversed — there the static block was stranded
where a cache couldn't reach it; here it is *duplicated* rather than referenced.

Its content is a standing *permission*, load-bearing only at a delegation decision — a
small minority of turns. Nothing about it varies with the prompt, so a hook is the wrong
mechanism for it.

**Fix:** move the paragraph into `CLAUDE.md` (paid once) and either delete the hook or
reduce it to a one-line reminder. If it must stay per-turn, compress it to a single
sentence: the second paragraph's "judgment still applies" caveat restates guidance already
in `CLAUDE.md`'s working principles and the budget-governor's own behavior.

## Finding 5 — `grill-me` is a dead skill advertised as live `[structural]`

**Severity: low.** `.claude/skills/grill-me/SKILL.md` (147 bytes) sets
`disable-model-invocation: true` and does not appear in the harness's available-skills
list — it cannot be invoked. `skill-router:10` advertises it: ``grilling`` (alias:
``grill-me``). The alias resolves to nothing.

**Fix:** drop the alias from the router, or delete the file. Note the router's own closing
rule — "New skills added under `.claude/skills/` must be registered in this table in the
same change, or they're invisible tomorrow" — guards the *missing*-from-table direction
only. This is the opposite failure: in the table, missing from reality.

---

## A note on what this audit deliberately did not claim

`run-evals` is mentioned in 15 scaffolding files, `BOT_VERSION` in 12. That is **not**
duplication worth cutting, and reporting it as such would have been the C14 mistake
(a scanner cannot tell "does the bad thing" from "legitimately reinforces it"). Skills load
on demand, so a session pays for at most the one or two it opens; a skill reminding you to
run evals *in its own context* is reinforcement working as designed. Repetition only costs
when it lands inside the always-loaded set — which is why Findings 1–4 are all in that set
and this paragraph is not a finding.

## Ranked recommendations

| # | Action | File | Cost | Risk |
|---|---|---|---|---|
| 1 | Delete the false "Preloaded always" sentence | `skill-router/SKILL.md:6` | 1 line | none |
| 2 | Replace `CLAUDE.md`'s table with its own pointer (or regenerate + add equality eval) | `CLAUDE.md:202-212` | small | none |
| 3 | Inject log headline + pointer, not the full row | `session-audit.sh:7` | small | none |
| 4 | Move standing-authorization into `CLAUDE.md`; drop or shrink the per-turn hook | `agent-authorization.py` | small | low — changes delegation prompting |
| 5 | Drop the `grill-me` alias or the file | `skill-router/SKILL.md:10` | 1 line | none |

Items 1, 2 and 5 are one-line edits to files that are actively misleading future sessions,
including mine. Nothing here has been applied — findings only.

Recurring shape across all five: **every one is an index or injection that describes the
system inaccurately, not a file that is too big.** The scaffolding's size is fine. Its
self-description has drifted from itself, and drifted specifically in the always-loaded
layer, where nothing on-demand can correct it.
