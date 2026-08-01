# Roadmap — telegram-companion-bot

Written 2026-07-06 from a code survey of bot.py v2026-07-05.12 (7,626 lines), the
changelog, and CLAUDE.md. Each item names its evidence — why it's on the list — plus
effort (S/M/L), risk, and what "done" means. Ordered by track, sequenced at the bottom.

**Deliberate non-goal, recorded to prevent future refactor urges:** bot.py stays a
single file. The entire deploy model (`vps-sync.sh` swapping one shared file across all
seven instances, `bot.py.bak` rollback) depends on it. The monolith's real cost —
regressions in pure logic — is covered by Track 2.1 instead.

---

## Track 1 — Reliability & platform

The phone *was* the existential risk (phantom process killer, OEM battery managers,
Python-bump venv breaks). 1.2 retired it on 2026-07-26 — six instances moved onto the
VPS that day, marcus joined directly there on 2026-07-29, and all seven run under
systemd now. Items here predating 2026-07-26 were written under the phone's
constraints; check their assumptions before acting on them.

### 1.1 ~~Commit watchdog.sh to the repo~~ ✅ (shipped v2026-07-06.3)
- Committed as `telegram-companion-bot/watchdog.sh` with curl-install instructions in
  its header, matching backup-all.sh's pattern. Covered by `shell-scripts-parse` eval.

### 1.2 VPS migration Phase 2 — actually move the fleet — L
- **Evidence:** Changelog v2026-07-05.12 is explicitly "Phase 1 of VPS migration":
  `deploy/bot@.service` (Restart=always) and `deploy/install-vps.sh` already exist and
  are confirmed compatible with the PID-lock/exit patterns. Phase 2 was never specced.
- **Status:** Pilot soak PASSED 2026-07-26 — jules's week on the VPS closed with +7
  errors total, 0 in the last hour, current release running, no fabricated-timestamp
  recurrence, and no note-ownership regressions (the v2026-07-19.2 backstop fired
  once, correctly, on a pre-fix polluted note). **Phase 2 COMPLETE 2026-07-26 — all
  six instances on the VPS under systemd; the Termux phone is empty.** Priya's and
  bonnie's cutovers each hit an incident (both in the operational log, both fixed in
  the runbook: verify state by content; rename the instance dir before any kill).
  Remaining for 1.2's done-when: 14 days of green healthchecks, the OPS_MANUAL "VPS
  operations" section, and marking CLAUDE.md's Termux quirks historical — plus the
  cleanup batch below. **ROADMAP 3.8 Phase 2 is now unblocked** (see "Unlocks on
  completion").
- **Plan:**
  1. Pilot with one low-state bot (jules). Cutover is per-bot and brief: stop the
     instance on the phone → restore its directory from the latest backup-all.sh
     archive onto the VPS → `systemctl start bot@jules`. Only one process may poll a
     bot token, so stop-then-start, never parallel.
  2. Set `HEALTHCHECK_URL` per migrated instance (dead man's switch already built).
  3. `ADMIN_API_ENABLED=1`, bound to the Tailscale IP (Phase 1 auth model, never 0.0.0.0).
     **NOT DONE — verified 2026-07-29.** `ADMIN_API_ENABLED` is unset on all six
     instances and nothing is bound; the migration moved instance directories from the
     phone, so no instance ever ran `install-vps.sh`, which is the only thing that writes
     that line. Consequence: **`/fleet` and `fleet-status.sh` cannot work** — they poll
     `/admin/health` on peers and no peer serves it. Silent, like every fail-closed
     default (the `GROUP_MODE` class, operational log 2026-07-28).
     **Do not enable it by adding one line to six `.env` files.** Every instance defaults
     to `ADMIN_API_PORT=8765` (bot.py) and `_start_admin_api` calls
     `ThreadingHTTPServer(...)` unguarded, so the second instance to start raises
     `Address already in use` **and fails startup** — one optional feature taking down the
     bot. Enabling means a distinct port per instance in the same edit, and the unguarded
     bind is worth fixing first so a port clash degrades instead of crashing.
  4. Soak the pilot for a week (watch `/audit` error counts vs its phone baseline),
     then migrate the rest one at a time. Phone keeps nora last — she's the shared-venv
     home instance; retire the phone (or keep it as a spare) when she moves.
- **Risk:** state divergence if a bot runs on both hosts — the stop-before-start rule
  is the whole safety story. Timezone: verify tzdata + TIMEZONE on the VPS before the
  first start (the v2026-07-05.5 startup-crash class).
- **Cleanup batch (owner, deferred to "all six migrated" — ask Claude to walk this
  list when Phase 2 completes; items accumulated during the 2026-07-19 pilot):**
  - [ ] VPS: `rm /opt/telegram-bots/jules/jules.json` (stale renamed card copy;
        `CHARACTER_CARD` now normalized to `jules_nakagawa.json`)
  - [ ] VPS: delete `/opt/telegram-bots/nora.parked` — do NOT revive it for nora's
        migration (rebuild from the runbook tar instead; its `.env` has duplicate
        `TELEGRAM_BOT_TOKEN` lines and cloned state)
  - [ ] Re-point `HEALTHCHECK_URL` to the VPS for jules + every instance as it moves
  - [ ] Phone: delete `~/jules-migrate.tar.gz` (jules's rollback copy — keep until
        soak passes; same per-instance after each successful migration)
  - [ ] Phone: as each instance migrates, remove/rename its `~/<name>-bot/` dir —
        `watchdog.sh` hard-codes the instance list and resurrects any dir it sees;
        retire watchdog.sh entirely when the phone empties
  - [ ] Verify Jules's proactive texts stayed free of fabricated `[sent HH:MM]`
        headers (card fix 2026-07-19); if recurred, ship the regex strip at the
        `_do_request` choke point as a versioned release
  - [x] OPS_MANUAL "VPS operations" section; mark CLAUDE.md Termux quirks historical
        (these two are also the 1.2 done-when criteria) — **done 2026-07-26**;
        CHEATSHEET.md rewritten for systemd in the same pass
- **Done when:** all six instances on systemd, healthchecks green for 14 days,
  OPS_MANUAL has a "VPS operations" section, and the Termux quirks in CLAUDE.md are
  marked historical.
- **Unlocked on completion:** item 3.8 Phase 2 (a pre-reply thinking *call*) was
  blocked on this item and is now open — the phone-bandwidth constraint that forbade
  per-message side completions is gone. **3.8's spec was rewritten 2026-07-26 to
  match reality**: the host gate it planned is obsolete (no phone instances to
  protect), the call must use a reduced prompt (~17k-token full context is the real
  cost driver), it only applies to non-`:thinking` models, and its A/B protocol is now
  concrete. Read 3.8 before starting it — the recommendation there is to measure
  whether Phase 1 plus the 2026-07-26 preset work already delivered the goal.

### 1.3 ~~Fleet status one-shot~~ ✅ (shipped v2026-07-06.3)
- Committed as `telegram-companion-bot/fleet-status.sh`. Hits `/admin/health` per
  instance, prints a six-row table. Works on-phone (localhost) or over tailnet.

### 1.4 ~~Degradation alerts (fallback rate + monthly spend)~~ ✅ (shipped v2026-07-06.3)
- `_self_audit` watches fallback rate (≥3/hr → DM) and optional `USAGE_BUDGET_MONTHLY`
  (DM at 80%/100%). Both use the existing 2h-cooldown DM pattern.

### 1.5 ~~Telegram-native fleet console~~ ✅ (shipped v2026-07-19.1)
- `/fleet` on a designated instance probes every peer's admin API (`FLEET_PEERS`,
  works across phone+VPS hosts mid-migration) and replies with one up/down /
  version / uptime / errors table — `fleet-status.sh` without the shell.

### 1.6 ~~Lock the vps-sync.sh bot.py swap~~ — S, **shipped 2026-08-01, VPS race-test pending**
- **Why now:** `perform_self_update` had exactly this bug and it bit on 2026-07-25
  (`FileNotFoundError: /opt/telegram-bots/bot.py.new`, operational log same date). Fixed
  in bot.py by a host-wide `flock` in v2026-07-25.11 — but `deploy/vps-sync.sh` performs
  the *same* swap on the *same* shared paths with no guard, so the class is only half
  closed. Cass and jules share `/opt/telegram-bots`, and the documented deploy is two
  back-to-back invocations, which is precisely the race.
- **The race** (`vps-sync.sh` lines 33/49/50/51):
  ```
  curl -o "$BASE/bot.py.new"   →  py_compile  →  cp bot.py bot.py.bak  →  mv bot.py.new bot.py
  ```
  Two concurrent runs share all three paths. The loud failure is one run's `mv` removing
  the other's `bot.py.new`. **The silent failure is worse and is the real reason to fix
  it:** if instance B's `cp bot.py bot.py.bak` lands after instance A's `mv`, the rollback
  point becomes a copy of the *new* code, and nothing reports it — you believe you can
  roll back and you cannot.
- **Fix:** `flock` around the bot.py swap. `flock` is util-linux and present by default on
  Ubuntu 24.04 (unlike Termux, which is why bot.py's phone-side guard and `watchdog.sh`'s
  PID-file guard were chosen differently — do not "unify" the three).
  ```bash
  exec 9>"$BASE/.vps-sync.lock"
  flock -n 9 || { echo "[vps-sync] another sync is swapping bot.py on this host; retry"; exit 1; }
  ```
  Only the shared code swap needs covering — the card, preset layers, `.env` and systemd
  unit are all per-instance. Locking the whole run is simpler and equally correct.
- **Also worth folding in:** `vps-sync.sh` currently `cp`s the backup *before* the `mv`
  with `|| true`, so a failed backup is silent. Make the backup failure fatal, since its
  entire purpose is the rollback path.
- **Done when:** two `vps-sync.sh` runs started simultaneously against the same host leave
  a correct `bot.py` and a `bot.py.bak` holding the genuinely previous version; the second
  run exits non-zero with a clear message rather than corrupting either. Verify by racing
  them deliberately on the VPS, not by inspection.
- **Shipped 2026-08-01** (see CHANGELOG "vps-sync.sh's bot.py swap is now locked"): the
  `flock` and the fatal backup are both in `deploy/vps-sync.sh` now. The locking
  mechanism itself was extracted and raced in isolation — a held lock correctly rejects
  a second concurrent `flock -n` attempt, and releases cleanly for the next solo run —
  but that's a controlled stand-in, not the real script. **This item's own done-when is
  explicit that verification means racing actual `vps-sync.sh` invocations on the VPS,
  not inspection**, and no VPS access exists from this session. Don't mark this fully
  closed until someone runs two real `vps-sync.sh nora` / `vps-sync.sh bonnie`-style
  calls at the same instant against the shared host and confirms one wins cleanly and
  the other exits non-zero without touching `bot.py.bak`.

---

## Track 2 — Engineering workflow

### 2.1 ~~Committed unit tests for the pure logic~~ ✅ (shipped v2026-07-06.4)
- `tests/test_pure.py` (pytest): 41 tests covering `extract_tags`, cron parsing,
  `_extract_json`, `parse_when`, `_est_tokens`, `_count_error` cap. CI runs pytest
  after the eval suite.

### 2.2 ~~New-instance bootstrap~~ ✅ (shipped v2026-07-06.4)
- `new-bot.sh <name> <card.json>`: interactive bootstrap, creates dir, prompts for
  tokens/models, curls card + seeds, launches via run-bot.sh.

### 2.3 ~~Card/seed sync tooling~~ ✅ (shipped v2026-07-06.3)
- `sync-cards.sh`: for each instance, reads CHARACTER_CARD from .env, pulls card +
  seed directory from main. Supports `--dry-run`.

### 2.4 Selfie prompt constants hoisted — S, **built and parked, awaiting a carrier release**
- **Status:** complete on `claude/github-commit-workflow-integration-ak6ql6`
  (v2026-08-01.1, changelog entry written). **Not merged to `main` on purpose** — see
  "why parked" below. This is the only open item that is code-complete but deliberately
  unmerged; anyone shipping the next bot.py release should fold this branch in rather
  than rebuild it.
- **What:** the anatomy rule and the realism/SFW rule were inline literals appended
  mid-`build_selfie_prompt`; they are now `_SELFIE_ANATOMY_RULE` and
  `_SELFIE_REALISM_RULE`, sitting with the other `SELFIE_*` pools. No behavior change
  (640-prompt before/after diff, byte-identical). Two tests pin it, both break-tested RED.
- **Why it was worth doing:** these two fragments are the ones you edit when the image
  model returns extra limbs or a filter-tripped frame, and finding them meant reading a
  70-line function instead of grepping a constant name.
- **Why parked:** zero user-visible change, so it does not justify a seven-instance deploy
  by itself. Standing policy is merge-when-green; the owner's explicit call (2026-08-01)
  was to bank it and let it ride the next functional release — 1.6 is the likely carrier.
- **Origin:** prompted by `ShopDevX/adeptlydev` b6d7437 (push-chains → template literals).
  The generalized version of that lesson was **considered and rejected** as an invariant —
  see "Rejected or already covered" below.
- **Done when:** merged to `main` as part of a release that has its own reason to deploy,
  and the carrier release's `/audit` shows its BOT_VERSION on all seven instances.

---

## Track 3 — Character & product features

### 3.1 ~~Voice conversational symmetry~~ ✅ (shipped v2026-07-06.3)
- `VOICE_REPLY_TO_VOICE` (default 0.9) replaces ambient `TTS_CHANCE` when the
  incoming message is a voice note. Text messages unaffected.

### 3.2 ~~Shared world context~~ ✅ (shipped v2026-07-06.4)
- `WORLD_GENERATOR=1` instance writes `world.txt` at midnight; every instance reads it
  during day generation. Degrades gracefully if absent.

### 3.3 ~~Semantic memory recall~~ ✅ (shipped v2026-07-06.5)
- NanoGPT embeddings (`text-embedding-3-small`). Embeds on write, cosine top-k on
  recall merged with keyword results. Falls back to keyword-only on API failure.

### 3.4 ~~Group chat / bot-to-bot~~ ✅ (shipped v2026-07-10.1)
- Design doc (`GROUP_CHAT_DESIGN.md`) survived four adversarial-critic review rounds,
  then the prototype shipped behind `GROUP_MODE=1` for the Priya + Jules pilot.
  Shared flock'd ledger + atomic claim files (Telegram never delivers bot messages to
  bots); chain cap 2; fleet-wide fail-closed group posture; two CI evals pin the
  group/private memory boundary. On-device rollout steps in OPS_MANUAL.

### 3.5 TomTom Maps — S
- **Phase 1 ✅ (shipped v2026-07-11.7):** slash commands `/route`, `/nearby`, `/place`
  behind `TOMTOM_API_KEY` (fail-closed); per-instance `TOMTOM_TRAVEL_MODE`. Raw
  `api.tomtom.com` REST, defensive parsers, 20 tests. Owner provisions the key.
- **`/food` ✅ (shipped v2026-07-11.13):** GPS-based nearby restaurant list
  (`/food [cuisine]`); "open now" held for a follow-up (tz-safe opening-hours parse).
- **In-character restaurant recs ✅ (shipped v2026-07-11.14, `FOOD_SUGGESTIONS`):**
  food-ish message + shared location → real nearby restaurants pre-fetched and
  injected into the single reply so the character recommends them in her own voice.
  No extra LLM call; default off. Proves the pre-fetch-and-inject pattern.
- **Phase 2 ✅ (shipped v2026-07-17.1, `MAP_INTENT`):** generalized map intent —
  route asks ("how do I get to X", "how far is X") and nearby asks ("is there a
  <thing> nearby") pre-fetch real TomTom data into the single reply via regex intent
  detection (`_map_intent`), honoring the budget rule (no per-message LLM side call).
  Deferred follow-ups (owner-settled 2026-07-17): "what's near <remote place>",
  memory-resolved "home"/"work" destinations, and a per-chat cooldown if the `[map]`
  log line ever shows over-firing.

### 3.6 ~~Schedule-driven unavailability~~ ✅ (shipped v2026-07-18.2, `SCHED_BUSY`)
- **Evidence:** `REVIEW-BRAINENGINE-2026-07-18.md` item A (owner-approved 2026-07-18).
  `schedule.txt` is injected into context every turn (`_read_schedule_today`) but
  nothing enforces it behaviorally — the character is always instantly available,
  never says she has to go, never replies slower mid-commitment. The always-on
  companion is the single biggest "puppet" tell.
- **Plan:** parse today's schedule section for time-ranged entries; when `now` falls
  inside a busy block, inject a system line (replying in stolen moments, shorter,
  may say she has to go and pick the thread up later) and optionally scale typing
  delay via the existing `send_bubbles` `pre_delay` plumbing. Env kill switch per
  owner policy 2026-07-18 (default on, `0` disables without redeploy). Zero extra
  LLM calls. Proactive sends unchanged — existing quiet-hours/nudge checks stay
  authoritative; this only adds restraint.
- **Risk:** low — prompt + arithmetic only. Main hazard is over-firing on loosely
  formatted schedule entries; parse conservatively (explicit `HH:MM-HH:MM` ranges
  only) and log a `[sched-busy]` line so over-firing is visible.
- **Done when:** a bot with a busy block active visibly changes register (and can
  exit a conversation), verified in a live exchange; no behavior change when the
  kill switch is set to `0` or schedule.txt has no timed entries.

### 3.7 ~~Fatigue accumulator + silence license + day-mood residue~~ ✅ (shipped v2026-07-18.3, `FATIGUE_STATE`/`DAY_MOOD_RESIDUE`)
- **Evidence:** `REVIEW-BRAINENGINE-2026-07-18.md` items B + C (owner-approved
  2026-07-18, bundled — they share the state plumbing and injection point). Mood
  tracks what she feels *about* things but nothing tracks remaining social capacity;
  and every message currently earns a full reply, another realism tell. Residue
  sub-item from `REVIEW-YURALUME-2026-07-18.md`: mood changes ONLY through
  conversation, so her generated day (`day.txt`) never colors how she opens.
- **Plan:** per-chat `fatigue` float 0–100 updated arithmetically where
  `post_reply_analysis` already lands valence (intense exchange +10–15, calm
  positive −15, else −5; decay with `_gap_hours`). No LLM call. Above a threshold,
  one system line ("socially drained — shorter replies, less patience"), plus a
  license for a bare "k"/reaction to be a complete reply when drained, busy (3.6),
  or low-mood. **Residue:** one extra JSON key (`opening_mood`: label + valence)
  on the existing midnight day-generation call, written into the normal mood state
  at rotation so her day seeds how she shows up — mood is presentation state, not
  a fact store, so the `[own-day]` provenance rule is untouched. Env kill switch
  per owner policy 2026-07-18 (default on, `0` disables without redeploy).
  Explicitly NOT adopting BrainEngine's "ego depletion" (dropping social
  regulation) — recorded rejection in the review.
- **Risk:** low — tuning risk only (fatigue that accumulates too fast reads as
  sulking). Start with conservative constants; log `[fatigue]` transitions.
- **Done when:** a long intense conversation produces a visible register shift that
  recovers after a gap; minimal replies occur but stay rare; a notable day.txt
  event visibly colors her first exchange after rotation; behavior with the
  kill switch set to `0` identical to today.

### 3.8 Stepped thinking — plan-then-speak — S (Phase 1 shipped; Phase 2 unblocked 2026-07-26)
- **Evidence:** owner request 2026-07-23 to port the idea behind the SillyTavern
  `st-stepped-thinking` extension (make the model think *as the character* before it
  answers). The extension's native mechanism is one extra LLM completion per configured
  thinking-prompt, per message — a direct violation of the phone-bandwidth invariant
  (`bot-code-invariants` #3, one combined `post_reply_analysis` call, no per-message
  side completions).
- **Phase 1 ✅ (shipped v2026-07-23.1, `STEP_INTENT`):** the idea folded into the
  machinery we already have, on **zero extra calls**. `post_reply_analysis` emits one
  extra JSON key (`intent`): a one-line forward-looking "frame of mind" note stored in
  the ephemeral `next_intent` dict (not persisted, never a user-fact store — provenance
  handled exactly like mood) and injected into her *next* reply after the mood note,
  freshness-gated (`STEP_INTENT_TTL_SEC`, default 6h) by pure `_step_intent_seed`.
  Companion content change: a `[STEPPED THINKING]` block in the fleet-wide `preset.txt`
  stages the `:thinking` chat model's hidden reasoning (feel → want → write), mirroring
  `[SELF-CHECK]`'s leak-safe "silently, keep it out of the reply" framing. Default on,
  kill switch `STEP_INTENT`.
- **Phase 2 — a real hidden thinking *call* before the reply — UNBLOCKED 2026-07-26
  (all six on VPS), but the case for building it got weaker, not stronger.** Read this
  before starting: the spec below was rewritten when the block lifted, because the
  constraint it was designed around dissolved and two of its guardrails became moot.
- **What the migration changed:**
  - **The host gate is obsolete — do NOT build it.** The old plan gated the call on a
    host signal so it could never fire on a phone instance. There are no phone
    instances. That gate would now be complexity defending a state that cannot occur;
    if an instance ever returns to the phone, that is when the gate earns its keep.
  - **Invariant #3 does not get a host carve-out.** Its original justification (phone
    bandwidth) is void, but the rule stands on **latency** and **cost** — see the
    invariant's own rewritten rationale in `bot-code-invariants` #3.
- **What did not change, with real numbers (from 2026-07-26 audits):**
  - **Cost is dominated by context, not output.** Instances run **~17k input tokens per
    call** (jules: 8.3k preset + ~5k card + memory) at 15-40 calls/day. A naive
    pre-reply call re-pays that entire prompt every user message, ×6 bots. **Therefore:
    the thinking call MUST use a deliberately reduced prompt** — recent turns plus
    character core only, no lorebook, no semantic-memory block. Target ≤5k. A
    full-context thinking call is not affordable and should not be built.
  - **Latency** — an extra round-trip delays time-to-first-token on every reply. Must
    be measured, not assumed maskable by the typing indicator.
- **Precondition the original spec missed: this is only applicable to
  non-`:thinking` models.** Emily runs `zai-org/glm-4.7:thinking`, which already
  reasons internally, and `preset.txt`'s `[STEPPED THINKING]` block already stages that
  reasoning (feel → want → write). A separate hidden call there duplicates what the
  model does natively. Phase 2's addressable surface is only the instances on
  non-reasoning models (e.g. jules on `xiaomi/mimo-v2.5-pro`).
- **Plan (if picked up):**
  1. One env flag, `STEP_THINK_CALL`, **default off** — the higher-cost/higher-risk
     carve-out that `bot-code-invariants` #16 permits with a rationale. No host gate.
  2. ONE extra call max — a single hidden "how does she read this, what does she want"
     pass seeding the visible reply; never N-per-thinking-prompt like the source
     extension. **Reduced prompt (≤5k), not the full reply context.**
  3. Route through the `_do_request` choke point (invariant #4) even though the thought
     is internal, and never let the raw thought reach the user (the documented
     planning-leak class — Priya's leaked monologue).
  4. **A/B protocol (the old "demonstrably improves replies" could never conclude —
     there is no automatic quality metric for companion replies):** pick ONE
     non-reasoning-model instance (jules), alternate `STEP_THINK_CALL` on/off **by day
     for two weeks**, judged on one concrete question — *does she act on what she wants
     more often, or merely narrate more?* Log per-reply latency and a per-day call
     count so `/audit` shows the cost throughout. Same bot against its own baseline;
     never compare two different characters.
- **Standing recommendation (2026-07-26): try the cheap experiment before building.**
  Phase 1's free `STEP_INTENT` seed, plus the 2026-07-26 `preset.txt` work (epistemic
  horizon, proactivity clause, anti-slop) attack the same target — characters acting on
  their wants — at zero marginal cost. Measure whether that already delivered the
  proactivity this item was for. Phase 2 may be solving a problem that closed while it
  was blocked.
- **Risk:** medium — first deliberate loosening of the LLM-call-budget invariant. With
  the host gate gone, the guardrails are: default-off, one-call cap, reduced context,
  choke-point routing, and the A/B gate.
- **Done when (Phase 2):** a default-off, reduced-context single pre-reply thinking call
  beats the free `STEP_INTENT` seed in the two-week same-bot A/B above, with latency and
  per-day call count visible on `/audit` — **or** the A/B shows it doesn't, and this item
  is closed as "tried, not worth it" with that evidence recorded.

### 3.9 ~~Topic-initiative balance~~ ✅ (shipped v2026-07-25.1, `PROMPT_BALANCE`)
- Owner reported the bots over-reach for memories/notes and rarely surface anything else.
  Cause was directive asymmetry, not card size or context pressure: only the two recall
  blocks told the character to raise their contents, while `day.txt` was explicitly told
  not to be foregrounded. Adds a `# Bringing things up` block plus rewritten
  notes/threads/day tails. This is the follow-on v2026-07-18.1 deferred.
- Card size was ruled out and should not be re-investigated: `CONTEXT_TOKEN_BUDGET`
  defaults to 0 (no trimming at all), and when set, every system block is protected —
  only conversation history is dropped.

### 3.10 ~~Garmin health feed~~ ✅ (shipped v2026-07-25.2, `GARMIN_FEED`)
- Sleep / resting HR / steps / Body Battery / stress / last workout as prompt context,
  plus three quiet-hours-and-budget-gated proactive check-ins, `/health` `/healthnow`
  `/stress`, and an `/audit` line. `garminconnect` stays an optional per-instance pip
  install, not a fleet requirement.
- **Why it took until now:** the feature was built on `claude/push-to-repo-7i2f3c`, an
  **orphan branch sharing no git history with `main`** (empty `git merge-base`; separate
  root commit 2026-04-15). Deploys all pull from `main`, so it shipped to nobody for
  ~3 weeks. Ported by hand.
- **Open follow-up:** that branch holds other unported work — on-this-day reminiscing,
  offline life events, adaptive texting-style mirroring, `acoustic_ears`, `/diag`. None is
  requested yet; audit it deliberately rather than assuming main is a superset, and treat
  every port as a rewrite against current main (a merge would drag in a parallel bot.py).

### 3.11 ~~Prompt-size observability~~ ✅ (shipped v2026-07-25.3, `PROMPT_STATS`)
- Per-call assembled size, running max with the three largest system blocks at the peak,
  coarse histogram, all on a new `/audit` `Prompt:` line. Nothing measured a *single*
  prompt before — `_llm_stats["tok_in"]` is a daily running sum.
- Baseline measured at ship time (empty instance, 20 short turns): cass 11,435 → jules
  14,822 tokens. `preset.txt` alone is **8,503 tokens on every message for every bot** —
  larger than any card, and 77% of cass's system stack.

### 3.12 ~~Tiered prompt trimming~~ ✅ (shipped v2026-07-25.4)
- `_trim_history_to_budget` → `_trim_prompt_to_budget`. The old version protected every
  system block and dropped only conversation (9/9 blocks kept, 13/20 turns dropped at a
  15k budget), and could strip all history while still shipping over budget. Now: optional
  blocks first (largest first), then history oldest-first, then a last-resort dip below
  `KEEP_RECENT`, then a warning. Opt-in marking via `_sys_opt()` — unmarked stays
  protected, so a new or reworded block can't silently become droppable.
- `CONTEXT_TOKEN_BUDGET` still defaults to 0/off. Set it from the `/audit` numbers.

### 3.13 ~~Reduce the protected prompt floor~~ ✅ (mechanism + content shipped, fleet-wide adoption owner-confirmed 2026-08-01)
- **Mechanism ✅ (v2026-07-25.5, `PRESET_FILES`):** ordered preset layer files, each
  injected as its own block; `sync-cards.sh` and `vps-sync.sh` are layer-aware. Inert by
  default — verified byte-identical prompt for the unset, explicit-single-layer, and legacy
  `PRESET_FILE` configs.
- **Correction to the earlier note here:** `[ATTRACTION RULE]` is **84 tokens**, not 4,715.
  That figure was the whole merged card block, mislabelled by `_prompt_top_blocks` (fixed
  in v2026-07-25.5). Moving it to the lorebook saves ~84 tokens — parked as not worth a
  release on size grounds; revisit only if there's a *behavioural* reason to make it
  conditional.
- **Content ✅, superseding the prototype numbers previously recorded here.** The
  "core/rp/feature, cass 11,031 → 4,758 (−57%)" split named in earlier drafts of this item
  was never shipped in that form. What actually shipped, across two releases, fits every
  character rather than cutting size for its own sake:
  - **v2026-07-25.6:** `preset.txt` carved into `preset-core.txt` (4,166 tok — voice,
    anti-slop, agency, epistemic horizon, repair, self-check), `preset-rp.txt` (1,680 tok
    — narration/scene machinery), `preset-explicit.txt` (1,930 tok), `preset-stepped.txt`
    (403 tok, pairs with `STEP_INTENT`), `preset-closeness.txt` (323 tok, pairs with
    `CLOSENESS_ENABLED`, default off). Cass moved onto `core+stepped`: 11,037 → 7,102
    (−36%).
  - **2026-07-26 → 2026-07-28:** a per-character format-contract layer for all seven —
    `preset-{nora,bonnie,cass,emily,priya,jules,marcus}.txt` (~250-430 raw tok each) —
    arbitrating where a card's format contract disagrees with the shared preset (Bonnie
    runs long by design against core's "prefer shorter"; Priya is lowercase/no-markdown;
    Emily is third-person; Marcus's asking-first is characterization, not the standing-
    consent narrator rule). Measured stacks (raw / cal): cass 4,827/4,441, priya
    4,830/4,444 (both ~43% below the 8,503-tok monolith); nora/bonnie/emily/jules land
    within ±35 tok of today's monolith on the full scene stack — the saving is fit, not a
    blanket cut, exactly as intended.
- **Fleet-wide adoption — owner-confirmed 2026-08-01, closing the gap the repo alone
  couldn't settle.** As of the previous entry, the changelog's last explicit status
  (2026-07-26) was "inert — no instance loads any of them yet," and `.env` files aren't
  tracked in this repo, so nothing here could confirm the layers were actually live on
  any instance beyond cass. The owner has now confirmed the layered preset is launched
  and in use fleet-wide, and is switched live per instance via `/preset` from Telegram
  (v2026-07-26.1) rather than requiring an `.env` edit + restart per experiment. Treat
  this owner statement as the record; a per-instance `/audit` `Preset layers:` check is
  the way to re-confirm it later if it's ever in doubt again.
- `preset.txt` remains voice-critical and deliberately tuned (v2026-07-18.1's anti-echo
  work) — any *further* layer change (new content, not just switching among what already
  exists) still goes through the owner, same as any other voice edit.

### 3.14 Port the banned-rhetoric block from Chimera v2 into `preset.txt` — S, owner-gated
- **Evidence:** the 2026-07-25 review of Writer's Block 5 against the root Chimera preset
  (`Chimera_v1_borrow-review_WritersBlock5.md`) found that naming the specific LLM
  constructions beats describing them. Chimera's old rule — *"write the positive action:
  'She looks away' rather than 'She doesn't look at him'"* — catches simple negation only.
  It misses `not X but Y`, which is the loudest machine tell. Shipped to the SillyTavern
  side in `Chimera_v2.json`; the fleet never got it.
- **What to port:** the four named bans — contrastive negation (`not X but Y`),
  false-correction/epanorthosis (`It was X. No — Y.`), negation-as-atmosphere
  (`it wasn't the wind`), and litotes (`not unkind`) — each with its one-line example.
  ~60 tokens. Do NOT port the rest of the Chimera diff: hooks, the relationship ladder,
  the assistants and the CoT tasks are all scene-roleplay machinery, wrong shape for a
  texting companion.
- **Blast radius:** universal prose hygiene, not scene machinery, so per 3.13 (shipped)
  it belongs in **`preset-core.txt`**, not the legacy monolithic `preset.txt` — one edit
  there reaches every instance that loads the core layer, which per 3.13 is all seven.
  Deploy is `vps-sync.sh` per instance (see `deploy-and-verify-fleet`); there is no
  phone path anymore.
- **Sequencing note (resolved):** this was blocked on 3.13 landing first, to avoid
  growing the monolith right before a split. 3.13 shipped (v2026-07-25.6 →
  2026-07-28, fleet-wide adoption owner-confirmed 2026-08-01) — the core layer exists
  now, so this item is unblocked and its target is settled: `preset-core.txt`.
- **Risk:** low on content, non-trivial on voice — `preset-core.txt` inherits
  `preset.txt`'s deliberate tuning (v2026-07-18.1 anti-echo work). Verify against Priya
  and Jules first: Priya's lowercase sardonic register and Jules's flat precision are
  the two most likely to shift.
- **Done =** the block is in `preset-core.txt`, every instance re-synced via
  `vps-sync.sh` and `/audit`-verified, with a before/after sample from Priya and Jules
  showing the register held.

---

## Track 4 — Audit backlog & memory integrity (from AUDIT-2026-07-10.md)

The 2026-07-10 audit (external Deepseek pass + verification + two user-observed bugs)
shipped its confirmed fixes as v2026-07-10.2. What remains, triaged below — and specced
in full, release-by-release, in **`IMPROVEMENTS_PLAN.md`** (self-contained handoff for
whichever agent implements it):

### 4.1 ~~Memory auditor~~ ✅ (shipped as R1, v2026-07-11.1)
- Source-attached memories (`memory_meta.json`), quote grounding, confidence + review
  queue (`/reviewmem`), `/editmem` + `/sourcemem`, `[memcheck:]` correction flow,
  append-only memory audit log — per the IMPROVEMENTS_PLAN.md R1 spec. "Done when"
  met: a wrong memory is traceable and correctable from Telegram in under a minute.
  Follow-up memory-loop refinements shipped v2026-07-12.1–.2.

### 4.2 ~~Availability awareness~~ ✅ (shipped as R2, v2026-07-11.2)
- `/away` + `/back`, remote-default framing, auto-extraction via post-reply analysis
  (auto-away expires after `AWAY_AUTO_HOURS`), busy/working/driving vibe presets.

### 4.3 ~~Robustness leftovers~~ ✅ (shipped as R3, v2026-07-11.3)
- Atomic small-file writes (`_atomic_write_text`), `_last_request` pruning, config
  warnings surfaced in `/audit` (`_CONFIG_WARNINGS` — the useful core of the suggested
  `validate_config()`), persisted error counts, graceful drain, LLM usage counters.

*(R4 prompt hygiene, R5 UX, and R6 evolution experiments from the same plan shipped as
v2026-07-11.4–.6 — see IMPROVEMENTS_PLAN.md and CHANGELOG.md.)*

### 4.4 Retune `MEMORY_TOKEN_BUDGET` in calibrated units — S, owner-gated
- **Context:** v2026-07-26.2 made reported token counts real (provider `usage`, plus a
  calibration ratio for what can only be estimated). `MEMORY_TOKEN_BUDGET` was
  deliberately left on the raw `len//4` unit.
- **Why it was left:** it is a tuned *recall* knob, not a cost ceiling. Every value in
  every `.env` was picked against the raw unit, so switching to calibrated counts would
  fit fewer memory lines into the same nominal budget and change how much six live
  characters remember — a personality change shipped as an accounting fix.
- **The work:** read each instance's calibration ratio from `/audit`, multiply its
  `MEMORY_TOKEN_BUDGET` by it so the *effective* recall is unchanged, then switch the
  budget to `_tokens()` in the same release. Net behaviour-neutral by construction; after
  that the knob means real tokens and can be tuned against a real ceiling.
- **Do not action without the owner** — the whole point is that recall volume is a
  product decision, and the migration is only safe if the multiply and the switch ship
  together.

### Rejected or already covered (recorded so they don't come back)
- **"Sweep the remaining pre-2026-07-18 default-off flags to default-on" — withdrawn
  2026-07-28, do not re-open.** Briefly filed as 4.5 after v2026-07-27.1, on the theory
  that the 2026-07-18 default-on policy had never swept backwards. The five flags were
  enumerated by *code shape* (`os.getenv("X", "0")`) without reading what any of them
  was. All five are deliberately off, each with a rationale that already existed in
  writing — which is precisely invariant #16's carve-out, not a violation of it:
  - `FEEDBACK_REACTIONS`, `CLOSENESS_ENABLED`, `THREADS_ENABLED`, `JOKE_CANDIDATES` are
    the R6 evolution experiments. The changelog titles that release *"R6 evolution
    experiments (all gated, default off)"* (v2026-07-11.6); `.env.example` heads the
    block *"default off, pilot one instance at a time"*; and the entry directly below
    this one already rejects flipping them as a class — *"product direction, not audit
    debt; revisit deliberately, not as a checklist."* A bulk default-flip is the
    checklist. Enabling any of them is a per-instance product decision for the owner.
  - `DEVICE_RENDER` is a cosmetic delivery preference (monospace bubbles, like a phone
    log), documented under *Voice & delivery* with its default value shown. Default-off
    is simply correct.
  - `GROUP_MODE`, `FOOD_SUGGESTIONS`, `MAP_INTENT` were never in the class either: the
    first is the group-chat pilot behind `GROUP_CHAT_DESIGN.md`, the latter two are
    additionally gated on `TOMTOM_ENABLED` so flipping them is a no-op without a key.
  Confirmed unset in all six live `.env` files (owner-run VPS check, 2026-07-28), so the
  flags genuinely are off — they are off *on purpose*. See constraints C10: an
  unexplained default is not the same as an unintended one.

- **"Add a prompt-assembly style rule to `bot-code-invariants`" — rejected 2026-08-01,
  do not re-open.** Considered alongside 2.4 after `ShopDevX/adeptlydev` b6d7437 (a
  TypeScript repo replacing ~30-call `lines.push()` chains with template literals).
  Rejected on three grounds. (1) **The problem does not exist here:** static prompt text
  lives in `preset.txt`, the character cards, and the preset layers — already single
  blocks. The `.append()` chains in bot.py are genuinely conditional assembly, which is
  what that commit *kept*, not what it removed. (2) **Zero occurrences**, against a
  standing bar of two — the whole point of the two-occurrence rule is not to build
  guardrails from imagination. (3) **Dilution:** all 17 `bot-code-invariants` rules trace
  to a real incident (concurrency corruption, the memory-hallucination bug, the
  phantom-process killer, PTB overriding `signal.signal`). A speculative rule 18 makes the
  file skimmable rather than binding, which costs the 17 that were paid for in outages.
  An eval was rejected for the same reason plus C14 — a scanner cannot distinguish static
  concatenation from correct conditional assembly. 2.4's refactor *is* the guardrail: it
  removes the mixed-shape example that would have taught the wrong pattern.
- `/rollback` command — `bot.py.bak` + shell already covers it; a bad bot.py can't be
  trusted to run its own rollback anyway.
- Group ledger pruning / bot liveness heartbeats — rotation already exists; liveness
  adds machinery the claim-file design deliberately avoids (a down bot just loses
  claims).
- "Unit tests, DRY_RUN" — test suite exists (95 tests); DRY_RUN adds a second untested
  code path to every send site for little value on a 1-user fleet.
- Self-evolution ideas (closeness score, auto inside-jokes, live self-image updates)
  — product direction, not audit debt; revisit deliberately, not as a checklist.

---

## Sequencing

| Phase | Items | Status |
|---|---|---|
| ~~**Now**~~ | ~~1.1 watchdog→repo, 1.3 fleet-status, 2.3 card sync, 3.1 voice symmetry, 1.4 alerts~~ | ✅ All shipped (v2026-07-06.3) |
| ~~**Next**~~ | ~~2.1 test suite, 2.2 new-bot.sh, 3.2 shared world, 3.3 semantic recall~~ | ✅ All shipped (v2026-07-06.4–5) |
| ~~**Someday**~~ | ~~3.4 group chat~~ | ✅ Shipped (v2026-07-10.1) after 4-round design review |
| ~~**Next**~~ | ~~4.1 memory auditor, 4.3 robustness leftovers~~ | ✅ Shipped as R1/R3 (v2026-07-11.1, .3) |
| ~~**Someday**~~ | ~~4.2 availability awareness~~ | ✅ Shipped as R2 (v2026-07-11.2) |
| ~~**Now**~~ | ~~1.2 VPS Phase 2 — pilot jules~~ | **Rollout complete, not just the pilot.** All seven instances (nora, bonnie, cass, emily, priya, jules, migrated 2026-07-26; marcus stood up directly on the VPS 2026-07-29) run under systemd — the Termux phone is empty. Formal done-when isn't fully closed yet: the 14-day healthcheck soak that started 2026-07-26 runs through **2026-08-09**, and several 1.2 cleanup-batch checkboxes are still open (phone-side `~/jules-migrate.tar.gz` and per-instance `~/<name>-bot/` removal, `HEALTHCHECK_URL` re-pointed per instance). OPS_MANUAL's "VPS operations" section and marking CLAUDE.md's Termux quirks historical are both done (2026-07-26). |
| ~~**Next**~~ | ~~3.5 TomTom Phase 2 — generalized map intent~~ | ✅ Shipped (v2026-07-17.1, `MAP_INTENT`) |
| ~~**Next**~~ | ~~3.6 schedule-driven unavailability, then 3.7 fatigue + silence license + day-mood residue~~ | ✅ Shipped (v2026-07-18.2, .3) same day as the reviews that sourced them |
| ~~**Next**~~ | ~~1.6 lock the `vps-sync.sh` bot.py swap~~ | **Shipped 2026-08-01** — `flock` plus a fatal backup, closing the other half of the concurrent-deploy bug bot.py fixed in v2026-07-25.11. Locking mechanism break-tested in isolation (held lock correctly rejects a second `flock -n`, releases cleanly after). **Not fully closed**: the item's own done-when requires racing real `vps-sync.sh` runs on the VPS, which this session couldn't do — needs that confirmation before treating it as done, not just shipped. |

Execution maps onto the agent system: builder implements one item per dispatch,
qa-engineer verifies against each item's "done when", research-scout owns the 3.3 gate,
adversarial-critic reviews the 3.4 design doc, and every bot.py-touching item ships
with the usual BOT_VERSION bump + changelog entry (the delivery gate enforces it).
