# PLAN — Ground the offline life in relationship memory

**Status:** awaiting owner sign-off (design settled, no code written)
**Author session:** claude/roadmap-priorities-uu9fyp, 2026-09-01
**Base:** `bot.py` v2026-08-31.2
**Scope:** `bot.py` change, fleet-wide, behind kill switches. Not a bot.py split, not a memory-system rework.

---

## 1. Problem (evidenced)

Emily's `/life` arc reads as unrelated to her actual relationship, and threads that
resolved in conversation stay frozen in the arc. Diagnosed on the VPS 2026-09-01.

The arc **contradicts her own memory**. Same Warren thread, two stores:

- **Life arc (`life.txt`, stale):** "Warren's Slack still sits unanswered — four drafts —
  can't decide if it was a test."
- **Recent memory (`recent_summaries`, resolved & real):** "I reached out to Brian
  first… I keep pulling it up like there's a field mark I'm missing. There isn't one.
  It's just a weird thing he did."

The relationship already processed the Warren photo *with the user* and the memory
records it accurately. The arc froze the anxious, unresolved version. Same for "photo
series she's been putting off" — memory correctly knows the activity is **watercolor
painting** + forum photo IDs; the arc mislabeled it into a "photo series" months ago and
locked it.

**The premise we tested and disproved:** the memory function is NOT the weak system. The
VPS dump showed a rich, current 174-word first-person long-term summary + 15 accurate
durable facts for the private chat (promoted 2026-08-31). Memory is the gold standard
here; the **life arc** is the drifting artifact.

## 2. Root cause (code, verified)

The offline-life generators are **isolated from relationship memory**:

- `_maybe_rotate_life_arc` (bot.py:14090) rewrites `life.txt` weekly from *previous arc +
  last 7 `day_*.txt` + `projects.txt`* only. Its rules — "carry over unresolved threads
  in the same words" + "let exactly ONE thing move" — re-entrench any thread verbatim,
  including stale/wrong ones.
- `_generate_life_event` (bot.py:1971) invents daily events from schedule/people/projects/
  arc/recent-events only.

Neither reads `summaries` / `facts` / `recent_summaries` (the per-chat relationship
memory). It's a closed generative loop: the sim reads the arc back in, reinforcing its own
inventions, with no signal from what actually happened with the user. So it drifts into a
self-consistent parallel life that contradicts the shared one.

The **write firewall is already correct** and stays untouched: offline days are stored
tagged `[own-day …]` (`_OWN_DAY_PREFIX`, bot.py:4159) and `memory_block` injects them
under a hard "NOT shared memories… never recall as things you did with the user" rule
(invariants #10/#17). The dump confirmed the tagging works.

## 3. Decision to sign off on

**The offline life becomes subordinate to memory: it READS relationship memory for
grounding; it never WRITES into it.** Owner answers this session: grounded continuity;
a mixture of both when the two touch.

- **Read direction (new):** the life generators read the owner chat's long-term summary +
  durable facts + recent summary, and must not contradict resolved/known threads.
- **Write direction (unchanged):** arc and events still land only in the `[own-day]`
  firewalled channel. No arc/event text is ever written to `summaries`/`facts`.
- **Mixture:** a shared thread (Warren, photos) reflects the *resolved* state from memory;
  the sim frames its own-world activity (work, art, forum, cat) as its own.

This will be recorded in `.claude/memory/decisions.md` on approval (what won: arc
subordinate to memory; what it beat: rebuild-memory, and grounded-both-directions).

## 4. Changes (exact)

All in `bot.py`. Selector for "which memory to ground against" is `get_owner()`
(bot.py:4868) — the instance's primary chat. The memory dicts (`summaries`, `facts`,
`recent_summaries`) are module-level (bot.py:3823-3827), readable from these functions.

### 4.1 New helper: `_relationship_grounding() -> str`
One compact, read-only block built from the owner chat's memory:
- `summaries.get(owner)` — the ≤200-word durable narrative (truncate defensively, e.g.
  ~600 chars).
- up to N durable `facts.get(owner)` (real facts only via `_split_own_day_facts`, e.g.
  first 8), **excluding own-day entries**.
- `recent_summaries.get(owner)` — so freshly-resolved threads (the Warren resolution) are
  visible.
Returns "" when there's no owner or no memory (degrades to today's behavior).

**Domain guard (risk #6.1):** the block is labelled as *context for consistency, not
material to restate* — "Here is how she remembers things with {user} and what they've
actually talked about. Keep her offline life consistent with this — don't contradict
what's resolved or known — but this is background, not events to narrate as her own day.
Keep offline events in her own world (work, art, forum, people, cat), not the private
specifics of the relationship." This keeps intimate/NSFW memory content from surfacing in
"here's my day" events while still fixing the contradiction problem.

### 4.2 `_generate_life_event` — add grounding
Insert `_relationship_grounding()` into `parts` (bot.py:1983-1990 region), and add one
line to the system prompt: the event must not contradict what she and the user have
actually discussed. **Zero new LLM calls** — same single call, larger prompt.

### 4.3 `_maybe_rotate_life_arc` — add grounding + stop the freeze
- Add `_relationship_grounding()` to the rotation prompt (bot.py:14119-14140 region).
- Amend the rules so a thread that is **resolved or contradicted by memory** must be
  updated or dropped, not carried verbatim. Keep "one thing moves" for genuinely
  unresolved threads; the change is that memory can force a thread to move.
**Zero new LLM calls** — same single call.

### 4.4 Secondary cleanups (same release; same subsystem — `fix-the-class`)
- **Own-day trim:** `_rotate_day_context` stores `day_ctx[:300]` verbatim — multi-event,
  truncated mid-word (seen in the dump). Store a clean single-line note (first event /
  first line, whole sentences) instead.
- **Life-event dedup:** `_append_life_event` (bot.py:1937) has no dedup; `life_events.txt`
  showed the identical "Warren accidentally replied 'that's great'…" 5×. Add a guard that
  drops a new event equal/near-equal to a recent one. (Also confirm the generator's
  anti-repeat context is actually being passed — it is, so the guard is the belt-and-braces
  fix.)
- **`Whiske` truncation:** minor generation artifact in events; note only, fix if trivial.

### 4.5 Kill switch (invariant #16)
New `LIFE_GROUNDING = _env_bool("LIFE_GROUNDING", True)` — default on, `=0` disables the
grounding read without a redeploy, restoring exactly today's isolated behavior. The
secondary cleanups (4.4) ride the existing `LIFE_ROTATE`/`LIFE_SIM_ENABLED` switches.

## 5. Invariants & docs
- **#3 LLM-call budget:** satisfied — no new calls; only larger prompts on existing calls.
  Note the modest token increase (grounding block ~800-1000 tokens on the twice-daily
  event call + weekly rotation; both off the reply path, so no reply latency).
- **#10/#17 memory provenance:** write firewall untouched; grounding is read-only; own-day
  tagging preserved. This is the highest-attention area in review.
- **#16 kill switch:** `LIFE_GROUNDING` default-on + off-switch.
- `group-chat-changes`: `_rotate_day_context` uses `get_owner()` (private), not group
  paths; the group chat (negative id) has no long-term promotion and is out of scope — but
  load the skill and confirm no group path is touched before shipping.
- BOT_VERSION bump + `CHANGELOG.md` entry (root cause first) — delivery gate enforces.

## 6. Risks & guards
1. **Intimate memory leaking into own-world events** — guarded by 4.1's domain instruction
   (offline events stay in work/art/forum/cat domain; relationship memory is
   consistency-context only). **Validate explicitly** in the live check (§8).
2. **Over-correction** — the arc collapsing into a summary of the relationship instead of
   keeping her own autonomous life. Guard: grounding is "don't contradict," not "be about
   the user"; keep the own-world domain instruction.
3. **Token cost** — bounded by truncating the grounding block; both calls are off the
   reply path.
4. **No owner set** (`get_owner()` is None) — `_relationship_grounding()` returns "";
   behavior identical to today.

## 7. Build order
1. Commit nothing until read-first done: re-read the four functions + `memory_block` +
   `get_owner` in full (repo-change-control).
2. Add `_relationship_grounding()` + `LIFE_GROUNDING`; wire into `_generate_life_event`
   and `_maybe_rotate_life_arc`.
3. Secondary cleanups (own-day trim, event dedup).
4. Tests (§8), break-tested RED first.
5. BOT_VERSION bump + changelog.
6. `.claude/tools/verify.sh` (full, not `--quick`).
7. Merge to main; hand off fleet deploy (`deploy-and-verify-fleet`).

## 8. Test plan
- **Delivery-gate requirement:** a test that *calls* each touched `*_cmd`/function, not
  one that asserts on source text. Here: unit-test `_relationship_grounding()` (owner set
  vs. none vs. empty memory), and tests that **call** `_generate_life_event` and
  `_maybe_rotate_life_arc` with a stub `call_nanogpt`, asserting the grounding block is
  present in the prompt when `LIFE_GROUNDING=1` and absent when `=0`. Break-test each RED.
- Dedup test: `_append_life_event` twice with the same line → stored once.
- Own-day trim test: a multi-line `day.txt` → single clean line stored.
- `bash .claude/evals/run-evals.sh` green (incl. secret scan, BOT_VERSION↔changelog).
- **Live done-when (one bot, real day):** after deploy to Emily, reset her arc (§9), let
  one rotation cycle run, and confirm (a) the arc no longer contradicts the resolved
  Warren/photo threads, (b) no intimate content surfaces in own-world events, (c)
  `life_events.txt` stops repeating. Same-bot before/after, not a cross-character compare.

## 9. Immediate remediation (independent of the code change)
Owner can do now on the VPS, no deploy needed:
- `/life <corrected arc>` to reset Emily's arc to match the real relationship.
- Truncate the repeating `life_events.txt` (drop the duplicate Warren lines).

## 10. Fleet note
Every instance runs the same isolated arc loop, so nora/bonnie/cass/jules/priya/marcus are
drifting the same way against their own (likely-fine) memories. The fix is fleet-wide by
construction (default-on). Spot-check 1-2 other instances' `life.txt` vs. their long-term
memory after deploy to confirm the class is closed (`fix-the-class`).

## 11. Open questions for owner
1. **Grounding source depth:** long-term summary + recent summary + N durable facts (this
   plan), or long-term summary only (leaner, less current)? Recent summary is what carries
   *just-resolved* threads, so I recommend including it.
2. **Arc cadence:** keep weekly `LIFE_ROTATE_DAYS=7`, or slow it now that the arc will be
   memory-corrected (drift is less likely, so weekly is fine — no change proposed)?
3. **Dedup aggressiveness:** exact-match only, or near-duplicate (normalized) — the Warren
   case was verbatim, so exact-match closes it; near-dup is optional.
