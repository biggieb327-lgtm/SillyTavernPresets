# Watchlist — low-level observations that aren't a problem yet

The parking lot for the small stuff: a smell, a latent gap, a "keep an eye on this" that
is **not yet** worth a failure record, a constraint, or a finding — but would be cheap to
lose and expensive to rediscover.

## The test — which file does this belong in?

Ask in this order; the first yes wins, and it is almost never this file:

| If… | it goes to |
|---|---|
| the **system** failed — a bot, a deploy, the fleet | `operational-log.md` |
| the **work** went wrong — our wrong command, premature "done", theory-as-fact | `constraints.md` |
| it's a **message to the next session** — a heads-up, a dead end, a handoff | `mycelium.md` |
| it's a durable **finding or decision** | Notion Fleet Knowledge Base |
| **none of the above — it hasn't happened, it just might** | **here** |

If you can name a concrete occurrence with a date, it is not a watch item any more — it has
graduated (below). A watch item is the state *before* the first occurrence.

## Every item names what would graduate it

The whole value of this file is that items leave it. Each entry states the **trigger** that
turns it into something real — the observation that would move it to an eval, a constraint,
or the operational log — or the condition under which it is simply **dismissed**. An item
with no graduation trigger is an opinion; write the trigger or don't write the item.

## Lifecycle

- **Reviewed at `session-debrief`**, where the "what earns a mechanism" decision already
  lives. A watch item whose trigger has now fired is a debrief output: promote it.
- **Pruned** when dismissed, or when it has graduated and the real record exists elsewhere.
  A watch item is never the only copy of anything load-bearing (same rule as a mycelium
  dead end).
- `session-audit.sh` prints the open count at startup so the list stays seen, not the items
  themselves — this file is consulted, not nagged.

## Entry format

```
### YYYY-MM-DD — one-line title | status: open
What was observed (one or two sentences). Why it is not a problem yet.
**Graduates when:** the concrete trigger that would move it out of this file, and to where.
```

`status: open` | `watching` (seen again, still sub-threshold) | `graduated` | `dismissed`.
Newest first. The header shape is what `session-audit.sh` counts — keep it exact.

---

## Items

### 2026-09-01 — grounded offline life can carry owner-private memory into group/non-owner chats | status: open
`v2026-09-01.1` made `_generate_life_event` / `_maybe_rotate_life_arc` read the owner's relationship
memory (intimate specifics included, for an NSFW companion) for grounding. Their outputs
(`life_events.txt`, `life.txt`) are injected into every chat, including groups (no owner-gate, predates
this change). The guard against an owner-private detail surfacing in a group is prompt-only
("consistency context, do not restate") + the solo-domain event scoping. Not a problem yet: no leak
observed, and the event prompt is strongly scoped to her own-world domain. Owner accepted the residual
(decisions.md 2026-09-01) rather than gate the injection.
**Graduates when:** any owner-private/relationship detail is seen in a group or non-owner chat — then
it's an operational-log incident, and the fix is to gate `life.txt`/`life_events.txt` injection to the
owner chat (`get_owner()`), which needs `group-chat-changes`. Immediate mitigation meanwhile:
`LIFE_GROUNDING=0`.

### 2026-08-29 — risk-guard.sh matches `git checkout <dirty-file>` inside heredoc/quoted bodies, not just executable positions | status: open
While committing the debrief, `risk-guard.sh` blocked `git commit -F - <<EOF … EOF` because
the C15 description *inside the commit message* contained the literal string of the forbidden
command over a then-dirty file. The block is content-blind: it scans the whole Bash command
text and cannot tell a real checkout from the same words quoted in a message body. Cost this
session was one reword — cheap. It is the correct trade (a guard that under-blocks is the
dangerous one), and it fired 100% correctly on the *actual* checkout attempt earlier the same
session, so this is a precision note, not a demand to loosen it.
**Graduates when:** the false positive blocks real work more than trivially — e.g. a session
has to fight it repeatedly, or it blocks a commit whose message legitimately must quote the
command — at which point narrow the match to executable positions (skip heredoc/quoted bodies)
and break-test in a throwaway repo. Until then, rewording the message is the right move and no
change is warranted.
**Recurred 2026-08-31 (different matcher, same root cause):** the `git add … .env` staging
matcher (not the C15 checkout matcher) blocked a `git commit -F - <<EOF` whose message body
contained the literal `git add .env` as prose. Same content-blind whole-command scan; the class
has now bitten two of risk-guard's matchers. Workaround was again cheap — wrote the message to a
file and used `git commit -F <file>`. Still under the graduation bar (rewording sufficed), but
the two-matcher spread is the argument for the eventual fix: strip heredoc + `-F` message bodies
before matching, then break-test both matchers.
**Same class, a third guard (2026-08-31):** `theory-guard.sh` fired twice on chat prose that
*quoted or retrospectively described* a behavioral claim ("… returns retired …") rather than
asserting it fresh — the claim was already proven by an executed, pasted pytest run. Same
content-blind root cause (a guard scanning text it cannot tell is a live claim vs. a mention);
now spanning risk-guard (commit-message bodies) and theory-guard (retrospective narrative). The
class fix is the same shape: a guard's matcher should exempt quoted/retrospective context, or
the author must cite the already-run evidence inline. Cost is trivial each time; logged for the
pattern, not as a demand to loosen either guard.
`shell-scripts-parse` globbed only `.claude/hooks/*.sh` and `telegram-companion-bot/*.sh`, so
no tool shell script was `bash -n`'d; `tools/prose-constraint-check.sh` was run by no eval
either, so its syntax was checked by nothing.
**Graduated 2026-08-23:** `shell-scripts-parse` now globs `.claude/tools/*.sh` too, and
`hook-py-refs-exist` was generalised to `hook-refs-exist` — it checks every
`.claude/{hooks,tools}/*.{py,sh}` a wrapper invokes exists, so a hook→tool.sh path is now
existence-checked as well as the .py paths. Break-tested. Kept for the record; prune at the
next hygiene pass.

### 2026-08-23 — startup context is creeping back up | status: open
`session-audit.sh` output measured 1,880 bytes today, up from the ~1,668 the 2026-08-21 trim
brought it to, because this session added the MECHANISM REVIEW and WATCHLIST lines. The
2026-08-21 mycelium note warned in as many words: "re-measure if the hook grows — the same
drift comes back one echo at a time." Two useful lines are worth 212 bytes; the point is the
direction, not this number.
**Graduates when:** `bash .claude/hooks/session-audit.sh | wc -c` passes ~2,436 (the measured
"past the point of being read" size that triggered the last trim), or the count/review lines
start pushing the operational lines out of what gets read first — then consolidate to
counting-plus-top-N.

### 2026-08-23 — debrief-nudge cadence is still unmeasured | status: open
`debrief-nudge.sh` (built 2026-08-11) is meant to produce roughly one `debrief-log.md` row per
working session, but the oplog row that shipped it says a distribution can't be judged from one
row and deliberately set no threshold. Startup still shows single-digit "commits since last
debrief", so it's plausibly firing — but nobody has checked the log has grown as designed.
**Graduates when:** `debrief-log.md` has enough rows to show the per-session rate (promote to a
cadence check or threshold in session-audit), OR a stretch of working sessions shows no new row
(the nudge isn't firing — an operational-log incident, the dormancy shape C-class).

### 2026-08-23 — the MECHANISM REVIEW startup line could grow into wallpaper | status: graduated
The new `session-audit.sh` MECHANISM REVIEW line names every guarded constraint whose
mistake recurred after its guard shipped — today six (C1, C3, C7, C8, C13, C14), and it
will keep naming roughly that set every session because those recurrences are in the
prose-only halves that will never get a mechanism. Six is legible. But this repo has
already been burned once by a startup line that grew until "fifteen names is past the point
of being read" (operational-log 2026-08-21), so a line that only ever grows is worth
watching.
**Graduates when:** the list reaches ~10 names, or a session is observed skipping past it —
at which point it should switch to counting-plus-top-N-by-seen, the same shape the PROSE
ONLY and OVERDUE lines already use. Until then, no change; a fix now would be speculative.
**Graduated 2026-08-31:** at 9 names (its trigger), reworked rather than deferred — the line
now shows only recurrences *since the last debrief* (fresh/unreviewed) and collapses the
already-reviewed ones to a count, so it goes quiet unless a guard actually fails again. Decision
logged in `decisions.md` (2026-08-31); pinned by the extended `mechanism-recurrence-surfaced`
eval. Prune at the next hygiene pass.
