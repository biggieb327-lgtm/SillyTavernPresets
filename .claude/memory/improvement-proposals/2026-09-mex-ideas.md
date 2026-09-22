# Plan — two ideas copied from MEX, 2026-09-22

Decision and rejected alternatives: `.claude/memory/decisions.md`, 2026-09-22 entry.
This file is the build plan. It is not a Routine proposal (see this directory's README);
it does not follow that format because neither item has a recorded failure behind it.
Both are pre-emptive, and that is stated as a cost below, not hidden.

Status (2026-09-22, owner): **item 1 parked** in `.claude/memory/watchlist.md` until its
trigger fires; **item 2 built** (mycelium.md Entry format).

---

## Item 1 — `doc-identifiers-resolve` eval (parked in the watchlist)

**What MEX does:** links a Wiki claim to a code symbol and flags the claim when the
symbol moves, changes, or disappears.

**What we copy:** only the "disappears" half. A backticked code identifier in
`CLAUDE.md` or a `SKILL.md` must still exist in a code file. CLAUDE.md §Vocabulary rule 1
tells sessions to name things by identifier *so a reader can grep them*; this check
proves the grep still finds something.

**Gap it closes:** `claude-md-refs-resolve` and `skill-refs-resolve` check file paths
only. A renamed function (`_handle_group_message`, `update_cmd`) or env var
(`GROUP_CHAIN_DECAY`) named in a skill passes both today.

**Design (prototyped 2026-09-22, not committed):**

- Sources: `CLAUDE.md` + `.claude/skills/*/SKILL.md`. Strip fenced blocks first (the
  2026-07-31 desync lesson in `claude-md-refs-resolve`).
- Candidates: inline backtick tokens that are a bare identifier (optional trailing `()`)
  AND match one of: leading underscore (`_foo`), `*_cmd`, UPPER_SNAKE with an underscore
  (`GROUP_CHAIN_DECAY`), or call-shaped `foo()`. Lowercase plain snake case
  (`current_item`) is deliberately excluded: those are field names a skill defines
  itself, and including them produced false positives in the first probe.
- Resolve with `git grep -qwF <tok> -- '*.py' '*.sh' '*.yml' '*.service' '*.example'
  '*.toml' '*.json' ':!vault' ':!.claude/tools/gate_corpus'`. Code files only: a name
  that survives only in `CHANGELOG.md` or another doc is exactly the drift this should
  catch. `gate_corpus` is excluded because its fixtures are crafted to contain bad
  names (C14).
- An `EXEMPT` set, empty at start, for names a doc mentions in order to say they are gone
  (same escape hatch `claude-md-refs-resolve` uses).
- Parser failure must fail the check: `2>&1`, test the exit status, and fail on
  "0 candidates parsed". Every sibling eval does this; copy the block.

**Prototype numbers:** 80 identifiers checked, 0 unresolved. So the check goes green on
day one with no exemptions, and it has nothing to fix today.

**Acceptance:**

1. Added to `.claude/evals/run-evals.sh` next to `skill-refs-resolve`.
2. Break-test (`add-regression-eval`): add `` `_no_such_function` `` to a skill body, see
   RED naming the skill and token, remove it by re-editing, see GREEN. Then break the
   parser (for example a bad glob) and see RED, not GREEN.
3. `.claude/tools/verify.sh` green; CI green on the branch.
4. Add a `gate_corpus` case only if the check grows a second mode; one mode does not
   need one.

**Cost stated plainly:** no incident has come from this class yet. The precedent for
building it anyway is the 2026-08-23 operational-log row (guard-layer checks built
"proactively — latent, no occurrence"). If the owner prefers to wait for the first
occurrence, the prototype above is enough to rebuild it in minutes; park it in
`.claude/memory/watchlist.md` with the trigger "a doc names an identifier that no longer
exists."

---

## Item 2 — commit SHA on mycelium entries (built 2026-09-22)

**What MEX does:** a Relay records the branch, `HEAD`, and whether the tree was dirty
when it was written, so the receiver can see how far the repo has moved.

**What we copy:** the `HEAD` part only. A mycelium entry's `from:` field names a
`claude/...` branch, and those branches are merged and deleted, so the reference dies.
A short SHA survives. The reader can then run `git log --oneline <sha>..origin/main --
<file the entry is about>` and see whether the entry's claim is still about the current
code. That fits the file's own rule that an entry is a claim to verify, not authority.

**Design:**

- Put the SHA in the **body**, first line, as `` at `abc1234` ``. Do **not** change the
  header: `session-audit.sh` counts headers by grep and `mycelium-format` pins the header
  regex, so a header change needs both edited together, and it buys nothing extra.
- Edit the Protocol and Entry format sections of `.claude/memory/mycelium.md` to say
  "new entries start with `at <short sha>`". Existing entries are not backfilled.
- No eval at first. Add one only if entries are seen without it after the rule exists
  (that is the repo's "recurs twice earns an eval" rule).

**Acceptance:** mycelium.md protocol text updated; `mycelium-format` still green; the
next entry written follows it.

---

## Not copied, and why (so nobody re-derives this)

- **Body-hash drift** (flag a claim when the function body changes): `bot.py` changes
  nearly every session, so nearly every claim would be flagged. A check that noisy gets
  switched off.
- **Code Graph / `mex graph scope`**: indexes are local and never committed, so every
  cloud session rebuilds before use; `rg` over one file is already fast; the benchmark
  behind it is too small to act on.
- **Hub, Members, Relay claiming, Inbox approval flow**: built for several humans
  reviewing in a local browser; this repo has one owner working from a phone.
- **Agent-memory mode / `HEARTBEAT.md`**: the fleet's liveness is systemd plus `/audit`;
  a second heartbeat contract would duplicate it.

## Order

Item 1, then item 2, in one branch. Neither touches `bot.py`, so no `BOT_VERSION` bump or
changelog entry; the delivery gate does not apply. Merge to `main` once `verify.sh` is
green (CLAUDE.md §Git workflow).
