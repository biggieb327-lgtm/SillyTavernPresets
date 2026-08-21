# 2026-08-07 — routines md external ideas drift

Archived from `.claude/memory/operational-log.md` on 2026-08-21, verbatim. The row
there is the index entry; this is the full record, including every correction
appended after the fact.

## Failure

**`routines.md` had been silently wrong about both monthly Routines' external-ideas step since 2026-08-03, in two layers.** First layer: the file still described a curl-to-reddit.com step (permanently SKIPPED since 2026-07-20) while the live Routines had actually been running a WebSearch-only scan with Reddit dropped entirely for two weeks. Second layer, found only after the fact: `origin/main` had *already* correctly documented and applied that exact drop via two 2026-08-03 commits (`5f6f4f0`, `b10672b`) — this session's own branch was built from a merge-base ~150 commits behind, so it rediscovered and redocumented history `main` already had right, then only surfaced the divergence when a same-branch `git push origin <branch>:main` was rejected as non-fast-forward

## Root cause

`[observed]` `list_triggers` on both `trig_012bvUUnBtnaE87CbBkjyAaZ` and `trig_01VXMxTLk8ZKwQ61tC3JxkCA` showed `updated_at: 2026-08-03T23:4[89]:*`, prompts already reading "External ideas... Reddit is out of scope as of 2026-08-03" — none of which existed in this branch's stale local `routines.md`. `[observed]` `git merge-base HEAD origin/main` resolved to `dee2058`, ~150 commits behind `origin/main`'s tip, including `5f6f4f0`/`b10672b` which independently diagnosed and applied the identical Reddit-drop the branch was re-deriving from the live trigger. `[code]` the 2026-07-29 operational-log row already named the exact gap this recurrence fell into: "removing hygiene check 4 leaves no automatic Routine-drift detector — the new eval guards the file's content, not file↔live-trigger equality, which is unreachable from CI." That gap sat open 9 days before it bit

## System patch

Backfilled the missing 2026-08-03 history into `routines.md`, then layered the owner-requested Reddit + Substack integration on top — first via a custom `idea-scraper-actor/` Apify actor, then retired the same day in favor of calling Apify's hosted `trudax/reddit-scraper-lite` (`oAuCIx3ItNrs2okjQ`) directly, both live triggers updated via `update_trigger` to match. Separately, merged `origin/main` into the branch before pushing (rather than force-pushing over it), reconciling this file, `constraints.md`, and `routines.md`'s independently-written 2026-08-03 history by hand instead of picking one side

## Eval

routine-prompts-runnable (pre-existing) still passes — it checks the file's own content, not file↔trigger equality, so it would not have caught either layer and does not claim to. No new eval: the check that would catch the first layer (`list_triggers` diff) is MCP-only and cannot run in CI; the second layer (stale merge-base) has no CI-visible signature either — it only shows up as a rejected push, which is the actual mitigation already in place

## Next

**The file↔live-trigger equality gap named on 2026-07-29 is now confirmed to bite, not just theoretical.** The second layer is new: a session's local branch can be stale against `origin/main` by a wide margin even with a real (old) merge-base, not just the no-merge-base case C13 already names — logged as a fresh Minor entry (2026-08-07) rather than folded into C13, since the failure mode (redundant rework, not a false-green check) differs from C13's.

