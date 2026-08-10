# Session autopsy — 2026-08-10

One session, nine commits, five bot releases (`v2026-08-10.8` → `.12`), plus a constraints
promotion pass and a content pass on two atlases. Everything shipped green and CI is clean
on every commit. This document is about the mistakes made getting there, what they have in
common, and what should change.

Counted from the transcript, not from memory. Where a number is a floor rather than a
total, it says so — which is itself one of the findings.

## What shipped

| commit | what |
|---|---|
| `537148f` | cass + bonnie atlases: a real place in every public entry |
| `ffbde83` | C21 minted |
| `90f414d` | `.env.example`: TomTom is fleet-wide; the key is not the feature switch |
| `ee958af` | `.8` — `MAP_INTENT` defaults on; `mapintent`/`foodsuggestions` become reportable |
| `41f156e` | `.9` — one on/off vocabulary for all 55 boolean env vars |
| `a3e0321` | constraints promotion pass: C22 minted, C8 → seen 7, 7 Minor entries retired |
| `8499bbf` | `.10` — `/audit` reports the map-intent fire rate |
| `9c5910e` | `.11` — `/audit` says what the error count actually is |
| `166e9bd` | `.12` — a poller fight is not a code crash; storms stop eating the log |

## The mistakes, grouped by actual cause

### A. A verification instrument that could not fail, or did not measure what I read it as

**Five occurrences, and this is the dominant pattern of the session.**

1. Two break-test injections matched **0** and **4** anchors instead of 1. Neither changed
   the file. pytest came back green both times and I read those greens as "the check
   holds" — they meant "the defect was never introduced."
2. A break-test revert dropped a leading newline, folding a restored dict entry into the
   comment above it. Python read it as a comment, `py_compile` passed, and only the full
   suite caught it two steps later. **I proved the check RED and never proved it GREEN
   again.**
3. Break-tested the new `session-audit.sh` staleness check in a clone checked out at
   `origin/main` — which predated the commit adding that check. I tested the *old* hook and
   got no output, then debugged the wrong thing.
4. `python3 -m py_compile bot.py` reported clean on a module that could not import
   (`_ERROR_LOG_THROTTLE_S` placed ~120 lines above `_env_int`). Compiling checks syntax,
   not name resolution at module exec.
5. A handed-over `.env` check used `grep … | cut … || echo '(car)'`, where `||` tests
   `cut`'s status, not `grep`'s — so "absent" and "empty value" rendered identically, and
   the fallback could never fire. A second column matched `=1` only, while the code accepts
   `1|true|yes`.

Existing constraints circle this: **C3** (prove RED before GREEN, seen 3), **C13** (a
command that cannot fail is not verification, seen 6), **C18** (a break-test proves one
assertion, seen 4). All three graduated to **prose or skills**. It recurred five more times
today.

### B. A copy of the thing consulted where the thing itself was one command away

Promoted to **C22** this session (seen 5), graduated to the `session-audit.sh` merge-base
warning. One more occurrence *after* minting it: I offered to "rotate or truncate"
`errors.log` without reading `bot.py:144`, where `RotatingFileHandler(maxBytes=2_000_000,
backupCount=3)` had been configured all along. C22 was written and then broken within the
same session.

### C. A floor reported as a total

- "~20 hand-rolled boolean idioms" went into a **shipped changelog**. The real number was
  **55**, and a third idiom matched neither pattern that produced the estimate.
- "~250 Conflict events over 87 minutes" — the real figure was **767 over seven hours**.
- The 2026-07-19 operational-log row said the poller fight lasted **~15 minutes**. It
  lasted about **seven hours**; the record was wrong by a factor of 28 for three weeks.

Absorbed into **C8** (seen 5 → 7) as its *wrong sample* / *wrong instrument* bullets.

**The uncomfortable part:** `v2026-08-10.11` exists because `/audit` reported a capped
floor as a total. I shipped that fix and went on making the same error in my own reports
for the rest of the session.

### D. Output engineered to be unfalsifiable

Left atlas entries describing places without naming them, and wrote the reasoning into two
header comments as policy — *"a generic landmark can never be factually wrong."* Shipped
twice, on bonnie and then cass, with the defence copied forward. Promoted to **C21**.

## What worked, and should not be quietly disbanded

- **The hooks fired five times and were right every time**: `risk-guard` blocked a stray
  `git checkout` over uncommitted work; `anchor-guard` blocked a line-numbered `sed`;
  `host-guard` twice caught an unlabelled VPS command block; `handoff-guard` caught relative
  paths in a handed-over block.
- **A mechanism added mid-session paid off inside the same session.** After the two silent
  non-injections, the injector was changed to assert its match count and print it. The very
  next break-test (`.11`, cap hardcoded to 999) matched 0 anchors and the injector refused
  to run — turning what would have been a sixth false green into a caught error.
- **`verify.sh` caught the `py_compile` gap** — not via its compile step, which passed, but
  because pytest could not import the module. The suite covered for a check that lied.
- **The owner's corrections were load-bearing three times**: the atlas-audit framing
  ("they're not real places"), the `/diag` Garmin display bug, and rejecting the
  unfalsifiable atlas entries.

## Decisions

### 1. Build `.claude/tools/break-test.sh` — the procedure gets a mechanism

Break-testing is what the repo relies on to trust every check it has, and it is performed by
hand every time. In this session's later half roughly **eighteen** break-test runs produced
**five** defective ones (~28%): three that injected nothing, one that tested the wrong
build, one whose revert silently corrupted the file.

The tool must, in one invocation: assert the anchor matches **exactly once** and refuse
otherwise; snapshot the file; inject; assert the file actually changed; run the given
command and **require non-zero**; restore from the snapshot; assert the file is byte-identical
to the snapshot; re-run and **require zero**. Print all six facts. Anything less reproduces
one of today's five.

**This is a direct rebuttal of C18's graduation note**, which said prose was chosen because
*"nothing can observe from outside whether two injections were applied together."* That
reasoning is sound for its own case and does not extend to the two failures seen today —
"did the injection land" and "did the revert restore" are both mechanically observable, and
neither was being observed. C18 should be updated to say so.

### 2. `verify.sh`'s compile step should import, not compile

**Corrected while implementing — the premise was wrong.** `run-evals.sh`'s `bot-imports`
eval has imported bot.py under a fixture since the v2026-07-11 NameError incident, and its
comment already says py_compile cannot catch that class. `verify.sh` runs it at step 3, so
the coverage was never missing. Break-tested to confirm: with the defect injected,
`bot-imports` fails.

What was actually wrong is smaller and worse. **The step's label lied** — `ok  compile
bot.py` on a module that could not load — and I ran `py_compile` *standalone, by hand*,
read that green, and moved on without running the harness that already knew better.

The change is still worth making (step 1 now means what it says, and fails fast) but it
closes no gap. **This is C22 for the third time in this session — proposing a mechanism
without checking whether the mechanism existed, while writing up the session's other
mistakes.**

### 3. C18 gets the two observable sub-cases, and graduates mechanically via decision 1

Not a new number — this is C18's own shape, and minting C23 would split one lesson across
two entries. Its "deliberately prose" note is now partly falsified and should be narrowed to
the multi-injection case it actually covers.

## What happened when these were built

**The break-tester's first version truncated `bot.py` to zero bytes.** `trap restore EXIT`
guarded on `[ -f "$SNAP" ]`; `mktemp` *creates* that file, so the guard was true before the
snapshot had been taken, and the first early exit — a 0-match anchor, the precise failure
the tool exists to catch — copied nothing over the target. It was caught immediately,
because the tool's failure modes were exercised rather than assumed, and `bot.py` was
restored from `git show HEAD:` (not `git checkout` — C15) byte-identical.

Two things follow. **A cleanup trap must prove the thing it restores was ever captured**;
`mktemp` existing is not the resource existing. And the tool now ships with
`break-test-selftest.sh`, pinned by a `break-tester` eval, which drives all six paths on
temp files and asserts the one invariant that was violated: whatever happens, the target is
byte-identical afterwards. Re-injecting the original trap bug turns it red on exactly the
two early-exit cases.

That a session about verification instruments produced, as its fix, an instrument that
destroyed a source file on its first run is the strongest available argument for the
constraint it implements.

## Deliberately not done

- **No new constraint for group C.** C8 already absorbed it this session at seen 7. A
  fourth entry describing the same reasoning error would dilute the numbered list rather
  than sharpen it.
- **No mechanism proposed for "a floor reported as a total" in prose.** Nothing can read a
  sentence and know whether the number behind it was capped. The counter-measure that
  actually worked today was structural — `_error_retention()` returns `saturated` as data,
  so the floor is visible at the source rather than remembered at the keyboard. Where a
  number can carry its own provenance, make it; where it cannot, no hook will help.
