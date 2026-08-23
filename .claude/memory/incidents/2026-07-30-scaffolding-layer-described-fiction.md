# 2026-07-30 — scaffolding layer described fiction

Archived from `.claude/memory/operational-log.md` on 2026-08-21, verbatim. The row
there is the index entry; this is the full record, including every correction
appended after the fact.

## Failure

**The always-loaded scaffolding layer was describing a system that didn't exist, and it suppressed the two skills that apply most often.** `skill-router` told every session that `artifact-first-delivery` and `repo-validation-gate` were already in context and must not be re-loaded; `CLAUDE.md` carried a divergent 8-row copy of the 16-row routing table; `grill-me` was advertised as a live alias for an uninvocable stub. Separately, the `UserPromptSubmit` hook was billing O(turns) for invariant text. No symptom — every session quietly routed slightly worse than it could

## Root cause

`[code]` `grep -c "artifact" CLAUDE.md` → **0**; neither skill's body is in `CLAUDE.md`, the SessionStart output, or any hook, so "already in context" was false and the two skills were also *omitted from the router table* because of it — one false sentence removed them from the index entirely. `[code]` `CLAUDE.md`'s copy omitted seven skills including `verify-external-audit`, whose trigger the same day's external-link audit matched verbatim — an always-loaded index that misroutes. `[code]` `grill-me/SKILL.md` sets `disable-model-invocation: true` and is absent from the harness skill list. `[observed]` hook `additionalContext` **accumulates**: both turns of the auditing session carried byte-identical copies, so turn N holds N copies — 224 tok × N, ~8,960 in a 40-turn session, ~3× all of `CLAUDE.md`. `[code]` the hook's own docstring rebuts the obvious fix: its position *later in the conversation than a server-side injection* is the mechanism, "which a CLAUDE.md line cannot do"

## System patch

Deleted the false exemption and added both skills as ordinary rows; deleted `CLAUDE.md`'s table in favour of the pointer that already preceded it plus the two composition facts per-skill descriptions can't express; deleted `grill-me/`. Hook rebuilt in two layers: the grant became `CLAUDE.md` working principle 8 (paid once, so the hook is no longer load-bearing for the permission's existence — that is what makes silence safe), and the hook now fires only on **breadth-or-multipart prompts that name no agent**, the one case where the injection bites and the grant flips the decision, at 74 tok, capped `MAX_EMITS=3`. Cost O(turns) → **O(1)**: ≤262 tok at any session length

## Eval

New eval **`skill-index-integrity`** — both directions (skill on disk missing from the table; table row naming a nonexistent or `disable-model-invocation` skill) plus rejection of any future "already in context" exemption. Break-tested RED on all four modes independently, green when clean. Scoped to the last cell of table rows because the router now explains the `grill-me` incident by name (**C14 — the eval's first version went red on my own explanatory prose in a clean tree**). Gate unit-tested 12/12; `AGENT_AUTHORIZATION=0`/`=always` and malformed stdin all verified. 29 evals pass, 0 fail

## Next

**Finding 3 of the audit is left open by choice:** 661 of the 881-token SessionStart injection is one operational-log row chosen by recency (`grep -m1`), untruncated — 75% of the budget on the least task-relevant part, while the same script relevance-filters the constraints line to `seen: 2+`. Fixing it changes what every future session is handed at startup, so it is an owner call, not a false statement to delete. Also unresolved in principle: **nothing detects `CLAUDE.md`↔`skill-router` divergence** — deleting the copy removed today's instance, but a future session re-adding a "quick reference" table would not trip any check

