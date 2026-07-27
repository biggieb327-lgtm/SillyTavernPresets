---
name: fix-the-class
description: After fixing a bug, find the OTHER instances of it before calling it done. Load whenever a fix is about to ship, or when a check/eval is being written. Encodes the 2026-07-25 finding that every point fix that day was actually a class.
---

# Fix the class, not the instance

On 2026-07-25 four separate "one-line fixes" were each shipped, then found to be
classes:

| shipped as one fix | actual scope |
|---|---|
| `/audit` sent arbitrary text through Markdown | 13 more sites, 11 commands |
| `perform_self_update` raced on the shared code dir | `vps-sync.sh` has the same race |
| "no graceful-stop line = SIGKILL" corrected in 4 docs | still asserted in 4 more places |
| `BOT_TIMEZONE` didn't set the timezone | whole-file env/doc drift, 72 vars |

Each was found by a scanner written in the moment. Those scanners are now
`.claude/tools/sweep.py`. **The rework cost of not doing this was most of a session.**

## When NOT to use

- Pure content edits (cards, presets, docs with no behavioural claim).
- A fix whose mechanism genuinely cannot exist elsewhere — but say *why* out loud
  before skipping; "it's just one line" is not a reason.

## Procedure

1. **Before declaring any fix done, name the class in one sentence.** Not "fixed
   `/audit`" but *"a command formats arbitrary data into a parser that can reject it."*
   If you can't write that sentence, you don't yet know what you fixed.

2. **Sweep for other instances mechanically, not by memory.**
   ```bash
   python3 .claude/tools/sweep.py              # all scanners
   python3 .claude/tools/sweep.py --list       # what each one looks for
   ```
   Exit code 1 = candidates found. Findings are **candidates, not defects** — each
   scanner prints why a hit may be benign. The reviewer decides; the scanner only
   guarantees the reviewer *sees* every site.

   If the class isn't covered by an existing scanner, grep for the *shape* of the bug
   across the repo before shipping. If it finds anything, add a scanner to `sweep.py`
   in the same change.

3. **Prefer a generalised guard over a point test.** A test asserting `/audit` has no
   `parse_mode` catches one regression. A test that re-derives the offender list from
   source and fails on any new one catches the class forever. See
   `TestNoUnescapedMarkdownInterpolation` in `tests/test_pure.py` for the pattern,
   including an allowlist that carries a *reason* per entry and a second assertion that
   fails when the allowlist goes stale.

4. **Break-test every check you add. Prove RED before trusting GREEN.**
   This is not optional and it is not theatre — the first `audit-plain-text` eval used
   `awk '/^async def audit_cmd/,/^async def /'`, which **collapses to a single line**
   because the opening line also matches the end pattern. It could never fail. It
   passed for exactly as long as it was worthless.
   ```bash
   cp telegram-companion-bot/bot.py /tmp/broken.py
   # re-inject the exact defect you just removed
   SWEEP_BOT=/tmp/broken.py python3 .claude/tools/sweep.py <scanner>   # must report it
   ```
   For an eval, the equivalent is `add-regression-eval`'s red-green procedure — and
   never `git checkout` a file holding uncommitted work to undo a test injection.

## The three questions that catch what greps miss

**"Is X referenced?" is strictly weaker than "does X do what the docs claim?"**
`BOT_TIMEZONE` passed a referenced-anywhere check for months: it *was* read — inside
`--check-config`, purely to label a warning — while the clock came from `TIMEZONE` and
every bot silently ran on Pacific. For any config the docs describe by *behaviour*,
trace the value to its actual use by hand. `sweep.py`'s `env-drift` scanner says this
in its own docstring because it cannot check it.

**"Does my diagnostic tell the truth?"** A mislabelled diagnostic is worse than none.
`_prompt_top_blocks` labelled every block by its first line, so an 84-token section was
reported as 4,715 tokens, and a real investigation was aimed at the wrong file for two
rounds. Before trusting a number a tool produced, check the tool against a case whose
answer you already know.

**"What does this reading actually measure — how current, what scope, and what would
*nothing* mean?"** (constraint C8, promoted 2026-07-27 after three instances in two
days.) Output gets believed at face value, and three times it was not what it looked
like:

| reading | read as | actually |
|---|---|---|
| an `/audit` line from earlier in the session | current config | **stale** — the model had been changed since, and a test plan was built on it |
| `grep '^MODEL='` returning nothing on six instances | "no model is set" | **wrong scope** — the variable is `NANOGPT_MODEL`; the grep answered a question nobody asked |
| `/errors` full of `Conflict` tracebacks | a fight happening now | **wrong currency** — `errors.log` is historical, survives restarts, and travels inside migration tars |

Two of those aimed a live diagnosis at the wrong thing for several rounds. The habits:
a grep that finds nothing is evidence only if the pattern was right — verify the name in
source before concluding from an empty result; a log tail proves what was *written*, never
what is *happening*, so for "now" use a bounded time window with a count; and any reading
taken earlier in a session is a historical claim, not a live one — re-read before acting
on it. No scanner can catch this one, which is why it lives here.

## Quality bar

- The class is written down in one sentence, in the changelog entry.
- `sweep.py` run and every candidate either fixed or explicitly justified.
- Any new check proved RED against a re-injected defect before being trusted.
- Guards are generalised where the class allows it; allowlists carry reasons.

## Verification checklist

- [ ] Class named in one sentence
- [ ] `python3 .claude/tools/sweep.py` run; candidates triaged
- [ ] New scanner added if the class wasn't covered
- [ ] New check break-tested red, then green
- [ ] Generalised guard preferred over a point assertion where possible

## Common mistakes

- Grepping only where you remember writing the thing. The wrong triage rule survived a
  correction pass exactly this way, including in the DM the owner reads *during* an
  incident.
- Trusting a check because it passes. Passing is meaningless until it has failed once
  on purpose.
- Treating a scanner hit as a defect. `bot.py.bak` in the shared code dir is a real hit
  and correctly mitigated — it sits inside the flock'd function.
- Fixing every candidate reflexively. Two Markdown sites were left alone deliberately
  (an int index; an int inside a code fence) and allowlisted with reasons.
