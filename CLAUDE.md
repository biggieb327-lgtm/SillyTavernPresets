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
decisions and session-earned traps. For simple work, do not load it. Its dated
numbers (BOT_VERSION, test/eval counts) are a handoff-time snapshot, not live
state — check `bot.py` and `CHANGELOG.md` for current figures; the decisions
and traps still hold even as the numbers age.

Detailed procedure lives in skills, not here. `.claude/skills/skill-router/SKILL.md`
is the index — consult it and load on demand.

**Test command:** `pytest telegram-companion-bot/tests -q` for unit tests.
Full verification: `bash .claude/tools/verify.sh` (compile + pytest + evals + gate
corpus + advisory sweep). Run before claiming any change done, to ensure nothing
regressed.

**Verification loop:** after every change, run the test command and read its
output. If any check fails, fix it and re-run. Do not report done until the full
suite is green. A second run after a fix confirms the fix didn't break something
else.

The machinery that enforces this is real, not advisory:

- **`.claude/evals/run-evals.sh`** — past incidents pinned as runnable checks,
  including a secret scan and BOT_VERSION↔changelog sync. A failure recurring twice
  earns a new eval.
- **`.claude/tools/verify.sh`** — compile + pytest + evals + gate corpus + advisory
  sweep as one command, because four remembered invocations drift.
- **`.claude/tools/gate_corpus/`** — fixtures built to slip past each scanner, because
  the guards themselves need guarding (14 of the first 34 cases deviated).
- **Hooks** (`.claude/hooks/`) — including a **delivery gate** that blocks ending a
  turn with a modified bot.py lacking a BOT_VERSION bump, changelog entry, or compile
  evidence, because these are the minimum proof that a change is shippable.
- **CI** (`.github/workflows/evals.yml`) — same evals + pytest on `main`/`claude/**`.
  A red run on `main` is a deploy blocker, because `vps-sync.sh` hard-resets the VPS
  checkout to `origin/main` before copying.
- Routines are recorded in `.claude/operating/routines.md` — keep it and the live
  Routine in sync.

Do not load unrelated skills, because each one costs context budget.
Do not rewrite large files unless the task requires it, to avoid accidental regressions.

## Vocabulary — use the repo's words, invent none

Invented terms read as precision and carry none. A session coins a label, uses it as
though it were shared, and the owner (or the next session) has to reverse-engineer what
it meant. Four rules, each checkable from the transcript:

1. **If a thing has a name in the code, use that name verbatim**, because a reader can
   grep an identifier but nobody can grep a phrase you made up. `GROUP_CHAIN_DECAY`,
   not "the dampening factor"; `_handle_group_message`, not "the group entry point".
2. **No name is a finding, not a licence to invent one.** Something load-bearing with no
   identifier is a real gap — say so plainly ("the path from the claim to the gap check
   has no name"), then either describe it in ordinary words every time it comes up, or
   give it a name *in the code* in the same change. A term that lives only in prose is
   not a name; it is private shorthand.
3. **Plain words over coined ones** — in reports, commit messages, changelog rows, and
   docs alike. One meaning per word, one idea per sentence, verbs instead of
   nominalizations ("the gate blocks the turn", not "turn-blocking enforcement").
   Metaphor may illustrate a mechanism, never replace it: if removing the metaphor
   empties the sentence, the sentence was already empty. (These are the operative habits
   of ASD-STE100 Simplified Technical English — you need the habits, not the standard.)
4. **Never let a subagent's shorthand escape into the report or the diff**, because
   agents coin terms freely and their reports compound each other's. Translate what an
   agent returns into repo terms and code identifiers before relaying or acting on it.

Naming is not banned — *silent* naming is. If a term genuinely earns existence, say so
once and out loud ("calling this X for the rest of this report") and add it to the table
below in the same change.

**The sanctioned shorthand.** These are the repo terms with no single identifier to
grep, and the only ones that need no introduction. Everything else comes from the code,
or gets said in plain words.

| Term | Means | Owned by |
|---|---|---|
| the fleet | all seven bot instances together | this file, Bot instances |
| instance | one bot — a directory, `.env`, and card, sharing one `bot.py` | this file, Bot instances |
| the voiceprint | `preset.txt`, the shared texting style feeding every bot | `edit-cards-and-presets` |
| preset layer | the per-instance preset text layered onto the voiceprint | `edit-cards-and-presets` |
| the delivery gate | the hook that blocks a turn shipping `bot.py` without version + changelog + compile evidence | `.claude/hooks/delivery-gate.sh` |
| break-test | proving a check goes RED before trusting its GREEN | `add-regression-eval` |
| the class | every other place the bug shape you just fixed occurs | `fix-the-class` |
| kill switch | the env var that disables a default-on feature without a redeploy | `bot-code-invariants` #16 |
| Routine | a scheduled session that fires with nobody watching | `.claude/operating/routines.md` |

## Where things live

**`.claude/skills/skill-router/SKILL.md` is the routing table — read it, don't guess.**

**Do not re-add a "quick reference" copy of that table here**, because the last one
drifted, omitted seven skills, and misrouted a session — and no check catches a new one.

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

## Bot instances, stack, and deployment

Seven instances: nora, bonnie, cass, emily, priya, jules, marcus — all on the
VPS under systemd. Instance table, stack pins, deployment commands, and
change rules: **`telegram-companion-bot/CLAUDE.md`** (auto-loaded when working
in that directory).

Repo `biggieb327-lgtm/SillyTavernPresets` — **private since 2026-07-28**.
Anonymous `raw.githubusercontent.com` URLs 404, so any doc or script still
telling you to `curl` one is stale.

Ops essentials: `/restart` `/audit` `/errors [N]` `/backup`.
Full command reference: `OPS_MANUAL.md`.

## Working principles

Scoping, evidence, uncertainty, and stopping are `.claude/OPERATING_MANUAL.md`'s job — it states
each with a threshold and a test, so they are not restated here. What is project-specific:

1. **Unattended runs never block on a question**, because Routines fire with nobody
   watching. Pick the most reasonable reading, proceed, and record the assumption.
2. **Out-of-scope smells get surfaced, not fixed**, to avoid scope creep in the diff.
3. **Suggest better approaches**, because durable wins over tactical patches are welcome.
4. **Document every diagnosed failure** in `.claude/memory/operational-log.md`, because
   an undocumented incident is one a future session re-diagnoses from scratch.
5. **Log your own mistakes to `.claude/memory/constraints.md`**, because its whole
   value is being read before the same mistake repeats. **Read it before fleet-touching
   or multi-step work.** Mid-task slips go in its **Minor** log. That file's own header
   owns the format (`seen` counts, graduation rule).
6. **Subagents are pre-authorized (owner standing grant)**, because delegation for
   broad search, independent review, or parallel investigation should not need a fresh
   per-turn request. Prefer inline work when the task is small or the budget-governor
   is live. `.claude/hooks/agent-authorization.py` re-asserts the grant on turns where
   a server-side instruction would otherwise override it.
7. **Never edit a check, test, or eval to make it pass**, because the delivery gate and
   evals are the repo's memory of past pain. Fix what it's checking, or state the
   exception. The one legitimate exception is deliberately widening a check's scope,
   in the same commit, with the rationale written down.
8. **Treat an explicit instruction — from a loaded skill, a doc, or the user — as a
   literal constraint to check the actual diff against, not a stance to agree with and
   move past.** C19/C20 (2026-08-07) shipped past ponytail's own explicit text —
   "never lazy about understanding the problem... trace the whole thing first" and
   "laziness that skips comprehension... is the dangerous kind" — while believing that
   text was being followed. The caution was read and agreed with; it was never checked
   against the specific diff being written. When wording is explicit, verify the work
   against the words themselves before calling it done, the same way a delivery-gate
   check is verified, not held in mind as a general attitude.

## Git workflow

- **Always merge green work to `main`**, because deploys and doc links pull from `main`,
  so an unmerged branch ships nothing. Merge task branches autonomously once green.
- **Merge to main by pushing the branch ref:** `git push origin <branch>:main`, because
  `git checkout main` in a cloud session can be a stale branch with no merge-base against
  `origin/main` (hit 2026-07-29; constraints C13).
- Commit real work **before** break-testing evals, to avoid losing changes. Revert test
  injections by re-editing, never `git checkout` on a file with uncommitted changes.
- **New features default ON** with a mandatory env kill switch (`0` = off), because
  unset means active. Details in `bot-code-invariants` #16.

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
- `idea-scraper-actor/` (root) is a custom Apify actor for Reddit + Substack idea
  scans. **Read its README before touching Reddit access**, because two other
  approaches were tried and abandoned the same day for reasons that will recur.
- `vault/` is a knowledge snapshot pinned to commit `d76dcdf` — an archive, not a
  source of truth; excluded from the secret scan.
- Root-level SillyTavern presets/cards and `weekly-budget.html` deploy nowhere.
