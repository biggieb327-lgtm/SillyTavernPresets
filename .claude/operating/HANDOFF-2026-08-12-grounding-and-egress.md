# Handoff — memory-claim grounding, and the egress allowlist

**Written 2026-08-12.** Two independent pieces of work. Part A is a `bot.py` change;
Part B is environment configuration plus the repo edits it unblocks. They share no
code — do them in either order, or in separate sessions.

## How to read this file

Same authority order as `HANDOFF-2026-08-08.md`, and for the same reason:

1. Runtime output (`=== STARTUP AUDIT ===`, `bash .claude/tools/verify.sh`) — always wins.
2. `CLAUDE.md`, `.claude/skills/skill-router/SKILL.md`, the skill bodies themselves.
3. This file.

Every line number below was checked on 2026-08-12 against `bot.py` at 16,159 lines.
`bot.py` changes constantly — **re-grep before editing**, do not trust an offset.

### Verified state at writing

| Thing | Value | How checked |
|---|---|---|
| `BOT_VERSION` | `2026-08-10.12` (`bot.py:100`) | `grep -n '^BOT_VERSION'` |
| `bot.py` | 16,159 lines | `wc -l` |
| `tests/test_pure.py` | 1,245 tests | `grep -c 'def test_'` |
| Live Routines | 5 (`practice-scan-weekly` added 2026-08-11) | `.claude/operating/routines.md` |
| Actor version | 0.14 | `idea-scraper-actor/.actor/actor.json` |

Not verified: eval suite pass count, pytest total. Run `bash .claude/tools/verify.sh`
yourself before and after — a baseline you did not observe is not a baseline.

---

# Part A — the grounding guard checks the quote, never the claim

**Origin:** `practice-scan-weekly`, 2026-08-12 —
`.claude/memory/practice-scan/2026-08-12.md` idea 1. The pointer was a Substack
teaser; the primary source is Ragas's `Faithfulness` metric. Read that file first;
this section is the implementation plan, not the argument for it.

## The gap (verified, not inferred)

`_quote_grounded` (`bot.py:2573`) is a substring test and nothing more:

```python
def _quote_grounded(quote: str, user_lines: list[str]) -> bool:
    """True if quote is a substring of any user line (case/whitespace-normalized)."""
```

Two callers, both in the extraction path:

* `bot.py:4768` → `_count_error("note_ungrounded")` on failure
* `bot.py:4808` → `_count_error("memory_ungrounded")` on failure

When it passes (`bot.py:4810`ff), the quote is kept alongside the claim:

```python
mem_meta = {
    "ts": time.time(), "chat_id": chat_id, "origin": "auto",
    "confidence": conf, "source": quote[:300],
}
```

So the guard establishes that **the evidence is real**. It never establishes that
**the claim follows from the evidence**. Those are different properties and only the
first is enforced.

Concretely: the user says *"I might try that new ramen place sometime."* The model
stores memory *"User loves ramen and eats it weekly"* with `memory_quote` =
*"try that new ramen place"*. The quote is a verbatim substring, so `_quote_grounded`
returns True, `memory_ungrounded` never fires, and a fabricated preference enters
`memories.txt` with a real quote attached to it. Nothing downstream can distinguish
that from a well-founded memory.

## Why the weekly audit is the right place for the fix

Everything needed already exists:

* `MEMORY_AUDIT` (`bot.py:1023`–`1027`, loop at `bot.py:1111`) — a cheap-model weekly
  pass over `memories.txt`.
* Its proposals route through the existing `/reviewmem` queue; the owner approves
  every mutation, and `_memory_replace` does the write.
* `memory_meta.json` (`MEMORY_META_FILE`, `bot.py:1012`) already stores `source` — the
  original grounding quote — next to each stored claim.

So this is **one more finding type in an existing pass**, not a new subsystem, and it
runs off the message path where a model call is affordable.

## The change

1. **`_parse_audit_findings` (`bot.py:~1160`)** — currently accepts
   `ftype in ("contradiction", "superseded", "stale")` and
   `action in ("delete", "merge")`. Add `"unsupported"`.

   Restrict it to `action == "delete"`: merging an unsupported claim into another
   entry propagates it rather than removing it. If you want a softer outcome, add a
   distinct action rather than reusing `merge` — but decide deliberately, and pin
   whichever you choose with a test.

2. **The audit prompt** must receive each entry's stored `source` alongside the entry
   text, or the model has nothing to judge entailment against. This is the crux of the
   whole change.

3. **Entries with no `source` must be skipped, not flagged.** Manually-added memories
   (`origin != "auto"`, `/remember`, owner edits) have no grounding quote by design.
   Flagging them as unsupported would propose deleting exactly the memories the owner
   entered deliberately — the worst possible failure mode for this feature.

## Before you write any of it

**Verify how `_memory_meta` keys map to `memories.txt` lines.** I did not, and Part A
depends on it entirely. `_parse_audit_findings` works in 1-based line indices into
`entries`; `_memory_meta` is a dict keyed by something else (`bot.py:1016`, `1057`).
If entries cannot be reliably paired with their meta — e.g. after a `_memory_replace`
renumbers lines — then **that mapping is the blocker**, and no prompt engineering
fixes it. Establish the pairing first; if it is unreliable, stop and report rather
than shipping a feature that silently mis-attributes quotes to claims.

## The eval

Both target functions already have pinned tests in
`telegram-companion-bot/tests/test_pure.py` — **extend those classes, do not add
files**:

* `_quote_grounded` — `tests/test_pure.py:685`–`713`
* `_parse_audit_findings` — `tests/test_pure.py:1665`–`1699`

Minimum cases:

* a finding with `type: "unsupported"`, `action: "delete"` is accepted and maps to the
  right entry
* `type: "unsupported"` with `action: "merge"` is dropped (assuming delete-only)
* an entry with no stored `source` is never proposed as unsupported

If you factor the entailment judgement into a pure helper, pin it with the
ramen-shaped case above: real quote, unsupported claim, must be flagged.

## Procedure

**Load `repo-change-control` before editing `bot.py`** — this is a fleet-reaching
change, so it takes the full path: read `CHANGELOG.md` entries touching memory and the
audit first (step 1 is non-negotiable and has caught naive fixes before), load
`bot-code-invariants` and keep it open, bump `BOT_VERSION` (`bot.py:100`), write the
changelog entry root-cause-first, get `bash .claude/tools/verify.sh` green, merge to
`main` by pushing the branch, then hand the owner the `vps-sync.sh` deploy per
instance. Your job ends at "merged, green, deploy instructions given."

## What not to do

* **Do not put entailment checking inside `_quote_grounded`.** It is a pure function on
  the message hot path with ten pinned tests. An LLM call there puts a model round-trip
  in the reply path for every extraction.
* **Do not auto-delete anything.** Every audit proposal goes through `/reviewmem` and
  the owner's ok/no. That posture is the reason this feature is safe to add at all.
* **Do not make the write-time guard stricter instead.** Rejecting at extraction time
  trades a silent-bad-memory problem for a silent-lost-memory problem, with no human in
  the loop. The audit has the owner in the loop by construction.

---

# Part B — the egress allowlist

## What this is about

Fired Routine sessions and this repo's research agents keep hitting a network policy
that blocks primary sources. Two concrete costs, both already paid:

**1. Two `hygiene-check-weekly` checks were deleted as impossible.** Per
`routines.md` (2026-07-29): CI state on `main` needs the GitHub REST API, and
Routine↔`routines.md` sync needs `list_triggers` — *"direct `api.github.com` calls are
refused by the agent proxy with 403 whether or not a token is sent."* Both checks were
removed rather than left lying.

**2. The 2026-08-12 practice-scan quoted a third-party mirror as a primary source.**
`openai.com` was blocked, so idea 2 cites
`raw.githubusercontent.com/celesteanders/harness` — a stranger's markdown file
asserting what OpenAI wrote. The session was transparent about the substitution, which
is the right instinct, but that is not verification. The evidence rule bans quoting a
`WebFetch` paraphrase and says nothing about unofficial mirrors; the gap is real.

## Measured from this session's container, 2026-08-12

| Host | Result |
|---|---|
| `api.github.com` | **200** |
| `www.reddit.com` | 200 |
| `api.apify.com` | 200 (404 on `/`, no root route — tunnel fine) |
| `raw.githubusercontent.com` | reachable (the practice-scan run used it) |
| `docs.apify.com` | CONNECT tunnel failed, 403 |
| `substack.com` | CONNECT tunnel failed, 403 |
| `support.reddithelp.com` | blocked |
| `openai.com`, `docs.ragas.io` | blocked (reported by the fired session) |

**`api.github.com` returning 200 here directly contradicts `routines.md`'s
2026-07-29 note.** Do not resolve that by believing either source. The likely
explanations are that the policy changed, or that interactive and fired sessions get
different policies — and which one it is decides whether the two deleted checks can
come back. **Measure it from a fired session before changing anything.**

## The fix

claude.ai/code → Environments → **SillyTavernPresets**
(`env_013KxczVfcQicP87yAYmHtKj`) → Network access → allowed domains.

Candidates, in priority order: `api.github.com`, `github.com`,
`raw.githubusercontent.com`, `openai.com`, `docs.ragas.io`, `docs.apify.com`,
`substack.com`. Keep *"include default list of common package managers"* checked.

## Verify from a fired session, not an interactive one

This distinction is the entire point — the deleted checks died because fired sessions
differ from interactive ones, and an interactive `curl` proves nothing about them.
Cheapest honest test: create a one-shot Routine (`run_once_at`, a few minutes out,
`create_new_session_on_fire: true`, same environment) whose whole prompt is to curl
each host and report status codes, then delete it. Record the results in
`routines.md` next to the 2026-07-29 note rather than overwriting it.

## Follow-on repo edits — only after that verification

* **Restore `hygiene-check-weekly`'s CI check** if `api.github.com` proves reachable
  from a fired session. Its removal note in `routines.md` must be updated in the same
  session as the live prompt, per that file's own mirroring rule.
* **Tighten `practice-scan-weekly`'s evidence rule**: an unofficial mirror is not a
  primary source. If the primary source is unreachable, the idea should be labelled
  *"unverified — host blocked by egress policy"* rather than quoting a third party.
  `research-scout`'s contract already says exactly this — *"A blocked host means the
  answer is 'unverified — host blocked by egress policy.' Never fill that gap with a
  WebFetch summary"* — so the practice-scan rule should inherit it rather than invent
  its own.

## Three vestigial lines to fix in the same edit

`practice-scan-weekly`'s prompt carries residue from the abandoned subscriber-feed
approach. Harmless today, but they are the kind of thing that makes a future session
re-derive a settled question — which this repo has now done three times on Reddit and
Substack access:

* Step 2 opens *"This Routine has no WebSearch fallback on purpose"*, which reads as a
  contradiction of step 4 requiring WebSearch. Both are true — banned as a *substitute
  for unreachable Apify*, required as a *deepening step* — but the prompt never says so;
  only the `routines.md` metadata bullet does.
* *"An empty result from a live secret is a normal quiet week"* — there is no secret.
* Step 4's FULL TEXT branch is unreachable: it fires only when a subscriber feed is
  configured, and Substack issues none.

---

# Open questions

1. **`memory_meta` ↔ `memories.txt` pairing** — unverified, and Part A cannot ship
   without it. Establish it first.
2. **`api.github.com` reachability from a fired session** — two sources disagree.
   Measure; do not pick a side.
3. **Should `unsupported` be delete-only**, or does it want its own softer action?
   A judgement call for the owner, not one to settle by implementation default.
