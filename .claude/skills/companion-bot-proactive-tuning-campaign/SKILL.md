---
name: companion-bot-proactive-tuning-campaign
description: >
  Decision-gated campaign for tuning PROACTIVE BEHAVIOR in telegram-companion-bot —
  the unprompted messages (heartbeat check-ins, event reminders, Garmin nudges,
  on-this-day reminiscing, cron jobs, follow-ups) that still sometimes fire at the
  wrong moment or feel robotic. Load this when: the owner complains about check-in /
  nudge / reminder TIMING or TONE ("she texted me at a bad time", "the check-ins feel
  canned", "too many messages", "two bots messaged me back to back"); you are tuning
  ANY proactive system's frequency, gating, or content; or you are adding a NEW
  proactive feature and need the invariants it must inherit. Do NOT use for: one-off
  triage of a single misfire ("why did she text me just now?") — that is
  companion-bot-debugging-playbook; memory-driven content quality (recall, episodes,
  extraction) — that is companion-bot-memory-campaign.
---

# Proactive Behavior Tuning Campaign

Ground truth verified against `telegram-companion-bot/bot.py` on 2026-07-02.

This is a CAMPAIGN, not a triage script. It assumes the bots are basically alive and the
complaint is about the *quality* of proactive behavior: wrong moments, wrong frequency,
robotic content, or systems stacking on each other. Success is MEASURED — log-tag counts
and defined metrics before and after — never judged by eye. Every phase ends with a GATE:
run the commands, compare against the expected observations, and take the branch stated.
Do not skip a gate and do not "fix" anything a gate has not implicated.

Six instances run on the owner's Termux/Android phone: nora, bonnie, cass, emily, jules,
priya. Each has its own dir `~/<char>-bot/` with its own `bot.log`, `.env`, and state.
All device commands the owner runs are pasted through a chat client that STRIPS `$...$`
spans: **device commands must contain NO dollar signs** — use `~`, literal paths, and
one line per bot. No `$(...)`, no `$HOME`, no `awk` (its `$1` fields die in paste). See
companion-bot-device-ops for the full paste-corruption rules and restart mechanics.

## The proactive-path inventory (ground truth)

Every unprompted message comes from exactly one of these paths. Identify the path by its
log tag BEFORE touching anything.

| Path | Trigger | Gates (in order) | Log tag | Env knobs | Restart persistence |
|---|---|---|---|---|---|
| **Heartbeat** | `schedule_next_heartbeat` rolls a random delay in [`HEARTBEAT_MIN_HOURS`, `HEARTBEAT_MAX_HOURS`] (defaults 2–6h); `heartbeat()` fires, always re-rolls first | owner set → skip if owner active within `HEARTBEAT_MIN * 0.9` (`last_seen`) → quiet hours (`QUIET_START`/`QUIET_END`, saves a draft) → `/quiet` active → nudge budget (`_check_nudge_budget`, default 3/day, saves a draft) → mood-based random skip (60% if mood ≤ −1.2, 25% if ≤ −0.4) | `[heartbeat]` | `HEARTBEAT_MIN_HOURS`, `HEARTBEAT_MAX_HOURS`, `QUIET_START`, `QUIET_END`; runtime `/quiet`, `/nudges` | next tick persisted to `.next_heartbeat`; resumed on restart if still in the future |
| **Follow-up** | regex `_FOLLOWUP_RE` matches the CHARACTER'S OWN reply (not the user's message); fires a second message after `random.uniform(FOLLOWUP_MIN, FOLLOWUP_MAX)` (45–120s) | `FOLLOWUP_ENABLED` (default **false**) → active vibe is not "in-person" → regex match | `[followup]` | `FOLLOWUP_ENABLED`, `FOLLOWUP_MIN_SECS`, `FOLLOWUP_MAX_SECS` | none — pending follow-up dies with the process |
| **Event reminders** | `fire_reminder` with `kind == "event"`; phases `before` / `after` / `recurring`, LLM-extracted from conversation | if owner active within `EVENT_NUDGE_BUFFER_MIN` (15) minutes of `last_seen`, DEFER by that many minutes, up to `EVENT_NUDGE_MAX_DEFERS` (3), then fire anyway | `[event-reminder]` | `EVENT_REMINDERS` (default on), `EVENT_NUDGE_BUFFER_MIN`, `EVENT_NUDGE_MAX_DEFERS` | reminders (incl. `_deferred` count) saved via `save_reminders()` |
| **Explicit user reminders** | `fire_reminder`, `kind != "event"` — the owner asked to be reminded | NONE. Fires exactly on time BY DESIGN. **Never "fix" this path's timing.** | `[reminders]` | — | persisted with reminders |
| **Garmin stress** | periodic `stress_monitor_job`, fires if stress stayed high | `STRESS_ALERTS` → cooldown `STRESS_ALERT_COOLDOWN_HOURS` → quiet hours / `/quiet` | `[stress]` (fetch layer logs `[garmin]`) | `STRESS_ALERTS`, `STRESS_ALERT_COOLDOWN_HOURS` | cooldown timestamp on disk |
| **Garmin body battery** | periodic `bb_monitor_job`, fires if BB ≤ `BB_LOW_THRESHOLD` | `BB_ALERTS` → cooldown `BB_ALERT_COOLDOWN_HOURS` → quiet hours / `/quiet` | `[bb]` | `BB_ALERTS`, `BB_ALERT_COOLDOWN_HOURS`, `BB_LOW_THRESHOLD` | cooldown timestamp on disk |
| **Garmin RHR** | morning job, fires if resting HR ≥ baseline + `RHR_ELEVATED_DELTA` | once/day (date file) → quiet hours / `/quiet` | `[rhr]` | `RHR_ELEVATED_DELTA` | once-per-day date file |
| **On-this-day** | daily job resurfaces an old episode | once/day (date file) → `ONTHISDAY_MIN_GAP_DAYS` between reminisces → quiet hours / `/quiet` | `[onthisday]` | `ONTHISDAY_MIN_GAP_DAYS` | date file |
| **Cron jobs** | owner-scheduled `run_cron_job` → `send_triggered` | NONE beyond the schedule — owner asked for it at that time | `[cron #<id>]` | — | cron jobs persisted |
| **Life-sim / offline life** | `update_life_event` generates offline-life lines | `LIFE_SIM_ENABLED` (default on) | `[life]` | `LIFE_SIM_ENABLED` | appended to life file |

Notes that matter:

- **Life-sim does not send messages.** It appends events to the character's life file,
  which later prompts consume. If proactive *content* feels off, life-sim can be a
  content input; it is never the sender. Do not hunt for a `[life]` send.
- **The Garmin monitors and cron jobs do NOT check `last_seen`.** Their gates are
  cooldowns and quiet hours only. This is a real, verified gap against the convergent
  invariant below — a Garmin nudge CAN land mid-conversation. If Phase 1 classifies a
  misfire as wrong-time and the tag is `[stress]`/`[bb]`/`[rhr]`, adding an
  owner-active defer (modeled on `fire_reminder`'s) is a legitimate Phase 3(a)/(b) fix.
- **Convergent invariant (project law):** every proactive path that initiates contact
  should check owner activity before firing. Heartbeat has it natively; event reminders
  got it on 2026-07-01 (commit `6a8061f`) after a live incident. Any NEW proactive
  feature inherits this obligation — route the design through
  companion-bot-architecture-contract.

## Fences — wrong paths already paid for. Do not re-enter.

1. **The misdiagnosis chain.** A mistimed message was blamed on the follow-up system
   (the delay felt similar), then on heartbeat. Both were DISPROVED by evidence:
   `FOLLOWUP_ENABLED` defaults to false and no `[followup]` line existed; no
   `[heartbeat] Proactive message sent.` line existed at the time. The culprit was
   event reminders, which then lacked an owner-active gate (fixed in `6a8061f`).
   **FENCE: never tune a system until its log tag proves it fired.** One grep beats an
   afternoon of tuning the wrong knob.
2. **"Heartbeat isn't working" usually is not a bug.** The heartbeat that "stopped"
   was nudge-budget exhaustion (default 3/day, `/nudges` to inspect) — the log said so:
   `[heartbeat] Nudge budget exhausted; saved draft.` **FENCE: before assuming
   breakage, check budget state (`/nudges`), `/quiet` state, and quiet hours.** Silence
   plus a skip-reason log line is the system working.
3. **Explicit user reminders and cron jobs fire on time on purpose.** The owner set the
   time. Deferring them "to be polite" is a regression, not a fix.

## Phase 0 — Instrument the baseline

You cannot tune what you have not counted. Establish per-bot, per-tag firing counts over
a window of N ≥ 3 days.

Send the owner these commands (dollar-free, one line per bot; repeat the block with each
of nora / bonnie / cass / emily / jules / priya):

```
grep -oE "\[(heartbeat|followup|event-reminder|reminders|stress|bb|rhr|onthisday)\]?[^]]*\]" ~/nora-bot/bot.log | sort | uniq -c | sort -rn
grep -o "\[heartbeat\] .*" ~/nora-bot/bot.log | sort | uniq -c | sort -rn
grep -c "owner active, deferring" ~/nora-bot/bot.log
```

Line 1 is the tag histogram (all senders). Line 2 is the heartbeat skip-reason
histogram — it distinguishes sends from quiet-hours drafts, budget drafts, mood skips,
and activity skips. Line 3 counts event-reminder deferrals. The logs may lack
timestamps, so counts are cumulative since log start: **run the same block again N days
later and subtract** to get per-window rates. Record both snapshots in your scratchpad.

**GATE 0.** Expected over the window, per bot:
- `[heartbeat] Proactive message sent.` — at most a few per day (2–6h roll × budget of
  3/day × skips means typically 1–3).
- `[event-reminder]` sends — only near real events the owner actually mentioned.
- `[followup]` — ZERO unless that bot's `.env` sets `FOLLOWUP_ENABLED=true`.
- Garmin tags — bounded by their cooldowns (≤ ~1/cooldown-window each).
- `[onthisday]` — ≤ 1/day and respecting `ONTHISDAY_MIN_GAP_DAYS`.

If counts are wildly off (a tag firing 10× its ceiling, a tag firing with its feature
disabled, zero heartbeat lines at all) → this is a BUG, not a tuning problem: **branch
to companion-bot-debugging-playbook** and come back when counts are sane. If counts are
plausible but the owner is still unhappy → proceed to Phase 1.

## Phase 1 — Classify the misfire

Get concrete examples from the owner: which bot, roughly when, what the message said,
what the owner was doing. Screenshot timestamps from Telegram are the timestamp source
when logs lack them. Classify EACH example into exactly one class:

- **Wrong-time** — fine message, bad moment (mid-conversation, mid-meeting, late).
- **Wrong-frequency** — too many (or too few) proactive contacts per day overall.
- **Wrong-content** — timing fine, but the message is robotic, repetitive, or generic.
- **Redundant** — two proactive systems (or two bots) stacking within minutes.

For each example, identify the sending path by log tag (Fence 1). A dollar-free
discriminator the owner can run, adjusting the tag and bot:

```
grep -n "\[event-reminder\]" ~/nora-bot/bot.log | tail -20
```

**GATE 1.** Every example has (a) one class and (b) one tag-proven sending path. If you
cannot prove the path for an example, discard the example — do not guess. Each class
routes to a different fix menu in Phase 3; **never apply a fix across classes** (e.g. do
not lower heartbeat frequency because one event reminder was robotic).

## Phase 2 — Measure the class

Turn the class into a number with an expected value, so the fix has a falsifiable target.

- **Wrong-time:** healthy = zero proactive sends within `EVENT_NUDGE_BUFFER_MIN`
  (15 min) of owner activity, excluding explicit reminders/cron (on-time by design) and
  excluding capped-defer fires (after 3 deferrals — 45 min of continuous activity — an
  event reminder fires anyway, by design). Measure: pair each offending send's Telegram
  timestamp with the owner's last message before it; also count capped fires:
  `grep -c "attempt 3/3" ~/nora-bot/bot.log`. Frequent 3/3 fires mean the buffer/cap
  knobs are the target.
- **Wrong-frequency:** proactive sends per bot per day, summed across tags, from the
  Phase 0 histograms. Compare against the owner's stated tolerance (ask for a number:
  "how many unprompted texts per bot per day feels right?").
- **Wrong-content:** define the repetitiveness metric BEFORE any fix. Collect the last
  10+ proactive messages per bot (owner forwards them, or exports the chat). Metric:
  trigram Jaccard overlap between consecutive proactive messages from the same bot.
  Compute it in YOUR scratchpad, not on the device. Record the baseline number.
- **Redundant:** count of days with ≥ 2 proactive sends from different tags (or
  different bots) within 30 minutes of each other, from Telegram timestamps. Healthy: 0.

**GATE 2.** You have a baseline number, an expected/target number, and the measurement
procedure written down. If the measurement shows the complaint is NOT reproducible in
the data (e.g. frequency is within the owner's stated tolerance), report that with the
numbers and STOP — do not tune to a vibe.

## Phase 3 — Solution menu, ranked. Cheapest first, each with obligations.

Work down this list; do not start at (d).

**(a) Per-system env-knob tightening.** Wrong-time on Garmin tags → add/derive an
owner-active defer (mirror `fire_reminder`'s `last_seen` check). Wrong-frequency on
heartbeat → raise `HEARTBEAT_MIN_HOURS`/`HEARTBEAT_MAX_HOURS` or lower the `/nudges`
budget. Event reminders firing into activity → raise `EVENT_NUDGE_BUFFER_MIN` or
`EVENT_NUDGE_MAX_DEFERS`. Obligation: before/after tag counts from the exact Phase 0
commands, same window length. Env-var names must be verified against
companion-bot-config-catalog before telling the owner to set them.

**(b) Cross-system "recently nudged" cooldown** (fixes redundant-class): any proactive
send records a timestamp; other paths skip/defer if a proactive went out within X
minutes. Derive it from the existing `last_seen` mechanics (a parallel `last_nudged`
dict, persisted like `last_seen` is). Obligation: this touches every proactive path's
gate order — route the design through companion-bot-architecture-contract's invariants
first, and exempt explicit reminders and cron (Fence 3).

**(c) Content variation keyed to recent-topic memory** (fixes wrong-content): feed the
last few proactive messages' topics into the proactive prompt so the model avoids
repeating itself. Obligation: the Phase 2 repetitiveness metric exists FIRST and you
show it move (baseline vs post-change trigram overlap on ≥ 10 messages each side). No
metric movement = revert.

**(d) Unified proactive scheduler — LAST RESORT.** One scheduler owning all proactive
paths, gates, and budgets. Obligations: full review against
companion-bot-architecture-contract; must not break the bot.py-standalone rule; explicit
owner sign-off BEFORE writing code; ships only through the Phase 4 A/B. If (a)–(c)
solved the measured problem, (d) is over-engineering — do not propose it.

All code changes: validate per companion-bot-validation-and-qa (compile gate, AST
dry-run for single functions), classify and ship per companion-bot-change-control.

**GATE 3.** A chosen fix, its class, its metric, and its predicted number ("after this,
heartbeat sends drop from ~5/day to ≤ 3/day on treated bots") written down before any
deploy. No prediction, no deploy.

## Phase 4 — Validation and promotion (the six-bot A/B)

The six instances are natural A/B cells.

1. Pick 2–3 treatment bots; the rest are controls. Treatment = the env flip or deployed
   change; controls stay as-is.
2. Env flips are owner-applied and dollar-free, one line per bot, e.g.:

   ```
   sed -i "s/HEARTBEAT_MAX_HOURS=6/HEARTBEAT_MAX_HOURS=8/" ~/nora-bot/.env
   ```

   then restart that bot per companion-bot-device-ops. Code changes deploy via
   `bash ~/telegram-bot/update-all.sh` (deploys bot.py to ALL bots — code-level A/B
   therefore needs the change to be env-gated so controls keep old behavior).
3. Define the falsifiable success criterion BEFORE flipping anything: the Phase 3
   prediction, measured by the Phase 0/2 commands, treated vs control.
4. Run ≥ 3 days. Re-run the measurement block on all six bots. Compare treated deltas
   against control deltas (controls absorb week-to-week noise).

**GATE 4.** Success = treated bots hit the predicted number AND controls did not move
comparably AND the owner confirms the felt problem improved. Then promote to all bots
via companion-bot-change-control. Failure or ambiguity = revert the treatment flips,
return to Phase 1 with the new data. Never promote on owner vibes alone, and never
leave a half-treated fleet: promote everywhere or revert everywhere.

## Provenance and maintenance

- Constants, gate order, defaults, and log tags verified by direct grep of
  `telegram-companion-bot/bot.py` on 2026-07-02; re-verify tag names and defaults
  against bot.py before each campaign run — this table goes stale silently.
- Event-reminder defer gate (`EVENT_NUDGE_BUFFER_MIN`/`EVENT_NUDGE_MAX_DEFERS`) added
  2026-07-01, commit `6a8061f`, after a live wrong-time incident; the misdiagnosis
  chain in the Fences section is from that same investigation.
- If a new proactive path is added to bot.py, add its row to the inventory table, its
  tag to the Phase 0 grep, and confirm it carries the owner-activity invariant.
