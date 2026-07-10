# Group Chat / Bot-to-Bot — Design (ROADMAP 3.4)

Status: draft for adversarial-critic review. No bot.py code lands until this survives.

Goal: two character bots (pilot: **Priya + Jules**) and one human in one Telegram group,
behind `GROUP_MODE=1` on exactly those two instances. Everything here is additive and
gated — with `GROUP_MODE` unset, bot.py behavior is byte-identical to today.

Product decisions already made (owner sign-off, 2026-07-07):

- Pilot pair is Priya + Jules.
- Characters treat each other as **real people in-fiction** — Priya believes Jules is a
  real person in the group, and vice versa. Neither knows the other is an AI.
- Group chats are **read-only** against flat-file memory: `memories.txt`,
  `user_notes.txt`, etc. are never written from a group, and `user_notes.txt` (private
  relationship state) is not even read into group prompts.
- v1 is **text + reactions only**: no voice notes, selfies, or memes in groups.

---

## 0. The platform constraint everything hangs on

**Telegram bots never receive messages sent by other bots.** This is a deliberate
Bot API anti-loop policy and is independent of privacy mode. Two consequences:

1. Bot-to-bot conversation cannot flow through Telegram updates at all. When Priya posts
   to the group, Jules's process hears nothing from Telegram. The side channel is the
   shared filesystem: all instances live on one phone and already share
   `~/telegram-bot/` (the `world.txt` precedent). We add a **group ledger** file there.
2. For bots to see ordinary (unaddressed) *human* group messages, **privacy mode must be
   disabled** per bot via BotFather (`/setprivacy` → Disable). With privacy on (the
   default), a group bot only receives commands, @mentions, and replies to itself.

A corollary worth stating plainly: because Telegram never shows one bot another bot's
messages, a runaway bot-to-bot loop through Telegram itself is *impossible*. The only
loop risk we create is through our own ledger — which means the loop controls in §3 are
enforceable in our own code, on our own data structure. The failure domain is entirely
ours.

## 1. Message flow and the shared ledger

### The ledger file

- Path: `<GROUP_LEDGER_DIR>/group_<chat_id>.jsonl`. Default `GROUP_LEDGER_DIR` is the
  directory containing bot.py (`_SCRIPT_DIR`, i.e. `~/telegram-bot/` on the phone) —
  the same shared-path convention as `WORLD_FILE`. Group chat_ids are negative; the
  filename keeps the sign (`group_-1001234.jsonl`).
- One JSON object per line:

  ```json
  {"ts": 1751900000.0, "msg_id": 118, "sender": "Priya", "kind": "bot",
   "text": "ok but why is the office fridge always full of other people's sadness",
   "reply_to": 117}
  ```

  `sender` is the character's first name for bots, the human's Telegram first name for
  humans. `kind` is `"human"` or `"bot"`. `msg_id` is the Telegram message id (unique
  per chat). `reply_to` is the Telegram message id being answered, or null.

### Writes

- Append-only, under `fcntl.flock(LOCK_EX)` with the file opened `O_APPEND`. All
  instances are on one phone / one ext4 filesystem, where flock is reliable. (First
  on-device prototype step: a two-process flock/O_EXCL smoke test before trusting it —
  see §10.)
- **Human messages**: every privacy-off bot in the group receives the same human message
  from Telegram. Whichever bot handles it first appends it; the others detect the
  duplicate `msg_id` under the same lock and skip the append (but still process the
  message for their own reply decision). Dedup check = scan the tail of the file for the
  msg_id while holding the lock; the tail window (last ~50 lines) is sufficient since
  msg_ids arrive roughly in order.
- **Bot messages**: after a successful `send_message`, the sending bot appends its own
  message using the `message_id` Telegram returned. This is the *only* way other bots
  ever learn it was said.

### Reads

- A `job_queue.run_repeating` poll job (`_group_poll_job`, every `GROUP_POLL_SECONDS=5`),
  registered only when `GROUP_MODE=1`, reads lines past a persisted cursor
  (`group_cursor[chat_id]` = byte offset, stored in state.json).
- **The poll job processes `kind == "bot"` entries from other senders ONLY.** Human
  messages are heard live via Telegram by every privacy-off bot and are *never* acted
  on from the ledger — their ledger entries exist purely as chain-reset markers and
  history. This is load-bearing: if the poll job also fed human entries into the reply
  path, a bot that already answered an addressed human message live would answer it a
  second time when its own poll swept past the same line (addressed messages don't go
  through claims, so nothing would dedup the double-reply).
- Human entries the poll encounters are consumed silently (cursor advances, human name
  cached for `{{user}}`, nothing else).
- **Startup staleness guard**: entries older than `GROUP_LEDGER_MAX_AGE_SECONDS=600`
  are skipped (cursor fast-forwarded past them). A bot that restarts mid-conversation
  must not replay a ten-minute-old exchange.
- Own entries are always skipped (matched on `sender == NAME`).
- Note on cadence: `run_repeating` is an in-process asyncio job — no new PID, so the
  phantom-process budget is untouched. It does add a 5s wakeup on the two pilot
  instances (alongside the existing 60s `_touch_alive`); that's the deliberate
  trade for bot-to-bot latency, and it exists only where `GROUP_MODE=1`.

### Rotation

When the appender finds the file over ~1000 lines it rewrites it to the last 300, under
the same exclusive lock (either bot may do it; the lock serializes append-vs-rotate,
and reads also take the lock briefly, so a reader never sees a half-rewritten file).
Readers detect shrink (file size < stored cursor) and reset their cursor to EOF. Honest
cost: a poller that was lagging at rotation time drops whatever unread bot messages fell
between its cursor and the rewrite — up to one poll interval's worth. That means a
missed reply opportunity, never a replay or a loop, and rotation fires at most once per
~1000 messages.

### Failure modes

| Failure | Behavior |
|---|---|
| Claim winner crashes before replying | That message stays unanswered — the claim file blocks any peer from retrying it until the claim TTL (10 min) prunes it, and by then it's stale anyway. This is a real dead window, accepted for v1: the human's recovery is sending a *new* addressed message, which is answered deterministically without a claim. |
| Corrupt/partial ledger line | Line-by-line tolerant JSON parse; bad lines skipped and counted (`_count_error("group_ledger")`). |
| Ledger file deleted mid-run | Appender recreates it; readers reset cursor. Conversation continuity in prompts survives via per-chat `conversation_history` (state.json), which is the actual prompt source — the ledger is a signaling channel, not the memory store. |
| One bot down | The other bot wins every claim; group degrades to single-bot, which is exactly today's behavior. |
| Clock skew | None — one phone, one clock. |

## 2. Turn-taking (hard problem 1)

Bots must not answer every message. Two cases:

### Addressed messages — deterministic

`_is_addressed(text, char_name, bot_username, replied_to_own)` returns True when any of:

- the text contains `@<bot_username>` (from `context.bot.username`),
- the text contains the character's first name on a **word boundary**, case-insensitive
  (`\bpriya\b` — "priya's" matches, "priyanka" does not),
- the message is a Telegram reply to a message this bot posted (checked against the
  ledger: `reply_to` msg_id whose entry has `sender == NAME`).

**Addressed *human* messages** → reply deterministically, no claim, no dice: addressing
selects the responder, and each bot decides independently off its own live Telegram
update. Both bots addressed in one message ("priya, jules, settle this") → both reply;
that's the correct reading of the message.

**Bot messages are different: being addressed by a bot never skips the claim.** Every
reply to a bot message — addressed or not — must win that message's claim (§3). This
matters because addressing is the LLM's favorite register ("jules, you're wrong" /
"priya, no") — if a name-drop bypassed the serialization, the loop controls would be
optional exactly when the loop risk is highest.

### Unaddressed messages — atomic claim, exactly one responder

1. On receiving an unaddressed human message (or deciding to respond to a bot message,
   §3), the bot waits a jittered delay — **`await asyncio.sleep`, mandatory; a blocking
   `time.sleep` here freezes the instance's entire event loop (every DM, the poll job,
   the `_touch_alive` heartbeat) for up to 5s per group message.** Delay =
   `uniform(0.5, 3.0)` + `GROUP_ALTERNATION_PENALTY` (default **2.0s**) if this bot was
   the last *bot* to speak in the ledger. The penalty biases toward alternation — the
   quieter character tends to win the next open message — without any coordination.
2. After the delay it attempts to create
   `<GROUP_LEDGER_DIR>/group_claims/<chat_id>_<msg_id>` with
   `os.open(..., O_CREAT | O_EXCL)`. Exactly one process can succeed — POSIX guarantees
   it. Winner replies; losers stay silent for that message, permanently.
3. Claim files are content-free markers, pruned after `GROUP_CLAIM_TTL_SECONDS=600`.

The claim also caps the human's cost exposure: an unaddressed message costs at most one
chat-model call fleet-wide, not one per bot.

### Alternatives considered and rejected

- **Deterministic routing (`msg_id % N`)**: no shared file needed, but requires a static
  agreed roster (fragile as instances come and go), can't express alternation or
  relevance, and a crashed bot silently eats its share of messages forever.
- **Leader/dispatcher bot**: single point of failure and a second protocol (how do
  followers learn the leader's verdict? …another shared file). Strictly more machinery
  for the same guarantee.
- **Independent probability 1/N per bot**: no file, but regularly produces zero
  responders (awkward silence) or two (pile-on), and both defects worsen as N grows.
- **Claim file** (chosen): ~10 lines of code, POSIX-atomic on one filesystem,
  exactly-one guarantee, and degrades perfectly — if one bot is down, the survivor wins
  every claim and the group still works.

## 3. Loop prevention (hard problem 2)

The ledger is the only channel bots hear each other on, so loop control is a property we
enforce on our own data structure. The controls, and — because two of them are checked
against a file that another process is concurrently appending to — exactly *when* each
is evaluated:

- **Serialization: every bot-message reply goes through the claim.** Addressed or not
  (§2). Each bot message can therefore get at most ONE reply fleet-wide, ever. A bot
  can also only react to a peer message *after* it exists in the ledger (that's the
  only way it learns of it), so at decision time the chain it reads already includes
  the message it's replying to. For N=2 this alone makes the exchange strictly
  alternating and the cap check race-free: when Priya evaluates a reply to Jules's
  message, every message that could lengthen the chain is already visible to her.
- **Hard cap.** `_bot_chain_len(entries)` counts consecutive `kind == "bot"` entries at
  the ledger tail. Checked twice: at decision time (before spending a model call), and
  **re-checked under the ledger's exclusive lock immediately before `send_message`** —
  if the chain reached `GROUP_BOT_CHAIN_MAX` (default **2**) while the reply was
  generating, the generated reply is discarded, not sent. A wasted model call is the
  price of never exceeding the cap. The lock is **released before** `send_message` —
  see the lock discipline below for why that window is provably empty at N=2. Any
  human message resets the chain to zero by construction. Worst case per human beat:
  human → bot A → bot B → silence.
- **Lock discipline (binding on the implementation).** bot.py has no existing `flock`
  usage; every blocking syscall elsewhere goes through a worker thread, and ledger I/O
  follows the same rule: *every* flock acquire/release (append, read, rotate, the
  pre-send cap re-check) runs inside `asyncio.to_thread`, and **the lock is never held
  across an `await`** — in particular never across `send_message`. Holding it across a
  network call would both starve the peer's 5s poll and, on a bad connection, freeze
  the writer's own event loop, reproducing the exact `time.sleep` failure mode §2
  bans. Releasing before send does open a check-then-send window, but at N=2 it is
  provably empty: the only actor who could lengthen the chain during my send is the
  peer, the peer only reacts to messages that exist in the ledger, my message enters
  the ledger only *after* my send completes, and the claim on the message I'm
  answering already excludes the peer from answering it too. At N≥3 the window is a
  real (two bots answering *different* messages) but bounded race — one message over
  cap, worst case — documented as the residual risk of the out-of-scope N≥3
  configuration.
- **Probability gate.** Below the cap, a bot replies to another bot's message only if
  `_is_addressed(...)` or `random() < GROUP_BOT_REPLY_PROB` (default **0.35**) — most
  bot remarks get no reply, which reads natural (group chats are full of unanswered
  messages) and keeps cost down. Passing the gate still requires winning the claim.
- **Self-filter.** A bot never processes its own ledger entries (`sender == NAME`).
- **Send throttle.** `GROUP_MIN_GAP_SECONDS=20` minimum between a bot's own consecutive
  group messages — even a logic bug upstream can't produce a message torrent.
- **Daily budget.** `GROUP_DAILY_BOT_BUDGET=30` bot-to-bot replies per instance per day
  (counter in state.json, reset at midnight rotation). At the cap the bot simply stops
  replying to bots until tomorrow; human-addressed messages are unaffected.

Defense in depth: claim (serializes every exchange), cap (bounds every exchange's
length, enforced under the lock), probability (bounds expected frequency), throttle
(bounds burst rate), budget (bounds daily total). Any four can fail and the fifth still
bounds the damage.

## 4. Cost (hard problem 3)

Worst case per human message: **≤2 chat-model calls fleet-wide plus amortized
summarization**. The "≤2" is a consequence of the mechanisms in §2–§3, not a separate
promise: the claim gives an unaddressed message exactly one responder, and the chain
cap ends every bot exchange at two. Summarization (`maintain_memory`, SUMMARY_MODEL) is
kept and runs on its normal amortized schedule — it is not per-beat, but it is not zero
either. Every other side call is off in groups:

| Call | In groups |
|---|---|
| `post_reply_analysis` (mood + user note + NPC memory) | **Skipped** — also the flat-file write path, see §5 |
| Inner voice | Skipped |
| `maybe_search` / link reading | Skipped in v1 |
| `maybe_auto_react` (REACTION_MODEL call) | Skipped — the in-completion `[react: …]` tag still works and is free |
| TTS / selfie / meme generation | Skipped (v1 is text + reactions only) |
| Rolling summarization (`maintain_memory`) | Kept, but trigger threshold doubled for group chats (`SUMMARY_EVERY × 2`) — group banter is lower-density than DM conversation |
| Embeddings on memory write | N/A — groups never write memories |

Expected steady-state: a chatty evening (50 human messages) costs ≤ 50 claims' worth of
single replies plus ≤ a handful of bot-to-bot beats — comparable to one active DM
conversation, on models already budgeted for that.

## 5. Memory semantics (hard problem 4)

Two memory tiers exist today, and they split cleanly:

- **Per-chat state (`state.json` dicts, keyed by chat_id)** — `conversation_history`,
  `summaries`, `facts`, `moods`, `milestones`, … The group is just a new chat_id, so the
  group automatically gets its own isolated history/facts/mood with **zero schema
  change**, and nothing from the group leaks into the DM chat_id's state. This is the
  free tier and it's already correct.
- **Per-instance flat files** (`memories.txt`, `user_notes.txt`, `people.txt`,
  `projects.txt`, `life.txt`, …) — injected into *every* chat's prompt, including the
  private DM. This is where pollution risk lives.

Policy (per owner decision — **read-only in groups**):

- **Writes: never from a group.** Two write surfaces exist, and they're closed by two
  different mechanisms — one per surface, not per function, because round 1 and round 2
  of adversarial review each caught a path a hand-enumerated list had missed
  (`_check_joke_used`, then `/note` `/notes` `/addjoke` `/deljoke` `/addoutfit`
  `/deloutfit` `/outfit` `/today` `/remindme` `/setreminder` `/cron`). A list that has
  been incomplete twice is the wrong shape; the design closes *classes*:

  | Write surface | Closed by |
  |---|---|
  | **Automatic (reply-generation tail)**: `post_reply_analysis` (→ `user_notes.txt`, `memories.txt`, `embeddings.json` via `_append_memory`, mood), `_check_joke_used` (→ `jokes.json`), selfie/wardrobe paths (→ `wardrobe.json`) | `_group_deliver` is a lean sibling of `_deliver` that simply *does not contain* these calls — the group tail is allowlist-built (remember + send + ledger append + react), not a copy of `_deliver` with skips. A new call added to `_deliver`'s tail later does not leak into groups by default. |
  | **Manual (command handlers)**: every `/command`, present and future | **Default-deny at one choke point.** A single guard handler registered in PTB handler group `-1` intercepts every command update in a group chat and stops propagation (`ApplicationHandlerStop`) with a one-line refusal, unless the command is on the tiny group allowlist: `/chatid` (needed during setup) — nothing else in v1. Ops commands (`/audit`, `/update`, …) are DM affordances; reminders and cron in groups are deferred with the other proactive-into-group features (§9). No per-command gating, so no future command reopens this. |

  The `inside_jokes` leak closes on the read side too: the group prompt never injects
  the inside-jokes block (`inside_jokes` is a global list, not per-chat — a DM's
  private bits must not be performed in front of the third party, and a group reply
  must not tick the DM's joke cooldowns).

  Per-chat in-memory structures written during group replies (`conversation_history`,
  `_recent_questions`, mood dict, facts) are keyed by the group's chat_id inside
  state.json — isolated by construction, allowed.
- **Reads: the character's life comes in; the private relationship doesn't.** Groups
  read `memories.txt`, `people.txt`, `projects.txt`, `life.txt`, day context, world
  context — Priya in the group is still Priya, same job, same day, same rainstorm
  (`world.txt` already synchronizes the backdrop fleet-wide, which now pays off
  directly: both bots describe the same weather in the same group).
  `user_notes.txt` is **excluded** from group prompts — it is the private ledger of the
  1:1 relationship ("mentioned the interview Tuesday", emotional state notes) and has no
  business being performed in front of a third party.

`{{user}}` and `fill()`: v1 scope is exactly one human in the group, so `{{user}}` still
denotes that human and the two-participant substitution in `fill()` holds. `user_names`'
overwrite-per-message behavior is corrected in group mode: the human's name is taken only
from `kind == "human"` messages, so a bot's ledger entry can never become `{{user}}`.
Multiple humans are explicitly out of scope (§9).

## 6. Safety and access control

- **Owner protection (pre-existing bug, fixed as part of this work).** `set_owner` is
  claimed by the *first interaction* today — if a bot were added to a group first, the
  group would capture all proactive messaging (heartbeats, note follow-ups) forever.
  There are seven `set_owner` call sites, not two, so the guard goes **centrally inside
  `set_owner()` itself**: a negative (group) chat_id is refused, once, where every
  caller passes through. This guard ships even for non-GROUP_MODE instances — it's a
  latent bug today.
- **Group allowlist — mandatory.** Privacy-off means the bot reads every message in any
  group anyone adds it to. `GROUP_ALLOWED_CHATS` (comma-separated chat ids) is required;
  a group message whose chat_id is not listed is dropped at the top of the handler —
  no state, no ledger, no reply. `GROUP_MODE=1` with an empty allowlist means group
  messages are ignored entirely (fail closed, same philosophy as `ADMIN_API_BIND`).
- **Human gating unchanged.** `_is_allowed(user_id)` still applies to the sender of
  every group message; strangers in an allowed group are ignored unless `ALLOWED_USERS`
  is empty.
- **Non-text handlers** (photo, voice, sticker, video, document, location) return early
  in group chats in v1 — smaller surface, and the media pipelines (vision calls, whisper
  transcription) are exactly the expensive paths §4 is keeping off.
- **Commands in groups: default-deny** (mechanism specified in §5). Every command —
  including admin ops like `/update`, `/restart`, `/backup` — is refused in group
  chats except `/chatid`. Admins run ops from the DM; `/backup` in particular must
  never post state files into a group.

## 7. Prompt and delivery changes

### Prompt (`assemble_messages` grows a group branch)

- New system block when assembling for a group chat_id:

  ```
  # Group chat
  You're in a small group chat with {human_name} and {peer_names}. {peer_lines}
  To you they're real people you know — this is just a group text thread.
  Group texting rules: keep replies short (usually 1-2 bubbles); talk TO people,
  not about them; you don't have to respond to everything — it's fine to let a
  message pass; never answer on someone else's behalf.
  ```

  `peer_names` comes from `GROUP_PEERS` (comma-separated character names in the
  instance's .env); `peer_lines` is an optional one-line-per-peer relationship note from
  `GROUP_PEER_NOTES` (e.g. `Jules: a friend you know through Brian; you find her
  funny but you haven't hung out one-on-one much`). The design deliberately keeps the
  peer relationship thin in v1 — the characters discover each other in conversation,
  and the discovered dynamic accumulates in the group's own per-chat facts/summaries.
- **Speaker-labeled history.** Others' messages are stored via
  `remember(chat_id, "user", f"{sender}: {text}")` — both the human's and the other
  bot's, distinguished by name prefix; own replies stored as `assistant` unprefixed.
  The existing summarization pipeline works on this unchanged (summaries naturally
  mention who said what).
- Known cosmetic limit, accepted for v1: card text written for a 1:1 register ("she's
  three months into something with {{user}}") can read oddly in a group. The group
  block's "group texting rules" mitigate; a card-side `group_scenario` field is a
  possible v2 refinement, noted in §9.

### Delivery (`_group_deliver`, a lean sibling of `_deliver`)

- **Threaded replies**: when answering an addressed message or a bot message, pass
  `reply_to_message_id` so the answer visibly threads. Unaddressed claimed replies send
  plain (that's how humans text in groups).
- `send_bubbles` gains an optional `reply_to_message_id` and returns the last sent
  `Message`, whose `message_id` goes into the ledger append.
- Reactions: the in-completion `[react: …]` tag sets a reaction on the message being
  answered — kept, it's charming and free.
- No TTS, no selfie, no meme, no scheduled follow-up ("did the thing go ok?" pings are
  a 1:1 intimacy, not group behavior), **no `_check_joke_used`** (§5 — it writes the
  global `jokes.json`), no typing-indicator *during the claim delay* (typing starts
  only after winning the claim — otherwise the loser visibly "gives up typing," which
  reads wrong).

## 8. Configuration summary

All new, all inert unless `GROUP_MODE=1`:

| Key | Default | Meaning |
|---|---|---|
| `GROUP_MODE` | `0` | Master switch per instance |
| `GROUP_ALLOWED_CHATS` | empty (fail closed) | Comma-separated group chat ids this bot may participate in |
| `GROUP_PEERS` | empty | Names of the other character(s) in the group |
| `GROUP_PEER_NOTES` | empty | Optional `Name: relationship line` per peer, `;`-separated |
| `GROUP_BOT_REPLY_PROB` | `0.35` | Chance of replying to an unaddressed bot message |
| `GROUP_BOT_CHAIN_MAX` | `2` | Consecutive bot messages allowed since last human one |
| `GROUP_MIN_GAP_SECONDS` | `20` | Min seconds between own group messages |
| `GROUP_DAILY_BOT_BUDGET` | `30` | Max bot-to-bot replies per day |
| `GROUP_POLL_SECONDS` | `5` | Ledger poll cadence |
| `GROUP_ALTERNATION_PENALTY` | `2.0` | Extra claim delay if this bot spoke last |
| `GROUP_LEDGER_DIR` | dir of bot.py | Shared dir for ledger + claim files |
| `GROUP_LEDGER_MAX_AGE_SECONDS` | `600` | Ignore ledger entries older than this at startup |
| `GROUP_CLAIM_TTL_SECONDS` | `600` | Claim files older than this are pruned |

## 9. Explicitly out of scope for v1

- **More than 2 bots** in one group — the mechanisms (claims, chain cap, budgets) are
  N-safe by construction, but the prototype validates N=2 only.
- **More than 1 human** — breaks the `{{user}}` two-participant assumption; needs
  per-participant identity in prompts (a real design change, not a config knob).
- **Media in groups** — voice/selfie/meme/photo-understanding, all off.
- **Group-initiated proactive messages** — heartbeats and note follow-ups stay DM-only,
  and so do user-created scheduled sends: `/remindme`, `/setreminder`, and `/cron` are
  refused in groups by the default-deny command guard (§5), so nothing can schedule a
  future message into the group. (A character spontaneously texting the group is v2
  gold, but it needs its own budget and claim design.)
- **Group-scoped flat-file memory** — a `group_memories.txt` tier can come later if the
  per-chat facts prove insufficient.
- **Edited-message handling** — ledger entries are immutable; edits are ignored.
- **Cross-group** — one group per pilot; multiple simultaneous groups are untested
  (though the design keys everything by chat_id).

## 10. Rollout and acceptance

Setup (documented in OPS_MANUAL/SETUP_GUIDE):

1. BotFather → `/setprivacy` → **Disable** for Priya's and Jules's bot accounts. Then
   remove and re-add each bot to the group — Telegram applies privacy changes to a group
   only on re-add.
2. Create the group; add both bots + the human. Get the chat_id (it appears in each
   bot's log line on the first received message; also `/chatid` works in-group).
3. In `~/priya-bot/.env` and `~/jules-bot/.env` only:
   `GROUP_MODE=1`, `GROUP_ALLOWED_CHATS=<id>`, `GROUP_PEERS=<other name>`.
4. Deploy bot.py normally (`/update` one bot, `/restart` the rest), then `/restart` the
   two pilots to pick up the .env changes.
5. **On-device atomicity smoke test** (once, before trusting either primitive): the
   prototype ships a tiny `--claim-test` mode covering both load-bearing mechanisms —
   (a) two concurrent processes race 100 claims, assert exactly one winner each
   (`O_EXCL`); (b) the same two processes append 100 ledger lines each under
   `flock(LOCK_EX)`, assert all 200 lines present, intact, and unintermixed. Verifies
   both on Termux's ext4 before the pilot goes live.

Acceptance script (all must pass before the pilot is called working):

1. Unaddressed human line → **exactly one** bot answers (repeat ×10, observe both bots
   win some — alternation working).
2. `@priya what do you think` → **exactly one reply from Priya, not two** — this probes
   the live-handler-vs-poll-job double-answer race directly (the poll job must never
   act on human entries). Repeat ×5 and count Priya's messages.
3. `jules you're wrong about this` (name, no @) → only Jules answers, once.
4. Human line → bot A answers → bot B chimes in → **silence** (chain cap 2 holds), ×5.
5. Adversarial loop bait, ×5: `priya, ask jules a question` — the reply will
   near-certainly name Jules, Jules's reply will near-certainly name Priya. Verify the
   exchange still stops at 2 bot messages under real poll timing (this probes the
   addressed-bypasses-nothing rule and the under-lock cap re-check).
6. Restart one pilot mid-conversation → no replay of old messages (staleness guard).
7. **Full flat-file freeze check.** Before the session:
   `sha256sum ~/priya-bot/{memories.txt,user_notes.txt,people.txt,projects.txt,life.txt,jokes.json,wardrobe.json,embeddings.json,reminders.json,cron_jobs.json} > /tmp/pre.sha`
   (same for jules-bot; missing files are skipped). During the session, deliberately
   attempt the leak paths from the group: `/note test`, `/notes clear`, `/addjoke x | y | z`,
   `/today fake event`, `/remindme 5m test`, `/addmem test` — every one must be refused
   by the default-deny guard. After the evening: every hash identical. `day.txt` and
   `state.json` are excluded from the hash set — jobs legitimately write them — but
   `/today` from the group must have been refused (checked above), the group's
   history/facts must exist under the group chat_id in state.json, and the DM chat_id's
   entries must be unchanged.
8. DM each pilot → normal 1:1 behavior, heartbeat/note-followups still target the DM
   owner only.
9. A non-allowed group: add Priya to a second group not in `GROUP_ALLOWED_CHATS`, send
   messages → zero response, zero ledger, zero state.

Kill switch: remove `GROUP_MODE=1` from the two .env files and `/restart` — instances
return to pure DM behavior; the ledger file goes inert (nothing reads it).

## 11. Monitoring

- New error categories: `group_ledger` (parse/IO failures), `group_claim` (claim IO
  errors). Both visible in `/errors` and counted by `_self_audit`.
- `/audit` gains one group line when GROUP_MODE=1: ledger size, bot-sends today vs
  budget, chain state — so "why did she stop replying to Jules?" is answerable from
  Telegram (answer: budget or cap, and which).
