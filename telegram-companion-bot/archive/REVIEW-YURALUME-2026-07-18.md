# External review — Yuralume core (2026-07-18)

Reviewed at owner request: https://github.com/Yuralume/yuralume-core
Companion piece to `REVIEW-BRAINENGINE-2026-07-18.md`; same rubric.

## What it is

A self-hosted AI-companion **platform**: FastAPI + PostgreSQL 16/pgvector + Vue 3 +
Docker Compose, multi-user JWT auth, one character identity unified across Telegram,
LINE, Discord, and WhatsApp, an Instagram-style character feed ("LumeGram"), media/TTS
gateway specs, BSL-1.1 licensed. Feature highlights: LLM-generated daily schedules
whose completed activities leave "emotional residue" and become episodic memories;
"dream-time" memory consolidation during downtime; a five-layer persona model
(identity/life/emotional/interaction/trust); three-gate proactive messaging (cheap
heuristic → LLM intention judge → LLM decider, daily caps); real-world fact injection
(holidays lib, Open-Meteo weather, curated RSS); scene-aware chat that checks whether
her scheduled location matches the conversational frame before allowing "same-space"
roleplay.

## Verdict up front

This is convergent evolution — a team-scale build of largely the same design our
single-file bot already implements. Most of what looks borrowable turns out to be
**already shipped here**, sometimes down to the same third-party API. The
architecture itself (Postgres, Docker, multi-platform, web UI) is a recorded
non-starter: bot.py stays a single file, and the deploy model depends on it.
**One idea is genuinely worth taking: emotional residue** — her own day's events
seeding her mood. One philosophy difference is worth recording as a deliberate
rejection.

## Already have (no action)

| Yuralume feature | Our equivalent | Evidence |
|---|---|---|
| LLM-generated daily life, activities become episodic memory | `day.txt` generation + midnight rotation into archived, provenance-tagged (`[own-day]`) history | bot.py:1670, `_rotate_day_context` bot.py:9231 |
| Dream-time memory consolidation | Fact consolidation at two horizons — recent (~weekly cap) and long-term — via `_consolidate_facts` | bot.py:4982–5156 |
| Semantic recall (pgvector) | NanoGPT embeddings, embed-on-write, cosine top-k merged with keyword recall (Track 3.3, shipped) | ROADMAP 3.3 |
| Proactive gating + daily caps | Nudge budget + quiet hours/windows + blocked-tick **drafts** ("I almost texted you earlier" — a feature they don't have) | bot.py:2337, 8749 |
| Real weather, keyless | Same API — Open-Meteo, cached hourly, injected as "the actual now" | bot.py:2887, 2965 |
| Holidays as context | Curated season/holiday markers | bot.py:2917 |
| World events backdrop | `world.txt` shared fleet-wide from the `WORLD_GENERATOR` instance | Track 3.2 |
| Per-character view of the user | Per-instance state dirs; each bot's memories/notes/mood are already isolated | architecture |
| Scene-aware framing | `/vibe in-person` mode (manual); automatic schedule-location consistency arrives with roadmap 3.6 | bot.py:5212 |

## Worth adopting

### Emotional residue — her day seeds her mood — S effort, rides an existing call

The one real gap. Today, mood (`moods[chat_id]`) changes **only** through
conversation (`post_reply_analysis`) plus gap decay (`nudge_mood`). Her generated
life — the flat tire, the good shift, the fight with a friend in `day.txt` — never
colors how she *opens*. The user only feels her day if the conversation happens to
touch it. Yuralume's residue concept fixes exactly this.

Zero-extra-call implementation: the midnight day-generation call already returns
structured content; add one JSON key (e.g. `"opening_mood"`: label + valence in her
voice) and write it into the existing mood state at rotation, marked so
`post_reply_analysis` treats it as the current mood baseline like any other. All
downstream behavior (mood → `_mood_behavior` guidance) already exists. Provenance is
safe by construction: mood is presentation state, not a fact store — the `[own-day]`
rule (her fiction never becomes "real" user-facing memory) is untouched.

Natural home: fold into roadmap **3.7** (fatigue + silence license) — same
state-plumbing area, same injection point, and residue gives 3.7's fatigue a
morning-state to interact with. Env kill switch per the 2026-07-18 default-on policy.

## Considered and rejected

- **The platform architecture** (Postgres/pgvector, Docker, Vue admin, multi-user
  auth, cross-platform sidecar) — recorded non-goal; bot.py stays a single file on
  a phone (ROADMAP header). VPS migration (1.2) changes the host, not the shape.
- **"Every semantic decision routes through the LLM"** (their explicit philosophy,
  rejecting keyword heuristics) — we deliberately run the opposite trade where it
  counts: `_map_intent` regex, availability extraction gated to explicit statements,
  proactive heuristic gates. On a phone with a strict LLM-call budget, deterministic
  pre-gates are the feature. Recorded so the philosophy isn't imported piecemeal.
- **Three-gate proactive cascade** (two LLM calls per candidate tick) — our
  heuristic gates + single hook-generation call + draft mechanism already cover the
  outcome at lower cost.
- **LumeGram social feed** — a whole product surface with no Telegram-DM analog.
  Its six posting triggers are mostly covered where they matter (silence → heartbeat
  cadence; memory dates → `_todays_memory_note`; schedule → proactive schedule
  injection). "Emotional-shift" as an extra proactive trigger is the only novel bit;
  not worth an item until the existing proactive system feels stale.
- **Trust/"interaction heat" layer** — solves cold-start relationship progression
  for multi-user platforms. Ours are single-owner, months-deep relationships with
  the anchor set by the character card; an explicit trust score adds state without
  behavior.
- **RSS news injection** — real news in a companion's mouth is a liability (stale
  feeds, grim headlines at the wrong moment) for marginal realism; world.txt +
  real weather + search-enabled ambient hints already ground her.
- **`holidays` library** — strictly more correct than our curated markers, but a new
  dependency across six phone instances to replace something that already works;
  revisit only if the curated list ever causes a miss that matters.

## Recommendation

Fold **emotional residue** into roadmap 3.7's spec (it shares plumbing and makes
fatigue richer); no new roadmap item needed. Everything else: no action, rejections
recorded above so they don't get re-proposed.

No bot.py changes made in this review.
