# Improvements Implementation Plan — for the next implementing agent

> **Status (2026-07-17): fully executed.** All six releases shipped 2026-07-11 as
> v2026-07-11.1–.6 (one release per phase, per ground rule 4) — see CHANGELOG.md for
> what each actually did and ROADMAP.md Track 4 for the closed backlog items. This
> document is retained as the handoff spec of record; do not re-implement from it.

Written 2026-07-10 against bot.py v2026-07-10.2 (~8,450 lines). This turns the
triaged improvement suggestions from the 2026-07-10 audit (see `AUDIT-2026-07-10.md`)
into an executable, release-by-release plan. It is self-contained: read this + the
files it names and you have everything needed.

## Ground rules (non-negotiable, enforced by hooks/evals)

1. **Read `CHANGELOG.md` before touching bot.py** — root causes of every past bug.
   Also read `AUDIT-2026-07-10.md` and, for anything group-related,
   `GROUP_CHAT_DESIGN.md` (that design survived four adversarial review rounds; its
   boundaries are pinned by CI evals `group-deliver-clean` and `group-cmd-allowlist`).
2. **bot.py stays a single file.** The deploy model (`/update` swaps one shared file,
   curl from `main`, `bot.py.bak` rollback) depends on it. Recorded non-goal.
3. **Every bot.py release:** bump `BOT_VERSION` (line ~71) + changelog entry (root
   cause/rationale style) — the delivery-gate hook blocks otherwise. Run
   `.claude/evals/run-evals.sh` AND `python -m pytest telegram-companion-bot/tests/`
   before claiming done. Merge to `main` (deploys pull from main).
4. **One release per phase below.** Small diffs deploy safely over `/update`; a
   mega-release risks the whole 6-bot fleet at once.
5. **Phone constraints:** NO new per-message LLM calls — side calls compete with
   user-facing replies for bandwidth (this is why `post_reply_analysis` is ONE
   combined call; extend its JSON, never add a sibling call). No new processes
   (phantom-process killer). `/tmp` is not writable on Termux.
6. **Concurrency rules (from v2026-07-10.2 fixes):** state serialization happens on
   the event loop only; never iterate the live state dicts from a worker thread;
   never run bare `requests` calls in an async handler (use `asyncio.to_thread`);
   never hold the group-ledger flock across an `await`.
7. **Memory provenance rule (from the hallucination bug):** generated content must
   NEVER enter user-fact stores unlabeled. Anything the character invents (day
   events, reflections) is either excluded from memory or carries a marker every
   consumer honors (see `_OWN_DAY_PREFIX` and its handling — that pattern is the
   template).
8. **Commit real work before break-testing evals**; revert test injections by
   re-editing, never `git checkout` on a file with uncommitted changes (this exact
   mistake destroyed 700 lines once — operational-log 2026-07-10).
9. Tests: every new pure function gets pytest coverage in `tests/test_pure.py`
   (fixture in `conftest.py` stands up a fake instance so `import bot` works).

## Release sequencing

| Release | Theme | Items | Status |
|---|---|---|---|
| R1 | Memory auditor | source-attached memories, quote grounding, review queue, /editmem //sourcemem, memcheck flow, audit log | ✅ v2026-07-11.1 |
| R2 | Availability | remote-default framing, /away //back, auto-extraction, new vibe presets | ✅ v2026-07-11.2 |
| R3 | Observability & robustness | persisted error counts, config warnings surfaced, atomic small-file writes, graceful drain, usage counters in /audit, _last_request prune | ✅ v2026-07-11.3 |
| R4 | Prompt hygiene & safety | token-budget trimming, lore dedupe, persona-break guardrail, summarization semaphore, /start full | ✅ v2026-07-11.4 |
| R5 | UX | /status tail, recurring quiet windows | ✅ v2026-07-11.5 |
| R6 | Evolution experiments (each behind its own env flag, ship one at a time) | reaction feedback, closeness score, open-threads list, joke candidates via review queue | ✅ v2026-07-11.6 |

---

## R1 — Memory auditor (the big one; theme behind the hallucination bug)

Goal: every memory is traceable to its source, correctable from Telegram in under a
minute, and low-confidence extractions never silently enter memory.

Current mechanics you must understand first:
- NPC/world memories = lines in `memories.txt`, written by `_append_memory(text,
  auto=)` (called from `_post_reply_analysis` and `/addmem`), read by
  `triggered_memories()` (keyword + semantic merge), embedded per line into
  `embeddings.json` **keyed by the exact line text** (see `_embed_memory_line`).
- `/mems` lists numbered; `/delmem <keyword or #>` removes (and must stay in sync
  with embeddings).

### 1a. Source-attached memories
- New sidecar `memory_meta.json` (BASE_DIR), same keyed-by-line-text pattern as
  `embeddings.json`: `{line_text: {"ts": float, "chat_id": int, "origin":
  "auto"|"manual", "confidence": int|null, "source": "<verbatim snippet>"}}`.
- `_append_memory` gains optional `meta: dict = None`; `_post_reply_analysis` passes
  the `hist_tail` lines it extracted from (the snapshot it already receives — do NOT
  re-read live history in the worker, see ground rule 6). `/addmem` passes
  `origin: "manual"`.
- Delete/edit paths must keep all three files in sync (memories.txt, embeddings.json,
  memory_meta.json). Factor one helper `_memory_replace(old_line, new_line|None,
  meta=None)` used by delete, edit, and append — one choke point, no drift.
- Orphaned meta entries (memories edited before this feature) are fine: meta lookup
  is always `.get()` with a "no source recorded (pre-2026-07)" fallback.

### 1b. Quote grounding (anti-hallucination, mechanical not prompt-hope)
- `_post_reply_analysis`'s JSON gains `"memory_quote"`: the exact sentence from the
  exchange that supports the memory. Validation in code, not trust: normalize
  whitespace/case and require `memory_quote` to be a substring of the `hist_tail`
  text **from user lines only**. Fails → memory is NOT stored, counted as
  `_count_error("memory_ungrounded")`.
- Pure function `_quote_grounded(quote: str, user_lines: list[str]) -> bool` +
  tests (exact match, case/whitespace tolerance, quote from assistant line → False,
  fabricated quote → False).

### 1c. Confidence + review queue
- JSON also gains `"memory_confidence"`: 1–10. `>= MEMORY_AUTOCONF` (env, default 7)
  AND grounded → stored directly. Grounded but lower → appended to
  `memory_review.json` instead (same meta shape + the proposed line).
- `/reviewmem` lists pending numbered with confidence + source; `/reviewmem ok <n>`
  promotes (through `_memory_replace`), `/reviewmem no <n>` drops. Queue capped at 20
  (oldest dropped, logged).
- Wire into `/audit`: one line `memory: N pending review` when nonzero.

### 1d. Correction flow (human stays in the loop — no autonomous deletion)
- New taught tag `[memcheck: <short query>]` added to the capabilities block in
  `assemble_messages` (~line 2560s), taught ONLY as: "if {uname} disputes something
  you remembered ('that never happened', 'I never said that'), include
  [memcheck: what's disputed]".
- Tag handling follows the existing `extract_tags` 4-tuple pattern — **note the
  contract**: `extract_tags` returns a tuple consumed at multiple call sites
  (`_deliver`, `send_triggered`, `_group_deliver`); extend it carefully and update
  every consumer, or better: handle `[memcheck:]` with its own regex pass in
  `_deliver` only (groups don't do memory anyway), leaving the 4-tuple contract
  untouched. Prefer the latter — the 4-tuple is pinned by tests.
- On the tag: run the existing recall machinery (`triggered_memories` + semantic
  recall, same as `/recall`) over the query; DM the numbered hits with their sources
  and the exact commands to fix (`/delmem N`, `/editmem N <text>`). She says her
  line; the plumbing message follows as a separate system-style message.
- Every memcheck + resolution appended to the audit log (1f).

### 1e. /editmem and /sourcemem
- `/editmem <n> <new text>` — replace line n (numbering identical to `/mems`),
  through `_memory_replace` (re-embeds, moves meta with `origin: "manual-edit"`,
  keeps original source).
- `/sourcemem <n>` — show the stored source snippet + ts + origin + confidence.
- Both refuse in group chats automatically (the group command guard is default-deny
  — do NOT add them to `GROUP_ALLOWED_COMMANDS`; the eval pins it).

### 1f. Memory audit log
- `memory_log.txt` (BASE_DIR), append-only lines:
  `2026-07-10T18:02 ADD auto conf=8 "text…" src="quote…"` / `EDIT` / `DEL` /
  `REVIEW-OK` / `REVIEW-NO` / `MEMCHECK "query" -> 2 hits`.
  Written from `_memory_replace` and the review/memcheck paths. Trim to last 500
  lines when >1000 (same pattern as the group ledger rotation).

R1 acceptance: (1) new auto-memory has source + confidence visible via `/sourcemem`;
(2) an ungrounded extraction is rejected (check `/errors` category); (3) low-conf
lands in `/reviewmem`, promotable; (4) "I never said that" produces a memcheck reply
naming the offending memory and the exact fix command; (5) `/editmem` survives a
restart and `/recall` finds the edited text (embedding refreshed); (6) memory_log
shows the whole story; (7) pytest + evals green.

## R2 — Availability awareness

- **Remote-default framing:** in `assemble_messages`, one system line when
  `active_vibe(chat_id) != "in-person"`: "You and {uname} are texting from different
  places — you're not physically together unless the scene explicitly says so."
  Kills the "walks over to you" class of slip. (Check `VIBE_PROMPTS` for the
  existing in-person vibe name before hardcoding.)
- **/away and /back:** new state dict `away = {}  # chat_id -> {"reason": str,
  "since": ts}` (+ serialize/load — follow the existing pattern in
  `_serialize_state`/`load_state`; remember it runs on the loop). `/away driving`,
  `/away meeting until 3` (free text, stored verbatim). Effects: heartbeat +
  note-followups + traffic alerts skip while away (gate beside the existing
  quiet_until checks in `heartbeat`, ~line 7100s); prompt gets "{uname} said they're
  away: {reason} — don't expect quick replies, don't pile up messages."
- **Auto-clear:** any text message from the user clears away (they're back by
  definition) — in `handle_message` after the group branch; she may acknowledge
  naturally (prompt note "they just got back from: {reason}" for that one turn).
- **Auto-extraction:** `post_reply_analysis` JSON gains `"availability"`:
  `"driving"|"working"|"busy"|null`, ONLY when explicitly stated. Sets away with
  `origin: auto` — auto-away expires after `AWAY_AUTO_HOURS` (default 3) as a
  belt-and-suspenders against a stuck flag.
- **Vibe presets:** add `busy`, `working`, `driving` to `VIBE_PROMPTS` (short,
  register-preserving: fewer/shorter replies, no long questions).

Acceptance: `/away driving` → heartbeat window passes silently; first message back
clears it; "gotta drive, ttyl" sets auto-away without any command; `/status` shows
away state.

## R3 — Observability & robustness

- **Persist `_error_counts`:** add to `_serialize_state` and `load_state`
  (`{cat: [ts,…]}`, already capped at 200/cat). `/audit`'s error history then
  survives restarts — restart-storm triage currently loses its own evidence.
- **Config warnings surfaced:** `_env_int`/`_env_float`/`_parse_id_set` currently
  warn to log only. Collect into module list `_CONFIG_WARNINGS` (append the
  formatted message); show count + first 3 in `/audit`; log all at startup after
  load. (This is the useful core of the suggested `validate_config()` — a separate
  validation pass would re-state 64 defaults for no gain. The suggested Config
  dataclass is rejected: pure churn on a working pattern, high line-count risk.)
- **Atomic small-file writes:** `_atomic_write_text(path, text)` helper (tmp +
  `os.replace`, same as state.json) used by `save_jokes`, `save_reminders`,
  `save_cron_jobs`, `save_payments`, wardrobe save — today a death mid-write
  truncates the file. Grep for `write_text(json.dumps` to find them all.
- **Graceful drain on /restart and /update:** before the exit path fires, wait up to
  5s for `_replies_in_flight == 0` (module counter already exists, line ~2500):
  `for _ in range(10): if not _replies_in_flight: break; await asyncio.sleep(0.5)`.
  Do NOT touch the signal handling itself — PTB's `run_polling` owns signals and
  `post_shutdown` is the only reliable hook (see CHANGELOG v2026-07-05.8).
- **Usage counters in /audit:** module dict `_llm_stats = {"date": str, "calls": int,
  "tok_in": int, "tok_out": int}` bumped in `call_nanogpt` via the existing
  `_est_tokens` (estimates are fine, label them "est."); reset when date changes;
  persist in state. `/audit` line: `LLM today: 41 calls, ~52k in / ~9k out (est)`.
- **Prune `_last_request`:** in `_self_audit` (runs every 30 min), drop entries older
  than 1h. One line.
- **Rejected, keep it that way:** `/rollback` command (bot.py.bak + shell already
  covers it; a broken bot.py can't be trusted to run its own rollback); exposing
  Telegram HTTP pool sizes (no evidence of pool starvation; revisit only with a
  symptom); blanket to_thread for file reads (all hot files are tiny and cached —
  measured non-problem).

## R4 — Prompt hygiene & safety

- **Token-budget trimming:** pure `_trim_history_to_budget(messages, budget)` —
  estimates with `_est_tokens`, drops oldest HISTORY messages only (system blocks and
  the final user turn are untouchable) until under `CONTEXT_TOKEN_BUDGET` (env,
  default 24000; 0 = disabled). Call at the end of `assemble_messages`. Log when it
  trims (`[prompt] trimmed N msgs, ~Xk tokens`). Tests: no-op under budget; drops
  oldest first; never drops system/final-user.
- **Lore dedupe:** `triggered_lore` returns duplicates when multiple keys of the same
  entry hit — add a `seen` set on entry content. Two lines + test.
- **Persona-break guardrail:** regex for the obvious breaks
  (`as an AI( language model)?`, `I'?m an AI\b`, `large language model`,
  `I don'?t have (feelings|a body|personal experiences)`) applied in `_deliver` and
  `send_triggered` on the final `clean` text: strip the offending sentence, count
  `_count_error("persona_break")` (visible in `/audit`). If the strip leaves the
  reply empty, fall back to sending nothing rather than a stump. No auto-regenerate
  in v1 (extra model call — ground rule 5). Tests with sample sentences, including
  false-positive guards ("my AI coworker shipped a bug" must survive — require the
  first-person pattern).
- **Summarization semaphore:** module `_SUMMARIZE_SEM = asyncio.Semaphore(1)` wrapped
  around the `to_thread(_summarize/_consolidate/_promote…)` calls in
  `maintain_memory`/`maintain_long_term_memory` — prevents multi-chat summarization
  bursts from stacking on phone bandwidth. (Per-chat overlap is already prevented by
  the `summarizing` set; this serializes across chats.)
- **/start full:** `/start full` additionally wipes summaries/facts/recent_*/
  milestones/pinned/moods/beliefs for that chat after an inline-button confirmation
  (reuse the existing `button_callback` machinery; look at how `/forget` confirms).
  Flat files (memories.txt etc.) untouched — those are the character's, not the
  chat's.

## R5 — UX

- **/status tail:** append the last 3 conversation messages (truncated to ~80 chars
  each, speaker-labeled) to `/status` output.
- **Recurring quiet windows:** `/quietwin add Fri 23:00-08:00`, `/quietwin list`,
  `/quietwin del <n>`; stored in state (`quiet_windows`: list of {dow, start, end});
  checked in the same proactive gate as `quiet_until` (find `_quiet_now` or
  equivalent — grep `quiet_until` consumers). Windows crossing midnight must work
  (23:00-08:00 = Fri night into Sat morning). Pure predicate
  `_in_quiet_window(now, windows)` + tests (midnight crossing, wrong day, boundary
  minutes). This subsumes the suggested "cron-style" syntax with something a human
  can type on a phone.
- **Already exists, don't rebuild:** quick-reply inline buttons = `/menu`
  (`button_callback`); check it before adding anything.

## R6 — Evolution experiments (product, not debt — each gated, shipped alone)

Order by value/risk. Every one behind its own env flag, default off, piloted on ONE
instance before fleet enablement. None may add a per-message LLM call.

- **Reaction feedback (`FEEDBACK_REACTIONS=1`):** register PTB
  `MessageReactionHandler` (requires adding `"message_reaction"` to
  `allowed_updates` in `run_polling` — verify against the pinned PTB version
  >=21,<22 before assuming API shape). 👍/👎 on her messages → append to a bounded
  per-chat feedback list in state + small mood nudge; 👎 also injects a one-turn
  prompt note ("that last message didn't land — recalibrate, don't apologize").
  The group guard stops reaction updates in groups already (TypeHandler group -1
  stops every non-text update) — verify with a test group before shipping.
- **Closeness score (`CLOSENESS_ENABLED=1`):** derived, not LLM-judged: function of
  days-active, message count, milestones count, vulnerability markers already
  tracked in beliefs/milestones. Map to 3 buckets rendered as one system line
  ("you're still getting to know each other" / "comfortable" / "deeply familiar").
  Recompute daily at rotation, store in state, show in `/status`. Keep the formula
  a pure function + tests.
- **Open threads (`THREADS_ENABLED=1`):** `next_goals[chat_id]` str → list capped at
  3 (migrate: wrap existing str into [str] in load_state). post_reply_analysis JSON
  gains `"thread_update"`: {"add": str|null, "resolved": str|null}. Prompt block
  "Open threads between you two" replaces the single next-goal line.
- **Auto inside-joke candidates (`JOKE_CANDIDATES=1`):** post_reply_analysis JSON
  gains `"joke_candidate"` ({phrase, meaning, tone} | null, strict criteria: both
  laughed / callback potential). Candidates go to the R1 review queue (never
  auto-added — jokes.json is global and surfaces in every chat, see CHANGELOG
  v2026-07-10.1's leak discussion).
- **Rejected:** live self-image updates after every exchange (nightly reflection is
  the deliberate design; per-exchange updates = more calls + thrash), daily "what I
  learned" memory writes (provenance risk — it's generated content summarizing
  generated impressions; the recent_facts pipeline already covers real learnings),
  inner-voice feeling tracker (INNER_VOICE is off by default for latency; don't
  build on an off-by-default foundation).

---

## Standing verification block (every release)

```
python3 -m py_compile telegram-companion-bot/bot.py
python -m pytest telegram-companion-bot/tests/ -q
bash .claude/evals/run-evals.sh
```
All green → merge to main → user deploys via /update (one bot) + /restart (rest) →
verify with /audit (BOT_VERSION must show the new release). If a release's feature
misbehaves on-device, its env flag (R2/R6) or config default (R4 budget=0) is the
kill switch — design every feature so unset = today's behavior.

Version numbering: continue the `YYYY-MM-DD.N` scheme; the changelog heading must
match BOT_VERSION exactly (`version-changelog-sync` eval enforces).
