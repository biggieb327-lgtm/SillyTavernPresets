# Roadmap — telegram-companion-bot

Written 2026-07-06 from a code survey of bot.py v2026-07-05.12 (7,626 lines), the
changelog, and CLAUDE.md. Each item names its evidence — why it's on the list — plus
effort (S/M/L), risk, and what "done" means. Ordered by track, sequenced at the bottom.

**Deliberate non-goal, recorded to prevent future refactor urges:** bot.py stays a
single file. The entire deploy model (`/update` swapping one shared file, update-all.sh
curling one URL, `bot.py.bak` rollback) depends on it. The monolith's real cost —
regressions in pure logic — is covered by Track 2.1 instead.

---

## Track 1 — Reliability & platform

The phone is the existential risk (phantom process killer, OEM battery managers,
Python-bump venv breaks — all documented in CLAUDE.md). Everything here reduces
single-device blast radius.

### 1.1 Commit watchdog.sh to the repo — S
- **Evidence:** CLAUDE.md: watchdog.sh "lives at ~/telegram-bot/watchdog.sh on-device —
  not part of this repo". It's load-bearing (catches Termux itself dying, frozen bots),
  caused a full lost debugging session (2026-07-05), and its only copy is on the device
  it's meant to protect. It's also invisible to the eval suite.
- **Risk:** none — additive; stays curl-installed like backup-all.sh.
- **Done when:** watchdog.sh committed; `shell-scripts-parse` eval covers it
  automatically; install instructions in its header match backup-all.sh's pattern.

### 1.2 VPS migration Phase 2 — actually move the fleet — L
- **Evidence:** Changelog v2026-07-05.12 is explicitly "Phase 1 of VPS migration":
  `deploy/bot@.service` (Restart=always) and `deploy/install-vps.sh` already exist and
  are confirmed compatible with the PID-lock/exit patterns. Phase 2 was never specced.
- **Plan:**
  1. Pilot with one low-state bot (jules). Cutover is per-bot and brief: stop the
     instance on the phone → restore its directory from the latest backup-all.sh
     archive onto the VPS → `systemctl start bot@jules`. Only one process may poll a
     bot token, so stop-then-start, never parallel.
  2. Set `HEALTHCHECK_URL` per migrated instance (dead man's switch already built).
  3. `ADMIN_API_ENABLED=1`, bound to the Tailscale IP (Phase 1 auth model, never 0.0.0.0).
  4. Soak the pilot for a week (watch `/audit` error counts vs its phone baseline),
     then migrate the rest one at a time. Phone keeps nora last — she's the shared-venv
     home instance; retire the phone (or keep it as a spare) when she moves.
- **Risk:** state divergence if a bot runs on both hosts — the stop-before-start rule
  is the whole safety story. Timezone: verify tzdata + TIMEZONE on the VPS before the
  first start (the v2026-07-05.5 startup-crash class).
- **Done when:** all six instances on systemd, healthchecks green for 14 days,
  OPS_MANUAL has a "VPS operations" section, and the Termux quirks in CLAUDE.md are
  marked historical.

### 1.3 Fleet status one-shot — S
- **Evidence:** `/audit` is per-bot and manual ×6. The admin API (Phase 1) already
  exposes health/audit per instance.
- **Plan:** `fleet-status.sh` — loop over instances, hit `/admin/health` (+ audit
  summary line each), print a six-row table. Works on-phone now, over tailnet post-1.2.
- **Done when:** one command answers "is everyone up, what version, any errors."

### 1.4 Degradation alerts (fallback rate + monthly spend) — S
- **Evidence:** `_self_audit` DMs on restart storms only. Today a dying primary model
  (every reply silently served by the fallback) or a runaway token bill is invisible
  until someone runs `/model` or `/usage`.
- **Plan:** two counters folded into the existing `_self_audit` pass, same 2h-cooldown
  DM pattern: (a) fallback engaged ≥N times in the last hour → alert; (b) optional
  `USAGE_BUDGET_MONTHLY` env — DM at 80% and 100%.
- **Done when:** alerts fire in a forced test (point NANOGPT_MODEL at a bogus model,
  confirm DM); changelog entry + BOT_VERSION bump (this touches bot.py).

---

## Track 2 — Engineering workflow

### 2.1 Committed unit tests for the pure logic — M (highest-leverage item in the plan)
- **Evidence:** No tests/ directory exists. Changelog v2026-07-05.11 says extract_tags
  changes were "verified via isolated extraction tests since a mismatch here would
  break every message" — those tests were written, used once, and thrown away. The
  eval suite greps for patterns; it cannot catch a logic regression.
- **Plan:** `tests/test_pure.py` (pytest) covering the functions where a regression is
  fleet-breaking and the logic is pure: `extract_tags` (4-tuple contract), cron/
  schedule parsing, `_extract_json`, reminder timezone normalization (pin the
  v2026-07-05.5 naive/aware bug forever), meme caption JSON parsing. First task:
  verify bot.py imports cleanly with `BOT_HOME` pointed at a fixture dir (module-level
  env reads are fine; anything that touches the network or Telegram at import time is
  a bug to fix as part of this item). Add a pytest step to the existing CI workflow.
- **Done when:** CI runs pytest green; the delivery-gate's compile-evidence check is
  upgraded to also accept/expect pytest for bot.py changes.

### 2.2 New-instance bootstrap — S
- **Evidence:** SETUP_GUIDE is a manual multi-step process; adding jules required
  hand-creating the directory, .env, and card, and editing update-all.sh's loop.
- **Plan:** `new-bot.sh <name> <card.json>`: mkdir `~/<name>-bot`, interactive .env
  from .env.example (token, models), curl the card + seed files, launch via run-bot.sh,
  and print the update-all.sh line to add (keeping that list authoritative and human-
  edited rather than magic).
- **Done when:** a seventh instance can be stood up in under five minutes.

### 2.3 Card/seed sync tooling — S
- **Evidence:** CLAUDE.md's "card-only update" is a hand-typed curl per file per
  instance; seeds (people/projects/schedule/atlas.txt) have no pull path at all —
  drift between repo and device is guaranteed over time.
- **Plan:** `sync-cards.sh` (or `update-all.sh --cards`): for each instance, read
  CHARACTER_CARD from its .env, pull that card + its seed directory from main, then
  per-bot `/restart` note. Never touches .env or state files.
- **Done when:** one command converges every instance's content files with main.

---

## Track 3 — Character & product features

### 3.1 Voice conversational symmetry — S
- **Evidence:** handle_voice transcribes and replies through the normal text path;
  a voice reply happens only if the user has toggled `/voice` on AND the 30%
  `TTS_CHANCE` roll hits. Answering a voice note with text reads as the character
  ignoring the medium.
- **Plan:** in the voice path, bias to reply in kind: if TTS is configured, reply to a
  voice note with voice at high probability (`VOICE_REPLY_TO_VOICE`, default ~0.9),
  independent of the ambient TTS_CHANCE. Respect existing infra (Inworld/OpenAI engine
  pairing rule from CLAUDE.md).
- **Done when:** sending a voice note gets a voice note back; text messages unchanged.

### 3.2 Shared world context — M (best character-depth per token spent)
- **Evidence:** all six characters live in the same Seattle metro; each instance's
  midnight `_rotate_day_context` generates its day in isolation. Nora's rainstorm is
  not Priya's rainstorm.
- **Plan:** one instance (nora, the home instance) additionally generates a small
  `world.txt` at midnight — shared weather mood, one or two ambient local happenings —
  written to a shared path (`~/telegram-bot/world.txt`); every instance's day
  generation reads it as context if present. One extra LLM call per day fleet-wide;
  degrades gracefully (file absent = today's behavior).
- **Done when:** two different bots, asked about their day, reference a consistent
  world (same weather/event) while keeping distinct personal threads.

### 3.3 Semantic memory recall — M, gated on a research question
- **Evidence:** recall/memory search is keyword-based; "remember when we talked about
  my sister's wedding?" only works if the stored fact shares words with the question.
- **Gate (research-scout task, do first):** does NanoGPT expose an embeddings endpoint?
  If no, this item is deferred — running local embedding models on the phone is off the
  table, and post-VPS it can be revisited.
- **Plan if yes:** embed facts/memories on write (cached to a sidecar file), embed the
  query on recall, cosine top-k merged with keyword results. Fallback to keyword-only
  on any API failure.
- **Done when:** paraphrased recall questions retrieve the right memory in a test set
  of ~20 stored facts.

### 3.4 Group chat / bot-to-bot — L, experimental, deliberately last
- **Evidence:** none of the plumbing assumes groups (`_is_allowed` is per-user, memory
  is per-chat_id); this is the one genuinely new surface. It's also the fun one:
  two characters + you in one Telegram group.
- **Hard problems to solve on paper before any code:** turn-taking (bots must not
  answer every message, especially each other's), loop prevention (hard cap on
  consecutive bot-to-bot exchanges), cost (two models per conversational beat), and
  memory semantics (group memories vs the private relationship state).
- **Done when:** a design doc survives adversarial-critic review; only then a
  prototype behind `GROUP_MODE=1` on two instances.

---

## Sequencing

| Phase | Items | Rationale |
|---|---|---|
| **Now** (days) | 1.1 watchdog→repo, 1.3 fleet-status, 2.3 card sync, 3.1 voice symmetry, 1.4 alerts | All S; four are pure additions, 1.4/3.1 are small bot.py diffs (one release each, normal /update deploy) |
| **Next** (weeks) | 2.1 test suite, 2.2 new-bot.sh, 3.2 shared world, 3.3 research gate | Tests before the bigger feature work lands on top |
| **Then** (a month+) | 1.2 VPS Phase 2 | Biggest payoff, needs the soak time; alerts+healthchecks from "Now" make the soak measurable |
| **Someday** | 3.3 build (if API supports), 3.4 group chat | Both gated — one on a fact, one on a design review |

Execution maps onto the agent system: builder implements one item per dispatch,
qa-engineer verifies against each item's "done when", research-scout owns the 3.3 gate,
adversarial-critic reviews the 3.4 design doc, and every bot.py-touching item ships
with the usual BOT_VERSION bump + changelog entry (the delivery gate enforces it).
