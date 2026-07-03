# Skill-library build: handoff state (2026-07-02)

Delete this file when the library is complete and reviewed.

## Mission
Build a 15-skill library under `.claude/skills/` so junior/mid-level engineers and
Sonnet-class sessions can maintain and advance telegram-companion-bot without the
departing maintainer. Full spec came from the owner; token cost is not a constraint,
correctness is. Multi-agent orchestration for authoring and review.

## Owner's Phase-1 answers (fold into everything)
- Hardest live problems: **proactive behavior tuning** and **memory quality** (two campaign skills).
- Non-negotiables (all owner-confirmed): bot.py stays the entry point; evidence before
  fixes; never rewrite a character's voice; never auto-touch device state (.env/state/wardrobe).
- Costliest past failures: stale deploys; wrong-diagnosis rabbit holes.
- Ambition ("beyond SOTA"): all four — deepest long-term memory, autonomous living
  characters, full multimodal presence, rock-solid phone infra.
- Audience: non-engineer hobbyist owner + Sonnet-class model with zero context.

## Done (9/15, committed: 80278bb, 4d7c697)
companion-bot-change-control, companion-bot-debugging-playbook,
companion-bot-architecture-contract, companion-bot-config-catalog,
companion-bot-device-ops, companion-bot-diagnostics (+ 4 tested scripts/),
companion-bot-failure-archaeology, companion-bot-validation-and-qa,
companion-persona-engineering-reference.

Key settled findings already encoded (do not re-derive):
- fix-bot-py dead branch: nothing lost; all memory-audit fixes ported to HEAD
  (d0bc024/1a4d067); break→continue deliberately reverted. See failure-archaeology.
- Card system_prompt stripping was SUPERSEDED by DOCUMENT_MODEL routing (9d19b6a).
- Owner's chat client strips $...$ from pasted commands → device-bound commands must
  be zero-dollar-sign. Encoded in device-ops/debugging/diagnostics.

## Remaining to author (6/15) — one agent per skill, general-purpose, background
Each: YAML frontmatter (name + trigger-rich description), when-NOT-to-use with sibling
routing, GROUND TRUTH ONLY (verify every claim against the repo that day), date-stamp
volatile facts, end with "Provenance and maintenance" re-verification one-liners.
Write ONLY inside the skill's own directory; repo otherwise read-only for authors.

1. **companion-bot-proactive-tuning-campaign** — executable, decision-gated campaign for
   the owner's #1 problem. Enumerate ALL proactive paths from bot.py (heartbeat, follow-up,
   event reminders w/ EVENT_NUDGE_BUFFER_MIN defer, explicit reminders (by-design exact),
   Garmin stress/bb/rhr, on-this-day, life-sim, cron) with trigger/gates/log-tag/knobs.
   Fences: never tune before a log tag proves which system fired (the heartbeat→followup→
   event-reminder misdiagnosis chain); budget/quiet-hours exhaustion is not a bug.
   Phases: 0 baseline tag counts (zero-dollar device commands) → 1 misfire taxonomy
   (wrong-time/frequency/content/redundant) → 2 measure the class w/ expected numbers →
   3 ranked menu (env knobs → cross-system cooldown → content variation w/ repetitiveness
   metric → unified scheduler LAST RESORT) → 4 six-bot A/B, promote via change-control.
2. **companion-bot-memory-campaign** — same shape for memory quality. Layer map (verbatim
   window → summary/facts → recent_facts → episodic embeddings (EMBED_CACHE_KEY) →
   lorebook → memories.txt → untrusted quarantine → milestones/pins). Archaeology is DONE
   (see above) — campaign starts at instrumentation: probe harness (planted fact, delay,
   probe, expected recall; recall/contradiction/staleness rates), baseline before tuning,
   failure taxonomy (never-stored / stored-not-retrieved / retrieved-not-used /
   retrieved-wrong → each routes to a different layer), ranked menu (extraction, retrieval,
   salience, provenance+supersession, consolidation LAST), 6-bot A/B, falsifiable
   30-day-recall milestone.
3. **companion-bot-analysis-toolkit** — proof methods as recipes w/ worked examples:
   remote hypothesis bisection (nohup→setsid a080f99; heartbeat chain 6a8061f), regex
   falsification (_FOLLOWUP_RE), AST-extraction dry run (run the skeleton once for real),
   synthetic-fixture proof (WAV w/ silent gap; NOTE constant-amplitude sine defeats the
   relative pause floor — fixture must be realistic in measured dimensions),
   deployed-vs-repo differential, log-absence reasoning (validity preconditions),
   prompt-assembly audit (safety false-positive 18d4162), API-contract-from-reference
   (Inworld swap ed15b25/faea119/bae2dcb).
4. **companion-bot-experiment-methodology** — hunch → accepted change: evidence bar (one
   mechanism explains ALL observations incl. negatives; adversarial self-refutation),
   predict numbers BEFORE running, the six-bot laboratory protocol (persona confounds,
   ≥3 days, log-tag metrics first, owner subjective report LAST), idea lifecycle
   (archaeology check → flag default-OFF → A/B → PROMOTE to .env.example default or
   RETIRE with documented numbers — undocumented retirement forbidden), where ideas come
   from (owner friction reports rank highest), experiment hygiene (don't reset state
   mid-window; restarts reschedule heartbeats; quiet-hours/budget confounds; one
   experiment per subsystem per window). Worked example: EVENT_NUDGE_BUFFER_MIN defer.
5. **companion-bot-research-frontier** — six entries, each: why SOTA ceilings out → this
   project's asset (six-bot lab, longitudinal state, Garmin, voice emotion, full stack,
   high-signal owner) → first three steps in-repo → falsifiable milestone → status:
   longitudinal memory coherence; biometric-attuned companionship; autonomous character
   lives; para-linguistic dialogue over time; commodity-phone fleet reliability (MTBF,
   chaos drill); personality-drift measurement. No oversell; statuses NOT STARTED/PARTIAL.
6. **companion-bot-docs-and-writing** — docs-of-record inventory (CLAUDE.md, OPS_MANUAL,
   SETUP_GUIDE (check INWORLD_API_KEY gap), EPISODIC_RECALL, PROJECT_CONTEXT/INSTRUCTIONS
   (flag stale voice-pipeline claims), MIGRATION.md canonical, .env.example, the skill
   library itself w/ Provenance maintenance protocol), house commit/doc style (git commit
   -F, imperative subjects, 2 real examples), preset.txt is-not-documentation rule,
   update-triggers table (change class → docs that move in the same commit), and a
   "known stale as of <date>" drift list from actual checks.

## Then Phase 3 (after all 15 exist)
Three parallel reviewers over the complete set, then one fixer:
- FACTUAL: re-verify flags/paths/commands/hashes against the repo; flag inventions/stale
  (severity = would it mislead?).
- DOCTRINE: contradictions with CLAUDE.md/owner rules or between skills; overclaims;
  missing gating on behavior-changing advice.
- USABILITY: description trigger quality, duplication (one home per fact), self-
  containedness, scannability.
Fixer applies blocking+important findings. Finally report to the owner: inventory with
one-line descriptions, what was spot-checked, what remains uncertain. Commit as batch 3.
