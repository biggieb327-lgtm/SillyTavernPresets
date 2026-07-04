---
name: companion-bot-validation-and-qa
description: >
  The validation and QA playbook for telegram-companion-bot — how correctness is actually
  proven in a repo with NO test suite and NO CI. Load this whenever you are: about to commit
  or push a change; about to claim a fix works or a task is "done"; designing how to verify a
  change before writing it; asked "how do I test this here?"; editing bot.py, acoustic_ears.py,
  a shell helper, or a character-card JSON and wondering what check applies; testing a single
  function from bot.py (which cannot be imported); verifying a regex, a control-flow change,
  an auth/guard change, or audio processing; or defining what the owner should observe in a
  live device test. Covers the compile gate, the AST-extraction dry run (the house pattern),
  trace tests, regex execution, synthetic-input smoke tests, JSON round-trips, deployed-vs-repo
  checks, the live verification protocol, the guard-coverage audit, and evidence standards.
  Do NOT use for: building diagnostic instruments (companion-bot-diagnostics), investigating
  a live bug or unknown behavior (companion-bot-analysis-toolkit / companion-bot-debugging-playbook),
  or deciding whether/how a change ships (companion-bot-change-control).
---

# Companion-Bot Validation and QA

How correctness is maintained in `telegram-companion-bot/` — a single ~8,900-line `bot.py`
running six live instances on the owner's phone, with **no test suite and no CI**. The only
automated gate is a PreToolUse hook in `.claude/settings.json` that runs `py_compile` on
`bot.py` before every `git commit`. Everything else is disciplined manual validation, and
this skill is the discipline. Facts verified against the repo on **2026-07-02**; every
"worked example" below was actually executed on that date.

**The owner's rule: evidence before fixes.** Nothing is "verified" by eyeballing when it
can be measured. If a check can be run, run it; if it can't be run here, define exactly
what the owner will observe on the device before asking them to test.

## Evidence standards

What counts as evidence:
- A command's actual output (compile result, script exit code, printed PASS/FAIL).
- A log line with the relevant tag (`[heartbeat]`, `[followup]`, `[event-reminder]`, ...).
- A diff you read after making it.
- A measured count (e.g. "56 `async def *_cmd(` handlers, 74 `CommandHandler(` registrations
  at HEAD") — numbers you produced, not numbers you remember.
- A regex executed against the real text in question.

What does NOT count:
- Plausibility. "Should work." "The logic looks right."
- Similarity of symptoms. **Canonical failure:** the owner reported "heartbeat messages
  firing a minute after I send a message." The follow-up feature's 45–120 s delay window
  matched "a minute", so it was suspect #1 and heartbeat suspect #2 — two full hypothesis
  cycles wasted on innocent systems. Executing `_FOLLOWUP_RE` against the actual triggering
  text (no match) and grepping the logs (`[followup]` empty, `[heartbeat]` showing normal
  cadence with correct skips) ruled both out; the real cause was an auto-extracted event
  reminder. Delay-window similarity is not evidence. (See companion-bot-debugging-playbook
  for the full chain; fix landed in commit `6a8061f`.)
- A passing check whose expected result you decided AFTER seeing the output.

## Acceptance discipline: state the expectation first

Before running any check, write down (in your working notes, or in the message to the owner)
the exact number, string, or observation that will count as PASS — and what would count as
FAIL. Then run it. If you can't state the expected result in advance, you don't understand
the change well enough to verify it; go back to the code.

Examples of well-formed acceptance criteria used in this repo:
- "`describe_voice_profile({})` returns `None`, not `''`."
- "The synthetic WAV has one 1.5 s silent gap starting at t=2.0 s; `analyze_acoustic` must
  report exactly one pause with duration 1.0–2.0 s starting between t=1.5 and t=2.5."
- "`cmp` of deployed vs clone bot.py exits 0 AND `grep -c` of the new marker string in the
  deployed file prints a nonzero count."

---

## Pattern 1: Compile gate

**When:** after every edit batch, before every commit. Non-negotiable.

```bash
python3 -m py_compile telegram-companion-bot/bot.py
python3 -m py_compile telegram-companion-bot/acoustic_ears.py   # if touched
bash -n telegram-companion-bot/update-all.sh                    # bash -n for any edited .sh
```

Silence = pass. The PreToolUse hook in `.claude/settings.json` re-runs the bot.py check at
commit time and blocks the commit on failure — but the hook only covers `bot.py`; shell
scripts, `bot_app/`, and `acoustic_ears.py` are on you. Run the checks yourself before the
hook does; the hook is a backstop, not the process. Verified 2026-07-02: `bot.py` and
`acoustic_ears.py` py_compile-clean at HEAD; all five `.sh` helpers pass `bash -n`.

Note the compile gate proves only syntax. It says nothing about behavior — that's what the
rest of this skill is for.

## Pattern 2: AST-extraction dry run (THE house pattern)

**When:** you changed or added one function in `bot.py` and want to execute it with
hand-built inputs. **Why not just import bot.py:** it has import-time side effects — it
loads dotenv, reads state files, and builds a network session at module scope. Importing it
in a test context is not safe and never will be (single-file entry point is an architecture
invariant). So: parse the file, extract the one function's source, `exec` it in a clean
namespace, and call it.

The runnable skeleton (authoritative copy — analysis-toolkit Method 3 points here) — this
exact script was run against the real `bot.py` on 2026-07-02 and all four cases passed:

```python
import ast

SOURCE_FILE = "telegram-companion-bot/bot.py"
TARGET = "describe_voice_profile"

src = open(SOURCE_FILE).read()
tree = ast.parse(src)
fn_src = next(
    ast.get_source_segment(src, node)
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == TARGET
)

ns = {}          # add stubs here for any module-level names the function touches
exec(compile(fn_src, f"<{TARGET}>", "exec"), ns)
fn = ns[TARGET]

# Hand-built inputs with KNOWN expected outputs -- state them before running.
cases = [
    ({}, None),                                                    # empty dict
    ({"emotion": [{"label": "warm"}]}, "emotion=warm"),            # partial
    ({"emotion": [{"label": "warm"}], "pitch": [{"label": "low"}],
      "vocalStyle": [{"label": "breathy"}]},
     "emotion=warm, style=breathy, pitch=low"),                    # full-ish, checks order
    ({"emotion": [{}]}, "emotion=?"),                              # missing label key
]
for inp, expected in cases:
    got = fn(inp)
    status = "PASS" if got == expected else "FAIL"
    print(f"{status}: {TARGET}({inp!r}) -> {got!r} (expected {expected!r})")
```

Output on 2026-07-02: four PASS lines, including the edge cases (empty dict → `None`;
`{"emotion": [{}]}` → `"emotion=?"`).

Recipe details:
- **Stubs go in `ns`.** If the function reads module-level globals (`conversation_history`,
  `user_names`, `NAME`, env-derived constants), assign fakes into `ns` before `exec`.
  Example: `_assess_safety` (bot.py:3594) was dry-run this way by stubbing
  `conversation_history` with a simulated 6-turn history dict and capturing the assembled
  prompt (stub `call_nanogpt` with a lambda that records its arguments and returns "no") —
  this verified both the history-snippet assembly and the empty-history degradation (the
  "Recent exchange:" block is omitted entirely when history is empty, per the conditional
  at its `user_content` assembly). That behavior shipped in commit `18d4162`.
- **Async functions:** extraction works the same (`ast.AsyncFunctionDef` is in the walk);
  run them with `asyncio.run(fn(...))` and stub the awaited collaborators.
- **Scope limit:** this tests one function's logic in isolation. It does not prove call
  sites pass the right arguments — read those separately.
- Write the script in the scratchpad, never into the repo.

## Pattern 3: Trace tests (simulated state, branch-by-branch)

**When:** you changed control flow that depends on runtime state you can't easily execute —
scheduling, deferral, dedup logic. Simulate the state and walk every branch on paper (or via
Pattern 2 with stubbed state), recording the outcome per branch.

Worked example A — the event-reminder defer logic (`fire_reminder`, bot.py:6429, commit
`6a8061f`): the branch defers when `time.time() - last_seen[chat_id] < EVENT_NUDGE_BUFFER_MIN*60`
(default 15 min) AND `_deferred < EVENT_NUDGE_MAX_DEFERS` (default 3). Trace matrix used:

| last_seen | _deferred | expected |
|---|---|---|
| 2 min ago | 0 | defer, `_deferred`→1, re-armed in 15 min, `[event-reminder] ... deferring` logged |
| 2 min ago | 3 | fires anyway (cap — never silently dropped forever) |
| 20 h ago (stale) | 0 | fires immediately |
| chat_id absent from last_seen | 0 | `last_seen.get(..., 0)` → fires (treated as stale) |

Each row is checked against the actual code, not against intent. The fourth row is the kind
of branch eyeballing misses.

Worked example B — the duplicate-reminder-ID fix (commit `7c205bd`): `_schedule_event` built
two reminder dicts (before- and after-event) and called `_new_reminder_id()` for each before
either was appended to the global `reminders` list, so both got `max(existing)+1` — the same
id — making `/delreminder` unable to target the second. The trace test: build the two dicts
with the fixed allocator against a simulated `reminders` list and confirm the ids are
distinct and both survive a save/load. The bug existed precisely because "each dict calls
the id allocator" sounded correct; only walking the state through both calls exposed it.

## Pattern 4: Regex verification — execute, never assert

**When:** you write, modify, or reason about ANY regex. Rule: never state what a regex
matches; run it against the real text.

```bash
python3 - <<'EOF'
import re
_FOLLOWUP_RE = re.compile(r"...paste the REAL pattern from bot.py...", re.IGNORECASE)
for t in ["the exact text in question", "a near-miss variant"]:
    print(bool(_FOLLOWUP_RE.search(t)), repr(t))
EOF
```

This pattern once DISPROVED a live hypothesis: during the proactive-message misdiagnosis
(see Evidence standards above), everyone assumed `_FOLLOWUP_RE` (bot.py:7785) matched the
owner's message. Executing it against the actual text returned no match, which — combined
with an empty `grep "[followup]"` in the log — eliminated the follow-up system in one step.

It also catches quiet gaps you'd swear don't exist. Executed 2026-07-02 against the real
pattern: `"brb, dinner's ready"` → True, `"give me a min"` → True, but `"one min"` → **False**
(the alternation has `one moment` and `give me a (…|min)` but no bare `one min`). Whether
that's a bug is a product question; that it's the current behavior is now a fact, not a guess.

## Pattern 5: Synthetic-input smoke tests

**When:** validating signal/data processing offline — build an input with KNOWN properties
using stdlib only, and assert the analyzer reports those properties.

Worked example — `acoustic_ears.analyze_acoustic` (voice-note tone analysis, vendored in
commit `bae2dcb`): synthesize a WAV with `wave` + `math.sin` + `struct` — 2 s of tone, a
deliberate 1.5 s silent gap, 2 s of tone — then assert exactly that gap appears in the
`pauses` output. Executed 2026-07-02:

```
duration_s: 5.5  pauses: [(1.82, 3.42, 1.6)]
summary: ~109 wpm, even volume, dark tone, 1 notable pause(s)
SMOKE PASS: pause detection caught the synthetic gap at (1.82, 3.42, 1.6)
```

**Hard-won detail (hit on 2026-07-02, keep it):** a constant-amplitude sine produces ZERO
detected pauses even with a real silent gap, because the detector's floor is RELATIVE —
`floor = max(percentile(rms_db,30), quiet + 6)` (acoustic_ears.py:94-95) sits above a
perfectly flat signal, making every frame "quiet" and the resulting whole-file event fail
the edge conditions. The synthetic tone needs speech-like level variation (a 3 Hz amplitude
modulation on the sine fixed it). General lesson: a synthetic input must be realistic in the
dimensions the algorithm keys on, and a surprising FAIL on a synthetic input is a finding
about the algorithm's assumptions — investigate before "fixing" the test.

## Pattern 6: JSON round-trip for card edits

**When:** editing any character card (`nora/`, `bonnie/`, `cass/`, `emily/`, `jules/`,
`priya/` JSON) or other data JSON.

- Edit surgically: change the single field's text in place (Edit tool, exact-string match).
  **Never** load-modify-dump the whole file — Python's `json.dump` re-flows arrays and
  whitespace, polluting the diff so the real change can't be reviewed.
- After every edit: `python3 -c "import json; json.load(open('telegram-companion-bot/nora/Nora.json'))"`
  (adjust the path). Silence = valid.
- Then read the diff and confirm it touches only the intended field.

## Pattern 7: Deployed-vs-repo verification

**When:** any time behavior on the device matters — the owner's costliest recurring failure
is debugging a phone that is quietly running OLD code. Never reason about device behavior
until you've proven what code is deployed.

Two independent checks (both zero-dollar, safe to paste into the owner's chat):

```
cmp ~/stp-deploy/telegram-companion-bot/bot.py ~/telegram-bot/bot.py && echo DEPLOY-MATCHES
grep -c "some_string_unique_to_the_new_change" ~/telegram-bot/bot.py
```

The `cmp` proves clone == deployed; the marker grep proves the clone actually contains the
new commit (a stale clone passes `cmp` happily). Pick the marker from the diff you just
shipped. `update-all.sh` self-verifies the copy step the same way (`cmp -s` after `cp`,
aborting loudly on mismatch — update-all.sh:33) — but that only covers the copy, not whether
the pull brought the commit, so the marker grep still earns its keep. Full deploy mechanics:
companion-bot-device-ops.

## Pattern 8: Live verification protocol (device-only behavior)

**When:** the behavior can only be observed on the phone (Telegram interaction, proactive
timing, voice notes, watchdog restarts). You cannot run it, so the protocol substitutes
rigor for execution:

1. **Define the expected observation BEFORE the owner tests.** Written in the message:
   "after you send X, within N seconds you should see Y in chat AND a `[tag] ...` line in
   `~/nora-bot/bot.log`."
2. **State what confirms vs what refutes.** "If Y appears without the log line, the message
   came from a different path — that refutes the fix, don't call it done."
3. **Zero dollar signs in every command** the owner will paste — their chat client renders
   `$...$` spans as math and strips them, silently corrupting commands. No `$HOME`, no
   `$(...)`, no `${var}`. Use `~` and literal paths. (Full paste-corruption rules:
   companion-bot-device-ops.)
4. **Deployed-vs-repo check first** (Pattern 7) — a live test against stale code is worse
   than no test.
5. Ask for the pasted output, not a summary of it.

## Pattern 9: Guard-coverage audit loop

**When:** after ANY change touching command handlers, auth, `_guard`, `_is_allowed`, or
handler registration. History: an audit found ~60 of 82 handlers never called
`_guard()`/`_is_allowed()`, so `ALLOWED_USERS` did not actually restrict most of the bot —
fixed in commit `fc44dd2`. The loop that found it, re-runnable any time:

```bash
grep -c "async def .*_cmd(" telegram-companion-bot/bot.py     # 56 at HEAD 2026-07-02
grep -c "CommandHandler(" telegram-companion-bot/bot.py       # 74 at HEAD 2026-07-02
grep -n "async def .*_cmd(" telegram-companion-bot/bot.py     # then check each body
```

Acceptance: every handler body calls `_guard(update)` (or `_guard(update, rate_limit=True)`)
near its top, OR is one of the two documented exceptions:
- `/chatid` — deliberately open; a new user needs it to discover their ID for `ALLOWED_USERS`.
- `/start` — greeting stays visible to anyone, but its `set_owner()` side effect is gated on
  `_is_allowed()` so an unauthorized caller can't hijack ownership of a fresh bot.

Any other unguarded handler is a finding. Note the counts differ (74 registrations vs 56
`*_cmd` defs) because some handlers don't follow the `_cmd` suffix and factories register
several commands — audit by registration list, not by naming convention alone.

---

## Golden inventory (as of 2026-07-02)

The honest list of what is currently verified — nothing more:

- `bot.py` and `acoustic_ears.py` py_compile-clean at HEAD; all five shell helpers pass
  `bash -n`.
- `acoustic_ears.analyze_acoustic` smoke-tested offline with a synthetic WAV (pause
  detection specifically exercised; see Pattern 5 for the transcript).
- `describe_voice_profile` dry-run via AST extraction, 4/4 cases pass (Pattern 2).
- `update-all.sh` self-verifies its bot.py copy with `cmp` and aborts loudly on pull failure.
- The commit-time hook in `.claude/settings.json` runs py_compile **and** the tests/ suite
  before every commit.
- `tests/run.py`: 45/45 pure-function assertions pass at HEAD (2026-07-04).

Anything not on this list, or not covered by `tests/test_pure.py`, was verified (if at all) only
at the time it shipped — re-verify before relying on it.

## The tests/ directory (BUILT 2026-07-04)

`telegram-companion-bot/tests/` now exists: `run.py` (the AST-extraction harness — pulls a
function from bot.py source and exec's it in a controlled namespace, so bot.py is never
imported) and `test_pure.py` (~45 assertions over the pure functions that had real bugs:
`_parse_hhmm`, `parse_when`, `parse_cron_schedule`, `due_between`, `in_quiet_hours`,
`_seconds_until_daytime_slot`, `_reminder_due_str`, `_looks_like_refusal`,
`_format_json_for_prompt`, the `_valid_*` load guards, mood decay). Run with
`python3 telegram-companion-bot/tests/run.py` — exits non-zero on any failure. The commit-time
hook in `.claude/settings.json` runs it before every `git commit` (alongside py_compile), so a
regression in a covered function blocks the commit. No bot.py refactor, no imports of it, no new
deps — does not violate the single-file entry-point rule. **When you fix a bug in a pure
function or add one, add a case to `test_pure.py` in the same change.**

## Run the periodic multi-agent audit after any batch of bot.py changes

Tests catch regressions in *covered* functions; they do not catch drift, integration
regressions, or new bugs in untested code — which is most of an 8,900-line file. Two audits this
session found 23 bugs the tests couldn't have (copy-paste drift, missing gates, cross-function
preconditions), and two were introduced by an earlier batch's own fixes. So **before deploying any
non-trivial batch of bot.py changes, run the multi-angle audit**: dispatch parallel review agents
(line-by-line, removed-behavior, cross-function, reuse/simplification/efficiency, plus subsystem
sweeps for the areas touched) per the methods in **companion-bot-analysis-toolkit**, verify each
surfaced finding against the code yourself, then fix. This is the process half of the safety net;
the tests are the automated half. Do not skip it because "the tests pass."

## Provenance and maintenance

- All facts, line numbers, counts, and command outputs verified against HEAD (`faea119`) on
  2026-07-02; the Pattern 2, 4, and 5 worked examples were executed that day, not recalled.
- Re-verify line numbers and handler counts after any large bot.py change; re-run the golden
  inventory before citing it.
- Sibling skills: change gating → companion-bot-change-control; deploy/device mechanics →
  companion-bot-device-ops; live-bug triage → companion-bot-debugging-playbook.
