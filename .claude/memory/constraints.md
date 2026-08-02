# Constraints — mistakes made doing the work, and the rule each one earned

**This file is not the operational log.** Keep them apart or both rot:

| File | Records | Example |
|---|---|---|
| `operational-log.md` | the **system** failed — a bot, a deploy, the fleet | "five instances had a dead man's switch that reported OK while returning 400" |
| **this file** | the **work** went wrong — a wrong command, a premature "done", a theory asserted as fact | "ran phone tooling on the VPS" |

The test: *did a bot misbehave, or did we?* Bot → operational log. Us → here.

## Rules for this file

1. **Add an entry the moment a mistake is recognised**, before continuing the task.
   Not at the end of the session — that is when they get forgotten or softened.
2. **One line for what happened, one imperative line for the constraint.** If the
   constraint needs a paragraph it belongs in a skill; link it from here instead.
3. **Increment `seen` when the same mistake recurs.** The count is the whole point —
   it is what tells a future session which constraints are load-bearing.
4. **At `seen: 2`, it graduates.** A constraint that failed twice is not a documentation
   problem, it is a missing guard: write a hook (the agent did X), a `sweep.py` scanner
   (this shape exists elsewhere in the repo), an eval (this can regress in bot.py), or —
   when no mechanism can see the mistake — **a section in the relevant skill**, and link
   it. This mirrors the standing repo rule that a failure recurring twice earns an eval.
   *Skills were added to this list on 2026-07-27: the original three-way rule would have
   rejected the only correct answer for C8, whose failure mode no hook or scanner can
   detect. Prefer a mechanism; accept prose only when you can say why nothing mechanical
   would see it.*
5. **Own it plainly.** "I asserted X without evidence" — not "it was unclear". A
   sanitised entry teaches nothing.

---

## Active constraints

### C1 — Confirm the host before any host-specific command
**seen: 6** (2026-07-19 ×1, 2026-07-26 ×3, 2026-08-01 ×1, 2026-08-02 ×1)
Phone tooling (`update-all.sh`, `tmux kill-session`, `pkg`) was run on the VPS, and
VPS commands (`journalctl`, `sudo`, `/opt/...`) on the phone. Each failure looked like
a broken tool rather than a wrong machine, and one silently no-op'd mid-cutover.
**Constraint:** before emitting a host-specific command, state which host it is for.
Before running one, `uname -o` — `Android` = phone, `GNU/Linux` = VPS.
**Graduated 2026-07-27:** `.claude/hooks/host-guard.sh` + `host_guard.py`, a Stop hook.
It blocks the turn when a fenced command block mixes VPS-only and phone-only commands,
when a host-specific block appears in a message that never names its host, or when a
`# host:` pragma contradicts the commands inside the block. Nine-case matrix, including
fail-open on a malformed payload.
**What it does NOT cover, deliberately:** the fleet is on a machine this container
cannot reach and the owner runs these commands by hand, so nothing here can stop a
paste into the wrong shell. The hook enforces only the agent's half — that every block
handed over is attributable to exactly one host. The operator's half stays prose
(`CHEATSHEET.md`: `uname -o` before anything host-specific).
**Occurrence 5 (2026-08-01) — the hook worked.** A `vps-sync.sh` deploy loop went out in
a message that never named its host; host-guard blocked the turn and the block was
relabelled before the session ended. Notable because the *preceding* deploy handoff in
the same session carried `# host: VPS (as root)` correctly — the lapse came with a
second, longer message where the commands were a follow-up rather than the main point.
The failure mode to watch is not "forgot the rule", it is **"the command block was
incidental to the message"**. No further mechanism needed; graduation is holding.
**Occurrence 6 (2026-08-02) — a shape the guard cannot resolve alone.** A block labelled
`# host: phone (Termux)` held `scp /sdcard/... root@vps:/opt/telegram-bots/...`. That is
correct: scp *runs* on the phone and *writes* to the VPS. But the block contains a VPS-only
path, so the guard read it as mixed and blocked — correctly, since it cannot distinguish a
remote destination argument from a local path, and guessing would defeat the check. The
resolution is the `# host: both` pragma the hook already offers, plus splitting the purely
local commands out. **Cross-host transfer commands (`scp`, `rsync`, `ssh <host> <cmd>`) are
inherently two-host and must be labelled `# host: both` up front** — not discovered at the
Stop hook. Both occurrences this session were labelling, never a wrong-host command.

### C16 — A handed-over command block must work on someone else's machine
**seen: 2** (2026-08-02 ×2) — *promoted straight to a mechanism the day both occurred;
rule 4's bar is two, and both had already cost a round trip.*
Two shapes, one session, both in the **handoff** rather than the work:
- A "full sequence" block did `cd /opt/telegram-bots` and then used relative paths. The
  owner's shell was in `~`; seven `vps-sync.sh` calls resolved against the wrong directory
  and failed at once. Every earlier message that session had used absolute paths — the
  regression came from compressing them into one block.
- An `scp` target was taken from the owner's shell prompt (`root@vmi3420780`). A prompt
  hostname is what a box calls itself locally, not an address another machine can route to.
**Constraint:** write every path absolute, even when longer, and take ssh/scp targets from
something that routes — never from a prompt, `hostname`, or a window title. Assume the
operator pastes a *subset* of the block, in a shell you did not set up.
**Graduated 2026-08-02:** `.claude/hooks/handoff-guard.sh` + `handoff_guard.py`, a Stop
hook. Scoped to operator-facing blocks (a `# host:` pragma, or fleet host-specific
commands), so illustrative snippets are untouched. Escape hatches `# handoff-ok: relative`
and `# handoff-ok: hostname`. Ten-case matrix — three defect shapes RED, seven legitimate
blocks green including quoted regexes, IP and FQDN targets, and a `cd` with absolute paths
after it — plus end-to-end checks that it blocks in situ, honours `stop_hook_active`, and
fails open on a malformed payload.
**Occurrence 3 (2026-08-02) — invented filenames that read as real ones.** An `scp` block
used `nora_aspiration.jpg` as a stand-in for a path only the owner knew; it looked like a
filename rather than a blank, so it was pasted verbatim and failed with `No such file`.
**Placeholders must be unmistakable** — `<PATH-TO-NORA-IMAGE>` in angle brackets, never a
plausible-looking name — and any block referencing files on the operator's machine should
be preceded by the command that finds them. Not a new mechanism: handoff-guard reads
argument tokens, and cannot know which filenames exist on a machine it has never seen.

**Occurrence 4 (2026-08-02) — an interactive `read` inside a pasted block.** A block began
`read -r -s -p "Giphy API key: " GIPHY_KEY` and continued with the loop that used it. Pasting
buffers every line on the terminal's stdin, so `read` consumed the *next line of the block*
(`for i in nora bonnie priya; do`) as the key; the loop header vanished, the body ran with an
empty `$i`, and a stray `/opt/telegram-bots/.env` was created. **Never put a command that
reads stdin — `read`, `passwd`, anything interactive — in a block intended to be pasted.**
Either split it into its own block with an explicit "run this alone" instruction, or avoid
stdin entirely. Same family as the `cd`-then-relative-paths case: the block was correct when
executed line by line and wrong when used the way operators actually use it.
**Correction, same day:** the first draft of this entry claimed handoff-guard "cannot see
this one — the paste semantics are in the terminal, not the text". That was itself an
unchecked assertion (C8). The signature is perfectly mechanical: a stdin-reading command
with further command lines after it in the same block. handoff-guard now checks it — six-case
matrix, RED on the real block, green on a lone `read`, a trailing `read`, comment-only
`read`, and the `# handoff-ok: interactive` hatch.

**Division of labour:** `host-guard` answers *which machine is this for?*; this answers
*will it actually work there?* Neither can stop a paste into the wrong shell — that half
stays the operator's, and it is why the C1 entry says what it says.

### C2 — Name the class before calling a fix done
**seen: 2** (2026-07-26 ×2)
v2026-07-26.6 fixed one `pip install` hint and shipped; three more hardcoded install
hints survived, one of them user-facing. Earlier the same night, the restart-storm fix
turned out to be three phone-era assumptions in one function, not one.
**Constraint:** write the class in one sentence before claiming done. Then run
`python3 .claude/tools/sweep.py` and triage every candidate.
**Graduated:** `.claude/skills/fix-the-class/SKILL.md`; new `install-hint` scanner in
`sweep.py` (v2026-07-26.8).

### C3 — Prove a check RED before trusting it GREEN
**seen: 3** (2026-07-25 ×1, 2026-07-26 ×1, 2026-07-28 ×1)
The `healthcheck-status-checked` eval passed its own break test — it grepped for
`status_code`, which still appeared in a log line after the guard was removed. The
earlier `audit-plain-text` eval had an awk range that collapsed to one line and could
never fail.
**2026-07-28 — a new form: a check handed to the operator.** The group-chat pre-enable
step told the owner to `journalctl | grep GROUP_LEDGER_DIR` to confirm both pilots
shared a ledger directory. That warning is gated `if GROUP_MODE and GROUP_PEERS`
(bot.py:387), so on a not-yet-enabled instance it can never print: the check was
circular — it verified a precondition using a signal that only exists after the thing
the precondition gates. Empty output was the only possible result, and I would have read
it as a finding. Caught only because the owner reported the empty output rather than the
expected line.
**Constraint:** every new eval, test, scanner **or operator-facing verification step**
must be shown capable of producing a signal before it is trusted — run it against a
deliberately re-injected defect, or for a manual check, state the conditions under which
the expected output appears and confirm those hold. **"Nothing printed" is a result only
if something could have printed.**
**Graduated:** `add-regression-eval` and `fix-the-class` both require it for automated
checks. The operator-facing form is new here and is why this entry now names it
explicitly — a handed-over check is one nobody will break-test unless the author did.

### C4 — Search for the bug's shape, not its remembered vocabulary
**seen: 1** (2026-07-26)
Swept for phone-era assumptions by grepping `Termux|Android|tmux|run-bot`, and missed
`pip install "python-telegram-bot[job-queue]"` — a live instance of the class whose
string contains none of those words. The scanner found it immediately.
**Constraint:** grep for the *mechanism* (the shape of the defect), not the words you
remember writing. If a mechanical scan is possible, write it instead of grepping.

### C5 — Label a theory as a theory until evidence arrives
**seen: 1** (2026-07-26)
Asserted that `watchdog.sh` was running from cron and that this explained bonnie's
resurrection. The interval was consistent with it but never confirmed, and the real
mechanism (watchdog relaunches on a *missing tmux session*, in any mode) made the cron
question irrelevant. The wrong frame was stated as fact in the middle of an incident.
**Constraint:** while diagnosing, mark unconfirmed causes as unconfirmed, and say what
evidence would settle them. Confidence follows evidence, not fluency.

### C6 — A migration invalidates assertions, not just docs
**seen: 1** (2026-07-26)
After the VPS cutover, a *test* still asserted phone-era behaviour as correct
(`test_graceful_stop_alone_still_counts`, justified by "an OEM battery-manager
SIGTERM"), and an operator-facing alert still pointed at `bot.log` and the Android
phantom killer. Three stale assumptions in one function.
**Constraint:** after any platform change, sweep tests and user-facing strings, not
only documentation. An assertion is a claim about the world too.

### C7 — Anchor edits on content, not position
**seen: 5** (2026-07-26, 2026-07-27, 2026-08-02 ×3) — *promoted from the Minor log by
`sweep.py constraints-drift`, its first real find.*
Two edits went wrong the same way: **the surrounding structure was not confirmed before
writing.** A paragraph was added to a function anchored on `n = 0` — a content anchor,
correctly matched — but the docstring had already closed above it, so the prose landed
in the function body and broke the module until `py_compile` caught it. A Routine
prompt was spliced into `routines.md` using line indexes read off `sed` output, off by
one, in a file already edited twice that session.
**Corrected framing (2026-07-27):** the first draft of this entry said both failures
"located the edit point by *where it was* rather than *what it says*". That is only
true of the second. The first used a content anchor and still failed, because the
anchor was right and the assumption about what sat *above* it was wrong. The shared
cause is not "used line numbers" — it is "did not verify the surrounding structure".
Getting this wrong would have aimed the guard at the wrong thing.
**Constraint:** before an in-place edit, confirm what actually surrounds the anchor —
read it, do not infer it. Never address an edit by line number; prefer the Edit tool,
which matches on a unique surrounding string and cannot drift.
**Graduated 2026-07-27 (partially, and the gap is the point):**
`.claude/hooks/anchor-guard.sh`, a PreToolUse hook, blocks `sed -i` carrying a numeric
line address against anything outside `/tmp`/scratchpad. Nine-case matrix; the four
must-not-fire cases (content-anchored substitution, read-only `sed -n`, throwaway
paths, `# anchor-ok`) all pass.
**Occurrences 3-5 (2026-08-02) — the docstring failure again, three times in one hour.**
Rewriting three `sweep.py` scanners, each edit anchored on the first line of the function
BODY and prepended explanatory prose. In all three the docstring had already closed above
that line, so the prose landed in executable position and the module stopped parsing. The
anchor matched exactly what it was meant to match, every time; what was never checked was
what sat immediately above it — which is this constraint, verbatim, five years of
sessions notwithstanding. **The tell is specific and worth naming: prepending prose to a
function body is almost always an edit to its DOCSTRING, so the anchor should include the
docstring's closing `\"\"\"`, not the code line after it.**
**Graduated further 2026-08-02:** the `gate-corpus` eval imports `sweep.py`, so an
unparseable version now fails CI and the corpus run alike — the first mechanism that can
see this failure mode at all. It catches the *consequence*, not the edit; the edit itself
still needs the rule above.

**What it does NOT cover:** the docstring failure. That was an Edit-tool call whose
anchor matched correctly — no hook can see that the *assumption above the anchor* was
wrong. Detecting line-index splicing inside a Python heredoc was also rejected:
`readlines()` + slice + write cannot be matched without false positives, and a guard
that misfires gets disabled. Both halves stay prose here. The existing backstop for the
first is the compile check, which caught it on the next call.

### C8 — Ask what a reading actually measures before concluding from it
**seen: 3** (2026-07-26 ×2, 2026-07-27) — *promoted by check 6 of the weekly hygiene
Routine, from three Minor entries sharing one cause.*
Three conclusions were drawn from readings that did not mean what they appeared to:
- an `/audit` line reporting jules on `mimo-v2.5-pro` was hours old; her model had been
  changed since, and a test recommendation was built on it — **stale**
- `grep '^MODEL='` returned nothing across six instances, read as "no model set"; the
  variable is `NANOGPT_MODEL` — **wrong scope**; the grep was answering a question
  nobody asked
- `/errors` output full of `Conflict` tracebacks was read as a live fight; `errors.log`
  is historical, persists across restarts, and travels inside migration tars — **wrong
  currency**
Two of these sent a live diagnosis down the wrong path for several rounds.
**Constraint:** before concluding from any output, state what it actually covers — how
current is it, what scope does it span, and what would absence of a result mean? A grep
that finds nothing is only evidence if the pattern was right. A log tail proves what was
written, never what is happening now. A reading from earlier in the session is a
historical claim, not a live one.
**Graduated 2026-07-27 — prose, deliberately.** No hook, scanner, or eval can see
"trusted a reading that did not mean what it appeared to": there is no code shape and no
tool call to intercept. Extended
`.claude/skills/fix-the-class/SKILL.md` §"The two questions that catch what greps miss",
which already carries the same family of lesson (`BOT_TIMEZONE` was *referenced*
everywhere and still did nothing). This is the case that forced rule 4 above to admit
skills as a graduation target.

**Graduated 2026-08-02, after a third occurrence (the owner's stated trigger).** Three
instances, one family — a claim stated as settled on evidence that was merely compatible
with it:
1. `_APPEARANCE_DEFAULT` asserted as reachable on live instances without checking the
   launch path (`bot@.service` passes the instance dir, so it never was).
2. `/audit` asserted to show the selfie-base field, which had only been added to the
   startup log line — a different code path.
3. An uploaded image called "confirmed" to be `priya_base.jpg` because `file` reported the
   same 1024x1024 progressive JPEG. Matching size is consistent with sameness and
   establishes nothing; they were different images, and three appearance.txt files were
   written on that footing.
**Sharpened constraint:** state what a reading *excludes*, not only what it is compatible
with. Dimensions exclude almost nothing; a hash excludes everything but the file itself.
**Mechanisms:** `.claude/hooks/claim-guard.sh` + `claim_guard.py` (Stop hook) blocks
identity/sameness claims resting on metadata with no hash — nine-case matrix, RED on the
exact sentence from #3, green on hedged wording, hashed comparisons, tables, and metadata
without a claim. Escape hatch `# claim-ok`. The `audit-keys-rendered` eval pins #2's shape:
any key in `gather_audit_data()` that no user-facing surface renders fails the suite.
**Occurrence 4 (2026-08-02) — and it shipped.** `/setbase` was documented as working as a
photo caption. PTB's `CommandHandler` matches `message.text` only, so it never could. All
eight tests were green because every one asserted on the handler's *source* — `_is_admin`
present, `CommandHandler("setbase"` registered, write atomic — and none exercised dispatch.
**Sharpened further: reading a function's source is not exercising it.** A test that greps
code proves the code exists; whether the framework ever calls it is a different claim
needing a different test. The fix's own test now runs PTB's `check_update` rather than
describing it.

**What stays prose, deliberately:** #1's shape — asserting a code path behaves some way
without exercising it. The text reads identically whether or not the path was run, so no
scanner can see it; rule 4 permits prose exactly here.

### C9 — Verify a load-bearing hypothesis before shipping, not after
**seen: 1** (2026-07-27)
v2026-07-27.1 shipped to `main`, CI-green, on the claim that all six instances had run
for two weeks with their memory-hygiene loops disabled. The claim was **labelled
`[hypothesis]`** in the operational log, in the changelog, and in the report to the
owner — and the release's entire justification still rested on it. It was false: every
`.env` set all three variables explicitly. The evidence that would settle it was one
command, and the owner ran it in one message when finally asked — *after* the merge.

The inference itself was empty, not merely unlucky: bot.py's default and a commented-out
`.env.example` say nothing whatsoever about a live `.env`, and per-instance override is
the normal way this fleet is configured. There was no weak evidence here to weigh, only
the absence of any.

**Constraint:** before a change ships, list what it *depends on being true*. Anything on
that list marked `[hypothesis]` is a blocker, not a caveat — verify it, or scope the
change so it doesn't depend on it. Honest labelling discharges the duty to *flag*
uncertainty; it does not discharge the duty to *resolve* it. Specifically: **this
container cannot reach the fleet, so every claim about live instance state is a question
for the owner.** Ask before, not after — it cost one message here and one rewritten
release entry.

**Relation to C5/C8:** C5 says label a theory as a theory (complied with — and it was not
enough). C8 says ask what a reading measures (this failure had *no* reading to measure).
C9 is the missing third: what a conclusion is allowed to carry.

**Not graduated to a mechanism.** A hook cannot know which of a diff's premises are
load-bearing, and an eval cannot query a machine it has no route to. Prose, deliberately,
per rule 4 — with the concrete precondition written into ROADMAP 4.5 so the next instance
of this exact question hits a check instead of an inference.

### C10 — An unexplained default is not an unintended one: read the registries first
**seen: 1** (2026-07-27)
Having flipped three memory flags to default-on, I grepped for the rest of the "class"
(`os.getenv("X", "0")`), found five, and shipped ROADMAP 4.5 to `main` calling them
policy-grandfathered oversights needing re-decision. Four are the R6 evolution
experiments and were deliberately off, with the rationale written down in **three**
places I did not open: the changelog release title (*"R6 evolution experiments (all
gated, default off)"*), the `.env.example` section header (*"default off, pilot one
instance at a time"*), and — most damningly — ROADMAP's own rejected registry six lines
below where I typed the new item (*"revisit deliberately, not as a checklist"*). The
fifth, `DEVICE_RENDER`, is a cosmetic preference whose correct default is off.

The enumeration was by **code shape**, and code shape cannot distinguish an oversight
from a decision. Both look like `os.getenv("X", "0")`.

**Constraint:** before classifying anything as drift, oversight, or debt, check whether
it was a decision. This repo keeps four registries for exactly that — CLAUDE.md
§"Known-deliberate — do not 'fix' these", ROADMAP §"Rejected or already covered",
`AUDIT-2026-07-10.md` §rejected, and the originating changelog entry. Read the feature's
own release entry and its `.env.example` block before writing a proposal about it.

**The sharpest part:** `verify-external-audit` step 1 *is* this rule — "check the
rejected-claims registries first… any incoming claim matching an entry is closed with a
citation, zero code read" — and I had that skill loaded in the same session. I applied
it to claims arriving from outside and not to a claim I generated myself. **Findings you
produce are not exempt from your own verification protocol**; if anything they are the
ones nobody else will check.

**Not graduated.** A scanner could list default-off flags but not read intent, which is
the whole failure. The nearest mechanical aid already exists — `sweep.py` — and the
lesson is about what to do with its output: a sweep emits *candidates*, and C2 already
says triage every one. Prose, per rule 4.

### C11 — A diagnostic sent into a group chat is an in-world event
**seen: 1** (2026-07-28)
Debugging why priya was silent in the pilot group, I gave the owner `@priya_bot hi` as a
privacy-mode discriminator. It worked as a probe. It is also plain text in a live group,
so it entered jules's ledger and her persisted `conversation_history` as
`Brian: @priya_bot hi` — a handle ending in `_bot`, sitting beside a participant who
never answered. Jules then referred to priya as "a bot that's not gonna answer",
contradicting her own prompt ("To you they're all real people you know"). She did not
break character; she read the evidence I put in front of her and inferred correctly.

The group design works hard to keep mechanism out of the characters' world —
`_group_deliver` is allowlist-built so DM side effects cannot leak in, `/backup` is
refused in groups so state files can never be posted, commands other than `/chatid` are
default-denied. I routed around all of it with a debugging command, because I was
thinking about the handler path and not about the context window it lands in.

**Constraint:** before sending anything into a group chat as a diagnostic, ask what it
looks like *in the fiction*. Commands are safe — `group_guard` raises
`ApplicationHandlerStop` before `handle_message`, so they never reach the ledger or
history. **Plain text is not**: it is permanent, it is shared with every participating
character, and it cannot be cleared from inside the group (`/clear` targets
`update.effective_chat.id`, and commands are refused there). Probe from a DM, use
`/chatid`-style allowlisted commands, or phrase the probe in-world.

**Not graduated.** No hook can see this: the damaging call is the owner typing in
Telegram, not a tool call I make. The mechanical half is already covered by the group
evals; this is the operator-instruction half. Recorded in `group-chat-changes` under the
same reasoning as C1's split between the agent's half and the operator's half.

### C13 — A verification command that cannot fail is not verification
**seen: 4** (2026-07-27, 2026-07-28, 2026-07-29 ×2) — *promoted from the Minor log on the
third occurrence, as that entry said it should be.*
Three times a check was run against the wrong working directory, because this shell
persists cwd across calls and an earlier `cd` had moved it: `find .env.example` read as
repo-root when cwd was `telegram-companion-bot/`; `sed -n fleet-status.sh` failed on a file
that exists; and on 2026-07-29 `bash .claude/evals/run-evals.sh` printed *No such file or
directory*.

**Fourth occurrence (2026-07-29) — wrong *tree*, not wrong directory, and it printed a
green.** Merging the Routine fix, `git checkout main` succeeded and the suite reported
`23 passed, 0 failed` — a clean result that said nothing about my work, because **this
container's local `main` is a stale branch with no merge-base against `origin/main`**
(`ahead 76, behind 65`; `git merge-base` returns nothing, `git merge` refuses as
"unrelated histories"). Only the *count* gave it away: 23, when the suite I had just
extended has 28. A dropped eval count is a weak signal to depend on — a green from the
wrong tree looks exactly like a green.
**Durable repo fact:** merge to main by pushing the branch ref
(`git push origin <branch>:main`, a fast-forward when the branch sits on `origin/main`'s
tip). Do **not** `git checkout main` in a fresh cloud session and merge there.

**The third one exposed the sharper half.** The command was
`bash .claude/evals/run-evals.sh 2>&1 | tail -2 && git add -A && git commit …`. A pipeline's
exit status is the *last* command's, so `tail` returned 0, `&&` did not short-circuit, and
the commit proceeded on an eval run that never happened. The gate reported nothing and
blocked nothing — it could not have.

**What saved it, and what did not.** `.claude/hooks/eval-gate.sh` is a Stop hook that runs
the suite itself, from `$CLAUDE_PROJECT_DIR`, on every turn touching gated surfaces. So the
work was still verified and nothing shipped unchecked. The residual damage is narrower and
entirely mine: **I told the user a suite had passed when I had not seen it pass.**

**Constraint:** run repo tooling by absolute path, or `cd` in the same command. Never put a
gate in a pipeline — `cmd | tail` discards its exit status; capture output and echo `$?`,
or run the gate on its own line and read the result. And never report a check as green
without having read its actual output in this turn.
**Graduated 2026-07-29 — the mechanism already existed, which is the finding.**
`.claude/hooks/eval-gate.sh` is a Stop hook that runs the suite itself from
`$CLAUDE_PROJECT_DIR` on every turn touching gated surfaces, so the enforcement half was
never actually at risk: my broken invocation could not have shipped anything unverified.
No new hook is owed. The reporting half — claiming a green you did not observe — has no
code shape to intercept and stays prose, per rule 4.

### C12 — A command copied out of documentation is a claim about the past
**seen: 1** (2026-07-29)
I handed the owner `curl -fsSL <raw-base>/deploy/vps-sync.sh | bash -s -- emily`, lifted
from CLAUDE.md's Deployment block. It failed twice over: `<raw-base>` was a literal
placeholder I never substituted, and the URL is dead regardless — **the repo went private
the day before, which was the entire point of the release I had just been reading about.**
I had read v2026-07-28.3's changelog entry, which says in its first line that raw URLs 404
on a private repo, and still shipped the raw-URL command, because I copied the deploy doc
instead of the deploy script.

The doc was not lying; it was *stale*. CLAUDE.md described a deploy path that was correct
until 2026-07-28. A command in documentation is a historical claim about how the system
worked when someone last wrote it down — exactly the C8 problem, applied to instructions
rather than to readings.

**Constraint:** before handing over any operational command, take it from the thing that
executes it — the script's own usage header, the unit file, `--help` — not from prose
describing it. If it must come from a doc, check the doc against the most recent change to
the subsystem. Never emit a placeholder (`<raw-base>`, `<instance>`) inside a command you
present as runnable without saying explicitly that it needs substituting.

**Graduated immediately** — `no-live-raw-urls` in `run-evals.sh` fails on any
`curl`/`wget`/`BASE=` line carrying a `raw.githubusercontent` URL unless it is annotated
dead within 6 lines or its file opens with `<!-- evals: raw-urls-historical -->`. The
whole class is now mechanical: seven live deploy instructions across CLAUDE.md,
OPS_MANUAL.md, CHEATSHEET.md, MIGRATION.md and the `deploy-and-verify-fleet` skill were
rewritten to run from the checkout, and the phone-era remainder is annotated.

---

### C14 — A scanner cannot tell "this file does the bad thing" from "this file explains it"
**seen: 3** (2026-07-29 ×3) — *promoted immediately: two fresh occurrences in one session,
and `sweep.py constraints-drift` then surfaced a third already in the Minor log.*
Three times a checker confused executable text with the prose documenting it:
1. An extraction assertion asserted `'list_triggers' not in prompt` — and tripped on the
   new paragraph that *explains* `list_triggers` is unavailable.
2. The `routine-prompts-runnable` eval matched `"(public repo)"` across the whole of
   `routines.md` — and failed on the two prose lines recording that the "(public repo)"
   annotation was the stale thing being removed.
3. **(2026-07-29, found in the Minor log)** `no-live-raw-urls`'s first draft exempted a
   whole file if a marker word appeared early; CHEATSHEET.md's header *explains* that raw
   URLs 404, so the file the check most needed to guard went entirely unchecked.

Note 1–2 fail loud (false flag) and 3 fails silent (false exempt) — the same cause points
both ways, and the silent direction is the dangerous one. In every case the string was a
defect *in one region* (a `### Verbatim prompt` block, a runnable `curl` line) and
legitimate everywhere else. A file-wide match cannot tell those apart, so it makes
documenting a fix impossible — the more carefully a removal is explained, the worse the
check behaves.

**Constraint: before matching a defect string, name the region where it is a defect and
scope the match to it.** If the same string is legal elsewhere in the file, a file-wide
`in`/`grep` is the wrong instrument. Ask "where would this be *correct*?" — if the answer
isn't "nowhere", the pattern needs a boundary, not a longer blocklist.
**Graduated:** the eval now parses `### Verbatim prompt` fenced blocks and only searches
inside them (`.claude/evals/run-evals.sh`, `routine-prompts-runnable`), break-tested RED
on all three branches with the surrounding prose left intact.

---

### C15 — Never `git checkout -- <file>` to revert a break-test edit; re-edit instead
**seen: 2** — documented once already, in `repo-change-control`'s own "Common mistakes"
("this destroyed ~700 lines once"), and repeated 2026-08-01 mid-session on bot.py's
uncommitted command-menu fix. *Promoted directly on the repeat rather than waiting for a
third occurrence — the first was already written down as exactly this trap, which makes
repeating it the more damning of the two, not the more forgivable.*

While break-testing a new regression eval (proving it fails RED before trusting it
GREEN — the correct instinct), a single deliberately-broken line was stripped out of
bot.py with `git checkout -- bot.py` to revert the break-test. `git checkout -- <path>`
restores the file to its last **committed** state, not to "current minus my last edit"
— and bot.py held ~18 lines of real, uncommitted work (17 command-menu additions from
earlier in the same task) at that moment. All of it was silently discarded in one
command, with no error or warning; git checkout succeeds identically whether it's
discarding a scratch edit or a task's worth of real work. Caught immediately by
`git diff --stat` showing zero changes where 18 lines were expected, so nothing shipped
broken — the cost was a full redo of the earlier edits from memory, not a real defect.

**Constraint:** revert a break-test change by **re-editing back to the original text**
— the method every other break-test in this same session used correctly, before and
after this one. Never `git checkout -- <file>` as the undo step, regardless of how
small the intended revert looks or how confident the belief that nothing else changed.
If a checkout-style revert ever seems like the only option, `git status`/`git diff
--stat` first — but the safer default is to just not reach for checkout on a file that
might hold uncommitted work. This class has now cost real content twice; there should
not be a third.

**Graduated 2026-08-01 — `risk-guard.sh` (PreToolUse/Bash).** Blocks `git checkout <path>`
/ `git restore <path>` only when `<path>` is a real file with a live `git diff` right
now — a branch checkout or a checkout of an already-clean file is not what C15 is about,
so those still pass through untouched. Break-tested in an isolated throwaway repo (not
this one): checkout/restore on a dirty tracked file blocked (rc=2) in both `--`-prefixed
and bare forms; the same commands on a clean file, a branch name, and `checkout -b`
allowed (rc=0); the three pre-existing risk-guard checks (force-push to main, root `rm
-rf`, staging `.env`) re-verified unaffected by the addition.

---


### C17 — Count an anchor's matches before writing through it
**seen: 2** (2026-07-31, 2026-08-02) — *promoted from the Minor log; both entries deleted.*
Two edits assumed a string named exactly one place and wrote through it without asking how
many it matched. `replace_all` on the fragment `principle 8` landed mid-sentence in two
different grammatical positions and needed two repair edits. A break-test script whose
*revert* anchor (`asyncio.create_task(maintain_memory(chat_id))`) occurred three times
would have rewritten two unrelated call sites; only an `assert count == 1` stopped it, and
it stopped mid-run with the injection still applied.
**This is not C7.** C7 is about what sits *above* an anchor — the structure you did not
read. This is about how many places the anchor *is*. An anchor can be perfectly
content-addressed, sit in exactly the structure you expect, and still match six times.
**Constraint:** before any programmatic write keyed on a string — `replace_all`, an
in-place `sed`, a `.replace()` in a helper script — count the matches first and require
the count you intend. In a script that is a literal `assert s.count(old) == 1`. Check the
*revert* anchor too: a script that injects and then reverts has two anchors, and only one
of them is usually thought about.
**Graduated 2026-08-02 (partially — the gap is stated):** `.claude/hooks/anchor-guard.sh`
already blocks the positional half (numeric in-place `sed` addresses). The multiplicity
half is not hookable: a hook cannot know whether three matches were intended, and one that
guessed would fire on every legitimate `replace_all` and get disabled. What is mechanical
is the assertion inside the script, now the documented shape in `add-regression-eval`.

### C18 — A break-test proves one assertion, not the check
**seen: 4** (2026-07-27, 2026-07-29, 2026-07-31, 2026-08-01) — *promoted from the Minor
log; all four entries deleted.*
Four checks passed their break-test and were still dead in ways the break-test could not
see. Three faults injected **at once**: two tests failed correctly, the third passed for
the wrong reason (the injection made the function return `None` for every input, and the
test asserted `None`). A backtick-pairing scanner **desynchronized below a fence** and
reported PASS on a clean tree and on an injected bad reference alike — caught only because
one break-test mode refused to go red. A `sweep-ok` pragma matched with a colon the real
markers did not have, so the helper self-reported forever. The first `no-live-raw-urls`
draft let a **whole file** opt out via one exemption.
**The cause is one thing:** an injection exercises the single path it touches. Everything
else in the check — the other assertions, the tokenizer, the exemption logic, the corpus
it will actually run against — stays unproven, and a green break-test reads as if it had
covered all of it.
**Constraint:** inject **one fault at a time**, and re-run the whole check after each.
Break-test against the *real* corpus (the file with the fences, the tree with the
pragmas), never a minimal fixture that omits the structure the check must survive. **A
break-test that will not go red is a bug in the check, not a clean tree** — that is the
signal, and it has now paid out twice.
**Graduated 2026-08-02 (deliberately prose, and here is why):** nothing can observe from
outside whether two injections were applied together — the run looks identical either way.
The mechanical descendants are the products this forced: `sweep.py`'s `SWEEP_BOT` /
`SWEEP_TESTS` / `SWEEP_CONSTRAINTS` overrides exist so a scanner can be pointed at a
deliberately broken corpus, and the `source-assertion` scanner was itself break-tested by
running it against the test suite as it stood *before* the bug it describes shipped.

## Minor — running log

**Mistakes made and fixed mid-task** — the ones that never reach the owner because
they were caught a minute later: a wrong path, a grep for the wrong variable name, a
broken test harness, a script that didn't parse, an assumption corrected the moment
evidence arrived. **These do not earn constraints on their own** — kept separate so
the numbered list above stays high-signal and the `seen: 2` graduation rule keeps
meaning something.

**Log it *because* you fixed it, not despite that.** "I caught it immediately, no harm
done" is the reflex that keeps this section empty and useless. Self-corrected errors
are the highest-frequency signal available — they are invisible to everyone but the
person who made them, they cost real minutes, and they are where the repeating shapes
show up first. A section with nothing in it means under-reporting, not a clean run.

**The promotion rule:** when two minor entries share a cause, delete both and write a
numbered constraint. That is the whole reason to log them; a minor entry nobody ever
promotes was still worth ten seconds to write.

**Last promotion pass: 2026-08-02** — `sweep.py constraints-drift` reads this line and
counts only what has arrived *since* it, which is what "is another pass worth running"
actually asks. **Update the date whenever you run a pass**, including one that promotes
nothing. Counting the *total* instead is what made the check useless: the 2026-08-02 pass
promoted six entries into C17/C18 and left 19 with no shared causes, and a total-based
threshold would have demanded a seventh pass that could only invent clusters.

**Archiving:** an entry earns its place by being available to pair with a *future* one.
After 30 days nothing has, so move it under `## Minor — archived` at the bottom — kept
verbatim and searchable, just out of the promotion count. The scanner names the entries
that are due. Archiving is not deletion and needs no judgement call; promotion does.

Format: `date — what happened → what to do instead`. One line. Newest first.

- 2026-08-02 — Handed over seed-placement blocks written as skip-if-exists (`[ -f x ] || cat > x`),
  then reported the Portland→Olympia relocation shipped. Every instance that already had the file
  silently no-op'd, and Emily kept saying Burnside for a further two rounds. → **a placement block
  is a write, and a write that silently declines is not a write.** When the intent is "this file
  should now contain this", the block must overwrite (with a timestamped `.bak`) and the
  verification must read the file back, not check that the command exited 0. Skip-if-exists is
  correct only for *seeding something absent*, and then the report must say "seeded where missing",
  never "updated". C13 family — the exit status could not fail.
- 2026-08-02 — Read seven `/audit` outputs and reported "life.txt missing on priya, marcus,
  jules". Nora's line said `MISSING: life.txt, setting.txt` too, so it was four. Then handed over
  `cat /opt/telegram-bots/nora/life.txt` as the way to see the file format — naming the one bot in
  that group guaranteed not to have one. → when summarising several structured outputs, extract
  the field from each into a list and read the list, rather than forming an impression while
  scrolling. Seven near-identical blocks is exactly where the eye fills in what it expects.
  C8 family: the reading was there, I just did not actually perform it.
- 2026-08-01 — Wrote a source-scanning test that failed twice before it was right: first it
  flagged its own explanatory comment (the block describes the wording it forbids — C14 exactly,
  and I wrote the C14 shape into a fresh test the same day I had it in front of me), then the
  substring `"he "` matched inside `"the "` in an innocent inline comment. → a scanner over source
  needs BOTH: strip comments (describing a defect is not committing it) and match on word
  boundaries, never bare substrings. Two failed runs is cheap; a scanner that greens on the wrong
  thing is not.
- 2026-08-01 — Wrote a conditional as `if X and not f.__wrapped__() if False else (X and f())`
  — leftover scaffolding from two half-finished versions of the same line, committed to the file
  in one Edit. Syntactically valid, semantically nonsense, and it would have compiled. Caught on
  re-reading my own diff before running anything, and rewritten as a plain `if` with the two
  claims separated. The cause was editing *while* still deciding the logic → settle the condition
  in full before writing the Edit; an `if` that needs a ternary escape hatch to express is a sign
  the branch isn't decided yet, not a sign it needs clever syntax.
- 2026-08-01 — Recommended a durable guardrail (a `bot-code-invariants` rule) for an
  external commit's lesson *before* reading how the target code was organised. One grep
  later — `SELFIE_EXPRESSIONS/FRAMINGS/OUTFITS/ACTIVITIES/CAMERA` are all already hoisted
  module constants — showed the refactor itself removes the wrong-pattern example, making
  the rule redundant, and that the class has zero occurrences here against a standing bar
  of two. Self-caught and reversed in the next turn, but the first answer would have added
  a speculative rule 18 to a file whose 17 rules were each earned by an incident → read the
  code's existing organisation before proposing machinery to protect it; "is this already
  solved structurally?" comes before "what rule would prevent this?" (C2 family: name the
  class — and check it exists — before building for it).
- 2026-07-31 — Grepped `routines.md` for Routine headings with `| head -20`, saw no
  `character-pass-monthly`, and started writing it up as doc drift; the heading was at
  line 242, past the cut. → **A `head`-truncated grep proves presence, never absence.
  Re-run unbounded before reporting anything missing.**
- 2026-07-31 — Ran a second Bash call assuming a fresh working directory after the first
  had `cd`'d into `telegram-companion-bot/`; four path checks failed as "No such file".
  → **The Bash working directory persists between calls: use absolute paths, or `cd` in
  every call that depends on one.**
- 2026-07-29 — Asked why the ops brief can't reach GitHub, I investigated from this
  container's working tree without fetching first, concluded "routines.md is out of sync
  with the live Routines, that's why it halts", and rewrote the file. All of it was
  already fixed on `origin/main` — six commits ahead of me, one of them the same routines
  sync with a *better* root cause. Wasted ~10 calls and told the owner a wrong diagnosis.
  Caught only because `git push origin main` was refused as non-fast-forward → **another
  session may be pushing to this repo right now: `git fetch origin main` and compare
  before diagnosing anything, not just before merging.** Distinct from C13's fourth
  occurrence — my local `main` was a true ancestor, merely 6 commits behind, so nothing
  looked wrong and the eval count was correct.

- 2026-07-30 — Shipped a written recommendation to "move the standing-authorization text
  into CLAUDE.md and delete the per-turn hook" **without having read the hook.** Its
  docstring rejects exactly that, with a mechanism that holds: the text must land *later in
  the conversation* than a server-side system-prompt injection, "which a CLAUDE.md line
  cannot do." The measurement behind the finding (O(turns) cost for invariant content) was
  right; the prescription was wrong because it read a positional requirement as redundancy
  → **before recommending that something be deleted, read it — especially when it looks
  redundant.** Redundant-looking machinery in this repo is usually load-bearing and usually
  says so in a comment. (C9 family: an inherited or inferred prediction is a hypothesis.
  This one reached the owner in a delivered audit before I caught it, so it is a near-miss,
  not a clean self-correction.)
- 2026-07-30 — Wrote `skill-index-integrity` to catch indexes that describe a reality that
  isn't there, then made the check a file-wide grep for "preloaded always" — and the same
  commit added a sentence to `skill-router` *explaining* the removed claim. The new eval
  went RED on a clean tree, flagging my own prose. Fixed by rewording the explanation so the
  file contains no live-looking claim, rather than by adding an exemption → **C14 is not a
  historical footnote; it is the default failure mode of writing a check and its
  documentation in one pass.** Write the check, then re-read the same commit's prose as if
  the scanner wrote it. (C14, `seen` unchanged — caught by the check itself, which is the
  system working.)
- 2026-07-30 — Ghost-token audit: reported card↔preset-layer duplication as "emily 38
  shared 8-grams", a number I was one sentence away from putting in a findings table. It
  measures nothing an owner can act on — consecutive shingles overlap, so 38 of them were
  **4** distinct passages (~87 tok). Re-measured with maximal common word-runs before
  writing it up → **a similarity count is not a quantity of waste.** When a metric is a
  proxy (shingles, matches, hits), convert it to the unit the decision is actually in
  (tokens, files, dollars) before it reaches a report. (C8 family: ask what the reading
  measures — here the proxy inflated the finding ~9x in the direction that made it look
  more important.)
- 2026-07-29 — Quoted a `for … ; do` loop as a two-line fragment to *illustrate* a change,
  with no body and no `done`. The owner pasted it and bash sat at a `>` continuation
  prompt — "didn't return to the command prompt" → **a fenced bash block is read as
  runnable, whatever it was meant to illustrate.** Show partial shell as prose or with an
  explicit `# fragment, not runnable` marker, or show the complete construct. (C12 family:
  the first case was a command that could not authenticate, this one cannot even parse.)
- 2026-07-29 — Told the owner `grep -c Warren emily_harper.json` should "expect 1". It is
  2 — the lorebook key *and* the content line, in a file I had written myself an hour
  earlier. The deploy was correct; my predicted value was wrong, and a wrong expectation
  handed to an operator reads as a failed deploy → when stating the expected output of a
  verification command, **measure it against the repo copy first**, don't recall it. (C3's
  neighbour: a check with a wrong expected value is as misleading as one that cannot fire.)
- 2026-07-28 — Wrote two full drafts of `preset-marcus.txt` arbitrating a paragraph-length
  conflict, because the handoff predicted his card would fight `preset-core.txt` "the way
  Bonnie's did". It doesn't: Bonnie's card states a numeric contract, his states no length
  at all. I had reasoned about the arbitration from `preset-core.txt` alone and had not
  read the other three layers in his stack; the real conflict (`preset-explicit.txt`'s
  standing-consent block deleting his defining behaviour) only appeared when I did →
  a per-character layer arbitrates against the WHOLE stack. Read every layer the instance
  will load before writing the one that resolves them. An inherited prediction is a
  hypothesis, not a finding (C9 family — this one was caught before shipping).
- 2026-07-28 — Filled the `.env.example` stack row for marcus by doing arithmetic off the
  table's own published numbers (8501 − emily's layer + marcus's) instead of measuring.
  The table is stale: `preset-core.txt` and `preset-explicit.txt` have grown since those
  rows were written, so every row reads ~60 raw low and my derived figure inherited the
  error → measure, don't derive from a published figure whose measurement date you did not
  check (C8 family). Fixed by measuring and annotating the staleness in the table.
- 2026-07-28 — `anchor-guard.sh` blocked a *content-anchored* `sed -i 's/^Layer is …/'`.
  Not my mistake and not a guard bug in the dangerous direction, but worth recording: line
  28 scans the entire command string for a line-address shape, and the `grep -n "434 raw
  tokens…"` half of the same compound command supplied `"` + digits + space + `r`, which
  is in its `[acdipsr]` command-letter class → the guard cannot tell which segment of a
  compound command the address-shaped text belongs to. Fail-safe direction, but "a guard
  that misfires gets disabled" is this file's own rule (C7), so it needs either
  per-segment matching or a note in the skill.
- 2026-07-27 — Break-tested the C1 hook through a bash heredoc; backtick escaping meant
  the code fences never reached the transcript, so all three cases "passed" and the
  guard looked dead. The *test* was broken, not the code → when a break-test shows
  nothing firing, suspect the harness before the check. Build fixtures in Python, not
  shell quoting.
- 2026-07-26 — `paste -sd '; '` in session-audit.sh produced `C1;C2 C3`: `-d` takes a
  *cycling list* of delimiter characters, not a delimiter string → join with one
  character, then substitute.
- 2026-08-02 — `risk-guard.sh` blocked a script because the script *quoted* a constraint's title, which contains the command pattern the guard forbids. Nothing was being run; the words were an anchor string. C14 exactly, in a hook rather than a scanner, and the second time this week a guard fired on prose about the thing it guards → when a helper script must mention a forbidden pattern, put the script in a file and run the file; do not inline it where a PreToolUse hook reads the command text.
- 2026-08-02 — Wrote the archiving rule into the Minor header, naming the archive heading mid-sentence, and the scanner's own section-splitter matched that mention and truncated the active log to zero entries. `constraints-drift` then reported a confident **0 candidates** — the all-clear and the blind failure are the same output. Caught only by printing the parsed entry count instead of trusting the summary line. → **a heading used as a parse marker must be matched line-anchored**, because the document will eventually describe its own structure. C14's third appearance this session (test, hook, parser) and the one that actually produced a wrong answer.

## Minor — archived

Entries that sat 30 days without pairing with anything. Kept verbatim — they are still
searchable evidence, and a shape that reappears after two months is worth finding — but
out of the promotion count, per the archiving rule above. Newest first.

*(empty as of 2026-08-02: the whole active log is 8 days old, so nothing is due yet.)*
