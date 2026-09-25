# Message log — design sketch

Status: **proposed, not built** (2026-09-25). Owner asked for a way to send the bots'
messages somewhere they can be analyzed and audited, with a slash command to toggle it
and 30-day retention. Owner is comfortable with the data at rest as long as it stays on
the VPS.

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

- `kind`: `reply` | `group` | `proactive` | `user`. Synthetic lines from
  `send_triggered` ("[you reached out to ... first]") get `is_system: true`.
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

## Analysis workflow

On the VPS:

```bash
cat /opt/telegram-bots/nora/msglog/<chat_id>/2026-09-*.jsonl > /tmp/nora-sept.jsonl
python3 rpzlib.py chat /tmp/nora-sept.jsonl
python3 rpzlib.py echo /opt/telegram-bots/nora/nora.json /tmp/nora-sept.jsonl
```

This is the first real bot output `rpzlib.py`'s `chat`/`echo` commands would ever see
(HANDOFF open item: "first run on real data").

## Verification (when built)

- Test that **calls** `msglog_cmd` for status/on/off (delivery gate + `handlers-exercised`).
- Test: `remember()` with logging on writes one well-formed line; with it off writes none;
  a write error does not raise.
- Test: prune deletes day 31, keeps day 30, uses filename date.
- Test or eval: `vps-backup.sh`'s `find` stays `-maxdepth 1` (or explicitly excludes
  `msglog`), so the log cannot start leaving the VPS unnoticed.
- `/audit` reports msglog status — `audit-keys-rendered` requires every key to render.
- `.env.example` documents both vars (`env-vars-documented`).
- BOT_VERSION bump + CHANGELOG entry; OPS_MANUAL command reference gets `/msglog`.

## Open choices (defaulted here, easy to change)

1. **Log the raw model output too?** v1 logs what the user saw. Logging the pre-filter
   text alongside it would show how often `_strip_slop` / `_strip_persona_breaks`
   rewrite a reply, but needs the raw text passed from `_deliver` into the log call.
2. **Group chats include other people's messages.** Logged by default like everything
   else; a `MESSAGE_LOG_GROUPS=0` switch is cheap to add if wanted.
3. **Per-instance or fleet-wide `/msglog`.** Per-instance (each bot's own command),
   matching `/preset`. Fleet-wide toggling is the `.env` + `vps-sync.sh` path.
