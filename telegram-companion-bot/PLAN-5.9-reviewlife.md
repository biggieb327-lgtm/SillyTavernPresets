# Handoff plan — ROADMAP 5.9 `/reviewlife` (6.2 "what nightly can absorb", item 4)

**Status:** not started. Scoped 2026-08-24 (`claude/continue-morning-work-g7gbif`) as the
next 6.2 sleep-time-compute slice, after slices 1 (`v2026-08-24.6`) and 2 (`v2026-08-24.7`)
shipped and slice 3 was closed not-applicable. This is a **feature, not a thin slice** —
read this whole file before writing code.

## Load first
`repo-change-control` + `bot-code-invariants` (any bot.py change). This touches the
living files and the nightly reflection, so also skim the CHANGELOG entries for
`v2026-08-02.11` (life.txt seeded-then-evolved) and the memory-auditor releases (R1 /
`v2026-07-11.1`, which shipped `/reviewmem` — the UX this mirrors).

## What it is (from ROADMAP 5.9)
The nightly reflection already extracts structured facts from the day's conversation. Have
that **same pass** also draft candidate one-line additions to the living files
(`life.txt` / `people.txt` / `projects.txt`) — the character's drift surface, sampled into
every prompt. Never apply them silently: queue them for **per-line accept/reject** via a
new `/reviewlife` command, exactly as `/reviewmem` gates the memory auditor. Accepting
appends one line to the correct living file with a visible log line; rejecting changes
nothing.

**Why per-line approval, not automatic:** silent personality drift is the wrong default on
a companion bot even opt-in. The owner stays in the loop the same way `/reviewmem` already
keeps them for memory.

## The extension point (this is what makes it cheap)
The nightly pass is **`reflect(chat_id)`** (bot.py ~5613), called by `reflection_job`
(bot.py ~13469, which this session already extended for slices 1–2). It builds one
`call_nanogpt` JSON request (`SUMMARY_MODEL`) and today returns
`{beliefs, new_recommendations, resolved, next_goal, milestones}`; the response is parsed
and consumed at bot.py ~5665–5720.

**Add one key to that same request** — `living_file_suggestions` — and one consumer block
next to the `milestones` handling (~5710). This adds **zero** LLM calls (not even a nightly
one): it rides the request that already fires. That is the whole reason 5.9 belongs to 6.2.
Do **not** add a second nightly call; if the reflection prompt is getting overloaded, that
is a prompt-quality conversation with the owner, not a reason to split the call
(`bot-code-invariants` #3).

## The living files (read/write already exist)
- Paths: `LIFE_ARC_FILE = life.txt` (bot.py:1142), `PEOPLE_FILE = people.txt` (1139),
  `PROJECTS_FILE = projects.txt` (1140).
- Read (cached, `_LIFE_TTL`): `_read_life_file(path, cache)` (1803), via `_read_life_arc`
  / `_read_people` / `_read_projects`.
- **There is no living-file *append* helper yet** — `_append_life_event` (1834) writes the
  *separate* `life.txt`-lookalike `LIFE_EVENTS_FILE` (the offline-life-sim log), NOT the
  three living files. You must write a new `_append_life_line(path, cache, line)` that
  appends one line and invalidates that file's cache (`cache["text"] = None`), mirroring
  `_append_life_event`'s shape. Do not reuse `_append_life_event` — wrong file, and it
  stamps `[Mon DD]` prefixes the living files don't use.

## The accept/reject UX to mirror
`/reviewmem` — `reviewmem_cmd` (bot.py:10168), backed by
`_load_memory_review` / `_save_memory_review` (a JSON queue file) and `_memory_log`.
Copy the shape:
- `/reviewlife` (no args) → numbered list of pending suggestions, each showing the target
  file, the candidate line, **and the source quote** from today's conversation that
  prompted it (see Provenance below). Footer: `Use /reviewlife ok <n> or /reviewlife no <n>`.
- `/reviewlife ok <n>` → pop item, `_append_life_line` to its target file, log line, confirm.
- `/reviewlife no <n>` → pop item, drop, log, confirm.
- Empty queue → "Nothing pending."
Store the queue in its own file (e.g. `life-review.json`), do **not** reuse the memory
queue — different lifecycle and apply path.

## Invariants this must satisfy (check the final diff against each)
- **#3 (no new per-message / no new call):** satisfied by folding into the existing
  `reflect()` JSON. Verify you did not add any `call_nanogpt`/`_do_request`.
- **#10 + #17 (provenance / null-over-guess):** the drafts are *model-generated*. The
  living files are the character's canvas, not a user-fact store, so #10 is not directly
  triggered — but store the **source quote** with each draft and show it in the listing
  (as `/reviewmem` shows `src:`), so approval is a human entailment judgement made with
  evidence, and instruct the prompt to propose a line **only when the day's conversation
  concretely supports it** (null over plausible guess). No source → no suggestion.
- **#6 (save_state on the loop only):** the queue file writes happen in `reflect()` (a
  coroutine, on the loop) and in `reviewlife_cmd` (handler, on the loop). Fine. Do not
  write the queue from a worker thread.
- **#15 (numeric env via `_env_int`):** any cap (e.g. max pending suggestions) through
  `_env_int`.
- **#16 (default-on + kill switch):** new feature defaults ON with a mandatory kill
  switch, e.g. `REVIEWLIFE=1` unset = active, `0` = the nightly pass skips drafting and
  `/reviewlife` reports disabled. Unset must preserve today's behavior (no drafting).

## Build order
1. Prompt: add `living_file_suggestions` to `reflect()`'s system prompt + JSON schema
   (~5632–5658). Ask for at most N items, each `{file: "life"|"people"|"projects", line:
   "<one line>", source: "<quote from today>"}`; empty list when nothing concrete.
2. Consumer: parse that key next to `milestones` (~5710); validate `file` is one of the
   three, `line`/`source` are non-empty strings; enqueue to `life-review.json`. Cap the
   queue (drop oldest or refuse). Gate the whole draft step on `REVIEWLIFE`.
3. `_append_life_line(path, cache, line)` helper near `_append_life_event` (1834).
4. `reviewlife_cmd` mirroring `reviewmem_cmd`; register it in `main()`'s command registry
   and the Telegram command menu (grep how `reviewmem` is registered and match both sites).
5. `.env.example`: document `REVIEWLIFE` (+ any cap var) with unset=active.
6. Version + changelog + ROADMAP (mark 5.9 shipped and check off 6.2 list item 4).

## Test plan
- **Pure/enqueue logic:** feed a fake `reflect()` JSON with a `living_file_suggestions`
  entry (monkeypatch `call_nanogpt`), assert it lands in the queue with file/line/source;
  assert a malformed `file` value is rejected; assert `REVIEWLIFE` off enqueues nothing.
- **`_append_life_line`:** appends one line to a tmp file, invalidates cache, does not
  stamp a date, does not touch the other files.
- **Delivery-gate requirement — do NOT skip:** the gate blocks the turn if the diff adds a
  `*_cmd` no test **calls**. Write a test that actually invokes `reviewlife_cmd` (via
  `asyncio.run`, `SimpleNamespace` update/context — copy a `reviewmem`/`reviewlife`-shaped
  existing test) for the list, `ok`, and `no` paths. A test that only reads the handler's
  source is exactly the defect that shipped the `/features` `ValueError` (2026-08-02); the
  gate exists to catch it.
- `_env_bool` census: add `REVIEWLIFE` to `TestEveryBooleanFlagDefault.DEFAULTS` in
  `tests/test_pure.py` (alphabetical) — `verify.sh` fails otherwise, as it did for
  `NIGHTLY_PREDRAFT`/`AMBIENT_PREDRAFT` this session.

## Stopping rule (written before the data, per unattended-loops discipline)
If the design turns out to need a new per-message call, or cannot keep the drafting off the
reply path, **stop and take it to the owner** — do not ship it as a live-path feature. 5.9
is only worth doing as an extension of the existing nightly call; if that premise breaks
(the way slice 3's premise broke), the right move is to close it, not to force it.

## Open questions for the owner (ask before building, per §Working-principles unattended note)
- Should suggestions be **per-chat** (owner only, like reflection) or fleet-shared? The
  living files are per-instance, and `reflect()` runs for `get_owner()` only, so per-owner
  is the natural default — confirm.
- Cap on pending suggestions before old ones drop, and whether an un-reviewed queue should
  nag (recommend: no nag, surfaced only on `/reviewlife`, like `/reviewmem`).
- "Done when" (from 5.9): a day's conversation with a clear life-event produces a correct
  one-line suggestion; rejecting changes nothing; accepting appends to the right file with
  a visible log line. Validate against a real day on one instance before fleet promotion.
