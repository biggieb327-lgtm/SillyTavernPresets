---
name: companion-bot-experiment-methodology
description: >
  The research methodology for telegram-companion-bot — the discipline that turns a hunch
  about companion behavior into an accepted change or a documented retirement. Load this
  whenever you are: proposing ANY behavior change ("let's try X", "what if she...", "she'd
  feel more alive if..."); designing an A/B experiment across the six bot instances;
  deciding whether an experimental env flag should become the default; evaluating whether
  an idea "worked"; writing success criteria for a tuning change; or tempted to accept
  "the reply felt better" as evidence. Covers the evidence bar (one mechanism must explain
  ALL observations), predict-before-run, the six-bot A/B protocol, the idea lifecycle from
  hunch to PROMOTE/RETIRE, idea sourcing, and experiment hygiene. Do NOT use for: choosing
  WHAT to research (companion-bot-research-frontier), investigating a live bug
  (companion-bot-analysis-toolkit / companion-bot-debugging-playbook), building measurement
  instruments (companion-bot-diagnostics), or the memory/proactive campaigns, which embed
  their own protocols.
---

# Companion-Bot Experiment Methodology

How a hunch about companion behavior becomes an accepted change — or a documented
retirement. Nothing in between.

**Why this skill exists.** This domain is seductive. Six characters text one human daily,
and every change *feels* like something. "The reply felt better" is not evidence. The
owner's confirmed rule for this project is **evidence before fixes, with measurable
success criteria**. This skill is that rule, operationalized.

**The system under study.** One ~8,900-line `bot.py` runs six identical-code,
different-persona instances (nora, bonnie, cass, emily, jules, priya) on the owner's
Termux/Android phone, each with its own `.env` and its own `state.json`/`bot.log`. One
human interacts with all six. That is a real laboratory — treat it like one.

---

## 0. Routing — is this the right skill?

- "What should we research next?" → **companion-bot-research-frontier**.
- "Something is broken / behaving weird" → **companion-bot-debugging-playbook** (triage),
  then **companion-bot-analysis-toolkit** (deep investigation).
- "How do I measure X?" → **companion-bot-diagnostics** (log tags, /diag, scripts).
- "Was this tried before?" → **companion-bot-failure-archaeology** (check FIRST, always).
- Memory recall or proactive-timing work → the **memory-campaign** / **proactive-tuning-campaign**
  skills embed their own decision-gated protocols; this skill is the general method they
  specialize.
- Shipping the resulting change → **companion-bot-change-control**; verifying it compiles
  and behaves → **companion-bot-validation-and-qa**; flag naming and `.env.example` duties
  → **companion-bot-config-catalog**.

---

## 1. The evidence bar: one mechanism, ALL observations

A hypothesis is accepted only when **one mechanism explains every observation you have —
including the negative ones** (the log line that ISN'T there, the bot that DIDN'T misfire).

**Worked example — the heartbeat misdiagnosis** (see commit `6a8061f`'s message for the
full record). The owner reported "heartbeat messages firing a minute after I send a
message."

- Hypothesis 1 (heartbeat itself): ruled out — the `[heartbeat]` log showed its normal
  2–6h cadence and correct skips near recent activity. *Mechanism failed to explain the
  timing.*
- Hypothesis 2 (follow-up feature): explained the delay, **but not the empty `[followup]`
  log** — its trigger regex genuinely did not match the offending reply, and the log
  confirmed it never fired. *One unexplained observation → not done. This is the step
  where it is tempting to stop.*
- Hypothesis 3 (auto-extracted event reminders): explained the delayed send, the empty
  `[followup]` log, AND an earlier-pasted `[event] scheduled 1 nudge(s)` line the other
  hypotheses ignored. `fire_reminder()` had no last_seen check, unlike every other
  proactive path. *Everything accounted for → accepted.*

**Checklist before accepting any mechanism:**

- [ ] List every observation, positive and negative (lines present, lines absent, timing,
      which bots affected, which bots NOT affected).
- [ ] The mechanism explains each one. A mechanism leaving even one observation
      unexplained is not done — say so and keep going.
- [ ] **Adversarial self-refutation:** construct the strongest alternative mechanism you
      can, then design the single observation that discriminates between it and yours.
      Go get that observation before accepting.

---

## 2. Predict numbers before running

Every experiment states its expected observation **before** execution, in terms of log
tags, counts, or timings — not vibes.

Good: "With the defer gate on, `[event-reminder]` should show `owner active, deferring`
lines on days with mid-conversation events, and there should be **zero** event-nudge
sends within 15 minutes of `last_seen`."

Bad: "The check-ins should feel more natural."

**If you cannot state an expected number or log pattern, you do not have an experiment —
you have a missing instrument.** Go to **companion-bot-diagnostics**, add or find the
log tag / counter / script that would make the prediction statable, and come back.

Write the prediction down (in the plan, the commit message, or the archaeology entry)
BEFORE the window opens, so the result cannot be quietly reinterpreted afterward.

---

## 3. The six-bot laboratory: per-bot A/B protocol

The project's unique asset: **identical code, different personas, one shared user.** A
flag can be ON for some `.env` files and OFF for others, giving treatment and control
cells running the same day against the same human.

**Protocol:**

1. **Choose cells.** 2–3 treatment bots + the rest as controls.
   **Account for persona confounds:** baselines differ per persona — do not put the one
   flirty character alone in treatment and then attribute her warmer replies to your flag.
   Mix persona types across cells, or compare each bot against its own pre-window baseline.
2. **Apply flags via owner-run `.env` edits.** The flags are per-instance because each bot
   has its own `.env`. Compose the commands per **companion-bot-device-ops** paste rules —
   in particular the owner's chat client **strips `$...$` spans**, so commands must contain
   zero dollar signs, one literal line per bot (no loops, no variables). Restart only the
   affected bots.
3. **Run the window: ≥3 days or ≥N interactions per cell** (state N up front, per your
   Section 2 prediction). Companion behavior is bursty; one good evening proves nothing.
4. **Measure objectively FIRST:** log-tag counts and timings from each bot's `bot.log`
   (grep the tags named in your prediction; **companion-bot-diagnostics** has the tag map
   and tested scripts).
5. **Owner's subjective report LAST.** Ask only after you have the numbers, so the numbers
   aren't anchored. Agreement is confirmatory. **Disagreement is a finding to investigate,
   never to suppress** — "the numbers say fewer interruptions but it still feels naggy" is
   the start of the next experiment, not noise.

---

## 4. The idea lifecycle

Every behavior idea walks this path. No skipping stages.

```
hunch → archaeology check → hypothesis w/ predicted numbers → flag implementation
      → A/B window → verdict: PROMOTE or RETIRE (both documented)
```

1. **Hunch.** "What if she deferred reminders when we're mid-conversation?"
2. **Archaeology check.** Load **companion-bot-failure-archaeology**: was this tried?
   Rejected? Why? If it lost before, you need a reason the old evidence no longer applies.
3. **Hypothesis with predicted numbers.** Per Section 2. Written down before any code.
4. **Env-flag implementation.** New behavior ships behind an env var, **default OFF**,
   documented in `.env.example` with a comment marking it experimental (naming and
   documentation duties per **companion-bot-config-catalog**). Default-off means deploying
   the code changes nothing until a `.env` opts in — treatment assignment stays in the
   owner's hands.
5. **A/B window.** Per Section 3.
6. **Verdict — one of exactly two:**
   - **PROMOTE:** flip the default in code and `.env.example`, update docs, and write an
     archaeology entry recording the evidence (the predicted numbers, the observed
     numbers, the window).
   - **RETIRE:** remove the flag and code, OR leave it documented-off if removal is risky
     — **plus an archaeology entry with what was tried, the numbers, and why it lost.**

**Undocumented retirement is forbidden.** A silently deleted flag is how battles get
re-fought six months later. The archaeology entry IS the retirement.

---

## 5. Where good ideas come from (ranked, with receipts)

Verifiable in `git log` of this repo:

1. **Owner friction reports — rank highest.** The heartbeat-timing complaint (→ `6a8061f`),
   the /delmem confusion (→ `1996735`), and safety false positives all began as complaints.
   A complaint is a free, pre-validated observation about the only user who matters.
2. **Audits.** The `fc44dd2` batch (uniform command guarding, SSRF validation, JSON
   quarantine) came from a systematic audit, not a symptom.
3. **External references, adapted via the API-contract method.** Don't port projects;
   extract the API contract and vendor the minimum. Examples: `menelly/AI_Ears` →
   `acoustic_ears.py` acoustic tone analysis (`bae2dcb`, vendored with attribution);
   the NanoGPT → Inworld STT/TTS swap (`ed15b25`, `faea119`).
4. **New-modality dogfooding.** Garmin health feed (`1b8c915`), voice emotion — adopt a
   new signal source, live with it, let friction reports emerge.

---

## 6. Experiment hygiene for THIS system

- **`state.json` and `bot.log` are the instruments. Never reset, trim, or "clean up"
  either mid-window.** Wiping state destroys your baseline; trimming logs destroys your
  measurements.
- **Restarts are safe for heartbeat timing** — the next tick is persisted in
  `.next_heartbeat` (see `NEXT_HEARTBEAT_FILE` and `schedule_next_heartbeat(...,
  resume=True)` in `bot.py`), so a mid-window restart does not re-roll it. But event
  reminder defer counts (`_deferred`) and job-queue state are in-process where noted —
  check `bot.py` before assuming any timer survives a restart.
- **Hold confounds constant across cells:** quiet hours (`in_quiet_hours()` plus the
  per-user `/quiet` state) and the per-chat nudge budget (default 3/day, persisted in
  `state.json`) both gate proactive sends. If treatment bots have different quiet windows
  or budgets than controls, your counts measure the gates, not your flag.
- **One experiment per subsystem per window.** Two simultaneous experiments are allowed
  only if their metrics share **no log tags and no prompt blocks** — otherwise you cannot
  attribute the delta.

---

## 7. Worked end-to-end example: the event-reminder defer (commit `6a8061f`)

Retrospective case study — this feature predates the formal protocol but exhibits it.

1. **Friction report:** "heartbeat messages firing a minute after I send a message."
2. **Discriminating evidence** (Section 1): heartbeat log normal → ruled out; follow-up
   explained timing but not the empty `[followup]` log → ruled out; event reminders
   explained everything **including** the earlier-pasted `[event] scheduled 1 nudge(s)`
   line. Root mechanism: `fire_reminder()` had no owner-active check, unlike the heartbeat
   (which skips when the owner was recently active). (The Garmin monitors don't check
   `last_seen` either — cooldown + quiet hours only; that gap is flagged in
   companion-bot-proactive-tuning-campaign.)
3. **Fix behind knobs:** `EVENT_NUDGE_BUFFER_MIN` (default **15** — defer if owner active
   within that many minutes) and `EVENT_NUDGE_MAX_DEFERS` (default **3** — fire anyway
   after that many deferrals), `bot.py` lines ~177–178. Scoped to `kind == "event"`
   auto-extracted nudges only — explicit `/remindme` reminders still fire exactly when
   asked.
4. **Observable prediction it supports:** `[event-reminder] <event>: owner active,
   deferring 15m (attempt N/3)` lines on interrupted days; zero event-nudge sends within
   the buffer of `last_seen`.
5. **What promotion looks like:** the knobs documented in `.env.example` (lines ~251–252)
   with sane defaults baked in — the behavior is now the default, and the knobs remain as
   tuning surface.

Use this shape for every future experiment; the only part that was missing historically
was the pre-registered prediction — do not skip it going forward.

---

## Provenance and maintenance

- Written 2026-07-02 against `bot.py` (~8,937 lines) on branch `claude/push-to-repo-7i2f3c`;
  all flag names, defaults (15/3), log tags, `.next_heartbeat` persistence, and commit
  hashes (`6a8061f`, `fc44dd2`, `bae2dcb`, `ed15b25`, `faea119`, `1b8c915`, `1996735`)
  verified in-repo on that date.
- If a cited default, tag, or line number disagrees with today's `bot.py`, trust `bot.py`
  and update this file in the same commit.
- When a sixth-bot roster change, a new proactive path, or a new instrument lands, update
  Sections 3 and 6 — they encode system facts, not just method.
