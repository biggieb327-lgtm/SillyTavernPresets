# Skill-Impact — did the intervention hold?

The closed loop the memory layer was missing. When we change the operating machinery — a
guard, a skill, a hook, an eval, a preset, an agent — **to stop a specific recurring
failure**, this file records the one thing no other file does: **did that change actually
stop it, or did the failure come back?**

The idea is lifted from WikiSkill's `skill-impact.md` (arXiv:2608.27454; the standalone
`skillforge/` project implements the full loop). Here it is a hand-kept ledger, not an
automated tracker.

## The test — which file does this belong in?

Ask in this order; the first yes wins:

| If… | it goes to |
|---|---|
| the **system** just failed — a bot, a deploy, the fleet | `operational-log.md` (one row per failure) |
| the **work** went wrong — our wrong command, premature "done", theory-as-fact | `constraints.md` |
| a **choice among alternatives** was settled — what won, what over, why | `decisions.md` |
| a **message to the next session** — heads-up, dead end, handoff | `mycelium.md` |
| it **hasn't happened yet**, it just might | `watchlist.md` |
| **we shipped a change to stop a failure class, and now we track whether it held** | **here** |

The line against the operational log is the sharp one. The oplog row for a fix looks
**backward**: what broke, the root cause, the patch. A skill-impact row looks **forward**:
across the sessions *after* the patch, did the class recur? The verdict "the
`v2026-08-25.1` widened guard did not work — it leaked again two days later" is a
cross-incident judgement that has no home in any single oplog row. That verdict is this
file's whole job.

An intervention earns a row only when it **targets a named failure class** — something that
has recurred, or that a guard/eval now exists to prevent. A routine feature or refactor with
no failure behind it is not an intervention; it does not go here.

## Every row ends in a verdict, or names what would settle it

- **`pending`** — shipped, but not enough time / evidence yet to say it held. The row MUST
  state its **holds-when** condition (the observation that would flip it to `holding`) and,
  where knowable, what a recurrence would look like. A `pending` row with no holds-when is
  an opinion.
- **`holding`** — the class has not recurred since, across a real observation window. Say
  what the window was.
- **`recurred`** — it came back. Link the recurrence (an oplog row) and the **next**
  intervention (a new row), so the chain stays followable. `recurred` is terminal for its
  own row; the follow-up lives in its own.

`session-audit.sh` prints the **`pending`** count at startup — those are the interventions
whose efficacy is still unconfirmed, the ones a new session should check against fresh
evidence before trusting. Settled rows (`holding`, `recurred`) are not nagged.

## Lifecycle

- **Written / updated at `session-debrief`.** A session that ships a class-targeting change
  adds a `pending` row; a session that observes a prior `pending` intervention hold or fail
  flips it to `holding` / `recurred` (and, on recurrence, opens the next row).
- **Never the only copy of anything.** The failure and its fix live in the operational log;
  this file holds the efficacy verdict and points back. Same rule as a mycelium dead end.

## Entry format

```
### YYYY-MM-DD | intervention: <short + version/commit> | class: <failure class> | status: pending
One or two sentences: what changed and why it should stop the class.
**Holds when:** the observation that would flip this to `holding` (for a pending row) — or,
for a settled row, what the window was / where it recurred and the next row.
Refs: oplog YYYY-MM-DD, changelog vX, constraint CN — wherever the failure and fix live.
```

`status: pending` | `holding` | `recurred`. The header shape is what `session-audit.sh`
counts and the `skill-impact-format` eval enforces — keep it exact. Newest first.

---

## Rows

### 2026-09-04 | intervention: `probe-context.py` + "measure, don't look up" in `.env.example` | class: external-system limits adopted as fact without measurement (C5's uncovered half) | status: pending
The failure this targets is not a wrong belief but an *unmeasurable-feeling* question: what
context window a provider actually serves. Every readable source was wrong or absent —
NanoGPT's `/v1/models` carries no context field, and public aggregators put
`magnum-v4-72b` at 32,768 and 131,072 while the live endpoint serves ~19,859. Prose telling
a session to "verify first" does not help when verifying looks impossible; so the
intervention makes measuring cheaper than guessing (one command) and rewrites the
`.env.example` guidance from a *guessed* worked example ("for a 16k model use 12000") into
the measured number plus the command that reproduces it.
**Holds when:** a later session facing a model/window question runs the probe (or cites a
measured figure) instead of quoting a spec sheet — and no `FALLBACK_CONTEXT_BUDGET` is ever
set from an aggregator number again. **Recurrence shape to expect:** a session reads the
now-measured 19,859 in `.env.example` and treats it as permanent after the provider silently
moves the window; the file says to re-probe on any `FALLBACK_MODEL` change, but nothing
enforces it. Second residual: the probe's own cost discipline (ramp up, `--budget`) is
prose-in-code, so a future tool that spends a shared quota gets no help from this row.
Refs: oplog 2026-09-04 (weekly-quota fallback storm); constraints C5 (seen 9, both
2026-09-04 occurrences); commits 26facec, 8e74cc2, 157b447.

### 2026-08-27 | intervention: v2026-08-27.1 structural short-circuit in `_looks_like_reasoning_leak` | class: reasoning-leak (model deliberation delivered as the reply) | status: pending
Replaced vocabulary-matching with a structural rule: ≥4 line-anchored markdown bold-colon
headers (`**Goal:**`, `1. **State:**`) over a 600-char floor → re-roll, whatever words fill
the outline. Vocabulary- and name-independent, so it should catch a *novel* self-invented
scaffold — the exact thing every prior guard missed. Env floors are the redeploy-free lever;
`leak_guard=False` paths (doc analysis) stay exempt.
**Holds when:** no reasoning-leak recurrence across a fleet-wide window after deploy (watch
`/errors` for `[reasoning-leak]` counts). Known residual → recurrence shape to expect: a leak
whose headers all wrap across lines (rare) still evades. Separately open and NOT closable by
this guard: the *cure* is a model-family decision — every thinking model tried (glm-4.7/5/5.1
`:thinking`) leaks — raised with the owner, not made.
Refs: oplog 2026-08-27; changelog v2026-08-27.1; `TestReasoningLeakGuard` (`OUTLINE_LEAK`).

### 2026-08-25 | intervention: v2026-08-25.1 widened `_REASONING_MARKERS` with preset planning vocabulary | class: reasoning-leak | status: recurred
Added the preset's private-planning labels (`epistemic check`, `rule priority`, …) as a
marker category to lift Emily's `[STEPPED THINKING]` leak over the 3-category floor.
**Recurred 2026-08-27** (leak #3): a self-invented scaffold sharing almost no vocabulary with
the preset scored 1 category and was delivered. Lesson the ledger exists to make loud —
chasing scaffold *vocabulary* is unwinnable against a thinking model that invents a fresh
outline each time. Superseded by the structural guard (row above, 2026-08-27).
Refs: oplog 2026-08-25 and 2026-08-27; changelog v2026-08-25.1.

### 2026-08-03 | intervention: v2026-08-03.1 `_looks_like_reasoning_leak` (≥2000 chars + ≥3 marker categories) | class: reasoning-leak | status: recurred
First general guard for plain-prose chain-of-thought delivered as the reply (Priya).
**Recurred 2026-08-25** (Emily): a cleaner render named the real user and headed its steps
"Drafting"/"Final Polish", evading enough markers to score 2 — one short of the floor.
Superseded by v2026-08-25.1 (which itself later recurred). Refs: oplog 2026-08-03 and
2026-08-25; changelog v2026-08-03.1.

### 2026-07-29 | intervention: v2026-07-29.1 `_strip_directive_lines` (ALL-CAPS bracket labels) | class: reasoning/directive leak (planning rendered as `[TAG: value]`) | status: recurred
First guard in this class: strip whole lines that are only an ALL-CAPS bracketed label,
after the named-tag strip (Jules's selfie caption leaked `[ATTRACTION RULE]:` etc.).
**Recurred 2026-08-03** in a different shape — plain-prose deliberation with no brackets —
which this line-shape guard cannot see. Shape-specific by construction; augmented by the
marker-based guard v2026-08-03.1. Refs: oplog 2026-07-29 and 2026-08-03; changelog v2026-07-29.1.
