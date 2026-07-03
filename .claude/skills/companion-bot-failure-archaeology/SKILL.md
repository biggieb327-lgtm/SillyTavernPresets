---
name: companion-bot-failure-archaeology
description: >
  The failure chronicle for telegram-companion-bot: every significant investigation, dead end,
  rejected approach, revert, and hard-won settled decision, with commit-hash evidence. Load this
  FIRST when: a bug feels familiar or "we've seen this before"; you are about to propose an
  approach that may already have been tried and rejected (follow-up triggers, dual-character mode,
  nohup daemonizing, prompt examples with concrete names, splitting bot.py); you are touching a
  subsystem with history (proactive/heartbeat, memory extraction, selfie generation, deploy
  scripts, voice pipeline, card reading); the owner reports a symptom that matches an old one
  ("she texted me out of nowhere", "deploy didn't take", "bot died after reboot", garbage
  memories); or you want to know WHY something is built the way it is before "fixing" it.
  Do NOT use for: active live triage (companion-bot-debugging-playbook), investigation
  methodology (companion-bot-analysis-toolkit), architecture reference
  (companion-bot-architecture-contract), or deploy mechanics (companion-bot-device-ops).
---

# Companion-bot failure archaeology

Chronicle date: **2026-07-02**. Ground truth is `git log` on branch `claude/push-to-repo-7i2f3c`
(~210 commits, the live line of development) plus session logs from 2026-06/07 for incidents
that never produced a commit. Every hash below was verified with `git show` on this date.

Entry format: **Symptom → Root cause → Evidence → Status.**
Statuses: `fixed @hash`, `open`, `lost-on-dead-branch`, `settled-forever` (a decision or
environmental constraint — do not re-litigate without new evidence).

---

## 0. The dead branch: `fix-bot-py` (verdict: nothing of value lost)

Two disjoint histories exist in this repo. `fix-bot-py` (12 commits, root `d81304f`, tip
`fcd8c2c`; local `main` sits at `13c707c` on the same history) shares **no merge-base** with the
live branch — `git merge-base fix-bot-py claude/push-to-repo-7i2f3c` returns nothing. It carries
PDF-OCR fixes and three rounds of memories-system audit fixes (`eb1a5d9`, `604a5a9`, `fcd8c2c`)
that are NOT ancestors of HEAD. Investigated 2026-07-02, fix by fix:

- **PDF-OCR fixes** (`d81304f` pypdf fallback, `3747d09` duplicate-response guard, `13c707c`
  scanner-watermark skip): `git cherry` shows `3747d09`/`13c707c` are patch-equivalent to HEAD's
  `0db1f63`/`7fc7abb`. The pypdf fallback substance is in HEAD (`grep pypdf bot.py` hits;
  `_pdf_ocr_fallback` exists). **Present in HEAD.**
- **`eb1a5d9` "Fix 9 issues found in memories system code review"**: every fix is in HEAD's
  bot.py — `_memory_lock` (line ~356), `scan_words` set-intersection in `triggered_memories`
  (~2138), `_memories_cache["ts"] = 0.0` resets, `startswith("[sent ")` sentinel (~7362),
  hardened none-filter `re.match(r"^(none|no\b|nothing|n/a|not\b)", ...)` (~1127),
  `asyncio.to_thread(_work)` + `CancelledError` re-raise in `update_memories`. Ported into HEAD
  via `d0bc024` ("Apply 13 efficiency and performance fixes"). **Present in HEAD** — with ONE
  deliberate exception, next bullet.
- **The `break → continue` budget-loop fix from `eb1a5d9` was ported and then INTENTIONALLY
  REVERTED** in HEAD's `1a4d067`, item 3: "revert continue → break — the continue allowed
  lower-relevance memories to fill remaining budget slots after a high-relevance but oversized
  entry was skipped, violating the relevance-first guarantee of the descending sort." Both
  memory budget loops in HEAD (~821, ~2158) use `break` on purpose. **settled-forever** — do
  not "fix" `break` to `continue` in a memory token-budget loop again.
- **`604a5a9`** (drop fragile 40-char prefix dedup; char-name in stopwords; scan window
  `history[-8:]`): all three in HEAD (`_append_memory` has no prefix check, builds
  `stopwords = _MEMORY_STOPWORDS | {char_name}`; `history[-8:]` at ~3324). **Present in HEAD.**
- **`fcd8c2c`** (length-scaled dedup threshold; content-word extraction gate; `_read_user_notes`
  delegates to `_read_life_file`): all three in HEAD — `threshold = min(3, max(1, len(new_words)))`,
  the `_MEMORY_STOPWORDS` any-content-word gate at the top of `update_memories`, and the one-line
  `_read_user_notes`. **Present in HEAD** (via `d0bc024`/`1a4d067`).

**Verdict: `fix-bot-py` is safe to ignore. Zero lost fixes.** The audit rounds were re-applied
to the live branch the same day (2026-06-26) as `d0bc024` + `1a4d067`, and HEAD's memory code
has since evolved far beyond them (semantic dedup, embeddings, `_memory_word_cache`). Do not
cherry-pick from `fix-bot-py`; you would regress the intentional `continue → break` revert.

---

## 1. Proactive systems (heartbeat, follow-up, reminders, Garmin monitors)

### 1.1 The heartbeat misdiagnosis chain — the project's canonical debugging lesson
- **Symptom:** "Heartbeat messages firing a minute after I send a message" — an unprompted
  message arriving right after the owner's own message.
- **Investigation dead ends (in order):** (1) Follow-up feature suspected — its trigger regex
  was tested against the offending reply: no match; log grep confirmed it never fired.
  (2) Heartbeat suspected — logs showed it firing on its normal 2–6h cadence and correctly
  skipping near recent activity.
- **Real root cause:** event-reminder nudges (`fire_reminder`, kind == "event") had **no
  owner-is-currently-active check at all**, unlike every other proactive path (heartbeat,
  stress, Body Battery, RHR all check `last_seen`). An auto-extracted "Aeropress lesson"
  check-in fired mid-conversation.
- **Evidence:** `6a8061f` (2026-07-01) — the commit message narrates the full diagnosis chain.
  Session log 2026-07.
- **Status:** fixed @`6a8061f` (`EVENT_NUDGE_BUFFER_MIN` defer + `EVENT_NUDGE_MAX_DEFERS` cap;
  scoped to event-kind nudges only — explicit `/remindme` reminders still fire exactly on time).
- **Settled lesson (settled-forever):** there are FIVE independent proactive paths. Discriminate
  by **log tags** (`[heartbeat]`, `[followup]`, `[reminders]`, `[stress]`, `[rhr]`), never by
  "the timing looks like X". Delay similarity proves nothing.

### 1.2 Follow-up feature: too trigger-happy, disabled by default
- **Symptom:** unprompted message 1–2 minutes after ordinary replies.
- **Root cause:** trigger regex matched conversational phrases ("let me see/check/look").
- **Evidence:** `d11f230` (narrow regex to unambiguous away-signals), `5fa438e` (suppress during
  in-person vibe), `cce9552` (gate behind `FOLLOWUP_ENABLED=true`, **default off**).
- **Status:** settled-forever — follow-up is opt-in. Don't re-enable by default or re-broaden
  the regex; both were tried and rolled back within one day (2026-06-22).

### 1.3 Heartbeat repetition and restart drift
- Repetitive heartbeat openers → generator now tracks last 8 hooks per chat as an avoid-list:
  fixed @`b4cc083`. Heartbeat re-rolling a fresh 2–6h delay on every restart (watchdog/deploy
  restarts kept pushing check-ins out) → tick persisted to `.next_heartbeat` and resumed:
  fixed @`8d4cc0e`.

### 1.4 Proactive check-ins copying prompt text: "almost texted you"
- **Symptom:** check-ins repeatedly opened with "I almost texted you earlier."
- **Root cause:** the unsent-draft side-note handed the model that verbatim line; it copied it —
  same copy-the-example trap as the hallucinated-name bug (§2.2).
- **Status:** fixed @`27da521`. **Settled lesson:** never put a concrete, usable example
  sentence or name in a prompt that feeds generation — the model WILL emit it verbatim.

### 1.5 Provider moderation refusals delivered as her message
- **Symptom:** Bonnie's heartbeats delivering "The request was rejected because it was
  considered high risk" as chat text.
- **Root cause:** GLM's content filter returns refusals as ordinary completion text (not an
  HTTP error); unprompted reach-outs are most likely to trip it.
- **Evidence & arc:** `9efe664` (`_looks_like_refusal()` guard, skip tick / suppress reply),
  `fd96e7a` (TEMP diagnostic logging of caught refusals), `b19fbba` (close-out: drop temp
  logging, retry a refused proactive once — the filter is probabilistic — never inject a
  refused hook as her "thought").
- **Status:** fixed @`b19fbba`. The detector stays permanently.

### 1.6 Safety classifier false positive on terse replies
- **Symptom:** "All of it." (answering an earlier question) classified as crisis-level distress.
- **Root cause:** `_assess_safety()` judged the newest message in total isolation.
- **Status:** fixed @`18d4162` (2026-07-01) — classifier now receives the same last-6-turn
  history snippet `generate_inner_voice` builds. Session log 2026-07. **Settled:** any
  classifier judging a single message needs conversation context.

### 1.7 Garmin login hammering
- **Symptom:** repeated 429s from Garmin's mobile-login endpoint after restarts.
- **Root cause:** every restart without a cached token attempted a fresh login against a
  hard-rate-limited endpoint.
- **Status:** fixed @`310d99f` — persisted cooldown file (`.garmin_cooldown`, default 30m)
  survives restarts. Related self-heal gap fixed later in `2012fbc` E3 (§6.3).

---

## 2. Memory systems

(Layer inventory lives in companion-bot-architecture-contract. This is the scar tissue.)

### 2.1 The garbage-auto-memories saga (2026-06-28, four commits in sequence)
A multi-round fight; know all four rounds before touching `_extract_memory`:
1. **Raw narration/dialogue/meta-commentary in memories.txt** → rewritten prompt (ONE
   third-person factual sentence), hard post-filter (reject asterisks/quotes/meta phrases,
   8–220 char range), newline collapse so multi-line output can't split into fake entries.
   Fixed @`285d4ea`.
2. **Hallucinated people** — "Bob reacted badly when Brian mentioned their ex" was the
   extraction prompt's own example, copied out verbatim; "Bob" never existed. Fix: no concrete
   example names in the prompt + grounding filter (every proper noun must appear in the actual
   exchange). Fixed @`aa02f43`. Same trap class as §1.4.
3. **First-person fragments** rejected @`8515e9b`; **capitalized contractions** ("I'll",
   "Don't") counting as third-party names fixed @`844f9f9`.
4. **Attitude poisoning** — extractor wrote negative psychoanalysis of the user himself
   ("Brian deflects to regain control"), which, re-injected each turn, primed the character to
   treat the owner as an adversary. Fix: third-parties-only scope, interpretation-marker reject
   list, grounding REQUIRES a real third-party name. Fixed @`325d26b`. Extended to the
   always-injected summary/facts layer @`ed73690` (the `_MEMORY_REJECT` filter).
- **Settled-forever:** memory extraction stores concrete third-party facts only — never
  psychology, predictions, or feelings about the user/relationship. Any new extraction path
  must route through `_MEMORY_REJECT` and the proper-noun grounding check.

### 2.2 Lore embedding 400s
- **Symptom:** embedding calls returning 400 for some characters.
- **Root cause:** lore entries embedded untruncated; a long card entry exceeded the model's
  ~512-token limit (episodes/memories were already truncated; lore wasn't).
- **Status:** fixed @`a53a28e` — truncation moved INSIDE `_embed()` (`EMBED_MAX_CHARS`) so every
  present and future caller is protected at the source. **Settled:** never truncate at call
  sites; the choke point owns the cap.

### 2.3 `[auto DATE]` prefix leaking fake keywords
- Memory scoring counted "auto" and the date as keywords. Fixed @`7fb70e1` (strip the leading
  tag before word extraction; trailing `[aka: ...]` aliases deliberately kept so paraphrases
  match — that's the alias-expansion feature from `36554c8`).

### 2.4 memories.txt system: where it lives
- Introduced @`71adaa7` on the live branch (its `fix-bot-py` twins are `9ccc372`/`6285507`,
  see §0 and §3.1). Injection and RAG logic in bot.py (`MEMORIES_FILE`, `triggered_memories`,
  `_append_memory` — region starts around line 349).

### 2.5 Audit remediation, memory-adjacent (2026-06-30 batch)
- **EMBED_DIM cache gap:** vector caches invalidated only on `EMBED_MODEL` change, never on
  `EMBED_DIM`; `_cosine()` silently zip-truncated mismatched vectors into meaningless scores.
  Fixed @`7c205bd` F3 (`EMBED_CACHE_KEY` = model+dim; `_cosine` returns 0.0 on length mismatch).
- **JSON quarantine gap:** `handle_document`'s JSON branch persisted full file bodies (entire
  character cards) into trusted `conversation_history`, bypassing the untrusted-notes
  quarantine that already covered captions and PDFs. Fixed @`fc44dd2` A3.

---

## 3. Deploy & ops

### 3.1 The commit that pushed a shell string instead of Python
- **Symptom:** deployed bot.py was one line: `$(cat .../bot_content.txt)` — a shell command
  substitution that never expanded, committed as the entire file.
- **Evidence:** `git show 9ccc372:telegram-companion-bot/bot.py` (on `fix-bot-py`). Restored
  @`6285507` ("The previous commit accidentally pushed a shell command string instead of the
  actual Python source").
- **Status:** fixed; the pre-commit `py_compile` hook (@`eecdc54`) now makes this class
  impossible. **Settled:** never build file content through shell substitution into a commit.

### 3.2 Silent stale deploys — "it didn't get the code"
- **Symptom:** recurring reports that a deploy "didn't take"; old code kept running with no
  error shown.
- **Root cause:** `set -e` in update-all.sh aborted on a blocked `--ff-only` pull (stray local
  changes on the device), silently, before the copy step.
- **Status:** fixed @`7948ddf` — auto-stash before pull, loud failure with fix commands, `cmp`
  the copied bot.py against the clone, print a ✓ line with deployed line count. Earlier
  related fixes: `1531a02` (`|| true` on kill commands so `set -e` didn't abort restarts),
  `b5f2aea`, `5ac0fff` (pull from `~/stp-deploy` clone, not curl from main).
- **Settled:** a deploy that can fail silently WILL be reported as a bot bug. Verify-copy is
  load-bearing; don't remove it.

### 3.3 nohup → setsid: watchdog dying after boot
- **Symptom:** after `termux-boot-start.sh` ran, `pgrep -f "watchdog.sh --loop"` found nothing —
  the previously-shipped `--loop` fix (@`db14312`) did not survive on-device.
- **Investigation (live on-device bisection, each step confirmed before the next):** ruled out
  termux-wake-lock hanging; ruled out the script not completing (echo DONE); ruled out a stale
  deployed watchdog.sh missing `--loop` (grep of deployed file); then showed
  `bash watchdog.sh --loop &` run directly persists, but the same through nohup+disown dies.
- **Root cause:** `nohup` only blocks SIGHUP — it does not create a new session. Android/Termux
  process-group cleanup killed the backgrounded loop when the short-lived launcher exited;
  neither nohup nor disown protects against that.
- **Status:** fixed @`a080f99` (setsid, confirmed live). Session log 2026-06/07.
- **Settled-forever:** on this device, anything that must outlive its launcher gets `setsid`,
  never nohup/disown.

### 3.4 One-shot watchdog (the gap §3.3's fix was fixing)
- `termux-boot-start.sh` called watchdog.sh with no args → single `check_once()` at boot, then
  nothing; the only crash recovery was the in-tmux supervisor, which dies with the tmux session
  — exactly the scenario the watchdog exists for. `--loop` mode was fully implemented but never
  invoked. Fixed @`db14312` (then completed by `a080f99`). Broader uptime chain: `a2692bb`/
  `831ab5f` (supervisor; note the nested-quoting bug fixed by writing the supervisor to a
  file), `1bdf9d1` (watchdog + Termux:Boot), `8421813` (liveness heartbeat for frozen-but-alive
  processes), and PID locks against duplicate instances (@`5a3cd4c`).

### 3.5 $-paste corruption (environmental, no commit)
- **Symptom:** commands pasted to the owner arrived mangled on-device; `cat -A` showed
  `$HOME/$dir` arriving as ` dir`.
- **Root cause:** the owner's chat client strips `$...$` spans from pasted text (LaTeX
  rendering).
- **Status: settled-forever (permanent environmental constraint).** Every command destined for
  the device must contain **zero dollar signs** — use `~`, literal paths, or here-docs.
  Provenance: session log 2026-06/07. Full composition rules: companion-bot-device-ops.

### 3.6 wardrobe.json cannot ship via git
- `wardrobe.json` is gitignored per-instance state (`telegram-companion-bot/.gitignore:8`).
  It can never deploy via `update-all.sh`; when it must be delivered it goes as a heredoc the
  owner pastes (subject to §3.5's zero-dollar rule). Settled convention, session log 2026-06/07.

### 3.7 .env.example missing on device
- Setting up Priya failed because `~/telegram-bot/.env.example` didn't exist — update-all.sh
  synced only bot.py, bot_app/, and the run/watchdog/status scripts; nothing kept the template
  current on an established device. Fixed @`3fd9d9e` (added to sync). Session log 2026-07.
- Related phantom-config cleanup: `.env.example` documented env vars that **did not exist**
  (`HEARTBEAT_MIN/MAX`, `BOT_TIMEZONE`, `PROACTIVE_HOUR_START/END`, `NUDGE_MAX`,
  `CONTEXT_LIMIT`, `SUMMARY_EVERY`) — settings silently no-oped. Fixed @`e9e3880` Part B.
  **Settled:** verify an env-var name against code (or companion-bot-config-catalog) before
  telling the owner to set it.

### 3.8 Termux network flakiness
- Typing indicator dying mid-model-call and sends failing on brief Android network gaps →
  `_keep_typing` swallows transient exceptions; `send_bubbles` retries 3× with backoff on
  TimedOut/NetworkError. Fixed @`0e3717c`. Connection hardening: `af252e1` (split timeouts,
  retry backoff), `2cf12c9` (persistent Session), `fcc1887` (Termux wake lock). Header-injection
  crash from a whitespace-padded API key fixed @`7a69f7f`-equivalent (HEAD strips the key).

### 3.9 /diag crash on surrogate pairs
- `/diag` report generated fine; the SEND crashed with UnicodeEncodeError ('surrogates not
  allowed') — a header emoji stored as literal `🩺` escapes became lone surrogates at
  runtime. Fixed @`54c8d36` (`_no_surrogates()` first step in both send paths). **Settled:**
  never put `\uXXXX` surrogate-pair escapes in source strings.

### 3.10 Startup NameError from definition order
- `load_jokes()`/`load_wardrobe()` ran at import time before their `*_FILE` constants were
  defined → NameError on startup. Fixed @`2bc569e`. (The jokes subsystem itself was later
  removed entirely @`8985c41` — see §5.6.)

---

## 4. Media & voice

### 4.1 Voice-provider churn, 2026-07-01 (know this before touching voice)
- STT: NanoGPT Whisper → **Inworld STT** @`ed15b25` (also returns a voiceProfile — emotion,
  vocal style, pitch, age, accent — which local analysis cannot derive).
- TTS: NanoGPT → **Inworld TTS** @`faea119` (requests OGG_OPUS directly, no ffmpeg step;
  `TTS_MODEL` deleted as dead config).
- Acoustic tone analysis vendored from menelly/AI_Ears (MIT) as `acoustic_ears.py` @`bae2dcb`
  — pure local FFT, runs alongside STT.
- **The trap (settled-forever):** OpenAI-style voice names (nova/shimmer/alloy) were briefly
  configured per-bot and then invalidated by the Inworld switch. `TTS_VOICE` must be an
  **Inworld voiceId** — custom voices are generated IDs like
  `amber-swan-3291__design-voice-5e83bdda`. A leftover OpenAI name in a `.env` fails exactly
  like a bad API key. Check this FIRST on any "voice replies stopped working" report.
- `handle_video`'s audio transcription is still NanoGPT (deliberately untouched in `ed15b25`).

### 4.2 Selfie generation: the long war
- `selfie_ready()` always True: `(BASE_DIR / SELFIE_BASE).exists()` with empty `SELFIE_BASE`
  resolves to BASE_DIR itself, a directory that always exists. Plus silent failures. Fixed
  @`732c623` (and crash-when-no-base-image @`f264391`; wrong constant `CHARACTER_NAME` vs
  `NAME` @`ebad370`; auto-discovery of base image @`4f68a80`).
- Anatomy artifacts (extra/detached limbs, "hand out of her chest"): natural-language anatomy
  clause added @`3e7b161` (commit is explicit: **reduces frequency, cannot eliminate** —
  generation is stochastic; the img2img base photo is the stronger anchor), and framings
  rebalanced away from reaching-arm poses @`7578e7c` (those poses are where models grow third
  limbs). Earlier round: `e8f05e1`. Don't promise elimination; don't re-add reaching-arm
  framings.
- Location bleed: Nora's Chicago backstory leaking into current-scene selfies → scene inference
  grounded to `WEATHER_LOCATION` @`b4cc083`; scene-continuity tracking added @`6ef1ffd`.
- Gemini safety-filter blackouts → per-character `appearance.txt` @`d846384`; underwear-adjacent
  phrases stripped from Gemini prompts @`5f3ea5a`.
- Nora tattoo flip-flop: ink added @`909d04f`/`c73b2d9`, **reverted** @`faa9bde` because the
  chosen base photo is ink-free — text and base image must describe the same body for stable
  img2img. Settled: appearance text follows the base image, not the other way around.

### 4.3 PDF/OCR
- Fallback blocked by missing pypdf (fixed, present in HEAD; dead-branch twin `d81304f`);
  duplicate responses when the user resends during slow OCR (fixed @`0db1f63`); scanner
  watermark as the only OCR output should not get a character response (fixed @`7fc7abb`).

---

## 5. Prompt & cards

### 5.1 Cass roleplaying the cards she was asked to analyze
- **Symptom:** sending Cass (writing-collaborator character) a character-card JSON made her
  BECOME that character instead of critiquing it.
- **Root cause:** card fields (`system_prompt`, `first_mes`, `mes_example`,
  `post_history_instructions`) are imperative text; roleplay models execute them as live
  instructions when they appear in context.
- **Evidence & arc:** `1cc41ab` (block-quote the performative fields, in-card "do not perform"
  header), `89804c4` (**strip `system_prompt` from card output entirely** — the commit subject
  is the lesson), `b34974f`, `4a3d993` (drop first_mes/mes_example).
- **Status:** fixed. **Settled-forever:** any card content shown to a live character must be
  quoted/stripped, never inlined raw. This is also why `fc44dd2` A3 quarantines JSON bodies
  (§2.5).

### 5.2 preset.txt is verbatim-injected — no comments possible
- **Settled-forever:** preset.txt's entire content is injected as live prompt text; no comment
  syntax survives. Do not add maintainer notes inside it. Documented in bot.py itself
  (~lines 218–228, `TEXTING_STYLE`). The file also carries the banned-phrases/anti-slop list
  built up across `f59cd7e`, `9e714cb`, `92ca53d`, `4e916e9`, `32b3b6b`, `78082b7`, `7d96542`,
  hardened from advisory to hard constraint @`102967b` — additions are fine, meta-commentary
  is not.

### 5.3 Wrong day/time drift
- **Root cause:** `environment_note()` dumped ALL six time-of-day personality periods into every
  turn next to the actual clock — the model picked the wrong one.
- **Status:** fixed @`3967811` — inject only the line matching the current hour; live date/time
  moved to the LAST system message so the real clock is most salient. **Settled:** salience is
  positional; the freshest ground truth goes last.

### 5.4 crash when character_book is null
- Cards with `"character_book": null` crashed card loading. Fixed @`3c82625`. Also
  `1506f9b` (bonnie.json had a literal newline in system_prompt — invalid JSON). **Settled:**
  card JSON from the wild needs null/format tolerance; validate after hand-edits.

### 5.5 Dual-character mode: built, shipped, removed
- Two personas in one bot instance (`dfca0d0` + four fix-up commits fighting repetition and
  suppression) was fully **reverted** @`93ff37b` — bot.py reset to pre-dual-mode state
  (`b4edc17`), Marcus Calder card deleted. One process = one character is the settled model
  (see architecture contract). Don't propose multi-persona per instance without acknowledging
  this history.

### 5.6 Inside-jokes and self-image reflection: removed subsystems
- Both fully deleted @`8985c41` (prompt blocks already cut @`4a64b9a` for per-turn prompt
  bloat). Milestones survived, slimmed into `nightly_maintenance`. If you see references to
  `/reflect`, `/selfimage`, jokes.json, `BELIEF_TRAITS` in docs or old notes: dead on purpose.

### 5.7 Emoji-only replies, reaction-only Bonnie, "chirp" meta-language
- Each a character-output pathology with a prompt-level fix: `388be69` (emoji-only replies +
  search double-message), `69d5b3b` (Bonnie reaction-only replies need a positive writing
  requirement, not just bans), `3496c39` (suppress "chirp" meta-language in Jules narration).
  Pattern: banning a behavior often isn't enough; require the replacement behavior.

---

## 6. Security & reliability (the 2026-06-30 audit remediation batch)

One coordinated audit produced five commits. Each finding, separately:

### 6.1 fc44dd2 — Security
- **~60 of 82 command handlers unguarded:** `ALLOWED_USERS` did not actually restrict most of
  the bot. Now `_guard()` on every handler, with exactly two documented exceptions: `/chatid`
  stays open (new users need it to discover their ID) and `/start`'s greeting stays open but
  its `set_owner()` side effect is gated (an unauthorized caller can no longer hijack a fresh
  bot). Settled: new handlers MUST call `_guard()`; a guard-coverage script verified the batch.
- **SSRF in link fetching:** any pasted URL was fetched, redirects followed blindly (cloud
  metadata reachable; DNS-rebinding via redirect). Now `_url_host_is_safe()` (stdlib
  `ipaddress`) rejects loopback/link-local/private/reserved/multicast, and `_fetch_generic`
  follows redirects manually, re-validating each hop.
- **JSON quarantine gap:** see §2.5.

### 6.2 e9e3880 — Cleanup
- Phantom env vars (§3.7); unreachable dead block stranded after a return in
  `_weather_camera_pool`; `start-bots.sh` deleted (superseded by run-bot.sh supervision) and
  every doc reference fixed; stale docs regenerated against actual `CommandHandler`
  registrations.

### 6.3 db14312 / 2012fbc / 7c205bd — Watchdog, reliability, correctness
- Watchdog one-shot → continuous `--loop` (§3.4; completed by §3.3).
- **Event-loop blocking:** `recap_cmd` and `check_usage` called the LLM directly on the event
  loop — a slow response froze the WHOLE process (all chats, all jobs) up to 300s × retries.
  Now `asyncio.to_thread`, like every other call site. Settled: no synchronous network I/O on
  the loop, ever.
- **ffmpeg no-timeout:** a malformed video could hang ffmpeg forever, zombie included. Now
  `FFMPEG_TIMEOUT` + kill + reap (the config value existed in bot_app but bot.py never read
  it — phantom-config again).
- **Garmin no-self-heal:** three poll functions caught exceptions but never cleared the cached
  `_garmin_obj`, so a mid-runtime session break failed silently forever. All now clear it.
- **Duplicate reminder IDs:** `_schedule_event`'s before/after pair both got max-id+1 before
  either was appended → `/delreminder` couldn't target the second. Local `next_id()` accounts
  for queued-this-call entries.
- **Migration-backup overwrite:** `migrate_common_env.py` re-runs replaced the true
  pre-migration `.bak` with migrated output, defeating its own "safe to re-run" claim. Now
  write-once.
- **EMBED_DIM cache gap:** §2.5.

---

## 7. Architecture decisions with rationale (bot_app migration)

From `telegram-companion-bot/bot_app/MIGRATION.md` (status updated @`aea2811`) — these are
DECISIONS, not TODOs:

- **Steps 0/2/3/4/5 done** (deploy plumbing, guards, untrusted-notes quarantine, action
  allowlist, ingestion isolation) — the security-relevant strangler-fig steps.
- **Step 1 (config → Settings): deliberately SKIPPED** — moving ~80 `os.getenv` constants is
  lateral churn; migrate opportunistically only as a subsystem moves.
- **Step 7 (command bodies → bot_app/handlers): deliberately DEFERRED** — 60+ working command
  bodies, high churn / zero security or correctness value.
- **Step 6 (`assemble_messages`): intentionally LAST, gated on parity tests** — the riskiest,
  most-tuned code in the bot; do not move without capture-and-diff parity against the current
  builder.
- **settled-forever:** `bot.py` stays the process entry point; do not switch to `main.py` or
  rewrite `main()`/handler registration (all scheduling lives there). Proposing "let's split
  bot.py properly" re-fights this settled battle — read MIGRATION.md's "What NOT to do" first.

---

## Provenance and maintenance

- Everything above was verified 2026-07-02 against branch `claude/push-to-repo-7i2f3c`
  (tip at that date: `faea119`), the dead branch `fix-bot-py` (tip `fcd8c2c`), and session
  logs from 2026-06/07 for the seven no-commit incidents (§1.1's diagnosis chain narrative,
  §3.3's bisection narrative, §3.5, §3.6, and the voice-name trap in §4.1).
- **To find what postdates this chronicle:** `git log --oneline --since=2026-07-02` — anything
  it lists is not covered here. If a listed commit reverts or supersedes an entry above, update
  the entry's Status rather than appending a duplicate.
- To re-verify any entry: `git show <hash>` — this project's commit messages carry full
  symptom/root-cause/verification narratives and are the primary source.
- When you close a NEW significant investigation (a dead end ruled out, an approach rejected,
  a revert with rationale), append it here in the same Symptom → Root cause → Evidence → Status
  format, under the right subsystem, and date-stamp your addition.
