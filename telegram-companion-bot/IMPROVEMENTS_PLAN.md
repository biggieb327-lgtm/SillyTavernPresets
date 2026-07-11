# Improvements Implementation Plan — for the next implementing agent

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

| Release | Theme | Items |
|---|---|---|
| R1 | Memory auditor | source-attached memories, quote grounding, review queue, /editmem //sourcemem, memcheck flow, audit log |
| R2 | Availability | remote-default framing, /away //back, auto-extraction, new vibe presets |
| R3 | Observability & robustness | persisted error counts, config warnings surfaced, atomic small-file writes, graceful drain, usage counters in /audit, _last_request prune |
| R4 | Prompt hygiene & safety | token-budget trimming, lore dedupe, persona-break guardrail, summarization semaphore, /start full |
| R5 | UX | /status tail, recurring quiet windows |
| R6 | Evolution experiments (each behind its own env flag, ship one at a time) | reaction feedback, closeness score, open-threads list, joke candidates via review queue |

---

## R1 — Memory auditor ✅ Shipped v2026-07-11.1

Source-attached memories (`memory_meta.json`), quote grounding (`_quote_grounded`),
confidence + review queue (`/reviewmem`), correction flow (`[memcheck:]` tag),
`/editmem`, `/sourcemem`, memory audit log (`memory_log.txt`). 13 new tests (108
total). Full details: CHANGELOG v2026-07-11.1.

## R2 — Availability awareness ✅ Shipped v2026-07-11.2

Remote-default framing, `/away` + `/back`, auto-extraction via `post_reply_analysis`,
new vibe presets (`busy`, `working`, `driving`). Full details: CHANGELOG v2026-07-11.2.

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
