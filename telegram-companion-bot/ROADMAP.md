# Roadmap — telegram-companion-bot

Written 2026-07-06 from a code survey of bot.py v2026-07-05.12 (7,626 lines), the
changelog, and CLAUDE.md. Each item names its evidence — why it's on the list — plus
effort (S/M/L), risk, and what "done" means. Ordered by track, sequenced at the bottom.

**Deliberate non-goal, recorded to prevent future refactor urges:** bot.py stays a
single application entrypoint. Immutable releases no longer depend on an in-place file
swap, but all seven instances still intentionally run the same entrypoint; the monolith's
real cost — regressions in pure logic — is covered by Track 2.1 instead.

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

### 1.6 ~~Lock the vps-sync.sh bot.py swap~~ ✅ (shipped + VPS race-confirmed 2026-08-01)
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
- **Shipped and closed 2026-08-01** (see CHANGELOG "vps-sync.sh's bot.py swap is now
  locked"): the `flock` and the fatal backup are both in `deploy/vps-sync.sh`.
  **Done-when satisfied on the real VPS, owner-run**, in two rounds — the first round
  raced the *pre-fix* script by construction (a sync's own checkout-reset is its first
  action, so the very first invocation after merging necessarily starts from whatever
  was already on disk) and surfaced a real git-level ref-lock collision between the two
  concurrent fetches instead, which the second round's winner resolved onto
  `a99e3e6`. The second round raced the now-current, actually-locked script: `cass`
  hit the flock and exited 1 with the intended message before its own `git fetch` ever
  ran; `bonnie` completed normally end-to-end (fetch, compile, backup, swap, restart,
  full hash + STARTUP AUDIT verification); `bot.py.bak`'s md5 after the race matched a
  baseline taken *before* the race exactly — proof it holds the genuinely-previous
  version, not a race-corrupted copy of the new code.

### 1.7 ~~Exact dependency lock + immutable releases~~ ✅ (shipped 2026-08-24)
- **Evidence:** CI and the VPS independently resolved broad ranges, deploys mutated one
  shared venv, and rollback covered only `bot.py`. The 2026-08-10 numpy incident proved
  the dependency side could leave default-on features inert fleet-wide.
- **Shipped:** a Python 3.12 hashed lock shared by CI and VPS; fatal install + `pip check`;
  lock-addressed immutable dependency layers; full-git-SHA code releases; atomic
  `current`/`previous` pointers; host-side rollback through `vps-sync.sh --rollback`.
  `immutable-release-contract` pins the cross-file contract.
- **Boundary:** release selection is still host-wide. Per-instance pointers and canary
  promotion are the next architecture item, not silently folded into this one.
- **Migration repair 2026-08-24:** the first selector-aware Nora canary proved the
  legacy-package guard could detect Garmin but could never be satisfied: it inspected
  only the old venv, not the replacement lock. `garminconnect` is now declared and
  hashed, both deploy paths condition the fatal on its absence from the new lock, and
  the release-contract checker derives and pins that old-to-new dependency class.

### 1.8 ~~Per-instance canary release selectors~~ ✅ (shipped 2026-08-24)
- **Evidence:** item 1.7 made code and dependencies reproducible, but one host-wide
  `current` pointer still moved all seven bots at once. A bad runtime release therefore
  had no bounded canary blast radius, and rollback necessarily restarted the whole fleet.
- **Shipped:** root-owned `selectors/<instance>/current` and `previous` pointers;
  instance-scoped deploy and rollback; explicit `--promote <canary>` for moving the
  tested immutable code/runtime release to all active bots. The systemd unit resolves
  `%i` through the selector store, and first migration seeds selectors without exposing
  them to the bot user. `immutable-release-contract` pins the selector, promotion, and
  rollback paths.

### 1.9 ~~Structured fleet operation events~~ ✅ (shipped v2026-08-24.3)
- **Evidence:** provider latency, fallback use, scheduled-job health, and Telegram
  delivery were recorded as unrelated prose lines or not recorded at all. Comparing
  the seven instances required ad-hoc grep and could not answer the same question at
  every boundary.
- **Shipped:** one payload-free JSON schema emitted to journald at shared model,
  external-fetch, scheduled-job, and delivery choke points; stable provider and error
  categories; a default-on `OP_EVENTS` kill switch; and `deploy/fleet_events.py`, which
  reports per-instance/provider call counts, outcomes, p50/p95 latency, and fallback
  rates from a bounded journal query. No hosted observability dependency was added.

### 1.10 ~~Incremental transactional machine-state persistence~~ ✅ (shipped v2026-08-24.4)
- **Evidence:** machine-managed mutable state was spread across whole-document JSON
  stores. Atomic rename avoids a torn file but does not provide a transactional store,
  schema namespace, or durable commit boundary for later state migrations.
- **First slice:** reminders only, selected because they are machine-managed and
  operationally meaningful without containing character or owner-authored content.
  One per-instance `machine-state.sqlite3` uses a namespaced key/value schema, WAL, and
  full synchronous commits. A forced child-process exit before commit leaves the prior
  value intact in the regression suite.
- **Migration/rollback:** first startup imports `reminders.json`, retains a dated
  pre-migration copy, verifies database readback, and continually refreshes the readable
  JSON export. `REMINDERS_SQLITE=0` is the one-release rollback path. Cards, presets,
  memories, `people.txt`, `projects.txt`, `schedule.txt`, `life.txt`, and `day.txt` stay
  file-backed. Future stores migrate separately only after this slice has fleet evidence.

### 1.11 ~~Per-instance systemd sandbox~~ ✅ (shipped 2026-08-24)
- **Evidence:** every bot ran as the same Unix user under a service template with no
  systemd sandbox. Instance directories organized state but did not prevent one
  compromised process from modifying a sibling or the host.
- **Shipped:** an instance-scoped root-owned drop-in makes the host read-only and grants
  writes only to that bot's directory, shared ledgers, and `world.txt`; removes ambient
  capabilities and privilege gain; restricts devices, kernel controls, namespaces,
  process visibility, realtime scheduling, and network address families. Each unit gets
  an instance-local `HOME` for PDF scratch files and Garmin tokens.
- **Rollout/rollback:** a normal deploy canaries the policy on one bot; `--promote`
  applies the exact tested drop-in to active units and health-checks all of them;
  `--rollback-hardening` removes only one instance's policy without moving its release.
- **Boundary:** syscall allowlisting, private networking, and executable-memory denial
  remain deferred until representative media and native-extension traces can prove them.

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

### 2.4 ~~Selfie prompt constants hoisted~~ ✅ (shipped v2026-08-01.1, riding with 1.6 as predicted)
- **What:** the anatomy rule and the realism/SFW rule were inline literals appended
  mid-`build_selfie_prompt`; they are now `_SELFIE_ANATOMY_RULE` and
  `_SELFIE_REALISM_RULE`, sitting with the other `SELFIE_*` pools. No behavior change
  (640-prompt before/after diff, byte-identical). Two tests pin it, both break-tested RED.
- **Why it was worth doing:** these two fragments are the ones you edit when the image
  model returns extra limbs or a filter-tripped frame, and finding them meant reading a
  70-line function instead of grepping a constant name.
- **Shipped:** parked on 2026-08-01 as v2026-08-01.1 specifically to ride the next
  functional release rather than justify a seven-instance deploy alone — 1.6 (v2026-08-01
  merge to main) was that carrier, exactly as predicted when it was parked. All seven
  instances are on `v2026-08-01.3` or later, which supersedes it.
- **Origin:** prompted by `ShopDevX/adeptlydev` b6d7437 (push-chains → template literals).
  The generalized version of that lesson was **considered and rejected** as an invariant —
  see "Rejected or already covered" below.

### 2.5 ~~Correct the stale TomTom instance list in bot.py~~ ✅ (shipped v2026-08-10.3, rode /place as predicted)

**Resolved by naming no instances at all**, which was the option flagged when this was
parked: the header now points at each `.env` and the `maps=` field in `/audit`. A roster
that cannot go stale beats one that is correct today. Original notes below.

`bot.py`'s TomTom section header reads `# --- TomTom Maps (routing + place/POI search;
Nora, Emily, Priya) ---`. On 2026-08-10 the owner provisioned Emily's key onto **bonnie,
cass, jules and marcus** as well (with `TOMTOM_TRAVEL_MODE=car` for cass, jules and marcus;
bonnie left unset, which defaults to car), so **all seven instances now have TomTom** and
that comment is wrong.

Low stakes but not zero: it is the kind of in-code roster a session trusts without checking,
and CLAUDE.md already carries a scar from a "quick reference" list that drifted, omitted
seven skills and misrouted a session.

**Deliberately parked, not skipped.** A comment-only edit still modifies `bot.py`, so the
delivery gate requires a `BOT_VERSION` bump and a changelog entry, which means a
seven-instance deploy for a line of prose. Fold it into the next real `bot.py` change —
the same "ride the next functional release" reasoning as 2.4 above, which worked.

**While you are there:** the roster belongs in exactly one place. Consider whether the
comment should name instances at all rather than say "per-instance, see each `.env`" —
a list that cannot go stale beats a list that is correct today.

### 2.6 ~~Declarative command and job registries~~ ✅ (second slice shipped v2026-08-24.5)

- **Evidence:** command handler registration, Telegram autocomplete entries, capability
  gates, and scheduled jobs were expressed in separate branches. The existing parity
  test could compare literal `CommandHandler` calls with menu lists, but it could not make
  one feature record authoritative for both paths or cover its job schedules.
- **Shipped:** immutable `CommandSpec` and `JobSpec` records plus shared registration
  helpers, with the health/Garmin family migrated first. Its three command records drive
  handlers and menu entries; its job records cover multiple daily pulls, startup refresh,
  stress and Body Battery polling, and the resting-HR daily check. Tests preserve parity
  across the legacy and registry paths and verify every schedule shape.
- **Second slice:** the nine maps, places, local-alert, and WSDOT commands now use the
  same records for callbacks, descriptions, registration, and menu visibility. It adds
  the mixed-gate case: WSDOT handlers follow capability while their menu entries follow
  the live `TRAFFIC_ENABLED` switch.
- **Boundary:** this stays incremental, not a whole-file rewrite. Feature and prompt
  registries remain separate changes; the rest of the direct command registrations move
  only as cohesive families, with behavior pinned before each migration.

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
- **Banter tuning ✅ (v2026-08-02.13):** the v1 caps made a back-and-forth impossible
  rather than rare (chain 2 with two bots = one reply per human message; the 20s send
  throttle sat inside the ~16s exchange round-trip and killed alternation on its own).
  Chain cap 6, base prob 0.5, gap 8s, budget 50, and a new `GROUP_CHAIN_DECAY` that
  shrinks the reply chance with exchange depth — including for addressed messages,
  which no longer bypass the gate. `GROUP_BANTER=0` restores every v1 number.

### 3.5 ~~TomTom Maps~~ ✅ (all phases shipped; three follow-ups explicitly deferred, not open)
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
  **Default ON since v2026-08-10.8**, with `MAP_INTENT=0` and `/features mapintent off`
  as kill switches. It shipped default-off as a pilot and was still unset on all seven
  weeks later, so the feature was built, tested, documented and dark. `mapintent` and
  `foodsuggestions` are `_FEATURES` entries now, so `/audit` and `/features` can report
  a flag whose state was previously readable only by grepping seven `.env` files.
  **The over-firing watch is now readable (v2026-08-10.10).** `/audit` carries a
  `Map intent:` line reporting fires over messages-considered (`2/9 messages (22%) — 1
  route, 1 nearby`), reset daily, with no-pin fires counted separately. The deferred
  per-chat cooldown stays unbuilt on purpose: this ROADMAP conditions it on the log
  showing over-firing, and the rate had never been observable — the flag was off
  everywhere until v2026-08-10.8, and reading it meant grepping journalctl. Decide on the
  cooldown from a week of that line, not from a guess.

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
     planning-leak class — Priya's leaked monologue). **Since v2026-08-03.1 the reply
     path also refuses reasoning-shaped completions outright** (`REASONING_LEAK_GUARD`);
     a hidden thinking call must not route its output through `generate_reply`, or the
     guard will correctly reject the thought it was asked to produce.
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
- **Correction, 2026-08-02: "fleet-wide" was true of cass, jules and marcus only.** The
  `/audit` sweep run the next day (see CHANGELOG v2026-08-02.10) found **nora, bonnie,
  emily and priya still loading the monolithic `preset.txt`** — every per-character layer
  already existed in the repo, so the gap was four `.env` lines, not missing content.
  Bonnie and emily were switched over during that pass; nora and priya followed on
  2026-08-02 with the `v2026-08-02.12` deploy (nora `core,rp,explicit,stepped,nora`;
  priya `core,stepped,priya`), owner-reported deployed and verified. **The lesson is the
  one the previous bullet half-anticipated:** an owner statement settles intent, not
  per-instance config — the `Preset layers:` line named there as the fallback check was
  in fact the only thing that could have caught this, and running it took one day. All
  seven are layered as of this date; re-confirm per instance rather than trusting this
  sentence if it ever matters again.
- `preset.txt` remains voice-critical and deliberately tuned (v2026-07-18.1's anti-echo
  work) — any *further* layer change (new content, not just switching among what already
  exists) still goes through the owner, same as any other voice edit.

### 3.14 ~~Port the banned-rhetoric block from Chimera v2~~ ✅ (shipped 2026-08-01, into `preset-rp.txt`)
- **Evidence:** the 2026-07-25 review of Writer's Block 5 against the root Chimera preset
  (`Chimera_v1_borrow-review_WritersBlock5.md`) found that naming the specific LLM
  constructions beats describing them. Chimera's old rule — *"write the positive action:
  'She looks away' rather than 'She doesn't look at him'"* — catches simple negation only.
  It misses `not X but Y`, which is the loudest machine tell. Shipped to the SillyTavern
  side in `Chimera_v2.json`; the fleet never got it.
- **What was ported:** the four named bans, taken verbatim from `Chimera_v2.json`'s own
  `<prose_craft>` block — contrastive negation (`not X but Y`),
  false-correction/epanorthosis (`It was X. No — Y.`), negation-as-atmosphere
  (`it wasn't the wind`), and litotes (`not unkind`) — each with its one-line example, as
  a single paragraph in the file's existing Bad/Good example style. ~60 tokens. The rest
  of the Chimera diff (hooks, the relationship ladder, the assistants, the CoT tasks)
  deliberately not ported — scene-roleplay machinery, wrong shape for a texting companion.
- **Target changed from the original plan, and this is the finding worth recording:**
  this was drafted against `preset-core.txt` (reasoned as "universal prose hygiene,"
  reaching all seven instances via 3.13's shipped layering). **A roleplay simulation
  before shipping caught that this was wrong.** Same test message run against both
  Priya (core+stepped+priya, no narration) and Jules (core+rp+explicit+stepped+jules,
  narrates in third person):
  - **Priya, before:** *"yeah. i'm fine. not mad or anything, just tired."* — a
    completely natural first-person texting hedge that happens to share contrastive-
    negation's surface shape. Applied to `preset-core.txt` under zero tolerance, the
    rule would have forced cutting it — sanding a real human speech habit to satisfy a
    rule written for a different problem. **False positive.**
  - **Jules, before:** narration reaching for *"It wasn't nothing, though"* in a
    restraint beat — genuinely the tell Chimera targets. **After:** *"It mattered."* —
    tighter, and arguably more in-character (`preset-jules.txt`: her resolution is never
    a soft line). **Correct catch.**
  - Root cause: Chimera's bans describe *third-person narrated prose*, not first-person
    conversational hedging. `preset-core.txt` is shared by narrating and non-narrating
    instances alike; `preset-rp.txt` (the narration layer, per 3.13) is loaded only by
    instances that actually narrate — nora, bonnie, emily, jules, marcus, never cass or
    priya. Moving the target to `preset-rp.txt` gets the correct scoping for free, from
    the layer boundary already built in 3.13, with no carve-out text to write or
    maintain.
- **Shipped into `preset-rp.txt`'s `[NARRATION]` section**, right after the opening
  paragraph. Diff is isolated to exactly that addition (`git diff` confirmed). Validated:
  `bash .claude/evals/run-evals.sh` 32/32 green (secret-scan and the rest unaffected —
  this is a plain-text preset layer, not JSON).
- **Done =** met. The block is in `preset-rp.txt`; the before/after verification the
  original plan called for was done as a roleplay simulation against Priya and Jules
  *before* committing to a target, which is stronger evidence than a post-hoc
  `/audit`-and-restart check would have been — it caught a wrong target, not just
  confirmed a right one. Still needs: `vps-sync.sh` re-run on the five instances that
  load `preset-rp.txt` to actually pick this up (see `deploy-and-verify-fleet`).

### 3.15 ~~Safety: distress detection~~ ✅ (shipped v2026-08-04.1, `SAFETY_ENABLED`)
- **History:** built once already (`d141e84`, 2026-06-29) on a branch that was never
  merged (`claude/push-to-repo-7i2f3c`, 509 commits stale) and silently vanished from
  institutional memory for over a month — see the operational-log 2026-08-04 entry.
  Reimplemented against current `bot.py` rather than cherry-picked.
- **What it does:** `_assess_safety` screens each incoming private-chat message
  off-loop (cheap classifier call, no character/history context) for genuine acute
  distress — suicidal thoughts, self-harm, real danger — as opposed to roleplay, dark
  humor, or ordinary venting. On a positive read, the performative inner-voice step is
  skipped and a high-salience system message (`_safety_prompt`) tells her to drop the
  act and respond with real care, mentioning `SAFETY_RESOURCES` (988 Lifeline by
  default) if it fits. On by default, independent of `INNER_VOICE_ENABLED`.
- **bot-code-invariants rule 3 exception (owner-approved 2026-08-04):** a genuine new
  per-message LLM call, justified because it carries no character/history context (a
  small fraction of a normal reply's token cost) and because the sanctioned extension
  point (`post_reply_analysis`) fires after the reply is already sent, which would make
  a safety feature one message late. Documented in `bot-code-invariants` itself as a
  second carve-out next to `MEMORY_SEMANTIC_LIVE`.
- **Scope:** `handle_message` (private text) only, matching what the original branch
  actually shipped — not group/voice/photo paths.

### 3.16 ~~Four more features from the same abandoned branch~~ ✅ (shipped v2026-08-04.2–.6)
- **History:** same source as 3.15 — `claude/push-to-repo-7i2f3c`, built June 2026,
  never merged. Found via a follow-up audit of the branch's full commit list after
  3.15 turned up one feature; ROADMAP 3.10 had already flagged some of these by name
  as unported ("on-this-day reminiscing, offline life events, adaptive texting-style
  mirroring, `acoustic_ears`, `/diag`") without a session picking them up until now.
- **Adaptive texting-style mirroring ✅ (v2026-08-04.2, `STYLE_MIRROR`):** passively
  reads the user's recent texting habits (length, emoji, lowercase, textspeak) and
  nudges her register to subtly match. Zero model calls — pure heuristics, no
  rule-3 question.
- **Offline life events ✅ (v2026-08-04.3, `LIFE_SIM_ENABLED`):** generates one
  concrete event in her own world a couple times a day, grounded in schedule/people/
  projects/life-arc via a cheap chat model call. `/news`, `/newsnow`. All helper
  functions it depends on already existed on `main` — reused, not rebuilt.
- **Voice-note acoustic tone analysis ✅ (v2026-08-04.4, `VOICE_TONE_ENABLED`):**
  local FFT pace/volume/brightness/pause read via vendored `acoustic_ears.py`
  (MIT, `menelly/AI_Ears`), no network call. First thing in the fleet to need numpy
  as a real (not commented-optional) dependency — also required `vps-sync.sh` to
  gain an explicit sync line, since it only copies named files, not a directory sync.
- **`/diag` ✅ (v2026-08-04.5, extended in .6):** scoped down from the original,
  not straight-ported — its log-error tail was redundant with `/errors`, its
  log-rotation half was Termux-era (superseded by `RotatingFileHandler` since the
  systemd migration), and its RHR monitor had already shipped separately. What
  remained: a compact status line for this session's behavior toggles, a different
  axis from `/audit`'s `_FEATURES` dict, not a duplicate of it.
- **Episodic recall + on-this-day reminiscing ✅ (v2026-08-04.6, `EPISODIC_RECALL`/
  `ONTHISDAY_ENABLED`):** the deepest one — rewritten against `main`'s actual
  embedding primitives (`EMBEDDING_MODEL`/`_embed_text`), since the abandoned
  branch's own embedding infrastructure doesn't exist here. Archives conversation
  that ages out of the verbatim window as embedded chunks; reuses the per-turn query
  vector for zero extra embed cost; surfaces the closest past exchange above a
  similarity floor, time-gated so the live window never echoes itself. On top of
  that, a once-daily job resurfaces an archived episode on its ~1mo/6mo/1yr
  anniversary. `/episodes` shows the archive size.
- **Deliberately not ported:** two further commits on the same branch —
  archiving sent photos as episodes, and an optional cross-encoder reranker for
  episodic recall — are enhancements to 3.16's episodic recall, not required for
  on-this-day to work. Not requested; flagged here as known follow-ups if wanted.

### 3.18 ~~"Open now" for /food and FOOD_SUGGESTIONS~~ ✅ (shipped v2026-08-10.1, `FOOD_OPEN_HOURS`)

**Shipped, but the design below is NOT what shipped — read the changelog entry.** The
"earliest date in the payload is the POI's today" premise recorded here is **still
unverified** — neither confirmed nor, despite a 2026-08-10 changelog claim since corrected,
refuted. That claim compared the response's date against a session date in an unestablished
timezone. What shipped does not depend on the premise either way. What shipped asks only whether
some range brackets now, and gates the verdict on a range falling on the instance's local
date. The blocker notes below are kept because the MCP-vs-REST finding outlived the item:
**the MCP tools silently omit `openingHours`, so they are not a probe for what the fleet key
can fetch.**

<details><summary>Original blocked-item notes (historical)</summary>



Approved to build, not built: **no session can currently see a TomTom opening-hours
response**, and writing the parser from remembered API docs is the thing CLAUDE.md's Stack
section exists to forbid. Three routes were tried on 2026-08-09 and all three are closed:
the TomTom MCP connector's token expired mid-session; `api.tomtom.com` needs the fleet key,
which no session has; and `developer.tomtom.com` is blocked by egress policy (`curl` gets
`403 CONNECT tunnel failed` through the proxy — the same wall as `nano-gpt.com`).

**Connector retried later the same day, and the answer got sharper — read this before
trying again.** The token was refreshed and the calls went through. Across two queries
(`coffee` and `Starbucks`, near downtown Seattle), **12 of 12 POIs came back with no
`openingHours` field at all**, with `response_detail=full` and `openingHours=nextSevenDays`
accepted without error. Not a trimming artifact: those same responses carry `entryPoints`,
`brands`, `extendedPostalCode`, `localizedCategories` and `countryCodeISO3`. The field is
specifically absent — the identical silent-absence seen with `timeZone=iana`.

Two live explanations, with very different consequences:

1. **The MCP wrapper drops the field.** The fleet's own key would still return it and the
   feature is fine.
2. **This TomTom account tier does not license POI opening-hours data.** Then the fleet key
   will not return it either, and this item is **not buildable as specified** — it would
   need a different data source, and should be closed rather than left open.

**The one command that settles it** (host: VPS, as root — it reads the fleet key from an
instance `.env`, so it works nowhere else):

```bash
KEY=$(grep -oP '^TOMTOM_API_KEY=\K.*' /opt/telegram-bots/priya/.env)
curl -sS "https://api.tomtom.com/search/2/search/coffee.json?key=$KEY&lat=47.6062&lon=-122.3321&radius=2000&limit=3&openingHours=nextSevenDays" \
  | python3 -m json.tool | grep -A12 -i openingHours
```

Empty output means explanation 2 — close this item. Output means explanation 1, and that
same JSON is the response shape the parser needs. **If it returns HTTP 400, suspect the
parameter name**: `bot.py`'s routing code already carries a scar where the raw REST spelling
(`fastest`) differs from the MCP tool's (`fast`), and MCP parameter names are not evidence
about the REST API. The key is interpolated into the URL, so it lands in shell history —
clear it afterwards if that matters on that box.

**The problem it fixes.** `FOOD_SUGGESTIONS` pre-fetches real nearby restaurants and hands
them to the model with no idea whether any are open, so at 11pm she can recommend a place
that shut at nine. That is the failure that makes her sound like she is reading a directory
rather than knowing the neighbourhood. `openingHours=nextSevenDays` is a parameter on the
search endpoint already called by `_fetch_tomtom_search`; no new endpoint is needed.

**The tz-safe design, worked out and worth keeping — but check its premise first.**
ROADMAP 3.5 parked this as needing a "tz-safe opening-hours parse" without saying what the
difficulty was. The difficulty below is *consistent with* that phrase and is what a session
in 2026-08 reconstructed; it is not quoted from the original note, so do not treat it as the
recorded intent. The problem as reconstructed: hours come back in the POI's local time and
the bot only knows its own `TZ`, so computing "open now" against bot-local time is silently
wrong whenever the user has shared a location in another timezone.

The cheap resolution uses data the response already carries — **on one load-bearing premise
that has not been verified against TomTom.** The `nextSevenDays` semantics below are read
off the **TomTom MCP tool's parameter description** ("shows the opening hours for next week,
starting with the current day in the local time of the POI"), which is a wrapper's account
of the API, not the API's own documentation — that host is blocked by egress policy. If the
raw REST endpoint orders or dates differently, the gate is unsound and the whole design
needs rework. **Confirm it against the same real response that unblocks the parser.**

Taking that premise: the earliest date in the payload is the POI's today. Compare it to the
bot's local today:

- **Dates differ** → the POI is in another timezone. Render the hours as text and emit **no
  open/closed verdict** — refuse the judgement rather than ship a wrong one.
- **Dates match** → close enough for the comparison to mean something; compute open/closed
  against the bot's clock.

State plainly what that check does and does not prove (C8): matching dates do not prove
matching timezones, they bound the error to within a day. It is a cheap sanity gate, not a
timezone lookup. `timeZone=iana` was tested as the real fix and returned **no timezone
object** on reverse-geocode at full detail — unverified, possibly POI-scoped, possibly
dropped by the MCP wrapper; worth one more test against a named POI before relying on it.

</details>

### 3.19 ~~Real-world morning news~~ ✅ (shipped v2026-08-24.1, `MORNING_NEWS`)

The weekday morning briefing now adds up to three recent RSS/Atom stories: local,
Washington-or-national, and technology/security/economy. Feed parsing, age filtering, duplicate
removal, and source selection are deterministic; no new model call is made. Defaults and
the per-instance feed override are documented in `.env.example`.

### 3.17 ~~Preserve small worn face items in the selfie face lock~~ ✅ (shipped v2026-08-10.3, rode /place)

**Shipped as specified, effect unverified.** The clause names the category — "anything
small she wears on her face, ears or hair — a forehead mark, a stud, a hoop, a clip" —
conditionally both ways, no character's trait. No session can generate an image to check
it, and priya runs `gemini-3-pro-image-preview`, which no face-lock A/B has ever covered.
**The braid stayed out of scope** for the reason recorded below. Original spec follows.

`_SELFIE_PRESERVE_RULE` enumerates what an edit model must copy from the reference photo
— face shape, bone structure, eyes, nose, mouth, brows, skin tone, skin marks, hairline,
hair colour and texture, apparent age — and then carries **one dedicated sentence for
eyewear**, phrased conditionally both ways ("if she is wearing glasses there she is
wearing those same glasses here; if she is wearing none, add none"). That sentence exists
because Emily's glasses kept vanishing (v2026-08-03.2).

Nothing covers the same class of item elsewhere on the face. `grep` finds "bindi" exactly
once in the whole repo — `priya/appearance.txt` — and never in `bot.py`, so a bindi is
governed by no rule at all: dropping it, adding one, or moving it violates nothing. It is
not a "mark on her skin" in the sense the rule means, any more than glasses are.

**Observed, not theorised (2026-08-09):** across six selfies from one session on Priya's
re-cropped reference, the bindi is clearly present in about half and clearly absent in the
rest. Same reference, same prompt, inconsistent result. (Small feature read off compressed
images — the count is approximate, the inconsistency is not.)

**The fix, when it is taken up:** widen the eyewear sentence into one clause covering small
worn or applied face items — eyewear, forehead marks, piercings, earrings — stated
conditionally both ways and category-generic. It must never assert that *she* has any of
them: that is the character-bleed trap of v2026-08-01.8's courier jacket and .9's
hardcoded freckles, and `test_shared_prompt_hardcodes_no_character_specific_feature` pins
it (conditional phrasing is why "glasses" is allowed to appear at all).

**Deliberately NOT in scope: the braid.** It is absent from five of the same six images,
but `SELFIE_ACTIVITIES` includes "just woke up, hair a mess" and "fresh out of the shower
with damp hair". Pinning a hairstyle would make the prompt contradict itself, which hands
back exactly the latitude these rules exist to remove (v2026-08-03.2's reasoning for
keeping the clarity rule compatible with every framing). Hair colour and texture are
already pinned; style is legitimately variable.

**Also seen once in the same six:** the beautify regression the rule already names —
slimmer face, heavy eye makeup, restyled — in one draw of six. One sample; not enough to
act on, recorded so a second sighting is recognised as a pattern rather than re-diagnosed.

**Verification is a live A/B, not a test run.** No session container has a
`GEMINI_API_KEY`, and the provider hosts are blocked by egress policy, so a prompt change
here cannot be proven from the repo. Priya runs `gemini-3-pro-image-preview`, and **no
face-lock A/B in the changelog was ever run against that model** — all 22 images in
v2026-08-03.2 predate the fleet's move to it. Shipping prompt text and calling it fixed is
what cost two releases in August.

---

## Track 4 — Audit backlog & memory integrity (from AUDIT-2026-07-10.md)

The 2026-07-10 audit (external Deepseek pass + verification + two user-observed bugs)
shipped its confirmed fixes as v2026-07-10.2. **Track 4 is complete as of 2026-08-10** —
4.1 through 4.4 all shipped, the last piece being 4.4's per-instance `.env` rollout. Kept
here rather than deleted because the "Rejected or already covered" section below is still
load-bearing: it records claims already ruled invalid, and a future audit that re-raises
them should find the reasoning rather than re-litigate it. Specs are in
**`IMPROVEMENTS_PLAN.md`**:

### 4.1 ~~Memory auditor~~ ✅ (shipped as R1, v2026-07-11.1)
- Source-attached memories (`memory_meta.json`), quote grounding, confidence + review
  queue (`/reviewmem`), `/editmem` + `/sourcemem`, `[memcheck:]` correction flow,
  append-only memory audit log — per the IMPROVEMENTS_PLAN.md R1 spec. "Done when"
  met: a wrong memory is traceable and correctable from Telegram in under a minute.
  Follow-up memory-loop refinements shipped v2026-07-12.1–.2.
- **Quote grounding proves the evidence is real, never that the claim follows from it**
  — closed v2026-08-12.1 with an `unsupported` finding type in the weekly audit, judged
  against each entry's own stored quote. Auto-extracted memories only; `/remember`,
  `/editmem` and audit merges are ineligible by construction. Deliberately NOT fixed in
  `_quote_grounded`, which is on the reply path.

### 4.2 ~~Availability awareness~~ ✅ (shipped as R2, v2026-07-11.2)
- `/away` + `/back`, remote-default framing, auto-extraction via post-reply analysis
  (auto-away expires after `AWAY_AUTO_HOURS`), busy/working/driving vibe presets.

### 4.3 ~~Robustness leftovers~~ ✅ (shipped as R3, v2026-07-11.3)
- Atomic small-file writes (`_atomic_write_text`), `_last_request` pruning, config
  warnings surfaced in `/audit` (`_CONFIG_WARNINGS` — the useful core of the suggested
  `validate_config()`), persisted error counts, graceful drain, LLM usage counters.

*(R4 prompt hygiene, R5 UX, and R6 evolution experiments from the same plan shipped as
v2026-07-11.4–.6 — see IMPROVEMENTS_PLAN.md and CHANGELOG.md.)*

### 4.4 ~~Retune `MEMORY_TOKEN_BUDGET` in calibrated units~~ ✅ (code 2026-08-01; `.env` rollout completed 2026-08-10 — item fully closed)
- **Context:** v2026-07-26.2 made reported token counts real (provider `usage`, plus a
  calibration ratio for what can only be estimated). `MEMORY_TOKEN_BUDGET` was
  deliberately left on the raw `len//4` unit.
- **Why it was left:** it is a tuned *recall* knob, not a cost ceiling. Every value in
  every `.env` was picked against the raw unit, so switching to calibrated counts would
  fit fewer memory lines into the same nominal budget and change how much seven live
  characters remember — a personality change shipped as an accounting fix.
- **Owner-approved 2026-08-01**, with each instance's calibration ratio supplied from
  `/audit` (see `v2026-08-01.3` in CHANGELOG.md for the full table and the actual
  multiplied values). All seven cluster tightly at 0.90-0.93 — the risk this item was
  gated against was real in principle, small in practice for this fleet.
- **Shipped:** `triggered_memories()` now costs memory lines with `_tokens()` (calibrated)
  instead of `_est_tokens()` (raw). `TOKEN_CALIBRATION=0` reverts this to the raw unit
  too, same kill switch as every other calibrated figure — no new one needed. Regression
  test updated in place (`test_memory_budget_uses_calibrated_units`), break-tested RED
  before being trusted.
- **The 300 assumption is now CONFIRMED (owner-run check, 2026-08-10).** All seven `.env`
  files have no `MEMORY_TOKEN_BUDGET` line at all, so every instance is running on the
  in-code default of 300 and no instance carries an override. The v2026-08-01.3 table
  therefore applies verbatim: bonnie 273 · emily 270 · nora 276 · priya 276 · cass 273 ·
  marcus 273 · jules 279.
  *(The first check handed over for this returned a blank for all seven and could not tell
  "absent" from "set to empty" — its `|| echo` fallback tested `cut`'s exit status rather
  than `grep`'s. Re-run with the test on the grep itself. Noted because the blank output
  looked like an answer.)*
- **Done 2026-08-10 (owner-run):** all seven `.env` files now carry their own multiplied
  value — nora 276 · bonnie 273 · cass 273 · emily 270 · priya 276 · jules 279 ·
  marcus 273 — each backed up as `.env.bak.2026-08-10`, every instance restarted. No
  instance runs on the shared in-code default any more, so the item is closed rather than
  approximately closed. **This was the last open piece of Track 4.**
  Until that `.env` edit lands per instance, that instance is quietly running on the
  shared in-code default (also 300, now calibrated) rather than its own prior effective
  budget — close, given how tight the ratios are, but not exact.

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

  **`MAP_INTENT` left this list on 2026-08-10 (v2026-08-10.8) — the rejection still
  stands and this is not an exception to it.** What was rejected is a bulk flip as audit
  debt; what this text asks for instead is "revisit deliberately". A fleet-wide `.env`
  sweep found `MAP_INTENT` unset on **all seven**, including the three it was piloted on,
  and the owner flipped it to default-on in the same conversation. So the 2026-07-28
  reading was right that the flag was off and wrong that it was off *on purpose*: nothing
  could report its state, so "unset" was indistinguishable from "decided". That is the
  limit of a `.env` grep, not a fault in C10. `FOOD_SUGGESTIONS` and `GROUP_MODE` stay in
  the class, still off, still per-instance product decisions.

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

## Track 5-A — Proposed (lateral-thinking session, 2026-08-04, owner triage pending)

**Naming:** this is Track 5-A; the 2026-08-05 exploratory block below is Track 5-B.
**Status of this whole track: unreviewed.** These came out of a `random-stimulus`
lateral-thinking pass run against this roadmap (fed the full shipped list and the
"Rejected or already covered" sections above, specifically to avoid recombining what
already exists). They are ideas, not specs — no evidence from a code survey, no
owner sign-off, no effort/risk estimate beyond a rough guess. Track 3's items earned
their numbers from a code survey or an owner request; these have not, which is why
they're a separate track rather than appended to Track 3 as 3.17+. Promote an item to
Track 3 (with a real spec) only once the owner picks it.

### 5.1 Constancy override ("lighthouse")
- **Idea:** every Track 3 state-modulation feature (`FATIGUE_STATE`, day-mood residue,
  `SCHED_BUSY`, `STYLE_MIRROR`) is instance-authored — the user has no lever to ask for
  the unmodulated baseline. A command or detected phrase ("just be normal for a sec")
  temporarily suppresses all of them for one exchange.
- **Why it's not already covered:** every existing modulation knob makes the character
  *more* variable; none of them let the user dial back to flat on request. `/away` is
  the closest existing thing and it's about the user's own status, not the character's
  presentation.
- **Rough shape:** a suppression flag read at the same injection points that already
  check fatigue/busy/mirror state — no new state to compute, just a bypass. Effort: S.
- **Open question:** does suppressing mirror/mood read as caring or as "turning off
  personality on command" — needs a real exchange to judge, not just a design read.

### 5.2 Vigil mode for anticipated hard events
- **Idea:** when fact-extraction (already-shipped memory pipeline) picks up a scheduled
  hard thing ("surgery Tuesday", "court date Friday"), enter a quieter, denser-but-not-
  cheerful check-in register for that window — explicitly low-pressure, not demanding a
  reply.
- **Why it's not already covered:** `SAFETY_ENABLED` handles acute, emergent distress.
  Ordinary proactive check-ins are generic and date-agnostic. Neither distinguishes
  "she knows something hard is coming" from either of those.
- **Rough shape:** reuses existing extraction + the proactive-send scheduler; needs a
  register/tone change at the injection point plus a start/end window. Effort: M.
- **Open question:** false-trigger risk on loosely worded "hard events" — needs the same
  conservative-parse discipline 3.6 used for schedule blocks.

### 5.3 Standing life-project with decay
- **5.3-A shipped (v2026-09-03.3).** One standing project per instance, persisted in
  `project.json` with momentum float (0.0-1.0) and stage (thriving/active/stalling/abandoned).
  Engagement detection via `post_reply_analysis` (no new LLM calls), nightly decay in
  `_rotate_day_context`, stage-aware context injection in `assemble_messages`. `/project`
  command to set/view/clear. Kill switch `LIFE_PROJECT` (default OFF — Track 5 pilot).
- **Idea:** a slow-arc thread in the character's own life (learning guitar, training for
  a race) that persists and drifts on its own — decaying or changing direction if
  neglected, growing if the user asks about it. Continuous state, not a discrete event.
- **Why it's not already covered:** `LIFE_SIM_ENABLED` generates discrete daily events;
  nothing has continuous, user-attention-responsive state. This is a genuinely different
  primitive, not a variant of the offline-life-events generator.
- **Rough shape:** new persisted state (project, momentum float, last-mentioned
  timestamp), a decay function, narrative surfacing through the existing day-generation
  or reply-injection path. Effort: M/L — the biggest new-state item in this batch.
- **Considered and NOT included as part of this idea:** a "fork a character" reading of
  the same stimulus (spin up a second instance from a memory snapshot that then
  diverges) — adjacent to the already-rejected self-evolution class above. Flagged so it
  doesn't come back framed as something new.

### 5.4 In-character introspection query ("signal vs noise")
- **Idea:** a user-facing, in-voice way to ask what the character currently thinks is
  going on with the user — mood, recently salient memory, what she's noticed — surfaced
  on request rather than only inferred from her replies.
- **Why it's not already covered:** `/audit` exposes system state to the operator, not
  the character's read on the user, and not in-voice. This is a different consumer.
- **Rough shape:** template already-computed state (mood, fatigue, recent-memory
  salience) into an in-voice answer; likely no new LLM call needed. Effort: S/M.
- **Open question / risk:** could read as a settings panel rather than genuine
  reflection and break immersion — depends entirely on execution, not the concept.

### 5.5 Chronotype + user-clock noticing
- **Idea:** a static per-character trait (night owl vs. early bird) shaping typing-delay
  and tone by time of day, plus passive noticing when the *user's* message timestamps
  repeatedly land at odd local hours ("you're up weird late again").
- **Why it's not already covered:** `FATIGUE_STATE` is load-driven, `SCHED_BUSY` is
  event-driven; neither tracks a body-clock axis, and nothing observes the user's own
  timing patterns.
- **Rough shape:** zero LLM calls — a fixed trait plus arithmetic on existing message
  timestamps, same shape as `STYLE_MIRROR`. Effort: S.

### 5.6 Invisible cross-instance query bridge
- **Idea:** when a user asks one character about another ("what does Priya think of
  you?"), the receiving instance does a one-shot, silent query to the peer instance to
  answer in-voice, then the link closes — no visible transcript, unlike `GROUP_MODE`.
- **Why it's not already covered:** `GROUP_MODE` banter is public and persistent by
  design (`GROUP_CHAT_DESIGN.md`); this would be private and momentary — a different
  mechanism, not a tuning of that one.
- **Rough shape:** could reuse the admin-API/claim-file plumbing that already lets
  instances see each other. Effort: M.
- **Open question:** needs a real design pass against `GROUP_CHAT_DESIGN.md`'s
  private/group memory boundary before being built — same class of risk that took four
  review rounds last time.

### 5.7 Authored-now, delivered-blind-later capsule ("message in a bottle")
- **Idea:** the character writes something now, sealed, and an internal scheduler
  (not the user, not a fixed date) decides when it resurfaces later, unpredictably —
  "found this old thing I wrote you."
- **Why it's not already covered:** `/remindme` is user-scheduled with a fixed date.
  `EPISODIC_RECALL`/`ONTHISDAY` resurface things that actually happened. Nothing does
  write-now/deliver-later-blind.
- **Rough shape:** a queue of sealed entries plus a resurfacing-time distribution;
  reuses the proactive-send path. Effort: M.
- **Open question:** real gimmick risk if the resurfacing timing isn't tuned carefully —
  the whole idea lives or dies on the "surprise" landing right, not on the mechanism.

### 5.8 Near-miss recall as character behavior ("tip-of-the-tongue")
- **Idea:** semantic recall currently either surfaces a memory or silently discards a
  low-confidence match. Surface the *sensation* of almost-remembering instead ("I know I
  told you about this, hang on—"), then follow up unprompted later if a stronger match
  re-triggers.
- **Why it's not already covered:** the memory auditor's job is being *right*; this
  claims the discard band between "confident enough to use" and "no match," which is
  currently silence.
- **Rough shape:** nearly free — reuses existing embedding infra, gives the discard band
  a behavior instead of dropping it. Effort: S.
- **Open question:** could read as a bug (character "forgetting") rather than a realism
  feature if the frequency isn't tuned low.

### 5.9 User-named transition marking ("ferryman")
- **Idea:** major life transitions (new job, move, breakup) currently flow into ordinary
  memory extraction with no distinct ritual beat. Require the *user* to explicitly name
  the crossing before the bot treats it as significant, avoiding false triggers on
  mundane facts.
- **Why it's not already covered, and why it's the weakest item here:** it overlaps
  meaningfully with date-aware follow-ups and `EPISODIC_RECALL` — this is more a
  refinement of existing infra than new territory. Kept because the "user must name it,
  not auto-detect" property is genuinely absent elsewhere, not because the gap is large.
- **Rough shape:** Effort: S. Lowest priority of the nine — consider folding into
  existing date-aware follow-up machinery rather than building standalone.

### Considered and not included
- **Transition-smoothing overlap window for `SCHED_BUSY`/`FATIGUE_STATE` register
  changes** (stimulus: relay baton handoff) — abandoned during the lateral-thinking
  session itself. It only ever produced narrative polish on a state transition the
  system already fully owns and auto-detects — tuning, not a new capability, and
  therefore out of scope for what the session was asked to find.
## Track 5-B — Lateral-thinking exploratory ideas (sourced 2026-08-05)

**Naming:** this is Track 5-B; the 2026-08-04 proposed block above is Track 5-A.
Not a code-audit finding or an owner request — surfaced by a forced-analogy
(Synectics) lateral-thinking pass run 2026-08-05 against the shipped feature set, to
find directions outside the already-exhausted playbook (memory, proactivity,
multi-modal I/O, group chat, health integration, safety, and cost engineering are all
shipped and iterated multiple times over Tracks 1-4). Recorded per the Track 4
"product direction, not audit debt; revisit deliberately" precedent: nothing here is
scheduled. Items marked **🧪 Experimental** carry a real chance of being wrong about
the *mechanism*, not just about priority — pilot one instance behind a default-off
flag with a kill switch (`bot-code-invariants` #16), never batch-adopt.

### 5.1 Shared proactive-message triage queue — M
- **Evidence:** ER-triage domain. Proactive check-ins, `/remindme`/cron, Garmin health
  alerts, and fatigue-driven silence-breaks each appear to gate themselves
  independently (own quiet-hours + budget check). ER triage instead runs one shared,
  continuously re-ranked queue — no department decides for itself.
- **Idea:** route every candidate proactive message (health anomaly, due reminder, a
  memory that just became newly relevant, a fatigue-driven check-in) through one
  shared urgency score, send only the single highest-scored candidate, re-queue and
  re-score the rest as new signals land. Targets a plausible failure mode of many
  independently-shipped proactive features: same-day collision, or all deferring at
  once and nothing gets said.
- **Risk:** medium — touches the send path for every proactive feature at once; needs
  its own soak before trusting it over today's independent gates.
- **Done when:** a design note showing which existing gates fold into the shared
  score, with the collision/silent-day failure mode reproduced against current
  behavior first (prove the bug before building the fix).

### 5.2 Weeks-long disengagement leading indicator — M
- **Evidence:** coral-bleaching domain. Every shipped signal (fatigue, mood residue,
  distress detection, `PROMPT_STATS`) operates per-message or per-day. Nothing tracks
  a slower trend — reef bleaching is preceded by weeks of invisible accumulating heat
  stress, tracked as a leading indicator well before visible collapse.
- **Idea:** a rolling multi-week trend line on `/audit` — user reply latency, message
  length, topic variety, user-initiated vs. bot-initiated ratio — as a distinct
  long-horizon metric, separate from the existing fast signals.
- **Risk:** low (additive, observability-only, no behavior change) — the risk is
  building a metric nobody looks at.
- **Done when:** the trend line exists on `/audit` and has been checked against at
  least one instance's real multi-week history to confirm it moves before, not after,
  a visible engagement drop.

### 5.3 🧪 Experimental — response refinement on recurring topics — M
- **Evidence:** immune-system domain (affinity maturation: immune memory sharpens its
  response on each re-exposure to the same antigen, not just recalling it). Distinct
  from the existing memory system, which stores facts but doesn't track whether the
  *response* to a recurring situational pattern (user vents about the same stressor
  again) is improving.
- **Idea:** score how a reply to a recognized recurring pattern landed (reply length,
  sentiment, whether the topic returns sooner/later) and let that reshape future
  responses to that specific pattern.
- **Why experimental:** the mapping is a real structural rhyme, but
  pattern-recognition-plus-reinforcement over conversational history is new
  mechanism, not new configuration — higher chance the first design is wrong. Pilot
  one instance, default off.
- **Risk:** medium-high — a personality-shaping feedback loop; same class of caution
  as the already-rejected self-evolution ideas (closeness score, auto inside-jokes)
  above, though the mechanism differs (recall shaping vs. a static score/flag).

### 5.4 Rising urgency floor for neglected memories — S
- **Evidence:** ER-triage domain (a stable case's priority rises automatically the
  longer it waits, even without new information — the opposite of relevance decay).
- **Idea:** a memory or observation that's been "worth mentioning" but never surfaced
  should gain, not lose, priority the longer it goes unsaid. Pairs naturally with
  5.1's shared queue if that gets built; stands alone otherwise.
- **Risk:** low — bounded to the recall-scoring path.

### 5.5 🧪 Experimental — comping mode for group chat — S
- **Evidence:** jazz-ensemble domain. A non-soloing player doesn't go silent or
  compete for the lead — they play sparse supportive chords ("comping").
- **Idea:** in group chat, a non-primary-responder bot sends a minimal reactive
  signal (reaction, one-word aside) instead of a full reply or nothing, so presence
  doesn't require winning the floor.
- **Why experimental:** `GROUP_CHAT_DESIGN.md` survived four adversarial review
  rounds — this is a genuine behavior change to that design, not a bolt-on, and needs
  the same scrutiny before it's more than an idea. Read that doc before prototyping.
- **Risk:** medium — group-chat turn-taking is exactly what that design doc was
  adversarially reviewed for.

### 5.6 🧪 Experimental — trading-fours interaction mode — S
- **Evidence:** jazz-ensemble domain (trading fours: soloists alternate strict short
  bursts, forcing tight call-and-response).
- **Idea:** an opt-in mode with a code-enforced (not prompt-hinted) hard reply-length
  cap and explicit hand-back, for rapid-fire exchange distinct from normal texting
  style.
- **Why experimental:** novelty/product-flavor feature, unrequested, lowest priority
  of this batch — recorded so it isn't re-invented, not because it's likely to be
  picked up soon.
- **Risk:** low — self-contained mode, opt-in.

### ~~5.7 🧪 Experimental — inward drift detection — S~~ Closed 2026-09-03
- **Closed (2026-09-03):** duplication check done. `reflect()` already covers
  self-image trait drift (bounded by `BELIEF_DRIFT_MAX`), `_memory_audit_scan` catches
  factual contradictions, `_engagement_trend` tracks user-side staleness. The one
  uncovered gap — repetitive phrasing in reply text — is real but narrow, and
  `reflect()` could absorb it as a single schema field if it ever surfaces as a
  problem. Not worth building speculatively; the item's own assessment was "likely
  low value."
- **Risk:** n/a — closed without building.

### 5.8 🧪 Experimental — banked variance as resilience — (unsized, direction only)
- **Evidence:** coral-bleaching domain (reefs that survive bleaching events are ones
  with pre-existing genetic diversity banked *before* the stress, not a response
  mounted after).
- **Idea:** deliberately bank variance in a character's register over time —
  occasional structural surprises, willingness to break its own pattern — as a hedge
  against staleness, rather than optimizing voiceprint consistency alone.
- **Why experimental — flagged as friction, not a recommendation:** this sits in
  direct tension with the project's heavy, multi-release investment in voiceprint
  consistency (3.13, `preset-core.txt`, per-character format-contract layers).
  Recorded because the analogy surfaced it honestly, not because it's endorsed — the
  owner should decide if this tension is worth resolving in either direction.
- **Risk:** unassessed — direction only, not a spec.

### 5.9 Nightly-suggested edits to the living files (`/reviewlife`) — ✅ SHIPPED v2026-08-24.8
- **Shipped (2026-08-24):** `reflect()` now asks its existing `SUMMARY_MODEL` request for one
  more key, `living_file_suggestions` (zero new LLM calls); `_enqueue_life_suggestions`
  validates + dedups them into `life_review.json`, and the new `/reviewlife` command gates
  each one per-line (`ok`/`no`) with its source quote shown, appending via `_append_life_line`
  on accept. Kill switch `REVIEWLIFE` (default on) gates the prompt itself, not just the
  enqueue. Built per `PLAN-5.9-reviewlife.md`; "done when" criteria met in tests, pending a
  real-day validation on one instance before fleet promotion.
- **Plan (2026-08-24):** scoped as 6.2's item-4 slice — full implementation handoff in
  `PLAN-5.9-reviewlife.md` (rides the existing `reflect()` JSON call, so zero new LLM
  calls; mirrors `/reviewmem`'s accept/reject UX). Read it before starting.
- **Evidence:** sourdough-starter domain (random-stimulus lateral-thinking pass,
  2026-08-05) — same culture, different loaf depending on how it's fed. `life.txt` /
  `people.txt` / `projects.txt` are already the intended drift surface (user-maintained,
  sampled into every prompt via `_read_life_file`), and `update_milestones()` already
  runs an LLM pass nightly against the day's conversation. Nothing today connects the two.
- **Idea:** right after `update_milestones()` runs in `nightly_maintenance`, have the
  same pass also draft (never apply) candidate one-line additions to the living files
  from what it just extracted. Surface via a new `/reviewlife` command for per-line
  accept/reject — explicit approval only, no silent drift. Store pending drafts the
  same way `unsent_drafts` already does.
- **Why not automatic:** silent personality drift is the wrong default on a companion
  bot even opt-in; per-line approval keeps the owner in the loop the same way
  `/reviewmem` already does for the memory auditor (4.1).
- **Risk:** low-medium — additive, no existing behavior changes; main risk is
  suggestion quality/noise if the nightly pass over-fires.
- **Done when:** a day's conversation with a clear life-event produces a correct,
  one-line `/reviewlife` suggestion; rejecting it changes nothing; accepting it appends
  to the correct living file with a visible log line.

### ~~5.10 `/mixtape` — composed highlight-reel send — S~~ SHIPPED v2026-09-03.1
- **Shipped:** temporal-spread bucket sampling over `milestones`, voice + text + image
  burst via existing TTS and selfie pipelines. Kill switches: `MIXTAPE_ENABLED`,
  `MIXTAPE_COUNT`.

### ~~5.11 Rhythm transparency — skip-reason on `/nudges` — S~~ SHIPPED v2026-09-01.2; receipts v2026-09-04.2
- **Evidence:** lighthouse domain (random-stimulus lateral-thinking pass, 2026-08-05) —
  a fixed, predictable signal that doesn't chase. The restraint already exists
  (`_check_nudge_budget`, mood-based `skip_chance`, quiet hours) and even carries a
  reason forward via `unsent_drafts`, but that reason only surfaces if the 40%
  weave-in roll hits a future proactive message. `/nudges` today shows only
  `sent_today/limit`. Receipts now add recent skipped/drafted reasons.
- **Idea:** have `/nudges` also surface the most recent `unsent_drafts` reason (if
  any), so the existing restraint is checkable on demand instead of only occasionally
  narrated in-character.
- **Open question, not yet a build item:** `skip_chance` rises as mood drops (0.6 at
  ≤ -1.2, 0.25 at ≤ -0.4) — meaning she reaches out *less* when the owner's mood is
  low. Worth an explicit owner decision on whether that's the intended emotional read
  or the opposite risk, and recording the answer as a comment near `heartbeat()`
  either way.
- **Risk:** low — read-only addition to an existing command.
- **Done when:** `/nudges` shows the last skip reason when one exists in the last 48h
  window (matching `_pop_draft`'s existing freshness cutoff).

### Not carried forward
- **Relay-post-system transplant ("reliability from designed handoffs, not one
  heroic actor")** — abandoned during the analogy session itself. The structural
  rhyme only held by giving "rider" a second forced role (either it means the
  character, which breaks the product's single-persistent-identity premise, or it
  means the engineering process, which the repo's own routines/evals/delivery gate
  already embody). No new idea survived; recorded so it isn't re-drawn.

---

## Track 6 — AI landscape research (sourced 2026-08-05)

Not lateral-thinking (Track 5's method) — a web-research pass against current (2026)
AI-industry developments, checked against this repo's actual code and open items
before being recorded. Multi-agent LLM orchestration was researched and explicitly
**not** carried forward: the shipped bot-to-bot design (`GROUP_CHAT_DESIGN.md`, 3.4,
four adversarial review rounds) already covers the pattern, and the live-collaboration
shape most 2026 frameworks assume runs straight into `bot-code-invariants` #3 (no new
per-message LLM side calls) with no case strong enough to argue an exception.

### 6.1 ~~Prompt caching on the `assemble_messages` prefix~~ — checked, not applicable (2026-09-01)
- **Closed 2026-09-01: checked, not applicable.** Step 1's instrument shipped
  (v2026-08-24.9, deployed 2026-08-25); the live read on Emily (2026-09-01, `journalctl`
  grep for `cached`/`cache_read` across a day's traffic) returned no output — NanoGPT's
  usage responses carry no `cache_read_input_tokens` or `prompt_tokens_details.cached_tokens`
  field for this fleet's model routes. Confirmed on both Emily (`glm-5:thinking`) and
  Jules (non-thinking model) — neither returns cache-hit data. Caching is not active;
  steps 2-3 do not apply. The `assemble_messages` prefix reorder is not worth doing
  (nothing to preserve), and 3.8 Phase 2's cost argument ("re-pays the entire ~17k-token
  prompt every call") stands unchanged. The `/audit` instrument (`_usage_cached_tokens`)
  remains in the code — if NanoGPT adds caching for open-source routes later, `/audit`'s
  `; N cached` figure will surface it without a new change.
- **Evidence:** NanoGPT (this fleet's provider) documents automatic implicit prompt
  caching — no request changes needed — for "OpenAI and Gemini model families plus
  many open-source provider/model routes," with cache hits reported via
  `cache_read_input_tokens` in the response usage block. This lands directly on 3.8's
  own numbers: "instances run ~17k input tokens per call... cost is dominated by
  context, not output" at 15-40 calls/day × 7 bots.
  **Not yet confirmed:** NanoGPT's docs do not enumerate which open-source routes are
  covered, and every default model here is one (`NANOGPT_MODEL=zai-org/glm-5:thinking`,
  `REACTION_MODEL=zai-org/glm-4.7-flash`) — none are OpenAI/Gemini. Whether caching
  applies to this fleet's actual models at all is unverified; treat it as a hypothesis,
  not a fact, per C9.
  **Also checked:** `assemble_messages` (bot.py:5090) currently defeats prefix caching
  even if the models support it — `ATLAS` gets `random.sample()`'d (line 5139) and the
  GIF capability line gets a `random.random() < GIF_CHANCE` roll (line 5162), both
  before conversation history. NanoGPT's docs are explicit that cache hits require a
  byte-identical prefix; either randomized block invalidates everything after it, on
  every call.
- **Idea, in verification order — do not skip step 1:**
  1. Confirm whether `cache_read_input_tokens` is ever nonzero today for any live
     instance's actual model, before assuming there's anything to fix.
  2. If caching is available but defeated by assembly order: this is a candidate for
     moving the randomized/conditional blocks (ATLAS sample, GIF roll) to *after*
     conversation history, not a rewrite of `assemble_messages` itself. That function
     is `repo-change-control`'s own Step 6 — "the riskiest code in the bot... only
     move behind parity tests." A reordering is smaller than a rewrite but still
     touches it directly; scope accordingly and get the parity-test treatment 3.8's
     own precedent (640-prompt byte-identical diff, 2.4) sets for prompt-shape changes.
  3. If step 1 shows caching is unavailable for these model routes: this item is
     closed as "checked, not applicable," same disposition as 3.8's own "tried, not
     worth it" clause — recorded either way, not left open.
- **Unlocks on completion (if caching turns out to be live and gets fixed):** revisits
  3.8 Phase 2's own cost argument against the pre-reply thinking call — its stated
  blocker is that a naive call "re-pays that entire prompt every user message." A
  working cache changes what "re-pay" costs.
- **Risk:** low for step 1 (read-only, no code change). Medium if step 2 is picked up,
  scoped to prompt-shape risk, not the invariant/concurrency risk classes.
- **Done when:** step 1's answer is recorded either way; if pursued past that, a
  before/after prompt capture (matching 2.4's methodology) proves the reorder is
  behavior-identical and `cache_read_input_tokens` moves off zero.

### 6.2 ~~Deepen `nightly_maintenance` as deliberate sleep-time compute~~ ✅ (first slice shipped v2026-08-24.6, `NIGHTLY_PREDRAFT`)
- **Shipped:** the nightly `reflection_job` now pre-drafts the day's proactive hooks
  (`_predraft_proactive_hooks` → persisted `predrafted_hooks` buffer, sized by
  `NIGHTLY_PREDRAFT_COUNT`, default 3 = the default daily nudge budget). `send_proactive`
  consumes a prepared hook via `_pop_predrafted_hook` and only pays the live
  `_generate_proactive_hook` call when the buffer is empty — so hook generation moves off
  the live proactive tick into the idle nightly window, with byte-identical fallback
  whenever no pre-draft exists. No new per-message reply-path call (`bot-code-invariants`
  #3 not implicated — these are nightly, off-loop). **Not** a call-count reduction, though:
  a `/code-review` pass corrected that first-draft claim — the nightly count is fixed while
  proactive sends are heavily gated, so on a low-activity day the surplus cheap calls go
  unused (net-neutral on active days, a small increase on quiet ones). Kill switch
  `NIGHTLY_PREDRAFT` (default on). See CHANGELOG v2026-08-24.6.
- **"What nightly consolidation can absorb" list** (the item's standing deliverable — the
  set of live-path work that can move to the nightly job with no new live call; extend
  as slices ship):
  1. ✅ **Proactive-hook pre-draft** — shipped v2026-08-24.6 (above).
  2. ✅ **Proactive ambient-detail refresh** — shipped v2026-08-24.7 (`AMBIENT_PREDRAFT`).
     The nightly reflection stashes a compact headline digest (reusing the morning-news
     feeds) in `_ambient_news_cache`; `send_proactive` injects it via
     `PROACTIVE_AMBIENT_STASH_HINT` instead of the live `[search:]`, falling back to the
     search hint when the stash is empty/stale. Removes the live web search from the ~25%
     of proactives that use ambient color, for one off-loop RSS fetch/night. See CHANGELOG
     v2026-08-24.7.
  3. ~~Selfie-scene pre-selection~~ — **checked, not applicable (2026-08-24).** The premise
     that a scene is "picked at send time" does not hold in the code. `send_proactive`'s
     selfie branch only appends a static `PROACTIVE_SELFIE_HINT` telling the model to include
     a `[selfie:]` tag in the reply it already generates — no scene selection, no call. Scene
     composition lives in `build_selfie_prompt` (bot.py:7482) and is pure local `random.choice`
     sampling from the `SELFIE_*` pools plus live weather/mood/wardrobe filtering and
     `_recent_selfie_hints` dedup — no LLM call, microseconds of CPU, nothing to move off-loop.
     The one expensive step, `generate_selfie_image`, is inherently live: pre-generating a
     selfie the night before would freeze it to stale weather/outfit, reintroducing the
     frozen-snapshot contradiction v2026-08-01.7 removed. So there is no sleep-time-compute
     win here; recorded closed rather than left open.
  4. ✅ **`/reviewlife` nightly edits** (5.9, same shape, sourced independently) — the living
     files (`life.txt`, `people.txt`, `projects.txt`) get nightly-suggested one-line
     additions drafted by the existing `reflect()` pass and gated per-line by a new
     `/reviewlife` command. **Shipped v2026-08-24.8** — rode the existing `reflect()` JSON
     (zero new LLM calls) per `PLAN-5.9-reviewlife.md`; kill switch `REVIEWLIFE` gates the
     prompt itself. That closes every actionable item on this 6.2 list (slice 3 closed
     not-applicable above).
  - Not on the list (deliberately live): anything that depends on the *current* inbound
    message (safety assessment, reply advisor 6.3, the reply itself) — those cannot be
    precomputed the night before.
- **Evidence:** "Sleep-time compute" (Letta, 2025) names a pattern this repo already
  half-built without naming it: agents that consolidate memory and pre-compute context
  during idle time instead of only at query time, reported at up to 18% accuracy gains
  and ~2.5x cost reduction on the calls that follow. `nightly_maintenance` (memory
  promotion, `update_milestones`, `_overnight_mood_reset`) is this pattern today, just
  not treated as a deliberate strategy to extend. Provider-agnostic — uses the same
  chat-completion calls already made nightly, on whatever model each instance runs, so
  none of 6.1's NanoGPT-support question applies here.
- **Idea:** treat `nightly_maintenance` as the standing place to move work off the
  live reply path, not just its current three jobs. Pairs directly with 5.9's
  `/reviewlife`, sourced independently but the same shape. One concrete extension not
  covered by 5.9: `_generate_proactive_hook` currently generates fresh at
  `send_proactive` time; a nightly pass could pre-draft a candidate hook instead, so
  the heartbeat tick consumes prepared context rather than generating cold.
  **Invariant check:** adds zero new per-message LLM calls (`bot-code-invariants` #3)
  — the nightly job already runs and already makes model calls; this redistributes
  what those calls do, not how many fire live.
- **Risk:** low — additive to an existing off-loop job, no new call-site class.
- **Done when:** a named "what nightly consolidation can absorb" list exists (starting
  with the proactive-hook pre-draft above) and at least one item ships behind the
  existing nightly job with no new live-path call.

### 6.3 Reply advisor — a second call with veto power over the draft reply — L
- **Evidence:** owner request 2026-08-05, following the pattern discussion prompted by
  this session's own `advisor()` tool (a stronger reviewer seeing full context, able to
  override before work is treated as done). Owner has explicitly waived `bot-code-
  invariants` #3's cost argument (60M tokens/week via the NanoGPT subscription) for
  this item specifically — **this does not waive the rule generally**, only for this
  named feature, and latency is a separate, unwaived cost: an extra round-trip on every
  reply regardless of token budget. Two existing partial precedents inform the design:
  `_assess_safety` (`SAFETY_ENABLED`, 3.15) is already an off-loop advisor-with-veto,
  scoped to no context specifically to avoid re-paying the ~17k-token prompt; here the
  scoping reason changes to judge quality (a focused judge is a better judge — the
  same principle that keeps 6.1's hypothetical cache-friendly reordering scoped small),
  since the token-cost reason no longer applies for this item.
- **What it checks (owner-selected, not the vaguest option):** in-character voice
  consistency and factual/memory accuracy. Explicitly not "general quality" — too
  vague to build a reliable judge for, highest risk of false rejects flattening replies.
- **Idea — hooks between existing functions, no rewrite of either:**
  1. `generate_reply()` (bot.py:5885) produces the draft via `_do_request` (the choke
     point, line 5627) exactly as today. The gate is a new step between that draft and
     `send_bubbles()` (line 6169) — the actual Telegram send. Neither function's
     internals change.
  2. **Memory-accuracy check:** run `triggered_memories()` (line 4093 — the same
     semantic+keyword recall already used for prompt injection) *against the draft
     reply text* instead of the incoming user message. Surfaces the specific stored
     facts/milestones the draft actually touches, not the whole fact store — reuses
     existing recall, doesn't invent new retrieval.
  3. **Voice check:** the instance's own `PRESET_LAYERS` stack as judging criteria,
     scoped down from full conversation history for judge-quality reasons (above).
  4. **Verdict:** approve, or reject-with-reason. On reject, regenerate with the
     reason fed back into the prompt, capped at **2 attempts** (matching the
     "two honest attempts" shape already used elsewhere in this roadmap, e.g. 5.9's
     honesty mechanic). After 2 failed attempts: **send the best-scored attempt
     anyway, flagged in the log** — not silence. A companion bot going silent on a
     direct reply is a worse failure than a mediocre one; `unsent_drafts` already
     encodes that going quiet is a designed, deliberate act for *proactive* messages
     only, never a fallback for a reactive one.
  5. **Leak discipline:** the advisor's own verdict/reasoning must never reach the
     user — same discipline `REASONING_LEAK_GUARD` already enforces on the
     character's own hidden reasoning. It does not route through `generate_reply`.
  6. **Optional follow-on, not required for v1:** a `/advisorlog`-style command
     surfacing recent rejections, matching the transparency pattern `/reviewmem` /
     `/dupefacts` already set for the memory auditor (4.1) — visibility into what got
     caught, not just that something did.
- **What this needs before it is code, not a design (per invariant #3's own text:
  "a design conversation with the user before the code exists"):**
  - A genuine new `bot-code-invariants` #3 carve-out, written into that file itself,
    owner-approved — same treatment `SAFETY_ENABLED` and `MEMORY_SEMANTIC_LIVE` got.
    This one is a bigger ask than either: it's a completion call carrying real
    context (draft + relevant facts + preset), not an embedding or a context-free
    classifier, so the carve-out's rationale has to say so plainly, not borrow their
    wording.
  - A kill switch per invariant #16. **Recommend default OFF to start** — not for
    cost (waived), but because this changes what the user sees on *every* message,
    a bigger blast radius than a silent infra change. Pilot one instance before
    fleet-wide, same posture as the R6 experiments (`CLOSENESS_ENABLED` et al.).
  - Latency measured and reported, not assumed maskable — same standard 3.8 Phase 2
    already set for its own pre-reply call.
- **Risk:** medium-high — first invariant #3 exception approved on cost grounds
  alone; the mitigations above (scoped context, capped retries, non-silent fallback,
  default-off pilot) are what stand in for the invariant's usual protection, per its
  own "say what replaces its protection" requirement.
- **Done when:** default-off, one-instance pilot; a same-bot before/after comparison
  (own-baseline, not cross-character, matching 3.8's A/B protocol) shows the voice
  and memory-accuracy checks catching real cases without materially flattening
  replies; latency per reply visible on `/audit`; the `bot-code-invariants` #3
  carve-out text written and merged in the same change that ships the feature flag.

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
| ~~**Next**~~ | ~~1.6 lock the `vps-sync.sh` bot.py swap~~ | ✅ **Shipped and VPS-confirmed 2026-08-01** — `flock` plus a fatal backup, closing the other half of the concurrent-deploy bug bot.py fixed in v2026-07-25.11. Owner raced real `vps-sync.sh` invocations on the fleet: the loser (`cass`) hit the lock and exited before touching anything; the winner (`bonnie`) completed cleanly; `bot.py.bak` matched a pre-race baseline exactly. |
| ~~**Next**~~ | ~~1.7 exact dependency lock + immutable releases~~ | ✅ **Shipped 2026-08-24** — CI/VPS share one hashed Python 3.12 lock; deploys select full-git-SHA releases with atomic rollback. Follow-up 1.8 added per-instance canary selectors. |
| ~~**Next**~~ | ~~1.8 per-instance canary release selectors~~ | ✅ **Shipped 2026-08-24** — each bot has a root-owned `current`/`previous` selector; deploy and rollback are instance-scoped, and a tested canary release can be promoted explicitly to the active fleet. |
| ~~**Next**~~ | ~~1.9 structured fleet operation events~~ | ✅ **Shipped v2026-08-24.3** — payload-free JSON at model, external-fetch, scheduled-job, and delivery boundaries; one journal report compares latency, outcomes, and fallback across the fleet. |
| ~~**Next**~~ | ~~1.10 incremental transactional machine-state persistence~~ | ✅ **Shipped v2026-08-24.4** — reminders use a transactional per-instance SQLite store with verified JSON migration/export and a one-release feature rollback. |
| ~~**Next**~~ | ~~1.11 per-instance systemd sandbox~~ | ✅ **Shipped 2026-08-24** — one-bot canary and explicit promotion of a root-owned sandbox drop-in; narrow writable paths and a release-independent rollback command. |
| **Someday** | 5.1 shared triage queue, ~~5.2 disengagement indicator~~, 5.4 rising urgency floor, 5.9 `/reviewlife`, 5.10 `/mixtape`, ~~5.11 nudge skip-reason transparency~~ | ~~5.11-B shipped v2026-09-01.2; 5.2-B shipped v2026-09-01.3~~ (Sprint 1 complete). ~~5.5-A shipped v2026-09-01.4; 5.1-A shipped v2026-09-02.1; 5.4-A shipped v2026-09-02.2~~ (Sprint 2 complete). Remaining items not scheduled. |
| **Not scheduled** | 5.3, 5.6, 5.7, 5.8 (all 🧪 Experimental) | Recorded for deliberate one-instance piloting only, per Track 5's header — do not batch-adopt or sweep to default-on. |
| ~~**Someday**~~ | ~~6.1 prompt-caching verification~~, ~~6.2 nightly-consolidation extension~~ | **6.1 closed 2026-09-01: checked, not applicable** — live read on Emily showed NanoGPT returns no cache-hit fields for this fleet's model routes; steps 2-3 do not apply. **6.2's first slice shipped v2026-08-24.6** (proactive-hook pre-draft, `NIGHTLY_PREDRAFT`) with a standing "what nightly can absorb" list for further slices. |
| **Not scheduled** | 6.3 reply advisor | Design recorded, not started — needs the `bot-code-invariants` #3 carve-out written and owner-approved before any code exists, per the item's own "done when." Largest/highest-risk item in the roadmap by blast radius (changes every message on the pilot instance); default-off, one-instance pilot only when picked up. |

Execution maps onto the agent system: builder implements one item per dispatch,
qa-engineer verifies against each item's "done when", research-scout owns the 3.3 gate,
adversarial-critic reviews the 3.4 design doc, and every bot.py-touching item ships
with the usual BOT_VERSION bump + changelog entry (the delivery gate enforces it).

## Proposed sprints (grouping of open items, 2026-08-25)

**What this is:** a grouping of the open Track 5/6 items by *shared code surface and risk
class*, so related work is picked up together (one context load, one review pass, one soak)
instead of one scattered item at a time. **This is organization, not a schedule or a
re-prioritization** — Track 5's items remain owner-triage-pending ideas, not committed work,
and 🧪 items still pilot one instance default-off (never batch-adopt). The two Track 5 blocks
share numbers, so they're disambiguated here as **5-A** (the 2026-08-04 "Proposed" block) and
**5-B** (the 2026-08-05 "Lateral exploratory" block). Sprints are ordered low→high risk, which
is also a sensible build order: warm up on observability, end on the design-review-heavy work.

### ~~Sprint 1 — Observability & transparency (no behavior change)~~ SHIPPED v2026-09-01.2/.3
Surface existing internal state on existing commands; same "read state, render it" shape as
the just-shipped 6.1 cache instrument. Lowest risk in the batch.
| Item | Size | Surface | Note |
|---|---|---|---|
| ~~5.11-B nudge skip-reason on `/nudges`~~ | S | `/nudges`, `unsent_drafts` | **Shipped v2026-09-01.2.** Owner decision recorded: `skip_chance` rising with low mood is intended (withdrawn = fewer nudges). |
| ~~5.2-B weeks-long disengagement trend on `/audit`~~ | M | `/audit`, rolling multi-week metric | **Shipped v2026-09-01.3.** Instrument deployed; live validation pending — confirm the metric moves before a visible engagement drop against real instance history after deploy. |

### Sprint 2 — Character presentation of existing state (zero/near-zero new LLM calls)
All hook the same reply-injection points that already read mood / fatigue / mirror / busy
state. Mechanism risk is low; the real risk is immersion/execution, judged only in a live
exchange.
| Item | Size | Surface | Note |
|---|---|---|---|
| ~~5.5-A chronotype + user-clock noticing~~ | S | timestamp arithmetic, `STYLE_MIRROR`-shaped | **Shipped v2026-09-01.4.** `_chronotype_note()` + `_user_clock_note()` injected in `assemble_messages`. `CHRONOTYPE` opt-in per instance; `CHRONOTYPE_NOTICE` default on. |
| ~~5.1-A constancy override ("lighthouse")~~ | S | suppression flag at the fatigue/busy/mirror injection points | **Shipped v2026-09-02.1.** Natural-language trigger phrases suppress mood/fatigue/busy/mirror for one exchange. `CONSTANCY_OVERRIDE` default on. Open question resolved in practice: needs live exchange to judge. |
| ~~5.4-A in-character introspection query~~ | S/M | template already-computed state in-voice | **Shipped v2026-09-02.2.** `/reflect` command — reads mood, fatigue, engagement trend, user-clock, energy; composes in-character paragraph. Zero LLM calls. `INTROSPECTION_QUERY` default on. |

### Sprint 3 — Recall & memory-surfacing behaviors
All live on the semantic-recall / memory-scoring path; all small and bounded there.
| Item | Size | Surface | Note |
|---|---|---|---|
| 5.8-A tip-of-the-tongue near-miss recall | S | the embedding *discard band* (currently silence) | **SHIPPED v2026-09-02.3** — `_tip_of_tongue_hint` fires on 0.15-0.3 cosine band when no confident hits exist. |
| 5.4-B rising urgency floor for neglected memories | S | recall-scoring path | **SHIPPED v2026-09-02.3** — `_urgency_boost` in `triggered_memories` rises linearly over MEMORY_URGENCY_CEILING turns. |
| 5.9-A user-named transition ("ferryman") | S | date-aware follow-up machinery | **SHIPPED v2026-09-02.4** — `/transition` stores a `(transition)`-tagged note; `_transition_hint` + `days:N` recurrence for check-ins. |

### Sprint 4 — Proactive-send unification (medium risk; soak required)
All touch the proactive-send scheduler. Build **5.1-B first as the spine** (one shared urgency
score); the other two are new proactive *sources* that ride it, and 5.4-B's urgency floor feeds
its score. Touches every proactive feature at once — reproduce the collision/silent-day failure
before building the fix, and soak before trusting it over today's independent gates.
| Item | Size | Surface | Note |
|---|---|---|---|
| 5.1-B shared proactive triage queue | M | every proactive send path | **SHIPPED v2026-09-02.5** — `_triage_register`/`_triage_should_yield`/`_triage_clear` coordinate by priority (health>vigil>transition>note>bottle>heartbeat). |
| 5.2-A vigil mode for anticipated hard events | M | extraction + proactive scheduler + tone | **SHIPPED v2026-09-02.5** — `_vigil_detect` scans user_notes for hard-event keywords + due dates; `_vigil_hint` tone modifier + `vigil_checkin_job` daily check-in via triage. |
| 5.7-A message-in-a-bottle capsule | M | sealed-entry queue + resurfacing distribution | **SHIPPED v2026-09-02.5** — `/bottle` seals messages; `bottle_resurfacing_job` delivers at random 7-60 day window via triage. |

### Sprint 5 — Group-chat & cross-instance (needs one GROUP_CHAT_DESIGN.md review pass)
All change bot-to-bot / cross-instance behavior. Batch so a single `group-chat-changes` +
design-review pass covers the set; `GROUP_CHAT_DESIGN.md` survived four adversarial rounds, so
none of these is a bolt-on. 🧪 = pilot one instance, default-off.
| Item | Size | Surface | Note |
|---|---|---|---|
| 5.5-B 🧪 comping mode | S | group turn-taking | **SHIPPED v2026-09-02.6** — `_group_comp_react` sends reaction emoji on claim-lost/declined; no ledger entry, no budget, no flat-file writes. `GROUP_COMPING` kill switch (default off). |
| 5.6-B 🧪 trading-fours mode | S | opt-in, code-enforced length cap | **SHIPPED v2026-09-02.6** — `_truncate_at_word` + `max_reply_chars` param on `_group_deliver`; applied only in `_maybe_reply_to_bot`. `GROUP_TRADING_FOURS` kill switch (default off). |
| 5.6-A invisible cross-instance query bridge | M | admin-API / claim-file plumbing | **SHIPPED v2026-09-02.6** — `_cross_query_detect`/`_cross_query_fetch` + `/admin/peer-view` endpoint; DM-only, one-shot system context injection. `CROSS_QUERY` kill switch (default on). |

### Standalone / gated — not sprinted, each needs its own decision
| Item | Why it stands alone |
|---|---|
| ~~5.10-B `/mixtape` (S)~~ | **Shipped v2026-09-03.1.** |
| 3.8 Phase 2 — pre-reply thinking call (S/M) | Default-off, A/B-gated, first #3 loosening. **Standing rec: measure whether the free `STEP_INTENT` seed + preset work already delivered the target before building.** |
| ~~6.1 step 2 — `assemble_messages` prefix reorder~~ | **Closed 2026-09-01** — the live cache read returned nothing; caching is not active for this fleet's model routes, so the reorder has nothing to preserve. |
| 6.3 reply advisor (L) | **Owner-gated:** needs a new `bot-code-invariants` #3 carve-out written into that file and owner-approved before any code. Largest blast radius in the roadmap. |
| ~~5.3-A standing life-project with decay (M/L)~~ | **Shipped v2026-09-03.3.** One project per instance, momentum float + nightly decay + stage-aware context injection. Default OFF (Track 5 pilot, `LIFE_PROJECT`). |
| 5.3-B 🧪 response refinement on recurring topics (M) | A personality-shaping feedback loop — same caution class as the rejected self-evolution ideas; highest-risk 🧪. |
| ~~5.7-B 🧪 inward drift detection (S)~~ | **Closed 2026-09-03** — duplication check done; existing machinery covers the valuable parts, uncovered gap (phrase repetition) too narrow to build speculatively. |
| 5.8-B 🧪 banked variance (unsized) | In direct tension with the multi-release voiceprint-consistency investment (3.13); an owner call on whether to resolve that tension at all, not a build item. |
