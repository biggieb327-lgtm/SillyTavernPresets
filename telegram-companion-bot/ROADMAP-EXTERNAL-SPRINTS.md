# External Research Sprints — roadmap amendment

Reconstructed 2026-08-15 from the surviving project/conversation context after the original local-only commit `964aba2` was lost before reaching GitHub. This document preserves the recovered intent rather than claiming byte-for-byte recovery of the missing diff.

The amendment turns the strongest external-research ideas into four ordered implementation sprints, adds a new Track 7 for companion-quality and memory evaluation, and sharpens ROADMAP 5.1 and 6.2 around proactive-message quality and nightly receipts. It is documentation-only: no bot behavior changes here.

## Operating rules

- One sprint at a time. Later sprints may be designed while an earlier sprint runs, but they do not ship around an unmet exit gate.
- Every behavior-changing item starts on one instance behind a kill switch unless the canonical roadmap already gives a narrower rule.
- Reuse existing choke points and nightly/off-loop machinery before introducing new live-path LLM calls.
- Own-baseline evaluation beats cross-character comparison. A character is compared with itself before/after the change.
- A quality metric must be able to reject a change. “We built it” is never an exit gate.
- Any new memory mutation remains reviewable and provenance-preserving; contested facts are not silently resolved by model confidence.

---

# Sprint 1 — Proactive quality before proactive volume

**Goal:** make proactive behavior easier to judge before centralizing or increasing it.

**Why first:** ROADMAP 5.1 proposes a shared proactive-message triage queue, but the current done-when focuses on reproducing collisions/silent days rather than proving the messages selected by a queue are actually worth sending. Centralizing poor candidates would make the wrong behavior more consistent, not better.

## Status (2026-09-04)

| Deliverable | State |
|---|---|
| Fixed quality corpus (`evals/proactive_quality_corpus.json`) | ✅ on main |
| Receipt contract + writer (`PROACTIVE-RECEIPTS.md`, `proactive_receipts.py`) | ✅ on main |
| Emily journal observer + systemd soak path | ✅ on main (pilot) |
| Offline collision-window analysis | ✅ on main |
| `/nudges` skip-reason inspectability (5.11-B) | ✅ shipped; receipts listed as of v2026-09-04.2 |
| In-bot receipts at existing decision points (health + memory provenance + collision ids) | ✅ v2026-09-04.2 (`PROACTIVE_RECEIPTS`, default on, fail-soft) |
| Shared triage queue / ranking behavior | ❌ **out of scope for Sprint 1** — observe first; do not land queue changes under this sprint |

Note: a separately shipped Track 5-B triage feature may already exist on main from other work. Sprint 1 still does not authorize *new* triage/ranking changes; its exit gate is inspectability and the quality corpus, not queue promotion.

## Scope

1. Add a small proactive-message evaluation corpus covering the current candidate classes: reminder, health signal, memory/topic hook, day/life event, and ordinary silence-break/check-in.
2. Grade candidates on four dimensions that matter to a companion bot:
   - **timing:** is this a good moment to interrupt?
   - **specificity:** does it connect to something real rather than generic “checking in” filler?
   - **novelty:** is it meaningfully different from recent proactive sends?
   - **pressure:** can the user ignore it without the message sounding needy, managerial, or guilt-inducing?
3. Instrument the existing proactive paths enough to produce a receipt for each candidate: source, candidate score/gates, sent vs skipped, and skip reason. This is observability, not a new generation call.
4. Amend 5.1’s design so the future shared queue ranks **quality-qualified candidates**, not every raw trigger that happens to fire.

## Dependency

- Existing proactive send paths and `unsent_drafts`/nudge budget behavior.
- No dependency on Sprint 2 or Track 7 implementation.

## Exit gate

- A fixed corpus exists and can distinguish clearly good, clearly bad, and collision-prone proactive candidates.
- At least one live instance produces inspectable candidate receipts for a soak period without changing send behavior.
- The 5.1 design identifies which current gates remain hard vetoes (quiet hours, safety, explicit limits) and which become ranking signals.
- No implementation of the shared queue starts until the owner can inspect *why* a message won or lost.

## ROADMAP 5.1 amendment — Shared proactive-message triage queue

Keep the existing 5.1 premise, but change the target from “one shared urgency score” to a two-stage decision:

1. **Eligibility/quality gate:** reject candidates that are mistimed, generic, repetitive, pressure-heavy, over budget, or inside quiet hours. Hard policy gates remain hard gates and cannot be outweighed by urgency.
2. **Ranking:** among eligible candidates, rank urgency/relevance and send at most the highest-value candidate for that decision window. Re-score deferred candidates when new evidence arrives; stale candidates expire instead of accumulating forever.

**Additional done-when for 5.1:** the queue must beat the current independent-gate baseline on the Sprint 1 corpus and in a one-instance soak: fewer same-window collisions without increasing generic or unwanted proactive sends. Every send/skip must leave an owner-readable receipt.

**Hard vetoes (must never be outweighed):** quiet hours / DND, explicit user limits (`/quiet`, `/away`, feature flags), safety/privacy policy, exhausted proactive budget, stale/invalid source data.

**Ranking signals (eligible candidates only):** timing quality, specificity, novelty, pressure/ease of ignoring, urgency/relevance, same-window collision with another eligible candidate.

---

# Sprint 2 — Nightly receipts and sleep-time compute

**Goal:** turn `nightly_maintenance` into a deliberate off-loop compute boundary whose work is visible and auditable the next day.

**Why second:** Sprint 1 defines what good proactive behavior looks like. Nightly compute can then prepare higher-quality candidates and context without adding latency to the live reply path.

## Scope

1. Define a structured **nightly receipt** written by the existing maintenance run. The receipt records what was considered and what changed, for example:
   - memory promotion/consolidation results;
   - milestone updates;
   - overnight mood/day-state transitions;
   - drafted proactive hooks or other precomputed context;
   - proposed living-file edits (`/reviewlife`) when that feature exists;
   - errors, skips, and “nothing to do” outcomes.
2. The receipt is operational evidence, not character-facing prose. It must separate applied state changes from drafts awaiting approval.
3. Move one bounded piece of work from the live path into nightly preparation. The first candidate is ROADMAP 6.2’s proactive-hook pre-draft because it has a clear current live-generation point and does not require a new user-facing feature.
4. Consumption of nightly-prepared work must fail soft: stale/missing nightly output falls back to current behavior rather than suppressing a reply or proactive event.

## Dependency

- Sprint 1’s proactive quality rubric for judging any pre-drafted hook.
- Existing `nightly_maintenance`, `update_milestones`, mood reset, and persistence conventions.

## Exit gate

- A nightly receipt is generated on a pilot instance for seven consecutive maintenance runs and accurately distinguishes applied changes, drafts, skips, and failures.
- At least one live-path generation task is successfully precomputed at night with no new per-message LLM call.
- Missing/stale/corrupt nightly prepared state has a tested fallback to today’s behavior.
- Owner can answer “what did the bot change or prepare overnight?” from one receipt without reconstructing it from logs.

## ROADMAP 6.2 amendment — Deepen `nightly_maintenance` as deliberate sleep-time compute

Keep 6.2’s “move work off the live reply path” principle, and add **receipts as a requirement**. A nightly optimization is incomplete if it makes state/prepares content invisibly.

The standing list of work nightly consolidation may absorb should be ordered:

1. proactive-hook pre-draft;
2. `/reviewlife` candidate extraction/drafting;
3. memory-test fixtures or consistency checks that are read-only against live state;
4. other expensive context preparation only when it has a deterministic freshness boundary and a current-behavior fallback.

**Additional done-when for 6.2:** every absorbed task appears in the nightly receipt with input freshness, applied/drafted/skipped status, and failure reason. At least one absorbed task must demonstrate lower live-path work without changing user-visible behavior when nightly output is absent.

---

# Sprint 3 — Track 7 evaluation harness

**Goal:** make companion quality testable in the places ordinary unit/eval suites do not currently cover: private banter, fleet-wide memory behavior, and contradictory memories.

**Why third:** Sprints 1–2 improve proactive and off-loop behavior. Before broadening those changes fleet-wide, the project needs regression checks for the conversational behaviors most likely to be damaged by “helpful” infrastructure changes.

## Track 7 — Companion quality & memory evaluation

### 7.1 DM banter evaluation — M

**Problem:** generic helpfulness, repeated question-answer cadence, and excessive warmth can all pass correctness tests while making a companion feel less like a person in a private chat.

**Plan:** add a small multi-turn DM corpus scored for reciprocal banter rather than task helpfulness. Cases should include teasing, callbacks, topic pivots, low-energy replies, disagreement, and a user message that does not require a question back. The evaluator should detect at minimum:

- unnecessary interview-style follow-up questions;
- generic affirmation/therapy voice replacing character-specific reaction;
- failure to pick up an obvious callback or running bit;
- over-explaining a casual exchange;
- inability to let a short reply be complete;
- voice flattening over several turns.

This is an eval of outputs, not a new production advisor call.

**Done when:** the corpus breaks on intentionally flattened/generic variants and passes representative known-good character replies; failures point to a named banter dimension rather than one opaque score.

### 7.2 Fleet memory testing — M

**Problem:** memory regressions are usually discovered per character, while the same memory pipeline serves all seven instances. Card/seed differences mean one-instance tests can miss fleet-specific retrieval or provenance failures.

**Plan:** build a fleet matrix of small memory fixtures using each character’s real configuration shape but synthetic/non-sensitive test facts. Cover:

- explicit user fact retrieval;
- own-day/character-state provenance boundaries;
- stale vs fresh fact selection;
- semantic vs keyword recall;
- memory that should *not* be surfaced in an unrelated turn;
- approved vs unreviewed auto-memory status where applicable.

The harness should reuse the existing memory functions and avoid model calls where pure retrieval logic is sufficient.

**Done when:** every fleet configuration runs the same core memory assertions, character-specific failures are visible by name, and the test suite can reproduce at least one historical memory bug class from the repo’s operational history.

### 7.3 Contested memories — M

**Problem:** real conversation contains corrections and disputed claims. A model or extraction pass must not silently convert “A says X, later user disputes X” into one authoritative fact merely because one phrasing scores higher.

**Plan:** represent a contested state explicitly when two otherwise-valid memory candidates conflict and no trusted resolution exists. Preserve provenance for both sides. Retrieval may summarize that the fact is disputed, but mutation/deletion requires the existing owner-review path or an explicit later user correction that meets the project’s grounding rules.

Minimum cases:

- direct correction (“No, that was Tuesday, not Monday”);
- two sources with different claims and different timestamps;
- user uncertainty (“I think it was Tuesday”) vs a prior confident statement;
- character inference vs user-grounded fact;
- reviewed/owner-approved memory vs a later auto-extracted conflicting candidate.

**Done when:** the harness demonstrates that unresolved contradictions remain visible as contradictions, an auto-extracted candidate cannot overwrite an owner-approved fact silently, and a genuine explicit correction can resolve the contest with provenance retained.

## Sprint 3 dependency

- Existing eval runner/gate corpus and memory retrieval code.
- No dependency on implementing the Track 7 production behavior; the first deliverable is test/evaluation infrastructure.

## Sprint 3 exit gate

- 7.1, 7.2, and 7.3 each have break-tested fixtures: an intentionally bad variant fails before the test is trusted.
- Fleet memory tests cover all seven character configurations.
- Track 7 tests are cheap enough to run in the normal validation workflow or have a clearly documented separate command if model-graded evaluation is required.

---

# Sprint 4 — Integrate, pilot, and promote

**Goal:** use the new evidence to ship the smallest high-value behavior changes, then decide what deserves fleet-wide promotion.

## Scope

1. Pilot the 5.1 shared proactive triage queue on one instance, using Sprint 1 receipts and quality gates.
2. Pilot 6.2 proactive-hook nightly pre-drafting and nightly receipts on the same or a deliberately chosen second instance; do not combine pilots if that would make attribution ambiguous.
3. Run Track 7 before and during the pilot so a proactive/maintenance improvement cannot quietly degrade banter or memory behavior.
4. Record a promotion decision for each pilot: fleet-wide, revise/retest, or close as not worth it. “Leave running indefinitely as an experiment” is not a completion state.

## Dependencies

- Sprint 1 exit gate met before 5.1 behavior changes.
- Sprint 2 exit gate met before treating nightly-prepared data as a production dependency.
- Sprint 3 baseline recorded before fleet-wide promotion of either behavior change.

## Exit gate

A sprint-4 pilot may promote only when all of the following are true:

- proactive collision rate improves or stays neutral while proactive quality does not regress on the fixed corpus;
- no material increase in generic check-ins, pressure-heavy messages, or unexplained skips;
- nightly receipts remain complete enough to explain applied/prepared state;
- DM banter eval does not regress;
- fleet memory and contested-memory tests remain green;
- kill switches and fallback behavior have been exercised, not merely inspected;
- the promotion/closure decision and evidence are written back into the canonical roadmap/changelog as appropriate.

---

# Sequencing amendment

| Order | Sprint | Primary roadmap links | Promotion gate |
|---|---|---|---|
| 1 | Proactive quality before volume | 5.1, 5.11 | Quality corpus + inspectable candidate receipts |
| 2 | Nightly receipts / sleep-time compute | 6.2, 5.9 | 7 clean nightly runs + one safe live-to-nightly move |
| 3 | Track 7 evaluation harness | 7.1–7.3 | Break-tested banter + fleet memory + contested-memory fixtures |
| 4 | Integrate, pilot, promote | 5.1, 6.2, Track 7 | One-instance evidence, regressions green, explicit promote/revise/close decision |

The sequencing is deliberate: measure proactive quality before centralizing it; make off-loop work observable before relying on it; establish conversational/memory regression checks before broad promotion; then pilot and promote only with evidence.

## Recovery note

The lost commit’s surviving metadata described this change as four ordered sprints, three Track 7 items, and 5.1/6.2 amendments for proactive-message quality and nightly receipts, with dependencies and exit gates. The exact original wording was not recoverable from GitHub or either local session. This reconstruction intentionally records that provenance so a future session does not mistake it for the byte-identical contents of `964aba2`.
