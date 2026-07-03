---
name: companion-bot-diagnostics
description: >
  Measurement and instrumentation reference for telegram-companion-bot: how to
  MEASURE bot health instead of eyeballing it. Load this skill when: interpreting
  /diag, /status, /health, /stress, /usage, /memory, /episodes, /recall, /nudges
  or any other in-chat diagnostic output; doing log forensics on bot.log or
  watchdog.log (what a [heartbeat]/[followup]/[garmin]/[memories] line means, or
  what its ABSENCE proves); the marker-grep/cmp verification technique for
  confirming a deploy landed (first stop for the SYMPTOM "did my deploy take?"
  is companion-bot-debugging-playbook); checking liveness (.alive
  heartbeat, tmux sessions, watchdog behavior); quantifying proactive behavior
  (how many nudges fired, why ticks were skipped); auditing env-var drift between
  code and .env.example; or gathering before/after evidence for any fix. Ships
  tested scripts in scripts/. Do NOT use for: choosing WHAT to investigate for a
  reported symptom (companion-bot-debugging-playbook has the symptom-to-first-command
  map); deep investigation methodology (companion-bot-analysis-toolkit); device
  setup, restart recipes, or deploy mechanics themselves (companion-bot-device-ops).
---

# Companion-Bot Diagnostics

Verified against bot.py (8937 lines), run-bot.sh, watchdog.sh, status.sh,
update-all.sh and .env.example at commit 80278bb on **2026-07-02**. Line numbers
refer to that bot.py. Re-verify with the one-liners in "Provenance and
maintenance" before trusting details after major changes.

**Motto: MEASURE, don't eyeball.** Every claim about bot behavior should be
backed by a number, a log line, or a deliberate absence of one.

## 0. Two measurement surfaces

Remote sessions **never touch the device**. Every measurement is one of:

1. **Repo-side analysis** — run here against the checked-out code
   (`telegram-companion-bot/`). The `scripts/` in this skill are mostly this kind.
2. **Device command handoff** — a command the owner pastes into Termux and whose
   output they paste back. The owner's chat client renders `$...$` spans as LaTeX
   and destroys them, so **every device-bound command must contain ZERO dollar
   signs**: use `~` and literal paths, no `$HOME`, no `$(...)`, no `${var}`, no
   loops — write one literal line per bot instead. (Full paste-corruption rules:
   companion-bot-device-ops.) Anything that genuinely needs `$` must travel as a
   file, not as chat text — see `scripts/proactive-log-summary.sh`.

## 1. In-chat diagnostic commands

All commands are owner-gated by `_guard()`. Registered in `main()` around
bot.py:8733-8817.

### /diag — the first-stop instrument (bot.py:5043)

One message that answers "what is on, what is loaded, what has been failing".
Anatomy, line by line:

| /diag line | What it reports | How to interpret |
|---|---|---|
| `Features:` block | ✅/— per feature flag: embeddings (+`EMBED_MODEL` name), episodic recall, safety, scene, offline life, event reminders, reading, on-this-day, style mirror, garmin, stress, resting-HR, body-battery | A — where you expected ✅ means the env var did not take: either never set in that bot's `.env`, or paste-corrupted, or the bot was not restarted after the edit. This is *the* fast check for "I set X and nothing changed". |
| `Embedded: N memories, N episodes, N lore (numpy: yes/MISSING)` | only shown when `EMBED_ENABLED`; sizes of the three vector stores | `0 memories` with a populated memories.txt = backfill failed (grep the log for `[memories] vector backfill`). `numpy: MISSING` = episodic recall silently dead — `pkg install python-numpy` on Termux. Episodes count only grows as conversation ages out of the live window; 0 on a fresh bot is normal. |
| `Garmin: snapshot X.Xh old; token cached/none` | age of last watch pull, auth token presence | snapshot older than `GARMIN_MAX_AGE_HOURS` (default 18) means it is no longer being injected into prompts. `token none` = next pull does a fresh password login (breaks more often). |
| `Memory: N NPC notes · N milestones · N reminders` | sizes of memories.txt, milestone list, this chat's reminders | Sudden drop in NPC notes = memories.txt was truncated/rewritten. Reminders 0 right after the owner mentioned a dated event = event extraction did not fire (grep `[event]`). |
| `bot_app: ✅ loaded · N untrusted note(s) quarantined` or `— not loaded (untrusted-notes channel off)` | whether the modular `bot_app/` package imported | `not loaded` on the device usually means `bot_app/` is missing or stale there — update-all.sh syncs it in lockstep with bot.py; a hand-copied bot.py without bot_app produces exactly this. The quarantined count is the untrusted-notes store (capped by `MAX_UNTRUSTED_NOTES`, default 60): a *growing* count is the quarantine doing its job, not a bug. |
| `Log errors (last 300 lines): N` + `↳ last error` | count of error/traceback/exception lines in the tail of that instance's bot.log | 0 = calm. Nonzero: the quoted last error tells you which subsystem to grep for. Note this window is the last 300 *lines*, not last N hours — a chatty bot scrolls errors out of the window fast. |

### The rest of the instrument panel

| Command | bot.py | Reports | Diagnostic use / interpretation |
|---|---|---|---|
| `/status` | 8218 | mood label + score bar, current outfit, life-arc/day/user-notes snippets, weather, quiet-mode remaining, time since last chat | "Is her state machine sane right now." A `Quiet mode: Nm remaining` line explains silent proactive behavior instantly. Mood bar is score −3..+3 mapped to 10 blocks. |
| `/health` | 4997 | latest Garmin snapshot + its age | Age stamp is the key datum: "20h ago" means pulls are failing — force one with /healthnow and read the error. |
| `/healthnow` | 5012 | forces a Garmin pull, prints result or "Couldn't pull anything that time (check the logs)" | The failure text lives in the log under `[garmin]` — this command is how you *provoke* a fresh, timestamped failure to grep for. |
| `/stress` | 5026 | avg Garmin stress over last `STRESS_SUSTAINED_MIN` (default 45) min, vs `STRESS_THRESHOLD` (default 60) | `avg 0` = no readings = watch not synced; distinguishes "alert system broken" from "no data". |
| `/usage` | 7291 | NanoGPT subscription daily/monthly used/remaining | `remaining 0` explains a suddenly mute or degraded bot (chat calls failing → fallback model or nothing). Check this before debugging "she stopped replying" as a code problem. |
| `/memory` | 4895 | long-term summary + facts, recent (~week) summary + facts | The two-tier memory state verbatim. Before/after evidence for any memory fix: capture it, apply fix, capture again, diff. |
| `/mems` | 5688 | numbered dump of every NPC/world memory (memories.txt) | Numbers feed /delmem. Count here should match /diag's "N NPC notes". |
| `/episodes` | 5746 | archive size vs `EPISODE_MAX` cap + newest chunk preview | Explicitly reports when episodic recall is off or numpy is missing. Archive frozen at the same N for days while chatting daily = archiving broken (grep `[episodes] archived`). |
| `/recall <kw>` | 5833 | keyword hits across facts/recent-facts/summaries, plus semantic `[memory~]` hits when embeddings on | Ground-truth probe: "does she actually hold X?" A `[memory~]` hit but no `[fact]` hit means it lives in NPC memory, not user facts — different fix path (/delmem vs /forget). |
| `/nudges` | 5412 | today's proactive budget `sent/limit` (or set it: `/nudges N`, 0 = unlimited) | `3/3` = budget exhausted → heartbeats will log `Nudge budget exhausted; saved draft` until midnight reset. First check when "she went quiet today". |
| `/mood` | 4918 | mood label, score, bar, age of last appraisal | Persistent score ≤ −1.2 makes heartbeats skip 60% of ticks (bot.py:8138) — a *measured* cause of proactive silence. |
| `/milestones` | 5091 | dated relationship milestones list | Nightly detection evidence; pairs with `[milestones] recorded N new` in logs. |
| `/heartbeat` | 8161 | forces a proactive message NOW, replies with the error on failure | Bypasses all gates (budget, quiet hours, mood). Use to split "proactive generation broken" from "proactive gates suppressing" — if /heartbeat works, the pipeline is fine and a gate fired; go read the `[heartbeat]` outcome lines. |
| `/exportmemory` | 5106 | full memory state as an attached .txt file | The before/after artifact for memory-surgery evidence. |
| `/quiet` | 6209 | set/inspect do-not-disturb | Its remaining time also shows in /status. |
| `/chatid` | — | your Telegram user id | Needed once for `ALLOWED_USERS`. |

Also real but secondary as instruments: `/reading`, `/news` (life-sim output so
far today), `/reminders`, `/crons`, `/payments`, `/settings`, `/model`.

## 2. Log forensics

### The convention

bot.py logs with `print("[tag] ...")` / `print(f"[tag] ...")` — 118 tagged print
sites. The process runs `python -u` piped through `tee -a bot.log` (run-bot.sh),
so lines are **unbuffered and real-time**. Bot lines carry **no timestamps**; the
only dated lines are the supervisor's `[run-bot] starting <session> at <date>` /
`[run-bot] <session> exited (code N) at <date>` — use those to bracket time
windows when reconstructing when something happened.

- Per-instance log: `~/<char>-bot/bot.log` (e.g. `~/nora-bot/bot.log`).
- Watchdog log: `~/telegram-bot/watchdog.log` — dated `<session> <reason> -> relaunching` lines.
- **Rotation** (run-bot.sh:62-66): the supervisor checks size *before each
  (re)start*; if bot.log > 5 MB it moves to `bot.log.1` (one backup, older
  history is gone). Consequence: rotation only happens on restart, so a
  long-lived bot's log can exceed 5 MB; and forensic windows are bounded — check
  `bot.log.1` too before declaring something absent.

### Absence of evidence IS evidence — with three preconditions

An empty grep is a valid discriminator (an empty `[followup]` grep once ruled
out an entire hypothesis about a mystery message). But an absent line only
proves something if:

1. **The deployed code contains the print.** Verify deploy sync FIRST (section 4)
   — greping a stale bot.py's log for a tag you added yesterday proves nothing.
2. **The feature is on** — check the /diag Features block.
3. **The log window covers the incident** — bracket with `[run-bot]` dates and
   check bot.log.1.

With those held: no `[followup] scheduled` lines → the follow-up path never
armed → the unexpected message was NOT a follow-up. No `[heartbeat]` lines at
all for hours → the job queue itself is dead or the process is down (every tick
logs *something*, see below). No `[memories] added:` across days of chatting →
memory extraction is silently failing or gated off.

### Tag map

Regenerate this list any time with `scripts/enumerate-log-tags.sh`. Two kinds of
tag: **progress tags** (presence = healthy) and **error-only tags** (healthy
state is zero lines). Grouped by subsystem:

**Proactive / outbound**

| Tag | Meaning | Healthy line | An absent line proves |
|---|---|---|---|
| `[heartbeat]` | proactive tick engine; **every tick prints ≥1 line**: always `next check in X.Xh` (reschedule, 8114), then exactly one outcome: `No owner yet` / `Owner recently active; skipping` / `Quiet hours; saved draft` / `User /quiet active; skipping` / `Nudge budget exhausted; saved draft` / `Mood is low (−X.X); saved draft` / `Proactive message sent.` / `Error:` | `[heartbeat] Proactive message sent.` | No `[heartbeat]` lines in a window ≥ `HEARTBEAT_MAX_HOURS` = ticks not firing at all (dead job queue / process down) — a much stronger claim than "gates suppressed it". |
| `[proactive]` | provider refused a proactive generation; retry / skip notice | (error-only) | absence = no provider refusals on proactive sends |
| `[followup]` | short-delay follow-up armed when `_FOLLOWUP_RE` matches an away-signal ("brb", "hold on") in the BOT'S OWN reply (7375), or failed later (7666); `FOLLOWUP_ENABLED` default off | `scheduled in 87s for chat N` (always within 45–120s, `FOLLOWUP_MIN_SECS`–`FOLLOWUP_MAX_SECS`) | message in question was not a follow-up |
| `[draft]` | proactive urge suppressed by a gate, saved as unsent thought (1737) | `Saved unsent thought for chat N: <reason>` | no gate suppressed anything (nothing wanted to send, or sends went out) |
| `[event]` | dated-event nudges scheduled from a message (6637) | `scheduled 2 nudge(s) for: dentist Tuesday` | event extraction never scheduled anything — the "good luck" text can't have come from here |
| `[event-reminder]` | a scheduled event nudge deferring (owner mid-conversation) or failing to fire | `... owner active, deferring` | no deferrals/failures |
| `[onthisday]` | anniversary reminiscence fired (3078) | `resurfaced an episode from <when>.` | on-this-day never fired in window |
| `[stress]` `[bb]` `[rhr]` | Garmin-derived check-ins: sustained stress, low body battery, elevated resting HR; each has fetch-failed / sent / alert-failed forms | `high-stress check-in sent (avg 71).` | that alert system did not send the message under investigation |
| `[cron #N]` | owner-defined cron job ran or errored (8030) | `Ran: <instruction>` | cron #N never executed |
| `[payments]` | weekly payment reminder sent (6150) or load failed | `Reminder sent: 3 due ...` | — |
| `[backup]` | weekly backup document sent (6426) | `Weekly backup sent: ...` | backup job didn't run |

**Memory layers**

| Tag | Meaning | Healthy | Absent proves |
|---|---|---|---|
| `[memory]` | rolling history → summary/facts machinery: `Summarized N message(s)`, `Consolidated recent facts a -> b`, `Promoted recent memory to long-term`, `Consolidated long-term facts a -> b`; plus error forms | `Summarized 12 message(s) for chat N.` | no summarization happened → history isn't overflowing (short conversations) or maintenance never runs |
| `[memories]` | NPC-memory extraction + embedding: `added: <mem>` (1168), `vector backfill complete (N embedded)` (8697); several error forms (embed/extraction/save failed) | `added: <mem>` | extraction added nothing (absence across active days = broken or gated) |
| `[episodes]` | episodic archive: `archived N chunk(s); N held` (954), `loaded N archived chunk(s)` at startup (8712); error forms | `archived 1 chunk(s); 392 held.` | nothing archived → /episodes count will be frozen; recall of new material impossible |
| `[lore]` | lorebook embedding at startup | `embedded 24 lorebook entries.` | lore vectors never loaded |
| `[recall]` `[rerank]` | error-only: semantic search / reranker failed (both fall back to keyword / cosine) | (silence) | fallbacks not engaged |
| `[photo-memory]` | fact extracted from a photo the owner sent (7645) | `<fact text>` | photos produced no memories |
| `[user-notes]` | note about the owner appended (6657) | `added: <note>` | — |
| `[upcoming]` | error-only: upcoming-thing extraction/update failed | (silence) | — |

**Character life simulation**

| Tag | Meaning | Healthy | Absent proves |
|---|---|---|---|
| `[life]` | offline-life event generated (2679) | `event: <line>` | she "lived" nothing → /news empty is expected, not a display bug |
| `[reading]` | reading-feed item added (2602) | `added (topic): <line>` | — |
| `[day-events]` | morning generation of today's 2-3 small events (8316) | `<NAME>: <events>…` | day.txt never filled today |
| `[day-rotate]` | midnight archive of day context (8343) | `archived 2026-07-01: <ctx>…` | — |
| `[mood]` | mood appraisal after exchanges (2367) + overnight reset (8184) | `settled (+1)` | mood never updated |
| `[scene]` | error-only: scene-continuity extraction failed | (silence) | — |
| `[milestones]` | nightly milestone detection (2544) | `recorded 1 new for chat N.` | — |
| `[wardrobe]` `[weather]` `[time]` | error-only: load/fetch/timezone failures | (silence) | — |

**Reply pipeline and providers**

| Tag | Meaning | Healthy | Absent proves |
|---|---|---|---|
| `[model]` | chat-model transient error / retry / fallback engaged (3505, 3509) | (error-only; a retry line that resolves is benign) | primary model never faltered |
| `[models]` `[setmodel]` | model-list fetch / /setmodel errors | (silence) | — |
| `[reply]` | provider moderation refusal suppressed instead of shown (7323) | (informational) | refusals aren't why a reply vanished |
| `[react]` `[react-auto]` | reaction set failed / auto-reaction applied or failed | `[react-auto] applied 👍` | — |
| `[selfie]` | image-gen retries and failures | (error-only) | selfie pipeline never errored |
| `[safety]` | error-only: distress classifier call failed | (silence) | — |
| `[search]` `[link]` | web search rejected/failed; link fetch failed | (error-only) | — |
| `[sticker]` `[voice-tone]` | sticker handling / vocal-tone analysis errors | (error-only) | — |

**Infrastructure**

| Tag | Meaning | Healthy | Absent proves |
|---|---|---|---|
| `[net]` | one quiet line per transient network error (8583) | (error-only; occasional lines on mobile networks are normal) | — |
| `[error]` | full traceback from the global error handler (8587) | (error-only) | no unhandled exceptions in window |
| `[config]` | bad sampling env value ignored (145) | (error-only) | sampling knobs parsed clean |
| `[reminders]` `[cron]` | state-file load failures at startup | (silence) | persisted state loaded fine |
| `[run-bot]` | **from run-bot.sh, not bot.py**: dated start/exit lines | one `starting` line per boot | count of `starting` lines = restart count; `exited (code N)` lines show crash loops with timestamps |

### Quantifying a log

Don't count by eye. Repo-side, regenerate the tag list with
`scripts/enumerate-log-tags.sh`. Device-side, ship
`scripts/proactive-log-summary.sh` to the phone once (as a file — it uses `$`
internally) and then this chat-safe line does the whole census:

```
bash ~/telegram-bot/proactive-log-summary.sh ~/nora-bot/bot.log
```

It prints per-tag counts, the heartbeat outcome breakdown (sent vs each skip
reason — the exact "why was she quiet / why so chatty" numbers), other
proactive-send evidence, restart count with dates, and error counts.

## 3. Liveness measurement

Three independent signals, weakest to strongest:

1. **Process exists**: `pgrep -af bot.py` — one python line per running instance.
2. **tmux session exists**: `tmux ls` — sessions named `nora bonnie cass emily jules priya`. A session can exist around a dead loop, so this alone is weak.
3. **Event loop is actually turning**: the `.alive` stamp. bot.py touches
   `~/<char>-bot/.alive` immediately at startup (8829) and then **every 60s**
   from a job on the event loop (8683, 8832). A fresh stamp proves the asyncio
   loop itself is alive — the one thing a live process + live tmux cannot prove.

**Watchdog semantics** (watchdog.sh): every `WATCHDOG_INTERVAL` (default 300s)
it relaunches any bot whose tmux session is missing, and any whose `.alive`
exists but is older than `WATCHDOG_STALE` (default 300s) — logged as
`frozen (heartbeat NNNs old)` in `~/telegram-bot/watchdog.log`. A **missing**
`.alive` is deliberately left alone (just-started or pre-feature bot.py).

Zero-dollar device commands (paste-safe, output pasted back):

```
bash ~/telegram-bot/status.sh
```
One table: per bot — SESSION up/DOWN, HEARTBEAT age, error count in last 300
log lines. This is the standing "how is the fleet" measurement.

```
tmux ls
pgrep -af bot.py
ls -l ~/nora-bot/.alive ~/bonnie-bot/.alive ~/cass-bot/.alive ~/emily-bot/.alive ~/jules-bot/.alive ~/priya-bot/.alive
tail -20 ~/telegram-bot/watchdog.log
```

Interpretation:

| Measurement | Value | Meaning | Next action |
|---|---|---|---|
| status.sh HEARTBEAT | < 120s | loop alive | nothing |
| status.sh HEARTBEAT | > 300s, SESSION up | frozen loop; watchdog should catch it within ~5 min | if it persists past two watchdog intervals, watchdog isn't running — check watchdog.log mtime |
| status.sh HEARTBEAT | `—` (no .alive) | just restarted, or deployed bot.py predates the liveness feature | check `[run-bot] starting` date; then deploy-sync check |
| status.sh SESSION | DOWN | tmux gone (Android killed Termux, or reboot without boot script) | watchdog relaunch expected; see companion-bot-device-ops for recovery |
| watchdog.log | repeating `frozen` relaunches for one bot | that instance wedges repeatedly — a code problem, not an ops problem | log forensics on its bot.log around the `[run-bot]` timestamps |
| bot.log | many `exited (code 1) ... restarting in 5s` in a tight loop | crash loop; the traceback is directly above each exit line | read the traceback; likely bad deploy or bad state file |

## 4. Deploy-sync verification

Stale deploys are the costliest failure class: you fix code here, the owner
"deploys", the device still runs old code, and every subsequent measurement lies.
**Verify deploy sync before trusting any other measurement after a change.**

What `bash ~/telegram-bot/update-all.sh` actually syncs (verified in
update-all.sh): git-pull of `~/stp-deploy` (ff-only, autostashes stray changes,
aborts loudly on failure), then copies `bot.py` (with a built-in `cmp` check),
`bot_app/` (rm -rf + full copy), `acoustic_ears.py`, `run-bot.sh`,
`watchdog.sh`, `status.sh`, `.env.example` — and restarts all six instances. It
never touches per-bot `.env` files, and never updates `update-all.sh` itself
(copy that by hand when it changes).

Three escalating zero-dollar checks:

**1. Files match the clone** (silence from cmp = identical):

```
cmp ~/stp-deploy/telegram-companion-bot/bot.py ~/telegram-bot/bot.py && echo MATCH || echo STALE
```

**2. Clone is at the right commit** (matches what you pushed):

```
git -C ~/stp-deploy log -1 --oneline
```

**3. The running process has the new code** — files matching is not enough if
the bot wasn't restarted. Confirm the restart happened after the deploy:

```
grep run-bot ~/nora-bot/bot.log | tail -3
```

(the `starting` date must postdate the deploy), and confirm the *content* with a
marker grep. Generate it repo-side:

```
bash .claude/skills/companion-bot-diagnostics/scripts/deploy-marker.sh
```

which prints HEAD, the expected line count, and a ready-to-send zero-dollar
command like:

```
grep -cF 'audio_bytes = await asyncio.to_thread(_synth_inworld, text)' ~/telegram-bot/bot.py
```

Reply `1` = deployed file contains the newest change; `0` = stale. Quick
secondary check: `wc -l ~/telegram-bot/bot.py` against the repo's line count
(update-all.sh prints it at deploy time too).

| Measurement | Value | Meaning | Next action |
|---|---|---|---|
| cmp check | STALE | copy step failed or update-all never ran | rerun update-all.sh; if it errors, its own messages name the fix (diverged clone etc.) |
| clone commit | behind your push | owner pulled before you pushed, or pull failed | push, rerun |
| marker grep | 0 but cmp says MATCH | you generated the marker from a different commit than the owner pulled | re-run deploy-marker.sh at the deployed commit |
| files new, `[run-bot] starting` old | process never restarted | restart (update-all does this; a manual copy does not) |
| `/diag` shows a feature — that the new code defaults on | .env override, or still stale | check .env (device-ops), then marker grep |

## 5. Shipped scripts

All in `scripts/` next to this file; all pass `bash -n`; the three repo-side
ones were executed against the live repo, the device-side one against a
synthetic log. Each has a usage header.

| Script | Side | What it measures |
|---|---|---|
| `enumerate-log-tags.sh` | repo | Re-derives the full bracketed log-tag list from bot.py with counts and line numbers. Run it whenever bot.py changes to keep section 2 honest. |
| `config-drift-check.sh` | repo | Env vars read by bot.py/bot_app (literal `os.getenv`, multi-line calls, and the sampling-knob table) vs vars documented in .env.example, both directions. As of 2026-07-02: 178 vars read, 99 documented, **0 phantom** (.env.example names nothing the code ignores), 79 undocumented — many intentionally internal (`BOT_HOME` is set by the launcher, `BOT_TOKEN` is bot_app-only, `WATCHDOG_*` belong to watchdog.sh); judge each hit, and see companion-bot-config-catalog for the authoritative var-by-var story. |
| `deploy-marker.sh` | repo | Prints HEAD, last commit touching bot.py, expected line count, and a paste-safe unique marker line + the zero-dollar device grep that confirms a deploy (section 4). |
| `proactive-log-summary.sh` | device | Per-tag counts, heartbeat outcome breakdown, proactive-send evidence, restart dates, error counts for one bot.log. Uses `$` internally → **must reach the phone as a file**; the invocation line is dollar-free (section 2). |

## 6. Consolidated interpretation table

Measurement → pattern → meaning → next action. For symptom-driven entry points
("she texted me out of nowhere", "bot frozen") start from
companion-bot-debugging-playbook, which picks the discriminator; this table is
for reading the numbers once you have them.

| Measurement | Value / pattern | Meaning | Next action |
|---|---|---|---|
| /diag Features | expected ✅ shows — | env var not in effect | .env check + restart check (device-ops), then paste-corruption suspicion |
| /diag Embedded | `numpy: MISSING` | episodic recall dead despite flags on | owner installs python-numpy, restart |
| /diag bot_app | `not loaded` | bot_app/ missing/stale on device | run update-all.sh (it syncs bot_app in lockstep) |
| /diag Log errors | > 0 | recent failures; last one quoted | grep bot.log for the quoted tag |
| /nudges | `3/3` (or N/N) | budget spent; heartbeats drafting instead of sending | expected silence; raise with /nudges N if unwanted |
| /mood score | ≤ −1.2 persistently | 60% of proactive ticks self-skip (8138) | that's designed behavior; tune mood, not the heartbeat |
| /usage | remaining 0 | provider quota exhausted | wait for reset / switch model; not a code bug |
| /heartbeat (forced) | works, but organic sends absent | generation fine, a gate fires | read `[heartbeat]` outcome lines / log summary breakdown |
| /heartbeat (forced) | replies with error text | proactive pipeline itself broken | that error string is the lead; grep its tag |
| log-summary heartbeat block | many `Quiet hours; saved draft` at odd times | timezone wrong on device | `TIMEZONE` var + `[time]` tag at startup |
| log-summary heartbeat block | zero lines of any kind | ticks not firing: process/job queue down | liveness checks (section 3) |
| `[followup]` grep | empty (preconditions of section 2 held) | mystery message wasn't a follow-up | check `[heartbeat]`, `[event]`, `[stress]`/`[bb]`/`[rhr]`, `[cron #]` sends instead |
| `[run-bot] starting` count | climbing without owner action | crash loop or watchdog frozen-restarts | tracebacks above `exited` lines; watchdog.log reasons |
| `.alive` age | > 300s while session up | wedged event loop | expect watchdog restart; if none, watchdog itself is down |
| cmp / marker grep | STALE / 0 | measurements about "current" code are void | fix deploy first, re-measure everything after |

## Provenance and maintenance

Everything above was read from the code, not remembered. Re-verify (repo root):

- Tag list current? `bash .claude/skills/companion-bot-diagnostics/scripts/enumerate-log-tags.sh` — diff against section 2.
- Command list current? `grep -n 'CommandHandler(' telegram-companion-bot/bot.py` — diff against section 1 (registrations live ~8733-8817).
- Config drift snapshot current? `bash .claude/skills/companion-bot-diagnostics/scripts/config-drift-check.sh` — update the counts in section 5 if they moved.
- Deploy manifest current? `sed -n '30,70p' telegram-companion-bot/update-all.sh` — diff against section 4's synced-files list.
- Liveness constants current? `grep -n 'WATCHDOG_STALE\|interval=60' telegram-companion-bot/watchdog.sh telegram-companion-bot/bot.py` and `grep -n 5242880 telegram-companion-bot/run-bot.sh` (rotation cap).
- Scripts still parse? `for f in .claude/skills/companion-bot-diagnostics/scripts/*.sh; do bash -n "$f" && echo "OK $f"; done`

Last full verification: **2026-07-02**, commit 80278bb.
