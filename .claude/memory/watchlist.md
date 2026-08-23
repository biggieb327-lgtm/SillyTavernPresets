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

### 2026-08-23 — the MECHANISM REVIEW startup line could grow into wallpaper | status: open
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
