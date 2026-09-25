# Message log — design sketch

Status: **built in v2026-09-25.1** (message log + `/msglog` in bot.py; weekly audit in
`tools/weekly_audit.py`). Owner asked for a way to send the bots' messages somewhere they
can be analyzed and audited, with a slash command to toggle it and 30-day retention, then
for a weekly job that runs rpzlib.py on the bots that have it on and says what could be
improved. Owner is comfortable with the data at rest as long as it stays on the VPS.

## What exists today (read from source, not observed on the VPS)

- `remember()` (bot.py ~9662) appends every turn to `conversation_history` and calls
  `save_state()`. `_serialize_state()` writes that dict into `state.json` (~4517).
- That window is **not an audit trail**: `maintain_memory` summarizes it away and
  `remember()` hard-caps it at `MAX_HISTORY * 4` entries.
- `deploy/vps-backup.sh` copies every top-level instance file except `.env*`, `*.pyc`,
  `*.log` (`find -maxdepth 1`). So `state.json` — and the rolling conversation window
  in it — **already leaves the VPS** nightly when `BACKUP_RCLONE_REMOTE` is set
  (encrypted Google Drive copy per the 2026-09-23 debrief-log row). Pre-existing, not
  something this design changes, but worth knowing given "as long as it's on the VPS".
- Logging otherwise: INFO to journald, errors to a rotating `errors.log`. Neither
  records conversation text as a deliberate record.

## Hook point: `remember()`

Every path that puts text in front of the user or into history calls `remember()`:

| path | caller | notes |
|---|---|---|
| private reply (text, photo, voice, video) | `_deliver` | assistant text is post-`_strip_slop` / `_strip_persona_breaks` — what the user saw |
| group reply | `_group_deliver` | chat_id < 0 |
| proactive / scheduled send | `send_triggered` | followups, briefings, vigil, note follow-ups; logs a synthetic user line first |
| user-only lines | handle_message branches (~13964–14046) | messages remembered without a reply |

Grep found no other writer to `conversation_history` (only `remember()` appends).
**Known gap:** `fire_reminder` (~12987) sends literal reminder text with
`context.bot.send_message` and never calls `remember()`, so reminders would not be
logged. It already emits a proactive receipt (below), and a reminder is the user's own
text echoed back, so v1 leaves it out.

**Alternative considered — reuse the proactive-receipt pipe.** `_emit_proactive_receipt`
writes structured lines to journald, and `deploy/proactive-receipt-observer@.service`
pipes `journalctl -u bot@%i` into `proactive-receipts.jsonl`. Routing conversation text
the same way was rejected: the text would then also sit in journald under journald's
retention, not `MESSAGE_LOG_DAYS`, so "delete after 30 days" would not be true; and the
log would depend on a second unit running. An in-process append keeps one owner of the
data and one retention rule.

Logging at `remember()` rather than at each caller means one call site, no
`GROUP_*` code touched, and new send paths are covered automatically as long as they
keep calling `remember()` (they must, for history to work).

## Storage

```
/opt/telegram-bots/<instance>/msglog/<chat_id>/<YYYY-MM-DD>.jsonl
```

- **Subdirectory on purpose.** `vps-backup.sh` uses `find -maxdepth 1`, so `msglog/`
  is never copied off-box. This is what keeps the log VPS-only. A test/eval should pin
  it (see Verification), because widening the backup's `find` depth would silently
  start shipping logs to Google Drive.
- **Per chat** so each file is one conversation — `rpzlib.py chat` treats a file as one
  log, and interleaved chats would wreck its novelty/loop numbers.
- **Per day** so retention is "delete files older than N days" — no rewriting.
- Directory `0700`, files `0600` (same user as the bot).

One JSON object per line, shaped so `rpzlib.py` reads it unchanged (`mes`, `is_user`,
`is_system` are the fields its `load_log` uses):

```json
{"ts": "2026-09-25T14:03:11-07:00", "chat_id": 123, "is_user": false,
 "is_system": false, "kind": "reply", "mes": "...", "ver": "2026-09-25.1"}
```

- `kind`: `chat` (a DM turn, either side) | `group` (chat_id < 0) | `proactive` (the
  message `send_triggered` sends) | `synthetic` (the "[you reached out to ... first]" user
  line `send_triggered` stores first; also `is_system: true`, so rpzlib skips it).
  `remember()` takes an optional `kind`; only `send_triggered` passes one.
- `ver` = `BOT_VERSION`, so an audit can split a window by release.
- `ensure_ascii=True` on write (house rule for JSON; also keeps one line per record).

## Toggle: `/msglog`

Admin-gated via `_is_admin`, same model as `/preset`:

```
/msglog            status: on/off, source (env or override), days kept,
                   chats logged, files, bytes on disk, oldest/newest day
/msglog on         start logging (persisted in state.json)
/msglog off        stop logging (persisted); existing files are kept until they age out
/msglog purge      delete this instance's whole msglog/ now (asks for /msglog purge confirm)
```

Plain-text replies (same reason `/preset` uses them: Telegram's legacy Markdown parser
rejects arbitrary text and the command answers with silence).

## Config (`.env.example`)

| var | default | meaning |
|---|---|---|
| `MESSAGE_LOG` | on | kill switch. `0` = off, **and** `/msglog` is unregistered and a saved override is ignored — same pairing as `PRESET_COMMAND=0`, so one `.env` line undoes it without editing `state.json` |
| `MESSAGE_LOG_DAYS` | 30 | retention; parsed via `_env_int` |

Default-on follows invariant 16 (new features default on, mandatory kill switch).

## Retention

- `job_queue.run_daily(_prune_msglog, time=04:17 local)` plus one run at startup.
- Deletes `<YYYY-MM-DD>.jsonl` files whose date is older than `MESSAGE_LOG_DAYS`;
  removes emptied chat directories. Filename date, not mtime — a restore or `cp`
  resets mtime.
- Runs in `asyncio.to_thread`. `pathlib` only — no subprocess (invariant 11).

## Invariants this touches

| rule | how it's satisfied |
|---|---|
| 1 single file | all in bot.py |
| 3 no new LLM calls | none — it's a file append |
| 6 state serialization on loop | `remember()` already runs on the loop; the override flag lives in state.json through `_serialize_state` like `preset_override` |
| 8 no blocking in async | one short line append per turn; if it ever shows in latency, queue lines and flush in `asyncio.to_thread` |
| 11 no processes | pathlib only |
| 15 env parsing | `_env_int` for `MESSAGE_LOG_DAYS` |
| 16 kill switch | `MESSAGE_LOG=0` |

A failed write logs one warning and never raises out of `remember()` — logging must not
be able to break a reply.

## Weekly audit (`tools/weekly_audit.py`)

Root crontab, Sundays 05:17 (install line in `OPS_MANUAL.md` § "Weekly message audit").
Audits every instance whose `msglog/` has day files from the last 7 days, i.e. the bots with
logging on that were talked to; the rest are listed as skipped. Fixed rules over
`tools/rpzlib.py` metrics (a copy of the owner's standalone tool, standard library only) —
no model call, no NanoGPT spend. Report to `/opt/telegram-bots/audits/<date>.md`, metrics
to `<date>.json` for next week's comparison, summary to the owner through `--notify`'s bot.
`audits/` is outside every instance folder, so `vps-backup.sh` never archives it.

Every rule result is exactly one of: **FLAG** (condition observed), **OK**, **BASELINE**
(a numeric-threshold rule, shown but not judged until 3 earlier reports exist — the
thresholds have never been checked against real bot output), **NOT CHECKED** (could not
tell: too few replies, card missing). Counted separately; NOT CHECKED never reads as OK.
Identical flags from several bots (a shared preset layer) are reported once, naming each bot.

**Tier 1 — bugs, flag from week one**

| rule | observes | fix it points at |
|---|---|---|
| `reasoning-leak` | think tags / "Thinking Process:" in the **raw** line (rpzlib's `clean()` deletes them, so this cannot run on cleaned text) | `leak_samples/` → `tests/leak_corpus/`, `_looks_like_reasoning_leak` |
| `mojibake` | `â€`, `Ã`+byte, `Â`+byte sequences | `_fix_mojibake`'s table |
| `assistant-voice` | "let me know if", "I'm here to help", "feel free to", ... in logged text | `_SLOP_OPENER_RE` for openers; a positively worded closing rule in `preset-<name>.txt` |
| `banned-phrases` | rpzlib's banned list (noisy patterns marked "often literal") | positive substitutes in `preset-<name>.txt` |
| `preset-negative-directives` | preset-layer lines starting Never / Don't / Do not / Avoid / No | rewrite as the behavior wanted |

Measured before building rule 3 (not assumed): `_strip_persona_breaks` removes only AI
self-reference sentences, and `_strip_slop` removes assistant openers only at the start of
a reply; neither touches "let me know if" or a mid-reply "I'm here to help". So the logged
(post-filter) text is where those show up. How often `_strip_persona_breaks` fires is
already counted — `_count_error("persona_break")` → `state.json["error_counts"]` — and the
report prints the week's count (a floor: 200 timestamps kept per category).

**Tier 2 — each character's format rule, from its `preset-<name>.txt` (BASELINE first)**

| rule | measures | limit |
|---|---|---|
| `priya-lowercase` / `priya-no-markdown` | replies opening with a capital / with markdown or asterisks | 20% / 5% |
| `emily-third-person`, `marcus-third-person` | first-person words in narration (outside quotes) | 25% |
| `cass-no-narration` | replies with `*action beats*` | 5% |
| `bonnie-length` | replies of 1–2 paragraphs (her card says 3–6) | 50% |
| `nora-questions` | replies ending on "?" | 50% |

Jules has none: "softening her is a character bug" has no fixed-rule signal; that stays with
the `character-reviewer` agent.

**Tier 3 — drift (BASELINE first)**

| rule | measures |
|---|---|
| `loops` | replies whose novelty vs the last 5 is under 65% of the chat's 75th percentile; flag above 15% |
| `openers` | one first word starting ≥30% of replies |
| `card-echo` | rpzlib echo vs card body and `mes_example`; flag at ≥0.15 (copied lines) |
| `proactive-staleness` | proactive messages' median novelty vs the chat's; flag under 65% |
| `voice-blending` | rpzlib `rooms` gap between two bots' replies; flag under 0.02 |
| `card-regression` | non-ASCII count, permanent tokens, lorebook entries missing any of the 15 fields — flag any rise since last week |

**First smoke run (2026-09-25, real cards and documented preset stacks, generated logs)**
already found three real things, left as follow-ups rather than widened into this release:
`preset-core.txt:122` ("Never reference {{user}}'s internal thoughts…", loaded by all seven)
and `preset-explicit.txt:97` ("No soft erotic landing…") are negative directives, and
`emily_harper.json` has 5 lorebook entries carrying only 3 of the 15 fields.

## Verification (shipped)

- `tests/test_msglog.py`: `remember()` writes one line per turn that rpzlib's own
  `load_log` parses; group/proactive/synthetic kinds; toggle off and `MESSAGE_LOG=0` write
  nothing (the kill switch beats a saved toggle); a failed write never breaks `remember()`;
  prune keeps day 30, deletes day 31, goes by filename; `/msglog` status/on/off/purge and
  its admin gate, driven with fake Telegram objects; **the real `vps-backup.sh` run against
  a fake tree archives no message-log content** (searched by content: the script's `cp`
  flattens subfolders, so a path check could not see a leak — found by break-test).
- `tests/test_weekly_audit.py`: tier 1 flags from week one on raw text; threshold rules wait
  for the baseline; too few replies is NOT CHECKED, never OK; a week with nothing audited
  is loud and does not advance the baseline; negative directives; card regression vs last
  week; missing card; report + json written; notify without credentials reports, not raises.
- Each branch above break-tested red with `.claude/tools/break-test.sh`.

## Open choices (defaulted here, easy to change)

1. **Log the raw model output too?** Still open, but narrower than first thought: the
   assistant-voice rule works on logged text and the persona-break count already exists.
   What raw logging would add is visibility into `_strip_slop`, which records no count.
2. **Group chats include other people's messages.** Logged by default like everything
   else; a `MESSAGE_LOG_GROUPS=0` switch is cheap to add if wanted.
3. **Per-instance or fleet-wide `/msglog`.** Per-instance (each bot's own command),
   matching `/preset`. Fleet-wide toggling is the `.env` + `vps-sync.sh` path.
