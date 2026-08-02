---
name: ship
description: One command for the release ritual — verify, review, merge to main, confirm CI, hand off the fleet deploy. Load when work is finished and needs to become a deployed release. It ORCHESTRATES repo-change-control and deploy-and-verify-fleet; it does not restate them.
---

# Ship it

The fix→verify→merge→CI→deploy loop, in order, with nothing duplicated.

**This skill owns sequencing only.** Every step's actual procedure lives in the skill
named beside it, and that skill is authoritative. A third copy of the release procedure
is how the last consolidated table drifted, omitted seven skills, and misrouted a session
(CLAUDE.md §Where things live). If a step's detail seems to be missing here, that is
deliberate — go to the owner.

## When NOT to use

- Mid-change. This starts at "the work is written". Editing bot.py → `repo-change-control`
  from step 1.
- Docs or `.claude/`-only changes: no BOT_VERSION, no changelog release entry, no fleet
  deploy. Run `.claude/tools/verify.sh` and merge.
- The deploy alone, for work already on main → `deploy-and-verify-fleet` directly.

## The sequence

1. **Verify.** One command, four required checks plus the advisory sweep:
   ```bash
   bash .claude/tools/verify.sh
   ```
   Green means py_compile, pytest, run-evals.sh and gate_corpus all passed. Any red =
   stop. Do not continue on a partial pass — that is what the script exists to prevent.

2. **Review the diff** — `/code-review` on what you are about to merge. Treat findings as
   *claims*: `verify-external-audit`. Owner: `repo-change-control` step 7.

3. **Version + changelog**, if bot.py changed. `BOT_VERSION` is `YYYY-MM-DD.N`, N
   incrementing per same-day release, and the newest `## v` changelog heading must equal
   it exactly. **The repo does not use git tags** — `git tag` is empty and always has
   been; the version lives in bot.py and `/audit` is how a deploy is proven. Owner:
   `repo-change-control` step 5. The delivery gate blocks the turn otherwise.

4. **Merge to main.** Push the branch ref — `git push origin <branch>:main` — after
   confirming `git rev-parse <branch>^` equals `origin/main`. Never `git checkout main`
   in a cloud session (C13). Owner: CLAUDE.md §Git workflow.

5. **Confirm CI.** The `evals` workflow on `main` must reach `conclusion: success`
   **before** any deploy: `vps-sync.sh` hard-resets the checkout to `origin/main`, so a
   red main is a fleet-wide deploy blocker. Report the head SHA and the conclusion, not
   "CI is green" — an unpolled claim is an assumption wearing a fact's clothes.

6. **Hand off the deploy.** All seven instances, one `vps-sync.sh` invocation each, run
   sequentially on the VPS as root. Then `/audit` per instance showing the new
   BOT_VERSION — the only proof a running process picked the change up. Owner:
   `deploy-and-verify-fleet`, which has the exact block and the rollback.

## What "done" means

Merged, CI green on main with the SHA quoted, deploy commands handed over, and — for a
bot.py release — the new BOT_VERSION visible in `/audit` on every instance. Steps 1-5 are
yours; step 6's execution belongs to whoever has the VPS shell, which is not this
container.

## Common mistakes

- Reporting CI green without polling it.
- Deploying before the merge lands (`vps-sync.sh` reads `origin/main`, so it would ship
  the previous release and look like a no-op).
- Assuming a `vps-sync.sh` batch landed. The swap is locked (ROADMAP 1.6, shipped
  2026-08-01), so a concurrent run is refused rather than corrupting — but a refused
  run deploys nothing, so it leaves that instance on the old version. `/audit` each.
- Treating `verify.sh --quick` as sufficient for a release. It skips the sweep, which is
  where a fix's *class* shows up.
