# Mycelium — cross-session messages

Sessions start cold. This file is the warm handshake: messages left by one session
for the ones that follow. Not failures (operational log), not mistakes (constraints),
not standing rules (CLAUDE.md). **Messages.**

## What belongs here

- A finding out of scope for your task but worth knowing
- A dead end that would cost the next session an hour to re-discover
- An owner preference or decision not yet codified in CLAUDE.md
- Partial work on a branch, with where you left off and what's next
- Fleet state worth watching — not an incident, just a heads-up
- A question you couldn't answer that the next session might

## What does NOT belong here

- System failures → `operational-log.md`
- Your own mistakes → `constraints.md`
- Standing rules → `CLAUDE.md`
- Durable findings/decisions → Notion Fleet Knowledge Base
- Full incident detail → `CHANGELOG.md`

If an entry here keeps getting copied forward because it matters permanently,
promote it: CLAUDE.md for rules, Notion for findings, a skill for procedures.

## Protocol

1. **Read open entries before non-trivial work.** `session-audit.sh` surfaces the count;
   the entries themselves are here.
2. **Write an entry when you learn something the next session needs.** Keep it short —
   a sentence or two, not a report. The value is the signal, not the detail.
3. **Acknowledge entries you've read.** Change `open` → `ack` (noted, no action needed)
   or `done` (acted on — say how in a one-liner). An entry sitting `open` across three
   sessions is either stale or important; figure out which.
4. **Prune during context-librarian passes.** `done` older than 14 days can go. `ack`
   older than 30 days can go. `open` entries don't age out — they wait.

## Entry format

```
### YYYY-MM-DD | from: <context> | to: <audience> | status: open
One or two sentences. What you found, why it matters, what the next session
should do (or not do) with it.
```

- **from** — branch name, task description, or just the date. Enough to find the
  session's work in the commit history if needed.
- **to** — who it's for. `—` means anyone. A topic like `bot.py work` or
  `character review` means the next session touching that area.
- **status** — `open` (unread), `ack` (read, no action), `done` (acted on).

Newest first, same as the operational log.

---

## Entries

### 2026-08-21 | from: claude/reddit-post-review-3oe3rx | to: — | status: open
r/claudexplorers post describes a system of 13 AI "seats" with file-based continuity
(journals, a shared-folder post office, grief protocols for session death). Architecture
is strikingly parallel to this repo's .claude/ infrastructure. Owner asked whether we do
the same thing — yes, in mechanism, different in purpose. This file is one outcome of
that comparison: the poster's "mycelium" pattern, made concrete here.
