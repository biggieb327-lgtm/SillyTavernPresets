# External review — MultiAgent-BrainEngine-SillyTavern (2026-07-18)

Reviewed at owner request: https://github.com/DonBananas/MultiAgent-BrainEngine-SillyTavern

## What it is

A Python proxy (OpenAI-compatible, sits between SillyTavern and the model) that
replaces one chat completion with a **six-agent cognitive cascade** per turn:

1. **Somatic Core** — physical reflex state (valence, arousal 0–10, symptoms) as JSON
2. **Neurochemical/Schema** — drives, ego, bonding, active trauma schemas
3. **Theory of Mind** — subtext/power-dynamics read of the user's message
4. **Default Mode Network** — intrusive thoughts + an hour-by-hour daily schedule the
   character actually honors ("if the conversation runs past her 2pm commitment, she
   leaves")
5. **Executive Cortex** — synthesizes 1–4 into a tactical decision, including
   `speech_intent: "Silence / Action Only"`; tracks cognitive fatigue 0–100
6. **Screenwriter** — writes the reply from choreography directives only; all
   `<think>` content regex-stripped from its input so it can't verbalize subtext

Supporting mechanics: fatigue updated **arithmetically** (high arousal or negative
valence +15, calm positive −20, else −5, clamped 0–100) with threshold behaviors
(tunnel vision >6.5 arousal ignores the schedule; critical fatigue = "ego depletion,"
loses social regulation); per-character JSON state file; DMN schedule regenerated
async *after* the reply via FastAPI BackgroundTasks; cheap models for agents 1–4,
expensive for 5–6.

## Hard incompatibility, stated up front

The architecture itself — six completion calls per user turn — directly violates our
**one combined post-reply analysis call** invariant (phone bandwidth; calls compete
with user-facing replies). The author admits the cost problem in their own README.
Nothing below proposes adopting the multi-call structure. What's worth taking are
**mechanics that transplant as prompt content, extra JSON keys on the existing
analysis call, or pure arithmetic on state we already extract** — all zero
additional LLM calls.

## What we already have (no action)

| BrainEngine feature | Our equivalent | Evidence |
|---|---|---|
| Mood/valence tracked per exchange, persistent | `post_reply_analysis` extracts `mood` + `valence` −3..3, moods persist across turns | bot.py:3034–3038 |
| Mood changes behavior, not just flavor text | `_mood_behavior` emits concrete length/energy/engagement guidance | bot.py:3262 |
| Screenwriter firewall (reply never verbalizes internals) | Mood fed as behavioral guidance, never the raw label; model thinking stripped at the `_do_request` choke point (`_strip_thinking`) | CLAUDE.md invariant |
| Hourly schedule in context | `schedule.txt` — today's section injected every turn | bot.py:429, 770, 3816–3819 |
| Independent life outside the chat | `day.txt` multi-day life threads, midnight rotation, `[own-day]` provenance | bot.py:1670 |
| User's physical/availability state | `availability` key (driving/working/busy, explicit-statement-only) + `/energy` + away state | bot.py:3063, 3181, 1831 |
| Cheap/expensive model split | `MOOD_MODEL`/`SUMMARY_MODEL`/`REACTION_MODEL` cheap, chat model expensive | .env.example |
| Thread-safe shared state | Stricter already: event-loop-only serialization, `call_soon_threadsafe` | CLAUDE.md invariants |
| Realistic compose timing | `_typing_delay_secs` + `send_bubbles` pre-delay | bot.py:4239, 4249 |

## Worth adopting

### A. Schedule-driven unavailability (their DMN's best idea) — HIGH value, S–M effort

The single sharpest observation in the repo: a companion that is *always instantly
available and never has to leave* reads as a puppet. We inject `schedule.txt` into
context (bot.py:3819) but nothing **enforces** it — the character never says "I'm
mid-shift, gotta run," never replies slower during a commitment, never returns later
referencing it.

Zero-call implementation sketch:
- Parse today's schedule section for time-ranged entries (we already read it per turn).
- If `now` falls inside a busy block, inject a system line: *"{NAME} is currently
  {activity}. Replies come slower and shorter — she's answering from her phone in
  stolen moments, and she may say she has to go and pick the thread up later."*
- Optionally scale `TYPING_DELAY_MAX` / add a bounded pre-reply delay during busy
  blocks (mechanics already exist in `send_bubbles`'s `pre_delay`).
- Interacts safely with proactives: the existing quiet-hours/nudge-budget checks stay
  authoritative; this only *adds* restraint, never sends.

Fits Track 3 (character & product features). Biggest realism win per line of code in
this whole review.

### B. Cognitive fatigue accumulator — MEDIUM-HIGH value, S effort

Their fatigue math needs **no LLM at all** — it's arithmetic on valence, which we
already extract every exchange (bot.py:3095). Sketch:

- `fatigue` float 0–100 in per-chat state; updated where the valence lands in
  `post_reply_analysis`: intense exchange (|valence| ≥ 2) +10–15, calm positive −15,
  otherwise decay −5; also decay with elapsed time between exchanges (we already
  compute `_gap_hours`, bot.py:3025).
- Above a threshold, one extra system line: *"{NAME} is socially drained — shorter
  replies, less patience for big topics, more likely to wrap up."* Below, nothing.
- Distinct from mood: mood is what she feels *about* things; fatigue is her remaining
  capacity. A great-mood-but-exhausted state is exactly the texture single-axis mood
  can't produce.

Skip their "ego depletion hijack" (dropping social regulation at critical fatigue) —
for a companion bot that failure mode is a feature in an RP sandbox and a liability in
a long-running relationship product.

### C. Silence / minimal-reply license — MEDIUM value, S effort

Their Agent 5 may output `speech_intent: "Silence / Action Only"`. Our bots always
produce a full reply. A prompt-level license — when fatigue is high, mood is low, or a
busy block is active, a bare "k", "lol", or a message reaction is a legitimate
complete reply — would break the "every message earns a paragraph" tell. We already
have reaction infrastructure (`REACTION_MODEL`). Prompt + small plumbing only.

## Considered and rejected

- **Theory-of-mind subtext extraction** (their Agent 3) — *could* ride the existing
  analysis call as one more JSON key, so it's invariant-compatible, but feeding a
  cheap model's guess about the user's hidden motives into the main model is a
  distortion amplifier: a wrong subtext read gets treated as fact by the next reply.
  glm-5:thinking already does this implicitly with full context. Rejected, not
  deferred.
- **Somatic layer as structure** (heart rate, symptoms as separate state) — the mood
  label is free-text and already carries physical state when relevant ("wired on her
  third coffee"). Extra structure, no extra behavior.
- **Dual-stream memory / last-3-think-blocks** — solves a problem we don't have; we
  strip thinking at the choke point and never store it.
- **"Setting" omniscient-narrator bypass** — SillyTavern-frontend concept, no Telegram
  analog; group-chat behavior is pinned by design doc + CI evals, don't touch.
- **The 6-call architecture itself** — see "Hard incompatibility" above. Also their
  own cost note. Recorded so a future session doesn't re-propose it.

## Recommendation

Promote **A** (schedule-driven unavailability) to ROADMAP Track 3 as its own item;
**B + C** together as a second item (they share the state plumbing and the same
prompt-injection point). None of the three adds an LLM call, all three are
default-off-able via env flags per house style. Owner call on whether/when to spec
them into IMPROVEMENTS_PLAN.md.

No bot.py changes made in this review.
