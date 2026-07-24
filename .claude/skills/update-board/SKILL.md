---
name: update-board
description: Mark a roadmap task done on the Mission Control board after completing it. Load whenever a roadmap item ships or an on-device migration completes.
---

# Update the Mission Control board

When a roadmap step completes (code shipped, migration done, doc written, cleanup
finished), reflect it on the board so the map stays current.

## Procedure

1. **Identify the task id.** Read `botfleet.seed.json` and find the task whose title
   matches the completed work. If no task matches, skip — the board only tracks items
   from `ROADMAP.md` §1.2 forward (earlier tracks are already shipped).

2. **Edit the seed** (`botfleet.seed.json`):
   - Set `"status": "done"` on the completed task.
   - Remove `"doing": true` if present.
   - If the next task in the chain is now unblocked and actively starting, add
     `"doing": true` to it.
   - Bump `"rev"` by 1 and update `"updated"` to today's date.

3. **Rebuild board.html:**
   ```bash
   node build.js botfleet.seed.json > /tmp/board-rebuild.html && cp /tmp/board-rebuild.html board.html
   ```
   Never `node build.js … > board.html` directly — the redirect truncates the file
   before build.js reads it.

4. **Run the smoke test:**
   ```bash
   node tests/smoke.js
   ```
   All checks must pass (valid deps, acyclic graph, unique ids).

5. **Commit** the seed + board.html together, in the same commit as the work that
   closed the task (or immediately after if the work was on-device / reported by the
   user). Commit message mentions the board update, e.g.:
   `"… + mark m-bonnie done on the board"`.

## When the user reports an on-device step done

Migrations (m-bonnie, m-emily, etc.) and on-device cleanup are done by the user, not
by Claude. When the user says one is complete:

1. Follow steps 1–5 above.
2. If the completed migration unblocks Claude-owned tasks (docs, features), note
   what's now ready.

## Adding or changing tasks

If the roadmap changes (new item, re-sequencing, scope change), edit the seed to
match, rebuild, test. Keep task ids stable — device-side localStorage deltas reference
them, so renaming an id orphans any taps the user made in the browser.
