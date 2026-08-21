# 2026-08-02 — features command never flipped

Archived from `.claude/memory/operational-log.md` on 2026-08-21, verbatim. The row
there is the index entry; this is the full record, including every correction
appended after the fact.

## Failure

**`/features <name> on|off` never flipped anything on any instance, and said nothing when it failed.** Found by a `/code-review` pass over the day's 13 releases, not by use.

## Root cause

`[code]` `features_cmd` ended with `_, probe = _FEATURES[name]` — the specs became 3-tuples in `v2026-08-02.10` when the detail probe was added, and this unpack still expected 2, so **every** flip raised `ValueError` before reaching `globals()[...] = want`. `[external]` PTB logs and swallows a handler exception, so the owner saw silence, not an error. `[code]` The `probe` name it bound was never used, so no linter flagged it. **Why the suite was green: the two tests covering this command assert on its *source*** — one checks the specs are 3-tuples, the other greps the handler text for `_is_admin`. Neither calls it. Fifth member of the family `v2026-08-02.4` named (C8), second to reach the fleet. `[code]` Four more defects of the same *review* pass shared a different shape — **a flag frozen at import while the thing it gates is switched at runtime**: `STRESS_ALERTS`/`BB_ALERTS`/`RHR_ALERTS` were `GARMIN_ENABLED and <env>` evaluated once, so `/features health off` reported off while the monitors kept firing; the Garmin and traffic jobs were *registered* under their switches, making off a one-way trip until restart.

## System patch

`v2026-08-02.14`: unpack deleted; `_alerts_on()` ANDs the live parent at call time and every monitor gate goes through it; Garmin + traffic jobs register on **capability**, since each already re-checks its own gate when it fires; `_feature_off_reason()` ends the "off" vs "never configured" conflation across 8 commands (`v2026-08-02.9` split `*_capable`/`*_ready` for exactly this and 8 call sites never adopted it); `send_triggered` sends the GIF it computes; `/setbase` tracks whether it made a backup instead of stat-ing `.prev` afterwards.

## Eval

18 new tests (885 total), **all five code fixes break-tested RED by re-injecting the original**. The `/features`, `send_triggered` and `/setbase` tests drive the real handlers with fake Telegram objects, so they fail on a broken dispatch path rather than a changed string. 33/33 evals.

## Next

**The reusable shape: a test that reads a handler's source cannot fail for the reason the handler exists.** Three separate releases this week (`.3`, `.9`, `.10`) added source-asserting tests to this same command family and all three stayed green through a crash. `add-regression-eval`'s break-test rule is the existing defence and it was followed — but a break-test only proves the check fails when the *asserted string* changes. **Closed same day:** `sweep.py source-assertion` now names every `*_cmd` the tests mention but never call (12 today), and the delivery gate blocks a turn whose diff touches one of them — break-tested four ways, including against the test suite as it stood *before* this bug shipped, where it names `features_cmd` and `setbase_cmd` and nothing else. `handlers-exercised` (eval 34) pins the three already paid for. The promotion pass also ran: C17 (count an anchor's matches) and C18 (a break-test proves one assertion, not the check) absorbed six Minor entries. The Minor-log threshold was reworked the same day rather than left firing: `constraints-drift` now counts entries added **since the last promotion pass** (new `**Last promotion pass:**` header line) instead of the total, archives entries unpaired after 30 days, and ranks pair candidates by rarity — 96 pairs down to 14, top 5, and only when a pass is due. Five break-tests, one injection at a time, all RED against a 0 baseline. **`[observed]` Deployed to all seven 2026-08-02; owner confirms `/audit` reports `2026-08-02.14` on each.** **`[observed]` Closed 2026-08-02, owner-confirmed in production:** `/features voice off` then `on` both replied and both took effect on a live instance — the handler that had raised `ValueError` on every invocation for four releases. That is the fix verified where it matters; `/audit` only ever proved the version landed. **`v2026-08-02.15` also deployed to all seven the same day** (`/audit` reports it on each): the `/features` listing now carries the same detail `/audit` does — voice backend, GIF safety level, selfie provider — through one shared `_feature_detail()`, because the command dedicated to features had been saying less about them than the general audit line.

