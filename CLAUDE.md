# SillyTavernPresets — Claude Code Standing Instructions

## What this repo is

A Python Telegram companion bot system (`telegram-companion-bot/bot.py`) running seven AI
character instances, all on a VPS under systemd (migrated off the Termux phone
2026-07-26). One `bot.py` handles all
characters; instances differ only by directory, `.env`, and SillyTavern v2 character card.
The repo root also archives standalone SillyTavern presets/cards and an unrelated
`voicekit-starter/` project.

## Docs map — read the right doc, not all of them

All under `telegram-companion-bot/` unless noted:

- `CHANGELOG.md` — **read before any bot.py change** (root causes of every shipped
  fix); add an entry after shipping one (root cause first). Skip only for pure
  content edits.
- `ROADMAP.md` — what's next and why; Track 4 is the audit backlog.
- `IMPROVEMENTS_PLAN.md` — release-by-release handoff specs for the Track 4 work.
- `AUDIT-2026-07-10.md` — 2026-07 audit findings, incl. rejected claims (don't re-fix).
- `GROUP_CHAT_DESIGN.md` — **read before touching any GROUP_* code**; survived 4
  adversarial review rounds.
- `OPS_MANUAL.md` — day-to-day operation + the **full bot command reference**.
- `SETUP_GUIDE.md` — standing up a new instance (or use `new-bot.sh`).
- `.env.example` — every variable bot.py reads, documented with defaults.
- `.claude/memory/operational-log.md` — one row per failure that changed the system.

## Operating rule

General method (scoping, evidence, verification, calibrated reporting):
`.claude/OPERATING_MANUAL.md` — **read it before non-trivial work**; it owns that layer,
which is why this file no longer restates it. Project rules here override it.

For complex work (multi-step, behavior-changing, or fleet-touching), read
`.claude/operating/fable-to-opus.md` before acting — it carries owner-settled
decisions and session-earned traps. For simple work, do not load it.

Detailed procedure lives in skills, not here. `.claude/skills/skill-router/SKILL.md`
is the index — consult it and load on demand.

The machinery that enforces this is real, not advisory:

- **`.claude/evals/run-evals.sh`** — past incidents pinned as runnable checks.
  **Run it before claiming any change done.** A failure recurring twice earns a new
  eval. Includes a secret scan (the repo is private since 2026-07-28, but cards and
  presets were public via raw URLs for months — assume anything committed before then
  is exposed) and
  BOT_VERSION↔changelog sync.
- **Hooks** (`.claude/hooks/`) — including a **delivery gate** that blocks ending a
  turn with a modified bot.py lacking a BOT_VERSION bump, changelog entry, or compile
  evidence.
- **CI** (`.github/workflows/evals.yml`) — same evals + pytest on `main`/`claude/**`.
  `vps-sync.sh` hard-resets the VPS checkout to `origin/main` before copying, so
  **a red run on main is a deploy blocker.**
- Routines are recorded in `.claude/operating/routines.md` — keep it and the live
  Routine in sync.

Do not load unrelated skills.
Do not rewrite large files unless the task requires it.
Every completion must include the verification command actually run.

## Where things live

**`.claude/skills/skill-router/SKILL.md` is the routing table — read it, don't guess.**

**Do not re-add a "quick reference" copy of that table here.** The last one drifted,
omitted seven skills, and misrouted a session (F2, `.claude/SCAFFOLDING-AUDIT-2026-07-30.md`);
no check catches a new one. A one-line description of every skill already reaches you for
free and cannot go stale.

Two composition facts the per-skill descriptions can't tell you:

- `repo-change-control` and `bot-code-invariants` ship together for any bot.py change.
- `repo-validation-gate` applies before declaring **anything** done, and
  `artifact-first-delivery` before deciding where any output goes. Neither is preloaded —
  load them.

## Known-deliberate — do not "fix" these

- **Emily runs `zai-org/glm-4.7:thinking`**, not glm-5 (owner-confirmed 2026-07-25).
  Per-instance model choice is expected, not drift.
- **bot.py stays a single file.** The whole deploy model depends on it. Recorded
  non-goal — don't propose splitting it.
- **`AUDIT-2026-07-10.md` records rejected claims.** Check it before "fixing" a
  finding someone already ruled invalid.
- **`.claude/.runtime/` is gitignored.** Never commit it, never add it back.

## Bot instances

**All seven run on the VPS under systemd** (six migrated 2026-07-26; marcus created 2026-07-29) — the Termux phone is empty
(ROADMAP 1.2 Phase 2 complete).

| Session | Directory | Character card |
|---------|-----------|----------------|
| `nora` | `/opt/telegram-bots/nora/` | `nora.json` |
| `bonnie` | `/opt/telegram-bots/bonnie/` | `bonnie.json` |
| `cass` | `/opt/telegram-bots/cass/` | `cass.json` |
| `emily` | `/opt/telegram-bots/emily/` | `emily_harper.json` |
| `priya` | `/opt/telegram-bots/priya/` | `priya.json` |
| `jules` | `/opt/telegram-bots/jules/` | `jules_nakagawa.json` |
| `marcus` | `/opt/telegram-bots/marcus/` | `marcus_calder.json` |

All instances share the venv at `/opt/telegram-bots/venv/`; `bot.py` lives at
`/opt/telegram-bots/bot.py`. Each runs as `bot@<instance>` (unit file
`deploy/bot@.service`, `WorkingDirectory=/opt/telegram-bots/%i`).

The instance directory is the basename on the `=== STARTUP AUDIT === … Instance:`
line — **that runtime value is authoritative** if it ever disagrees with this table.
The authoritative instance list is the set of `bot@<instance>` systemd units.

**Phone-era tooling is historical.** `update-all.sh`, `sync-cards.sh`,
`watchdog.sh`, `run-bot.sh` and the `.supervise.sh` supervisor were Termux-only and
now manage nothing; VPS deploys go through `deploy/vps-sync.sh` (see Deployment
below). The phone retains `~/<name>-bot.migrated` rollback dirs until the 14-day soak
ends **2026-08-09**; after that date this sentence is stale — confirm before relying on it.

## Stack

- Python **3.12** on the VPS (Ubuntu 24.04) — the `=== STARTUP AUDIT ===` line reports
  the live version; trust it over this file. CI pins the same version in
  `.github/workflows/evals.yml` and the `runtime-version-pinned` eval fails if the two
  diverge — change both together. The phone's cp314 wheel scarcity is historical: wheels
  are now readily available, so a new binary dependency is no longer likely to compile
  from source.
- `python-telegram-bot >=21.0,<22.0` (async, job-queue). PTB v21's deprecated
  `asyncio.get_event_loop()` call is worked around in `main()` — don't remove it.
- NanoGPT — OpenAI-compatible API at `https://nano-gpt.com/api/v1`.
- SillyTavern `chara_card_v2` JSON cards.
- Repo `biggieb327-lgtm/SillyTavernPresets` — **private since 2026-07-28**. Anonymous
  `raw.githubusercontent.com` URLs 404, so any doc or script still telling you to `curl`
  one is stale. Deploys read from the checkout at `/opt/telegram-bots/.repo`.

## Deployment

All seven instances deploy from `main` via **`deploy/vps-sync.sh`**, one invocation per
instance — it pulls `preset.txt`, the instance's preset layers and card, and `bot.py`
(compile-checked, `bot.py.bak` kept), normalizes `CHARACTER_CARD`, restarts and
enables the unit, then prints hash + STARTUP AUDIT verification:

```bash
# host: VPS (as root)
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh <instance>
```

It fetches and hard-resets the checkout to `origin/main` before copying anything, so
running the on-disk copy is correct even when the checkout is stale. **Not** curl-piped —
the repo is private and raw URLs 404.

Exact commands, verification, and rollback: **`deploy-and-verify-fleet`**.

**`/update` is dead as a deploy path.** The handler still exists, but it downloads over
raw URLs, so on the private repo it fails with `repo_not_readable` and replies telling the
owner to run `vps-sync.sh` instead (see `update_cmd` in bot.py). `update-all.sh` and
`sync-cards.sh` are historical for the same reason.

**Bump `BOT_VERSION` on every release** — it's how `/audit` proves a deploy landed.
The delivery gate enforces this.

Ops essentials: `/restart` `/audit` `/errors [N]` `/backup`.
Full command reference: `OPS_MANUAL.md`.

## Working principles

Scoping, evidence, uncertainty, and stopping are `.claude/OPERATING_MANUAL.md`'s job — it states
each with a threshold and a test, so they are not restated here. What is project-specific:

1. **Unattended runs never block on a question.** Routines and loops fire with nobody
   watching: pick the most reasonable reading, proceed, and record the assumption in the
   output. Ask first only when someone is there to answer.
2. **Out-of-scope smells get surfaced, not fixed** — name them as follow-ups in the
   report, keep them out of the diff.
3. **Suggest better approaches** — durable wins over tactical patches are welcome, even
   when the better answer is bigger than what was asked.
4. **Document every diagnosed failure.** Once a live-ops or code failure is root-caused
   and resolved, add an operational-log row (`.claude/memory/operational-log.md`) before
   calling the task done — even when the fix is a doc/guardrail update rather than a
   bot.py change, and even when nothing shipped to CI. The log is the system's memory;
   an undocumented incident is one a future session re-diagnoses from scratch.
5. **Log your own mistakes to `.claude/memory/constraints.md` the moment you notice
   them.** That file records mistakes made *doing the work* — wrong host, a "done" that
   was one instance of a class, a theory asserted as fact — as opposed to the operational
   log's record of the *system* failing. The test: did a bot misbehave, or did we?
   **Read it before fleet-touching or multi-step work**; its whole value is being read
   before the same mistake repeats. Slips you caught and fixed **mid-task** still get
   logged, in that file's **Minor** running log — log them *because* they were
   self-corrected: they cost real minutes and nobody else ever sees them. That file's
   own header owns the rest (`seen` counts, the `seen: 2` graduation rule, promotion
   out of Minor) — don't restate it here.
6. **Subagents are pre-authorized (owner standing grant).** Delegation for work that
   genuinely warrants it — broad multi-file search, an independent review pass, parallel
   investigation, or any contract in `.claude/agents/` — does **not** need a fresh
   per-turn request. In this repo, breadth or multiple parts *does* count as the user
   having asked. Not mandatory: prefer inline work when the task is small, the context is
   already loaded, or the budget-governor is live. This is the **durable** statement of
   the grant, paid once per session; `.claude/hooks/agent-authorization.py` re-asserts it
   only on the turns where a server-side instruction would otherwise override it.

## Git workflow

- Develop on `claude/...` branches if useful, but **always merge green work to `main`**
  — deploys and doc links pull from `main`, so an unmerged branch ships nothing. Owner
  policy (2026-07-18): merge task branches to `main` autonomously once the full
  verification block is green; a designated feature branch is where you *develop*, not
  a place work should stop. (If a session-level instruction pins you to a branch and
  forbids pushing elsewhere, that owner standing permission is your explicit go-ahead.)
- **Merge to main by pushing the branch ref:** `git push origin <branch>:main` (a
  fast-forward when the branch sits on `origin/main`'s tip — verify with
  `git rev-parse <branch>^` vs `origin/main`). Do **not** `git checkout main` and merge
  there: a cloud session's local `main` can be a stale branch with *no merge-base* against
  `origin/main`, and the eval suite run on it reports a confident green about nothing
  (hit 2026-07-29; constraints C13).
- Commit real work **before** break-testing evals; revert test injections by
  re-editing, never `git checkout` on a file with uncommitted changes.
- **New-feature default policy (owner, 2026-07-18):** new features default **ON** with a
  mandatory env kill switch (unset = active, `0` = off). The kill switch is required;
  default-on is the norm. Details in `bot-code-invariants` #16.

## Repo layout

`telegram-companion-bot/` holds everything that deploys: `bot.py`, the ops scripts,
character cards + seed dirs, `preset.txt`, `tests/`, `deploy/` (VPS), and the docs
above. `ls` it for the rest. The non-obvious bits:

- `requirements.txt` is the single source of truth for pip installs.
- `preset.txt` is the shared voiceprint — editing it changes **all seven** bots.
- `watchdog.sh`, `backup-all.sh`, `cleanup-all.sh` are phone-era leftovers: they were
  curl-installed onto the phone once, and no VPS deploy path touches them. Editing them
  in-repo ships nothing.
- `character-review/` (root) is the card inbox for the monthly character pass — the
  `character-pass-monthly` Routine reads it and writes proposals, never edits (see its
  README). On-demand reviews and voice-defect triage: the `character-reviewer` agent.
- `caa16137-nora.json` (root) is a SillyTavern archive copy that has **diverged** from
  the bot's `nora.json` — not a mirror, never sync them.
- `voicekit-starter/` is a separate project; none of the bot's rules apply to it.
- `idea-scraper-actor/` (root) is a separate project too — a custom Apify actor
  the `improvement-loop-monthly` and `character-pass-monthly` Routines call for
  their Reddit + Substack idea scans (see its README and
  `.claude/operating/routines.md`). Not deployed by anything in this repo; the
  owner deploys it to Apify by hand (`apify push`).

Nothing else at the repo root deploys anywhere: the standalone SillyTavern presets and
cards (`TheAtelier*`, `UnifiedWritersRoom*`, `Chimera*`, `WritersBlock*`,
`megumin-mobile/`), `vault/` (a knowledge snapshot built 2026-07-11 and pinned to commit
`d76dcdf` — **an archive, not a source of truth**; it describes the phone-era system and
is excluded from the secret scan), and `weekly-budget.html` + `index.html` (an unrelated
personal budget page).
