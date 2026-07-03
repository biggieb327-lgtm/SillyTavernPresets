---
name: companion-bot-research-frontier
description: >
  The research-frontier map for telegram-companion-bot: where this specific project — six
  persona-differentiated bot instances sharing one bot.py, one real daily user, months of
  per-character state, a live Garmin biometric feed, voice-with-emotion in/out, and total
  stack ownership on a Termux phone — can genuinely advance the state of the art, stated
  honestly with zero oversell. Load this when: choosing ambitious work beyond maintenance;
  the owner asks "what's the next big thing?" or "what should we build next?"; evaluating
  whether a proposed idea is actually novel here or just novel-sounding; prioritizing
  between long-term memory, autonomy, multimodal presence, and infrastructure ambitions; or
  writing up a result and needing the frontier framing it belongs to. This skill owns the
  MAP, not the marches. Do NOT use for: day-to-day fixes and live symptoms
  (companion-bot-debugging-playbook); how to run an experiment once chosen
  (companion-bot-experiment-methodology); memory-campaign execution detail
  (companion-bot-memory-campaign); proactive-timing execution detail
  (companion-bot-proactive-tuning-campaign).
---

# Companion-bot research frontier

All file/function/flag references below verified against HEAD on **2026-07-02**. Every entry
carries a status line; **nothing on this map is claimed as achieved**. "Publishing" for this
personal project means: a written-up result in the repo with reproducible numbers, not a
paper. When an entry graduates from map to march, it gets a campaign skill (as memory and
proactive tuning already did) — this file then points there and keeps only the framing.

## Why this project can touch the frontier at all

The unfair assets, each verified real:

- **(a) A six-way natural laboratory.** Six instances (`nora`, `bonnie`, `cass`, `emily`,
  `jules`, `priya` — six per-character dirs in `telegram-companion-bot/`) run *identical
  code* (`bot.py`, 8,937 lines) with different personas and per-instance state, talking to
  *one shared human*. Same code + same user + varied persona = controlled A/B across
  characters for free. No lab replicates months of this cheaply.
- **(b) Longitudinal real-relationship state.** Months of `state.json`, `.episodes.jsonl`,
  `life_events.txt`, `memories.txt` per character (`STATE_FILE`/`EPISODES_FILE` in bot.py).
  Real accrued history, not synthetic benchmark transcripts.
- **(c) A live biometric side-channel.** Garmin stress / body battery / resting HR wired to
  behavior: `stress_monitor_job`, `bb_monitor_job`, `rhr_monitor_job` in bot.py, gated by
  `STRESS_ALERTS` / `BB_ALERTS` / `RHR_ALERTS`. Verified caveat (2026-07-02): these
  monitors do **not** check `last_seen` — a flagged invariant gap owned by
  companion-bot-proactive-tuning-campaign.
- **(d) Para-linguistic input.** Inworld STT returns an emotion `voiceProfile`
  (`_transcribe_inworld`, `voiceProfileConfig.enableVoiceProfile`), plus local acoustic
  tone analysis (`acoustic_ears.py`, `VOICE_TONE_ENABLED`, `_analyze_voice_tone`). Voice
  out via Inworld TTS (`_synth_inworld`). Landed 2026-07-01.
- **(e) Total-stack ownership on commodity hardware.** Prompt assembly, memory, scheduling,
  supervision (`watchdog.sh`, `.alive`, `termux-boot-start.sh`) — all owned, all
  instrumentable, on one consumer Android phone.
- **(f) A high-signal evaluator.** One owner with established feedback discipline; every
  proactive message and recall gets a real human read, daily.

The four ambition axes these assets serve: deepest long-term memory, autonomous living
characters, full multimodal presence, rock-solid phone infra.

---

## Frontier 1 — Longitudinal memory coherence

**Why SOTA ceilings out.** Common practice is RAG over chat logs; over months it degrades
into contradiction and staleness (old facts outrank their replacements; nothing marks a
fact superseded). Month-scale, single-user coherence numbers are essentially unpublished —
benchmarks use synthetic long contexts, not one real relationship aging in place.

**This project's asset.** (b): months of real per-character state with known plant dates,
plus (a): the same fact can be probed across bots with different memory-knob settings.

**First steps in this repo:**
1. Build the probe harness specified in companion-bot-memory-campaign **Phase 1** (its own
   text, verified today: "no probe harness in the repo as of 2026-07-02" — the fixture is a
   4-tuple of planted fact / delay / probe question / expected recall).
2. Add provenance to extracted facts (source date + origin layer) so a recalled fact can be
   audited back to what created it — touches the `recent_facts` / `memories.txt` /
   `.episodes.jsonl` layers mapped in the memory campaign skill.
3. Add supersession semantics: when a new fact contradicts a stored one ("Kate moved to
   Denver" → "Kate's Denver plan fell through"), the old one must lose retrieval priority,
   not merely coexist.

**You have a result when:** a fact planted ≥30 days prior is retrieved in ≥9/10 scripted
probes on 3+ bots, with zero contradictions in a 20-probe audit.

**Status: PARTIAL.** The layered memory system exists and works day-to-day; the memory
campaign skill exists with the probe-harness design; the fix-bot-py reconciliation is
**DONE** (all fixes in HEAD — not an open step). No harness, no provenance, no
supersession, no numbers yet.

---

## Frontier 2 — Biometric-attuned companionship

**Why SOTA ceilings out.** No consumer companion product closes the loop from live
physiology to conversational behavior. Fitness apps show you the number; companions ignore
it. The interesting question — does physiological attunement measurably change engagement —
has no published answer because nobody has both signals in one system with one user.

**This project's asset.** (c) + (f): a real Garmin feed already wired to three monitor jobs,
and an owner whose reply latency/length is measurable from logs.

**First steps in this repo:**
1. Quantify the baseline from logs: `[stress]` / `[bb]` / `[rhr]` firings vs owner
   receptivity (did the owner reply, how fast, how long) — instrumentation per
   companion-bot-diagnostics.
2. Close the flagged gap: the Garmin monitors (`stress_monitor_job`, `bb_monitor_job`,
   `rhr_monitor_job`) don't check `last_seen`, so a nudge can land mid-conversation — the
   fix pattern (mirror `fire_reminder`'s owner-active defer) is already sketched in
   companion-bot-proactive-tuning-campaign.
3. Move beyond check-ins to **tone modulation**: key conversational register to body-battery
   bands (e.g. BB ≤ `BB_LOW_THRESHOLD` → softer, lower-demand replies) behind a new
   experimental env flag, then A/B it across bots per companion-bot-experiment-methodology.

**You have a result when:** attuned vs control bots show a measurable engagement difference
(owner reply latency/length from logs) over 2 weeks.

**Status: PARTIAL.** The feed, snapshot cache (`_garmin_snapshot`), and three alert monitors
exist and fire. No receptivity quantification, no last_seen gate, no tone modulation, no
A/B numbers.

---

## Frontier 3 — Autonomous character lives

**Why SOTA ceilings out.** Generative-agents research (simulated towns, emergent routines)
never ships into one real user's daily texture — it's evaluated on sim-internal metrics,
not on whether a human *living alongside it* finds the life credible over months.

**This project's asset.** (a) + (b) + (f): a life-sim that already runs
(`LIFE_SIM_ENABLED`, `life_event_job` → `_generate_life_event` → `_append_life_event` into
`life_events.txt`, grounded in per-character `schedule.txt` / `people.txt` /
`projects.txt`). Verified today: it **never sends messages** — events only color
conversation via prompt assembly (`_read_life_events` feeds the prompt path). Six parallel
lives, one human judge.

**First steps in this repo:**
1. Audit how much life actually accrues weekly: count and read `life_events.txt` growth per
   character from device logs — is it a life or a trickle?
2. Cross-character world consistency behind a flag: two bots referencing one shared event
   (they nominally inhabit overlapping worlds; today each `life_events.txt` is an island).
3. Define a surprise-without-nonsense proxy: events should be novel against the character's
   recent-events list (the generator already anti-repeats) yet consistent with her
   `people.txt`/`projects.txt` — score both, not just one.

**You have a result when:** owner-blind discrimination — the owner cannot reliably tell
scripted from emergent life events in K trials, while contradictions stay zero.

**Status: PARTIAL.** Life-sim ships and runs daily. No accrual audit, no cross-character
events, no discrimination trial, no contradiction audit.

---

## Frontier 4 — Para-linguistic dialogue over time

**Why SOTA ceilings out.** Voice-emotion SOTA is per-utterance: classify this clip, react to
this turn. Prosody *over time* — "your voice has sounded flat all week" — is ignored,
because no system holds both longitudinal voice data and a persistent relationship.

**This project's asset.** (d) + (b): every voice note already yields an Inworld
`voiceProfile` and a local acoustic read (`acoustic_ears.analyze_acoustic` →
`describe_acoustic`), inside a system that persists state per character.

**First steps in this repo:**
1. Verify persistence (done today, 2026-07-02): in `handle_voice`, the tone note
   (`vp_note`/`tone_note`) enters only the single turn as `[How it sounded: …]`; the
   `recent_facts` entry keeps **only the transcript snippet** (`Voice note: "…"`). Tone is
   currently discarded after one turn — that's the gap.
2. Persist a compact per-voice-note tone record (timestamp + emotion label + energy) into
   per-instance state.
3. Add tone trending behind a flag: a rolling window over those records ("voice energy
   declining across a week") feeding the existing mood system (`nudge_mood` /
   `_appraise_mood` / `update_mood`) so the character can *notice*, not just react.

**You have a result when:** the bot correctly flags a synthetic "flat week" fixture (built
per companion-bot-analysis-toolkit's synthetic-audio recipes) AND a real one the owner
confirms.

**Status: PARTIAL.** Per-turn emotion + acoustic tone shipped 2026-07-01 and works. Zero
persistence of tone, zero trending.

---

## Frontier 5 — Commodity-phone fleet reliability

**Why SOTA ceilings out.** "Run 6 unattended LLM companion processes 24/7 on one consumer
Android phone" is an unpublished ops regime. The lore is real and non-obvious: the
`termux-boot-start.sh` header documents (verified today) that **nohup was insufficient** —
Termux/Android process-group cleanup killed nohup'd loops anyway, and only `setsid`
(a genuinely new session) survives. That kind of knowledge exists nowhere else.

**This project's asset.** (e): full supervision chain owned in-repo — `watchdog.sh` (tmux
session + stale-`.alive` restart logic), the bot's 60s `.alive` stamping, `watchdog.log`,
`termux-boot-start.sh`, `update-all.sh`.

**First steps in this repo:**
1. Uptime instrumentation: parse `watchdog.log` restart lines plus `.alive` mtime gaps into
   a per-bot MTBF definition (build the script per companion-bot-diagnostics conventions).
2. Chaos drill: owner reboots the phone cold; measure unattended time-to-full-recovery for
   all six bots, no human touch.
3. Publish the regime: write up MTBF, recovery time, and the setsid finding with numbers.

**You have a result when:** 30 days, zero human interventions, **measured** from logs — not
assumed from silence.

**Status: PARTIAL.** Supervision chain built and battle-tested (watchdog, liveness file,
boot script, one-command deploy). No MTBF metric, no measured chaos drill, no 30-day
zero-touch record.

---

## Frontier 6 — Personality stability under drift

**Why SOTA ceilings out.** Whether a fixed-card persona's *voice* drifts over months of
accumulating memory/context is unmeasured everywhere — evals test persona adherence on
fresh contexts, never on month-old organically-grown ones.

**This project's asset.** (a) + (b): six fixed character cards (`nora/nora.json` etc.,
format per companion-persona-engineering-reference) plus months of real reply logs per
character — the exact corpus a drift measurement needs.

**First steps in this repo:**
1. Build a style-fingerprint probe: n-gram / stylistic-marker distributions per character
   from log history (device `bot.log` archives), computed offline in the scratchpad.
2. Compute drift rate: fingerprint distance from each character's early-epoch baseline,
   per week, per character.
3. Test whether periodic exemplar re-injection (fresh card-voice examples into the prompt,
   respecting the voice-preservation rules in companion-persona-engineering-reference)
   flattens the curve — A/B across bots.

**You have a result when:** a drift metric is defined and a baseline curve exists for 3
characters. (The re-injection test is the *second* result.)

**Status: NOT STARTED.** The raw materials (fixed cards, long logs) exist; no fingerprint,
no metric, no curve.

---

## Routing

- Chose a frontier and now designing the experiment → **companion-bot-experiment-methodology**.
- Frontier 1 execution → **companion-bot-memory-campaign**. Frontier 2's gating/timing work
  → **companion-bot-proactive-tuning-campaign**.
- Building the measurement instrument → **companion-bot-diagnostics**; proving a mechanism
  → **companion-bot-analysis-toolkit**; shipping it → **companion-bot-change-control** and
  **companion-bot-validation-and-qa**.
- Before proposing anything here, check **companion-bot-failure-archaeology** — several
  obvious-seeming ideas were already tried and retired.

## Provenance and maintenance

- Written 2026-07-03; every named file/function/flag verified against HEAD on 2026-07-02.
- Sources: bot.py (8,937 lines at verification), acoustic_ears.py, watchdog.sh,
  termux-boot-start.sh, and the sibling skills named above.
- Update this file when: a frontier's status changes (steps land, a milestone is hit or
  falsified), a new campaign skill spins out of an entry, or a verified asset stops being
  true (e.g. the Garmin last_seen gap gets closed — Frontier 2 step 2).
- Honesty rule: statuses may only move on evidence with numbers in the repo; "it felt
  better" never advances a status.
