# Changelog — telegram-companion-bot

Read this before making changes; add an entry after shipping one. See `CLAUDE.md` for
why this file exists and the rule for keeping it updated.

Entries are newest first. Each one names the actual root cause, not just the code diff —
that's the part worth reading twice, since re-diagnosing a solved problem from scratch is
exactly what this file is meant to prevent.

## 2026-07-20 — Ops: reconcile Nora's instance dir in launch/sync scripts (no bot.py change, no version bump)

Root cause: `update-all.sh`, `watchdog.sh`, and `sync-cards.sh` all passed `$BOT_SRC`
(`~/telegram-bot`, the shared *code* dir) as Nora's *instance* dir, but her instance dir
is `~/nora-bot` (confirmed on-device 2026-07-11 via the STARTUP AUDIT `Instance:` line;
recorded in CLAUDE.md, vault/entities/nora.md, SETUP_GUIDE, OPS_MANUAL). This was the
open item CLAUDE.md flagged ("verify update-all.sh matches on-device") and never closed.
Latent, not yet fired: `/restart` restarts the running process in place and watchdog only
relaunches a *down* session, so the wrong dir never executed — but the next `update-all.sh`
full redeploy or post-crash watchdog relaunch would have brought Nora up from `~/telegram-bot`
(wrong `.env`/token/state), and watchdog's freeze check was already reading the wrong
`~/telegram-bot/.alive` heartbeat. Fixed all three to use `~/nora-bot`; `$BOT_SRC` stays the
code dir (run-bot.sh is still invoked from it). Pinned by the new `nora-instance-dir` eval
(break-tested red-green). Surfaced during the preset.txt deploy-path work below.

## 2026-07-20 — Content: preset.txt anti-slop banlist extended, fleet-wide (no bot.py change, no version bump)

Cherry-picked the emotional-narration clichés from the Megumin Suite V9 banlist that our
shared `preset.txt` didn't already cover. Root reason to record: `preset.txt`'s existing
`[ANTI-SLOP]` list targets structural/assistant tells ("X, not Y" frames, rule of three,
"a testament to"); Megumin's targets emotional-cliché phrasing — largely non-overlapping,
so the additions are additive, not redundant. Added to `[ANTI-SLOP]`: three construction
bullets (action+symbolic-meaning double, mask-drop announcements, feelings-as-machinery
verbs) and inline phrases ("washed over," "flooded through," "let out a breath she didn't
know she was holding," "before she could stop herself," "seemed to physically flinch,"
"hit like a physical blow," "the weight of it" as standalone metaphor). Fleet-wide: all
six bots read the shared preset. Deploy: `sync-cards.sh` + `/restart` each bot. Note:
`sync-cards.sh` previously synced only the card + seed files and never touched
`preset.txt` — a shared fleet-wide file with no deploy path — so this change adds a
`preset.txt` pull to it (verified via `--dry-run`). Origin: mobile Tavo port task — see
`megumin-mobile/`; wholesale-merging the port was rejected (it duplicated ~70% of
preset.txt and carried CYOA/"the PC" vocabulary that doesn't fit a texting companion).
## 2026-07-20 — Fleet preset.txt: three refinements (no bot.py change, no version bump)

From the preset review (`character-review/PROPOSALS-2026-07-presets.md`). All three
touch `preset.txt`, the shared voiceprint feeding all six bots (fleet-wide):
1. **Anti-slop "deliberate craft" clause** (mined from Atelier 2.0's No-Slop): the
   banned-construction list is now explicitly "defaults to avoid, not a checklist to
   freeze against" — a banned move made on purpose because the voice earned it is
   craft, not slop. Prevents the hard banned-list from stiffening prose into hedged,
   generic replies.
2. **Anti-diagnosis register rule** (mined from UnifiedWritersRoom's Reaction
   Patterns), added to EPISTEMIC HORIZON: {{char}} reads {{user}} but doesn't
   armchair-diagnose them ("you use humor to deflect") unless literally a therapist —
   voice a read as observation + question, not a packaged verdict.
3. **"Punchy" wording fix**: TEXT DELIVERY said "prefer shorter, punchier responses"
   while ANTI-SLOP bans closing on a punchy one-liner; clarified to "brevity, not a
   dramatic one-liner" so the two sections stop contradicting.
Root/inbox presets needed no edits (TheAtelierV5 was already replaced; Megumin's
Arabic CoT is intentional — scoped to hidden thinking, output stays English).
Deploy: `sync-cards.sh` + `/restart` all six bots (preset.txt is fleet-wide).

## 2026-07-20 — Content: Priya geography fix + Jules seed files (no bot.py change, no version bump)

From the first character-pass review (proposals in `character-review/PROPOSALS-2026-07.md`
on `claude/character-review`): the 2026-07 Austin→Bellevue relocation missed Priya's
apartment line — "small Belltown apartment" (Seattle) survived in both her description
and the Nimbus lorebook entry, contradicting CLAUDE.md, her atlas, and her Eastside
habits. Moved to "small apartment in downtown Bellevue" in both places (+ mes_example
"rent in seattle" → "rent in bellevue"). Also created `jules/` seed files
(people/projects/schedule/atlas, Bellingham-grounded — she was the only character
without any) and corrected the Bonnie personality-order note in CLAUDE.md + the
edit-cards skill, which had recorded the card's section order reversed since it was
written. Deploy: `sync-cards.sh` + `/restart` priya and jules.

## v2026-07-19.2 — Note ownership: her events no longer become the user's calendar

**Root cause (owner-reported):** bots brought up events from *their own* fictional
lives and then asked the owner "how it went" as if it were the owner's plan. Third
generation of the provenance-leak class (2026-07-10 hallucinated memories,
v2026-07-12.4 note grounding): the v2026-07-12.4 fix requires `user_note_quote` to
be a verbatim substring of the *user's* lines — a topic gate, not an ownership
gate. When the character has a scrimmage Saturday and the user replies "good luck
at the scrimmage," the user's own line states the event verbatim, the note passes
grounding legitimately, and is stored ownerless. `note_followup_job`'s trigger then
hard-codes ownership the wrong way ("{user} mentioned this — ask how it went"),
completing the flip. Every guard checked whose *mouth* the words came from; none
checked whose *life* the event belonged to.

**Fix (prompt-level, both ends of the pipe, zero new LLM calls, no new code paths):**
- Extraction (`post_reply_analysis`): `user_note` now requires the event to be part
  of the user's OWN life; the user asking about / reacting to / wishing luck on the
  character's event is explicitly null. The CRITICAL clause adds the principle:
  ownership of the event decides, not whose message mentioned it.
- Follow-up backstop (`note_followup_job` trigger): if a stored note actually
  describes the character's own event, she must not ask the user how it went — she
  tells them how it went for her instead. This degrades already-polluted notes
  gracefully instead of gaslighting the owner.
- No kill switch: pure prompt-text bugfix on existing behavior — "off" would mean
  "keep the bug." Existing polluted entries should be pruned manually via
  `/notes` + `/notes del <n>` on affected bots; the backstop covers what remains.

## v2026-07-19.1 — /fleet: Telegram-native fleet console over the admin API

**Root cause (a gap, not a bug):** fleet visibility required a shell.
`fleet-status.sh` answers "is everyone up, what version" but only from a terminal
— and the VPS migration is exactly when that answer is needed from a phone with
no SSH at hand: instances now live on two hosts, and the jules pilot's failure
mode (two hosts polling one token) is the kind of thing a glanceable per-host
view catches early. The admin API already served all the data
(`/admin/health`, `/admin/audit`); nothing consumed it from inside Telegram.

**What shipped:**
- `/fleet` (admin-gated, `_is_admin`): probes every peer in `FLEET_PEERS`
  concurrently (`asyncio.gather` over `asyncio.to_thread` — no bare `requests`
  in the async handler) and replies with one table: UP/DOWN, version, uptime,
  and `err:<n>` last-hour error count when the fleet shares one
  `ADMIN_API_TOKEN` (audit probe degrades to `?` on a token mismatch or older
  peer). DOWN is labeled as "admin API unreachable", not "bot dead" — the
  common case is `ADMIN_API_ENABLED` unset on a healthy bot.
- `FLEET_PEERS=name=port,name=host:port,…` — host defaults to localhost, so
  the same config works on-phone now and across the tailnet mid-migration.
  Parsed by pure `_fleet_parse_peers`; bad entries warn via `_CONFIG_WARNINGS`
  and are skipped (the .env-typo-must-not-brick rule, v2026-07-10.2).
- `/admin/health` now includes `instance` and `uptime_hours` (still
  unauthenticated liveness only) — `fleet-status.sh` already tried to read
  `uptime_hours` and rendered 0.0h for everyone; now it's real.
- Kill switch `FLEET_CMD` (unset = on, `0` = off) per owner policy 2026-07-18;
  feature is inert without `FLEET_PEERS` regardless. `FLEET_TIMEOUT` (default
  4s) bounds each probe. Group-safe automatically: commands in groups are
  default-deny (`GROUP_ALLOWED_COMMANDS`), untouched.

**Tests:** `TestFleetParsePeers` (5) + `TestFleetFormat` (3) in test_pure.py.

## v2026-07-18.5 — /usage speaks NanoGPT's token-based subscription shape

**Root cause:** the v2026-07-18.4 self-describing error did its job — the owner's
very next `/usage` captured the real response. NanoGPT's subscription API is no
longer daily/monthly request counts; it's **token-based**: top-level per-section
usage dicts (`weeklyInputTokens`, `dailyInputTokens`, `dailyImages`, each
`{used, remaining, percentUsed}`) keyed identically to the `limits` dict, plus
`period.currentPeriodEnd`. Jules's real numbers: 60M weekly input tokens limit,
`dailyInputTokens` limit null (= uncapped), 100 daily images.

**What shipped:** `_usage_summary` now recognizes the token shape first (sections
missing their usage dict are skipped; a null limit renders as ∞; renewal date
appended) and falls back to the legacy daily/monthly shape, else None → the
v2026-07-18.4 self-describing path. New pure `_fmt_count` humanizes counts
(60000000 → 60M, 15400 → 15.4k). The captured real body is pinned in the tests
so the next API drift fails loudly against known-good data.

**Tests:** `TestUsageSummaryTokenShape` (4, incl. the real captured body) +
`TestFmtCount` (2); legacy-shape tests unchanged and still green.

## v2026-07-18.4 — /usage no longer crashes on an unexpected API response shape

**Root cause:** `check_usage` trusted the NanoGPT subscription endpoint's response
shape — it gated on `data.get("active")` but then indexed `data["daily"]` /
`data["monthly"]` / `data["limits"]` directly. On Jules the endpoint returned
`active` truthy **without** a `daily` key (account tier or API shape change — the
crash destroyed the evidence of which), so `/usage` died with
`KeyError: 'daily'` and an `[unhandled]` traceback instead of telling anyone what
the API actually said. Same defect class as the streaming-error-body rule: an
external response consumed without validation is undiagnosable when it changes.

**What shipped:**
- New pure `_usage_summary(data)`: validates the daily/monthly/limits shape
  (returns None on mismatch), tolerates missing inner keys with `?` placeholders.
- `check_usage` now handles all three failure modes gracefully: non-JSON body
  (HTTP status to chat, body to log), inactive subscription (unchanged), and
  active-but-unrecognized shape — the reply names the keys the API returned and
  the full body goes to the log, so the *next* shape change is self-describing
  (debugging protocol #3) instead of a KeyError.
- No new env vars; bugfix to an existing command, no kill switch needed.

**Tests:** `TestUsageSummary` (5) — full shape, missing/wrong-typed sections,
missing inner keys, empty response.

## v2026-07-18.3 — Social battery + minimal-reply license + day-mood residue (ROADMAP 3.7)

**Root causes this release addresses (three related realism tells, one plumbing area):**
1. Mood tracks what she feels *about* things, but nothing tracked remaining social
   capacity — a six-hour intense conversation left her exactly as available as minute
   one. Single-axis mood can't express "great day, no energy left."
2. Every incoming message earned a full-length reply — no real person pads "k" into a
   paragraph, but the prompt never licensed anything less.
3. Her generated life (`day.txt`) never colored how she *opened* — mood changed ONLY
   through conversation (`post_reply_analysis` + gap decay in `nudge_mood`), so the
   flat tire in her day was invisible unless the user happened to ask
   (`REVIEW-YURALUME-2026-07-18.md`, the one adoption from that review).

**What shipped (zero extra LLM calls; `FATIGUE_STATE=0` / `DAY_MOOD_RESIDUE=0` kill
switches, default on):**
- **Social battery:** per-chat `fatigue` 0–100, persisted with state. Pure
  `_fatigue_update` runs inside the existing analysis worker on the valence it
  already extracts: time decay first (`FATIGUE_DECAY_PER_HOUR`, default 10), then
  |valence| ≥ 2 → +12 (intensity drains regardless of sign — a big high costs energy
  too), calm-positive → −15, else −5. Worker-thread writes go back via
  `call_soon_threadsafe`, mirroring the adjacent mood write. `[fatigue]` log line on
  threshold crossings only.
- **Read-time decay:** `_fatigue_effective` applies passive decay at prompt-assembly
  time so a long silent gap recovers her *before* the first reply of a new
  conversation, not one reply late.
- **Drained register:** above `FATIGUE_THRESHOLD` (default 70), one system line —
  shorter replies, less patience, winds the chat down; explicitly not
  BrainEngine's "ego depletion" (losing social regulation was rejected in the
  review as a liability for a long-running relationship).
- **Minimal-reply license:** when drained, mid-busy-block (3.6), or in a low mood
  (≤ −1.2), a system line makes 'k'/'lol'/an emoji a legitimate complete reply.
  Master switch is `FATIGUE_STATE`.
- **Day-mood residue:** the midnight day generator now ends with one
  `MOOD: <label> | <valence>` line. Pure `_split_opening_mood` peels it off BEFORE
  `day.txt` is written — the meta line never reaches prompts or memory — and seeds
  the owner's mood state (on-loop job, direct write is correct there). A model that
  ignores the instruction degrades to no residue that day. Provenance unaffected:
  mood is presentation state, not a fact store; the `[own-day]` rule is untouched.
- `assemble_messages` now reads `schedule.txt` once per assembly (previously the 3.6
  block re-read it); busy state is shared between the license and the schedule
  section.

**Config:** `FATIGUE_STATE`, `FATIGUE_THRESHOLD`, `FATIGUE_DECAY_PER_HOUR`,
`DAY_MOOD_RESIDUE` in `.env.example`; numerics via `_env_float`.

**Pure helpers + tests:** `_fatigue_update`, `_fatigue_effective`,
`_split_opening_mood`; `TestFatigue` (8) + `TestSplitOpeningMood` (6): drain/recharge
arithmetic, clamps, gap decay ordering, read-time decay, MOOD-line parse/strip/clamp,
mid-text immunity, graceful absence.

## v2026-07-18.2 — Schedule-driven unavailability (SCHED_BUSY; ROADMAP 3.6)

**Root cause this release addresses:** `schedule.txt` was injected into context every
turn but nothing **enforced** it behaviorally — the character read as always instantly
available, never mid-anything, never having to leave. The always-on companion is the
single biggest "puppet" tell (identified in `REVIEW-BRAINENGINE-2026-07-18.md`, the
one idea from that review worth its weight). Context alone doesn't shift register;
models treat an injected schedule as trivia unless the prompt states what it means
*right now*.

**What shipped (zero extra LLM calls):** behind `SCHED_BUSY` (default **on**, `0`
disables without redeploy):
- New pure `_parse_busy_blocks(sched_text)`: extracts `(start_min, end_min, activity)`
  from today's schedule lines carrying an **explicit** `HH:MM-HH:MM` range (hyphen/en
  dash/em dash). Deliberately conservative — loose wording ("morning shift", "gym
  later") never fires; invalid clock values and overnight ranges (end ≤ start) are
  skipped rather than guessed. `_busy_now(sched_text, now)` returns the activity the
  current time falls inside, else "".
- `assemble_messages`: when mid-block, one system line after the schedule — she's
  answering from her phone in stolen moments, shorter replies, and may say she has to
  get back to it. Logs `[sched-busy] <activity>` per assembly so over-firing is
  visible in bot.log (the ROADMAP-specified tripwire).
- Private reply path: compose delay (`_typing_delay_secs`) is multiplied by
  `SCHED_BUSY_DELAY_MULT` (default 3.0, clamped 1–10 at use) while busy. The **group
  path keeps its own timing untouched** — no group-behavior change in this release.
- Proactive sends unchanged: quiet hours + nudge budget stay authoritative; this
  feature only adds restraint, never sends.

**Config:** `SCHED_BUSY`, `SCHED_BUSY_DELAY_MULT` documented in `.env.example`.
Numeric parsing via `_env_float` (bad values warn + fall back).

**Pure helpers + tests:** `_parse_busy_blocks`, `_busy_now`; `TestBusyBlocks` (8
tests: explicit ranges, loose-wording immunity, dash variants, overnight/invalid
skip, boundary minutes, empty schedule).

## v2026-07-18.1 — Stop memory latching (MEMORY_REPEAT_SUPPRESS_TURNS)

**Root cause this release addresses:** `triggered_memories` is deterministic and
**stateless across turns** — every reply it re-scores all of `memories.txt` against the
recent conversation (keyword overlap + cosine ×3.0), sorts, and greedily fills the
300-token budget. Nothing recorded which memories were injected on prior turns, so while
a conversation stayed on one theme the *same* top-scoring lines won the budget every
single turn and the character re-told one memory endlessly, reworded each time. It's a
feedback loop: the memory she mentions lands in the recent-history scan text, which
re-ranks it to the top again next turn. The repo already solved this exact shape for
*questions* (`_recent_questions` → "don't repeat these") but had no equivalent for
memories; write-time dedup (`MEMORY_DEDUP_SIM`) only stops *storing* duplicates, not
re-injecting the same stored line.

**What shipped:** behind `MEMORY_REPEAT_SUPPRESS_TURNS` (default **6 = on**; set 0 to
disable — the first release under the new owner default-on policy, see below), per-chat
in-memory tracking of recently-injected memory lines, consumed as a score multiplier in
`triggered_memories`:
- New pure `_repeat_penalty(last_turn, current_turn, window, floor)`: full penalty
  (`MEMORY_REPEAT_PENALTY`, default 0.15) the turn right after a line is injected, fading
  linearly back to 1.0 over `window` turns. A **multiplier, never exclusion** — a memory
  the user directly asks about still outscores the penalty and surfaces.
- `triggered_memories` gains `chat_id=None`. With a `chat_id` (the live reply path) and
  the flag on, it increments a per-chat turn counter, down-weights recently-seen lines,
  and records the winners. `chat_id=None` (e.g. `/recall`) and the flag off are both
  byte-identical to old behavior, so existing callers/tests are untouched.
- Trackers (`_mem_inject_turn`, `_mem_last_injected`) are **in-memory only**, matching
  `_recent_questions` — no state-serialization changes, no cross-thread concerns; a
  restart just clears suppression (worst case: one repeated theme after a restart).
- A gated one-liner is appended to the `# Relevant memories` block telling the character
  not to re-raise a memory she's referenced recently unless the user brings it up. The
  kill switch (0) restores the exact old prompt.

**Policy change (owner, 2026-07-18):** new features now default **ON** with a mandatory
env kill switch (unset = active, `0` = off), reversing the prior default-off convention.
The kill switch is now the required safety mechanism rather than the off-by-default state.
Recorded in `CLAUDE.md`, `bot-code-invariants` #16, and `repo-change-control`. This
release is the first under it — hence `MEMORY_REPEAT_SUPPRESS_TURNS=6` by default.

**Preset (`preset.txt`, ships alongside; content, no BOT_VERSION dependency):** added a
contrastive `[ANTI-ECHO / NO REHASH]` section and inline bad→good example pairs under
several existing abstract rules (narrated emotion, narrator tipping off lies, generic
voice, repeated sensory detail, NPC servility) — bad→good pairs steer models harder than
abstract prose. Deploys via the card/seed path (`sync-cards.sh` / curl into instance
dirs), not `/update`.

**Deliberately out of scope (so it isn't re-litigated):**
- `MEMORY_DECAY_HALFLIFE_DAYS` (default 0) remains a config-only, orthogonal mitigation
  for *old* memories dominating — it does nothing about within-conversation latching,
  which is what this release fixes.
- Lore, `memory_block` facts/summaries, `user_notes`, pinned, and `day.txt` can also
  carry a latching theme but are injected wholesale (not ranked), so suppression there is
  a different mechanism — left for a future release to keep this diff minimal.

**Pure helper + tests:** `_repeat_penalty`. New `TestRepeatPenalty` and
`TestTriggeredMemoriesRepeatSuppression` (suppression rotates the winner, fades after the
window, kill switch and `chat_id=None` preserve old behavior, per-chat isolation).

## v2026-07-17.1 — Generalized map intent (MAP_INTENT; ROADMAP 3.5 phase 2)

**Root cause this release addresses:** FOOD_SUGGESTIONS (v2026-07-11.14) proved that
pre-fetching real TomTom data into the single reply stops the character inventing
places — but only for food. Asked "how far is bellevue square" or "is there a
pharmacy nearby", she still answered from imagination: fabricated minutes, distances,
and place names, exactly the hallucination class the food path closed.

**What shipped:** behind `MAP_INTENT=1` (default off; unset = prior behavior), an
explicit map-shaped ask in a 1:1 chat pre-fetches real data and injects it as the
same one-turn bracketed note the food path uses, riding the single existing reply:
- **Route asks** ("how do I get to X", "how far is (it to) X", "directions to X",
  "how long to bike/drive/walk to X", "what's the commute to X"): geocode the
  destination, route from the user's stored location with the instance's
  `TOMTOM_TRAVEL_MODE`, inject a plain `_route_brief` ("drive to X: 18 min, 7.9 mi
  (incl. +4 min traffic)") with use-ONLY-these-facts phrasing. Max 2 REST calls.
- **Nearby asks** ("is there a <thing> nearby", "any <thing> around here",
  "closest/nearest <thing>"): POI search around the user's location (5 km), injected
  via `_places_brief` (`_restaurants_brief` generalized; the old name delegates so the
  food path and its tests are untouched). 1 REST call.

**Design decisions (why, so they aren't re-litigated):**
- **Keyword regex intent, not an LLM classifier** — intent runs on every 1:1 message
  and a per-message LLM side call is banned (bot-code-invariants #3, same reason
  `_is_food_query` is a regex). The negative space is test-pinned: "how do I get to
  sleep", "how far is too far", "closest thing to heaven" etc. must never fire; a
  destination stoplist (`_MAP_DEST_REJECT`) catches figurative objects, \b-anchored
  so real places ("Knoxville") survive. Misses on creative phrasings are accepted v1
  cost, same as food.
- **Location freshness gate** (`_fresh_location`): route origins and nearby centers
  use the stored location only when <4h old (the photo path's precedent) or inside a
  live-share window — a route from last week's pin would be confidently wrong.
  Without one she nudges for a pin instead of guessing (food-path pattern).
- **Un-geocodable destinations fail honestly:** "home"/"work" geocode literally,
  usually miss, and inject a "you couldn't find it — say so, don't invent" note.
  Resolving them from her memory of the user is a deliberate follow-up
  (owner-settled 2026-07-17), as is "what's near <remote place>" — v1 nearby is
  user-location-only.
- **No cooldown/cache** (owner-approved): the precise intent gate is the budget
  control, matching how FOOD_SUGGESTIONS shipped; a `[map] intent=...` log line
  instruments the fire rate. If fleet logs show over-firing, a per-chat cooldown is
  the pre-agreed follow-up.
- Food wins when both flags fire (elif chain) — at most one injection + one TomTom
  fetch sequence per message. Group chats never reach the block (it lives in the 1:1
  `handle_message` path); `_TomTomError` anywhere degrades silently to a normal
  reply; error logging stays key-free via the existing `_tomtom_err_reason` path.

**Pure helpers + tests:** `_map_intent`, `_clean_map_dest`, `_route_brief`,
`_places_brief`, `_fresh_location`. 17 new tests; `TestRestaurantsBrief` passes
unmodified against the delegate, proving the refactor is behavior-preserving.

## v2026-07-13.2 — Error hygiene + --check-config preflight (R2+R3, operability)

Two small items from the same hardening plan as v2026-07-13.1, shipped together.

**R2 — raw exceptions no longer reach chat.** Eight handler sites sent
`❌ Something went wrong: {e}` (and variants) and the global `on_error` sent
`{type(err).__name__}: {err}` to whatever chat triggered the failure. That leaks
internals (paths, library errors, provider details) and — the sharp edge — `on_error`
would post them into a *group* chat, i.e. to every human in the pilot group. All
user-facing errors are now a fixed generic line pointing at `/errors` (admin-gated,
where the detail already lives via the existing `log.error` calls; the one site that
didn't log, the menu heartbeat button, now does). `on_error` additionally goes silent
in group chats. Kept as-is: human-authored messages ("file's too big"), and the JSON
upload parse error now shows only the structured `e.msg`/`e.lineno` from
JSONDecodeError — that's about the user's own file, not internals. Eval-pinned
(`no-exception-leak`).

**R3 — `python bot.py <dir> --check-config`.** No-network preflight for standing up
an instance: token shape, timezone actually resolving (`BOT_TIMEZONE` set but
`ZoneInfo` failing = missing tzdata, the silent naive-time failure mode), card
loaded, instance dir writable, every present state file parses as JSON (a corrupt
one means silent empty-state startup — restore from backup first), owner claimed or
not, ALLOWED_USERS empty or not, models set. Exit 0 = ready to launch. Missing
token/key/card already hard-fail at import with actionable messages, so the check
covers the failures that were previously only discoverable at 3am.

## v2026-07-13.1 — Ownership hardening: claim-once owner + private-chat gate (R1, security)

**Root cause (found while fact-checking an external review, confirmed in code):**
two authorization gaps, one severe.

1. **Ownership takeover via /start.** `set_owner` refused group ids but had no
   "already claimed" guard — it rewrote `owner_chat.txt` on every call whenever
   `OWNER_CHAT_ID` was unset. Six of its seven call sites wrapped it in
   `if get_owner() is None:`; the `/start` handler called it bare. Telegram bots are
   publicly addressable by username, so any stranger who found the bot and sent
   `/start` silently became the owner — heartbeats, note follow-ups, and every
   proactive message redirected to them, and the real owner got no signal.
2. **ALLOWED_USERS only half-enforced.** `_is_allowed` was a per-handler check that
   drifted: media/text handlers had it, `/start` and most of the ~80 commands never
   got it. With an allowlist configured, a stranger couldn't send a photo but could
   run `/notes`, `/mems`, `/settings` — and `/start`.

**Fixes (both eval-pinned, mirroring how the group boundary is protected):**
- `set_owner` claims once: first contact binds ownership, chat traffic can never
  reassign it. Deliberate transfer = edit `owner_chat.txt` on-device or set
  `OWNER_CHAT_ID` (env stays authoritative). Behavior change to know about: sending
  /start from a NEW chat no longer moves ownership there.
- `_private_gate`, a sibling of `group_guard` in handler group -1: when
  ALLOWED_USERS is set, private-chat updates from anyone else stop at one choke
  point — commands, messages, media, callbacks, and any future update type — instead
  of relying on per-handler checks (which is exactly how the gap formed). The owner
  always passes even if left out of ALLOWED_USERS (locking the owner out of their
  own fleet is worse than redundancy). Empty ALLOWED_USERS = today's open behavior;
  group chats are untouched (group_guard's jurisdiction, GROUP_CHAT_DESIGN.md).
  Existing per-handler checks stay as defense in depth.

New evals: `owner-claim-once` (set_owner keeps its guard) and
`private-gate-registered` (the gate stays wired in group -1).

## v2026-07-12.4 — User-note quality: grounding, debris sanitation, real dedup, stale-note expiry

**Root cause (owner's live user_notes.txt, reviewed 2026-07-12):** a 15-note file
where ~12 entries were garbage, four distinct failure modes visible at once:

1. **Character fiction stored as user facts** ("has a husband trapped in the bedroom
   who is confused by her performance", her own banana bread as *his* baking). The
   extraction prompt forbids this, but during roleplay scenes the analysis model does
   it anyway. This is the exact failure class as the 2026-07-10 hallucinated-memories
   bug — and the memory path got quote-grounding as its fix while **the notes path had
   no grounding check at all**.
2. **JSON debris in note text**: "mentions his upcoming DOR audit tour… (valence
   null)" — the model leaks schema fragments into the note string. Worse than
   cosmetic: a model-emitted "(due …)" would reach the follow-up parser without
   passing the caller's date validation.
3. **Dedup misses obvious duplicates**: "has a call with Yuen in eight minutes" and
   "has a 2pm call with Yuen" were both stored — the 20-char-prefix check can't see
   past a differing sentence opening.
4. **Retired notes never leave**: "(asked …)" lines linger in the prompt block every
   reply until the 15-note cap happens to evict them.

**Fixes (each with its own kill switch, unset = on):**
- `user_note_quote` added to the combined analysis JSON (zero new LLM calls); the
  note is rejected unless the quote is a verbatim substring of the user's own lines
  (reuses `_quote_grounded`). Rejections logged as `note_ungrounded`. `NOTE_GROUNDED=0`
  restores old behavior. Prompt also now demands ONE event per note (the "walk thing +
  Yuen tab" mashup).
- `_sanitize_note` strips machinery-shaped parentheticals — `(due|every|asked|noted|
  valence|mood|confidence …)` — from model-supplied note text before markers are
  appended, so stored markers are only ever written by us.
- `_note_is_dup`: legacy prefix check plus word-containment (shared tokens / smaller
  set ≥ `NOTE_DEDUP_SIM`, default 0.8; 0 = prefix-only).
- `note_followup_job` prunes `(asked …)` notes older than `NOTE_ASKED_TTL_DAYS`
  (default 7; 0 = keep forever) in its daily pass.

## v2026-07-12.3 — Recurring events from conversation actually recur (and stay in character)

**Root cause (owner-reported):** "recurring event reminders added via conversation get
logged but never come up naturally — just a regular reminder message." Recurring events
fell into a gap between three disconnected subsystems. (1) The conversation-capture
path (`post_reply_analysis`) only had a single `user_note_date` — "practice every
Thursday" captured at most the first Thursday, and after `note_followup_job` asked
about it once, the line was rewritten to `(asked …)` and retired forever. (2) The only
recurring machinery, `/setreminder`, delivers through `fire_reminder`'s literal
`⏰ Reminder: <text>` — mechanical, no character voice, no LLM involved. (3) The
natural-delivery machinery (`send_triggered`, used by cron jobs and note follow-ups)
existed but nothing recurring was ever wired into it.

**Fix — wire the existing pieces together, per the owner's chosen split:**
- `post_reply_analysis` gains a `user_note_recurring` JSON key in the same combined
  call (zero new LLM calls, per the invariant): `weekly:<day>` / `monthly:<1-31>` /
  `yearly:<MM-DD>`, null for one-offs and vague cadences.
- Recurring notes are stored as `<note> (every <rule>) (due <date>)` in
  user_notes.txt; if the model gave a rule but no date, the first due anchor is the
  next occurrence. Rules are validated by `_parse_recurrence` — anything garbled
  degrades to a one-off note rather than crashing the pass.
- `note_followup_job` (already natural, in-character, quiet-hours- and
  nudge-budget-aware) now rolls a recurring note's due date forward via
  `_next_recurrence` after asking, instead of retiring it. Next occurrence is
  computed from *today*, not the stored due date, so a note overdue by weeks (phone
  off) can't roll to a past date and refire daily while catching up. Overflow days
  clamp (monthly:31 fires Apr 30).
- **Deliberately NOT changed:** `/remindme` and `/setreminder` keep the mechanical
  `⏰` format — owner-confirmed split. Hard reminders (meds, timers) should be
  unambiguous and never lost in character flavor; only conversation-captured events
  go the natural route.
- Kill switch `NOTE_RECURRING=0` (default on — owner requested the behavior;
  disabling restores exact previous behavior: capture as one-off, `(asked …)` retire).
  Cancel a recurring note anytime with `/notes del <n>`.

## v2026-07-12.2 — Embeddings that actually recall: live semantic memory + lore, semantic dedup, eviction & provenance fixes

**Root cause (the headline):** every memory write embeds the line via a blocking
NanoGPT `/embeddings` call, but **those vectors were never read during a live reply.**
`triggered_memories` skipped semantic scoring whenever it ran on the event loop (a
guard added so the 30s blocking embed couldn't freeze the loop), and `assemble_messages`
always runs on the loop — so semantic recall only ever fired for the manual `/recall`
and `[memcheck:]` commands. Normal chat was keyword-only and the `*3.0` semantic
weight was dead code. We paid the write cost and got almost none of the read benefit.

**Live semantic recall (`MEMORY_SEMANTIC_LIVE`, default on):** the blocking query
embed is now hoisted into the async handler via a new `assemble_messages_async`
wrapper — `_embed_query_cached` runs `_embed_text` in `asyncio.to_thread` bounded by
`MEMORY_QUERY_EMBED_TIMEOUT` (3s), with a small LRU so repeated openers don't
re-embed. The vector is threaded through `assemble_messages` → `triggered_memories`,
which now ranks with a pure-cosine `_semantic_recall_vec` (no HTTP, no event-loop
skip). Keyword scoring, recency decay, hedging, and the token budget are unchanged —
they finally operate on a real semantic candidate set. On timeout/failure/disable it
degrades to exactly today's keyword-only behavior.

*Deliberate, recorded decision:* this adds **one embedding round-trip per reply** — a
per-message side call, which the bot-code-invariants caution against for phone
bandwidth. The owner accepted it explicitly: an embedding is a tiny, fast request (not
a 150s chat completion), it is cached + timeout-bounded + off-loop, and it has a
default-on kill switch (`MEMORY_SEMANTIC_LIVE=0`). It is NOT a new LLM analysis call,
so the "one combined `post_reply_analysis` call" invariant is untouched. Logged in
`.claude/memory/operational-log.md` so it isn't later flagged as a regression.

**Semantic lorebook matching:** the same per-reply vector now also powers
`triggered_lore` — non-constant lore entries are embedded once into
`lore_embeddings.json` by a startup job (`_embed_lore_job`, off-loop), and up to
`MEMORY_LORE_SEMANTIC_TOPK` (3) semantically-close entries above the 0.3 floor are
added to the keyword hits. A user paraphrasing a topic without hitting a lore keyword
now surfaces the relevant lore. No extra call — reuses the memory query vector.

**Semantic write-dedup (`MEMORY_DEDUP_SIM`, 0.92):** the lexical dedup in
`_append_memory` missed reworded duplicates ("lives in Seattle" → "moved to
Portland"). The auto path now embeds the entry once (the embed `_memory_replace`
would do anyway — passed through via `precomputed_vec`, so it is not embedded twice)
and skips it if `_is_semantic_dup` finds a near-duplicate already stored. Manual adds
and audit-merges are intentional and bypass it.

**Sidecar orphan leak fixed + confidence-aware eviction:** `MEMORIES_MAX` overflow
used a FIFO slice that dropped lines but **never popped their `memory_meta.json` /
`embeddings.json` entries** — both sidecars grew unbounded and stale meta could shadow
a new identical line. New pure `_evict_by_value` drops the lowest-value entries
(confidence, ties broken by oldest ts; legacy no-meta = neutral 5) and the caller pops
every evicted key from both sidecars — so a hand-corrected conf-10 fact now outlives a
trivial conf-3 one, and R1's "three files stay in sync" holds on the eviction path too.

**Provenance shown to the model:** `_hedge_memory_lines` now appends the recorded
source snippet to hedged (low-confidence) memories — `(unsure) <line> [you recall this
from: "<source>"]` — so the character can self-check a shaky memory against the
sentence that created it, instead of provenance being admin-only (`/sourcemem`).

27 new tests (semantic recall vec, semantic dedup, value eviction, lore semantic hits,
provenance hedge, query-embed cache, and a live-path regression proving semantic recall
now returns a hit that shares no keywords with the query).

## v2026-07-12.1 — Memory loops: weekly audit → review queue, recency decay, confidence hedging

**Root cause (all three, one theme):** the memory system had a write path with
provenance (R1) but no *loop* — nothing ever went back over what was stored.
memories.txt was append-only apart from manual `/delmem`/`/editmem`: contradictions
and superseded facts accumulated until the count cap evicted something arbitrary.
Recall ranked purely by keyword hits + cosine similarity, so a 6-month-old one-off
outranked yesterday's correction if it shared a keyword. And a low-confidence memory
the owner approved from the review queue was asserted at recall with the same
certainty as a conf-10 quote-grounded fact — the meta confidence existed but was
never consulted at injection.

**Weekly memory audit (`MEMORY_AUDIT`, off by default):** `memory_audit_job` rides
the nightly `reflection_job` and fires once a week (`MEMORY_AUDIT_WEEKDAY`): one
batched `SUMMARY_MODEL` call over memories.txt (+ age/conf annotations from
memory_meta) proposing at most `MEMORY_AUDIT_MAX_PROPOSALS` contradiction/
superseded/stale findings. Proposals land in the EXISTING `memory_review.json` →
`/reviewmem` flow as `kind: "audit"` items — the bot never deletes or merges on its
own. Approving applies delete/merge through `_memory_replace` (meta+embeddings stay
in sync; merges get `origin: audit-merge`, min-of-parents confidence, and a
`merged: a | b` source trail for `/sourcemem`); a target edited since the proposal
aborts safely ("memory changed since proposed"). Rejecting records an
order-insensitive pair key in `memory_audit_seen.json` so a declined proposal never
returns; queue-cap overflow just re-proposes next week (never evicts pending items).

**Recency decay (`MEMORY_DECAY_HALFLIFE_DAYS`, off by default, recommend 90):**
`triggered_memories` now multiplies the merged keyword+semantic score by
`_recency_weight` — exponential half-life on the memory_meta timestamp, floored at
0.1 so old memories fade in the ranking but never disappear from it. Entries with
no recorded ts (legacy, pre-meta) stay at neutral 1.0 — never punished.

**Confidence hedging (`MEMORY_HEDGE`, off by default):** at injection,
`_hedge_memory_lines` prefixes `(unsure)` on recalled memories whose meta
confidence is below `MEMORY_AUTOCONF` and appends one instruction line telling the
character to hedge rather than assert. Display-time only; the stored line is
untouched.

**Invariant compliance:** zero new per-message LLM calls (the audit is a weekly
scheduled call under `_SUMMARIZE_SEM`, via `asyncio.to_thread`); all mutations go
through the `_memory_replace` choke point behind the owner's explicit `/reviewmem
ok`; audit-merged text is labeled provenance (origin + source), honoring the
generated-content rule. Also fixed in passing: `/reviewmem ok` called
`_append_memory` directly on the event loop — `_memory_replace → _embed_memory_line`
makes a blocking HTTP call (up to 30s stall); now wrapped in `asyncio.to_thread`.

34 new tests (recency weight, hedging, audit parse/dedup/queue/apply).

## 2026-07-12 — Ops: eval-fix retry loop (Stop hook) + improvement Routine activated

Not a bot release (bot.py untouched). Two workflow loops from the AI-loops gap
analysis, `.claude/` only:

**Eval-fix retry loop (`.claude/hooks/eval-gate.sh`, new Stop hook):** the evals
could fail with nothing feeding the failure back — the delivery gate blocks once,
CI blocks on push, but no mechanism re-presented the failing output for another fix
round; a session could end its turn with red evals it caused. The new hook runs
`run-evals.sh` (+ pytest when evals are green) whenever the session has uncommitted
changes to gated surfaces, and on failure blocks turn-end with the failing lines: 3
bounded fix rounds, then one escalation block (summarize for the owner, never edit
an eval to pass), then it stands aside so the turn can always end. Counter in
gitignored `.claude/.runtime/`, keyed by session id.

**Improvement Routine activated:** CLAUDE.md described a "monthly Routine" that had
never actually been scheduled — the improvement loop existed only as prose. Created
`improvement-loop-monthly` (cron `0 9 1 * *`, fresh session per firing) and recorded
its schedule + verbatim prompt in `.claude/operating/routines.md` with a sync rule so
the live trigger can't silently drift from the repo's record.

## v2026-07-11.15 — Two niggles: command menu completeness + restart-storm false alarm

**Command autocomplete menu (`set_my_commands`):** the hand-kept menu list had drifted
from the actual handler registrations — the maps commands (`/route /nearby /place
/food`) and traffic commands (`/traffic /incidents`) were registered but absent from
the menu, so they didn't autocomplete. Added them via a testable `_build_command_menu`:
maps always (those handlers are unconditional), traffic only when `WSDOT_API_KEY` is
set (mirrors registration), payments as before.

**Restart-storm false alarm:** `_self_audit`'s "restarted Nx in the last hour —
something is killing the process" counted every `STARTUP AUDIT`, including the owner's
own `/restart` and `/update`. During ordinary maintenance (like this session's rapid
deploys) that tripped a false alarm. `_tally_unexpected_restarts` (pure, tested) now
skips any start preceded by a `[restart] requested` or `[update] …; restarting` marker,
so only real crashes/kills (SIGKILL, watchdog, battery manager) count — a graceful-stop
with no such marker (a battery-manager SIGTERM) still counts.

8 new tests.

## v2026-07-11.14 — In-character restaurant recs (release B; FOOD_SUGGESTIONS)

**What this adds (the "they recommend" layer):** with `FOOD_SUGGESTIONS=1` (+ a
TomTom key), when the user sends a food-ish message and has shared their location,
`handle_message` pre-fetches real nearby restaurants and appends them to the user
content as a bracketed note before `assemble_messages`. The character then
recommends *those real places in her own voice* — no list, no command.

**Invariant compliance (bot-code-invariants):** this rides the **single** existing
reply call — NO new per-message LLM call (#3). The TomTom fetch is off the event
loop via `asyncio.to_thread` (#8) and wrapped so a failure degrades to a normal
reply. It reuses the exact one-turn `[Note: …]` injection pattern the gap-aware and
lull-detection notes already use. Default off (#16): unset = today's behavior.

**Anti-hallucination:** the injected note says use ONLY the listed places and don't
invent restaurants. If no location is shared, a different note tells her to ask the
user to drop a pin rather than name places she can't verify.

**Pure helpers + tests:** `_is_food_query` (keyword heuristic, v1), `_restaurants_brief`
(plain prompt-format lines). 6 new tests. Trigger is keyword-based for v1 — it will
miss creative phrasings; broadening it is a future tweak.

## v2026-07-11.13 — /food: nearby restaurant recommendations (release A of 2)

**What this adds:** `/food [cuisine]` uses the user's shared GPS location to list real
nearby restaurants (name · cuisine · distance, nearest first). `/food` alone lists
restaurants generally; `/food thai` filters by cuisine. Registered unconditionally
like the other maps commands (replies "Maps aren't set up" without a key); requires a
shared location. Reuses `_fetch_tomtom_search` (5 km bias). New pure helpers
`_poi_cuisine` + `_format_restaurants`, 7 tests.

**Deliberately out of v1:** "open now". It needs opening-hours parsing + local-time
comparison, and this project has a scar from tz-aware-vs-naive `datetime` (fleet
startup crash, v2026-07-05.5) — shipping it correct is a fast follow-up, not a guess.

**This is release A of the owner's "both" choice.** Release B (ROADMAP 3.5) is the
in-character layer: when a location is shared and the user asks something food-ish,
pre-fetch nearby restaurants and inject them into the *single* reply so the character
recommends in her own voice — no extra per-message LLM call.

## v2026-07-11.12 — /update cache-busts GitHub's raw CDN

**Root cause this release addresses:** `/update` fetches `main/bot.py` from
`raw.githubusercontent.com`, which Fastly caches for ~5 min. Running `/update` right
after a push repeatedly fetched the stale prior version, matched it against the
running version, and reported "already current" — the deploy appeared stuck (cost
real time across this session's rapid releases).

**Fix:** `perform_self_update` now requests the raw URL with a unique `_cb=<ms>` query
param (Fastly keys its cache on the full URL, so a new param = cache miss = fresh
fetch) plus `Cache-Control: no-cache` / `Pragma: no-cache` headers. Verified the raw
host still serves the file with an arbitrary query param. `update-all.sh` (the shell
deploy path) still hits the plain URL — left as a follow-up.

## v2026-07-11.11 — TomTom routing: routeType "fastest" (REST spelling, not MCP "fast")

**Root cause this release addresses:** the route call sent `routeType=fast` →
TomTom "HTTP 400 — Invalid route type: [fast]" (surfaced by v.10's error-body
plumbing). `fast` is the *MCP tool's* parameter name; the raw `api.tomtom.com`
Routing REST API uses **`fastest`**. Same MCP-names-≠-REST-names trap that the
GeoJSON-vs-native response shape hit earlier — copying an MCP param value into the
REST call. Fixed to `fastest`; a test pins the REST spelling so it can't regress.

## v2026-07-11.10 — TomTom routing: no traffic= for bike/pedestrian; surface 4xx body

**Root cause this release addresses:** `/route` sent `traffic=true` on *every* route,
but TomTom's Routing API only accepts that parameter for motorized modes — so a
bicycle (Nora) or pedestrian (Priya) route came back **HTTP 400**. And v.9's key
redaction had over-corrected: it dropped TomTom's error *body*, so the 400 surfaced
as a bare "HTTP 400" with no reason.

**Fixes:**
- `_tomtom_route_params(mode)` adds `traffic=true` only for `_TOMTOM_TRAFFIC_MODES`
  (car/truck/taxi/bus/van/motorcycle); bicycle/pedestrian omit it. Fixes the 400 for
  Nora and Priya.
- `_tomtom_err_detail(resp)` extracts TomTom's human error message from the response
  body (`detailedError.message` / `error.description` / `message`) and appends it to
  HTTP-error reasons, so a 400 now reads e.g. "HTTP 400 — <TomTom's reason>". The body
  is key-free (the key is only ever in the query string, which we never log); a guard
  drops anything containing a `key=` token just in case. 6 new tests.

## v2026-07-11.9 — TomTom: honest error messages + key never logged

**Root cause this release addresses (both found during on-device rollout):**
1. The fetch helpers returned the *same* empty result for a genuine "not found" and
   for a network/HTTP failure, so `/route` reported "Couldn't find Bellevue" when the
   real cause was a **401 Unauthorized** (a placeholder key had been pasted into
   `.env`). The misleading message cost several debugging round-trips.
2. On failure the helpers logged `str(exception)`, and `requests` puts the API key in
   the query string — so the **full key was written to `bot.log`/`errors.log`** (and
   thus into any backup or pasted log). A public-repo fleet must never log secrets.

**Fixes:**
- New `_TomTomError` carries a short, **key-free** reason. Fetch helpers now raise it
  on a network/HTTP failure and return empty only for a genuine miss. Handlers reply
  "Maps lookup failed: HTTP 401 — key rejected …" / "rate limited" / "timed out" /
  "network/DNS error" instead of a misleading "Couldn't find X".
- `_tomtom_err_reason()` classifies the exception from `response.status_code` / type
  name and never includes the URL or key; the log line prints only that reason. 7 new
  tests, incl. one asserting the reason never contains `tomtom.com` or `key=`.

**Doc fix (confirmed on-device):** CLAUDE.md's instance table listed Nora's directory
as `~/telegram-bot/`, but her running instance is `~/nora-bot/` (the STARTUP AUDIT
`Instance:` line is authoritative). Corrected the table and `vault/entities/nora.md`.

## v2026-07-11.8 — TomTom observability: unsilence disabled state + audit visibility

**Root cause this release addresses:** v.7 registered `/route /nearby /place` only
when `TOMTOM_API_KEY` was present (the WSDOT pattern). When the key wasn't loaded,
the commands weren't registered, so Telegram returned **no reply at all** — an
undiagnosable silence. During rollout this made "is the key actually loaded?"
impossible to answer from the user side (the bot exposed no TomTom state anywhere),
which cost several debugging round-trips.

**Fixes (observability, no behavior change when a key is set):**
- `/route /nearby /place` are now registered **unconditionally**; with no key they
  reply "Maps aren't set up (TOMTOM_API_KEY missing)." instead of going silent.
- The `STARTUP AUDIT` log line now includes `Maps: <mode>|off`, so a restart shows
  whether the running process actually loaded the key (and which travel mode).
- `/audit` and `gather_audit_data()` now report `Maps (TomTom): <mode>|off`.

This is the repo's "opaque error → instrument first" rule applied: make the failure
self-describing rather than guess at it from outside.

## v2026-07-11.7 — TomTom Maps: /route, /nearby, /place (gated, default off)

**Root cause this release addresses:** three characters are grounded in real
geography (Nora bikes Seattle, Emily does western-WA traffic, Priya references real
Bellevue/Eastside places) but the bot had no way to answer routing, travel-time, or
"what's near me" questions with real data — only WSDOT incident feeds for Emily.

**What shipped (slash commands, phase 1 of 2):** three user-initiated commands,
registered only when `TOMTOM_API_KEY` is set (fail-closed, same gate shape as WSDOT):
- `/route <from> to <dest>` — geocodes both endpoints, then a traffic-aware TomTom
  route; reports ETA + distance (+ traffic delay when ≥1 min). Travel mode is
  per-instance via `TOMTOM_TRAVEL_MODE` (validated; bad value warns → car).
- `/nearby <thing>` — POI search around the user's shared location, distance-sorted.
- `/place <name>` — geocode/business lookup, location-biased when a location is shared.

**Architecture notes:** bot.py calls the raw `api.tomtom.com` REST endpoints (native
JSON), not the GeoJSON the Claude MCP connector returns — so each bot needs its own
key (documented in `.env.example`). All parsers are defensive/total (deep `.get()`
chains; a response-shape change degrades to a message, never a crash), mirroring the
WSDOT integration's discipline. Network fetches run via `asyncio.to_thread`; no new
per-message LLM calls, no new processes. Pure parsers/formatters covered by 25 new
tests; live REST round-trip is verified on-device (needs a real key).

**Deferred to phase 2 (owner-approved "both, slash first"):** an in-character layer
that lets Nora/Emily/Priya weave map data into conversation via a taught intent tag
(like `[search:]`), rather than only explicit commands. Tracked in ROADMAP 3.5.

## v2026-07-11.6 — R6 evolution experiments (all gated, default off)

**Root cause this release addresses:** the bot had no mechanism for users to
signal approval/disapproval of individual messages without typing, no derived
measure of relationship depth to modulate system behavior, `next_goals` was a
single string that couldn't track parallel conversation threads, and humorous
callbacks couldn't be surfaced for curation without a dedicated LLM call.

**Reaction feedback (`FEEDBACK_REACTIONS=1`):** registers PTB
`MessageReactionHandler`; 👍/👎 on bot messages → bounded per-chat `feedback_log`
(capped 50) + ±0.3 mood nudge. 👎 also injects a one-turn recalibration note
into the next reply prompt. `allowed_updates` extended to include
`message_reaction` only when the flag is on.

**Closeness score (`CLOSENESS_ENABLED=1`):** pure `_compute_closeness(days_active,
message_count, milestones_count, beliefs_count)` → (float 0-1, bucket). Buckets:
"getting to know each other" / "comfortable" / "deeply familiar". Recomputed
daily at midnight rotation; shown in `/status`; injected as a one-line system
note in `assemble_messages`. Five new tests pin the formula.

**Open threads (`THREADS_ENABLED=1`):** migrates `next_goals` str → per-chat
`open_threads` list (capped 3) on load. `post_reply_analysis` JSON gains
`"thread_update"` (add/resolved). Prompt block "Open threads between you two"
replaces the single next-goal line. When THREADS_ENABLED is off, existing
next_goals behavior is unchanged.

**Auto inside-joke candidates (`JOKE_CANDIDATES=1`):** `post_reply_analysis` JSON
gains `"joke_candidate"` ({phrase, meaning, tone} | null). Candidates go to the
existing `/reviewmem` queue — never auto-added to jokes.json.

All four features default off and have zero per-message LLM cost (reactions are
local, closeness is a formula, threads/jokes piggyback on the existing
post-reply analysis call that already runs).

## v2026-07-11.5 — R5 UX: status tail & recurring quiet windows

**Root cause this release addresses:** `/status` gave no visibility into what was
just said (you had to scroll up), and suppressing proactive messages on a schedule
(e.g. every Friday night) required remembering to `/quiet` each week.

**/status tail:** appends the last 3 conversation messages, speaker-labeled and
truncated to ~80 chars each, so you can see the recent thread at a glance.

**Recurring quiet windows (`/quietwin`):** three subcommands:
- `/quietwin add Fri 23:00-08:00` — adds a weekly quiet window (midnight crossing
  supported: start > end spans into the next day).
- `/quietwin list` — shows numbered list.
- `/quietwin del 2` — removes by index.

Per-chat state `quiet_windows` (list of `{dow, start, end}`). Checked via pure
predicate `_in_quiet_window(now, windows)` in the same proactive gates as
`quiet_until` (heartbeat and note-followup jobs). Twelve new tests cover midnight
crossing, wrong day, boundary minutes, and multiple windows. `/status` also shows
active quiet windows inline.

## v2026-07-11.4 — R4 prompt hygiene & safety

**Root cause this release addresses:** long conversations could silently exceed the
model's effective context window (no trimming), `triggered_lore` returned duplicate
entries when multiple keys in the same lorebook entry matched, models occasionally
broke character with "as an AI" responses that reached the user unfiltered, and
multi-chat summarization bursts could stack bandwidth-heavy LLM calls on the phone
simultaneously.

**Token-budget trimming:** new pure function `_trim_history_to_budget(messages,
budget)` drops oldest non-system, non-final-user messages until the estimated token
count is under `CONTEXT_TOKEN_BUDGET` (env, default 0 = disabled; recommended 24000).
Called at the end of `assemble_messages`. Logs when it trims.

**Lore dedupe:** `triggered_lore` now uses a `seen` set on entry content — duplicate
content from multiple matching keys in the same entry is suppressed.

**Persona-break guardrail:** regex catches first-person AI admissions (`I'm an AI`,
`as an AI language model`, `large language model`, `I don't have feelings/a body/
personal experiences`). Applied in `_deliver` and `send_triggered` on the final
`clean` text: offending sentence is stripped, counted as `persona_break` (visible in
`/audit`). Third-person references ("my AI coworker") pass through (first-person
pattern required). Empty result after strip = nothing sent (no auto-regenerate).

**Summarization semaphore:** `_SUMMARIZE_SEM = asyncio.Semaphore(1)` serializes
summarization across chats in `maintain_memory` and `maintain_long_term_memory` —
prevents multi-chat bursts from stacking on phone bandwidth. Per-chat overlap was
already prevented by the `summarizing` set.

**/start full:** `/start full` wipes conversation history AND all per-chat memory
(summaries, facts, recent_summaries, recent_facts, milestones, pinned, moods,
beliefs) after an inline-button confirmation. Character-level memories
(memories.txt) are untouched. Normal `/start` behavior unchanged.

## v2026-07-11.3 — R3 observability & robustness

**Root cause this release addresses:** restart-storm triage lost its own evidence
because `_error_counts` was memory-only (wiped on every restart). Bad `.env` values
were warned only to the log file nobody checks from Telegram. Small-file saves
(jokes, reminders, cron, payments, wardrobe) used non-atomic writes that could
truncate on a process death. `/update` and `/restart` could cut a reply mid-stream
because there was no drain. And there was no visibility into LLM call volume.

**Persist `_error_counts`:** error history now survives restarts — serialized into
`state.json` alongside `_llm_stats`. Restart-storm triage from `/audit` no longer
loses the evidence it was generated to show.

**Config warnings surfaced:** `_env_int`/`_env_float`/`_parse_id_set` now collect
warnings into `_CONFIG_WARNINGS` (in addition to logging). `/audit` shows count + first
3 warnings. All warnings also log at startup in one consolidated message.

**Atomic small-file writes:** new `_atomic_write_text(path, text)` helper (tmp +
`os.replace`) used by `save_jokes`, `save_reminders`, `save_cron_jobs`,
`save_payments`, `save_wardrobe`. A death mid-write no longer truncates these files.

**Graceful drain on /restart and /update:** `_schedule_exit` now waits up to 5s for
`_replies_in_flight == 0` before writing state and exiting. Replies in progress
complete rather than being cut mid-stream.

**LLM usage counters in /audit:** module dict `_llm_stats` tracks daily calls and
estimated token counts (via `_est_tokens`). Bumped in `call_nanogpt` on every
successful call. Persisted in state, resets on date change. `/audit` shows:
`LLM today: N calls, ~Xk in / ~Yk out (est)`.

**Prune `_last_request`:** `_self_audit` (every 30 min) now drops entries older than
1h from the rate-limit dict, preventing unbounded growth in long-running instances
with many unique users.

## v2026-07-11.2 — R2 availability awareness: /away, /back, remote-default framing

**Root cause this release addresses:** characters would "walk over to you" or describe
being in the same room during normal texting — there was no framing that the
conversation is remote by default. Proactive messages (heartbeats, note follow-ups,
traffic alerts) also had no way to be suppressed when the user is driving, in a
meeting, or otherwise unavailable without using the heavier /quiet command.

**Remote-default framing:** `assemble_messages` now injects a system note when
`active_vibe` is not `"in-person"`: "You and {user} are texting from different places —
you're not physically together unless the scene explicitly says so." Kills the class of
roleplay slips where the character describes physical proximity during texting.

**/away and /back commands:** new `away` state dict persisted in state.json. `/away
driving` or `/away meeting until 3` stores the reason verbatim and suppresses all
proactives (heartbeat, note follow-ups, traffic alerts). `/back` clears it manually.
Any incoming text message auto-clears away status (they're back by definition) and
injects a one-turn "just got back from: {reason}" prompt note so the character can
acknowledge naturally.

**Auto-extraction from conversation:** `post_reply_analysis` JSON schema gains an
`"availability"` field (`"driving"|"working"|"busy"|null`). When the user explicitly
states availability (e.g. "gotta drive, ttyl"), away is set automatically with
`origin: auto` and a configurable `AWAY_AUTO_HOURS` (default 3h) expiry as a
belt-and-suspenders against stuck flags.

**New vibe presets:** `busy`, `working`, `driving` — shorter replies, no long questions,
low-demand register. `driving` is ultra-short and non-initiating.

**Away in /status and /audit:** `/status` shows current away state with reason, duration,
origin, and expiry. `/audit` includes `away_users` in its data.

## v2026-07-11.1 — R1 memory auditor: source-attached memories, quote grounding, review queue

**Root cause this release addresses:** the 2026-07-10 audit found that auto-extracted
memories had no provenance — no way to know where a memory came from, no mechanical
check that the extraction was grounded in what the user actually said, no way to
correct a bad memory from Telegram in under a minute. This release makes every memory
traceable, every extraction grounded, and every correction fast.

**Source-attached memories:** new sidecar `memory_meta.json` stores provenance for each
memory line: timestamp, chat_id, origin (`auto`/`manual`/`manual-edit`), confidence
(1-10), and the verbatim source quote from the user's message. New `_memory_replace`
helper is the single choke point for all memory mutations (add/edit/delete) — keeps
`memories.txt`, `embeddings.json`, and `memory_meta.json` in sync. `/delmem` migrated
to use it. `/sourcemem <n>` shows stored provenance; pre-2026-07 memories show a
"no source recorded" fallback.

**Quote grounding (anti-hallucination, mechanical not prompt-hope):** the post-reply
analysis LLM call now returns `memory_quote` (verbatim substring from the user's
messages) and `memory_confidence` (1-10). Code-side validation requires the quote to be
a case/whitespace-normalized substring of the user's actual lines — if it fails, the
memory is rejected and counted as `memory_ungrounded` (visible in `/errors`/`/audit`).
Pure function `_quote_grounded` with tests (exact match, case tolerance, fabricated
quote rejection, empty inputs).

**Confidence + review queue:** memories with confidence >= `MEMORY_AUTOCONF` (env,
default 7) AND grounded are stored directly. Grounded but lower-confidence memories go
to `memory_review.json` instead (capped at 20, oldest dropped). `/reviewmem` lists
pending with confidence + source; `/reviewmem ok <n>` promotes, `/reviewmem no <n>`
drops. `/audit` shows count when nonzero.

**Correction flow (`[memcheck:]` tag):** new capability tag taught to the character:
when the user disputes a memory ("that never happened"), include
`[memcheck: what's disputed]`. Tag handling runs existing recall machinery (keyword +
semantic) over the query, DMs the numbered hits with their sources and exact fix
commands (`/delmem N`, `/editmem N <text>`). Handled via separate regex in `_deliver`
only — the `extract_tags` 4-tuple contract is untouched.

**`/editmem <n> <new text>`:** replaces a memory line through `_memory_replace`
(re-embeds, moves meta with `origin: "manual-edit"`, preserves original source).

**Memory audit log:** `memory_log.txt` (append-only) records every mutation:
`ADD auto/manual`, `EDIT`, `DEL`, `REVIEW-OK`, `REVIEW-NO`, `REVIEW-DROP`,
`REVIEW-QUEUE`, `MEMCHECK`. Trims to 500 lines when >1000.

New tests: `TestQuoteGrounded` (9 cases), `TestMemoryReplace` (4 cases). Total test
count: 108 (was 95).

## v2026-07-10.2 — audit release: memory hallucination + tool-call leak + concurrency fixes

Triggered by two user-observed symptoms plus an external (Deepseek) audit of bot.py.
Every audit claim was verified against the code before being fixed — 10 of 15 confirmed,
4 false, 1 by-design. Full triage in `AUDIT-2026-07-10.md`.

**Heartbeat memory hallucination (root cause):** `_rotate_day_context` archived each
day's `day.txt` — the character's own GENERATED fiction — into `recent_facts[owner]` as
a plain `"[Jul 09] …"` fact. `memory_block` rendered it under "Recent specifics" (read
by the model as real shared history), weekly promotion folded it into permanent
long-term facts, and `_todays_memory_note` could flag her own archive as "a significant
date". Fix: own-day provenance tag (`[own-day …]`) honored by every consumer — separate
clearly-framed prompt section, never LLM-merged into user facts, never promoted, skipped
by the date scan, capped at `OWN_DAYS_KEPT=5`; `load_state` migrates legacy entries
(sparing `[… ] Voice note:` user content). Extraction prompt also tightened: notes and
memories only from what the USER said.

**Raw `<tool_call>` XML sent to the user (root cause):** models taught the bracket
`[search: …]` tag sometimes emit the intent in their NATIVE function-call XML instead;
nothing anywhere parsed or stripped that syntax, so it sailed through to Telegram.
Fix: `_strip_native_tool_calls` at the model-output choke point (both `_do_request`
return paths, including the `reasoning_content` fallback, itself a leak vector) —
search-like calls become `[search: q]` so `maybe_search` still runs; others stripped.

**Concurrency (audit-confirmed):** state serialization now always happens on the event
loop (worker-thread saves hand off via `call_soon_threadsafe`; only the file write runs
in a thread) — the old path iterated ~28 live dicts cross-thread (`RuntimeError: dict
changed size during iteration`). Post-reply analysis snapshots the history tail on the
loop. Voice/video transcription and `/usage` no longer run bare synchronous `requests`
calls on the event loop (each froze every chat for up to 60s). `_error_counts`
iteration snapshotted.

**Smaller confirmed bugs:** `ALLOWED_USERS`/`GROUP_ALLOWED_CHATS` no longer crash the
import on malformed ids (`--123`); schedule day-headings require the first word to BE a
day name ("money" is not Monday, "wedding" is not Wednesday); `_extract_json` recovers
the first balanced object when a stray brace follows; `get_owner` warns loudly on a
non-numeric `OWNER_CHAT_ID`; `/backup` skips files that vanish mid-run; all 64
`int()/float()` env parses fall back to defaults with a warning instead of
crash-looping the bot on a typo'd `.env`; deleted 13 lines of unreachable dead code in
`_weather_camera_pool`.

## v2026-07-10.1 — group chat prototype (GROUP_MODE, Priya + Jules pilot)

**Group chat / bot-to-bot (ROADMAP 3.4):** two character bots + one human in one
Telegram group, behind `GROUP_MODE=1` + `GROUP_ALLOWED_CHATS` on the pilot instances
only. Full design + rationale in `GROUP_CHAT_DESIGN.md` — it survived four rounds of
adversarial-critic review before any of this code was written, and the review caught
real bugs (a poll/live double-answer race, a chain-cap race, and two rounds of missed
flat-file write paths), so read it before touching this feature.

**The platform fact everything is built around:** Telegram never delivers one bot's
messages to another bot (API-level anti-loop policy, regardless of privacy mode).
Bot-to-bot therefore flows through a shared ledger file (`group_<chat_id>.jsonl`
alongside bot.py, same cross-instance pattern as world.txt): each bot appends what it
posts, a 5s poll job reads what peers said. Human messages arrive live via Telegram
(privacy mode must be DISABLED via BotFather for the pilot bots) and are never acted
on from the ledger — acting on both would double-answer every addressed message.

- **Turn-taking:** addressed messages (@mention / first name on word boundary / reply
  to own message) answered deterministically; unaddressed ones through an atomic claim
  file (`O_CREAT|O_EXCL`) so exactly one bot answers, with a jittered delay biased
  toward alternation.
- **Loop prevention, layered:** every reply to a bot message needs the claim (even
  when addressed by name — the LLM's favorite register is exactly the loop risk);
  chain cap `GROUP_BOT_CHAIN_MAX=2` re-checked under the ledger lock right before
  send (generated reply discarded if the chain filled meanwhile); 20s send throttle;
  30/day bot-to-bot budget.
- **Fleet-wide fail-closed (deliberate behavior change):** group chats are ignored by
  every instance unless GROUP_MODE + allowlist say otherwise, and ALL commands except
  `/chatid` are refused in any group via a single TypeHandler choke point (group -1).
  Previously any bot added to a random group would execute `/note`, `/backup`, etc.
  there — same latent-bug class as `set_owner` being claimable by a group, which is
  also fixed (central guard: negative chat_ids can never become the proactive owner).
- **Memory read-only in groups:** group prompts read the character's life (memories,
  people, projects, day/world context) but never `user_notes.txt` or inside jokes
  (private 1:1 state); nothing in a group writes any flat file — `_group_deliver` is
  allowlist-built (no post_reply_analysis, no joke tracking, no TTS/selfie/meme) and
  the command guard blocks the manual paths. Two new evals pin this boundary in CI
  (`group-deliver-clean`, `group-cmd-allowlist`).
- **Cost:** ≤2 chat-model calls per human message fleet-wide + amortized summarization
  (groups summarize half as often); zero side calls in groups.
- **Ops:** `python bot.py <dir> --claim-test` smoke-tests both atomicity primitives
  on-device; `/audit` shows ledger size, budget, and chain state per group; new error
  categories `group_ledger` / `group_claim`.

## v2026-07-07.2 — repair server-side mojibake from NanoGPT SSE

**Root cause:** The encoding issue was never on our side. NanoGPT's SSE infrastructure
decodes model output (UTF-8) as Latin-1 and re-encodes to UTF-8 before sending. By the
time the bytes reach our socket, they already spell `â€™` instead of `'`. Our previous
fixes (v2026-07-06.1 `resp.encoding`, v2026-07-07.1 manual `.decode("utf-8")`) correctly
decoded the wire bytes — but those bytes were already wrong.

**Fix:** `_fix_mojibake(text)` reverses the Latin-1 misinterpretation:
`text.encode("latin-1").decode("utf-8")`. If the text is clean (no mojibake), the
encode step either round-trips harmlessly or raises `UnicodeEncodeError` (characters
above U+00FF can't encode to Latin-1), in which case we keep the original. Applied to
both streaming and non-streaming return paths in `_do_request`.

## v2026-07-07.1 — fix SSE mojibake for real (manual UTF-8 decode)

**Root cause:** The v2026-07-06.1 fix (`resp.encoding = "utf-8"`) relied on `requests`'
`iter_lines(decode_unicode=True)` honoring the encoding override. On the phone's
`requests` version it didn't — the response was still decoded as Latin-1, producing
double-mojibake (`Ã¢ÂÂ` instead of `'`) as the already-garbled text was re-encoded
through another layer.

**Fix:** Drop `decode_unicode=True` entirely. Call `resp.iter_lines()` to get raw bytes,
then decode each line explicitly with `raw.decode("utf-8", errors="replace")`. This
bypasses `requests`' encoding detection completely — no Content-Type header, no
`apparent_encoding`, no library version variance. The bytes come from the socket and we
decode them ourselves.

## v2026-07-06.5 — semantic memory recall via NanoGPT embeddings

**Semantic recall (ROADMAP 3.3):** memory retrieval now supplements keyword matching with
cosine-similarity search over NanoGPT embeddings (`text-embedding-3-small` by default,
configurable via `EMBEDDING_MODEL`).

- **On memory write:** `_append_memory` embeds the new line and caches the vector in
  `embeddings.json` (sidecar to `memories.txt`). One API call per new memory.
- **On context assembly:** `triggered_memories` merges keyword hits (existing behavior) with
  semantic matches (cosine top-k, threshold 0.3). Scores are summed so a line that matches
  both keyword AND meaning ranks highest.
- **On /recall:** semantic results (with similarity percentage) appear alongside keyword
  hits, so paraphrased queries ("remember when we talked about my sister's wedding?")
  work even when the stored fact uses different words.
- **Fallback:** any embedding API failure falls back silently to keyword-only — the
  feature is additive, never subtractive.

## v2026-07-06.4 — shared world context, test suite, new-bot bootstrap

**Shared world context (ROADMAP 3.2):** all six characters now share the same weather
and ambient happenings each day. The designated world-generator instance
(`WORLD_GENERATOR=1`, typically nora) writes `world.txt` at midnight — a 2-3 line shared
backdrop (weather mood, local color). Every instance's `_generate_daily_events` reads it
as context, so Nora's rainstorm is also Priya's rainstorm. Degrades gracefully: if the
file is absent (generator not configured, or it failed), behavior is unchanged from
before — each instance generates its own weather independently.

**Test suite (ROADMAP 2.1):** `tests/test_pure.py` (pytest) covering the pure functions
where a regression is fleet-breaking: `extract_tags` (4-tuple contract), `parse_cron_schedule`/
`describe_cron_schedule` (roundtrip), `_extract_json` (prose/fence extraction), `parse_when`
(reminder time parsing), `_est_tokens`, `_count_error` cap. 41 tests. CI workflow updated
to run pytest after the eval suite. Fixture in `conftest.py` stands up a temporary instance
directory with a minimal `.env` and character card so bot.py imports cleanly.

**new-bot.sh (ROADMAP 2.2):** interactive bootstrap script for new instances — creates the
directory, prompts for tokens/models, pulls the card and seed files, starts the bot. A
seventh instance can be stood up in under five minutes.

## v2026-07-06.3 — voice reply symmetry + degradation alerts

**Voice symmetry (ROADMAP 3.1):** sending a voice note to a bot with `/voice` on now
biases toward replying in kind — `VOICE_REPLY_TO_VOICE` (default 0.9) replaces the
ambient `TTS_CHANCE` (default 0.3) when the incoming message is a voice note.
Implementation: `_deliver` gains a `voice_input` flag; `handle_voice` sets it; the
TTS probability check picks the higher value. Text messages are unaffected.

**Degradation alerts (ROADMAP 1.4):** `_self_audit` now watches two new signals:
- *Fallback rate*: a new `"fallback"` error category is incremented each time
  `call_nanogpt` falls from the primary model to `FALLBACK_MODEL` (budget exceeded or
  retries exhausted). If fallback fires ≥3 times in the last hour, the owner gets a DM
  (2h cooldown, same pattern as restart-storm alerts).
- *Monthly spend*: if `USAGE_BUDGET_MONTHLY` is set in `.env`, `_self_audit` hits the
  NanoGPT subscription/usage API every 30 min and DMs the owner at 80% and 100% of
  budget (24h cooldown). Inert when unset.

Also in this release: `watchdog.sh`, `fleet-status.sh`, `sync-cards.sh` committed to the
repo (ROADMAP 1.1, 1.3, 2.3 — shell scripts only, no bot.py change for those).

## v2026-07-06.2 — fix selfie crash when no base PNG (NanoGPT path)

**Root cause:** `_generate_selfie_nanogpt` unconditionally called `_base_data_url()`,
which reads `SELFIE_BASE` (e.g. `priya_base.png`) from disk. If no base image exists
but an `appearance.txt` does, `selfie_ready()` returns True (text-only generation is
fine), and `build_selfie_prompt` correctly takes the text-only branch — but then
`_generate_selfie_nanogpt` crashes with `FileNotFoundError` because it never checked
`_has_base_image()` first. The Gemini path already had this guard (line 2778); the
NanoGPT path was missing it.

**Fix:** Only include `imageDataUrl` in the NanoGPT payload when `_has_base_image()`
is True, matching the Gemini path's behavior.

## v2026-07-06.1 — fix UTF-8 mojibake + suppress "almost did X" model tic

**Mojibake root cause:** `requests`' `iter_lines(decode_unicode=True)` uses the response's
`Content-Type` charset to decode bytes. NanoGPT's SSE endpoint returns
`text/event-stream` without an explicit `charset=utf-8`, so `requests` falls back to
ISO-8859-1 (the HTTP/1.1 default for `text/*`). Any multi-byte UTF-8 character — curly
quotes, em dashes, accented letters — gets decoded as Latin-1 garbage (e.g. `'` →
`â€™`). Always latent, but never triggered until GLM 5.2 started using smart
punctuation instead of ASCII apostrophes.

**Mojibake fix:** Force `resp.encoding = "utf-8"` on the streaming response before
`iter_lines(decode_unicode=True)` in `_do_request`.

**"Almost texted you" tic:** GLM 5.2 heavily favors narrating actions it almost took
("almost texted you," "I deleted a whole argument," "was going to send you this") as a
low-effort way to perform emotional attachment. Added a rule to the default texting style
calling this out — either do it or don't mention it.

## 2026-07-06 — ops tooling: fleet backup script, CI evals, secret scan (no bot.py change)

**Not a bot release — no BOT_VERSION bump.** (New heading convention, enforced by the
`version-changelog-sync` eval: only actual bot.py releases get `## v<version>` headings,
which must match `BOT_VERSION`; ops/docs entries use dated headings like this one.)

- **`backup-all.sh`**: nightly-cronable fleet state backup. Motivation: all character
  memory/state lives on one phone; `/backup` is manual and per-bot, so a dead phone
  meant losing everything. Archives each instance's state files (same list as `/backup`,
  `.env` always excluded) to `~/storage/shared/bot-backups/` (survives Termux
  uninstall), prunes after 14 days, optional `BACKUP_RCLONE_REMOTE` for off-phone push.
  Like `watchdog.sh` it must be curl-installed once and is not touched by
  `update-all.sh`. Setup instructions in the script header and `OPS_MANUAL.md`.
- **CI** (`.github/workflows/evals.yml`): runs `.claude/evals/run-evals.sh` on every
  push to `main`/`claude/**` and on PRs. Rationale: bots deploy by curling raw files
  from `main`, and session-side checks only run when a session runs them — a web-UI
  edit or phone push had no gate at all before this.
- **Two new evals**: `secret-scan` (token-shaped strings in tracked files — Telegram
  bot tokens, sk- keys, AWS key IDs; this repo is pulled over public raw URLs, so a
  committed token is instantly public) and `version-changelog-sync` (BOT_VERSION must
  equal the newest `## v` changelog heading — the delivery gate checks both changed,
  but not that they agree). Both break-it tested.

## v2026-07-05.12 — admin HTTP API (Phase 1 of VPS migration)

**New capability, not a bug fix.** Adds an opt-in HTTP admin API that mirrors
`/audit /errors /backup /update /restart` for non-Telegram clients — the motivating
case is a future native Android control-panel app, which can't just be a second
Telegram client (only one process can poll a bot token for updates at a time, and
there's no way to route a "send as the user" reply back to a second client via the
Bot API). Fully inert unless `ADMIN_API_ENABLED=1` is set — existing Termux instances
that never set it are unaffected.

Refactored `audit_cmd`/`errors_cmd`/`update_cmd`/`_send_backup` so their logic lives in
plain functions (`gather_audit_data`, `tail_error_lines`, `backup_file_list`,
`build_backup_zip`, `perform_self_update`) called by both the Telegram handler and the
matching HTTP route — no duplicated logic, and the Telegram-facing output text/format
is unchanged.

`/update` and `/restart`'s old pattern — reply, `_write_state()`, immediate
`os._exit(0)` — doesn't hold for HTTP: `ThreadingHTTPServer` writes its response on the
same thread handling the request, so an immediate exit right after building the
response risks killing the process before those bytes reach the socket (the caller
would see a connection reset instead of the 200 they were just sent). New
`_schedule_exit()` helper fires `os._exit(0)` from a `threading.Timer` after a short
delay instead, used by `/update`, `/restart`, and the matching `/admin/update`,
`/admin/restart` HTTP routes. `threading.Timer` runs on its own thread regardless of
caller, so this works uniformly from both the asyncio event loop thread (Telegram
handlers) and an admin API request-handling thread.

Auth: every route except `GET /admin/health` requires `Authorization: Bearer
<ADMIN_API_TOKEN>`, compared with `secrets.compare_digest`. `/admin/health` is
deliberately unauthenticated (trivial liveness ping, no sensitive data) so uptime
monitors and the future app's connectivity check don't need the token wired in.
`ADMIN_API_BIND` defaults to `127.0.0.1` (fails closed) — set it to the host's
Tailscale IP to actually expose it over the private tailnet; never bind `0.0.0.0`.

Also new: `telegram-companion-bot/deploy/bot@.service` (systemd template unit,
`Restart=always`, `RestartSec=2`) and `deploy/install-vps.sh` (idempotent VPS
installer — clones/pulls the repo, builds the venv from `requirements.txt` as the
single source of truth, prompts per-instance for tokens, installs the systemd unit,
prints Tailscale setup instructions). Confirmed `_PID_FILE`'s stale-lock detection
(`os.kill(pid, 0)`) and `os._exit(0)` are already compatible with `Restart=always` as-is
— `RestartSec=2` exists specifically to make PID-reuse races between an old exiting
process and systemd's relaunch practically impossible, not to work around a new bug.

## v2026-07-05.11 — meme generation (`/meme` + `[meme:]` tag)

**New feature, not a bug fix.** Bots can now make and send a meme via `/meme [hint]`,
or decide to send one unprompted mid-conversation via a `[meme: top | bottom]` tag —
mirrors exactly how `/selfie`/`[selfie: hint]` already work (same tag-parsing pattern
in `extract_tags`, same `_deliver`/`send_triggered` wiring, same `_is_allowed` gating,
same `_keep_uploading`/`BytesIO`/`send_photo` send path).

**Deliberate design choice:** memes are template images + Pillow text overlay, not
AI-generated. AI image models render text unreliably (garbled/misspelled captions),
which defeats the entire point of a meme — the caption *is* the joke. Templates
(`meme_templates/*.jpg`) and the font (`fonts/Anton-Regular.ttf`, OFL-licensed) are
shared assets alongside `bot.py`, not per-instance, and not part of `update-all.sh`'s
routine pull — see `SETUP_GUIDE.md` Step 8 for the one-time fetch.

New: `meme_ready`/`_pick_meme_template` (with per-chat dedup, mirrors
`_recent_selfie_hints`)/`render_meme` (word-wrap + auto-shrink-to-fit + stroked text)/
`_generate_meme_captions` (one LLM call, JSON `{"top", "bottom"}`, reuses the existing
`_extract_json` helper)/`send_meme`/`meme_cmd`. `extract_tags` now returns a 4-tuple
(`clean_text, reaction, selfie_hint, meme_caption`) instead of 3 — both call sites
(`_deliver`, `send_triggered`) updated; verified via isolated extraction tests since a
mismatch here would break every message, not just meme ones.

New dependency: `Pillow>=10.0,<11.0`. Termux install can be flaky — see the Termux
quirks note in `CLAUDE.md` for the `pkg install python-pillow` + `--system-site-packages`
fallback if a source build fails.

BOT_VERSION 2026-07-05.11.

## v2026-07-05.10 — repo cleanup: dead launchers, stale docs, Priya's real location

**Not a bug fix — a documentation/hygiene pass**, prompted by finding that several files
in the repo hadn't been touched since before this project's reliability work (this
session, v2026-07-05.1 through .9) and had drifted into actively misleading territory:

- `run.sh` and `start-bots.sh` both still launched with bare `python` (no supervisor,
  no crash recovery) — the exact `ModuleNotFoundError` crash-loop bug already fixed in
  `run-bot.sh`. Deleted both; `run-bot.sh` (with no folder argument) and `update-all.sh`
  already cover everything they did.
- `PROJECT_CONTEXT.md`/`PROJECT_INSTRUCTIONS.md` were snapshot docs from an earlier,
  now-superseded session — wrong instance list, a stale git branch reference, "as of
  last session" state. Fully superseded by `CLAUDE.md` + this changelog. Deleted rather
  than left to be trusted over the real docs by mistake.
- `Dockerfile`/`docker-compose.yml` were incomplete (no multi-instance/`BOT_HOME`
  support, single hardcoded `CMD`) and unreferenced by `CLAUDE.md` — this project is
  Termux-first and the Docker path was never actually wired up. Removed; `requirements.txt`
  is now the single source of truth for pip installs (`SETUP_GUIDE.md`, `CLAUDE.md`'s venv
  rebuild recipe) instead of being duplicated inline in three places, which is exactly
  the kind of drift that caused the missing-`tzdata` bug in v2026-07-05.5.
- `SETUP_GUIDE.md` told users to set `NANOGPT_BASE_URL` — the actual code reads
  `NANOGPT_BASE`; the wrong name would silently do nothing and leave every non-NanoGPT
  provider setup broken. Fixed, along with the default URL (code default is
  `https://nano-gpt.com/api/v1`, guide said `https://api.nano-gpt.com/v1`).
- `DOCUMENT_MODEL`'s code default (`meta-llama/llama-3.3-70b-instruct`) never matched
  what `CLAUDE.md` documented (`deepseek/deepseek-v4-flash`) or what's actually run in
  practice. Changed the code default to match.
- `ATLAS_FILE` default renamed `portland_places.txt` → `atlas.txt` (code default and all
  five character subdirectories) — the old name was a copy-paste artifact that was
  actively wrong for most characters.
- **Found and fixed a real, pre-existing bug while investigating a Priya relocation
  request:** `DEFAULT_SETTING` in `bot.py` — the fallback setting text for the
  *unnamed/home instance* (Nora's slot) — was hardcoded describing "Priya... Houston,
  Texas... moved to Portland, Oregon to tattoo at a shop." It never matched Nora (the
  only character it could actually apply to) and never applied to the real Priya either
  (named instances don't fall back to `DEFAULT_SETTING` at all unless they lack their
  own `setting.txt`). Rewritten to actually describe Nora (Chicago South Side → Seattle,
  per her real card) instead of an orphaned, wrong-character placeholder.
- Priya (the real, deployed `priya.json` — Tamil-American software engineer, Rutgers
  grad) relocated from Austin, TX to Bellevue, WA at the user's request. Updated her
  card description and rewrote `priya/atlas.txt` with real Eastside/Seattle-area places
  (Meydenbauer Bay Park, Cougar Mountain, Stone Gardens, etc.), keeping the same
  personality-revealing-annotation structure as the original. `people.txt`/
  `projects.txt`/`schedule.txt` needed no changes — they had no Austin-specific content.
  Added Priya's (and Jules's) missing entries to `CLAUDE.md`'s Character notes — Priya
  had never actually had one; the Houston/Portland description some earlier session may
  have gone by was always `DEFAULT_SETTING` (see above), never a documented fact about her.

## v2026-07-05.9 — `.alive` heartbeat for watchdog.sh

**Root cause:** a phone-side script (`~/telegram-bot/watchdog.sh`, not part of this repo)
restarts any bot whose `.alive` file is older than 300s, treating it as frozen. `bot.py`
never wrote that file. `watchdog.log` showed every bot flagged `frozen (heartbeat ~70000s
old)` and relaunched every 5 minutes, forever, on all six bots — via `run-bot.sh`'s own
`kill $OLD_PID`, a real SIGTERM against perfectly healthy processes. This was the actual
cause of the entire restart-storm saga (v2026-07-05.4 through .8 below); Samsung battery
settings, Auto Blocker, and the phantom-process-killer fix were all real issues but never
the cause of *this* pattern.

**Fix:** added `_touch_alive`, a 60s repeating job that touches `BASE_DIR/.alive`,
matching what `watchdog.sh` expects. Documented the `watchdog.sh`/`.alive` contract in
CLAUDE.md's Monitoring section, including the one-command diagnostic that would have
found this immediately: `tail watchdog.log` logs its exact reason (`session down` vs
`frozen (heartbeat Ns old)`) before every relaunch.

## v2026-07-05.8 — dead shutdown signal handler

**Root cause:** `python-telegram-bot`'s `run_polling()` installs its own SIGINT/SIGTERM
handlers internally, silently overriding whatever `signal.signal()` was registered in
`main()` beforehand. Our custom `_shutdown` handler (logging "Received signal...") had
never fired, not once, through any restart all session — the entire "no signal line =
SIGKILL" diagnostic this session's phantom-killer theory was built on was unreliable
from the start.

**Fix:** replaced the dead `signal.signal()` registration with
`ApplicationBuilder().post_shutdown(_on_shutdown)` — an async hook that runs as part of
PTB's own already-correct graceful-shutdown sequence regardless of what triggered it.
Removed the now-unused `signal` import.

## v2026-07-05.7 — false-positive restart-storm alerts

**Root cause:** the v2026-07-05.4 restart counter used `time.mktime(time.strptime(...))`
to parse log timestamps, which depends on the OS's local-time calibration
(`/etc/localtime`/`TZ`) — a different mechanism than Python's `zoneinfo`, but one the
same `pkg upgrade` (see v.5) evidently also disrupted. All six bots run on the same
phone, so all of them misjudged old `STARTUP AUDIT` lines as "within the last hour"
identically, producing a fleet-wide false alarm (~199 restarts reported on healthy bots).

**Fix:** compare naive wall-clock `datetime` objects directly instead of converting
through Unix epoch — only needs "same frame, consistent relative diff," not absolute
UTC correctness.

## v2026-07-05.6 — Python 3.14 asyncio incompatibility

**Root cause:** an unrelated `pkg upgrade` (run to fix an adb/libprotobuf error) landed
Termux on Python 3.14, which removed the auto-create fallback that
`asyncio.get_event_loop()` used to provide. `python-telegram-bot` v21's `run_polling()`
depends on that fallback, so every launch crashed with `RuntimeError: There is no
current event loop in thread 'MainThread'` before the bot could even start polling.

**Fix:** explicitly create and set an event loop in `main()` before `run_polling()` if
none exists — a no-op on Python versions where the old fallback still works.

## v2026-07-05.5 — startup crash from missing `tzdata`

**Root cause:** the same `pkg upgrade` (v.6) bumped Python enough that the venv needed
rebuilding (see the pre-versioning `dca3c30` fix below), but the rebuild recipe didn't
include `tzdata`. Termux has no system IANA timezone database, so `zoneinfo.ZoneInfo`
silently fell back to `TZ = None`. A previously-saved reminder's `due` timestamp was
still timezone-aware (saved before the break), so comparing it against a now-naive
`datetime.now()` raised `TypeError: can't compare offset-naive and offset-aware
datetimes` while re-arming reminders at startup — crashing the entire process before it
could serve Telegram at all.

**Fix:** `schedule_reminder` normalizes mismatched aware/naive timestamps instead of
crashing; the startup reminder-rearm loop wraps each reminder in try/except so one bad
entry can't block the rest (or the bot itself). CLAUDE.md's venv rebuild recipe now
includes `tzdata`.

## v2026-07-05.4 — monitoring: restart-storm self-report + dead man's switch

Added `_self_audit` restart counting (buggy until v.7 — see above) and `HEALTHCHECK_URL`
support: when set in an instance's `.env`, the bot pings that URL every 30 min so an
external service (e.g. healthchecks.io) can alert on silence — covers bot-fully-down and
phone-dead, which nothing on-device can self-report.

## v2026-07-05.3 — continuity features

- **Date-aware note follow-ups**: the combined post-reply analysis call now also
  extracts a date when a user note is datable ("interview Tuesday"); stored as a
  `(due YYYY-MM-DD)` suffix in `user_notes.txt`. A daily job (`NOTE_FOLLOWUP_TIME`,
  default 18:00) proactively asks how it went once the date passes, then rewrites the
  marker to `(asked ...)` so it never re-fires. Respects quiet hours and the nudge
  budget; max one per day.
- **Multi-day life threads**: the midnight day-context rotation now feeds yesterday's
  `day.txt` into today's event generation, so a hanging thread (a plan, an errand, a
  person) may continue or resolve instead of the character's life resetting daily.

## v2026-07-05.2 — ops hardening

- `/backup` and the weekly auto-backup now include `memories.txt`, `user_notes.txt`,
  `setting.txt` (previously only `state.json`/`reminders.json`/`payments.json` — a
  character's accumulated relationship history was never actually backed up).
  `.env` stays excluded on purpose.
- New `_is_admin` gate (allowlist member or owner only) on `/update`, `/restart`,
  `/errors`, `/audit`, `/backup` — previously `_is_allowed` returned true for *anyone*
  when `ALLOWED_USERS` was unset, so these operational commands were wide open on any
  instance without an explicit allowlist.
- `/restart`: clean supervisor restart from Telegram, no shell needed for `.env` edits.
- Supervisor trims `bot.log` to its last 1 MB once it exceeds 5 MB (previously unbounded;
  `errors.log` already rotated at 2 MB via `RotatingFileHandler`).

## v2026-07-05.1 — self-deploy, consolidated analysis call, leaner supervisor

- **`BOT_VERSION` introduced** — shown in `/audit` and the startup log, so "did the
  update take?" is answerable from Telegram instead of guessed at.
- **`/update` command**: downloads `bot.py` from `main`, refuses to install anything
  that doesn't `py_compile`, keeps a `bot.py.bak`, swaps, and restarts via the
  supervisor. No Termux shell needed for routine deploys.
- **One combined post-reply analysis call** (`post_reply_analysis`) replaces three
  separate LLM calls (mood appraisal, user-note extraction, NPC memory extraction) that
  ran after every message. On a phone connection those side calls competed with the
  user-facing reply for bandwidth — a real driver of Emily's earlier timeout storm (see
  the pre-versioning entries below). Auto-react also now skips while a reply is
  in flight.
- `run-bot.sh`: supervisor logs via `>>` redirect instead of `tee` — one fewer process
  per bot, six fewer toward Android's 32-phantom-process kill limit.

## Pre-versioning fixes (same debugging session, before `BOT_VERSION` existed)

These landed before the version stamp was introduced above; find them by commit message
via `git log` if you need the exact diff. In the order they were actually found and
fixed — root causes only:

- **`run-bot.sh` launched bare `python`, not the venv's.** Only worked if the venv
  happened to be on `PATH` when tmux started; otherwise crash-looped on
  `ModuleNotFoundError: No module named 'requests'`. This exact bug recurred later
  (unrelated to this fix — a `pkg upgrade` broke the venv itself; see v2026-07-05.5)
  and is a recurring hazard worth checking first on any instance that won't start.
- **Emily's "Vision API Error: 400 —" had an empty body.** The streaming response's
  `with` block closed the connection before `raise_for_status()`'s error body could be
  read. Fixed by force-reading `resp.content` on any status ≥ 400 before raising —
  this pattern must be kept if `_do_request` is ever touched again, or every future
  4xx/5xx becomes undiagnosable again.
- **`VISION_MODEL` defaulted to `NANOGPT_MODEL`** (a text-only reasoning model), so any
  instance without an explicit `VISION_MODEL` in `.env` sent photos to a model that
  rejects images. Changed the default to `zai-org/glm-4.6v`.
- **`STREAM_TIMEOUT` (30s) was too tight** for a phone connection running several
  concurrent side-calls per message; every model, including fast flash-tier ones,
  timed out constantly. Raised to 90s.
- **WSDOT `GetAlertsAsJson` returns a bare array**, but the parser called `.get("Alerts")`
  on it, crashing the traffic poller every 10 minutes (silently, since it was caught and
  logged, not fatal — but `/traffic`/`/incidents` were broken the whole time). Fixed to
  accept both a bare array and a wrapped object.
- **Inworld voice IDs sent to NanoGPT's OpenAI-style TTS endpoint 400'd** — voice and
  model must come from the same provider. Added native Inworld TTS support
  (`INWORLD_API_KEY`/`INWORLD_TTS_MODEL`), auto-selected when the key is set.
- **Added `/errors` command** — tails `errors.log` into chat, so future bug reports
  carry the actual error text instead of a vague "it's down."

For history before this debugging session (memory system fixes, latency work, thread
safety, etc.), `git log` is the source of truth — those commits predate this file.
