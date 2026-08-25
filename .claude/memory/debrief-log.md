# Debrief ledger

One row per `session-debrief` run. Exists because **the reach-rate cannot be measured from
inside a session**: `evidence-log.sh` writes to the gitignored `.claude/.runtime/`, and
session transcripts live in an ephemeral container — after a restart there is exactly one,
the current session. The repo is the only durable substrate, so the record has to live here
or not exist.

**What this measures:** commits of real work between recorded debriefs. That is a proxy for
"is a debrief overdue", surfaced by `session-audit.sh` at the start of the next session,
where it is actionable.

**What it deliberately does NOT measure:** whether the debrief was reached for unprompted
or asked for. That distinction matters and is exactly the thing a self-report cannot
establish — the agent whose reliability is in question is not a witness to it. The owner is
the only reliable observer of that, and this file does not pretend otherwise.

**No threshold yet.** One session is one data point, and picking a "debrief every N commits"
rule from it would be the estimate-as-fact trap this repo has already paid for twice.
`session-audit.sh` reports the number without judging it. Set a threshold once there are
enough rows to see a distribution.

## Why there is still only one row (2026-08-21)

The skill, `debrief-check.sh` and this ledger were all built on 2026-08-11, and the single
row below is that session recording itself. **170 commits of real work later, nothing had
run the skill again.** The tooling was never the problem — `debrief-check.sh` works and is
honest about what it cannot check. Nothing invoked it.

The only prompt was a `session-audit.sh` line saying "run `debrief-check.sh` when this
session reaches a stopping point": a request delivered at the **start** of a session about
something to do at the **end**, by which time it has scrolled away or been compacted out.
That hook's own comment argued SessionStart was the only actionable moment. One row in ten
days settles it — a reminder nobody acts on is not actionable, whatever the reasoning.

The ask now lives in **`.claude/hooks/debrief-nudge.sh`**, a Stop hook that fires once per
session when the tree is clean and the session committed something that day. It does not
judge whether the work deserves a debrief; `debrief-check.sh` still owns that and can
answer "not a stopping point yet". Deliberately no commit-count gate — that would be the
invented threshold this file has twice refused, and firing on every session that ships
something is also what produces the rows a real threshold would need.

**Read the next several rows as measuring the nudge, not the ritual.** If they cluster at
one row per working session, the mechanism works and a threshold becomes answerable. If
rows appear and say nothing worth keeping, the gate is too loose and should tighten.

Append with: `bash .claude/tools/debrief-check.sh --record`

| date | head | commits since previous | notes |
|---|---|---|---|
| 2026-08-11 | d3fa2b1 | 28 (first row — counted from 3ecd5db, the session's starting point) | first run of the skill, on the session that produced it; C23 minted, C22 → 7, 4 Minor entries retired |
| 2026-08-21 | 87f6b83 | 174 | **First run reached by `debrief-nudge.sh` rather than by asking** — the hook shipped this session and fired on its own first live stop. Found the session's biggest defect *during* the harvest, not before it: 12 of 15 evals reported PASS on a dead parser. C13 → 9, C14 → 5, 3 Minor entries, 5 evals added (41 → 46). |
| 2026-08-22 | 563ab65 | 13 | Artifact-only session (Fleet Graphs workflow diagrams). All 13 commits belong to the prior session that ran earlier today; this session produced 0 commits, 0 code changes. Nudge fired on per-day commit count, not per-session. No constraints to update, no incidents. verify.sh RED is missing PIL/pytest in container, not a regression. |
| 2026-08-23 | 46c736f | 6 | Shipped `/fire` — the fleet's first **proactive** location alert (Seattle Fire real-time 911, `kzjm-xkqj`, ~5-min feed), after `/crime` + `/dispatch` (pull-only) earlier in the session. The user's "alerts aren't working" was correct-by-design: pull-only + daily-lagged data; the fix was a genuinely near-real-time feed, fire/EMS only (no free real-time police source exists). Step-7 `/code-review` caught **4** real dedup bugs a green 1300-test suite missed (id-less re-alert, away-return backlog dump, unbounded set, dropped-past-limit) — all fixed + regression-pinned. Merge integrated a concurrent `v2026-08-21.4` release off main; CHANGELOG had to be reconstructed (main's preamble was misplaced). 2 Minor entries, 0 new constraints, 0 mechanisms owed. CI on `13d79b2` confirmed `completed \| success`. |
| 2026-08-23 | 9bc5bd9 | 14 | Self-improvement session (machinery-only, no bot.py). Benchmarked the repo against 2026 SOTA on self-improving agents → the one real gap was meta-eval of the learning layer, built as the `MECHANISM REVIEW` startup line + `mechanism-recurrence-surfaced` eval; dated the 6 undated graduation markers and widened it; then closed two guard-integrity gaps (`hook-python-compiles`, `hook-refs-exist`, `shell-scripts-parse` over `tools/`). New `watchlist.md` for sub-threshold items (3 open). Harvest: C18 → 7 (a break-test that went red for the wrong reason, self-caught), 2 Minor near-misses (git-dates-from-a-bulk-import, a non-gap almost listed — both caught by grepping first), 1 oplog row. 4 evals added (46 → 50). The hubris discipline (review-not-verdict) was the session's spine and caught 2 would-be false findings. verify.sh RED locally is missing PIL/pytest in container, not the work; CI on `bce41cd` (all code changes) confirmed `completed \| success`, `9bc5bd9` (docs-only harvest) in progress and expected green — same content the local 50/0 suite passed. |
| 2026-08-24 | 468d090 | 3 | Single-purpose machinery session (no bot.py). Baked the owner's separate-reviewer prompt — judge only against the standard, list every shortfall before saying anything positive — verbatim into all three reviewer agents (adversarial-critic, qa-engineer, character-reviewer), and pinned it with the new `reviewer-stance-present` eval, which decides "reviewer agent" from the frontmatter description verb (review/verif/critiqu) so it reaches reviewer agents not yet written. Break-tested both ways RED (stance stripped; detector matches nothing); full suite green (50 → 51 evals). Harvest: 1 Minor near-miss (backslash in an f-string expression — 3.12-only, caught before running), 0 new constraints, 0 mechanisms owed. verify.sh RED locally is missing python-telegram-bot in the container (import/pytest), not a regression — bot.py untouched and parses clean. Not merged to main: session pinned to `claude/reviewer-agent-prompt-gamqk3` by instruction. CI on 468d090 to confirm by hand. Open: `/code-review` + `/security-review` run inline, not as spawned reviewers, so they don't inherit the stance — extend only if owner wants it. |
| 2026-08-24 | 80ef179 | 31 | Continued the morning's merged selector/immutable-release work with ROADMAP 6.2 (sleep-time compute). Shipped two "what nightly can absorb" slices — proactive-hook pre-draft (`v2026-08-24.6`, `NIGHTLY_PREDRAFT`) and ambient-news refresh (`v2026-08-24.7`, `AMBIENT_PREDRAFT`) — and closed slice 3 (selfie pre-selection) as not-applicable after tracing `build_selfie_prompt` (local `random.choice`, no LLM to move; pre-generating would reintroduce the `v2026-08-01.7` frozen-snapshot bug). **Harvest — 1 Minor slip:** asserted "redistributes an existing call, adds none / net-neutral" across 4 files from design intent *without counting the call sites*, when the old call fired only per-send and the nightly one fires a fixed count under heavy gating (so it's a small net *increase* on quiet days). Caught by `/code-review` (repo-change-control step 7, the exact mandated mechanism) and corrected before merge. Adjacent to C8 but outside its readings/samples scope — a cost-count assertion, not a misread reading — so NOT folded into C8 (still seen 8); kept standalone Minor at seen 1. 0 new constraints, 0 mechanisms owed (already guarded by step-7 review). **What worked:** `/code-review` caught the overclaim plus 3 real slice-2 findings; the boolean-flag census test caught a missing DEFAULTS entry; trace-before-build correctly killed slice 3 (C19/C20 discipline in the positive direction). `theory-guard` fired (false positive on already-pasted output). **Open:** 6.2 item 4 (`/reviewlife`, = 5.9) is a feature not a thin slice — mycelium handoff written with a stopping rule; deploy of `.6`/`.7` to the VPS pending (owner runs `vps-sync.sh`; `/audit` must show `2026-08-24.7`). CI on `80ef179` confirmed `completed | success` by hand (run #1003). |
| 2026-08-25 | d332fc8 | 7 | Two releases across one conversation (3 of the 7 commits belong to the prior session). **5.9 `/reviewlife`** (`v2026-08-24.8`): the nightly `reflect()` pass now drafts one-line living-file additions (life/people/projects) gated per-line via `/reviewlife`, riding the existing JSON call (zero new LLM calls); owner-confirmed per-owner/no-nag/cap-20. **6.1 step-1 instrument** (`v2026-08-24.9`): `/audit` now shows `; N cached` from the usage block (`_usage_cached_tokens`, both provider shapes) — the read-only diagnostic that answers "is prompt caching live for our routes?"; the *answer* still needs a live `/audit` read post-deploy. **Harvest:** C1 → 8 and C5 → 3, both from **stop-hook catches on the final report** (unlabeled VPS `vps-sync` block; an unhedged "does a real day produce a good suggestion?" that was an unverified prediction) — the guards did their job. 1 Minor: both releases shipped a changelog claim that overreached the diff (5.9 "REVIEWLIFE=0 stops the drafting" gated only the enqueue; 6.1 "% of in" wrong for the flat usage shape), both caught by step-7 `/code-review` — 2nd occurrence of the 2026-08-24 cost-overclaim shape, guard (mandatory `/code-review`) already exists. 0 new constraints, 0 mechanisms owed. **What worked:** `/code-review` caught 4 (5.9) + 4 (6.1) real defects a green suite missed; `host-guard`/`theory-guard` caught both report slips; the boolean-flag census forced the REVIEWLIFE DEFAULTS entry. **Open (both need one owner action):** `v2026-08-24.8` and `.9` sit un-deployed on main — owner runs `vps-sync.sh` per instance (`/audit` must show `2026-08-24.9`); the same post-deploy `/audit` readings answer 5.9's real-day done-when AND 6.1's live cache read (stopping rule: persistent `0 cached` closes 6.1 not-applicable, nonzero opens step 2 — do not touch `assemble_messages` until then). CI on `ad9f39c` + `d332fc8` confirmed `completed \| success` by hand (runs #1015, #1017). |
