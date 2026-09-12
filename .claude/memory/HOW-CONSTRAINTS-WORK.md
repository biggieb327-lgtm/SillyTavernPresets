# How the Constraints Process Works

This document explains the purpose, lifecycle, and enforcement machinery behind
`.claude/memory/constraints.md` -- the repo's record of mistakes made *doing the work*,
and the rules each one earned.

## What constraints.md is (and is not)

Constraints.md records mistakes the *agent* made -- a wrong command, a premature "done",
a theory asserted as fact, a check that could not fail. It is the system's memory of its
own failure modes, written in the moment they happen and enforced by machinery that grows
from those failures.

It is **not** the operational log. The operational log (`operational-log.md`) records when
the *system* failed -- a bot crashed, a deploy went wrong, the fleet misbehaved. The
sorting test is one question: *did a bot misbehave, or did we?* Bot failures go to the
operational log. Agent mistakes go to constraints.

| File | Records | Example |
|---|---|---|
| `operational-log.md` | the **system** failed | "five instances had a dead man's switch that reported OK while returning 400" |
| `constraints.md` | the **work** went wrong | "ran phone tooling on the VPS" |


## The lifecycle of a constraint

### 1. Recognition and logging

The moment a mistake is recognised -- not at the end of the session, not in a summary,
not softened after the fact -- an entry is added to constraints.md. The rule is
immediate: before continuing the task, write down what happened.

Each entry follows a strict format:
- One line for **what happened** (plain, unvarnished)
- One imperative line for **the constraint** (the rule it earns)

If the constraint needs a paragraph to explain, it belongs in a skill file; link it from
constraints.md instead of expanding the entry.

Honesty is load-bearing. "I asserted X without evidence" -- not "it was unclear." A
sanitised entry teaches nothing.

### 2. The Minor log

Not every mistake earns a numbered constraint immediately. Self-corrected errors -- the
wrong path you caught a minute later, the broken test harness you fixed before anyone
saw it -- go in the **Minor** running log at the bottom of the file.

These *do* get logged, and that is the point. "I caught it immediately, no harm done" is
the reflex that keeps the Minor section empty and useless. Self-corrected errors are the
highest-frequency signal available: they are invisible to everyone but the agent who made
them, they cost real minutes, and they are where the repeating shapes show up first. A
Minor section with nothing in it means under-reporting, not a clean run.

Format: `- YYYY-MM-DD -- what happened -> what to do instead`. One line. Newest first.

### 3. The `seen` counter

When the same mistake recurs, the constraint's `seen` count is incremented. The count is
the whole point -- it tells a future session which constraints are load-bearing and which
are one-off.

This is the core mechanism that separates constraints from a diary. A constraint at
`seen: 1` is an observation. A constraint at `seen: 5` is a pattern that keeps
repeating, and its entry carries a detailed record of every occurrence -- what shape it
took, what caught it (or didn't), and what was learned.

### 4. Graduation at `seen: 2`

This is the escalation rule. A constraint that failed twice is not a documentation
problem -- it is a missing guard. At `seen: 2`, the constraint owes a **mechanism**:

- A **hook** (the agent did X) -- a PreToolUse or Stop hook in `.claude/hooks/` that
  blocks the turn when the mistake shape appears
- A **scanner** in `sweep.py` (this shape exists elsewhere in the repo)
- An **eval** in `run-evals.sh` (this can regress in bot.py)
- A **section in the relevant skill** -- but only when no mechanism can see the mistake

The preference order is: mechanism first, prose only when you can say *why nothing
mechanical would see it*. This mirrors the standing repo rule that a failure recurring
twice earns an eval.

### 5. Promotion from Minor

When two Minor entries share a cause, both are deleted and a new numbered constraint is
written. That is the sole reason Minor entries exist -- as raw material for pairing.
A Minor entry nobody ever promotes was still worth the ten seconds to write.

The `sweep.py constraints-drift` scanner enforces this mechanically:
- It counts the Minor backlog and flags when it passes 8 entries
- It looks for Minor entries sharing distinctive vocabulary -- candidates for a shared
  cause, which is the promotion trigger
- It tracks the date of the last promotion pass so the check is cumulative, not total

### 6. Archiving

After 30 days, if a Minor entry has not paired with anything, it moves under
`## Minor -- archived` at the bottom. Kept verbatim and searchable, just out of the
promotion count. Archiving is not deletion and needs no judgement call; promotion does.


## The enforcement machinery

Constraints do not stay as prose. The ones that recur grow into mechanical guards. Here
is how the system is layered:

### Session startup (session-audit.sh)

Every session begins with `session-audit.sh` reading constraints.md and reporting:

1. **Total count** of active constraints and how many have a mechanism
2. **PROSE ONLY** -- lists constraints with no mechanical guard, because reading them is
   the *only* defence. These are the ones that matter most at startup
3. **MECHANISM REVIEW** -- constraints that recurred *after* their guard was graduated,
   surfaced only when unreviewed (between debriefs)
4. **OVERDUE A MECHANISM** -- prose-only constraints already at `seen: 2+`, violating
   rule 4
5. **UNDATED GRADUATION** -- guards with no dated Graduated line, so recurrence timing
   cannot be checked

The design is deliberate: constraints that already have a hook or eval are *counted* but
not *named* at startup, because the mechanism catches them whether or not the session
reads the name. The ones named on the startup line are the unguarded ones -- exactly the
set where reading is the whole defence.

### Hooks (`.claude/hooks/`)

Graduated constraints become executable guards. Examples from the repo:

| Constraint | Hook | What it catches |
|---|---|---|
| C1 (confirm the host) | `host-guard.sh` | A command block with no host label, or mixed VPS/phone commands |
| C5 (label theories) | `theory-guard.sh` | Asserting what a named function returns without hedging |
| C7 (anchor edits on content) | `anchor-guard.sh` | `sed -i` with a numeric line address on a real file |
| C8 (what a reading measures) | `claim-guard.sh` | Identity/sameness claims resting on metadata with no hash |
| C13 (verification that cannot fail) | `eval-gate.sh` | Runs the eval suite on every turn touching gated surfaces |
| C15 (never git checkout to revert) | `risk-guard.sh` | `git checkout <path>` when the file has uncommitted changes |
| C16 (handover commands must work) | `handoff-guard.sh` | Relative paths or prompt hostnames in operator-facing blocks |
| C23 (shell evaluated something hidden) | `shell-semantics-guard.sh` | `\|\|` fallback on a pipeline tail; backticks in `git commit -m` |

Each hook has a documented escape hatch (e.g., `# theory-ok`, `# claim-ok`,
`# handoff-ok: relative`) and a break-tested case matrix.

### Evals (`.claude/evals/run-evals.sh`)

Some constraints graduate into evals that run in the test suite:

| Constraint | Eval | What it pins |
|---|---|---|
| C8 | `audit-keys-rendered` | Any key in `gather_audit_data()` that no user-facing surface renders |
| C12 | `no-live-raw-urls`, `roadmap-claims-current` | Dead `raw.githubusercontent` URLs; stale ROADMAP claims |
| C13 | `eval-parsers-fail-loudly`, `verify-steps-covered` | Python heredoc captures that discard stderr; verify.sh steps nothing exercises |
| C14 | `routine-prompts-runnable` (scoped) | Defect patterns matched only inside their correct region |
| C18 | `break-tester` | Guards `break-test.sh` itself through all six failure paths |
| C23 | `grep-c-fallback` | `grep -c ... \|\| echo` in committed shell scripts |

The eval `constraints-mechanism-marked` guards the *file itself*: every numbered
constraint must carry either `**Graduated` or `**Not graduated` as a line-anchored
marker, and the paths a graduation line names must resolve. This keeps the
categorisation that session-audit.sh depends on from drifting silently.

### Scanners (`sweep.py`)

The `constraints-drift` scanner in `sweep.py` enforces the file's own rules:

1. Flags any constraint at `seen: 2+` with no `**Graduated` line
2. Counts the Minor backlog and flags past 8 entries
3. Looks for Minor entries sharing vocabulary -- candidates for promotion
4. Tracks when the last promotion pass happened

### The debrief (session-debrief skill)

At the end of every session, the debrief skill asks:

- Were any mistakes made this session? (Always log them -- Minor or numbered)
- Do any Minor entries share a cause? (Promote them)
- Did any existing constraint recur? (Increment `seen`)
- Did any mechanism ship that targets a failure class? (Write a `skill-impact.md` row)

The debrief is where constraints.md gets maintained. It is also where the most dangerous
C22 shape lives ("reasoning *about* the machinery instead of reading it"), which is why
the debrief skill carries a grep step.


## The prose-only constraints

Not every constraint can be graduated to a mechanism. The file explicitly tracks *why*:

- **C4** (search for the shape, not the vocabulary) -- a search that returns too little
  is byte-identical to a search over a clean tree. Nothing can flag an absence it cannot
  distinguish from a genuine zero.
- **C6** (a migration invalidates assertions) -- no hook can see "a platform change just
  happened" as a trigger.
- **C9** (verify load-bearing hypotheses before shipping) -- a hook cannot know which of
  a diff's premises are load-bearing.
- **C10** (an unexplained default is not unintended) -- a scanner could list default-off
  flags but not read intent.
- **C11** (a diagnostic in a group chat is an in-world event) -- the damaging action is
  the owner typing in Telegram, not a tool call the agent makes.
- **C20** (a green test suite is not proof a reused pattern is safe) -- no mechanism
  generalizes "does this refactor change a function from a live-global reader to an
  import-time-bound closure."

These are named on the startup line precisely because reading them is the only defence.


## How constraints interact with other memory files

| File | Relationship |
|---|---|
| `operational-log.md` | System failures; constraints are agent failures. Distinct populations, same format discipline. |
| `decisions.md` | Records *choices*; constraints record *mistakes*. A decision to not graduate a constraint goes in the constraint entry, not the decision log. |
| `mycelium.md` | Messages between sessions. A constraint entry might reference a mycelium handoff that carried a wrong claim. |
| `watchlist.md` | Low-level observations not yet worth a constraint. A watchlist item can graduate to a Minor entry if it recurs. |
| `skill-impact.md` | Tracks whether an intervention (a graduated mechanism) held. A `pending` row is written when a mechanism ships; it flips to `holding` or `recurred` based on forward evidence. |


## The design principles

1. **Immediate logging.** Not at the end, not softened. The moment it is recognised.
2. **Plain ownership.** "I asserted X" -- not "it was unclear."
3. **Counting recurrence.** The `seen` counter is the escalation signal.
4. **Graduating to mechanisms.** Prose that failed twice earns a guard, because prose
   alone already failed.
5. **Admitting what cannot be mechanised.** Every `**Not graduated**` entry states *why*,
   and that scope claim is itself tested -- the `constraints-mechanism-marked` eval
   resolves the paths a graduation line names.
6. **Failing loud.** A broken parser, a missing file, an empty result -- each is treated
   as a failure, never as "nothing to report." The session-audit hook, the evals, and
   `sweep.py` all fail toward noise rather than silence.
7. **Self-reference discipline.** The file's own rules are enforced by evals
   (`constraints-mechanism-marked`, `mechanism-recurrence-surfaced`) and scanners
   (`constraints-drift`), because a learning system whose bookkeeping drifts silently
   teaches the wrong lessons.
