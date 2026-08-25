---
name: log-decision
description: Record a project-changing decision — what won, what it beat, and why — in .claude/memory/decisions.md. Load whenever you (or the owner, or a subagent you're relaying) settle a choice among real alternatives that changes the project: architecture, a contract, the deploy or memory layer, a default that ships, a standing will/won't, or an approach ruled out. Not for routine implementation with one obvious path.
---

# Log the decision

The code records *what* we did. It almost never records *why we did it this way and not the
other way* — the alternatives we weighed, the one we ruled out, the reason the winner won.
That rationale used to scatter across the changelog, the audit files, design docs, commit
messages, and chats nobody kept, so a later session would re-open a settled question or undo a
deliberate choice because the code alone didn't defend it. `.claude/memory/decisions.md` is the
one place that answers it. This skill is the standing obligation to write to it.

## When a decision qualifies

Log it when **all three** hold:

1. **There were real alternatives.** A fork with more than one defensible path — not one
   obvious way to do the thing.
2. **It changes the project.** Architecture, a file's or system's contract, the deploy or
   memory layer, a default that ships to the fleet, a standing "we will / won't do X", or an
   approach **ruled out** so nobody wastes a session re-attempting it.
3. **The rationale outlives the diff.** A future session reading only the code would not
   recover *why*, and might reasonably undo it.

If you can't say what you chose it *over*, it probably isn't a decision — it's an
implementation detail. Don't log those.

## When NOT to log

- A routine implementation choice with one obvious path → nothing, or a code comment.
- A system failure and its fix → `operational-log.md` (+ `CHANGELOG.md` for a bot.py change).
- A mistake you made doing the work → `constraints.md`.
- A rule everyone must now follow → `CLAUDE.md` (and if the rule came from a decision, leave
  the decision entry as the record of *why* the rule exists).
- A transient heads-up for the next session → `mycelium.md`.

## How to log it

1. **Write the entry at the top of `.claude/memory/decisions.md`** (newest first), using the
   format in that file's header:

   ```
   ### YYYY-MM-DD | <short decision title> | status: current
   **Decided:** what won, in one line.
   **Over:** each alternative considered, and why it lost.
   **Why:** the deciding reason — the thing that made the winner win.
   **By:** owner / a session / an eval — and how it was settled.
   **Detail:** link to the fuller record, or `—` if this entry is the whole record.
   ```

2. **Record the rejected options as carefully as the winner.** The record of what was ruled
   out is the whole point — it is what stops the re-attempt. An entry with an empty **Over:**
   is a changelog line in the wrong file.

3. **Use plain words and the repo's own terms** (CLAUDE.md §Vocabulary). Name the env var,
   file, or command verbatim; don't coin a label for the decision.

4. **A subagent's decision is logged by the main session.** Agents surface choices in their
   own shorthand; translate it into repo terms and code identifiers *before* writing the entry
   (CLAUDE.md §Vocabulary #4). The session that made or ratified the decision owns the entry.

5. **Superseding, not deleting.** If a later decision reverses an earlier one, add a new
   `status: current` entry that links back, and change the old entry's header to
   `status: superseded`. Never delete the old one — the record of the reversal is worth as much
   as the reversal. This is the same append-don't-erase rule mycelium uses.

## Verify

The `decisions-format` eval (`.claude/evals/run-evals.sh`) fails if any `### 20…` header line
does not end `| status: current` or `| status: superseded`, so a malformed entry drops out of
the log silently → the eval catches it. Run the suite before calling the change done:

```bash
.claude/evals/run-evals.sh
```

## Where this is enforced

- **`CLAUDE.md` → Working principles** carries the standing rule ("Log project-changing
  decisions").
- **`session-debrief`** asks, at the natural stopping point, whether the session settled a
  decision that isn't yet logged — the behavioral backstop, since no hook can read intent.
- **`decisions-format`** guards the file's shape, not the behavior. Logging the decision at all
  is on you; this skill is why you know to.
