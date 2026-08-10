---
name: hubris
description: Stop "I could not determine this" from being reported as "this is wrong" — in a checker you are writing, in a finding you are about to report, or in an explanation for a failure you have not read the source of. Load BEFORE writing any tool that renders a verdict, before reporting a result from a tool or an external reading, and before telling a user why something broke. Encodes the 2026-08-10 session where the same collapse shipped four times in one tool and five times in one report.
---

# Unknown is not a negative verdict

Named by the owner on 2026-08-10, after a session in which one tool told them nine real
places did not exist, and its author told them four things that were not true — all from the
same move: **turning "I could not determine this" into "this is wrong".**

The constraints file already covers most of the claim half (C8, C13, C14, C18, C19, C20) and
the hooks fired on the day. They fired *after* the sentence was written. This skill is for
before.

## When NOT to use

- Reporting an outcome you executed and observed end to end (a test run, a diff you made).
  Say what happened, plainly. This is not a licence to hedge everything.
- Ordinary uncertainty already stated as such. Adding a second layer of qualification is its
  own failure — it moves the work of judging onto the reader.

## Rule 1 — a checker has three outcomes, not two

**Any tool that renders a verdict needs `pass`, `fail`, and `could not determine`, and must
never let the third print as the second.** All four of these shipped in one tool in one
session:

| What happened | What the report said | What it should have said |
|---|---|---|
| HTTP 429 rate limit | `NOT FOUND` (× 9 real places) | `LOOKUP FAILED` — never checked |
| Entry is a district, not a POI | `NOT FOUND` | matched as an area |
| Entry is a description, not a name | `NOT FOUND` (× 19) | not a place name — not looked up |
| Dependencies missing | bare `ModuleNotFoundError` | which interpreter to use |

The owner's read on the third was sharper than the author's: *"They're not real places so
there's no point in trying to find them."* A tool that says "I can't check this" twenty times
is barely better than one that says it wrongly.

Checks to run against a verdict-producing tool before shipping it:

- List every way the check can fail to reach an answer. Each needs its own outcome.
- Grep the reporting path: can an exception, an empty result, or an unsupported input reach
  the same branch as a genuine negative? If yes, that is the defect.
- Count outcomes separately in the summary. **Never sum "flagged" and "failed"** — one is a
  finding, the other is the absence of one.
- Give distinct exit codes, so a caller can retry the undetermined and act on the confirmed.
- Ask what a wrong verdict costs. Here it was the owner deleting real, well-chosen content
  on the tool's say-so. Bias the default toward *skipping*, so the failure is a missing
  check rather than a false accusation.

## Rule 2 — before a reading becomes a finding, name what it measured

C8 with the specific shapes that got past it on 2026-08-10, all stated to the owner as fact:

- *"The photo matches"* — from filename, scene and pixel dimensions. Metadata narrows; it
  does not identify. Hash it or say "consistent with".
- *"The deploy is live"* — from one new field appearing in output. Consistent with, not proof.
- *"The premise is disproved"* — a payload date read as *tomorrow* by comparing it against a
  session date **in an unestablished timezone**. It was plausibly today.
- *"Her weather has been wrong"* — from a config label, without checking that the weather
  path reads a different variable entirely (`WEATHER_LAT`/`WEATHER_LON`). It does.
- *"She is a Portland character"* — from a seed file, when the owner's answer was Seattle.
  Content on disk is evidence about content on disk.

The test before writing the sentence: **what exactly did I observe, and what else is
consistent with it?** If more than one thing is, the finding is a hypothesis. Label it.

## Rule 3 — never explain a failure with a mechanism you have not read

A command failed. The explanation offered was "probably a detached HEAD" — plausible,
confident, and wrong. The real cause was in `vps-sync.sh`, in the repo, one grep away:
it exports `GIT_SSH_COMMAND` with a deploy key per-run, so nothing outside it inherits auth.

**When a repo script owns the thing that broke, read the script before theorising.** A
mechanism offered as an explanation is a claim, and it gets the same bar as any other. "I do
not know yet, reading X" costs one turn; a wrong mechanism costs a round trip and sends the
owner to fix the wrong thing.

## Rule 4 — a break-test that passes is a finding

C18's live case. Break-testing a new classifier against 21 real inputs came back **green**
with half the logic disabled: capitalisation alone decided every case, so the marker branch
was untested code that looked verified.

**If disabling a branch does not turn something red, that branch has no test.** Either write
the case that pins it, or delete the branch. Do not record it as verified.

## Verification checklist

- [ ] Every "could not determine" path in the tool has its own outcome, distinct from `fail`
- [ ] Summary counts undetermined separately; nothing sums it with findings
- [ ] Each claim in the report traced to what was actually observed, and hedged where more
      than one explanation fits
- [ ] No failure explained by a mechanism whose source was not read
- [ ] Every new branch break-tested RED individually, not as a group

## Common mistakes

- Treating this as an instruction to hedge. Calibration is not throat-clearing: state
  observed facts plainly and hypotheses as hypotheses. Both, precisely.
- Writing the honest caveat *after* the confident sentence, in the same message. The reader
  has already acted on the first line.
- Assuming the guard-rails cover it. On the day this was named, `claim-guard`,
  `handoff-guard` and `host-guard` all fired and the mistakes still reached the owner —
  Stop hooks catch a sentence that is already written.

## What to report back

For a tool: the outcome set, and which inputs reach each. For a finding: what was observed,
what was inferred, and which parts are still hypotheses.
