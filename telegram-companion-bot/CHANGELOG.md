# Changelog — telegram-companion-bot

Read this before making changes; add an entry after shipping one. See `CLAUDE.md` for
why this file exists and the rule for keeping it updated.

Entries are newest first. Each one names the actual root cause, not just the code diff —
that's the part worth reading twice, since re-diagnosing a solved problem from scratch is
exactly what this file is meant to prevent.

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
