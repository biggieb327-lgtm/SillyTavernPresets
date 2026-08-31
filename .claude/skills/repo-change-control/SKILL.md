---
name: repo-change-control
description: End-to-end procedure for shipping any bot.py change (feature, bugfix, refactor). Load BEFORE editing bot.py whenever the change is meant to reach the fleet — i.e. almost every bot.py edit. Covers the read-first rules, versioning, changelog, verification, merge to main, and the deploy handoff.
---

# Ship a bot.py release

All seven instances deploy from `main` via `deploy/vps-sync.sh` (one invocation per
instance, run on the VPS as root) — see `deploy-and-verify-fleet` for the full command
and the instance list. Merging to main = making it deployable; the user (or you, if you
have VPS access this session) then runs `vps-sync.sh` per instance. `/update` is retired:
the handler still exists but does an in-place single-file swap that bypasses the
immutable-release deploy (its raw fetch works again now the repo is public — that is not
a reason to use it).
Your job ends at "merged, green, deploy instructions given."

## When NOT to use

- Card/seed/preset edits with no bot.py change → `edit-cards-and-presets`.
- Diagnosing a live problem (no fix known yet) → `repo-debugging-playbook` first.
- Docs-only or `.claude/`-only changes: no BOT_VERSION bump, no changelog release
  entry (use a `## YYYY-MM-DD — ...` heading if the change deserves a changelog note
  at all). The delivery gate only fires when bot.py itself changed.

## Procedure

1. **Read before editing** (non-negotiable, in this order):
   - `telegram-companion-bot/CHANGELOG.md` — skim ALL headings, then fully read the
     entries touching the subsystems you'll change: if your planned change resembles
     a past incident, the entry usually contains the constraint that makes the naive
     fix wrong.
   - `telegram-companion-bot/AUDIT-2026-07-10.md` §"rejected" + ROADMAP §"Rejected or
     already covered" — do not re-implement rejected ideas.
   - If touching anything group-related → stop, load `group-chat-changes`.
   - Load `bot-code-invariants` and keep it open while writing the diff.

2. **Fresh-container setup** (once per session, before any test/eval run):
   ```bash
   python3 -m venv /tmp/telegram-bot-verify-venv
   /tmp/telegram-bot-verify-venv/bin/python -m pip install \
     --require-hashes --only-binary=:all: -r telegram-companion-bot/requirements.lock
   /tmp/telegram-bot-verify-venv/bin/python -m pip install pytest==8.4.2
   PATH=/tmp/telegram-bot-verify-venv/bin:$PATH bash .claude/tools/verify.sh
   ```
   Without the isolated environment, `bot-imports` can skip on `ModuleNotFoundError`
   and pytest can die inside Debian's system cryptography. Both are environment gaps,
   not code bugs. Never repair them with root pip in the system interpreter (C24): use
   the disposable exact-lock venv, then classify any remaining traceback.

3. **Implement.** Small diffs: one release = one theme (a mega-release risks all seven
   bots at once). New/changed env vars get documented in `.env.example`. Per owner
   policy (2026-07-18) new features default **ON** with a mandatory env kill switch —
   *unset = feature active*, `0`/off disables without a redeploy (see
   `bot-code-invariants` #16).

4. **Tests.** Every new pure function gets pytest coverage in
   `telegram-companion-bot/tests/test_pure.py` (the `conftest.py` fixture stands up a
   fake instance so `import bot` works — reuse it, don't invent a new import path).

5. **Version + changelog** (the delivery-gate Stop hook blocks the turn otherwise):
   - Bump `BOT_VERSION` in bot.py (`grep -n '^BOT_VERSION' telegram-companion-bot/bot.py`),
     scheme `YYYY-MM-DD.N` — increment N for same-day releases.
   - Add a `## v<exact BOT_VERSION>` entry at the TOP of CHANGELOG.md, **root cause
     first, fix second**. The `version-changelog-sync` eval fails if the newest
     `## v` heading ≠ BOT_VERSION.
   - **Prove every behavioral claim against the final diff, not the design.** A sentence
     asserting what the change *does* — "adds no model call", "net-neutral", "kill switch
     stops drafting", "cannot send twice", "cached tokens are N% of input", "this path
     never reaches Telegram" — needs one of: a test that demonstrates it, a before/after
     runtime observation, or a complete code-path trace where it is unambiguous. Intent is
     not evidence, and this is a repeat class: `/reviewlife`'s kill switch first stopped the
     enqueue but not the model call, and the cached-token percentage held for one usage
     shape but not all — both written from the feature's design, both caught only at review
     (step 7). Verify each claim against the diff *before* it reaches review.

6. **Verify** — one command, and paste its real output:
   ```bash
   bash .claude/tools/verify.sh
   ```
   Runs py_compile, pytest, `run-evals.sh` and `gate_corpus`, then prints the advisory
   sweep. It exists so "I ran the tests" cannot quietly mean a different subset each
   time. The individual commands still work if you need one in isolation.

   **If this release FIXES something, also sweep for the rest of the class** before
   step 7 — on 2026-07-25 every point fix that day turned out to be a class, and the
   rework cost most of a session:
   ```bash
   python3 .claude/tools/sweep.py
   ```
   Advisory, not a CI gate: it emits *candidates*, and judgement is required (a real
   hit may be correctly mitigated). Triage each one, then load `fix-the-class` if the
   sweep — or the shape of the bug — suggests other instances exist.

7. **Review the diff before merging it.** Green tests are not a review: on 2026-08-02 a
   `/code-review` pass over one day's 13 releases found six defects a fully green suite
   had shipped, including `/features <name> on|off` raising `ValueError` on every
   invocation for four releases. Run it on the diff you are about to merge:
   ```bash
   /code-review          # reviews the working diff; /review is for a GitHub PR
   ```
   Fix what it finds, or say in the report why a finding is not real —
   `verify-external-audit` applies to its output exactly as it does to any other
   outside claim, because a review is a batch of *claims*, not a batch of defects.
   **Two of the six were mis-diagnosed** on that pass and re-checking changed the fix.

   Mechanically enforced half: the delivery gate blocks the turn if the diff touches a
   `*_cmd` handler that no test **calls** (`sweep.py source-assertion` lists the
   backlog). A test that reads a handler's source cannot fail for the reason the
   handler exists — that is the defect the review found, five times over.

8. **Commit on the session's `claude/...` branch, then merge to `main` and push.**
   Standing policy (owner-approved 2026-07-11): merge autonomously **only when steps 6–7
   are fully green**. Any red check = stop, report, do not merge.
   ```bash
   git checkout main && git pull origin main && git merge <branch> && git push -u origin main
   ```
   Never force-push main (risk-guard blocks it; deploys would brick).

9. **Update planning docs in the same session**: mark the shipped item done in
   `ROADMAP.md` (this was skipped after R1–R6 and the docs drifted). If the release
   closed an operational-log "Next" item, note it there.

10. **Hand off the deploy.** Tell the user exactly:
   - `/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh <instance>`,
     once per instance (nora, bonnie, cass, emily, priya, jules, marcus) — it fetches
     and hard-resets the checkout to `origin/main`, so it's correct even if the
     on-disk checkout is stale.
   - `/audit` on each instance afterward — MUST show the new BOT_VERSION.
   - Full command block, verification, and rollback: `deploy-and-verify-fleet`.

## Quality bar

- Diff does one thing; nothing unrelated reformatted or "improved".
- Zero new per-message LLM calls (extend `post_reply_analysis` JSON instead).
- Every invariant in `bot-code-invariants` checked against the final diff.
- Changelog entry explains the root cause well enough that a future session
  won't re-diagnose it from scratch.
- Every behavioral claim in the changelog/docs is backed by a test, a runtime
  observation, or a full code-path trace — not the feature's intent.

## Verification checklist

- [ ] `bash .claude/tools/verify.sh` green — actual output seen, not assumed
- [ ] `/code-review` run on the diff; every finding fixed or refuted in the report
- [ ] No `*_cmd` the diff touches is left un-called by tests (the delivery gate blocks it)
- [ ] BOT_VERSION bumped and equals the newest `## v` changelog heading
- [ ] Every behavioral changelog/doc claim proven against the final diff (test, runtime
      observation, or full code-path trace) — not asserted from intent
- [ ] New env vars in `.env.example`, unset = old behavior
- [ ] New pure functions have tests
- [ ] Merged to main and pushed; CI (`evals` workflow) **polled** on main and
      reported as `<sha> | completed | success` — not asserted from having pushed
- [ ] ROADMAP/plan docs updated
- [ ] Deploy instructions given to the user

## Common mistakes

- Fixing the environment's missing deps by editing bot.py (see step 2).
- Bumping BOT_VERSION but titling the changelog entry with a date heading (or vice
  versa) — the sync eval catches it late; get it right up front.
- Leaving work on the claude/ branch: the fleet deploys from main, so an unmerged
  green branch ships nothing.
- Proposing to split bot.py into modules. Recorded non-goal; immutable releases still
  ship bot.py as the single application entrypoint used by every instance.
- Running `git checkout -- bot.py` to undo an experiment while the file holds
  uncommitted real work — this destroyed ~700 lines once. Commit real work first;
  revert experiments by re-editing.

## What to report back

Version shipped, one-line root cause, the three verification outputs (pasted),
merge commit on main, CI status, and the exact `vps-sync.sh` command(s) the user
should run on the VPS.
