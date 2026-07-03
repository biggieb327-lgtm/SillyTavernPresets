---
name: companion-bot-debugging-playbook
description: >
  Symptom-to-discriminator triage playbook for debugging the telegram-companion-bot
  (bot.py) instances running on the owner's Termux/Android phone. Load this skill
  whenever the owner reports ANY bug or unexpected behavior: "X isn't working",
  "the bot sent a message it shouldn't have", "she texted me out of nowhere",
  proactive/heartbeat message complaints, bot not responding, bot frozen, voice
  notes or voice replies failing, selfies broken or weird, crash on startup,
  "did my deploy take?", or any log/error output pasted from the device. It gives
  the exact first command to send the owner for each symptom, the log-tag map for
  every proactive system, and the project's known debugging traps. Do NOT use for:
  deep memory-recall investigations (use companion-bot-memory-campaign), designing
  or tuning proactive behavior (companion-bot-proactive-tuning-campaign), deploy
  and device mechanics reference (companion-bot-device-ops), or in-depth
  investigation methodology (companion-bot-analysis-toolkit).
---

# Companion-Bot Debugging Playbook

How to debug `telegram-companion-bot/bot.py` (~8,900 lines, single file) when it
misbehaves on the owner's phone. All facts below verified against the repo on
**2026-07-02**; see "Provenance and maintenance" for re-verification commands.

## The setting (read once)

- **You never have device access.** The bots run on the owner's Android phone
  under Termux. The owner runs commands you give them and pastes the output back.
- Cloud repo (branch `claude/push-to-repo-7i2f3c`) → phone clone `~/stp-deploy` →
  deployed code `~/telegram-bot/bot.py` → per-character instance dirs
  `~/nora-bot`, `~/bonnie-bot`, `~/cass-bot`, `~/emily-bot`, `~/jules-bot`,
  `~/priya-bot` (six instances as of 2026-07-02; the list lives in `watchdog.sh`
  and `update-all.sh`).
- Each instance runs in its own tmux session (named after the character) under a
  supervisor loop written by `run-bot.sh`. Logs:
  - Per-bot: `~/<char>-bot/bot.log` (rotated to `bot.log.1` at ~5 MB by the supervisor)
  - Watchdog: `~/telegram-bot/watchdog.log`
- Liveness: the bot stamps `~/<char>-bot/.alive` every 60 s
  (`_touch_liveness`, scheduled in `main()`); `watchdog.sh` restarts any bot
  whose `.alive` is older than `WATCHDOG_STALE` (default 300 s) even if its
  tmux session is up. Missing `.alive` is deliberately left alone.
- Deploy is `bash ~/telegram-bot/update-all.sh`: pulls `~/stp-deploy`, copies
  `bot.py` (and `bot_app/`, `acoustic_ears.py`, helper scripts) into
  `~/telegram-bot/`, `cmp`-verifies the bot.py copy, restarts all instances.
  `update-all.sh` does NOT copy itself, and never touches per-bot `.env` files.

Jargon: a **proactive message** is anything the bot sends without the owner
having just messaged it. There are many independent systems that can do this —
see the enumeration table below.

## The remote-debugging protocol (non-negotiable)

The owner has confirmed this discipline as required. Never skip steps, never fix
on a guess.

1. **State the hypothesis.** One sentence: "I suspect X because Y."
2. **Give ONE exact discriminating command.** Copy-pasteable, chosen so its
   output will *confirm or refute* the hypothesis — not just "gather info".
   State in advance what output means "confirmed" and what means "refuted".
3. **Wait for the paste.** Do not stack commands, do not propose fixes yet.
4. **Judge the evidence honestly.** If refuted, say so, discard the hypothesis,
   and move to the next one. Delay-window or timing coincidence is NOT evidence.
5. **Only fix a confirmed cause.** Then give one verification command that
   proves the fix on-device (a log line, a `pgrep`, a `cmp`).
6. **Before ANY logic debugging, rule out a stale deploy** (see traps). It is
   this project's costliest historical failure class.

### Command formatting rules for the owner's device

- **ZERO dollar signs** in any command destined for the owner. The owner's chat
  client strips `$...$` spans (renders them as math), silently corrupting
  commands. Use `~` for home and literal per-bot lines instead of shell loops
  with variables.
- If a command that reached the device behaves inexplicably, suspect paste
  corruption first: have the owner run `cat -A` on the file (or history) to see
  what actually landed.
- Keep commands short and single-purpose so the pasted output is unambiguous.

(Full command-formatting rules: companion-bot-device-ops.)

## Symptom → first discriminating command

For every row: hypothesis order is left to right in the notes; always send only
the FIRST command, interpret, then proceed. Replace `nora` with the affected
character; every instance has the same layout.

| Symptom | First command (paste-safe) | If hypothesis TRUE you see | If FALSE you see |
|---|---|---|---|
| Unexpected / mistimed proactive message | `grep -aE "\[heartbeat\]\|\[followup\]\|\[event-reminder\]\|\[stress\]\|\[bb\]\|\[rhr\]\|\[onthisday\]\|\[cron\|\[proactive\]\|\[payments\]\|\[backup\]" ~/nora-bot/bot.log \| tail -40` | A tagged line timestamp-adjacent to the rogue message names the sender system | No tagged line near that time → message came from the normal reply path or a system without a send-log; widen with `tail -200 ~/nora-bot/bot.log` |
| Bot not responding at all | `bash ~/telegram-bot/status.sh` | `SESSION DOWN` or `HEARTBEAT ...h ago (stale)` for that bot | All `up`, heartbeat seconds-fresh → process is fine; suspect Telegram-side, network, or the reply path (check `tail -50 ~/nora-bot/bot.log`) |
| Bot frozen-but-alive (session up, no replies) | `ls -l ~/nora-bot/.alive` | `.alive` mtime > 5 min old → event loop wedged; watchdog should restart it within `WATCHDOG_STALE` (300 s default) — if it didn't, check the watchdog (next row) | mtime < 60–120 s old → loop is ticking; problem is upstream (Telegram polling, guard, model call) |
| Watchdog suspected dead | `pgrep -af "watchdog.sh --loop"` | No output → loop is dead; check `tail -20 ~/telegram-bot/watchdog.log` and relaunch via the setsid line in `termux-boot-start.sh` | One process line → loop alive; check `watchdog.log` for what it decided |
| Voice notes failing (owner sends voice, gets "[couldn't make out that voice note]") | `grep -c INWORLD_API_KEY ~/telegram-bot/common.env ~/nora-bot/.env` | `0` in both files → key not configured (STT raises `INWORLD_API_KEY not configured`) — first check since the 2026 Inworld migration | Key present (count ≥ 1 somewhere) → `grep -ai "transcription failed" ~/nora-bot/bot.log \| tail -5` for the real HTTP error (401 = bad key, 4xx/5xx = API) |
| Voice replies failing (text arrives, no audio) | `grep -ai "TTS failed" ~/nora-bot/bot.log \| tail -5` | Error lines: 401 → `INWORLD_API_KEY`; 400/404 mentioning voice → invalid `TTS_VOICE` voiceId (valid ids: Inworld `GET /voices/v1/voices`) | No lines → TTS never attempted: voice replies are per-chat opt-in (`/voice on`) and fire only `TTS_CHANCE` (default 0.30) of the time — probably just the dice |
| Selfie anomalies (fails, wrong look, refusal) | `grep -a "\[selfie\]" ~/nora-bot/bot.log \| tail -5` | `[selfie] failed: ...` with the provider error (Gemini by default when `GEMINI_API_KEY` set, else NanoGPT) | No failures → image generated; anomaly is prompt-side (`appearance.txt` / base photo / `build_selfie_prompt`), a code question, not a device one |
| Memory recall wrong ("she forgot X", wrong fact) | Have the owner send `/diag` to the bot in Telegram | `Embedded: 0 memories ...` or `numpy: MISSING` → retrieval infrastructure down | Counts healthy → this is a real memory-quality issue: **stop and switch to the companion-bot-memory-campaign skill** |
| Deploy suspected stale | `cmp ~/stp-deploy/telegram-companion-bot/bot.py ~/telegram-bot/bot.py && echo SAME` | Anything but `SAME` (a differ line) → stale deploy confirmed; rerun `bash ~/telegram-bot/update-all.sh` | `SAME` → deployed file matches the clone; also confirm the clone itself is current: `git -C ~/stp-deploy log --oneline -1` and compare to the expected commit |
| Crash on startup / restart loop | `tail -50 ~/nora-bot/bot.log` | Repeating `[run-bot] starting ... exited (code N) ... restarting in 5s` every ~5 s, with a traceback or a `SystemExit` reason between (`TELEGRAM_BOT_TOKEN not found`, `NANOGPT_API_KEY not found`, `SELFIE_PROVIDER=gemini but GEMINI_API_KEY not found`) | Single clean start, no exit lines → not a startup crash; reclassify the symptom |
| One bot broken, others fine | `diff <listing not possible without vars — instead:> ls ~/nora-bot/` then compare to a healthy bot: `ls ~/emily-bot/` | Missing/odd files (`.env`, character card, base photo) explain the divergence | Same layout → suspect that bot's `.env` values; helper scripts and `bot.py` are shared, so per-bot config is the only per-bot difference |

Note the shared-vs-per-bot rule: **`bot.py` is identical across all six bots.**
A bug in one bot only = config (`.env`, character card, appearance files,
state files in that dir). A bug in all bots = code or shared `common.env`.

## Every proactive system, by log tag

There are MANY independent proactive senders. When the owner says "she texted
me out of nowhere," discriminate by log tag, never by timing vibes. All of these
live in `bot.py`; entry points named for grep-ability.

| System | Function(s) | Log tag | Cadence / trigger | Owner-active guard? |
|---|---|---|---|---|
| Heartbeat check-in | `heartbeat`, `schedule_next_heartbeat`, sends via `send_proactive` | `[heartbeat]` | Random 2–6 h (`HEARTBEAT_MIN_HOURS`/`MAX`); persisted across restarts | Yes — skips if owner active within ~0.9×min window; also quiet hours, `/quiet`, nudge budget, low mood |
| Follow-up ("brb" comeback) | `_send_followup`, gated by `_FOLLOWUP_RE` on the BOT's own reply | `[followup]` | 45–120 s (`FOLLOWUP_MIN_SECS`/`MAX`) after the bot says brb/hold on/one sec; **off by default** (`FOLLOWUP_ENABLED`) | Cancelled if the user replies first |
| Event reminders (auto-extracted) | `fire_reminder` with `kind == "event"`; scheduling logs `[event]`/`[upcoming]` | `[event-reminder]` | At the extracted event time; recurring ones re-arm | Since commit `6a8061f`: defers 15 min (`EVENT_NUDGE_BUFFER_MIN`) up to 3 times (`EVENT_NUDGE_MAX_DEFERS`) if owner active, **then fires anyway** |
| Plain reminders (`/remindme`) | `fire_reminder`, non-event kind | (sends literal `⏰ Reminder:` text, no log tag) | At the set time | No |
| Garmin stress monitor | `stress_monitor_job` | `[stress]` | Every 30 min (`STRESS_POLL_MIN`) when `STRESS_ALERTS` on | Cooldown hours + quiet hours + `/quiet`; no recent-activity check |
| Garmin body-battery monitor | `bb_monitor_job` | `[bb]` | Every 30 min when `BB_ALERTS` on | Same as stress |
| Garmin resting-HR monitor | `rhr_monitor_job` | `[rhr]` | Once daily (morning) when `RHR_ALERTS` on | Once/day + quiet hours |
| On-this-day reminiscing | `onthisday_job` | `[onthisday]` | Once daily; min-gap days between reminisces | Quiet hours + `/quiet` |
| Cron jobs (`/cron`) | `run_cron_job` | `[cron #N]` | Owner-defined daily/interval schedule | No |
| Payments reminder | `payments_reminder` | `[payments]` | Daily at a fixed time | No |
| Weekly backup | `weekly_backup` | `[backup]` | Weekly, fixed weekday | No |
| Traffic alerts | `traffic_poll_job` | `[traffic]` (via `log.warning` on failure) | Every 30 min (`TRAFFIC_POLL_MINUTES`), only when `WSDOT_API_KEY` set and location shared | No |

Authoritative full inventory with gates: companion-bot-architecture-contract §4.

**Not senders (common misattribution):** the life-sim (`[life]`, `update_life_event`)
and day-events (`[day-events]`, `[day-rotate]`) systems only generate background
context files (`day.txt`, life events). They never send messages — but they explain
"she mentioned something happening in her life I never heard about."

`send_triggered` / `send_proactive` (`[proactive]` tag on refusal-retry) are the
shared send paths most of the above funnel through.

## Traps — each one cost real debugging time here

### 1. The proactive-message misdiagnosis chain (canonical rabbit hole)
- **Trap:** Owner reported "heartbeat messages firing a minute after I send a
  message." The follow-up feature looked perfect: its 45–120 s delay window
  matches "a minute". Heartbeat was suspect #2.
- **Cost:** Two full hypothesis cycles spent on innocent systems.
- **Discriminators that worked:** (a) run `_FOLLOWUP_RE` against the actual
  triggering text — no match — AND `grep "\[followup\]" bot.log` empty, so
  follow-up ruled out; (b) `[heartbeat]` lines showed normal 2–6 h cadence with
  correct "Owner recently active; skipping" lines, so heartbeat ruled out.
  Real cause: an auto-extracted event reminder (`fire_reminder`,
  `kind == "event"`) — at the time the ONE proactive path with no owner-active
  check (guard added later in `6a8061f`; it still fires after 3 deferrals).
- **Lesson:** delay-window similarity is not evidence. Enumerate ALL proactive
  systems (table above) and discriminate by log tags.

### 2. nohup → setsid (launcher-dependent death)
- **Trap:** The watchdog `--loop` died when launched via
  `termux-boot-start.sh` but survived when launched directly. Every plausible
  in-script cause looked good on paper.
- **Cost:** Multiple bisection rounds on-device.
- **Discriminators:** wake-lock hang ruled out via `time termux-wake-lock`;
  script-not-completing ruled out via an `echo DONE` at the end; stale deployed
  script ruled out by grepping the deployed file for a new-version line; then
  direct-vs-wrapped launch bisection isolated the launcher itself. Root cause:
  `nohup` only blocks SIGHUP — it does not create a new session, and Android
  tore down the launcher's process group. Fix: `setsid` (see the long comment
  in `termux-boot-start.sh`). Verified live with `pgrep -af "watchdog.sh --loop"`.
- **Lesson:** "works when I run it by hand" points at the *launch context*
  (session, process group, environment), not the script body.

### 3. Stale deploys (the costliest failure class)
- **Trap:** The device silently ran old code while everyone debugged the new
  code. `set -e` in an early `update-all.sh` could abort after a failed pull,
  leaving stale files with no error the owner noticed.
- **Cost:** Entire debugging sessions invalidated.
- **Discriminator:** `cmp ~/stp-deploy/telegram-companion-bot/bot.py ~/telegram-bot/bot.py`
  (update-all.sh now does this automatically for bot.py — commit `7948ddf`), or
  grep the *deployed* file for a line unique to the new version. Note the deploy
  only auto-syncs `bot.py`, `bot_app/`, `acoustic_ears.py`, `run-bot.sh`,
  `watchdog.sh`, `status.sh`, `.env.example` — `update-all.sh` itself and
  `termux-boot-start.sh` must be copied by hand and go stale silently.
- **Rule:** ALWAYS rule out stale deploy before debugging logic.

### 4. Dollar-sign paste corruption
- **Trap:** Commands pasted through the owner's chat client get `$...$` spans
  stripped (rendered as math). A heredoc script arrived with `$HOME/$dir`
  mangled to ` dir`.
- **Cost:** Debugging a "bug" that was actually transport corruption.
- **Discriminator:** `cat -A` on the file that landed on-device.
- **Rule:** zero dollar signs in anything the owner will paste (see formatting
  rules above; full rules: companion-bot-device-ops).

### 5. /diag UnicodeEncodeError
- **Trap:** Surrogate-pair emoji in source strings crashed Telegram sends of
  `/diag` output.
- **Fix:** `_no_surrogates()` sanitizer (bot.py, applied on the send paths;
  commit `54c8d36`).
- **Lesson:** a Telegram send failure with `UnicodeEncodeError`/surrogates in
  the traceback is a payload-content bug, not an API problem — check what text
  was being sent, not the network.

### 6. Safety-classifier false positive on fragments
- **Trap:** A terse reply ("All of it.") judged in isolation read as crisis
  language and tripped the safety response.
- **Fix:** `_assess_safety` now passes the last 6 turns of conversation history
  and its prompt explicitly forbids judging short replies out of context
  (commit `18d4162`).
- **Lesson:** any cheap-classifier feature that sees text without context will
  misfire on fragments; the discriminator is reproducing the classifier call
  with and without the surrounding turns.

### 7. Garmin login rate-limiting
- **Trap:** Retrying Garmin login on every failure got the account rate-limited,
  turning one transient failure into a lockout.
- **Fix:** persisted login cooldown + `_garmin_obj = None` self-heal (commits
  `310d99f`, `2012fbc`). Tag: `[garmin]`.
- **Lesson:** never let a retry loop hammer an authenticated third-party login;
  when Garmin data goes missing, check for cooldown/rate-limit lines before
  touching credentials.

### 8. More precedent in git history
Before inventing a novel theory, grep history — many bug shapes recurred:
`git log --oneline | grep -iE "fix|bug"` in the repo. Known ones: duplicate
reminder IDs and the `EMBED_DIM` cache gap (`7c205bd`), lore embed HTTP 400
from over-long embedding inputs (`a53a28e`), event-loop-blocking sync calls and
un-timed-out ffmpeg (`2012fbc`), Cass roleplaying documents instead of analyzing
them (fixed by the `DOCUMENT_MODEL` split — documents go to a separate model),
and PDF OCR issues (fixes fully reconciled into HEAD — see
companion-bot-failure-archaeology §0; never cherry-pick from the dead branch
`fix-bot-py`).

## Log-tag reference

Full tag map + regeneration script: companion-bot-diagnostics
(`scripts/enumerate-log-tags.sh`). This table covers only the proactive senders the
symptom rows need.

Tags are bracketed prefixes on `print()` lines; `bot.py` runs under `python -u`
so they appear in `~/<char>-bot/bot.log` in real time. The high-signal ones:

| Tag | Subsystem |
|---|---|
| `[heartbeat]` | Proactive check-in scheduling/skips/sends |
| `[followup]` | brb auto-follow-up scheduling and errors |
| `[event-reminder]` | Event-reminder fire/defer/fail |
| `[event]` / `[upcoming]` | Event extraction and nudge scheduling |
| `[proactive]` | Shared proactive send path (refusal retries) |
| `[stress]` / `[bb]` / `[rhr]` | Garmin stress / body-battery / resting-HR monitors |
| `[garmin]` | Garmin login/fetch layer |
| `[onthisday]` | Daily reminiscing job |
| `[cron #N]` / `[cron]` | Owner-defined cron jobs / cron persistence |
| `[payments]` / `[backup]` | Payments reminder / weekly backup |
| `[memory]` / `[memories]` / `[episodes]` / `[lore]` / `[recall]` / `[rerank]` | Memory: summarization, fact extraction, episodic archive, lore embeds, semantic search |
| `[safety]` | Crisis classifier failures |
| `[selfie]` | Image generation failures/retries |
| `[voice-tone]` | Acoustic tone analysis (acoustic_ears) |
| `[model]` / `[models]` / `[setmodel]` | Model retries/fallbacks, model lists |
| `[reply]` / `[react]` / `[react-auto]` / `[sticker]` | Reply path, reactions, stickers |
| `[mood]` / `[scene]` / `[life]` / `[day-events]` / `[day-rotate]` / `[reading]` / `[wardrobe]` / `[milestones]` | Character-state background systems (context only, not senders) |
| `[draft]` | Unsent-thought drafts (saved when a proactive send was suppressed) |
| `[weather]` / `[traffic]` / `[search]` / `[link]` / `[net]` | External fetches |
| `[time]` / `[config]` / `[reminders]` / `[user-notes]` / `[photo-memory]` / `[error]` | Misc: timezone, bad env values, persistence loads, note/photo extraction |

Voice STT/TTS failures use `log.warning`, not tags: grep for
`"transcription failed"` and `"TTS failed"`. Supervisor restarts are
`[run-bot]` lines (written by `run-bot.sh`'s generated `.supervise.sh`).

## Provenance and maintenance

Everything above was verified against the repo at `telegram-companion-bot/` on
2026-07-02. Re-verify before trusting volatile facts:

- Log tags: `grep -oE 'print\((f?"?\[[a-z0-9_ -]+\])' telegram-companion-bot/bot.py | sed -E 's/print\(f?"?//' | sort | uniq -c | sort -rn`
- Bot instance list: `grep -A8 '^BOTS=' telegram-companion-bot/watchdog.sh` and the restart loop in `update-all.sh`
- Proactive job wiring: `grep -n 'run_daily\|run_repeating\|run_once' telegram-companion-bot/bot.py`
- Proactive send paths: `grep -n 'send_triggered\|send_proactive' telegram-companion-bot/bot.py`
- Heartbeat/nudge constants: `grep -n 'HEARTBEAT_MIN\|HEARTBEAT_MAX\|EVENT_NUDGE' telegram-companion-bot/bot.py`
- Voice provider (Inworld as of 2026-07): `grep -n 'INWORLD' telegram-companion-bot/bot.py`
- Watchdog stale threshold and .alive contract: `grep -n 'STALE\|\.alive' telegram-companion-bot/watchdog.sh telegram-companion-bot/bot.py`
- What update-all.sh actually syncs: read `telegram-companion-bot/update-all.sh` (short)
- Trap commit hashes: `git log --oneline | grep -iE 'nohup|stale|surrogate|safety|garmin|reminder'`
