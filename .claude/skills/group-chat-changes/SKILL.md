---
name: group-chat-changes
description: Rules for touching ANY group-chat code — GROUP_* env vars, the shared ledger, claim files, _group_deliver, bot-to-bot behavior, the priya/jules pilot, OR any handler that branches on `chat_id < 0` / calls `_handle_group_message` (handle_message is the one that matters — it looks like a plain per-message handler and is also the group entry point). Load BEFORE reading or modifying that code, even for "small" changes, and even when the change looks private-chat-only.
---

# Group-chat changes

The protections here are *class-level* (choke points + allowlists, two of them
CI-pinned) because hand-kept inventories of write paths missed leaks twice during
design review. A small, plausible-looking change here is how group content leaks
into private DM state, or vice versa.

## When NOT to use

- Bot changes that don't touch group paths — `repo-change-control` +
  `bot-code-invariants` suffice.
- Operating the pilot (enabling GROUP_MODE, BotFather settings, adding a chat) —
  that's configuration, documented in `OPS_MANUAL.md` § "Group chat (experimental)"
  and `SETUP_GUIDE.md`; no code skill needed.

## Procedure

1. **Read `telegram-companion-bot/GROUP_CHAT_DESIGN.md` first — actually read it.**
   Minimum: §0 (the platform constraint: Telegram never delivers one bot's messages
   to another bot — everything flows through the flock'd ledger + atomic claim
   files), §6 (safety/access control), §9 (explicitly out of scope for v1), §12
   (durable enforcement). If your change contradicts §9, it's a design change:
   stop and take it to the user, don't code it.

2. **Know the pinned boundaries** (CI evals `group-deliver-clean` and
   `group-cmd-allowlist` in `.claude/evals/run-evals.sh`):
   - `_group_deliver` is allowlist-BUILT: none of the DM tail's side effects
     (`post_reply_analysis`, `_check_joke_used`, `send_selfie`, `send_meme`,
     `_send_voice_reply`, `_append_user_note`, `_append_memory`) may appear in its
     body — those write per-instance flat files that would leak group content into
     private DM state.
   - `GROUP_ALLOWED_COMMANDS` stays exactly `{"chatid"}`. Widening either boundary
     is a reviewed act: **edit the eval in the same commit**, with the rationale in
     the commit message. A red group eval is never "fix the eval to pass".

3. **Preserve the failure-closed posture:** fleet-wide default is groups ignored
   (only `/chatid` answers); `GROUP_MODE=1` + `GROUP_ALLOWED_CHATS` (fail closed) +
   `GROUP_PEERS` enable it per-instance. Loop protection: `GROUP_BOT_CHAIN_MAX=2`,
   `GROUP_DAILY_BOT_BUDGET=30`. A change that makes any of these default-open or
   removable-by-omission is wrong by definition.

4. **Concurrency rule that bites here specifically:** never hold the group-ledger
   flock across an `await` (see `bot-code-invariants` #9). The claim-file design
   assumes short, synchronous critical sections.

5. **Verify:** full standing block (py_compile, pytest, run-evals.sh) — watch the
   two group evals by name. On-device, the pilot has a one-time check:
   `python bot.py ~/priya-bot --claim-test` (expect two PASS lines) — ask the user
   to run it after any ledger/claim change.

6. **Ship** via `repo-change-control` (this skill adds constraints; it doesn't replace
   the release process).

## Debugging a live group — the probe is in-world (C11)

Group traffic splits in two, and only one half is safe to debug with:

- **Commands are invisible to the characters.** `group_guard` raises
  `ApplicationHandlerStop` before `handle_message`, so nothing but the reply itself
  ever exists. `/chatid` answers from any instance, participating or not (it returns
  at the allowlist check, *before* `GROUP_MODE` is consulted). Any other command
  produces the audible `"(commands are a DM thing)"` refusal **only** when
  `GROUP_MODE and chat.id in GROUP_ALLOWED_CHATS` — which makes it a free readout of
  whether an instance considers itself a participant.
- **Plain text is permanent and shared.** It enters the ledger and every
  participating character's persisted `conversation_history`. It cannot be cleared
  from inside the group: `/clear` targets `update.effective_chat.id` and commands are
  refused there.

On 2026-07-28 an `@priya_bot` probe — sent to test privacy mode — taught jules that
her groupmate was a bot, and she said so in character. Use the command probes above,
or a DM, or phrase the probe in-world.

## Quality bar

- No new write path from group context to per-instance flat files unless it is
  provenance-tagged, designed for it, and the evals are extended to cover it in
  the same commit.
- §9's out-of-scope list respected, or the user explicitly approved the scope
  change first.
- The change reasons about BOTH bots (priya and jules run this code against the
  same ledger concurrently).

## Verification checklist

- [ ] GROUP_CHAT_DESIGN.md sections read this session (not recalled from memory)
- [ ] `group-deliver-clean` and `group-cmd-allowlist` green — or deliberately
      edited in the same commit with rationale
- [ ] No flock held across an await in the diff
- [ ] Fail-closed defaults intact (unset env = groups ignored)
- [ ] `--claim-test` requested from the user if ledger/claim logic changed

## Common mistakes

- Adding memory/notes/selfie behavior to group replies because "the DM path has
  it" — that asymmetry is the design, not an oversight.
- Widening `GROUP_ALLOWED_COMMANDS` for a convenient debug command without
  touching the eval — CI goes red and the "fix" temptation is to gut the eval.
- Reasoning about one bot at a time — the hard bugs here are two instances racing
  on the ledger.
- Trusting a hand-enumerated list of "all the write paths" — that approach failed
  twice in review; think in choke points and allowlists.
- Deleting a per-handler `_is_allowed` check as "redundant with `_private_gate`"
  without checking whether the handler is dual-purpose. `_private_gate` explicitly
  excludes `chat_id < 0` ("group_guard's jurisdiction"), and `group_guard` never
  checks the sender's identity — only chat-level `GROUP_ALLOWED_CHATS` membership.
  A handler reachable from both private and group dispatch (`handle_message`) needs
  its own guard even after `_private_gate` ships; the two mechanisms cover different
  halves of the caller space, not the same half twice. Caught by `/code-review`
  before merge on 2026-08-07 (see `.claude/memory/constraints.md` C19) — verifying
  "not called outside dispatch" proves reachability, not which jurisdiction covers
  the call.

## What to report back

Which design sections constrained the change, the state of both group evals, any
boundary deliberately widened (with rationale), and whether `--claim-test` was
run on-device.
